"""Prompt 06 §4-§5: the Code Workshop's control plane and the owner's voice orders.

Code Workshop (contract §17.3; OPERATING_MODEL §1.1 Lead Developer, §1.5):
  - workshop.workspaces: one repository each (data, seeded from
    seed/workspaces.yaml and edited by the owner); `policy` says what a
    session may do there (branch prefix hq/, PRs, merge and deploy stay with
    the owner's seal).
  - workshop.grants (G-0001): the owner's permission for one workspace: the
    actions, the driver (an agent, or none = the owner drives), a USD cap
    per session, an expiry; created by the owner (🔏) or by the seal of a
    `code_session` decision an agent proposed. Revoked, never deleted.
  - workshop.sessions (S-0001): one Claude Code session under a grant, on a
    runtime (managed | self_hosted), with its state, branch, PR, usage,
    `area` (the part of the repository it writes: a path prefix, "" = all;
    one writing session per area at a time, OPERATING_MODEL §1.5) and `held`
    (why it waits: work_lock, company_locked, budget).
  - workshop.events: append-only, numbered per session (seq), summaries and
    metadata only (contract rule 7); the full transcript goes to file storage.
  - workshop.approvals (AP-0001): what a session asks before it pushes, opens
    a PR or runs a command outside the allow-list; the owner answers.
Voice orders (contract §17.4): owner.orders (F-0001) with their routes.
The decision kind `code_session` (A1) joins cartable.decisions.

Revision ID: 0014
Revises: 0012 (re-chained after 0013 when merged)
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0014"
down_revision = "0012"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
KINDS = (
    "'hire', 'dismissal', 'recurring_approval', 'deploy', 'a3_action', 'proposal', "
    "'budget_change', 'evaluation'"
)


def _rls(tables: list[str]) -> str:
    return "\n".join(
        f"""
        ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {t} FORCE ROW LEVEL SECURITY;
        CREATE POLICY {t.split('.')[1]}_tenant ON {t} TO {APP_ROLES}
            USING (company_id = ANY ((SELECT core.allowed_company_ids())::uuid[]))
            WITH CHECK (company_id = ANY ((SELECT core.allowed_company_ids())::uuid[]));
        CREATE POLICY {t.split('.')[1]}_owner_role ON {t} TO hq USING (true) WITH CHECK (true);
        """
        for t in tables
    )


def upgrade() -> None:
    execute_script(
        rf"""
        CREATE SCHEMA workshop;
        GRANT USAGE ON SCHEMA workshop TO {APP_ROLES};

        CREATE TABLE workshop.workspaces (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      uuid NOT NULL REFERENCES core.companies (id),
            code            text NOT NULL UNIQUE CHECK (code ~ '^[A-Z][A-Z0-9]{{1,9}}-[A-Z0-9]{{2,20}}$'),
            repo            text NOT NULL CHECK (repo ~ '^[A-Za-z0-9_.-]{{1,100}}/[A-Za-z0-9_.-]{{1,100}}$'),
            default_branch  text NOT NULL CHECK (length(default_branch) BETWEEN 1 AND 200),
            title_fa        text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
            policy          jsonb NOT NULL CHECK (jsonb_typeof(policy) = 'object'),
            status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused')),
            version         int NOT NULL DEFAULT 1,
            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (company_id, id)
        );
        CREATE TRIGGER workspaces_immutable BEFORE UPDATE ON workshop.workspaces
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'code', 'created_at');
        CREATE TRIGGER workspaces_version BEFORE UPDATE ON workshop.workspaces
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();
        CREATE TRIGGER workspaces_no_delete BEFORE DELETE ON workshop.workspaces
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        CREATE SEQUENCE workshop.grant_ref_seq;
        CREATE SEQUENCE workshop.session_ref_seq;
        CREATE SEQUENCE workshop.approval_ref_seq;
        GRANT USAGE ON SEQUENCE workshop.grant_ref_seq, workshop.session_ref_seq,
            workshop.approval_ref_seq TO {APP_ROLES};

        CREATE TABLE workshop.grants (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref              text NOT NULL UNIQUE
                                  DEFAULT 'G-' || lpad(nextval('workshop.grant_ref_seq')::text, 4, '0'),
            company_id       uuid NOT NULL REFERENCES core.companies (id),
            workspace_id     uuid NOT NULL REFERENCES workshop.workspaces (id),
            actions          text[] NOT NULL CHECK (cardinality(actions) BETWEEN 1 AND 5
                                  AND actions <@ ARRAY['read', 'edit', 'run', 'push_branch', 'open_pr']),
            driver_kind      text CHECK (driver_kind IN ('owner', 'agent')),
            driver_code      text CHECK (length(driver_code) BETWEEN 1 AND 64),
            budget_usd       numeric(12, 4) NOT NULL CHECK (budget_usd > 0 AND budget_usd <= 10000),
            expires_at       timestamptz NOT NULL,
            granted_by_kind  text NOT NULL CHECK (granted_by_kind IN ('owner', 'service')),
            granted_by_code  text NOT NULL,
            decision_id      uuid UNIQUE REFERENCES cartable.decisions (id),
            revoked_at       timestamptz,
            revoked_by_kind  text CHECK (revoked_by_kind IN ('owner', 'service')),
            revoked_by_code  text,
            created_at       timestamptz NOT NULL DEFAULT now(),
            CHECK ((driver_kind IS NULL) = (driver_code IS NULL)),
            CHECK (expires_at > created_at)
        );
        CREATE INDEX grants_workspace ON workshop.grants (workspace_id, created_at DESC);
        CREATE TRIGGER grants_immutable BEFORE UPDATE ON workshop.grants
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'ref', 'company_id', 'workspace_id', 'actions', 'driver_kind', 'driver_code',
                'budget_usd', 'expires_at', 'granted_by_kind', 'granted_by_code', 'decision_id',
                'created_at');
        CREATE TRIGGER grants_no_delete BEFORE DELETE ON workshop.grants
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        CREATE TABLE workshop.sessions (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref                 text NOT NULL UNIQUE
                                     DEFAULT 'S-' || lpad(nextval('workshop.session_ref_seq')::text, 4, '0'),
            company_id          uuid NOT NULL REFERENCES core.companies (id),
            workspace_id        uuid NOT NULL REFERENCES workshop.workspaces (id),
            grant_id            uuid NOT NULL REFERENCES workshop.grants (id),
            title               text NOT NULL CHECK (length(title) BETWEEN 1 AND 300),
            brief               text NOT NULL DEFAULT '' CHECK (length(brief) <= 20000),
            area                text NOT NULL DEFAULT '' CHECK (length(area) <= 300),
            writes              boolean NOT NULL,
            opened_by_kind      text NOT NULL CHECK (opened_by_kind IN ('owner', 'agent', 'service')),
            opened_by_code      text NOT NULL,
            driver_kind         text NOT NULL CHECK (driver_kind IN ('owner', 'agent')),
            driver_code         text NOT NULL,
            runtime             text NOT NULL CHECK (runtime IN ('managed', 'self_hosted', 'fake')),
            model               text NOT NULL CHECK (length(model) <= 100),
            effort              text NOT NULL CHECK (effort IN ('low', 'medium', 'high', 'xhigh', 'max')),
            state               text NOT NULL DEFAULT 'starting'
                                     CHECK (state IN ('starting', 'working', 'waiting_approval', 'idle',
                                                      'done', 'failed', 'stopped')),
            held                text CHECK (held IN ('work_lock', 'company_locked', 'budget')),
            branch              text CHECK (length(branch) <= 200),
            pr_url              text CHECK (pr_url ~ '^https://'),
            usd                 numeric(12, 4) NOT NULL DEFAULT 0 CHECK (usd >= 0),
            input_tokens        bigint NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
            output_tokens       bigint NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
            external_id         text CHECK (length(external_id) <= 200),
            external_cursor     text CHECK (length(external_cursor) <= 200),
            transcript_file_id  uuid REFERENCES files.files (id),
            error_code          text CHECK (error_code ~ '^[a-z][a-z0-9_]{{1,40}}$'),
            last_seq            int NOT NULL DEFAULT 0,
            version             int NOT NULL DEFAULT 1,
            created_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now(),
            finished_at         timestamptz,
            CHECK ((state IN ('done', 'failed', 'stopped')) = (finished_at IS NOT NULL))
        );
        CREATE INDEX sessions_workspace ON workshop.sessions (workspace_id, created_at DESC);
        CREATE INDEX sessions_active ON workshop.sessions (workspace_id)
            WHERE state NOT IN ('done', 'failed', 'stopped');
        CREATE FUNCTION workshop.sessions_guard() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF OLD.state IN ('done', 'failed', 'stopped') AND NEW.state <> OLD.state THEN
                    RAISE EXCEPTION 'session % is finished (%)', OLD.ref, OLD.state USING ERRCODE = 'HQV01';
                END IF;
                IF NEW.usd < OLD.usd OR NEW.input_tokens < OLD.input_tokens
                   OR NEW.output_tokens < OLD.output_tokens OR NEW.last_seq < OLD.last_seq THEN
                    RAISE EXCEPTION 'session %: counters never go down', OLD.ref USING ERRCODE = 'HQV01';
                END IF;
                NEW.updated_at := now();
                RETURN NEW;
            END $$;
        CREATE TRIGGER sessions_guard BEFORE UPDATE ON workshop.sessions
            FOR EACH ROW EXECUTE FUNCTION workshop.sessions_guard();
        CREATE TRIGGER sessions_immutable BEFORE UPDATE ON workshop.sessions
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'ref', 'company_id', 'workspace_id', 'grant_id', 'title', 'brief', 'area', 'writes',
                'opened_by_kind', 'opened_by_code', 'driver_kind', 'driver_code', 'runtime', 'created_at');
        CREATE TRIGGER sessions_version BEFORE UPDATE ON workshop.sessions
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();
        CREATE TRIGGER sessions_no_delete BEFORE DELETE ON workshop.sessions
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        CREATE TABLE workshop.events (
            id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            session_id  uuid NOT NULL REFERENCES workshop.sessions (id),
            company_id  uuid NOT NULL REFERENCES core.companies (id),
            seq         int NOT NULL CHECK (seq >= 1),
            at          timestamptz NOT NULL DEFAULT now(),
            type        text NOT NULL CHECK (type IN ('message', 'progress', 'command', 'file_change',
                                                     'approval_request', 'approval_result', 'state', 'error')),
            actor_kind  text NOT NULL CHECK (actor_kind IN ('owner', 'agent', 'service', 'system')),
            actor_code  text NOT NULL CHECK (length(actor_code) BETWEEN 1 AND 64),
            summary_fa  text NOT NULL DEFAULT '' CHECK (length(summary_fa) <= 2000),
            data        jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(data) = 'object'),
            UNIQUE (session_id, seq)
        );
        CREATE TRIGGER events_append_only BEFORE UPDATE OR DELETE ON workshop.events
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER events_no_truncate BEFORE TRUNCATE ON workshop.events
            FOR EACH STATEMENT EXECUTE FUNCTION core.reject_change();

        CREATE TABLE workshop.approvals (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref              text NOT NULL UNIQUE
                                  DEFAULT 'AP-' || lpad(nextval('workshop.approval_ref_seq')::text, 4, '0'),
            session_id       uuid NOT NULL REFERENCES workshop.sessions (id),
            company_id       uuid NOT NULL REFERENCES core.companies (id),
            action           text NOT NULL CHECK (action IN ('push_branch', 'open_pr', 'command', 'budget')),
            detail           text NOT NULL DEFAULT '' CHECK (length(detail) <= 2000),
            external_id      text CHECK (length(external_id) <= 200),
            state            text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'allowed', 'denied')),
            decided_at       timestamptz,
            decided_by_kind  text CHECK (decided_by_kind IN ('owner', 'service')),
            decided_by_code  text,
            note             text CHECK (length(note) <= 2000),
            step_up_id       uuid,
            created_at       timestamptz NOT NULL DEFAULT now(),
            CHECK ((state = 'pending') = (decided_at IS NULL))
        );
        CREATE INDEX approvals_session ON workshop.approvals (session_id, created_at);
        CREATE FUNCTION workshop.approvals_final() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF OLD.state <> 'pending' AND NEW.state <> OLD.state THEN
                    RAISE EXCEPTION 'approval % is already %', OLD.ref, OLD.state USING ERRCODE = 'HQS01';
                END IF;
                RETURN NEW;
            END $$;
        CREATE TRIGGER approvals_final BEFORE UPDATE OF state ON workshop.approvals
            FOR EACH ROW EXECUTE FUNCTION workshop.approvals_final();
        CREATE TRIGGER approvals_no_delete BEFORE DELETE ON workshop.approvals
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        GRANT SELECT ON workshop.workspaces, workshop.grants, workshop.sessions, workshop.events,
            workshop.approvals TO {APP_ROLES};
        GRANT INSERT ON workshop.workspaces TO hq_api;
        GRANT UPDATE (repo, default_branch, title_fa, policy, status, updated_at)
            ON workshop.workspaces TO hq_api;
        GRANT INSERT ON workshop.grants TO {APP_ROLES};
        GRANT UPDATE (revoked_at, revoked_by_kind, revoked_by_code) ON workshop.grants TO {APP_ROLES};
        GRANT INSERT ON workshop.sessions TO {APP_ROLES};
        GRANT UPDATE (state, held, branch, pr_url, usd, input_tokens, output_tokens, external_id,
                      external_cursor, transcript_file_id, error_code, last_seq, updated_at, finished_at)
            ON workshop.sessions TO {APP_ROLES};
        GRANT INSERT ON workshop.events TO {APP_ROLES};
        GRANT INSERT ON workshop.approvals TO {APP_ROLES};
        GRANT UPDATE (state, decided_at, decided_by_kind, decided_by_code, note, step_up_id)
            ON workshop.approvals TO {APP_ROLES};

        -- ---------------------------------------------------------- orders
        CREATE SEQUENCE owner.order_ref_seq;
        GRANT USAGE ON SEQUENCE owner.order_ref_seq TO {APP_ROLES};
        CREATE TABLE owner.orders (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref         text NOT NULL UNIQUE
                             DEFAULT 'F-' || lpad(nextval('owner.order_ref_seq')::text, 4, '0'),
            company_id  uuid NOT NULL REFERENCES core.companies (id),
            text        text NOT NULL CHECK (length(text) BETWEEN 1 AND 10000),
            source      text NOT NULL CHECK (source IN ('voice', 'text')),
            file_id     uuid REFERENCES files.files (id),
            company_hint text CHECK (company_hint ~ '^[A-Z][A-Z0-9]{{1,9}}$'),
            routes      jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(routes) = 'array'),
            routed_by   text NOT NULL DEFAULT 'rules' CHECK (routed_by IN ('rules', 'model', 'advisor')),
            summary_fa  text NOT NULL DEFAULT '' CHECK (length(summary_fa) <= 2000),
            created_at  timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX orders_at ON owner.orders (created_at DESC);
        CREATE TRIGGER orders_no_delete BEFORE DELETE ON owner.orders
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        GRANT SELECT, INSERT ON owner.orders TO {APP_ROLES};

        {_rls(["workshop.workspaces", "workshop.grants", "workshop.sessions", "workshop.events",
               "workshop.approvals", "owner.orders"])}

        -- ------------------------------------------- decision kind code_session
        ALTER TABLE cartable.decisions DROP CONSTRAINT decisions_kind_check;
        ALTER TABLE cartable.decisions ADD CONSTRAINT decisions_kind_check
            CHECK (kind IN ({KINDS}, 'code_session'));
        """
    )


def downgrade() -> None:
    execute_script(
        f"""
        ALTER TABLE cartable.decisions DROP CONSTRAINT decisions_kind_check;
        ALTER TABLE cartable.decisions ADD CONSTRAINT decisions_kind_check CHECK (kind IN ({KINDS}));
        DROP TABLE owner.orders;
        DROP SEQUENCE owner.order_ref_seq;
        DROP SCHEMA workshop CASCADE;
        """
    )
