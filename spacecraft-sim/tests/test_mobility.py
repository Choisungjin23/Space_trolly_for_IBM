import pytest

from spacecraft_sim import config
from spacecraft_sim.crew import rank_crew_for_evacuation, update_crew
from spacecraft_sim.mobility import consume_passage, update_connectivity
from spacecraft_sim.models import Crew
from tests.conftest import make_line_scenario


@pytest.mark.parametrize(
    ("connectivity", "crew_per_min", "air_percent_per_min"),
    [(100, 4, 10), (49, 1.96, 4.9), (25, 1, 2.5)],
)
def test_connectivity_controls_crew_and_air_throughput(
    connectivity, crew_per_min, air_percent_per_min
):
    scenario = make_line_scenario(n_modules=2)
    connection = scenario.connection("c0")
    connection.connectivity = connectivity
    assert connection.crew_throughput_per_min == pytest.approx(crew_per_min)
    assert connection.air_throughput_percent_per_min == pytest.approx(
        air_percent_per_min
    )


def test_disaster_and_passage_create_persistent_negative_feedback():
    scenario = make_line_scenario(n_modules=2, fire_in="A1")
    connection = scenario.connection("c0")
    update_connectivity(scenario, 60)
    after_fire = connection.connectivity
    assert after_fire == pytest.approx(99)

    connection.crew_passage_credit = 1
    destination_o2 = scenario.module("A2").atmosphere.o2
    assert consume_passage(scenario, connection, "A2") is True
    assert connection.connectivity < after_fire
    assert scenario.module("A2").atmosphere.o2 < destination_o2


def test_low_air_caps_connectivity_even_without_new_passage():
    scenario = make_line_scenario(n_modules=2)
    scenario.module("A1").atmosphere.o2 = 0.125
    update_connectivity(scenario, 60)
    assert scenario.connection("c0").connectivity == pytest.approx(50)


def test_higher_priority_crew_consumes_the_only_passage_slot_first():
    scenario = make_line_scenario(n_modules=2, fire_in="A1")
    connection = scenario.connection("c0")
    connection.connectivity = 25
    scenario.crew = [
        Crew(id="ordinary", name="Ordinary", role="scientist", module_id="A1"),
        Crew(
            id="critical",
            name="Critical",
            role="engineer",
            provides_functions=["life_support_ops", "repair"],
            module_id="A1",
        ),
    ]
    scenario.module("A1").crew_ids = ["ordinary", "critical"]
    for crew in scenario.crew:
        crew.state = "EVACUATING"
        crew.route = ["A2"]
        crew.hop_eta_seconds = 0

    rank_crew_for_evacuation(scenario)
    update_crew(scenario, t=60, dt=60, response_seconds=0)

    assert scenario.crew_member("critical").module_id == "A2"
    assert scenario.crew_member("ordinary").module_id == "A1"
    assert scenario.crew_member("ordinary").waiting_for_connection_id == "c0"


def test_collapsed_connectivity_permanently_blocks_new_crew_passage():
    scenario = make_line_scenario(n_modules=2)
    connection = scenario.connection("c0")
    connection.connectivity = config.ASSUMED_HATCH_IMPASSABLE_CONNECTIVITY
    crew = Crew(id="blocked", name="Blocked", role="crew", module_id="A1")
    scenario.crew = [crew]
    scenario.module("A1").crew_ids = [crew.id]
    crew.state = "EVACUATING"
    crew.route = ["A2"]
    crew.hop_eta_seconds = 0

    for minute in range(60):
        update_crew(scenario, t=minute * 60, dt=60, response_seconds=0)

    assert crew.module_id == "A1"
    assert crew.state == "TRAPPED"
    assert connection.crew_passage_credit == 0
