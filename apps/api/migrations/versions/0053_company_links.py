"""Company links and the owner's canvas (contract §35.6, §35.7), the owner, 2026-11-06: «شرکت ها به
هم دیگه ارتباط داشته باشند و همه به هاب و بتونم این ارتباط هارو شکل بدم».

- core.company_links: one directed link between two companies (`serves`, `publishes`, `feeds`,
  `sells`, `supports`) with a purpose in one Persian line, `on` or `off` (never deleted). The row
  belongs to the holding (`company_id`); the hub node is linked to every company implicitly, so
  no row is kept for that. Unique per (from, to, kind).
- owner.canvas_nodes: where the owner put a company on his canvas (x, y in 0..1).
- owner.settings.links_enforced: while false (the default) a cross-company request of an agent
  goes as it always did (CEO to CEO); while true a request along an `on` link is accepted for a
  CEO or a manager.
- core.company_linked(a, b) and core.company_links_of(company): the two reads agents' transactions
  need (their scope is their own company, the rows are the holding's): SECURITY DEFINER, read only.

Additive only; nothing is deleted.

Revision ID: 0053
Revises: 0052
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"


def _rls(table: str) -> str:
    name = table.split(".")[1]
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
CREATE TRIGGER {name}_no_delete BEFORE DELETE ON {table}
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
"""


UPGRADE = f"""
CREATE TABLE core.company_links (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    from_company_id  uuid NOT NULL REFERENCES core.companies (id),
    to_company_id    uuid NOT NULL REFERENCES core.companies (id),
    kind             text NOT NULL CHECK (kind IN ('serves', 'publishes', 'feeds', 'sells', 'supports')),
    purpose_fa       text NOT NULL DEFAULT '' CHECK (length(purpose_fa) <= 200),
    state            text NOT NULL DEFAULT 'on' CHECK (state IN ('on', 'off')),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    version          int NOT NULL DEFAULT 1,
    CHECK (from_company_id <> to_company_id),
    UNIQUE (from_company_id, to_company_id, kind)
);
CREATE INDEX company_links_to ON core.company_links (to_company_id) WHERE state = 'on';
CREATE TRIGGER company_links_version BEFORE UPDATE ON core.company_links
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
CREATE TRIGGER company_links_immutable BEFORE UPDATE ON core.company_links
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'from_company_id',
                                                      'to_company_id', 'created_at');
GRANT SELECT, INSERT ON core.company_links TO {APP_ROLES};
GRANT UPDATE (kind, purpose_fa, state) ON core.company_links TO {APP_ROLES};

CREATE TABLE owner.canvas_nodes (
    company_id  uuid PRIMARY KEY REFERENCES core.companies (id),
    x           numeric(7, 6) NOT NULL CHECK (x BETWEEN 0 AND 1),
    y           numeric(7, 6) NOT NULL CHECK (y BETWEEN 0 AND 1),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT ON owner.canvas_nodes TO {APP_ROLES};
GRANT UPDATE (x, y, updated_at) ON owner.canvas_nodes TO {APP_ROLES};

ALTER TABLE owner.settings ADD COLUMN links_enforced boolean NOT NULL DEFAULT false;
GRANT UPDATE (links_enforced) ON owner.settings TO hq_api;

CREATE FUNCTION core.company_linked(p_a uuid, p_b uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT EXISTS (
        SELECT 1 FROM core.company_links
        WHERE state = 'on'
          AND ((from_company_id = p_a AND to_company_id = p_b)
               OR (from_company_id = p_b AND to_company_id = p_a)))
    $$;
REVOKE ALL ON FUNCTION core.company_linked(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION core.company_linked(uuid, uuid) TO {APP_ROLES};

CREATE FUNCTION core.company_links_of(p_company uuid)
    RETURNS TABLE (other_code text, other_name_fa text, kind text, purpose_fa text, outgoing boolean)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT o.code, o.name_fa, l.kind, l.purpose_fa, l.from_company_id = p_company
    FROM core.company_links l
    JOIN core.companies o ON o.id = CASE WHEN l.from_company_id = p_company
                                         THEN l.to_company_id ELSE l.from_company_id END
    WHERE l.state = 'on' AND p_company IN (l.from_company_id, l.to_company_id)
    ORDER BY o.code, l.kind
    $$;
REVOKE ALL ON FUNCTION core.company_links_of(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION core.company_links_of(uuid) TO {APP_ROLES};
"""

DOWNGRADE = """
DROP FUNCTION IF EXISTS core.company_links_of(uuid);
DROP FUNCTION IF EXISTS core.company_linked(uuid, uuid);
REVOKE UPDATE (links_enforced) ON owner.settings FROM hq_api;
ALTER TABLE owner.settings DROP COLUMN links_enforced;
DROP TABLE owner.canvas_nodes;
DROP TABLE core.company_links;
"""


def upgrade() -> None:
    execute_script(UPGRADE + _rls("core.company_links") + _rls("owner.canvas_nodes"))


def downgrade() -> None:
    execute_script(DOWNGRADE)
