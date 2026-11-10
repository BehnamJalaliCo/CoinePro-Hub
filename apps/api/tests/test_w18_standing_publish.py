"""⟨2026-11-10⟩ The owner's standing permission to publish (contract §45).

The owner: «به صورت خودکار از روز دوم انجام بشه و به اتوماسیون تبدیل بشه نه اینکه هر بار من تایید
کنم. 100 تا کارگروه راه بندازم اونوقت باید روزی صد بار تایید بدم. پس جوری آپ رو باید طراحی بکنید که
همه جور بشه باهاش کار کرد.» His word is given once for a company in a working group: from the next
run the hub publishes each routine's package (the video, its cover, `caption.txt`) by itself,
through the same job as his tap. Without that word each output still waits for his tap, now also
outside a session. Sealing a working group is his tap, no passkey.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.domain import groups as GR
from hq_api.domain import playbooks as PB
from hq_api.domain import session_publish as SPB
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .p10_fakes import holding_switch
from .test_p13a_media import mp4
from .test_p17_runners import pair, poll, take
from .test_p21_groups import TEHRAN, at
from .test_p21_routing_orders import auto_hiring, envelope  # noqa: F401 - the fixture
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_p22_ops import route_answer
from .test_p23_talk import talk  # noqa: F401 - the fixture
from .test_w10_playbooks import REEL_TEXT, a_draft, hire, join, model
from .test_w11_connections import set_connection
from .test_w14_workshop import refuse_queued, run_ask, send_file, workshop
from .test_w17_session_publish import a_png

COMMAND = "/srv/ig/bin/hq-publish"
CAPTION = "سه سطح مهم طلا در این هفته\n#طلا #پروچارت"


async def a_group(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    seal: dict[str, Any] | None,
) -> dict[str, Any]:
    """A session of a company became a working group (one daily routine on the scriptwriter's
    seat), sealed with `seal` as its body; the company's Instagram goes out through IG-Hub."""
    owner = owner_session["headers"]
    ig, company = await new_company(), await new_company()
    co = company["code"]
    await envelope(su, company)
    out = await post_order(client, owner, REEL_TEXT.format(co=co, w=words()))
    writer = await hire(hub, company, "scriptwriter")
    await join(client, owner, out["ref"], f"scriptwriter@{co}")
    route_answer(monkeypatch, model(a_draft(co)))
    r = await client.post(f"/api/v1/orders/{out['ref']}/playbook", headers={**owner, **idem()})
    assert r.status_code == 201, r.text
    pref = r.json()["ref"]
    # the seal is the owner's tap: his bearer, no step-up assertion
    r = await client.post(f"/api/v1/playbooks/{pref}/seal", headers=owner, json=seal)
    assert r.status_code == 200, r.text
    r = await set_connection(
        client,
        f"{ig['code']}-TECH-MGR",
        {"company": co, "kind": "instagram", "accounts": ["@pro.chart"], "via": "ig_hub",
         "server": {"company": ig["code"], "name": "IG-Hub"},
         "read_command": "cat /srv/ig/daily.json", "publish_command": COMMAND},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    return {
        "company": company, "co": co, "ig": ig, "writer": writer, "playbook": r and pref,
        "key": PB.group_key(pref), "sealed": (await client.get(
            f"/api/v1/playbooks/{pref}", headers=owner)).json(),
        "ig_rn": await pair(client, hub, owner_session, ig, "IG-Hub"),
        "rn": await workshop(client, hub, owner_session, su),
    }  # fmt: skip


def caption_of(day: date) -> str:
    """Each day says something of its own (⟨§47⟩ the hub never sends one topic twice)."""
    return f"سه سطح مهم طلا، روز {day.day}\n#طلا #پروچارت"


async def a_day(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    g: dict[str, Any],
    day: date,
    files: tuple[str, ...],
    deliver: bool = True,
    texts: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The routine's run of `day`: its work, a workshop turn that leaves `files` in `out/`
    (one output of the work), and the work delivered by its holder. `texts`: what a `.txt`
    file says (the caption otherwise)."""
    async with holding_switch(su, "released"):
        ticked = await GR.tick(hub, now=at(day, 8, 0), only={g["company"]["id"]})
    assert ticked["queued"] >= 1, ticked  # its own routine (and the file groups' of that hour)
    run = await su.fetchrow(
        """SELECT x.id, w.id AS work_id, w.ref, w.brief FROM growth.routine_runs x
           JOIN growth.groups gr ON gr.id = x.group_id JOIN work.work w ON w.id = x.work_id
           WHERE gr.key = $1 ORDER BY x.occurrence_at DESC LIMIT 1""",
        g["key"],
    )
    r = await run_ask(client, g["writer"], {"work": run["ref"], "brief": "ریلز امروز را بساز"})
    assert r.status_code == 201, r.text
    job = await take(client, g["rn"])
    ids = []
    for i, name in enumerate(files):
        if name.endswith(".mp4"):
            r = await send_file(client, g["rn"], job["id"], name, "video/mp4", mp4(2))
        elif name.endswith(".txt"):
            said = (texts or {}).get(name, caption_of(day))
            r = await send_file(
                client, g["rn"], job["id"], name, "text/plain", f"\ufeff{said}\n".encode()
            )
        else:
            r = await send_file(client, g["rn"], job["id"], name, "image/png", a_png(i + day.day))
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    await refuse_queued(su, str(run["work_id"]))
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "تمام شد.",
              "data": {"session_id": f"cs-{day.day}", "result_fa": "ساخته شد.", "files": ids}},
        headers=g["rn"]["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
    output = await su.fetchval(
        "SELECT ref FROM cartable.deliverables WHERE work_id = $1 ORDER BY created_at DESC LIMIT 1",
        run["work_id"],
    )
    assert output is not None
    if deliver:
        await refuse_queued(su, str(run["work_id"]))
        r = await client.post(
            f"/internal/v1/work/{run['work_id']}/deliver",
            headers={**await agent_headers(g["writer"]), **idem()},
            json={"title": "ریلز امروز آماده است", "body": "بسته در خروجی کارگاه است."},
        )
        assert r.status_code == 200, r.text
        assert r.json()["work"]["status"] == "delivered", r.json()["work"]
    return {"run": run["id"], "work_id": run["work_id"], "work": run["ref"], "brief": run["brief"],
            "output": output, "files": dict(zip(files, ids, strict=True))}  # fmt: skip


async def jobs_of(su: Any, run: Any) -> list[Any]:
    return list(
        await su.fetch(
            """SELECT id, state, args FROM infra.server_jobs
               WHERE kind = 'publish' AND args -> 'standing' ->> 'run' = $1 ORDER BY created_at""",
            str(run),
        )
    )


def args_of(job: Any) -> dict[str, Any]:
    raw = job["args"]
    return dict(raw) if isinstance(raw, dict) else dict(json.loads(raw))


def test_the_word_is_read_as_ask_unless_the_owner_said_auto() -> None:
    assert SPB.rule_of(None)["mode"] == "ask" and SPB.brief_block(None) == ""
    assert SPB.rule_of({"mode": "anything"})["mode"] == "ask"
    rule = SPB.rule_of('{"mode": "auto", "account": "@pro.chart", "story": true}')
    assert (rule["mode"], rule["account"], rule["story"]) == ("auto", "pro.chart", True)
    told = SPB.brief_block({"mode": "auto", "account": "pro.chart", "story": True})
    assert "standing permission" in told and "@pro.chart and as a story" in told
    assert "caption.txt" in told and "never ask the owner" in told
    assert GR.member_publish({"mode": "auto", "account": "a"}).mode == "auto"
    assert GR.member_publish(None).mode == "ask"


async def test_a_working_groups_daily_reel_goes_out_on_the_owners_standing_word(
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
    # the owner seals the working group and says once: publish by yourself, as a story too
    g = await a_group(client, hub, owner_session, su, new_company, monkeypatch,
                      {"publish": {"mode": "auto", "story": True}})  # fmt: skip
    co, key = g["co"], g["key"]
    [member] = g["sealed"]["members"]
    assert member["publish"]["mode"] == "auto" and member["publish"]["story"] is True
    assert member["publish"]["since"]
    row = await su.fetchrow(
        "SELECT action_class, actor_kind, step_up FROM audit.entries "
        "WHERE action = 'group.publish' AND target_ref = $1",
        f"{key}:{co}",
    )
    assert (row["action_class"], row["actor_kind"], row["step_up"]) == ("A3", "owner", False)
    # the account is one of the company's own
    r = await client.put(f"/api/v1/groups/{key}/members/{co}/publish", headers=owner,
                         json={"mode": "auto", "account": "@someone.else"})  # fmt: skip
    assert r.status_code == 422 and "pro.chart" in r.json()["fields"]["account"], r.text
    r = await client.put(f"/api/v1/groups/{key}/members/{co}/publish", headers=owner,
                         json={"mode": "auto", "account": "@pro.chart", "story": True})  # fmt: skip
    assert r.status_code == 200 and r.json()["publish"]["account"] == "pro.chart", r.text

    # day two: the routine runs by itself, its work is told how its package goes out
    day = datetime.now(TEHRAN).date() + timedelta(days=1)
    cards = await su.fetchval("SELECT count(*) FROM cartable.decisions WHERE status = 'pending'")
    made = await a_day(client, hub, su, g, day, ("reel.mp4", "cover.png", "caption.txt"))
    assert "standing permission" in made["brief"] and "caption.txt" in made["brief"]
    assert "to @pro.chart and as a story" in made["brief"]

    # delivered: the hub sends the package itself, on his word. No card, no tap, no passkey.
    # (both jobs are made in one transaction: told apart by their kind, never by their order)
    jobs = {args_of(j)["kind"]: j for j in await jobs_of(su, made["run"])}
    reel, story = jobs["reel"], jobs["story"]
    assert cards == await su.fetchval(
        "SELECT count(*) FROM cartable.decisions WHERE status = 'pending'"
    )
    taken = {j["id"]: j for j in (await take(client, g["ig_rn"]), await take(client, g["ig_rn"]))}
    job = taken[str(reel["id"])]
    assert job["kind"] == "publish"
    a = job["args"]
    assert a["command"] == COMMAND and a["caption"] == caption_of(day) and a["kind"] == "reel"
    assert a["meta"] == {"channel": "instagram", "kind": "reel", "account": "pro.chart",
                         "company": co, "cover": True, "key": a["meta"]["key"]}  # fmt: skip
    assert len(a["meta"]["key"]) == 32  # ⟨1.31⟩ the publication's own key, the same on a retry
    assert a["standing"]["group"] == key and a["standing"]["routine"] == "daily_topic"
    assert a["session"]["order"] is None and a["session"]["output"] == made["output"]
    video, cover = a["files"]
    # ⟨§52⟩ the cover goes out as a JPEG the hub made from the PNG
    assert video["name"] == "reel.mp4" and cover["name"] == "cover.jpg" and cover["role"] == "cover"
    assert cover["mime"] == "image/jpeg"
    got = await client.get(video["url"], headers=g["ig_rn"]["h"])
    assert got.status_code == 200 and len(got.content) > 100
    s_args = args_of(story)
    assert s_args["kind"] == "story" and s_args["caption"] == "" and len(s_args["files"]) == 1
    audits = await su.fetch(
        "SELECT actor_kind, actor_code, action_class, summary FROM audit.entries "
        "WHERE action = 'publish.standing' AND company_id = $1",
        g["company"]["id"],
    )
    assert len(audits) == 2 and {x["action_class"] for x in audits} == {"A3"}
    assert all("standing permission" in x["summary"] for x in audits)
    note = await su.fetchval("SELECT note_fa FROM growth.routine_runs WHERE id = $1", made["run"])
    assert "انتشار خودکار" in note and "@pro.chart" in note

    # sent once: the next ticks and a second look at the same work make nothing
    async with holding_switch(su, "released"):
        again = await GR.tick(hub, now=at(day, 8, 10), only={g["company"]["id"]})
    assert again["published"] == 0 and len(await jobs_of(su, made["run"])) == 2
    assert await SPB.after_delivered(hub, made["work_id"]) == "sent"

    # Instagram answers: the run says so and the output's page shows it, marked automatic
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "منتشر شد.",
              "data": {"external_id": "1789", "url": "https://www.instagram.com/reel/Cx1/"}},
        headers=g["ig_rn"]["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
    note = await su.fetchval("SELECT note_fa FROM growth.routine_runs WHERE id = $1", made["run"])
    assert (
        note.startswith("خودکار منتشر شد: ریلز در @pro.chart") and "instagram.com/reel/Cx1" in note
    )
    r = await client.get(f"/api/v1/deliverables/{made['output']}/publish", headers=owner)
    assert r.status_code == 200, r.text
    panel = r.json()
    assert panel["tap"] is True and panel["order"] is None
    assert panel["caption"] == caption_of(day)
    assert panel["group"] == key and panel["mode"] == "auto" and panel["ready"] is True
    by_kind = {p["kind"]: p for p in panel["publishes"]}
    assert by_kind["reel"]["state"] == "published" and by_kind["reel"]["auto"] is True
    assert by_kind["reel"]["cover_name"] == "cover.png"
    assert by_kind["reel"]["url"] == "https://www.instagram.com/reel/Cx1/"
    assert by_kind["story"]["state"] == "publishing" and by_kind["story"]["auto"] is True
    assert await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'publish.standing_done' AND company_id = $1",
        g["company"]["id"],
    ) == 1  # fmt: skip

    # the story refused by Instagram: said to the owner once, with the output
    job = taken[str(story["id"])]
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 1, "summary_fa": "اینستاگرام نپذیرفت."},
        headers=g["ig_rn"]["h"],
    )
    assert r.status_code == 200, r.text
    told = await su.fetch(
        "SELECT title_fa, body_fa, link_kind FROM notify.notifications WHERE link_ref = $1 "
        "AND source_code = 'publish'",
        made["output"],
    )
    assert len(told) == 1 and "انجام نشد" in told[0]["title_fa"], [dict(x) for x in told]
    assert told[0]["link_kind"] == "deliverable" and "استوری" in told[0]["body_fa"]

    # a video without its caption is never sent on a standing word: it waits for his tap and
    # says so once; nothing is published by a later tick either
    day3 = day + timedelta(days=1)
    bare = await a_day(client, hub, su, g, day3, ("reel.mp4", "cover.png"))
    assert await jobs_of(su, bare["run"]) == []
    note = await su.fetchval("SELECT note_fa FROM growth.routine_runs WHERE id = $1", bare["run"])
    assert note == SPB.NO_CAPTION_FA
    async with holding_switch(su, "released"):
        await GR.tick(hub, now=at(day3, 8, 10), only={g["company"]["id"]})
    held = await su.fetch(
        "SELECT title_fa FROM notify.notifications WHERE link_ref = $1 AND source_code = 'publish'",
        bare["output"],
    )
    assert len(held) == 1 and "منتظر شماست" in held[0]["title_fa"]
    # ... and his tap on it in the outputs page (no session) sends it
    r = await client.post(
        f"/api/v1/deliverables/{bare['output']}/publish",
        headers={**owner, **idem()},
        json={"file_id": bare["files"]["reel.mp4"], "cover_file_id": bare["files"]["cover.png"],
              "caption": "کپشن دستی"},
    )  # fmt: skip
    assert r.status_code == 202 and r.json()["state"] == "publishing", r.text
    assert r.json()["auto"] is False and r.json()["kind"] == "reel"

    # he takes his word back: the next day's output waits for his tap again
    r = await client.put(f"/api/v1/groups/{key}/members/{co}/publish", headers=owner,
                         json={"mode": "ask"})  # fmt: skip
    assert r.status_code == 200 and r.json()["publish"] == {
        "mode": "ask", "account": None, "story": False, "since": None, "at": None, "best": False}  # fmt: skip
    day4 = day3 + timedelta(days=1)
    asked = await a_day(client, hub, su, g, day4, ("reel.mp4", "cover.png", "caption.txt"))
    assert "standing permission" not in asked["brief"]
    assert await jobs_of(su, asked["run"]) == []
    panel = (
        await client.get(f"/api/v1/deliverables/{asked['output']}/publish", headers=owner)
    ).json()
    assert panel["mode"] == "ask" and panel["caption"] == caption_of(day4)
    assert panel["publishes"] == []


async def test_a_word_given_later_covers_only_what_comes_after_and_waits_for_the_path(
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
    g = await a_group(client, hub, owner_session, su, new_company, monkeypatch, None)
    co, key = g["co"], g["key"]
    assert g["sealed"]["members"][0]["publish"]["mode"] == "ask"
    # yesterday's package was made while each output was his to tap ...
    day = datetime.now(TEHRAN).date() - timedelta(days=1)
    old = await a_day(client, hub, su, g, day, ("reel.mp4", "caption.txt"))
    assert await jobs_of(su, old["run"]) == []
    # ... he gives his word now: it covers what comes after, never what was made before it
    r = await client.put(f"/api/v1/groups/{key}/members/{co}/publish", headers=owner,
                         json={"mode": "auto"})  # fmt: skip
    assert r.status_code == 200 and r.json()["publish"]["account"] == "pro.chart", r.text
    async with holding_switch(su, "released"):
        ticked = await GR.tick(hub, now=at(day, 8, 20), only={g["company"]["id"]})
    assert ticked["published"] == 0 and await jobs_of(su, old["run"]) == []

    # a company whose publish path is not registered: the technical team's work, made once, and
    # the run goes out by itself on a later tick, when the path is there
    await su.execute(
        "UPDATE growth.connections SET config = config - 'publish_command' "
        "WHERE company_id = $1 AND kind = 'instagram'",
        g["company"]["id"],
    )
    day2 = datetime.now(TEHRAN).date() + timedelta(days=1)
    made = await a_day(client, hub, su, g, day2, ("reel.mp4", "caption.txt"))
    assert await jobs_of(su, made["run"]) == []
    note = await su.fetchval("SELECT note_fa FROM growth.routine_runs WHERE id = $1", made["run"])
    assert note == SPB.WAIT_SETUP_FA
    setup = await su.fetch("SELECT ref FROM work.work WHERE run_meta ->> 'ig_publish' = $1", co)
    assert len(setup) == 1
    assert await SPB.after_delivered(hub, made["work_id"]) == "waiting_setup"
    assert len(await su.fetch(
        "SELECT ref FROM work.work WHERE run_meta ->> 'ig_publish' = $1", co)) == 1  # fmt: skip
    r = await set_connection(
        client,
        f"{g['ig']['code']}-TECH-MGR",
        {"company": co, "kind": "instagram", "accounts": ["@pro.chart"], "via": "ig_hub",
         "server": {"company": g["ig"]["code"], "name": "IG-Hub"},
         "read_command": "cat /srv/ig/daily.json", "publish_command": COMMAND},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    # the launch gate holds everything that runs by itself, this too
    assert (await poll(client, g["ig_rn"])).status_code in (200, 204)
    async with holding_switch(su, "released"):
        ticked = await GR.tick(hub, now=at(day2, 8, 20), only={g["company"]["id"]})
    assert ticked["published"] == 1, ticked
    [job] = await jobs_of(su, made["run"])
    args = args_of(job)
    assert args["kind"] == "reel" and args["meta"]["cover"] is False
    assert args["caption"] == caption_of(day2)

    # he taps a package himself before its work is delivered: his standing word never sends
    # that file a second time
    day3 = day2 + timedelta(days=1)
    own = await a_day(client, hub, su, g, day3, ("reel.mp4", "caption.txt"), deliver=False)
    r = await client.post(
        f"/api/v1/deliverables/{own['output']}/publish",
        headers={**owner, **idem()},
        json={"file_id": own["files"]["reel.mp4"], "caption": caption_of(day3)},
    )
    assert r.status_code == 202 and r.json()["auto"] is False, r.text
    await refuse_queued(su, str(own["work_id"]))
    r = await client.post(
        f"/internal/v1/work/{own['work_id']}/deliver",
        headers={**await agent_headers(g["writer"]), **idem()},
        json={"title": "ریلز امروز آماده است", "body": "بسته در خروجی کارگاه است."},
    )
    assert r.status_code == 200, r.text
    assert await jobs_of(su, own["run"]) == []
    note = await su.fetchval("SELECT note_fa FROM growth.routine_runs WHERE id = $1", own["run"])
    assert note == SPB.ALREADY_FA
    posts = await su.fetchval(
        "SELECT count(*) FROM infra.server_jobs WHERE kind = 'publish' "
        "AND args -> 'session' ->> 'output' = $1",
        own["output"],
    )
    assert posts == 1
