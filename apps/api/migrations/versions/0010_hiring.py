"""Prompt 5.1 §1.3: hiring starts with the owner (contract §18.11, v1.4.2).

Owner decision, 2026-10-17: none of the seven hire proposals of prompt 5 is
approved. Until the owner brings the hub up for real work, nobody proposes a
hire; then the owner either hires directly or asks the CEOs for proposals.

- core.hiring: the hiring state, one row for the holding (RLS like every
  tenant table; written by the api only). No row = closed. `state` is "open"
  only in mode "proposals" (agents may propose hires); mode "self" keeps it
  closed to agents while the owner hires directly. `withdrawn` keeps the refs
  of the hire cards the system withdrew.
- core.hiring_state(): the state for any caller (SECURITY DEFINER), so a
  company-scoped agent transaction, which cannot see the holding's row, still
  reads it. Anything missing reads "closed" (fail-closed).
- cartable.withdraw_pending_hires(note): every pending hire card becomes
  `withdrawn` (decided_by system, the owner's note, a system message in its
  thread, `decision.updated`, an audit row) and its ref is kept in
  core.hiring.withdrawn. Nothing is deleted. Used by this migration and by
  POST /owner/hiring/close, so both do exactly the same.
- Once, now: the pending cards (D-000001..D-000007 on the hub) are withdrawn,
  and the month-1 setup work whose aim was hire proposals (tag
  bootstrap:month1:*) is cancelled with the same note if still open; its
  queued runs are refused. Running it again changes nothing.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
NOTE = "مالک: استخدام با شروع خود مالک"


def upgrade() -> None:
    execute_script(
        rf"""
        CREATE TABLE core.hiring (
            company_id       uuid PRIMARY KEY REFERENCES core.companies (id),
            state            text NOT NULL DEFAULT 'closed' CHECK (state IN ('closed', 'open')),
            mode             text CHECK (mode IN ('self', 'proposals')),
            changed_at       timestamptz,
            changed_by_kind  text CHECK (changed_by_kind IN ('owner', 'service')),
            changed_by_code  text CHECK (length(changed_by_code) BETWEEN 1 AND 64),
            withdrawn        text[] NOT NULL DEFAULT '{{}}',
            CHECK (state = 'closed' OR mode = 'proposals')
        );
        COMMENT ON TABLE core.hiring IS
            'Hiring state of the holding (contract 18.11); no row = closed';
        ALTER TABLE core.hiring ENABLE ROW LEVEL SECURITY;
        ALTER TABLE core.hiring FORCE ROW LEVEL SECURITY;
        CREATE POLICY hiring_tenant ON core.hiring TO {APP_ROLES}
            USING (company_id = ANY ((SELECT core.allowed_company_ids())::uuid[]))
            WITH CHECK (company_id = ANY ((SELECT core.allowed_company_ids())::uuid[]));
        CREATE POLICY hiring_owner_role ON core.hiring TO hq USING (true) WITH CHECK (true);
        GRANT SELECT ON core.hiring TO {APP_ROLES};
        GRANT INSERT, UPDATE (state, mode, changed_at, changed_by_kind, changed_by_code, withdrawn)
            ON core.hiring TO hq_api;

        CREATE FUNCTION core.hiring_state() RETURNS text
            LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
                SELECT COALESCE(
                    (SELECT h.state FROM core.hiring h
                       JOIN core.companies c ON c.id = h.company_id
                      WHERE c.kind = 'holding'),
                    'closed')
            $$;
        REVOKE ALL ON FUNCTION core.hiring_state() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION core.hiring_state() TO {APP_ROLES};

        CREATE FUNCTION cartable.withdraw_pending_hires(p_note text) RETURNS text[]
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
                                jsonb_build_object(
                                    'id', gen_random_uuid(), 'type', 'message.created',
                                    'at', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
                                    'company', d.company, 'ref', m.ref,
                                    'data', jsonb_build_object('thread', d.thread_code, 'author', 'system')));
                    END IF;
                    INSERT INTO core.outbox (event_id, subject, payload)
                    VALUES (gen_random_uuid(), 'hq.core.' || d.company || '.decision.updated',
                            jsonb_build_object(
                                'id', gen_random_uuid(), 'type', 'decision.updated',
                                'at', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
                                'company', d.company, 'ref', d.ref,
                                'data', jsonb_build_object('status', 'withdrawn', 'kind', 'hire',
                                                           'note', p_note)));
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
        REVOKE ALL ON FUNCTION cartable.withdraw_pending_hires(text) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION cartable.withdraw_pending_hires(text) TO hq_api;

        -- Once, now (idempotent): withdraw what is pending and cancel the open
        -- month-1 setup work whose aim was hire proposals.
        INSERT INTO core.hiring (company_id)
            SELECT id FROM core.companies WHERE kind = 'holding' ON CONFLICT DO NOTHING;
        SELECT cartable.withdraw_pending_hires('{NOTE}');

        DO $cancel$
        DECLARE
            w record;
        BEGIN
            FOR w IN
                SELECT DISTINCT x.id, x.ref, x.company_id, c.code AS company
                  FROM work.work x
                  JOIN work.work_events e ON e.work_id = x.id
                  JOIN core.companies c ON c.id = x.company_id
                 WHERE e.kind = 'bootstrap' AND e.data->>'tag' LIKE 'bootstrap:month1:%'
                   AND x.status IN ('queued', 'in_progress', 'waiting', 'delivered')
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
                        jsonb_build_object(
                            'id', gen_random_uuid(), 'type', 'work.updated',
                            'at', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
                            'company', w.company, 'ref', w.ref,
                            'data', jsonb_build_object('status', 'cancelled')));
                INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action,
                                           action_class, target_kind, target_ref, summary)
                VALUES ('system', 'system', 'system', w.company_id, 'work.cancel', 'A2', 'work', w.ref,
                        '{NOTE}');
            END LOOP;
        END
        $cancel$;
        """
    )


def downgrade() -> None:
    execute_script(
        """
        DROP FUNCTION cartable.withdraw_pending_hires(text);
        DROP FUNCTION core.hiring_state();
        DROP TABLE core.hiring;
        """
    )
