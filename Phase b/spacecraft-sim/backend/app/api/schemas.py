"""
Pydantic schemas for Phase B API.

These are the request/response models for POST /api/simulate and
GET /api/templates endpoints. They mirror the TypeScript types in
frontend/src/types/.

Phase A physics (propagation, Monte Carlo, PROPAGATION_FACTOR, etc.)
are NOT represented here. The MockSimulatorAdapter in adapters/ provides
placeholder results until Phase A ships.
"""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, model_validator


# ─── Canonical scenario input models ────────────────────────────────────────

class CrewMemberIn(BaseModel):
    id: str
    name: str
    role: str
    providesFunctions: list[str] = Field(default_factory=list)


class EquipmentIn(BaseModel):
    id: str
    name: str
    type: str
    state: Literal[
        "operational",
        "exposed_at_risk",
        "unavailable",
        "explicitly_failed",
    ]
    providesCapabilities: list[str] = Field(default_factory=list)


class ModuleIn(BaseModel):
    id: str
    name: str
    type: Literal["habitat", "storage", "life_support", "power", "propulsion", "other"]
    pressure: Optional[float] = None
    oxygenFraction: Optional[float] = None
    crew: list[CrewMemberIn] = Field(default_factory=list)
    equipment: list[EquipmentIn] = Field(default_factory=list)
    # position is frontend-only; accepted but not used by simulator
    position: Optional[dict[str, float]] = None


class ConnectionIn(BaseModel):
    id: str
    source: str
    target: str
    type: Literal["hatch", "imv", "leak", "other"]
    state: Literal["open", "closed", "unknown"]
    ventilationOn: bool = False
    flowDirection: Literal[
        "source_to_target",
        "target_to_source",
        "bidirectional",
        "none",
        "unknown",
    ] = "unknown"
    transferClass: Literal["none", "low", "medium", "high", "unknown"] = "unknown"


class EmergencyConfigIn(BaseModel):
    type: Literal["fire"] = "fire"
    affectedModuleId: str
    detected: bool = True
    sourceProfileId: Optional[str] = None


class ScenarioIn(BaseModel):
    id: Optional[str] = None
    name: str = "Unnamed Spacecraft"
    missionPhase: Optional[str] = None
    modules: dict[str, ModuleIn] = Field(default_factory=dict)
    connections: dict[str, ConnectionIn] = Field(default_factory=dict)
    emergency: Optional[EmergencyConfigIn] = None

    @model_validator(mode="after")
    def validate_graph_integrity(self) -> "ScenarioIn":
        for module_key, module in self.modules.items():
            if module_key != module.id:
                raise ValueError(
                    f"Module dictionary key '{module_key}' must match module id '{module.id}'"
                )

        for connection_key, connection in self.connections.items():
            if connection_key != connection.id:
                raise ValueError(
                    f"Connection dictionary key '{connection_key}' must match connection id "
                    f"'{connection.id}'"
                )
            if connection.source not in self.modules:
                raise ValueError(
                    f"Connection '{connection.id}' references missing source module "
                    f"'{connection.source}'"
                )
            if connection.target not in self.modules:
                raise ValueError(
                    f"Connection '{connection.id}' references missing target module "
                    f"'{connection.target}'"
                )
            if connection.source == connection.target:
                raise ValueError(f"Connection '{connection.id}' cannot connect a module to itself")

        crew_ids: set[str] = set()
        equipment_ids: set[str] = set()
        for module in self.modules.values():
            for crew_member in module.crew:
                if crew_member.id in crew_ids:
                    raise ValueError(f"Duplicate crew id '{crew_member.id}'")
                crew_ids.add(crew_member.id)
            for equipment in module.equipment:
                if equipment.id in equipment_ids:
                    raise ValueError(f"Duplicate equipment id '{equipment.id}'")
                equipment_ids.add(equipment.id)

        if self.emergency and self.emergency.affectedModuleId not in self.modules:
            raise ValueError(
                f"Emergency references missing module '{self.emergency.affectedModuleId}'"
            )

        return self


