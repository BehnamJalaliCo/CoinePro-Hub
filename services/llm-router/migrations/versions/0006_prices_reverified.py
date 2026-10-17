"""Anthropic prices re-checked on the official page (prompt 04.1 §1.13).

The review expected $0.20/MTok for claude-sonnet-5-5 cache reads; the
official page (2026-10-17) prices cache hits on Opus 5.5 and Sonnet 5.5 at
0.05x base input: $0.20 on Opus 5.5 and $0.10 on Sonnet 5.5. Every Anthropic
price matches the page, so only `as_of` moves. The seed carries the same
table (a test keeps them identical).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17
"""

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

from llm_router.migration_sql import execute_script

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

AS_OF = "2026-10-17"


def _previous() -> dict[str, Any]:
    path = Path(__file__).with_name("0005_official_prices.py")
    spec = importlib.util.spec_from_file_location("m0005", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prices: dict[str, Any] = copy.deepcopy(module.PRICES)
    return prices


PRICES = _previous()
for _price in PRICES.values():
    _price["as_of"] = AS_OF


def upgrade() -> None:
    # Plain JSON of numbers and fixed URLs: no quote can appear in it.
    execute_script(
        f"""
        UPDATE llm.connections SET pricing = '{json.dumps(PRICES)}'::jsonb, updated_at = now()
        WHERE key IN ('claude-max', 'anthropic-api');
        """
    )


def downgrade() -> None:
    pass
