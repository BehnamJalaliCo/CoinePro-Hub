"""Prompt 17 (contract §26 ⟨1.8⟩): company server runners.

The holding's agents work on the companies' own servers through a pull runner
(`hq-runner`) on each server; the hub never connects into a company server.

- infra.servers: a server is `provisioned` (made by the provisioner: plan and
  Hetzner id) or `attached` (paired through its runner: no plan, no Hetzner
  id). New columns: origin, hostname, os, runner_version, via (private |
  public), state (pending | online | offline | revoked; NULL for a
  provisioned server that never had a runner), work_user, last_seen_at,
  hub_rtt_ms, map_at, map (the latest server.map, §26.5).
- infra.runner_pairings: the device-authorisation flow (§26.1): the sha256
  of the device code, the short user code, the company, what the runner
  reported, the expiry (15 minutes), who approved it and the server.
- infra.runners: one credential per server, its sha256 only; rotated every
  24 h (the previous one stays valid for a short grace), revoked at detach.
- infra.server_jobs: one unit of work for one server (§26.2 shape plus the
  company, the actor, args, the destructive category, the deploy flag and
  the seal card); infra.server_job_events: append-only, numbered per job,
  masked before they are stored.
- infra.network_links: the latest result of each link a `netcheck` job
  measured (from a server to the hub or another server, one port).
- control.server_policy: the holding's single row, `seal_required[]`.
- workshop.sessions: a session may run on a company server (runtime
  `company_server`): no workspace or grant then, a server instead, and the
  repository folder it runs in.
- Decision kind `server_destructive` (A3, 🔏 server.destructive); the media
  publish log takes channel `runner` (§26.1b); the router's ledger takes the
  rows of `claude` jobs (caller `company_runner`, task class `server_claude`).

Every company table carries company_id under FORCE RLS (the once-per-query
tenant policy of 0009) and nothing is ever deleted.

Revision ID: 0032
Revises: 0031
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
CATEGORIES = (
    "'db_drop', 'volume_delete', 'backup_delete', 'disk_wipe', 'access_change', 'server_delete'"
)
TABLES = (
    "infra.runner_pairings",
    "infra.runners",
    "infra.server_jobs",
    "infra.server_job_events",
    "infra.network_links",
)


def _rls(table: str) -> str:
    name = table.split(".")[1]
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
        CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
        CREATE TRIGGER {name}_no_delete BEFORE DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
    """


def _kinds_sql(
    table: str, constraint: str, add: tuple[str, ...], drop: tuple[str, ...], valid: bool
) -> str:
    """Rewrite a `kind IN (...)` CHECK from the kinds it holds now (0029's helper)."""
    added = ", ".join(f"'{k}'" for k in add) or "''"
    dropped = ", ".join(f"'{k}'" for k in drop) or "''"
    tail = "" if valid else " NOT VALID"
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
            ) x WHERE k IS NOT NULL AND k <> '' AND k <> ALL (ARRAY[{dropped}]::text[]);
            ALTER TABLE {table} DROP CONSTRAINT {constraint};
            EXECUTE format('ALTER TABLE {table} ADD CONSTRAINT {constraint} '
                           'CHECK (kind IN (%s)){tail}', kinds);
        END $$;
    """


UPGRADE = f"""
-- (left NOT VALID by a downgrade of this revision, if one ran)
ALTER TABLE infra.servers DROP CONSTRAINT IF EXISTS servers_provisioned_only;
ALTER TABLE workshop.sessions DROP CONSTRAINT IF EXISTS sessions_workspace_required;

