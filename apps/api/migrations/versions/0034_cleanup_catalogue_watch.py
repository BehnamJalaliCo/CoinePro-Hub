"""Prompt 19 (contract §28 ⟨1.10⟩): the owner's clean-up of outputs, the
company catalogue, the watch and the council's robustness.

- §28.1 Delete for good: `cartable.owner_delete_deliverables` (SECURITY
  DEFINER, owner hq) removes the given deliverables, their ratings, the
  overseer's claims about them and the weekly letters made of them, and the
  files only they used (it answers the storage keys; the api removes the
  blobs). A review's minutes keep their review (the link is cleared). The
  append-only guards (core.reject_change, files.guard_change) let those
  DELETEs through only while `hq.owner_delete = 'deliverables'` is set in
  the same transaction, as the owner role hq, which only this function does.
  Archive records the outputs were filed into stay.
- §28.2 infra.catalogues: one deep extraction of a company per run (its jobs
  on every paired server, the sections, the archive record and the
  deliverable).
- §28.3 ops.client_errors: the apps' own error log, masked on the device and
  again on the hub; ops.watch_runs: one row per periodic watch duty (week,
  month), so a duty runs once. oversight.findings: `kind` (the watch's),
  `fix_md` and `fix` (a work item, a Workshop session or a card).
- §28.4 work.councils.note_fa (one answer is said plainly, no synthesis);
  substitutes.players.web_error_until: a web recipe that failed twice
  takes the player out of the next councils until then; substitutes.calls
  .attempt: a call retried once (another model, a reloaded profile).

Every new table carries company_id under FORCE RLS; nothing else is deleted.

Revision ID: 0034
Revises: 0033
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
OWNER_DELETE_TABLES = (
    "'cartable.deliverables', 'cartable.ratings', 'quality.claims', 'reports.briefings', "
    "'reports.ceo_letters'"
)

UPGRADE = f"""
CREATE OR REPLACE FUNCTION core.reject_change() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    -- core.purge_company (as hq) deletes a company that has no history
    IF TG_OP = 'DELETE' AND current_user = 'hq'
       AND COALESCE(current_setting('hq.purge_company', true), '') <> '' THEN
        RETURN OLD;
    END IF;
    -- ⟨1.10⟩ cartable.owner_delete_deliverables (as hq): the owner's delete for good
    IF TG_OP = 'DELETE' AND current_user = 'hq'
       AND COALESCE(current_setting('hq.owner_delete', true), '') = 'deliverables'
       AND format('%s.%s', TG_TABLE_SCHEMA, TG_TABLE_NAME) IN ({OWNER_DELETE_TABLES}) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION '%.% is append-only (% rejected)', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'HQA01';
END $$;

CREATE OR REPLACE FUNCTION files.guard_change() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    -- (no app role may DELETE here at all: only core.purge_company and
    -- cartable.owner_delete_deliverables get this far)
    IF TG_OP = 'DELETE'
       AND COALESCE(current_setting('hq.purge_company', true), '') = OLD.company_id::text THEN
        RETURN OLD;
    END IF;
    IF TG_OP = 'DELETE'
       AND COALESCE(current_setting('hq.owner_delete', true), '') = 'deliverables' THEN
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE'
       AND (to_jsonb(NEW) - 'company_id') = (to_jsonb(OLD) - 'company_id')
       AND OLD.company_id IS DISTINCT FROM NEW.company_id
       AND EXISTS (SELECT 1 FROM core.companies WHERE id = OLD.company_id AND kind = 'holding')
       AND EXISTS (SELECT 1 FROM core.companies WHERE id = NEW.company_id AND kind = 'company')
       AND ((OLD.variant = 'original' AND OLD.created_by_kind = 'owner')
            OR (OLD.variant <> 'original' AND OLD.created_by_kind = 'service'
                AND EXISTS (SELECT 1 FROM files.files p
                            WHERE p.id = OLD.parent_id AND p.created_by_kind = 'owner')))
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'files.files is append-only (% rejected)', TG_OP USING ERRCODE = 'HQA01';
END $$;

