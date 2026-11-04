"""Prompt 23 (contract §32.5–32.6): the voice engines' state (the light) and the meter's
usage rows, in schema talk. SKELETON: the voice layer's builder fills it; until then it
changes nothing.

Revision ID: 0044
Revises: 0043
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0044"
down_revision = "0043"
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
