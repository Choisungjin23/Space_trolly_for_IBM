"""The human-preservation policy is code, not an LLM preference."""

from phase_c.contracts.analysis import CrewCriticality
from phase_c.ethics import EthicsEvaluator


def _action(
    template,
    action_id: str,
    *,
    returnees: float,
    survivors: float,
    survival_probabilities: list[float] | None = None,
    capabilities: dict | None = None,
):
    crew = {}
    source_crew = list(template.crew.items())
    probabilities = survival_probabilities or [1.0] * len(source_crew)
    for (crew_id, member), probability in zip(source_crew, probabilities):
        crew[crew_id] = member.model_copy(
            update={
                "survival_probability": probability,
                "abandoned": False,
                "smac_dose_fraction": 0.0,
                "state": "SAFE",
            },
            deep=True,
        )
    return template.model_copy(
        update={
            "action": template.action.model_copy(
                update={"id": action_id, "label": action_id}, deep=True
            ),
            "expected_returnees": returnees,
            "expected_survivors": survivors,
            "crew": crew,
            "capabilities": capabilities or template.capabilities,
            "hazard": template.hazard.model_copy(
                update={"reached_modules": [], "smac_exceeded_modules": []},
                deep=True,
            ),
        },
        deep=True,
    )


def test_committed_fixture_selects_the_lowest_human_exposure_action(case):
    result = EthicsEvaluator().evaluate(case)

    assert result.status == "POLICY_CONSISTENT"
    assert result.selected_action_id == "isolate:M2"
    assert result.co_recommended_action_ids == ["isolate:M2"]


def test_equal_returnees_prefers_more_survivors(case):
    base = case.actions[0]
    fewer = _action(base, "fewer", returnees=3.0, survivors=3.0)
    more = _action(base, "more", returnees=3.0, survivors=4.0)

    result = EthicsEvaluator().evaluate(case.model_copy(update={"actions": [fewer, more]}))

    assert result.selected_action_id == "more"
    assert result.tie_break_steps[-1].criterion == "expected_survivors"


def test_equal_totals_improve_the_worst_off_crew_member(case):
    base = case.actions[0]
    unequal = _action(
        base,
        "unequal",
        returnees=3.0,
        survivors=3.0,
        survival_probabilities=[0.4, 1.0, 1.0, 1.0],
    )
    safer_floor = _action(
        base,
        "safer_floor",
        returnees=3.0,
        survivors=3.0,
        survival_probabilities=[0.6, 0.8, 1.0, 1.0],
    )

    result = EthicsEvaluator().evaluate(
        case.model_copy(update={"actions": [unequal, safer_floor]})
    )

    assert result.selected_action_id == "safer_floor"
    assert result.tie_break_steps[-1].criterion == "minimum_crew_survival_probability"


def test_mission_capability_cannot_compensate_for_fewer_survivors(case):
    base = case.actions[0]
    humans_first = _action(
        base,
        "humans_first",
        returnees=3.0,
        survivors=4.0,
        capabilities={"RETURN": "UNAVAILABLE"},
    )
    mission_first = _action(
        base,
        "mission_first",
        returnees=3.0,
        survivors=3.0,
        capabilities={"RETURN": "AVAILABLE", "HABITATION": "AVAILABLE"},
    )

    result = EthicsEvaluator().evaluate(
        case.model_copy(update={"actions": [mission_first, humans_first]})
    )

    assert result.selected_action_id == "humans_first"


def test_role_and_criticality_weights_do_not_change_intrinsic_life_value(case):
    original = EthicsEvaluator().evaluate(case)
    changed = case.model_copy(
        update={
            "criticality": [
                CrewCriticality(
                    crew_id=item.crew_id,
                    role=f"renamed_{index}",
                    measured_score=999.0 - index,
                    assumed_weight=999.0 - index,
                )
                for index, item in enumerate(case.criticality)
            ]
        },
        deep=True,
    )

    assert EthicsEvaluator().evaluate(changed).selected_action_id == original.selected_action_id


def test_unresolved_tie_is_exposed_instead_of_claiming_false_precision(case):
    base = case.actions[0]
    a = _action(base, "a", returnees=4.0, survivors=4.0)
    b = _action(base, "b", returnees=4.0, survivors=4.0)

    result = EthicsEvaluator().evaluate(case.model_copy(update={"actions": [b, a]}))

    assert result.status == "REVIEW_REQUIRED"
    assert result.co_recommended_action_ids == ["a", "b"]
    assert "human review" in result.selection_basis


def test_policy_sources_are_versioned_and_checkable(case):
    result = EthicsEvaluator().evaluate(case)

    assert result.policy_id.startswith("ASSUMED_")
    assert result.policy_version == "1.0.0"
    assert {source.source_id for source in result.sources} == {
        "PROJECT-HUMAN-PRESERVATION-POLICY-V1",
        "NASA-STD-3001-V1",
        "NIST-AI-100-1",
    }
    assert all(source.locator for source in result.sources)


def test_llm_context_keeps_the_decision_but_not_the_repeated_action_table(case):
    result = EthicsEvaluator().evaluate(case)
    context = result.decision_context()

    assert context["selected_action_id"] == result.selected_action_id
    assert context["selected_action_assessment"]["action_id"] == result.selected_action_id
    assert "action_assessments" not in context
