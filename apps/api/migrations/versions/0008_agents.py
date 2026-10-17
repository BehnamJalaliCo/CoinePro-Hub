"""Prompt 05: agents at work, rule-based site checks, and what 04.1 left.

Agents (contract §16.1-16.3, OPERATING_MODEL §1.3, §1.4):
  - core.employees.role: the charter (agents/roles/<role>.md) an employee
    runs with. Leadership positions get it from their template; a hire from
    its decision's payload. NULL = no charter = never woken.
  - agents.runs: the run registry. A run is a RECORD first (state queued):
    triggers below queue one whenever work reaches an agent, a child's
    deliverable reaches its parent's assignee, or the owner writes in an
    agent's thread. The worker claims it (running, at most one per employee),
    executes it and closes it (done | failed | refused). An agent token is
    accepted only while its run is running (the api checks this table).
  - agents.steps: one row per step: a Persian summary and tool metadata only
    (tool, class, outcome, ref) - never a prompt, raw model output or payload.
  - core.employee_memory: append-only notes of each employee (memory.read /
    memory.write); a dismissal copies them to the receiver (knowledge transfer).

Site checks (contract §16.4): ops.sites (data, edited by the owner), ops.checks
(daily partitions, 30 days kept), ops.incidents (I-0001, one open per site),
ops.hub_health (the hub's own latest snapshot, for health.hub).

Also: msg.messages gains `citations` and `meta` (advisor citations validated
server-side), the work budget now bounds spending (tokens_used/usd_used), the
web session token can rotate after a step-up, new functions are never
executable by PUBLIC by default, and the evidence CHECKs added NOT VALID in
0007 are validated (no old row breaks them).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
NIL = "00000000-0000-0000-0000-000000000000"


def _rls(tables: list[str]) -> str:
    return "\n".join(
        f"""
        ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {t} FORCE ROW LEVEL SECURITY;
        CREATE POLICY {t.split('.')[1]}_tenant ON {t} TO {APP_ROLES}
            USING (company_id = ANY (core.allowed_company_ids()))
            WITH CHECK (company_id = ANY (core.allowed_company_ids()));
        CREATE POLICY {t.split('.')[1]}_owner_role ON {t} TO hq USING (true) WITH CHECK (true);
        """
        for t in tables
    )


def upgrade() -> None:
    execute_script(
        rf"""
        -- ------------------------------------------- functions: never PUBLIC
        -- Every function created from now on by the owner role starts without
        -- EXECUTE for PUBLIC; each one is granted to the roles that need it.
        ALTER DEFAULT PRIVILEGES FOR ROLE hq REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

        -- -------------------------------------------- evidence CHECKs, validated
        ALTER TABLE work.work VALIDATE CONSTRAINT work_evidence_items;
        ALTER TABLE cartable.deliverables VALIDATE CONSTRAINT deliverables_evidence_items;

        -- --------------------------------- web sessions rotate after a step-up
        GRANT UPDATE (token_sha256) ON auth.sessions TO hq_api;

        -- ------------------------------------------------ the charter of a role
        ALTER TABLE core.employees
            ADD COLUMN role text CHECK (role ~ '^[a-z][a-z0-9_]{{1,40}}$');
        COMMENT ON COLUMN core.employees.role IS
            'Charter agents/roles/<role>.md (leadership: from the template; hires: from the decision)';

        -- ------------------------------------------- spending stays in budget
        -- A work item's own spending (tokens_used, usd_used) may not grow once
        -- its budget is used up (what it spent plus what its children were
        -- given). The step that crosses the line is still recorded truthfully;
        -- the runtime checks what is left before every step.
        CREATE OR REPLACE FUNCTION work.before_update() RETURNS trigger
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
                IF NEW.tokens_used < OLD.tokens_used OR NEW.usd_used < OLD.usd_used THEN
                    RAISE EXCEPTION 'work %: spending never goes down', NEW.ref USING ERRCODE = 'HQV01';
                END IF;
                IF (NEW.tokens_used > OLD.tokens_used AND NEW.budget_tokens IS NOT NULL)
                   OR (NEW.usd_used > OLD.usd_used AND NEW.budget_usd IS NOT NULL) THEN
                    SELECT COALESCE(sum(budget_tokens), 0), COALESCE(sum(budget_usd), 0)
                        INTO children_tokens, children_usd FROM work.work WHERE parent_id = NEW.id;
                    IF NEW.tokens_used > OLD.tokens_used AND NEW.budget_tokens IS NOT NULL
                       AND OLD.tokens_used + children_tokens >= NEW.budget_tokens THEN
                        RAISE EXCEPTION 'work % has no token budget left (% used, % given to children, budget %)',
                            NEW.ref, OLD.tokens_used, children_tokens, NEW.budget_tokens USING ERRCODE = 'HQB01';
                    END IF;
                    IF NEW.usd_used > OLD.usd_used AND NEW.budget_usd IS NOT NULL
                       AND OLD.usd_used + children_usd >= NEW.budget_usd THEN
                        RAISE EXCEPTION 'work % has no USD budget left', NEW.ref USING ERRCODE = 'HQB01';
                    END IF;
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

        -- ------------------------------------------------------------- agents
        CREATE SCHEMA agents;
        GRANT USAGE ON SCHEMA agents TO {APP_ROLES};

        CREATE TABLE agents.runs (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id          uuid NOT NULL REFERENCES core.companies (id),
            employee_id         uuid NOT NULL,
            work_id             uuid,
            thread_id           uuid,
            trigger             text NOT NULL CHECK (trigger IN ('work', 'message', 'schedule', 'alert')),
            reason              text NOT NULL DEFAULT '' CHECK (length(reason) <= 200),
            state               text NOT NULL DEFAULT 'queued'
                                     CHECK (state IN ('queued', 'running', 'done', 'failed', 'refused')),
            priority            text NOT NULL DEFAULT 'P3' CHECK (priority IN ('P0', 'P1', 'P2', 'P3', 'P4')),
            charter_role        text CHECK (charter_role ~ '^[a-z][a-z0-9_]{{1,40}}$'),
            charter_version     int CHECK (charter_version >= 1),
            model               text CHECK (length(model) <= 100),
            effort              text CHECK (effort IN ('low', 'medium', 'high', 'xhigh', 'max')),
            steps               int NOT NULL DEFAULT 0 CHECK (steps >= 0),
            steps_cap           int CHECK (steps_cap BETWEEN 1 AND 50),
            token_cap           bigint CHECK (token_cap >= 0),
            tool_calls          int NOT NULL DEFAULT 0 CHECK (tool_calls >= 0),
            tool_calls_cap      int NOT NULL DEFAULT 48 CHECK (tool_calls_cap BETWEEN 0 AND 500),
            input_tokens        bigint NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
            output_tokens       bigint NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
            cache_read_tokens   bigint NOT NULL DEFAULT 0 CHECK (cache_read_tokens >= 0),
            cache_write_tokens  bigint NOT NULL DEFAULT 0 CHECK (cache_write_tokens >= 0),
            equiv_cost_usd      numeric(14, 6) NOT NULL DEFAULT 0 CHECK (equiv_cost_usd >= 0),
            cost_usd            numeric(14, 6) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
            partial             boolean NOT NULL DEFAULT false,
            error_code          text CHECK (error_code ~ '^[a-z][a-z0-9_]{{1,40}}$'),
            note                text CHECK (length(note) <= 1000),
            queued_at           timestamptz NOT NULL DEFAULT now(),
            dispatched_at       timestamptz,
            started_at          timestamptz,
            finished_at         timestamptz,
            token_expires_at    timestamptz,
            version             int NOT NULL DEFAULT 1,
            created_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now(),
            UNIQUE (company_id, id),
            FOREIGN KEY (company_id, employee_id) REFERENCES core.employees (company_id, id),
            FOREIGN KEY (company_id, work_id) REFERENCES work.work (company_id, id),
            FOREIGN KEY (company_id, thread_id) REFERENCES msg.threads (company_id, id),
            CHECK (state = 'queued' OR state = 'refused' OR state = 'failed' OR started_at IS NOT NULL),
            CHECK ((state IN ('done', 'failed', 'refused')) = (finished_at IS NOT NULL)),
            CHECK (tool_calls <= tool_calls_cap)
        );
        -- At most one run at a time per employee; one queued run per employee and cause.
        CREATE UNIQUE INDEX runs_one_running ON agents.runs (employee_id) WHERE state = 'running';
        CREATE UNIQUE INDEX runs_one_queued ON agents.runs
            (employee_id, COALESCE(work_id, '{NIL}'::uuid), COALESCE(thread_id, '{NIL}'::uuid))
            WHERE state = 'queued';
        CREATE INDEX runs_dispatch ON agents.runs (queued_at) WHERE state = 'queued';
        CREATE INDEX runs_company ON agents.runs (company_id, created_at DESC);
        CREATE INDEX runs_employee ON agents.runs (employee_id, created_at DESC);
        CREATE INDEX runs_work ON agents.runs (work_id, created_at DESC) WHERE work_id IS NOT NULL;

        -- queued -> running | refused | failed; running -> done | failed | refused.
        -- A finished run never changes; counters never go down.
        CREATE FUNCTION agents.runs_guard() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF OLD.state IN ('done', 'failed', 'refused') THEN
                    RAISE EXCEPTION 'run % is finished (%)', OLD.id, OLD.state USING ERRCODE = 'HQI01';
                END IF;
                IF OLD.state = 'queued' AND NEW.state NOT IN ('queued', 'running', 'refused', 'failed')
                   OR OLD.state = 'running' AND NEW.state NOT IN ('running', 'done', 'failed', 'refused') THEN
                    RAISE EXCEPTION 'run %: % -> % is not a transition', OLD.id, OLD.state, NEW.state
                        USING ERRCODE = 'HQV01';
                END IF;
                IF NEW.steps < OLD.steps OR NEW.tool_calls < OLD.tool_calls
                   OR NEW.input_tokens < OLD.input_tokens OR NEW.output_tokens < OLD.output_tokens
                   OR NEW.cache_read_tokens < OLD.cache_read_tokens
                   OR NEW.cache_write_tokens < OLD.cache_write_tokens
                   OR NEW.equiv_cost_usd < OLD.equiv_cost_usd OR NEW.cost_usd < OLD.cost_usd THEN
                    RAISE EXCEPTION 'run %: counters never go down', OLD.id USING ERRCODE = 'HQV01';
                END IF;
                RETURN NEW;
            END $$;
        CREATE TRIGGER runs_guard BEFORE UPDATE ON agents.runs
            FOR EACH ROW EXECUTE FUNCTION agents.runs_guard();
        CREATE TRIGGER runs_immutable BEFORE UPDATE ON agents.runs
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'company_id', 'employee_id', 'work_id', 'thread_id', 'trigger', 'reason',
                'queued_at', 'created_at');
        CREATE TRIGGER runs_version BEFORE UPDATE ON agents.runs
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();
        CREATE TRIGGER runs_no_delete BEFORE DELETE ON agents.runs
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER runs_no_truncate BEFORE TRUNCATE ON agents.runs
            FOR EACH STATEMENT EXECUTE FUNCTION core.reject_change();
        CREATE FUNCTION agents.runs_notify() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                PERFORM pg_notify('hq_runs', '');
                RETURN NULL;
            END $$;
        CREATE TRIGGER runs_notify AFTER INSERT ON agents.runs
            FOR EACH STATEMENT EXECUTE FUNCTION agents.runs_notify();

        CREATE TABLE agents.steps (
            id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            run_id      uuid NOT NULL,
            company_id  uuid NOT NULL REFERENCES core.companies (id),
            n           int  NOT NULL CHECK (n BETWEEN 1 AND 50),
            at          timestamptz NOT NULL DEFAULT now(),
            summary_fa  text NOT NULL DEFAULT '' CHECK (length(summary_fa) <= 2000),
            actions     jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(actions) = 'array'),
            usage       jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(usage) = 'object'),
            call_id     uuid,
            UNIQUE (run_id, n),
            FOREIGN KEY (company_id, run_id) REFERENCES agents.runs (company_id, id)
        );
        CREATE TRIGGER steps_append_only BEFORE UPDATE OR DELETE ON agents.steps
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER steps_no_truncate BEFORE TRUNCATE ON agents.steps
            FOR EACH STATEMENT EXECUTE FUNCTION core.reject_change();

        -- Queue a run for an employee (idempotent per employee and cause).
        -- Nobody is woken who has no charter, is not active, or is the
        -- rule-based report system.
        CREATE FUNCTION agents.queue_run(p_employee uuid, p_trigger text, p_work uuid, p_thread uuid,
                                         p_reason text, p_priority text) RETURNS uuid
            LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            DECLARE
                e record;
                rid uuid;
            BEGIN
                SELECT id, company_id, kind, status, role INTO e FROM core.employees WHERE id = p_employee;
                IF NOT FOUND OR e.kind = 'system' OR e.status <> 'active' OR e.role IS NULL THEN
                    RETURN NULL;
                END IF;
                INSERT INTO agents.runs (company_id, employee_id, work_id, thread_id, trigger, reason, priority)
                VALUES (e.company_id, e.id, p_work, p_thread, p_trigger, left(COALESCE(p_reason, ''), 200),
                        COALESCE(p_priority, 'P3'))
                ON CONFLICT (employee_id, COALESCE(work_id, '{NIL}'::uuid), COALESCE(thread_id, '{NIL}'::uuid))
                    WHERE state = 'queued' DO NOTHING
                RETURNING id INTO rid;
                IF rid IS NULL THEN
                    SELECT id INTO rid FROM agents.runs
                     WHERE employee_id = e.id AND state = 'queued'
                       AND work_id IS NOT DISTINCT FROM p_work AND thread_id IS NOT DISTINCT FROM p_thread;
                END IF;
                RETURN rid;
            END $$;
        GRANT EXECUTE ON FUNCTION agents.queue_run(uuid, text, uuid, uuid, text, text) TO {APP_ROLES};

        -- Work reaching an agent wakes it (owner orders, delegation, requests,
        -- recurring occurrences, incidents, knowledge transfer, reassignment).
        -- A recurring template is a definition, not work: its occurrences wake.
        CREATE FUNCTION agents.wake_on_work() RETURNS trigger
            LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            DECLARE
                arrived boolean;
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    arrived := true;
                ELSE
                    arrived := NEW.assignee_id IS DISTINCT FROM OLD.assignee_id;
                END IF;
                IF arrived AND NEW.assignee_id IS NOT NULL AND NEW.kind <> 'recurring'
                   AND NEW.status = 'queued' THEN
                    PERFORM agents.queue_run(
                        NEW.assignee_id,
                        CASE WHEN NEW.recurrence_of IS NOT NULL THEN 'schedule'
                             WHEN NEW.kind = 'event' AND NEW.created_by_kind = 'service' THEN 'alert'
                             ELSE 'work' END,
                        NEW.id, NULL, 'work:' || NEW.ref, NEW.priority);
                END IF;
                RETURN NULL;
            END $$;
        CREATE TRIGGER work_wake AFTER INSERT OR UPDATE OF assignee_id ON work.work
            FOR EACH ROW EXECUTE FUNCTION agents.wake_on_work();

        -- A child's deliverable wakes the parent's assignee (it does not wait).
        CREATE FUNCTION agents.wake_on_deliverable() RETURNS trigger
            LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            DECLARE
                c record;
                p record;
            BEGIN
                SELECT parent_id, ref INTO c FROM work.work WHERE id = NEW.work_id;
                IF c.parent_id IS NULL THEN
                    RETURN NULL;
                END IF;
                SELECT id, assignee_id, status, priority INTO p FROM work.work WHERE id = c.parent_id;
                IF p.assignee_id IS NOT NULL AND p.status IN ('queued', 'in_progress', 'waiting') THEN
                    PERFORM agents.queue_run(p.assignee_id, 'work', p.id, NULL,
                                             'child_delivered:' || c.ref || ':' || NEW.ref, p.priority);
                END IF;
                RETURN NULL;
            END $$;
        CREATE TRIGGER deliverables_wake AFTER INSERT ON cartable.deliverables
            FOR EACH ROW EXECUTE FUNCTION agents.wake_on_deliverable();

        -- The owner writing in an agent's thread wakes that agent (advisor at P2).
        CREATE FUNCTION agents.wake_on_message() RETURNS trigger
            LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            DECLARE
                t record;
            BEGIN
                IF NEW.author_kind <> 'owner' THEN
                    RETURN NULL;
                END IF;
                SELECT kind, employee_id INTO t FROM msg.threads WHERE id = NEW.thread_id;
                IF t.employee_id IS NOT NULL AND t.kind IN ('advisor', 'ceo', 'manager', 'employee') THEN
                    PERFORM agents.queue_run(t.employee_id, 'message', NULL, NEW.thread_id,
                                             'message:' || NEW.ref,
                                             CASE WHEN t.kind = 'advisor' THEN 'P2' END);
                END IF;
                RETURN NULL;
            END $$;
        CREATE TRIGGER messages_wake AFTER INSERT ON msg.messages
            FOR EACH ROW EXECUTE FUNCTION agents.wake_on_message();

        GRANT SELECT ON agents.runs, agents.steps TO {APP_ROLES};
        -- The gateway's reservation of a tool call (through the api, agent's own run).
        GRANT UPDATE (tool_calls) ON agents.runs TO hq_api;
        GRANT UPDATE (state, priority, charter_role, charter_version, model, effort, steps, steps_cap,
                      token_cap, tool_calls, tool_calls_cap, input_tokens, output_tokens,
                      cache_read_tokens, cache_write_tokens, equiv_cost_usd, cost_usd, partial,
                      error_code, note, dispatched_at, started_at, finished_at, token_expires_at)
            ON agents.runs TO hq_worker;
        GRANT INSERT ON agents.steps TO hq_worker;

        -- ------------------------------------------------- employee memory
        CREATE TABLE core.employee_memory (
            id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            company_id          uuid NOT NULL REFERENCES core.companies (id),
            employee_id         uuid NOT NULL,
            run_id              uuid,
            note                text NOT NULL CHECK (length(note) BETWEEN 1 AND 4000),
            tags                text[] NOT NULL DEFAULT '{{}}' CHECK (cardinality(tags) <= 10),
            source_employee_id  uuid,
            created_at          timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (company_id, employee_id) REFERENCES core.employees (company_id, id),
            FOREIGN KEY (company_id, run_id) REFERENCES agents.runs (company_id, id),
            FOREIGN KEY (company_id, source_employee_id) REFERENCES core.employees (company_id, id)
        );
        CREATE INDEX employee_memory_latest ON core.employee_memory (employee_id, id DESC);
        CREATE TRIGGER employee_memory_append_only BEFORE UPDATE OR DELETE ON core.employee_memory
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER employee_memory_no_truncate BEFORE TRUNCATE ON core.employee_memory
            FOR EACH STATEMENT EXECUTE FUNCTION core.reject_change();
        GRANT SELECT, INSERT ON core.employee_memory TO {APP_ROLES};

        -- --------------------------------------------- messages: citations
        ALTER TABLE msg.messages
            ADD COLUMN citations jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(citations) = 'array'),
            ADD COLUMN meta jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(meta) = 'object');

        -- --------------------------------------------- the subscription quota
        GRANT SELECT ON llm.quota_status TO {APP_ROLES};

        -- ------------------------------------------------------------ ops
        CREATE SCHEMA ops;
        GRANT USAGE ON SCHEMA ops TO {APP_ROLES};

        CREATE TABLE ops.sites (
            id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id            uuid NOT NULL REFERENCES core.companies (id),
            url                   text NOT NULL CHECK (url ~ '^https?://[^\s/$.?#][^\s]*$' AND length(url) <= 500),
            kind                  text NOT NULL DEFAULT 'web' CHECK (kind IN ('web', 'api', 'bot')),
            method                text NOT NULL DEFAULT 'GET' CHECK (method IN ('GET', 'HEAD')),
            expect                jsonb NOT NULL DEFAULT '{{"status": 200}}' CHECK (jsonb_typeof(expect) = 'object'),
            interval_s            int NOT NULL DEFAULT 300 CHECK (interval_s BETWEEN 60 AND 86400),
            enabled               boolean NOT NULL DEFAULT true,
            canary                boolean NOT NULL DEFAULT false,
            consecutive_failures  int NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
            last_checked_at       timestamptz,
            version               int NOT NULL DEFAULT 1,
            created_at            timestamptz NOT NULL DEFAULT now(),
            updated_at            timestamptz NOT NULL DEFAULT now(),
            UNIQUE (company_id, url),
            UNIQUE (company_id, id)
        );
        CREATE TRIGGER sites_immutable BEFORE UPDATE ON ops.sites
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'url', 'canary', 'created_at');
        CREATE TRIGGER sites_version BEFORE UPDATE ON ops.sites
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();
        CREATE TRIGGER sites_no_delete BEFORE DELETE ON ops.sites
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        -- Check results: telemetry, kept 30 days in daily partitions.
        CREATE TABLE ops.checks (
            site_id        uuid NOT NULL,
            company_id     uuid NOT NULL REFERENCES core.companies (id),
            at             timestamptz NOT NULL DEFAULT now(),
            ok             boolean NOT NULL,
            status         int CHECK (status BETWEEN 100 AND 599),
            latency_ms     int CHECK (latency_ms >= 0),
            tls_days_left  int,
            error_code     text CHECK (error_code ~ '^[a-z][a-z0-9_]{{1,40}}$'),
            PRIMARY KEY (site_id, at),
            FOREIGN KEY (company_id, site_id) REFERENCES ops.sites (company_id, id)
        ) PARTITION BY RANGE (at);
        CREATE INDEX checks_company_at ON ops.checks (company_id, at DESC);

        CREATE FUNCTION ops.ensure_check_partitions(p_days int) RETURNS int
            LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            DECLARE
                d date;
                name text;
                made int := 0;
            BEGIN
                FOR i IN 0 .. greatest(p_days, 0) LOOP
                    d := (now() AT TIME ZONE 'UTC')::date + i;
                    name := 'checks_' || to_char(d, 'YYYYMMDD');
                    IF to_regclass('ops.' || name) IS NULL THEN
                        EXECUTE format('CREATE TABLE ops.%I PARTITION OF ops.checks FOR VALUES FROM (%L) TO (%L)',
                                       name, d::timestamp AT TIME ZONE 'UTC', (d + 1)::timestamp AT TIME ZONE 'UTC');
                        made := made + 1;
                    END IF;
                END LOOP;
                RETURN made;
            END $$;
        CREATE FUNCTION ops.drop_old_check_partitions(p_keep_days int) RETURNS int
            LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            DECLARE
                r record;
                dropped int := 0;
            BEGIN
                FOR r IN SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
                         WHERE i.inhparent = 'ops.checks'::regclass AND c.relname ~ '^checks_[0-9]{{8}}$' LOOP
                    IF to_date(substr(r.relname, 8), 'YYYYMMDD')
                       < (now() AT TIME ZONE 'UTC')::date - greatest(p_keep_days, 1) THEN
                        EXECUTE format('DROP TABLE ops.%I', r.relname);
                        dropped := dropped + 1;
                    END IF;
                END LOOP;
                RETURN dropped;
            END $$;
        GRANT EXECUTE ON FUNCTION ops.ensure_check_partitions(int), ops.drop_old_check_partitions(int)
            TO hq_worker;
        SELECT ops.ensure_check_partitions(2);

        CREATE SEQUENCE ops.incident_ref_seq;
        GRANT USAGE ON SEQUENCE ops.incident_ref_seq TO hq_worker;
        CREATE TABLE ops.incidents (
            id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref            text NOT NULL UNIQUE
                                DEFAULT 'I-' || lpad(nextval('ops.incident_ref_seq')::text, 4, '0'),
            company_id     uuid NOT NULL REFERENCES core.companies (id),
            site_id        uuid NOT NULL,
            opened_at      timestamptz NOT NULL DEFAULT now(),
            closed_at      timestamptz,
            severity       text NOT NULL DEFAULT 'sev2' CHECK (severity IN ('sev1', 'sev2', 'sev3')),
            work_id        uuid,
            checks_failed  int NOT NULL DEFAULT 0 CHECK (checks_failed >= 0),
            last_status    int CHECK (last_status BETWEEN 100 AND 599),
            last_error     text CHECK (last_error ~ '^[a-z][a-z0-9_]{{1,40}}$'),
            version        int NOT NULL DEFAULT 1,
            updated_at     timestamptz NOT NULL DEFAULT now(),
            UNIQUE (company_id, id),
            FOREIGN KEY (company_id, site_id) REFERENCES ops.sites (company_id, id),
            FOREIGN KEY (company_id, work_id) REFERENCES work.work (company_id, id),
            CHECK (closed_at IS NULL OR closed_at >= opened_at)
        );
        CREATE UNIQUE INDEX incidents_one_open ON ops.incidents (site_id) WHERE closed_at IS NULL;
        CREATE INDEX incidents_company ON ops.incidents (company_id, opened_at DESC);
        CREATE TRIGGER incidents_immutable BEFORE UPDATE ON ops.incidents
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'site_id', 'opened_at');
        CREATE TRIGGER incidents_version BEFORE UPDATE ON ops.incidents
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();
        CREATE TRIGGER incidents_no_delete BEFORE DELETE ON ops.incidents
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        CREATE FUNCTION ops.incident_closed_final() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF OLD.closed_at IS NOT NULL THEN
                    RAISE EXCEPTION 'incident % is closed', OLD.ref USING ERRCODE = 'HQI01';
                END IF;
                RETURN NEW;
            END $$;
        CREATE TRIGGER incidents_closed_final BEFORE UPDATE ON ops.incidents
            FOR EACH ROW EXECUTE FUNCTION ops.incident_closed_final();

        -- The hub's own latest health snapshot (one row, the holding's).
        CREATE TABLE ops.hub_health (
            company_id  uuid PRIMARY KEY REFERENCES core.companies (id),
            at          timestamptz NOT NULL DEFAULT now(),
            data        jsonb NOT NULL CHECK (jsonb_typeof(data) = 'object')
        );

        GRANT SELECT ON ops.sites, ops.checks, ops.incidents, ops.hub_health TO {APP_ROLES};
        GRANT INSERT ON ops.sites TO hq_api;
        GRANT UPDATE (kind, method, expect, interval_s, enabled) ON ops.sites TO hq_api;
        GRANT UPDATE (consecutive_failures, last_checked_at) ON ops.sites TO hq_worker;
        GRANT INSERT ON ops.checks TO hq_worker;
        GRANT INSERT ON ops.incidents TO hq_worker;
        GRANT UPDATE (closed_at, severity, work_id, checks_failed, last_status, last_error)
            ON ops.incidents TO hq_worker;
        GRANT INSERT, UPDATE ON ops.hub_health TO hq_worker;
        """
    )
    execute_script(
        _rls(
            [
                "agents.runs",
                "agents.steps",
                "core.employee_memory",
                "ops.sites",
                "ops.checks",
                "ops.incidents",
                "ops.hub_health",
            ]
        )
    )


def downgrade() -> None:
    raise NotImplementedError("0008 adds append-only records; restore from backup to go back")
