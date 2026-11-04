"""Prompt 22 part 3 (contract §31.3-§31.5): newsletter, SEO rank and competitors,
one campaign calendar.

- §31.3 growth.newsletter_lists: which Listmonk list is which company's (Listmonk
  keeps the subscribers, their consent and the one-click unsubscribe; the hub
  keeps only the mapping); growth.newsletter_campaigns: the campaigns the hub
  made or scheduled (the calendar's rows and the step-up record); the daily
  open and click figures go to growth.metrics_daily, kind `newsletter`.
- §31.4 growth.keywords, growth.rank_daily (our positions: Search Console, and
  SearXNG marked approximate), growth.competitors, growth.competitor_daily (public
  figures), growth.competitor_jumps (one work item per jump, never twice).
- §31.5 growth.campaigns and growth.calendar_manual (the owner's own items).

Every new table carries company_id under FORCE RLS like 0039. Fresh start:
definitions (lists, keywords, competitors, campaigns) stay, the daily data goes.

Revision ID: 0041
Revises: 0040
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
OLD_KINDS = (
    "'search_console', 'ga4', 'instagram', 'telegram', 'youtube', 'x', 'pagespeed', 'trends', "
    "'bing', 'play_console', 'hub'"
)
TABLES = (
    "growth.newsletter_lists",
    "growth.newsletter_campaigns",
    "growth.keywords",
    "growth.rank_daily",
    "growth.competitors",
    "growth.competitor_daily",
    "growth.competitor_jumps",
    "growth.campaigns",
    "growth.calendar_manual",
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
-- the daily read of the newsletter joins the kinds
ALTER TABLE growth.metrics_daily DROP CONSTRAINT metrics_daily_kind_check;
ALTER TABLE growth.metrics_daily ADD CONSTRAINT metrics_daily_kind_check
    CHECK (kind IN ({OLD_KINDS}, 'newsletter'));

-- §31.3 newsletter (Listmonk keeps the subscribers; the hub keeps the mapping)
CREATE TABLE growth.newsletter_lists (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    listmonk_id  int NOT NULL CHECK (listmonk_id >= 1),
    name         text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (listmonk_id)
);
CREATE INDEX newsletter_lists_company ON growth.newsletter_lists (company_id);
GRANT SELECT, INSERT ON growth.newsletter_lists TO {APP_ROLES};

CREATE TABLE growth.newsletter_campaigns (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    listmonk_id  int NOT NULL CHECK (listmonk_id >= 1),
    list_id      int NOT NULL CHECK (list_id >= 1),
    subject      text NOT NULL CHECK (length(subject) BETWEEN 1 AND 300),
    state        text NOT NULL DEFAULT 'draft'
                 CHECK (state IN ('draft', 'scheduled', 'running', 'finished', 'paused', 'cancelled')),
    send_at      timestamptz,
    list_size    int CHECK (list_size IS NULL OR list_size >= 0),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (listmonk_id)
);
CREATE INDEX newsletter_campaigns_when ON growth.newsletter_campaigns (company_id, send_at);
CREATE TRIGGER newsletter_campaigns_immutable BEFORE UPDATE ON growth.newsletter_campaigns
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'listmonk_id', 'created_at');
GRANT SELECT, INSERT ON growth.newsletter_campaigns TO {APP_ROLES};
GRANT UPDATE (state, send_at, list_size, updated_at) ON growth.newsletter_campaigns TO {APP_ROLES};

-- §31.4 SEO rank and competitors
CREATE TABLE growth.keywords (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    phrase      text NOT NULL CHECK (length(btrim(phrase)) BETWEEN 1 AND 200),
    site        text NOT NULL CHECK (site ~ '^[A-Za-z0-9.-]{{3,253}}$'),
    target_url  text CHECK (target_url IS NULL OR length(target_url) <= 2000),
    state       text NOT NULL DEFAULT 'on' CHECK (state IN ('on', 'paused')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, site, phrase)
);
CREATE TRIGGER keywords_immutable BEFORE UPDATE ON growth.keywords
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'created_at');
GRANT SELECT, INSERT, DELETE ON growth.keywords TO {APP_ROLES};
GRANT UPDATE (phrase, site, target_url, state, updated_at) ON growth.keywords TO {APP_ROLES};

CREATE TABLE growth.rank_daily (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    keyword_id  uuid NOT NULL REFERENCES growth.keywords (id) ON DELETE CASCADE,
    day         date NOT NULL,
    source      text NOT NULL CHECK (source IN ('search_console', 'searxng')),
    position    numeric CHECK (position IS NULL OR position >= 0),
    url         text CHECK (url IS NULL OR length(url) <= 2000),
    at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (keyword_id, day, source)
);
CREATE INDEX rank_daily_recent ON growth.rank_daily (company_id, day DESC);
GRANT SELECT, INSERT ON growth.rank_daily TO {APP_ROLES};
GRANT UPDATE (position, url, at) ON growth.rank_daily TO {APP_ROLES};

CREATE TABLE growth.competitors (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    name_fa     text NOT NULL CHECK (length(btrim(name_fa)) BETWEEN 1 AND 200),
    site        text CHECK (site IS NULL OR site ~ '^[A-Za-z0-9.-]{{3,253}}$'),
    instagram   text CHECK (instagram IS NULL OR instagram ~ '^[A-Za-z0-9._]{{1,64}}$'),
    youtube     text CHECK (youtube IS NULL OR youtube ~ '^UC[A-Za-z0-9_-]{{20,24}}$'),
    telegram    text CHECK (telegram IS NULL OR telegram ~ '^[A-Za-z0-9_]{{4,64}}$'),
    state       text NOT NULL DEFAULT 'on' CHECK (state IN ('on', 'paused')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX competitors_company ON growth.competitors (company_id);
CREATE TRIGGER competitors_immutable BEFORE UPDATE ON growth.competitors
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'created_at');
GRANT SELECT, INSERT, DELETE ON growth.competitors TO {APP_ROLES};
GRANT UPDATE (name_fa, site, instagram, youtube, telegram, state, updated_at)
    ON growth.competitors TO {APP_ROLES};

CREATE TABLE growth.competitor_daily (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    competitor_id  uuid NOT NULL REFERENCES growth.competitors (id) ON DELETE CASCADE,
    day            date NOT NULL,
    key            text NOT NULL CHECK (key ~ '^[a-z][a-z0-9_]{{0,40}}$'),
    value          numeric NOT NULL,
    source         text NOT NULL CHECK (length(source) BETWEEN 1 AND 100),
    at             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (competitor_id, day, key)
);
CREATE INDEX competitor_daily_recent ON growth.competitor_daily (company_id, day DESC);
GRANT SELECT, INSERT ON growth.competitor_daily TO {APP_ROLES};
GRANT UPDATE (value, source, at) ON growth.competitor_daily TO {APP_ROLES};

CREATE TABLE growth.competitor_jumps (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    competitor_id  uuid NOT NULL REFERENCES growth.competitors (id) ON DELETE CASCADE,
    day            date NOT NULL,
    key            text NOT NULL CHECK (key ~ '^[a-z][a-z0-9_]{{0,40}}$'),
    before_value   numeric NOT NULL,
    after_value    numeric NOT NULL,
    work_id        uuid REFERENCES work.work (id),
    at             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (competitor_id, day, key)
);
GRANT SELECT, INSERT ON growth.competitor_jumps TO {APP_ROLES};
GRANT UPDATE (work_id) ON growth.competitor_jumps TO {APP_ROLES};

-- §31.5 one campaign calendar
CREATE TABLE growth.campaigns (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    title_fa    text NOT NULL CHECK (length(btrim(title_fa)) BETWEEN 1 AND 200),
    goal_fa     text NOT NULL DEFAULT '' CHECK (length(goal_fa) <= 1000),
    starts      date NOT NULL,
    ends        date NOT NULL,
    channels    text[] NOT NULL DEFAULT '{{}}' CHECK (cardinality(channels) <= 20),
    budget      numeric CHECK (budget IS NULL OR budget >= 0),
    state       text NOT NULL DEFAULT 'planned'
                CHECK (state IN ('planned', 'running', 'done', 'cancelled')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (ends >= starts)
);
CREATE INDEX campaigns_window ON growth.campaigns (company_id, starts, ends);
CREATE TRIGGER campaigns_immutable BEFORE UPDATE ON growth.campaigns
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'created_at');
GRANT SELECT, INSERT, DELETE ON growth.campaigns TO {APP_ROLES};
GRANT UPDATE (title_fa, goal_fa, starts, ends, channels, budget, state, updated_at)
    ON growth.campaigns TO {APP_ROLES};

CREATE TABLE growth.calendar_manual (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    day         date NOT NULL,
    at          timestamptz,
    title_fa    text NOT NULL CHECK (length(btrim(title_fa)) BETWEEN 1 AND 200),
    platform    text CHECK (platform IS NULL OR platform ~ '^[a-z][a-z0-9_]{{1,40}}$'),
    state       text NOT NULL DEFAULT 'planned' CHECK (state IN ('planned', 'done', 'cancelled')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX calendar_manual_day ON growth.calendar_manual (company_id, day);
CREATE TRIGGER calendar_manual_immutable BEFORE UPDATE ON growth.calendar_manual
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'created_at');
GRANT SELECT, INSERT, DELETE ON growth.calendar_manual TO {APP_ROLES};
GRANT UPDATE (day, at, title_fa, platform, state, updated_at) ON growth.calendar_manual
    TO {APP_ROLES};
"""
    + "".join(_rls(t) for t in TABLES)
)

DOWNGRADE = f"""
DROP TABLE growth.calendar_manual;
DROP TABLE growth.campaigns;
DROP TABLE growth.competitor_jumps;
DROP TABLE growth.competitor_daily;
DROP TABLE growth.competitors;
DROP TABLE growth.rank_daily;
DROP TABLE growth.keywords;
DROP TABLE growth.newsletter_campaigns;
DROP TABLE growth.newsletter_lists;
DELETE FROM growth.metrics_daily WHERE kind = 'newsletter';
ALTER TABLE growth.metrics_daily DROP CONSTRAINT metrics_daily_kind_check;
ALTER TABLE growth.metrics_daily ADD CONSTRAINT metrics_daily_kind_check
    CHECK (kind IN ({OLD_KINDS}));
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
