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

def test_advisor_status_is_honest_about_configuration():
    response = client.get("/api/advisor/status")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"available", "detail"}
    # Without watsonx credentials it must say so rather than claim readiness.
    if not body["available"]:
        assert "WATSONX" in body["detail"] or "phase_c" in body["detail"]


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
        focus_action_id="isolate:mod-storage",
        samples=2,
        seed=42,
        llm=scripted_llm,
    )
    assert package["provenance"]["focus_action_id"] == "isolate:mod-storage"


def test_advisor_output_never_claims_probability(demo, scripted_llm):
    scenario, emergency = demo
    package = phase_c_advisor.analyze(
        scenario, emergency, samples=2, seed=42, llm=scripted_llm
    )
    text = json.dumps(package).lower()
    assert "survival probability" not in text
    assert "% probability" not in text
