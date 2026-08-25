"""IBM Granite via watsonx, behind a hard budget guard.

Credentials are never copied into code, config, or shell history. Either:

    WATSONX_API_KEY        the key itself, if you prefer an env var
    WATSONX_APIKEY_FILE    path to the JSON IBM gives you; the key is read
                           from its "apikey" field at call time and never
                           written anywhere

Always required:

    WATSONX_PROJECT_ID     the watsonx project the model is deployed in

Optional:

    WATSONX_URL            region endpoint, default https://us-south.ml.cloud.ibm.com
    WATSONX_MODEL_ID       default ibm/granite-3-8b-instruct

Every call reserves its worst-case cost before going out and settles with the
real token count on the way back, so the run cannot quietly exceed the cap.
"""

import json
import os
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from phase_c.llm import budget
from phase_c.llm.base import LLMError, parse_structured

T = TypeVar("T", bound=BaseModel)

DEFAULT_URL = "https://us-south.ml.cloud.ibm.com"
DEFAULT_MODEL_ID = "ibm/granite-3-8b-instruct"


def _read_api_key() -> str | None:
    """Prefer an explicit env var; otherwise read the key out of the JSON file
    IBM hands you. The value is returned, never logged or persisted."""
    key = os.environ.get("WATSONX_API_KEY")
    if key:
        return key

    key_file = os.environ.get("WATSONX_APIKEY_FILE")
    if not key_file:
        return None

    path = Path(key_file)
    if not path.is_file():
        raise LLMError(f"WATSONX_APIKEY_FILE points at a missing file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LLMError(f"WATSONX_APIKEY_FILE is not valid JSON: {exc}") from exc

    value = data.get("apikey") or data.get("api_key")
    if not value:
        raise LLMError(
            f"No 'apikey' field in {path.name}. Expected the JSON IBM Cloud "
            "gives you when you create an API key."
        )
    return value


class GraniteClient:
    def __init__(
        self,
        *,
        model_id: str | None = None,
        url: str | None = None,
        api_key: str | None = None,
        project_id: str | None = None,
        max_new_tokens: int = 1600,
        retries: int = 1,
        budget_guard: bool = True,
    ) -> None:
        self.model_id = model_id or os.environ.get("WATSONX_MODEL_ID", DEFAULT_MODEL_ID)
        self.url = url or os.environ.get("WATSONX_URL", DEFAULT_URL)
        self.api_key = api_key or _read_api_key()
        self.project_id = project_id or os.environ.get("WATSONX_PROJECT_ID")
        self.max_new_tokens = max_new_tokens
        self.retries = retries
        self.budget_guard = budget_guard

        if not self.api_key:
            raise LLMError(
                "No watsonx API key. Set WATSONX_API_KEY, or point "
                "WATSONX_APIKEY_FILE at the JSON file IBM gave you."
            )
        if not self.project_id:
            raise LLMError(
                "No WATSONX_PROJECT_ID. Find it in watsonx.ai: open your "
                "project, then Manage > General > Details."
            )
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        try:
            from ibm_watsonx_ai import Credentials
            from ibm_watsonx_ai.foundation_models import ModelInference
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise LLMError(
                'ibm-watsonx-ai is not installed. Run: pip install -e ".[granite]"'
            ) from exc

        self._model = ModelInference(
            model_id=self.model_id,
            credentials=Credentials(url=self.url, api_key=self.api_key),
            project_id=self.project_id,
            params={
                "decoding_method": "greedy",
                "max_new_tokens": self.max_new_tokens,
            },
        )
        return self._model

    @staticmethod
    def _usage(response: dict) -> tuple[int | None, int | None]:
        """Pull the real token counts out of a watsonx generate() response."""
        results = (response or {}).get("results") or []
        if not results:
            return None, None
        first = results[0]
        return first.get("input_token_count"), first.get("generated_token_count")

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        temperature: float = 0.0,
    ) -> T:
        prompt = (
            f"{system}\n\n"
            f"Reply with a single JSON object matching this schema:\n"
            f"{schema.model_json_schema()}\n\n"
            f"{user}\n\nJSON:"
        )

        model = self._ensure_model()

        reservation = None
        if self.budget_guard:
            # Raises BudgetExceeded before any network traffic.
            reservation = budget.reserve_budget(prompt, self.max_new_tokens)

        settled = False
        last_error: Exception | None = None
        try:
            for _ in range(self.retries + 1):
                # generate() rather than generate_text(): it returns the token
                # counts the budget ledger needs to settle accurately.
                response = model.generate(prompt=prompt)
                input_tokens, output_tokens = self._usage(response)

                if reservation is not None and not settled:
                    budget.settle_budget(reservation, input_tokens, output_tokens)
                    settled = True

                text = ""
                results = (response or {}).get("results") or []
                if results:
                    text = results[0].get("generated_text", "")

                try:
                    return parse_structured(text, schema)
                except LLMError as exc:
                    # One retry on a parse failure; each attempt is billed, so
                    # each attempt reserves and settles on its own.
                    last_error = exc
                    if reservation is not None:
                        reservation = budget.reserve_budget(prompt, self.max_new_tokens)
                        settled = False

            raise LLMError(
                f"Granite response never matched {schema.__name__}: {last_error}"
            )
        except Exception:
            # A reservation that never reached IBM is released rather than
            # booked, so local failures do not eat the budget.
            if reservation is not None and not settled:
                budget.release_reservation(reservation)
            raise
