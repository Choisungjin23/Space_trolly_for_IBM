# Phase C — Implementation Plan (multi-agent decision support)

Status: **plan only, nothing implemented.** For review before build.

Authoritative input: [`phase-a-contract.md`](phase-a-contract.md) (as-built, verified
against `spacecraft-sim/src/spacecraft_sim/` while writing this).
`phase-a-plan.md` is stale and was not used.

Phase A is **not modified by this work.** Phase C imports it read-only through one
adapter, or runs against fixtures.

---

## 0. Two things the reviewer must know first

**0.1 The task spec I was given is truncated.** It ends mid-sentence in section 11
(`critical_functions[ { function, flag`). Sections 9 and 10 fully specified the
Hazard and Crew agents; the requirements for **Systems, Mission, Evidence/RAG,
Critic, and Coordinator were never received.** Their roster is recoverable from the
spec's section-1 flow diagram and the contract's §7 mapping table, so this plan
proposes them — but sections 6.3–6.7 below are **my design, not your requirement.**
Flagging so you can correct them at review rather than discover it later.

**0.2 A real integration trap in Phase A's Monte Carlo.** The contract says
capability names are scenario-defined and must never be hardcoded. But
`montecarlo.py:112-114` does exactly that:

```python
return_ok     = summary["capabilities"].get("RETURN", "AVAILABLE")     != "UNAVAILABLE"
habitation_ok = summary["capabilities"].get("HABITATION", "AVAILABLE") != "UNAVAILABLE"
```

For a scenario that declares different capabilities (say `EVA`, `SCIENCE`), the
`.get(..., "AVAILABLE")` default makes `return_available` and `habitation_available`
report **n/n vacuously** — a count that looks like good news and means nothing.
Since Phase A is frozen for this task, **the adapter must gate those two fields on
the scenario actually declaring those capability keys**, and otherwise mark them
`not_applicable`. The capability-agnostic counts (`hazard_contained_to_sources`,
`no_crew_trapped`, `all_crew_safe_or_evacuated`, `no_crew_reached_smac_dose`) stay
valid for every scenario. Recorded here as a Phase A defect to fix later, on its own
schedule.

**0.3 Capabilities are not in timeline frames.** Verified: a frame carries only
`t, extinction, co_mg_m3, crew, crew_modules, systems`. The spec's wish for
"capability state transition" events therefore cannot be read directly — Phase C
must **derive** it per frame by mapping `frame["systems"]` through
`scenario.capabilities`, replicating the roll-up rule (any UNAVAILABLE/FAILED →
UNAVAILABLE; any EXPOSED_AT_RISK → AT_RISK; else AVAILABLE). That derivation is
adapter-side and must be labelled as derived, not as engine output.

---

## 1. Scope

**In:** adapter boundary, normalized analysis contract, timeline event extraction,
seven agents, grounding enforcement, RAG corpus, orchestration, Phase B endpoint and
UI panel, tests.

**Out:** modifying Phase A; fine-tuning; agent autonomy over actions (agents advise,
never actuate); real-time/streaming simulation; multi-emergency types.

**Non-negotiables carried from the spec and contract**

- The simulator produces numbers; agents never invent them.
- Monte Carlo output is *counts over sampled assumption sets*, never probability.
- Simulator values are simulation facts, never universal NASA truths.
- Survival and return estimates must resolve to the explicit ASSUMED exposure
  model. Prioritization maximizes expected surviving returnees and must never
  be presented as an intrinsic valuation of people.
- Capability names, action ids, and module ids are read dynamically, never hardcoded.
- The human is the final decision-maker.

---

## 2. Directory structure

