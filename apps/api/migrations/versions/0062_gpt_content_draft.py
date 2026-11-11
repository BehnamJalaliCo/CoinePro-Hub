"""ChatGPT writes the script, as the owner ordered (the stall of 2026-11-10; the owner's reels
order, docs/ORDER_PROCHART_REELS_2026-11-10.md: topic, script, directing and cover «با ChatGPT»).

- substitutes.seats: GPT's `content_draft` seat (via web, the strong model, 30 a day, on). GPT had
  none (only Gemini sat there), so a holder that named ChatGPT for a script draft was refused.
  The seed adds a player's seats only when it seeds the player itself, so an existing hub gets the
  row here; a fresh database gets it from the seed (no players yet: nothing is inserted here).
  Gemini keeps its own seat. The model is `gpt-5.5` while GPT offers it, else the model of GPT's
  second-opinion seat (the strong one the model check moved it to). Only when missing (ON CONFLICT
  DO NOTHING): a seat the owner already set is never touched. One audit row when it is added.
- substitutes.calls.queued_at: when a call last joined its queue (NULL: when it was made). A call
  asked again (another model, the Persian instruction, a reloaded page) waits from then, so its
  queue deadline (substitutes.DEADLINE_SQL) never runs from its first, slow attempt. An index on
  the claimed calls of each lane reads how long a lane was busy after a call joined it.
- substitutes.calls.delivery_owed: an agent's call that ended without its reply yet (the
  reaper's per-pass cap on reply works, or a delivery that failed): the next passes deliver it,
  however old it is by then.
- llm.quota_status: the api may write it (INSERT, UPDATE; it only read it before). A workshop
  turn's Claude Code reports its account's rate-limit windows (the runner's rate_limit_event);
  the api records them, so the next turn picks the account that is not limited.
- work.reopen(uuid): the worker may call it too (0055 granted it to the api only): the session
  sweep (order_tick, on the worker) reopens a delivered root whose plan still has open tasks.

Additive only. The downgrade switches the seat off (seats are never deleted), drops the columns
and their indexes and takes the grants back. A downgrade then an upgrade leaves GPT's content_draft
seat switched off: the row is still there, so the re-insert does nothing (the owner switches it
on again on the players' page).

Revision ID: 0062
Revises: 0061
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

QUEUED_AT = """
ALTER TABLE substitutes.calls ADD COLUMN queued_at timestamptz;
COMMENT ON COLUMN substitutes.calls.queued_at IS
    'when the call last joined its queue (asked again); NULL: when it was made';
CREATE INDEX substitutes_calls_lane ON substitutes.calls (via, claimed_at)
    WHERE claimed_at IS NOT NULL;
ALTER TABLE substitutes.calls ADD COLUMN delivery_owed boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN substitutes.calls.delivery_owed IS
    'an agent''s call that ended before its reply was made (the next reaper passes make it)';
CREATE INDEX substitutes_calls_owed ON substitutes.calls (finished_at)
    WHERE delivery_owed AND delivered_at IS NULL;
"""

SEAT = """
WITH added AS (
    INSERT INTO substitutes.seats (company_id, player, seat, via, model, enabled, per_day, position)
    SELECT p.company_id, 'gpt', 'content_draft', 'web',
           CASE WHEN EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(p.models, '[]'::jsonb)) m
                             WHERE m ->> 'id' = 'gpt-5.5'
                               AND COALESCE((m ->> 'available')::boolean, true))
                THEN 'gpt-5.5'
                ELSE COALESCE((SELECT s.model FROM substitutes.seats s
                               WHERE s.player = 'gpt' AND s.seat = 'advisor_second_opinion'), 'gpt-5.5')
           END,
           true, 30,
           COALESCE((SELECT max(s.position) + 1 FROM substitutes.seats s WHERE s.player = 'gpt'), 0)
    FROM substitutes.players p
    WHERE p.player = 'gpt'
    ON CONFLICT (player, seat) DO NOTHING
    RETURNING company_id, seat
)
INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action, action_class,
                           target_kind, target_ref, step_up, summary)
SELECT 'system', 'system', 'system', company_id, 'substitute.seats', 'A1', 'seat', 'gpt:' || seat, false,
       'the owner''s reels order: ChatGPT writes the script draft (seat content_draft, migration 0062)'
FROM added;
"""

GRANT = """
GRANT INSERT, UPDATE ON llm.quota_status TO hq_api;
GRANT EXECUTE ON FUNCTION work.reopen(uuid) TO hq_worker;
"""

UPGRADE = QUEUED_AT + SEAT + GRANT

DOWNGRADE = """
REVOKE EXECUTE ON FUNCTION work.reopen(uuid) FROM hq_worker;
REVOKE INSERT, UPDATE ON llm.quota_status FROM hq_api;
DROP INDEX substitutes.substitutes_calls_owed;
DROP INDEX substitutes.substitutes_calls_lane;
ALTER TABLE substitutes.calls DROP COLUMN delivery_owed;
ALTER TABLE substitutes.calls DROP COLUMN queued_at;
UPDATE substitutes.seats SET enabled = false, updated_at = now()
 WHERE player = 'gpt' AND seat = 'content_draft';
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
