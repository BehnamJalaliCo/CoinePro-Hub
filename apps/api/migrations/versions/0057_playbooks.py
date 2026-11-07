"""A session remembers, and becomes a working group the owner can give to any company (contract
§40, v1.22; the owner, 2026-11-07: «۲-۳ هزار خط چت کردیم و به یه نتیجه رسیدیم. میخوام اون نتیجه به یه
اسکیل تبدیل بشه … که بتونم اونو به شرکت‌های دیگه هم بدم»).

- owner.order_reports: `memory_md` (§40.1 the session's memory, ≤ 6 000 chars of plain Persian:
  what was decided, who does what, the helpers chosen, the open points; code appends a line per
  card done and per person joining, a small model folds the turns every 20 and at close),
  `memory_upto` (the talk turn the fold reached), `source_playbook` (§40.3 the playbook a session
  was opened from).
- owner.playbooks (§40.2): a working group as data, drafted by a session's holder from its memory,
  plan, hires, automations and cards; `draft` until the owner's seal 🔏, then a growth.groups row
  (eligibility `chosen`: only the companies the owner gives it to) with the session's company as
  its first member; `retired` stops its routines for every member. The holding's rows (RLS), never
  deleted; `source` and `ref` immutable.
- talk.cards: the kind `playbook` («کارگروه از این جلسه»: open, edit, seal; the holder's rewrite of
  the draft when the owner asks in words).
- llm.task_classes: `session_memory` (the fold, the cheapest model that does it well) and
  `playbook_draft` (the holder's draft, a strong-but-not-premium model); the router's seed holds
  the same rows.

Additive only; nothing is deleted.

Revision ID: 0057
Revises: 0056
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
PLATFORMS = "'instagram', 'youtube', 'telegram', 'site', 'any'"

UPGRADE = f"""
-- ================================================================ §40.1 the memory ==
ALTER TABLE owner.order_reports
    ADD COLUMN memory_md text CHECK (memory_md IS NULL OR length(memory_md) <= 8000),
    ADD COLUMN memory_upto int NOT NULL DEFAULT 0 CHECK (memory_upto >= 0),
    ADD COLUMN source_playbook text CHECK (source_playbook IS NULL OR source_playbook ~ '^PB-[0-9]{{4,}}$');
GRANT UPDATE (memory_md, memory_upto, source_playbook) ON owner.order_reports TO {APP_ROLES};

-- ================================================================ §40.2 playbooks ==
CREATE SEQUENCE owner.playbook_ref_seq;
GRANT USAGE ON SEQUENCE owner.playbook_ref_seq TO {APP_ROLES};

CREATE TABLE owner.playbooks (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    ref         text NOT NULL UNIQUE DEFAULT lines.pad_ref('PB-', nextval('owner.playbook_ref_seq'), 4),
    title_fa    text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
    purpose_fa  text NOT NULL DEFAULT '' CHECK (length(purpose_fa) <= 2000),
    state       text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft', 'sealed', 'retired')),
    version     int NOT NULL DEFAULT 1 CHECK (version >= 1),
    platform    text NOT NULL DEFAULT 'any' CHECK (platform IN ({PLATFORMS})),
    -- {{seats, routines, kpis, connections, rules_fa}} as the contract's Playbook shape
    definition  jsonb NOT NULL DEFAULT '{{}}'
                    CHECK (jsonb_typeof(definition) = 'object' AND length(definition::text) <= 200000),
    -- {{order, company, conversation}}: the session it was drafted from
    source      jsonb NOT NULL CHECK (jsonb_typeof(source) = 'object'),
    parent      text CHECK (parent IS NULL OR parent ~ '^PB-[0-9]{{4,}}$'),
    group_id    uuid REFERENCES growth.groups (id),
    note_fa     text CHECK (note_fa IS NULL OR length(note_fa) <= 2000),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    sealed_at   timestamptz,
    retired_at  timestamptz
);
CREATE INDEX playbooks_state ON owner.playbooks (state, created_at DESC);
CREATE INDEX playbooks_source_order ON owner.playbooks ((source->>'order'));
CREATE TRIGGER playbooks_immutable BEFORE UPDATE ON owner.playbooks
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'source', 'created_at');
CREATE TRIGGER playbooks_no_delete BEFORE DELETE ON owner.playbooks
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON owner.playbooks TO {APP_ROLES};
GRANT UPDATE (title_fa, purpose_fa, state, version, platform, definition, parent, group_id, note_fa,
              updated_at, sealed_at, retired_at) ON owner.playbooks TO {APP_ROLES};
ALTER TABLE owner.playbooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE owner.playbooks FORCE ROW LEVEL SECURITY;
CREATE POLICY playbooks_tenant ON owner.playbooks TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY playbooks_owner_role ON owner.playbooks TO hq USING (true) WITH CHECK (true);

-- the two router calls of §40 (the router's seed file holds the same rows)
INSERT INTO llm.task_classes (key, transferable, description)
VALUES ('session_memory', false,
        'A session''s memory folded from its last turns, the cheapest model that does it well (contract 40.1)'),
       ('playbook_draft', false,
        'A working group drafted by a session''s holder from its memory, plan, hires and cards (contract 40.2)')
ON CONFLICT (key) DO NOTHING;
"""

DOWNGRADE = """
DROP TABLE owner.playbooks;
DROP SEQUENCE owner.playbook_ref_seq;
ALTER TABLE owner.order_reports DROP COLUMN memory_md, DROP COLUMN memory_upto, DROP COLUMN source_playbook;
"""


def _kinds_sql(table: str, constraint: str, add: tuple[str, ...]) -> str:
    """Rewrite a `kind IN (...)` CHECK from the kinds it holds now (0029's helper)."""
    added = ", ".join(f"'{k}'" for k in add)
    return f"""
        DO $$
        DECLARE kinds text;
        BEGIN
            SELECT string_agg(quote_literal(k), ', ' ORDER BY k) INTO kinds FROM (
                SELECT DISTINCT m[1] AS k
                FROM pg_constraint c,
                     regexp_matches(pg_get_constraintdef(c.oid), '''([a-z0-9_]+)''', 'g') AS m
                WHERE c.conrelid = '{table}'::regclass AND c.conname = '{constraint}'
                UNION SELECT unnest(ARRAY[{added}]::text[])
            ) x WHERE k IS NOT NULL AND k <> '';
            ALTER TABLE {table} DROP CONSTRAINT {constraint};
            EXECUTE format('ALTER TABLE {table} ADD CONSTRAINT {constraint} '
                           'CHECK (kind IN (%s))', kinds);
        END $$;
    """


def upgrade() -> None:
    execute_script(UPGRADE)
    execute_script(_kinds_sql("talk.cards", "cards_kind_check", ("playbook",)))


# The kind `playbook` stays in the CHECK: its cards are kept (as 0052's and 0056's).
def downgrade() -> None:
    execute_script(DOWNGRADE)
