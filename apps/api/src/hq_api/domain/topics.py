"""⟨1.31⟩ §47 The ledger of what was said: a topic is never made twice.

The owner's order (2026-11-10): «هیچ روزی تکراری نباشد: ۳۶۵ روز، ۳۶۵ مطلب و ویدیوی متفاوت», and
for the Pinterest sample of each day «هر بار متفاوت». Until now that rested on what a model
remembered of a session. Here it is code: every topic and every reference a company used in a
working group is a row, and a new one that says the same thing is refused before anything is
made.

Two things say «the same»: the words (letters unified, marks and filler words dropped, the order
of the words ignored; two titles that share four words of five are one topic) and, for a
reference, its address (a Pinterest pin by its number).

Who writes a row:
- `topic.claim` (an agent, A1): the routine's work names today's topic, and its reference, before
  it writes or builds. A taken one answers `409 topic_taken` with the row it collides with.
- the hub itself, when a package goes out on the owner's standing word and its run named no
  topic: the package's `topic.txt`, else the first line of its caption (`source: package`).
- the owner, in the working group's page («این را قبلاً گفته‌ایم»).

A topic claimed in a session before its working group exists belongs to that session
(`order_ref`); sealing the session's playbook moves it to the group, so day one counts.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from hq_api.db import Tx
from hq_api.errors import ApiError

Kind = Literal["topic", "reference"]
Source = Literal["claim", "package", "owner"]
TITLE_MAX = 300
URL_MAX = 2000
SAME = 0.8  # the share of words two titles have in common from which they are one topic
SCAN = 5000  # rows of one ledger read to compare (a daily group fills 365 a year)
BRIEF_TOPICS = 40
BRIEF_REFERENCES = 10
TOPIC_NAMES = ("topic.txt", "topic.md")

_MAP = str.maketrans(
    {
        "ي": "ی", "ى": "ی", "ئ": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "ؤ": "و",
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        # the half-space and the joiners, the direction marks, the stretch (tatweel)
        "\u200c": "", "\u200d": "", "\u200e": "", "\u200f": "", "\u0640": "",
        **{chr(0x06F0 + i): str(i) for i in range(10)},
        **{chr(0x0660 + i): str(i) for i in range(10)},
    }
)  # fmt: skip
# the short vowels and the Quran's marks
_MARKS = re.compile("[\u064b-\u065f\u0670\u06d6-\u06ed]")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
# the «ی» / «ای» that ties a word to the next after a half-space («مقایسه‌ی پروچارت»)
_EZAFE = re.compile("\u200c(?:ای|ی|ي)(?![^\\W_])")
# words that carry no topic: «آموزش اندیکاتور RSI» and «معرفی اندیکاتور RSI» are one reel
FILLER = frozenset(
    {
        "و", "در", "به", "از", "که", "را", "با", "برای", "تا", "بر", "یا", "هم", "این", "ان",
        "یک", "ی", "ای", "است", "هست", "شد", "شود", "میشود", "چیست", "چیه", "چطور", "چگونه",
        "چرا", "کدام", "هر", "ما", "شما", "من", "تو", "او", "ها", "های", "اموزش", "معرفی",
        "ویدیو", "ویدیوی", "ریلز", "درباره", "مورد", "نگاهی", "the", "a", "an", "of", "to",
        "in", "on", "for", "and", "or", "with", "is", "are", "how", "what", "why", "this",
        "that", "video", "reel",
    }
)  # fmt: skip


def words(text: str, brand: frozenset[str] = frozenset()) -> list[str]:
    """The words of a title as code compares them, in their own order: letters unified (Arabic
    and Persian forms, digits), marks, half-spaces and punctuation gone, a plural's «ها»/«های»
    cut, filler words dropped (kept when nothing else is left). `brand`: the company's own name
    (brand_of), which is in every title of its and says nothing of the topic."""
    s = _EZAFE.sub(" ", unicodedata.normalize("NFKC", text or "")).translate(_MAP)
    s = _MARKS.sub("", s).lower()
    raw = _WORD.findall(s)
    out: list[str] = []
    for w in raw:
        if len(w) >= 6 and w.endswith("های"):
            w = w[:-3]
        elif len(w) >= 6 and w.endswith("ها"):
            w = w[:-2]
        out.append(w)
    kept = [w for w in out if w not in FILLER and w not in brand]
    return (kept or [w for w in out if w not in brand] or out)[:60]


async def brand_of(tx: Tx, company_id: UUID) -> frozenset[str]:
    """The words of a company's own name (Persian, English, its code), together and apart
    («پرو چارت», «پروچارت»): no title is told apart by them."""
    row = await tx.first(
        "SELECT code, name_fa, name_en FROM core.companies WHERE id = :id", id=company_id
    )
    if row is None:
        return frozenset()
    out: set[str] = {str(row["code"]).lower()}
    for name in (row["name_fa"], row["name_en"]):
        got = words(str(name or ""))
        out.update(got)
        if got:
            out.add("".join(got))
    return frozenset(w for w in out if len(w) >= 2)


def norm_of(tokens: list[str]) -> str:
    """The key one topic has however its words are ordered."""
    return " ".join(sorted(set(tokens)))[:400]


def norm_url(url: str) -> str | None:
    """A reference's address as code compares it: an https address without its `www.`, country
    prefix, query and trailing slash; a Pinterest pin is its number. None: not an address."""
    try:
        u = urlsplit((url or "").strip())
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if u.scheme not in ("http", "https") or "." not in host:
        return None
    host = host.removeprefix("www.")
    path = re.sub(r"/+", "/", u.path).rstrip("/")
    if host == "pinterest.com" or host.endswith(".pinterest.com") or host.startswith("pinterest."):
        pin = re.search(r"/pin/(?:[^/]*?-)?(\d{5,})$", path) or re.search(r"/pin/(\d{5,})", path)
        if pin is not None:
            return f"pinterest:pin:{pin.group(1)}"
        host = "pinterest.com"
    return f"{host}{path}".lower()[:400] or None


def same(a: list[str], b: list[str]) -> bool:
    """Two titles are one topic: the same words in any order, the same letters once the spaces
    are out («پرو چارت» and «پروچارت»), or at least SAME of their words in common."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return False
    if sa == sb or "".join(a) == "".join(b):
        return True
    return len(sa & sb) / len(sa | sb) >= SAME


