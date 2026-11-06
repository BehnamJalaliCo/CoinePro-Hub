"""Erasing for good (contract §37, v1.19; the owner, 2026-11-06: «یه گزینه حذف هم داشته باشه که اصلا شاید
یه سشن رو من میخوام پاک کنم اصلا نباشه و قابلیت پاک کردن از بایگانی هم بذار»; an agent only
proposes one).

- owner.erase_order(order, dry) (SECURITY DEFINER, owner hq; only hq_api may call it): a session erased
  in one go, or (dry) what it would erase, by the same code in a sub-transaction rolled back, so the
  preview is exactly the erase. Gone: the report, its tasks and files, the talk (conversations, turns,
  cards, the memory and stream events of its turns, their spoken audio), the outputs (and their
  ratings, claims, letters), the cards nothing kept stands on (the others withdrawn, their record
  kept), the notifications and the api's replays that point at the order, the runs' steps, prompts
  and memories, the works' parts, workspace and council, the owner's interactions and routing
  corrections of it, and the order itself. Kept, with no word of the order: the works (each marked
  `erased_at`, its title and brief «پاک‌شده», hidden from every app role by a RESTRICTIVE policy:
  their runs, events and the token ledger stand on them), the work events (their data «پاک‌شده»), the
  players' calls (their figures; the prompt and answer gone), the runs and the token ledger (figures
  only), the audit chain (hash-linked; never changed). A stored file goes only when nothing that
  stays uses it; its object is queued in archive.destroy_queue (why `erase`) and removed after the
  commit.
- cartable.erase_output(deliverable, dry): one output erased (cartable.owner_delete_deliverables
  of §28.1) with the notifications pointing at it and its pending cards withdrawn; its files queued.
- core.reject_change / files.guard_change let those DELETEs (and the work events' blanking) through
  only while `hq.owner_delete = 'erase'` is set, as the owner role hq, which only these functions do.
- work.reopen(work) (SECURITY DEFINER): a delivered, done or cancelled work back to `in_progress`
  (§37.4: the owner's word after delivery; a reopened session's cancelled root), the closed-work
  guard of work.before_update letting exactly that one through.
- the decision kind `erase` (§37.3: an agent proposes, the owner seals); archive.destroy_queue.why
  `erase`; archive.tombstones.decision_ref may be `owner` (an erase by the owner's own hand).

Revision ID: 0055
Revises: 0054
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
OWNER_DELETE_TABLES = (
    "'cartable.deliverables', 'cartable.ratings', 'quality.claims', 'reports.briefings', "
    "'reports.ceo_letters'"
)
# what a session's erase deletes past the append-only guards (owner.order_files is 0054's)
ERASE_DELETE_TABLES = (
    "'owner.orders', 'owner.order_reports', 'owner.session_tasks', 'owner.order_files', "
    "'owner.dispatch_memory', 'owner.interactions', 'owner.decision_reminders', "
    "'talk.conversations', 'talk.turns', 'talk.cards', 'talk.memory', 'talk.turn_events', "
    "'cartable.deliverables', 'cartable.ratings', 'quality.claims', 'reports.briefings', "
    "'reports.ceo_letters', 'agents.steps', 'core.employee_memory', 'dceo.predictions', "
    "'advisor.memos', 'work.councils', 'work.splits', 'work.split_parts', 'work.workspaces'"
)
# what it keeps but empties of the order's words
ERASE_BLANK_TABLES = "'work.work_events'"

REJECT_0034 = f"""
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
"""

REJECT = f"""
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
    -- ⟨1.19⟩ owner.erase_order (as hq): a session erased for good; a guarded ledger row it keeps
    -- loses the order's words
    IF current_user = 'hq' AND COALESCE(current_setting('hq.owner_delete', true), '') = 'erase' THEN
        IF TG_OP = 'DELETE'
           AND format('%s.%s', TG_TABLE_SCHEMA, TG_TABLE_NAME) IN ({ERASE_DELETE_TABLES}) THEN
            RETURN OLD;
        END IF;
        IF TG_OP = 'UPDATE'
           AND format('%s.%s', TG_TABLE_SCHEMA, TG_TABLE_NAME) IN ({ERASE_BLANK_TABLES}) THEN
            RETURN NEW;
        END IF;
    END IF;
    RAISE EXCEPTION '%.% is append-only (% rejected)', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'HQA01';
