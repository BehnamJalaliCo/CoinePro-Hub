"""Prompt 22 (contract §30): production lines, one engine for every company
and every platform.

- lines.lines: a template (apps/api/seed/lines/*.yaml) set for one company,
  one platform and one channel (LN-0001): its steps as the line overrides
  them, its caps, schedule, state (draft / on / paused), mode (draft / auto)
  and the count of sealed runs that published (`good_runs`).
- lines.line_versions: every change of a line is a new version (the whole
  line as `body`); append-only. A run records the version it ran; a revert
  is a new version with the old body.
- lines.runs (RN-000001) and lines.step_runs: what ran, step by step: each
  step's attempt, output (text in the row, files by id), the tool that
  answered, its tokens; a gated step's card (line_publish, A3).
- lines.assets: the library (cover folders, voices, prompts, patterns,
  music, brand); the holding's rows serve every company.
- §31.1 the learning loop: lines.run_features (what a published run was
  made of, by code at publish: its hook, length, voice, pattern, hour,
  caption) and lines.insights (one row per line: its published runs ranked
  by the template's metric, the best hour / length / voice / pattern, the
  top hooks and plain Persian lessons; code only, no model).

- media.items.line_run_ref: an item a line's `render` step made (RN-…); the
  studio's own review and publish never take it (the line checks and
  publishes it).

Every table carries company_id under FORCE RLS; nothing is deleted by the
app (an asset is retired with `state = 'deleted'`). The decision kind
`line_publish` joins cartable.decisions' CHECK (kept by a downgrade: its
cards stay, like 0032's).

Revision ID: 0040
Revises: 0039
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
TABLES = (
    "lines.lines",
    "lines.line_versions",
    "lines.runs",
    "lines.step_runs",
    "lines.assets",
    "lines.run_features",
    "lines.insights",
)
KEY = r"'^[a-z][a-z0-9_]{1,40}$'"
STEP_KINDS = (
    "'gpt_text', 'dedupe', 'tts', 'pattern_search', 'council_pick', 'opus_build', 'render', "
    "'cover', 'quality', 'publish', 'deliver', 'n8n', 'seal'"
)


def _rls(table: str) -> str:
    name = table.split(".")[1]
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
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


UPGRADE = r"""
CREATE SCHEMA lines;
GRANT USAGE ON SCHEMA lines TO @APP@;

-- A ref never cut short: lpad() alone truncates past its width.
CREATE FUNCTION lines.pad_ref(prefix text, n bigint, width int) RETURNS text
    LANGUAGE sql IMMUTABLE AS
$$ SELECT prefix || CASE WHEN length(n::text) >= width THEN n::text
                         ELSE lpad(n::text, width, '0') END $$;
GRANT EXECUTE ON FUNCTION lines.pad_ref(text, bigint, int) TO @APP@;
CREATE SEQUENCE lines.line_ref_seq;
CREATE SEQUENCE lines.run_ref_seq;
GRANT USAGE ON SEQUENCE lines.line_ref_seq, lines.run_ref_seq TO @APP@;

-- §30.1 a line: a template set for one company, platform and channel
CREATE TABLE lines.lines (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref               text NOT NULL UNIQUE DEFAULT lines.pad_ref('LN-', nextval('lines.line_ref_seq'), 4),
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    template          text NOT NULL CHECK (template ~ @KEY@),
    template_version  int NOT NULL CHECK (template_version >= 1),
    platform          text NOT NULL CHECK (platform ~ @KEY@),
    -- {kind, subject}: where it publishes (a connection kind and its channel)
    channel           jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(channel) = 'object'),
    title_fa          text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
    schedule          text CHECK (length(schedule) BETWEEN 1 AND 500),
    state             text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft', 'on', 'paused')),
    mode              text NOT NULL DEFAULT 'draft' CHECK (mode IN ('draft', 'auto')),
    good_runs         int NOT NULL DEFAULT 0 CHECK (good_runs >= 0),
    auto_after        int NOT NULL DEFAULT 7 CHECK (auto_after BETWEEN 1 AND 100),
    -- {runs_per_day, tokens_per_run, opus_per_day}
    caps              jsonb NOT NULL CHECK (jsonb_typeof(caps) = 'object'),
    -- [StepDef] as this line overrides its template's
    steps             jsonb NOT NULL CHECK (jsonb_typeof(steps) = 'array'),
    library           uuid[] NOT NULL DEFAULT '{}',
    copied_from       text CHECK (copied_from ~ '^LN-[0-9]{4,}$'),
    version           int NOT NULL DEFAULT 1 CHECK (version >= 1),
    -- the schedule's last occurrence the tick made into a run
    last_due_at       timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX lines_company ON lines.lines (company_id, created_at);
