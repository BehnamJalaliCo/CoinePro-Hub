"""Review of prompt 5.1: hiring to contract v1.4.3, and the review's fixes.

- core.hiring.mode is "delegated" | "proposals" (v1.4.3 §18.11); the old
  "self" mode (never used on the hub) reads as no mode.
- cartable.decisions gains `approver` (approver_kind/approver_code; NULL = the
  owner decides, §5.1) and core.employees gains `probation_until` (§4): both
  NULL until delegated hiring arrives (prompt 8).
- core.hiring_state_for_share(): the state read with FOR SHARE on the
  holding's row, inside the proposing transaction, so a concurrent close
  (an UPDATE of that row) waits for the proposal to commit and then
  withdraws it: no pending hire card can outlive a close.
- cartable.withdraw_pending_hires() also emits `decision.decided` with
  status withdrawn (the §7 type clients follow), and the cards withdrawn by
  migration 0010 get that event now, once.
- The month-1 setup work cancelled by 0010 had its open children left
  running: they are cancelled now with the same note (queued runs refused).

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
NOTE = "مالک: استخدام با شروع خود مالک"
ENVELOPE = """jsonb_build_object(
                    'id', gen_random_uuid(), 'type', {type},
                    'at', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
                    'company', {company}, 'ref', {ref}, 'data', {data})"""


def _event(type_: str, company: str, ref: str, data: str) -> str:
    return ENVELOPE.format(type=f"'{type_}'", company=company, ref=ref, data=data)


def upgrade() -> None:
    withdrawn_data = "jsonb_build_object('status', 'withdrawn', 'kind', 'hire', 'note', p_note)"
    execute_script(
        rf"""
        UPDATE core.hiring SET mode = NULL WHERE mode = 'self';
        ALTER TABLE core.hiring DROP CONSTRAINT IF EXISTS hiring_mode_check;
        ALTER TABLE core.hiring ADD CONSTRAINT hiring_mode_check
            CHECK (mode IN ('delegated', 'proposals'));
        ALTER TABLE core.hiring DROP CONSTRAINT IF EXISTS hiring_check;
        ALTER TABLE core.hiring ADD CONSTRAINT hiring_check
            CHECK (state = 'closed' OR mode IN ('delegated', 'proposals'));

        ALTER TABLE cartable.decisions
            ADD COLUMN approver_kind text CHECK (approver_kind IN ('owner', 'agent')),
            ADD COLUMN approver_code text CHECK (length(approver_code) BETWEEN 1 AND 64),
            ADD CONSTRAINT decisions_approver_pair
                CHECK ((approver_kind IS NULL) = (approver_code IS NULL));
        COMMENT ON COLUMN cartable.decisions.approver_kind IS
            'who decides the card (contract 18.11); NULL = the owner';
        ALTER TABLE core.employees ADD COLUMN probation_until timestamptz;
        COMMENT ON COLUMN core.employees.probation_until IS
            'end of the probation after a delegated hire (contract 18.11), else NULL';

        CREATE FUNCTION core.hiring_state_for_share() RETURNS text
            LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            DECLARE
                s text;
            BEGIN
                SELECT h.state INTO s FROM core.hiring h
                  JOIN core.companies c ON c.id = h.company_id
                 WHERE c.kind = 'holding'
                   FOR SHARE OF h;
                RETURN COALESCE(s, 'closed');
            END $$;
        REVOKE ALL ON FUNCTION core.hiring_state_for_share() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION core.hiring_state_for_share() TO {APP_ROLES};

        CREATE OR REPLACE FUNCTION cartable.withdraw_pending_hires(p_note text) RETURNS text[]
            LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
            DECLARE
                d record;
                m msg.messages%ROWTYPE;
                refs text[] := '{{}}';
                holding uuid;
            BEGIN
                FOR d IN
                    SELECT x.id, x.ref, x.company_id, x.thread_code, c.code AS company
                      FROM cartable.decisions x JOIN core.companies c ON c.id = x.company_id
                     WHERE x.kind = 'hire' AND x.status = 'pending'
                     ORDER BY x.created_at
                       FOR UPDATE OF x
                LOOP
                    UPDATE cartable.decisions
                       SET status = 'withdrawn', decided_at = now(), decided_by_kind = 'service',
                           decided_by_code = 'system', note = p_note
                     WHERE id = d.id;
                    IF d.thread_code IS NOT NULL
                       AND EXISTS (SELECT 1 FROM msg.threads WHERE code = d.thread_code) THEN
                        m := msg.post((SELECT id FROM msg.threads WHERE code = d.thread_code),
                                      'service', 'system',
                                      'تصمیم ' || d.ref || ' پس گرفته شد · ' || p_note,
                                      jsonb_build_object('decision', d.ref), NULL, 'system');
                        INSERT INTO core.outbox (event_id, subject, payload)
                        VALUES (gen_random_uuid(), 'hq.core.' || d.company || '.message.created',
                                {_event("message.created", "d.company", "m.ref", "jsonb_build_object('thread', d.thread_code, 'author', 'system')")});
                    END IF;
                    -- decision.decided is the type every client follows (§7); .updated stays
                    INSERT INTO core.outbox (event_id, subject, payload)
                    VALUES (gen_random_uuid(), 'hq.core.' || d.company || '.decision.decided',
                            {_event("decision.decided", "d.company", "d.ref", withdrawn_data)});
                    INSERT INTO core.outbox (event_id, subject, payload)
                    VALUES (gen_random_uuid(), 'hq.core.' || d.company || '.decision.updated',
                            {_event("decision.updated", "d.company", "d.ref", withdrawn_data)});
                    INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action,
                                               action_class, target_kind, target_ref, summary)
                    VALUES ('system', 'system', 'system', d.company_id, 'decision.withdraw', 'A1',
                            'decision', d.ref, left(p_note, 500));
                    refs := refs || d.ref;
                END LOOP;
                IF cardinality(refs) > 0 THEN
                    SELECT id INTO holding FROM core.companies WHERE kind = 'holding';
                    IF holding IS NOT NULL THEN
                        INSERT INTO core.hiring (company_id) VALUES (holding) ON CONFLICT DO NOTHING;
                        UPDATE core.hiring
                           SET withdrawn = ARRAY(SELECT DISTINCT unnest(withdrawn || refs) ORDER BY 1)
                         WHERE company_id = holding;
                    END IF;
                END IF;
                RETURN refs;
            END $$;

        -- The cards 0010 withdrew get their decision.decided once.
        INSERT INTO core.outbox (event_id, subject, payload)
        SELECT gen_random_uuid(), 'hq.core.' || c.code || '.decision.decided',
               {_event("decision.decided", "c.code", "d.ref", "jsonb_build_object('status', 'withdrawn', 'kind', 'hire', 'note', d.note)")}
          FROM cartable.decisions d JOIN core.companies c ON c.id = d.company_id
         WHERE d.kind = 'hire' AND d.status = 'withdrawn' AND d.decided_by_code = 'system'
           AND NOT EXISTS (SELECT 1 FROM core.outbox o
                            WHERE o.subject = 'hq.core.' || c.code || '.decision.decided'
                              AND o.payload->>'ref' = d.ref);

        -- The open children of the cancelled month-1 setup work, with the same note.
        DO $children$
        DECLARE
            w record;
        BEGIN
            FOR w IN
                WITH RECURSIVE root AS (
                    SELECT DISTINCT x.id FROM work.work x
                      JOIN work.work_events e ON e.work_id = x.id
                     WHERE e.kind = 'bootstrap' AND e.data->>'tag' LIKE 'bootstrap:month1:%'
                       AND x.status = 'cancelled' AND x.close_reason = '{NOTE}'),
                down AS (
                    SELECT c.id FROM work.work c JOIN root ON c.parent_id = root.id
                    UNION SELECT c.id FROM work.work c JOIN down ON c.parent_id = down.id)
                SELECT x.id, x.ref, x.company_id, c.code AS company
                  FROM work.work x JOIN down ON down.id = x.id
                  JOIN core.companies c ON c.id = x.company_id
                 WHERE x.status IN ('queued', 'in_progress', 'waiting', 'delivered')
            LOOP
                UPDATE work.work SET status = 'cancelled', close_reason = '{NOTE}', closed_at = now()
                 WHERE id = w.id;
                INSERT INTO work.work_events (work_id, company_id, kind, actor_kind, actor_code, data)
                VALUES (w.id, w.company_id, 'cancelled', 'service', 'system',
                        jsonb_build_object('reason', '{NOTE}', 'cascade', 0));
                UPDATE agents.runs SET state = 'refused', error_code = 'work_closed', finished_at = now(),
                       note = '{NOTE}'
                 WHERE work_id = w.id AND state = 'queued';
                INSERT INTO core.outbox (event_id, subject, payload)
                VALUES (gen_random_uuid(), 'hq.core.' || w.company || '.work.updated',
                        {_event("work.updated", "w.company", "w.ref", "jsonb_build_object('status', 'cancelled')")});
                INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action,
                                           action_class, target_kind, target_ref, summary)
                VALUES ('system', 'system', 'system', w.company_id, 'work.cancel', 'A2', 'work', w.ref,
                        '{NOTE}');
            END LOOP;
        END
        $children$;
        """
    )


def downgrade() -> None:
    execute_script(
        """
        DROP FUNCTION core.hiring_state_for_share();
        ALTER TABLE core.employees DROP COLUMN probation_until;
        ALTER TABLE cartable.decisions DROP CONSTRAINT decisions_approver_pair,
            DROP COLUMN approver_code, DROP COLUMN approver_kind;
        UPDATE core.hiring SET state = 'closed', mode = NULL WHERE mode = 'delegated';
        ALTER TABLE core.hiring DROP CONSTRAINT hiring_check, DROP CONSTRAINT hiring_mode_check;
        ALTER TABLE core.hiring ADD CONSTRAINT hiring_mode_check CHECK (mode IN ('self', 'proposals')),
            ADD CONSTRAINT hiring_check CHECK (state = 'closed' OR mode = 'proposals');
        """
    )
