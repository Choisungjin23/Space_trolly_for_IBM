"""Crew Safety Agent (task spec §10).

`crew` is a dict keyed by crew_id, never a list.
"""

from phase_c.agents.base import Agent, events_of
from phase_c.contracts.analysis import ActionAnalysis, CaseAnalysis

CREW_EVENTS = {"crew_state_change", "crew_module_change"}


class CrewSafetyAgent(Agent):
    name = "crew_safety"
    role = """\
You are the Crew Safety analyst. You reason about exposure, evacuation,
entrapment, module transitions, remaining evacuation feasibility, and the
consequences of losing a function provider. Compare modeled survival and return
probabilities and identify which crew preservation produces the largest
counterfactual gain in total surviving returnees.

Answer these, using only the DATA:
  - Where did each crew member end up, and in what state?
  - Who accumulated exposure, and how much? `smac_dose_fraction` of 1.0 means
    the equivalent of one hour at the 1-hour exposure guideline; report the
    fraction as given.
  - Use `estimated_survival_minutes` and `resource_risk_reasons` to explain the
    combined air, power, water, contaminant and direct-fire burden. Very low
    survival under sustained fire is permitted by the explicit ASSUMED model;
    report it without softening or treating it as a clinical forecast.
  - Did anyone become TRAPPED, and what does the event sequence say about why?
  - Which hatch is the limiting queue? Compare its connectivity, crew/min and
    air %/min, and identify who is waiting there.
  - If everyone and all portable equipment cannot pass, explain the computed
    crew order first and the portable-equipment order second. Test whether a
    different ordering preserves more total surviving returnees or a unique
    mission function, including passage-driven air/connectivity feedback.
  - Which functions have a single provider or none, and which crew member that
    depends on?
  - What does `criticality` say? `measured_score` is the capability lost when
    that person is removed from the simulation; `assumed_weight` is a
    configurable FMECA-style table value. Explain priorities through their
    effect on total expected surviving returnees. Criticality measures how
    irreplaceable a FUNCTION is under the current scenario; it is never a claim
    about a person's intrinsic social worth."""

    def project(self, analysis: ActionAnalysis, case: CaseAnalysis) -> dict:
        return {
            "crew": {k: v.model_dump(mode="json") for k, v in analysis.crew.items()},
            "crew_counts": analysis.crew_counts,
            "expected_survivors": analysis.expected_survivors,
            "expected_returnees": analysis.expected_returnees,
            "resources": {
                k: v.model_dump(mode="json") for k, v in analysis.resources.items()
            },
            "connectivity": {
                k: v.model_dump(mode="json")
                for k, v in analysis.connectivity.items()
            },
            "escape_target": analysis.escape_target,
            "portable_equipment_priority": {
                k: v.model_dump(mode="json")
                for k, v in analysis.equipment.items()
                if v.portable
            },
            "critical_functions": [
                cf.model_dump(mode="json") for cf in analysis.critical_functions
            ],
            "events": events_of(analysis, CREW_EVENTS),
            "criticality": [c.model_dump(mode="json") for c in case.criticality],
            "criticality_baseline_action": case.criticality_baseline_action,
        }
