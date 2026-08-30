"""LLM boundary.

Agents never talk to a vendor SDK directly. They ask for a schema-validated
object; the client is responsible for getting one or raising.
"""

import ast
import json
from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


@runtime_checkable
class LLMClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        temperature: float = 0.0,
    ) -> T:
        ...


def _load_object(blob: str) -> Any:
    """Read a JSON object, falling back to a Python literal.

    Instruction-tuned models do not all emit strict JSON: some reply with a
    Python-style dict using single quotes. `ast.literal_eval` reads that
    correctly - including apostrophes inside strings, which naive quote
    substitution would corrupt - and evaluates literals only, never code.
    """
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return ast.literal_eval(blob)


def parse_structured(text: str, schema: type[T]) -> T:
    """Parse a model response into `schema`, tolerating fenced code blocks."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[: -3]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"No JSON object in model response: {text[:200]!r}")
    try:
        return schema.model_validate(_load_object(cleaned[start : end + 1]))
    except (json.JSONDecodeError, ValueError, SyntaxError, ValidationError) as exc:
        raise LLMError(f"Response did not match {schema.__name__}: {exc}") from exc
