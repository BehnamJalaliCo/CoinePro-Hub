"""Files in a session (contract §36, the owner, 2026-11-06: «میخوام اینجا فایل بفرستم برای سشن
نمیتونم» · «تایتل بذاره با فونتی که ما میدیم»).

- files.files: a new kind `font` (TrueType, OpenType, WOFF, WOFF2; a text file and a ZIP are a
  `document`), and `meta` (what the hub read of the file at upload, in the untrusted child: a
  font's {family, style}). The table stays append-only: `meta` is written with the row.
- talk.turns.files: the owner's files of a turn (at most 10; the owner's own uploads), written
  with the turn and never changed.
- owner.order_files: the files of an order (§36.3): every file of the owner's turns in a session
  belongs to the order, so every run of the order's works may read it (`files.read`) whatever
  its company. The holding's rows, FORCE RLS, never changed and never deleted.
- media.items.style: the item's style ({font_file_id}: a font of the item's order or company,
  used by the render beside IRANYekanX).

Additive only; nothing is deleted.

Revision ID: 0054
Revises: 0053
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
KINDS_BEFORE = "'image', 'video', 'audio', 'document', 'other'"
KINDS = KINDS_BEFORE + ", 'font'"

UPGRADE = f"""
-- ============================================================ §36.1 upload ==
ALTER TABLE files.files DROP CONSTRAINT files_kind_check;
ALTER TABLE files.files ADD CONSTRAINT files_kind_check CHECK (kind IN ({KINDS}));
ALTER TABLE files.files
    ADD COLUMN meta jsonb NOT NULL DEFAULT '{{}}'
        CHECK (jsonb_typeof(meta) = 'object' AND length(meta::text) <= 2000);
COMMENT ON COLUMN files.files.meta IS
    'What the hub read of the file at upload (a font: family, style), in the untrusted child';

-- ================================================== §36.2 a turn with files ==
ALTER TABLE talk.turns
    ADD COLUMN files uuid[] NOT NULL DEFAULT '{{}}' CHECK (cardinality(files) <= 10);

-- ========================================== §36.3 files go with the order ==
CREATE TABLE owner.order_files (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    order_id    uuid NOT NULL REFERENCES owner.orders (id),
    file_id     uuid NOT NULL REFERENCES files.files (id),
    turn_id     uuid REFERENCES talk.turns (id),
    added_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (order_id, file_id)
);
CREATE INDEX order_files_file ON owner.order_files (file_id);
CREATE TRIGGER order_files_append_only BEFORE UPDATE OR DELETE ON owner.order_files
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON owner.order_files TO {APP_ROLES};
ALTER TABLE owner.order_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE owner.order_files FORCE ROW LEVEL SECURITY;
CREATE POLICY order_files_tenant ON owner.order_files TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY order_files_owner_role ON owner.order_files TO hq USING (true) WITH CHECK (true);

-- the media studio: an item's style (a font of its order or company)
ALTER TABLE media.items
    ADD COLUMN style jsonb CHECK (style IS NULL OR jsonb_typeof(style) = 'object');
"""

DOWNGRADE = f"""
ALTER TABLE media.items DROP COLUMN style;
DROP TABLE owner.order_files;
ALTER TABLE talk.turns DROP COLUMN files;
ALTER TABLE files.files DROP COLUMN meta;
-- rows of the new kind stay (nothing is deleted): the old CHECK comes back NOT VALID
ALTER TABLE files.files DROP CONSTRAINT files_kind_check;
ALTER TABLE files.files ADD CONSTRAINT files_kind_check CHECK (kind IN ({KINDS_BEFORE})) NOT VALID;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
