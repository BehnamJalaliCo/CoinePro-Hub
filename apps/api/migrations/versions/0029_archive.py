"""Prompt 14 (contract §23): the archive of record of the holding and of every
company, with its open layer.

New schema `archive`. Every table carries company_id under FORCE RLS (the
once-per-query tenant policy of 0009); no row is ever deleted (disposal is
its own path: the files go, a tombstone stays).

The open layer (holding rows; the owner extends them from the app):
  levels           public 0, internal 10, confidential 20, secret 30 (data);
                   a used level's rank is fixed (trigger)
  clearance        one row per subject (role:<role> | employee:<code>):
                   grants [{scope: own|holding|all|<code>, level}] and the
                   metadata level (the archivist sees what it files)
  classes          RecordClass rows; every change is a new class_versions row
  class_versions   append-only snapshots (a record keeps its class version)
  fields           every field a class ever had: never deleted, only retired
  folders          FP-0001, the file plan (company_id = its scope)
  party_kinds · parties (PT-0001) · link_kinds
  retention_rules  RR-0001 · reminder_rules RM-0001 · automations AU-0001
  automation_runs  one row per run (append-only)
  sources          the closed list of what the hub files by itself (§23.8)
The records:
  records          AR-000001: scope (company_id), class, level (and its rank),
                   state, metadata (validated in code against the class
                   version), retention, the search vectors
  record_versions  n, manifest_sha256; sealed versions never change (trigger)
  record_files     a version's files: the archive's own stored copy (secret:
                   AES-GCM with a DEK wrapped by OpenBao transit
                   `archive-secret`), sha256 (plaintext) and stored_sha256
                   (what fixity re-hashes), the extracted text and OCR state
  intake           an upload's scan, hashes and text before it is filed
  links · holds (LH-0001) · reminders · access_log (append-only)
  fixity_runs (append-only) · tombstones (append-only)

Clearance in the database (prompt 14 red line 3): archive.can_see(rank,
scope) reads app.clearance, which the api sets with SET LOCAL for every
transaction that reads the archive (the owner and the hub's own jobs: all;
an agent: its role's grants). Without it nothing is visible. The policies of
records and of every table holding a record's metadata use it; a version, a
link or a reminder is visible only with its record; a file (content) only
within the content clearance, never by the archivist's metadata exception.

Also: decision kinds `archive_schema` and `archive_disposal` (the kind CHECK
rewritten NOT VALID, then validated here: this revision is the head); task
class `archive` (the archivist's runs, never on another provider);
agents.queue_run wakes a `system` employee that has a charter (the archivist
HQ-ARC; HQ-SYS has none and is never woken).

Revision ID: 0029
Revises: 0028_1
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0029"
down_revision = "0028_1"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"

CONFIG = (
    "archive.levels",
    "archive.clearance",
    "archive.classes",
    "archive.class_versions",
    "archive.fields",
    "archive.folders",
    "archive.party_kinds",
    "archive.parties",
    "archive.link_kinds",
    "archive.retention_rules",
    "archive.reminder_rules",
    "archive.automations",
    "archive.automation_runs",
    "archive.sources",
)
RECORD = (
    "archive.records",
    "archive.record_versions",
    "archive.record_files",
    "archive.intake",
    "archive.links",
    "archive.holds",
    "archive.reminders",
    "archive.access_log",
    "archive.fixity_runs",
    "archive.tombstones",
    "archive.destroy_queue",
)
TABLES = CONFIG + RECORD
APPEND_ONLY = (
    "archive.class_versions",
    "archive.automation_runs",
    "archive.access_log",
    "archive.fixity_runs",
    "archive.tombstones",
)
SEQUENCES = (
    "archive.record_ref_seq",
    "archive.folder_ref_seq",
    "archive.party_ref_seq",
    "archive.retention_ref_seq",
    "archive.hold_ref_seq",
    "archive.reminder_ref_seq",
    "archive.automation_ref_seq",
)
# Tables whose rows are a record's metadata (visible with the record only).
WITH_RECORD = ("archive.record_versions", "archive.links", "archive.reminders")
CLEARANCE_POLICY = {
    # metadata: the record's own rank, or the subject's metadata level for
    # what it filed itself
    "archive.records": "archive.can_see(level_rank, company_id, created_by_code)",
    # content: the content clearance only, through the record
    "archive.record_files": (
        "EXISTS (SELECT 1 FROM archive.records r WHERE r.id = record_id"
        " AND archive.can_see(r.level_rank, r.company_id))"
    ),
    "archive.tombstones": "archive.can_see(level_rank, company_id)",
    "archive.access_log": "archive.can_see(level_rank, company_id)",
}
CLEARANCE_POLICY.update(
    {t: "EXISTS (SELECT 1 FROM archive.records r WHERE r.id = record_id)" for t in WITH_RECORD}
)
TASK_CLASSES = (
    (
        "archive",
        "The archivist's work: classify drafts, complete metadata, links, the weekly gaps (prompt 14)",
    ),
)
QUEUE_RUN_OLD = "e.kind = 'system' OR e.status <> 'active' OR e.role IS NULL"
QUEUE_RUN_NEW = "e.status <> 'active' OR e.role IS NULL"

UPGRADE = r"""
CREATE SCHEMA archive;
GRANT USAGE ON SCHEMA archive TO @APP@;
CREATE SEQUENCE archive.record_ref_seq;
CREATE SEQUENCE archive.folder_ref_seq;
CREATE SEQUENCE archive.party_ref_seq;
CREATE SEQUENCE archive.retention_ref_seq;
CREATE SEQUENCE archive.hold_ref_seq;
CREATE SEQUENCE archive.reminder_ref_seq;
CREATE SEQUENCE archive.automation_ref_seq;

