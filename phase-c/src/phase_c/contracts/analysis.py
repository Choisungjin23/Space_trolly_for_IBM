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


class EquipmentOutcome(BaseModel):
    """Only available from `TimelineResult.final.equipment` (contract §8.4)."""

    name: str
    module: str
    system: str
    powered: bool
    damaged: bool
    repair_progress_seconds: float = 0.0


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
    without the scenario declaring it — see plan §0.2. Phase A defaults an
    undeclared capability to AVAILABLE, so the count would be vacuously n/n.
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
    systems: dict[str, SystemState] = Field(default_factory=dict)
    system_reasons: dict[str, str] = Field(default_factory=dict)
    equipment: dict[str, EquipmentOutcome] = Field(default_factory=dict)
    capabilities: dict[str, CapabilityState] = Field(default_factory=dict)
    critical_functions: list[CriticalFunction] = Field(default_factory=list)
    events: list[TimelineEvent] = Field(default_factory=list)
    sampled: SampledOutcome | None = None
    provenance: Provenance


class CrewCriticality(BaseModel):
    """Leave-one-out measurement plus the assumed FMECA-style weight.

    Neither is a valuation of a life — this is function irreplaceability under
    the current situation (contract §5).
    """

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
    actions: list[ActionAnalysis] = Field(default_factory=list)

    def action(self, action_id: str) -> ActionAnalysis:
        for candidate in self.actions:
            if candidate.action.id == action_id:
                return candidate
        raise KeyError(f"No analysis for action id {action_id!r}")
