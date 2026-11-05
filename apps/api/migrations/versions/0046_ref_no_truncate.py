"""Bug of 2026-11-05 (prompt 23.2 §1, the owner: «هر جوری شده باید هر باگی که داره در بیاد»): no meeting since 11-03.

Every `ref` default was `'<P>-' || lpad(nextval(seq)::text, <w>, '0')`. Postgres' lpad CUTS a longer string to <w>,
so once a sequence passed 10^w - 1 its refs repeat: `meetings.meeting_ref_seq` reached 29303, and 29300..29309 all
became `MT-2930`. The meetings planner makes several meetings in one transaction; the second one hit
`meetings_ref_key`, the whole plan rolled back, 1332 times in 48 h, and no meeting or standup was made since
2026-11-03 16:10Z (`meetings.meetings` had 0 rows).

Now every such default (55 columns; any `<P>-` prefix, any width) goes through `core.pad_ref`, which pads to the
width but never cuts (the same rule as `lines.pad_ref`, `talk.pad_ref`, `cartable.next_resolution_ref` and
`msg.messages_number` already follow). Existing refs and the sequences are untouched; a ref past the width simply
grows a digit (`MT-29316`).

Revision ID: 0046
Revises: 0045
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE FUNCTION core.pad_ref(prefix text, n bigint, width integer) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    SET search_path = pg_catalog, pg_temp
    AS $$ SELECT prefix || CASE WHEN length(n::text) >= width THEN n::text ELSE lpad(n::text, width, '0') END $$;
-- The roles that insert into the tables with these defaults (only they and the owner have INSERT there).
GRANT EXECUTE ON FUNCTION core.pad_ref(text, bigint, integer) TO hq_api, hq_worker;

DO $$
DECLARE
    r record;
    m text[];
    n int := 0;
BEGIN
    FOR r IN
        SELECT ns.nspname AS s, c.relname AS t, a.attname AS col, pg_get_expr(d.adbin, d.adrelid) AS def
          FROM pg_attrdef d
          JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
          JOIN pg_class c ON c.oid = d.adrelid
          JOIN pg_namespace ns ON ns.oid = c.relnamespace
         WHERE c.relkind IN ('r', 'p')
           AND pg_get_expr(d.adbin, d.adrelid) LIKE '%lpad((nextval(%'
    LOOP
        m := regexp_match(
            r.def,
            '^\(''([A-Z]+-)''::text \|\| lpad\(\(nextval\(''([^'']+)''::regclass\)\)::text, ([0-9]+), ''0''::text\)\)$'
        );
        IF m IS NULL THEN
            RAISE EXCEPTION 'ref default of %.%.% has an unknown shape', r.s, r.t, r.col;
        END IF;
        EXECUTE format(
            'ALTER TABLE %I.%I ALTER COLUMN %I SET DEFAULT core.pad_ref(%L, nextval(%L::regclass), %s)',
            r.s, r.t, r.col, m[1], m[2], m[3]::int
        );
        n := n + 1;
    END LOOP;
    RAISE NOTICE 'ref defaults made safe: %', n;
END
$$;
"""

DOWNGRADE = r"""
DO $$
DECLARE
    r record;
    m text[];
BEGIN
    FOR r IN
        SELECT ns.nspname AS s, c.relname AS t, a.attname AS col, pg_get_expr(d.adbin, d.adrelid) AS def
          FROM pg_attrdef d
          JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
          JOIN pg_class c ON c.oid = d.adrelid
          JOIN pg_namespace ns ON ns.oid = c.relnamespace
         WHERE pg_get_expr(d.adbin, d.adrelid) LIKE 'core.pad_ref(%'
    LOOP
        m := regexp_match(r.def, '^core\.pad_ref\(''([A-Z]+-)''::text, nextval\(''([^'']+)''::regclass\), ([0-9]+)\)$');
        EXECUTE format(
            'ALTER TABLE %I.%I ALTER COLUMN %I SET DEFAULT (%L || lpad(nextval(%L::regclass)::text, %s, %L))',
            r.s, r.t, r.col, m[1], m[2], m[3]::int, '0'
        );
    END LOOP;
END
$$;
DROP FUNCTION core.pad_ref(text, bigint, integer);
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
