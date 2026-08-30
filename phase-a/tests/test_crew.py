from spacecraft_sim import config
from spacecraft_sim.actions import find_action
from spacecraft_sim.crew import (
    crew_weight,
    critical_functions,
    measured_criticality,
    module_is_hazardous,
    move_crew,
    update_crew,
)
from spacecraft_sim.engine import simulate
from tests.conftest import add_crew, make_line_scenario


def flood_with_smoke(scenario, module_id, extinction=1.0):
    """Raise a module's soot to a chosen extinction level (1/m)."""
    soot_mg_m3 = extinction / config.VERIFIED_MASS_EXTINCTION_M2_PER_G * 1000.0
    scenario.module(module_id).species_mg_m3["soot"] = soot_mg_m3


def test_hazard_is_driven_by_real_thresholds():
    scenario = make_line_scenario(n_modules=2)
    # Just below the egress-impairment extinction: not yet hazardous.
    flood_with_smoke(
        scenario, "A1", config.ASSUMED_EGRESS_IMPAIR_EXTINCTION_PER_M * 0.5
    )
    assert not module_is_hazardous(scenario, "A1")

    flood_with_smoke(scenario, "A1", config.ASSUMED_EGRESS_IMPAIR_EXTINCTION_PER_M * 1.1)
    assert module_is_hazardous(scenario, "A1")


def test_smac_exceedance_makes_module_hazardous():
    scenario = make_line_scenario(n_modules=2)
    scenario.module("A1").species_mg_m3["HCN"] = config.VERIFIED_SMAC_1H_MG_M3["HCN"] * 1.1
    assert module_is_hazardous(scenario, "A1")


def test_exposure_and_dose_accumulate_and_states_transition():
    scenario = make_line_scenario(n_modules=3)
    crew = add_crew(scenario, "C1", "engineer", "A1")
    flood_with_smoke(scenario, "A1", 1.0)
    scenario.module("A1").species_mg_m3["CO"] = config.VERIFIED_SMAC_1H_MG_M3["CO"]

    update_crew(scenario, t=0.0, dt=30.0, response_seconds=60.0)
    assert crew.state == "EXPOSED"
    assert crew.hazard_exposure_seconds == 30.0
    # One full 1-hour-SMAC exposure for 30 s = 30/3600 of a dose.
    assert crew.smac_dose_fraction > 0

    for step in range(1, 10):
        update_crew(scenario, t=step * 30.0, dt=30.0, response_seconds=60.0)
    assert crew.state == "EVACUATED"
    assert crew.module_id == "A2"


def test_trapped_when_no_route_exists():
    scenario = make_line_scenario(n_modules=2, path_state="closed")
    crew = add_crew(scenario, "C1", "pilot", "A1")
    flood_with_smoke(scenario, "A1", 1.0)
    for step in range(0, 20):
        update_crew(scenario, t=step * 30.0, dt=30.0, response_seconds=30.0)
    assert crew.state == "TRAPPED"


def test_move_crew_explicit_order():
    scenario = make_line_scenario(n_modules=3)
    crew = add_crew(scenario, "C1", "medic", "A1")
    move_crew(scenario, "C1", "A3")
    assert crew.state == "EVACUATING"
    assert crew.route == ["A2", "A3"]

    blocked = make_line_scenario(n_modules=3, path_state="closed")
    crew2 = add_crew(blocked, "C1", "medic", "A1")
    move_crew(blocked, "C1", "A3")
    assert crew2.state == "TRAPPED"


def test_declared_escape_target_overrides_nearest_safe_module():
    scenario = make_line_scenario(n_modules=3)
    scenario.escape_target_connection_id = "c1"
    scenario.escape_from_module_id = "A2"
    scenario.escape_target_module_id = "A3"
    crew = add_crew(scenario, "C1", "engineer", "A1")
    flood_with_smoke(scenario, "A1", 1.0)

    for step in range(8):
        update_crew(scenario, t=step * 60.0, dt=60.0, response_seconds=0.0)

    assert crew.state == "EVACUATED"
    assert crew.module_id == "A3"


