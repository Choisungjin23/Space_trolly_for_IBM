"""PhaseASimulatorAdapter — the real Phase A engine behind the Phase B API.

Wraps the `spacecraft_sim` package (real-unit, NASA-calibrated PoC engine):
species mass-balance hazard transport, computed smoke detection, crew state
machine with SMAC doses, equipment damage/repair, and Monte Carlo over
uncertain scenario assumptions.

Public interface: generate_actions() + simulate().

Locating Phase A: `import spacecraft_sim` is tried first (pip install -e).
If that fails, the path in the SPACECRAFT_SIM_SRC environment variable is
used, then the default sibling checkout `<repo>/phase-a/src`.
"""

from __future__ import annotations

import os
import sys
import hashlib
from pathlib import Path
from typing import Optional

# ── Phase A import bootstrap ────────────────────────────────────────────────

_DEFAULT_PHASE_A_SRC = Path(__file__).resolve().parents[5] / "phase-a" / "src"

try:
    import spacecraft_sim  # noqa: F401
except ImportError:  # pragma: no cover - depends on environment
    _candidate = Path(os.environ.get("SPACECRAFT_SIM_SRC", _DEFAULT_PHASE_A_SRC))
    if (_candidate / "spacecraft_sim").is_dir():
        sys.path.insert(0, str(_candidate))
    import spacecraft_sim  # noqa: F401

from spacecraft_sim import config as pa_config
from spacecraft_sim.actions import Action, generate_actions as pa_generate_actions
from spacecraft_sim.crew import functions_of
from spacecraft_sim.engine import TimelineResult, counterfactual
from spacecraft_sim.models import (
    Atmosphere,
    Connection as PAConnection,
    Crew as PACrew,
    Equipment as PAEquipment,
    Module as PAModule,
    Scenario as PAScenario,
    System as PASystem,
)
from spacecraft_sim.montecarlo import run_montecarlo

from app.api.schemas import (
    ActionOperationOut,
    ActionSimulationResult,
    ActionSpecOut,
    CapabilityOutcomeSummary,
    CriticalFunctionEntry,
    CriticalFunctionSummary,
    ConnectionConnectivityOutcome,
    ConnectivityOutcomeSummary,
    ModuleResourceOutcome,
    ResourceOutcomeSummary,
    CrewMemberOutcome,
    CrewOutcomeSummary,
    EmergencyConfigIn,
    EquipmentItemOutcome,
    EquipmentOutcomeSummary,
    ExampleTrajectory,
    HazardOutcome,
    ReturnCapabilityOutcome,
    ScenarioIn,
    SimulationResponse,
    TrajectoryStep,
    UncertaintySummary,
)

SOURCE_LABEL = (
    "PhaseASimulatorAdapter — spacecraft_sim real-unit engine "
    "(NASA-calibrated PoC; VERIFIED_/ASSUMED_ provenance in its config)"
)

HORIZON_SECONDS = pa_config.HORIZON_SECONDS
DT_SECONDS = pa_config.DT_SECONDS
TRAJECTORY_MAX_STEPS = 8

# Phase B transfer classes scale the connection-type default flow.
_TRANSFER_FACTORS = {"none": 0.0, "low": 0.33, "medium": 0.66, "high": 1.0}

# ── Systems and capabilities ────────────────────────────────────────────────
#
# Phase B's `providesCapabilities` tags are systems, not capabilities: they name
# what a box does (`main_propulsion`), while a Phase A capability names what the
# mission can still do (`RETURN`). So each tag becomes one Phase A System over
# the equipment carrying it, and the mission capabilities below compose those
# systems.
#
# Tags are redundant by nature — three life-support units all provide
# `habitation` — so their systems are declared `redundancy="any"`, which is the
# semantics the Phase B UI has always shown.