# ─── Simulation request ──────────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    scenario: ScenarioIn
    emergency: EmergencyConfigIn
    actions: Optional[list[str]] = None  # null = generate all feasible
    runs: int = Field(default=200, ge=1, le=5000)
    seed: Optional[int] = None

    @model_validator(mode="after")
    def validate_request_consistency(self) -> "SimulateRequest":
        if self.emergency.affectedModuleId not in self.scenario.modules:
            raise ValueError(
                f"Emergency references missing module '{self.emergency.affectedModuleId}'"
            )
        if self.scenario.emergency and self.scenario.emergency != self.emergency:
            raise ValueError("scenario.emergency must match the top-level emergency")
        if self.actions is not None:
            if not self.actions:
                raise ValueError("actions must be null or contain at least one action id")
            if len(set(self.actions)) != len(self.actions):
                raise ValueError("actions must not contain duplicate action ids")
        return self


# ─── Simulation response models ──────────────────────────────────────────────

class ActionOperationOut(BaseModel):
    type: str
    targetId: str


class ActionSpecOut(BaseModel):
    id: str
    label: str
    description: str
    operations: list[ActionOperationOut]


class HazardOutcome(BaseModel):
    modulesReached: int
    modulesReachedIds: list[str]
    containedInNScenarios: int
    totalScenarios: int


class CrewMemberOutcome(BaseModel):
    status: str
    exposureExampleSeconds: int


class CrewOutcomeSummary(BaseModel):
    allEvacuatedCount: int
    anyTrappedCount: int
    totalScenarios: int
    byCrewMember: Optional[dict[str, CrewMemberOutcome]] = None


class EquipmentItemOutcome(BaseModel):
    name: str
    state: str


class EquipmentOutcomeSummary(BaseModel):
    byEquipmentId: dict[str, EquipmentItemOutcome]


class CapabilityOutcomeSummary(BaseModel):
    byCapability: dict[str, str]  # available | degraded | unavailable


class CriticalFunctionEntry(BaseModel):
    providersAvailable: int
    totalProviders: int
    status: str  # nominal | single_provider | no_provider


class CriticalFunctionSummary(BaseModel):
    byFunction: dict[str, CriticalFunctionEntry]


class UncertaintySummary(BaseModel):
    note: str


class TrajectoryStep(BaseModel):
    stepIndex: int
    timeSeconds: int
    moduleStates: dict[str, Any]
    events: list[str]


class ExampleTrajectory(BaseModel):
    seed: int
    steps: list[TrajectoryStep]


class ActionSimulationResult(BaseModel):
    actionId: str
    hazard: HazardOutcome
    crew: CrewOutcomeSummary
    equipment: EquipmentOutcomeSummary
    capabilities: CapabilityOutcomeSummary
    criticalFunctions: CriticalFunctionSummary
    uncertaintySummary: Optional[UncertaintySummary] = None
    exampleTrajectory: Optional[ExampleTrajectory] = None


class SimulationResponse(BaseModel):
    generatedActions: list[ActionSpecOut]
    results: list[ActionSimulationResult]
    simulatedHorizonSeconds: int
    runsRequested: int
    seed: Optional[int]
    sourceLabel: str


# ─── Template list ───────────────────────────────────────────────────────────

class TemplateSummary(BaseModel):
    id: str
    name: str
    description: str

# ─── Phase C advisor ─────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    """Runs the Phase C multi-agent pipeline over a scenario.

    Separate from SimulateRequest: simulation is fast and deterministic, while
    analysis adds seven LLM agents on top of it.
    """

    scenario: ScenarioIn
    emergency: EmergencyConfigIn
    focusActionId: Optional[str] = None
    samples: int = Field(default=20, ge=1, le=500)
    seed: Optional[int] = 42

    @model_validator(mode="after")
    def validate_request_consistency(self) -> "AnalyzeRequest":
        if self.emergency.affectedModuleId not in self.scenario.modules:
            raise ValueError(
                f"Emergency references missing module '{self.emergency.affectedModuleId}'"
            )
        return self


class AdvisorStatus(BaseModel):
    available: bool
    detail: str = ""