-- §28.1: the owner's delete for good. -> {{deleted: [{{id, ref, title, company_id}}], storage_keys}}
CREATE OR REPLACE FUNCTION cartable.owner_delete_deliverables(p_ids uuid[]) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    gone   jsonb;
    keys   jsonb;
    k      record;
BEGIN
    PERFORM set_config('hq.owner_delete', 'deliverables', true);
    SELECT COALESCE(jsonb_agg(jsonb_build_object('id', d.id, 'ref', d.ref, 'title', d.title,
                                                 'company_id', d.company_id) ORDER BY d.ref), '[]')
      INTO gone FROM cartable.deliverables d WHERE d.id = ANY (p_ids);
    -- the files these outputs carried, unless anything else uses them
    CREATE TEMP TABLE IF NOT EXISTS owner_delete_files (id uuid PRIMARY KEY) ON COMMIT DROP;
    DELETE FROM owner_delete_files;
    INSERT INTO owner_delete_files SELECT DISTINCT unnest(attachments) FROM cartable.deliverables
        WHERE id = ANY (p_ids) ON CONFLICT DO NOTHING;
    DELETE FROM owner_delete_files f USING cartable.deliverables d
        WHERE d.id <> ALL (p_ids) AND f.id = ANY (d.attachments);
    DELETE FROM owner_delete_files f USING msg.messages m WHERE f.id = ANY (m.attachments);
    FOR k IN SELECT format('%I.%I', cn.nspname, cr.relname) AS child, a.attname AS col
               FROM pg_constraint c
               JOIN pg_class cr ON cr.oid = c.conrelid JOIN pg_namespace cn ON cn.oid = cr.relnamespace
               JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
              WHERE c.contype = 'f' AND c.confrelid = 'files.files'::regclass
                AND cardinality(c.conkey) = 1 AND c.conrelid <> 'files.files'::regclass
    LOOP
        EXECUTE format('DELETE FROM owner_delete_files f USING %s x WHERE x.%I = f.id', k.child, k.col);
    END LOOP;
    INSERT INTO owner_delete_files SELECT id FROM files.files
        WHERE parent_id IN (SELECT id FROM owner_delete_files) ON CONFLICT DO NOTHING;
    SELECT COALESCE(jsonb_agg(storage_key), '[]') INTO keys FROM files.files
        WHERE id IN (SELECT id FROM owner_delete_files);
    -- what stands on the outputs goes with them; a review keeps its minutes' place
    UPDATE owner.reviews SET minutes_deliverable_id = NULL WHERE minutes_deliverable_id = ANY (p_ids);
    DELETE FROM reports.ceo_letters WHERE briefing_id IN
        (SELECT id FROM reports.briefings WHERE deliverable_id = ANY (p_ids));
    DELETE FROM reports.briefings WHERE deliverable_id = ANY (p_ids);
    DELETE FROM quality.claims WHERE deliverable_id = ANY (p_ids);
    DELETE FROM cartable.ratings WHERE deliverable_id = ANY (p_ids);
    DELETE FROM cartable.deliverables WHERE id = ANY (p_ids);
    DELETE FROM files.processing WHERE file_id IN (SELECT id FROM owner_delete_files);
    DELETE FROM files.files WHERE parent_id IN (SELECT id FROM owner_delete_files);
    DELETE FROM files.files WHERE id IN (SELECT id FROM owner_delete_files);
    PERFORM set_config('hq.owner_delete', '', true);
    RETURN jsonb_build_object('deleted', gone, 'storage_keys', keys);
