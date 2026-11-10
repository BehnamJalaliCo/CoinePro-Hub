"""The direct session's turn has a run of its own (contract §54, v1.32; the owner, 2026-11-10:
«مثل همین سشنی که من با تو صحبت میکنم»).

The holder of a session is one Claude Code session on the workshop with the hub's tools. Every
tool call of that session still goes through the Tool Gateway, which acts for a **run** (its
caps, its audit rows). So a direct turn opens a run of the holder, `trigger = 'direct'`, for
the order's own work:

- it never counts against the one-running-run rule (as a `talk` run does not, 0045): a holder
  whose turn builds for an hour still answers its other work, and the owner's messages;
- one live direct run per work (`runs_one_direct`): a session has one brain and one thread;
- `agents.open_direct_run()` opens it (the app's roles cannot insert a running run), first
  failing one of the same work left open past its token (a turn whose end was never told);
- `agents.close_direct_run()` ends it with what the turn spent.

Additive; the downgrade keeps the direct runs as plain work runs (one still open ends).

Revision ID: 0061
Revises: 0060
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

TRIGGERS_BEFORE = "'work', 'message', 'schedule', 'alert', 'meeting', 'talk'"

UPGRADE = f"""
ALTER TABLE agents.runs DROP CONSTRAINT runs_trigger_check;
ALTER TABLE agents.runs ADD CONSTRAINT runs_trigger_check
    CHECK (trigger IN ({TRIGGERS_BEFORE}, 'direct'));

DROP INDEX agents.runs_one_running;
CREATE UNIQUE INDEX runs_one_running ON agents.runs (employee_id)
    WHERE state = 'running' AND trigger NOT IN ('talk', 'direct');
CREATE UNIQUE INDEX runs_one_direct ON agents.runs (work_id)
    WHERE state = 'running' AND trigger = 'direct';

CREATE FUNCTION agents.open_direct_run(p_employee uuid, p_work uuid, p_reason text, p_ttl_s int)
    RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        e record;
        rid uuid;
    BEGIN
        SELECT id, company_id, status, role INTO e FROM core.employees WHERE id = p_employee;
        IF NOT FOUND OR e.status <> 'active' OR e.role IS NULL OR p_work IS NULL THEN
            RETURN NULL;
        END IF;
        -- a turn whose end was never told (its runner gone): not open for ever
        UPDATE agents.runs
           SET state = 'failed', error_code = 'direct_expired', finished_at = now(),
               updated_at = now()
         WHERE trigger = 'direct' AND state = 'running' AND work_id = p_work
           AND COALESCE(token_expires_at, started_at + interval '2 hours') < now();
        INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
                                 priority, charter_role, steps_cap, tool_calls_cap,
                                 step_tool_calls_cap, started_at, token_expires_at)
        SELECT e.company_id, e.id, w.id, 'direct', left(COALESCE(p_reason, ''), 200), 'running',
               'P1', e.role, 50, 500, 50, now(),
               now() + make_interval(secs => LEAST(GREATEST(p_ttl_s, 60), 7200))
          FROM work.work w WHERE w.id = p_work
        ON CONFLICT DO NOTHING
        RETURNING id INTO rid;
        RETURN rid;
    END $$;
REVOKE ALL ON FUNCTION agents.open_direct_run(uuid, uuid, text, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION agents.open_direct_run(uuid, uuid, text, int) TO hq_api, hq_worker;

CREATE FUNCTION agents.close_direct_run(p_run uuid, p_state text, p_code text, p_in bigint,
                                        p_out bigint, p_cache_read bigint, p_cache_write bigint,
                                        p_note text)
    RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        n int;
    BEGIN
        IF p_state NOT IN ('done', 'failed') THEN
            RAISE EXCEPTION 'a direct run ends done or failed';
        END IF;
        UPDATE agents.runs
           SET state = p_state, error_code = p_code, finished_at = now(), updated_at = now(),
               input_tokens = GREATEST(COALESCE(p_in, 0), 0),
               output_tokens = GREATEST(COALESCE(p_out, 0), 0),
               cache_read_tokens = GREATEST(COALESCE(p_cache_read, 0), 0),
               cache_write_tokens = GREATEST(COALESCE(p_cache_write, 0), 0),
               note = left(p_note, 1000)
         WHERE id = p_run AND trigger = 'direct' AND state = 'running';
        GET DIAGNOSTICS n = ROW_COUNT;
        RETURN n > 0;
    END $$;
REVOKE ALL ON FUNCTION agents.close_direct_run(uuid, text, text, bigint, bigint, bigint, bigint, text)
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION agents.close_direct_run(uuid, text, text, bigint, bigint, bigint, bigint, text)
    TO hq_api, hq_worker;
"""  # noqa: S608 - composed from module constants only

DOWNGRADE = f"""
DROP FUNCTION agents.close_direct_run(uuid, text, text, bigint, bigint, bigint, bigint, text);
DROP FUNCTION agents.open_direct_run(uuid, uuid, text, int);
DROP INDEX agents.runs_one_direct;
DROP INDEX agents.runs_one_running;
-- the direct runs stay as history (their audit rows and memory rows name them), as plain work
-- runs of the same employee and work; one still open ends here
ALTER TABLE agents.runs DISABLE TRIGGER runs_immutable;
ALTER TABLE agents.runs DISABLE TRIGGER runs_guard;
UPDATE agents.runs
   SET trigger = 'work',
       error_code = CASE WHEN state = 'running' THEN 'direct_expired' ELSE error_code END,
       finished_at = CASE WHEN state = 'running' THEN now() ELSE finished_at END,
       state = CASE WHEN state = 'running' THEN 'failed' ELSE state END
 WHERE trigger = 'direct';
ALTER TABLE agents.runs ENABLE TRIGGER runs_guard;
ALTER TABLE agents.runs ENABLE TRIGGER runs_immutable;
CREATE UNIQUE INDEX runs_one_running ON agents.runs (employee_id)
    WHERE state = 'running' AND trigger <> 'talk';
ALTER TABLE agents.runs DROP CONSTRAINT runs_trigger_check;
ALTER TABLE agents.runs ADD CONSTRAINT runs_trigger_check CHECK (trigger IN ({TRIGGERS_BEFORE}));
"""  # noqa: S608 - composed from module constants only


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
