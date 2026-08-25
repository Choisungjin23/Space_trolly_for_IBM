"""Pydantic request/response schemas mirroring the domain models."""

from typing import Any

from pydantic import BaseModel, Field

from app.config import DEFAULT_RUNS, MAX_RUNS


class CrewMemberOut(BaseModel):
    id: str
    name: str
    alive: bool


class ModuleOut(BaseModel):
    id: str
    name: str
    fire_severity: float
    isolated: bool
    crew: list[CrewMemberOut]
    systems: list[str]


class ConnectionOut(BaseModel):
    source: str
    target: str
    hazard_spread_probability: float
    active: bool


class ActionOut(BaseModel):
    id: str
    label: str
    description: str


class ScenarioOut(BaseModel):
    modules: dict[str, ModuleOut]
    connections: list[ConnectionOut]
    critical_systems: list[str]
    # Actions depend on where the fire is, so they travel with the scenario.
    actions: list[ActionOut]


class SettingsIn(BaseModel):
    """Partial override of SimulationConfig sent by the GUI.

    Numeric values are clamped to FIELD_SPECS bounds in config.build_config;
    unknown keys are ignored there. Only structural choices are validated here.
    """

    model_config = {"extra": "ignore"}

    initial_fire_module: str | None = None
    crew_placement: dict[str, str] | None = None

    initial_fire_severity: float | None = None
    connection_hazard_probability: float | None = None
    sim_steps: int | None = None
    propagation_factor: float | None = None
    ignition_severity: float | None = None
    growth_rate: float | None = None
    extinguish_prob: float | None = None
    extinguish_amount: float | None = None
    system_damage_threshold: float | None = None
    system_failure_prob: float | None = None
    crew_hazard_threshold: float | None = None
    crew_fatality_factor: float | None = None


class ScenarioRequest(BaseModel):
    settings: SettingsIn | None = None


class FieldSpecOut(BaseModel):
    key: str
    label: str
    group: str
    min: float
    max: float
    step: float
    integer: bool
    help: str


class CrewOut(BaseModel):
    id: str
    name: str


class ConfigOut(BaseModel):
    """Everything the GUI needs to render parameter controls."""

    defaults: dict[str, Any]
    fields: list[FieldSpecOut]
    modules: list[CrewOut]  # id + display name, reused shape
    crew: list[CrewOut]


class SimulateRequest(BaseModel):
    # None = simulate every available action (the frontend's compare-all case).
    actions: list[str] | None = None
    runs: int = Field(default=DEFAULT_RUNS, ge=1, le=MAX_RUNS)
    seed: int | None = None
    settings: SettingsIn | None = None


class ActionResult(BaseModel):
    action_id: str
    label: str
    runs: int
    total_crew: int
    expected_surviving_crew: float
    crew_survival_pct: float
    fire_contained_pct: float
    critical_systems_pct: float
    mission_survival_pct: float
    mean_final_fire_severity: float


class SimulateResponse(BaseModel):
    runs: int
    seed: int | None
    steps: int
    results: list[ActionResult]
