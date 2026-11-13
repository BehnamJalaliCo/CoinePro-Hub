#!/usr/bin/env bash
# infra/maintenance/ledger-turn-cost-fix.sh: the F-0018 usage audit's P6, a one-off correction of
# the Token Treasury rows that the hub's workshop and company servers booked before
# servers.turn_cost (2026-11-13, usage audit, commit ca3f94ed).
#
# What was wrong: a `claude` server job reports the Claude Code CLI's `total_cost_usd`, which is
# the running total of its Claude session. servers.record_usage booked that figure as the job's
# own cost, so every turn of a resumed session booked all of its earlier turns again: F-0018's
# direct turns read $1,108 in the ledger against about $131 really spent. The token counts were
# each turn's own and are right; only the dollars are wrong.
#
# What it changes, in ONE transaction:
#   1. llm.calls (caller = 'company_runner', task_class = 'server_claude'): equiv_cost_usd becomes
#      what servers.turn_cost gives today, recomputed from infra.server_jobs.usage (left as it is:
#      the CLI's own report): the job's total minus the highest total booked before it for the
#      same Claude session (usage.session_id) on the same server; a total that went down, a job
#      without a session id, or a first turn keeps its own figure. Absolute values, so a row
#      booked after the fix (already right) is left alone and a second run changes nothing.
#   2. workshop.sessions.usd: record_usage ADDED each job's figure to its session (it is not
#      rebuilt from the ledger), so each session loses exactly what its jobs' rows lose (never
#      below 0). Its guard (workshop.sessions_guard: "counters never go down") is the one thing
#      bypassed, for this statement only (session_replication_role = replica, which also skips
#      sessions_version: version and updated_at are set by hand).
# What it does not need to change:
#   - llm.usage: written only by llm-router for its own calls; the server rows were never added
#     to it (2026-11-13: the holding's day in llm.usage = $26.71 = the ledger without
#     company_runner rows).
#   - llm.v_usage_daily / v_usage_monthly / v_top_actors_30d: views over llm.calls.
#   - work.work.usd_used, agents.runs: a workshop turn books tokens only, never these dollars.
#   - flows.spent_usd (P4's cap) and the treasury pages read llm.calls live.
#   - llm.waste_daily: one row per owner-local day, recomputed by the daily waste job (upsert);
#     the script lists the days it touched that already have a row (to recompute, if any).
#
# Usage: ledger-turn-cost-fix.sh [--dry-run | --apply]
#   --dry-run (the default): everything above runs, the totals before and after are printed, and
#             the transaction is ROLLED BACK. Nothing is written.
#   --apply:  the same, then COMMIT. Only with the owner's approval and after `make backup`.
# Env: HQ_PG_CONTAINER (default coinepro-hq-postgres-1), HQ_PG_DB (default hq).
set -euo pipefail
MODE=dry-run
case "${1:-}" in
  "" | --dry-run) MODE=dry-run ;;
  --apply) MODE=apply ;;
  *) echo "usage: $0 [--dry-run | --apply]" >&2; exit 2 ;;
esac
END="ROLLBACK;"
[[ "$MODE" == apply ]] && END="COMMIT;"
PG="${HQ_PG_CONTAINER:-coinepro-hq-postgres-1}"
DB="${HQ_PG_DB:-hq}"
echo "ledger-turn-cost-fix: $MODE on $PG/$DB ($(date -u +%FT%TZ))"

docker exec -i "$PG" psql -U postgres -d "$DB" -v ON_ERROR_STOP=1 -X -P pager=off <<SQL
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- every booked server row with its job and the figure servers.turn_cost gives it
CREATE TEMP TABLE fix ON COMMIT DROP AS
WITH j AS (
    SELECT j.id, j.server_id, j.created_at, j.session_id, j.usage ->> 'session_id' AS sid,
           GREATEST(COALESCE(
               NULLIF(CASE WHEN jsonb_typeof(j.usage -> 'cost_usd') = 'number'
                           THEN (j.usage ->> 'cost_usd')::numeric END, 0),
               CASE WHEN jsonb_typeof(j.usage -> 'total_cost_usd') = 'number'
                    THEN (j.usage ->> 'total_cost_usd')::numeric END,
               0), 0) AS total
    FROM infra.server_jobs j
    WHERE j.kind = 'claude'
), b AS (
    SELECT j.*,
           (SELECT max(CASE WHEN jsonb_typeof(x.usage -> 'cost_usd') = 'number'
                            THEN (x.usage ->> 'cost_usd')::numeric END)
            FROM infra.server_jobs x
            WHERE x.server_id = j.server_id AND x.kind = 'claude' AND x.id <> j.id
              AND x.created_at < j.created_at AND x.usage ->> 'session_id' = j.sid) AS before
    FROM j
)
SELECT c.id AS call_id, c.started_at, c.company_id, c.work_ref, b.id AS job_id, b.session_id,
       c.equiv_cost_usd AS booked,
       round(CASE WHEN b.sid IS NULL OR b.total <= 0 OR b.server_id IS NULL
                       OR b.before IS NULL OR b.before > b.total THEN b.total
                  ELSE b.total - b.before END, 6) AS turn
