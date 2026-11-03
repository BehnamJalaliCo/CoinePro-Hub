"""Prompt 21 part 3 (contract §29.9, §29.11, §29.12, §29.13): working groups,
connections, the owner's home, readiness.

- §29.11 growth.groups: one row per working group defined in data
  (apps/api/seed/groups/*.yaml; the holding's rows); a changed file makes a
  new version (growth.group_versions keeps each), the owner's pauses of a
  routine (`routine_states`) survive it. growth.memberships: one row per
  company in a group (state, its seats -> employee, the content lead's plan
  of the day). growth.routine_runs: each routine's run per period (unique:
  never twice), the work item it made. growth.experiments: one a week per
  company, closed with its figure.
- §29.12 growth.connections: one row per company and kind (the ten kinds),
  non-secret config only; the secret lives in OpenBao
  (kv/hq/growth/<company>/<kind>), here only whether it is set.
  growth.metrics_daily: the daily read of every connected kind (by code, no
  model), one row per (company, kind, day, key, subject); `hub` holds the
  figures the hub computes from its own tables (items published).
- §29.13 owner.suggestions (the home's «پیشنهاد مؤثر» and «پیشنهاد خوب»: the
  owner's run / later / no and its reason), owner.progress (before and after,
  from real figures only), growth.home_mornings (the 5 morning lines of a day).

Every new table carries company_id under FORCE RLS (the group definitions
and the morning lines are the holding's rows); nothing is deleted by the app.

Revision ID: 0039
Revises: 0038
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
KINDS = (
    "'search_console', 'ga4', 'instagram', 'telegram', 'youtube', 'x', 'pagespeed', 'trends', "
    "'bing', 'play_console'"
)
TABLES = (
    "growth.groups",
    "growth.group_versions",
    "growth.memberships",
    "growth.routine_runs",
    "growth.experiments",
    "growth.connections",
    "growth.metrics_daily",
    "growth.home_mornings",
    "owner.suggestions",
    "owner.progress",
)


def _rls(table: str) -> str:
    name = table.split(".")[1]
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
"""


