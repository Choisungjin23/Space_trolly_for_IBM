from dataclasses import replace

from app.config import DEFAULT_CONFIG, build_config
from app.domain.scenario import build_initial_scenario
from app.simulation.actions import action_registry
from app.simulation.monte_carlo import run_monte_carlo, simulate_actions

RUNS = 200
SEED = 42


def test_same_seed_gives_identical_results():
    state = build_initial_scenario()
    a = simulate_actions(state, None, RUNS, seed=SEED)
    b = simulate_actions(state, None, RUNS, seed=SEED)
    assert a == b


def test_different_seeds_give_different_results():
    state = build_initial_scenario()
    a = simulate_actions(state, None, RUNS, seed=1)
    b = simulate_actions(state, None, RUNS, seed=2)
    assert a != b


def test_action_result_independent_of_other_actions_in_request():
    # Each action derives its own RNG from (seed, action_id), so its numbers
    # must not depend on which other actions were simulated alongside it.
    state = build_initial_scenario()
    alone = simulate_actions(state, ["isolate_m2"], RUNS, seed=SEED)[0]
    with_others = next(
        r for r in simulate_actions(state, None, RUNS, seed=SEED) if r["action_id"] == "isolate_m2"
    )
    assert alone == with_others


def test_metrics_stay_in_valid_ranges():
    state = build_initial_scenario()
    for result in simulate_actions(state, None, RUNS, seed=SEED):
        assert 0.0 <= result["expected_surviving_crew"] <= 4.0
        for key in (
            "crew_survival_pct",
            "fire_contained_pct",
            "critical_systems_pct",
            "mission_survival_pct",
        ):
            assert 0.0 <= result[key] <= 100.0, key
        assert 0.0 <= result["mean_final_fire_severity"] <= 1.0
        assert result["runs"] == RUNS


def test_metrics_stay_in_range_for_edited_settings():
    # The GUI can push parameters to their extremes; metrics must stay valid.
    for overrides in (
        {"propagation_factor": 5.0, "growth_rate": 1.0, "crew_fatality_factor": 1.0},
        {"propagation_factor": 0.0, "initial_fire_severity": 0.0},
        {"initial_fire_module": "M1", "crew_placement": {"C1": "M1", "C2": "M1", "C3": "M1", "C4": "M1"}},
        {"sim_steps": 1},
    ):
        cfg = build_config(overrides)
        state = build_initial_scenario(cfg)
        for result in simulate_actions(state, None, 100, seed=SEED, cfg=cfg):
            assert 0.0 <= result["expected_surviving_crew"] <= 4.0
            for key in (
                "crew_survival_pct",
                "fire_contained_pct",
                "critical_systems_pct",
                "mission_survival_pct",
            ):
                assert 0.0 <= result[key] <= 100.0, (overrides, key)


def test_zero_spread_probability_always_contains_fire():
    cfg = replace(DEFAULT_CONFIG, connection_hazard_probability=0.0)
    state = build_initial_scenario(cfg)
    action = action_registry(state)["do_nothing"]
    result = run_monte_carlo(state, action, RUNS, seed=SEED, cfg=cfg)
    assert result["fire_contained_pct"] == 100.0


def test_isolation_contains_at_least_as_well_as_doing_nothing():
    # Model-dependent sanity check at the default config: sealing the burning
    # module can only help containment.
    state = build_initial_scenario()
    registry = action_registry(state)
    isolate = run_monte_carlo(state, registry["isolate_m2"], 1000, seed=SEED)
    nothing = run_monte_carlo(state, registry["do_nothing"], 1000, seed=SEED)
    assert isolate["fire_contained_pct"] >= nothing["fire_contained_pct"]


def test_crew_placement_changes_outcomes():
    # Putting everyone in the burning module must not be safer than keeping
    # them away from it.
    away = build_config({"crew_placement": {"C1": "M5", "C2": "M5", "C3": "M5", "C4": "M5"}})
    inside = build_config({"crew_placement": {"C1": "M2", "C2": "M2", "C3": "M2", "C4": "M2"}})

    def survivors(cfg):
        state = build_initial_scenario(cfg)
        action = action_registry(state)["isolate_m2"]
        return run_monte_carlo(state, action, 300, seed=SEED, cfg=cfg)["expected_surviving_crew"]

    assert survivors(away) > survivors(inside)
