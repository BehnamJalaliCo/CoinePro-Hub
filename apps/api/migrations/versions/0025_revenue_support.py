"""Prompt 10 (contract §19): revenue radar, funnel and referral rescue, the
support desk with teaching mode, lifecycle messages, NPS, the feedback inbox
and intake from outside. Every table of prompt 10 §2-§11 is made here, so the
sections build on it without a migration of their own.

Five schemas, every table company-scoped (company_id, FORCE RLS, the
once-per-query policy of 0009); no company-less table (intake.sources and the
nonce table carry company_id too):

  revenue   accounts (an exchange's affiliate account = a §18.13 service
            account), days (RevenueDay), invitees (pseudonymous: subject +
            meets_minimum only), pulls, alerts (one per incident)
  support   settings (thresholds set only by a sealed go-live card), channels,
            customers (the ONLY place for a raw handle, user id or UID),
            conversations (SC-000001), messages (masked; body NULL after the
            retention job), kb_articles (KB-0001, versioned rows),
            history_imports, shadow_runs
  growth    rescue_cases (RC-000001), rescue_steps, referral_checks (cache and
            rate), templates (TM-0001, versioned), rules (LR-0001, versioned),
            sends, opt_outs (for good), nps_waves, nps_responses, funnel_days,
            leaks
  feedback  items (FB-000001), signals, keywords
  intake    sources, nonces, events, rejections

Customer identities outside support.customers are `subject` only:
HMAC-SHA256 hex (hq_common.pseudonym), enforced by CHECK. Versioned rows
(kb_articles, templates, rules) share their ref inside one company
(support.ref_stays_in_company). Decision kinds gain message_template,
lifecycle_rule and support_go_live (appended to whatever the constraint holds,
so a migration before this one keeps its kinds). The academy takes the private
shadow suites: eval_suites.ref may be support-shadow-<CODE> and gains a
version; eval_runs.purpose gains 'shadow'.

Revision ID: 0025
Revises: 0024 (re-chained after 9.1's 0024; it does not touch the decision kinds)
"""

from __future__ import annotations

import re

from hq_api.migration_sql import execute_script

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
NEW_KINDS = ("message_template", "lifecycle_rule", "support_go_live")
SCHEMAS = ("revenue", "support", "growth", "feedback", "intake")

# Every table of the migration, in creation order (RLS and grants follow it).
TABLES = (
    "revenue.accounts",
    "revenue.days",
    "revenue.invitees",
    "revenue.pulls",
    "revenue.alerts",
    "support.settings",
    "support.channels",
    "support.customers",
    "support.conversations",
    "support.messages",
    "support.kb_articles",
    "support.history_imports",
    "support.shadow_runs",
    "growth.rescue_cases",
    "growth.rescue_steps",
    "growth.referral_checks",
    "growth.templates",
    "growth.rules",
    "growth.sends",
    "growth.opt_outs",
    "growth.nps_waves",
    "growth.nps_responses",
    "growth.funnel_days",
    "growth.leaks",
    "feedback.items",
    "feedback.signals",
    "feedback.keywords",
    "intake.sources",
    "intake.nonces",
    "intake.events",
    "intake.rejections",
)
# Append-only: rows are never changed (the rest is protected column by column).
APPEND_ONLY = (
    "growth.rescue_steps",
    "growth.referral_checks",
    "growth.opt_outs",
    "intake.rejections",
)
SEQUENCES = (
    "support.conversation_ref_seq",
    "support.kb_ref_seq",
    "growth.rescue_ref_seq",
    "growth.template_ref_seq",
    "growth.rule_ref_seq",
    "feedback.item_ref_seq",
)


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


SUBJECT = "text NOT NULL CHECK (subject ~ '^[0-9a-f]{64}$')"
CHANNEL_KINDS = "'telegram_business', 'telegram_bot', 'chatwoot', 'product_bot', 'mystery'"
ACTOR_KINDS = "'owner', 'agent', 'service', 'rule'"
FEEDBACK_KINDS = "'bug', 'feature', 'confusion', 'complaint', 'praise'"
STAGES = "'visit', 'signup', 'referral_verified', 'min_balance', 'vip_active'"
PRODUCT_EVENTS = (
    "'signup', 'uid_submitted', 'referral_verified', 'referral_failed', 'vip_activated', "
    "'support_message'"
)
TEMPLATE_REF = r"'^TM-[0-9]{4,6}@[0-9]+$'"

