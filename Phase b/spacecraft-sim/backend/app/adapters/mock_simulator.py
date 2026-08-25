"""
MockSimulatorAdapter — Phase B integration fixture.

THIS IS NOT PHASE A SIMULATION PHYSICS.
It is a structured placeholder that returns plausible-shaped results so the
Phase B UI can be fully exercised before Phase A ships.

When Phase A ships, replace this file with PhaseASimulatorAdapter that
implements the same generate_actions() + simulate() interface.

No propagation formulas, no PROPAGATION_FACTOR, no Monte Carlo physics,
no crew lethality thresholds. Only demo-appropriate structured output.
"""

from __future__ import annotations

import hashlib
import random
from typing import Optional

from app.api.schemas import (
    ActionOperationOut,
    ActionSimulationResult,
    ActionSpecOut,
    CapabilityOutcomeSummary,
    CriticalFunctionEntry,
    CriticalFunctionSummary,
    CrewMemberOutcome,
    CrewOutcomeSummary,
    EquipmentItemOutcome,
    EquipmentOutcomeSummary,
    ExampleTrajectory,
    HazardOutcome,
    ScenarioIn,
    EmergencyConfigIn,
    SimulationResponse,
    TrajectoryStep,
    UncertaintySummary,
)


SOURCE_LABEL = "MockSimulatorAdapter (Phase B — not Phase A simulation physics)"
SIMULATED_HORIZON_SECONDS = 300
TIME_STEP_SECONDS = 60


def generate_actions(scenario: ScenarioIn, emergency: EmergencyConfigIn) -> list[ActionSpecOut]:
    """
    Generate plausible feasible actions from the current graph topology.
    Actions are derived from the live graph — not hard-coded to any module names.
    """
    actions: list[ActionSpecOut] = []

    # Always include baseline
    actions.append(ActionSpecOut(
        id="do_nothing",
        label="Do Nothing",
        description=(
            "No immediate intervention. All propagation pathways remain open. "
            "Preserves access to all resources but allows hazard spread."
        ),
        operations=[ActionOperationOut(type="do_nothing", targetId="")],
    ))

    affected_id = emergency.affectedModuleId
    modules = scenario.modules
    connections = scenario.connections

    # Close each open connection adjacent to the affected module
    for conn in connections.values():
        if conn.source == affected_id or conn.target == affected_id:
            if conn.state == "open":
                other_id = conn.target if conn.source == affected_id else conn.source
                other_name = modules[other_id].name if other_id in modules else other_id
                affected_name = modules[affected_id].name if affected_id in modules else affected_id
                conn_type_label = conn.type.upper() if conn.type else "CONNECTION"
                actions.append(ActionSpecOut(
                    id=f"close_conn_{conn.id}",
                    label=f"Close {conn_type_label}: {affected_name} ↔ {other_name}",
                    description=(
                        f"Seals the {conn.type} between {affected_name} and {other_name}. "
                        f"Reduces direct hazard pathway to {other_name}. "
                        f"Resources in both modules remain accessible via other paths."
                    ),
                    operations=[ActionOperationOut(type="close_connection", targetId=conn.id)],
                ))

                # Also generate ventilation shutdown for IMV connections
                if conn.type == "imv" and conn.ventilationOn:
                    actions.append(ActionSpecOut(
                        id=f"shutdown_vent_{conn.id}",
                        label=f"Shutdown IMV Ventilation: {affected_name} ↔ {other_name}",
                        description=(
                            f"Turns off the ventilation fan on the IMV duct between "
                            f"{affected_name} and {other_name}. "
                            f"Reduces atmospheric transfer without fully sealing the path."
                        ),
                        operations=[ActionOperationOut(type="shutdown_ventilation", targetId=conn.id)],
                    ))

    # Isolate the affected module entirely
    if affected_id in modules:
        affected_name = modules[affected_id].name
        actions.append(ActionSpecOut(
            id=f"isolate_module_{affected_id}",
            label=f"Isolate {affected_name}",
            description=(
                f"Disconnects {affected_name} from the entire spacecraft network. "
                f"Strongest hazard containment, but all equipment inside {affected_name} "
                f"becomes unavailable for the remainder of the mission."
            ),
            operations=[ActionOperationOut(type="isolate_module", targetId=affected_id)],
        ))

    return actions


