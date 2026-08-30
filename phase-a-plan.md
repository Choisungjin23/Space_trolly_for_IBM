# Phase A Implementation Plan — Graph-Based Stochastic Spacecraft Simulator (PoC)

> Historical plan note: the implemented engine has since replaced the generic
> fire-severity fatality coin flip described in the original draft with an
> explicit ASSUMED oxygen/contaminant survival-and-return model. Its top-level
> allocation objective is expected surviving returnees; see `spacecraft-sim/README.md`.

**Project:** IBM AI Builders Challenge — AI-assisted spacecraft emergency decision support
**Phase A scope:** No AI. Only the simulation pipeline:
`current state → emergency action → stochastic future simulation → outcome comparison`

**Repository note:** The working directory currently contains an unrelated project (workout planner HTML files). Phase A will be created entirely inside a new `spacecraft-sim/` subdirectory and will not touch existing files.

---

## 1. Proposed directory structure

```
spacecraft-sim/
├── README.md
├── backend/
│   ├── pyproject.toml            # deps: fastapi, uvicorn, pydantic, pytest
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI app factory, CORS, router mounting
│   │   ├── config.py             # ALL tunable PoC parameters in one place
│   │   ├── domain/
│   │   │   ├── __init__.py
│   │   │   ├── models.py         # Module, Connection, Spacecraft, CrewMember
│   │   │   └── scenario.py       # builds the initial 5-module fire-in-M2 scenario
│   │   ├── simulation/
│   │   │   ├── __init__.py
│   │   │   ├── actions.py        # action registry; each action mutates a state copy
│   │   │   ├── propagation.py    # one-step stochastic fire spread + growth model
│   │   │   ├── monte_carlo.py    # N-run loop, per-run simulation, aggregation
│   │   │   └── metrics.py        # metric definitions computed from end states
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── routes.py         # thin handlers only — delegate to simulation/
│   │       └── schemas.py        # Pydantic request/response models
│   └── tests/
│       ├── test_actions.py
│       ├── test_propagation.py
│       ├── test_monte_carlo.py
│       └── test_api.py
└── frontend/
    ├── package.json              # react, react-dom, typescript, vite
    ├── vite.config.ts            # dev proxy: /api → http://localhost:8000
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx               # single dashboard page
        ├── api.ts                # typed fetch wrappers for the 3 endpoints
        ├── types.ts              # TS mirrors of the API schemas
        └── components/
            ├── SpacecraftGraph.tsx   # modules + connections (simple SVG)
            ├── ModuleCard.tsx        # per-module detail (fire, crew, systems)
            ├── ActionPanel.tsx       # action list + run controls
            └── ResultsComparison.tsx # side-by-side table of all actions
```

Rationale: domain / simulation / api / frontend are fully separated, per the engineering requirements. No route handler contains simulation logic.

---

## 2. Data models

Pydantic models in `domain/models.py` (also serve as API response shapes via `schemas.py`):

```python
class CrewMember:
    id: str            # "C1".."C4"
    name: str

class Module:
    id: str                    # "M1".."M5"
    name: str                  # Habitat, Storage, Life Support, Power, Propulsion
    fire_severity: float       # 0.0–1.0 (0 = no fire)
    isolated: bool             # isolated module: no spread in or out, crew can't evacuate
    crew: list[CrewMember]
    systems: list[str]         # e.g. ["life_support"], with critical systems flagged in config

class Connection:
    source: str                # module id
    target: str                # module id
    hazard_spread_probability: float  # 0.0–1.0, per-connection base spread chance
    active: bool               # False = hatch closed, no spread across it

class Spacecraft:
    modules: dict[str, Module]
    connections: list[Connection]   # undirected for spread purposes (checked both ways)
```

**Initial scenario** (`domain/scenario.py`) — linear-ish graph with one branch:

- Topology: `M1—M2`, `M2—M3`, `M3—M4`, `M4—M5`, `M1—M4` (gives the graph a cycle so isolation choices matter).
- Crew: C1, C2 in M1 (Habitat); C3 in M3 (Life Support); C4 in M4 (Power).
- Systems: M1 `["crew_quarters"]`, M2 `["storage"]`, M3 `["life_support"]` (critical), M4 `["power"]` (critical), M5 `["propulsion"]` (critical).
- Fire: M2 starts with `fire_severity = 0.6`; all others 0.0.
- All connections `active = True`, `hazard_spread_probability` per connection from config (default 0.35 each).

All numeric choices live in `config.py` and are explicitly labeled as **configurable PoC assumptions, not validated fire physics**.

---

## 3. Simulation algorithm

### 3.1 Actions (`simulation/actions.py`)

Registry `ACTIONS: dict[str, Action]`, each with `id`, `label`, `description`, and `apply(state) -> state` that deep-copies the state and mutates the copy **before** simulation:

| id | Effect on state |
|---|---|
| `do_nothing` | No change. |
| `isolate_m2` | `M2.isolated = True` → all connections touching M2 are treated as inactive for spread; crew in M2 (none initially) could not evacuate. |
| `close_m2_m3` | The `M2—M3` connection gets `active = False`. Other M2 connections stay open. |

