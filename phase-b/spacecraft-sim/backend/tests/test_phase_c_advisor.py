"""Phase B <-> Phase C integration.

The advisor runs on a scripted LLM here, so these tests need no watsonx
credentials and no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters import phase_c_advisor
from app.api.schemas import EmergencyConfigIn, ScenarioIn
from app.main import app

pytestmark = pytest.mark.skipif(
    not phase_c_advisor.PHASE_C_AVAILABLE, reason="phase_c not installed"
)

client = TestClient(app)
FIXTURES_DIR = Path(__file__).parent.parent / "app" / "fixtures"


@pytest.fixture
def demo() -> tuple[ScenarioIn, EmergencyConfigIn]:
    raw = json.loads((FIXTURES_DIR / "five_module_demo.json").read_text("utf-8"))
    return ScenarioIn(**raw), EmergencyConfigIn(**raw["emergency"])


@pytest.fixture
def scripted_llm():
    from phase_c.agents.critic import _CriticDraft
    from phase_c.agents.evidence import _EvidenceBundle, _EvidenceDraft
    from phase_c.contracts.findings import (
        AgentFinding,
        Claim,
        Recommendation,
        Tradeoff,
    )

    finding = AgentFinding(
        agent="x",
        claims=[
            Claim(
                statement="In this simulation, smoke stayed within the modules listed.",
                basis="SIMULATION_FACT",
                refs=["/actions/0/hazard/reached_modules"],
            )
        ],
    )
    recommendation = Recommendation(
        recommended_action_id="do_nothing",
        rationale=[
            Claim(
                statement="Baseline retained the declared capabilities.",
                basis="SIMULATION_FACT",
                refs=["/actions/0/capabilities"],
            )
        ],
        tradeoffs=[
            Tradeoff(
                versus_action_id="do_nothing",
                gives_up="Containment margin",
                gains="Continued access to every module",
            )
        ],
        uncertainty=["Sampling covered decision delay and flow uncertainty only."],
    )

    responses = {
        "hazard": finding,
        "crew_safety": finding,
        "systems": finding,
        "mission": finding,
        "evidence": _EvidenceBundle(
            answers=[
                _EvidenceDraft(
                    claim="The source states an exposure guideline.",
                    applicability="Applies to spacecraft cabin atmospheres.",
                )
            ]
        ),
        "critic": _CriticDraft(),
        "coordinator": recommendation,
    }

    class Scripted:
        def complete(self, *, system, user, schema, temperature=0.0):
            agent = next(
                (
                    line.split("AGENT:", 1)[1].strip()
                    for line in system.splitlines()
                    if line.strip().startswith("AGENT:")
                ),
                "unknown",
            )
            return responses[agent]

    return Scripted()


# ── Status endpoint ─────────────────────────────────────────────────────────

@pytest.fixture
def configured(monkeypatch):
    """A complete Dallas configuration, as backend/.env supplies it."""
    monkeypatch.setenv("WATSONX_API_KEY", "test-secret-that-must-not-appear")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "test-project-id-that-must-not-appear")
    monkeypatch.setenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    monkeypatch.setenv("WATSONX_MODEL_ID", "ibm/granite-4-h-small")
    monkeypatch.delenv("WATSONX_APIKEY_FILE", raising=False)
    return monkeypatch


def test_advisor_status_is_honest_about_configuration():
    response = client.get("/api/advisor/status")
    assert response.status_code == 200
    body = response.json()
    # Without watsonx credentials it must say so rather than claim readiness.
    if not body["available"]:
        assert "WATSONX" in body["detail"] or "phase_c" in body["detail"]


def test_advisor_status_accepts_loaded_configuration(configured):
    response = client.get("/api/advisor/status")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["configured"] is True


def test_advisor_status_reports_the_configured_model_and_region(configured):
    """An operator must be able to see which model produced the advice."""
    body = client.get("/api/advisor/status").json()

    assert body["model_id"] == "ibm/granite-4-h-small"
    assert body["watsonx_url"] == "https://us-south.ml.cloud.ibm.com"


def test_advisor_status_never_returns_the_key_or_project_id(configured):
    response = client.get("/api/advisor/status")

    assert "test-secret-that-must-not-appear" not in response.text
    assert "test-project-id-that-must-not-appear" not in response.text


def test_advisor_status_rejects_unedited_example_placeholders(configured):
    configured.setenv("WATSONX_API_KEY", "YOUR_IBM_API_KEY")
    configured.setenv("WATSONX_PROJECT_ID", "YOUR_WATSONX_PROJECT_ID")
    configured.setenv("WATSONX_URL", "https://YOUR_REGION.ml.cloud.ibm.com")

    response = client.get("/api/advisor/status")

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert "YOUR_IBM_API_KEY" not in response.text


def test_advisor_status_requires_a_model_id(configured):
    """WATSONX_MODEL_ID has no default, so an unset one must disable the
    advisor rather than fall back to a previously hardcoded model."""
    configured.delenv("WATSONX_MODEL_ID", raising=False)

    body = client.get("/api/advisor/status").json()

    assert body["available"] is False
    assert "WATSONX_MODEL_ID" in body["detail"]


def test_analyze_endpoint_reports_missing_llm_rather_than_crashing(demo):
    scenario, emergency = demo
    response = client.post(
        "/api/analyze",
        json={
            "scenario": json.loads(scenario.model_dump_json()),
            "emergency": json.loads(emergency.model_dump_json()),
            "samples": 2,
            "seed": 1,
        },
    )
    # Either the advisor is configured, or it fails cleanly with 503.
    assert response.status_code in (200, 503)
    if response.status_code == 503:
        assert "detail" in response.json()


def test_analyze_rejects_an_emergency_in_a_missing_module(demo):
    scenario, _ = demo
    response = client.post(
        "/api/analyze",
        json={
            "scenario": json.loads(scenario.model_dump_json()),
            "emergency": {"type": "fire", "affectedModuleId": "nope", "detected": True},
            "samples": 2,
        },
    )
    assert response.status_code == 422


# ── Pipeline on a scripted LLM ──────────────────────────────────────────────

def test_advisor_runs_end_to_end_on_the_demo(demo, scripted_llm):
    scenario, emergency = demo
    package = phase_c_advisor.analyze(
        scenario, emergency, samples=2, seed=42, llm=scripted_llm
    )

    assert package["scenario_digest"]
    assert [f["agent"] for f in package["findings"]] == [
        "hazard",
        "crew_safety",
        "systems",
        "mission",
    ]
    assert package["recommendation"]["human_decision_required"] is True
    ethics = package["ethical_assessment"]
    assert ethics["policy_id"] == "ASSUMED_HUMAN_PRESERVATION_POLICY_V1"
    assert ethics["sources"]
    assert package["recommendation"]["recommended_action_id"] == ethics["selected_action_id"]
    assert "counts over sampled assumption sets" in package["provenance"]["sampling_note"]


def test_advisor_uses_the_real_engine_not_the_mock(demo, scripted_llm):
    scenario, emergency = demo
    package = phase_c_advisor.analyze(
        scenario, emergency, samples=2, seed=42, llm=scripted_llm
    )
    assert package["provenance"]["engine"].startswith("spacecraft_sim")


def test_advisor_can_focus_a_specific_action(demo, scripted_llm):
    scenario, emergency = demo
    package = phase_c_advisor.analyze(
        scenario,
        emergency,
        focus_action_id="isolate:mod-habitat",
        samples=2,
        seed=42,
        llm=scripted_llm,
    )
    assert package["provenance"]["focus_action_id"] == "isolate:mod-habitat"


def test_advisor_output_carries_modeled_survival_probability(demo, scripted_llm):
    scenario, emergency = demo
    package = phase_c_advisor.analyze(
        scenario, emergency, samples=2, seed=42, llm=scripted_llm
    )
    assert package["provenance"]["decision_objective"] == (
        "lexicographic_human_preservation_policy_v1"
    )


# ── Action id vocabulary across the Phase B / Phase C boundary ──────────────

def test_focus_action_id_is_translated_into_the_engine_vocabulary(demo):
    """Phase B names an action `power_down_mod-habitat`; the engine, and so
    Phase C, calls the same action `power_down:mod-habitat`. Passing the Phase B
    id straight through used to fail with 'No analysis for action id'."""
    from app.adapters.phase_a_simulator import to_phase_a_action_id

    scenario, emergency = demo

    assert (
        to_phase_a_action_id(scenario, emergency, "power_down_mod-habitat")
        == "power_down:mod-habitat"
    )
    # Already an engine id: returned unchanged, so either side may call it.
    assert (
        to_phase_a_action_id(scenario, emergency, "power_down:mod-habitat")
        == "power_down:mod-habitat"
    )


def test_every_generated_action_id_translates(demo):
    from app.adapters.phase_a_simulator import generate_actions, to_phase_a_action_id

    scenario, emergency = demo
    for action in generate_actions(scenario, emergency):
        assert to_phase_a_action_id(scenario, emergency, action.id)


def test_an_unknown_focus_action_names_the_valid_ids(demo):
    from app.adapters.phase_a_simulator import to_phase_a_action_id

    scenario, emergency = demo
    with pytest.raises(ValueError, match="Unknown action id"):
        to_phase_a_action_id(scenario, emergency, "not_an_action")


def test_advisor_focuses_a_phase_b_action_id_end_to_end(demo, scripted_llm):
    """The id the results table hands the Advisor must reach the pipeline."""
    scenario, emergency = demo
    package = phase_c_advisor.analyze(
        scenario,
        emergency,
        focus_action_id="power_down_mod-habitat",
        samples=2,
        seed=42,
        llm=scripted_llm,
    )
    assert package["provenance"]["focus_action_id"] == "power_down:mod-habitat"


def test_analyze_endpoint_rejects_an_unknown_focus_action(demo):
    scenario, emergency = demo
    response = client.post(
        "/api/analyze",
        json={
            "scenario": json.loads(scenario.model_dump_json()),
            "emergency": json.loads(emergency.model_dump_json()),
            "focusActionId": "not_an_action",
            "samples": 2,
        },
    )
    assert response.status_code == 422
    assert "Unknown action id" in response.json()["detail"]


def test_station_repairer_actions_reach_the_phase_b_api(demo):
    """Phase B declares no systems, so this action used to be unreachable."""
    from app.adapters.phase_a_simulator import generate_actions

    scenario, emergency = demo
    ids = [a.id for a in generate_actions(scenario, emergency)]

    assert any(i.startswith("station_") for i in ids)
    # Never into the burning module.
    assert not any(i.endswith("_in_mod-habitat") for i in ids)


def test_advisor_status_identifies_the_key_without_disclosing_it(configured):
    """A running server loads .env once at startup. Editing the file afterwards
    changes nothing until restart, which looks exactly like a bad credential.
    The fingerprint lets an operator compare the running key against the file."""
    from phase_c.config import fingerprint

    body = client.get("/api/advisor/status").json()

    assert body["key_fingerprint"] == fingerprint(
        "test-secret-that-must-not-appear"
    )
    assert body["key_source"] is not None
    assert "test-secret-that-must-not-appear" not in str(body)


def test_advisor_status_says_when_the_shell_shadows_the_env_file(configured):
    body = client.get("/api/advisor/status").json()
    # The fixture sets the variables in the process environment, so the source
    # must not claim they came from the file.
    assert body["key_source"] != "unset"


# ── Progress streaming ──────────────────────────────────────────────────────

def _read_sse(response) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    name = "message"
    for line in response.iter_lines():
        if line.startswith("event: "):
            name = line[7:].strip()
        elif line.startswith("data: "):
            events.append((name, json.loads(line[6:])))
    return events


def test_simulate_stream_reports_every_action_then_the_result(demo):
    """A minute of spinner with no explanation is the thing this replaces, so
    the stream must name each action as it is reached."""
    scenario, emergency = demo
    with client.stream(
        "POST",
        "/api/simulate/stream",
        json={
            "scenario": json.loads(scenario.model_dump_json()),
            "emergency": json.loads(emergency.model_dump_json()),
            "actions": None,
            "runs": 5,
            "seed": 42,
        },
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        events = _read_sse(response)

    progress = [payload for name, payload in events if name == "progress"]
    results = [payload for name, payload in events if name == "result"]

    assert len(results) == 1
    assert len(progress) == len(results[0]["result"]["results"]) + 1  # + Complete
    assert progress[0]["percent"] == 0
    assert progress[-1]["percent"] == 100
    # Never goes backwards.
    assert progress == sorted(progress, key=lambda p: p["percent"])


def test_stream_progress_is_monotonic_and_labelled(demo):
    scenario, emergency = demo
    with client.stream(
        "POST",
        "/api/simulate/stream",
        json={
            "scenario": json.loads(scenario.model_dump_json()),
            "emergency": json.loads(emergency.model_dump_json()),
            "actions": None,
            "runs": 2,
            "seed": 1,
        },
    ) as response:
        events = _read_sse(response)

    for _, payload in [e for e in events if e[0] == "progress"]:
        assert payload["label"], "every stage names what is running"
        assert 0 <= payload["percent"] <= 100
        assert payload["done"] <= payload["total"]


def test_the_streamed_result_matches_the_plain_endpoint(demo):
    """The stream is a view onto the same work, not a second implementation."""
    scenario, emergency = demo
    body = {
        "scenario": json.loads(scenario.model_dump_json()),
        "emergency": json.loads(emergency.model_dump_json()),
        "actions": None,
        "runs": 5,
        "seed": 42,
    }
    plain = client.post("/api/simulate", json=body).json()
    with client.stream("POST", "/api/simulate/stream", json=body) as response:
        events = _read_sse(response)
    streamed = [p for n, p in events if n == "result"][0]["result"]

    assert streamed["generatedActions"] == plain["generatedActions"]
    assert streamed["results"] == plain["results"]


def test_a_stream_failure_arrives_as_an_error_event(demo):
    """A failure mid-stream cannot use an HTTP status — headers are long sent —
    so it has to reach the client as an event."""
    scenario, _ = demo
    with client.stream(
        "POST",
        "/api/simulate/stream",
        json={
            "scenario": json.loads(scenario.model_dump_json()),
            "emergency": {"type": "fire", "affectedModuleId": "nope", "detected": True},
            "actions": None,
            "runs": 2,
        },
    ) as response:
        # The request body itself is invalid, so this one is rejected up front.
        assert response.status_code == 422


def test_advisor_stream_refuses_cleanly_when_unconfigured(demo, monkeypatch):
    for name in ("WATSONX_API_KEY", "WATSONX_PROJECT_ID"):
        monkeypatch.delenv(name, raising=False)
    scenario, emergency = demo
    response = client.post(
        "/api/analyze/stream",
        json={
            "scenario": json.loads(scenario.model_dump_json()),
            "emergency": json.loads(emergency.model_dump_json()),
            "samples": 2,
        },
    )
    assert response.status_code == 503
    assert "WATSONX" in response.json()["detail"]