def simulate(
    scenario: ScenarioIn,
    emergency: EmergencyConfigIn,
    action_ids: Optional[list[str]],
    runs: int,
    seed: Optional[int],
) -> SimulationResponse:
    """
    Phase B mock simulation. Returns plausible-shaped structured output.
    All sample counts are mock values — not Phase A physics results.
    """
    rng = random.Random(seed if seed is not None else 42)

    all_actions = generate_actions(scenario, emergency)

    # Filter to requested action IDs, or use all
    if action_ids is not None:
        available_ids = {action.id for action in all_actions}
        unknown_ids = [action_id for action_id in action_ids if action_id not in available_ids]
        if unknown_ids:
            raise ValueError(f"Unknown action id(s): {', '.join(unknown_ids)}")
        selected = [a for a in all_actions if a.id in action_ids]
    else:
        selected = all_actions

    results: list[ActionSimulationResult] = []

    modules = scenario.modules
    connections = scenario.connections
    affected_id = emergency.affectedModuleId

    # Collect all crew across all modules
    all_crew: dict[str, tuple[str, str]] = {}  # id -> (name, module_id)
    for mod_id, mod in modules.items():
        for c in mod.crew:
            all_crew[c.id] = (c.name, mod_id)

    # Collect all equipment across all modules
    all_equipment: dict[str, tuple[str, str, str, str, list[str]]] = {}
    # id -> (name, type, module_id, initial_state, capabilities)
    for mod_id, mod in modules.items():
        for eq in mod.equipment:
            all_equipment[eq.id] = (
                eq.name,
                eq.type,
                mod_id,
                eq.state,
                eq.providesCapabilities,
            )

    for action in selected:
        is_isolation = any(op.type == "isolate_module" for op in action.operations)
        is_close = any(op.type == "close_connection" for op in action.operations)
        is_do_nothing = any(op.type == "do_nothing" for op in action.operations)
        is_vent_shutdown = any(op.type == "shutdown_ventilation" for op in action.operations)

        # Compute mock containment ratios — better for more aggressive actions
        if is_isolation:
            containment_ratio = rng.uniform(0.85, 0.97)
            crew_safe_ratio = rng.uniform(0.75, 0.90)
            trapped_ratio = rng.uniform(0.0, 0.05)
            exposure_seconds = rng.randint(0, 30)
        elif is_close:
            containment_ratio = rng.uniform(0.55, 0.75)
            crew_safe_ratio = rng.uniform(0.70, 0.88)
            trapped_ratio = rng.uniform(0.02, 0.08)
            exposure_seconds = rng.randint(30, 120)
        elif is_vent_shutdown:
            containment_ratio = rng.uniform(0.40, 0.60)
            crew_safe_ratio = rng.uniform(0.65, 0.82)
            trapped_ratio = rng.uniform(0.03, 0.10)
            exposure_seconds = rng.randint(60, 180)
        else:  # do_nothing
            containment_ratio = rng.uniform(0.05, 0.20)
            crew_safe_ratio = rng.uniform(0.40, 0.65)
            trapped_ratio = rng.uniform(0.10, 0.25)
            exposure_seconds = rng.randint(120, 300)

        all_evacuated_count = int(crew_safe_ratio * runs)
        any_trapped_count = int(trapped_ratio * runs)
        contained_count = int(containment_ratio * runs)

        # Determine hazard reach — isolation = stays in affected module
        if is_isolation:
            reached_ids = [affected_id] if affected_id in modules else []
        elif is_do_nothing:
            # Hazard spreads to neighbors
            reached_ids = [affected_id]
            for conn in connections.values():
                if conn.source == affected_id and conn.state == "open":
                    reached_ids.append(conn.target)
                elif conn.target == affected_id and conn.state == "open":
                    reached_ids.append(conn.source)
        else:
            # Partial spread: only some neighbors reached
            reached_ids = [affected_id]
            for conn in connections.values():
                if conn.state != "open":
                    continue
                if conn.source == affected_id or conn.target == affected_id:
                    other = conn.target if conn.source == affected_id else conn.source
                    closed_by_action = any(
                        op.targetId == conn.id
                        for op in action.operations
                        if op.type == "close_connection"
                    )
                    if not closed_by_action and rng.random() > 0.5:
                        reached_ids.append(other)

        # Build per-crew outcome
        crew_outcomes: dict[str, CrewMemberOutcome] = {}
        for crew_id, (crew_name, crew_module_id) in all_crew.items():
            if crew_module_id == affected_id:
                if is_isolation:
                    status = "evacuated"
                    exp = exposure_seconds
                elif is_do_nothing:
                    status = "exposed"
                    exp = exposure_seconds
                else:
                    status = "evacuating" if rng.random() > 0.3 else "safe"
                    exp = exposure_seconds
            else:
                status = "safe"
                exp = 0
            crew_outcomes[crew_id] = CrewMemberOutcome(status=status, exposureExampleSeconds=exp)

        # Build per-equipment outcome
        equipment_outcomes: dict[str, EquipmentItemOutcome] = {}
        for eq_id, (eq_name, eq_type, eq_module_id, initial_state, capabilities) in all_equipment.items():
            if initial_state in ("unavailable", "explicitly_failed"):
                state = initial_state
            elif eq_module_id == affected_id and is_isolation:
                state = "unavailable"
            elif eq_module_id in reached_ids and is_do_nothing:
                state = "exposed_at_risk"
            elif eq_module_id == affected_id:
                state = "exposed_at_risk"
            else:
                state = initial_state
            equipment_outcomes[eq_id] = EquipmentItemOutcome(name=eq_name, state=state)

        # Build capability outcomes from providesCapabilities
        capability_map: dict[str, list[str]] = {}  # capability -> list of equipment states
        for eq_id, (eq_name, eq_type, eq_module_id, initial_state, capabilities) in all_equipment.items():
            for cap in capabilities:
                capability_map.setdefault(cap, []).append(equipment_outcomes[eq_id].state)

        cap_summary: dict[str, str] = {}
        for cap, states in capability_map.items():
            if any(s == "operational" for s in states):
                cap_summary[cap] = "available"
            elif any(s == "exposed_at_risk" for s in states):
                cap_summary[cap] = "degraded"
            else:
                cap_summary[cap] = "unavailable"

        # Build critical functions from providesFunctions
        function_map: dict[str, list[str]] = {}  # function -> list of crew statuses
        for crew_id, (crew_name, crew_module_id) in all_crew.items():
            crew_obj = None
            if crew_module_id in modules:
                for c in modules[crew_module_id].crew:
                    if c.id == crew_id:
                        crew_obj = c
                        break
            if crew_obj:
                crew_status = crew_outcomes[crew_id].status
                for fn in crew_obj.providesFunctions:
                    function_map.setdefault(fn, []).append(crew_status)

        fn_summary: dict[str, CriticalFunctionEntry] = {}
        for fn, statuses in function_map.items():
            total = len(statuses)
            available = sum(1 for s in statuses if s in ("safe", "evacuating", "evacuated"))
            if available == 0:
                fn_status = "no_provider"
            elif available == 1:
                fn_status = "single_provider"
            else:
                fn_status = "nominal"
            fn_summary[fn] = CriticalFunctionEntry(
                providersAvailable=available,
                totalProviders=total,
                status=fn_status,
            )

        # Example trajectory (mock steps)
        base_seed = seed if seed is not None else 42
        stable_action_hash = int.from_bytes(
            hashlib.sha256(action.id.encode("utf-8")).digest()[:4],
            byteorder="big",
        )
        traj_seed = base_seed + stable_action_hash % 1000
        trajectory = _build_example_trajectory(
            modules=modules,
            affected_id=affected_id,
            action=action,
            traj_seed=traj_seed,
            n_steps=5,
        )

        results.append(ActionSimulationResult(
            actionId=action.id,
            hazard=HazardOutcome(
                modulesReached=len(set(reached_ids)),
                modulesReachedIds=list(set(reached_ids)),
                containedInNScenarios=contained_count,
                totalScenarios=runs,
            ),
            crew=CrewOutcomeSummary(
                allEvacuatedCount=all_evacuated_count,
                anyTrappedCount=any_trapped_count,
                totalScenarios=runs,
                byCrewMember=crew_outcomes if crew_outcomes else None,
            ),
            equipment=EquipmentOutcomeSummary(byEquipmentId=equipment_outcomes),
            capabilities=CapabilityOutcomeSummary(byCapability=cap_summary),
            criticalFunctions=CriticalFunctionSummary(byFunction=fn_summary),
            uncertaintySummary=UncertaintySummary(
                note="Mock Phase B output. Sample counts do not reflect validated physical simulation."
            ),
            exampleTrajectory=trajectory,
        ))

    return SimulationResponse(
        generatedActions=selected,
        results=results,
        simulatedHorizonSeconds=SIMULATED_HORIZON_SECONDS,
        runsRequested=runs,
        seed=seed,
        sourceLabel=SOURCE_LABEL,
    )


