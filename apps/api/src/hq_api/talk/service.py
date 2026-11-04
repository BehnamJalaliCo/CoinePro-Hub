"""The api's side of a turn (contract §32.2-§32.4, §32.8): store the owner's
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
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from hq_api import workflows_client
from hq_api.context import Ctx
from hq_api.db import Tx
from hq_api.domain import orders as O
from hq_api.errors import ApiError
from hq_api.talk import cards as K
from hq_api.talk import engine, personas, store
from hq_api.talk.intents import read as read_intents
from hq_api.talk.scrub import clean

log = logging.getLogger("hq_api.talk.service")
EVENTS_PATH = "/api/v1/talk/turns/{id}/events"


async def new_conversation(
    ctx: Ctx, tx: Tx, key: str, mode: str, title_fa: str | None
) -> dict[str, Any]:
    p = await personas.resolve(tx, ctx.hub, key)
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
    conv = await store.conversation(tx, ref, lock=True)
    if client_id:
        prev = await tx.first(
            """SELECT a.id AS answer, o.id AS owner FROM talk.turns o
               JOIN talk.turns a ON a.reply_to = o.id
               WHERE o.conversation_id = :c AND o.client_id = :k""",
            c=conv["id"],
            k=client_id,
        )
        if prev is not None:  # the same turn sent again: its answer, not a second one
            return prev["answer"], prev["owner"]
    holding = await ctx.hub.companies.holding()
    clean_text, had_key = clean(text) if text else ("", False)
    owner_id: UUID | None = None
    n = int(conv["turns"])
    if directive is None:
        intent = read_intents(clean_text, await O.directory(tx))
        if intent.secretary and conv["persona"] != "secretary":
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
            if mp is not None and mp.key != conv["persona"]:
                joined = await K.join_with_notice(tx, ctx.hub, conv, mp)
                n = int(conv["turns"])
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
                   state, finished_at)
               VALUES (:c, :co, :n, 'owner', :s, :t, :k, 'done', now()) RETURNING id""",
            c=conv["id"],
            co=holding.id,
            n=n,
            s=source,
            t=clean_text,
            k=client_id,
        )
        if intent.remember and not had_key:
            await store.remember(tx, holding.id, clean(intent.remember)[0], owner_id)
    p = await personas.resolve(tx, ctx.hub, conv["persona"])
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
        d=directive,
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
        summary=f"turn {n - 1} to {p.key}" + (" (a key was removed)" if had_key else ""),
    )
    return answer_id, owner_id


async def dispatch(hub: Any, turn_id: UUID) -> None:
    """After the commit: the worker answers; without it, the plain line at once."""
    started = False
    try:
        started = await workflows_client.talk_turn(hub, str(turn_id))
    except Exception:  # noqa: BLE001 - the fallback below answers
        log.warning("could not start the talk turn", extra={"turn": str(turn_id)})
    if not started:
        await engine.unavailable(hub, str(turn_id))


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