-- ============================================================ clearance ==
-- app.clearance (jsonb text, SET LOCAL by the api): {"all": true} for the
-- owner and the hub's own jobs; for an agent {"code": "<employee>",
-- "grants": {"<company uuid>"|"*": <rank>}, "meta": <rank>}. Missing or
-- empty: nothing is visible.
CREATE FUNCTION archive.clearance() RETURNS jsonb
    LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT CAST(NULLIF(current_setting('app.clearance', true), '') AS jsonb)
$$;

CREATE FUNCTION archive.rank_in(p_scope uuid) RETURNS int
    LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT CASE
        WHEN c IS NULL THEN -1
        WHEN COALESCE(c->>'all', 'false') = 'true' THEN 2147483647
        ELSE COALESCE((c->'grants'->>(p_scope::text))::int, (c->'grants'->>'*')::int, -1)
    END
    FROM (SELECT archive.clearance() AS c) x
$$;

-- Content: may the reader see a record of this rank in this scope?
CREATE FUNCTION archive.can_see(p_rank int, p_scope uuid) RETURNS boolean
    LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT p_rank <= archive.rank_in(p_scope)
$$;

-- Metadata: the content clearance, or what the subject filed itself up to
-- its metadata level (contract §23.12 metadata_level).
CREATE FUNCTION archive.can_see(p_rank int, p_scope uuid, p_filed_by text) RETURNS boolean
    LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT p_rank <= archive.rank_in(p_scope)
        OR (p_filed_by IS NOT NULL AND c IS NOT NULL AND c->>'code' = p_filed_by
            AND p_rank <= COALESCE((c->>'meta')::int, -1))
    FROM (SELECT archive.clearance() AS c) x
$$;
GRANT EXECUTE ON FUNCTION archive.clearance(), archive.rank_in(uuid), archive.can_see(int, uuid),
    archive.can_see(int, uuid, text) TO @APP@;

-- pg_trgm's word similarity for ranking titles (the app roles have no USAGE on
-- schema public, where the extension lives; its LIKE support needs none).
CREATE FUNCTION archive.title_similarity(p_q text, p_title text) RETURNS real
    LANGUAGE sql STABLE PARALLEL SAFE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT word_similarity(p_q, p_title)
$$;
GRANT EXECUTE ON FUNCTION archive.title_similarity(text, text) TO @APP@;

-- ======================================================= the open layer ==
CREATE TABLE archive.levels (
    key             text PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]{1,30}$'),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    title_fa        text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 60),
    rank            int NOT NULL UNIQUE CHECK (rank BETWEEN 0 AND 1000),
    color_index     int NOT NULL DEFAULT 0 CHECK (color_index BETWEEN 0 AND 11),
    watermark       boolean NOT NULL DEFAULT false,
    encrypt         boolean NOT NULL DEFAULT false,
    step_up_to_view boolean NOT NULL DEFAULT false,
    agents_max      boolean NOT NULL DEFAULT false,
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    version         int NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
-- The highest level an agent may be cleared for (seeded on confidential).
CREATE UNIQUE INDEX levels_one_agents_max ON archive.levels ((true)) WHERE agents_max;
CREATE TRIGGER levels_immutable BEFORE UPDATE ON archive.levels
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('key', 'company_id', 'created_at');
CREATE TRIGGER levels_version BEFORE UPDATE ON archive.levels
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

CREATE TABLE archive.clearance (
    subject         text PRIMARY KEY CHECK (subject ~ '^(role|employee):([a-z][a-z0-9_]{1,40}|\*|[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?)$'),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    grants          jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(grants) = 'array'
                                                     AND jsonb_array_length(grants) <= 100),
    metadata_level  text REFERENCES archive.levels (key),
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    version         int NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER clearance_immutable BEFORE UPDATE ON archive.clearance
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('subject', 'company_id', 'created_at');
CREATE TRIGGER clearance_version BEFORE UPDATE ON archive.clearance
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- A class: `spec` holds the RecordClass (contract §23.2) without its fields;
-- `fields` its current fields. Every change is a new class version.
CREATE TABLE archive.classes (
    key         text PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]{1,40}$'),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    spec        jsonb NOT NULL CHECK (jsonb_typeof(spec) = 'object'),
    fields      jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(fields) = 'array'
                                                  AND jsonb_array_length(fields) <= 200),
    status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    version     int NOT NULL DEFAULT 1,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER classes_immutable BEFORE UPDATE ON archive.classes
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('key', 'company_id', 'created_at');
CREATE TRIGGER classes_version BEFORE UPDATE ON archive.classes
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

CREATE TABLE archive.class_versions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    class_key       text NOT NULL REFERENCES archive.classes (key),
    version         int NOT NULL CHECK (version >= 1),
    spec            jsonb NOT NULL CHECK (jsonb_typeof(spec) = 'object'),
    fields          jsonb NOT NULL CHECK (jsonb_typeof(fields) = 'array'),
    created_by_kind text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service', 'system')),
    created_by_code text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (class_key, version)
);