END $$;
"""

FILES_GUARD = """
CREATE OR REPLACE FUNCTION files.guard_change() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    -- (no app role may DELETE here at all: only core.purge_company,
    -- cartable.owner_delete_deliverables @ERASE@get this far)
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

# work.before_update refuses any status change of a closed work; work.reopen lets one through
CLOSED_GUARD = "IF OLD.status IN ('done', 'cancelled', 'failed') AND NEW.status <> OLD.status THEN"
CLOSED_GUARD_REOPEN = (
    "IF OLD.status IN ('done', 'cancelled', 'failed') AND NEW.status <> OLD.status\n"
    "                   AND NOT work.reopening(OLD.id, NEW.status) THEN"
)


def _rewrite_before_update(old: str, new: str) -> str:
    """work.before_update rewritten from its own definition: one line replaced, nothing else."""
    o = old.replace("'", "''")
    n = new.replace("'", "''")
    return f"""
DO $$
DECLARE src text;
BEGIN
    src := pg_get_functiondef('work.before_update()'::regprocedure);
    IF position('{o}' IN src) = 0 THEN
        RAISE EXCEPTION 'work.before_update: the closed-work guard is not where 0055 expects it';
    END IF;
    EXECUTE replace(src, '{o}', '{n}');
END $$;
"""


