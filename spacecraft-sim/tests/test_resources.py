import pytest

from spacecraft_sim.models import Connection, Crew, Equipment, Module, Scenario
from spacecraft_sim.resources import update_resources


def _chain() -> Scenario:
    modules = [
        Module(id="P", name="Power", type="power", power_level_w=100, max_power_output_w=200),
        Module(id="A", name="A", water_stored_kg=1, water_capacity_kg=1),
        Module(id="B", name="B", water_stored_kg=1, water_capacity_kg=1),
    ]
    connections = [
        Connection(id="c1", source="P", target="A", type="hatch"),
        Connection(id="c2", source="A", target="B", type="hatch"),
    ]
    return Scenario(modules=modules, connections=connections)


def test_power_level_drops_one_watt_per_hop():
    scenario = _chain()
    update_resources(scenario, 60)
    assert scenario.module("A").power_level_w == pytest.approx(99)
    assert scenario.module("B").power_level_w == pytest.approx(98)
    assert scenario.connection("c1").power_flow_direction == "source_to_target"


def test_power_capacity_is_split_equally_then_compared_with_each_demand():
    source = Module(
        id="P", name="Power", type="power", power_level_w=100,
        max_power_output_w=60,
    )
    a = Module(id="A", name="A", power_consumption_w=25)
    b = Module(id="B", name="B", power_consumption_w=35)
    scenario = Scenario(
        modules=[source, a, b],
        connections=[
            Connection(id="a", source="P", target="A", type="hatch"),
            Connection(id="b", source="P", target="B", type="hatch"),
        ],
    )
    update_resources(scenario, 60)
    assert a.power_level_w == pytest.approx(30)
    assert b.power_level_w == pytest.approx(30)
    assert a.power_sufficient is True
    assert b.power_sufficient is False


def test_water_refills_only_consumed_amount_and_recovers_98_percent():
    source = Module(
        id="LS",
        name="Life Support",
        type="life_support",
        supplies_water=True,
        max_water_output_kg_per_min=1,
        water_stored_kg=100,
        water_capacity_kg=100,
    )
    habitat = Module(id="H", name="Habitat", water_stored_kg=1, water_capacity_kg=1)
    crew = Crew(id="C1", name="C1", role="crew", module_id="H")
    scenario = Scenario(
        modules=[source, habitat],
        connections=[Connection(id="w", source="LS", target="H", type="hatch")],
        crew=[crew],
    )
    update_resources(scenario, 60)
    assert habitat.water_demand_kg_per_min == pytest.approx(0.00264)
    assert habitat.water_stored_kg == pytest.approx(1.0)
    assert habitat.water_received_kg_last_step == pytest.approx(0.00264)
    # 2% unrecovered crew water plus 0.00001 kg one-hop transfer loss.
    assert source.water_stored_kg == pytest.approx(100 - 0.00264 * 0.02 - 0.00001)


def test_closed_hatch_blocks_air_but_not_power_or_water_lines():
    scenario = _chain()
    scenario.connection("c1").path_state = "closed"
    update_resources(scenario, 60)
    assert scenario.module("A").power_level_w == pytest.approx(99)
    assert scenario.connection("c1").air_supply_direction == "none"
    assert scenario.connection("c1").power_flow_direction == "source_to_target"


def test_air_source_maintains_25_percent_and_drops_half_point_per_hop():
    source = Module(
        id="LS",
        name="Life Support",
        type="life_support",
        supplies_air=True,
        max_air_output_fraction_per_min=1,
    )
    a = Module(id="A", name="A")
    b = Module(id="B", name="B")
    scenario = Scenario(
        modules=[source, a, b],
        connections=[
            Connection(id="a", source="LS", target="A", type="hatch"),
            Connection(id="b", source="A", target="B", type="hatch"),
        ],
    )
    update_resources(scenario, 60)
    assert source.atmosphere.o2 == pytest.approx(0.25)
    assert a.atmosphere.o2 == pytest.approx(0.245)
    assert b.atmosphere.o2 == pytest.approx(0.24)


def test_low_oxygen_reduces_modeled_survival_probability():
    module = Module(id="H", name="H")
    module.atmosphere.o2 = 0.08
    crew = Crew(id="C", name="C", role="crew", module_id="H")
    scenario = Scenario(modules=[module], connections=[], crew=[crew])
    update_resources(scenario, 60)
    assert 0 < crew.survival_probability < 1


def test_equipment_and_enabled_life_support_outputs_add_power_load():
    module = Module(
        id="LS",
        name="Life Support",
        type="life_support",
        power_consumption_w=10,
        supplies_air=True,
        supplies_water=True,
    )
    equipment = Equipment(
        id="scrubber",
        name="Scrubber",
        module_id="LS",
        system="co2_removal",
        power_consumption_w=12,
    )
    scenario = Scenario(modules=[module], connections=[], equipment=[equipment])
    update_resources(scenario, 60)
    assert module.power_consumption_w == pytest.approx(10 + 12 + 25 + 20)
    assert module.power_sufficient is False


def test_electronic_short_power_passage_factor_limits_delivery():
    source = Module(
        id="P", name="Power", type="power", power_level_w=100,
        max_power_output_w=100,
    )
    consumer = Module(id="C", name="Consumer", power_consumption_w=20)
    scenario = Scenario(
        modules=[source, consumer],
        connections=[Connection(
            id="shorted", source="P", target="C", type="hatch",
            power_transfer_factor=0.1,
        )],
    )
    update_resources(scenario, 60)
    assert consumer.power_level_w == pytest.approx(10)
    assert consumer.power_sufficient is False


def test_backup_power_source_keeps_its_own_bus_setpoint():
    main = Module(
        id="MAIN", name="Main", type="power", power_level_w=200,
        max_power_output_w=200,
    )
    backup = Module(
        id="BACKUP", name="Backup", type="power", power_level_w=85,
        max_power_output_w=85,
    )
    refuge = Module(id="R", name="Refuge", power_consumption_w=50)
    scenario = Scenario(
        modules=[main, backup, refuge],
        connections=[
            Connection(id="main-backup", source="MAIN", target="BACKUP", type="hatch"),
            Connection(id="backup-refuge", source="BACKUP", target="R", type="hatch"),
        ],
    )
    update_resources(scenario, 60)
    assert backup.power_level_w == pytest.approx(85)


def test_survival_model_combines_power_water_and_extreme_fire():
    module = Module(
        id="H", name="Hazard", fire_state="sustained",
        power_level_w=0, power_consumption_w=10,
        water_stored_kg=0, water_capacity_kg=0,
    )
    crew = Crew(id="C", name="C", role="crew", module_id="H")
    scenario = Scenario(modules=[module], connections=[], crew=[crew])
    update_resources(scenario, 60 * 60)
    assert crew.survival_probability < 0.001
    assert crew.estimated_survival_minutes == 0
    assert set(crew.resource_risk_reasons) >= {
        "insufficient_power", "insufficient_water", "sustained_fire_exposure"
    }


def test_refuge_capacity_denial_drives_survival_probability_near_zero():
    module = Module(id="S", name="Staging", water_stored_kg=1, water_capacity_kg=1)
    crew = Crew(
        id="C", name="C", role="passenger", module_id="S",
        escape_capacity_denied=True,
    )
    scenario = Scenario(modules=[module], connections=[], crew=[crew])
    update_resources(scenario, 30 * 60)
    assert crew.survival_probability < 0.01
    assert "refuge_capacity_exceeded" in crew.resource_risk_reasons