-- ================================================================ servers ==
ALTER TABLE infra.servers ALTER COLUMN plan_id DROP NOT NULL;
ALTER TABLE infra.servers ALTER COLUMN hetzner_id DROP NOT NULL;
ALTER TABLE infra.servers
    ADD COLUMN origin          text NOT NULL DEFAULT 'provisioned'
                               CHECK (origin IN ('provisioned', 'attached')),
    ADD COLUMN hostname        text CHECK (length(hostname) <= 253),
    ADD COLUMN os              text CHECK (length(os) <= 120),
    ADD COLUMN runner_version  text CHECK (length(runner_version) <= 40),
    ADD COLUMN via             text CHECK (via IN ('private', 'public')),
    ADD COLUMN state           text CHECK (state IN ('pending', 'online', 'offline', 'revoked')),
    ADD COLUMN work_user       text CHECK (work_user ~ '^[a-z_][a-z0-9_.-]{{0,31}}$'),
    ADD COLUMN last_seen_at    timestamptz,
    ADD COLUMN hub_rtt_ms      numeric(10, 2) CHECK (hub_rtt_ms >= 0),
    ADD COLUMN map_at          timestamptz,
    ADD COLUMN map             jsonb CHECK (map IS NULL OR jsonb_typeof(map) = 'object'),
    ADD CONSTRAINT servers_origin_shape CHECK (
        origin = 'attached' OR (plan_id IS NOT NULL AND hetzner_id IS NOT NULL));
-- One attached server of a name per company (the seal target is <CODE>:<name>;
-- the api also refuses a name a provisioned server of the company has).
CREATE UNIQUE INDEX servers_company_name ON infra.servers (company_id, lower(name))
    WHERE origin = 'attached';
GRANT UPDATE (hostname, os, runner_version, via, state, work_user, last_seen_at, hub_rtt_ms,
              map_at, map) ON infra.servers TO {APP_ROLES};

-- =============================================================== pairings ==
CREATE TABLE infra.runner_pairings (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    device_sha256     text NOT NULL UNIQUE CHECK (device_sha256 ~ '^[0-9a-f]{{64}}$'),
    user_code         text NOT NULL CHECK (user_code ~ '^[A-Z0-9]{{4}}-[A-Z0-9]{{4}}$'),
    payload           jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    ip_hash           text CHECK (length(ip_hash) <= 64),
    state             text NOT NULL DEFAULT 'pending'
                      CHECK (state IN ('pending', 'approved', 'claimed')),
    expires_at        timestamptz NOT NULL,
    approved_by_kind  text CHECK (approved_by_kind IN ('owner')),
    approved_by_code  text,
    approved_at       timestamptz,
    step_up_id        uuid,
    server_id         uuid REFERENCES infra.servers (id),
    claimed_at        timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'pending') = (server_id IS NULL))
);
-- A code the owner types names one pending pairing at a time.
CREATE UNIQUE INDEX runner_pairings_open_code ON infra.runner_pairings (user_code)
    WHERE state = 'pending';
CREATE TRIGGER runner_pairings_immutable BEFORE UPDATE ON infra.runner_pairings
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'device_sha256',
                                                      'user_code', 'payload', 'created_at');

-- ================================================================ runners ==
CREATE TABLE infra.runners (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    server_id         uuid NOT NULL REFERENCES infra.servers (id),
    pairing_id        uuid REFERENCES infra.runner_pairings (id),
    token_sha256      text NOT NULL UNIQUE CHECK (token_sha256 ~ '^[0-9a-f]{{64}}$'),
    prev_sha256       text CHECK (prev_sha256 ~ '^[0-9a-f]{{64}}$'),
    prev_valid_until  timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    rotated_at        timestamptz NOT NULL DEFAULT now(),
    last_used_at      timestamptz,
    revoked_at        timestamptz,
    revoked_by_kind   text CHECK (revoked_by_kind IN ('owner', 'service', 'system')),
    revoked_by_code   text
);
CREATE INDEX runners_prev ON infra.runners (prev_sha256) WHERE prev_sha256 IS NOT NULL;
-- One live credential per server.
CREATE UNIQUE INDEX runners_live ON infra.runners (server_id) WHERE revoked_at IS NULL;
CREATE TRIGGER runners_immutable BEFORE UPDATE ON infra.runners
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'server_id', 'pairing_id',
                                                      'created_at');

