from pathlib import Path

import pytest

from spacecraft_sim.models import (
    Atmosphere,
    Connection,
    Crew,
    Equipment,
    Module,
    Scenario,
    System,
)

DEMO_PATH = Path(__file__).parent.parent / "examples" / "demo_spacecraft.json"


@pytest.fixture
def demo() -> Scenario:
    return Scenario.model_validate_json(DEMO_PATH.read_text(encoding="utf-8"))


def make_module(mid: str, **kwargs) -> Module:
    defaults = dict(id=mid, name=mid, atmosphere=Atmosphere(), volume_m3=70.0)
    defaults.update(kwargs)
    return Module(**defaults)


def make_line_scenario(
    n_modules: int = 3,
    fire_in: str | None = None,
    profile: str = "STEADY_FABRIC_SPREAD",
    connection_type: str = "hatch",
    path_state: str = "open",
    ventilation: str = "off",
    flow_m3_s: float | None = 0.0708,
    volume_m3: float = 70.0,
) -> Scenario:
    """A linear chain A1-A2-...-An — proves the engine has no fixed-size or
    fixed-id assumptions."""
    modules = [make_module(f"A{i + 1}", volume_m3=volume_m3) for i in range(n_modules)]
    if fire_in:
        module = next(m for m in modules if m.id == fire_in)
        module.fire_state = "sustained"
        module.source_profile_id = profile
    connections = [
        Connection(
            id=f"c{i}",
            source=f"A{i + 1}",
            target=f"A{i + 2}",
            type=connection_type,
            path_state=path_state,
            ventilation_state=ventilation,
            airflow_direction="source_to_target" if connection_type == "imv" else "none",
            flow_m3_s=flow_m3_s,
        )
        for i in range(n_modules - 1)
    ]
    return Scenario(modules=modules, connections=connections)


def add_crew(scenario: Scenario, crew_id: str, role: str, module_id: str) -> Crew:
    crew = Crew(id=crew_id, name=crew_id, role=role, module_id=module_id)
    scenario.crew.append(crew)
    scenario.module(module_id).crew_ids.append(crew_id)
    return crew


def add_system(
    scenario: Scenario, system_id: str, module_id: str, equipment_id: str | None = None
) -> System:
    dep_equipment = []
    if equipment_id:
        scenario.equipment.append(
            Equipment(
                id=equipment_id, name=equipment_id, module_id=module_id, system=system_id
            )
        )
        scenario.module(module_id).equipment_ids.append(equipment_id)
        dep_equipment = [equipment_id]
    system = System(
        id=system_id,
        name=system_id,
        depends_on_modules=[module_id],
        depends_on_equipment=dep_equipment,
    )
    scenario.systems.append(system)
    return system
