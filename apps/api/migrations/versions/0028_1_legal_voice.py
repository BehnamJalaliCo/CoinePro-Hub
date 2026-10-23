"""Prompt 13, the legal and voice half (contract §22.3, §22.4, §22.6, §22.7):
the holding's legal counsel and the hub's voice registry.

New schema `legal` (and `media`, shared with the media studio's migration:
created only if it is not there yet). Every table carries company_id under
FORCE RLS (the once-per-query policy of 0009), no row is ever deleted:

  legal.cases          LC-0001: one matter of one company (company_id = the
                       company the case is about; the holding's own matters
                       are the holding's), its counsel, status and deadlines
  legal.case_events    the case's timeline (append-only)
  legal.emails         every email of a case: the counsel's drafts (sealed by
                       the owner on their digest, sent once) and the replies
                       the poller matched (masked); the message itself never
                       changes after it is written (a change is a new draft)
  legal.mailbox        the poller's cursor on the holding mailbox (holding
                       only; no address, no secret: those are the `mail`
                       service account's)
  media.voices         the voice registry (holding only): every engine and
                       speaker pair, its licence, its measured RTF and peak
                       memory, the owner's blind score, and at most one active
  media.voice_samples  a bake-off sample: one fixed script spoken by one
                       voice, its audio file and its measurement (append-only)
  media.speech_jobs    the TTS one-shot's second queue: bake-off samples and
                       the narration of a media item (briefings keep theirs)
  media.voice_references the owner's own recorded voice (holding only; one
                       current, older ones superseded)

Also: decision kind `email_send` (the CHECK rewritten from the kinds it holds,
NOT VALID; the head validates); thread kind `legal` and code `L` (the owner's
thread with HQ-LGL; an owner message there wakes it at P2, like A, N and P);
task classes `legal_case` and `legal_email` (never on another provider).

Revision ID: 0028_1
Revises: 0027_1 (the parent re-chains it after the media studio's 0028)
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0028_1"
down_revision = "0027_1"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"

TABLES = (
    "legal.cases",
    "legal.case_events",
    "legal.emails",
    "legal.mailbox",
    "media.voices",
    "media.voice_samples",
    "media.speech_jobs",
    "media.voice_references",
)
APPEND_ONLY = ("legal.case_events", "media.voice_samples")
SEQUENCES = ("legal.case_ref_seq",)
THREAD_CODE_OLD = "^(A|N|P|[A-Z][A-Z0-9]{1,9}(-[A-Z0-9]+){1,2})$"
THREAD_CODE = "^(A|N|P|L|[A-Z][A-Z0-9]{1,9}(-[A-Z0-9]+){1,2})$"
TASK_CLASSES = (
    ("legal_case", "The legal counsel's work on a case (prompt 13 §3; never on an alternative)"),
    ("legal_email", "The legal counsel's reading of a reply and its next step (prompt 13 §3)"),
)

WAKE = """
CREATE OR REPLACE FUNCTION agents.wake_on_message() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        t record;
    BEGIN
        IF NEW.author_kind <> 'owner' THEN
            RETURN NULL;
        END IF;
        SELECT kind, employee_id INTO t FROM msg.threads WHERE id = NEW.thread_id;
        IF t.employee_id IS NOT NULL AND t.kind IN ({kinds}) THEN
            PERFORM agents.queue_run(t.employee_id, 'message', NULL, NEW.thread_id,
                                     'message:' || NEW.ref,
                                     CASE WHEN t.kind IN ({p2}) THEN 'P2' END);
        END IF;
        RETURN NULL;
    END $$;
"""
WAKE_KINDS = "'advisor', 'overseer', 'assistant', 'ceo', 'manager', 'employee'"
WAKE_P2 = "'advisor', 'overseer', 'assistant'"

UPGRADE = r"""
CREATE SCHEMA legal;
CREATE SCHEMA IF NOT EXISTS media;
GRANT USAGE ON SCHEMA legal, media TO @APP@;
CREATE SEQUENCE legal.case_ref_seq;

