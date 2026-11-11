"""⟨2026-11-11⟩ The publishing route and the daily working group never wait silently.

The owner's standing decision: Instagram, for every company, is read and published through IG-Hub;
it is never his step. The hub knows IG-Hub's command (the holding's `ig_hub` setting), so a
company's route is ready once the technical team has registered its accounts, which it learns from
IG-Hub by code (`<command> accounts`). A technical work that was delivered while the route is
still not ready is made again (once a day at most); a standing publish held for the route says the
desk's own line and keeps an open technical work; a routine that cannot run for an empty seat says
why and asks the company's CEO to fill it (once a seat a day); a routine's workshop output is
delivered by its turn, and its package follows without waiting for the agent's deliver.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.domain import best_hour as BH
from hq_api.domain import connections as CN
from hq_api.domain import groups as GR
from hq_api.domain import humanize as H
from hq_api.domain import publish_desk as PD
from hq_api.domain import session_publish as SPB
from hq_api.domain import work as W
from hq_api.hub import Hub

from .p10_fakes import holding_switch
from .test_p17_runners import pair, poll, take
from .test_p21_groups import TEHRAN, at, channel
from .test_p21_routing_orders import all_tx, auto_hiring  # noqa: F401 - the fixture
from .test_p21_secretary import no_model  # noqa: F401 - the fixture
from .test_p23_talk import talk  # noqa: F401 - the fixture
from .test_w18_standing_publish import a_day, a_group, args_of, jobs_of

HUB_COMMAND = "python3 /srv/ig-hub/deploy/hq_publish.py"
DESK_LINE = "مسیر انتشار این شرکت را تیم فنی وصل میکند"  # the desk card's line (web, Android)


async def instagram(su: Any, company_id: Any, config: str) -> None:
    await su.execute(
        """INSERT INTO growth.connections (company_id, kind, label_fa, config, origin)
           VALUES ($1, 'instagram', 'اینستاگرام (از راه IG-Hub)', CAST($2 AS jsonb), 'seed')
           ON CONFLICT (company_id, kind) DO UPDATE SET config = EXCLUDED.config""",
        company_id,
        config,
    )


async def tech_works(su: Any, tag: str, code: str) -> list[Any]:
    return list(
        await su.fetch(
            "SELECT ref, status FROM work.work WHERE run_meta ->> $1::text = $2 ORDER BY created_at",
            tag,
            code,
        )
    )


# ========================================== 1. the route: the holding's command, the accounts ==
def test_the_holdings_command_publishes_every_company_through_ig_hub() -> None:
    assert CN.ig_hub_command() == HUB_COMMAND  # seed/channels.yaml, not code
    assert CN.publish_command_of({"via": "ig_hub", "accounts": ["a"]}) == HUB_COMMAND
    assert CN.publish_command_of({}) == HUB_COMMAND  # no `via`: on IG-Hub by the owner's decision
    assert CN.publish_command_of({"publish_command": " /srv/own/pub "}) == "/srv/own/pub"
    assert CN.publish_command_of({"via": "elsewhere"}) is None
    # through IG-Hub the accounts are all it takes (no figures command is needed)
    assert CN.missing("instagram", {"via": "ig_hub", "accounts": ["pro.chart"]}, False) == []
    assert CN.missing("instagram", {"via": "ig_hub", "accounts": []}, False) == [
        "حساب روی IG-Hub است؛ تیم فنی آن را به هاب معرفی میکند"
    ]
    row = {"config": {"via": "ig_hub", "accounts": ["pro.chart"]}, "secret_set": False}
    assert CN.state_of("instagram", row) == "connected"
    assert CN.ig_hub_line(row) == "از راه IG-Hub خوانده و منتشر میشود (1 حساب)."
    assert BH.command(HUB_COMMAND, "@pro.chart") == f"{HUB_COMMAND} posts pro.chart 100"


def test_the_technical_team_learns_the_accounts_from_ig_hub_by_code() -> None:
    details = {"name_fa": "پروچارت", "name_en": "Pro-Chart", "sites": ["https://pro-chart.com"]}
    brief = CN.ig_setup_brief("PC", details)
    assert f"`{HUB_COMMAND} accounts`" in brief and "server.exec" in brief
    assert "server.map" in brief and "connection.set" in brief
    assert (
        "kind: instagram, via: ig_hub" in brief and "server: {company: IG, name: IG-Hub}" in brief
    )
    assert "paused" in brief and "never registered" in brief
    assert "«پروچارت»" in brief and "Pro-Chart" in brief and "https://pro-chart.com" in brief
    assert "Match by the company's name, its site and the handle" in brief
    assert "register nothing and say so in this work's result" in brief
    assert "Never ask the owner" in brief and "not connected: it is, through IG-Hub" in brief
    assert "read_command}" not in brief  # no figures command is asked for
    told = CN.ig_publish_brief("PC", details)
    assert f"`{HUB_COMMAND} accounts`" in told and "HQ_PUBLISH_FILE_1" in told
    assert "publish_command" in told and "goes out by itself" in told
    note = CN.ig_hub_note("PC")
    assert f"`{HUB_COMMAND} accounts`" in note and "NOT missing" in note


async def test_a_company_is_ready_once_its_accounts_are_registered(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    async with await all_tx(hub) as tx:
        none = await SPB._route(tx, co["id"])
    assert none["ready"] is False and none["command"] == HUB_COMMAND and none["accounts"] == []
    await instagram(su, co["id"], '{"via": "ig_hub", "accounts": []}')
    async with await all_tx(hub) as tx:
        empty = await SPB._route(tx, co["id"])
    assert empty["ready"] is False and empty["server_name"] == "IG-Hub"
    await instagram(su, co["id"], '{"via": "ig_hub", "accounts": ["pro.chart"]}')
    async with await all_tx(hub) as tx:
        ready = await SPB._route(tx, co["id"])
        state = await tx.scalar(
            "SELECT state FROM growth.connections WHERE company_id = :co AND kind = 'instagram'",
            co=co["id"],
        )
    assert ready["ready"] is True and ready["command"] == HUB_COMMAND
    assert ready["accounts"] == ["pro.chart"] and state is not None
    # a company's own command wins
    await instagram(
        su, co["id"], '{"via": "ig_hub", "accounts": ["pro.chart"], "publish_command": "/srv/x"}'
    )
    async with await all_tx(hub) as tx:
        assert (await SPB._route(tx, co["id"]))["command"] == "/srv/x"
    # the daily read of a connection with accounts and no figures command: nothing to read, no
    # error (the posts are read for the best hour)
    await instagram(su, co["id"], '{"via": "ig_hub", "accounts": ["pro.chart"]}')
    async with holding_switch(su, "released"):
        after = await CN.read_one(hub, co["id"], "instagram")
    assert after["state"] == "connected" and after["last_error_fa"] is None


async def test_the_best_hour_reads_the_posts_with_the_holdings_command(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    ig, co = await new_company(), await new_company()
    rn = await pair(client, hub, owner_session, ig, "IG-Hub")
    assert (await poll(client, rn)).status_code in (200, 204)
    server = {"company": ig["code"], "name": "IG-Hub"}
    await instagram(
        su, co["id"], json.dumps({"via": "ig_hub", "accounts": ["pro.chart"], "server": server})
    )
    got = await BH.read_due(hub, datetime.now(UTC))
    assert got["asked"] >= 1, got
    job = await take(client, rn)
    assert job["kind"] == "exec" and job["args"]["cmd"] == f"{HUB_COMMAND} posts pro.chart 100"


# ================================ 3. a delivered technical work is not open; once a day again ==
async def test_a_delivered_tech_work_with_the_route_not_ready_is_made_again_once_a_day(
    hub: Hub, su: Any, new_company: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    co = await new_company()
    code = co["code"]
    async with await all_tx(hub) as tx:
        first = await CN.ensure_ig_publish_work(tx, co["id"])
        assert first is not None
        assert await CN.ensure_ig_publish_work(tx, co["id"]) == first  # open: the same one
    # the technical team delivered it, and the route is still not ready: within the day it stands
    await su.execute("UPDATE work.work SET status = 'delivered' WHERE ref = $1", first)
    async with await all_tx(hub) as tx:
        assert await CN.ensure_ig_publish_work(tx, co["id"]) == first
    assert len(await tech_works(su, "ig_publish", code)) == 1
    # a day later: a new open one
    monkeypatch.setattr(CN, "TECH_AGAIN", timedelta(0))
    async with await all_tx(hub) as tx:
        again = await CN.ensure_ig_publish_work(tx, co["id"])
        assert again is not None and again != first
        assert await CN.ensure_ig_publish_work(tx, co["id"]) == again
    works = await tech_works(su, "ig_publish", code)
    assert [w["ref"] for w in works] == [first, again] and works[1]["status"] in W.OPEN
    # the same for the registration of the accounts
    async with await all_tx(hub) as tx:
        setup = await CN.ensure_ig_setup_work(tx, co["id"])
    assert setup is not None
    await su.execute("UPDATE work.work SET status = 'delivered' WHERE ref = $1", setup)
    async with await all_tx(hub) as tx:
        assert await CN.ig_setup_work(tx, co["id"]) is None  # delivered is not open
        made = await CN.ensure_ig_setup_work(tx, co["id"])
    assert made is not None and made != setup
    brief = await su.fetchval("SELECT brief FROM work.work WHERE ref = $1", made)
    assert f"`{HUB_COMMAND} accounts`" in brief and "شرکت آزمایشی" in brief


# ===== 4 + 6. the workshop output delivers a routine's work; a held publish says the desk's line ==
async def test_a_routines_output_goes_out_and_a_held_one_keeps_an_open_tech_work_silently(
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
    g = await a_group(client, hub, owner_session, su, new_company, monkeypatch,
                      {"publish": {"mode": "auto"}})  # fmt: skip
    co, cid = g["co"], g["company"]["id"]
    # 6. the workshop turn's end delivers the routine's work (a_day checks it) and its package
    # goes out by itself: nobody waits for the holder's deliver, nobody is woken to show it
    day = datetime.now(TEHRAN).date() + timedelta(days=1)
    made = await a_day(client, hub, su, g, day, ("reel.mp4", "cover.png", "caption.txt"))
    [job] = await jobs_of(su, made["run"])
    assert args_of(job)["kind"] == "reel" and args_of(job)["standing"]["run"] == str(made["run"])
    ws = await su.fetchval("SELECT state FROM work.workspaces WHERE work_id = $1", made["work_id"])
    assert ws == "delivered"
    woken = await su.fetchval(
        "SELECT count(*) FROM agents.runs WHERE work_id = $1 AND reason LIKE 'workshop_done:%'",
        made["work_id"],
    )
    assert woken == 0

    # 4. the accounts are gone (not registered): held, with the desk's own line on the run, an
    # open technical work, and no notification
    await su.execute(
        "UPDATE growth.connections SET config = config - 'accounts' - 'publish_command' "
        "WHERE company_id = $1 AND kind = 'instagram'",
        cid,
    )
    day2 = day + timedelta(days=1)
    held = await a_day(client, hub, su, g, day2, ("reel.mp4", "cover.png", "caption.txt"))
    assert await jobs_of(su, held["run"]) == []
    note = await su.fetchval("SELECT note_fa FROM growth.routine_runs WHERE id = $1", held["run"])
    assert note == SPB.WAIT_SETUP_FA and note.startswith(DESK_LINE) and H.check(note) == []
    [tech] = await tech_works(su, "ig_publish", co)
    assert tech["status"] in W.OPEN
    told = await su.fetchval(
        "SELECT count(*) FROM notify.notifications WHERE source_code = 'publish' AND company_id = $1",
        cid,
    )
    assert told == 0
    # the working group's page says it (the run's line), and so does the desk card
    r = await client.get(f"/api/v1/groups/{g['key']}/runs", headers=owner_session["headers"],
                         params={"company": co})  # fmt: skip
    assert any(x["note_fa"] == SPB.WAIT_SETUP_FA for x in r.json()["items"]), r.json()
    async with await all_tx(hub) as tx:
        desk = await PD.desk(tx, hub, cid)
    card = next(c for c in desk.ready if c.output == held["output"])
    assert card.route_ready is False
    # the technical team delivered its work and the route is still not ready: every tick keeps
    # it as it is within the day, and a day later a new open one is made, still without a push
    await su.execute("UPDATE work.work SET status = 'delivered' WHERE ref = $1", tech["ref"])
    assert await SPB.after_delivered(hub, held["work_id"]) == "waiting_setup"
    assert len(await tech_works(su, "ig_publish", co)) == 1
    monkeypatch.setattr(CN, "TECH_AGAIN", timedelta(0))
    async with holding_switch(su, "released"):
        await GR.tick(hub, now=at(day2, 8, 20), only={cid})
    works = await tech_works(su, "ig_publish", co)
    assert len(works) == 2 and works[1]["status"] in W.OPEN
    async with holding_switch(su, "released"):
        await GR.tick(hub, now=at(day2, 8, 30), only={cid})
    assert len(await tech_works(su, "ig_publish", co)) == 2  # an open one stands
    assert await su.fetchval(
        "SELECT count(*) FROM notify.notifications WHERE source_code = 'publish' AND company_id = $1",
        cid,
    ) == 0  # fmt: skip


# ============================== 5. an empty seat: the reason on the page, the CEO asked once ==
async def test_an_empty_seat_says_why_and_asks_the_ceo_to_fill_it_once_a_day(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    co = await new_company()
    code = co["code"]
    await channel(client, hub, owner_session, code)
    day = datetime.now(TEHRAN).date() + timedelta(days=1)
    async with holding_switch(su, "released"):
        out = await GR.tick(hub, now=at(day, 8, 0), only={co["id"]})
    assert out["skipped"] >= 1, out
    run = await su.fetchrow(
        """SELECT x.state, x.note_fa FROM growth.routine_runs x
           WHERE x.company_id = $1 AND x.routine = 'numbers' ORDER BY x.occurrence_at DESC LIMIT 1""",
        co["id"],
    )
    assert run["state"] == "skipped"
    assert run["note_fa"] == GR.EMPTY_CEO_FA.format(seat="تحلیلگر عملکرد")
    assert H.check(run["note_fa"]) == []
    # the working group's page shows the line
    r = await client.get("/api/v1/groups/content/runs", headers=owner_session["headers"],
                         params={"company": code, "routine": "numbers"})  # fmt: skip
    assert r.json()["items"][0]["note_fa"] == run["note_fa"], r.json()
    fills = await su.fetch(
        """SELECT w.ref, w.title, w.brief, w.priority, w.status, e.code, e.kind FROM work.work w
           JOIN core.employees e ON e.id = w.assignee_id
           WHERE w.company_id = $1 AND w.run_meta ->> 'seat_fill' = 'content:content_analyst'""",
        co["id"],
    )
    assert len(fills) == 1
    fill = fills[0]
    assert fill["kind"] == "ceo" and fill["status"] in W.OPEN and fill["priority"] == "P2"
    assert "تحلیلگر عملکرد" in fill["title"] and H.check(fill["title"]) == []
    assert "`hire`" in fill["brief"] and "content_analyst" in fill["brief"]
    assert "Never ask the owner" in fill["brief"]

    async def fills_now() -> int:
        return int(
            await su.fetchval(
                """SELECT count(*) FROM work.work
                   WHERE company_id = $1 AND run_meta ->> 'seat_fill' = 'content:content_analyst'""",
                co["id"],
            )
        )

    # the next day's run is skipped too: the open work stands, nothing new
    async with holding_switch(su, "released"):
        await GR.tick(hub, now=at(day + timedelta(days=1), 8, 0), only={co["id"]})
    assert await fills_now() == 1
    # the CEO delivered it and the seat is still empty: within the day nothing new; a day later
    # one more
    await su.execute("UPDATE work.work SET status = 'delivered' WHERE ref = $1", fill["ref"])
    async with holding_switch(su, "released"):
        await GR.tick(hub, now=at(day + timedelta(days=2), 8, 0), only={co["id"]})
    assert await fills_now() == 1
    monkeypatch.setattr(GR, "SEAT_FILL_AGAIN", timedelta(0))
    async with holding_switch(su, "released"):
        await GR.tick(hub, now=at(day + timedelta(days=3), 8, 0), only={co["id"]})
    assert await fills_now() == 2
    # an optional seat is never a hire of its own: its run says so plainly
    assert (
        "اختیاری" in GR.EMPTY_OPTIONAL_FA and H.check(GR.EMPTY_OPTIONAL_FA.format(seat="x")) == []
    )
