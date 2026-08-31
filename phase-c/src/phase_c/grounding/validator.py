"""Machine grounding checks.

Prompt instructions alone do not stop fabrication. These do:

  R1  every numeric literal in prose must trace to the registry, to a cited
      evidence chunk, or sit in a non-numeric INFERENCE/ASSUMPTION claim
  R2  every SIMULATION_FACT claim must carry at least one resolving ref
  R3  sampled counts must never be phrased as probability/percentage
  R4  survival/mortality claims must be grounded like every other model output
  R5  "BEST ACTION" only from the Coordinator

Violations are returned, never silently corrected — the operator should see that
an agent attempted an unsupported assertion.
"""

import re

from phase_c.contracts.evidence import EvidenceAnswer
from phase_c.contracts.ethics import EthicalAssessment
from phase_c.contracts.findings import AgentFinding, Claim, GroundingViolation
from phase_c.grounding.registry import FactRegistry

# Matches 270, 270.0, 0.004, 1,000 — but not the digits inside identifiers such
# as M2, C3, or c_m1_m2, which are handled by masking identifiers out first.
_NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?![\w])")
_IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\d[A-Za-z0-9_]*\b")
_POINTER = re.compile(r"/[A-Za-z0-9_#/\-]*")

_PROBABILITY_WORDS = re.compile(
    r"\b(probabilit\w*|likelihood|chance[sd]?|odds|percent\w*)\b|%", re.IGNORECASE
)
_BEST_ACTION = re.compile(r"\bbest\s+action\b", re.IGNORECASE)

# Numbers that carry no factual load in prose ("one of the two hatches").
_STRUCTURAL_ALLOWANCE = {0.0, 1.0, 2.0}


def _numbers_in(text: str) -> list[float]:
    masked = _IDENTIFIER.sub(" ", text)
    masked = _POINTER.sub(" ", masked)
    values: list[float] = []
    for raw in _NUMBER.findall(masked):
        try:
            values.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return values


def _evidence_supports(value: float, evidence: list[EvidenceAnswer]) -> bool:
    for answer in evidence:
        haystack = f"{answer.claim} {answer.applicability} {answer.limits}"
        if value in _numbers_in(haystack):
            return True
    return False


def validate_finding(
    finding: AgentFinding,
    registry: FactRegistry,
    *,
    evidence: list[EvidenceAnswer] | None = None,
    allow_best_action: bool = False,
    action_prefix: str | None = None,
) -> list[GroundingViolation]:
    """Check one agent's claims against the tree that agent was shown.

    `action_prefix` is for the Coordinator alone. It reads a case-shaped payload
    where each action hangs under `/actions/<i>`, but the specialists' findings
    it synthesizes cite into their own single-action views, so it tends to copy
    a bare `/systems/...` that cannot resolve here. Given the recommended
    action's prefix, such a ref is retried under it: the claim is then about a
    real value and is recorded as an imprecision rather than a fabrication.
    Only the missing prefix is forgiven — a ref naming a field that does not
    exist stays a BLOCKER, because that is the case the rule exists to catch.
    """
    evidence = evidence or []
    violations: list[GroundingViolation] = []

    def add(rule: str, detail: str, claim: Claim | None = None, severity="MAJOR"):
        violations.append(
            GroundingViolation(
                agent=finding.agent,
                action_id=finding.action_id,
                rule=rule,
                detail=detail,
                claim_statement=claim.statement if claim else None,
                severity=severity,
            )
        )

    for claim in finding.claims:
        numbers = _numbers_in(claim.statement)

        # R2 — a simulation fact must point somewhere that resolves.
        if claim.basis == "SIMULATION_FACT":
            resolving = [r for r in claim.refs if registry.resolves(r)]
            rescued = (
                [
                    r
                    for r in claim.refs
                    if not registry.resolves(r)
                    and registry.resolves(f"{action_prefix}{r}")
                ]
                if action_prefix and not resolving
                else []
            )
            if not resolving and rescued:
                add(
                    "R2_action_scoped_ref",
                    f"Ref(s) {rescued!r} omit the action index and only resolve "
                    f"under {action_prefix!r}. The value is real; the pointer is "
                    "imprecise, so a reader cannot tell which action it means.",
                    claim,
                    "MINOR",
                )
            elif not resolving:
                add(
                    "R2_unreferenced_simulation_fact",
                    "SIMULATION_FACT claim has no ref that resolves against the "
                    f"analysis. refs={claim.refs!r}",
                    claim,
                    "BLOCKER",
                )

        # R1 — every number must be traceable.
        for value in numbers:
            if value in _STRUCTURAL_ALLOWANCE:
                continue
            if registry.supports_number(value):
                continue
            if _evidence_supports(value, evidence):
                continue
            add(
                "R1_unsupported_number",
                f"{value:g} appears in the claim but is not in the simulation "
                "output or any cited evidence.",
                claim,
                "BLOCKER",
            )

        # R3 — sampled counts are counts, not probabilities.
        # Pointers may be rooted at an action ("/sampled/...") or at the
        # whole case ("/actions/0/sampled/..."), so match the segment.
        touches_sampled = any(
            r == "/sampled" or "/sampled/" in r or r.endswith("/sampled")
            for r in claim.refs
        )
        if touches_sampled and _PROBABILITY_WORDS.search(claim.statement):
            add(
                "R3_sampled_as_probability",
                "Monte Carlo output is a count over sampled assumption sets. "
                "Rephrase as 'k of n sampled assumption sets'.",
                claim,
                "BLOCKER",
            )

    # R5 — scan every text surface the agent produced.
    surfaces = (
        [c.statement for c in finding.claims] + finding.concerns + finding.open_questions
    )
    for text in surfaces:
        if not allow_best_action and _BEST_ACTION.search(text):
            add(
                "R5_best_action_outside_coordinator",
                f"Only the Coordinator may recommend. Offending text: {text!r}",
                None,
                "MAJOR",
            )

    return violations


