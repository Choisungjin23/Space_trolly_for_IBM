"""The adapter must close every gap in phase-a-contract.md §8, and the fixture
it produces is real Phase A output — so these assertions test the normalization,
not a hand-written mock."""

from pathlib import Path

import pytest

from phase_c.contracts.analysis import CaseAnalysis

FIXTURE = Path(__file__).parent / "fixtures" / "demo_case.json"


def test_fixture_is_a_valid_case_analysis():
    case = CaseAnalysis.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    assert case.actions
    assert case.scenario_digest


def test_action_ids_are_opaque_and_not_hardcoded(case):
    ids = [a.action.id for a in case.actions]
    assert "do_nothing" in ids
    # Ids encode their target; the adapter must not have rewritten them.
    assert any(i.startswith("isolate:") for i in ids)
    assert all(isinstance(i, str) for i in ids)


def test_gap4_equipment_is_present(case):
    """Equipment lives only on TimelineResult.final — summary has no such key."""
    analysis = case.action("do_nothing")
    assert analysis.equipment
    item = next(iter(analysis.equipment.values()))
    assert item.module and item.system
    assert isinstance(item.damaged, bool) and isinstance(item.powered, bool)


def test_gap5_timeline_replaced_by_events(case):
    """120 frames must not survive into the agent-facing contract."""
    analysis = case.action("do_nothing")
    assert analysis.events
    assert len(analysis.events) < 120
    assert all(hasattr(e, "type") and hasattr(e, "t") for e in analysis.events)


def test_gap6_capabilities_passed_through_without_hardcoding(case):
    analysis = case.action("do_nothing")
    # Whatever the scenario declared, in the same keys.
    assert set(analysis.capabilities) == set(case.capability_names)


def test_gap7_capability_counts_are_gated_on_declaration(case):
    """Fixed Distribution fields must not become vacuous n/n claims."""
    analysis = case.action("do_nothing")
    assert analysis.sampled is not None
    for name, count in analysis.sampled.capability_counts.items():
        assert count.applicable is (name in case.capability_names)


def test_gap7_custom_capability_names_are_preserved(monkeypatch):
    """The adapter must not turn scenario-defined names back into literals."""
    from types import SimpleNamespace

    from phase_c.providers import phase_a as adapter_module
    from phase_c.providers.phase_a import PhaseASimulationAdapter

    distribution = SimpleNamespace(
        samples=2,
        return_available=2,
        habitation_available=2,
        mean_total_exposure_seconds=0.0,
        mean_peak_smac_dose=0.0,
        mean_expected_survivors=2.0,
        mean_expected_returnees=2.0,
        notes=[],
        hazard_contained_to_sources=2,
        no_crew_trapped=2,
        all_crew_safe_or_evacuated=2,
        no_crew_reached_smac_dose=2,
        retained_evacuation_and_return=2,
    )
    monkeypatch.setattr(adapter_module, "run_montecarlo", lambda *a, **k: distribution)

    scenario = SimpleNamespace(
        return_capability_name="EARTH_RETURN",
        habitation_capability_name="SAFE_HAVEN",
        model_copy=lambda deep: None,
    )
    sampled = PhaseASimulationAdapter()._sample(
        scenario,
        object(),
        2,
        42,
        {"EARTH_RETURN": "AVAILABLE"},
    )

    assert set(sampled.capability_counts) == {"EARTH_RETURN", "SAFE_HAVEN"}
    assert sampled.capability_counts["EARTH_RETURN"].applicable is True
    assert sampled.capability_counts["SAFE_HAVEN"].applicable is False


def test_gap8_detection_null_is_first_class(case):
    analysis = case.action("do_nothing")
    assert analysis.detection.status in ("DETECTED", "NEVER_DETECTED")
    if analysis.detection.status == "NEVER_DETECTED":
        assert analysis.detection.detected_at_seconds is None
    else:
        assert analysis.detection.detected_at_seconds is not None


def test_sampled_counts_never_exceed_sample_size(case):
    for analysis in case.actions:
        if not analysis.sampled:
            continue
        n = analysis.sampled.samples
        for name, value in analysis.sampled.counts.items():
            assert 0 <= value <= n, name


def test_provenance_records_engine_and_notice(case):
    provenance = case.action("do_nothing").provenance
    assert provenance.engine.startswith("spacecraft_sim")
    assert "ASSUMED_" in provenance.ethics_notice
    assert provenance.downsampled is False


def test_mock_provider_filters_actions(provider):
    subset = provider.analyze_case(action_ids=["do_nothing"])
    assert [a.action.id for a in subset.actions] == ["do_nothing"]
    with pytest.raises(KeyError):
        provider.analyze_case(action_ids=["not-an-action"])


def test_phase_a_is_imported_in_exactly_one_module():
    """Agents must never reach into the engine (contract §8, closing note).

    Checked by AST rather than substring: a module may legitimately *mention*
    the engine in a docstring or a version label without importing it.
    """
    import ast

    src = Path(__file__).resolve().parents[1] / "src" / "phase_c"
    offenders = []
    for path in sorted(src.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name.split(".")[0] == "spacecraft_sim" for name in names):
                offenders.append(path.relative_to(src).as_posix())
                break
    assert offenders == ["providers/phase_a.py"], offenders
