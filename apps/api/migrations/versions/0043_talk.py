"""Prompt 23 (contract §32.1-§32.4, §32.7-§32.9): the owner's talk.

- talk.conversations (CV-0001 ...): one conversation of the owner with a
  persona, its mode (consult | work), who is present, its running summary and
  what it cost; talk.turns: every turn, kept forever (the owner's words never
  change once stored; a persona's answer fills in while it streams);
  talk.turn_events: what the SSE stream of one turn sends (text deltas,
  spoken sentences, audio, cards, the end), read by the api's stream route
  while the worker writes them; talk.cards: what a turn offers (an order, an
  ask, a hire, a decision, a planner item, a rule, an automation, minutes,
  an invite) and what running it made; talk.memory: the owner's facts, only
  when the owner says so («یادت باشه»); talk.personas: the owner's choices of
  voice, engine and effort per persona, and the voice a manager was given.
- Full-text search over a turn's text with the Persian normalisation of §5.3
  (core.fa_normalize: ی/ي, ک/ك, ZWNJ).
- RLS: every table carries company_id under FORCE RLS. The owner's
  conversations are holding-level: their rows (and the turns and cards of the
  holding's personas) carry the HOLDING's id, as growth.automations' holding
  rows do, so no company's agent ever reads them; a manager's turns and cards
  carry its own company's id, so its company's scope (its runs) reads only
  its own part of a conversation. The owner's api reads every company.
- The holding secretary (agents/roles/holding_secretary.md) is a system
  employee of the holding (<HOLDING>-HSEC), like the meeting secretary: its
  read tools run through the Tool Gateway under short `talk` runs.
- agents.runs gains the trigger `talk` (a turn's read-only tool steps); the
  long voice sessions of §29.5 gain the purpose `talk`.
- The router's task classes `talk_turn` and `talk_summary` (the router's seed
  file holds the same rows).

Fresh start: conversations, turns, cards, memory and the persona choices stay
(the owner's records); the streams' events go.

Revision ID: 0043
Revises: 0042
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
PERSONA = r"'^([a-z][a-z_]{1,30}|[a-z][a-z0-9_]{1,40}@[A-Z][A-Z0-9]{1,9})$'"
TABLES = (
    "talk.personas",
    "talk.conversations",
    "talk.turns",
    "talk.turn_events",
    "talk.cards",
    "talk.memory",
)
TRIGGERS_BEFORE = "'work', 'message', 'schedule', 'alert', 'meeting'"
PURPOSES_BEFORE = "'order', 'rule', 'message', 'note'"


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
CREATE SCHEMA talk;
GRANT USAGE ON SCHEMA talk TO {APP_ROLES};

-- the router's two task classes of §32 (its seed file holds the same rows)
INSERT INTO llm.task_classes (key, transferable, description)
VALUES ('talk_turn', false,
        'One turn of the owner''s talk with a persona: a strict answer schema, read tools only (contract 32.2)'),
       ('talk_summary', false,
        'A conversation''s running summary every 10 turns, a light model (contract 32.8)')
ON CONFLICT (key) DO NOTHING;

-- a turn's read tools run as a short `talk` run of the persona's employee (§32.2)
ALTER TABLE agents.runs DROP CONSTRAINT runs_trigger_check;
ALTER TABLE agents.runs ADD CONSTRAINT runs_trigger_check
    CHECK (trigger IN ({TRIGGERS_BEFORE}, 'talk'));

-- §29.5 the hub's speech to text for a long turn of the talk (additive)
ALTER TABLE owner.voice_sessions DROP CONSTRAINT voice_sessions_purpose_check;
ALTER TABLE owner.voice_sessions ADD CONSTRAINT voice_sessions_purpose_check
    CHECK (purpose IN ({PURPOSES_BEFORE}, 'talk'));

-- the holding secretary: a system employee of the holding (never hired, rated or starred)
INSERT INTO core.employees (company_id, code, kind, title_fa, title_en, activity, role)
SELECT c.id, c.code || '-HSEC', 'system', 'منشی هلدینگ', 'Holding Secretary', 'sleeping',
       'holding_secretary'
FROM core.companies c WHERE c.kind = 'holding'
ON CONFLICT (code) DO NOTHING;

CREATE FUNCTION talk.pad_ref(prefix text, n bigint, width int) RETURNS text
    LANGUAGE sql IMMUTABLE AS
$$ SELECT prefix || CASE WHEN length(n::text) >= width THEN n::text
                         ELSE lpad(n::text, width, '0') END $$;
GRANT EXECUTE ON FUNCTION talk.pad_ref(text, bigint, int) TO {APP_ROLES};
CREATE SEQUENCE talk.conversation_ref_seq;
GRANT USAGE ON SEQUENCE talk.conversation_ref_seq TO {APP_ROLES};

-- A persona's reads run under a short `talk` run of its employee (the Tool
-- Gateway's run gate needs one; the gate lets a talk run read only, A0). Runs
-- are made only through definer functions, as agents.queue_run makes them;
-- NULL when the employee is not active or is busy in a run of its own.
CREATE FUNCTION talk.open_run(p_employee uuid, p_reason text, p_steps int, p_token_cap bigint,
                              p_ttl_s int) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        e record;
        rid uuid;
        steps int := LEAST(GREATEST(p_steps, 1), 50);
    BEGIN
        SELECT id, company_id, status, role INTO e FROM core.employees WHERE id = p_employee;
        IF NOT FOUND OR e.status <> 'active' OR e.role IS NULL THEN
            RETURN NULL;
        END IF;
        INSERT INTO agents.runs (company_id, employee_id, trigger, reason, state, priority, charter_role,
                                 steps_cap, token_cap, tool_calls_cap, step_tool_calls_cap, started_at,
                                 token_expires_at)
        VALUES (e.company_id, e.id, 'talk', left(COALESCE(p_reason, ''), 200), 'running', 'P1', e.role,
                steps, GREATEST(p_token_cap, 0), LEAST(steps * 3, 500), 3, now(),
                now() + make_interval(secs => LEAST(GREATEST(p_ttl_s, 60), 3600)))
        ON CONFLICT DO NOTHING
        RETURNING id INTO rid;
        RETURN rid;
    END $$;
CREATE FUNCTION talk.close_run(p_run uuid, p_input bigint, p_output bigint, p_cache_read bigint,
                               p_cache_write bigint, p_usd numeric) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    BEGIN
        UPDATE agents.runs
           SET state = 'done', finished_at = now(), updated_at = now(),
               input_tokens = GREATEST(p_input, 0), output_tokens = GREATEST(p_output, 0),
               cache_read_tokens = GREATEST(p_cache_read, 0), cache_write_tokens = GREATEST(p_cache_write, 0),
               equiv_cost_usd = GREATEST(p_usd, 0)
         WHERE id = p_run AND trigger = 'talk' AND state = 'running';
    END $$;
REVOKE ALL ON FUNCTION talk.open_run(uuid, text, int, bigint, int) FROM PUBLIC;
REVOKE ALL ON FUNCTION talk.close_run(uuid, bigint, bigint, bigint, bigint, numeric) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION talk.open_run(uuid, text, int, bigint, int) TO {APP_ROLES};
GRANT EXECUTE ON FUNCTION talk.close_run(uuid, bigint, bigint, bigint, bigint, numeric) TO {APP_ROLES};

-- the owner's choices per persona; a manager's voice, drawn once from the pool
CREATE TABLE talk.personas (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    key         text NOT NULL UNIQUE CHECK (key ~ {PERSONA}),
    engine      text CHECK (engine ~ '^[a-z0-9][a-z0-9._-]{{1,60}}$'),
    voice       text CHECK (length(voice) BETWEEN 1 AND 60),
    rate        numeric(4, 2) CHECK (rate BETWEEN 0.8 AND 1.25),
    effort      text CHECK (effort IN ('low', 'medium', 'high', 'xhigh', 'max')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER personas_immutable BEFORE UPDATE ON talk.personas
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'key', 'created_at');
GRANT SELECT, INSERT ON talk.personas TO {APP_ROLES};
GRANT UPDATE (engine, voice, rate, effort, updated_at) ON talk.personas TO {APP_ROLES};

CREATE TABLE talk.conversations (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ref            text NOT NULL UNIQUE
                   DEFAULT talk.pad_ref('CV-', nextval('talk.conversation_ref_seq'), 4),
    -- the holding's: the owner's conversations are holding-level (see the docstring)
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    title_fa       text NOT NULL DEFAULT '' CHECK (length(title_fa) <= 200),
    persona        text NOT NULL CHECK (persona ~ {PERSONA}),
    present        text[] NOT NULL DEFAULT '{{}}' CHECK (cardinality(present) <= 20),
    mode           text NOT NULL DEFAULT 'consult' CHECK (mode IN ('consult', 'work')),
    turns          int NOT NULL DEFAULT 0 CHECK (turns >= 0),
    summary_fa     text CHECK (length(summary_fa) <= 4000),
    summary_upto   int NOT NULL DEFAULT 0 CHECK (summary_upto >= 0),
    -- the turn number of the last card a persona offered unasked (TALK_CARD_EVERY)
    last_card_n    int NOT NULL DEFAULT 0 CHECK (last_card_n >= 0),
    tokens         bigint NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    usd_equiv      numeric(14, 6) NOT NULL DEFAULT 0 CHECK (usd_equiv >= 0),
    voice_usd      numeric(14, 6) NOT NULL DEFAULT 0 CHECK (voice_usd >= 0),
    started_at     timestamptz NOT NULL DEFAULT now(),
    last_turn_at   timestamptz,
    updated_at     timestamptz NOT NULL DEFAULT now(),
    version        int NOT NULL DEFAULT 1
);
CREATE INDEX conversations_recent ON talk.conversations (last_turn_at DESC NULLS LAST, id);
CREATE INDEX conversations_persona ON talk.conversations (persona, last_turn_at DESC);
CREATE TRIGGER conversations_immutable BEFORE UPDATE ON talk.conversations
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'started_at');
CREATE TRIGGER conversations_version BEFORE UPDATE ON talk.conversations
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
CREATE TRIGGER conversations_no_delete BEFORE DELETE ON talk.conversations
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON talk.conversations TO {APP_ROLES};
GRANT UPDATE (title_fa, persona, present, mode, turns, summary_fa, summary_upto, last_card_n, tokens,
              usd_equiv, voice_usd, last_turn_at, updated_at) ON talk.conversations TO {APP_ROLES};

-- every turn, forever (§32.8); the owner's words never change once stored
CREATE TABLE talk.turns (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid NOT NULL REFERENCES talk.conversations (id),
    -- the holding's; a manager's turn carries its own company's
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    n               int NOT NULL CHECK (n >= 1),
    by_kind         text NOT NULL CHECK (by_kind IN ('owner', 'persona')),
    persona         text CHECK (persona ~ {PERSONA}),
    source          text NOT NULL CHECK (source IN ('typed', 'hold', 'handsfree', 'system')),
    text            text NOT NULL DEFAULT '' CHECK (length(text) <= 20000),
    say_fa          text CHECK (length(say_fa) <= 400),
    show_md         text CHECK (length(show_md) <= 20000),
    audio           jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(audio) = 'array'),
    tokens          jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(tokens) = 'object'),
    voice           jsonb CHECK (voice IS NULL OR jsonb_typeof(voice) = 'object'),
    state           text NOT NULL DEFAULT 'done'
                    CHECK (state IN ('streaming', 'done', 'stopped', 'failed')),
    reason_fa       text CHECK (length(reason_fa) <= 500),
    stop_requested  boolean NOT NULL DEFAULT false,
    client_id       text CHECK (length(client_id) BETWEEN 1 AND 100),
    reply_to        uuid REFERENCES talk.turns (id),
    -- what the code asks of the answer besides answering: one `minutes` card (§32.3)
    directive       text CHECK (directive IN ('minutes')),
    run_id          uuid,
    search          tsvector GENERATED ALWAYS AS (
                        to_tsvector('simple', core.fa_normalize(text || ' ' || COALESCE(show_md, '')))
                    ) STORED,
    at              timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    UNIQUE (conversation_id, n),
    CHECK ((by_kind = 'owner') = (persona IS NULL)),
    CHECK ((state = 'streaming') = (finished_at IS NULL))
);
CREATE UNIQUE INDEX turns_client ON talk.turns (conversation_id, client_id) WHERE client_id IS NOT NULL;
CREATE INDEX turns_search ON talk.turns USING gin (search);
CREATE INDEX turns_open ON talk.turns (at) WHERE state = 'streaming';
CREATE TRIGGER turns_immutable BEFORE UPDATE ON talk.turns
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'conversation_id', 'company_id', 'n', 'by_kind',
                                                      'persona', 'source', 'text', 'client_id', 'reply_to', 'directive',
                                                      'at');
CREATE TRIGGER turns_no_delete BEFORE DELETE ON talk.turns
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON talk.turns TO {APP_ROLES};
GRANT UPDATE (say_fa, show_md, audio, tokens, voice, state, reason_fa, stop_requested, run_id, finished_at)
    ON talk.turns TO {APP_ROLES};

-- what one turn's SSE stream sends, in order (written by the worker, read by the api)
CREATE TABLE talk.turn_events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    turn_id     uuid NOT NULL REFERENCES talk.turns (id),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    seq         int NOT NULL CHECK (seq >= 1),
    type        text NOT NULL CHECK (type IN ('text', 'say', 'audio', 'card', 'invite', 'meter', 'tool',
                                              'done', 'error')),
    data        jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(data) = 'object'),
    at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (turn_id, seq)
);
CREATE TRIGGER turn_events_append_only BEFORE UPDATE OR DELETE ON talk.turn_events
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON talk.turn_events TO {APP_ROLES};

CREATE TABLE talk.cards (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  uuid NOT NULL REFERENCES talk.conversations (id),
    turn_id          uuid NOT NULL REFERENCES talk.turns (id),
    -- the holding's; a manager's card carries its own company's
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    kind             text NOT NULL CHECK (kind IN ('order', 'ask', 'hire', 'decision', 'planner', 'rule',
                                                   'automation', 'minutes', 'invite')),
    title_fa         text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
    body_fa          text NOT NULL DEFAULT '' CHECK (length(body_fa) <= 8000),
    payload          jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(payload) = 'object'),
    state            text NOT NULL DEFAULT 'offered'
                     CHECK (state IN ('offered', 'done', 'dismissed', 'failed')),
    made             text[] NOT NULL DEFAULT '{{}}' CHECK (cardinality(made) <= 50),
    reason_fa        text CHECK (length(reason_fa) <= 500),
    unsolicited      boolean NOT NULL DEFAULT false,
    -- an ask card: the deliverables already posted back into the conversation
    answered         text[] NOT NULL DEFAULT '{{}}' CHECK (cardinality(answered) <= 50),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    version          int NOT NULL DEFAULT 1
);
CREATE INDEX cards_conversation ON talk.cards (conversation_id, created_at);
CREATE INDEX cards_made ON talk.cards USING gin (made);
CREATE TRIGGER cards_immutable BEFORE UPDATE ON talk.cards
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'conversation_id', 'turn_id', 'company_id', 'kind',
                                                      'unsolicited', 'created_at');
CREATE TRIGGER cards_version BEFORE UPDATE ON talk.cards
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
CREATE TRIGGER cards_no_delete BEFORE DELETE ON talk.cards
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON talk.cards TO {APP_ROLES};
GRANT UPDATE (title_fa, body_fa, payload, state, made, reason_fa, answered, updated_at)
    ON talk.cards TO {APP_ROLES};

-- the owner's facts, only when the owner says so (§32.8)
CREATE TABLE talk.memory (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    fact_fa     text NOT NULL CHECK (length(fact_fa) BETWEEN 1 AND 2000),
    turn_id     uuid REFERENCES talk.turns (id),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX memory_recent ON talk.memory (created_at DESC);
CREATE TRIGGER memory_append_only BEFORE UPDATE OR DELETE ON talk.memory
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON talk.memory TO {APP_ROLES};
"""
    + "".join(_rls(t) for t in TABLES)
)

