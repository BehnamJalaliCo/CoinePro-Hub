"""Prompt 21 part 2 (contract §29.3, §29.4, §29.5, §29.7, §29.8): the owner's rules, the secretary, long voice, Persian only, the council v2.

- §29.4 owner.dispatch_memory: the secretary's memory, read first by every
  preview: the owner's corrections of a preview (the route the secretary
  proposed and the one the owner sent) and every «نه» reason of the home's
  cards. Append-only, the holding's. owner.orders.route: the route an order
  followed (§29.4 `Route`).
- §29.3 oversight.orders: `applies_to` widened to all | overseer | roles |
  companies (the roles or company codes in `applies_codes`); `owner_text`
  keeps the owner's own words; a new version (PUT /rules/{ref}, 🔏) replaces
  the text in place and keeps the previous one in `history`; `report_at` /
  `report`: the first enforcement report, 24 hours after the seal.
- §29.5 owner.voice_sessions: one long recording sent in chunks (≤ 90 s
  each), each chunk a file of the holding; expires after 30 minutes unused.
- §29.7 substitutes.calls.lang_retried: an answer that was not Persian was
  asked once more (the second failure ends the call).
- §29.8 work.councils: `round` (1 proposals, 2 critique, 3 the captain's
  plan; NULL for a council from before v2), `roles` ({player: role}),
  `rounds` (the members of the rounds before the current one), the fact pack
  the members read (`fact_pack`, `fact_pack_ref`), the plan (`plan_md`) and
  the order «اجرا کن» made of it (`order_ref`); owner.settings.council_roles.

Every new table carries company_id under FORCE RLS; nothing is deleted.

Revision ID: 0038
Revises: 0037
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
COUNCIL_ROLES = (
    '{"claude": "captain", "gemini": "researcher", "deepseek": "numbers", "gpt": "devil"}'
)

UPGRADE = f"""
-- ---------------------------------------------------- §29.4 the secretary --
CREATE TABLE owner.dispatch_memory (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    kind        text NOT NULL CHECK (kind IN ('correction', 'no')),
    text_fa     text NOT NULL CHECK (length(text_fa) BETWEEN 1 AND 10000),
    norm        text NOT NULL DEFAULT '' CHECK (length(norm) <= 10000),
    data        jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(data) = 'object'),
    order_ref   text CHECK (order_ref ~ '^F-[0-9]+$'),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX dispatch_memory_recent ON owner.dispatch_memory (kind, created_at DESC);
CREATE TRIGGER dispatch_memory_append_only BEFORE UPDATE OR DELETE ON owner.dispatch_memory
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
ALTER TABLE owner.dispatch_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE owner.dispatch_memory FORCE ROW LEVEL SECURITY;
CREATE POLICY dispatch_memory_tenant ON owner.dispatch_memory TO {APP_ROLES}
    USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY dispatch_memory_owner_role ON owner.dispatch_memory TO hq USING (true) WITH CHECK (true);
GRANT SELECT, INSERT ON owner.dispatch_memory TO {APP_ROLES};

ALTER TABLE owner.orders ADD COLUMN route jsonb
    CHECK (route IS NULL OR jsonb_typeof(route) = 'object');

-- ------------------------------------------------------- §29.3 the rules --
ALTER TABLE oversight.orders DROP CONSTRAINT orders_applies_to_check;
ALTER TABLE oversight.orders ADD CONSTRAINT orders_applies_to_check
    CHECK (applies_to IN ('overseer', 'all', 'roles', 'companies'));
ALTER TABLE oversight.orders
    ADD COLUMN applies_codes text[] NOT NULL DEFAULT '{{}}'
        CHECK (cardinality(applies_codes) <= 50),
    ADD COLUMN owner_text  text CHECK (length(owner_text) <= 10000),
    ADD COLUMN history     jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(history) = 'array'),
    ADD COLUMN report_at   timestamptz,
    ADD COLUMN report      jsonb CHECK (report IS NULL OR jsonb_typeof(report) = 'object'),
    ADD CONSTRAINT orders_applies_codes_match
        CHECK ((applies_to IN ('roles', 'companies')) = (cardinality(applies_codes) > 0));
-- a new version (🔏) changes the text in place; the previous one stays in `history`
DROP TRIGGER orders_immutable ON oversight.orders;
CREATE TRIGGER orders_immutable BEFORE UPDATE ON oversight.orders
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
        'id', 'ref', 'company_id', 'source', 'file_id', 'owner_text', 'created_by_kind',
        'created_by_code', 'created_at');
CREATE INDEX orders_report_due ON oversight.orders (sealed_at)
    WHERE status = 'sealed' AND report_at IS NULL;
GRANT UPDATE (text_md, applies_to, applies_codes, history) ON oversight.orders TO hq_api;
GRANT UPDATE (report_at, report, updated_at) ON oversight.orders TO {APP_ROLES};

