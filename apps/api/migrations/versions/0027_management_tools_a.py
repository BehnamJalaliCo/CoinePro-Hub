"""Prompt 12, part A (contract §21.1, §21.7, §21.11, §21.13): the premium
advisor's memos and proactive triggers, a new connection, and the substitute
players (ChatGPT, Gemini, DeepSeek) with their seats, calls, sign-ins and
creatives. Part B (§4-§8, §10-§12) and §2/§3/§13 have migrations of their own.

Two schemas, every table company-scoped (company_id, FORCE RLS, the
once-per-query policy of 0009; owner and holding rows carry the holding's id):

  advisor      memos (DM-0001: bound to one decision, mode and card version),
               triggers (one row per rule trigger and day: `key` is unique)
  substitutes  players (gpt, gemini, deepseek), seats, calls (every seat call,
               also the CLI and web job queue), logins (a CLI's headless
               sign-in; the owner's pasted code is kept until the runner reads
               it once), creatives (CR-0001)

Also:
- owner.settings gains `advisor` and `substitutes` (jsonb blocks, §21.12);
- work.work gains `run_meta` (a run's task class and owner-zone flag, read by
  the runner; set by the code that makes the work, never by an agent);
- a memo becomes `stale` when its pending card changes (any column but the
  bookkeeping ones: version, updated_at, reminded_at, reminders, waiting_h);
- llm.connections: statuses pending_secret, verifying, ready and error (a new
  connection, §21.7), kind `subscription` (the substitute accounts), verified_at;
  the api may insert a connection (POST /connections, sealed) and write the
  ledger rows of the substitute calls (caller 'substitutes' only);
- the new task classes (§21.0, §21.13), the three substitute connections
  (chatgpt-plus, gemini-pro, deepseek-free; disabled for the router: a Claude
  run never goes to them) and the three web profile accounts (chatgpt-web,
  gemini-web, deepseek-web; policy browse.kind "profile", no secret).

No decision kind is added (contract §21.12), so decisions_kind_check is not
touched.

Revision ID: 0027
Revises: 0025 (the parent re-chains it after prompt 11's 0026_1)
"""

from __future__ import annotations

import re

from hq_api.migration_sql import execute_script

revision = "0027"
down_revision = "0025"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
SCHEMAS = ("advisor", "substitutes")
TABLES = (
    "advisor.memos",
    "advisor.triggers",
    "substitutes.players",
    "substitutes.seats",
    "substitutes.calls",
    "substitutes.logins",
    "substitutes.creatives",
)
SEQUENCES = ("advisor.memo_ref_seq", "substitutes.creative_ref_seq")
SEATS = (
    "'advisor_second_opinion', 'code_review', 'overseer_cross_check', 'assistant_errand', "
    "'content_draft', 'long_read', 'quick_search', 'third_opinion', 'creative'"
)
PLAYERS = "'gpt', 'gemini', 'deepseek'"
TRIGGER_KINDS = (
    "'budget', 'quota', 'compliance', 'incident', 'revenue', 'waiting_decisions', 'finding', 'okr'"
)
PLACEMENTS = (
    "'telegram_post', 'telegram_story', 'instagram_post', 'instagram_story', 'banner', 'other'"
)
TASK_CLASSES = (
    ("advisor_memo", "The advisor's decision memo on a pending card (prompt 12 §1)"),
    ("advisor_proactive", "The advisor's proactive note on a rule trigger (prompt 12 §1.3)"),
    ("advisor_review", "The advisor's weekly review brief (prompt 12 §3)"),
    ("ask_hub", "The librarian's answer to ask the hub (prompt 12 §2)"),
    ("ceo_letter", "A CEO's weekly letter to the owner (prompt 12 §4.3)"),
    ("hr_eval", "The monthly HR evaluation (prompt 12 §6)"),
    ("dceo_predict", "The digital CEO's model prediction (prompt 12 §13)"),
    ("dceo_principles", "The digital CEO's weekly principles (prompt 12 §13)"),
    ("sub_code_review", "A substitute player's second code review (subscription only)"),
    ("sub_second_opinion", "A substitute player's second opinion on a memo (subscription only)"),
    ("sub_cross_check", "A substitute player's cross-check of sampled claims (subscription only)"),
    ("sub_errand", "A substitute player's errand draft (subscription only)"),
    ("sub_draft", "A substitute player's first draft of content (subscription only)"),
    ("sub_long_read", "A substitute player's summary of a long read (subscription only)"),
    ("sub_creative", "A substitute player's image or video (subscription only)"),
)

