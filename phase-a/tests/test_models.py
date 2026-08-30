import pytest

import spacecraft_sim.config as config
from spacecraft_sim.engine import simulate
from tests.conftest import make_line_scenario


def test_demo_scenario_loads_and_validates(demo):
    assert len(demo.modules) == 5
    assert len(demo.crew) == 4
    assert demo.module("M2").fire_state == "sustained"
    assert demo.capabilities["RETURN"] == ["power", "propulsion", "gnc"]


def test_demo_uses_real_iss_scale_volumes(demo):
    # Destiny-class lab ~105 m^3, Node-class ~70 m^3.
    assert demo.module("M1").volume_m3 == 105.0
    assert demo.module("M4").volume_m3 == 70.0


def test_demo_imv_uses_verified_flow(demo):
    assert demo.connection("c_m2_m3").nominal_flow_m3_s() == pytest.approx(
        config.VERIFIED_IMV_FLOW_M3_S
    )


def test_connection_flow_defaults_by_type():
    from spacecraft_sim.models import Connection

    imv = Connection(id="a", source="X", target="Y", type="imv")
    hatch = Connection(id="b", source="X", target="Y", type="hatch")
    leak = Connection(id="c", source="X", target="Y", type="leak")
    assert imv.nominal_flow_m3_s() == config.VERIFIED_IMV_FLOW_M3_S
    assert hatch.nominal_flow_m3_s() == config.ASSUMED_HATCH_EXCHANGE_M3_S
    assert leak.nominal_flow_m3_s() == config.ASSUMED_LEAK_EXCHANGE_M3_S


def test_engine_is_size_agnostic():
    for n in (3, 12):
        scenario = make_line_scenario(n_modules=n, fire_in="A2")
        result = simulate(scenario, horizon=300, dt=30)
        assert result.final is not None
        assert len(result.final.modules) == n


def test_no_single_severity_scalar(demo):
    assert not hasattr(demo.module("M2"), "fire_severity")
    assert not hasattr(demo.module("M2"), "smoke_gas_load")


@pytest.mark.parametrize(
    "banned",
    [
        "PROPAGATION_FACTOR",
        "CREW_FATALITY_FACTOR",
        "GROWTH_RATE",
        "GENERIC_SPREAD_PROBABILITY",
        "SYSTEM_FAILURE_PROB",
        "CONNECTION_HAZARD_PROBABILITY",
        "TRANSFER_PROXY",
    ],
)
def test_banned_constants_absent_from_config(banned):
    # The design brief discards constants that cannot be calibrated from
    # evidence; they must not exist in the engine's config.
    assert not hasattr(config, banned)


def test_every_tunable_constant_declares_its_provenance():
    """Constants must be VERIFIED_* or ASSUMED_*, or be on the allowed list of
    plain settings / structures that carry their own per-entry comments."""
    allowed = {
        "SOURCES",
        "TRACKED_SPECIES",
        "SOURCE_PROFILES",
        "GROWTH_TIME_REFERENCE_SECONDS",
        "ROLE_FUNCTIONS",
        # A crew-function name, like ROLE_FUNCTIONS above - vocabulary rather
        # than a calibrated quantity, so there is nothing to source or assume.
        "DEFAULT_REPAIR_FUNCTION",
        "DT_SECONDS",
        "HORIZON_SECONDS",
        "MONTECARLO_SAMPLES",
        "ETHICS_NOTICE",
    }
    for name, value in vars(config).items():
        if name.startswith("_") or name in allowed:
            continue
        if not isinstance(value, (int, float, str, dict, tuple, list)):
            continue
        assert name.startswith(("VERIFIED_", "ASSUMED_")), (
            f"{name} declares no provenance; prefix it VERIFIED_ or ASSUMED_"
        )


