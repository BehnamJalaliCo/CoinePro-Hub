"""Two owner switches (the owner, 2026-11-14: no idle spend the hub starts by itself; every n8n
automation on the automations board).

- owner.settings.self_work: while true (the default, as before) the hub's own schedules and agents
  start work by themselves. False: an agent run starts only for what the owner asked for (a work
  whose chain leads to his order, his talk, a direct turn of his session, a meeting he called);
  anything else is refused at its claim and its work cancelled, nothing deleted
  (domain/self_work.py).
- owner.settings.flows_off: the keys of the n8n flows (domain/flows.py) the owner switched off from
  the automations board; n8n's call for such a flow makes no order.

Additive: the downgrade drops the two columns.

Revision ID: 0067
Revises: 0066
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None

UPGRADE = """
ALTER TABLE owner.settings ADD COLUMN self_work boolean NOT NULL DEFAULT true;
ALTER TABLE owner.settings ADD COLUMN flows_off text[] NOT NULL DEFAULT '{}'
    CHECK (cardinality(flows_off) <= 100);
GRANT UPDATE (self_work, flows_off) ON owner.settings TO hq_api;
"""

DOWNGRADE = """
ALTER TABLE owner.settings DROP COLUMN flows_off;
ALTER TABLE owner.settings DROP COLUMN self_work;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
