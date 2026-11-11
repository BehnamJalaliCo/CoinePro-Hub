"""Fixes from the audit of 2026-11-11 that need the schema (the owner's order in chat:
«هر ایرادی ... پیدا و رفع بکنند»).

- owner.erase_order_run: a session's erase counted the filed outputs by
  `source_kind = 'deliverable'`, but a filed output is `source_kind = 'owner'` with
  `source_ref = 'deliverable:<ref>'`, so the count was always 0. It reads the ref now.
- core.employees.title_fa: an approved promote/demote card sets the new title (hr.apply) from
  the api and the worker, which could not update that column.
- growth.rescue_cases.conversation_id: was immutable, so a rescue case could never be linked
  to the conversation it opens. It may be set once (NULL to a value), never changed.
- archive.levels: a level's rank and encryption are fixed while records use it (a record
  filed as encrypted must not read as plain because its level changed).
- owner.progress: the newsletter's progress rows (kind `newsletter`) were refused by the kind
  CHECK; the kind is added, keeping every kind the CHECK holds now.

Revision ID: 0062
Revises: 0061
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

# owner.erase_order_run as 0055 made it, with the filed outputs read by their ref
ERASE_RUN_FIXED = r"""
CREATE OR REPLACE FUNCTION owner.erase_order_run(p_order uuid) RETURNS jsonb
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
     WHERE source_ref IN (SELECT 'deliverable:' || x FROM unnest(v_dl_refs) AS x)
       AND state <> 'disposed';
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
"""

# as 0055 made it (the downgrade)
ERASE_RUN_BEFORE = r"""
CREATE OR REPLACE FUNCTION owner.erase_order_run(p_order uuid) RETURNS jsonb
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
"""

RESCUE_KEEP = "'id', 'ref', 'company_id', 'source', 'exchange', 'subject', 'mystery', 'opened_at'"
RESCUE_KEEP_BEFORE = (
    "'id', 'ref', 'company_id', 'source', 'conversation_id', 'exchange', 'subject', 'mystery', "
    "'opened_at'"
)

UPGRADE = f"""
GRANT UPDATE (title_fa) ON core.employees TO hq_api, hq_worker;

DROP TRIGGER growth_rescue_cases_immutable ON growth.rescue_cases;
CREATE TRIGGER growth_rescue_cases_immutable BEFORE UPDATE ON growth.rescue_cases
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable({RESCUE_KEEP});
CREATE FUNCTION growth.rescue_conversation_set_once() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
    BEGIN
        IF OLD.conversation_id IS NOT NULL
           AND NEW.conversation_id IS DISTINCT FROM OLD.conversation_id THEN
            RAISE EXCEPTION 'growth.rescue_cases: conversation_id is set once'
                USING ERRCODE = 'HQI01';
        END IF;
        RETURN NEW;
    END $$;
CREATE TRIGGER growth_rescue_cases_conversation_once
    BEFORE UPDATE OF conversation_id ON growth.rescue_cases
    FOR EACH ROW EXECUTE FUNCTION growth.rescue_conversation_set_once();

CREATE FUNCTION archive.level_fixed_when_used() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    BEGIN
        IF (NEW.rank IS DISTINCT FROM OLD.rank OR NEW.encrypt IS DISTINCT FROM OLD.encrypt)
           AND EXISTS (SELECT 1 FROM archive.records r
                        WHERE r.level = OLD.key
                          AND (OLD.company_id IS NULL OR r.company_id = OLD.company_id)) THEN
            RAISE EXCEPTION 'archive level %: rank and encrypt are fixed while records use it',
                OLD.key USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$;
REVOKE ALL ON FUNCTION archive.level_fixed_when_used() FROM PUBLIC;
CREATE TRIGGER levels_fixed_when_used BEFORE UPDATE OF rank, encrypt ON archive.levels
    FOR EACH ROW EXECUTE FUNCTION archive.level_fixed_when_used();
"""

DOWNGRADE = f"""
DROP TRIGGER levels_fixed_when_used ON archive.levels;
DROP FUNCTION archive.level_fixed_when_used();

DROP TRIGGER growth_rescue_cases_conversation_once ON growth.rescue_cases;
DROP FUNCTION growth.rescue_conversation_set_once();
DROP TRIGGER growth_rescue_cases_immutable ON growth.rescue_cases;
CREATE TRIGGER growth_rescue_cases_immutable BEFORE UPDATE ON growth.rescue_cases
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable({RESCUE_KEEP_BEFORE});

REVOKE UPDATE (title_fa) ON core.employees FROM hq_api, hq_worker;
"""


def _progress_kinds(add: bool) -> str:
    """owner.progress's kind CHECK rewritten from the kinds it holds now (0055's helper), with
    `newsletter` added or taken out (taken out NOT VALID: rows already written stay)."""
    pick = "UNION SELECT 'newsletter'" if add else ""
    drop = "" if add else "AND k <> 'newsletter'"
    valid = "" if add else " NOT VALID"
    return f"""
        DO $$
        DECLARE kinds text;
        BEGIN
            SELECT string_agg(quote_literal(k), ', ' ORDER BY k) INTO kinds FROM (
                SELECT DISTINCT m[1] AS k
                FROM pg_constraint c,
                     regexp_matches(pg_get_constraintdef(c.oid), '''([a-z0-9_]+)''', 'g') AS m
                WHERE c.conrelid = 'owner.progress'::regclass AND c.conname = 'progress_kind_check'
                {pick}
            ) x WHERE k IS NOT NULL AND k <> '' {drop};
            ALTER TABLE owner.progress DROP CONSTRAINT progress_kind_check;
            EXECUTE format('ALTER TABLE owner.progress ADD CONSTRAINT progress_kind_check '
                           'CHECK (kind IN (%s)){valid}', kinds);
        END $$;
    """


def upgrade() -> None:
    execute_script(UPGRADE)
    execute_script(ERASE_RUN_FIXED)
    execute_script(_progress_kinds(True))


def downgrade() -> None:
    execute_script(_progress_kinds(False))
    execute_script(ERASE_RUN_BEFORE)
    execute_script(DOWNGRADE)
