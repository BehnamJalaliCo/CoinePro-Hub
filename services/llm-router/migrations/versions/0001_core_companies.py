"""core.companies: the minimal company registry.

Companies are data, not code (OPERATING_MODEL §0): rows come from
seed/companies.yaml and later from the app. Exactly one holding.

Revision ID: 0001
Revises:
Create Date: 2026-10-16
"""

from llm_router.migration_sql import execute_script

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script(
        """
        CREATE SCHEMA core;

        CREATE TABLE core.companies (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            code        text NOT NULL UNIQUE CHECK (code ~ '^[A-Z][A-Z0-9]{1,9}$'),
            name        text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
            kind        text NOT NULL CHECK (kind IN ('holding', 'company')),
            status      text NOT NULL DEFAULT 'active'
                             CHECK (status IN ('active', 'paused', 'archived')),
            created_at  timestamptz NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX companies_single_holding ON core.companies (kind)
            WHERE kind = 'holding';

        GRANT USAGE ON SCHEMA core TO hq_llm_writer, hq_llm_reader;
        GRANT SELECT ON core.companies TO hq_llm_writer, hq_llm_reader;
        """
    )


def downgrade() -> None:
    execute_script("DROP SCHEMA core CASCADE")
