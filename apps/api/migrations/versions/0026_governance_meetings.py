"""Prompt 11, first half (contract §20.1-§20.3): the meeting room, the charter
and its addenda, the four-layer knowledge base. Every table of prompt 11
§1-§3 is made here; the second half (§4-§10: cards, OKR, outcomes, the
authority matrix, risks, the calendar, the batch seal) is 0026_1.

Every table is company-scoped (company_id, FORCE RLS, the once-per-query
policy of 0009). Two reads cross companies on purpose, each by its own
SELECT-only policy and only for rows of the holding company:
  governance.charters  the holding's charter (scope 'holding') for everyone
  knowledge.entries    the holding layer (approved) for everyone
A trigger keeps both honest: a 'holding' row lives in the holding company and
nowhere else, so the extra policy never shows another company's row.

  meetings   types (MeetingType, data), meetings (MT-0001), items (the
             agenda), turns (append-only), claims, whispers (the owner only),
             drafts (resolution drafts and votes), requests (MI-0001: an
             agent's meeting.item for the next meeting of a type)
  governance charters (versioned, append-only but for the seal)
  knowledge  entries (K-0001, versioned rows), support_entries (a VIEW over
             support.kb_articles: the company layer's kind `support`, never a
             copy)

Decision kinds gain meeting_resolution, charter_amendment and
knowledge_entry (appended to whatever the constraint holds, NOT VALID, so
0026_1 can append its own and validate them all at the head); agents.runs.trigger gains 'meeting'; meetings.queue_turn()
queues a meeting turn (or the secretary's minutes run: the one system role
that runs, contract §20.1).

Revision ID: 0026
Revises: 0025
"""

from __future__ import annotations

import re

from hq_api.migration_sql import execute_script

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
HOLDING = (
    "(SELECT h.id FROM core.companies h WHERE h.kind = 'holding' ORDER BY h.created_at LIMIT 1)"
)
NEW_KINDS = ("meeting_resolution", "charter_amendment", "knowledge_entry")
TYPES = "'board', 'company', 'standup', 'war_room', 'postmortem', 'strategy'"