def _build_example_trajectory(
    modules: dict,
    affected_id: str,
    action: ActionSpecOut,
    traj_seed: int,
    n_steps: int,
) -> ExampleTrajectory:
    rng = random.Random(traj_seed)
    steps: list[TrajectoryStep] = []

    severity = 0.35  # initial fire severity in affected module

    for i in range(n_steps + 1):
        t = i * TIME_STEP_SECONDS
        module_states: dict[str, dict] = {}
        events: list[str] = []

        for mod_id, mod in modules.items():
            if mod_id == affected_id:
                sev = min(1.0, severity + i * rng.uniform(0.0, 0.08))
                # Action applied at step 1
                if i == 1 and not any(op.type == "do_nothing" for op in action.operations):
                    sev = max(0.0, sev - 0.1)  # mild suppression effect
            else:
                # Spread only if not contained by action
                is_contained = any(
                    (op.type in ("close_connection", "isolate_module"))
                    for op in action.operations
                )
                if is_contained:
                    sev = 0.0
                else:
                    sev = rng.uniform(0.0, 0.15) if i > 2 else 0.0

            crew_count = sum(
                1 for c in mod.crew
            ) if i == 0 else max(0, sum(1 for c in mod.crew) - (1 if mod_id == affected_id and i > 1 else 0))
            module_states[mod_id] = {
                "hazardSeverity": round(sev, 3),
                "crewPresent": crew_count,
            }

        if i == 0:
            events.append(f"Fire detected in {modules[affected_id].name}" if affected_id in modules else "Fire detected")
        if i == 1 and not any(op.type == "do_nothing" for op in action.operations):
            events.append(f"Action applied: {action.label}")
        if i == 2 and any(op.type == "isolate_module" for op in action.operations):
            events.append(f"Module isolated — all connections sealed")
        if i == 3:
            events.append("Crew status assessment complete")

        steps.append(TrajectoryStep(
            stepIndex=i,
            timeSeconds=t,
            moduleStates=module_states,
            events=events,
        ))

    return ExampleTrajectory(seed=traj_seed, steps=steps)
