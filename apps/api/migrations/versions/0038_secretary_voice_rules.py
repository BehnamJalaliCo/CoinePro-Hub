"""Prompt 21 part 2 (contract §29.3, §29.4, §29.5, §29.7, §29.8): the owner's rules, the secretary, long voice, Persian only, the council v2.

Revision ID: 0038
Revises: 0037
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

UPGRADE = """
SELECT 1;
"""

DOWNGRADE = """
SELECT 1;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
