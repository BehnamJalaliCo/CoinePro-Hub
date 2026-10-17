"""Prompt 07 §1 (contract §18.9): what the API knows of the backups.

The backups themselves run on the host (infra/backup: WAL-G, restic,
rclone); the api has no restic, Docker or credentials. The scripts write
metadata-only status files; the worker reads them (Maintenance, every 5 min)
into:
- backup.status         the latest status (one row, the holding's)
- backup.runs           one row per hourly run (append-only): the source of
                        backup.done / backup.failed on the stream
- backup.snapshots      the snapshots each repository lists now (a mirror)
- backup.restore_tests  the weekly automatic restore test (append-only)
All rows belong to the holding; RLS like every tenant table. Nothing here
can start a restore (contract §18.9).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"


def _rls(table: str) -> str:
    name = table.split(".")[1]
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
        CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
    """


def upgrade() -> None:
    execute_script(
        f"""
        CREATE SCHEMA backup;
        GRANT USAGE ON SCHEMA backup TO {APP_ROLES};

        CREATE TABLE backup.status (
            company_id  uuid PRIMARY KEY REFERENCES core.companies (id),
            at          timestamptz NOT NULL DEFAULT now(),
            hourly      jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(hourly) = 'object'),
            restore     jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(restore) = 'object')
        );
        COMMENT ON TABLE backup.status IS
            'Latest hourly status and restore-test file of the host backup (metadata only, no secret)';

        CREATE TABLE backup.runs (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id    uuid NOT NULL REFERENCES core.companies (id),
            at            timestamptz NOT NULL,
            ok            boolean NOT NULL,
            snapshot      text CHECK (snapshot ~ '^[0-9a-f]{{8,64}}$'),
            size_bytes    bigint CHECK (size_bytes >= 0),
            duration_s    int CHECK (duration_s >= 0),
            error         text CHECK (length(error) <= 300),
            destinations  jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(destinations) = 'array'),
            UNIQUE (company_id, at)
        );
        CREATE INDEX runs_at ON backup.runs (company_id, at DESC);
        CREATE TRIGGER runs_append_only BEFORE DELETE OR UPDATE ON backup.runs
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        CREATE TABLE backup.snapshots (
            company_id   uuid NOT NULL REFERENCES core.companies (id),
            destination  text NOT NULL CHECK (destination IN ('local', 'gdrive', 'hetzner')),
            snapshot_id  text NOT NULL CHECK (snapshot_id ~ '^[0-9a-f]{{8,64}}$'),
            time         timestamptz NOT NULL,
            size_bytes   bigint CHECK (size_bytes >= 0),
            tags         text[] NOT NULL DEFAULT '{{}}',
            seen_at      timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, destination, snapshot_id)
        );
        CREATE INDEX snapshots_time ON backup.snapshots (company_id, time DESC);

        CREATE TABLE backup.restore_tests (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  uuid NOT NULL REFERENCES core.companies (id),
            at          timestamptz NOT NULL,
            ok          boolean NOT NULL,
            duration_s  int CHECK (duration_s >= 0),
            source      text CHECK (source IN ('local', 'gdrive', 'hetzner')),
            snapshot    text,
            notes       text CHECK (length(notes) <= 1000),
            detail      jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(detail) = 'object'),
            UNIQUE (company_id, at)
        );
        CREATE TRIGGER restore_tests_append_only BEFORE DELETE OR UPDATE ON backup.restore_tests
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        {_rls("backup.status")}
        {_rls("backup.runs")}
        {_rls("backup.snapshots")}
        {_rls("backup.restore_tests")}

        GRANT SELECT ON backup.status, backup.runs, backup.snapshots, backup.restore_tests TO {APP_ROLES};
        GRANT INSERT, UPDATE ON backup.status TO hq_worker;
        GRANT INSERT ON backup.runs, backup.restore_tests TO hq_worker;
        GRANT INSERT, UPDATE, DELETE ON backup.snapshots TO hq_worker;
        """
    )


def downgrade() -> None:
    execute_script("DROP SCHEMA backup CASCADE;")
