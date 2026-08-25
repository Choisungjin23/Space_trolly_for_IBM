"""Tests for PhaseASimulatorAdapter — the bridge from Phase B's API contract
to the real spacecraft_sim engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.phase_a_simulator import (
    SOURCE_LABEL,
    generate_actions,
    simulate,
    to_phase_a_scenario,
)
from app.api.schemas import (
    ConnectionIn,
    CrewMemberIn,
    EmergencyConfigIn,
    EquipmentIn,
    ModuleIn,
    ScenarioIn,
)

FIXTURES_DIR = Path(__file__).parent.parent / "app" / "fixtures"

RUNS = 20
SEED = 42


@pytest.fixture
def demo() -> tuple[ScenarioIn, EmergencyConfigIn]:
    fixture = json.loads((FIXTURES_DIR / "five_module_demo.json").read_text("utf-8"))
    emergency = EmergencyConfigIn(**fixture["emergency"])
    return ScenarioIn(**fixture), emergency


def make_two_module(affected: str = "alpha") -> tuple[ScenarioIn, EmergencyConfigIn]:
    scenario = ScenarioIn(
        name="Bridge test",
        modules={
            "alpha": ModuleIn(
                id="alpha",
                name="Alpha",
                type="habitat",
                crew=[
                    CrewMemberIn(
                        id="c-eng",
                        name="Engineer",
                        role="Flight Engineer",
                        providesFunctions=["repair", "power_ops"],
                    )
                ],
                equipment=[
                    EquipmentIn(
                        id="eq-a",
                        name="Radio",
                        type="comms",
                        state="operational",
                        providesCapabilities=["communications"],
                    )
                ],
            ),
            "beta": ModuleIn(id="beta", name="Beta", type="storage"),
        },
        connections={
            "c1": ConnectionIn(
                id="c1",
                source="alpha",
                target="beta",
                type="hatch",
                state="open",
                flowDirection="bidirectional",
                transferClass="medium",
            )
        },
    )
    emergency = EmergencyConfigIn(affectedModuleId=affected, detected=True)
    return scenario, emergency


# ── Translation ─────────────────────────────────────────────────────────────

def test_translation_carries_graph_crew_and_equipment(demo):
    scenario, emergency = demo
    pa = to_phase_a_scenario(scenario, emergency)

    assert {m.id for m in pa.modules} == set(scenario.modules)
    assert {c.id for c in pa.connections} == set(scenario.connections)
    assert len(pa.crew) == 4
    assert len(pa.equipment) == 11

    fire = pa.module("mod-storage")
    assert fire.fire_state == "sustained"
    assert fire.detected is True  # emergency.detected -> alarm already sounded

    engineer = pa.crew_member("crew-engineer")
    assert set(engineer.provides_functions) == {"life_support_ops", "repair", "power_ops"}


def test_transfer_class_scales_connection_flow(demo):
    scenario, emergency = demo
    pa = to_phase_a_scenario(scenario, emergency)
    # Demo: conn-stor-ls is an IMV with transferClass=high -> full IMV flow.
    imv = pa.connection("conn-stor-ls")
    hatch_medium = pa.connection("conn-ls-pwr")  # hatch, medium
    assert imv.nominal_flow_m3_s() == pytest.approx(0.0708)
    assert hatch_medium.nominal_flow_m3_s() == pytest.approx(0.010 * 0.66)


def test_failed_equipment_translates_to_damaged():
    scenario, emergency = make_two_module()
    scenario.modules["alpha"].equipment[0].state = "explicitly_failed"
    pa = to_phase_a_scenario(scenario, emergency)
    assert pa.equipment[0].damaged is True


# ── Action mapping ──────────────────────────────────────────────────────────

def test_actions_use_phase_b_id_vocabulary(demo):
    scenario, emergency = demo
    ids = {a.id for a in generate_actions(scenario, emergency)}
    assert "do_nothing" in ids
    assert "isolate_module_mod-storage" in ids
    assert "close_conn_conn-hab-stor" in ids
    assert "shutdown_vent_conn-stor-ls" in ids
    # No raw Phase A ids leak through.
    assert not any(":" in action_id for action_id in ids)


def test_operations_stay_within_frontend_enum(demo):
    scenario, emergency = demo
    allowed = {
        "close_connection",
        "isolate_module",
        "shutdown_ventilation",
        "evacuate_crew",
        "power_down_equipment",
        "do_nothing",
    }
    for action in generate_actions(scenario, emergency):
        for operation in action.operations:
            assert operation.type in allowed


# ── Simulation results ──────────────────────────────────────────────────────

def test_simulate_produces_engine_backed_results(demo):
    scenario, emergency = demo
    response = simulate(scenario, emergency, None, RUNS, SEED)

    assert response.sourceLabel == SOURCE_LABEL
    assert response.simulatedHorizonSeconds == 3600
    assert len(response.results) == len(response.generatedActions)

    for result in response.results:
        assert 0 <= result.hazard.containedInNScenarios <= RUNS
        assert 0 <= result.crew.anyTrappedCount <= RUNS
        assert result.crew.totalScenarios == RUNS
        assert result.exampleTrajectory is not None
        assert len(result.exampleTrajectory.steps) > 1


def test_isolation_contains_and_do_nothing_spreads(demo):
    scenario, emergency = demo
    response = simulate(
        scenario, emergency, ["do_nothing", "isolate_module_mod-storage"], RUNS, SEED
    )
    by_id = {r.actionId: r for r in response.results}

    spread = by_id["do_nothing"].hazard.modulesReachedIds
    contained = by_id["isolate_module_mod-storage"].hazard.modulesReachedIds
    assert len(contained) < len(spread)
    assert contained == ["mod-storage"]


def test_capabilities_track_hazard_reach(demo):
    # "habitation" is provided by equipment in Habitat and Life Support. Under
    # do_nothing the smoke reaches both, so every provider is exposed ->
    # degraded; isolating the fire keeps the providers clean -> available.
    scenario, emergency = demo
    response = simulate(
        scenario, emergency, ["do_nothing", "isolate_module_mod-storage"], RUNS, SEED
    )
    by_id = {r.actionId: r.capabilities.byCapability for r in response.results}
    assert by_id["do_nothing"]["habitation"] == "degraded"
    assert by_id["isolate_module_mod-storage"]["habitation"] == "available"


def test_critical_functions_derive_from_declared_lists(demo):
    scenario, emergency = demo
    response = simulate(scenario, emergency, ["do_nothing"], RUNS, SEED)
    functions = response.results[0].criticalFunctions.byFunction
    # Only Engineer Park declares life_support_ops in the demo fixture.
    assert functions["life_support_ops"].totalProviders == 1
    # navigation is declared by two crew members (commander + pilot).
    assert functions["navigation"].totalProviders == 2


def test_trajectory_reports_real_detection_event():
    scenario, emergency = make_two_module()
    emergency = EmergencyConfigIn(affectedModuleId="alpha", detected=False)
    response = simulate(scenario, emergency, ["do_nothing"], 5, SEED)
    events = [
        e for step in response.results[0].exampleTrajectory.steps for e in step.events
    ]
    assert any("Smoke alarm confirmed" in e for e in events)


def test_unknown_action_id_raises_value_error(demo):
    scenario, emergency = demo
    with pytest.raises(ValueError, match="Unknown action"):
        simulate(scenario, emergency, ["not-real"], RUNS, SEED)


def test_seeded_runs_reproduce(demo):
    scenario, emergency = demo
    a = simulate(scenario, emergency, ["do_nothing"], RUNS, 7)
    b = simulate(scenario, emergency, ["do_nothing"], RUNS, 7)
    assert a.results[0].hazard == b.results[0].hazard
    assert a.results[0].crew == b.results[0].crew


def test_no_banned_vocabulary_in_response(demo):
    scenario, emergency = demo
    text = simulate(scenario, emergency, None, RUNS, SEED).model_dump_json().lower()
    assert "hazard_spread_probability" not in text
    assert "propagation_factor" not in text
    assert "best action" not in text
