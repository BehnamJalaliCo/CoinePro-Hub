"""The automations as data (contract §61, prompt 39 P1; the owner, 2026-11-17: «بخش اتوماسیون خیلی
مبتدیه و باید یک قسمت مهم آپ باشه با کلی فیچر … و با قابلیت تغییرات»).

- automations.flows: one row per daily flow (§61.1), `ref` AF-0001 from automations.flow_ref_seq,
  `key` unique (the `N8:<key>` of §59.7.1 resolves to it). `schedule` holds the hours of the round
  of weeks (null = that week's best hour), `best_week`, `days` (Saturday = 0 … Friday = 6),
  `stories`, `trigger_at`, `same_day` and `start`; `version` is the body's number (each save of
  the owner makes the next one).
- automations.flow_versions: one row per save, `body` = every editable field; never updated or
  deleted (no UPDATE or DELETE grant).
- automations.alerts: §61.6, one open alert per flow and kind (made by code; its logic is P2).
- Seeded from today's code flows (domain/flows.py FLOWS, read through flow_defs.seed_rows), every
  one, the pilots too (an empty account publishes nothing), with the same key and behaviour, for
  the companies that exist; version 1 «ساخته شد از روند کدی هاب». The keys owner.settings.flows_off
  names move into `state` ('off') and leave that list (it keeps only keys no row has). A flow no
  n8n workflow ever started (a pilot, run by hand) is 'off' too: the hub's clock (§61.2) starts
  only what n8n started before.
- audit.entries.action takes three parts too (`automation.flow.update`, §61.3), as the step-up's
  action pattern already does.

All FORCE RLS by company_id, as their neighbours; KEEP in a fresh start. Additive: the downgrade
puts the off keys back in flows_off, drops the schema and the looser audit check.

Revision ID: 0070
Revises: 0069
"""

from __future__ import annotations

import json

from hq_api.migration_sql import execute_script

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
KINDS = "'reel', 'stories', 'short', 'video', 'article', 'tg_post'"
ALERT_KINDS = "'run_failed', 'cap_reached', 'page_held', 'login_expired', 'clock_missed', 'late'"


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
CREATE SCHEMA automations;
GRANT USAGE ON SCHEMA automations TO {APP_ROLES};

-- ======================================================= §61.1 the flows ==
CREATE SEQUENCE automations.flow_ref_seq;
GRANT USAGE ON SEQUENCE automations.flow_ref_seq TO {APP_ROLES};

CREATE TABLE automations.flows (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref            text NOT NULL UNIQUE
                   DEFAULT core.pad_ref('AF-', nextval('automations.flow_ref_seq'), 4),
    key            text NOT NULL UNIQUE CHECK (key ~ '^[a-z][a-z0-9_]{{0,40}}$'),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    channel        text NOT NULL DEFAULT 'instagram' CHECK (channel ~ '^[a-z][a-z0-9_]{{1,30}}$'),
    -- '' publishes nothing (a pilot for the owner's eyes)
    account        text NOT NULL DEFAULT '' CHECK (length(account) <= 100),
    title_fa       text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    kit            text NOT NULL CHECK (length(kit) BETWEEN 1 AND 300),
    kind           text NOT NULL CHECK (kind IN ({KINDS})),
    state          text NOT NULL DEFAULT 'on' CHECK (state IN ('on', 'off', 'paused')),
    paused_until   date,
    skips          date[] NOT NULL DEFAULT '{{}}' CHECK (cardinality(skips) <= 400),
    schedule       jsonb NOT NULL CHECK (jsonb_typeof(schedule) = 'object'),
    -- a reel's own story cut goes out with it
    story          boolean NOT NULL DEFAULT false,
    model          text NOT NULL DEFAULT '' CHECK (length(model) <= 100),
    model_from     date,
    effort         text NOT NULL DEFAULT 'max' CHECK (effort IN ('high', 'xhigh', 'max')),
    usd_cap        numeric(8, 2) NOT NULL CHECK (usd_cap BETWEEN 1 AND 500),
    budget_tokens  bigint NOT NULL CHECK (budget_tokens BETWEEN 1 AND 100000000),
    cycle          text[] NOT NULL DEFAULT '{{}}' CHECK (cardinality(cycle) <= 7),
    -- null: a fresh reply word every day
    story_word     text CHECK (length(story_word) BETWEEN 1 AND 40),
    -- the per-flow n8n workflow that still calls (§61.2: a no-op once the hub's clock started the day)
    n8n            text NOT NULL DEFAULT '' CHECK (length(n8n) <= 100),
    pair           text CHECK (pair ~ '^[a-z][a-z0-9_]{{0,40}}$'),
    recipe         text CHECK (length(recipe) <= 40),
    note_fa        text CHECK (length(note_fa) <= 2000),
    version        int NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'paused') OR paused_until IS NULL)
);
CREATE INDEX flows_company ON automations.flows (company_id, account);
CREATE TRIGGER flows_immutable BEFORE UPDATE ON automations.flows
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'key', 'company_id', 'created_at');
COMMENT ON TABLE automations.flows IS
    'contract 61.1: a daily flow the owner edits from the app; FLOWS of domain/flows.py was its seed';
GRANT SELECT, INSERT ON automations.flows TO {APP_ROLES};
GRANT UPDATE (account, title_fa, kit, state, paused_until, skips, schedule, story, model, model_from,
              effort, usd_cap, budget_tokens, cycle, story_word, n8n, pair, recipe, note_fa,
              version, updated_at)
    ON automations.flows TO {APP_ROLES};

