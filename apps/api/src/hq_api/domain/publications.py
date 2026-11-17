"""⟨1.39⟩ Contract §60 (prompt 39): the publish centre, every publication kept for good.

One permanent row of `media.publications` per publication chain (§55.4): the `publish` job that
sent it and every later question (`meta.check`, §46) and cancel (`meta.cancel`, §51) of the same
file, account and kind. Nothing here publishes: the row is written where every publication passes
(`session_publish._send`, in the job's own transaction) and follows IG-Hub's answers:

    record    the row, with the job (a session's tap, a working group's standing word, a flow's
              reel and story, each slide of a stories flow with its set)
    apply     every job of the chain, as it is made and as it ends: the row's state, link, note
    backfill  one row per chain of every `publish` job there is (any state), from the jobs, the
              files, the topics and a flow's run where it still is; what is missing stays null

The texts are the job's own (`caption`, `meta.comment`, `meta.story_rule`); the title is the topic
(the flow's day, `growth.topics`, the session's), else the caption's first line, never a file name.
`search_fa` folds every searchable text through hq_common.persian, so «بلاکچین», «بلاک چین» and
«بلاک‌چین» are one key (pg_trgm's GIN index serves the LIKE).

The routes of §60.2 read only these rows (and, for what is still to be made, the flows through
`planned_today`, the one place their definitions are read here).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import tempfile
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import order_report as OR
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_common import persian

log = logging.getLogger("hq_api.publications")

SERVICE = Principal(kind="service", code="publications", role="service")
TEHRAN = "Asia/Tehran"
Channel = Literal["instagram", "youtube", "telegram", "website"]
PubKind = Literal["reel", "story", "post", "carousel", "short", "video", "tg_post", "article"]
PubState = Literal["scheduled", "publishing", "published", "held", "failed", "cancelled"]
Role = Literal["video", "cover", "slide", "image", "thumb"]
Match = Literal["title", "topic", "caption", "word"]
KIND_FA = {"reel": "ریلز", "story": "استوری", "post": "پست", "carousel": "اسلاید", "short": "شورت",
           "video": "ویدیو", "tg_post": "پست تلگرام", "article": "مقاله"}  # fmt: skip
HELD_FA = "صفحه بسته است؛ به محض باز شدن پیج میرود"
TITLE_MAX = 80
SNIPPET_MAX = 80
CAPTION_MAX = 5000
THUMB_WIDTH = 540
THUMB_AT_S = 1.0
THUMB_LIMIT_S = 30.0
TOPIC_TREE_DAYS = 30
LIST_LIMIT = 30
LIST_MAX = 100
CALENDAR_DEFAULT = 14
CALENDAR_MAX = 62
COUNTED = ("published", "scheduled", "held", "failed")
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
ARABIC = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})


# ------------------------------------------------------------------ shapes --
class PubFile(BaseModel):
    role: Role
    file_id: str
    name: str | None = None
    mime: str | None = None
    size: int | None = None
    n: int | None = None


class Button(BaseModel):
    title: str
    url: str


class PubComment(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    match: str | None = None
    reply: str | None = None
    link: str | None = None
    buttons: list[Button] = Field(default_factory=list)
    public_replies: list[str] = Field(default_factory=list)


class PubSeo(BaseModel):
    slug: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    canonical: str | None = None


class SetItem(BaseModel):
    ref: str
    n: int | None = None
    at: datetime
    state: PubState
    file_id: str | None = None


class PubSource(BaseModel):
    automation: str | None = None
    automation_fa: str | None = None
    flow_key: str | None = None
    version: int | None = None
    day: date | None = None
    order: str | None = None
    work: str | None = None
    output: str | None = None
    session: str | None = None
    job_id: str


class Insights(BaseModel):
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    dms: int | None = None
    best_hour: str | None = None
    updated_at: datetime | None = None


class Publication(BaseModel):
    ref: str
    company: str
    company_fa: str
    channel: Channel
    account: str
    kind: PubKind
    state: PubState
    state_note_fa: str | None = None
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    at: datetime
    url: str | None = None
    external_id: str | None = None
    title_fa: str
    topic_fa: str | None = None
    caption: str | None = None
    comment: PubComment | None = None
    story_word: str | None = None
    seo: PubSeo | None = None
    files: list[PubFile] = Field(default_factory=list)
    thumb_file_id: str | None = None
    set_key: str | None = None
    set: list[SetItem] | None = None
    source: PubSource
    insights: Insights | None = None
    created_at: datetime
    updated_at: datetime


class CardSet(BaseModel):
    n: int
    done: int
    next_at: datetime | None = None


class PublicationCard(BaseModel):
    ref: str
    company: str
    company_fa: str
    channel: Channel
    account: str
    kind: PubKind
    state: PubState
    state_note_fa: str | None = None
    at: datetime
    title_fa: str
    thumb_file_id: str | None = None
    files_n: int = 0
    url: str | None = None
    set_key: str | None = None
    set: CardSet | None = None
    automation: str | None = None
    automation_fa: str | None = None
    # with `q`: where the words were found and the words around them (≤ 80 characters)
    match: Match | None = None
    snippet_fa: str | None = None


class PlannedItem(BaseModel):
    automation: str
    automation_fa: str
    account: str
    kind: PubKind
    title_fa: str
    build_at: datetime
    publish_at: datetime
    state: Literal["planned", "building"]


class TodayCounts(BaseModel):
    published: int = 0
    scheduled: int = 0
    held: int = 0
    failed: int = 0


class PublishToday(BaseModel):
    day: date
    items: list[PublicationCard] = Field(default_factory=list)
    planned: list[PlannedItem] = Field(default_factory=list)
    next: PublicationCard | None = None
    counts: TodayCounts = Field(default_factory=TodayCounts)


class TreeAccount(BaseModel):
    channel: Channel
    account: str
    avatar_file_id: str | None = None
    total: int
    by_kind: dict[str, int] = Field(default_factory=dict)
    automations: int = 0


class TreeCompany(BaseModel):
    code: str
    name_fa: str
    mark_file_id: str | None = None
    total: int
    accounts: list[TreeAccount] = Field(default_factory=list)


class PublishTree(BaseModel):
    companies: list[TreeCompany] = Field(default_factory=list)


class PublicationPage(BaseModel):
    items: list[PublicationCard] = Field(default_factory=list)
    next: str | None = None


class CalendarDay(BaseModel):
    day: date
    published: int = 0
    scheduled: int = 0
    held: int = 0
    failed: int = 0
    planned: int = 0
    accounts: list[str] = Field(default_factory=list)


class PublishCalendar(BaseModel):
    days: list[CalendarDay] = Field(default_factory=list)


class WaitingAction(BaseModel):
    key: str
    label_fa: str
    primary: bool = False


class Waiting(BaseModel):
    id: str
    kind: Literal["publish_ask", "budget_cap"]
    title_fa: str
    account: str | None = None
    at: datetime
    deadline_at: datetime | None = None
    publication: PublicationCard | None = None
    actions: list[WaitingAction] = Field(default_factory=list)


class WaitingList(BaseModel):
    items: list[Waiting] = Field(default_factory=list)


class WaitingIn(BaseModel):
    """`raise_cap`: the day's new cap (USD, 1 to 500)."""

    usd_cap: Decimal | None = Field(default=None, ge=1, le=500)


# ------------------------------------------------------------- the search --
def fold(text: str | None) -> str:
    """A text as the search compares it (hq_common.persian's words, ZWNJ and spaces dropped,
    Arabic ی/ک and every digit as Persian writes them read the same)."""
    if not text:
        return ""
    return "".join(persian.words(str(text).translate(DIGITS)))


def _fold_char(c: str) -> str:
    c = c.translate(ARABIC).translate(DIGITS).lower()
    return c if (c.isalnum() or c == "_") else ""


