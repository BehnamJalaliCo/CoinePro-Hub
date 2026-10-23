"""Spoken briefings and the CEOs' weekly letters (prompt 12 §4, contract §21.4).

Briefing BR-0001: a written report (the morning report of prompt 5, or a
CEO's weekly letter) and its Persian voice. The text is the report itself,
no new number; the spoken script is built by code (hq_api.speech). The voice
is made on the hub by the TTS one-shot (opt-in profile `tts`, Piper): it
claims the oldest `pending` briefing over /internal/v1/tts/claim and sends the
Ogg back with /done. With TTS off the briefing is `audio_state: "off"` and the
text is unchanged.

Nothing here is generated while the holding is locked (owner decision
2026-10-22): no briefing, no letter work, no TTS claim. The rule-only lines
the morning report gains (waste, reminders) are not gated.

The weekly letter: Saturday (owner zone, default 09:00) one work item for the
CEO of every active operating company, with a facts pack built by code (≤ 40 000
tokens; the letter ≤ 600 words). A figure not in the facts pack sends the
letter back once (422 on deliver); the second time it is published marked
«عدد بی‌منبع» and a PR-001 finding opens.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import gate, hiring, notify, oversight
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.speech import assert_spoken, fa_speech_script, word_count

SERVICE = Principal(kind="service", code="briefings", role="service")
PIPER_VERSION = "1.3.0"
# The voices of rhasspy/piper-voices, each with its MODEL_CARD's dataset licence
# (read 2026-10-22). Only a free licence is a default; NC only by the owner.
VOICES = {
    "fa_IR-amir-medium": "CC0-1.0 (dataset, MODEL_CARD); weights MIT (rhasspy/piper-voices)",
    "fa_IR-ganji-medium": "CC0-1.0 (dataset, MODEL_CARD); weights MIT (rhasspy/piper-voices)",
    "fa_IR-reza_ibrahim-medium": "CC0-1.0 (dataset, MODEL_CARD); weights MIT (rhasspy/piper-voices)",
}
LETTER_WORDS = 600
LETTER_TOKENS = 40_000
UNSOURCED = "«عدد بی‌منبع»"
TTS_RECLAIM_MIN = 15  # a claim not finished in this time is claimed again
TTS_MAX_ATTEMPTS = 3
DEFAULT_AUDIO = {"morning": True, "ceo_letters": True}
DEFAULT_LETTER = {"enabled": True, "day": "sa", "at": "09:00"}
DAYS = {"mo": 0, "tu": 1, "we": 2, "th": 3, "fr": 4, "sa": 5, "su": 6}
_NUM = re.compile(r"[0-9][0-9,]*(?:\.[0-9]+)?")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫٬", "01234567890123456789.,")
_LIST_MARK = re.compile(r"^\s*[0-9]+[.)]\s+", re.MULTILINE)


def voice(settings: Any) -> dict[str, str]:
    name = settings.tts_voice if settings.tts_voice in VOICES else "fa_IR-amir-medium"
    return {"engine": "piper", "version": PIPER_VERSION, "voice": name, "license": VOICES[name]}


async def _registry_voice(tx: Tx, settings: Any) -> dict[str, str]:
    """⟨1.6⟩ one registry for every voice (prompt 13 §4.1): the active voice of
    media.voices when the TTS image runs it, else the configured default."""
    from hq_api.domain import voices

    return await voices.briefing_voice(tx, settings)


async def owner_blocks(tx: Tx) -> tuple[dict[str, Any], dict[str, Any]]:
    row = (
        await tx.first("SELECT audio_briefings, ceo_weekly_letter FROM owner.settings WHERE id = 1")
        or {}
    )
    return (
        {**DEFAULT_AUDIO, **dict(row.get("audio_briefings") or {})},
        {**DEFAULT_LETTER, **dict(row.get("ceo_weekly_letter") or {})},
    )


# ------------------------------------------------------------ the script --
async def lookups(tx: Tx, text: str) -> dict[str, dict[str, str]]:
    """Titles of the refs and Persian titles of the codes the text names."""
    refs: dict[str, str] = {}
    found = set(re.findall(r"\b(?:D|W|O|M)-[0-9]{4,8}\b", text))
    for ref in found:
        title = await tx.scalar(
            """SELECT COALESCE(
                   (SELECT title FROM cartable.decisions WHERE ref = :r),
                   (SELECT title FROM work.work WHERE ref = :r),
                   (SELECT title FROM cartable.deliverables WHERE ref = :r),
                   (SELECT title FROM cartable.resolutions WHERE ref = :r))""",
            r=ref,
        )
        if title:
            refs[ref] = " ".join(str(title).split())[:120]
    codes: dict[str, str] = {}
    for code in set(re.findall(r"\b[A-Z][A-Z0-9]{1,9}-[A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)?\b", text)):
        title = await tx.scalar(
            """SELECT e.title_fa || ' ' || COALESCE(c.name_fa, c.code) FROM core.employees e
               JOIN core.companies c ON c.id = e.company_id WHERE e.code = :c""",
            c=code,
        )
        if title:
            codes[code] = str(title)
    companies = {
        r["code"]: r["name_fa"] or r["code"]
        for r in await tx.all("SELECT code, name_fa FROM core.companies")
    }
    return {"refs": refs, "codes": codes, "companies": companies}


async def script_of(tx: Tx, text: str) -> str:
    lk = await lookups(tx, text)
    script = fa_speech_script(text, refs=lk["refs"], codes=lk["codes"], companies=lk["companies"])
    assert_spoken(script)
    return script


# -------------------------------------------------------------- briefings --
async def create(
    tx: Tx,
    settings: Any,
    *,
    kind: str,
    company_id: UUID,
    company_code: str,
    period: tuple[date, date],
    deliverable: dict[str, Any],
    text_md: str,
    audio_wanted: bool,
    unsourced: bool = False,
) -> dict[str, Any] | None:
    """One briefing (idempotent per kind, company and period start)."""
    if await tx.scalar(
        "SELECT 1 FROM reports.briefings WHERE kind = :k AND company_id = :co AND period_from = :f",
        k=kind,
        co=company_id,
        f=period[0],
    ):
        return None
    tts = audio_wanted and settings.tts
    script = await script_of(tx, text_md) if tts else None
    row = await tx.one(
        """INSERT INTO reports.briefings (company_id, kind, period_from, period_to, deliverable_id,
               deliverable_ref, text_md, script, audio_state, voice, unsourced)
           VALUES (:co, :k, :f, :t, :dl, :dref, :text, :script, :state, CAST(:voice AS jsonb), :uns)
           RETURNING *""",
        co=company_id,
        k=kind,
        f=period[0],
        t=period[1],
        dl=deliverable["id"],
        dref=deliverable["ref"],
        text=text_md,
        script=script,
        state="pending" if tts else "off",
        voice=json.dumps(await _registry_voice(tx, settings)) if tts else None,
        uns=unsourced,
    )
    await events.emit(
        tx,
        company_code,
        "briefing.ready",
        row["ref"],
        {"kind": kind, "audio_state": row["audio_state"], "deliverable": deliverable["ref"]},
    )
    await audit.record(
        tx,
        audit.SYSTEM,
        company_id=company_id,
        action="briefing.create",
        action_class="A1",
        target_kind="briefing",
        target_ref=row["ref"],
        summary=f"{kind} from {deliverable['ref']}, audio {row['audio_state']}",
    )
    return row


async def morning(
    tx: Tx, settings: Any, holding: Any, deliverable: dict[str, Any], text_md: str, day: date
) -> dict[str, Any] | None:
    """The morning report's briefing (after the written report; same text).
    Nothing while the holding is locked."""
    if await gate.holding_lock(tx) is not None:
        return None
    audio, _ = await owner_blocks(tx)
    return await create(
        tx,
        settings,
        kind="morning",
        company_id=holding.id,
        company_code=holding.code,
        period=(day, day),
        deliverable=deliverable,
        text_md=text_md,
        audio_wanted=bool(audio.get("morning", True)),
    )


SQL = """
    SELECT b.*, c.code AS company FROM reports.briefings b JOIN core.companies c ON c.id = b.company_id
