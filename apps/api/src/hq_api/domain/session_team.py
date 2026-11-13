"""⟨1.35⟩ §57 The session's team, one person at a time (the owner, 2026-11-13).

«میخوام … مستقیم بزنم روی کارمند باهاش توی یه فضای کوچیک حرف بزنم و ببندم و اون ادامه بده کارشو ولی
نمیخوام خیلی تو ابعاد گسترده باز باشه که انقدر بین اینا حرف بزنم گیج بشم»

    the team        `GET /orders/{ref}/team`: the holder first; the media seats of a content
                    session (scriptwriter, video_director, motion_designer: the person of the session
                    with that role, else empty); then the other people present (§39), players
                    excluded. Each seat: working (a run of theirs in the order's tree is queued or
                    running) or idle, the side talk's last line and how many of its lines are unread.
    a side talk     owner.session_side_lines: the owner's words to one person of the session and
                    that person's answers; never the main thread. The main session gets one step per
                    burst: when the same side's previous line of the seat is older than BURST.
    say             the word joins the person's open work of the order (it runs again now, the side
                    talk in its run's brief), else a side work is made for them under the order's
                    root, with a plan task of the owner's (as the session's «delegate» card does).
    the answers     while a person works a side work of the order (or a work a side word woke within
                    SIDE_WOKEN), their `order.ask` and `order.progress` on that order are side lines:
                    no main step, no owner's turn, no notification (`session.team` on the stream).
    hire            an empty media seat filled at once by the owner's own hire (by code, with his
                    approval's hard checks); the newcomer joins the session (§39).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from hq_api import events, pagination
from hq_api.db import Tx
from hq_api.domain import order_report as OR
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Page

OWNER_FA = "مدیر کل"
HOLDER_FA = "مسئول جلسه"
MEDIA_SEATS: tuple[tuple[str, str], ...] = (
    ("scriptwriter", "نویسنده"),
    ("video_director", "کارگردان"),
    ("motion_designer", "موشن‌گرافی"),
)
SEAT_ROLES = tuple(r for r, _ in MEDIA_SEATS)
# a media role already in the session makes it a content session
MEDIA_ROLES = frozenset(
    {*SEAT_ROLES, "media_director", "voice_producer", "visual_designer", "publisher",
     "content_analyst"}
)  # fmt: skip
BURST_MINUTES = 10
SIDE_WOKEN_MINUTES = 60
LAST_CHARS = 160
TEXT_MAX = 4000
STEP_CHARS = 80
BRIEF_LINES = 12
BRIEF_LINE_CHARS = 1000
SIDE_REASON = OR.SIDE_WORD_REASON
EVENT = "session.team"
HOLDER_SAY_FA = "با مسئول جلسه از همین جای نوشتن حرف بزن."
NOT_SEAT_FA = "این کس در تیم این جلسه نیست."
NO_ROOT_FA = "این جلسه هنوز کاری ندارد که حرف تو به آن برسد."
SEAT_FULL_FA = "این جایگاه پر است؛ با همان کس حرف بزن."
NO_COMPANY_FA = "شرکتِ این جلسه روشن نیست؛ برای آن کسی استخدام نمیشود."
NO_CHARTER_FA = "این نقش در این شرکت منشور ندارد."
EMPTY_FA = "متن خالی است."
OWNER_STEP_FA = "با {who}: {words}"
SEAT_STEP_FA = "جواب داد"
SIDE_BRIEF_FA = (
    "این گفتگوی کوتاه مدیر کل با توست در جلسه‌ی {ref}؛ جوابت را با order.ask یا order.progress "
    "بده: به همین گفتگو میرسد. کار تحویلی را deliver کن."
)
SO_FAR_FA = "## گفتگوی کوتاه تا اینجا"
SIDE_RULE = (
    "SIDE TALK: the owner spoke to you alone in session {ref}, apart from its main thread (its "
    "holder runs the session). Answer him in this run: `order.ask` for a question, "
    "`order.progress` for your reply; both reach only this side talk. Deliver what you make "
    "with `deliver`. Do not take over the session's plan or the holder's part."
)
HIRE_REFUSED_FA = {
    "envelope_exceeded": "پاکت ماه این شرکت جای این استخدام را ندارد؛ کسی استخدام نشد.",
    "envelope_required": "این شرکت پاکت ماه ندارد؛ کسی استخدام نشد.",
    "company_locked": "این شرکت قفل است؛ تا قفل باز نشود کسی استخدام نمیشود.",
    "rate_limited": "سقف استخدام امروز این شرکت پر شده است؛ کسی استخدام نشد.",
    "validation_failed": "مدل یا برآورد این نقش الان پذیرفته نیست؛ کسی استخدام نشد.",
}
PERSON_SQL = """SELECT e.id, e.code, e.role, e.kind, e.title_fa, e.company_id, c.code AS company,
                       c.kind AS company_kind, c.name_fa AS company_fa
                FROM core.employees e JOIN core.companies c ON c.id = e.company_id"""
LINE_COLS = "id, created_at, who, who_fa, text, work_ref"


# ------------------------------------------------------------------ shapes --
class TeamSeatEmployee(BaseModel):
    code: str
    title_fa: str
    company: str


class TeamSideLast(BaseModel):
    at: datetime
    who: Literal["owner", "seat"]
    text: str


class TeamSeat(BaseModel):
    """One chip of «تیم این جلسه»: `key` is the employee code when filled, `role:<role>` when
    empty; `holder`: the session's holder (no side talk: the main composer is his)."""

    key: str
    role: str | None = None
    role_fa: str
    holder: bool = False
    employee: TeamSeatEmployee | None = None
    state: Literal["working", "idle", "empty"]
    last: TeamSideLast | None = None
    unread: int = 0


