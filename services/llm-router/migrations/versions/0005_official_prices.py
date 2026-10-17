"""Official Anthropic prices on the Anthropic connections (owner decision, prompt 04 §9).

Our price table becomes the only cost source, so the claude-max and
anthropic-api rows get the prices of the official pricing page, each with
source_url and as_of; Claude Haiku 5.5 gets its long-prompt tier and every
model its 1-hour cache-write rate. The owner's decision overrides the
seed's "never overwrite" rule for these two rows. A fresh database gets the
same table from seed/connections.yaml (a test keeps both identical).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-16
"""

import json
from typing import Any

from llm_router.migration_sql import execute_script

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

SOURCE = {
    "source_url": "https://platform.claude.com/docs/en/about-claude/pricing",
    "as_of": "2026-10-16",
}
PRICES: dict[str, Any] = {
    "claude-fable-5-1": {
        "input": 10.00,
        "output": 50.00,
        "cache_read": 0.25,
        "cache_write": 12.50,
        "cache_write_1h": 20.00,
        **SOURCE,
    },
    "claude-opus-5-5": {
        "input": 4.00,
        "output": 20.00,
        "cache_read": 0.20,
        "cache_write": 5.00,
        "cache_write_1h": 8.00,
        **SOURCE,
    },
    "claude-sonnet-5-5": {
        "input": 2.00,
        "output": 10.00,
        "cache_read": 0.10,
        "cache_write": 2.50,
        "cache_write_1h": 4.00,
        **SOURCE,
    },
    "claude-haiku-5-5": {
        "input": 0.10,
        "output": 0.50,
        "cache_read": 0.01,
        "cache_write": 0.125,
        "cache_write_1h": 0.20,
        "long_prompt": {
            "above_prompt_tokens": 100000,
            "input": 0.50,
            "output": 2.50,
            "cache_read": 0.05,
            "cache_write": 0.625,
            "cache_write_1h": 1.00,
        },
        **SOURCE,
    },
}


def upgrade() -> None:
    # Plain JSON of numbers and fixed URLs: no quote can appear in it.
    execute_script(
        f"""
        UPDATE llm.connections SET pricing = '{json.dumps(PRICES)}'::jsonb, updated_at = now()
        WHERE key IN ('claude-max', 'anthropic-api');
        """
    )


def downgrade() -> None:
    """Prices are data: a downgrade keeps them."""
