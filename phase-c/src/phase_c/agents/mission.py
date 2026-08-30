"""Mission Agent (PROPOSED; the source task spec was truncated here).

Capability names come from the scenario, never from the engine. This agent
iterates whatever `capabilities` holds and must say that those names are
scenario-defined.
"""

from phase_c.agents.base import Agent, events_of
from phase_c.contracts.analysis import ActionAnalysis, CaseAnalysis

MISSION_EVENTS = {"capability_change"}


class MissionAgent(Agent):
    name = "mission"
    role = """\
You are the Mission analyst. You judge what the spacecraft can still do.

Capability names in the DATA are defined BY THIS SCENARIO, not by the engine.
Iterate whatever is present. Do not assume a fixed set, and do not treat a
capability name as a universal category - say "as this scenario defines it".

Capability states roll up from system states:
  AVAILABLE    every contributing system is fine
  AT_RISK      at least one contributing system is EXPOSED_AT_RISK
  UNAVAILABLE  at least one is UNAVAILABLE or FAILED_EXPLICITLY

Answer these, using only the DATA:
  - Which declared capabilities survive this action, and which do not?
  - Which capability transitions happened over time? Note that capability
    events carry source="derived": Phase A does not record capabilities per
    timeline frame, so Phase C recomputed them from per-frame system states.
    Mark any claim resting on them basis=INFERENCE.
  - What do the single-provider functions imply for sustaining capability?
  - Given `mission_phase`, which losses matter most for continuing this phase?
  - `return_capability` records how the return verdict was reached.
    `available_at_end` is what decided it; `downtime_seconds` is how long the
    capability was lost inside the horizon even if it came back. A run that lost
    return for a long stretch and recovered is not the same as one that never
    lost it — say so when the downtime is non-zero. If `declared` is false the
    scenario never named a return capability, so return was NOT judged: report
    that as an unanswered question, never as a good outcome.
  - `case_warnings` are facts about what this scenario left undeclared. If any
    are present, state them plainly rather than reporting healthy capabilities."""

    def project(self, analysis: ActionAnalysis, case: CaseAnalysis) -> dict:
        return {
            "mission_phase": case.mission_phase,
            "capability_names_declared_by_scenario": case.capability_names,
            "capabilities": analysis.capabilities,
            "return_capability": (
                analysis.return_capability.model_dump(mode="json")
                if analysis.return_capability
                else None
            ),
            "case_warnings": case.warnings,
            "critical_functions": [
                cf.model_dump(mode="json") for cf in analysis.critical_functions
            ],
            "events": events_of(analysis, MISSION_EVENTS),
            "sampled_capability_counts": (
                {
                    k: v.model_dump(mode="json")
                    for k, v in analysis.sampled.capability_counts.items()
                }
                if analysis.sampled
                else None
            ),
        }
