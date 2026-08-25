"""All tunable constants for the Phase A engine, in one file, in REAL UNITS.

======================== PROVENANCE / VALIDITY NOTICE =========================
Constants here fall into exactly two classes, and the names say which:

  VERIFIED_*  read directly from a primary source (see SOURCES below).
  ASSUMED_*   a configurable PoC assumption. NOT validated. Replace when data
              becomes available.

Anything without a prefix is either a plain simulation setting (time step,
sample count), a derived value computed from the above, or a structure that
mixes both, in which case each entry carries its own comment.

Combustion chemistry note: ISS cabin atmosphere is essentially sea-level air
(101.3 kPa, 21% O2), so ground-based well-ventilated combustion yields are a
defensible starting point for *what* a fire emits. What does NOT transfer from
the ground is how fast a fire spreads: Saffire measured microgravity pyrolysis
spread 18-24x slower than 1g while fuel burnout was only 1.6-3x slower. So this
model takes yields from ground fire science and spread behaviour from Saffire.

Ethics: the crew criticality tables are a FMECA function-criticality model
following MIL-STD-1629A severity classification. They express "how
irreplaceable is this FUNCTION right now", never "how much is this person's
life worth". The severity *categories* are quoted from the standard; assigning
our functions to those categories is our own analysis, not a NASA ruling.

Deliberately absent (impossible to calibrate from evidence, per the design
brief): PROPAGATION_FACTOR, generic spread probabilities, CREW_FATALITY_FACTOR /
P(death), generic system failure probabilities, and a global fire GROWTH_RATE.
The engine tracks states, concentrations and exposure instead of inventing
survival odds.
===============================================================================
"""

SOURCES: dict[str, str] = {
    "SMAC": "JSC 20584 Rev C, Spacecraft Maximum Allowable Concentrations for "
            "Airborne Contaminants, NASA JSC, 2024-06-13.",
    "IMV": "Inter-Module Ventilation Changes to the ISS Vehicle, NTRS 20150009509 "
           "(IMV fan 140-150 cfm; 4.25 m^3/min at 150 cfm).",
    "SAFFIRE_II": "Analysis of Saffire II two-sided concurrent flame spread "
                  "(microgravity PMMA pyrolysis front 0.05-0.06 mm/s, burnout "
                  "0.014-0.05 mm/s; forced flow 200 mm/s typical of ISS).",
    "SAFFIRE_I": "Operation and Development Status of the Spacecraft Fire "
                 "Experiment, NTRS 20170002628 (SIBAL fabric 75% cotton / 25% "
                 "fiberglass, area density 18.0 mg/cm^2).",
    "DETECTOR": "Overview of ISS US Fire Detection, NTRS 20030053429 "
                "(laser scatter/obscuration detectors on ventilation intake "
                "ducts; alarm requires the threshold be exceeded twice).",
    "MODULE_VOLUME": "ISS module pressurized volumes: Destiny ~105 m^3, "
                     "Unity ~71 m^3, Harmony ~70 m^3. Destiny length ~8.5 m.",
    "FDS": "NISTIR 6784, Fire Dynamics Simulator (Version 2) User's Guide, NIST. "
           "Koylu-Faeth CO/soot correlation for well-ventilated fires; default "
           "mass extinction coefficient 7600 m^2/kg for flaming combustion of "
           "wood and plastics; WOOD reference reaction SOOT_YIELD 0.01.",
    "PU_HCN": "Fire toxicity of polyurethane foams / Toxicity Assessment of "
              "Products of Combustion of Flexible Polyurethane Foam (IAFSS). "
              "Rigid PU HCN yield 15.8 mg/g at 600 C, 7.4 mg/g at 800 C, rising "
              "to 33.9 mg/g at 1000 C. Well-ventilated flaming gives the low end.",
    "FMECA": "MIL-STD-1629A, Procedures for Performing a Failure Mode, Effects "
             "and Criticality Analysis, para 4.4.3 severity classification. "
             "NASA reliability requirements: NASA-STD-8729.1A. (Note: "
             "NASA-STD-8719.13 is the Software Safety Standard, cancelled "
             "2020-06-10, and is NOT a FMECA reference.)",
}


