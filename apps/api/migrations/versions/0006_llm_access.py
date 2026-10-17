"""Access of the api and worker roles to llm.* (contract §10, Token Treasury).

Read side: the ledger, usage counters, budgets and the registry. RLS on
llm.calls/usage/budgets already binds every role to app.company_ids.
Write side (owner actions behind step-up, and the hire effect):
connection status/name/prices, assignments, budgets. Never transcripts,
never a secret (keys live only in OpenBao). Partitions of llm.calls get no
grant, so the parent's policies cannot be bypassed through them.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script(
        """
        GRANT USAGE ON SCHEMA llm TO hq_api, hq_worker;
        GRANT EXECUTE ON FUNCTION llm.allowed_company_ids() TO hq_api, hq_worker;
        GRANT SELECT ON llm.connections, llm.task_classes, llm.assignments, llm.calls,
            llm.usage, llm.budgets TO hq_api, hq_worker;
        GRANT SELECT ON llm.v_usage_daily, llm.v_usage_monthly, llm.v_top_actors_30d TO hq_api;
        GRANT UPDATE (display_name, status, status_reason, status_changed_at, pricing, updated_at)
            ON llm.connections TO hq_api;
        GRANT INSERT, UPDATE (connection_id, model, effort, note, updated_at)
            ON llm.assignments TO hq_api, hq_worker;
        -- budget_change decisions are applied by the worker
        GRANT INSERT, UPDATE (token_limit, usd_limit, enabled, updated_at) ON llm.budgets TO hq_worker;
        GRANT INSERT, UPDATE (token_limit, usd_limit, enabled, updated_at)
            ON llm.budgets TO hq_api;

        -- llm-router's policies name only its own roles: the same company
        -- scope (app.company_ids) for the api and worker roles.
        CREATE POLICY calls_api_select ON llm.calls FOR SELECT TO hq_api, hq_worker
            USING (company_id = ANY (llm.allowed_company_ids()));
        CREATE POLICY usage_api_select ON llm.usage FOR SELECT TO hq_api, hq_worker
            USING (company_id = ANY (llm.allowed_company_ids()));
        CREATE POLICY budgets_api_select ON llm.budgets FOR SELECT TO hq_api, hq_worker
            USING (company_id = ANY (llm.allowed_company_ids()));
        CREATE POLICY budgets_api_insert ON llm.budgets FOR INSERT TO hq_api, hq_worker
            WITH CHECK (company_id = ANY (llm.allowed_company_ids()));
        CREATE POLICY budgets_api_update ON llm.budgets FOR UPDATE TO hq_api, hq_worker
            USING (company_id = ANY (llm.allowed_company_ids()))
            WITH CHECK (company_id = ANY (llm.allowed_company_ids()));
        """
    )


def downgrade() -> None:
    execute_script(
        """
        DROP POLICY calls_api_select ON llm.calls;
        DROP POLICY usage_api_select ON llm.usage;
        DROP POLICY budgets_api_select ON llm.budgets;
        DROP POLICY budgets_api_insert ON llm.budgets;
        DROP POLICY budgets_api_update ON llm.budgets;
        REVOKE ALL ON llm.connections, llm.task_classes, llm.assignments, llm.calls, llm.usage,
            llm.budgets, llm.v_usage_daily, llm.v_usage_monthly, llm.v_top_actors_30d
            FROM hq_api, hq_worker;
        REVOKE ALL ON FUNCTION llm.allowed_company_ids() FROM hq_api, hq_worker;
        REVOKE USAGE ON SCHEMA llm FROM hq_api, hq_worker;
        """
    )