### 3.2 One simulation step (`simulation/propagation.py`)

Each Monte Carlo run simulates `SIM_STEPS` (default 10) discrete time steps. Per step, in order:

1. **Fire spread.** For every active connection where exactly one side burns (`fire_severity > 0`) and neither endpoint is isolated:
   `P(spread i→j) = fire_severity_i × hazard_spread_probability_ij × PROPAGATION_FACTOR`
   (clamped to [0, 1]). On success, module *j* ignites at `IGNITION_SEVERITY` (default 0.3). Spread decisions in a step are computed against the state at the start of the step (synchronous update), so ordering doesn't bias results.
2. **Fire growth.** Every burning module: `fire_severity = min(1.0, fire_severity + GROWTH_RATE)` (default +0.1/step).
3. **Fire burnout/suppression (optional, keeps runs from being deterministic doom).** With probability `EXTINGUISH_PROB` (default 0.05) per burning module per step, severity drops by `EXTINGUISH_AMOUNT` (default 0.2, floor 0).
4. **System damage.** A module with `fire_severity ≥ SYSTEM_DAMAGE_THRESHOLD` (default 0.8) has probability `SYSTEM_FAILURE_PROB` (default 0.5) per step of destroying its systems (marked failed for the run).
5. **Crew hazard (superseded implementation).** Crew evacuate through available
   hatches, accumulate contaminant exposure, and receive an explicit ASSUMED
   survival/return estimate from oxygen and dose. An explicit abandonment action
   may isolate occupants when that produces the largest expected surviving-returnee
   outcome under constrained resources.

All names in CAPS are constants in `config.py`. The docstring at the top of `propagation.py` and the README both state plainly: *this is a simplified, configurable PoC model chosen for demonstrable behavior, not a physically validated NASA fire model.*

### 3.3 Monte Carlo loop (`simulation/monte_carlo.py`)

```
def run_monte_carlo(base_state, action_id, n_runs, seed=None):
    rng = random.Random(seed)          # single seeded RNG drives all runs → reproducible
    end_states = []
    for _ in range(n_runs):
        state = ACTIONS[action_id].apply(deep_copy(base_state))
        for _ in range(SIM_STEPS):
            step(state, rng)
        end_states.append(state)
    return aggregate(end_states)
```

Reproducibility: same `seed` + same inputs → byte-identical metrics. `seed=None` → nondeterministic (seeded from system entropy).

### 3.4 Metrics (`simulation/metrics.py`) — exact definitions

Computed over the N end states (N = number of runs). These definitions go verbatim into the README and API docs:

