"""Prompt 08 §6-§7 (contract §18.5, §18.6): the skill library and the holding academy.

- knowledge.skills + knowledge.skill_versions: a version is immutable once
  written (a change is a new version); in_review -> the overseer's review ->
  the academy's eval -> approved -> active only with the owner's seal.
- academy.curricula, academy.eval_suites (seeded from agents/academy),
  academy.eval_runs (the gate: score >= baseline - 1), academy.teachings
  (the owner's teaching -> a proposal -> review -> eval -> the owner's
  approval) and academy.addenda: an approved charter rule never edits
  agents/ (read-only); it becomes a sealed addendum after the role's charter.
- agents.runs.skills: the skill versions a run's system prompt carried.
Everything is the holding's (company_id = the holding), with RLS like the rest.

Revision ID: 0022
Revises: 0018
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0022"
down_revision = "0018"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"


def _rls(table: str, name: str) -> str:
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES}
            USING (company_id = ANY ((SELECT core.allowed_company_ids())::uuid[]))
            WITH CHECK (company_id = ANY ((SELECT core.allowed_company_ids())::uuid[]));
        CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
    """


def upgrade() -> None:
    execute_script(
        rf"""
        CREATE SCHEMA IF NOT EXISTS knowledge;
        GRANT USAGE ON SCHEMA knowledge TO {APP_ROLES};
        CREATE SCHEMA academy;
        GRANT USAGE ON SCHEMA academy TO {APP_ROLES};

        -- Skills made in the app start at SK-101 (SK-001..SK-100: the seeds in agents/skills).
        CREATE SEQUENCE knowledge.skill_ref_seq START 101;
        GRANT USAGE ON SEQUENCE knowledge.skill_ref_seq TO hq_api;

        CREATE TABLE knowledge.skills (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      uuid NOT NULL REFERENCES core.companies (id),
            ref             text NOT NULL UNIQUE CHECK (ref ~ '^SK-[0-9]{{3,6}}$'),
            name_fa         text NOT NULL CHECK (length(name_fa) BETWEEN 1 AND 200),
            summary_fa      text NOT NULL CHECK (length(summary_fa) BETWEEN 1 AND 1000),
            scope           jsonb NOT NULL CHECK (jsonb_typeof(scope) = 'object'),
            eval_suite      text CHECK (eval_suite ~ '^EV-[0-9]{{3,6}}$'),
            latest_version  int NOT NULL DEFAULT 1 CHECK (latest_version >= 1),
            active_version  int CHECK (active_version >= 1),
            status          text NOT NULL DEFAULT 'in_review'
                                 CHECK (status IN ('draft', 'in_review', 'approved', 'active', 'retired')),
            source          text NOT NULL CHECK (source IN ('seed', 'text', 'voice', 'file', 'teaching')),
            created_by_kind text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
            created_by_code text NOT NULL CHECK (length(created_by_code) <= 64),
            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now(),
            activated_at    timestamptz
        );
        CREATE TRIGGER skills_immutable BEFORE UPDATE ON knowledge.skills
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'created_at');
        CREATE TRIGGER skills_no_delete BEFORE DELETE ON knowledge.skills
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        {_rls("knowledge.skills", "skills")}
        GRANT SELECT, INSERT, UPDATE ON knowledge.skills TO hq_api;
        GRANT SELECT ON knowledge.skills TO hq_worker;
        GRANT UPDATE (status, updated_at) ON knowledge.skills TO hq_worker;

        CREATE TABLE knowledge.skill_versions (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            skill_id        uuid NOT NULL REFERENCES knowledge.skills (id),
            company_id      uuid NOT NULL REFERENCES core.companies (id),
            version         int NOT NULL CHECK (version >= 1),
            body_md         text NOT NULL CHECK (length(body_md) BETWEEN 1 AND 20000),
            resources       uuid[] NOT NULL DEFAULT '{{}}',
            source          text NOT NULL CHECK (source IN ('seed', 'text', 'voice', 'file', 'teaching')),
            precheck        jsonb NOT NULL CHECK (jsonb_typeof(precheck) = 'object'),
            review          jsonb,
            eval            jsonb,
            status          text NOT NULL DEFAULT 'in_review'
                                 CHECK (status IN ('in_review', 'approved', 'rejected', 'active',
                                                   'retired', 'superseded')),
            created_by_kind text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
            created_by_code text NOT NULL CHECK (length(created_by_code) <= 64),
            created_at      timestamptz NOT NULL DEFAULT now(),
            decided_at      timestamptz,
            UNIQUE (skill_id, version)
        );
        -- What a version says never changes: a change is a new version.
        CREATE TRIGGER skill_versions_immutable BEFORE UPDATE ON knowledge.skill_versions
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'skill_id', 'company_id', 'version', 'body_md', 'resources', 'source',
                'precheck', 'created_by_kind', 'created_by_code', 'created_at');
        CREATE TRIGGER skill_versions_no_delete BEFORE DELETE ON knowledge.skill_versions
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        {_rls("knowledge.skill_versions", "skill_versions")}
        GRANT SELECT, INSERT ON knowledge.skill_versions TO hq_api;
        GRANT UPDATE (review, eval, status, decided_at) ON knowledge.skill_versions TO hq_api;
        GRANT SELECT ON knowledge.skill_versions TO hq_worker;
        GRANT UPDATE (eval, status, decided_at) ON knowledge.skill_versions TO hq_worker;

        CREATE TABLE academy.curricula (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  uuid NOT NULL REFERENCES core.companies (id),
            role        text NOT NULL CHECK (role ~ '^[a-z][a-z0-9_]{{1,40}}$'),
            version     int NOT NULL CHECK (version >= 1),
            modules     jsonb NOT NULL CHECK (jsonb_typeof(modules) = 'array'),
            updated_at  timestamptz NOT NULL DEFAULT now(),
            UNIQUE (role, version)
        );
        CREATE TRIGGER curricula_no_delete BEFORE DELETE ON academy.curricula
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        {_rls("academy.curricula", "curricula")}
        GRANT SELECT, INSERT ON academy.curricula TO hq_api;
        GRANT SELECT ON academy.curricula TO hq_worker;

        CREATE TABLE academy.eval_suites (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  uuid NOT NULL REFERENCES core.companies (id),
            ref         text NOT NULL UNIQUE CHECK (ref ~ '^EV-[0-9]{{3,6}}$'),
            role        text NOT NULL CHECK (role ~ '^[a-z][a-z0-9_]{{1,40}}$'),
            title_fa    text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
            cases       jsonb NOT NULL CHECK (jsonb_typeof(cases) = 'array'),
            baseline    jsonb,  -- {{subject, version, score}}: raised when a version goes live
            updated_at  timestamptz NOT NULL DEFAULT now()
        );
        CREATE TRIGGER eval_suites_immutable BEFORE UPDATE ON academy.eval_suites
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref');
        CREATE TRIGGER eval_suites_no_delete BEFORE DELETE ON academy.eval_suites
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        {_rls("academy.eval_suites", "eval_suites")}
        GRANT SELECT, INSERT ON academy.eval_suites TO hq_api;
        GRANT UPDATE (baseline, updated_at) ON academy.eval_suites TO hq_api;
        GRANT SELECT ON academy.eval_suites TO hq_worker;

        CREATE TABLE academy.teachings (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      uuid NOT NULL REFERENCES core.companies (id),
            ref             text NOT NULL UNIQUE,
            target          jsonb NOT NULL CHECK (jsonb_typeof(target) = 'object'),
            source          text NOT NULL CHECK (source IN ('voice', 'text', 'lesson')),
            text_md         text NOT NULL CHECK (length(text_md) BETWEEN 1 AND 20000),
            file_id         uuid REFERENCES files.files (id),
            lesson_ref      text CHECK (length(lesson_ref) <= 20),
            proposal        jsonb,
            precheck        jsonb,
            review          jsonb,
            eval_run_id     uuid,
            result          jsonb,
            status          text NOT NULL DEFAULT 'drafting'
                                 CHECK (status IN ('drafting', 'proposed', 'approved', 'rejected')),
            work_id         uuid REFERENCES work.work (id),
            created_by_kind text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
            created_by_code text NOT NULL CHECK (length(created_by_code) <= 64),
            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now(),
            decided_at      timestamptz
        );
        CREATE SEQUENCE academy.teaching_ref_seq;
        ALTER TABLE academy.teachings ALTER COLUMN ref
            SET DEFAULT 'TE-' || lpad(nextval('academy.teaching_ref_seq')::text, 4, '0');
        ALTER TABLE academy.teachings ADD CONSTRAINT teachings_ref_check CHECK (ref ~ '^TE-[0-9]{{4,8}}$');
        GRANT USAGE ON SEQUENCE academy.teaching_ref_seq TO hq_api;
        CREATE TRIGGER teachings_immutable BEFORE UPDATE ON academy.teachings
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'company_id', 'ref', 'target', 'source', 'text_md', 'file_id', 'created_at');
        CREATE TRIGGER teachings_no_delete BEFORE DELETE ON academy.teachings
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        {_rls("academy.teachings", "teachings")}
        GRANT SELECT, INSERT, UPDATE ON academy.teachings TO hq_api;
        GRANT SELECT ON academy.teachings TO hq_worker;

        CREATE TABLE academy.eval_runs (
            id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        uuid NOT NULL REFERENCES core.companies (id),
            suite_ref         text NOT NULL REFERENCES academy.eval_suites (ref),
            subject           jsonb NOT NULL CHECK (jsonb_typeof(subject) = 'object'),
            candidate         jsonb,  -- what is under test when it is not live yet (a draft's text)
            purpose           text NOT NULL CHECK (purpose IN ('manual', 'skill', 'teaching')),
            skill_version_id  uuid REFERENCES knowledge.skill_versions (id),
            teaching_id       uuid REFERENCES academy.teachings (id),
            status            text NOT NULL DEFAULT 'queued'
                                   CHECK (status IN ('queued', 'running', 'done', 'failed')),
            score             numeric(5, 2) CHECK (score BETWEEN 0 AND 100),
            passed            boolean,
            gate              jsonb,
            cases             jsonb,
            tokens            bigint NOT NULL DEFAULT 0 CHECK (tokens >= 0),
            error             text CHECK (length(error) <= 300),
            requested_by_kind text NOT NULL CHECK (requested_by_kind IN ('owner', 'agent', 'service')),
            requested_by_code text NOT NULL CHECK (length(requested_by_code) <= 64),
            at                timestamptz NOT NULL DEFAULT now(),
            finished_at       timestamptz
        );
        CREATE INDEX eval_runs_suite_at ON academy.eval_runs (suite_ref, at DESC);
        CREATE TRIGGER eval_runs_immutable BEFORE UPDATE ON academy.eval_runs
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'company_id', 'suite_ref', 'subject', 'candidate', 'purpose',
                'skill_version_id', 'teaching_id', 'requested_by_kind', 'requested_by_code', 'at');
        CREATE TRIGGER eval_runs_no_delete BEFORE DELETE ON academy.eval_runs
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        {_rls("academy.eval_runs", "eval_runs")}
        GRANT SELECT, INSERT ON academy.eval_runs TO hq_api;
        GRANT SELECT ON academy.eval_runs TO hq_worker;
        GRANT UPDATE (status, score, passed, gate, cases, tokens, error, finished_at)
            ON academy.eval_runs TO hq_worker;

        CREATE TABLE academy.addenda (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id   uuid NOT NULL REFERENCES core.companies (id),
            role         text NOT NULL CHECK (role ~ '^[a-z][a-z0-9_]{{1,40}}$'),
            version      int NOT NULL CHECK (version >= 1),
            text_md      text NOT NULL CHECK (length(text_md) BETWEEN 1 AND 8000),
            teaching_id  uuid NOT NULL REFERENCES academy.teachings (id),
            active       boolean NOT NULL DEFAULT true,
            created_at   timestamptz NOT NULL DEFAULT now(),
            UNIQUE (role, version)
        );
        CREATE TRIGGER addenda_immutable BEFORE UPDATE ON academy.addenda
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'company_id', 'role', 'version', 'text_md', 'teaching_id', 'created_at');
        CREATE TRIGGER addenda_no_delete BEFORE DELETE ON academy.addenda
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        {_rls("academy.addenda", "addenda")}
        GRANT SELECT, INSERT ON academy.addenda TO hq_api;
        GRANT UPDATE (active) ON academy.addenda TO hq_api;
        GRANT SELECT ON academy.addenda TO hq_worker;

        ALTER TABLE agents.runs ADD COLUMN skills text[];
        GRANT UPDATE (skills) ON agents.runs TO hq_worker;
        """
    )


def downgrade() -> None:
    execute_script(
        """
        ALTER TABLE agents.runs DROP COLUMN skills;
        DROP SCHEMA academy CASCADE;
        DROP TABLE knowledge.skill_versions;
        DROP TABLE knowledge.skills;
        DROP SEQUENCE knowledge.skill_ref_seq;
        """
    )
