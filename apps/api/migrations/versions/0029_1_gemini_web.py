"""Prompt 14.1 §2.2, contract ⟨1.7.2⟩: Google ended the Gemini CLI's sign-in
for individuals, so every Gemini seat runs `via: "web"` (the signed-in browser
profile) and the player's text capability is the web.

Only seats the owner has not changed by hand move: the owner's seat edits go
through `PUT /substitutes/players/gemini/seats`, which writes an audit row
`substitute.seats` with target `gemini`. While no such row exists the seats are
still the seed's (all 0027 seeded them in one statement), so they move; once
the owner has edited Gemini's seats, nothing is touched. One audit row per
moved seat.

Revision ID: 0029_1
Revises: 0029
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0029_1"
down_revision = "0029"
branch_labels = None
depends_on = None

REASON = "Gemini CLI for individuals is discontinued by Google; Gemini runs through make gemini-web-login"

UPGRADE = f"""
WITH moved AS (
    UPDATE substitutes.seats SET via = 'web', updated_at = now()
    WHERE player = 'gemini' AND via = 'cli'
      AND NOT EXISTS (SELECT 1 FROM audit.entries
                      WHERE action = 'substitute.seats' AND target_ref = 'gemini')
    RETURNING company_id, seat
)
INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action, action_class,
                           target_kind, target_ref, step_up, summary)
SELECT 'system', 'system', 'system', company_id, 'substitute.seats', 'A1', 'seat',
       'gemini:' || seat, false, 'contract 1.7.2: the Gemini seat runs via web (migration 0029_1)'
FROM moved;

UPDATE substitutes.players
   SET capabilities = jsonb_set(capabilities, '{{text}}', '"web"'),
       status_reason = CASE WHEN status = 'off' THEN '{REASON}' ELSE status_reason END,
       updated_at = now()
 WHERE player = 'gemini' AND capabilities ->> 'text' = 'cli';
"""

DOWNGRADE = """
UPDATE substitutes.players
   SET capabilities = jsonb_set(capabilities, '{text}', '"cli"'), updated_at = now()
 WHERE player = 'gemini' AND capabilities ->> 'text' = 'web';
UPDATE substitutes.seats SET via = 'cli', updated_at = now()
 WHERE player = 'gemini' AND via = 'web' AND seat IN ('code_review', 'content_draft', 'long_read');
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
