"""PhaseASimulationAdapter — the ONLY file in Phase C that imports Phase A.

Closes every gap listed in phase-a-contract.md §8:

1. TimelineResult is a plain dataclass      -> read attributes, model_dump() the final Scenario
2. Distribution is a separate call/object   -> joined here, per action
3. summary is a plain dict                  -> validated into pydantic at this boundary
4. equipment absent from summary            -> pulled from final.equipment
5. timeline is 120 heavy frames             -> replaced by semantic events
6. capability keys are scenario-defined     -> iterated, never named in code
7. MC has fixed return/habitation fields    -> keyed by scenario capability names
8. detected_at_seconds may be null          -> first-class NEVER_DETECTED
9. no JSON CLI mode                         -> serialized in-process; Phase A unchanged

Phase A is never mutated: scenarios are deep-copied before every engine call.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

# ── Phase A import bootstrap ────────────────────────────────────────────────
_DEFAULT_PHASE_A_SRC = Path(__file__).resolve().parents[4] / "spacecraft-sim" / "src"

try:  # pragma: no cover - depends on environment
    import spacecraft_sim  # noqa: F401
except ImportError:  # pragma: no cover
    _candidate = Path(os.environ.get("SPACECRAFT_SIM_SRC", _DEFAULT_PHASE_A_SRC))
    if (_candidate / "spacecraft_sim").is_dir():
        sys.path.insert(0, str(_candidate))
    import spacecraft_sim  # noqa: F401

from spacecraft_sim import __version__ as PHASE_A_VERSION
from spacecraft_sim import config as pa_config
from spacecraft_sim.actions import find_action, generate_actions
from spacecraft_sim.crew import measured_criticality
from spacecraft_sim.engine import counterfactual
from spacecraft_sim.montecarlo import run_montecarlo

from phase_c.contracts.analysis import (
    ActionAnalysis,
    ActionRef,
    CapabilityCount,
    CaseAnalysis,
    CrewCriticality,
    CrewOutcome,
    ConnectivityOutcome,
    Detection,
    EquipmentOutcome,
    Hazard,
    Provenance,
    ResourceOutcome,
    ReturnCapability,
    SampledOutcome,
)
from phase_c.timeline.events import extract_events

# Counts that hold for any scenario, regardless of capability naming.
_CAPABILITY_AGNOSTIC_COUNTS = (
    "hazard_contained_to_sources",
    "no_crew_trapped",
    "all_crew_safe_or_evacuated",
    "no_crew_reached_smac_dose",
    "retained_evacuation_and_return",
)


def load_scenario(path):
    """Parse a Phase A scenario JSON. Lives here so that this module stays the
    single point of contact with the engine (see test_adapter isolation test)."""
    from spacecraft_sim.models import Scenario

    return Scenario.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _case_warnings(scenario) -> list[str]:
    """Say when a number means "not asked" rather than "answered well".

    An undeclared return capability is the important one: the engine defaults it
    to available, so every action reports expected_returnees == expected_survivors
    and the coordinator's first objective silently stops discriminating.
    """
    warnings: list[str] = []
    name = scenario.return_capability_name
    if name not in scenario.capabilities:
        warnings.append(
            f"This scenario declares no {name} capability, so the ability to "
            f"come home was never judged. expected_returnees equals "
            f"expected_survivors for every action by construction, not because "
            f"return was assured — do not read the two being equal as evidence."
        )
    if not scenario.systems:
        warnings.append(
            "This scenario declares no systems, so every system-state and "
            "capability field is empty. Say so rather than reporting that "
            "nothing is degraded."
        )
    return warnings


def _digest(scenario) -> str:
    return hashlib.sha256(scenario.model_dump_json().encode("utf-8")).hexdigest()[:12]


class PhaseASimulationAdapter:
    """Normalizes Phase A output into the Phase C analysis contract."""

    def __init__(
        self,
        *,
        horizon_seconds: float | None = None,
        dt_seconds: float | None = None,
        default_samples: int = 50,
    ) -> None:
        self.horizon_seconds = (
            pa_config.HORIZON_SECONDS if horizon_seconds is None else horizon_seconds
        )
        self.dt_seconds = pa_config.DT_SECONDS if dt_seconds is None else dt_seconds
        self.default_samples = default_samples

    # ── actions ─────────────────────────────────────────────────────────────
    def list_actions(self, scenario) -> list[ActionRef]:
        return [
            ActionRef(
                id=a.id,
                kind=a.kind,
                label=a.label,
                description=a.description,
                params=dict(a.params),
            )
            for a in generate_actions(scenario.model_copy(deep=True))
        ]

    # ── one action ──────────────────────────────────────────────────────────
    def analyze_action(
        self,
        scenario,
        action_id: str,
        *,
        samples: int | None = None,
        seed: int | None = None,
    ) -> ActionAnalysis:
        base = scenario.model_copy(deep=True)
        action = find_action(base, action_id)

        result = counterfactual(
            base, action, horizon=self.horizon_seconds, dt=self.dt_seconds
        )
        summary = result.summary
        final = result.final

        detected_at = summary.get("detected_at_seconds")
        detection = Detection(
            status="DETECTED" if detected_at is not None else "NEVER_DETECTED",
            detected_at_seconds=detected_at,
        )

        hazard = Hazard(
            reached_modules=list(summary.get("hazard_reached", [])),
            smac_exceeded_modules=list(summary.get("smac_exceeded", [])),
            peak_extinction_per_m=dict(summary.get("peak_extinction_per_m", {})),
        )

        crew = {
            crew_id: CrewOutcome(
                state=info["state"],
                exposure_seconds=info["exposure_seconds"],
                smac_dose_fraction=info["smac_dose_fraction"],
                module=info["module"],
                survival_probability=info["survival_probability"],
                return_probability=info["return_probability"],
                abandoned=info["abandoned"],
                priority_score=info.get("priority_score", 0.0),
                priority_rank=info.get("priority_rank"),
                priority_reasons=info.get("priority_reasons", []),
                waiting_for_connection_id=info.get("waiting_for_connection_id"),
                estimated_survival_minutes=info.get("estimated_survival_minutes"),
                resource_risk_reasons=info.get("resource_risk_reasons", []),
            )
            for crew_id, info in summary.get("crew", {}).items()
        }

        # Gap 4: equipment lives only on `final`.
        equipment = {
            item.id: EquipmentOutcome(
                name=item.name,
                module=item.module_id,
                system=item.system,
                powered=item.powered,
                damaged=item.damaged,
                repair_progress_seconds=item.repair_progress_seconds,
                portable=item.portable,
                passage_units=item.passage_units,
                priority_score=item.evacuation_priority_score,
                priority_rank=item.evacuation_priority_rank,
                priority_reasons=list(item.priority_reasons),
                evacuated=item.evacuated,
            )
            for item in (final.equipment if final else [])
        }

        capability_map = dict(final.capabilities) if final else {}
        events = extract_events(
            result.timeline,
            detected_at_seconds=detected_at,
            smac_exceeded_modules=hazard.smac_exceeded_modules,
            capability_map=capability_map,
        )

        sampled = None
        n = self.default_samples if samples is None else samples
        if n and n > 0:
            sampled = self._sample(base, action, n, seed, summary.get("capabilities", {}))

        return ActionAnalysis(
            action=ActionRef(
                id=action.id,
                kind=action.kind,
                label=action.label,
                description=action.description,
                params=dict(action.params),
            ),
            detection=detection,
            hazard=hazard,
            crew=crew,
            crew_counts=dict(summary.get("crew_counts", {})),
            resources={
                module_id: ResourceOutcome.model_validate(values)
                for module_id, values in summary.get("resources", {}).items()
            },
            expected_survivors=summary.get("expected_survivors", 0.0),
            expected_returnees=summary.get("expected_returnees", 0.0),
            return_capability=(
                ReturnCapability.model_validate(summary["return_capability"])
                if summary.get("return_capability")
                else None
            ),
            systems=dict(summary.get("systems", {})),
            system_reasons=dict(summary.get("system_reasons", {})),
            equipment=equipment,
            connectivity={
                connection_id: ConnectivityOutcome.model_validate(values)
                for connection_id, values in summary.get("connectivity", {}).items()
            },
            escape_target=summary.get("escape_target"),
            capabilities=dict(summary.get("capabilities", {})),
            critical_functions=list(summary.get("critical_functions", [])),
            events=events,
            sampled=sampled,
            provenance=Provenance(
                engine=f"spacecraft_sim {PHASE_A_VERSION}",
                horizon_seconds=self.horizon_seconds,
                dt_seconds=self.dt_seconds,
                seed=seed,
                ethics_notice=pa_config.ETHICS_NOTICE,
            ),
        )

    def _sample(
        self, scenario, action, n: int, seed: int | None, capabilities: dict
    ) -> SampledOutcome:
        distribution = run_montecarlo(
            scenario.model_copy(deep=True),
            action,
            n=n,
            seed=seed,
            horizon=self.horizon_seconds,
            dt=self.dt_seconds,
        )

        counts = {
            field: getattr(distribution, field)
            for field in _CAPABILITY_AGNOSTIC_COUNTS
            if hasattr(distribution, field)
        }

        # Phase A's Distribution has two fixed semantic fields, but Scenario
        # lets callers name those capabilities. Preserve the scenario's names
        # and mark a count inapplicable when that capability was not declared.
        capability_count_fields = {
            scenario.return_capability_name: "return_available",
            scenario.habitation_capability_name: "habitation_available",
        }
        capability_counts: dict[str, CapabilityCount] = {}
        for capability_name, field in capability_count_fields.items():
            if not hasattr(distribution, field):
                continue
            declared = capability_name in capabilities
            capability_counts[capability_name] = CapabilityCount(
                available=getattr(distribution, field) if declared else 0,
                applicable=declared,
            )

        return SampledOutcome(
            samples=distribution.samples,
            counts=counts,
            capability_counts=capability_counts,
            means={
                "total_exposure_seconds": distribution.mean_total_exposure_seconds,
                "peak_smac_dose": distribution.mean_peak_smac_dose,
                "expected_survivors": distribution.mean_expected_survivors,
                "expected_returnees": distribution.mean_expected_returnees,
            },
            notes=list(distribution.notes),
        )

    # ── whole case ──────────────────────────────────────────────────────────
    def analyze_case(
        self,
        scenario,
        *,
        action_ids: list[str] | None = None,
        samples: int | None = None,
        seed: int | None = None,
    ) -> CaseAnalysis:
        available = self.list_actions(scenario)
        available_ids = {a.id for a in available}

        if action_ids is None:
            selected = [a.id for a in available]
        else:
            unknown = [a for a in action_ids if a not in available_ids]
            if unknown:
                raise KeyError(f"Unknown action id(s) for this scenario: {unknown}")
            selected = list(action_ids)

        analyses = [
            self.analyze_action(scenario, action_id, samples=samples, seed=seed)
            for action_id in selected
        ]

        # measured_criticality is action-scoped in Phase A; agents compare across
        # actions, so run it once for a named baseline and label which one.
        baseline_id = "do_nothing" if "do_nothing" in available_ids else selected[0]
        base = scenario.model_copy(deep=True)
        criticality = [
            CrewCriticality(**row)
            for row in measured_criticality(
                base,
                find_action(base, baseline_id),
                horizon=self.horizon_seconds,
                dt=self.dt_seconds,
            )
        ]

        return CaseAnalysis(
            scenario_digest=_digest(scenario),
            mission_phase=scenario.mission_phase,
            capability_names=sorted(scenario.capabilities),
            criticality=criticality,
            criticality_baseline_action=baseline_id,
            warnings=_case_warnings(scenario),
            actions=analyses,
        )
