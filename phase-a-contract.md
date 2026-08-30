# Phase A — Output Contract (as built, 2026-08-22)

Integration specification for Phase B (UI) and Phase C (multi-agent AI).
Generated from the actual implementation in `spacecraft-sim/src/spacecraft_sim/`,
not from a plan. Every JSON block below is real output from
`examples/demo_spacecraft.json`.

> **`phase-a-plan.md` in this folder is STALE.** It describes the retired
> FastAPI + React prototype with probabilistic fire spread. Do not use it as an
> integration spec. This file supersedes it for anything about interfaces.

---

## 0. What Phase A actually is

A Python library + Typer CLI. **No HTTP server, no JSON output mode today.**
Phase B/C consume it by importing the package:

```python
from spacecraft_sim.models import Scenario
from spacecraft_sim.actions import generate_actions, find_action
from spacecraft_sim.engine import counterfactual
from spacecraft_sim.montecarlo import run_montecarlo
from spacecraft_sim.crew import measured_criticality
```

Five entry points, five result shapes:

| Call | Returns | Purpose |
|---|---|---|
| `generate_actions(scenario)` | `list[Action]` | candidate actions for this graph |
| `counterfactual(scenario, action, ...)` | `TimelineResult` | one action, deterministic |
| `run_montecarlo(scenario, action, n, seed)` | `Distribution` | counts over sampled assumptions |
| `measured_criticality(scenario, action)` | `list[dict]` | leave-one-out crew criticality |
| `evaluate_capabilities(scenario)` | `dict[str,str]` | capability roll-up (used internally) |

---

## 1. Input — `Scenario` (pydantic, Phase B emits this)

```
Scenario
├── modules: [Module]          # id, name, type, volume_m3, atmosphere{pressure,o2},
│                              # fire_state: non|incipient|sustained|suppressed,
│                              # source_profile_id, species_mg_m3{CO,HCN,soot},
│                              # temperature_c, detected, detector_streak, isolated,
│                              # crew_ids[], equipment_ids[]
├── connections: [Connection]  # id, source, target, type: hatch|imv|leak,
│                              # path_state: open|closed|unknown,
│                              # ventilation_state: on|off, airflow_direction,
│                              # flow_m3_s (null = unknown -> MC samples it)
├── crew: [Crew]               # id, name, role, provides_functions[], module_id,
│                              # state: SAFE|EXPOSED|EVACUATING|EVACUATED|TRAPPED,
│                              # hazard_exposure_seconds, smac_dose_fraction
├── equipment: [Equipment]     # id, name, module_id, system, powered, damaged,
│                              # repair_progress_seconds
├── systems: [System]          # id, name, state, depends_on_modules[],
│                              # depends_on_equipment[], operator_function,
│                              # repair_function, unavailable_reason
├── capabilities: {CAP: [system_id]}   # e.g. {"RETURN": ["power","propulsion","gnc"]}
└── mission_phase: str                 # "cruise" | ...
```

No fixed topology. Any module count, any ids. `Scenario.model_validate_json(text)`
and `scenario.model_dump_json()` are the serialization boundary.

Engine defaults: `DT_SECONDS = 30.0`, `HORIZON_SECONDS = 3600.0` →
timeline is **120 steps**. `MONTECARLO_SAMPLES = 1000`.
Tracked species: `("CO", "HCN", "soot")`.

---

## 2. `Action` (frozen dataclass — NOT pydantic)

```python
Action(id: str, kind: str, label: str, description: str, params: dict)
```

`kind` is one of `do_nothing | close_hatch | close_imv | shutdown_ventilation |
isolate | evacuate | power_down | station_repairer`.

`id` encodes the target: `"isolate:M2"`, `"close_hatch:c_m1_m2"`,
`"evacuate:C3:M4"`, `"station_repairer:C2:M3"`. Real output for the demo:

```
do_nothing                     Do nothing
close_hatch:c_m1_m2            Close hatch M1-M2
shutdown_ventilation:c_m2_m3   Shut down ventilation M2-M3
close_imv:c_m2_m3              Close IMV duct M2-M3
isolate:M2                     Isolate Storage (M2)
station_repairer:C2:M3         Station C2 in Life Support (M3)
station_repairer:C2:M4         Station C2 in Power (M4)
station_repairer:C2:M5         Station C2 in Propulsion (M5)
```

