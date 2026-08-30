"""IBM watsonx.ai API budget guard.

Adapted from the user-supplied `budget_guard.py`, with its design intact:
reserve the worst-case cost BEFORE a call, settle with the real token usage
AFTER, and refuse the call outright if it could push total spend over the cap.
Reservation and settlement are serialized through SQLite so concurrent callers
cannot race past the limit.

Changes from the original:

1. The configured Granite model has separate published input and output rates.
   Unknown models must provide both price variables instead of silently using
   the wrong model's price.
2. The database path is configurable via IBM_BUDGET_DB, so the ledger does not
   land inside an installed package directory.
3. Every setting is read when it is used, not when this module is imported, so
   a backend/.env loaded during application startup is honoured.

This is an application-side guard, NOT an IBM Cloud billing hard-stop.
"""

import os
import sqlite3
import threading
from decimal import Decimal
from pathlib import Path
from typing import Optional

# ── Settings ──────────────────────────────────────────────────────

# Official watsonx.ai pay-as-you-go rates for the model shipped in
# backend/.env.example, checked against IBM's supported-models table on
# 2026-08-31. Prices are USD per 1,000,000 tokens. Environment overrides remain
# available because IBM pricing and the selected model can change.
PRICED_MODEL_ID = "ibm/granite-4-h-small"
DEFAULT_INPUT_PRICE_PER_1M = "0.0636"
DEFAULT_OUTPUT_PRICE_PER_1M = "0.265"
DEFAULT_BUDGET_USD = "100.00"
DEFAULT_SAFETY_FACTOR = "1.10"


def budget_usd() -> Decimal:
    """The hard spend cap, normally set by IBM_BUDGET_USD in backend/.env."""
    return Decimal(os.getenv("IBM_BUDGET_USD", DEFAULT_BUDGET_USD))


def _published_default(price: str) -> Decimal:
    model_id = os.getenv("WATSONX_MODEL_ID", "").strip()
    if model_id != PRICED_MODEL_ID:
        shown = model_id or "<unset>"
        raise RuntimeError(
            f"IBM token prices are not configured for WATSONX_MODEL_ID={shown}. "
            "Set IBM_INPUT_PRICE_PER_1M and IBM_OUTPUT_PRICE_PER_1M from the "
            "current IBM watsonx.ai pricing table."
        )
    return Decimal(price)


def input_price_per_1m() -> Decimal:
    configured = os.getenv("IBM_INPUT_PRICE_PER_1M")
    if configured is not None:
        return Decimal(configured)
    return _published_default(DEFAULT_INPUT_PRICE_PER_1M)


def output_price_per_1m() -> Decimal:
    configured = os.getenv("IBM_OUTPUT_PRICE_PER_1M")
    if configured is not None:
        return Decimal(configured)
    return _published_default(DEFAULT_OUTPUT_PRICE_PER_1M)


def safety_factor() -> Decimal:
    """Conservative margin applied to every estimate."""
    return Decimal(os.getenv("IBM_BUDGET_SAFETY_FACTOR", DEFAULT_SAFETY_FACTOR))


def db_path() -> Path:
    return Path(
        os.getenv("IBM_BUDGET_DB", Path.home() / ".phase_c_ibm_budget.sqlite3")
    )


_LOCK = threading.Lock()


class BudgetExceeded(RuntimeError):
    """Raised BEFORE any API call when the cap would be breached."""


def _validate_prices() -> None:
    if input_price_per_1m() <= 0 or output_price_per_1m() <= 0:
        raise RuntimeError(
            "IBM model token prices are not configured.\n\n"
            "Set them before running:\n"
            '  $env:IBM_INPUT_PRICE_PER_1M="<current input rate per 1M>"\n'
            '  $env:IBM_OUTPUT_PRICE_PER_1M="<current output rate per 1M>"\n\n'
            "Use the exact current pricing for the watsonx.ai model you call."
        )


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS budget (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            spent_usd REAL NOT NULL DEFAULT 0,
            reserved_usd REAL NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO budget (id, spent_usd, reserved_usd) VALUES (1, 0, 0)"
    )
    conn.commit()
    return conn


