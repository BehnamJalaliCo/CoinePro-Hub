"""Prompt 13, the media half (contract §22.1, §22.2, §22.5, §22.6): department
mandates and identities, the media studio, roles written on demand.

- core.departments gains `mandate` (from_fa, to_fa, outputs_fa, boundaries_fa,
  tool_ceiling, model_ceiling) and `identity_md`; the seed fills both from the
  template where they are empty. agents.runs gains `identity_doc` (the
  department identity a run read, "TY-MEDIA@4").
- New schema `media`; every table carries company_id under FORCE RLS (the
  once-per-query policy of 0009) and refuses DELETE:

    media.series        SR-0001: a publishing series the owner seals once
    media.items         MI-0001: one reel, story, post, carousel or design
    media.compositions  the motion graphics of an item as code (append-only:
                        every change is a new numbered version with its sha256)
    media.render_jobs   the sandboxed render worker's queue (one-shot, profile
                        `media`): queued -> claimed -> done | failed
    media.publish_log   every publish and unpublish attempt (append-only)

- people.role_drafts (RD-0001): a role a department manager writes when the
  work needs one and no charter covers it (§22.5).
- owner.stories may be of kind `role` («نقش تازه در …», §22.7).
- Data: every operating company gets the department MEDIA («رسانه و طراحی»,
  sort 25) with its asleep manager <CO>-MEDIA-MGR (charter media_director)
  and its two threads; the holding gets LEGAL («حقوقی», no manager) with the
  asleep employee <HQ>-LGL (charter legal_counsel), like <HQ>-PA. No
  numbered employee is created. The legal counsel's thread L and the
  `legal` thread kind are §22.4's (the other half of prompt 13).
- Decision kinds media_series, media_publish, role_new (and email_send, which
  §22.4 adds too) join decisions_kind_check, rewritten from the kinds it
  holds now and added NOT VALID.

Revision ID: 0028
Revises: 0027_1
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0028"
down_revision = "0027_1"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"

TABLES = (
    "media.series",
    "media.items",
    "media.compositions",
    "media.render_jobs",
    "media.publish_log",
    "people.role_drafts",
)
APPEND_ONLY = ("media.compositions", "media.publish_log")
SEQUENCES = ("media.series_ref_seq", "media.item_ref_seq", "people.role_draft_ref_seq")
NEW_KINDS = ("media_series", "media_publish", "role_new", "email_send")

SERIES_STATUS = "'draft', 'proposed', 'sealed', 'paused', 'retired'"
ITEM_KINDS = "'reel', 'story', 'post', 'carousel', 'design'"
ITEM_STATES = (
    "'scripting', 'directing', 'composing', 'voicing', 'rendering', 'checking', 'review', "
    "'scheduled', 'published', 'waiting_owner', 'held', 'failed', 'rejected'"
)
DRAFT_STATES = "'drafting', 'in_review', 'eval', 'proposed', 'active', 'rejected', 'retired'"
ACTOR = "'owner', 'agent', 'service'"


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


UPGRADE = rf"""
-- ======================================================= departments ==
-- «مبدأ و مقصد» and the department's character (§22.1); NULL until the seed
-- fills them from the template (only where empty: the owner's edits stay).
ALTER TABLE core.departments
    ADD COLUMN mandate jsonb CHECK (mandate IS NULL OR jsonb_typeof(mandate) = 'object'),
    ADD COLUMN identity_md text CHECK (identity_md IS NULL OR length(identity_md) <= 6000);
ALTER TABLE agents.runs
    ADD COLUMN identity_doc text CHECK (identity_doc IS NULL OR length(identity_doc) <= 80);

-- A role story (§22.7): «نقش تازه در …».
ALTER TABLE owner.stories DROP CONSTRAINT IF EXISTS stories_kind_check;
ALTER TABLE owner.stories ADD CONSTRAINT stories_kind_check
    CHECK (kind IN ('hire', 'deliverable', 'stars', 'milestone', 'post', 'role'));

CREATE SCHEMA media;
GRANT USAGE ON SCHEMA media TO @APP@;
CREATE SEQUENCE media.series_ref_seq;
CREATE SEQUENCE media.item_ref_seq;
CREATE SEQUENCE people.role_draft_ref_seq;

-- ============================================================ series ==
CREATE TABLE media.series (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    ref               text NOT NULL UNIQUE
                           DEFAULT 'SR-' || lpad(nextval('media.series_ref_seq')::text, 4, '0')
                           CHECK (ref ~ '^SR-[0-9]{{4,}}$'),
    title_fa          text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
    kind              text NOT NULL CHECK (kind IN ('reel', 'story', 'post', 'carousel')),
    targets           jsonb NOT NULL CHECK (jsonb_typeof(targets) = 'array'),
    schedule          text NOT NULL CHECK (length(schedule) BETWEEN 5 AND 500),
    topics            jsonb CHECK (topics IS NULL OR jsonb_typeof(topics) = 'object'),
    format            jsonb NOT NULL CHECK (jsonb_typeof(format) = 'object'),
    checks            text[] NOT NULL CHECK (cardinality(checks) BETWEEN 1 AND 7),
    auto_publish      boolean NOT NULL DEFAULT false,
    max_per_day       int NOT NULL CHECK (max_per_day BETWEEN 1 AND 20),
    status            text NOT NULL DEFAULT 'draft' CHECK (status IN ({SERIES_STATUS})),
    status_note_fa    text CHECK (length(status_note_fa) <= 500),
    -- sha256 of the canonical JSON of what the seal covers (domain/media.py)
    digest            text NOT NULL CHECK (digest ~ '^[0-9a-f]{{64}}$'),
    proposed_by_kind  text NOT NULL CHECK (proposed_by_kind IN ({ACTOR})),
    proposed_by_code  text NOT NULL CHECK (length(proposed_by_code) BETWEEN 1 AND 64),
    work_id           uuid REFERENCES work.work (id),
    decision_id       uuid REFERENCES cartable.decisions (id),
    sealed_at         timestamptz,
    sealed_digest     text CHECK (sealed_digest ~ '^[0-9a-f]{{64}}$'),
    sealed_step_up_id uuid,
    -- the schedule: the next topic of the pool, the last occurrence handled
    topic_next        int NOT NULL DEFAULT 0 CHECK (topic_next >= 0),
    ticked_at         timestamptz,
    version           int NOT NULL DEFAULT 1,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    -- a sealed series is sealed on exactly what it holds now
    CHECK (status <> 'sealed' OR (sealed_at IS NOT NULL AND sealed_digest = digest))
);
CREATE INDEX series_company ON media.series (company_id, status);
CREATE TRIGGER series_immutable BEFORE UPDATE ON media.series
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'created_at');
CREATE TRIGGER series_version BEFORE UPDATE ON media.series
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- ============================================================= items ==
CREATE TABLE media.items (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    ref              text NOT NULL UNIQUE
                          DEFAULT 'MI-' || lpad(nextval('media.item_ref_seq')::text, 4, '0')
                          CHECK (ref ~ '^MI-[0-9]{{4,}}$'),
    series_id        uuid REFERENCES media.series (id),
    kind             text NOT NULL CHECK (kind IN ({ITEM_KINDS})),
    title_fa         text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    state            text NOT NULL CHECK (state IN ({ITEM_STATES})),
    state_note_fa    text CHECK (length(state_note_fa) <= 1000),
    one_off          boolean NOT NULL DEFAULT false,
    brief_md         text CHECK (length(brief_md) <= 20000),
    topic_fa         text CHECK (length(topic_fa) <= 500),
    -- the occurrence of the series' schedule that made it (null: a one-off)
    slot_at          timestamptz,
    -- the step's own record: {{text_fa, sources, by}} · {{shots, by}}
    script           jsonb CHECK (script IS NULL OR jsonb_typeof(script) = 'object'),
    direction        jsonb CHECK (direction IS NULL OR jsonb_typeof(direction) = 'object'),
    composition_id   uuid,
    assets           uuid[] NOT NULL DEFAULT '{{}}' CHECK (cardinality(assets) <= 50),
    -- the narration of the voice step: {{text_fa, voice_id, state, attempts, error, spoken}}
    narration        jsonb CHECK (narration IS NULL OR jsonb_typeof(narration) = 'object'),
    voice_file_id    uuid REFERENCES files.files (id),
    render_file_id   uuid REFERENCES files.files (id),
    captions_file_id uuid REFERENCES files.files (id),
    -- the render per placement and the pages (a design's screenshots, a carousel's slides)
    outputs          jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(outputs) = 'array'),
    pages            jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(pages) = 'array'),
    render_meta      jsonb CHECK (render_meta IS NULL OR jsonb_typeof(render_meta) = 'object'),
    checks           jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(checks) = 'array'),
    qc               jsonb CHECK (qc IS NULL OR jsonb_typeof(qc) = 'object'),
    publish          jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(publish) = 'array'),
    publish_at       timestamptz,
    decision_id      uuid REFERENCES cartable.decisions (id),
    deliverable_ref  text CHECK (deliverable_ref ~ '^O-[0-9]+$'),
    -- the work item of the current step (its role's), and every step's
    step_work_id     uuid REFERENCES work.work (id),
    steps            jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(steps) = 'array'),
    cost_tokens      bigint NOT NULL DEFAULT 0 CHECK (cost_tokens >= 0),
    cost_usd         numeric(14, 6) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
    ai_generated     boolean NOT NULL DEFAULT true CHECK (ai_generated),
    created_by_kind  text NOT NULL CHECK (created_by_kind IN ({ACTOR})),
    created_by_code  text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
    version          int NOT NULL DEFAULT 1,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CHECK (kind <> 'design' OR (series_id IS NULL AND publish = '[]'::jsonb))
);
CREATE INDEX items_company ON media.items (company_id, state, created_at DESC);
CREATE INDEX items_series ON media.items (series_id, created_at DESC) WHERE series_id IS NOT NULL;
CREATE INDEX items_due ON media.items (publish_at) WHERE state = 'scheduled';
CREATE UNIQUE INDEX items_slot ON media.items (series_id, slot_at) WHERE slot_at IS NOT NULL;
CREATE TRIGGER items_immutable BEFORE UPDATE ON media.items
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'series_id', 'kind',
                                                      'one_off', 'slot_at', 'created_by_kind',
                                                      'created_by_code', 'created_at');
