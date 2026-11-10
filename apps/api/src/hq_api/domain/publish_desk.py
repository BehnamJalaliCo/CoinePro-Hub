"""⟨1.33⟩ §55.2 The publish desk («میز انتشار»): everything that can go out, is set to go out, or
went out, of every company, on one page.

Nothing new is stored: an output's files are the package, the `publish` jobs are the record
(domain.session_publish), and the owner's tap on a card is the same «تأیید و انتشار» of §44.5
(`POST /deliverables/{ref}/publish`). The desk only gathers them:

- `ready`: an output of the last READY_DAYS that carries a video or a picture and has no
  publication that stands (none at all, or only failed and cancelled ones);
- `queue`: a publication IG-Hub holds for its time, or that is on its way, soonest first;
- `done`: what went out, failed or was cancelled in the last DONE_DAYS, newest first.

A report, an analysis or a text has no card: it is nothing to publish, which is no fault.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api.db import Tx
from hq_api.domain import best_hour as BH
from hq_api.domain import order_report as OR
from hq_api.domain import session_publish as SPB
from hq_api.domain.gov_common import owner_tz

READY_DAYS = 14
DONE_DAYS = 7
OUTPUTS = 80
JOBS = 400
SECTION = 30
CAPTION_CHARS = 600

DESK_SQL = """SELECT d.ref, d.title, d.work_id, d.company_id, d.attachments, d.produced_with,
       d.created_at, c.code AS company, c.name_fa AS company_fa, w.ref AS work_ref
FROM cartable.deliverables d JOIN core.companies c ON c.id = d.company_id
JOIN work.work w ON w.id = d.work_id
WHERE (d.created_at > now() - make_interval(days => :days) OR d.ref = ANY(CAST(:refs AS text[])))
  AND (CAST(:co AS uuid) IS NULL OR d.company_id = :co)
  AND cardinality(d.attachments) > 0
