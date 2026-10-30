"""Prompt 18 (contract §27 ⟨1.9⟩): the player of an order and the council of
models.

- work.work: `player` (auto | claude | gpt | gemini | deepseek) and `mode`
  (single | council), inherited by children; `media` (image | video) for a
  council that makes pictures or video; `player_wait_since`,
  `player_tried_at` and `player_fallback_at`: a named player that is not
  available waits up to 30 minutes, then the work falls back to auto.
- work.councils: one per council order: its members (Claude and every
  substitute player that was ready), each with its call, creative or
  deliverable, and the synthesis (a child work Claude writes).
- substitutes.creatives: `picked_at` (the owner's pick among a council's
  versions) and `source_creative_id` (a video animated from a picked image).

Every new table carries company_id under FORCE RLS; nothing is deleted.

Revision ID: 0033
Revises: 0032
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"

UPGRADE = f"""
ALTER TABLE work.work
    ADD COLUMN player              text NOT NULL DEFAULT 'auto'
                                   CHECK (player IN ('auto', 'claude', 'gpt', 'gemini', 'deepseek')),
    ADD COLUMN mode                text NOT NULL DEFAULT 'single' CHECK (mode IN ('single', 'council')),
    ADD COLUMN media               text CHECK (media IN ('image', 'video')),
    ADD COLUMN player_wait_since   timestamptz,
    ADD COLUMN player_tried_at     timestamptz,
    ADD COLUMN player_fallback_at  timestamptz;
GRANT UPDATE (player, mode, player_wait_since, player_tried_at, player_fallback_at)
    ON work.work TO {APP_ROLES};
CREATE INDEX work_player_waiting ON work.work (player_wait_since)
    WHERE player_wait_since IS NOT NULL AND player_fallback_at IS NULL;

CREATE TABLE work.councils (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         uuid NOT NULL REFERENCES core.companies (id),
    work_id            uuid NOT NULL UNIQUE REFERENCES work.work (id),
    state              text NOT NULL DEFAULT 'running'
                       CHECK (state IN ('running', 'synthesising', 'done', 'failed')),
    members            jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(members) = 'array'),
    synthesis_work_id  uuid REFERENCES work.work (id),
    synthesis_ref      text CHECK (synthesis_ref ~ '^O-[0-9]+$'),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX councils_open ON work.councils (state) WHERE state IN ('running', 'synthesising');
CREATE TRIGGER councils_immutable BEFORE UPDATE ON work.councils
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'work_id', 'created_at');
ALTER TABLE work.councils ENABLE ROW LEVEL SECURITY;
ALTER TABLE work.councils FORCE ROW LEVEL SECURITY;
CREATE POLICY councils_tenant ON work.councils TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY councils_owner_role ON work.councils TO hq USING (true) WITH CHECK (true);
CREATE TRIGGER councils_no_delete BEFORE DELETE ON work.councils
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON work.councils TO {APP_ROLES};
GRANT UPDATE (state, members, synthesis_work_id, synthesis_ref, updated_at) ON work.councils
    TO {APP_ROLES};

ALTER TABLE substitutes.creatives
    ADD COLUMN picked_at           timestamptz,
    ADD COLUMN source_creative_id  uuid REFERENCES substitutes.creatives (id);
GRANT UPDATE (picked_at) ON substitutes.creatives TO {APP_ROLES};
"""

DOWNGRADE = f"""
REVOKE UPDATE (picked_at) ON substitutes.creatives FROM {APP_ROLES};
ALTER TABLE substitutes.creatives DROP COLUMN source_creative_id, DROP COLUMN picked_at;
DROP TABLE work.councils;
DROP INDEX work.work_player_waiting;
REVOKE UPDATE (player, mode, player_wait_since, player_tried_at, player_fallback_at)
    ON work.work FROM {APP_ROLES};
ALTER TABLE work.work DROP COLUMN player, DROP COLUMN mode, DROP COLUMN media,
    DROP COLUMN player_wait_since, DROP COLUMN player_tried_at, DROP COLUMN player_fallback_at;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
