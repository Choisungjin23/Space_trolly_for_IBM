"""The budget guard refuses before the network and settles conservatively."""

import os
from decimal import Decimal

import pytest
from pydantic import BaseModel

from phase_c.llm import budget as budget_module


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """A fresh ledger per test, with known prices.

    Set through the environment rather than module attributes, because the
    guard reads every setting when it is used - that is what lets a value in
    backend/.env take effect.
    """
    monkeypatch.setenv("IBM_BUDGET_DB", str(tmp_path / "b.sqlite3"))
    monkeypatch.setenv("IBM_BUDGET_USD", "100.00")
    monkeypatch.setenv("IBM_INPUT_PRICE_PER_1M", "0.20")
    monkeypatch.setenv("IBM_OUTPUT_PRICE_PER_1M", "0.20")
    monkeypatch.setenv("IBM_BUDGET_SAFETY_FACTOR", "1.10")
    return budget_module


def test_starts_empty(ledger):
    s = ledger.get_budget_status()
    assert s["spent_usd"] == 0 and s["reserved_usd"] == 0
    assert s["remaining_usd"] == 100.0


def test_reserve_then_settle_with_real_usage(ledger):
    reservation = ledger.reserve_budget("hello world", max_output_tokens=1000)
    assert ledger.get_budget_status()["reserved_usd"] > 0

    booked = ledger.settle_budget(reservation, input_tokens=100, output_tokens=200)
    s = ledger.get_budget_status()
    assert s["reserved_usd"] == pytest.approx(0.0, abs=1e-9)
    assert s["spent_usd"] == pytest.approx(float(booked))
    # Real usage was far below the worst case, so spend < reservation.
    assert booked < reservation


def test_settle_without_usage_books_the_whole_reservation(ledger):
    reservation = ledger.reserve_budget("x" * 500, max_output_tokens=1000)
    booked = ledger.settle_budget(reservation, None, None)
    assert booked == reservation


def test_release_returns_the_reservation_unspent(ledger):
    reservation = ledger.reserve_budget("hello", max_output_tokens=1000)
    ledger.release_reservation(reservation)
    s = ledger.get_budget_status()
    assert s["reserved_usd"] == pytest.approx(0.0, abs=1e-9)
    assert s["spent_usd"] == 0.0


def test_blocks_before_the_call_when_the_cap_would_break(ledger, monkeypatch):
    monkeypatch.setenv("IBM_BUDGET_USD", "0.01")
    with pytest.raises(ledger.BudgetExceeded) as exc:
        ledger.reserve_budget("x" * 100_000, max_output_tokens=100_000)
    assert "BLOCKED" in str(exc.value)
    # Nothing was reserved or spent by the rejected attempt.
    s = ledger.get_budget_status()
    assert s["reserved_usd"] == 0.0 and s["spent_usd"] == 0.0


def test_reservations_accumulate_until_settled(ledger):
    a = ledger.reserve_budget("one", max_output_tokens=1000)
    b = ledger.reserve_budget("two", max_output_tokens=1000)
    assert ledger.get_budget_status()["reserved_usd"] == pytest.approx(float(a + b))


def test_zero_price_is_still_rejected(ledger, monkeypatch):
    """The original guard's safety property: never account a call as free."""
    monkeypatch.setenv("IBM_INPUT_PRICE_PER_1M", "0")
    with pytest.raises(RuntimeError, match="prices are not configured"):
        ledger.calculate_cost(10, 10)


def test_default_prices_match_the_published_granite_rates(monkeypatch):
    monkeypatch.setenv("WATSONX_MODEL_ID", budget_module.PRICED_MODEL_ID)
    monkeypatch.delenv("IBM_INPUT_PRICE_PER_1M", raising=False)
    monkeypatch.delenv("IBM_OUTPUT_PRICE_PER_1M", raising=False)

    assert budget_module.input_price_per_1m() == Decimal("0.0636")
    assert budget_module.output_price_per_1m() == Decimal("0.265")


