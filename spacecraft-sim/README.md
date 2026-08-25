# Spacecraft Emergency Simulator — Phase A: Generic Simulation Engine

Proof-of-concept for an AI-assisted spacecraft emergency decision-support
system (IBM AI Builders Challenge). Phase A is a **generic, graph-based
emergency simulation engine** with a CLI — no AI, no UI yet:

```
build spacecraft graph → current state → inject emergency → generate actions
→ generic simulation engine → counterfactual outcomes (facts, no recommendation)
```

The engine runs in **real physical units**, calibrated against NASA primary
sources where they exist. See [`docs/nasa-calibration-report.html`](docs/nasa-calibration-report.html)
for the source survey and the unit-conversion design.

Phase B (sandbox canvas UI) and Phase C (multi-agent Mission Control AI) come
later. An earlier FastAPI + React prototype is kept in `legacy/` for reference.

## Design principles

1. **The simulator produces the numbers; AI never invents them.**
2. Values that cannot be calibrated from evidence were **removed**:
   `PROPAGATION_FACTOR`, generic spread probabilities, `CREW_FATALITY_FACTOR`,
   `P(death)`, generic system-failure probabilities, a global fire
   `GROWTH_RATE`. Tests enforce their absence.
3. Every constant lives in `src/spacecraft_sim/config.py` and **declares its
   provenance in its name**: `VERIFIED_*` came from a NASA primary source,
   `ASSUMED_*` is an unvalidated PoC assumption. A test fails the build if a
   constant declares neither.
4. The engine is size-agnostic: 3 or 15 modules, any ids — no
   `isolate_m2()`-style hardcoding. The 5-module ship is just a demo file.
5. Ethically sensitive assumptions (crew criticality) are labelled: **PoC
   assumptions, not mission norms.**

Run `spacecraft-sim provenance` to print the notice and the full source list.

## World state (A-2, A-3)

No `fire_severity` scalar and no dimensionless "load". A module carries a free
`volume_m3`, `atmosphere` (pressure, O2), `fire_state`
(`non | incipient | sustained | suppressed`), a `source_profile_id`, per-species
concentrations in **mg/m³**, `temperature_c`, and detector state.

Connections are **typed edges** carrying a real volumetric flow:
`type` (`hatch | imv | leak`), `path_state` (`open | closed | unknown`),
`ventilation_state`, `airflow_direction`, and `flow_m3_s` (None = unknown, which
Monte Carlo samples).

## Fire source profiles (A-4)

Saffire-inspired — fire behaviour depends on material, geometry, O2, pressure
and airflow, so there is **no single global growth rate**. A profile's primary
quantity is the fuel **mass loss rate in mg/s**; species emission is that times
a yield.

`STEADY_FABRIC_SPREAD` is derived as `18.0 mg/cm² × 0.1 cm/s × 40 cm = 72 mg/s`,
where the SIBAL fabric area density is verified (Saffire-I) and the spread rate
and burn width are assumed.

> ⚠️ Profiles are **inspired by** Saffire findings — not a validated NASA fire model.

## Hazard transport (A-5)

A real-unit mass balance, per species s and module j:

```
V_j · dC_s,j/dt = Σ_i Q_ij · (C_s,i − C_s,j) + Y_s · ṁ_j − Q_scrub · C_s,j
```

`V` m³ · `C` mg/m³ · `Q` m³/s · `ṁ` mg/s · `Y` mg/mg.

Because exchange is `(C_i − C_j)` rather than a one-way push from the fire,
**smoke now propagates multi-hop**: a module that fills with smoke becomes a
source for its own neighbours. This removed the single-hop limitation of the
earlier dimensionless model.

Closed paths, ventilation-off IMV ducts, zero flow, and isolated endpoints
transport nothing.

## Detection is computed, not assumed

A module alarms once smoke extinction passes the **verified ISS detector
threshold of 0.033 /m** (= 1 %/ft obscuration) on two consecutive readings.
ISS detectors sit on ventilation intake ducts, so an **unventilated module takes
an assumed penalty factor longer to confirm** — cutting ventilation slows your
own alarm. The action then lands at `detection time + decision delay`, so "how
fast the crew learn" is an emergent property rather than a free parameter.

## Crew (A-6): states and dose, never death odds

`SAFE → EXPOSED → EVACUATING → EVACUATED | TRAPPED`, plus
`hazard_exposure_seconds` and a cumulative **`smac_dose_fraction`** where 1.0
means the equivalent of one hour at the 1-hour SMAC limit.

A module is hazardous when it is burning, when any species exceeds its 1-hour
SMAC (JSC 20584 Rev C: CO 485, HCN 9, HCl 8 mg/m³), or when extinction passes
the assumed egress-impairment level. **HCN's limit is 54× stricter than CO's**,
which is why species are tracked separately.

Crew evacuate through **open hatches only** (IMV ducts are not passages),
re-plan when a hatch closes mid-route, and are TRAPPED when no route exists.
There is no fatality formula anywhere.

## Capability graph (A-7) and crew coupling (A-8.2)

Systems depend on modules, equipment **and crew**; capabilities (`RETURN`,
`HABITATION`) depend on systems. The four states are defined by
*recoverability*: `FAILED_EXPLICITLY` (equipment damaged) · `UNAVAILABLE`
(isolated, powered down, or **no available operator**) · `EXPOSED_AT_RISK`
(detectable smoke or fire) · `OPERATIONAL`. Each system also reports an
`unavailable_reason` so an agent can tell "sealed off" from "nobody left who
can run it".

