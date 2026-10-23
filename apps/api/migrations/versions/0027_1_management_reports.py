"""Prompt 12, part B (contract §21.4-§21.9, §21.12): spoken briefings and the
CEOs' weekly letters, department ranks, the monthly HR round, the daily waste
report, quick notes and cartable reminders, refuted claims; PR-082 on the
Jalali calendar.

New schemas `reports` and `quality`; every table carries company_id (owner
and holding rows: the holding's) under FORCE RLS (the once-per-query policy
of 0009):

  reports.briefings          BR-0001: a morning report or a CEO letter, its
                             spoken script and its audio (the TTS job queue:
                             audio_state 'pending' = queued for the one-shot)
  reports.ceo_letters        one per company and week: the facts pack built
                             by code, the attempts and the unsourced figures
  people.department_ranks    a department's score of a closed week or month
                             (append-only, written with the stars roll-up)
  people.hr_rounds           HR-0001: the monthly round of a company (or the
                             holding), its facts and flags per employee
  llm.waste_daily            the day's waste by category (no prompt or reply
                             text, only counts, tokens, dollars and refs)
  owner.notes                NT-0001: the owner's quick notes (no delete)
  owner.decision_reminders   one row per card and threshold (append-only)
  quality.claims             CL-0001: a checked claim (append-only; a
                             refuted one carries evidence)

Also owner.settings gains the blocks audio_briefings, ceo_weekly_letter and
reminders (§21.12), and oversight.protocols gains `calendar` (gregorian |
jalali, §21.12); the current_protocols view is recreated to show it. The
data step moves PR-082 to the 3rd of the Jalali month at 10:00 and makes it
active (a new version, with its audit row) where it is still the seeded,
paused version 1. No decision kind is added: the kind CHECK is not touched.

Revision ID: 0027_1
Revises: 0027 (prompt 12 part A; the parent moves 0027 after prompt 11's 0026_1)
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0027_1"
down_revision = "0027"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"

TABLES = (
    "reports.briefings",
    "reports.ceo_letters",
    "people.department_ranks",
    "people.hr_rounds",
    "llm.waste_daily",
    "owner.notes",
    "owner.decision_reminders",
    "quality.claims",
)
APPEND_ONLY = ("people.department_ranks", "owner.decision_reminders", "quality.claims")
SEQUENCES = (
    "reports.briefing_ref_seq",
    "people.hr_round_ref_seq",
    "owner.note_ref_seq",
    "quality.claim_ref_seq",
)
PR082_CHECK = (
    "Each month's HR round ran for every active operating company and the holding, with its "
    "monthly HR report, and an `evaluation` card for every flagged employee (and only with "
    "evidence and `override_reason` for an unflagged one)."
)
PR082_SCHEDULE = "FREQ=MONTHLY;BYMONTHDAY=3;BYHOUR=10;BYMINUTE=0"


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


UPGRADE = r"""
CREATE SCHEMA reports;
CREATE SCHEMA quality;
GRANT USAGE ON SCHEMA reports, quality TO @APP@;
CREATE SEQUENCE reports.briefing_ref_seq;
CREATE SEQUENCE people.hr_round_ref_seq;
CREATE SEQUENCE owner.note_ref_seq;
CREATE SEQUENCE quality.claim_ref_seq;

-- ============================================================ briefings ==
-- A written report and its voice (§21.4). The TTS one-shot claims the
-- oldest `pending` row; `off` = the voice is switched off, the text stands.
CREATE TABLE reports.briefings (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    ref             text NOT NULL UNIQUE
                         DEFAULT 'BR-' || lpad(nextval('reports.briefing_ref_seq')::text, 4, '0')
                         CHECK (ref ~ '^BR-[0-9]{4,}$'),
    kind            text NOT NULL CHECK (kind IN ('morning', 'ceo_letter')),
    period_from     date NOT NULL,
    period_to       date NOT NULL CHECK (period_to >= period_from),
    deliverable_id  uuid NOT NULL REFERENCES cartable.deliverables (id),
    deliverable_ref text NOT NULL CHECK (deliverable_ref ~ '^O-[0-9]+$'),
    text_md         text NOT NULL CHECK (length(text_md) <= 500000),
    script          text CHECK (length(script) <= 200000),
    audio_file_id   uuid REFERENCES files.files (id),
    audio_state     text NOT NULL CHECK (audio_state IN ('pending', 'ready', 'off', 'failed')),
    voice           jsonb CHECK (voice IS NULL OR jsonb_typeof(voice) = 'object'),
    unsourced       boolean NOT NULL DEFAULT false,      -- a letter published «عدد بی‌منبع»
    tts_attempts    int NOT NULL DEFAULT 0 CHECK (tts_attempts BETWEEN 0 AND 20),
    tts_claimed_at  timestamptz,
    tts_error       text CHECK (length(tts_error) <= 300),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (kind, company_id, period_from),
    CHECK ((audio_state = 'ready') = (audio_file_id IS NOT NULL))
);
CREATE INDEX briefings_pending ON reports.briefings (created_at) WHERE audio_state = 'pending';
CREATE INDEX briefings_latest ON reports.briefings (kind, company_id, created_at DESC);
CREATE TRIGGER briefings_immutable BEFORE UPDATE ON reports.briefings
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'kind', 'period_from',
                                                      'period_to', 'deliverable_id', 'deliverable_ref',
                                                      'text_md', 'created_at');

