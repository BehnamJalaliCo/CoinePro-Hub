"""⟨2026-11-10⟩ «تأیید و انتشار» (contract §44.5): the owner's tap on a file of his own session
publishes it.

The owner, 2026-11-10: «این برو بیا و هی مهر بکن و اینو مجوز بده … آزار و اذیت میده منو». What
goes out and can be taken back (a reel, a post, a story) needs his word once, in the session, on
the file itself: no second card, no passkey. The passkey stays for money, deleting for good,
keys and access, and a destructive command on a server.

Nothing here is a new way out of the hub. Instagram, for every company, lives on IG-Hub (the
owner's decision of 2026-11-08), and a server publishes through its own runner (§26.1b, the
`publish` job: the files, the caption, a command that prints `{external_id, url}`). So the tap
makes one `publish` job on IG-Hub's server with the company's own `publish_command` (a
non-secret setting of its Instagram connection, registered by the holding's technical team with
`connection.set`). The job is the record: the session reads its publishes from the jobs.

A company whose publish command is not registered yet is never the owner's step: the technical
work is made by code, once, under the order, and the session says so.

⟨§45⟩ The owner's standing permission (2026-11-10: «به صورت خودکار از روز دوم انجام بشه … نه اینکه
هر بار من تایید کنم. ۱۰۰ تا کارگروه راه بندازم اونوقت باید روزی صد بار تایید بدم»). His word can
be given once for a working group instead of once for each output: a company's membership carries
`publish` (`auto`: the hub sends the package of each routine's delivered work by itself, on that
word; `ask`, the default: each output waits for his tap, here or in «خروجی‌ها»). Both go out through
the same job. The package is the newest output of the routine's work that holds a video (else an
image), its cover an image of the same output, its caption the output's `caption.txt`. A package
without a caption is never sent on a standing word: it waits for his tap and says so.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import connections as CN
from hq_api.domain import gate
from hq_api.domain import humanize as HZ
from hq_api.domain import order_report as OR
from hq_api.domain import servers as SV
from hq_api.errors import ApiError
from hq_api.principal import Principal

log = logging.getLogger("hq_api.session_publish")

Kind = Literal["reel", "post", "story", "carousel"]
State = Literal[
    "publishing", "scheduled", "published", "failed", "waiting_seal", "waiting_setup", "cancelled"
]  # as OR's; fmt: skip
CAPTION_MAX = 2200
TIMEOUT_S = 900
KIND_FA = {"reel": "ریلز", "post": "پست", "story": "استوری", "carousel": "اسلاید"}
OWNER_FA = "مدیر کل"
SYSTEM_FA = "سامانه"
LIVE = ("queued", "running", "awaiting_seal")
SERVICE = Principal(kind="service", code="publish", role="service")

TAPPED_FA = "«تأیید و انتشار»: {kind} «{name}» به @{account} میرود"
SETUP_FA = (
    "مسیر انتشار اینستاگرام {company} روی {server} هنوز ثبت نشده؛ تیم فنی هلدینگ وصلش میکند و "
    "خبرش همین‌جا می‌آید. کاری از تو لازم نیست."
)
SETUP_NOBODY_FA = (
    "مسیر انتشار اینستاگرام {company} روی {server} هنوز ثبت نشده و کسی در تیم فنی نیست که وصلش کند."
)
# ⟨2026-11-11⟩ the team's work for it was delivered today and the route is still not ready: no work
# is open until the next day's (connections.tech_work_of), and this says so
SETUP_AGAIN_FA = (
    "مسیر انتشار اینستاگرام {company} روی {server} هنوز ثبت نشده؛ تیم فنی هلدینگ امروز یک بار "
    "سراغش رفته و تا یک روز دیگر دوباره سراغش میرود. کاری از تو لازم نیست."
)
# the team's work for it failed (or was cancelled) a moment ago: the next one comes after a
# cool-down (connections.TECH_AFTER_FAIL), never one a tick
SETUP_SOON_FA = (
    "مسیر انتشار اینستاگرام {company} روی {server} هنوز ثبت نشده؛ تیم فنی هلدینگ سراغش رفته و "
    "کمی بعد دوباره سراغش میرود. کاری از تو لازم نیست."
)
DONE_FA = "منتشر شد: {kind} در @{account}"
FAILED_FA = "انتشار {kind} در @{account} انجام نشد: {why}"
NOT_MEDIA_FA = "فقط ویدیو یا تصویر منتشر میشود."
PICK_ACCOUNT_FA = "این شرکت چند حساب دارد؛ یکی را انتخاب کن."
# ⟨§45⟩ the standing permission
GROUPS = Principal(kind="service", code="groups", role="service")
CAPTION_NAMES = ("caption.txt", "caption.md")
# ⟨§46⟩ the package's comment rule (the word viewers are asked to comment, the private reply,
# its link), the time a publication is set for, and asking IG-Hub again how it stands
COMMENT_NAMES = ("comment.txt", "comment.md")
PENDING = "pub:"  # the command's external id while scheduled, or while Meta prepares the file
# ⟨§51⟩ the command's external id once IG-Hub cancelled the publication it held
CANCELLED = "cancelled:"
CANCEL_CODE = "publish_cancelled"  # the hub's own job, cancelled before any runner took it
TRANSIENT = ("timed_out", "not_started")  # a check the runner never answered: asked again
# a check (or a cancel) the hub itself took back before it was answered (a kill switch, the
# server detached): the publication IG-Hub holds is untouched, so it is asked about again
HELD = ("company_locked", "server_detached")
CHECK_AFTER = timedelta(seconds=90)
CHECK_EVERY = timedelta(minutes=3)
CHECK_FOR = timedelta(hours=6)
CHECK_TIMEOUT_S = 120
SOON = timedelta(minutes=2)  # a time this near is «now»
FAR = timedelta(days=365)
CAROUSEL_MAX = 10
SCHEDULED_FA = "زمان‌بندی شد: {kind} در @{account}، {when}"
QUEUED_FA = "اینستاگرام دارد {kind} را آماده میکند (@{account})؛ نتیجه همین‌جا می‌آید"
AT = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
CAPTION_FILE_MAX = 64 * 1024
SWEEP_DAYS = 3
WORK_DONE = ("done", "delivered")
AUTO_SENT_FA = "انتشار خودکار: {kind} به @{account} میرود"
AUTO_DONE_FA = "خودکار منتشر شد: {kind} در @{account}"
AUTO_FAILED_FA = "انتشار خودکار {kind} در @{account} انجام نشد: {why}"
NO_PACKAGE_FA = "کار این نوبت بسته‌ای برای انتشار نداشت (ویدیو یا تصویر با کپشن)؛ چیزی منتشر نشد."
NO_CAPTION_FA = "ویدیوی این نوبت کپشن نداشت؛ خودکار منتشر نشد و با یک لمس تو میرود."
# ⟨2026-11-11⟩ the very line the working group's page and the desk card say of a route not ready
WAIT_SETUP_FA = "مسیر انتشار این شرکت را تیم فنی وصل میکند؛ بعد خودش منتشر میشود."
ALREADY_FA = "این بسته را خودت پیش‌تر منتشر کرده‌ای؛ دوباره فرستاده نشد."
PICK_STANDING_FA = "این شرکت چند حساب دارد و حساب انتشار خودکار این کارگروه انتخاب نشده است."
HELD_TITLE_FA = "انتشار خودکار «{group}» ({company}) منتظر توست"
# ⟨§51⟩ cancelling a publication IG-Hub still holds
CANCEL_ASKED_FA = "لغو انتشار: {kind} در @{account}"
CANCEL_DONE_FA = "لغو شد: {kind} در @{account} منتشر نمیشود"
CANCEL_FAILED_FA = "لغو {kind} در @{account} انجام نشد: {why}"
CANCEL_NOTE_FA = "لغو انجام نشد ({why})؛ از تقویم خود IG-Hub هم میشود لغوش کرد."
CANCELLING_FA = "در حال لغو"
NOT_CANCELLABLE_FA = "این انتشار دیگر لغوشدنی نیست."
STILL_SENDING_FA = "فایل هنوز در راه IG-Hub است؛ چند لحظه بعد دوباره لغو کن."
# ⟨§47⟩ a package whose topic was said before is not sent by itself
DUPLICATE_FA = (
    "موضوع این نوبت پیش‌تر گفته شده («{title}»، {day})؛ خودکار منتشر نشد. اگر همین را میخواهی، "
    "با یک لمس تو میرود."
)
# ⟨§52⟩ Instagram publishes JPEG pictures only
JPEG = "image/jpeg"
JPEG_QUALITY = 92
JPEG_SIDE = 4096
NOT_A_PICTURE_FA = "تصویر «{name}» خوانده نشد و به JPEG تبدیل نشد."
FAILED_TITLE_FA = "انتشار خودکار «{group}» ({company}) انجام نشد"


SessionPublish = OR.SessionPublish


def _line(who: str, what: str) -> dict[str, Any]:
    """A step of the session as written: an account's handle and a post's link are what the
    owner reads here, so they are not passed through the humanizer (it takes them for codes)."""
    return {"at": datetime.now(UTC).isoformat(), "who_fa": who, "what_fa": what[:500]}


def _cfg(row: dict[str, Any] | None) -> dict[str, Any]:
    cfg = (row or {}).get("config") or {}
    return json.loads(cfg) if isinstance(cfg, str) else dict(cfg)


def _when(raw: Any) -> datetime | None:
    """A time with its zone, or None."""
    try:
        t = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return t if t.tzinfo is not None else None


def _pending(j: dict[str, Any]) -> bool:
    """The command answered `pub:<id>` and no link: IG-Hub holds it for its time, or Meta is
    still preparing the file. The hub asks again (follow_up)."""
    result = OR._j(j.get("result")) or {}
    ext = str(result.get("external_id") or "")
    return str(j["state"]) == "done" and ext.startswith(PENDING) and not result.get("url")


def _waiting(meta: dict[str, Any]) -> State:
    when = _when(meta.get("scheduled_at"))
    return "scheduled" if when is not None and when > datetime.now(UTC) else "publishing"


def _state(j: dict[str, Any]) -> State:
    st = str(j["state"])
    meta = (OR._j(j["args"]) or {}).get("meta") or {}
    asks = meta.get("check") or meta.get("cancel")
    if st in ("queued", "running"):
        # a question (or ⟨§51⟩ a cancel) on its way: what it asks about stands as it stood
        return _waiting(meta) if asks else "publishing"
    if st == "awaiting_seal":
        return "waiting_seal"
    if st == "done":
        ext = str((OR._j(j.get("result")) or {}).get("external_id") or "")
        if ext.startswith(CANCELLED):
            return "cancelled"
        return _waiting(meta) if _pending(j) else "published"
    if str(j.get("error_code") or "") == CANCEL_CODE:
        return "cancelled"  # ⟨§51⟩ he cancelled it before it reached IG-Hub
    if meta.get("cancel"):
        return _waiting(meta)  # ⟨§51⟩ a cancel IG-Hub refused: the publication still stands
    code = str(j.get("error_code") or "")
    if meta.get("check") and (code in TRANSIENT or (st == "cancelled" and code in HELD)):
        return _waiting(meta)  # the question was never answered: it is asked again
    return "failed"


def view(j: dict[str, Any]) -> SessionPublish:
    args = OR._j(j["args"]) or {}
    result = OR._j(j.get("result")) or {}
    s = args.get("session") or {}
    meta = args.get("meta") or {}
    files = args.get("files") or []
    state = _state(j)
    url = str(result.get("url") or "") or None
    note = None
    if state == "failed":
        note = HZ.humanize(str(j.get("summary_fa") or "")) or "پلتفرم انتشار را نپذیرفت"
    elif state == "waiting_seal":
        note = "دستور انتشار این سرور مُهر تو را میخواهد."
    elif meta.get("cancel") and state in ("scheduled", "publishing"):
        # ⟨§51⟩ a cancel on its way, or one IG-Hub refused (the publication still stands)
        if str(j["state"]) in ("queued", "running"):
            note = CANCELLING_FA
        else:
            why = HZ.humanize(str(j.get("summary_fa") or "")) or "IG-Hub نپذیرفت"
            note = CANCEL_NOTE_FA.format(why=why)[:500]
    words = (meta.get("comment") or {}).get("keywords") or []
    return SessionPublish(
        job=str(j["id"]),
        output=s.get("output"),
        file_id=str(s.get("file_id") or ""),
        file_name=s.get("file_name") or ((files or [{}])[0] or {}).get("name"),
        cover_name=s.get("cover_name")
        or next((x.get("name") for x in files if x.get("role") == "cover"), None),
        kind=args.get("kind") if args.get("kind") in KIND_FA else "post",
        account=args.get("account"),
        state=state,
        url=url if url and url.startswith(("https://", "http://")) else None,
        note_fa=note,
        at=j.get("created_at"),
        published_at=j.get("finished_at") if state == "published" else None,
        auto=bool(args.get("standing")),
        scheduled_at=_when(meta.get("scheduled_at")),
        comment=str(words[0]) if words else None,
        files=max(1, int(s.get("files") or 1)),
    )


JOB_COLS = (
    "j.id, j.state, j.args, j.result, j.summary_fa, j.error_code, j.created_at, j.finished_at"
)
JOB_SQL = f"""SELECT {JOB_COLS} FROM infra.server_jobs j
              WHERE j.kind = 'publish' AND j.args -> 'session' ->> 'order' = :ref"""  # noqa: S608
# an output's publishes, whatever asked for them (a tap in its session, a tap in «خروجی‌ها», the
# owner's standing word)
OUT_SQL = f"""SELECT {JOB_COLS} FROM infra.server_jobs j
              WHERE j.kind = 'publish' AND j.args -> 'session' ->> 'output' = :out"""  # noqa: S608


def publication_of(j: dict[str, Any]) -> tuple[str, str, str, str]:
    """What one publication is: this file of this output, as this kind, to this account."""
    args = OR._j(j["args"]) or {}
    s = args.get("session") or {}
    return (
        str(s.get("output") or ""), str(s.get("file_id") or ""),
        str(args.get("account") or ""), str(args.get("kind") or ""),
    )  # fmt: skip


def collapse(rows: list[Any], limit: int = 20) -> list[SessionPublish]:
    """⟨1.33⟩ §55.4 One row for one publication. The hub asks IG-Hub about a publication it holds
    (⟨§46⟩ `meta.check`) and cancels it (⟨§51⟩ `meta.cancel`) with further jobs of the same
    file, account and kind: the newest of them says where the publication stands and is the row
    (its `job` is what a cancel names); the job that first sent it says when (`at`). `rows`:
    the jobs newest first."""
    out: list[SessionPublish] = []
    open_chain: dict[tuple[str, str, str, str], int] = {}
    for r in rows:
        j = dict(r)
        key = publication_of(j)
        meta = (OR._j(j["args"]) or {}).get("meta") or {}
        asks = bool(meta.get("check") or meta.get("cancel"))
        if key in open_chain:
            out[open_chain[key]].at = j.get("created_at")
            if not asks:
                del open_chain[key]  # the job that sent it: the chain ends here
            continue
        out.append(view(j))
        if asks:
            open_chain[key] = len(out) - 1
    return out[:limit]


async def of_order(tx: Tx, ref: str) -> list[SessionPublish]:
    """The session's publishes, newest first (the jobs are the record)."""
    rows = await tx.all(JOB_SQL + " ORDER BY j.created_at DESC LIMIT 80", ref=ref)
    return collapse(rows)


