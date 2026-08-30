"""Power, clean-air and regenerative-water network simulation.

The utility graph is deliberately separate from hazard ventilation. IMV flow
transports smoke; ``air_line_on`` transports clean life-support capacity.
"""

from __future__ import annotations

from collections import deque
import heapq
import math

from spacecraft_sim import config
from spacecraft_sim.models import Connection, Module, Scenario


def module_power_demand_w(scenario: Scenario, module: Module) -> float:
    """Current module load: base services + usable equipment + LS outputs."""
    demand = (
        module.base_power_consumption_w
        if module.base_power_consumption_w is not None
        else module.power_consumption_w
    )
    demand += sum(
        equipment.power_consumption_w
        for equipment in scenario.equipment_in(module.id)
        if equipment.powered and not equipment.damaged
    )
    if module.type == "life_support" and module.supplies_air:
        demand += config.ASSUMED_AIR_OUTPUT_POWER_W
    if module.type == "life_support" and module.supplies_water:
        demand += config.ASSUMED_WATER_OUTPUT_POWER_W
    return demand


def _other(conn: Connection, module_id: str) -> str:
    return conn.target if conn.source == module_id else conn.source


def _distances(scenario: Scenario, source_id: str, resource: str) -> dict[str, int]:
    distances = {source_id: 0}
    queue = deque([source_id])
    while queue:
        current = queue.popleft()
        for conn in scenario.connections_of(current):
            enabled = bool(getattr(conn, f"{resource}_line_on"))
            if resource == "air" and conn.type == "hatch":
                enabled = enabled and conn.path_state == "open"
            if not enabled:
                continue
            neighbor = _other(conn, current)
            if neighbor not in distances:
                distances[neighbor] = distances[current] + 1
                queue.append(neighbor)
    return distances


def _widest_air_connectivity(scenario: Scenario, source_id: str) -> dict[str, float]:
    """Maximum bottleneck connectivity available to each air-line target."""
    best = {source_id: 100.0}
    queue: list[tuple[float, str]] = [(-100.0, source_id)]
    while queue:
        negative_width, current = heapq.heappop(queue)
        width = -negative_width
        if width < best.get(current, 0.0):
            continue
        for connection in scenario.connections_of(current):
            if (
                connection.type != "hatch"
                or connection.path_state != "open"
                or not connection.air_line_on
            ):
                continue
            neighbor = _other(connection, current)
            candidate = min(width, connection.connectivity)
            if candidate > best.get(neighbor, -1.0):
                best[neighbor] = candidate
                heapq.heappush(queue, (-candidate, neighbor))
    return best


def _widest_power_factor(scenario: Scenario, source_id: str) -> dict[str, float]:
    """Best bottleneck power-transfer factor through enabled hatch lines."""
    best = {source_id: 1.0}
    queue: list[tuple[float, str]] = [(-1.0, source_id)]
    while queue:
        negative_width, current = heapq.heappop(queue)
        width = -negative_width
        if width < best.get(current, 0.0):
            continue
        for connection in scenario.connections_of(current):
            if connection.type != "hatch" or not connection.power_line_on:
                continue
            neighbor = _other(connection, current)
            candidate = min(width, connection.power_transfer_factor)
            if candidate > best.get(neighbor, -1.0):
                best[neighbor] = candidate
                heapq.heappush(queue, (-candidate, neighbor))
    return best


def _set_directions(
    scenario: Scenario, assignments: dict[str, str], resource: str
) -> None:
    field = "air_supply_direction" if resource == "air" else f"{resource}_flow_direction"
    for conn in scenario.connections:
        setattr(conn, field, "none")
    # Direction is reconstructed locally from level differences. This also
    # remains stable in cyclic graphs and never invents a circulating flow.
    level = {
        "power": lambda m: m.power_level_w,
        "air": lambda m: m.atmosphere.o2,
        "water": lambda m: m.water_stored_kg,
    }[resource]
    for conn in scenario.connections:
        if not getattr(conn, f"{resource}_line_on"):
            continue
        if resource == "air" and conn.type == "hatch" and conn.path_state != "open":
            continue
        a, b = scenario.module(conn.source), scenario.module(conn.target)
        if level(a) > level(b):
            setattr(conn, field, "source_to_target")
        elif level(b) > level(a):
            setattr(conn, field, "target_to_source")


