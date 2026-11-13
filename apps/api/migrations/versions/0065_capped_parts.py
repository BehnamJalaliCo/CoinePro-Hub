"""⟨2026-11-13⟩ F-0018 P5: a part that goes on by itself after its run's cap wakes nobody.

The runner queues the next run of a part of an open session that stopped at its per-run cap
(reason `capped:<ref>`, runner._continue_capped) before it delivers the partial output. The
deliverable trigger of 0050 (agents.wake_on_deliverable) still queued a run of the parent's
assignee for that partial output (`child_delivered:`), and the session's holder issued the part
again from nothing. The function gets one more skip: a deliverable whose title starts with
«خروجی ناقص» (work.PARTIAL_PREFIX), of a work with a queued `capped:` run, wakes nobody. A requested
work (no parent) is not this trigger's: order_turns.on_child_closed skips it the same way.

The function only; the downgrade puts the 0050 function back.

Revision ID: 0065
Revises: 0064
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

WAKE_ON_DELIVERABLE = """
CREATE OR REPLACE FUNCTION agents.wake_on_deliverable() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        c record;
        p record;
    BEGIN
        SELECT parent_id, ref INTO c FROM work.work WHERE id = NEW.work_id;
        IF c.parent_id IS NULL THEN
            RETURN NULL;
        END IF;
        IF EXISTS (SELECT 1 FROM work.split_parts sp WHERE sp.work_id = NEW.work_id) THEN
            RETURN NULL;
        END IF;
        {capped}
        SELECT id, assignee_id, status, priority INTO p FROM work.work WHERE id = c.parent_id;
        IF p.assignee_id IS NOT NULL AND p.status IN ('queued', 'in_progress', 'waiting') THEN
            PERFORM agents.queue_run(p.assignee_id, 'work', p.id, NULL,
                                     'child_delivered:' || c.ref || ':' || NEW.ref, p.priority);
        END IF;
        RETURN NULL;
    END $$;
"""
SKIP_CAPPED = """IF starts_with(NEW.title, 'خروجی ناقص') AND EXISTS (
            SELECT 1 FROM agents.runs r
            WHERE r.work_id = NEW.work_id AND r.state = 'queued' AND r.reason LIKE 'capped:%') THEN
            RETURN NULL;
        END IF;"""


def upgrade() -> None:
    execute_script(WAKE_ON_DELIVERABLE.format(capped=SKIP_CAPPED))


def downgrade() -> None:
    execute_script(WAKE_ON_DELIVERABLE.format(capped=""))