OUTPUT_SQL = """SELECT d.ref, d.title, d.work_id, d.company_id, d.attachments, d.produced_with,
                       c.code AS company, c.name_fa AS company_fa, w.ref AS work_ref
                FROM cartable.deliverables d JOIN core.companies c ON c.id = d.company_id
                JOIN work.work w ON w.id = d.work_id"""


async def _route(tx: Tx, company_id: UUID) -> dict[str, Any]:
    """Where a company's Instagram goes out: its registered accounts, its publish command and
    IG-Hub's server (the company's own setting, else the holding's default). ⟨2026-11-11⟩ The
    command is the connection's own, else the holding's IG-Hub command (the `ig_hub` setting):
    the route is ready once the technical team has registered at least one account."""
    cfg = _cfg(
        await tx.first(
            "SELECT config FROM growth.connections WHERE company_id = :co AND kind = 'instagram'",
            co=company_id,
        )
    )
    hubs = CN.ig_hub()
    code = await tx.scalar("SELECT code FROM core.companies WHERE id = :co", co=company_id)
    # ⟨audit 2026-11-11⟩ a stored server that is neither IG-Hub's nor the company's own is never
    # used: the route is not ready (the technical team registers it again), and IG-Hub stands in
    where = CN.ig_server(cfg, str(code) if code is not None else None)
    accounts = [str(a).lstrip("@") for a in cfg.get("accounts") or []]
    command = CN.publish_command_of(cfg) or ""
    server_co, server_name = where or (hubs["company"], hubs["server"])
    return {
        "accounts": accounts,
        "command": command,
        "ready": bool(accounts and command and where is not None),
        "server_co": server_co,
        "server_name": server_name,
    }


async def _files(tx: Tx, d: dict[str, Any]) -> list[dict[str, Any]]:
    """The output's own files (originals of its company), in the order they were made."""
    ids = [str(a) for a in d["attachments"] or []]
    if not ids:
        return []
    return await tx.all(
        """SELECT id, name, mime, size, storage_key FROM files.files
           WHERE id = ANY(CAST(:ids AS uuid[])) AND variant = 'original' AND company_id = :co
           ORDER BY created_at, name""",
        ids=ids,
        co=d["company_id"],
    )


async def _text_of(tx: Tx, hub: Any, d: dict[str, Any], names: tuple[str, ...]) -> str | None:
    """A small text file of the output, by its name (a workshop turn leaves it in `out/`)."""
    f = next(
        (x for x in await _files(tx, d) if str(x["name"] or "").strip().lower() in names), None
    )
    if f is None or hub is None or int(f["size"] or 0) > CAPTION_FILE_MAX:
        return None

    def read() -> str:
        with open(hub.storage.local_path(f["storage_key"]), "rb") as fh:
            return fh.read(CAPTION_FILE_MAX).decode("utf-8", errors="replace")

    try:
        return (await asyncio.to_thread(read)).replace("\ufeff", "").strip() or None
    except OSError:
        return None


