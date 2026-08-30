"""Crew state, modeled survival/return, and criticality (A-6, A-8).

Crew move through states
    SAFE -> EXPOSED -> EVACUATING -> EVACUATED | TRAPPED
and accumulate exposure time, SMAC dose, and an explicitly ASSUMED modeled
survival estimate used for constrained resource comparisons.

A module is hazardous when it is burning, when any species exceeds its 1-hour
SMAC (JSC 20584 Rev C), or when smoke extinction passes the assumed egress
impairment level. Note the real-unit consequence: with ventilation running, a
small fire's CO plateaus well below its SMAC, so the binding hazard is usually
obscuration, not toxicity.

A-8: `crew_weight` returns how irreplaceable a crew member's FUNCTIONS are in
the current situation (FMECA-inspired), never a value of their life.
`measured_criticality` bypasses the assumed tables entirely by measuring what
removing each crew member does to the outcome.
"""

from collections import deque

from spacecraft_sim import config
from spacecraft_sim.models import Crew, Scenario
from spacecraft_sim.mobility import (
    connection_between,
    consume_passage,
    replenish_passage_credit,
)


# ── Movement graph (crew walk through open hatches only; IMV ducts are not
#    crew passages, leaks even less so) ──────────────────────────────────────

def _traversable(scenario: Scenario, module_id: str) -> list[str]:
    modules = {m.id: m for m in scenario.modules}
    out = []
    for conn in scenario.connections_of(module_id):
        if conn.type != "hatch" or conn.path_state != "open":
            continue
        if conn.connectivity <= config.ASSUMED_HATCH_IMPASSABLE_CONNECTIVITY:
            continue
        other = conn.target if conn.source == module_id else conn.source
        if modules[module_id].isolated or modules[other].isolated:
            continue
        out.append(other)
    return out


def module_is_hazardous(scenario: Scenario, module_id: str) -> bool:
    module = scenario.module(module_id)
    if module.fire_state in ("incipient", "sustained"):
        return True
    if module.worst_smac_fraction >= 1.0:
        return True
    return module.extinction_per_m >= config.ASSUMED_EGRESS_IMPAIR_EXTINCTION_PER_M


def find_route(
    scenario: Scenario, start: str, target: str | None = None
) -> list[str] | None:
    """BFS through open hatches. With a target: route to it. Without: route to
    the nearest non-hazardous, non-isolated module. Returns hops (start
    excluded) or None when unreachable."""
    seen = {start}
    queue: deque[tuple[str, list[str]]] = deque([(start, [])])
    while queue:
        current, path = queue.popleft()
        goal_reached = (
            current == target
            if target is not None
            else (current != start and not module_is_hazardous(scenario, current))
        )
        if goal_reached:
            return path
        for neighbor in _traversable(scenario, current):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    return None


def find_evacuation_route(scenario: Scenario, start: str) -> list[str] | None:
    """Honor a declared directional hatch target; otherwise use nearest safety."""
    if scenario.escape_target_module_id:
        return find_route(scenario, start, scenario.escape_target_module_id)
    return find_route(scenario, start)


def move_crew(scenario: Scenario, crew_id: str, target_module: str) -> None:
    """Explicit evacuation order: plan a route now; TRAPPED when none exists."""
    crew = scenario.crew_member(crew_id)
    if crew.module_id == target_module:
        return
    route = find_route(scenario, crew.module_id, target_module)
    if route is None:
        crew.state = "TRAPPED"
        crew.route = []
        return
    crew.state = "EVACUATING"
    crew.route = route
    crew.hop_eta_seconds = config.ASSUMED_CREW_MOVE_SECONDS_PER_HOP


def _accumulate_dose(crew: Crew, scenario: Scenario, dt: float) -> None:
    """Add this step's fraction-of-1-hour-SMAC dose, summed over species."""
    module = scenario.module(crew.module_id)
    per_hour = sum(
        module.smac_fraction(species) for species in config.VERIFIED_SMAC_1H_MG_M3
    )
    crew.smac_dose_fraction += per_hour * dt / 3600.0