```
phase-c/
├── pyproject.toml                  # deps: pydantic, httpx, numpy; optional: ibm-watsonx-ai
├── README.md
├── src/phase_c/
│   ├── contracts/                  # THE stable boundary — pydantic, versioned
│   │   ├── analysis.py             # ActionAnalysis, CaseAnalysis (normalized input)
│   │   ├── findings.py             # Claim, AgentFinding, CriticReview, Recommendation
│   │   └── evidence.py             # EvidenceCitation, EvidenceAnswer
│   ├── providers/
│   │   ├── base.py                 # SimulationProvider protocol
│   │   ├── mock.py                 # MockSimulationProvider (golden fixtures)
│   │   └── phase_a.py              # PhaseASimulationAdapter (only file importing Phase A)
│   ├── timeline/
│   │   └── events.py               # semantic event extraction + optional downsample
│   ├── agents/
│   │   ├── base.py                 # Agent protocol, prompt assembly, output parsing
│   │   ├── hazard.py  crew.py  systems.py  mission.py
│   │   ├── evidence.py             # RAG-backed; answers, never decides
│   │   ├── critic.py               # red-team over the others
│   │   └── coordinator.py          # synthesis + recommendation
│   ├── grounding/
│   │   ├── registry.py             # every numeric fact the agents are allowed to cite
│   │   └── validator.py            # machine check: no unsupported numbers
│   ├── rag/
│   │   ├── store.py                # local index (no external service)
│   │   └── corpus/                 # NASA excerpts + citation metadata
│   ├── llm/
│   │   ├── base.py                 # LLMClient protocol
│   │   ├── granite.py              # IBM Granite via watsonx
│   │   └── stub.py                 # deterministic offline client for tests
│   └── orchestrator.py             # pipeline: analyze(case) -> DecisionPackage
└── tests/
    ├── fixtures/                   # real Phase A output, captured once, committed
    ├── test_adapter.py  test_events.py  test_grounding.py
    ├── test_agents.py  test_critic.py  test_coordinator.py
    └── test_integration.py
```

Rule enforced by a test: searching `src/phase_c/` for `spacecraft_sim` matches
**only** `providers/phase_a.py`.

---

## 3. The adapter boundary

```python
class SimulationProvider(Protocol):
    def list_actions(self, scenario) -> list[ActionRef]: ...
    def analyze_action(self, scenario, action_id, *, samples: int | None,
                       seed: int | None) -> ActionAnalysis: ...
    def analyze_case(self, scenario, *, action_ids: list[str] | None,
                     samples: int | None, seed: int | None) -> CaseAnalysis: ...
```

`PhaseASimulationAdapter` closes every gap the contract §8 lists:

| # | Gap | Handling |
|---|---|---|
| 1 | `TimelineResult` is a plain dataclass | `dataclasses.asdict()`, then `final` via `model_dump()` |
| 2 | `Distribution` is a separate call/object | adapter calls both and joins them per action |
| 3 | `summary` is a plain dict | copied into a pydantic `ActionAnalysis`, validated at the boundary |
| 4 | equipment absent from `summary` | pulled from `final.equipment`, projected to id/name/module/system/powered/damaged/repair_progress |
| 5 | timeline is 120 heavy frames | replaced by extracted events (§5); raw kept out of band |
| 6 | capability keys are scenario-defined | passed through as a dict, iterated, never named in code |
| 7 | MC hardcodes RETURN/HABITATION | gated on declared capabilities (§0.2), else `not_applicable` |
| 8 | `detected_at_seconds` may be `null` | first-class `NEVER_DETECTED` state, not a missing key |
| 9 | no JSON CLI mode | adapter serializes in-process; no Phase A change needed |

`MockSimulationProvider` replays committed fixtures so every agent test runs offline
and deterministically.

---

## 4. Normalized Phase C input (adapter output — *not* Phase A's schema)

Smallest useful shape. Field names mirror Phase A where they exist, so a reader can
trace them back; **new** keys appear only where Phase A has a genuine gap.

