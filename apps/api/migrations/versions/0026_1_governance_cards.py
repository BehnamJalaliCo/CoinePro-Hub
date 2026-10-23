"""Prompt 11 §4-§10 (contract §20.4-§20.10): the three cards and the live
scorecard, OKRs, the 30/60/90-day decision outcome reviews, the authority
matrix, the risk register, the change calendar and the batch seal. Every
table of those sections is made here (the meeting room, the charter and the
four-layer knowledge base are migration 0026, chained before this one).

Schema `governance` (CREATE ... IF NOT EXISTS: 0026 makes it too). Company
tables carry company_id under FORCE RLS (the once-per-query policy of 0009):

  kpi_sets         one row per company: the version GET/PUT /kpis/{company} use
  kpis             a KPI's definition (versioned by hand: the collector's
                   last_* columns are a cache, not a new version)
  kpi_values       the time series (append-only)
  kpi_changes      every definition change (append-only)
  objectives       OB-0001; key_results KR-0001; okr_checkins (append-only)
  outcome_reviews  OR-0001: day 30, 60 and 90 of a sealed decision's `expected`
  risks            RK-0001 (score = likelihood x impact); risk_history (append-only)
  calendar_events  CE-0001 (code fills deploys, freezes, backups, holidays)
  batches          B-0001: one batch seal (append-only)

Holding configuration without a company (read by the api and the worker only,
like tools.accounts): authority (the matrix; OPA reads it as
data.hq.authority), authority_history (append-only) and rollout (when this
prompt went live: the 7 days in which a proposal without `expected` is only
a warning).

cartable.decisions gains `expected` and `warnings` (set once, at the
proposal); work.work gains key_result_id. The decision kinds gain the six of
contract §20.11 (appended to what the constraint holds, NOT VALID; the
head, 0028_1, validates every kind at once, so a round trip keeps the cards
of a later revision). PR-090,
PR-112, PR-113 and PR-116 become active (a data migration with an audit row
each) where only their seeded, paused versions exist; on a fresh database the
seed does the same right after it seeds them (hq_api.domain.gov_checks).

Revision ID: 0026_1
Revises: 0026 (the meeting room, the charter and the knowledge base)
"""

from __future__ import annotations

import re

from hq_api.migration_sql import execute_script

revision = "0026_1"
down_revision = "0026"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
NEW_KINDS = (
    "meeting_resolution",
    "charter_amendment",
    "okr",
    "knowledge_entry",
    "risk_acceptance",
    "authority_change",
)
ACTIVATED = ("PR-090", "PR-112", "PR-113", "PR-116")

TABLES = (
    "governance.kpi_sets",
    "governance.kpis",
    "governance.kpi_values",
    "governance.kpi_changes",
    "governance.objectives",
    "governance.key_results",
    "governance.okr_checkins",
    "governance.outcome_reviews",
    "governance.risks",
    "governance.risk_history",
    "governance.calendar_events",
    "governance.batches",
)
APPEND_ONLY = (
    "governance.kpi_values",
    "governance.kpi_changes",
    "governance.okr_checkins",
    "governance.risk_history",
    "governance.batches",
)
SEQUENCES = (
    "governance.objective_ref_seq",
    "governance.key_result_ref_seq",
    "governance.outcome_ref_seq",
    "governance.risk_ref_seq",
    "governance.calendar_ref_seq",
    "governance.batch_ref_seq",
)
ACTORS = "'owner', 'agent', 'service', 'rule'"
SOURCE = (
    "jsonb_typeof(@COL@) = 'object' AND @COL@ ? 'kind' AND @COL@ ? 'ref' "
    "AND length(@COL@->>'ref') BETWEEN 1 AND 500"
)

