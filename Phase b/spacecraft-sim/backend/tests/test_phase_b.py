"""
Backend tests for Phase B.

Tests verify:
- Arbitrary module IDs work (no M1/M2 dependency)
- 2-module scenario works end-to-end
- Demo fixture loads and passes through the same code path
- SimulationResponse shape is valid
- No hazard_spread_probability in responses
- Action IDs are derived from graph, not hard-coded
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.adapters.phase_a_simulator import generate_actions, simulate
from app.api.schemas import (
    ConnectionIn,
    EmergencyConfigIn,
    EquipmentIn,
    ModuleIn,
    ScenarioIn,
)


client = TestClient(app)

FIXTURES_DIR = Path(__file__).parent.parent / "app" / "fixtures"


# ─── Helpers ────────────────────────────────────────────────────────────────

def make_minimal_scenario(affected_module_id: str = "alpha") -> tuple[ScenarioIn, EmergencyConfigIn]:
    """2-module scenario with arbitrary IDs."""
    scenario = ScenarioIn(
        name="Test Scenario",
        modules={
            "alpha": ModuleIn(id="alpha", name="Alpha Module", type="habitat"),
            "beta": ModuleIn(id="beta", name="Beta Module", type="storage"),
        },
        connections={
            "conn-ab": ConnectionIn(
                id="conn-ab",
                source="alpha",
                target="beta",
                type="hatch",
                state="open",
                ventilationOn=False,
                flowDirection="bidirectional",
                transferClass="medium",
            ),
        },
        emergency=EmergencyConfigIn(
            type="fire",
            affectedModuleId=affected_module_id,
            detected=True,
        ),
    )
    emergency = EmergencyConfigIn(
        type="fire",
        affectedModuleId=affected_module_id,
        detected=True,
    )
    return scenario, emergency


def make_large_scenario(n: int = 10) -> tuple[ScenarioIn, EmergencyConfigIn]:
    """N-module scenario with generated IDs."""
    modules = {}
    connections = {}
    for i in range(n):
        mid = f"mod-{i}"
        modules[mid] = ModuleIn(id=mid, name=f"Module {i}", type="other")
    # Connect in a chain
    for i in range(n - 1):
        cid = f"conn-{i}-{i+1}"
        connections[cid] = ConnectionIn(
            id=cid,
            source=f"mod-{i}",
            target=f"mod-{i+1}",
            type="hatch",
            state="open",
            ventilationOn=False,
            flowDirection="bidirectional",
            transferClass="medium",
        )
    scenario = ScenarioIn(
        name="Large Scenario",
        modules=modules,
        connections=connections,
    )
    emergency = EmergencyConfigIn(
        type="fire",
        affectedModuleId="mod-0",
        detected=True,
    )
    return scenario, emergency


# ─── Adapter unit tests ──────────────────────────────────────────────────────

def test_directional_escape_target_requires_an_independently_survivable_zone():
    fixture = json.loads((FIXTURES_DIR / "five_module_demo.json").read_text("utf-8"))
    fixture["emergency"]["escapeTarget"] = {
        "connectionId": "conn-storage2-ls2",
        "fromModuleId": "mod-storage-2",
        "toModuleId": "mod-life-support-2",
        "selection": "recommended",
    }
    scenario = ScenarioIn(**fixture)
    assert scenario.emergency.escapeTarget.toModuleId == "mod-life-support-2"

    fixture["emergency"]["escapeTarget"] = {
        "connectionId": "conn-hab-stor",
        "fromModuleId": "mod-storage",
        "toModuleId": "mod-habitat",
        "selection": "manual",
    }
    with pytest.raises(ValueError, match="entry side is not connected"):
        ScenarioIn(**fixture)


def test_equipment_power_defaults_by_type_and_source_capabilities_are_removed():
    equipment = EquipmentIn(
        id="eq",
        name="Generator",
        type="life_support",
        state="operational",
        providesCapabilities=["oxygen_supply", "electrical_power", "habitation"],
    )
    assert equipment.powerConsumptionW == 25
    assert equipment.providesCapabilities == ["habitation"]


# ─── API endpoint tests ──────────────────────────────────────────────────────

class TestTemplatesEndpoint:
    def test_list_templates_returns_list(self):
        response = client.get("/api/templates")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_template_has_required_fields(self):
        response = client.get("/api/templates")
        templates = response.json()
        for t in templates:
            assert "id" in t
            assert "name" in t
            assert "description" in t

    def test_get_demo_template(self):
        response = client.get("/api/templates/five-module-demo")
        assert response.status_code == 200
        data = response.json()
        assert "modules" in data
        assert "connections" in data
        assert len(data["modules"]) == 8

    def test_unknown_template_returns_404(self):
        response = client.get("/api/templates/does-not-exist")
        assert response.status_code == 404


class TestSimulateEndpoint:
    def _minimal_payload(self, affected: str = "alpha") -> dict:
        return {
            "scenario": {
                "name": "API Test Scenario",
                "modules": {
                    "alpha": {"id": "alpha", "name": "Alpha", "type": "habitat", "crew": [], "equipment": []},
                    "beta": {"id": "beta", "name": "Beta", "type": "storage", "crew": [], "equipment": []},
                },
                "connections": {
                    "c1": {
                        "id": "c1",
                        "source": "alpha",
                        "target": "beta",
                        "type": "hatch",
                        "state": "open",
                        "ventilationOn": False,
                        "flowDirection": "bidirectional",
                        "transferClass": "medium",
                    }
                },
            },
            "emergency": {
                "type": "fire",
                "affectedModuleId": affected,
                "detected": True,
            },
            "actions": None,
            "runs": 50,
            "seed": 42,
        }

    def test_simulate_user_scenario_returns_200(self):
        response = client.post("/api/simulate", json=self._minimal_payload())
        assert response.status_code == 200

    def test_simulate_returns_generated_actions(self):
        response = client.post("/api/simulate", json=self._minimal_payload())
        data = response.json()
        assert "generatedActions" in data
        assert len(data["generatedActions"]) > 0

    def test_simulate_returns_results_per_action(self):
        response = client.post("/api/simulate", json=self._minimal_payload())
        data = response.json()
        assert "results" in data
        assert len(data["results"]) > 0
        for r in data["results"]:
            assert "actionId" in r
            assert "hazard" in r
            assert "crew" in r

    def test_simulate_source_label_is_phase_a(self):
        """The API now runs the real Phase A engine, and says so."""
        response = client.post("/api/simulate", json=self._minimal_payload())
        data = response.json()
        assert "PhaseASimulatorAdapter" in data["sourceLabel"]
        assert "Mock" not in data["sourceLabel"]

    def test_demo_fixture_uses_same_path(self):
        """Demo fixture must go through the same /api/simulate endpoint as user scenarios."""
        fixture_path = FIXTURES_DIR / "five_module_demo.json"
        fixture = json.loads(fixture_path.read_text())
        # Extract emergency from fixture
        emergency = fixture.pop("emergency", {
            "type": "fire",
            "affectedModuleId": "mod-storage",
            "detected": True,
        })
        payload = {
            "scenario": fixture,
            "emergency": emergency,
            "actions": None,
            "runs": 50,
            "seed": 42,
        }
        response = client.post("/api/simulate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) > 0

    def test_action_ids_do_not_contain_m1_m2(self):
        response = client.post("/api/simulate", json=self._minimal_payload())
        data = response.json()
        for action in data["generatedActions"]:
            assert "m1" not in action["id"].lower()
            assert "m2" not in action["id"].lower()

    def test_no_hazard_spread_probability_in_response(self):
        response = client.post("/api/simulate", json=self._minimal_payload())
        text = response.text
        assert "hazard_spread_probability" not in text

    def test_no_best_action_in_response(self):
        response = client.post("/api/simulate", json=self._minimal_payload())
        text = response.text.lower()
        assert "best action" not in text

    def test_health_check(self):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_invalid_emergency_type_returns_422(self):
        payload = self._minimal_payload()
        payload["emergency"]["type"] = "radiation"

        response = client.post("/api/simulate", json=payload)

        assert response.status_code == 422

    def test_missing_emergency_module_returns_422(self):
        response = client.post(
            "/api/simulate",
            json=self._minimal_payload(affected="missing-module"),
        )

        assert response.status_code == 422

    def test_module_dictionary_key_must_match_id(self):
        payload = self._minimal_payload()
        payload["scenario"]["modules"]["alpha"]["id"] = "different-id"

        response = client.post("/api/simulate", json=payload)

        assert response.status_code == 422

    def test_unknown_requested_action_returns_422(self):
        payload = self._minimal_payload()
        payload["actions"] = ["not-a-generated-action"]

        response = client.post("/api/simulate", json=payload)

        assert response.status_code == 422
        assert "Unknown action" in response.json()["detail"]

    def test_empty_action_list_returns_422(self):
        payload = self._minimal_payload()
        payload["actions"] = []

        response = client.post("/api/simulate", json=payload)

        assert response.status_code == 422

    def test_single_module_scenario_is_supported(self):
        payload = self._minimal_payload()
        payload["scenario"]["modules"] = {
            "alpha": payload["scenario"]["modules"]["alpha"]
        }
        payload["scenario"]["connections"] = {}

        response = client.post("/api/simulate", json=payload)

        assert response.status_code == 200
        assert len(response.json()["results"]) == 2


# ─── Nothing-hardcoded invariants, on the real engine ───────────────────────
#
# These two moved here from the deleted mock-adapter suite. Every other test in
# that suite has an equivalent in test_phase_a_adapter.py or in the endpoint
# tests above, but nothing else exercises a synthetic topology: the adapter
# tests all run on the five-module demo or a two-module fixture. `runs=1` keeps
# the real engine's Monte Carlo from lengthening an already slow suite.

def test_actions_reference_the_scenarios_own_ids():
    """Action ids carry the scenario's real ids, never a fixed vocabulary."""
    scenario, emergency = make_minimal_scenario("alpha")
    actions = generate_actions(scenario, emergency)

    non_trivial = [a for a in actions if a.id != "do_nothing"]
    assert non_trivial, "a scenario with a fire should afford some action"
    for action in non_trivial:
        assert "alpha" in action.id or "conn-ab" in action.id
        assert "m1" not in action.id.lower()
        assert "m2" not in action.id.lower()


