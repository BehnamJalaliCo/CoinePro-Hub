"""The player of an order and the council of models (contract §27.1-§27.2
⟨1.9⟩, prompt 18), in the caller's transaction.

The player (`work.player`):
  auto      the LLM Router picks, as always.
  claude    the Claude models through the router (the assignee's own run).
  gpt · gemini · deepseek
            every model call of the work goes to that substitute player: the
            assignee's run hands the work's brief to the player's text seat
            (§21.13: the seat's daily cap, the same masking and data guard)
            and the player's answer becomes the work's deliverable, labelled
            with its source. A player that is signed out, limited or off: the
            work waits (`player_wait_since`, retried every few minutes) up to
            30 minutes, then falls back to auto (a notification and a work
            event say so; the assignee's Claude run picks it up).
The council (`work.mode = council`, at the order's root):
  members   Claude (the assignee's own run, its deliverable) and every
            substitute player whose text seat is ready (a seat call each);
            one that is not, or would pass its seat's cap, is `skipped` with
            its reason. A media order (`work.media`) asks every player that
            can make the kind for its own Creative instead; the owner picks
            one (and may animate a picked image into a video).
  synthesis once every member ended, Claude writes it: a child work of the
            same assignee with every answer in full; its deliverable is the
            synthesis (agree / differ and why / recommendation / each answer).
Every change of a council is a `work.council` event (topic `work`). The
worker's Maintenance (every 5 minutes) runs `sweep`: the worker's role
queues the retried and fallen-back runs.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import notify
from hq_api.domain import substitutes as S
from hq_api.principal import Principal

PLAYERS = ("auto", "claude", "gpt", "gemini", "deepseek")
SUBSTITUTES = ("gpt", "gemini", "deepseek")
WAIT = timedelta(minutes=30)
RETRY = timedelta(minutes=5)
# A work's text goes to the first of these seats the player holds and has on.
TEXT_SEATS = ("content_draft", "long_read", "third_opinion", "assistant_errand", "quick_search")
SERVICE = Principal(kind="service", code="players", role="service")
FINAL_MEMBER = ("done", "failed", "skipped")
PLAYER_FA = {"claude": "Claude", "gpt": "ChatGPT", "gemini": "Gemini", "deepseek": "DeepSeek"}
# Voice orders (§27.1): «با جی‌پی‌تی / با جمنای / با دیپ‌سیک / شورا».
VOICE_PLAYERS = (
    (
        "gpt",
        re.compile(
            r"با\s*(?:جی\s*‌?\s*پی\s*‌?\s*تی|چت\s*‌?\s*جی\s*‌?\s*پی\s*‌?\s*تی|gpt|chatgpt)", re.I
        ),
    ),
    ("gemini", re.compile(r"با\s*(?:جمنای|جمینای|جیمینای|gemini)", re.I)),
    ("deepseek", re.compile(r"با\s*(?:دیپ\s*‌?\s*سیک|deepseek)", re.I)),
    ("claude", re.compile(r"با\s*(?:کلود|claude)", re.I)),
)
VOICE_COUNCIL = re.compile(r"(?:^|\s)(?:با\s*)?شورا(?:ی\s*مدل‌ها)?(?:\s|$|[،.؟!])")


class Member(BaseModel):
    player: str
    model: str | None = None
    state: Literal["queued", "working", "done", "failed", "skipped"]
    run_id: str | None = None
    deliverable_ref: str | None = None
    # ⟨1.10⟩ §28.4 always plain Persian (never a provider's raw text: that
    # stays in the call's run log); `reason_code` is the machine's word
    reason: str | None = None
    reason_code: str | None = None
    # ⟨additive⟩ a media council's version (Creative) of this player
    creative_ref: str | None = None


class Council(BaseModel):
    work_ref: str
    members: list[Member]
    synthesis_ref: str | None
    state: Literal["running", "synthesising", "done", "failed"]
    media: Literal["image", "video"] | None = None
    # ⟨1.10⟩ §28.4 said plainly when fewer than two answered (no synthesis then)
    note_fa: str | None = None


# ----------------------------------------------------------- reasons (§28.4) --
REASON_FA = {
    "off": "این بازیکن خاموش است یا جایگاهش بسته است.",
    "signed_out": "این بازیکن وارد حسابش نشده است؛ مالک باید وارد شود.",
    "expired": "ورود این بازیکن منقضی شده است؛ مالک باید دوباره وارد شود.",
    "limited": "سهمیه‌ی اشتراک این بازیکن فعلاً تمام شده است.",
    "per_day": "سقف روزانه‌ی این جایگاه پر شده است.",
    "holding_locked": "کلید توقف هلدینگ روشن است؛ هیچ بازیکنی صدا زده نمیشود.",
    "error": "صفحه‌ی وب این بازیکن در کار قبلی دو بار خطا داد؛ تا بررسی دستورالعمل کنار گذاشته شده است.",
    "recipe_failed": (
        "صفحه‌ی وب این بازیکن عوض شده و دستورالعمل خودکار کار نکرد "
        "(یک بار با بارگذاری دوباره‌ی صفحه امتحان شد). تصویر صفحه برای ناظر پیوست شد."
    ),
    "recipe_retry": "صفحه‌ی وب این بازیکن خطا داد؛ با بارگذاری دوباره‌ی صفحه دوباره امتحان میشود.",
    "timeout": "این بازیکن در زمان مقرر جواب نداد.",
    "busy": "این بازیکن مشغول کار دیگری بود.",
    "policy_denied": "متن کار داده‌ای دارد که به بازیکن بیرونی نمیرود؛ Claude خودش انجامش میدهد.",
    "unavailable": "این بازیکن در دسترس نیست.",
    "failed": "این بازیکن خطا داد و جوابی نداد.",
    "cancelled": "این کار لغو شد.",
    "claude_failed": "Claude این کار را تمام نکرد.",
}


def reason_of(raw: str | None, model: str | None = None) -> tuple[str | None, str | None]:
    """(code, Persian sentence) of a call's or member's reason; a provider's
    raw text never reaches the member."""
    if not raw:
        return None, None
    text = str(raw)
    low = text.lower()
    if low.startswith("model_refused") or S.refused_model(text):
        m = re.search(r"model_refused:\s*([A-Za-z0-9._-]+)", text)
        name = m.group(1) if m else (model or "")
        retried = "retried" in low
        fa = f"مدل {name} با اشتراک این بازیکن پشتیبانی نمیشود"
        fa += "؛ با مدل پیش‌فرض دوباره امتحان شد." if retried else "."
        return "model_refused", fa
    if low.startswith("policy_denied"):
        return "policy_denied", REASON_FA["policy_denied"]
    if low.startswith("recipe_failed") and "retrying" in low:
        return "recipe_retry", REASON_FA["recipe_retry"]
    code = re.split(r"[:\s;]", low, maxsplit=1)[0] or "failed"
    for key in REASON_FA:
        if code == key:
            return key, REASON_FA[key]
    if code in ("locked", "launch_gate", "kill_switch") or "lock" in code:
        return "holding_locked", REASON_FA["holding_locked"]
    return "failed", REASON_FA["failed"]


def _set_reason(m: dict[str, Any], raw: str | None, model: str | None = None) -> None:
    code, fa = reason_of(raw, model)
    m["reason_code"], m["reason"] = code, fa


# ------------------------------------------------------------- voice orders --
def from_voice(text: str) -> tuple[str | None, str | None]:
    """(player, mode) an order names in words, or (None, None)."""
    mode = "council" if VOICE_COUNCIL.search(text or "") else None
    for player, rx in VOICE_PLAYERS:
        if rx.search(text or ""):
            return player, mode
    return None, mode


# ------------------------------------------------------------------ seats --
async def text_seat(tx: Tx, player: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """(player row, seat row) of the player's text seat: the first of
    TEXT_SEATS it holds and has on, else the first it holds."""
    held = None
    for seat in TEXT_SEATS:
        found = await S.holder(tx, seat, player)
        if found is None:
            continue
        if found[1]["enabled"]:
            return found
        held = held or found
    return held


async def availability(tx: Tx, player: str, now: datetime | None = None) -> str | None:
    """None when the player can take a text call now, else why not."""
    found = await text_seat(tx, player)
    if found is None:
        return "off"
    return S._skip_reason(found[0], found[1], now or datetime.now(UTC))


def brief_of(w: dict[str, Any]) -> str:
    return (
        f"# {w['title']}\n\n{w['brief'] or ''}\n\n"
        "Answer in Persian unless the task says otherwise. Give the conclusion first, then the "
        "reasoning and the steps; say plainly what you could not check."
    )


# ----------------------------------------------------------------- player --
async def player_turn(tx: Tx, hub: Any, run: dict[str, Any]) -> str | None:
    """Before the assignee's run of a work whose player is a substitute: the
    work goes to that player (`player_call`), or waits for it
    (`player_waiting`). None: the run goes on as usual (auto, claude, a
    council's own Claude member, a fallen-back work)."""
    w = await tx.first(
        """SELECT w.*, c.code AS company FROM work.work w JOIN core.companies c ON c.id = w.company_id
           WHERE w.id = :id FOR UPDATE OF w""",
        id=run["work_id"],
    )
    if (
        w is None
        or w["player"] not in SUBSTITUTES
        or w["player_fallback_at"] is not None
        or w["mode"] == "council"
        or w["status"] not in ("queued", "in_progress", "waiting")
    ):
        return None
    if await tx.scalar(
        """SELECT 1 FROM substitutes.calls WHERE purpose_kind = 'work' AND purpose_ref = :r
             AND state IN ('queued', 'running')""",
        r=w["ref"],
    ):
        return "player_call"
    found = await text_seat(tx, w["player"])
    text = brief_of(w)
    reason = await S.guard(tx, hub, found[1]["seat"] if found else "content_draft", text)
    if reason is not None:
        # The data guard refuses the brief for any substitute: Claude does it.
        await fall_back(tx, w, f"policy_denied: {reason}")
        return None
    call = await S.seat_call(
        tx,
        hub,
        SERVICE,
        seat=found[1]["seat"] if found else "content_draft",
        input_md=text,
        company_id=w["company_id"],
        purpose=("work", w["ref"]),
        player=w["player"],
    )
    if call["state"] == "queued":
        await tx.exec(
            """UPDATE work.work SET player_wait_since = NULL, player_tried_at = now(),
                   status = CASE WHEN status = 'queued' THEN 'in_progress' ELSE status END
               WHERE id = :id""",
            id=w["id"],
        )
        await _event(tx, w, "player_call", {"player": w["player"], "call": str(call["id"])})
        return "player_call"
    await tx.exec(
        """UPDATE work.work SET player_wait_since = COALESCE(player_wait_since, now()),
               player_tried_at = now() WHERE id = :id""",
        id=w["id"],
    )
    await _event(tx, w, "player_waiting", {"player": w["player"], "reason": call["state_reason"]})
    return "player_waiting"


async def _event(tx: Tx, w: dict[str, Any], kind: str, data: dict[str, Any]) -> None:
    from hq_api.domain import work as W

    await W.event(tx, w, kind, SERVICE, data)
    await events.emit(tx, w["company"], "work.updated", w["ref"], {kind: True, **data})


async def fall_back(tx: Tx, w: dict[str, Any], why: str) -> None:
    """The named player is not available (30 minutes, or refused): the work
    goes on with auto; a notification and a work event say so."""
    await tx.exec(
        """UPDATE work.work SET player_fallback_at = now(), player_wait_since = NULL WHERE id = :id
             AND player_fallback_at IS NULL""",
        id=w["id"],
    )
    await _event(tx, w, "player_fallback", {"player": w["player"], "reason": why[:200]})
    name = PLAYER_FA.get(w["player"], w["player"])
    await notify.raise_notification(
        tx,
        company_id=w["company_id"],
        company_code=w["company"],
        level="info",
        title_fa=f"{w['ref']} با {name} انجام نشد؛ با انتخاب خودکار ادامه یافت",
        body_fa=f"{name} در دسترس نبود ({why[:120]}). کار با مدل‌های خود هاب ادامه پیدا کرد.",
        link_kind="work",
        link_ref=w["ref"],
        source_kind="system",
        source_code="players",
    )
    if w.get("assignee_id"):
        await tx.exec(
            "SELECT agents.queue_run(:e, 'work', :w, NULL, 'player_fallback', NULL)",
            e=w["assignee_id"],
            w=w["id"],
        )


# ⟨1.10.1⟩ nothing is cut: a text longer than the place it goes is kept whole
# in the file store, attached, with its head in place
BODY_LIMIT = 480_000  # a deliverable's body (the column holds 500 000)
BRIEF_LIMIT = 48_000  # a work's brief (the column holds 50 000)


async def store_text(tx: Tx, hub: Any, company_id: UUID, name: str, text: str) -> UUID:
    data = text.encode("utf-8")
    key, sha = await hub.storage.put(data)
    fid: UUID = await tx.scalar(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key,
               created_by_kind, created_by_code)
           VALUES (:co, :name, 'text/markdown', :size, :sha, :key, 'service', 'players')
           RETURNING id""",
        co=company_id,
        name=name[:200],
        size=len(data),
        sha=sha,
        key=key,
    )
    return fid


async def deliver(
    tx: Tx,
    w: dict[str, Any],
    *,
    title: str,
    body: str,
    produced_with: dict[str, Any],
    hub: Any = None,
) -> dict[str, Any]:
    """A deliverable on the work from its assignee (what a player made, or a
    council's synthesis), the work delivered, its delivered children done. A
    body longer than the column goes whole into an attachment (with `hub`)."""
    from hq_api.domain import work as W

    attachments: list[str] = []
    if len(body) > BODY_LIMIT and hub is not None:
        fid = await store_text(tx, hub, w["company_id"], f"{w['ref']}-full.md", body)
        attachments.append(str(fid))
        body = body[:BODY_LIMIT] + "\n\n… متن کامل (بی‌هیچ برش) در فایل پیوست همین خروجی است."
    dl = await tx.one(
        """INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title, summary, body,
               attachments, produced_with, usage, evidence)
           VALUES (:co, :w, :p, :title, :summary, :body, CAST(:att AS uuid[]), CAST(:pw AS jsonb),
                   '{}', '[]')
           RETURNING id, ref""",
        co=w["company_id"],
        w=w["id"],
        p=w["assignee_id"],
        title=title[:300],
        summary=body.strip().split("\n", 1)[0][:500],
        body=body,
        att=attachments,
        pw=json.dumps(produced_with, ensure_ascii=False),
    )
    await W.set_status(tx, w, "delivered", delivered_at=datetime.now(UTC))
    closed = await W.close_delivered_children(tx, w, SERVICE)
    await W.event(
        tx, w, "delivered", SERVICE, {"deliverable": dl["ref"], "closed_children": closed}
    )
    await events.emit(
        tx,
        w["company"],
        "deliverable.created",
        dl["ref"],
        {"work": w["ref"], "producer": "players"},
    )
    await events.emit(tx, w["company"], "work.updated", w["ref"], {"status": "delivered"})
    if w["parent_id"] is None:
        await notify.raise_notification(
            tx,
            company_id=w["company_id"],
            company_code=w["company"],
            level="info",
            title_fa=f"خروجی تازه {dl['ref']}: {title[:120]}",
            link_kind="deliverable",
            link_ref=dl["ref"],
            source_kind="system",
            source_code="players",
        )
    return dict(dl)


async def on_call(tx: Tx, hub: Any, call: dict[str, Any]) -> None:
    """A substitute call of a work or a council finished (or ended)."""
    if call["purpose_kind"] == "work":
        await _work_call(tx, hub, call)
    elif call["purpose_kind"] == "council":
        c = await _council_by_ref(tx, str(call["purpose_ref"]))
        if c is not None:
            await refresh(tx, hub, c)


async def _work_call(tx: Tx, hub: Any, call: dict[str, Any]) -> None:
    from hq_api.domain import work as W

    w = await W.load_ref(tx, str(call["purpose_ref"]))
    if w["status"] not in W.OPEN or w["player_fallback_at"] is not None:
        return
    res = call.get("result") or {}
    if call["state"] == "done" and res.get("text_md"):
        name = PLAYER_FA.get(call["player"], call["player"])
        await deliver(
            tx,
            w,
            title=w["title"],
            body=await S.full_text(tx, hub, res),
            produced_with={
                "player": call["player"],
                "model": call["model"],
                "label_fa": f"انجام‌شده با {name}",
                "source": S.source(call),
                "substitute_call": str(call["id"]),
            },
            hub=hub,
        )
        return
    await tx.exec(
        """UPDATE work.work SET player_wait_since = COALESCE(player_wait_since, now()),
               player_tried_at = now() WHERE id = :id""",
        id=w["id"],
    )
    await _event(
        tx,
        w,
        "player_waiting",
        {"player": w["player"], "reason": call["state_reason"] or call["state"]},
    )


async def sweep(tx: Tx, hub: Any, now: datetime | None = None) -> dict[str, int]:
    """Waiting players: after 30 minutes the work falls back to auto; before,
    it is tried again every few minutes. A call that ended without an answer
    puts its work back in the wait. Open councils are brought up to date."""
    from hq_api.domain import work as W

    now = now or datetime.now(UTC)
    out = {"fallback": 0, "retried": 0, "councils": 0}
    for w in await tx.all(
        W.WORK_SQL  # noqa: S608 - module constants; values are bound
        + """ WHERE w.player = ANY(:subs) AND w.player_fallback_at IS NULL AND w.mode = 'single'
                AND w.status = ANY(:open)
                AND (w.player_wait_since IS NOT NULL OR NOT EXISTS (
                     SELECT 1 FROM substitutes.calls x WHERE x.purpose_kind = 'work'
                       AND x.purpose_ref = w.ref AND x.state IN ('queued', 'running', 'done')))
                AND w.player_tried_at IS NOT NULL
              ORDER BY w.created_at LIMIT 200""",
        subs=list(SUBSTITUTES),
        open=list(W.OPEN),
    ):
        since = w["player_wait_since"] or w["player_tried_at"]
        if now - since >= WAIT:
            await fall_back(tx, w, "unavailable for 30 minutes")
            out["fallback"] += 1
        elif now - w["player_tried_at"] >= RETRY and w["assignee_id"]:
            await tx.exec(
                "SELECT agents.queue_run(:e, 'work', :w, NULL, 'player_retry', NULL)",
                e=w["assignee_id"],
                w=w["id"],
            )
            out["retried"] += 1
    for c in await tx.all(
        "SELECT * FROM work.councils WHERE state IN ('running', 'synthesising') ORDER BY created_at LIMIT 100"
    ):
        if await refresh(tx, hub, c):
            out["councils"] += 1
    return out


# ---------------------------------------------------------------- council --
COUNCIL_SQL = """
    SELECT k.*, w.ref AS work_ref, w.media, sw.ref AS synthesis_work_ref
    FROM work.councils k JOIN work.work w ON w.id = k.work_id
    LEFT JOIN work.work sw ON sw.id = k.synthesis_work_id
"""


async def _council_by_ref(tx: Tx, work_ref: str) -> dict[str, Any] | None:
    return await tx.first(COUNCIL_SQL + " WHERE w.ref = :r FOR UPDATE OF k", r=work_ref)


async def council_of(tx: Tx, work_id: UUID) -> dict[str, Any] | None:
    return await tx.first(COUNCIL_SQL + " WHERE k.work_id = :w", w=work_id)


def render(c: dict[str, Any]) -> Council:
    members = []
    for m in c["members"] or []:
        m = dict(m)
        if m.get("reason") and not m.get("reason_code"):
            _set_reason(m, m["reason"], m.get("model"))  # a council from before ⟨1.10⟩
        members.append(Member(**m))
    return Council(
        work_ref=c["work_ref"],
        members=members,
        synthesis_ref=c["synthesis_ref"],
        state=c["state"],
        media=c.get("media"),
        note_fa=c.get("note_fa"),
    )


async def start_council(tx: Tx, hub: Any, w: dict[str, Any]) -> dict[str, Any]:
    """The council of an order: Claude (its assignee's own run) and every
    ready substitute player; a media order asks every player that can make
    the kind for its own Creative."""
    if (existing := await council_of(tx, w["id"])) is not None:
        return existing
    members: list[dict[str, Any]] = []
    media = w.get("media")
    if media:
        members += await _media_members(tx, hub, w, media)
    else:
        members.append({"player": "claude", "model": None, "state": "queued"})
        text = brief_of(w)
        for p in SUBSTITUTES:
            members.append(await _text_member(tx, hub, w, p, text))
    await tx.exec(
        """INSERT INTO work.councils (company_id, work_id, members)
           VALUES (:co, :w, CAST(:m AS jsonb))""",
        co=w["company_id"],
        w=w["id"],
        m=json.dumps(members, ensure_ascii=False),
    )
    c = await council_of(tx, w["id"])
    assert c is not None
    await _emit(tx, w["company"], c)
    await refresh(tx, hub, c)
    return await council_of(tx, w["id"]) or c


async def _text_member(tx: Tx, hub: Any, w: dict[str, Any], p: str, text: str) -> dict[str, Any]:
    found = await text_seat(tx, p)
    if found is None:
        return _member(p, None, "skipped", "off")
    reason = S._skip_reason(found[0], found[1], datetime.now(UTC))
    if reason is not None:
        return _member(p, found[1]["model"], "skipped", reason)
    guard = await S.guard(tx, hub, found[1]["seat"], text)
    if guard is not None:
        return _member(p, found[1]["model"], "skipped", f"policy_denied: {guard}")
    call = await S.seat_call(
        tx,
        hub,
        SERVICE,
        seat=found[1]["seat"],
        input_md=text,
        company_id=w["company_id"],
        purpose=("council", w["ref"]),
        player=p,
    )
    if call["state"] != "queued":
        # the seat's daily cap, a lock, ...: the envelope's rule (§27.2)
        return _member(p, call["model"], "skipped", call["state_reason"])
    return {"player": p, "model": call["model"], "state": "queued", "call_id": str(call["id"])}


def _member(player: str, model: str | None, state: str, raw: str | None) -> dict[str, Any]:
    m: dict[str, Any] = {"player": player, "model": model, "state": state}
    _set_reason(m, raw, model)
    return m


async def _media_members(tx: Tx, hub: Any, w: dict[str, Any], media: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    placement = "instagram_story" if media == "video" else "instagram_post"
    for p in SUBSTITUTES:
        caps = S.DEFAULT_PLAYERS[p]["capabilities"]
        if caps.get(media, "off") == "off":
            continue
        row = await S.create_creative(
            tx,
            hub,
            SERVICE,
            company_id=w["company_id"],
            kind=media,
            brief_md=(w["brief"] or w["title"])[:4000],
            prompt_md=S.template_prompt(
                w["brief"] or w["title"], placement, media, 6 if media == "video" else None
            ),
            placement=placement,
            overlay=None,
            duration_s=6 if media == "video" else None,
            player=p,
            work_id=w["id"],
        )
        m = {
            "player": p,
            "model": row["model"],
            "state": "failed" if row["state"] == "failed" else "queued",
            "creative_ref": row["ref"],
        }
        if row["state"] == "failed":
            call = await tx.first(
                "SELECT state_reason FROM substitutes.calls WHERE id = :id", id=row["call_id"]
            )
            _set_reason(m, (call or {}).get("state_reason") or "failed", row["model"])
        out.append(m)
    return out


async def refresh(tx: Tx, hub: Any, c: dict[str, Any]) -> bool:
    """Bring a council's members up to date from their calls, creatives and
    deliverables; start the synthesis once every member ended; close it
    when the synthesis is delivered. True when anything changed."""
    from hq_api.domain import work as W

    c = await tx.first(COUNCIL_SQL + " WHERE k.id = :id FOR UPDATE OF k", id=c["id"]) or c
    if c["state"] in ("done", "failed"):
        return False
    w = await W.load(tx, c["work_id"])
    members = [dict(m) for m in c["members"] or []]
    for m in members:
        if m["state"] in FINAL_MEMBER:
            continue
        if m["player"] == "claude":
            dl = await tx.first(
                """SELECT ref FROM cartable.deliverables WHERE work_id = :w AND producer_id = :p
                   ORDER BY created_at LIMIT 1""",
                w=w["id"],
                p=w["assignee_id"],
            )
            run = await tx.scalar(
                "SELECT id FROM agents.runs WHERE work_id = :w ORDER BY queued_at DESC LIMIT 1",
                w=w["id"],
            )
            m["run_id"] = str(run) if run else m.get("run_id")
            if dl is not None:
                m.update(state="done", deliverable_ref=dl["ref"])
            elif w["status"] in ("failed", "cancelled"):
                m["state"] = "failed"
                _set_reason(m, "claude_failed" if w["status"] == "failed" else "cancelled")
            elif run is not None:
                m["state"] = "working"
        elif m.get("call_id"):
            call = await tx.first(
                """SELECT state, state_reason, model, attempt FROM substitutes.calls
                   WHERE id = CAST(:id AS uuid)""",
                id=m["call_id"],
            )
            if call is not None:
                st = {"queued": "queued", "running": "working", "done": "done"}.get(
                    call["state"], call["state"]
                )
                m["state"] = (
                    st if st in ("queued", "working", "done", "failed", "skipped") else "failed"
                )
                m["model"] = call["model"] or m.get("model")
                if m["state"] in ("failed", "skipped"):
                    _set_reason(m, call["state_reason"] or "failed", call["model"])
                elif call["attempt"] > 1 and call["state_reason"]:
                    _set_reason(m, call["state_reason"], call["model"])  # tried again
        elif m.get("creative_ref"):
            cr = await tx.first(
                """SELECT r.state, r.review_md, x.state_reason FROM substitutes.creatives r
                   LEFT JOIN substitutes.calls x ON x.id = r.call_id WHERE r.ref = :r""",
                r=m["creative_ref"],
            )
            if cr is not None:
                m["state"] = {
                    "queued": "queued", "generating": "working", "review": "done", "accepted": "done",
                    "rejected": "done", "failed": "failed",
                }.get(cr["state"], "working")  # fmt: skip
                if m["state"] == "failed":
                    _set_reason(m, cr["state_reason"] or "failed", m.get("model"))
    state = c["state"]
    synthesis_ref = c["synthesis_ref"]
    synthesis_work_id = c["synthesis_work_id"]
    note = c.get("note_fa")
    ended = all(m["state"] in FINAL_MEMBER for m in members)
    answered = [m for m in members if m["state"] == "done"]
    if state == "running" and ended:
        # ⟨1.10⟩ §28.4 never waits for members that ended, whatever their outcome
        if c.get("media"):
            state = "done" if answered else "failed"
        elif len(answered) >= 2:
            synthesis_work_id = await _synthesis_work(tx, hub, w, members)
            state = "synthesising"
        elif len(answered) == 1:
            # one answer is not a council: said plainly, that answer is the result
            only = answered[0]
            name = PLAYER_FA.get(only["player"], only["player"])
            note = (
                f"فقط {name} جواب داد؛ بقیه‌ی اعضا جواب ندادند (دلیل هر کدام کنارش آمده). "
                "این یک پاسخ است، نه جمع‌بندی شورا."
            )
            synthesis_ref = only.get("deliverable_ref") or await _lone_answer(tx, hub, w, only)
            state = "done"
        else:
            note = "هیچ عضوی جواب نداد؛ دلیل هر کدام کنارش آمده است."
            state = "failed"
    if state == "synthesising" and synthesis_work_id is not None:
        dl = await tx.scalar(
            "SELECT ref FROM cartable.deliverables WHERE work_id = :w ORDER BY created_at LIMIT 1",
            w=synthesis_work_id,
        )
        if dl:
            synthesis_ref, state = dl, "done"
    changed = (
        members != list(c["members"] or [])
        or state != c["state"]
        or synthesis_ref != c["synthesis_ref"]
        or synthesis_work_id != c["synthesis_work_id"]
        or note != c.get("note_fa")
    )
    if changed:
        await tx.exec(
            """UPDATE work.councils SET members = CAST(:m AS jsonb), state = :st, synthesis_ref = :sr,
                   synthesis_work_id = :sw, note_fa = :n, updated_at = now() WHERE id = :id""",
            m=json.dumps(members, ensure_ascii=False),
            st=state,
            sr=synthesis_ref,
            sw=synthesis_work_id,
            n=note,
            id=c["id"],
        )
        fresh = await tx.first(COUNCIL_SQL + " WHERE k.id = :id", id=c["id"])
        assert fresh is not None
        await _emit(tx, w["company"], fresh)
    return changed


async def _answer_of(tx: Tx, hub: Any, m: dict[str, Any]) -> str:
    if m["player"] == "claude" and m.get("deliverable_ref"):
        return str(
            await tx.scalar(
                "SELECT coalesce(body, summary, '') FROM cartable.deliverables WHERE ref = :r",
                r=m["deliverable_ref"],
            )
            or ""
        )
    if m.get("call_id"):
        res = await tx.scalar(
            "SELECT result FROM substitutes.calls WHERE id = CAST(:id AS uuid)", id=m["call_id"]
        )
        if isinstance(res, dict):
            return await S.full_text(tx, hub, res)
    return ""


async def _lone_answer(tx: Tx, hub: Any, w: dict[str, Any], m: dict[str, Any]) -> str | None:
    """The one substitute that answered (Claude did not): its answer becomes
    the order's deliverable, labelled with its source; none when the order
    already ended."""
    from hq_api.domain import work as W

    if w["status"] not in W.OPEN or not m.get("call_id"):
        return None
    call = await tx.first(
        "SELECT * FROM substitutes.calls WHERE id = CAST(:id AS uuid)", id=m["call_id"]
    )
    text = await S.full_text(tx, hub, (call or {}).get("result"))
    if call is None or not text:
        return None
    name = PLAYER_FA.get(call["player"], call["player"])
    full = await tx.first(
        """SELECT w.*, c.code AS company FROM work.work w JOIN core.companies c ON c.id = w.company_id
           WHERE w.id = :id""",
        id=w["id"],
    )
    assert full is not None
    dl = await deliver(
        tx,
        dict(full),
        title=w["title"],
        body=text,
        produced_with={
            "player": call["player"],
            "model": call["model"],
            "label_fa": f"انجام‌شده با {name} (تنها پاسخ شورا)",
            "source": S.source(call),
            "substitute_call": str(call["id"]),
        },
        hub=hub,
    )
    return str(dl["ref"])


SYNTHESIS_FA = (
    "جمع‌بندی شورای مدل‌ها برای همین کار. پاسخ‌های مستقل زیر را بخوان و یک خروجی بده با این بخش‌ها:\n"
    "1. «جایی که هم‌نظرند» (با ذکر مدل‌ها)\n"
    "2. «جایی که اختلاف دارند و چرا»\n"
    "3. «پیشنهاد» (یک توصیه‌ی روشن با دلیل و ریسک)\n"
    "4. «هر پاسخ کامل»: پاسخ هر مدل، کامل و بی‌تغییر، با نام مدل.\n"
    "هیچ ادعایی بی‌منبع نیست؛ پاسخ بازیکن‌های ذخیره منبع‌اند نه شاهد.\n"
)


async def _synthesis_work(
    tx: Tx, hub: Any, w: dict[str, Any], members: list[dict[str, Any]]
) -> UUID:
    from hq_api.domain import work as W

    parts = [SYNTHESIS_FA]
    for m in members:
        name = PLAYER_FA.get(m["player"], m["player"])
        if m["state"] == "done":
            parts.append(f"\n## {name} ({m.get('model') or '—'})\n\n{await _answer_of(tx, hub, m)}")
        else:
            parts.append(f"\n## {name}: {m['state']} ({m.get('reason') or '—'})")
    brief = "\n".join(parts)
    if len(brief) > BRIEF_LIMIT:
        # every answer whole, in a file the assignee reads (files.read)
        fid = await store_text(tx, hub, w["company_id"], f"{w['ref']}-council-answers.md", brief)
        listed = "\n".join(
            f"- {PLAYER_FA.get(m['player'], m['player'])}: {m['state']}" for m in members
        )
        brief = (
            f"{SYNTHESIS_FA}\nThe members' answers are too long for this brief; read them whole "
            f"with files.read {fid} (Markdown, every answer under its model's heading).\n{listed}"
        )
    child = await W.create(
        tx,
        SERVICE,
        company_id=w["company_id"],
        company_code=w["company"],
        title=f"جمع‌بندی شورا: {w['title']}"[:300],
        brief=brief,
        kind="one_off",
        priority=w["priority"],
        assignee_code=w["a_code"],
        parent=w,
        player="claude",
        mode="single",
    )
    await _event(tx, w, "council_synthesis", {"synthesis_work": child["ref"]})
    return UUID(str(child["id"]))


async def _emit(tx: Tx, company: str, c: dict[str, Any]) -> None:
    await events.emit(tx, company, "work.council", c["work_ref"], render(c).model_dump(mode="json"))


async def on_deliverable(tx: Tx, hub: Any, w: dict[str, Any]) -> None:
    """A deliverable arrived on a work: its council (Claude's member) or the
    council whose synthesis it is, brought up to date."""
    c = await tx.first(
        "SELECT * FROM work.councils WHERE work_id = :w OR synthesis_work_id = :w FOR UPDATE",
        w=w["id"],
    )
    if c is not None:
        await refresh(tx, hub, c)
