from spacecraft_sim import config
from spacecraft_sim.actions import find_action, generate_actions
from spacecraft_sim.engine import counterfactual, simulate
from spacecraft_sim.montecarlo import run_montecarlo
from spacecraft_sim.report import format_comparison, format_criticality, format_result
from tests.conftest import add_crew, add_system, make_line_scenario

HORIZON = 1800.0
DT = 30.0


def test_isolation_yields_unavailable_not_failed():
    scenario = make_line_scenario(n_modules=3, fire_in="A2")
    add_system(scenario, "power", "A1", equipment_id="eq1")
    scenario.module("A1").isolated = True
    result = simulate(scenario, horizon=300, dt=DT)
    assert result.summary["systems"]["power"] == "UNAVAILABLE"


def test_fire_damage_yields_failed_explicitly():
    scenario = make_line_scenario(
        n_modules=3, fire_in="A1", profile="GRADUAL_PMMA_GROWTH"
    )
    add_system(scenario, "power", "A1", equipment_id="eq1")
    result = simulate(scenario, horizon=HORIZON, dt=DT)
    assert result.summary["systems"]["power"] == "FAILED_EXPLICITLY"


def test_unavailable_vs_failed_are_distinct_states():
    scenario = make_line_scenario(
        n_modules=4, fire_in="A1", profile="GRADUAL_PMMA_GROWTH"
    )
    add_system(scenario, "sysA", "A1", equipment_id="eqA")   # burns -> FAILED
    add_system(scenario, "sysB", "A4", equipment_id="eqB")   # isolated -> UNAVAILABLE
    scenario.module("A4").isolated = True
    result = simulate(scenario, horizon=HORIZON, dt=DT)
    assert result.summary["systems"]["sysA"] == "FAILED_EXPLICITLY"
    assert result.summary["systems"]["sysB"] == "UNAVAILABLE"


def test_counterfactual_close_hatch_contains_smoke():
    scenario = make_line_scenario(n_modules=3, fire_in="A1")
    base = counterfactual(scenario, find_action(scenario, "do_nothing"), HORIZON, DT)
    closed = counterfactual(scenario, find_action(scenario, "close_hatch:c0"), HORIZON, DT)

    assert "A2" in base.summary["hazard_reached"]
    assert closed.summary["hazard_reached"] == ["A1"]


# ── Detection is computed, not assumed ───────────────────────────────────────

def test_detection_happens_when_smoke_reaches_alarm_level():
    scenario = make_line_scenario(n_modules=2, fire_in="A1")
    result = simulate(scenario, horizon=HORIZON, dt=DT)
    detected = result.summary["detected_at_seconds"]
    assert detected is not None and detected > 0


def test_no_fire_means_no_detection():
    scenario = make_line_scenario(n_modules=2)
    result = simulate(scenario, horizon=HORIZON, dt=DT)
    assert result.summary["detected_at_seconds"] is None
    assert result.summary["hazard_reached"] == []


def test_unventilated_module_detects_later():
    # Detectors sit on ventilation intake ducts, so an unventilated module takes
    # the assumed penalty factor longer to confirm an alarm.
    vented = make_line_scenario(
        n_modules=2, fire_in="A1", connection_type="imv", ventilation="on"
    )
    unvented = make_line_scenario(
        n_modules=2, fire_in="A1", connection_type="imv", ventilation="off"
    )
    t_vented = simulate(vented, horizon=HORIZON, dt=DT).summary["detected_at_seconds"]
    t_unvented = simulate(unvented, horizon=HORIZON, dt=DT).summary["detected_at_seconds"]
    assert t_vented is not None and t_unvented is not None
    assert t_unvented > t_vented


def test_decision_delay_shifts_when_the_action_lands():
    scenario = make_line_scenario(n_modules=3, fire_in="A1")
    action = find_action(scenario, "close_hatch:c0")
    prompt = counterfactual(scenario, action, HORIZON, DT, decision_delay=0.0)
    slow = counterfactual(scenario, action, HORIZON, DT, decision_delay=900.0)
    # Acting late lets more smoke through before the hatch shuts.
    assert (
        slow.summary["peak_extinction_per_m"]["A2"]
        > prompt.summary["peak_extinction_per_m"]["A2"]
    )


# ── Real-unit outcomes ───────────────────────────────────────────────────────

def test_ventilated_small_fire_does_not_reach_smac(demo):
    """The calibration report's key prediction: with ventilation running, a
    fire of this scale plateaus well below the 1-hour SMAC, so the binding
    hazard is obscuration rather than toxicity."""
    result = counterfactual(demo, find_action(demo, "do_nothing"), HORIZON, DT)
    assert result.summary["smac_exceeded"] == []
    assert result.summary["hazard_reached"]  # smoke is still detected


def test_summary_reports_capabilities_and_critical_functions(demo):
    result = simulate(demo, horizon=HORIZON, dt=DT)
    assert set(result.summary["capabilities"]) == {"RETURN", "HABITATION"}
    flagged = {f["function"] for f in result.summary["critical_functions"]}
    assert "life_support_ops" in flagged


# ── Monte Carlo ──────────────────────────────────────────────────────────────

def test_montecarlo_returns_counts_not_probabilities(demo):
    action = find_action(demo, "shutdown_ventilation:c_m2_m3")
    dist = run_montecarlo(demo, action, n=15, seed=7, horizon=600, dt=60)
    assert dist.samples == 15
    for count in (
        dist.retained_evacuation_and_return,
        dist.no_crew_trapped,
        dist.return_available,
        dist.habitation_available,
        dist.hazard_contained_to_sources,
        dist.no_crew_reached_smac_dose,
    ):
        assert isinstance(count, int)
        assert 0 <= count <= 15


def test_montecarlo_reproducible_with_seed(demo):
    action = find_action(demo, "do_nothing")
    a = run_montecarlo(demo, action, n=10, seed=42, horizon=600, dt=60)
    b = run_montecarlo(demo, action, n=10, seed=42, horizon=600, dt=60)
    assert a == b


def test_montecarlo_samples_flow_uncertainty(demo):
    import numpy as np

    from spacecraft_sim.montecarlo import sample_scenario

    rng = np.random.default_rng(0)
    flows = {sample_scenario(demo, rng)[0].connection("c_m2_m3").flow_m3_s for _ in range(5)}
    assert len(flows) > 1
    for flow in flows:
        assert flow > 0


# ── Reports ──────────────────────────────────────────────────────────────────

def test_compare_report_shows_facts_without_best_action(demo):
    results = [
        counterfactual(demo, action, 600, 60) for action in generate_actions(demo)
    ]
    text = format_comparison(results)
    assert "BEST" not in text.upper()
    assert "no recommendation" in text
    assert "do_nothing" in text


def test_result_report_shows_real_units(demo):
    result = counterfactual(demo, find_action(demo, "isolate:M2"), HORIZON, DT)
    text = format_result(result)
    assert text.startswith("ACTION: isolate:M2")
    assert "Detected at:" in text
    assert "SMAC" in text
    assert "0.033 /m" in text


def test_criticality_report_distinguishes_measured_from_assumed():
    findings = [
        {"crew_id": "C1", "role": "commander", "measured_score": 0.5, "assumed_weight": 0.9}
    ]
    text = format_criticality(findings)
    assert "measured" in text and "assumed" in text
    assert "Neither is a valuation of a life" in text


def test_default_horizon_covers_real_timescales():
    # The report's order-of-magnitude check showed 600 s is far too short once
    # emissions and dilution are in real units.
    assert config.HORIZON_SECONDS >= 3600.0
    assert config.DT_SECONDS >= 30.0
