"""Prompt 5.1 §2.4: a subscription quota state is never `limited` for good.

- llm.quota_status.resets_estimated: true when `resets_at` is not a reset time
  the provider reported but the hold the Quota Controller chose (the circuit
  breaker's retry time, or five hours) because none could be read, as with
  every billing_error. A non-ok state always has a `resets_at` from now on,
  so every reader (the router after a restart, the core's quota view) sees it
  lapse.
- llm.quota_status.windows: the state of each window the CLI reports apart
  (five_hour, seven_day, ...) and of the quota guard and the ledger windows,
  keyed by window; the row's own columns are the worst of them that still
  holds. Metadata only, never content.
- Rows saved before this migration in a non-ok state without a reset time
  would hold for good: they get five hours from when they were observed.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-17
"""

from llm_router.migration_sql import execute_script

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script(
        """
        ALTER TABLE llm.quota_status
            ADD COLUMN resets_estimated boolean NOT NULL DEFAULT false,
            ADD COLUMN windows jsonb NOT NULL DEFAULT '{}'::jsonb
                CHECK (jsonb_typeof(windows) = 'object');
        UPDATE llm.quota_status
           SET resets_at = observed_at + interval '5 hours', resets_estimated = true
         WHERE status <> 'ok' AND resets_at IS NULL;
        ALTER TABLE llm.quota_status ADD CONSTRAINT quota_status_holds_end
            CHECK (status = 'ok' OR resets_at IS NOT NULL);
        COMMENT ON COLUMN llm.quota_status.resets_estimated IS
            'resets_at is the hold the controller chose (breaker retry time or five hours), not a reported reset';
        COMMENT ON COLUMN llm.quota_status.windows IS
            'Per-window states (window -> status, resets_at, source, ...); the row is the worst that holds';
        """
    )


def downgrade() -> None:
    execute_script(
        """
        ALTER TABLE llm.quota_status DROP CONSTRAINT quota_status_holds_end;
        ALTER TABLE llm.quota_status DROP COLUMN windows, DROP COLUMN resets_estimated;
        """
    )
