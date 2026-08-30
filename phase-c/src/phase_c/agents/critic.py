"""Critic / Red-Team Agent (plan §6.6 — PROPOSED; the task spec was truncated).

Reads every other finding PLUS the raw analysis, and hunts for the failure modes
this architecture is most exposed to. Machine-detected grounding violations are
merged in here rather than dropped, so the operator sees them.
"""

import json

from pydantic import BaseModel, Field

from phase_c.contracts.analysis import ActionAnalysis, CaseAnalysis
from phase_c.contracts.findings import (
    AgentFinding,
    CriticIssue,
    CriticReview,
    GroundingViolation,
)
from phase_c.llm.base import LLMClient

CRITIC_RULES = """\
AGENT: critic

You are the Red-Team reviewer. Your job is to attack the other agents' findings,
not to summarize them. Assume they are over-confident until shown otherwise.

Look specifically for:
1. Numbers that appear in a finding but not in the ANALYSIS data.
2. Monte Carlo counts described as probability, percentage, or likelihood.
3. Simulator values generalized into universal truths ("fires are detected after
   270 s") instead of statements about this run.
4. Hazard pathways, modules, crew, systems or actions that nobody discussed.
5. Direct contradictions between two agents.
6. Capability claims that rest on a sampled count marked `applicable: false` -
   that count is vacuous and means nothing.
7. Single-provider or no-provider functions that no agent mentioned.
8. Claims resting on `source: "derived"` events presented as engine output.
9. Survival or mortality claims that lack a model-output ref, confuse sampled
   counts with probabilities, or present ASSUMED estimates as clinical fact.

For each problem emit an issue with severity BLOCKER, MAJOR or MINOR, the agent
responsible, and a concrete suggested correction. If a finding is sound, do not
invent a complaint about it.

Report at most 8 issues, the most serious first, and keep each `description` and
`suggested_correction` to one sentence. An operator acts on a short list of real
problems; an exhaustive one buries them. A reply that runs past the output limit
is cut off mid-structure and discarded entirely, so brevity is what gets your
findings seen at all.
"""


class _CriticDraft(BaseModel):
    issues: list[CriticIssue] = Field(default_factory=list)
    unexamined_actions: list[str] = Field(default_factory=list)


class CriticAgent:
    name = "critic"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def review(
        self,
        findings: list[AgentFinding],
        analysis: ActionAnalysis,
        case: CaseAnalysis,
        *,
        violations: list[GroundingViolation] | None = None,
    ) -> CriticReview:
        violations = list(violations or [])

        payload = {
            "action_under_review": analysis.action.id,
            "all_action_ids_in_case": [a.action.id for a in case.actions],
            "analysis": analysis.model_dump(mode="json"),
            "findings": [f.model_dump(mode="json") for f in findings],
            "machine_detected_violations": [
                v.model_dump(mode="json") for v in violations
            ],
        }

        draft = self.llm.complete(
            system=CRITIC_RULES,
            user=(
                "Review the following. The machine validator already caught the "
                "items in `machine_detected_violations`; do not repeat them, but "
                "do consider what they imply about the agent that produced them."
                f"\n\n{json.dumps(payload, separators=(',', ':'), ensure_ascii=False)}"
            ),
            schema=_CriticDraft,
        )

        discussed = " ".join(
            claim.statement
            for finding in findings
            for claim in finding.claims
        )
        unexamined = sorted(
            {
                other.action.id
                for other in case.actions
                if other.action.id != analysis.action.id
                and other.action.id not in discussed
            }
        )

        return CriticReview(
            issues=draft.issues,
            grounding_violations=violations,
            unexamined_actions=draft.unexamined_actions or unexamined,
        )