def _update_power(scenario: Scenario) -> None:
    for module in scenario.modules:
        module.power_consumption_w = module_power_demand_w(scenario, module)
    sources = [m for m in scenario.modules if m.type == "power" and m.max_power_output_w > 0]
    if not sources:
        for module in scenario.modules:
            module.power_sufficient = module.power_level_w >= module.power_consumption_w
        _set_directions(scenario, {}, "power")
        return
    distances = {source.id: _distances(scenario, source.id, "power") for source in sources}
    transfer_factors = {
        source.id: _widest_power_factor(scenario, source.id) for source in sources
    }
    assigned: dict[str, str] = {}
    for module in scenario.modules:
        if module in sources:
            # Independent generators keep their own bus setpoint. A stronger
            # remote source must not overwrite a deliberately constrained
            # backup source before that backup serves its refuge zone.
            assigned[module.id] = module.id
            continue
        candidates = [
            (source.power_level_w - distances[source.id][module.id] * config.ASSUMED_POWER_LEVEL_DROP_W_PER_HOP, source)
            for source in sources
            if module.id in distances[source.id]
        ]
        if candidates:
            assigned[module.id] = max(candidates, key=lambda pair: pair[0])[1].id

    for source in sources:
        consumers = [m for m in scenario.modules if assigned.get(m.id) == source.id and m.id != source.id]
        # The first allocation policy is deliberately equal by connected
        # consumer, independent of role or declared demand. Demand determines
        # whether that equal allocation is sufficient for operation.
        equal_share_w = source.max_power_output_w / len(consumers) if consumers else 0.0
        source.power_sufficient = source.power_level_w >= source.power_consumption_w
        for module in consumers:
            hops = distances[source.id][module.id]
            nominal = max(0.0, source.power_level_w - hops * config.ASSUMED_POWER_LEVEL_DROP_W_PER_HOP)
            passage_limit = source.max_power_output_w * transfer_factors[source.id].get(
                module.id, 0.0
            )
            module.power_level_w = min(nominal, equal_share_w, passage_limit)
            module.power_sufficient = module.power_level_w >= module.power_consumption_w
    for module in scenario.modules:
        if module.id not in assigned:
            module.power_level_w = 0.0
            module.power_sufficient = module.power_consumption_w <= 0
    _set_directions(scenario, assigned, "power")


def _update_air(scenario: Scenario, minutes: float) -> None:
    sources = [m for m in scenario.modules if m.type == "life_support" and m.supplies_air]
    source_ids = {m.id for m in sources}
    for module in scenario.modules:
        if module.id in source_ids:
            # A functioning source maintains its configured setpoint; its
            # output capacity below is reserved for the connected consumers.
            continue
        module.atmosphere.o2 = max(
            0.0,
            module.atmosphere.o2
            - config.ASSUMED_AIR_CONSUMPTION_FRACTION_PER_MIN * minutes,
        )
    if not sources:
        return
    distances = {source.id: _distances(scenario, source.id, "air") for source in sources}
    path_connectivity = {
        source.id: _widest_air_connectivity(scenario, source.id) for source in sources
    }
    assignments: dict[str, str] = {}
    target_levels: dict[str, float] = {}
    for module in scenario.modules:
        candidates = [
            (source.atmosphere.o2 - distances[source.id][module.id] * config.ASSUMED_AIR_LEVEL_DROP_FRACTION_PER_HOP, source)
            for source in sources
            if module.id in distances[source.id]
        ]
        if not candidates:
            continue
        target, source = max(candidates, key=lambda pair: pair[0])
        assignments[module.id] = source.id
        target_levels[module.id] = max(0.0, target)
    for source in sources:
        targets = [
            m
            for m in scenario.modules
            if assignments.get(m.id) == source.id and m.id != source.id
        ]
        allowance = source.max_air_output_fraction_per_min * minutes
        share = allowance / len(targets) if targets else 0.0
        for module in targets:
            hatch_limit = (
                config.ASSUMED_HATCH_AIR_PERCENT_PER_MIN_AT_100
                / 100.0
                * path_connectivity[source.id].get(module.id, 0.0)
                / 100.0
                * minutes
            )
            # The network's steady-state pressure/concentration gradient is
            # visible even when a downstream module began above its reachable
            # setpoint. If it is below that setpoint, equal-share source output
            # can restore it, but never above the per-hop target.
            module.atmosphere.o2 = min(
                target_levels[module.id], module.atmosphere.o2 + min(share, hatch_limit)
            )
    _set_directions(scenario, assignments, "air")


