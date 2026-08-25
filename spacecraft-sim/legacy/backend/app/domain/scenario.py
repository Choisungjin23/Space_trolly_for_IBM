r"""Builds the initial scenario: 5 modules, 4 crew, one burning module.

Topology (undirected):

    M1 --- M2 --- M3
     \            |
      \           |
       M4 --------+
       |
       M5

Edges: M1-M2, M2-M3, M3-M4, M4-M5, M1-M4. The M1-M4 edge creates a cycle on
purpose: it makes "isolate the burning module" and "close a single hatch" lead
to genuinely different outcomes, because fire can still travel the long way
around a closed hatch.

Which module burns, how hard, and where each crew member starts all come from
the SimulationConfig, so the GUI can change them without editing this file.
"""

from app.config import DEFAULT_CONFIG, SimulationConfig
from app.domain.models import Connection, CrewMember, Module, Spacecraft

# (id, display name, onboard systems)
MODULE_DEFS: list[tuple[str, str, list[str]]] = [
    ("M1", "Habitat", ["crew_quarters"]),
    ("M2", "Storage", ["storage"]),
    ("M3", "Life Support", ["life_support"]),
    ("M4", "Power", ["power"]),
    ("M5", "Propulsion", ["propulsion"]),
]

# (id, display name)
CREW_DEFS: list[tuple[str, str]] = [
    ("C1", "Commander Vega"),
    ("C2", "Engineer Okafor"),
    ("C3", "Specialist Lindqvist"),
    ("C4", "Technician Aram"),
]

EDGES = [("M1", "M2"), ("M2", "M3"), ("M3", "M4"), ("M4", "M5"), ("M1", "M4")]

MODULE_IDS = [mid for mid, _, _ in MODULE_DEFS]
CREW_NAMES = dict(CREW_DEFS)


def build_initial_scenario(cfg: SimulationConfig = DEFAULT_CONFIG) -> Spacecraft:
    modules = {
        mid: Module(id=mid, name=name, systems=list(systems))
        for mid, name, systems in MODULE_DEFS
    }

    # Crew placement: unknown crew or module ids are skipped rather than raising,
    # so a stale GUI payload degrades gracefully instead of 500-ing.
    for crew_id, module_id in cfg.crew_placement:
        if crew_id in CREW_NAMES and module_id in modules:
            modules[module_id].crew.append(CrewMember(crew_id, CREW_NAMES[crew_id]))

    fire_module = modules.get(cfg.initial_fire_module)
    if fire_module is not None and cfg.initial_fire_severity > 0:
        fire_module.fire_severity = cfg.initial_fire_severity
        fire_module.ever_ignited = True

    connections = [
        Connection(source=a, target=b, hazard_spread_probability=cfg.connection_hazard_probability)
        for a, b in EDGES
    ]

    return Spacecraft(modules=modules, connections=connections)
