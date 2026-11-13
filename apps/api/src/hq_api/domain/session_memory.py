"""The session remembers (contract §40.1, v1.22; the owner, 2026-11-07: «۲-۳ هزار خط چت کردیم و
به یه نتیجه رسیدیم … جلسه‌ها به همدیگه ارتباطی ندارن، کار گم میشه»).

    memory_md       owner.order_reports.memory_md: at most MEMORY_CHARS of plain Persian, what was
                    decided, who does what, the tools and helpers chosen, the open points. One
                    place: the report is the session.
    by code         `remember` appends one line per card done and per person joining (the
                    session's own paths call it); the oldest lines go when the memory is full.
    by the model    `fold` folds the talk's turns since the last fold into the memory: every
                    FOLD_EVERY turns (the worker, after a turn) and at close (the api, in the
                    background). Task class `session_memory` (the cheapest model that does it
                    well); the turns are masked as the talk's summary masks them; a failure keeps
                    the old memory and never blocks a turn.
    carried         the holder's talk context and run brief, every participant's turn in that
                    session (order_turns.talk_brief), and `OrderReport.memory_md`.
    related         the company's last three other sessions (title, one outcome line, their
                    playbook if any), in the holder's context: sessions are not islands.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.talk.scrub import clean

log = logging.getLogger("hq_api.session_memory")

MEMORY_CHARS = 6_000
FOLD_EVERY = 20
# ⟨2026-11-13⟩ a direct session (domain/direct.py) folds sooner: a fresh Claude session of the same
# meeting starts from this memory (the owner: never a model that forgot, never millions of tokens
# re-read per word); at most FOLD_CHUNK turns go to the model at once, oldest first
DIRECT_FOLD_EVERY = 8
FOLD_CHUNK = 25
MIN_CHUNK = 6  # the smallest chunk tried again in halves
CATCH_UP_ROUNDS = 8
TASK_CLASS = "session_memory"
RELATED = 3
TURN_CHARS = 900  # ⟨2026-11-13⟩ was 1500: a turn's gist, not its whole text
SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["memory_md"],
    # ⟨2026-11-13⟩ no maxLength: a memory a little over it failed the whole answer (Haiku on
    # F-0018); the text is cut to MEMORY_CHARS here (_fit), oldest lines first
    "properties": {"memory_md": {"type": "string"}},
}
SYSTEM = (
    "You keep the memory of one working session between a holding's owner (مدیر کل) and the people "
    "in it (the holder of the owner's order, the employees hired into it, outside helpers such as "
    "ChatGPT). Fold the new turns into the memory so far and answer the WHOLE memory again: plain "
    "Persian, at most 5000 characters (about 50 short lines; never longer), short lines under these "
    "headings when there is something "
    "to say: «## تصمیم‌ها» (what was decided), «## چه کسی چه میکند» (each person present and their "
    "task), «## ابزارها و کمک‌ها» (the tools and helpers chosen, e.g. «موضوع روزانه را نویسنده با "
    "ChatGPT پیدا میکند»), «## نکته‌های باز» (what is still open). Keep refs (W-, F-, D-, PB-, CV-) "
    "and figures as written, in Latin digits. Keep every decision already in the memory unless the "
    'new turns change it. No new facts, no advice. Answer {"memory_md": "..."} only.'
)


# -------------------------------------------------------------------- by code --
def _fit(text: str, limit: int = MEMORY_CHARS) -> str:
    """At most `limit` characters: the oldest lines go first (the headings' order is the model's)."""
    text = text.strip()
    while len(text) > limit and "\n" in text:
        text = text.split("\n", 1)[1].lstrip()
    return text[-limit:] if len(text) > limit else text


async def remember(tx: Tx, report_id: UUID, line: str) -> None:
    """One line of the session's memory, by code («<title> به جلسه آمد», «خودکارسازی ثبت شد: …»)."""
    one = clean(" ".join(line.split()))[0][:400]
    if not one:
        return
    cur = await tx.scalar(
        "SELECT memory_md FROM owner.order_reports WHERE id = :id FOR UPDATE", id=report_id
    )
    text = _fit(f"{cur or ''}\n- {one}" if cur else f"- {one}")
    await tx.exec(
        "UPDATE owner.order_reports SET memory_md = :m, updated_at = now() WHERE id = :id",
        m=text,
        id=report_id,
    )