Systems are not self-sufficient boxes — the scenario wires each one to crew
functions:

- **Operating.** A system with an `operator_function` needs at least one
  available (not trapped) crew member providing it. Losing the sole provider
  takes the system down even though the hardware is fine, which is what gives
  the `SINGLE_PROVIDER` warning real teeth.
- **Repairing.** Damaged equipment is no longer permanently lost. It recovers
  while a crew member providing the system's `repair_function` is physically in
  that module, able to work, and the module is not hazardous — so `isolate` and
  `close hatch` actions can cut off a repair by sealing the repairer out.

Both mappings live in the scenario JSON (`operator_function`,
`repair_function`), so the engine stays generic.

## Crew criticality (A-8): two independent routes

**Rule-based (FMECA).** Each function is classified against the MIL-STD-1629A
severity categories (I Catastrophic / II Critical / III Marginal / IV Minor)
with the failure effect that drives the classification recorded alongside it,
and the criticality number is *derived* from that category rather than
hand-written. A crew member's weight is then
`Σ criticality × (1 / available providers) × facility demand`. The factual
output is `critical_functions` — e.g. `life_support_ops = SINGLE_PROVIDER (C2)`.

**Measured (leave-one-out, A-8.5).** `spacecraft-sim criticality` removes each
crew member in turn, re-runs the engine, and reports the capability lost. This
needs no external data and cross-checks the assumed tables. On the demo:

```
crew     role           measured   assumed
C2       engineer         0.5000    2.7000
C4       pilot            0.2500    1.3000
C1       commander        0.0000    0.9000
C3       medic            0.0000    0.6000
```

The two methods agree on the ordering — an independent check that the assumed
table is not wildly off. The zeros are informative too: `command_decision` and
`medical` are not wired to any system in this demo, so the engine measures no
capability loss for them. A scenario that models command or medical dependence
would show otherwise.

> ⚠️ Neither is a valuation of a life. Both express how irreplaceable a
> *function* is right now.

## Monte Carlo (A-10): uncertain assumptions, not spread odds

Each sample draws one plausible world — crew decision delay after the alarm,
crew response time, unknown leak paths open/closed, ±25 % connection-flow
uncertainty, source-profile uncertainty — then runs the deterministic engine.
Output is **counts**: "820 / 1000 samples retained evacuation + return", never
"82 % survival". Seeded runs are reproducible.

## CLI

```
pip install -e .            # or: pip install pydantic numpy typer

spacecraft-sim actions      examples/demo_spacecraft.json
spacecraft-sim simulate     examples/demo_spacecraft.json --action "isolate:M2"
spacecraft-sim compare      examples/demo_spacecraft.json
spacecraft-sim montecarlo   examples/demo_spacecraft.json --action "isolate:M2" -n 1000 --seed 42
spacecraft-sim criticality  examples/demo_spacecraft.json
spacecraft-sim provenance
```

Without installing: `$env:PYTHONPATH="src"` then `python -m spacecraft_sim.cli ...`.

`compare` lists facts side by side and **never designates a BEST ACTION** —
recommendation is reserved for Phase C agents and, ultimately, humans.

## Tests

```
python -m pytest
```

99 tests cover: closed paths / ventilation-off / isolation / zero flow
transporting nothing; flow and module volume affecting concentration as
physics requires; multi-hop propagation; per-profile mass-loss curves and
extinction; computed detection including the unventilated penalty; crew dose
accumulation and state transitions; `UNAVAILABLE` vs `FAILED_EXPLICITLY` and
each `unavailable_reason`; operator loss taking a system down; repair
completing only with a provider on site in a safe module; `station_repairer`
generation and movement; leave-one-out separating crew and agreeing with the
assumed ranking; seeded Monte Carlo reproducibility returning counts; a
size-agnostic engine on arbitrary graphs; the FMECA worksheet carrying a failure effect for every function; per-profile
yields with nitrogen-free fuels emitting no HCN; and two provenance guards —
**no banned constant exists**, and **every tunable constant is prefixed
VERIFIED_ or ASSUMED_**.

## Current limitations

- Crew coupling is coarse: one operator function per system, presence-based
  repair with a single fixed duration, and no skill levels, fatigue, or
  partial degradation.
- `station_repairer` actions are chosen at t=0, so the engine cannot yet model
  dispatching someone *after* damage appears. Actions are single-shot by design
  in Phase A.
- Combustion product yields are now per source profile and partly derived
  rather than guessed: CO comes from the Koylu-Faeth correlation published in
  NISTIR 6784, soot yields sit in the range NIST cites for wood and plastics,
  and HCN is zero for cellulose and PMMA because those molecules contain no
  nitrogen. Ground yields are applied on the argument that ISS cabin air is
  essentially sea-level air; what is *not* taken from the ground is spread
  behaviour, which comes from Saffire.
- Equipment limits and crew timings are `ASSUMED_` but bracketed rather than
  free: the damage temperature sits between the 85 C industrial part rating and
  the ~183 C solder melting point, and the crew hop time is derived from module
  length divided by translation speed plus hatch transit.
- The thermal model is a crude proxy, not a heat balance.
- Atmosphere (pressure/O2) is carried in the state but does not yet feed back
  into fire behaviour.
- One emergency type (fire); leak/depressurization exists only as a connection
  type, not its own emergency model.
- Monte Carlo perturbs flows per sample but shares one global config, so runs
  are single-threaded by construction.
