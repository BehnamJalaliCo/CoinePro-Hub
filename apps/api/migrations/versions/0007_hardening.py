"""Prompt 04.1 hardening, in the database itself.

  - core.employee_scores: past months never change; the current month only
    its score columns; keys never change; DELETE/TRUNCATE refused (§1.2)
  - composite foreign keys (company_id, id): a child row always belongs to
    its parent's company (§1.10)
  - msg.messages: seq, ref and company_id come from the thread (trigger)
  - a decided decision is sealed: verdict, seal, note, amendments once (§1.10)
  - llm.assignments: the api role writes only through llm.put_assignment(),
    which keeps the change inside the caller's companies (§1.10)
  - audit.entries.at is always the database clock (§1.10)
  - notify.agent_notification_counts(): quota counts without widening the
    caller's company scope (§1.9)
  - color_index 1..8 or NULL (chart palette v2; the seed assigns slots) (§1.13)
  - llm.connections.version for If-Match (§1.14)
  - functions are no longer executable by PUBLIC; counters only through
    core.next_counter(); core.fa_normalize v2 (alef/teh marbuta/waw forms,
    ZWNJ as a space) and core.like_escape(); evidence items need kind + ref

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"

# (child table, child column, parent table) for (company_id, column) -> parent (company_id, id)
COMPOSITE_FKS = [
    ("work.work", "assignee_id", "core.employees"),
    ("work.work", "parent_id", "work.work"),
    ("work.work", "recurrence_of", "work.work"),
    ("work.work_events", "work_id", "work.work"),
    ("work.escrows", "work_id", "work.work"),
    ("work.escrows", "decision_id", "cartable.decisions"),
    ("work.schedules", "work_id", "work.work"),
    ("cartable.decisions", "work_id", "work.work"),
    ("cartable.deliverables", "work_id", "work.work"),
    ("cartable.deliverables", "producer_id", "core.employees"),
    ("cartable.ratings", "deliverable_id", "cartable.deliverables"),
    ("cartable.resolutions", "follow_up_work_id", "work.work"),
    ("cartable.resolutions", "source_decision_id", "cartable.decisions"),
    ("cartable.resolutions", "source_message_id", "msg.messages"),
    ("msg.messages", "thread_id", "msg.threads"),
    ("msg.threads", "employee_id", "core.employees"),
    ("core.employees", "reports_to", "core.employees"),
    ("core.employees", "hired_by_decision_id", "cartable.decisions"),
    ("core.employee_scores", "employee_id", "core.employees"),
]
PARENTS = ["core.employees", "work.work", "cartable.decisions", "cartable.deliverables", "msg.threads", "msg.messages"]


def upgrade() -> None:
    # ---------------------------------------------------------- composite FKs
    execute_script(
        "\n".join(
            f"ALTER TABLE {p} ADD CONSTRAINT {p.split('.')[1]}_company_id_key UNIQUE (company_id, id);" for p in PARENTS
        )
        + "\n"
        + "\n".join(
            f"""ALTER TABLE {c} ADD CONSTRAINT {c.split('.')[1]}_{col}_same_company
                    FOREIGN KEY (company_id, {col}) REFERENCES {p} (company_id, id);"""
            for c, col, p in COMPOSITE_FKS
        )
    )
    execute_script(
        rf"""
        -- --------------------------------------------- score history (§1.2)
        CREATE FUNCTION core.employee_scores_guard() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF OLD.month < date_trunc('month', now())::date THEN
                    RAISE EXCEPTION 'score history: % is closed', OLD.month USING ERRCODE = 'HQA01';
                END IF;
                RETURN NEW;
            END $$;
        CREATE TRIGGER employee_scores_closed_months BEFORE UPDATE ON core.employee_scores
            FOR EACH ROW EXECUTE FUNCTION core.employee_scores_guard();
        CREATE TRIGGER employee_scores_immutable BEFORE UPDATE ON core.employee_scores
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('employee_id', 'company_id', 'month');
        CREATE TRIGGER employee_scores_no_delete BEFORE DELETE ON core.employee_scores
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER employee_scores_no_truncate BEFORE TRUNCATE ON core.employee_scores
            FOR EACH STATEMENT EXECUTE FUNCTION core.reject_change();
        REVOKE UPDATE ON core.employee_scores FROM {APP_ROLES};
        GRANT UPDATE (value, components, computed_at) ON core.employee_scores TO {APP_ROLES};

        -- ------------------------------------------- messages from the thread
        CREATE FUNCTION msg.messages_number() RETURNS trigger
            LANGUAGE plpgsql AS $$
            DECLARE
                t msg.threads%ROWTYPE;
            BEGIN
                UPDATE msg.threads SET last_seq = last_seq + 1, last_message_at = now(),
                       owner_read_seq = CASE WHEN NEW.author_kind = 'owner' THEN last_seq + 1
                                             ELSE owner_read_seq END
                 WHERE id = NEW.thread_id RETURNING * INTO t;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'thread not found' USING ERRCODE = 'HQN01';
                END IF;
                NEW.company_id := t.company_id;
                NEW.seq := t.last_seq;
                NEW.ref := t.code || '-' || lpad(t.last_seq::text, greatest(4, length(t.last_seq::text)), '0');
                NEW.created_at := now();
                RETURN NEW;
            END $$;
        CREATE TRIGGER messages_number BEFORE INSERT ON msg.messages
            FOR EACH ROW EXECUTE FUNCTION msg.messages_number();
        CREATE OR REPLACE FUNCTION msg.post(p_thread uuid, p_author_kind text, p_author_code text, p_body text,
                                            p_links jsonb, p_attachments uuid[], p_kind text)
            RETURNS msg.messages
            LANGUAGE sql AS $$
            INSERT INTO msg.messages (thread_id, company_id, seq, ref, author_kind, author_code, body,
                                      attachments, links, kind)
            VALUES (p_thread, '00000000-0000-0000-0000-000000000000', 0, '', p_author_kind, p_author_code,
                    p_body, COALESCE(p_attachments, '{{}}'), COALESCE(p_links, '{{}}'), COALESCE(p_kind, 'text'))
            RETURNING *
            $$;

        -- ------------------------------------------------- sealed decisions
        CREATE FUNCTION cartable.decisions_sealed() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF OLD.status <> 'pending' AND (
                       NEW.decided_at IS DISTINCT FROM OLD.decided_at
                    OR NEW.decided_by_kind IS DISTINCT FROM OLD.decided_by_kind
                    OR NEW.decided_by_code IS DISTINCT FROM OLD.decided_by_code
                    OR NEW.seal_at IS DISTINCT FROM OLD.seal_at
                    OR NEW.seal_method IS DISTINCT FROM OLD.seal_method
                    OR NEW.seal_step_up_id IS DISTINCT FROM OLD.seal_step_up_id
                    OR NEW.note IS DISTINCT FROM OLD.note
                    OR NEW.reason_code IS DISTINCT FROM OLD.reason_code
                    OR NEW.amendments::text IS DISTINCT FROM OLD.amendments::text) THEN
                    RAISE EXCEPTION 'decision % is sealed', OLD.ref USING ERRCODE = 'HQI01';
                END IF;
                RETURN NEW;
            END $$;
        CREATE TRIGGER decisions_sealed BEFORE UPDATE ON cartable.decisions
            FOR EACH ROW EXECUTE FUNCTION cartable.decisions_sealed();

        -- ------------------------------------------ assignments, scope-checked
        REVOKE INSERT, UPDATE ON llm.assignments FROM hq_api;
        CREATE FUNCTION llm.put_assignment(p_scope_type text, p_scope_ref text, p_connection uuid,
                                           p_model text, p_effort text, p_note text) RETURNS void
            LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            DECLARE
                allowed uuid[] := COALESCE(NULLIF(current_setting('app.company_ids', true), '')::uuid[], '{{}}');
                holding uuid := (SELECT id FROM core.companies WHERE kind = 'holding');
                co_code text;
            BEGIN
                IF p_scope_type = 'holding' THEN
                    co_code := NULL;
                ELSIF p_scope_type = 'company' THEN
                    co_code := p_scope_ref;
                ELSIF p_scope_type = 'department' THEN
                    co_code := split_part(p_scope_ref, '-', 1);
                ELSIF p_scope_type IN ('role', 'task_class') THEN
                    co_code := CASE WHEN position(':' IN p_scope_ref) > 0 THEN split_part(p_scope_ref, ':', 1) END;
                ELSE
                    RAISE EXCEPTION 'unknown scope type' USING ERRCODE = 'HQV01';
                END IF;
                -- Holding-wide levels (and global role/task-class refs) need the
                -- holding in the caller's scope: the owner, never one company.
                IF co_code IS NULL THEN
                    IF NOT holding = ANY (allowed) THEN
                        RAISE EXCEPTION 'outside the caller''s companies' USING ERRCODE = '42501';
                    END IF;
                ELSIF NOT EXISTS (SELECT 1 FROM core.companies c WHERE c.code = co_code AND c.id = ANY (allowed)) THEN
                    RAISE EXCEPTION 'outside the caller''s companies' USING ERRCODE = '42501';
                END IF;
                INSERT INTO llm.assignments (scope_type, scope_ref, connection_id, model, effort, note)
                VALUES (p_scope_type, p_scope_ref, p_connection, p_model, p_effort, p_note)
                ON CONFLICT (scope_type, scope_ref) DO UPDATE
                    SET connection_id = EXCLUDED.connection_id, model = EXCLUDED.model,
                        effort = EXCLUDED.effort, note = EXCLUDED.note, updated_at = now();
            END $$;
        REVOKE ALL ON FUNCTION llm.put_assignment(text, text, uuid, text, text, text) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION llm.put_assignment(text, text, uuid, text, text, text) TO {APP_ROLES};

        -- ---------------------------------------------- the audit clock
        CREATE OR REPLACE FUNCTION audit.chain() RETURNS trigger
            LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            DECLARE
                h audit.chain_head%ROWTYPE;
            BEGIN
                SELECT * INTO h FROM audit.chain_head WHERE id = 1 FOR UPDATE;
                NEW.seq := h.last_seq + 1;
                NEW.at := clock_timestamp();  -- always the database clock
                NEW.prev_hash := h.last_hash;
                NEW.hash := encode(sha256(convert_to(NEW.prev_hash || audit.canonical(NEW), 'UTF8')), 'hex');
                UPDATE audit.chain_head SET last_seq = NEW.seq, last_hash = NEW.hash WHERE id = 1;
                RETURN NEW;
            END $$;

        -- The chain head is read (never written) by the anchoring job and verify.
        GRANT SELECT ON audit.chain_head TO {APP_ROLES};

        -- -------------------------- notification quotas without widening scope
        CREATE FUNCTION notify.agent_notification_counts(p_day_start timestamptz, p_source_code text,
                                                         p_company uuid,
                                                         OUT learning_today bigint, OUT source_today bigint,
                                                         OUT company_urgent_hour bigint)
            LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            SELECT (SELECT count(*) FROM notify.notifications
                     WHERE level = 'learning' AND created_at >= p_day_start AND delivered_in_app),
                   (SELECT count(*) FROM notify.notifications
                     WHERE source_kind = 'agent' AND source_code = p_source_code AND level <> 'urgent'
                       AND created_at >= p_day_start AND state <> 'suppressed'),
                   (SELECT count(*) FROM notify.notifications
                     WHERE company_id = p_company AND source_kind = 'agent' AND level = 'urgent'
                       AND created_at >= now() - interval '1 hour')
            $$;
        REVOKE ALL ON FUNCTION notify.agent_notification_counts(timestamptz, text, uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION notify.agent_notification_counts(timestamptz, text, uuid) TO {APP_ROLES};

        -- ---------------------------------------------------- colour slots
        ALTER TABLE core.companies DROP CONSTRAINT companies_color_index_check;
        UPDATE core.companies SET color_index = NULL WHERE color_index IS NOT NULL;
        ALTER TABLE core.companies ADD CONSTRAINT companies_color_index_check CHECK (color_index BETWEEN 1 AND 8);
        CREATE UNIQUE INDEX companies_color_slot ON core.companies (color_index) WHERE color_index IS NOT NULL;

        -- ------------------------------ passkeys: a suspected clone is flagged
        ALTER TABLE auth.passkeys ADD COLUMN flagged_at timestamptz, ADD COLUMN flag_reason text;
        GRANT UPDATE (flagged_at, flag_reason) ON auth.passkeys TO hq_api;

        -- ------------------------------------------- connections: If-Match
        ALTER TABLE llm.connections ADD COLUMN version int NOT NULL DEFAULT 1;
        CREATE TRIGGER connections_version BEFORE UPDATE ON llm.connections
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();

        -- ---------------------------------- counters only through functions
        CREATE OR REPLACE FUNCTION core.next_counter(p_name text) RETURNS bigint
            LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            INSERT INTO core.counters AS c (name, value) VALUES (p_name, 1)
            ON CONFLICT (name) DO UPDATE SET value = c.value + 1
            RETURNING value
            $$;
        REVOKE INSERT, UPDATE ON core.counters FROM {APP_ROLES};

        -- ------------------------------------------- evidence must say something
        CREATE FUNCTION work.evidence_ok(e jsonb) RETURNS boolean
            LANGUAGE sql IMMUTABLE AS $$
            SELECT jsonb_typeof(e) = 'array' AND NOT EXISTS (
                SELECT 1 FROM jsonb_array_elements(e) x
                WHERE jsonb_typeof(x) <> 'object' OR COALESCE(x ->> 'kind', '') = '' OR COALESCE(x ->> 'ref', '') = '')
            $$;
        ALTER TABLE work.work ADD CONSTRAINT work_evidence_items CHECK (work.evidence_ok(evidence)) NOT VALID;
        ALTER TABLE cartable.deliverables ADD CONSTRAINT deliverables_evidence_items
            CHECK (work.evidence_ok(evidence)) NOT VALID;

        -- --------------------------- Persian normalisation v2 + LIKE escaping
        CREATE OR REPLACE FUNCTION core.fa_normalize(t text) RETURNS text
            LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
            AS $$
            SELECT btrim(regexp_replace(lower(translate(t,
                U&'\064A\0649\0643\06C0\0623\0625\0622\0671\0629\0624\200C'
                || U&'\06F0\06F1\06F2\06F3\06F4\06F5\06F6\06F7\06F8\06F9'
                || U&'\0660\0661\0662\0663\0664\0665\0666\0667\0668\0669'
                || U&'\200D\0640'
                || U&'\064B\064C\064D\064E\064F\0650\0651\0652\0653\0654\0655'
                || U&'\0656\0657\0658\0659\065A\065B\065C\065D\065E\065F\0670',
                U&'\06CC\06CC\06A9\0647\0627\0627\0627\0627\0647\0648 ' || '0123456789' || '0123456789')),
                '\s+', ' ', 'g'))
            $$;
        CREATE FUNCTION core.like_escape(t text) RETURNS text
            LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
            AS $$ SELECT replace(replace(replace(t, '\', '\\'), '%', '\%'), '_', '\_') $$;
        -- Stored search columns and indexes follow the new normalisation.
        DROP INDEX msg.messages_trgm;
        ALTER TABLE msg.messages DROP COLUMN search;
        ALTER TABLE msg.messages ADD COLUMN search tsvector
            GENERATED ALWAYS AS (to_tsvector('simple', core.fa_normalize(body))) STORED;
        CREATE INDEX messages_search ON msg.messages USING gin (search);
        CREATE INDEX messages_trgm ON msg.messages USING gin (core.fa_normalize(body) gin_trgm_ops);
        """
    )
    # Functions are executable by PUBLIC by default: only the roles that need them.
    execute_script(
        rf"""
        DO $$
        DECLARE f record;
        BEGIN
            FOR f IN SELECT p.oid::regprocedure AS sig FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                     WHERE n.nspname IN ('core', 'work', 'cartable', 'msg', 'notify', 'owner', 'audit', 'control', 'files')
            LOOP
                EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f.sig);
            END LOOP;
        END $$;
        GRANT EXECUTE ON FUNCTION core.fa_normalize(text), core.like_escape(text), core.allowed_company_ids(),
            core.issue_employee_code(uuid, uuid), core.next_counter(text), cartable.next_resolution_ref(),
            msg.post(uuid, text, text, text, jsonb, uuid[], text), audit.verify_chain(),
            control.lock_state(uuid), work.evidence_ok(jsonb) TO {APP_ROLES};
        GRANT EXECUTE ON FUNCTION control.lock_state(uuid) TO hq_llm_writer, hq_llm_reader;
        GRANT EXECUTE ON FUNCTION notify.agent_notification_counts(timestamptz, text, uuid) TO {APP_ROLES};
        """
    )


def downgrade() -> None:
    raise NotImplementedError("0007 hardens rules in place; restore from backup to go back")
