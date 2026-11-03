"""Prompt 21 part 1 (contract §29.1, §29.2, §29.6, §29.10, §29.14): routing by domain, the order report, the delegation budget, automatic hiring.

Revision ID: 0037
Revises: 0036
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0037"
down_revision = "0036"
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