```jsonc
// ActionAnalysis
{
  "action": {"id": "isolate:M2", "kind": "isolate", "label": "...", "params": {}},

  "detection": {"detected_at_seconds": 270.0, "status": "DETECTED"},   // or NEVER_DETECTED

  "hazard": {                        // Phase C grouping; no such key in Phase A
    "reached_modules": ["M2"],
    "smac_exceeded_modules": ["M2"],
    "peak_extinction_per_m": {"M1": 0.00047, "M2": 1.52296}
  },

  "crew": {"C1": {"state": "SAFE", "exposure_seconds": 0.0,
                  "smac_dose_fraction": 0.0007, "module": "M1"}},   // keyed by crew_id
  "crew_counts": {"SAFE": 4, "EXPOSED": 0, "EVACUATING": 0, "EVACUATED": 0, "TRAPPED": 0},

  "systems": {"life_support": "OPERATIONAL"},
  "system_reasons": {},                                  // only non-operational appear
  "equipment": {"eq_ls": {"module": "M3", "system": "life_support",
                          "powered": true, "damaged": false}},      // from final, gap #4

  "capabilities": {"RETURN": "AVAILABLE"},               // whatever the scenario declares
  "critical_functions": [{"function": "repair", "flag": "SINGLE_PROVIDER",
                          "providers": ["C2"]}],

  "events": [ /* §5 */ ],

  "sampled": {                                           // null when MC not run
    "samples": 50,
    "counts": {"hazard_contained_to_sources": 50, "no_crew_trapped": 50},
    "capability_counts": {"RETURN": {"available": 50, "applicable": true}},
    "means": {"total_exposure_seconds": 0.0, "peak_smac_dose": 0.004},
    "notes": ["Counts over sampled scenario assumptions; ..."]
  },

  "provenance": {"engine": "spacecraft_sim 0.2.0", "horizon_s": 3600, "dt_s": 30,
                 "seed": 42, "ethics_notice": "...VERIFIED_/ASSUMED_..."}
}
```

`CaseAnalysis` = `{scenario_digest, mission_phase, capability_names[], criticality[],
actions: [ActionAnalysis]}`. `criticality` carries `measured_criticality` once per
case (it is action-scoped in Phase A but agents compare across actions, so the
adapter runs it for a named baseline action and labels which one).

**Deliberately not duplicated:** the full `final` Scenario, raw timeline frames,
per-frame CO. Those stay retrievable by id for the UI and debugging.

---

## 5. Timeline event extraction

Semantic first, as the spec asked. From 120 frames, emit typed events:

| Event | Trigger |
|---|---|
| `detection_confirmed` | `detected_at_seconds` reached |
| `hazard_arrival` | module's extinction first crosses the alarm level (0.033 /m) |
| `smac_exceeded` | module's peak first reaches a 1-hour SMAC |
| `crew_state_change` | `frame.crew[cid]` differs from the previous frame |
| `crew_module_change` | `frame.crew_modules[cid]` differs |
| `system_state_change` | `frame.systems[sid]` differs |
| `capability_change` | **derived** from system states (§0.3), flagged `derived: true` |
| `extinction_milestone` | burning module's extinction peaks, then falls below peak/2 |

Each event: `{t, type, subject, from, to, source: "timeline" | "derived"}`.
Typical volume: ~10–30 events per action versus 120 frames × 5 dicts — small enough
for a prompt and *more* informative than a sampled curve.

Optional uniform downsampling (every k-th frame) exists only as a debug aid and is
**off by default**; when enabled it is recorded in `provenance` so nobody mistakes a
sampled curve for the full one.

---

## 6. Agents

All agents share one output contract:

```python
class AgentFinding(BaseModel):
    agent: str
    action_id: str | None
    claims: list[Claim]
    concerns: list[str]
    open_questions: list[str]

class Claim(BaseModel):
    statement: str
    basis: Literal["SIMULATION_FACT", "EVIDENCE", "INFERENCE", "ASSUMPTION"]
    refs: list[str]      # JSON-pointer into ActionAnalysis, or an evidence citation id
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
```

`basis` plus `refs` are what make §7's validator possible: an agent that wants to
state a number must point at where the number came from.

**6.1 Hazard** — reads `detection`, `hazard`, hazard events, and the scenario's
pathway state. Answers containment reach, which pathway mattered, whether exposure
thresholds were crossed, and what changed over time. Must separate "the simulator
produced this" from "this depends on Phase A assumptions" — it is handed the
`VERIFIED_`/`ASSUMED_` provenance notice for exactly that purpose. Forbidden: new
spread rates, growth rates, detection times, physical constants.

**6.2 Crew Safety** — reads `crew` (dict keyed by crew_id), `crew_counts`, crew
events, resource state, modeled survival/return estimates, and `criticality`.
Reasons about exposure, evacuation feasibility, trapped state, module transitions,
and loss-of-provider consequences. It may prioritize or identify an explicit
abandonment alternative by counterfactual expected-returnee impact, but never by
intrinsic human worth. Criticality remains *function irreplaceability under the
current situation*, not the value of a life.

