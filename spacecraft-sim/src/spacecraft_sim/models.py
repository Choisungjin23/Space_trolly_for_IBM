"""World-state data models (A-2, A-3), in real units.

The spacecraft is an arbitrary graph: any number of modules, typed connections,
crew, equipment, systems, and a capability map. Nothing in the engine assumes a
specific module count or specific ids.

Units: module free volume in m^3, species concentrations in mg/m^3, connection
flows in m^3/s, temperature in degrees C. Fire is a state plus a source
profile; there is no `fire_severity` scalar.
"""

from typing import Literal

from pydantic import BaseModel, Field

from spacecraft_sim import config


class Atmosphere(BaseModel):
    pressure: float = 101.3  # kPa
    o2: float = 0.21         # fraction 0..1


def _zero_species() -> dict[str, float]:
    return {species: 0.0 for species in config.TRACKED_SPECIES}


class Module(BaseModel):
    id: str
    name: str
    type: str = "generic"  # habitat | storage | life_support | power | propulsion | lab | ...
    volume_m3: float = config.ASSUMED_DEFAULT_MODULE_VOLUME_M3
    atmosphere: Atmosphere = Field(default_factory=Atmosphere)

    fire_state: Literal["non", "incipient", "sustained", "suppressed"] = "non"
    source_profile_id: str | None = None

    # Engine-updated state, all in real units.
    species_mg_m3: dict[str, float] = Field(default_factory=_zero_species)
    temperature_c: float = config.ASSUMED_AMBIENT_TEMPERATURE_C

    detected: bool = False
    detector_streak: int = 0  # consecutive readings above the alarm threshold
    isolated: bool = False    # sealed by an isolate action

    crew_ids: list[str] = Field(default_factory=list)
    equipment_ids: list[str] = Field(default_factory=list)

    def concentration(self, species: str) -> float:
        return self.species_mg_m3.get(species, 0.0)

    @property
    def extinction_per_m(self) -> float:
        """Smoke extinction coefficient (1/m) from soot mass concentration."""
        soot_g_m3 = self.concentration("soot") / 1000.0
        return config.VERIFIED_MASS_EXTINCTION_M2_PER_G * soot_g_m3

    def smac_fraction(self, species: str) -> float:
        """Current concentration as a fraction of the species' 1-hour SMAC."""
        limit = config.VERIFIED_SMAC_1H_MG_M3.get(species)
        if not limit:
            return 0.0
        return self.concentration(species) / limit

    @property
    def worst_smac_fraction(self) -> float:
        return max(
            (self.smac_fraction(s) for s in config.VERIFIED_SMAC_1H_MG_M3),
            default=0.0,
        )


class Connection(BaseModel):
    id: str
    source: str  # module id
    target: str  # module id
    type: Literal["hatch", "imv", "leak"]
    path_state: Literal["open", "closed", "unknown"] = "open"
    ventilation_state: Literal["on", "off"] = "off"
    airflow_direction: Literal["source_to_target", "target_to_source", "none"] = "none"
    # Volumetric flow in m^3/s. None = unknown; the engine falls back to the
    # per-type default and Monte Carlo samples the uncertainty.
    flow_m3_s: float | None = None

    def nominal_flow_m3_s(self) -> float:
        if self.flow_m3_s is not None:
            return self.flow_m3_s
        if self.type == "imv":
            return config.VERIFIED_IMV_FLOW_M3_S
        if self.type == "hatch":
            return config.ASSUMED_HATCH_EXCHANGE_M3_S
        return config.ASSUMED_LEAK_EXCHANGE_M3_S


class Crew(BaseModel):
    id: str
    name: str
    role: str  # commander | engineer | medic | pilot | scientist | free-form
    # Explicit function list. When set it overrides the role-based lookup in
    # config.ROLE_FUNCTIONS — scenario builders (Phase B) declare functions
    # directly instead of relying on Phase A role names.
    provides_functions: list[str] = Field(default_factory=list)
    module_id: str
    state: Literal["SAFE", "EXPOSED", "EVACUATING", "EVACUATED", "TRAPPED"] = "SAFE"
    hazard_exposure_seconds: float = 0.0
    # Cumulative dose as a fraction of a full 1-hour SMAC exposure, summed over
    # species: sum over t of (C/SMAC_1h) * dt / 3600. 1.0 means the crew member
    # has taken the equivalent of one hour at the 1-hour limit.
    smac_dose_fraction: float = 0.0
    # Engine bookkeeping (serializable, defaults empty):
    exposed_at_seconds: float | None = None
    route: list[str] = Field(default_factory=list)
    hop_eta_seconds: float = 0.0


class Equipment(BaseModel):
    id: str
    name: str
    module_id: str
    system: str            # which system this equipment contributes to
    powered: bool = True
    damaged: bool = False  # repairable, given a repair provider on site
    repair_progress_seconds: float = 0.0


class System(BaseModel):
    id: str
    name: str  # life_support | power | propulsion | gnc | navigation ...
    state: Literal[
        "OPERATIONAL", "EXPOSED_AT_RISK", "UNAVAILABLE", "FAILED_EXPLICITLY"
    ] = "OPERATIONAL"
    depends_on_modules: list[str] = Field(default_factory=list)
    depends_on_equipment: list[str] = Field(default_factory=list)

    # Crew coupling. None = the system needs nobody to run it.
    operator_function: str | None = None
    repair_function: str = "repair"

    # Why the system is not OPERATIONAL — diagnostic for downstream agents.
    unavailable_reason: str | None = None


class Scenario(BaseModel):
    """Serialization unit — Phase B's canvas will eventually emit this JSON."""

    modules: list[Module]
    connections: list[Connection]
    crew: list[Crew] = Field(default_factory=list)
    equipment: list[Equipment] = Field(default_factory=list)
    systems: list[System] = Field(default_factory=list)
    capabilities: dict[str, list[str]] = Field(default_factory=dict)
    mission_phase: str = "cruise"

    # ── Convenience lookups (no engine logic here) ──────────────────────────
    def module(self, module_id: str) -> Module:
        return next(m for m in self.modules if m.id == module_id)

    def crew_member(self, crew_id: str) -> Crew:
        return next(c for c in self.crew if c.id == crew_id)

    def connection(self, connection_id: str) -> Connection:
        return next(c for c in self.connections if c.id == connection_id)

    def connections_of(self, module_id: str) -> list[Connection]:
        return [c for c in self.connections if module_id in (c.source, c.target)]

    def equipment_in(self, module_id: str) -> list[Equipment]:
        return [e for e in self.equipment if e.module_id == module_id]

    def fire_modules(self) -> list[Module]:
        return [m for m in self.modules if m.fire_state in ("incipient", "sustained")]
