"""IBM Granite via watsonx.ai, behind a hard budget guard.

Everything that identifies the IBM environment comes from configuration, read
when the client is constructed - see `phase_c.config`. There is no default
model and no default region here: pointing the advisor at another region or
another supported foundation model is a `.env` edit, not a code change.

    WATSONX_API_KEY        the key itself
    WATSONX_APIKEY_FILE    alternatively, the JSON IBM gives you; the key is
                           read from its "apikey" field at call time
    WATSONX_PROJECT_ID     the watsonx project, in the same region as the URL
    WATSONX_URL            regional endpoint, e.g. https://us-south.ml.cloud.ibm.com
    WATSONX_MODEL_ID       e.g. ibm/granite-4-h-small

Whether the configured model exists is decided by watsonx itself: the SDK
checks `model_id` against the models the configured environment actually
serves. A model that region does not offer fails loudly rather than being
swapped for something else.

Inference goes through watsonx's chat endpoint. The Granite instruction models
are chat-tuned, and the older text-generation endpoint - which the SDK reports
as deprecated - does not apply their chat template: handed an agent prompt,
granite-4-h-small returns an immediate end-of-sequence token and no text at
all. `chat()` applies the template and answers normally.

Every call reserves its worst-case cost before going out and settles with the
real token count on the way back, so the run cannot quietly exceed the cap.
"""

import json
import re
from typing import TypeVar

from pydantic import BaseModel

from phase_c.config import ConfigError, WatsonxConfig, fingerprint, value_sources
from phase_c.llm import budget
from phase_c.llm.base import LLMError, parse_structured

T = TypeVar("T", bound=BaseModel)

# A ceiling on how far a truncated reply may grow its retry. Without one, a
# model that rambles would keep doubling its own bill.
MAX_OUTPUT_TOKENS = 4000


# IBM Cloud IAM answers with its own codes, and they arrive over a transport
# that carries no HTTP status, so the generic branches below never see them.
# Each of these means something different for the operator to go and do.
_IAM_CODES: dict[str, str] = {
    "BXNIM0462E": (
        "the API key exists but is DISABLED in IBM Cloud. Re-enable it, or "
        "create a new one, at IBM Cloud > Manage > Access (IAM) > API keys"
    ),
    "BXNIM0415E": (
        "IBM Cloud has no such API key. It was deleted, or the value is "
        "truncated or from another account"
    ),
    "BXNIM0410E": "the API key is not valid for this account",
    "BXNIM0439E": "the API key has expired",
}


