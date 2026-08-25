"""Machine grounding checks (plan §7).

Prompt instructions alone do not stop fabrication. These do:

  R1  every numeric literal in prose must trace to the registry, to a cited
      evidence chunk, or sit in a non-numeric INFERENCE/ASSUMPTION claim
  R2  every SIMULATION_FACT claim must carry at least one resolving ref
  R3  sampled counts must never be phrased as probability/percentage
  R4  no fatality or survival-probability phrasing, anywhere
  R5  "BEST ACTION" only from the Coordinator

Violations are returned, never silently corrected — the operator should see that
an agent attempted an unsupported assertion.
"""

import re

from phase_c.contracts.evidence import EvidenceAnswer
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
_FATALITY_WORDS = re.compile(
    r"\b(fatalit\w*|death\w*|died|dies|lethal\w*|kill\w*|"
    r"survival\s+(?:probabilit\w*|rate|chance\w*)|mortalit\w*)\b",
    re.IGNORECASE,
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
) -> list[GroundingViolation]:
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
            if not resolving:
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

    # R4/R5 — scan every text surface the agent produced.
    surfaces = (
        [c.statement for c in finding.claims] + finding.concerns + finding.open_questions
    )
    for text in surfaces:
        if _FATALITY_WORDS.search(text):
            add(
                "R4_fatality_language",
                "The engine models crew states and exposure, never fatality. "
                f"Offending text: {text!r}",
                None,
                "BLOCKER",
            )
        if not allow_best_action and _BEST_ACTION.search(text):
            add(
                "R5_best_action_outside_coordinator",
                f"Only the Coordinator may recommend. Offending text: {text!r}",
                None,
                "MAJOR",
            )

    return violations


def validate_recommendation(recommendation, registry: FactRegistry) -> list[GroundingViolation]:
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

    finding = AgentFinding(
        agent="coordinator",
        action_id=recommendation.recommended_action_id,
        claims=recommendation.rationale,
    )
    violations.extend(
        validate_finding(finding, registry, allow_best_action=True)
    )
    return violations
