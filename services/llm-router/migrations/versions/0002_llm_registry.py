"""llm registry: connections, task classes, assignments.

- connections: every Claude subscription account and every API key is one
  connection. secret_ref is only an OpenBao path, never the secret itself.
  pricing: {model: {input, output, cache_read, cache_write}} in USD per 1M tokens.
- task_classes: which kinds of work exist and whether they may move to an
  alternative provider (§1.6 "transferable").
- assignments: holding -> company -> department -> role -> task_class; each
  level overrides the one above, field by field.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16
"""

from llm_router.migration_sql import execute_script

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script(
        """
        CREATE SCHEMA llm;
        GRANT USAGE ON SCHEMA llm TO hq_llm_writer, hq_llm_reader;

        CREATE TABLE llm.connections (
            id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            key                text NOT NULL UNIQUE CHECK (key ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
            kind               text NOT NULL CHECK (kind IN ('claude_subscription', 'api')),
            provider           text NOT NULL CHECK (provider ~ '^[a-z0-9_]{2,40}$'),
            display_name       text NOT NULL,
            status             text NOT NULL DEFAULT 'disabled'
                                    CHECK (status IN ('enabled', 'disabled', 'quota_exhausted')),
            status_reason      text,
            status_changed_at  timestamptz NOT NULL DEFAULT now(),
            quota_reset_at     timestamptz,
            secret_ref         text CHECK (secret_ref ~ '^kv/[a-z0-9][a-z0-9/_-]*$'),
            api_base           text,
            models             jsonb NOT NULL DEFAULT '[]'
                                    CHECK (jsonb_typeof(models) = 'array'),
            default_model      text,
            pricing            jsonb NOT NULL DEFAULT '{}'
                                    CHECK (jsonb_typeof(pricing) = 'object'),
            limits             jsonb NOT NULL DEFAULT '{}'
                                    CHECK (jsonb_typeof(limits) = 'object'),
            fallback_priority  int CHECK (fallback_priority > 0),
            created_at         timestamptz NOT NULL DEFAULT now(),
            updated_at         timestamptz NOT NULL DEFAULT now()
        );
        COMMENT ON COLUMN llm.connections.secret_ref IS
            'OpenBao KV path only (e.g. kv/llm-connections/openai); never the key itself';
        COMMENT ON COLUMN llm.connections.fallback_priority IS
            'NULL = never used as an alternative; lower = tried first (§1.6)';

        CREATE TABLE llm.task_classes (
            key           text PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]{1,40}$'),
            transferable  boolean NOT NULL DEFAULT false,
            description   text NOT NULL DEFAULT ''
        );

        CREATE TABLE llm.assignments (
            id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            scope_type     text NOT NULL
                                CHECK (scope_type IN ('holding', 'company', 'department', 'role', 'task_class')),
            scope_ref      text NOT NULL CHECK (length(scope_ref) BETWEEN 1 AND 100),
            connection_id  uuid REFERENCES llm.connections (id),
            model          text,
            effort         text CHECK (effort IN ('low', 'medium', 'high', 'xhigh', 'max')),
            note           text,
            created_at     timestamptz NOT NULL DEFAULT now(),
            updated_at     timestamptz NOT NULL DEFAULT now(),
            UNIQUE (scope_type, scope_ref),
            CHECK (connection_id IS NOT NULL OR model IS NOT NULL OR effort IS NOT NULL)
        );

        GRANT SELECT ON llm.connections, llm.task_classes, llm.assignments
            TO hq_llm_writer, hq_llm_reader;
        -- The router flips health state only (quota guard / breaker).
        GRANT UPDATE (status, status_reason, status_changed_at, quota_reset_at, updated_at)
            ON llm.connections TO hq_llm_writer;
        """
    )


def downgrade() -> None:
    execute_script("DROP TABLE llm.assignments, llm.task_classes, llm.connections; DROP SCHEMA llm")
