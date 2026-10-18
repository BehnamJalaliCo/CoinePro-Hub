"""Prompt 08 §4, §8, §9 (contract §18.4, §18.11, §18.12): stars, lessons,
delegated hiring and stories.

- people.star_rubrics (one version per company and change; the latest is
  the active one), people.stars (one per employee and week, Saturday in the
  owner's zone; `counted` false without a reason or evidence, or by the
  overseer's audit), people.star_rollups (the holding's weekly and Jalali
  monthly roll-up, a snapshot).
- knowledge.lessons (L-0001, from the best company) and
  knowledge.lesson_adoptions (one per other company: proposed -> adopted |
  rejected, through a `lesson_adoption` decision).
- owner.stories (ST-000001; 24 h live, then the archive; idempotent system
  stories by `event_key`).
- cartable.decisions kind `lesson_adoption`; core.employees.probation_until
  becomes writable (a delegated hire's 7 days).

Revision ID: 0021
Revises: 0020
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
# The kinds after 0020 (prompt 08 merge: 0019 protocol, 0020 errand_action).
KINDS = (
    "'hire', 'dismissal', 'recurring_approval', 'deploy', 'a3_action', 'proposal', "
    "'budget_change', 'evaluation', 'code_session', 'protocol', 'errand_action'"
)


def _rls(table: str) -> str:
    name = table.split(".")[1]
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
        CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
    """


