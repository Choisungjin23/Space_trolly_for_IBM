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
    EscapeTargetIn,
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
    assert len(pa.crew) == 10
    assert len(pa.equipment) == 11

    fire = pa.module("mod-habitat")
    assert fire.fire_state == "sustained"
    assert fire.detected is True  # emergency.detected -> alarm already sounded

    engineer = pa.crew_member("crew-engineer")
    assert set(engineer.provides_functions) == {"life_support_ops", "repair", "power_ops"}


def test_translation_carries_directional_escape_target(demo):
    scenario, emergency = demo
    emergency.escapeTarget = EscapeTargetIn(
        connectionId="conn-storage2-ls2",
        fromModuleId="mod-storage-2",
        toModuleId="mod-life-support-2",
        selection="recommended",
        maxOccupants=9,
    )
    pa = to_phase_a_scenario(scenario, emergency)
    assert pa.escape_target_connection_id == "conn-storage2-ls2"
    assert pa.escape_from_module_id == "mod-storage-2"
    assert pa.escape_target_module_id == "mod-life-support-2"
    assert pa.escape_capacity_people == 9


def test_transfer_class_scales_connection_flow(demo):
    scenario, emergency = demo
    pa = to_phase_a_scenario(scenario, emergency)
    # The former Storage/Life Support ventilation link is now an ordinary hatch.
    ordinary_hatch = pa.connection("conn-stor-ls")
    hatch_medium = pa.connection("conn-ls-pwr")  # hatch, medium
    assert ordinary_hatch.type == "hatch"
    assert ordinary_hatch.nominal_flow_m3_s() == pytest.approx(0.010)
    assert hatch_medium.nominal_flow_m3_s() == pytest.approx(0.010 * 0.66)


def test_failed_equipment_translates_to_damaged():
    scenario, emergency = make_two_module()
    scenario.modules["alpha"].equipment[0].state = "explicitly_failed"
    pa = to_phase_a_scenario(scenario, emergency)
    assert pa.equipment[0].damaged is True


def test_fire_rolls_adjacent_connectivity_between_one_and_fifty():
    scenario, emergency = make_two_module()
    pa = to_phase_a_scenario(scenario, emergency)
    assert 1 <= pa.connection("c1").connectivity <= 50


def test_electronic_short_reduces_power_passage_without_starting_fire():
    scenario, _ = make_two_module()
    emergency = EmergencyConfigIn(
        type="electronic_short", affectedModuleId="alpha", detected=True
    )
    pa = to_phase_a_scenario(scenario, emergency)
    assert pa.module("alpha").electrical_short is True
    assert pa.module("alpha").fire_state == "non"
    assert 0.05 <= pa.connection("c1").power_transfer_factor <= 0.20
    assert "shutdown_power_line_c1" in {
        action.id for action in generate_actions(scenario, emergency)
    }
    response = simulate(scenario, emergency, ["do_nothing"], runs=1, seed=42)
    outcome = response.results[0].connectivity.byConnectionId["c1"]
    assert outcome.powerTransferPercent <= 20


# ── Action mapping ──────────────────────────────────────────────────────────

def test_actions_use_phase_b_id_vocabulary(demo):
    scenario, emergency = demo
    ids = {a.id for a in generate_actions(scenario, emergency)}
    assert "do_nothing" in ids
    assert "isolate_module_mod-habitat" in ids
    assert "close_conn_conn-hab-stor" in ids
    assert "shutdown_vent_conn-hab-ls" in ids
    # No raw Phase A ids leak through.
    assert not any(":" in action_id for action_id in ids)


def test_operations_stay_within_frontend_enum(demo):
    scenario, emergency = demo
    allowed = {
        "close_connection",
        "isolate_module",
            "shutdown_ventilation",
            "shutdown_power_line",
            "shutdown_air_line",
            "shutdown_water_line",
            "abandon_module",
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
        scenario, emergency, ["do_nothing", "isolate_module_mod-habitat"], RUNS, SEED
    )
    by_id = {r.actionId: r for r in response.results}

    spread = by_id["do_nothing"].hazard.modulesReachedIds
    contained = by_id["isolate_module_mod-habitat"].hazard.modulesReachedIds
    assert set(contained).issubset(spread)
    assert contained == []


def test_capabilities_track_hazard_reach(demo):
    # Redundant habitation remains available because Life Support stays clean
    # even while the Habitat provider is exposed.
    scenario, emergency = demo
    response = simulate(
        scenario, emergency, ["do_nothing", "isolate_module_mod-habitat"], RUNS, SEED
    )
    by_id = {r.actionId: r.capabilities.byCapability for r in response.results}
    assert by_id["do_nothing"]["habitation"] == "available"
    assert by_id["isolate_module_mod-habitat"]["habitation"] == "available"
    # These capabilities now come from enabled source modules rather than
    # equipment capability tags.
    assert by_id["isolate_module_mod-habitat"]["oxygen_supply"] == "available"
    assert by_id["isolate_module_mod-habitat"]["electrical_power"] == "available"


def test_critical_functions_derive_from_declared_lists(demo):
    scenario, emergency = demo
    response = simulate(scenario, emergency, ["do_nothing"], RUNS, SEED)
    functions = response.results[0].criticalFunctions.byFunction
    # Only Engineer Park declares life_support_ops in the demo fixture.
    assert functions["life_support_ops"].totalProviders == 1
    # navigation is declared by commander, pilot and return specialist.
    assert functions["navigation"].totalProviders == 3


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


