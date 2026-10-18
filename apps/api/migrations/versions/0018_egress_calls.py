"""Prompt 07.1 §1.3: an agent's internet call counts even when its answer is lost.

  - egress.log.call_id: the call's reservation. Reserve writes the call's row
    before the request leaves (its call_id is its own id); the call's log
    entries carry the same call_id. Until they arrive the reservation counts
    as one request (a lost answer, a gateway killed mid-call); once they do,
    it is settled: it counts no more and is not listed.
  - egress.log.requests: how many requests one row stands for (1; more for
    the row that sums a call's entries beyond the log batch's 200).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-18
"""

from hq_api.migration_sql import execute_script

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script(
        """
        ALTER TABLE egress.log ADD COLUMN call_id uuid;
        ALTER TABLE egress.log ADD COLUMN requests int NOT NULL DEFAULT 1
            CHECK (requests BETWEEN 1 AND 1000000);
        CREATE INDEX log_call ON egress.log (call_id) WHERE call_id IS NOT NULL;
        COMMENT ON COLUMN egress.log.call_id IS
            'The tool call''s reservation row (its own id on that row); settled once the call''s entries name it';
        COMMENT ON COLUMN egress.log.requests IS 'Requests this row stands for (an aggregated row: more than 1)';
        """
    )


def downgrade() -> None:
    execute_script(
        """
        DROP INDEX egress.log_call;
        ALTER TABLE egress.log DROP COLUMN requests;
        ALTER TABLE egress.log DROP COLUMN call_id;
        """
    )
