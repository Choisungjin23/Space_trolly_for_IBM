"""
FastAPI routes for Phase B.

Three endpoints:
  GET  /api/templates          — list available scenario templates
  GET  /api/templates/{id}     — full scenario JSON for a given template
  POST /api/simulate           — run mock simulation against a user scenario

Route handlers are thin. All logic is in app/adapters/mock_simulator.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    AdvisorStatus,
    AnalyzeRequest,
    ScenarioIn,
    SimulateRequest,
    SimulationResponse,
    TemplateSummary,
)

# Prefer the real Phase A engine; fall back to the mock only when the
# spacecraft_sim package cannot be located (see phase_a_simulator's bootstrap).
try:
    from app.adapters.phase_a_simulator import simulate

    ACTIVE_ADAPTER = "PhaseASimulatorAdapter"
except ImportError:  # pragma: no cover - depends on environment
    from app.adapters.mock_simulator import simulate

    ACTIVE_ADAPTER = "MockSimulatorAdapter (Phase A engine not found)"

router = APIRouter()

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# Registry of available templates (id → fixture filename)
TEMPLATE_REGISTRY: dict[str, str] = {
    "five-module-demo": "five_module_demo.json",
}

TEMPLATE_META: list[TemplateSummary] = [
    TemplateSummary(
        id="five-module-demo",
        name="5-Module Spacecraft Fire Demo",
        description="5 modules, 4 crew, example equipment, fire in Storage",
    ),
]


@router.get("/templates", response_model=list[TemplateSummary])
def list_templates() -> list[TemplateSummary]:
    """Return available scenario templates."""
    return TEMPLATE_META


@router.get("/templates/{template_id}", response_model=ScenarioIn)
def get_template(template_id: str) -> dict:
    """
    Return the full scenario payload for a given template ID.
    The response shape matches the `scenario` field in SimulateRequest.
    """
    if template_id not in TEMPLATE_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    fixture_path = FIXTURES_DIR / TEMPLATE_REGISTRY[template_id]
    if not fixture_path.exists():
        raise HTTPException(status_code=500, detail="Template fixture file missing")
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@router.post("/simulate", response_model=SimulationResponse)
def run_simulation(request: SimulateRequest) -> SimulationResponse:
    """
    Run mock simulation for the user-supplied scenario.

    The scenario comes entirely from the request body — no server-side
    fixed topology. The MockSimulatorAdapter generates actions and results
    from the graph described in the request.

    When Phase A ships, replace MockSimulatorAdapter with PhaseASimulatorAdapter
    implementing the same interface.
    """
    try:
        return simulate(
            scenario=request.scenario,
            emergency=request.emergency,
            action_ids=request.actions,
            runs=request.runs,
            seed=request.seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

# ─── Phase C advisor ─────────────────────────────────────────────────────────

from app.adapters import phase_c_advisor  # noqa: E402


@router.get("/advisor/status", response_model=AdvisorStatus)
def advisor_status() -> AdvisorStatus:
    """Whether the Phase C multi-agent layer can run here."""
    if not phase_c_advisor.PHASE_C_AVAILABLE:
        return AdvisorStatus(
            available=False,
            detail=f"phase_c not importable: {phase_c_advisor.PHASE_C_ERROR}",
        )
    import os

    if not (os.environ.get("WATSONX_API_KEY") and os.environ.get("WATSONX_PROJECT_ID")):
        return AdvisorStatus(
            available=False,
            detail=(
                "phase_c is installed but no LLM is configured. Set "
                "WATSONX_API_KEY and WATSONX_PROJECT_ID to enable the advisor."
            ),
        )
    return AdvisorStatus(available=True, detail="Phase C advisor ready (IBM Granite).")


@router.post("/analyze")
def analyze_emergency(request: AnalyzeRequest) -> dict:
    """Run the Phase C pipeline and return a DecisionPackage.

    Slower than /api/simulate by design: seven agents run on top of the
    simulation. The recommendation is advisory; the operator decides.
    """
    if not phase_c_advisor.PHASE_C_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"Phase C is not available: {phase_c_advisor.PHASE_C_ERROR}",
        )
    try:
        return phase_c_advisor.analyze(
            request.scenario,
            request.emergency,
            focus_action_id=request.focusActionId,
            samples=request.samples,
            seed=request.seed,
        )
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Advisor failed: {exc}") from exc
