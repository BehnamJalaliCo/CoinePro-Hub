"""The media studio (prompt 13 §2, contract §22.2 and §22.7): publishing series
the owner seals once, the items they make every day, and the pipeline that
carries an item from its script to its publishing.

    series   draft -> (series.propose: proposed + a media_series card) -> sealed
             on its digest (🔏 media.series); editing a sealed series takes it
             back to `proposed` (the seal no longer covers it); pause, retire.
    items    one per occurrence of a sealed series' RRULE (owner time zone),
             with the next topic of its pool; or a one-off (always a card).
    pipeline each step is a work item to the role that owns it, woken in
             order; code moves the item on:
               video (reel, a story with a duration):
                 script -> direction -> composition -> voice? -> render -> checks -> review
               still (post, carousel, an image story):
                 script -> composition (the visual designer's frames, or a
                 composition rendered to stills) -> checks -> review
               design (the UI designer's mockups, never published):
                 brief -> composition -> render -> review
             After the review: a sealed series with auto_publish, every check
             `pass` and every placement through an official API -> `scheduled`
             (published at the next occurrence of its schedule); anything else
             -> `waiting_owner` and a `media_publish` card (A3).

Models write the script, the direction and the composition; the schedule, the
checks, the render, the captions and the publishing are code. Every job that
runs on its own (the sweep, the render one-shot's claim, the narration's
claim, publishing) asks the launch gate first and does nothing while the
holding (or the item's company) is locked.

The narration is the voice registry's (domain/voices.py, §22.3): media.voice
queues a `narration` job there with the active voice, the TTS one-shot speaks
it, and voices.ON_NARRATION (on_narration below) brings the file to the item
and moves it on; a narration that failed for good lets it go on silent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import decisions as D
from hq_api.domain import gate, recurrence
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_common import composition as C

log = logging.getLogger("hq_api.studio")

SERVICE = Principal(kind="service", code="media", role="service")
SERIES_KINDS = ("reel", "story", "post", "carousel")
ITEM_KINDS = (*SERIES_KINDS, "design")
CHECK_KEYS = ("brand", "red_lines", "risk_warning", "facts", "rights", "platform", "qc")
PLACEMENT_CHANNEL = {
    "telegram_post": "telegram",
    "telegram_story": "telegram",
    "instagram_reel": "instagram",
    "instagram_story": "instagram",
    "instagram_post": "instagram",
}
PLACEMENTS_OF_KIND = {
    "reel": ("instagram_reel", "telegram_post"),
    "story": ("instagram_story", "telegram_story"),
    "post": ("instagram_post", "telegram_post"),
    "carousel": ("instagram_post", "telegram_post"),
}
# A Telegram channel story has no Bot API: always a card with the file (§22.2).
MANUAL_PLACEMENTS = ("telegram_story",)
SIZE = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080), "16:9": (1920, 1080)}
MB = 1024 * 1024
# The platforms' own limits (their published specs; checked by `platform`).
LIMITS: dict[str, dict[str, Any]] = {
    "instagram_reel": {"aspects": ("9:16",), "video": (3, 90, 100 * MB), "image": None},
    "instagram_story": {"aspects": ("9:16",), "video": (1, 60, 100 * MB), "image": 8 * MB},
    "instagram_post": {"aspects": ("4:5", "1:1"), "video": None, "image": 8 * MB},
    "telegram_post": {"aspects": tuple(SIZE), "video": (1, 600, 50 * MB), "image": 10 * MB},
    "telegram_story": {"aspects": ("9:16",), "video": (1, 60, 50 * MB), "image": 10 * MB},
}
PER_24H = {"instagram": 50, "telegram": None}  # Instagram: 50 API posts a day per account
# The safe zones of the placements (top, right, bottom, left), as the overlay
# composer of prompt 12 uses them (a reel shares the story's interface).
SAFE = {
    "instagram_reel": (0.14, 0.06, 0.20, 0.06),
    "instagram_story": (0.14, 0.06, 0.20, 0.06),
    "telegram_story": (0.12, 0.06, 0.18, 0.06),
    "instagram_post": (0.05, 0.05, 0.05, 0.05),
    "telegram_post": (0.06, 0.05, 0.06, 0.05),
}
DESIGN_PAGES = (
    {"name": "phone", "width": 390, "height": 844, "scale": 2},
    {"name": "desktop", "width": 1440, "height": 900, "scale": 1},
)
DEFAULT_MAX_PER_DAY = {"reel": 2, "story": 3, "post": 2, "carousel": 2}  # §0.9 #5
DEFAULT_FORMAT: dict[str, dict[str, Any]] = {
    "reel": {"aspect": "9:16", "duration_s": 30, "voice": {"voice_id": "default"}},
    "story": {"aspect": "9:16", "duration_s": 15, "voice": None},
    "post": {"aspect": "4:5", "duration_s": None, "voice": None},
    "carousel": {"aspect": "4:5", "duration_s": None, "voice": None},
}
STATE_OF_STEP = {
    "script": "scripting",
    "direction": "directing",
    "brief": "composing",
    "composition": "composing",
    "voice": "voicing",
    "render": "rendering",
    "checks": "checking",
    "review": "review",
}
STEP_FA = {
    "script": "سناریو",
    "direction": "کارگردانی",
    "brief": "بریف طراحی",
    "composition": "ترکیب‌بندی",
    "voice": "صدا",
    "review": "بازبینی",
}
TASK_CLASS = {
    "script": "media_script",
    "direction": "media_direction",
    "composition": "media_motion",
    "voice": "media_direction",
    "review": "media_review",
    "brief": "ui_design",
}
CATCH_UP = timedelta(minutes=30)  # missed occurrences older than this are skipped, never backfilled
RENDER_TIMEOUT_S = 600
STILL_AT_S = 3.0  # a still is the frame at 3 s (its entrance animations have settled)
RENDER_RECLAIM_MIN = 20
RENDER_MAX_ATTEMPTS = 3
ROLE_IN_NOTE = re.compile(
    r"\b(scriptwriter|video_director|motion_designer|voice_producer|visual_designer|ui_designer)\b"
)
STEP_OF_ROLE = {
    "scriptwriter": "script",
    "video_director": "direction",
    "motion_designer": "composition",
    "visual_designer": "composition",
    "ui_designer": "composition",
    "voice_producer": "voice",
}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def series_digest(company: str, s: dict[str, Any]) -> str:
    """SHA-256 of what the seal covers: the series as the owner saw it."""
    covered = {
        "company": company,
        **{
            k: s.get(k)
            for k in (
                "title_fa",
                "kind",
                "targets",
                "schedule",
                "topics",
                "format",
                "checks",
                "auto_publish",
                "max_per_day",
            )
        },
    }
    return hashlib.sha256(canonical(covered).encode()).hexdigest()


def is_video(kind: str, fmt: dict[str, Any] | None) -> bool:
    if kind == "reel":
        return True
    return kind == "story" and bool((fmt or {}).get("duration_s"))


def steps_of(kind: str, fmt: dict[str, Any] | None) -> list[str]:
    if kind == "design":
        return ["brief", "composition", "render", "review"]
    if is_video(kind, fmt):
        voice = ["voice"] if (fmt or {}).get("voice") else []
        return ["script", "direction", "composition", *voice, "render", "checks", "review"]
    return ["script", "composition", "render", "checks", "review"]


def roles_for(kind: str, fmt: dict[str, Any] | None, step: str) -> tuple[str, ...]:
    if step == "composition":
        if kind == "design":
            return ("ui_designer",)
        if is_video(kind, fmt):
            return ("motion_designer",)
        return ("visual_designer", "motion_designer")
    return {
        "script": ("scriptwriter",),
        "direction": ("video_director",),
        "voice": ("voice_producer",),
        "review": ("media_director",),
        "brief": ("ui_designer",),
    }.get(step, ())


def runner_account(server: str) -> str:
    """⟨1.8⟩ the publishing "account" of a runner target: the server it runs on."""
    return f"runner-{server.lower()}"[:41]


def account_key(channel: str, company: str) -> str:
    """The publishing account of a company on a channel (contract §22.7)."""
    return f"{channel}-{company.lower()}"


# ------------------------------------------------------------- validation --
def check_series(company: str, s: dict[str, Any]) -> dict[str, Any]:
    """422 for a series the pipeline could not honour; returns it normalised
    (the RRULE normalised, defaults filled)."""
    bad: dict[str, str] = {}
    kind = s["kind"]
    rule = recurrence.parse(s["schedule"])  # 422 schedule.rrule
    s["schedule"] = rule.rrule()
    fmt = dict(s.get("format") or {})
    if kind == "reel" and fmt.get("aspect") != "9:16":
        bad["format.aspect"] = "a reel is 9:16"
    if kind == "reel" and not fmt.get("duration_s"):
        bad["format.duration_s"] = "a reel has a duration"
    if kind in ("post", "carousel") and fmt.get("duration_s"):
        bad["format.duration_s"] = f"a {kind} is a still"
    if kind == "story" and fmt.get("aspect") != "9:16":
        bad["format.aspect"] = "a story is 9:16"
    if kind in ("post", "carousel") and fmt.get("aspect") not in ("4:5", "1:1"):
        bad["format.aspect"] = "a post or carousel is 4:5 or 1:1"
    if fmt.get("music") == "library":
        # §0.9 #4: no licensed library of the owner's yet
        bad["format.music"] = "no licensed music library exists: none"
    if fmt.get("voice") and not is_video(kind, fmt):
        bad["format.voice"] = "only a video has a voice"
    seen = set()
    # ⟨1.8⟩ a target through a company's own product API (contract §26.1b):
    # `channel: "runner"` with `{server, command}`; its account is the server's.
    s["targets"] = [
        {k: v for k, v in t.items() if v is not None or k == "account"}
        for t in s.get("targets") or []
    ]
    for i, t in enumerate(s["targets"]):
        p = t["placement"]
        if t["channel"] == "runner":
            server, command = str(t.get("server") or ""), str(t.get("command") or "")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}", server):
                bad[f"targets.{i}.server"] = "the name of one of the company's paired servers"
            if not command.strip() or len(command) > 2000:
                bad[f"targets.{i}.command"] = "the server's own publish command (≤ 2000)"
            t["account"] = runner_account(server)
            if p not in PLACEMENTS_OF_KIND[kind]:
                bad[f"targets.{i}.placement"] = f"a {kind} is not published as {p}"
            if (p, t["account"]) in seen:
                bad[f"targets.{i}"] = "twice"
            seen.add((p, t["account"]))
            continue
        for extra in ("server", "command"):
            if t.get(extra) is not None:
                bad[f"targets.{i}.{extra}"] = "only a runner target names a server"
        if PLACEMENT_CHANNEL[p] != t["channel"]:
            bad[f"targets.{i}.placement"] = f"{p} is not on {t['channel']}"
        if p not in PLACEMENTS_OF_KIND[kind]:
            bad[f"targets.{i}.placement"] = f"a {kind} is not published as {p}"
        if t["account"] != account_key(t["channel"], company):
            bad[f"targets.{i}.account"] = (
                f"the company's own account: {account_key(t['channel'], company)}"
            )
        if (p, t["account"]) in seen:
            bad[f"targets.{i}"] = "twice"
        seen.add((p, t["account"]))
    if not s.get("targets"):
        bad["targets"] = "at least one"
    missing = [k for k in CHECK_KEYS if k not in (s.get("checks") or CHECK_KEYS)]
    if missing:
        bad["checks"] = "all seven checks run on every item: " + ", ".join(missing)
    topics = s.get("topics")
    if topics is not None and not (topics.get("pool") or topics.get("rule_fa")):
        bad["topics"] = "a pool of topics or a rule"
    if bad:
        raise ApiError(422, "validation_failed", fields=bad)
    s["format"] = fmt
    s["checks"] = list(CHECK_KEYS)
    s["max_per_day"] = int(s.get("max_per_day") or DEFAULT_MAX_PER_DAY[kind])
    return s


# ---------------------------------------------------------------- series --
SERIES_SQL = """
    SELECT s.*, c.code AS company, d.ref AS decision_ref,
           (SELECT count(*) FROM media.items i WHERE i.series_id = s.id) AS items_total
    FROM media.series s JOIN core.companies c ON c.id = s.company_id
    LEFT JOIN cartable.decisions d ON d.id = s.decision_id