async def caption_of(tx: Tx, hub: Any, d: dict[str, Any]) -> str | None:
    """⟨§45⟩ The caption a package carries: the text of its `caption.txt` (a workshop turn leaves
    it in `out/` beside the video and the cover)."""
    text = await _text_of(tx, hub, d, CAPTION_NAMES)
    return text[:CAPTION_MAX] or None if text else None


COMMENT_KEYS = {
    "keywords": ("keyword", "keywords", "word", "کلمه", "کلمات", "کد", "عدد"),
    "reply": ("reply", "message", "پاسخ", "جواب", "پیام"),
    "link": ("link", "url", "لینک"),
    "public": ("public", "public_reply", "عمومی", "پاسخ عمومی", "جواب عمومی"),
}


def clean_comment(raw: Any) -> dict[str, Any] | None:
    """⟨§46⟩ A comment rule as IG-Hub takes it, or None when it has no word or no reply: up to
    10 words, the private reply, an https link (anything else is left out), public replies."""
    if not isinstance(raw, dict):
        return None
    words = raw.get("keywords") or raw.get("keyword") or []
    if isinstance(words, str):
        words = re.split(r"[,،]", words)
    words = list(dict.fromkeys(str(w).strip()[:100] for w in words if str(w).strip()))[:10]
    reply = str(raw.get("reply") or raw.get("reply_text") or "").strip()[:1000]
    if not words or not reply:
        return None
    out: dict[str, Any] = {"keywords": words, "reply": reply}
    link = str(raw.get("link") or "").strip()
    if re.fullmatch(r"https://\S{3,1900}", link):
        out["link"] = link
        if str(raw.get("button") or "").strip():
            out["button"] = str(raw["button"]).strip()[:20]
    public = raw.get("public_replies") or []
    if isinstance(public, str):
        public = [public]
    public = [str(x).strip()[:300] for x in public if str(x).strip()][:10]
    if public:
        out["public_replies"] = public
    return out


def parse_comment(text: str | None) -> dict[str, Any] | None:
    """`comment.txt` of a package, one `label: value` a line, in English or Persian:
    `keyword: ۷`, `reply: این هم لینک`, `link: https://…`, `public: دایرکت را ببین`."""
    got: dict[str, Any] = {}
    for line in (text or "").splitlines():
        label, sep, value = line.partition(":")
        if not sep:
            label, sep, value = line.partition("：")
        label, value = label.strip().lower().strip("-* "), value.strip()
        if not sep or not value:
            continue
        for key, names in COMMENT_KEYS.items():
            if label in names:
                if key == "public":
                    got.setdefault("public_replies", []).append(value)
                else:
                    got.setdefault(key, value)
    return clean_comment(got)


async def comment_of(tx: Tx, hub: Any, d: dict[str, Any]) -> dict[str, Any] | None:
    """⟨§46⟩ The comment rule a package carries (`comment.txt`), or None."""
    return parse_comment(await _text_of(tx, hub, d, COMMENT_NAMES))


async def of_output(tx: Tx, output: str) -> list[SessionPublish]:
    rows = await tx.all(OUT_SQL + " ORDER BY j.created_at DESC LIMIT 80", out=output)
    return collapse(rows)


async def panel(tx: Tx, output: str, hub: Any = None) -> OR.PublishPanel:
    """What the output's page shows: the company's registered accounts, the publishes of this
    output, the caption its package carries, its session (when it is one's) and ⟨§45⟩ the working
    group whose routine made it, with the owner's standing word."""
    d = await tx.first(OUTPUT_SQL + " WHERE d.ref = :r", r=output)
    if d is None:
        raise ApiError(404, "not_found", f"output {output}")
    route = await _route(tx, d["company_id"])
    run = await run_of_work(tx, d["work_id"])
    # ⟨§49⟩ the hour this company's account does best at (the sheet offers it as a time)
    from hq_api.domain import best_hour as BH
    from hq_api.domain.gov_common import owner_tz

    rule = rule_of(run["publish"]) if run else None
    handle = (rule or {}).get("account") or (
        route["accounts"][0] if len(route["accounts"]) == 1 else None
    )
    best = await BH.best(tx, d["company_id"], handle, await owner_tz(tx)) if handle else None
    return OR.PublishPanel(
        order=await OR.order_of_work(tx, d["work_id"]),
        accounts=route["accounts"],
        ready=route["ready"],
        publishes=await of_output(tx, output),
        tap=True,
        caption=await caption_of(tx, hub, dict(d)),
        comment=await comment_of(tx, hub, dict(d)),
        group=run["group_key"] if run else None,
        group_fa=run["group_fa"] if run else None,
        mode=rule["mode"] if rule else None,
        best=best if best is not None and best.enough else None,
    )


async def order_of_output(tx: Tx, output: str) -> str | None:
    """The session an output belongs to; None for an output of no session (⟨§45⟩ it is tapped
    in «خروجی‌ها» all the same)."""
    work_id = await tx.scalar("SELECT work_id FROM cartable.deliverables WHERE ref = :r", r=output)
    if work_id is None:
        raise ApiError(404, "not_found", f"output {output}")
    return await OR.order_of_work(tx, work_id)


def _to_jpeg(path: str) -> tuple[bytes, int, int]:
    """A picture as Instagram takes it: turned the way it is seen, on white where it was
    see-through, RGB, its longer side at most JPEG_SIDE."""
    import io

    from PIL import Image, ImageOps

    with contextlib.suppress(ImportError):  # HEIC from a phone
        import pillow_heif

        pillow_heif.register_heif_opener()
    with Image.open(path) as raw:
        img = ImageOps.exif_transpose(raw) or raw
        if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.getchannel("A"))
            img = flat
        else:
            img = img.convert("RGB")
        img.thumbnail((JPEG_SIDE, JPEG_SIDE))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return out.getvalue(), img.width, img.height


async def as_jpeg(tx: Tx, hub: Any, f: dict[str, Any], company_id: UUID) -> dict[str, Any]:
    """⟨§52⟩ Instagram publishes JPEG pictures only (IG-Hub refuses any other: `publish_jpeg_only`).
    A PNG, WebP or HEIC of an output goes out as a JPEG the hub makes from it once: a file of
    the same company that names the picture it came from (`meta.jpeg_of`). A video, and a
    picture that is a JPEG already, are returned as they are. `ValueError`: not a picture the
    hub can read."""
    mime = str(f["mime"])
    if not mime.startswith("image/") or mime == JPEG or hub is None:
        return f
    made = await tx.first(
        """SELECT id, name, mime FROM files.files
           WHERE company_id = :co AND variant = 'original' AND mime = 'image/jpeg'
             AND meta ->> 'jpeg_of' = :src ORDER BY created_at DESC LIMIT 1""",
        co=company_id,
        src=str(f["id"]),
    )
    if made is not None:
        return dict(made)
    key = f.get("storage_key") or await tx.scalar(
        "SELECT storage_key FROM files.files WHERE id = :id AND company_id = :co",
        id=f["id"],
        co=company_id,
    )
    try:
        data, width, height = await asyncio.to_thread(
            _to_jpeg, str(hub.storage.local_path(str(key)))
        )
    except Exception as exc:
        raise ValueError(str(f["name"])) from exc
    from hq_api.domain import files as F

    stem = str(f["name"] or "image").rsplit(".", 1)[0][:240] or "image"
    name = f"{stem}.jpg"
    new_key, sha = await hub.storage.put(data)
    fid = await F.insert(
        tx, company_id=company_id, name=name, mime=JPEG, size=len(data), sha256=sha,
        storage_key=new_key, kind="image", by_kind="service", by_code=SERVICE.code,
        width=width, height=height, meta={"jpeg_of": str(f["id"])},
    )  # fmt: skip
    return {"id": fid, "name": name, "mime": JPEG}


def publication_key(output: str, file_id: str, account: str, what: str) -> str:
    """One publication's own key, the same on every try: IG-Hub can refuse to make it twice."""
    import hashlib

    return hashlib.sha256(f"{output}|{file_id}|{account}|{what}".encode()).hexdigest()[:32]


async def lock_publication(tx: Tx, output: str, file_id: str, account: str, what: str) -> None:
    """Held till the transaction ends: two senders of the same publication (two taps, a tap and
    the standing sweep) are made one after the other, so the second one's `last_of` sees the
    first one's job and sends nothing."""
    await tx.exec(
        "SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))",
        k="publish:" + publication_key(output, file_id, account, what),
    )


