"""What the owner's reels order still lacked (contract §47 to §53, v1.31; the owner, 2026-11-10:
«شماره های ۲ و ۴ و ۵ رو … کامله کامله کامل انجام بده»).

- growth.topics (§47, the ledger of what was said): one row per topic and per reference (a
  Pinterest sample) a company used in a working group. `norm` is the text as code compares it;
  one topic is said once (the unique index on it), a day's run names one topic and one reference.
  A topic claimed in a session before its working group exists has no group yet (`order_ref`
  names the session); the seal moves it to the group. The owner frees one (`state: freed`):
  nothing is deleted. No foreign key on `run_id`: the ledger outlives a fresh start, the runs
  do not.
- media.narrators (§48): a company's narrator, set once: the voice and the style every
  `speech.make` for that company's content uses.
- growth.ig_posts and growth.ig_post_reads (§49, the best hour): each post of a company's
  account as IG-Hub last reported it (likes and comments only: IG-Hub keeps no views or reach),
  and the daily read job of each account.
- growth.automations.source (§50): a standing routine the owner asked for in one sentence names
  the session it was said in; it is `on` without a seal (`sealed_step_up_id` stays empty).

Additive only; nothing is deleted.

Revision ID: 0060
Revises: 0059
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
TABLES = ("growth.topics", "media.narrators", "growth.ig_posts", "growth.ig_post_reads")


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
-- §47 the ledger of topics said
CREATE TABLE growth.topics (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    -- the working group it was said in; NULL while it is a session's (order_ref), before a seal
    group_id    uuid REFERENCES growth.groups (id),
    order_ref   text CHECK (length(order_ref) <= 40),
    kind        text NOT NULL CHECK (kind IN ('topic', 'reference')),
    title_fa    text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    url         text CHECK (length(url) <= 2000),
    -- the text as code compares it (letters unified, marks and filler words dropped, sorted)
    norm        text NOT NULL CHECK (length(norm) BETWEEN 1 AND 400),
    tokens      text[] NOT NULL DEFAULT '{{}}',
    run_id      uuid,
    work_ref    text CHECK (length(work_ref) <= 40),
    output      text CHECK (length(output) <= 40),
    source      text NOT NULL CHECK (source IN ('claim', 'package', 'owner')),
    by_code     text NOT NULL CHECK (length(by_code) <= 64),
    state       text NOT NULL DEFAULT 'said' CHECK (state IN ('said', 'freed')),
    freed_at    timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'freed') = (freed_at IS NOT NULL))
);
-- one topic is said once in a company's working group (a session's, before its group, apart)
CREATE UNIQUE INDEX topics_said ON growth.topics
    (company_id, COALESCE(group_id::text, 'o:' || COALESCE(order_ref, '')), kind, norm)
    WHERE state = 'said';
-- a day's run names one topic and one reference
CREATE UNIQUE INDEX topics_run ON growth.topics (run_id, kind)
    WHERE run_id IS NOT NULL AND state = 'said';
CREATE INDEX topics_recent ON growth.topics (company_id, group_id, kind, created_at DESC);
CREATE TRIGGER topics_immutable BEFORE UPDATE ON growth.topics
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'kind', 'created_at');
GRANT SELECT, INSERT ON growth.topics TO {APP_ROLES};
GRANT UPDATE (group_id, title_fa, url, norm, tokens, run_id, work_ref, output, source, by_code,
              state, freed_at)
    ON growth.topics TO {APP_ROLES};

-- §48 a company's narrator, set once
CREATE TABLE media.narrators (
    company_id  uuid PRIMARY KEY REFERENCES core.companies (id),
    voice       text NOT NULL CHECK (voice ~ '^[A-Za-z]{{2,30}}$'),
    style_fa    text NOT NULL DEFAULT '' CHECK (length(style_fa) <= 500),
    by_kind     text NOT NULL CHECK (by_kind IN ('owner', 'agent')),
    by_code     text NOT NULL CHECK (length(by_code) <= 64),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER narrators_immutable BEFORE UPDATE ON media.narrators
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('company_id', 'created_at');
GRANT SELECT, INSERT ON media.narrators TO {APP_ROLES};
GRANT UPDATE (voice, style_fa, by_kind, by_code, updated_at) ON media.narrators TO {APP_ROLES};

-- §49 the posts of a company's Instagram account as IG-Hub last reported them
CREATE TABLE growth.ig_posts (
    company_id    uuid NOT NULL REFERENCES core.companies (id),
    account       text NOT NULL CHECK (length(account) BETWEEN 1 AND 64),
    post_id       text NOT NULL CHECK (length(post_id) BETWEEN 1 AND 64),
    media_type    text CHECK (length(media_type) <= 32),
    permalink     text CHECK (length(permalink) <= 500),
    posted_at     timestamptz NOT NULL,
    likes         int NOT NULL DEFAULT 0 CHECK (likes >= 0),
    comments      int NOT NULL DEFAULT 0 CHECK (comments >= 0),
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, account, post_id)
);
CREATE INDEX ig_posts_recent ON growth.ig_posts (company_id, account, posted_at DESC);
GRANT SELECT, INSERT ON growth.ig_posts TO {APP_ROLES};
GRANT UPDATE (media_type, permalink, posted_at, likes, comments, updated_at)
    ON growth.ig_posts TO {APP_ROLES};

-- the daily read of each account: the job on IG-Hub's server that was asked, and how it ended
CREATE TABLE growth.ig_post_reads (
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    account     text NOT NULL CHECK (length(account) BETWEEN 1 AND 64),
    job_id      uuid,
    asked_at    timestamptz,
    read_at     timestamptz,
    posts       int NOT NULL DEFAULT 0 CHECK (posts >= 0),
    note_fa     text CHECK (length(note_fa) <= 500),
    PRIMARY KEY (company_id, account)
);
GRANT SELECT, INSERT ON growth.ig_post_reads TO {APP_ROLES};
GRANT UPDATE (job_id, asked_at, read_at, posts, note_fa) ON growth.ig_post_reads TO {APP_ROLES};

-- §50 a standing routine names the session it was asked in ({{order, by}}); set at birth
ALTER TABLE growth.automations
    ADD COLUMN source jsonb CHECK (source IS NULL OR jsonb_typeof(source) = 'object');
CREATE INDEX automations_source_order ON growth.automations ((source ->> 'order'))
    WHERE source IS NOT NULL;
"""  # noqa: S608 - composed from module constants only
    + "".join(_rls(t) for t in TABLES)
)

DOWNGRADE = """
DROP INDEX growth.automations_source_order;
ALTER TABLE growth.automations DROP COLUMN source;
DROP TABLE growth.ig_post_reads;
DROP TABLE growth.ig_posts;
DROP TABLE media.narrators;
DROP TABLE growth.topics;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