ORDER BY d.created_at DESC LIMIT :n"""

DeskState = Literal[
    "ready", "scheduled", "publishing", "published", "failed", "cancelled", "waiting_setup",
    "waiting_seal",
]  # fmt: skip


class DeskFile(BaseModel):
    id: str
    name: str
    mime: str
    size: int


class DeskCard(BaseModel):
    output: str
    title_fa: str
    company: str
    company_fa: str
    order: str | None = None
    group_fa: str | None = None
    file: DeskFile
    cover: DeskFile | None = None
    files: int = 1
    kind: Literal["reel", "post", "story", "carousel"]
    channel: Literal["instagram"] = "instagram"
    account: str | None = None
    accounts: list[str] = Field(default_factory=list)
    route_ready: bool = False
    caption: str | None = None
    state: DeskState
    publish: OR.SessionPublish | None = None
    best: OR.BestHour | None = None
    mode: Literal["ask", "auto"] | None = None
    at: datetime


class PublishDesk(BaseModel):
    ready: list[DeskCard] = Field(default_factory=list)
    queue: list[DeskCard] = Field(default_factory=list)
    done: list[DeskCard] = Field(default_factory=list)


def _file(f: dict[str, Any]) -> DeskFile:
    return DeskFile(
        id=str(f["id"]), name=str(f["name"] or ""), mime=str(f["mime"]), size=int(f["size"] or 0)
    )


def package(files: list[dict[str, Any]]) -> dict[str, Any] | None:
    """What of an output's files would go out, as session_publish.package_of reads a routine's:
    its video with a picture of the same output as the cover (one named `cover…` first); without a
    video, its picture, or its pictures together as a carousel. None: nothing to publish."""
    videos = [f for f in files if str(f["mime"]).startswith("video/")]
    images = [f for f in files if str(f["mime"]).startswith("image/")]
    images.sort(key=lambda f: not str(f["name"] or "").lower().startswith("cover"))
    if videos:
        return {"file": videos[0], "cover": images[0] if images else None, "kind": "reel", "n": 1}
    if len(images) >= 2:
        return {"file": images[0], "cover": None, "kind": "carousel", "n": min(10, len(images))}
    if images:
        return {"file": images[0], "cover": None, "kind": "post", "n": 1}
    return None


async def desk(tx: Tx, hub: Any, company_id: UUID | None = None) -> PublishDesk:
    now = datetime.now(UTC)
    jobs = await tx.all(
        f"""SELECT {SPB.JOB_COLS} FROM infra.server_jobs j
            WHERE j.kind = 'publish' AND j.args -> 'session' ->> 'output' IS NOT NULL
              AND j.created_at > now() - make_interval(days => :days)
            ORDER BY j.created_at DESC LIMIT :n""",  # noqa: S608 - constant columns
        days=READY_DAYS,
        n=JOBS,
    )
    by_output: dict[str, list[OR.SessionPublish]] = {}
    for p in SPB.collapse(jobs, limit=JOBS):
        if p.output:
            by_output.setdefault(p.output, []).append(p)
    refs = list(by_output)
    rows = await tx.all(DESK_SQL, days=READY_DAYS, refs=refs, co=company_id, n=OUTPUTS)
    tz = await owner_tz(tx)
    routes: dict[Any, dict[str, Any]] = {}
    bests: dict[tuple[Any, str], OR.BestHour | None] = {}
    out = PublishDesk()
    for r in rows:
        d = dict(r)
        if (OR._j(d.get("produced_with")) or {}).get("unfinished"):
            continue
        files = [dict(f) for f in await SPB._files(tx, d)]
        pack = package(files)
        if pack is None:
            continue
        co = d["company_id"]
        if co not in routes:
            routes[co] = await SPB._route(tx, co)
        route = routes[co]
        run = await SPB.run_of_work(tx, d["work_id"])
        rule = SPB.rule_of(run["publish"]) if run else None
        pubs = by_output.get(str(d["ref"]), [])
        # the publication of the package's own file stands first; else the output's newest
        mine = [p for p in pubs if p.file_id == str(pack["file"]["id"])] or pubs
        live = next((p for p in mine if p.state not in ("failed", "cancelled")), None)
        shown = live or (mine[0] if mine else None)
        account = (
            (shown.account if shown else None)
            or (rule or {}).get("account")
            or (route["accounts"][0] if len(route["accounts"]) == 1 else None)
        )
        best = None
        if account:
            k = (co, str(account))
            if k not in bests:
                got = await BH.best(tx, co, account, tz)
                bests[k] = got if got.enough else None
            best = bests[k]
        caption = await SPB.caption_of(tx, hub, d)
        card = DeskCard(
            output=str(d["ref"]),
            title_fa=str(d["title"] or ""),
            company=str(d["company"]),
            company_fa=str(d["company_fa"] or d["company"]),
            order=await OR.order_of_work(tx, d["work_id"]),
            group_fa=run["group_fa"] if run else None,
            file=_file(pack["file"]),
            cover=_file(pack["cover"]) if pack["cover"] else None,
            files=int(pack["n"]),
            kind=(shown.kind if shown else pack["kind"]),
            account=str(account) if account else None,
            accounts=list(route["accounts"]),
            route_ready=bool(route["ready"]),
            caption=caption[:CAPTION_CHARS] if caption else None,
            state="ready",
            publish=shown,
            best=best,
            mode=rule["mode"] if rule else None,
            at=d["created_at"],
        )
        if live is None:
            if shown is not None and (shown.at or now) > now - timedelta(days=DONE_DAYS):
                # tried and it did not go out (or he took it back): said in «منتشرشده», and the
                # same output is ready again
                out.done.append(
                    card.model_copy(update={"state": shown.state, "at": shown.at or now})
                )
            if d["created_at"] > now - timedelta(days=READY_DAYS):
                out.ready.append(card.model_copy(update={"publish": None}))
        elif live.state in ("scheduled", "publishing", "waiting_seal", "waiting_setup"):
            when = live.scheduled_at or live.at or now
            out.queue.append(card.model_copy(update={"state": live.state, "at": when}))
        elif (live.published_at or live.at or now) > now - timedelta(days=DONE_DAYS):
            when = live.published_at or live.at or now
            out.done.append(card.model_copy(update={"state": live.state, "at": when}))
    out.ready = out.ready[:SECTION]
    out.queue = sorted(out.queue, key=lambda c: c.at)[:SECTION]
    out.done = sorted(out.done, key=lambda c: c.at, reverse=True)[:SECTION]
    return out
