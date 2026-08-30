# AI-Assisted Spacecraft Emergency Decision Support

**IBM AI Builders Challenge** — three phases, one pipeline.

```
Build a spacecraft graph  →  inject a fire  →  simulate every candidate action
  →  compare outcomes  →  multi-agent analysis  →  recommendation  →  human decides
```

The simulator produces the numbers. The AI interprets them and never invents any.
The operator makes the final call.

---

## What is here

| Folder | Phase | What it is | Tests |
|---|---|---|---|
| [`spacecraft-sim/`](spacecraft-sim/) | **A** | Real-unit stochastic emergency engine (Python library + CLI) | 132 |
| [`phase-b/`](phase-b/) | **B** | Product layer — React Flow builder + FastAPI | 78 |
| [`phase-c/`](phase-c/) | **C** | Multi-agent decision support over Phase A | 141 |

**353 tests, all passing.** None require network or credentials.

New here? [`SETUP.md`](SETUP.md) takes you from a fresh clone to a running app.

### Documents

- [`SETUP.md`](SETUP.md) — install, run, configure credentials, run the tests.
- [`phase-a-contract.md`](phase-a-contract.md) — **the integration contract.** Real
  output shapes from the built engine. This is what B and C were written against.
- [`docs/beginner-guide.html`](docs/beginner-guide.html) — what the whole system
  does, written for someone who has never coded. Includes a glossary.
- [`docs/phase-a-explained.html`](docs/phase-a-explained.html) — the engine taken
  apart: NASA data, smoke transport, crew and equipment weighting.
- [`spacecraft-sim/docs/nasa-calibration-report.html`](spacecraft-sim/docs/nasa-calibration-report.html)
  — how the engine's constants were mapped to NASA primary sources.

---

## Division of responsibility

| Question | Answered by |
|---|---|
| What happened under this simulated action? | Phase A engine |
| What does real technical evidence say? | Phase C evidence agent, over a cited NASA corpus |
| What does this mean in my domain? | Phase C: Hazard, Crew Safety, Systems, Mission |
| What did everyone get wrong? | Phase C critic / red-team |
| Which response should be recommended? | Phase C coordinator — advisory only |
| Which response do we take? | **The human operator** |

---

## Design rules held across all three phases

1. **No invented numbers.** Phase C machine-checks every numeric literal an agent
   states against a registry built from the simulation output. Violations are
   *shown to the operator*, never silently corrected.
2. **Separate samples from modeled probability.** Monte Carlo still reports *k of n
   sampled assumption sets*. Survival and return probabilities come from a separate,
   explicitly `ASSUMED_*` mortality model and are not clinical forecasts.
3. **Maximize surviving returnees.** Under limited power, air, water and time, the
   coordinator compares actions by expected surviving returnees and may surface an
   isolation or abandonment option when it improves the total.
4. **Operational priority, not social worth.** Crew and equipment priority is their
   counterfactual contribution to surviving returnees. Identity and rank are not
   intrinsic life-value weights.
5. **Provenance in the name.** Engine constants are `VERIFIED_*` (NASA primary
   source) or `ASSUMED_*` (PoC assumption). A test fails the build if a constant
   declares neither.
6. **No topology identifiers hardcoded.** Module ids, action ids and capability
   names come from the scenario. The engine runs on 3 modules or 15; explicit
   PoC equations and default mappings remain documented as assumptions.

---

## Running it

Requires Python 3.11+ and a Vite-supported Node.js release (20.19+ or 22.12+).

### 1. The engine (Phase A)

```bash
cd spacecraft-sim
pip install -e .
python -m pytest
python -m spacecraft_sim.cli compare examples/demo_spacecraft.json
```

### 2. The app (Phase B)

#### macOS quick start

Install Python 3.11+ and Node.js 20.19+ or 22.12+, then run this once from the repository
root (Terminal asks for no credentials and keeps the Windows environment
separate):

```bash
chmod +x run-app.sh
./run-app.sh
```

The launcher creates `.venv-macos`, installs the correct Apple Silicon or Intel
frontend packages, starts both servers, and opens `http://localhost:5173`.
Press `Control-C` to stop both servers. Use `./run-app.sh --no-browser` if you
do not want it to open a browser.

#### Manual start

```bash
cd "phase-b/spacecraft-sim/backend"
python3 -m venv .venv-macos
source .venv-macos/bin/activate
pip install -r requirements.txt -e ../../../spacecraft-sim -e "../../../phase-c[granite]"
uvicorn app.main:app --reload
```

```bash
cd "phase-b/spacecraft-sim/frontend"
npm install
npm run dev
```