def validate_recommendation(
    recommendation,
    registry: FactRegistry,
    *,
    action_prefix: str | None = None,
    ethical_assessment: EthicalAssessment | None = None,
) -> list[GroundingViolation]:
    """A recommendation with no trade-off and no uncertainty is rejected — that
    shape is how these systems get over-trusted."""
    violations: list[GroundingViolation] = []

    def add(rule: str, detail: str, severity="MAJOR"):
        violations.append(
            GroundingViolation(
                agent="coordinator", rule=rule, detail=detail, severity=severity
            )
        )

    if not recommendation.tradeoffs:
        add(
            "R6_no_tradeoff",
            "A recommendation must name at least one trade-off against an "
            "alternative action.",
            "BLOCKER",
        )
    if not recommendation.uncertainty:
        add(
            "R7_no_uncertainty",
            "A recommendation must state what remains uncertain, including what "
            "the sampling did and did not cover.",
            "BLOCKER",
        )
    if not recommendation.human_decision_required:
        add(
            "R8_human_not_final",
            "human_decision_required must stay true: the operator decides.",
            "BLOCKER",
        )

    if ethical_assessment is not None:
        expected = ethical_assessment.selected_action_id
        if expected is not None and recommendation.recommended_action_id != expected:
            add(
                "E5_policy_selection_mismatch",
                f"Recommendation names {recommendation.recommended_action_id!r}, "
                f"but policy {ethical_assessment.policy_id} selected {expected!r}.",
                "BLOCKER",
            )
        if recommendation.policy_override_applied:
            add(
                "E6_coordinator_policy_override",
                f"The model proposed {recommendation.model_proposed_action_id!r}; "
                f"the deterministic policy enforced {recommendation.recommended_action_id!r}.",
                "MAJOR",
            )
        if recommendation.policy_id != ethical_assessment.policy_id:
            add(
                "E7_policy_provenance_mismatch",
                "Recommendation does not carry the policy id used by the evaluator.",
                "BLOCKER",
            )

    finding = AgentFinding(
        agent="coordinator",
        action_id=recommendation.recommended_action_id,
        claims=recommendation.rationale,
    )
    violations.extend(
        validate_finding(
            finding, registry, allow_best_action=True, action_prefix=action_prefix
        )
    )
    return violations


def validate_ethical_assessment(
    assessment: EthicalAssessment, valid_action_ids: set[str]
) -> list[GroundingViolation]:
    """Structural checks for the non-LLM policy stage."""

    violations: list[GroundingViolation] = []

    def add(rule: str, detail: str, severity="MAJOR"):
        violations.append(
            GroundingViolation(
                agent="ethics_policy",
                rule=rule,
                detail=detail,
                severity=severity,
            )
        )

    if assessment.selected_action_id not in valid_action_ids:
        add(
            "E1_unknown_policy_action",
            f"Policy selected unknown action {assessment.selected_action_id!r}.",
            "BLOCKER",
        )
    if assessment.selected_action_id not in assessment.co_recommended_action_ids:
        add(
            "E2_selected_action_not_co_recommended",
            "The selected action is absent from the policy's surviving candidates.",
            "BLOCKER",
        )
    if not assessment.sources:
        add(
            "E3_missing_policy_sources",
            "The ethical assessment has no checkable policy source.",
            "BLOCKER",
        )
    if not assessment.human_decision_required:
        add(
            "E4_ethics_claims_final_authority",
            "The ethical assessment must preserve human final authority.",
            "BLOCKER",
        )
    return violations
