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
import json
import logging
from datetime import UTC, datetime
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

Kind = Literal["reel", "post", "story"]
State = Literal["publishing", "published", "failed", "waiting_seal", "waiting_setup"]  # as OR's
CAPTION_MAX = 2200
TIMEOUT_S = 900
KIND_FA = {"reel": "ریلز", "post": "پست", "story": "استوری"}
OWNER_FA = "مدیر کل"
SYSTEM_FA = "سامانه"
LIVE = ("queued", "running", "awaiting_seal")
SERVICE = Principal(kind="service", code="publish", role="service")

TAPPED_FA = "«تأیید و انتشار»: {kind} «{name}» به @{account} میرود"
SETUP_FA = (
    "مسیر انتشار اینستاگرام {company} روی {server} هنوز ثبت نشده؛ تیم فنی هلدینگ همین حالا وصلش "
    "میکند و خبرش همین‌جا می‌آید. کاری از شما لازم نیست."
)
SETUP_NOBODY_FA = (
    "مسیر انتشار اینستاگرام {company} روی {server} هنوز ثبت نشده و کسی در تیم فنی نیست که وصلش کند."
)
DONE_FA = "منتشر شد: {kind} در @{account}"
FAILED_FA = "انتشار {kind} در @{account} انجام نشد: {why}"
NOT_MEDIA_FA = "فقط ویدیو یا تصویر منتشر میشود."
PICK_ACCOUNT_FA = "این شرکت چند حساب دارد؛ یکی را انتخاب کنید."
# ⟨§45⟩ the standing permission
GROUPS = Principal(kind="service", code="groups", role="service")
CAPTION_NAMES = ("caption.txt", "caption.md")
CAPTION_FILE_MAX = 64 * 1024
SWEEP_DAYS = 3
WORK_DONE = ("done", "delivered")
AUTO_SENT_FA = "انتشار خودکار: {kind} به @{account} میرود"
AUTO_DONE_FA = "خودکار منتشر شد: {kind} در @{account}"
AUTO_FAILED_FA = "انتشار خودکار {kind} در @{account} انجام نشد: {why}"
NO_PACKAGE_FA = "کار این نوبت بسته‌ای برای انتشار نداشت (ویدیو یا تصویر با کپشن)؛ چیزی منتشر نشد."
NO_CAPTION_FA = "ویدیوی این نوبت کپشن نداشت؛ خودکار منتشر نشد و با یک لمس شما میرود."
WAIT_SETUP_FA = (
    "مسیر انتشار اینستاگرام این شرکت هنوز ثبت نشده؛ تیم فنی وصلش میکند و بعد خودش منتشر میشود."
)
ALREADY_FA = "این بسته را خودتان پیش‌تر منتشر کرده‌اید؛ دوباره فرستاده نشد."
PICK_STANDING_FA = "این شرکت چند حساب دارد و حساب انتشار خودکار این کارگروه انتخاب نشده است."
HELD_TITLE_FA = "انتشار خودکار «{group}» ({company}) منتظر شماست"
FAILED_TITLE_FA = "انتشار خودکار «{group}» ({company}) انجام نشد"


SessionPublish = OR.SessionPublish


def _line(who: str, what: str) -> dict[str, Any]:
    """A step of the session as written: an account's handle and a post's link are what the
    owner reads here, so they are not passed through the humanizer (it takes them for codes)."""
    return {"at": datetime.now(UTC).isoformat(), "who_fa": who, "what_fa": what[:500]}


def _cfg(row: dict[str, Any] | None) -> dict[str, Any]:
    cfg = (row or {}).get("config") or {}
    return json.loads(cfg) if isinstance(cfg, str) else dict(cfg)


def _state(j: dict[str, Any]) -> State:
    st = str(j["state"])
    if st in ("queued", "running"):
        return "publishing"
    if st == "awaiting_seal":
        return "waiting_seal"
    return "published" if st == "done" else "failed"