-- =================================================================== jobs ==
CREATE TABLE infra.server_jobs (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id           uuid NOT NULL REFERENCES core.companies (id),
    server_id            uuid NOT NULL REFERENCES infra.servers (id),
    kind                 text NOT NULL CHECK (kind IN ('map', 'exec', 'read', 'write', 'claude',
                                                       'publish', 'netcheck')),
    actor_kind           text NOT NULL CHECK (actor_kind IN ('owner', 'agent', 'service', 'system')),
    actor_code           text NOT NULL CHECK (length(actor_code) BETWEEN 1 AND 64),
    -- an agent of another company working through a cross-company request
    -- the actor's CEO accepted (the job runs as that company's actor)
    on_behalf_code       text CHECK (length(on_behalf_code) <= 64),
    work_ref             text CHECK (length(work_ref) <= 40),
    args                 jsonb NOT NULL CHECK (jsonb_typeof(args) = 'object'),
    args_sha256          text NOT NULL CHECK (args_sha256 ~ '^[0-9a-f]{{64}}$'),
    summary_in           text NOT NULL DEFAULT '' CHECK (length(summary_in) <= 2000),
    state                text NOT NULL DEFAULT 'queued'
                         CHECK (state IN ('queued', 'running', 'awaiting_seal', 'done', 'failed',
                                          'cancelled')),
    category             text CHECK (category IN ({CATEGORIES})),
    pattern              text CHECK (length(pattern) <= 120),
    deploy               boolean NOT NULL DEFAULT false,
    decision_id          uuid REFERENCES cartable.decisions (id),
    session_id           uuid REFERENCES workshop.sessions (id),
    timeout_s            int NOT NULL DEFAULT 600 CHECK (timeout_s BETWEEN 1 AND 3600),
    created_at           timestamptz NOT NULL DEFAULT now(),
    dispatched_at        timestamptz,
    started_at           timestamptz,
    finished_at          timestamptz,
    exit_code            int,
    summary_fa           text CHECK (length(summary_fa) <= 2000),
    error_code           text CHECK (error_code ~ '^[a-z][a-z0-9_]{{1,40}}$'),
    result               jsonb CHECK (result IS NULL OR jsonb_typeof(result) = 'object'),
    usage                jsonb CHECK (usage IS NULL OR jsonb_typeof(usage) = 'object'),
    transcript_file_id   uuid REFERENCES files.files (id),
    cancel_reason        text CHECK (length(cancel_reason) <= 200),
    cancel_delivered_at  timestamptz,
    last_seq             int NOT NULL DEFAULT 0 CHECK (last_seq >= 0),
    updated_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX server_jobs_server ON infra.server_jobs (server_id, created_at DESC);
CREATE INDEX server_jobs_queue ON infra.server_jobs (server_id, created_at)
    WHERE state = 'queued';
CREATE INDEX server_jobs_open ON infra.server_jobs (company_id)
    WHERE state IN ('queued', 'running', 'awaiting_seal');
CREATE INDEX server_jobs_decision ON infra.server_jobs (decision_id) WHERE decision_id IS NOT NULL;
CREATE FUNCTION infra.server_jobs_guard() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.state IN ('done', 'failed', 'cancelled') AND NEW.state <> OLD.state THEN
        RAISE EXCEPTION 'job % is finished (%)', OLD.id, OLD.state USING ERRCODE = 'HQV01';
    END IF;
    IF NEW.last_seq < OLD.last_seq THEN
        RAISE EXCEPTION 'job %: the sequence never goes down', OLD.id USING ERRCODE = 'HQV01';
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END $$;
CREATE TRIGGER server_jobs_guard BEFORE UPDATE ON infra.server_jobs
    FOR EACH ROW EXECUTE FUNCTION infra.server_jobs_guard();
CREATE TRIGGER server_jobs_immutable BEFORE UPDATE ON infra.server_jobs
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'server_id', 'kind',
                                                      'actor_kind', 'actor_code', 'on_behalf_code',
                                                      'args', 'args_sha256', 'created_at');

CREATE TABLE infra.server_job_events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id      uuid NOT NULL REFERENCES infra.server_jobs (id),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    seq         int NOT NULL CHECK (seq >= 1),
    type        text NOT NULL CHECK (type IN ('stdout', 'stderr', 'session_event', 'progress')),
    data        jsonb NOT NULL CHECK (jsonb_typeof(data) = 'object'),
    at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (job_id, seq)
);
CREATE TRIGGER server_job_events_append_only BEFORE UPDATE ON infra.server_job_events
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();

