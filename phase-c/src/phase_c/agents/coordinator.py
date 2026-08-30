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
   number must come from the DATA, with refs pointing at it. Your DATA is the
   whole case, so an action's value is cited through its index in `actions`:
   write "/actions/0/sampled/counts/no_crew_trapped", never
   "/sampled/counts/no_crew_trapped". The `refs` you can see inside `findings`
   are each specialist's pointers into its own private view of one action -
   they do not resolve here, so do not copy them.
6. Maximize `expected_returnees` first, then `expected_survivors`, under the
   declared resource constraints. Monte Carlo counts are not probabilities;
   the engine's explicit crew survival/return probabilities are model outputs.
7. `human_decision_required` stays true. You advise; the operator decides.
8. A recommendation may isolate or abandon a rescue when that maximizes total
   expected surviving returnees. Name who is affected, why, and the alternative.
   These estimates are ASSUMED model outputs, not clinical guarantees.
9. Account for hatch queues explicitly. Compare connectivity, crew/min and air
   %/min, people waiting, and the passage order. Crew capacity is allocated
   before portable equipment; consider whether an alternate crew ordering
   improves expected surviving returnees while preserving indispensable return
   equipment. Include the negative feedback from each hazardous passage.

The DATA is trimmed for comparison: each action lists only the equipment whose
state is not nominal, and the per-action timeline is omitted. Everything shown
is citable as usual. Engine provenance is the same for every action: constants
named VERIFIED_* come from primary sources, ASSUMED_* are PoC assumptions and
are not validated.
"""


def _comparable(analysis) -> dict:
    """What the coordinator needs to weigh one action against another.

    Whole subtrees are dropped, never reshaped. That distinction matters: a
    surviving value keeps the exact JSON pointer the fact registry built for
    it, so trimming cannot turn a sound citation into a grounding violation.
    Reshaping the payload would.

    The saving is large. Every action carried a full equipment inventory and a
    copy of the same provenance block, so a ten-action case spent most of its
    prompt restating things that do not differ between the options.
    """
    data = analysis.model_dump(mode="json")

    # The specialists read the timeline in depth; the coordinator compares
    # outcomes, and `detection` already carries the timing that decides.
    data.pop("events", None)
    # Identical for every action — stated once in the rules above instead.
    data.pop("provenance", None)

    equipment = data.get("equipment")
    if isinstance(equipment, dict):
        # Nominal equipment is the default; only departures inform a choice.
        data["equipment"] = {
            equipment_id: item
            for equipment_id, item in equipment.items()
            if item.get("damaged") or not item.get("powered", True)
        }
    return data


class CoordinatorAgent:
    name = "coordinator"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def payload(
        self,
        case: CaseAnalysis,
        findings: list[AgentFinding],
        critic: CriticReview,
        evidence: list[EvidenceAnswer],
    ) -> dict:
        """Everything the coordinator is shown.

        Public because the grounding validator has to check its citations
        against this exact tree - the coordinator cites into a case-shaped
        payload (`/actions/0/hazard/...`), not into a single action.
        """
        return {
            "mission_phase": case.mission_phase,
            "capability_names_declared_by_scenario": case.capability_names,
            "actions": [_comparable(a) for a in case.actions],
            "findings": [f.model_dump(mode="json") for f in findings],
            "critic": critic.model_dump(mode="json"),
            "evidence": [e.model_dump(mode="json") for e in evidence],
        }

    def recommend(
        self,
        case: CaseAnalysis,
        findings: list[AgentFinding],
        critic: CriticReview,
        evidence: list[EvidenceAnswer],
    ) -> Recommendation:
        payload = self.payload(case, findings, critic, evidence)

        recommendation = self.llm.complete(
            system=COORDINATOR_RULES,
            user=(
                "Compare every action in the DATA and recommend one.\n\n"
                # Compact separators: indentation is a third of this payload
                # and carries nothing the model reads.
                f"{json.dumps(payload, separators=(',', ':'), ensure_ascii=False)}"
            ),
            schema=Recommendation,
        )
        # Copy rather than mutate, for the same reason as the specialists.
        return recommendation.model_copy(
            update={"human_decision_required": True}, deep=True
        )