def calculate_cost(input_tokens: int, output_tokens: int) -> Decimal:
    """Estimated cost including the configured safety factor."""
    _validate_prices()
    input_cost = Decimal(input_tokens) / Decimal("1000000") * input_price_per_1m()
    output_cost = Decimal(output_tokens) / Decimal("1000000") * output_price_per_1m()
    return (input_cost + output_cost) * safety_factor()


def conservative_input_token_estimate(text: str) -> int:
    """Pre-request token estimate that deliberately overestimates.

    Uses UTF-8 byte length rather than a model-specific tokenizer. Note this
    overestimates Korean text especially hard (3 bytes per character), which is
    fine for a reservation — settlement corrects it with the real count.
    """
    return max(1, len(text.encode("utf-8")))


def get_budget_status() -> dict:
    conn = _connect()
    spent_usd, reserved_usd = conn.execute(
        "SELECT spent_usd, reserved_usd FROM budget WHERE id = 1"
    ).fetchone()
    conn.close()

    spent = Decimal(str(spent_usd))
    reserved = Decimal(str(reserved_usd))
    cap = budget_usd()
    return {
        "budget_usd": float(cap),
        "spent_usd": float(spent),
        "reserved_usd": float(reserved),
        "remaining_usd": float(max(Decimal("0"), cap - spent - reserved)),
    }


def reserve_budget(prompt: str, max_output_tokens: int) -> Decimal:
    """Reserve the worst-case cost BEFORE calling the API.

    Raises BudgetExceeded — before any network call — if the cap would break.
    """
    maximum_cost = calculate_cost(
        input_tokens=conservative_input_token_estimate(prompt),
        output_tokens=max_output_tokens,
    )

    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            spent_usd, reserved_usd = conn.execute(
                "SELECT spent_usd, reserved_usd FROM budget WHERE id = 1"
            ).fetchone()

            spent = Decimal(str(spent_usd))
            reserved = Decimal(str(reserved_usd))
            projected = spent + reserved + maximum_cost
            cap = budget_usd()

            if projected > cap:
                raise BudgetExceeded(
                    f"IBM API BLOCKED: ${cap:.2f} budget limit would be exceeded.\n"
                    f"Spent:     ${spent:.4f}\n"
                    f"Reserved:  ${reserved:.4f}\n"
                    f"New max:   ${maximum_cost:.4f}\n"
                    f"Projected: ${projected:.4f}"
                )

            conn.execute(
                "UPDATE budget SET reserved_usd = reserved_usd + ? WHERE id = 1",
                (float(maximum_cost),),
            )
            conn.commit()
            return maximum_cost
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def settle_budget(
    reserved_cost: Decimal,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
) -> Decimal:
    """Settle a reservation once the response (and its token usage) is known.

    With no usage available the whole reservation is booked as spent, which
    stays conservative. Returns the amount actually booked.
    """
    if input_tokens is None or output_tokens is None:
        actual_cost = reserved_cost
    else:
        actual_cost = calculate_cost(input_tokens, output_tokens)

    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE budget
                SET reserved_usd = MAX(0, reserved_usd - ?),
                    spent_usd = spent_usd + ?
                WHERE id = 1
                """,
                (float(reserved_cost), float(actual_cost)),
            )
            conn.commit()
            return actual_cost
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def release_reservation(reserved_cost: Decimal) -> None:
    """Drop a reservation without booking spend.

    Used when the call provably never reached IBM (bad credentials, missing
    SDK, a refusal raised locally) — booking those as spend would burn the
    budget on requests that cost nothing.
    """
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE budget SET reserved_usd = MAX(0, reserved_usd - ?) WHERE id = 1",
                (float(reserved_cost),),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def format_status() -> str:
    s = get_budget_status()
    return (
        f"budget ${s['budget_usd']:.2f} | spent ${s['spent_usd']:.4f} | "
        f"reserved ${s['reserved_usd']:.4f} | remaining ${s['remaining_usd']:.4f}"
    )
