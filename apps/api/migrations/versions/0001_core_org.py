"""Core helpers and the organisation: companies (extended), departments,
employees, forward-only employee codes, score history, outbox, idempotency.

Conventions for every apps/api table (contract §0, prompt 04 §2):
  - Tenant rows carry company_id; RLS is FORCEd. Application roles (hq_api,
    hq_worker) see only core.allowed_company_ids() (app.company_ids, a uuid[]
    set per transaction with SET LOCAL, exactly like llm.*). The owner role
    hq (migrations, seeds, SECURITY DEFINER helpers) has an explicit policy.
  - Holding-level rows use the holding company's id, never NULL.
  - Business data is never deleted: no DELETE grant on business tables;
    append-only tables also reject UPDATE/DELETE/TRUNCATE with a trigger.
  - Human codes (TY-TECH-01, D-…, O-…, W-…, M-…, A-0142) are unique and
    immutable (trigger).
  - Errors raised by rules use SQLSTATE class HQ (mapped to API codes):
      HQD01 delegation_depth_exceeded   HQB01 budget_exceeded
      HQE01 evidence_required           HQS01 decision_not_pending
      HQA01 append_only                 HQI01 immutable
      HQV01 validation_failed           HQN01 not_found

Revision ID: 0001
Revises:
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"


def upgrade() -> None:
    execute_script(
        rf"""
        -- ------------------------------------------------------------ helpers --
        CREATE FUNCTION core.allowed_company_ids() RETURNS uuid[]
            LANGUAGE sql STABLE
            AS $$ SELECT COALESCE(NULLIF(current_setting('app.company_ids', true), '')::uuid[],
                                  '{{}}'::uuid[]) $$;
        GRANT EXECUTE ON FUNCTION core.allowed_company_ids() TO {APP_ROLES};

        -- Persian-safe normalisation for search: Arabic yeh/kaf -> Persian,
        -- heh with yeh -> heh, Persian/Arabic digits -> Latin, and ZWNJ, ZWJ,
        -- tatweel and diacritics (harakat, superscript alef) removed.
        CREATE FUNCTION core.fa_normalize(t text) RETURNS text
            LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
            AS $$
            SELECT btrim(regexp_replace(lower(translate(t,
                U&'\064A\0649\0643\06C0'
                || U&'\06F0\06F1\06F2\06F3\06F4\06F5\06F6\06F7\06F8\06F9'
                || U&'\0660\0661\0662\0663\0664\0665\0666\0667\0668\0669'
                || U&'\200C\200D\0640'
                || U&'\064B\064C\064D\064E\064F\0650\0651\0652\0653\0654\0655'
                || U&'\0656\0657\0658\0659\065A\065B\065C\065D\065E\065F\0670',
                U&'\06CC\06CC\06A9\0647' || '0123456789' || '0123456789')),
                '\s+', ' ', 'g'))
            $$;
        GRANT EXECUTE ON FUNCTION core.fa_normalize(text) TO {APP_ROLES};

        CREATE FUNCTION core.reject_change() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION '%.% is append-only (% rejected)', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
                    USING ERRCODE = 'HQA01';
            END $$;

        -- Usage: core.keep_immutable('col1', 'col2', ...) as a BEFORE UPDATE trigger.
        CREATE FUNCTION core.keep_immutable() RETURNS trigger
            LANGUAGE plpgsql AS $$
            DECLARE
                col text;
                old_v text;
                new_v text;
            BEGIN
                FOREACH col IN ARRAY TG_ARGV LOOP
                    EXECUTE format('SELECT ($1).%1$I::text, ($2).%1$I::text', col)
                        INTO old_v, new_v USING OLD, NEW;
                    IF old_v IS DISTINCT FROM new_v THEN
                        RAISE EXCEPTION '%.%: % is immutable', TG_TABLE_SCHEMA, TG_TABLE_NAME, col
                            USING ERRCODE = 'HQI01';
                    END IF;
                END LOOP;
                RETURN NEW;
            END $$;

        -- Bumps version and updated_at on every UPDATE (optimistic concurrency).
        CREATE FUNCTION core.bump_version() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                NEW.version := OLD.version + 1;
                NEW.updated_at := now();
                RETURN NEW;
            END $$;

        -- Gapless counters (resolutions M-0001 ...). The row lock serialises
        -- issuers until commit, so a rolled-back transaction leaves no gap.
        CREATE TABLE core.counters (
            name   text PRIMARY KEY CHECK (name ~ '^[a-z][a-z0-9_]{{1,40}}$'),
            value  bigint NOT NULL CHECK (value >= 0)
        );
        CREATE FUNCTION core.next_counter(p_name text) RETURNS bigint
            LANGUAGE sql AS $$
            INSERT INTO core.counters AS c (name, value) VALUES (p_name, 1)
            ON CONFLICT (name) DO UPDATE SET value = c.value + 1
            RETURNING value
            $$;
        CREATE TRIGGER counters_forward BEFORE UPDATE ON core.counters
            FOR EACH ROW WHEN (NEW.value <= OLD.value) EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER counters_no_delete BEFORE DELETE ON core.counters
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        GRANT SELECT, INSERT, UPDATE ON core.counters TO {APP_ROLES};
        GRANT EXECUTE ON FUNCTION core.next_counter(text) TO {APP_ROLES};

        -- ----------------------------------------------------------- companies --
        ALTER TABLE core.companies
            ADD COLUMN name_fa      text CHECK (length(name_fa) BETWEEN 1 AND 200),
            ADD COLUMN name_en      text CHECK (length(name_en) BETWEEN 1 AND 200),
            ADD COLUMN color_index  int  CHECK (color_index BETWEEN 1 AND 10),
            ADD COLUMN template     text CHECK (template ~ '^[a-z][a-z0-9_]{{1,40}}$'),
            ADD COLUMN version      int  NOT NULL DEFAULT 1,
            ADD COLUMN updated_at   timestamptz NOT NULL DEFAULT now();
        UPDATE core.companies SET name_en = name WHERE name_en IS NULL;

        -- `name` (llm-router) follows name_en.
        CREATE FUNCTION core.companies_sync_name() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.name_en IS NULL THEN
                    NEW.name_en := NEW.name;
                ELSE
                    NEW.name := NEW.name_en;
                END IF;
                RETURN NEW;
            END $$;
        CREATE TRIGGER companies_sync_name BEFORE INSERT OR UPDATE ON core.companies
            FOR EACH ROW EXECUTE FUNCTION core.companies_sync_name();
        CREATE TRIGGER companies_immutable BEFORE UPDATE ON core.companies
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'code', 'kind', 'created_at');
        CREATE TRIGGER companies_version BEFORE UPDATE ON core.companies
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();
        CREATE TRIGGER companies_no_delete BEFORE DELETE ON core.companies
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        GRANT USAGE ON SCHEMA core TO {APP_ROLES};
        GRANT SELECT ON core.companies TO {APP_ROLES};
        GRANT INSERT (code, name, kind, status, name_fa, name_en, color_index, template)
            ON core.companies TO hq_api;
        GRANT UPDATE (name, name_fa, name_en, color_index, status) ON core.companies TO hq_api;

        -- --------------------------------------------------------- departments --
        CREATE TABLE core.departments (
            id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        uuid NOT NULL REFERENCES core.companies (id),
            code              text NOT NULL CHECK (code ~ '^[A-Z][A-Z0-9]{{1,11}}$'),
            name_fa           text NOT NULL CHECK (length(name_fa) BETWEEN 1 AND 120),
            name_en           text NOT NULL CHECK (length(name_en) BETWEEN 1 AND 120),
            manager_title_fa  text NOT NULL CHECK (length(manager_title_fa) BETWEEN 1 AND 120),
            manager_title_en  text NOT NULL CHECK (length(manager_title_en) BETWEEN 1 AND 120),
            status            text NOT NULL DEFAULT 'active'
                                   CHECK (status IN ('active', 'paused', 'archived')),
            sort              int  NOT NULL DEFAULT 100,
            version           int  NOT NULL DEFAULT 1,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            UNIQUE (company_id, code),
            UNIQUE (company_id, id)
        );
        CREATE TRIGGER departments_immutable BEFORE UPDATE ON core.departments
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'code', 'created_at');
        CREATE TRIGGER departments_version BEFORE UPDATE ON core.departments
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();

        -- ----------------------------------------------------------- employees --
        CREATE TABLE core.employees (
            id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id            uuid NOT NULL REFERENCES core.companies (id),
            department_id         uuid,
            code                  text NOT NULL UNIQUE
                                       CHECK (code ~ '^[A-Z][A-Z0-9]{{1,9}}-[A-Z0-9]+(-[A-Z0-9]+)?$'),
            kind                  text NOT NULL
                                       CHECK (kind IN ('ceo', 'manager', 'employee', 'advisor',
                                                       'inspector', 'system')),
            title_fa              text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
            title_en              text NOT NULL CHECK (length(title_en) BETWEEN 1 AND 200),
            display_name          text CHECK (length(display_name) BETWEEN 1 AND 80),
            reports_to            uuid REFERENCES core.employees (id),
            status                text NOT NULL DEFAULT 'active'
                                       CHECK (status IN ('active', 'paused', 'dismissed')),
            activity              text NOT NULL DEFAULT 'sleeping'
                                       CHECK (activity IN ('sleeping', 'working', 'waiting', 'error')),
            activity_note         text CHECK (length(activity_note) <= 500),
            activity_at           timestamptz,
            duties                jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(duties) = 'array'),
            permissions           jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(permissions) = 'array'),
            score                 numeric(4, 2) CHECK (score BETWEEN 0 AND 10),
            score_owner_avg       numeric(4, 2) CHECK (score_owner_avg BETWEEN 0 AND 10),
            score_components      jsonb,
            rank_in_department    int CHECK (rank_in_department >= 1),
            score_updated_at      timestamptz,
            hired_at              timestamptz NOT NULL DEFAULT now(),
            hired_by_decision_id  uuid,
            dismissed_at          timestamptz,
            dismissal_reason      text,
            version               int NOT NULL DEFAULT 1,
            created_at            timestamptz NOT NULL DEFAULT now(),
            updated_at            timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (company_id, department_id) REFERENCES core.departments (company_id, id),
            CHECK ((status = 'dismissed') = (dismissed_at IS NOT NULL)),
            CHECK (kind NOT IN ('employee', 'manager') OR department_id IS NOT NULL)
        );
        CREATE UNIQUE INDEX employees_one_ceo ON core.employees (company_id)
            WHERE kind = 'ceo' AND status <> 'dismissed';
        CREATE UNIQUE INDEX employees_one_manager ON core.employees (department_id)
            WHERE kind IN ('manager', 'inspector') AND status <> 'dismissed';
        CREATE INDEX employees_company_dept ON core.employees (company_id, department_id, kind);
        CREATE TRIGGER employees_immutable BEFORE UPDATE ON core.employees
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'company_id', 'department_id', 'code', 'kind', 'hired_at',
                'hired_by_decision_id', 'created_at');
        -- A dismissal is final: the code stays retired forever.
        CREATE FUNCTION core.employees_dismissal_final() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF OLD.status = 'dismissed' AND NEW.status <> 'dismissed' THEN
                    RAISE EXCEPTION 'a dismissed employee cannot come back (code % is retired)', OLD.code
                        USING ERRCODE = 'HQV01';
                END IF;
                RETURN NEW;
            END $$;
        CREATE TRIGGER employees_dismissal_final BEFORE UPDATE OF status ON core.employees
            FOR EACH ROW EXECUTE FUNCTION core.employees_dismissal_final();
        CREATE TRIGGER employees_version BEFORE UPDATE ON core.employees
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();

        -- Forward-only numbering per company + department: a code is issued
        -- once and never again, even after dismissal (§1.2).
        CREATE TABLE core.employee_code_seq (
            company_id     uuid NOT NULL REFERENCES core.companies (id),
            department_id  uuid NOT NULL,
            next_no        int  NOT NULL CHECK (next_no >= 1),
            PRIMARY KEY (company_id, department_id),
            FOREIGN KEY (company_id, department_id) REFERENCES core.departments (company_id, id)
        );
        CREATE TRIGGER employee_code_seq_forward BEFORE UPDATE ON core.employee_code_seq
            FOR EACH ROW WHEN (NEW.next_no <= OLD.next_no OR NEW.company_id <> OLD.company_id
                               OR NEW.department_id <> OLD.department_id)
            EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER employee_code_seq_no_delete BEFORE DELETE ON core.employee_code_seq
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER employee_code_seq_no_truncate BEFORE TRUNCATE ON core.employee_code_seq
            FOR EACH STATEMENT EXECUTE FUNCTION core.reject_change();

        CREATE FUNCTION core.issue_employee_code(p_company uuid, p_department uuid) RETURNS text
            LANGUAGE plpgsql AS $$
            DECLARE
                n int;
                co text;
                dep text;
            BEGIN
                SELECT c.code INTO co FROM core.companies c WHERE c.id = p_company;
                SELECT d.code INTO dep FROM core.departments d
                    WHERE d.id = p_department AND d.company_id = p_company;
                IF co IS NULL OR dep IS NULL THEN
                    RAISE EXCEPTION 'unknown company or department' USING ERRCODE = 'HQN01';
                END IF;
                INSERT INTO core.employee_code_seq AS s (company_id, department_id, next_no)
                    VALUES (p_company, p_department, 2)
                    ON CONFLICT (company_id, department_id) DO UPDATE SET next_no = s.next_no + 1
                    RETURNING s.next_no - 1 INTO n;
                RETURN co || '-' || dep || '-'
                       || CASE WHEN n < 100 THEN lpad(n::text, 2, '0') ELSE n::text END;
            END $$;
        GRANT EXECUTE ON FUNCTION core.issue_employee_code(uuid, uuid) TO {APP_ROLES};

        -- Monthly score snapshots for the 12-month trend (§1.16).
        CREATE TABLE core.employee_scores (
            employee_id  uuid NOT NULL REFERENCES core.employees (id),
            company_id   uuid NOT NULL REFERENCES core.companies (id),
            month        date NOT NULL CHECK (date_trunc('month', month) = month),
            value        numeric(4, 2) CHECK (value BETWEEN 0 AND 10),
            components   jsonb NOT NULL DEFAULT '{{}}',
            computed_at  timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (employee_id, month)
        );

        GRANT SELECT ON core.departments, core.employees, core.employee_code_seq,
            core.employee_scores TO {APP_ROLES};
        GRANT INSERT ON core.departments, core.employees TO {APP_ROLES};
        GRANT INSERT, UPDATE ON core.employee_code_seq TO {APP_ROLES};
        GRANT UPDATE (name_fa, name_en, manager_title_fa, manager_title_en, status, sort)
            ON core.departments TO hq_api;
        GRANT UPDATE (display_name, reports_to, status, activity, activity_note, activity_at,
                      dismissed_at, dismissal_reason)
            ON core.employees TO {APP_ROLES};
        GRANT UPDATE (score, score_owner_avg, score_components, rank_in_department,
                      score_updated_at)
            ON core.employees TO {APP_ROLES};
        GRANT INSERT, UPDATE ON core.employee_scores TO {APP_ROLES};

        -- -------------------------------------------------------------- outbox --
        -- Events are written in the same transaction as the change and relayed
        -- to NATS afterwards (at-least-once; Nats-Msg-Id = id dedupes).
        -- Metadata only: never a message body or a secret.
        CREATE TABLE core.outbox (
            id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            event_id      uuid NOT NULL UNIQUE,
            subject       text NOT NULL CHECK (subject ~ '^hq\.core\.[A-Z][A-Z0-9]{{1,9}}\.[a-z_]+\.[a-z_]+$'),
            payload       jsonb NOT NULL,
            created_at    timestamptz NOT NULL DEFAULT now(),
            published_at  timestamptz
        );
        CREATE INDEX outbox_pending ON core.outbox (id) WHERE published_at IS NULL;
        CREATE FUNCTION core.outbox_notify() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                PERFORM pg_notify('hq_outbox', '');
                RETURN NULL;
            END $$;
        CREATE TRIGGER outbox_notify AFTER INSERT ON core.outbox
            FOR EACH STATEMENT EXECUTE FUNCTION core.outbox_notify();
        GRANT SELECT, INSERT ON core.outbox TO {APP_ROLES};
        GRANT UPDATE (published_at) ON core.outbox TO {APP_ROLES};
        GRANT DELETE ON core.outbox TO hq_worker;  -- purge of published rows after 7 days

        -- -------------------------------------------------------- idempotency --
        CREATE TABLE core.idempotency_keys (
            principal    text NOT NULL,
            key          uuid NOT NULL,
            method       text NOT NULL,
            path         text NOT NULL,
            body_sha256  text NOT NULL,
            status_code  int,
            response     jsonb,
            created_at   timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (principal, key)
        );
        GRANT SELECT, INSERT, UPDATE ON core.idempotency_keys TO {APP_ROLES};
        GRANT DELETE ON core.idempotency_keys TO hq_worker;  -- purge after 24 h
        """
    )
    _rls("core", ["departments", "employees", "employee_code_seq", "employee_scores"])


def _rls(schema: str, tables: list[str]) -> None:
    """FORCE RLS: application roles see only permitted companies; hq sees all."""
    execute_script(
        "\n".join(
            f"""
            ALTER TABLE {schema}.{t} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {schema}.{t} FORCE ROW LEVEL SECURITY;
            CREATE POLICY {t}_tenant ON {schema}.{t} TO {APP_ROLES}
                USING (company_id = ANY (core.allowed_company_ids()))
                WITH CHECK (company_id = ANY (core.allowed_company_ids()));
            CREATE POLICY {t}_owner_role ON {schema}.{t} TO hq USING (true) WITH CHECK (true);
            """
            for t in tables
        )
    )


def downgrade() -> None:
    execute_script(
        """
        DROP TABLE core.idempotency_keys, core.outbox, core.employee_scores,
            core.employee_code_seq, core.employees, core.departments, core.counters;
        DROP TRIGGER companies_sync_name ON core.companies;
        DROP TRIGGER companies_immutable ON core.companies;
        DROP TRIGGER companies_version ON core.companies;
        DROP TRIGGER companies_no_delete ON core.companies;
        ALTER TABLE core.companies DROP COLUMN name_fa, DROP COLUMN name_en,
            DROP COLUMN color_index, DROP COLUMN template, DROP COLUMN version,
            DROP COLUMN updated_at;
        DROP FUNCTION core.issue_employee_code(uuid, uuid), core.employees_dismissal_final(),
            core.companies_sync_name(), core.outbox_notify(), core.next_counter(text),
            core.bump_version(), core.keep_immutable(), core.reject_change(),
            core.fa_normalize(text), core.allowed_company_ids();
        """
    )