def test_verified_smac_values_match_jsc_20584_rev_c():
    # 1-hour SMACs read from the primary source: CO 425 ppm (485 mg/m^3),
    # HCN 8 ppm (9 mg/m^3), HCl 5 ppm (8 mg/m^3).
    assert config.VERIFIED_SMAC_1H_MG_M3 == {"CO": 485.0, "HCN": 9.0, "HCl": 8.0}
    # HCN is the binding constraint in a fire, not CO.
    assert config.VERIFIED_SMAC_1H_MG_M3["HCN"] < config.VERIFIED_SMAC_1H_MG_M3["CO"]


def test_detector_threshold_matches_one_percent_per_foot():
    import math

    expected = -math.log(0.99) / 0.3048  # 1 %/ft obscuration -> 1/m
    assert config.VERIFIED_DETECTOR_ALARM_EXTINCTION_PER_M == pytest.approx(
        expected, abs=5e-4
    )


def test_provenance_notice_present():
    assert "VERIFIED_" in config.ETHICS_NOTICE
    assert "ASSUMED_" in config.ETHICS_NOTICE
    assert "not a valuation of lives" in config.ETHICS_NOTICE
    assert "SMAC" in config.SOURCES and "JSC 20584" in config.SOURCES["SMAC"]


# ── FMECA-derived crew criticality (MIL-STD-1629A) ──────────────────────────

def test_severity_categories_are_quoted_from_the_standard():
    cats = config.VERIFIED_MIL_STD_1629A_SEVERITY
    assert set(cats) == {"I", "II", "III", "IV"}
    assert cats["I"].startswith("Catastrophic")
    assert "mission loss" in cats["II"]
    assert cats["IV"].startswith("Minor")


def test_every_function_has_a_fmeca_worksheet_row():
    """A FMECA worksheet needs the failure EFFECT that drives the category,
    not just the category letter."""
    known = {f for funcs in config.ROLE_FUNCTIONS.values() for f in funcs}
    worksheet = config.ASSUMED_FUNCTION_SEVERITY_CATEGORY
    assert known <= set(worksheet)
    for function, row in worksheet.items():
        assert row["category"] in config.VERIFIED_MIL_STD_1629A_SEVERITY
        assert len(row["effect"]) > 40, function


def test_criticality_is_derived_from_severity_not_hand_written():
    for function, row in config.ASSUMED_FUNCTION_SEVERITY_CATEGORY.items():
        expected = config.ASSUMED_SEVERITY_CRITICALITY[row["category"]]
        assert config.ASSUMED_FUNCTION_CRITICALITY[function] == expected


def test_life_critical_functions_outrank_mission_and_science():
    crit = config.ASSUMED_FUNCTION_CRITICALITY
    # Category I (loss of life) must outrank Category II (mission loss),
    # which must outrank Category IV (science only).
    assert crit["life_support_ops"] > crit["propulsion_ops"] > crit["science"]
    assert crit["power_ops"] == crit["life_support_ops"]  # both Category I


def test_combustion_yields_carry_their_derivation():
    # The correlation is verified; the soot yields it consumes are assumed.
    assert config.VERIFIED_KOYLU_FAETH_SLOPE == 0.37
    assert config.VERIFIED_MASS_EXTINCTION_M2_PER_G == 7.6
    for profile_id, profile in config.SOURCE_PROFILES.items():
        assert "yields" in profile, profile_id
        assert set(profile["yields"]) >= set(config.TRACKED_SPECIES), profile_id


def test_crew_move_time_is_derived_from_distance_and_speed():
    expected = round(
        config.ASSUMED_MODULE_TRAVERSE_LENGTH_M
        / config.ASSUMED_CREW_TRANSLATION_SPEED_M_S
        + config.ASSUMED_HATCH_TRANSIT_SECONDS
    )
    assert config.ASSUMED_CREW_MOVE_SECONDS_PER_HOP == expected
    assert 20 <= config.ASSUMED_CREW_MOVE_SECONDS_PER_HOP <= 90
