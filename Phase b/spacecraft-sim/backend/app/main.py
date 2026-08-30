"""
FastAPI application entry point for Phase B.

Phase B backend contains:
  - API routing
  - PhaseASimulatorAdapter (adapters/phase_a_simulator.py) — bridges to the
    real spacecraft_sim engine (real-unit, NASA-calibrated PoC)
  - MockSimulatorAdapter (adapters/mock_simulator.py) — fallback fixture kept
    for environments where the Phase A package cannot be located
  - Template fixtures (fixtures/)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load backend/.env before routes import Phase C. Some Phase C settings, such
# as the spend guard, are evaluated when their modules are imported.
from app.config import load_backend_env

load_backend_env()

from app.api.routes import ACTIVE_ADAPTER, router

app = FastAPI(
    title="Spacecraft Emergency Decision-Support — Phase B",
    description=(
        "Phase B product layer over the Phase A simulation engine. "
        "Active adapter: see GET / ."
    ),
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def health_check() -> dict:
    return {"status": "ok", "phase": "B", "adapter": ACTIVE_ADAPTER}
