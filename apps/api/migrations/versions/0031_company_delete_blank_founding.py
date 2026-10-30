"""Prompt 15.2, contract §25 ⟨1.7.5⟩: delete a company made by mistake, and
the simple founding.

- A company with no history (no work delivered or done, no deliverable,
  archive record, revenue day, treasury usage or server) may be deleted.
  Its rows go, in one transaction, through `core.purge_company`
  (SECURITY DEFINER, owner hq): every table with a key to core.companies,
  children before parents. Its audit rows stay: audit outlives what it
  records, so audit.entries loses its key to core.companies (the rows keep
  the deleted company's id; the deletion itself is audited on the holding).
- The append-only guards (core.reject_change, files.guard_change) let a
  DELETE through only while `hq.purge_company` is set in the same
  transaction (and, for reject_change, only for the owner role hq), which
  only core.purge_company does. The app roles have no DELETE on any guarded
  table and cannot become hq, so for them nothing changes.
- The treasury tables (llm.calls, llm.usage, llm.budgets) force row security
  even on their owner: hq gets a policy that shows (and, for usage and
  budgets, removes) the rows of the one company `hq.purge_company` names,
  so the history check sees its token use and the purge its budget rows.
  llm.calls is never deleted (a call is history).
- Companies may be `draft`: a founding of kind `blank` registers one without
  an audit or a proposal. A founding keeps the owner's tagline, colour slot
  and logo file (the brand is made from them when the founding is sealed).

Revision ID: 0031
Revises: 0030
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

UPGRADE = """
ALTER TABLE core.companies DROP CONSTRAINT companies_status_check;
ALTER TABLE core.companies ADD CONSTRAINT companies_status_check
    CHECK (status IN ('active', 'paused', 'archived', 'draft'));

ALTER TABLE core.foundings DROP CONSTRAINT foundings_source_check;
ALTER TABLE core.foundings ADD CONSTRAINT foundings_source_check
    CHECK ((source ->> 'kind') IN ('repo', 'idea', 'blank'));
ALTER TABLE core.foundings
    ADD COLUMN tagline      text CHECK (length(tagline) <= 200),
    ADD COLUMN color_index  int CHECK (color_index BETWEEN 1 AND 8),
    ADD COLUMN logo_file_id uuid REFERENCES files.files (id);

ALTER TABLE audit.entries DROP CONSTRAINT entries_company_id_fkey;

CREATE OR REPLACE FUNCTION core.reject_change() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    -- core.purge_company (as hq) deletes a company that has no history
    IF TG_OP = 'DELETE' AND current_user = 'hq'
       AND COALESCE(current_setting('hq.purge_company', true), '') <> '' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION '%.% is append-only (% rejected)', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'HQA01';
END $$;

CREATE OR REPLACE FUNCTION files.guard_change() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    -- (no app role may DELETE here at all: only core.purge_company gets this far)
    IF TG_OP = 'DELETE'
       AND COALESCE(current_setting('hq.purge_company', true), '') = OLD.company_id::text THEN
        RETURN OLD;
    END IF;
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

CREATE POLICY calls_company_purge ON llm.calls FOR SELECT TO hq
    USING (company_id::text = current_setting('hq.purge_company', true));
CREATE POLICY usage_company_purge ON llm.usage FOR ALL TO hq
    USING (company_id::text = current_setting('hq.purge_company', true));
CREATE POLICY budgets_company_purge ON llm.budgets FOR ALL TO hq
    USING (company_id::text = current_setting('hq.purge_company', true));

-- What makes a company more than a mistake (contract §25): its history.
CREATE OR REPLACE FUNCTION core.company_history(p_id uuid) RETURNS text[]
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    found  text[];
    before text := COALESCE(current_setting('hq.purge_company', true), '');
