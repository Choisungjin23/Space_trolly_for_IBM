"""The budget guard must refuse before the network, settle on real usage, and
never book spend for a call that failed locally."""

import os
from decimal import Decimal

import pytest

from phase_c.llm import budget as budget_module


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """A fresh ledger per test, with known prices."""
    monkeypatch.setattr(budget_module, "DB_PATH", tmp_path / "b.sqlite3")
    monkeypatch.setattr(budget_module, "BUDGET_USD", Decimal("100.00"))
    monkeypatch.setattr(budget_module, "INPUT_PRICE_PER_1M", Decimal("0.20"))
    monkeypatch.setattr(budget_module, "OUTPUT_PRICE_PER_1M", Decimal("0.20"))
    monkeypatch.setattr(budget_module, "SAFETY_FACTOR", Decimal("1.10"))
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
    monkeypatch.setattr(ledger, "BUDGET_USD", Decimal("0.01"))
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
    monkeypatch.setattr(ledger, "INPUT_PRICE_PER_1M", Decimal("0"))
    with pytest.raises(RuntimeError, match="prices are not configured"):
        ledger.calculate_cost(10, 10)


def test_default_price_matches_the_published_granite_rate():
    # 0.0002 USD per 1,000 tokens = 0.20 USD per 1,000,000.
    assert budget_module.DEFAULT_PRICE_PER_1M == "0.20"


def test_korean_prompts_overestimate_conservatively(ledger):
    """UTF-8 byte length inflates Korean text ~3x. That is intended for a
    reservation, but it must not be mistaken for an accurate count."""
    korean = "우주선 화재"
    assert ledger.conservative_input_token_estimate(korean) > len(korean)


# ── GraniteClient wiring ────────────────────────────────────────────────────

def test_client_refuses_without_a_project_id(monkeypatch):
    from phase_c.llm.base import LLMError
    from phase_c.llm.granite import GraniteClient

    monkeypatch.setenv("WATSONX_API_KEY", "k" * 20)
    monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
    with pytest.raises(LLMError, match="WATSONX_PROJECT_ID"):
        GraniteClient()


def test_client_reads_the_key_from_a_file_without_copying_it(tmp_path, monkeypatch):
    import json

    from phase_c.llm.granite import GraniteClient

    key_file = tmp_path / "apikey.json"
    key_file.write_text(json.dumps({"name": "x", "apikey": "SECRET-VALUE"}), "utf-8")

    monkeypatch.delenv("WATSONX_API_KEY", raising=False)
    monkeypatch.setenv("WATSONX_APIKEY_FILE", str(key_file))
    monkeypatch.setenv("WATSONX_PROJECT_ID", "proj-1")

    client = GraniteClient()
    assert client.api_key == "SECRET-VALUE"
    # The key must not have been written anywhere in the project.
    assert not any(
        "SECRET-VALUE" in p.read_text("utf-8", errors="ignore")
        for p in tmp_path.rglob("*")
        if p.is_file() and p != key_file
    )


def test_client_reports_a_missing_key_file(tmp_path, monkeypatch):
    from phase_c.llm.base import LLMError
    from phase_c.llm.granite import GraniteClient

    monkeypatch.delenv("WATSONX_API_KEY", raising=False)
    monkeypatch.setenv("WATSONX_APIKEY_FILE", str(tmp_path / "nope.json"))
    monkeypatch.setenv("WATSONX_PROJECT_ID", "proj-1")
    with pytest.raises(LLMError, match="missing file"):
        GraniteClient()


def test_usage_extraction_from_a_watsonx_response():
    from phase_c.llm.granite import GraniteClient

    response = {
        "results": [
            {
                "generated_text": '{"status": "ok"}',
                "input_token_count": 123,
                "generated_token_count": 45,
            }
        ]
    }
    assert GraniteClient._usage(response) == (123, 45)
    assert GraniteClient._usage({}) == (None, None)
