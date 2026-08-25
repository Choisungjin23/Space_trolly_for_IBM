"""Time-integration loop and counterfactual simulation (A-5, A-10).

`simulate` advances an independent deep copy of the scenario:
    hazard transport -> fire evolution -> detection -> equipment damage
    -> systems/capabilities -> crew update
recording a timeline plus an end-of-run summary.

Detection is COMPUTED, not assumed. A module alarms once its smoke extinction
passes the verified ISS detector threshold on two consecutive readings. Because
ISS detectors sit on ventilation intake ducts, a module with no active
ventilation takes an assumed penalty factor longer to confirm. The action is
then applied at (detection time + decision delay), so "how fast the crew learn"
becomes an emergent property rather than a free parameter.
"""

from dataclasses import dataclass, field

from spacecraft_sim import config
from spacecraft_sim.actions import Action
from spacecraft_sim.capability import (
    damaged_facilities,
    evaluate_capabilities,
    evaluate_systems,
    update_equipment_damage,
    update_repairs,
)
from spacecraft_sim.crew import critical_functions, update_crew
from spacecraft_sim.hazard import step_hazard
from spacecraft_sim.models import Scenario
from spacecraft_sim.profiles import is_extinguished


@dataclass
class TimelineResult:
    action_id: str
    timeline: list[dict] = field(default_factory=list)
    final: Scenario | None = None
    summary: dict = field(default_factory=dict)


def _module_has_active_ventilation(scenario: Scenario, module_id: str) -> bool:
    return any(
        conn.type == "imv"
        and conn.ventilation_state == "on"
        and conn.path_state == "open"
        for conn in scenario.connections_of(module_id)
    )


def _update_detection(scenario: Scenario, dt: float) -> bool:
    """Advance each module's detector. Returns True if anything is alarming."""
    for module in scenario.modules:
        above = (
            module.extinction_per_m >= config.VERIFIED_DETECTOR_ALARM_EXTINCTION_PER_M
        )
        if not above:
            module.detector_streak = 0
            continue

        confirm = config.ASSUMED_DETECTOR_CONFIRM_SECONDS
        if not _module_has_active_ventilation(scenario, module.id):
            confirm *= config.ASSUMED_UNVENTILATED_DETECTION_PENALTY

        module.detector_streak += 1
        # Two consecutive readings, each taking `confirm` seconds of dwell.
        if module.detector_streak * dt >= 2 * confirm:
            module.detected = True

    return any(m.detected for m in scenario.modules)


def simulate(
    scenario: Scenario,
    action: Action | None = None,
    horizon: float | None = None,
    dt: float | None = None,
    decision_delay: float = 0.0,
    response_seconds: float | None = None,
) -> TimelineResult:
    horizon = config.HORIZON_SECONDS if horizon is None else horizon
    dt = config.DT_SECONDS if dt is None else dt
    if response_seconds is None:
        response_seconds = config.ASSUMED_CREW_RESPONSE_SECONDS_DEFAULT

    sc = scenario.model_copy(deep=True)
    result = TimelineResult(action_id=action.id if action else "do_nothing")

    peak_extinction = {m.id: m.extinction_per_m for m in sc.modules}
    peak_smac = {m.id: m.worst_smac_fraction for m in sc.modules}
    applied = action is None
    detected_at: float | None = None

    steps = int(horizon / dt)
    t = 0.0
    for _ in range(steps):
        step_hazard(sc, t, dt)

        # Decaying-profile fires burn out once their emission ramps to zero.
        for module in sc.modules:
            if is_extinguished(module, t):
                module.fire_state = "suppressed"

        if _update_detection(sc, dt) and detected_at is None:
            detected_at = t

        # The action lands once the crew know AND have decided.
        if not applied and detected_at is not None and t >= detected_at + decision_delay:
            sc = action.apply(sc)
            applied = True

        update_equipment_damage(sc)
        update_repairs(sc, dt)
        evaluate_systems(sc)
        update_crew(sc, t, dt, response_seconds)

        for module in sc.modules:
            peak_extinction[module.id] = max(
                peak_extinction[module.id], module.extinction_per_m
            )
            peak_smac[module.id] = max(peak_smac[module.id], module.worst_smac_fraction)

        t += dt
        result.timeline.append(
            {
                "t": t,
                "extinction": {m.id: round(m.extinction_per_m, 5) for m in sc.modules},
                "co_mg_m3": {m.id: round(m.concentration("CO"), 3) for m in sc.modules},
                "crew": {c.id: c.state for c in sc.crew},
                "crew_modules": {c.id: c.module_id for c in sc.crew},
                "systems": {s.id: s.state for s in sc.systems},
            }
        )

    # A fire that is never detected means the action never fires; apply it at
    # the end so the summary still reflects the requested counterfactual.
    if not applied:
        sc = action.apply(sc)

    evaluate_systems(sc)
    facilities_down = damaged_facilities(sc)

    result.final = sc
    result.summary = {
        "action_id": result.action_id,
        "detected_at_seconds": detected_at,
        "hazard_reached": sorted(
            mid
            for mid, peak in peak_extinction.items()
            if peak >= config.VERIFIED_DETECTOR_ALARM_EXTINCTION_PER_M
        ),
        "smac_exceeded": sorted(
            mid for mid, peak in peak_smac.items() if peak >= 1.0
        ),
        "peak_extinction_per_m": {
            mid: round(peak, 5) for mid, peak in peak_extinction.items()
        },
        "crew": {
            c.id: {
                "state": c.state,
                "exposure_seconds": round(c.hazard_exposure_seconds, 1),
                "smac_dose_fraction": round(c.smac_dose_fraction, 4),
                "module": c.module_id,
            }
            for c in sc.crew
        },
        "crew_counts": {
            state: sum(1 for c in sc.crew if c.state == state)
            for state in ("SAFE", "EXPOSED", "EVACUATING", "EVACUATED", "TRAPPED")
        },
        "systems": {s.id: s.state for s in sc.systems},
        "system_reasons": {
            s.id: s.unavailable_reason for s in sc.systems if s.unavailable_reason
        },
        "capabilities": evaluate_capabilities(sc),
        "critical_functions": critical_functions(sc.crew, facilities_down),
    }
    return result


def counterfactual(
    scenario: Scenario,
    action: Action,
    horizon: float | None = None,
    dt: float | None = None,
    decision_delay: float = 0.0,
    response_seconds: float | None = None,
) -> TimelineResult:
    return simulate(
        scenario,
        action=action,
        horizon=horizon,
        dt=dt,
        decision_delay=decision_delay,
        response_seconds=response_seconds,
    )