def _iam_reason(message: str) -> tuple[str, str] | None:
    """Pull IBM's own IAM code and text out of the JSON it embeds in a message."""
    match = re.search(r'\{.*"errorCode".*\}', message, re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    code = str(payload.get("errorCode", ""))
    detail = str(payload.get("errorMessage", "")).strip()
    if not code:
        return None
    return code, detail


# watsonx puts its own machine-readable code in the response body. Reading it
# matters: a 403 for an exhausted plan quota and a 403 for a project the key
# cannot see need completely different fixes, and the HTTP status alone cannot
# tell them apart.
_WATSONX_CODES: dict[str, str] = {
    "token_quota_reached": (
        "the watsonx.ai plan's token quota is exhausted. This is an account "
        "limit, not a credential problem: the key and project are fine. Wait "
        "for the quota to reset, or raise the plan under IBM Cloud > watsonx.ai "
        "> Plan"
    ),
    "model_not_supported": (
        "this region does not serve WATSONX_MODEL_ID. Choose a model it lists"
    ),
    "no_associated_service_instance": (
        "WATSONX_PROJECT_ID has no watsonx.ai runtime associated. Associate one "
        "under the project's Manage > Services & integrations"
    ),
}


def _watsonx_reason(message: str) -> tuple[str, str] | None:
    """Pull watsonx's own error code out of the JSON body echoed in a message."""
    for match in re.finditer(r'\{"errors".*?\}\s*\]', message, re.DOTALL):
        try:
            payload = json.loads(match.group(0) + "}")
        except json.JSONDecodeError:
            continue
        errors = payload.get("errors") or []
        if errors:
            first = errors[0]
            code = str(first.get("code", ""))
            if code:
                return code, str(first.get("message", "")).strip()
    # Fall back to a bare code mention when the body is not cleanly parseable.
    for code in _WATSONX_CODES:
        if code in message:
            return code, ""
    return None


def _key_provenance() -> str:
    """Which file or shell the key in play came from, plus its fingerprint.

    An OS variable silently outranks backend/.env, so an app can run on a stale
    key while the file holds a good one. This is the line that makes that
    visible instead of baffling.
    """
    try:
        import os

        source = value_sources().get("WATSONX_API_KEY", "unset")
        tag = fingerprint(os.environ.get("WATSONX_API_KEY"))
        return f"The key in use came from {source} (fingerprint {tag})."
    except Exception:  # pragma: no cover - diagnostics must never mask the error
        return ""


def _classify(exc: Exception, config: WatsonxConfig) -> str:
    """Turn an IBM SDK failure into a specific, sanitized diagnosis.

    The point is to say which of the four configured values is wrong, rather
    than reporting a generic failure that invites swapping the model at random.
    Only the exception's own message is echoed; no credential passes through.
    """
    status = None
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)

    message = str(getattr(exc, "error_msg", None) or exc)
    where = f"model {config.model_id} at {config.url}"

    # IAM rejections come back without an HTTP status, so they are read first.
    iam = _iam_reason(message)
    if iam:
        code, detail = iam
        explanation = _IAM_CODES.get(code)
        if explanation:
            return (
                f"IBM Cloud rejected the credentials for {where}: {explanation}. "
                f"{_key_provenance()} (IAM {code}: {detail})"
            )
        return (
            f"IBM Cloud rejected the credentials for {where}. "
            f"{_key_provenance()} (IAM {code}: {detail})"
        )

    # watsonx's own code is more specific than the HTTP status, so it wins.
    service = _watsonx_reason(message)
    if service:
        code, detail = service
        explanation = _WATSONX_CODES.get(code)
        if explanation:
            return (
                f"watsonx refused {where}: {explanation}. "
                f"(watsonx {code}{': ' + detail if detail else ''})"
            )

    if status == 401:
        return (
            f"401 authentication failed for {where}. WATSONX_API_KEY is "
            f"invalid, expired, or belongs to another IBM Cloud account. "
            f"IBM said: {message}"
        )
    if status == 403:
        return (
            f"403 permission denied for {where}. The API key's user lacks "
            f"access to WATSONX_PROJECT_ID, or the project's plan does not "
            f"allow this model. IBM said: {message}"
        )
    if status == 404:
        return (
            f"404 not found for {where}. WATSONX_PROJECT_ID does not exist in "
            f"the {config.region} region - a project from another region will "
            f"not resolve here. IBM said: {message}"
        )
    if status == 429:
        return f"429 rate limit or quota exhausted for {where}. IBM said: {message}"
    if "is not supported for this environment" in message:
        return (
            f"WATSONX_MODEL_ID '{config.model_id}' is not served by the "
            f"{config.region} region. Choose a model this region lists, or "
            f"point WATSONX_URL and WATSONX_PROJECT_ID at a region that has "
            f"it. IBM said: {message}"
        )
    if status is not None:
        return f"IBM returned {status} for {where}. IBM said: {message}"
    return f"watsonx call failed for {where}: {message}"