CREATE TRIGGER items_version BEFORE UPDATE ON media.items
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- ====================================================== compositions ==
-- The motion graphics as code (§22.2 step 4): one HTML document or one
-- Lottie JSON, checked against the schema before it is stored; each change
-- is a new version (append-only), identified by its sha256.
CREATE TABLE media.compositions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    item_id     uuid NOT NULL REFERENCES media.items (id),
    n           int NOT NULL CHECK (n >= 1),
    format      text NOT NULL CHECK (format IN ('html', 'lottie')),
    sha256      text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{{64}}$'),
    source      text NOT NULL CHECK (length(source) BETWEEN 1 AND 1500000),
    report      jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(report) = 'object'),
    by_kind     text NOT NULL CHECK (by_kind IN ({ACTOR})),
    by_code     text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64),
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (item_id, n)
);
ALTER TABLE media.items ADD CONSTRAINT items_composition_fk
    FOREIGN KEY (composition_id) REFERENCES media.compositions (id);

-- ======================================================= render jobs ==
-- The render one-shot claims the oldest queued job (204 while the holding or
-- the item's company is locked); a job renders exactly one composition.
CREATE TABLE media.render_jobs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    item_id         uuid NOT NULL REFERENCES media.items (id),
    composition_id  uuid NOT NULL REFERENCES media.compositions (id),
    purpose         text NOT NULL CHECK (purpose IN ('final', 'preview')),
    state           text NOT NULL DEFAULT 'queued'
                         CHECK (state IN ('queued', 'claimed', 'done', 'failed', 'cancelled')),
    spec            jsonb NOT NULL CHECK (jsonb_typeof(spec) = 'object'),
    attempts        int NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 10),
    claimed_at      timestamptz,
    finished_at     timestamptz,
    error           text CHECK (length(error) <= 500),
    files           jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(files) = 'array'),
    metrics         jsonb CHECK (metrics IS NULL OR jsonb_typeof(metrics) = 'object'),
    requested_by    text NOT NULL CHECK (length(requested_by) BETWEEN 1 AND 64),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX render_jobs_queue ON media.render_jobs (created_at) WHERE state IN ('queued', 'claimed');
