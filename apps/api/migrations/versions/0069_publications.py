"""⟨1.39⟩ Contract §60 (prompt 39): the publish centre, every publication kept for good.

- media.publications: one permanent row per publication chain (§55.4): the first `publish` job
  and every later question (`meta.check`) and cancel (`meta.cancel`) of the same file, account and
  kind. Written where every publication passes (session_publish._send) in the job's transaction,
  updated on every answer of IG-Hub (domain/publications.apply). The texts (caption, the comment
  rule's words, DM, buttons and public replies, a story's reply word), the files with their roles,
  the source (the automation, the day, the session, the output), the state.
- `chain`: the ids of the chain's jobs, the first one first (unique: one row per chain; the
  backfill and a second recording of the same job make nothing new).
- `search_fa`: the title, the topic, the caption, the comment's words and the story word, each
  folded through hq_common.persian (ی/ي، ک/ك، spaces and ZWNJ dropped, digits as ASCII), so
  «بلاکچین», «بلاک چین» and «بلاک‌چین» are one key; a pg_trgm GIN index serves its LIKE.
- `file_ids`: every file the row refers to (its files, a set's slide, its frame), generated: the
  fresh start keeps a file a kept row lists in a uuid[] column, and the 72-hour sweep skips them.
- `ref` P-000001 … from media.publication_ref_seq.

KEEP on a fresh start (no foreign key but the company's, so a wipe of the work never touches it).
FORCE RLS by company_id as its neighbours; nothing is deleted by the app (no DELETE grant).

Revision ID: 0069
Revises: 0068
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"

UPGRADE = f"""
CREATE SEQUENCE media.publication_ref_seq;

-- every file a row refers to, as one uuid[]: the fresh start keeps a file a kept row lists in a
-- uuid[] column, and the 72-hour sweep skips them (§58.4 amended)
CREATE FUNCTION media.file_ids(p_files jsonb, p_thumb uuid) RETURNS uuid[]
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT coalesce(array_agg(DISTINCT x.id), '{{}}'::uuid[]) FROM (
        SELECT CAST(e ->> 'file_id' AS uuid) AS id FROM jsonb_array_elements(p_files) e
        WHERE e ->> 'file_id' ~ '^[0-9a-fA-F]{{8}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{12}}$'
        UNION ALL SELECT p_thumb WHERE p_thumb IS NOT NULL) x
$$;
GRANT EXECUTE ON FUNCTION media.file_ids(jsonb, uuid) TO {APP_ROLES};
GRANT USAGE ON SEQUENCE media.publication_ref_seq TO {APP_ROLES};

CREATE TABLE media.publications (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref            text NOT NULL UNIQUE
                   DEFAULT 'P-' || lpad(nextval('media.publication_ref_seq')::text, 6, '0'),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    channel        text NOT NULL DEFAULT 'instagram'
                   CHECK (channel IN ('instagram', 'youtube', 'telegram', 'website')),
    account        text NOT NULL CHECK (length(account) BETWEEN 1 AND 200),
    kind           text NOT NULL CHECK (kind IN ('reel', 'story', 'post', 'carousel', 'short', 'video',
                                                 'tg_post', 'article')),
    state          text NOT NULL CHECK (state IN ('scheduled', 'publishing', 'published', 'held',
                                                  'failed', 'cancelled')),
    state_note_fa  text CHECK (length(state_note_fa) <= 500),
    scheduled_at   timestamptz,
    published_at   timestamptz,
    url            text CHECK (length(url) <= 1000),
    external_id    text CHECK (length(external_id) <= 200),
    title_fa       text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
    topic_fa       text CHECK (length(topic_fa) <= 300),
    caption        text CHECK (length(caption) <= 5000),
    comment        jsonb CHECK (comment IS NULL OR jsonb_typeof(comment) = 'object'),
    story_word     text CHECK (length(story_word) <= 100),
    seo            jsonb CHECK (seo IS NULL OR jsonb_typeof(seo) = 'object'),
    files          jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(files) = 'array'),
    thumb_file_id  uuid,
    set_key        text CHECK (length(set_key) <= 300),
    set_n          smallint CHECK (set_n BETWEEN 1 AND 100),
    source         jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(source) = 'object'),
    insights       jsonb CHECK (insights IS NULL OR jsonb_typeof(insights) = 'object'),
    chain          uuid[] NOT NULL CHECK (cardinality(chain) BETWEEN 1 AND 2000),
    search_fa      text NOT NULL DEFAULT '' CHECK (length(search_fa) <= 20000),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    version        int NOT NULL DEFAULT 1,
    file_ids       uuid[] GENERATED ALWAYS AS (media.file_ids(files, thumb_file_id)) STORED,
    -- §60.1 at = published_at ?? scheduled_at ?? created_at
    at             timestamptz GENERATED ALWAYS AS (COALESCE(published_at, scheduled_at, created_at))
                   STORED
);
-- one row per chain: its first job
CREATE UNIQUE INDEX publications_first_job ON media.publications ((chain[1]));
CREATE INDEX publications_chain ON media.publications USING gin (chain);
CREATE INDEX publications_files ON media.publications USING gin (file_ids);
CREATE INDEX publications_company_at ON media.publications (company_id, at DESC);
CREATE INDEX publications_account_at ON media.publications (account, at DESC);
CREATE INDEX publications_set ON media.publications (set_key) WHERE set_key IS NOT NULL;
CREATE INDEX publications_automation ON media.publications ((source ->> 'automation'));
CREATE INDEX publications_search ON media.publications USING gin (search_fa gin_trgm_ops);
CREATE TRIGGER publications_immutable BEFORE UPDATE ON media.publications
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'created_at');
CREATE TRIGGER publications_version BEFORE UPDATE ON media.publications
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
GRANT SELECT, INSERT ON media.publications TO {APP_ROLES};
GRANT UPDATE (channel, account, kind, state, state_note_fa, scheduled_at, published_at, url,
              external_id, title_fa, topic_fa, caption, comment, story_word, seo, files,
              thumb_file_id, set_key, set_n, source, insights, chain, search_fa, updated_at)
    ON media.publications TO {APP_ROLES};

ALTER TABLE media.publications ENABLE ROW LEVEL SECURITY;
ALTER TABLE media.publications FORCE ROW LEVEL SECURITY;
CREATE POLICY publications_tenant ON media.publications TO {APP_ROLES}
    USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY publications_owner_role ON media.publications TO hq USING (true) WITH CHECK (true);
"""

DOWNGRADE = """
DROP TABLE media.publications;
DROP SEQUENCE media.publication_ref_seq;
DROP FUNCTION media.file_ids(jsonb, uuid);
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