async def _send(
    tx: Tx,
    who: Principal,
    d: dict[str, Any],
    f: dict[str, Any],
    cover: dict[str, Any] | None,
    *,
    hub: Any = None,
    what: Kind,
    account: str,
    caption: str,
    route: dict[str, Any],
    order: str | None,
    standing: dict[str, Any] | None = None,
    request_id: str | None = None,
    more: list[dict[str, Any]] | None = None,
    scheduled_at: datetime | None = None,
    comment: dict[str, Any] | None = None,
    first_comment: str | None = None,
) -> dict[str, Any]:
    """One `publish` job on IG-Hub's server: the file (a reel's cover, a carousel's other
    files), the caption, the company's own command. ⟨§46⟩ `scheduled_at`: IG-Hub holds it for
    that time; `comment`: the rule made for this post alone when it is out."""

    def item(x: dict[str, Any], role: str | None = None) -> dict[str, Any]:
        mime = str(x["mime"])
        kind = "video" if mime.startswith("video/") else "image"
        got = {"file_id": str(x["id"]), "name": x["name"], "mime": mime, "kind": kind}
        return {**got, "role": role} if role else got

    # ⟨§52⟩ every picture of the job is a JPEG (the file the tap named stays the publication's
    # own: `session.file_id` is the original)
    sent = await as_jpeg(tx, hub, f, d["company_id"])
    others = [await as_jpeg(tx, hub, x, d["company_id"]) for x in more or []]
    files = [item(sent), *(item(x) for x in others)]
    cover_name = cover["name"] if cover is not None else None
    if cover is not None:
        files.append(item(await as_jpeg(tx, hub, cover, d["company_id"]), "cover"))
    server = await SV.load_server(tx, route["server_name"], company=route["server_co"])
    where = f"جلسه‌ی {order}" if order else f"خروجی {d['ref']}"
    meta: dict[str, Any] = {
        "channel": "instagram",
        "kind": what,
        "account": account,
        "company": d["company"],
        # the cover, when there is one, is the job's second file (HQ_PUBLISH_FILE_2)
        "cover": cover is not None,
        # ⟨1.31⟩ the publication's own key, the same on a second try (IG-Hub may refuse a twin)
        "key": publication_key(str(d["ref"]), str(f["id"]), account, what),
    }
    if scheduled_at is not None:
        meta["scheduled_at"] = scheduled_at.isoformat()
    if comment and what != "story":
        meta["comment"] = comment
    if (first_comment or "").strip() and what != "story":
        meta["first_comment"] = str(first_comment).strip()[:CAPTION_MAX]
    j = await SV.create_job(
        tx,
        server=server,
        kind="publish",
        args={
            "session": {
                "order": order,
                "output": d["ref"],
                "work": d["work_ref"],
                "company": d["company"],
                "file_id": str(f["id"]),
                # kept here too: a later question about this publication carries no file
                "file_name": f["name"],
                "cover_name": cover_name,
                "files": 1 + len(more or []),
            },
            **({"standing": standing} if standing else {}),
            "kind": what,
            "placement": f"instagram_{what}",
            "account": account,
            "command": route["command"],
            "caption": caption.strip()[:CAPTION_MAX],
            "title_fa": str(d["title"])[:200],
            "meta": meta,
            "files": files,
        },
        actor_kind=who.kind,
        actor_code=who.code,
        work_ref=str(d["work_ref"]),
        summary=f"انتشار {'خودکار ' if standing else ''}{KIND_FA[what]} در @{account} از {where}",
        timeout_s=TIMEOUT_S,
        request_id=request_id,
    )
    return {**dict(j), "server_company_id": server["company_id"]}


async def last_of(
    tx: Tx, output: str, file_id: str, account: str, what: str
) -> SessionPublish | None:
    """Where this file stands for this account and kind (its newest job), unless that failed:
    the same file is never sent twice, whatever sent it; after a failure a tap is a new try."""
    row = await tx.first(LAST_SQL, out=output, f=file_id, a=account, k=what)
    got = view(dict(row)) if row is not None else None
    # ⟨§51⟩ one he cancelled is over as well: a tap is a new publication
    return got if got is not None and got.state not in ("failed", "cancelled") else None


async def _setup_fa(tx: Tx, ref: str | None) -> str:
    """What the session says of a route that is not ready, by where the team's work stands: open
    (it is being connected), failed a moment ago (the next try after a cool-down), delivered
    today (the next try within a day), or nobody to take it."""
    from hq_api.domain import work as W

    if ref is None:
        return SETUP_NOBODY_FA
    status = await tx.scalar("SELECT status FROM work.work WHERE ref = :r", r=ref)
    if status in W.OPEN:
        return SETUP_FA
    return SETUP_SOON_FA if status in CN.TECH_DEAD else SETUP_AGAIN_FA


def when_fa(t: datetime, tz: str) -> str:
    """A time as the owner reads it: «امروز ۱۸:۳۰» is said by the app; here the clock alone."""
    from hq_api.domain.gov_common import zone

    local = t.astimezone(zone(tz))
    return f"ساعت {local:%H:%M} ({local:%Y-%m-%d})"


async def start(
    tx: Tx,
    who: Principal,
    ref: str | None,
    *,
    output: str,
    file_id: UUID,
    kind: Kind | None = None,
    caption: str | None = None,
    account: str | None = None,
    cover_file_id: UUID | None = None,
    request_id: str | None = None,
    file_ids: list[UUID] | None = None,
    scheduled_at: datetime | None = None,
    comment: dict[str, Any] | None = None,
    first_comment: str | None = None,
    hub: Any = None,
) -> SessionPublish:
    """The owner's tap. `tx` reaches every company (the session is the holding's, the file is
    its company's, the job is IG-Hub's). `ref`: the session the tap was made in; None for an
    output tapped in «خروجی‌ها» (⟨§45⟩ a working group's daily output is no session's).
    ⟨§46⟩ `file_ids`: a carousel's other files, in order; `scheduled_at`: the time he set (IG-Hub
    holds it till then; a time that near is now); `comment`: the rule for this post alone."""
    rep = None
    if ref is not None:
        rep = await OR.ensure(tx, ref)
        order = await OR.load_order(tx, ref) if rep is not None else None
        if rep is None or order is None:
            raise ApiError(404, "not_found", f"order {ref}")
        works = await OR.tree(tx, OR.root_refs(order))
        d = await tx.first(
            OUTPUT_SQL + " WHERE d.ref = :r AND d.work_id = ANY(:ids)",
            r=output,
            ids=[w["id"] for w in works],
        )
    else:
        d = await tx.first(OUTPUT_SQL + " WHERE d.ref = :r", r=output)
    if d is None:
        raise ApiError(404, "not_found", f"output {output}" + (f" of {ref}" if ref else ""))
    d = dict(d)
    if str(file_id) not in {str(a) for a in d["attachments"] or []}:
        raise ApiError(422, "validation_failed", fields={"file_id": "not a file of this output"})
    f = await tx.first(
        """SELECT id, name, mime FROM files.files
           WHERE id = :id AND variant = 'original' AND company_id = :co""",
        id=file_id,
        co=d["company_id"],
    )
    mime = str((f or {}).get("mime") or "")
    media = "video" if mime.startswith("video/") else "image" if mime.startswith("image/") else ""
    if f is None or not media:
        raise ApiError(
            422, "validation_failed", fields={"file_id": "a video or an image"},
            message_fa=NOT_MEDIA_FA,
        )  # fmt: skip
    what: Kind = kind or ("reel" if media == "video" else "post")
    if what == "reel" and media != "video":
        raise ApiError(422, "validation_failed", fields={"kind": "a reel is a video"})
    # ⟨§46⟩ a carousel: this file and 1 to 9 more of the same output, in the order given
    more: list[dict[str, Any]] = []
    others = list(dict.fromkeys(str(x) for x in file_ids or [] if str(x) != str(file_id)))
    if what == "carousel":
        mine = {str(a) for a in d["attachments"] or []}
        rows = await tx.all(
            """SELECT id, name, mime FROM files.files
               WHERE id = ANY(CAST(:ids AS uuid[])) AND variant = 'original' AND company_id = :co
                 AND (mime LIKE 'image/%' OR mime LIKE 'video/%')""",
            ids=others,
            co=d["company_id"],
        )
        by_id = {str(r["id"]): dict(r) for r in rows if str(r["id"]) in mine}
        if not 1 <= len(others) <= CAROUSEL_MAX - 1 or len(by_id) != len(others):
            raise ApiError(
                422, "validation_failed",
                fields={"file_ids": "1 to 9 more videos or images of this output"},
                message_fa="اسلاید ۲ تا ۱۰ فایل از همین خروجی میخواهد.",
            )  # fmt: skip
        more = [by_id[x] for x in others]
    elif others:
        raise ApiError(422, "validation_failed", fields={"file_ids": "only for a carousel"})
    when = None
    if scheduled_at is not None:
        if scheduled_at.tzinfo is None:
            raise ApiError(
                422, "validation_failed", fields={"scheduled_at": "a time with its zone"}
            )
        if scheduled_at > datetime.now(UTC) + FAR:
            raise ApiError(
                422, "validation_failed", fields={"scheduled_at": "at most a year ahead"}
            )
        when = scheduled_at if scheduled_at > datetime.now(UTC) + SOON else None
    rule = clean_comment(comment) if what != "story" else None
    if comment is not None and what != "story" and rule is None:
        raise ApiError(
            422, "validation_failed", fields={"comment": "a word and a reply"},
            message_fa="برای کامنت، هم کلمه لازم است و هم پاسخ.",
        )  # fmt: skip
    # ⟨2026-11-10⟩ the owner's own order: «ویدیو و کاور و کپشن رو میبریم به شرکت IG»: a reel goes out
    # with its cover, an image of the same output
    cover = None
    if cover_file_id is not None:
        if what != "reel":
            raise ApiError(422, "validation_failed", fields={"cover_file_id": "a reel's cover"})
        cover = await tx.first(
            """SELECT id, name, mime FROM files.files
               WHERE id = :id AND variant = 'original' AND company_id = :co AND mime LIKE 'image/%'""",
            id=cover_file_id,
            co=d["company_id"],
        )
        if cover is None or str(cover_file_id) not in {str(a) for a in d["attachments"] or []}:
            raise ApiError(
                422, "validation_failed",
                fields={"cover_file_id": "an image of this output"},
            )  # fmt: skip
    if await tx.scalar("SELECT control.lock_state(:co)", co=d["company_id"]) is not None:
        raise ApiError(423, "company_locked")

    route = await _route(tx, d["company_id"])
    accounts = route["accounts"]
    company_fa = str(d["company_fa"] or d["company"])
    if not route["ready"]:
        # never the owner's step: the holding's technical team registers it, once, under the order
        made = await CN.ensure_ig_publish_work(tx, d["company_id"], requested_by=d["work_id"])
        say = (await _setup_fa(tx, made)).format(company=company_fa, server=route["server_name"])
        if rep is not None:
            await OR._append_steps(tx, rep["id"], [_line(SYSTEM_FA, say)])
        return SessionPublish(
            output=d["ref"], file_id=str(file_id), file_name=f["name"], kind=what,
            state="waiting_setup", note_fa=say,
        )  # fmt: skip
    wanted = (account or "").strip().lstrip("@")
    if not wanted and len(accounts) == 1:
        wanted = accounts[0]
    if wanted not in accounts:
        raise ApiError(
            422, "validation_failed",
            fields={"account": "one of: " + ", ".join("@" + a for a in accounts[:20])},
            message_fa=PICK_ACCOUNT_FA,
        )  # fmt: skip

    # one tap, one post: the same file to the same account is not sent twice (whatever sent it)
    await lock_publication(tx, d["ref"], str(file_id), wanted, what)
    before = await last_of(tx, d["ref"], str(file_id), wanted, what)
    if before is not None:
        return before

    try:
        j = await _send(
            tx, who, d, dict(f), dict(cover) if cover is not None else None,
            hub=hub, what=what, account=wanted, caption=caption or "", route=route, order=ref,
            request_id=request_id, more=more, scheduled_at=when, comment=rule,
            first_comment=first_comment,
        )  # fmt: skip
    except ValueError as exc:  # ⟨§52⟩ a picture the hub could not read to make a JPEG of
        raise ApiError(
            422, "validation_failed", fields={"file_id": "not a readable picture"},
            message_fa=NOT_A_PICTURE_FA.format(name=str(exc)[:120]),
        ) from exc  # fmt: skip
    if what != "story":
        # ⟨§47⟩ what he sends himself was said too: a routine's output he tapped is in its
        # working group's ledger (a twin is his own choice here, so it is only noted)
        from hq_api.domain import topics as TP

        run = await run_of_work(tx, d["work_id"])
        if run is not None:
            with contextlib.suppress(ApiError):
                async with tx.conn.begin_nested():
                    await TP.of_package(
                        tx, run, d, topic_txt=await _text_of(tx, hub, d, TP.TOPIC_NAMES),
                        caption=caption or await caption_of(tx, hub, d),
                    )  # fmt: skip
    if rep is not None:
        said = TAPPED_FA.format(kind=KIND_FA[what], name=f["name"], account=wanted)
        if when is not None:
            from hq_api.domain.gov_common import owner_tz

            said += f"، {when_fa(when, await owner_tz(tx))}"
        await OR._append_steps(tx, rep["id"], [_line(OWNER_FA, said)])
    for co_id in dict.fromkeys((d["company_id"], j["server_company_id"])):
        await audit.record(
            tx,
            who,
            company_id=co_id,
            action="publish.session",
            action_class="A3",
            target_kind="order" if ref else "deliverable",
            target_ref=ref or d["ref"],
            summary=f"the owner's «تأیید و انتشار» in {ref or 'the outputs'}: {what} {f['name']} of "
            f"{d['ref']} to @{wanted} ({d['company']}) through "
            f"{route['server_co']}:{route['server_name']}; job {j['id']}"[:500],
            request_id=request_id,
        )
    row = await tx.one(
        f"SELECT {JOB_COLS} FROM infra.server_jobs j WHERE j.id = :id",  # noqa: S608
        id=j["id"],
    )
    return view(dict(row))


