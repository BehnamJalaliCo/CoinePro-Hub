"""The holding live: what the stream was last told, so it is told only of a change (contract §42,
v1.24; the owner, 2026-11-08: «نقشه نشون بده کدوم شرکت به کدوم وصل شد قطع شد … همه جای آپ باشه»).

- core.employee_live: each employee's §29.14 state as last derived (state, since when, the work it
  is on, why it is stuck) and what `employee.state` last said (`sent_state`, `sent_at`, `pending`:
  a change within 2 s of the last one waits for the window). Derived data of the employee's company
  (RLS), wiped by a fresh start, never deleted otherwise.
- infra.network_links: `since` (when the link's `ok` last changed) and what `network.link` last
  said of it (`emitted_at`, `emitted_ok`, `emitted_slow`: a change at most once a minute).
- infra.servers: `state_since` (when its state began) and `state_reason` (the reason the last
  `server.state` gave: an offline server's reason is told again only when a netcheck changes it).

Additive only; nothing is deleted.

Revision ID: 0059
Revises: 0057 (0058 is the session wave's; at the merge this revision sits on 0058)
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0059"
down_revision = "0057"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
STATES = "'idle', 'thinking', 'working', 'waiting', 'stuck', 'done'"
REASONS = "'no_poll', 'runner_stopped', 'server_unreachable', 'revoked', 'fallback_public', 'slow'"

UPGRADE = f"""
-- ======================================================= §42.2 employee.state ==
CREATE TABLE core.employee_live (
    employee_id  uuid PRIMARY KEY REFERENCES core.employees (id),
    company_id   uuid NOT NULL REFERENCES core.companies (id),
    state        text NOT NULL CHECK (state IN ({STATES})),
    since        timestamptz NOT NULL DEFAULT now(),
    work_ref     text CHECK (length(work_ref) <= 40),
    root_ref     text CHECK (length(root_ref) <= 40),
    stuck_fa     text CHECK (length(stuck_fa) <= 300),
    sent_state   text CHECK (sent_state IN ({STATES})),
    sent_at      timestamptz,
    pending      boolean NOT NULL DEFAULT false,
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX employee_live_pending ON core.employee_live (sent_at) WHERE pending;
CREATE TRIGGER employee_live_immutable BEFORE UPDATE ON core.employee_live
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('employee_id', 'company_id');
CREATE TRIGGER employee_live_no_delete BEFORE DELETE ON core.employee_live
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON core.employee_live TO {APP_ROLES};
GRANT UPDATE (state, since, work_ref, root_ref, stuck_fa, sent_state, sent_at, pending, updated_at)
    ON core.employee_live TO {APP_ROLES};
ALTER TABLE core.employee_live ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.employee_live FORCE ROW LEVEL SECURITY;
CREATE POLICY employee_live_tenant ON core.employee_live TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY employee_live_owner_role ON core.employee_live TO hq USING (true) WITH CHECK (true);

-- ======================================================= §42.2 network.link ==
ALTER TABLE infra.network_links
    ADD COLUMN since         timestamptz,
    ADD COLUMN emitted_at    timestamptz,
    ADD COLUMN emitted_ok    boolean,
    ADD COLUMN emitted_slow  boolean;
UPDATE infra.network_links
    SET since = at;
ALTER TABLE infra.network_links ALTER COLUMN since SET DEFAULT now(), ALTER COLUMN since SET NOT NULL;
GRANT UPDATE (since, emitted_at, emitted_ok, emitted_slow) ON infra.network_links TO {APP_ROLES};

-- ======================================================= §42.2 server.state ==
ALTER TABLE infra.servers
    ADD COLUMN state_since   timestamptz,
    ADD COLUMN state_reason  text CHECK (state_reason IN ({REASONS}));
UPDATE infra.servers
    SET state_since = CASE WHEN state = 'offline' THEN last_seen_at ELSE updated_at END
    WHERE state IS NOT NULL;
GRANT UPDATE (state_since, state_reason) ON infra.servers TO {APP_ROLES};
"""  # noqa: S608 - composed from module constants only

DOWNGRADE = """
ALTER TABLE infra.servers DROP COLUMN state_since, DROP COLUMN state_reason;
ALTER TABLE infra.network_links DROP COLUMN since, DROP COLUMN emitted_at, DROP COLUMN emitted_ok,
    DROP COLUMN emitted_slow;
DROP TABLE core.employee_live;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