Actions are **generated from the graph**, so the candidate set differs per
scenario. Phase C must not hardcode action ids; call `generate_actions` (or the
adapter's equivalent) and treat ids as opaque strings, using `kind` / `params`
for semantics. `find_action(scenario, id)` raises `KeyError` for an unavailable id.

---

## 3. Deterministic result — `TimelineResult`

```python
@dataclass
class TimelineResult:
    action_id: str
    timeline: list[dict]     # 120 entries at default settings
    final: Scenario | None   # full post-run world state (pydantic)
    summary: dict            # the flat fact sheet below
```

Note: plain dataclass. `.summary` is a **plain dict**, not a model — there is no
`.model_dump()` on the result. Only `.final` is pydantic.

### 3.1 `summary` — the primary Phase C input

Real output, `action = "isolate:M2"`:

```json
{
  "action_id": "isolate:M2",
  "detected_at_seconds": 270.0,
  "hazard_reached": ["M2"],
  "smac_exceeded": ["M2"],
  "peak_extinction_per_m": {"M1":0.00047,"M2":1.52296,"M3":0.00321,"M4":0.00043,"M5":0.0001},
  "crew": {
    "C1": {"state":"SAFE","exposure_seconds":0.0,"smac_dose_fraction":0.0007,"module":"M1"},
    "C2": {"state":"SAFE","exposure_seconds":0.0,"smac_dose_fraction":0.0007,"module":"M1"},
    "C3": {"state":"SAFE","exposure_seconds":0.0,"smac_dose_fraction":0.0043,"module":"M3"},
    "C4": {"state":"SAFE","exposure_seconds":0.0,"smac_dose_fraction":0.0007,"module":"M4"}
  },
  "crew_counts": {"SAFE":4,"EXPOSED":0,"EVACUATING":0,"EVACUATED":0,"TRAPPED":0},
  "systems": {"life_support":"OPERATIONAL","power":"OPERATIONAL",
              "propulsion":"OPERATIONAL","gnc":"OPERATIONAL"},
  "system_reasons": {},
  "capabilities": {"RETURN":"AVAILABLE","HABITATION":"AVAILABLE"},
  "critical_functions": [
    {"function":"command_decision","flag":"SINGLE_PROVIDER","providers":["C1"]},
    {"function":"life_support_ops","flag":"SINGLE_PROVIDER","providers":["C2"]},
    {"function":"repair","flag":"SINGLE_PROVIDER","providers":["C2"]}
  ]
}
```

Field semantics:

| Field | Meaning |
|---|---|
| `detected_at_seconds` | `float` or `null`. **null = never detected** — smoke stayed below the ISS detector alarm level, so the action was applied only at the end of the horizon. Phase C must handle null. Detection is computed, not assumed. |
| `hazard_reached` | sorted module ids whose *peak* smoke extinction reached 0.033 /m (verified ISS alarm level) |
| `smac_exceeded` | sorted module ids whose peak concentration reached a 1-hour SMAC (JSC 20584 Rev C) |
| `peak_extinction_per_m` | per-module peak obscuration, 1/m. The burning module is normally far above 1.0 |
| `crew` | **dict keyed by crew_id**, not a list. `smac_dose_fraction` 1.0 = one hour at the 1-hour limit |
| `crew_counts` | always all five states, zero-filled |
| `systems` | `OPERATIONAL / EXPOSED_AT_RISK / UNAVAILABLE / FAILED_EXPLICITLY` — defined by *recoverability*, not cause |
| `system_reasons` | only non-operational systems appear. Values: `equipment_damaged`, `module_isolated`, `equipment_powered_down`, `no_operator:<function>`, `smoke_or_fire_in_module` |
| `capabilities` | `AVAILABLE / AT_RISK / UNAVAILABLE`, keyed by whatever caps the scenario declares (demo: `RETURN`, `HABITATION`) |
| `critical_functions` | list, possibly empty. `flag` is `SINGLE_PROVIDER` or `NO_PROVIDER` |

Survival and return probabilities are explicit modeled outputs. They come from
`ASSUMED_*` response curves and must not be presented as clinically validated
forecasts. Phase A still reports outcomes; action recommendation belongs to
Phase C.
That judgment is Phase C's, and ultimately the human's.

### 3.2 `timeline[i]` — 120 frames for Phase B charts

```json
{
  "t": 3600.0,
  "extinction":    {"M1":0.00026,"M2":1.52296,"M3":0.00132,"M4":0.0004,"M5":0.0001},
  "co_mg_m3":      {"M1":0.085,"M2":500.972,"M3":0.434,"M4":0.131,"M5":0.032},
  "crew":          {"C1":"SAFE","C2":"SAFE","C3":"SAFE","C4":"SAFE"},
  "crew_modules":  {"C1":"M1","C2":"M1","C3":"M3","C4":"M4"},
  "systems":       {"life_support":"OPERATIONAL","power":"OPERATIONAL",
                    "propulsion":"OPERATIONAL","gnc":"OPERATIONAL"}
}
```

`t` is the time at the **end** of the step, so `timeline[0]["t"] == dt == 30.0`.
Only CO and soot-derived extinction are exposed per frame; HCN is tracked
internally but summarized only via the SMAC fields.

### 3.3 `final` — full post-run `Scenario`

The only place **equipment state** (`damaged`, `powered`, `repair_progress_seconds`)
and per-module `species_mg_m3` / `temperature_c` are available.
Use `result.final.model_dump()` for a JSON view.

---

## 4. Monte Carlo — `Distribution` (dataclass)

Counts, never probabilities. Each sample draws one plausible world (decision
delay, crew response time, unknown leak open/closed, flow jitter, unknown source
profile) and runs the deterministic engine on it.

```python
Distribution(
  action_id: str, samples: int,
  retained_evacuation_and_return: int,
  no_crew_trapped: int,
  all_crew_safe_or_evacuated: int,
  return_available: int,
  habitation_available: int,
  hazard_contained_to_sources: int,
  no_crew_reached_smac_dose: int,
  mean_total_exposure_seconds: float,
  mean_peak_smac_dose: float,
  notes: list[str],
)
```

Real run, `isolate:M2`, n=50, seed=42 → `50/50` on every count.

**Phrasing rule for Phase C:** report as *"k of n sampled assumption sets"*.
Never render as a percentage survival/success probability. `notes` already
carries the disclaimer — surface it rather than dropping it.

`run_montecarlo` returns `Distribution` **separately** from `TimelineResult`;
it is not nested inside `summary`. An adapter must join them.

---

## 5. Crew criticality — `measured_criticality(...) -> list[dict]`

```json
[
  {"crew_id":"C2","role":"engineer", "measured_score":0.5,  "assumed_weight":2.7},
  {"crew_id":"C4","role":"pilot",    "measured_score":0.25, "assumed_weight":1.3},
  {"crew_id":"C1","role":"commander","measured_score":0.0,  "assumed_weight":0.9},
  {"crew_id":"C3","role":"medic",    "measured_score":0.0,  "assumed_weight":0.6}
]
```

Sorted by `measured_score` descending. `measured_score` = capability score lost
when that crew member is removed (leave-one-out, engine-measured).
`assumed_weight` = FMECA-style table value from `config.ASSUMED_*`.
**Neither is a valuation of a life** — this is function irreplaceability under
the current situation. Phase C must carry that framing into any prompt.

Roles map to functions via `config.ROLE_FUNCTIONS` unless `Crew.provides_functions`
is set (Phase B should set it explicitly):

```
commander -> {command_decision}
engineer  -> {repair, power_ops, life_support_ops}
medic     -> {medical}
pilot     -> {propulsion_ops, navigation}
scientist -> {science}
```

---

## 6. Action comparison (what Phase B's table shows)

`compare` runs every generated action and prints facts side by side — real output:

```
action                        detect_s smoke_reached  trapped evac expo_s  dose     RETURN  HABITATION
do_nothing                        270  M1,M2,M3,M4          0    1    150  0.370   AT_RISK     AT_RISK
close_hatch:c_m1_m2               270  M2,M3,M4             0    1    150  0.342   AT_RISK     AT_RISK
shutdown_ventilation:c_m2_m3      270  M1,M2                0    0      0  0.088   AT_RISK   AVAILABLE
close_imv:c_m2_m3                 270  M1,M2                0    0      0  0.088   AT_RISK   AVAILABLE
isolate:M2                        270  M2                   0    0      0  0.004 AVAILABLE   AVAILABLE
station_repairer:C2:M3            270  M1,M2,M3,M4          0    2    270  0.370   AT_RISK     AT_RISK

(Facts only — no recommendation is made at this phase.)
```

There is **no ranking column by design**. The comparison is a
`list[TimelineResult]`; every derived column above is computed from `summary`.

---

## 7. Agent → data mapping for Phase C

Corrected against the real schema (there is no top-level `hazard` or
`equipment` key on `summary`):

| Agent | Reads |
|---|---|
| Hazard | `detected_at_seconds`, `hazard_reached`, `smac_exceeded`, `peak_extinction_per_m`, `timeline[].extinction` / `.co_mg_m3` |
| Crew | `crew`, `crew_counts`, `timeline[].crew` / `.crew_modules`, `measured_criticality` |
| Systems | `systems`, `system_reasons`, **`final.equipment`** (not in `summary`) |
| Mission | `capabilities`, `critical_functions`, `scenario.mission_phase` |
| Critic | `Distribution` counts + the `notes` disclaimer |
| Coordinator | the `compare` list of summaries |
| Evidence / RAG | independent of Phase A |

---

## 8. Known gaps an adapter must close

1. **No JSON CLI mode.** `simulate` / `compare` / `montecarlo` print formatted
   text only. Either add a `--json` flag to Phase A, or have Phase C import the
   library and serialize `summary` itself.
2. **`TimelineResult` and `Distribution` are dataclasses**, not pydantic —
   `dataclasses.asdict()` works, but `final` inside it needs `model_dump()`.
3. **Monte Carlo is a separate call** and a separate object from the
   deterministic run. Nothing joins them today.
4. **Equipment state is absent from `summary`** — only in `final`.
5. **Timeline is heavy** — 120 frames × 5 dicts per action. Do not feed raw
   timelines to an LLM; downsample or aggregate in the adapter.
6. **Capability keys are scenario-defined.** `RETURN` / `HABITATION` come from
   the demo file, not the engine. Never hardcode them; iterate the dict.

Phase C should depend only on this document's shapes, behind:

```python
class SimulationResultProvider:
    def get_results(self, scenario) -> ...   # MockSimulationProvider today
                                             # PhaseASimulationAdapter later
```

and never import `spacecraft_sim.hazard`, `.crew`, or `.capability` internals.
