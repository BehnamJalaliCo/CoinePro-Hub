"""Prompt 24 (contract §33.1, §33.4–33.6). SKELETON: the  usage reports, leads, affiliate gaps, decisions' money impact:sales builder fills it; until then it changes nothing.

Revision ID: 0046
Revises: 0045
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0046"
down_revision = "0045"
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
