"""Outcome metrics aggregated over N Monte Carlo end states.

Exact definitions (N = number of runs, 4 crew, 3 critical systems):

- expected_surviving_crew: mean over runs of the number of crew alive at the
  end of the run. Range 0..4.
- crew_survival_pct: 100 * (total crew alive across all runs) / (4 * N).
  Equivalent to expected_surviving_crew / 4 * 100.
- fire_contained_pct: 100 * (runs where no module outside the initially
  burning set ever ignited) / N. Tracked via each module's `ever_ignited`
  flag during simulation.
- critical_systems_pct: 100 * (critical systems functional at end, summed
  over runs) / (3 * N). A system is functional iff it is not listed in its
  module's `failed_systems`. Critical systems come from config
  (life_support, power, propulsion).
- mission_survival_pct: 100 * (surviving runs) / N. A run survives iff at
  least one crew member is alive AND every system in
  cfg.mission_required_systems (life_support, power) is functional at end.
  Propulsion loss degrades but does not end the mission (PoC assumption,
  see config).
- mean_final_fire_severity: mean over runs of the maximum fire severity
  across all modules at the end of the run. Range 0..1.
"""

from app.config import SimulationConfig
from app.domain.models import Spacecraft


def aggregate(
    end_states: list[Spacecraft],
    initial_burning: set[str],
    cfg: SimulationConfig,
) -> dict[str, float | int]:
    n = len(end_states)
    total_crew_per_run = len(end_states[0].all_crew())
    n_critical = len(cfg.critical_systems)

    total_alive = 0
    contained_runs = 0
    critical_functional = 0
    surviving_runs = 0
    severity_sum = 0.0

    for state in end_states:
        alive = sum(1 for c in state.all_crew() if c.alive)
        total_alive += alive

        if all(
            not m.ever_ignited or m.id in initial_burning for m in state.modules.values()
        ):
            contained_runs += 1

        functional = {
            system
            for m in state.modules.values()
            for system in m.systems
            if system not in m.failed_systems
        }
        critical_functional += sum(1 for s in cfg.critical_systems if s in functional)

        crew_ok = alive > 0 or total_crew_per_run == 0
        if crew_ok and all(s in functional for s in cfg.mission_required_systems):
            surviving_runs += 1

        severity_sum += max(m.fire_severity for m in state.modules.values())

    # A config could place no crew at all; report 100% rather than dividing by zero.
    crew_survival_pct = (
        100.0 * total_alive / (total_crew_per_run * n) if total_crew_per_run else 100.0
    )

    return {
        "runs": n,
        "total_crew": total_crew_per_run,
        "expected_surviving_crew": round(total_alive / n, 3),
        "crew_survival_pct": round(crew_survival_pct, 2),
        "fire_contained_pct": round(100.0 * contained_runs / n, 2),
        "critical_systems_pct": round(100.0 * critical_functional / (n_critical * n), 2),
        "mission_survival_pct": round(100.0 * surviving_runs / n, 2),
        "mean_final_fire_severity": round(severity_sum / n, 3),
    }
