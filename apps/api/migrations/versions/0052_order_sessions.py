"""Every order a session (contract §35, the owner, 2026-11-06: «هر فرمان من باید یک سشن خودش رو
داشته باشه تا بتونیم به نتیجه برسونیم و کار رو که اوکی کردیم و همه چی تموم شد سشن بایگانی بشه»).

- owner.order_reports: `closed_at` (the owner's close, the only end of an order now), `hidden_at`
  (a hidden session leaves every list; nothing is deleted), `badge` (your_turn | ready | stuck |
  moving | closed, by code; a change streams `session.updated`). `turn` keeps several asks
  (jsonb: {question_fa, at, by, who_fa, asks: [...], reminded_at}). owner.orders.pace may be
  changed by the owner at any time (POST /orders/{ref}/pace: «با من / خودکار»).
- owner.session_tasks: the session's plan («فهرست کارها»): the holder's steps (`order.ack`) and
  the owner's own lines, each todo | doing | done | dropped, linked to a real work when one is.
  The holding's rows, FORCE RLS, never deleted (dropped instead).
- talk: a persona key may be a player (`player:gpt|gemini|deepseek`, the substitutes of §21.13,
  answering through their seats); a card may be `delegate`, `budget`, `group` or `line`; a turn's
  directive may be `sum_up` (the holder sums up after «نظر همه»); a conversation knows its
  `holder` (persona key) and `holder_code` (the one employee of the order's holder, so the
  persona resolves to the holder and never to another employee of the same charter), and is
  read-only once `closed_at` is set (the session archived).
- work.wake_assignee honours the locks: NULL (no run) while the work's company is locked
  (control.lock_state) or while the work's order is stopped for talking without output.

Additive only; nothing is deleted.

Revision ID: 0052
Revises: 0051
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
PERSONA_BEFORE = r"'^([a-z][a-z_]{1,30}|[a-z][a-z0-9_]{1,40}@[A-Z][A-Z0-9]{1,9})$'"
PERSONA = r"'^([a-z][a-z_]{1,30}|[a-z][a-z0-9_]{1,40}@[A-Z][A-Z0-9]{1,9}|player:(gpt|gemini|deepseek))$'"
CARD_KINDS_BEFORE = "'order', 'ask', 'hire', 'decision', 'planner', 'rule', 'automation', 'minutes', 'invite'"
CARD_KINDS = CARD_KINDS_BEFORE + ", 'delegate', 'budget', 'group', 'line'"
BADGES = "'your_turn', 'ready', 'stuck', 'moving', 'closed'"


def _rls(table: str) -> str:
    name = table.split(".")[1]
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
CREATE TRIGGER {name}_no_delete BEFORE DELETE ON {table}
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
"""


WAKE = """
CREATE OR REPLACE FUNCTION work.wake_assignee(p_work uuid, p_reason text) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        w record;
    BEGIN
        SELECT id, ref, company_id, assignee_id, status INTO w FROM work.work WHERE id = p_work;
        IF NOT FOUND OR w.assignee_id IS NULL
           OR w.status NOT IN ('queued', 'in_progress', 'waiting') THEN
            RETURN NULL;
        END IF;
        {locks}
        RETURN agents.queue_run(w.assignee_id, 'work', w.id, NULL, left(COALESCE(p_reason, ''), 200), 'P1');
    END $$;
"""
LOCKS = """IF control.lock_state(w.company_id) IS NOT NULL THEN
            RETURN NULL;
        END IF;
        IF EXISTS (SELECT 1 FROM owner.order_reports r
                   WHERE r.talk_stopped_at IS NOT NULL AND r.ended_at IS NULL
                     AND w.ref = ANY(r.work_refs)) THEN
            RETURN NULL;
        END IF;"""