# ------------------------------------------------------------------ shapes --
class TopicEntry(BaseModel):
    """One line of the ledger. `source`: `claim` (the routine's work named it), `package` (the
    hub read it from what went out), `owner` (he added it himself)."""

    id: UUID
    kind: Kind
    title_fa: str
    url: str | None = None
    at: datetime
    by: str
    source: Source
    work_ref: str | None = None
    output: str | None = None


class TopicCount(BaseModel):
    topics: int = 0
    references: int = 0
    last_fa: str | None = None
    last_at: datetime | None = None


def render(r: dict[str, Any]) -> TopicEntry:
    return TopicEntry(
        id=r["id"], kind=r["kind"], title_fa=r["title_fa"], url=r.get("url"), at=r["created_at"],
        by=r["by_code"], source=r["source"], work_ref=r.get("work_ref"), output=r.get("output"),
    )  # fmt: skip


# ------------------------------------------------------------------- scope --
SCOPE_SQL = """WITH RECURSIVE up(id, hops) AS (
    SELECT CAST(:w AS uuid), 0
    UNION
    SELECT COALESCE(w.parent_id, w.requested_by_work_id), up.hops + 1
    FROM work.work w JOIN up ON w.id = up.id
    WHERE COALESCE(w.parent_id, w.requested_by_work_id) IS NOT NULL AND up.hops < 20)
SELECT x.id AS run_id, x.group_id, x.company_id, g.key AS group_key, g.title_fa AS group_fa
FROM growth.routine_runs x JOIN growth.groups g ON g.id = x.group_id
WHERE x.work_id IN (SELECT id FROM up) ORDER BY x.at DESC LIMIT 1"""


