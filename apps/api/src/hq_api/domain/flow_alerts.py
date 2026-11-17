"""⟨1.39⟩ Contract §61.6 (prompt 39.1): an automation's alerts, made and closed by code.

Kinds: `run_failed`, `cap_reached`, `page_held` (a publication `held`), `login_expired` (ChatGPT,
AI Studio, Gemini in the hub's browser), `clock_missed` (no tick and no backup run), `late` (a
publish hour passed without its package). One open alert per flow and kind (a unique index); it
closes by itself when its cause is gone (`closed_at`, `closed_fa` of how). No model is asked.

The sweep runs with the hub's clock (flows.clock: n8n's minute tick, or the backup when n8n is
silent). Only a real crisis notifies the owner (the standing rule): a day that did not go out
(`late` past its hour by an hour, with no run left that could still make it) and the clock
silent for 30 minutes. Everything else stays on the flow's page.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from hq_api.db import Tx
from hq_api.domain import flows as FL

log = logging.getLogger("hq_api.flow_alerts")

KINDS = ("run_failed", "cap_reached", "page_held", "login_expired", "clock_missed", "late")
LATE_AFTER = timedelta(minutes=5)  # a publish hour this far past without its package: `late`
NOT_OUT_AFTER = timedelta(minutes=60)  # …and this far, with no run left: the owner is told
CLOCK_SILENT = timedelta(minutes=30)
CLOCK_ALERT_FOR = timedelta(hours=1)  # a clock_missed alert stays on the page this long
WENT_OUT_BEFORE, WENT_OUT_AFTER = timedelta(hours=1), timedelta(hours=3)  # (went_out's window)
FA_DIGITS = FL.FA_DIGITS

CAP_REACHED_FA = "هزینه‌ی ساخت امروز به {usd} دلار رسید (سقف روز {cap} دلار)؛ ساخت تا آخر ادامه یافت"
RUN_FAILED_FA = "ساخت {day} به نتیجه نرسید"
PAGE_HELD_FA = "{n} انتشار این اتوماسیون منتظر باز شدن پیج است"
LOGIN_FA = "ورود {who} در مرورگر هاب کار نمیکند"
CLOCK_MISSED_FA = "ساعت اتوماسیون‌ها {minutes} دقیقه خاموش بود؛ ساخت این روز دیرتر شروع شد"
LATE_FA = "ساعت انتشار {at} گذشت و بسته‌ی این روز هنوز نرسیده است"
NOT_OUT_TITLE_FA = "«{title}» امروز منتشر نشد"
NOT_OUT_BODY_FA = "ساعت انتشار {at} یک ساعت پیش گذشت و ساخت این روز دیگر کاری در جریان ندارد."
CLOCK_TITLE_FA = "ساعت اتوماسیون‌ها {minutes} دقیقه خاموش بود"
CLOCK_BODY_FA = "هاب ساخت این‌ها را دیرتر شروع کرد: {titles}"
CLOSED_SENT_FA = "بسته رسید و زمان‌بندی شد"
CLOSED_DAY_FA = "روز تازه شد"
CLOSED_OK_FA = "دوباره روبه‌راه است"
HELPER_OF = {"gpt": "helpers_browser", "gemini": "helpers_browser", "aistudio": "aistudio"}
HELPER_FA = {"helpers_browser": "ChatGPT", "aistudio": "ای‌آی استودیو"}


class Alert(BaseModel):
    id: UUID
    kind: str
    note_fa: str
    day: date | None = None
    opened_at: datetime
    notified: bool = False
    closed_at: datetime | None = None
    closed_fa: str | None = None


def fa(v: Any) -> str:
    return str(v).translate(FA_DIGITS)


async def open_alert(
    tx: Tx, flow: FL.Flow, kind: str, note_fa: str, day: date | None = None
) -> UUID | None:
    """The flow's open alert of this kind (made now, or None when one is open already)."""
    got = await tx.scalar(
        """INSERT INTO automations.alerts (company_id, flow_id, kind, day, note_fa)
           SELECT company_id, id, :k, :d, :n FROM automations.flows WHERE ref = :r
           ON CONFLICT (flow_id, kind) WHERE closed_at IS NULL DO NOTHING
           RETURNING id""",
        k=kind,
        d=day,
        n=note_fa[:500],
        r=flow.ref,
    )
    return UUID(str(got)) if got else None