UPGRADE = r"""
CREATE SCHEMA advisor;
CREATE SCHEMA substitutes;
GRANT USAGE ON SCHEMA advisor, substitutes TO @APP@;

-- ================================================================ advisor ==
CREATE SEQUENCE advisor.memo_ref_seq;
-- A decision memo (contract §21.1): bound to one card, mode and card version;
-- the same three again is the same memo. `facts` is the masked facts pack the
-- advisor and the substitutes' second and third opinions all read.
CREATE TABLE advisor.memos (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref                text NOT NULL UNIQUE
                            DEFAULT 'DM-' || lpad(nextval('advisor.memo_ref_seq')::text, 4, '0'),
    company_id         uuid NOT NULL REFERENCES core.companies (id),
    decision_id        uuid NOT NULL REFERENCES cartable.decisions (id),
    decision_ref       text NOT NULL CHECK (decision_ref ~ '^D-[0-9]{4,9}$'),
    decision_version   int NOT NULL CHECK (decision_version >= 1),
    mode               text NOT NULL CHECK (mode IN ('standard', 'devil')),
    trigger            text NOT NULL CHECK (trigger IN ('owner', 'auto')),
    state              text NOT NULL DEFAULT 'writing'
                            CHECK (state IN ('writing', 'ready', 'failed', 'stale')),
    state_reason       text CHECK (length(state_reason) <= 300),
    summary_fa         text CHECK (length(summary_fa) <= 4000),
    recommendation     text CHECK (recommendation IN ('approve', 'reject', 'return', 'ask')),
    confidence         numeric(4, 3) CHECK (confidence BETWEEN 0 AND 1),
    options            jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(options) = 'array'),
    against_md         text CHECK (length(against_md) <= 20000),
    risks              jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(risks) = 'array'),
    questions          jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(questions) = 'array'),
    citations          jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(citations) = 'array'),
    citations_dropped  int NOT NULL DEFAULT 0 CHECK (citations_dropped >= 0),
    usage_tokens       bigint NOT NULL DEFAULT 0 CHECK (usage_tokens >= 0),
    usage_usd          numeric(14, 6) NOT NULL DEFAULT 0 CHECK (usage_usd >= 0),
    second_opinion     jsonb CHECK (second_opinion IS NULL OR jsonb_typeof(second_opinion) = 'object'),
    third_opinion      jsonb CHECK (third_opinion IS NULL OR jsonb_typeof(third_opinion) = 'object'),
    facts              jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(facts) = 'object'),
    facts_sha256       text CHECK (facts_sha256 ~ '^[0-9a-f]{64}$'),
    work_id            uuid REFERENCES work.work (id),
    created_by_kind    text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
    created_by_code    text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
    written_by_code    text CHECK (length(written_by_code) <= 64),
    created_at         timestamptz NOT NULL DEFAULT now(),
    written_at         timestamptz,
    updated_at         timestamptz NOT NULL DEFAULT now(),
    version            int NOT NULL DEFAULT 1,
    UNIQUE (decision_id, mode, decision_version),
    -- A ready memo always carries the strongest case against and an answer.
    CHECK (state <> 'ready' OR (recommendation IS NOT NULL AND confidence IS NOT NULL
                                AND length(btrim(coalesce(against_md, ''))) > 0))
);
CREATE INDEX advisor_memos_decision ON advisor.memos (decision_id, mode, decision_version DESC);
CREATE INDEX advisor_memos_recent ON advisor.memos (created_at DESC);
CREATE INDEX advisor_memos_work ON advisor.memos (work_id) WHERE work_id IS NOT NULL;
CREATE TRIGGER advisor_memos_version BEFORE UPDATE ON advisor.memos
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
CREATE TRIGGER advisor_memos_immutable BEFORE UPDATE ON advisor.memos
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'decision_id', 'decision_ref',
                                                      'decision_version', 'mode', 'trigger', 'created_by_kind',
                                                      'created_by_code', 'created_at');

-- A proactive trigger (contract §21.1): rules fire it by code, once per key
-- (kind, subject and day); the advisor is woken at most once per key.
CREATE TABLE advisor.triggers (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          uuid NOT NULL REFERENCES core.companies (id),
    key                 text NOT NULL UNIQUE CHECK (key ~ '^[a-z_]+:[A-Za-z0-9:_.@-]{1,180}$'),
    kind                text NOT NULL CHECK (kind IN (@TRIGGER_KINDS@)),
    subject_company_id  uuid REFERENCES core.companies (id),
    day                 date NOT NULL,
    fired_at            timestamptz NOT NULL DEFAULT now(),
    facts               jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(facts) = 'object'),
    state               text NOT NULL CHECK (state IN ('sent', 'deferred', 'capped')),
    state_reason        text CHECK (length(state_reason) <= 300),
    work_id             uuid REFERENCES work.work (id),
    message_ref         text CHECK (message_ref ~ '^A-[0-9]{1,9}$'),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX advisor_triggers_recent ON advisor.triggers (fired_at DESC);
CREATE INDEX advisor_triggers_day ON advisor.triggers (day, state);
CREATE INDEX advisor_triggers_work ON advisor.triggers (work_id) WHERE work_id IS NOT NULL;
CREATE TRIGGER advisor_triggers_immutable BEFORE UPDATE ON advisor.triggers
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'key', 'kind', 'subject_company_id',
                                                      'day', 'fired_at', 'facts');

-- A memo of a still-pending card becomes stale when the card changes (its
-- version moves for anything but bookkeeping). SECURITY DEFINER: the card's
-- company session cannot see the holding's memo rows under RLS.
CREATE FUNCTION advisor.stale_on_change() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        skip text[] := ARRAY['version', 'updated_at', 'reminded_at', 'reminders', 'waiting_h'];
    BEGIN
        IF NEW.version IS DISTINCT FROM OLD.version AND NEW.status = 'pending'
           AND (to_jsonb(NEW) - skip) IS DISTINCT FROM (to_jsonb(OLD) - skip) THEN
            UPDATE advisor.memos SET state = 'stale', state_reason = 'the card changed', updated_at = now()
             WHERE decision_id = NEW.id AND decision_version < NEW.version AND state <> 'stale';
        END IF;
        RETURN NEW;
    END $$;
REVOKE ALL ON FUNCTION advisor.stale_on_change() FROM PUBLIC;
CREATE TRIGGER decisions_memo_stale AFTER UPDATE ON cartable.decisions
    FOR EACH ROW EXECUTE FUNCTION advisor.stale_on_change();

-- ============================================================ substitutes ==
-- A substitute player (contract §21.13): its sign-ins, status, models (data,
-- checked against what its CLI offers), capabilities and web profile state.
CREATE TABLE substitutes.players (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    player            text NOT NULL UNIQUE CHECK (player IN (@PLAYERS@)),
    connection_key    text NOT NULL CHECK (connection_key ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
    runner            text CHECK (runner IN ('codex_cli', 'gemini_cli')),
    web_account       text NOT NULL CHECK (web_account ~ '^[a-z0-9][a-z0-9_.-]{1,40}$'),
    plan_fa           text NOT NULL CHECK (length(plan_fa) BETWEEN 1 AND 200),
    login_state       text NOT NULL DEFAULT 'signed_out'
                           CHECK (login_state IN ('signed_out', 'signing_in', 'signed_in', 'expired')),
    login_since       timestamptz,
    login_last_ok_at  timestamptz,
    status            text NOT NULL DEFAULT 'off' CHECK (status IN ('ready', 'limited', 'off', 'error')),
    limited_until     timestamptz,
    status_reason     text CHECK (length(status_reason) <= 300),
    models            jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(models) = 'array'),
    models_checked_at timestamptz,
    capabilities      jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(capabilities) = 'object'),
    web_state         text NOT NULL DEFAULT 'signed_out'
                           CHECK (web_state IN ('signed_in', 'expired', 'signed_out')),
    web_last_ok_at    timestamptz,
    web_last_job_at   timestamptz,
    recipe_version    text NOT NULL DEFAULT '1' CHECK (length(recipe_version) BETWEEN 1 AND 40),
    web_last_failure  text CHECK (length(web_last_failure) <= 300),
    price_usd         numeric(10, 2) NOT NULL DEFAULT 0 CHECK (price_usd >= 0),
    version           int NOT NULL DEFAULT 1,
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER substitutes_players_version BEFORE UPDATE ON substitutes.players
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
CREATE TRIGGER substitutes_players_immutable BEFORE UPDATE ON substitutes.players
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'player', 'connection_key', 'runner',
                                                      'web_account');

-- A seat a player holds (the owner changes them with 🔏 substitute.seats).
CREATE TABLE substitutes.seats (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    player         text NOT NULL REFERENCES substitutes.players (player),
    seat           text NOT NULL CHECK (seat IN (@SEATS@)),
    via            text NOT NULL CHECK (via IN ('cli', 'web')),
    model          text NOT NULL CHECK (length(model) BETWEEN 1 AND 80),
    enabled        boolean NOT NULL DEFAULT true,
    per_day        int NOT NULL CHECK (per_day BETWEEN 0 AND 1000),
    per_day_video  int CHECK (per_day_video BETWEEN 0 AND 100),
    position       int NOT NULL DEFAULT 0,
    updated_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (player, seat),
    CHECK (seat <> 'creative' OR via = 'web'),
    CHECK (player <> 'deepseek' OR via = 'web')
);

-- Every seat call: the CLI job queue (claimed by the host dispatcher) and the
-- web job queue (run by the worker through egress) at once. The input is the
-- masked text the player reads (cleared once finished); the result is
-- labelled with its source and is never evidence.
CREATE TABLE substitutes.calls (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    player         text NOT NULL CHECK (player IN (@PLAYERS@)),
    seat           text CHECK (seat IN (@SEATS@)),
    kind           text NOT NULL DEFAULT 'call' CHECK (kind IN ('call', 'login', 'logout', 'models')),
    via            text NOT NULL CHECK (via IN ('cli', 'web')),
    task           text NOT NULL DEFAULT 'text' CHECK (task IN ('text', 'image', 'video')),
    model          text CHECK (length(model) <= 80),
    state          text NOT NULL DEFAULT 'queued'
                        CHECK (state IN ('queued', 'running', 'done', 'failed', 'skipped')),
    state_reason   text CHECK (length(state_reason) <= 300),
    caller_kind    text NOT NULL CHECK (caller_kind IN ('owner', 'agent', 'service')),
    caller_code    text NOT NULL CHECK (length(caller_code) BETWEEN 1 AND 64),
    purpose_kind   text CHECK (purpose_kind ~ '^[a-z_]{2,30}$'),
    purpose_ref    text CHECK (length(purpose_ref) <= 64),
    input_md       text CHECK (length(input_md) <= 200000),
    input_sha256   text CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    checkout       jsonb CHECK (checkout IS NULL OR jsonb_typeof(checkout) = 'object'),
    login_id       uuid,
    result         jsonb CHECK (result IS NULL OR jsonb_typeof(result) = 'object'),
    file_ids       uuid[],
    input_tokens   int CHECK (input_tokens >= 0),
    output_tokens  int CHECK (output_tokens >= 0),
    estimated      boolean NOT NULL DEFAULT false,
    equiv_usd      numeric(14, 6) NOT NULL DEFAULT 0 CHECK (equiv_usd >= 0),
    timeout_s      int NOT NULL DEFAULT 300 CHECK (timeout_s BETWEEN 10 AND 1800),
    -- An agent's call answered later: the answer goes back to it as a work item.
    delivered_at   timestamptz,
    reply_work_id  uuid REFERENCES work.work (id),
    day            date NOT NULL,
    month_key      text NOT NULL CHECK (month_key ~ '^[0-9]{4}-[0-9]{2}$'),
    created_at     timestamptz NOT NULL DEFAULT now(),
    claimed_at     timestamptz,
    finished_at    timestamptz
);
CREATE INDEX substitutes_calls_queue ON substitutes.calls (via, created_at) WHERE state = 'queued';
CREATE INDEX substitutes_calls_running ON substitutes.calls (via) WHERE state = 'running';
CREATE INDEX substitutes_calls_day ON substitutes.calls (player, seat, day);
CREATE INDEX substitutes_calls_month ON substitutes.calls (player, month_key);
CREATE INDEX substitutes_calls_purpose ON substitutes.calls (purpose_kind, purpose_ref);
CREATE TRIGGER substitutes_calls_immutable BEFORE UPDATE ON substitutes.calls
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'player', 'seat', 'kind', 'via', 'task',
                                                      'caller_kind', 'caller_code', 'purpose_kind', 'purpose_ref',
                                                      'input_sha256', 'day', 'month_key', 'created_at');

-- A CLI's headless sign-in from the app (contract §21.13). `code` is the
-- owner's pasted auth code: write-only, handed to the runner once, then NULL.
CREATE TABLE substitutes.logins (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    player            text NOT NULL CHECK (player IN ('gpt', 'gemini')),
    connection_key    text NOT NULL,
    method            text CHECK (method IN ('device_code', 'auth_code')),
    verification_url  text CHECK (verification_url ~ '^https://' AND length(verification_url) <= 2000),
    user_code         text CHECK (length(user_code) <= 64),
    code              text CHECK (length(code) <= 512),
    code_given_at     timestamptz,
    expires_at        timestamptz NOT NULL,
    state             text NOT NULL DEFAULT 'waiting' CHECK (state IN ('waiting', 'done', 'expired', 'failed')),
    status_reason     text CHECK (length(status_reason) <= 300),
    call_id           uuid REFERENCES substitutes.calls (id),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX substitutes_logins_open ON substitutes.logins (player) WHERE state = 'waiting';

-- An ad image or video (contract §21.13): the Claude agent's prompt, the
-- player renders, the hub sets the Persian overlay by code.
CREATE SEQUENCE substitutes.creative_ref_seq;
CREATE TABLE substitutes.creatives (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref               text NOT NULL UNIQUE
                           DEFAULT 'CR-' || lpad(nextval('substitutes.creative_ref_seq')::text, 4, '0'),
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    kind              text NOT NULL CHECK (kind IN ('image', 'video')),
    brief_md          text NOT NULL CHECK (length(brief_md) BETWEEN 1 AND 4000),
    prompt_md         text CHECK (length(prompt_md) <= 8000),
    placement         text NOT NULL CHECK (placement IN (@PLACEMENTS@)),
    aspect            text NOT NULL CHECK (aspect IN ('1:1', '4:5', '9:16', '16:9')),
    duration_s        int CHECK (duration_s BETWEEN 1 AND 10),
    overlay           jsonb CHECK (overlay IS NULL OR jsonb_typeof(overlay) = 'object'),
    composed_file_id  uuid REFERENCES files.files (id),
    file_ids          uuid[] NOT NULL DEFAULT '{}',
    player            text NOT NULL CHECK (player IN ('gpt', 'gemini')),
    model             text NOT NULL CHECK (length(model) BETWEEN 1 AND 80),
    path              text NOT NULL DEFAULT 'web' CHECK (path IN ('web', 'cli', 'api')),
    state             text NOT NULL DEFAULT 'queued'
                           CHECK (state IN ('queued', 'generating', 'review', 'accepted', 'rejected', 'failed')),
    requested_by_kind text NOT NULL CHECK (requested_by_kind IN ('owner', 'agent', 'service')),
    requested_by_code text NOT NULL CHECK (length(requested_by_code) BETWEEN 1 AND 64),
    work_id           uuid REFERENCES work.work (id),
    errand_ref        text CHECK (length(errand_ref) <= 32),
    call_id           uuid REFERENCES substitutes.calls (id),
    review_md         text CHECK (length(review_md) <= 8000),
    owner_note        text CHECK (length(owner_note) <= 2000),
    source            jsonb CHECK (source IS NULL OR jsonb_typeof(source) = 'object'),
    ai_generated      boolean NOT NULL DEFAULT true CHECK (ai_generated),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    version           int NOT NULL DEFAULT 1,
    CHECK (kind = 'video' OR duration_s IS NULL)
);
CREATE INDEX substitutes_creatives_company ON substitutes.creatives (company_id, created_at DESC);
CREATE INDEX substitutes_creatives_call ON substitutes.creatives (call_id) WHERE call_id IS NOT NULL;
CREATE TRIGGER substitutes_creatives_version BEFORE UPDATE ON substitutes.creatives
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
CREATE TRIGGER substitutes_creatives_immutable BEFORE UPDATE ON substitutes.creatives
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'kind', 'brief_md', 'placement',
                                                      'aspect', 'duration_s', 'requested_by_kind',
                                                      'requested_by_code', 'created_at');

-- ========================================================= owner settings ==
ALTER TABLE owner.settings
    ADD COLUMN advisor jsonb NOT NULL
        DEFAULT '{"auto_memo": {"enabled": true, "max_per_day": 3}, "proactive_per_day": 3}'
        CHECK (jsonb_typeof(advisor) = 'object'),
    ADD COLUMN substitutes jsonb NOT NULL
        DEFAULT '{"behind_ratio": 0.4, "creative_default_image": "gpt"}'
        CHECK (jsonb_typeof(substitutes) = 'object');
GRANT UPDATE (advisor, substitutes) ON owner.settings TO hq_api;

-- ===================================================================== work ==
-- What the code that made a work item tells its run: the router task class
-- (advisor_memo, advisor_proactive, ...) and the owner-zone flag (auto/direct).
ALTER TABLE work.work ADD COLUMN run_meta jsonb
    CHECK (run_meta IS NULL OR jsonb_typeof(run_meta) = 'object');
GRANT UPDATE (run_meta) ON work.work TO @APP@;

-- ====================================================================== llm ==
ALTER TABLE llm.connections DROP CONSTRAINT connections_status_check;
ALTER TABLE llm.connections ADD CONSTRAINT connections_status_check
    CHECK (status IN ('enabled', 'disabled', 'quota_exhausted', 'pending_secret', 'verifying', 'ready', 'error'));
ALTER TABLE llm.connections DROP CONSTRAINT connections_kind_check;
ALTER TABLE llm.connections ADD CONSTRAINT connections_kind_check
    CHECK (kind IN ('claude_subscription', 'api', 'fake', 'subscription'));
ALTER TABLE llm.connections ADD COLUMN verified_at timestamptz;
GRANT INSERT (key, kind, provider, display_name, status, status_reason, status_changed_at, secret_ref,
              api_base, models, default_model, pricing, limits, fallback_priority)
    ON llm.connections TO hq_api;
GRANT UPDATE (verified_at) ON llm.connections TO hq_api, hq_llm_writer;
-- The advisor's quota trigger reads the Quota Controller's state (metadata only).
GRANT SELECT ON llm.quota_status TO @APP@;
-- The ledger rows of the substitute calls (contract §21.13: recorded at their
-- equivalent cost; they count against no daily cap or share).
GRANT INSERT ON llm.calls TO @APP@;
CREATE POLICY calls_substitutes_insert ON llm.calls FOR INSERT TO hq_api, hq_worker
    WITH CHECK (company_id = ANY (llm.allowed_company_ids()) AND caller = 'substitutes');
"""