FUNCTIONS = r"""
-- ⟨1.19⟩ §37.4 a closed work back to in_progress, by work.reopen only
CREATE FUNCTION work.reopening(p_work uuid, p_status text) RETURNS boolean
    LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $$
    SELECT p_status = 'in_progress' AND current_user = 'hq'
           AND COALESCE(current_setting('hq.reopen_work', true), '') = p_work::text
$$;
-- (the guard runs as whoever updates a work: every role that may)
GRANT EXECUTE ON FUNCTION work.reopening(uuid, text) TO hq_api, hq_worker;

CREATE FUNCTION work.reopen(p_work uuid) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    n integer;
BEGIN
    PERFORM set_config('hq.reopen_work', p_work::text, true);
    UPDATE work.work SET status = 'in_progress', closed_at = NULL, close_reason = NULL,
           delivered_at = NULL
     WHERE id = p_work AND erased_at IS NULL
       AND status IN ('delivered', 'done', 'cancelled', 'failed')
       AND company_id = ANY (core.allowed_company_ids());
    GET DIAGNOSTICS n = ROW_COUNT;
    PERFORM set_config('hq.reopen_work', '', true);
    RETURN n > 0;
END $$;
REVOKE ALL ON FUNCTION work.reopen(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION work.reopen(uuid) TO hq_api;

-- every foreign key into a table's `id` (the child table and its column): what a row stands on
CREATE FUNCTION owner.erase_refs(p_table regclass) RETURNS TABLE (child text, col text)
    LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $$
    SELECT DISTINCT format('%I.%I', cn.nspname, cr.relname), a.attname::text
    FROM pg_constraint c
    JOIN pg_class cr ON cr.oid = c.conrelid
    JOIN pg_namespace cn ON cn.oid = cr.relnamespace
    JOIN pg_attribute pk ON pk.attrelid = c.confrelid AND pk.attname = 'id'
    JOIN pg_attribute a ON a.attrelid = c.conrelid
                       AND a.attnum = c.conkey[array_position(c.confkey, pk.attnum)]
    WHERE c.contype = 'f' AND c.confrelid = p_table AND c.conrelid <> p_table
      AND pk.attnum = ANY (c.confkey)
$$;
REVOKE ALL ON FUNCTION owner.erase_refs(regclass) FROM PUBLIC;

-- the files of erase_files nothing that stays uses -> their storage keys, queued for destruction
CREATE FUNCTION owner.erase_sweep_files(p_ref text) RETURNS integer
    LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    k record;
    n integer;
BEGIN
    -- (a file another delete removed already is not counted twice)
    DELETE FROM erase_files f WHERE NOT EXISTS (SELECT 1 FROM files.files x WHERE x.id = f.id);
    INSERT INTO erase_files SELECT id FROM files.files
        WHERE parent_id IN (SELECT id FROM erase_files) ON CONFLICT DO NOTHING;
    -- the spoken audio's queue rows go with the audio
    DELETE FROM talk.voice_jobs WHERE file_id IN (SELECT id FROM erase_files);
    FOR k IN SELECT * FROM owner.erase_refs('files.files'::regclass)
              WHERE child NOT IN ('files.files', 'files.processing') LOOP
        EXECUTE format('DELETE FROM erase_files f USING %s x WHERE x.%I = f.id', k.child, k.col);
    END LOOP;
    DELETE FROM erase_files f USING cartable.deliverables d WHERE f.id = ANY (d.attachments);
    DELETE FROM erase_files f USING msg.messages m WHERE f.id = ANY (m.attachments);
    DELETE FROM erase_files f USING owner.errands e
        WHERE f.id = ANY (e.file_ids) OR f.id = ANY (e.attachments);
    DELETE FROM erase_files f USING legal.cases x WHERE f.id = ANY (x.file_ids);
    DELETE FROM erase_files f USING substitutes.calls x WHERE f.id = ANY (x.file_ids);
    DELETE FROM erase_files f USING substitutes.creatives x WHERE f.id = ANY (x.file_ids);
    DELETE FROM erase_files f USING lines.assets x WHERE f.id = ANY (x.files);
    DELETE FROM erase_files f USING archive.record_files x WHERE x.file_id = f.id;
    DELETE FROM erase_files f USING archive.intake x WHERE x.file_id = f.id;
    DELETE FROM erase_files f USING knowledge.corpus_chunks x WHERE x.file_id = f.id;
    DELETE FROM erase_files f USING media.render_jobs x WHERE strpos(x.files::text, f.id::text) > 0;
    DELETE FROM erase_files f USING legal.emails x WHERE strpos(x.attachments::text, f.id::text) > 0;
    DELETE FROM erase_files f USING talk.turns x
        WHERE strpos(x.audio::text, f.id::text) > 0;
    IF EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = 'talk.turns'::regclass
                 AND attname = 'files' AND NOT attisdropped) THEN
        EXECUTE 'DELETE FROM erase_files f USING talk.turns x WHERE f.id = ANY (x.files)';
    END IF;
    IF to_regclass('owner.order_files') IS NOT NULL THEN
        EXECUTE 'DELETE FROM erase_files f USING owner.order_files x WHERE x.file_id = f.id';
    END IF;
    -- an original stays with a variant that stays; a variant goes only with its original
    DELETE FROM erase_files f
        WHERE EXISTS (SELECT 1 FROM files.files v WHERE v.parent_id = f.id
                        AND NOT EXISTS (SELECT 1 FROM erase_files e WHERE e.id = v.id));
    DELETE FROM erase_files f USING files.files x
        WHERE x.id = f.id AND x.parent_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM erase_files e WHERE e.id = x.parent_id);
    CREATE TEMP TABLE IF NOT EXISTS erase_keys (company_id uuid, k text) ON COMMIT DROP;
    DELETE FROM erase_keys;
    INSERT INTO erase_keys SELECT DISTINCT company_id, storage_key FROM files.files
        WHERE id IN (SELECT id FROM erase_files) AND storage_key IS NOT NULL;
    DELETE FROM files.processing WHERE file_id IN (SELECT id FROM erase_files);
    DELETE FROM files.files WHERE id IN (SELECT id FROM erase_files);
    SELECT count(*) INTO n FROM erase_files;
    -- an object another file row (or an archive copy) still points at stays
    INSERT INTO archive.destroy_queue (company_id, storage_key, why, ref)
        SELECT DISTINCT ON (e.k) e.company_id, e.k, 'erase', p_ref FROM erase_keys e
         WHERE e.k ~ '^[0-9a-f]{32}$'
           AND NOT EXISTS (SELECT 1 FROM files.files x WHERE x.storage_key = e.k)
           AND NOT EXISTS (SELECT 1 FROM archive.record_files x WHERE x.storage_key = e.k);
    RETURN n;
END $$;
REVOKE ALL ON FUNCTION owner.erase_sweep_files(text) FROM PUBLIC;

-- ⟨1.19⟩ §37.1 the session erased (the body; owner.erase_order runs it, or dry-runs it)
CREATE FUNCTION owner.erase_order_run(p_order uuid) RETURNS jsonb
    LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    erased      constant text := 'پاک‌شده';
    o_ref       text;
    o_routes    jsonb;
    o_file      uuid;
    rep_refs    text[];
    rep_conv    text;
    v_works       uuid[];
    v_work_refs   text[];
    v_convs       uuid[];
    v_conv_refs   text[];
    v_turns       uuid[];
    v_dls         uuid[];
    v_dl_refs     text[];
    v_decs        uuid[];
    v_dec_refs    text[];
    v_runs        uuid[];
    v_refs        text[];
    k           record;
    n_works     integer;
    n_turns     integer;
    n_outputs   integer;
    n_notes     integer;
    n_files     integer;
    n_cards     integer;
    n_kept      integer;
    n_built     integer;
    n_filed     integer;
BEGIN
    SELECT ref, routes, file_id INTO o_ref, o_routes, o_file
      FROM owner.orders WHERE id = p_order FOR UPDATE;
    IF o_ref IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT work_refs, conversation_ref INTO rep_refs, rep_conv
      FROM owner.order_reports WHERE order_id = p_order FOR UPDATE;
    PERFORM set_config('hq.owner_delete', 'erase', true);

    -- the works: the routes' roots, every work the report saw, the order's council and the CEO's
    -- small items of it, with their children and the requests made from them
    WITH RECURSIVE seed(id) AS (
        SELECT w.id FROM work.work w
         WHERE w.ref IN (SELECT r ->> 'work_ref'
                           FROM jsonb_array_elements(CASE WHEN jsonb_typeof(o_routes) = 'array'
                                                          THEN o_routes ELSE '[]' END) r
                          WHERE jsonb_typeof(r) = 'object')
            OR w.ref = ANY (COALESCE(rep_refs, '{}'))
            OR (starts_with(w.title, 'فرمان ' || o_ref || ': ') AND w.created_by_kind = 'service'
                AND w.created_by_code = 'orders')
            OR w.id IN (SELECT c.work_id FROM work.councils c WHERE c.order_ref = o_ref)
            OR w.id IN (SELECT c.synthesis_work_id FROM work.councils c WHERE c.order_ref = o_ref)
    ), t(id) AS (
        SELECT id FROM seed
        UNION
        SELECT c.id FROM work.work c JOIN t ON c.parent_id = t.id OR c.requested_by_work_id = t.id
    )
    SELECT COALESCE(array_agg(t.id), '{}') INTO v_works FROM t;
    SELECT COALESCE(array_agg(ref), '{}') INTO v_work_refs FROM work.work WHERE id = ANY (v_works);
    n_works := cardinality(v_works);
    -- the talk: the session's conversation (and any other bound to the order)
    SELECT COALESCE(array_agg(id), '{}'), COALESCE(array_agg(ref), '{}') INTO v_convs, v_conv_refs
      FROM talk.conversations WHERE order_ref = o_ref OR ref = rep_conv;
    SELECT COALESCE(array_agg(id), '{}') INTO v_turns FROM talk.turns WHERE conversation_id = ANY (v_convs);
    n_turns := cardinality(v_turns);
    SELECT count(*) INTO n_built FROM talk.cards
     WHERE conversation_id = ANY (v_convs) AND kind IN ('group', 'line') AND state = 'done';
    -- the outputs and the cards (of the works, or made by the session's cards)
    SELECT COALESCE(array_agg(id), '{}'), COALESCE(array_agg(ref), '{}') INTO v_dls, v_dl_refs
      FROM cartable.deliverables WHERE work_id = ANY (v_works);
    n_outputs := cardinality(v_dls);
    SELECT count(*) INTO n_filed FROM archive.records
     WHERE source_kind = 'deliverable' AND source_ref = ANY (v_dl_refs) AND state <> 'disposed';
    SELECT COALESCE(array_agg(id), '{}'), COALESCE(array_agg(ref), '{}') INTO v_decs, v_dec_refs
      FROM cartable.decisions
     WHERE work_id = ANY (v_works)
        OR ref IN (SELECT unnest(c.made) FROM talk.cards c WHERE c.conversation_id = ANY (v_convs));
    -- the runs: of the works, and the talk's own
    SELECT COALESCE(array_agg(id), '{}') INTO v_runs FROM agents.runs
     WHERE work_id = ANY (v_works)
        OR id IN (SELECT run_id FROM talk.turns WHERE id = ANY (v_turns) AND run_id IS NOT NULL);
    v_refs := ARRAY[o_ref] || v_work_refs || v_conv_refs || v_dl_refs || v_dec_refs;

    -- the files the order carried (each one destroyed at the end only when nothing that stays uses it)
    CREATE TEMP TABLE IF NOT EXISTS erase_files (id uuid PRIMARY KEY) ON COMMIT DROP;
    DELETE FROM erase_files;
    INSERT INTO erase_files SELECT o_file WHERE o_file IS NOT NULL ON CONFLICT DO NOTHING;
    INSERT INTO erase_files SELECT DISTINCT unnest(attachments) FROM cartable.deliverables
        WHERE id = ANY (v_dls) ON CONFLICT DO NOTHING;
    INSERT INTO erase_files
        SELECT DISTINCT CAST(a ->> 'file_id' AS uuid)
        FROM talk.turns t,
             jsonb_array_elements(CASE WHEN jsonb_typeof(t.audio) = 'array' THEN t.audio ELSE '[]' END) a
        WHERE t.id = ANY (v_turns) AND jsonb_typeof(a) = 'object'
          AND a ->> 'file_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        ON CONFLICT DO NOTHING;
    IF to_regclass('owner.order_files') IS NOT NULL THEN
        EXECUTE 'INSERT INTO erase_files SELECT file_id FROM owner.order_files WHERE order_id = $1
                 ON CONFLICT DO NOTHING' USING p_order;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = 'talk.turns'::regclass
                 AND attname = 'files' AND NOT attisdropped) THEN
        EXECUTE 'INSERT INTO erase_files SELECT DISTINCT unnest(files) FROM talk.turns
                 WHERE id = ANY ($1) ON CONFLICT DO NOTHING' USING v_turns;
    END IF;

    -- what still runs stops: the open works cancelled (as close {verdict: cancel}), their runs refused
    UPDATE agents.runs SET state = 'refused', error_code = 'erased', finished_at = now(),
           note = 'the owner erased the order'
     WHERE id = ANY (v_runs) AND state IN ('queued', 'running');
    UPDATE work.work SET status = 'cancelled', closed_at = now(), close_reason = erased
     WHERE id = ANY (v_works) AND status IN ('queued', 'in_progress', 'waiting');
    UPDATE work.schedules SET status = 'ended' WHERE work_id = ANY (v_works) AND status <> 'ended';
    UPDATE cartable.decisions SET status = 'withdrawn', decided_at = now(), decided_by_kind = 'service',
           decided_by_code = 'erase', note = erased
     WHERE id = ANY (v_decs) AND status = 'pending';

    -- the session: its report, plan and files; what the owner did on it; his routing corrections
    DELETE FROM owner.session_tasks WHERE order_id = p_order;
    IF to_regclass('owner.order_files') IS NOT NULL THEN
        EXECUTE 'DELETE FROM owner.order_files WHERE order_id = $1' USING p_order;
    END IF;
    DELETE FROM owner.order_reports WHERE order_id = p_order;
    DELETE FROM owner.dispatch_memory WHERE order_ref = o_ref;
    DELETE FROM owner.interactions WHERE target_ref = ANY (v_refs);
    -- the talk: its turns (their memory, stream events and spoken audio) and cards
    DELETE FROM talk.memory WHERE turn_id = ANY (v_turns);
    DELETE FROM talk.turn_events WHERE turn_id = ANY (v_turns);
    DELETE FROM talk.cards WHERE conversation_id = ANY (v_convs);
    DELETE FROM talk.turns WHERE id = ANY (v_turns);
    DELETE FROM talk.conversations WHERE id = ANY (v_convs);
    -- the outputs (what stands on them goes with them; a review keeps its place)
    UPDATE owner.reviews SET minutes_deliverable_id = NULL WHERE minutes_deliverable_id = ANY (v_dls);
    DELETE FROM reports.ceo_letters WHERE briefing_id IN
        (SELECT id FROM reports.briefings WHERE deliverable_id = ANY (v_dls));
    DELETE FROM reports.briefings WHERE deliverable_id = ANY (v_dls);
    DELETE FROM quality.claims WHERE deliverable_id = ANY (v_dls);
    DELETE FROM cartable.ratings WHERE deliverable_id = ANY (v_dls);
    DELETE FROM cartable.deliverables WHERE id = ANY (v_dls);
    -- the run transcripts: the steps, the model's prompts and answers, what the runs remembered
    DELETE FROM core.employee_memory WHERE run_id = ANY (v_runs);
    DELETE FROM agents.steps WHERE run_id = ANY (v_runs);
    DELETE FROM llm.transcripts WHERE call_id IN
        (SELECT id FROM llm.calls WHERE work_ref = ANY (v_work_refs) OR meta ->> 'run_id' = ANY (v_runs::text[]));
    -- the players' calls keep their figures (the treasury adds them up) and lose their words
    UPDATE substitutes.calls SET input_md = erased, result = NULL
     WHERE reply_work_id = ANY (v_works) OR purpose_ref = ANY (v_refs);
    -- the works' parts, workspaces and council
    DELETE FROM work.split_parts WHERE work_id = ANY (v_works)
        OR split_id IN (SELECT id FROM work.splits WHERE work_id = ANY (v_works));
    DELETE FROM work.splits WHERE work_id = ANY (v_works);
    DELETE FROM work.workspaces WHERE work_id = ANY (v_works);
    DELETE FROM work.councils WHERE order_ref = o_ref OR work_id = ANY (v_works)
        OR synthesis_work_id = ANY (v_works);
    -- the cards: their reminders, memos and predictions go; a card nothing kept stands on goes too,
    -- the others keep their record (withdrawn above when pending)
    DELETE FROM owner.decision_reminders WHERE decision_id = ANY (v_decs);
    DELETE FROM advisor.memos WHERE decision_id = ANY (v_decs);
    DELETE FROM dceo.predictions WHERE decision_id = ANY (v_decs);
    CREATE TEMP TABLE IF NOT EXISTS erase_decisions (id uuid PRIMARY KEY) ON COMMIT DROP;
    DELETE FROM erase_decisions;
    INSERT INTO erase_decisions SELECT DISTINCT unnest(v_decs) ON CONFLICT DO NOTHING;
    FOR k IN SELECT * FROM owner.erase_refs('cartable.decisions'::regclass) LOOP
        EXECUTE format('DELETE FROM erase_decisions e USING %s x WHERE x.%I = e.id', k.child, k.col);
    END LOOP;
    SELECT count(*) INTO n_cards FROM erase_decisions;
    n_kept := cardinality(v_decs) - n_cards;
    DELETE FROM cartable.decisions WHERE id IN (SELECT id FROM erase_decisions);
    -- the notifications that point at the order, its talk, works, cards or outputs
    DELETE FROM notify.notifications WHERE link_ref = ANY (v_refs);
    GET DIAGNOSTICS n_notes = ROW_COUNT;
    -- the api's stored replays of answers that carried the order
    DELETE FROM core.idempotency_keys x WHERE x.response IS NOT NULL
       AND EXISTS (SELECT 1 FROM unnest(v_refs) r WHERE strpos(x.response::text, '"' || r || '"') > 0);
    -- the order itself
    DELETE FROM owner.orders WHERE id = p_order;
    -- the works stay only as what the ledgers stand on (runs, events, the token ledger): no words,
    -- and no app role sees them again (the RESTRICTIVE policy work_not_erased)
    UPDATE work.work_events SET data = jsonb_build_object('text_fa', erased) WHERE work_id = ANY (v_works);
    UPDATE work.work SET erased_at = now(), title = erased, brief = erased, progress_note = NULL,
           close_reason = CASE WHEN close_reason IS NULL THEN NULL ELSE erased END,
           evidence = '[]', run_meta = NULL
     WHERE id = ANY (v_works);
    -- the files nothing that stays uses
    n_files := owner.erase_sweep_files(o_ref);
    PERFORM set_config('hq.owner_delete', '', true);
    RETURN jsonb_build_object(
        'ref', o_ref,
        'counts', jsonb_build_object('turns', n_turns, 'files', n_files, 'outputs', n_outputs,
                                     'works', n_works, 'notifications', n_notes),
        'cards', jsonb_build_object('erased', n_cards, 'kept', n_kept),
        'built', n_built,
        'filed', n_filed,
        'work_refs', to_jsonb(v_work_refs),
        'conversation_refs', to_jsonb(v_conv_refs));
END $$;
REVOKE ALL ON FUNCTION owner.erase_order_run(uuid) FROM PUBLIC;

-- -> what was erased ({ref, counts, cards, built, filed, work_refs, conversation_refs}), null when
-- there is no such order; `p_dry`: the same erase in a sub-transaction rolled back (the preview)
CREATE FUNCTION owner.erase_order(p_order uuid, p_dry boolean) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    out jsonb;
BEGIN
    BEGIN
        out := owner.erase_order_run(p_order);
        IF p_dry THEN
            RAISE EXCEPTION USING ERRCODE = 'HQX56', MESSAGE = COALESCE(out::text, 'null');
        END IF;
    EXCEPTION WHEN SQLSTATE 'HQX56' THEN
        out := CAST(SQLERRM AS jsonb);
    END;
    RETURN out;
END $$;
REVOKE ALL ON FUNCTION owner.erase_order(uuid, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION owner.erase_order(uuid, boolean) TO hq_api;

-- ⟨1.19⟩ §37.2 one output erased: §28.1's delete for good, the notifications that point at it,
-- its pending cards withdrawn; its files (only they used) queued for destruction
CREATE FUNCTION cartable.erase_output_run(p_deliverable uuid) RETURNS jsonb
    LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    d_ref   text;
    d_work  uuid;
    d_co    uuid;
    gone    jsonb;
    n_notes integer;
    n_cards integer;
    n_files integer;
BEGIN
    SELECT ref, work_id, company_id INTO d_ref, d_work, d_co
      FROM cartable.deliverables WHERE id = p_deliverable FOR UPDATE;
    IF d_ref IS NULL THEN
        RETURN NULL;
    END IF;
    UPDATE cartable.decisions SET status = 'withdrawn', decided_at = now(), decided_by_kind = 'service',
           decided_by_code = 'erase', note = 'پاک‌شده'
     WHERE status = 'pending' AND kind <> 'erase' AND strpos(payload::text, '"' || d_ref || '"') > 0;
    GET DIAGNOSTICS n_cards = ROW_COUNT;
    DELETE FROM notify.notifications WHERE link_ref = d_ref;
    GET DIAGNOSTICS n_notes = ROW_COUNT;
    CREATE TEMP TABLE IF NOT EXISTS erase_files (id uuid PRIMARY KEY) ON COMMIT DROP;
    DELETE FROM erase_files;
    INSERT INTO erase_files SELECT DISTINCT unnest(attachments) FROM cartable.deliverables
        WHERE id = p_deliverable ON CONFLICT DO NOTHING;
    gone := cartable.owner_delete_deliverables(ARRAY[p_deliverable]);
    -- what §28.1's delete left (a file it keeps for its processing row) when nothing else uses it
    PERFORM set_config('hq.owner_delete', 'erase', true);
    n_files := owner.erase_sweep_files(d_ref);
    PERFORM set_config('hq.owner_delete', '', true);
    -- the objects of the files §28.1's delete removed
    INSERT INTO archive.destroy_queue (company_id, storage_key, why, ref)
        SELECT DISTINCT ON (k) d_co, k, 'erase', d_ref
        FROM jsonb_array_elements_text(COALESCE(gone -> 'storage_keys', '[]')) k
        WHERE k ~ '^[0-9a-f]{32}$'
          AND NOT EXISTS (SELECT 1 FROM files.files x WHERE x.storage_key = k)
          AND NOT EXISTS (SELECT 1 FROM archive.record_files x WHERE x.storage_key = k);
    n_files := n_files + jsonb_array_length(COALESCE(gone -> 'storage_keys', '[]'));
    RETURN jsonb_build_object(
        'ref', d_ref, 'work_id', d_work,
        'counts', jsonb_build_object('turns', 0, 'files', n_files, 'outputs',
                                     jsonb_array_length(gone -> 'deleted'), 'works', 0,
                                     'notifications', n_notes),
        'cards', jsonb_build_object('withdrawn', n_cards));
END $$;
REVOKE ALL ON FUNCTION cartable.erase_output_run(uuid) FROM PUBLIC;

CREATE FUNCTION cartable.erase_output(p_deliverable uuid, p_dry boolean) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    out jsonb;
BEGIN
    BEGIN
        out := cartable.erase_output_run(p_deliverable);
        IF p_dry THEN
            RAISE EXCEPTION USING ERRCODE = 'HQX56', MESSAGE = COALESCE(out::text, 'null');
        END IF;
    EXCEPTION WHEN SQLSTATE 'HQX56' THEN
        out := CAST(SQLERRM AS jsonb);
    END;
    RETURN out;
END $$;
REVOKE ALL ON FUNCTION cartable.erase_output(uuid, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION cartable.erase_output(uuid, boolean) TO hq_api;
"""