CREATE UNIQUE INDEX render_jobs_one_open ON media.render_jobs (item_id)
    WHERE state IN ('queued', 'claimed');
CREATE TRIGGER render_jobs_immutable BEFORE UPDATE ON media.render_jobs
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'item_id', 'composition_id',
                                                      'purpose', 'spec', 'requested_by', 'created_at');

-- ======================================================= publish log ==
CREATE TABLE media.publish_log (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    item_id      uuid NOT NULL REFERENCES media.items (id),
    series_id    uuid REFERENCES media.series (id),
    action       text NOT NULL CHECK (action IN ('publish', 'unpublish')),
    channel      text NOT NULL CHECK (channel IN ('telegram', 'instagram')),
    placement    text NOT NULL CHECK (placement IN ('telegram_post', 'telegram_story', 'instagram_reel',
                                                    'instagram_story', 'instagram_post')),
    account      text NOT NULL CHECK (account ~ '^[a-z0-9][a-z0-9_.-]{{1,40}}$'),
    via          text NOT NULL CHECK (via IN ('api', 'manual')),
    outcome      text NOT NULL CHECK (outcome IN ('ok', 'error', 'skipped')),
    external_id  text CHECK (length(external_id) <= 200),
    url          text CHECK (length(url) <= 500),
    error        text CHECK (error ~ '^[a-z_]{{2,40}}$'),
    by_kind      text NOT NULL CHECK (by_kind IN ({ACTOR})),
    by_code      text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64),
    decision_id  uuid REFERENCES cartable.decisions (id),
    at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX publish_log_account ON media.publish_log (account, at DESC) WHERE outcome = 'ok';
