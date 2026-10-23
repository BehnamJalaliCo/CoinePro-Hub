"""What the hub files by itself (prompt 14 §7, contract §23.8): a closed list
of system sources, each switched on or off by the owner. The worker's
sources job (rule-only: database reads, a PDF made by the hub's own
libraries, no model, no outside call) looks for each source's new events and
files one `filed` record of the source's class per event, with
`source: {kind: "system", ref}` (unique: an event is filed once):

  charter_sealed        every sealed version of the holding charter or a
                        company's addendum (governance.charters, prompt 11;
                        nothing until that table exists)
  resolution_month      a company's sealed resolutions of a finished Jalali
                        month, as one PDF
  brand_sealed          every sealed (active) brand version (§18.14)
  founding_registration the sealed founding proposal (a company_found card)
  legal_email           every email the counsel's case sent (§22.4)
  case_closed           a closed legal case, its timeline
  server_plan_sealed    a sealed server plan (§18.8)
  backup_restore_test   the first restore test of each Jalali month (§18.9)

A system record is filed with what its source knows: a required field the
source cannot know stays missing (the schema's impact counts it; the
archivist completes it). Its text is the source's own (text_layer) and is
scanned for secrets like any file: an item that holds one is not filed and
the source's note says so (never what it was).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from hq_api.archive import scan
from hq_api.archive import store as ST
from hq_api.archive import vocab as V
from hq_api.archive.common import J
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal

log = logging.getLogger("hq_api.archive.sources")
SYSTEM = Principal(kind="service", code="archive", role="service")
PER_RUN = 20  # events filed per source per run (the rest next time)
LOOKBACK_MONTHS = 12


async def listing(tx: Tx) -> list[dict[str, Any]]:
    rows = await tx.all("SELECT * FROM archive.sources ORDER BY key")
    return [
        {
            "key": r["key"],
            "title_fa": r["title_fa"],
            "class": r["class_key"],
            "enabled": r["enabled"],
            "filed": r["filed"],
            "last_at": r["last_at"],
            "note_fa": r["note_fa"],
            "version": r["version"],
        }
        for r in rows
    ]


async def put(tx: Tx, switches: dict[str, Any]) -> list[dict[str, Any]]:
    errors = {k: "a system source of the closed list" for k in switches if k not in V.SOURCES}
    errors.update({k: "true or false" for k, v in switches.items() if not isinstance(v, bool)})
    if errors:
        raise ApiError(422, "schema_invalid", fields=errors)
    for k, on in switches.items():
        await tx.exec(
            "UPDATE archive.sources SET enabled = :on WHERE key = :k AND enabled <> :on", k=k, on=on
        )
    return await listing(tx)


# ================================================================= filing ==
async def file_system(
    hub: Any,
    txf: Any,
    *,
    source: str,
    source_ref: str,
    company_id: Any,
    title_fa: str,
    metadata: dict[str, Any],
    pdf_title: str,
    pdf_body: str,
    file_name: str,
    links: list[dict[str, Any]] | None = None,
) -> str | None:
    """One system record (filed) -> its ref, or None (already filed, refused,
    or the source's class is gone)."""
    from hq_api.archive import clearance as CL
    from hq_api.archive import pdf
    from hq_api.archive import records as R

    async with txf() as tx:
        await CL.full(tx)
        if await tx.scalar(
            "SELECT 1 FROM archive.records WHERE source_kind = 'system' AND source_ref = :s",
            s=source_ref,
        ):
            return None
        src = await tx.first("SELECT * FROM archive.sources WHERE key = :k", k=source)
        if src is None or not src["enabled"]:
            return None
        co = await tx.one("SELECT id, code, kind FROM core.companies WHERE id = :c", c=company_id)
        cls = await R.resolve_class(tx, src["class_key"], co["code"])
        lv = await R.resolve_level(tx, None, cls, None)
    text = f"{pdf_title}\n\n{pdf_body}"
    if scan.kinds(text) or scan.values_kinds(metadata):
        async with txf() as tx:
            await tx.exec(
                """UPDATE archive.sources SET note_fa = :n WHERE key = :k""",
                k=source,
                n=f"یک مورد ({source_ref.split(':')[0]}) الگوی رمز داشت و بایگانی نشد"[:500],
            )
        log.warning("a system source item held a secret pattern", extra={"source": source})
        return None
    data, pages = await pdf.render(hub, pdf_title, pdf_body, footer=f"CoinePro HQ · {source_ref}")
    sha = hashlib.sha256(data).hexdigest()
    wrapped = None
    blob = data
    fid = uuid.uuid4()
    if lv["encrypt"]:
        v = ST.vault(hub)
        if v is None:
            return None
        dek, wrapped = await v.new_key()
        blob = ST.encrypt(dek, data, str(fid).encode())
    key, stored_sha = await hub.storage.put(blob)
    it = ST.Intake(
        file_id=fid,
        name=file_name,
        mime="application/pdf",
        size=len(data),
        sha256=sha,
        storage_key=key,
        pages=pages,
        text_state="text_layer",
        text=text[:400_000],
        ocr_confidence=None,
    )
    stored = [ST.Stored(it, key, stored_sha, bool(lv["encrypt"]), wrapped)]
    try:
        async with txf() as tx:
            await CL.full(tx)
            co = await tx.one(
                "SELECT id, code, kind FROM core.companies WHERE id = :c", c=company_id
            )
            cls = await R.resolve_class(tx, src["class_key"], co["code"])
            folder = await R.default_folder(tx, co["id"], co["code"], cls)
            fields = list(cls["fields"]) if cls else []
            # only the values that fit the class's fields (never a refusal here)
            known = {f["key"] for f in fields}
            meta, _missing, _errors = V.validate_metadata(
                fields, {k: v for k, v in metadata.items() if k in known}, complete=False
            )
            r = await R.create(
                tx,
                SYSTEM,
                scope=co,
                cls=cls,
                title_fa=title_fa[:300],
                metadata=meta,
                lv=lv,
                folder=folder,
                stored=stored,
                parties=None,
                links=links,
                file_now=False,
                source_kind="system",
                source_ref=source_ref,
            )
            # Filed by the hub itself: what the source knows (a required field
            # it cannot know stays missing for the archivist).
            await tx.exec(
                "UPDATE archive.records SET state = 'filed', filed_at = now() WHERE id = :id",
                id=r["id"],
            )
            r = await R.load(tx, r["ref"])
            from hq_api.archive import automations as AU
            from hq_api.archive import retention as RT

            await RT.compute(tx, r, cls, fields)
            await R.emit(tx, r, "record.filed", change="system", source=source)
            await AU.fire(tx, "filed", r)
            await tx.exec(
                "UPDATE archive.sources SET filed = filed + 1, last_at = now(), note_fa = NULL WHERE key = :k",
                k=source,
            )
            return str(r["ref"])
    except BaseException:
        await hub.storage.destroy(key)
        raise


# ================================================================= events ==
def _md(lines: list[str]) -> str:
    return "\n".join(lines)


async def _charters(hub: Any, txf: Any) -> int:
    async with txf() as tx:
        if not await tx.scalar("SELECT to_regclass('governance.charters') IS NOT NULL"):
            return 0
        rows = await tx.all(
            """SELECT scope, version, body_md, red_lines, body_sha256, sealed_at FROM governance.charters
               WHERE sealed_at IS NOT NULL ORDER BY sealed_at LIMIT 200"""
        )
        out = []
        for x in rows:
            ref = f"charter:{x['scope']}@{x['version']}"
            if await tx.scalar(
                "SELECT 1 FROM archive.records WHERE source_kind = 'system' AND source_ref = :s",
                s=ref,
            ):
                continue
            code = x["scope"]
            co = await tx.first(
                "SELECT id FROM core.companies WHERE code = :c OR (:c = 'holding' AND kind = 'holding') LIMIT 1",
                c=code,
            )
            if co is not None:
                out.append((ref, co["id"], x))
    n = 0
    for ref, cid, x in out[:PER_RUN]:
        name = "اساسنامه‌ی هلدینگ" if x["scope"] == "holding" else f"الحاقیه‌ی {x['scope']}"
        red = J(x["red_lines"], []) or []
        body = (
            (x["body_md"] or "")
            + "\n\nخطوط قرمز:\n"
            + "\n".join(f"- {r.get('text_fa', '')}" for r in red if isinstance(r, dict))
        )
        got = await file_system(
            hub,
            txf,
            source="charter_sealed",
            source_ref=ref,
            company_id=cid,
            title_fa=f"{name}، نسخه‌ی {x['version']} (مُهرشده)",
            metadata={
                "policy": name,
                "version": int(x["version"]),
                "sealed_at": x["sealed_at"].date().isoformat(),
                "digest": x["body_sha256"],
            },
            pdf_title=f"{name} — نسخه‌ی {x['version']}",
            pdf_body=body,
            file_name=f"charter-{x['scope']}-v{x['version']}.pdf",
        )
        n += 1 if got else 0
    return n


def _jalali_key(d: date) -> str:
    from hq_api.worker.jalali import to_jalali

    y, m, _ = to_jalali(d)
    return f"{y:04d}-{m:02d}"


async def _resolutions(hub: Any, txf: Any, today: date) -> int:
    this_month = _jalali_key(today)
    async with txf() as tx:
        rows = await tx.all(
            """SELECT r.ref, r.title, r.body, r.sealed_at, r.company_id, c.code
               FROM cartable.resolutions r JOIN core.companies c ON c.id = r.company_id
               WHERE r.sealed_at > now() - CAST(:lb AS interval) ORDER BY r.sealed_at, r.ref""",
            lb=timedelta(days=LOOKBACK_MONTHS * 31),
        )
    groups: dict[tuple[Any, str, str], list[dict[str, Any]]] = {}
    for x in rows:
        month = _jalali_key(x["sealed_at"].date())
        if month >= this_month:
            continue  # only finished months
        groups.setdefault((x["company_id"], x["code"], month), []).append(x)
    n = 0
    for (cid, code, month), items in sorted(groups.items(), key=lambda kv: kv[0][2]):
        if n >= PER_RUN:
            break
        ref = f"resolutions:{code}:{month}"
        body = _md(
            [
                f"{x['ref']} · {x['sealed_at'].date().isoformat()} · {x['title']}\n{(x['body'] or '')[:1500]}\n"
                for x in items
            ]
        )
        got = await file_system(
            hub,
            txf,
            source="resolution_month",
            source_ref=ref,
            company_id=cid,
            title_fa=f"مصوبه‌های {month} ({code})",
            metadata={
                "month": month,
                "count": len(items),
                "first_ref": items[0]["ref"],
                "last_ref": items[-1]["ref"],
            },
            pdf_title=f"مصوبه‌های ماه {month} — {code}",
            pdf_body=body,
            file_name=f"resolutions-{code}-{month}.pdf",
        )
        n += 1 if got else 0
    return n


async def _brands(hub: Any, txf: Any) -> int:
    async with txf() as tx:
        rows = await tx.all(
            """SELECT b.company_id, b.version, b.digest, b.ink, b.accent, b.palette, b.activated_at, c.code
               FROM org.company_brands b JOIN core.companies c ON c.id = b.company_id
               WHERE b.step_up_id IS NOT NULL AND b.activated_at IS NOT NULL ORDER BY b.activated_at LIMIT 200"""
        )
    n = 0
    for x in rows:
        if n >= PER_RUN:
            break
        palette = ", ".join(
            str(p.get("hex") if isinstance(p, dict) else p) for p in J(x["palette"], []) or []
        )
        got = await file_system(
            hub,
            txf,
            source="brand_sealed",
            source_ref=f"brand:{x['code']}@{x['version']}",
            company_id=x["company_id"],
            title_fa=f"نشان مُهرشده‌ی {x['code']}، نسخه‌ی {x['version']}",
            metadata={
                "version": int(x["version"]),
                "sealed_at": x["activated_at"].date().isoformat(),
                "digest": x["digest"] or "",
            },
            pdf_title=f"نشان و مُهر {x['code']} — نسخه‌ی {x['version']}",
            pdf_body=f"رنگ متن: {x['ink']}\nرنگ تأکید: {x['accent'] or '-'}\nپالت: {palette or '-'}\n"
            f"چکیده‌ی مُهر: {x['digest'] or '-'}",
            file_name=f"brand-{x['code']}-v{x['version']}.pdf",
        )
        n += 1 if got else 0
    return n


async def _foundings(hub: Any, txf: Any) -> int:
    async with txf() as tx:
        rows = await tx.all(
            """SELECT d.ref, d.title, d.what, d.payload, d.decided_at, d.company_id
               FROM cartable.decisions d WHERE d.kind = 'company_found' AND d.status = 'approved'
               ORDER BY d.decided_at LIMIT 200"""
        )
        out = []
        for x in rows:
            p = J(x["payload"], {})
            code = p.get("code") or p.get("company")
            co = (
                await tx.first("SELECT id FROM core.companies WHERE code = :c", c=code)
                if code
                else None
            )
            out.append((x, co["id"] if co else x["company_id"]))
    n = 0
    for x, cid in out:
        if n >= PER_RUN:
            break
        p = J(x["payload"], {})
        got = await file_system(
            hub,
            txf,
            source="founding_registration",
            source_ref=f"founding:{x['ref']}",
            company_id=cid,
            title_fa=f"پیشنهاد مُهرشده‌ی تأسیس: {x['title']}"[:300],
            metadata={"registered_at": x["decided_at"].date().isoformat()},
            pdf_title=f"پیشنهاد تأسیس — {x['ref']}",
            pdf_body=(x["what"] or "")
            + "\n\n"
            + json.dumps(p, ensure_ascii=False, indent=1, default=str)[:20000],
            file_name=f"founding-{x['ref']}.pdf",
            links=[{"kind": "evidence_for", "to": {"kind": "decision", "ref": x["ref"]}}],
        )
        n += 1 if got else 0
    return n


async def _emails(hub: Any, txf: Any) -> int:
    async with txf() as tx:
        rows = await tx.all(
            """SELECT e.message_id, e.subject, e.body_md, e.to_addrs, e.cc_addrs, e.from_addr, e.sent_at,
                      e.attachments, e.company_id, k.ref AS case_ref, k.title_fa
               FROM legal.emails e JOIN legal.cases k ON k.id = e.case_id
               WHERE e.direction = 'out' AND e.state = 'sent' ORDER BY e.sent_at LIMIT 500"""
        )
    n = 0
    for x in rows:
        if n >= PER_RUN:
            break
        mid = hashlib.sha256(x["message_id"].encode()).hexdigest()[:24]
        atts = "\n".join(
            f"- {a.get('name')} (sha256 {a.get('sha256')})" for a in J(x["attachments"], []) or []
        )
        body = (
            f"از: {x['from_addr']}\nبه: {', '.join(x['to_addrs'] or [])}\n"
            + (f"رونوشت: {', '.join(x['cc_addrs'] or [])}\n" if x["cc_addrs"] else "")
            + f"تاریخ: {x['sent_at'].isoformat()}\nموضوع: {x['subject']}\nپرونده: {x['case_ref']}\n\n{x['body_md']}"
            + (f"\n\nپیوست‌ها:\n{atts}" if atts else "")
        )
        got = await file_system(
            hub,
            txf,
            source="legal_email",
            source_ref=f"email:{mid}",
            company_id=x["company_id"],
            title_fa=f"ایمیل حقوقی {x['case_ref']}: {x['subject']}"[:300],
            metadata={
                "case": {"kind": "case", "ref": x["case_ref"]},
                "direction": "out",
                "date": x["sent_at"].date().isoformat(),
                "subject": x["subject"][:500],
            },
            pdf_title=f"ایمیل ارسال‌شده — {x['case_ref']}",
            pdf_body=body,
            file_name=f"email-{x['case_ref']}-{mid[:8]}.pdf",
        )
        n += 1 if got else 0
    return n


async def _cases(hub: Any, txf: Any) -> int:
    async with txf() as tx:
        rows = await tx.all(
            """SELECT k.id, k.ref, k.title_fa, k.kind, k.brief_md, k.closed_at, k.company_id
               FROM legal.cases k WHERE k.status = 'closed' ORDER BY k.closed_at LIMIT 500"""
        )
        events_of = {}
        for x in rows:
            events_of[x["id"]] = await tx.all(
                "SELECT at, kind, summary_fa FROM legal.case_events WHERE case_id = :c ORDER BY at, id",
                c=x["id"],
            )
    n = 0
    for x in rows:
        if n >= PER_RUN:
            break
        timeline = "\n".join(
            f"- {e['at'].date().isoformat()} · {e['kind']} · {e['summary_fa']}"
            for e in events_of[x["id"]]
        )
        got = await file_system(
            hub,
            txf,
            source="case_closed",
            source_ref=f"case:{x['ref']}",
            company_id=x["company_id"],
            title_fa=f"پرونده‌ی بسته‌شده {x['ref']}: {x['title_fa']}"[:300],
            metadata={
                "case": {"kind": "case", "ref": x["ref"]},
                "date": x["closed_at"].date().isoformat(),
                "subject": x["title_fa"][:500],
            },
            pdf_title=f"پرونده‌ی {x['ref']} — {x['title_fa']}",
            pdf_body=f"نوع: {x['kind']}\n\n{x['brief_md']}\n\nروند پرونده:\n{timeline}",
            file_name=f"case-{x['ref']}.pdf",
        )
        n += 1 if got else 0
    return n


async def _plans(hub: Any, txf: Any) -> int:
    async with txf() as tx:
        rows = await tx.all(
            """SELECT ref, company_id, company_code, name, type, location, image, monthly_eur, software, firewall,
                      sealed_digest, sealed_at
               FROM provisioning.plans WHERE sealed_at IS NOT NULL ORDER BY sealed_at LIMIT 200"""
        )
    n = 0
    for x in rows:
        if n >= PER_RUN:
            break
        body = (
            f"شرکت: {x['company_code']}\nنام: {x['name']}\nنوع: {x['type']} · {x['location']} · {x['image']}\n"
            f"هزینه‌ی ماهانه: {x['monthly_eur']} EUR\nنرم‌افزار: {json.dumps(J(x['software'], []), ensure_ascii=False)}\n"
            f"فایروال: {json.dumps(J(x['firewall'], []), ensure_ascii=False)}\nچکیده‌ی مُهر: {x['sealed_digest']}"
        )
        got = await file_system(
            hub,
            txf,
            source="server_plan_sealed",
            source_ref=f"server_plan:{x['ref']}",
            company_id=x["company_id"],
            title_fa=f"طرح سرور مُهرشده {x['ref']} ({x['company_code']})",
            metadata={
                "date": x["sealed_at"].date().isoformat(),
                "subject": f"{x['name']} {x['type']}"[:500],
            },
            pdf_title=f"طرح سرور {x['ref']}",
            pdf_body=body,
            file_name=f"server-plan-{x['ref']}.pdf",
        )
        n += 1 if got else 0
    return n


async def _restore_tests(hub: Any, txf: Any) -> int:
    async with txf() as tx:
        rows = await tx.all(
            """SELECT at, ok, duration_s, source, snapshot, notes, detail, company_id FROM backup.restore_tests
               WHERE at > now() - CAST(:lb AS interval) ORDER BY at""",
            lb=timedelta(days=LOOKBACK_MONTHS * 31),
        )
    firsts: dict[str, dict[str, Any]] = {}
    for x in rows:
        firsts.setdefault(_jalali_key(x["at"].date()), x)
    n = 0
    for month, x in sorted(firsts.items()):
        if n >= PER_RUN:
            break
        detail = J(x["detail"], {})
        body = (
            f"زمان: {x['at'].isoformat()}\nنتیجه: {'موفق' if x['ok'] else 'ناموفق'}\nمدت: {x['duration_s']} ثانیه\n"
            f"منبع: {x['source']}\nsnapshot: {x['snapshot']}\nیادداشت: {x['notes'] or '-'}\n\n"
            + json.dumps(detail, ensure_ascii=False, indent=1, default=str)[:8000]
        )
        got = await file_system(
            hub,
            txf,
            source="backup_restore_test",
            source_ref=f"restore:{month}",
            company_id=x["company_id"],
            title_fa=f"نتیجه‌ی آزمون بازیابی ماه {month}: {'موفق' if x['ok'] else 'ناموفق'}",
            metadata={"date": x["at"].date().isoformat(), "subject": f"restore test {month}"},
            pdf_title=f"آزمون بازیابی — {month}",
            pdf_body=body,
            file_name=f"restore-test-{month}.pdf",
        )
        n += 1 if got else 0
    return n


async def run(hub: Any, txf: Any, today: date | None = None) -> dict[str, Any]:
    """The sources job: each enabled source's new events, filed once."""
    today = today or datetime.now(UTC).date()
    async with txf() as tx:
        enabled = {r["key"] for r in await tx.all("SELECT key FROM archive.sources WHERE enabled")}
    jobs: dict[str, Callable[[], Awaitable[int]]] = {
        "charter_sealed": lambda: _charters(hub, txf),
        "resolution_month": lambda: _resolutions(hub, txf, today),
        "brand_sealed": lambda: _brands(hub, txf),
        "founding_registration": lambda: _foundings(hub, txf),
        "legal_email": lambda: _emails(hub, txf),
        "case_closed": lambda: _cases(hub, txf),
        "server_plan_sealed": lambda: _plans(hub, txf),
        "backup_restore_test": lambda: _restore_tests(hub, txf),
    }
    out: dict[str, Any] = {}
    for key, job in jobs.items():
        if key not in enabled:
            out[key] = "off"
            continue
        try:
            out[key] = await job()
        except Exception as exc:  # noqa: BLE001 - one source never stops the others
            log.warning("archive source failed", extra={"source": key, "error": type(exc).__name__})
            out[key] = f"failed: {type(exc).__name__}"
    return out