# ── Toxicology thresholds ────────────────────────────────────────────────────
# VERIFIED: JSC 20584 Rev C. Values in mg/m^3 (the document also lists ppm).
# The 1-hour and 24-hour limits are the contingency limits the document itself
# designates for off-nominal situations, which is what a fire is.
VERIFIED_SMAC_1H_MG_M3: dict[str, float] = {
    "CO": 485.0,    # 425 ppm
    "HCN": 9.0,     # 8 ppm  -- 54x more restrictive than CO
    "HCl": 8.0,     # 5 ppm
}
VERIFIED_SMAC_24H_MG_M3: dict[str, float] = {
    "CO": 114.0,    # 100 ppm
    "HCN": 4.5,     # 4 ppm
    "HCl": 3.0,     # 2 ppm
}

# Species the engine transports. "soot" carries no SMAC; it drives obscuration.
TRACKED_SPECIES: tuple[str, ...] = ("CO", "HCN", "soot")


# ── Ventilation and transport ────────────────────────────────────────────────
# VERIFIED: IMV fan rated 150 cfm = 4.25 m^3/min.
VERIFIED_IMV_FLOW_M3_S = 0.0708

# ASSUMED: passive exchange through an open hatch with no forced flow, and
# through an unsealed leak path. No public figure found; sized well below IMV.
ASSUMED_HATCH_EXCHANGE_M3_S = 0.010
ASSUMED_LEAK_EXCHANGE_M3_S = 0.003

# ASSUMED: air-scrubbing removal (ARS/CDRA and filters) as a volumetric rate.
# Real removal is species-specific and was not found in public sources; this is
# an additive term alongside the physical ventilation exchange.
ASSUMED_SCRUB_FLOW_M3_S = 0.020

# ASSUMED: default module free volume when a scenario does not state one.
# Sized between the ISS Node (~70 m^3) and Lab (~105 m^3) figures.
ASSUMED_DEFAULT_MODULE_VOLUME_M3 = 90.0


# ── Combustion product yields ────────────────────────────────────────────────
# VERIFIED (NISTIR 6784): for well-ventilated fires FDS derives the CO yield
# from the soot yield via the Koylu-Faeth correlation
#
#     y_CO = (12 x / (M_f nu_f)) * (0.0014 + 0.37 y_soot)
#
# where x is the carbon count of the fuel molecule, M_f its molecular weight,
# and nu_f the fuel's stoichiometric coefficient (1 for a per-mole-fuel
# reaction). This replaces the flat guessed CO yield the model used before.
VERIFIED_KOYLU_FAETH_INTERCEPT = 0.0014
VERIFIED_KOYLU_FAETH_SLOPE = 0.37


def koylu_faeth_co_yield(carbon_count: float, fuel_mw: float, soot_yield: float) -> float:
    """CO yield (mg per mg fuel) for a well-ventilated fire. See SOURCES['FDS']."""
    return (12.0 * carbon_count / fuel_mw) * (
        VERIFIED_KOYLU_FAETH_INTERCEPT + VERIFIED_KOYLU_FAETH_SLOPE * soot_yield
    )


# ASSUMED soot yields, chosen from the fire-science range NIST cites (the FDS
# WOOD reference reaction uses 0.01; PMMA is commonly modelled near 0.022;
# flexible PU foam is markedly sootier).
ASSUMED_SOOT_YIELD_CELLULOSE = 0.015
ASSUMED_SOOT_YIELD_PMMA = 0.022
ASSUMED_SOOT_YIELD_PU_FOAM = 0.05

# VERIFIED (IAFSS PU studies): HCN yield of a nitrogen-bearing polymer under
# well-ventilated flaming, taken at the 800 C figure (7.4 mg/g).
VERIFIED_PU_FOAM_HCN_YIELD = 0.0074