-- ================================================================ network ==
CREATE TABLE infra.network_links (
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    from_server_id  uuid NOT NULL REFERENCES infra.servers (id),
    to_key          text NOT NULL CHECK (to_key = 'hub' OR to_key ~ '^[0-9a-f-]{{36}}$'),
    to_ip           text NOT NULL CHECK (length(to_ip) <= 45),
    port            int NOT NULL CHECK (port BETWEEN 1 AND 65535),
    ok              boolean NOT NULL,
    ms              numeric(10, 2) CHECK (ms >= 0),
    error           text CHECK (length(error) <= 120),
    at              timestamptz NOT NULL,
    last_ok_at      timestamptz,
    job_id          uuid REFERENCES infra.server_jobs (id),
    PRIMARY KEY (from_server_id, to_key, port)
);

{"".join(_rls(t) for t in TABLES)}

GRANT SELECT, INSERT ON {", ".join(TABLES)} TO {APP_ROLES};
GRANT UPDATE (state, approved_by_kind, approved_by_code, approved_at, step_up_id, server_id,
              claimed_at) ON infra.runner_pairings TO {APP_ROLES};
GRANT UPDATE (token_sha256, prev_sha256, prev_valid_until, rotated_at, last_used_at, revoked_at,
              revoked_by_kind, revoked_by_code) ON infra.runners TO {APP_ROLES};
GRANT UPDATE (state, category, pattern, deploy, decision_id, session_id, dispatched_at,
              started_at, finished_at, exit_code, summary_fa, error_code, result, usage,
              transcript_file_id, cancel_reason, cancel_delivered_at, last_seq, updated_at)
    ON infra.server_jobs TO {APP_ROLES};
GRANT UPDATE (to_ip, ok, ms, error, at, last_ok_at, job_id) ON infra.network_links TO {APP_ROLES};

-- ================================================================ control ==
-- The holding's single row: the categories that wait for the owner's seal.
CREATE TABLE control.server_policy (
    id               boolean PRIMARY KEY DEFAULT true CHECK (id),
    seal_required    text[] NOT NULL
                     CHECK (seal_required <@ ARRAY[{CATEGORIES}]::text[]),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    updated_by_kind  text CHECK (updated_by_kind IN ('owner')),
    updated_by_code  text,
    step_up_id       uuid
);
INSERT INTO control.server_policy (seal_required) VALUES (ARRAY[{CATEGORIES}]::text[]);
CREATE TRIGGER server_policy_no_delete BEFORE DELETE ON control.server_policy
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT ON control.server_policy TO {APP_ROLES};
GRANT UPDATE (seal_required, updated_at, updated_by_kind, updated_by_code, step_up_id)
    ON control.server_policy TO hq_api;

-- =============================================================== workshop ==
ALTER TABLE workshop.sessions ALTER COLUMN workspace_id DROP NOT NULL;
ALTER TABLE workshop.sessions ALTER COLUMN grant_id DROP NOT NULL;
ALTER TABLE workshop.sessions DROP CONSTRAINT sessions_runtime_check;
ALTER TABLE workshop.sessions ADD CONSTRAINT sessions_runtime_check
    CHECK (runtime IN ('managed', 'self_hosted', 'fake', 'company_server'));
ALTER TABLE workshop.sessions
    ADD COLUMN server_id uuid REFERENCES infra.servers (id),
    ADD COLUMN cwd       text CHECK (length(cwd) <= 500),
    ADD CONSTRAINT sessions_server_shape CHECK (
        (runtime = 'company_server') = (server_id IS NOT NULL)
        AND (runtime = 'company_server' OR (workspace_id IS NOT NULL AND grant_id IS NOT NULL)));
CREATE INDEX sessions_server ON workshop.sessions (server_id, created_at DESC)
    WHERE server_id IS NOT NULL;

-- ================================================================== media ==
ALTER TABLE media.publish_log DROP CONSTRAINT publish_log_channel_check;
ALTER TABLE media.publish_log ADD CONSTRAINT publish_log_channel_check
    CHECK (channel IN ('telegram', 'instagram', 'runner'));