# Capabilities that belong to a module rather than to a box inside it. Phase B
# strips these from equipment (EquipmentIn.remove_source_capabilities), so they
# are rebuilt here from the module's own source configuration.
_SOURCE_SYSTEMS = {
    "oxygen_supply": lambda m: m.type == "life_support" and m.supplies_air,
    "electrical_power": lambda m: m.type == "power" and m.max_power_output_w > 0,
}

# ASSUMED: which systems a mission capability needs. Conjunctive — coming home
# needs propulsion AND navigation AND power, not any one of them. Only systems
# the scenario actually declares are included, and a capability with no
# surviving members is not declared at all.
ASSUMED_MISSION_CAPABILITIES: dict[str, set[str]] = {
    "RETURN": {
        "return_capability",
        "main_propulsion",
        "navigation",
        "electrical_power",
    },
    "HABITATION": {
        "habitation",
        "co2_removal",
        "oxygen_supply",
        "electrical_power",
    },
}

# ASSUMED: the crew function a system needs someone available to perform.
#
# The split is between systems that run themselves and systems that need a
# person acting. Life support, power and thermal control are automated: an
# oxygen generator does not stop because nobody is standing next to it, so
# leaving them uncoupled keeps a habitable spacecraft habitable while the crew
# are cut off. Manoeuvring, navigation, returning and fire response are things
# a crew member does, so losing every provider of that function takes them
# down even though the hardware is intact — which is the point of Phase A's
# crew coupling.
#
# Applied only when the scenario actually has a crew member providing it — see
# `_operator_for`. Without that guard a scenario whose crew happens not to
# declare `gnc_ops` would lose attitude control at t=0, which is a modelling
# artifact rather than an emergency.
ASSUMED_SYSTEM_OPERATOR_FUNCTION: dict[str, str] = {
    "main_propulsion": "propulsion_ops",
    "propulsion_reserve": "propulsion_ops",
    "rcs": "gnc_ops",
    "rcs_reserve": "gnc_ops",
    "attitude_control": "gnc_ops",
    "navigation": "navigation",
    "return_capability": "return_ops",
    "docking": "docking",
    "fire_suppression": "fire_response",
    # Automated, and so deliberately absent: habitation, co2_removal,
    # emergency_life_support, thermal_control, oxygen_supply,
    # electrical_power, communications.
}

_PA_TO_PHASE_B_CAPABILITY_STATE = {
    "AVAILABLE": "available",
    "AT_RISK": "degraded",
    "UNAVAILABLE": "unavailable",
}

_AIRFLOW_MAP = {
    "source_to_target": "source_to_target",
    "target_to_source": "target_to_source",
    "bidirectional": "none",  # Phase A: no single direction = both ways
    "none": "none",
    "unknown": "none",
}


def _operator_for(tag: str, declared_functions: set[str]) -> Optional[str]:
    """The operator function for a system, but only when someone can perform it.

    A system whose operator function nobody in the crew provides would be
    UNAVAILABLE from the first step. That says more about how the scenario was
    filled in than about the emergency, so the coupling is applied only where
    the crew actually declares the function.
    """
    function = ASSUMED_SYSTEM_OPERATOR_FUNCTION.get(tag)
    return function if function in declared_functions else None


def _build_systems_and_capabilities(
    scenario: ScenarioIn, modules: list[PAModule], crew: list[PACrew]
) -> tuple[list[PASystem], dict[str, list[str]]]:
    """Turn Phase B's equipment tags and source modules into Phase A systems,
    then compose the mission capabilities that read from them."""
    providers: dict[str, list[str]] = {}
    for module_in in scenario.modules.values():
        for equipment_in in module_in.equipment:
            for tag in equipment_in.providesCapabilities:
                providers.setdefault(tag, []).append(equipment_in.id)

    source_modules: dict[str, list[str]] = {}
    for module in modules:
        for tag, applies in _SOURCE_SYSTEMS.items():
            if applies(module):
                source_modules.setdefault(tag, []).append(module.id)

    declared_functions = {f for member in crew for f in functions_of(member)}

    systems: list[PASystem] = []
    for tag in sorted(providers):
        systems.append(
            PASystem(
                id=tag,
                name=tag,
                depends_on_equipment=providers[tag],
                redundancy="any",
                operator_function=_operator_for(tag, declared_functions),
            )
        )
    for tag in sorted(source_modules):
        systems.append(
            PASystem(
                id=tag,
                name=tag,
                depends_on_modules=source_modules[tag],
                redundancy="any",
                operator_function=_operator_for(tag, declared_functions),
            )
        )

    declared = {system.id for system in systems}
    # Every system is also a capability in its own right, which is what the
    # results table has always displayed.
    capabilities: dict[str, list[str]] = {sid: [sid] for sid in sorted(declared)}
    # Mission capabilities sit on top, composed conjunctively.
    for capability, members in ASSUMED_MISSION_CAPABILITIES.items():
        present = sorted(members & declared)
        if present:
            capabilities[capability] = present
    return systems, capabilities