CREATE TRIGGER lines_immutable BEFORE UPDATE ON lines.lines
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'template',
                                                      'platform', 'copied_from', 'created_at');
GRANT SELECT, INSERT ON lines.lines TO @APP@;
GRANT UPDATE (template_version, channel, title_fa, schedule, state, mode, good_runs, auto_after,
              caps, steps, library, version, last_due_at, updated_at) ON lines.lines TO @APP@;

CREATE TABLE lines.line_versions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    line_id     uuid NOT NULL REFERENCES lines.lines (id),
    version     int NOT NULL CHECK (version >= 1),
    body        jsonb NOT NULL CHECK (jsonb_typeof(body) = 'object'),
    by_kind     text NOT NULL CHECK (by_kind IN ('owner', 'agent', 'service', 'system')),
    by_code     text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64),
    note_fa     text CHECK (length(note_fa) <= 500),
    at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (line_id, version)
);
CREATE TRIGGER line_versions_append_only BEFORE UPDATE OR DELETE ON lines.line_versions
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON lines.line_versions TO @APP@;

-- §30.1 a run (one Temporal workflow LineRun each) and its steps
CREATE TABLE lines.runs (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref            text NOT NULL UNIQUE DEFAULT lines.pad_ref('RN-', nextval('lines.run_ref_seq'), 6),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    line_id        uuid NOT NULL REFERENCES lines.lines (id),
    line_version   int NOT NULL CHECK (line_version >= 1),
    trigger        text NOT NULL CHECK (trigger IN ('schedule', 'owner', 'test', 'n8n', 'group')),
    dry            boolean NOT NULL DEFAULT false,
    state          text NOT NULL DEFAULT 'queued'
                   CHECK (state IN ('queued', 'running', 'waiting', 'done', 'failed', 'skipped',
                                    'cancelled')),
    -- the schedule's occurrence (one run per occurrence, never two)
    occurrence_at  timestamptz,
    rerun_of       uuid REFERENCES lines.runs (id),
    from_step      text CHECK (from_step ~ @KEY@),
    at             timestamptz NOT NULL DEFAULT now(),
    started_at     timestamptz,
    ended_at       timestamptz,
    tokens         bigint NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    usd_equiv      numeric(14, 6) NOT NULL DEFAULT 0 CHECK (usd_equiv >= 0),
    -- [{platform, kind, external_id, at, url}]
    published      jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(published) = 'array'),
    -- {h24: {...} | null, d7: {...} | null}
    metrics        jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metrics) = 'object'),
    -- the open card of a gated step (line_publish)
    decision_id    uuid REFERENCES cartable.decisions (id),
    sealed         boolean NOT NULL DEFAULT false,
    counted        boolean NOT NULL DEFAULT false,
    note_fa        text CHECK (length(note_fa) <= 1000),
    by_kind        text NOT NULL DEFAULT 'service',
    by_code        text NOT NULL DEFAULT 'lines',
    updated_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (line_id, occurrence_at)
);
CREATE INDEX runs_line ON lines.runs (line_id, at DESC);
CREATE INDEX runs_open ON lines.runs (state, at) WHERE state IN ('queued', 'running', 'waiting');
CREATE TRIGGER runs_immutable BEFORE UPDATE ON lines.runs
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'line_id',
                                                      'line_version', 'trigger', 'dry', 'at');
GRANT SELECT, INSERT ON lines.runs TO @APP@;
GRANT UPDATE (state, started_at, ended_at, tokens, usd_equiv, published, metrics, decision_id,
              sealed, counted, note_fa, updated_at) ON lines.runs TO @APP@;

CREATE TABLE lines.step_runs (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    run_id       uuid NOT NULL REFERENCES lines.runs (id),
    pos          smallint NOT NULL CHECK (pos >= 0),
    key          text NOT NULL CHECK (key ~ @KEY@),
    kind         text NOT NULL CHECK (kind IN (@KINDS@)),
    state        text NOT NULL DEFAULT 'pending'
                 CHECK (state IN ('pending', 'running', 'waiting', 'done', 'failed', 'skipped')),
    attempt      smallint NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    started_at   timestamptz,
    ended_at     timestamptz,
    -- {text, file_id, files, data}
    output       jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(output) = 'object'),
    via          text NOT NULL DEFAULT '' CHECK (length(via) <= 120),
    tokens       bigint NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    usd_equiv    numeric(14, 6) NOT NULL DEFAULT 0 CHECK (usd_equiv >= 0),
    error_fa     text CHECK (length(error_fa) <= 1000),
    -- the prompt's variables that rendered empty
    missing      text[] NOT NULL DEFAULT '{}',
    -- what the next attempt is told (a step after it asked for a new one)
    hint_fa      text CHECK (length(hint_fa) <= 500),
    -- copied from an earlier run (a rerun from a later step)
    reused       boolean NOT NULL DEFAULT false,
    -- a gate (owner / ceo): its card, and its seal
    gate         text CHECK (gate IN ('owner', 'ceo')),
    decision_id  uuid REFERENCES cartable.decisions (id),
    sealed_at    timestamptz,
    sealed_by    text CHECK (length(sealed_by) <= 64),
    UNIQUE (run_id, key),
    UNIQUE (run_id, pos)
);
CREATE TRIGGER step_runs_immutable BEFORE UPDATE ON lines.step_runs
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'run_id', 'pos', 'key',
                                                      'kind');
