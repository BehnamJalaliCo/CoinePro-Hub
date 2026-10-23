"""The owner's quick notes and the cartable reminders (prompt 12 §11,
contract §21.8). No model runs on either.

Notes (NT-0001): text or a transcribed voice; edited with If-Match, archived,
never deleted; promoted to a work item, an order or an errand through the
existing paths, with the link kept.

Reminders (every 15 minutes, code): for each pending card the OWNER decides
(a card with an approver, e.g. a CEO's hire, is not the owner's), each
threshold once:
    half            50% of the time to its expiry has passed
    before_expiry   6 hours before it expires
    age_24h / age_72h / age_7d   for a card without expiry, by its age
A `decision`-level notification (shown at once, pushed with the digest; held
through Khalvat like every decision notification).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import notify

DEFAULT = {"enabled": True, "fraction": 0.5, "before_expiry_h": 6, "ages_h": [24, 72, 168]}

NOTE_SQL = "SELECT n.* FROM owner.notes n"


def render(r: dict[str, Any]) -> dict[str, Any]:
    """OwnerNote (contract §21.8)."""
    return {
        "id": r["id"],
        "ref": r["ref"],
        "text_md": r["text_md"],
        "source": r["source"],
        "file_id": r["file_id"],
        "tags": list(r["tags"] or []),
        "status": r["status"],
        "promoted_to": {"kind": r["promoted_kind"], "ref": r["promoted_ref"]}
        if r["promoted_ref"]
        else None,
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "version": r["version"],
    }


def clean_tags(tags: list[str] | None) -> list[str]:
    out: list[str] = []
    for t in tags or []:
        t = " ".join(str(t).split())[:40]
        if t and t not in out:
            out.append(t)
    return out[:20]


async def create(
    tx: Tx,
    holding_id: Any,
    holding_code: str,
    *,
    text_md: str,
    source: str,
    file_id: Any = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    row = await tx.one(
        """INSERT INTO owner.notes (company_id, text_md, source, file_id, tags)
           VALUES (:co, :t, :s, :f, :tags) RETURNING *""",
        co=holding_id,
        t=text_md,
        s=source,
        f=file_id,
        tags=clean_tags(tags),
    )
    await events.emit(tx, holding_code, "note.created", row["ref"], {"source": source})
    return row


def kind_of(age_h: int) -> str:
    return "age_7d" if age_h == 168 else f"age_{age_h}h"


def due_kinds(
    created_at: datetime, expires_at: datetime | None, now: datetime, cfg: dict[str, Any]
) -> list[str]:
    """The thresholds a card has passed by `now` (pure)."""
    out: list[str] = []
    if expires_at is not None:
        span = (expires_at - created_at).total_seconds()
        if span > 0 and now >= created_at + timedelta(seconds=span * float(cfg["fraction"])):
            out.append("half")
        if now >= expires_at - timedelta(hours=float(cfg["before_expiry_h"])) and now < expires_at:
            out.append("before_expiry")
        return out
    age = (now - created_at).total_seconds() / 3600
    for h in sorted(int(x) for x in cfg["ages_h"]):
        if age >= h:
            out.append(kind_of(h))
    return out


async def settings(tx: Tx) -> dict[str, Any]:
    raw = await tx.scalar("SELECT reminders FROM owner.settings WHERE id = 1") or {}
    return {**DEFAULT, **dict(raw)}


async def remind(tx: Tx, now: datetime | None = None) -> list[dict[str, Any]]:
    """One pass: each due threshold of each pending owner card, once (the
    unique row is the guard). Returns the notifications raised."""
    cfg = await settings(tx)
    if not cfg.get("enabled", True):
        return []
    now = now or datetime.now(UTC)
    # One pass at a time (the guard row is written after its notification).
    await tx.exec("SELECT pg_advisory_xact_lock(hashtextextended('hq:cartable-reminders', 0))")
    cards = await tx.all(
        """SELECT d.id, d.ref, d.title, d.company_id, c.code AS company, d.created_at, d.expires_at,
                  ARRAY(SELECT kind FROM owner.decision_reminders x WHERE x.decision_id = d.id) AS sent
           FROM cartable.decisions d JOIN core.companies c ON c.id = d.company_id
           WHERE d.status = 'pending' AND d.approver_code IS NULL
           ORDER BY d.created_at"""
    )
    raised: list[dict[str, Any]] = []
    for d in cards:
        for kind in due_kinds(d["created_at"], d["expires_at"], now, cfg):
            if kind in (d["sent"] or []):
                continue
            waiting = round((now - d["created_at"]).total_seconds() / 3600)
            n = await notify.raise_notification(
                tx,
                company_id=d["company_id"],
                company_code=d["company"],
                level="decision",
                title_fa=f"یادآوری {d['ref']}: {d['title'][:100]}",
                body_fa=_body(kind, waiting),
                link_kind="decision",
                link_ref=d["ref"],
            )
            await tx.exec(
                """INSERT INTO owner.decision_reminders (company_id, decision_id, kind, at, notification_id)
                   VALUES (:co, :d, :k, :at, :n)""",
                co=d["company_id"],
                d=d["id"],
                k=kind,
                at=now,
                n=n["id"],
            )
            await events.emit(
                tx,
                d["company"],
                "decision.reminded",
                d["ref"],
                {"kind": kind, "waiting_h": waiting},
            )
            await audit.record(
                tx,
                audit.SYSTEM,
                company_id=d["company_id"],
                action="decision.remind",
                action_class="A1",
                target_kind="decision",
                target_ref=d["ref"],
                summary=kind,
            )
            raised.append({**n, "decision": d["ref"], "kind": kind})
    return raised


def _body(kind: str, waiting_h: int) -> str:
    if kind == "half":
        return f"نیمی از مهلت این کارت گذشته است ({waiting_h} ساعت منتظر)."
    if kind == "before_expiry":
        return "کمتر از ۶ ساعت به پایان مهلت این کارت مانده است."
    return f"این کارت {waiting_h} ساعت است که منتظر تصمیم توست."


async def morning_line(tx: Tx, now: datetime | None = None) -> str:
    """One line for the morning report: the owner's pending cards by age."""
    now = now or datetime.now(UTC)
    rows = await tx.all(
        """SELECT created_at FROM cartable.decisions
           WHERE status = 'pending' AND approver_code IS NULL"""
    )
    ages = [(now - r["created_at"]).total_seconds() / 3600 for r in rows]
    if not ages:
        return "- **یادآوری کارتابل:** کارتی منتظر تصمیم تو نیست."
    under = sum(1 for a in ages if a < 24)
    day3 = sum(1 for a in ages if 24 <= a < 72)
    week = sum(1 for a in ages if 72 <= a < 168)
    older = sum(1 for a in ages if a >= 168)
    return (
        f"- **یادآوری کارتابل:** {len(ages)} کارت منتظر تو: {under} زیر ۲۴ ساعت، "
        f"{day3} بین ۱ تا ۳ روز، {week} بین ۳ تا ۷ روز، {older} بیش از ۷ روز."
    )
