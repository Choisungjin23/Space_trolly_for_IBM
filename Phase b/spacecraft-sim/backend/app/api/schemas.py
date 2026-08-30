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
    powerConsumptionW: float = Field(default=5.0, ge=0)
    portable: bool = False
    passageUnits: float = Field(default=1.0, gt=0)

    @model_validator(mode="before")
    @classmethod
    def default_power_by_type(cls, data: Any) -> Any:
        if isinstance(data, dict):
            defaults = {
                "life_support": 25.0,
                "power": 8.0,
                "propulsion": 50.0,
                "gnc": 15.0,
                "comms": 20.0,
                "fuel": 1.0,
                "fire_suppression": 12.0,
                "medical": 15.0,
                "science": 20.0,
                "other": 5.0,
            }
            updates: dict[str, Any] = {}
            if "powerConsumptionW" not in data:
                updates["powerConsumptionW"] = defaults.get(data.get("type"), 5.0)
            if "portable" not in data:
                updates["portable"] = data.get("type") in {
                    "gnc", "comms", "fire_suppression", "medical", "science", "other"
                }
            data = {**data, **updates}
        return data

    @model_validator(mode="after")
    def remove_source_capabilities(self) -> "EquipmentIn":
        self.providesCapabilities = [
            capability
            for capability in self.providesCapabilities
            if capability not in {"oxygen_supply", "electrical_power"}
        ]
        return self


class ModuleIn(BaseModel):
    id: str
    name: str
    type: Literal["habitat", "storage", "life_support", "power", "propulsion", "other"]
    pressure: Optional[float] = None
    oxygenFraction: Optional[float] = None
    powerLevelW: float = Field(default=10.0, ge=0)
    powerConsumptionW: float = Field(default=10.0, ge=0)
    maxPowerOutputW: float = Field(default=0.0, ge=0)
    waterStoredKg: float = Field(default=0.0, ge=0)
    waterCapacityKg: float = Field(default=0.0, ge=0)
    suppliesAir: bool = False
    suppliesWater: bool = False
    maxAirOutputPercentPerMin: float = Field(default=0.0, ge=0)
    maxWaterOutputKgPerMin: float = Field(default=0.0, ge=0)
    waterRecoveryEfficiency: float = Field(default=0.98, ge=0, le=1)
    disruptionLevel: float = Field(default=0.0, ge=0, le=1)
    sourceSizingLocked: bool = False
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
    powerLineOn: bool = True
    airLineOn: bool = True
    waterLineOn: bool = True
    baseConnectivity: float = Field(default=100.0, ge=0, le=100)
    connectivity: float = Field(default=100.0, ge=0, le=100)
    powerTransferFactor: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_utility_lines(self) -> "ConnectionIn":
        if self.type != "hatch" and (self.powerLineOn or self.airLineOn or self.waterLineOn):
            # Utility lines are carried by physical hatch/corridor connections.
            self.powerLineOn = False
            self.airLineOn = False
            self.waterLineOn = False
        return self


class EscapeTargetIn(BaseModel):
    connectionId: str
    fromModuleId: str
    toModuleId: str
    selection: Literal["recommended", "manual"] = "recommended"
    maxOccupants: Optional[int] = Field(default=None, ge=1)


