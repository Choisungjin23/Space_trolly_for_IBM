"""Crew state tracking (A-6) and criticality (A-8).

A-6: no fatality odds. Crew move through states
    SAFE -> EXPOSED -> EVACUATING -> EVACUATED | TRAPPED
and accumulate exposure time plus a cumulative SMAC dose fraction. Nothing here
computes P(death).

A module is hazardous when it is burning, when any species exceeds its 1-hour
SMAC (JSC 20584 Rev C), or when smoke extinction passes the assumed egress
impairment level. Note the real-unit consequence: with ventilation running, a
small fire's CO plateaus well below its SMAC, so the binding hazard is usually
obscuration, not toxicity.

A-8: `crew_weight` returns how irreplaceable a crew member's FUNCTIONS are in
the current situation (FMECA-inspired), never a value of their life.
`measured_criticality` bypasses the assumed tables entirely by measuring what
removing each crew member does to the outcome.
"""

from collections import deque

from spacecraft_sim import config
from spacecraft_sim.models import Crew, Scenario


# ── Movement graph (crew walk through open hatches only; IMV ducts are not
#    crew passages, leaks even less so) ──────────────────────────────────────

def _traversable(scenario: Scenario, module_id: str) -> list[str]:
    modules = {m.id: m for m in scenario.modules}
    out = []
    for conn in scenario.connections_of(module_id):
        if conn.type != "hatch" or conn.path_state != "open":
            continue
        other = conn.target if conn.source == module_id else conn.source
        if modules[module_id].isolated or modules[other].isolated:
            continue
        out.append(other)
    return out


def module_is_hazardous(scenario: Scenario, module_id: str) -> bool:
    module = scenario.module(module_id)
    if module.fire_state in ("incipient", "sustained"):
        return True
    if module.worst_smac_fraction >= 1.0:
        return True
    return module.extinction_per_m >= config.ASSUMED_EGRESS_IMPAIR_EXTINCTION_PER_M


def find_route(
    scenario: Scenario, start: str, target: str | None = None
) -> list[str] | None:
    """BFS through open hatches. With a target: route to it. Without: route to
    the nearest non-hazardous, non-isolated module. Returns hops (start
    excluded) or None when unreachable."""
    seen = {start}
    queue: deque[tuple[str, list[str]]] = deque([(start, [])])
    while queue:
        current, path = queue.popleft()
        goal_reached = (
            current == target
            if target is not None
            else (current != start and not module_is_hazardous(scenario, current))
        )
        if goal_reached:
            return path
        for neighbor in _traversable(scenario, current):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    return None


def move_crew(scenario: Scenario, crew_id: str, target_module: str) -> None:
    """Explicit evacuation order: plan a route now; TRAPPED when none exists."""
    crew = scenario.crew_member(crew_id)
    if crew.module_id == target_module:
        return
    route = find_route(scenario, crew.module_id, target_module)
    if route is None:
        crew.state = "TRAPPED"
        crew.route = []
        return
    crew.state = "EVACUATING"
    crew.route = route
    crew.hop_eta_seconds = config.ASSUMED_CREW_MOVE_SECONDS_PER_HOP


def _accumulate_dose(crew: Crew, scenario: Scenario, dt: float) -> None:
    """Add this step's fraction-of-1-hour-SMAC dose, summed over species."""
    module = scenario.module(crew.module_id)
    per_hour = sum(
        module.smac_fraction(species) for species in config.VERIFIED_SMAC_1H_MG_M3
    )
    crew.smac_dose_fraction += per_hour * dt / 3600.0


def update_crew(scenario: Scenario, t: float, dt: float, response_seconds: float) -> None:
    """One step of exposure accumulation, state transitions, and movement."""
    for crew in scenario.crew:
        hazardous_here = module_is_hazardous(scenario, crew.module_id)

        if crew.state != "EVACUATED":
            _accumulate_dose(crew, scenario, dt)
        if hazardous_here and crew.state != "EVACUATED":
            crew.hazard_exposure_seconds += dt

        if crew.state == "SAFE":
            if hazardous_here:
                crew.state = "EXPOSED"
                crew.exposed_at_seconds = t

        elif crew.state == "EXPOSED":
            if crew.exposed_at_seconds is not None and (
                t - crew.exposed_at_seconds >= response_seconds
            ):
                route = find_route(scenario, crew.module_id)
                if route is None:
                    crew.state = "TRAPPED"
                else:
                    crew.state = "EVACUATING"
                    crew.route = route
                    crew.hop_eta_seconds = config.ASSUMED_CREW_MOVE_SECONDS_PER_HOP

        elif crew.state == "EVACUATING":
            if not crew.route:
                crew.state = "EVACUATED" if not hazardous_here else "EXPOSED"
                continue
            crew.hop_eta_seconds -= dt
            if crew.hop_eta_seconds <= 0:
                next_module = crew.route[0]
                if next_module in _traversable(scenario, crew.module_id):
                    current_module = scenario.module(crew.module_id)
                    current_module.crew_ids = [
                        c for c in current_module.crew_ids if c != crew.id
                    ]
                    crew.module_id = next_module
                    scenario.module(next_module).crew_ids.append(crew.id)
                    crew.route = crew.route[1:]
                    crew.hop_eta_seconds = config.ASSUMED_CREW_MOVE_SECONDS_PER_HOP
                    if not crew.route:
                        if module_is_hazardous(scenario, crew.module_id):
                            crew.state = "EXPOSED"
                            crew.exposed_at_seconds = t
                        else:
                            crew.state = "EVACUATED"
                else:
                    replan = find_route(scenario, crew.module_id)
                    if replan is None:
                        crew.state = "TRAPPED"
                        crew.route = []
                    else:
                        crew.route = replan
                        crew.hop_eta_seconds = config.ASSUMED_CREW_MOVE_SECONDS_PER_HOP

        elif crew.state == "EVACUATED" and hazardous_here:
            crew.state = "EXPOSED"
            crew.exposed_at_seconds = t


