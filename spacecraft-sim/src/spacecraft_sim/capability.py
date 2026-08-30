"""Capability dependency graph (A-7) with crew coupling, in real units.

Separate from the physical module graph. The four system states are defined by
*recoverability*, not by cause:

- FAILED_EXPLICITLY: depended-on equipment is damaged and cannot currently be
  repaired (no repair provider on site).
- UNAVAILABLE:       recoverable by reversing a choice or restoring a person —
                     the module is isolated, equipment is powered down, or the
                     system has no available operator.
- EXPOSED_AT_RISK:   a depended-on module carries detectable smoke or fire.
- OPERATIONAL:       none of the above.

`unavailable_reason` records which of those applies, so a downstream agent can
tell "sealed off" from "nobody left who can run it".

Crew coupling (the A-8.2 "function vs function capability" idea):
- Operating: a system with an `operator_function` needs at least one available
  crew member providing it. Losing the sole provider takes the system down even
  though the hardware is fine.
- Repairing: damaged equipment recovers only while a crew member providing the
  system's `repair_function` is physically in that module, able to work, and
  the module is not hazardous.
"""

from spacecraft_sim import config
from spacecraft_sim.models import Crew, Scenario


def available_providers(scenario: Scenario, function: str) -> list[Crew]:
    """Crew who provide `function` and are not trapped."""
    from spacecraft_sim.crew import functions_of  # local: avoids a cycle

    return [
        c for c in scenario.crew if c.state != "TRAPPED" and function in functions_of(c)
    ]


def working_providers_in(scenario: Scenario, function: str, module_id: str) -> list[Crew]:
    """Providers of `function` who are in `module_id` and able to do work."""
    return [
        c
        for c in available_providers(scenario, function)
        if c.module_id == module_id and c.state in config.ASSUMED_WORKING_CREW_STATES
    ]


def update_equipment_damage(scenario: Scenario) -> None:
    """Permanent-unless-repaired equipment damage from local conditions.

    ASSUMED rules: heat damages everything; heavy soot shorts out *powered*
    electronics, so powering equipment down protects against the smoke path but
    not the heat path.
    """
    for equipment in scenario.equipment:
        if equipment.damaged:
            continue
        module = scenario.module(equipment.module_id)
        if module.temperature_c >= config.ASSUMED_EQUIPMENT_DAMAGE_TEMPERATURE_C:
            equipment.damaged = True
            equipment.repair_progress_seconds = 0.0
        elif (
            equipment.powered
            and module.concentration("soot") >= config.ASSUMED_EQUIPMENT_DAMAGE_SOOT_MG_M3
        ):
            equipment.damaged = True
            equipment.repair_progress_seconds = 0.0


def update_repairs(scenario: Scenario, dt: float) -> None:
    """Advance repairs on damaged equipment that has a repairer on site."""
    from spacecraft_sim.crew import module_is_hazardous  # local: avoids a cycle

    repair_function_for = {
        system.id: system.repair_function for system in scenario.systems
    }

    for equipment in scenario.equipment:
        if not equipment.damaged:
            continue
        if module_is_hazardous(scenario, equipment.module_id):
            continue  # nobody works a repair inside smoke or fire

        function = repair_function_for.get(
            equipment.system, config.DEFAULT_REPAIR_FUNCTION
        )
        if not working_providers_in(scenario, function, equipment.module_id):
            continue

        equipment.repair_progress_seconds += dt
        if equipment.repair_progress_seconds >= config.ASSUMED_REPAIR_SECONDS:
            equipment.damaged = False
            equipment.repair_progress_seconds = 0.0


def evaluate_systems(scenario: Scenario) -> dict[str, str]:
    """Judge every system from its module, equipment and crew dependencies
    (in-place and returned as {system_id: state})."""
    equipment_by_id = {e.id: e for e in scenario.equipment}
    states: dict[str, str] = {}

    for system in scenario.systems:
        dep_equipment = [
            equipment_by_id[eid]
            for eid in system.depends_on_equipment
            if eid in equipment_by_id
        ]
        dep_modules = [m for m in scenario.modules if m.id in system.depends_on_modules]

        operators = (
            available_providers(scenario, system.operator_function)
            if system.operator_function
            else None
        )

        if any(e.damaged for e in dep_equipment):
            state, reason = "FAILED_EXPLICITLY", "equipment_damaged"
        elif any(m.isolated for m in dep_modules):
            state, reason = "UNAVAILABLE", "module_isolated"
        elif any(not m.power_sufficient for m in dep_modules):
            state, reason = "UNAVAILABLE", "insufficient_module_power"
        elif any(not e.powered for e in dep_equipment):
            state, reason = "UNAVAILABLE", "equipment_powered_down"
        elif operators is not None and not operators:
            state, reason = "UNAVAILABLE", f"no_operator:{system.operator_function}"
        elif any(
            m.fire_state in ("incipient", "sustained")
            or m.extinction_per_m >= config.VERIFIED_DETECTOR_ALARM_EXTINCTION_PER_M
            for m in dep_modules
        ):
            state, reason = "EXPOSED_AT_RISK", "smoke_or_fire_in_module"
        else:
            state, reason = "OPERATIONAL", None

        system.state = state
        system.unavailable_reason = reason
        states[system.id] = state
    return states


def evaluate_capabilities(scenario: Scenario) -> dict[str, str]:
    """Aggregate systems into capability availability:
    AVAILABLE | AT_RISK | UNAVAILABLE."""
    system_states = {s.id: s.state for s in scenario.systems}
    capabilities: dict[str, str] = {}
    for capability, system_ids in scenario.capabilities.items():
        states = [system_states.get(sid, "OPERATIONAL") for sid in system_ids]
        if any(s in ("UNAVAILABLE", "FAILED_EXPLICITLY") for s in states):
            capabilities[capability] = "UNAVAILABLE"
        elif any(s == "EXPOSED_AT_RISK" for s in states):
            capabilities[capability] = "AT_RISK"
        else:
            capabilities[capability] = "AVAILABLE"
    return capabilities


def damaged_facilities(scenario: Scenario) -> list[str]:
    """System ids currently not functioning — feeds crew criticality demand."""
    return [
        s.id for s in scenario.systems if s.state in ("UNAVAILABLE", "FAILED_EXPLICITLY")
    ]
