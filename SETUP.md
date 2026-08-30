# Setup

From a fresh clone to a running app. Nothing here needs IBM credentials except
[the advisor](#4-the-advisor-optional) — the simulator, the builder UI and all
353 tests run offline.

**Requirements:** Python 3.11+ and Node.js 20.19+ or 22.12+.

---

## 1. The quick way

The launcher creates the virtual environment, installs everything, starts both
servers and opens the browser.

```bash
# Windows
run-app.bat

# macOS / Linux
chmod +x run-app.sh
./run-app.sh
```

Then open <http://localhost:5173>. Press `Ctrl-C` in the launcher window to stop
both servers. Pass `--no-browser` if you would rather open it yourself.

To confirm you are running the real engine and not a stand-in:

```bash
curl http://localhost:8000/
# {"status":"ok","phase":"B","adapter":"PhaseASimulatorAdapter"}
```

If the backend cannot import the Phase A engine it now refuses to start and says
what is missing. There is deliberately no fallback simulator: a stand-in that
answers with different physics under the same response shape is worse than a
server that will not start.

---

## 2. Manual install

Useful when the launcher does not fit your setup, or when you want to run the
pieces separately.

### Backend

```bash
cd "phase-b/spacecraft-sim/backend"

python -m venv .venv                 # macOS/Linux: python3 -m venv .venv
.venv\Scripts\Activate.ps1            # macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
pip install -e ../../../spacecraft-sim          # Phase A engine
pip install -e "../../../phase-c[granite]"      # Phase C advisor

uvicorn app.main:app --reload
```

The backend serves on <http://localhost:8000>.

### Frontend

```bash
cd "phase-b/spacecraft-sim/frontend"
npm install
npm run dev
```

The Vite dev server serves on <http://localhost:5173> and proxies `/api` to the
backend. The app is always served from the dev server — there is no build step
in the normal workflow, and `npm run build` output is not used by anything.

---

## 3. Running the tests

Three independent suites. All of them are offline and deterministic.

```bash
# Phase A — the engine                      (~2 s)
cd spacecraft-sim && python -m pytest

# Phase C — agents, grounding, contracts    (~3 s)
cd phase-c && python -m pytest

# Phase B — the product layer               (~15 min: real engine + Monte Carlo)
cd "phase-b/spacecraft-sim/backend" && python -m pytest
```

Use the backend virtual environment for all three — it has the other two
installed in editable mode:

```bash
"phase-b/spacecraft-sim/backend/.venv/Scripts/python.exe" -m pytest
```

Phase B is slow because every test drives the real engine over a 1-hour horizon
plus Monte Carlo samples. That is intentional; it is the suite that would catch
a bridge that silently stopped matching the engine.

---

## 4. The advisor (optional)

The **Advisor** tab runs seven agents over the simulation on IBM watsonx.ai.
Everything else works without it.

### Credentials

All four values live in one private file, `phase-b/spacecraft-sim/backend/.env`,
which Git ignores. Copy the example and fill it in:

```bash
cd "phase-b/spacecraft-sim/backend"
cp .env.example .env
```

```env
WATSONX_API_KEY=<your IBM Cloud API key>
WATSONX_PROJECT_ID=<your watsonx project ID>
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_MODEL_ID=ibm/granite-4-h-small
```

> **Edit the file, do not export the key on a command line.** A key pasted into
> a shell command lands in your shell history. `.env` is git-ignored and the
> backend loads it at startup, so no shell variables are needed.

`WATSONX_PROJECT_ID` is not in the API key JSON. Find it in watsonx.ai: open your
project, then **Manage → General → Details**. It must belong to the same region
as `WATSONX_URL` — a Tokyo or Toronto project will not resolve against the Dallas
endpoint above.

### Check it before spending anything

```bash
python -m phase_c.cli doctor --access
```

`--access` verifies the key, the project and the model availability **without
spending any tokens**. It prints the region and model in use and never prints
your key or project ID. Use `--live` instead if you want it to make one real
call.

With that green, the Advisor tab becomes active.

### Spend guard

Every Granite call goes through a hard budget guard (`phase_c/llm/budget.py`): it
reserves the worst-case cost *before* the request, refuses the call outright if
the cap would break, and settles against the real token counts watsonx returns.
The example uses IBM's separate input/output prices for
`ibm/granite-4-h-small`, checked against the
[IBM supported-model pricing table](https://www.ibm.com/docs/en/watsonx/saas?topic=solutions-supported-models)
on 2026-08-31. If you change models, update both prices from IBM's current
table. Configure them in the same `.env`:

```env
IBM_BUDGET_USD=5.00
IBM_INPUT_PRICE_PER_1M=0.0636
IBM_OUTPUT_PRICE_PER_1M=0.265
IBM_BUDGET_DB=/absolute/path/to/ledger.sqlite3
```

This is an application-side guard, not an IBM Cloud billing hard-stop.

One full analysis is seven calls and takes roughly 100–170 seconds.

---

## 5. Using it

1. **Build** a spacecraft on the canvas, or load the `five-module-demo` template.
2. **Tag equipment with the capabilities it provides.** This matters more than it
   looks: capability tags become the engine's systems, and `RETURN` is composed
   from them. A scenario that tags nothing gets no return verdict, and the
   response says so in `warnings`. Untagged equipment now takes a capability
   from its type where that is unambiguous.
3. **Inject** an emergency — pick the module, the type, and optionally an escape
   target with a seat limit.
4. **Simulate.** Every candidate action the graph affords is run as an
   independent counterfactual and compared. This view never recommends.
5. **Advisor** (optional). The only place an action is recommended. The
   coordinator advises, the critic argues back, machine-detected grounding
   violations are shown rather than hidden, and the operator decides.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Backend exits on start with an import error naming `spacecraft_sim` | Phase A is not installed in this environment. Run the two `pip install -e` lines in §2, or set `SPACECRAFT_SIM_SRC` to `<repo>/spacecraft-sim/src`. |
| `GET /` reports an adapter other than `PhaseASimulatorAdapter` | You are on an old checkout. There is only one simulator now. |
| Advisor tab is inactive | `GET /api/advisor/status` says why. Usually a missing or wrong `.env`; run `doctor --access`. |
| `404 not found` from watsonx | `WATSONX_PROJECT_ID` is from a different region than `WATSONX_URL`. |
| `expectedReturnees` always equals `expectedSurvivors` | The scenario declares no `RETURN` capability, so return was never judged. Check `warnings` in the response and tag the relevant equipment. |
| Port 5173 or 8000 already in use | Vite picks the next free port and prints it. For the backend, pass `--port`. |
