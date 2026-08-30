import pytest

from spacecraft_sim.actions import find_action, generate_actions
from spacecraft_sim.models import Connection
from tests.conftest import add_crew, make_line_scenario


def action_ids(scenario):
    return [a.id for a in generate_actions(scenario)]


def test_actions_follow_the_fire_no_hardcoded_ids():
    # Arbitrary ids, arbitrary size — the generator must adapt.
    scenario = make_line_scenario(n_modules=4, fire_in="A3")
    ids = action_ids(scenario)
    assert "do_nothing" in ids
    assert "isolate:A3" in ids
    # A3's hatches are c1 (A2-A3) and c2 (A3-A4).
    assert "close_hatch:c1" in ids
    assert "close_hatch:c2" in ids
    assert not any("m2" in i.lower() for i in ids)


def test_imv_actions_generated_for_ventilated_connection():
    scenario = make_line_scenario(
        n_modules=2, fire_in="A1", connection_type="imv", ventilation="on"
    )
    ids = action_ids(scenario)
    assert "shutdown_ventilation:c0" in ids
    assert "close_imv:c0" in ids


def test_evacuation_generated_for_crew_in_hazardous_module():
    scenario = make_line_scenario(n_modules=3, fire_in="A1")
    add_crew(scenario, "C9", "medic", "A1")
    ids = action_ids(scenario)
    assert "evacuate:C9:A2" in ids


def test_apply_never_mutates_input():
    scenario = make_line_scenario(n_modules=3, fire_in="A2")
    snapshot = scenario.model_copy(deep=True)
    for action in generate_actions(scenario):
        action.apply(scenario)
    assert scenario == snapshot


def test_isolate_closes_every_connection_of_the_module():
    scenario = make_line_scenario(n_modules=3, fire_in="A2")
    result = find_action(scenario, "isolate:A2").apply(scenario)
    assert result.module("A2").isolated is True
    for conn in result.connections_of("A2"):
        assert conn.path_state == "closed"
        assert conn.ventilation_state == "off"


def test_close_hatch_closes_exactly_one_connection():
    scenario = make_line_scenario(n_modules=3, fire_in="A2")
    result = find_action(scenario, "close_hatch:c0").apply(scenario)
    assert result.connection("c0").path_state == "closed"
    assert result.connection("c1").path_state == "open"


def test_power_down_cuts_power_in_module():
    scenario = make_line_scenario(n_modules=2, fire_in="A1")
    from tests.conftest import add_system

    add_system(scenario, "power", "A1", equipment_id="eq1")
    result = find_action(scenario, "power_down:A1").apply(scenario)
    assert all(not e.powered for e in result.equipment_in("A1"))


def test_unknown_action_raises_with_guidance():
    scenario = make_line_scenario(n_modules=2, fire_in="A1")
    with pytest.raises(KeyError):
        find_action(scenario, "isolate:NOPE")
