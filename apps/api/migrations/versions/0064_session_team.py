"""The session's team, one person at a time (contract §57; the owner, 2026-11-13: «میخوام … مستقیم
بزنم روی کارمند باهاش توی یه فضای کوچیک حرف بزنم و ببندم و اون ادامه بده کارشو»).

- owner.session_side_lines: the side talk of a session with one person of its team (an employee
  code, `seat_code`): the owner's words to that person (`who = 'owner'`) and the person's answers
  (`who = 'seat'`: their `order.ask` / `order.progress` from a side work of the order). `work_id`:
  the work the owner's word joined or made (`made_work`: made for this word, a side work), or the
  work the person answered from (`asked`: a question, their `order.ask`). Append-only (no UPDATE or DELETE for the app roles); the lines go
  with their order when the owner erases it (ON DELETE CASCADE from owner.orders).
- owner.session_side_reads: how far the owner has read each side talk (`read_id`, the newest line
  he saw), for the seat's `unread`. One row per order and seat.

Both are the holding's rows, as the order and its report are (FORCE RLS in the InitPlan form).

§58.4 what stays after a publication, and what goes (the owner: «کاور اصلی و ریلز اصلی و متن کپشن
بایگانی بشه و بقیه … پاک بشه دیسک رو سنگین نکنه»):
- files.publish_keep: one row per output whose publication IG-Hub confirmed: when, the package kept
  (its video, cover and caption.txt) and the archive record it was filed as; after the daily sweep,
  how many files went and how many bytes were freed. The output's company's rows.
- files.opened: when the owner last opened or downloaded a file (GET /files/{id}); a file he
  opened after the publication stays. No foreign key: it never holds a file anything deletes.
- files.publish_sweep(output, ids, chain, since): deletes those files of a published output and its
  earlier versions that nothing else uses (another output, a session's files, a message, an
  archive record …, or the owner's own open since the publication), their variants with them;
  their stored objects are queued in archive.destroy_queue (why `publish_sweep`). files.guard_change
  lets a delete through under `hq.owner_delete = 'publish_sweep'` (set only by that function).

Additive only; the downgrade drops the tables and the function and puts the guard and the queue's
CHECK back (rows of the new value stay: the old CHECK comes back NOT VALID).

Revision ID: 0064
Revises: 0063
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
EMP = r"'^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$'"


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
CREATE TABLE owner.session_side_lines (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    order_id    uuid NOT NULL REFERENCES owner.orders (id) ON DELETE CASCADE,
    seat_code   text NOT NULL CHECK (seat_code ~ {EMP}),
    who         text NOT NULL CHECK (who IN ('owner', 'seat')),
    who_fa      text NOT NULL CHECK (length(who_fa) BETWEEN 1 AND 200),
    text        text NOT NULL CHECK (length(text) BETWEEN 1 AND 4000),
    work_id     uuid REFERENCES work.work (id),
    work_ref    text CHECK (work_ref IS NULL OR work_ref ~ '^W-[0-9]{{6,12}}$'),
    made_work   boolean NOT NULL DEFAULT false,
    asked       boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT made_work OR (who = 'owner' AND work_id IS NOT NULL)),
    CHECK (NOT asked OR who = 'seat')
);
CREATE INDEX session_side_lines_seat ON owner.session_side_lines (order_id, seat_code, created_at);
CREATE INDEX session_side_lines_work ON owner.session_side_lines (work_id) WHERE work_id IS NOT NULL;
COMMENT ON TABLE owner.session_side_lines IS
    'contract §57: a session''s side talk with one person of its team (append-only)';
GRANT SELECT, INSERT ON owner.session_side_lines TO {APP_ROLES};

CREATE TABLE owner.session_side_reads (
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    order_id    uuid NOT NULL REFERENCES owner.orders (id) ON DELETE CASCADE,
    seat_code   text NOT NULL CHECK (seat_code ~ {EMP}),
    read_id     bigint NOT NULL DEFAULT 0 CHECK (read_id >= 0),
    read_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, seat_code)
);
COMMENT ON TABLE owner.session_side_reads IS
    'contract §57.2: the newest side line of a seat the owner has read (its unread count)';
GRANT SELECT, INSERT ON owner.session_side_reads TO {APP_ROLES};
GRANT UPDATE (read_id, read_at) ON owner.session_side_reads TO {APP_ROLES};

-- ============================================== §58.4 what a publication keeps ==
CREATE TABLE files.publish_keep (
    output        text PRIMARY KEY CHECK (output ~ '^O-[0-9]+$'),
    company_id    uuid NOT NULL REFERENCES core.companies (id),
    job_id        uuid NOT NULL,
    published_at  timestamptz NOT NULL,
    kept          uuid[] NOT NULL DEFAULT '{{}}',
    record_ref    text CHECK (record_ref IS NULL OR record_ref ~ '^AR-[0-9]+$'),
    swept_at      timestamptz,
    swept_files   int CHECK (swept_files IS NULL OR swept_files >= 0),
    freed_bytes   bigint CHECK (freed_bytes IS NULL OR freed_bytes >= 0),
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX publish_keep_due ON files.publish_keep (published_at) WHERE swept_at IS NULL;
COMMENT ON TABLE files.publish_keep IS
    'contract §58.4: a published output''s package kept (archived) and the sweep of the rest';
GRANT SELECT, INSERT ON files.publish_keep TO {APP_ROLES};
GRANT UPDATE (record_ref, swept_at, swept_files, freed_bytes) ON files.publish_keep TO {APP_ROLES};

CREATE TABLE files.opened (
    file_id     uuid PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    opened_at   timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE files.opened IS
    'contract §58.4: when the owner last opened or downloaded a file (a sweep keeps it)';
GRANT SELECT, INSERT ON files.opened TO {APP_ROLES};
GRANT UPDATE (opened_at) ON files.opened TO {APP_ROLES};

ALTER TABLE archive.destroy_queue DROP CONSTRAINT destroy_queue_why_check;
ALTER TABLE archive.destroy_queue ADD CONSTRAINT destroy_queue_why_check
    CHECK (why IN ('disposal', 'restore', 'intake', 'erase', 'publish_sweep'));
"""
    + _rls("owner.session_side_lines")
    + _rls("owner.session_side_reads")
    + _rls("files.publish_keep")
    + _rls("files.opened")
)