FROM llm.calls c
JOIN b ON b.id::text = c.meta ->> 'server_job'
WHERE c.caller = 'company_runner' AND c.task_class = 'server_claude';

\echo
\echo == llm.calls, caller company_runner: before ==
SELECT count(*) AS rows, round(sum(equiv_cost_usd), 2) AS equiv_usd, min(started_at) AS first,
       max(started_at) AS last
FROM llm.calls WHERE caller = 'company_runner';
SELECT count(*) AS rows_without_their_job FROM llm.calls c
WHERE c.caller = 'company_runner' AND NOT EXISTS (SELECT 1 FROM fix f WHERE f.call_id = c.id);
SELECT count(*) FILTER (WHERE booked IS DISTINCT FROM turn) AS rows_to_change,
       round(sum(booked), 2) AS booked_usd, round(sum(turn), 2) AS corrected_usd,
       round(sum(booked) - sum(turn), 2) AS removed_usd
FROM fix;

\echo == by work (the largest corrections) ==
SELECT work_ref, count(*) AS turns, round(sum(booked), 2) AS booked_usd,
       round(sum(turn), 2) AS corrected_usd
FROM fix GROUP BY work_ref ORDER BY sum(booked) - sum(turn) DESC LIMIT 12;

\echo == workshop.sessions with booked server rows: before ==
SELECT s.ref, s.state, round(s.usd, 2) AS usd, round(sum(f.booked), 2) AS booked,
       round(sum(f.turn), 2) AS corrected, count(*) AS turns
FROM fix f JOIN workshop.sessions s ON s.id = f.session_id
GROUP BY s.ref, s.state, s.usd ORDER BY sum(f.booked) - sum(f.turn) DESC, s.ref;

-- 1. the ledger rows
UPDATE llm.calls c SET equiv_cost_usd = f.turn
FROM fix f
WHERE c.id = f.call_id AND c.started_at = f.started_at AND c.equiv_cost_usd IS DISTINCT FROM f.turn;

-- 2. the sessions, by what their rows lost (their guard never lets a counter go down)
SET LOCAL session_replication_role = replica;
UPDATE workshop.sessions s
SET usd = GREATEST(s.usd - d.lost, 0), version = s.version + 1, updated_at = now()
FROM (SELECT session_id, sum(booked - turn) AS lost FROM fix
      WHERE session_id IS NOT NULL GROUP BY session_id HAVING sum(booked - turn) <> 0) d
WHERE s.id = d.session_id;
SET LOCAL session_replication_role = origin;

\echo
\echo == llm.calls, caller company_runner: after ==
SELECT count(*) AS rows, round(sum(equiv_cost_usd), 2) AS equiv_usd
FROM llm.calls WHERE caller = 'company_runner';
SELECT (started_at AT TIME ZONE 'UTC')::date AS day_utc, count(*) AS rows,
       round(sum(equiv_cost_usd), 2) AS equiv_usd
FROM llm.calls WHERE caller = 'company_runner' GROUP BY 1 ORDER BY 1;

\echo == workshop.sessions with booked server rows: after ==
SELECT s.ref, s.state, round(s.usd, 2) AS usd
FROM workshop.sessions s WHERE s.id IN (SELECT session_id FROM fix)
ORDER BY s.usd DESC, s.ref;
SELECT round(sum(s.usd), 2) AS sessions_usd_after
FROM workshop.sessions s WHERE s.id IN (SELECT session_id FROM fix);

\echo == llm.waste_daily rows of the days touched (recompute them after an apply) ==
SELECT w.day, w.scope, round(w.total_usd, 2) AS total_usd FROM llm.waste_daily w
WHERE w.day IN (SELECT DISTINCT (f.started_at AT TIME ZONE 'Asia/Tehran')::date FROM fix f
                WHERE f.booked IS DISTINCT FROM f.turn)
ORDER BY w.day, w.scope;

$END
SQL
echo "ledger-turn-cost-fix: $MODE done ($([[ "$MODE" == apply ]] && echo committed || echo rolled back))"