def view(j: dict[str, Any]) -> SessionPublish:
    args = OR._j(j["args"]) or {}
    result = OR._j(j.get("result")) or {}
    s = args.get("session") or {}
    state = _state(j)
    url = str(result.get("url") or "") or None
    note = None
    if state == "failed":
        note = HZ.humanize(str(j.get("summary_fa") or "")) or "پلتفرم انتشار را نپذیرفت"
    elif state == "waiting_seal":
        note = "دستور انتشار این سرور مُهر شما را میخواهد."
    return SessionPublish(
        job=str(j["id"]),
        output=s.get("output"),
        file_id=str(s.get("file_id") or ""),
        file_name=((args.get("files") or [{}])[0] or {}).get("name"),
        cover_name=next(
            (x.get("name") for x in args.get("files") or [] if x.get("role") == "cover"), None
        ),
        kind=args.get("kind") if args.get("kind") in KIND_FA else "post",
        account=args.get("account"),
        state=state,
        url=url if url and url.startswith(("https://", "http://")) else None,
        note_fa=note,
        at=j.get("created_at"),
        published_at=j.get("finished_at") if state == "published" else None,
        auto=bool(args.get("standing")),
    )


JOB_COLS = "j.id, j.state, j.args, j.result, j.summary_fa, j.created_at, j.finished_at"
JOB_SQL = f"""SELECT {JOB_COLS} FROM infra.server_jobs j
              WHERE j.kind = 'publish' AND j.args -> 'session' ->> 'order' = :ref"""  # noqa: S608
# an output's publishes, whatever asked for them (a tap in its session, a tap in «خروجی‌ها», the
# owner's standing word)
OUT_SQL = f"""SELECT {JOB_COLS} FROM infra.server_jobs j
              WHERE j.kind = 'publish' AND j.args -> 'session' ->> 'output' = :out"""  # noqa: S608


async def of_order(tx: Tx, ref: str) -> list[SessionPublish]:
    """The session's publishes, newest first (the jobs are the record)."""
    rows = await tx.all(JOB_SQL + " ORDER BY j.created_at DESC LIMIT 20", ref=ref)
    return [view(dict(r)) for r in rows]


OUTPUT_SQL = """SELECT d.ref, d.title, d.work_id, d.company_id, d.attachments, d.produced_with,
                       c.code AS company, c.name_fa AS company_fa, w.ref AS work_ref
                FROM cartable.deliverables d JOIN core.companies c ON c.id = d.company_id
                JOIN work.work w ON w.id = d.work_id"""


