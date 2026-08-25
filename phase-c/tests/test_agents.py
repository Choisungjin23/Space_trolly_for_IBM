"""Agents must see only their domain's data, and must not be able to relabel
themselves or wander onto another action."""

import json

import pytest

from phase_c.agents.crew import CrewSafetyAgent
from phase_c.agents.evidence import EvidenceAgent
from phase_c.agents.hazard import HazardAgent
from phase_c.agents.mission import MissionAgent
from phase_c.agents.systems import SystemsAgent
from phase_c.contracts.findings import AgentFinding
from phase_c.llm.stub import StubLLMClient
from phase_c.rag.store import EvidenceStore
from tests.conftest import ScriptedLLM, grounded_finding

SPECIALISTS = [HazardAgent, CrewSafetyAgent, SystemsAgent, MissionAgent]


@pytest.mark.parametrize("agent_cls", SPECIALISTS)
def test_agent_declares_itself_in_the_system_prompt(agent_cls):
    agent = agent_cls(StubLLMClient())
    assert f"AGENT: {agent.name}" in agent.system_prompt()


@pytest.mark.parametrize("agent_cls", SPECIALISTS)
def test_house_rules_are_always_present(agent_cls):
    prompt = agent_cls(StubLLMClient()).system_prompt()
    assert "never invent" in prompt.lower()
    assert "sampled assumption sets" in prompt
    assert "no fatality model" in prompt.lower() or "fatality" in prompt.lower()


@pytest.mark.parametrize("agent_cls", SPECIALISTS)
def test_agent_output_is_relabelled_to_the_truth(agent_cls, focus, case):
    """An agent claiming to be someone else, or analysing another action, is
    overwritten — the orchestrator decides who ran and on what."""
    liar = grounded_finding(agent="not_me", action_id="some:other:action")
    agent = agent_cls(ScriptedLLM({agent_cls.name: liar}))
    finding = agent.analyze(focus, case)
    assert finding.agent == agent_cls.name
    assert finding.action_id == focus.action.id


def test_hazard_agent_sees_hazard_only(focus, case):
    payload = HazardAgent(StubLLMClient()).project(focus, case)
    assert set(payload) == {"detection", "hazard", "events", "sampled"}
    assert "crew" not in payload and "systems" not in payload


def test_crew_agent_receives_crew_keyed_by_id(focus, case):
    payload = CrewSafetyAgent(StubLLMClient()).project(focus, case)
    assert isinstance(payload["crew"], dict)
    for crew_id, outcome in payload["crew"].items():
        assert crew_id.startswith("C") or crew_id
        assert {"state", "exposure_seconds", "smac_dose_fraction", "module"} <= set(
            outcome
        )


def test_crew_agent_carries_the_criticality_framing(focus, case):
    role = CrewSafetyAgent(StubLLMClient()).role
    assert "worth of a life" in role
    assert "irreplaceable a FUNCTION" in role
    payload = CrewSafetyAgent(StubLLMClient()).project(focus, case)
    assert payload["criticality_baseline_action"]


def test_systems_agent_gets_equipment_and_reasons(focus, case):
    payload = SystemsAgent(StubLLMClient()).project(focus, case)
    assert "equipment" in payload and "system_reasons" in payload
    assert "RECOVERABLE" in SystemsAgent(StubLLMClient()).role


def test_mission_agent_is_told_capabilities_are_scenario_defined(focus, case):
    agent = MissionAgent(StubLLMClient())
    payload = agent.project(focus, case)
    assert payload["capability_names_declared_by_scenario"] == case.capability_names
    assert "defined BY THIS SCENARIO" in agent.role


def test_no_agent_prompt_hardcodes_demo_identifiers(focus, case):
    """Module, crew and capability names must come from data, not the prompt."""
    for agent_cls in SPECIALISTS:
        role = agent_cls(StubLLMClient()).role
        for banned in ("M1", "M2", "C3", "isolate:M2", "c_m2_m3"):
            assert banned not in role, (agent_cls.name, banned)


def test_user_prompt_contains_the_data_and_the_provenance(focus, case):
    prompt = HazardAgent(StubLLMClient()).user_prompt(focus, case)
    assert focus.action.id in prompt
    assert "ENGINE PROVENANCE" in prompt
    assert "ASSUMED_" in prompt


def test_stub_refuses_to_guess():
    from phase_c.llm.base import LLMError

    with pytest.raises(LLMError):
        StubLLMClient().complete(
            system="AGENT: hazard", user="", schema=AgentFinding
        )


# ── Evidence / RAG ──────────────────────────────────────────────────────────

def test_corpus_loads_and_every_citation_has_a_locator():
    store = EvidenceStore.from_corpus()
    assert store.chunks
    for chunk in store.chunks:
        assert chunk.citation.locator.strip()
        assert chunk.citation.source_id and chunk.citation.title


def test_corpus_rejects_a_citation_without_a_locator(tmp_path):
    (tmp_path / "bad.json").write_text(
        json.dumps(
            [
                {
                    "id": "x",
                    "text": "t",
                    "keywords": [],
                    "citation": {"source_id": "s", "title": "t", "locator": "  "},
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="locator"):
        EvidenceStore.from_corpus(tmp_path)


def test_search_finds_the_expected_source():
    store = EvidenceStore.from_corpus()
    hits = store.search("carbon monoxide exposure limit", limit=2)
    assert any("JSC-20584" in c.citation.source_id for c in hits)


def test_evidence_queries_follow_what_actually_happened(focus, case):
    agent = EvidenceAgent(StubLLMClient(), EvidenceStore.from_corpus())
    queries = agent.queries_for(focus, case)
    assert queries
    assert all(isinstance(q, str) and q for q in queries)


def test_evidence_answers_carry_a_citation_and_applicability(focus, case):
    from phase_c.agents.evidence import _EvidenceBundle, _EvidenceDraft

    llm = ScriptedLLM(
        {
            "evidence": _EvidenceBundle(
                answers=[
                    _EvidenceDraft(
                        claim="The source states an exposure guideline.",
                        applicability="Applies to spacecraft cabin atmospheres only.",
                        limits="Not a prediction about this run.",
                    )
                ]
            )
        }
    )
    answers = EvidenceAgent(llm, EvidenceStore.from_corpus()).gather(focus, case)
    assert answers
    for answer in answers:
        assert answer.citation.locator
        assert answer.applicability
        assert answer.ref_id.startswith("evidence:")
