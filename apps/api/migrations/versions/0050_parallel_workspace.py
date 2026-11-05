"""Prompt 24 (contract §33.7, §33.10): a work split into parallel parts, and workspaces on the
companies' own servers.

- §33.7 work.splits: one split of a work into independent parts (2..PARALLEL_MAX, data), proposed by
  the parent's assignee (`work.split`, A1); `state` running -> merging (every part ended: ONE merge
  run of the parent's assignee was queued) -> done (the parent delivered or closed) | failed |
  cancelled. work.split_parts: each part is an ordinary child work (its own run and budget share);
  a part's deliverable does not wake the parent's assignee one by one (agents.wake_on_deliverable
  skips it): code gathers them all and queues the one merge run.
- §33.10 work.work.mode gains `on_server`. work.workspaces: one per work (never shared): the server
  whose Claude Code works in `~/hq-workspace/<work-ref>` through runner 0.3.0's `claude` job, the
  Workshop session that carries its turns (a resume keeps the folder), its state, and the close the
  runner is told (`closed` on its long-poll) so that it removes the folder 30 days later (logged
  there).

Fresh start: the splits, their parts and the workspaces go with the work. Every new table carries
company_id under FORCE RLS; nothing is deleted by the app.

Revision ID: 0050
Revises: 0049
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
TABLES = ("work.splits", "work.split_parts", "work.workspaces")
NIL = "00000000-0000-0000-0000-000000000000"


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


# The deliverable trigger of 0008, with the one change of §33.7: a part's deliverable waits for the
# merge (code queues one run of the parent's assignee when every part has ended).
WAKE_ON_DELIVERABLE = """
CREATE OR REPLACE FUNCTION agents.wake_on_deliverable() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        c record;
        p record;
    BEGIN
        SELECT parent_id, ref INTO c FROM work.work WHERE id = NEW.work_id;
        IF c.parent_id IS NULL THEN
            RETURN NULL;
        END IF;
        {skip}
        SELECT id, assignee_id, status, priority INTO p FROM work.work WHERE id = c.parent_id;
        IF p.assignee_id IS NOT NULL AND p.status IN ('queued', 'in_progress', 'waiting') THEN
            PERFORM agents.queue_run(p.assignee_id, 'work', p.id, NULL,
                                     'child_delivered:' || c.ref || ':' || NEW.ref, p.priority);
        END IF;
        RETURN NULL;
    END $$;
"""
SKIP_PART = """IF EXISTS (SELECT 1 FROM work.split_parts sp WHERE sp.work_id = NEW.work_id) THEN
            RETURN NULL;
        END IF;"""

UPGRADE = f"""
-- ============================================================ §33.10 mode ==
ALTER TABLE work.work DROP CONSTRAINT work_mode_check;
ALTER TABLE work.work ADD CONSTRAINT work_mode_check
    CHECK (mode IN ('single', 'council', 'on_server'));

-- ======================================================== §33.7 the split ==
CREATE TABLE work.splits (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    work_id          uuid NOT NULL REFERENCES work.work (id),
    state            text NOT NULL DEFAULT 'running'
                     CHECK (state IN ('running', 'merging', 'done', 'failed', 'cancelled')),
    parts            int NOT NULL CHECK (parts BETWEEN 2 AND 10),
    proposed_by      text NOT NULL CHECK (length(proposed_by) BETWEEN 1 AND 64),
    merge_reason     text CHECK (length(merge_reason) <= 200),
    merge_queued_at  timestamptz,
    ended_at         timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX splits_one_open ON work.splits (work_id) WHERE state IN ('running', 'merging');
CREATE INDEX splits_open ON work.splits (state) WHERE state IN ('running', 'merging');
CREATE TRIGGER splits_immutable BEFORE UPDATE ON work.splits
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'work_id', 'parts',
                                                      'proposed_by', 'created_at');
GRANT SELECT, INSERT ON work.splits TO {APP_ROLES};
GRANT UPDATE (state, merge_reason, merge_queued_at, ended_at, updated_at) ON work.splits
    TO {APP_ROLES};

CREATE TABLE work.split_parts (
    split_id    uuid NOT NULL REFERENCES work.splits (id),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    work_id     uuid NOT NULL UNIQUE REFERENCES work.work (id),
    n           smallint NOT NULL CHECK (n BETWEEN 1 AND 10),
    role        text NOT NULL CHECK (length(role) BETWEEN 1 AND 64),
    PRIMARY KEY (split_id, n)
);
CREATE TRIGGER split_parts_append_only BEFORE UPDATE ON work.split_parts
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON work.split_parts TO {APP_ROLES};
"""
UPGRADE += WAKE_ON_DELIVERABLE.format(skip=SKIP_PART)
UPGRADE += f"""
-- ==================================================== §33.10 workspaces ==
CREATE TABLE work.workspaces (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    work_id        uuid NOT NULL UNIQUE REFERENCES work.work (id),
    work_ref       text NOT NULL CHECK (work_ref ~ '^W-[0-9]{{6,12}}$'),
    server_id      uuid NOT NULL REFERENCES infra.servers (id),
    session_id     uuid REFERENCES workshop.sessions (id),
    state          text NOT NULL DEFAULT 'starting'
                   CHECK (state IN ('starting', 'working', 'awaiting_seal', 'idle', 'delivered',
                                    'stopped', 'failed')),
    turns          int NOT NULL DEFAULT 0 CHECK (turns >= 0),
    last_job_id    uuid REFERENCES infra.server_jobs (id),
    note_fa        text CHECK (length(note_fa) <= 1000),
    closed_at      timestamptz,
    close_sent_at  timestamptz,
    remove_after   timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX workspaces_server ON work.workspaces (server_id, created_at);
CREATE INDEX workspaces_unsent ON work.workspaces (server_id)
    WHERE closed_at IS NOT NULL AND close_sent_at IS NULL;
CREATE TRIGGER workspaces_immutable BEFORE UPDATE ON work.workspaces
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'work_id', 'work_ref',
                                                      'server_id', 'created_at');
GRANT SELECT, INSERT ON work.workspaces TO {APP_ROLES};
GRANT UPDATE (session_id, state, turns, last_job_id, note_fa, closed_at, close_sent_at,
              remove_after, updated_at) ON work.workspaces TO {APP_ROLES};
"""

# A work made `on_server` cannot stay under the old CHECK: it reads `single` again (its workspace
# rows go with the table; the server's folder is the runner's to remove).
DOWNGRADE = (
    """
DROP TABLE work.workspaces;
"""
    + WAKE_ON_DELIVERABLE.format(skip="")
    + """
DROP TABLE work.split_parts;
DROP TABLE work.splits;
UPDATE work.work SET mode = 'single' WHERE mode = 'on_server';
ALTER TABLE work.work DROP CONSTRAINT work_mode_check;
ALTER TABLE work.work ADD CONSTRAINT work_mode_check CHECK (mode IN ('single', 'council'));
"""
)


def upgrade() -> None:
    execute_script(UPGRADE + "".join(_rls(t) for t in TABLES))


def downgrade() -> None:
    execute_script(DOWNGRADE)
