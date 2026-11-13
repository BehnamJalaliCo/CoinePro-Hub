"""The session's team, one person at a time (contract §57; the owner, 2026-11-13: «میخوام … مستقیم
بزنم روی کارمند باهاش توی یه فضای کوچیک حرف بزنم و ببندم و اون ادامه بده کارشو»).

- owner.session_side_lines: the side talk of a session with one person of its team (an employee
  code, `seat_code`): the owner's words to that person (`who = 'owner'`) and the person's answers
  (`who = 'seat'`: their `order.ask` / `order.progress` from a side work of the order). `work_id`:
  the work the owner's word joined or made (`made_work`: made for this word, a side work), or the
  work the person answered from (`asked`: a question, their `order.ask`). Append-only (no UPDATE or DELETE for the app roles); the lines go
  with their order when the owner erases it (ON DELETE CASCADE from owner.orders).
- owner.session_side_reads: how far the owner has read each side talk (`read_id`, the newest line
  he saw), for the seat's `unread`. One row per order and seat.

Both are the holding's rows, as the order and its report are (FORCE RLS in the InitPlan form).
Additive only; the downgrade drops the two tables.

Revision ID: 0064
Revises: 0063
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
EMP = r"'^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$'"


def _rls(table: str) -> str:
    name = table.split(".")[1]
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
"""


UPGRADE = (
    f"""
CREATE TABLE owner.session_side_lines (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    order_id    uuid NOT NULL REFERENCES owner.orders (id) ON DELETE CASCADE,
    seat_code   text NOT NULL CHECK (seat_code ~ {EMP}),
    who         text NOT NULL CHECK (who IN ('owner', 'seat')),
    who_fa      text NOT NULL CHECK (length(who_fa) BETWEEN 1 AND 200),
    text        text NOT NULL CHECK (length(text) BETWEEN 1 AND 4000),
    work_id     uuid REFERENCES work.work (id),
    work_ref    text CHECK (work_ref IS NULL OR work_ref ~ '^W-[0-9]{{6,12}}$'),
    made_work   boolean NOT NULL DEFAULT false,
    asked       boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT made_work OR (who = 'owner' AND work_id IS NOT NULL)),
    CHECK (NOT asked OR who = 'seat')
);
CREATE INDEX session_side_lines_seat ON owner.session_side_lines (order_id, seat_code, created_at);
CREATE INDEX session_side_lines_work ON owner.session_side_lines (work_id) WHERE work_id IS NOT NULL;
COMMENT ON TABLE owner.session_side_lines IS
    'contract §57: a session''s side talk with one person of its team (append-only)';
GRANT SELECT, INSERT ON owner.session_side_lines TO {APP_ROLES};

CREATE TABLE owner.session_side_reads (
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    order_id    uuid NOT NULL REFERENCES owner.orders (id) ON DELETE CASCADE,
    seat_code   text NOT NULL CHECK (seat_code ~ {EMP}),
    read_id     bigint NOT NULL DEFAULT 0 CHECK (read_id >= 0),
    read_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, seat_code)
);
COMMENT ON TABLE owner.session_side_reads IS
    'contract §57.2: the newest side line of a seat the owner has read (its unread count)';
GRANT SELECT, INSERT ON owner.session_side_reads TO {APP_ROLES};
GRANT UPDATE (read_id, read_at) ON owner.session_side_reads TO {APP_ROLES};
"""
    + _rls("owner.session_side_lines")
    + _rls("owner.session_side_reads")
)

DOWNGRADE = """
DROP TABLE owner.session_side_reads;
DROP TABLE owner.session_side_lines;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
