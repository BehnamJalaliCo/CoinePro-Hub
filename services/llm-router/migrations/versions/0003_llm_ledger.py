"""llm ledger (Token Treasury): calls, usage counters, budgets, transcripts + RLS.

Row-level security, keyed on company_id and the session variable
app.company_ids (a uuid[] literal set per transaction with SET LOCAL):
  - hq_llm_writer: select/insert/update rows of the permitted companies
  - hq_llm_reader: select rows of the permitted companies
  - nobody may delete ledger rows (only the owner purges expired transcripts)
FORCE ROW LEVEL SECURITY also binds the table owner. Partitions get no
grants, so the parent's policies cannot be bypassed through them.

Prompt and response text never go into llm.calls. llm.transcripts is opt-in
per call (store_transcript=true) and expires.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-16
"""

from llm_router.migration_sql import execute_script

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

RLS_TABLES = ("calls", "usage", "budgets", "transcripts")


def upgrade() -> None:
    execute_script(
        """
        -- Companies this session may see/write; empty (no rows) when unset.
        CREATE FUNCTION llm.allowed_company_ids() RETURNS uuid[]
            LANGUAGE sql STABLE PARALLEL SAFE
            AS $$ SELECT COALESCE(NULLIF(current_setting('app.company_ids', true), '')::uuid[],
                                  '{}'::uuid[]) $$;
        GRANT EXECUTE ON FUNCTION llm.allowed_company_ids() TO hq_llm_writer, hq_llm_reader;

        -- One row per model call, written by llm-router (status running -> final).
        CREATE TABLE llm.calls (
            id                  uuid NOT NULL,
            started_at          timestamptz NOT NULL,
            finished_at         timestamptz,
            company_id          uuid NOT NULL REFERENCES core.companies (id),
            department          text,
            actor_ref           text NOT NULL,
            work_ref            text,
            task_class          text NOT NULL,
            priority            smallint NOT NULL CHECK (priority BETWEEN 0 AND 4),
            caller              text NOT NULL,
            connection_id       uuid REFERENCES llm.connections (id),
            provider            text,
            model               text,
            effort              text,
            input_tokens        integer CHECK (input_tokens >= 0),
            output_tokens       integer CHECK (output_tokens >= 0),
            cache_read_tokens   integer CHECK (cache_read_tokens >= 0),
            cache_write_tokens  integer CHECK (cache_write_tokens >= 0),
            thinking_tokens     integer CHECK (thinking_tokens >= 0),
            cost_usd            numeric(14, 6),
            equiv_cost_usd      numeric(14, 6),
            latency_ms          integer,
            status              text NOT NULL CHECK (status IN (
                                    'running', 'ok', 'error', 'refusal', 'timeout',
                                    'rate_limited', 'quota_exhausted', 'rejected_budget')),
            error_class         text,
            meta                jsonb NOT NULL DEFAULT '{}',
            PRIMARY KEY (id, started_at)
        ) PARTITION BY RANGE (started_at);
        COMMENT ON COLUMN llm.calls.thinking_tokens IS
            'NULL when the backend does not report thinking separately; then it is inside output_tokens';
        COMMENT ON COLUMN llm.calls.equiv_cost_usd IS
            'Subscription calls: the SDK total_cost_usd (API-price equivalent of the quota used)';

        CREATE TABLE llm.calls_default PARTITION OF llm.calls DEFAULT;
        CREATE INDEX calls_company_started_idx ON llm.calls (company_id, started_at);
        CREATE INDEX calls_actor_started_idx ON llm.calls (actor_ref, started_at);
        CREATE INDEX calls_running_idx ON llm.calls (started_at) WHERE status = 'running';

        -- Monthly partitions, created ahead by the router (daily) and the migrate job.
        CREATE FUNCTION llm.ensure_calls_partitions(p_months_ahead integer DEFAULT 3)
            RETURNS integer
            LANGUAGE plpgsql SECURITY DEFINER
            SET search_path = pg_catalog, llm
            AS $$
        DECLARE
            month_start date;
            part_name   text;
            created     integer := 0;
        BEGIN
            FOR i IN 0..p_months_ahead LOOP
                month_start := (date_trunc('month', now() AT TIME ZONE 'UTC')
                                + make_interval(months => i))::date;
                part_name := format('calls_%s', to_char(month_start, 'YYYY_MM'));
                IF to_regclass(format('llm.%I', part_name)) IS NULL THEN
                    EXECUTE format(
                        'CREATE TABLE llm.%I PARTITION OF llm.calls FOR VALUES FROM (%L) TO (%L)',
                        part_name,
                        month_start::timestamp AT TIME ZONE 'UTC',
                        (month_start + interval '1 month')::timestamp AT TIME ZONE 'UTC');
                    created := created + 1;
                END IF;
            END LOOP;
            RETURN created;
        END $$;
        REVOKE ALL ON FUNCTION llm.ensure_calls_partitions(integer) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION llm.ensure_calls_partitions(integer) TO hq_llm_writer;
        SELECT llm.ensure_calls_partitions(3);

        -- Running totals per budget scope and period (O(1) budget checks).
        -- company_id = the company that owns the scope (the holding for
        -- holding-, role- and task-class-wide scopes).
        CREATE TABLE llm.usage (
            company_id    uuid NOT NULL REFERENCES core.companies (id),
            scope_type    text NOT NULL
                               CHECK (scope_type IN ('holding', 'company', 'department', 'role', 'task_class')),
            scope_ref     text NOT NULL,
            period        text NOT NULL CHECK (period IN ('day', 'month')),
            period_start  date NOT NULL,
            calls         bigint NOT NULL DEFAULT 0,
            tokens        bigint NOT NULL DEFAULT 0,
            usd           numeric(16, 6) NOT NULL DEFAULT 0,
            updated_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (scope_type, scope_ref, period, period_start)
        );

        CREATE TABLE llm.budgets (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id          uuid NOT NULL REFERENCES core.companies (id),
            scope_type          text NOT NULL
                                     CHECK (scope_type IN ('holding', 'company', 'department', 'role', 'task_class')),
            scope_ref           text NOT NULL,
            period              text NOT NULL CHECK (period IN ('day', 'month')),
            token_limit         bigint CHECK (token_limit > 0),
            usd_limit           numeric(14, 4) CHECK (usd_limit > 0),
            enabled             boolean NOT NULL DEFAULT true,
            alert_level         smallint NOT NULL DEFAULT 0 CHECK (alert_level IN (0, 70, 90, 100)),
            alert_period_start  date,
            created_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now(),
            UNIQUE (scope_type, scope_ref, period),
            CHECK (token_limit IS NOT NULL OR usd_limit IS NOT NULL)
        );

        CREATE TABLE llm.transcripts (
            call_id     uuid PRIMARY KEY,
            company_id  uuid NOT NULL REFERENCES core.companies (id),
            created_at  timestamptz NOT NULL DEFAULT now(),
            expires_at  timestamptz NOT NULL,
            request     jsonb NOT NULL,
            response    text,
            structured  jsonb
        );
        CREATE INDEX transcripts_expires_idx ON llm.transcripts (expires_at);

        GRANT SELECT, INSERT, UPDATE ON llm.calls, llm.usage TO hq_llm_writer;
        GRANT SELECT, INSERT ON llm.transcripts TO hq_llm_writer;
        GRANT SELECT ON llm.budgets TO hq_llm_writer;
        GRANT UPDATE (alert_level, alert_period_start, updated_at) ON llm.budgets TO hq_llm_writer;
        GRANT SELECT ON llm.calls, llm.usage, llm.budgets, llm.transcripts TO hq_llm_reader;
        """
    )
    for table in RLS_TABLES:
        execute_script(
            f"""
            ALTER TABLE llm.{table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE llm.{table} FORCE ROW LEVEL SECURITY;
            CREATE POLICY {table}_select ON llm.{table} FOR SELECT
                TO hq_llm_reader, hq_llm_writer
                USING (company_id = ANY (llm.allowed_company_ids()));
            CREATE POLICY {table}_insert ON llm.{table} FOR INSERT
                TO hq_llm_writer
                WITH CHECK (company_id = ANY (llm.allowed_company_ids()));
            CREATE POLICY {table}_update ON llm.{table} FOR UPDATE
                TO hq_llm_writer
                USING (company_id = ANY (llm.allowed_company_ids()))
                WITH CHECK (company_id = ANY (llm.allowed_company_ids()));
            """
        )
    execute_script(
        """
        -- The owner may only see and delete transcripts that have expired.
        CREATE POLICY transcripts_owner_purge_select ON llm.transcripts FOR SELECT
            TO hq USING (expires_at < now());
        CREATE POLICY transcripts_owner_purge_delete ON llm.transcripts FOR DELETE
            TO hq USING (expires_at < now());

        CREATE FUNCTION llm.purge_expired_transcripts() RETURNS integer
            LANGUAGE plpgsql SECURITY DEFINER
            SET search_path = pg_catalog, llm
            AS $$
        DECLARE n integer;
        BEGIN
            DELETE FROM llm.transcripts WHERE expires_at < now();
            GET DIAGNOSTICS n = ROW_COUNT;
            RETURN n;
        END $$;
        REVOKE ALL ON FUNCTION llm.purge_expired_transcripts() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION llm.purge_expired_transcripts() TO hq_llm_writer;
        """
    )


def downgrade() -> None:
    execute_script(
        """
        DROP FUNCTION llm.purge_expired_transcripts();
        DROP TABLE llm.transcripts, llm.budgets, llm.usage, llm.calls;
        DROP FUNCTION llm.ensure_calls_partitions(integer);
        DROP FUNCTION llm.allowed_company_ids();
        """
    )