ALTER TABLE media.publish_log DROP CONSTRAINT publish_log_via_check;
ALTER TABLE media.publish_log ADD CONSTRAINT publish_log_via_check
    CHECK (via IN ('api', 'manual', 'runner'));

-- ==================================================================== llm ==
-- A `claude` job's usage, reported from the server's own Claude login
-- (contract §26.3): recorded at its equivalent cost, like a substitute call.
INSERT INTO llm.task_classes (key, transferable, description)
VALUES ('server_claude', false,
        'Claude Code on a company server (prompt 17): the server''s own login, usage reported by its runner')
ON CONFLICT (key) DO NOTHING;
CREATE POLICY calls_runner_insert ON llm.calls FOR INSERT TO hq_api, hq_worker
    WITH CHECK (company_id = ANY ((SELECT llm.allowed_company_ids())::uuid[])
                AND caller = 'company_runner');
"""

DOWNGRADE = f"""
DROP POLICY calls_runner_insert ON llm.calls;
-- (the task class stays: ledger rows may name it)
-- NOT VALID: past rows stay as they are.
ALTER TABLE media.publish_log DROP CONSTRAINT publish_log_channel_check;
ALTER TABLE media.publish_log ADD CONSTRAINT publish_log_channel_check
    CHECK (channel IN ('telegram', 'instagram')) NOT VALID;
ALTER TABLE media.publish_log DROP CONSTRAINT publish_log_via_check;
ALTER TABLE media.publish_log ADD CONSTRAINT publish_log_via_check
    CHECK (via IN ('api', 'manual')) NOT VALID;

DROP INDEX workshop.sessions_server;
ALTER TABLE workshop.sessions DROP CONSTRAINT sessions_server_shape;
ALTER TABLE workshop.sessions DROP COLUMN cwd;
ALTER TABLE workshop.sessions DROP CONSTRAINT sessions_runtime_check;
ALTER TABLE workshop.sessions ADD CONSTRAINT sessions_runtime_check
    CHECK (runtime IN ('managed', 'self_hosted', 'fake')) NOT VALID;

DROP TABLE control.server_policy;
DROP TABLE infra.network_links;
DROP TABLE infra.server_job_events;
DROP TABLE infra.server_jobs;
DROP FUNCTION infra.server_jobs_guard();
ALTER TABLE workshop.sessions DROP COLUMN server_id;
ALTER TABLE workshop.sessions ADD CONSTRAINT sessions_workspace_required
    CHECK (workspace_id IS NOT NULL AND grant_id IS NOT NULL) NOT VALID;
DROP TABLE infra.runners;
DROP TABLE infra.runner_pairings;

REVOKE UPDATE (hostname, os, runner_version, via, state, work_user, last_seen_at, hub_rtt_ms,
               map_at, map) ON infra.servers FROM {APP_ROLES};
DROP INDEX infra.servers_company_name;
ALTER TABLE infra.servers DROP CONSTRAINT servers_origin_shape;
-- Attached servers keep their rows (nothing is deleted): the old shape holds
-- for every new row only.
ALTER TABLE infra.servers ADD CONSTRAINT servers_provisioned_only
    CHECK (plan_id IS NOT NULL AND hetzner_id IS NOT NULL) NOT VALID;
ALTER TABLE infra.servers DROP COLUMN origin, DROP COLUMN hostname, DROP COLUMN os,
    DROP COLUMN runner_version, DROP COLUMN via, DROP COLUMN state, DROP COLUMN work_user,
    DROP COLUMN last_seen_at, DROP COLUMN hub_rtt_ms, DROP COLUMN map_at, DROP COLUMN map;
"""


def upgrade() -> None:
    execute_script(UPGRADE)
    # Added valid at once (every row already fits). No VALIDATE statement:
    # 0029 stays the one migration that validates (test_p13f_join).
    execute_script(
        _kinds_sql("cartable.decisions", "decisions_kind_check", ("server_destructive",), (), True)
    )


def downgrade() -> None:
    # The kind stays in the CHECK: its cards are kept (resolutions point at them).
    execute_script(DOWNGRADE)