async def _route(tx: Tx, company_id: UUID) -> dict[str, Any]:
    """Where a company's Instagram goes out: its registered accounts, its publish command and
    IG-Hub's server (the company's own setting, else the holding's default)."""
    cfg = _cfg(
        await tx.first(
            "SELECT config FROM growth.connections WHERE company_id = :co AND kind = 'instagram'",
            co=company_id,
        )
    )
    hubs = CN.ig_hub()
    srv = cfg.get("server") if isinstance(cfg.get("server"), dict) else {}
    accounts = [str(a).lstrip("@") for a in cfg.get("accounts") or []]
    command = str(cfg.get("publish_command") or "").strip()
    return {
        "accounts": accounts,
        "command": command,
        "ready": bool(accounts and command),
        "server_co": str((srv or {}).get("company") or hubs["company"]),
        "server_name": str((srv or {}).get("name") or hubs["server"]),
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


async def caption_of(tx: Tx, hub: Any, d: dict[str, Any]) -> str | None:
    """⟨§45⟩ The caption a package carries: the text of its `caption.txt` (a workshop turn leaves
    it in `out/` beside the video and the cover)."""
    f = next(
        (x for x in await _files(tx, d) if str(x["name"] or "").strip().lower() in CAPTION_NAMES),
        None,
    )
    if f is None or hub is None or int(f["size"] or 0) > CAPTION_FILE_MAX:
        return None

    def read() -> str:
        with open(hub.storage.local_path(f["storage_key"]), "rb") as fh:
            return fh.read(CAPTION_FILE_MAX).decode("utf-8", errors="replace")

    try:
        text = (await asyncio.to_thread(read)).replace("﻿", "").strip()
    except OSError:
        return None
    return text[:CAPTION_MAX] or None


async def of_output(tx: Tx, output: str) -> list[SessionPublish]:
    rows = await tx.all(OUT_SQL + " ORDER BY j.created_at DESC LIMIT 20", out=output)
    return [view(dict(r)) for r in rows]


async def panel(tx: Tx, output: str, hub: Any = None) -> OR.PublishPanel:
    """What the output's page shows: the company's registered accounts, the publishes of this
    output, the caption its package carries, its session (when it is one's) and ⟨§45⟩ the working
    group whose routine made it, with the owner's standing word."""
    d = await tx.first(OUTPUT_SQL + " WHERE d.ref = :r", r=output)
    if d is None:
        raise ApiError(404, "not_found", f"output {output}")
    route = await _route(tx, d["company_id"])
    run = await run_of_work(tx, d["work_id"])
    return OR.PublishPanel(
        order=await OR.order_of_work(tx, d["work_id"]),
        accounts=route["accounts"],
        ready=route["ready"],
        publishes=await of_output(tx, output),
        tap=True,
        caption=await caption_of(tx, hub, dict(d)),
        group=run["group_key"] if run else None,
        group_fa=run["group_fa"] if run else None,
        mode=rule_of(run["publish"])["mode"] if run else None,
    )


async def order_of_output(tx: Tx, output: str) -> str | None:
    """The session an output belongs to; None for an output of no session (⟨§45⟩ it is tapped
    in «خروجی‌ها» all the same)."""
    work_id = await tx.scalar("SELECT work_id FROM cartable.deliverables WHERE ref = :r", r=output)
    if work_id is None:
        raise ApiError(404, "not_found", f"output {output}")
    return await OR.order_of_work(tx, work_id)


async def _send(
    tx: Tx,
    who: Principal,
    d: dict[str, Any],
    f: dict[str, Any],
    cover: dict[str, Any] | None,
    *,
    what: Kind,
    account: str,
    caption: str,
    route: dict[str, Any],
    order: str | None,
    standing: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """One `publish` job on IG-Hub's server: the file (and a reel's cover), the caption, the
    company's own command."""
    mime = str(f["mime"])
    media = "video" if mime.startswith("video/") else "image"
    server = await SV.load_server(tx, route["server_name"], company=route["server_co"])
    where = f"جلسه‌ی {order}" if order else f"خروجی {d['ref']}"
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
            },
            **({"standing": standing} if standing else {}),
            "kind": what,
            "placement": f"instagram_{what}",
            "account": account,
            "command": route["command"],
            "caption": caption.strip()[:CAPTION_MAX],
            "title_fa": str(d["title"])[:200],
            "meta": {
                "channel": "instagram",
                "kind": what,
                "account": account,
                "company": d["company"],
                # the cover, when there is one, is the job's second file (HQ_PUBLISH_FILE_2)
                "cover": cover is not None,
            },
            "files": [
                {"file_id": str(f["id"]), "name": f["name"], "mime": mime, "kind": media},
                *(
                    [
                        {
                            "file_id": str(cover["id"]),
                            "name": cover["name"],
                            "mime": str(cover["mime"]),
                            "kind": "image",
                            "role": "cover",
                        }
                    ]
                    if cover is not None
                    else []
                ),
            ],
        },
        actor_kind=who.kind,
        actor_code=who.code,
        work_ref=str(d["work_ref"]),
        summary=f"انتشار {'خودکار ' if standing else ''}{KIND_FA[what]} در @{account} از {where}",
        timeout_s=TIMEOUT_S,
        request_id=request_id,
    )
    return {**dict(j), "server_company_id": server["company_id"]}


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
) -> SessionPublish:
    """The owner's tap. `tx` reaches every company (the session is the holding's, the file is
    its company's, the job is IG-Hub's). `ref`: the session the tap was made in; None for an
    output tapped in «خروجی‌ها» (⟨§45⟩ a working group's daily output is no session's)."""
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
        say = (SETUP_FA if made else SETUP_NOBODY_FA).format(
            company=company_fa, server=route["server_name"]
        )
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
    before = await tx.first(
        SENT_SQL, out=d["ref"], f=str(file_id), a=wanted, k=what, st=[*LIVE, "done"]
    )
    if before is not None:
        return view(dict(before))

    j = await _send(
        tx, who, d, dict(f), dict(cover) if cover is not None else None,
        what=what, account=wanted, caption=caption or "", route=route, order=ref,
        request_id=request_id,
    )  # fmt: skip
    if rep is not None:
        await OR._append_steps(
            tx,
            rep["id"],
            [_line(OWNER_FA, TAPPED_FA.format(kind=KIND_FA[what], name=f["name"], account=wanted))],
        )
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
    """A membership's `publish` as the code reads it: `ask` unless the owner said `auto`."""
    cfg = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    mode = "auto" if cfg.get("mode") == "auto" else "ask"
    account = str(cfg.get("account") or "").strip().lstrip("@") or None
    return {"mode": mode, "account": account, "story": bool(cfg.get("story")),
            "since": cfg.get("since")}  # fmt: skip


