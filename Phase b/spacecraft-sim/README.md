# Spacecraft Emergency Decision-Support Sandbox

**IBM AI Builders Challenge — Phase B**

An interactive local web application for building spacecraft topologies, injecting fire emergencies, and comparing simulated action outcomes side-by-side.

> ✅ **Phase A engine connected.** `POST /api/simulate` now runs `PhaseASimulatorAdapter`, which bridges to the real `spacecraft_sim` engine (real-unit species mass balance, computed smoke detection, crew state machine with SMAC doses, equipment damage/repair, Monte Carlo over uncertain scenario assumptions). The engine lives in the sibling checkout `../../spacecraft-sim` and is installed into this backend's `.venv` with `pip install -e`. `MockSimulatorAdapter` remains only as a fallback for environments where the engine package cannot be found (the health check at `GET /` reports which adapter is active).
>
> ⚠ Sample counts are counts over sampled scenario assumptions — still not validated physical probabilities. The engine's constants carry `VERIFIED_` (NASA primary source) or `ASSUMED_` (PoC assumption) provenance prefixes; see the engine README and `docs/nasa-calibration-report.html` there.

---

## What it does

1. **Build** an arbitrary spacecraft topology on a node canvas (React Flow)
2. **Configure** modules, connections, crew, and equipment
3. **Inject** a fire emergency into any module
4. **Analyze** — one button serializes the scenario and sends it to the simulator interface
5. **Compare** returned action outcomes side-by-side, revealing trade-offs
6. **Inspect** an example sampled trajectory on the Timeline tab

```
Build spacecraft → Configure → Inject emergency
  → ANALYZE EMERGENCY → Structured simulator response
  → Compare actions → Inspect timeline
```

---

## Architecture

```
Browser (React + TypeScript + Vite)
  ├── Canonical Scenario State (Zustand)   ← source of truth
  ├── React Flow canvas                     ← derived visual layer
  ├── Inspector panels                      ← edit scenario state
  └── SimulatorClient interface             ← replaceable adapter

        ↓  POST /api/simulate

FastAPI Backend
  ├── adapters/mock_simulator.py            ← Phase B fixture
  └── fixtures/five_module_demo.json        ← demo template data
```

**Phase A simulator** (future): replace `MockSimulatorAdapter` with `PhaseASimulatorAdapter` implementing the same `simulate()` interface. No frontend changes required.

**Phase C agents** (future): consume structured `SimulationResponse` JSON directly. The response shape is already machine-readable.

---

## Project Structure

```
spacecraft-sim/
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                  # FastAPI app
│   │   ├── api/
│   │   │   ├── routes.py            # POST /api/simulate, GET /api/templates
│   │   │   └── schemas.py           # Pydantic request/response models
│   │   ├── adapters/
│   │   │   └── mock_simulator.py    # Phase B mock (NOT Phase A physics)
│   │   └── fixtures/
│   │       └── five_module_demo.json
│   └── tests/
│       └── test_phase_b.py          # 34 backend tests
└── frontend/
    ├── src/
    │   ├── types/
    │   │   ├── scenario.ts          # canonical domain types
    │   │   └── simulator.ts         # request/response types
    │   ├── store/
    │   │   ├── useScenarioStore.ts  # spacecraft state
    │   │   └── useSimulationStore.ts
    │   ├── api/
    │   │   └── simulatorClient.ts   # SimulatorClient interface
    │   └── components/
    │       ├── landing/             # LandingPage
    │       ├── builder/             # SpacecraftCanvas, ModuleNode, ConnectionEdge
    │       ├── inspector/           # ModuleInspector, ConnectionInspector, editors
    │       ├── emergency/           # EmergencyInjector
    │       ├── results/             # ResultsPage, ActionResultCard, TimelineView
    │       └── shared/              # DisclaimerBanner
    └── vite.config.ts               # /api proxy → localhost:8000
```

---

## How to Run

### Backend

**Requirements:** Python 3.11+

```powershell
cd spacecraft-sim/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e ..\..\..\spacecraft-sim   # the Phase A engine (spacecraft_sim)
uvicorn app.main:app --reload
```

Verify the engine is active: `GET http://localhost:8000/` should report
`"adapter": "PhaseASimulatorAdapter"`. If the engine package cannot be found,
the server falls back to the mock and says so here.