**6.3 Systems** *(proposed — spec truncated)* — reads `systems`, `system_reasons`,
`equipment`. The load-bearing distinction it must preserve is Phase A's
recoverability semantics: `UNAVAILABLE` (isolated / powered down / no operator —
reversible) versus `FAILED_EXPLICITLY` (damaged — not reversible without repair).
`system_reasons` supplies the cause verbatim; the agent should quote it, not guess.

**6.4 Mission** *(proposed)* — reads `capabilities`, `critical_functions`,
`mission_phase`. Iterates whatever capabilities the scenario declares. Judges mission
continuation, habitability, and return posture *as this scenario defines them*, and
says so explicitly rather than implying universal categories.

**6.5 Evidence / RAG** *(proposed)* — independent of Phase A. Retrieves from a local
NASA corpus and returns `EvidenceAnswer{claim, citation, applicability, limits}`.
**It never decides.** Applicability is mandatory: an ISS ventilation figure may not
transfer to a different vehicle, and ground-test combustion data does not transfer to
microgravity (Saffire: pyrolysis spread 18–24× slower while fuel burnout is only
1.6–3× slower). Starter corpus, all verified during Phase A calibration: JSC 20584
Rev C (SMAC), Saffire I/II, NASA-STD-6001B Test 1, NTRS 20150009509 (IMV), NTRS
20030053429 (fire detection), MIL-STD-1629A (FMECA). Each chunk stores
`{text, source_id, title, locator, retrieved_on}`; a citation without a locator is
rejected at ingest.

**6.6 Critic / Red-Team** *(proposed)* — reads every other finding **plus** the raw
`ActionAnalysis`, and hunts for: unsupported numbers; sampled counts phrased as
probability; simulator values generalized into universal truths; pathways or actions
nobody discussed; contradictions between agents; capability claims resting on the
§0.2 vacuous-count trap; single-provider risks left unmentioned. Emits
`CriticReview{severity, target_claim_ref, issue, suggested_correction}`. Findings that
fail §7 validation surface here rather than being silently dropped.

**6.7 Decision Coordinator** *(proposed)* — the only agent permitted to recommend.
Consumes all findings, the critic review, and the full `CaseAnalysis`. Emits:

```python
Recommendation(
  recommended_action_id: str,
  rationale: list[Claim],
  tradeoffs: list[Tradeoff],        # what this action costs against each alternative
  dissent: list[str],               # unresolved critic issues
  uncertainty: list[str],           # including what Monte Carlo did and did not cover
  human_decision_required: bool = True,
)
```

It must name at least one trade-off and reproduce the sampled-counts phrasing rule. A
recommendation with no trade-off and no uncertainty is rejected by the validator —
that shape is precisely how such systems get over-trusted.

---

## 7. Grounding enforcement (the core safety mechanism)

Prompt instructions alone do not stop fabrication. Two machine checks do:

**7.1 Fact registry.** Before any agent runs, the orchestrator walks the
`ActionAnalysis` and builds `{json_pointer -> value}` for every scalar. That is the
complete set of numbers an agent is allowed to state.

**7.2 Validator.** After each agent returns:

1. Extract every numeric literal from the prose.
2. Each must match a registry value (relative tolerance 1e-6, with a rounding
   allowance), **or** appear in a cited evidence chunk, **or** sit inside a claim
   marked `INFERENCE`/`ASSUMPTION` that carries no numeric assertion.
3. Every `SIMULATION_FACT` claim must carry at least one `refs` pointer that resolves.
4. Regex gate: `%`, "probability", "likelihood", or "chance" adjacent to a `sampled.*`
   reference is rejected, with the `k of n` rewrite offered.
5. Banned-phrase gate: "BEST ACTION" outside the Coordinator. Survival or
   mortality claims are allowed only when grounded in the modeled fields or a
   cited source; sampled-run counts still cannot be relabelled as probability.

Failures route to the Critic and appear in the output. **Nothing is silently edited** —
the operator sees that an agent attempted an unsupported assertion.

---

## 8. LLM boundary

