"""W11 G (2026-11-08): an asked person joins with the session's context, from the right company.
The owner, on F-0011: «پرسش عمیق کرد و رفت یکی رو از یه شرکت دیگه آورد که اصلا نمیدونست توی شرکتش
چه خبره» — the step said «مدیر فنی (CTO) پروچارت آمد» while the card asked IG's CTO.

- `ask {to: "CTO", company: IG}` → IG's CTO; `ask {to: "IG-CTO"}` (a full code) → IG's CTO, whatever
  company the card says (a conflicting one is refused in one line);
- the asked person's work carries the session's title, the order, the holder's words, the memory
  («تا اینجا») and the plan; the joined persona's talk context carries the memory too.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from hq_api.domain import order_report as OR
from hq_api.domain import sessions as SE
from hq_api.hub import Hub

from .test_p21_routing_orders import all_tx, report
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_p23_talk import answer, say, talk  # noqa: F401 - the fixture
from .test_w7_sessions import WORK_TEXT, refuse_queued, run_card

MEMORY_LINE = "موضوع روزانه را نویسنده با ChatGPT پیدا میکند"


async def assignee_of(su: Any, work_ref: str) -> Any:
    return await su.fetchrow(
        """SELECT e.code, w.brief FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE w.ref = $1""",
        work_ref,
    )


async def test_the_asked_person_is_the_one_named_and_knows_the_session(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    other = (await new_company())["code"]
    text = WORK_TEXT.format(co=co, w=words())
    out = await post_order(client, owner, text)
    ref, conv = out["ref"], out["talk_ref"]
    await refuse_queued(su, out["routes"][0]["work_ref"])
    holder_key = await su.fetchval("SELECT holder FROM talk.conversations WHERE ref = $1", conv)
    # the session already knows something (§40.1) and has a plan
    async with await all_tx(hub) as tx:
        rep = await OR.ensure(tx, ref)
        assert rep is not None
        await SE.remember(tx, rep["id"], MEMORY_LINE)
        await SE.add_task(tx, rep, title_fa="حساب را روی سرور ثبت کن", by="owner")
    cards = [
        {"kind": "ask", "title_fa": "از مدیر فنی آن شرکت", "body_fa": "حساب روی سرور آن شرکت است",
         "payload": {"text": "حساب اینستاگرام را روی سرور ثبت کن", "to": "CTO", "company": other}},
        {"kind": "ask", "title_fa": "با کد کامل", "body_fa": "",
         "payload": {"text": "دستور خواندن را هم بگذار", "to": f"{other}-TECH-MGR"}},
        {"kind": "ask", "title_fa": "کد و شرکت ناسازگار", "body_fa": "",
         "payload": {"text": "یک سؤال", "to": f"{other}-TECH-MGR", "company": co}},
    ]  # fmt: skip
    own = {"kind": "ask", "title_fa": "نقش با حروف بزرگ در شرکت خودمان", "body_fa": "",
           "payload": {"text": "عددهای سرور خودمان", "to": "Cto"}}  # fmt: skip
    talk["router"].answers = [answer("چهار کارت.", cards=cards)]
    said = await say(client, owner, conv, "به مدیر فنی آن شرکت بگو حساب را ثبت کند")
    by_title = {c["title_fa"]: c for c in said["answer"]["cards"]}
    # (1) `to: CTO` + company → that company's CTO, never the holder's company's
    r = await run_card(client, owner, by_title[cards[0]["title_fa"]])
    assert r.status_code == 200, r.text
    [w1] = r.json()["made"]
    got = await assignee_of(su, w1)
    assert got["code"] == f"{other}-TECH-MGR"
    # (2) the work's brief: the question, the session, the order, who asks and why, the memory,
    # the plan, and how the answer comes back
    brief = got["brief"]
    assert brief.startswith("حساب اینستاگرام را روی سرور ثبت کن")
    assert "## جلسه:" in brief and ref in brief and MEMORY_LINE in brief
    assert "حساب روی سرور آن شرکت است" in brief  # the holder's why (the card's words)
    assert "1. حساب را روی سرور ثبت کن [todo]" in brief and "deliver" in brief
    # a full code names the person and the company; a conflicting company is refused plainly
    r = await run_card(client, owner, by_title[cards[1]["title_fa"]])
    assert r.status_code == 200, r.text
    [w2] = r.json()["made"]
    assert (await assignee_of(su, w2))["code"] == f"{other}-TECH-MGR"
    r = await run_card(client, owner, by_title[cards[2]["title_fa"]])
    assert r.status_code == 422, r.text
    assert r.json()["message_fa"].startswith(f"{other}-TECH-MGR در شرکت {other} است، نه {co}")
    # a role in any case, in the holder's own company (a second turn: three cards a turn)
    talk["router"].answers = [answer("یک کارت.", cards=[own])]
    said = await say(client, owner, conv, "از مدیر فنی خودمان هم بپرس")
    (c4,) = said["answer"]["cards"]
    r = await run_card(client, owner, c4)
    assert r.status_code == 200, r.text
    [w4] = r.json()["made"]
    assert (await assignee_of(su, w4))["code"] == f"{co}-TECH-MGR"
    # the step names the right company's person; the person is present in the session
    rep_out = await report(client, owner, ref)
    assert {f"cto@{other}", f"cto@{co}"} <= {p["key"] for p in rep_out["participants"]}
    joined = [s["what_fa"] for s in rep_out["steps"] if "به جلسه آمد" in s["what_fa"]]
    assert joined and len(joined) == 2
    # (3) the joined persona's talk context carries the session's memory
    talk["router"].answers = [answer("حساب را ثبت میکنم.")]
    said = await say(client, owner, conv, "وضعیت چیست؟", to=f"cto@{other}")
    assert said["turn"]["by"] == f"cto@{other}"
    sent = talk["router"].text_sent()
    assert MEMORY_LINE in sent and "## The order you hold" in sent
    assert json.dumps(holder_key) in json.dumps(sent) or holder_key in sent


async def test_delegate_takes_a_company_and_a_named_server_points_at_its_company(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    """Audit M3: `delegate` leaves the holder's company when the card names one, like `ask`; and
    both resolve a server or a company the words name (the text, then the session's memory)
    before falling back to the holder's company — the owner who writes «IG-Hub» means IG's CTO."""
    co = (await new_company())["code"]
    other = await new_company()
    oc = other["code"]
    srv = f"Box-{oc}"  # (the seed's own IG-Hub exists already: a server name of this test's own)
    await su.execute(
        """INSERT INTO infra.servers (company_id, origin, name, state, last_seen_at)
           VALUES ($1, 'attached', $2, 'online', now())""",
        other["id"],
        srv,
    )
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref, conv = out["ref"], out["talk_ref"]
    root_ref = out["routes"][0]["work_ref"]
    await refuse_queued(su, root_ref)
    cards = [
        {"kind": "delegate", "title_fa": "به مدیر فنی آن شرکت بسپار", "body_fa": "",
         "payload": {"to": "cto", "company": oc, "text": "حساب را ثبت کن"}},
        {"kind": "ask", "title_fa": "از مدیر فنی سرور", "body_fa": "",
         "payload": {"to": "cto", "text": f"حساب را روی سرور {srv} ثبت کن"}},
        {"kind": "delegate", "title_fa": "به نام شرکت", "body_fa": "",
         "payload": {"to": "cto", "text": f"دستور خواندن را روی شرکت آزمایشی {oc} بگذار"}},
    ]  # fmt: skip
    talk["router"].answers = [answer("سه کارت.", cards=cards)]
    said = await say(client, owner, conv, "به مدیر فنی سرور بگو حساب را ثبت کند")
    by_title = {c["title_fa"]: c for c in said["answer"]["cards"]}
    # delegate with `company`: a work requested by the root in that company, for its CTO
    r = await run_card(client, owner, by_title[cards[0]["title_fa"]])
    assert r.status_code == 200, r.text
    [w1] = r.json()["made"]
    row = await su.fetchrow(
        """SELECT e.code, q.ref AS requested_by, w.parent_id FROM work.work w
           JOIN core.employees e ON e.id = w.assignee_id
           LEFT JOIN work.work q ON q.id = w.requested_by_work_id WHERE w.ref = $1""",
        w1,
    )
    assert row["code"] == f"{oc}-TECH-MGR" and row["requested_by"] == root_ref
    assert row["parent_id"] is None
    # a server named in the words: its company's CTO, no `company` written
    r = await run_card(client, owner, by_title[cards[1]["title_fa"]])
    assert r.status_code == 200, r.text
    [w2] = r.json()["made"]
    assert (await assignee_of(su, w2))["code"] == f"{oc}-TECH-MGR"
    # a company named by its name: the same
    r = await run_card(client, owner, by_title[cards[2]["title_fa"]])
    assert r.status_code == 200, r.text
    [w3] = r.json()["made"]
    assert (await assignee_of(su, w3))["code"] == f"{oc}-TECH-MGR"
    # the session's memory names the server: a plain ask for «the CTO» goes there too
    async with await all_tx(hub) as tx:
        rep = await OR.ensure(tx, ref)
        assert rep is not None
        await SE.remember(tx, rep["id"], f"حساب روی سرور {srv} است")
    plain_ask = {"kind": "ask", "title_fa": "از مدیر فنی", "body_fa": "",
                 "payload": {"to": "cto", "text": "آمار دیروز را بده"}}  # fmt: skip
    talk["router"].answers = [answer("میپرسم.", cards=[plain_ask])]
    said = await say(client, owner, conv, "از مدیر فنی آمار را بگیر")
    (c4,) = said["answer"]["cards"]
    r = await run_card(client, owner, c4)
    assert r.status_code == 200, r.text
    [w4] = r.json()["made"]
    assert (await assignee_of(su, w4))["code"] == f"{oc}-TECH-MGR"
    # the people joined this session; no new order anywhere
    rep_out = await report(client, owner, ref)
    assert f"cto@{oc}" in {p["key"] for p in rep_out["participants"]}
    assert await su.fetchval("SELECT count(*) FROM owner.orders WHERE ref > $1", ref) == 0