-- Every field a class ever had (never deleted; `retired` keeps its values).
CREATE TABLE archive.fields (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    class_key       text NOT NULL REFERENCES archive.classes (key),
    key             text NOT NULL CHECK (key ~ '^[a-z][a-z0-9_]{1,40}$'),
    type            text NOT NULL CHECK (type IN ('text', 'long_text', 'number', 'money', 'percent', 'date',
                                                  'date_range', 'enum', 'multi_enum', 'boolean', 'party',
                                                  'company', 'ref', 'url', 'email', 'phone', 'id_code', 'iban')),
    spec            jsonb NOT NULL CHECK (jsonb_typeof(spec) = 'object'),
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    since_version   int NOT NULL CHECK (since_version >= 1),
    retired_version int,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (class_key, key)
);
CREATE TRIGGER fields_immutable BEFORE UPDATE ON archive.fields
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'class_key', 'key', 'type',
                                                      'since_version');

CREATE TABLE archive.folders (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    ref             text NOT NULL UNIQUE
                         DEFAULT 'FP-' || lpad(nextval('archive.folder_ref_seq')::text, 4, '0')
                         CHECK (ref ~ '^FP-[0-9]{4,}$'),
    seed_key        text UNIQUE CHECK (seed_key ~ '^[a-z][a-z0-9_:.-]{1,80}$'),
    parent_id       uuid REFERENCES archive.folders (id),
    title_fa        text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
    classes         text[] NOT NULL DEFAULT '{}' CHECK (cardinality(classes) <= 100),
    default_level   text REFERENCES archive.levels (key),
    sort            int NOT NULL DEFAULT 100,
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    version         int NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CHECK (parent_id IS DISTINCT FROM id)
);
CREATE INDEX folders_scope ON archive.folders (company_id, sort);
CREATE TRIGGER folders_immutable BEFORE UPDATE ON archive.folders
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'created_at');
CREATE TRIGGER folders_version BEFORE UPDATE ON archive.folders
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

CREATE TABLE archive.party_kinds (
    key               text PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]{1,40}$'),
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    title_fa          text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 100),
    identifier_fields jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(identifier_fields) = 'array'),
    status            text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    version           int NOT NULL DEFAULT 1,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER party_kinds_immutable BEFORE UPDATE ON archive.party_kinds
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('key', 'company_id', 'created_at');
CREATE TRIGGER party_kinds_version BEFORE UPDATE ON archive.party_kinds
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

CREATE TABLE archive.parties (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    ref             text NOT NULL UNIQUE
                         DEFAULT 'PT-' || lpad(nextval('archive.party_ref_seq')::text, 4, '0')
                         CHECK (ref ~ '^PT-[0-9]{4,}$'),
    kind            text NOT NULL REFERENCES archive.party_kinds (key),
    name_fa         text NOT NULL CHECK (length(name_fa) BETWEEN 1 AND 200),
    name_en         text CHECK (length(name_en) <= 200),
    identifiers     jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(identifiers) = 'object'),
    scopes          text[] NOT NULL DEFAULT '{}' CHECK (cardinality(scopes) <= 200),
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    created_by_kind text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service', 'system')),
    created_by_code text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
    version         int NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX parties_name ON archive.parties USING gin (core.fa_normalize(name_fa) gin_trgm_ops);
CREATE TRIGGER parties_immutable BEFORE UPDATE ON archive.parties
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'created_by_kind',
                                                      'created_by_code', 'created_at');
CREATE TRIGGER parties_version BEFORE UPDATE ON archive.parties
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

CREATE TABLE archive.link_kinds (
    key         text PRIMARY KEY CHECK (key ~ '^[a-z][a-z0-9_]{1,40}$'),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    title_fa    text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 100),
    inverse_fa  text NOT NULL CHECK (length(inverse_fa) BETWEEN 1 AND 100),
    to_kinds    text[] NOT NULL CHECK (cardinality(to_kinds) BETWEEN 1 AND 20),
    status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    version     int NOT NULL DEFAULT 1,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER link_kinds_immutable BEFORE UPDATE ON archive.link_kinds
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('key', 'company_id', 'created_at');
CREATE TRIGGER link_kinds_version BEFORE UPDATE ON archive.link_kinds
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

CREATE TABLE archive.retention_rules (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    ref         text NOT NULL UNIQUE
                     DEFAULT 'RR-' || lpad(nextval('archive.retention_ref_seq')::text, 4, '0')
                     CHECK (ref ~ '^RR-[0-9]{4,}$'),
    seed_key    text UNIQUE CHECK (seed_key ~ '^[a-z][a-z0-9_:.-]{1,80}$'),
    title_fa    text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
    trigger     text NOT NULL CHECK (trigger ~ '^(filed|case_closed|superseded|field:[a-z][a-z0-9_]{1,40})$'),
    keep        jsonb NOT NULL CHECK (jsonb_typeof(keep) IN ('object', 'string')),
    then_do     text NOT NULL CHECK (then_do IN ('review', 'dispose_card')),
    status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    version     int NOT NULL DEFAULT 1,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER retention_rules_immutable BEFORE UPDATE ON archive.retention_rules
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'created_at');
CREATE TRIGGER retention_rules_version BEFORE UPDATE ON archive.retention_rules
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

CREATE TABLE archive.reminder_rules (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    ref         text NOT NULL UNIQUE
                     DEFAULT 'RM-' || lpad(nextval('archive.reminder_ref_seq')::text, 4, '0')
                     CHECK (ref ~ '^RM-[0-9]{4,}$'),
    seed_key    text UNIQUE CHECK (seed_key ~ '^[a-z][a-z0-9_:.-]{1,80}$'),
    class_key   text NOT NULL REFERENCES archive.classes (key),
    field       text NOT NULL CHECK (field ~ '^[a-z][a-z0-9_]{1,40}$'),
    lead_days   int[] NOT NULL CHECK (cardinality(lead_days) BETWEEN 1 AND 10),
    to_whom     jsonb NOT NULL CHECK (jsonb_typeof(to_whom) IN ('object', 'string')),
    channel     text NOT NULL CHECK (channel IN ('cartable', 'digest')),
    status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    version     int NOT NULL DEFAULT 1,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER reminder_rules_immutable BEFORE UPDATE ON archive.reminder_rules
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'created_at');
CREATE TRIGGER reminder_rules_version BEFORE UPDATE ON archive.reminder_rules
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