# 0055's guard, with the publication sweep's mode (`modes`)
FILES_GUARD = """
CREATE OR REPLACE FUNCTION files.guard_change() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    -- (no app role may DELETE here at all: only core.purge_company,
    -- cartable.owner_delete_deliverables and owner.erase_order @SWEEP@get this far)
    IF TG_OP = 'DELETE'
       AND COALESCE(current_setting('hq.purge_company', true), '') = OLD.company_id::text THEN
        RETURN OLD;
    END IF;
    IF TG_OP = 'DELETE'
       AND COALESCE(current_setting('hq.owner_delete', true), '') IN (@MODES@) THEN
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

SWEEP = """
-- §58.4 the files of a published output that nothing else uses -> {files, bytes}; their objects
-- queued for destruction (archive.destroy_queue, why `publish_sweep`)
CREATE FUNCTION files.publish_sweep(p_output text, p_ids uuid[], p_chain text[], p_since timestamptz)
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    k record;
    n integer;
    b bigint;
BEGIN
    CREATE TEMP TABLE IF NOT EXISTS sweep_files (id uuid PRIMARY KEY) ON COMMIT DROP;
    DELETE FROM sweep_files;
    INSERT INTO sweep_files SELECT DISTINCT x FROM unnest(p_ids) AS x
        WHERE x IS NOT NULL ON CONFLICT DO NOTHING;
    DELETE FROM sweep_files f WHERE NOT EXISTS (SELECT 1 FROM files.files x WHERE x.id = f.id);
    INSERT INTO sweep_files SELECT id FROM files.files
        WHERE parent_id IN (SELECT id FROM sweep_files) ON CONFLICT DO NOTHING;
    -- what the owner opened or downloaded since the publication stays
    DELETE FROM sweep_files f USING files.opened o WHERE o.file_id = f.id AND o.opened_at >= p_since;
    -- whatever else uses a file keeps it (as owner.erase_sweep_files reads it)
    FOR k IN SELECT * FROM owner.erase_refs('files.files'::regclass)
              WHERE child NOT IN ('files.files', 'files.processing') LOOP
        EXECUTE format('DELETE FROM sweep_files f USING %s x WHERE x.%I = f.id', k.child, k.col);
    END LOOP;
    DELETE FROM sweep_files f USING cartable.deliverables d
        WHERE f.id = ANY (d.attachments) AND d.ref <> ALL (p_chain);
    DELETE FROM sweep_files f USING msg.messages m WHERE f.id = ANY (m.attachments);
    DELETE FROM sweep_files f USING owner.errands e
        WHERE f.id = ANY (e.file_ids) OR f.id = ANY (e.attachments);
    DELETE FROM sweep_files f USING legal.cases x WHERE f.id = ANY (x.file_ids);
    DELETE FROM sweep_files f USING substitutes.calls x WHERE f.id = ANY (x.file_ids);
    DELETE FROM sweep_files f USING substitutes.creatives x WHERE f.id = ANY (x.file_ids);
    DELETE FROM sweep_files f USING lines.assets x WHERE f.id = ANY (x.files);
    DELETE FROM sweep_files f USING archive.record_files x WHERE x.file_id = f.id;
    DELETE FROM sweep_files f USING archive.intake x WHERE x.file_id = f.id;
    DELETE FROM sweep_files f USING knowledge.corpus_chunks x WHERE x.file_id = f.id;
    DELETE FROM sweep_files f USING media.render_jobs x WHERE strpos(x.files::text, f.id::text) > 0;
    DELETE FROM sweep_files f USING legal.emails x WHERE strpos(x.attachments::text, f.id::text) > 0;
    DELETE FROM sweep_files f USING talk.turns x WHERE strpos(x.audio::text, f.id::text) > 0;
    IF EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = 'talk.turns'::regclass
                 AND attname = 'files' AND NOT attisdropped) THEN
        EXECUTE 'DELETE FROM sweep_files f USING talk.turns x WHERE f.id = ANY (x.files)';
    END IF;
    DELETE FROM sweep_files f USING owner.order_files x WHERE x.file_id = f.id;
    -- a file another publication still keeps (its package) stays
    DELETE FROM sweep_files f USING files.publish_keep x WHERE f.id = ANY (x.kept);
    -- an original stays with a variant that stays; a variant goes only with its original
    DELETE FROM sweep_files f
        WHERE EXISTS (SELECT 1 FROM files.files v WHERE v.parent_id = f.id
                        AND NOT EXISTS (SELECT 1 FROM sweep_files e WHERE e.id = v.id));
    DELETE FROM sweep_files f USING files.files x
        WHERE x.id = f.id AND x.parent_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM sweep_files e WHERE e.id = x.parent_id);
    CREATE TEMP TABLE IF NOT EXISTS sweep_keys (company_id uuid, k text) ON COMMIT DROP;
    DELETE FROM sweep_keys;
    INSERT INTO sweep_keys SELECT DISTINCT company_id, storage_key FROM files.files
        WHERE id IN (SELECT id FROM sweep_files) AND storage_key IS NOT NULL;
    SELECT count(*), COALESCE(sum(size), 0) INTO n, b FROM files.files
        WHERE id IN (SELECT id FROM sweep_files);
    PERFORM set_config('hq.owner_delete', 'publish_sweep', true);
    DELETE FROM files.processing WHERE file_id IN (SELECT id FROM sweep_files);
    DELETE FROM files.files WHERE id IN (SELECT id FROM sweep_files);
    PERFORM set_config('hq.owner_delete', '', true);
    DELETE FROM files.opened WHERE file_id IN (SELECT id FROM sweep_files);
    -- an object another file row (or an archive copy) still points at stays
    INSERT INTO archive.destroy_queue (company_id, storage_key, why, ref)
        SELECT DISTINCT ON (e.k) e.company_id, e.k, 'publish_sweep', p_output FROM sweep_keys e
         WHERE e.k ~ '^[0-9a-f]{32}$'
           AND NOT EXISTS (SELECT 1 FROM files.files x WHERE x.storage_key = e.k)
           AND NOT EXISTS (SELECT 1 FROM archive.record_files x WHERE x.storage_key = e.k);
    RETURN jsonb_build_object('files', n, 'bytes', b);