def _connections_sql() -> str:
    """The three substitute accounts (kind subscription; disabled for the
    router, which never routes a Claude run to them) and their web profiles."""
    rows = [
        ("chatgpt-plus", "openai", "ChatGPT Plus (بازیکن ذخیره)", '["gpt-5.5", "gpt-5.3"]', "gpt-5.5"),
        ("gemini-pro", "google", "Google AI Pro (بازیکن ذخیره)", '["gemini-3.8"]', "gemini-3.8"),
        ("deepseek-free", "deepseek", "DeepSeek (رایگان، بازیکن ذخیره)", '["deepseek-chat"]', "deepseek-chat"),
    ]
    values = ",\n".join(
        f"('{k}', 'subscription', '{p}', '{n}', 'disabled', "
        f"'a substitute player: called by seat only, never by the router', '{m}'::jsonb, '{d}')"
        for k, p, n, m, d in rows
    )
    accounts = [
        ("chatgpt-web", "chatgpt.com", "پروفایل مرورگر ChatGPT"),
        ("gemini-web", "gemini.google.com", "پروفایل مرورگر Gemini"),
        ("deepseek-web", "chat.deepseek.com", "پروفایل مرورگر DeepSeek"),
    ]
    acc = ",\n".join(
        f"('{k}', '{s}', '{t}', NULL, '{{\"browse\": {{\"kind\": \"profile\"}}}}'::jsonb)"
        for k, s, t in accounts
    )
    classes = ",\n".join(f"('{k}', false, '{d}')" for k, d in TASK_CLASSES)
    return f"""
        INSERT INTO llm.connections (key, kind, provider, display_name, status, status_reason, models,
                                     default_model)
        VALUES {values}
        ON CONFLICT (key) DO NOTHING;
        INSERT INTO tools.accounts (key, site, title_fa, companies, policy)
        VALUES {acc}
        ON CONFLICT (key) DO NOTHING;
        INSERT INTO llm.task_classes (key, transferable, description)
        VALUES {classes}
        ON CONFLICT (key) DO NOTHING;
    """


