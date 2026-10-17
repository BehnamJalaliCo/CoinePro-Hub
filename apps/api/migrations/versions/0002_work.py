"""Work and delegation (contract §4): work items, their timeline, escrows
("پاکت اختیار") and schedules of recurring work.

Rules enforced here, not only in code (prompt 04 §2):
  1. depth <= 2: a child is always its parent's depth + 1 (HQD01).
  2. a child's budget <= what remains of its parent; the sum of children <=
     the parent (HQB01). A child without a budget inherits what remains.
  3. `done` only with at least one deliverable or evidence item (HQE01).
Delegation is a record (§1.4): parent_id/root_id/depth, never an agent call.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"


def upgrade() -> None:
    execute_script(
        rf"""
        CREATE SCHEMA work;
        GRANT USAGE ON SCHEMA work TO {APP_ROLES};

        CREATE SEQUENCE work.work_ref_seq;
        GRANT USAGE ON SEQUENCE work.work_ref_seq TO {APP_ROLES};

        CREATE TABLE work.work (
            id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref                   text NOT NULL UNIQUE
                                       DEFAULT 'W-' || lpad(nextval('work.work_ref_seq')::text, 6, '0'),
            company_id            uuid NOT NULL REFERENCES core.companies (id),
            department_id         uuid,
            kind                  text NOT NULL CHECK (kind IN ('one_off', 'recurring', 'event', 'project')),
            title                 text NOT NULL CHECK (length(title) BETWEEN 1 AND 300),
            brief                 text NOT NULL DEFAULT '' CHECK (length(brief) <= 50000),
            priority              text NOT NULL DEFAULT 'P3'
                                       CHECK (priority IN ('P0', 'P1', 'P2', 'P3', 'P4')),
            status                text NOT NULL DEFAULT 'queued'
                                       CHECK (status IN ('queued', 'in_progress', 'waiting', 'delivered',
                                                         'done', 'cancelled', 'failed')),
            created_by_kind       text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
            created_by_code       text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
            assignee_id           uuid REFERENCES core.employees (id),
            parent_id             uuid REFERENCES work.work (id),
            root_id               uuid NOT NULL,
            depth                 int  NOT NULL DEFAULT 0 CHECK (depth BETWEEN 0 AND 2),
            requested_by_work_id  uuid REFERENCES work.work (id),
            recurrence_of         uuid REFERENCES work.work (id),
            occurrence_at         timestamptz,
            due_at                timestamptz,
            escalation_level      int  NOT NULL DEFAULT 0 CHECK (escalation_level BETWEEN 0 AND 3),
            escalated_at          timestamptz,
            budget_tokens         bigint CHECK (budget_tokens >= 0),
            budget_usd            numeric(14, 6) CHECK (budget_usd >= 0),
            tokens_used           bigint NOT NULL DEFAULT 0 CHECK (tokens_used >= 0),
            usd_used              numeric(14, 6) NOT NULL DEFAULT 0 CHECK (usd_used >= 0),
            evidence              jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(evidence) = 'array'),
            progress_note         text CHECK (length(progress_note) <= 2000),
            progress_pct          int CHECK (progress_pct BETWEEN 0 AND 100),
            close_reason          text CHECK (length(close_reason) <= 2000),
            accepted_at           timestamptz,
            delivered_at          timestamptz,
            closed_at             timestamptz,
            version               int  NOT NULL DEFAULT 1,
            created_at            timestamptz NOT NULL DEFAULT now(),
            updated_at            timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (company_id, department_id) REFERENCES core.departments (company_id, id),
            UNIQUE (recurrence_of, occurrence_at),
            CHECK ((recurrence_of IS NULL) = (occurrence_at IS NULL))
        );
        CREATE INDEX work_company_status ON work.work (company_id, status, created_at DESC);
        CREATE INDEX work_assignee ON work.work (assignee_id, status);
        CREATE INDEX work_parent ON work.work (parent_id);
        CREATE INDEX work_root ON work.work (root_id);
        CREATE INDEX work_due ON work.work (due_at)
            WHERE status IN ('queued', 'in_progress', 'waiting');

        -- Delegation depth, root and budget of a new work item.
        CREATE FUNCTION work.before_insert() RETURNS trigger
            LANGUAGE plpgsql AS $$
            DECLARE
                p work.work%ROWTYPE;
                given_tokens bigint;
                given_usd numeric;
                left_tokens bigint;
                left_usd numeric;
            BEGIN
                IF NEW.parent_id IS NULL THEN
                    NEW.root_id := NEW.id;
                    RETURN NEW;
                END IF;
                SELECT * INTO p FROM work.work WHERE id = NEW.parent_id FOR UPDATE;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'parent work not found' USING ERRCODE = 'HQN01';
                END IF;
                IF p.company_id <> NEW.company_id THEN
                    RAISE EXCEPTION 'delegation stays inside one company (cross-company goes CEO to CEO)'
                        USING ERRCODE = 'HQV01';
                END IF;
                IF p.depth + 1 > 2 THEN
                    RAISE EXCEPTION 'delegation depth would be %, the maximum is 2', p.depth + 1
                        USING ERRCODE = 'HQD01';
                END IF;
                NEW.depth := p.depth + 1;
                NEW.root_id := p.root_id;
                IF p.status IN ('done', 'cancelled', 'failed') THEN
                    RAISE EXCEPTION 'parent work is closed' USING ERRCODE = 'HQV01';
                END IF;
                SELECT COALESCE(sum(budget_tokens), 0), COALESCE(sum(budget_usd), 0)
                    INTO given_tokens, given_usd
                    FROM work.work WHERE parent_id = p.id;
                IF p.budget_tokens IS NOT NULL THEN
                    left_tokens := p.budget_tokens - p.tokens_used - given_tokens;
                    NEW.budget_tokens := COALESCE(NEW.budget_tokens, greatest(left_tokens, 0));
                    IF NEW.budget_tokens > left_tokens THEN
                        RAISE EXCEPTION 'child token budget % exceeds what remains of the parent (%)',
                            NEW.budget_tokens, left_tokens USING ERRCODE = 'HQB01';
                    END IF;
                END IF;
                IF p.budget_usd IS NOT NULL THEN
                    left_usd := p.budget_usd - p.usd_used - given_usd;
                    NEW.budget_usd := COALESCE(NEW.budget_usd, greatest(left_usd, 0));
                    IF NEW.budget_usd > left_usd THEN
                        RAISE EXCEPTION 'child USD budget % exceeds what remains of the parent (%)',
                            NEW.budget_usd, left_usd USING ERRCODE = 'HQB01';
                    END IF;
                END IF;
                RETURN NEW;
            END $$;
        CREATE TRIGGER work_before_insert BEFORE INSERT ON work.work
            FOR EACH ROW EXECUTE FUNCTION work.before_insert();

        -- Budget changes keep the tree consistent; `done` needs evidence.
        CREATE FUNCTION work.before_update() RETURNS trigger
            LANGUAGE plpgsql AS $$
            DECLARE
                p work.work%ROWTYPE;
                siblings_tokens bigint;
                siblings_usd numeric;
                children_tokens bigint;
                children_usd numeric;
            BEGIN
                IF NEW.status = 'done' AND OLD.status <> 'done'
                   AND jsonb_array_length(NEW.evidence) = 0
                   AND NOT EXISTS (SELECT 1 FROM cartable.deliverables d WHERE d.work_id = NEW.id) THEN
                    RAISE EXCEPTION 'work % cannot be done without a deliverable or evidence', NEW.ref
                        USING ERRCODE = 'HQE01';
                END IF;
                IF OLD.status IN ('done', 'cancelled', 'failed') AND NEW.status <> OLD.status THEN
                    RAISE EXCEPTION 'work % is closed (%)', NEW.ref, OLD.status USING ERRCODE = 'HQV01';
                END IF;
                IF NEW.budget_tokens IS DISTINCT FROM OLD.budget_tokens
                   OR NEW.budget_usd IS DISTINCT FROM OLD.budget_usd THEN
                    SELECT COALESCE(sum(budget_tokens), 0), COALESCE(sum(budget_usd), 0)
                        INTO children_tokens, children_usd FROM work.work WHERE parent_id = NEW.id;
                    IF NEW.budget_tokens IS NOT NULL AND NEW.budget_tokens < children_tokens + NEW.tokens_used
                       OR NEW.budget_usd IS NOT NULL AND NEW.budget_usd < children_usd + NEW.usd_used THEN
                        RAISE EXCEPTION 'budget of % is below what its children and its own use already need',
                            NEW.ref USING ERRCODE = 'HQB01';
                    END IF;
                    IF NEW.parent_id IS NOT NULL THEN
                        SELECT * INTO p FROM work.work WHERE id = NEW.parent_id FOR UPDATE;
                        SELECT COALESCE(sum(budget_tokens), 0), COALESCE(sum(budget_usd), 0)
                            INTO siblings_tokens, siblings_usd
                            FROM work.work WHERE parent_id = p.id AND id <> NEW.id;
                        IF p.budget_tokens IS NOT NULL AND (NEW.budget_tokens IS NULL
                               OR NEW.budget_tokens > p.budget_tokens - p.tokens_used - siblings_tokens)
                           OR p.budget_usd IS NOT NULL AND (NEW.budget_usd IS NULL
                               OR NEW.budget_usd > p.budget_usd - p.usd_used - siblings_usd) THEN
                            RAISE EXCEPTION 'budget of % exceeds what remains of its parent', NEW.ref
                                USING ERRCODE = 'HQB01';
                        END IF;
                    END IF;
                END IF;
                RETURN NEW;
            END $$;
        CREATE TRIGGER work_before_update BEFORE UPDATE ON work.work
            FOR EACH ROW EXECUTE FUNCTION work.before_update();
        CREATE TRIGGER work_immutable BEFORE UPDATE ON work.work
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'ref', 'company_id', 'kind', 'created_by_kind', 'created_by_code',
                'parent_id', 'root_id', 'depth', 'requested_by_work_id', 'recurrence_of',
                'occurrence_at', 'created_at');
        CREATE TRIGGER work_version BEFORE UPDATE ON work.work
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();

        -- Timeline: append-only.
        CREATE TABLE work.work_events (
            id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            work_id     uuid NOT NULL REFERENCES work.work (id),
            company_id  uuid NOT NULL REFERENCES core.companies (id),
            at          timestamptz NOT NULL DEFAULT now(),
            kind        text NOT NULL CHECK (kind ~ '^[a-z_]{{2,40}}$'),
            actor_kind  text NOT NULL CHECK (actor_kind IN ('owner', 'agent', 'service')),
            actor_code  text NOT NULL,
            data        jsonb NOT NULL DEFAULT '{{}}'
        );
        CREATE INDEX work_events_work ON work.work_events (work_id, id);
        CREATE TRIGGER work_events_append_only BEFORE UPDATE OR DELETE ON work.work_events
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER work_events_no_truncate BEFORE TRUNCATE ON work.work_events
            FOR EACH STATEMENT EXECUTE FUNCTION core.reject_change();

        -- پاکت اختیار: what a recurring work may do without asking again (§1.4).
        CREATE TABLE work.escrows (
            id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id              uuid NOT NULL REFERENCES core.companies (id),
            work_id                 uuid NOT NULL UNIQUE REFERENCES work.work (id),
            allowed_action_classes  text[] NOT NULL DEFAULT ARRAY['A0', 'A1']
                                         CHECK (allowed_action_classes <@ ARRAY['A0', 'A1', 'A2']),
            token_cap_per_run       bigint NOT NULL CHECK (token_cap_per_run > 0),
            usd_cap_per_month       numeric(14, 6) NOT NULL CHECK (usd_cap_per_month >= 0),
            expires_at              timestamptz NOT NULL,
            status                  text NOT NULL DEFAULT 'pending'
                                         CHECK (status IN ('pending', 'active', 'expired', 'revoked')),
            approved_by_kind        text CHECK (approved_by_kind IN ('owner', 'agent')),
            approved_by_code        text,
            decision_id             uuid,
            version                 int NOT NULL DEFAULT 1,
            created_at              timestamptz NOT NULL DEFAULT now(),
            updated_at              timestamptz NOT NULL DEFAULT now(),
            CHECK (status <> 'active' OR approved_by_code IS NOT NULL)
        );
        CREATE TRIGGER escrows_immutable BEFORE UPDATE ON work.escrows
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'work_id', 'created_at');
        CREATE TRIGGER escrows_version BEFORE UPDATE ON work.escrows
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();

        CREATE TABLE work.schedules (
            id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id            uuid NOT NULL REFERENCES core.companies (id),
            work_id               uuid NOT NULL UNIQUE REFERENCES work.work (id),
            rrule                 text NOT NULL CHECK (length(rrule) BETWEEN 5 AND 500),
            timezone              text NOT NULL DEFAULT 'Asia/Tehran',
            next_at               timestamptz,
            status                text NOT NULL DEFAULT 'pending'
                                       CHECK (status IN ('pending', 'active', 'paused', 'ended')),
            temporal_schedule_id  text,
            last_run_at           timestamptz,
            version               int NOT NULL DEFAULT 1,
            created_at            timestamptz NOT NULL DEFAULT now(),
            updated_at            timestamptz NOT NULL DEFAULT now()
        );
        CREATE TRIGGER schedules_immutable BEFORE UPDATE ON work.schedules
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'work_id', 'created_at');
        CREATE TRIGGER schedules_version BEFORE UPDATE ON work.schedules
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();

        GRANT SELECT, INSERT ON work.work, work.work_events, work.escrows, work.schedules
            TO {APP_ROLES};
        GRANT UPDATE (department_id, title, brief, priority, status, assignee_id, due_at,
                      escalation_level, escalated_at, budget_tokens, budget_usd, tokens_used,
                      usd_used, evidence, progress_note, progress_pct, close_reason, accepted_at,
                      delivered_at, closed_at)
            ON work.work TO {APP_ROLES};
        GRANT UPDATE (status, approved_by_kind, approved_by_code, decision_id, expires_at)
            ON work.escrows TO {APP_ROLES};
        GRANT UPDATE (rrule, timezone, next_at, status, temporal_schedule_id, last_run_at)
            ON work.schedules TO {APP_ROLES};
        """
    )
    execute_script(
        "\n".join(
            f"""
            ALTER TABLE work.{t} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE work.{t} FORCE ROW LEVEL SECURITY;
            CREATE POLICY {t}_tenant ON work.{t} TO {APP_ROLES}
                USING (company_id = ANY (core.allowed_company_ids()))
                WITH CHECK (company_id = ANY (core.allowed_company_ids()));
            CREATE POLICY {t}_owner_role ON work.{t} TO hq USING (true) WITH CHECK (true);
            """
            for t in ("work", "work_events", "escrows", "schedules")
        )
    )


def downgrade() -> None:
    execute_script("DROP SCHEMA work CASCADE")