# ASSUMED: PU foam CO yield. The Koylu-Faeth correlation is calibrated on
# well-ventilated hydrocarbon-type fuels, so it is not applied to PU here.
ASSUMED_PU_FOAM_CO_YIELD = 0.02

# Fuel chemistry. Cellulose (cotton) and PMMA contain NO nitrogen, so they
# cannot produce HCN — that zero is stoichiometry, not an assumption.
VERIFIED_FUEL_CHEMISTRY: dict[str, dict[str, float]] = {
    # formula, carbon count, monomer molecular weight (g/mol)
    "cellulose": {"carbon_count": 6.0, "fuel_mw": 162.14, "nitrogen": 0.0},
    "pmma":      {"carbon_count": 5.0, "fuel_mw": 100.12, "nitrogen": 0.0},
}


# ── Fire source profiles ─────────────────────────────────────────────────────
# Primary quantity is the fuel mass loss rate in mg/s. Each profile also
# carries its own product yields, because what a fire emits depends on what is
# burning — a single global yield table was the previous model's weakest point.
#
# Derivation for thin fuels: m_dot = area_density x spread_rate x width.
#   SAFFIRE_I SIBAL fabric area density 18.0 mg/cm^2 is VERIFIED.
#   The spread rate and burning width are ASSUMED (Saffire-I's measured spread
#   rate was not obtainable; Saffire-II's 0.05-0.06 mm/s is for a thermally
#   thick PMMA slab and does not transfer to thin fabric).
VERIFIED_SIBAL_AREA_DENSITY_MG_CM2 = 18.0          # SAFFIRE_I
VERIFIED_SAFFIRE_II_PYROLYSIS_SPREAD_MM_S = 0.055  # microgravity, thick PMMA
VERIFIED_SAFFIRE_II_BURNOUT_MM_S = 0.03            # microgravity, thick PMMA
VERIFIED_ISS_TYPICAL_FLOW_MM_S = 200.0             # SAFFIRE_II

ASSUMED_FABRIC_SPREAD_RATE_CM_S = 0.1   # 1 mm/s over thin fabric
ASSUMED_FABRIC_BURN_WIDTH_CM = 40.0

_CELLULOSE_CO = koylu_faeth_co_yield(6.0, 162.14, ASSUMED_SOOT_YIELD_CELLULOSE)
_PMMA_CO = koylu_faeth_co_yield(5.0, 100.12, ASSUMED_SOOT_YIELD_PMMA)

SOURCE_PROFILES: dict[str, dict] = {
    "NON_SUSTAINING": {
        "mass_loss_rate_mg_s": 0.0,
        "growth_per_60s": 0.0,
        "yields": {"CO": 0.0, "HCN": 0.0, "soot": 0.0},
        "fuel": "none",
    },
    # 18.0 mg/cm^2 x 0.1 cm/s x 40 cm = 72 mg/s. Cotton = cellulose, no nitrogen.
    "STEADY_FABRIC_SPREAD": {
        "mass_loss_rate_mg_s": 72.0,
        "growth_per_60s": 0.0,
        "yields": {"CO": _CELLULOSE_CO, "HCN": 0.0, "soot": ASSUMED_SOOT_YIELD_CELLULOSE},
        "fuel": "cellulose",
    },
    "GRADUAL_PMMA_GROWTH": {
        "mass_loss_rate_mg_s": 50.0,
        "growth_per_60s": 0.15,
        "yields": {"CO": _PMMA_CO, "HCN": 0.0, "soot": ASSUMED_SOOT_YIELD_PMMA},
        "fuel": "pmma",
    },
    "LIMITED_FLAME": {
        "mass_loss_rate_mg_s": 15.0,
        "growth_per_60s": 0.02,
        "yields": {"CO": _CELLULOSE_CO, "HCN": 0.0, "soot": ASSUMED_SOOT_YIELD_CELLULOSE},
        "fuel": "cellulose",
    },
    "FLOW_SHUTDOWN_EXTINCTION_CANDIDATE": {
        "mass_loss_rate_mg_s": 40.0,
        "growth_per_60s": -0.20,
        "yields": {"CO": _CELLULOSE_CO, "HCN": 0.0, "soot": ASSUMED_SOOT_YIELD_CELLULOSE},
        "fuel": "cellulose",
    },
    # Nitrogen-bearing polymer (foam, upholstery, wire insulation). The only
    # profile that produces HCN, which is the species with the strictest SMAC.
    "NITROGEN_RICH_FOAM": {
        "mass_loss_rate_mg_s": 60.0,
        "growth_per_60s": 0.10,
        "yields": {
            "CO": ASSUMED_PU_FOAM_CO_YIELD,
            "HCN": VERIFIED_PU_FOAM_HCN_YIELD,
            "soot": ASSUMED_SOOT_YIELD_PU_FOAM,
        },
        "fuel": "pu_foam",
    },
    # Unknown material: the Monte Carlo samples a concrete profile in its place.
    "POC_UNKNOWN": {
        "mass_loss_rate_mg_s": 40.0,
        "growth_per_60s": 0.05,
        "yields": {"CO": _CELLULOSE_CO, "HCN": 0.0, "soot": ASSUMED_SOOT_YIELD_CELLULOSE},
        "fuel": "unknown",
    },
}

