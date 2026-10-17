"""Prompt 5.1 §2.6 and §3: the daily cap's index; queue_run for the worker only.

- agents.runs (started_at): the hub's daily agent token cap is now checked
  before every model call (not only at claim), summing today's runs; this
  index keeps that a range scan.
- agents.queue_run (SECURITY DEFINER) is called by the worker (requeue,
  daily reports) and by the wake triggers (themselves SECURITY DEFINER, so
  they run as its owner); hq_api never calls it, so it loses EXECUTE.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

SIGNATURE = "agents.queue_run(uuid, text, uuid, uuid, text, text)"


def upgrade() -> None:
    execute_script(
        f"""
        CREATE INDEX IF NOT EXISTS runs_started ON agents.runs (started_at)
            WHERE started_at IS NOT NULL;
        REVOKE EXECUTE ON FUNCTION {SIGNATURE} FROM hq_api;
        """
    )


def downgrade() -> None:
    execute_script(
        f"""
        GRANT EXECUTE ON FUNCTION {SIGNATURE} TO hq_api;
        DROP INDEX IF EXISTS agents.runs_started;
        """
    )
