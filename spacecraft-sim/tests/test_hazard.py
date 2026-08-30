import pytest

from spacecraft_sim import config
from spacecraft_sim.hazard import step_hazard
from spacecraft_sim.models import Module
from spacecraft_sim.profiles import (
    get_mass_loss_rate_mg_s,
    get_species_emission_mg_s,
    is_extinguished,
)
from tests.conftest import make_line_scenario


def run_steps(scenario, steps=40, dt=30.0):
    t = 0.0
    for _ in range(steps):
        step_hazard(scenario, t, dt)
        t += dt
    return scenario


def soot(scenario, mid):
    return scenario.module(mid).concentration("soot")


# ── Transport blocking ───────────────────────────────────────────────────────

def test_closed_hatch_blocks_transport():
    scenario = make_line_scenario(fire_in="A1", path_state="closed")
    run_steps(scenario)
    assert soot(scenario, "A1") > 0
    assert soot(scenario, "A2") == 0.0


def test_ventilation_off_blocks_imv_transport():
    scenario = make_line_scenario(fire_in="A1", connection_type="imv", ventilation="off")
    run_steps(scenario)
    assert soot(scenario, "A2") == 0.0


def test_open_imv_transports_along_airflow():
    scenario = make_line_scenario(fire_in="A1", connection_type="imv", ventilation="on")
    run_steps(scenario)
    assert soot(scenario, "A2") > 0


def test_isolated_module_neither_sends_nor_receives():
    scenario = make_line_scenario(fire_in="A1")
    scenario.module("A1").isolated = True
    run_steps(scenario)
    assert soot(scenario, "A2") == 0.0


def test_zero_flow_blocks_transport():
    scenario = make_line_scenario(fire_in="A1", flow_m3_s=0.0)
    run_steps(scenario)
    assert soot(scenario, "A2") == 0.0


# ── Real-unit behaviour ──────────────────────────────────────────────────────

def test_higher_flow_moves_more_smoke():
    loads = {}
    for flow in (0.005, 0.02, 0.0708):
        scenario = make_line_scenario(fire_in="A1", flow_m3_s=flow)
        run_steps(scenario, steps=20)
        loads[flow] = soot(scenario, "A2")
    assert loads[0.005] < loads[0.02] < loads[0.0708]


def test_smaller_module_reaches_higher_concentration():
    small = make_line_scenario(fire_in="A1", volume_m3=20.0)
    large = make_line_scenario(fire_in="A1", volume_m3=200.0)
    run_steps(small, steps=20)
    run_steps(large, steps=20)
    assert soot(small, "A1") > soot(large, "A1")


def test_smoke_propagates_multi_hop():
    # The (C_i - C_j) exchange term means a smoke-filled module becomes a source
    # for its own neighbours, so A3 fills even though only A1 is burning.
    scenario = make_line_scenario(n_modules=3, fire_in="A1")
    run_steps(scenario, steps=60)
    assert soot(scenario, "A3") > 0


def test_concentrations_never_go_negative():
    scenario = make_line_scenario(n_modules=4, fire_in="A2")
    run_steps(scenario, steps=200)
    for module in scenario.modules:
        for species in config.TRACKED_SPECIES:
            assert module.concentration(species) >= 0.0
        assert module.temperature_c >= config.ASSUMED_AMBIENT_TEMPERATURE_C


def test_extinction_derives_from_soot():
    module = Module(id="X", name="X")
    module.species_mg_m3["soot"] = 1000.0  # 1 g/m^3
    assert module.extinction_per_m == pytest.approx(
        config.VERIFIED_MASS_EXTINCTION_M2_PER_G
    )


def test_smac_fraction_uses_verified_limits():
    module = Module(id="X", name="X")
    module.species_mg_m3["CO"] = config.VERIFIED_SMAC_1H_MG_M3["CO"]
    assert module.smac_fraction("CO") == pytest.approx(1.0)
    assert module.worst_smac_fraction == pytest.approx(1.0)


# ── Source profiles ──────────────────────────────────────────────────────────