CREATE INDEX publish_log_item ON media.publish_log (item_id, at);

-- ======================================================= role drafts ==
-- A role the work needs (§22.5): written by the department's manager, then
-- the originality check, the overseer's review, its own eval, the approval.
-- An active draft is a charter on the server, scoped to its company and
-- department; files in agents/ are never written.
CREATE TABLE people.role_drafts (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    ref              text NOT NULL UNIQUE
                          DEFAULT 'RD-' || lpad(nextval('people.role_draft_ref_seq')::text, 4, '0')
                          CHECK (ref ~ '^RD-[0-9]{{4,}}$'),
    department_id    uuid NOT NULL REFERENCES core.departments (id),
    role             text CHECK (role ~ '^[a-z][a-z0-9_]{{1,40}}$'),
    title_fa         text CHECK (length(title_fa) BETWEEN 1 AND 120),
    title_en         text CHECK (length(title_en) BETWEEN 1 AND 120),
    brief_md         text CHECK (length(brief_md) <= 10000),
    why_md           text CHECK (length(why_md) <= 10000),
    compared         text[] NOT NULL DEFAULT '{{}}' CHECK (cardinality(compared) <= 30),
    charter_md       text CHECK (length(charter_md) <= 30000),
    tools            text[] NOT NULL DEFAULT '{{}}' CHECK (cardinality(tools) <= 80),
    model            text CHECK (model IN ('claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5')),
    effort           text CHECK (effort IN ('low', 'medium', 'high', 'xhigh', 'max')),
    limits           jsonb CHECK (limits IS NULL OR jsonb_typeof(limits) = 'object'),
    eval             jsonb CHECK (eval IS NULL OR jsonb_typeof(eval) = 'object'),
    state            text NOT NULL DEFAULT 'drafting' CHECK (state IN ({DRAFT_STATES})),
    state_note_fa    text CHECK (length(state_note_fa) <= 1000),
    originality      jsonb CHECK (originality IS NULL OR jsonb_typeof(originality) = 'object'),
    review           jsonb CHECK (review IS NULL OR jsonb_typeof(review) = 'object'),
    eval_run         jsonb CHECK (eval_run IS NULL OR jsonb_typeof(eval_run) = 'object'),
    sha256           text CHECK (sha256 ~ '^[0-9a-f]{{64}}$'),
    requested_by_kind text NOT NULL CHECK (requested_by_kind IN ({ACTOR})),
    requested_by_code text NOT NULL CHECK (length(requested_by_code) BETWEEN 1 AND 64),
    written_by_code  text CHECK (length(written_by_code) BETWEEN 1 AND 64),
    work_id          uuid REFERENCES work.work (id),
    approver_kind    text CHECK (approver_kind IN ({ACTOR})),
    approver_code    text CHECK (length(approver_code) BETWEEN 1 AND 64),
    decision_id      uuid REFERENCES cartable.decisions (id),
    supersedes_id    uuid REFERENCES people.role_drafts (id),
    version          int NOT NULL DEFAULT 1,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    activated_at     timestamptz,
    retired_at       timestamptz
);
-- One active charter per role and company (a new version supersedes it).
CREATE UNIQUE INDEX role_drafts_active ON people.role_drafts (company_id, role) WHERE state = 'active';
CREATE INDEX role_drafts_company ON people.role_drafts (company_id, department_id, state);
CREATE TRIGGER role_drafts_immutable BEFORE UPDATE ON people.role_drafts
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'department_id',
                                                      'requested_by_kind', 'requested_by_code',
                                                      'created_at');