def upgrade() -> None:
    execute_script(
        f"""
        CREATE SCHEMA IF NOT EXISTS people;
        CREATE SCHEMA IF NOT EXISTS knowledge;
        GRANT USAGE ON SCHEMA people, knowledge TO {APP_ROLES};

        -- ------------------------------------------------------------ stars --
        CREATE TABLE people.star_rubrics (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  uuid NOT NULL REFERENCES core.companies (id),
            version     int  NOT NULL CHECK (version >= 1),
            criteria    jsonb NOT NULL CHECK (jsonb_typeof(criteria) = 'array'
                                              AND jsonb_array_length(criteria) BETWEEN 1 AND 12),
            rules_md    text NOT NULL DEFAULT '' CHECK (length(rules_md) <= 10000),
            by_kind     text NOT NULL CHECK (by_kind IN ('agent', 'owner', 'service')),
            by_code     text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64),
            created_at  timestamptz NOT NULL DEFAULT now(),
            UNIQUE (company_id, version)
        );
        CREATE TRIGGER star_rubrics_append_only BEFORE DELETE OR UPDATE ON people.star_rubrics
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        CREATE TABLE people.stars (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      uuid NOT NULL REFERENCES core.companies (id),
            employee_id     uuid NOT NULL REFERENCES core.employees (id),
            week            date NOT NULL CHECK (extract(isodow FROM week) = 6),  -- a Saturday
            stars           numeric(2, 1) NOT NULL CHECK (stars BETWEEN 0 AND 5 AND stars * 2 = round(stars * 2)),
            criteria        jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(criteria) = 'object'),
            reason_md       text NOT NULL DEFAULT '' CHECK (length(reason_md) <= 4000),
            evidence        jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(evidence) = 'array'),
            counted         boolean NOT NULL,
            rubric_version  int,
            by_kind         text NOT NULL CHECK (by_kind IN ('agent', 'owner', 'service')),
            by_code         text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64),
            overseer_note   text CHECK (length(overseer_note) <= 2000),
            audited_by      text CHECK (length(audited_by) <= 64),
            audited_at      timestamptz,
            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now(),
            UNIQUE (employee_id, week)
        );
        CREATE INDEX stars_company_week ON people.stars (company_id, week DESC);
        CREATE TRIGGER stars_keep BEFORE UPDATE ON people.stars
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'company_id', 'employee_id', 'week', 'created_at');

        CREATE TABLE people.star_rollups (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id    uuid NOT NULL REFERENCES core.companies (id),  -- the holding's
            period        text NOT NULL CHECK (period IN ('week', 'month')),
            key           text NOT NULL CHECK (key ~ '^[0-9]{{4}}-[0-9]{{2}}(-[0-9]{{2}})?$'),
            starts_on     date NOT NULL,
            ends_on       date NOT NULL,  -- exclusive
            best_company  text,
            data          jsonb NOT NULL CHECK (jsonb_typeof(data) = 'object'),
            created_at    timestamptz NOT NULL DEFAULT now(),
            UNIQUE (period, key)
        );
        CREATE TRIGGER star_rollups_append_only BEFORE DELETE OR UPDATE ON people.star_rollups
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        -- ---------------------------------------------------------- lessons --
        CREATE SEQUENCE knowledge.lesson_ref_seq;
        GRANT USAGE ON SEQUENCE knowledge.lesson_ref_seq TO {APP_ROLES};
        CREATE TABLE knowledge.lessons (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref         text NOT NULL UNIQUE
                             DEFAULT 'L-' || lpad(nextval('knowledge.lesson_ref_seq')::text, 4, '0'),
            company_id  uuid NOT NULL REFERENCES core.companies (id),  -- the source company
            period      text NOT NULL CHECK (period ~ '^(week|month):[0-9]{{4}}-[0-9]{{2}}(-[0-9]{{2}})?$'),
            title_fa    text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
            body_md     text NOT NULL CHECK (length(body_md) BETWEEN 1 AND 20000),
            evidence    jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(evidence) = 'array'),
            by_kind     text NOT NULL CHECK (by_kind IN ('agent', 'owner', 'service')),
            by_code     text NOT NULL CHECK (length(by_code) BETWEEN 1 AND 64),
            created_at  timestamptz NOT NULL DEFAULT now()
        );
        CREATE TRIGGER lessons_append_only BEFORE DELETE OR UPDATE ON knowledge.lessons
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        CREATE TABLE knowledge.lesson_adoptions (
            lesson_id     uuid NOT NULL REFERENCES knowledge.lessons (id),
            -- the lesson's ref, readable by the adopting company (the lesson row is the source's)
            lesson_ref    text NOT NULL,
            company_id    uuid NOT NULL REFERENCES core.companies (id),  -- the adopting company
            status        text NOT NULL DEFAULT 'proposed'
                               CHECK (status IN ('proposed', 'adopted', 'rejected')),
            work_ref      text,
            decision_ref  text,
            updated_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (lesson_id, company_id)
        );

        -- ---------------------------------------------------------- stories --
        CREATE SEQUENCE owner.story_ref_seq;
        GRANT USAGE ON SEQUENCE owner.story_ref_seq TO {APP_ROLES};
        CREATE TABLE owner.stories (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref           text NOT NULL UNIQUE
                               DEFAULT 'ST-' || lpad(nextval('owner.story_ref_seq')::text, 6, '0'),
            company_id    uuid NOT NULL REFERENCES core.companies (id),
            kind          text NOT NULL CHECK (kind IN ('hire', 'deliverable', 'stars', 'milestone', 'post')),
            author_kind   text NOT NULL CHECK (author_kind IN ('agent', 'service')),
            author_code   text NOT NULL CHECK (length(author_code) BETWEEN 1 AND 64),
            title_fa      text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 60),
            body_fa       text NOT NULL DEFAULT '' CHECK (length(body_fa) <= 280),
            figures       jsonb NOT NULL DEFAULT '[]'
                               CHECK (jsonb_typeof(figures) = 'array' AND jsonb_array_length(figures) <= 3),
            media_file_id uuid REFERENCES files.files (id),
            links         jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(links) = 'object'),
            event_key     text UNIQUE CHECK (length(event_key) <= 120),  -- system stories: once per event
            created_at    timestamptz NOT NULL DEFAULT now(),
            expires_at    timestamptz NOT NULL DEFAULT now() + interval '24 hours',
            seen_at       timestamptz,
            welcomed_at   timestamptz
        );
        CREATE INDEX stories_live ON owner.stories (company_id, created_at);
        CREATE TRIGGER stories_keep BEFORE UPDATE ON owner.stories
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'ref', 'company_id', 'kind', 'author_kind', 'author_code', 'title_fa', 'body_fa',
                'figures', 'media_file_id', 'links', 'event_key', 'created_at', 'expires_at');

        {_rls("people.star_rubrics")}
        {_rls("people.stars")}
        {_rls("people.star_rollups")}
        {_rls("knowledge.lessons")}
        {_rls("knowledge.lesson_adoptions")}
        {_rls("owner.stories")}

        GRANT SELECT, INSERT ON people.star_rubrics, people.stars, people.star_rollups,
            knowledge.lessons, knowledge.lesson_adoptions, owner.stories TO {APP_ROLES};
        GRANT UPDATE (stars, criteria, reason_md, evidence, counted, rubric_version, by_kind, by_code,
                      overseer_note, audited_by, audited_at, updated_at)
            ON people.stars TO {APP_ROLES};
        GRANT UPDATE (status, work_ref, decision_ref, updated_at)
            ON knowledge.lesson_adoptions TO {APP_ROLES};
        GRANT UPDATE (seen_at, welcomed_at) ON owner.stories TO hq_api;

        -- The hiring mode for any caller (an agent's company-scoped transaction
        -- cannot see the holding's row): NULL while closed.
        CREATE FUNCTION core.hiring_mode() RETURNS text
            LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
                SELECT h.mode FROM core.hiring h JOIN core.companies c ON c.id = h.company_id
                 WHERE c.kind = 'holding' AND h.state = 'open'
            $$;
        REVOKE ALL ON FUNCTION core.hiring_mode() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION core.hiring_mode() TO {APP_ROLES};

        -- Whether a week is rolled up already (a CEO's company-scoped
        -- transaction cannot see the holding's roll-up rows).
        CREATE FUNCTION people.week_rolled_up(p_week date) RETURNS boolean
            LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
                SELECT EXISTS (SELECT 1 FROM people.star_rollups
                                WHERE period = 'week' AND key = to_char(p_week, 'YYYY-MM-DD'))
            $$;
        REVOKE ALL ON FUNCTION people.week_rolled_up(date) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION people.week_rolled_up(date) TO {APP_ROLES};

        -- A delegated hire starts on probation (+7 days, contract §18.11).
        GRANT UPDATE (probation_until) ON core.employees TO {APP_ROLES};

        ALTER TABLE cartable.decisions DROP CONSTRAINT decisions_kind_check;
        ALTER TABLE cartable.decisions ADD CONSTRAINT decisions_kind_check
            CHECK (kind IN ({KINDS}, 'lesson_adoption')) NOT VALID;  -- 0023 validates
        """
    )


def downgrade() -> None:
    execute_script(
        f"""
        -- NOT VALID: past lesson_adoption cards stay (resolutions point at them); new ones are refused.
        ALTER TABLE cartable.decisions DROP CONSTRAINT decisions_kind_check;
        ALTER TABLE cartable.decisions ADD CONSTRAINT decisions_kind_check
            CHECK (kind IN ({KINDS})) NOT VALID;
        REVOKE UPDATE (probation_until) ON core.employees FROM {APP_ROLES};
        DROP FUNCTION core.hiring_mode();
        DROP TABLE owner.stories;
        DROP SEQUENCE owner.story_ref_seq;
        DROP TABLE knowledge.lesson_adoptions;
        DROP TABLE knowledge.lessons;
        DROP SEQUENCE knowledge.lesson_ref_seq;
        DROP FUNCTION people.week_rolled_up(date);
        DROP TABLE people.star_rollups;
        DROP TABLE people.stars;
        DROP TABLE people.star_rubrics;
        DROP SCHEMA people;
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'knowledge') THEN
                DROP SCHEMA knowledge;
            END IF;
        END $$;
        """
    )
