"""Prompt 38 (contract §59.5, §59.6): a company's links (UTM by code), a flow's reply policy and its
preview, and the three rules a flow's publication makes when it is out.

The owner, 2026-11-13 (IG-Hub 1806b86, `rules.public_turn`): the public replies go out in turn, so
the pool's order is the order they are sent in. It is checked here from the policy through the
package's `comment.txt` to the rule body IG-Hub gets."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import uuid4

import httpx
import pytest

from hq_api.domain import flow_shapes as FS
from hq_api.domain import session_publish as SPB
from hq_api.domain import site_links as SL
from hq_api.errors import ApiError
from hq_api.hub import Hub

from .test_p17_runners import take
from .test_p21_secretary import no_model  # noqa: F401 - the fixture
from .test_w19_publish_time import answer, connected

REEL_ID, STORY_ID = "17866260483693371", "18127217014697683"
DAY = date(2026, 11, 14)
OWN = [f"جواب {i} از مالک 🌱" for i in range(1, 13)]  # twelve, in the owner's order
LINKS = FS.SiteLinks(
    company="PC",
    site=FS.SiteUrl(url="https://pro-chart.com"),
    sections=[FS.SiteSection(key="next", url="https://pro-chart.com/next/?ref=ig&utm_source=bio")],
)


# ------------------------------------------------------------------ units --
def test_a_reply_link_carries_its_paths_utm_built_by_code() -> None:
    url = SL.link_for(LINKS, None, "comment", "at_0042", DAY)
    assert url == (
        "https://pro-chart.com?utm_source=instagram&utm_medium=comment&utm_campaign=at_0042"
        "&utm_content=20261114"
    )
    sec = SL.link_for(LINKS, "next", "dm", "at_0042", "2026-11-14")
    # the parameters already on the url are kept (its own utm_source too)
    assert sec.startswith("https://pro-chart.com/next/?ref=ig&utm_source=bio&utm_medium=dm")
    assert "utm_source=instagram" not in sec and "utm_content=20261114" in sec
    assert SL.link_for(LINKS, "nope", "story", "f", DAY).startswith("https://pro-chart.com?")
    assert SL.link_for(None, None, "dm", "f", DAY) == ""
    custom = LINKS.model_copy(update={"utm": FS.SiteUtm(campaign="reels_{flow}")})
    assert "utm_campaign=reels_at_0042" in SL.link_for(custom, None, "story", "at_0042", DAY)
    assert SL.flow_name("AT-0042") == "at_0042"


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"dm_template": {"text_fa": "x" * 641}}, "dm_template.text_fa"),
        ({"dm_template": {"buttons": [{"title_fa": "a"}] * 4}}, "dm_template.buttons"),
        ({"dm_template": {"buttons": [{"title_fa": "x" * 21}]}}, "dm_template.buttons[0].title_fa"),
        ({"dm_template": {"buttons": [{"title_fa": "a", "section": "shop"}]}},
         "dm_template.buttons[0].section"),
        ({"section": "shop"}, "section"),
        ({"public_pool": ["x"] * 31}, "public_pool"),
        ({"public_pool": ["ok", "x" * 301]}, "public_pool[1]"),
    ],
)  # fmt: skip
def test_a_policy_out_of_bounds_is_refused_by_field(change: dict[str, Any], field: str) -> None:
    with pytest.raises(ApiError) as e:
        SL.check_policy(FS.ReplyPolicy.model_validate(change), LINKS)
    assert e.value.status == 422 and field in (e.value.fields or {})
    SL.check_policy(FS.ReplyPolicy(public_pool=["one"], section="next"), LINKS)  # fewer is fine


def test_the_pool_keeps_its_order_from_the_policy_to_igHubs_rule_body() -> None:
    policy = SL.lenient(FS.ReplyPolicy(public_pool=OWN[:3]))
    # fewer than ten: the hub's pool fills them, the policy's own first, order kept
    assert policy.public_pool[:3] == OWN[:3] and len(policy.public_pool) == 10
    assert policy.public_pool[3:] == list(SPB.PUBLIC_POOL[:7])
    public = SL.fill_pool(OWN)  # twelve of his own: all of them, in his order
    assert public == OWN
    rules = SL.flow_rules(
        FS.ReplyPolicy(public_pool=OWN), LINKS, flow="at_0042", day=DAY, keyword="بازپخش",
        match_any=True, dm_text="سلام", public=public, story=True,
    )  # fmt: skip
    text = SL.comment_txt(rules["comment"], "سلام", public)
    parsed = SPB.parse_comment(text)
    assert parsed is not None and parsed["public_replies"] == OWN and parsed["match"] == "any"
    body = SPB.rule_body("comment", rules["comment"], "@pro.chart", [REEL_ID], "k")
    assert body["public_replies"] == OWN and body["cooldown_days"] == 365
    assert body["match"] == "any" and body["post_ids"] == [REEL_ID]
    dm = SPB.rule_body("dm", rules["dm"], "pro.chart", [], "k2")
    assert dm["trigger"] == "dm" and dm["post_ids"] == [] and dm["public_replies"] == []
    assert dm["match"] == "contains" and dm["keywords"] == ["بازپخش"]
    assert "utm_medium=dm" in dm["buttons"][0]["url"]
    story = SPB.rule_body("story_reply", rules["story_reply"], "pro.chart", [], "k3")
    assert "utm_medium=story" in story["buttons"][0]["url"]
    every = FS.ReplyPolicy(repeat=FS.RepeatPolicy(mode="after_days", days=30), dm=False)
    got = SL.flow_rules(every, LINKS, flow="f", day=DAY, keyword=None, match_any=True,
                        dm_text="x", public=public, story=True)  # fmt: skip
    # no word: only the comment rule, for every comment; the story and the DM answer a word only
    assert set(got) == {"comment"} and got["comment"]["cooldown_days"] == 30
    # a session's rule is as before: ten at most
    assert len(SPB.rule_body("comment", {"keywords": ["x"], "reply": "y", "public_replies": OWN},
                             "a", [], "k")["public_replies"]) == 10  # fmt: skip


# --------------------------------------------------------------- the links --
async def test_the_owner_sets_the_companys_links(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    url = f"/api/v1/companies/{co['code']}/site-links"
    r = await client.get(url, headers=owner)
    assert r.status_code == 200 and r.json()["site"]["url"] == "", r.text
    bad = {"site": {"url": "http://x.example"},
           "sections": [{"key": "a", "url": "https://x.example/a"}, {"key": "b", "url": "ftp://x"}]}  # fmt: skip
    r = await client.put(url, headers=owner, json=bad)
    assert r.status_code == 422, r.text
    assert {"site.url", "sections[1].url"} <= set(r.json()["fields"])
    r = await client.put(url, headers=owner, json={"site": {"url": "https://x.example"},
                                                   "sections": [{"key": "Bad Key", "url": "https://x.example"}]})  # fmt: skip
    assert r.status_code == 422, r.text
    r = await client.put(url, headers=owner, json={"sections": [{"key": f"s{i}", "url": "https://x.example"}
                                                                for i in range(31)],
                                                   "site": {"url": "https://x.example"}})  # fmt: skip
    assert r.status_code == 422, r.text
    good = {"site": {"url": "https://x.example", "title_fa": "سایت"},
            "sections": [{"key": "next", "title_fa": "بعدی", "url": "https://x.example/next/"}]}  # fmt: skip
    r = await client.put(url, headers=owner, json=good)
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["company"] == co["code"] and got["sections"][0]["key"] == "next"
    assert got["utm"]["medium"] == {"comment": "comment", "story": "story", "dm": "dm"}
    assert (await client.get(url, headers=owner)).json()["site"]["url"] == "https://x.example"
    n = await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'company.site_links' AND target_ref = $1",
        co["code"],
    )
    assert n == 1


# -------------------------------------------------------------- the policy --
async def a_flow(su: Any, company_id: Any, replies: dict[str, Any] | None = None) -> str:
    ref: str = await su.fetchval(
        """INSERT INTO growth.automations (company_id, scope, sentence_fa, rule, state, sealed_at,
               kind, playbook, playbook_version, line, schedule, replies, account, story)
           VALUES ($1::uuid, 'company', 'ریلز روزانه', '{}'::jsonb, 'on', now(), 'flow',
                   'PB-9001', 1, 'LN-9001', '{"mode": "best"}'::jsonb, $2::jsonb, 'pro.chart', true)
           RETURNING ref""",
        company_id,
        json.dumps(replies) if replies is not None else None,
    )
    return ref


async def test_a_flows_replies_are_set_and_previewed_in_the_order_they_go_out(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    r = await client.put(
        f"/api/v1/companies/{co['code']}/site-links", headers=owner,
        json={"site": {"url": "https://x.example"},
              "sections": [{"key": "next", "url": "https://x.example/next/"}]},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    ref = await a_flow(su, co["id"])
    url = f"/api/v1/automations/{ref}/replies"
    policy = {"comment": {"match": "word"}, "story": True, "dm": False,
              "public_pool": OWN[:3],
              "dm_template": {"text_fa": "سلام! درباره‌ی «{topic}» 👇",
                              "buttons": [{"title_fa": "بعدی", "section": "next"}]},
              "per_video_dm": True, "repeat": {"mode": "after_days", "days": 30}}  # fmt: skip
    r = await client.put(url, headers=owner, json={**policy, "section": "shop"})
    assert r.status_code == 422 and "section" in r.json()["fields"], r.text
    r = await client.put(url, headers=owner, json=policy)
    assert r.status_code == 200, r.text
    flow = r.json()
    assert flow["ref"] == ref and flow["kind"] == "flow"
    assert (
        flow["replies"]["public_pool"][:3] == OWN[:3] and len(flow["replies"]["public_pool"]) == 10
    )
    stored = json.loads(
        await su.fetchval("SELECT replies FROM growth.automations WHERE ref = $1", ref)
    )
    assert stored["public_pool"] == OWN[:3]  # as he gave it; the hub's pool fills it on reading
    assert await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'automation.replies' AND target_ref = $1",
        ref,
    ) == 1  # fmt: skip

    r = await client.post(f"{url}/preview", headers=owner, json={"topic_fa": "کندل چکش"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["dm"]["text"] == "سلام! درباره‌ی «کندل چکش» 👇"
    [button] = p["dm"]["buttons"]
    assert button["title"] == "بعدی" and button["url"].startswith("https://x.example/next/?utm_")
    assert f"utm_campaign={SL.flow_name(ref)}" in button["url"]
    # every reply, in the order they go out: the first commenter gets the first
    assert p["public"] == flow["replies"]["public_pool"]
    assert "۳۰ روز" in p["comment_fa"] and p["dm_fa"] == "جواب دایرکت خاموش است."
    assert (await client.post(f"{url}/preview", headers=owner, json={})).json()["dm"]["text"] == (
        "سلام! درباره‌ی «این ویدیو» 👇"
    )
    r = await client.put("/api/v1/automations/AT-999999/replies", headers=owner, json=policy)
    assert r.status_code == 404, r.text


# ---------------------------------------------- the three rules, once each --
async def test_a_flows_publication_makes_its_three_rules_each_once_and_tells_a_refusal(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    ig, pc = await new_company(), await new_company()
    rn = await connected(client, hub, owner_session, ig, pc["code"])
    line = await su.fetchrow(
        """INSERT INTO lines.lines (company_id, template, template_version, platform, title_fa,
               caps, steps)
           VALUES ($1::uuid, 'flow_test', 1, 'instagram_reel', 'ریلز روزانه', '{}', '[]')
           RETURNING id, ref""",
        pc["id"],
    )
    run = await su.fetchval(
        """INSERT INTO lines.runs (company_id, line_id, line_version, trigger, state)
           VALUES ($1::uuid, $2, 1, 'n8n', 'running') RETURNING ref""",
        pc["id"],
        line["id"],
    )
    public = SL.fill_pool(OWN)
    rules = SL.flow_rules(
        FS.ReplyPolicy(public_pool=OWN), LINKS, flow="at_0042", day=DAY, keyword="بازپخش",
        match_any=True, dm_text="سلام 👋", public=public, story=True,
    )  # fmt: skip
    flow = {"run": run, "step": "publish", "automation": "AT-0042", "platform": "instagram_reel",
            "rules": rules}  # fmt: skip
    d = {"ref": run, "company_id": pc["id"], "company": pc["code"], "work_ref": None, "title": "t"}

    async def send(what: SPB.Kind) -> None:
        f = {"id": str(uuid4()), "name": f"{what}.mp4", "mime": "video/mp4"}
        async with hub.db.tx(await hub.companies.ids()) as tx:
            route = await SPB._route(tx, pc["id"])
            await SPB._send(tx, SPB.SERVICE, d, f, None, hub=hub, what=what, account="pro.chart",
                            caption="کپشن" if what == "reel" else "", route=route, order=None,
                            flow=flow)  # fmt: skip

    await send("reel")
    reel = await take(client, rn)
    assert reel["args"]["flow"]["run"] == run and "comment" not in reel["args"]["meta"]
    await answer(client, rn, reel["id"], {"external_id": REEL_ID,
                                          "url": "https://www.instagram.com/reel/x/"})  # fmt: skip
    made = [await take(client, rn), await take(client, rn)]  # one transaction: either order
    by = {j["args"]["meta"]["rule"]["trigger"]: j for j in made}
    comment, dm = by["comment"], by["dm"]
    c = comment["args"]["meta"]["rule"]
    assert c["trigger"] == "comment" and c["post_ids"] == [REEL_ID] and c["match"] == "any"
    assert c["public_replies"] == OWN  # the policy's order, as it goes out
    assert c["cooldown_days"] == 365 and "utm_medium=comment" in c["buttons"][0]["url"]
    assert comment["args"]["rule_for"]["run"] == run
    m = dm["args"]["meta"]["rule"]
    assert m["trigger"] == "dm" and m["post_ids"] == [] and m["keywords"] == ["بازپخش"]
    assert "utm_medium=dm" in m["buttons"][0]["url"]

    # IG-Hub (before IGHUB_04) refuses thirty replies and `cooldown_days`: tried once more as it
    # took rules before, then told once in the run
    await answer(client, rn, comment["id"], None, exit_code=1, why="قاعده پذیرفته نشد.")
    again = await take(client, rn)
    a = again["args"]["meta"]
    assert a["compat"] is True and "cooldown_days" not in a["rule"]
    assert a["rule"]["public_replies"] == OWN[:10] and a["key"] == comment["args"]["meta"]["key"]
    await answer(client, rn, again["id"], None, exit_code=1, why="قاعده پذیرفته نشد.")
    note = await su.fetchval("SELECT note_fa FROM lines.runs WHERE ref = $1", run)
    assert note is not None and note.count("کامنت هوشمند در @pro.chart ساخته نشد") == 1
    await answer(client, rn, dm["id"], {"external_id": "rule:7", "url": None})

    # the story goes out: its own rule with its own UTM, and no second comment rule
    await send("story")
    story = await take(client, rn)
    await answer(client, rn, story["id"], {"external_id": STORY_ID, "url": None})
    sr = await take(client, rn)
    s = sr["args"]["meta"]["rule"]
    assert s["trigger"] == "story_reply" and "utm_medium=story" in s["buttons"][0]["url"]
    counts = {
        r["t"]: r["n"]
        for r in await su.fetch(
            "SELECT args -> 'rule_for' ->> 'trigger' AS t, count(*) AS n FROM infra.server_jobs"
            " WHERE args -> 'rule_for' ->> 'run' = $1 GROUP BY 1",
            run,
        )
    }
    assert counts == {"comment": 2, "dm": 1, "story_reply": 1}