-- One weekly letter per company: the facts pack is code, the letter the CEO's.
CREATE TABLE reports.ceo_letters (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    week         date NOT NULL CHECK (extract(isodow FROM week) = 6),   -- the Saturday it is written
    work_id      uuid REFERENCES work.work (id),
    ceo_code     text NOT NULL CHECK (length(ceo_code) BETWEEN 3 AND 64),
    facts        jsonb NOT NULL CHECK (jsonb_typeof(facts) = 'object'),
    figures      text[] NOT NULL DEFAULT '{}',
    state        text NOT NULL DEFAULT 'writing'
                      CHECK (state IN ('writing', 'returned', 'published', 'failed')),
    attempts     int NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 10),
    unsourced    text[] NOT NULL DEFAULT '{}' CHECK (cardinality(unsourced) <= 50),
    briefing_id  uuid REFERENCES reports.briefings (id),
    finding_ref  text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, week)
);
CREATE UNIQUE INDEX ceo_letters_work ON reports.ceo_letters (work_id) WHERE work_id IS NOT NULL;
CREATE TRIGGER ceo_letters_immutable BEFORE UPDATE ON reports.ceo_letters
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'week', 'facts', 'figures',
                                                      'created_at');

-- ===================================================== department ranks ==
CREATE TABLE people.department_ranks (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    period         text NOT NULL CHECK (period IN ('week', 'month')),
    key            text NOT NULL CHECK (key ~ '^[0-9]{4}-[0-9]{2}(-[0-9]{2})?$'),
    department_id  uuid NOT NULL REFERENCES core.departments (id),
    department     text NOT NULL CHECK (department ~ '^[A-Z][A-Z0-9]{1,11}$'),
    score          numeric(5, 1) NOT NULL CHECK (score BETWEEN 0 AND 100),
    parts          jsonb NOT NULL CHECK (jsonb_typeof(parts) = 'object'),
    employees      int NOT NULL CHECK (employees >= 1),
    rank_company   int NOT NULL CHECK (rank_company >= 1),
    rank_holding   int CHECK (rank_holding >= 1),
    trend          jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(trend) = 'array'),
    computed_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (period, key, department_id)
);
CREATE INDEX department_ranks_period ON people.department_ranks (period, key, company_id);

-- ======================================================== the HR round ==
CREATE TABLE people.hr_rounds (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    ref              text NOT NULL UNIQUE
                          DEFAULT 'HR-' || lpad(nextval('people.hr_round_ref_seq')::text, 4, '0')
                          CHECK (ref ~ '^HR-[0-9]{4,}$'),
    month            text NOT NULL CHECK (month ~ '^1[34][0-9]{2}-(0[1-9]|1[0-2])$'),
    state            text NOT NULL DEFAULT 'drafting' CHECK (state IN ('drafting', 'proposed', 'done')),
    evaluator_kind   text NOT NULL CHECK (evaluator_kind IN ('agent', 'owner', 'service')),
    evaluator_code   text NOT NULL CHECK (length(evaluator_code) BETWEEN 1 AND 64),
    work_id          uuid REFERENCES work.work (id),
    due_at           timestamptz NOT NULL,
    employees        jsonb NOT NULL CHECK (jsonb_typeof(employees) = 'array'),
    deliverable_ref  text CHECK (deliverable_ref ~ '^O-[0-9]+$'),
    decisions        text[] NOT NULL DEFAULT '{}',
    teachings        text[] NOT NULL DEFAULT '{}',
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, month)
);
CREATE UNIQUE INDEX hr_rounds_work ON people.hr_rounds (work_id) WHERE work_id IS NOT NULL;
CREATE TRIGGER hr_rounds_immutable BEFORE UPDATE ON people.hr_rounds
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'month', 'employees',
                                                      'created_at');