def update_crew(scenario: Scenario, t: float, dt: float, response_seconds: float) -> None:
    """One step of exposure accumulation, state transitions, and movement."""
    # Kept here (rather than in the engine) so direct library callers receive
    # exactly the same throughput behavior as a full simulation step.
    replenish_passage_credit(scenario, dt)
    rank_crew_for_evacuation(scenario)
    if scenario.escape_capacity_people is not None:
        for candidate in scenario.crew:
            if candidate.escape_seat_reserved is None:
                candidate.escape_seat_reserved = (
                    (candidate.evacuation_priority_rank or 10**9)
                    <= scenario.escape_capacity_people
                )
    # Stable priority order decides who consumes a constrained hatch slot.
    ordered_crew = sorted(
        scenario.crew,
        key=lambda crew: (-crew.evacuation_priority_score, crew.id),
    )
    for crew in ordered_crew:
        hazardous_here = module_is_hazardous(scenario, crew.module_id)

        if crew.state != "EVACUATED":
            _accumulate_dose(crew, scenario, dt)
        if hazardous_here and crew.state != "EVACUATED":
            crew.hazard_exposure_seconds += dt

        if crew.state == "SAFE":
            if scenario.escape_target_module_id and crew.module_id != scenario.escape_target_module_id:
                route = find_evacuation_route(scenario, crew.module_id)
                if route is None:
                    crew.state = "TRAPPED"
                else:
                    crew.state = "EVACUATING"
                    crew.route = route
                    crew.hop_eta_seconds = config.ASSUMED_CREW_MOVE_SECONDS_PER_HOP
            elif hazardous_here:
                crew.state = "EXPOSED"
                crew.exposed_at_seconds = t

        elif crew.state == "EXPOSED":
            if crew.exposed_at_seconds is not None and (
                t - crew.exposed_at_seconds >= response_seconds
            ):
                route = find_evacuation_route(scenario, crew.module_id)
                if route is None:
                    crew.state = "TRAPPED"
                else:
                    crew.state = "EVACUATING"
                    crew.route = route
                    crew.hop_eta_seconds = config.ASSUMED_CREW_MOVE_SECONDS_PER_HOP

        elif crew.state == "EVACUATING":
            if not crew.route:
                crew.state = "EVACUATED" if not hazardous_here else "EXPOSED"
                continue
            crew.hop_eta_seconds -= dt
            if crew.hop_eta_seconds <= 0:
                next_module = crew.route[0]
                if next_module in _traversable(scenario, crew.module_id):
                    entering_refuge = (
                        next_module == scenario.escape_target_module_id
                        and crew.module_id == scenario.escape_from_module_id
                    )
                    if entering_refuge and crew.escape_seat_reserved is False:
                        admitted = sum(
                            1
                            for candidate in scenario.crew
                            if candidate.module_id == scenario.escape_target_module_id
                            and candidate.id != crew.id
                        )
                        if admitted >= (scenario.escape_capacity_people or 0):
                            crew.state = "TRAPPED"
                            crew.route = []
                            crew.escape_capacity_denied = True
                            crew.waiting_for_connection_id = scenario.escape_target_connection_id
                            # The refuge is now full. Seal the air path immediately;
                            # power and water lines remain independent, per the
                            # hatch/utility separation policy.
                            if scenario.escape_target_connection_id:
                                refuge_hatch = scenario.connection(
                                    scenario.escape_target_connection_id
                                )
                                refuge_hatch.path_state = "closed"
                                # A refuge seal is an explicit three-control
                                # procedure: the hatch closes for air, while the
                                # independently switchable power/water lines are
                                # also turned off to stop scarce backup output
                                # leaking back into the compromised staging side.
                                refuge_hatch.power_line_on = False
                                refuge_hatch.water_line_on = False
                        else:
                            crew.waiting_for_connection_id = scenario.escape_target_connection_id
                            crew.hop_eta_seconds = 0.0
                        continue
                    connection = connection_between(
                        scenario, crew.module_id, next_module
                    )
                    if connection is None:
                        crew.waiting_for_connection_id = None
                        continue
                    if not consume_passage(
                        scenario, connection, next_module, equipment=False
                    ):
                        crew.waiting_for_connection_id = connection.id
                        crew.hop_eta_seconds = 0.0
                        continue
                    crew.waiting_for_connection_id = None
                    current_module = scenario.module(crew.module_id)
                    current_module.crew_ids = [
                        c for c in current_module.crew_ids if c != crew.id
                    ]
                    crew.module_id = next_module
                    scenario.module(next_module).crew_ids.append(crew.id)
                    crew.route = crew.route[1:]
                    crew.hop_eta_seconds = config.ASSUMED_CREW_MOVE_SECONDS_PER_HOP
                    if not crew.route:
                        if module_is_hazardous(scenario, crew.module_id):
                            crew.state = "EXPOSED"
                            crew.exposed_at_seconds = t
                        else:
                            crew.state = "EVACUATED"
                else:
                    replan = find_evacuation_route(scenario, crew.module_id)
                    if replan is None:
                        crew.state = "TRAPPED"
                        crew.route = []
                    else:
                        crew.route = replan
                        crew.hop_eta_seconds = config.ASSUMED_CREW_MOVE_SECONDS_PER_HOP

        elif crew.state == "EVACUATED" and hazardous_here:
            crew.state = "EXPOSED"
            crew.exposed_at_seconds = t