# ------------------------------------------------- §45 the standing permission --
def rule_of(raw: Any) -> dict[str, Any]:
    """A membership's `publish` as the code reads it: `ask` unless the owner said `auto`.
    ⟨§46⟩ `at`: the clock time («HH:MM», the owner's zone) its package goes out at."""
    cfg = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    mode = "auto" if cfg.get("mode") == "auto" else "ask"
    account = str(cfg.get("account") or "").strip().lstrip("@") or None
    at = str(cfg.get("at") or "").strip()
    return {"mode": mode, "account": account, "story": bool(cfg.get("story")),
            "since": cfg.get("since"), "at": at if AT.fullmatch(at) else None,
            # ⟨§49⟩ `best`: the hour the account's own posts did best at, once there is a
            # month of them; until then `at`, else at once
            "best": bool(cfg.get("best"))}  # fmt: skip


def at_today(at: str | None, tz: str, now: datetime | None = None) -> datetime | None:
    """Today's «HH:MM» in the owner's zone, when it is still ahead; None: it goes out now (a
    package made after its hour is not kept for tomorrow, when the next one comes)."""
    m = AT.fullmatch(at or "")
    if m is None:
        return None
    from hq_api.domain.gov_common import zone

    local = (now or datetime.now(UTC)).astimezone(zone(tz))
    t = local.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
    return t.astimezone(UTC) if t > local + SOON else None


RUN_SQL = """SELECT x.id AS run_id, x.routine, x.occurrence_at, x.work_id, x.note_fa, x.company_id,
                    x.group_id, g.key AS group_key, g.title_fa AS group_fa, g.state AS group_state,
                    m.publish, m.state AS member_state, w.ref AS work_ref,
                    w.status AS work_status, w.delivered_at, c.code AS company,
                    c.name_fa AS company_fa
             FROM growth.routine_runs x JOIN growth.groups g ON g.id = x.group_id
             JOIN growth.memberships m ON m.group_id = x.group_id AND m.company_id = x.company_id
             JOIN work.work w ON w.id = x.work_id
             JOIN core.companies c ON c.id = x.company_id"""


UP_CTE = """WITH RECURSIVE up(id, hops) AS (
    SELECT CAST(:w AS uuid), 0
    UNION
    SELECT COALESCE(w.parent_id, w.requested_by_work_id), up.hops + 1
    FROM work.work w JOIN up ON w.id = up.id
    WHERE COALESCE(w.parent_id, w.requested_by_work_id) IS NOT NULL AND up.hops < 20) """
UP_WHERE = " WHERE x.work_id IN (SELECT id FROM up) ORDER BY x.at DESC LIMIT 1"
SWEEP_WHERE = """ WHERE x.occurrence_at > now() - make_interval(days => :days)
    AND x.state = ANY(CAST(:st AS text[])) AND w.status = ANY(CAST(:done AS text[]))
    AND m.publish ->> 'mode' = 'auto' AND m.state = 'on' AND g.state = 'on'
    AND NOT EXISTS (SELECT 1 FROM infra.server_jobs j WHERE j.kind = 'publish'
                    AND j.args -> 'standing' ->> 'run' = x.id::text)
    ORDER BY x.occurrence_at LIMIT 50"""
LAST_WHERE = """ AND j.args -> 'session' ->> 'file_id' = :f AND j.args ->> 'account' = :a
    AND j.args ->> 'kind' = :k ORDER BY j.created_at DESC LIMIT 1"""
LAST_SQL = "".join((OUT_SQL, LAST_WHERE))  # module constants only
RUN_UP_SQL = "".join((UP_CTE, RUN_SQL, UP_WHERE))
RUN_SWEEP_SQL = "".join((RUN_SQL, SWEEP_WHERE))
RUN_OF_WORK_SQL = "".join((RUN_SQL, " WHERE x.work_id = :w"))
RUN_BY_ID_SQL = "".join((RUN_SQL, " WHERE x.id = CAST(:r AS uuid)"))


async def run_of_work(tx: Tx, work_id: UUID) -> dict[str, Any] | None:
    """The routine run a work item belongs to (itself, or up its parents and its requests)."""
    row = await tx.first(RUN_UP_SQL, w=str(work_id))
    return dict(row) if row is not None else None


