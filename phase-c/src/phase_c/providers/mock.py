"""MockSimulationProvider — replays committed fixtures.

Lets every agent and orchestration test run offline and deterministically,
without Phase A installed. Fixtures are captured from real Phase A output by
`tools/capture_fixture.py`, so the shapes are real, not imagined.
"""

import json
from pathlib import Path

from phase_c.contracts.analysis import ActionRef, CaseAnalysis


class MockSimulationProvider:
    def __init__(self, case: CaseAnalysis) -> None:
        self.case = case

    @classmethod
    def from_fixture(cls, path: str | Path) -> "MockSimulationProvider":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(CaseAnalysis.model_validate(data))

    def list_actions(self, scenario=None) -> list[ActionRef]:
        return [analysis.action for analysis in self.case.actions]

    def analyze_case(
        self,
        scenario=None,
        *,
        action_ids: list[str] | None = None,
        samples: int | None = None,
        seed: int | None = None,
    ) -> CaseAnalysis:
        if action_ids is None:
            return self.case
        available = {a.action.id for a in self.case.actions}
        unknown = [a for a in action_ids if a not in available]
        if unknown:
            raise KeyError(f"Unknown action id(s) for this fixture: {unknown}")
        return self.case.model_copy(
            update={
                "actions": [
                    a for a in self.case.actions if a.action.id in set(action_ids)
                ]
            }
        )