# ── A-8: rule-based (assumed) criticality ────────────────────────────────────

def functions_of(crew: Crew) -> set[str]:
    """The functions a crew member provides: their explicit list when declared,
    otherwise the role-based lookup."""
    if crew.provides_functions:
        return set(crew.provides_functions)
    return config.ROLE_FUNCTIONS.get(crew.role, set())


def _available(crew: Crew) -> bool:
    """A trapped crew member cannot currently provide their functions."""
    return crew.state != "TRAPPED"


def crew_weight(
    crew: Crew, alive_crew: list[Crew], damaged_facilities: list[str]
) -> float:
    """How irreplaceable this crew member's functions are RIGHT NOW.

    Not a value of the person's life: weight = f(function criticality,
    redundancy among available crew, facility-driven demand). Built from
    ASSUMED_ tables — see config's provenance notice.
    """
    total = 0.0
    for func in functions_of(crew):
        base = config.ASSUMED_FUNCTION_CRITICALITY.get(
            func, config.ASSUMED_DEFAULT_FUNCTION_CRITICALITY
        )
        providers = sum(
            1 for c in alive_crew if _available(c) and func in functions_of(c)
        )
        redundancy_factor = 1.0 / max(providers, 1)  # single point -> spike
        demand = 1.0
        for facility in damaged_facilities:
            demand *= config.ASSUMED_FACILITY_FUNCTION_DEMAND.get(facility, {}).get(
                func, 1.0
            )
        total += base * redundancy_factor * demand
    return total


def rank_crew_for_evacuation(scenario: Scenario) -> list[Crew]:
    """Rank passage order by urgency and function preservation, not identity."""
    provider_counts: dict[str, int] = {}
    for candidate in scenario.crew:
        if candidate.abandoned:
            continue
        for function in functions_of(candidate):
            provider_counts[function] = provider_counts.get(function, 0) + 1

    for crew in scenario.crew:
        reasons: list[str] = []
        if crew.escape_capacity_denied:
            crew.evacuation_priority_score = 0.0
            crew.priority_reasons = ["refuge_capacity_denied_after_priority_selection"]
            continue
        if crew.abandoned:
            crew.evacuation_priority_score = 0.0
            crew.priority_reasons = ["explicitly_abandoned"]
            continue
        score = crew_weight(crew, scenario.crew, damaged_facilities=[]) * 20.0
        if score:
            reasons.append("mission_function_criticality")
        unique = sum(
            1 for function in functions_of(crew) if provider_counts.get(function) == 1
        )
        if unique:
            score += unique * 12.0
            reasons.append(f"{unique}_unique_function_provider")
        if module_is_hazardous(scenario, crew.module_id):
            score += 35.0
            reasons.append("currently_in_hazard")
        risk = max(0.0, 1.0 - crew.survival_probability)
        if risk:
            score += risk * 25.0
            reasons.append("modeled_survival_risk")
        crew.evacuation_priority_score = round(min(100.0, score), 3)
        crew.priority_reasons = reasons or ["no_immediate_hazard"]

    ranked = sorted(
        (crew for crew in scenario.crew if not crew.abandoned),
        key=lambda crew: (-crew.evacuation_priority_score, crew.id),
    )
    for rank, crew in enumerate(ranked, start=1):
        crew.evacuation_priority_rank = rank
    return ranked


_EQUIPMENT_PRIORITY = {
    "life_support": 38.0,
    "oxygen_supply": 38.0,
    "co2_removal": 36.0,
    "power": 34.0,
    "electrical_power": 34.0,
    "propulsion": 30.0,
    "return_capability": 32.0,
    "gnc": 28.0,
    "navigation": 28.0,
    "medical": 26.0,
    "fire_suppression": 25.0,
    "communications": 22.0,
    "science": 10.0,
}


