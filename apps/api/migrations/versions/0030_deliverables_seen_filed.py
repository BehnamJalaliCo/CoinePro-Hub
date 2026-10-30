"""Prompt 15 §1, contract §5.2 ⟨1.7.3⟩: deliverables gain `category`
(report | work), `seen_at` and `filed_as`.

- `category` is set once, at insert (a trigger: the hub's own reporting, a
  producer `<CODE>-SYS`, writes `report`; everything else is `work`), and
  existing rows get it here. It stays immutable like every other column.
- `seen_at` and `filed_as` are the only columns that may change: the
  append-only trigger becomes "no delete, nothing else changes", and the api
  role gets UPDATE on those two columns only. Nothing is ever deleted.
- The archive's `about` link may point at a deliverable (filing it, §23).

Revision ID: 0030
Revises: 0029_1
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0030"
down_revision = "0029_1"
branch_labels = None
depends_on = None

IMMUTABLE = (
    "'id', 'ref', 'company_id', 'work_id', 'producer_id', 'title', 'summary', 'body', "
    "'attachments', 'produced_with', 'usage', 'evidence', 'created_at', 'category'"
)

UPGRADE = f"""
ALTER TABLE cartable.deliverables
    ADD COLUMN category text,
    ADD COLUMN seen_at  timestamptz,
    ADD COLUMN filed_as text CHECK (filed_as ~ '^AR-[0-9]{{6,}}$');

ALTER TABLE cartable.deliverables DISABLE TRIGGER deliverables_append_only;
UPDATE cartable.deliverables d SET category = CASE WHEN e.code LIKE '%-SYS' THEN 'report' ELSE 'work' END
  FROM core.employees e WHERE e.id = d.producer_id;
UPDATE cartable.deliverables SET category = 'work' WHERE category IS NULL;
ALTER TABLE cartable.deliverables ENABLE TRIGGER deliverables_append_only;
ALTER TABLE cartable.deliverables
    ALTER COLUMN category SET NOT NULL,
    ADD CONSTRAINT deliverables_category_check CHECK (category IN ('report', 'work'));

CREATE FUNCTION cartable.deliverable_category() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF NEW.category IS NULL THEN
        NEW.category := CASE WHEN EXISTS (SELECT 1 FROM core.employees e
                                          WHERE e.id = NEW.producer_id AND e.code LIKE '%-SYS')
                             THEN 'report' ELSE 'work' END;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER deliverables_category BEFORE INSERT ON cartable.deliverables
    FOR EACH ROW EXECUTE FUNCTION cartable.deliverable_category();

DROP TRIGGER deliverables_append_only ON cartable.deliverables;
CREATE TRIGGER deliverables_no_delete BEFORE DELETE ON cartable.deliverables
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
CREATE TRIGGER deliverables_immutable BEFORE UPDATE ON cartable.deliverables
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable({IMMUTABLE});
GRANT UPDATE (seen_at, filed_as) ON cartable.deliverables TO hq_api;

CREATE INDEX deliverables_unseen ON cartable.deliverables (created_at DESC) WHERE seen_at IS NULL;

UPDATE archive.link_kinds SET to_kinds = array_append(to_kinds, 'deliverable')
 WHERE key = 'about' AND NOT ('deliverable' = ANY (to_kinds));
ALTER TABLE archive.links DROP CONSTRAINT links_to_kind_check;
ALTER TABLE archive.links ADD CONSTRAINT links_to_kind_check CHECK (to_kind IN (
    'decision', 'resolution', 'case', 'work', 'record', 'employee', 'revenue_account', 'party',
    'company', 'deliverable'));
"""

DOWNGRADE = """
ALTER TABLE archive.links DROP CONSTRAINT links_to_kind_check;
ALTER TABLE archive.links ADD CONSTRAINT links_to_kind_check CHECK (to_kind IN (
    'decision', 'resolution', 'case', 'work', 'record', 'employee', 'revenue_account', 'party',
    'company')) NOT VALID;
UPDATE archive.link_kinds SET to_kinds = array_remove(to_kinds, 'deliverable') WHERE key = 'about';
DROP INDEX cartable.deliverables_unseen;
REVOKE UPDATE (seen_at, filed_as) ON cartable.deliverables FROM hq_api;
DROP TRIGGER deliverables_immutable ON cartable.deliverables;
DROP TRIGGER deliverables_no_delete ON cartable.deliverables;
CREATE TRIGGER deliverables_append_only BEFORE UPDATE OR DELETE ON cartable.deliverables
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
DROP TRIGGER deliverables_category ON cartable.deliverables;
DROP FUNCTION cartable.deliverable_category();
ALTER TABLE cartable.deliverables DROP COLUMN filed_as, DROP COLUMN seen_at, DROP COLUMN category;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
