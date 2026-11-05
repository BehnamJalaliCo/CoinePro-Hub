"""Prompt 24 (contract §33.7, §33.10). SKELETON: the  work split into parallel parts, workspaces on company servers:engine builder fills it; until then it changes nothing.

Revision ID: 0048
Revises: 0047
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0048"
down_revision = "0047"
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