UPGRADE = r"""
CREATE SCHEMA IF NOT EXISTS governance;
GRANT USAGE ON SCHEMA governance TO @APP@;

-- ================================================================ rollout ==
CREATE TABLE governance.rollout (
    key  text PRIMARY KEY CHECK (key ~ '^[a-z0-9_.]{1,40}$'),
    at   timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER rollout_append_only BEFORE UPDATE OR DELETE ON governance.rollout
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
INSERT INTO governance.rollout (key) VALUES ('p11.governance');
GRANT SELECT ON governance.rollout TO @APP@;

-- =================================================================== KPIs ==
CREATE TABLE governance.kpi_sets (
    company_id   uuid PRIMARY KEY REFERENCES core.companies (id),
    seeded_from  text NOT NULL CHECK (seeded_from IN ('standard', 'founding')),
    version      int NOT NULL DEFAULT 1,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER kpi_sets_version BEFORE UPDATE ON governance.kpi_sets
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

CREATE TABLE governance.kpis (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    key              text NOT NULL CHECK (key ~ '^[a-z][a-z0-9_.]{1,60}$'),
    card             text NOT NULL CHECK (card IN ('stability', 'growth', 'safety_cost')),
    name_fa          text NOT NULL CHECK (length(name_fa) BETWEEN 1 AND 200),
    unit             text NOT NULL DEFAULT '' CHECK (length(unit) <= 20),
    direction        text NOT NULL CHECK (direction IN ('up', 'down', 'range')),
    -- {kind: "query", query: "<registry key>"} | {kind: "manual"}
    source           jsonb NOT NULL CHECK (jsonb_typeof(source) = 'object'
                          AND (source->>'kind' = 'manual'
                               OR (source->>'kind' = 'query' AND source->>'query' ~ '^[a-z][a-z0-9_.]{2,60}$'))),
    freshness_hours  int NOT NULL CHECK (freshness_hours BETWEEN 1 AND 8760),
    target           numeric(20, 6),
    target_max       numeric(20, 6),     -- direction 'range' only: the upper bound
    scorecard        boolean NOT NULL DEFAULT false,
    aggregate        text NOT NULL DEFAULT 'sum' CHECK (aggregate IN ('sum', 'avg', 'min', 'max')),
    status           text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused')),
    origin           text NOT NULL CHECK (origin IN ('standard', 'founding', 'owner')),
    last_value       numeric(20, 6),
    last_at          timestamptz,
    last_source_ref  jsonb CHECK (last_source_ref IS NULL OR jsonb_typeof(last_source_ref) = 'object'),
    stale_since      timestamptz,
    version          int NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, key),
    UNIQUE (company_id, id),
    CHECK (direction = 'range' OR target_max IS NULL),
    CHECK ((last_value IS NULL) = (last_at IS NULL))
);
CREATE TRIGGER kpis_immutable BEFORE UPDATE ON governance.kpis
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'key', 'source', 'origin',
                                                      'created_at');

CREATE TABLE governance.kpi_values (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    kpi_id            uuid NOT NULL,
    at                timestamptz NOT NULL,
    value             numeric(20, 6) NOT NULL,
    source_ref        jsonb NOT NULL CHECK (@SOURCE_REF@),
    recorded_by_kind  text NOT NULL CHECK (recorded_by_kind IN (@ACTORS@)),
    recorded_by_code  text NOT NULL CHECK (length(recorded_by_code) BETWEEN 1 AND 64),
    created_at        timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, kpi_id) REFERENCES governance.kpis (company_id, id)
);
CREATE INDEX kpi_values_series ON governance.kpi_values (kpi_id, at DESC);

CREATE TABLE governance.kpi_changes (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    kpi_id      uuid NOT NULL,
    version     int NOT NULL CHECK (version >= 1),
    change      jsonb NOT NULL CHECK (jsonb_typeof(change) = 'object'),
    by_kind     text NOT NULL CHECK (by_kind IN (@ACTORS@)),
    by_code     text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64),
    at          timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, kpi_id) REFERENCES governance.kpis (company_id, id)
);

-- ==================================================================== OKR ==
CREATE SEQUENCE governance.objective_ref_seq;
CREATE SEQUENCE governance.key_result_ref_seq;
CREATE TABLE governance.objectives (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref              text NOT NULL UNIQUE
                          DEFAULT 'OB-' || lpad(nextval('governance.objective_ref_seq')::text, 4, '0'),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    quarter          text NOT NULL CHECK (quarter ~ '^1[3-9][0-9]{2}-Q[1-4]$'),
    title_fa         text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    why_md           text NOT NULL DEFAULT '' CHECK (length(why_md) <= 5000),
    owner_kind       text NOT NULL CHECK (owner_kind IN ('owner', 'agent')),
    owner_code       text NOT NULL CHECK (length(owner_code) BETWEEN 1 AND 64),
    status           text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'proposed', 'active', 'closed')),
    decision_id      uuid REFERENCES cartable.decisions (id),
    activated_at     timestamptz,
    closed_at        timestamptz,
    created_by_kind  text NOT NULL CHECK (created_by_kind IN (@ACTORS@)),
    created_by_code  text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
    version          int NOT NULL DEFAULT 1,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    CHECK (status <> 'active' OR activated_at IS NOT NULL)
);
CREATE INDEX objectives_company ON governance.objectives (company_id, quarter, status);
CREATE TRIGGER objectives_immutable BEFORE UPDATE ON governance.objectives
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'quarter', 'created_at');
CREATE TRIGGER objectives_version BEFORE UPDATE ON governance.objectives
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

CREATE TABLE governance.key_results (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref              text NOT NULL UNIQUE
                          DEFAULT 'KR-' || lpad(nextval('governance.key_result_ref_seq')::text, 4, '0'),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    objective_id     uuid NOT NULL,
    title_fa         text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    kpi_key          text CHECK (kpi_key ~ '^[a-z][a-z0-9_.]{1,60}$'),
    metric_fa        text CHECK (length(metric_fa) BETWEEN 1 AND 300),
    start            numeric(20, 6) NOT NULL,
    target           numeric(20, 6) NOT NULL,
    current          numeric(20, 6),
    confidence       numeric(3, 2) CHECK (confidence BETWEEN 0 AND 1),
    weight           numeric(6, 2) NOT NULL DEFAULT 1 CHECK (weight > 0 AND weight <= 100),
    last_checkin_at  timestamptz,
    version          int NOT NULL DEFAULT 1,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, objective_id) REFERENCES governance.objectives (company_id, id),
    CHECK ((kpi_key IS NULL) <> (metric_fa IS NULL))   -- a KPI, or a metric checked in by hand
);
CREATE INDEX key_results_objective ON governance.key_results (objective_id);
CREATE TRIGGER key_results_immutable BEFORE UPDATE ON governance.key_results
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'objective_id', 'kpi_key',
                                                      'metric_fa', 'created_at');
CREATE TRIGGER key_results_version BEFORE UPDATE ON governance.key_results
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

CREATE TABLE governance.okr_checkins (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    key_result_id  uuid NOT NULL,
    at             timestamptz NOT NULL DEFAULT now(),
    by_kind        text NOT NULL CHECK (by_kind IN ('owner', 'agent')),
    by_code        text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64),
    confidence     numeric(3, 2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    note_md        text NOT NULL CHECK (length(note_md) BETWEEN 1 AND 5000),
    evidence       jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(evidence) = 'array'),
    current        numeric(20, 6),
    FOREIGN KEY (company_id, key_result_id) REFERENCES governance.key_results (company_id, id)
);
CREATE INDEX okr_checkins_kr ON governance.okr_checkins (key_result_id, at DESC);

-- Work.key_result (contract §20.5): set by POST /work and work.delegate.
ALTER TABLE work.work ADD COLUMN key_result_id uuid;
ALTER TABLE work.work ADD CONSTRAINT work_key_result
    FOREIGN KEY (company_id, key_result_id) REFERENCES governance.key_results (company_id, id);

-- ================================================== decision outcomes (§6) ==
ALTER TABLE cartable.decisions
    ADD COLUMN expected jsonb CHECK (expected IS NULL OR jsonb_typeof(expected) = 'object'),
    ADD COLUMN warnings text[] NOT NULL DEFAULT '{}' CHECK (cardinality(warnings) <= 10);
CREATE TRIGGER decisions_expected_immutable BEFORE UPDATE ON cartable.decisions
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('expected', 'warnings');

CREATE SEQUENCE governance.outcome_ref_seq;
CREATE TABLE governance.outcome_reviews (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref                text NOT NULL UNIQUE
                            DEFAULT 'OR-' || lpad(nextval('governance.outcome_ref_seq')::text, 4, '0'),
    company_id         uuid NOT NULL REFERENCES core.companies (id),
    decision_id        uuid NOT NULL REFERENCES cartable.decisions (id),
    decision_ref       text NOT NULL CHECK (decision_ref ~ '^D-[0-9]{4,}$'),
    day                int NOT NULL CHECK (day IN (30, 60, 90)),
    due_at             timestamptz NOT NULL,
    expected           jsonb NOT NULL CHECK (jsonb_typeof(expected) = 'object'),
    measured           jsonb CHECK (measured IS NULL OR jsonb_typeof(measured) = 'object'),
    verdict            text NOT NULL DEFAULT 'pending'
                            CHECK (verdict IN ('pending', 'met', 'partly', 'missed', 'unmeasurable')),
    proposer_kind      text NOT NULL CHECK (proposer_kind IN ('owner', 'agent', 'service')),
    proposer_code      text NOT NULL CHECK (length(proposer_code) BETWEEN 1 AND 64),
    proposer_note_md   text CHECK (length(proposer_note_md) <= 5000),
    proposer_evidence  jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(proposer_evidence) = 'array'),
    overseer_note_md   text CHECK (length(overseer_note_md) <= 5000),
    status             text NOT NULL DEFAULT 'due' CHECK (status IN ('due', 'answered', 'verified')),
    due_emitted_at     timestamptz,
    decided_by_kind    text CHECK (decided_by_kind IN (@ACTORS@)),
    decided_by_code    text CHECK (length(decided_by_code) <= 64),
    decided_at         timestamptz,
    version            int NOT NULL DEFAULT 1,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (decision_id, day),
    CHECK ((status = 'verified') = (decided_at IS NOT NULL))
);
CREATE INDEX outcome_reviews_due ON governance.outcome_reviews (due_at) WHERE status <> 'verified';
CREATE TRIGGER outcome_reviews_immutable BEFORE UPDATE ON governance.outcome_reviews
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'decision_id', 'decision_ref',
                                                      'day', 'due_at', 'expected', 'proposer_kind',
                                                      'proposer_code', 'created_at');
CREATE TRIGGER outcome_reviews_version BEFORE UPDATE ON governance.outcome_reviews
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
-- A verdict, once verified, is final (the owner's record of who was right).
CREATE FUNCTION governance.outcome_final() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.status = 'verified' AND (NEW.verdict IS DISTINCT FROM OLD.verdict
                                        OR NEW.status IS DISTINCT FROM OLD.status) THEN
            RAISE EXCEPTION 'outcome review % is verified', OLD.ref USING ERRCODE = 'HQI01';
        END IF;
        RETURN NEW;
    END $$;
CREATE TRIGGER outcome_reviews_final BEFORE UPDATE ON governance.outcome_reviews
    FOR EACH ROW EXECUTE FUNCTION governance.outcome_final();

-- ======================================================= authority matrix ==
-- Holding configuration (no company): rows seeded from apps/api/seed/authority.yaml.
-- A locked row's actor and limit change only through the seed (role hq).
CREATE TABLE governance.authority (
    key              text PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_.]{1,60}$'),
    title_fa         text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    action           text NOT NULL CHECK (length(action) BETWEEN 1 AND 100),
    actor            text NOT NULL CHECK (actor ~ '^[a-z][a-z0-9_]{1,40}$'),
    default_actor    text NOT NULL CHECK (default_actor ~ '^[a-z][a-z0-9_]{1,40}$'),
    scope            text NOT NULL CHECK (scope IN ('own_company', 'holding')),
    lim              jsonb CHECK (lim IS NULL OR jsonb_typeof(lim) = 'object'),
    bounds           jsonb CHECK (bounds IS NULL OR jsonb_typeof(bounds) = 'object'),
    step_up          boolean NOT NULL DEFAULT false,
    class            text NOT NULL CHECK (class IN ('A0', 'A1', 'A2', 'A3', 'A4')),
    locked           boolean NOT NULL DEFAULT false,
    note_fa          text NOT NULL DEFAULT '' CHECK (length(note_fa) <= 2000),
    sort             int NOT NULL DEFAULT 0,
    updated_by_kind  text NOT NULL DEFAULT 'service' CHECK (updated_by_kind IN ('owner', 'service')),
    updated_by_code  text NOT NULL DEFAULT 'seed' CHECK (length(updated_by_code) BETWEEN 1 AND 64),
    version          int NOT NULL DEFAULT 1,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION governance.authority_locked() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.locked AND current_user <> 'hq'
           AND (NEW.lim::text IS DISTINCT FROM OLD.lim::text OR NEW.actor IS DISTINCT FROM OLD.actor
                OR NEW.locked IS DISTINCT FROM OLD.locked) THEN
            RAISE EXCEPTION 'authority rule % is locked', OLD.key USING ERRCODE = 'HQI01';
        END IF;
        IF current_user <> 'hq' AND (NEW.bounds::text IS DISTINCT FROM OLD.bounds::text
                                     OR NEW.class IS DISTINCT FROM OLD.class
                                     OR NEW.default_actor IS DISTINCT FROM OLD.default_actor) THEN
            RAISE EXCEPTION 'authority rule %: bounds, class and default actor come from the seed', OLD.key
                USING ERRCODE = 'HQI01';
        END IF;
        RETURN NEW;
    END $$;
CREATE TRIGGER authority_locked BEFORE UPDATE ON governance.authority
    FOR EACH ROW EXECUTE FUNCTION governance.authority_locked();
CREATE TRIGGER authority_version BEFORE UPDATE ON governance.authority
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
CREATE TRIGGER authority_no_delete BEFORE DELETE ON governance.authority
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();

CREATE TABLE governance.authority_history (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key           text NOT NULL REFERENCES governance.authority (key),
    version       int NOT NULL,
    before        jsonb NOT NULL CHECK (jsonb_typeof(before) = 'object'),
    after         jsonb NOT NULL CHECK (jsonb_typeof(after) = 'object'),
    by_kind       text NOT NULL CHECK (by_kind IN ('owner', 'service')),
    by_code       text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64),
    decision_ref  text CHECK (decision_ref ~ '^D-[0-9]{4,}$'),
    at            timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER authority_history_append_only BEFORE UPDATE OR DELETE ON governance.authority_history
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT ON governance.authority, governance.authority_history TO @APP@;
GRANT UPDATE (actor, lim, updated_by_kind, updated_by_code) ON governance.authority TO hq_api;
GRANT INSERT ON governance.authority_history TO hq_api;

-- ================================================================== risks ==
CREATE SEQUENCE governance.risk_ref_seq;
CREATE TABLE governance.risks (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref                   text NOT NULL UNIQUE
                               DEFAULT 'RK-' || lpad(nextval('governance.risk_ref_seq')::text, 4, '0'),
    company_id            uuid NOT NULL REFERENCES core.companies (id),
    title_fa              text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    body_md               text NOT NULL DEFAULT '' CHECK (length(body_md) <= 20000),
    category              text NOT NULL CHECK (category IN ('product', 'security', 'data', 'money', 'people',
                                                            'vendor', 'ops', 'reputation')),
    likelihood            int NOT NULL CHECK (likelihood BETWEEN 1 AND 5),
    impact                int NOT NULL CHECK (impact BETWEEN 1 AND 5),
    score                 int GENERATED ALWAYS AS (likelihood * impact) STORED,
    owner_kind            text NOT NULL CHECK (owner_kind IN ('owner', 'agent')),
    owner_code            text NOT NULL CHECK (length(owner_code) BETWEEN 1 AND 64),
    mitigation_md         text CHECK (length(mitigation_md) <= 20000),
    status                text NOT NULL DEFAULT 'open'
                               CHECK (status IN ('open', 'mitigating', 'accepted', 'closed')),
    review_at             timestamptz NOT NULL,
    accepted_decision_id  uuid REFERENCES cartable.decisions (id),
    accepted_until        timestamptz,
    links                 jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(links) = 'object'),
    origin                text NOT NULL CHECK (origin IN ('owner', 'agent', 'finding', 'postmortem')),
    draft                 boolean NOT NULL DEFAULT false,
    dedupe_key            text CHECK (length(dedupe_key) <= 200),
    review_work_id        uuid,
    closed_at             timestamptz,
    closed_by_code        text CHECK (length(closed_by_code) <= 64),
    created_by_kind       text NOT NULL CHECK (created_by_kind IN (@ACTORS@)),
    created_by_code       text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
    version               int NOT NULL DEFAULT 1,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    CHECK (status <> 'accepted' OR (accepted_decision_id IS NOT NULL AND accepted_until IS NOT NULL)),
    CHECK ((status = 'closed') = (closed_at IS NOT NULL))
);
CREATE UNIQUE INDEX risks_dedupe ON governance.risks (company_id, dedupe_key) WHERE dedupe_key IS NOT NULL;
CREATE INDEX risks_company ON governance.risks (company_id, status, review_at);
CREATE TRIGGER risks_immutable BEFORE UPDATE ON governance.risks
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'origin', 'dedupe_key',
                                                      'created_by_kind', 'created_by_code', 'created_at');
CREATE TRIGGER risks_version BEFORE UPDATE ON governance.risks
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

CREATE TABLE governance.risk_history (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    risk_id     uuid NOT NULL,
    at          timestamptz NOT NULL DEFAULT now(),
    by_kind     text NOT NULL CHECK (by_kind IN (@ACTORS@)),
    by_code     text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64),
    change      jsonb NOT NULL CHECK (jsonb_typeof(change) = 'object'),
    note        text NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
    FOREIGN KEY (company_id, risk_id) REFERENCES governance.risks (company_id, id)
);
CREATE INDEX risk_history_risk ON governance.risk_history (risk_id, at);

-- =============================================================== calendar ==
CREATE SEQUENCE governance.calendar_ref_seq;
CREATE TABLE governance.calendar_events (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref              text NOT NULL UNIQUE
                          DEFAULT 'CE-' || lpad(nextval('governance.calendar_ref_seq')::text, 4, '0'),
    company_id       uuid NOT NULL REFERENCES core.companies (id),   -- the holding's: holding-wide
    kind             text NOT NULL CHECK (kind IN ('deploy', 'campaign', 'event', 'maintenance', 'meeting',
                                                   'freeze', 'holiday')),
    title_fa         text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    starts_at        timestamptz NOT NULL,
    ends_at          timestamptz NOT NULL,
    source           jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(source) = 'object'),
    status           text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'done', 'cancelled')),
    risk             text NOT NULL DEFAULT 'low' CHECK (risk IN ('low', 'medium', 'high')),
    repo             text CHECK (length(repo) <= 200),    -- a deploy's service (two deploys of one service)
    auto_key         text UNIQUE CHECK (length(auto_key) <= 200),  -- an event code filled in, once
    created_by_kind  text NOT NULL CHECK (created_by_kind IN (@ACTORS@)),
    created_by_code  text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
    version          int NOT NULL DEFAULT 1,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CHECK (ends_at >= starts_at),
    CHECK (ends_at - starts_at <= interval '400 days')
);
CREATE INDEX calendar_events_time ON governance.calendar_events (starts_at, ends_at);
CREATE INDEX calendar_events_company ON governance.calendar_events (company_id, starts_at);
CREATE TRIGGER calendar_events_immutable BEFORE UPDATE ON governance.calendar_events
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'kind', 'auto_key',
                                                      'created_by_kind', 'created_by_code', 'created_at');
CREATE TRIGGER calendar_events_version BEFORE UPDATE ON governance.calendar_events
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- ============================================================ batch seal ==
CREATE SEQUENCE governance.batch_ref_seq;
CREATE TABLE governance.batches (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref            text NOT NULL UNIQUE DEFAULT 'B-' || lpad(nextval('governance.batch_ref_seq')::text, 4, '0'),
    company_id     uuid NOT NULL REFERENCES core.companies (id),   -- the holding's
    items          jsonb NOT NULL CHECK (jsonb_typeof(items) = 'array' AND jsonb_array_length(items) BETWEEN 1 AND 200),
    target_sha256  text NOT NULL CHECK (target_sha256 ~ '^[0-9a-f]{64}$'),
    step_up_id     uuid NOT NULL,
    note           text CHECK (length(note) <= 5000),
    created_at     timestamptz NOT NULL DEFAULT now()
);
"""


