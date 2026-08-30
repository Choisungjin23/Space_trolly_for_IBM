"""Crew <-> system coupling: operating and repairing (A-8.2)."""

from spacecraft_sim import config
from spacecraft_sim.actions import find_action, generate_actions
from spacecraft_sim.capability import (
    available_providers,
    evaluate_systems,
    update_repairs,
    working_providers_in,
)
from spacecraft_sim.crew import measured_criticality
from spacecraft_sim.engine import counterfactual, simulate
from tests.conftest import add_crew, add_system, make_line_scenario

HORIZON = 1800.0
DT = 30.0


def scenario_with_operated_system(operator="power_ops", role="engineer"):
    scenario = make_line_scenario(n_modules=3)
    system = add_system(scenario, "power", "A2", equipment_id="eq1")
    system.operator_function = operator
    add_crew(scenario, "OP", role, "A1")
    return scenario


# ── Operating ────────────────────────────────────────────────────────────────

def test_system_with_an_operator_is_operational():
    scenario = scenario_with_operated_system()
    assert evaluate_systems(scenario)["power"] == "OPERATIONAL"


def test_losing_the_only_operator_makes_the_system_unavailable():
    scenario = scenario_with_operated_system()
    scenario.crew.clear()
    assert evaluate_systems(scenario)["power"] == "UNAVAILABLE"
    assert scenario.systems[0].unavailable_reason == "no_operator:power_ops"


def test_trapped_operator_cannot_run_the_system():
    scenario = scenario_with_operated_system()
    scenario.crew_member("OP").state = "TRAPPED"
    assert evaluate_systems(scenario)["power"] == "UNAVAILABLE"


def test_system_without_operator_function_needs_nobody():
    scenario = scenario_with_operated_system()
    scenario.systems[0].operator_function = None
    scenario.crew.clear()
    assert evaluate_systems(scenario)["power"] == "OPERATIONAL"


def test_unavailable_reason_distinguishes_causes():
    scenario = scenario_with_operated_system()
    scenario.module("A2").isolated = True
    evaluate_systems(scenario)
    assert scenario.systems[0].unavailable_reason == "module_isolated"

    scenario.module("A2").isolated = False
    scenario.equipment[0].powered = False
    evaluate_systems(scenario)
    assert scenario.systems[0].unavailable_reason == "equipment_powered_down"

    scenario.equipment[0].powered = True
    scenario.equipment[0].damaged = True
    evaluate_systems(scenario)
    assert scenario.systems[0].unavailable_reason == "equipment_damaged"


def test_provider_helpers():
    scenario = scenario_with_operated_system()
    assert [c.id for c in available_providers(scenario, "power_ops")] == ["OP"]
    assert working_providers_in(scenario, "power_ops", "A1")
    assert not working_providers_in(scenario, "power_ops", "A2")


# ── Repairing ────────────────────────────────────────────────────────────────

def damaged_scenario(repairer_module="A2"):
    scenario = make_line_scenario(n_modules=3)
    add_system(scenario, "power", "A2", equipment_id="eq1")
    scenario.equipment[0].damaged = True
    add_crew(scenario, "ENG", "engineer", repairer_module)
    return scenario


def test_repair_completes_with_a_repairer_on_site():
    scenario = damaged_scenario(repairer_module="A2")
    steps = int(config.ASSUMED_REPAIR_SECONDS / DT) + 1
    for _ in range(steps):
        update_repairs(scenario, DT)
    assert scenario.equipment[0].damaged is False


def test_repair_does_not_progress_without_a_repairer_present():
    scenario = damaged_scenario(repairer_module="A1")  # wrong module
    for _ in range(200):
        update_repairs(scenario, DT)
    assert scenario.equipment[0].damaged is True
    assert scenario.equipment[0].repair_progress_seconds == 0.0


def test_repair_does_not_progress_inside_a_hazardous_module():
    scenario = damaged_scenario(repairer_module="A2")
    scenario.module("A2").fire_state = "sustained"
    scenario.module("A2").source_profile_id = "STEADY_FABRIC_SPREAD"
    for _ in range(200):
        update_repairs(scenario, DT)
    assert scenario.equipment[0].damaged is True


