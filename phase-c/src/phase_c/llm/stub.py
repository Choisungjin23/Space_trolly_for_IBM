"""Deterministic offline LLM client.

Every test in the suite runs on this, so CI needs no key and no network. It is
also the adversarial harness: `scripted` lets a test hand back a deliberately
ungrounded finding to prove the validator catches it.
"""

from typing import Callable, TypeVar

from pydantic import BaseModel

from phase_c.llm.base import LLMError

T = TypeVar("T", bound=BaseModel)

Responder = Callable[[str, str, type[BaseModel]], BaseModel]


class StubLLMClient:
    def __init__(
        self,
        *,
        scripted: dict[str, BaseModel] | None = None,
        responder: Responder | None = None,
    ) -> None:
        # Keyed by the agent name embedded in the system prompt.
        self.scripted = scripted or {}
        self.responder = responder
        self.calls: list[tuple[str, str, str]] = []

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        temperature: float = 0.0,
    ) -> T:
        agent = _agent_of(system)
        self.calls.append((agent, system, user))

        if agent in self.scripted:
            return self.scripted[agent]  # type: ignore[return-value]
        if self.responder is not None:
            return self.responder(system, user, schema)  # type: ignore[return-value]
        raise LLMError(
            f"StubLLMClient has no scripted response for agent {agent!r}. "
            "Provide `scripted` or `responder`."
        )


def _agent_of(system_prompt: str) -> str:
    marker = "AGENT:"
    for line in system_prompt.splitlines():
        if line.strip().startswith(marker):
            return line.split(marker, 1)[1].strip()
    return "unknown"