END $$;
REVOKE ALL ON FUNCTION cartable.owner_delete_deliverables(uuid[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION cartable.owner_delete_deliverables(uuid[]) TO hq_api;

-- §28.2 the company catalogue
CREATE TABLE infra.catalogues (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    state           text NOT NULL DEFAULT 'running' CHECK (state IN ('running', 'done', 'failed')),
    reason_fa       text CHECK (length(reason_fa) <= 500),
    jobs            jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(jobs) = 'array'),
    sections        jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(sections) = 'array'),
    record_ref      text CHECK (record_ref ~ '^AR-[0-9]+$'),
    deliverable_ref text CHECK (deliverable_ref ~ '^O-[0-9]+$'),
    work_id         uuid REFERENCES work.work (id),
    previous_id     uuid REFERENCES infra.catalogues (id),
    diff            jsonb CHECK (diff IS NULL OR jsonb_typeof(diff) = 'object'),
    started_by_kind text NOT NULL CHECK (started_by_kind IN ('owner', 'agent', 'service')),
    started_by_code text NOT NULL CHECK (length(started_by_code) BETWEEN 1 AND 64),
    created_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX catalogues_latest ON infra.catalogues (company_id, created_at DESC);
CREATE INDEX catalogues_running ON infra.catalogues (state) WHERE state = 'running';
CREATE INDEX catalogues_jobs ON infra.catalogues USING gin (jobs jsonb_path_ops);
CREATE TRIGGER catalogues_immutable BEFORE UPDATE ON infra.catalogues
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'previous_id', 'started_by_kind',
                                                      'started_by_code', 'created_at');
CREATE TRIGGER catalogues_no_delete BEFORE DELETE ON infra.catalogues
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
ALTER TABLE infra.catalogues ENABLE ROW LEVEL SECURITY;
ALTER TABLE infra.catalogues FORCE ROW LEVEL SECURITY;
CREATE POLICY catalogues_tenant ON infra.catalogues TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY catalogues_owner_role ON infra.catalogues TO hq USING (true) WITH CHECK (true);
GRANT SELECT, INSERT ON infra.catalogues TO {APP_ROLES};
GRANT UPDATE (state, reason_fa, jobs, sections, record_ref, deliverable_ref, work_id, diff,
              finished_at, updated_at) ON infra.catalogues TO {APP_ROLES};

-- §28.3 the apps' own error reports (masked on the device, again here)
CREATE TABLE ops.client_errors (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    app          text NOT NULL CHECK (app IN ('android', 'web')),
    version      text NOT NULL CHECK (length(version) BETWEEN 1 AND 60),
    entry_id     bigint,
    at           timestamptz NOT NULL,
    kind         text NOT NULL CHECK (kind ~ '^[a-z_]{{1,30}}$'),
    level        text NOT NULL CHECK (level IN ('error', 'warning', 'info')),
    screen       text CHECK (length(screen) <= 200),
    status       int,
    code         text CHECK (length(code) <= 80),
    message      text CHECK (length(message) <= 2000),
    fingerprint  text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{{64}}$'),
    entry        jsonb NOT NULL CHECK (jsonb_typeof(entry) = 'object'),
    received_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (app, version, fingerprint)
);
CREATE INDEX client_errors_recent ON ops.client_errors (received_at DESC);
CREATE INDEX client_errors_app ON ops.client_errors (app, version, at DESC);
CREATE TRIGGER client_errors_append_only BEFORE UPDATE OR DELETE ON ops.client_errors
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
ALTER TABLE ops.client_errors ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.client_errors FORCE ROW LEVEL SECURITY;
CREATE POLICY client_errors_tenant ON ops.client_errors TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY client_errors_owner_role ON ops.client_errors TO hq USING (true) WITH CHECK (true);
GRANT SELECT, INSERT ON ops.client_errors TO {APP_ROLES};

