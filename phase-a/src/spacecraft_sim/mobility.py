"""Dynamic hatch connectivity, throughput budgets and passage feedback."""

from __future__ import annotations

from spacecraft_sim import config
from spacecraft_sim.models import Connection, Scenario


def connection_between(scenario: Scenario, a: str, b: str) -> Connection | None:
    for connection in scenario.connections_of(a):
        if connection.type != "hatch" or connection.path_state != "open":
            continue
        if connection.connectivity <= config.ASSUMED_HATCH_IMPASSABLE_CONNECTIVITY:
            connection.crew_passage_credit = 0.0
            continue
        if {connection.source, connection.target} == {a, b}:
            return connection
    return None


def _module_disruption(scenario: Scenario, module_id: str) -> tuple[float, str]:
    module = scenario.module(module_id)
    if module.fire_state == "sustained":
        return config.ASSUMED_FIRE_CONNECTIVITY_LOSS_PER_MIN, "fire"
    if module.fire_state == "incipient":
        return config.ASSUMED_INCIPIENT_CONNECTIVITY_LOSS_PER_MIN, "incipient_fire"
    if module.worst_smac_fraction >= 1.0 or (
        module.extinction_per_m >= config.ASSUMED_EGRESS_IMPAIR_EXTINCTION_PER_M
    ):
        return config.ASSUMED_SMOKE_CONNECTIVITY_LOSS_PER_MIN, "smoke"
    if module.disruption_level > 0:
        return (
            config.ASSUMED_FIRE_CONNECTIVITY_LOSS_PER_MIN * module.disruption_level,
            "other_disaster",
        )
    return 0.0, "nominal"


def update_connectivity(scenario: Scenario, dt_seconds: float) -> None:
    """Degrade hazard-adjacent hatches; passage capacity is replenished separately."""
    minutes = dt_seconds / 60.0
    for connection in scenario.connections:
        if connection.type != "hatch":
            continue
        source_loss, _ = _module_disruption(scenario, connection.source)
        target_loss, _ = _module_disruption(scenario, connection.target)
        loss_per_min = max(source_loss, target_loss)
        source_air = scenario.module(connection.source).atmosphere.o2
        target_air = scenario.module(connection.target).atmosphere.o2
        air_ratio = max(
            0.0,
            min(1.0, min(source_air, target_air) / config.ASSUMED_NORMAL_O2_FRACTION),
        )
        if loss_per_min > 0:
            connection.connectivity = max(
                config.ASSUMED_MIN_DAMAGED_HATCH_CONNECTIVITY,
                connection.connectivity - loss_per_min * (2.0 - air_ratio) * minutes,
            )
        else:
            connection.connectivity = min(
                connection.base_connectivity, connection.connectivity
            )
        # Connectivity represents inverse air/movement resistance, so depleted
        # fresh air is also a hard ceiling on the connection's usable value.
        connection.connectivity = min(
            connection.connectivity,
            max(1.0, connection.base_connectivity * air_ratio),
        )


def replenish_passage_credit(scenario: Scenario, dt_seconds: float) -> None:
    """Accumulate fractional hatch capacity until a whole passage is possible."""
    minutes = dt_seconds / 60.0
    for connection in scenario.connections:
        if connection.type != "hatch" or connection.path_state != "open":
            continue
        if connection.connectivity <= config.ASSUMED_HATCH_IMPASSABLE_CONNECTIVITY:
            connection.crew_passage_credit = 0.0
            continue
        connection.crew_passage_credit += connection.crew_throughput_per_min * minutes
        connection.crew_passage_credit = min(
            connection.crew_passage_credit,
            max(1.0, connection.crew_throughput_per_min),
        )


def consume_passage(
    scenario: Scenario,
    connection: Connection,
    destination_module_id: str,
    passage_units: float = 1.0,
    *,
    equipment: bool = False,
) -> bool:
    """Consume throughput and apply the air/connectivity negative feedback."""
    if connection.crew_passage_credit + 1e-12 < passage_units:
        return False
    connection.crew_passage_credit -= passage_units
    resistance_factor = 100.0 / max(connection.connectivity, 1.0)
    if equipment:
        connectivity_loss = (
            config.ASSUMED_CONNECTIVITY_LOSS_PER_EQUIPMENT_UNIT
            * passage_units
            * resistance_factor
        )
        air_loss = (
            config.ASSUMED_FRESH_AIR_LOSS_FRACTION_PER_EQUIPMENT_UNIT
            * passage_units
            * resistance_factor
        )
        connection.total_equipment_passage_units += passage_units
    else:
        connectivity_loss = (
            config.ASSUMED_CONNECTIVITY_LOSS_PER_CREW_PASSAGE * resistance_factor
        )
        air_loss = (
            config.ASSUMED_FRESH_AIR_LOSS_FRACTION_PER_CREW_PASSAGE
            * resistance_factor
        )
        connection.total_crew_passages += 1
    connection.connectivity = max(
        config.ASSUMED_MIN_DAMAGED_HATCH_CONNECTIVITY,
        connection.connectivity - connectivity_loss,
    )
    destination = scenario.module(destination_module_id)
    destination.atmosphere.o2 = max(0.0, destination.atmosphere.o2 - air_loss)
    return True
