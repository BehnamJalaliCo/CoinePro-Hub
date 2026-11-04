"""Prompt 23 (contract §32.5–32.6): the voice layer's data, in schema talk.

- talk.voice_usage   one row per spoken sentence (a sample or a check too): the provider's own
                     token counts and the price in force at that moment, so the meter is a sum
                     of rows and never a guess. Append-only (the owner's money record: it stays
                     through a fresh start).
- talk.engine_state  one row per engine: the light (missing / checking / ok / failing / capped),
                     its plain Persian reason, whether the provider's key is set (never the key),
                     and the owner's price override (a whole price object, or none).
- talk.voice_jobs    the local engine's queue: a sentence for Piper, claimed by the hub's TTS
                     one-shot (a third queue beside the briefings and the bake-off), answered
                     with an Ogg/Opus file. Piper is the chain's last link, so this queue is how
                     the voice never stops.
- owner.settings.voice  {month_cap_usd|null, warn_at, chain} (the owner's cap and chain; nothing
                     but the owner raises the cap). Additive: GET/PUT /owner/settings.

Every table carries company_id (the holding's: this is holding-level data) under FORCE RLS as in
0042. Schema `talk` itself is made by 0043.

Revision ID: 0044
Revises: 0043
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
TABLES = ("talk.voice_usage", "talk.engine_state", "talk.voice_jobs")


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
-- ============================================================== usage ==
CREATE TABLE talk.voice_usage (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    at               timestamptz NOT NULL DEFAULT now(),
    engine           text NOT NULL CHECK (engine ~ '^[a-z0-9][a-z0-9._-]{{1,60}}$'),
    provider         text NOT NULL CHECK (provider IN ('google', 'local')),
    -- what the call was: a spoken sentence of a turn, the owner's sample, or the key's check
    kind             text NOT NULL DEFAULT 'speech' CHECK (kind IN ('speech', 'sample', 'check')),
    persona          text NOT NULL DEFAULT '' CHECK (length(persona) <= 80),
    conversation_ref text CHECK (length(conversation_ref) <= 40),
    turn_id          text CHECK (length(turn_id) <= 80),
    seq              int CHECK (seq >= 0),
    chars            int NOT NULL DEFAULT 0 CHECK (chars >= 0),
    -- the provider's own counts (usageMetadata); zero for the local engine
    text_tokens      int NOT NULL DEFAULT 0 CHECK (text_tokens >= 0),
    audio_tokens     int NOT NULL DEFAULT 0 CHECK (audio_tokens >= 0),
    seconds          numeric(9, 3) NOT NULL DEFAULT 0 CHECK (seconds >= 0),
    -- the price in force when the sentence was made, and tokens x price
    price            jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(price) = 'object'),
    usd              numeric(14, 8) NOT NULL DEFAULT 0 CHECK (usd >= 0)
);
CREATE INDEX voice_usage_at ON talk.voice_usage (at DESC);
CREATE INDEX voice_usage_engine ON talk.voice_usage (engine, at DESC);
CREATE TRIGGER voice_usage_append_only BEFORE UPDATE OR DELETE ON talk.voice_usage
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON talk.voice_usage TO {APP_ROLES};

-- ============================================================== light ==
CREATE TABLE talk.engine_state (
    engine         text PRIMARY KEY CHECK (engine ~ '^[a-z0-9][a-z0-9._-]{{1,60}}$'),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    provider       text NOT NULL CHECK (provider IN ('google', 'local')),
    state          text NOT NULL DEFAULT 'missing'
                        CHECK (state IN ('missing', 'checking', 'ok', 'failing', 'capped')),
    reason_fa      text CHECK (length(reason_fa) <= 300),
    secret_set     boolean NOT NULL DEFAULT false,
    checked_at     timestamptz,
    -- the owner's own price for this engine (a whole price object), else the table's
    price_override jsonb CHECK (price_override IS NULL OR jsonb_typeof(price_override) = 'object'),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT ON talk.engine_state TO {APP_ROLES};
GRANT UPDATE (state, reason_fa, secret_set, checked_at, price_override, updated_at)
    ON talk.engine_state TO {APP_ROLES};

-- ======================================================== Piper's queue ==
CREATE TABLE talk.voice_jobs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    voice       text NOT NULL CHECK (voice ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{{1,80}}$'),
    script      text NOT NULL CHECK (length(script) BETWEEN 1 AND 2000),
    rate        numeric(4, 2) NOT NULL DEFAULT 1.00 CHECK (rate BETWEEN 0.5 AND 2.0),
    state       text NOT NULL DEFAULT 'queued'
                     CHECK (state IN ('queued', 'claimed', 'done', 'failed', 'cancelled')),
    attempts    int NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 20),
    claimed_at  timestamptz,
    error       text CHECK (length(error) <= 300),
    file_id     uuid REFERENCES files.files (id),
    seconds     numeric(9, 3),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'done') = (file_id IS NOT NULL))
);
CREATE INDEX voice_jobs_queued ON talk.voice_jobs (created_at) WHERE state IN ('queued', 'claimed');
CREATE TRIGGER voice_jobs_immutable BEFORE UPDATE ON talk.voice_jobs
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'voice', 'script', 'rate',
                                                      'created_at');
GRANT SELECT, INSERT ON talk.voice_jobs TO {APP_ROLES};
GRANT UPDATE (state, attempts, claimed_at, error, file_id, seconds, updated_at)
    ON talk.voice_jobs TO {APP_ROLES};

-- ================================================== the owner's settings ==
ALTER TABLE owner.settings
    ADD COLUMN voice jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(voice) = 'object');
GRANT UPDATE (voice) ON owner.settings TO hq_api;
"""
    + "".join(_rls(t) for t in TABLES)
)

DOWNGRADE = """
REVOKE UPDATE (voice) ON owner.settings FROM hq_api;
ALTER TABLE owner.settings DROP COLUMN voice;
DROP TABLE talk.voice_jobs;
DROP TABLE talk.engine_state;
DROP TABLE talk.voice_usage;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
