"""The api's side of a turn (contract §32.2-§32.4, §32.8; §35.4): store the owner's
words (scrubbed), apply what the rules see in them, and hand the answer to the
worker. Nothing here calls a model.

    owner turn   stored at once, a key already removed (§32.5)
    rules        «منشی» → back to the secretary; «… را بیاور» → the manager
                 joins (§32.4); «جلسه‌ی کاری» / «حالت مشورت» → the mode;
                 «یادت باشه» → the owner's memory; «صورت‌جلسه کن» or, in a
                 working meeting, «پایان جلسه» → this answer carries the one
                 minutes card (§32.3)
    answer turn  stored `streaming` for the persona present, then the worker's
                 workflow TalkTurn answers it; when the worker cannot be
                 reached the plain line of §32.2 answers at once (never 5xx)
    a session    ⟨1.17⟩ §35.4 a talk bound to an order: the holder answers by default; `to`
                 names a participant (a player answers through its seat); `to: all` or «نظر
                 همه» makes every present participant answer once (at most 5), then the holder
                 sums up (directive `sum_up`). A closed session takes no turn (409).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from hq_api import workflows_client
from hq_api.context import Ctx
from hq_api.db import Tx
from hq_api.domain import files as F
from hq_api.domain import orders as O
from hq_api.errors import ApiError
from hq_api.talk import cards as K
from hq_api.talk import engine, personas, store
from hq_api.talk.intents import read as read_intents
from hq_api.talk.scrub import clean

log = logging.getLogger("hq_api.talk.service")
EVENTS_PATH = "/api/v1/talk/turns/{id}/events"
EVERYONE_MAX = 5
CLOSED_FA = "این جلسه بسته شده است؛ برای ادامه آن را دوباره باز کنید."


async def new_conversation(
    ctx: Ctx,
    tx: Tx,
    key: str,
    mode: str,
    title_fa: str | None,
    *,
    employee_code: str | None = None,
) -> dict[str, Any]:
    p = await personas.resolve(tx, ctx.hub, key, employee_code=employee_code)
    holding = await ctx.hub.companies.holding()
    row = await tx.one(
        """INSERT INTO talk.conversations (company_id, title_fa, persona, present, mode)
           VALUES (:co, :t, :p, :pr, :m) RETURNING *""",
        co=holding.id,
        t=(title_fa or p.title_fa)[:200],
        p=p.key,
        pr=[p.key],
        m=mode,
    )
    await ctx.audit(
        tx,
        company_id=holding.id,
        action="talk.conversation",
        action_class="A0",
        target_kind="conversation",
        target_ref=row["ref"],
        summary=f"opened with {p.key} ({mode})",
    )
    return dict(row)


def _answerers(
    conv: dict[str, Any], to: str | None, intent: Any, invited: str | None
) -> list[tuple[str, str | None]]:
    """Who answers this turn: [(persona key, directive)]."""
    bound = bool(conv.get("order_ref"))
    holder = str(conv.get("holder") or conv["persona"])
    present = [str(k) for k in conv.get("present") or []]
    if to and to != "all":
        if to != holder and to not in present:
            raise ApiError(404, "not_found", "not a participant",
                           message_fa="این کس در این گفتگو نیست.")  # fmt: skip
        return [(to, None)]
    if bound and (to == "all" or (intent is not None and intent.everyone)):
        others = [k for k in present if k != holder][:EVERYONE_MAX]
        return [*((k, None) for k in others), (holder, "sum_up" if others else None)]
    if invited is not None:
        return [(invited, None)]
    if intent is not None and intent.secretary:
        return [("secretary", None)]
    return [(holder if bound else str(conv["persona"]), None)]


async def add_turns(
    ctx: Ctx,
    tx: Tx,
    ref: str,
    text: str,
    source: str,
    client_id: str | None,
    *,
    directive: str | None = None,
    to: str | None = None,
    files: list[UUID] | None = None,
) -> tuple[list[UUID], UUID | None]:
    """(the answer turns, in order; the owner's turn) in the caller's transaction. ⟨1.18⟩ §36.2
    `files`: the owner's own uploads, kept on the owner's turn; in a session each one becomes a
    file of the order (§36.3)."""
    conv = await store.conversation(tx, ref, lock=True)
    if conv.get("closed_at") is not None:
        raise ApiError(409, "validation_failed", "the session is closed", message_fa=CLOSED_FA)
    if client_id:
        prev = await tx.all(
            """SELECT a.id AS answer, o.id AS owner FROM talk.turns o
               JOIN talk.turns a ON a.reply_to = o.id
               WHERE o.conversation_id = :c AND o.client_id = :k ORDER BY a.n""",
            c=conv["id"],
            k=client_id,
        )
        if prev:  # the same turn sent again: its answers, not new ones
            return [r["answer"] for r in prev], prev[0]["owner"]
    holding = await ctx.hub.companies.holding()
    sent = await F.owner_uploads(tx, files or [], holding.id) if directive is None else []
    clean_text, had_key = clean(text) if text else ("", False)
    owner_id: UUID | None = None
    n = int(conv["turns"])
    intent = None
    invited: str | None = None
    if directive is None:
        intent = read_intents(clean_text, await O.directory(tx))
        if intent.secretary and conv["persona"] != "secretary" and not conv.get("order_ref"):
            await tx.exec(
                "UPDATE talk.conversations SET persona = 'secretary', updated_at = now() WHERE id = :id",
                id=conv["id"],
            )
            conv["persona"] = "secretary"
        if intent.invite is not None and not had_key:
            try:
                key = await personas.invite_key(tx, ctx.hub, *intent.invite)
                mp = await personas.resolve(tx, ctx.hub, key)
            except ApiError:
                mp = None
            if mp is not None and mp.key != conv["persona"] and mp.key != conv.get("holder"):
                joined = await K.join_with_notice(tx, ctx.hub, conv, mp)
                n = int(conv["turns"])
                invited = str(joined["persona"])
                log.info("talk invite", extra={"ref": ref, "persona": joined["persona"]})
        mode = "work" if intent.work_mode else ("consult" if intent.consult_mode else conv["mode"])
        if mode != conv["mode"]:
            await tx.exec(
                "UPDATE talk.conversations SET mode = :m, updated_at = now() WHERE id = :id",
                m=mode,
                id=conv["id"],
            )
            conv["mode"] = mode
        if intent.minutes or (intent.end_meeting and conv["mode"] == "work"):
            directive = "minutes"
        n += 1
        owner_id = await tx.scalar(
            """INSERT INTO talk.turns (conversation_id, company_id, n, by_kind, source, text, client_id,
                   state, finished_at, files)
               VALUES (:c, :co, :n, 'owner', :s, :t, :k, 'done', now(), :f) RETURNING id""",
            c=conv["id"],
            co=holding.id,
            n=n,
            s=source,
            t=clean_text,
            k=client_id,
            f=[r["id"] for r in sent],
        )
        if conv.get("order_ref"):
            from hq_api.domain import order_turns as OT

            if sent:
                # ⟨1.18⟩ §36.3 in a session the owner's files go with the order
                await OT.add_files(tx, str(conv["order_ref"]), sent, owner_id)
            if clean_text and not had_key:
                # ⟨1.23⟩ §41.2 the owner's numbered steps are the session's plan (by code)
                await OT.plan_from_owner(tx, str(conv["order_ref"]), clean_text)
        if intent.remember and not had_key:
            await store.remember(tx, holding.id, clean(intent.remember)[0], owner_id)
    who = (
        [(str(conv["persona"]), directive)]
        if directive == "minutes"
        else _answerers(conv, to, intent, invited)
    )
    answers: list[UUID] = []
    for key, d in who:
        p = await personas.resolve_in(tx, ctx.hub, key, conv)
        n += 1
        answer_id: UUID = await tx.scalar(
            """INSERT INTO talk.turns (conversation_id, company_id, n, by_kind, persona, source, state,
                   reply_to, directive)
               VALUES (:c, :co, :n, 'persona', :p, 'system', 'streaming', :r, :d) RETURNING id""",
            c=conv["id"],
            co=p.company_id,
            n=n,
            p=p.key,
            r=owner_id,
            d=d,
        )
        answers.append(answer_id)
    if who[-1][0] != conv["persona"]:
        # the screen shows who speaks now (the last to answer)
        await tx.exec(
            "UPDATE talk.conversations SET persona = :p, updated_at = now() WHERE id = :id",
            p=who[-1][0],
            id=conv["id"],
        )
    await tx.exec(
        """UPDATE talk.conversations SET turns = :n, last_turn_at = now(), updated_at = now()
           WHERE id = :id""",
        n=n,
        id=conv["id"],
    )
    await ctx.audit(
        tx,
        company_id=holding.id,
        action="talk.turn",
        action_class="A0",
        target_kind="conversation",
        target_ref=ref,
        summary=f"turn {n - len(answers)} to {', '.join(k for k, _ in who)}"
        + (f" with {len(sent)} file(s)" if sent else "")
        + (" (a key was removed)" if had_key else ""),
    )
    return answers, owner_id


async def add_turn(
    ctx: Ctx,
    tx: Tx,
    ref: str,
    text: str,
    source: str,
    client_id: str | None,
    *,
    directive: str | None = None,
) -> tuple[UUID, UUID | None]:
    """(the answer turn, the owner's turn) in the caller's transaction."""
    answers, owner_id = await add_turns(ctx, tx, ref, text, source, client_id, directive=directive)
    return answers[0], owner_id


async def dispatch(hub: Any, turn_id: UUID) -> None:
    """After the commit: the worker answers; without it, the plain line at once."""
    started = False
    try:
        started = await workflows_client.talk_turn(hub, str(turn_id))
    except Exception:  # noqa: BLE001 - the fallback below answers
        log.warning("could not start the talk turn", extra={"turn": str(turn_id)})
    if not started:
        await engine.unavailable(hub, str(turn_id))


async def dispatch_all(hub: Any, turn_ids: list[UUID]) -> None:
    """⟨1.17⟩ §35.4 «نظر همه»: the answers one after the other, so the holder's sum-up reads
    every answer before it (a player's answer may still be on its way: the sum-up says so)."""
    for tid in turn_ids:
        await dispatch(hub, tid)


async def stop(ctx: Ctx, turn_id: UUID) -> store.TalkTurn:
    """Barge-in (§32.7): the worker stops generating and speaking within a
    moment; a turn whose worker is gone is closed here."""
    async with ctx.tx() as tx:
        t = await store.turn(tx, turn_id, lock=True)
        if t["state"] == "streaming":
            await tx.exec("UPDATE talk.turns SET stop_requested = true WHERE id = :id", id=t["id"])
            last = await tx.scalar(
                "SELECT max(at) FROM talk.turn_events WHERE turn_id = :id", id=t["id"]
            )
            idle = await tx.scalar(
                "SELECT now() - COALESCE(CAST(:l AS timestamptz), :a) > make_interval(secs => :s)",
                l=last,
                a=t["at"],
                s=engine.STEP_TIMEOUT_S * 2,
            )
            if idle:
                await tx.exec(
                    """UPDATE talk.turns SET state = 'stopped', finished_at = now(),
                           reason_fa = 'پاسخ متوقف شد.' WHERE id = :id""",
                    id=t["id"],
                )
                await store.add_event(tx, t["id"], t["company_id"], "done", {"state": "stopped"})
        return await store.turn_out(tx, turn_id)
