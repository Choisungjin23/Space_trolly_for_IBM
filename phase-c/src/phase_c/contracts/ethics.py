"""Machine-enforced ethical-policy output.

This contract deliberately avoids a single "ethics score".  It exposes the
human-impact dimensions, the policy rule that separated the candidates, and
the sources behind that policy so an operator can audit the recommendation.
"""

from typing import Literal

from pydantic import BaseModel, Field

from phase_c.contracts.evidence import EvidenceCitation

EthicsStatus = Literal["POLICY_CONSISTENT", "REVIEW_REQUIRED", "BLOCKED"]
PolicyCheckStatus = Literal["PASS", "REVIEW", "BLOCK"]


class PolicyCheck(BaseModel):
    rule_id: str
    status: PolicyCheckStatus
    summary: str
    refs: list[str] = Field(default_factory=list)


class ActionEthicsAssessment(BaseModel):
    action_id: str
    eligible: bool = True
    expected_returnees: float
    expected_survivors: float
    minimum_crew_survival_probability: float | None = None
    abandoned_crew_count: int = 0
    trapped_crew_count: int = 0
    maximum_smac_dose_fraction: float | None = None
    smac_exceeded_module_count: int = 0
    hazard_reached_module_count: int = 0
    affected_crew_ids: list[str] = Field(default_factory=list)
    policy_checks: list[PolicyCheck] = Field(default_factory=list)
    co_recommended: bool = False


class TieBreakStep(BaseModel):
    criterion: str
    direction: Literal["MAXIMIZE", "MINIMIZE"]
    best_value: float
    tie_margin: float
    remaining_action_ids: list[str]
    explanation: str


class EthicalAssessment(BaseModel):
    """A versioned PoC policy assessment, not a claim of moral truth."""

    policy_id: str
    policy_version: str
    status: EthicsStatus
    selected_action_id: str | None = None
    co_recommended_action_ids: list[str] = Field(default_factory=list)
    selection_basis: str
    action_assessments: list[ActionEthicsAssessment] = Field(default_factory=list)
    tie_break_steps: list[TieBreakStep] = Field(default_factory=list)
    sources: list[EvidenceCitation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    human_decision_required: bool = True

    def decision_context(self) -> dict:
        """Compact policy view for LLM review and explanation.

        The API keeps every action assessment for the operator.  Agents already
        receive the full action outputs separately, so repeating the complete
        table in two prompts only spends tokens without adding evidence.
        """

        selected = next(
            (
                action.model_dump(mode="json")
                for action in self.action_assessments
                if action.action_id == self.selected_action_id
            ),
            None,
        )
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "status": self.status,
            "selected_action_id": self.selected_action_id,
            "co_recommended_action_ids": self.co_recommended_action_ids,
            "selection_basis": self.selection_basis,
            "selected_action_assessment": selected,
            "tie_break_steps": [
                step.model_dump(mode="json") for step in self.tie_break_steps
            ],
            "sources": [source.model_dump(mode="json") for source in self.sources],
            "limitations": self.limitations,
            "human_decision_required": self.human_decision_required,
        }