"""


async def owner_zone(tx: Tx) -> str:
    tz = await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1")
    return str(tz or "Asia/Tehran")


async def load_series(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        SERIES_SQL + " WHERE s.ref = :r" + (" FOR UPDATE OF s" if lock else ""),
        r=ref,
        not_found="not_found",
    )


async def series_view(tx: Tx, s: dict[str, Any]) -> dict[str, Any]:
    """The series with what the server computes (§22.7): its next runs in the
    owner's zone (while sealed), today's count, the items it made."""
    tz = await owner_zone(tx)
    zone = ZoneInfo(tz)
    now = datetime.now(UTC)
    next_at: list[datetime] = []
    today = None
    if s["status"] == "sealed":
        next_at = recurrence.occurrences(
            recurrence.parse(s["schedule"]), tz, now, now + timedelta(days=31), limit=5
        )
    if s["status"] in ("sealed", "paused"):
        start = datetime.now(zone).replace(hour=0, minute=0, second=0, microsecond=0)
        row = await tx.first(
            """SELECT count(*) FILTER (WHERE i.created_at >= :d) AS made,
                      count(*) FILTER (WHERE i.state = 'published' AND EXISTS (
                          SELECT 1 FROM media.publish_log l WHERE l.item_id = i.id
                             AND l.action = 'publish' AND l.outcome = 'ok' AND l.at >= :d)) AS published
               FROM media.items i WHERE i.series_id = :s""",
            s=s["id"],
            d=start.astimezone(UTC),
        )
        assert row is not None
        today = {"made": int(row["made"] or 0), "published": int(row["published"] or 0)}
    return {
        **s,
        "proposed_by": {"kind": s["proposed_by_kind"], "code": s["proposed_by_code"]},
        "next_at": next_at,
        "today": today,
    }


async def create_series(
    tx: Tx,
    who: Principal,
    company_id: UUID,
    company: str,
    body: dict[str, Any],
    *,
    status: str,
    work_id: UUID | None = None,
) -> dict[str, Any]:
    s = check_series(company, dict(body))
    digest = series_digest(company, s)
    row = await tx.one(
        """INSERT INTO media.series (company_id, title_fa, kind, targets, schedule, topics, format,
               checks, auto_publish, max_per_day, status, digest, proposed_by_kind, proposed_by_code,
               work_id)
           VALUES (:co, :t, :k, CAST(:tg AS jsonb), :sch, CAST(:tp AS jsonb), CAST(:f AS jsonb), :ch,
                   :ap, :mx, :st, :dg, :pk, :pc, :w)
           RETURNING ref""",
        co=company_id,
        t=s["title_fa"],
        k=s["kind"],
        tg=canonical(s["targets"]),
        sch=s["schedule"],
        tp=canonical(s.get("topics")) if s.get("topics") is not None else None,
        f=canonical(s["format"]),
        ch=s["checks"],
        ap=bool(s.get("auto_publish")),
        mx=s["max_per_day"],
        st=status,
        dg=digest,
        pk=who.kind,
        pc=who.code,
        w=work_id,
    )
    await events.emit(tx, company, "media.series", row["ref"], {"status": status})
    return await load_series(tx, row["ref"])


async def update_series(tx: Tx, s: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    if s["status"] == "retired":
        raise ApiError(409, "validation_failed", f"{s['ref']} is retired")
    if body["company"] != s["company"]:
        raise ApiError(
            422, "validation_failed", fields={"company": "a series stays in its company"}
        )
    if body["kind"] != s["kind"]:
        raise ApiError(
            422, "validation_failed", fields={"kind": "the kind of a series never changes"}
        )
    n = check_series(s["company"], dict(body))
    digest = series_digest(s["company"], n)
    status, note = s["status"], s["status_note_fa"]
    if digest != s["digest"] and s["status"] in ("sealed", "paused"):
        # The seal covered the old digest only (contract §22.2).
        status = "proposed"
        note = "ویرایش شد؛ مُهر قبلی این نسخه را نمیپوشاند و تا مُهر دوباره چیزی خودکار منتشر نمیشود."
    await tx.exec(
        """UPDATE media.series SET title_fa = :t, targets = CAST(:tg AS jsonb), schedule = :sch,
               topics = CAST(:tp AS jsonb), format = CAST(:f AS jsonb), auto_publish = :ap,
               max_per_day = :mx, digest = :dg, status = :st, status_note_fa = :note,
               sealed_at = CASE WHEN :st = 'sealed' THEN sealed_at ELSE NULL END,
               sealed_digest = CASE WHEN :st = 'sealed' THEN sealed_digest ELSE NULL END
           WHERE id = :id""",
        id=s["id"],
        t=n["title_fa"],
        tg=canonical(n["targets"]),
        sch=n["schedule"],
        tp=canonical(n.get("topics")) if n.get("topics") is not None else None,
        f=canonical(n["format"]),
        ap=bool(n.get("auto_publish")),
        mx=n["max_per_day"],
        dg=digest,
        st=status,
        note=note,
    )
    await events.emit(tx, s["company"], "media.series", s["ref"], {"status": status})
    return await load_series(tx, s["ref"])


async def unconfigured_accounts(tx: Tx, bao: Any, targets: list[dict[str, Any]]) -> list[str]:
    from hq_api.domain import egress as G

    out = []
    for key in sorted({t["account"] for t in targets if t.get("channel") != "runner"}):
        row = await tx.first("SELECT key FROM tools.accounts WHERE key = :k", k=key)
        if row is None or not await G.has_secret(bao, key):
            out.append(key)
    return out


async def seal_series(
    tx: Tx, hub: Any, who: Principal, s: dict[str, Any], digest: str, step_up_id: UUID
) -> dict[str, Any]:
    """The owner's seal on exactly this digest; a pending media_series card of
    the series is decided by it (approved), a paused series resumes."""
    if s["status"] == "retired":
        raise ApiError(409, "validation_failed", f"{s['ref']} is retired")
    if digest != s["digest"]:
        raise ApiError(409, "version_conflict", "the series changed since you saw it")
    missing = await unconfigured_accounts(tx, getattr(hub, "bao", None), s["targets"])
    note = (
        f"مُهر شد؛ {'، '.join(missing)} هنوز کلید ندارد و تا ورودش روی آن منتشر نمیشود."
        if missing
        else None
    )
    await tx.exec(
        """UPDATE media.series SET status = 'sealed', sealed_at = now(), sealed_digest = digest,
               sealed_step_up_id = :su, status_note_fa = :note,
               ticked_at = CASE WHEN status = 'sealed' THEN ticked_at ELSE now() END
           WHERE id = :id""",
        id=s["id"],
        su=step_up_id,
        note=note,
    )
    card = await tx.first(
        """SELECT ref FROM cartable.decisions WHERE kind = 'media_series' AND status = 'pending'
             AND company_id = :co AND payload->>'series' = :ref ORDER BY created_at""",
        co=s["company_id"],
        ref=s["ref"],
    )
    if card is not None:
        d = await D.load(tx, card["ref"], lock=True)
        await D.decide(
            tx, who, d, "approved", note=f"مُهر روی digest {digest[:12]}…", step_up_id=step_up_id
        )
        await tx.exec(
            "UPDATE media.series SET decision_id = :d WHERE id = :id", d=d["id"], id=s["id"]
        )
    await events.emit(tx, s["company"], "media.series", s["ref"], {"status": "sealed"})
    return await load_series(tx, s["ref"])


async def set_series_status(
    tx: Tx, s: dict[str, Any], status: str, note: str | None
) -> dict[str, Any]:
    if s["status"] == "retired":
        raise ApiError(409, "validation_failed", f"{s['ref']} is retired")
    await tx.exec(
        "UPDATE media.series SET status = :st, status_note_fa = :n WHERE id = :id",
        id=s["id"],
        st=status,
        n=note,
    )
    await events.emit(tx, s["company"], "media.series", s["ref"], {"status": status})
    return await load_series(tx, s["ref"])


async def propose_series(
    tx: Tx,
    who: Principal,
    company_id: UUID,
    company: str,
    body: dict[str, Any],
    work_id: UUID | None,
) -> dict[str, Any]:
    """series.propose (A1): a `proposed` series and its media_series card."""
    s = await create_series(tx, who, company_id, company, body, status="proposed", work_id=work_id)
    payload = {
        "series": s["ref"],
        "digest": s["digest"],
        "title_fa": s["title_fa"],
        "kind": s["kind"],
        "auto_publish": s["auto_publish"],
        "max_per_day": s["max_per_day"],
        "schedule": s["schedule"],
        "targets": s["targets"],
    }
    din = D.DecisionIn(
        kind="media_series",
        title=f"برنامه‌ی انتشار «{s['title_fa']}»"[:300],
        what=(body.get("what_fa") or "")[:20000]
        or f"{s['kind']} · {s['schedule']} · سقف روزانه {s['max_per_day']} · "
        + ("انتشار خودکار وقتی هر هفت چک قبول باشد" if s["auto_publish"] else "هر آیتم کارت مالک"),
        why=(body.get("why_fa") or "")[:20000],
        work_id=work_id,
        risk="medium" if s["auto_publish"] else "low",
        payload=payload,
    )
    thread = await tx.scalar(
        "SELECT code FROM msg.threads WHERE employee_id = (SELECT id FROM core.employees WHERE code = :c)",
        c=who.code,
    )
    d = await D.propose(
        tx,
        SERVICE,
        company_id=company_id,
        company_code=company,
        body=din,
        thread_code=thread,
    )
    await tx.exec("UPDATE media.series SET decision_id = :d WHERE id = :id", d=d["id"], id=s["id"])
    return {**(await load_series(tx, s["ref"])), "card": d["ref"]}


async def card_declined(tx: Tx, d: dict[str, Any], verdict: str, note: str | None) -> None:
    """A media_series or media_publish card rejected or returned (§22.7)."""
    p = d["payload"] or {}
    if d["kind"] == "media_series" and p.get("series"):
        await tx.exec(
            """UPDATE media.series SET status = 'draft', status_note_fa = :n
               WHERE ref = :r AND status = 'proposed'""",
            r=p["series"],
            n=(f"مالک برگرداند: «{note}»" if verdict == "returned" else "مالک رد کرد.")[:500],
        )
    if d["kind"] == "media_publish" and p.get("item"):
        await tx.exec(
            """UPDATE media.items SET state = 'rejected', publish_at = NULL, state_note_fa = :n
               WHERE ref = :r AND state = 'waiting_owner'""",
            r=p["item"],
            n=(f"مالک برگرداند: «{note}»" if verdict == "returned" else "مالک رد کرد.")[:1000],
        )


# ----------------------------------------------------------------- items --
ITEM_SQL = """
    SELECT i.*, c.code AS company, s.ref AS series_ref, d.ref AS decision_ref,
           cp.format AS composition_format, cp.sha256 AS composition_sha256, cp.n AS composition_n,
           cp.by_kind AS composition_by_kind, cp.by_code AS composition_by_code, cp.report AS composition_report,
           s.format AS series_format, s.targets AS series_targets, s.status AS series_status,
           s.auto_publish AS series_auto_publish, s.digest AS series_digest,
           s.sealed_digest AS series_sealed_digest, s.schedule AS series_schedule,
           s.max_per_day AS series_max_per_day, s.title_fa AS series_title_fa
    FROM media.items i JOIN core.companies c ON c.id = i.company_id
    LEFT JOIN media.series s ON s.id = i.series_id
    LEFT JOIN cartable.decisions d ON d.id = i.decision_id
    LEFT JOIN media.compositions cp ON cp.id = i.composition_id
