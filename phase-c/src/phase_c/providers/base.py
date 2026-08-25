"""The integration boundary.

Agents depend only on `SimulationProvider` output. No agent, no orchestrator,
and no prompt ever imports a Phase A module — enforced by a test.
"""

from typing import Protocol, runtime_checkable

from phase_c.contracts.analysis import ActionRef, CaseAnalysis


@runtime_checkable
class SimulationProvider(Protocol):
    def list_actions(self, scenario) -> list[ActionRef]:
        """Candidate actions for this scenario graph. Ids are opaque strings."""
        ...

    def analyze_case(
        self,
        scenario,
        *,
        action_ids: list[str] | None = None,
        samples: int | None = None,
        seed: int | None = None,
    ) -> CaseAnalysis:
        """Normalized analysis for every requested action (all when None)."""
        ...