GRANT SELECT, INSERT ON lines.step_runs TO @APP@;
GRANT UPDATE (state, attempt, started_at, ended_at, output, via, tokens, usd_equiv, error_fa,
              missing, hint_fa, gate, decision_id, sealed_at, sealed_by) ON lines.step_runs TO @APP@;

-- §30.1 the library; the holding's rows serve every company
CREATE TABLE lines.assets (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    kind        text NOT NULL
                CHECK (kind IN ('cover_folder', 'voice', 'prompt', 'pattern', 'music', 'brand')),
    title_fa    text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
    config      jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(config) = 'object'),
    files       uuid[] NOT NULL DEFAULT '{}',
    state       text NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'deleted')),
    version     int NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX assets_company ON lines.assets (company_id, kind) WHERE state = 'active';
CREATE TRIGGER assets_immutable BEFORE UPDATE ON lines.assets
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'created_at');
GRANT SELECT, INSERT ON lines.assets TO @APP@;
GRANT UPDATE (kind, title_fa, config, files, state, version, updated_at) ON lines.assets TO @APP@;

-- §30.2 a media item a line's render step made: the line checks and publishes it
ALTER TABLE media.items ADD COLUMN line_run_ref text CHECK (line_run_ref ~ '^RN-[0-9]{6,}$');
CREATE INDEX items_line_run ON media.items (line_run_ref) WHERE line_run_ref IS NOT NULL;

-- §31.1 what a published run was made of (by code, at its first publish)
CREATE TABLE lines.run_features (
    run_id        uuid PRIMARY KEY REFERENCES lines.runs (id),
    company_id    uuid NOT NULL REFERENCES core.companies (id),
    line_id       uuid NOT NULL REFERENCES lines.lines (id),
    platform      text NOT NULL CHECK (platform ~ @KEY@),
    hook          text CHECK (length(hook) <= 500),
    words         int CHECK (words >= 0),
    length_s      numeric(8, 1) CHECK (length_s >= 0),
    voice         text CHECK (length(voice) <= 120),
    pattern       text CHECK (length(pattern) <= 300),
    publish_hour  smallint CHECK (publish_hour BETWEEN 0 AND 23),
    caption_len   int CHECK (caption_len >= 0),
    at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX run_features_line ON lines.run_features (line_id, at DESC);
CREATE TRIGGER run_features_append_only BEFORE UPDATE OR DELETE ON lines.run_features
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON lines.run_features TO @APP@;

-- §31.1 a line's insights, written again after each 24h / 7d read
CREATE TABLE lines.insights (
    line_id      uuid PRIMARY KEY REFERENCES lines.lines (id),
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    metric       text NOT NULL CHECK (metric ~ @KEY@),
    window_runs  int NOT NULL DEFAULT 0 CHECK (window_runs >= 0),
    -- {hour, length_bucket, voice, pattern_source}
    best         jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(best) = 'object'),
    top_hooks    jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(top_hooks) = 'array'),
    lessons_fa   jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(lessons_fa) = 'array'),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER insights_immutable BEFORE UPDATE ON lines.insights
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('line_id', 'company_id');
GRANT SELECT, INSERT ON lines.insights TO @APP@;
GRANT UPDATE (metric, window_runs, best, top_hooks, lessons_fa, updated_at) ON lines.insights
    TO @APP@;
"""

# The kind `line_publish` stays in the CHECK: its cards are kept (as 0032's).
DOWNGRADE = """
ALTER TABLE media.items DROP COLUMN line_run_ref;
DROP SCHEMA lines CASCADE;
"""


def upgrade() -> None:
    sql = (
        UPGRADE.replace("@APP@", APP_ROLES).replace("@KEY@", KEY).replace("@KINDS@", STEP_KINDS)
    )
    execute_script(sql + "".join(_rls(t) for t in TABLES))
    execute_script(_kinds_sql("cartable.decisions", "decisions_kind_check", ("line_publish",)))


def downgrade() -> None:
    execute_script(DOWNGRADE)
