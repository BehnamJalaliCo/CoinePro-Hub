"""⟨1.17⟩ §35.4 a player in a session: ChatGPT, Gemini or DeepSeek (the substitutes of §21.13)
answers a turn of an order's talk through its substitute seat.

    start      (the engine, for a `player:…` persona turn) the masked conversation (the last
               turns, «## The order you hold», the owner's words) goes to the player's text seat
               as one seat call (purpose `talk`, the turn's id); the turn stays `streaming` until
               the runner answers. A seat that cannot take it (signed out, limited, locked, the
               data guard) ends the turn at once with one plain line, never an error.
    on_call    (substitutes.finish → _applied) the answer becomes the turn: labelled with the
               player and its model, scrubbed, streamed as `text` and `done`.

The player reads nothing of the hub but the conversation and the order it is in: no tools, no
cards, no charter; what reaches it is scrubbed as every seat call is (hq_common.redact.scrub).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import players as PL
from hq_api.domain import substitutes as S
from hq_api.principal import Principal
from hq_api.talk import context as C
from hq_api.talk import store
from hq_api.talk.scrub import clean

log = logging.getLogger("hq_api.talk.player")
TALK = Principal(kind="service", code="talk", role="service")
PURPOSE = "talk"
TURNS = 12
ANSWER_MAX = 12_000
WAIT_FA = "{name} در حال پاسخ است؛ جوابش همین‌جا می‌آید."
OFF_FA = {
    "off": "{name} روشن نیست.",
    "signed_out": "{name} وارد نشده است؛ اول در صفحه‌ی بازیکن‌ها واردش کنید.",
    "expired": "ورود {name} تمام شده است؛ دوباره واردش کنید.",
    "limited": "{name} به سقف امروزش رسیده است.",
    "per_day": "{name} به سقف امروزش رسیده است.",
    "holding_locked": "هلدینگ قفل است؛ {name} صدا نمیشود.",
}


async def transcript(
    tx: Tx, hub: Any, conv: dict[str, Any], owner_text: str, before_n: int, name: str
) -> str:
    """The conversation as the player sees it: who said what (titles, never codes), the order it
    is in, and the owner's words last."""
    from hq_api.domain import order_turns as OT
    from hq_api.talk import personas

    titles: dict[str, str] = {}
    for key in {*(conv.get("present") or []), str(conv["persona"])}:
        try:
            titles[key] = (
                await personas.resolve_in(tx, hub, key, conv, store_voice=False)
            ).title_fa
        except Exception:  # noqa: BLE001 - a key that no longer resolves is shown as it is
            titles[key] = key
    lines = [
        f"You are {name}, a member of the owner's working session in a Persian-speaking holding. "
        "Answer the owner in Persian, briefly (the conclusion first, then why), from what is in "
        "this conversation and the order below only. You have no tools and no other knowledge of "
        "the holding; say plainly what you cannot know. Never invent a figure, a name or a state.",
        "",
    ]
    if conv.get("order_ref"):
        held = await OT.talk_brief(tx, str(conv["order_ref"]))
        if held is not None:
            lines += ["## The order you hold (with the others)",
                      json.dumps(held, ensure_ascii=False, default=str), ""]  # fmt: skip
    lines.append("## The conversation (oldest first)")
    for t in await store.last_turns(tx, conv["id"], TURNS, before_n=before_n):
        if t["by_kind"] == "owner":
            lines.append(f"owner: {t['text']}")
        elif t["show_md"]:
            lines.append(f"[{C._speaker(t, titles)}] {t['show_md']}")
    lines += ["", "## The owner now says", owner_text or "(the owner asked for this without words)",
              "", "Your answer, in Persian:"]  # fmt: skip
    return "\n".join(lines)


async def start(run: Any) -> dict[str, Any]:
    """The engine's player turn: one seat call, the turn left streaming until the answer comes."""
    p = run.persona
    assert p is not None
    assert p.player is not None
    name = p.title_fa
    holding = await run.hub.companies.holding()
    async with run.tx() as tx:
        text = await transcript(tx, run.hub, run.conv, run.owner_text, run._before_n, name)
        found = await PL.text_seat(tx, p.player)
        seat = found[1]["seat"] if found else "third_opinion"
        refused = await S.guard(tx, run.hub, seat, text)
        if refused is not None:
            call = None
        else:
            call = await S.seat_call(
                tx,
                run.hub,
                TALK,
                seat=seat,
                input_md=text,
                company_id=holding.id,
                purpose=(PURPOSE, run.turn_id),
                player=p.player,
            )
    if call is None or call["state"] != "queued":
        if call is None:
            line = f"{name} این بار صدا نشد: متن گفتگو برای بازیکن بیرونی مناسب نبود."
        else:
            why = str(call.get("state_reason") or "off")
            line = OFF_FA.get(why, "{name} الان در دسترس نیست.").format(name=name)
        failed: dict[str, Any] = await run._finish(
            "failed", line, line, cards=[], reason=line[:500]
        )
        return failed
    await run.emit("text", {"delta": "_" + WAIT_FA.format(name=name) + "_"})
    return {"state": "streaming", "player_call": str(call["id"]), "ref": run.conv["ref"]}


async def on_call(tx: Tx, hub: Any, call: dict[str, Any]) -> None:
    """The player's answer (or why it gave none) becomes the turn."""
    try:
        t = await store.turn(tx, str(call["purpose_ref"]), lock=True)
    except Exception:  # noqa: BLE001 - a turn that is gone takes no answer
        log.warning("talk player call without its turn", extra={"call": str(call["id"])})
        return
    if t["state"] != "streaming":
        return
    conv = await store.conversation(tx, t["conversation_ref"], lock=True)
    name = PL.PLAYER_FA.get(call["player"], call["player"])
    model = call.get("model")
    label = f"**{name}**" + (f" · {model}" if model else "")
    res = call.get("result") or {}
    answer = clean(await S.full_text(tx, hub, res))[0].strip() if call["state"] == "done" else ""
    if answer:
        show = f"{label}: {S.cut_residue(answer) or answer}"[:ANSWER_MAX]
        say = clean(answer)[0][:400]
        state, reason = "done", None
    else:
        why = str(call.get("state_reason") or "")
        show = say = OFF_FA.get(why.split(":")[0], "{name} جوابی نداد.").format(name=name)
        state, reason = "failed", show[:500]
    await tx.exec(
        """UPDATE talk.turns SET say_fa = :say, show_md = :show, state = :st, reason_fa = :reason,
               finished_at = now()
           WHERE id = :id AND state = 'streaming'""",
        say=say,
        show=show,
        st=state,
        reason=reason,
        id=t["id"],
    )
    await store.add_event(tx, t["id"], t["company_id"], "text", {"delta": "\n\n" + show})
    out = (await store.turn_out(tx, t["id"])).model_dump(mode="json")
    await store.add_event(tx, t["id"], t["company_id"], "done", {"state": state, "turn": out})
    await tx.exec(
        "UPDATE talk.conversations SET last_turn_at = now(), updated_at = now() WHERE id = :id",
        id=conv["id"],
    )
    holding = await hub.companies.holding()
    await events.emit(
        tx, holding.code, "talk.turn", conv["ref"],
        {"turn": str(t["id"]), "state": state, "persona": t["persona"]},
    )  # fmt: skip