DOWNGRADE = f"""
DROP SCHEMA talk CASCADE;
-- the talk runs and the holding secretary (only talk runs ever named it)
ALTER TABLE agents.runs DISABLE TRIGGER runs_no_delete;
DELETE FROM agents.runs WHERE trigger = 'talk';
ALTER TABLE agents.runs ENABLE TRIGGER runs_no_delete;
DELETE FROM core.employees WHERE role = 'holding_secretary' AND kind = 'system';
ALTER TABLE agents.runs DROP CONSTRAINT runs_trigger_check;
ALTER TABLE agents.runs ADD CONSTRAINT runs_trigger_check CHECK (trigger IN ({TRIGGERS_BEFORE}));
ALTER TABLE owner.voice_sessions DISABLE TRIGGER voice_sessions_no_delete;
DELETE FROM owner.voice_sessions WHERE purpose = 'talk';
ALTER TABLE owner.voice_sessions ENABLE TRIGGER voice_sessions_no_delete;
ALTER TABLE owner.voice_sessions DROP CONSTRAINT voice_sessions_purpose_check;
ALTER TABLE owner.voice_sessions ADD CONSTRAINT voice_sessions_purpose_check
    CHECK (purpose IN ({PURPOSES_BEFORE}));
-- (the task classes stay: ledger rows may name them)
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
