"""Prompt 08 §1 (contract §18.0): the Chief Overseer and the personal assistant.

- core.employees.kind and msg.threads.kind gain `overseer` and `assistant`;
  thread codes `N` (the overseer's) and `P` (the assistant's) beside `A`.
- The owner writing in either thread wakes its agent at P2, like the advisor.
The positions themselves (HQ-OVR, HQ-PA) are data: the holding template.

Revision ID: 0018
Revises: 0014
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0018"
down_revision = "0014"
branch_labels = None
depends_on = None

EMPLOYEE_KINDS = "'ceo', 'manager', 'employee', 'advisor', 'inspector', 'system'"
THREAD_KINDS = "'advisor', 'ceo', 'manager', 'department', 'employee'"
THREAD_CODE = "^(A|[A-Z][A-Z0-9]{1,9}(-[A-Z0-9]+){1,2})$"
THREAD_CODE_V2 = "^(A|N|P|[A-Z][A-Z0-9]{1,9}(-[A-Z0-9]+){1,2})$"

WAKE = """
CREATE OR REPLACE FUNCTION agents.wake_on_message() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        t record;
    BEGIN
        IF NEW.author_kind <> 'owner' THEN
            RETURN NULL;
        END IF;
        SELECT kind, employee_id INTO t FROM msg.threads WHERE id = NEW.thread_id;
        IF t.employee_id IS NOT NULL AND t.kind IN ({kinds}) THEN
            PERFORM agents.queue_run(t.employee_id, 'message', NULL, NEW.thread_id,
                                     'message:' || NEW.ref,
                                     CASE WHEN t.kind IN ({p2}) THEN 'P2' END);
        END IF;
        RETURN NULL;
    END $$;
"""


def _kinds(table: str, constraint: str, kinds: str) -> str:
    return f"""
        ALTER TABLE {table} DROP CONSTRAINT {constraint};
        ALTER TABLE {table} ADD CONSTRAINT {constraint} CHECK (kind IN ({kinds}));"""


def upgrade() -> None:
    execute_script(
        _kinds("core.employees", "employees_kind_check", f"{EMPLOYEE_KINDS}, 'overseer', 'assistant'")
        + _kinds("msg.threads", "threads_kind_check", f"{THREAD_KINDS}, 'overseer', 'assistant'")
        + f"""
        ALTER TABLE msg.threads DROP CONSTRAINT threads_code_check;
        ALTER TABLE msg.threads ADD CONSTRAINT threads_code_check CHECK (code ~ '{THREAD_CODE_V2}');
        """
        + WAKE.format(
            kinds="'advisor', 'overseer', 'assistant', 'ceo', 'manager', 'employee'",
            p2="'advisor', 'overseer', 'assistant'",
        )
    )


def downgrade() -> None:
    # NOT VALID: the seeded overseer and assistant rows stay (data); new rows
    # of those kinds are refused again.
    execute_script(
        _kinds("msg.threads", "threads_kind_check", THREAD_KINDS).replace(");", ") NOT VALID;")
        + f"""
        ALTER TABLE msg.threads DROP CONSTRAINT threads_code_check;
        ALTER TABLE msg.threads ADD CONSTRAINT threads_code_check CHECK (code ~ '{THREAD_CODE}') NOT VALID;
        """
        + _kinds("core.employees", "employees_kind_check", EMPLOYEE_KINDS).replace(");", ") NOT VALID;")
        + WAKE.format(kinds="'advisor', 'ceo', 'manager', 'employee'", p2="'advisor'")
    )