UPGRADE = f"""
-- ============================================== §37.1 the works an erase keeps ==
ALTER TABLE work.work ADD COLUMN erased_at timestamptz;
COMMENT ON COLUMN work.work.erased_at IS
    'The owner erased the order this work was part of (contract §37.1): kept only for the ledgers';
CREATE POLICY work_not_erased ON work.work AS RESTRICTIVE TO {APP_ROLES} USING (erased_at IS NULL);

-- the erase reads and removes the run transcripts of its works (the llm router's tables)
CREATE POLICY calls_owner_erase ON llm.calls FOR SELECT TO hq
    USING (COALESCE(current_setting('hq.owner_delete', true), '') = 'erase');
CREATE POLICY transcripts_owner_erase_select ON llm.transcripts FOR SELECT TO hq
    USING (COALESCE(current_setting('hq.owner_delete', true), '') = 'erase');
CREATE POLICY transcripts_owner_erase_delete ON llm.transcripts FOR DELETE TO hq
    USING (COALESCE(current_setting('hq.owner_delete', true), '') = 'erase');

-- ======================================================== the destroy queue ==
ALTER TABLE archive.destroy_queue DROP CONSTRAINT destroy_queue_why_check;
ALTER TABLE archive.destroy_queue ADD CONSTRAINT destroy_queue_why_check
    CHECK (why IN ('disposal', 'restore', 'intake', 'erase'));
-- §37.2 a record erased by the owner's own hand (no card): its tombstone says so
ALTER TABLE archive.tombstones DROP CONSTRAINT tombstones_decision_ref_check;
ALTER TABLE archive.tombstones ADD CONSTRAINT tombstones_decision_ref_check
    CHECK (decision_ref ~ '^D-[0-9]{{6,}}$' OR decision_ref = 'owner');
"""

