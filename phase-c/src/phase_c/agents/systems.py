"""Systems Agent (plan §6.3 — PROPOSED; the task spec was truncated here).

The load-bearing job is preserving Phase A's recoverability semantics:
UNAVAILABLE is reversible, FAILED_EXPLICITLY is not. `system_reasons` gives the
cause verbatim, so quote it rather than guessing.
"""

from phase_c.agents.base import Agent, events_of
from phase_c.contracts.analysis import ActionAnalysis, CaseAnalysis

SYSTEM_EVENTS = {"system_state_change"}


class SystemsAgent(Agent):
    name = "systems"
    role = """\
You are the Systems analyst. You assess which systems still work, which do not,
and crucially whether a loss is RECOVERABLE.

Phase A defines the four states by recoverability, not by cause:
  OPERATIONAL       working
  EXPOSED_AT_RISK   a module it depends on carries detectable smoke or fire
  UNAVAILABLE       RECOVERABLE - the module is isolated, equipment is powered
                    down, or no crew member can operate it. Reversing that
                    choice, or freeing that person, restores the system.
  FAILED_EXPLICITLY NOT recoverable without repair - equipment is damaged.

Answer these, using only the DATA:
  - Which systems are degraded or lost, and in which of those two senses?
  - Quote `system_reasons` for the cause. Values look like `module_isolated`,
    `equipment_powered_down`, `equipment_damaged`, `no_operator:<function>`,
    `smoke_or_fire_in_module`. Never invent a cause that is not listed.
  - Which equipment is damaged versus merely unpowered? Unpowered equipment is
    a choice that can be undone; damaged equipment needs repair.
  - Does any equipment show repair progress?
  - Which system losses were driven by a person rather than by hardware
    (`no_operator:` reasons)? Those are the ones a crew action can reverse."""

    def project(self, analysis: ActionAnalysis, case: CaseAnalysis) -> dict:
        return {
            "systems": analysis.systems,
            "system_reasons": analysis.system_reasons,
            "equipment": {
                k: v.model_dump(mode="json") for k, v in analysis.equipment.items()
            },
            "resources": {
                k: v.model_dump(mode="json") for k, v in analysis.resources.items()
            },
            "expected_survivors": analysis.expected_survivors,
            "expected_returnees": analysis.expected_returnees,
            "events": events_of(analysis, SYSTEM_EVENTS),
        }
