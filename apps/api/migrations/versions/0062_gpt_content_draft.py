"""ChatGPT writes the script, as the owner ordered (the stall of 2026-11-10; the owner's reels
order, docs/ORDER_PROCHART_REELS_2026-11-10.md: topic, script, directing and cover «با ChatGPT»).

- substitutes.seats: GPT's `content_draft` seat (via web, the strong model, 30 a day, on). GPT had
  none (only Gemini sat there), so a holder that named ChatGPT for a script draft was refused.
  The seed adds a player's seats only when it seeds the player itself, so an existing hub gets the
  row here; a fresh database gets it from the seed (no players yet: nothing is inserted here).
  Gemini keeps its own seat. The model is `gpt-5.5` while GPT offers it, else the model of GPT's
  second-opinion seat (the strong one the model check moved it to). Only when missing (ON CONFLICT
  DO NOTHING): a seat the owner already set is never touched. One audit row when it is added.
- llm.quota_status: the api may write it (INSERT, UPDATE; it only read it before). A workshop
  turn's Claude Code reports its account's rate-limit windows (the runner's rate_limit_event);
  the api records them, so the next turn picks the account that is not limited.

Additive only; the downgrade switches the seat off (seats are never deleted) and takes the
grant back.

Revision ID: 0062
Revises: 0061
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

UPGRADE = """
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

GRANT INSERT, UPDATE ON llm.quota_status TO hq_api;
"""

DOWNGRADE = """
REVOKE INSERT, UPDATE ON llm.quota_status FROM hq_api;
UPDATE substitutes.seats SET enabled = false, updated_at = now()
 WHERE player = 'gpt' AND seat = 'content_draft';
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
