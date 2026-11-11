"""Erasing for good (contract §37, v1.19; the owner, 2026-11-06: «یه گزینه حذف هم داشته باشه که اصلا
شاید یه سشن رو من میخوام پاک کنم اصلا نباشه و قابلیت پاک کردن از بایگانی هم بذار»).

Hiding (§35) stays; erasing is for good, and every erase is the owner's alone, sealed (🔏). An agent
only proposes one (`erase.propose`): a decision card `erase` whose seal runs the erase.

    session         (§37.1) owner.erase_order (migration 0055) in one transaction: the order, its
                    session (report, steps, tasks), its talk (turns, their voice and files), its
                    files, its outputs and their files, its cards (withdrawn; gone when nothing kept
                    stands on them), the notifications that point at it, its runs' transcripts. Its
                    works stay only as the ledgers' anchors: no words, hidden from every app role
                    (work.work.erased_at). The preview is the same erase in a sub-transaction rolled
                    back, so what it counts is what the erase does.
    archive_record  (§37.2) the archive's own disposal (§23.5) run now: its files destroyed, the
                    record disposed; the tombstone keeps only the ref, the date and «به دستور مدیر
                    کل»; a record under a legal hold is 409 with the hold named.
    output          (§37.2) one output and its files (§28.1's delete for good), the notifications
                    that point at it, its pending cards withdrawn; the work it belongs to stays and
                    its order says «خروجی پاک شد».

A stored object is destroyed only once the transaction has committed (archive.destroy_queue, why
`erase`; `destroy_after`), and only when no file row that stays points at it. Every erase writes
one audit line (A3, the counts); the audit chain itself is never changed.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import humanize as HZ
from hq_api.errors import ApiError
from hq_api.principal import Principal

Kind = Literal["session", "archive_record", "output"]
KINDS: tuple[str, ...] = ("session", "archive_record", "output")
ERASED_FA = "پاک‌شده"
BY_OWNER_FA = "به دستور مدیر کل"
OWNER_FA = "مدیر کل"
ACTION = {"session": "session.erase", "archive_record": "archive.erase", "output": "output.erase"}
TARGET_KIND = {"session": "order", "archive_record": "archive_record", "output": "deliverable"}
NOT_FOUND_FA = {
    "session": "این فرمان پیدا نشد.",
    "archive_record": "این سند در بایگانی پیدا نشد.",
    "output": "این خروجی پیدا نشد.",
}
KEEP_AUDIT_FA = "یک خط در دفتر ممیزی که میگوید چه چیزی و چند تا پاک شد"
KEEP_MONEY_FA = "رقم‌های توکن و هزینه، که خزانه باید همچنان جمعشان را داشته باشد"


class EraseCounts(BaseModel):
    turns: int = 0
    files: int = 0
    outputs: int = 0
    works: int = 0
    notifications: int = 0


class ErasePreview(BaseModel):
    """What an erase would remove, and in plain Persian what stays (nothing changes)."""

    ref: str
    kind: Kind
    title_fa: str
    counts: EraseCounts
    keeps_fa: list[str] = Field(default_factory=list)


class Erased(BaseModel):
    ref: str
    erased: EraseCounts


def _counts(raw: dict[str, Any] | None) -> EraseCounts:
    c = (raw or {}).get("counts") or {}
    return EraseCounts(**{k: int(c.get(k) or 0) for k in EraseCounts.model_fields})


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def _title(text: str | None, limit: int = 80) -> str:
    one = " ".join((text or "").split())
    return (HZ.humanize(one) or one)[:limit].rstrip() or "فرمان"


async def _holding(tx: Tx) -> dict[str, Any]:
    return await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding'")


def _not_found(kind: str, ref: str) -> ApiError:
    return ApiError(404, "not_found", f"no {kind} {ref}", message_fa=NOT_FOUND_FA[kind])


# ================================================================ session ==
async def _order(tx: Tx, ref: str) -> dict[str, Any]:
    row = await tx.first("SELECT id, ref, text, company_id FROM owner.orders WHERE ref = :r", r=ref)
    if row is None:
        raise _not_found("session", ref)
    return dict(row)


def _session_keeps(raw: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if int(raw.get("built") or 0):
        out.append(
            "گروه کاری یا خط تولیدی که این جلسه راه انداخت؛ آن را در صفحه‌ی خودش جدا پاک کنید"
        )
    if int(raw.get("filed") or 0):
        out.append(
            "سندهایی که از خروجی‌های این جلسه در بایگانی ثبت شده‌اند؛ از بایگانی جدا پاک میشوند"
        )
    if int((raw.get("cards") or {}).get("kept") or 0):
        out.append(
            "کارت‌هایی که چیزی روی آنها ایستاده (مثل یک استخدام): پس گرفته میشوند و سابقه‌شان میماند"
        )
    out.append(KEEP_AUDIT_FA)
    out.append(KEEP_MONEY_FA)
    return out


async def session_preview(tx: Tx, ref: str) -> ErasePreview:
    """GET /orders/{ref}/erase/preview: the session's erase run and rolled back."""
    o = await _order(tx, ref)
    raw = _j(await tx.scalar("SELECT owner.erase_order(:id, true)", id=o["id"])) or {}
    return ErasePreview(
        ref=ref,
        kind="session",
        title_fa=_title(o["text"]),
        counts=_counts(raw),
        keeps_fa=_session_keeps(raw),
    )