def test_unknown_model_requires_explicit_prices(monkeypatch):
    monkeypatch.setenv("WATSONX_MODEL_ID", "ibm/another-model")
    monkeypatch.delenv("IBM_INPUT_PRICE_PER_1M", raising=False)
    monkeypatch.delenv("IBM_OUTPUT_PRICE_PER_1M", raising=False)

    with pytest.raises(RuntimeError, match="not configured"):
        budget_module.calculate_cost(10, 10)


def test_the_cap_is_read_when_it_is_used_not_at_import(monkeypatch):
    """backend/.env is loaded after this module is first imported, so a cap
    captured at import time would silently ignore IBM_BUDGET_USD."""
    monkeypatch.setenv("IBM_BUDGET_USD", "5.00")
    assert budget_module.budget_usd() == Decimal("5.00")


def test_korean_prompts_overestimate_conservatively(ledger):
    """UTF-8 byte length inflates Korean text ~3x. That is intended for a
    reservation, but it must not be mistaken for an accurate count."""
    korean = "우주선 화재"
    assert ledger.conservative_input_token_estimate(korean) > len(korean)


# ── GraniteClient wiring ────────────────────────────────────────────────────

@pytest.fixture
def configured(monkeypatch):
    """Every required watsonx value present, so a test can remove exactly one."""
    monkeypatch.setenv("WATSONX_API_KEY", "k" * 20)
    monkeypatch.setenv("WATSONX_PROJECT_ID", "proj-1")
    monkeypatch.setenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    monkeypatch.setenv("WATSONX_MODEL_ID", "ibm/granite-4-h-small")
    monkeypatch.delenv("WATSONX_APIKEY_FILE", raising=False)
    return monkeypatch


def test_client_refuses_without_a_project_id(configured):
    from phase_c.llm.base import LLMError
    from phase_c.llm.granite import GraniteClient

    configured.delenv("WATSONX_PROJECT_ID", raising=False)
    with pytest.raises(LLMError, match="WATSONX_PROJECT_ID"):
        GraniteClient()


def test_client_refuses_without_a_model_id(configured):
    """No default model: an unset WATSONX_MODEL_ID must fail rather than fall
    back to whatever the code was last pinned to."""
    from phase_c.llm.base import LLMError
    from phase_c.llm.granite import GraniteClient

    configured.delenv("WATSONX_MODEL_ID", raising=False)
    with pytest.raises(LLMError, match="WATSONX_MODEL_ID"):
        GraniteClient()


def test_client_refuses_without_a_url(configured):
    from phase_c.llm.base import LLMError
    from phase_c.llm.granite import GraniteClient

    configured.delenv("WATSONX_URL", raising=False)
    with pytest.raises(LLMError, match="WATSONX_URL"):
        GraniteClient()


def test_client_refuses_unedited_example_placeholders(configured):
    from phase_c.llm.base import LLMError
    from phase_c.llm.granite import GraniteClient

    configured.setenv("WATSONX_URL", "https://YOUR_REGION.ml.cloud.ibm.com")
    with pytest.raises(LLMError, match="WATSONX_URL"):
        GraniteClient()


def test_client_takes_region_and_model_from_the_environment(configured):
    from phase_c.llm.granite import GraniteClient

    configured.setenv("WATSONX_URL", "https://eu-de.ml.cloud.ibm.com")
    configured.setenv("WATSONX_MODEL_ID", "ibm/some-other-model")

    client = GraniteClient()

    assert client.model_id == "ibm/some-other-model"
    assert client.url == "https://eu-de.ml.cloud.ibm.com"
    assert client.config.region == "eu-de"


def test_client_reads_the_key_from_a_file_without_copying_it(tmp_path, configured):
    import json

    from phase_c.llm.granite import GraniteClient

    key_file = tmp_path / "apikey.json"
    key_file.write_text(json.dumps({"name": "x", "apikey": "SECRET-VALUE"}), "utf-8")

    configured.delenv("WATSONX_API_KEY", raising=False)
    configured.setenv("WATSONX_APIKEY_FILE", str(key_file))

    client = GraniteClient()
    assert client.config.api_key == "SECRET-VALUE"
    # The key must not have been written anywhere in the project.
    assert not any(
        "SECRET-VALUE" in p.read_text("utf-8", errors="ignore")
        for p in tmp_path.rglob("*")
        if p.is_file() and p != key_file
    )


