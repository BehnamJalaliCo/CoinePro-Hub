"""Prompt 22 part 3 (contract §31.6, §31.7): ad budgets that stop by themselves,
an automation from one sentence.

- §31.6 the two ad platforms are connection kinds (`google_ads`, `meta_ads`:
  the kind checks of growth.connections, growth.metrics_daily and owner.progress
  gain them, whatever other kinds a parallel migration added); growth.ad_rules
  are the owner's budget rules (a daily cap, a ROAS floor after a minimum
  spend; the action pauses or only tells); growth.ad_campaigns the campaigns
  as the platform last showed them (and who paused one); growth.ad_daily one
  row per campaign and day (read by code through egress); growth.ad_trips the
  record of each trip, once per rule, campaign and day.
- §31.7 growth.automations (AT-0001 ...: the owner's sentence, the validated
  rule, its state; the rule and the sentence never change after the proposal,
  so the seal binds exactly what runs) and growth.automation_runs (each
  firing, once per occurrence key).
- The task class `automation_compile` of the one router call that turns a
  sentence into a rule (the same rows the router's seed file holds).

Fresh start: the rules and the automations stay (the owner's decisions); the
daily figures, the campaigns' state, the trips and the runs go.

Every new table carries company_id under FORCE RLS; nothing is deleted by the app.

Revision ID: 0042
Revises: 0040
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0042"
down_revision = "0040"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
PLATFORMS = "'google_ads', 'meta_ads'"
REGCLASSES = (
    "'growth.connections'::regclass, 'growth.metrics_daily'::regclass, 'owner.progress'::regclass"
)
TABLES = (
    "growth.ad_rules",
    "growth.ad_campaigns",
    "growth.ad_daily",
    "growth.ad_trips",
    "growth.automations",
    "growth.automation_runs",
)


def _rls(table: str) -> str:
    name = table.split(".")[1]
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
"""


def _kinds(add: bool) -> str:
    """Rewrite the `kind` check of the three tables from what it holds now
    (a parallel migration may have added kinds of its own): add ours, or take
    them out again."""
    new = "ARRAY['google_ads', 'meta_ads']"
    merged = (
        f"(kinds || {new})"
        if add
        else f"ARRAY(SELECT k FROM unnest(kinds) k WHERE k <> ALL ({new}))"
    )
    return f"""
DO $kinds$
DECLARE
    r record;
    kinds text[];
BEGIN
    FOR r IN
        SELECT c.conname, c.conrelid::regclass AS tbl, pg_get_constraintdef(c.oid) AS def
        FROM pg_constraint c
        WHERE c.contype = 'c' AND c.conrelid IN ({REGCLASSES})
    LOOP
        CONTINUE WHEN r.def NOT LIKE '%(kind = ANY%';
        IF r.def ~ '[{{][^}}]*[}}]' THEN  -- printed as '{{a,b}}'::text[] ...
            kinds := string_to_array(substring(r.def from '[{{]([^}}]*)[}}]'), ',');
        ELSE  -- ... or as ARRAY['a'::text, 'b'::text]
            SELECT array_agg(DISTINCT m[1]) INTO kinds
            FROM regexp_matches(r.def, '''([a-z_0-9]+)''::text', 'g') AS m;
        END IF;
        kinds := {merged};
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tbl, r.conname);
        EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I CHECK (kind = ANY (ARRAY[%s]))', r.tbl,
                       r.conname, (SELECT string_agg(quote_literal(k), ', ') FROM unnest(kinds) k));
    END LOOP;
END
$kinds$;
"""


