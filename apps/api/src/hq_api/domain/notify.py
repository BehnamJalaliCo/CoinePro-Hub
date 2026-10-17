"""Notifications (contract §6, OPERATING_MODEL §1.7). The single entry point
for every notification is `raise_notification()`; it stores the row and
decides its delivery inside the caller's transaction. Channels (push) are
called only after commit: `deliver_pending()` for urgent items,
`flush_digest()` (worker, every few minutes) for batches and releases,
`flush_rhythm()` (morning report) for reports.

Levels and behaviour:
  urgent    always, even in Khalvat or muted; in-app + push + sound
  decision  in-app now (silent); push waits for the digest batch
  report    in-app now; push on the fixed rhythm (morning report)
  info      in-app only, silent
  learning  in-app, rare: capped per day (owner.settings.learning_daily_cap)
Khalvat on: everything except urgent is held, not shown, not pushed.
Muted (settings matrix muted_until in the future): held unless urgent.
CEO attention quota: non-urgent items from one CEO beyond
owner.settings.ceo_daily_attention per (owner's) day wait for the digest.
The stream (`notification.created`) carries metadata only, never a body.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from hq_api import audit, events
from hq_api.db import Tx

if TYPE_CHECKING:
    from hq_api.hub import Hub

log = logging.getLogger("hq_api.notify")

LEVELS = ("urgent", "decision", "report", "info", "learning")
# Default per-level behaviour when the settings matrix says nothing.
DEFAULTS: dict[str, dict[str, bool]] = {
    "urgent": {"in_app": True, "push": True, "sound": True},
    "decision": {"in_app": True, "push": True, "sound": False},
    "report": {"in_app": True, "push": True, "sound": False},
    "info": {"in_app": True, "push": False, "sound": False},
    "learning": {"in_app": True, "push": False, "sound": False},
}
MAX_TOP = 5
URGENT_RETRY_WINDOW = timedelta(minutes=10)

COLUMNS = """n.id, n.company_id, c.code AS company, n.level, n.title_fa, n.body_fa, n.link_kind,
    n.link_ref, n.source_kind, n.source_code, n.choices, n.answer, n.answered_at, n.state,
    n.queue_reason, n.delivered_in_app, n.delivered_web_push, n.delivered_fcm,
    n.delivered_telegram, n.sound, n.delivered_at, n.batch_id, n.read_at, n.created_at"""


@dataclass(frozen=True)
class LevelSetting:
    in_app: bool
    push: bool
    sound: bool
    muted_until: datetime | None

    def muted(self, now: datetime) -> bool:
        return self.muted_until is not None and self.muted_until > now


def level_setting(matrix: dict[str, Any], company_code: str, level: str) -> LevelSetting:
    """Specific company overrides "*", which overrides the level defaults."""
    merged: dict[str, Any] = dict(DEFAULTS[level])
    merged["muted_until"] = None
    for scope in ("*", company_code):
        entry = (matrix.get(scope) or {}).get(level) or {}
        for key in ("in_app", "push", "sound", "muted_until"):
            if key in entry:
                merged[key] = entry[key]
    muted = merged["muted_until"]
    if isinstance(muted, str):
        try:
            muted = datetime.fromisoformat(muted.replace("Z", "+00:00"))
        except ValueError:
            muted = None
    if isinstance(muted, datetime) and muted.tzinfo is None:
        muted = muted.replace(tzinfo=UTC)
    return LevelSetting(
        in_app=bool(merged["in_app"]),
        push=bool(merged["push"]),
        sound=bool(merged["sound"]),
        muted_until=muted if isinstance(muted, datetime) else None,
    )


async def _context(tx: Tx) -> dict[str, Any]:
    """Owner settings, presence and the settings matrix in one round trip."""
    return await tx.one(
        """SELECT s.timezone, s.digest_minutes, s.ceo_daily_attention, s.learning_daily_cap,
                  p.khalvat, ns.matrix, now() AS now,
                  (date_trunc('day', now() AT TIME ZONE s.timezone) AT TIME ZONE s.timezone)
                      AS day_start
           FROM owner.settings s, owner.presence p, notify.settings ns
           WHERE s.id = 1 AND p.id = 1 AND ns.id = 1"""
    )


async def _is_ceo(tx: Tx, source_kind: str, source_code: str) -> bool:
    if source_kind != "agent":
        return False
    kind = await tx.scalar("SELECT kind FROM core.employees WHERE code = :c", c=source_code)
    return bool(kind == "ceo")


# Agents may raise 🔴 only for incidents, at most this many per company per hour (§1.5 of 04.1).
AGENT_URGENT_PER_HOUR = 5


async def counts(tx: Tx, day_start: datetime, source_code: str, company_id: UUID) -> dict[str, int]:
    """Quota counts across the holding, as numbers only, through a SECURITY
    DEFINER function: the caller's company scope is never widened."""
    row = await tx.one(
        "SELECT * FROM notify.agent_notification_counts(:day, :sc, :co)",
        day=day_start,
        sc=source_code,
        co=company_id,
    )
    return {k: int(v) for k, v in row.items()}


