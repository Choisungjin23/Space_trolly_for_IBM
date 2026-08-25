# Spacecraft Emergency Simulator — Phase A PoC

Proof-of-concept for an AI-assisted spacecraft emergency decision-support system
(IBM AI Builders Challenge). Phase A contains **no AI**: it only proves the core
pipeline works:

```
current spacecraft state → emergency action → stochastic future simulation → outcome comparison
```

A user sees a 5-module spacecraft with a fire in the Storage module, and runs
Monte Carlo simulations to compare how three different emergency actions affect
crew survival, fire containment, and mission survival.

## The problem

During a spacecraft emergency, crews must choose between actions (seal a module,
close a hatch, do nothing) whose consequences unfold stochastically over time.
Phase A builds the simulation substrate that a future AI advisor will reason
over: given a state and a set of candidate actions, quantify the distribution of
future outcomes for each action.

## The simplified spacecraft model

Five modules connected as a graph, four crew members:

| Module | Name | Systems | Crew |
|---|---|---|---|
| M1 | Habitat | crew_quarters | C1 Commander Vega, C2 Engineer Okafor |
| M2 | Storage | storage | — (fire starts here, severity 0.6) |
| M3 | Life Support | life_support ★ | C3 Specialist Lindqvist |
| M4 | Power | power ★ | C4 Technician Aram |
| M5 | Propulsion | propulsion ★ | — |

★ = critical system.

### Graph representation

Modules are nodes; connections are undirected edges:

```
M1 --- M2 --- M3
 \             |
  \            |
   M4 -------- +      edges: M1-M2, M2-M3, M3-M4, M4-M5, M1-M4
   |
   M5
```

The M1–M4 edge creates a cycle on purpose: it makes "isolate M2" and "close only
the M2–M3 hatch" genuinely different, because with only the hatch closed, fire
can still reach M3 the long way around (M2 → M1 → M4 → M3).

Each module carries: `id`, `name`, `fire_severity` (0–1), `isolated`, `crew`,
`systems` (plus per-run tracking fields `failed_systems`, `ever_ignited`).
Each connection carries: `source`, `target`, `hazard_spread_probability`, `active`.

### Actions

Actions are **generated from the current state**, not hard-coded to one module,
so moving the fire produces the matching set of options:

1. **do_nothing** — no state change.
2. **isolate_&lt;module&gt;** — seals the burning module entirely: fire cannot spread
   in or out through any of its connections (and crew inside cannot evacuate).
3. **close_&lt;a&gt;_&lt;b&gt;** — one action per hatch leading out of the burning module;
   deactivates just that connection.

With the default fire in M2 this yields `do_nothing`, `isolate_m2`,
`close_m1_m2`, and `close_m2_m3`. Actions modify a copy of the state *before*
simulation begins.

## Editing parameters from the GUI

Everything that used to require editing `config.py` is adjustable in the browser
under **Scenario parameters**:

- **Fire starts in** — which module ignites (the action list regenerates to match).
- **Crew placement** — which module each of the four crew members starts in.
- **Sliders** for every numeric parameter: initial fire severity, connection
  hazard probability, simulation steps, propagation factor, ignition severity,
  growth rate, burnout chance and amount, system damage threshold and failure
  chance, crew hazard threshold, and crew fatality factor.
- **Reset to defaults** restores the shipped values.

The diagram and action list update live as you change settings; press **Run
Simulation** to see the effect on outcomes. Settings travel with each API
request — the server stays stateless.

`GET /api/config` is the single source of truth for the controls: it returns the
defaults plus each field's bounds, step, group, and help text, and the same
`FIELD_SPECS` are used to clamp incoming values server-side. Adding a parameter
to `FIELD_SPECS` in [`backend/app/config.py`](backend/app/config.py) makes it
appear in the GUI with no frontend change.

## The stochastic propagation assumption

> ⚠️ **This is a configurable PoC assumption, not a physically validated fire
> model (NASA or otherwise).** Every parameter lives in
> [`backend/app/config.py`](backend/app/config.py) so the whole set can later be
> replaced with evidence-based values without touching simulation code.