-- ========================================================= daily waste ==
-- scope 'holding' (company_id = the holding) is the holding's total.
CREATE TABLE llm.waste_daily (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL REFERENCES core.companies (id),
    scope         text NOT NULL CHECK (scope IN ('company', 'holding')),
    day           date NOT NULL,
    total_tokens  bigint NOT NULL CHECK (total_tokens >= 0),
    total_usd     numeric(14, 6) NOT NULL CHECK (total_usd >= 0),
    waste_tokens  bigint NOT NULL CHECK (waste_tokens >= 0),
    waste_usd     numeric(14, 6) NOT NULL CHECK (waste_usd >= 0),
    share         numeric(7, 6) NOT NULL CHECK (share BETWEEN 0 AND 1),
    vs_7d         numeric(12, 6),
    items         jsonb NOT NULL CHECK (jsonb_typeof(items) = 'array'),
    computed_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (day, scope, company_id)
);
CREATE TRIGGER waste_daily_immutable BEFORE UPDATE ON llm.waste_daily
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'scope', 'day');

-- ========================================================= quick notes ==
CREATE TABLE owner.notes (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    ref            text NOT NULL UNIQUE
                        DEFAULT 'NT-' || lpad(nextval('owner.note_ref_seq')::text, 4, '0')
                        CHECK (ref ~ '^NT-[0-9]{4,}$'),
    text_md        text NOT NULL CHECK (length(text_md) BETWEEN 1 AND 20000),
    source         text NOT NULL CHECK (source IN ('text', 'voice')),
    file_id        uuid REFERENCES files.files (id),
    tags           text[] NOT NULL DEFAULT '{}' CHECK (cardinality(tags) <= 20),
    status         text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'promoted', 'archived')),
    promoted_kind  text CHECK (promoted_kind IN ('work', 'order', 'errand')),
    promoted_ref   text CHECK (length(promoted_ref) <= 40),
    version        int NOT NULL DEFAULT 1,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CHECK ((status = 'promoted') = (promoted_ref IS NOT NULL)),
    CHECK ((promoted_kind IS NULL) = (promoted_ref IS NULL))
);
CREATE INDEX notes_recent ON owner.notes (status, created_at DESC);
CREATE TRIGGER notes_immutable BEFORE UPDATE ON owner.notes
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'source', 'file_id',
                                                      'created_at');
CREATE TRIGGER notes_version BEFORE UPDATE ON owner.notes
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- A cartable reminder: each threshold of a card once (§21.8).
CREATE TABLE owner.decision_reminders (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    decision_id  uuid NOT NULL REFERENCES cartable.decisions (id),
    kind         text NOT NULL CHECK (kind ~ '^(half|before_expiry|age_[0-9]{1,4}h|age_7d)$'),
    at           timestamptz NOT NULL DEFAULT now(),
    notification_id uuid,
    UNIQUE (decision_id, kind)
);

-- ============================================================== claims ==
CREATE TABLE quality.claims (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    ref              text NOT NULL UNIQUE
                          DEFAULT 'CL-' || lpad(nextval('quality.claim_ref_seq')::text, 4, '0')
                          CHECK (ref ~ '^CL-[0-9]{4,}$'),
    deliverable_id   uuid NOT NULL REFERENCES cartable.deliverables (id),
    deliverable_ref  text NOT NULL CHECK (deliverable_ref ~ '^O-[0-9]+$'),
    employee_id      uuid REFERENCES core.employees (id),
    employee_code    text,
    claim_md         text NOT NULL CHECK (length(claim_md) BETWEEN 1 AND 300),
    verdict          text NOT NULL CHECK (verdict IN ('confirmed', 'refuted', 'unverifiable')),
    checked_by_kind  text NOT NULL CHECK (checked_by_kind IN ('agent', 'owner', 'service')),
    checked_by_code  text NOT NULL CHECK (length(checked_by_code) BETWEEN 1 AND 64),
    protocol         text CHECK (protocol ~ '^PR-[0-9]{3,}$'),
    evidence         jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(evidence) = 'array'),
    at               timestamptz NOT NULL DEFAULT now(),
    CHECK (verdict <> 'refuted' OR jsonb_array_length(evidence) > 0)
);
CREATE INDEX claims_employee ON quality.claims (employee_id, at DESC);
CREATE INDEX claims_company ON quality.claims (company_id, at DESC);

