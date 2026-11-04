"""Prompt 23 (contract §32.1–32.4, §32.8): the owner's talk — conversations (CV-0001 ...),
turns and cards. SKELETON: the talk engine's builder fills the tables; until then it only
makes the schema.

Revision ID: 0043
Revises: 0042
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"

UPGRADE = r"""
CREATE SCHEMA talk;
GRANT USAGE ON SCHEMA talk TO @APP@;
"""

DOWNGRADE = r"""
DROP SCHEMA talk CASCADE;
"""


def upgrade() -> None:
    execute_script(UPGRADE.replace("@APP@", APP_ROLES))


def downgrade() -> None:
    execute_script(DOWNGRADE)
