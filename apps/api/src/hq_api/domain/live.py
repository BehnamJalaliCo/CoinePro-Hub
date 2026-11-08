"""The holding live (contract §42 ⟨1.24⟩; design/LIVE_VIEWS.md §3, §5; the owner, 2026-11-08:
«نقشه نشون بده کدوم شرکت به کدوم وصل شد قطع شد … همه جای آپ باشه»).

    holding.flow       what crosses the hub between companies (topic `holding`): an owner order
                       routed to its holder, a cross-company work asked, accepted or delivered
                       back (A → hub → B), another company's data read for a work, a playbook
                       given to another company, a line publishing to the world. `from` and `to`
                       are "hub" (the holding is the hub), a company code or "outside"; the
                       envelope's company is the holding's (it is the holding's map).
    employee.state     each employee's §29.14 state (routes/org.employee_states, the one rule),
                       derived again after an event that says its run, activity or server job
                       moved (events.MOVED, in the writer's transaction) and told only on a
                       change: at most once per employee per 2 s (a change inside the window waits
                       as `pending` for the worker's flush), `stuck` and `done` at once. A
                       reconcile every 30 s catches what no such event says (a card decided, a
                       lock, the day turning).
    GET /live/summary  the seed of every live view: a fixed handful of aggregate queries for any
                       number of companies; `seq` is the stream's last sequence, read first, so
                       the client resumes right after it (`Last-Event-ID`) and loses nothing.

Metadata and plain Persian labels only (§7): never a message body, a title someone wrote, a
secret, a hostname or an address. Nothing here knows a company code or how many there are.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from hq_api import events
from hq_api.db import Tx
from hq_api.domain.work import CACHE_READ_SHARE

log = logging.getLogger("hq_api.live")

FlowKind = Literal["order", "request", "accept", "deliver", "read", "playbook", "publish"]
State = Literal["idle", "thinking", "working", "waiting", "stuck", "done"]
LABEL_MAX = 60
EMPLOYEE_WINDOW_S = 2.0  # at most one employee.state per employee in this window
AT_ONCE = ("stuck", "done")  # ... but these go out at once
BUSY = ("thinking", "working", "waiting", "stuck")  # the states that name a work
FLUSH_S = 1.0
RECONCILE_S = 30.0
ONLINE_S = 90  # domain/servers.ONLINE_S: three missed polls
LAST_EVENTS = 20_000  # the newest outbox rows a company's last event is looked for in


def iso(at: datetime | None) -> str | None:
    if at is None:
        return None
    return at.astimezone(UTC).isoformat().replace("+00:00", "Z")


def label(text: str | None) -> str | None:
    """A flow's plain Persian label: one line, at most 60 characters, or None."""
    one = " ".join(str(text or "").split())
    if not one:
        return None
    return one if len(one) <= LABEL_MAX else one[: LABEL_MAX - 1].rstrip() + "…"


async def holding_code(tx: Tx) -> str:
    return str(
        await tx.scalar(
            "SELECT code FROM core.companies WHERE kind = 'holding' ORDER BY created_at LIMIT 1"
        )
    )


async def name_of(tx: Tx, code: str) -> str:
    """A company's Persian name (its code when it has none); «هاب» for the hub."""
    if code == "hub":
        return "هاب"
    row = await tx.first(
        "SELECT kind, COALESCE(name_fa, code) AS n FROM core.companies WHERE code = :c", c=code
    )
    if row is None:
        return code
    return "هاب" if row["kind"] == "holding" else str(row["n"])