def test_refuge_capacity_reserves_seats_by_priority_and_denies_last_crew():
    scenario = make_line_scenario(n_modules=4)
    scenario.escape_target_connection_id = "c2"
    scenario.escape_from_module_id = "A3"
    scenario.escape_target_module_id = "A4"
    scenario.escape_capacity_people = 1
    engineer = add_crew(scenario, "C-engineer", "engineer", "A1")
    passenger = add_crew(scenario, "C-passenger", "passenger", "A1")

    for step in range(12):
        update_crew(scenario, t=step * 60.0, dt=60.0, response_seconds=0.0)

    assert engineer.state == "EVACUATED"
    assert engineer.module_id == "A4"
    assert passenger.state == "TRAPPED"
    assert passenger.module_id == "A3"
    assert passenger.escape_capacity_denied is True
    assert scenario.connection("c2").path_state == "closed"
    assert scenario.connection("c2").power_line_on is False
    assert scenario.connection("c2").water_line_on is False


def test_crew_walk_through_hatches_not_imv():
    scenario = make_line_scenario(n_modules=2, connection_type="imv", ventilation="on")
    crew = add_crew(scenario, "C1", "engineer", "A1")
    move_crew(scenario, "C1", "A2")
    assert crew.state == "TRAPPED"  # an IMV duct is not a crew passage


def test_no_fatality_constants_anywhere():
    assert not hasattr(config, "CREW_FATALITY_FACTOR")
    scenario = make_line_scenario(fire_in="A1")
    add_crew(scenario, "C1", "engineer", "A1")
    result = simulate(scenario, horizon=600, dt=30)
    assert result.summary["crew"]["C1"]["state"] in (
        "SAFE", "EXPOSED", "EVACUATING", "EVACUATED", "TRAPPED"
    )


# ── A-8 assumed criticality ──────────────────────────────────────────────────

def test_single_provider_function_flagged():
    scenario = make_line_scenario(n_modules=3)
    engineer = add_crew(scenario, "C2", "engineer", "A1")
    add_crew(scenario, "C1", "commander", "A2")

    flagged = {f["function"]: f for f in critical_functions(scenario.crew, [])}
    assert flagged["life_support_ops"]["flag"] == "SINGLE_PROVIDER"
    assert flagged["life_support_ops"]["providers"] == ["C2"]

    engineer.state = "TRAPPED"
    flagged = {
        f["function"]: f for f in critical_functions(scenario.crew, ["life_support"])
    }
    assert flagged["life_support_ops"]["flag"] == "NO_PROVIDER"


def test_crew_weight_rises_with_scarcity_and_facility_damage():
    scenario = make_line_scenario(n_modules=3)
    e1 = add_crew(scenario, "E1", "engineer", "A1")
    e2 = add_crew(scenario, "E2", "engineer", "A2")

    duo = crew_weight(e1, scenario.crew, damaged_facilities=[])
    e2.state = "TRAPPED"
    solo = crew_weight(e1, scenario.crew, damaged_facilities=[])
    assert solo > duo

    solo_with_damage = crew_weight(e1, scenario.crew, damaged_facilities=["power"])
    assert solo_with_damage > solo


# ── A-8.5 measured criticality ───────────────────────────────────────────────

def test_measured_criticality_reports_every_crew_member(demo):
    action = find_action(demo, "do_nothing")
    findings = measured_criticality(demo, action, horizon=600, dt=60)
    assert {f["crew_id"] for f in findings} == {"C1", "C2", "C3", "C4"}
    for f in findings:
        assert "measured_score" in f and "assumed_weight" in f
    # Sorted most-critical first.
    scores = [f["measured_score"] for f in findings]
    assert scores == sorted(scores, reverse=True)


def test_measured_criticality_needs_no_assumed_tables(demo):
    # The measured score comes from re-running the engine, so it is independent
    # of ASSUMED_FUNCTION_CRITICALITY.
    action = find_action(demo, "do_nothing")
    before = measured_criticality(demo, action, horizon=600, dt=60)
    original = dict(config.ASSUMED_FUNCTION_CRITICALITY)
    try:
        for key in config.ASSUMED_FUNCTION_CRITICALITY:
            config.ASSUMED_FUNCTION_CRITICALITY[key] = 0.5
        after = measured_criticality(demo, action, horizon=600, dt=60)
    finally:
        config.ASSUMED_FUNCTION_CRITICALITY.update(original)

    assert {f["crew_id"]: f["measured_score"] for f in before} == {
        f["crew_id"]: f["measured_score"] for f in after
    }