"""


async def load_item(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        ITEM_SQL + " WHERE i.ref = :r" + (" FOR UPDATE OF i" if lock else ""),
        r=ref,
        not_found="not_found",
    )


def fmt_of(item: dict[str, Any]) -> dict[str, Any]:
    """The format the item is made in: its series', or its kind's default."""
    if item.get("series_format"):
        return dict(item["series_format"])
    base = DEFAULT_FORMAT.get(item["kind"], {})
    return {"captions": True, "music": "none", "overlay": {"cta_fa": None, "mark": True}, **base}


def targets_of(item: dict[str, Any]) -> list[dict[str, Any]]:
    if item.get("series_targets"):
        return list(item["series_targets"])
    if item["kind"] == "design":
        return []
    return [
        {
            "channel": PLACEMENT_CHANNEL[p],
            "account": account_key(PLACEMENT_CHANNEL[p], item["company"]),
            "placement": p,
        }
        for p in PLACEMENTS_OF_KIND[item["kind"]]
        if p not in MANUAL_PLACEMENTS or item["kind"] == "story"
    ]


async def create_item(
    tx: Tx,
    hub: Any,
    who: Principal,
    *,
    company_id: UUID,
    company: str,
    kind: str,
    title_fa: str,
    brief_md: str | None,
    series: dict[str, Any] | None = None,
    topic_fa: str | None = None,
    slot_at: datetime | None = None,
    one_off: bool = True,
) -> dict[str, Any]:
    if series is not None and series["kind"] != kind:
        raise ApiError(
            422, "validation_failed", fields={"kind": f"the series makes {series['kind']}s"}
        )
    first = steps_of(kind, (series or {}).get("format") or DEFAULT_FORMAT.get(kind))[0]
    row = await tx.one(
        """INSERT INTO media.items (company_id, series_id, kind, title_fa, state, one_off, brief_md,
               topic_fa, slot_at, created_by_kind, created_by_code)
           VALUES (:co, :s, :k, :t, :st, :one, :b, :tp, :slot, :bk, :bc) RETURNING ref""",
        co=company_id,
        s=series["id"] if series else None,
        k=kind,
        t=title_fa[:300],
        st=STATE_OF_STEP[first],
        one=one_off,
        b=brief_md,
        tp=topic_fa,
        slot=slot_at,
        bk=who.kind,
        bc=who.code,
    )
    item = await load_item(tx, row["ref"], lock=True)
    await events.emit(tx, company, "media.item", item["ref"], {"state": item["state"]})
    await wake(tx, hub, item, first)
    return await load_item(tx, row["ref"])


async def _pick(tx: Tx, company_id: UUID, roles: tuple[str, ...]) -> dict[str, Any] | None:
    """The least busy active employee of the company's MEDIA department in one of `roles`."""
    if not roles:
        return None
    return await tx.first(
        """SELECT e.id, e.code, e.role FROM core.employees e
           JOIN core.departments d ON d.id = e.department_id
           WHERE e.company_id = :co AND d.code = 'MEDIA' AND e.role = ANY(:roles)
             AND e.status = 'active' AND e.kind <> 'system'
           ORDER BY (SELECT count(*) FROM work.work w WHERE w.assignee_id = e.id
                       AND w.status IN ('queued', 'in_progress', 'waiting')),
                    array_position(CAST(:roles AS text[]), e.role), e.code
           LIMIT 1""",
        co=company_id,
        roles=list(roles),
    )


async def _note(tx: Tx, item: dict[str, Any], state: str, note: str | None) -> None:
    await tx.exec(
        "UPDATE media.items SET state = :st, state_note_fa = :n WHERE id = :id",
        id=item["id"],
        st=state,
        n=note[:1000] if note else None,
    )
    await events.emit(tx, item["company"], "media.item", item["ref"], {"state": state})


async def wake(
    tx: Tx, hub: Any, item: dict[str, Any], step: str, *, note: str | None = None
) -> None:
    """Move the item into `step`: a work item for the step's role, a render
    job, the checks, or the review."""
    fmt = fmt_of(item)
    if step == "render":
        await queue_render(tx, hub, item, purpose="final", by=SERVICE.code)
        return
    if step == "checks":
        await run_checks(tx, hub, item)
        return
    if step == "voice" and not getattr(hub.settings, "tts", False):
        # The voice is an opt-in profile (prompt 12 §4): without it the item
        # goes on silent, with captions; the review and the owner see why.
        await tx.exec(
            """UPDATE media.items SET narration = CAST(:n AS jsonb) WHERE id = :id""",
            id=item["id"],
            n=canonical({"state": "off"}),
        )
        await _note(
            tx,
            item,
            "voicing",
            "صدای هاب خاموش است (پروفایل tts)؛ آیتم بی‌صدا و با زیرنویس ساخته میشود.",
        )
        await advance(tx, hub, await load_item(tx, item["ref"], lock=True), "voice")
        return
    roles = roles_for(item["kind"], fmt, step)
    emp = await _pick(tx, item["company_id"], roles)
    state = STATE_OF_STEP[step]
    if emp is None:
        await _note(
            tx,
            item,
            "held",
            f"گام «{STEP_FA.get(step, step)}» نقش {' یا '.join(roles)} را میخواهد که هنوز در "
            "دپارتمان رسانه‌ی این شرکت استخدام نشده.",
        )
        await _tell_director(tx, hub, item, step, roles)
        return
    lib = getattr(hub, "charters", None)
    charter = lib.get(emp["role"]) if lib is not None else None
    tokens = (charter.limits.tokens_per_run * 2) if charter is not None else None
    w = await W.create(
        tx,
        SERVICE,
        company_id=item["company_id"],
        company_code=item["company"],
        title=f"{item['ref']} · {STEP_FA.get(step, step)}: {item['title_fa']}"[:300],
        brief=await brief(tx, hub, item, step, note),
        kind="one_off",
        priority="P3",
        assignee_code=emp["code"],
        budget=W.BudgetIn(tokens=tokens) if tokens else None,
    )
    await tx.exec(
        "UPDATE work.work SET run_meta = CAST(:m AS jsonb) WHERE id = :id",
        id=w["id"],
        m=canonical(
            {
                "task_class": TASK_CLASS.get(step, "media_script")
                if item["kind"] != "design" or step == "review"
                else "ui_design",
                "media_item": item["ref"],
                "media_step": step,
            }
        ),
    )
    await tx.exec(
        """UPDATE media.items SET state = :st, step_work_id = :w, state_note_fa = :n,
               steps = steps || CAST(:s AS jsonb)
           WHERE id = :id""",
        id=item["id"],
        st=state,
        w=w["id"],
        n=None,
        s=canonical(
            [{"step": step, "work": w["ref"], "employee": emp["code"], "at": datetime.now(UTC)}]
        ),
    )
    await events.emit(
        tx, item["company"], "media.item", item["ref"], {"state": state, "step": step}
    )


