"""⟨2026-11-13⟩ Rules on a post that is out: the smart comment and the story's DM reply.

The owner (F-0018): «چرا دستور منو اجرا نمیکنه تنظیم دایرکت هوشمند برای کامنت پست و دایرکت
استوری», then: from inside the app, for every company (all paths are open to all). A rule on a publication that is out is one `publish` job with meta `rule`
and no file (IG-Hub's `POST /api/v1/rules`); a story that goes out takes its reel's comment
rule for the account's story replies by itself; a word is taken in its joined forms too
(«باز پخش», «بازپخش»).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from hq_api.domain import session_publish as SPB
from hq_api.hub import Hub

from .conftest import idem
from .test_p17_runners import take
from .test_p21_secretary import no_model  # noqa: F401 - the fixture
from .test_w17_session_publish import an_output, tap
from .test_w19_publish_time import answer, connected

REEL_ID, STORY_ID = "17866260483693371", "18127217014697683"
RULE = {"keywords": ["باز پخش"], "reply": "لینک سایت", "link": "https://pro-chart.com/chart",
        "button": "نمودار"}  # fmt: skip


def test_a_word_is_taken_in_its_joined_forms() -> None:
    assert SPB.word_forms(["باز پخش"]) == ["باز پخش", "بازپخش"]
    assert SPB.word_forms(["باز‌پخش", "۷"]) == ["باز‌پخش", "بازپخش", "۷"]
    assert len(SPB.word_forms([f"و {i}" for i in range(9)])) == 10
    body = SPB.rule_body("comment", {**RULE, "public_replies": ["دایرکت را ببین"]}, "@pro.chart",
                         [REEL_ID, "pub:7"], "k")  # fmt: skip
    assert body["account"] == "pro.chart" and body["trigger"] == "comment"
    assert body["keywords"] == ["باز پخش", "بازپخش"] and body["match"] == "contains"
    assert body["post_ids"] == [REEL_ID]  # an id IG-Hub still holds is no post
    assert body["buttons"] == [{"title": "نمودار", "url": "https://pro-chart.com/chart"}]
    assert body["public_replies"] == ["دایرکت را ببین"] and body["reply_text"] == "لینک سایت"
    assert "buttons" not in SPB.rule_body(
        "story_reply", {"keywords": ["x"], "reply": "y"}, "a", [], "k"
    )


async def rules(
    client: httpx.AsyncClient, owner: dict[str, str], job: str, body: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        f"/api/v1/publishes/{job}/rules", headers={**owner, **idem()}, json=body
    )


async def test_the_owner_sets_a_rule_on_a_reel_that_is_out_and_its_story_takes_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    ig, pc = await new_company(), await new_company()
    made = await an_output(client, hub, owner, owner_session, su, pc["code"],
                           ("reel.mp4", "cover.png", "story.png"))  # fmt: skip
    order, output, (reel, cover, story) = made["order"], made["output"], made["files"]
    rn = await connected(client, hub, owner_session, ig, pc["code"])

    # 1. the reel goes out with its comment rule: the word in both its forms
    r = await tap(client, owner, order, {"output": output, "file_id": reel,
                                         "cover_file_id": cover, "comment": RULE})  # fmt: skip
    assert r.status_code == 202, r.text
    pub = r.json()["job"]
    job = await take(client, rn)
    assert job["args"]["meta"]["comment"]["keywords"] == ["باز پخش", "بازپخش"]
    # not out yet: no rule on it
    r = await rules(client, owner, pub, {"trigger": "comment", **RULE})
    assert r.status_code == 409 and "بعد از انتشار" in r.json()["message_fa"], r.text
    await answer(client, rn, job["id"], {"external_id": REEL_ID,
                                         "url": "https://www.instagram.com/reel/x/"})  # fmt: skip

    # 2. the owner's rule on the reel that is out: one job, no file, for this post alone
    r = await rules(client, owner, pub, {"trigger": "comment", "keywords": ["سطح"], "reply": "hi"})
    assert r.status_code == 200, r.text
    assert r.json()["trigger"] == "comment" and r.json()["keywords"] == ["سطح"]
    rule_job = await take(client, rn)
    assert rule_job["id"] == r.json()["job"] and rule_job["kind"] == "publish"
    a = rule_job["args"]
    assert a["files"] == [] and a["caption"] == "" and "session" not in a
    assert a["command"] == job["args"]["command"] and a["rule_for"]["order"] == order
    rule = a["meta"]["rule"]
    assert a["meta"]["kind"] == "rule" and rule["trigger"] == "comment"
    assert rule["post_ids"] == [REEL_ID] and rule["account"] == "pro.chart"
    assert rule["key"] == a["meta"]["key"]
    await answer(client, rn, rule_job["id"], {"external_id": "rule:41", "url": None})
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    said = [s["what_fa"] for s in rep["steps"]]
    assert any(x.startswith("کامنت هوشمند برای @pro.chart به IG-Hub رفت") for x in said), said
    assert any(x.startswith("کامنت هوشمند روشن شد: «سطح»") for x in said), said
    # a rule's job is no publication of its own
    assert [p["job"] for p in rep["publishes"]] == [pub]

    # 3. a word without its reply is no rule
    r = await rules(client, owner, pub, {"trigger": "comment", "keywords": ["x"], "reply": ""})
    assert r.status_code == 422, r.text

    # 4. the story goes out: the reel's comment rule is made for the story replies by itself
    r = await tap(client, owner, order, {"output": output, "file_id": story, "kind": "story"})
    assert r.status_code == 202, r.text
    sj = await take(client, rn)
    assert "comment" not in sj["args"]["meta"]
    await answer(client, rn, sj["id"], {"external_id": STORY_ID, "url": None})
    auto = await take(client, rn)
    rule = auto["args"]["meta"]["rule"]
    assert rule["trigger"] == "story_reply" and rule["post_ids"] == []
    assert rule["keywords"] == ["باز پخش", "بازپخش"] and rule["reply_text"] == "لینک سایت"
    assert rule["buttons"] == [{"title": "نمودار", "url": "https://pro-chart.com/chart"}]
    # IG-Hub refused it: said plainly
    await answer(client, rn, auto["id"], None, exit_code=1, why="حساب در دسترس کلید نیست.")
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    said = [s["what_fa"] for s in rep["steps"]]
    assert any(x.startswith("جواب دایرکت استوری در @pro.chart ساخته نشد") for x in said), said
    acts = await su.fetch(
        "SELECT action FROM audit.entries WHERE target_ref = $1 AND action = 'publish.rule' "
        "AND company_id = $2::uuid",
        order,
        pc["id"],
    )
    assert len(acts) == 2
