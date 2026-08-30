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
import os
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


def _advisor_configuration_problem() -> str | None:
    """Return a safe configuration error, or None. Never exposes a credential.

    Phase C owns the rules, so the backend and `phase-c doctor` cannot drift
    apart on what counts as configured.
    """
    from phase_c.config import configuration_problems

    problems = configuration_problems()
    if not problems:
        return None
    return " ".join(problems)


@router.get("/advisor/status", response_model=AdvisorStatus)
def advisor_status() -> AdvisorStatus:
    """Whether the Phase C multi-agent layer can run here.

    Reports which watsonx environment is configured - the region endpoint and
    the model id - because an operator needs to see what the advice came from.
    The API key and the project id are account-scoped and never returned.
    """
    if not phase_c_advisor.PHASE_C_AVAILABLE:
        return AdvisorStatus(
            available=False,
            detail=f"phase_c not importable: {phase_c_advisor.PHASE_C_ERROR}",
        )
    configuration_problem = _advisor_configuration_problem()
    if configuration_problem:
        return AdvisorStatus(
            available=False,
            detail=f"Phase C is installed but not configured. {configuration_problem}",
        )

    from phase_c.config import fingerprint, value_sources

    return AdvisorStatus(
        available=True,
        configured=True,
        model_id=os.environ["WATSONX_MODEL_ID"].strip(),
        watsonx_url=os.environ["WATSONX_URL"].strip(),
        key_fingerprint=fingerprint(os.environ.get("WATSONX_API_KEY")),
        key_source=value_sources().get("WATSONX_API_KEY"),
        detail="Phase C advisor ready (IBM watsonx.ai).",
    )


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
    configuration_problem = _advisor_configuration_problem()
    if configuration_problem:
        raise HTTPException(
            status_code=503,
            detail=f"Advisor is not configured. {configuration_problem}",
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


# ─── Progress streaming ──────────────────────────────────────────────────────
#
# /api/simulate and /api/analyze stay exactly as they are — a single request,
# a single JSON answer. These two add a live view of the same work for a UI
# that would otherwise show a minute of unexplained spinner.
#
# The events report stages the pipeline actually reached. Nothing here
# interpolates against a clock: a run that stalls on one agent must look
# stalled, not keep creeping forward.

import queue  # noqa: E402
import threading  # noqa: E402

from fastapi.responses import StreamingResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402


def _json_default(value):
    """The two pipelines answer in different shapes — the simulator returns a
    Pydantic model, the advisor a plain dict — so serialisation is normalised
    here rather than at each call site."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _sse(event: str, payload: dict) -> str:
    body = json.dumps(payload, ensure_ascii=False, default=_json_default)
    return f"event: {event}\ndata: {body}\n\n"


def _stream_in_worker(work, *, on_progress_kwarg: str = "on_progress"):
    """Run `work` on a thread, forwarding its progress callbacks as SSE.

    The pipelines are synchronous and CPU/network bound, so they run off the
    event loop; the queue is the only thing crossing the thread boundary.
    """
    events: "queue.Queue[tuple[str, dict] | None]" = queue.Queue()
    outcome: dict = {}

    def report(*, stage: str, label: str, done: int, total: int) -> None:
        events.put(
            (
                "progress",
                {
                    "stage": stage,
                    "label": label,
                    "done": done,
                    "total": total,
                    "percent": round(done / total * 100) if total else 0,
                },
            )
        )

    def run() -> None:
        try:
            outcome["result"] = work(**{on_progress_kwarg: report})
        except Exception as exc:  # surfaced to the client as an error event
            outcome["error"] = exc
        finally:
            events.put(None)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()

    def generate():
        while True:
            item = events.get()
            if item is None:
                break
            name, payload = item
            yield _sse(name, payload)

        worker.join()
        error = outcome.get("error")
        if error is not None:
            yield _sse("error", {"detail": _stream_error_detail(error)})
            return
        yield _sse("progress", {"stage": "done", "label": "Complete",
                                "done": 1, "total": 1, "percent": 100})
        yield _sse("result", {"result": outcome.get("result")})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream_error_detail(error: Exception) -> str:
    """The same wording the non-streaming routes would have returned."""
    if isinstance(error, (KeyError, ValueError)):
        return str(error)
    return f"Advisor failed: {error}"


@router.post("/simulate/stream")
def stream_simulation(request: SimulateRequest) -> StreamingResponse:
    """POST /api/simulate with per-action progress events."""
    return _stream_in_worker(
        lambda on_progress: simulate(
            scenario=request.scenario,
            emergency=request.emergency,
            action_ids=request.actions,
            runs=request.runs,
            seed=request.seed,
            on_progress=on_progress,
        )
    )


@router.post("/analyze/stream")
def stream_analysis(request: AnalyzeRequest) -> StreamingResponse:
    """POST /api/analyze with per-agent progress events."""
    if not phase_c_advisor.PHASE_C_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"Phase C is not available: {phase_c_advisor.PHASE_C_ERROR}",
        )
    configuration_problem = _advisor_configuration_problem()
    if configuration_problem:
        raise HTTPException(
            status_code=503,
            detail=f"Advisor is not configured. {configuration_problem}",
        )
    return _stream_in_worker(
        lambda on_progress: phase_c_advisor.analyze(
            request.scenario,
            request.emergency,
            focus_action_id=request.focusActionId,
            samples=request.samples,
            seed=request.seed,
            on_progress=on_progress,
        )
    )