UPGRADE = (
    f"""
-- §29.11 working groups, defined in data (the holding's rows)
CREATE TABLE growth.groups (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    key             text NOT NULL UNIQUE CHECK (key ~ '^[a-z][a-z0-9_]{{1,40}}$'),
    version         int NOT NULL DEFAULT 1 CHECK (version >= 1),
    digest          text NOT NULL CHECK (digest ~ '^[0-9a-f]{{64}}$'),
    title_fa        text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
    purpose_fa      text NOT NULL DEFAULT '' CHECK (length(purpose_fa) <= 2000),
    definition      jsonb NOT NULL CHECK (jsonb_typeof(definition) = 'object'),
    state           text NOT NULL DEFAULT 'on' CHECK (state IN ('on', 'off')),
    -- the owner's pauses of a routine: {{routine: "paused"}}, kept across versions
    routine_states  jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(routine_states) = 'object'),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER groups_immutable BEFORE UPDATE ON growth.groups
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'key', 'created_at');
GRANT SELECT, INSERT ON growth.groups TO {APP_ROLES};
GRANT UPDATE (version, digest, title_fa, purpose_fa, definition, state, routine_states, updated_at)
    ON growth.groups TO {APP_ROLES};

CREATE TABLE growth.group_versions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    group_id    uuid NOT NULL REFERENCES growth.groups (id),
    version     int NOT NULL CHECK (version >= 1),
    digest      text NOT NULL CHECK (digest ~ '^[0-9a-f]{{64}}$'),
    definition  jsonb NOT NULL CHECK (jsonb_typeof(definition) = 'object'),
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (group_id, version)
);
CREATE TRIGGER group_versions_append_only BEFORE UPDATE OR DELETE ON growth.group_versions
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON growth.group_versions TO {APP_ROLES};

CREATE TABLE growth.memberships (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    group_id    uuid NOT NULL REFERENCES growth.groups (id),
    state       text NOT NULL DEFAULT 'on' CHECK (state IN ('on', 'paused')),
    joined_at   timestamptz NOT NULL DEFAULT now(),
    -- [{{seat, role, employee: code|null}}], resolved by the groups' tick
    seats       jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(seats) = 'array'),
    -- the content lead's plan of the day (group.plan)
    plan        jsonb CHECK (plan IS NULL OR jsonb_typeof(plan) = 'object'),
    plan_at     timestamptz,
    paused_at   timestamptz,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (group_id, company_id)
);
CREATE TRIGGER memberships_immutable BEFORE UPDATE ON growth.memberships
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'group_id', 'joined_at');
GRANT SELECT, INSERT ON growth.memberships TO {APP_ROLES};
GRANT UPDATE (state, seats, plan, plan_at, paused_at, updated_at) ON growth.memberships
    TO {APP_ROLES};

CREATE TABLE growth.routine_runs (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    group_id       uuid NOT NULL REFERENCES growth.groups (id),
    routine        text NOT NULL CHECK (routine ~ '^[a-z][a-z0-9_]{{1,40}}$'),
    -- the routine's occurrence (its period): one run per occurrence, never two
    occurrence_at  timestamptz NOT NULL,
    at             timestamptz NOT NULL DEFAULT now(),
    seat           text CHECK (seat ~ '^[a-z][a-z0-9_]{{1,40}}$'),
    employee_code  text CHECK (length(employee_code) <= 64),
    work_id        uuid REFERENCES work.work (id),
    state          text NOT NULL CHECK (state IN ('queued', 'done', 'failed', 'skipped')),
    note_fa        text CHECK (length(note_fa) <= 500),
    UNIQUE (group_id, company_id, routine, occurrence_at)
);
CREATE INDEX routine_runs_recent ON growth.routine_runs (group_id, occurrence_at DESC);
CREATE INDEX routine_runs_work ON growth.routine_runs (work_id) WHERE work_id IS NOT NULL;
CREATE TRIGGER routine_runs_immutable BEFORE UPDATE ON growth.routine_runs
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'group_id', 'routine',
                                                      'occurrence_at', 'at');
GRANT SELECT, INSERT ON growth.routine_runs TO {APP_ROLES};
GRANT UPDATE (state, note_fa, work_id) ON growth.routine_runs TO {APP_ROLES};

CREATE TABLE growth.experiments (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    group_id         uuid NOT NULL REFERENCES growth.groups (id),
    week             date NOT NULL,  -- the owner's week (its Saturday)
    hypothesis_fa    text NOT NULL CHECK (length(hypothesis_fa) BETWEEN 1 AND 1000),
    metric           text NOT NULL CHECK (metric ~ '^[a-z][a-z0-9_]{{1,40}}$'),
    target           numeric NOT NULL,
    baseline         numeric,
    result           numeric,
    kept             boolean,
    note_fa          text CHECK (length(note_fa) <= 1000),
    created_by_code  text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
    closed_at        timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (group_id, company_id, week),
    CHECK ((closed_at IS NULL) = (result IS NULL))
);
CREATE TRIGGER experiments_immutable BEFORE UPDATE ON growth.experiments
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'group_id', 'week',
                                                      'created_by_code', 'created_at');
GRANT SELECT, INSERT ON growth.experiments TO {APP_ROLES};
GRANT UPDATE (hypothesis_fa, metric, target, baseline, result, kept, note_fa, closed_at, updated_at)
    ON growth.experiments TO {APP_ROLES};

-- §29.12 connections: non-secret config here, the secret in OpenBao only
CREATE TABLE growth.connections (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    kind           text NOT NULL CHECK (kind IN ({KINDS})),
    label_fa       text NOT NULL CHECK (length(label_fa) BETWEEN 1 AND 200),
    state          text NOT NULL DEFAULT 'not_connected'
                   CHECK (state IN ('not_connected', 'connected', 'error')),
    config         jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(config) = 'object'),
    secret_set     boolean NOT NULL DEFAULT false,
    secret_set_at  timestamptz,
    last_read_at   timestamptz,
    last_error_fa  text CHECK (length(last_error_fa) <= 500),
    -- a read waiting on something (an IG-Hub runner job): {{job_id, day, at}}
    pending        jsonb CHECK (pending IS NULL OR jsonb_typeof(pending) = 'object'),
    origin         text NOT NULL DEFAULT 'owner' CHECK (origin IN ('seed', 'owner')),
    version        int NOT NULL DEFAULT 1,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, kind)
);
CREATE TRIGGER connections_immutable BEFORE UPDATE ON growth.connections
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'kind', 'created_at');
CREATE TRIGGER connections_version BEFORE UPDATE ON growth.connections
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
GRANT SELECT, INSERT ON growth.connections TO {APP_ROLES};
GRANT UPDATE (label_fa, state, config, secret_set, secret_set_at, last_read_at, last_error_fa,
              pending, updated_at) ON growth.connections TO {APP_ROLES};

CREATE TABLE growth.metrics_daily (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    kind        text NOT NULL CHECK (kind IN ({KINDS}, 'hub')),
    day         date NOT NULL,
    key         text NOT NULL CHECK (key ~ '^[a-z][a-z0-9_]{{0,40}}$'),
    -- what the figure is of (a channel, a site, a property); '' for the whole kind
    subject     text NOT NULL DEFAULT '' CHECK (length(subject) <= 200),
    value       numeric NOT NULL,
    source      text NOT NULL CHECK (length(source) BETWEEN 1 AND 200),
    at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, kind, day, key, subject)
);
CREATE INDEX metrics_daily_series ON growth.metrics_daily (company_id, key, day DESC);
GRANT SELECT, INSERT ON growth.metrics_daily TO {APP_ROLES};
GRANT UPDATE (value, source, at) ON growth.metrics_daily TO {APP_ROLES};

-- §29.13 the owner's home
CREATE TABLE growth.home_mornings (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    day         date NOT NULL UNIQUE,
    lines       jsonb NOT NULL CHECK (jsonb_typeof(lines) = 'array' AND jsonb_array_length(lines) <= 5),
    at          timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT ON growth.home_mornings TO {APP_ROLES};
GRANT UPDATE (lines, at) ON growth.home_mornings TO {APP_ROLES};

CREATE TABLE owner.suggestions (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    kind         text NOT NULL CHECK (kind IN ('effective', 'good')),
    title_fa     text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    why_fa       text NOT NULL DEFAULT '' CHECK (length(why_fa) <= 1000),
    impact_fa    text NOT NULL DEFAULT '' CHECK (length(impact_fa) <= 300),
    cost_fa      text NOT NULL DEFAULT '' CHECK (length(cost_fa) <= 300),
    impact       smallint NOT NULL CHECK (impact BETWEEN 1 AND 5),
    cost         smallint NOT NULL CHECK (cost BETWEEN 1 AND 5),
    source       text NOT NULL CHECK (source IN ('council', 'group', 'advisor')),
    source_ref   text CHECK (length(source_ref) <= 200),
    -- one suggestion per idea (the generator's key): a «نه» is never made again
    key          text NOT NULL UNIQUE CHECK (length(key) BETWEEN 3 AND 300),
    state        text NOT NULL DEFAULT 'new' CHECK (state IN ('new', 'run', 'later', 'no')),
    reason_fa    text CHECK (length(reason_fa) <= 1000),
    order_ref    text CHECK (order_ref ~ '^F-[0-9]{{4,}}$'),
    later_until  timestamptz,
    decided_at   timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX suggestions_open ON owner.suggestions (state, created_at DESC);
CREATE TRIGGER suggestions_immutable BEFORE UPDATE ON owner.suggestions
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'key', 'source',
                                                      'created_at');
GRANT SELECT, INSERT ON owner.suggestions TO {APP_ROLES};
GRANT UPDATE (state, reason_fa, order_ref, later_until, decided_at, updated_at)
    ON owner.suggestions TO {APP_ROLES};

CREATE TABLE owner.progress (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL REFERENCES core.companies (id),
    title_fa      text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    kpi           text NOT NULL CHECK (kpi ~ '^[a-z][a-z0-9_]{{0,40}}$'),
    kind          text NOT NULL CHECK (kind IN ({KINDS}, 'hub')),
    subject       text NOT NULL DEFAULT '' CHECK (length(subject) <= 200),
    before_value  numeric NOT NULL,
    before_at     date NOT NULL,
    after_value   numeric NOT NULL,
    after_at      date NOT NULL,
    source        text NOT NULL CHECK (length(source) BETWEEN 1 AND 200),
    work_ref      text CHECK (length(work_ref) <= 40),
    key           text NOT NULL UNIQUE CHECK (length(key) BETWEEN 3 AND 300),
    created_at    timestamptz NOT NULL DEFAULT now(),
    CHECK (after_at > before_at)
);
CREATE INDEX progress_recent ON owner.progress (created_at DESC);
CREATE TRIGGER progress_append_only BEFORE UPDATE OR DELETE ON owner.progress
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON owner.progress TO {APP_ROLES};
"""
    + "".join(_rls(t) for t in TABLES)
)

DOWNGRADE = """
DROP TABLE owner.progress;
DROP TABLE owner.suggestions;
DROP TABLE growth.home_mornings;
DROP TABLE growth.metrics_daily;
DROP TABLE growth.connections;
DROP TABLE growth.experiments;
DROP TABLE growth.routine_runs;
DROP TABLE growth.memberships;
DROP TABLE growth.group_versions;
DROP TABLE growth.groups;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
