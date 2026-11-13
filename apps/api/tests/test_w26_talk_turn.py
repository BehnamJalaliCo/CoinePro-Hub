"""⟨1.37⟩ Contract §59.12 (prompt 38): a direct session's conversational turn. The owner's word that
asks for no build and no file (a question, a short thanks) is answered by the classic run on a
Sonnet-class model with at most fifteen tools (workshop.run among them), not by an Opus turn on
the workshop; any word that asks for a build, a change or a file is the workshop's turn as before."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from hq_api.domain import direct as DR
from hq_api.hub import Hub

from .conftest import idem
from .test_p17_runners import take
from .test_p21_secretary import no_model  # noqa: F401 - the fixture
from .test_w14_workshop import workshop
from .test_w21_direct_session import an_order, end_run, queued_run, result


def test_a_word_is_talk_only_when_it_asks_for_nothing_to_be_made() -> None:
    for t in ("چرا امروز رنگش مشکی بود؟", "کار به کجا رسید؟", "مرسی، عالی بود", "باشه",
              "آیا ساعت ۹:۳۰ خوبه؟", "چند تا کامنت گرفت؟"):  # fmt: skip
        assert DR.talk_only(t), t
    for t in ("کاور رو عوض کن", "ادامه بده", "ویدیو رو دوباره رندر کن", "شعار آخرش این باشد",
              "یه نسخه‌ی کوتاه‌تر بساز", "", "چرا " + "خیلی " * 80 + "؟",
              "فایل صدا کو؟", "لینک رو بفرست"):  # fmt: skip
        assert not DR.talk_only(t), t


def test_the_talk_turn_carries_at_most_fifteen_tools_in_order() -> None:
    have = (*DR.TALK_TOOLS[::-1], "media.render", "kill_switch.engage", "deploy.freeze")
    got = DR.talk_tools(have)
    assert got == DR.TALK_TOOLS and len(got) <= DR.TALK_MAX
    assert "workshop.run" in got and "media.render" not in got
    assert DR.talk_tools(("order.ask", "media.render")) == ("order.ask",)


async def test_a_question_in_a_session_is_the_classic_turn_and_a_change_the_workshops(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    co = (await new_company())["code"]
    rn = await workshop(client, hub, owner_session, su, version="0.3.5")
    o = await an_order(client, owner, su, co)
    run = await queued_run(su, o)
    note = await DR.hand_over(hub, run, o["emp"])
    assert note is not None and note.startswith("direct turn "), note
    await end_run(su, run, note)
    job = await take(client, rn)
    await result(client, rn, job["id"], "متن ریلز آماده است.")

    # a question: no workshop turn, the run goes on as the classic one (marked for the runner)
    r = await client.post(f"/api/v1/orders/{o['ref']}/reply", headers={**owner, **idem()},
                          json={"text": "چرا این رنگ‌ها انتخاب شد؟"})  # fmt: skip
    assert r.status_code == 200, r.text
    run = await queued_run(su, o, reason=f"owner_reply:{o['ref']}")
    assert await DR.hand_over(hub, run, o["emp"]) is None
    assert DR.take_talk(run["id"]) is True and DR.take_talk(run["id"]) is False
    await end_run(su, run, "answered")
    assert (await client.get("/api/v1/runners/jobs/next", params={"wait": 0}, headers=rn["h"])
            ).status_code == 204  # no workshop turn was started  # fmt: skip

    # a change: the workshop's turn as before
    r = await client.post(f"/api/v1/orders/{o['ref']}/reply", headers={**owner, **idem()},
                          json={"text": "شعار آخرش «با پروچارت همیشه با نمودار» بشه، عوضش کن"})  # fmt: skip
    assert r.status_code == 200, r.text
    run = await queued_run(su, o, reason=f"owner_reply:{o['ref']}")
    note = await DR.hand_over(hub, run, o["emp"])
    assert note is not None and note.startswith("direct turn "), note
    assert DR.take_talk(run["id"]) is False
    await end_run(su, run, note)
    nxt = await take(client, rn)
    assert nxt["args"]["direct"] is True