def snippet(text: str, q: str) -> str | None:
    """≤ SNIPPET_MAX characters of `text` around the first place `q` (folded) is found."""
    key = fold(q)
    if not key or not text:
        return None
    chars: list[str] = []
    where: list[int] = []
    for i, c in enumerate(text):
        f = _fold_char(c)
        for x in f:
            chars.append(x)
            where.append(i)
    at = "".join(chars).find(key)
    if at < 0:
        return None
    start, end = where[at], where[at + len(key) - 1] + 1
    room = max(0, SNIPPET_MAX - (end - start))
    lo = max(0, start - room // 2)
    hi = min(len(text), lo + SNIPPET_MAX)
    lo = max(0, hi - SNIPPET_MAX)
    out = " ".join(text[lo:hi].split())
    return out[:SNIPPET_MAX] or None


def search_of(
    title: str | None, topic: str | None, caption: str | None, words: list[str], story: str | None
) -> str:
    """The row's `search_fa`: each text folded, apart (a space never folds in)."""
    parts = [fold(title), fold(topic), fold(caption), *(fold(w) for w in words), fold(story)]
    return " ".join(p for p in parts if p)[:20000]


def first_line(text: str | None) -> str | None:
    for line in str(text or "").splitlines():
        line = " ".join(line.split())
        if line:
            return line[:TITLE_MAX]
    return None


def title_of(
    topic: str | None, session_topic: str | None, caption: str | None, kind: str, account: str
) -> str:
    """§60.1: the topic, then the session's topic, then the caption's first line (≤ 80); never a
    file name. With none of them: the kind and the page."""
    for x in (topic, session_topic):
        got = first_line(x)
        if got:
            return got
    return first_line(caption) or f"{KIND_FA.get(kind, 'انتشار')} در @{account}"[:TITLE_MAX]


# ------------------------------------------------------------- the record --
JOB_COLS = (
    "j.id, j.state, j.args, j.result, j.summary_fa, j.error_code, j.created_at, j.finished_at, "
    "j.actor_kind, j.actor_code"
)
JOB_SQL = f"SELECT {JOB_COLS} FROM infra.server_jobs j WHERE j.id = :id AND j.kind = 'publish'"  # noqa: S608


def _j(v: Any) -> Any:
    return OR._j(v)


def _asks(args: dict[str, Any]) -> bool:
    meta = args.get("meta") or {}
    return bool(meta.get("check") or meta.get("cancel"))


def comment_of(rule: Any) -> dict[str, Any] | None:
    """A rule of the job (`meta.comment`, `meta.story_rule`) in §60.1's shape."""
    if not isinstance(rule, dict) or not rule:
        return None
    buttons = [
        {"title": str(b.get("title") or "")[:40], "url": str(b.get("url") or "")[:500]}
        for b in rule.get("buttons") or []
        if isinstance(b, dict) and b.get("url")
    ]
    return {
        "keywords": [str(k)[:100] for k in rule.get("keywords") or [] if str(k).strip()][:50],
        "match": str(rule["match"])[:40] if rule.get("match") else None,
        "reply": str(rule["reply"])[:4000] if rule.get("reply") else None,
        "link": str(rule["link"])[:500] if rule.get("link") else None,
        "buttons": buttons[:10],
        "public_replies": [
            str(x)[:500] for x in rule.get("public_replies") or [] if str(x).strip()
        ][:30],
    }


def _roles(args: dict[str, Any], set_n: int | None) -> list[dict[str, Any]]:
    """The job's files with their roles (§60.1): a reel's video and cover, a story's video or its
    picture (a slide of a set), a post's picture, a carousel's slides in order."""
    kind = str(args.get("kind") or "")
    out: list[dict[str, Any]] = []
    pos = 0
    for x in args.get("files") or []:
        if not isinstance(x, dict) or not x.get("file_id"):
            continue
        mime = str(x.get("mime") or "")
        if x.get("role") == "cover":
            role, n = "cover", None
        elif mime.startswith("video/"):
            role, n = "video", None
        elif kind == "carousel":
            pos += 1
            role, n = "slide", pos
        elif kind == "story" and set_n is not None:
            role, n = "slide", set_n
        else:
            role, n = "image", None
        out.append({"role": role, "file_id": str(x["file_id"]), "name": x.get("name"),
                    "mime": mime or None, "size": None, "n": n})  # fmt: skip
    return out


async def _sizes(tx: Tx, files: list[dict[str, Any]]) -> None:
    ids = [f["file_id"] for f in files]
    if not ids:
        return
    rows = await tx.all(
        "SELECT id::text AS id, name, mime, size FROM files.files WHERE id = ANY(CAST(:ids AS uuid[]))",
        ids=ids,
    )
    got = {str(r["id"]): r for r in rows}
    for f in files:
        r = got.get(f["file_id"])
        if r is not None:
            f["size"] = int(r["size"] or 0)
            f["name"] = f["name"] or r["name"]
            f["mime"] = f["mime"] or r["mime"]


async def automation_of(tx: Tx, flow_key: str) -> tuple[str, str | None, int | None]:
    """A code flow's ref, name and version: §61's row (`automations.flows`) once it is there, else
    `N8:<key>` and the code's own name."""
    if await tx.scalar("SELECT to_regclass('automations.flows') IS NOT NULL"):
        row = await tx.first(
            "SELECT ref, title_fa, version FROM automations.flows WHERE key = :k", k=flow_key
        )
        if row is not None:
            return str(row["ref"]), row["title_fa"], int(row["version"] or 1)
    from hq_api.domain import flows as FL

    flow = FL.FLOWS.get(flow_key)
    return f"N8:{flow_key}", flow.title_fa if flow else None, None


async def _flow_meta(tx: Tx, work_ref: str | None) -> dict[str, Any]:
    """A code flow's run (`work.work.run_meta.flow`), where its work still is."""
    if not work_ref:
        return {}
    got = await tx.scalar(
        "SELECT run_meta -> 'flow' FROM work.work WHERE ref = :w AND run_meta ? 'flow'", w=work_ref
    )
    return dict(_j(got) or {})


async def _topic(tx: Tx, order: str | None, before: datetime | None) -> str | None:
    if not order:
        return None
    got = await tx.scalar(
        """SELECT title_fa FROM growth.topics WHERE order_ref = :o AND kind = 'topic'
             AND (CAST(:t AS timestamptz) IS NULL OR created_at <= CAST(:t AS timestamptz) + interval '1 day')
           ORDER BY created_at DESC LIMIT 1""",
        o=order,
        t=before,
    )
    return str(got) if got else None


async def _session_topic(tx: Tx, order: str | None) -> str | None:
    if not order:
        return None
    got = await tx.scalar("SELECT summary_fa FROM owner.orders WHERE ref = :o", o=order)
    return str(got) if got else None


async def _source(
    tx: Tx, j: dict[str, Any], args: dict[str, Any], extra: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """§60.1 `source`, and the flow's run it came from ({} when none)."""
    s = args.get("session") or {}
    flow = await _flow_meta(tx, s.get("work"))
    key = extra.get("flow_key") or flow.get("key")
    automation, automation_fa, version = extra.get("automation"), extra.get("automation_fa"), None
    standing = args.get("standing") or {}
    line = args.get("flow") or {}
    if key and not automation:
        automation, automation_fa, version = await automation_of(tx, str(key))
    elif standing.get("group") and not automation:
        automation = f"SP:{standing['group']}:{s.get('company') or ''}"
        automation_fa = await tx.scalar(
            "SELECT title_fa FROM growth.groups WHERE key = :k", k=str(standing["group"])
        )
    elif line.get("automation") and not automation:
        automation = str(line["automation"])
        automation_fa = await tx.scalar(
            "SELECT coalesce(title_fa, sentence_fa) FROM growth.automations WHERE ref = :r",
            r=automation,
        )
    order = s.get("order")
    by_owner = str(j.get("actor_kind") or "") == "owner"
    day = extra.get("day") or flow.get("day")
    return {
        "automation": automation,
        "automation_fa": automation_fa,
        "flow_key": key,
        "version": extra.get("version") or version,
        "day": str(day) if day else None,
        "order": order,
        "work": s.get("work"),
        "output": s.get("output"),
        "session": order if by_owner and order else None,
        "job_id": str(j["id"]),
    }, flow


async def _values(
    tx: Tx, j: dict[str, Any], chain: list[str], extra: dict[str, Any] | None
) -> dict[str, Any] | None:
    """The row of a chain from its first job (`j`), as the job carried it."""
    extra = dict(extra or {})
    args = _j(j["args"]) or {}
    s = args.get("session") or {}
    account = str(args.get("account") or "").lstrip("@")
    kind = str(args.get("kind") or "")
    company = str(s.get("company") or (args.get("meta") or {}).get("company") or "")
    co = await tx.first("SELECT id, code FROM core.companies WHERE code = :c", c=company)
    if not account or kind not in KIND_FA or co is None:
        return None
    meta = args.get("meta") or {}
    source, _flow = await _source(tx, j, args, extra)
    set_key, set_n = extra.get("set_key"), extra.get("n")
    caption = str(args.get("caption") or "").strip()[:CAPTION_MAX] or None
    rule = meta.get("comment") if kind != "story" else meta.get("story_rule")
    comment = comment_of(rule or meta.get("comment"))
    words = (comment or {}).get("keywords") or []
    story_word = str(words[0]) if kind == "story" and words else None
    topic = extra.get("topic_fa") or await _topic(tx, s.get("order"), j.get("created_at"))
    title = title_of(topic, await _session_topic(tx, s.get("order")), caption, kind, account)
    files = _roles(args, int(set_n) if set_n else None)
    await _sizes(tx, files)
    thumb = next((f["file_id"] for f in files if f["role"] == "cover"), None) or next(
        (f["file_id"] for f in files if f["role"] in ("image", "slide")), None
    )
    return {
        "company_id": co["id"],
        "company": str(co["code"]),
        "channel": str(meta.get("channel") or "instagram"),
        "account": account[:200],
        "kind": kind,
        "scheduled_at": _when(meta.get("scheduled_at")),
        "title_fa": title,
        "topic_fa": first_line(topic) if topic else None,
        "caption": caption,
        "comment": comment,
        "story_word": story_word,
        "files": files,
        "thumb_file_id": thumb,
        "set_key": set_key,
        "set_n": int(set_n) if set_n else None,
        "source": source,
        "chain": chain,
        "search_fa": search_of(title, topic, caption, words, story_word),
        "created_at": j.get("created_at"),
    }


def _when(raw: Any) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return t if t.tzinfo is not None else None


INSERT_SQL = """INSERT INTO media.publications
    (company_id, channel, account, kind, state, state_note_fa, scheduled_at, published_at, url,
     external_id, title_fa, topic_fa, caption, comment, story_word, files, thumb_file_id, set_key,
     set_n, source, chain, search_fa, created_at)
VALUES (:co, :channel, :account, :kind, :state, :note, :scheduled_at, :published_at, :url, :ext,
        :title, :topic, :caption, CAST(:comment AS jsonb), :story_word, CAST(:files AS jsonb),
        CAST(:thumb AS uuid), :set_key, :set_n, CAST(:source AS jsonb), CAST(:chain AS uuid[]),
        :search, COALESCE(CAST(:created_at AS timestamptz), now()))
ON CONFLICT ((chain[1])) DO NOTHING
RETURNING id"""


async def _insert(tx: Tx, v: dict[str, Any], state: dict[str, Any]) -> UUID | None:
    got: UUID | None = await tx.scalar(
        INSERT_SQL,
        co=v["company_id"],
        channel=v["channel"],
        account=v["account"],
        kind=v["kind"],
        state=state["state"],
        note=state["note"],
        scheduled_at=v["scheduled_at"],
        published_at=state["published_at"],
        url=state["url"],
        ext=state["external_id"],
        title=v["title_fa"],
        topic=v["topic_fa"],
        caption=v["caption"],
        comment=json.dumps(v["comment"], ensure_ascii=False) if v["comment"] else None,
        story_word=v["story_word"],
        files=json.dumps(v["files"], ensure_ascii=False),
        thumb=v["thumb_file_id"],
        set_key=v["set_key"],
        set_n=v["set_n"],
        source=json.dumps(v["source"], ensure_ascii=False, default=str),
        chain=v["chain"],
        search=v["search_fa"],
        created_at=v["created_at"],
    )
    return got


def state_of(j: dict[str, Any], before: dict[str, Any] | None) -> dict[str, Any]:
    """Where the publication stands after this job of its chain (§60.1 states), from the same
    reading the session uses (session_publish.view). A question still on its way, or one never
    answered, leaves it as it stood; a page IG-Hub holds closed is `held`."""
    from hq_api.domain import session_publish as SPB

    args = _j(j["args"]) or {}
    meta = args.get("meta") or {}
    result = _j(j.get("result")) or {}
    v = SPB.view(j)
    st = str(j["state"])
    out: dict[str, Any] = {
        "state": v.state, "note": v.note_fa, "url": v.url, "published_at": None,
        "external_id": str(result.get("external_id") or "")[:200] or None,
        "scheduled_at": v.scheduled_at,
    }  # fmt: skip
    if v.state in ("waiting_seal", "waiting_setup"):
        out["state"] = "publishing"
    soon = datetime.now(UTC) + timedelta(minutes=2)
    if out["state"] == "publishing" and v.scheduled_at is not None and v.scheduled_at > soon:
        out["state"] = "scheduled"  # set for its hour from the moment it is made (IG-Hub holds it)
    if v.state == "published":
        out["published_at"] = j.get("finished_at") or datetime.now(UTC)
        out["note"] = None
    if v.state == "cancelled":
        out["note"] = None
    if out["state"] in ("scheduled", "publishing"):
        if result.get("held") and st == "done":
            out["state"], out["note"] = "held", HELD_FA
        elif _asks(args) and st != "done" and before is not None:
            # a question on its way or never answered, or a cancel IG-Hub refused: as it stood
            out["state"] = before["state"]
            if not meta.get("cancel"):
                out["note"] = before.get("state_note_fa")
    if before is not None:
        out["url"] = out["url"] or before.get("url")
        out["external_id"] = out["external_id"] or before.get("external_id")
        out["published_at"] = out["published_at"] or (
            before.get("published_at") if out["state"] == "published" else None
        )
    return out


async def _emit(tx: Tx, row: dict[str, Any]) -> None:
    """§60.4 `publication.updated` on every change of a row."""
    company = await tx.scalar("SELECT code FROM core.companies WHERE id = :c", c=row["company_id"])
    at = row.get("at") or row.get("published_at") or row.get("scheduled_at") or row["created_at"]
    await events.emit(
        tx,
        str(company),
        "publication.updated",
        str(row["ref"]),
        {"ref": row["ref"], "state": row["state"], "at": at, "company": str(company),
         "account": row["account"], "kind": row["kind"], "set_key": row.get("set_key")},
    )  # fmt: skip


async def record(tx: Tx, job_id: UUID, extra: dict[str, Any] | None = None) -> str | None:
    """The row of a publication made now (its first job), in the job's transaction. Answers its
    ref (None: not a publication of a page, or recorded already)."""
    row = await tx.first(JOB_SQL, id=job_id)
    if row is None:
        return None
    j = dict(row)
    args = _j(j["args"]) or {}
    if args.get("rule_for") or not args.get("session") or _asks(args):
        return None
    v = await _values(tx, j, [str(j["id"])], extra)
    if v is None:
        return None
    st = state_of(j, None)
    v["scheduled_at"] = v["scheduled_at"] or st["scheduled_at"]
    made = await _insert(tx, v, st)
    if made is None:
        return None
    got = await tx.one("SELECT * FROM media.publications WHERE id = :id", id=made)
    await _emit(tx, dict(got))
    return str(got["ref"])


CHAIN_ROW_SQL = """SELECT p.* FROM media.publications p JOIN infra.server_jobs f ON f.id = p.chain[1]
WHERE f.kind = 'publish' AND f.args -> 'session' ->> 'output' = :o
  AND f.args -> 'session' ->> 'file_id' = :f AND f.args ->> 'account' = :a AND f.args ->> 'kind' = :k
  AND f.created_at <= :t
ORDER BY f.created_at DESC LIMIT 1"""


async def _row_of_job(tx: Tx, j: dict[str, Any]) -> dict[str, Any] | None:
    from hq_api.domain import session_publish as SPB

    row = await tx.first(
        "SELECT * FROM media.publications WHERE chain @> ARRAY[CAST(:id AS uuid)] FOR UPDATE",
        id=str(j["id"]),
    )
    if row is not None:
        return dict(row)
    args = _j(j["args"]) or {}
    if not _asks(args):
        return None
    o, f, a, k = SPB.publication_of(j)
    row = await tx.first(CHAIN_ROW_SQL, o=o, f=f, a=a, k=k, t=j["created_at"])
    if row is None:
        return None
    await tx.exec(
        """UPDATE media.publications SET chain = array_append(chain, CAST(:id AS uuid))
           WHERE id = :p AND NOT chain @> ARRAY[CAST(:id AS uuid)]""",
        id=str(j["id"]),
        p=row["id"],
    )
    return dict(
        await tx.one("SELECT * FROM media.publications WHERE id = :p FOR UPDATE", p=row["id"])
    )


async def apply(tx: Tx, job_id: UUID) -> str | None:
    """A job of a chain was made or ended (a question, a cancel, IG-Hub's answer): the chain's row
    follows it. A first job without a row (made before §60, or its recording failed) gets one
    now. Answers the row's ref."""
    got = await tx.first(JOB_SQL, id=job_id)
    if got is None:
        return None
    j = dict(got)
    args = _j(j["args"]) or {}
    if args.get("rule_for") or not args.get("session"):
        return None
    row = await _row_of_job(tx, j)
    if row is None:
        if _asks(args):
            return None
        return await record(tx, job_id)
    newest = await tx.scalar(
        """SELECT id FROM infra.server_jobs WHERE id = ANY(CAST(:c AS uuid[]))
           ORDER BY created_at DESC LIMIT 1""",
        c=[str(x) for x in row["chain"]],
    )
    if newest is not None and str(newest) != str(j["id"]):
        return str(row["ref"])  # an older job of the chain: the newest one says where it stands
    st = state_of(j, row)
    sched = st["scheduled_at"] or row["scheduled_at"]
    same = (
        st["state"] == row["state"] and st["note"] == row["state_note_fa"] and st["url"] == row["url"]
        and st["published_at"] == row["published_at"] and sched == row["scheduled_at"]
        and st["external_id"] == row["external_id"]
    )  # fmt: skip
    if same:
        return str(row["ref"])
    await tx.exec(
        """UPDATE media.publications SET state = :s, state_note_fa = :n, url = :u,
               published_at = :p, scheduled_at = :sc, external_id = :e WHERE id = :id""",
        s=st["state"],
        n=(st["note"] or None) and str(st["note"])[:500],
        u=st["url"],
        p=st["published_at"],
        sc=sched,
        e=st["external_id"],
        id=row["id"],
    )
    now = await tx.one("SELECT * FROM media.publications WHERE id = :id", id=row["id"])
    await _emit(tx, dict(now))
    return str(row["ref"])


async def on_job(hub: Any, job_id: UUID) -> None:
    """After a chain's job ended (committed): its row follows, then a reel without a cover gets its
    frame. Never raises."""
    ref = None
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            ref = await apply(tx, job_id)
    except Exception:  # noqa: BLE001 - the publication's end never fails on its record
        log.warning("the publication's row did not follow its job", extra={"job": str(job_id)})
    if ref is not None:
        await make_thumb(hub, ref)


# ------------------------------------------------------------- the frame --
async def make_thumb(hub: Any, ref: str) -> str | None:
    """§60.1 a video without a cover: its frame at 1 s (JPEG, 540 wide), made once, a file of the
    same company; the row's `thumb` file. Never raises (no frame: the app shows the kind)."""
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            row = await tx.first(
                "SELECT id, company_id, files, thumb_file_id FROM media.publications WHERE ref = :r",
                r=ref,
            )
            if row is None or row["thumb_file_id"] is not None:
                return None
            video = next((f for f in _j(row["files"]) or [] if f.get("role") == "video"), None)
            if video is None:
                return None
            made = await tx.scalar(
                """SELECT id FROM files.files WHERE company_id = :co AND meta ->> 'thumb_of' = :v
                   ORDER BY created_at LIMIT 1""",
                co=row["company_id"],
                v=str(video["file_id"]),
            )
            key = await tx.scalar(
                "SELECT storage_key FROM files.files WHERE id = CAST(:v AS uuid)",
                v=str(video["file_id"]),
            )
        if made is None:
            made = await _new_thumb(hub, row["company_id"], video, key)
        if made is None:
            return None
        async with hub.db.tx(await hub.companies.ids()) as tx:
            files = [f for f in _j(row["files"]) or [] if f.get("role") != "thumb"]
            files.append({"role": "thumb", "file_id": str(made), "name": None, "mime": "image/jpeg",
                          "size": None, "n": None})  # fmt: skip
            await _sizes(tx, files)
            done = await tx.first(
                """UPDATE media.publications SET thumb_file_id = CAST(:t AS uuid),
                       files = CAST(:f AS jsonb)
                   WHERE id = :id AND thumb_file_id IS NULL RETURNING *""",
                t=str(made),
                f=json.dumps(files, ensure_ascii=False),
                id=row["id"],
            )
            if done is not None:
                await _emit(tx, dict(done))
        return str(made)
    except Exception:  # no frame is no fault
        log.info("no frame for the publication", extra={"ref": ref}, exc_info=True)
        return None


async def _new_thumb(hub: Any, company_id: UUID, video: dict[str, Any], key: Any) -> UUID | None:
    """The frame made and kept (outside any transaction while ffmpeg runs)."""
    if not key:
        return None
    got = await frame(str(hub.storage.local_path(str(key))))
    if got is None:
        return None
    data, width, height = got
    new_key, sha = await hub.storage.put(data)
    from hq_api.domain import files as F

    stem = str(video.get("name") or "video").rsplit(".", 1)[0][:200] or "video"
    async with hub.db.tx(await hub.companies.ids()) as tx:
        made: UUID = await F.insert(
            tx, company_id=company_id, name=f"{stem}-thumb.jpg", mime="image/jpeg",
            size=len(data), sha256=sha, storage_key=new_key, kind="image",
            by_kind="service", by_code=SERVICE.code, width=width, height=height,
            frame_at_s=THUMB_AT_S, meta={"thumb_of": str(video["file_id"])},
        )  # fmt: skip
    return made


async def frame(path: str) -> tuple[bytes, int, int] | None:
    """The frame at 1 s of a local video (ffmpeg, the same guarded input as every media call),
    JPEG, THUMB_WIDTH wide; None when it cannot be read."""
    from hq_api import media

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "thumb.jpg"
        code, _, _ = await media.run_tool(
            "ffmpeg", "-nostdin", "-v", "error", "-threads", media.FF_THREADS,
            "-ss", str(THUMB_AT_S), *media.ff_input(path), "-frames:v", "1",
            "-vf", f"scale={THUMB_WIDTH}:-2", "-q:v", "3", "-y", str(out),
            limit_s=THUMB_LIMIT_S,
        )  # fmt: skip
        if code != 0 or not out.exists() or out.stat().st_size == 0:
            return None
        data = out.read_bytes()
    from PIL import Image

    def size() -> tuple[int, int]:
        import io

        with Image.open(io.BytesIO(data)) as im:
            return im.width, im.height

    w, h = await asyncio.to_thread(size)
    return data, w, h


# ------------------------------------------------------------ the backfill --
BACKFILL_SQL = f"""SELECT {JOB_COLS} FROM infra.server_jobs j
WHERE j.kind = 'publish' AND j.args ? 'session' AND NOT (j.args ? 'rule_for')
ORDER BY j.created_at, j.id"""  # noqa: S608


def chains(jobs: list[dict[str, Any]]) -> tuple[list[list[dict[str, Any]]], int]:
    """The jobs (oldest first) in their chains (§55.4): a first job opens one, every question and
    cancel of the same file, account and kind joins the newest open one. Answers the chains and
    how many questions had no chain (never made into a row)."""
    from hq_api.domain import session_publish as SPB

    out: list[list[dict[str, Any]]] = []
    open_: dict[tuple[str, str, str, str], int] = {}
    lost = 0
    for j in jobs:
        key = SPB.publication_of(j)
        if _asks(_j(j["args"]) or {}):
            if key in open_:
                out[open_[key]].append(j)
            else:
                lost += 1
            continue
        open_[key] = len(out)
        out.append([j])
    return out, lost


def _sets(found: list[list[dict[str, Any]]]) -> dict[str, tuple[str, int]]:
    """The backfill's sets: the picture stories of one output and one page on one Tehran day,
    two or more, in their hours' order (what a stories flow sends; read from the jobs, never
    guessed). Answers each first job's (set_key, n)."""
    tz = ZoneInfo(TEHRAN)
    groups: dict[str, list[tuple[datetime, str]]] = {}
    for c in found:
        j = c[0]
        args = _j(j["args"]) or {}
        s = args.get("session") or {}
        files = args.get("files") or []
        picture = bool(files) and str((files[0] or {}).get("mime") or "").startswith("image/")
        if args.get("kind") != "story" or not picture or not s.get("output"):
            continue
        at = _when((args.get("meta") or {}).get("scheduled_at")) or j["created_at"]
        day = at.astimezone(tz).date().isoformat()
        key = f"{str(args.get('account') or '').lstrip('@')}:{day}:{s['output']}"
        groups.setdefault(key, []).append((at, str(j["id"])))
    out: dict[str, tuple[str, int]] = {}
    for key, items in groups.items():
        if len(items) < 2:
            continue
        for n, (_, jid) in enumerate(sorted(items), 1):
            out[jid] = (key, n)
    return out


async def backfill(tx: Tx) -> dict[str, Any]:
    """§60.1 one row per chain of every `publish` job (any state), idempotent: a chain with its
    row only gains the jobs it lacks and IG-Hub's last word. Answers the counts, per account."""
    jobs = [dict(r) for r in await tx.all(BACKFILL_SQL)]
    found, lost = chains(jobs)
    sets = _sets(found)
    made, updated, skipped = 0, 0, 0
    per: dict[str, int] = {}
    for c in found:
        first, last = c[0], c[-1]
        ids = [str(j["id"]) for j in c]
        row = await tx.first(
            "SELECT * FROM media.publications WHERE chain[1] = CAST(:id AS uuid) FOR UPDATE",
            id=ids[0],
        )
        if row is None:
            extra: dict[str, Any] = {}
            if ids[0] in sets:
                extra["set_key"], extra["n"] = sets[ids[0]]
            v = await _values(tx, first, ids, extra)
            if v is None:
                skipped += 1
                continue
            before = None
            st = state_of(first, None)
            for j in c[1:]:
                before = {"state": st["state"], "state_note_fa": st["note"], "url": st["url"],
                          "external_id": st["external_id"], "published_at": st["published_at"]}  # fmt: skip
                st = state_of(j, before)
            v["scheduled_at"] = v["scheduled_at"] or st["scheduled_at"]
            if await _insert(tx, v, st) is not None:
                made += 1
        else:
            missing = [i for i in ids if i not in {str(x) for x in row["chain"]}]
            if missing:
                await tx.exec(
                    """UPDATE media.publications SET chain = chain || CAST(:m AS uuid[])
                       WHERE id = :id""",
                    m=missing,
                    id=row["id"],
                )
                updated += 1
            if await apply(tx, last["id"]) is None:
                skipped += 1
        account = str((_j(first["args"]) or {}).get("account") or "").lstrip("@")
        per[account] = per.get(account, 0) + 1
    rows = await tx.all(
        "SELECT account, count(*) AS n FROM media.publications GROUP BY account ORDER BY account"
    )
    return {
        "jobs": len(jobs),
        "chains": len(found),
        "made": made,
        "updated": updated,
        "skipped": skipped,
        "questions_without_chain": lost,
        "chains_per_account": dict(sorted(per.items())),
        "rows_per_account": {str(r["account"]): int(r["n"]) for r in rows},
    }


# ---------------------------------------------------------------- reading --
ROW_SQL = """SELECT p.*, c.code AS company, coalesce(c.name_fa, c.code) AS company_fa,
       NULL::bigint AS set_total, NULL::bigint AS set_done, NULL::timestamptz AS set_next
FROM media.publications p JOIN core.companies c ON c.id = p.company_id"""


def _card(r: dict[str, Any], q: str | None = None) -> PublicationCard:
    src = _j(r["source"]) or {}
    files = _j(r["files"]) or []
    card = PublicationCard(
        ref=str(r["ref"]),
        company=str(r["company"]),
        company_fa=str(r["company_fa"]),
        channel=r["channel"],
        account=str(r["account"]),
        kind=r["kind"],
        state=r["state"],
        state_note_fa=r["state_note_fa"],
        at=r["at"],
        title_fa=str(r["title_fa"]),
        thumb_file_id=str(r["thumb_file_id"]) if r["thumb_file_id"] else None,
        files_n=len([f for f in files if f.get("role") != "thumb"]),
        url=r["url"],
        set_key=r["set_key"],
        automation=src.get("automation"),
        automation_fa=src.get("automation_fa"),
    )
    if r.get("set_total") is not None and r["set_key"]:
        card.set = CardSet(
            n=int(r["set_total"]), done=int(r["set_done"] or 0), next_at=r["set_next"]
        )
    if q:
        comment = _j(r["comment"]) or {}
        for where, text in (
            ("title", r["title_fa"]), ("topic", r["topic_fa"]), ("caption", r["caption"]),
            ("word", " ".join([*(comment.get("keywords") or []), r["story_word"] or ""])),
        ):  # fmt: skip
            got = snippet(str(text or ""), q)
            if got:
                card.match, card.snippet_fa = cast(Match, where), got
                break
    return card


def _set_items(rows: list[dict[str, Any]] | None) -> list[SetItem] | None:
    if rows is None:
        return None
    out = []
    for x in rows:
        files = _j(x["files"]) or []
        fid = next(
            (str(f["file_id"]) for f in files if f.get("role") in ("slide", "image", "video")), None
        )
        out.append(
            SetItem(ref=str(x["ref"]), n=x["set_n"], at=x["at"], state=x["state"], file_id=fid)
        )
    return out


def _publication(r: dict[str, Any], set_rows: list[dict[str, Any]] | None) -> Publication:
    src = _j(r["source"]) or {}
    return Publication(
        ref=str(r["ref"]),
        company=str(r["company"]),
        company_fa=str(r["company_fa"]),
        channel=r["channel"],
        account=str(r["account"]),
        kind=r["kind"],
        state=r["state"],
        state_note_fa=r["state_note_fa"],
        scheduled_at=r["scheduled_at"],
        published_at=r["published_at"],
        at=r["at"],
        url=r["url"],
        external_id=r["external_id"],
        title_fa=str(r["title_fa"]),
        topic_fa=r["topic_fa"],
        caption=r["caption"],
        comment=PubComment.model_validate(_j(r["comment"])) if r["comment"] else None,
        story_word=r["story_word"],
        seo=PubSeo.model_validate(_j(r["seo"])) if r["seo"] else None,
        files=[PubFile.model_validate(f) for f in _j(r["files"]) or []],
        thumb_file_id=str(r["thumb_file_id"]) if r["thumb_file_id"] else None,
        set_key=r["set_key"],
        set=_set_items(set_rows),
        source=PubSource.model_validate({**src, "job_id": src.get("job_id") or str(r["chain"][0])}),
        insights=Insights.model_validate(_j(r["insights"])) if r["insights"] else None,
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


async def _company_id(tx: Tx, code: str | None) -> UUID | None:
    if code is None:
        return None
    got = await tx.scalar("SELECT id FROM core.companies WHERE code = :c", c=code)
    if got is None:
        raise ApiError(404, "not_found", f"company {code}")
    return UUID(str(got))


async def _check_account(tx: Tx, account: str | None) -> str | None:
    if account is None:
        return None
    a = account.lstrip("@")
    if not await tx.scalar("SELECT 1 FROM media.publications WHERE account = :a LIMIT 1", a=a):
        raise ApiError(404, "not_found", f"account {account}")
    return a


def day_bounds(day: date, tz: str) -> tuple[datetime, datetime]:
    from hq_api.domain.gov_common import zone

    start = datetime.combine(day, time(0, 0), zone(tz))
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


# One card for a set (group=set): its first slide, with the set's progress.
SET_SQL = """SELECT p.*, c.code AS company, coalesce(c.name_fa, c.code) AS company_fa,
       s.total AS set_total, s.done AS set_done, s.next_at AS set_next, s.first_id
FROM media.publications p JOIN core.companies c ON c.id = p.company_id LEFT JOIN LATERAL (
    SELECT count(*) AS total, count(*) FILTER (WHERE x.state = 'published') AS done,
           min(x.at) FILTER (WHERE x.state IN ('scheduled', 'publishing', 'held')) AS next_at,
           (array_agg(x.id ORDER BY x.set_n NULLS LAST, x.at, x.ref))[1] AS first_id
    FROM media.publications x
    WHERE p.set_key IS NOT NULL AND x.set_key = p.set_key AND x.company_id = p.company_id) s ON true"""
SET_FIRST = " AND (p.set_key IS NULL OR s.first_id = p.id)"


def _filters(
    company_id: UUID | None, account: str | None, channel: str | None, kind: str | None,
    state: str | None, automation: str | None,
) -> tuple[str, dict[str, Any]]:  # fmt: skip
    where: list[str] = []
    args: dict[str, Any] = {}
    for col, val in (("p.company_id", company_id), ("p.account", account), ("p.channel", channel),
                     ("p.kind", kind), ("p.state", state)):  # fmt: skip
        if val is not None:
            name = col.split(".")[1]
            where.append(f"{col} = :{name}")
            args[name] = val
    if automation is not None:
        where.append("p.source ->> 'automation' = :automation")
        args["automation"] = automation
    return "".join(f" AND {w}" for w in where), args


async def page(
    tx: Tx,
    *,
    company: str | None = None,
    account: str | None = None,
    channel: str | None = None,
    kind: str | None = None,
    state: str | None = None,
    from_: date | None = None,
    to: date | None = None,
    q: str | None = None,
    automation: str | None = None,
    group: str | None = None,
    cursor: str | None = None,
    limit: int = LIST_LIMIT,
) -> PublicationPage:
    """§60.2 the list, newest first; `q` through the folded text; `group=set`: a set as one card."""
    from hq_api import pagination
    from hq_api.domain.gov_common import owner_tz

    co = await _company_id(tx, company)
    acc = await _check_account(tx, account)
    where, args = _filters(co, acc, channel, kind, state, automation)
    tz = await owner_tz(tx)
    if from_ is not None:
        where += " AND p.at >= :lo"
        args["lo"] = day_bounds(from_, tz)[0]
    if to is not None:
        where += " AND p.at < :hi"
        args["hi"] = day_bounds(to, tz)[1]
    if q is not None:
        key = fold(q)
        if not key:
            return PublicationPage()
        where += " AND p.search_fa LIKE :q"
        args["q"] = "%" + re.sub(r"([%_\\])", r"\\\1", key) + "%"
    at, rid = pagination.time_id(cursor)
    if at is not None:
        where += " AND (p.at, p.id) < (:cat, :cid)"
        args["cat"], args["cid"] = at, rid
    grouped = group == "set"
    sql = "".join((SET_SQL if grouped else ROW_SQL, " WHERE true", where,
                   SET_FIRST if grouped else "", " ORDER BY p.at DESC, p.id DESC LIMIT :n"))  # fmt: skip
    rows = [dict(r) for r in await tx.all(sql, n=min(limit, LIST_MAX) + 1, **args)]
    items, nxt = pagination.page(rows, min(limit, LIST_MAX), ("at", "id"))
    return PublicationPage(items=[_card(r, q) for r in items], next=nxt)


async def get(tx: Tx, ref: str) -> Publication:
    row = await tx.first(ROW_SQL + " WHERE p.ref = :r", r=ref)
    if row is None:
        raise ApiError(404, "not_found", f"publication {ref}")
    r = dict(row)
    set_rows = None
    if r["set_key"]:
        set_rows = [
            dict(x)
            for x in await tx.all(
                """SELECT ref, set_n, at, state, files FROM media.publications
                   WHERE set_key = :k AND company_id = :co ORDER BY set_n NULLS LAST, at, ref""",
                k=r["set_key"],
                co=r["company_id"],
            )
        ]
    return _publication(r, set_rows)


async def planned_today(tx: Tx, day: date) -> list[PlannedItem]:
    """§60.2 `planned`: what the daily flows will still make on `day` (Tehran), not yet a row. The
    ONE place the centre reads the flows' definitions (today the code's FLOWS through `slot_of`
    and `story_times`; §61's table and its loader replace them here)."""
    from hq_api.domain import flows as FL

    off = await FL.off_keys(tx)
    now = datetime.now(UTC)
    rows = await tx.all(
        """SELECT DISTINCT source ->> 'flow_key' AS k FROM media.publications
           WHERE source ->> 'day' = :d AND source ->> 'flow_key' IS NOT NULL""",
        d=day.isoformat(),
    )
    made = {str(r["k"]) for r in rows}
    tz = ZoneInfo(FL.TEHRAN)
    out: list[PlannedItem] = []
    for flow in FL.FLOWS.values():
        if not flow.account or flow.key in off or flow.key in made:
            continue
        co = await tx.scalar("SELECT id FROM core.companies WHERE code = :c", c=flow.company)
        if co is None:
            continue
        if flow.stories:
            times = FL.story_times(flow, day)
            publish_at, last, kind = times[0], times[-1], "story"
        else:
            publish_at, _ = await FL.slot_of(tx, flow, day, co)
            last, kind = publish_at, "reel"
        hh, mm = (int(x) for x in flow.trigger_at.split(":"))
        build_day = day if flow.same_day else day - timedelta(days=1)
        build_at = datetime.combine(build_day, time(hh, mm), tz).astimezone(UTC)
        building = await tx.scalar(
            """SELECT 1 FROM work.work WHERE run_meta -> 'flow' ->> 'key' = :k
                 AND run_meta -> 'flow' ->> 'day' = :d AND status NOT IN ('failed', 'cancelled')
               LIMIT 1""",
            k=flow.key,
            d=day.isoformat(),
        )
        if not building and last < now:
            continue  # its hour is gone and nothing is being made: not «still to be made»
        ref, name, _ = await automation_of(tx, flow.key)
        out.append(
            PlannedItem(
                automation=ref, automation_fa=name or flow.title_fa, account=flow.account,
                kind=kind, title_fa=flow.title_fa, build_at=build_at, publish_at=publish_at,
                state="building" if building else "planned",
            )
        )  # fmt: skip
    return sorted(out, key=lambda p: p.publish_at)


async def today(
    tx: Tx, day: date | None = None, *, company: str | None = None, account: str | None = None,
    channel: str | None = None,
) -> PublishToday:  # fmt: skip
    """§60.2 the owner's day: its rows (a set as one card) in time order, what is still to be made,
    the next to go out and the day's counts."""
    from hq_api.domain.gov_common import owner_tz
    from hq_api.domain.gov_common import today as today_of

    tz = await owner_tz(tx)
    day = day or today_of(tz)
    co = await _company_id(tx, company)
    acc = await _check_account(tx, account)
    where, args = _filters(co, acc, channel, None, None, None)
    lo, hi = day_bounds(day, tz)
    sql = "".join((SET_SQL, " WHERE p.at >= :lo AND p.at < :hi", where, " ORDER BY p.at, p.id"))
    rows = [dict(r) for r in await tx.all(sql, lo=lo, hi=hi, **args)]
    counts = TodayCounts()
    for r in rows:
        if r["state"] in COUNTED:
            setattr(counts, r["state"], getattr(counts, r["state"]) + 1)
    # a set is one card, where its first slide of the day stands
    seen: set[str] = set()
    items: list[PublicationCard] = []
    for r in rows:
        if r["set_key"]:
            if r["set_key"] in seen:
                continue
            seen.add(str(r["set_key"]))
        items.append(_card(r))
    now = datetime.now(UTC)
    nxt = next(
        (
            c
            for c in items
            if c.state in ("scheduled", "publishing", "held") and c.at >= now - timedelta(minutes=5)
        ),
        None,
    )
    if nxt is None:
        nxt = next((c for c in items if c.set is not None and c.set.next_at is not None), None)
    planned = await _planned_for(tx, day, co, acc)
    if channel not in (None, "instagram"):
        planned = []
    return PublishToday(day=day, items=items, planned=planned, next=nxt, counts=counts)


async def _planned_for(
    tx: Tx, day: date, company_id: UUID | None, account: str | None
) -> list[PlannedItem]:
    """planned_today, of one company (its registered pages) or one page."""
    got = await planned_today(tx, day)
    if company_id is not None:
        from hq_api.domain import session_publish as SPB

        mine = set((await SPB._route(tx, company_id))["accounts"])
        got = [p for p in got if p.account in mine]
    if account is not None:
        got = [p for p in got if p.account == account]
    return got


async def tree(tx: Tx, from_: date | None, to: date | None) -> PublishTree:
    """§60.2 every company and page with at least one row in the range (default the last 30 days):
    totals, by kind, how many automations made them."""
    from hq_api.domain.gov_common import owner_tz
    from hq_api.domain.gov_common import today as today_of

    tz = await owner_tz(tx)
    end = to or today_of(tz)
    start = from_ or end - timedelta(days=TOPIC_TREE_DAYS - 1)
    if start > end:
        raise ApiError(422, "validation_failed", fields={"from": "after to"})
    lo, hi = day_bounds(start, tz)[0], day_bounds(end, tz)[1]
    rows = await tx.all(
        """SELECT c.code, coalesce(c.name_fa, c.code) AS name_fa, p.channel, p.account, p.kind,
                  count(*) AS n,
                  count(DISTINCT p.source ->> 'automation') AS automations
           FROM media.publications p JOIN core.companies c ON c.id = p.company_id
           WHERE p.at >= :lo AND p.at < :hi
           GROUP BY c.code, c.name_fa, p.channel, p.account, p.kind
           ORDER BY c.code, p.account, p.kind""",
        lo=lo,
        hi=hi,
    )
    autos = {
        (str(r["code"]), str(r["account"])): int(r["n"])
        for r in await tx.all(
            """SELECT c.code, p.account, count(DISTINCT p.source ->> 'automation') AS n
               FROM media.publications p JOIN core.companies c ON c.id = p.company_id
               WHERE p.at >= :lo AND p.at < :hi GROUP BY c.code, p.account""",
            lo=lo,
            hi=hi,
        )
    }
    out: dict[str, TreeCompany] = {}
    for r in rows:
        code = str(r["code"])
        co = out.setdefault(code, TreeCompany(code=code, name_fa=str(r["name_fa"]), total=0))
        acc = next(
            (a for a in co.accounts if a.account == r["account"] and a.channel == r["channel"]),
            None,
        )
        if acc is None:
            acc = TreeAccount(channel=r["channel"], account=str(r["account"]), total=0,
                              automations=autos.get((code, str(r["account"])), 0))  # fmt: skip
            co.accounts.append(acc)
        acc.by_kind[str(r["kind"])] = int(r["n"])
        acc.total += int(r["n"])
        co.total += int(r["n"])
    return PublishTree(companies=list(out.values()))


async def calendar(
    tx: Tx, from_: date | None, to: date | None, company: str | None, account: str | None
) -> PublishCalendar:
    """§60.2 the Tehran days of the range: each day's rows by state, and the future's planned
    count (what the flows will still make)."""
    from hq_api.domain.gov_common import owner_tz
    from hq_api.domain.gov_common import today as today_of

    tz = await owner_tz(tx)
    now_day = today_of(tz)
    start = from_ or now_day - timedelta(days=CALENDAR_DEFAULT)
    end = to or now_day + timedelta(days=CALENDAR_DEFAULT)
    if start > end or (end - start).days >= CALENDAR_MAX:
        raise ApiError(
            422, "validation_failed", fields={"to": f"from..to, at most {CALENDAR_MAX} days"}
        )
    co = await _company_id(tx, company)
    acc = await _check_account(tx, account)
    where, args = _filters(co, acc, None, None, None, None)
    lo, hi = day_bounds(start, tz)[0], day_bounds(end, tz)[1]
    rows = await tx.all(
        f"""SELECT (p.at AT TIME ZONE :tz)::date AS day, p.state, p.account, count(*) AS n
            FROM media.publications p WHERE p.at >= :lo AND p.at < :hi{where}
            GROUP BY 1, 2, 3""",  # noqa: S608 - the filters are constants with bound values
        tz=tz,
        lo=lo,
        hi=hi,
        **args,
    )
    days: dict[date, CalendarDay] = {}
    d = start
    while d <= end:
        days[d] = CalendarDay(day=d)
        d += timedelta(days=1)
    for r in rows:
        cd = days.get(r["day"])
        if cd is None:
            continue
        if r["state"] in COUNTED:
            setattr(cd, r["state"], getattr(cd, r["state"]) + int(r["n"]))
        if r["account"] not in cd.accounts:
            cd.accounts.append(str(r["account"]))
    for day, cd in days.items():
        if day < now_day:
            continue
        for p in await _planned_for(tx, day, co, acc):
            cd.planned += 1
            if p.account not in cd.accounts:
                cd.accounts.append(p.account)
    return PublishCalendar(days=list(days.values()))


# --------------------------------------------------------- «منتظر شما» --
ASK_LABELS = (WaitingAction(key="publish", label_fa="انتشار", primary=True),
              WaitingAction(key="skip", label_fa="این بار نه"))  # fmt: skip
CAP_LABELS = (WaitingAction(key="raise_cap", label_fa="سقف را بالا ببر", primary=True),
              WaitingAction(key="skip", label_fa="این نوبت رد شود"))  # fmt: skip
ASK_SKIPPED_FA = "مدیر کل این بار نخواست؛ منتشر نشد."
CAP_TITLE_FA = "«{title}» به سقف هزینه‌ی امروز رسید"
ASK_TITLE_FA = "«{group}»: {title}"
LINE_ASK_FA = "«{title}»: نوبت تو برای انتشار"
CAP_SKIPPED_FA = "این نوبت رد شد؛ منتشر نمیشود"
DAYS_A_MONTH = 30


async def _asks_of_groups(tx: Tx) -> list[tuple[Waiting, dict[str, Any]]]:
    """§45 a working group in `ask` mode whose run of today made a package nobody has sent."""
    from hq_api.domain import session_publish as SPB
    from hq_api.domain.gov_common import owner_tz
    from hq_api.domain.gov_common import today as today_of

    tz = await owner_tz(tx)
    lo, hi = day_bounds(today_of(tz), tz)
    rows = await tx.all(
        SPB.RUN_SQL
        + """ WHERE x.occurrence_at >= :lo AND x.occurrence_at < :hi
                AND w.status = ANY(CAST(:done AS text[]))
                AND coalesce(m.publish ->> 'mode', 'ask') <> 'auto'
                AND m.state = 'on' AND g.state = 'on' AND coalesce(x.note_fa, '') <> :skipped
              ORDER BY x.occurrence_at LIMIT 50""",
        lo=lo,
        hi=hi,
        done=list(SPB.WORK_DONE),
        skipped=ASK_SKIPPED_FA,
    )
    out = []
    for r in rows:
        run = dict(r)
        pkg = await SPB.package_of(tx, run)
        if pkg is None or not pkg.get("captioned"):
            continue
        d = pkg["d"]
        if any(
            p.state not in ("failed", "cancelled") for p in await SPB.of_output(tx, str(d["ref"]))
        ):
            continue
        rule = SPB.rule_of(run["publish"])
        route = await SPB._route(tx, run["company_id"])
        account = rule["account"] or (route["accounts"][0] if len(route["accounts"]) == 1 else None)
        caption = await SPB.caption_of(tx, None, d)
        topic = await _topic(tx, await OR.order_of_work(tx, d["work_id"]), None)
        title = title_of(topic, None, caption, "reel", account or "")
        out.append((
            Waiting(
                id=f"ask:{run['run_id']}", kind="publish_ask",
                title_fa=ASK_TITLE_FA.format(group=run["group_fa"], title=title)[:200],
                account=account, at=run["delivered_at"] or run["occurrence_at"], deadline_at=hi,
                actions=list(ASK_LABELS),
            ),
            {"run": run, "pkg": pkg, "account": account, "rule": rule},
        ))  # fmt: skip
    return out


async def _waits_of_lines(tx: Tx) -> list[tuple[Waiting, dict[str, Any]]]:
    """§59.7 a flow's line run waiting for the owner: its `ask` at the publish step, or its cap."""
    from hq_api.domain import flow_auto as FA
    from hq_api.lines import store

    rows = await tx.all(store.RUN_SQL + " WHERE r.state = 'waiting' ORDER BY r.at LIMIT 50")
    budget = tuple(x.split("(")[0] for x in (FA.BUDGET_DAY_FA, FA.BUDGET_RUN_FA))
    out = []
    for r in rows:
        run = dict(r)
        if not run.get("automation"):
            continue
        try:
            flow = await FA.load(tx, str(run["automation"]))
        except ApiError:
            continue
        title = str(flow.get("title_fa") or flow.get("sentence_fa") or run["automation"])
        step = await tx.first(
            """SELECT * FROM lines.step_runs WHERE run_id = :r AND state = 'waiting'
                 AND kind = 'publish' AND gate IS NOT NULL AND decision_id IS NOT NULL
               ORDER BY pos LIMIT 1""",
            r=run["id"],
        )
        if step is not None:
            w = Waiting(id=f"line:{run['ref']}", kind="publish_ask",
                        title_fa=LINE_ASK_FA.format(title=title)[:200], account=flow.get("account"),
                        at=step["started_at"] or run["updated_at"], actions=list(ASK_LABELS))  # fmt: skip
            out.append((w, {"run": run, "step": dict(step), "flow": flow}))
        elif str(run.get("note_fa") or "").startswith(budget):
            w = Waiting(id=f"line:{run['ref']}", kind="budget_cap",
                        title_fa=f"«{title}»: {run['note_fa']}"[:200], account=flow.get("account"),
                        at=run["updated_at"], actions=list(CAP_LABELS))  # fmt: skip
            out.append((w, {"run": run, "flow": flow}))
    return out


async def _caps_of_flows(tx: Tx) -> list[tuple[Waiting, dict[str, Any]]]:
    """A code flow's day at its cap (flows.over_cap: `capped` on its run, its package not sent)."""
    from hq_api.domain import flows as FL

    rows = await tx.all(
        """SELECT w.id, w.ref, w.company_id, w.updated_at, w.run_meta -> 'flow' AS flow,
                  c.code AS company
           FROM work.work w JOIN core.companies c ON c.id = w.company_id
           WHERE w.run_meta -> 'flow' ? 'capped' AND NOT (w.run_meta -> 'flow' ? 'sent')
             AND NOT (w.run_meta -> 'flow' ? 'skipped')
             AND w.status NOT IN ('failed', 'cancelled')
             AND w.created_at > now() - interval '3 days'
           ORDER BY w.created_at LIMIT 50"""
    )
    out = []
    for r in rows:
        meta = _j(r["flow"]) or {}
        flow = FL.FLOWS.get(str(meta.get("key") or ""))
        title = flow.title_fa if flow else str(meta.get("key") or "انتشار روزانه")
        at = _when(meta.get("publish_at")) or r["updated_at"]
        out.append((
            Waiting(id=f"cap:{r['ref']}", kind="budget_cap", title_fa=CAP_TITLE_FA.format(title=title)[:200],
                    account=str(meta.get("account") or "") or None, at=at, actions=list(CAP_LABELS)),
            {"work": dict(r), "meta": meta, "flow": flow},
        ))  # fmt: skip
    return out


async def _all_waiting(tx: Tx) -> list[tuple[Waiting, dict[str, Any]]]:
    return [*await _asks_of_groups(tx), *await _waits_of_lines(tx), *await _caps_of_flows(tx)]


async def waiting(tx: Tx) -> WaitingList:
    """§60.2 only what cannot move without the owner, oldest first."""
    got = [w for w, _ in await _all_waiting(tx)]
    return WaitingList(items=sorted(got, key=lambda w: w.at))


async def act(ctx: Any, tx: Tx, wid: str, key: str, body: WaitingIn) -> tuple[list[str], list[str]]:
    """`POST /publications/waiting/{id}/{key}`: the action, as a tap (a cap above the company's
    month envelope: 🔏 `automation.budget`). Answers the line runs to drive and to wake after the
    commit."""
    found = next(((w, x) for w, x in await _all_waiting(tx) if w.id == wid), None)
    if found is None:
        raise ApiError(404, "not_found", f"waiting {wid}")
    w, x = found
    if key not in {a.key for a in w.actions}:
        raise ApiError(
            422, "validation_failed", fields={"key": f"one of {[a.key for a in w.actions]}"}
        )
    if wid.startswith("ask:"):
        await _act_group(ctx, tx, x, key)
        return [], []
    if wid.startswith("line:"):
        return await _act_line(ctx, tx, w, x, key, body)
    await _act_cap(ctx, tx, x, key, body)
    return [], []


async def _act_group(ctx: Any, tx: Tx, x: dict[str, Any], key: str) -> None:
    from hq_api.domain import session_publish as SPB
    from hq_api.domain.gov_common import owner_tz

    run, pkg = x["run"], x["pkg"]
    if key == "skip":
        await tx.exec(
            "UPDATE growth.routine_runs SET note_fa = :n WHERE id = :id",
            n=ASK_SKIPPED_FA,
            id=run["run_id"],
        )
        await audit.record(
            tx, ctx.who, company_id=run["company_id"], action="publish.ask_skipped", action_class="A1",
            target_kind="group", target_ref=f"{run['group_key']}:{run['company']}"[:64],
            summary=f"the owner skipped {pkg['d']['ref']} of run {run['run_id']}"[:500],
        )  # fmt: skip
        return
    if x["account"] is None:
        raise ApiError(409, "validation_failed", message_fa=SPB.PICK_STANDING_FA)
    when = SPB.at_today(x["rule"]["at"], await owner_tz(tx))
    await SPB.start(
        tx, ctx.who, None, output=str(pkg["d"]["ref"]), file_id=UUID(str(pkg["file"]["id"])),
        account=x["account"], hub=ctx.hub, scheduled_at=when,
        cover_file_id=UUID(str(pkg["cover"]["id"])) if pkg.get("cover") else None,
    )  # fmt: skip


async def _act_line(
    ctx: Any, tx: Tx, w: Waiting, x: dict[str, Any], key: str, body: WaitingIn
) -> tuple[list[str], list[str]]:
    from hq_api.domain import decisions as DE
    from hq_api.domain import flow_auto as FA
    from hq_api.domain import flow_shapes as FS
    from hq_api.lines import engine

    run = x["run"]
    if w.kind == "publish_ask":
        d = await tx.first(
            "SELECT * FROM cartable.decisions WHERE id = :d FOR UPDATE", d=x["step"]["decision_id"]
        )
        if d is None:
            raise ApiError(409, "decision_not_pending", "no card")
        verdict: Literal["approved", "rejected"] = "approved" if key == "publish" else "rejected"
        await DE.decide(tx, ctx.who, dict(d), verdict, note=None if key == "publish" else "این بار نه",
                        hub=ctx.hub)  # fmt: skip
        return ([str(run["ref"])] if key == "publish" else []), []
    if key == "skip":
        await engine.cancel(tx, run, skip=True)
        return [], []
    if body.usd_cap is None:
        raise ApiError(422, "validation_failed", fields={"usd_cap": "required"})
    flow = x["flow"]
    old = FA.budget_of(flow)
    patch = FS.FlowPatch(budget=FS.FlowBudget(per_run_usd=max(old.per_run_usd, float(body.usd_cap)),
                                              per_day_usd=float(body.usd_cap)))  # fmt: skip
    await FA.patch(ctx, tx, ctx.request, str(flow["ref"]), patch)
    return [], [str(r) for r in await FA.waiting_runs(tx, await FA.load(tx, str(flow["ref"])))]


async def _act_cap(ctx: Any, tx: Tx, x: dict[str, Any], key: str, body: WaitingIn) -> None:
    """A code flow's day at its cap: a higher cap for this day (the run's own `usd_cap`; §61 moves
    it to the flow's row), or the day is skipped."""
    from hq_api.domain import flow_auto as FA
    from hq_api.security import stepup

    work, meta = x["work"], dict(x["meta"])
    ref = f"N8:{meta.get('key')}"
    w = await tx.first(
        "SELECT run_meta -> 'flow' AS flow FROM work.work WHERE id = :w FOR UPDATE", w=work["id"]
    )
    meta = dict(_j((w or {}).get("flow")) or meta)
    before = {k: meta.get(k) for k in ("usd_cap", "capped", "skipped")}
    step_up = False
    if key == "skip":
        meta["skipped"] = datetime.now(UTC).isoformat()
    else:
        if body.usd_cap is None:
            raise ApiError(422, "validation_failed", fields={"usd_cap": "required"})
        from hq_api.domain import flows as FL

        spent = await FL.spent_usd(tx, str(work["ref"]))
        if body.usd_cap <= spent:
            raise ApiError(422, "validation_failed", fields={"usd_cap": f"above today's {spent:.2f}"},
                           message_fa="سقف تازه باید بیشتر از هزینه‌ی امروز باشد")  # fmt: skip
        limit = await FA.month_limit_usd(tx, work["company_id"])
        if limit is None or float(body.usd_cap) * DAYS_A_MONTH > limit:
            await stepup.consume(tx, ctx.request, ctx.who, "automation.budget",
                                 FA.budget_target(ref, float(body.usd_cap)))  # fmt: skip
            step_up = True
        meta["usd_cap"] = str(body.usd_cap)
        meta.pop("capped", None)
    await tx.exec(
        "UPDATE work.work SET run_meta = jsonb_set(run_meta, '{flow}', CAST(:m AS jsonb)) WHERE id = :w",
        w=work["id"],
        m=json.dumps(meta, ensure_ascii=False),
    )
    await audit.record(
        tx, ctx.who, company_id=work["company_id"],
        action="flow.cap_raised" if key == "raise_cap" else "flow.cap_skipped", action_class="A2",
        target_kind="work", target_ref=str(work["ref"]),
        summary=f"{ref} {meta.get('day')}: {json.dumps(before, default=str)} -> "
        f"{'$' + str(body.usd_cap) if key == 'raise_cap' else CAP_SKIPPED_FA}"
        f"{' (step-up automation.budget)' if step_up else ''}"[:500],
    )  # fmt: skip
    if key == "raise_cap":
        with contextlib.suppress(Exception):
            async with tx.conn.begin_nested():
                await tx.scalar(
                    "SELECT work.wake_assignee(:w, :r)", w=work["id"], r=f"uncapped:{work['ref']}"
                )