-- ------------------------------------------------------ §29.5 long voice --
CREATE TABLE owner.voice_sessions (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    purpose      text NOT NULL CHECK (purpose IN ('order', 'rule', 'message', 'note')),
    state        text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'finished', 'expired')),
    -- [{{n, file_id, sha256, duration_s, at}}], in the order of n
    chunks       jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(chunks) = 'array'),
    seconds      numeric(10, 2) NOT NULL DEFAULT 0 CHECK (seconds >= 0),
    result       jsonb CHECK (result IS NULL OR jsonb_typeof(result) = 'object'),
    created_at   timestamptz NOT NULL DEFAULT now(),
    used_at      timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    CHECK ((state = 'open') = (finished_at IS NULL))
);
CREATE INDEX voice_sessions_open ON owner.voice_sessions (used_at) WHERE state = 'open';
CREATE TRIGGER voice_sessions_immutable BEFORE UPDATE ON owner.voice_sessions
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'purpose', 'created_at');
CREATE TRIGGER voice_sessions_no_delete BEFORE DELETE ON owner.voice_sessions
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
ALTER TABLE owner.voice_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE owner.voice_sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY voice_sessions_tenant ON owner.voice_sessions TO {APP_ROLES}
    USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY voice_sessions_owner_role ON owner.voice_sessions TO hq USING (true) WITH CHECK (true);
GRANT SELECT, INSERT ON owner.voice_sessions TO {APP_ROLES};
GRANT UPDATE (state, chunks, seconds, result, used_at, finished_at) ON owner.voice_sessions
    TO {APP_ROLES};

-- ------------------------------------------------- §29.7 Persian answers --
-- (substitutes.calls is updatable as a whole by the app roles since 0027)
ALTER TABLE substitutes.calls ADD COLUMN lang_retried boolean NOT NULL DEFAULT false;

-- ------------------------------------------------------ §29.8 council v2 --
ALTER TABLE work.councils
    ADD COLUMN round          smallint CHECK (round BETWEEN 1 AND 3),
    ADD COLUMN roles          jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(roles) = 'object'),
    ADD COLUMN rounds         jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(rounds) = 'array'),
    ADD COLUMN fact_pack      jsonb CHECK (fact_pack IS NULL OR jsonb_typeof(fact_pack) = 'object'),
    ADD COLUMN fact_pack_ref  text CHECK (fact_pack_ref ~ '^FP-[0-9]+$'),
    ADD COLUMN plan_md        text CHECK (length(plan_md) <= 20000),
    ADD COLUMN order_ref      text CHECK (order_ref ~ '^F-[0-9]+$');
GRANT UPDATE (round, rounds, plan_md, order_ref) ON work.councils TO {APP_ROLES};
ALTER TABLE owner.settings ADD COLUMN council_roles jsonb NOT NULL
    DEFAULT '{COUNCIL_ROLES}'::jsonb CHECK (jsonb_typeof(council_roles) = 'object');
GRANT UPDATE (council_roles) ON owner.settings TO hq_api;
"""

DOWNGRADE = f"""
-- a rule for some roles or companies reads as one for every role again
UPDATE oversight.orders SET applies_to = 'all', applies_codes = '{{}}'
 WHERE applies_to IN ('roles', 'companies');
REVOKE UPDATE (council_roles) ON owner.settings FROM hq_api;
ALTER TABLE owner.settings DROP COLUMN council_roles;
REVOKE UPDATE (round, rounds, plan_md, order_ref) ON work.councils FROM {APP_ROLES};
ALTER TABLE work.councils DROP COLUMN round, DROP COLUMN roles, DROP COLUMN rounds,
    DROP COLUMN fact_pack, DROP COLUMN fact_pack_ref, DROP COLUMN plan_md, DROP COLUMN order_ref;
ALTER TABLE substitutes.calls DROP COLUMN lang_retried;
DROP TABLE owner.voice_sessions;
REVOKE UPDATE (report_at, report) ON oversight.orders FROM {APP_ROLES};
REVOKE UPDATE (text_md, applies_to, applies_codes, history) ON oversight.orders FROM hq_api;
DROP INDEX oversight.orders_report_due;
DROP TRIGGER orders_immutable ON oversight.orders;
CREATE TRIGGER orders_immutable BEFORE UPDATE ON oversight.orders
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
        'id', 'ref', 'company_id', 'text_md', 'source', 'file_id', 'applies_to',
        'created_by_kind', 'created_by_code', 'created_at');
ALTER TABLE oversight.orders DROP CONSTRAINT orders_applies_codes_match,
    DROP COLUMN applies_codes, DROP COLUMN owner_text, DROP COLUMN history,
    DROP COLUMN report_at, DROP COLUMN report;
ALTER TABLE oversight.orders DROP CONSTRAINT orders_applies_to_check;
ALTER TABLE oversight.orders ADD CONSTRAINT orders_applies_to_check
    CHECK (applies_to IN ('overseer', 'all'));
ALTER TABLE owner.orders DROP COLUMN route;
DROP TABLE owner.dispatch_memory;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