RUN_SQL = """SELECT x.id AS run_id, x.routine, x.occurrence_at, x.work_id, x.note_fa, x.company_id,
                    g.key AS group_key, g.title_fa AS group_fa, g.state AS group_state,
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
SENT_WHERE = """ AND j.args -> 'session' ->> 'file_id' = :f AND j.args ->> 'account' = :a
    AND j.args ->> 'kind' = :k AND j.state = ANY(:st) ORDER BY j.created_at DESC LIMIT 1"""
SENT_SQL = "".join((OUT_SQL, SENT_WHERE))  # module constants only
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
    is sent once (its jobs name it)."""
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
        if (run.get("note_fa") or "") != WAIT_SETUP_FA:
            # never the owner's step: the technical team registers it; the next tick sends
            await CN.ensure_ig_publish_work(tx, run["company_id"], requested_by=run["work_id"])
            await _hold(tx, run, WAIT_SETUP_FA, tell=False)
        return "waiting_setup"
    account = str(rule["account"] or (route["accounts"][0] if len(route["accounts"]) == 1 else ""))
    if account not in route["accounts"]:
        return await _hold(tx, run, PICK_STANDING_FA, output=d["ref"])
    kinds: list[Kind] = ["reel" if str(f["mime"]).startswith("video/") else "post"]
    if rule["story"]:
        kinds.append("story")
    standing = {
        "run": str(run["run_id"]),
        "group": run["group_key"],
        "routine": run["routine"],
        "occurrence": run["occurrence_at"].isoformat(),
        "since": rule["since"],
    }
    sent: list[Kind] = []
    for what in kinds:
        # he may have tapped this very file himself already: the same file to the same account
        # in the same kind is never sent twice, whatever sent it
        if await tx.scalar(
            SENT_SQL, out=d["ref"], f=str(f["id"]), a=account, k=what, st=[*LIVE, "done"]
        ):
            continue
        sent.append(what)
        j = await _send(
            tx, GROUPS, d, f, cover if what == "reel" else None,
            what=what, account=account, caption=caption if what != "story" else "",
            route=route, order=None, standing=standing,
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
    rule = (
        {"mode": "auto", "account": wanted, "story": bool(story),
         "since": datetime.now(UTC).isoformat(), "by": "owner"}
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
    return (
        "(Publishing: the owner gave this working group his standing permission. If this "
        "routine makes something to publish (a reel, a post), the hub itself publishes its "
        f"package to Instagram{to}{also} when this work is delivered; nobody is asked. The "
        "package is one output that holds the video (`.mp4`), its cover (`cover.jpg`, a JPEG: "
        "Instagram publishes no PNG) and `caption.txt` (the caption with its hashtags, UTF-8, "
        "at most 2200 characters): have the workshop turn (`workshop.run`) that builds the video leave "
        "exactly these in `out/`. Deliver the work only when the package is right; never ask "
        "the owner to approve it. Without `caption.txt` nothing is published. A routine that "
        "makes nothing to publish (a report, an analysis) delivers as usual.)"
    )


async def after_job(hub: Any, job_id: UUID) -> None:
    """The publish job of a session (or ⟨§45⟩ of a standing word) ended, after its result was
    committed: the session says so (the run's note does, and a failure is told to the owner),
    and the company's audit trail keeps it."""
    async with hub.db.tx(await hub.companies.ids()) as tx:
        j = await tx.first(
            """SELECT id, state, args, result, summary_fa, error_code, created_at, finished_at
               FROM infra.server_jobs WHERE id = :id AND kind = 'publish'""",
            id=job_id,
        )
        if j is None:
            return
        args = OR._j(j["args"]) or {}
        s = args.get("session") or {}
        standing = args.get("standing") or {}
        ref = str(s.get("order") or "")
        if not (ref or standing) or j["state"] in LIVE:
            return
        done = view(dict(j))
        kind = KIND_FA.get(str(args.get("kind")), "پست")
        account = str(args.get("account") or "")
        ok = done.state == "published"
        company_id = await tx.scalar(
            "SELECT id FROM core.companies WHERE code = :c", c=str(s.get("company") or "")
        )
        rep = await OR.ensure(tx, ref) if ref else None
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
            run = await tx.first(RUN_BY_ID_SQL, r=str(standing.get("run") or ""))
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