DOWNGRADE = """
DROP FUNCTION cartable.erase_output(uuid, boolean);
DROP FUNCTION cartable.erase_output_run(uuid);
DROP FUNCTION owner.erase_order(uuid, boolean);
DROP FUNCTION owner.erase_order_run(uuid);
DROP FUNCTION owner.erase_sweep_files(text);
DROP FUNCTION owner.erase_refs(regclass);
DROP FUNCTION work.reopen(uuid);
-- rows of the new values stay (nothing is deleted): the old CHECKs come back NOT VALID
ALTER TABLE archive.tombstones DROP CONSTRAINT tombstones_decision_ref_check;
ALTER TABLE archive.tombstones ADD CONSTRAINT tombstones_decision_ref_check
    CHECK (decision_ref ~ '^D-[0-9]{6,}$') NOT VALID;
ALTER TABLE archive.destroy_queue DROP CONSTRAINT destroy_queue_why_check;
ALTER TABLE archive.destroy_queue ADD CONSTRAINT destroy_queue_why_check
    CHECK (why IN ('disposal', 'restore', 'intake')) NOT VALID;
DROP POLICY transcripts_owner_erase_delete ON llm.transcripts;
DROP POLICY transcripts_owner_erase_select ON llm.transcripts;
DROP POLICY calls_owner_erase ON llm.calls;
DROP POLICY work_not_erased ON work.work;
ALTER TABLE work.work DROP COLUMN erased_at;
"""


