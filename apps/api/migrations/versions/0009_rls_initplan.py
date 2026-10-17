"""Prompt 05: tenant policies evaluate the company scope once per query.

The tenant policies compared every row with `ANY (<schema>.allowed_company_ids())`.
The function is STABLE, but its result (a text setting cast to uuid[]) was
computed again for each row, so a scan cost rows x companies, and no index on
company_id could be used. As a scalar subquery it is computed once per query
(an InitPlan) and the company_id indexes apply: on a test database with 330
companies the owner's inbox summary went from 778 ms to 46 ms. Same rows, same
rule; only the evaluation changes. Idempotent: only the exact old form is
rewritten, so running it again (or after the other service's migration) is a
no-op. Covers the api's schemas and the policies 0006 put on llm tables.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

SCHEMAS = (
    "ARRAY['core', 'work', 'cartable', 'msg', 'notify', 'auth', 'owner', 'audit', "
    "'control', 'files', 'agents', 'ops', 'llm']"
)


def upgrade() -> None:
    execute_script(
        r"""
        DO $hoist$
        DECLARE
            p record;
            q text;
            c text;
            stmt text;
        BEGIN
            FOR p IN
                SELECT n.nspname AS s, t.relname AS t, pol.polname AS name,
                       pg_get_expr(pol.polqual, pol.polrelid) AS qual,
                       pg_get_expr(pol.polwithcheck, pol.polrelid) AS chk
                FROM pg_policy pol
                JOIN pg_class t ON t.oid = pol.polrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = ANY (SCHEMAS)
                  AND pg_get_userbyid(t.relowner) = current_user
            LOOP
                q := regexp_replace(p.qual, 'ANY \((core|llm)\.allowed_company_ids\(\)\)',
                                    'ANY ((SELECT \1.allowed_company_ids())::uuid[])', 'g');
                c := regexp_replace(p.chk, 'ANY \((core|llm)\.allowed_company_ids\(\)\)',
                                    'ANY ((SELECT \1.allowed_company_ids())::uuid[])', 'g');
                IF q IS DISTINCT FROM p.qual OR c IS DISTINCT FROM p.chk THEN
                    stmt := format('ALTER POLICY %I ON %I.%I', p.name, p.s, p.t);
                    IF q IS NOT NULL THEN
                        stmt := stmt || format(' USING (%s)', q);
                    END IF;
                    IF c IS NOT NULL THEN
                        stmt := stmt || format(' WITH CHECK (%s)', c);
                    END IF;
                    EXECUTE stmt;
                END IF;
            END LOOP;
        END
        $hoist$;
        """.replace("SCHEMAS", SCHEMAS)
    )


def downgrade() -> None:
    pass  # the old form is slower, not different: nothing to undo
