from dataclasses import replace
from random import Random

from app.config import DEFAULT_CONFIG
from app.domain.scenario import build_initial_scenario
from app.simulation.actions import action_registry
from app.simulation.propagation import step


def certain_spread_config(**overrides):
    """Config where spread always happens and nothing extinguishes."""
    base = replace(
        DEFAULT_CONFIG,
        propagation_factor=10.0,  # pushes every spread probability to the 1.0 clamp
        extinguish_prob=0.0,
        initial_fire_severity=1.0,
    )
    return replace(base, **overrides)


def burning_ids(state):
    return {m.id for m in state.modules.values() if m.fire_severity > 0}


def test_isolated_module_never_spreads_fire():
    cfg = certain_spread_config()
    base = build_initial_scenario(cfg)
    state = action_registry(base)["isolate_m2"].apply(base)
    rng = Random(1)
    for _ in range(50):
        step(state, rng, cfg)
    assert burning_ids(state) == {"M2"}


def test_closed_connection_blocks_spread():
    # Close M2-M3 and zero out every other connection's probability: M3 must
    # never ignite even though M2 burns at full severity.
    cfg = certain_spread_config()
    base = build_initial_scenario(cfg)
    state = action_registry(base)["close_m2_m3"].apply(base)
    for conn in state.connections:
        if {conn.source, conn.target} != {"M2", "M3"}:
            conn.hazard_spread_probability = 0.0
    rng = Random(1)
    for _ in range(50):
        step(state, rng, cfg)
    assert burning_ids(state) == {"M2"}


def test_spread_happens_over_active_connection_with_certain_probability():
    cfg = certain_spread_config()
    state = build_initial_scenario(cfg)
    step(state, Random(1), cfg)
    # M2's neighbors are M1 and M3; both must ignite on the first step.
    assert {"M1", "M3"} <= burning_ids(state)


def test_synchronous_update_newly_ignited_module_waits_a_step():
    # M2 burns; with certain spread M1/M3 ignite in step 1, but M4 (not adjacent
    # to M2) must not ignite until step 2.
    cfg = certain_spread_config()
    state = build_initial_scenario(cfg)
    rng = Random(1)
    step(state, rng, cfg)
    assert "M4" not in burning_ids(state)
    step(state, rng, cfg)
    assert "M4" in burning_ids(state)


def test_zero_propagation_factor_never_spreads():
    cfg = certain_spread_config(propagation_factor=0.0)
    state = build_initial_scenario(cfg)
    rng = Random(1)
    for _ in range(20):
        step(state, rng, cfg)
    assert burning_ids(state) == {"M2"}