async def close_alert(tx: Tx, flow: FL.Flow, kind: str, closed_fa: str) -> bool:
    got = await tx.scalar(
        """UPDATE automations.alerts a SET closed_at = now(), closed_fa = :c
           FROM automations.flows f
           WHERE f.id = a.flow_id AND f.ref = :r AND a.kind = :k AND a.closed_at IS NULL
           RETURNING a.id""",
        c=closed_fa[:500],
        r=flow.ref,
        k=kind,
    )
    return got is not None


async def of_flow(tx: Tx, flow: FL.Flow, *, open_only: bool = True) -> list[Alert]:
    rows = await tx.all(
        """SELECT a.* FROM automations.alerts a JOIN automations.flows f ON f.id = a.flow_id
           WHERE f.ref = :r AND (a.closed_at IS NULL OR NOT :o)
           ORDER BY a.opened_at DESC LIMIT 50""",
        r=flow.ref,
        o=open_only,
    )
    return [
        Alert(
            id=r["id"],
            kind=r["kind"],
            note_fa=r["note_fa"],
            day=r["day"],
            opened_at=r["opened_at"],
            notified=r["notified_at"] is not None,
            closed_at=r["closed_at"],
            closed_fa=r["closed_fa"],
        )
        for r in rows
    ]


async def _open_one(tx: Tx, flow: FL.Flow, kind: str) -> dict[str, Any] | None:
    row = await tx.first(
        """SELECT a.* FROM automations.alerts a JOIN automations.flows f ON f.id = a.flow_id
           WHERE f.ref = :r AND a.kind = :k AND a.closed_at IS NULL""",
        r=flow.ref,
        k=kind,
    )
    return dict(row) if row is not None else None


async def _tell(tx: Tx, alert_ids: list[UUID], company: str, title: str, body: str,
                link: str) -> list[UUID]:  # fmt: skip
    """ONE notification for these alerts (only those not told yet); the notification's id."""
    from hq_api.domain import notify

    fresh = await tx.all(
        """UPDATE automations.alerts SET notified_at = now()
           WHERE id = ANY(:ids) AND notified_at IS NULL RETURNING id""",
        ids=alert_ids,
    )
    if not fresh:
        return []
    co = await tx.one("SELECT id FROM core.companies WHERE code = :c", c=company)
    got = await notify.raise_notification(
        tx, company_id=co["id"], company_code=company, level="urgent", title_fa=title[:300],
        body_fa=body[:1000], link_kind="automation", link_ref=link, source_kind="system",
        source_code="flows", domain="business",
    )  # fmt: skip
    return [UUID(str(got["id"]))] if got.get("push_now") else []


# ------------------------------------------------------------------ the sweep --
async def sweep(hub: Any, now: datetime, *, quiet_since: datetime | None = None) -> list[UUID]:
    """Every flow's alerts, opened and closed by what is there now. `quiet_since`: the clock's
    previous run (a tick or the backup) when it came 30 minutes or more ago. Returns the
    notifications to push after the commit."""
    from hq_api.domain import automation_board as BOARD

    push: list[UUID] = []
    async with hub.db.tx(await hub.companies.ids()) as tx:
        flows = [f for f in (await FL.active_flows(tx)).values() if f.ref and f.account]
        health: dict[str, Any] = {h.key: h for h in await BOARD.health(tx, hub, now)}
        for flow in flows:
            if flow.state == "off":
                continue
            try:
                async with tx.conn.begin_nested():
                    await _failed(tx, hub, flow)
                    await _capped(tx, flow)
                    await _held(tx, flow)
                    await _login(tx, flow, health)
                    push += await _late(tx, flow, now)
            except Exception:  # (one flow's alerts never stop the others')
                log.exception("a flow's alerts were not read", extra={"flow": flow.key})
        push += await _clock(tx, flows, now, quiet_since)
    return push