def _rls(table: str) -> str:
    name = table.replace(".", "_")
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
        CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
    """


def _no_delete(table: str) -> str:
    name = table.replace(".", "_")
    return f"""CREATE TRIGGER {name}_no_delete BEFORE DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();"""


def _kinds_sql(add: tuple[str, ...], drop: tuple[str, ...]) -> str:
    """Rewrite decisions_kind_check from the kinds it holds now (plus `add`,
    minus `drop`), NOT VALID: an earlier or later migration's kinds stay."""
    added = ", ".join(f"'{k}'" for k in add)
    dropped = ", ".join(f"'{k}'" for k in drop)
    return f"""
        DO $$
        DECLARE kinds text;
        BEGIN
            SELECT string_agg(quote_literal(k), ', ' ORDER BY k) INTO kinds FROM (
                SELECT DISTINCT m[1] AS k
                FROM pg_constraint c,
                     regexp_matches(pg_get_constraintdef(c.oid), '''([a-z0-9_]+)''', 'g') AS m
                WHERE c.conrelid = 'cartable.decisions'::regclass AND c.conname = 'decisions_kind_check'
                UNION SELECT unnest(ARRAY[{added}]::text[])
            ) x WHERE k IS NOT NULL AND k <> ALL (ARRAY[{dropped}]::text[]);
            ALTER TABLE cartable.decisions DROP CONSTRAINT decisions_kind_check;
            EXECUTE format('ALTER TABLE cartable.decisions ADD CONSTRAINT decisions_kind_check '
                           'CHECK (kind IN (%s)) NOT VALID', kinds);
        END $$;
    """


