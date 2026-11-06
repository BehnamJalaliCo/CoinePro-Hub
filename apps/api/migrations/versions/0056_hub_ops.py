"""The hub run from the app (contract §38, the owner, 2026-11-06: «نمیشه که یبار توی آپ من بگم یبارم
بیام به تو بگم یبار تو به سرور بگی»).

- ops.hub_jobs: one operation of the fixed hub-ops catalogue (domain/hub_ops.py), asked by a
  technical role (`hub.ops`) or by the owner (the services page, §38.3), run on the hub host by the
  hub-ops dispatcher (infra/hubops/dispatch.sh). `argv` is the exact command the api built from the
  validated arguments; the dispatcher runs it only when its own allow-list builds the same.
  `digest` binds an A3 job to its 🔏 `hub_op` card. The output is masked twice (on the host and
  here) and at most 64 KB. The holding's rows only, FORCE RLS, never deleted.
- ops.hub_snapshot: the dispatcher's latest look at the host (memory, budget, caps, per-container
  use, which optional services are on), at most every 60 s; one row, the holding's.
- cartable.decisions: the kind `hub_op` (an A3 operation waiting for the owner's seal).

Additive only; nothing is deleted.

Revision ID: 0056
Revises: 0055
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"

UPGRADE = f"""
CREATE SEQUENCE ops.hub_job_ref_seq;
GRANT USAGE ON SEQUENCE ops.hub_job_ref_seq TO {APP_ROLES};

CREATE TABLE ops.hub_jobs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref           text NOT NULL UNIQUE DEFAULT lines.pad_ref('HJ-', nextval('ops.hub_job_ref_seq'), 6),
    company_id    uuid NOT NULL REFERENCES core.companies (id),
    op            text NOT NULL CHECK (op ~ '^[a-z][a-z0-9_.]{{1,40}}$'),
    args          jsonb NOT NULL DEFAULT '{{}}'
                      CHECK (jsonb_typeof(args) = 'object' AND length(args::text) <= 300000),
    argv          jsonb NOT NULL CHECK (jsonb_typeof(argv) = 'array' AND length(argv::text) <= 4000),
    digest        text NOT NULL CHECK (digest ~ '^[0-9a-f]{{64}}$'),
    class         text NOT NULL CHECK (class IN ('A0', 'A2', 'A3')),
    state         text NOT NULL DEFAULT 'queued'
                      CHECK (state IN ('queued', 'running', 'done', 'failed', 'refused', 'awaiting_seal')),
    requested_kind text NOT NULL CHECK (requested_kind IN ('agent', 'owner')),
    requested_by  text NOT NULL CHECK (length(requested_by) BETWEEN 1 AND 60),
    employee_id   uuid REFERENCES core.employees (id),
    run_id        uuid,
    decision_ref  text CHECK (decision_ref ~ '^D-[0-9]{{6,}}$'),
    timeout_s     int NOT NULL DEFAULT 600 CHECK (timeout_s BETWEEN 10 AND 3600),
    output        text CHECK (length(output) <= 65536),
    exit_code     int,
    result_fa     text CHECK (length(result_fa) <= 500),
    blocking      jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(blocking) = 'array'),
    error_code    text CHECK (error_code ~ '^[a-z_]{{1,40}}$'),
    created_at    timestamptz NOT NULL DEFAULT now(),
    started_at    timestamptz,
    finished_at   timestamptz,
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX hub_jobs_queue ON ops.hub_jobs (state, created_at) WHERE state IN ('queued', 'running');
CREATE INDEX hub_jobs_recent ON ops.hub_jobs (created_at DESC);
CREATE INDEX hub_jobs_decision ON ops.hub_jobs (decision_ref) WHERE decision_ref IS NOT NULL;
CREATE TRIGGER hub_jobs_no_delete BEFORE DELETE ON ops.hub_jobs
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
CREATE TRIGGER hub_jobs_immutable BEFORE UPDATE ON ops.hub_jobs
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('company_id', 'op', 'args', 'argv', 'digest', 'class',
                                                       'requested_kind', 'requested_by', 'created_at');
GRANT SELECT, INSERT ON ops.hub_jobs TO {APP_ROLES};
GRANT UPDATE (state, decision_ref, output, exit_code, result_fa, blocking, error_code, started_at,
              finished_at, updated_at) ON ops.hub_jobs TO {APP_ROLES};
ALTER TABLE ops.hub_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.hub_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY hub_jobs_tenant ON ops.hub_jobs TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY hub_jobs_owner_role ON ops.hub_jobs TO hq USING (true) WITH CHECK (true);

CREATE TABLE ops.hub_snapshot (
    company_id  uuid PRIMARY KEY REFERENCES core.companies (id),
    at          timestamptz NOT NULL DEFAULT now(),
    data        jsonb NOT NULL CHECK (jsonb_typeof(data) = 'object' AND length(data::text) <= 200000)
);
GRANT SELECT, INSERT, UPDATE ON ops.hub_snapshot TO {APP_ROLES};
ALTER TABLE ops.hub_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.hub_snapshot FORCE ROW LEVEL SECURITY;
CREATE POLICY hub_snapshot_tenant ON ops.hub_snapshot TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY hub_snapshot_owner_role ON ops.hub_snapshot TO hq USING (true) WITH CHECK (true);
"""

DOWNGRADE = """
DROP TABLE ops.hub_snapshot;
DROP TABLE ops.hub_jobs;
DROP SEQUENCE ops.hub_job_ref_seq;
"""


def _kinds_sql(table: str, constraint: str, add: tuple[str, ...]) -> str:
    """Rewrite a `kind IN (...)` CHECK from the kinds it holds now (0029's helper)."""
    added = ", ".join(f"'{k}'" for k in add)
    return f"""
        DO $$
        DECLARE kinds text;
        BEGIN
            SELECT string_agg(quote_literal(k), ', ' ORDER BY k) INTO kinds FROM (
                SELECT DISTINCT m[1] AS k
                FROM pg_constraint c,
                     regexp_matches(pg_get_constraintdef(c.oid), '''([a-z0-9_]+)''', 'g') AS m
                WHERE c.conrelid = '{table}'::regclass AND c.conname = '{constraint}'
                UNION SELECT unnest(ARRAY[{added}]::text[])
            ) x WHERE k IS NOT NULL AND k <> '';
            ALTER TABLE {table} DROP CONSTRAINT {constraint};
            EXECUTE format('ALTER TABLE {table} ADD CONSTRAINT {constraint} '
                           'CHECK (kind IN (%s))', kinds);
        END $$;
    """


def upgrade() -> None:
    execute_script(UPGRADE)
    execute_script(_kinds_sql("cartable.decisions", "decisions_kind_check", ("hub_op",)))


# The kind `hub_op` stays in the CHECK: its cards are kept (as 0032's and 0040's).
def downgrade() -> None:
    execute_script(DOWNGRADE)