class TeamNarrator(BaseModel):
    """§48's narrator of the order's company (the «گوینده» chip)."""

    company: str
    voice: str
    voice_fa: str
    style_fa: str | None = None


class SessionTeam(BaseModel):
    seats: list[TeamSeat]
    narrator: TeamNarrator | None = None


class SideLine(BaseModel):
    """One line of a side talk, newest last in a page."""

    id: int
    at: datetime
    who: Literal["owner", "seat"]
    who_fa: str
    text: str
    work_ref: str | None = None


class SayOut(BaseModel):
    line: SideLine
    work_ref: str
    woken: bool


# ----------------------------------------------------------------- helpers --
def who_fa(p: dict[str, Any]) -> str:
    """A person as the owner names them: their title, and their company outside the holding."""
    return OR.who_fa(p["title_fa"], None if p["company_kind"] == "holding" else p["company_fa"])


def _line(r: dict[str, Any]) -> SideLine:
    return SideLine(
        id=int(r["id"]), at=r["created_at"], who=r["who"], who_fa=r["who_fa"], text=r["text"],
        work_ref=r.get("work_ref"),
    )  # fmt: skip


async def _person_of_key(tx: Tx, key: str) -> dict[str, Any] | None:
    """The employee behind a persona key of the talk (`role@CODE`, or a fixed persona of the
    holding); None for a player, a system employee or nobody."""
    if key.startswith("player:"):
        return None
    if "@" in key:
        role, _, code = key.partition("@")
        row = await tx.first(
            PERSON_SQL
            + """ WHERE c.code = :co AND e.role = :r AND e.status = 'active'
                               AND e.kind <> 'system' ORDER BY e.hired_at LIMIT 1""",
            co=code,
            r=role,
        )
    else:
        row = await tx.first(
            PERSON_SQL
            + """ WHERE c.kind = 'holding' AND e.role = :r AND e.status = 'active'
                               AND e.kind <> 'system' ORDER BY e.hired_at LIMIT 1""",
            r=key,
        )
    return dict(row) if row is not None else None