CREATE TABLE archive.automations (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    ref         text NOT NULL UNIQUE
                     DEFAULT 'AU-' || lpad(nextval('archive.automation_ref_seq')::text, 4, '0')
                     CHECK (ref ~ '^AU-[0-9]{4,}$'),
    title_fa    text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
    on_event    text NOT NULL CHECK (on_event IN ('filed', 'sealed', 'reminder_due', 'retention_due',
                                                  'hold_set', 'version_added')),
    when_cond   jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(when_cond) = 'object'),
    actions     jsonb NOT NULL CHECK (jsonb_typeof(actions) = 'array'
                                      AND jsonb_array_length(actions) BETWEEN 1 AND 10),
    status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    version     int NOT NULL DEFAULT 1,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER automations_immutable BEFORE UPDATE ON archive.automations
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'created_at');
CREATE TRIGGER automations_version BEFORE UPDATE ON archive.automations
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

CREATE TABLE archive.automation_runs (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id    uuid NOT NULL REFERENCES core.companies (id),
    automation_id uuid NOT NULL REFERENCES archive.automations (id),
    record_ref    text CHECK (record_ref ~ '^AR-[0-9]{6,}$'),
    event         text NOT NULL CHECK (event ~ '^[a-z_]{2,30}$'),
    outcome       text NOT NULL CHECK (outcome IN ('done', 'partial', 'deferred', 'failed')),
    actions       jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(actions) = 'array'),
    at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX automation_runs_recent ON archive.automation_runs (automation_id, at DESC);

CREATE TABLE archive.sources (
    key         text PRIMARY KEY CHECK (key IN ('charter_sealed', 'resolution_month', 'brand_sealed',
                                                'founding_registration', 'legal_email', 'case_closed',
                                                'server_plan_sealed', 'backup_restore_test')),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    title_fa    text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
    class_key   text NOT NULL REFERENCES archive.classes (key),
    enabled     boolean NOT NULL DEFAULT true,
    filed       int NOT NULL DEFAULT 0 CHECK (filed >= 0),
    last_at     timestamptz,
    note_fa     text CHECK (length(note_fa) <= 500),
    version     int NOT NULL DEFAULT 1,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER sources_immutable BEFORE UPDATE ON archive.sources
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('key', 'company_id', 'created_at');
CREATE TRIGGER sources_version BEFORE UPDATE ON archive.sources
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- ============================================================= records ==
CREATE TABLE archive.records (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         uuid NOT NULL REFERENCES core.companies (id),
    ref                text NOT NULL UNIQUE
                            DEFAULT 'AR-' || lpad(nextval('archive.record_ref_seq')::text, 6, '0')
                            CHECK (ref ~ '^AR-[0-9]{6,}$'),
    class_key          text REFERENCES archive.classes (key),
    class_version      int,
    title_fa           text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    folder_id          uuid REFERENCES archive.folders (id),
    level              text NOT NULL REFERENCES archive.levels (key),
    level_rank         int NOT NULL CHECK (level_rank BETWEEN 0 AND 1000),
    state              text NOT NULL CHECK (state IN ('draft', 'filed', 'sealed', 'superseded', 'disposed')),
    metadata           jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata) = 'object'),
    doc_date           date,
    parties            jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(parties) = 'array'
                                                         AND jsonb_array_length(parties) <= 50),
    party_refs         text[] NOT NULL DEFAULT '{}',
    watch_dates        date[] NOT NULL DEFAULT '{}',
    current_version    int NOT NULL DEFAULT 1 CHECK (current_version >= 1),
    source_kind        text NOT NULL CHECK (source_kind IN ('owner', 'agent', 'system')),
    source_ref         text CHECK (length(source_ref) <= 120),
    suggestion         jsonb CHECK (suggestion IS NULL OR jsonb_typeof(suggestion) = 'object'),
    retention_rule_id  uuid REFERENCES archive.retention_rules (id),
    trigger_at         date,
    due_at             date,
    disposable         boolean NOT NULL DEFAULT false,
    disposal_ref       text CHECK (disposal_ref ~ '^D-[0-9]{6,}$'),
    disposal_kept      boolean NOT NULL DEFAULT false,
    review_work_ref    text,
    due_seen_at        timestamptz,
    created_by_kind    text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service', 'system')),
    created_by_code    text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
    created_at         timestamptz NOT NULL DEFAULT now(),
    filed_at           timestamptz,
    sealed_at          timestamptz,
    disposed_at        timestamptz,
    meta_tsv           tsvector,
    sens_tsv           tsvector,
    text_tsv           tsvector,
    version            int NOT NULL DEFAULT 1,
    updated_at         timestamptz NOT NULL DEFAULT now(),
    CHECK (state = 'draft' OR class_key IS NOT NULL),
    CHECK ((class_key IS NULL) = (class_version IS NULL)),
    CHECK ((state = 'sealed') = (sealed_at IS NOT NULL)),
    CHECK ((state = 'disposed') = (disposed_at IS NOT NULL)),
    CHECK (state = 'draft' OR filed_at IS NOT NULL)
);
-- One system record per event of its source (a sealed charter version, a month...).
CREATE UNIQUE INDEX records_source ON archive.records (source_ref) WHERE source_kind = 'system';
CREATE INDEX records_list ON archive.records (company_id, state, created_at DESC);
CREATE INDEX records_class ON archive.records (class_key, state);
CREATE INDEX records_due ON archive.records (due_at) WHERE state IN ('filed', 'sealed', 'superseded');
CREATE INDEX records_meta_tsv ON archive.records USING gin (meta_tsv);
CREATE INDEX records_text_tsv ON archive.records USING gin (text_tsv);
CREATE INDEX records_sens_tsv ON archive.records USING gin (sens_tsv);
CREATE INDEX records_title_trgm ON archive.records USING gin (core.fa_normalize(title_fa) gin_trgm_ops);
CREATE TRIGGER records_immutable BEFORE UPDATE ON archive.records
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'source_kind', 'source_ref',
                                                      'created_by_kind', 'created_by_code', 'created_at');
