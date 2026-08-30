"""Phase C pipeline.

    CaseAnalysis (from a SimulationProvider)
        -> specialist agents      (hazard, crew, systems, mission)
        -> evidence / RAG
        -> grounding validator    (machine, before the critic sees anything)
        -> critic / red-team
        -> coordinator
        -> DecisionPackage        -> human operator

Nothing here imports Phase A. The provider is injected.
"""

from typing import Callable, Protocol

from phase_c.agents.coordinator import CoordinatorAgent
from phase_c.agents.crew import CrewSafetyAgent
from phase_c.agents.critic import CriticAgent
from phase_c.agents.evidence import EvidenceAgent
from phase_c.agents.hazard import HazardAgent
from phase_c.agents.mission import MissionAgent
from phase_c.agents.systems import SystemsAgent
from phase_c.contracts.analysis import ActionAnalysis, CaseAnalysis
from phase_c.contracts.findings import DecisionPackage, GroundingViolation
from phase_c.grounding.registry import FactRegistry
from phase_c.grounding.validator import validate_finding, validate_recommendation
from phase_c.llm.base import LLMClient
from phase_c.rag.store import EvidenceStore


class ProgressSink(Protocol):
    """Told which stage is starting and how far through the run it is.

    The pipeline is a minute of silence otherwise. Reporting real stage
    transitions rather than a timer keeps the progress honest: it moves when
    work actually completes, and stalls visibly when something is slow.
    """

    def __call__(self, *, stage: str, label: str, done: int, total: int) -> None:
        ...


# The seven agents, in the order they run. Named here so the pipeline and the
# progress readout cannot drift apart.
STAGES: list[tuple[str, str]] = [
    ("evidence", "Retrieving NASA evidence"),
    ("hazard", "Hazard analyst"),
    ("crew_safety", "Crew safety analyst"),
    ("systems", "Systems analyst"),
    ("mission", "Mission analyst"),
    ("critic", "Red-team critic"),
    ("coordinator", "Coordinator"),
]


class Orchestrator:
    def __init__(
        self,
        llm: LLMClient,
        *,
        evidence_store: EvidenceStore | None = None,
        focus_action_id: str | None = None,
    ) -> None:
        self.llm = llm
        self.specialists = [
            HazardAgent(llm),
            CrewSafetyAgent(llm),
            SystemsAgent(llm),
            MissionAgent(llm),
        ]
        self.evidence_agent = EvidenceAgent(llm, evidence_store)
        self.critic = CriticAgent(llm)
        self.coordinator = CoordinatorAgent(llm)
        self.focus_action_id = focus_action_id

    def _focus(self, case: CaseAnalysis) -> ActionAnalysis:
        """The action the specialists analyze in depth. Defaults to the
        do-nothing baseline when present, else the first action."""
        if self.focus_action_id:
            return case.action(self.focus_action_id)
        for analysis in case.actions:
            if analysis.action.kind == "do_nothing":
                return analysis
        if not case.actions:
            raise ValueError("CaseAnalysis contains no actions")
        return case.actions[0]

    def run(
        self,
        case: CaseAnalysis,
        *,
        on_progress: ProgressSink | Callable[..., None] | None = None,
    ) -> DecisionPackage:
        total = len(STAGES)
        done = 0

        def announce(stage: str, label: str) -> None:
            """Report a stage as it begins, so the reader sees what is running
            now rather than what finished a moment ago."""
            if on_progress is not None:
                on_progress(stage=stage, label=label, done=done, total=total)

        focus = self._focus(case)

        announce(*STAGES[0])
        evidence = self.evidence_agent.gather(focus, case)
        done += 1

        findings = []
        violations: list[GroundingViolation] = []
        for agent, (stage, label) in zip(self.specialists, STAGES[1:5]):
            announce(stage, label)
            finding = agent.analyze(focus, case)
            findings.append(finding)
            # Checked against the agent's own projection, which is the tree it
            # was told to cite into. Each specialist sees a different shape -
            # the mission agent's data has /sampled_capability_counts, the
            # systems agent's has /equipment - so validating them all against
            # one shared tree marks sound citations unreferenced.
            violations.extend(
                validate_finding(
                    finding,
                    FactRegistry.from_payload(agent.project(focus, case)),
                    evidence=evidence,
                )
            )
            done += 1

        announce(*STAGES[5])
        critic_review = self.critic.review(
            findings, focus, case, violations=violations
        )
        done += 1

        announce(*STAGES[6])
        recommendation = self.coordinator.recommend(
            case, findings, critic_review, evidence
        )
        done += 1
        recommendation_violations = validate_recommendation(
            recommendation,
            FactRegistry.from_payload(
                self.coordinator.payload(case, findings, critic_review, evidence)
            ),
        )
        critic_review.grounding_violations.extend(recommendation_violations)

        return DecisionPackage(
            scenario_digest=case.scenario_digest,
            findings=findings,
            evidence=evidence,
            critic=critic_review,
            recommendation=recommendation,
            provenance={
                "focus_action_id": focus.action.id,
                "engine": focus.provenance.engine,
                "horizon_seconds": focus.provenance.horizon_seconds,
                "dt_seconds": focus.provenance.dt_seconds,
                "seed": focus.provenance.seed,
                "ethics_notice": focus.provenance.ethics_notice,
                "criticality_baseline_action": case.criticality_baseline_action,
                "sampling_note": (
                    "Monte Carlo values are counts over sampled assumption sets, "
                    "not validated real-world probabilities."
                ),
                "agents": [a.name for a in self.specialists]
                + ["evidence", "critic", "coordinator"],
            },
        )
