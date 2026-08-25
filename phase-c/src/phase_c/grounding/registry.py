"""Fact registry — every value an agent is allowed to state.

Built by walking the normalized ActionAnalysis before any agent runs. Keys are
JSON pointers, so a claim's `refs` can point straight at the source of a number.

Besides raw scalars the registry also holds *structural* facts, because agents
legitimately say things like "3 modules were reached" where 3 is a list length
rather than a stored value:

    /hazard/reached_modules        -> ["M1","M2","M3"]
    /hazard/reached_modules#count  -> 3
"""

from typing import Any

from phase_c.contracts.analysis import ActionAnalysis, CaseAnalysis


def _walk(node: Any, pointer: str, out: dict[str, Any]) -> None:
    if isinstance(node, dict):
        out[f"{pointer}#count"] = len(node)
        for key, value in node.items():
            _walk(value, f"{pointer}/{key}", out)
        numeric = [v for v in node.values() if isinstance(v, (int, float))
                   and not isinstance(v, bool)]
        if numeric:
            out[f"{pointer}#max"] = max(numeric)
            out[f"{pointer}#min"] = min(numeric)
            out[f"{pointer}#sum"] = sum(numeric)
    elif isinstance(node, list):
        out[f"{pointer}#count"] = len(node)
        for index, value in enumerate(node):
            _walk(value, f"{pointer}/{index}", out)
    else:
        out[pointer] = node


class FactRegistry:
    """The complete set of values agents may assert, for one action."""

    def __init__(self, facts: dict[str, Any]) -> None:
        self.facts = facts
        self._numeric = {
            pointer: float(value)
            for pointer, value in facts.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }

    @classmethod
    def from_action(cls, analysis: ActionAnalysis) -> "FactRegistry":
        facts: dict[str, Any] = {}
        _walk(analysis.model_dump(mode="json"), "", facts)
        return cls(facts)

    @classmethod
    def from_case(cls, case: CaseAnalysis) -> "FactRegistry":
        facts: dict[str, Any] = {}
        _walk(case.model_dump(mode="json"), "", facts)
        return cls(facts)

    def resolves(self, pointer: str) -> bool:
        if pointer in self.facts:
            return True
        # A pointer to a container resolves if anything sits beneath it.
        prefix = pointer.rstrip("/") + "/"
        return any(key.startswith(prefix) for key in self.facts)

    def supports_number(self, value: float, *, rel_tol: float = 1e-6) -> bool:
        """True when the registry holds this number, allowing for the rounding
        an agent naturally applies in prose (270.0 -> 270, 0.0043 -> 0.004)."""
        for known in self._numeric.values():
            if known == value:
                return True
            scale = max(abs(known), abs(value), 1.0)
            if abs(known - value) <= rel_tol * scale:
                return True
            # Rounding to the agent's stated precision.
            for digits in range(0, 7):
                if round(known, digits) == value:
                    return True
        return False

    def numbers(self) -> dict[str, float]:
        return dict(self._numeric)
