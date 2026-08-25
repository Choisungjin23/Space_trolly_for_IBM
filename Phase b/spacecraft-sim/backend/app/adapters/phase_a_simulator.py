"""PhaseASimulatorAdapter — the real Phase A engine behind the Phase B API.

Replaces MockSimulatorAdapter with the `spacecraft_sim` package (real-unit,
NASA-calibrated PoC engine): species mass-balance hazard transport, computed
smoke detection, crew state machine with SMAC doses, equipment damage/repair,
and Monte Carlo over uncertain scenario assumptions.

Same public interface as the mock: generate_actions() + simulate().

Locating Phase A: `import spacecraft_sim` is tried first (pip install -e).
If that fails, the path in the SPACECRAFT_SIM_SRC environment variable is
used, then the default sibling checkout `<...>/Claude/spacecraft-sim/src`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# ── Phase A import bootstrap ────────────────────────────────────────────────

_DEFAULT_PHASE_A_SRC = Path(__file__).resolve().parents[5] / "spacecraft-sim" / "src"

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
)
from spacecraft_sim.montecarlo import run_montecarlo

from app.api.schemas import (
    ActionOperationOut,
    ActionSimulationResult,
    ActionSpecOut,
    CapabilityOutcomeSummary,
    CriticalFunctionEntry,
    CriticalFunctionSummary,
    CrewMemberOutcome,
    CrewOutcomeSummary,
    EmergencyConfigIn,
    EquipmentItemOutcome,
    EquipmentOutcomeSummary,
    ExampleTrajectory,
    HazardOutcome,
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

_AIRFLOW_MAP = {
    "source_to_target": "source_to_target",
    "target_to_source": "target_to_source",
    "bidirectional": "none",  # Phase A: no single direction = both ways
    "none": "none",
    "unknown": "none",
}


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
                    else 0.21,
                ),
                crew_ids=[c.id for c in module_in.crew],
                equipment_ids=[e.id for e in module_in.equipment],
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
            )
        )

    pa_scenario = PAScenario(
        modules=modules,
        connections=connections,
        crew=crew,
        equipment=equipment,
        systems=[],  # Phase B computes capabilities from equipment directly
        capabilities={},
        mission_phase=scenario.missionPhase or "cruise",
    )

    fire_module = pa_scenario.module(emergency.affectedModuleId)
    fire_module.fire_state = "sustained"
    profile = emergency.sourceProfileId
    fire_module.source_profile_id = (
        profile if profile in pa_config.SOURCE_PROFILES else None
    )
    # detected=True means the alarm has already sounded at t=0; otherwise the
    # engine computes detection from smoke reaching the detector threshold.
    fire_module.detected = bool(emergency.detected)

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


def _capability_summary(equipment_states: dict[str, str], scenario: ScenarioIn) -> dict:
    """Phase B semantics: a capability is available while ANY provider is
    operational (redundancy), degraded when the best provider is exposed."""
    by_capability: dict[str, list[str]] = {}
    for module_in in scenario.modules.values():
        for eq_in in module_in.equipment:
            for capability in eq_in.providesCapabilities:
                by_capability.setdefault(capability, []).append(
                    equipment_states[eq_in.id]
                )
    summary: dict[str, str] = {}
    for capability, states in by_capability.items():
        if any(s == "operational" for s in states):
            summary[capability] = "available"
        elif any(s == "exposed_at_risk" for s in states):
            summary[capability] = "degraded"
        else:
            summary[capability] = "unavailable"
    return summary


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
            events.append(f"Fire burning in {fire_names or 'spacecraft'}")
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
) -> SimulationResponse:
    pairs = _action_pairs(scenario, emergency)

    if action_ids is not None:
        available = {spec.id for spec, _, _ in pairs}
        unknown = [a for a in action_ids if a not in available]
        if unknown:
            raise ValueError(f"Unknown action id(s): {', '.join(unknown)}")
        pairs = [p for p in pairs if p[0].id in action_ids]

    results: list[ActionSimulationResult] = []

    for spec, pa_action, pa_scenario in pairs:
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
                            name=equipment_names[eq_id], state=state
                        )
                        for eq_id, state in equipment_states.items()
                    }
                ),
                capabilities=CapabilityOutcomeSummary(
                    byCapability=_capability_summary(equipment_states, scenario)
                ),
                criticalFunctions=CriticalFunctionSummary(
                    byFunction=_critical_functions(final)
                ),
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
    )