def decide(
    *,
    level: str,
    khalvat: bool,
    setting: LevelSetting,
    now: datetime,
    ceo_over_quota: bool,
    learning_over_cap: bool,
) -> dict[str, Any]:
    """Pure delivery decision for a new notification (no I/O)."""
    if level == "urgent":
        return {
            "state": "delivered",
            "queue_reason": None,
            "in_app": True,
            "push": True,
            "sound": True,
        }
    if khalvat:
        return {
            "state": "held",
            "queue_reason": "khalvat",
            "in_app": False,
            "push": False,
            "sound": False,
        }
    if setting.muted(now):
        return {
            "state": "held",
            "queue_reason": "muted",
            "in_app": False,
            "push": False,
            "sound": False,
        }
    if not setting.in_app:
        return {
            "state": "suppressed",
            "queue_reason": "muted",
            "in_app": False,
            "push": False,
            "sound": False,
        }
    if ceo_over_quota:
        return {
            "state": "queued",
            "queue_reason": "attention_quota",
            "in_app": False,
            "push": False,
            "sound": False,
        }
    if level == "learning" and learning_over_cap:
        return {
            "state": "suppressed",
            "queue_reason": "learning_cap",
            "in_app": False,
            "push": False,
            "sound": False,
        }
    if level == "decision":
        # Shown now, silently; one push for the whole batch at the digest.
        reason = "digest" if setting.push else None
        state = "queued" if setting.push else "delivered"
        return {
            "state": state,
            "queue_reason": reason,
            "in_app": True,
            "push": False,
            "sound": False,
        }
    if level == "report":
        reason = "rhythm" if setting.push else None
        state = "queued" if setting.push else "delivered"
        return {
            "state": state,
            "queue_reason": reason,
            "in_app": True,
            "push": False,
            "sound": False,
        }
    # info, learning: in-app only, silent
    return {
        "state": "delivered",
        "queue_reason": None,
        "in_app": True,
        "push": False,
        "sound": False,
    }