-- §28.2-§28.3: one row per periodic watch duty (a catalogue refresh, a growth
-- memo, the holding's proposal), so each runs once per its period
CREATE TABLE ops.watch_runs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    key         text NOT NULL UNIQUE CHECK (key ~ '^[a-z_]+:[A-Za-z0-9:_.-]{{1,120}}$'),
    kind        text NOT NULL CHECK (kind IN ('catalogue', 'growth_memo', 'holding_proposal')),
    work_id     uuid REFERENCES work.work (id),
    catalogue_id uuid REFERENCES infra.catalogues (id),
    note        text CHECK (length(note) <= 300),
    at          timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER watch_runs_append_only BEFORE UPDATE OR DELETE ON ops.watch_runs
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
ALTER TABLE ops.watch_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.watch_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY watch_runs_tenant ON ops.watch_runs TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY watch_runs_owner_role ON ops.watch_runs TO hq USING (true) WITH CHECK (true);
GRANT SELECT, INSERT ON ops.watch_runs TO {APP_ROLES};

ALTER TABLE oversight.findings
    ADD COLUMN kind    text CHECK (kind IN ('security', 'app_health', 'code', 'growth', 'holding')),
    ADD COLUMN fix_md  text CHECK (length(fix_md) <= 20000),
    ADD COLUMN fix     jsonb CHECK (fix IS NULL OR (jsonb_typeof(fix) = 'object'
                                    AND fix ->> 'kind' IN ('work', 'workshop', 'decision')));

ALTER TABLE work.councils ADD COLUMN note_fa text CHECK (length(note_fa) <= 500);
GRANT UPDATE (note_fa) ON work.councils TO {APP_ROLES};

ALTER TABLE substitutes.players ADD COLUMN web_error_until timestamptz;
GRANT UPDATE (web_error_until) ON substitutes.players TO {APP_ROLES};
ALTER TABLE substitutes.calls ADD COLUMN attempt smallint NOT NULL DEFAULT 1 CHECK (attempt BETWEEN 1 AND 3);
GRANT UPDATE (attempt) ON substitutes.calls TO {APP_ROLES};
"""

DOWNGRADE = f"""
REVOKE UPDATE (attempt) ON substitutes.calls FROM {APP_ROLES};
ALTER TABLE substitutes.calls DROP COLUMN attempt;
REVOKE UPDATE (note_fa) ON work.councils FROM {APP_ROLES};
ALTER TABLE work.councils DROP COLUMN note_fa;
REVOKE UPDATE (web_error_until) ON substitutes.players FROM {APP_ROLES};
ALTER TABLE substitutes.players DROP COLUMN web_error_until;
ALTER TABLE oversight.findings DROP COLUMN kind, DROP COLUMN fix_md, DROP COLUMN fix;
DROP TABLE ops.watch_runs;
DROP TABLE ops.client_errors;
DROP TABLE infra.catalogues;
DROP FUNCTION cartable.owner_delete_deliverables(uuid[]);

CREATE OR REPLACE FUNCTION core.reject_change() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_user = 'hq'
       AND COALESCE(current_setting('hq.purge_company', true), '') <> '' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION '%.% is append-only (% rejected)', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'HQA01';
END $$;

CREATE OR REPLACE FUNCTION files.guard_change() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND COALESCE(current_setting('hq.purge_company', true), '') = OLD.company_id::text THEN
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE'
       AND (to_jsonb(NEW) - 'company_id') = (to_jsonb(OLD) - 'company_id')
       AND OLD.company_id IS DISTINCT FROM NEW.company_id
       AND EXISTS (SELECT 1 FROM core.companies WHERE id = OLD.company_id AND kind = 'holding')
       AND EXISTS (SELECT 1 FROM core.companies WHERE id = NEW.company_id AND kind = 'company')
       AND ((OLD.variant = 'original' AND OLD.created_by_kind = 'owner')
            OR (OLD.variant <> 'original' AND OLD.created_by_kind = 'service'
                AND EXISTS (SELECT 1 FROM files.files p
                            WHERE p.id = OLD.parent_id AND p.created_by_kind = 'owner')))
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'files.files is append-only (% rejected)', TG_OP USING ERRCODE = 'HQA01';
END $$;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
