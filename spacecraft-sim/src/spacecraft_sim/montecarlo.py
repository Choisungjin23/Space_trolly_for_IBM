"""Monte Carlo over uncertain scenario ASSUMPTIONS (A-10).

Not "repeat a spread probability 1000 times". Each sample draws one plausible
world — crew decision delay after the alarm, crew response time, unknown leak
paths open or closed, connection flow uncertainty, source-profile uncertainty —
and runs the deterministic engine on it. Results are reported as counts over
samples ("k of n samples retained evacuation + return"), never as a validated
real-world probability.

Detection delay is no longer sampled: the engine now computes when the smoke
actually reaches an alarm level. What remains uncertain is how long the crew
take to decide once they know.
"""

from dataclasses import dataclass, field

import numpy as np

from spacecraft_sim import config
from spacecraft_sim.actions import Action
from spacecraft_sim.engine import counterfactual
from spacecraft_sim.models import Scenario


@dataclass
class Distribution:
    """Counts over n sampled scenario-assumption worlds (not probabilities)."""

    action_id: str
    samples: int
    retained_evacuation_and_return: int = 0
    no_crew_trapped: int = 0
    # Samples where every crew member ended SAFE or EVACUATED (nobody trapped,
    # still exposed, or still in transit at the end of the horizon).
    all_crew_safe_or_evacuated: int = 0
    return_available: int = 0
    habitation_available: int = 0
    hazard_contained_to_sources: int = 0
    # Crew-centric: the burning module always exceeds its own SMAC, so counting
    # module exceedance would be constant by construction and tell us nothing.
    no_crew_reached_smac_dose: int = 0
    mean_total_exposure_seconds: float = 0.0
    mean_peak_smac_dose: float = 0.0
    mean_expected_survivors: float = 0.0
    mean_expected_returnees: float = 0.0
    notes: list[str] = field(default_factory=list)


def sample_scenario(
    scenario: Scenario, rng: np.random.Generator
) -> tuple[Scenario, dict]:
    """One plausible world plus the assumption values that produced it."""
    sc = scenario.model_copy(deep=True)

    for conn in sc.connections:
        # Unknown path state (possible leakage) -> open in a share of samples.
        if conn.path_state == "unknown":
            conn.path_state = (
                "open"
                if rng.random() < config.ASSUMED_UNKNOWN_PATH_OPEN_SHARE
                else "closed"
            )
        # Flow uncertainty: perturb each connection's actual volumetric flow.
        jitter = 1.0 + rng.uniform(
            -config.ASSUMED_FLOW_UNCERTAINTY_FRACTION,
            config.ASSUMED_FLOW_UNCERTAINTY_FRACTION,
        )
        conn.flow_m3_s = max(0.0, conn.nominal_flow_m3_s() * jitter)

    for module in sc.modules:
        if (
            module.fire_state in ("incipient", "sustained")
            and (module.source_profile_id or "POC_UNKNOWN") == "POC_UNKNOWN"
        ):
            module.source_profile_id = str(
                rng.choice(config.ASSUMED_UNKNOWN_PROFILE_CHOICES)
            )

    assumptions = {
        "decision_delay": float(
            rng.uniform(*config.ASSUMED_DECISION_DELAY_RANGE_SECONDS)
        ),
        "crew_response": float(rng.uniform(*config.ASSUMED_CREW_RESPONSE_RANGE_SECONDS)),
    }
    return sc, assumptions


def run_montecarlo(
    scenario: Scenario,
    action: Action,
    n: int = config.MONTECARLO_SAMPLES,
    seed: int | None = None,
    horizon: float | None = None,
    dt: float | None = None,
) -> Distribution:
    rng = np.random.default_rng(seed)
    dist = Distribution(action_id=action.id, samples=n)
    total_exposure = 0.0
    total_peak_dose = 0.0
    total_expected_survivors = 0.0
    total_expected_returnees = 0.0

    for _ in range(n):
        sc, assumptions = sample_scenario(scenario, rng)
        result = counterfactual(
            sc,
            action,
            horizon=horizon,
            dt=dt,
            decision_delay=assumptions["decision_delay"],
            response_seconds=assumptions["crew_response"],
        )

        summary = result.summary
        trapped = summary["crew_counts"]["TRAPPED"]
        return_ok = summary["capabilities"].get("RETURN", "AVAILABLE") != "UNAVAILABLE"
        habitation_ok = (
            summary["capabilities"].get("HABITATION", "AVAILABLE") != "UNAVAILABLE"
        )
        source_ids = {m.id for m in sc.fire_modules()}
        contained = set(summary["hazard_reached"]) <= source_ids

        if trapped == 0:
            dist.no_crew_trapped += 1
        counts = summary["crew_counts"]
        if (
            trapped == 0
            and counts["EXPOSED"] == 0
            and counts["EVACUATING"] == 0
        ):
            dist.all_crew_safe_or_evacuated += 1
        if return_ok:
            dist.return_available += 1
        if habitation_ok:
            dist.habitation_available += 1
        if trapped == 0 and return_ok:
            dist.retained_evacuation_and_return += 1
        if contained:
            dist.hazard_contained_to_sources += 1

        peak_dose = max(
            (c["smac_dose_fraction"] for c in summary["crew"].values()), default=0.0
        )
        if peak_dose < 1.0:
            dist.no_crew_reached_smac_dose += 1

        total_exposure += sum(c["exposure_seconds"] for c in summary["crew"].values())
        total_peak_dose += peak_dose
        total_expected_survivors += summary["expected_survivors"]
        total_expected_returnees += summary["expected_returnees"]

    dist.mean_total_exposure_seconds = round(total_exposure / n, 1) if n else 0.0
    dist.mean_peak_smac_dose = round(total_peak_dose / n, 4) if n else 0.0
    dist.mean_expected_survivors = round(total_expected_survivors / n, 6) if n else 0.0
    dist.mean_expected_returnees = round(total_expected_returnees / n, 6) if n else 0.0
    dist.notes.append(
        "Counts over sampled scenario assumptions; the Monte Carlo repetition "
        "does not validate real-world probabilities."
    )
    return dist
