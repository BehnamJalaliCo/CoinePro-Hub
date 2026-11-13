"""The library of working groups and the automations (contract §59, prompt 38; the owner, 2026-11-13:
«یه نسخه‌ای ازش بسازیم که بتونیم توی شرکت‌های دیگه ازش استفاده بکنیم … از اولین و تا آخرین لحظه
اتوماسیون بشه»). The contract calls this migration `0065`; that number went to the usage audit's
`0065_capped_parts` the same day, so it is `0066` here.

- owner.playbook_versions: one row per body of a playbook (§59.1). `version` is the body's number
  (v1 at the first seal, v2 …); a sealed version is frozen (the app roles may change only a draft's
  `body` and `changelog_fa`, and move `state` on). The existing playbooks become v1: a sealed one v1
  sealed, a draft v1 draft, a retired one v1 retired. Their body is the playbook's definition with its
  header (title, purpose, platform) and empty `steps`, `package` and `lessons`.
- owner.playbooks.edits: what `version` counted before 1.37 (each PATCH of a draft); `version` is now
  the newest body's number (every existing playbook: 1).
- growth.automations: `kind` (`rule` as before; `routine` for a §50 routine's automation, read from
  `source.routine`; `flow` for §59.7), the flow's `playbook` and `playbook_version` (the contract's
  `.version`: that column already holds a rule's own version), `line`, `schedule`, `budget`,
  `replies`, `mode`, `account`, `story`, `paused_until` and `skips`; `state` gains `paused`.
- growth.site_links: a company's own web links (§59.5); Pro-Chart's is seeded (https://pro-chart.com,
  no sections).
- growth.memberships: `version` (the playbook version the member runs) and `automation` (its flow).
- growth.run_results: what a flow run's publication did (§59.9), read from IG-Hub by code.
- growth.flow_clock: the holding's one row, n8n's last tick and the hub's own fallback runs (§59.7).
- lines.step_runs.kind: the six new step kinds (§59.2).

All FORCE RLS as their neighbours (the holding's or the company's rows). Additive: nothing is
deleted; the downgrade drops what was added and puts the old CHECKs back (NOT VALID, so rows made
since stay).

Revision ID: 0066
Revises: 0065
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
OLD_KINDS = (
    "'gpt_text', 'dedupe', 'tts', 'pattern_search', 'council_pick', 'opus_build', 'render', "
    "'cover', 'quality', 'publish', 'deliver', 'n8n', 'seal', 'persona_test'"
)
NEW_KINDS = OLD_KINDS + ", 'topic', 'voice_check', 'inspire', 'workshop', 'package', 'report'"


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
-- ======================================================== §59.1 playbook versions ==
ALTER TABLE owner.playbooks ADD COLUMN edits integer NOT NULL DEFAULT 0 CHECK (edits >= 0);
UPDATE owner.playbooks SET edits = version - 1, version = 1;
GRANT UPDATE (edits) ON owner.playbooks TO {APP_ROLES};

CREATE TABLE owner.playbook_versions (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL REFERENCES core.companies (id),
    playbook_id   uuid NOT NULL REFERENCES owner.playbooks (id),
    version       integer NOT NULL CHECK (version >= 1),
    state         text NOT NULL CHECK (state IN ('draft', 'sealed', 'retired')),
    body          jsonb NOT NULL
                  CHECK (jsonb_typeof(body) = 'object' AND length(body::text) <= 400000),
    changelog_fa  text[] NOT NULL DEFAULT '{{}}',
    by_kind       text NOT NULL DEFAULT 'owner'
                  CHECK (by_kind IN ('owner', 'agent', 'service', 'system')),
    by_fa         text NOT NULL DEFAULT '' CHECK (length(by_fa) <= 200),
    at            timestamptz NOT NULL DEFAULT now(),
    sealed_at     timestamptz,
    UNIQUE (playbook_id, version),
    CHECK ((state = 'draft') = (sealed_at IS NULL))
);
CREATE INDEX playbook_versions_newest ON owner.playbook_versions (playbook_id, version DESC);
COMMENT ON TABLE owner.playbook_versions IS
    'contract §59.1: the bodies of a playbook (v1, v2 …); a sealed one is frozen';
GRANT SELECT, INSERT ON owner.playbook_versions TO {APP_ROLES};
GRANT UPDATE (state, body, changelog_fa, by_kind, by_fa, at, sealed_at)
    ON owner.playbook_versions TO {APP_ROLES};

INSERT INTO owner.playbook_versions (company_id, playbook_id, version, state, body, by_kind,
                                     by_fa, at, sealed_at)
SELECT p.company_id, p.id, 1,
       CASE WHEN p.state = 'retired' AND p.sealed_at IS NULL THEN 'draft' ELSE p.state END,
       p.definition || jsonb_build_object(
           'title_fa', p.title_fa, 'purpose_fa', p.purpose_fa, 'platform', p.platform,
           'steps', COALESCE(p.definition -> 'steps', '[]'::jsonb),
           'package', COALESCE(p.definition -> 'package', '[]'::jsonb),
           'lessons', COALESCE(p.definition -> 'lessons', '[]'::jsonb)),
       'system', 'سامانه', COALESCE(p.sealed_at, p.created_at), p.sealed_at
FROM owner.playbooks p;

-- ================================================ §59.7 automations: flow kind ==
ALTER TABLE growth.automations
    ADD COLUMN kind text NOT NULL DEFAULT 'rule' CHECK (kind IN ('rule', 'routine', 'flow')),
    ADD COLUMN playbook text CHECK (playbook IS NULL OR playbook ~ '^PB-[0-9]{{4,}}$'),
    ADD COLUMN playbook_version integer
        CHECK (playbook_version IS NULL OR playbook_version >= 1),
    ADD COLUMN line text CHECK (line IS NULL OR line ~ '^LN-[0-9]{{4,}}$'),
    ADD COLUMN schedule jsonb CHECK (schedule IS NULL OR jsonb_typeof(schedule) = 'object'),
    ADD COLUMN budget jsonb CHECK (budget IS NULL OR jsonb_typeof(budget) = 'object'),
    ADD COLUMN replies jsonb CHECK (replies IS NULL OR jsonb_typeof(replies) = 'object'),
    ADD COLUMN mode text CHECK (mode IS NULL OR mode IN ('auto', 'ask')),
    ADD COLUMN account text CHECK (account IS NULL OR length(account) BETWEEN 1 AND 100),
    ADD COLUMN story boolean,
    ADD COLUMN paused_until timestamptz,
    ADD COLUMN skips jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(skips) = 'array');
UPDATE growth.automations SET kind = 'routine' WHERE source ? 'routine';
ALTER TABLE growth.automations DROP CONSTRAINT automations_state_check;
ALTER TABLE growth.automations ADD CONSTRAINT automations_state_check
    CHECK (state IN ('proposed', 'on', 'off', 'paused'));
ALTER TABLE growth.automations ADD CONSTRAINT automations_flow_check
    CHECK (kind <> 'flow' OR (playbook IS NOT NULL AND playbook_version IS NOT NULL
                              AND line IS NOT NULL AND schedule IS NOT NULL));
CREATE INDEX automations_kind ON growth.automations (kind, state);
GRANT UPDATE (playbook_version, line, schedule, budget, replies, mode, account, story,
              paused_until, skips, sentence_fa)
    ON growth.automations TO {APP_ROLES};

-- ================================================== §59.5 a company's own links ==
CREATE TABLE growth.site_links (
    company_id  uuid PRIMARY KEY REFERENCES core.companies (id),
    site        jsonb NOT NULL CHECK (jsonb_typeof(site) = 'object'),
    sections    jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(sections) = 'array'),
    utm         jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(utm) = 'object'),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    by_fa       text NOT NULL DEFAULT '' CHECK (length(by_fa) <= 200)
);
COMMENT ON TABLE growth.site_links IS
    'contract §59.5: a company''s web links (site and sections) and its UTM defaults';
GRANT SELECT, INSERT ON growth.site_links TO {APP_ROLES};
GRANT UPDATE (site, sections, utm, updated_at, by_fa) ON growth.site_links TO {APP_ROLES};
INSERT INTO growth.site_links (company_id, site, utm, by_fa)
SELECT id, jsonb_build_object('url', 'https://pro-chart.com', 'title_fa', 'پرو چارت'),
       jsonb_build_object('source', 'instagram', 'campaign', '{{flow}}',
                          'medium', jsonb_build_object('comment', 'comment', 'story', 'story',
                                                       'dm', 'dm')),
       'سامانه'
FROM core.companies WHERE code = 'PC';

-- ======================================================== §59.4 a member's version ==
ALTER TABLE growth.memberships
    ADD COLUMN version integer CHECK (version IS NULL OR version >= 1),
    ADD COLUMN automation text CHECK (automation IS NULL OR automation ~ '^AT-[0-9]{{4,}}$');
GRANT UPDATE (version, automation) ON growth.memberships TO {APP_ROLES};

-- ===================================================== §59.9 what a run's post did ==
CREATE TABLE growth.run_results (
    run_id           uuid PRIMARY KEY REFERENCES lines.runs (id) ON DELETE CASCADE,
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    automation       text CHECK (automation IS NULL OR automation ~ '^AT-[0-9]{{4,}}$'),
    permalink        text CHECK (permalink IS NULL OR length(permalink) <= 1000),
    story_permalink  text CHECK (story_permalink IS NULL OR length(story_permalink) <= 1000),
    comments         integer CHECK (comments IS NULL OR comments >= 0),
    dms_sent         integer CHECK (dms_sent IS NULL OR dms_sent >= 0),
    clicks           integer CHECK (clicks IS NULL OR clicks >= 0),
    views            integer CHECK (views IS NULL OR views >= 0),
    reach            integer CHECK (reach IS NULL OR reach >= 0),
    likes            integer CHECK (likes IS NULL OR likes >= 0),
    saves            integer CHECK (saves IS NULL OR saves >= 0),
    shares           integer CHECK (shares IS NULL OR shares >= 0),
    read_at          timestamptz,
    reads            integer NOT NULL DEFAULT 0 CHECK (reads >= 0),
    next_read_at     timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX run_results_due ON growth.run_results (next_read_at) WHERE next_read_at IS NOT NULL;
CREATE INDEX run_results_automation ON growth.run_results (automation, created_at DESC);
COMMENT ON TABLE growth.run_results IS
    'contract §59.9: a flow run''s figures read from IG-Hub (null: not given, never guessed)';
GRANT SELECT, INSERT ON growth.run_results TO {APP_ROLES};
GRANT UPDATE (automation, permalink, story_permalink, comments, dms_sent, clicks, views, reach,
              likes, saves, shares, read_at, reads, next_read_at)
    ON growth.run_results TO {APP_ROLES};

-- ================================================== §59.7 the clock (n8n, fallback) ==
CREATE TABLE growth.flow_clock (
    company_id        uuid PRIMARY KEY REFERENCES core.companies (id),
    last_tick_at      timestamptz,
    last_fallback_at  timestamptz,
    ticks             bigint NOT NULL DEFAULT 0 CHECK (ticks >= 0),
    updated_at        timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE growth.flow_clock IS
    'contract §59.7: the holding''s one row: n8n''s last signed tick and the hub''s own fallback';
GRANT SELECT, INSERT ON growth.flow_clock TO {APP_ROLES};
GRANT UPDATE (last_tick_at, last_fallback_at, ticks, updated_at) ON growth.flow_clock TO {APP_ROLES};

-- ======================================================= §59.2 the new step kinds ==
ALTER TABLE lines.step_runs DROP CONSTRAINT step_runs_kind_check;
ALTER TABLE lines.step_runs ADD CONSTRAINT step_runs_kind_check CHECK (kind IN ({NEW_KINDS}));
"""
    + _rls("owner.playbook_versions")
    + _rls("growth.site_links")
    + _rls("growth.run_results")
    + _rls("growth.flow_clock")
)