def _update_water(scenario: Scenario, minutes: float) -> None:
    occupied = {m.id: 0 for m in scenario.modules}
    for crew in scenario.crew:
        if not crew.abandoned:
            occupied[crew.module_id] = occupied.get(crew.module_id, 0) + 1
    consumed: dict[str, float] = {}
    for module in scenario.modules:
        module.water_received_kg_last_step = 0.0
        module.water_demand_kg_per_min = occupied.get(module.id, 0) * config.ASSUMED_WATER_CONSUMPTION_KG_PER_CREW_MIN
        amount = module.water_demand_kg_per_min * minutes
        actual = min(module.water_stored_kg, amount)
        module.water_stored_kg -= actual
        consumed[module.id] = actual
        module.water_sufficient = actual + 1e-12 >= amount

    sources = [m for m in scenario.modules if m.type == "life_support" and m.supplies_water and m.max_water_output_kg_per_min > 0]
    if not sources:
        return
    distances = {source.id: _distances(scenario, source.id, "water") for source in sources}
    assignments: dict[str, str] = {}
    for module in scenario.modules:
        candidates = [(distances[s.id][module.id], s) for s in sources if module.id in distances[s.id]]
        if candidates:
            assignments[module.id] = min(candidates, key=lambda pair: pair[0])[1].id

    for source in sources:
        targets = [m for m in scenario.modules if assignments.get(m.id) == source.id and consumed[m.id] > 0 and m.id != source.id]
        available = min(source.water_stored_kg, source.max_water_output_kg_per_min * minutes)
        share = available / len(targets) if targets else 0.0
        for module in targets:
            hops = distances[source.id][module.id]
            loss = config.ASSUMED_WATER_TRANSFER_LOSS_KG_PER_MIN_PER_HOP * hops * minutes
            gross_needed = consumed[module.id] + loss
            gross = min(gross_needed, share, source.water_stored_kg)
            delivered = max(0.0, gross - loss)
            source.water_stored_kg -= gross
            module.water_stored_kg = min(module.water_capacity_kg, module.water_stored_kg + delivered)
            module.water_received_kg_last_step = delivered
            module.water_sufficient = delivered + 1e-12 >= consumed[module.id]

        # Wastewater/condensate recovery returns only consumed crew water;
        # transfer leakage is deliberately unrecoverable.
        recovered = sum(
            amount
            for module_id, amount in consumed.items()
            if assignments.get(module_id) == source.id
        ) * source.water_recovery_efficiency
        source.water_stored_kg = min(source.water_capacity_kg, source.water_stored_kg + recovered)
    _set_directions(scenario, assignments, "water")


def update_resources(scenario: Scenario, dt_seconds: float) -> None:
    """Advance every resource network by one engine timestep."""
    minutes = dt_seconds / 60.0
    _update_power(scenario)
    _update_air(scenario, minutes)
    _update_water(scenario, minutes)

    for crew in scenario.crew:
        if crew.abandoned:
            crew.survival_probability = 0.0
            crew.return_probability = 0.0
            continue
        module = scenario.module(crew.module_id)
        o2 = module.atmosphere.o2
        hypoxia_rate = 0.0
        if o2 < config.ASSUMED_SEVERE_HYPOXIA_O2_FRACTION:
            hypoxia_rate = config.ASSUMED_SEVERE_HYPOXIA_MORTALITY_RATE_PER_MIN
        elif o2 < config.ASSUMED_HYPOXIA_ONSET_O2_FRACTION:
            severity = (
                config.ASSUMED_HYPOXIA_ONSET_O2_FRACTION - o2
            ) / (
                config.ASSUMED_HYPOXIA_ONSET_O2_FRACTION
                - config.ASSUMED_SEVERE_HYPOXIA_O2_FRACTION
            )
            hypoxia_rate = config.ASSUMED_HYPOXIA_MORTALITY_RATE_PER_MIN * severity
        contaminant_rate = (
            module.worst_smac_fraction * config.ASSUMED_SMAC_MORTALITY_MULTIPLIER
        )
        reasons: list[str] = []
        if hypoxia_rate:
            reasons.append("low_air")
        if contaminant_rate:
            reasons.append("contaminants")
        power_rate = 0.0 if module.power_sufficient else config.ASSUMED_POWER_LOSS_MORTALITY_RATE_PER_MIN
        water_rate = 0.0 if module.water_sufficient else config.ASSUMED_WATER_LOSS_MORTALITY_RATE_PER_MIN
        if power_rate:
            reasons.append("insufficient_power")
        if water_rate:
            reasons.append("insufficient_water")
        fire_rate = 0.0
        if module.fire_state == "sustained":
            fire_rate = config.ASSUMED_SUSTAINED_FIRE_MORTALITY_RATE_PER_MIN
            reasons.append("sustained_fire_exposure")
        elif module.fire_state == "incipient":
            fire_rate = config.ASSUMED_INCIPIENT_FIRE_MORTALITY_RATE_PER_MIN
            reasons.append("incipient_fire_exposure")
        capacity_rate = 0.0
        if crew.escape_capacity_denied:
            capacity_rate = config.ASSUMED_REFUGE_CAPACITY_DENIAL_MORTALITY_RATE_PER_MIN
            reasons.append("refuge_capacity_exceeded")
        total_rate = (
            hypoxia_rate + contaminant_rate + power_rate + water_rate
            + fire_rate + capacity_rate
        )
        crew.survival_probability = max(
            0.0,
            min(
                1.0,
                crew.survival_probability
                * math.exp(-total_rate * minutes),
            ),
        )
        crew.resource_risk_reasons = reasons
        crew.estimated_survival_minutes = (
            max(
                0.0,
                math.log(
                    max(crew.survival_probability, 1e-12)
                    / config.ASSUMED_SURVIVAL_TIME_THRESHOLD
                )
                / total_rate,
            )
            if total_rate > 0
            and crew.survival_probability > config.ASSUMED_SURVIVAL_TIME_THRESHOLD
            else (0.0 if crew.survival_probability <= config.ASSUMED_SURVIVAL_TIME_THRESHOLD else None)
        )