Open http://localhost:5173. `GET http://localhost:8000/` should report
`"adapter": "PhaseASimulatorAdapter"`. There is only one simulator: if the
Phase A engine cannot be imported the backend refuses to start and says what
is missing, rather than falling back to something that answers differently.

### 3. The advisor (Phase C)

Needs IBM watsonx.ai credentials. All four values live in one private file,
`phase-b/spacecraft-sim/backend/.env`, which Git ignores. Copy the example and
fill it in — **do not paste your API key into a shell command or a source
file**, so the secret never lands in your shell history or in the repo:

```env
WATSONX_API_KEY=<your IBM Cloud API key>
WATSONX_PROJECT_ID=<your watsonx project ID>
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_MODEL_ID=ibm/granite-4-h-small
```

`WATSONX_PROJECT_ID` is not in the API key JSON. Find it in watsonx.ai: open
your project, then **Manage > General > Details**. It must belong to the same
region as `WATSONX_URL` — a Tokyo or Toronto project will not resolve against
the Dallas endpoint above.

No shell variables are needed: the backend loads this file at startup. Then
check and run:

```bash
cd "phase-b/spacecraft-sim/backend"
.venv-macos/bin/python -m phase_c.cli doctor --access
```

`--access` verifies the key, the project and the model availability **without
spending any tokens**; use `--live` if you also want one real call. With that
green, the **Advisor** tab in the results view becomes active. `doctor` prints
the region and model it will use, and never prints your key or project ID.

Moving to another region or another supported foundation model is an edit to
those three lines plus a restart. Nothing in the source pins a model or a
region, and the model is validated against what the configured region actually
serves — an unavailable one fails loudly rather than being silently swapped.

#### Spend guard

Every Granite call goes through a hard budget guard (`phase_c/llm/budget.py`):
it reserves the worst-case cost *before* the request, refuses the call outright
if the cap would break, and settles against the real token counts returned by
watsonx. The example configuration uses IBM's separate input and output rates
for `ibm/granite-4-h-small`, checked against the
[IBM supported-model pricing table](https://www.ibm.com/docs/en/watsonx/saas?topic=solutions-supported-models)
on 2026-08-31. A different model requires explicit current prices. Set the cap
and rates alongside the credentials:

```env
IBM_BUDGET_USD=5.00
IBM_INPUT_PRICE_PER_1M=0.0636
IBM_OUTPUT_PRICE_PER_1M=0.265
IBM_BUDGET_DB=/Users/you/spacecraft-sim-ledger.sqlite3
```

`doctor` prints the running balance. This is an application-side guard, not an
IBM Cloud billing hard-stop.

---

## Current limitations

Honest list; details in each phase's README.

- **Every test runs on a deterministic stub, not a real model.** The pipeline has
  been exercised against live Granite, and the first runs behaved as this list
  warned: the coordinator copied the specialists' JSON pointers verbatim, which
  omits the action index. The validator now records that as a MINOR imprecision
  instead of rejecting a factually correct claim, but the prompt itself did not
  stop the model doing it. Expect more prompt iteration.
- **Analysis is synchronous.** The planned job-id + polling design is not built, so
  a large scenario holds the HTTP request open (~2.4 s of simulation at 20 samples,
  plus seven LLM calls; roughly 100-170 s end to end in practice).
- **Five of the seven agent specifications are proposals.** The source task spec was
  truncated; Systems, Mission, Evidence, Critic and Coordinator are marked
  `PROPOSED` in code and README.
- **Combustion yields now come from ground fire science**, on the argument that
  ISS cabin air is essentially sea-level air: CO is derived from the
  Koylu-Faeth correlation published by NIST, and nitrogen-free fuels emit no
  HCN by stoichiometry. What is still unverified is whether product *ratios*
  hold in microgravity — Saffire measured spread rates, not yields.
- **Return is judged once, at the end of the horizon.** A return capability lost
  and repaired inside the hour therefore costs nothing, which is defensible —
  the return flight happens after the emergency — but it means a marginal run
  and a comfortable one can report the same `expectedReturnees`. The engine now
  reports `returnCapability.downtimeSeconds` so the difference is visible, but
  the verdict itself is still a final-state snapshot.
- **Mission capabilities are composed from a fixed table.** `RETURN` and
  `HABITATION` are built in the Phase B bridge from the equipment capability
  tags a scenario declares. A scenario that tags nothing gets no return verdict
  at all — the response says so in `warnings` rather than reporting a healthy
  spacecraft.
- **The frontend and the engine size power differently.** `autoSizeResourceSources`
  assigns each module to its *nearest* source, while the engine allocates from
  the *highest-level* one, so a source sized by the builder can still be
  spread thinner than intended. The demo fixture is sized for the engine's
  policy; user-built scenarios may not be.