async def _tell_director(
    tx: Tx, hub: Any, item: dict[str, Any], step: str, roles: tuple[str, ...]
) -> None:
    """Once per item and step: the media director hears that the step has nobody."""
    key = f"missing:{step}"
    if any(s.get("step") == key for s in item.get("steps") or []):
        return
    director = await _pick(tx, item["company_id"], ("media_director",))
    if director is None or step == "review":
        return
    w = await W.create(
        tx,
        SERVICE,
        company_id=item["company_id"],
        company_code=item["company"],
        title=f"{item['ref']}: نقش {roles[0]} لازم است"[:300],
        brief=(
            f"Media item {item['ref']} («{item['title_fa']}») is held at the step "
            f"«{STEP_FA.get(step, step)}»: no active employee of the MEDIA department holds the role "
            f"{' or '.join(roles)}. Propose the hire (propose kind hire, while hiring is open), or "
            "record the team gap in your report while it is closed. Nothing else is needed: the item "
            "goes on by itself once the role exists and you wake it with a new item of the series."
        ),
        kind="one_off",
        priority="P3",
        assignee_code=director["code"],
    )
    await tx.exec(
        "UPDATE media.items SET steps = steps || CAST(:s AS jsonb) WHERE id = :id",
        id=item["id"],
        s=canonical(
            [{"step": key, "work": w["ref"], "employee": director["code"], "at": datetime.now(UTC)}]
        ),
    )


async def _close_step_work(tx: Tx, item: dict[str, Any], why: str) -> None:
    if item.get("step_work_id") is None:
        return
    w = await tx.first(
        "SELECT id, ref, status, company_id FROM work.work WHERE id = :id FOR UPDATE",
        id=item["step_work_id"],
    )
    if w is not None and w["status"] in ("queued", "in_progress", "waiting"):
        # Done with its evidence: the item's own record holds the step (HQE01).
        await tx.exec(
            """UPDATE work.work SET status = 'done', close_reason = :r, closed_at = now(),
                   evidence = evidence || CAST(:e AS jsonb)
               WHERE id = :id""",
            id=w["id"],
            r=why[:500],
            e=canonical([{"kind": "media_item", "ref": item["ref"], "note": why[:300]}]),
        )


async def advance(tx: Tx, hub: Any, item: dict[str, Any], done: str) -> None:
    """The step `done` is complete: the next one starts."""
    steps = steps_of(item["kind"], fmt_of(item))
    if done not in steps:
        return
    i = steps.index(done)
    if i + 1 >= len(steps):
        return
    nxt = steps[i + 1]
    await wake(tx, hub, await load_item(tx, item["ref"], lock=True), nxt)


def current_step(item: dict[str, Any]) -> str | None:
    by_state = {v: k for k, v in STATE_OF_STEP.items() if k != "brief"}
    if item["kind"] == "design" and item["state"] == "composing" and not item.get("script"):
        return "brief"
    return by_state.get(item["state"])


# ------------------------------------------------------------ the briefs --
async def brief(tx: Tx, hub: Any, item: dict[str, Any], step: str, note: str | None) -> str:
    """What the step's work item tells its role (English; data in Persian)."""
    fmt = fmt_of(item)
    targets = targets_of(item)
    head = [
        f"Media item {item['ref']} «{item['title_fa']}» ({item['kind']}"
        + (
            f", series {item['series_ref']} «{item.get('series_title_fa') or ''}»"
            if item.get("series_ref")
            else ", a one-off"
        )
        + ").",
        "Format: " + canonical(fmt),
        "Placements: " + ", ".join(t["placement"] for t in targets)
        if targets
        else "Placements: none (a design).",
    ]
    if item.get("topic_fa"):
        head.append(f"Topic: «{item['topic_fa']}»")
    if item.get("brief_md"):
        head.append("Brief:\n" + str(item["brief_md"])[:5000])
    if note:
        head.append("Review notes to act on:\n" + note[:5000])
    script = item.get("script") or {}
    direction = item.get("direction") or {}
    if step == "script":
        head.append(
            'Write the script with media.item {"ref": "{ref}", "step": "script", "script": {"text_fa": …, '
            '"sources": [{"kind", "ref" or "url", "note"}]}}. Parts: «قلاب», «بدنه», «جمع‌بندی و دعوت», '
            "«هشدار ریسک» (every trading topic), «کپشن». Every figure needs a source whose note names "
            "that figure; illustrative numbers say «فرض کنید». No promise of profit.".replace(
                "{ref}", item["ref"]
            )
        )
    elif step == "direction":
        head.append("Script (fixed):\n" + str(script.get("text_fa") or "")[:12000])
        head.append("Sources:\n" + canonical(script.get("sources") or [])[:6000])
        head.append(
            'Store the shot list with media.item {"ref": "{ref}", "step": "direction", "direction": '
            '{"shots": [{"n", "duration_s", "visual_fa", "text_on_screen_fa", "voice_fa"}]}}; the '
            "durations add up to {dur} s; one shot carries the risk warning on trading content.".replace(
                "{ref}", item["ref"]
            ).replace("{dur}", str(fmt.get("duration_s")))
        )
    elif step in ("composition", "brief"):
        if script.get("text_fa"):
            head.append(
                ("Design brief" if item["kind"] == "design" else "Script")
                + ":\n"
                + str(script["text_fa"])[:12000]
            )
        if direction.get("shots"):
            head.append("Direction (fixed):\n" + canonical(direction["shots"])[:15000])
        head.append("Brand: " + canonical(await brand_of(tx, item["company_id"]))[:4000])
        if step == "brief":
            head.append(
                'Write the design brief with media.item {"ref": "{ref}", "step": "brief", "brief_md": …}.'.replace(
                    "{ref}", item["ref"]
                )
            )
        else:
            size = SIZE.get(str(fmt.get("aspect") or "9:16"), (1080, 1920))
            head.append(
                "The composition schema (refused otherwise): one HTML document with "
                '<html lang="fa" dir="rtl">, CSS animations, SVG, the Web Animations API, inline scripts '
                'and only <script src="/lib/anime.min.js"> or <script src="/lib/lottie.min.js">; images '
                "only as /assets/<file id> of this company's files or creatives; IRANYekanX the only font "
                "(declared by the render page; no @font-face); no network of any kind; or one Lottie JSON "
                "without expressions. Motion follows the timeline (a virtual clock drives it)."
            )
            if item["kind"] == "design":
                head.append(
                    "Pages are rendered at phone (390x844 @2x) and desktop (1440x900) width, full page. "
                    'Store it with media.item {"ref": "{ref}", "step": "composition", "composition": '
                    '{"format": "html", "source": …}}, then media.render.'.replace(
                        "{ref}", item["ref"]
                    )
                )
            elif is_video(item["kind"], fmt):
                head.append(
                    f"Canvas {size[0]}x{size[1]} at 30 fps for {fmt.get('duration_s')} s; the hub burns in the "
                    "captions and places the company's mark itself; keep text inside the safe zone "
                    + canonical(SAFE.get(targets[0]["placement"]) if targets else None)
                    + '. Store it with media.item {"ref": "{ref}", "step": "composition", "composition": '
                    '{"format": "html"|"lottie", "source": …}}; media.render gives you a preview.'.replace(
                        "{ref}", item["ref"]
                    )
                )
            else:
                head.append(
                    f"A still {size[0]}x{size[1]}. Either frames as creatives (substitute.call seat creative, "
                    "the item's placement, the Persian text in `overlay`) delivered with their CR-… refs (one "
                    "per line), or one composition (media.item step composition) rendered to stills: a "
                    'carousel puts data-slides="N" on <body> and shows slide k during [k-1, k) seconds; '
                    "a single still is the frame at 3 seconds."
                )
    elif step == "voice":
        head.append("Shots:\n" + canonical(direction.get("shots") or [])[:12000])
        head.append(
            'Make the narration with media.voice {"ref": "{ref}", "text_fa": …}; one line per shot, '
            "spelled for speech; the warning spoken in full.".replace("{ref}", item["ref"])
        )
    elif step == "review":
        head.append("Script:\n" + str(script.get("text_fa") or "")[:8000])
        if direction.get("shots"):
            head.append("Direction:\n" + canonical(direction["shots"])[:8000])
        head.append("Render outputs: " + canonical(item.get("outputs") or [])[:3000])
        head.append("Pages: " + canonical(item.get("pages") or [])[:2000])
        head.append("Checks by code: " + canonical(item.get("checks") or [])[:4000])
        head.append(
            'Review it (files.read on the render) with media.review {"ref": "{ref}", "verdict": '
            '"pass"|"changes"|"reject", "note_md": …}; on `changes` name the role that owns each fix '
            "(scriptwriter, video_director, motion_designer, voice_producer, visual_designer, "
            "ui_designer): the item goes back to the earliest of them.".replace(
                "{ref}", item["ref"]
            )
        )
    return "\n\n".join(head)[:49000]