CREATE TRIGGER role_drafts_version BEFORE UPDATE ON people.role_drafts
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
-- A draft's own eval cases run through the academy's eval run (purpose role_draft).
ALTER TABLE academy.eval_runs DROP CONSTRAINT eval_runs_purpose_check;
ALTER TABLE academy.eval_runs ADD CONSTRAINT eval_runs_purpose_check
    CHECK (purpose IN ('manual', 'skill', 'teaching', 'shadow', 'role_draft'));
"""

# Data (§22.1): MEDIA for every operating company (the department, its asleep
# manager and its threads, nothing else), LEGAL and HQ-LGL for the holding.
DATA = r"""
INSERT INTO core.departments (company_id, code, name_fa, name_en, manager_title_fa, manager_title_en, sort)
SELECT c.id, 'MEDIA', 'رسانه و طراحی', 'Media and Design', 'مدیر رسانه و طراحی',
       'Head of Media and Design', 25
FROM core.companies c WHERE c.kind = 'company'
ON CONFLICT (company_id, code) DO NOTHING;

INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en, reports_to,
                            activity, role)
SELECT c.id, d.id, c.code || '-MEDIA-MGR', 'manager', 'مدیر رسانه و طراحی', 'Head of Media and Design',
       (SELECT e.id FROM core.employees e WHERE e.company_id = c.id AND e.kind = 'ceo'
          AND e.status <> 'dismissed' ORDER BY e.hired_at LIMIT 1),
       'sleeping', 'media_director'
FROM core.companies c JOIN core.departments d ON d.company_id = c.id AND d.code = 'MEDIA'
WHERE c.kind = 'company'
ON CONFLICT (code) DO NOTHING;

