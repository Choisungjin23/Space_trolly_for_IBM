from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

METRIC_FIELDS = [
    "expected_surviving_crew",
    "crew_survival_pct",
    "fire_contained_pct",
    "critical_systems_pct",
    "mission_survival_pct",
    "mean_final_fire_severity",
]


def test_scenario_endpoint():
    data = client.get("/api/scenario").json()
    assert set(data["modules"]) == {"M1", "M2", "M3", "M4", "M5"}
    crew = [c for m in data["modules"].values() for c in m["crew"]]
    assert len(crew) == 4
    burning = [mid for mid, m in data["modules"].items() if m["fire_severity"] > 0]
    assert burning == ["M2"]
    assert len(data["connections"]) == 5
    assert data["critical_systems"] == ["life_support", "power", "propulsion"]
    assert [a["id"] for a in data["actions"]][0] == "do_nothing"


def test_config_endpoint_describes_gui_controls():
    data = client.get("/api/config").json()
    assert data["defaults"]["initial_fire_module"] == "M2"
    assert data["defaults"]["crew_placement"] == {"C1": "M1", "C2": "M1", "C3": "M3", "C4": "M4"}
    assert [m["id"] for m in data["modules"]] == ["M1", "M2", "M3", "M4", "M5"]
    assert [c["id"] for c in data["crew"]] == ["C1", "C2", "C3", "C4"]
    for spec in data["fields"]:
        assert spec["min"] <= data["defaults"][spec["key"]] <= spec["max"]
        assert spec["label"] and spec["group"] and spec["help"]


def test_scenario_preview_applies_settings():
    body = {
        "settings": {
            "initial_fire_module": "M4",
            "initial_fire_severity": 0.9,
            "crew_placement": {"C1": "M5", "C2": "M5", "C3": "M5", "C4": "M5"},
        }
    }
    data = client.post("/api/scenario", json=body).json()
    assert data["modules"]["M4"]["fire_severity"] == 0.9
    assert data["modules"]["M2"]["fire_severity"] == 0.0
    assert len(data["modules"]["M5"]["crew"]) == 4
    assert data["modules"]["M1"]["crew"] == []
    # Actions must follow the fire to M4.
    ids = [a["id"] for a in data["actions"]]
    assert "isolate_m4" in ids and "isolate_m2" not in ids


def test_out_of_range_settings_are_clamped_not_rejected():
    body = {"settings": {"initial_fire_severity": 99.0, "propagation_factor": -5.0}}
    data = client.post("/api/scenario", json=body).json()
    assert data["modules"]["M2"]["fire_severity"] == 1.0


def test_actions_endpoint():
    data = client.get("/api/actions").json()
    assert [a["id"] for a in data["actions"]] == [
        "do_nothing",
        "isolate_m2",
        "close_m1_m2",
        "close_m2_m3",
    ]
    assert all(a["label"] and a["description"] for a in data["actions"])


def test_simulate_defaults_to_all_actions():
    response = client.post("/api/simulate", json={"runs": 50, "seed": 42})
    assert response.status_code == 200
    data = response.json()
    assert data["runs"] == 50
    assert data["seed"] == 42
    assert [r["action_id"] for r in data["results"]] == [
        "do_nothing",
        "isolate_m2",
        "close_m1_m2",
        "close_m2_m3",
    ]
    for result in data["results"]:
        for field in METRIC_FIELDS:
            assert field in result, field


def test_simulate_honours_settings():
    body = {
        "runs": 50,
        "seed": 42,
        "settings": {"initial_fire_module": "M4", "sim_steps": 3},
    }
    data = client.post("/api/simulate", json=body).json()
    assert data["steps"] == 3
    assert any(r["action_id"] == "isolate_m4" for r in data["results"])


def test_simulate_is_reproducible_over_http():
    body = {"runs": 50, "seed": 7}
    a = client.post("/api/simulate", json=body).json()
    b = client.post("/api/simulate", json=body).json()
    assert a == b


def test_simulate_rejects_action_not_valid_for_scenario():
    # isolate_m2 is meaningless once the fire has been moved to M4.
    body = {"runs": 10, "actions": ["isolate_m2"], "settings": {"initial_fire_module": "M4"}}
    assert client.post("/api/simulate", json=body).status_code == 422


def test_simulate_rejects_unknown_action():
    response = client.post("/api/simulate", json={"actions": ["vent_atmosphere"], "runs": 10})
    assert response.status_code == 422


def test_simulate_rejects_out_of_range_runs():
    assert client.post("/api/simulate", json={"runs": 0}).status_code == 422
    assert client.post("/api/simulate", json={"runs": 999999}).status_code == 422
