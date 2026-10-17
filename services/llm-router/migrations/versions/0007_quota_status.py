"""Quota Controller state (prompt 05 §8) and the test-only fake connection kind.

- llm.quota_status: one row per subscription connection, written by the
  router's Quota Controller (code, no model). Status ok | warning | limited
  from the SDK's rate-limit events (most reliable), the quota guard
  (usage-limit errors) and, if configured, ledger counts over the 5-hour and
  weekly windows. `changed_at` moves only when the status changes, so the
  owner is told once per change. Not tenant data (like llm.connections).
- llm.connections.kind gains 'fake': a connection the test environment's fake
  backend answers with pre-written JSON. Production never seeds one, and the
  router registers no backend for it unless LLM_FAKE_BACKEND=1.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17
"""

from llm_router.migration_sql import execute_script

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script(
        """
        CREATE TABLE llm.quota_status (
            connection_id  uuid PRIMARY KEY REFERENCES llm.connections (id),
            status         text NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'warning', 'limited')),
            window_kind    text CHECK (window_kind ~ '^[a-z0-9_]{2,40}$'),
            utilization    numeric(5, 4) CHECK (utilization BETWEEN 0 AND 1),
            resets_at      timestamptz,
            source         text NOT NULL CHECK (source IN ('sdk_rate_limit_event', 'quota_guard',
                                                           'ledger_window', 'reset')),
            observed_at    timestamptz NOT NULL DEFAULT now(),
            changed_at     timestamptz NOT NULL DEFAULT now()
        );
        COMMENT ON TABLE llm.quota_status IS
            'Subscription quota as the Quota Controller sees it (metadata only)';
        GRANT SELECT, INSERT, UPDATE ON llm.quota_status TO hq_llm_writer;
        GRANT SELECT ON llm.quota_status TO hq_llm_reader;

        ALTER TABLE llm.connections DROP CONSTRAINT connections_kind_check;
        ALTER TABLE llm.connections ADD CONSTRAINT connections_kind_check
            CHECK (kind IN ('claude_subscription', 'api', 'fake'));
        """
    )


def downgrade() -> None:
    execute_script(
        """
        DROP TABLE llm.quota_status;
        ALTER TABLE llm.connections DROP CONSTRAINT connections_kind_check;
        ALTER TABLE llm.connections ADD CONSTRAINT connections_kind_check
            CHECK (kind IN ('claude_subscription', 'api'));
        """
    )
