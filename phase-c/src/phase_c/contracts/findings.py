"""Agent output contract.

Every agent returns claims, and every claim declares where it came from. That
`basis` + `refs` pair is what makes the grounding validator possible: an agent
that wants to state a number must point at the field the number came from.
"""

from typing import Literal

from pydantic import BaseModel, Field

Basis = Literal["SIMULATION_FACT", "EVIDENCE", "INFERENCE", "ASSUMPTION"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]
Severity = Literal["BLOCKER", "MAJOR", "MINOR"]


class Claim(BaseModel):
    statement: str
    basis: Basis
    # JSON pointer into the ActionAnalysis (e.g. "/hazard/reached_modules"),
    # or an evidence citation id (e.g. "evidence:smac-co-1h").
    refs: list[str] = Field(default_factory=list)
    confidence: Confidence = "MEDIUM"


class AgentFinding(BaseModel):
    agent: str
    action_id: str | None = None
    claims: list[Claim] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class GroundingViolation(BaseModel):
    """A machine-detected grounding failure. Never silently corrected — the
    operator sees that an agent tried to assert something unsupported."""

    agent: str
    action_id: str | None = None
    rule: str
    detail: str
    claim_statement: str | None = None
    severity: Severity = "MAJOR"


class CriticIssue(BaseModel):
    severity: Severity
    target_agent: str
    target_claim_ref: str | None = None
    issue: str
    suggested_correction: str | None = None


class CriticReview(BaseModel):
    issues: list[CriticIssue] = Field(default_factory=list)
    # Violations found by the machine validator, surfaced rather than dropped.
    grounding_violations: list[GroundingViolation] = Field(default_factory=list)
    unexamined_actions: list[str] = Field(default_factory=list)


class Tradeoff(BaseModel):
    versus_action_id: str
    gives_up: str
    gains: str


class Recommendation(BaseModel):
    """The only place in the whole system where an action is recommended.

    A recommendation with no trade-off and no stated uncertainty is rejected by
    the validator — that shape is how these systems get over-trusted.
    """

    recommended_action_id: str
    rationale: list[Claim] = Field(default_factory=list)
    tradeoffs: list[Tradeoff] = Field(default_factory=list)
    dissent: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    human_decision_required: bool = True


class DecisionPackage(BaseModel):
    """What Phase C hands the operator (and Phase B's Advisor panel)."""

    scenario_digest: str
    findings: list[AgentFinding] = Field(default_factory=list)
    evidence: list["EvidenceAnswer"] = Field(default_factory=list)  # noqa: F821
    critic: CriticReview = Field(default_factory=CriticReview)
    recommendation: Recommendation | None = None
    provenance: dict = Field(default_factory=dict)


from phase_c.contracts.evidence import EvidenceAnswer  # noqa: E402

DecisionPackage.model_rebuild()