async def _session(tx: Tx, ref: str) -> dict[str, Any]:
    """The order's report, the order, its tree, its holder (a person row with `work_id`), its
    talk and its company (the holder's, else the route's)."""
    from hq_api.domain import order_turns as OT

    rep = await OR.ensure(tx, ref)
    order = await OR.load_order(tx, ref) if rep is not None else None
    if rep is None or order is None:
        raise ApiError(404, "not_found", "unknown order", message_fa="این فرمان پیدا نشد.")
    works = await OR.tree(tx, OR.root_refs(order))
    h = await OT.holder(tx, ref)
    holder = None
    if h is not None:
        row = await tx.first(PERSON_SQL + " WHERE e.code = :c", c=h["code"])
        if row is not None:
            holder = {**dict(row), "work_id": h.get("work_id"), "key": OT.persona_key(h)}
    conv = None
    if rep.get("conversation_ref"):
        found = await tx.first(
            "SELECT present, holder FROM talk.conversations WHERE ref = :r",
            r=rep["conversation_ref"],
        )
        conv = dict(found) if found is not None else None
    company = (
        holder["company"]
        if holder is not None and holder["company_kind"] != "holding"
        else OR.route_company(rep)
    )
    return {
        "ref": ref, "rep": rep, "order": order, "works": works, "holder": holder, "conv": conv,
        "company": company,
    }  # fmt: skip


