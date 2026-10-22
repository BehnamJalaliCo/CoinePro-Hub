"""Prompt 08 §2 (contract §18.1): the Chief Overseer.

- oversight.protocols: the overseer's written duties (PR-001...), one row per
  version (append-only: an edit, a pause or a resume is a new version, sealed
  by the owner or by a `protocol` decision); seeded from agents/protocols.
- oversight.protocol_runs: one scheduled run of a protocol; rule-based ones
  are checked by code (no model), the others become the overseer's work.
- oversight.findings (FI-0001) + finding_history (append-only): what a run or
  an agent found, who answers for it, until it is verified (evidence) and closed.
- oversight.challenges (CH-0001): the overseer's challenge to a company.
- oversight.orders (SO-001): the owner's standing orders (sealed: in the
  overseer's system prompt, or every role's).
- oversight.holds (H-0001): an action stopped until the owner decides; one
  open hold per target.
- oversight.compliance: one score per company and day.
- oversight.watch: the periods of watch mode with the "while you were away"
  report.
Also owner.settings.watch_after_hours (default 6) and the decision kind
`protocol` (A1, sealed by the owner).

Revision ID: 0019
Revises: 0018
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
# The kinds after 0017_6 (0017_4 adds tool_enable).
KINDS = (
    "'hire', 'dismissal', 'recurring_approval', 'deploy', 'a3_action', 'proposal', "
    "'budget_change', 'evaluation', 'code_session', 'tool_enable'"
)
AREAS = (
    "'truth', 'authority', 'money', 'safety', 'quality', 'delivery', 'security', 'data', "
    "'people', 'product', 'owner'"
)
METHODS = "'rule', 'sample', 'llm', 'reconcile', 'blind_test', 'mystery', 'drill'"
SEVERITIES = "'info', 'low', 'medium', 'high', 'critical'"
TABLES = [
    "oversight.protocols",
    "oversight.protocol_runs",
    "oversight.findings",
    "oversight.finding_history",
    "oversight.challenges",
    "oversight.orders",
    "oversight.holds",
    "oversight.compliance",
    "oversight.watch",
]


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
        CREATE SCHEMA IF NOT EXISTS oversight;
        GRANT USAGE ON SCHEMA oversight TO {APP_ROLES};

        CREATE SEQUENCE oversight.finding_ref_seq;
        CREATE SEQUENCE oversight.challenge_ref_seq;
        CREATE SEQUENCE oversight.order_ref_seq;
        CREATE SEQUENCE oversight.hold_ref_seq;
        GRANT USAGE ON SEQUENCE oversight.finding_ref_seq, oversight.challenge_ref_seq,
            oversight.order_ref_seq, oversight.hold_ref_seq TO {APP_ROLES};

        -- ------------------------------------------------------ protocols --
        CREATE TABLE oversight.protocols (
            id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id         uuid NOT NULL REFERENCES core.companies (id),
            ref                text NOT NULL CHECK (ref ~ '^PR-[0-9]{{3,}}$'),
            version            int NOT NULL CHECK (version >= 1),
            title_fa           text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
            area               text NOT NULL CHECK (area IN ({AREAS})),
            check_md           text NOT NULL CHECK (length(check_md) BETWEEN 1 AND 20000),
            method             text NOT NULL CHECK (method IN ({METHODS})),
            schedule           text NOT NULL CHECK (length(schedule) BETWEEN 6 AND 200),
            scope              text NOT NULL CHECK (scope IN ('holding', 'company', 'department')),
            evidence_md        text NOT NULL DEFAULT '' CHECK (length(evidence_md) <= 5000),
            severity           text NOT NULL CHECK (severity IN ({SEVERITIES})),
            answerable         text NOT NULL CHECK (answerable ~ '^[a-z][a-z0-9_]{{1,40}}$'),
            status             text NOT NULL CHECK (status IN ('active', 'paused', 'draft')),
            source             text NOT NULL CHECK (source IN ('seed', 'owner', 'decision')),
            sealed_at          timestamptz,
            sealed_step_up_id  uuid,
            decision_id        uuid REFERENCES cartable.decisions (id),
            created_by_kind    text NOT NULL CHECK (created_by_kind IN ('owner', 'service')),
            created_by_code    text NOT NULL,
            created_at         timestamptz NOT NULL DEFAULT now(),
            UNIQUE (ref, version),
            CHECK (source = 'seed' OR sealed_at IS NOT NULL)
        );
        CREATE TRIGGER protocols_append_only BEFORE UPDATE OR DELETE ON oversight.protocols
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        -- The protocol in force: its newest version.
        CREATE VIEW oversight.current_protocols WITH (security_invoker = true) AS
            SELECT DISTINCT ON (ref) * FROM oversight.protocols ORDER BY ref, version DESC;

        CREATE TABLE oversight.protocol_runs (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id    uuid NOT NULL REFERENCES core.companies (id),
            protocol_id   uuid NOT NULL REFERENCES oversight.protocols (id),
            protocol_ref  text NOT NULL,
            version       int NOT NULL,
            method        text NOT NULL,
            started_at    timestamptz NOT NULL DEFAULT now(),
            finished_at   timestamptz,
            result        text NOT NULL DEFAULT 'pending'
                               -- deferred: the oversight share was spent (contract §18.1 v1.4.4)
                               CHECK (result IN ('pending', 'pass', 'fail', 'partial', 'skipped', 'deferred')),
            by_kind       text NOT NULL CHECK (by_kind IN ('system', 'agent')),
            by_code       text NOT NULL,
            findings      int NOT NULL DEFAULT 0 CHECK (findings >= 0),
            per_company   jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(per_company) = 'object'),
            notes         text NOT NULL DEFAULT '' CHECK (length(notes) <= 20000),
            work_id       uuid REFERENCES work.work (id),
            CHECK ((result = 'pending') = (finished_at IS NULL))
        );
        CREATE INDEX protocol_runs_ref ON oversight.protocol_runs (protocol_ref, started_at DESC);
        CREATE INDEX protocol_runs_work ON oversight.protocol_runs (work_id) WHERE work_id IS NOT NULL;
        CREATE TRIGGER protocol_runs_no_delete BEFORE DELETE ON oversight.protocol_runs
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        -- ------------------------------------------------------- findings --
        CREATE TABLE oversight.findings (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref              text NOT NULL UNIQUE
                                  DEFAULT 'FI-' || lpad(nextval('oversight.finding_ref_seq')::text, 4, '0'),
            company_id       uuid NOT NULL REFERENCES core.companies (id),
            protocol_id      uuid REFERENCES oversight.protocols (id),
            run_id           uuid REFERENCES oversight.protocol_runs (id),
            severity         text NOT NULL CHECK (severity IN ({SEVERITIES})),
            title_fa         text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
            body_md          text NOT NULL DEFAULT '' CHECK (length(body_md) <= 20000),
            evidence         jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(evidence) = 'array'),
            status           text NOT NULL DEFAULT 'open'
                                  CHECK (status IN ('open', 'acknowledged', 'fixing', 'fixed', 'verified',
                                                    'disputed', 'closed')),
            answerable_kind  text NOT NULL CHECK (answerable_kind IN ('owner', 'agent')),
            answerable_code  text NOT NULL CHECK (length(answerable_code) BETWEEN 1 AND 64),
            raised_by_kind   text NOT NULL CHECK (raised_by_kind IN ('system', 'agent', 'owner')),
            raised_by_code   text NOT NULL,
            dedupe_key       text CHECK (length(dedupe_key) <= 200),
            due_at           timestamptz NOT NULL,
            opened_at        timestamptz NOT NULL DEFAULT now(),
            closed_at        timestamptz,
            version          int NOT NULL DEFAULT 1,
            updated_at       timestamptz NOT NULL DEFAULT now(),
            CHECK ((status = 'closed') = (closed_at IS NOT NULL))
        );
        CREATE INDEX findings_company ON oversight.findings (company_id, status, severity);
        -- A rule found again while its finding is still open is the same finding.
        CREATE UNIQUE INDEX findings_open_once ON oversight.findings (company_id, dedupe_key)
            WHERE dedupe_key IS NOT NULL AND status NOT IN ('verified', 'closed');
        CREATE TRIGGER findings_immutable BEFORE UPDATE ON oversight.findings
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'ref', 'company_id', 'protocol_id', 'run_id', 'severity', 'title_fa', 'body_md',
                'raised_by_kind', 'raised_by_code', 'dedupe_key', 'opened_at');
        CREATE TRIGGER findings_version BEFORE UPDATE ON oversight.findings
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();
        CREATE TRIGGER findings_no_delete BEFORE DELETE ON oversight.findings
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        CREATE TABLE oversight.finding_history (
            id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            finding_id  uuid NOT NULL REFERENCES oversight.findings (id),
            company_id  uuid NOT NULL REFERENCES core.companies (id),
            at          timestamptz NOT NULL DEFAULT now(),
            by_kind     text NOT NULL CHECK (by_kind IN ('system', 'agent', 'owner')),
            by_code     text NOT NULL,
            status      text NOT NULL,
            note        text NOT NULL DEFAULT '' CHECK (length(note) <= 5000),
            evidence    jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(evidence) = 'array')
        );
        CREATE INDEX finding_history_finding ON oversight.finding_history (finding_id, at);
        CREATE TRIGGER finding_history_append_only BEFORE UPDATE OR DELETE ON oversight.finding_history
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        -- ----------------------------------------------------- challenges --
        CREATE TABLE oversight.challenges (
            id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref            text NOT NULL UNIQUE
                                DEFAULT 'CH-' || lpad(nextval('oversight.challenge_ref_seq')::text, 4, '0'),
            company_id     uuid NOT NULL REFERENCES core.companies (id),
            period         text NOT NULL CHECK (period IN ('week', 'month')),
            period_key     date NOT NULL,  -- the week's Saturday or the month's first day (owner TZ)
            title_fa       text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
            brief_md       text NOT NULL DEFAULT '' CHECK (length(brief_md) <= 20000),
            criteria       jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(criteria) = 'array'),
            due_at         timestamptz NOT NULL,
            status         text NOT NULL DEFAULT 'issued'
                                CHECK (status IN ('issued', 'accepted', 'submitted', 'scored', 'missed')),
            score          int CHECK (score BETWEEN 0 AND 100),
            judge_kind     text NOT NULL CHECK (judge_kind IN ('owner', 'agent')),
            judge_code     text NOT NULL,
            issued_by_code text NOT NULL,
            work_id        uuid REFERENCES work.work (id),
            submit_note    text NOT NULL DEFAULT '' CHECK (length(submit_note) <= 5000),
            score_notes    text NOT NULL DEFAULT '' CHECK (length(score_notes) <= 5000),
            submitted_at   timestamptz,
            scored_at      timestamptz,
            created_at     timestamptz NOT NULL DEFAULT now(),
            version        int NOT NULL DEFAULT 1,
            updated_at     timestamptz NOT NULL DEFAULT now(),
            CHECK ((status = 'scored') = (score IS NOT NULL))
        );
        CREATE INDEX challenges_company ON oversight.challenges (company_id, period_key DESC);
        CREATE TRIGGER challenges_immutable BEFORE UPDATE ON oversight.challenges
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'ref', 'company_id', 'period', 'period_key', 'title_fa', 'brief_md', 'criteria',
                'judge_kind', 'judge_code', 'issued_by_code', 'created_at');
        CREATE TRIGGER challenges_version BEFORE UPDATE ON oversight.challenges
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();
        CREATE TRIGGER challenges_no_delete BEFORE DELETE ON oversight.challenges
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        -- ------------------------------------------------- standing orders --
        CREATE TABLE oversight.orders (
            id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref                text NOT NULL UNIQUE
                                    DEFAULT 'SO-' || lpad(nextval('oversight.order_ref_seq')::text, 3, '0'),
            company_id         uuid NOT NULL REFERENCES core.companies (id),
            text_md            text NOT NULL CHECK (length(text_md) BETWEEN 1 AND 10000),
            source             text NOT NULL CHECK (source IN ('voice', 'text')),
            file_id            uuid REFERENCES files.files (id),
            applies_to         text NOT NULL CHECK (applies_to IN ('overseer', 'all')),
            status             text NOT NULL DEFAULT 'proposed'
                                    CHECK (status IN ('proposed', 'sealed', 'retired')),
            sealed_at          timestamptz,
            sealed_step_up_id  uuid,
            retired_at         timestamptz,
            created_by_kind    text NOT NULL CHECK (created_by_kind IN ('owner', 'agent')),
            created_by_code    text NOT NULL,
            created_at         timestamptz NOT NULL DEFAULT now(),
            version            int NOT NULL DEFAULT 1,
            updated_at         timestamptz NOT NULL DEFAULT now(),
            CHECK ((status = 'proposed') OR sealed_at IS NOT NULL OR retired_at IS NOT NULL)
        );
        CREATE TRIGGER orders_immutable BEFORE UPDATE ON oversight.orders
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'ref', 'company_id', 'text_md', 'source', 'file_id', 'applies_to',
                'created_by_kind', 'created_by_code', 'created_at');
        CREATE TRIGGER orders_version BEFORE UPDATE ON oversight.orders
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();
        CREATE TRIGGER orders_no_delete BEFORE DELETE ON oversight.orders
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        -- ----------------------------------------------------------- holds --
        CREATE TABLE oversight.holds (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref              text NOT NULL UNIQUE
                                  DEFAULT 'H-' || lpad(nextval('oversight.hold_ref_seq')::text, 4, '0'),
            company_id       uuid NOT NULL REFERENCES core.companies (id),
            target_kind      text NOT NULL
                                  CHECK (target_kind IN ('decision', 'session', 'work', 'employee', 'tool',
                                                         'story')),
            target_ref       text NOT NULL CHECK (length(target_ref) BETWEEN 1 AND 120),
            summary_fa       text NOT NULL DEFAULT '' CHECK (length(summary_fa) <= 500),
            payload_digest   text CHECK (payload_digest ~ '^[0-9a-f]{{64}}$'),
            reason_md        text NOT NULL CHECK (length(reason_md) BETWEEN 1 AND 5000),
            held_by_kind     text NOT NULL CHECK (held_by_kind IN ('agent', 'system')),
            held_by_code     text NOT NULL,
            held_at          timestamptz NOT NULL DEFAULT now(),
            watch            boolean NOT NULL DEFAULT false,
            state            text NOT NULL DEFAULT 'held' CHECK (state IN ('held', 'released', 'cancelled')),
            decided_by_kind  text CHECK (decided_by_kind IN ('owner')),
            decided_by_code  text,
            decided_at       timestamptz,
            decision_note    text CHECK (length(decision_note) <= 2000),
            step_up_id       uuid,
            version          int NOT NULL DEFAULT 1,
            updated_at       timestamptz NOT NULL DEFAULT now(),
            CHECK ((state = 'held') = (decided_at IS NULL))
        );
        CREATE UNIQUE INDEX holds_open_once ON oversight.holds (target_kind, target_ref)
            WHERE state = 'held';
        CREATE INDEX holds_state ON oversight.holds (state, held_at DESC);
        CREATE FUNCTION oversight.holds_final() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF OLD.state <> 'held' AND NEW.state <> OLD.state THEN
                    RAISE EXCEPTION 'hold % is already %', OLD.ref, OLD.state USING ERRCODE = 'HQS01';
                END IF;
                NEW.updated_at := now();
                RETURN NEW;
            END $$;
        CREATE TRIGGER holds_final BEFORE UPDATE ON oversight.holds
            FOR EACH ROW EXECUTE FUNCTION oversight.holds_final();
        CREATE TRIGGER holds_immutable BEFORE UPDATE ON oversight.holds
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'ref', 'company_id', 'target_kind', 'target_ref', 'summary_fa', 'payload_digest',
                'reason_md', 'held_by_kind', 'held_by_code', 'held_at', 'watch');
        CREATE TRIGGER holds_version BEFORE UPDATE ON oversight.holds
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();
        CREATE TRIGGER holds_no_delete BEFORE DELETE ON oversight.holds
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        -- ------------------------------------------------------ compliance --
        CREATE TABLE oversight.compliance (
            company_id     uuid NOT NULL REFERENCES core.companies (id),
            day            date NOT NULL,
            score          numeric(5, 2) NOT NULL CHECK (score BETWEEN 0 AND 100),
            by_area        jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(by_area) = 'object'),
            findings_open  jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(findings_open) = 'object'),
            protocols      jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(protocols) = 'object'),
            computed_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, day)
        );

        -- ----------------------------------------------------------- watch --
        CREATE TABLE oversight.watch (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  uuid NOT NULL REFERENCES core.companies (id),
            reason      text NOT NULL CHECK (reason IN ('khalvat', 'inactivity', 'owner')),
            since       timestamptz NOT NULL DEFAULT now(),
            until       timestamptz,
            summary_md  text NOT NULL DEFAULT '' CHECK (length(summary_md) <= 20000),
            report      jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(report) = 'object'),
            report_at   timestamptz,
            CHECK (until IS NULL OR until >= since)
        );
        CREATE UNIQUE INDEX watch_one_open ON oversight.watch ((true)) WHERE until IS NULL;
        -- Whether watch mode is on, for every company's transaction (a card of
        -- any company is held while the owner is away); nothing else of the
        -- watch rows is shown.
        CREATE FUNCTION oversight.watch_on() RETURNS boolean
            LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
                SELECT EXISTS (SELECT 1 FROM oversight.watch WHERE until IS NULL)
            $$;
        REVOKE ALL ON FUNCTION oversight.watch_on() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION oversight.watch_on() TO {APP_ROLES};
        CREATE TRIGGER watch_no_delete BEFORE DELETE ON oversight.watch
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        -- ----------------------------------------------------------- grants --
        GRANT SELECT ON oversight.protocols, oversight.current_protocols, oversight.protocol_runs,
            oversight.findings, oversight.finding_history, oversight.challenges, oversight.orders,
            oversight.holds, oversight.compliance, oversight.watch TO {APP_ROLES};
        GRANT INSERT ON oversight.protocols TO {APP_ROLES};
        GRANT INSERT ON oversight.protocol_runs TO {APP_ROLES};
        GRANT UPDATE (finished_at, result, findings, per_company, notes, work_id, by_kind, by_code)
            ON oversight.protocol_runs TO {APP_ROLES};
        GRANT INSERT ON oversight.findings, oversight.finding_history TO {APP_ROLES};
        GRANT UPDATE (status, evidence, answerable_kind, answerable_code, due_at, closed_at, updated_at)
            ON oversight.findings TO {APP_ROLES};
        GRANT INSERT ON oversight.challenges TO {APP_ROLES};
        GRANT UPDATE (status, score, work_id, submit_note, score_notes, submitted_at, scored_at, updated_at)
            ON oversight.challenges TO {APP_ROLES};
        GRANT INSERT ON oversight.orders TO hq_api;
        GRANT UPDATE (status, sealed_at, sealed_step_up_id, retired_at, updated_at)
            ON oversight.orders TO hq_api;
        GRANT INSERT ON oversight.holds TO {APP_ROLES};
        GRANT UPDATE (state, decided_by_kind, decided_by_code, decided_at, decision_note, step_up_id,
                      updated_at)
            ON oversight.holds TO hq_api;
        GRANT INSERT, UPDATE ON oversight.compliance TO hq_worker;
        GRANT INSERT ON oversight.watch TO {APP_ROLES};
        GRANT UPDATE (until, summary_md, report, report_at) ON oversight.watch TO {APP_ROLES};

        {_rls(TABLES)}

        -- ------------------------------------------------- owner settings --
        ALTER TABLE owner.settings
            ADD COLUMN watch_after_hours int NOT NULL DEFAULT 6 CHECK (watch_after_hours BETWEEN 1 AND 72);
        GRANT UPDATE (watch_after_hours) ON owner.settings TO hq_api;

        -- --------------------------------------------- decision kind protocol
        ALTER TABLE cartable.decisions DROP CONSTRAINT decisions_kind_check;
        ALTER TABLE cartable.decisions ADD CONSTRAINT decisions_kind_check
            CHECK (kind IN ({KINDS}, 'protocol')) NOT VALID;  -- 0023 validates
        """
    )


def downgrade() -> None:
    execute_script(
        f"""
        ALTER TABLE cartable.decisions DROP CONSTRAINT decisions_kind_check;
        ALTER TABLE cartable.decisions ADD CONSTRAINT decisions_kind_check
            CHECK (kind IN ({KINDS})) NOT VALID;
        ALTER TABLE owner.settings DROP COLUMN watch_after_hours;
        DROP FUNCTION oversight.watch_on();
        DROP VIEW oversight.current_protocols;
        DROP TABLE oversight.watch, oversight.compliance, oversight.holds, oversight.orders,
            oversight.challenges, oversight.finding_history, oversight.findings,
            oversight.protocol_runs, oversight.protocols;
        DROP SEQUENCE oversight.finding_ref_seq, oversight.challenge_ref_seq,
            oversight.order_ref_seq, oversight.hold_ref_seq;
        DROP FUNCTION oversight.holds_final();
        -- The schema is shared with the inquiries (prompt 08 §3): only when empty.
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                           WHERE n.nspname = 'oversight') THEN
                DROP SCHEMA oversight;
            END IF;
        END $$;
        """
    )
