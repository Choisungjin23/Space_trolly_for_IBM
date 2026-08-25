import copy

from app.config import build_config
from app.domain.scenario import build_initial_scenario
from app.simulation.actions import action_registry, available_actions


def test_default_scenario_offers_expected_actions():
    # Fire in M2, whose neighbors are M1 and M3.
    state = build_initial_scenario()
    assert [a.id for a in available_actions(state)] == [
        "do_nothing",
        "isolate_m2",
        "close_m1_m2",
        "close_m2_m3",
    ]


def test_action_set_follows_the_fire():
    cfg = build_config({"initial_fire_module": "M4"})
    state = build_initial_scenario(cfg)
    ids = [a.id for a in available_actions(state)]
    # M4's neighbors are M3, M5 and M1.
    assert ids == ["do_nothing", "isolate_m4", "close_m3_m4", "close_m4_m5", "close_m1_m4"]
    assert "isolate_m2" not in ids


def test_actions_do_not_mutate_input_state():
    state = build_initial_scenario()
    for action in available_actions(state):
        snapshot = copy.deepcopy(state)
        action.apply(state)
        assert state == snapshot, f"{action.id} mutated its input state"


def test_do_nothing_returns_equal_copy():
    state = build_initial_scenario()
    result = action_registry(state)["do_nothing"].apply(state)
    assert result == state
    assert result is not state


def test_isolate_sets_only_isolation_flag():
    state = build_initial_scenario()
    result = action_registry(state)["isolate_m2"].apply(state)
    assert result.modules["M2"].isolated is True
    assert all(not m.isolated for mid, m in result.modules.items() if mid != "M2")
    assert all(c.active for c in result.connections)


def test_close_hatch_deactivates_exactly_that_connection():
    state = build_initial_scenario()
    result = action_registry(state)["close_m2_m3"].apply(state)
    for conn in result.connections:
        expected_active = {conn.source, conn.target} != {"M2", "M3"}
        assert conn.active is expected_active
    assert all(not m.isolated for m in result.modules.values())


def test_hatch_action_ids_are_order_independent():
    # The M1-M2 edge is stored as (M1, M2); reached from M2 it must still be
    # named close_m1_m2 rather than close_m2_m1.
    state = build_initial_scenario()
    assert "close_m1_m2" in action_registry(state)
    assert "close_m2_m1" not in action_registry(state)