UPGRADE = r"""
CREATE SCHEMA revenue;
CREATE SCHEMA support;
CREATE SCHEMA growth;
CREATE SCHEMA feedback;
CREATE SCHEMA intake;
GRANT USAGE ON SCHEMA revenue, support, growth, feedback, intake TO @APP@;

-- A versioned row (an article, a template, a rule) keeps its ref inside one
-- company: a seal bound to "ref@version" can never be replayed elsewhere.
-- SECURITY DEFINER: the caller's RLS would hide the other company's row.
CREATE FUNCTION support.ref_stays_in_company() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE other uuid;
    BEGIN
        EXECUTE format('SELECT company_id FROM %I.%I WHERE ref = $1 AND company_id <> $2 LIMIT 1',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME)
            INTO other USING NEW.ref, NEW.company_id;
        IF other IS NOT NULL THEN
            RAISE EXCEPTION '%.%: % belongs to another company', TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.ref
                USING ERRCODE = 'HQV01';
        END IF;
        RETURN NEW;
    END $$;

-- The text an article is found by (question and variants, Persian-normalised).
CREATE FUNCTION support.kb_search_text(q text, v text[]) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$ SELECT core.fa_normalize(coalesce(q, '') || ' ' || coalesce(array_to_string(v, ' '), '')) $$;

-- The thresholds of a company have no edit route (contract §19.9): they change
-- only together with the sealed support_go_live card that carries them.
CREATE FUNCTION support.thresholds_from_a_card() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF (NEW.verbatim_threshold IS DISTINCT FROM OLD.verbatim_threshold
            OR NEW.grounded_threshold IS DISTINCT FROM OLD.grounded_threshold)
           AND (NEW.thresholds_decision_id IS NULL
                OR NEW.thresholds_decision_id IS NOT DISTINCT FROM OLD.thresholds_decision_id) THEN
            RAISE EXCEPTION 'support.settings: thresholds change only with a new go-live card'
                USING ERRCODE = 'HQV01';
        END IF;
        RETURN NEW;
    END $$;
REVOKE ALL ON FUNCTION support.ref_stays_in_company(), support.kb_search_text(text, text[]),
    support.thresholds_from_a_card() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION support.kb_search_text(text, text[]) TO @APP@;

-- ================================================================ revenue ==
-- An exchange's affiliate account: a mapping onto a §18.13 service account
-- (the key and secret stay in OpenBao, read by egress only).
CREATE TABLE revenue.accounts (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    exchange         text NOT NULL CHECK (exchange ~ '^[a-z][a-z0-9_-]{1,30}$'),
    adapter          text NOT NULL CHECK (adapter ~ '^[a-z][a-z0-9-]{1,40}$'),
    service_account  text NOT NULL CHECK (service_account ~ '^[a-z0-9][a-z0-9_.-]{1,40}$'),
    title_fa         text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
    status           text NOT NULL DEFAULT 'not_configured'
                          CHECK (status IN ('not_configured', 'ok', 'error')),
    last_pull_at     timestamptz,
    last_error       text CHECK (length(last_error) <= 300),
    failures_in_row  int NOT NULL DEFAULT 0 CHECK (failures_in_row >= 0),
    backfilled_at    timestamptz,                    -- the first 90-day fill is done
    body_sha256      text CHECK (body_sha256 ~ '^[0-9a-f]{64}$'),  -- the sealed POST body
    created_by_kind  text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
    created_by_code  text NOT NULL CHECK (length(created_by_code) <= 64),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    version          int NOT NULL DEFAULT 1,
    UNIQUE (company_id, exchange)
);
CREATE TRIGGER revenue_accounts_immutable BEFORE UPDATE ON revenue.accounts
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'exchange', 'created_by_kind',
                                                      'created_by_code', 'created_at');
CREATE TRIGGER revenue_accounts_version BEFORE UPDATE ON revenue.accounts
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- One settlement day of one account (RevenueDay; lbank: T+1 at UTC+8).
CREATE TABLE revenue.days (
    company_id            uuid NOT NULL REFERENCES core.companies (id),
    account_id            uuid NOT NULL REFERENCES revenue.accounts (id),
    day                   date NOT NULL,
    commission_usdt       numeric(24, 8) NOT NULL DEFAULT 0,
    by_coin               jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(by_coin) = 'array'),
    fees_usdt             numeric(24, 8),
    volume_usdt           numeric(24, 8),
    new_invitees          int NOT NULL DEFAULT 0 CHECK (new_invitees >= 0),
    min_balance_invitees  int CHECK (min_balance_invitees >= 0),  -- reached the minimum that day
    active_traders        int CHECK (active_traders >= 0),
    deposits_usdt         numeric(24, 8),
    complete              boolean NOT NULL DEFAULT false,
    gaps                  jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(gaps) = 'array'),  -- [{endpoint, page, error}]
    source                jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(source) = 'object'),  -- {adapter, endpoints}
    attempts              int NOT NULL DEFAULT 1 CHECK (attempts >= 1),
    pulled_at             timestamptz NOT NULL DEFAULT now(),
    created_at            timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, day)
);
CREATE INDEX revenue_days_company ON revenue.days (company_id, day DESC);
CREATE TRIGGER revenue_days_immutable BEFORE UPDATE ON revenue.days
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('company_id', 'account_id', 'day', 'created_at');

-- The account's invitees, pseudonymous: whether each meets the minimum is
-- kept, the balance itself is read and dropped (prompt 10 §2.3).
CREATE TABLE revenue.invitees (
    company_id           uuid NOT NULL REFERENCES core.companies (id),
    account_id           uuid NOT NULL REFERENCES revenue.accounts (id),
    subject              @SUBJECT@,
    invited_on           date,
    meets_minimum        boolean,
    meets_minimum_since  date,
    first_seen_at        timestamptz NOT NULL DEFAULT now(),
    last_checked_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, subject)
);
CREATE INDEX revenue_invitees_invited ON revenue.invitees (company_id, invited_on);
CREATE INDEX revenue_invitees_minimum ON revenue.invitees (company_id, meets_minimum_since)
    WHERE meets_minimum_since IS NOT NULL;
CREATE TRIGGER revenue_invitees_immutable BEFORE UPDATE ON revenue.invitees
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('company_id', 'account_id', 'subject', 'first_seen_at');

CREATE TABLE revenue.pulls (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         uuid NOT NULL REFERENCES core.companies (id),
    account_id         uuid NOT NULL REFERENCES revenue.accounts (id),
    kind               text NOT NULL CHECK (kind IN ('scheduled', 'retry', 'manual', 'backfill')),
    from_day           date NOT NULL,
    to_day             date NOT NULL,
    state              text NOT NULL DEFAULT 'queued'
                            CHECK (state IN ('queued', 'running', 'ok', 'incomplete', 'failed', 'skipped')),
    skipped_reason     text CHECK (length(skipped_reason) <= 60),   -- e.g. holding_locked
    days_complete      int NOT NULL DEFAULT 0 CHECK (days_complete >= 0),
    days_incomplete    int NOT NULL DEFAULT 0 CHECK (days_incomplete >= 0),
    requests           int NOT NULL DEFAULT 0 CHECK (requests >= 0),
    error_code         text CHECK (length(error_code) <= 60),
    error              text CHECK (length(error) <= 300),
    workflow_id        text CHECK (length(workflow_id) <= 200),
    requested_by_kind  text NOT NULL CHECK (requested_by_kind IN ('owner', 'service')),
    requested_by_code  text NOT NULL CHECK (length(requested_by_code) <= 64),
    created_at         timestamptz NOT NULL DEFAULT now(),
    started_at         timestamptz,
    finished_at        timestamptz,
    CHECK (to_day >= from_day AND to_day - from_day <= 400)
);
CREATE INDEX revenue_pulls_account ON revenue.pulls (account_id, created_at DESC);
CREATE TRIGGER revenue_pulls_immutable BEFORE UPDATE ON revenue.pulls
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'account_id', 'kind', 'from_day',
                                                      'to_day', 'requested_by_kind', 'requested_by_code',
                                                      'created_at');

-- One alert per incident (incident_key, e.g. "drop:<account>:<day>").
CREATE TABLE revenue.alerts (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    account_id       uuid REFERENCES revenue.accounts (id),
    kind             text NOT NULL CHECK (kind IN ('drop', 'pull_failed', 'incomplete')),
    day              date,
    incident_key     text NOT NULL CHECK (length(incident_key) BETWEEN 1 AND 200),
    note_fa          text NOT NULL CHECK (length(note_fa) BETWEEN 1 AND 500),
    data             jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(data) = 'object'),
    notification_id  uuid,
    work_id          uuid REFERENCES work.work (id),            -- the platform SRE's task
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, incident_key)
);
CREATE TRIGGER revenue_alerts_immutable BEFORE UPDATE ON revenue.alerts
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'account_id', 'kind', 'day',
                                                      'incident_key', 'note_fa', 'data', 'created_at');

-- ================================================================ support ==
CREATE TABLE support.settings (
    company_id              uuid PRIMARY KEY REFERENCES core.companies (id),
    verbatim_threshold      numeric(5, 4) CHECK (verbatim_threshold BETWEEN 0 AND 1),  -- NULL: no verbatim answers yet
    verbatim_margin         numeric(5, 4) NOT NULL DEFAULT 0.1500 CHECK (verbatim_margin BETWEEN 0 AND 1),
    grounded_threshold      numeric(5, 4) CHECK (grounded_threshold BETWEEN 0 AND 1),
    thresholds_decision_id  uuid REFERENCES cartable.decisions (id),
    outbound_daily_cap      int CHECK (outbound_daily_cap > 0),   -- NULL: SUPPORT_DAILY_OUTBOUND_CAP
    draft_daily_tokens      int CHECK (draft_daily_tokens > 0),   -- NULL: SUPPORT_DRAFT_DAILY_TOKENS
    feedback_threshold      int NOT NULL DEFAULT 5 CHECK (feedback_threshold >= 1),
    feedback_window_days    int NOT NULL DEFAULT 7 CHECK (feedback_window_days BETWEEN 1 AND 90),
    kb_expiry_days          int NOT NULL DEFAULT 180 CHECK (kb_expiry_days BETWEEN 1 AND 3650),
    version                 int NOT NULL DEFAULT 1,
    updated_at              timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER support_settings_thresholds BEFORE UPDATE ON support.settings
    FOR EACH ROW EXECUTE FUNCTION support.thresholds_from_a_card();
CREATE TRIGGER support_settings_version BEFORE UPDATE ON support.settings
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- A channel of a company (SupportChannel). Live only through a sealed
-- support_go_live card; "already went live" = live_since IS NOT NULL.
CREATE TABLE support.channels (
    company_id           uuid NOT NULL REFERENCES core.companies (id),
    kind                 text NOT NULL CHECK (kind IN (@CHANNELS@)),
    state                text NOT NULL DEFAULT 'not_configured'
                              CHECK (state IN ('not_configured', 'shadow', 'live', 'paused')),
    auto_send            text NOT NULL DEFAULT 'kb_verbatim'
                              CHECK (auto_send IN ('kb_verbatim', 'kb_grounded', 'off')),
    live_since           timestamptz,
    paused_at            timestamptz,
    paused_reason        text CHECK (length(paused_reason) <= 300),
    go_live_decision_id  uuid REFERENCES cartable.decisions (id),
    premium_connected    boolean NOT NULL DEFAULT false,      -- telegram_business: Business -> Chatbots
    config               jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(config) = 'object'),  -- never a secret
    version              int NOT NULL DEFAULT 1,
    updated_at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, kind),
    CHECK (state <> 'live' OR (live_since IS NOT NULL AND (go_live_decision_id IS NOT NULL OR kind = 'mystery')))
);
CREATE TRIGGER support_channels_immutable BEFORE UPDATE ON support.channels
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('company_id', 'kind');
CREATE TRIGGER support_channels_version BEFORE UPDATE ON support.channels
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- The only table with a customer's raw handle, user id or exchange UIDs.
CREATE TABLE support.customers (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    channel        text NOT NULL CHECK (channel IN (@CHANNELS@)),
    external_id    text NOT NULL CHECK (length(external_id) BETWEEN 1 AND 128),
    subject        @SUBJECT@,
    handle         text CHECK (length(handle) <= 128),
    display_name   text CHECK (length(display_name) <= 200),
    lang           text NOT NULL DEFAULT 'fa' CHECK (lang ~ '^[a-z]{2,3}$'),
    uids           jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(uids) = 'array'),  -- [{exchange, uid}]
    started_at     timestamptz,     -- wrote first (a Telegram bot writes only to those who did)
    first_seen_at  timestamptz NOT NULL DEFAULT now(),
    last_seen_at   timestamptz NOT NULL DEFAULT now(),
    version        int NOT NULL DEFAULT 1,
    updated_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, channel, external_id),
    UNIQUE (company_id, subject)
);
CREATE TRIGGER support_customers_immutable BEFORE UPDATE ON support.customers
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'channel', 'external_id', 'subject',
                                                      'first_seen_at');
CREATE TRIGGER support_customers_version BEFORE UPDATE ON support.customers
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

CREATE SEQUENCE support.conversation_ref_seq;
CREATE TABLE support.conversations (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref                text NOT NULL UNIQUE
                            DEFAULT 'SC-' || lpad(nextval('support.conversation_ref_seq')::text, 6, '0'),
    company_id         uuid NOT NULL REFERENCES core.companies (id),
    channel            text NOT NULL CHECK (channel IN (@CHANNELS@)),
    customer_id        uuid NOT NULL REFERENCES support.customers (id),
    state              text NOT NULL DEFAULT 'open'
                            CHECK (state IN ('open', 'waiting_owner', 'answered', 'closed')),
    handoff_reason     text CHECK (handoff_reason IN ('no_kb', 'low_confidence', 'blocked',
                                                      'asked_for_human', 'complaint', 'security')),
    handoff_at         timestamptz,
    handoff_note       text CHECK (length(handoff_note) <= 1000),
    owner_notified_at  timestamptz,           -- its line in the owner's digest (batched every 30 min)
    tags               text[] NOT NULL DEFAULT '{}' CHECK (cardinality(tags) <= 30),
    rescue_case_id     uuid,                  -- FK below (growth.rescue_cases)
    csat               smallint CHECK (csat BETWEEN 1 AND 5),
    csat_asked_at      timestamptz,
    mystery            boolean NOT NULL DEFAULT false,   -- PR-043: never reaches a channel, never counted
    safety_sent_at     timestamptz,           -- the safety line went out (first answer or a masked secret)
    paused_at          timestamptz,           -- the loop guard stopped automatic answers
    paused_reason      text CHECK (length(paused_reason) <= 200),
    external           jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(external) = 'object'),  -- chat id, business_connection_id
    opened_at          timestamptz NOT NULL DEFAULT now(),
    last_message_at    timestamptz NOT NULL DEFAULT now(),
    closed_at          timestamptz,
    closed_by_kind     text CHECK (closed_by_kind IN (@ACTORS@)),
    closed_by_code     text CHECK (length(closed_by_code) <= 64),
    version            int NOT NULL DEFAULT 1,
    updated_at         timestamptz NOT NULL DEFAULT now(),
    CHECK (state <> 'waiting_owner' OR handoff_reason IS NOT NULL),
    CHECK ((state = 'closed') = (closed_at IS NOT NULL))
);
CREATE UNIQUE INDEX support_conversations_one_open ON support.conversations (customer_id)
    WHERE state <> 'closed';
CREATE INDEX support_conversations_state ON support.conversations (company_id, state, last_message_at DESC);
CREATE INDEX support_conversations_recent ON support.conversations (company_id, last_message_at DESC);
CREATE TRIGGER support_conversations_immutable BEFORE UPDATE ON support.conversations
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'channel', 'customer_id',
                                                      'mystery', 'opened_at');
CREATE TRIGGER support_conversations_version BEFORE UPDATE ON support.conversations
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- SupportMessage. `body` is masked (hq_common.customer_mask) before it is
-- written, and NULL once the retention job has purged it (the row, its time,
-- status and refs stay).
CREATE TABLE support.messages (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    conversation_id  uuid NOT NULL REFERENCES support.conversations (id),
    at               timestamptz NOT NULL DEFAULT now(),
    direction        text NOT NULL CHECK (direction IN ('in', 'out')),
    author           text NOT NULL CHECK (author IN ('customer', 'agent', 'owner', 'rule')),
    author_code      text CHECK (length(author_code) <= 64),     -- employee code, 'owner' or a rule ref
    body             text CHECK (length(body) <= 8000),
    body_purged_at   timestamptz,
    masked           text[] NOT NULL DEFAULT '{}'
                          CHECK (masked <@ ARRAY['seed_phrase', 'private_key', 'card', 'secret', 'personal']),
    status           text NOT NULL CHECK (status IN ('draft', 'queued', 'sent', 'blocked', 'failed')),
    failure          text CHECK (failure IN ('no_channel', 'send_error', 'send_limit', 'channel_not_live',
                                             'opted_out')),
    verbatim         boolean NOT NULL DEFAULT false,  -- one approved faq, word for word, no model
    kb_refs          text[] NOT NULL DEFAULT '{}' CHECK (cardinality(kb_refs) <= 20),  -- "KB-0042@3"
    confidence       numeric(4, 3) CHECK (confidence BETWEEN 0 AND 1),
    checks           jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(checks) = 'object'),  -- {guard, grounded}
    blocked_reasons  text[] NOT NULL DEFAULT '{}' CHECK (cardinality(blocked_reasons) <= 20),
    template         text CHECK (template ~ @TEMPLATE_REF@),   -- a rule-sent message's template
    run_id           uuid,                                     -- the support agent's run that drafted it
    tokens           int CHECK (tokens >= 0),
    external_id      text CHECK (length(external_id) <= 128),  -- the channel's message id (webhook retries)
    sent_at          timestamptz,
    search           tsvector GENERATED ALWAYS AS (to_tsvector('simple', core.fa_normalize(coalesce(body, '')))) STORED,
    CHECK (body IS NOT NULL OR body_purged_at IS NOT NULL)
);
CREATE UNIQUE INDEX support_messages_external ON support.messages (conversation_id, direction, external_id)
    WHERE external_id IS NOT NULL;
CREATE INDEX support_messages_conversation ON support.messages (conversation_id, at);
CREATE INDEX support_messages_outbound ON support.messages (company_id, at) WHERE direction = 'out';
CREATE INDEX support_messages_retention ON support.messages (at) WHERE body IS NOT NULL;
CREATE INDEX support_messages_search ON support.messages USING gin (search);
CREATE TRIGGER support_messages_immutable BEFORE UPDATE ON support.messages
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'conversation_id', 'at', 'direction',
                                                      'author', 'author_code');

-- KbArticle: one row per version; the content of a version never changes.
CREATE SEQUENCE support.kb_ref_seq;
CREATE TABLE support.kb_articles (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref                  text NOT NULL DEFAULT 'KB-' || lpad(nextval('support.kb_ref_seq')::text, 4, '0')
                              CHECK (ref ~ '^KB-[0-9]{4,6}$'),
    company_id           uuid NOT NULL REFERENCES core.companies (id),
    version              int NOT NULL DEFAULT 1 CHECK (version >= 1),
    kind                 text NOT NULL CHECK (kind IN ('faq', 'policy', 'procedure', 'referral',
                                                       'official_link', 'safety')),
    key                  text CHECK (key ~ '^[a-z][a-z0-9_.]{1,60}$'),     -- policy keys: vip.min_balance
    question_fa          text NOT NULL CHECK (length(question_fa) BETWEEN 1 AND 1000),
    variants             text[] NOT NULL DEFAULT '{}' CHECK (cardinality(variants) <= 50),
    answer_md            text NOT NULL CHECK (length(answer_md) BETWEEN 1 AND 8000),
    variables            jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(variables) = 'array'),
    links                jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(links) = 'array'),
    codes                jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(codes) = 'array'),
    status               text NOT NULL DEFAULT 'proposed'
                              CHECK (status IN ('proposed', 'approved', 'expired', 'retired')),
    source               jsonb NOT NULL DEFAULT '{"kind": "owner"}'
                              CHECK (source ->> 'kind' IN ('owner_answer', 'owner', 'doc', 'agent')),
    sha256               text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    approved_at          timestamptz,
    approved_step_up_id  uuid,
    expires_at           timestamptz NOT NULL DEFAULT now() + interval '180 days',
    reminded_at          timestamptz,           -- the support lead's reminder 14 days before
    retired_at           timestamptz,
    proposed_by_kind     text NOT NULL CHECK (proposed_by_kind IN ('owner', 'agent', 'service')),
    proposed_by_code     text NOT NULL CHECK (length(proposed_by_code) <= 64),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    search               tsvector GENERATED ALWAYS AS
                              (to_tsvector('simple', support.kb_search_text(question_fa, variants))) STORED,
    UNIQUE (ref, version),
    CHECK (status <> 'approved' OR approved_at IS NOT NULL),
    CHECK (kind <> 'policy' OR key IS NOT NULL)
);
CREATE UNIQUE INDEX support_kb_one_approved ON support.kb_articles (ref) WHERE status = 'approved';
CREATE UNIQUE INDEX support_kb_policy_key ON support.kb_articles (company_id, key)
    WHERE status = 'approved' AND key IS NOT NULL;
CREATE INDEX support_kb_list ON support.kb_articles (company_id, kind, status);
CREATE INDEX support_kb_search ON support.kb_articles USING gin (search);
CREATE TRIGGER support_kb_articles_ref BEFORE INSERT ON support.kb_articles
    FOR EACH ROW EXECUTE FUNCTION support.ref_stays_in_company();
CREATE TRIGGER support_kb_articles_immutable BEFORE UPDATE ON support.kb_articles
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'version', 'kind', 'key',
                                                      'question_fa', 'variants', 'answer_md', 'variables',
                                                      'links', 'codes', 'source', 'sha256',
                                                      'proposed_by_kind', 'proposed_by_code', 'created_at');

-- POST /support/history: an owner's chat export -> the private shadow suite.
CREATE TABLE support.history_imports (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         uuid NOT NULL REFERENCES core.companies (id),
    file_id            uuid NOT NULL REFERENCES files.files (id),
    format             text CHECK (format IN ('telegram_json', 'csv')),
    state              text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'parsing', 'done', 'failed')),
    pairs_found        int CHECK (pairs_found >= 0),
    cases_kept         int CHECK (cases_kept BETWEEN 0 AND 100),
    topics             jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(topics) = 'object'),
    suite_ref          text CHECK (length(suite_ref) <= 60),
    suite_version      int CHECK (suite_version >= 1),
    error              text CHECK (length(error) <= 300),
    requested_by_code  text NOT NULL DEFAULT 'owner' CHECK (length(requested_by_code) <= 64),
    created_at         timestamptz NOT NULL DEFAULT now(),
    finished_at        timestamptz
);
CREATE TRIGGER support_history_imports_immutable BEFORE UPDATE ON support.history_imports
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'file_id', 'requested_by_code',
                                                      'created_at');

-- ShadowReport: one academy eval run of the support charter on the suite.
CREATE TABLE support.shadow_runs (
    id                           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id                   uuid NOT NULL REFERENCES core.companies (id),
    suite_ref                    text NOT NULL CHECK (length(suite_ref) <= 60),
    suite_version                int NOT NULL CHECK (suite_version >= 1),
    eval_run_id                  uuid REFERENCES academy.eval_runs (id),
    state                        text NOT NULL DEFAULT 'queued'
                                      CHECK (state IN ('queued', 'running', 'done', 'failed', 'skipped')),
    skipped_reason               text CHECK (length(skipped_reason) <= 60),
    total                        int CHECK (total >= 0),
    correct                      int CHECK (correct >= 0),
    partial                      int CHECK (partial >= 0),
    wrong                        int CHECK (wrong >= 0),
    safety_failures              int CHECK (safety_failures >= 0),
    wrong_codes                  int CHECK (wrong_codes >= 0),
    pass                         boolean,
    threshold                    numeric(4, 3) NOT NULL DEFAULT 0.9,
    disagreements                jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(disagreements) = 'array'),
    proposed_auto_send           text CHECK (proposed_auto_send IN ('kb_verbatim', 'kb_grounded', 'off')),
    proposed_verbatim_threshold  numeric(5, 4) CHECK (proposed_verbatim_threshold BETWEEN 0 AND 1),
    proposed_grounded_threshold  numeric(5, 4) CHECK (proposed_grounded_threshold BETWEEN 0 AND 1),
    decision_id                  uuid REFERENCES cartable.decisions (id),   -- the support_go_live card
    tokens                       bigint NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    error                        text CHECK (length(error) <= 300),
    requested_by_kind            text NOT NULL CHECK (requested_by_kind IN ('owner', 'agent', 'service')),
    requested_by_code            text NOT NULL CHECK (length(requested_by_code) <= 64),
    at                           timestamptz NOT NULL DEFAULT now(),
    finished_at                  timestamptz
);
CREATE INDEX support_shadow_runs_latest ON support.shadow_runs (company_id, at DESC);
CREATE TRIGGER support_shadow_runs_immutable BEFORE UPDATE ON support.shadow_runs
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'suite_ref', 'suite_version',
                                                      'requested_by_kind', 'requested_by_code', 'at');

-- ================================================================= growth ==
CREATE SEQUENCE growth.rescue_ref_seq;
CREATE TABLE growth.rescue_cases (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref                text NOT NULL UNIQUE
                            DEFAULT 'RC-' || lpad(nextval('growth.rescue_ref_seq')::text, 6, '0'),
    company_id         uuid NOT NULL REFERENCES core.companies (id),
    source             text NOT NULL CHECK (source IN ('support', 'product')),
    conversation_id    uuid REFERENCES support.conversations (id),
    exchange           text NOT NULL CHECK (exchange ~ '^[a-z][a-z0-9_-]{1,30}$'),
    subject            @SUBJECT@,
    state              text NOT NULL DEFAULT 'open'
                            CHECK (state IN ('open', 'contacted', 'rescued', 'lost', 'opted_out')),
    follow_ups         int NOT NULL DEFAULT 0 CHECK (follow_ups >= 0),
    last_contact_at    timestamptz,
    next_follow_up_at  timestamptz,
    close_reason       text CHECK (length(close_reason) <= 60),
    mystery            boolean NOT NULL DEFAULT false,
    opened_at          timestamptz NOT NULL DEFAULT now(),
    rescued_at         timestamptz,
    closed_at          timestamptz,
    version            int NOT NULL DEFAULT 1,
    updated_at         timestamptz NOT NULL DEFAULT now(),
    CHECK ((state IN ('rescued', 'lost', 'opted_out')) = (closed_at IS NOT NULL)),
    CHECK ((state = 'rescued') = (rescued_at IS NOT NULL))
);
CREATE UNIQUE INDEX growth_rescue_one_open ON growth.rescue_cases (company_id, exchange, subject)
    WHERE state IN ('open', 'contacted');
CREATE INDEX growth_rescue_list ON growth.rescue_cases (company_id, state, opened_at DESC);
CREATE INDEX growth_rescue_due ON growth.rescue_cases (next_follow_up_at)
    WHERE state IN ('open', 'contacted');
CREATE TRIGGER growth_rescue_cases_immutable BEFORE UPDATE ON growth.rescue_cases
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'source', 'conversation_id',
                                                      'exchange', 'subject', 'mystery', 'opened_at');
CREATE TRIGGER growth_rescue_cases_version BEFORE UPDATE ON growth.rescue_cases
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
ALTER TABLE support.conversations ADD CONSTRAINT conversations_rescue_case_fkey
    FOREIGN KEY (rescue_case_id) REFERENCES growth.rescue_cases (id);

CREATE TABLE growth.rescue_steps (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id     uuid NOT NULL REFERENCES growth.rescue_cases (id),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    at          timestamptz NOT NULL DEFAULT now(),
    kind        text NOT NULL CHECK (kind IN ('check', 'message', 'follow_up', 'note')),
    template    text CHECK (template ~ @TEMPLATE_REF@),
    result_fa   text NOT NULL CHECK (length(result_fa) BETWEEN 1 AND 1000),
    by_kind     text NOT NULL CHECK (by_kind IN (@ACTORS@)),
    by_code     text NOT NULL CHECK (length(by_code) <= 64)
);
CREATE INDEX growth_rescue_steps_case ON growth.rescue_steps (case_id, at);

-- referral.check: the 10-minute cache and the 30-an-hour cap (cached rows do
-- not count). Never a balance, a name or anything else of the account.
CREATE TABLE growth.referral_checks (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    exchange         text NOT NULL CHECK (exchange ~ '^[a-z][a-z0-9_-]{1,30}$'),
    subject          @SUBJECT@,
    ok               boolean NOT NULL,          -- the connector answered
    invitee          boolean,
    meets_minimum    boolean,
    cached           boolean NOT NULL DEFAULT false,
    error_code       text CHECK (length(error_code) <= 60),
    conversation_id  uuid REFERENCES support.conversations (id),
    rescue_case_id   uuid REFERENCES growth.rescue_cases (id),
    mystery          boolean NOT NULL DEFAULT false,
    by_kind          text NOT NULL CHECK (by_kind IN (@ACTORS@)),
    by_code          text NOT NULL CHECK (length(by_code) <= 64),
    at               timestamptz NOT NULL DEFAULT now(),
    CHECK (ok OR (invitee IS NULL AND meets_minimum IS NULL))
);
CREATE INDEX growth_referral_checks_cache ON growth.referral_checks (company_id, exchange, subject, at DESC);
CREATE INDEX growth_referral_checks_rate ON growth.referral_checks (company_id, at) WHERE NOT cached;

-- Template: one row per version; the body of a version never changes.
CREATE SEQUENCE growth.template_ref_seq;
CREATE TABLE growth.templates (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref               text NOT NULL DEFAULT 'TM-' || lpad(nextval('growth.template_ref_seq')::text, 4, '0')
                           CHECK (ref ~ '^TM-[0-9]{4,6}$'),
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    version           int NOT NULL DEFAULT 1 CHECK (version >= 1),
    purpose           text NOT NULL CHECK (purpose IN ('welcome', 'reactivation', 'rescue', 'nps',
                                                       'holding_reply', 'safety', 'csat')),
    body_fa           text NOT NULL CHECK (length(body_fa) BETWEEN 1 AND 4000),
    variables         text[] NOT NULL DEFAULT '{}' CHECK (cardinality(variables) <= 20),
    status            text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'sealed', 'retired')),
    sha256            text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    sealed_at         timestamptz,
    seal_step_up_id   uuid,
    decision_id       uuid REFERENCES cartable.decisions (id),
    proposed_by_kind  text NOT NULL CHECK (proposed_by_kind IN ('owner', 'agent', 'service')),
    proposed_by_code  text NOT NULL CHECK (length(proposed_by_code) <= 64),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (ref, version),
    CHECK (status <> 'sealed' OR sealed_at IS NOT NULL)
);
CREATE INDEX growth_templates_list ON growth.templates (company_id, purpose, status);
CREATE TRIGGER growth_templates_ref BEFORE INSERT ON growth.templates
    FOR EACH ROW EXECUTE FUNCTION support.ref_stays_in_company();
CREATE TRIGGER growth_templates_immutable BEFORE UPDATE ON growth.templates
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'version', 'purpose',
                                                      'body_fa', 'variables', 'sha256', 'proposed_by_kind',
                                                      'proposed_by_code', 'created_at');

-- LifecycleRule: one row per version; active only while its template version
-- is sealed (sealing the rule is the owner's A3 approval in advance).
CREATE SEQUENCE growth.rule_ref_seq;
CREATE TABLE growth.rules (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref               text NOT NULL DEFAULT 'LR-' || lpad(nextval('growth.rule_ref_seq')::text, 4, '0')
                           CHECK (ref ~ '^LR-[0-9]{4,6}$'),
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    version           int NOT NULL DEFAULT 1 CHECK (version >= 1),
    kind              text NOT NULL CHECK (kind IN ('welcome', 'reactivation', 'rescue', 'nps', 'csat')),
    trigger           jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(trigger) = 'object'),
    template_ref      text NOT NULL CHECK (template_ref ~ '^TM-[0-9]{4,6}$'),
    template_version  int NOT NULL CHECK (template_version >= 1),
    channel           text NOT NULL CHECK (channel IN (@CHANNELS@)),
    limits            jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(limits) = 'object'),
    status            text NOT NULL DEFAULT 'proposed'
                           CHECK (status IN ('proposed', 'active', 'paused', 'retired')),
    paused_reason     text CHECK (length(paused_reason) <= 200),
    sealed_at         timestamptz,
    seal_step_up_id   uuid,
    decision_id       uuid REFERENCES cartable.decisions (id),
    last_run_at       timestamptz,
    proposed_by_kind  text NOT NULL CHECK (proposed_by_kind IN ('owner', 'agent', 'service')),
    proposed_by_code  text NOT NULL CHECK (length(proposed_by_code) <= 64),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (ref, version),
    CHECK (status <> 'active' OR sealed_at IS NOT NULL)
);
CREATE UNIQUE INDEX growth_rules_one_active ON growth.rules (ref) WHERE status = 'active';
CREATE INDEX growth_rules_list ON growth.rules (company_id, kind, status);
CREATE TRIGGER growth_rules_ref BEFORE INSERT ON growth.rules
    FOR EACH ROW EXECUTE FUNCTION support.ref_stays_in_company();
CREATE TRIGGER growth_rules_immutable BEFORE UPDATE ON growth.rules
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'version', 'kind', 'trigger',
                                                      'template_ref', 'template_version', 'channel', 'limits',
                                                      'proposed_by_kind', 'proposed_by_code', 'created_at');

-- What a rule sent, or why it did not (caps, quiet hours, opt-out, Telegram's
-- own rules: no_channel). dedupe_key: one send per occurrence.
CREATE TABLE growth.sends (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    rule_id          uuid REFERENCES growth.rules (id),
    template         text NOT NULL CHECK (template ~ @TEMPLATE_REF@),
    subject          @SUBJECT@,
    channel          text NOT NULL CHECK (channel IN (@CHANNELS@)),
    dedupe_key       text NOT NULL CHECK (length(dedupe_key) BETWEEN 1 AND 200),
    status           text NOT NULL DEFAULT 'queued'
                          CHECK (status IN ('queued', 'sent', 'blocked', 'skipped', 'no_channel', 'failed')),
    reason           text CHECK (length(reason) <= 60),
    blocked_reasons  text[] NOT NULL DEFAULT '{}' CHECK (cardinality(blocked_reasons) <= 20),
    message_id       uuid REFERENCES support.messages (id),
    rescue_case_id   uuid REFERENCES growth.rescue_cases (id),
    nps_wave_id      uuid,                       -- FK below (growth.nps_waves)
    follow_up        int CHECK (follow_up >= 0),
    at               timestamptz NOT NULL DEFAULT now(),
    sent_at          timestamptz,
    UNIQUE (company_id, dedupe_key)
);
CREATE INDEX growth_sends_rule ON growth.sends (company_id, rule_id, at DESC);
CREATE INDEX growth_sends_subject ON growth.sends (company_id, subject, at DESC);
CREATE TRIGGER growth_sends_immutable BEFORE UPDATE ON growth.sends
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'rule_id', 'template', 'subject',
                                                      'channel', 'dedupe_key', 'at');

-- «لغو», "stop", «نمیخواهم»: every rule of that company stops for that
-- customer for good (append-only).
CREATE TABLE growth.opt_outs (
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    subject     @SUBJECT@,
    at          timestamptz NOT NULL DEFAULT now(),
    source      text NOT NULL CHECK (source IN ('message', 'product', 'owner')),
    message_id  uuid REFERENCES support.messages (id),
    PRIMARY KEY (company_id, subject)
);

CREATE TABLE growth.nps_waves (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref                   text NOT NULL UNIQUE CHECK (ref ~ '^NP-[0-9]{4}Q[1-4]-[A-Z][A-Z0-9]{1,9}$'),
    company_id            uuid NOT NULL REFERENCES core.companies (id),
    quarter               text NOT NULL CHECK (quarter ~ '^[0-9]{4}Q[1-4]$'),
    rule_id               uuid REFERENCES growth.rules (id),
    state                 text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'closed')),
    sample                int NOT NULL DEFAULT 0 CHECK (sample >= 0),
    sent                  int NOT NULL DEFAULT 0 CHECK (sent >= 0),
    responses             int NOT NULL DEFAULT 0 CHECK (responses >= 0),
    promoters             int NOT NULL DEFAULT 0 CHECK (promoters >= 0),
    passives              int NOT NULL DEFAULT 0 CHECK (passives >= 0),
    detractors            int NOT NULL DEFAULT 0 CHECK (detractors >= 0),
    score                 int CHECK (score BETWEEN -100 AND 100),
    comments_to_feedback  int NOT NULL DEFAULT 0 CHECK (comments_to_feedback >= 0),
    opens_at              timestamptz NOT NULL,
    closes_at             timestamptz NOT NULL,
    closed_at             timestamptz,
    version               int NOT NULL DEFAULT 1,
    updated_at            timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, quarter),
    CHECK (closes_at > opens_at)
);
CREATE TRIGGER growth_nps_waves_immutable BEFORE UPDATE ON growth.nps_waves
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'quarter', 'opens_at');
CREATE TRIGGER growth_nps_waves_version BEFORE UPDATE ON growth.nps_waves
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
ALTER TABLE growth.sends ADD CONSTRAINT sends_nps_wave_fkey
    FOREIGN KEY (nps_wave_id) REFERENCES growth.nps_waves (id);

CREATE TABLE growth.nps_responses (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    wave_id            uuid NOT NULL REFERENCES growth.nps_waves (id),
    company_id         uuid NOT NULL REFERENCES core.companies (id),
    subject            @SUBJECT@,
    score              smallint NOT NULL CHECK (score BETWEEN 0 AND 10),
    comment            text CHECK (length(comment) <= 2000),     -- masked; NULL after the retention job
    comment_purged_at  timestamptz,
    message_id         uuid REFERENCES support.messages (id),
    at                 timestamptz NOT NULL DEFAULT now(),
    UNIQUE (wave_id, subject)
);
CREATE TRIGGER growth_nps_responses_immutable BEFORE UPDATE ON growth.nps_responses
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'wave_id', 'company_id', 'subject', 'score',
                                                      'message_id', 'at');

-- One count per company, day and stage (the funnel and its 4-week medians).
CREATE TABLE growth.funnel_days (
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    day         date NOT NULL,
    stage       text NOT NULL CHECK (stage IN (@STAGES@)),
    count       int NOT NULL CHECK (count >= 0),
    source      text NOT NULL CHECK (source IN ('affiliate', 'product_events', 'support', 'analytics')),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, day, stage)
);

CREATE TABLE growth.leaks (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL REFERENCES core.companies (id),
    stage         text NOT NULL CHECK (stage IN (@STAGES@)),
    period        text NOT NULL CHECK (period IN ('week', 'month')),
    period_start  date NOT NULL,
    rate          numeric(6, 5) NOT NULL CHECK (rate BETWEEN 0 AND 1),
    median_rate   numeric(6, 5) NOT NULL CHECK (median_rate BETWEEN 0 AND 1),
    note_fa       text NOT NULL CHECK (length(note_fa) BETWEEN 1 AND 500),
    work_id       uuid REFERENCES work.work (id),       -- the SALES manager's work item
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, stage, period, period_start)
);
CREATE TRIGGER growth_leaks_immutable BEFORE UPDATE ON growth.leaks
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'stage', 'period', 'period_start',
                                                      'rate', 'median_rate', 'created_at');

-- =============================================================== feedback ==
CREATE SEQUENCE feedback.item_ref_seq;
CREATE TABLE feedback.items (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref                text NOT NULL UNIQUE
                            DEFAULT 'FB-' || lpad(nextval('feedback.item_ref_seq')::text, 6, '0'),
    company_id         uuid NOT NULL REFERENCES core.companies (id),
    kind               text NOT NULL CHECK (kind IN (@FEEDBACK_KINDS@)),
    area               text NOT NULL CHECK (length(area) BETWEEN 1 AND 60),
    title_fa           text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    count              int NOT NULL DEFAULT 1 CHECK (count >= 0),
    first_seen         timestamptz NOT NULL DEFAULT now(),
    last_seen          timestamptz NOT NULL DEFAULT now(),
    quotes             jsonb NOT NULL DEFAULT '[]'
                            CHECK (jsonb_typeof(quotes) = 'array' AND jsonb_array_length(quotes) <= 3),  -- masked
    sources            text[] NOT NULL DEFAULT '{}' CHECK (cardinality(sources) <= 500),   -- SC-…, NP-…
    state              text NOT NULL DEFAULT 'new'
                            CHECK (state IN ('new', 'triaged', 'in_backlog', 'done', 'wont_do')),
    work_ref           text CHECK (length(work_ref) <= 40),
    threshold_work_id  uuid REFERENCES work.work (id),      -- the PRODUCT manager's work item
    merged_into        uuid REFERENCES feedback.items (id),  -- merged into a similar item (never deleted)
    search             tsvector GENERATED ALWAYS AS (to_tsvector('simple', core.fa_normalize(title_fa))) STORED,
    version            int NOT NULL DEFAULT 1,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX feedback_items_top ON feedback.items (company_id, count DESC, last_seen DESC);
CREATE INDEX feedback_items_merge ON feedback.items (company_id, kind, area);
CREATE INDEX feedback_items_search ON feedback.items USING gin (search);
CREATE TRIGGER feedback_items_immutable BEFORE UPDATE ON feedback.items
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'first_seen', 'created_at');
CREATE TRIGGER feedback_items_version BEFORE UPDATE ON feedback.items
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- One piece of feedback (a message, an NPS comment): tagged by keyword rules
-- at once, the rest ('pending') by the nightly light-model batch.
CREATE TABLE feedback.signals (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    item_id          uuid REFERENCES feedback.items (id),
    source_ref       text NOT NULL CHECK (source_ref ~ '^(SC-[0-9]{6,}|NP-[0-9]{4}Q[1-4]-[A-Z][A-Z0-9]{1,9})$'),
    message_id       uuid REFERENCES support.messages (id),
    nps_response_id  uuid REFERENCES growth.nps_responses (id),
    quote            text CHECK (length(quote) <= 600),       -- masked (customer_mask.quote); NULL after retention
    quote_purged_at  timestamptz,
    kind             text CHECK (kind IN (@FEEDBACK_KINDS@)),
    area             text CHECK (length(area) BETWEEN 1 AND 60),
    tagged_by        text NOT NULL DEFAULT 'pending' CHECK (tagged_by IN ('pending', 'rule', 'model', 'agent')),
    tagged_at        timestamptz,
    mystery          boolean NOT NULL DEFAULT false,
    at               timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX feedback_signals_message ON feedback.signals (message_id) WHERE message_id IS NOT NULL;
CREATE UNIQUE INDEX feedback_signals_nps ON feedback.signals (nps_response_id) WHERE nps_response_id IS NOT NULL;
CREATE INDEX feedback_signals_pending ON feedback.signals (company_id, at) WHERE tagged_by = 'pending';
CREATE INDEX feedback_signals_item ON feedback.signals (item_id, at);
CREATE TRIGGER feedback_signals_immutable BEFORE UPDATE ON feedback.signals
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'source_ref', 'message_id',
                                                      'nps_response_id', 'mystery', 'at');

-- Each company's keywords (data, not prompt): pattern -> kind and area.
CREATE TABLE feedback.keywords (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    pattern          text NOT NULL CHECK (length(pattern) BETWEEN 1 AND 100),
    kind             text NOT NULL CHECK (kind IN (@FEEDBACK_KINDS@)),
    area             text NOT NULL CHECK (length(area) BETWEEN 1 AND 60),
    active           boolean NOT NULL DEFAULT true,
    created_by_kind  text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
    created_by_code  text NOT NULL CHECK (length(created_by_code) <= 64),
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, pattern)
);
CREATE TRIGGER feedback_keywords_immutable BEFORE UPDATE ON feedback.keywords
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'created_by_kind', 'created_by_code',
                                                      'created_at');

-- ================================================================= intake ==
-- IntakeSource. Its secret is in OpenBao (make intake-secret / make
-- telegram-bot-token), never here; "configured" is the secret's presence.
CREATE TABLE intake.sources (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    kind              text NOT NULL CHECK (kind IN ('telegram', 'chatwoot', 'product')),
    channel           text CHECK (channel IN (@CHANNELS@)),    -- telegram: which support channel
    allowed_ips       cidr[] NOT NULL DEFAULT '{}' CHECK (cardinality(allowed_ips) <= 50),
    kinds             text[] NOT NULL DEFAULT '{}' CHECK (kinds <@ ARRAY[@PRODUCT_EVENTS@]),
    enabled           boolean NOT NULL DEFAULT true,
    body_sha256       text CHECK (body_sha256 ~ '^[0-9a-f]{64}$'),   -- the sealed POST body
    last_event_at     timestamptz,
    last_rejected_at  timestamptz,
    created_by_code   text NOT NULL DEFAULT 'owner' CHECK (length(created_by_code) <= 64),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    version           int NOT NULL DEFAULT 1,
    UNIQUE NULLS NOT DISTINCT (company_id, kind, channel)
);
CREATE TRIGGER intake_sources_immutable BEFORE UPDATE ON intake.sources
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'kind', 'channel', 'created_at');
CREATE TRIGGER intake_sources_version BEFORE UPDATE ON intake.sources
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- Replay protection (an event id, a Telegram update_id); purged after expiry.
CREATE TABLE intake.nonces (
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    source_id    uuid NOT NULL REFERENCES intake.sources (id),
    nonce        text NOT NULL CHECK (length(nonce) BETWEEN 1 AND 128),
    received_at  timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL DEFAULT now() + interval '1 day',
    PRIMARY KEY (source_id, nonce)
);
CREATE INDEX intake_nonces_expiry ON intake.nonces (expires_at);
CREATE TRIGGER intake_nonces_immutable BEFORE UPDATE ON intake.nonces
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();

-- An accepted event (products: signup, referral_failed...); `data` is masked,
-- never a raw UID (subject instead), and '{}' after the retention job.
CREATE TABLE intake.events (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    source_id       uuid NOT NULL REFERENCES intake.sources (id),
    kind            text NOT NULL CHECK (kind IN (@PRODUCT_EVENTS@, 'telegram_update', 'chatwoot_event')),
    event_id        text NOT NULL CHECK (length(event_id) BETWEEN 1 AND 128),
    at              timestamptz,                -- the event's own time
    received_at     timestamptz NOT NULL DEFAULT now(),
    subject         text CHECK (subject ~ '^[0-9a-f]{64}$'),
    data            jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(data) = 'object'),
    data_purged_at  timestamptz,
    state           text NOT NULL DEFAULT 'accepted' CHECK (state IN ('accepted', 'applied', 'ignored', 'failed')),
    applied_at      timestamptz,
    error           text CHECK (length(error) <= 300),
    UNIQUE (source_id, event_id)
);
CREATE INDEX intake_events_recent ON intake.events (company_id, kind, received_at DESC);
CREATE INDEX intake_events_pending ON intake.events (received_at) WHERE state = 'accepted';
CREATE TRIGGER intake_events_immutable BEFORE UPDATE ON intake.events
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'source_id', 'kind', 'event_id', 'at',
                                                      'received_at', 'subject');

-- A refused call (bad signature, stale, duplicate, IP...): counts only.
CREATE TABLE intake.rejections (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    source_id   uuid REFERENCES intake.sources (id),
    kind        text NOT NULL CHECK (kind IN ('telegram', 'chatwoot', 'product')),
    reason      text NOT NULL CHECK (reason IN ('bad_signature', 'stale', 'duplicate', 'ip_not_allowed',
                                                'too_large', 'malformed', 'unknown_source', 'disabled',
                                                'rate_limited')),
    at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX intake_rejections_recent ON intake.rejections (company_id, at DESC);

-- ================================================================ academy ==
-- The private shadow suite of a company (support-shadow-<CODE>, versioned)
-- and its eval runs (purpose 'shadow').
ALTER TABLE academy.eval_suites DROP CONSTRAINT eval_suites_ref_check;
ALTER TABLE academy.eval_suites ADD CONSTRAINT eval_suites_ref_check
    CHECK (ref ~ '^EV-[0-9]{3,6}$' OR ref ~ '^support-shadow-[A-Z][A-Z0-9]{1,9}$');
ALTER TABLE academy.eval_suites ADD COLUMN version int NOT NULL DEFAULT 1 CHECK (version >= 1);
GRANT UPDATE (cases, version) ON academy.eval_suites TO hq_api;
GRANT INSERT, UPDATE (cases, version, updated_at) ON academy.eval_suites TO hq_worker;
ALTER TABLE academy.eval_runs DROP CONSTRAINT eval_runs_purpose_check;
ALTER TABLE academy.eval_runs ADD CONSTRAINT eval_runs_purpose_check
    CHECK (purpose IN ('manual', 'skill', 'teaching', 'shadow'));
GRANT INSERT ON academy.eval_runs TO hq_worker;
"""


