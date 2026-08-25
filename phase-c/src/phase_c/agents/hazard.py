"""Hazard Agent (task spec §9).

Reads only hazard/fire/environment consequences. Forbidden: inventing spread
probabilities, growth rates, detection times, or physical constants.
"""

from phase_c.agents.base import Agent, events_of
from phase_c.contracts.analysis import ActionAnalysis, CaseAnalysis

HAZARD_EVENTS = {
    "detection_confirmed",
    "hazard_arrival",
    "smac_exceeded",
    "extinction_milestone",
}


class HazardAgent(Agent):
    name = "hazard"
    role = """\
You are the Hazard analyst. You assess how far the hazard travelled, how well
this action contained it, whether exposure guideline thresholds were crossed,
which pathways mattered, and what changed over time.

Answer these, using only the DATA:
  - Which modules did smoke reach, and which stayed clean?
  - Did any module exceed a 1-hour SMAC exposure guideline?
  - What does the peak obscuration per module say about severity?
  - When was the fire detected, and what does that timing imply for this run?
  - Which conclusions come straight from simulator output, and which depend on
    Phase A's configurable assumptions? Mark the latter basis=ASSUMPTION.

`detection.status == "NEVER_DETECTED"` is a real outcome: smoke stayed below the
detector alarm level for the whole horizon, so the action landed only at the end.
Say so plainly if you see it."""

    def project(self, analysis: ActionAnalysis, case: CaseAnalysis) -> dict:
        return {
            "detection": analysis.detection.model_dump(mode="json"),
            "hazard": analysis.hazard.model_dump(mode="json"),
            "events": events_of(analysis, HAZARD_EVENTS),
            "sampled": analysis.sampled.model_dump(mode="json")
            if analysis.sampled
            else None,
        }