async def session_erase(tx: Tx, ref: str) -> dict[str, Any]:
    """POST /orders/{ref}/erase (or a sealed card): the session gone for good. Answers the raw
    result ({ref, counts, cards, built, filed, work_refs, conversation_refs})."""
    o = await _order(tx, ref)
    raw = _j(await tx.scalar("SELECT owner.erase_order(:id, false)", id=o["id"]))
    if raw is None:
        raise _not_found("session", ref)
    holding = await _holding(tx)
    await events.emit(tx, holding["code"], "order.erased", ref, {"counts": raw.get("counts")})
    await events.emit(
        tx, holding["code"], "session.updated", ref, {"badge": "closed", "erased": True}
    )
    return dict(raw)


# ================================================================= output ==
async def _output(tx: Tx, ref: str) -> dict[str, Any]:
    row = await tx.first(
        """SELECT dl.id, dl.ref, dl.title, dl.work_id, dl.company_id, c.code AS company
           FROM cartable.deliverables dl JOIN core.companies c ON c.id = dl.company_id
           WHERE dl.ref = :r""",
        r=ref,
    )
    if row is None:
        raise _not_found("output", ref)
    return dict(row)


async def _output_keeps(tx: Tx, dl: dict[str, Any]) -> list[str]:
    out = ["کاری که این خروجی از آن آمد میماند؛ در گزارش فرمانش «خروجی پاک شد» نوشته میشود"]
    # an output is filed with source_ref 'deliverable:<ref>' (archive/deliverables.py)
    filed = await tx.scalar(
        """SELECT count(*) FROM archive.records WHERE source_ref = :r AND state <> 'disposed'""",
        r=f"deliverable:{dl['ref']}",
    )
    if int(filed or 0):
        out.append("سندی که از این خروجی در بایگانی ثبت شده است؛ از بایگانی جدا پاک میشود")
    out.append(KEEP_AUDIT_FA)
    return out


async def output_preview(tx: Tx, ref: str) -> ErasePreview:
    dl = await _output(tx, ref)
    raw = _j(await tx.scalar("SELECT cartable.erase_output(:id, true)", id=dl["id"])) or {}
    return ErasePreview(
        ref=ref,
        kind="output",
        title_fa=(HZ.humanize(dl["title"]) or dl["title"] or "خروجی")[:80],
        counts=_counts(raw),
        keeps_fa=await _output_keeps(tx, dl),
    )


async def output_erase(tx: Tx, ref: str) -> dict[str, Any]:
    """One output and its files gone; the work stays; its order's story says «خروجی پاک شد»."""
    from hq_api.domain import order_report as OR
    from hq_api.domain import sessions as SE

    dl = await _output(tx, ref)
    order = await OR.order_of_work(tx, dl["work_id"])
    raw = _j(await tx.scalar("SELECT cartable.erase_output(:id, false)", id=dl["id"]))
    if raw is None:
        raise _not_found("output", ref)
    await events.emit(tx, dl["company"], "deliverable.deleted", ref, {"erased": True})
    if order is not None:
        await _scrub_output_steps(tx, order, str(dl["title"] or ""))
        await SE.step(tx, order, OWNER_FA, "خروجی پاک شد")
    return dict(raw)


async def _scrub_output_steps(tx: Tx, order_ref: str, title: str) -> None:
    """The order's story no longer names the erased output («خروجی رسید: …» goes)."""
    rep = await tx.first(
        "SELECT id, steps FROM owner.order_reports WHERE ref = :r FOR UPDATE", r=order_ref
    )
    if rep is None or not title:
        return
    names = {HZ.humanize(title) or title, title}
    lines = {f"خروجی رسید: {n}" for n in names} | {f"خروجی ناقص رسید: {n}" for n in names}
    steps = [s for s in _j(rep["steps"]) or [] if HZ.humanize(s.get("what_fa")) not in lines]
    await tx.exec(
        "UPDATE owner.order_reports SET steps = CAST(:s AS jsonb), updated_at = now() WHERE id = :id",
        s=json.dumps(steps, ensure_ascii=False),
        id=rep["id"],
    )


