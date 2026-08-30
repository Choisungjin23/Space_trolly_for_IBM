"""Normalized Phase C analysis contract.

This is the ONLY shape agents ever see. It is *not* Phase A's native schema —
see phase-a-contract.md for that. Field names mirror Phase A where an equivalent
exists so a reader can trace them back; new keys appear only where Phase A has a
genuine gap (equipment, events, joined Monte Carlo, provenance).
"""

from typing import Literal

from pydantic import BaseModel, Field

DetectionStatus = Literal["DETECTED", "NEVER_DETECTED"]
SystemState = Literal[
    "OPERATIONAL", "EXPOSED_AT_RISK", "UNAVAILABLE", "FAILED_EXPLICITLY"
]
CapabilityState = Literal["AVAILABLE", "AT_RISK", "UNAVAILABLE"]
CrewState = Literal["SAFE", "EXPOSED", "EVACUATING", "EVACUATED", "TRAPPED"]


class ActionRef(BaseModel):
    """A Phase A action, id treated as an opaque string (contract §2)."""

    id: str
    kind: str
    label: str
    description: str = ""
    params: dict = Field(default_factory=dict)


class Detection(BaseModel):
    """`detected_at_seconds` is nullable in Phase A; null is a real outcome
    (smoke never reached the alarm level), not a missing field."""

    status: DetectionStatus
    detected_at_seconds: float | None = None


class ReturnCapability(BaseModel):
    """How the engine reached its return verdict for one action.

    `available_at_end` is what sets every crew member's return probability, and
    so `expected_returnees`. The timing fields say how close the run came to the
    other answer: a capability lost and repaired inside the horizon costs
    nothing, which is defensible (the return flight happens afterwards) but
    invisible without these. `declared` false means the scenario never named a
    return capability, so return was not judged at all and `expected_returnees`
    equals `expected_survivors` by construction rather than by evidence.
    """

    name: str
    declared: bool
    final_state: str | None = None
    available_at_end: bool = True
    downtime_seconds: float = 0.0
    first_lost_at_seconds: float | None = None
    restored_at_seconds: float | None = None


class Hazard(BaseModel):
    """Phase C grouping. Phase A has no top-level `hazard` key — these three
    fields sit flat on `summary`."""

    reached_modules: list[str] = Field(default_factory=list)
    smac_exceeded_modules: list[str] = Field(default_factory=list)
    peak_extinction_per_m: dict[str, float] = Field(default_factory=dict)


class CrewOutcome(BaseModel):
    state: CrewState
    exposure_seconds: float
    smac_dose_fraction: float
    module: str
    survival_probability: float = 1.0
    return_probability: float = 1.0
    abandoned: bool = False
    priority_score: float = 0.0
    priority_rank: int | None = None
    priority_reasons: list[str] = Field(default_factory=list)
    waiting_for_connection_id: str | None = None
    escape_capacity_denied: bool = False
    estimated_survival_minutes: float | None = None
    resource_risk_reasons: list[str] = Field(default_factory=list)


class ResourceOutcome(BaseModel):
    power_level_w: float
    power_consumption_w: float
    power_sufficient: bool
    air_level_fraction: float
    water_stored_kg: float
    water_demand_kg_per_min: float
    water_sufficient: bool


class EquipmentOutcome(BaseModel):
    """Only available from `TimelineResult.final.equipment` (contract §8.4)."""

    name: str
    module: str
    system: str
    powered: bool
    damaged: bool
    repair_progress_seconds: float = 0.0
    portable: bool = False
    passage_units: float = 1.0
    priority_score: float = 0.0
    priority_rank: int | None = None
    priority_reasons: list[str] = Field(default_factory=list)
    evacuated: bool = False


class ConnectivityOutcome(BaseModel):
    connectivity: float
    base_connectivity: float
    crew_throughput_per_min: float
    air_throughput_percent_per_min: float
    crew_passages: int = 0
    equipment_passage_units: float = 0.0
    power_transfer_percent: float = 100.0


class CriticalFunction(BaseModel):
    function: str
    flag: Literal["SINGLE_PROVIDER", "NO_PROVIDER"]
    providers: list[str] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    """One semantic event extracted from the 120-frame timeline (§5).

    `source` distinguishes what the engine reported from what Phase C derived —
    capability transitions are derived, because frames carry no capabilities.
    """

    t: float
    type: str
    subject: str
    from_state: str | None = None
    to_state: str | None = None
    source: Literal["timeline", "derived"] = "timeline"


class CapabilityCount(BaseModel):
    """Monte Carlo count for one capability.

    `applicable` is false when Phase A's Distribution reported this capability
    without the scenario declaring it. Phase A defaults an undeclared
    capability to AVAILABLE, so the count would otherwise be vacuously n/n.
    """

    available: int
    applicable: bool


class SampledOutcome(BaseModel):
    """Counts over sampled assumption sets. NEVER probabilities (contract §4)."""

    samples: int
    counts: dict[str, int] = Field(default_factory=dict)
    capability_counts: dict[str, CapabilityCount] = Field(default_factory=dict)
    means: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class Provenance(BaseModel):
    engine: str
    horizon_seconds: float
    dt_seconds: float
    seed: int | None = None
    ethics_notice: str = ""
    downsampled: bool = False


class ActionAnalysis(BaseModel):
    """Everything an agent may know about one simulated action."""

    action: ActionRef
    detection: Detection
    hazard: Hazard
    crew: dict[str, CrewOutcome] = Field(default_factory=dict)
    crew_counts: dict[str, int] = Field(default_factory=dict)
    resources: dict[str, ResourceOutcome] = Field(default_factory=dict)
    expected_survivors: float = 0.0
    expected_returnees: float = 0.0
    return_capability: ReturnCapability | None = None
    systems: dict[str, SystemState] = Field(default_factory=dict)
    system_reasons: dict[str, str] = Field(default_factory=dict)
    equipment: dict[str, EquipmentOutcome] = Field(default_factory=dict)
    connectivity: dict[str, ConnectivityOutcome] = Field(default_factory=dict)
    escape_target: dict[str, str | int | None] | None = None
    capabilities: dict[str, CapabilityState] = Field(default_factory=dict)
    critical_functions: list[CriticalFunction] = Field(default_factory=list)
    events: list[TimelineEvent] = Field(default_factory=list)
    sampled: SampledOutcome | None = None
    provenance: Provenance


class CrewCriticality(BaseModel):
    """Leave-one-out contribution to expected crew return plus role demand."""

    crew_id: str
    role: str
    measured_score: float
    assumed_weight: float


class CaseAnalysis(BaseModel):
    """All actions for one scenario, plus case-level facts."""

    scenario_digest: str
    mission_phase: str
    capability_names: list[str] = Field(default_factory=list)
    criticality: list[CrewCriticality] = Field(default_factory=list)
    criticality_baseline_action: str | None = None
    # What the reader must know to interpret the numbers — most importantly
    # when a capability was never declared, so a comfortable-looking result is
    # an unasked question rather than a reassuring answer.
    warnings: list[str] = Field(default_factory=list)
    actions: list[ActionAnalysis] = Field(default_factory=list)

    def action(self, action_id: str) -> ActionAnalysis:
        for candidate in self.actions:
            if candidate.action.id == action_id:
                return candidate
        raise KeyError(f"No analysis for action id {action_id!r}")