"""


async def render(tx: Tx, r: dict[str, Any]) -> dict[str, Any]:
    from hq_api.domain import files as F

    audio = None
    if r["audio_file_id"]:
        audio = (await F.refs(tx, [r["audio_file_id"]])).get(r["audio_file_id"])
    return {
        "id": r["id"],
        "ref": r["ref"],
        "kind": r["kind"],
        "company": r["company"],
        "period": {"from": r["period_from"], "to": r["period_to"]},
        "deliverable_ref": r["deliverable_ref"],
        "text_md": r["text_md"],
        "audio": audio,
        "audio_state": r["audio_state"],
        "voice": r["voice"],
        "created_at": r["created_at"],
    }


# -------------------------------------------------------------- the TTS job --
async def claim(tx: Tx) -> dict[str, Any] | None:
    """The oldest pending briefing for the TTS one-shot; None while the
    holding is locked or when there is nothing to say."""
    if await gate.holding_lock(tx) is not None:
        return None
    row = await tx.first(
        """SELECT b.id, b.ref, b.script, b.voice, b.tts_attempts FROM reports.briefings b
           WHERE b.audio_state = 'pending'
             AND (b.tts_claimed_at IS NULL OR b.tts_claimed_at < now() - make_interval(mins => :m))
           ORDER BY b.created_at LIMIT 1 FOR UPDATE SKIP LOCKED""",
        m=TTS_RECLAIM_MIN,
    )
    if row is None:
        return None
    if int(row["tts_attempts"]) >= TTS_MAX_ATTEMPTS:
        await tx.exec(
            """UPDATE reports.briefings SET audio_state = 'failed', tts_error = 'too many attempts',
                   updated_at = now() WHERE id = :id""",
            id=row["id"],
        )
        return None
    await tx.exec(
        """UPDATE reports.briefings SET tts_claimed_at = now(), tts_attempts = tts_attempts + 1,
               updated_at = now() WHERE id = :id""",
        id=row["id"],
    )
    v = row["voice"] or {}
    return {
        "id": row["id"],
        "ref": row["ref"],
        "script": row["script"] or "",
        "voice": v.get("voice"),
    }


async def finish(
    tx: Tx, briefing_id: UUID, *, key: str, sha: str, size: int, duration_s: float | None
) -> dict[str, Any]:
    b = await tx.one(SQL + " WHERE b.id = :id FOR UPDATE OF b", id=briefing_id)
    if b["audio_state"] != "pending":
        raise ApiError(409, "validation_failed", f"{b['ref']} is {b['audio_state']}")
    from hq_api.domain import files as F

    fid = await F.insert(
        tx,
        company_id=b["company_id"],
        name=f"{b['ref']}.ogg",
        mime="audio/ogg",
        size=size,
        sha256=sha,
        storage_key=key,
        kind="audio",
        by_kind="service",
        by_code="tts",
        duration_s=duration_s,
    )
    await tx.exec(
        """UPDATE reports.briefings SET audio_state = 'ready', audio_file_id = :f, tts_error = NULL,
               updated_at = now() WHERE id = :id""",
        f=fid,
        id=b["id"],
    )
    await events.emit(
        tx, b["company"], "briefing.ready", b["ref"], {"kind": b["kind"], "audio_state": "ready"}
    )
    await audit.record(
        tx,
        Principal(kind="service", code="tts", role="service"),
        company_id=b["company_id"],
        action="briefing.audio",
        action_class="A1",
        target_kind="briefing",
        target_ref=b["ref"],
        summary=f"audio/ogg, {size} bytes",
    )
    return {**b, "audio_state": "ready", "audio_file_id": fid}


async def fail(tx: Tx, briefing_id: UUID, error: str) -> None:
    b = await tx.one(SQL + " WHERE b.id = :id FOR UPDATE OF b", id=briefing_id)
    final = int(b["tts_attempts"]) >= TTS_MAX_ATTEMPTS
    await tx.exec(
        """UPDATE reports.briefings SET audio_state = CASE WHEN :final THEN 'failed' ELSE 'pending' END,
               tts_error = :e, tts_claimed_at = NULL, updated_at = now() WHERE id = :id""",
        final=final,
        e=re.sub(r"[^A-Za-z0-9 _.:-]", "", error)[:300] or "failed",
        id=b["id"],
    )
    if final:
        await events.emit(
            tx,
            b["company"],
            "briefing.ready",
            b["ref"],
            {"kind": b["kind"], "audio_state": "failed"},
        )


# ------------------------------------------------------ the weekly letter --
def numbers_of(text: str) -> set[str]:
    """The figures of a text, normalised (digits, separators, trailing zeros)."""
    out: set[str] = set()
    for raw in _NUM.findall(_LIST_MARK.sub("", text.translate(_DIGITS))):
        s = raw.replace(",", "").rstrip(".")
        if not s:
            continue
        try:
            d = Decimal(s)
        except ArithmeticError:
            continue
        out.add(format(d.normalize(), "f"))
    return out


def unsourced(letter: str, figures: set[str]) -> list[str]:
    return sorted(n for n in numbers_of(letter) if n not in figures)


async def facts(
    tx: Tx, company: dict[str, Any], start_day: date, end_day: date, zone: ZoneInfo
) -> dict[str, Any]:
    """The facts pack of one company's week [start_day, end_day), by code."""
    s = datetime.combine(start_day, time.min, tzinfo=zone).astimezone(UTC)
    e = datetime.combine(end_day, time.min, tzinfo=zone).astimezone(UTC)
    co = company["id"]
    rollup = await tx.first(
        "SELECT data FROM people.star_rollups WHERE period = 'week' AND key = :k",
        k=start_day.isoformat(),
    )
    standing = next(
        (
            c
            for c in ((rollup or {}).get("data") or {}).get("companies", [])
            if c["company"] == company["code"]
        ),
        None,
    )
    spend = await tx.one(
        """SELECT COALESCE(sum(COALESCE(k.input_tokens, 0) + COALESCE(k.output_tokens, 0)
                               + COALESCE(k.cache_read_tokens, 0) + COALESCE(k.cache_write_tokens, 0)), 0) AS tokens,
                  COALESCE(sum(COALESCE(k.cost_usd, 0) + COALESCE(k.equiv_cost_usd, 0)), 0) AS usd
           FROM llm.calls k WHERE k.company_id = :co AND k.started_at >= :s AND k.started_at < :e""",
        co=co,
        s=s,
        e=e,
    )
    env = next((x for x in await hiring.envelopes(tx) if x.company == company["code"]), None)
    dl = await tx.one(
        """SELECT count(*) AS n, count(rt.score) AS rated, avg(rt.score) AS avg_rating
           FROM cartable.deliverables d
           LEFT JOIN LATERAL (SELECT x.score FROM cartable.ratings x WHERE x.deliverable_id = d.id
                              ORDER BY x.version_no DESC LIMIT 1) rt ON true
           WHERE d.company_id = :co AND d.created_at >= :s AND d.created_at < :e""",
        co=co,
        s=s,
        e=e,
    )
    incidents = await tx.one(
        """SELECT count(*) AS opened, count(*) FILTER (WHERE severity = 'sev1') AS sev1,
                  count(*) FILTER (WHERE closed_at IS NULL) AS still_open
           FROM ops.incidents WHERE company_id = :co AND opened_at >= :s AND opened_at < :e""",
        co=co,
        s=s,
        e=e,
    )
    findings = await tx.all(
        """SELECT severity, count(*) AS n FROM oversight.findings
           WHERE company_id = :co AND status NOT IN ('verified', 'closed') GROUP BY severity ORDER BY severity""",
        co=co,
    )
    challenge = await tx.first(
        """SELECT ref, title_fa, status, score FROM oversight.challenges
           WHERE company_id = :co AND period = 'week' AND period_key = :k ORDER BY created_at DESC LIMIT 1""",
        co=co,
        k=start_day,
    )
    revenue = await tx.first(
        """SELECT count(*) AS days, COALESCE(sum(commission_usdt), 0) AS commission,
                  COALESCE(sum(new_invitees), 0) AS invitees
           FROM revenue.days WHERE company_id = :co AND day >= :a AND day < :b""",
        co=co,
        a=start_day,
        b=end_day,
    )
    plan = await tx.all(
        """SELECT ref, title FROM work.work WHERE company_id = :co AND parent_id IS NULL
             AND status IN ('queued', 'in_progress', 'waiting') AND due_at >= :e AND due_at < :n
           ORDER BY due_at LIMIT 5""",
        co=co,
        e=e,
        n=e + timedelta(days=7),
    )
    return {
        "company": company["code"],
        "week": {"from": start_day.isoformat(), "to": (end_day - timedelta(days=1)).isoformat()},
        "kpis": None,  # no KPI store is connected: «وصل نیست», never an estimate
        "stars": {k: standing.get(k) for k in ("stars", "score", "rank")} if standing else None,
        "spend": {
            "tokens_week": int(spend["tokens"]),
            "usd_week": str(Decimal(spend["usd"]).quantize(Decimal("0.01"))),
            "tokens_month": env.used_month if env else None,
            "envelope_month": env.tokens_month if env else None,
        },
        "deliverables": {
            "count": int(dl["n"]),
            "rated": int(dl["rated"]),
            "avg_rating": round(float(dl["avg_rating"]), 1)
            if dl["avg_rating"] is not None
            else None,
        },
        "incidents": {k: int(incidents[k]) for k in ("opened", "sev1", "still_open")},
        "findings_open": {r["severity"]: int(r["n"]) for r in findings},
        "challenge": {
            "ref": challenge["ref"],
            "title_fa": challenge["title_fa"],
            "status": challenge["status"],
            "score": challenge["score"],
        }
        if challenge
        else None,
        "revenue": {
            "commission_usdt": str(Decimal(revenue["commission"]).quantize(Decimal("0.01"))),
            "days": int(revenue["days"]),
            "new_invitees": int(revenue["invitees"]),
        }
        if revenue and int(revenue["days"])
        else None,  # no revenue account: «وصل نیست»
        "next_week": [{"ref": p["ref"], "title": p["title"]} for p in plan],
    }