async def brand_of(tx: Tx, company_id: UUID) -> dict[str, Any] | None:
    from hq_api.domain import brands

    b = await brands.active(tx, company_id)
    if b is None:
        return None
    c = brands.content(b)
    raw = b.get("palette")
    if isinstance(raw, str):
        raw = json.loads(raw or "[]")
    palette = [str(p["hex"]) for p in raw or [] if isinstance(p, dict) and p.get("hex")]
    return {
        "ink": c["ink"],
        "accent": c.get("accent"),
        "accent_night": c.get("accent_night"),
        "accent_day": c.get("accent_day"),
        "palette": palette,
        "mark": c.get("mark"),
    }


def brand_colours(brand: dict[str, Any] | None) -> list[str]:
    if not brand:
        return []
    return [
        c
        for c in (
            brand.get("ink"),
            brand.get("accent"),
            brand.get("accent_night"),
            brand.get("accent_day"),
            *brand.get("palette", []),
        )
        if c
    ]


# ------------------------------------------------- the agents' tools --
def _require_role(who: Principal, roles: tuple[str, ...], step: str) -> None:
    if (who.charter or who.role) not in roles:
        raise ApiError(
            403, "policy_denied", f"the step «{step}» is written by {' or '.join(roles)}"
        )


async def write_step(tx: Tx, hub: Any, who: Principal, body: dict[str, Any]) -> dict[str, Any]:
    """media.item (A1): the current step of an item, for its role."""
    item = await load_item(tx, body["ref"], lock=True)
    if item["company_id"] != who.company_id:
        raise ApiError(403, "policy_denied", "an item of another company")
    step = body["step"]
    fmt = fmt_of(item)
    cur = current_step(item)
    if cur != step:
        raise ApiError(
            409, "validation_failed", f"{item['ref']} is at «{cur or item['state']}», not «{step}»"
        )
    _require_role(who, roles_for(item["kind"], fmt, step), step)
    actor = {"kind": "agent", "code": who.code}
    hint = None
    if step == "script":
        sc = body.get("script") or {}
        if not str(sc.get("text_fa") or "").strip():
            raise ApiError(422, "validation_failed", fields={"script.text_fa": "required"})
        await tx.exec(
            "UPDATE media.items SET script = CAST(:s AS jsonb) WHERE id = :id",
            id=item["id"],
            s=canonical(
                {"text_fa": sc["text_fa"], "sources": sc.get("sources") or [], "by": actor}
            ),
        )
    elif step == "brief":
        text = str(body.get("brief_md") or "").strip()
        if not text:
            raise ApiError(422, "validation_failed", fields={"brief_md": "required"})
        await tx.exec(
            "UPDATE media.items SET script = CAST(:s AS jsonb) WHERE id = :id",
            id=item["id"],
            s=canonical({"text_fa": text, "sources": [], "by": actor, "kind": "brief"}),
        )
    elif step == "direction":
        shots = (body.get("direction") or {}).get("shots") or []
        if not shots:
            raise ApiError(
                422, "validation_failed", fields={"direction.shots": "at least one shot"}
            )
        total = sum(float(s.get("duration_s") or 0) for s in shots)
        want = fmt.get("duration_s")
        if want and abs(total - float(want)) > 1.0:
            raise ApiError(
                422,
                "validation_failed",
                fields={"direction.shots": f"they last {total:g} s, the format {want} s"},
            )
        await tx.exec(
            "UPDATE media.items SET direction = CAST(:d AS jsonb) WHERE id = :id",
            id=item["id"],
            d=canonical({"shots": shots, "by": actor}),
        )
    elif step == "composition":
        comp = body.get("composition") or {}
        rep = await check_composition(
            tx, item, str(comp.get("format") or ""), str(comp.get("source") or "")
        )
        n = int(
            await tx.scalar(
                "SELECT COALESCE(max(n), 0) + 1 FROM media.compositions WHERE item_id = :i",
                i=item["id"],
            )
        )
        cid = await tx.scalar(
            """INSERT INTO media.compositions (company_id, item_id, n, format, sha256, source, report,
                   by_kind, by_code)
               VALUES (:co, :i, :n, :f, :sha, :src, CAST(:rep AS jsonb), 'agent', :by) RETURNING id""",
            co=item["company_id"],
            i=item["id"],
            n=n,
            f=comp["format"],
            sha=rep.sha256,
            src=comp["source"],
            rep=canonical(rep.as_dict()),
            by=who.code,
        )
        await tx.exec(
            "UPDATE media.items SET composition_id = :c, assets = :a WHERE id = :id",
            id=item["id"],
            c=cid,
            a=[UUID(a) for a in rep.assets],
        )
        hint = f"composition {rep.sha256} (version {n}) stored"
        if rep.warnings:
            hint += "; warnings: " + ", ".join(w["rule"] for w in rep.warnings)
    else:
        raise ApiError(
            422, "validation_failed", fields={"step": "script, direction, composition or brief"}
        )
    await _close_step_work(tx, item, f"{STEP_FA.get(step, step)} ثبت شد")
    await events.emit(
        tx, item["company"], "media.item", item["ref"], {"step": step, "stored": True}
    )
    await advance(tx, hub, await load_item(tx, item["ref"], lock=True), step)
    out = await load_item(tx, item["ref"])
    return {
        "ref": out["ref"],
        "state": out["state"],
        "step": step,
        "hint": hint,
        "composition": {"sha256": out["composition_sha256"], "n": out["composition_n"]}
        if step == "composition"
        else None,
    }


async def check_composition(tx: Tx, item: dict[str, Any], fmt: str, source: str) -> C.Report:
    rep = C.check(fmt, source, None)
    if rep.assets:
        own = {
            str(r["id"])
            for r in await tx.all(
                "SELECT id FROM files.files WHERE id = ANY(:ids) AND company_id = :co",
                ids=[UUID(a) for a in rep.assets],
                co=item["company_id"],
            )
        }
        for a in rep.assets:
            if a not in own:
                rep.refuse("asset_not_allowed", f"/assets/{a}: not a file of this company")
    if rep.ok:
        # What a viewer reads must hold no secret: the source is code and is not
        # rewritten, so a key or a customer's data in its text is refused.
        from hq_api.domain.studio_checks import visible_text
        from hq_common.redact import scrub

        shown = visible_text(source, fmt)
        if scrub(shown, secrets_only=True) != shown or re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", shown):
            rep.refuse("secret", "the visible text holds a credential or an e-mail address")
    if not rep.ok:
        raise ApiError(
            422,
            "validation_failed",
            "the composition breaks the schema: "
            + "; ".join(f"{p['rule']}: {p['detail']}" for p in rep.problems[:8]),
            fields={"composition": ", ".join(sorted({p["rule"] for p in rep.problems}))},
        )
    return rep


async def queue_render(
    tx: Tx, hub: Any, item: dict[str, Any], *, purpose: str, by: str
) -> dict[str, Any] | None:
    """A render job for the item's current composition (one open job per item;
    a final render asked while a preview is still queued replaces it)."""
    if item.get("composition_id") is None:
        if purpose == "final" and not is_video(item["kind"], fmt_of(item)) and item.get("pages"):
            # still frames delivered as creatives: nothing to render
            await advance(tx, hub, item, "render")
            return None
        raise ApiError(409, "validation_failed", f"{item['ref']} has no composition yet")
    open_job = await tx.first(
        """SELECT id, state, purpose FROM media.render_jobs
           WHERE item_id = :i AND state IN ('queued', 'claimed') FOR UPDATE""",
        i=item["id"],
    )
    if open_job is not None:
        if purpose == "preview":
            raise ApiError(409, "validation_failed", "a render of this item is already queued")
        if open_job["state"] == "queued":
            await tx.exec(
                "UPDATE media.render_jobs SET state = 'cancelled', updated_at = now() WHERE id = :id",
                id=open_job["id"],
            )
        else:
            await tx.exec(
                """UPDATE media.items SET render_meta = COALESCE(render_meta, '{}'::jsonb) || '{"final_wanted": true}'
                   WHERE id = :id""",
                id=item["id"],
            )
            await _note(
                tx, item, "rendering", "render پیش‌نمایش در جریان است؛ render نهایی بعد از آن"
            )
            return None
    spec = await render_spec(tx, item)
    job = await tx.one(
        """INSERT INTO media.render_jobs (company_id, item_id, composition_id, purpose, spec, requested_by)
           VALUES (:co, :i, :c, :p, CAST(:s AS jsonb), :by) RETURNING id""",
        co=item["company_id"],
        i=item["id"],
        c=item["composition_id"],
        p=purpose,
        s=canonical(spec),
        by=by,
    )
    if purpose == "final":
        off = not getattr(getattr(hub, "settings", None), "media", False)
        await _note(
            tx,
            item,
            "rendering",
            "render worker خاموش است (پروفایل media)؛ آیتم در صف render میماند تا روشن شود."
            if off
            else None,
        )
    await events.emit(tx, item["company"], "media.item", item["ref"], {"render": purpose})
    return {"job": job["id"], "purpose": purpose}


