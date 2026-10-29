"""The hub's fresh start before the owner's opening (prompt 16).

`python -m hq_api.fresh_start sql --snapshot ID --previous-seq N --previous-hash H`
prints one SQL script for `psql -U postgres -d hq` (the superuser: it turns
the tables' own guards off for its one transaction); `anchor` (in the worker)
then appends the new chain's first anchor, and `blobs` (in the api) removes
the stored files of the wiped rows. infra/fresh-start/fresh-start.sh runs the
three. What ran goes; what the hub is made of stays:

- WIPE: everything that was run or produced (work, decisions, deliverables,
  messages, runs, the token ledger, stars and scores, oversight's findings,
  meetings, media, legal, archive records, support, the audit chain ...).
- KEEP: the owner's identity, the companies and their structure (every
  employee stays, the owner's decision of 2026-10-29), charters, protocols,
  the authority matrix, the calendar, connections, sign-ins, settings and the
  archive's scheme. RESET clears what a kept row remembers of the wiped data.
- ASK: in neither list of the prompt: kept, and listed in the report.

A table in no list stops the script (a later migration's table is never
wiped unread), as does a ref sequence in no list. After the deletes, every
foreign key into a wiped table is checked from the kept side: one row left
pointing at wiped data and nothing is committed. The audit chain then starts
again at its genesis, its first row this fresh start (snapshot and the
previous head included). Nothing here reads or prints a secret.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from hq_api import audit
from hq_api.audit import GENESIS

DECISION = "شروع تازه را اجرا کن"

WIPE: tuple[str, ...] = (
    "academy.eval_runs", "academy.teachings",
    "advisor.memos", "advisor.triggers",
    "agents.runs", "agents.steps",
    "archive.access_log", "archive.automation_runs", "archive.destroy_queue", "archive.fixity_runs",
    "archive.holds", "archive.intake", "archive.links", "archive.parties", "archive.record_files",
    "archive.record_versions", "archive.records", "archive.reminders", "archive.tombstones",
    "audit.entries",
    "cartable.decisions", "cartable.deliverables", "cartable.ratings", "cartable.resolutions",
    "core.counters", "core.employee_memory", "core.employee_scores", "core.foundings",
    "core.idempotency_keys",
    "dceo.predictions",
    "feedback.items", "feedback.signals",
    "governance.batches", "governance.kpi_values", "governance.okr_checkins",
    "governance.outcome_reviews",
    "growth.funnel_days", "growth.leaks", "growth.nps_responses", "growth.nps_waves",
    "growth.referral_checks", "growth.rescue_cases", "growth.rescue_steps", "growth.sends",
    "intake.events", "intake.nonces", "intake.rejections",
    "knowledge.asks", "knowledge.lesson_adoptions", "knowledge.lessons",
    "legal.case_events", "legal.cases", "legal.emails",
    "llm.calls", "llm.transcripts", "llm.usage", "llm.waste_daily",
    "media.compositions", "media.items", "media.publish_log", "media.render_jobs", "media.series",
    "media.speech_jobs",
    "meetings.claims", "meetings.drafts", "meetings.items", "meetings.meetings", "meetings.requests",
    "meetings.turns", "meetings.whispers",
    "msg.messages",
    "notify.digest_batches", "notify.notifications",
    "oversight.challenges", "oversight.compliance", "oversight.finding_history",
    "oversight.findings", "oversight.holds", "oversight.inquiries", "oversight.orders",
    "oversight.protocol_runs", "oversight.watch",
    "owner.decision_reminders", "owner.errands", "owner.notes", "owner.orders",
    "owner.planner_items", "owner.reviews", "owner.stories",
    "people.department_ranks", "people.hr_rounds", "people.role_drafts", "people.star_rollups",
    "people.stars",
    "quality.claims",
    "reports.briefings", "reports.ceo_letters",
    "revenue.alerts", "revenue.days", "revenue.invitees", "revenue.pulls",
    "substitutes.calls", "substitutes.creatives",
    "support.conversations", "support.customers", "support.history_imports", "support.messages",
    "support.shadow_runs",
    "tools.mcp_calls",
    "work.escrows", "work.schedules", "work.work", "work.work_events",
    "workshop.approvals", "workshop.events", "workshop.grants", "workshop.sessions",
)  # fmt: skip

KEEP: tuple[str, ...] = (
    "academy.addenda", "academy.curricula", "academy.eval_suites",
    "archive.automations", "archive.class_versions", "archive.classes", "archive.clearance", "archive.fields",
    "archive.folders", "archive.levels", "archive.link_kinds", "archive.party_kinds",
    "archive.reminder_rules", "archive.retention_rules", "archive.sources",
    "audit.chain_head",
    "auth.challenges", "auth.enrolment_tokens", "auth.passkeys", "auth.sessions", "auth.step_ups",
    "control.deploy_freezes", "control.kill_switches",
    "core.companies", "core.departments", "core.employee_code_seq", "core.employees", "core.hiring",
    "feedback.keywords",
    "governance.authority", "governance.authority_history", "governance.calendar_events",
    "governance.charters", "governance.kpi_changes", "governance.kpi_sets", "governance.kpis",
    "governance.rollout",
    "growth.opt_outs", "growth.rules", "growth.templates",
    "infra.inventory", "infra.servers",
    "intake.sources",
    "knowledge.corpus_chunks", "knowledge.corpus_files", "knowledge.corpus_sources",
    "knowledge.skill_versions", "knowledge.skills",
    "legal.mailbox",
    "llm.assignments", "llm.budgets", "llm.connections", "llm.task_classes",
    "media.voice_references", "media.voice_samples", "media.voices",
    "meetings.types",
    "msg.threads",
    "notify.fcm_tokens", "notify.settings", "notify.web_push_subscriptions",
    "ops.hub_health", "ops.sites",
    "org.company_brands",
    "oversight.protocols",
    "owner.presence", "owner.settings",
    "people.star_rubrics",
    "public.alembic_version_api", "public.alembic_version_llm_router",
    "revenue.accounts",
    "substitutes.logins", "substitutes.players", "substitutes.seats",
    "support.channels", "support.kb_articles", "support.settings",
    "tools.accounts", "tools.mcp_servers",
    "workshop.workspaces",
)  # fmt: skip

# In neither list of the prompt (16 §5.5): kept as they are, named in the report.
ASK: tuple[str, ...] = (
    "backup.restore_tests", "backup.runs", "backup.snapshots", "backup.status",
    "core.outbox",
    "dceo.principles",
    "egress.log",
    "files.files", "files.processing",
    "governance.key_results", "governance.objectives", "governance.risk_history", "governance.risks",
    "knowledge.entries",
    "llm.quota_status",
    "ops.checks", "ops.incidents",
    "owner.interactions",
    "provisioning.plans", "provisioning.run_events", "provisioning.runs",
)  # fmt: skip

# What a kept row remembers of the wiped data.
RESET: tuple[str, ...] = (
    # every employee stays; its activity and scores start again
    """UPDATE core.employees SET activity = 'sleeping', activity_note = NULL, activity_at = NULL,
           score = NULL, score_owner_avg = NULL, score_components = NULL, rank_in_department = NULL,
           score_updated_at = NULL, version = version + 1
     WHERE activity <> 'sleeping' OR activity_note IS NOT NULL OR activity_at IS NOT NULL
        OR score IS NOT NULL OR score_owner_avg IS NOT NULL OR score_components IS NOT NULL
        OR rank_in_department IS NOT NULL OR score_updated_at IS NOT NULL""",
    # every thread stays (one per role, made by the templates), empty
    """UPDATE msg.threads SET last_seq = 0, last_message_at = NULL, owner_read_seq = 0
     WHERE last_seq <> 0 OR last_message_at IS NOT NULL OR owner_read_seq <> 0""",
    # an open incident keeps watching its site; its work item is gone
    "UPDATE ops.incidents SET work_id = NULL WHERE work_id IS NOT NULL",
)

# The ref sequences no table owns (nextval in the code): what they number.
REF_RESET: tuple[str, ...] = (
    "academy.teaching_ref_seq", "advisor.memo_ref_seq",
    "archive.hold_ref_seq", "archive.party_ref_seq", "archive.record_ref_seq",
    "cartable.decision_ref_seq", "cartable.deliverable_ref_seq",
    "core.founding_ref_seq",
    "feedback.item_ref_seq",
    "governance.batch_ref_seq", "governance.outcome_ref_seq",
    "growth.rescue_ref_seq",
    "knowledge.ask_ref_seq", "knowledge.lesson_ref_seq",
    "legal.case_ref_seq",
    "media.item_ref_seq", "media.series_ref_seq",
    "meetings.meeting_ref_seq", "meetings.request_ref_seq",
    "oversight.challenge_ref_seq", "oversight.finding_ref_seq", "oversight.hold_ref_seq",
    "oversight.inquiry_ref_seq", "oversight.order_ref_seq",
    "owner.errand_ref_seq", "owner.note_ref_seq", "owner.order_ref_seq", "owner.planner_ref_seq",
    "owner.review_ref_seq", "owner.story_ref_seq",
    "people.hr_round_ref_seq", "people.role_draft_ref_seq",
    "quality.claim_ref_seq",
    "reports.briefing_ref_seq",
    "substitutes.creative_ref_seq",
    "support.conversation_ref_seq",
    "work.work_ref_seq",
    "workshop.approval_ref_seq", "workshop.grant_ref_seq", "workshop.session_ref_seq",
)  # fmt: skip
REF_KEEP: tuple[str, ...] = (
    "archive.automation_ref_seq", "archive.folder_ref_seq", "archive.reminder_ref_seq",
    "archive.retention_ref_seq",
    "dceo.principle_ref_seq",
    "governance.calendar_ref_seq", "governance.key_result_ref_seq", "governance.objective_ref_seq",
    "governance.risk_ref_seq",
    "growth.rule_ref_seq", "growth.template_ref_seq",
    "knowledge.entry_ref_seq", "knowledge.skill_ref_seq",
    "ops.incident_ref_seq",
    "provisioning.plan_ref_seq",
    "support.kb_ref_seq",
)  # fmt: skip

SNAPSHOT = re.compile(r"^[0-9a-f]{8,64}$")
HASH = re.compile(r"^[0-9a-f]{64}$")


def _array(names: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{n}'" for n in names) + "]::text[]"


def _quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def summary(snapshot: str, previous_seq: int, previous_hash: str) -> str:
    return (
        f"fresh start: the owner's decision of 2026-10-29 ({DECISION}); every employee stays, "
        f"what ran starts at zero; snapshot {snapshot}; "
        f"previous chain seq {previous_seq} hash {previous_hash}"
    )[:500]


def body(snapshot: str, previous_seq: int, previous_hash: str) -> str:
    """The statements, without BEGIN/COMMIT (the tests run them and roll back)."""
    if not SNAPSHOT.match(snapshot):
        raise ValueError("snapshot: a restic snapshot id")
    if previous_seq < 0 or not HASH.match(previous_hash):
        raise ValueError("previous head: a seq and a sha256")
    wipe, kept = _array(WIPE), _array(KEEP + ASK)
    deletes = "\n".join(f"DELETE FROM {t};" for t in WIPE)  # noqa: S608 - the listed names
    resets = "\n".join(f"{s};" for s in RESET)
    restarts = "\n".join(f"ALTER SEQUENCE {s} RESTART;" for s in REF_RESET)
    return f"""
