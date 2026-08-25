"""IBM watsonx.ai API budget guard.

Adapted from the user-supplied `budget_guard.py`, with its design intact:
reserve the worst-case cost BEFORE a call, settle with the real token usage
AFTER, and refuse the call outright if it could push total spend over the cap.
Reservation and settlement are serialized through SQLite so concurrent callers
cannot race past the limit.

Two changes from the original:

1. Prices default to the published rate for granite-3-8b-instruct
   ($0.0002 per 1,000 tokens, input and output alike, since watsonx bills both
   as Resource Units) instead of 0. The original refused to run until prices
   were set by hand; the check that rejects a zero or negative price is kept,
   so an explicit 0 still fails loudly.
2. The database path is configurable via IBM_BUDGET_DB, so the ledger does not
   land inside an installed package directory.

This is an application-side guard, NOT an IBM Cloud billing hard-stop.
"""

import os
import sqlite3
import threading
from decimal import Decimal
from pathlib import Path
from typing import Optional

# ── Hard limit ──────────────────────────────────────────────────────────────

BUDGET_USD = Decimal(os.getenv("IBM_BUDGET_USD", "100.00"))

# Published rate for ibm/granite-3-8b-instruct: 0.0002 USD per Resource Unit,
# where 1 RU = 1,000 tokens counting input and output together. That is
# 0.20 USD per 1,000,000 tokens on each side.
DEFAULT_PRICE_PER_1M = "0.20"

INPUT_PRICE_PER_1M = Decimal(os.getenv("IBM_INPUT_PRICE_PER_1M", DEFAULT_PRICE_PER_1M))
OUTPUT_PRICE_PER_1M = Decimal(os.getenv("IBM_OUTPUT_PRICE_PER_1M", DEFAULT_PRICE_PER_1M))

# Conservative safety margin on every estimate.
SAFETY_FACTOR = Decimal(os.getenv("IBM_BUDGET_SAFETY_FACTOR", "1.10"))

DB_PATH = Path(
    os.getenv("IBM_BUDGET_DB", Path.home() / ".phase_c_ibm_budget.sqlite3")
)

_LOCK = threading.Lock()


class BudgetExceeded(RuntimeError):
    """Raised BEFORE any API call when the cap would be breached."""


def _validate_prices() -> None:
    if INPUT_PRICE_PER_1M <= 0 or OUTPUT_PRICE_PER_1M <= 0:
        raise RuntimeError(
            "IBM model token prices are not configured.\n\n"
            "Set them before running:\n"
            '  $env:IBM_INPUT_PRICE_PER_1M="0.20"\n'
            '  $env:IBM_OUTPUT_PRICE_PER_1M="0.20"\n\n'
            "Use the exact current pricing for the watsonx.ai model you call."
        )


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
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
    input_cost = Decimal(input_tokens) / Decimal("1000000") * INPUT_PRICE_PER_1M
    output_cost = Decimal(output_tokens) / Decimal("1000000") * OUTPUT_PRICE_PER_1M
    return (input_cost + output_cost) * SAFETY_FACTOR


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
    return {
        "budget_usd": float(BUDGET_USD),
        "spent_usd": float(spent),
        "reserved_usd": float(reserved),
        "remaining_usd": float(max(Decimal("0"), BUDGET_USD - spent - reserved)),
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

            if projected > BUDGET_USD:
                raise BudgetExceeded(
                    f"IBM API BLOCKED: ${BUDGET_USD:.2f} budget limit would be exceeded.\n"
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
