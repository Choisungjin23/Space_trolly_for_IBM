"""Monte Carlo driver: apply an action to copies of the initial state, run the
stochastic simulation N times, and aggregate outcome metrics.

Reproducibility: a run with the same (seed, action, runs, config, base state)
returns byte-identical metrics. Each action gets its own RNG derived from
`"{seed}:{action_id}"`, so an action's results do not depend on which other
actions were simulated in the same request. seed=None means nondeterministic.
"""

from random import Random

from app.config import DEFAULT_CONFIG, SimulationConfig
from app.domain.models import Spacecraft
from app.simulation.actions import Action, action_registry
from app.simulation.metrics import aggregate
from app.simulation.propagation import step


def run_monte_carlo(
    base_state: Spacecraft,
    action: Action,
    n_runs: int,
    seed: int | None = None,
    cfg: SimulationConfig = DEFAULT_CONFIG,
) -> dict[str, float | int]:
    rng = Random(f"{seed}:{action.id}") if seed is not None else Random()
    initial_burning = {m.id for m in base_state.modules.values() if m.fire_severity > 0}

    end_states: list[Spacecraft] = []
    for _ in range(n_runs):
        state = action.apply(base_state)
        for _ in range(cfg.sim_steps):
            step(state, rng, cfg)
        end_states.append(state)

    return aggregate(end_states, initial_burning, cfg)


def simulate_actions(
    base_state: Spacecraft,
    action_ids: list[str] | None,
    n_runs: int,
    seed: int | None = None,
    cfg: SimulationConfig = DEFAULT_CONFIG,
) -> list[dict]:
    """Simulate the given action ids (or every available action when None)."""
    registry = action_registry(base_state)
    ids = action_ids if action_ids is not None else list(registry)

    results = []
    for action_id in ids:
        action = registry[action_id]
        metrics = run_monte_carlo(base_state, action, n_runs, seed=seed, cfg=cfg)
        results.append({"action_id": action.id, "label": action.label, **metrics})
    return results
