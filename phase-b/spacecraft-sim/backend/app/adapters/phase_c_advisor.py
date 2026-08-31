"""Phase C bridge for the Phase B product layer.

Phase B already translates its camelCase scenario into a Phase A `Scenario`
(see `phase_a_simulator.to_phase_a_scenario`). Phase C then consumes that same
Scenario through its own adapter, so the two paths share the engine but not
code.

Availability is optional at import time: if `phase_c` is not installed, the
`/api/analyze` route reports it rather than crashing the whole backend.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from app.adapters.phase_a_simulator import (
    _action_pairs,
    to_phase_a_action_id,
    to_phase_a_scenario,
)
from app.api.schemas import EmergencyConfigIn, ScenarioIn

_DEFAULT_PHASE_C_SRC = Path(__file__).resolve().parents[5] / "phase-c" / "src"

PHASE_C_AVAILABLE = False
PHASE_C_ERROR: str | None = None

try:
    import phase_c  # noqa: F401

    PHASE_C_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on environment
    _candidate = Path(os.environ.get("PHASE_C_SRC", _DEFAULT_PHASE_C_SRC))
    if (_candidate / "phase_c").is_dir():
        sys.path.insert(0, str(_candidate))
    try:
        import phase_c  # noqa: F401

        PHASE_C_AVAILABLE = True
    except ImportError as exc:
        PHASE_C_ERROR = str(exc)

if PHASE_C_AVAILABLE:
    from phase_c.llm.base import LLMError
    from phase_c.orchestrator import Orchestrator
    from phase_c.providers.phase_a import PhaseASimulationAdapter


def _build_llm(prefer_granite: bool):
    """Granite when credentials are present, otherwise raise a clear error.

    Phase C's StubLLMClient is a test double and deliberately refuses to invent
    findings, so it is not offered as a silent production fallback.
    """
    from phase_c.llm.granite import GraniteClient

    if not prefer_granite:
        raise LLMError("Advisor requires an LLM; set use_granite=true.")
    return GraniteClient()


def analyze(
    scenario: ScenarioIn,
    emergency: EmergencyConfigIn,
    *,
    focus_action_id: Optional[str] = None,
    samples: int = 20,
    seed: Optional[int] = 42,
    llm=None,
    on_progress=None,
) -> dict:
    """Run the Phase C pipeline over a Phase B scenario. Returns a
    DecisionPackage as a plain dict, ready for JSON."""
    if not PHASE_C_AVAILABLE:  # pragma: no cover
        raise RuntimeError(f"phase_c is not importable: {PHASE_C_ERROR}")

    pa_scenario = to_phase_a_scenario(scenario, emergency)

    # The caller is Phase B (and ultimately the results table), so the focus
    # action arrives under its Phase B id. Phase C indexes by the engine's id.
    if focus_action_id is not None:
        focus_action_id = to_phase_a_action_id(scenario, emergency, focus_action_id)

    provider = PhaseASimulationAdapter(default_samples=samples)
    case = provider.analyze_case(pa_scenario, samples=samples, seed=seed)

    client = llm if llm is not None else _build_llm(True)
    orchestrator = Orchestrator(client, focus_action_id=focus_action_id)
    package = orchestrator.run(case, on_progress=on_progress).model_dump(mode="json")

    # Phase C names actions the engine's way (`isolate:mod-storage`); the
    # results table names them Phase B's way (`isolate_module_mod-storage`).
    # Carrying the mapping lets the UI line a recommendation up with its
    # simulated outcome instead of re-deriving the translation client-side.
    package.setdefault("provenance", {})["action_id_map"] = {
        pa_action.id: spec.id for spec, pa_action, _ in _action_pairs(scenario, emergency)
    }
    package["provenance"]["decision_objective"] = (
        "lexicographic_human_preservation_policy_v1"
    )
    return package
