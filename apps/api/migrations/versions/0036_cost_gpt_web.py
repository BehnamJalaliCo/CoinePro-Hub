"""Prompt 20.1 (contract §28.6 ⟨1.10.2⟩): what the holding spends, and GPT's
text on the web.

- core.companies.daily_token_cap: a company's own agent runs per UTC day
  (input + output + cache tokens); NULL = AGENT_COMPANY_DAILY_TOKEN_CAP. One
  company never eats every other's day again.
- GPT's text goes through ChatGPT's web chat (the owner, 2026-11-02): its
  text capability is `web`; its text seats (advisor_second_opinion,
  overseer_cross_check, assistant_errand) run `via: "web"`; Codex (cli) keeps
  only code review, off until the owner turns it on. As in 0029_1, only seats
  the owner has not changed by hand move (no audit row `substitute.seats` on
  target `gpt`); one audit row per moved seat. A GPT whose web profile is
  already signed in is ready at once (its readiness is the web's now).

Revision ID: 0036
Revises: 0035
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

UPGRADE = """
ALTER TABLE core.companies ADD COLUMN daily_token_cap bigint
    CHECK (daily_token_cap IS NULL OR daily_token_cap >= 0);
COMMENT ON COLUMN core.companies.daily_token_cap IS
    'prompt 20.1: the company''s own agent tokens per UTC day; NULL = AGENT_COMPANY_DAILY_TOKEN_CAP';

WITH moved AS (
    UPDATE substitutes.seats
       SET via = CASE WHEN seat = 'code_review' THEN via ELSE 'web' END,
           enabled = CASE WHEN seat = 'code_review' THEN false ELSE enabled END,
           updated_at = now()
     WHERE player = 'gpt'
       AND ((seat IN ('advisor_second_opinion', 'overseer_cross_check', 'assistant_errand') AND via = 'cli')
            OR (seat = 'code_review' AND enabled))
       AND NOT EXISTS (SELECT 1 FROM audit.entries
                       WHERE action = 'substitute.seats' AND target_ref = 'gpt')
    RETURNING company_id, seat
)
INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action, action_class,
                           target_kind, target_ref, step_up, summary)
SELECT 'system', 'system', 'system', company_id, 'substitute.seats', 'A1', 'seat', 'gpt:' || seat, false,
       CASE WHEN seat = 'code_review'
            THEN 'prompt 20.1: Codex only for code review, off until the owner asks (migration 0036)'
            ELSE 'prompt 20.1: the GPT text seat runs via web, not Codex (migration 0036)' END
FROM moved;

UPDATE substitutes.players
   SET capabilities = jsonb_set(capabilities, '{text}', '"web"'),
       status = CASE WHEN web_state = 'signed_in' AND status = 'off' THEN 'ready' ELSE status END,
       status_reason = CASE WHEN web_state = 'signed_in' AND status = 'off' THEN NULL ELSE status_reason END,
       updated_at = now()
 WHERE player = 'gpt' AND capabilities ->> 'text' = 'cli';
"""

DOWNGRADE = """
UPDATE substitutes.players
   SET capabilities = jsonb_set(capabilities, '{text}', '"cli"'), updated_at = now()
 WHERE player = 'gpt' AND capabilities ->> 'text' = 'web';
UPDATE substitutes.seats SET via = 'cli', updated_at = now()
 WHERE player = 'gpt' AND via = 'web'
   AND seat IN ('advisor_second_opinion', 'overseer_cross_check', 'assistant_errand');
ALTER TABLE core.companies DROP COLUMN daily_token_cap;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