def _kinds_sql(add: tuple[str, ...], drop: tuple[str, ...], valid: bool) -> str:
    """Rewrite decisions_kind_check from the kinds it holds now (plus `add`,
    minus `drop`): an earlier migration's kinds are kept whatever they are."""
    added = ", ".join(f"'{k}'" for k in add)
    dropped = ", ".join(f"'{k}'" for k in drop)
    tail = "" if valid else " NOT VALID"
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
                           'CHECK (kind IN (%s)){tail}', kinds);
        END $$;
    """


def upgrade() -> None:
    sql = (
        UPGRADE.replace("@APP@", APP_ROLES)
        .replace("@SUBJECT@", SUBJECT)
        .replace("@CHANNELS@", CHANNEL_KINDS)
        .replace("@ACTORS@", ACTOR_KINDS)
        .replace("@FEEDBACK_KINDS@", FEEDBACK_KINDS)
        .replace("@STAGES@", STAGES)
        .replace("@PRODUCT_EVENTS@", PRODUCT_EVENTS)
        .replace("@TEMPLATE_REF@", TEMPLATE_REF)
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
    # Replay protection expires: the nonce table is the one place rows go.
    grants.append("DROP TRIGGER intake_nonces_no_delete ON intake.nonces;")
    grants.append(f"GRANT DELETE ON intake.nonces TO {APP_ROLES};")
    execute_script("\n".join(grants))
    execute_script(_kinds_sql(NEW_KINDS, (), valid=True))


def downgrade() -> None:
    execute_script(
        _kinds_sql((), NEW_KINDS, valid=False)
        + """
        -- NOT VALID: shadow runs and support-shadow suites made since stay.
        ALTER TABLE academy.eval_runs DROP CONSTRAINT eval_runs_purpose_check;
        ALTER TABLE academy.eval_runs ADD CONSTRAINT eval_runs_purpose_check
            CHECK (purpose IN ('manual', 'skill', 'teaching')) NOT VALID;
        REVOKE INSERT ON academy.eval_runs FROM hq_worker;
        REVOKE INSERT, UPDATE ON academy.eval_suites FROM hq_worker;
        REVOKE UPDATE (cases, version) ON academy.eval_suites FROM hq_api;
        ALTER TABLE academy.eval_suites DROP COLUMN version;
        ALTER TABLE academy.eval_suites DROP CONSTRAINT eval_suites_ref_check;
        ALTER TABLE academy.eval_suites ADD CONSTRAINT eval_suites_ref_check
            CHECK (ref ~ '^EV-[0-9]{3,6}$') NOT VALID;
        DROP SCHEMA intake CASCADE;
        DROP SCHEMA feedback CASCADE;
        DROP SCHEMA growth CASCADE;
        DROP SCHEMA support CASCADE;
        DROP SCHEMA revenue CASCADE;
        """
    )
