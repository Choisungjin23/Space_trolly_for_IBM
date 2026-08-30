"""Evidence / RAG Agent (PROPOSED; the source task spec was truncated).

Independent of Phase A. Answers "what does relevant real technical evidence
say?" and never decides. Applicability is mandatory on every answer.
"""

from pydantic import BaseModel, Field

from phase_c.contracts.analysis import ActionAnalysis, CaseAnalysis
from phase_c.contracts.evidence import EvidenceAnswer, EvidenceChunk
from phase_c.llm.base import LLMClient
from phase_c.rag.store import EvidenceStore

EVIDENCE_RULES = """\
AGENT: evidence

You are the Evidence analyst. You report what cited technical sources say, and
you NEVER decide, rank, or recommend anything.

Rules:
1. Every answer rests on exactly one retrieved SOURCE below. Do not blend
   sources into one claim.
2. `applicability` is mandatory and must be honest about transfer. A figure
   measured on ISS may not apply to a different vehicle; ground-test combustion
   data does not transfer to microgravity.
3. Never restate a simulator number as if the source said it. The sources know
   nothing about this simulation run.
4. If the sources do not address the question, say so in `claim` and set
   `applicability` to explain the gap. Do not fill it in from memory.
5. Survival or mortality evidence must be used only when the retrieved source
   supports it; distinguish evidence from the engine's modeled estimate.
"""


class _EvidenceDraft(BaseModel):
    claim: str
    applicability: str
    limits: str = ""


class _EvidenceBundle(BaseModel):
    answers: list[_EvidenceDraft] = Field(default_factory=list)


class EvidenceAgent:
    name = "evidence"

    def __init__(self, llm: LLMClient, store: EvidenceStore | None = None) -> None:
        self.llm = llm
        self.store = store or EvidenceStore.from_corpus()

    def queries_for(self, analysis: ActionAnalysis, case: CaseAnalysis) -> list[str]:
        """Questions worth asking the corpus, derived from what actually
        happened — not a fixed list."""
        queries: list[str] = []
        if analysis.hazard.smac_exceeded_modules:
            queries.append(
                "exposure limits for combustion products carbon monoxide hydrogen cyanide"
            )
        if analysis.detection.status == "NEVER_DETECTED":
            queries.append("smoke detection alarm threshold ventilation dependence")
        elif analysis.detection.detected_at_seconds is not None:
            queries.append("smoke detector placement ventilation intake alarm confirmation")
        if any(e.type == "hazard_arrival" for e in analysis.events):
            queries.append("intermodule ventilation flow rate dilution air exchange")
        if analysis.action.kind in ("shutdown_ventilation", "close_imv"):
            queries.append("ventilation airflow effect on flame spread microgravity")
        if analysis.critical_functions:
            queries.append("criticality analysis single point failure redundancy methodology")
        if not queries:
            queries.append("spacecraft fire safety flammability screening")
        return queries

    def gather(
        self, analysis: ActionAnalysis, case: CaseAnalysis
    ) -> list[EvidenceAnswer]:
        answers: list[EvidenceAnswer] = []
        seen: set[str] = set()

        for query in self.queries_for(analysis, case):
            for chunk in self.store.search(query, limit=2):
                if chunk.id in seen:
                    continue
                seen.add(chunk.id)
                answers.append(self._answer(query, chunk))
        return answers

    def _answer(self, query: str, chunk: EvidenceChunk) -> EvidenceAnswer:
        bundle = self.llm.complete(
            system=EVIDENCE_RULES,
            user=(
                f"QUESTION: {query}\n\n"
                f"SOURCE [{chunk.citation.source_id}] {chunk.citation.title}\n"
                f"Locator: {chunk.citation.locator}\n"
                f"Text: {chunk.text}\n\n"
                "Produce exactly one answer object in `answers`."
            ),
            schema=_EvidenceBundle,
        )
        draft = (
            bundle.answers[0]
            if bundle.answers
            else _EvidenceDraft(
                claim=chunk.text,
                applicability="Reported verbatim; applicability not assessed.",
            )
        )
        return EvidenceAnswer(
            query=query,
            claim=draft.claim,
            citation=chunk.citation,
            applicability=draft.applicability,
            limits=draft.limits,
        )