async def package_of(tx: Tx, run: dict[str, Any]) -> dict[str, Any] | None:
    """What a routine's work made to go out: its newest finished output that carries a caption
    (`caption.txt`) and a video (with an image of the same output as its cover: one named
    `cover…` first) or, without a video, an image. `captioned: False`: there is a video but no
    output carries a caption with one (said to the owner; never sent). None: the work made
    nothing to publish (a report, an analysis), which is no fault."""
    works = await OR.tree(tx, [str(run["work_ref"])])
    rows = await tx.all(
        OUTPUT_SQL
        + " WHERE d.work_id = ANY(:ids) AND d.company_id = :co ORDER BY d.created_at DESC LIMIT 30",
        ids=[w["id"] for w in works],
        co=run["company_id"],
    )
    bare: dict[str, Any] | None = None
    for r in rows:
        d = dict(r)
        if (OR._j(d.get("produced_with")) or {}).get("unfinished"):
            continue
        files = await _files(tx, d)
        videos = [f for f in files if str(f["mime"]).startswith("video/")]
        images = [f for f in files if str(f["mime"]).startswith("image/")]
        images.sort(key=lambda f: not str(f["name"] or "").lower().startswith("cover"))
        captioned = any(str(f["name"] or "").strip().lower() in CAPTION_NAMES for f in files)
        if captioned and videos:
            return {"d": d, "file": dict(videos[0]), "captioned": True,
                    "cover": dict(images[0]) if images else None}  # fmt: skip
        if captioned and images:
            return {"d": d, "file": dict(images[0]), "cover": None, "captioned": True}
        if videos and bare is None:
            bare = {"d": d, "file": dict(videos[0]), "cover": None, "captioned": False}
    return bare


async def _hold(
    tx: Tx, run: dict[str, Any], why_fa: str, *, output: str | None = None, tell: bool = True
) -> str:
    """A run the standing word could not send: said once (the run's note and, when it is the
    owner's to tap, one notification with the output), never again for the same reason."""
    if (run.get("note_fa") or "") == why_fa:
        return "held"
    await tx.exec(
        "UPDATE growth.routine_runs SET note_fa = :n WHERE id = :id", id=run["run_id"], n=why_fa
    )
    if tell:
        from hq_api.domain import notify

        await notify.raise_notification(
            tx,
            company_id=run["company_id"],
            company_code=str(run["company"]),
            level="report",
            title_fa=HELD_TITLE_FA.format(
                group=run["group_fa"], company=run["company_fa"] or run["company"]
            )[:300],
            body_fa=why_fa,
            link_kind="deliverable" if output else "work",
            link_ref=output or str(run["work_ref"]),
            source_kind="system",
            source_code="publish",
            owner_action=True,
        )
    return "held"


async def publish_run(tx: Tx, hub: Any, run: dict[str, Any]) -> str:
    """⟨§45⟩ One routine run whose work is delivered goes out on the owner's standing word, if
    he gave it for this company in this working group before the run's time. Idempotent: a run
    is sent once (its jobs name it). ⟨2026-11-11⟩ The run is locked for the call: the hook after a
    deliver and the groups' tick never both send it ("busy": the other one has it)."""
    if not await tx.scalar(
        "SELECT 1 FROM growth.routine_runs WHERE id = :r FOR UPDATE SKIP LOCKED",
        r=run["run_id"],
    ):
        return "busy"
    rule = rule_of(run["publish"])
    if rule["mode"] != "auto":
        return "ask"
    if run["member_state"] != "on" or run["group_state"] != "on":
        return "off"
    if run["work_status"] not in WORK_DONE:
        return "open"
    try:
        since = datetime.fromisoformat(str(rule["since"]))
    except ValueError:
        since = None
    # only what was delivered after he gave his word: an output that was already waiting for his
    # tap when he said `auto` stays his to tap (never a surprise post of something older)
    made_at = run.get("delivered_at") or run["occurrence_at"]
    if since is not None and made_at < since:
        return "before"
    if await gate.automation_lock(tx, run["company_id"]) is not None:
        return "locked"
    # the API (a delivered work) and the worker's sweep can both reach the same run: one at a
    # time, so the second one sees the first one's job below and sends nothing
    await tx.exec(
        "SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))",
        k="publish-run:" + str(run["run_id"]),
    )
    if await tx.scalar(
        """SELECT 1 FROM infra.server_jobs j
           WHERE j.kind = 'publish' AND j.args -> 'standing' ->> 'run' = :r LIMIT 1""",
        r=str(run["run_id"]),
    ):
        return "sent"
    pkg = await package_of(tx, run)
    if pkg is None:
        return await _hold(tx, run, NO_PACKAGE_FA, tell=False)
    d, f, cover = pkg["d"], pkg["file"], pkg["cover"]
    caption = await caption_of(tx, hub, d) if pkg["captioned"] else None
    if not caption:
        return await _hold(tx, run, NO_CAPTION_FA, output=d["ref"])
    route = await _route(tx, run["company_id"])
    if not route["ready"]:
        # never the owner's step and never a push: the run (the working group's page) says the
        # line the desk card says, and every tick asks for the technical work (⟨2026-11-11⟩ an
        # open one stands; a failed or cancelled one is made again after a cool-down, a delivered
        # one once a day at most: connections.tech_work_of); the next tick after the route is
        # ready sends it
        await CN.ensure_ig_publish_work(tx, run["company_id"], requested_by=run["work_id"])
        await _hold(tx, run, WAIT_SETUP_FA, tell=False)
        return "waiting_setup"
    account = str(rule["account"] or (route["accounts"][0] if len(route["accounts"]) == 1 else ""))
    if account not in route["accounts"]:
        return await _hold(tx, run, PICK_STANDING_FA, output=d["ref"])
    kinds: list[Kind] = ["reel" if str(f["mime"]).startswith("video/") else "post"]
    if rule["story"]:
        kinds.append("story")
    # taken before the topic ledger is written (as a tap takes it before it): one order of locks
    for what in kinds:
        await lock_publication(tx, d["ref"], str(f["id"]), account, what)
    standing = {
        "run": str(run["run_id"]),
        "group": run["group_key"],
        "routine": run["routine"],
        "occurrence": run["occurrence_at"].isoformat(),
        "since": rule["since"],
    }
    # ⟨§46⟩ the hour he set for this working group (IG-Hub holds the package till then), and
    # the comment rule the package carries for this post
    from hq_api.domain.gov_common import owner_tz

    tz = await owner_tz(tx)
    when = at_today(rule["at"], tz)
    if rule["best"]:
        # ⟨§49⟩ the hour this account's posts did best at, today while it is still ahead; too
        # little data yet: his fixed hour when he set one, else now
        from hq_api.domain import best_hour as BH

        got = await BH.best(tx, run["company_id"], account, tz)
        if got.enough and got.hour:
            when = BH.next_at(int(got.hour[:2]), tz, datetime.now(UTC), tomorrow=False)
    comment = await comment_of(tx, hub, d)
    # ⟨§47⟩ a topic is never sent twice by itself: the run's own claim stands; a run that named
    # none is read from its package (`topic.txt`, else the caption's first line)
    from hq_api.domain import topics as TP

    twin = await TP.of_package(
        tx, run, d, topic_txt=await _text_of(tx, hub, d, TP.TOPIC_NAMES), caption=caption
    )
    # he may have tapped this very file himself already: the same file to the same account in
    # the same kind is never sent twice, whatever sent it (and what he sent is no twin to hold)
    todo: list[Kind] = [
        what for what in kinds
        if await last_of(tx, d["ref"], str(f["id"]), account, what) is None
    ]  # fmt: skip
    if twin is not None and todo:
        return await _hold(
            tx, run,
            DUPLICATE_FA.format(title=str(twin["title_fa"])[:120], day=f"{twin['created_at']:%Y-%m-%d}"),
            output=d["ref"],
        )  # fmt: skip
    sent: list[Kind] = []
    for what in todo:
        sent.append(what)
        j = await _send(
            tx, GROUPS, d, f, cover if what == "reel" else None,
            hub=hub, what=what, account=account, caption=caption if what != "story" else "",
            route=route, order=None, standing=standing, scheduled_at=when,
            comment=comment if what != "story" else None,
        )  # fmt: skip
        for co_id in dict.fromkeys((run["company_id"], j["server_company_id"])):
            await audit.record(
                tx,
                GROUPS,
                company_id=co_id,
                action="publish.standing",
                action_class="A3",
                target_kind="group",
                target_ref=f"{run['group_key']}:{run['company']}",
                summary=f"on the owner's standing permission of {rule['since'] or '-'}: {what} "
                f"{f['name']} of {d['ref']} ({run['routine']}) to @{account} through "
                f"{route['server_co']}:{route['server_name']}; job {j['id']}"[:500],
            )
    if not sent:
        await _hold(tx, run, ALREADY_FA, tell=False)
        return "sent"
    await tx.exec(
        "UPDATE growth.routine_runs SET note_fa = :n WHERE id = :id",
        id=run["run_id"],
        n=AUTO_SENT_FA.format(kind=KIND_FA[sent[0]], account=account)[:500],
    )
    await events.emit(
        tx, str(run["company"]), "group.run", str(run["work_ref"]),
        {"group": run["group_key"], "routine": run["routine"], "state": "publishing",
         "output": d["ref"]},
    )  # fmt: skip
    return "publishing"


async def after_delivered(hub: Any, work_id: UUID) -> str | None:
    """A work was delivered (after its commit): when it is a routine's own work, its package
    goes out on the owner's standing word. Never raises (a deliver is not undone by it); the
    groups' tick sweeps what this missed."""
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            row = await tx.first(RUN_OF_WORK_SQL, w=work_id)
            if row is None:
                return None
            return await publish_run(tx, hub, dict(row))
    except Exception:  # noqa: BLE001 - the sweep tries again
        log.warning("standing publish after a deliver failed", extra={"work": str(work_id)})
        return None