async def scope_of_work(tx: Tx, w: dict[str, Any]) -> dict[str, Any]:
    """Whose ledger a work writes in: the working group of the routine run it belongs to (itself,
    or up its parents and its requests), else the session it is part of, else its company's own
    loose list."""
    from hq_api.domain import order_report as OR

    run = await tx.first(SCOPE_SQL, w=str(w["id"]))
    if run is not None:
        return {"company_id": run["company_id"], "group_id": run["group_id"],
                "group_key": run["group_key"], "run_id": run["run_id"], "order_ref": None}  # fmt: skip
    return {"company_id": w["company_id"], "group_id": None, "group_key": None, "run_id": None,
            "order_ref": await OR.order_of_work(tx, w["id"])}  # fmt: skip


WHERE = """company_id = :co AND kind = :k AND state = 'said'
    AND group_id IS NOT DISTINCT FROM CAST(:g AS uuid)
    AND (CAST(:g AS uuid) IS NOT NULL OR order_ref IS NOT DISTINCT FROM CAST(:o AS text))"""


SCAN_SQL = "".join((  # module constants only
    "SELECT id, title_fa, url, norm, tokens, run_id, created_at FROM growth.topics WHERE ",
    WHERE,
    " ORDER BY created_at DESC LIMIT :n",
))  # fmt: skip
RECENT_SQL = "".join(
    ("SELECT * FROM growth.topics WHERE ", WHERE, " ORDER BY created_at DESC LIMIT :n")
)


async def taken_by(
    tx: Tx, scope: dict[str, Any], kind: Kind, tokens: list[str], norm: str,
    *, but_run: UUID | None = None, exact: bool = False,
) -> dict[str, Any] | None:  # fmt: skip
    """The row of this ledger that already says it, or None. `exact`: only the same words (a
    caption's first line read by the hub is not held to the looser rule of a named topic)."""
    rows = await tx.all(
        SCAN_SQL,
        co=scope["company_id"], k=kind, g=scope.get("group_id"), o=scope.get("order_ref"), n=SCAN,
    )  # fmt: skip
    for r in rows:
        if but_run is not None and r["run_id"] == but_run:
            continue
        if r["norm"] == norm:
            return dict(r)
        if kind == "topic" and not exact and same(tokens, list(r["tokens"] or [])):
            return dict(r)
    return None


def taken_error(row: dict[str, Any], recent: list[str]) -> ApiError:
    day = f"{row['created_at']:%Y-%m-%d}"
    return ApiError(
        409,
        "topic_taken",
        f"said on {day}",
        fields={
            "title_fa": f"taken: «{str(row['title_fa'])[:160]}» ({day})",
            "recent": "؛ ".join(recent)[:1500],
        },
        message_fa=f"این پیش‌تر گفته شده: «{str(row['title_fa'])[:160]}» ({day}). یک موضوع تازه انتخاب کن.",
    )


async def recent(
    tx: Tx, scope: dict[str, Any], kind: Kind, limit: int = BRIEF_TOPICS
) -> list[dict[str, Any]]:
    return await tx.all(
        RECENT_SQL,
        co=scope["company_id"], k=kind, g=scope.get("group_id"), o=scope.get("order_ref"), n=limit,
    )  # fmt: skip


def parts(
    kind: Kind, title: str | None, url: str | None, brand: frozenset[str] = frozenset()
) -> tuple[str, str | None, list[str], str]:
    """(title, url, words, key) of what is being said, or 422."""
    text = " ".join((title or "").split())[:TITLE_MAX]
    link = (url or "").strip()[:URL_MAX] or None
    if kind == "reference":
        key = norm_url(link or text)
        if key is None:
            raise ApiError(
                422, "validation_failed", fields={"url": "the reference's https address"},
                message_fa="نمونه نشانی (لینک) میخواهد.",
            )  # fmt: skip
        return text or (link or ""), link or text, [], key
    tokens = words(text, brand)
    if not tokens:
        raise ApiError(
            422, "validation_failed", fields={"title_fa": "the topic in a few words"},
            message_fa="موضوع را در چند کلمه بنویس.",
        )  # fmt: skip
    return text, link, tokens, norm_of(tokens)