# ========================================================= archive record ==
async def _record(tx: Tx, ref: str) -> dict[str, Any]:
    from hq_api.archive import records as R

    try:
        r = await R.load(tx, ref)
    except ApiError as exc:
        if exc.status == 404:
            raise _not_found("archive_record", ref) from exc
        raise
    if r["state"] == "disposed":
        raise _not_found("archive_record", ref)
    return dict(r)


async def _holds(tx: Tx, r: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(h)
        for h in await tx.all(
            """SELECT ref, title_fa FROM archive.holds
               WHERE ref = ANY(archive.held_by(:r)) ORDER BY ref""",
            r=r["id"],
        )
    ]


def held_error(holds: list[dict[str, Any]]) -> ApiError:
    names = "، ".join(f"«{h['title_fa']}» ({h['ref']})" for h in holds)
    return ApiError(
        409,
        "validation_failed",
        "the record is under a legal hold: " + ", ".join(h["ref"] for h in holds),
        message_fa=f"این سند زیر توقیف قانونی {names} است و تا آزاد نشود پاک نمیشود.",
    )


async def record_preview(tx: Tx, ref: str) -> ErasePreview:
    r = await _record(tx, ref)
    files = await tx.scalar(
        "SELECT count(*) FROM archive.record_files WHERE record_id = :r AND destroyed_at IS NULL",
        r=r["id"],
    )
    keeps = ["سنگ‌نوشته‌ای که فقط شماره‌ی سند، تاریخ و «به دستور مدیر کل» را نگه میدارد"]
    holds = await _holds(tx, r)
    if holds:
        keeps.insert(0, held_error(holds).message_fa or "")
    keeps.append(KEEP_AUDIT_FA)
    return ErasePreview(
        ref=ref,
        kind="archive_record",
        title_fa=(r["title_fa"] or "سند")[:80],
        counts=EraseCounts(files=int(files or 0)),
        keeps_fa=keeps,
    )


async def record_erase(tx: Tx, ref: str, *, card_ref: str | None = None) -> dict[str, Any]:
    """The archive's own disposal run now (§23.5); 409 under a legal hold."""
    from hq_api.archive import retention as RT

    r = await _record(tx, ref)
    holds = await _holds(tx, r)
    if holds:
        raise held_error(holds)
    files = await RT.erase_record(tx, ref, card_ref=card_ref)
    return {"ref": ref, "counts": {"files": files}}


# ================================================================ the seal ==
PREVIEWS = {"session": session_preview, "archive_record": record_preview, "output": output_preview}


async def preview(tx: Tx, kind: str, ref: str) -> ErasePreview:
    return await PREVIEWS[kind](tx, ref)


async def erase(
    tx: Tx,
    who: Principal,
    kind: str,
    ref: str,
    *,
    step_up: bool,
    card_ref: str | None = None,
    request_id: str | None = None,
) -> Erased:
    """The erase of one thing, with its one audit line (A3: the ref and the counts)."""
    if kind == "session":
        raw = await session_erase(tx, ref)
        company_id = (await _holding(tx))["id"]
    elif kind == "output":
        dl = await _output(tx, ref)
        raw = await output_erase(tx, ref)
        company_id = dl["company_id"]
    else:
        r = await _record(tx, ref)
        raw = await record_erase(tx, ref, card_ref=card_ref)
        company_id = r["company_id"]
    counts = _counts(raw)
    summary = {"ref": ref, "erased": counts.model_dump()}
    if card_ref:
        summary["card"] = card_ref
    await audit.record(
        tx,
        who,
        company_id=company_id,
        action=ACTION[kind],
        action_class="A3",
        target_kind=TARGET_KIND[kind],
        target_ref=ref,
        summary=json.dumps(summary, ensure_ascii=False),
        step_up=step_up,
        request_id=request_id,
    )
    return Erased(ref=ref, erased=counts)


async def destroy_after(hub: Any) -> int:
    """After the commit: the stored objects of what was erased are removed (the archive's queue)."""
    from hq_api.archive import retention as RT
    from hq_api.archive.common import wide_txf

    return await RT.destroy_queued(hub, wide_txf(hub))


# ============================================================ the proposal ==
def _counts_fa(kind: str, c: EraseCounts) -> str:
    if kind == "archive_record":
        return f"سند بایگانی و {c.files} فایل آن"
    if kind == "output":
        return f"یک خروجی و {c.files} فایل آن"
    return (
        f"جلسه با {c.turns} پیام گفتگو، {c.works} کار، {c.outputs} خروجی، {c.files} فایل "
        f"و {c.notifications} اعلان"
    )