async def render_spec(tx: Tx, item: dict[str, Any]) -> dict[str, Any]:
    fmt = fmt_of(item)
    targets = targets_of(item)
    video = is_video(item["kind"], fmt)
    aspect = str(fmt.get("aspect") or "9:16")
    w, h = SIZE.get(aspect, (1080, 1920))
    outputs: list[dict[str, Any]] = []
    placements = [t["placement"] for t in targets]
    if item["kind"] == "design":
        outputs = [
            {
                "name": p["name"],
                "placement": "design",
                "width": p["width"],
                "height": p["height"],
                "video": False,
                "format": "png",
                "full_page": True,
                "scale": p["scale"],
                "max_bytes": 20 * MB,
                "at_s": 0,
            }
            for p in DESIGN_PAGES
        ]
    elif video:
        caps = [LIMITS[p]["video"] for p in placements if LIMITS[p]["video"]]
        outputs = [
            {
                "name": "main",
                "placement": placements[0] if placements else "telegram_post",
                "width": w,
                "height": h,
                "video": True,
                "fps": 30,
                "max_duration_s": min((c[1] for c in caps), default=90),
                "max_bytes": min((c[2] for c in caps), default=50 * MB),
            }
        ]
    else:
        slides = 1
        if item["kind"] == "carousel":
            src = await tx.scalar(
                "SELECT source FROM media.compositions WHERE id = :c", c=item["composition_id"]
            )
            m = re.search(r'data-slides\s*=\s*["\']?(\d{1,2})', str(src or ""))
            slides = max(1, min(10, int(m.group(1)))) if m else 1
        imax = min((LIMITS[p]["image"] for p in placements if LIMITS[p]["image"]), default=8 * MB)
        outputs = [
            {
                "name": f"slide{k}" if item["kind"] == "carousel" else "main",
                "placement": placements[0] if placements else "telegram_post",
                "width": w,
                "height": h,
                "video": False,
                "format": "jpeg",
                "max_bytes": imax,
                "at_s": (k - 0.5) if item["kind"] == "carousel" else STILL_AT_S,
            }
            for k in range(1, slides + 1)
        ]
    files = await tx.all(
        "SELECT id, name, mime, sha256, size FROM files.files WHERE id = ANY(:ids) AND company_id = :co",
        ids=list(item.get("assets") or []),
        co=item["company_id"],
    )
    voice = None
    if item.get("voice_file_id"):
        v = await tx.first(
            "SELECT id, mime, sha256, duration_s FROM files.files WHERE id = :id",
            id=item["voice_file_id"],
        )
        if v is not None:
            voice = {
                "id": str(v["id"]),
                "mime": v["mime"],
                "sha256": v["sha256"],
                "duration_s": float(v["duration_s"]) if v["duration_s"] is not None else None,
            }
    shots = (item.get("direction") or {}).get("shots") or []
    duration = sum(float(s.get("duration_s") or 0) for s in shots) or (
        float(fmt["duration_s"]) if fmt.get("duration_s") else None
    )
    brand = await brand_of(tx, item["company_id"])
    placement = placements[0] if placements else "instagram_reel"
    top, right, bottom, left = SAFE.get(placement, (0.05, 0.05, 0.05, 0.05))
    return {
        "kind": item["kind"],
        "outputs": outputs,
        "duration_s": duration if video else None,
        "fps": 30,
        "assets": [
            {
                "id": str(f["id"]),
                "name": f["name"],
                "mime": f["mime"],
                "sha256": f["sha256"],
                "size": int(f["size"]),
            }
            for f in files
        ],
        "voice": voice,
        "music": None,
        "captions": captions(shots, voice["duration_s"] if voice else None)
        if (video and fmt.get("captions", True))
        else [],
        "overlay": {
            "mark": bool((fmt.get("overlay") or {}).get("mark", True)) and item["kind"] != "design",
            "cta_fa": (fmt.get("overlay") or {}).get("cta_fa"),
        },
        "brand": {
            "ink": (brand or {}).get("ink"),
            "accent": (brand or {}).get("accent"),
            "palette": brand_colours(brand),
            "mark": (brand or {}).get("mark"),
        },
        "safe_zone": {"top": top, "right": right, "bottom": bottom, "left": left},
        "limits": {"timeout_s": RENDER_TIMEOUT_S},
    }


def captions(
    shots: list[dict[str, Any]], voice_s: float | None, max_chars: int = 60
) -> list[dict[str, Any]]:
    """The burned-in Persian captions, from the shots' voice lines: timed by
    the shots, or spread over the narration's real length by the share of
    characters (the narration is one continuous voice) when it exists."""
    lines: list[tuple[float, float, str]] = []
    t = 0.0
    for s in shots:
        d = float(s.get("duration_s") or 0)
        text = str(s.get("voice_fa") or "").strip()
        if text:
            lines.append((t, t + d, text))
        t += d
    if not lines:
        return []
    if voice_s:
        total = sum(len(x[2]) for x in lines) or 1
        pos = 0.0
        spread = []
        for _, _, text in lines:
            span = voice_s * len(text) / total
            spread.append((pos, pos + span, text))
            pos += span
        lines = spread
    out: list[dict[str, Any]] = []
    for start, end, text in lines:
        chunks = _chunks(text, max_chars)
        total = sum(len(c) for c in chunks) or 1
        at = start
        for c in chunks:
            span = (end - start) * len(c) / total
            out.append({"start_s": round(at, 2), "end_s": round(at + span, 2), "text_fa": c})
            at += span
    return out


def _chunks(text: str, n: int) -> list[str]:
    words, out, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > n:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return out


async def request_render(tx: Tx, hub: Any, who: Principal, ref: str) -> dict[str, Any]:
    """media.render (A2): a preview of the current composition, for its composer."""
    item = await load_item(tx, ref, lock=True)
    if item["company_id"] != who.company_id:
        raise ApiError(403, "policy_denied", "an item of another company")
    _require_role(who, roles_for(item["kind"], fmt_of(item), "composition"), "render")
    if item["state"] in ("published", "rejected", "failed", "scheduled", "waiting_owner"):
        raise ApiError(409, "validation_failed", f"{ref} is {item['state']}")
    if not getattr(hub.settings, "media", False):
        raise ApiError(
            503,
            "channel_not_configured",
            "the render worker is off (profile media): no preview now",
        )
    out = await queue_render(tx, hub, item, purpose="preview", by=who.code)
    return {
        "ref": ref,
        "queued": bool(out),
        "purpose": "preview",
        "hint": "the render arrives as a file on the item (files.read on it); nothing advances",
    }


async def request_voice(tx: Tx, hub: Any, who: Principal, body: dict[str, Any]) -> dict[str, Any]:
    """media.voice (A2, the voice producer): the item's narration, queued in
    the voice registry with its active voice (or the one the call or the
    series' format names; "default" is the active one). The registry refuses
    a non-commercial voice the owner did not choose (409 licence_not_chosen)
    and an uninstalled one (409 not_ready). With the `tts` profile off the
    item goes on silent, with captions."""
    from hq_api import speech
    from hq_api.domain import voices as V

    item = await load_item(tx, body["ref"], lock=True)
    if item["company_id"] != who.company_id:
        raise ApiError(403, "policy_denied", "an item of another company")
    _require_role(who, ("voice_producer",), "voice")
    if item["state"] != "voicing":
        raise ApiError(409, "validation_failed", f"{item['ref']} is {item['state']}, not voicing")
    text = str(body.get("text_fa") or "").strip()
    if not text:
        raise ApiError(422, "validation_failed", fields={"text_fa": "required"})
    fmt = fmt_of(item)
    named = body.get("voice_id") or ((fmt.get("voice") or {}).get("voice_id"))
    voice_id = None if named in (None, "default") else str(named)
    spoken = speech.fa_speech_script(text)
    narration: dict[str, Any] = {
        "text_fa": text,
        "spoken": spoken,
        "by": who.code,
        "at": datetime.now(UTC),
    }
    if not getattr(hub.settings, "tts", False):
        note = "صدای هاب خاموش است (پروفایل tts)؛ آیتم بی‌صدا و با زیرنویس ساخته میشود."
        await tx.exec(
            "UPDATE media.items SET narration = CAST(:n AS jsonb), state_note_fa = :note WHERE id = :id",
            id=item["id"],
            n=canonical({**narration, "voice_id": voice_id, "state": "off"}),
            note=note,
        )
        await _close_step_work(tx, item, "صدا خاموش است؛ بی‌صدا ادامه میدهد")
        await advance(tx, hub, await load_item(tx, item["ref"], lock=True), "voice")
        return {"job": None, "item": item["ref"], "state": "off", "voice": None,
                "spoken_chars": len(spoken), "note_fa": note}  # fmt: skip
    out = await V.narrate(
        tx, who, company_id=item["company_id"], ref=item["ref"], text_fa=text, voice_id=voice_id
    )
    voice = out["voice"]
    await tx.exec(
        "UPDATE media.items SET narration = CAST(:n AS jsonb), state_note_fa = NULL WHERE id = :id",
        id=item["id"],
        n=canonical(
            {
                **narration,
                "voice_id": voice["id"],
                "licence_commercial": voice["licence_commercial"],
                "job": out["job"],
                "state": "pending",
            }
        ),
    )
    await _close_step_work(tx, item, "روایت در صف صدا")
    return {**out, "note_fa": None}


