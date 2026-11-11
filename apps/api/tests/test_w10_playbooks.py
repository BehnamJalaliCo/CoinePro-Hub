"""W10 (2026-11-07), contract §40: a session remembers, and becomes a working group («playbook»)
the owner can give to any company or platform. The owner: «۲-۳ هزار خط چت کردیم و به یه نتیجه رسیدیم.
میخوام اون نتیجه به یه اسکیل تبدیل بشه … که بتونم اونو به شرکت‌های دیگه هم بدم … همون مدل رو برای
یوتیوب … جلسات به همدیگه ارتباطی ندارن، کار گم میشه».

A. the session's memory: appended by code on a card done and a person joining, folded by a small
   model every 20 turns and at close (never blocking a turn), carried in the holder's and every
   participant's context with the company's last sessions;
B. the playbook: drafted by the holder from the session (a bad role and a bad RRULE dropped with a
   note), its card in the session, edited directly or in words, sealed 🔏 into a working group in
   the database with the session's hires in its seats, run by the groups' tick, untouched by the
   files' seeding;
C. given to another company: as is (a member at once), or as a new session with the playbook as
   its first word and `source` on the session; retired 🔏 (the routines stop, nothing deleted).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api import fresh_start as FS
from hq_api.domain import groups as GR
from hq_api.domain import hiring
from hq_api.domain import humanize as HZ
from hq_api.domain import order_turns as OT
from hq_api.domain import playbooks as PB
from hq_api.domain import session_memory as MEM
from hq_api.hub import Hub
from hq_api.talk import context as C
from hq_api.talk import store

from .conftest import idem, step_up
from .p10_fakes import holding_switch
from .test_p21_groups import TEHRAN, at
from .test_p21_routing_orders import all_tx, auto_hiring, envelope, report  # noqa: F401
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_p22_ops import route_answer
from .test_p23_talk import answer, say, talk  # noqa: F401 - the fixture
from .test_w7_sessions import run_card

REEL_TEXT = "برای {co} یک ریلز آموزشی بساز {w}"
RRULE = "FREQ=DAILY;BYHOUR=8;BYMINUTE=0"


def model(structured: dict[str, Any] | None) -> dict[str, Any]:
    """What the worker's OrderRouting workflow answers for a one-call use of the model."""
    return {"routes": None, "status": "ok", "structured": structured}


async def hire(hub: Hub, company: dict[str, Any], role: str) -> str:
    async with await all_tx(hub) as tx:
        out = await hiring.auto_fill(tx, company["id"], role, charters=hub.charters, reason="آزمون")
    return str(out["employee"])


async def memory_of(su: Any, ref: str) -> tuple[str | None, int]:
    row = await su.fetchrow(
        "SELECT memory_md, memory_upto FROM owner.order_reports WHERE ref = $1", ref
    )
    return row["memory_md"], int(row["memory_upto"])


async def join(client: httpx.AsyncClient, owner: dict[str, str], ref: str, key: str) -> None:
    r = await client.post(
        f"/api/v1/orders/{ref}/participants", headers=owner, json={"kind": "person", "key": key}
    )
    assert r.status_code == 200, r.text


def a_draft(co: str) -> dict[str, Any]:
    """What the holder's model writes for the Pro-Chart content session: a real role, a title
    for a role, a role nobody has (dropped), a bad RRULE (dropped), a routine on no seat
    (dropped), a KPI without a source (dropped), an unknown connection (dropped)."""
    return {
        "title_fa": "تولید محتوای روزانه با موضوع‌یاب",
        "purpose_fa": "هر روز یک موضوع تازه با ChatGPT پیدا شود و یک ریلز ساخته شود.",
        "platform": "instagram",
        "seats": [
            {"seat": "director", "role": "media_director", "title_fa": "مدیر محتوا",
             "duties_fa": "برنامه‌ی روز و بازبینی", "helpers": []},
            {"seat": "topic_finder", "role": "سناریست", "title_fa": "موضوع‌یاب",
             "duties_fa": "موضوع روزانه را با ChatGPT پیدا میکند", "helpers": ["gpt", "bing"],
             "model": None},
            {"seat": "pilot", "role": "خلبان", "title_fa": "خلبان", "duties_fa": "",
             "helpers": []},
        ],
        "routines": [
            {"key": "daily_topic", "title_fa": "موضوع روزانه", "seat": "topic_finder",
             "schedule": RRULE, "brief_md": "Find today's topic for {company_name} with ChatGPT."},
            {"key": "bad_rule", "title_fa": "روال خراب", "seat": "topic_finder",
             "schedule": "FREQ=YEARLY", "brief_md": "never"},
            {"key": "orphan", "title_fa": "روال بی‌جایگاه", "seat": "nobody",
             "schedule": RRULE, "brief_md": "never"},
        ],
        "kpis": [
            {"key": "views", "title_fa": "بازدید ریلز", "source": "instagram", "unit": "count"},
            {"key": "", "title_fa": "", "source": ""},
        ],
        "connections": ["instagram", "tiktok"],
        "rules_fa": ["هر ریلز با فونت شرکت تیتر میخورد.", ""],
    }  # fmt: skip