def _rls(table: str) -> str:
    name = table.replace(".", "_")
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
        CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
        CREATE TRIGGER {name}_no_delete BEFORE DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
    """


def upgrade() -> None:
    sql = (
        UPGRADE.replace("@APP@", APP_ROLES)
        .replace("@SEATS@", SEATS)
        .replace("@PLAYERS@", PLAYERS)
        .replace("@TRIGGER_KINDS@", TRIGGER_KINDS)
        .replace("@PLACEMENTS@", PLACEMENTS)
    )
    assert not re.search(r"@[A-Z_]+@", sql), "an unreplaced placeholder"
    execute_script(sql)
    grants = [_rls(t) for t in TABLES]
    grants.append(f"GRANT SELECT, INSERT, UPDATE ON {', '.join(TABLES)} TO {APP_ROLES};")
    grants.append(f"GRANT USAGE ON SEQUENCE {', '.join(SEQUENCES)} TO {APP_ROLES};")
    execute_script("\n".join(grants))
    execute_script(_connections_sql())


def downgrade() -> None:
    execute_script(
        """
        DROP POLICY calls_substitutes_insert ON llm.calls;
        REVOKE INSERT ON llm.calls FROM hq_api, hq_worker;
        REVOKE SELECT ON llm.quota_status FROM hq_api, hq_worker;
        REVOKE UPDATE (verified_at) ON llm.connections FROM hq_api, hq_llm_writer;
        REVOKE INSERT ON llm.connections FROM hq_api;
        ALTER TABLE llm.connections DROP COLUMN verified_at;
        -- NOT VALID: connections made since keep their status and kind.
        ALTER TABLE llm.connections DROP CONSTRAINT connections_status_check;
        ALTER TABLE llm.connections ADD CONSTRAINT connections_status_check
            CHECK (status IN ('enabled', 'disabled', 'quota_exhausted')) NOT VALID;
        ALTER TABLE llm.connections DROP CONSTRAINT connections_kind_check;
        ALTER TABLE llm.connections ADD CONSTRAINT connections_kind_check
            CHECK (kind IN ('claude_subscription', 'api', 'fake')) NOT VALID;
        ALTER TABLE work.work DROP COLUMN run_meta;
        ALTER TABLE owner.settings DROP COLUMN advisor, DROP COLUMN substitutes;
        DROP TRIGGER decisions_memo_stale ON cartable.decisions;
        DROP SCHEMA substitutes CASCADE;
        DROP SCHEMA advisor CASCADE;
        """
    )
