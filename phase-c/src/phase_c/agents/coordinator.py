"""Decision Coordinator (plan §6.7 — PROPOSED; the task spec was truncated).

The only agent permitted to recommend. It must name trade-offs and state
uncertainty; a recommendation without both is rejected by the validator, because
that shape is how these systems get over-trusted. The human decides.
"""

import json

from phase_c.contracts.analysis import CaseAnalysis
from phase_c.contracts.evidence import EvidenceAnswer
from phase_c.contracts.findings import AgentFinding, CriticReview, Recommendation
from phase_c.llm.base import LLMClient

COORDINATOR_RULES = """\
AGENT: coordinator

You are the Decision Coordinator. You are the only agent allowed to recommend an
action. You synthesize the specialist findings, the evidence, and the critic's
objections into one structured recommendation for a human operator.

Requirements:
1. `recommended_action_id` must be one of the action ids present in the DATA.
2. `tradeoffs` must contain at least one entry. Name what the recommended action
   GIVES UP against a specific alternative, not only what it gains. If you
   cannot find a cost, you have not looked hard enough.
3. `uncertainty` must contain at least one entry, and must state what the
   sampling did and did not cover.
4. `dissent` carries every critic issue you did not resolve. Do not quietly drop
   objections; if you disagree with one, say so there.
5. `rationale` claims follow the same grounding rules as the other agents: every
   number must come from the DATA, with refs pointing at it.
6. Monte Carlo results are counts over sampled assumption sets, never
   probabilities or percentages.
7. `human_decision_required` stays true. You advise; the operator decides.
8. No fatality, lethality or survival-probability language. The engine models
   crew states and exposure only.
"""


class CoordinatorAgent:
    name = "coordinator"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def recommend(
        self,
        case: CaseAnalysis,
        findings: list[AgentFinding],
        critic: CriticReview,
        evidence: list[EvidenceAnswer],
    ) -> Recommendation:
        payload = {
            "mission_phase": case.mission_phase,
            "capability_names_declared_by_scenario": case.capability_names,
            "actions": [a.model_dump(mode="json") for a in case.actions],
            "findings": [f.model_dump(mode="json") for f in findings],
            "critic": critic.model_dump(mode="json"),
            "evidence": [e.model_dump(mode="json") for e in evidence],
        }

        recommendation = self.llm.complete(
            system=COORDINATOR_RULES,
            user=(
                "Compare every action in the DATA and recommend one.\n\n"
                f"{json.dumps(payload, indent=2, ensure_ascii=False)}"
            ),
            schema=Recommendation,
        )
        # Copy rather than mutate, for the same reason as the specialists.
        return recommendation.model_copy(
            update={"human_decision_required": True}, deep=True
        )