async def _people(tx: Tx, s: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(the people present but the holder, in the order they came; the people of the session's
    company who work a work of the order with a media seat's role)."""
    holder = s["holder"]
    conv = s["conv"] or {}
    skip = {conv.get("holder"), (holder or {}).get("key")}
    present: list[dict[str, Any]] = []
    for key in conv.get("present") or []:
        if key in skip:
            continue
        p = await _person_of_key(tx, str(key))
        if p is None or (holder is not None and p["code"] == holder["code"]):
            continue
        if all(x["code"] != p["code"] for x in present):
            present.append(p)
    tree: list[dict[str, Any]] = []
    for w in s["works"]:
        code = w["a_code"]
        if (
            not code
            or w["a_role"] not in SEAT_ROLES
            or w["company"] != s["company"]
            or (holder is not None and code == holder["code"])
            or any(x["code"] == code for x in [*present, *tree])
        ):
            continue
        row = await tx.first(PERSON_SQL + " WHERE e.code = :c AND e.status = 'active'", c=code)
        if row is not None:
            tree.append(dict(row))
    return present, tree


async def narrator_of(tx: Tx, company: str | None) -> TeamNarrator | None:
    from hq_api.domain import narrator as NR
    from hq_api.lines.adapters import tts

    if not company:
        return None
    cid = await tx.scalar("SELECT id FROM core.companies WHERE code = :c", c=company)
    row = await NR.of(tx, cid) if cid is not None else None
    if row is None:
        return None
    voice = str(row["voice"])
    trait = next((t for n, _, t in tts.DOCUMENTED if n == voice), None)
    return TeamNarrator(
        company=company, voice=voice, voice_fa=f"{voice} ({trait})" if trait else voice,
        style_fa=row["style_fa"] or None,
    )  # fmt: skip


async def _members(
    tx: Tx, s: dict[str, Any]
) -> tuple[list[dict[str, Any]], TeamNarrator | None, list[dict[str, Any]]]:
    """(the seats in order as {key, role, role_fa, holder, person}, the narrator, every person
    of the session but the holder)."""
    holder = s["holder"]
    present, tree = await _people(tx, s)
    narrator = await narrator_of(tx, s["company"])
    out: list[dict[str, Any]] = []
    if holder is not None:
        out.append({"key": holder["code"], "role": holder["role"], "role_fa": HOLDER_FA,
                    "holder": True, "person": holder})  # fmt: skip
    content = (
        (holder is not None and holder["role"] in MEDIA_ROLES)
        or any(p["role"] in MEDIA_ROLES for p in [*present, *tree])
        or bool(s["rep"].get("source_playbook"))
        or narrator is not None
    )
    used: set[str] = set()
    if content:
        for role, label in MEDIA_SEATS:
            if holder is not None and holder["role"] == role:
                continue  # the holder's own chip is this seat
            p = next((x for x in [*present, *tree] if x["role"] == role), None)
            if p is not None:
                used.add(p["code"])
            out.append({"key": p["code"] if p else f"role:{role}", "role": role, "role_fa": label,
                        "holder": False, "person": p})  # fmt: skip
    for p in present:
        if p["code"] not in used:
            out.append({"key": p["code"], "role": p["role"], "role_fa": p["title_fa"],
                        "holder": False, "person": p})  # fmt: skip
            used.add(p["code"])
    return out, narrator, [*present, *tree]


async def _in_burst(tx: Tx, order_id: Any, code: str, who: str) -> bool:
    """Whether the seat's previous line of this side (`owner` or `seat`) is within the burst."""
    return bool(
        await tx.scalar(
            """SELECT EXISTS (SELECT 1 FROM owner.session_side_lines
                 WHERE order_id = :o AND seat_code = :c AND who = :w
                   AND created_at > now() - make_interval(mins => :m))""",
            o=order_id,
            c=code,
            w=who,
            m=BURST_MINUTES,
        )
    )


async def _recent(tx: Tx, order_id: Any, code: str, n: int) -> list[dict[str, Any]]:
    rows = await tx.all(
        f"""SELECT {LINE_COLS} FROM owner.session_side_lines
            WHERE order_id = :o AND seat_code = :c ORDER BY id DESC LIMIT :n""",  # noqa: S608
        o=order_id,
        c=code,
        n=n,
    )
    return [dict(r) for r in reversed(rows)]


async def _insert(
    tx: Tx,
    rep: dict[str, Any],
    code: str,
    who: str,
    name: str,
    text: str,
    work: dict[str, Any] | None,
    *,
    made: bool = False,
) -> SideLine:
    row = await tx.one(
        f"""INSERT INTO owner.session_side_lines (company_id, order_id, seat_code, who, who_fa,
                text, work_id, work_ref, made_work)
            VALUES (:co, :o, :c, :w, :name, :t, :wid, :wref, :made)
            RETURNING {LINE_COLS}""",  # noqa: S608
        co=rep["company_id"],
        o=rep["order_id"],
        c=code,
        w=who,
        name=(name or OWNER_FA)[:200],
        t=text[:TEXT_MAX],
        wid=work["id"] if work else None,
        wref=str(work["ref"]) if work else None,
        made=made,
    )
    return _line(dict(row))


async def _emit(tx: Tx, ref: str, code: str) -> None:
    """`session.team {order, seat}` on the holding's stream (topic `orders`): the apps read the
    side talk again."""
    holding = await OR._holding(tx)
    await events.emit(tx, holding["code"], EVENT, ref, {"order": ref, "seat": code})


async def _busy(tx: Tx, work_id: Any) -> bool:
    return bool(
        await tx.scalar(
            """SELECT EXISTS (SELECT 1 FROM agents.runs WHERE work_id = :w
                 AND state IN ('queued', 'running'))""",
            w=work_id,
        )
    )


# ------------------------------------------------------------------ the team --
async def team(tx: Tx, ref: str) -> SessionTeam:
    """GET /orders/{ref}/team."""
    s = await _session(tx, ref)
    members, narrator, _ = await _members(tx, s)
    ids = [w["id"] for w in s["works"]]
    working: set[str] = set()
    if ids:
        working = {
            str(r["code"])
            for r in await tx.all(
                """SELECT DISTINCT e.code FROM agents.runs r
                   JOIN core.employees e ON e.id = r.employee_id
                   WHERE r.work_id = ANY(:ids) AND r.state IN ('queued', 'running')
                     AND r.trigger <> 'talk'""",
                ids=ids,
            )
        }
    order_id = s["rep"]["order_id"]
    last = {
        str(r["seat_code"]): dict(r)
        for r in await tx.all(
            """SELECT DISTINCT ON (seat_code) seat_code, created_at, who, text
               FROM owner.session_side_lines WHERE order_id = :o ORDER BY seat_code, id DESC""",
            o=order_id,
        )
    }
    unread = {
        str(r["seat_code"]): int(r["n"])
        for r in await tx.all(
            """SELECT l.seat_code, count(*) AS n FROM owner.session_side_lines l
               LEFT JOIN owner.session_side_reads x
                 ON x.order_id = l.order_id AND x.seat_code = l.seat_code
               WHERE l.order_id = :o AND l.who = 'seat' AND l.id > COALESCE(x.read_id, 0)
               GROUP BY l.seat_code""",
            o=order_id,
        )
    }
    seats: list[TeamSeat] = []
    for m in members:
        p = m["person"]
        if p is None:
            seats.append(
                TeamSeat(key=m["key"], role=m["role"], role_fa=m["role_fa"], state="empty")
            )
            continue
        code = str(p["code"])
        side = None if m["holder"] else last.get(code)
        seats.append(
            TeamSeat(
                key=code,
                role=m["role"],
                role_fa=m["role_fa"],
                holder=m["holder"],
                employee=TeamSeatEmployee(code=code, title_fa=p["title_fa"], company=p["company"]),
                state="working" if code in working else "idle",
                last=TeamSideLast(
                    at=side["created_at"],
                    who=side["who"],
                    text=" ".join(str(side["text"]).split())[:LAST_CHARS],
                )
                if side is not None
                else None,
                unread=0 if m["holder"] else unread.get(code, 0),
            )
        )
    return SessionTeam(seats=seats, narrator=narrator)


async def lines(
    tx: Tx, ref: str, code: str, *, limit: int = 50, before: str | None = None
) -> Page[SideLine]:
    """GET /orders/{ref}/team/{code}/lines: newest last; the newest page marks the seat read."""
    s = await _session(tx, ref)
    order_id = s["rep"]["order_id"]
    members, _, _ = await _members(tx, s)
    known = any(m["person"] is not None and m["key"] == code for m in members) or bool(
        await tx.scalar(
            """SELECT EXISTS (SELECT 1 FROM owner.session_side_lines
                 WHERE order_id = :o AND seat_code = :c)""",
            o=order_id,
            c=code,
        )
    )
    if not known:
        raise ApiError(404, "not_found", "not a seat of this session", message_fa=NOT_SEAT_FA)
    after = pagination.decode(before, 1)
    try:
        below = int(after[0]) if after else None
    except (TypeError, ValueError) as exc:
        raise ApiError(422, "validation_failed", fields={"before": "invalid"}) from exc
    rows = [
        dict(r)
        for r in await tx.all(
            f"""SELECT {LINE_COLS} FROM owner.session_side_lines
                WHERE order_id = :o AND seat_code = :c
                  AND (CAST(:b AS bigint) IS NULL OR id < CAST(:b AS bigint))
                ORDER BY id DESC LIMIT :n""",  # noqa: S608
            o=order_id,
            c=code,
            b=below,
            n=limit + 1,
        )
    ]
    more = len(rows) > limit
    rows = rows[:limit]
    nxt = pagination.encode([int(rows[-1]["id"])]) if more and rows else None
    if below is None and rows:
        await tx.exec(
            """INSERT INTO owner.session_side_reads (company_id, order_id, seat_code, read_id)
               VALUES (:co, :o, :c, :r)
               ON CONFLICT (order_id, seat_code) DO UPDATE
               SET read_id = GREATEST(owner.session_side_reads.read_id, EXCLUDED.read_id),
                   read_at = now()""",
            co=s["rep"]["company_id"],
            o=order_id,
            c=code,
            r=int(rows[0]["id"]),
        )
    return Page(items=[_line(r) for r in reversed(rows)], next_cursor=nxt)


# --------------------------------------------------------------------- say --
async def child_of_order(
    tx: Tx,
    who: Principal,
    parent: dict[str, Any],
    emp: dict[str, Any],
    *,
    title: str,
    brief: str,
    hold_parent: bool = True,
) -> dict[str, Any]:
    """A work of the order for `emp`: a child of the root in the root's company; in another
    company (or the holding) a work requested by the root, which the order's tree follows.
    `hold_parent=False` (a side work): the root goes on as it is."""
    if emp["company_id"] == parent["company_id"]:
        return await W.delegate(tx, who, parent, to_code=str(emp["code"]), title=title,
                                brief=brief, priority=None, due_at=None, budget=None,
                                hold_parent=hold_parent)  # fmt: skip
    return await W.create(
        tx,
        who,
        company_id=emp["company_id"],
        company_code=str(emp["company"]),
        title=title,
        brief=brief,
        kind="one_off",
        priority=str(parent["priority"]),
        assignee_code=str(emp["code"]),
        requested_by_work_id=parent["id"],
    )


def side_brief(ref: str, words: str, so_far: list[dict[str, Any]]) -> str:
    out = [words, ""]
    if so_far:
        out += [SO_FAR_FA]
        out += [f"{x['who_fa']}: {str(x['text'])[:BRIEF_LINE_CHARS]}" for x in so_far]
        out.append("")
    out.append(SIDE_BRIEF_FA.format(ref=ref))
    return "\n".join(out)[:40000]


async def _side_marked(tx: Tx, order_id: Any, code: str, ids: list[Any]) -> list[Any]:
    """The works among `ids` that are side works of this seat, or that a side word woke within
    SIDE_WOKEN_MINUTES (newest word first)."""
    if not ids:
        return []
    rows = await tx.all(
        """SELECT work_id, max(id) AS last FROM owner.session_side_lines
           WHERE order_id = :o AND seat_code = :c AND who = 'owner' AND work_id = ANY(:ids)
             AND (made_work OR created_at > now() - make_interval(mins => :m))
           GROUP BY work_id ORDER BY max(id) DESC""",
        o=order_id,
        c=code,
        ids=ids,
        m=SIDE_WOKEN_MINUTES,
    )
    return [r["work_id"] for r in rows]


async def say(ctx: Any, tx: Tx, ref: str, code: str, text: str) -> SayOut:
    """POST /orders/{ref}/team/{code}/say: the owner's word to one person of the session."""
    from hq_api.domain import order_turns as OT
    from hq_api.domain import sessions as SE

    words = text.strip()[:TEXT_MAX]
    if not words:
        raise ApiError(422, "validation_failed", fields={"text": "empty"}, message_fa=EMPTY_FA)
    await SE._open(tx, ref)  # 404, or 409 for an ended session (as /reply)
    s = await _session(tx, ref)
    rep, works = s["rep"], s["works"]
    if s["holder"] is not None and code == s["holder"]["code"]:
        raise ApiError(409, "validation_failed", "the holder's word is /reply",
                       message_fa=HOLDER_SAY_FA)  # fmt: skip
    members, _, _ = await _members(tx, s)
    m = next((x for x in members if x["person"] is not None and x["key"] == code), None)
    if m is None:
        raise ApiError(404, "not_found", "not a seat of this session", message_fa=NOT_SEAT_FA)
    p = m["person"]
    name = who_fa(p)
    order_id = rep["order_id"]
    burst = not await _in_burst(tx, order_id, code, "owner")
    so_far = await _recent(tx, order_id, code, BRIEF_LINES)
    mine = [w for w in works if w["a_code"] == code and w["status"] in W.OPEN]
    marked = await _side_marked(tx, order_id, code, [w["id"] for w in mine])
    target = next((w for wid in marked for w in mine if w["id"] == wid), None) or (
        mine[-1] if mine else None
    )
    made = target is None
    if target is not None:
        await W.event(tx, target, "side_word", ctx.who, {"order": ref, "text": words[:500]})
        work = target
    else:
        root_id = (s["holder"] or {}).get("work_id") or next(
            (w["id"] for w in works if w["is_root"]), None
        )
        if root_id is None:
            raise ApiError(409, "validation_failed", "the order has no work",
                           message_fa=NO_ROOT_FA)  # fmt: skip
        parent = await W.load(tx, root_id, lock=True)
        title = " ".join(words.split())[:300]
        work = await child_of_order(
            tx, ctx.who, parent, p, title=title, brief=side_brief(ref, words, so_far),
            hold_parent=False,
        )  # fmt: skip
        await SE.add_task(tx, rep, title_fa=title, by="owner", who_fa=name, who_code=code,
                          work_ref=str(work["ref"]))  # fmt: skip
    line = await _insert(tx, rep, code, "owner", OWNER_FA, words, work, made=made)
    if target is not None:
        await OT._wake_for_owner(tx, works, target, f"{SIDE_REASON}{ref}")
    woken = await _busy(tx, work["id"])
    if burst:
        first = " ".join(words.split())[:STEP_CHARS]
        await OR._append_steps(
            tx, rep["id"], [OR._step(OWNER_FA, OWNER_STEP_FA.format(who=name, words=first))]
        )
    await _emit(tx, ref, code)
    return SayOut(line=line, work_ref=str(work["ref"]), woken=woken)


# ------------------------------------------------------------- the answers --
async def side_work_of(tx: Tx, ref: str, who: Principal) -> dict[str, Any] | None:
    """§57.4 The side work of the order the agent answers from: its run's work when that is one,
    else (a run without a work) its open side work. None: its words go to the main thread."""
    if not who.is_agent:
        return None
    if not await tx.scalar(
        """SELECT EXISTS (SELECT 1 FROM owner.session_side_lines l
             JOIN owner.order_reports r ON r.order_id = l.order_id
             WHERE r.ref = :r AND l.seat_code = :c AND l.who = 'owner')""",
        r=ref,
        c=who.code,
    ):
        return None  # nobody spoke to them aside in this session: the main thread
    rep = await tx.first("SELECT order_id FROM owner.order_reports WHERE ref = :r", r=ref)
    order = await OR.load_order(tx, ref) if rep is not None else None
    if rep is None or order is None:
        return None
    mine = [w for w in await OR.tree(tx, OR.root_refs(order)) if w["a_code"] == who.code]
    if not mine:
        return None
    run_work = None
    if who.run_id:
        run_work = await tx.scalar(
            "SELECT work_id FROM agents.runs WHERE id = CAST(:r AS uuid) AND employee_id = :e",
            r=who.run_id,
            e=who.employee_id,
        )
    own = [w for w in mine if w["id"] == run_work]
    candidates = own or [w for w in mine if w["status"] in W.OPEN]
    marked = await _side_marked(tx, rep["order_id"], who.code, [w["id"] for w in candidates])
    return next((w for wid in marked for w in candidates if w["id"] == wid), None)


async def answer(tx: Tx, ref: str, who: Principal, text: str, work: dict[str, Any]) -> None:
    """The person's `order.ask` / `order.progress` from a side work: a side line, and one main
    step «… جواب داد» per burst."""
    rep = await OR.ensure(tx, ref)
    if rep is None:
        return
    row = await tx.first(PERSON_SQL + " WHERE e.code = :c", c=who.code)
    name = who_fa(dict(row)) if row is not None else who.code
    burst = not await _in_burst(tx, rep["order_id"], who.code, "seat")
    await _insert(tx, rep, who.code, "seat", name, " ".join(text.split()), work)
    if burst:
        await OR._append_steps(tx, rep["id"], [OR._step(name, SEAT_STEP_FA)])
    await _emit(tx, ref, who.code)


async def run_brief(tx: Tx, rep: dict[str, Any], work_id: Any) -> dict[str, Any] | None:
    """For a run of a side work (or of a work a side word woke within SIDE_WOKEN_MINUTES): the
    side talk's last lines and how to answer; None otherwise."""
    row = await tx.first(
        """SELECT seat_code FROM owner.session_side_lines
           WHERE order_id = :o AND work_id = :w AND who = 'owner'
             AND (made_work OR created_at > now() - make_interval(mins => :m))
           ORDER BY id DESC LIMIT 1""",
        o=rep["order_id"],
        w=work_id,
        m=SIDE_WOKEN_MINUTES,
    )
    if row is None:
        return None
    talk = await _recent(tx, rep["order_id"], str(row["seat_code"]), BRIEF_LINES)
    return {
        "with": OWNER_FA,
        "lines": [f"{x['who_fa']}: {str(x['text'])[:BRIEF_LINE_CHARS]}" for x in talk],
        "rule": SIDE_RULE.format(ref=rep["ref"]),
    }


# -------------------------------------------------------------------- hire --
async def hire(ctx: Any, tx: Tx, ref: str, role: str) -> SessionTeam:
    """POST /orders/{ref}/team/hire: an empty media seat filled at once, the owner's own hire in
    his session (by code with `owner_order`: the model offered, the estimate, the five a day);
    the role's charter defaults (model, effort) and 30 runs as the monthly estimate. A hard check
    that refuses answers its own code; nothing is made. An active employee of that role in the
    session's company who is not in it yet comes in instead (nobody new is hired)."""
    from hq_api.domain import decisions as D
    from hq_api.domain import hiring
    from hq_api.domain import sessions as SE

    rep = await SE._open(tx, ref)
    s = await _session(tx, ref)
    _, _, people = await _members(tx, s)
    holder = s["holder"]
    if (holder is not None and holder["role"] == role) or any(p["role"] == role for p in people):
        raise ApiError(409, "validation_failed", "the seat is filled", message_fa=SEAT_FULL_FA)
    company = await ctx.hub.companies.find(s["company"]) if s["company"] else None
    if company is None or company.kind == "holding":
        raise ApiError(409, "validation_failed", "the session has no company",
                       message_fa=NO_COMPANY_FA)  # fmt: skip
    have = await tx.first(
        PERSON_SQL
        + """ WHERE e.company_id = :co AND e.role = :r AND e.status = 'active'
                           AND e.kind <> 'system' ORDER BY e.hired_at LIMIT 1""",
        co=company.id,
        r=role,
    )
    if have is not None:
        # the company has that person already: they come into this session, nobody new is hired
        await SE.add_participant(ctx, tx, ref, "person", f"{role}@{company.code}")
        await ctx.audit(tx, company_id=company.id, action="session.participant",
                        action_class="A1", target_kind="order", target_ref=ref,
                        summary=f"+{have['code']} for the empty {role} seat")  # fmt: skip
        return await team(tx, ref)
    lib = await D.company_charters(tx, ctx.hub.charters, company.id)
    charter = lib.get(role) if lib is not None else None
    if charter is None or charter.kind != "employee" or not charter.department:
        raise ApiError(422, "validation_failed", fields={"role": f"no employee charter {role}"},
                       message_fa=NO_CHARTER_FA)  # fmt: skip
    reason = f"استخدام به خواست مدیر کل در جلسه‌ی {ref}"
    payload = {
        "company": company.code,
        "department": charter.department,
        "role": role,
        "title_fa": charter.title_fa[:200],
        "title_en": charter.title_en[:200],
        "reason": reason,
        "model": charter.model,
        "effort": charter.effort,
        "quota_estimate_month": {"tokens": int(charter.limits.tokens_per_run) * 30},
    }
    try:
        d = await D.propose(
            tx,
            ctx.who,
            company_id=company.id,
            company_code=company.code,
            body=D.DecisionIn(kind="hire", title=f"استخدام: {charter.title_fa}"[:300],
                              what=reason, why=reason, risk="low", payload=payload),
            thread_code=None,
            charters=ctx.hub.charters,
            company_kind=company.kind,
            notify_owner=False,
        )  # fmt: skip
        d = await hiring.approve_by_code(tx, d, ctx.hub.charters, owner_order=ref)
    except ApiError as exc:
        exc.message_fa = exc.message_fa or HIRE_REFUSED_FA.get(exc.code)
        raise
    emp = await tx.one(
        "SELECT code, title_fa FROM core.employees WHERE hired_by_decision_id = :d", d=d["id"]
    )
    conv = await SE._conversation(ctx, tx, ref, rep)
    await SE.join_hired(tx, str(emp["code"]), role, company.code, str(emp["title_fa"]),
                        conversation_id=conv["id"])  # fmt: skip
    await ctx.audit(tx, company_id=company.id, action="session.hire", action_class="A2",
                    target_kind="employee", target_ref=str(emp["code"]),
                    summary=f"{role} for {company.code} in session {ref} ({d['ref']})")  # fmt: skip
    return await team(tx, ref)
