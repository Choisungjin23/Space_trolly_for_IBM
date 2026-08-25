"""Plain-text result reports in real units. Facts only — no BEST ACTION ranking
(that judgment is reserved for the Phase C agents and, ultimately, humans)."""

from spacecraft_sim.engine import TimelineResult
from spacecraft_sim.montecarlo import Distribution


def format_result(result: TimelineResult, mc: Distribution | None = None) -> str:
    s = result.summary
    lines = [f"ACTION: {s['action_id']}"]

    detected = s["detected_at_seconds"]
    lines.append(
        "Detected at:            "
        + (f"{detected:.0f} s" if detected is not None else "never (below alarm level)")
    )
    lines.append(
        "Smoke reached:          "
        + (", ".join(s["hazard_reached"]) if s["hazard_reached"] else "none")
        + "   (>= 0.033 /m, ISS detector alarm level)"
    )
    lines.append(
        "SMAC exceeded in:       "
        + (", ".join(s["smac_exceeded"]) if s["smac_exceeded"] else "none")
    )

    counts = s["crew_counts"]
    lines.append(
        "Crew:                   "
        f"{counts['EVACUATED']} evacuated / {counts['TRAPPED']} trapped / "
        f"{counts['SAFE']} safe / {counts['EXPOSED'] + counts['EVACUATING']} in transit or exposed"
    )

    exposures = [
        f"{cid} = {info['exposure_seconds']:.0f} s"
        for cid, info in s["crew"].items()
        if info["exposure_seconds"] > 0
    ]
    lines.append("Exposure:               " + (", ".join(exposures) if exposures else "none"))

    doses = [
        f"{cid} = {info['smac_dose_fraction']:.3f}"
        for cid, info in s["crew"].items()
        if info["smac_dose_fraction"] > 0
    ]
    lines.append(
        "SMAC dose (1.0 = 1 h at the 1-hour limit): "
        + (", ".join(doses) if doses else "none")
    )

    lines.append(
        "Systems:                "
        + ", ".join(f"{sid} = {state}" for sid, state in s["systems"].items())
    )
    lines.append(
        "Capabilities:           "
        + ", ".join(f"{cap} = {state}" for cap, state in s["capabilities"].items())
    )

    if s["critical_functions"]:
        for finding in s["critical_functions"]:
            providers = ", ".join(finding["providers"]) or "-"
            lines.append(
                f"Critical Function Risk: {finding['function']} = "
                f"{finding['flag']} ({providers})"
            )
    else:
        lines.append("Critical Function Risk: none flagged")

    if mc is not None:
        lines.append(
            "Monte Carlo:            "
            f"{mc.retained_evacuation_and_return} / {mc.samples} samples retained "
            "evacuation + return"
        )
        lines.append(
            "                        "
            f"no-trapped {mc.no_crew_trapped}/{mc.samples}; "
            f"return {mc.return_available}/{mc.samples}; "
            f"habitation {mc.habitation_available}/{mc.samples}; "
            f"smoke contained {mc.hazard_contained_to_sources}/{mc.samples}; "
            f"no crew reached a full SMAC dose {mc.no_crew_reached_smac_dose}/{mc.samples}"
        )

    return "\n".join(lines)


def format_comparison(results: list[TimelineResult]) -> str:
    """Side-by-side facts per action. Deliberately no recommendation column."""
    header = (
        f"{'action':<34} {'detect_s':>8} {'smoke_reached':<16} {'trapped':>7} "
        f"{'evac':>5} {'expo_s':>7} {'dose':>6} {'RETURN':>11} {'HABITATION':>11}"
    )
    rows = [header, "-" * len(header)]
    for result in results:
        s = result.summary
        total_exposure = sum(c["exposure_seconds"] for c in s["crew"].values())
        peak_dose = max(
            (c["smac_dose_fraction"] for c in s["crew"].values()), default=0.0
        )
        detected = s["detected_at_seconds"]
        rows.append(
            f"{s['action_id']:<34} "
            f"{(f'{detected:.0f}' if detected is not None else '-'):>8} "
            f"{','.join(s['hazard_reached']) or 'none':<16} "
            f"{s['crew_counts']['TRAPPED']:>7} "
            f"{s['crew_counts']['EVACUATED']:>5} "
            f"{total_exposure:>7.0f} "
            f"{peak_dose:>6.3f} "
            f"{s['capabilities'].get('RETURN', '-'):>11} "
            f"{s['capabilities'].get('HABITATION', '-'):>11}"
        )
    rows.append("")
    rows.append("(Facts only — no recommendation is made at this phase.)")
    return "\n".join(rows)


def format_criticality(findings: list[dict]) -> str:
    """Leave-one-out measured criticality vs the assumed FMECA-style weight."""
    header = f"{'crew':<8} {'role':<12} {'measured':>10} {'assumed':>9}"
    rows = [
        header,
        "-" * len(header),
    ]
    for f in findings:
        rows.append(
            f"{f['crew_id']:<8} {f['role']:<12} "
            f"{f['measured_score']:>10.4f} {f['assumed_weight']:>9.4f}"
        )
    rows.append("")
    rows.append(
        "measured = capability score lost when this crew member is removed "
        "(leave-one-out)."
    )
    rows.append(
        "assumed  = FMECA-style weight from the ASSUMED_ tables in config. "
        "Neither is a valuation of a life."
    )

    if findings and all(f["measured_score"] == 0.0 for f in findings):
        rows.append("")
        rows.append(
            "NOTE: every measured score is 0.000. In the current model, "
            "capabilities depend only on modules and equipment — no crew member "
            "operates or repairs a system, so removing one cannot change the "
            "outcome. Leave-one-out becomes informative once the model couples "
            "crew functions to system recovery (e.g. a FAILED system stays "
            "failed unless a 'repair' provider is available and can reach it)."
        )
    return "\n".join(rows)