async def claim(
    tx: Tx,
    scope: dict[str, Any],
    *,
    kind: Kind,
    title: str | None,
    url: str | None = None,
    source: Source = "claim",
    by: str,
    work_ref: str | None = None,
    output: str | None = None,
    exact: bool = False,
) -> tuple[dict[str, Any], bool]:
    """One line in a ledger, or `409 topic_taken`. A run names one topic and one reference: the
    same one again answers the same row (`False`), another one replaces it."""
    text, link, tokens, norm = parts(kind, title, url, await brand_of(tx, scope["company_id"]))
    run_id = scope.get("run_id")
    mine = None
    if run_id is not None:
        mine = await tx.first(
            """SELECT * FROM growth.topics WHERE run_id = :r AND kind = :k AND state = 'said'
               FOR UPDATE""",
            r=run_id, k=kind,
        )  # fmt: skip
        if mine is not None and mine["norm"] == norm:
            return dict(mine), False
    hit = await taken_by(tx, scope, kind, tokens, norm, but_run=run_id, exact=exact)
    if hit is not None:
        raise taken_error(hit, [str(r["title_fa"]) for r in await recent(tx, scope, kind, 12)])
    try:
        async with tx.conn.begin_nested():
            if mine is not None:
                row = await tx.one(
                    """UPDATE growth.topics SET title_fa = :t, url = :u, norm = :n, tokens = :tk,
                           source = :s, by_code = :by, work_ref = COALESCE(:w, work_ref),
                           output = COALESCE(:out, output)
                       WHERE id = :id RETURNING *""",
                    id=mine["id"], t=text, u=link, n=norm, tk=tokens, s=source, by=by[:64],
                    w=work_ref, out=output,
                )  # fmt: skip
            else:
                row = await tx.one(
                    """INSERT INTO growth.topics (company_id, group_id, order_ref, kind, title_fa,
                           url, norm, tokens, run_id, work_ref, output, source, by_code)
                       VALUES (:co, :g, :o, :k, :t, :u, :n, :tk, :r, :w, :out, :s, :by)
                       RETURNING *""",
                    co=scope["company_id"], g=scope.get("group_id"),
                    o=None if scope.get("group_id") else scope.get("order_ref"),
                    k=kind, t=text, u=link, n=norm, tk=tokens, r=run_id, w=work_ref, out=output,
                    s=source, by=by[:64],
                )  # fmt: skip
    except IntegrityError:  # said by another run in the same moment
        hit = await taken_by(tx, scope, kind, tokens, norm, but_run=run_id, exact=True)
        if hit is None:
            raise
        raise taken_error(hit, []) from None
    return dict(row), True


async def of_run(tx: Tx, run_id: UUID) -> dict[str, dict[str, Any]]:
    rows = await tx.all(
        "SELECT * FROM growth.topics WHERE run_id = :r AND state = 'said'", r=run_id
    )
    return {str(r["kind"]): dict(r) for r in rows}


async def adopt(tx: Tx, order_ref: str, company_id: UUID, group_id: UUID) -> int:
    """A session became a working group: what the session said is the group's from now on (a
    line the group already has stays the session's)."""
    return await tx.exec(
        """UPDATE growth.topics t SET group_id = :g
           WHERE t.company_id = :co AND t.group_id IS NULL AND t.order_ref = :o AND t.state = 'said'
             AND NOT EXISTS (SELECT 1 FROM growth.topics x
                             WHERE x.company_id = t.company_id AND x.group_id = :g
                               AND x.kind = t.kind AND x.norm = t.norm AND x.state = 'said')""",
        g=group_id, co=company_id, o=order_ref,
    )  # fmt: skip


