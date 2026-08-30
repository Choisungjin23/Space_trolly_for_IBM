"""The grounding validator is the core safety mechanism (plan §7).

These are adversarial: each test hands the validator a finding that a
sloppy or over-confident LLM would plausibly produce.
"""

from phase_c.contracts.evidence import EvidenceAnswer, EvidenceCitation
from phase_c.contracts.findings import AgentFinding, Claim
from phase_c.grounding.registry import FactRegistry
from phase_c.grounding.validator import validate_finding, validate_recommendation
from tests.conftest import grounded_finding, sound_recommendation


def rules(violations):
    return {v.rule for v in violations}


def test_grounded_finding_passes(case):
    registry = FactRegistry.from_case(case)
    assert validate_finding(grounded_finding("hazard"), registry) == []


def test_r1_invented_number_is_caught(case):
    registry = FactRegistry.from_case(case)
    finding = AgentFinding(
        agent="hazard",
        claims=[
            Claim(
                statement="Fire spread at a rate of 8.42 mm per second.",
                basis="INFERENCE",
            )
        ],
    )
    assert "R1_unsupported_number" in rules(validate_finding(finding, registry))


def test_r1_allows_a_number_that_exists_in_the_analysis(case):
    registry = FactRegistry.from_case(case)
    detected = case.action("do_nothing").detection.detected_at_seconds
    finding = AgentFinding(
        agent="hazard",
        claims=[
            Claim(
                statement=f"Detection occurred at {detected:g} s in this run.",
                basis="SIMULATION_FACT",
                refs=["/actions/0/detection/detected_at_seconds"],
            )
        ],
    )
    assert validate_finding(finding, registry) == []


def test_r1_allows_a_list_length(case):
    """Agents legitimately say 'N modules were reached'."""
    registry = FactRegistry.from_case(case)
    count = len(case.action("do_nothing").hazard.reached_modules)
    finding = AgentFinding(
        agent="hazard",
        claims=[
            Claim(
                statement=f"Smoke reached {count} modules in this run.",
                basis="SIMULATION_FACT",
                refs=["/actions/0/hazard/reached_modules"],
            )
        ],
    )
    assert validate_finding(finding, registry) == []


def test_r1_accepts_a_number_backed_by_cited_evidence(case):
    registry = FactRegistry.from_case(case)
    evidence = [
        EvidenceAnswer(
            query="exposure limits",
            claim="The 1-hour SMAC for carbon monoxide is 425 ppm.",
            citation=EvidenceCitation(
                source_id="JSC-20584-RevC", title="SMAC", locator="CO row"
            ),
            applicability="Applies to spacecraft cabin atmospheres.",
        )
    ]
    finding = AgentFinding(
        agent="hazard",
        claims=[
            Claim(
                statement="The 1-hour carbon monoxide guideline is 425 ppm.",
                basis="EVIDENCE",
                refs=["evidence:JSC-20584-RevC"],
            )
        ],
    )
    assert validate_finding(finding, registry, evidence=evidence) == []


def test_r2_simulation_fact_without_a_resolving_ref(case):
    registry = FactRegistry.from_case(case)
    finding = AgentFinding(
        agent="crew_safety",
        claims=[
            Claim(
                statement="Everyone stayed safe.",
                basis="SIMULATION_FACT",
                refs=["/nowhere/at/all"],
            )
        ],
    )
    assert "R2_unreferenced_simulation_fact" in rules(validate_finding(finding, registry))


def test_r3_sampled_counts_phrased_as_probability(case):
    registry = FactRegistry.from_case(case)
    finding = AgentFinding(
        agent="hazard",
        claims=[
            Claim(
                statement="There is a 100% probability the hazard stays contained.",
                basis="SIMULATION_FACT",
                refs=["/actions/0/sampled/counts/hazard_contained_to_sources"],
            )
        ],
    )
    assert "R3_sampled_as_probability" in rules(validate_finding(finding, registry))


def test_r3_allows_k_of_n_phrasing(case):
    registry = FactRegistry.from_case(case)
    sampled = case.action("do_nothing").sampled
    contained = sampled.counts["hazard_contained_to_sources"]
    finding = AgentFinding(
        agent="hazard",
        claims=[
            Claim(
                statement=(
                    f"The hazard stayed contained in {contained} of "
                    f"{sampled.samples} sampled assumption sets."
                ),
                basis="SIMULATION_FACT",
                refs=["/actions/0/sampled/counts/hazard_contained_to_sources"],
            )
        ],
    )
    assert validate_finding(finding, registry) == []


