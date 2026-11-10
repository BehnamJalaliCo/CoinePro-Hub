"""The owner's standing permission to publish a working group's daily output (contract §45, v1.29;
the owner, 2026-11-10: «به صورت خودکار از روز دوم انجام بشه … نه اینکه هر بار من تایید کنم. ۱۰۰ تا
کارگروه راه بندازم اونوقت باید روزی صد بار تایید بدم»).

- growth.memberships.publish: what the owner said once for this company in this working group:
  `{mode: "auto" | "ask", account?, story?, since, by}`. NULL (and `ask`) is today's behaviour:
  each output waits for his tap. `auto`: the hub publishes the package of each routine's delivered
  work by itself, through the company's own publish command on IG-Hub (§44.5).

Additive only; nothing is deleted.

Revision ID: 0059
Revises: 0058
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"

UPGRADE = f"""
ALTER TABLE growth.memberships
    ADD COLUMN publish jsonb CHECK (publish IS NULL OR jsonb_typeof(publish) = 'object');
GRANT UPDATE (publish) ON growth.memberships TO {APP_ROLES};
"""  # noqa: S608 - composed from module constants only

DOWNGRADE = """
ALTER TABLE growth.memberships DROP COLUMN publish;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