CREATE TABLE automations.flow_versions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    flow_id     uuid NOT NULL REFERENCES automations.flows (id),
    version     int NOT NULL CHECK (version >= 1),
    at          timestamptz NOT NULL DEFAULT now(),
    by_kind     text NOT NULL CHECK (by_kind IN ('owner', 'agent', 'service', 'system')),
    by_code     text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64),
    by_fa       text NOT NULL CHECK (length(by_fa) BETWEEN 1 AND 200),
    note_fa     text CHECK (length(note_fa) <= 500),
    changes     jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(changes) = 'array'),
    body        jsonb NOT NULL CHECK (jsonb_typeof(body) = 'object'),
    UNIQUE (flow_id, version)
);
COMMENT ON TABLE automations.flow_versions IS
    'contract 61.1: one row per save of a flow (body = every editable field); never deleted';
GRANT SELECT, INSERT ON automations.flow_versions TO {APP_ROLES};

-- ====================================================== §61.6 the alerts ==
CREATE TABLE automations.alerts (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    flow_id     uuid NOT NULL REFERENCES automations.flows (id),
    kind        text NOT NULL CHECK (kind IN ({ALERT_KINDS})),
    day         date,
    note_fa     text NOT NULL CHECK (length(note_fa) BETWEEN 1 AND 500),
    opened_at   timestamptz NOT NULL DEFAULT now(),
    notified_at timestamptz,
    closed_at   timestamptz,
    closed_fa   text CHECK (length(closed_fa) <= 500),
    CHECK ((closed_at IS NULL) = (closed_fa IS NULL))
);
-- one open alert per flow and kind
CREATE UNIQUE INDEX alerts_open ON automations.alerts (flow_id, kind) WHERE closed_at IS NULL;
CREATE INDEX alerts_company ON automations.alerts (company_id, opened_at DESC);
COMMENT ON TABLE automations.alerts IS
    'contract 61.6: an alert of a flow, made and closed by code; one open per flow and kind';
GRANT SELECT, INSERT ON automations.alerts TO {APP_ROLES};
GRANT UPDATE (note_fa, notified_at, closed_at, closed_fa) ON automations.alerts TO {APP_ROLES};

-- §61.3 audit `automation.flow.<verb>`: an action of three parts, as the step-up's pattern
ALTER TABLE audit.entries DROP CONSTRAINT entries_action_check;
ALTER TABLE audit.entries ADD CONSTRAINT entries_action_check
    CHECK (action ~ '^[a-z_]+\\.[a-z_]+(\\.[a-z_]+)?$');
"""
    + _rls("automations.flows")
    + _rls("automations.flow_versions")
    + _rls("automations.alerts")
)

SEED_NOTE_FA = "ساخته شد از روند کدی هاب"


def seed_sql(rows: list[dict[str, object]]) -> str:
    """The seed of the code flows (flow_defs.seed_rows), for the companies that exist; a key that
    has a row already is left as it is, so the seed may run again (a test's company made later)."""
    data = json.dumps(rows, ensure_ascii=False)
    if "$seed$" in data:  # (the dollar quote below)
        raise ValueError("a seed row holds the quote")
    return f"""
WITH s AS (
    SELECT * FROM jsonb_to_recordset($seed${data}$seed$::jsonb) AS x(
        ord int, key text, company text, channel text, account text, title_fa text, kit text,
        kind text, schedule jsonb, story boolean, model text, model_from date, effort text,
        usd_cap numeric, budget_tokens bigint, cycle jsonb, story_word text, n8n text, pair text,
        recipe text, note_fa text, body jsonb)
), made AS (
    INSERT INTO automations.flows (key, company_id, channel, account, title_fa, kit, kind, state,
        schedule, story, model, model_from, effort, usd_cap, budget_tokens, cycle, story_word, n8n,
        pair, recipe, note_fa)
    SELECT s.key, c.id, s.channel, s.account, s.title_fa, s.kit, s.kind,
           CASE WHEN s.key = ANY (coalesce(o.flows_off, '{{}}')) OR s.n8n = '' THEN 'off'
                ELSE 'on' END,
           s.schedule, s.story, s.model, s.model_from, s.effort, s.usd_cap, s.budget_tokens,
           ARRAY(SELECT jsonb_array_elements_text(s.cycle)), s.story_word, s.n8n, s.pair, s.recipe,
           s.note_fa
    FROM s JOIN core.companies c ON c.code = s.company
    LEFT JOIN owner.settings o ON o.id = 1
    ORDER BY s.ord
    ON CONFLICT (key) DO NOTHING
    RETURNING id, key, company_id
)
INSERT INTO automations.flow_versions (company_id, flow_id, version, by_kind, by_code, by_fa,
                                       note_fa, body)
SELECT m.company_id, m.id, 1, 'system', 'hub', 'Claude سرور هاب', '{SEED_NOTE_FA}', s.body
FROM made m JOIN s ON s.key = m.key;
UPDATE owner.settings SET flows_off = ARRAY(
    SELECT k FROM unnest(flows_off) AS k WHERE k NOT IN (SELECT key FROM automations.flows))
WHERE id = 1;
"""


DOWNGRADE = """
UPDATE owner.settings SET flows_off = ARRAY(
    SELECT DISTINCT k FROM unnest(flows_off || ARRAY(
        SELECT key FROM automations.flows WHERE state = 'off')) AS k)
WHERE id = 1;
DROP SCHEMA automations CASCADE;
ALTER TABLE audit.entries DROP CONSTRAINT entries_action_check;
ALTER TABLE audit.entries ADD CONSTRAINT entries_action_check
    CHECK (action ~ '^[a-z_]+\\.[a-z_]+$') NOT VALID;
"""


def upgrade() -> None:
    from hq_api.domain.flow_defs import seed_rows

    execute_script(UPGRADE)
    execute_script(seed_sql(seed_rows()))


def downgrade() -> None:
    execute_script(DOWNGRADE)