# ------------------------------------------------------------- holding.flow --
async def flow(
    tx: Tx,
    *,
    src: str,
    dst: str,
    kind: FlowKind,
    ref: str,
    root_ref: str | None = None,
    label_fa: str | None = None,
) -> bool:
    """`holding.flow` in the writer's transaction. Either end is "hub", "outside" or a company
    code (the holding's own code is the hub). False when nothing crosses the hub."""
    holding = await holding_code(tx)
    a = "hub" if src in ("hub", holding) else src
    b = "hub" if dst in ("hub", holding) else dst
    if a == b:
        return False
    await events.emit(
        tx,
        holding,
        "holding.flow",
        ref,
        {
            "from": a,
            "to": b,
            "kind": kind,
            "via": "hub",
            "ref": ref,
            "root_ref": root_ref,
            "label_fa": label(label_fa),
        },
    )
    return True


REQUESTER_SQL = """
    SELECT c.code AS company, COALESCE(rt.ref, r.ref) AS root_ref
    FROM work.work r JOIN core.companies c ON c.id = r.company_id
    LEFT JOIN work.work rt ON rt.id = r.root_id
    WHERE r.id = :id
"""


async def requester(tx: Tx, work_id: UUID | None) -> dict[str, Any] | None:
    """The company of the work that asked for another (`requested_by_work_id`) and its root's
    ref, when this transaction sees it."""
    if work_id is None:
        return None
    row = await tx.first(REQUESTER_SQL, id=work_id)
    return dict(row) if row is not None else None


async def work_flow(
    tx: Tx, kind: Literal["request", "accept", "deliver"], w: dict[str, Any], asker: dict[str, Any]
) -> bool:
    """A cross-company work (A asked B through the hub): `request` A → B when it is created,
    `accept` and `deliver` B → A. `asker`: `requester()` of the work's `requested_by_work_id`."""
    a, b = str(asker["company"]), str(w["company"])
    if a == b:
        return False
    a_fa, b_fa = await name_of(tx, a), await name_of(tx, b)
    if kind == "request":
        return await flow(tx, src=a, dst=b, kind=kind, ref=w["ref"], root_ref=asker["root_ref"],
                          label_fa=f"درخواست کار از {a_fa} به {b_fa}")  # fmt: skip
    text = f"{b_fa} کار {a_fa} را پذیرفت" if kind == "accept" else f"{b_fa} کار {a_fa} را تحویل داد"
    return await flow(
        tx, src=b, dst=a, kind=kind, ref=w["ref"], root_ref=asker["root_ref"], label_fa=text
    )


# What was read, in the label «‹reader› ‹what› ‹owner› را خواند».
READ_FA = {
    "profile": "معرفی",
    "kpis": "شاخص‌های",
    "outputs": "خروجی‌های",
    "catalogue": "فهرست",
    "connections": "اتصال‌های",
    "links": "پیوندهای",
    "knowledge": "دانسته‌های",
    "file": "فایل فرمان",
}


async def read_flow(
    tx: Tx, *, owner: str, reader: str, ref: str, root_ref: str | None, what_fa: str
) -> bool:
    """Another company's data read for a work: data owner → hub → reader ("hub" is the
    holding's data, e.g. a file the owner gave the order)."""
    if owner == reader:
        return False
    o_fa, r_fa = await name_of(tx, owner), await name_of(tx, reader)
    return await flow(tx, src=owner, dst=reader, kind="read", ref=ref, root_ref=root_ref,
                      label_fa=f"{r_fa} {what_fa} {o_fa} را خواند")  # fmt: skip


async def playbook_flow(tx: Tx, row: dict[str, Any], company: str, root_ref: str | None) -> bool:
    """A playbook given to another company: from the company whose session made it (the hub
    when none) to the company that receives it. `root_ref`: the session that adapts it, if any."""
    src = row.get("source")
    if isinstance(src, str):
        src = json.loads(src)
    origin = str((src or {}).get("company") or "hub")
    to_fa = await name_of(tx, company)
    return await flow(tx, src=origin, dst=company, kind="playbook", ref=str(row["ref"]),
                      root_ref=root_ref, label_fa=f"کارگروه به {to_fa} داده شد")  # fmt: skip


PLATFORM_FA = {
    "instagram": "اینستاگرام",
    "youtube": "یوتیوب",
    "telegram": "تلگرام",
    "site": "سایت",
    "x": "ایکس",
    "linkedin": "لینکدین",
}