# ── Scenario translation ────────────────────────────────────────────────────

def to_phase_a_scenario(
    scenario: ScenarioIn, emergency: EmergencyConfigIn
) -> PAScenario:
    modules: list[PAModule] = []
    crew: list[PACrew] = []
    equipment: list[PAEquipment] = []

    for module_in in scenario.modules.values():
        modules.append(
            PAModule(
                id=module_in.id,
                name=module_in.name,
                type=module_in.type if module_in.type != "other" else "generic",
                atmosphere=Atmosphere(
                    pressure=module_in.pressure if module_in.pressure is not None else 101.3,
                    o2=module_in.oxygenFraction
                    if module_in.oxygenFraction is not None
                    else 0.25,
                ),
                crew_ids=[c.id for c in module_in.crew],
                equipment_ids=[e.id for e in module_in.equipment],
                power_level_w=module_in.powerLevelW,
                power_consumption_w=module_in.powerConsumptionW,
                base_power_consumption_w=module_in.powerConsumptionW,
                max_power_output_w=(
                    module_in.maxPowerOutputW if module_in.type == "power" else 0.0
                ),
                water_stored_kg=module_in.waterStoredKg,
                water_capacity_kg=max(
                    module_in.waterCapacityKg, module_in.waterStoredKg
                ),
                supplies_air=(
                    module_in.type == "life_support" and module_in.suppliesAir
                ),
                supplies_water=(
                    module_in.type == "life_support" and module_in.suppliesWater
                ),
                max_air_output_fraction_per_min=(
                    module_in.maxAirOutputPercentPerMin / 100.0
                ),
                max_water_output_kg_per_min=module_in.maxWaterOutputKgPerMin,
                water_recovery_efficiency=module_in.waterRecoveryEfficiency,
                disruption_level=module_in.disruptionLevel,
            )
        )
        for crew_in in module_in.crew:
            crew.append(
                PACrew(
                    id=crew_in.id,
                    name=crew_in.name,
                    role=crew_in.role.lower(),
                    provides_functions=list(crew_in.providesFunctions),
                    module_id=module_in.id,
                )
            )
        for eq_in in module_in.equipment:
            equipment.append(
                PAEquipment(
                    id=eq_in.id,
                    name=eq_in.name,
                    module_id=module_in.id,
                    # Phase A wants a system link; the first declared capability
                    # (or the equipment type) stands in for it.
                    system=(
                        eq_in.providesCapabilities[0]
                        if eq_in.providesCapabilities
                        else eq_in.type
                    ),
                    powered=eq_in.state != "unavailable",
                    damaged=eq_in.state == "explicitly_failed",
                    power_consumption_w=eq_in.powerConsumptionW,
                    portable=eq_in.portable,
                    passage_units=eq_in.passageUnits,
                )
            )

    connections: list[PAConnection] = []
    for conn_in in scenario.connections.values():
        conn_type = conn_in.type if conn_in.type in ("hatch", "imv", "leak") else "hatch"
        factor = _TRANSFER_FACTORS.get(conn_in.transferClass)  # None for "unknown"
        if factor is None:
            flow = None  # engine default + Monte Carlo uncertainty
        else:
            default = PAConnection(
                id="_", source="_a", target="_b", type=conn_type
            ).nominal_flow_m3_s()
            flow = default * factor
        adjacent_emergency = conn_in.type == "hatch" and emergency.affectedModuleId in {
            conn_in.source, conn_in.target
        }
        digest = hashlib.sha256(
            f"{scenario.id or scenario.name}:{emergency.type}:{conn_in.id}".encode()
        ).digest()
        rolled_connectivity = 1 + digest[0] % 50
        current_connectivity = (
            rolled_connectivity
            if adjacent_emergency and conn_in.connectivity > 50
            else conn_in.connectivity
        )
        rolled_power_factor = (5 + digest[1] % 16) / 100.0
        power_transfer_factor = (
            rolled_power_factor
            if adjacent_emergency
            and emergency.type == "electronic_short"
            and conn_in.powerTransferFactor >= 1
            else conn_in.powerTransferFactor
        )
        connections.append(
            PAConnection(
                id=conn_in.id,
                source=conn_in.source,
                target=conn_in.target,
                type=conn_type,
                path_state=conn_in.state,
                ventilation_state="on" if conn_in.ventilationOn else "off",
                airflow_direction=_AIRFLOW_MAP.get(conn_in.flowDirection, "none"),
                flow_m3_s=flow,
                power_line_on=conn_in.powerLineOn,
                air_line_on=conn_in.airLineOn,
                water_line_on=conn_in.waterLineOn,
                base_connectivity=conn_in.baseConnectivity,
                connectivity=current_connectivity,
                power_transfer_factor=power_transfer_factor,
            )
        )

    systems, capabilities = _build_systems_and_capabilities(scenario, modules, crew)

    pa_scenario = PAScenario(
        modules=modules,
        connections=connections,
        crew=crew,
        equipment=equipment,
        systems=systems,
        capabilities=capabilities,
        mission_phase=scenario.missionPhase or "cruise",
        escape_target_connection_id=(
            emergency.escapeTarget.connectionId if emergency.escapeTarget else None
        ),
        escape_from_module_id=(
            emergency.escapeTarget.fromModuleId if emergency.escapeTarget else None
        ),
        escape_target_module_id=(
            emergency.escapeTarget.toModuleId if emergency.escapeTarget else None
        ),
        escape_capacity_people=(
            emergency.escapeTarget.maxOccupants if emergency.escapeTarget else None
        ),
    )

    emergency_module = pa_scenario.module(emergency.affectedModuleId)
    if emergency.type == "fire":
        emergency_module.fire_state = "sustained"
        profile = emergency.sourceProfileId
        emergency_module.source_profile_id = (
            profile if profile in pa_config.SOURCE_PROFILES else None
        )
    else:
        emergency_module.electrical_short = True
        emergency_module.disruption_level = max(emergency_module.disruption_level, 0.7)
    # detected=True means the alarm has already sounded at t=0; otherwise the
    # engine computes detection from smoke reaching the detector threshold.
    emergency_module.detected = bool(emergency.detected)

    return pa_scenario


