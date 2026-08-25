"""Emergency actions.

Actions are generated from the current state rather than hard-coded to one
module, so moving the fire (via the GUI) produces the matching set of options:
seal the burning module, or close any one of the hatches leading out of it.
Each action deep-copies the state and mutates the copy BEFORE the stochastic
simulation starts; the input state is never modified.
"""

import copy
from dataclasses import dataclass

from app.domain.models import Spacecraft

DO_NOTHING_ID = "do_nothing"


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    description: str
    kind: str  # "do_nothing" | "isolate" | "close_hatch"
    targets: tuple[str, ...]

    def apply(self, state: Spacecraft) -> Spacecraft:
        new_state = copy.deepcopy(state)
        if self.kind == "isolate":
            new_state.modules[self.targets[0]].isolated = True
        elif self.kind == "close_hatch":
            pair = set(self.targets)
            for conn in new_state.connections:
                if {conn.source, conn.target} == pair:
                    conn.active = False
        return new_state


def _do_nothing_action() -> Action:
    return Action(
        id=DO_NOTHING_ID,
        label="Do nothing",
        description="Take no action; let the fire develop on its own.",
        kind="do_nothing",
        targets=(),
    )


def _isolate_action(state: Spacecraft, module_id: str) -> Action:
    module = state.modules[module_id]
    return Action(
        id=f"isolate_{module_id.lower()}",
        label=f"Isolate {module.name} ({module_id})",
        description=(
            f"Seal {module_id} completely: fire cannot spread in or out through any "
            f"of its connections, and crew inside cannot evacuate."
        ),
        kind="isolate",
        targets=(module_id,),
    )


def _close_hatch_action(state: Spacecraft, a: str, b: str) -> Action:
    first, second = sorted((a, b))
    return Action(
        id=f"close_{first.lower()}_{second.lower()}",
        label=f"Close hatch {first}–{second}",
        description=(
            f"Close only the {first}–{second} connection; every other connection "
            f"stays open."
        ),
        kind="close_hatch",
        targets=(first, second),
    )


def available_actions(state: Spacecraft) -> list[Action]:
    """Candidate actions for the current state: do nothing, isolate each burning
    module, and close each hatch leading out of a burning module."""
    actions = [_do_nothing_action()]
    burning = [m.id for m in state.modules.values() if m.fire_severity > 0]

    for module_id in burning:
        actions.append(_isolate_action(state, module_id))

    seen: set[str] = set()
    for module_id in burning:
        for neighbor_id in state.neighbors(module_id):
            action = _close_hatch_action(state, module_id, neighbor_id)
            if action.id not in seen:
                seen.add(action.id)
                actions.append(action)

    return actions


def action_registry(state: Spacecraft) -> dict[str, Action]:
    return {action.id: action for action in available_actions(state)}
