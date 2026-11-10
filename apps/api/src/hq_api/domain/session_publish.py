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
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from hq_api import audit
from hq_api.db import Tx
from hq_api.domain import connections as CN
from hq_api.domain import humanize as HZ
from hq_api.domain import order_report as OR
from hq_api.domain import servers as SV
from hq_api.errors import ApiError
from hq_api.principal import Principal

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
        kind=args.get("kind") if args.get("kind") in KIND_FA else "post",
        account=args.get("account"),
        state=state,
        url=url if url and url.startswith(("https://", "http://")) else None,
        note_fa=note,
        at=j.get("created_at"),
        published_at=j.get("finished_at") if state == "published" else None,
    )


JOB_SQL = """SELECT j.id, j.state, j.args, j.result, j.summary_fa, j.created_at, j.finished_at
             FROM infra.server_jobs j
             WHERE j.kind = 'publish' AND j.args -> 'session' ->> 'order' = :ref"""


async def of_order(tx: Tx, ref: str) -> list[SessionPublish]:
    """The session's publishes, newest first (the jobs are the record)."""
    rows = await tx.all(JOB_SQL + " ORDER BY j.created_at DESC LIMIT 20", ref=ref)
    return [view(dict(r)) for r in rows]


async def start(
    tx: Tx,
    who: Principal,
    ref: str,
    *,
    output: str,
    file_id: UUID,
    kind: Kind | None = None,
    caption: str | None = None,
    account: str | None = None,
    request_id: str | None = None,
) -> SessionPublish:
    """The owner's tap. `tx` reaches every company (the session is the holding's, the file is
    its company's, the job is IG-Hub's)."""
    rep = await OR.ensure(tx, ref)
    order = await OR.load_order(tx, ref) if rep is not None else None
    if rep is None or order is None:
        raise ApiError(404, "not_found", f"order {ref}")
    works = await OR.tree(tx, OR.root_refs(order))
    d = await tx.first(
        """SELECT d.ref, d.title, d.work_id, d.company_id, d.attachments, c.code AS company,
                  c.name_fa AS company_fa, w.ref AS work_ref
           FROM cartable.deliverables d JOIN core.companies c ON c.id = d.company_id
           JOIN work.work w ON w.id = d.work_id
           WHERE d.ref = :r AND d.work_id = ANY(:ids)""",
        r=output,
        ids=[w["id"] for w in works],
    )
    if d is None:
        raise ApiError(404, "not_found", f"output {output} of {ref}")
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
    if await tx.scalar("SELECT control.lock_state(:co)", co=d["company_id"]) is not None:
        raise ApiError(423, "company_locked")

    conn = await tx.first(
        "SELECT config FROM growth.connections WHERE company_id = :co AND kind = 'instagram'",
        co=d["company_id"],
    )
    cfg = _cfg(conn)
    hubs = CN.ig_hub()
    srv = cfg.get("server") if isinstance(cfg.get("server"), dict) else {}
    server_co = str((srv or {}).get("company") or hubs["company"])
    server_name = str((srv or {}).get("name") or hubs["server"])
    accounts = [str(a).lstrip("@") for a in cfg.get("accounts") or []]
    command = str(cfg.get("publish_command") or "").strip()
    company_fa = str(d["company_fa"] or d["company"])
    if not accounts or not command:
        # never the owner's step: the holding's technical team registers it, once, under the order
        made = await CN.ensure_ig_publish_work(tx, d["company_id"], requested_by=d["work_id"])
        say = (SETUP_FA if made else SETUP_NOBODY_FA).format(company=company_fa, server=server_name)
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

    # one tap, one post: the same file to the same account is not sent twice
    before = await tx.first(
        JOB_SQL
        + """ AND j.args -> 'session' ->> 'file_id' = :f AND j.args ->> 'account' = :a
              AND j.args ->> 'kind' = :k AND j.state = ANY(:st) ORDER BY j.created_at DESC LIMIT 1""",
        ref=ref,
        f=str(file_id),
        a=wanted,
        k=what,
        st=[*LIVE, "done"],
    )
    if before is not None:
        return view(dict(before))

    server = await SV.load_server(tx, server_name, company=server_co)
    j = await SV.create_job(
        tx,
        server=server,
        kind="publish",
        args={
            "session": {
                "order": ref,
                "output": d["ref"],
                "work": d["work_ref"],
                "company": d["company"],
                "file_id": str(file_id),
            },
            "kind": what,
            "placement": f"instagram_{what}",
            "account": wanted,
            "command": command,
            "caption": (caption or "").strip()[:CAPTION_MAX],
            "title_fa": str(d["title"])[:200],
            "meta": {
                "channel": "instagram",
                "kind": what,
                "account": wanted,
                "company": d["company"],
            },
            "files": [{"file_id": str(f["id"]), "name": f["name"], "mime": mime, "kind": media}],
        },
        actor_kind=who.kind,
        actor_code=who.code,
        work_ref=str(d["work_ref"]),
        summary=f"انتشار {KIND_FA[what]} در @{wanted} از جلسه‌ی {ref}",
        timeout_s=TIMEOUT_S,
        request_id=request_id,
    )
    await OR._append_steps(
        tx,
        rep["id"],
        [_line(OWNER_FA, TAPPED_FA.format(kind=KIND_FA[what], name=f["name"], account=wanted))],
    )
    for co_id in dict.fromkeys((d["company_id"], server["company_id"])):
        await audit.record(
            tx,
            who,
            company_id=co_id,
            action="publish.session",
            action_class="A3",
            target_kind="order",
            target_ref=ref,
            summary=f"the owner's «تأیید و انتشار» in {ref}: {what} {f['name']} of {d['ref']} to "
            f"@{wanted} ({d['company']}) through {server_co}:{server_name}; job {j['id']}"[:500],
            request_id=request_id,
        )
    row = await tx.one(
        """SELECT id, state, args, result, summary_fa, created_at, finished_at
           FROM infra.server_jobs WHERE id = :id""",
        id=j["id"],
    )
    return view(dict(row))


async def after_job(hub: Any, job_id: UUID) -> None:
    """The publish job of a session ended (after its result was committed): the session says
    so, and the company's audit trail keeps it."""
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
        ref = str(s.get("order") or "")
        if not ref or j["state"] in LIVE:
            return
        done = view(dict(j))
        kind = KIND_FA.get(str(args.get("kind")), "پست")
        account = str(args.get("account") or "")
        ok = done.state == "published"
        rep = await OR.ensure(tx, ref)
        if rep is not None:
            if ok:
                say = DONE_FA.format(kind=kind, account=account)
                say += f" · {done.url}" if done.url else ""
            else:
                say = FAILED_FA.format(kind=kind, account=account, why=done.note_fa or "-")
            await OR._append_steps(tx, rep["id"], [_line(SYSTEM_FA, say)])
        company_id = await tx.scalar(
            "SELECT id FROM core.companies WHERE code = :c", c=str(s.get("company") or "")
        )
        if company_id is not None:
            outcome = (
                f"published {done.url or ''}" if ok else f"failed ({j['error_code'] or j['state']})"
            )
            await audit.record(
                tx,
                SERVICE,
                company_id=company_id,
                action="publish.session_done" if ok else "publish.session_failed",
                action_class="A1",
                target_kind="order",
                target_ref=ref,
                summary=f"{args.get('kind')} to @{account} from {ref}: {outcome}"[:500],
            )
