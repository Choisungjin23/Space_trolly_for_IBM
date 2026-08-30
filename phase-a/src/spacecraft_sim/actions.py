"""Rule-based action generator (A-9). No AI, no hardcoded module ids.

Given any scenario graph, emit the generic actions the situation affords:
close hatches/IMV around fire modules, shut down ventilation, isolate a module,
evacuate crew, power down equipment. Every action's `apply` works on a deep
copy — the input scenario is never mutated.
"""

from dataclasses import dataclass, field
from typing import Callable

from spacecraft_sim import config
from spacecraft_sim.crew import find_route, functions_of, module_is_hazardous, move_crew
from spacecraft_sim.models import Scenario


@dataclass(frozen=True)
class Action:
    id: str
    kind: str  # do_nothing | close_hatch | close_imv | shutdown_ventilation
               # | isolate | evacuate | power_down
    label: str
    description: str
    params: dict = field(default_factory=dict)

    def apply(self, scenario: Scenario) -> Scenario:
        sc = scenario.model_copy(deep=True)
        _APPLIERS[self.kind](sc, self.params)
        return sc


def _apply_do_nothing(sc: Scenario, params: dict) -> None:
    pass


def _apply_close_path(sc: Scenario, params: dict) -> None:
    conn = sc.connection(params["connection_id"])
    conn.path_state = "closed"


def _apply_shutdown_ventilation(sc: Scenario, params: dict) -> None:
    conn = sc.connection(params["connection_id"])
    conn.ventilation_state = "off"


def _apply_shutdown_utility(sc: Scenario, params: dict) -> None:
    conn = sc.connection(params["connection_id"])
    setattr(conn, f"{params['resource']}_line_on", False)


def _apply_isolate(sc: Scenario, params: dict) -> None:
    module = sc.module(params["module_id"])
    module.isolated = True
    for conn in sc.connections_of(module.id):
        conn.path_state = "closed"
        conn.ventilation_state = "off"


def _apply_abandon(sc: Scenario, params: dict) -> None:
    """Deliberately stop rescue and utility allocation to one module."""
    module = sc.module(params["module_id"])
    module.isolated = True
    for crew in sc.crew:
        if crew.module_id == module.id:
            crew.abandoned = True
            crew.state = "TRAPPED"
    for conn in sc.connections_of(module.id):
        conn.path_state = "closed"
        conn.ventilation_state = "off"
        conn.power_line_on = False
        conn.air_line_on = False
        conn.water_line_on = False


def _apply_evacuate(sc: Scenario, params: dict) -> None:
    move_crew(sc, params["crew_id"], params["target_module"])


def _apply_power_down(sc: Scenario, params: dict) -> None:
    for equipment in sc.equipment_in(params["module_id"]):
        equipment.powered = False


def _apply_station_repairer(sc: Scenario, params: dict) -> None:
    # Same movement mechanics as an evacuation order; the intent differs.
    move_crew(sc, params["crew_id"], params["target_module"])


_APPLIERS: dict[str, Callable[[Scenario, dict], None]] = {
    "do_nothing": _apply_do_nothing,
    "close_hatch": _apply_close_path,
    "close_imv": _apply_close_path,
    "shutdown_ventilation": _apply_shutdown_ventilation,
    "shutdown_utility": _apply_shutdown_utility,
    "isolate": _apply_isolate,
    "abandon": _apply_abandon,
    "evacuate": _apply_evacuate,
    "power_down": _apply_power_down,
    "station_repairer": _apply_station_repairer,
}