async def review(tx: Tx, hub: Any, who: Principal, body: dict[str, Any]) -> dict[str, Any]:
    """media.review (A2, the media director only): the `qc` check."""
    item = await load_item(tx, body["ref"], lock=True)
    if item["company_id"] != who.company_id:
        raise ApiError(403, "policy_denied", "an item of another company")
    _require_role(who, ("media_director",), "review")
    if item["state"] != "review":
        raise ApiError(409, "validation_failed", f"{item['ref']} is {item['state']}, not in review")
    verdict = body["verdict"]
    note = str(body.get("note_md") or "")
    qc = {
        "by": {"kind": "agent", "code": who.code},
        "verdict": verdict,
        "note_md": note,
        "at": datetime.now(UTC),
    }
    checks = [c for c in item.get("checks") or [] if c.get("key") != "qc"]
    checks.append(
        {
            "key": "qc",
            "result": "pass" if verdict == "pass" else "fail",
            "note_fa": None if verdict == "pass" else note[:300],
        }
    )
    await tx.exec(
        "UPDATE media.items SET qc = CAST(:q AS jsonb), checks = CAST(:c AS jsonb) WHERE id = :id",
        id=item["id"],
        q=canonical(qc),
        c=canonical(checks),
    )
    await _close_step_work(tx, item, f"بازبینی: {verdict}")
    item = await load_item(tx, item["ref"], lock=True)
    if verdict == "reject":
        await _note(tx, item, "rejected", f"مدیر رسانه رد کرد: {note[:300]}")
    elif verdict == "changes":
        steps = steps_of(item["kind"], fmt_of(item))
        named = [STEP_OF_ROLE[r] for r in ROLE_IN_NOTE.findall(note) if STEP_OF_ROLE[r] in steps]
        back = (
            min(named, key=steps.index)
            if named
            else ("composition" if "composition" in steps else steps[0])
        )
        await wake(tx, hub, item, back, note=note)
    elif item["kind"] == "design":
        await _note(
            tx,
            item,
            "review",
            "بازبینی قبول شد؛ طراحی به‌صورت خروجی برای مدیر فنی میماند و منتشر نمیشود.",
        )
    else:
        from hq_api.domain import studio_publish as P

        await P.after_review(tx, hub, item)
    out = await load_item(tx, item["ref"])
    return {"ref": out["ref"], "state": out["state"], "verdict": verdict}


# ----------------------------------------------------------- deliveries --
CR_REF = re.compile(r"\bCR-[0-9]{4,}\b")


async def on_delivered(tx: Tx, hub: Any, w: dict[str, Any], dl: dict[str, Any], body: str) -> None:
    """A step's work item delivered: the visual designer's frames (creatives by
    their CR refs) become the still's pages; the UI designer's design
    deliverable is recorded on its item."""
    item = await tx.first(ITEM_SQL + " WHERE i.step_work_id = :w FOR UPDATE OF i", w=w["id"])
    if item is None:
        return
    if item["kind"] == "design":
        await tx.exec(
            "UPDATE media.items SET deliverable_ref = :d WHERE id = :id", id=item["id"], d=dl["ref"]
        )
        return
    if item["state"] != "composing" or is_video(item["kind"], fmt_of(item)):
        return
    refs = list(dict.fromkeys(CR_REF.findall(body)))[:10]
    if not refs:
        return
    rows = await tx.all(
        """SELECT ref, composed_file_id FROM substitutes.creatives
           WHERE company_id = :co AND ref = ANY(:refs) AND composed_file_id IS NOT NULL
             AND state IN ('review', 'accepted')""",
        co=item["company_id"],
        refs=refs,
    )
    by_ref = {r["ref"]: r["composed_file_id"] for r in rows}
    files = [by_ref[r] for r in refs if r in by_ref]
    if not files:
        return
    meta = await tx.all(
        "SELECT id, width, height, size, mime FROM files.files WHERE id = ANY(:ids)", ids=files
    )
    m = {r["id"]: r for r in meta}
    pages = [
        {
            "file_id": str(f),
            "width": m[f]["width"],
            "height": m[f]["height"],
            "bytes": int(m[f]["size"]),
            "mime": m[f]["mime"],
            "creative": r,
        }
        for r, f in zip([r for r in refs if r in by_ref], files, strict=True)
    ]
    outputs = [
        {
            "name": f"slide{k}" if len(pages) > 1 else "main",
            "kind": "image",
            "placement": t["placement"],
            **pg,
        }
        for t in targets_of(item)
        for k, pg in enumerate(pages, 1)
    ]
    await tx.exec(
        """UPDATE media.items SET pages = CAST(:p AS jsonb), outputs = CAST(:o AS jsonb),
               render_file_id = :r, assets = :a, render_meta = CAST(:rm AS jsonb)
           WHERE id = :id""",
        id=item["id"],
        p=canonical(pages),
        o=canonical(outputs),
        r=files[0],
        a=files,
        rm=canonical({"source": "creatives", "creatives": list(by_ref), "mark": True}),
    )
    await advance(tx, hub, await load_item(tx, item["ref"], lock=True), "render")


# ---------------------------------------------- the render one-shot queue --
async def claim_render(tx: Tx, hub: Any) -> dict[str, Any] | None:
    """The oldest queued render job; None while the holding is locked, or for
    a job whose company is locked (it waits)."""
    if await gate.holding_lock(tx) is not None:
        return None
    rows = await tx.all(
        """SELECT j.id, j.item_id, j.company_id, j.attempts, j.purpose, j.spec, j.state
           FROM media.render_jobs j
           WHERE (j.state = 'queued' OR (j.state = 'claimed' AND j.claimed_at < now() - make_interval(mins => :m)))
           ORDER BY j.created_at LIMIT 10 FOR UPDATE SKIP LOCKED""",
        m=RENDER_RECLAIM_MIN,
    )
    for j in rows:
        if await gate.automation_lock(tx, j["company_id"]) is not None:
            continue
        if int(j["attempts"]) >= RENDER_MAX_ATTEMPTS:
            await _render_failed(tx, hub, j, "too_many_attempts: the render did not finish")
            continue
        await tx.exec(
            """UPDATE media.render_jobs SET state = 'claimed', claimed_at = now(), attempts = attempts + 1,
                   updated_at = now() WHERE id = :id""",
            id=j["id"],
        )
        item = await tx.one(ITEM_SQL + " WHERE i.id = :id", id=j["item_id"])
        comp = await tx.one(
            """SELECT format, sha256, source FROM media.compositions
               WHERE id = (SELECT composition_id FROM media.render_jobs WHERE id = :j)""",
            j=j["id"],
        )
        spec = dict(j["spec"])
        return {
            "id": j["id"],
            "item": item["ref"],
            "company": item["company"],
            "purpose": j["purpose"],
            "composition": {
                "format": comp["format"],
                "sha256": comp["sha256"],
                "source": comp["source"],
            },
            **spec,
        }
    return None


async def job_for(tx: Tx, job_id: UUID) -> dict[str, Any]:
    j = await tx.one(
        "SELECT * FROM media.render_jobs WHERE id = :id FOR UPDATE",
        id=job_id,
        not_found="not_found",
    )
    if j["state"] != "claimed":
        raise ApiError(409, "validation_failed", f"the job is {j['state']}")
    return j


def job_file_ids(j: dict[str, Any]) -> set[str]:
    spec = j["spec"] or {}
    ids = {a["id"] for a in spec.get("assets") or []}
    if spec.get("voice"):
        ids.add(spec["voice"]["id"])
    return ids


async def render_output(
    tx: Tx,
    j: dict[str, Any],
    *,
    name: str,
    kind: str,
    file_id: UUID,
    width: int | None,
    height: int | None,
    duration_s: float | None,
    size: int,
) -> None:
    files = list(j["files"] or [])
    files.append(
        {
            "name": name,
            "kind": kind,
            "file_id": str(file_id),
            "width": width,
            "height": height,
            "duration_s": duration_s,
            "bytes": size,
        }
    )
    await tx.exec(
        "UPDATE media.render_jobs SET files = CAST(:f AS jsonb), updated_at = now() WHERE id = :id",
        id=j["id"],
        f=canonical(files),
    )


async def render_done(
    tx: Tx, hub: Any, j: dict[str, Any], metrics: dict[str, Any], violations: list[dict[str, Any]]
) -> dict[str, Any]:
    item = await tx.one(ITEM_SQL + " WHERE i.id = :id FOR UPDATE OF i", id=j["item_id"])
    if violations:
        rules = ", ".join(sorted({str(v.get("rule")) for v in violations}))[:200]
        await _render_failed(tx, hub, j, f"runtime_violation: {rules}", violations=violations)
        return {"state": "failed"}
    files = list(j["files"] or [])
    outs = [f for f in files if f["kind"] in ("video", "image")]
    if not outs:
        await _render_failed(tx, hub, j, "no_output: the worker sent no file", permanent=False)
        return {"state": "failed"}
    await tx.exec(
        """UPDATE media.render_jobs SET state = 'done', finished_at = now(), metrics = CAST(:m AS jsonb),
               updated_at = now() WHERE id = :id""",
        id=j["id"],
        m=canonical(metrics),
    )
    spec = j["spec"] or {}
    if j["purpose"] == "preview":
        previews = ((item.get("render_meta") or {}).get("previews") or [])[-4:]
        previews.append({"job": str(j["id"]), "files": outs, "at": datetime.now(UTC)})
        meta = {**(item.get("render_meta") or {}), "previews": previews}
        await tx.exec(
            "UPDATE media.items SET render_meta = CAST(:m AS jsonb) WHERE id = :id",
            id=item["id"],
            m=canonical(meta),
        )
        if meta.get("final_wanted"):
            meta.pop("final_wanted", None)
            await tx.exec(
                "UPDATE media.items SET render_meta = CAST(:m AS jsonb) WHERE id = :id",
                id=item["id"],
                m=canonical(meta),
            )
            await queue_render(
                tx,
                hub,
                await load_item(tx, item["ref"], lock=True),
                purpose="final",
                by=SERVICE.code,
            )
        await events.emit(
            tx, item["company"], "media.item", item["ref"], {"render": "preview_ready"}
        )
        return {"state": "done", "purpose": "preview"}
    main = outs[0]
    by_name = {o["name"]: o for o in outs}
    posters = {f["name"]: f["file_id"] for f in files if f["kind"] == "poster"}
    vtt = next((f for f in files if f["kind"] == "captions"), None)
    targets = targets_of(item)
    if item["kind"] == "design":
        outputs = [{**o, "placement": "design"} for o in outs]
    else:
        outputs = [
            {
                **by_name.get(o["name"], o),
                "placement": t["placement"],
                "poster_file_id": posters.get(o["name"]),
            }
            for t in targets
            for o in outs
        ]
    pages = (
        [o for o in outs if o["kind"] == "image"]
        if (item["kind"] in ("carousel", "design"))
        else []
    )
    await tx.exec(
        """UPDATE media.items SET outputs = CAST(:o AS jsonb), pages = CAST(:p AS jsonb), render_file_id = :r,
               captions_file_id = :cap, render_meta = CAST(:m AS jsonb)
           WHERE id = :id""",
        id=item["id"],
        o=canonical(outputs),
        p=canonical(pages),
        r=UUID(main["file_id"]),
        cap=UUID(vtt["file_id"]) if vtt else None,
        m=canonical(
            {
                "job": str(j["id"]),
                "metrics": metrics,
                "mark": bool((spec.get("overlay") or {}).get("mark")),
                "captions": len(spec.get("captions") or []),
                "voice": bool(spec.get("voice")),
            }
        ),
    )
    await events.emit(tx, item["company"], "media.item", item["ref"], {"render": "ready"})
    await advance(tx, hub, await load_item(tx, item["ref"], lock=True), "render")
    return {"state": "done", "purpose": "final"}