# ============================================================ A. the session remembers ==
async def test_the_session_remembers_by_code_and_a_small_model_folds_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = await new_company()
    co = company["code"]
    out = await post_order(client, owner, REEL_TEXT.format(co=co, w=words()))
    ref, conv = out["ref"], out["talk_ref"]
    holder_key = await su.fetchval("SELECT holder FROM talk.conversations WHERE ref = $1", conv)
    assert holder_key == f"media_director@{co}"
    assert await memory_of(su, ref) == (None, 0)
    # a person joining: one line, by code
    await join(client, owner, ref, "advisor")
    memory, _ = await memory_of(su, ref)
    assert memory == "- مشاور کل به جلسه آمد"
    # a card done: one line; a card that fails: none
    card = {
        "kind": "budget",
        "title_fa": "بودجه‌ی بیشتر",
        "body_fa": "",
        "payload": {"tokens": 5000},
    }
    bad = {"kind": "budget", "title_fa": "بودجه‌ی خراب", "body_fa": "", "payload": {"tokens": "x"}}
    talk["router"].answers = [answer("دو کارت.", cards=[card, bad])]
    said = await say(client, owner, conv, "بودجه بده")
    by_title = {c["title_fa"]: c for c in said["answer"]["cards"]}
    assert (await run_card(client, owner, by_title["بودجه‌ی بیشتر"])).status_code == 200
    assert (await run_card(client, owner, by_title["بودجه‌ی خراب"])).status_code == 422
    memory, upto = await memory_of(su, ref)
    assert memory is not None and upto == 0
    assert memory.splitlines() == ["- مشاور کل به جلسه آمد", "- بودجه انجام شد: بودجه‌ی بیشتر"]
    assert HZ.check(memory) == [], memory
    # the memory is in the holder's context (the talk) and in the run brief, and every participant
    # in the session reads it too; the persona is told what it is
    talk["router"].answers = [answer("خواندم.")]
    await say(client, owner, conv, "تا اینجا چه شد؟")
    body = talk["router"].bodies[-1]
    head = body["messages"][0]["content"]
    assert '"memory_md": "- مشاور کل به جلسه آمد' in head
    assert "«memory_md» under «## The order you hold» is this session's memory" in body["system"]
    talk["router"].answers = [answer("من هم خواندم.")]
    await say(client, owner, conv, "نظر مشاور؟", to="advisor")
    assert (
        '"memory_md": "- مشاور کل به جلسه آمد'
        in talk["router"].bodies[-1]["messages"][0]["content"]
    )
    async with await all_tx(hub) as tx:
        brief = await OT.talk_brief(tx, ref)
    assert brief is not None and brief["memory_md"].startswith("- مشاور کل به جلسه آمد")
    assert "related_sessions" not in brief  # the company's first session
    rep = await report(client, owner, ref)
    assert rep["memory_md"] == memory
    # the fold: the cheapest model's task class, the turns masked, the memory replaced; not due
    # before 20 turns unless forced (at close)
    turns = int(await su.fetchval("SELECT turns FROM talk.conversations WHERE ref = $1", conv))
    folded = "## تصمیم‌ها\n- بودجه‌ی بیشتر داده شد\n## چه کسی چه میکند\n- مشاور کل: مشورت"
    seen = route_answer(monkeypatch, model({"memory_md": folded}))
    async with await all_tx(hub) as tx:
        assert await MEM.due(tx, ref) is False
    assert await MEM.fold(hub, MEM.api_call(hub), ref) == {"folded": False, "why": "not_due"}
    assert seen == []
    assert await MEM.fold(hub, MEM.api_call(hub), ref, force=True) == {
        "folded": True,
        "upto": turns,
    }
    assert len(seen) == 1 and seen[0]["task_class"] == MEM.TASK_CLASS
    prompt = json.loads(seen[0]["prompt"])
    assert prompt["memory_so_far"] == memory and prompt["session"] == ref
    assert any("بودجه بده" in line for line in prompt["new_turns"])
    assert "مشاور کل" in prompt["present"]
    assert seen[0]["json_schema"]["properties"]["memory_md"]["maxLength"] == MEM.MEMORY_CHARS
    assert await memory_of(su, ref) == (folded, turns)
    # a failure never blocks: the old memory stays
    route_answer(monkeypatch, None)
    assert (await MEM.fold(hub, MEM.api_call(hub), ref, force=True))["folded"] is False
    assert await memory_of(su, ref) == (folded, turns)
    # 20 more turns: due, and folded by the worker's path (its router)
    async with await all_tx(hub) as tx:
        locked = await store.conversation(tx, conv, lock=True)
        for i in range(MEM.FOLD_EVERY):
            await OT.post_turn(tx, locked, holder_key, f"قدم {i}", f"قدم {i}")
        assert await MEM.due(tx, ref) is True
    got = await MEM.fold(hub, MEM.router_call(talk["router"]), ref)
    assert got["folded"] is False  # the fake router answers the summary's shape, not the memory's
    assert talk["router"].bodies[-1]["task_class"] == MEM.TASK_CLASS
    # at close, the api folds once more in the background
    seen = route_answer(monkeypatch, model({"memory_md": folded + "\n## نکته‌های باز\n- بسته شد"}))
    r = await client.post(
        f"/api/v1/orders/{ref}/close", headers={**owner, **idem()}, json={"verdict": "cancel"}
    )
    assert r.status_code == 200, r.text
    assert len(seen) == 1 and seen[0]["task_class"] == MEM.TASK_CLASS
    memory, upto = await memory_of(su, ref)
    assert memory is not None and memory.endswith("- بسته شد")
    # … through the close's own line («لغو و بستن» is the owner's last turn)
    assert upto == await su.fetchval("SELECT turns FROM talk.conversations WHERE ref = $1", conv)
    assert upto == turns + MEM.FOLD_EVERY + 1
    # related sessions: the company's next session names this one (title, one line, no playbook)
    out2 = await post_order(client, owner, REEL_TEXT.format(co=co, w=words()))
    async with await all_tx(hub) as tx:
        brief = await OT.talk_brief(tx, out2["ref"])
    assert brief is not None
    [related] = brief["related_sessions"]
    assert related["order"] == ref and related["state"] == "closed" and related["playbook"] is None
    assert related["title_fa"].startswith("برای") and related["outcome_fa"]
    assert HZ.check(related["outcome_fa"]) == []