SET LOCAL lock_timeout = '30s';
DO $guard$
DECLARE
    listed text[] := {wipe} || {kept};
    refs text[] := {_array(REF_RESET)} || {_array(REF_KEEP)};
    missing text;
BEGIN
    SELECT string_agg(t, ', ') INTO missing FROM unnest(listed) t WHERE to_regclass(t) IS NULL;
    IF missing IS NOT NULL THEN RAISE EXCEPTION 'fresh start: no such table: %', missing; END IF;
    SELECT string_agg(t, ', ') INTO missing FROM unnest(refs) t WHERE to_regclass(t) IS NULL;
    IF missing IS NOT NULL THEN RAISE EXCEPTION 'fresh start: no such sequence: %', missing; END IF;
    SELECT string_agg(format('%I.%I', n.nspname, c.relname), ', ') INTO missing
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.relkind IN ('r', 'p') AND NOT c.relispartition
       AND n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg\\_%'
       AND format('%I.%I', n.nspname, c.relname) <> ALL (listed);
    IF missing IS NOT NULL THEN RAISE EXCEPTION 'fresh start: tables in no list: %', missing; END IF;
    SELECT string_agg(format('%I.%I', n.nspname, c.relname), ', ') INTO missing
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.relkind = 'S' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
       AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype IN ('a', 'i'))
       AND format('%I.%I', n.nspname, c.relname) <> ALL (refs);
    IF missing IS NOT NULL THEN RAISE EXCEPTION 'fresh start: sequences in no list: %', missing; END IF;