class EmergencyConfigIn(BaseModel):
    type: Literal["fire", "electronic_short"] = "fire"
    affectedModuleId: str
    detected: bool = True
    sourceProfileId: Optional[str] = None
    escapeTarget: Optional[EscapeTargetIn] = None


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
        if self.emergency and self.emergency.escapeTarget:
            target = self.emergency.escapeTarget
            connection = self.connections.get(target.connectionId)
            if connection is None:
                raise ValueError(
                    f"Escape target references missing connection '{target.connectionId}'"
                )
            if connection.type != "hatch" or connection.state != "open":
                raise ValueError("Escape target must use an open hatch")
            if {target.fromModuleId, target.toModuleId} != {
                connection.source, connection.target
            }:
                raise ValueError("Escape target direction must match hatch endpoints")

            def component(start: str) -> set[str]:
                seen = {start}
                queue = [start]
                while queue:
                    current = queue.pop(0)
                    for candidate in self.connections.values():
                        if (
                            candidate.id == target.connectionId
                            or candidate.type != "hatch"
                            or candidate.state != "open"
                        ):
                            continue
                        neighbor = None
                        if candidate.source == current:
                            neighbor = candidate.target
                        elif candidate.target == current:
                            neighbor = candidate.source
                        if neighbor and neighbor not in seen:
                            seen.add(neighbor)
                            queue.append(neighbor)
                return seen

            source_zone = component(target.fromModuleId)
            target_zone = component(target.toModuleId)
            if self.emergency.affectedModuleId not in source_zone:
                raise ValueError("Escape target entry side is not connected to the hazard")
            if self.emergency.affectedModuleId in target_zone:
                raise ValueError("Escape target zone is not isolated from the hazard")

            zone_modules = [self.modules[module_id] for module_id in target_zone]
            power_capacity = sum(
                module.maxPowerOutputW
                for module in zone_modules
                if module.type == "power"
            )
            power_demand = sum(
                module.powerConsumptionW
                + sum(
                    equipment.powerConsumptionW
                    for equipment in module.equipment
                    if equipment.state in {"operational", "exposed_at_risk"}
                )
                + (25.0 if module.type == "life_support" and module.suppliesAir else 0.0)
                + (20.0 if module.type == "life_support" and module.suppliesWater else 0.0)
                for module in zone_modules
            )
            if power_capacity < power_demand:
                raise ValueError("Escape target zone lacks sufficient independent power")

            air_capacity = sum(
                module.maxAirOutputPercentPerMin
                for module in zone_modules
                if module.type == "life_support" and module.suppliesAir
            )
            if air_capacity < len(zone_modules) * 0.01:
                raise ValueError("Escape target zone lacks sufficient independent air")

            crew_count = sum(len(module.crew) for module in self.modules.values())
            water_required = crew_count * 0.00264 * 60
            water_stored = sum(module.waterStoredKg for module in zone_modules)
            if water_stored < water_required:
                raise ValueError("Escape target zone lacks a 60-minute crew water reserve")

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
    survivalProbability: float = Field(default=1.0, ge=0, le=1)
    returnProbability: float = Field(default=1.0, ge=0, le=1)
    abandoned: bool = False
    priorityScore: float = Field(default=0.0, ge=0, le=100)
    priorityRank: Optional[int] = None
    priorityReasons: list[str] = Field(default_factory=list)
    waitingForConnectionId: Optional[str] = None
    escapeCapacityDenied: bool = False
    estimatedSurvivalMinutes: Optional[float] = Field(default=None, ge=0)
    resourceRiskReasons: list[str] = Field(default_factory=list)


class CrewOutcomeSummary(BaseModel):
    allEvacuatedCount: int
    anyTrappedCount: int
    totalScenarios: int
    byCrewMember: Optional[dict[str, CrewMemberOutcome]] = None


class EquipmentItemOutcome(BaseModel):
    name: str
    state: str
    portable: bool = False
    priorityScore: float = Field(default=0.0, ge=0, le=100)
    priorityRank: Optional[int] = None
    priorityReasons: list[str] = Field(default_factory=list)
    evacuated: bool = False


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


class ModuleResourceOutcome(BaseModel):
    powerLevelW: float
    powerDemandW: float
    powerSufficient: bool
    airLevelPercent: float
    waterStoredKg: float
    waterDemandKgPerMin: float
    waterSufficient: bool


class ResourceOutcomeSummary(BaseModel):
    byModuleId: dict[str, ModuleResourceOutcome] = Field(default_factory=dict)


class ConnectionConnectivityOutcome(BaseModel):
    connectivity: float = Field(ge=0, le=100)
    baseConnectivity: float = Field(ge=0, le=100)
    crewThroughputPerMin: float = Field(ge=0)
    airThroughputPercentPerMin: float = Field(ge=0)
    crewPassages: int = Field(ge=0)
    equipmentPassageUnits: float = Field(ge=0)
    powerTransferPercent: float = Field(default=100.0, ge=0, le=100)


class ConnectivityOutcomeSummary(BaseModel):
    byConnectionId: dict[str, ConnectionConnectivityOutcome] = Field(default_factory=dict)


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
    resources: ResourceOutcomeSummary = Field(default_factory=ResourceOutcomeSummary)
    connectivity: ConnectivityOutcomeSummary = Field(
        default_factory=ConnectivityOutcomeSummary
    )
    expectedSurvivors: float = 0.0
    expectedReturnees: float = 0.0
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
    """Safe to publish: it names the watsonx environment, never the account.

    `model_id` and `watsonx_url` let an operator confirm which model produced
    the advice. The API key and project id are deliberately absent.
    """

    available: bool
    detail: str = ""
    configured: bool = False
    model_id: Optional[str] = None
    watsonx_url: Optional[str] = None
    # A one-way tag for the key this process is running on, and where it came
    # from. Reveals nothing about the key, but answers the question that is
    # otherwise unanswerable from outside: is the running server using the key
    # currently in backend/.env, or a stale one it loaded at startup?
    key_fingerprint: Optional[str] = None
    key_source: Optional[str] = None