UPGRADE = (
    f"""
-- ======================================================= §35.1 the session ==
ALTER TABLE owner.order_reports
    ADD COLUMN closed_at timestamptz,
    ADD COLUMN hidden_at timestamptz,
    ADD COLUMN badge text NOT NULL DEFAULT 'moving' CHECK (badge IN ({BADGES}));
CREATE INDEX order_reports_sessions ON owner.order_reports (closed_at, updated_at DESC)
    WHERE hidden_at IS NULL;
GRANT UPDATE (closed_at, hidden_at, badge) ON owner.order_reports TO {APP_ROLES};
-- the owner switches «با من / خودکار» at any time (POST /orders/{{ref}}/pace)
GRANT UPDATE (pace) ON owner.orders TO {APP_ROLES};

-- the session's plan: the holder's steps and the owner's own lines
CREATE TABLE owner.session_tasks (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    order_id    uuid NOT NULL REFERENCES owner.orders (id),
    ref         text NOT NULL CHECK (ref ~ '^F-[0-9]{{4,}}$'),
    n           int NOT NULL CHECK (n >= 1),
    title_fa    text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
    state       text NOT NULL DEFAULT 'todo' CHECK (state IN ('todo', 'doing', 'done', 'dropped')),
    by          text NOT NULL CHECK (by IN ('owner', 'agent')),
    who_fa      text CHECK (length(who_fa) <= 200),
    who_code    text CHECK (length(who_code) <= 64),
    work_ref    text CHECK (work_ref IS NULL OR work_ref ~ '^W-[0-9]{{6,12}}$'),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX session_tasks_order ON owner.session_tasks (order_id, n);
CREATE TRIGGER session_tasks_immutable BEFORE UPDATE ON owner.session_tasks
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'order_id', 'ref', 'by',
                                                      'created_at');
GRANT SELECT, INSERT ON owner.session_tasks TO {APP_ROLES};
GRANT UPDATE (n, title_fa, state, who_fa, who_code, work_ref, updated_at) ON owner.session_tasks
    TO {APP_ROLES};

-- ============================================================ §35.4 the talk ==
ALTER TABLE talk.personas DROP CONSTRAINT personas_key_check;
ALTER TABLE talk.personas ADD CONSTRAINT personas_key_check CHECK (key ~ {PERSONA});
ALTER TABLE talk.conversations DROP CONSTRAINT conversations_persona_check;
ALTER TABLE talk.conversations ADD CONSTRAINT conversations_persona_check CHECK (persona ~ {PERSONA});
ALTER TABLE talk.turns DROP CONSTRAINT turns_persona_check;
ALTER TABLE talk.turns ADD CONSTRAINT turns_persona_check CHECK (persona ~ {PERSONA});
ALTER TABLE talk.turns DROP CONSTRAINT turns_directive_check;
ALTER TABLE talk.turns ADD CONSTRAINT turns_directive_check CHECK (directive IN ('minutes', 'sum_up'));
ALTER TABLE talk.cards DROP CONSTRAINT cards_kind_check;
ALTER TABLE talk.cards ADD CONSTRAINT cards_kind_check CHECK (kind IN ({CARD_KINDS}));
ALTER TABLE talk.conversations
    ADD COLUMN closed_at timestamptz,
    ADD COLUMN holder text CHECK (holder IS NULL OR holder ~ {PERSONA}),
    ADD COLUMN holder_code text CHECK (holder_code IS NULL OR length(holder_code) <= 64);
GRANT UPDATE (closed_at, holder, holder_code) ON talk.conversations TO {APP_ROLES};
"""
    + WAKE.format(locks=LOCKS)
    + _rls("owner.session_tasks")
)

DOWNGRADE = (
    WAKE.format(locks="")
    + f"""
ALTER TABLE talk.conversations DROP COLUMN closed_at, DROP COLUMN holder, DROP COLUMN holder_code;
-- rows of the new kinds stay (nothing is deleted): the old CHECKs come back NOT VALID
ALTER TABLE talk.cards DROP CONSTRAINT cards_kind_check;
ALTER TABLE talk.cards ADD CONSTRAINT cards_kind_check CHECK (kind IN ({CARD_KINDS_BEFORE})) NOT VALID;
ALTER TABLE talk.turns DROP CONSTRAINT turns_directive_check;
ALTER TABLE talk.turns ADD CONSTRAINT turns_directive_check CHECK (directive IN ('minutes')) NOT VALID;
ALTER TABLE talk.turns DROP CONSTRAINT turns_persona_check;
ALTER TABLE talk.turns ADD CONSTRAINT turns_persona_check CHECK (persona ~ {PERSONA_BEFORE}) NOT VALID;
ALTER TABLE talk.conversations DROP CONSTRAINT conversations_persona_check;
ALTER TABLE talk.conversations ADD CONSTRAINT conversations_persona_check
    CHECK (persona ~ {PERSONA_BEFORE}) NOT VALID;
ALTER TABLE talk.personas DROP CONSTRAINT personas_key_check;
ALTER TABLE talk.personas ADD CONSTRAINT personas_key_check CHECK (key ~ {PERSONA_BEFORE}) NOT VALID;
DROP TABLE owner.session_tasks;
REVOKE UPDATE (pace) ON owner.orders FROM {APP_ROLES};
DROP INDEX IF EXISTS owner.order_reports_sessions;
ALTER TABLE owner.order_reports DROP COLUMN closed_at, DROP COLUMN hidden_at, DROP COLUMN badge;
"""
)


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