END $$;
REVOKE ALL ON FUNCTION files.publish_sweep(text, uuid[], text[], timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION files.publish_sweep(text, uuid[], text[], timestamptz) TO hq_api, hq_worker;
"""

DOWNGRADE = """
DROP FUNCTION files.publish_sweep(text, uuid[], text[], timestamptz);
ALTER TABLE archive.destroy_queue DROP CONSTRAINT destroy_queue_why_check;
ALTER TABLE archive.destroy_queue ADD CONSTRAINT destroy_queue_why_check
    CHECK (why IN ('disposal', 'restore', 'intake', 'erase')) NOT VALID;
DROP TABLE files.opened;
DROP TABLE files.publish_keep;
DROP TABLE owner.session_side_reads;
DROP TABLE owner.session_side_lines;
"""


def _guard(sweep: bool) -> str:
    if sweep:
        return FILES_GUARD.replace("@SWEEP@", "and files.publish_sweep ").replace(
            "@MODES@", "'deliverables', 'erase', 'publish_sweep'"
        )
    return FILES_GUARD.replace("@SWEEP@", "").replace("@MODES@", "'deliverables', 'erase'")


def upgrade() -> None:
    execute_script(UPGRADE)
    execute_script(_guard(True))
    execute_script(SWEEP)


def downgrade() -> None:
    execute_script(_guard(False))
    execute_script(DOWNGRADE)