async def render_failed(tx: Tx, hub: Any, j: dict[str, Any], error: str) -> None:
    """The one-shot's own failure: retried up to three times, except a
    composition the schema refused (`schema:`) or a render that is too large."""
    permanent = error.startswith(("schema", "too_large", "runtime_violation"))
    await _render_failed(tx, hub, j, error, permanent=permanent)


async def _render_failed(
    tx: Tx,
    hub: Any,
    j: dict[str, Any],
    error: str,
    *,
    permanent: bool = True,
    violations: list[dict[str, Any]] | None = None,
) -> None:
    error = re.sub(r"[^A-Za-z0-9 _.:,/()-]", "", error)[:300] or "failed"
    retry = not permanent and int(j["attempts"]) < RENDER_MAX_ATTEMPTS
    await tx.exec(
        """UPDATE media.render_jobs SET state = CASE WHEN :retry THEN 'queued' ELSE 'failed' END,
               error = :e, claimed_at = NULL, finished_at = CASE WHEN :retry THEN NULL ELSE now() END,
               metrics = COALESCE(metrics, CAST(:v AS jsonb)), updated_at = now() WHERE id = :id""",
        id=j["id"],
        retry=retry,
        e=error,
        v=canonical({"violations": violations}) if violations else None,
    )
    if retry or j["purpose"] == "preview":
        return
    item = await tx.one(ITEM_SQL + " WHERE i.id = :id FOR UPDATE OF i", id=j["item_id"])
    fails = int((item.get("render_meta") or {}).get("failures") or 0) + 1
    meta = {**(item.get("render_meta") or {}), "failures": fails, "last_error": error}
    await tx.exec(
        "UPDATE media.items SET render_meta = CAST(:m AS jsonb) WHERE id = :id",
        id=item["id"],
        m=canonical(meta),
    )
    if fails >= RENDER_MAX_ATTEMPTS:
        await _note(tx, item, "failed", f"render نشد ({error[:120]}).")
        return
    # Back to its composer with the reason (a runtime violation is the schema's).
    await wake(
        tx,
        hub,
        await load_item(tx, item["ref"], lock=True),
        "composition",
        note=f"The render failed: {error}. Fix the composition and store it again.",
    )


# ------------------------------------------------------ the narrations --
async def _narrated_item(tx: Tx, job: dict[str, Any]) -> dict[str, Any] | None:
    """The item a registry job narrates, while it still waits for that job
    (in `voicing`, its narration pending on this very job); else None."""
    if job.get("kind") != "narration" or not job.get("subject_ref"):
        return None
    item = await tx.first(
        ITEM_SQL + " WHERE i.ref = :r AND i.company_id = :co FOR UPDATE OF i",
        r=job["subject_ref"],
        co=job["company_id"],
    )
    if item is None:
        return None
    n = dict(item.get("narration") or {})
    if item["state"] != "voicing" or n.get("state") != "pending" or n.get("job") != str(job["id"]):
        return None  # moved on, rejected, or a newer narration: the file only stays a file
    return dict(item)


async def on_narration(tx: Tx, hub: Any, job: dict[str, Any], file_id: UUID) -> None:
    """voices.ON_NARRATION: the item's narration is ready (spoken by the TTS
    one-shot, through §17.1): the file goes on the item and the render follows."""
    item = await _narrated_item(tx, job)
    if item is None:
        return
    seconds = await tx.scalar("SELECT duration_s FROM files.files WHERE id = :f", f=file_id)
    n = dict(item.get("narration") or {})
    n.update(
        {
            "state": "ready",
            "file_id": str(file_id),
            "duration_s": float(seconds) if seconds is not None else None,
        }
    )
    await tx.exec(
        "UPDATE media.items SET narration = CAST(:n AS jsonb), voice_file_id = :f WHERE id = :id",
        id=item["id"],
        n=canonical(n),
        f=file_id,
    )
    await advance(tx, hub, await load_item(tx, item["ref"], lock=True), "voice")


async def on_narration_failed(tx: Tx, hub: Any, job: dict[str, Any], error: str) -> None:
    """voices.ON_NARRATION_FAILED: the registry gave the narration up (three
    tries, or its voice is not installed): the item goes on silent, with captions."""
    item = await _narrated_item(tx, job)
    if item is None:
        return
    n = dict(item.get("narration") or {})
    n.update(
        {"state": "failed", "error": re.sub(r"[^A-Za-z0-9 _.:-]", "", error)[:200] or "failed"}
    )
    await tx.exec(
        "UPDATE media.items SET narration = CAST(:n AS jsonb) WHERE id = :id",
        id=item["id"],
        n=canonical(n),
    )
    await _note(tx, item, "voicing", "صدا ساخته نشد؛ آیتم بی‌صدا و با زیرنویس ادامه میدهد.")
    await advance(tx, hub, await load_item(tx, item["ref"], lock=True), "voice")


def _hook_the_registry() -> None:
    from hq_api.domain import voices as V

    if on_narration not in V.ON_NARRATION:
        V.ON_NARRATION.append(on_narration)
    if on_narration_failed not in V.ON_NARRATION_FAILED:
        V.ON_NARRATION_FAILED.append(on_narration_failed)


_hook_the_registry()


# ---------------------------------------------------------------- checks --
async def run_checks(tx: Tx, hub: Any, item: dict[str, Any]) -> None:
    from hq_api.domain import studio_checks as K

    await _note(tx, item, "checking", None)
    results = await K.run(tx, hub, await load_item(tx, item["ref"], lock=True))
    results.append({"key": "qc", "result": "n/a", "note_fa": "در انتظار بازبینی مدیر رسانه"})
    await tx.exec(
        "UPDATE media.items SET checks = CAST(:c AS jsonb) WHERE id = :id",
        id=item["id"],
        c=canonical(results),
    )
    await advance(tx, hub, await load_item(tx, item["ref"], lock=True), "checks")


# ----------------------------------------------------------------- sweep --
async def tick_series(tx: Tx, hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """The sealed series' schedules (the caller checked the holding's lock):
    one item per due occurrence (≤ max_per_day a day in the owner's zone),
    with the next topic of the pool; missed occurrences older than 30 minutes
    are skipped, never backfilled."""
    now = now or datetime.now(UTC)
    tz = await owner_zone(tx)
    zone = ZoneInfo(tz)
    made: list[str] = []
    skipped: dict[str, str] = {}
    for s in await tx.all(
        SERIES_SQL + " WHERE s.status = 'sealed' ORDER BY s.created_at FOR UPDATE OF s SKIP LOCKED"
    ):
        if (lock := await gate.automation_lock(tx, s["company_id"])) is not None:
            skipped[s["ref"]] = gate.REASONS.get(lock, lock)
            continue
        since = max(x for x in (s["ticked_at"], s["sealed_at"], now - CATCH_UP) if x is not None)
        due = recurrence.occurrences(
            recurrence.parse(s["schedule"]), tz, since, now + timedelta(seconds=1), limit=5
        )
        topic_next = int(s["topic_next"])
        for at in due:
            if at <= (s["ticked_at"] or datetime.min.replace(tzinfo=UTC)):
                continue
            if await tx.scalar(
                "SELECT 1 FROM media.items WHERE series_id = :s AND slot_at = :at", s=s["id"], at=at
            ):
                continue  # this occurrence already has its item
            day = (
                at.astimezone(zone)
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .astimezone(UTC)
            )
            n = await tx.scalar(
                "SELECT count(*) FROM media.items WHERE series_id = :s AND slot_at >= :d AND slot_at < :e",
                s=s["id"],
                d=day,
                e=day + timedelta(days=1),
            )
            if int(n) >= int(s["max_per_day"]):
                continue
            pool = list((s["topics"] or {}).get("pool") or [])
            topic = pool[topic_next % len(pool)] if pool else (s["topics"] or {}).get("rule_fa")
            if pool:
                topic_next += 1
            item = await create_item(
                tx,
                hub,
                SERVICE,
                company_id=s["company_id"],
                company=s["company"],
                kind=s["kind"],
                title_fa=f"{s['title_fa']} · {topic}"[:300] if topic else s["title_fa"],
                brief_md=None,
                series=s,
                topic_fa=topic,
                slot_at=at,
                one_off=False,
            )
            made.append(item["ref"])
        await tx.exec(
            "UPDATE media.series SET ticked_at = :t, topic_next = :n WHERE id = :id",
            id=s["id"],
            t=now,
            n=topic_next,
        )
    return {"made": made, "skipped": skipped}


def item_ref_ok(ref: str) -> bool:
    return bool(re.match(r"^MI-[0-9]{4,}$", ref))
