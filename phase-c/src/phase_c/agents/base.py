"""Agent base: prompt assembly, projection, and the shared house rules.

Each agent projects the ActionAnalysis down to the fields its domain needs
(contract §7 mapping), so a prompt never carries the whole world.
"""

import json
from abc import ABC, abstractmethod

from phase_c.contracts.analysis import ActionAnalysis, CaseAnalysis
from phase_c.contracts.findings import AgentFinding
from phase_c.llm.base import LLMClient

HOUSE_RULES = """\
Rules you must follow, without exception:

1. The simulator produces the numbers. You never invent one. Every number you
   state must already appear in the DATA below, or in cited evidence.
2. Numbers from the simulator are facts *about this simulation run*, not
   universal truths. Say "in this simulation, detection occurred at 270 s",
   never "spacecraft fires are detected after 270 s".
3. Monte Carlo output is a COUNT over sampled assumption sets. Write
   "k of n sampled assumption sets". Never a percentage or a probability.
4. The engine models crew states and exposure. It has no fatality model. Never
   mention death, lethality, survival probability, or mortality.
5. Never rank people by worth. Crew criticality means how irreplaceable a
   FUNCTION is right now, not the value of a life.
6. Do not recommend an action. Report what your domain sees.
7. Every claim carries a `basis` and `refs`. Use `refs` JSON pointers into the
   DATA, for example "/hazard/reached_modules" or "/crew/C3/exposure_seconds".
   A SIMULATION_FACT claim with no resolving ref is rejected.
8. Module ids, action ids, capability names and crew ids come from the DATA.
   Never assume a fixed set.
"""


class Agent(ABC):
    name: str = "agent"
    role: str = ""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    @abstractmethod
    def project(self, analysis: ActionAnalysis, case: CaseAnalysis) -> dict:
        """The subset of the analysis this agent is entitled to see."""

    def system_prompt(self) -> str:
        return f"AGENT: {self.name}\n\n{self.role}\n\n{HOUSE_RULES}"

    def user_prompt(self, analysis: ActionAnalysis, case: CaseAnalysis) -> str:
        payload = self.project(analysis, case)
        return (
            f"ACTION UNDER ANALYSIS: {analysis.action.id} "
            f"(kind={analysis.action.kind})\n\n"
            f"DATA (this is the whole of what you know):\n"
            f"{json.dumps(payload, indent=2, ensure_ascii=False)}\n\n"
            f"ENGINE PROVENANCE: {analysis.provenance.ethics_notice}\n\n"
            f"Produce your findings."
        )

    def analyze(self, analysis: ActionAnalysis, case: CaseAnalysis) -> AgentFinding:
        finding = self.llm.complete(
            system=self.system_prompt(),
            user=self.user_prompt(analysis, case),
            schema=AgentFinding,
        )
        # The agent does not get to relabel itself or drift onto another action.
        # Copy rather than mutate: an LLM client may legitimately return a
        # shared or cached object, and mutating it would corrupt other findings.
        return finding.model_copy(
            update={"agent": self.name, "action_id": analysis.action.id}, deep=True
        )


def events_of(analysis: ActionAnalysis, types: set[str]) -> list[dict]:
    return [e.model_dump(mode="json") for e in analysis.events if e.type in types]