def facts_md(f: dict[str, Any]) -> str:
    return "```json\n" + json.dumps(f, ensure_ascii=False, indent=1, default=str) + "\n```"


async def letters(tx: Tx, now: datetime | None = None) -> dict[str, Any]:
    """The weekly letters of this Saturday at the owner's hour (idempotent).
    Nothing while the holding is locked; a locked company gets none."""
    if (lock := await gate.holding_lock(tx)) is not None:
        return gate.skipped(lock)
    _, cfg = await owner_blocks(tx)
    if not cfg.get("enabled", True):
        return {"skipped": True, "reason": "off"}
    zone = ZoneInfo(
        str(await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran")
    )
    local = (now or datetime.now(UTC)).astimezone(zone)
    hh, mm = (int(x) for x in str(cfg.get("at") or "09:00").split(":"))
    if local.weekday() != DAYS.get(str(cfg.get("day") or "sa"), 5) or (local.hour, local.minute) < (
        hh,
        mm,
    ):
        return {"skipped": True, "reason": "not_the_hour"}
    week = local.date() - timedelta(days=(local.weekday() - 5) % 7)  # the Saturday it is written
    start_day, end_day = week - timedelta(days=7), week
    made: list[str] = []
    companies = await tx.all(
        "SELECT id, code, kind FROM core.companies WHERE kind = 'company' AND status = 'active' ORDER BY code"
    )
    for c in companies:
        if await gate.automation_lock(tx, c["id"]) is not None:
            continue
        if await tx.scalar(
            "SELECT 1 FROM reports.ceo_letters WHERE company_id = :co AND week = :w",
            co=c["id"],
            w=week,
        ):
            continue
        ceo = await tx.scalar(
            "SELECT code FROM core.employees WHERE company_id = :co AND kind = 'ceo' AND status = 'active'"
            " ORDER BY created_at LIMIT 1",
            co=c["id"],
        )
        if ceo is None:
            continue
        pack = await facts(tx, dict(c), start_day, end_day, zone)
        md = facts_md(pack)
        w = await W.create(
            tx,
            SERVICE,
            company_id=c["id"],
            company_code=c["code"],
            title=f"نامه‌ی هفتگی به مالک: {c['code']} {start_day.isoformat()}",
            brief=(
                f"نامه‌ی هفتگی‌ات به مالک (حداکثر {LETTER_WORDS} کلمه) را بنویس و با deliver تحویل بده. "
                "هر عددی که میآوری باید در بسته‌ی واقعیت‌های زیر باشد؛ عدد دیگری ننویس "
                "(عدد بی‌منبع نامه را یک بار برمیگرداند). جایی که داده‌ای «وصل نیست»، همین را بگو.\n\n"
                + md
            ),
            kind="one_off",
            priority="P3",
            assignee_code=str(ceo),
            budget=W.BudgetIn(tokens=LETTER_TOKENS),
        )
        await tx.exec(
            """INSERT INTO reports.ceo_letters (company_id, week, work_id, ceo_code, facts, figures)
               VALUES (:co, :w, :work, :ceo, CAST(:f AS jsonb), :figs)""",
            co=c["id"],
            w=week,
            work=w["id"],
            ceo=str(ceo),
            f=json.dumps(pack, ensure_ascii=False, default=str),
            figs=sorted(numbers_of(md)),
        )
        await audit.record(
            tx,
            SERVICE,
            company_id=c["id"],
            action="letter.open",
            action_class="A1",
            target_kind="work",
            target_ref=w["ref"],
            summary=f"weekly letter {week.isoformat()} for {ceo}",
        )
        made.append(w["ref"])
    return {"letters": made, "week": week.isoformat()}


async def letter_gate(ctx: Any, work_id: UUID, body_md: str) -> bool:
    """Before a deliver (its own transaction): a CEO letter's figures. A first
    unsourced attempt is sent back (422, recorded); the second is published
    marked. Returns True when this delivery is to be marked «عدد بی‌منبع»."""
    async with ctx.tx() as tx:
        letter = await tx.first(
            "SELECT * FROM reports.ceo_letters WHERE work_id = :w FOR UPDATE", w=work_id
        )
        if letter is None or letter["state"] == "published":
            return False
        if word_count(body_md) > LETTER_WORDS:
            raise ApiError(
                422,
                "validation_failed",
                f"the letter has {word_count(body_md)} words; at most {LETTER_WORDS}",
                fields={"body": f"at most {LETTER_WORDS} words"},
            )
        missing = unsourced(body_md, set(letter["figures"] or []))
        attempts = int(letter["attempts"]) + 1
        await tx.exec(
            """UPDATE reports.ceo_letters SET attempts = :a, unsourced = :u,
                   state = CASE WHEN :ret THEN 'returned' ELSE state END, updated_at = now()
               WHERE id = :id""",
            a=attempts,
            u=missing[:50],
            ret=bool(missing) and attempts == 1,
            id=letter["id"],
        )
    if missing and attempts == 1:
        raise ApiError(
            422,
            "validation_failed",
            "figures that are not in the facts pack: " + ", ".join(missing[:20]),
            fields={
                "body": "every figure must come from the facts pack: " + ", ".join(missing[:20])
            },
        )
    return bool(missing)


def marked(title: str, mark: bool) -> str:
    return f"{UNSOURCED} {title}"[:300] if mark else title


async def on_delivered(
    tx: Tx, settings: Any, w: dict[str, Any], dl: dict[str, Any], body_md: str, mark: bool
) -> None:
    """The deliver route's hook: a CEO letter arrived -> its briefing; a
    second unsourced attempt opens a PR-001 finding."""
    letter = await tx.first(
        "SELECT * FROM reports.ceo_letters WHERE work_id = :w AND state <> 'published' FOR UPDATE",
        w=w["id"],
    )
    if letter is None:
        return
    finding = None
    if mark:
        proto = await oversight.protocol_in_force(tx, "PR-001")
        f, _ = await oversight.raise_finding(
            tx,
            company_id=w["company_id"],
            company_code=w["company"],
            severity="medium",
            title_fa=f"عدد بی‌منبع در نامه‌ی هفتگی {dl['ref']}",
            body_md="Figures not in the facts pack: "
            + ", ".join(list(letter["unsourced"] or [])[:30]),
            evidence=[{"kind": "deliverable", "ref": dl["ref"], "note": "weekly CEO letter"}],
            protocol=proto,
            dedupe_key=f"letter:{letter['id']}",
        )
        finding = f["ref"]
    audio, _ = await owner_blocks(tx)
    b = await create(
        tx,
        settings,
        kind="ceo_letter",
        company_id=w["company_id"],
        company_code=w["company"],
        period=(letter["week"] - timedelta(days=7), letter["week"] - timedelta(days=1)),
        deliverable=dl,
        text_md=(f"{UNSOURCED}\n\n" if mark else "") + body_md,
        audio_wanted=bool(audio.get("ceo_letters", True)),
        unsourced=mark,
    )
    await tx.exec(
        """UPDATE reports.ceo_letters SET state = 'published', briefing_id = :b, finding_ref = :f,
               updated_at = now() WHERE id = :id""",
        b=b["id"] if b else None,
        f=finding,
        id=letter["id"],
    )
    holding = await tx.first("SELECT id, code FROM core.companies WHERE kind = 'holding' LIMIT 1")
    if holding is not None:
        await notify.raise_notification(
            tx,
            company_id=w["company_id"],
            company_code=w["company"],
            level="report",
            title_fa=f"نامه‌ی هفتگی {w['company']}" + (f" ({UNSOURCED})" if mark else ""),
            body_fa=dl["ref"],
            link_kind="deliverable",
            link_ref=dl["ref"],
        )
