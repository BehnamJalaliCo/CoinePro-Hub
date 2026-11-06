"""The owner's order answered live (contract §34, the owner, 2026-11-06: «به محض فرمان باید اون
مسئول … با من حرف بزنه و مرحله به مرحله با من پیش بره یا یه فرمان کلی بدم خودش بره همه کارهارو
بکنه»).

- owner.orders.pace: `auto` (a general order: its holder plans it and carries it to the end) or
  `step` (the owner goes step by step with its holder: one step, then the holder asks).
- owner.order_reports.turn: the holder's open question to the owner (`order.ask`), cleared by the
  owner's reply (POST /orders/{ref}/reply). While it is set the order is `waiting` on the owner and
  no «no progress» timer runs.
- owner.order_reports.conversation_ref / talk.conversations.order_ref: the live talk with the
  order's holder (POST /orders/{ref}/talk); a step order opens it at once. What the owner tells the
  holder there becomes a card that goes onto that same order as the owner's next word.

- work.wake_assignee(work, reason): one run of an open work's assignee (SECURITY DEFINER; the api
  may not queue runs itself): the owner's reply wakes the holder at once.

Additive only; nothing is deleted.

Revision ID: 0051
Revises: 0050
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

UPGRADE = """
ALTER TABLE owner.orders
    ADD COLUMN pace text NOT NULL DEFAULT 'auto' CHECK (pace IN ('auto', 'step'));
ALTER TABLE owner.order_reports
    ADD COLUMN turn jsonb CHECK (turn IS NULL OR jsonb_typeof(turn) = 'object'),
    ADD COLUMN conversation_ref text CHECK (conversation_ref IS NULL OR conversation_ref ~ '^CV-[0-9]{4,}$');
ALTER TABLE talk.conversations
    ADD COLUMN order_ref text CHECK (order_ref IS NULL OR order_ref ~ '^F-[0-9]{4,}$');
CREATE INDEX conversations_order ON talk.conversations (order_ref) WHERE order_ref IS NOT NULL;
GRANT UPDATE (turn, conversation_ref) ON owner.order_reports TO hq_api, hq_worker;
GRANT UPDATE (order_ref) ON talk.conversations TO hq_api, hq_worker;

-- The owner's word wakes the work's assignee at once: one run of an open work (the api may not
-- queue runs itself; this is the one narrow door, for the owner's reply).
CREATE FUNCTION work.wake_assignee(p_work uuid, p_reason text) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        w record;
    BEGIN
        SELECT id, assignee_id, status INTO w FROM work.work WHERE id = p_work;
        IF NOT FOUND OR w.assignee_id IS NULL
           OR w.status NOT IN ('queued', 'in_progress', 'waiting') THEN
            RETURN NULL;
        END IF;
        RETURN agents.queue_run(w.assignee_id, 'work', w.id, NULL, left(COALESCE(p_reason, ''), 200), 'P1');
    END $$;
REVOKE ALL ON FUNCTION work.wake_assignee(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION work.wake_assignee(uuid, text) TO hq_api, hq_worker;
"""

DOWNGRADE = """
DROP FUNCTION IF EXISTS work.wake_assignee(uuid, text);
REVOKE UPDATE (order_ref) ON talk.conversations FROM hq_api, hq_worker;
REVOKE UPDATE (turn, conversation_ref) ON owner.order_reports FROM hq_api, hq_worker;
DROP INDEX IF EXISTS talk.conversations_order;
ALTER TABLE talk.conversations DROP COLUMN order_ref;
ALTER TABLE owner.order_reports DROP COLUMN conversation_ref, DROP COLUMN turn;
ALTER TABLE owner.orders DROP COLUMN pace;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