# PR-090, PR-112, PR-113, PR-116 (prompt 11 §4.7, §12.2): a new active version
# of each protocol whose every version is the seeded one and whose current
# version is paused (a protocol the owner touched keeps the owner's version).
ACTIVATE = r"""
DO $act$
DECLARE
    p record;
    holding uuid;
BEGIN
    SELECT id INTO holding FROM core.companies WHERE kind = 'holding' ORDER BY created_at LIMIT 1;
    FOR p IN
        SELECT DISTINCT ON (ref) * FROM oversight.protocols
         WHERE ref = ANY (ARRAY[@REFS@]) ORDER BY ref, version DESC
    LOOP
        CONTINUE WHEN p.status <> 'paused'
            OR EXISTS (SELECT 1 FROM oversight.protocols x WHERE x.ref = p.ref AND x.source <> 'seed');
        INSERT INTO oversight.protocols (company_id, ref, version, title_fa, area, check_md, method,
                                         schedule, scope, evidence_md, severity, answerable, status,
                                         source, created_by_kind, created_by_code)
        VALUES (p.company_id, p.ref, p.version + 1, p.title_fa, p.area, p.check_md, p.method, p.schedule,
                p.scope, p.evidence_md, p.severity, p.answerable, 'active', 'seed', 'service',
                'migration-0026_1');
        INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action,
                                   action_class, target_kind, target_ref, summary)
        VALUES ('system', 'system', 'system', coalesce(holding, p.company_id), 'protocol.activate', 'A1',
                'protocol', p.ref, 'prompt 11: paused -> active (v' || (p.version + 1) || ')');
    END LOOP;
END
$act$;
"""