# ── Action translation ──────────────────────────────────────────────────────

def _to_phase_b_action(action: Action, pa_scenario: PAScenario) -> ActionSpecOut:
    """Map a Phase A action onto the Phase B id and operation vocabulary."""
    if action.kind == "do_nothing":
        return ActionSpecOut(
            id="do_nothing",
            label="Do Nothing",
            description=action.description,
            operations=[ActionOperationOut(type="do_nothing", targetId="")],
        )
    if action.kind in ("close_hatch", "close_imv"):
        conn_id = action.params["connection_id"]
        return ActionSpecOut(
            id=f"close_conn_{conn_id}",
            label=action.label,
            description=action.description,
            operations=[ActionOperationOut(type="close_connection", targetId=conn_id)],
        )
    if action.kind == "shutdown_ventilation":
        conn_id = action.params["connection_id"]
        return ActionSpecOut(
            id=f"shutdown_vent_{conn_id}",
            label=action.label,
            description=action.description,
            operations=[
                ActionOperationOut(type="shutdown_ventilation", targetId=conn_id)
            ],
        )
    if action.kind == "isolate":
        module_id = action.params["module_id"]
        return ActionSpecOut(
            id=f"isolate_module_{module_id}",
            label=action.label,
            description=action.description,
            operations=[ActionOperationOut(type="isolate_module", targetId=module_id)],
        )
    if action.kind == "shutdown_utility":
        conn_id = action.params["connection_id"]
        resource = action.params["resource"]
        return ActionSpecOut(
            id=f"shutdown_{resource}_line_{conn_id}",
            label=action.label,
            description=action.description,
            operations=[
                ActionOperationOut(
                    type=f"shutdown_{resource}_line", targetId=conn_id
                )
            ],
        )
    if action.kind == "abandon":
        module_id = action.params["module_id"]
        return ActionSpecOut(
            id=f"abandon_module_{module_id}",
            label=action.label,
            description=action.description,
            operations=[ActionOperationOut(type="abandon_module", targetId=module_id)],
        )
    if action.kind == "power_down":
        module_id = action.params["module_id"]
        return ActionSpecOut(
            id=f"power_down_{module_id}",
            label=action.label,
            description=action.description,
            operations=[
                ActionOperationOut(type="power_down_equipment", targetId=module_id)
            ],
        )
    if action.kind == "evacuate":
        crew_id = action.params["crew_id"]
        return ActionSpecOut(
            id=f"evacuate_{crew_id}_to_{action.params['target_module']}",
            label=action.label,
            description=action.description,
            operations=[ActionOperationOut(type="evacuate_crew", targetId=crew_id)],
        )
    if action.kind == "station_repairer":
        crew_id = action.params["crew_id"]
        return ActionSpecOut(
            id=f"station_{crew_id}_in_{action.params['target_module']}",
            label=action.label,
            description=action.description,
            operations=[ActionOperationOut(type="evacuate_crew", targetId=crew_id)],
        )
    raise ValueError(f"Unmapped Phase A action kind: {action.kind}")