CREATE TRIGGER records_version BEFORE UPDATE ON archive.records
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- A sealed record keeps its title, class, metadata, parties and folder; only
-- its access level, retention bookkeeping and state (a new version, its
-- supersession, its disposal) change (SQLSTATE HQR01 -> 409 sealed_record).
CREATE FUNCTION archive.guard_record() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.state = 'disposed' THEN
            RAISE EXCEPTION 'archive.records: % is disposed', OLD.ref USING ERRCODE = 'HQR01';
        END IF;
        IF OLD.state = 'sealed' AND NEW.state = 'sealed'
           AND (NEW.title_fa, NEW.class_key, NEW.class_version, NEW.metadata, NEW.parties, NEW.folder_id)
               IS DISTINCT FROM (OLD.title_fa, OLD.class_key, OLD.class_version, OLD.metadata, OLD.parties,
                                 OLD.folder_id) THEN
            RAISE EXCEPTION 'archive.records: % is sealed', OLD.ref USING ERRCODE = 'HQR01';
        END IF;
        RETURN NEW;
    END $$;
CREATE TRIGGER records_guard BEFORE UPDATE ON archive.records
    FOR EACH ROW EXECUTE FUNCTION archive.guard_record();

CREATE TABLE archive.record_versions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    record_id       uuid NOT NULL REFERENCES archive.records (id),
    n               int NOT NULL CHECK (n >= 1),
    manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    note_fa         text CHECK (length(note_fa) <= 2000),
    state           text NOT NULL DEFAULT 'current' CHECK (state IN ('current', 'superseded')),
    sealed          boolean NOT NULL DEFAULT false,
    sealed_at       timestamptz,
    seal_step_up_id uuid,
    created_by_kind text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service', 'system')),
    created_by_code text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (record_id, n),
    CHECK (sealed = (sealed_at IS NOT NULL))
);
CREATE UNIQUE INDEX record_versions_one_current ON archive.record_versions (record_id) WHERE state = 'current';
CREATE TRIGGER record_versions_immutable BEFORE UPDATE ON archive.record_versions
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'record_id', 'n', 'manifest_sha256',
                                                      'note_fa', 'created_by_kind', 'created_by_code',
                                                      'created_at');
-- A sealed version never changes again, except that a newer version
-- supersedes it; a seal is never taken back.
CREATE FUNCTION archive.guard_version() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.sealed AND (NOT NEW.sealed OR NEW.sealed_at IS DISTINCT FROM OLD.sealed_at
                           OR NEW.seal_step_up_id IS DISTINCT FROM OLD.seal_step_up_id
                           OR (NEW.state <> OLD.state AND NEW.state <> 'superseded')) THEN
            RAISE EXCEPTION 'archive.record_versions: a sealed version is immutable' USING ERRCODE = 'HQR01';
        END IF;
        IF OLD.state = 'superseded' AND NEW.state <> 'superseded' THEN
            RAISE EXCEPTION 'archive.record_versions: a superseded version stays superseded'
                USING ERRCODE = 'HQR01';
        END IF;
        RETURN NEW;
    END $$;
CREATE TRIGGER record_versions_guard BEFORE UPDATE ON archive.record_versions
    FOR EACH ROW EXECUTE FUNCTION archive.guard_version();

CREATE TABLE archive.record_files (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    record_id       uuid NOT NULL REFERENCES archive.records (id),
    version_n       int NOT NULL CHECK (version_n >= 1),
    file_id         uuid NOT NULL,
    name            text NOT NULL CHECK (length(name) BETWEEN 1 AND 255),
    mime            text NOT NULL CHECK (length(mime) BETWEEN 3 AND 100),
    size_bytes      bigint NOT NULL CHECK (size_bytes >= 0),
    sha256          text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    stored_sha256   text NOT NULL CHECK (stored_sha256 ~ '^[0-9a-f]{64}$'),
    storage_key     text CHECK (storage_key ~ '^[0-9a-f]{32}$'),
    encrypted       boolean NOT NULL DEFAULT false,
    wrapped_dek     text CHECK (length(wrapped_dek) <= 1000),
    pages           int CHECK (pages >= 0),
    text_state      text NOT NULL DEFAULT 'none' CHECK (text_state IN ('none', 'text_layer', 'ocr', 'failed')),
    ocr_wanted      boolean NOT NULL DEFAULT false,
    ocr_attempts    int NOT NULL DEFAULT 0 CHECK (ocr_attempts BETWEEN 0 AND 20),
    ocr_confidence  numeric(5, 4) CHECK (ocr_confidence BETWEEN 0 AND 1),
    low_conf_pages  int[] NOT NULL DEFAULT '{}',
    text            text CHECK (length(text) <= 400000),
    quarantined     boolean NOT NULL DEFAULT false,
    destroyed_at    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (record_id, version_n, file_id),
    CHECK (encrypted = (wrapped_dek IS NOT NULL) OR destroyed_at IS NOT NULL),
    CHECK (destroyed_at IS NULL OR (storage_key IS NULL AND wrapped_dek IS NULL AND text IS NULL)),
    CHECK (destroyed_at IS NOT NULL OR storage_key IS NOT NULL)
);
CREATE INDEX record_files_record ON archive.record_files (record_id, version_n);
CREATE INDEX record_files_ocr ON archive.record_files (created_at) WHERE ocr_wanted AND destroyed_at IS NULL;
CREATE TRIGGER record_files_immutable BEFORE UPDATE ON archive.record_files
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'record_id', 'version_n', 'file_id',
                                                      'name', 'mime', 'size_bytes', 'sha256', 'created_at');
