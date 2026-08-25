"""Fire source profiles (A-4), in real units.

There is deliberately no global GROWTH_RATE: the same fire behaves differently
depending on material, geometry, O2, pressure, and airflow (a Saffire finding),
so each source selects a profile. A profile's primary quantity is the fuel mass
loss rate in mg/s; species emission follows from the yield table in config.

Provenance: the SIBAL fabric area density behind STEADY_FABRIC_SPREAD is
verified (Saffire-I); the spread rate and burn width used to turn it into a
mass loss rate are assumed. See config for the full notice.
"""

from spacecraft_sim import config
from spacecraft_sim.models import Module


def get_mass_loss_rate_mg_s(module: Module, t: float) -> float:
    """Fuel consumption rate of `module`'s fire at time t (0 when not burning)."""
    if module.fire_state in ("non", "suppressed"):
        return 0.0

    profile = config.SOURCE_PROFILES[module.source_profile_id or "POC_UNKNOWN"]
    growth_factor = 1.0 + profile["growth_per_60s"] * (
        t / config.GROWTH_TIME_REFERENCE_SECONDS
    )
    rate = profile["mass_loss_rate_mg_s"] * max(0.0, growth_factor)

    if module.fire_state == "incipient":
        rate *= config.ASSUMED_INCIPIENT_RELEASE_FRACTION
    return rate


def yields_for(module: Module) -> dict[str, float]:
    """Product yields (mg species per mg fuel) for this module's fire.

    Yields are per PROFILE, not global: what a fire emits depends on what is
    burning. Cellulose and PMMA contain no nitrogen and so emit no HCN — that
    zero is stoichiometry, not an assumption.
    """
    profile = config.SOURCE_PROFILES[module.source_profile_id or "POC_UNKNOWN"]
    return profile.get("yields", {})


def get_species_emission_mg_s(module: Module, t: float) -> dict[str, float]:
    """Per-species emission (mg/s) = fuel mass loss rate x that fuel's yield."""
    fuel = get_mass_loss_rate_mg_s(module, t)
    if fuel <= 0.0:
        return {species: 0.0 for species in config.TRACKED_SPECIES}
    yields = yields_for(module)
    return {
        species: fuel * yields.get(species, 0.0)
        for species in config.TRACKED_SPECIES
    }


def is_extinguished(module: Module, t: float) -> bool:
    """True when a decaying profile's mass loss has ramped down to zero."""
    if module.fire_state not in ("incipient", "sustained"):
        return False
    profile = config.SOURCE_PROFILES[module.source_profile_id or "POC_UNKNOWN"]
    return profile["growth_per_60s"] < 0 and get_mass_loss_rate_mg_s(module, t) <= 0.0
