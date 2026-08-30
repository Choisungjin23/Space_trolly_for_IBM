# Phase B — Interactive spacecraft sandbox

Phase B is the product layer for the emergency decision-support pipeline. It
provides a React canvas for constructing a spacecraft scenario and a FastAPI
backend that runs every candidate response through the Phase A engine.

There is no production mock fallback. If `spacecraft_sim` cannot be imported,
the backend stops with a clear error instead of returning different physics
under the same API shape. Phase C is optional: the simulator works without IBM
credentials, while the Advisor tab explains why it is unavailable.

## What it does

1. Build and edit arbitrary module/connection graphs.
2. Assign crew, equipment, capabilities, and resource sources.
3. Inject a fire or electronic-short emergency.
4. Run counterfactual actions with the Phase A stochastic engine.
5. Compare outcomes without selecting a “best” action.
6. Optionally run the Phase C Granite advisor, grounding validator, and critic.

## Structure

```text
backend/
  app/api/                 FastAPI routes and request/response schemas
  app/adapters/            Phase A simulator and Phase C advisor bridges
  app/fixtures/            five-module demo scenario
  tests/                   78 offline tests
frontend/
  src/api/                 typed API client
  src/store/               canonical scenario and simulation state
  src/components/          builder, inspectors, results, and Advisor UI
  src/domain/              resource sizing and escape-route calculations
```

## Run

From the repository root:

```powershell
.\run-app.ps1
```

or on macOS/Linux:

```bash
./run-app.sh
```

The frontend opens at <http://localhost:5173> and proxies `/api` to the backend
at <http://localhost:8000>. See the root [`SETUP.md`](../../SETUP.md) for manual
installation, credentials, testing, and troubleshooting.

## API

- `GET /api/templates` and `GET /api/templates/{id}`
- `POST /api/simulate` and `POST /api/simulate/stream`
- `GET /api/advisor/status`
- `POST /api/analyze` and `POST /api/analyze/stream`

`GET /` reports `"adapter": "PhaseASimulatorAdapter"` when the backend is
healthy.

## Verify

```bash
cd phase-b/spacecraft-sim/backend
python -m pytest

cd ../frontend
npm run lint
npm run build
```

The backend suite contains 78 tests. The frontend build performs the TypeScript
check before producing the ignored `dist/` directory.

## Scope and safety

This is a research proof of concept, not certified flight software. Simulation
sample counts are not physical event probabilities, modeled survival is not a
clinical forecast, and Phase C recommendations remain advisory. The operator
makes the final decision.