-- ================================================================ cases ==
CREATE TABLE legal.cases (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    ref             text NOT NULL UNIQUE
                         DEFAULT 'LC-' || lpad(nextval('legal.case_ref_seq')::text, 4, '0')
                         CHECK (ref ~ '^LC-[0-9]{4,}$'),
    title_fa        text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    kind            text NOT NULL CHECK (kind IN ('platform_restriction', 'account_appeal', 'takedown',
                                                  'partner_dispute', 'policy_review', 'contract_review',
                                                  'compliance', 'other')),
    brief_md        text NOT NULL DEFAULT '' CHECK (length(brief_md) <= 20000),
    counterpart     jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(counterpart) = 'object'),
    status          text NOT NULL DEFAULT 'open'
                         CHECK (status IN ('open', 'waiting_reply', 'waiting_owner', 'resolved', 'closed')),
    counsel_id      uuid NOT NULL REFERENCES core.employees (id),
    counsel_code    text NOT NULL CHECK (length(counsel_code) BETWEEN 3 AND 64),
    deadlines       jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(deadlines) = 'array'
                                                       AND jsonb_array_length(deadlines) <= 50),
    file_ids        uuid[] NOT NULL DEFAULT '{}' CHECK (cardinality(file_ids) <= 20),
    opened_by_kind  text NOT NULL CHECK (opened_by_kind IN ('owner', 'agent', 'service')),
    opened_by_code  text NOT NULL CHECK (length(opened_by_code) BETWEEN 1 AND 64),
    work_id         uuid REFERENCES work.work (id),
    closed_at       timestamptz,
    version         int NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CHECK ((status = 'closed') = (closed_at IS NOT NULL))
);
CREATE INDEX cases_list ON legal.cases (status, updated_at DESC);
CREATE INDEX cases_counsel ON legal.cases (counsel_id, status);
CREATE TRIGGER cases_immutable BEFORE UPDATE ON legal.cases
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'opened_by_kind',
                                                      'opened_by_code', 'created_at');
CREATE TRIGGER cases_version BEFORE UPDATE ON legal.cases
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- The timeline: every step, form, decision and outcome (append-only).
CREATE TABLE legal.case_events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    case_id     uuid NOT NULL REFERENCES legal.cases (id),
    at          timestamptz NOT NULL DEFAULT now(),
    kind        text NOT NULL CHECK (kind IN ('note', 'email_out', 'email_in', 'form', 'decision')),
    ref         text CHECK (length(ref) BETWEEN 1 AND 80),
    summary_fa  text NOT NULL CHECK (length(summary_fa) BETWEEN 1 AND 4000),
    by_kind     text NOT NULL CHECK (by_kind IN ('owner', 'agent', 'service', 'system')),
    by_code     text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64)
);
CREATE INDEX case_events_case ON legal.case_events (case_id, at);