- **expected_surviving_crew** = mean over runs of (number of crew alive at end of run). Range 0–4.
- **crew_survival_pct** = 100 × (total crew alive across all runs) ÷ (4 × N). Equivalently `expected_surviving_crew / 4 × 100`.
- **fire_contained_pct** = 100 × (runs where fire never spread beyond the initially burning module set, i.e. no module other than M2 ever ignited) ÷ N. Tracked with an `ever_ignited` flag per module during the run.
- **critical_systems_pct** = 100 × (count of critical systems functional at end, summed over runs) ÷ (3 × N). Critical systems: life_support, power, propulsion (listed in config).
- **mission_survival_pct** = 100 × (runs counted as mission-surviving) ÷ N, where a run survives iff **at least one crew member is alive AND life_support AND power are functional at end** (propulsion loss degrades but doesn't end the mission — documented as a PoC assumption in config).

Also returned per action for context: `mean_final_fire_severity` (mean over runs of the max fire severity across modules at end) and `runs`.

---

## 4. API design

FastAPI app on `http://localhost:8000`. Scenario is rebuilt fresh from `scenario.py` on each request — stateless, in-memory only.

### `GET /api/scenario`
Returns the initial spacecraft state:
```json
{
  "modules": { "M1": { "id": "M1", "name": "Habitat", "fire_severity": 0.0,
                        "isolated": false, "crew": [{"id":"C1","name":"Commander Vega"}],
                        "systems": ["crew_quarters"] }, ... },
  "connections": [ { "source": "M1", "target": "M2",
                     "hazard_spread_probability": 0.35, "active": true }, ... ],
  "critical_systems": ["life_support", "power", "propulsion"]
}
```

### `GET /api/actions`
```json
{ "actions": [ { "id": "do_nothing", "label": "Do nothing", "description": "..." },
               { "id": "isolate_m2", "label": "Isolate Storage (M2)", "description": "..." },
               { "id": "close_m2_m3", "label": "Close hatch M2–M3", "description": "..." } ] }
```

### `POST /api/simulate`
Request (all fields validated by Pydantic; `runs` capped 1–10000, default 1000):
```json
{ "actions": ["do_nothing", "isolate_m2", "close_m2_m3"], "runs": 1000, "seed": 42 }
```
`actions` optional — omitted means "simulate all registered actions" (the frontend's compare-everything case). Response:
```json
{
  "runs": 1000, "seed": 42, "steps": 10,
  "results": [
    { "action_id": "isolate_m2", "label": "Isolate Storage (M2)",
      "expected_surviving_crew": 3.84, "crew_survival_pct": 96.0,
      "fire_contained_pct": 88.2, "critical_systems_pct": 91.4,
      "mission_survival_pct": 90.1, "mean_final_fire_severity": 0.42 },
    ...
  ]
}
```
Unknown action id → 422 with a clear message. CORS enabled for the Vite dev origin.

---

## 5. Frontend structure

Single-page dashboard (Vite + React + TS, no router, no state library — `useState`/`useEffect` only). Vite dev server proxies `/api` to the backend so no CORS/env config is needed in code.

- **App.tsx** — loads scenario + actions on mount; holds `runs` (default 1000), optional `seed`, simulation status, and results.
- **SpacecraftGraph.tsx** — small hand-positioned SVG: 5 module boxes at fixed coordinates, lines for connections. Burning module tinted red with severity shown; inactive connections dashed; isolated modules outlined. Crew shown as small badges on their module. No graph library — fixed layout is fine for 5 nodes.
- **ModuleCard.tsx** — row of 5 cards listing each module's systems (critical ones marked), crew names, fire severity, isolation status.
- **ActionPanel.tsx** — lists the three actions with descriptions, an input for run count and optional seed, and a **Run Simulation** button that always simulates *all* actions in one `POST /api/simulate` call (the whole point is comparison).
- **ResultsComparison.tsx** — one table, actions as columns, the five metrics as rows, best value per row highlighted. Plus a one-line plain-English note ("Isolating M2 gives the highest mission survival: 90.1%") computed from the numbers.

Deliberately minimal styling (plain CSS in one file). Correctness and legibility over polish, per the brief.

---

## 6. Test strategy

pytest, backend only, no network in unit tests (FastAPI `TestClient` for the API tests). All stochastic tests use fixed seeds.

**test_actions.py** — each action modifies expected state:
- `do_nothing` returns a deep-equal copy, and does **not** mutate the input state (checked for every action).
- `isolate_m2` sets `M2.isolated = True` and nothing else.
- `close_m2_m3` deactivates exactly the M2–M3 connection.

**test_propagation.py** — isolation/closure semantics:
- With M2 isolated and severity 1.0, forced spread probability 1.0: after many steps no other module ever ignites (isolation blocks all M2 edges).
- With M2–M3 closed and all other connections' probabilities forced to 0: M3 never ignites.
- With an active connection and probability forced to 1.0: neighbor ignites on step 1 (spread does happen when it should).
- Synchronous update: a module ignited in step *k* doesn't spread until step *k+1*.

**test_monte_carlo.py** — determinism and metric validity:
- Same seed twice → identical full result objects; different seeds → (almost surely) different results.
- For every action at seed 42, 200 runs: every percentage metric in [0, 100], `expected_surviving_crew` in [0, 4], `mean_final_fire_severity` in [0, 1].
- Degenerate configs behave sanely: spread probability 0 everywhere → `fire_contained_pct == 100`.
- Sanity ordering (documented as model-dependent, generous tolerance): `isolate_m2` containment ≥ `do_nothing` containment at the default config.

**test_api.py** — endpoint contracts:
- `GET /api/scenario` returns 5 modules, 4 crew total, fire in M2 only.
- `GET /api/actions` returns exactly the 3 registered actions.
- `POST /api/simulate` with seed returns one result per action with all required metric fields; invalid action id → 422; `runs` out of range → 422.

---

## 7. Implementation order

Each step leaves the project runnable/testable:

1. **Scaffold backend** — `pyproject.toml`, package layout, empty FastAPI app boots under uvicorn.
2. **`config.py` + domain models + initial scenario** — all constants in one file; `GET /api/scenario` wired up as the first vertical slice.
3. **Actions** (`actions.py`) + `GET /api/actions` + `test_actions.py`.
4. **Propagation step** (`propagation.py`) + `test_propagation.py` — the core stochastic model, tested before any aggregation exists.
5. **Monte Carlo + metrics** (`monte_carlo.py`, `metrics.py`) + `test_monte_carlo.py`.
6. **`POST /api/simulate`** + `test_api.py` — backend complete; verifiable with curl.
7. **Scaffold frontend** — Vite React-TS template, proxy config, `api.ts`/`types.ts`, scenario rendering (graph + module cards).
8. **Action panel + simulate flow + results comparison table.**
9. **README** — problem statement, model description, propagation assumption disclaimer, metric definitions, run instructions for both halves, current limitations.
10. **End-to-end check** — run backend + frontend together, click Run Simulation, confirm the three actions produce plausibly ordered, reproducible results.

**Estimated size:** ~600–800 lines backend (including tests), ~400 lines frontend. Small enough to complete in one focused implementation session.

### Out of scope for Phase A (deferred by design)
Databases, auth, IBM Granite/LLM integration, RAG, LangFlow, external APIs, ML models, Docker, real-time step-by-step animation, additional emergency types (depressurization, power failure), evidence-based propagation parameters.