END $guard$;

-- The tables' own guards (append-only, no delete, sealed) are off for this
-- transaction only; the foreign keys are checked below instead.
SET LOCAL session_replication_role = replica;
CREATE TEMP TABLE fresh_start_blobs ON COMMIT DROP AS
    SELECT storage_key FROM archive.record_files WHERE storage_key IS NOT NULL;
-- An uploaded file goes when only wiped rows used it (with its variants).
CREATE TEMP TABLE fresh_start_files (id uuid PRIMARY KEY) ON COMMIT DROP;
DO $files$
DECLARE k record;
BEGIN
    FOR k IN SELECT format('%I.%I', cn.nspname, cr.relname) AS child, a.attname AS col
               FROM pg_constraint c
               JOIN pg_class cr ON cr.oid = c.conrelid JOIN pg_namespace cn ON cn.oid = cr.relnamespace
               JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
              WHERE c.contype = 'f' AND c.confrelid = 'files.files'::regclass
                AND cardinality(c.conkey) = 1
                AND format('%I.%I', cn.nspname, cr.relname) = ANY ({wipe})
    LOOP
        EXECUTE format('INSERT INTO fresh_start_files SELECT DISTINCT %I FROM %s WHERE %I IS NOT NULL
                        ON CONFLICT DO NOTHING', k.col, k.child, k.col);
    END LOOP;
    INSERT INTO fresh_start_files SELECT DISTINCT unnest(attachments) FROM msg.messages
        ON CONFLICT DO NOTHING;
    -- a file a kept row uses stays, even if a message carried it too
    FOR k IN SELECT format('%I.%I', cn.nspname, cr.relname) AS child, a.attname AS col
               FROM pg_constraint c
               JOIN pg_class cr ON cr.oid = c.conrelid JOIN pg_namespace cn ON cn.oid = cr.relnamespace
               JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
              WHERE c.contype = 'f' AND c.confrelid = 'files.files'::regclass
                AND cardinality(c.conkey) = 1 AND c.conrelid <> 'files.files'::regclass
                AND format('%I.%I', cn.nspname, cr.relname) <> ALL ({wipe})
    LOOP
        EXECUTE format('DELETE FROM fresh_start_files f USING %s x WHERE x.%I = f.id', k.child, k.col);
    END LOOP;
    INSERT INTO fresh_start_files SELECT id FROM files.files
     WHERE parent_id IN (SELECT id FROM fresh_start_files) ON CONFLICT DO NOTHING;
END $files$;
INSERT INTO fresh_start_blobs SELECT storage_key FROM files.files WHERE id IN (SELECT id FROM fresh_start_files);
{deletes}
DELETE FROM files.processing WHERE file_id IN (SELECT id FROM fresh_start_files);
DELETE FROM files.files WHERE id IN (SELECT id FROM fresh_start_files);
{resets}
{restarts}
DO $owned$
DECLARE s text;
BEGIN
    FOR s IN SELECT format('%I.%I', sn.nspname, sc.relname)
               FROM pg_depend d
               JOIN pg_class sc ON sc.oid = d.objid AND sc.relkind = 'S'
               JOIN pg_namespace sn ON sn.oid = sc.relnamespace
               JOIN pg_class t ON t.oid = d.refobjid
               JOIN pg_namespace tn ON tn.oid = t.relnamespace
              WHERE d.deptype IN ('a', 'i') AND format('%I.%I', tn.nspname, t.relname) = ANY ({wipe})
    LOOP
        EXECUTE format('ALTER SEQUENCE %s RESTART', s);
    END LOOP;
END $owned$;
SET LOCAL session_replication_role = origin;

DO $keys$
DECLARE
    k record;
    n bigint;
    bad text := '';
BEGIN
    -- every foreign key from a kept table into a wiped one (or into files)
    FOR k IN SELECT c.conname, format('%I.%I', cn.nspname, cr.relname) AS child,
                    format('%I.%I', pn.nspname, pr.relname) AS parent,
                    (SELECT string_agg(format('x.%I IS NOT NULL', ca.attname), ' AND ')
                       FROM unnest(c.conkey) col JOIN pg_attribute ca
                         ON ca.attrelid = c.conrelid AND ca.attnum = col) AS present,
                    (SELECT string_agg(format('p.%I = x.%I', pa.attname, ca.attname), ' AND ')
                       FROM unnest(c.conkey, c.confkey) AS u(ck, fk)
                       JOIN pg_attribute ca ON ca.attrelid = c.conrelid AND ca.attnum = u.ck
                       JOIN pg_attribute pa ON pa.attrelid = c.confrelid AND pa.attnum = u.fk) AS same
               FROM pg_constraint c
               JOIN pg_class cr ON cr.oid = c.conrelid JOIN pg_namespace cn ON cn.oid = cr.relnamespace
               JOIN pg_class pr ON pr.oid = c.confrelid JOIN pg_namespace pn ON pn.oid = pr.relnamespace
              WHERE c.contype = 'f'
                AND format('%I.%I', pn.nspname, pr.relname) = ANY ({wipe} || ARRAY['files.files'])
                AND format('%I.%I', cn.nspname, cr.relname) <> ALL ({wipe})
    LOOP
        EXECUTE format('SELECT count(*) FROM %s x WHERE %s AND NOT EXISTS (SELECT 1 FROM %s p WHERE %s)',
                       k.child, k.present, k.parent, k.same) INTO n;
        IF n > 0 THEN bad := bad || format('%s (%s rows) ', k.conname, n); END IF;
    END LOOP;
    IF bad <> '' THEN RAISE EXCEPTION 'fresh start: kept rows point at wiped data: %', bad; END IF;
END $keys$;

-- The audit chain starts again: its first row is this fresh start.
UPDATE audit.chain_head SET last_seq = 0, last_hash = '{GENESIS}' WHERE id = 1;
INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action, action_class,
                           target_kind, target_ref, summary)