def upgrade() -> None:
    sql = (
        UPGRADE.replace("@APP@", APP_ROLES)
        .replace("@ACTORS@", ACTORS)
        .replace("@SOURCE_REF@", SOURCE.replace("@COL@", "source_ref"))
    )
    assert not re.search(r"@[A-Z_]+@", sql), "an unreplaced placeholder"
    execute_script(sql)
    grants = [_rls(t) for t in TABLES]
    grants += [_no_delete(t) for t in TABLES]
    grants += [
        f"""CREATE TRIGGER {t.replace(".", "_")}_append_only BEFORE UPDATE ON {t}
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();"""
        for t in APPEND_ONLY
    ]
    mutable = ", ".join(t for t in TABLES if t not in APPEND_ONLY)
    grants.append(f"GRANT SELECT, INSERT ON {', '.join(TABLES)} TO {APP_ROLES};")
    grants.append(f"GRANT UPDATE ON {mutable} TO {APP_ROLES};")
    grants.append(f"GRANT USAGE ON SEQUENCE {', '.join(SEQUENCES)} TO {APP_ROLES};")
    execute_script("\n".join(grants))
    # NOT VALID (0026 added its three NOT VALID too): the head (0028_1)
    # validates every card against every kind of prompts 11, 12 and 13, so a
    # down-and-up run keeps a later revision's cards (test_hiring's round trip).
    execute_script(_kinds_sql(NEW_KINDS, ()))
    execute_script(ACTIVATE.replace("@REFS@", ", ".join(f"'{r}'" for r in ACTIVATED)))


