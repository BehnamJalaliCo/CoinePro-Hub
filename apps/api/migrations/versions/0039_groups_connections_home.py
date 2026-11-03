"""Prompt 21 part 3 (contract §29.9, §29.11, §29.12, §29.13): working groups, connections, the owner's home, readiness.

Revision ID: 0039
Revises: 0038
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0039"
down_revision = "0038"
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
