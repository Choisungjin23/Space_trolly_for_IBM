"""API routes. Thin handlers only — all simulation logic lives in app/simulation."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.config import DEFAULT_CONFIG, FIELD_SPECS, build_config
from app.domain.scenario import CREW_DEFS, MODULE_DEFS, build_initial_scenario
from app.simulation.actions import available_actions
from app.simulation.monte_carlo import simulate_actions
from app.api.schemas import (
    ConfigOut,
    ScenarioOut,
    ScenarioRequest,
    SimulateRequest,
    SimulateResponse,
)

router = APIRouter(prefix="/api")


def _scenario_payload(settings) -> ScenarioOut:
    cfg = build_config(settings.model_dump(exclude_none=True) if settings else None)
    state = build_initial_scenario(cfg)
    return ScenarioOut(
        modules={mid: asdict(m) for mid, m in state.modules.items()},
        connections=[asdict(c) for c in state.connections],
        critical_systems=list(cfg.critical_systems),
        actions=[
            {"id": a.id, "label": a.label, "description": a.description}
            for a in available_actions(state)
        ],
    )


@router.get("/config", response_model=ConfigOut)
def get_config() -> ConfigOut:
    """Default parameter values plus the control metadata the GUI renders."""
    defaults = asdict(DEFAULT_CONFIG)
    defaults["crew_placement"] = dict(DEFAULT_CONFIG.crew_placement)
    return ConfigOut(
        defaults=defaults,
        fields=FIELD_SPECS,
        modules=[{"id": mid, "name": name} for mid, name, _ in MODULE_DEFS],
        crew=[{"id": cid, "name": name} for cid, name in CREW_DEFS],
    )


@router.get("/scenario", response_model=ScenarioOut)
def get_scenario() -> ScenarioOut:
    """Default scenario. Use POST /api/scenario to preview edited settings."""
    return _scenario_payload(None)


@router.post("/scenario", response_model=ScenarioOut)
def preview_scenario(request: ScenarioRequest) -> ScenarioOut:
    return _scenario_payload(request.settings)


@router.get("/actions")
def get_actions() -> dict:
    state = build_initial_scenario()
    return {
        "actions": [
            {"id": a.id, "label": a.label, "description": a.description}
            for a in available_actions(state)
        ]
    }


@router.post("/simulate", response_model=SimulateResponse)
def simulate(request: SimulateRequest) -> SimulateResponse:
    settings = request.settings.model_dump(exclude_none=True) if request.settings else None
    cfg = build_config(settings)
    base_state = build_initial_scenario(cfg)

    registry = {a.id for a in available_actions(base_state)}
    action_ids = request.actions if request.actions is not None else None
    if action_ids is not None:
        unknown = [a for a in action_ids if a not in registry]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown action id(s) for this scenario: {unknown}",
            )
        if not action_ids:
            raise HTTPException(status_code=422, detail="actions must not be empty")

    results = simulate_actions(base_state, action_ids, request.runs, seed=request.seed, cfg=cfg)
    return SimulateResponse(
        runs=request.runs,
        seed=request.seed,
        steps=cfg.sim_steps,
        results=results,
    )
