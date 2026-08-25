"""Semantic timeline extraction (plan §5), including the derived capability
transitions that plan §0.3 identified as necessary."""

from phase_c.timeline.events import ALARM_EXTINCTION_PER_M, downsample, extract_events


def frame(t, extinction=None, crew=None, crew_modules=None, systems=None):
    return {
        "t": t,
        "extinction": extinction or {},
        "co_mg_m3": {},
        "crew": crew or {},
        "crew_modules": crew_modules or {},
        "systems": systems or {},
    }


def types_of(events):
    return [e.type for e in events]


def test_empty_timeline_yields_nothing():
    assert extract_events([], detected_at_seconds=None, smac_exceeded_modules=[]) == []


def test_detection_event_uses_the_reported_time():
    timeline = [frame(30, {"M1": 0.0}), frame(60, {"M1": 0.0})]
    events = extract_events(timeline, detected_at_seconds=45.0, smac_exceeded_modules=[])
    detection = [e for e in events if e.type == "detection_confirmed"]
    assert len(detection) == 1
    assert detection[0].t == 45.0


def test_no_detection_means_no_detection_event():
    timeline = [frame(30, {"M1": 0.0})]
    events = extract_events(timeline, detected_at_seconds=None, smac_exceeded_modules=[])
    assert "detection_confirmed" not in types_of(events)


def test_hazard_arrival_fires_once_at_the_alarm_level():
    timeline = [
        frame(30, {"M1": ALARM_EXTINCTION_PER_M / 2}),
        frame(60, {"M1": ALARM_EXTINCTION_PER_M}),
        frame(90, {"M1": ALARM_EXTINCTION_PER_M * 4}),
    ]
    events = extract_events(timeline, detected_at_seconds=None, smac_exceeded_modules=[])
    arrivals = [e for e in events if e.type == "hazard_arrival"]
    assert len(arrivals) == 1
    assert arrivals[0].t == 60 and arrivals[0].subject == "M1"


def test_a_clean_module_produces_no_arrival():
    timeline = [frame(30, {"M1": 1.0, "M2": 0.0}), frame(60, {"M1": 1.0, "M2": 0.0})]
    events = extract_events(timeline, detected_at_seconds=None, smac_exceeded_modules=[])
    assert {e.subject for e in events if e.type == "hazard_arrival"} == {"M1"}


def test_crew_state_and_module_transitions():
    timeline = [
        frame(30, crew={"C1": "SAFE"}, crew_modules={"C1": "M1"}),
        frame(60, crew={"C1": "EXPOSED"}, crew_modules={"C1": "M1"}),
        frame(90, crew={"C1": "EVACUATING"}, crew_modules={"C1": "M2"}),
    ]
    events = extract_events(timeline, detected_at_seconds=None, smac_exceeded_modules=[])
    states = [e for e in events if e.type == "crew_state_change"]
    moves = [e for e in events if e.type == "crew_module_change"]
    assert [(e.from_state, e.to_state) for e in states] == [
        ("SAFE", "EXPOSED"),
        ("EXPOSED", "EVACUATING"),
    ]
    assert [(e.from_state, e.to_state) for e in moves] == [("M1", "M2")]


def test_system_transition_is_reported():
    timeline = [
        frame(30, systems={"power": "OPERATIONAL"}),
        frame(60, systems={"power": "EXPOSED_AT_RISK"}),
    ]
    events = extract_events(timeline, detected_at_seconds=None, smac_exceeded_modules=[])
    system_events = [e for e in events if e.type == "system_state_change"]
    assert len(system_events) == 1
    assert system_events[0].to_state == "EXPOSED_AT_RISK"


def test_capability_change_is_derived_and_labelled():
    """Plan §0.3: frames carry no capabilities, so Phase C recomputes them and
    must mark the result as derived rather than engine output."""
    timeline = [
        frame(30, systems={"power": "OPERATIONAL", "gnc": "OPERATIONAL"}),
        frame(60, systems={"power": "UNAVAILABLE", "gnc": "OPERATIONAL"}),
    ]
    events = extract_events(
        timeline,
        detected_at_seconds=None,
        smac_exceeded_modules=[],
        capability_map={"RETURN": ["power", "gnc"]},
    )
    caps = [e for e in events if e.type == "capability_change"]
    assert len(caps) == 1
    assert caps[0].subject == "RETURN"
    assert caps[0].to_state == "UNAVAILABLE"
    assert caps[0].source == "derived"


def test_capability_rollup_matches_phase_a_rules():
    timeline = [
        frame(30, systems={"a": "OPERATIONAL", "b": "OPERATIONAL"}),
        frame(60, systems={"a": "EXPOSED_AT_RISK", "b": "OPERATIONAL"}),
        frame(90, systems={"a": "EXPOSED_AT_RISK", "b": "FAILED_EXPLICITLY"}),
    ]
    events = extract_events(
        timeline,
        detected_at_seconds=None,
        smac_exceeded_modules=[],
        capability_map={"CAP": ["a", "b"]},
    )
    caps = [e.to_state for e in events if e.type == "capability_change"]
    assert caps == ["AT_RISK", "UNAVAILABLE"]


def test_smac_event_is_marked_derived():
    """The summary says WHICH modules exceeded, never when — so the event is
    anchored to hazard arrival and labelled derived rather than invented."""
    timeline = [frame(30, {"M2": 1.0}), frame(60, {"M2": 1.2})]
    events = extract_events(
        timeline, detected_at_seconds=None, smac_exceeded_modules=["M2"]
    )
    smac = [e for e in events if e.type == "smac_exceeded"]
    assert len(smac) == 1 and smac[0].source == "derived"


def test_events_are_chronological():
    timeline = [
        frame(30, {"M1": 1.0}, crew={"C1": "SAFE"}),
        frame(60, {"M1": 1.0, "M2": 1.0}, crew={"C1": "EXPOSED"}),
    ]
    events = extract_events(timeline, detected_at_seconds=30.0, smac_exceeded_modules=[])
    assert [e.t for e in events] == sorted(e.t for e in events)


def test_real_fixture_produces_a_prompt_sized_event_list(case):
    for analysis in case.actions:
        assert len(analysis.events) <= 40, analysis.action.id


def test_downsample_keeps_the_last_frame():
    timeline = [frame(t) for t in range(0, 100, 10)]
    sampled = downsample(timeline, 4)
    assert sampled[0] is timeline[0]
    assert sampled[-1] is timeline[-1]