async def readable(tx: Tx, who: Principal, kind: str, ref: str) -> tuple[bool, str | None]:
    """(may the agent read it, the thing's company code): the policy lets a role propose only what
    it can read (an order it works on; an output of its company or of an order it works on; an
    archive record within its clearance). A holding-scope role reads every company."""
    from hq_api.domain import order_report as OR

    holding_scope = who.scope == "holding"
    if kind == "session":
        await _order(tx, ref)
        works = await OR.may_speak(tx, ref, who)
        return works or holding_scope, (who.company if works else None)
    if kind == "output":
        dl = await _output(tx, ref)
        order = await OR.order_of_work(tx, dl["work_id"])
        mine = dl["company"] == who.company or (
            order is not None and await OR.may_speak(tx, order, who)
        )
        return mine or holding_scope, (who.company if mine else dl["company"])
    from hq_api.archive import clearance as CL

    await CL.for_principal(tx, who)
    try:
        r = await _record(tx, ref)
    except ApiError as exc:
        if exc.status in (403, 404):
            return False, None
        raise
    company = await tx.scalar("SELECT code FROM core.companies WHERE id = :id", id=r["company_id"])
    return True, (who.company if company == who.company or holding_scope else str(company))


async def propose(tx: Tx, who: Principal, kind: str, ref: str, why_fa: str) -> dict[str, Any]:
    """`erase.propose`: a card `erase` to the owner with the preview's counts (the seal, 🔏 on the
    card's ref, runs the erase of exactly this kind and ref; rejecting it changes nothing)."""
    from hq_api.domain import decisions as D

    pv = await preview(tx, kind, ref)
    why = " ".join(why_fa.split())[:2000]
    kind_fa = {"session": "جلسه", "archive_record": "سند بایگانی", "output": "خروجی"}[kind]
    what = (
        f"با مُهر این کارت، {_counts_fa(kind, pv.counts)} برای همیشه پاک میشود و برنمیگردد.\n\n"
        "چه میماند:\n" + "\n".join(f"- {k}" for k in pv.keeps_fa)
    )
    open_card = await tx.scalar(
        """SELECT ref FROM cartable.decisions WHERE kind = 'erase' AND status = 'pending'
             AND payload ->> 'kind' = :k AND payload ->> 'ref' = :r LIMIT 1""",
        k=kind,
        r=ref,
    )
    if open_card:
        raise ApiError(
            409,
            "validation_failed",
            f"{open_card} already proposes this erase",
            message_fa=f"کارت {open_card} همین پاک کردن را پیشنهاد کرده و منتظر مدیر کل است.",
        )
    assert who.company_id is not None
    assert who.company is not None
    company_kind = await tx.scalar(
        "SELECT kind FROM core.companies WHERE id = :id", id=who.company_id
    )
    d = await D.propose(
        tx,
        who,
        company_id=who.company_id,
        company_code=who.company,
        body=D.DecisionIn(
            kind="erase",
            title=f"پاک کردن برای همیشه ({kind_fa}): {pv.title_fa}"[:300],
            what=what[:20000],
            why=why,
            risk="high",
            reversible=False,
            payload={
                "kind": kind,
                "ref": ref,
                "why_fa": why,
                "title_fa": pv.title_fa,
                "counts": pv.counts.model_dump(),
            },
        ),
        thread_code=await tx.scalar(
            """SELECT code FROM msg.threads WHERE code = :c
                 OR (employee_id = :e AND kind IN ('advisor', 'overseer', 'assistant', 'legal'))
               ORDER BY code = :c DESC LIMIT 1""",
            c=who.code,
            e=who.employee_id,
        ),
        company_kind=str(company_kind or "company"),
        system=True,
    )
    return dict(d)


async def apply_card(tx: Tx, d: dict[str, Any], who: Principal, step_up: bool) -> str:
    """The owner sealed an `erase` card (in its deciding transaction): exactly its kind and ref is
    erased. A thing already gone voids the card (409 decision_not_pending; nothing changes)."""
    p = d["payload"] or {}
    kind, ref = str(p.get("kind")), str(p.get("ref"))
    if kind not in KINDS:
        raise ApiError(
            422, "validation_failed", fields={"payload.kind": "session | archive_record | output"}
        )
    try:
        out = await erase(tx, who, kind, ref, step_up=step_up, card_ref=d["ref"])
    except ApiError as exc:
        if exc.status == 404:
            raise ApiError(
                409,
                "decision_not_pending",
                f"{ref} is gone already",
                message_fa="آنچه این کارت پاک میکرد دیگر نیست.",
            ) from exc
        raise
    c = out.erased
    return f"پاک شد: {ref} ({_counts_fa(kind, c)})"
