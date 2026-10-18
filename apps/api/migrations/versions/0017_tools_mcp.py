"""Prompt 07 §3: the MCP bridge (contract §18.7), and the text of PDF files.

  - tools.mcp_servers: one MCP server the owner registered (🔏 the body) and
    enabled (🔏 the key): its transport (`http` through the egress proxy, or
    `container`: a compose service on the internal hq-mcp network), the tools
    the owner sealed with their class, the companies that may call it.
    Holding configuration, no company rows: only the api reads it (the
    agents' tool goes through POST /internal/v1/tools/mcp/resolve). The
    server's own listing is pinned (`listing_sha256`) the first time the
    gateway sees it after an enable; a different listing later switches the
    server off until the owner seals it again. Never deleted.
  - tools.mcp_calls: one row per resolved call (company, run, server, tool,
    class): the per-run and per-company caps count it. Append-only.
  - files.processing.text: the text of a PDF (pypdf, at upload), for files.read.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"


def upgrade() -> None:
    execute_script(
        rf"""
        CREATE SCHEMA IF NOT EXISTS tools;
        GRANT USAGE ON SCHEMA tools TO {APP_ROLES};

        CREATE TABLE tools.mcp_servers (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            key              text NOT NULL UNIQUE CHECK (key ~ '^[a-z][a-z0-9-]{{1,39}}$'),
            title_fa         text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
            transport        text NOT NULL CHECK (transport IN ('http', 'container')),
            url              text NOT NULL CHECK (length(url) BETWEEN 8 AND 500),
            image            text CHECK (length(image) <= 300),
            tools            jsonb NOT NULL CHECK (jsonb_typeof(tools) = 'array'),
            companies        text[],  -- NULL: every company
            auth_header      text CHECK (auth_header ~ '^[A-Za-z][A-Za-z0-9-]{{0,60}}$'),
            auth_scheme      text CHECK (length(auth_scheme) <= 20),
            status           text NOT NULL DEFAULT 'pending'
                                  CHECK (status IN ('pending', 'enabled', 'disabled')),
            status_reason    text CHECK (length(status_reason) <= 200),
            registration_sha256 text NOT NULL CHECK (registration_sha256 ~ '^[0-9a-f]{{64}}$'),
            listing_sha256   text CHECK (listing_sha256 ~ '^[0-9a-f]{{64}}$'),
            listed_tools     text[],
            listed_at        timestamptz,
            added_by         text NOT NULL,
            added_at         timestamptz NOT NULL DEFAULT now(),
            enabled_at       timestamptz,
            updated_at       timestamptz NOT NULL DEFAULT now(),
            version          int NOT NULL DEFAULT 1
        );
        CREATE TRIGGER mcp_servers_immutable BEFORE UPDATE ON tools.mcp_servers
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'key', 'added_at');
        CREATE TRIGGER mcp_servers_version BEFORE UPDATE ON tools.mcp_servers
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();
        CREATE TRIGGER mcp_servers_no_delete BEFORE DELETE ON tools.mcp_servers
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        GRANT SELECT, INSERT, UPDATE ON tools.mcp_servers TO hq_api;
        GRANT SELECT ON tools.mcp_servers TO hq_worker;

        CREATE TABLE tools.mcp_calls (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            at           timestamptz NOT NULL DEFAULT now(),
            company_id   uuid NOT NULL REFERENCES core.companies (id),
            run_id       uuid,
            actor_code   text NOT NULL CHECK (length(actor_code) <= 64),
            server_key   text NOT NULL CHECK (length(server_key) <= 40),
            tool         text NOT NULL CHECK (length(tool) <= 128),
            class        text NOT NULL CHECK (class IN ('A0', 'A1', 'A2', 'A3')),
            outcome      text NOT NULL CHECK (outcome IN ('resolved', 'decision')),
            args_sha256  text NOT NULL CHECK (args_sha256 ~ '^[0-9a-f]{{64}}$'),
            decision_id  uuid REFERENCES cartable.decisions (id)
        );
        CREATE INDEX mcp_calls_company_at ON tools.mcp_calls (company_id, at DESC);
        CREATE INDEX mcp_calls_run ON tools.mcp_calls (run_id) WHERE run_id IS NOT NULL;
        CREATE TRIGGER mcp_calls_append_only BEFORE UPDATE OR DELETE ON tools.mcp_calls
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        ALTER TABLE tools.mcp_calls ENABLE ROW LEVEL SECURITY;
        ALTER TABLE tools.mcp_calls FORCE ROW LEVEL SECURITY;
        CREATE POLICY mcp_calls_tenant ON tools.mcp_calls TO {APP_ROLES}
            USING (company_id = ANY ((SELECT core.allowed_company_ids())::uuid[]))
            WITH CHECK (company_id = ANY ((SELECT core.allowed_company_ids())::uuid[]));
        CREATE POLICY mcp_calls_owner_role ON tools.mcp_calls TO hq USING (true) WITH CHECK (true);
        GRANT SELECT, INSERT ON tools.mcp_calls TO hq_api;
        GRANT SELECT ON tools.mcp_calls TO hq_worker;

        ALTER TABLE files.processing
            ADD COLUMN text text CHECK (length(text) <= 200000);
        """
    )


def downgrade() -> None:
    execute_script(
        """
        ALTER TABLE files.processing DROP COLUMN text;
        DROP TABLE tools.mcp_calls;
        DROP TABLE tools.mcp_servers;  -- the schema stays: 0016's tools.accounts lives there
        """
    )