TABLES = (
    "meetings.types",
    "meetings.meetings",
    "meetings.items",
    "meetings.turns",
    "meetings.claims",
    "meetings.whispers",
    "meetings.drafts",
    "meetings.requests",
    "governance.charters",
    "knowledge.entries",
)
APPEND_ONLY = ("meetings.whispers",)
SEQUENCES = (
    "meetings.meeting_ref_seq",
    "meetings.request_ref_seq",
    "knowledge.entry_ref_seq",
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


UPGRADE = r"""
CREATE SCHEMA IF NOT EXISTS meetings;
CREATE SCHEMA IF NOT EXISTS governance;
GRANT USAGE ON SCHEMA meetings, governance, knowledge TO @APP@;
CREATE SEQUENCE meetings.meeting_ref_seq;
CREATE SEQUENCE meetings.request_ref_seq;
CREATE SEQUENCE knowledge.entry_ref_seq;

-- A row that says it is the holding's (a charter of scope 'holding', a
-- knowledge entry of layer 'holding') must live in the holding company, and a
-- row of the holding company must say so: the holding-wide SELECT policy then
-- never shows an operating company's row. SECURITY DEFINER: core.companies is
-- read whatever the caller's scope.
CREATE FUNCTION governance.holding_row_check() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        is_holding boolean;
        says_holding boolean;
    BEGIN
        SELECT c.kind = 'holding' INTO is_holding FROM core.companies c WHERE c.id = NEW.company_id;
        IF TG_TABLE_NAME = 'charters' THEN
            says_holding := NEW.scope = 'holding';
            IF NOT says_holding AND NEW.scope IS DISTINCT FROM
                    (SELECT c.code FROM core.companies c WHERE c.id = NEW.company_id) THEN
                RAISE EXCEPTION 'governance.charters: an addendum lives in its own company'
                    USING ERRCODE = 'HQV01';
            END IF;
        ELSE
            says_holding := NEW.layer = 'holding';
        END IF;
        IF says_holding IS DISTINCT FROM COALESCE(is_holding, false) THEN
            RAISE EXCEPTION '%.%: the holding layer lives in the holding company only',
                TG_TABLE_SCHEMA, TG_TABLE_NAME USING ERRCODE = 'HQV01';
        END IF;
        RETURN NEW;
    END $$;
REVOKE ALL ON FUNCTION governance.holding_row_check() FROM PUBLIC;

-- =============================================================== meetings ==
-- MeetingType: data the owner edits (🔏 meetings.settings); one row per key.
CREATE TABLE meetings.types (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    key              text NOT NULL CHECK (key IN (@TYPES@)),
    title_fa         text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
    schedule         text CHECK (length(schedule) BETWEEN 6 AND 200),   -- RRULE; null = opened by an event
    calendar         text NOT NULL DEFAULT 'gregorian' CHECK (calendar IN ('gregorian', 'jalali')),
    members          jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(members) = 'object'),
    max_rounds       int NOT NULL DEFAULT 2 CHECK (max_rounds BETWEEN 1 AND 3),
    max_speakers     int NOT NULL DEFAULT 6 CHECK (max_speakers BETWEEN 2 AND 8),
    budget_tokens    bigint CHECK (budget_tokens >= 0),               -- null = no meeting cap
    turn_cap_tokens  int NOT NULL DEFAULT 6000 CHECK (turn_cap_tokens BETWEEN 500 AND 50000),
    owner_presence   text NOT NULL DEFAULT 'summary' CHECK (owner_presence IN ('live', 'summary', 'audio')),
    model_summary    boolean NOT NULL DEFAULT false,                  -- standup: the secretary's summary
    enabled          boolean NOT NULL DEFAULT true,
    updated_by_kind  text NOT NULL DEFAULT 'service' CHECK (updated_by_kind IN ('owner', 'service')),
    updated_by_code  text NOT NULL DEFAULT 'seed' CHECK (length(updated_by_code) <= 64),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    version          int NOT NULL DEFAULT 1,
    UNIQUE (company_id, key),
    CHECK (budget_tokens IS NOT NULL OR key = 'war_room')
);
CREATE TRIGGER meetings_types_immutable BEFORE UPDATE ON meetings.types
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'key', 'created_at');
CREATE TRIGGER meetings_types_version BEFORE UPDATE ON meetings.types
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- Meeting (MT-0001). company_id: the holding's for board and strategy.
CREATE TABLE meetings.meetings (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    ref              text NOT NULL UNIQUE DEFAULT 'MT-' || lpad(nextval('meetings.meeting_ref_seq')::text, 4, '0')
                          CHECK (ref ~ '^MT-[0-9]{4,}$'),
    type             text NOT NULL CHECK (type IN (@TYPES@)),
    department       text CHECK (department ~ '^[A-Z][A-Z0-9]{1,11}$'),      -- a standup's
    title_fa         text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    starts_at        timestamptz NOT NULL,
    state            text NOT NULL DEFAULT 'scheduled'
                          CHECK (state IN ('scheduled', 'prep', 'live', 'closing', 'ended', 'cancelled')),
    mode             text NOT NULL DEFAULT 'discussion' CHECK (mode IN ('discussion', 'written')),
    budget_cap       bigint CHECK (budget_cap >= 0),          -- null: a war room (no meeting cap)
    estimate         bigint NOT NULL DEFAULT 0 CHECK (estimate >= 0),
    reserved         bigint NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    used             bigint NOT NULL DEFAULT 0 CHECK (used >= 0),
    reserved_on      date,                                    -- the UTC day of the reservation
    trimmed_fa       text CHECK (length(trimmed_fa) <= 2000),
    owner_presence   text NOT NULL DEFAULT 'summary' CHECK (owner_presence IN ('live', 'summary', 'audio')),
    settings         jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(settings) = 'object'),
    participants     jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(participants) = 'array'),
    origin           text NOT NULL DEFAULT 'schedule' CHECK (origin IN ('schedule', 'owner', 'incident')),
    slot_key         text CHECK (length(slot_key) BETWEEN 3 AND 80),      -- one meeting per scheduled slot
    incident_id      uuid,
    incident_ref     text CHECK (incident_ref ~ '^I-[0-9]{4,}$'),
    pending          jsonb CHECK (pending IS NULL OR jsonb_typeof(pending) = 'object'),  -- the turn in flight
    pending_run_id   uuid,
    minutes_ref      text CHECK (minutes_ref ~ '^O-[0-9]{6,}$'),
    summary_md       text CHECK (length(summary_md) <= 8000),
    digest_sha256    text CHECK (digest_sha256 ~ '^[0-9a-f]{64}$'),       -- a standup's records
    end_reason       text CHECK (end_reason ~ '^[a-z][a-z0-9_]{1,40}$'),
    started_at       timestamptz,
    ended_at         timestamptz,
    created_by_kind  text NOT NULL DEFAULT 'service' CHECK (created_by_kind IN ('owner', 'agent', 'service')),
    created_by_code  text NOT NULL DEFAULT 'meetings' CHECK (length(created_by_code) <= 64),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    version          int NOT NULL DEFAULT 1,
    UNIQUE (company_id, id),
    UNIQUE (company_id, slot_key),
    CHECK ((state IN ('ended', 'cancelled')) = (ended_at IS NOT NULL))
);
CREATE UNIQUE INDEX meetings_one_war_room ON meetings.meetings (incident_id) WHERE type = 'war_room';
CREATE UNIQUE INDEX meetings_one_postmortem ON meetings.meetings (incident_id) WHERE type = 'postmortem';
CREATE INDEX meetings_due ON meetings.meetings (state, starts_at);
CREATE INDEX meetings_company ON meetings.meetings (company_id, starts_at DESC);
CREATE INDEX meetings_pending_run ON meetings.meetings (pending_run_id) WHERE pending_run_id IS NOT NULL;
CREATE INDEX meetings_reserved_day ON meetings.meetings (reserved_on) WHERE reserved > 0;
CREATE TRIGGER meetings_meetings_immutable BEFORE UPDATE ON meetings.meetings
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'type', 'department', 'origin',
                                                      'slot_key', 'created_by_kind', 'created_by_code', 'created_at');
-- An alert's war room takes the incident that comes after it; never another.
CREATE FUNCTION meetings.incident_once() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.incident_id IS NOT NULL AND NEW.incident_id IS DISTINCT FROM OLD.incident_id THEN
            RAISE EXCEPTION 'meeting %: the incident is set once', OLD.ref USING ERRCODE = 'HQI01';
        END IF;
        RETURN NEW;
    END $$;
CREATE TRIGGER meetings_meetings_incident BEFORE UPDATE ON meetings.meetings
    FOR EACH ROW EXECUTE FUNCTION meetings.incident_once();
CREATE TRIGGER meetings_meetings_version BEFORE UPDATE ON meetings.meetings
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
-- An ended or cancelled meeting never changes again.
CREATE FUNCTION meetings.final() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.state IN ('ended', 'cancelled') THEN
            RAISE EXCEPTION 'meeting % is %', OLD.ref, OLD.state USING ERRCODE = 'HQI01';
        END IF;
        RETURN NEW;
    END $$;
CREATE TRIGGER meetings_meetings_final BEFORE UPDATE ON meetings.meetings
    FOR EACH ROW EXECUTE FUNCTION meetings.final();

-- MeetingItem: the agenda, built by code at T-24h; the owner reorders or skips.
CREATE TABLE meetings.items (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    meeting_id   uuid NOT NULL,
    n            int NOT NULL CHECK (n BETWEEN 1 AND 50),
    title_fa     text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    brief_md     text NOT NULL DEFAULT '' CHECK (length(brief_md) <= 8000),
    sources      jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(sources) = 'array'),
    time_box_min int NOT NULL DEFAULT 10 CHECK (time_box_min BETWEEN 1 AND 120),
    importance   text NOT NULL DEFAULT 'normal' CHECK (importance IN ('high', 'normal', 'low')),
    origin       text NOT NULL DEFAULT 'code' CHECK (origin IN ('owner', 'agent', 'code')),
    owner_code   text CHECK (length(owner_code) <= 64),          -- who drafts the resolution
    speakers     jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(speakers) = 'array'),   -- devil last
    devil        text CHECK (length(devil) <= 64),
    writers      jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(writers) = 'array'),    -- written statements
    rounds       int NOT NULL DEFAULT 2 CHECK (rounds BETWEEN 0 AND 3),   -- after the trim
    round        int NOT NULL DEFAULT 0 CHECK (round BETWEEN 0 AND 3),
    state        text NOT NULL DEFAULT 'waiting'
                      CHECK (state IN ('waiting', 'round_1', 'round_2', 'done', 'skipped')),
    request_id   uuid,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    version      int NOT NULL DEFAULT 1,
    UNIQUE (meeting_id, n) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (company_id, meeting_id) REFERENCES meetings.meetings (company_id, id)
);
CREATE TRIGGER meetings_items_immutable BEFORE UPDATE ON meetings.items
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'meeting_id', 'origin', 'request_id',
                                                      'created_at');
CREATE TRIGGER meetings_items_version BEFORE UPDATE ON meetings.items
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- Turn: never changed but for its tokens. kind 'written' = a company's written statement (code,
-- from its records: no model); 'owner' = the owner's word (jumps the queue).
CREATE TABLE meetings.turns (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL REFERENCES core.companies (id),
    meeting_id    uuid NOT NULL,
    item_id       uuid REFERENCES meetings.items (id),
    n             int NOT NULL CHECK (n >= 1),
    round         int NOT NULL DEFAULT 0 CHECK (round BETWEEN 0 AND 3),
    speaker_kind  text NOT NULL CHECK (speaker_kind IN ('owner', 'agent', 'service')),
    speaker_code  text NOT NULL CHECK (length(speaker_code) <= 64),
    kind          text NOT NULL CHECK (kind IN ('statement', 'challenge', 'vote', 'owner', 'written')),
    statement_md  text NOT NULL DEFAULT '' CHECK (length(statement_md) <= 8000),
    draft_md      text CHECK (length(draft_md) <= 8000),
    stance        jsonb CHECK (stance IS NULL OR jsonb_typeof(stance) = 'object'),
    file_id       uuid,                                          -- the owner's voice note
    run_id        uuid,
    tokens        bigint NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    at            timestamptz NOT NULL DEFAULT now(),
    UNIQUE (meeting_id, n),
    FOREIGN KEY (company_id, meeting_id) REFERENCES meetings.meetings (company_id, id)
);
CREATE INDEX meetings_turns_item ON meetings.turns (item_id, n);
CREATE INDEX meetings_turns_run ON meetings.turns (run_id) WHERE run_id IS NOT NULL;
-- A turn never changes but for its tokens (known when its run ends).
CREATE TRIGGER meetings_turns_immutable BEFORE UPDATE ON meetings.turns
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'meeting_id', 'item_id', 'n', 'round',
                                                      'speaker_kind', 'speaker_code', 'kind', 'statement_md',
                                                      'draft_md', 'stance', 'file_id', 'run_id', 'at');

-- Claim: every claim of a turn with its source and the code's verdict.
CREATE TABLE meetings.claims (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    meeting_id     uuid NOT NULL,
    item_id        uuid REFERENCES meetings.items (id),
    turn_id        uuid NOT NULL REFERENCES meetings.turns (id),
    n              int NOT NULL DEFAULT 1 CHECK (n BETWEEN 1 AND 50),   -- its place in the turn
    text_fa        text NOT NULL CHECK (length(text_fa) BETWEEN 1 AND 1000),
    source_kind    text CHECK (source_kind ~ '^[a-z][a-z_]{1,20}$'),
    source_ref     text CHECK (length(source_ref) BETWEEN 1 AND 80),
    status         text NOT NULL CHECK (status IN ('sourced', 'unsourced', 'challenged', 'withdrawn')),
    check_note     text CHECK (check_note ~ '^[a-z][a-z_]{1,40}$'),     -- why unsourced
    challenged_by  uuid REFERENCES meetings.turns (id),
    at             timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, meeting_id) REFERENCES meetings.meetings (company_id, id),
    CHECK (status <> 'sourced' OR (source_kind IS NOT NULL AND source_ref IS NOT NULL))
);
CREATE INDEX meetings_claims_item ON meetings.claims (item_id, at);
CREATE TRIGGER meetings_claims_immutable BEFORE UPDATE ON meetings.claims
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'meeting_id', 'item_id', 'turn_id',
                                                      'n', 'text_fa', 'source_kind', 'source_ref', 'check_note',
                                                      'at');
-- A claim the code refused never becomes sourced later.
CREATE FUNCTION meetings.claim_status() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.status = 'sourced' AND OLD.status <> 'sourced' THEN
            RAISE EXCEPTION 'claim %: % never becomes sourced', OLD.id, OLD.status USING ERRCODE = 'HQV01';
        END IF;
        RETURN NEW;
    END $$;
CREATE TRIGGER meetings_claims_status BEFORE UPDATE ON meetings.claims
    FOR EACH ROW EXECUTE FUNCTION meetings.claim_status();

-- Whisper: the advisor's note to the owner, append-only, never in a speaker's context.
CREATE TABLE meetings.whispers (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    meeting_id  uuid NOT NULL,
    item_id     uuid NOT NULL REFERENCES meetings.items (id),
    round       int NOT NULL CHECK (round BETWEEN 1 AND 3),
    text_md     text NOT NULL CHECK (length(text_md) BETWEEN 1 AND 4000),
    sources     jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(sources) = 'array'),
    run_id      uuid,
    at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (item_id, round),                                    -- at most one per item and round
    FOREIGN KEY (company_id, meeting_id) REFERENCES meetings.meetings (company_id, id)
);

-- Draft: one resolution draft per item (by its owner) and the votes on it.
CREATE TABLE meetings.drafts (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    meeting_id     uuid NOT NULL,
    item_id        uuid NOT NULL UNIQUE REFERENCES meetings.items (id),
    turn_id        uuid NOT NULL REFERENCES meetings.turns (id),
    text_md        text NOT NULL CHECK (length(text_md) BETWEEN 1 AND 8000),
    proposer_code  text NOT NULL CHECK (length(proposer_code) <= 64),
    votes          jsonb NOT NULL DEFAULT '{"support": 0, "oppose": 0, "abstain": 0}'
                        CHECK (jsonb_typeof(votes) = 'object'),
    decision_ref   text CHECK (decision_ref ~ '^D-[0-9]{6,}$'),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    version        int NOT NULL DEFAULT 1,
    FOREIGN KEY (company_id, meeting_id) REFERENCES meetings.meetings (company_id, id)
);
CREATE TRIGGER meetings_drafts_immutable BEFORE UPDATE ON meetings.drafts
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'meeting_id', 'item_id', 'turn_id',
                                                      'text_md', 'proposer_code', 'created_at');
CREATE TRIGGER meetings_drafts_version BEFORE UPDATE ON meetings.drafts
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- MI-0001: an agent's item for the next meeting of a type (meeting.item); the
-- row is the requester's company's; prep places it on the agenda.
CREATE TABLE meetings.requests (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         uuid NOT NULL REFERENCES core.companies (id),
    ref                text NOT NULL UNIQUE DEFAULT 'MI-' || lpad(nextval('meetings.request_ref_seq')::text, 4, '0')
                            CHECK (ref ~ '^MI-[0-9]{4,}$'),
    type               text NOT NULL CHECK (type IN ('board', 'company', 'strategy', 'postmortem')),
    for_company_id     uuid NOT NULL REFERENCES core.companies (id),   -- the meeting's company
    title_fa           text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    brief_md           text NOT NULL DEFAULT '' CHECK (length(brief_md) <= 8000),
    sources            jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(sources) = 'array'),
    by_kind            text NOT NULL CHECK (by_kind IN ('agent', 'service')),
    by_code            text NOT NULL CHECK (length(by_code) <= 64),
    status             text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'placed', 'dropped')),
    meeting_ref        text CHECK (meeting_ref ~ '^MT-[0-9]{4,}$'),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX meetings_requests_open ON meetings.requests (type, for_company_id) WHERE status = 'open';
CREATE TRIGGER meetings_requests_immutable BEFORE UPDATE ON meetings.requests
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'type', 'for_company_id',
                                                      'title_fa', 'brief_md', 'sources', 'by_kind', 'by_code',
                                                      'created_at');

-- Queue one meeting turn (agents.runs, trigger 'meeting'). Like
-- agents.queue_run, but the one system role that runs (the secretary, its
-- minutes) may be queued; anyone else inactive, charterless or a system
-- employee is not. NULL when the employee already has a run queued without
-- work or thread (the meeting asks again on its next tick).
CREATE FUNCTION meetings.queue_turn(p_employee uuid, p_reason text, p_priority text) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        e record;
        rid uuid;
    BEGIN
        SELECT id, company_id, kind, status, role INTO e FROM core.employees WHERE id = p_employee;
        IF NOT FOUND OR e.status <> 'active' OR e.role IS NULL
           OR (e.kind = 'system' AND e.role <> 'secretary') THEN
            RETURN NULL;
        END IF;
        -- A queued turn no meeting waits for any more (it moved on, it ended) is
        -- finished first: it never runs and never blocks the next turn.
        UPDATE agents.runs r SET state = 'failed', finished_at = now(), error_code = 'meeting_moved_on'
         WHERE r.employee_id = e.id AND r.state = 'queued' AND r.trigger = 'meeting'
           AND NOT EXISTS (SELECT 1 FROM meetings.meetings m WHERE m.pending_run_id = r.id);
        INSERT INTO agents.runs (company_id, employee_id, trigger, reason, priority)
        VALUES (e.company_id, e.id, 'meeting', left(COALESCE(p_reason, ''), 200), COALESCE(p_priority, 'P2'))
        ON CONFLICT (employee_id, COALESCE(work_id, '00000000-0000-0000-0000-000000000000'::uuid),
                     COALESCE(thread_id, '00000000-0000-0000-0000-000000000000'::uuid))
            WHERE state = 'queued' DO NOTHING
        RETURNING id INTO rid;
        RETURN rid;
    END $$;
REVOKE ALL ON FUNCTION meetings.queue_turn(uuid, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION meetings.queue_turn(uuid, text, text) TO @APP@;

-- ============================================================ governance ==
-- Charter and addenda (contract §20.2): versioned; a version never changes
-- but for its seal (proposed -> sealed -> superseded, proposed -> superseded).
CREATE TABLE governance.charters (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    scope            text NOT NULL CHECK (scope = 'holding' OR scope ~ '^[A-Z][A-Z0-9]{1,9}$'),
    version          int NOT NULL CHECK (version >= 1),
    status           text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'sealed', 'superseded')),
    body_md          text NOT NULL CHECK (length(body_md) BETWEEN 1 AND 6000),
    red_lines        jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(red_lines) = 'array'),
    body_sha256      text NOT NULL CHECK (body_sha256 ~ '^[0-9a-f]{64}$'),
    source           text NOT NULL CHECK (source IN ('seed', 'owner', 'decision')),
    decision_ref     text CHECK (decision_ref ~ '^D-[0-9]{6,}$'),
    created_by_kind  text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
    created_by_code  text NOT NULL CHECK (length(created_by_code) <= 64),
    created_at       timestamptz NOT NULL DEFAULT now(),
    sealed_at        timestamptz,
    sealed_by_kind   text CHECK (sealed_by_kind IN ('owner')),
    sealed_by_code   text CHECK (length(sealed_by_code) <= 64),
    seal_step_up_id  uuid,
    superseded_at    timestamptz,
    UNIQUE (scope, version),
    CHECK (scope = 'holding' OR length(body_md) <= 3000),
    CHECK (status <> 'proposed' OR (sealed_at IS NULL AND superseded_at IS NULL)),
    CHECK (status <> 'superseded' OR superseded_at IS NOT NULL),
    CHECK (status <> 'sealed' OR (sealed_at IS NOT NULL AND sealed_by_kind = 'owner' AND superseded_at IS NULL))
);
CREATE UNIQUE INDEX governance_charters_one_sealed ON governance.charters (scope) WHERE status = 'sealed';
CREATE TRIGGER governance_charters_holding BEFORE INSERT ON governance.charters
    FOR EACH ROW EXECUTE FUNCTION governance.holding_row_check();
CREATE TRIGGER governance_charters_immutable BEFORE UPDATE ON governance.charters
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'scope', 'version', 'body_md',
                                                      'red_lines', 'body_sha256', 'source', 'decision_ref',
                                                      'created_by_kind', 'created_by_code', 'created_at');
CREATE FUNCTION governance.charter_status() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.status = 'superseded'
           OR (OLD.status = 'sealed' AND NEW.status NOT IN ('sealed', 'superseded'))
           OR (OLD.status = 'sealed' AND NEW.status = 'sealed'
               AND (NEW.sealed_at, NEW.sealed_by_code, NEW.seal_step_up_id)
                   IS DISTINCT FROM (OLD.sealed_at, OLD.sealed_by_code, OLD.seal_step_up_id)) THEN
            RAISE EXCEPTION 'charter %@%: % -> % is not a transition', OLD.scope, OLD.version, OLD.status, NEW.status
                USING ERRCODE = 'HQV01';
        END IF;
        RETURN NEW;
    END $$;
CREATE TRIGGER governance_charters_status BEFORE UPDATE ON governance.charters
    FOR EACH ROW EXECUTE FUNCTION governance.charter_status();

-- ============================================================= knowledge ==
-- KnowledgeEntry (contract §20.3): the holding, company and department
-- layers (the employee layer is core.employee_memory; support articles stay
-- in support.kb_articles, seen through knowledge.support_entries). Sources and
-- an expiry are required; the longest expiry by kind is the database's too.
CREATE TABLE knowledge.entries (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    ref               text NOT NULL DEFAULT 'K-' || lpad(nextval('knowledge.entry_ref_seq')::text, 4, '0')
                           CHECK (ref ~ '^K-[0-9]{4,}$'),
    version           int NOT NULL DEFAULT 1 CHECK (version >= 1),
    layer             text NOT NULL CHECK (layer IN ('holding', 'company', 'department')),
    department        text CHECK (department ~ '^[A-Z][A-Z0-9]{1,11}$'),
    kind              text NOT NULL CHECK (kind IN ('principle', 'policy', 'fact', 'faq', 'playbook')),
    title_fa          text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    body_md           text NOT NULL CHECK (length(body_md) BETWEEN 1 AND 20000),
    sources           jsonb NOT NULL CHECK (jsonb_typeof(sources) = 'array' AND jsonb_array_length(sources) BETWEEN 1 AND 20),
    valid_until       date NOT NULL,
    status            text NOT NULL DEFAULT 'draft'
                           CHECK (status IN ('draft', 'in_review', 'approved', 'expired', 'retired')),
    review            jsonb CHECK (review IS NULL OR jsonb_typeof(review) = 'object'),
    approved_by_kind  text CHECK (approved_by_kind IN ('owner', 'agent')),
    approved_by_code  text CHECK (length(approved_by_code) <= 64),
    approved_at       timestamptz,
    decision_ref      text CHECK (decision_ref ~ '^D-[0-9]{6,}$'),     -- a holding entry's card
    review_work_ref   text CHECK (review_work_ref ~ '^W-[0-9]{6,}$'),  -- the 14-day review work
    expired_at        timestamptz,
    retired_at        timestamptz,
    created_by_kind   text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
    created_by_code   text NOT NULL CHECK (length(created_by_code) <= 64),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    search            text GENERATED ALWAYS AS (core.fa_normalize(title_fa || ' ' || body_md)) STORED,
    UNIQUE (ref, version),
    CHECK ((layer = 'department') = (department IS NOT NULL)),
    CHECK (status <> 'approved' OR approved_at IS NOT NULL),
    CHECK (valid_until <= (created_at AT TIME ZONE 'UTC')::date
           + CASE kind WHEN 'fact' THEN 90 WHEN 'faq' THEN 180 WHEN 'principle' THEN 730 ELSE 365 END)
);
CREATE UNIQUE INDEX knowledge_entries_one_approved ON knowledge.entries (ref) WHERE status = 'approved';
CREATE INDEX knowledge_entries_list ON knowledge.entries (company_id, layer, kind, status);
CREATE INDEX knowledge_entries_expiry ON knowledge.entries (valid_until) WHERE status = 'approved';
CREATE INDEX knowledge_entries_search ON knowledge.entries USING gin (search gin_trgm_ops);
CREATE TRIGGER knowledge_entries_ref BEFORE INSERT ON knowledge.entries
    FOR EACH ROW EXECUTE FUNCTION support.ref_stays_in_company();
CREATE TRIGGER knowledge_entries_holding BEFORE INSERT ON knowledge.entries
    FOR EACH ROW EXECUTE FUNCTION governance.holding_row_check();
CREATE TRIGGER knowledge_entries_immutable BEFORE UPDATE ON knowledge.entries
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'version', 'layer', 'department',
                                                      'kind', 'title_fa', 'body_md', 'sources', 'valid_until',
                                                      'created_by_kind', 'created_by_code', 'created_at');
-- draft -> in_review -> approved | draft (changes) | retired (rejected);
-- approved -> expired | retired; expired -> retired. Nothing comes back.
CREATE FUNCTION knowledge.entry_status() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
               (OLD.status = 'draft' AND NEW.status IN ('in_review', 'approved', 'retired'))
            OR (OLD.status = 'in_review' AND NEW.status IN ('draft', 'approved', 'retired'))
            OR (OLD.status = 'approved' AND NEW.status IN ('expired', 'retired'))
            OR (OLD.status = 'expired' AND NEW.status = 'retired')) THEN
            RAISE EXCEPTION 'knowledge %@%: % -> % is not a transition', OLD.ref, OLD.version, OLD.status, NEW.status
                USING ERRCODE = 'HQV01';
        END IF;
        NEW.updated_at := now();
        RETURN NEW;
    END $$;
CREATE TRIGGER knowledge_entries_status BEFORE UPDATE ON knowledge.entries
    FOR EACH ROW EXECUTE FUNCTION knowledge.entry_status();

-- The support articles of prompt 10 in the company layer (kind 'support'):
-- a view, read with the caller's RLS; edited and approved only at /support/kb.
CREATE VIEW knowledge.support_entries WITH (security_invoker = true) AS
    SELECT a.id, a.company_id, a.ref, a.version, 'company'::text AS layer, NULL::text AS department,
           'support'::text AS kind, a.question_fa AS title_fa, a.answer_md AS body_md,
           jsonb_build_array(jsonb_build_object('kind', 'support_article',
                                                'ref', a.ref || '@' || a.version,
                                                'note', a.source ->> 'kind')) AS sources,
           (a.expires_at AT TIME ZONE 'UTC')::date AS valid_until,
           CASE a.status WHEN 'proposed' THEN 'in_review' ELSE a.status END AS status,
           a.approved_at, a.proposed_by_kind AS created_by_kind, a.proposed_by_code AS created_by_code,
           a.created_at, a.updated_at,
           support.kb_search_text(a.question_fa, a.variants) || ' ' || core.fa_normalize(a.answer_md) AS search
    FROM support.kb_articles a;
GRANT SELECT ON knowledge.support_entries TO @APP@;

-- ========================================================= agents.runs ==
ALTER TABLE agents.runs DROP CONSTRAINT runs_trigger_check;
ALTER TABLE agents.runs ADD CONSTRAINT runs_trigger_check
    CHECK (trigger IN ('work', 'message', 'schedule', 'alert', 'meeting'));
"""

HOLDING_READ = f"""
-- The holding's charter and its approved knowledge are read by every company.
CREATE POLICY governance_charters_holding_read ON governance.charters FOR SELECT TO {APP_ROLES}
    USING (scope = 'holding' AND company_id = {HOLDING});
CREATE POLICY knowledge_entries_holding_read ON knowledge.entries FOR SELECT TO {APP_ROLES}
    USING (layer = 'holding' AND status = 'approved' AND company_id = {HOLDING});
"""


def _kinds_sql(add: tuple[str, ...], drop: tuple[str, ...], valid: bool) -> str:
    """Rewrite decisions_kind_check from the kinds it holds now (plus `add`,
    minus `drop`): an earlier or a later migration's kinds are kept."""
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
    sql = UPGRADE.replace("@APP@", APP_ROLES).replace("@TYPES@", TYPES)
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
    grants.append(HOLDING_READ)
    execute_script("\n".join(grants))
    execute_script(_kinds_sql(NEW_KINDS, (), valid=False))  # 0026_1 (the head) validates


def downgrade() -> None:
    execute_script(
        _kinds_sql((), NEW_KINDS, valid=False)
        + """
        -- NOT VALID: meeting runs made since stay.
        ALTER TABLE agents.runs DROP CONSTRAINT runs_trigger_check;
        ALTER TABLE agents.runs ADD CONSTRAINT runs_trigger_check
            CHECK (trigger IN ('work', 'message', 'schedule', 'alert')) NOT VALID;
        DROP VIEW knowledge.support_entries;
        DROP TABLE knowledge.entries;
        DROP FUNCTION knowledge.entry_status();
        DROP SEQUENCE knowledge.entry_ref_seq;
        DROP TABLE governance.charters;
        DROP FUNCTION governance.charter_status();
        DROP FUNCTION governance.holding_row_check();
        DROP SCHEMA meetings CASCADE;
        -- governance is shared with 0026_1, which is downgraded first: drop it
        -- only when nothing is left in it.
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                           WHERE n.nspname = 'governance')
               AND NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                               WHERE n.nspname = 'governance') THEN
                DROP SCHEMA governance;
            END IF;
        END $$;
        """
    )
