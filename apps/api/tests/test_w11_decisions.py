"""The owner's three decisions of 2026-11-08 (W11, after the audit):

1. Voice is off. The talk answers in text alone (`voice.enabled`, default false); no «صدا در
   دسترس نیست» line, ever; the voice is no readiness item, blocker, brief block or owner's step.
2. Instagram = IG-Hub, for every company. The owner never reads an Instagram blocker, «وصل نیست»
   or a step of his own; a company whose accounts are not registered here gets the holding's
   technical work made by code (IG-Hub's CTO, else AIOPS: `connection.set` + `server.*` on IG-Hub),
   once, under the order; the session reads one technical step.
3. No video tool. `media.render`, `media.on`, ffmpeg and the voice are never a blocker or a
   readiness item; the brief and the charters say the video step of a plan is done when the media
   team delivers the «بسته‌ی ساخت ویدیو».
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from hq_api.domain import capabilities as CAP
from hq_api.domain import connections as CN
from hq_api.domain import order_turns as OT
from hq_api.domain import work as W
from hq_api.hub import Hub
from hq_api.voice import store as voice_store
from hq_common import charters as CHL

from .test_p21_readiness import auto_hiring, checks, holding_switch
from .test_p21_routing_orders import all_tx, make_order, report
from .test_p21_secretary import no_model  # noqa: F401 - the fixture
from .test_p23_talk import answer, events_of, open_cv, say, talk  # noqa: F401 - the fixture
from .test_w7_sessions import WORK_TEXT, refuse_queued
from .test_w11_audit import done_run, words

IG_STEP = "تیم فنی حساب‌های اینستاگرام را از راه IG-Hub به هاب معرفی میکند"


# ============================================================== 1. voice is off ==
def test_voice_is_off_by_default_and_the_setting_turns_it_on() -> None:
    assert voice_store.settings_of(None)["enabled"] is False
    assert voice_store.settings_of({})["enabled"] is False
    assert voice_store.settings_of({"enabled": True})["enabled"] is True


async def test_a_talk_turn_with_voice_off_is_text_alone_and_says_nothing_of_a_voice(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    talk: dict[str, Any],  # noqa: F811
) -> None:
    # the default: `enabled` absent (the talk fixture turned it on for the voice tests)
    await su.execute("UPDATE owner.settings SET voice = voice - 'enabled' WHERE id = 1")
    try:
        cv = await open_cv(client, owner)
        talk["voice"].unavailable = False
        talk["router"].answers = [answer("سلام. همه چیز خوب است.", "**همه چیز خوب است.**")]
        out = await say(client, owner, cv["ref"], "سلام")
        a = out["answer"]
        assert a["state"] == "done" and a["show_md"].strip() == "**همه چیز خوب است.**"
        assert "صدا" not in a["show_md"]
        assert talk["voice"].said == []  # nothing synthesised
        assert a["audio"] == []
        kinds = [k for k, _ in await events_of(client, owner, a["id"])]
        assert "say" not in kinds and "audio" not in kinds and kinds[-1] == "done"
        # the layer down changes nothing: still text alone, no notice
        talk["voice"].unavailable = True
        talk["router"].answers = [answer("باز هم سلام.", "**باز هم.**")]
        out = await say(client, owner, cv["ref"], "دوباره")
        assert out["answer"]["state"] == "done" and "صدا" not in out["answer"]["show_md"]
        # the owner turns it on: the sentences are spoken again (the voice code stays)
        cur = await client.get("/api/v1/owner/settings", headers=owner)
        r = await client.put(
            "/api/v1/owner/settings",
            headers={**owner, "If-Match": f'"{cur.json()["version"]}"'},
            json={"voice": {"enabled": True}},
        )
        assert r.status_code == 200 and r.json()["voice"]["enabled"] is True, r.text
        talk["voice"].unavailable = False
        talk["router"].answers = [answer("سلام سوم.", "**سوم.**")]
        out = await say(client, owner, cv["ref"], "سوم")
        assert len(out["answer"]["audio"]) == 1 and len(talk["voice"].said) == 1
    finally:
        await su.execute("UPDATE owner.settings SET voice = voice - 'enabled' WHERE id = 1")


# ============================================= 2. Instagram is IG-Hub, for every company ==
async def test_an_instagram_refusal_makes_the_technical_work_once_and_no_blocker(
    hub: Hub,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    await su.execute(
        """INSERT INTO growth.connections (company_id, kind, label_fa, config, origin)
           VALUES ($1, 'instagram', 'اینستاگرام (از راه IG-Hub)',
                   '{"via": "ig_hub", "accounts": [], "server": {"company": "IG", "name": "IG-Hub"}}'::jsonb,
                   'seed')""",
        company["id"],
    )
    made = await make_order(hub, company, WORK_TEXT.format(co=co, w=words()))
    ref, w = made["ref"], made["work"]
    await refuse_queued(su, w["ref"])
    await done_run(su, w["id"], "ig:1",
                   [{"tool": "instagram", "outcome": "refused", "code": "channel_not_configured"}])  # fmt: skip
    rep = await report(client, owner, ref)
    assert rep["blockers"] == [], rep["blockers"]
    assert rep["session"]["badge"] != "your_turn"
    assert [s["what_fa"] for s in rep["steps"]].count(IG_STEP) == 1
    assert not any("وصل نیست" in json.dumps(s, ensure_ascii=False) for s in rep["steps"])
    # the technical work: IG-Hub's CTO (else the holding's AIOPS), under the order's work
    async with await all_tx(hub) as tx:
        who = await CN.ig_setup_assignee(tx)
        setup_ref = await CN.ig_setup_work(tx, company["id"])
    assert who is not None and setup_ref is not None
    row = await su.fetchrow(
        """SELECT w.title, w.brief, w.status, w.budget_tokens, w.run_meta, e.code, q.ref AS under
           FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           LEFT JOIN work.work q ON q.id = w.requested_by_work_id WHERE w.ref = $1""",
        setup_ref,
    )
    assert row["code"] == who["code"] and row["under"] == w["ref"]
    assert json.loads(row["run_meta"])["ig_setup"] == co and row["status"] in W.OPEN
    assert "connection.set" in row["brief"] and "server.map" in row["brief"]
    assert "IG-Hub" in row["title"] and "اینستاگرام" in row["title"]
    assert row["budget_tokens"] is None  # never stopped by a cap of its own
    # once: a second refusal and a second refresh make no second work and no second step
    await done_run(su, w["id"], "ig:2",
                   [{"tool": "instagram", "outcome": "refused", "code": "channel_not_configured"}])  # fmt: skip
    rep = await report(client, owner, ref)
    assert [s["what_fa"] for s in rep["steps"]].count(IG_STEP) == 1
    n = await su.fetchval("SELECT count(*) FROM work.work WHERE run_meta ->> 'ig_setup' = $1", co)
    assert n == 1
    # the daily read's hook makes the same work (idempotent) for a read path not registered
    async with await all_tx(hub) as tx:
        assert await CN.ensure_ig_setup_work(tx, company["id"]) == setup_ref
    n = await su.fetchval("SELECT count(*) FROM work.work WHERE run_meta ->> 'ig_setup' = $1", co)
    assert n == 1


async def test_readiness_never_shows_an_instagram_or_media_step_to_the_owner(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    await auto_hiring(su)
    async with holding_switch(su, "engaged"):
        r = await client.get(f"/api/v1/companies/{co['code']}/readiness", headers=owner,
                             params={"group": "content"})  # fmt: skip
    c = checks(r)
    assert "media_tools" not in c
    assert c["channels"]["ok"] and c["channels"]["fix"] is None
    assert (
        c["channels"]["detail_fa"]
        == "اینستاگرام از راه IG-Hub خوانده و منتشر میشود؛ تیم فنی حساب‌ها را به هاب معرفی میکند."
    )
    assert c["group"]["fix"] is None and "تیم فنی" in c["group"]["detail_fa"]
    for x in c.values():
        text = json.dumps(x, ensure_ascii=False)
        assert "وصل نیست" not in text and "connection.guide" not in text and "media.on" not in text
    # a row without accounts: still «through IG-Hub», no fix; with accounts: the count
    await su.execute(
        """INSERT INTO growth.connections (company_id, kind, label_fa, config, origin)
           VALUES ($1, 'instagram', 'اینستاگرام', '{"via": "ig_hub", "accounts": []}'::jsonb, 'seed')""",
        co["id"],
    )
    async with holding_switch(su, "engaged"):
        c = checks(await client.get(f"/api/v1/companies/{co['code']}/readiness", headers=owner,
                                    params={"group": "content"}))  # fmt: skip
    assert c["connection:instagram"]["ok"] is True and c["connection:instagram"]["fix"] is None
    assert c["connection:instagram"]["detail_fa"].startswith("اینستاگرام از راه IG-Hub")
    await su.execute(
        """UPDATE growth.connections SET config = '{"via": "ig_hub", "accounts": ["@a", "@b"],
               "command": "cat /srv/ig/d.json"}'::jsonb WHERE company_id = $1 AND kind = 'instagram'""",
        co["id"],
    )
    async with holding_switch(su, "engaged"):
        c = checks(await client.get(f"/api/v1/companies/{co['code']}/readiness", headers=owner,
                                    params={"group": "content"}))  # fmt: skip
    assert c["connection:instagram"]["detail_fa"] == "از راه IG-Hub خوانده و منتشر میشود (2 حساب)."