Backend runs at `http://localhost:8000`. Verify with `GET http://localhost:8000/`.

### Frontend

**Requirements:** Node.js 18+

```powershell
cd spacecraft-sim/frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`. The Vite dev server proxies `/api` to `localhost:8000`.

### Backend Tests

```powershell
cd spacecraft-sim/backend
.\.venv\Scripts\Activate.ps1
python -m pytest tests/ -v
```

All 34 tests should pass.

---

## API

### `GET /api/templates`
Returns available scenario templates.

### `GET /api/templates/{id}`
Returns a full scenario payload (e.g. `five-module-demo`).

### `POST /api/simulate`
Accepts user-created spacecraft scenario + emergency, returns structured action outcomes.

```json
{
  "scenario": { "modules": {}, "connections": {}, ... },
  "emergency": { "type": "fire", "affectedModuleId": "...", "detected": true },
  "actions": null,
  "runs": 200,
  "seed": 42
}
```

Response includes `generatedActions`, `results` (per-action outcomes), `exampleTrajectory` (for timeline), and `sourceLabel` identifying the adapter.

---

## Phase Boundaries

| Phase | Status | Description |
|---|---|---|
| **Phase B (this)** | ✅ Complete | Product layer, interactive builder, results UI |
| **Phase A** | ✅ Connected | Real-unit engine in `../../spacecraft-sim`, bridged via `PhaseASimulatorAdapter` |
| **Phase C** | Not implemented | AI agents: Hazard, Crew Safety, Systems, Mission, Decision Coordinator |

---

## Important Disclaimers

- No `hazard_spread_probability` in the frontend — physical interpretation belongs to Phase A
- No crew-value numeric weighting
- No "BEST ACTION" recommendation — trade-off decision belongs to the operator
- Sample counts ("824 / 1000 sampled scenarios") are mock values from `MockSimulatorAdapter`
- All results labeled "Phase B — not Phase A simulation physics"
- Phase C AI synthesis not implemented

---

## Development with IBM Bob

This Phase B implementation was developed using **IBM Bob** (IBM's AI coding assistant):

- **Architecture refinement** — reviewed requirements, identified hard-coded M1–M5 patterns to eliminate, designed the `SimulatorClient` adapter boundary
- **React Flow builder** — `SpacecraftCanvas`, `ModuleNode`, `ConnectionEdge` with custom rendering and canonical state sync
- **Inspector and editor components** — `ModuleInspector`, `ConnectionInspector`, `CrewEditor`, `EquipmentEditor`
- **Emergency injector** — `EmergencyInjector` dialog with fire-only Phase B scope
- **Mock simulator adapter** — `MockSimulatorAdapter` in Python generating structured `SimulationResponse` from arbitrary graph topologies
- **FastAPI integration** — `POST /api/simulate` accepting user-supplied scenarios (not hard-coded server scenarios)
- **State management** — Zustand stores (`useScenarioStore`, `useSimulationStore`) with clean separation of concerns
- **Results and timeline** — `ActionResultCard`, `TimelineView` with sample-count wording and no probability claims
- **Test generation** — 34 backend tests covering genericity, validation, mock validity, and API contracts
- **TypeScript cleanup** — resolved all build errors, zero-warning production build
- **Documentation** — this README and inline code comments

Bob did not implement Phase A physics or Phase C agents (both out of scope).

---

## Completion Checklist

- [x] Load demo or create fresh spacecraft
- [x] Add / move / edit modules on React Flow canvas
- [x] Add / edit connections with typed properties
- [x] Assign crew (name, role, providesFunctions) per module
- [x] Assign equipment (name, type, state, providesCapabilities) per module
- [x] Inject fire emergency into any module
- [x] Click ANALYZE EMERGENCY → receives structured mock results
- [x] Compare returned actions side-by-side
- [x] Timeline tab with step slider
- [x] User-created spacecraft (non-demo) uses identical code path
- [x] No hard-coded M1–M5 IDs outside demo fixture
- [x] No `hazard_spread_probability` in frontend types
- [x] No crew-value weighting
- [x] No "BEST ACTION" recommendation
- [x] Mock outputs clearly labeled
- [x] 34 backend tests pass
- [x] Frontend builds with 0 TypeScript errors
