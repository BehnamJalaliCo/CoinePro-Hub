"""Aggregate views over the ledger (security_invoker: the caller's RLS applies).

- llm.v_usage_daily    per day x company x connection x model
- llm.v_usage_monthly  per month x company x connection x model
- llm.v_top_actors_30d heaviest actor_refs over the last 30 days

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-16
"""

from llm_router.migration_sql import execute_script

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_TOTALS = """
    count(*)                                         AS calls,
    count(*) FILTER (WHERE c.status = 'ok')          AS ok_calls,
    coalesce(sum(c.input_tokens), 0)                 AS input_tokens,
    coalesce(sum(c.output_tokens), 0)                AS output_tokens,
    coalesce(sum(c.cache_read_tokens), 0)            AS cache_read_tokens,
    coalesce(sum(c.cache_write_tokens), 0)           AS cache_write_tokens,
    sum(c.thinking_tokens)                           AS thinking_tokens,
    coalesce(sum(c.cost_usd), 0)                     AS cost_usd,
    coalesce(sum(c.equiv_cost_usd), 0)               AS equiv_cost_usd
"""

_TOKENS = (
    "coalesce(c.input_tokens, 0) + coalesce(c.output_tokens, 0)"
    " + coalesce(c.cache_read_tokens, 0) + coalesce(c.cache_write_tokens, 0)"
)


def upgrade() -> None:
    for name, bucket in (("v_usage_daily", "day"), ("v_usage_monthly", "month")):
        execute_script(
            f"""
            CREATE VIEW llm.{name} WITH (security_invoker = true) AS
            SELECT (date_trunc('{bucket}', c.started_at AT TIME ZONE 'UTC'))::date AS {bucket},
                   co.code  AS company,
                   cn.key   AS connection,
                   c.model,
                   {_TOTALS}
            FROM llm.calls c
            JOIN core.companies co ON co.id = c.company_id
            LEFT JOIN llm.connections cn ON cn.id = c.connection_id
            GROUP BY 1, 2, 3, 4;
            """
        )
    execute_script(
        f"""
        CREATE VIEW llm.v_top_actors_30d WITH (security_invoker = true) AS
        SELECT co.code                          AS company,
               c.actor_ref,
               count(*)                         AS calls,
               sum({_TOKENS})                   AS tokens,
               coalesce(sum(c.cost_usd), 0)     AS cost_usd,
               coalesce(sum(c.equiv_cost_usd), 0) AS equiv_cost_usd,
               max(c.started_at)                AS last_call_at
        FROM llm.calls c
        JOIN core.companies co ON co.id = c.company_id
        WHERE c.started_at >= now() - interval '30 days'
        GROUP BY 1, 2;

        GRANT SELECT ON llm.v_usage_daily, llm.v_usage_monthly, llm.v_top_actors_30d
            TO hq_llm_reader, hq_llm_writer;
        """
    )


def downgrade() -> None:
    execute_script("DROP VIEW llm.v_top_actors_30d, llm.v_usage_monthly, llm.v_usage_daily")