GROWTH_TIME_REFERENCE_SECONDS = 60.0

# ASSUMED: fraction of the full mass loss rate while a fire is still incipient.
ASSUMED_INCIPIENT_RELEASE_FRACTION = 0.3


# ── Obscuration / detection ──────────────────────────────────────────────────
# VERIFIED: ISS detectors alarm at ~1 %/ft obscuration. Converting to an
# extinction coefficient: T = exp(-sigma L); 1 % loss over 1 ft (0.3048 m)
# gives sigma = -ln(0.99)/0.3048 = 0.033 /m.
VERIFIED_DETECTOR_ALARM_EXTINCTION_PER_M = 0.033

# VERIFIED (NISTIR 6784): FDS default mass extinction coefficient, 7600 m^2/kg
# = 7.6 m^2/g, "a value suggested for flaming combustion of wood and plastics".
VERIFIED_MASS_EXTINCTION_M2_PER_G = 7.6

# ASSUMED: extinction at which smoke impairs egress (finding your way out),
# well above the detector alarm threshold.
ASSUMED_EGRESS_IMPAIR_EXTINCTION_PER_M = 0.5

# VERIFIED (logic, not timing): the alarm requires the threshold to be exceeded
# on two consecutive readings. ASSUMED: how long one reading cycle takes.
ASSUMED_DETECTOR_CONFIRM_SECONDS = 20.0

# ASSUMED: detectors sit on ventilation intake ducts, so with ventilation off
# smoke reaches them far more slowly. Multiplier on the confirmation time.
ASSUMED_UNVENTILATED_DETECTION_PENALTY = 6.0


# ── Thermal / equipment damage ───────────────────────────────────────────────
ASSUMED_AMBIENT_TEMPERATURE_C = 22.0
# Temperature rise per second per mg/s of fuel burned, in the burning module.
ASSUMED_THERMAL_RISE_C_PER_S_PER_MG_S = 0.004
ASSUMED_THERMAL_DECAY_PER_S = 0.002

# ASSUMED, bracketed by real electronics limits rather than picked freely:
# industrial-grade parts are rated to ~85 C operating, and eutectic tin-lead
# solder melts at ~183 C. Permanent damage is placed between the two, nearer
# the rating, since board-level plastics and adhesives fail well before solder.
ASSUMED_EQUIPMENT_DAMAGE_TEMPERATURE_C = 120.0

