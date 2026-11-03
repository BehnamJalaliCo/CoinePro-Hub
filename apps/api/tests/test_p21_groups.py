"""Prompt 21 part 3 (contract §29.11): working groups as data. The content
group loads from its file (the management review §4's seats, routines and
KPIs); every eligible company joins by itself, a new one too; a routine's
occurrence makes ONE work item for the seat's employee, never two; a paused
membership or routine runs nothing; experiments one a week, closed with
their figure; the content lead's plan and suggestion through group.plan."""

from __future__ import annotations

import json
import secrets
import shutil
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from hq_api.domain import groups as GR
from hq_api.domain import humanize as H
from hq_api.hub import Hub

from .conftest import agent_headers, signed_put
from .p10_fakes import holding_switch

TEHRAN = ZoneInfo("Asia/Tehran")


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TEHRAN).astimezone(UTC)


async def channel(client: httpx.AsyncClient, hub: Hub, owner: dict[str, Any], co: str) -> None:
    """A publishing channel (a Telegram channel) for the company: it joins."""
    body = {"config": {"channels": [{"role": "signal", "title_fa": "کانال آزمایشی", "chat": "@test_ch"}]}}
    r = await signed_put(
        client, hub, owner, f"/api/v1/companies/{co}/connections/telegram", body, "connection.config"
    )
    assert r.status_code == 200, r.text


async def runs(su: Any, company_id: Any) -> list[Any]:
    return await su.fetch(
        """SELECT x.routine, x.state, x.note_fa, x.employee_code, x.occurrence_at, w.ref,
                  w.budget_tokens, w.run_meta, w.brief, e.code AS assignee
           FROM growth.routine_runs x LEFT JOIN work.work w ON w.id = x.work_id
           LEFT JOIN core.employees e ON e.id = w.assignee_id
           WHERE x.company_id = $1 ORDER BY x.occurrence_at, x.routine""",
        company_id,
    )


def test_the_content_group_is_data_as_the_management_review_says() -> None:
    files = dict(GR.load_files())
    d = files["content"]
    seats = {s["seat"]: s for s in d["seats"]}
    assert set(seats) == {
        "media_director", "scriptwriter", "visual_designer", "motion_designer", "video_director",
        "voice_producer", "publisher", "content_analyst",
    }  # fmt: skip
    assert {s for s, v in seats.items() if v["optional"]} == {"video_director", "voice_producer"}
    assert all(v["count"] == 1 for v in seats.values())
    assert d["lead"] == "media_director" and d["eligible"] == "has_channel"
    r = {x["key"]: x for x in d["routines"]}
    assert (r["numbers"]["seat"], r["numbers"]["schedule"]) == (
        "content_analyst", "FREQ=DAILY;BYHOUR=7;BYMINUTE=30"
    )  # fmt: skip
    assert r["plan"]["seat"] == "media_director" and "BYHOUR=8;" in r["plan"]["schedule"]
    assert r["review"]["task_class"] == "media_review" and "BYHOUR=14;" in r["review"]["schedule"]
    assert r["publishing"]["seat"] == "publisher" and r["publishing"]["needs"] == "sealed_series"
    assert "BYHOUR=20;" in r["evening_line"]["schedule"]
    assert "BYDAY=SA" in r["weekly_review"]["schedule"] and "BYDAY=SA" in r["weekly_plan"]["schedule"]
    assert r["weekly_review"]["seat"] == "content_analyst"
    assert [k["key"] for k in d["kpis"]][0] == "published"
    assert {"published", "followers", "views", "first_pass", "on_time", "experiments"} <= {
        k["key"] for k in d["kpis"]
    }
    assert {"instagram", "telegram"} <= set(d["connections"])
    for x in [d["title_fa"], d["purpose_fa"], *[s["title_fa"] for s in d["seats"]],
              *[x["title_fa"] for x in d["routines"]], *[k["title_fa"] for k in d["kpis"]]]:  # fmt: skip
        assert H.check(x) == [], x