def _action_pairs(
    scenario: ScenarioIn, emergency: EmergencyConfigIn
) -> list[tuple[ActionSpecOut, Action, PAScenario]]:
    pa_scenario = to_phase_a_scenario(scenario, emergency)
    return [
        (_to_phase_b_action(a, pa_scenario), a, pa_scenario)
        for a in pa_generate_actions(pa_scenario)
    ]


def generate_actions(
    scenario: ScenarioIn, emergency: EmergencyConfigIn
) -> list[ActionSpecOut]:
    return [spec for spec, _, _ in _action_pairs(scenario, emergency)]


def to_phase_a_action_id(
    scenario: ScenarioIn, emergency: EmergencyConfigIn, action_id: str
) -> str:
    """Translate a Phase B action id into the Phase A id it was built from.

    The two layers name the same action differently - `power_down_mod-storage`
    here, `power_down:mod-storage` in the engine - and Phase C speaks the
    engine's vocabulary. `_action_pairs` already holds both names for the same
    action, so the translation is a lookup rather than string surgery.

    A Phase A id passes through unchanged, so callers on either side of the
    boundary can hand their own id over without knowing which it is.
    """
    pairs = _action_pairs(scenario, emergency)
    for spec, pa_action, _ in pairs:
        if action_id in (spec.id, pa_action.id):
            return pa_action.id
    known = ", ".join(sorted(spec.id for spec, _, _ in pairs))
    raise ValueError(
        f"Unknown action id '{action_id}' for this scenario. Available: {known}"
    )


# ── Result translation ──────────────────────────────────────────────────────

_STATE_TO_STATUS = {
    "SAFE": "safe",
    "EXPOSED": "exposed",
    "EVACUATING": "evacuating",
    "EVACUATED": "evacuated",
    "TRAPPED": "trapped",
}

