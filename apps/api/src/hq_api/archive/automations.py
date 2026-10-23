"""The archive's automations (prompt 14 §6, contract §23.7, §23.12): rules
only, never a model. An event of the closed list (filed, sealed,
reminder_due, retention_due, hold_set, version_added) runs every active
automation whose `when` matches the record (class, scope, a minimum level,
one field condition), in the transaction of the event; each run is one
`archive.automation_runs` row and one audit row.

Actions: notify (the owner or a role's holders; info, report or decision,
never urgent), work_item (a role of the hub; it waits while the holding or
the record's company is locked: `deferred`, no run is woken), link,
move_to_folder, raise_level (only up; a level that encrypts is the owner's
PATCH, with its re-store), add_reminder. An action never fires another
automation.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from hq_api import audit
from hq_api.archive.common import SERVICE, J, dumps
from hq_api.db import Tx
from hq_api.domain import gate
from hq_api.errors import ApiError

_RUNNING: set[str] = set()  # records an automation is acting on (no recursion)


def _cmp(op: str, have: Any, want: Any) -> bool:
    if have is None:
        return False
    if isinstance(have, dict):
        have = have.get("amount", have.get("to", have.get("ref")))
    if op == "contains":
        if isinstance(have, list):
            return want in have
        return str(want).lower() in str(have).lower()
    if op == "eq":
        return str(have) == str(want)
    try:
        a, b = Decimal(str(have)), Decimal(str(want))
    except InvalidOperation:
        a, b = str(have), str(want)  # type: ignore[assignment]
    return a < b if op == "lt" else a > b


async def matches(tx: Tx, when: dict[str, Any], r: dict[str, Any]) -> bool:
    if "class" in when and when["class"] != r["class_key"]:
        return False
    if "scope" in when and when["scope"] != r["scope"]:
        return False
    if "level_min" in when:
        rank = await tx.scalar("SELECT rank FROM archive.levels WHERE key = :k", k=when["level_min"])
        if rank is None or r["level_rank"] < int(rank):
            return False
    f = when.get("field")
    if f:
        return _cmp(f["op"], J(r["metadata"], {}).get(f["key"]), f["value"])
    return True


async def _holders(tx: Tx, role: str, company_id: Any) -> list[dict[str, Any]]:
    """The active employees on charter `role` in the record's company, else
    in the holding (a holding role)."""
    return await tx.all(
        """SELECT e.id, e.code, e.company_id, c.code AS company FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id
           WHERE e.role = :r AND e.status = 'active'
             AND (e.company_id = :co OR c.kind = 'holding')
           ORDER BY (e.company_id = :co) DESC, e.created_at LIMIT 3""",
        r=role, co=company_id,
    )  # fmt: skip


async def act(tx: Tx, a: dict[str, Any], r: dict[str, Any], title: str) -> dict[str, Any]:
    from hq_api.archive import records as R
    from hq_api.domain import notify
    from hq_api.domain import work as W

    action, args = a["action"], a.get("args") or {}
    if action == "notify":
        level = args.get("level", "info")
        if level == "urgent":  # never, whatever the row says
            level = "report"
        to = args.get("to", "owner")
        if to != "owner":
            holders = await _holders(tx, to, r["company_id"])
            if not holders:
                return {"action": action, "outcome": "skipped", "why": "no holder of that role"}
            if await gate.automation_lock(tx, r["company_id"]) is not None:
                return {"action": action, "outcome": "deferred", "why": "locked"}
            for h in holders[:1]:
                await W.create(
                    tx, SERVICE, company_id=h["company_id"], company_code=h["company"],
                    title=f"{r['ref']}: {args.get('text_fa', '')}"[:300], brief=f"{title}\n\n{args.get('text_fa', '')}",
                    kind="one_off", priority="P4", assignee_code=h["code"],
                )  # fmt: skip
            return {"action": action, "outcome": "done", "to": to}
        await notify.raise_notification(
            tx, company_id=r["company_id"], company_code=r["scope"], level=level,
            title_fa=f"بایگانی {r['ref']}: {args.get('text_fa', '')}"[:200], body_fa=title[:500],
            link_kind="archive_record", link_ref=r["ref"], source_kind="service", source_code="archive",
        )  # fmt: skip
        return {"action": action, "outcome": "done"}
    if action == "work_item":
        if await gate.automation_lock(tx, r["company_id"]) is not None:
            return {"action": action, "outcome": "deferred", "why": "locked"}
        holders = await _holders(tx, args["role"], r["company_id"])
        if not holders:
            return {"action": action, "outcome": "skipped", "why": "no holder of that role"}
        h = holders[0]
        w = await W.create(
            tx, SERVICE, company_id=h["company_id"], company_code=h["company"],
            title=f"{args['title_fa']} ({r['ref']})"[:300],
            brief=f"Archive automation «{title}» for record {r['ref']} ({r['class_key']}). Read it with archive.read.",
            kind="one_off", priority="P3", assignee_code=h["code"],
        )  # fmt: skip
        return {"action": action, "outcome": "done", "work": w["ref"]}
    if action == "link":
        got = await R.add_link(tx, SERVICE, r, args["kind"], args["to"], quiet=True)
        return {"action": action, "outcome": "done" if got else "skipped"}
    if action == "move_to_folder":
        f = await tx.first(
            "SELECT id, company_id FROM archive.folders WHERE ref = :f AND status = 'active'", f=args["folder"]
        )
        if f is None or f["company_id"] != r["company_id"] or r["state"] in ("sealed", "disposed"):
            return {"action": action, "outcome": "skipped", "why": "not a folder of this scope, or sealed"}
        await tx.exec("UPDATE archive.records SET folder_id = :f WHERE id = :id", f=f["id"], id=r["id"])
        return {"action": action, "outcome": "done"}
    if action == "raise_level":
        lv = await tx.first("SELECT key, rank, encrypt FROM archive.levels WHERE key = :k", k=args["level"])
        if lv is None or lv["rank"] <= r["level_rank"]:
            return {"action": action, "outcome": "skipped", "why": "only up"}
        cur = await tx.scalar("SELECT encrypt FROM archive.levels WHERE key = :k", k=r["level"])
        if lv["encrypt"] and not cur:
            return {"action": action, "outcome": "skipped", "why": "an encrypting level is the owner's PATCH"}
        await tx.exec(
            "UPDATE archive.records SET level = :l, level_rank = :lr WHERE id = :id",
            l=lv["key"], lr=lv["rank"], id=r["id"],
        )  # fmt: skip
        await R.log_access(tx, SERVICE, r, "level", level_from=r["level"], level_to=lv["key"])
        return {"action": action, "outcome": "done"}
    if action == "add_reminder":
        from hq_api.archive import vocab as V

        fields = await R.class_fields(tx, r)
        f = next((x for x in fields if x["key"] == args["field"]), None)
        at = V.field_dates(f, J(r["metadata"], {}).get(args["field"]))
        if at is None:
            return {"action": action, "outcome": "skipped", "why": "no date in that field"}
        lead = int(args["lead_days"])
        n = await tx.exec(
            """INSERT INTO archive.reminders (company_id, record_id, field, at, lead_days, due_at, channel, to_whom)
               VALUES (:co, :r, :f, :at, :ld, :due, 'cartable', CAST('"owner"' AS jsonb))
               ON CONFLICT (record_id, field, at, lead_days) DO NOTHING""",
            co=r["company_id"], r=r["id"], f=args["field"], at=at, ld=lead, due=at - timedelta(days=lead),
        )  # fmt: skip
        return {"action": action, "outcome": "done" if n else "skipped"}
    raise ApiError(422, "schema_invalid", f"unknown action {action}")


async def fire(tx: Tx, event: str, r: dict[str, Any]) -> int:
    """Every active automation on `event` whose condition matches -> runs."""
    if r["ref"] in _RUNNING or r["state"] == "disposed":
        return 0
    autos = await tx.all(
        "SELECT * FROM archive.automations WHERE on_event = :e AND status = 'active' ORDER BY ref", e=event
    )
    ran = 0
    for au in autos:
        if not await matches(tx, J(au["when_cond"], {}), r):
            continue
        _RUNNING.add(r["ref"])
        results = []
        try:
            for a in J(au["actions"], []):
                try:
                    results.append(await act(tx, a, r, au["title_fa"]))
                except ApiError as exc:
                    results.append({"action": a.get("action"), "outcome": "failed", "why": exc.code})
        finally:
            _RUNNING.discard(r["ref"])
        outcomes = {x["outcome"] for x in results}
        outcome = (
            "done" if outcomes <= {"done", "skipped"}
            else "deferred" if outcomes <= {"done", "skipped", "deferred"} and "deferred" in outcomes
            else "failed" if outcomes == {"failed"} else "partial"
        )  # fmt: skip
        await tx.exec(
            """INSERT INTO archive.automation_runs (company_id, automation_id, record_ref, event, outcome, actions)
               VALUES (:co, :a, :r, :e, :o, CAST(:x AS jsonb))""",
            co=au["company_id"], a=au["id"], r=r["ref"], e=event, o=outcome, x=dumps(results),
        )  # fmt: skip
        await audit.record(
            tx, SERVICE, company_id=r["company_id"], action="archive.automation", action_class="A1",
            target_kind="archive_record", target_ref=r["ref"], summary=f"{au['ref']} on {event}: {outcome}",
        )  # fmt: skip
        ran += 1
    return ran