async def publish_flow(tx: Tx, run: dict[str, Any], published: list[dict[str, Any]]) -> bool:
    """A line published to the world: its company → outside."""
    platform = str((published[0] if published else {}).get("platform") or run.get("platform") or "")
    where = PLATFORM_FA.get(platform)
    return await flow(tx, src=str(run["company"]), dst="outside", kind="publish", ref=str(run["ref"]),
                      label_fa=f"انتشار در {where}" if where else "انتشار بیرونی")  # fmt: skip


async def run_work(tx: Tx, run_id: str | None) -> dict[str, Any] | None:
    """The work an agent's run is on and its root (for a read's `ref`), when there is one."""
    if not run_id:
        return None
    row = await tx.first(
        """SELECT w.ref, COALESCE(rt.ref, w.ref) AS root_ref FROM agents.runs r
           JOIN work.work w ON w.id = r.work_id LEFT JOIN work.work rt ON rt.id = w.root_id
           WHERE r.id = CAST(:id AS uuid)""",
        id=run_id,
    )
    return dict(row) if row is not None else None


# ----------------------------------------------------------- employee.state --
REFS_SQL = """
    SELECT e.id, e.code, e.company_id, c.code AS company, d.code AS department,
           cur.ref AS work_ref, cur.root_ref
    FROM core.employees e JOIN core.companies c ON c.id = e.company_id
    LEFT JOIN core.departments d ON d.id = e.department_id
    LEFT JOIN LATERAL (
        SELECT w.ref, COALESCE(rt.ref, w.ref) AS root_ref
        FROM work.work w LEFT JOIN work.work rt ON rt.id = w.root_id
        WHERE w.id = COALESCE(
            (SELECT r.work_id FROM agents.runs r
              WHERE r.employee_id = e.id AND r.state = 'running' AND r.work_id IS NOT NULL
              ORDER BY r.started_at DESC NULLS LAST LIMIT 1),
            (SELECT o.id FROM work.work o
              WHERE o.assignee_id = e.id AND o.status IN ('queued', 'in_progress', 'waiting')
              ORDER BY o.updated_at DESC LIMIT 1))
    ) cur ON true
    WHERE e.id = ANY(:ids)
"""


