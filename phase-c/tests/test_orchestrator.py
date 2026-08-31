"""End-to-end pipeline on the stub client: specialists -> evidence -> validator
-> critic -> coordinator -> DecisionPackage."""

from phase_c.agents.critic import _CriticDraft
from phase_c.agents.evidence import _EvidenceBundle, _EvidenceDraft
from phase_c.contracts.findings import AgentFinding, Claim, CriticIssue
from phase_c.orchestrator import Orchestrator
from tests.conftest import ScriptedLLM, grounded_finding, sound_recommendation

EVIDENCE = _EvidenceBundle(
    answers=[
        _EvidenceDraft(
            claim="The source gives an exposure guideline for combustion products.",
            applicability="Applies to spacecraft cabin atmospheres, not to this run's numbers.",
        )
    ]
)


def scripted(**overrides):
    responses = {
        "hazard": grounded_finding("hazard"),
        "crew_safety": grounded_finding("crew_safety"),
        "systems": grounded_finding("systems"),
        "mission": grounded_finding("mission"),
        "evidence": EVIDENCE,
        "critic": _CriticDraft(),
        "coordinator": sound_recommendation(),
    }
    responses.update(overrides)
    return ScriptedLLM(responses)


def test_pipeline_produces_a_complete_package(case):
    package = Orchestrator(scripted()).run(case)

    assert package.scenario_digest == case.scenario_digest
    assert [f.agent for f in package.findings] == [
        "hazard",
        "crew_safety",
        "systems",
        "mission",
    ]
    assert package.evidence
    assert package.recommendation is not None
    assert package.recommendation.human_decision_required is True


def test_every_agent_is_actually_consulted(case):
    llm = scripted()
    Orchestrator(llm).run(case)
    assert {"hazard", "crew_safety", "systems", "mission", "critic", "coordinator"} <= set(
        llm.seen
    )


def test_focus_defaults_to_the_do_nothing_baseline(case):
    package = Orchestrator(scripted()).run(case)
    assert package.provenance["focus_action_id"] == "do_nothing"
    assert all(f.action_id == "do_nothing" for f in package.findings)


def test_focus_can_be_directed_at_another_action(case):
    package = Orchestrator(scripted(), focus_action_id="isolate:M2").run(case)
    assert package.provenance["focus_action_id"] == "isolate:M2"


def test_grounding_violations_reach_the_operator(case):
    """An agent that invents a number must not be silently cleaned up."""
    liar = AgentFinding(
        agent="hazard",
        claims=[
            Claim(
                statement="The fire grew at 7.77 mm per second.",
                basis="INFERENCE",
            )
        ],
    )
    package = Orchestrator(scripted(hazard=liar)).run(case)
    rules = {v.rule for v in package.critic.grounding_violations}
    assert "R1_unsupported_number" in rules
    # And the offending claim is still visible, not deleted.
    assert any("7.77" in c.statement for f in package.findings for c in f.claims)


def test_probability_phrasing_on_sampled_counts_is_flagged(case):
    liar = AgentFinding(
        agent="mission",
        claims=[
            Claim(
                statement="Capability survives with 100% probability.",
                basis="SIMULATION_FACT",
                refs=["/actions/0/sampled/counts/no_crew_trapped"],
            )
        ],
    )
    package = Orchestrator(scripted(mission=liar)).run(case)
    assert "R3_sampled_as_probability" in {
        v.rule for v in package.critic.grounding_violations
    }


def test_bad_recommendation_is_flagged_not_swallowed(case):
    bare = sound_recommendation().model_copy(
        update={"tradeoffs": [], "uncertainty": []}
    )
    package = Orchestrator(scripted(coordinator=bare)).run(case)
    rules = {v.rule for v in package.critic.grounding_violations}
    assert {"R6_no_tradeoff", "R7_no_uncertainty"} <= rules


def test_coordinator_cannot_hand_the_decision_to_the_machine(case):
    rec = sound_recommendation().model_copy(update={"human_decision_required": False})
    package = Orchestrator(scripted(coordinator=rec)).run(case)
    assert package.recommendation.human_decision_required is True


def test_coordinator_cannot_replace_the_policy_selected_action(case):
    proposed = sound_recommendation("do_nothing")
    package = Orchestrator(scripted(coordinator=proposed)).run(case)

    assert package.ethical_assessment.selected_action_id == "isolate:M2"
    assert package.recommendation.recommended_action_id == "isolate:M2"
    assert package.recommendation.model_proposed_action_id == "do_nothing"
    assert package.recommendation.policy_override_applied is True
    assert "E6_coordinator_policy_override" in {
        violation.rule for violation in package.critic.grounding_violations
    }


def test_critic_issues_are_carried_through(case):
    review = _CriticDraft(
        issues=[
            CriticIssue(
                severity="MAJOR",
                target_agent="hazard",
                issue="No mention of the alternative containment actions.",
                suggested_correction="Compare against the other generated actions.",
            )
        ]
    )
    package = Orchestrator(scripted(critic=review)).run(case)
    assert package.critic.issues and package.critic.issues[0].target_agent == "hazard"


def test_provenance_carries_the_sampling_and_ethics_notices(case):
    provenance = Orchestrator(scripted()).run(case).provenance
    assert "counts over sampled assumption sets" in provenance["sampling_note"]
    assert "ASSUMED_" in provenance["ethics_notice"]
    assert provenance["engine"].startswith("spacecraft_sim")
    assert provenance["criticality_baseline_action"] == "do_nothing"


def test_package_serializes_for_an_api(case):
    package = Orchestrator(scripted()).run(case)
    payload = package.model_dump_json()
    assert "recommendation" in payload
    assert "grounding_violations" in payload