Each Monte Carlo run simulates 10 discrete time steps. Per step, in order:

1. **Spread** — for each active connection with both endpoints non-isolated and
   exactly one side burning:
   `P(spread i→j) = fire_severity_i × hazard_spread_probability_ij × propagation_factor`
   (clamped to [0,1]). Newly ignited modules start at severity 0.3. Updates are
   synchronous: a module ignited this step cannot spread or grow until the next step.
2. **Growth** — modules burning at the start of the step gain +0.1 severity (cap 1.0).
3. **Burnout/suppression** — each burning module has a 5% chance of losing 0.2 severity.
4. **System damage** — a module at severity ≥ 0.8 rolls a 50% failure chance per
   intact onboard system per step; failures are permanent within the run.
5. **Crew hazard** — crew in a module at severity ≥ 0.5 evacuate deterministically
   to the first adjacent non-burning, non-isolated module reachable through an
   active connection; if no such module exists, each member dies that step with
   probability `fire_severity × 0.3`.

## Monte Carlo simulation

For every action: copy the same initial state, apply the action, simulate 10
steps, repeat N times (default 1000), aggregate. A seeded RNG makes results
reproducible; each action derives its RNG from `(seed, action_id)` so an
action's numbers do not depend on which other actions were simulated.

### Metric definitions (N = runs, 4 crew, 3 critical systems)

- **expected_surviving_crew** — mean over runs of crew alive at end. Range 0–4.
- **crew_survival_pct** — `100 × total crew alive across runs ÷ (4 × N)`.
- **fire_contained_pct** — `100 × (runs where no module outside the initially
  burning set ever ignited) ÷ N`.
- **critical_systems_pct** — `100 × (critical systems functional at end, summed
  over runs) ÷ (3 × N)`. A system is functional iff not in its module's
  `failed_systems`.
- **mission_survival_pct** — `100 × surviving runs ÷ N`, where a run survives
  iff ≥ 1 crew member alive **and** life_support **and** power functional at
  end. (PoC assumption: propulsion loss degrades but does not end the mission.)
- **mean_final_fire_severity** — mean over runs of the max severity across
  modules at end. Range 0–1.

## API

- `GET /api/config` — parameter defaults plus the control metadata (bounds,
  step, group, help) the GUI renders.
- `GET /api/scenario` — default spacecraft state and its available actions.
- `POST /api/scenario` — body `{"settings": {...}}`; previews the state a given
  parameter set produces. Out-of-range numbers are clamped, not rejected.
- `GET /api/actions` — actions available for the default scenario.
- `POST /api/simulate` — body
  `{"settings": {...}, "actions": [...], "runs": 1000, "seed": 42}`;
  `settings` omitted = defaults; `actions` omitted = simulate all available;
  `seed` omitted = nondeterministic; `runs` accepted range 1–10000. Requesting
  an action that does not exist for the given scenario returns 422. Returns
  aggregated metrics per action.

## How to run

### Backend (Python 3.12+)

```
cd backend
pip install fastapi uvicorn
python -m uvicorn app.main:app --port 8000
```

Tests (`pip install pytest httpx` first):

```
cd backend
python -m pytest
```

### Frontend (Node 18+)

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies `/api` to the backend
on port 8000, so start the backend first.

## Current limitations

- The propagation model and all its parameters are unvalidated PoC assumptions.
- Only one emergency type (fire); the scenario is rebuilt fresh per request from
  the settings in that request — nothing is persisted between sessions.
- Module names, onboard systems, and the connection topology are still defined
  in code ([`scenario.py`](backend/app/domain/scenario.py)); the GUI cannot add
  modules or rewire connections.
- Every connection shares one hazard probability; per-edge values require a code
  change.
- Actions are single-step and mutually exclusive — no combined, sequenced, or
  timed actions, and no action taken partway through a run.
- Crew evacuation is deterministic and simplistic (first eligible neighbor,
  no pathfinding beyond one hop, evacuation always succeeds).
- Metrics are end-of-run aggregates only; no per-step trajectories or
  confidence intervals are reported.
- No AI/LLM integration, no RAG, no databases, no auth — deferred by design to
  later phases.