async def _failed(tx: Tx, hub: Any, flow: FL.Flow) -> None:
    from hq_api.domain import flow_view as FV

    days = await FV._days(tx, flow, 1)
    last = await FV.run_ref(tx, hub, days[0]) if days else None
    if last is not None and last.state == "failed":
        day = str(days[0]["flow"].get("day") or "")
        await open_alert(tx, flow, "run_failed", RUN_FAILED_FA.format(day=_day_fa(day)),
                         day=date.fromisoformat(day) if day else None)  # fmt: skip
    else:
        await close_alert(tx, flow, "run_failed", CLOSED_OK_FA)


async def _capped(tx: Tx, flow: FL.Flow) -> None:
    """Opened by flows.over_cap; closed when the flow's newest day is not past its cap."""
    if await _open_one(tx, flow, "cap_reached") is None:
        return
    capped = await tx.scalar(
        """SELECT run_meta -> 'flow' ? 'capped' FROM work.work
           WHERE parent_id IS NULL AND run_meta -> 'flow' ->> 'key' = :k
           ORDER BY created_at DESC LIMIT 1""",
        k=flow.key,
    )
    if not capped:
        await close_alert(tx, flow, "cap_reached", CLOSED_DAY_FA)


async def _held(tx: Tx, flow: FL.Flow) -> None:
    n = await tx.scalar(
        """SELECT count(*) FROM media.publications
           WHERE state = 'held' AND source ->> 'flow_key' = :k""",
        k=flow.key,
    )
    if n:
        await open_alert(tx, flow, "page_held", PAGE_HELD_FA.format(n=fa(n)))
    else:
        await close_alert(tx, flow, "page_held", CLOSED_OK_FA)


async def _login(tx: Tx, flow: FL.Flow, health: dict[str, Any]) -> None:
    from hq_api.domain import flow_view as FV

    used = {HELPER_OF[s.helper] for s in FV.steps_of(flow) if s.helper in HELPER_OF}
    down = [k for k in sorted(used) if k in health and health[k].state == "down"]
    if down:
        await open_alert(tx, flow, "login_expired",
                         LOGIN_FA.format(who="، ".join(HELPER_FA[k] for k in down)))  # fmt: skip
    else:
        await close_alert(tx, flow, "login_expired", CLOSED_OK_FA)


async def _late(tx: Tx, flow: FL.Flow, now: datetime) -> list[UUID]:
    """Today's post (Tehran): its hour gone without its package → `late`; an hour gone and no run
    left that could still make it → the owner is told, once. Closes when the package is sent, or
    on the next day."""
    tz = ZoneInfo(FL.TEHRAN)
    today = now.astimezone(tz).date()
    open_ = await _open_one(tx, flow, "late")
    if open_ is not None and open_["day"] is not None and open_["day"] != today:
        await close_alert(tx, flow, "late", CLOSED_DAY_FA)
        open_ = None
    if FL.held_why(flow, today) is not None:
        return []
    co = await tx.scalar("SELECT id FROM core.companies WHERE code = :c", c=flow.company)
    at, _ = await FL.slot_of(tx, flow, today, co)
    if now < at + LATE_AFTER:
        return []
    day = await tx.first(
        """SELECT status, run_meta -> 'flow' ? 'sent' AS sent FROM work.work
           WHERE parent_id IS NULL AND run_meta -> 'flow' ->> 'key' = :k
             AND run_meta -> 'flow' ->> 'day' = :d
           ORDER BY (run_meta -> 'flow' ? 'sent') DESC, created_at DESC LIMIT 1""",
        k=flow.key,
        d=today.isoformat(),
    )
    if (day is not None and day["sent"]) or await went_out(tx, flow, today, at):
        if open_ is not None:
            await close_alert(tx, flow, "late", CLOSED_SENT_FA)
        return []
    when = FL.at_fa(at)
    made = await open_alert(tx, flow, "late", LATE_FA.format(at=when), day=today)
    alert = made or (open_ or {}).get("id")
    left = day is not None and day["status"] not in ("failed", "cancelled", "done")
    if alert is None or now < at + NOT_OUT_AFTER or left:
        return []
    return await _tell(tx, [UUID(str(alert))], flow.company,
                       NOT_OUT_TITLE_FA.format(title=flow.title_fa),
                       NOT_OUT_BODY_FA.format(at=when), flow.ref)  # fmt: skip