async def sweep(tx: Tx, hub: Any) -> int:
    """The groups' tick: every recent run of a member with the owner's standing word whose work
    is delivered and that has not gone out yet (a package that waited for its publish path, a
    deliver whose own hook was lost). Each in its own savepoint."""
    rows = await tx.all(RUN_SWEEP_SQL, days=SWEEP_DAYS, st=["queued", "done"], done=list(WORK_DONE))
    sent = 0
    for r in rows:
        try:
            async with tx.conn.begin_nested():
                if await publish_run(tx, hub, dict(r)) == "publishing":
                    sent += 1
        except Exception:  # noqa: BLE001 - one run never stops the tick
            log.warning("standing publish failed", extra={"run": str(r["run_id"])})
    return sent


async def set_rule(
    tx: Tx,
    group_id: UUID,
    company_id: UUID,
    *,
    mode: Literal["ask", "auto"],
    account: str | None = None,
    story: bool = False,
    at: str | None = None,
    best: bool = False,
) -> dict[str, Any]:
    """The owner's word for one company in one working group. `auto` with an account names one
    of the company's registered accounts (checked when there are any; a company whose path is
    not registered yet is checked when it goes out)."""
    wanted = (account or "").strip().lstrip("@") or None
    if mode == "auto":
        accounts = (await _route(tx, company_id))["accounts"]
        if accounts and wanted is None and len(accounts) == 1:
            wanted = accounts[0]
        if accounts and wanted not in accounts:
            raise ApiError(
                422, "validation_failed",
                fields={"account": "one of: " + ", ".join("@" + a for a in accounts[:20])},
                message_fa=PICK_ACCOUNT_FA,
            )  # fmt: skip
    clock = (at or "").strip() or None
    if clock is not None and AT.fullmatch(clock) is None:
        raise ApiError(
            422, "validation_failed", fields={"at": "HH:MM"},
            message_fa="ساعت انتشار را به شکل ۱۸:۳۰ بنویس.",
        )  # fmt: skip
    rule = (
        {"mode": "auto", "account": wanted, "story": bool(story), "at": clock,
         "best": bool(best), "since": datetime.now(UTC).isoformat(), "by": "owner"}
        if mode == "auto"
        else {"mode": "ask"}
    )  # fmt: skip
    await tx.exec(
        """UPDATE growth.memberships SET publish = CAST(:p AS jsonb), updated_at = now()
           WHERE group_id = :g AND company_id = :co""",
        g=group_id,
        co=company_id,
        p=json.dumps(rule, ensure_ascii=False),
    )
    return rule


def brief_block(raw: Any) -> str:
    """What a routine's work is told when the owner gave his standing word (appended to its
    brief by the groups' tick): the package, and that nobody is asked."""
    rule = rule_of(raw)
    if rule["mode"] != "auto":
        return ""
    to = f" to @{rule['account']}" if rule["account"] else ""
    also = " and as a story" if rule["story"] else ""
    at = f" at {rule['at']} (the owner's time)" if rule["at"] else ""
    if rule["best"]:
        at = " at the hour this account's posts do best (the hub chooses it)"
    return (
        "(Publishing: the owner gave this working group his standing permission. If this "
        "routine makes something to publish (a reel, a post), the hub itself publishes its "
        f"package to Instagram{to}{also}{at} when this work is delivered; nobody is asked. The "
        "package is one output that holds the video (`.mp4`), its cover (`cover.jpg`, a JPEG: "
        "Instagram publishes no PNG) and `caption.txt` (the caption with its hashtags, UTF-8, "
        "at most 2200 characters): have the workshop turn (`workshop.run`) that builds the video leave "
        "exactly these in `out/`. When the reel asks viewers to comment a word or a number, add "
        "`comment.txt` with three lines, `keyword: <that word>`, `reply: <the private message>` "
        "and `link: https://…`: whoever comments it on this post gets the reply with the link. "
        "When that one turn leaves the whole package in `out/` (the video or the picture, and "
        "`caption.txt`), its end delivers this work by itself and the package goes out, so give "
        "that turn the whole package (its input files included); a turn that leaves less wakes "
        "you to finish it (another turn, then deliver); never ask "
        "the owner to approve it. Without `caption.txt` nothing is published. A routine that "
        "makes nothing to publish (a report, an analysis) delivers as usual.)"
    )


async def after_job(hub: Any, job_id: UUID) -> None:
    """The publish job of a session (or ⟨§45⟩ of a standing word) ended, after its result was
    committed: the session says so (the run's note does, and a failure is told to the owner),
    and the company's audit trail keeps it. ⟨§46⟩ A publication IG-Hub holds for its time (or
    Meta is still preparing) is said once as «زمان‌بندی شد»; its end is said when a later
    question (follow_up) brings it."""
    from hq_api.domain.gov_common import owner_tz

    async with hub.db.tx(await hub.companies.ids()) as tx:
        j = await tx.first(
            f"SELECT {JOB_COLS} FROM infra.server_jobs j WHERE j.id = :id AND j.kind = 'publish'",  # noqa: S608
            id=job_id,
        )
        if j is None:
            return
        j = dict(j)
        args = OR._j(j["args"]) or {}
        s = args.get("session") or {}
        meta = args.get("meta") or {}
        standing = args.get("standing") or {}
        ref = str(s.get("order") or "")
        if not (ref or standing) or j["state"] in LIVE:
            return
        done = view(j)
        kind = KIND_FA.get(str(args.get("kind")), "پست")
        account = str(args.get("account") or "")
        rep = await OR.ensure(tx, ref) if ref else None
        run = None
        if standing:
            run = await tx.first(RUN_BY_ID_SQL, r=str(standing.get("run") or ""))
        if meta.get("cancel") and done.state != "published":
            # ⟨§51⟩ the end of a cancel: gone, or IG-Hub refused and the publication stands
            if done.state == "cancelled":
                say = CANCEL_DONE_FA.format(kind=kind, account=account)
            else:
                why = HZ.humanize(str(j.get("summary_fa") or "")) or "IG-Hub نپذیرفت"
                say = CANCEL_FAILED_FA.format(kind=kind, account=account, why=why)
            if rep is not None:
                await OR._append_steps(tx, rep["id"], [_line(SYSTEM_FA, say)])
            if run is not None and args.get("kind") != "story":
                await tx.exec(
                    "UPDATE growth.routine_runs SET note_fa = :n WHERE id = :id",
                    id=run["run_id"],
                    n=say[:500],
                )
            return
        if done.state == "cancelled":
            return  # cancelled before it reached IG-Hub: said when he cancelled it
        if done.state in ("scheduled", "publishing"):
            # not out yet: said once, when the command first answered (never for each question)
            if meta.get("check") or j["state"] != "done":
                return
            if done.state == "scheduled" and done.scheduled_at is not None:
                when = when_fa(done.scheduled_at, await owner_tz(tx))
                say = SCHEDULED_FA.format(kind=kind, account=account, when=when)
            else:
                say = QUEUED_FA.format(kind=kind, account=account)
            if rep is not None:
                await OR._append_steps(tx, rep["id"], [_line(SYSTEM_FA, say)])
            if run is not None and args.get("kind") != "story":
                await tx.exec(
                    "UPDATE growth.routine_runs SET note_fa = :n WHERE id = :id",
                    id=run["run_id"],
                    n=say[:500],
                )
            return
        ok = done.state == "published"
        company_id = await tx.scalar(
            "SELECT id FROM core.companies WHERE code = :c", c=str(s.get("company") or "")
        )
        if rep is not None:
            if ok:
                say = DONE_FA.format(kind=kind, account=account)
                say += f" · {done.url}" if done.url else ""
            else:
                say = FAILED_FA.format(kind=kind, account=account, why=done.note_fa or "-")
            await OR._append_steps(tx, rep["id"], [_line(SYSTEM_FA, say)])
        if standing:
            if ok:
                note = AUTO_DONE_FA.format(kind=kind, account=account)
                note += f" · {done.url}" if done.url else ""
            else:
                note = AUTO_FAILED_FA.format(kind=kind, account=account, why=done.note_fa or "-")
            # the reel's (or the post's) end is the run's note; a story's failure is told too
            if run is not None and (args.get("kind") != "story" or not ok):
                await tx.exec(
                    "UPDATE growth.routine_runs SET note_fa = :n WHERE id = :id",
                    id=run["run_id"],
                    n=note[:500],
                )
            if run is not None and not ok and company_id is not None:
                from hq_api.domain import notify

                await notify.raise_notification(
                    tx,
                    company_id=company_id,
                    company_code=str(run["company"]),
                    level="report",
                    title_fa=FAILED_TITLE_FA.format(
                        group=run["group_fa"], company=run["company_fa"] or run["company"]
                    )[:300],
                    body_fa=note,
                    link_kind="deliverable",
                    link_ref=str(s.get("output") or ""),
                    source_kind="system",
                    source_code="publish",
                    owner_action=True,
                )
        if company_id is not None:
            outcome = (
                f"published {done.url or ''}" if ok else f"failed ({j['error_code'] or j['state']})"
            )
            base = "publish.standing" if standing else "publish.session"
            await audit.record(
                tx,
                SERVICE,
                company_id=company_id,
                action=f"{base}_done" if ok else f"{base}_failed",
                action_class="A1",
                target_kind="group" if standing and not ref else "order",
                target_ref=ref or f"{standing.get('group')}:{s.get('company')}",
                summary=f"{args.get('kind')} to @{account} from {ref or s.get('output')}: "
                f"{outcome}"[:500],
            )


