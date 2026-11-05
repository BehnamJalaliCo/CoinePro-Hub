"""Prompt 24 (contract §33.8-§33.9): the company journey, personas, the persona_test step.

- §33.8 growth.journey_plans (a company made from a kit that has its own stages keeps them; no row
  means the default list), growth.journey_stages (the stages reached, by code from existing rows:
  once reached a stage stays reached, with its evidence), growth.journey_state (the current stage and
  the one `next_fa` line, written only when a stage changes).
- §33.9 growth.personas (the owner's data; `version` counts edits; a persona is archived, never
  deleted) and growth.persona_tests (each test of a message: the results as the model gave them and
  code checked them).
- The line step kind `persona_test` joins the CHECK of lines.step_runs.kind.
- The two router task classes `journey_next` and `persona_test` (the router's seed file holds the
  same rows); the persona suggestion uses `persona_test` too.

Fresh start: the personas stay (the owner's own data); the stage cache, the state and the tests go.
Every new table carries company_id under FORCE RLS; nothing is deleted by the app.

Revision ID: 0048
Revises: 0047
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
TABLES = (
    "growth.journey_plans",
    "growth.journey_stages",
    "growth.journey_state",
    "growth.personas",
    "growth.persona_tests",
)
OLD_KINDS = (
    "'gpt_text', 'dedupe', 'tts', 'pattern_search', 'council_pick', 'opus_build', 'render', "
    "'cover', 'quality', 'publish', 'deliver', 'n8n', 'seal'"
)
NEW_KINDS = OLD_KINDS + ", 'persona_test'"


def _rls(table: str) -> str:
    name = table.split(".")[1]
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
"""


def _step_kinds(kinds: str) -> str:
    return f"""
ALTER TABLE lines.step_runs DROP CONSTRAINT step_runs_kind_check;
ALTER TABLE lines.step_runs ADD CONSTRAINT step_runs_kind_check CHECK (kind IN ({kinds}));
"""


UPGRADE = (
    _step_kinds(NEW_KINDS)
    + f"""
INSERT INTO llm.task_classes (key, transferable, description)
VALUES ('journey_next', false,
        'The one line that says what the company does next, written when a stage changes (contract 33.8)'),
       ('persona_test', false,
        'A message tested against a company''s personas, and the personas suggested from its knowledge (contract 33.9)')
ON CONFLICT (key) DO NOTHING;

-- ============================================================ §33.8 journey ==
CREATE TABLE growth.journey_plans (
    company_id  uuid PRIMARY KEY REFERENCES core.companies (id),
    kit         text CHECK (length(kit) <= 60),
    -- [{{key, title_fa, rule: {{kind, min?}}}}], in order
    stages      jsonb NOT NULL CHECK (jsonb_typeof(stages) = 'array' AND jsonb_array_length(stages) BETWEEN 1 AND 20),
    created_at  timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT ON growth.journey_plans TO {APP_ROLES};

CREATE TABLE growth.journey_stages (
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    key            text NOT NULL CHECK (key ~ '^[a-z][a-z0-9_]{{1,40}}$'),
    reached_at     timestamptz NOT NULL,
    evidence_kind  text NOT NULL CHECK (length(evidence_kind) BETWEEN 1 AND 40),
    evidence_ref   text CHECK (length(evidence_ref) <= 100),
    seen_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, key)
);
GRANT SELECT, INSERT ON growth.journey_stages TO {APP_ROLES};

CREATE TABLE growth.journey_state (
    company_id   uuid PRIMARY KEY REFERENCES core.companies (id),
    current_key  text NOT NULL CHECK (current_key ~ '^[a-z][a-z0-9_]{{1,40}}$'),
    -- the stage `next_fa` was written for (the first one not reached then)
    next_for     text CHECK (next_for ~ '^[a-z][a-z0-9_]{{1,40}}$'),
    next_fa      text CHECK (length(next_fa) <= 500),
    changed_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT ON growth.journey_state TO {APP_ROLES};
GRANT UPDATE (current_key, next_for, next_fa, changed_at, updated_at) ON growth.journey_state
    TO {APP_ROLES};

-- ============================================================ §33.9 personas ==
CREATE TABLE growth.personas (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    name_fa         text NOT NULL CHECK (length(name_fa) BETWEEN 1 AND 100),
    summary_fa      text NOT NULL CHECK (length(summary_fa) BETWEEN 1 AND 1000),
    pains_fa        jsonb NOT NULL DEFAULT '[]'
                    CHECK (jsonb_typeof(pains_fa) = 'array' AND jsonb_array_length(pains_fa) <= 8),
    objections_fa   jsonb NOT NULL DEFAULT '[]'
                    CHECK (jsonb_typeof(objections_fa) = 'array' AND jsonb_array_length(objections_fa) <= 8),
    channel_fa      text NOT NULL DEFAULT '' CHECK (length(channel_fa) <= 200),
    source          text NOT NULL DEFAULT 'owner' CHECK (source IN ('owner', 'kb_suggested')),
    version         int NOT NULL DEFAULT 1,
    archived_at     timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX personas_company ON growth.personas (company_id, created_at) WHERE archived_at IS NULL;
CREATE TRIGGER personas_immutable BEFORE UPDATE ON growth.personas
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'created_at');
CREATE TRIGGER personas_version BEFORE UPDATE ON growth.personas
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
GRANT SELECT, INSERT ON growth.personas TO {APP_ROLES};
GRANT UPDATE (name_fa, summary_fa, pains_fa, objections_fa, channel_fa, source, archived_at,
              updated_at) ON growth.personas TO {APP_ROLES};

CREATE TABLE growth.persona_tests (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    message     text NOT NULL CHECK (length(message) BETWEEN 1 AND 8000),
    results     jsonb NOT NULL CHECK (jsonb_typeof(results) = 'array'),
    source      text NOT NULL DEFAULT 'owner' CHECK (source IN ('owner', 'line')),
    run_ref     text CHECK (length(run_ref) <= 20),
    tokens      bigint NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX persona_tests_company ON growth.persona_tests (company_id, at DESC);
GRANT SELECT, INSERT ON growth.persona_tests TO {APP_ROLES};
"""
)

# The task classes stay (ledger rows may name them). A step run of the new kind cannot stay under
# the old CHECK, so those step rows are made to read `seal` first (their output is kept).
DOWNGRADE = (
    """
DROP TABLE growth.persona_tests;
DROP TABLE growth.personas;
DROP TABLE growth.journey_state;
DROP TABLE growth.journey_stages;
DROP TABLE growth.journey_plans;
ALTER TABLE lines.step_runs DISABLE TRIGGER step_runs_immutable;
UPDATE lines.step_runs SET kind = 'seal' WHERE kind = 'persona_test';
ALTER TABLE lines.step_runs ENABLE TRIGGER step_runs_immutable;
"""
    + _step_kinds(OLD_KINDS)
)


def upgrade() -> None:
    execute_script(UPGRADE + "".join(_rls(t) for t in TABLES))


def downgrade() -> None:
    execute_script(DOWNGRADE)