# ================================================================ 3. no video tool ==
async def test_media_tool_refusals_are_never_blockers_and_the_brief_names_the_video_package(
    hub: Hub,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    made = await make_order(hub, company, WORK_TEXT.format(co=co, w=words()))
    ref, w = made["ref"], made["work"]
    await refuse_queued(su, w["ref"])
    for tool in ("media.render", "media.item", "speech.make", "media.on"):
        await done_run(su, w["id"], f"off:{tool}",
                       [{"tool": tool, "outcome": "refused", "code": "channel_not_configured"}])  # fmt: skip
    rep = await report(client, owner, ref)
    assert rep["blockers"] == [], rep["blockers"]
    text = json.dumps(rep, ensure_ascii=False)
    assert "ابزار ویدیو" not in text and "AI Studio" not in text and "media.on" not in text
    # the brief: no voice block, no voice how; the video package; Instagram through IG-Hub
    async with await all_tx(hub) as tx:
        brief = await CAP.brief(tx, company["id"], n8n_up=False)
    assert "voice" not in brief and "voice" not in brief["how"]
    assert "بسته‌ی ساخت ویدیو" in brief["how"]["video"]
    for word in ("script", "shot list", "on-screen text", "voice text", "caption", "hashtags",
                 "cover prompt", "IG-Hub"):  # fmt: skip
        assert word in brief["how"]["video"], word
    assert "kind: video" not in brief["how"]["cover_image"]
    assert (
        "IG-Hub" in brief["how"]["instagram"]
        and "never the owner's step" in brief["how"]["instagram"]
    )
    # ⟨2026-11-09⟩ §43 a video made without a camera goes to the workshop, which is in the brief
    assert "workshop.run" in brief["how"]["video"] and "workshop.run" in brief["how"]["workshop"]
    assert brief["workshop"]["state"] in ("ready", "not set up yet")
    # the holder's plan instruction says when a video task is done
    assert "بسته‌ی ساخت ویدیو" in OT.PLAN_INSTRUCTION and "IG-Hub" in OT.PLAN_INSTRUCTION
    assert "workshop.run" in OT.PLAN_INSTRUCTION


def test_the_media_charters_and_the_common_rules_carry_the_three_decisions() -> None:
    lib = CHL.load()
    for role in ("media_director", "scriptwriter", "video_director", "motion_designer"):
        c = lib.get(role)
        assert c is not None
        # ⟨2026-11-10⟩ the owner's own voice talk is what is off; the narrator of content is wanted
        assert "speech.make" in c.tools, role
        assert "IG-Hub" in c.body, role
        assert "بسته‌ی ساخت ویدیو" in c.body, role
        # ⟨2026-11-09⟩ §43 a video made without a camera is the workshop's
        assert "workshop.run" in c.body and "workshop.run" in c.tools, role
    assert "Instagram, for all companies, is read and published through IG-Hub" in lib.common
    assert "بسته‌ی ساخت ویدیو" in lib.common and "The workshop is your hands" in lib.common
    assert "workshop.run" in lib.common and "No video tool" not in lib.common
    assert lib.common_version >= 13 and "narrator" in lib.common.lower()
    assert lib.problems == []