DOWNGRADE = f"""
ALTER TABLE lines.step_runs DROP CONSTRAINT step_runs_kind_check;
ALTER TABLE lines.step_runs ADD CONSTRAINT step_runs_kind_check
    CHECK (kind IN ({OLD_KINDS})) NOT VALID;
DROP TABLE growth.flow_clock;
DROP TABLE growth.run_results;
ALTER TABLE growth.memberships DROP COLUMN automation, DROP COLUMN version;
DROP TABLE growth.site_links;
DROP INDEX growth.automations_kind;
ALTER TABLE growth.automations DROP CONSTRAINT automations_flow_check;
ALTER TABLE growth.automations DROP CONSTRAINT automations_state_check;
ALTER TABLE growth.automations ADD CONSTRAINT automations_state_check
    CHECK (state IN ('proposed', 'on', 'off')) NOT VALID;
ALTER TABLE growth.automations
    DROP COLUMN skips, DROP COLUMN paused_until, DROP COLUMN story, DROP COLUMN account,
    DROP COLUMN mode, DROP COLUMN replies, DROP COLUMN budget, DROP COLUMN schedule,
    DROP COLUMN line, DROP COLUMN playbook_version, DROP COLUMN playbook, DROP COLUMN kind;
DROP TABLE owner.playbook_versions;
UPDATE owner.playbooks SET version = version + edits;
ALTER TABLE owner.playbooks DROP COLUMN edits;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