def _kinds_sql(table: str, constraint: str, add: tuple[str, ...]) -> str:
    """Rewrite a `kind IN (...)` CHECK from the kinds it holds now (0040's helper)."""
    added = ", ".join(f"'{k}'" for k in add)
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
            ) x WHERE k IS NOT NULL AND k <> '';
            ALTER TABLE {table} DROP CONSTRAINT {constraint};
            EXECUTE format('ALTER TABLE {table} ADD CONSTRAINT {constraint} '
                           'CHECK (kind IN (%s))', kinds);
        END $$;
    """


def _files_guard(erase: bool) -> str:
    if erase:
        return FILES_GUARD.replace("@ERASE@", "and owner.erase_order ").replace(
            "@MODES@", "'deliverables', 'erase'"
        )
    return FILES_GUARD.replace("@ERASE@", "").replace("@MODES@", "'deliverables'")


def upgrade() -> None:
    execute_script(UPGRADE)
    execute_script(REJECT + _files_guard(True))
    execute_script(FUNCTIONS)
    execute_script(_rewrite_before_update(CLOSED_GUARD, CLOSED_GUARD_REOPEN))
    # ⟨1.19⟩ §37.3 the agent-proposed erase, sealed by the owner
    execute_script(_kinds_sql("cartable.decisions", "decisions_kind_check", ("erase",)))


# The kind `erase` stays in the CHECK: its cards are kept (as 0040's line_publish).
def downgrade() -> None:
    execute_script(_rewrite_before_update(CLOSED_GUARD_REOPEN, CLOSED_GUARD))
    execute_script(DOWNGRADE)
    execute_script(REJECT_0034 + _files_guard(False))
    execute_script("DROP FUNCTION work.reopening(uuid, text);")