def test_the_memory_keeps_its_last_lines_and_the_fold_is_bounded() -> None:
    long = "\n".join(f"- خط {i} " + "x" * 50 for i in range(200))
    kept = MEM._fit(long)
    assert len(kept) <= MEM.MEMORY_CHARS and kept.startswith("- خط") and kept.endswith("x")
    assert kept.splitlines()[-1].startswith("- خط 199")
    body = MEM.body_of("HQ", "F-0001", None, ["مدیر رسانه"], ["مدیر کل: سلام"])
    assert body["task_class"] == "session_memory" and body["effort"] == "low"
    assert body["json_schema"] == MEM.SCHEMA and "memory_md" in body["system"]
    assert "owner.playbooks" in FS.KEEP and "owner.playbook_ref_seq" in FS.REF_KEEP


# ====================================================== B. the playbook, from the session ==
async def test_the_holder_drafts_a_playbook_the_owner_edits_and_seals_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    auto_hiring: None,  # noqa: F811
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = owner_session["headers"]
    company = await new_company()
    co = company["code"]
    await envelope(su, company)
    out = await post_order(client, owner, REEL_TEXT.format(co=co, w=words()))
    ref, conv = out["ref"], out["talk_ref"]
    # the topic finder hired from inside the session (§39: joins it at once)
    writer = await hire(hub, company, "scriptwriter")
    await join(client, owner, ref, f"scriptwriter@{co}")
    holding = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
    # the draft: the holder's one call with the session's material; code checks what comes back
    seen = route_answer(monkeypatch, model(a_draft(co)))
    r = await client.post(f"/api/v1/orders/{ref}/playbook", headers=owner)
    assert r.status_code == 422  # Idempotency-Key
    key = idem()
    r = await client.post(f"/api/v1/orders/{ref}/playbook", headers={**owner, **key})
    assert r.status_code == 201, r.text
    pb = r.json()
    pref = pb["ref"]
    assert pref.startswith("PB-") and pb["state"] == "draft" and pb["version"] == 1
    assert pb["platform"] == "instagram" and pb["title_fa"] == "تولید محتوای روزانه با موضوع‌یاب"
    assert [(s["seat"], s["role"]) for s in pb["seats"]] == [
        ("director", "media_director"), ("topic_finder", "scriptwriter")
    ]  # fmt: skip
    assert pb["seats"][1]["helpers"] == ["gpt"] and pb["seats"][1]["title_fa"] == "موضوع‌یاب"
    assert [r_["key"] for r_ in pb["routines"]] == ["daily_topic"]
    assert (
        pb["routines"][0]["schedule"] == RRULE
        and pb["routines"][0]["max_tokens"] == PB.DEFAULT_TOKENS
    )
    assert [k["key"] for k in pb["kpis"]] == ["views"] and pb["connections"] == ["instagram"]
    assert pb["rules_fa"] == ["هر ریلز با فونت شرکت تیتر میخورد."]
    assert pb["source"] == {"order": ref, "company": co, "conversation": conv}
    assert pb["members"] == [] and pb["parent"] is None and pb["sealed_at"] is None
    note = pb["note_fa"]
    assert "«خلبان»" in note and "روال خراب" in note and "RRULE" in note and "tiktok" in note
    assert "روال بی‌جایگاه" in note and HZ.check(note) == [], note
    # what the holder read: its task class, the session's people and the company's real roles
    assert len(seen) == 1 and seen[0]["task_class"] == PB.TASK_CLASS
    prompt = json.loads(seen[0]["prompt"])
    assert prompt["company"] == co and prompt["roles"]["scriptwriter"] == "سناریست"
    assert {p["role"] for p in prompt["people_in_the_session"]} == {
        "media_director",
        "scriptwriter",
    }
    assert prompt["skeleton"]["seats"][1]["role"] == "scriptwriter"
    assert seen[0]["json_schema"] == PB.SCHEMA
    # the same key: the same draft, not a second one
    again = await client.post(f"/api/v1/orders/{ref}/playbook", headers={**owner, **key})
    assert again.status_code == 201 and again.json()["ref"] == pref
    assert again.headers.get("Idempotent-Replay") == "true"
    assert (
        await su.fetchval("SELECT count(*) FROM owner.playbooks WHERE source->>'order' = $1", ref)
        == 1
    )
    assert (
        await su.fetchval("SELECT company_id FROM owner.playbooks WHERE ref = $1", pref) == holding
    )
    # the card «کارگروه از این جلسه» in the session, under the holder, and the step
    card = await su.fetchrow(
        """SELECT c.kind, c.payload, c.state, t.persona FROM talk.cards c JOIN talk.turns t ON t.id = c.turn_id
           JOIN talk.conversations v ON v.id = c.conversation_id WHERE v.ref = $1 AND c.kind = 'playbook'""",
        conv,
    )
    assert card["state"] == "offered" and card["persona"] == f"media_director@{co}"
    assert json.loads(card["payload"]) == {"playbook": pref}
    rep = await report(client, owner, ref)
    assert (
        rep["steps"][-1]["what_fa"] == f"کارگروه از این جلسه پیش‌نویس شد: {pref} «{pb['title_fa']}»"
    )
    assert rep["memory_md"].splitlines()[-1].startswith(f"- کارگروه از این جلسه پیش‌نویس شد: {pref}")
    # the library
    r = await client.get("/api/v1/playbooks", headers=owner, params={"state": "draft"})
    assert pref in {x["ref"] for x in r.json()}
    assert (await client.get(f"/api/v1/playbooks/{pref}", headers=owner)).json()["ref"] == pref
    assert (await client.get("/api/v1/playbooks/PB-9999", headers=owner)).status_code == 404
    # the owner edits it directly: the whole checked again, the version counts up
    r = await client.patch(f"/api/v1/playbooks/{pref}", headers=owner, json={})
    assert r.status_code == 422
    r = await client.patch(
        f"/api/v1/playbooks/{pref}",
        headers=owner,
        json={
            "title_fa": "موضوع‌یاب روزانه",
            "routines": [*pb["routines"], {"key": "weekly", "title_fa": "جمع‌بندی هفته",
                                           "seat": "director", "schedule": "FREQ=WEEKLY;BYDAY=FR;BYHOUR=18",
                                           "brief_md": "Sum the week up for {company_name}."},
                         {"key": "nope", "title_fa": "بی‌زمان", "seat": "director",
                          "schedule": "whenever", "brief_md": "x"}],
        },
    )  # fmt: skip
    assert r.status_code == 200, r.text
    pb = r.json()
    assert pb["version"] == 2 and pb["title_fa"] == "موضوع‌یاب روزانه"
    assert [x["key"] for x in pb["routines"]] == ["daily_topic", "weekly"]
    assert "بی‌زمان" in pb["note_fa"] and "«خلبان»" not in pb["note_fa"]
    # … or in words: the holder offers the full new draft as a `playbook` card
    draft = {**a_draft(co), "title_fa": "موضوع‌یاب روزانه (نسخه‌ی مدیر)", "platform": "youtube",
             "routines": pb["routines"]}  # fmt: skip
    rewrite = {"kind": "playbook", "title_fa": "بازنویسی کارگروه", "body_fa": "",
               "payload": {"playbook": pref, "draft": draft}}  # fmt: skip
    talk["router"].answers = [answer("بازنویسی کردم.", cards=[rewrite])]
    said = await say(client, owner, conv, "پلتفرم را یوتیوب کن و اسمش را عوض کن")
    assert "playbook: the owner asked, in words" in talk["router"].bodies[-1]["system"]
    assert f'"playbooks": [{{"ref": "{pref}"' in talk["router"].bodies[-1]["messages"][0]["content"]
    (c,) = said["answer"]["cards"]
    r = await run_card(client, owner, c)
    assert r.status_code == 200, r.text
    assert r.json()["made"] == [pref]
    pb = (await client.get(f"/api/v1/playbooks/{pref}", headers=owner)).json()
    assert pb["version"] == 3 and pb["platform"] == "youtube"
    assert pb["title_fa"] == "موضوع‌یاب روزانه (نسخه‌ی مدیر)"
    rep = await report(client, owner, ref)
    assert rep["steps"][-1]["what_fa"].startswith(f"پیش‌نویس کارگروه {pref} بازنویسی شد (نسخه‌ی 3)")
    # the pointer card (no draft) only points
    r = await run_card(client, owner, {"id": str(await su.fetchval(
        "SELECT c.id FROM talk.cards c JOIN talk.conversations v ON v.id = c.conversation_id "
        "WHERE v.ref = $1 AND c.kind = 'playbook' AND c.payload->>'draft' IS NULL", conv))})  # fmt: skip
    assert r.status_code == 200 and r.json()["made"] == [pref]
    # the seal: the owner's tap (⟨§45⟩ no passkey since 2026-11-10: it is for money, deleting
    # for good, keys and access, a destructive command)
    r = await client.post(f"/api/v1/playbooks/{pref}/seal", headers=owner)
    assert r.status_code == 200, r.text
    pb = r.json()
    gkey = PB.group_key(pref)
    assert pb["state"] == "sealed" and pb["sealed_at"] and pb["group"] == gkey
    [member] = pb["members"]
    # ⟨§45⟩ without his standing word each output waits for his tap
    asks = {"mode": "ask", "account": None, "story": False, "since": None, "at": None,
            "best": False}  # fmt: skip
    assert member == {"company": co, "name_fa": f"شرکت آزمایشی {co}", "state": "on", "order": ref,
                      "publish": asks}  # fmt: skip
    # a working group in the database: eligibility `chosen`, on, version 1, the playbook named
    r = await client.get(f"/api/v1/groups/{gkey}", headers=owner)
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["eligible"] == "chosen" and g["state"] == "on" and g["version"] == 1
    assert g["playbook"] == pref and g["lead"] == "director"
    assert [(s["seat"], s["role"]) for s in g["seats"]] == [
        ("director", "media_director"), ("topic_finder", "scriptwriter")
    ]  # fmt: skip
    assert [x["key"] for x in g["routines"]] == ["daily_topic", "weekly"]
    assert g["routines"][0]["max_tokens"] == PB.DEFAULT_TOKENS and g["routines"][0]["state"] == "on"
    assert g["kpis"][0]["key"] == "views" and g["connections"] == ["instagram"]
    # the seats are the session's hires
    r = await client.get(f"/api/v1/groups/{gkey}/members", headers=owner)
    [m] = r.json()
    assert {s["seat"]: s["employee"] for s in m["seats"]} == {
        "director": f"{co}-MEDIA-MGR", "topic_finder": writer
    }  # fmt: skip
    rep = await report(client, owner, ref)
    assert rep["steps"][-1]["what_fa"] == f"کارگروه {pref} مُهر شد و راه افتاد؛ 2 جایگاه از 2 پر است"
    # sealed: no edits, no second seal
    r = await client.patch(f"/api/v1/playbooks/{pref}", headers=owner, json={"title_fa": "x"})
    assert r.status_code == 409
    r = await client.post(f"/api/v1/playbooks/{pref}/seal",
                          headers={**owner, **await step_up(hub, owner_session["session_id"], "playbook.seal", pref)})  # fmt: skip
    assert r.status_code == 409
    # the tick runs its routine for the member exactly as a file group's: one work for the seat
    day = datetime.now(TEHRAN).date() + timedelta(days=1)
    async with holding_switch(su, "released"):
        first = await GR.tick(hub, now=at(day, 8, 0), only={company["id"]})
        again = await GR.tick(hub, now=at(day, 8, 5), only={company["id"]})
    assert first["queued"] == 1 and again["queued"] == 0, (first, again)
    run = await su.fetchrow(
        """SELECT x.routine, x.state, x.employee_code, w.ref, w.budget_tokens, w.brief, w.run_meta
           FROM growth.routine_runs x JOIN growth.groups g ON g.id = x.group_id
           LEFT JOIN work.work w ON w.id = x.work_id WHERE g.key = $1""",
        gkey,
    )
    assert run["routine"] == "daily_topic" and run["state"] == "queued"
    assert run["employee_code"] == writer and run["budget_tokens"] == PB.DEFAULT_TOKENS
    assert f"شرکت آزمایشی {co}" in run["brief"] and "ChatGPT" in run["brief"]
    meta = json.loads(run["run_meta"]) if isinstance(run["run_meta"], str) else run["run_meta"]
    assert meta["group"] == gkey and meta["routine"] == "daily_topic"
    # the files' seeding never touches it; nobody joins it by itself
    async with await all_tx(hub) as tx:
        await GR.seed(tx, holding)
        row = await GR.row_of(tx, gkey)
        assert row["version"] == 1 and row["state"] == "on"
        assert await GR.eligible(tx, GR.render(row)) == []
        assert await GR.reconcile_members(tx, row, fill=False) == {
            "joined": 0,
            "filled": 0,
            "asked": 0,
        }
    assert gkey not in {k for k, _ in GR.load_files()}
    assert (
        await su.fetchval(
            "SELECT count(*) FROM growth.memberships m JOIN growth.groups g ON g.id = m.group_id WHERE g.key = $1",
            gkey,
        )
        == 1
    )
    # audited as the owner's (A3), without a step-up
    row = await su.fetchrow(
        "SELECT step_up, action_class, actor_kind FROM audit.entries "
        "WHERE action = 'playbook.seal' AND target_ref = $1",
        pref,
    )
    assert (row["step_up"], row["action_class"], row["actor_kind"]) == (False, "A3", "owner")


