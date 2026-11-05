"""Prompt 24 (contract §33.2–33.3). SKELETON: the  crypto payments read and reconciled, revenue board caches:money builder fills it; until then it changes nothing.

Revision ID: 0045
Revises: 0044
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0045"
down_revision = "0044"
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