_AVAILABLE_STATUSES = ("safe", "evacuating", "evacuated")


def _equipment_state(
    equipment: PAEquipment, final: PAScenario, hazard_reached: set[str]
) -> str:
    if equipment.damaged:
        return "explicitly_failed"
    if not equipment.powered:
        return "unavailable"
    module = final.module(equipment.module_id)
    if module.isolated:
        return "unavailable"
    if module.id in hazard_reached or module.fire_state in ("incipient", "sustained"):
        return "exposed_at_risk"
    return "operational"


def _return_capability(summary: dict) -> Optional[ReturnCapabilityOutcome]:
    """Carry the engine's account of how the return verdict was reached."""
    block = summary.get("return_capability")
    if not block:
        return None
    return ReturnCapabilityOutcome(
        name=block["name"],
        declared=block["declared"],
        finalState=block.get("final_state"),
        availableAtEnd=block["available_at_end"],
        downtimeSeconds=block["downtime_seconds"],
        firstLostAtSeconds=block.get("first_lost_at_seconds"),
        restoredAtSeconds=block.get("restored_at_seconds"),
    )


def _response_warnings(results: list[ActionSimulationResult]) -> list[str]:
    """Say when a number means "not asked" rather than "answered well"."""
    warnings: list[str] = []
    undeclared = next(
        (r.returnCapability for r in results if r.returnCapability and not r.returnCapability.declared),
        None,
    )
    if undeclared is not None:
        warnings.append(
            f"No {undeclared.name} capability is declared by this scenario, so "
            f"the ability to come home was never judged: expectedReturnees "
            f"equals expectedSurvivors for every action by construction, not "
            f"because return was assured. Tag the equipment that provides it "
            f"(for example return_capability, main_propulsion or navigation)."
        )
    return warnings


def _capability_summary(capabilities: dict[str, str]) -> dict:
    """Render the engine's capability verdict in the product's vocabulary.

    The engine is the single source of truth here: the redundancy that used to
    be computed separately in this file now lives in the Phase A systems built
    by `_build_systems_and_capabilities`, so the UI and the advisor read the
    same judgement instead of two implementations that can disagree.
    """
    return {
        capability: _PA_TO_PHASE_B_CAPABILITY_STATE.get(state, "unavailable")
        for capability, state in capabilities.items()
    }


def _critical_functions(final: PAScenario) -> dict[str, CriticalFunctionEntry]:
    by_function: dict[str, list[str]] = {}
    for crew in final.crew:
        status = _STATE_TO_STATUS[crew.state]
        for function in functions_of(crew):
            by_function.setdefault(function, []).append(status)

    summary: dict[str, CriticalFunctionEntry] = {}
    for function, statuses in by_function.items():
        available = sum(1 for s in statuses if s in _AVAILABLE_STATUSES)
        if available == 0:
            status = "no_provider"
        elif available == 1:
            status = "single_provider"
        else:
            status = "nominal"
        summary[function] = CriticalFunctionEntry(
            providersAvailable=available,
            totalProviders=len(statuses),
            status=status,
        )
    return summary