async def test_a_changed_file_is_a_new_version_and_the_owners_pause_survives(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any, tmp_path: Path
) -> None:
    key = f"t{secrets.token_hex(4)}"
    src = (GR.GROUPS_DIR / "content.yaml").read_text(encoding="utf-8")
    body = src.replace("key: content", f"key: {key}").replace('state: "on"', 'state: "off"')
    (tmp_path / "g.yaml").write_text(body, encoding="utf-8")
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await GR.seed(tx, holding.id, tmp_path) == 1
        assert await GR.seed(tx, holding.id, tmp_path) == 0  # idempotent
    r = await client.put(f"/api/v1/groups/{key}/routines/plan", headers=owner, json={"state": "paused"})
    assert r.status_code == 200, r.text
    assert next(x for x in r.json()["routines"] if x["key"] == "plan")["state"] == "paused"
    (tmp_path / "g.yaml").write_text(body.replace("max_tokens: 120000", "max_tokens: 110000"),
                                     encoding="utf-8")  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await GR.seed(tx, holding.id, tmp_path) == 1
    g = (await client.get(f"/api/v1/groups/{key}", headers=owner)).json()
    assert g["version"] == 2 and g["state"] == "off"
    plan = next(x for x in g["routines"] if x["key"] == "plan")
    assert (plan["state"], plan["max_tokens"]) == ("paused", 110000)  # the pause survived
    versions = await su.fetch(
        """SELECT v.version FROM growth.group_versions v JOIN growth.groups g ON g.id = v.group_id
           WHERE g.key = $1 ORDER BY v.version""",
        key,
    )
    assert [v["version"] for v in versions] == [1, 2]
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "b.yaml").write_text(src.replace("seat: publisher\n", "seat: nobody\n"), encoding="utf-8")
    assert GR.load_files(bad) == []  # a file that does not hold together is refused whole
    shutil.rmtree(bad)
    listed = (await client.get("/api/v1/groups", headers=owner)).json()
    assert "content" in {x["key"] for x in listed}


