"""World-state data models (A-2, A-3), in real units.

The spacecraft is an arbitrary graph: any number of modules, typed connections,
crew, equipment, systems, and a capability map. Nothing in the engine assumes a
specific module count or specific ids.

Units: module free volume in m^3, species concentrations in mg/m^3, connection
flows in m^3/s, temperature in degrees C. Fire is a state plus a source
profile; there is no `fire_severity` scalar.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from spacecraft_sim import config


class Atmosphere(BaseModel):
    pressure: float = 101.3  # kPa
    o2: float = config.ASSUMED_NORMAL_O2_FRACTION  # fraction 0..1


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
    # 0..1 hook for non-fire disasters introduced by future scenarios.
    disruption_level: float = Field(default=0.0, ge=0.0, le=1.0)
    electrical_short: bool = False

    crew_ids: list[str] = Field(default_factory=list)
    equipment_ids: list[str] = Field(default_factory=list)

    # Utility state and demand. Power and water sources use the same current
    # level/storage fields as consumers plus the source-specific capacities.
    power_level_w: float = config.ASSUMED_DEFAULT_POWER_LEVEL_W
    power_consumption_w: float = config.ASSUMED_DEFAULT_POWER_CONSUMPTION_W
    base_power_consumption_w: float | None = None
    max_power_output_w: float = 0.0
    power_sufficient: bool = True

    water_stored_kg: float = 0.0
    water_capacity_kg: float = 0.0
    water_received_kg_last_step: float = 0.0
    water_demand_kg_per_min: float = 0.0
    water_sufficient: bool = True

    supplies_air: bool = False
    supplies_water: bool = False
    max_air_output_fraction_per_min: float = 0.0
    max_water_output_kg_per_min: float = 0.0
    water_recovery_efficiency: float = config.VERIFIED_ISS_WATER_RECOVERY_EFFICIENCY

    @model_validator(mode="after")
    def remember_base_power_demand(self) -> "Module":
        if self.base_power_consumption_w is None:
            self.base_power_consumption_w = self.power_consumption_w
        return self

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
    # Utility lines are independent. Closing a hatch blocks clean-air supply;
    # power and water remain controlled by their own switches.
    power_line_on: bool = True
    air_line_on: bool = True
    water_line_on: bool = True
    power_flow_direction: Literal["source_to_target", "target_to_source", "none"] = "none"
    air_supply_direction: Literal["source_to_target", "target_to_source", "none"] = "none"
    water_flow_direction: Literal["source_to_target", "target_to_source", "none"] = "none"
    base_connectivity: float = Field(
        default=config.ASSUMED_NOMINAL_HATCH_CONNECTIVITY, ge=0.0, le=100.0
    )
    connectivity: float = Field(
        default=config.ASSUMED_NOMINAL_HATCH_CONNECTIVITY, ge=0.0, le=100.0
    )
    crew_passage_credit: float = Field(default=0.0, ge=0.0)
    total_crew_passages: int = 0
    total_equipment_passage_units: float = 0.0
    power_transfer_factor: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def crew_throughput_per_min(self) -> float:
        if self.type != "hatch" or self.path_state != "open":
            return 0.0
        return config.ASSUMED_HATCH_CREW_PER_MIN_AT_100 * self.connectivity / 100.0

    @property
    def air_throughput_percent_per_min(self) -> float:
        if self.type != "hatch" or self.path_state != "open":
            return 0.0
        return config.ASSUMED_HATCH_AIR_PERCENT_PER_MIN_AT_100 * self.connectivity / 100.0

    @model_validator(mode="after")
    def utility_lines_require_hatch(self) -> "Connection":
        if self.type != "hatch":
            self.power_line_on = False
            self.air_line_on = False
            self.water_line_on = False
        return self

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
    survival_probability: float = 1.0
    return_probability: float = 1.0
    estimated_survival_minutes: float | None = None
    resource_risk_reasons: list[str] = Field(default_factory=list)
    abandoned: bool = False
    evacuation_priority_score: float = 0.0
    evacuation_priority_rank: int | None = None
    waiting_for_connection_id: str | None = None
    priority_reasons: list[str] = Field(default_factory=list)
    escape_capacity_denied: bool = False
    escape_seat_reserved: bool | None = None


class Equipment(BaseModel):
    id: str
    name: str
    module_id: str
    system: str            # which system this equipment contributes to
    powered: bool = True
    damaged: bool = False  # repairable, given a repair provider on site
    repair_progress_seconds: float = 0.0
    # Legacy/direct Phase A scenarios default to zero for compatibility;
    # Phase B assigns an explicit type-appropriate value to every item.
    power_consumption_w: float = 0.0
    portable: bool = False
    passage_units: float = Field(default=1.0, gt=0.0)
    evacuation_priority_score: float = 0.0
    evacuation_priority_rank: int | None = None
    priority_reasons: list[str] = Field(default_factory=list)
    evacuated: bool = False
    evacuation_route: list[str] = Field(default_factory=list)


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
    repair_function: str = config.DEFAULT_REPAIR_FUNCTION

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
    escape_target_connection_id: str | None = None
    escape_from_module_id: str | None = None
    escape_target_module_id: str | None = None
    escape_capacity_people: int | None = Field(default=None, ge=1)

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
