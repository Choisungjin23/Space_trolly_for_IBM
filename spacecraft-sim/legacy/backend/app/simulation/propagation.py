"""One discrete time step of the stochastic fire model.

PoC assumption notice: this is a simplified, configurable toy model chosen for
demonstrable behavior — NOT a physically validated fire model. All parameters
live in app/config.py so they can be replaced with evidence-based values later.

Step order (all randomness drawn from the single passed-in `rng`, and modules
always iterated in their fixed dict insertion order, so a given seed replays
identically):

1. Fire spread — for every active connection whose endpoints are both
   non-isolated and where exactly one side burns:
       P(spread i -> j) = fire_severity_i * hazard_spread_probability_ij * propagation_factor
   Spread decisions use the severities from the START of the step (synchronous
   update): a module ignited this step cannot spread or grow until next step.
2. Fire growth — every module burning at the start of the step gains
   `growth_rate` severity, capped at 1.0.
3. Burnout/suppression — each burning module has `extinguish_prob` chance of
   losing `extinguish_amount` severity (floor 0).
4. System damage — a module at/above `system_damage_threshold` severity rolls
   `system_failure_prob` per intact onboard system per step; failed systems
   stay failed.
5. Crew hazard — each living crew member in a module at/above
   `crew_hazard_threshold`: if the module is not isolated and has an active
   connection to a non-burning, non-isolated module, everyone evacuates there
   (deterministically, to the first eligible neighbor in connection order).
   Otherwise each member dies that step with probability
   `fire_severity * crew_fatality_factor`.
"""

from random import Random

from app.config import SimulationConfig
from app.domain.models import Spacecraft


def step(state: Spacecraft, rng: Random, cfg: SimulationConfig) -> None:
    modules = state.modules

    # Snapshot of who is burning at the start of the step (synchronous update).
    burning_at_start = {m.id: m.fire_severity for m in modules.values() if m.fire_severity > 0}

    # 1. Fire spread.
    to_ignite: set[str] = set()
    for conn in state.connections:
        if not conn.active:
            continue
        src, tgt = modules[conn.source], modules[conn.target]
        if src.isolated or tgt.isolated:
            continue
        for burning, other in ((src, tgt), (tgt, src)):
            if burning.id in burning_at_start and other.id not in burning_at_start:
                p = burning_at_start[burning.id] * conn.hazard_spread_probability * cfg.propagation_factor
                p = min(1.0, max(0.0, p))
                if rng.random() < p:
                    to_ignite.add(other.id)

    for module_id in sorted(to_ignite):
        module = modules[module_id]
        module.fire_severity = max(module.fire_severity, cfg.ignition_severity)
        module.ever_ignited = True

    # 2. Fire growth (only modules that were burning at the start of the step).
    for module_id in burning_at_start:
        module = modules[module_id]
        module.fire_severity = min(1.0, module.fire_severity + cfg.growth_rate)

    # 3. Burnout/suppression.
    for module in modules.values():
        if module.fire_severity > 0 and rng.random() < cfg.extinguish_prob:
            module.fire_severity = max(0.0, module.fire_severity - cfg.extinguish_amount)

    # 4. System damage.
    for module in modules.values():
        if module.fire_severity >= cfg.system_damage_threshold:
            for system in module.systems:
                if system not in module.failed_systems and rng.random() < cfg.system_failure_prob:
                    module.failed_systems.append(system)

    # 5. Crew hazard.
    for module in list(modules.values()):
        if module.fire_severity < cfg.crew_hazard_threshold:
            continue
        living = [c for c in module.crew if c.alive]
        if not living:
            continue

        evacuation_target = None
        if not module.isolated:
            for neighbor_id in state.neighbors(module.id):
                neighbor = modules[neighbor_id]
                if neighbor.fire_severity == 0 and not neighbor.isolated:
                    evacuation_target = neighbor
                    break

        if evacuation_target is not None:
            for crew_member in living:
                module.crew.remove(crew_member)
                evacuation_target.crew.append(crew_member)
        else:
            for crew_member in living:
                if rng.random() < module.fire_severity * cfg.crew_fatality_factor:
                    crew_member.alive = False