async def test_every_eligible_company_joins_by_itself_a_new_one_too(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    members = (await client.get("/api/v1/groups/content/members", headers=h)).json()
    assert co["code"] not in {m["company"] for m in members}  # no channel yet
    # the seeded companies (the channels' seed) are members already
    assert {"TY", "FX", "PC"} <= {m["company"] for m in members}
    await channel(client, hub, owner_session, co["code"])
    day = datetime.now(TEHRAN).date()
    async with holding_switch(su, "released"):
        out = await GR.tick(hub, now=at(day, 3, 0), only={co["id"]})  # nothing due at 03:00
    assert out["joined"] >= 1 and out["queued"] == 0
    members = (await client.get("/api/v1/groups/content/members", headers=h)).json()
    mine = next(m for m in members if m["company"] == co["code"])
    seats = {s["seat"]: s for s in mine["seats"]}
    assert mine["state"] == "on"
    assert seats["media_director"]["employee"] == f"{co['code']}-MEDIA-MGR"
    assert seats["content_analyst"]["employee"] is None
    assert seats["video_director"]["optional"] is True


async def test_routines_make_one_work_item_per_period_for_the_seats_employee(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    await channel(client, hub, owner_session, co["code"])
    day = datetime.now(TEHRAN).date() + timedelta(days=1)
    only = {co["id"]}
    async with holding_switch(su, "released"):
        first = await GR.tick(hub, now=at(day, 8, 0), only=only)
        again = await GR.tick(hub, now=at(day, 8, 5), only=only)  # the same periods
        await GR.tick(hub, now=at(day, 14, 0), only=only)
        await GR.tick(hub, now=at(day + timedelta(days=1), 8, 0), only=only)
    assert first["queued"] == 1 and first["skipped"] == 1, first
    assert again["queued"] == 0 and again["skipped"] == 0, again
    found = await runs(su, co["id"])
    by = [(r["routine"], r["state"]) for r in found]
    # 07:30 numbers (within the look-back): its seat is empty; 08:00 plan: the lead's work
    assert by == [
        ("numbers", "skipped"), ("plan", "queued"), ("review", "queued"),
        ("numbers", "skipped"), ("plan", "queued"),
    ], by  # fmt: skip
    numbers = found[0]
    assert "خالی" in numbers["note_fa"] and H.check(numbers["note_fa"]) == []
    plan = found[1]
    assert plan["assignee"] == plan["employee_code"] == f"{co['code']}-MEDIA-MGR"
    assert plan["budget_tokens"] == 120000
    meta = json.loads(plan["run_meta"]) if isinstance(plan["run_meta"], str) else plan["run_meta"]
    assert (meta["group"], meta["routine"]) == ("content", "plan") and "task_class" not in meta
    assert "شرکت آزمایشی" in plan["brief"] and "group.plan" in plan["brief"]
    review = found[2]
    meta = json.loads(review["run_meta"]) if isinstance(review["run_meta"], str) else review["run_meta"]
    assert meta["task_class"] == "media_review"
    page = (
        await client.get(
            "/api/v1/groups/content/runs",
            headers=owner_session["headers"],
            params={"company": co["code"], "limit": 2},
        )
    ).json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    assert page["items"][0]["routine"] == "plan" and page["items"][0]["work_ref"].startswith("W-")
    # a work item that ends settles its run
    await su.execute(
        "UPDATE work.work SET status = 'cancelled' WHERE ref = $1", page["items"][0]["work_ref"]
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await GR.settle_runs(tx) >= 1
    state = await su.fetchval(
        """SELECT x.state FROM growth.routine_runs x JOIN work.work w ON w.id = x.work_id
           WHERE w.ref = $1""",
        page["items"][0]["work_ref"],
    )
    assert state == "failed"


async def test_nothing_runs_while_locked_or_paused(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    await channel(client, hub, owner_session, co["code"])
    day = datetime.now(TEHRAN).date() + timedelta(days=3)
    only = {co["id"]}
    # the launch gate: nothing while the holding's kill switch is engaged
    async with holding_switch(su, "engaged"):
        out = await GR.tick(hub, now=at(day, 8, 0), only=only)
    assert out.get("skipped") is True and await runs(su, co["id"]) == []
    async with holding_switch(su, "released"):
        await GR.tick(hub, now=at(day, 2, 0), only=only)  # joins
        r = await client.put(f"/api/v1/groups/content/members/{co['code']}", headers=h,
                             json={"state": "paused"})  # fmt: skip
        assert r.status_code == 200 and r.json()["state"] == "paused", r.text
        await GR.tick(hub, now=at(day, 8, 0), only=only)
        assert await runs(su, co["id"]) == []  # a paused membership runs nothing
        r = await client.put(f"/api/v1/groups/content/members/{co['code']}", headers=h,
                             json={"state": "on"})  # fmt: skip
        assert r.json()["state"] == "on"
        r = await client.put("/api/v1/groups/content/routines/plan", headers=h,
                             json={"state": "paused"})  # fmt: skip
        assert r.status_code == 200
        try:
            await GR.tick(hub, now=at(day, 8, 0), only=only)
        finally:
            await client.put("/api/v1/groups/content/routines/plan", headers=h, json={"state": "on"})
        assert [x["routine"] for x in await runs(su, co["id"])] == ["numbers"]  # plan was paused
        # a locked company runs nothing either
        await su.execute(
            "UPDATE control.kill_switches SET state = 'engaged' WHERE company_id = $1", co["id"]
        )
        try:
            await GR.tick(hub, now=at(day, 14, 0), only=only)
        finally:
            await su.execute(
                "UPDATE control.kill_switches SET state = 'released' WHERE company_id = $1", co["id"]
            )
        assert "review" not in [x["routine"] for x in await runs(su, co["id"])]
    bad = await client.put("/api/v1/groups/content/routines/nope", headers=h, json={"state": "paused"})
    assert bad.status_code == 404


async def test_publishing_waits_for_a_sealed_series_and_its_seat(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    await channel(client, hub, owner_session, co["code"])
    day = datetime.now(TEHRAN).date() + timedelta(days=5)
    async with holding_switch(su, "released"):
        await GR.tick(hub, now=at(day, 14, 30), only={co["id"]})
        found = [r for r in await runs(su, co["id"]) if r["routine"] == "publishing"]
        assert found[0]["state"] == "skipped" and "سری" in found[0]["note_fa"]
        await su.execute(
            """INSERT INTO media.series (company_id, title_fa, kind, targets, schedule, format, checks,
                   max_per_day, status, digest, proposed_by_kind, proposed_by_code, sealed_at,
                   sealed_digest)
               VALUES ($1, 'سری آزمایشی', 'post', '[{"channel": "telegram"}]', 'FREQ=DAILY;BYHOUR=10',
                       '{}', ARRAY['qc'], 1, 'sealed', repeat('a', 64), 'agent', 'x', now(),
                       repeat('a', 64))""",
            co["id"],
        )
        await su.execute(
            """INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en, role)
               SELECT c.id, d.id, $1, 'employee', 'مسئول انتشار', 'Publisher', 'publisher'
               FROM core.companies c JOIN core.departments d ON d.company_id = c.id AND d.code = 'MEDIA'
               WHERE c.id = $2""",
            f"{co['code']}-MEDIA-07",
            co["id"],
        )
        await GR.tick(hub, now=at(day, 20, 30), only={co["id"]})
    found = [r for r in await runs(su, co["id"]) if r["routine"] == "publishing"]
    assert [r["state"] for r in found] == ["skipped", "queued"]
    assert found[1]["assignee"] == f"{co['code']}-MEDIA-07"


async def test_experiments_and_the_leads_plan_through_the_agent_tools(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    c = co["code"]
    await channel(client, hub, owner_session, c)
    lead = await agent_headers(f"{c}-MEDIA-MGR")
    ceo = await agent_headers(f"{c}-CEO")
    async with holding_switch(su, "released"):
        await GR.tick(hub, now=at(datetime.now(TEHRAN).date(), 2, 0), only={co["id"]})
        r = await client.post(
            "/internal/v1/experiments",
            headers=lead,
            json={"hypothesis_fa": "ریلز ۱۵ ثانیه‌ای بیشتر دیده میشود", "metric": "views", "target": 1000},
        )
        assert r.status_code == 200, r.text
        e = r.json()
        assert e["result"] is None and e["company"] == c
        missing = await client.post("/internal/v1/experiments", headers=lead,
                                    json={"week": "2020-01-04", "metric": "views"})  # fmt: skip
        assert missing.status_code == 422
        closed = await client.post(
            "/internal/v1/experiments", headers=lead, json={"result": 1250, "kept": True}
        )
        assert closed.status_code == 200 and closed.json()["closed_at"], closed.text
        again = await client.post("/internal/v1/experiments", headers=lead, json={"result": 1})
        assert again.status_code == 409
        refused = await client.post(
            "/internal/v1/experiments", headers=ceo, json={"hypothesis_fa": "x x x", "metric": "views",
                                                           "target": 1}
        )  # fmt: skip
        assert refused.status_code == 403  # the CEO plans; the analyst and the lead experiment
        plan = await client.post(
            "/internal/v1/groups/plan",
            headers=lead,
            json={
                "items": [{"seat": "scriptwriter", "title_fa": "متن ریلز آموزش حد ضرر"}],
                "suggestion": {
                    "title_fa": "سری ریلز روزانه‌ی آموزشی را مُهر کنید",
                    "why_fa": "بازدید ریلزهای آموزشی دو برابر پست‌ها بود.",
                    "impact_fa": "بازدید هفتگی حدود 30٪ بیشتر",
                    "cost_fa": "یک ریلز در روز",
                    "impact": 4,
                    "cost": 2,
                },
            },
        )
        assert plan.status_code == 200, plan.text
        p = plan.json()
        assert p["items"] == 1 and p["suggestion"]["source"] == "group", p
        assert p["suggestion"]["company"] == c and p["suggestion"]["state"] == "new"
        bad = await client.post("/internal/v1/groups/plan", headers=lead,
                                json={"items": [{"seat": "nobody", "title_fa": "x"}]})  # fmt: skip
        assert bad.status_code == 422
        other = await client.post("/internal/v1/groups/plan", headers=lead,
                                  json={"company": "TY", "items": []})  # fmt: skip
        assert other.status_code == 403
    listed = (await client.get("/api/v1/groups/content/experiments", headers=h,
                               params={"company": c})).json()  # fmt: skip
    assert [(x["result"], x["kept"]) for x in listed] == [(1250.0, True)]
    members = (await client.get("/api/v1/groups/content/members", headers=h)).json()
    mine = next(m for m in members if m["company"] == c)
    assert mine["plan"]["items"][0]["seat"] == "scriptwriter"


async def test_kpis_are_the_real_daily_figures(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    await channel(client, hub, owner_session, co["code"])
    async with holding_switch(su, "released"):
        await GR.tick(hub, now=at(datetime.now(TEHRAN).date(), 2, 0), only={co["id"]})
    today = datetime.now(TEHRAN).date()
    for subject, value in (("@a_ch", 100), ("@b_ch", 50)):
        await su.execute(
            """INSERT INTO growth.metrics_daily (company_id, kind, day, key, subject, value, source)
               VALUES ($1, 'telegram', $2, 'followers', $3, $4, 'telegram')""",
            co["id"], today - timedelta(days=1), subject, value,
        )  # fmt: skip
    r = await client.get("/api/v1/groups/content/kpis", headers=owner_session["headers"],
                         params={"company": co["code"], "days": 7})  # fmt: skip
    assert r.status_code == 200, r.text
    (mine,) = r.json()["companies"]
    kpis = {k["key"]: k for k in mine["kpis"]}
    assert kpis["followers"]["series"] == [
        {"day": (today - timedelta(days=1)).isoformat(), "value": 150.0}
    ]
    assert kpis["first_pass"]["series"] == []  # not read yet: no point, never a guess


@pytest.mark.parametrize("routine", ["numbers", "plan", "review", "publishing", "evening_line"])
def test_each_routine_is_due_once_in_its_window(routine: str) -> None:
    from hq_api.domain import recurrence

    r = next(x for x in dict(GR.load_files())["content"]["routines"] if x["key"] == routine)
    rule = recurrence.parse(r["schedule"])
    day = date(2026, 11, 4)
    hits = set()
    for minute in range(0, 24 * 60, 10):
        occ = GR.due_occurrence(rule, "Asia/Tehran", at(day, minute // 60, minute % 60))
        if occ is not None and occ.astimezone(TEHRAN).date() == day:
            hits.add(occ)
    assert 1 <= len(hits) <= 2  # one occurrence a day (publishing: twice)