def update_equipment_evacuation(scenario: Scenario) -> None:
    """Use remaining hatch capacity for portable equipment, by mission impact."""
    portable_items = []
    for equipment in scenario.equipment:
        reasons: list[str] = []
        score = _EQUIPMENT_PRIORITY.get(equipment.system, 15.0)
        if module_is_hazardous(scenario, equipment.module_id):
            score += 25.0
            reasons.append("currently_in_hazard")
        if equipment.damaged:
            score *= 0.25
            reasons.append("already_damaged")
        if not equipment.portable:
            score = 0.0
            reasons.append("fixed_equipment")
        equipment.evacuation_priority_score = round(min(100.0, score), 3)
        equipment.priority_reasons = reasons or ["mission_capability"]
        if equipment.portable:
            portable_items.append(equipment)

    portable_items.sort(key=lambda item: (-item.evacuation_priority_score, item.id))
    for rank, equipment in enumerate(portable_items, start=1):
        equipment.evacuation_priority_rank = rank
    candidates = [
        equipment
        for equipment in portable_items
        if not equipment.evacuated and not equipment.damaged
    ]
    for equipment in candidates:
        if not module_is_hazardous(scenario, equipment.module_id) and not equipment.evacuation_route:
            continue
        if not equipment.evacuation_route:
            route = find_evacuation_route(scenario, equipment.module_id)
            if not route:
                continue
            equipment.evacuation_route = route
        next_module = equipment.evacuation_route[0]
        connection = connection_between(scenario, equipment.module_id, next_module)
        if connection is None or not consume_passage(
            scenario,
            connection,
            next_module,
            passage_units=equipment.passage_units,
            equipment=True,
        ):
            continue
        current = scenario.module(equipment.module_id)
        current.equipment_ids = [item for item in current.equipment_ids if item != equipment.id]
        equipment.module_id = next_module
        scenario.module(next_module).equipment_ids.append(equipment.id)
        equipment.evacuation_route = equipment.evacuation_route[1:]
        equipment.evacuated = not equipment.evacuation_route and not module_is_hazardous(
            scenario, equipment.module_id
        )


def critical_functions(
    alive_crew: list[Crew], damaged_facilities: list[str]
) -> list[dict]:
    """Flag every function whose available-provider count is 0 or 1.

    This factual output ("life_support_ops has a single provider: C2") is what
    the engine hands to downstream agents — not a ranking of people.
    """
    all_functions = {
        func for role_funcs in config.ROLE_FUNCTIONS.values() for func in role_funcs
    }
    for crew in alive_crew:
        all_functions |= functions_of(crew)
    findings = []
    for func in sorted(all_functions):
        providers = [
            c.id for c in alive_crew if _available(c) and func in functions_of(c)
        ]
        if len(providers) == 1:
            findings.append(
                {"function": func, "flag": "SINGLE_PROVIDER", "providers": providers}
            )
        elif len(providers) == 0 and func in {
            f
            for fac in damaged_facilities
            for f in config.ASSUMED_FACILITY_FUNCTION_DEMAND.get(fac, {})
        }:
            findings.append({"function": func, "flag": "NO_PROVIDER", "providers": []})
    return findings


# ── A-8.5: measured (leave-one-out) criticality ──────────────────────────────

def measured_criticality(
    scenario: Scenario,
    action,
    horizon: float | None = None,
    dt: float | None = None,
) -> list[dict]:
    """Measure each crew member's criticality instead of assuming it.

    Removes one crew member at a time, re-runs the simulation, and reports how
    much the outcome degrades. Needs no external data and cross-checks the
    ASSUMED_ tables: `crew_weight` is theoretical criticality, this is what the
    simulator actually measures.

    Score = (capabilities retained with the member) - (retained without them),
    so a positive score means the crew member's presence protects capability.
    """
    from spacecraft_sim.engine import counterfactual  # local: avoids a cycle

    def capability_score(sc: Scenario) -> float:
        result = counterfactual(sc, action, horizon=horizon, dt=dt)
        return float(result.summary["expected_returnees"])

    baseline = capability_score(scenario)

    findings = []
    for crew in scenario.crew:
        reduced = scenario.model_copy(deep=True)
        reduced.crew = [c for c in reduced.crew if c.id != crew.id]
        for module in reduced.modules:
            module.crew_ids = [cid for cid in module.crew_ids if cid != crew.id]
        findings.append(
            {
                "crew_id": crew.id,
                "role": crew.role,
                "measured_score": round(baseline - capability_score(reduced), 4),
                "assumed_weight": round(
                    crew_weight(crew, scenario.crew, damaged_facilities=[]), 4
                ),
            }
        )

    findings.sort(key=lambda f: f["measured_score"], reverse=True)
    return findings
