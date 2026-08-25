"""Extensions added for external scenario builders (Phase B bridge):
explicit crew function lists, bidirectional IMV loops, crew positions in the
timeline, and the all-crew-safe Monte Carlo count."""

from spacecraft_sim.capability import available_providers, evaluate_systems
from spacecraft_sim.crew import critical_functions, functions_of
from spacecraft_sim.engine import simulate
from spacecraft_sim.hazard import step_hazard
from spacecraft_sim.montecarlo import run_montecarlo
from spacecraft_sim.actions import find_action
from tests.conftest import add_crew, add_system, make_line_scenario


def test_provides_functions_overrides_role_lookup():
    scenario = make_line_scenario(n_modules=2)
    crew = add_crew(scenario, "X1", "Mission Specialist", "A1")  # unknown role
    assert functions_of(crew) == set()

    crew.provides_functions = ["power_ops", "docking"]
    assert functions_of(crew) == {"power_ops", "docking"}

    # Providers, criticality flags, and operator checks all honour the list.
    assert [c.id for c in available_providers(scenario, "power_ops")] == ["X1"]
    flagged = {f["function"] for f in critical_functions(scenario.crew, [])}
    assert "docking" in flagged  # single provider of a declared function

    system = add_system(scenario, "power", "A2", equipment_id="eq1")
    system.operator_function = "power_ops"
    assert evaluate_systems(scenario)["power"] == "OPERATIONAL"


def test_imv_circulation_loop_exchanges_both_ways():
    scenario = make_line_scenario(
        n_modules=2, fire_in="A1", connection_type="imv", ventilation="on"
    )
    scenario.connections[0].airflow_direction = "none"  # circulation loop
    for step_i in range(20):
        step_hazard(scenario, step_i * 30.0, 30.0)
    assert scenario.module("A2").concentration("soot") > 0


def test_timeline_records_crew_positions():
    scenario = make_line_scenario(n_modules=2, fire_in="A1")
    add_crew(scenario, "C1", "engineer", "A1")
    result = simulate(scenario, horizon=300, dt=30)
    assert result.timeline[0]["crew_modules"] == {"C1": "A1"}


def test_montecarlo_counts_all_crew_safe(demo):
    action = find_action(demo, "isolate:M2")
    dist = run_montecarlo(demo, action, n=10, seed=3, horizon=600, dt=60)
    assert 0 <= dist.all_crew_safe_or_evacuated <= 10
    assert dist.all_crew_safe_or_evacuated <= dist.no_crew_trapped