def test_modeled_survival_probability_is_allowed_when_grounded(case):
    registry = FactRegistry.from_case(case)
    finding = AgentFinding(
        agent="crew_safety",
        claims=[Claim(
            statement="C1 modeled survival probability is 1.",
            basis="SIMULATION_FACT",
            refs=["/actions/0/crew/C1/survival_probability"],
        )],
    )
    assert validate_finding(finding, registry) == []


def test_fatality_language_is_not_blanket_blocked(case):
    registry = FactRegistry.from_case(case)
    finding = AgentFinding(
        agent="crew_safety",
        claims=[],
        concerns=["Delay raises the risk of crew deaths."],
    )
    assert validate_finding(finding, registry) == []


def test_r5_best_action_only_from_coordinator(case):
    registry = FactRegistry.from_case(case)
    finding = AgentFinding(
        agent="mission",
        claims=[Claim(statement="The best action is to isolate.", basis="INFERENCE")],
    )
    assert "R5_best_action_outside_coordinator" in rules(
        validate_finding(finding, registry)
    )
    assert "R5_best_action_outside_coordinator" not in rules(
        validate_finding(finding, registry, allow_best_action=True)
    )


def test_module_and_crew_ids_are_not_read_as_numbers(case):
    """M2 and C3 must not trip the numeric check."""
    registry = FactRegistry.from_case(case)
    finding = AgentFinding(
        agent="hazard",
        claims=[
            Claim(
                statement="Smoke reached M2 while C3 remained in M3.",
                basis="SIMULATION_FACT",
                refs=["/actions/0/hazard/reached_modules"],
            )
        ],
    )
    assert validate_finding(finding, registry) == []


def test_recommendation_needs_a_tradeoff_and_uncertainty(case):
    registry = FactRegistry.from_case(case)
    good = sound_recommendation()
    assert validate_recommendation(good, registry) == []

    bare = good.model_copy(update={"tradeoffs": [], "uncertainty": []})
    found = rules(validate_recommendation(bare, registry))
    assert "R6_no_tradeoff" in found
    assert "R7_no_uncertainty" in found


def test_recommendation_must_leave_the_human_in_charge(case):
    registry = FactRegistry.from_case(case)
    rec = sound_recommendation().model_copy(update={"human_decision_required": False})
    assert "R8_human_not_final" in rules(validate_recommendation(rec, registry))


# ── The registry must match the tree the agent was shown ────────────────────

def test_a_specialist_is_checked_against_its_own_projection(case, focus):
    """Every agent sees a different projection, and house rule 7 tells it to
    cite into that. Checking those citations against the whole case, or against
    the raw action, marks sound work unreferenced - and a wall of false
    violations hides the real ones."""
    from phase_c.agents.mission import MissionAgent
    from phase_c.agents.systems import SystemsAgent
    from phase_c.grounding.registry import FactRegistry

    mission = FactRegistry.from_payload(MissionAgent(None).project(focus, case))
    systems = FactRegistry.from_payload(SystemsAgent(None).project(focus, case))

    # Shapes only these projections have.
    assert mission.resolves("/capability_names_declared_by_scenario")
    assert systems.resolves("/equipment")

    # The case-wide tree resolves neither, which is what used to be used.
    whole_case = FactRegistry.from_case(case)
    assert not whole_case.resolves("/capability_names_declared_by_scenario")
    assert not whole_case.resolves("/equipment")


def test_an_empty_container_is_still_citable():
    """Phase B declares no systems, so `/systems` arrives empty. "No systems
    are declared" is a true statement about the data and the registry knows it
    (`/systems#count` is 0); requiring a child would reject exactly the claims
    that report an absence."""
    from phase_c.grounding.registry import FactRegistry

    registry = FactRegistry.from_payload(
        {"systems": {}, "system_reasons": {}, "crew": {"c1": {"state": "SAFE"}}}
    )

    assert registry.resolves("/systems")
    assert registry.resolves("/system_reasons")
    assert registry.resolves("/crew")
    assert not registry.resolves("/systems_typo")


def test_a_container_with_children_resolves(focus):
    from phase_c.grounding.registry import FactRegistry

    registry = FactRegistry.from_action(focus)
    assert registry.resolves("/hazard/reached_modules")
    assert registry.resolves("/hazard")


def test_an_invented_pointer_still_fails(focus):
    """The loosening must not make fabrication citable."""
    from phase_c.grounding.registry import FactRegistry

    registry = FactRegistry.from_action(focus)
    assert not registry.resolves("/hazard/made_up_field")
    assert not registry.resolves("/crew/nobody/state")
    assert not registry.resolves("/totally/invented")
    # A near-miss on a real key is still a miss.
    assert not registry.resolves("/hazard/sm_ac_exceeded_modules")