def test_client_reports_a_missing_key_file(tmp_path, configured):
    from phase_c.llm.base import LLMError
    from phase_c.llm.granite import GraniteClient

    configured.delenv("WATSONX_API_KEY", raising=False)
    configured.setenv("WATSONX_APIKEY_FILE", str(tmp_path / "nope.json"))
    with pytest.raises(LLMError, match="missing file"):
        GraniteClient()


def test_usage_extraction_from_a_watsonx_chat_response():
    from phase_c.llm.granite import GraniteClient

    response = {
        "choices": [{"message": {"content": '{"status": "ok"}'}}],
        "usage": {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168},
    }
    assert GraniteClient._usage(response) == (123, 45)
    assert GraniteClient._text(response) == '{"status": "ok"}'
    # An empty reply must settle as unknown usage, not as a free call.
    assert GraniteClient._usage({}) == (None, None)
    assert GraniteClient._text({}) == ""


# ── Truncated replies ───────────────────────────────────────────────────────

def _chat_response(text: str, finish_reason: str = "stop") -> dict:
    return {
        "choices": [{"message": {"content": text}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }


class _Reply(BaseModel):
    status: str


def test_truncation_is_detected_from_the_finish_reason():
    from phase_c.llm.granite import GraniteClient

    assert GraniteClient._was_truncated(_chat_response("{", "length")) is True
    assert GraniteClient._was_truncated(_chat_response("{}", "stop")) is False
    assert GraniteClient._was_truncated({}) is False


def test_a_truncated_reply_retries_with_more_room(ledger, configured):
    """Repeating a cut-off request verbatim cuts at the same place and bills
    twice for the same failure, so the retry must be given room to finish."""
    from phase_c.llm.granite import GraniteClient

    caps: list[int] = []

    class Model:
        def chat(self, *, messages, params):
            caps.append(params["max_tokens"])
            if len(caps) == 1:
                return _chat_response('{"status": "o', "length")
            return _chat_response('{"status": "ok"}', "stop")

    client = GraniteClient(max_new_tokens=100, retries=1)
    client._model = Model()

    result = client.complete(system="AGENT: t", user="go", schema=_Reply)

    assert result.status == "ok"
    assert caps == [100, 200], "the retry should double the allowance"


def test_persistent_truncation_says_so_plainly(ledger, configured):
    from phase_c.llm.base import LLMError
    from phase_c.llm.granite import GraniteClient

    class Model:
        def chat(self, *, messages, params):
            return _chat_response('{"status": "o', "length")

    client = GraniteClient(max_new_tokens=100, retries=1)
    client._model = Model()

    with pytest.raises(LLMError, match="ran out of output room"):
        client.complete(system="AGENT: t", user="go", schema=_Reply)


def test_a_malformed_but_complete_reply_does_not_grow_the_allowance(ledger, configured):
    """Only truncation justifies spending more; a model that misread the schema
    will misread it again at twice the size."""
    from phase_c.llm.base import LLMError
    from phase_c.llm.granite import GraniteClient

    caps: list[int] = []

    class Model:
        def chat(self, *, messages, params):
            caps.append(params["max_tokens"])
            return _chat_response("not json at all", "stop")

    client = GraniteClient(max_new_tokens=100, retries=1)
    client._model = Model()

    with pytest.raises(LLMError, match="never matched"):
        client.complete(system="AGENT: t", user="go", schema=_Reply)
    assert caps == [100, 100]


def test_failed_api_attempt_books_the_full_reservation(ledger, configured):
    """A transport error can arrive after IBM accepted a request. Treating it
    as free could let repeated failures pass the local hard cap."""
    from phase_c.llm.base import LLMError
    from phase_c.llm.granite import GraniteClient

    class Model:
        def chat(self, *, messages, params):
            raise RuntimeError("connection dropped after send")

    client = GraniteClient(max_new_tokens=100, retries=0)
    client._model = Model()

    with pytest.raises(LLMError, match="connection dropped"):
        client.complete(system="AGENT: t", user="go", schema=_Reply)

    status = ledger.get_budget_status()
    assert status["reserved_usd"] == pytest.approx(0.0, abs=1e-9)
    assert status["spent_usd"] > 0