def test_ten_module_scenario_runs_on_the_real_engine():
    """The engine has no fixed module count — the demo happens to have five."""
    scenario, emergency = make_large_scenario(10)
    response = simulate(scenario, emergency, ["do_nothing"], 1, 42)

    assert len(response.results) == 1
    result = response.results[0]
    assert result.actionId == "do_nothing"
    # Every module the scenario declared is accounted for in the resource map.
    assert set(result.resources.byModuleId) == set(scenario.modules)


# ─── Capability tags, and saying so when there are none ─────────────────────
#
# Untagged equipment gives the engine nothing to judge: no systems, no RETURN,
# and returnees that equal survivors because return was never assessed rather
# than because it was assured. The builder creates equipment with an empty
# list, so that was the default state for anything built in the UI.

def test_equipment_type_implies_a_capability_when_none_is_given():
    assert EquipmentIn(
        id="e", name="e", type="propulsion", state="operational"
    ).providesCapabilities == ["main_propulsion"]
    # The builder sends an explicit empty list, which means the same thing.
    assert EquipmentIn(
        id="e", name="e", type="gnc", state="operational", providesCapabilities=[]
    ).providesCapabilities == ["navigation"]


def test_an_explicit_capability_is_never_overwritten():
    equipment = EquipmentIn(
        id="e", name="e", type="propulsion", state="operational",
        providesCapabilities=["rcs"],
    )
    assert equipment.providesCapabilities == ["rcs"]