-- The stored bytes and their key change only with the file's destruction
-- (once), or when its record's level crosses the encryption boundary (the
-- same plaintext, sha256 unchanged, stored again encrypted or in clear).
CREATE FUNCTION archive.guard_file() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.destroyed_at IS NOT NULL THEN
            RAISE EXCEPTION 'archive.record_files: a destroyed file stays destroyed' USING ERRCODE = 'HQR01';
        END IF;
        IF (NEW.storage_key, NEW.stored_sha256, NEW.encrypted, NEW.wrapped_dek)
           IS DISTINCT FROM (OLD.storage_key, OLD.stored_sha256, OLD.encrypted, OLD.wrapped_dek) THEN
            IF NEW.destroyed_at IS NOT NULL THEN
                IF NEW.stored_sha256 <> OLD.stored_sha256 OR NEW.encrypted <> OLD.encrypted THEN
                    RAISE EXCEPTION 'archive.record_files: a destruction keeps the hashes'
                        USING ERRCODE = 'HQR01';
                END IF;
            ELSIF NEW.encrypted = OLD.encrypted OR NEW.storage_key IS NULL THEN
                RAISE EXCEPTION 'archive.record_files: the stored file is immutable' USING ERRCODE = 'HQR01';
            END IF;
        END IF;
        NEW.updated_at := now();
        RETURN NEW;
    END $$;
CREATE TRIGGER record_files_guard BEFORE UPDATE ON archive.record_files
    FOR EACH ROW EXECUTE FUNCTION archive.guard_file();

-- An upload's intake (§23.12 POST /archive/intake): the secret scan passed,
-- its hashes and its text, before any record holds it.
CREATE TABLE archive.intake (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    file_id         uuid NOT NULL UNIQUE,
    name            text NOT NULL CHECK (length(name) BETWEEN 1 AND 255),
    mime            text NOT NULL CHECK (length(mime) BETWEEN 3 AND 100),
    size_bytes      bigint NOT NULL CHECK (size_bytes >= 0),
    sha256          text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    pages           int CHECK (pages >= 0),
    text_state      text NOT NULL CHECK (text_state IN ('none', 'text_layer', 'ocr', 'failed')),
    ocr_confidence  numeric(5, 4) CHECK (ocr_confidence BETWEEN 0 AND 1),
    low_conf_pages  int[] NOT NULL DEFAULT '{}',
    text            text CHECK (length(text) <= 400000),
    suggestion      jsonb CHECK (suggestion IS NULL OR jsonb_typeof(suggestion) = 'object'),
    by_kind         text NOT NULL CHECK (by_kind IN ('owner', 'agent', 'service', 'system')),
    by_code         text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER intake_immutable BEFORE UPDATE ON archive.intake
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'file_id', 'sha256', 'created_at');

CREATE TABLE archive.links (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    record_id       uuid NOT NULL REFERENCES archive.records (id),
    kind            text NOT NULL REFERENCES archive.link_kinds (key),
    to_kind         text NOT NULL CHECK (to_kind IN ('decision', 'resolution', 'case', 'work', 'record',
                                                     'employee', 'revenue_account', 'party', 'company')),
    to_ref          text NOT NULL CHECK (length(to_ref) BETWEEN 1 AND 80),
    title_fa        text CHECK (length(title_fa) <= 300),
    sealed          boolean NOT NULL DEFAULT false,
    by_kind         text NOT NULL CHECK (by_kind IN ('owner', 'agent', 'service', 'system')),
    by_code         text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64),
    created_at      timestamptz NOT NULL DEFAULT now(),
    removed_at      timestamptz,
    removed_by      text CHECK (length(removed_by) <= 64),
    CHECK (NOT (sealed AND removed_at IS NOT NULL))
);
CREATE UNIQUE INDEX links_one ON archive.links (record_id, kind, to_kind, to_ref) WHERE removed_at IS NULL;
CREATE INDEX links_to ON archive.links (to_kind, to_ref) WHERE removed_at IS NULL;
CREATE TRIGGER links_immutable BEFORE UPDATE ON archive.links
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'record_id', 'kind', 'to_kind', 'to_ref',
                                                      'by_kind', 'by_code', 'created_at');
CREATE TRIGGER links_kept BEFORE UPDATE ON archive.links
    FOR EACH ROW WHEN (OLD.sealed AND NEW.removed_at IS NOT NULL OR OLD.removed_at IS NOT NULL)
    EXECUTE FUNCTION core.reject_change();