class GraniteClient:
    def __init__(
        self,
        *,
        config: WatsonxConfig | None = None,
        max_new_tokens: int = 1600,
        retries: int = 1,
        budget_guard: bool = True,
    ) -> None:
        try:
            self.config = config or WatsonxConfig.from_env()
        except ConfigError as exc:
            raise LLMError(str(exc)) from exc

        self.max_new_tokens = max_new_tokens
        self.retries = retries
        self.budget_guard = budget_guard
        self._model = None

    @property
    def model_id(self) -> str:
        return self.config.model_id

    @property
    def url(self) -> str:
        return self.config.url

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        try:
            from ibm_watsonx_ai import Credentials
            from ibm_watsonx_ai.foundation_models import ModelInference
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise LLMError(
                "ibm-watsonx-ai is not installed. Run: pip install -e '.[granite]'"
            ) from exc

        try:
            # ModelInference validates model_id against the models this
            # environment actually serves, so an unsupported model fails here.
            self._model = ModelInference(
                model_id=self.config.model_id,
                credentials=Credentials(
                    url=self.config.url, api_key=self.config.api_key
                ),
                project_id=self.config.project_id,
            )
        except Exception as exc:
            raise LLMError(_classify(exc, self.config)) from exc
        return self._model

    @staticmethod
    def _usage(response: dict) -> tuple[int | None, int | None]:
        """Pull the real token counts out of a watsonx chat response, so the
        budget ledger settles on what was actually billed."""
        usage = (response or {}).get("usage") or {}
        return usage.get("prompt_tokens"), usage.get("completion_tokens")

    @staticmethod
    def _was_truncated(response: dict) -> bool:
        """True when the model stopped because it hit the output cap.

        A cut-off reply fails to parse for a reason that has nothing to do with
        the model misunderstanding the schema, and the two need opposite
        responses, so they must not be confused for each other.
        """
        choices = (response or {}).get("choices") or []
        if not choices:
            return False
        return choices[0].get("finish_reason") == "length"

    @staticmethod
    def _text(response: dict) -> str:
        choices = (response or {}).get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message") or {}).get("content") or ""

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        temperature: float = 0.0,
    ) -> T:
        instruction = (
            f"{system}\n\n"
            f"Reply with a single JSON object matching this schema:\n"
            f"{schema.model_json_schema()}"
        )
        question = f"{user}\n\nJSON:"
        messages = [
            {"role": "system", "content": instruction},
            {"role": "user", "content": question},
        ]
        # The reservation must cover everything that goes over the wire.
        prompt = instruction + question

        model = self._ensure_model()

        allowance = self.max_new_tokens
        last_error: Exception | None = None
        truncated = False

        for attempt in range(self.retries + 1):
            reservation = None
            settled = False
            request_attempted = False
            try:
                if self.budget_guard:
                    # Raises BudgetExceeded before any network traffic.
                    reservation = budget.reserve_budget(prompt, allowance)

                try:
                    request_attempted = True
                    response = model.chat(
                        messages=messages,
                        params={"max_tokens": allowance, "temperature": temperature},
                    )
                except Exception as exc:
                    raise LLMError(_classify(exc, self.config)) from exc

                input_tokens, output_tokens = self._usage(response)
                if reservation is not None:
                    budget.settle_budget(reservation, input_tokens, output_tokens)
                    settled = True

                truncated = self._was_truncated(response)
                text = self._text(response)

                try:
                    return parse_structured(text, schema)
                except LLMError as exc:
                    last_error = exc
                    if truncated:
                        # The reply was sound but ran out of room, so repeating
                        # it verbatim would cut at the same place and bill twice
                        # for the same failure. Give the retry room to finish.
                        allowance = min(allowance * 2, MAX_OUTPUT_TOKENS)
            except Exception:
                # Once a request was attempted, an exception cannot prove IBM
                # did not process or bill it. Book the full reservation to keep
                # the local cap conservative. Only failures before the request
                # release their reservation.
                if reservation is not None and not settled:
                    if request_attempted:
                        budget.settle_budget(reservation)
                    else:
                        budget.release_reservation(reservation)
                raise

        if truncated:
            raise LLMError(
                f"Granite ran out of output room on {schema.__name__} even at "
                f"{allowance} tokens, so its reply was cut off mid-structure. "
                f"Raise max_new_tokens, or ask the agent for fewer items."
            )
        raise LLMError(
            f"Granite response never matched {schema.__name__}: {last_error}"
        )