async def derive(tx: Tx, ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    """Each employee's §29.14 state (the one rule: routes/org.employee_states) and what the
    stream says besides: the company, the department, the work it is on and its root."""
    if not ids:
        return {}
    from hq_api.routes.org import employee_states

    states = await employee_states(tx, ids)
    out: dict[UUID, dict[str, Any]] = {}
    for r in await tx.all(REFS_SQL, ids=ids):
        st = states.get(r["id"])
        if st is None:
            continue
        state = str(st["state"])
        stuck = st.get("stuck")
        busy = state in BUSY
        out[r["id"]] = {
            "employee": r["code"],
            "company": r["company"],
            "company_id": r["company_id"],
            "department": r["department"],
            "state": state,
            "work_ref": r["work_ref"] if busy else None,
            "root_ref": r["root_ref"] if busy else None,
            "stuck_fa": (stuck.reason_fa[:300] if state == "stuck" and stuck is not None else None),
        }
    return out


def _same(row: dict[str, Any] | None, d: dict[str, Any]) -> bool:
    if row is None:
        return bool(d["state"] == "idle")
    return all(row[k] == d[k] for k in ("state", "work_ref", "root_ref", "stuck_fa"))


async def _emit_state(tx: Tx, d: dict[str, Any], since: datetime) -> None:
    await events.emit(
        tx,
        d["company"],
        "employee.state",
        d["employee"],
        {
            "employee": d["employee"],
            "company": d["company"],
            "department": d["department"],
            "state": d["state"],
            "since": iso(since),
            "work_ref": d["work_ref"],
            "root_ref": d["root_ref"],
            "stuck_fa": d["stuck_fa"],
        },
    )


LIVE_SQL = """
    SELECT l.*, l.sent_at > now() - make_interval(secs => :w) AS recent
    FROM core.employee_live l WHERE l.employee_id = :e FOR UPDATE
"""


async def apply(tx: Tx, ids: list[UUID], derived: dict[UUID, dict[str, Any]] | None = None) -> int:
    """Store each employee's state; a change goes on the stream now (`stuck`, `done`, or the
    first in its window) or waits as `pending` for `flush`. Returns how many went out now."""
    if derived is None:
        derived = await derive(tx, ids)
    sent = 0
    for eid in ids:
        d = derived.get(eid)
        if d is None:
            continue
        cur = await tx.first(LIVE_SQL, e=eid, w=EMPLOYEE_WINDOW_S)
        if cur is None:
            if d["state"] == "idle":
                continue  # nothing to tell: an employee never seen is idle
            await tx.exec(
                """INSERT INTO core.employee_live (employee_id, company_id, state)
                   VALUES (:e, :co, 'idle') ON CONFLICT (employee_id) DO NOTHING""",
                e=eid,
                co=d["company_id"],
            )
            cur = await tx.one(LIVE_SQL, e=eid, w=EMPLOYEE_WINDOW_S)
        if _same(cur, d):
            continue
        now = d["state"] in AT_ONCE or cur["sent_at"] is None or not cur["recent"]
        since = await tx.scalar(
            """UPDATE core.employee_live
               SET since = CASE WHEN state <> CAST(:s AS text) THEN now() ELSE since END,
                   state = CAST(:s AS text), work_ref = :wr, root_ref = :rr, stuck_fa = :why,
                   pending = NOT CAST(:now AS boolean),
                   sent_at = CASE WHEN CAST(:now AS boolean) THEN now() ELSE sent_at END,
                   sent_state = CASE WHEN CAST(:now AS boolean) THEN CAST(:s AS text) ELSE sent_state END,
                   updated_at = now()
               WHERE employee_id = :e RETURNING since""",
            e=eid,
            s=d["state"],
            wr=d["work_ref"],
            rr=d["root_ref"],
            why=d["stuck_fa"],
            now=now,
        )
        if now:
            await _emit_state(tx, d, since)
            sent += 1
    return sent


async def employee_moved(tx: Tx, code: str) -> None:
    """events.MOVED: the employee's state again (skipped when this transaction does not see him)."""
    eid = await tx.scalar("SELECT id FROM core.employees WHERE code = :c", c=code)
    if eid is not None:
        await apply(tx, [eid])


async def flush(tx: Tx, window_s: float = EMPLOYEE_WINDOW_S, limit: int = 500) -> int:
    """The changes that waited for their window: each employee's latest state, once."""
    rows = await tx.all(
        """SELECT l.*, e.code AS employee, c.code AS company, d.code AS department
           FROM core.employee_live l JOIN core.employees e ON e.id = l.employee_id
           JOIN core.companies c ON c.id = l.company_id
           LEFT JOIN core.departments d ON d.id = e.department_id
           WHERE l.pending AND (l.sent_at IS NULL OR l.sent_at <= now() - make_interval(secs => :w))
           ORDER BY l.sent_at NULLS FIRST LIMIT :n FOR UPDATE OF l SKIP LOCKED""",
        w=window_s,
        n=limit,
    )
    for r in rows:
        await tx.exec(
            """UPDATE core.employee_live SET pending = false, sent_at = now(), sent_state = state
               WHERE employee_id = :e""",
            e=r["employee_id"],
        )
        await _emit_state(tx, dict(r), r["since"])
    return len(rows)


async def reconcile(tx: Tx) -> int:
    """Every active employee's state against the stored one; a difference is applied (what no
    event of events.MOVED tells: a card decided, a lock, the day turning). Four queries for the
    whole holding, then one statement per changed employee."""
    ids = [r["id"] for r in await tx.all("SELECT id FROM core.employees WHERE status = 'active'")]
    derived = await derive(tx, ids)
    stored = {
        r["employee_id"]: dict(r)
        for r in await tx.all(
            "SELECT employee_id, state, work_ref, root_ref, stuck_fa FROM core.employee_live"
        )
    }
    # in one order, as every writer locks its own employee's row only
    moved = sorted(eid for eid, d in derived.items() if not _same(stored.get(eid), d))
    return await apply(tx, moved, derived) if moved else 0


async def loop(hub: Any) -> None:
    """The worker's live loop: every second the states that waited for their window; every 30 s
    the reconcile. A failed pass is logged and the loop goes on."""
    last = 0.0
    while True:
        await asyncio.sleep(FLUSH_S)
        try:
            async with hub.db.tx(await hub.companies.ids()) as tx:
                await flush(tx)
            if time.monotonic() - last >= RECONCILE_S:
                last = time.monotonic()
                async with hub.db.tx(await hub.companies.ids()) as tx:
                    await reconcile(tx)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the live loop never stops the worker
            log.warning("live pass failed")


# ------------------------------------------------------------ /live/summary --
class LivePeople(BaseModel):
    """Active employees by their §29.14 state (idle and done are the rest of `total`)."""

    working: int
    thinking: int
    waiting: int
    stuck: int
    total: int


class LiveSessions(BaseModel):
    """Open sessions (not closed, not hidden) by badge."""

    moving: int
    your_turn: int
    stuck: int
    ready: int


class LiveServers(BaseModel):
    """Servers with a runner, not revoked (`total` counts the pending ones too)."""

    online: int
    offline: int
    total: int


class LiveTokens(BaseModel):
    """Today (the Token Treasury's UTC day): every token; with a cache read at a tenth; those of
    the calls that finished in the last minute; real plus equivalent dollars; the holding's daily
    dollar budget, or null."""

    today: int
    effective_today: int
    per_min: int
    equiv_usd_today: Decimal
    budget_usd: Decimal | None


class LiveControl(BaseModel):
    """The kill switches engaged: the holding's, and the companies'."""

    holding: bool
    companies_locked: list[str]


class LiveCompany(BaseModel):
    """One operating company (the holding is the hub, not a row). `working`: its people thinking
    or working now; `sessions_open`: the open sessions it holds; `last_event_at`: its newest event
    on the stream, null when none is recent; `state`: locked, else stuck (someone is), else busy
    (someone works), else ok."""

    code: str
    name_fa: str
    working: int
    total: int
    sessions_open: int
    servers_online: int
    servers_total: int
    spend_today_usd: Decimal
    last_event_at: datetime | None
    state: Literal["ok", "busy", "stuck", "locked"]


class LiveSummary(BaseModel):
    """§42.3 the seed of the live views (null where nothing is known, never a made-up zero).
    `seq`: the stream's last sequence when read (null only while the event bus is down)."""

    seq: int | None
    at: datetime
    people: LivePeople
    sessions: LiveSessions
    approvals: int
    urgent_unread: int
    servers: LiveServers
    tokens: LiveTokens
    control: LiveControl
    companies: list[LiveCompany]


async def stream_seq(hub: Any) -> int | None:
    """The last sequence of the stream `/stream` serves (its `id:`), or None while the bus is down."""
    bus = hub.bus
    if bus is None or not bus.connected:
        return None
    try:
        info = await bus.js.stream_info(events.STREAM)
    except Exception:  # noqa: BLE001 - the bus answers nothing: the client starts the stream fresh
        return None
    return int(info.state.last_seq)


def day_start(now: datetime) -> datetime:
    """The Token Treasury's day (UTC, as the router's budgets count it)."""
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


SESSIONS_SQL = """
    SELECT r.badge, o.routes -> 0 ->> 'company' AS company, count(*) AS n
    FROM owner.order_reports r JOIN owner.orders o ON o.id = r.order_id
    WHERE r.closed_at IS NULL AND r.hidden_at IS NULL
    GROUP BY 1, 2
"""
OWNER_SQL = """
    SELECT (SELECT count(*) FROM cartable.decisions
             WHERE status = 'pending' AND approver_code IS NULL AND owner_visible) AS approvals,
           (SELECT count(*) FROM notify.notifications
             WHERE level = 'urgent' AND delivered_in_app AND read_at IS NULL AND owner_visible
               AND created_at > now() - interval '7 days') AS urgent,
           (SELECT usd_limit FROM llm.budgets
             WHERE scope_type = 'holding' AND period = 'day' AND enabled AND usd_limit IS NOT NULL
             ORDER BY updated_at DESC LIMIT 1) AS budget_usd
"""
SERVERS_SQL = """
    SELECT company_id,
           count(*) FILTER (WHERE state = 'online'
                              AND last_seen_at > now() - make_interval(secs => :o)) AS online,
           count(*) FILTER (WHERE state <> 'pending' AND NOT (state = 'online'
                              AND last_seen_at > now() - make_interval(secs => :o))) AS offline,
           count(*) AS total
    FROM infra.servers WHERE state IS NOT NULL AND state <> 'revoked'
    GROUP BY company_id
"""
TOKENS_SQL = """
    SELECT company_id,
           COALESCE(sum(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)
                        + COALESCE(cache_read_tokens, 0) + COALESCE(cache_write_tokens, 0)), 0) AS tokens,
           COALESCE(sum(COALESCE(cache_read_tokens, 0)), 0) AS cache_read,
           COALESCE(sum(COALESCE(cost_usd, 0) + COALESCE(equiv_cost_usd, 0)), 0) AS usd,
           COALESCE(sum(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)
                        + COALESCE(cache_read_tokens, 0) + COALESCE(cache_write_tokens, 0))
                    FILTER (WHERE finished_at >= now() - interval '1 minute'), 0) AS last_min
    FROM llm.calls WHERE started_at >= :day
    GROUP BY company_id
"""
LOCKS_SQL = """
    SELECT c.code, c.kind FROM control.kill_switches k JOIN core.companies c ON c.id = k.company_id
    WHERE k.state = 'engaged'
"""
LAST_EVENTS_SQL = """
    SELECT split_part(subject, '.', 3) AS company, max(created_at) AS at FROM core.outbox
    WHERE id > (SELECT COALESCE(max(id), 0) FROM core.outbox) - :n
    GROUP BY 1
"""


def effective(tokens: int, cache_read: int) -> int:
    """§29.6: a cache read counts a tenth (as work.effective_tokens)."""
    return int(tokens) - int(cache_read) + round(int(cache_read) * CACHE_READ_SHARE)


USD = Decimal("0.000001")


def usd(v: Any) -> Decimal:
    """Money as §1 has it: a decimal of 6 places (a JSON string), 0 when nothing was spent."""
    return Decimal(str(v if v not in (None, "") else 0)).quantize(USD)


async def gather(tx: Tx, now: datetime) -> dict[str, Any]:
    """The summary's raw figures, by company id or code: nine queries whatever the number of
    companies (two of them the §29.14 rule over every active employee)."""
    from hq_api.routes.org import employee_states

    emps = await tx.all("SELECT id, company_id FROM core.employees WHERE status = 'active'")
    states = await employee_states(tx, [r["id"] for r in emps])
    return {
        "employees": [
            {"company_id": r["company_id"], "state": str(states[r["id"]]["state"])}
            for r in emps
            if r["id"] in states
        ],
        "sessions": [dict(r) for r in await tx.all(SESSIONS_SQL)],
        "owner": dict(await tx.one(OWNER_SQL)),
        "servers": {r["company_id"]: dict(r) for r in await tx.all(SERVERS_SQL, o=ONLINE_S)},
        "tokens": {r["company_id"]: dict(r) for r in await tx.all(TOKENS_SQL, day=day_start(now))},
        "locks": [dict(r) for r in await tx.all(LOCKS_SQL)],
        "last": {r["company"]: r["at"] for r in await tx.all(LAST_EVENTS_SQL, n=LAST_EVENTS)},
    }


def assemble(
    raw: dict[str, Any], companies: list[Any], seq: int | None, now: datetime
) -> LiveSummary:
    """The summary from `gather`'s figures (pure: any number of companies, zero included).
    `companies`: the registry's rows; the holding is the hub, not one of `companies`."""
    people = dict.fromkeys(("working", "thinking", "waiting", "stuck"), 0)
    working: dict[Any, int] = {}
    total: dict[Any, int] = {}
    stuck: set[Any] = set()
    for e in raw["employees"]:
        co, st = e["company_id"], e["state"]
        total[co] = total.get(co, 0) + 1
        if st in people:
            people[st] += 1
        if st in ("thinking", "working"):
            working[co] = working.get(co, 0) + 1
        if st == "stuck":
            stuck.add(co)
    badges = dict.fromkeys(("moving", "your_turn", "stuck", "ready"), 0)
    open_by: dict[str, int] = {}
    for s in raw["sessions"]:
        if s["badge"] in badges:
            badges[s["badge"]] += int(s["n"])
            if s["company"]:
                open_by[s["company"]] = open_by.get(s["company"], 0) + int(s["n"])
    servers = raw["servers"]
    tokens = raw["tokens"]
    held = any(x["kind"] == "holding" for x in raw["locks"])
    locked = sorted(str(x["code"]) for x in raw["locks"] if x["kind"] != "holding")
    owner = raw["owner"]
    all_tokens = sum(int(t["tokens"]) for t in tokens.values())
    all_cache = sum(int(t["cache_read"]) for t in tokens.values())
    budget = owner.get("budget_usd")
    out: list[LiveCompany] = []
    for c in companies:
        if c.kind == "holding" or c.status not in ("active", "paused"):
            continue
        sv = servers.get(c.id) or {}
        w = working.get(c.id, 0)
        state: Literal["ok", "busy", "stuck", "locked"] = "ok"
        if held or c.code in locked:
            state = "locked"
        elif c.id in stuck:
            state = "stuck"
        elif w:
            state = "busy"
        out.append(
            LiveCompany(
                code=c.code,
                name_fa=c.name_fa or c.code,
                working=w,
                total=total.get(c.id, 0),
                sessions_open=open_by.get(c.code, 0),
                servers_online=int(sv.get("online") or 0),
                servers_total=int(sv.get("total") or 0),
                spend_today_usd=usd((tokens.get(c.id) or {}).get("usd")),
                last_event_at=raw["last"].get(c.code),
                state=state,
            )
        )
    return LiveSummary(
        seq=seq,
        at=now,
        people=LivePeople(**people, total=len(raw["employees"])),
        sessions=LiveSessions(**badges),
        approvals=int(owner.get("approvals") or 0),
        urgent_unread=int(owner.get("urgent") or 0),
        servers=LiveServers(
            online=sum(int(s["online"]) for s in servers.values()),
            offline=sum(int(s["offline"]) for s in servers.values()),
            total=sum(int(s["total"]) for s in servers.values()),
        ),
        tokens=LiveTokens(
            today=all_tokens,
            effective_today=effective(all_tokens, all_cache),
            per_min=sum(int(t["last_min"]) for t in tokens.values()),
            equiv_usd_today=usd(sum((Decimal(str(t["usd"])) for t in tokens.values()), Decimal(0))),
            budget_usd=usd(budget) if budget is not None else None,
        ),
        control=LiveControl(holding=held, companies_locked=locked),
        companies=out,
    )


async def summary(tx: Tx, companies: list[Any], seq: int | None) -> LiveSummary:
    now = datetime.now(UTC)
    return assemble(await gather(tx, now), companies, seq, now)