async def raise_notification(
    tx: Tx,
    *,
    company_id: UUID,
    company_code: str,
    level: str,
    title_fa: str,
    body_fa: str = "",
    link_kind: str | None = None,
    link_ref: str | None = None,
    source_kind: str = "system",
    source_code: str = "system",
    choices: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Store a notification and decide how it is delivered (in the caller's tx).

    Returns the row (id, level, state, queue_reason, delivered_in_app, ...) plus
    `push_now`: when true, call `deliver_pending(hub, [id])` after commit.
    """
    if level not in LEVELS:
        raise ValueError(f"unknown level {level}")
    ctx = await _context(tx)
    now: datetime = ctx["now"]
    setting = level_setting(ctx["matrix"] or {}, company_code, level)
    n = await counts(tx, ctx["day_start"], source_code, company_id)
    ceo_over = False
    if level != "urgent" and await _is_ceo(tx, source_kind, source_code):
        ceo_over = n["source_today"] >= int(ctx["ceo_daily_attention"])
    learning_over = level == "learning" and n["learning_today"] >= int(ctx["learning_daily_cap"])
    d = decide(
        level=level,
        khalvat=bool(ctx["khalvat"]),
        setting=setting,
        now=now,
        ceo_over_quota=ceo_over,
        learning_over_cap=learning_over,
    )
    row = await tx.one(
        """INSERT INTO notify.notifications (company_id, level, title_fa, body_fa, link_kind,
               link_ref, source_kind, source_code, choices, state, queue_reason,
               delivered_in_app, sound, delivered_at)
           VALUES (:co, :level, :title, :body, :lk, :lr, :sk, :sc, CAST(:choices AS jsonb),
                   :state, :reason, :in_app, :sound, CASE WHEN :in_app THEN now() END)
           RETURNING id, level, state, queue_reason, delivered_in_app, sound, created_at""",
        co=company_id,
        level=level,
        title=title_fa,
        body=body_fa,
        lk=link_kind,
        lr=link_ref,
        sk=source_kind,
        sc=source_code,
        choices=json.dumps(choices, ensure_ascii=False) if choices is not None else None,
        state=d["state"],
        reason=d["queue_reason"],
        in_app=d["in_app"],
        sound=d["sound"],
    )
    if d["in_app"]:
        await _emit_created(tx, company_code, row["id"], level, link_kind, link_ref)
    row["push_now"] = bool(d["push"])
    return row


async def _emit_created(
    tx: Tx, company_code: str, nid: UUID, level: str, link_kind: str | None, link_ref: str | None
) -> None:
    await events.emit(
        tx,
        company_code,
        "notification.created",
        str(nid),
        {"level": level, "link_kind": link_kind, "link_ref": link_ref},
    )


# ------------------------------------------------------------------ delivery --


def _channels(hub: Hub) -> Any:
    from hq_api.channels import Channels

    if hub.channels is None:
        hub.channels = Channels(hub)
    return hub.channels


async def _mark_pushed(hub: Hub, ids: list[UUID], result: dict[str, bool]) -> None:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await tx.exec(
            """UPDATE notify.notifications
               SET delivered_web_push = delivered_web_push OR :wp,
                   delivered_fcm = delivered_fcm OR :fcm,
                   delivered_telegram = delivered_telegram OR :tg
               WHERE id = ANY(:ids)""",
            wp=result.get("web_push", False),
            fcm=result.get("fcm", False),
            tg=result.get("telegram", False),
            ids=ids,
        )


async def deliver_pending(hub: Hub, ids: list[UUID]) -> dict[str, Any]:
    """Push urgent notifications now (call after the raising tx committed)."""
    from hq_api.channels import PushMessage

    if not ids:
        return {"pushed": 0}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        rows = await tx.all(
            f"""SELECT {COLUMNS} FROM notify.notifications n
                JOIN core.companies c ON c.id = n.company_id
                WHERE n.id = ANY(:ids) AND n.level = 'urgent'
                  AND NOT (n.delivered_web_push OR n.delivered_fcm OR n.delivered_telegram)""",  # noqa: S608 - constant column list, values are bound
            ids=ids,
        )
    channels = _channels(hub)
    pushed = 0
    for r in rows:
        result = await channels.push(
            PushMessage(
                title=r["title_fa"],
                level=r["level"],
                company=r["company"],
                link_kind=r["link_kind"],
                link_ref=r["link_ref"],
                sound=True,
            )
        )
        if any(result.values()):
            pushed += 1
            await _mark_pushed(hub, [r["id"]], result)
    return {"pushed": pushed, "considered": len(rows)}


async def flush_digest(hub: Hub) -> dict[str, Any]:
    """Release what waits (worker, every few minutes; idempotent).

    Khalvat on: nothing but the urgent retry sweep. Khalvat off: held items
    (Khalvat, ended mutes) become visible; digest and attention-quota items
    older than the digest window go out as ONE batch (one push) per company.
    """
    from hq_api.channels import PushMessage

    released = 0
    batches: list[dict[str, Any]] = []
    async with hub.db.tx(await hub.companies.ids()) as tx:
        ctx = await _context(tx)
        recent_urgent = await tx.all(
            """SELECT id FROM notify.notifications
               WHERE level = 'urgent' AND created_at > now() - make_interval(secs => :w)
                 AND NOT (delivered_web_push OR delivered_fcm OR delivered_telegram)""",
            w=int(URGENT_RETRY_WINDOW.total_seconds()),
        )
        if not ctx["khalvat"]:
            released = await _release_held(tx, ctx)
            batches = await _batch_digest(tx, ctx)
    urgent = await deliver_pending(hub, [r["id"] for r in recent_urgent])
    if ctx["khalvat"]:
        return {"khalvat": True, "released": 0, "batches": 0, "urgent": urgent}
    channels = _channels(hub)
    for b in batches:
        result = await channels.push(
            PushMessage(
                title=_batch_title(b["items"]),
                level="decision",
                company=b["company"],
                link_kind="inbox",
                link_ref="decisions",
                sound=False,
                count=b["items"],
            )
        )
        if any(result.values()):
            await _mark_pushed(hub, b["ids"], result)
    return {"khalvat": False, "released": released, "batches": len(batches), "urgent": urgent}


def _batch_title(n: int) -> str:
    return f"{n} مورد تازه در کارتابل منتظر توست"


async def _release_held(tx: Tx, ctx: dict[str, Any]) -> int:
    """Khalvat is off: held items appear (mutes only once they have ended)."""
    rows = await tx.all(
        f"""SELECT {COLUMNS} FROM notify.notifications n
            JOIN core.companies c ON c.id = n.company_id
            WHERE n.state = 'held' ORDER BY n.created_at FOR UPDATE OF n SKIP LOCKED"""  # noqa: S608 - constant column list, values are bound
    )
    released = 0
    for r in rows:
        if r["queue_reason"] == "muted" and level_setting(
            ctx["matrix"] or {}, r["company"], r["level"]
        ).muted(ctx["now"]):
            continue
        setting = level_setting(ctx["matrix"] or {}, r["company"], r["level"])
        if r["level"] == "decision" and setting.push:
            state, reason = "queued", "digest"
        elif r["level"] == "report" and setting.push:
            state, reason = "queued", "rhythm"
        else:
            state, reason = "delivered", None
        await tx.exec(
            """UPDATE notify.notifications
               SET state = :state, queue_reason = :reason, delivered_in_app = true,
                   delivered_at = now()
               WHERE id = :id""",
            state=state,
            reason=reason,
            id=r["id"],
        )
        await _emit_created(tx, r["company"], r["id"], r["level"], r["link_kind"], r["link_ref"])
        released += 1
    return released


async def _batch_digest(tx: Tx, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    rows = await tx.all(
        f"""SELECT {COLUMNS} FROM notify.notifications n
            JOIN core.companies c ON c.id = n.company_id
            WHERE n.state = 'queued' AND n.queue_reason IN ('digest', 'attention_quota')
              AND n.created_at <= now() - make_interval(mins => :mins)
            ORDER BY c.code, n.created_at
            FOR UPDATE OF n SKIP LOCKED""",  # noqa: S608 - constant column list, values are bound
        mins=int(ctx["digest_minutes"]),
    )
    by_company: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_company.setdefault(r["company"], []).append(r)
    batches: list[dict[str, Any]] = []
    for code, items in by_company.items():
        company_id = items[0]["company_id"]
        batch_id = await tx.scalar(
            """INSERT INTO notify.digest_batches (company_id, items, reason)
               VALUES (:co, :n, 'digest') RETURNING id""",
            co=company_id,
            n=len(items),
        )
        ids = [i["id"] for i in items]
        await tx.exec(
            """UPDATE notify.notifications
               SET state = 'delivered', queue_reason = NULL, batch_id = :b,
                   delivered_in_app = true, delivered_at = COALESCE(delivered_at, now())
               WHERE id = ANY(:ids)""",
            b=batch_id,
            ids=ids,
        )
        for i in items:
            if not i["delivered_in_app"]:  # attention-quota items appear only now
                await _emit_created(tx, code, i["id"], i["level"], i["link_kind"], i["link_ref"])
        await audit.record(
            tx,
            audit.SYSTEM,
            company_id=company_id,
            action="notification.digest",
            action_class="A0",
            target_kind="digest_batch",
            target_ref=str(batch_id),
            summary=f"digest batch of {len(items)} notifications",
        )
        batches.append({"company": code, "items": len(items), "ids": ids, "batch_id": batch_id})
    return batches


async def flush_rhythm(hub: Hub) -> dict[str, Any]:
    """Reports waiting for the fixed rhythm (morning report): one push in all."""
    from hq_api.channels import PushMessage

    async with hub.db.tx(await hub.companies.ids()) as tx:
        holding = await hub.companies.holding()
        rows = await tx.all(
            """UPDATE notify.notifications SET state = 'delivered', queue_reason = NULL
               WHERE state = 'queued' AND queue_reason = 'rhythm' RETURNING id"""
        )
        if not rows:
            return {"reports": 0}
        batch_id = await tx.scalar(
            """INSERT INTO notify.digest_batches (company_id, items, reason)
               VALUES (:co, :n, 'rhythm') RETURNING id""",
            co=holding.id,
            n=len(rows),
        )
        ids = [r["id"] for r in rows]
        await tx.exec(
            "UPDATE notify.notifications SET batch_id = :b WHERE id = ANY(:ids)",
            b=batch_id,
            ids=ids,
        )
    result = await _channels(hub).push(
        PushMessage(
            title=f"{len(rows)} گزارش تازه",
            level="report",
            company=holding.code,
            link_kind="inbox",
            link_ref="reports",
            sound=False,
            count=len(rows),
        )
    )
    if any(result.values()):
        await _mark_pushed(hub, ids, result)
    return {"reports": len(rows)}


# -------------------------------------------------------------- summaries --


async def away_summary(tx: Tx, since: datetime) -> dict[str, Any]:
    """«در نبودت چه گذشت»: counts and top items per box and per company since
    `since`. Deterministic (fixed ordering), no model involved."""
    totals = await tx.one(
        """SELECT
             (SELECT count(*) FROM cartable.decisions WHERE created_at >= :s) AS decisions_new,
             (SELECT count(*) FROM cartable.decisions WHERE status = 'pending')
               AS decisions_pending,
             (SELECT count(*) FROM cartable.deliverables WHERE created_at >= :s)
               AS deliverables_new,
             (SELECT count(*) FROM cartable.deliverables d
               WHERE NOT EXISTS (SELECT 1 FROM cartable.ratings r WHERE r.deliverable_id = d.id))
               AS deliverables_unrated,
             (SELECT count(*) FROM msg.messages WHERE created_at >= :s AND author_kind <> 'owner')
               AS messages_new,
             (SELECT COALESCE(sum(last_seq - owner_read_seq), 0) FROM msg.threads)
               AS messages_unread,
             (SELECT count(*) FROM notify.notifications WHERE created_at >= :s AND state = 'held')
               AS notifications_held""",
        s=since,
    )
    by_level = dict.fromkeys(LEVELS, 0)
    for r in await tx.all(
        """SELECT level, count(*) AS n FROM notify.notifications
           WHERE created_at >= :s AND state <> 'suppressed' GROUP BY level""",
        s=since,
    ):
        by_level[r["level"]] = int(r["n"])
    top_decisions = await tx.all(
        """SELECT d.ref, d.title, d.kind, d.risk, d.status, c.code AS company, d.created_at
           FROM cartable.decisions d JOIN core.companies c ON c.id = d.company_id
           WHERE d.created_at >= :s
           ORDER BY CASE d.risk WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                    d.created_at DESC, d.ref
           LIMIT :n""",
        s=since,
        n=MAX_TOP,
    )
    top_deliverables = await tx.all(
        """SELECT d.ref, d.title, c.code AS company, d.created_at
           FROM cartable.deliverables d JOIN core.companies c ON c.id = d.company_id
           WHERE d.created_at >= :s ORDER BY d.created_at DESC, d.ref LIMIT :n""",
        s=since,
        n=MAX_TOP,
    )
    top_threads = await tx.all(
        """SELECT t.code AS thread, c.code AS company, count(*) AS new_messages,
                  max(m.created_at) AS last_at
           FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
           JOIN core.companies c ON c.id = t.company_id
           WHERE m.created_at >= :s AND m.author_kind <> 'owner'
           GROUP BY t.code, c.code ORDER BY count(*) DESC, t.code LIMIT :n""",
        s=since,
        n=MAX_TOP,
    )
    top_notifications = await tx.all(
        """SELECT n.id, n.level, n.title_fa, c.code AS company, n.created_at, n.link_kind,
                  n.link_ref
           FROM notify.notifications n JOIN core.companies c ON c.id = n.company_id
           WHERE n.created_at >= :s AND n.state <> 'suppressed'
           ORDER BY CASE n.level WHEN 'urgent' THEN 0 WHEN 'decision' THEN 1 WHEN 'report' THEN 2
                                 WHEN 'learning' THEN 3 ELSE 4 END,
                    n.created_at DESC, n.id
           LIMIT :n""",
        s=since,
        n=MAX_TOP,
    )
    companies = await tx.all(
        """SELECT c.code AS company,
                  (SELECT count(*) FROM cartable.decisions d
                    WHERE d.company_id = c.id AND d.created_at >= :s) AS decisions_new,
                  (SELECT count(*) FROM cartable.deliverables d
                    WHERE d.company_id = c.id AND d.created_at >= :s) AS deliverables_new,
                  (SELECT count(*) FROM msg.messages m
                    WHERE m.company_id = c.id AND m.created_at >= :s AND m.author_kind <> 'owner')
                    AS messages_new,
                  (SELECT count(*) FROM notify.notifications n
                    WHERE n.company_id = c.id AND n.created_at >= :s AND n.state <> 'suppressed')
                    AS notifications_new
           FROM core.companies c
           WHERE c.id = ANY(core.allowed_company_ids())
           ORDER BY c.kind = 'holding' DESC, c.code""",
        s=since,
    )
    active = [
        {k: (int(v) if k != "company" else v) for k, v in row.items()}
        for row in companies
        if any(
            int(row[k])
            for k in ("decisions_new", "deliverables_new", "messages_new", "notifications_new")
        )
    ]
    return {
        "since": since,
        "until": datetime.now(UTC),
        "decisions": {
            "new": int(totals["decisions_new"]),
            "pending": int(totals["decisions_pending"]),
            "top": top_decisions,
        },
        "deliverables": {
            "new": int(totals["deliverables_new"]),
            "unrated": int(totals["deliverables_unrated"]),
            "top": top_deliverables,
        },
        "messages": {
            "new": int(totals["messages_new"]),
            "unread": int(totals["messages_unread"]),
            "top_threads": [{**t, "new_messages": int(t["new_messages"])} for t in top_threads],
        },
        "notifications": {
            "by_level": by_level,
            "held": int(totals["notifications_held"]),
            "top": top_notifications,
        },
        "companies": active,
    }