def downgrade() -> None:
    # The six kinds stay in decisions_kind_check: cards of those kinds outlive
    # the tables (0026's downgrade then takes its own three out, NOT VALID; the
    # re-upgrade validates at the head, 0028_1: the 0009 round trip of test_hiring).
    # The activated protocols keep their versions.
    execute_script(
        """
        ALTER TABLE work.work DROP CONSTRAINT work_key_result;
        ALTER TABLE work.work DROP COLUMN key_result_id;
        DROP TRIGGER decisions_expected_immutable ON cartable.decisions;
        ALTER TABLE cartable.decisions DROP COLUMN expected, DROP COLUMN warnings;
        DROP TABLE governance.batches, governance.calendar_events, governance.risk_history,
            governance.risks, governance.authority_history, governance.authority,
            governance.outcome_reviews, governance.okr_checkins, governance.key_results,
            governance.objectives, governance.kpi_changes, governance.kpi_values, governance.kpis,
            governance.kpi_sets, governance.rollout;
        DROP FUNCTION governance.outcome_final(), governance.authority_locked();
        DROP SEQUENCE governance.objective_ref_seq, governance.key_result_ref_seq,
            governance.outcome_ref_seq, governance.risk_ref_seq, governance.calendar_ref_seq,
            governance.batch_ref_seq;
        """
    )