WENT_OUT_SQL = """SELECT 1 FROM media.publications
    WHERE state NOT IN ('failed', 'cancelled') AND (
        (source ->> 'flow_key' = :k AND source ->> 'day' = :d)
        OR (account = :a AND kind = :kind AND at >= :lo AND at < :hi
            AND coalesce(source ->> 'flow_key', '') IN ('', :k)))
    LIMIT 1"""


async def went_out(tx: Tx, flow: FL.Flow, day: date, at: datetime) -> bool:
    """⟨2026-11-17⟩ the day's package went out, read from what was published (§60.1), not only from
    its work: a day whose work is gone (the owner's wipe of 07:24Z took that morning's works, and
    every day made before §60 has no flow on its rows) still counts. Its publication row (this
    flow and day), or a post of the page of the flow's kind from an hour before its hour to three
    hours after its last one, that no other flow claims."""
    last = FL.story_times(flow, day)[-1] if flow.stories else at
    got = await tx.scalar(
        WENT_OUT_SQL, k=flow.key, d=day.isoformat(), a=flow.account,
        kind="story" if flow.stories else "reel", lo=at - WENT_OUT_BEFORE,
        hi=last + WENT_OUT_AFTER,
    )  # fmt: skip
    return got is not None


async def _clock(
    tx: Tx, flows: list[FL.Flow], now: datetime, quiet_since: datetime | None
) -> list[UUID]:
    """The clock back after 30 minutes or more of silence: a `clock_missed` alert on every flow
    whose build hour fell in the silence, and ONE notification. Each closes an hour later."""
    for f in flows:
        a = await _open_one(tx, f, "clock_missed")
        if a is not None and now - a["opened_at"] >= CLOCK_ALERT_FOR:
            await close_alert(tx, f, "clock_missed", CLOSED_OK_FA)
    if quiet_since is None or now - quiet_since < CLOCK_SILENT:
        return []
    minutes = int((now - quiet_since).total_seconds() // 60)
    tz = ZoneInfo(FL.TEHRAN)
    today = now.astimezone(tz).date()
    hit: list[tuple[FL.Flow, UUID]] = []
    for f in flows:
        if f.state != "on":
            continue
        for day in (today, today + timedelta(days=1)):
            if quiet_since < FL.trigger_of(f, day) <= now:
                got = await open_alert(tx, f, "clock_missed",
                                       CLOCK_MISSED_FA.format(minutes=fa(minutes)), day=day)  # fmt: skip
                if got is not None:
                    hit.append((f, got))
                break
    if not hit:
        return []
    holding = await tx.one("SELECT code FROM core.companies WHERE kind = 'holding' LIMIT 1")
    return await _tell(
        tx, [a for _, a in hit], str(holding["code"]),
        CLOCK_TITLE_FA.format(minutes=fa(minutes)),
        CLOCK_BODY_FA.format(titles="، ".join(f.title_fa for f, _ in hit)), hit[0][0].ref,
    )  # fmt: skip


def _day_fa(day: str) -> str:
    try:
        return FL.fa_day(date.fromisoformat(day))
    except ValueError:
        return "این روز"
