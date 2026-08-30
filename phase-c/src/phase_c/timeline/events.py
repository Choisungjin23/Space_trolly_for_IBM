"""Semantic event extraction from the Phase A timeline.

A raw timeline is 120 frames x 5 dicts per action — far too heavy for a prompt
and less informative than the transitions inside it. This module turns it into
~10-30 typed events.

Frames carry only: t, extinction, co_mg_m3, crew, crew_modules, systems.
Capabilities are NOT in a frame, so capability transitions are
*derived* here by rolling per-frame system states up through the scenario's
capability map, and are flagged `source="derived"`.
"""

from phase_c.contracts.analysis import TimelineEvent

# Verified ISS detector alarm level, 1 %/ft obscuration expressed as 1/m.
# Mirrors Phase A's VERIFIED_DETECTOR_ALARM_EXTINCTION_PER_M; kept local so this
# module does not import the engine.
ALARM_EXTINCTION_PER_M = 0.033


def _rollup(system_states: dict[str, str], members: list[str]) -> str:
    """Phase A's capability roll-up rule, replicated for per-frame derivation."""
    states = [system_states.get(sid, "OPERATIONAL") for sid in members]
    if any(s in ("UNAVAILABLE", "FAILED_EXPLICITLY") for s in states):
        return "UNAVAILABLE"
    if any(s == "EXPOSED_AT_RISK" for s in states):
        return "AT_RISK"
    return "AVAILABLE"


def extract_events(
    timeline: list[dict],
    *,
    detected_at_seconds: float | None,
    smac_exceeded_modules: list[str],
    capability_map: dict[str, list[str]] | None = None,
) -> list[TimelineEvent]:
    """Turn frames into semantic events, in chronological order."""
    events: list[TimelineEvent] = []
    if not timeline:
        return events

    capability_map = capability_map or {}

    previous_crew: dict[str, str] = {}
    previous_modules: dict[str, str] = {}
    previous_systems: dict[str, str] = {}
    previous_caps: dict[str, str] = {}
    hazard_announced: set[str] = set()
    smac_announced: set[str] = set()
    detection_announced = False

    # Peak extinction per module, for the burnback milestone.
    peaks: dict[str, float] = {}
    peak_time: dict[str, float] = {}
    halved: set[str] = set()

    smac_pending = set(smac_exceeded_modules)

    for frame in timeline:
        t = float(frame["t"])
        extinction: dict[str, float] = frame.get("extinction", {})
        crew: dict[str, str] = frame.get("crew", {})
        crew_modules: dict[str, str] = frame.get("crew_modules", {})
        systems: dict[str, str] = frame.get("systems", {})

        if (
            not detection_announced
            and detected_at_seconds is not None
            and t >= detected_at_seconds
        ):
            events.append(
                TimelineEvent(
                    t=detected_at_seconds,
                    type="detection_confirmed",
                    subject="spacecraft",
                    to_state="DETECTED",
                )
            )
            detection_announced = True

        for module_id, value in extinction.items():
            if value >= ALARM_EXTINCTION_PER_M and module_id not in hazard_announced:
                hazard_announced.add(module_id)
                events.append(
                    TimelineEvent(
                        t=t,
                        type="hazard_arrival",
                        subject=module_id,
                        to_state="SMOKE_AT_ALARM_LEVEL",
                    )
                )
            # SMAC exceedance times are not in frames; the summary only lists
            # which modules. Anchor the event at that module's hazard arrival so
            # the ordering stays truthful without inventing a timestamp.
            if (
                module_id in smac_pending
                and module_id in hazard_announced
                and module_id not in smac_announced
            ):
                smac_announced.add(module_id)
                events.append(
                    TimelineEvent(
                        t=t,
                        type="smac_exceeded",
                        subject=module_id,
                        to_state="ABOVE_1H_SMAC",
                        source="derived",
                    )
                )

            if value > peaks.get(module_id, -1.0):
                peaks[module_id] = value
                peak_time[module_id] = t
            elif (
                module_id in peaks
                and peaks[module_id] >= ALARM_EXTINCTION_PER_M
                and module_id not in halved
                and value <= peaks[module_id] / 2
            ):
                halved.add(module_id)
                events.append(
                    TimelineEvent(
                        t=t,
                        type="extinction_milestone",
                        subject=module_id,
                        from_state="PEAK",
                        to_state="HALF_PEAK",
                    )
                )

        for crew_id, state in crew.items():
            if previous_crew and previous_crew.get(crew_id) != state:
                events.append(
                    TimelineEvent(
                        t=t,
                        type="crew_state_change",
                        subject=crew_id,
                        from_state=previous_crew.get(crew_id),
                        to_state=state,
                    )
                )
        previous_crew = dict(crew)

        for crew_id, module_id in crew_modules.items():
            if previous_modules and previous_modules.get(crew_id) != module_id:
                events.append(
                    TimelineEvent(
                        t=t,
                        type="crew_module_change",
                        subject=crew_id,
                        from_state=previous_modules.get(crew_id),
                        to_state=module_id,
                    )
                )
        previous_modules = dict(crew_modules)

        for system_id, state in systems.items():
            if previous_systems and previous_systems.get(system_id) != state:
                events.append(
                    TimelineEvent(
                        t=t,
                        type="system_state_change",
                        subject=system_id,
                        from_state=previous_systems.get(system_id),
                        to_state=state,
                    )
                )
        previous_systems = dict(systems)

        if capability_map:
            current_caps = {
                name: _rollup(systems, members)
                for name, members in capability_map.items()
            }
            for name, state in current_caps.items():
                if previous_caps and previous_caps.get(name) != state:
                    events.append(
                        TimelineEvent(
                            t=t,
                            type="capability_change",
                            subject=name,
                            from_state=previous_caps.get(name),
                            to_state=state,
                            source="derived",
                        )
                    )
            previous_caps = current_caps

    events.sort(key=lambda e: (e.t, e.type, e.subject))
    return events


def downsample(timeline: list[dict], every: int) -> list[dict]:
    """Uniform downsampling. Debug aid only, OFF by default — when used, the
    caller must record it in Provenance so nobody mistakes a sampled curve for
    the full one."""
    if every < 1:
        raise ValueError("every must be >= 1")
    sampled = timeline[::every]
    if timeline and sampled[-1] is not timeline[-1]:
        sampled.append(timeline[-1])
    return sampled
