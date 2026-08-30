# Phase C — Multi-agent decision support

A decision-support layer over the Phase A spacecraft simulator, implemented
against the interfaces in [`../phase-a-contract.md`](../phase-a-contract.md).

```
Scenario -> Phase A engine -> PhaseASimulationAdapter -> normalized analysis
  -> specialist agents -> NASA evidence -> grounding validator
  -> red-team critic -> coordinator -> structured recommendation -> human
```

**The AI does not replace the simulator.** Phase A answers *what happened*;
the agents answer *what it means*; the operator decides.

## Division of responsibility

| Question | Answered by |
|---|---|
| What happened under this simulated action? | Phase A engine |
| What does real technical evidence say? | Evidence agent over a cited NASA corpus |
| What does this mean in my domain? | Hazard, Crew Safety, Systems, Mission |
| What did everyone get wrong? | Critic / red-team |
| Which response should be recommended? | Coordinator (advisory only) |
| Which response do we take? | **The human operator** |

## Install and test

```bash
pip install -e .            # add ".[granite]" for the IBM watsonx client
python -m pytest            # 143 tests, no network, no credentials
```

Phase A is located automatically: an installed `spacecraft_sim` first, then
`$SPACECRAFT_SIM_SRC`, then the sibling `../phase-a/src`.

## The adapter boundary

Agents never import the engine. `providers/phase_a.py` is the only module that
touches `spacecraft_sim`, and a test enforces it. It closes every gap listed in
the Phase A contract §8:

- `TimelineResult` / `Distribution` dataclasses serialized, `final` via `model_dump()`
- the separate Monte Carlo call joined onto the deterministic result
- **equipment** lifted out of `final` (it is absent from `summary`)
- hatch connectivity, crew/air throughput, passage feedback, and the computed
  crew/portable-equipment queue normalized for bottleneck-aware advice
- 120 timeline frames replaced by ~10–30 semantic events
- capability keys iterated, never named in code
- `detected_at_seconds: null` promoted to a first-class `NEVER_DETECTED` status

### One Phase A defect the adapter works around

`Distribution` exposes fixed return/habitation count fields and the engine
defaults an undeclared configured capability to `AVAILABLE`, which could read
as a vacuous *n/n*. The adapter keys those fields with the scenario-defined
capability names and marks undeclared counts `applicable: false`. Phase A is
unmodified; contract tests cover both custom and missing names.

## Grounding — the core safety mechanism

Prompt instructions do not stop fabrication. Two machine checks do. Before any
agent runs, a **fact registry** is built from the normalized analysis: every
scalar, plus list lengths and per-dict min/max/sum, keyed by JSON pointer. After
each agent returns, the **validator** enforces:

| Rule | Catches |
|---|---|
| R1 | a number in prose that is not in the simulation or cited evidence |
| R2 | a `SIMULATION_FACT` claim whose refs do not resolve |
| R3 | a Monte Carlo count phrased as a probability or percentage |
| R4 | survival or mortality claims must resolve to modeled output or cited evidence |
| R5 | "BEST ACTION" from anyone but the Coordinator |
| R6–R8 | a recommendation with no trade-off, no uncertainty, or that takes the decision away from the human |

Violations are **surfaced, never silently corrected** — the operator sees that
an agent tried to assert something unsupported. Module and crew ids (`M2`, `C3`)
are masked before numeric extraction so they do not trip R1.

## Evidence corpus

Nine chunks from six sources, all verified during Phase A calibration: JSC 20584
Rev C (SMAC for CO / HCN / HCl), Saffire I and II, NASA-STD-6001B Test 1, NTRS
20150009509 (IMV flow), NTRS 20030053429 (ISS fire detection), MIL-STD-1629A
(FMECA). Ingest rejects any citation without a specific locator, so every claim
is checkable by a human. Every answer must state its **applicability** — ISS
figures may not transfer to another vehicle, and ground-test combustion data
does not transfer to microgravity.

## LLM

`LLMClient` is a protocol. `GraniteClient` talks to watsonx.ai, configured
only by environment - in normal local development from
`phase-b/spacecraft-sim/backend/.env`:

```
WATSONX_API_KEY      required
WATSONX_PROJECT_ID   required, and must belong to the region below
WATSONX_URL          required, e.g. https://us-south.ml.cloud.ibm.com (Dallas)
WATSONX_MODEL_ID     required, e.g. ibm/granite-4-h-small
```

None of the four has a built-in default. There is no fallback model and no
fallback region, so moving to another region or another supported foundation
model is a `.env` edit and a restart - never a code change. Whether the model
exists is decided by watsonx itself: the SDK checks `model_id` against what the
configured environment actually serves, so an unavailable model fails loudly
rather than being silently swapped.

`phase-c doctor` prints the resolved region and model, and `--live` makes one
minimal real call. Neither ever prints the API key or the project id.

`StubLLMClient` is a deterministic test double that **refuses to invent
findings** — it is not offered as a production fallback, because a decision-
support system that quietly degrades to fabricated advice is worse than one that
says it is unavailable.

## Phase B integration

Additive; `POST /api/simulate` is untouched.

- `GET /api/advisor/status` — whether the advisor can run, and why not if it cannot
- `POST /api/analyze` — runs the pipeline, returns a `DecisionPackage`
- **Advisor** tab in the results view: recommendation with trade-offs, grounding
  violations, per-agent findings, critic issues, cited evidence

The comparison table stays recommendation-free, as Phase B intends. Recommendation
appears only in the Advisor panel.

## Known limitations

- The specialists analyse one focus action in depth (the do-nothing baseline by
  default); the Coordinator sees all actions' summaries. Deep per-action analysis
  for every action would multiply LLM cost.
- `smac_exceeded` events are anchored to that module's hazard arrival, because
  Phase A's summary reports *which* modules exceeded but not *when*. They are
  labelled `source: "derived"`.
- Capability transitions are likewise derived, since timeline frames carry no
  capabilities.
- `measured_criticality` is action-scoped in Phase A; the adapter runs it once
  for a labelled baseline action rather than per action.
- Analysis is synchronous. A job-id + polling design is not built yet; a
  large scenario with many actions will hold the request open.
- Agent specifications for Systems, Mission, Evidence, Critic and Coordinator
  are **proposals** — the task spec was truncated before defining them
  completely.