UPGRADE = (
    _kinds(True)
    + f"""
-- the one router call of §31.7 (the router's seed file holds the same row)
INSERT INTO llm.task_classes (key, transferable, description)
VALUES ('automation_compile', false,
        'An automation from one sentence of the owner: one mid-model call, a strict JSON schema (contract 31.7)')
ON CONFLICT (key) DO NOTHING;

-- ============================================================ §31.6 ads ==
CREATE TABLE growth.ad_rules (
    id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id                uuid NOT NULL REFERENCES core.companies (id),
    platform                  text NOT NULL CHECK (platform IN ({PLATFORMS})),
    -- 'account' = every campaign of the company's account, else one campaign id
    scope                     text NOT NULL DEFAULT 'account' CHECK (length(scope) BETWEEN 1 AND 100),
    daily_cap                 numeric(18, 4) CHECK (daily_cap > 0),
    window_days               int NOT NULL DEFAULT 7 CHECK (window_days BETWEEN 1 AND 90),
    min_roas                  numeric(10, 4) CHECK (min_roas >= 0),
    min_spend_before_judging  numeric(18, 4) NOT NULL DEFAULT 0 CHECK (min_spend_before_judging >= 0),
    action                    text NOT NULL DEFAULT 'pause' CHECK (action IN ('pause', 'notify')),
    state                     text NOT NULL DEFAULT 'on' CHECK (state IN ('on', 'off')),
    note_fa                   text CHECK (length(note_fa) <= 300),
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now(),
    version                   int NOT NULL DEFAULT 1,
    CHECK (daily_cap IS NOT NULL OR min_roas IS NOT NULL)
);
CREATE INDEX ad_rules_company ON growth.ad_rules (company_id, platform);
CREATE TRIGGER ad_rules_immutable BEFORE UPDATE ON growth.ad_rules
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'platform', 'created_at');
CREATE TRIGGER ad_rules_version BEFORE UPDATE ON growth.ad_rules
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
GRANT SELECT, INSERT, DELETE ON growth.ad_rules TO {APP_ROLES};
GRANT UPDATE (scope, daily_cap, window_days, min_roas, min_spend_before_judging, action, state,
              note_fa, updated_at) ON growth.ad_rules TO {APP_ROLES};

-- the campaigns as the platform last showed them, and who paused one
CREATE TABLE growth.ad_campaigns (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    platform          text NOT NULL CHECK (platform IN ({PLATFORMS})),
    campaign_id       text NOT NULL CHECK (length(campaign_id) BETWEEN 1 AND 100),
    name              text NOT NULL DEFAULT '' CHECK (length(name) <= 300),
    status            text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'removed')),
    paused_by         text CHECK (paused_by IN ('rule', 'owner', 'platform')),
    paused_rule_id    uuid,
    paused_at         timestamptz,
    paused_reason_fa  text CHECK (length(paused_reason_fa) <= 500),
    resumed_at        timestamptz,
    seen_at           timestamptz NOT NULL DEFAULT now(),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, platform, campaign_id)
);
CREATE INDEX ad_campaigns_platform ON growth.ad_campaigns (platform, campaign_id);
CREATE TRIGGER ad_campaigns_immutable BEFORE UPDATE ON growth.ad_campaigns
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'platform', 'campaign_id',
                                                      'created_at');
GRANT SELECT, INSERT ON growth.ad_campaigns TO {APP_ROLES};
GRANT UPDATE (name, status, paused_by, paused_rule_id, paused_at, paused_reason_fa, resumed_at,
              seen_at, updated_at) ON growth.ad_campaigns TO {APP_ROLES};

CREATE TABLE growth.ad_daily (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    platform     text NOT NULL CHECK (platform IN ({PLATFORMS})),
    campaign_id  text NOT NULL CHECK (length(campaign_id) BETWEEN 1 AND 100),
    day          date NOT NULL,
    spend        numeric(18, 4) NOT NULL DEFAULT 0 CHECK (spend >= 0),
    clicks       bigint NOT NULL DEFAULT 0 CHECK (clicks >= 0),
    conversions  numeric(18, 4) NOT NULL DEFAULT 0 CHECK (conversions >= 0),
    revenue      numeric(18, 4) NOT NULL DEFAULT 0 CHECK (revenue >= 0),
    roas         numeric(12, 4),
    at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, platform, campaign_id, day)
);
CREATE INDEX ad_daily_recent ON growth.ad_daily (company_id, day DESC);
GRANT SELECT, INSERT ON growth.ad_daily TO {APP_ROLES};
GRANT UPDATE (spend, clicks, conversions, revenue, roas, at) ON growth.ad_daily TO {APP_ROLES};
GRANT DELETE ON growth.ad_daily TO {APP_ROLES};  -- figures older than 120 days go

-- each trip of a rule: once per rule, campaign and day (the owner's weekly summary reads it)
CREATE TABLE growth.ad_trips (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    rule_id      uuid NOT NULL,
    platform     text NOT NULL CHECK (platform IN ({PLATFORMS})),
    campaign_id  text NOT NULL CHECK (length(campaign_id) BETWEEN 1 AND 100),
    day          date NOT NULL,
    reason       text NOT NULL CHECK (reason IN ('daily_cap', 'min_roas')),
    action       text NOT NULL CHECK (action IN ('pause', 'notify')),
    outcome      text NOT NULL CHECK (outcome IN ('paused', 'notified', 'failed')),
    detail_fa    text NOT NULL CHECK (length(detail_fa) BETWEEN 1 AND 500),
    work_id      uuid REFERENCES work.work (id),
    at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (rule_id, campaign_id, day)
);
CREATE INDEX ad_trips_recent ON growth.ad_trips (company_id, at DESC);
CREATE TRIGGER ad_trips_immutable BEFORE UPDATE ON growth.ad_trips
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'rule_id', 'platform',
                                                      'campaign_id', 'day', 'reason', 'action', 'at');
GRANT SELECT, INSERT ON growth.ad_trips TO {APP_ROLES};
GRANT UPDATE (outcome, detail_fa, work_id) ON growth.ad_trips TO {APP_ROLES};

-- ================================================== §31.7 automations ==
CREATE SEQUENCE growth.automation_ref_seq;
GRANT USAGE ON SEQUENCE growth.automation_ref_seq TO {APP_ROLES};

CREATE TABLE growth.automations (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref               text NOT NULL UNIQUE
                      DEFAULT 'AT-' || lpad(nextval('growth.automation_ref_seq')::text, 4, '0'),
    -- the company it is for, or the holding's row when it is for the whole holding
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    scope             text NOT NULL CHECK (scope IN ('holding', 'company')),
    sentence_fa       text NOT NULL CHECK (length(sentence_fa) BETWEEN 1 AND 2000),
    rule              jsonb NOT NULL CHECK (jsonb_typeof(rule) = 'object'),
    state             text NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed', 'on', 'off')),
    runs              int NOT NULL DEFAULT 0 CHECK (runs >= 0),
    failures_in_row   int NOT NULL DEFAULT 0 CHECK (failures_in_row >= 0),
    last_run_at       timestamptz,
    last_error_fa     text CHECK (length(last_error_fa) <= 500),
    off_reason        text CHECK (off_reason IN ('owner', 'failures')),
    n8n_workflow      text CHECK (length(n8n_workflow) <= 200),
    sealed_at         timestamptz,
    sealed_step_up_id uuid,
    -- events: the last core.outbox row looked at; schedules: the last occurrence run
    event_cursor      bigint NOT NULL DEFAULT 0,
    last_occurrence   timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    version           int NOT NULL DEFAULT 1,
    CHECK ((state = 'proposed') = (sealed_at IS NULL))
);
CREATE INDEX automations_state ON growth.automations (state, created_at DESC);
-- the sentence and the rule never change: the seal binds exactly what runs
CREATE TRIGGER automations_immutable BEFORE UPDATE ON growth.automations
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'scope', 'sentence_fa',
                                                      'rule', 'created_at');
CREATE TRIGGER automations_version BEFORE UPDATE ON growth.automations
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
GRANT SELECT, INSERT ON growth.automations TO {APP_ROLES};
GRANT UPDATE (state, runs, failures_in_row, last_run_at, last_error_fa, off_reason, n8n_workflow,
              sealed_at, sealed_step_up_id, event_cursor, last_occurrence, updated_at)
    ON growth.automations TO {APP_ROLES};

CREATE TABLE growth.automation_runs (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    automation_id  uuid NOT NULL REFERENCES growth.automations (id),
    -- the occurrence (schedule time, metric day, event id): one run per key, never two
    key            text NOT NULL CHECK (length(key) BETWEEN 1 AND 200),
    trigger        jsonb NOT NULL CHECK (jsonb_typeof(trigger) = 'object'),
    outcome        text NOT NULL CHECK (outcome IN ('ok', 'failed', 'skipped')),
    steps          jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(steps) = 'array'),
    error_fa       text CHECK (length(error_fa) <= 500),
    at             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (automation_id, key)
);
CREATE INDEX automation_runs_recent ON growth.automation_runs (automation_id, at DESC);
CREATE TRIGGER automation_runs_append_only BEFORE UPDATE OR DELETE ON growth.automation_runs
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON growth.automation_runs TO {APP_ROLES};
"""
    + "".join(_rls(t) for t in TABLES)
)

DOWNGRADE = """
DROP TABLE growth.automation_runs;
DROP TABLE growth.automations;
DROP SEQUENCE growth.automation_ref_seq;
DROP TABLE growth.ad_trips;
DROP TABLE growth.ad_daily;
DROP TABLE growth.ad_campaigns;
DROP TABLE growth.ad_rules;
-- (the task class stays: ledger rows may name it)
DELETE FROM growth.metrics_daily WHERE kind IN ('google_ads', 'meta_ads');
DELETE FROM growth.connections WHERE kind IN ('google_ads', 'meta_ads');
ALTER TABLE owner.progress DISABLE TRIGGER progress_append_only;
DELETE FROM owner.progress WHERE kind IN ('google_ads', 'meta_ads');
ALTER TABLE owner.progress ENABLE TRIGGER progress_append_only;
""" + _kinds(False)


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
