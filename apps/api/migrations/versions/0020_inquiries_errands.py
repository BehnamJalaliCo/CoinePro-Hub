"""Prompt 08 §3 and §5 (contract §18.2, §18.3, §18.10): formal inquiries and
the personal assistant's errands.

- oversight.inquiries (Q-0001): a question from the overseer, the advisor or
  a CEO (inside its company) to one employee, with a due time; the answer
  goes to the asker's thread. The row belongs to the asked one's company.
- owner.errands (E-0001): the owner's everyday errands for the assistant,
  with their trail of steps, result and attachments; owner.planner_items:
  the dated reminders the assistant puts in the owner's planner.
- The decision kind `errand_action` (A3): an external commitment of an
  errand (pay, buy, book, sign up, send, a security change).

Revision ID: 0020
Revises: 0018
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0020"
down_revision = "0018"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
KINDS = (
    "'hire', 'dismissal', 'recurring_approval', 'deploy', 'a3_action', 'proposal', "
    "'budget_change', 'evaluation', 'code_session'"
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
        CREATE SCHEMA IF NOT EXISTS oversight;
        GRANT USAGE ON SCHEMA oversight TO {APP_ROLES};

        -- --------------------------------------------------------- inquiries --
        CREATE SEQUENCE oversight.inquiry_ref_seq;
        GRANT USAGE ON SEQUENCE oversight.inquiry_ref_seq TO {APP_ROLES};
        CREATE TABLE oversight.inquiries (
            id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref                text NOT NULL UNIQUE
                                    DEFAULT 'Q-' || lpad(nextval('oversight.inquiry_ref_seq')::text, 4, '0'),
            company_id         uuid NOT NULL REFERENCES core.companies (id),  -- the asked one's
            from_kind          text NOT NULL CHECK (from_kind IN ('owner', 'agent')),
            from_code          text NOT NULL CHECK (length(from_code) BETWEEN 1 AND 64),
            from_company_id    uuid REFERENCES core.companies (id),
            from_rank          int CHECK (from_rank BETWEEN 1 AND 5),
            to_employee_id     uuid NOT NULL REFERENCES core.employees (id),
            to_code            text NOT NULL CHECK (length(to_code) BETWEEN 1 AND 64),
            question_md        text NOT NULL CHECK (length(question_md) BETWEEN 1 AND 20000),
            due_at             timestamptz NOT NULL,
            status             text NOT NULL DEFAULT 'open'
                                    CHECK (status IN ('open', 'answered', 'late', 'withdrawn')),
            answer_md          text CHECK (length(answer_md) <= 50000),
            evidence           jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(evidence) = 'array'),
            answered_at        timestamptz,
            late_at            timestamptz,
            thread_code        text NOT NULL CHECK (length(thread_code) BETWEEN 1 AND 40),
            answer_message_ref text,
            work_id            uuid REFERENCES work.work (id),
            run_id             uuid,
            created_at         timestamptz NOT NULL DEFAULT now(),
            updated_at         timestamptz NOT NULL DEFAULT now(),
            CHECK ((status = 'answered') = (answered_at IS NOT NULL))
        );
        CREATE INDEX inquiries_open ON oversight.inquiries (due_at) WHERE status = 'open';
        CREATE INDEX inquiries_to ON oversight.inquiries (to_employee_id, status);
        CREATE INDEX inquiries_from ON oversight.inquiries (from_code, created_at DESC);
        CREATE TRIGGER inquiries_no_delete BEFORE DELETE ON oversight.inquiries
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER inquiries_immutable BEFORE UPDATE ON oversight.inquiries
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'ref', 'company_id', 'from_kind', 'from_code', 'to_employee_id', 'question_md',
                'created_at');
        GRANT SELECT, INSERT ON oversight.inquiries TO {APP_ROLES};
        GRANT UPDATE (status, answer_md, evidence, answered_at, late_at, answer_message_ref, work_id,
                      updated_at) ON oversight.inquiries TO {APP_ROLES};

        -- ----------------------------------------------------------- errands --
        CREATE SEQUENCE owner.errand_ref_seq;
        GRANT USAGE ON SEQUENCE owner.errand_ref_seq TO {APP_ROLES};
        CREATE TABLE owner.errands (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref          text NOT NULL UNIQUE
                              DEFAULT 'E-' || lpad(nextval('owner.errand_ref_seq')::text, 4, '0'),
            company_id   uuid NOT NULL REFERENCES core.companies (id),  -- the holding
            title_fa     text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
            brief_md     text NOT NULL CHECK (length(brief_md) BETWEEN 1 AND 20000),
            source       text NOT NULL CHECK (source IN ('voice', 'text')),
            file_ids     uuid[] NOT NULL DEFAULT '{{}}' CHECK (cardinality(file_ids) <= 10),
            due_at       timestamptz,
            status       text NOT NULL DEFAULT 'queued'
                              CHECK (status IN ('queued', 'working', 'waiting_owner', 'done', 'failed',
                                                'cancelled')),
            steps        jsonb NOT NULL DEFAULT '[]'
                              CHECK (jsonb_typeof(steps) = 'array' AND jsonb_array_length(steps) <= 200),
            result_md    text CHECK (length(result_md) <= 50000),
            attachments  uuid[] NOT NULL DEFAULT '{{}}' CHECK (cardinality(attachments) <= 20),
            decision_id  uuid REFERENCES cartable.decisions (id),
            message_ref  text,  -- the owner's message that opened it (thread P)
            run_ids      uuid[] NOT NULL DEFAULT '{{}}',
            created_at   timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now(),
            finished_at  timestamptz
        );
        CREATE INDEX errands_at ON owner.errands (created_at DESC);
        CREATE INDEX errands_open ON owner.errands (status) WHERE status IN ('queued', 'working', 'waiting_owner');
        CREATE TRIGGER errands_no_delete BEFORE DELETE ON owner.errands
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER errands_immutable BEFORE UPDATE ON owner.errands
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'created_at');
        GRANT SELECT, INSERT ON owner.errands TO {APP_ROLES};
        GRANT UPDATE (title_fa, status, steps, result_md, attachments, decision_id, message_ref, run_ids,
                      updated_at, finished_at) ON owner.errands TO {APP_ROLES};

        -- The owner's own dated reminders (planner.add): shown by GET /planner
        -- beside the work that is due; they never wake or escalate anyone.
        CREATE SEQUENCE owner.planner_ref_seq;
        GRANT USAGE ON SEQUENCE owner.planner_ref_seq TO {APP_ROLES};
        CREATE TABLE owner.planner_items (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref         text NOT NULL UNIQUE
                             DEFAULT 'PL-' || lpad(nextval('owner.planner_ref_seq')::text, 4, '0'),
            company_id  uuid NOT NULL REFERENCES core.companies (id),  -- the holding
            title_fa    text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
            at          timestamptz NOT NULL,
            note        text CHECK (length(note) <= 2000),
            errand_id   uuid REFERENCES owner.errands (id),
            created_by_kind text NOT NULL CHECK (created_by_kind IN ('owner', 'agent')),
            created_by_code text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
            created_at  timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX planner_items_at ON owner.planner_items (at);
        CREATE TRIGGER planner_items_no_delete BEFORE DELETE ON owner.planner_items
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER planner_items_no_update BEFORE UPDATE ON owner.planner_items
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        GRANT SELECT, INSERT ON owner.planner_items TO {APP_ROLES};

        {_rls(["oversight.inquiries", "owner.errands", "owner.planner_items"])}

        -- ----------------------------------------- decision kind errand_action
        ALTER TABLE cartable.decisions DROP CONSTRAINT decisions_kind_check;
        ALTER TABLE cartable.decisions ADD CONSTRAINT decisions_kind_check
            CHECK (kind IN ({KINDS}, 'errand_action'));
        """
    )


def downgrade() -> None:
    execute_script(
        f"""
        ALTER TABLE cartable.decisions DROP CONSTRAINT decisions_kind_check;
        ALTER TABLE cartable.decisions ADD CONSTRAINT decisions_kind_check
            CHECK (kind IN ({KINDS})) NOT VALID;
        DROP TABLE owner.planner_items;
        DROP SEQUENCE owner.planner_ref_seq;
        DROP TABLE owner.errands;
        DROP SEQUENCE owner.errand_ref_seq;
        DROP TABLE oversight.inquiries;
        DROP SEQUENCE oversight.inquiry_ref_seq;
        """
    )