-- ====================================================== owner settings ==
ALTER TABLE owner.settings
    ADD COLUMN audio_briefings jsonb NOT NULL
        DEFAULT '{"morning": true, "ceo_letters": true}' CHECK (jsonb_typeof(audio_briefings) = 'object'),
    ADD COLUMN ceo_weekly_letter jsonb NOT NULL
        DEFAULT '{"enabled": true, "day": "sa", "at": "09:00"}' CHECK (jsonb_typeof(ceo_weekly_letter) = 'object'),
    ADD COLUMN reminders jsonb NOT NULL
        DEFAULT '{"enabled": true, "fraction": 0.5, "before_expiry_h": 6, "ages_h": [24, 72, 168]}'
        CHECK (jsonb_typeof(reminders) = 'object');
GRANT UPDATE (audio_briefings, ceo_weekly_letter, reminders) ON owner.settings TO hq_api;

-- ============================================== protocols: the calendar ==
ALTER TABLE oversight.protocols
    ADD COLUMN calendar text NOT NULL DEFAULT 'gregorian' CHECK (calendar IN ('gregorian', 'jalali'));
CREATE OR REPLACE VIEW oversight.current_protocols WITH (security_invoker = true) AS
    SELECT DISTINCT ON (ref) * FROM oversight.protocols ORDER BY ref, version DESC;
"""

# PR-082 (prompt 12 §6.7): the seeded, paused version 1 gets a version 2,
# active, on the 3rd of the Jalali month. A fresh database has no PR-082 yet
# (the seed runs after the migrations); the worker's seed then applies the
# same step (hq_api.domain.oversight.activate_pr082).
ACTIVATE_PR082 = f"""
WITH cur AS (
    SELECT * FROM oversight.current_protocols WHERE ref = 'PR-082'
), ins AS (
    INSERT INTO oversight.protocols (company_id, ref, version, title_fa, area, check_md, method, schedule,
                                     scope, evidence_md, severity, answerable, status, source,
                                     created_by_kind, created_by_code, calendar)
    SELECT company_id, ref, version + 1, title_fa, area, '{PR082_CHECK.replace("'", "''")}', method,
           '{PR082_SCHEDULE}', scope, evidence_md, severity, answerable, 'active', 'seed',
           'service', 'migration-0027_1', 'jalali'
    FROM cur WHERE version = 1 AND source = 'seed' AND status = 'paused'
    RETURNING company_id, ref, version
)
INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action, action_class,
                           target_kind, target_ref, step_up, summary)
SELECT 'system', 'system', 'system', company_id, 'oversight.protocol_activate', 'A1', 'protocol',
       ref || '@' || version, false, 'prompt 12: active on the 3rd of the Jalali month (migration 0027_1)'
FROM ins;
"""


def upgrade() -> None:
    execute_script(UPGRADE.replace("@APP@", APP_ROLES))
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
    execute_script(ACTIVATE_PR082)


def downgrade() -> None:
    execute_script(
        """
        -- The PR-082 versions stay (protocols are append-only); only the column goes.
        DROP VIEW oversight.current_protocols;
        ALTER TABLE oversight.protocols DROP COLUMN calendar;
        CREATE VIEW oversight.current_protocols WITH (security_invoker = true) AS
            SELECT DISTINCT ON (ref) * FROM oversight.protocols ORDER BY ref, version DESC;
        GRANT SELECT ON oversight.current_protocols TO hq_api, hq_worker;
        REVOKE UPDATE (audio_briefings, ceo_weekly_letter, reminders) ON owner.settings FROM hq_api;
        ALTER TABLE owner.settings DROP COLUMN audio_briefings, DROP COLUMN ceo_weekly_letter,
            DROP COLUMN reminders;
        DROP TABLE owner.decision_reminders;
        DROP TABLE owner.notes;
        DROP SEQUENCE owner.note_ref_seq;
        DROP TABLE llm.waste_daily;
        DROP TABLE people.hr_rounds;
        DROP SEQUENCE people.hr_round_ref_seq;
        DROP TABLE people.department_ranks;
        DROP SCHEMA quality CASCADE;
        DROP SCHEMA reports CASCADE;
        """
    )