BEGIN
    PERFORM set_config('hq.purge_company', p_id::text, true);  -- the treasury rows show
    SELECT array_remove(ARRAY[
        CASE WHEN EXISTS (SELECT 1 FROM work.work
                          WHERE company_id = p_id AND status IN ('delivered', 'done'))
             THEN 'work' END,
        CASE WHEN EXISTS (SELECT 1 FROM cartable.deliverables WHERE company_id = p_id)
             THEN 'deliverables' END,
        CASE WHEN EXISTS (SELECT 1 FROM archive.records WHERE company_id = p_id)
             THEN 'archive' END,
        CASE WHEN EXISTS (SELECT 1 FROM revenue.days WHERE company_id = p_id)
             THEN 'revenue' END,
        CASE WHEN EXISTS (SELECT 1 FROM llm.calls WHERE company_id = p_id)
               OR EXISTS (SELECT 1 FROM llm.usage
                          WHERE company_id = p_id AND (calls <> 0 OR tokens <> 0 OR usd <> 0))
             THEN 'treasury' END,
        CASE WHEN EXISTS (SELECT 1 FROM infra.servers WHERE company_id = p_id)
             THEN 'server' END
    ], NULL) INTO found;
    PERFORM set_config('hq.purge_company', before, true);
    RETURN found;
END $$;

-- Deletes a company without history and every row keyed to it (never its
-- audit rows), children before parents; returns {table: rows}.
CREATE OR REPLACE FUNCTION core.purge_company(p_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    co        record;
    item      text;
    pending   text[];
    left_over text[];
    n         bigint;
    counts    jsonb := '{}';
    progress  boolean;
BEGIN
    SELECT id, code, kind INTO co FROM core.companies WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no company %', p_id USING ERRCODE = 'HQA04';
    END IF;
    IF co.kind = 'holding' THEN
        RAISE EXCEPTION 'the holding is never deleted' USING ERRCODE = 'HQA02';
    END IF;
    IF cardinality(core.company_history(p_id)) > 0 THEN
        RAISE EXCEPTION 'company % has history: %', co.code, core.company_history(p_id)
            USING ERRCODE = 'HQA03';
    END IF;
    PERFORM set_config('hq.purge_company', p_id::text, true);
    pending := ARRAY(
        SELECT DISTINCT format('%I.%I', n.nspname, c.relname) || ' ' || quote_ident(a.attname)
        FROM pg_constraint k
        JOIN pg_class c ON c.oid = k.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = ANY (k.conkey)
        WHERE k.contype = 'f' AND k.confrelid = 'core.companies'::regclass
          AND NOT c.relispartition AND k.conrelid <> 'audit.entries'::regclass
    );
    LOOP
        progress := false;
        left_over := '{}';
        FOREACH item IN ARRAY pending LOOP
            BEGIN
                EXECUTE format('DELETE FROM %s WHERE %s = $1', split_part(item, ' ', 1),
                               split_part(item, ' ', 2)) USING p_id;
                GET DIAGNOSTICS n = ROW_COUNT;
                IF n > 0 THEN
                    counts := counts || jsonb_build_object(split_part(item, ' ', 1),
                        n + COALESCE((counts ->> split_part(item, ' ', 1))::bigint, 0));
                END IF;
                progress := true;
            EXCEPTION WHEN foreign_key_violation THEN
                left_over := left_over || item;  -- rows still pointing at these: next round
            END;
        END LOOP;
        pending := left_over;
        EXIT WHEN cardinality(pending) = 0 OR NOT progress;
    END LOOP;
    IF cardinality(pending) > 0 THEN
        RAISE EXCEPTION 'company % is still linked from %', co.code, pending
            USING ERRCODE = 'HQA05';
    END IF;
    BEGIN
        DELETE FROM core.companies WHERE id = p_id;
    EXCEPTION WHEN foreign_key_violation THEN
        RAISE EXCEPTION 'company % is still linked: %', co.code, SQLERRM USING ERRCODE = 'HQA05';
    END;
    PERFORM set_config('hq.purge_company', '', true);
    RETURN counts;
END $$;

REVOKE ALL ON FUNCTION core.company_history(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION core.purge_company(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION core.company_history(uuid) TO hq_api;
GRANT EXECUTE ON FUNCTION core.purge_company(uuid) TO hq_api;
"""

DOWNGRADE = """
DROP FUNCTION core.purge_company(uuid);
DROP FUNCTION core.company_history(uuid);
DROP POLICY calls_company_purge ON llm.calls;
DROP POLICY usage_company_purge ON llm.usage;
DROP POLICY budgets_company_purge ON llm.budgets;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