-- ================================================================ email ==
-- An outgoing email is the counsel's draft: the exact message the owner
-- seals (digest = SHA-256 of its canonical form). Its content never changes;
-- a change is a new draft (and a new card), the old one `superseded`.
-- state: waiting_seal -> queued (sealed; waits while a lock is set) ->
-- sending -> sent | failed; or superseded | rejected. An incoming one is
-- `received`, masked by code before it is stored.
CREATE TABLE legal.emails (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    case_id        uuid NOT NULL REFERENCES legal.cases (id),
    direction      text NOT NULL CHECK (direction IN ('out', 'in')),
    state          text NOT NULL CHECK (state IN ('waiting_seal', 'queued', 'sending', 'sent', 'failed',
                                                  'received', 'superseded', 'rejected')),
    from_addr      text NOT NULL CHECK (length(from_addr) <= 320),
    to_addrs       text[] NOT NULL CHECK (cardinality(to_addrs) BETWEEN 0 AND 20),
    cc_addrs       text[] NOT NULL DEFAULT '{}' CHECK (cardinality(cc_addrs) <= 20),
    subject        text NOT NULL CHECK (length(subject) <= 998),
    body_md        text NOT NULL CHECK (length(body_md) <= 100000),
    lang           text NOT NULL CHECK (lang IN ('fa', 'en')),
    attachments    jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(attachments) = 'array'
                                                      AND jsonb_array_length(attachments) <= 10),
    digest         text CHECK (digest ~ '^[0-9a-f]{64}$'),
    message_id     text NOT NULL UNIQUE CHECK (length(message_id) BETWEEN 3 AND 998),
    in_reply_to    text CHECK (length(in_reply_to) <= 998),
    refs           text[] NOT NULL DEFAULT '{}' CHECK (cardinality(refs) <= 50),
    decision_id    uuid REFERENCES cartable.decisions (id),
    decision_ref   text CHECK (decision_ref ~ '^D-[0-9]{6,}$'),
    drafted_by     text CHECK (length(drafted_by) BETWEEN 1 AND 64),
    imap_uid       bigint,
    sent_at        timestamptz,
    received_at    timestamptz,
    send_attempt_at timestamptz,
    error          text CHECK (length(error) <= 300),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CHECK ((direction = 'out') = (digest IS NOT NULL)),
    CHECK (direction = 'out' OR state = 'received'),
    CHECK (direction = 'in' OR state <> 'received'),
    CHECK ((state = 'sent') = (sent_at IS NOT NULL))
);
CREATE INDEX emails_case ON legal.emails (case_id, created_at);
CREATE INDEX emails_waiting ON legal.emails (state) WHERE state IN ('waiting_seal', 'queued', 'sending');
CREATE UNIQUE INDEX emails_one_waiting ON legal.emails (case_id) WHERE state = 'waiting_seal';
CREATE TRIGGER emails_immutable BEFORE UPDATE ON legal.emails
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'case_id', 'direction',
                                                      'from_addr', 'to_addrs', 'cc_addrs', 'subject',
                                                      'body_md', 'lang', 'attachments', 'digest',
                                                      'message_id', 'in_reply_to', 'refs', 'created_at');

-- The poller's cursor on the holding mailbox (IMAP UIDVALIDITY and last UID).
CREATE TABLE legal.mailbox (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL REFERENCES core.companies (id),
    account       text NOT NULL UNIQUE CHECK (account ~ '^[a-z0-9][a-z0-9_.-]{1,40}$'),
    uidvalidity   bigint,
    last_uid      bigint NOT NULL DEFAULT 0 CHECK (last_uid >= 0),
    last_poll_at  timestamptz,
    last_result   text CHECK (length(last_result) <= 200),
    polls         bigint NOT NULL DEFAULT 0,
    matched       bigint NOT NULL DEFAULT 0,
    ignored       bigint NOT NULL DEFAULT 0,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

-- =============================================================== voices ==
-- One row per engine and speaker (contract §22.7). `runtime` names what the
-- TTS image runs it with ({"piper_voice": "fa_IR-amir-medium"}); null = not
-- installed on the hub (measured elsewhere or not at all: `note_fa` says why).
CREATE TABLE media.voices (
    id                  text PRIMARY KEY CHECK (id ~ '^[a-z0-9][a-z0-9_.-]{1,60}$'),
    company_id          uuid NOT NULL REFERENCES core.companies (id),
    engine              text NOT NULL CHECK (engine ~ '^[a-z0-9][a-z0-9_-]{1,30}$'),
    name_fa             text NOT NULL CHECK (length(name_fa) BETWEEN 1 AND 200),
    licence             text NOT NULL CHECK (length(licence) BETWEEN 1 AND 300),
    licence_commercial  boolean NOT NULL,
    speaker             text NOT NULL CHECK (speaker IN ('model', 'owner')),
    clones              boolean NOT NULL DEFAULT false,
    runtime             jsonb CHECK (runtime IS NULL OR jsonb_typeof(runtime) = 'object'),
    source              jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(source) = 'object'),
    rtf                 numeric(8, 3) CHECK (rtf >= 0),
    mem_mb              numeric(9, 1) CHECK (mem_mb >= 0),
    measured_at         timestamptz,
    measured_on         text CHECK (length(measured_on) <= 200),
    owner_score         int CHECK (owner_score BETWEEN 1 AND 10),
    scored_at           timestamptz,
    status              text NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'active', 'retired')),
    activated_at        timestamptz,
    note_fa             text CHECK (length(note_fa) <= 2000),
    sort                int NOT NULL DEFAULT 100,
    version             int NOT NULL DEFAULT 1,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK ((rtf IS NULL) = (measured_at IS NULL)),
    CHECK (status <> 'active' OR measured_at IS NOT NULL)
);
CREATE UNIQUE INDEX voices_one_active ON media.voices ((true)) WHERE status = 'active';
CREATE TRIGGER voices_immutable BEFORE UPDATE ON media.voices
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'engine', 'speaker',
                                                      'created_at');