def generate_actions(scenario: Scenario) -> list[Action]:
    """All rule-generated candidate actions for the current state."""
    actions: list[Action] = [
        Action(
            id="do_nothing",
            kind="do_nothing",
            label="Do nothing",
            description="Baseline: take no action.",
        )
    ]
    seen: set[str] = {"do_nothing"}

    def add(action: Action) -> None:
        if action.id not in seen:
            seen.add(action.id)
            actions.append(action)

    fire_modules = scenario.fire_modules()
    incident_modules = list(fire_modules)
    incident_modules.extend(
        module for module in scenario.modules if module.electrical_short and module not in incident_modules
    )

    for module in incident_modules:
        for conn in scenario.connections_of(module.id):
            pair = f"{conn.source}-{conn.target}"
            if conn.type == "hatch" and conn.path_state == "open":
                add(
                    Action(
                        id=f"close_hatch:{conn.id}",
                        kind="close_hatch",
                        label=f"Close hatch {pair}",
                        description=f"Close hatch connection {conn.id} ({pair}).",
                        params={"connection_id": conn.id},
                    )
                )
            if conn.type == "imv":
                if conn.ventilation_state == "on":
                    add(
                        Action(
                            id=f"shutdown_ventilation:{conn.id}",
                            kind="shutdown_ventilation",
                            label=f"Shut down ventilation {pair}",
                            description=f"Stop IMV airflow on {conn.id} ({pair}); duct stays open.",
                            params={"connection_id": conn.id},
                        )
                    )
                if conn.path_state == "open":
                    add(
                        Action(
                            id=f"close_imv:{conn.id}",
                            kind="close_imv",
                            label=f"Close IMV duct {pair}",
                            description=f"Physically close IMV duct {conn.id} ({pair}).",
                            params={"connection_id": conn.id},
                        )
                    )

            if conn.type == "hatch":
                for resource in ("power", "air", "water"):
                    if getattr(conn, f"{resource}_line_on"):
                        add(
                            Action(
                                id=f"shutdown_{resource}_line:{conn.id}",
                                kind="shutdown_utility",
                                label=f"Shut {resource} line {pair}",
                                description=(
                                    f"Stop {resource} supply on {conn.id} while "
                                    "leaving the other utility lines independently controlled."
                                ),
                                params={
                                    "connection_id": conn.id,
                                    "resource": resource,
                                },
                            )
                        )
        add(
            Action(
                id=f"isolate:{module.id}",
                kind="isolate",
                label=f"Isolate {module.name} ({module.id})",
                description=(
                    f"Seal {module.id}: close every connection and stop its "
                    f"ventilation. Crew inside can no longer leave."
                ),
                params={"module_id": module.id},
            )
        )

        if any(c.module_id == module.id for c in scenario.crew):
            affected = sorted(c.id for c in scenario.crew if c.module_id == module.id)
            add(
                Action(
                    id=f"abandon:{module.id}",
                    kind="abandon",
                    label=f"Abandon {module.name} ({module.id})",
                    description=(
                        f"Stop rescue and all utility supply to {module.id}; "
                        f"affected crew: {', '.join(affected)}. This option is "
                        "included so total expected surviving returnees can be compared."
                    ),
                    params={"module_id": module.id, "crew_ids": affected},
                )
            )

        if scenario.equipment_in(module.id):
            add(
                Action(
                    id=f"power_down:{module.id}",
                    kind="power_down",
                    label=f"Power down equipment in {module.id}",
                    description=(
                        f"Cut power to all equipment in {module.id}: protects it "
                        f"from smoke-induced shorts, but its systems go "
                        f"UNAVAILABLE while off."
                    ),
                    params={"module_id": module.id},
                )
            )

    # Pre-positioning: send a repair-capable crew member to a module holding
    # equipment, so that if it is damaged later someone is on site to fix it.
    # Repairs only progress with a provider present, so this is a real choice
    # made before the damage happens.
    # A scenario need not declare systems - Phase B builds capabilities from
    # equipment directly and declares none. update_repairs() still repairs that
    # equipment, falling back to the default repair function, so the action
    # that puts a repairer on site has to be offered on the same terms.
    # Deriving the set from systems alone would leave this action unreachable
    # for every such scenario.
    repair_functions = {system.repair_function for system in scenario.systems} or {
        config.DEFAULT_REPAIR_FUNCTION
    }
    modules_with_equipment = sorted({e.module_id for e in scenario.equipment})

    for crew in scenario.crew:
        if crew.state in ("EVACUATED", "TRAPPED"):
            continue
        if not (functions_of(crew) & repair_functions):
            continue
        for module_id in modules_with_equipment:
            if module_id == crew.module_id:
                continue
            if module_is_hazardous(scenario, module_id):
                continue
            if find_route(scenario, crew.module_id, module_id) is None:
                continue
            module = scenario.module(module_id)
            add(
                Action(
                    id=f"station_repairer:{crew.id}:{module_id}",
                    kind="station_repairer",
                    label=f"Station {crew.id} in {module.name} ({module_id})",
                    description=(
                        f"Move {crew.name} ({crew.id}) to {module_id} so damaged "
                        f"equipment there can be repaired on site."
                    ),
                    params={"crew_id": crew.id, "target_module": module_id},
                )
            )

    # Evacuations: crew currently in a hazardous module, to the nearest safe one.
    for crew in scenario.crew:
        if crew.state in ("EVACUATED", "TRAPPED"):
            continue
        if not module_is_hazardous(scenario, crew.module_id):
            continue
        route = find_route(scenario, crew.module_id)
        if route:
            target = route[-1]
            add(
                Action(
                    id=f"evacuate:{crew.id}:{target}",
                    kind="evacuate",
                    label=f"Evacuate {crew.id} {crew.module_id}->{target}",
                    description=(
                        f"Order {crew.name} ({crew.id}) to move from "
                        f"{crew.module_id} to {target} immediately."
                    ),
                    params={"crew_id": crew.id, "target_module": target},
                )
            )

    return actions


def find_action(scenario: Scenario, action_id: str) -> Action:
    for action in generate_actions(scenario):
        if action.id == action_id:
            return action
    raise KeyError(
        f"Action '{action_id}' is not available for this scenario. "
        f"Run the 'actions' command to list valid ids."
    )
