"""Bug fixes of 2026-11-05 (the owner: «به مدیرعامل پیام میدم خبری نمیشه»; «گفتگو از هیچ چیز خبر نداشت»).

A talk turn opens a short `talk` run so the gateway lets its persona read (0043). Two faults:

- It shared `runs_one_running` (one running run per employee) with the employee's real work. While the secretary,
  the advisor or a CEO was in a run of its own, the talk could not open one, so every read was refused and the
  persona answered blind; and while a talk run was open, the employee's own queued run (an owner's message, an
  order) could not start.
- A talk run is closed by the turn itself. A worker that stopped mid-turn (a deploy, a restart) left it `running`
  for good, and the employee stayed "busy" for ever: its runs waited and the owner's messages were never answered.

Now a talk run never counts against the one-running rule, and talk runs past their token's expiry are failed by
`talk.reap_runs()` (called by the worker's sweep) and before each new talk run of the same employee.

Revision ID: 0045
Revises: 0044
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


UPGRADE = """
DROP INDEX agents.runs_one_running;
CREATE UNIQUE INDEX runs_one_running ON agents.runs (employee_id) WHERE state = 'running' AND trigger <> 'talk';
CREATE INDEX runs_talk_open ON agents.runs (token_expires_at) WHERE state = 'running' AND trigger = 'talk';

CREATE FUNCTION talk.reap_runs(p_employee uuid DEFAULT NULL) RETURNS int
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        n int;
    BEGIN
        UPDATE agents.runs
           SET state = 'failed', error_code = 'talk_expired', finished_at = now(), updated_at = now()
         WHERE trigger = 'talk' AND state = 'running'
           AND (p_employee IS NULL OR employee_id = p_employee)
           AND COALESCE(token_expires_at, started_at + interval '1 hour') < now();
        GET DIAGNOSTICS n = ROW_COUNT;
        RETURN n;
    END $$;
REVOKE ALL ON FUNCTION talk.reap_runs(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION talk.reap_runs(uuid) TO hq_api, hq_worker;

CREATE OR REPLACE FUNCTION talk.open_run(p_employee uuid, p_reason text, p_steps int, p_token_cap bigint,
                                         p_ttl_s int) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        e record;
        rid uuid;
        steps int := LEAST(GREATEST(p_steps, 1), 50);
    BEGIN
        SELECT id, company_id, status, role INTO e FROM core.employees WHERE id = p_employee;
        IF NOT FOUND OR e.status <> 'active' OR e.role IS NULL THEN
            RETURN NULL;
        END IF;
        PERFORM talk.reap_runs(e.id);
        INSERT INTO agents.runs (company_id, employee_id, trigger, reason, state, priority, charter_role,
                                 steps_cap, token_cap, tool_calls_cap, step_tool_calls_cap, started_at,
                                 token_expires_at)
        VALUES (e.company_id, e.id, 'talk', left(COALESCE(p_reason, ''), 200), 'running', 'P1', e.role,
                steps, GREATEST(p_token_cap, 0), LEAST(steps * 3, 500), 3, now(),
                now() + make_interval(secs => LEAST(GREATEST(p_ttl_s, 60), 3600)))
        RETURNING id INTO rid;
        RETURN rid;
    END $$;
"""

DOWNGRADE = """
CREATE OR REPLACE FUNCTION talk.open_run(p_employee uuid, p_reason text, p_steps int, p_token_cap bigint,
                                         p_ttl_s int) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        e record;
        rid uuid;
        steps int := LEAST(GREATEST(p_steps, 1), 50);
    BEGIN
        SELECT id, company_id, status, role INTO e FROM core.employees WHERE id = p_employee;
        IF NOT FOUND OR e.status <> 'active' OR e.role IS NULL THEN
            RETURN NULL;
        END IF;
        INSERT INTO agents.runs (company_id, employee_id, trigger, reason, state, priority, charter_role,
                                 steps_cap, token_cap, tool_calls_cap, step_tool_calls_cap, started_at,
                                 token_expires_at)
        VALUES (e.company_id, e.id, 'talk', left(COALESCE(p_reason, ''), 200), 'running', 'P1', e.role,
                steps, GREATEST(p_token_cap, 0), LEAST(steps * 3, 500), 3, now(),
                now() + make_interval(secs => LEAST(GREATEST(p_ttl_s, 60), 3600)))
        ON CONFLICT DO NOTHING
        RETURNING id INTO rid;
        RETURN rid;
    END $$;
DROP FUNCTION talk.reap_runs(uuid);
DROP INDEX agents.runs_talk_open;
UPDATE agents.runs SET state = 'failed', error_code = 'talk_expired', finished_at = now(), updated_at = now()
 WHERE trigger = 'talk' AND state = 'running';
DROP INDEX agents.runs_one_running;
CREATE UNIQUE INDEX runs_one_running ON agents.runs (employee_id) WHERE state = 'running';
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