```python
class LLMClient(Protocol):
    def complete(self, *, system: str, user: str,
                 schema: type[BaseModel], temperature: float = 0.0) -> BaseModel: ...
```

- `GraniteClient` — IBM Granite via watsonx (fits the challenge), configured by env var.
- `StubLLMClient` — deterministic, offline, returns fixture findings. **Every test in
  the suite runs on the stub**, so CI needs no key and no network.

Structured output is enforced by schema-validated parsing with one retry on parse
failure, then a typed error — never a free-text fallback.

---

## 9. Integration with Phase A and Phase B

**Phase A — read-only, zero changes.** Only `providers/phase_a.py` imports it, and
only through the five documented entry points. Phase C pins the engine version in
`provenance`; a mismatch raises rather than guessing.

**Phase B — additive.** Its existing `POST /api/simulate` is untouched.

- New `POST /api/analyze` runs the Phase C pipeline and returns a `DecisionPackage`
  (findings, critic review, recommendation, provenance).
- Phase B already has its own `PhaseASimulatorAdapter`; Phase C's provider sits beside
  it, not inside it. The two share the engine but not code paths.
- Frontend: a new **Advisor** panel on the results page — per-agent findings, critic
  flags inline, coordinator recommendation with trade-offs and an explicit "you
  decide" affordance. The existing comparison table stays recommendation-free, as
  Phase B intends; recommendation appears only in the Advisor panel.
- The existing disclaimer banner gains an agent-provenance line.

Long-running work: analysis is far slower than simulation (seven agents × LLM calls),
so the endpoint returns a job id immediately and the UI polls. That keeps Phase B
responsive and avoids a request timeout.

---

## 10. Test strategy

- **Fixtures.** Capture real Phase A output (demo scenario, every action,
  deterministic plus Monte Carlo at seed 42) once; commit as JSON. All agent tests
  replay it.
- **Adapter.** Round-trips every contract §8 gap; `detected_at_seconds: null` becomes
  `NEVER_DETECTED`; equipment is present; capability dict passes through, with a
  non-`RETURN` scenario proving the §0.2 gating works.
- **Events.** A closed hatch produces no downstream `hazard_arrival`; derived
  `capability_change` agrees with the summary end state.
- **Grounding.** Adversarial fixtures where the stub LLM emits an invented number, a
  percentage on a sampled count, and an unreferenced `SIMULATION_FACT` — the validator
  must catch all three.
- **Isolation.** No `spacecraft_sim` import outside the adapter; Phase A's own suite
  (90 tests) still green afterwards.
- **Coordinator.** Rejects a recommendation with no trade-off; always sets
  `human_decision_required`.
- **Integration.** Phase B `/api/analyze` end-to-end on the stub client.

---

## 11. Implementation order

Each step ends green and is independently reviewable.

1. **Contracts** (`contracts/`) plus fixtures captured from real Phase A output.
2. **Adapter** and `MockSimulationProvider`, with the §8 gap tests.
3. **Timeline events.**
4. **Grounding registry and validator** — built before any agent exists, so agents are
   written against a live check instead of having one retrofitted.
5. **LLM boundary and stub.**
6. **Hazard and Crew agents** (the two your spec fully specified).
7. **Systems and Mission agents** — *pending your review of §6.3–6.4.*
8. **RAG corpus and Evidence agent.**
9. **Critic.**
10. **Coordinator.**
11. **Orchestrator** end-to-end on fixtures.
12. **Phase B endpoint and Advisor panel.**
13. **Granite client**, wired last, behind the same boundary the stub already proved.

---

## 12. Decisions I need from you

1. **Implement now, or stop here?** Your spec says plan-only and stop; your closing
   line asks to execute and integrate. I stopped at the plan.
2. **The truncated sections.** Do you have the real requirements for Systems, Mission,
   Evidence, Critic, and Coordinator? §6.3–6.7 are my proposal.
3. **Granite access.** Do you have watsonx credentials, or should Phase C ship
   stub-only until you do? Everything above is testable without them.
4. **Phase A defect §0.2.** Leave the vacuous Monte Carlo capability counts to the
   adapter as planned, or open a separate Phase A fix later?
5. **RAG scope.** Start with the six already-verified NASA sources, or gather a wider
   corpus first?