async def cancel(
    tx: Tx, who: Principal, job_id: UUID, *, request_id: str | None = None
) -> SessionPublish:
    """⟨§51⟩ The owner takes back a publication that is not out yet (set for a time, or still
    being prepared). One that never reached IG-Hub is cancelled here; one IG-Hub holds is
    cancelled there by a `publish` job with meta `cancel` and no file (its command answers
    `cancelled:pub:<id>`, or the post's link when it went out first). `409 not_cancellable` for
    anything else. `job`: any job of that publication."""
    first = await tx.first(
        f"SELECT {JOB_COLS} FROM infra.server_jobs j WHERE j.id = :id AND j.kind = 'publish'"  # noqa: S608
        " AND j.args ? 'session'",
        id=job_id,
    )
    if first is None:
        raise ApiError(404, "not_found", f"publication {job_id}")
    a0 = OR._j(first["args"]) or {}
    s0 = a0.get("session") or {}
    row = await tx.first(
        LAST_SQL, out=str(s0.get("output") or ""), f=str(s0.get("file_id") or ""),
        a=str(a0.get("account") or ""), k=str(a0.get("kind") or ""),
    )  # fmt: skip
    j = dict(row or first)
    now = view(j)
    args = OR._j(j["args"]) or {}
    meta = dict(args.get("meta") or {})
    if now.state not in ("scheduled", "publishing"):
        raise ApiError(409, "not_cancellable", f"it is {now.state}", message_fa=NOT_CANCELLABLE_FA)
    if meta.get("cancel") and str(j["state"]) in ("queued", "running"):
        return now  # a cancel is on its way already
    s = args.get("session") or {}
    ref = str(s.get("order") or "") or None
    kind = KIND_FA.get(str(args.get("kind")), "پست")
    account = str(args.get("account") or "")
    company_id = await tx.scalar(
        "SELECT id FROM core.companies WHERE code = :c", c=str(s.get("company") or "")
    )
    result = OR._j(j.get("result")) or {}
    ext = str(meta.get("check") or meta.get("cancel") or result.get("external_id") or "")
    job = await SV.load_job(tx, j["id"], lock=True)
    if not ext.startswith(PENDING):
        # the first job itself: IG-Hub has nothing yet
        if str(job["state"]) != "queued" or job.get("dispatched_at") is not None:
            raise ApiError(
                409, "not_cancellable", "the file is on its way", message_fa=STILL_SENDING_FA
            )
        await SV.cancel(tx, job, CANCEL_CODE, "مدیر کل انتشار را لغو کرد")
        said, new_id = CANCEL_DONE_FA.format(kind=kind, account=account), j["id"]
    else:
        if company_id is None:
            raise ApiError(409, "not_cancellable", message_fa=NOT_CANCELLABLE_FA)
        route = await _route(tx, company_id)
        server = await SV.load_server(tx, route["server_name"], company=route["server_co"])
        meta.pop("check", None)
        made = await SV.create_job(
            tx,
            server=server,
            kind="publish",
            args={**args, "caption": "", "files": [], "meta": {**meta, "cancel": ext}},
            actor_kind=who.kind,
            actor_code=who.code,
            work_ref=job.get("work_ref"),
            summary=f"لغو انتشار {kind} در @{account}",
            timeout_s=CHECK_TIMEOUT_S,
            request_id=request_id,
        )
        said, new_id = CANCEL_ASKED_FA.format(kind=kind, account=account), made["id"]
    if ref:
        rep = await OR.ensure(tx, ref)
        if rep is not None:
            await OR._append_steps(tx, rep["id"], [_line(OWNER_FA, said)])
    if company_id is not None:
        await audit.record(
            tx,
            who,
            company_id=company_id,
            action="publish.cancel",
            action_class="A2",
            target_kind="order" if ref else "deliverable",
            target_ref=ref or str(s.get("output") or ""),
            summary=f"the owner cancelled {args.get('kind')} to @{account} of "
            f"{s.get('output')} ({ext or 'not sent yet'}); job {new_id}"[:500],
            request_id=request_id,
        )
    out = await tx.one(
        f"SELECT {JOB_COLS} FROM infra.server_jobs j WHERE j.id = :id",  # noqa: S608
        id=new_id,
    )
    return view(dict(out))


# A publication set for a later time is followed from that time on (not from the day it was
# sent: one set 10 days ahead is asked about when it is due), and one not due yet is left out of
# the batch so it never crowds out the ones that are.
FOLLOW_SQL = """SELECT j.id, j.state, j.args, j.result, j.summary_fa, j.error_code, j.created_at,
       j.finished_at, j.work_ref
FROM infra.server_jobs j
CROSS JOIN LATERAL (
    SELECT CASE WHEN j.args -> 'meta' ->> 'scheduled_at' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
                THEN CAST(j.args -> 'meta' ->> 'scheduled_at' AS timestamptz) END AS at) s
WHERE j.kind = 'publish' AND j.args ? 'session'
  AND GREATEST(j.created_at, s.at) > now() - interval '8 days'
  AND (s.at IS NULL OR s.at <= CAST(:now AS timestamptz))
  AND ((j.state = 'done' AND j.result ->> 'external_id' LIKE 'pub:%' AND j.result ->> 'url' IS NULL)
       OR (j.state = 'failed' AND j.args -> 'meta' ? 'check'
           AND j.error_code = ANY(CAST(:transient AS text[])))
       OR (j.state = 'cancelled' AND j.args -> 'meta' ? 'check'
           AND j.error_code = ANY(CAST(:held AS text[])))
       OR (j.state = 'failed' AND j.args -> 'meta' ? 'cancel'
           AND COALESCE(j.error_code, '') <> 'publish_cancelled')
       OR (j.state = 'cancelled' AND j.args -> 'meta' ? 'cancel'
           AND j.error_code = ANY(CAST(:held AS text[]))))
  AND NOT EXISTS (
      SELECT 1 FROM infra.server_jobs n
      WHERE n.kind = 'publish' AND n.created_at > j.created_at
        AND n.args -> 'session' ->> 'output' = j.args -> 'session' ->> 'output'
        AND n.args -> 'session' ->> 'file_id' = j.args -> 'session' ->> 'file_id'
        AND n.args ->> 'account' = j.args ->> 'account' AND n.args ->> 'kind' = j.args ->> 'kind')
ORDER BY j.created_at LIMIT 50"""


async def follow_up(hub: Any, now: datetime | None = None) -> int:
    """⟨§46⟩ Every publication IG-Hub still holds (scheduled, or being prepared by Meta) is
    asked about again: a `publish` job with meta `check` and no file, 90 seconds after its time
    and then every 3 minutes, for 6 hours. Its answer is the publication's record from then on
    (the newest job is), so the session and the run hear its end as they hear any other.

    The 6 hours run from its time, or for one sent for now from its first answer
    (`meta.first_at`, carried by every question and cancel after it): never from the newest
    question, which would move them on with every answer and ask without end."""
    now = now or datetime.now(UTC)
    asked = 0
    async with hub.db.tx(await hub.companies.ids()) as tx:
        rows = await tx.all(FOLLOW_SQL, transient=list(TRANSIENT), held=list(HELD), now=now)
        for row in rows:
            j = dict(row)
            args = OR._j(j["args"]) or {}
            meta = dict(args.get("meta") or {})
            result = OR._j(j.get("result")) or {}
            # a question that was never answered, or ⟨§51⟩ a cancel IG-Hub refused: asked again
            again = meta.get("check") or meta.pop("cancel", None)
            ext = str(again or result.get("external_id") or "")
            when = _when(meta.get("scheduled_at"))
            since = j["finished_at"] or j["created_at"]
            # a chain from before `first_at` was carried starts its window here, once
            first = _when(meta.get("first_at")) or since
            meta["first_at"] = first.isoformat()
            due = max(when, since) if when is not None else since
            due += CHECK_EVERY if again else CHECK_AFTER
            if not ext.startswith(PENDING) or now < due or now > (when or first) + CHECK_FOR:
                continue
            try:
                async with tx.conn.begin_nested():
                    company_id = await tx.scalar(
                        "SELECT id FROM core.companies WHERE code = :c",
                        c=str((args.get("session") or {}).get("company") or ""),
                    )
                    if company_id is None:
                        continue
                    route = await _route(tx, company_id)
                    server = await SV.load_server(
                        tx, route["server_name"], company=route["server_co"]
                    )
                    await SV.create_job(
                        tx,
                        server=server,
                        kind="publish",
                        args={**args, "caption": "", "files": [], "meta": {**meta, "check": ext}},
                        actor_kind=SERVICE.kind,
                        actor_code=SERVICE.code,
                        work_ref=j["work_ref"],
                        summary=f"پیگیری انتشار {KIND_FA.get(str(args.get('kind')), 'پست')} "
                        f"در @{args.get('account')}",
                        timeout_s=CHECK_TIMEOUT_S,
                    )
                    asked += 1
            except Exception:  # noqa: BLE001 - one publication never stops the others
                log.warning("publish follow-up failed", extra={"job": str(j["id"])})
    return asked
