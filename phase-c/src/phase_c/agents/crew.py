"""Crew Safety Agent (task spec §10).

`crew` is a dict keyed by crew_id, never a list. Forbidden: fatality
probabilities, any numerical valuation of a person.
"""

from phase_c.agents.base import Agent, events_of
from phase_c.contracts.analysis import ActionAnalysis, CaseAnalysis

CREW_EVENTS = {"crew_state_change", "crew_module_change"}


class CrewSafetyAgent(Agent):
    name = "crew_safety"
    role = """\
You are the Crew Safety analyst. You reason about exposure, evacuation,
entrapment, module transitions, remaining evacuation feasibility, and the
consequences of losing a function provider.

Answer these, using only the DATA:
  - Where did each crew member end up, and in what state?
  - Who accumulated exposure, and how much? `smac_dose_fraction` of 1.0 means
    the equivalent of one hour at the 1-hour exposure guideline; report the
    fraction as given.
  - Did anyone become TRAPPED, and what does the event sequence say about why?
  - Which functions have a single provider or none, and which crew member that
    depends on?
  - What does `criticality` say? `measured_score` is the capability lost when
    that person is removed from the simulation; `assumed_weight` is a
    configurable FMECA-style table value. Neither is the worth of a life -
    both describe how irreplaceable a FUNCTION currently is. State that framing
    whenever you mention them."""

    def project(self, analysis: ActionAnalysis, case: CaseAnalysis) -> dict:
        return {
            "crew": {k: v.model_dump(mode="json") for k, v in analysis.crew.items()},
            "crew_counts": analysis.crew_counts,
            "critical_functions": [
                cf.model_dump(mode="json") for cf in analysis.critical_functions
            ],
            "events": events_of(analysis, CREW_EVENTS),
            "criticality": [c.model_dump(mode="json") for c in case.criticality],
            "criticality_baseline_action": case.criticality_baseline_action,
        }