# ASSUMED: soot concentration at which *powered* electronics short out.
# Anchored to something observable: 200 mg/m^3 x 7.6 m^2/g = 1.52 /m extinction,
# roughly 3x the egress-impairment level and 46x the detector alarm. In other
# words equipment only shorts in smoke far too thick for a person to work in.
ASSUMED_EQUIPMENT_DAMAGE_SOOT_MG_M3 = 200.0


# ── Crew movement ────────────────────────────────────────────────────────────
# ASSUMED: pre-movement time (alarm heard -> movement begins). Fire-safety
# engineering treats this as the dominant term in egress time; trained,
# regularly drilled occupants with a clear alarm sit at the short end of the
# published categories. ISS crew drill emergencies routinely.
ASSUMED_CREW_RESPONSE_SECONDS_DEFAULT = 60.0

# ASSUMED, derived rather than picked: an ISS lab module is ~8.5 m end to end
# (SOURCES['MODULE_VOLUME']), and handrail translation in microgravity is
# deliberately slow. At ~0.25 m/s that is ~34 s, plus hatch transit and the
# turn at each end.
ASSUMED_CREW_TRANSLATION_SPEED_M_S = 0.25
ASSUMED_MODULE_TRAVERSE_LENGTH_M = 8.5
ASSUMED_HATCH_TRANSIT_SECONDS = 11.0
ASSUMED_CREW_MOVE_SECONDS_PER_HOP = round(
    ASSUMED_MODULE_TRAVERSE_LENGTH_M / ASSUMED_CREW_TRANSLATION_SPEED_M_S
    + ASSUMED_HATCH_TRANSIT_SECONDS
)


# ── Crew <-> system coupling ─────────────────────────────────────────────────
# Systems are not self-sufficient boxes: someone has to operate them, and
# someone has to repair them. Which function does which is declared per system
# in the scenario (System.operator_function / System.repair_function).
#
# ASSUMED: how long a crew member providing the repair function needs, on site
# and in a non-hazardous module, to restore one damaged piece of equipment.
ASSUMED_REPAIR_SECONDS = 900.0

# ASSUMED: crew states in which a crew member can actually do work. Evacuating
# or trapped crew are not operating or repairing anything.
ASSUMED_WORKING_CREW_STATES: tuple[str, ...] = ("SAFE", "EXPOSED")


# ── Crew criticality: FMECA severity classification ──────────────────────────
# VERIFIED: severity categories quoted from MIL-STD-1629A para 4.4.3.
VERIFIED_MIL_STD_1629A_SEVERITY: dict[str, str] = {
    "I": "Catastrophic - A failure which may cause death or weapon system loss.",
    "II": "Critical - A failure which may cause severe injury, major property "
          "damage, or major system damage which will result in mission loss.",
    "III": "Marginal - A failure which may cause minor injury, minor property "
           "damage, or minor system damage which will result in delay or loss "
           "of availability or mission degradation.",
    "IV": "Minor - A failure not serious enough to cause injury, property "
          "damage, or system damage, but which will result in unscheduled "
          "maintenance or repair.",
}

# ASSUMED: our own FMECA worksheet. The methodology and the categories are from
# the standard; assigning each function to a category is our analysis, and a
# real programme would review it. `effect` is the failure effect that drives the
# classification — the column a FMECA worksheet actually requires.
ASSUMED_FUNCTION_SEVERITY_CATEGORY: dict[str, dict[str, str]] = {
    "life_support_ops": {
        "category": "I",
        "effect": "Cabin atmosphere unmanaged; CO2 and O2 drift out of limits "
                  "with no one able to intervene. Directly life-threatening.",
    },
    "power_ops": {
        "category": "I",
        "effect": "Electrical power unmanaged; life support, thermal control "
                  "and GNC all depend on it, so the loss cascades to vehicle "
                  "loss rather than stopping at one system.",
    },
    "command_decision": {
        "category": "II",
        "effect": "No authority to commit the crew to a coordinated response. "
                  "Individuals can still act, so this degrades the response "
                  "rather than ending it, but mission loss is plausible.",
    },
    "repair": {
        "category": "II",
        "effect": "Damaged equipment stays damaged for the rest of the mission. "
                  "Severity depends on what broke; mission loss is plausible "
                  "when the damaged item is itself critical.",
    },
    "propulsion_ops": {
        "category": "II",
        "effect": "Return burn cannot be executed. Crew survive until "
                  "consumables run out, so this is mission loss rather than "
                  "immediate loss of life.",
    },
    "navigation": {
        "category": "II",
        "effect": "Return trajectory cannot be targeted. Same character as "
                  "propulsion loss: the vehicle is intact but cannot come home.",
    },
    "medical": {
        "category": "III",
        "effect": "Injury or exposure goes untreated. Severe injury is "
                  "possible; the vehicle and mission continue.",
    },
    "science": {
        "category": "IV",
        "effect": "Science objectives are lost. No injury, no system damage, "
                  "no effect on crew return.",
    },
}