CREATE TABLE archive.holds (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    ref             text NOT NULL UNIQUE
                         DEFAULT 'LH-' || lpad(nextval('archive.hold_ref_seq')::text, 4, '0')
                         CHECK (ref ~ '^LH-[0-9]{4,}$'),
    title_fa        text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    case_ref        text CHECK (case_ref ~ '^LC-[0-9]{4,}$'),
    reason_md       text NOT NULL CHECK (length(reason_md) BETWEEN 1 AND 20000),
    scope           jsonb NOT NULL CHECK (jsonb_typeof(scope) = 'object'),
    record_refs     text[] NOT NULL DEFAULT '{}',
    folder_ids      uuid[] NOT NULL DEFAULT '{}',
    classes         text[] NOT NULL DEFAULT '{}',
    party_refs      text[] NOT NULL DEFAULT '{}',
    from_date       date,
    to_date         date,
    state           text NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'released')),
    placed_by_kind  text NOT NULL CHECK (placed_by_kind IN ('owner', 'agent')),
    placed_by_code  text NOT NULL CHECK (length(placed_by_code) BETWEEN 1 AND 64),
    placed_at       timestamptz NOT NULL DEFAULT now(),
    released_at     timestamptz,
    release_step_up_id uuid,
    version         int NOT NULL DEFAULT 1,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'released') = (released_at IS NOT NULL)),
    CHECK (cardinality(record_refs) > 0 OR cardinality(folder_ids) > 0 OR cardinality(classes) > 0
           OR cardinality(party_refs) > 0 OR from_date IS NOT NULL OR to_date IS NOT NULL)
);
CREATE TRIGGER holds_immutable BEFORE UPDATE ON archive.holds
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'title_fa', 'case_ref',
                                                      'reason_md', 'scope', 'record_refs', 'folder_ids',
                                                      'classes', 'party_refs', 'from_date', 'to_date',
                                                      'placed_by_kind', 'placed_by_code', 'placed_at');
CREATE TRIGGER holds_version BEFORE UPDATE ON archive.holds
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
-- A released hold stays released.
CREATE TRIGGER holds_once BEFORE UPDATE ON archive.holds
    FOR EACH ROW WHEN (OLD.state = 'released') EXECUTE FUNCTION core.reject_change();

-- Is a record under an active legal hold? records: an explicit list; the
-- other facets must all match (contract §23.12 Hold).
CREATE FUNCTION archive.held_by(p_record uuid) RETURNS text[]
    LANGUAGE sql STABLE AS $$
    SELECT COALESCE(array_agg(h.ref ORDER BY h.ref), '{}')
    FROM archive.holds h, archive.records r
    WHERE r.id = p_record AND h.state = 'active'
      AND (r.ref = ANY (h.record_refs)
           OR ((cardinality(h.folder_ids) > 0 OR cardinality(h.classes) > 0 OR cardinality(h.party_refs) > 0
                OR h.from_date IS NOT NULL OR h.to_date IS NOT NULL)
               AND (cardinality(h.folder_ids) = 0 OR r.folder_id = ANY (h.folder_ids))
               AND (cardinality(h.classes) = 0 OR r.class_key = ANY (h.classes))
               AND (cardinality(h.party_refs) = 0 OR r.party_refs && h.party_refs)
               AND (h.from_date IS NULL OR COALESCE(r.doc_date, r.created_at::date) >= h.from_date)
               AND (h.to_date IS NULL OR COALESCE(r.doc_date, r.created_at::date) <= h.to_date)))
$$;
GRANT EXECUTE ON FUNCTION archive.held_by(uuid) TO @APP@;

CREATE TABLE archive.reminders (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    record_id       uuid NOT NULL REFERENCES archive.records (id),
    rule_id         uuid REFERENCES archive.reminder_rules (id),
    field           text NOT NULL CHECK (field ~ '^[a-z][a-z0-9_]{1,40}$'),
    at              date NOT NULL,
    lead_days       int NOT NULL CHECK (lead_days BETWEEN 0 AND 3650),
    due_at          date NOT NULL,
    channel         text NOT NULL CHECK (channel IN ('cartable', 'digest')),
    to_whom         jsonb NOT NULL CHECK (jsonb_typeof(to_whom) IN ('object', 'string')),
    state           text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'sent', 'done')),
    sent_at         timestamptz,
    done_at         timestamptz,
    done_by         text CHECK (length(done_by) <= 64),
    notification_id uuid,
    work_ref        text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'done') = (done_at IS NOT NULL))
);
CREATE UNIQUE INDEX reminders_once ON archive.reminders (record_id, field, at, lead_days);
CREATE INDEX reminders_open ON archive.reminders (state, due_at) WHERE state <> 'done';
CREATE TRIGGER reminders_immutable BEFORE UPDATE ON archive.reminders
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'record_id', 'rule_id', 'field', 'at',
                                                      'lead_days', 'due_at', 'created_at');

-- Who viewed or downloaded what, when (the owner reads it; append-only).
CREATE TABLE archive.access_log (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    record_id   uuid NOT NULL REFERENCES archive.records (id),
    level_rank  int NOT NULL,
    at          timestamptz NOT NULL DEFAULT now(),
    actor_kind  text NOT NULL CHECK (actor_kind IN ('owner', 'agent', 'service', 'system')),
    actor_code  text NOT NULL CHECK (length(actor_code) BETWEEN 1 AND 64),
    action      text NOT NULL CHECK (action IN ('view', 'download', 'metadata', 'level')),
    file_id     uuid,
    version_n   int,
    step_up     boolean NOT NULL DEFAULT false,
    watermarked boolean NOT NULL DEFAULT false,
    level_from  text,
    level_to    text
);
CREATE INDEX access_log_record ON archive.access_log (record_id, at DESC);

