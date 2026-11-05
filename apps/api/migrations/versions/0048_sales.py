"""Prompt 24 (contract §33.1, §33.4–33.6): usage in the advisor's words, a small CRM
per company, affiliate follow-up, the money impact of decisions.

- sales.usage_reports (UR-0001 ...): one report of the holding's own spend, the
  pack (numbers, by code) and the words (a mid model, or a plain text by code
  when the model could not answer); holding-level (the holding's id), so no
  company's agent ever reads it. A scheduled report is once per period.
- sales.lead_stages (per company, data: key, title, position, kind open | won |
  lost), sales.leads (LD-000001 ...: a pseudonym and a display name only; the
  contact details stay in the company's own systems), sales.lead_events (the
  trail of each lead, append only).
- sales.affiliate_receipts (what the owner or the FIN manager says arrived, per
  account and month) and sales.affiliate_gaps (due against received, per
  account and month, with the follow-up it opened).
- cartable.decisions gains `impact` (measured by code, or an estimate of the
  model, labelled) and `impact_tries` (the estimate is tried a few times only).
- The router's task classes `usage_report`, `sales_followup`, `decision_impact`
  (the router's seed file holds the same rows).

Fresh start: the stage definitions and what the owner said was received stay;
the reports, the leads and their trails, and the gaps go (they are rebuilt).

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
    "sales.usage_reports",
    "sales.lead_stages",
    "sales.leads",
    "sales.lead_events",
    "sales.affiliate_receipts",
    "sales.affiliate_gaps",
)
SOURCES = "'support', 'telegram', 'site', 'payment', 'referral', 'manual'"
EVENT_KINDS = "'created', 'stage', 'note', 'reminder', 'draft', 'paid', 'payment', 'assigned', 'updated'"


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
CREATE SCHEMA sales;
GRANT USAGE ON SCHEMA sales TO {APP_ROLES};

-- the three router calls of §33 (the router's seed file holds the same rows)
INSERT INTO llm.task_classes (key, transferable, description)
VALUES ('usage_report', false,
        'The holding''s usage in the advisor''s words: a mid model, low effort, a strict schema (contract 33.1)'),
       ('sales_followup', false,
        'A follow-up message drafted for a lead or an affiliate gap, in the company''s voice; never sent (contract 33.4, 33.5)'),
       ('decision_impact', false,
        'The money impact of a proposal or an A3 card, one call per card, a strict schema, labelled an estimate (contract 33.6)')
ON CONFLICT (key) DO NOTHING;

-- ====================================================== §33.1 usage reports ==
CREATE SEQUENCE sales.usage_report_ref_seq;
GRANT USAGE ON SEQUENCE sales.usage_report_ref_seq TO {APP_ROLES};
CREATE TABLE sales.usage_reports (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref         text NOT NULL UNIQUE
                     DEFAULT core.pad_ref('UR-', nextval('sales.usage_report_ref_seq'), 4),
    company_id  uuid NOT NULL REFERENCES core.companies (id),        -- the holding's
    period      text NOT NULL CHECK (period IN ('day', 'week')),
    from_at     timestamptz NOT NULL,
    to_at       timestamptz NOT NULL,
    pack        jsonb NOT NULL CHECK (jsonb_typeof(pack) = 'object'),
    text        jsonb CHECK (text IS NULL OR jsonb_typeof(text) = 'object'),   -- {{lines_fa, saving_fa}}
    words       text NOT NULL DEFAULT 'model' CHECK (words IN ('model', 'code')),
    made_by     text NOT NULL CHECK (made_by IN ('schedule', 'owner')),
    delivered   jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(delivered) = 'object'),
    at          timestamptz NOT NULL DEFAULT now(),
    CHECK (to_at > from_at)
);
CREATE INDEX usage_reports_recent ON sales.usage_reports (period, at DESC);
-- a scheduled report exists once per period; the owner may make as many as he likes
CREATE UNIQUE INDEX usage_reports_scheduled ON sales.usage_reports (period, from_at)
    WHERE made_by = 'schedule';
CREATE TRIGGER usage_reports_immutable BEFORE UPDATE ON sales.usage_reports
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'period', 'from_at',
                                                      'to_at', 'pack', 'made_by', 'at');
GRANT SELECT, INSERT ON sales.usage_reports TO {APP_ROLES};
GRANT UPDATE (text, words, delivered) ON sales.usage_reports TO {APP_ROLES};

-- ============================================================ §33.4 the CRM ==
CREATE TABLE sales.lead_stages (
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    key         text NOT NULL CHECK (key ~ '^[a-z][a-z0-9_]{{1,30}}$'),
    title_fa    text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 60),
    position    int NOT NULL CHECK (position BETWEEN 0 AND 100),
    kind        text NOT NULL DEFAULT 'open' CHECK (kind IN ('open', 'won', 'lost')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, key)
);
GRANT SELECT, INSERT ON sales.lead_stages TO {APP_ROLES};
GRANT UPDATE (title_fa, position, kind) ON sales.lead_stages TO {APP_ROLES};

CREATE SEQUENCE sales.lead_ref_seq;
GRANT USAGE ON SEQUENCE sales.lead_ref_seq TO {APP_ROLES};
CREATE TABLE sales.leads (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref              text NOT NULL UNIQUE
                          DEFAULT core.pad_ref('LD-', nextval('sales.lead_ref_seq'), 6),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    source           text NOT NULL CHECK (source IN ({SOURCES})),
    name_fa          text CHECK (length(name_fa) BETWEEN 1 AND 200),
    contact          text NOT NULL CHECK (contact ~ '^[A-Za-z0-9_:.-]{{8,128}}$'),     -- a pseudonym, never a contact detail
    stage            text NOT NULL,
    value_usdt       numeric(18, 4) CHECK (value_usdt >= 0),
    next_at          timestamptz,
    next_fa          text CHECK (length(next_fa) <= 300),
    assignee_kind    text CHECK (assignee_kind IN ('owner', 'agent')),
    assignee_code    text CHECK (length(assignee_code) BETWEEN 1 AND 64),
    lost_reason_fa   text CHECK (length(lost_reason_fa) <= 300),
    paid_at          timestamptz,
    reminded_for     timestamptz,                         -- the `next_at` the last reminder was made for
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    version          int NOT NULL DEFAULT 1,
    UNIQUE (company_id, contact),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, stage) REFERENCES sales.lead_stages (company_id, key),
    CHECK ((assignee_kind IS NULL) = (assignee_code IS NULL))
);
CREATE INDEX leads_company_stage ON sales.leads (company_id, stage, updated_at DESC);
CREATE INDEX leads_due ON sales.leads (next_at) WHERE next_at IS NOT NULL;
CREATE TRIGGER leads_immutable BEFORE UPDATE ON sales.leads
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'source', 'contact',
                                                      'created_at');
CREATE TRIGGER leads_version BEFORE UPDATE ON sales.leads
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
GRANT SELECT, INSERT ON sales.leads TO {APP_ROLES};
GRANT UPDATE (name_fa, stage, value_usdt, next_at, next_fa, assignee_kind, assignee_code,
              lost_reason_fa, paid_at, reminded_for) ON sales.leads TO {APP_ROLES};

CREATE TABLE sales.lead_events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    lead_id     uuid NOT NULL,
    at          timestamptz NOT NULL DEFAULT now(),
    kind        text NOT NULL CHECK (kind IN ({EVENT_KINDS})),
    note_fa     text NOT NULL DEFAULT '' CHECK (length(note_fa) <= 500),
    data        jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(data) = 'object'),
    FOREIGN KEY (company_id, lead_id) REFERENCES sales.leads (company_id, id)
);
CREATE INDEX lead_events_lead ON sales.lead_events (lead_id, id);
CREATE TRIGGER lead_events_append_only BEFORE UPDATE OR DELETE ON sales.lead_events
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON sales.lead_events TO {APP_ROLES};

-- ================================================== §33.5 affiliate follow-up ==
-- what arrived, said by the owner or the FIN manager (the exchange pays outside the hub)
CREATE TABLE sales.affiliate_receipts (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL REFERENCES core.companies (id),
    account_id    uuid NOT NULL REFERENCES revenue.accounts (id),
    month         date NOT NULL CHECK (date_trunc('month', month) = month),
    received_usdt numeric(24, 8) NOT NULL CHECK (received_usdt >= 0),
    note_fa       text CHECK (length(note_fa) <= 300),
    by_kind       text NOT NULL CHECK (by_kind IN ('owner', 'agent', 'service')),
    by_code       text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64),
    at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX affiliate_receipts_month ON sales.affiliate_receipts (account_id, month);
CREATE TRIGGER affiliate_receipts_append_only BEFORE UPDATE OR DELETE ON sales.affiliate_receipts
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON sales.affiliate_receipts TO {APP_ROLES};

CREATE TABLE sales.affiliate_gaps (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL REFERENCES core.companies (id),
    account_id    uuid NOT NULL REFERENCES revenue.accounts (id),
    month         date NOT NULL CHECK (date_trunc('month', month) = month),
    due_usdt      numeric(24, 8) NOT NULL CHECK (due_usdt >= 0),
    received_usdt numeric(24, 8) NOT NULL DEFAULT 0 CHECK (received_usdt >= 0),
    gap_usdt      numeric(24, 8) NOT NULL,
    gap_pct       numeric(10, 4) NOT NULL,
    state         text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'closed')),
    work_ref      text CHECK (work_ref ~ '^W-[0-9]{{4,}}$'),          -- the FIN manager's planner item
    draft_fa      text CHECK (length(draft_fa) <= 2000),
    opened_at     timestamptz NOT NULL DEFAULT now(),
    closed_at     timestamptz,
    updated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, month)
);
CREATE INDEX affiliate_gaps_company ON sales.affiliate_gaps (company_id, state, month DESC);
GRANT SELECT, INSERT ON sales.affiliate_gaps TO {APP_ROLES};
GRANT UPDATE (due_usdt, received_usdt, gap_usdt, gap_pct, state, work_ref, draft_fa, closed_at,
              updated_at) ON sales.affiliate_gaps TO {APP_ROLES};

-- ================================================ §33.6 a decision's impact ==
ALTER TABLE cartable.decisions
    ADD COLUMN impact jsonb CHECK (impact IS NULL OR jsonb_typeof(impact) = 'object'),
    ADD COLUMN impact_tries smallint NOT NULL DEFAULT 0 CHECK (impact_tries >= 0);
GRANT UPDATE (impact, impact_tries) ON cartable.decisions TO {APP_ROLES};
"""
    + "".join(_rls(t) for t in TABLES)
)

DOWNGRADE = r"""
ALTER TABLE cartable.decisions DROP COLUMN impact, DROP COLUMN impact_tries;
DROP SCHEMA sales CASCADE;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