def test_a_non_repair_role_cannot_repair():
    scenario = make_line_scenario(n_modules=3)
    add_system(scenario, "power", "A2", equipment_id="eq1")
    scenario.equipment[0].damaged = True
    add_crew(scenario, "MED", "medic", "A2")  # medic provides no repair function
    for _ in range(200):
        update_repairs(scenario, DT)
    assert scenario.equipment[0].damaged is True


def test_repaired_system_returns_to_operational():
    scenario = damaged_scenario(repairer_module="A2")
    scenario.systems[0].operator_function = None
    assert evaluate_systems(scenario)["power"] == "FAILED_EXPLICITLY"
    steps = int(config.ASSUMED_REPAIR_SECONDS / DT) + 1
    for _ in range(steps):
        update_repairs(scenario, DT)
    assert evaluate_systems(scenario)["power"] == "OPERATIONAL"


# ── Actions ──────────────────────────────────────────────────────────────────

def test_station_repairer_actions_are_generated_for_repair_capable_crew(demo):
    ids = [a.id for a in generate_actions(demo)]
    # C2 is the engineer (repair provider); C1/C3/C4 are not.
    assert "station_repairer:C2:M4" in ids
    assert not any(i.startswith("station_repairer:C1") for i in ids)
    assert not any(i.startswith("station_repairer:C3") for i in ids)


def test_station_repairer_moves_the_crew_member(demo):
    result = counterfactual(
        demo, find_action(demo, "station_repairer:C2:M4"), HORIZON, DT
    )
    assert result.summary["crew"]["C2"]["module"] == "M4"


def test_station_repairer_never_targets_a_hazardous_module(demo):
    ids = [a.id for a in generate_actions(demo)]
    assert "station_repairer:C2:M2" not in ids  # M2 is on fire


def test_station_repairer_is_offered_when_no_systems_are_declared(demo):
    """A scenario may build capabilities from equipment and declare no systems
    at all - Phase B does exactly that. update_repairs() still repairs that
    equipment on the default repair function, so deriving the offer from
    scenario.systems alone would make this action unreachable there."""
    demo.systems.clear()

    ids = [a.id for a in generate_actions(demo)]

    assert any(i.startswith("station_repairer:C2:") for i in ids)
    # Crew without the repair function are still excluded.
    assert not any(i.startswith("station_repairer:C1:") for i in ids)


def test_declared_systems_still_decide_the_repair_function(demo):
    """The fallback must not override an explicit declaration."""
    for system in demo.systems:
        system.repair_function = "nobody_has_this_function"

    ids = [a.id for a in generate_actions(demo)]

    assert not any(i.startswith("station_repairer:") for i in ids)


# ── Measured criticality now has signal ──────────────────────────────────────

def test_leave_one_out_now_separates_crew(demo):
    findings = measured_criticality(
        demo, find_action(demo, "do_nothing"), horizon=600, dt=60
    )
    scores = {f["crew_id"]: f["measured_score"] for f in findings}
    # The engineer operates life support and power; the pilot operates
    # propulsion and navigation. Both must now register.
    assert scores["C2"] > 0
    assert scores["C4"] > 0
    # Both are single points of failure for return in this scenario, so the
    # new expected-returnee objective correctly ties their marginal impact.
    assert scores["C2"] == scores["C4"]


def test_measured_and_assumed_rankings_agree_on_the_demo(demo):
    """Cross-check: the leave-one-out measurement and the assumed FMECA-style
    table should at least agree on the ordering, or the tables are suspect."""
    findings = measured_criticality(
        demo, find_action(demo, "do_nothing"), horizon=600, dt=60
    )
    ranked_measured = [f["crew_id"] for f in findings]
    ranked_assumed = [
        f["crew_id"]
        for f in sorted(findings, key=lambda x: x["assumed_weight"], reverse=True)
    ]
    assert ranked_measured[0] == ranked_assumed[0] == "C2"


def test_operator_loss_shows_up_in_the_summary(demo):
    reduced = demo.model_copy(deep=True)
    reduced.crew = [c for c in reduced.crew if c.id != "C2"]
    for module in reduced.modules:
        module.crew_ids = [cid for cid in module.crew_ids if cid != "C2"]

    result = simulate(reduced, horizon=600, dt=60)
    assert result.summary["systems"]["life_support"] == "UNAVAILABLE"
    assert result.summary["system_reasons"]["life_support"] == (
        "no_operator:life_support_ops"
    )
    assert result.summary["capabilities"]["HABITATION"] == "UNAVAILABLE"
