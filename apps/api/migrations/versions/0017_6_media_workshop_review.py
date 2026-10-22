"""Review of prompt 6 (06.1 §2-§3): files and the workshop, in the database.

- files.guard_change(): the one move files.files allows (holding -> the
  company of the thread it is attached in) is for the owner's own uploads
  and the variants the media service made of them; a holding agent's output,
  a workshop transcript or anything else of the holding never moves.
- files.lock_company(file_id): the file's company, its row locked FOR SHARE
  for the rest of the caller's transaction. The worker reads it before it
  stores a variant or announces a result, so an attachment (which locks the
  original FOR UPDATE) either waits for it or is seen by it: no variant stays
  behind in the holding, no file.ready goes to the wrong stream. hq_worker
  may lock no row of files.files otherwise (it has no UPDATE right).
- msg.messages.attachments gets a GIN index: "is this owner upload attached
  anywhere yet" (the holding's agents do not see one that is not).
- workshop.events and workshop.approvals: their company is the session's,
  bound by a foreign key on (session_id, company_id).
- workshop.approvals: one per (session, runtime id): a runtime that replays
  its events (a lost cursor) never makes a second approval for the same ask.

Revision ID: 0017_6
Revises: 0017_4
Create Date: 2026-10-22
"""

from hq_api.migration_sql import execute_script

revision = "0017_6"
down_revision = "0017_4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script(
        """
        CREATE OR REPLACE FUNCTION files.guard_change() RETURNS trigger
            LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            BEGIN
                IF TG_OP = 'UPDATE'
                   AND (to_jsonb(NEW) - 'company_id') = (to_jsonb(OLD) - 'company_id')
                   AND OLD.company_id IS DISTINCT FROM NEW.company_id
                   AND EXISTS (SELECT 1 FROM core.companies WHERE id = OLD.company_id AND kind = 'holding')
                   AND EXISTS (SELECT 1 FROM core.companies WHERE id = NEW.company_id AND kind = 'company')
                   AND ((OLD.variant = 'original' AND OLD.created_by_kind = 'owner')
                        OR (OLD.variant <> 'original' AND OLD.created_by_kind = 'service'
                            AND EXISTS (SELECT 1 FROM files.files p
                                        WHERE p.id = OLD.parent_id AND p.created_by_kind = 'owner')))
                THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'files.files is append-only (% rejected)', TG_OP USING ERRCODE = 'HQA01';
            END $$;

        CREATE FUNCTION files.lock_company(p_file uuid) RETURNS uuid
            LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
                SELECT company_id FROM files.files WHERE id = p_file FOR SHARE
            $$;
        REVOKE ALL ON FUNCTION files.lock_company(uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION files.lock_company(uuid) TO hq_worker;

        CREATE INDEX messages_attachments ON msg.messages USING gin (attachments);

        ALTER TABLE workshop.sessions ADD CONSTRAINT sessions_id_company UNIQUE (id, company_id);
        ALTER TABLE workshop.events ADD CONSTRAINT events_session_company
            FOREIGN KEY (session_id, company_id) REFERENCES workshop.sessions (id, company_id);
        ALTER TABLE workshop.approvals ADD CONSTRAINT approvals_session_company
            FOREIGN KEY (session_id, company_id) REFERENCES workshop.sessions (id, company_id);
        CREATE UNIQUE INDEX approvals_external ON workshop.approvals (session_id, external_id)
            WHERE external_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    execute_script(
        """
        DROP INDEX workshop.approvals_external;
        ALTER TABLE workshop.approvals DROP CONSTRAINT approvals_session_company;
        ALTER TABLE workshop.events DROP CONSTRAINT events_session_company;
        ALTER TABLE workshop.sessions DROP CONSTRAINT sessions_id_company;
        DROP INDEX msg.messages_attachments;
        DROP FUNCTION files.lock_company(uuid);
        CREATE OR REPLACE FUNCTION files.guard_change() RETURNS trigger
            LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            BEGIN
                IF TG_OP = 'UPDATE'
                   AND (to_jsonb(NEW) - 'company_id') = (to_jsonb(OLD) - 'company_id')
                   AND OLD.company_id IS DISTINCT FROM NEW.company_id
                   AND EXISTS (SELECT 1 FROM core.companies WHERE id = OLD.company_id AND kind = 'holding')
                   AND EXISTS (SELECT 1 FROM core.companies WHERE id = NEW.company_id AND kind = 'company')
                THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'files.files is append-only (% rejected)', TG_OP USING ERRCODE = 'HQA01';
            END $$;
        """
    )