# -------------------------------------------------------------- by the model --
def _line(r: dict[str, Any], titles: dict[str, str]) -> str:
    if r["by_kind"] == "owner":
        return "مدیر کل: " + str(r.get("text") or "")
    who = titles.get(str(r["persona"]), str(r["persona"]))
    return f"{who}: {r.get('show_md') or r.get('say_fa') or ''}"


def body_of(
    holding: str,
    ref: str,
    memory_md: str | None,
    present: list[str],
    lines: list[str],
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """The router call that folds the lines (masked already) into the memory."""
    prompt = json.dumps(
        {
            "session": ref,
            "memory_so_far": memory_md or "",
            "present": present,
            "new_turns": lines,
        },
        ensure_ascii=False,
    )
    body: dict[str, Any] = {
        "company_code": holding,
        "actor_ref": "session:memory",
        "task_class": TASK_CLASS,
        "priority": 3,
        "effort": "low",
        "system": SYSTEM,
        "prompt": prompt,
        "json_schema": SCHEMA,
        # ⟨2026-11-13⟩ was 2500: Persian runs about a token per 1.3 characters, so a memory past
        # ~3000 characters was cut mid-answer (the CLI's cap, every attempt) and never saved; the
        # owner: a longer answer from Sonnet is fine
        "max_output_tokens": 8_000,
        "timeout_s": 60,
        "meta": {"purpose": "session_memory", "order": ref},
    }
    if model:
        body["model"] = model
    return body


async def due(tx: Tx, order_ref: str) -> bool:
    """Whether FOLD_EVERY turns came since the last fold (the worker asks after a turn)."""
    row = await tx.first(
        """SELECT r.memory_upto, c.turns FROM owner.order_reports r
           JOIN talk.conversations c ON c.ref = r.conversation_ref WHERE r.ref = :r""",
        r=order_ref,
    )
    return row is not None and int(row["turns"]) - int(row["memory_upto"]) >= FOLD_EVERY


async def fold(
    hub: Any, call: Any, ref: str, *, force: bool = False, every: int = FOLD_EVERY
) -> dict[str, Any]:
    """The turns since the last fold into the memory (at most FOLD_CHUNK, oldest first). `call(body)
    -> dict | None` is the model (the worker's router, or the api's workflow). `force`: whatever
    the count; `every`: how many turns make it due. Nothing raised: a failure keeps the old memory
    and is logged."""
    try:
        return await _fold(hub, call, ref, force=force, every=every)
    except Exception:  # the memory is best effort, the turn is not
        log.warning("session memory not folded", extra={"ref": ref}, exc_info=True)
        return {"folded": False, "why": "error"}


async def catch_up(hub: Any, call: Any, ref: str) -> int:
    """⟨2026-11-13⟩ Every turn not yet in the memory folded, chunk by chunk (before a fresh Claude
    session of the meeting starts from it). Answers the chunks folded; never raises."""
    n = 0
    for _ in range(CATCH_UP_ROUNDS):
        got = await fold(hub, call, ref, force=True)
        if not got.get("folded"):
            break
        n += 1
    return n


async def _fold(hub: Any, call: Any, ref: str, *, force: bool, every: int) -> dict[str, Any]:
    from hq_api.domain import sessions as SE

    async with hub.db.tx(await hub.companies.ids()) as tx:
        rep = await tx.first(
            "SELECT id, memory_md, memory_upto, conversation_ref FROM owner.order_reports WHERE ref = :r",
            r=ref,
        )
        if rep is None or not rep.get("conversation_ref"):
            return {"folded": False, "why": "no_session"}
        conv = await tx.first(
            "SELECT id, turns, present, holder FROM talk.conversations WHERE ref = :r",
            r=rep["conversation_ref"],
        )
        if conv is None:
            return {"folded": False, "why": "no_session"}
        upto = int(rep["memory_upto"])
        rows = [
            dict(r)
            for r in await tx.all(
                """SELECT n, by_kind, persona, text, say_fa, show_md FROM talk.turns
                   WHERE conversation_id = :c AND n > :u AND state = 'done' ORDER BY n""",
                c=conv["id"],
                u=upto,
            )
        ]
        if not rows or (not force and len(rows) < every):
            return {"folded": False, "why": "not_due"}
        rows = rows[:FOLD_CHUNK]
        keys = list(dict.fromkeys([str(conv.get("holder") or ""), *(conv.get("present") or [])]))
        titles = {k: (await SE.title_of(tx, k))[0] for k in keys if k}
        holding = await hub.companies.holding()
    text = ""
    # ⟨2026-11-13⟩ a chunk the model cannot fold (it ran past its output cap on some turns of
    # F-0018) is tried again on its first half, then its first quarter: the memory moves on
    while rows:
        lines = [clean(_line(r, titles))[0][:TURN_CHARS] for r in rows]
        body = body_of(holding.code, ref, rep["memory_md"], list(titles.values()), lines)
        out = await call(body)
        text = (
            clean(str((out or {}).get("memory_md") or "").strip())[0]
            if isinstance(out, dict)
            else ""
        )
        if text or len(rows) <= MIN_CHUNK:
            break
        rows = rows[: len(rows) // 2]
    if not text:
        log.info("session memory: the model gave nothing", extra={"ref": ref})
        return {"folded": False, "why": "no_answer"}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        cur = await tx.first(
            "SELECT memory_md, memory_upto FROM owner.order_reports WHERE id = :id FOR UPDATE",
            id=rep["id"],
        )
        if cur is None or int(cur["memory_upto"]) != upto:
            return {"folded": False, "why": "folded_meanwhile"}
        # the lines `remember` added while the model was folding stay (after the model's text)
        await tx.exec(
            """UPDATE owner.order_reports SET memory_md = :m, memory_upto = :u, updated_at = now()
               WHERE id = :id""",
            m=merged(rep["memory_md"], cur["memory_md"], text),
            u=int(rows[-1]["n"]),
            id=rep["id"],
        )
    return {"folded": True, "upto": int(rows[-1]["n"])}


def merged(was: str | None, now: str | None, folded: str) -> str:
    """The model's memory (folded from `was`) and the lines appended to the memory since (`now`
    holds them: `remember` writes while the model folds)."""
    before = set((was or "").splitlines())
    added = [ln for ln in (now or "").splitlines() if ln.strip() and ln not in before]
    return _fit("\n".join([folded, *added]))


def router_call(router: Any) -> Any:
    """`call` for the worker: the router's run, its structured answer (or its text parsed)."""

    async def call(body: dict[str, Any]) -> dict[str, Any] | None:
        if router is None:
            return None
        got = await router.run(body, int(body.get("timeout_s", 60)))
        if not got.ok:
            return None
        out = got.structured
        if out is None and got.text:
            try:
                out = json.loads(got.text)
            except ValueError:
                out = None
        return out if isinstance(out, dict) else None

    return call


def api_call(hub: Any) -> Any:
    """`call` for the api (which cannot reach the router): the worker's model workflow."""
    from hq_api import workflows_client

    async def call(body: dict[str, Any]) -> dict[str, Any] | None:
        return await workflows_client.model_call(hub, body, timeout_s=90)

    return call


async def fold_after_close(hub: Any, ref: str) -> None:
    """At close (the api, after the response): the last turns folded, whatever their count."""
    await catch_up(hub, api_call(hub), ref)


# ------------------------------------------------------------ related sessions --
async def related(tx: Tx, ref: str, company: str | None) -> list[dict[str, Any]]:
    """The company's last RELATED other sessions (the orders routed to it), newest first: the
    order, its title, one outcome line, and the playbook drafted from it if any."""
    from hq_api.domain import order_report as OR
    from hq_api.domain import sessions as SE

    if not company:
        return []
    rows = await tx.all(
        """SELECT r.ref, r.state, r.summary, r.steps, r.closed_at, o.text,
                  (SELECT p.ref FROM owner.playbooks p WHERE p.source->>'order' = r.ref
                     ORDER BY p.created_at DESC LIMIT 1) AS playbook
           FROM owner.order_reports r JOIN owner.orders o ON o.id = r.order_id
           WHERE o.routes @> CAST(:j AS jsonb) AND r.ref <> :me AND r.hidden_at IS NULL
           ORDER BY COALESCE(r.last_step_at, r.updated_at, r.created_at) DESC LIMIT :l""",
        j=json.dumps([{"company": company}]),
        me=ref,
        l=RELATED,
    )
    out = []
    for r in rows:
        summary = OR._j(r.get("summary")) or {}
        steps = OR._j(r.get("steps")) or []
        outcome = (
            summary.get("done_fa") or (steps[-1].get("what_fa") if steps else None) or r["state"]
        )
        out.append(
            {
                "order": r["ref"],
                "title_fa": SE._title(r.get("text")),
                "state": "closed" if r.get("closed_at") is not None else "open",
                "outcome_fa": SE.short(str(outcome), 160),
                "playbook": r.get("playbook"),
            }
        )
    return out
