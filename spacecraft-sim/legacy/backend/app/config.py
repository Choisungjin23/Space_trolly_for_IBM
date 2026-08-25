"""All tunable simulation parameters in one place.

IMPORTANT — PoC assumption notice:
Every value in this file is a configurable proof-of-concept assumption chosen
to produce demonstrable, plausible-looking behavior. None of these numbers
come from a physically validated fire model (NASA or otherwise). They exist
so the whole parameter set can later be replaced with evidence-based values
without touching the simulation code.

`SimulationConfig` holds the defaults. The GUI edits a copy of it: FIELD_SPECS
below describes every numeric field (bounds, step, label, help text) so the
frontend can render controls without duplicating those limits, and the API
validates incoming values against the same specs.
"""

from dataclasses import dataclass, fields, replace
from typing import Any


@dataclass(frozen=True)
class SimulationConfig:
    # --- Fire propagation ---
    # P(spread i -> j per step) = fire_severity_i * hazard_spread_probability_ij * propagation_factor
    propagation_factor: float = 1.0
    # Severity a module starts with when fire spreads into it.
    ignition_severity: float = 0.3
    # Severity added per step to every module that was burning at the start of the step.
    growth_rate: float = 0.1
    # Per burning module per step: chance that suppression/burnout reduces severity.
    extinguish_prob: float = 0.05
    extinguish_amount: float = 0.2

    # --- System damage ---
    # A module at or above this severity may destroy its onboard systems.
    system_damage_threshold: float = 0.8
    # Per system per step chance of failing once the threshold is reached.
    system_failure_prob: float = 0.5

    # --- Crew hazard ---
    # Crew react (evacuate or risk death) at or above this severity.
    crew_hazard_threshold: float = 0.5
    # P(fatality per crew member per step) = fire_severity * crew_fatality_factor,
    # applied only when evacuation is impossible.
    crew_fatality_factor: float = 0.3

    # --- Simulation horizon ---
    sim_steps: int = 10

    # --- Initial scenario ---
    initial_fire_module: str = "M2"
    initial_fire_severity: float = 0.6
    # Base per-connection hazard spread probability used for every connection.
    connection_hazard_probability: float = 0.35
    # Which module each crew member starts in. Tuple-of-pairs keeps the dataclass
    # frozen/hashable; the API exposes it as a {crew_id: module_id} object.
    crew_placement: tuple[tuple[str, str], ...] = (
        ("C1", "M1"),
        ("C2", "M1"),
        ("C3", "M3"),
        ("C4", "M4"),
    )

    # --- Metrics ---
    # Systems whose survival defines the critical-system metric.
    critical_systems: tuple[str, ...] = ("life_support", "power", "propulsion")
    # PoC assumption: a run "survives" iff >=1 crew alive AND these systems work
    # at the end. Propulsion loss degrades but does not end the mission.
    mission_required_systems: tuple[str, ...] = ("life_support", "power")


DEFAULT_CONFIG = SimulationConfig()

# Monte Carlo defaults / limits (API layer)
DEFAULT_RUNS = 1000
MAX_RUNS = 10000


# --- GUI-editable numeric fields -------------------------------------------
# Single source of truth for the controls the frontend renders and the bounds
# the API enforces. Adding a parameter here makes it appear in the GUI.

FIELD_SPECS: list[dict[str, Any]] = [
    {
        "key": "initial_fire_severity",
        "label": "Initial fire severity",
        "group": "Scenario",
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
        "integer": False,
        "help": "How intense the fire is at t=0 in the module where it starts.",
    },
    {
        "key": "connection_hazard_probability",
        "label": "Connection hazard probability",
        "group": "Scenario",
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
        "integer": False,
        "help": "Base spread chance carried by every connection (hatch leakiness).",
    },
    {
        "key": "sim_steps",
        "label": "Simulation steps",
        "group": "Scenario",
        "min": 1,
        "max": 50,
        "step": 1,
        "integer": True,
        "help": "How many discrete time steps each Monte Carlo run simulates.",
    },
    {
        "key": "propagation_factor",
        "label": "Propagation factor",
        "group": "Fire propagation",
        "min": 0.0,
        "max": 5.0,
        "step": 0.1,
        "integer": False,
        "help": "Global multiplier on every spread probability. 0 = fire never spreads.",
    },
    {
        "key": "ignition_severity",
        "label": "Ignition severity",
        "group": "Fire propagation",
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
        "integer": False,
        "help": "Severity a module starts at when fire spreads into it.",
    },
    {
        "key": "growth_rate",
        "label": "Growth rate per step",
        "group": "Fire propagation",
        "min": 0.0,
        "max": 1.0,
        "step": 0.02,
        "integer": False,
        "help": "Severity added each step to a module that is already burning.",
    },
    {
        "key": "extinguish_prob",
        "label": "Burnout/suppression chance",
        "group": "Fire propagation",
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
        "integer": False,
        "help": "Per burning module per step, chance the fire weakens.",
    },
    {
        "key": "extinguish_amount",
        "label": "Burnout severity drop",
        "group": "Fire propagation",
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
        "integer": False,
        "help": "How much severity is removed when burnout/suppression happens.",
    },
    {
        "key": "system_damage_threshold",
        "label": "System damage threshold",
        "group": "Damage & crew",
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
        "integer": False,
        "help": "Severity at which a module starts destroying its own systems.",
    },
    {
        "key": "system_failure_prob",
        "label": "System failure chance",
        "group": "Damage & crew",
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
        "integer": False,
        "help": "Per system per step failure chance once above the threshold.",
    },
    {
        "key": "crew_hazard_threshold",
        "label": "Crew hazard threshold",
        "group": "Damage & crew",
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
        "integer": False,
        "help": "Severity at which crew evacuate, or start risking death if trapped.",
    },
    {
        "key": "crew_fatality_factor",
        "label": "Crew fatality factor",
        "group": "Damage & crew",
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
        "integer": False,
        "help": "P(death per trapped crew member per step) = severity x this factor.",
    },
]

FIELD_SPEC_BY_KEY = {spec["key"]: spec for spec in FIELD_SPECS}
_CONFIG_FIELD_NAMES = {f.name for f in fields(SimulationConfig)}


def build_config(overrides: dict[str, Any] | None = None) -> SimulationConfig:
    """Return DEFAULT_CONFIG with `overrides` applied, clamped to FIELD_SPECS bounds.

    Unknown keys are ignored so the API never crashes on an extra field.
    """
    if not overrides:
        return DEFAULT_CONFIG

    clean: dict[str, Any] = {}
    for key, value in overrides.items():
        if key not in _CONFIG_FIELD_NAMES or value is None:
            continue
        spec = FIELD_SPEC_BY_KEY.get(key)
        if spec is not None:
            value = min(spec["max"], max(spec["min"], value))
            value = int(round(value)) if spec["integer"] else float(value)
        clean[key] = value

    if "crew_placement" in clean and isinstance(clean["crew_placement"], dict):
        clean["crew_placement"] = tuple(sorted(clean["crew_placement"].items()))

    return replace(DEFAULT_CONFIG, **clean)