def test_ambiguous_equipment_types_are_left_untagged():
    """`science` and `other` carry no single obvious capability, so they are
    not guessed at — a wrong tag is worse than an absent one."""
    for equipment_type in ("science", "other", "fuel", "medical"):
        assert EquipmentIn(
            id="e", name="e", type=equipment_type, state="operational"
        ).providesCapabilities == []


def test_a_scenario_that_declares_no_return_capability_says_so():
    scenario = ScenarioIn(
        name="untagged",
        modules={
            "alpha": ModuleIn(
                id="alpha", name="alpha", type="habitat",
                equipment=[EquipmentIn(id="x", name="x", type="science",
                                       state="operational")],
            ),
            "beta": ModuleIn(id="beta", name="beta", type="storage"),
        },
        connections={
            "c": ConnectionIn(id="c", source="alpha", target="beta",
                              type="hatch", state="open"),
        },
    )
    emergency = EmergencyConfigIn(type="fire", affectedModuleId="alpha")

    response = simulate(scenario, emergency, ["do_nothing"], 1, 1)

    assert response.warnings, "an unjudged return capability must be reported"
    assert "RETURN" in response.warnings[0]
    result = response.results[0]
    assert result.returnCapability.declared is False
    # The two being equal here is an artefact of not asking, which is exactly
    # what the warning exists to stop a reader concluding from.
    assert result.expectedReturnees == result.expectedSurvivors


def test_the_demo_declares_return_and_reports_no_warning():
    fixture = json.loads((FIXTURES_DIR / "five_module_demo.json").read_text("utf-8"))
    response = simulate(
        ScenarioIn(**fixture), EmergencyConfigIn(**fixture["emergency"]),
        ["do_nothing"], 1, 42,
    )

    assert response.warnings == []
    assert response.results[0].returnCapability.declared is True