INSERT INTO msg.threads (code, kind, company_id, employee_id, title_fa)
SELECT e.code, 'manager', e.company_id, e.id, 'مدیر رسانه و طراحی'
FROM core.employees e JOIN core.companies c ON c.id = e.company_id
WHERE c.kind = 'company' AND e.code = c.code || '-MEDIA-MGR'
ON CONFLICT (code) DO NOTHING;

INSERT INTO msg.threads (code, kind, company_id, department_id, title_fa)
SELECT c.code || '-MEDIA', 'department', c.id, d.id, 'رسانه و طراحی'
FROM core.companies c JOIN core.departments d ON d.company_id = c.id AND d.code = 'MEDIA'
WHERE c.kind = 'company'
ON CONFLICT (code) DO NOTHING;

INSERT INTO core.departments (company_id, code, name_fa, name_en, manager_title_fa, manager_title_en, sort)
SELECT c.id, 'LEGAL', 'حقوقی', 'Legal', 'مشاور حقوقی', 'Legal Counsel', 30
FROM core.companies c WHERE c.kind = 'holding'
ON CONFLICT (company_id, code) DO NOTHING;

INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en, activity, role)
SELECT c.id, d.id, c.code || '-LGL', 'employee', 'مشاور حقوقی', 'Legal Counsel', 'sleeping', 'legal_counsel'
FROM core.companies c JOIN core.departments d ON d.company_id = c.id AND d.code = 'LEGAL'
WHERE c.kind = 'holding'
ON CONFLICT (code) DO NOTHING;
"""


def _kinds_sql(add: tuple[str, ...], drop: tuple[str, ...]) -> str:
    """Rewrite decisions_kind_check from the kinds it holds now (plus `add`,
    minus `drop`), NOT VALID: an earlier migration's kinds are kept whatever
    they are, and a sibling migration doing the same composes with this one."""
    added = ", ".join(f"'{k}'" for k in add)
    dropped = ", ".join(f"'{k}'" for k in drop)  # empty: ARRAY[]::text[] (a NULL would drop every kind)
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
                           'CHECK (kind IN (%s)) NOT VALID', kinds);
        END $$;
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
    # the owner edits mandate and identity (PUT …/mandate); the runtime records the identity read
    grants.append("GRANT UPDATE (mandate, identity_md) ON core.departments TO hq_api;")
    grants.append(f"GRANT UPDATE (identity_doc) ON agents.runs TO {APP_ROLES};")
    execute_script("\n".join(grants))
    execute_script(_kinds_sql(NEW_KINDS, ()))
    execute_script(DATA)


def downgrade() -> None:
    # The data rows stay (departments, positions and threads are never deleted).
    execute_script(_kinds_sql((), NEW_KINDS))
    execute_script(
        """
        REVOKE UPDATE (identity_doc) ON agents.runs FROM hq_api, hq_worker;
        REVOKE UPDATE (mandate, identity_md) ON core.departments FROM hq_api;
        ALTER TABLE agents.runs DROP COLUMN identity_doc;
        ALTER TABLE core.departments DROP COLUMN mandate, DROP COLUMN identity_md;
        ALTER TABLE academy.eval_runs DROP CONSTRAINT eval_runs_purpose_check;
        ALTER TABLE academy.eval_runs ADD CONSTRAINT eval_runs_purpose_check
            CHECK (purpose IN ('manual', 'skill', 'teaching', 'shadow')) NOT VALID;
        DROP TABLE people.role_drafts;
        DROP SEQUENCE people.role_draft_ref_seq;
        DROP SCHEMA media CASCADE;
        ALTER TABLE owner.stories DROP CONSTRAINT stories_kind_check;
        ALTER TABLE owner.stories ADD CONSTRAINT stories_kind_check
            CHECK (kind IN ('hire', 'deliverable', 'stars', 'milestone', 'post')) NOT VALID;
        """
    )
