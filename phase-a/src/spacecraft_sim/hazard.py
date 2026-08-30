"""Hazard transport engine (A-5) as a real-unit mass balance.

Not "module i ignites module j with probability p", and no longer a
dimensionless load. For each tracked species s and module j:

    V_j * dC_s,j/dt = sum_i Q_ij * (C_s,i - C_s,j)   [ventilation exchange]
                    + Y_s * m_dot_j                   [local combustion source]
                    - Q_scrub * C_s,j                 [air revitalisation]

    V   module free volume            m^3
    C   species concentration         mg/m^3
    Q   volumetric flow               m^3/s
    m_dot fuel mass loss rate         mg/s
    Y   species yield                 mg/mg

Because the exchange term is (C_i - C_j) rather than a one-way source push,
smoke now propagates multi-hop on its own: a module that fills with smoke
becomes an upstream source for its own neighbours. That removes the single-hop
limitation the earlier dimensionless model had.

Directionality (PoC rules):
- imv:   transports only while ventilation is ON — one-way along
         airflow_direction, or both ways when no single direction is set
         (a circulation loop).
- hatch/leak: passive bidirectional exchange, unless an airflow direction is set.
- Closed paths, zero flow, and isolated endpoints transport nothing.
"""

from collections import defaultdict

from spacecraft_sim import config
from spacecraft_sim.models import Connection, Scenario
from spacecraft_sim.profiles import get_mass_loss_rate_mg_s, get_species_emission_mg_s


def active_directions(conn: Connection) -> list[tuple[str, str]]:
    """(i, j) module-id pairs this connection currently transports along."""
    if conn.path_state != "open":
        return []
    if conn.nominal_flow_m3_s() <= 0.0:
        return []

    if conn.type == "imv":
        if conn.ventilation_state != "on":
            return []
        if conn.airflow_direction == "source_to_target":
            return [(conn.source, conn.target)]
        if conn.airflow_direction == "target_to_source":
            return [(conn.target, conn.source)]
        # Ventilation running with no single direction set: a circulation loop
        # exchanges air both ways at the duct's flow rate.
        return [(conn.source, conn.target), (conn.target, conn.source)]

    # hatch / leak: passive
    if conn.airflow_direction == "source_to_target":
        return [(conn.source, conn.target)]
    if conn.airflow_direction == "target_to_source":
        return [(conn.target, conn.source)]
    return [(conn.source, conn.target), (conn.target, conn.source)]


def step_hazard(scenario: Scenario, t: float, dt: float) -> None:
    """One integration step of the species mass balance plus the thermal proxy."""
    modules = {m.id: m for m in scenario.modules}
    emissions = {m.id: get_species_emission_mg_s(m, t) for m in scenario.modules}

    # Net mass inflow per module per species, in mg/s.
    inflow: dict[tuple[str, str], float] = defaultdict(float)

    for module in scenario.modules:
        for species, rate in emissions[module.id].items():
            if rate:
                inflow[(module.id, species)] += rate

    for conn in scenario.connections:
        flow = conn.nominal_flow_m3_s()
        if conn.type == "hatch":
            flow *= conn.connectivity / 100.0
        for i, j in active_directions(conn):
            if modules[i].isolated or modules[j].isolated:
                continue
            for species in config.TRACKED_SPECIES:
                delta = modules[i].concentration(species) - modules[j].concentration(species)
                inflow[(j, species)] += flow * delta

    for module in scenario.modules:
        volume = max(module.volume_m3, 1e-6)
        for species in config.TRACKED_SPECIES:
            current = module.concentration(species)
            scrubbed = config.ASSUMED_SCRUB_FLOW_M3_S * current
            net = inflow[(module.id, species)] - scrubbed
            module.species_mg_m3[species] = max(0.0, current + dt * net / volume)

        # Thermal proxy (ASSUMED throughout — not a heat balance).
        fuel = get_mass_loss_rate_mg_s(module, t)
        ambient = config.ASSUMED_AMBIENT_TEMPERATURE_C
        rise = config.ASSUMED_THERMAL_RISE_C_PER_S_PER_MG_S * fuel
        cooling = config.ASSUMED_THERMAL_DECAY_PER_S * (module.temperature_c - ambient)
        module.temperature_c = max(ambient, module.temperature_c + dt * (rise - cooling))
