"""Domain models: the spacecraft represented as a graph of modules and connections."""

from dataclasses import dataclass, field


@dataclass
class CrewMember:
    id: str
    name: str
    alive: bool = True


@dataclass
class Module:
    """A graph node. `failed_systems` and `ever_ignited` are per-run tracking state."""

    id: str
    name: str
    fire_severity: float = 0.0  # 0.0 (no fire) .. 1.0 (fully ablaze)
    isolated: bool = False  # isolated: fire cannot spread in or out, crew cannot evacuate
    crew: list[CrewMember] = field(default_factory=list)
    systems: list[str] = field(default_factory=list)
    failed_systems: list[str] = field(default_factory=list)
    ever_ignited: bool = False


@dataclass
class Connection:
    """A graph edge, undirected for fire-spread purposes (checked in both directions)."""

    source: str
    target: str
    hazard_spread_probability: float
    active: bool = True  # False = hatch closed, no spread and no evacuation across it


@dataclass
class Spacecraft:
    modules: dict[str, Module]
    connections: list[Connection]

    def neighbors(self, module_id: str) -> list[str]:
        """Module ids reachable through active connections, in connection-list order."""
        out: list[str] = []
        for conn in self.connections:
            if not conn.active:
                continue
            if conn.source == module_id:
                out.append(conn.target)
            elif conn.target == module_id:
                out.append(conn.source)
        return out

    def all_crew(self) -> list[CrewMember]:
        return [c for m in self.modules.values() for c in m.crew]
