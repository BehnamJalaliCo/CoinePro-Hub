"""Prompt 07 §2 (contract §18.7): the agents' internet, logged.

- egress.log: one row per request an agent's tool sent out through the egress
  service, or that was stopped (blocked_reason): tool, class, method, host,
  status, sizes, time; never a query, URL path, header or body. Append-only,
  RLS by company like every tenant table.
- tools.accounts: the holding's service accounts (metadata and the injection
  policy only; the secret is in OpenBao kv/tools/accounts/<key>, written by
  the owner with `make account-secret`). Holding-level (no company_id):
  `companies` lists who may use one (NULL = every company).

Revision ID: 0016
Revises: 0014
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0016"
down_revision = "0014"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"


def upgrade() -> None:
    execute_script(
        f"""
        CREATE SCHEMA egress;
        GRANT USAGE ON SCHEMA egress TO {APP_ROLES};
        CREATE TABLE egress.log (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            at              timestamptz NOT NULL DEFAULT now(),
            company_id      uuid NOT NULL REFERENCES core.companies (id),
            actor           text NOT NULL CHECK (length(actor) BETWEEN 1 AND 60),
            run_id          uuid,
            tool            text NOT NULL CHECK (tool ~ '^[a-z][a-z_]*(\\.[a-z_]+)?$'),
            kind            text NOT NULL DEFAULT 'request'
                                 CHECK (kind IN ('request', 'connect', 'search', 'browse')),
            class           text NOT NULL CHECK (class IN ('A0', 'A1', 'A2', 'A3')),
            method          text NOT NULL CHECK (length(method) BETWEEN 1 AND 10),
            host            text NOT NULL CHECK (length(host) BETWEEN 1 AND 255),
            status          int CHECK (status BETWEEN 100 AND 999),
            bytes_in        bigint NOT NULL DEFAULT 0 CHECK (bytes_in >= 0),
            bytes_out       bigint NOT NULL DEFAULT 0 CHECK (bytes_out >= 0),
            ms              int NOT NULL DEFAULT 0 CHECK (ms >= 0),
            blocked_reason  text CHECK (blocked_reason ~ '^[a-z][a-z0-9_]{{1,40}}$')
        );
        COMMENT ON TABLE egress.log IS
            'Every request an agent tool sent out (or was refused); metadata only, no URL path or body';
        CREATE INDEX log_company_at ON egress.log (company_id, at DESC);
        CREATE INDEX log_run ON egress.log (run_id) WHERE run_id IS NOT NULL;
        CREATE INDEX log_blocked ON egress.log (at DESC) WHERE blocked_reason IS NOT NULL;
        CREATE TRIGGER log_append_only BEFORE UPDATE OR DELETE ON egress.log
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER log_no_truncate BEFORE TRUNCATE ON egress.log
            FOR EACH STATEMENT EXECUTE FUNCTION core.reject_change();
        ALTER TABLE egress.log ENABLE ROW LEVEL SECURITY;
        ALTER TABLE egress.log FORCE ROW LEVEL SECURITY;
        CREATE POLICY log_tenant ON egress.log TO {APP_ROLES}
            USING (company_id = ANY ((SELECT core.allowed_company_ids())::uuid[]))
            WITH CHECK (company_id = ANY ((SELECT core.allowed_company_ids())::uuid[]));
        CREATE POLICY log_owner_role ON egress.log TO hq USING (true) WITH CHECK (true);
        GRANT SELECT, INSERT ON egress.log TO hq_api;
        GRANT SELECT ON egress.log TO hq_worker;

        CREATE SCHEMA IF NOT EXISTS tools;
        GRANT USAGE ON SCHEMA tools TO {APP_ROLES};
        CREATE TABLE tools.accounts (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            key           text NOT NULL UNIQUE CHECK (key ~ '^[a-z0-9][a-z0-9_.-]{{1,40}}$'),
            site          text NOT NULL CHECK (site ~ '^[a-z0-9]([a-z0-9.-]{{1,251}}[a-z0-9])?$'),
            title_fa      text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
            companies     text[] CHECK (companies IS NULL OR cardinality(companies) BETWEEN 1 AND 100),
            policy        jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(policy) = 'object'),
            created_at    timestamptz NOT NULL DEFAULT now(),
            updated_at    timestamptz NOT NULL DEFAULT now(),
            last_used_at  timestamptz
        );
        COMMENT ON TABLE tools.accounts IS
            'Holding service accounts: metadata and injection policy; the secret is in OpenBao, never here';
        GRANT SELECT, INSERT ON tools.accounts TO hq_api;
        GRANT UPDATE (site, title_fa, companies, policy, updated_at, last_used_at) ON tools.accounts TO hq_api;
        GRANT SELECT ON tools.accounts TO hq_worker;
        """
    )


def downgrade() -> None:
    execute_script(
        """
        DROP TABLE tools.accounts;
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'tools') THEN
                DROP SCHEMA tools;
            END IF;
        END $$;
        DROP TABLE egress.log;
        DROP SCHEMA egress;
        """
    )
