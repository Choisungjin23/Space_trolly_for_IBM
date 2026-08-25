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
from app.adapters.mock_simulator import generate_actions, simulate
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

class TestGenerateActions:
    def test_do_nothing_always_present(self):
        scenario, emergency = make_minimal_scenario("alpha")
        actions = generate_actions(scenario, emergency)
        ids = [a.id for a in actions]
        assert "do_nothing" in ids

    def test_close_connection_generated_from_graph(self):
        scenario, emergency = make_minimal_scenario("alpha")
        actions = generate_actions(scenario, emergency)
        ids = [a.id for a in actions]
        # Should have a close action for the open connection
        assert any("close_conn" in aid for aid in ids)

    def test_isolate_module_generated(self):
        scenario, emergency = make_minimal_scenario("alpha")
        actions = generate_actions(scenario, emergency)
        ids = [a.id for a in actions]
        assert any("isolate_module" in aid for aid in ids)

    def test_no_m1_m2_in_action_ids(self):
        scenario, emergency = make_minimal_scenario("alpha")
        actions = generate_actions(scenario, emergency)
        for action in actions:
            assert "m1" not in action.id.lower()
            assert "m2" not in action.id.lower()

    def test_actions_reference_arbitrary_ids(self):
        """Action IDs must contain the actual module/connection IDs, not hard-coded names."""
        scenario, emergency = make_minimal_scenario("alpha")
        actions = generate_actions(scenario, emergency)
        non_trivial = [a for a in actions if a.id != "do_nothing"]
        assert len(non_trivial) > 0
        # Each non-trivial action should reference 'alpha' or 'conn-ab' in its ID
        for a in non_trivial:
            assert "alpha" in a.id or "conn-ab" in a.id


class TestSimulate:
    def test_2module_scenario_returns_valid_response(self):
        scenario, emergency = make_minimal_scenario("alpha")
        response = simulate(scenario, emergency, None, 100, 42)
        assert response.sourceLabel.startswith("MockSimulatorAdapter")
        assert len(response.results) > 0
        assert response.runsRequested == 100

    def test_10module_scenario_accepted(self):
        scenario, emergency = make_large_scenario(10)
        response = simulate(scenario, emergency, None, 50, 1)
        assert len(response.results) > 0

    def test_no_hazard_spread_probability_in_response(self):
        scenario, emergency = make_minimal_scenario("alpha")
        response = simulate(scenario, emergency, None, 50, 42)
        import json as _json
        response_json = response.model_dump_json()
        assert "hazard_spread_probability" not in response_json
        assert "PROPAGATION_FACTOR" not in response_json

    def test_source_label_is_mock(self):
        scenario, emergency = make_minimal_scenario("alpha")
        response = simulate(scenario, emergency, None, 10, 42)
        assert "Mock" in response.sourceLabel or "mock" in response.sourceLabel.lower()

    def test_results_have_all_required_fields(self):
        scenario, emergency = make_minimal_scenario("alpha")
        response = simulate(scenario, emergency, None, 50, 42)
        for result in response.results:
            assert result.actionId
            assert result.hazard is not None
            assert result.crew is not None
            assert result.equipment is not None
            assert result.capabilities is not None
            assert result.criticalFunctions is not None

    def test_determinism_with_seed(self):
        scenario, emergency = make_minimal_scenario("alpha")
        r1 = simulate(scenario, emergency, None, 100, 99)
        r2 = simulate(scenario, emergency, None, 100, 99)
        assert r1.results[0].crew.allEvacuatedCount == r2.results[0].crew.allEvacuatedCount

    def test_sample_counts_within_range(self):
        scenario, emergency = make_minimal_scenario("alpha")
        response = simulate(scenario, emergency, None, 200, 42)
        for result in response.results:
            assert 0 <= result.crew.allEvacuatedCount <= 200
            assert 0 <= result.crew.anyTrappedCount <= 200
            assert 0 <= result.hazard.containedInNScenarios <= 200

    def test_existing_failed_equipment_state_is_preserved(self):
        scenario, emergency = make_minimal_scenario("alpha")
        scenario.modules["beta"].equipment = [
            EquipmentIn(
                id="eq-failed",
                name="Failed Radio",
                type="comms",
                state="explicitly_failed",
                providesCapabilities=["communications"],
            )
        ]

        response = simulate(scenario, emergency, ["do_nothing"], 20, 42)

        result = response.results[0]
        assert result.equipment.byEquipmentId["eq-failed"].state == "explicitly_failed"
        assert result.capabilities.byCapability["communications"] == "unavailable"

    def test_closed_connection_is_not_a_partial_spread_path(self):
        modules = {
            module_id: ModuleIn(id=module_id, name=module_id, type="other")
            for module_id in ("alpha", "beta", "gamma")
        }
        scenario = ScenarioIn(
            name="Closed path scenario",
            modules=modules,
            connections={
                "open-path": ConnectionIn(
                    id="open-path",
                    source="alpha",
                    target="beta",
                    type="hatch",
                    state="open",
                ),
                "closed-path": ConnectionIn(
                    id="closed-path",
                    source="alpha",
                    target="gamma",
                    type="hatch",
                    state="closed",
                ),
            },
        )
        emergency = EmergencyConfigIn(affectedModuleId="alpha")

        response = simulate(scenario, emergency, ["close_conn_open-path"], 20, 0)

        assert "gamma" not in response.results[0].hazard.modulesReachedIds

    def test_trajectory_seed_uses_stable_action_hash_and_preserves_zero_seed(self):
        scenario, emergency = make_minimal_scenario("alpha")
        response = simulate(scenario, emergency, ["do_nothing"], 20, 0)
        expected_hash = int.from_bytes(
            hashlib.sha256(b"do_nothing").digest()[:4],
            byteorder="big",
        )

        assert response.results[0].exampleTrajectory is not None
        assert response.results[0].exampleTrajectory.seed == expected_hash % 1000


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
        assert len(data["modules"]) == 5

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