# ASSUMED: numeric weight per severity category, so the ordinal categories can
# be combined with redundancy and demand. Evenly spaced by design — the
# standard ranks categories, it does not scale them.
ASSUMED_SEVERITY_CRITICALITY: dict[str, float] = {
    "I": 1.00,
    "II": 0.75,
    "III": 0.50,
    "IV": 0.25,
}

# Derived from the FMECA worksheet above rather than hand-written. This is the
# table `crew.crew_weight` reads.
ASSUMED_FUNCTION_CRITICALITY: dict[str, float] = {
    function: ASSUMED_SEVERITY_CRITICALITY[row["category"]]
    for function, row in ASSUMED_FUNCTION_SEVERITY_CATEGORY.items()
}

# ASSUMED: criticality for a function not covered by the worksheet (scenario
# builders may declare arbitrary function names). Category III equivalent.
ASSUMED_DEFAULT_FUNCTION_CRITICALITY = 0.5

ROLE_FUNCTIONS: dict[str, set[str]] = {
    "commander": {"command_decision"},
    "engineer":  {"repair", "power_ops", "life_support_ops"},
    "medic":     {"medical"},
    "pilot":     {"propulsion_ops", "navigation"},
    "scientist": {"science"},
}

# ASSUMED: how a failed facility raises demand for a function.
ASSUMED_FACILITY_FUNCTION_DEMAND: dict[str, dict[str, float]] = {
    "life_support": {"life_support_ops": 1.6, "medical": 1.3, "repair": 1.2},
    "power":        {"power_ops": 1.7, "repair": 1.3},
    "propulsion":   {"propulsion_ops": 1.5, "repair": 1.2},
}


# ── Simulation settings ──────────────────────────────────────────────────────
DT_SECONDS = 30.0
HORIZON_SECONDS = 3600.0
MONTECARLO_SAMPLES = 1000


# ── Monte Carlo scenario-assumption sampling ─────────────────────────────────
ASSUMED_DECISION_DELAY_RANGE_SECONDS = (0.0, 180.0)
ASSUMED_CREW_RESPONSE_RANGE_SECONDS = (30.0, 120.0)
ASSUMED_FLOW_UNCERTAINTY_FRACTION = 0.25
ASSUMED_UNKNOWN_PATH_OPEN_SHARE = 0.5
ASSUMED_UNKNOWN_PROFILE_CHOICES = (
    "NON_SUSTAINING",
    "STEADY_FABRIC_SPREAD",
    "GRADUAL_PMMA_GROWTH",
    "LIMITED_FLAME",
    "FLOW_SHUTDOWN_EXTINCTION_CANDIDATE",
    "NITROGEN_RICH_FOAM",
)

ETHICS_NOTICE = (
    "Mixed provenance: constants named VERIFIED_* come from primary sources "
    "(see config.SOURCES); constants named ASSUMED_* are PoC assumptions and "
    "are not validated. Crew criticality is a FMECA function-criticality model "
    "following MIL-STD-1629A severity classification, not a valuation of lives "
    "and not a real mission decision norm."
)
