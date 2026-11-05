"""Prompt 24 (contract §33.8–33.9). SKELETON: the  the company journey, personas, the persona_test step:journey builder fills it; until then it changes nothing.

Revision ID: 0047
Revises: 0046
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

UPGRADE = r"""
SELECT 1;
"""

DOWNGRADE = r"""
SELECT 1;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
