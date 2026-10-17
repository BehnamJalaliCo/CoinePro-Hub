"""Prompt 6 §2 (contract §17.1): owner photos, videos, voice and documents.

- files.files (append-only) gains what an upload is: kind (image, video,
  audio, document, other), variant (original, thumb, poster, frame, agent:
  the downscaled image a model sees) with parent_id, width, height,
  duration_s and frame_at_s; a video may be 200 MiB.
- An owner upload belongs to the holding until it is attached in a thread;
  attaching moves it (and its variants) to that thread's company, once:
  files.guard_change() still refuses every other UPDATE and every DELETE.
- files.processing: the mutable part of a video or audio file (status
  processing -> ready | failed, the transcript of its sound and the quality
  log of the punctuation pass), RLS like the file.
- msg.messages: a body may be empty when the message carries attachments.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
MAX_SIZE = 200 * 1024 * 1024


def upgrade() -> None:
    execute_script(
        rf"""
        ALTER TABLE files.files
            ADD COLUMN kind text NOT NULL DEFAULT 'other'
                CHECK (kind IN ('image', 'video', 'audio', 'document', 'other')),
            ADD COLUMN variant text NOT NULL DEFAULT 'original'
                CHECK (variant IN ('original', 'thumb', 'poster', 'frame', 'agent')),
            ADD COLUMN parent_id uuid REFERENCES files.files (id),
            ADD COLUMN width int CHECK (width > 0),
            ADD COLUMN height int CHECK (height > 0),
            ADD COLUMN duration_s numeric(10, 3) CHECK (duration_s >= 0),
            ADD COLUMN frame_at_s numeric(10, 3) CHECK (frame_at_s >= 0),
            ADD CONSTRAINT files_variant_parent CHECK ((variant = 'original') = (parent_id IS NULL));
        ALTER TABLE files.files DROP CONSTRAINT files_size_check;
        ALTER TABLE files.files ADD CONSTRAINT files_size_check CHECK (size BETWEEN 0 AND {MAX_SIZE});
        CREATE INDEX files_parent ON files.files (parent_id) WHERE parent_id IS NOT NULL;

        -- Append-only, except one move: an owner upload (and its variants) from the
        -- holding to the company of the thread it is attached in.
        CREATE FUNCTION files.guard_change() RETURNS trigger
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
        DROP TRIGGER files_append_only ON files.files;
        CREATE TRIGGER files_append_only BEFORE DELETE OR UPDATE ON files.files
            FOR EACH ROW EXECUTE FUNCTION files.guard_change();
        GRANT UPDATE (company_id) ON files.files TO hq_api;

        CREATE TABLE files.processing (
            file_id                uuid PRIMARY KEY REFERENCES files.files (id),
            company_id             uuid NOT NULL REFERENCES core.companies (id),
            status                 text NOT NULL DEFAULT 'processing'
                                        CHECK (status IN ('processing', 'ready', 'failed')),
            transcript             text CHECK (length(transcript) <= 200000),
            transcript_normalised  text CHECK (length(transcript_normalised) <= 200000),
            punctuation            text CHECK (punctuation IN ('accepted', 'rejected', 'off', 'failed')),
            punctuation_edit_ratio numeric(6, 4),
            stt                    jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(stt) = 'object'),
            error                  text CHECK (length(error) <= 300),
            attempts               int NOT NULL DEFAULT 0,
            created_at             timestamptz NOT NULL DEFAULT now(),
            updated_at             timestamptz NOT NULL DEFAULT now()
        );
        COMMENT ON TABLE files.processing IS
            'Mutable state of a video or audio upload; stt = engine, timing and confidence (no audio)';
        ALTER TABLE files.processing ENABLE ROW LEVEL SECURITY;
        ALTER TABLE files.processing FORCE ROW LEVEL SECURITY;
        CREATE POLICY processing_tenant ON files.processing TO {APP_ROLES}
            USING (company_id = ANY ((SELECT core.allowed_company_ids())::uuid[]))
            WITH CHECK (company_id = ANY ((SELECT core.allowed_company_ids())::uuid[]));
        CREATE POLICY processing_owner_role ON files.processing TO hq USING (true) WITH CHECK (true);
        GRANT SELECT, INSERT ON files.processing TO {APP_ROLES};
        GRANT UPDATE (company_id) ON files.processing TO hq_api;
        GRANT UPDATE (status, transcript, transcript_normalised, punctuation, punctuation_edit_ratio, stt,
                      error, attempts, updated_at) ON files.processing TO hq_worker;

        ALTER TABLE msg.messages DROP CONSTRAINT messages_body_check;
        ALTER TABLE msg.messages ADD CONSTRAINT messages_body_check
            CHECK (length(body) <= 100000 AND (length(body) >= 1 OR cardinality(attachments) > 0));
        """
    )


def downgrade() -> None:
    execute_script(
        """
        ALTER TABLE msg.messages DROP CONSTRAINT messages_body_check;
        ALTER TABLE msg.messages ADD CONSTRAINT messages_body_check
            CHECK (length(body) BETWEEN 1 AND 100000) NOT VALID;
        DROP TABLE files.processing;
        DROP TRIGGER files_append_only ON files.files;
        CREATE TRIGGER files_append_only BEFORE DELETE OR UPDATE ON files.files
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        DROP FUNCTION files.guard_change();
        ALTER TABLE files.files DROP CONSTRAINT files_size_check;
        ALTER TABLE files.files ADD CONSTRAINT files_size_check CHECK (size BETWEEN 0 AND 104857600) NOT VALID;
        ALTER TABLE files.files DROP CONSTRAINT files_variant_parent, DROP COLUMN frame_at_s,
            DROP COLUMN duration_s, DROP COLUMN height, DROP COLUMN width, DROP COLUMN parent_id,
            DROP COLUMN variant, DROP COLUMN kind;
        """
    )