CREATE TRIGGER voices_version BEFORE UPDATE ON media.voices
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- The queue of the TTS one-shot beside the briefings: `sample` (one bake-off
-- script for one voice, round n) and `narration` (a media item's voice).
CREATE TABLE media.speech_jobs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL REFERENCES core.companies (id),
    kind          text NOT NULL CHECK (kind IN ('sample', 'narration')),
    voice_id      text NOT NULL REFERENCES media.voices (id),
    script_key    text CHECK (script_key ~ '^[a-z][a-z0-9_]{1,40}$'),
    round         int NOT NULL DEFAULT 1 CHECK (round >= 1),
    subject_ref   text CHECK (subject_ref ~ '^MI-[0-9]{4,}$'),
    script        text NOT NULL CHECK (length(script) BETWEEN 1 AND 20000),
    state         text NOT NULL DEFAULT 'queued'
                       CHECK (state IN ('queued', 'claimed', 'done', 'failed', 'cancelled')),
    attempts      int NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 20),
    claimed_at    timestamptz,
    error         text CHECK (length(error) <= 300),
    file_id       uuid REFERENCES files.files (id),
    result        jsonb CHECK (result IS NULL OR jsonb_typeof(result) = 'object'),
    created_by_kind text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
    created_by_code text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CHECK ((kind = 'sample') = (script_key IS NOT NULL)),
    CHECK ((kind = 'narration') = (subject_ref IS NOT NULL)),
    CHECK ((state = 'done') = (file_id IS NOT NULL))
);
CREATE UNIQUE INDEX speech_jobs_sample ON media.speech_jobs (voice_id, script_key, round)
    WHERE kind = 'sample';
CREATE INDEX speech_jobs_queued ON media.speech_jobs (created_at) WHERE state IN ('queued', 'claimed');
CREATE TRIGGER speech_jobs_immutable BEFORE UPDATE ON media.speech_jobs
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'kind', 'voice_id',
                                                      'script_key', 'round', 'subject_ref', 'script',
                                                      'created_at');