# ── Systems and mission capabilities ────────────────────────────────────────
#
# Phase B used to hand the engine `systems=[]` and `capabilities={}` and judge
# capability itself, which left the engine's whole systems layer inert: the
# Systems and Mission agents received empty dictionaries, and because the
# engine defaults an undeclared RETURN to AVAILABLE, expected_returnees was
# always identical to expected_survivors. These lock that in.

def test_equipment_tags_become_redundant_phase_a_systems(demo):
    scenario, emergency = demo
    pa_scenario = to_phase_a_scenario(scenario, emergency)

    assert pa_scenario.systems, "the engine must receive systems, not an empty list"
    by_id = {system.id: system for system in pa_scenario.systems}
    # Interchangeable providers, so one lost unit does not lose the capability.
    assert by_id["habitation"].redundancy == "any"
    assert len(by_id["habitation"].depends_on_equipment) == 3
    # Source capabilities rest on their modules, not on a box inside one.
    assert by_id["oxygen_supply"].depends_on_modules
    assert not by_id["oxygen_supply"].depends_on_equipment


def test_mission_capabilities_are_declared_for_the_engine(demo):
    scenario, emergency = demo
    pa_scenario = to_phase_a_scenario(scenario, emergency)

    # The engine and the Monte Carlo read these two names.
    assert "RETURN" in pa_scenario.capabilities
    assert "HABITATION" in pa_scenario.capabilities
    # Composed conjunctively from systems that actually exist.
    assert set(pa_scenario.capabilities["RETURN"]) <= {
        system.id for system in pa_scenario.systems
    }


def test_operator_function_only_when_the_crew_can_provide_it(demo):
    scenario, emergency = demo
    by_id = {s.id: s for s in to_phase_a_scenario(scenario, emergency).systems}
    # The demo crew declares propulsion_ops, so the coupling applies.
    assert by_id["main_propulsion"].operator_function == "propulsion_ops"

    # Strip every declared function: no system may then demand an operator,
    # or it would be UNAVAILABLE from the first step for want of a person who
    # was never in this scenario.
    stripped = scenario.model_copy(deep=True)
    for module in stripped.modules.values():
        for crew_member in module.crew:
            crew_member.providesFunctions = []
            crew_member.role = "unlisted-role"
    for system in to_phase_a_scenario(stripped, emergency).systems:
        assert system.operator_function is None


def test_systems_reach_the_results_and_are_not_empty(demo):
    scenario, emergency = demo
    response = simulate(scenario, emergency, ["do_nothing"], RUNS, SEED)
    capabilities = response.results[0].capabilities.byCapability
    # Mission rollups now sit alongside the per-system capabilities.
    assert capabilities["RETURN"] in {"available", "degraded", "unavailable"}
    assert capabilities["HABITATION"] in {"available", "degraded", "unavailable"}


def test_losing_return_separates_returnees_from_survivors(demo):
    """The coordinator's first objective only means something when the two
    can differ. Closing the habitat hatch saves the most lives in this demo
    and strands them, which is exactly the trade-off worth surfacing."""
    scenario, emergency = demo
    response = simulate(
        scenario, emergency, ["do_nothing", "close_conn_conn-hab-stor"], RUNS, SEED
    )
    by_id = {r.actionId: r for r in response.results}

    baseline = by_id["do_nothing"]
    assert baseline.capabilities.byCapability["RETURN"] == "available"
    assert baseline.expectedReturnees == pytest.approx(baseline.expectedSurvivors)

    stranded = by_id["close_conn_conn-hab-stor"]
    assert stranded.capabilities.byCapability["RETURN"] == "unavailable"
    assert stranded.expectedReturnees == 0.0
    # More people alive, none of them able to come home.
    assert stranded.expectedSurvivors > baseline.expectedSurvivors


def test_automated_systems_do_not_need_an_operator(demo):
    """Life support and power run themselves; manoeuvring needs a person.

    Without this split, isolating the central module traps every crew member
    and the spacecraft instantly loses oxygen and electrical power on paper,
    which describes the coupling table rather than the emergency.
    """
    scenario, emergency = demo
    by_id = {s.id: s for s in to_phase_a_scenario(scenario, emergency).systems}

    for automated in ("habitation", "co2_removal", "oxygen_supply", "electrical_power"):
        assert by_id[automated].operator_function is None, automated
    for crewed in ("main_propulsion", "navigation", "return_capability"):
        assert by_id[crewed].operator_function is not None, crewed


def test_trapped_crew_lose_return_but_keep_a_habitable_ship(demo):
    """The trade-off the coordinator exists to weigh: sealing the hatch keeps
    the most people alive and the ship habitable, and strands all of them."""
    scenario, emergency = demo
    response = simulate(
        scenario, emergency, ["do_nothing", "close_conn_conn-hab-stor"], RUNS, SEED
    )
    sealed = next(r for r in response.results if r.actionId == "close_conn_conn-hab-stor")
    assert sealed.capabilities.byCapability["RETURN"] == "unavailable"
    assert sealed.capabilities.byCapability["HABITATION"] == "available"