def test_source_profiles_produce_different_mass_loss_curves():
    curves = {}
    for profile in ("STEADY_FABRIC_SPREAD", "GRADUAL_PMMA_GROWTH", "LIMITED_FLAME"):
        module = Module(
            id="X", name="X", fire_state="sustained", source_profile_id=profile
        )
        curves[profile] = [get_mass_loss_rate_mg_s(module, t) for t in (0, 120, 300)]
    assert curves["STEADY_FABRIC_SPREAD"] != curves["GRADUAL_PMMA_GROWTH"]
    assert curves["LIMITED_FLAME"][0] < curves["STEADY_FABRIC_SPREAD"][0]


def test_fabric_profile_matches_its_documented_derivation():
    # 18.0 mg/cm^2 (verified) x 0.1 cm/s x 40 cm (assumed) = 72 mg/s
    expected = (
        config.VERIFIED_SIBAL_AREA_DENSITY_MG_CM2
        * config.ASSUMED_FABRIC_SPREAD_RATE_CM_S
        * config.ASSUMED_FABRIC_BURN_WIDTH_CM
    )
    assert config.SOURCE_PROFILES["STEADY_FABRIC_SPREAD"]["mass_loss_rate_mg_s"] == (
        pytest.approx(expected)
    )


def test_species_emission_is_yield_times_fuel():
    module = Module(
        id="X", name="X", fire_state="sustained", source_profile_id="STEADY_FABRIC_SPREAD"
    )
    fuel = get_mass_loss_rate_mg_s(module, 0)
    emission = get_species_emission_mg_s(module, 0)
    yields = config.SOURCE_PROFILES["STEADY_FABRIC_SPREAD"]["yields"]
    assert emission["CO"] == pytest.approx(fuel * yields["CO"])


def test_yields_are_per_profile_not_global():
    """What a fire emits depends on what is burning."""
    cellulose = config.SOURCE_PROFILES["STEADY_FABRIC_SPREAD"]["yields"]
    foam = config.SOURCE_PROFILES["NITROGEN_RICH_FOAM"]["yields"]
    assert cellulose["soot"] != foam["soot"]
    assert cellulose["CO"] != foam["CO"]


def test_nitrogen_free_fuels_emit_no_hcn():
    """Cellulose and PMMA contain no nitrogen, so HCN is stoichiometrically
    impossible - that zero is chemistry, not an assumption."""
    for profile_id in ("STEADY_FABRIC_SPREAD", "GRADUAL_PMMA_GROWTH", "LIMITED_FLAME"):
        assert config.SOURCE_PROFILES[profile_id]["yields"]["HCN"] == 0.0
    assert config.SOURCE_PROFILES["NITROGEN_RICH_FOAM"]["yields"]["HCN"] > 0.0


def test_co_yield_follows_the_koylu_faeth_correlation():
    """CO is derived from soot via the NIST-published correlation, not guessed."""
    expected = config.koylu_faeth_co_yield(
        6.0, 162.14, config.ASSUMED_SOOT_YIELD_CELLULOSE
    )
    assert config.SOURCE_PROFILES["STEADY_FABRIC_SPREAD"]["yields"]["CO"] == (
        pytest.approx(expected)
    )
    # Sanity: well-ventilated cellulose CO yield is a few thousandths of a
    # gram per gram, not the 0.05 the model guessed before calibration.
    assert 0.001 < expected < 0.01


def test_extinction_candidate_ramps_to_zero():
    module = Module(
        id="X",
        name="X",
        fire_state="sustained",
        source_profile_id="FLOW_SHUTDOWN_EXTINCTION_CANDIDATE",
    )
    assert get_mass_loss_rate_mg_s(module, 0) > 0
    assert get_mass_loss_rate_mg_s(module, 600) == 0.0
    assert is_extinguished(module, 600)


def test_suppressed_and_non_states_emit_nothing():
    for state in ("non", "suppressed"):
        module = Module(
            id="X", name="X", fire_state=state, source_profile_id="STEADY_FABRIC_SPREAD"
        )
        assert get_mass_loss_rate_mg_s(module, 100) == 0.0