def _build_trajectory(
    result: TimelineResult, pa_scenario: PAScenario, action_label: str, seed: int
) -> ExampleTrajectory:
    timeline = result.timeline
    if not timeline:
        return ExampleTrajectory(seed=seed, steps=[])

    stride = max(1, len(timeline) // (TRAJECTORY_MAX_STEPS - 1))
    indices = list(range(0, len(timeline), stride))
    if indices[-1] != len(timeline) - 1:
        indices.append(len(timeline) - 1)

    detected_at = result.summary.get("detected_at_seconds")
    egress = pa_config.ASSUMED_EGRESS_IMPAIR_EXTINCTION_PER_M

    steps: list[TrajectoryStep] = []
    previous_crew: dict[str, str] = {c.id: c.state for c in pa_scenario.crew}
    detection_reported = False
    action_reported = False

    for step_index, timeline_index in enumerate(indices):
        entry = timeline[timeline_index]
        t = entry["t"]

        module_states = {}
        crew_here = entry.get("crew_modules", {})
        for module in pa_scenario.modules:
            extinction = entry["extinction"].get(module.id, 0.0)
            module_states[module.id] = {
                "hazardSeverity": round(min(1.0, extinction / egress), 3),
                "crewPresent": sum(1 for m in crew_here.values() if m == module.id),
            }

        events: list[str] = []
        if step_index == 0:
            fire_names = ", ".join(m.name for m in pa_scenario.fire_modules())
            short_names = ", ".join(m.name for m in pa_scenario.modules if m.electrical_short)
            if fire_names:
                events.append(f"Fire burning in {fire_names}")
            elif short_names:
                events.append(f"Electronic short active in {short_names}")
            else:
                events.append("Emergency active in spacecraft")
        if not detection_reported and detected_at is not None and t >= detected_at:
            events.append(f"Smoke alarm confirmed at t={detected_at:.0f}s")
            detection_reported = True
            if not action_reported and action_label != "Do Nothing":
                events.append(f"Action applied: {action_label}")
                action_reported = True
        for crew_id, state in entry["crew"].items():
            if state != previous_crew.get(crew_id) and state in (
                "EVACUATING",
                "EVACUATED",
                "TRAPPED",
            ):
                events.append(f"{crew_id} {state.lower()}")
            previous_crew[crew_id] = state

        steps.append(
            TrajectoryStep(
                stepIndex=step_index,
                timeSeconds=int(t),
                moduleStates=module_states,
                events=events,
            )
        )

    return ExampleTrajectory(seed=seed, steps=steps)


# ── Entry point ─────────────────────────────────────────────────────────────

def simulate(
    scenario: ScenarioIn,
    emergency: EmergencyConfigIn,
    action_ids: Optional[list[str]],
    runs: int,
    seed: Optional[int],
    on_progress=None,
) -> SimulationResponse:
    pairs = _action_pairs(scenario, emergency)

    if action_ids is not None:
        available = {spec.id for spec, _, _ in pairs}
        unknown = [a for a in action_ids if a not in available]
        if unknown:
            raise ValueError(f"Unknown action id(s): {', '.join(unknown)}")
        pairs = [p for p in pairs if p[0].id in action_ids]

    results: list[ActionSimulationResult] = []
    total = len(pairs)

    for index, (spec, pa_action, pa_scenario) in enumerate(pairs):
        # Each action is a deterministic run plus `runs` Monte Carlo samples,
        # so per-action is the finest granularity that costs nothing to report.
        if on_progress is not None:
            on_progress(
                stage=spec.id, label=spec.label, done=index, total=total
            )
        deterministic = counterfactual(
            pa_scenario, pa_action, horizon=HORIZON_SECONDS, dt=DT_SECONDS
        )
        summary = deterministic.summary
        final = deterministic.final

        distribution = run_montecarlo(
            pa_scenario,
            pa_action,
            n=runs,
            seed=seed,
            horizon=HORIZON_SECONDS,
            dt=DT_SECONDS,
        )

        hazard_reached = set(summary["hazard_reached"])
        equipment_states = {
            e.id: _equipment_state(e, final, hazard_reached) for e in final.equipment
        }
        equipment_names = {e.id: e.name for e in final.equipment}

        crew_outcomes = {
            crew_id: CrewMemberOutcome(
                status=_STATE_TO_STATUS[info["state"]],
                exposureExampleSeconds=int(info["exposure_seconds"]),
                survivalProbability=info["survival_probability"],
                returnProbability=info["return_probability"],
                abandoned=info["abandoned"],
                priorityScore=info.get("priority_score", 0.0),
                priorityRank=info.get("priority_rank"),
                priorityReasons=info.get("priority_reasons", []),
                waitingForConnectionId=info.get("waiting_for_connection_id"),
                escapeCapacityDenied=info.get("escape_capacity_denied", False),
                estimatedSurvivalMinutes=info.get("estimated_survival_minutes"),
                resourceRiskReasons=info.get("resource_risk_reasons", []),
            )
            for crew_id, info in summary["crew"].items()
        }

        results.append(
            ActionSimulationResult(
                actionId=spec.id,
                hazard=HazardOutcome(
                    modulesReached=len(hazard_reached),
                    modulesReachedIds=sorted(hazard_reached),
                    containedInNScenarios=distribution.hazard_contained_to_sources,
                    totalScenarios=runs,
                ),
                crew=CrewOutcomeSummary(
                    allEvacuatedCount=distribution.all_crew_safe_or_evacuated,
                    anyTrappedCount=runs - distribution.no_crew_trapped,
                    totalScenarios=runs,
                    byCrewMember=crew_outcomes or None,
                ),
                equipment=EquipmentOutcomeSummary(
                    byEquipmentId={
                        eq_id: EquipmentItemOutcome(
                            name=equipment_names[eq_id],
                            state=state,
                            portable=next(e.portable for e in final.equipment if e.id == eq_id),
                            priorityScore=next(e.evacuation_priority_score for e in final.equipment if e.id == eq_id),
                            priorityRank=next(e.evacuation_priority_rank for e in final.equipment if e.id == eq_id),
                            priorityReasons=next(e.priority_reasons for e in final.equipment if e.id == eq_id),
                            evacuated=next(e.evacuated for e in final.equipment if e.id == eq_id),
                        )
                        for eq_id, state in equipment_states.items()
                    }
                ),
                capabilities=CapabilityOutcomeSummary(
                    byCapability=_capability_summary(summary["capabilities"])
                ),
                returnCapability=_return_capability(summary),
                criticalFunctions=CriticalFunctionSummary(
                    byFunction=_critical_functions(final)
                ),
                resources=ResourceOutcomeSummary(
                    byModuleId={
                        module_id: ModuleResourceOutcome(
                            powerLevelW=values["power_level_w"],
                            powerDemandW=values["power_consumption_w"],
                            powerSufficient=values["power_sufficient"],
                            airLevelPercent=values["air_level_fraction"] * 100,
                            waterStoredKg=values["water_stored_kg"],
                            waterDemandKgPerMin=values["water_demand_kg_per_min"],
                            waterSufficient=values["water_sufficient"],
                        )
                        for module_id, values in summary["resources"].items()
                    }
                ),
                connectivity=ConnectivityOutcomeSummary(
                    byConnectionId={
                        connection_id: ConnectionConnectivityOutcome(
                            connectivity=values["connectivity"],
                            baseConnectivity=values["base_connectivity"],
                            crewThroughputPerMin=values["crew_throughput_per_min"],
                            airThroughputPercentPerMin=values["air_throughput_percent_per_min"],
                            crewPassages=values["crew_passages"],
                            equipmentPassageUnits=values["equipment_passage_units"],
                            powerTransferPercent=values.get("power_transfer_percent", 100.0),
                        )
                        for connection_id, values in summary["connectivity"].items()
                    }
                ),
                expectedSurvivors=summary["expected_survivors"],
                expectedReturnees=summary["expected_returnees"],
                uncertaintySummary=UncertaintySummary(
                    note=(
                        "Phase A engine: counts over sampled scenario assumptions "
                        "(decision delay, crew response, unknown paths, flow "
                        "uncertainty); not validated real-world probabilities. "
                        f"{pa_config.ETHICS_NOTICE}"
                    )
                ),
                exampleTrajectory=_build_trajectory(
                    deterministic,
                    pa_scenario,
                    spec.label,
                    seed if seed is not None else 0,
                ),
            )
        )

    return SimulationResponse(
        generatedActions=[spec for spec, _, _ in pairs],
        results=results,
        simulatedHorizonSeconds=int(HORIZON_SECONDS),
        runsRequested=runs,
        seed=seed,
        sourceLabel=SOURCE_LABEL,
        warnings=_response_warnings(results),
    )
