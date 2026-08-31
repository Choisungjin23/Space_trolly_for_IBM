"""Deterministic human-preservation policy evaluator.

The LLM never chooses the policy winner.  It receives this assessment after the
ranking is complete and may only explain it.  The evaluator reads modeled human
outcomes, never crew names, demographics, social status, or rank.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from phase_c.contracts.analysis import ActionAnalysis, CaseAnalysis
from phase_c.contracts.ethics import (
    ActionEthicsAssessment,
    EthicalAssessment,
    PolicyCheck,
    TieBreakStep,
)
from phase_c.rag.store import EvidenceStore

POLICY_PATH = Path(__file__).with_name("policy.json")


class _Rule(BaseModel):
    rule_id: str
    title: str
    description: str
    source_ids: list[str] = Field(default_factory=list)


class _Criterion(BaseModel):
    field: str
    direction: Literal["MAXIMIZE", "MINIMIZE"]
    tie_margin: float = 0.0
    description: str


class _Policy(BaseModel):
    policy_id: str
    version: str
    status: str
    title: str
    source_ids: list[str]
    prohibited_personal_attributes: list[str]
    rules: list[_Rule]
    criteria: list[_Criterion]
    limitations: list[str]


def load_policy(path: Path | None = None) -> _Policy:
    source = path or POLICY_PATH
    return _Policy.model_validate(json.loads(source.read_text(encoding="utf-8")))


def _finite(value: float) -> bool:
    return math.isfinite(float(value))


class EthicsEvaluator:
    def __init__(
        self,
        evidence_store: EvidenceStore | None = None,
        *,
        policy_path: Path | None = None,
    ) -> None:
        self.policy = load_policy(policy_path)
        self.evidence_store = evidence_store or EvidenceStore.from_corpus()

    def _assessment_for(
        self, analysis: ActionAnalysis, action_index: int
    ) -> ActionEthicsAssessment:
        crew = analysis.crew
        probabilities = [member.survival_probability for member in crew.values()]
        doses = [member.smac_dose_fraction for member in crew.values()]
        minimum_survival = min(probabilities) if probabilities else None
        maximum_dose = max(doses) if doses else None

        numeric_values = [analysis.expected_returnees, analysis.expected_survivors]
        numeric_values.extend(probabilities)
        numeric_values.extend(doses)
        valid = all(_finite(value) for value in numeric_values)
        probabilities_valid = all(0.0 <= value <= 1.0 for value in probabilities)
        eligible = valid and probabilities_valid

        affected = sorted(
            crew_id
            for crew_id, member in crew.items()
            if member.state != "SAFE"
            or member.abandoned
            or member.survival_probability < 1.0
            or member.smac_dose_fraction > 0.0
        )

        checks: list[PolicyCheck] = []
        for rule in self.policy.rules:
            status: Literal["PASS", "REVIEW", "BLOCK"] = "PASS"
            summary = rule.description
            if rule.rule_id == "HP-001" and not crew:
                status = "REVIEW"
                summary = (
                    "No crew outcomes are present, so the human-preservation "
                    "ordering cannot distinguish this action."
                )
            if not eligible:
                status = "BLOCK"
                summary = "Human-outcome values are non-finite or outside valid bounds."
            refs = [f"policy:{rule.rule_id}"] + [
                f"evidence:{source_id}" for source_id in rule.source_ids
            ]
            if rule.rule_id == "HP-001":
                refs.extend(
                    [
                        f"/actions/{action_index}/expected_returnees",
                        f"/actions/{action_index}/expected_survivors",
                    ]
                )
            checks.append(
                PolicyCheck(
                    rule_id=rule.rule_id,
                    status=status,
                    summary=summary,
                    refs=refs,
                )
            )

        return ActionEthicsAssessment(
            action_id=analysis.action.id,
            eligible=eligible,
            expected_returnees=analysis.expected_returnees,
            expected_survivors=analysis.expected_survivors,
            minimum_crew_survival_probability=minimum_survival,
            abandoned_crew_count=sum(member.abandoned for member in crew.values()),
            trapped_crew_count=sum(member.state == "TRAPPED" for member in crew.values()),
            maximum_smac_dose_fraction=maximum_dose,
            smac_exceeded_module_count=len(analysis.hazard.smac_exceeded_modules),
            hazard_reached_module_count=len(analysis.hazard.reached_modules),
            affected_crew_ids=affected,
            policy_checks=checks,
        )

    @staticmethod
    def _criterion_value(
        action: ActionEthicsAssessment, field: str
    ) -> float:
        value = getattr(action, field)
        if value is None:
            # Missing crew metrics cannot defeat a measured human outcome.  If
            # every action is missing it they remain tied and require review.
            return 0.0
        return float(value)

    def evaluate(self, case: CaseAnalysis) -> EthicalAssessment:
        if not case.actions:
            raise ValueError("Cannot evaluate ethics for a case with no actions")

        action_assessments = [
            self._assessment_for(action, index)
            for index, action in enumerate(case.actions)
        ]
        candidates = [action for action in action_assessments if action.eligible]
        steps: list[TieBreakStep] = []

        for criterion in self.policy.criteria:
            if len(candidates) <= 1:
                break
            values = [
                self._criterion_value(candidate, criterion.field)
                for candidate in candidates
            ]
            best = max(values) if criterion.direction == "MAXIMIZE" else min(values)
            remaining = [
                candidate
                for candidate in candidates
                if abs(self._criterion_value(candidate, criterion.field) - best)
                <= criterion.tie_margin
            ]
            steps.append(
                TieBreakStep(
                    criterion=criterion.field,
                    direction=criterion.direction,
                    best_value=best,
                    tie_margin=criterion.tie_margin,
                    remaining_action_ids=[item.action_id for item in remaining],
                    explanation=criterion.description,
                )
            )
            candidates = remaining

        co_recommended_ids = sorted(candidate.action_id for candidate in candidates)
        selected_action_id = co_recommended_ids[0] if co_recommended_ids else None
        for action in action_assessments:
            action.co_recommended = action.action_id in co_recommended_ids

        source_chunks = []
        missing_sources = []
        for source_id in self.policy.source_ids:
            try:
                source_chunks.append(self.evidence_store.get_by_source_id(source_id))
            except KeyError:
                missing_sources.append(source_id)

        selected = next(
            (item for item in action_assessments if item.action_id == selected_action_id),
            None,
        )
        selected_needs_review = bool(
            selected
            and any(check.status != "PASS" for check in selected.policy_checks)
        )
        if not candidates:
            status = "BLOCKED"
            selection_basis = "No action has valid human-outcome data."
        elif len(candidates) > 1:
            status = "REVIEW_REQUIRED"
            selection_basis = (
                "The declared human-preservation criteria did not separate all "
                "remaining actions; they are co-recommended for human review."
            )
        elif missing_sources or selected_needs_review:
            status = "REVIEW_REQUIRED"
            selection_basis = (
                "One action ranks first, but policy evidence or human-outcome "
                "coverage is incomplete and requires operator review."
            )
        else:
            status = "POLICY_CONSISTENT"
            deciding_step = next(
                (step for step in reversed(steps) if len(step.remaining_action_ids) == 1),
                None,
            )
            selection_basis = (
                deciding_step.explanation
                if deciding_step
                else "The action is the only policy-eligible candidate."
            )

        limitations = list(self.policy.limitations)
        if missing_sources:
            limitations.append(
                "Missing policy evidence source(s): " + ", ".join(missing_sources)
            )

        return EthicalAssessment(
            policy_id=self.policy.policy_id,
            policy_version=self.policy.version,
            status=status,
            selected_action_id=selected_action_id,
            co_recommended_action_ids=co_recommended_ids,
            selection_basis=selection_basis,
            action_assessments=action_assessments,
            tie_break_steps=steps,
            sources=[chunk.citation for chunk in source_chunks],
            limitations=limitations,
            human_decision_required=True,
        )