CREATE TABLE archive.fixity_runs (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    at          timestamptz NOT NULL DEFAULT now(),
    kind        text NOT NULL CHECK (kind IN ('nightly', 'weekly', 'manual')),
    slice       int CHECK (slice BETWEEN 0 AND 6),
    checked     int NOT NULL CHECK (checked >= 0),
    failed      jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(failed) = 'array'),
    seconds     numeric(10, 3) NOT NULL DEFAULT 0,
    next_at     timestamptz
);
CREATE INDEX fixity_runs_recent ON archive.fixity_runs (at DESC);

-- Stored objects to remove after the transaction that destroyed them has
-- committed (a sealed disposal, a re-store across the encryption boundary):
-- the bytes go only once the rows say so, and a crash leaves the key here.
CREATE TABLE archive.destroy_queue (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    storage_key text NOT NULL CHECK (storage_key ~ '^[0-9a-f]{32}$'),
    why         text NOT NULL CHECK (why IN ('disposal', 'restore', 'intake')),
    ref         text CHECK (length(ref) <= 80),
    queued_at   timestamptz NOT NULL DEFAULT now(),
    done_at     timestamptz
);
CREATE INDEX destroy_queue_open ON archive.destroy_queue (queued_at) WHERE done_at IS NULL;
CREATE TRIGGER destroy_queue_immutable BEFORE UPDATE ON archive.destroy_queue
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'storage_key', 'why', 'ref', 'queued_at');

-- What stays of a disposed record (contract §23.0): never changed, never deleted.
CREATE TABLE archive.tombstones (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    record_id    uuid NOT NULL UNIQUE REFERENCES archive.records (id),
    ref          text NOT NULL CHECK (ref ~ '^AR-[0-9]{6,}$'),
    class_key    text,
    title_fa     text NOT NULL,
    level_rank   int NOT NULL,
    dates        jsonb NOT NULL CHECK (jsonb_typeof(dates) = 'object'),
    hashes       jsonb NOT NULL CHECK (jsonb_typeof(hashes) = 'array'),
    decision_ref text NOT NULL CHECK (decision_ref ~ '^D-[0-9]{6,}$'),
    at           timestamptz NOT NULL DEFAULT now()
);
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
    cond = TENANT
    if table in CLEARANCE_POLICY:
        cond = f"{TENANT} AND {CLEARANCE_POLICY[table]}"
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({cond}) WITH CHECK ({cond});
        CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
        CREATE TRIGGER {name}_no_delete BEFORE DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
    """


def _queue_run(condition: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION agents.queue_run(p_employee uuid, p_trigger text, p_work uuid, p_thread uuid,
                                                    p_reason text, p_priority text) RETURNS uuid
            LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            DECLARE
                e record;
                rid uuid;
            BEGIN
                SELECT id, company_id, kind, status, role INTO e FROM core.employees WHERE id = p_employee;
                IF NOT FOUND OR {condition} THEN
                    RETURN NULL;
                END IF;
                INSERT INTO agents.runs (company_id, employee_id, work_id, thread_id, trigger, reason, priority)
                VALUES (e.company_id, e.id, p_work, p_thread, p_trigger, left(COALESCE(p_reason, ''), 200),
                        COALESCE(p_priority, 'P3'))
                ON CONFLICT (employee_id, COALESCE(work_id, '00000000-0000-0000-0000-000000000000'::uuid),
                             COALESCE(thread_id, '00000000-0000-0000-0000-000000000000'::uuid))
                    WHERE state = 'queued' DO NOTHING
                RETURNING id INTO rid;
                IF rid IS NULL THEN
                    SELECT id INTO rid FROM agents.runs
                     WHERE employee_id = e.id AND state = 'queued'
                       AND work_id IS NOT DISTINCT FROM p_work AND thread_id IS NOT DISTINCT FROM p_thread;
                END IF;
                RETURN rid;
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
    execute_script("\n".join(grants))
    execute_script(_queue_run(QUEUE_RUN_NEW))
    # An owner upload the archive took over (or refused for a secret) loses
    # its extracted text and transcript with its bytes (prompt 14 §3).
    execute_script("GRANT UPDATE (transcript) ON files.processing TO hq_api;")
    execute_script(
        # Added NOT VALID, then validated in its own statement (the head
        # validates: every earlier re-add is NOT VALID, so a down-and-up run
        # of the migrations keeps every later revision's rows).
        _kinds_sql(
            "cartable.decisions",
            "decisions_kind_check",
            ("archive_schema", "archive_disposal"),
            (),
            False,
        )
    )
    execute_script(
        """ALTER TABLE cartable.decisions VALIDATE CONSTRAINT decisions_kind_check;
           ALTER TABLE msg.threads VALIDATE CONSTRAINT threads_kind_check;"""
    )
    classes = ",\n".join(
        "('{}', false, '{}')".format(k, d.replace("'", "''")) for k, d in TASK_CLASSES
    )
    execute_script(
        f"""INSERT INTO llm.task_classes (key, transferable, description)
            VALUES {classes} ON CONFLICT (key) DO NOTHING;"""
    )


def downgrade() -> None:
    # Data stays out of reach, never rewritten: archive cards are kept (the
    # CHECK NOT VALID); the archive schema goes.
    execute_script(
        _kinds_sql(
            "cartable.decisions",
            "decisions_kind_check",
            (),
            ("archive_schema", "archive_disposal"),
            False,
        )
        + _queue_run(QUEUE_RUN_OLD)
        + "REVOKE UPDATE (transcript) ON files.processing FROM hq_api;"
        + "DROP SCHEMA archive CASCADE;"
    )
