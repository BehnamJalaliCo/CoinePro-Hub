"""Prompt 19.3 (contract §28.5 ⟨1.10.1⟩): the owner deletes notifications for
good.

`notify.owner_delete_notifications` (SECURITY DEFINER, owner hq) removes the
given notifications, or every read one shown in the app up to a moment, and
answers how many went. Only hq_api may call it (the owner's route); no app
role gets DELETE on the table itself. No tombstone: a notification is a copy
of an event that stays in its own record (contract §28.5).

Revision ID: 0035
Revises: 0034
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

UPGRADE = """
-- -> how many notifications went: the ids given (read or not), or with no ids
-- every read one shown in the app created up to p_before
CREATE OR REPLACE FUNCTION notify.owner_delete_notifications(p_ids uuid[], p_before timestamptz)
    RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    n integer;
BEGIN
    IF p_ids IS NOT NULL THEN
        DELETE FROM notify.notifications WHERE id = ANY (p_ids);
    ELSIF p_before IS NOT NULL THEN
        DELETE FROM notify.notifications
         WHERE read_at IS NOT NULL AND delivered_in_app AND created_at <= p_before;
    ELSE
        RAISE EXCEPTION 'ids or a moment are needed' USING ERRCODE = '22023';
    END IF;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $$;
REVOKE ALL ON FUNCTION notify.owner_delete_notifications(uuid[], timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION notify.owner_delete_notifications(uuid[], timestamptz) TO hq_api;
"""

DOWNGRADE = """
DROP FUNCTION notify.owner_delete_notifications(uuid[], timestamptz);
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