SELECT 'system', 'fresh-start', 'system', id, 'hub.fresh_start', 'A3', 'hub', {_quote("snapshot:" + snapshot)},
       {_quote(summary(snapshot, previous_seq, previous_hash))}
  FROM core.companies WHERE kind = 'holding';
DO $chain$
BEGIN
    IF NOT (SELECT ok FROM audit.verify_chain()) OR (SELECT last_seq FROM audit.chain_head) <> 1 THEN
        RAISE EXCEPTION 'fresh start: the new chain does not verify';
    END IF;
END $chain$;
SELECT 'blob ' || storage_key FROM fresh_start_blobs;
SELECT 'head ' || last_seq || ' ' || last_hash FROM audit.chain_head;
"""  # noqa: S608 - module constants; the snapshot and the head are checked above


def script(snapshot: str, previous_seq: int, previous_hash: str) -> str:
    return (
        "\\set ON_ERROR_STOP on\nBEGIN;\n"
        + body(snapshot, previous_seq, previous_hash)
        + "COMMIT;\n"
    )


async def anchor(snapshot: str, previous_seq: int, previous_hash: str) -> dict[str, Any]:
    """The new chain's first anchor, carrying the old chain's last anchor and
    head (the anchor file is append-only: nothing in it is ever rewritten)."""
    from hq_api.companies import Companies
    from hq_api.config import Settings
    from hq_api.db import Database

    s = Settings()
    if not s.audit_anchor_file:
        raise ValueError("HQ_AUDIT_ANCHOR_FILE is not set")
    db = Database.create(s, pool_size=1)
    try:
        async with db.tx(await Companies(db, ttl_s=0).ids()) as tx:
            first = await tx.first("SELECT action, target_ref FROM audit.entries WHERE seq = 1")
            head = await tx.one(
                "SELECT last_seq AS seq, last_hash AS hash, now() AS at FROM audit.chain_head"
            )
            chain = await tx.one("SELECT ok FROM audit.verify_chain()")
    finally:
        await db.close()
    if (
        first is None
        or first["action"] != "hub.fresh_start"
        or first["target_ref"] != f"snapshot:{snapshot}"
    ):
        raise ValueError("the chain does not start with this fresh start")
    if not chain["ok"]:
        raise ValueError("the new chain does not verify")
    line = {
        "seq": head["seq"],
        "hash": head["hash"],
        "at": head["at"].isoformat(),
        "fresh_start": True,
        "snapshot": snapshot,
        "previous": audit.last_anchor(s.audit_anchor_file),
        "previous_head": {"seq": previous_seq, "hash": previous_hash},
    }
    await asyncio.to_thread(audit._append, Path(s.audit_anchor_file), json.dumps(line))
    return {"seq": head["seq"]}


async def blobs(keys: list[str]) -> int:
    """Remove the stored files of the wiped rows (in the api: its storage root)."""
    from hq_api.config import Settings
    from hq_api.storage import LocalStorage

    store = LocalStorage(Settings().files_root)
    gone = 0
    for key in keys:
        if not re.fullmatch(r"[0-9a-f]{32}", key):
            raise ValueError("a storage key is 32 hex characters")
        gone += int(await store.destroy(key))
    return gone


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, text in (("sql", "print the script for psql"), ("anchor", "append the first anchor")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--snapshot", required=True)
        p.add_argument("--previous-seq", type=int, required=True)
        p.add_argument("--previous-hash", required=True)
    sub.add_parser("blobs", help="remove the stored files named on stdin")
    args = parser.parse_args()
    try:
        if args.cmd == "sql":
            sys.stdout.write(script(args.snapshot, args.previous_seq, args.previous_hash))
        elif args.cmd == "anchor":
            body(args.snapshot, args.previous_seq, args.previous_hash)  # the same checks
            out = asyncio.run(anchor(args.snapshot, args.previous_seq, args.previous_hash))
            print(f"fresh-start: anchored seq {out['seq']}")
        else:
            n = asyncio.run(blobs(sys.stdin.read().split()))
            print(f"fresh-start: {n} stored file(s) removed")
    except ValueError as e:
        print(f"fresh-start: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