async def count(tx: Tx, company_id: UUID, group_id: UUID) -> TopicCount:
    row = await tx.one(
        """SELECT count(*) FILTER (WHERE kind = 'topic') AS topics,
                  count(*) FILTER (WHERE kind = 'reference') AS refs
           FROM growth.topics WHERE company_id = :co AND group_id = :g AND state = 'said'""",
        co=company_id, g=group_id,
    )  # fmt: skip
    last = await tx.first(
        """SELECT title_fa, created_at FROM growth.topics
           WHERE company_id = :co AND group_id = :g AND state = 'said' AND kind = 'topic'
           ORDER BY created_at DESC LIMIT 1""",
        co=company_id, g=group_id,
    )  # fmt: skip
    return TopicCount(
        topics=int(row["topics"] or 0), references=int(row["refs"] or 0),
        last_fa=last["title_fa"] if last else None, last_at=last["created_at"] if last else None,
    )  # fmt: skip


async def brief_block(tx: Tx, company_id: UUID, group_id: UUID) -> str:
    """What a routine's work is told (appended to its brief by the groups' tick): what was
    already said, and that today's topic is claimed before anything is made."""
    scope = {"company_id": company_id, "group_id": group_id}
    said = [str(r["title_fa"])[:80] for r in await recent(tx, scope, "topic", BRIEF_TOPICS)]
    refs = [str(r["url"] or r["title_fa"])[:120]
            for r in await recent(tx, scope, "reference", BRIEF_REFERENCES)]  # fmt: skip
    lines = [
        "(Ledger: this working group never says a topic twice. When this routine makes a piece "
        "of content (a reel, a video, a post, an article): BEFORE writing or building, name "
        "today's topic with topic.claim {title_fa}; when the work uses an outside sample (a "
        "Pinterest pin), name it too with topic.claim {kind: reference, url, title_fa}. The hub "
        "refuses one that was said before (409 topic_taken names it): choose another and claim "
        "again. Leave `topic.txt` (the topic, one line) in the package. A routine that makes no "
        "content (a report, an analysis) skips this.",
    ]
    if said:
        lines.append("Already said, newest first: " + "؛ ".join(said) + ".")
    if refs:
        lines.append("Samples already used: " + " ".join(refs) + ".")
    return " ".join(lines) + ")"


async def of_package(
    tx: Tx, run: dict[str, Any], d: dict[str, Any], *, topic_txt: str | None, caption: str | None
) -> dict[str, Any] | None:
    """A package is about to go out on the owner's standing word. The run's own claim stands (it
    was checked when it was made; its output is noted). A run that named nothing is read by the
    hub: `topic.txt`, else the caption's first line, held to the same words only. Returns the
    row it collides with (the package is not sent by itself), else None."""
    scope = {"company_id": run["company_id"], "group_id": run["group_id"],
             "run_id": run["run_id"]}  # fmt: skip
    mine = (await of_run(tx, run["run_id"])).get("topic")
    if mine is not None:
        if not mine.get("output"):
            await tx.exec(
                "UPDATE growth.topics SET output = :o WHERE id = :id", id=mine["id"], o=d["ref"]
            )
        return None
    named = " ".join((topic_txt or "").split()[:40])
    first = next((ln.strip() for ln in (caption or "").splitlines() if ln.strip()), "")
    first = re.sub(r"[#@]\S+", " ", first).strip()
    title = (named or first)[:TITLE_MAX]
    if not title or not words(title):
        return None
    try:
        await claim(
            tx, scope, kind="topic", title=title, source="package", by="publish",
            work_ref=str(run.get("work_ref") or "") or None, output=d["ref"], exact=not named,
        )  # fmt: skip
    except ApiError as e:
        if e.code != "topic_taken":
            raise
        said = words(title, await brand_of(tx, run["company_id"]))
        return await taken_by(
            tx, scope, "topic", said, norm_of(said), but_run=run["run_id"], exact=not named
        )
    return None
