"""Prompt 9.1 §1 (contract §18.14): the company's brand and seal as data.

- org.company_brands: one row per version of a company's mark (and
  wordmark), traced by code from the owner's logo or seeded from the design
  files. Append-only except its state: while a version is `processing` the
  worker fills what it traced; after that only `state` moves (proposed ->
  active -> retired, processing -> failed) with its time stamps. Never
  deleted. At most one `active` version per company.
- `digest` is what the owner's seal is bound to (sha256 of the canonical JSON
  of mark, wordmark, ink, accent, accent_night, accent_day); the api
  recomputes it from the row at activation.
- Company.brand_version and Founding.brand are read from here (no copy on
  core.companies to drift).
The seed of the existing companies runs with the YAML seed (hq_api.migrate),
from the folders of design/brand/companies/: no company code is written here.

Revision ID: 0024
Revises: 0023
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
HEX = "'^#[0-9A-F]{6}$'"


def upgrade() -> None:
    execute_script(
        f"""
        CREATE SCHEMA IF NOT EXISTS org;
        GRANT USAGE ON SCHEMA org TO {APP_ROLES};

        CREATE TABLE org.company_brands (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       uuid NOT NULL REFERENCES core.companies (id),
            version          int NOT NULL CHECK (version >= 1),
            state            text NOT NULL DEFAULT 'processing'
                                  CHECK (state IN ('processing', 'proposed', 'active', 'failed', 'retired')),
            -- which part this version traced (the other is carried over from the active one)
            part             text NOT NULL CHECK (part IN ('mark', 'wordmark')),
            source           jsonb NOT NULL CHECK (source->>'kind' IN ('upload', 'seed')),
            file_id          uuid REFERENCES files.files (id),
            mark             jsonb CHECK (mark IS NULL OR jsonb_typeof(mark->'layers') = 'array'),
            wordmark         jsonb CHECK (wordmark IS NULL OR jsonb_typeof(wordmark->'layers') = 'array'),
            ink              text NOT NULL DEFAULT '#111216' CHECK (ink ~ {HEX}),
            accent           text CHECK (accent ~ {HEX}),
            accent_night     text CHECK (accent_night ~ {HEX}),
            accent_day       text CHECK (accent_day ~ {HEX}),
            palette          jsonb NOT NULL DEFAULT '[]'
                                  CHECK (jsonb_typeof(palette) = 'array' AND jsonb_array_length(palette) <= 6),
            options          jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(options) = 'object'),
            checks           jsonb CHECK (checks IS NULL OR jsonb_typeof(checks) = 'object'),
            digest           text CHECK (digest ~ '^[0-9a-f]{{64}}$'),
            status_reason    text CHECK (length(status_reason) <= 40),
            attempts         int NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            step_up_id       uuid,
            created_by_kind  text NOT NULL CHECK (created_by_kind IN ('owner', 'service')),
            created_by_code  text NOT NULL CHECK (length(created_by_code) <= 40),
            created_at       timestamptz NOT NULL DEFAULT now(),
            updated_at       timestamptz NOT NULL DEFAULT now(),
            activated_at     timestamptz,
            retired_at       timestamptz,
            UNIQUE (company_id, version),
            CHECK (state NOT IN ('proposed', 'active', 'retired')
                   OR (digest IS NOT NULL AND (mark IS NOT NULL OR wordmark IS NOT NULL))),
            CHECK (state <> 'active' OR mark IS NOT NULL),
            CHECK (state <> 'failed' OR status_reason IS NOT NULL)
        );
        CREATE UNIQUE INDEX company_brands_one_active ON org.company_brands (company_id)
            WHERE state = 'active';
        CREATE INDEX company_brands_processing ON org.company_brands (updated_at)
            WHERE state = 'processing';

        -- Append-only except the state (prompt 9.1 §1): what was traced is
        -- written once, while the version is still processing.
        CREATE FUNCTION org.company_brands_guard() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.id <> OLD.id OR NEW.company_id <> OLD.company_id OR NEW.version <> OLD.version
                   OR NEW.part <> OLD.part OR NEW.file_id IS DISTINCT FROM OLD.file_id
                   OR NEW.created_by_kind <> OLD.created_by_kind OR NEW.created_by_code <> OLD.created_by_code
                   OR NEW.created_at <> OLD.created_at THEN
                    RAISE EXCEPTION 'org.company_brands: identity columns are immutable' USING ERRCODE = 'HQI01';
                END IF;
                IF OLD.state <> 'processing' AND (
                       NEW.source IS DISTINCT FROM OLD.source OR NEW.mark IS DISTINCT FROM OLD.mark
                    OR NEW.wordmark IS DISTINCT FROM OLD.wordmark OR NEW.ink IS DISTINCT FROM OLD.ink
                    OR NEW.accent IS DISTINCT FROM OLD.accent OR NEW.accent_night IS DISTINCT FROM OLD.accent_night
                    OR NEW.accent_day IS DISTINCT FROM OLD.accent_day OR NEW.palette IS DISTINCT FROM OLD.palette
                    OR NEW.options IS DISTINCT FROM OLD.options OR NEW.checks IS DISTINCT FROM OLD.checks
                    OR NEW.digest IS DISTINCT FROM OLD.digest
                    OR NEW.status_reason IS DISTINCT FROM OLD.status_reason) THEN
                    RAISE EXCEPTION 'org.company_brands: version % is % (append-only except its state)',
                        OLD.version, OLD.state USING ERRCODE = 'HQA01';
                END IF;
                IF NEW.state <> OLD.state AND NOT (
                       (OLD.state = 'processing' AND NEW.state IN ('proposed', 'failed'))
                    OR (OLD.state = 'proposed' AND NEW.state = 'active')
                    OR (OLD.state = 'retired' AND NEW.state = 'active')
                    OR (OLD.state = 'active' AND NEW.state = 'retired')) THEN
                    RAISE EXCEPTION 'org.company_brands: % -> % is not a move', OLD.state, NEW.state
                        USING ERRCODE = 'HQA01';
                END IF;
                RETURN NEW;
            END $$;
        CREATE TRIGGER company_brands_guard BEFORE UPDATE ON org.company_brands
            FOR EACH ROW EXECUTE FUNCTION org.company_brands_guard();
        CREATE TRIGGER company_brands_no_delete BEFORE DELETE ON org.company_brands
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        ALTER TABLE org.company_brands ENABLE ROW LEVEL SECURITY;
        ALTER TABLE org.company_brands FORCE ROW LEVEL SECURITY;
        CREATE POLICY company_brands_tenant ON org.company_brands TO {APP_ROLES}
            USING ({TENANT}) WITH CHECK ({TENANT});
        CREATE POLICY company_brands_owner_role ON org.company_brands TO hq USING (true) WITH CHECK (true);

        GRANT SELECT, INSERT ON org.company_brands TO {APP_ROLES};
        GRANT UPDATE (state, source, mark, wordmark, ink, accent, accent_night, accent_day, palette, options,
                      checks, digest, status_reason, attempts, step_up_id, updated_at, activated_at,
                      retired_at)
            ON org.company_brands TO {APP_ROLES};
        """
    )


def downgrade() -> None:
    execute_script(
        """
        DROP TABLE org.company_brands;
        DROP FUNCTION org.company_brands_guard();
        DROP SCHEMA org;
        """
    )