# ================================================= C. given to another company or platform ==
async def test_a_draft_that_fails_after_the_model_keeps_its_key_free(
    client: httpx.AsyncClient,
    owner_session: dict[str, Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Audit 2026-11-11: the key is claimed with the stored draft, so a draft that fails after
    the model call is retried with the same Idempotency-Key (not 409 «still running»)."""
    from hq_api.errors import ApiError

    owner = owner_session["headers"]
    company = await new_company()
    co = company["code"]
    await envelope(su, company)
    ref = (await post_order(client, owner, REEL_TEXT.format(co=co, w=words())))["ref"]
    route_answer(monkeypatch, model(a_draft(co)))
    real = PB.store_draft
    calls: list[int] = []

    async def once(*a: Any, **kw: Any) -> Any:
        calls.append(1)
        if len(calls) == 1:
            raise ApiError(503, "internal_error", "store failed once")
        return await real(*a, **kw)

    monkeypatch.setattr(PB, "store_draft", once)
    key = idem()
    r = await client.post(f"/api/v1/orders/{ref}/playbook", headers={**owner, **key})
    assert r.status_code == 503, r.text
    r = await client.post(f"/api/v1/orders/{ref}/playbook", headers={**owner, **key})
    assert r.status_code == 201, r.text
    again = await client.post(f"/api/v1/orders/{ref}/playbook", headers={**owner, **key})
    assert again.status_code == 201 and again.json()["ref"] == r.json()["ref"]
    assert again.headers.get("Idempotent-Replay") == "true"
    assert (
        await su.fetchval("SELECT count(*) FROM owner.playbooks WHERE source->>'order' = $1", ref)
        == 1
    )


async def test_a_sealed_playbook_is_given_as_is_or_adapted_in_a_new_session_and_retired(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    auto_hiring: None,  # noqa: F811
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = owner_session["headers"]
    company = await new_company()
    co = company["code"]
    await envelope(su, company)
    out = await post_order(client, owner, REEL_TEXT.format(co=co, w=words()))
    ref = out["ref"]
    await hire(hub, company, "scriptwriter")
    await join(client, owner, ref, f"scriptwriter@{co}")
    route_answer(monkeypatch, model(a_draft(co)))
    r = await client.post(f"/api/v1/orders/{ref}/playbook", headers={**owner, **idem()})
    assert r.status_code == 201, r.text
    pref = r.json()["ref"]
    gkey = PB.group_key(pref)
    # not sealed yet: no membership as is, and nothing runs before the seal
    other = await new_company()
    await envelope(su, other)
    r = await client.post(f"/api/v1/playbooks/{pref}/apply", headers={**owner, **idem()},
                          json={"company": other["code"], "as_is": True})  # fmt: skip
    assert r.status_code == 409 and "مُهر" in r.json()["message_fa"]
    assert await su.fetchval("SELECT 1 FROM growth.groups WHERE key = $1", gkey) is None
    su_h = await step_up(hub, owner_session["session_id"], "playbook.seal", pref)
    assert (
        await client.post(f"/api/v1/playbooks/{pref}/seal", headers={**owner, **su_h})
    ).status_code == 200
    # as is: the other company joins the sealed group at once, its seats filled by automatic
    # hiring inside its envelope (§29.10); no session
    orders_before = await su.fetchval("SELECT count(*) FROM owner.orders")
    async with holding_switch(su, "released"):  # automatic hiring runs only with the hub launched
        r = await client.post(f"/api/v1/playbooks/{pref}/apply", headers={**owner, **idem()},
                              json={"company": other["code"], "as_is": True})  # fmt: skip
    assert r.status_code == 200, r.text
    applied = r.json()
    assert applied["order"] is None and applied["conversation"] is None
    assert applied["member"]["company"] == other["code"] and applied["member"]["state"] == "on"
    assert {m["company"] for m in applied["playbook"]["members"]} == {co, other["code"]}
    assert await su.fetchval("SELECT count(*) FROM owner.orders") == orders_before
    r = await client.get(f"/api/v1/groups/{gkey}/members", headers=owner)
    seats = {m["company"]: {s["seat"]: s["employee"] for s in m["seats"]} for m in r.json()}
    assert seats[other["code"]]["director"] == f"{other['code']}-MEDIA-MGR"
    hired = seats[other["code"]]["topic_finder"]
    assert hired and hired.startswith(other["code"]), seats
    assert (
        await su.fetchval(
            "SELECT role FROM core.employees WHERE code = $1 AND status = 'active'", hired
        )
        == "scriptwriter"
    )
    assert (await client.post(f"/api/v1/playbooks/{pref}/apply", headers={**owner, **idem()},
                              json={"company": "ZZZZ", "as_is": True})).status_code == 404  # fmt: skip
    # with a platform: a new session for that company, the playbook its first word, `source` set
    third = await new_company()
    r = await client.post(
        f"/api/v1/playbooks/{pref}/apply",
        headers={**owner, **idem()},
        json={"company": third["code"], "platform": "telegram", "note_fa": "با لحن رسمی‌تر"},
    )
    assert r.status_code == 200, r.text
    applied = r.json()
    new_ref, new_conv = applied["order"], applied["conversation"]
    assert new_ref and new_ref != ref and new_conv and applied["member"] is None
    assert await su.fetchval("SELECT count(*) FROM owner.orders") == orders_before + 1
    text = await su.fetchval("SELECT text FROM owner.orders WHERE ref = $1", new_ref)
    assert text.startswith(
        f"این کارگروه را برای شرکت آزمایشی {third['code']} روی تلگرام پیاده کن: با لحن رسمی‌تر"
    )
    # the owner's words only: the title, the people, plain times; no ref, no RRULE, no role key
    assert "# کارگروه «" in text and "موضوع‌یاب" in text and "هر روز ساعت 08:00" in text
    assert pref not in text and RRULE not in text
    rep = await report(client, owner, new_ref)
    assert rep["session"]["source"] == pref and rep["session"]["state"] == "open"
    assert rep["participants"][0]["company"] == third["code"]
    assert rep["memory_md"] == f"- این جلسه از کارگروه {pref} باز شد"
    listed = (await client.get("/api/v1/sessions", headers=owner)).json()["items"]
    assert next(s for s in listed if s["ref"] == new_ref)["source"] == pref
    detail = (await client.get(f"/api/v1/talk/conversations/{new_conv}", headers=owner)).json()
    assert detail["order_ref"] == new_ref
    owner_turns = [t for t in detail["turns_page"]["items"] if t["by"] == "owner"]
    assert owner_turns and "# کارگروه «" in owner_turns[-1]["text"]
    async with await all_tx(hub) as tx:
        brief = await OT.talk_brief(tx, new_ref)
    assert brief is not None and brief["source_playbook"] == pref
    # the holder sees every key the owner's words leave out
    defn = brief["source_playbook_definition"]
    assert defn["routines"] and defn["routines"][0]["schedule"] == RRULE and defn["seats"]
    # the playbook lists that session as the company's (not yet a member)
    pb = (await client.get(f"/api/v1/playbooks/{pref}", headers=owner)).json()
    assert third["code"] not in {m["company"] for m in pb["members"]}
    # sealing a draft from the adapted session: a version with `parent`, that company a member
    route_answer(monkeypatch, model({**a_draft(third["code"]), "platform": "telegram",
                                     "title_fa": "موضوع‌یاب تلگرام"}))  # fmt: skip
    r = await client.post(f"/api/v1/orders/{new_ref}/playbook", headers={**owner, **idem()})
    assert r.status_code == 201, r.text
    child = r.json()
    assert child["parent"] == pref and child["platform"] == "telegram" and child["state"] == "draft"
    assert child["source"]["order"] == new_ref and child["source"]["company"] == third["code"]
    su_h = await step_up(hub, owner_session["session_id"], "playbook.seal", child["ref"])
    r = await client.post(f"/api/v1/playbooks/{child['ref']}/seal", headers={**owner, **su_h})
    assert r.status_code == 200, r.text
    [m] = r.json()["members"]
    assert m["company"] == third["code"] and m["order"] == new_ref
    assert PB.group_key(child["ref"]) != gkey
    # the retire: the owner's tap (⟨§45⟩), the group off (its routines stop for every member),
    # nothing deleted; a client that still sends a step-up assertion is answered the same
    su_h = await step_up(hub, owner_session["session_id"], "playbook.retire", pref)
    r = await client.post(f"/api/v1/playbooks/{pref}/retire", headers={**owner, **su_h})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "retired" and r.json()["retired_at"]
    assert len(r.json()["members"]) == 2
    assert await su.fetchval("SELECT state FROM growth.groups WHERE key = $1", gkey) == "off"
    day = datetime.now(TEHRAN).date() + timedelta(days=2)
    async with holding_switch(su, "released"):
        ticked = await GR.tick(hub, now=at(day, 8, 0), only={company["id"], other["id"]})
    assert (
        await su.fetchval(
            "SELECT count(*) FROM growth.routine_runs x JOIN growth.groups g ON g.id = x.group_id WHERE g.key = $1",
            gkey,
        )
        == 0
    ), ticked
    r = await client.post(f"/api/v1/playbooks/{pref}/apply", headers={**owner, **idem()},
                          json={"company": other["code"], "platform": "site"})  # fmt: skip
    assert r.status_code == 409
    r = await client.get("/api/v1/playbooks", headers=owner, params={"state": "retired"})
    assert pref in {x["ref"] for x in r.json()}
    # the holder of the first session is told of its playbooks
    async with await all_tx(hub) as tx:
        brief = await OT.talk_brief(tx, ref)
    assert brief is not None and [b["ref"] for b in brief["playbooks"]] == [pref]
    assert brief["playbooks"][0]["state"] == "retired"


def test_the_shapes_are_checked_by_code_never_refused() -> None:
    notes: list[str] = []
    d = PB.normalise(
        {"seats": [{"role": "ceo", "seat": "Boss Man"}], "platform": "mars"}, None, None, notes
    )
    assert d["title_fa"] == "کارگروه از این جلسه" and d["platform"] == "any" and d["seats"] == []
    assert any("mars" in n for n in notes) and any("ceo" in n for n in notes)
    assert PB.group_key("PB-0012") == "pb_0012"
    text = PB.markdown(PB.Playbook(
        ref="PB-0001", title_fa="t", purpose_fa="p", state="draft", version=1, platform="any",
        source=PB.PlaybookSource(order="F-0001", company=None, conversation=None),
        created_at=datetime.now(),
    ))  # fmt: skip
    assert text.startswith("# کارگروه «t»") and "هر پلتفرمی" in text and "PB-" not in text
    # the owner's words: helpers by name, times in plain Persian, no RRULE, no role key
    rich = PB.markdown(PB.Playbook(
        ref="PB-0002", title_fa="موضوع روزانه", purpose_fa="", state="sealed", version=1,
        platform="instagram",
        seats=[PB.PlaybookSeat(seat="writer", role="scriptwriter", title_fa="نویسنده",
                               duties_fa="موضوع روز", helpers=["gpt"])],
        routines=[PB.PlaybookRoutine(key="topic", title_fa="یافتن موضوع", seat="writer",
                                     schedule="FREQ=DAILY;BYHOUR=8;BYMINUTE=0", brief_md="x")],
        source=PB.PlaybookSource(order="F-0001", company=None, conversation=None),
        created_at=datetime.now(),
    ))  # fmt: skip
    assert "ChatGPT" in rich and "هر روز ساعت 08:00" in rich and "با نویسنده" in rich
    assert (
        "FREQ=" not in rich
        and "scriptwriter" not in rich
        and "gpt" not in rich.replace("ChatGPT", "")
    )
    assert "playbook" in C.BOUND_HELP and "playbook" in store.CardKind.__args__  # type: ignore[attr-defined]