CREATE TABLE media.voice_samples (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    voice_id    text NOT NULL REFERENCES media.voices (id),
    script_key  text NOT NULL CHECK (script_key ~ '^[a-z][a-z0-9_]{1,40}$'),
    round       int NOT NULL CHECK (round >= 1),
    job_id      uuid NOT NULL UNIQUE REFERENCES media.speech_jobs (id),
    file_id     uuid NOT NULL REFERENCES files.files (id),
    duration_s  numeric(9, 3) NOT NULL CHECK (duration_s > 0),
    synth_s     numeric(9, 3) NOT NULL CHECK (synth_s >= 0),
    peak_mb     numeric(9, 1) CHECK (peak_mb >= 0),
    at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX voice_samples_voice ON media.voice_samples (voice_id, round, script_key);

-- The owner's own voice, 1-3 minutes (contract §22.3): never sent anywhere.
CREATE TABLE media.voice_references (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    file_id     uuid NOT NULL REFERENCES files.files (id),
    duration_s  numeric(9, 3) NOT NULL CHECK (duration_s > 0),
    state       text NOT NULL CHECK (state IN ('processing', 'ready', 'rejected', 'superseded')),
    reason_fa   text CHECK (length(reason_fa) <= 500),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX voice_references_current ON media.voice_references ((true))
    WHERE state <> 'superseded';
CREATE TRIGGER voice_references_immutable BEFORE UPDATE ON media.voice_references
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'file_id', 'duration_s',
                                                      'created_at');

-- ============================================== threads: L, kind legal ==
ALTER TABLE msg.threads DROP CONSTRAINT threads_code_check;
ALTER TABLE msg.threads ADD CONSTRAINT threads_code_check CHECK (code ~ '@THREAD_CODE@');
"""


def _kinds_sql(
    table: str, constraint: str, add: tuple[str, ...], drop: tuple[str, ...], valid: bool
) -> str:
    """Rewrite a `kind IN (...)` CHECK from the kinds it holds now (plus `add`,
    minus `drop`): whatever another migration added is kept (0025's helper)."""
    added = ", ".join(f"'{k}'" for k in add)
    dropped = ", ".join(f"'{k}'" for k in drop) or "''"
    tail = "" if valid else " NOT VALID"
    return f"""
        DO $$
        DECLARE kinds text;
        BEGIN
            SELECT string_agg(quote_literal(k), ', ' ORDER BY k) INTO kinds FROM (
                SELECT DISTINCT m[1] AS k
                FROM pg_constraint c,
                     regexp_matches(pg_get_constraintdef(c.oid), '''([a-z0-9_]+)''', 'g') AS m
                WHERE c.conrelid = '{table}'::regclass AND c.conname = '{constraint}'
                UNION SELECT unnest(ARRAY[{added}]::text[])
            ) x WHERE k IS NOT NULL AND k <> ALL (ARRAY[{dropped}]::text[]);
            ALTER TABLE {table} DROP CONSTRAINT {constraint};
            EXECUTE format('ALTER TABLE {table} ADD CONSTRAINT {constraint} '
                           'CHECK (kind IN (%s)){tail}', kinds);
        END $$;
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
    execute_script(UPGRADE.replace("@APP@", APP_ROLES).replace("@THREAD_CODE@", THREAD_CODE))
    grants = [_rls(t) for t in TABLES]
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
    execute_script(
        # NOT VALID (the task's rule for the decision kind CHECK); 'legal' is
        # only added to the thread kinds, so that one stays VALID.
        _kinds_sql("cartable.decisions", "decisions_kind_check", ("email_send",), (), False)
        + _kinds_sql("msg.threads", "threads_kind_check", ("legal",), (), True)
        + WAKE.format(kinds=WAKE_KINDS + ", 'legal'", p2=WAKE_P2 + ", 'legal'")
    )
    classes = ",\n".join(f"('{k}', false, '{d}')" for k, d in TASK_CLASSES)
    execute_script(
        f"""INSERT INTO llm.task_classes (key, transferable, description)
            VALUES {classes} ON CONFLICT (key) DO NOTHING;"""
    )


def downgrade() -> None:
    # Data stays out of reach, never rewritten: email_send cards and thread L
    # are kept (NOT VALID), the tables of this revision go.
    execute_script(
        WAKE.format(kinds=WAKE_KINDS, p2=WAKE_P2)
        + _kinds_sql("msg.threads", "threads_kind_check", (), ("legal",), False)
        + _kinds_sql("cartable.decisions", "decisions_kind_check", (), ("email_send",), False)
        + f"""
        ALTER TABLE msg.threads DROP CONSTRAINT threads_code_check;
        ALTER TABLE msg.threads ADD CONSTRAINT threads_code_check CHECK (code ~ '{THREAD_CODE_OLD}') NOT VALID;
        DROP TABLE media.voice_references;
        DROP TABLE media.voice_samples;
        DROP TABLE media.speech_jobs;
        DROP TABLE media.voices;
        DROP SCHEMA legal CASCADE;
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                           WHERE n.nspname = 'media') THEN
                DROP SCHEMA media;
            END IF;
        END $$;
        """
    )