# ── A-8: rule-based (assumed) criticality ────────────────────────────────────

def functions_of(crew: Crew) -> set[str]:
    """The functions a crew member provides: their explicit list when declared,
    otherwise the role-based lookup."""
    if crew.provides_functions:
        return set(crew.provides_functions)
    return config.ROLE_FUNCTIONS.get(crew.role, set())


def _available(crew: Crew) -> bool:
    """A trapped crew member cannot currently provide their functions."""
    return crew.state != "TRAPPED"


def crew_weight(
    crew: Crew, alive_crew: list[Crew], damaged_facilities: list[str]
) -> float:
    """How irreplaceable this crew member's functions are RIGHT NOW.

    Not a value of the person's life: weight = f(function criticality,
    redundancy among available crew, facility-driven demand). Built from
    ASSUMED_ tables — see config's provenance notice.
    """
    total = 0.0
    for func in functions_of(crew):
        base = config.ASSUMED_FUNCTION_CRITICALITY.get(
            func, config.ASSUMED_DEFAULT_FUNCTION_CRITICALITY
        )
        providers = sum(
            1 for c in alive_crew if _available(c) and func in functions_of(c)
        )
        redundancy_factor = 1.0 / max(providers, 1)  # single point -> spike
        demand = 1.0
        for facility in damaged_facilities:
            demand *= config.ASSUMED_FACILITY_FUNCTION_DEMAND.get(facility, {}).get(
                func, 1.0
            )
        total += base * redundancy_factor * demand
    return total


def critical_functions(
    alive_crew: list[Crew], damaged_facilities: list[str]
) -> list[dict]:
    """Flag every function whose available-provider count is 0 or 1.

    This factual output ("life_support_ops has a single provider: C2") is what
    the engine hands to downstream agents — not a ranking of people.
    """
    all_functions = {
        func for role_funcs in config.ROLE_FUNCTIONS.values() for func in role_funcs
    }
    for crew in alive_crew:
        all_functions |= functions_of(crew)
    findings = []
    for func in sorted(all_functions):
        providers = [
            c.id for c in alive_crew if _available(c) and func in functions_of(c)
        ]
        if len(providers) == 1:
            findings.append(
                {"function": func, "flag": "SINGLE_PROVIDER", "providers": providers}
            )
        elif len(providers) == 0 and func in {
            f
            for fac in damaged_facilities
            for f in config.ASSUMED_FACILITY_FUNCTION_DEMAND.get(fac, {})
        }:
            findings.append({"function": func, "flag": "NO_PROVIDER", "providers": []})
    return findings


# ── A-8.5: measured (leave-one-out) criticality ──────────────────────────────

def measured_criticality(
    scenario: Scenario,
    action,
    horizon: float | None = None,
    dt: float | None = None,
) -> list[dict]:
    """Measure each crew member's criticality instead of assuming it.

    Removes one crew member at a time, re-runs the simulation, and reports how
    much the outcome degrades. Needs no external data and cross-checks the
    ASSUMED_ tables: `crew_weight` is theoretical criticality, this is what the
    simulator actually measures.

    Score = (capabilities retained with the member) - (retained without them),
    so a positive score means the crew member's presence protects capability.
    """
    from spacecraft_sim.engine import counterfactual  # local: avoids a cycle

    def capability_score(sc: Scenario) -> float:
        result = counterfactual(sc, action, horizon=horizon, dt=dt)
        caps = result.summary["capabilities"]
        weights = {"AVAILABLE": 1.0, "AT_RISK": 0.5, "UNAVAILABLE": 0.0}
        if not caps:
            return 0.0
        return sum(weights[state] for state in caps.values()) / len(caps)

    baseline = capability_score(scenario)

    findings = []
    for crew in scenario.crew:
        reduced = scenario.model_copy(deep=True)
        reduced.crew = [c for c in reduced.crew if c.id != crew.id]
        for module in reduced.modules:
            module.crew_ids = [cid for cid in module.crew_ids if cid != crew.id]
        findings.append(
            {
                "crew_id": crew.id,
                "role": crew.role,
                "measured_score": round(baseline - capability_score(reduced), 4),
                "assumed_weight": round(
                    crew_weight(crew, scenario.crew, damaged_facilities=[]), 4
                ),
            }
        )

    findings.sort(key=lambda f: f["measured_score"], reverse=True)
    return findings
