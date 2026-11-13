"""⟨1.37⟩ W26 (contract §59.9-§59.10, prompt 38): the automations board, its health, the owner's
day, n8n's summary, the calendar, an automation's audit and a run's results.

The owner, 2026-11-13, asked for one place in the app for the automations. Every kind that runs by
itself is one list with one switch; his day is one line; n8n tells it at 21:30, once.
Rows are made by SQL (each test makes its own company; the test database outlives a run).
"""

from __future__ import annotations

import json
import random
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.domain import automation_board as AB
from hq_api.domain import run_results as RR
from hq_api.domain.gov_common import owner_tz, today
from hq_api.hub import Hub
from hq_api.lines import signing
from hq_api.principal import Principal

OWNER = Principal(kind="owner", code="owner", role="owner")
TOPIC = "سه سطح مهم طلا"
PERMALINK = "https://www.instagram.com/reel/AbC123/"


# ------------------------------------------------------------------- the rows --
async def holding_id(su: Any) -> uuid.UUID:
    return await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")


async def a_line(su: Any, co: dict[str, Any], schedule: str | None = None) -> dict[str, Any]:
    row = await su.fetchrow(
        """INSERT INTO lines.lines (company_id, template, template_version, platform, title_fa,
               caps, steps, schedule, state)
           VALUES ($1, 'reels_daily', 1, 'instagram_reel', 'ریلز روزانه', '{}', '[]', $2, 'on')
           RETURNING id, ref""",
        co["id"],
        schedule,
    )
    return dict(row)


async def a_flow(
    su: Any,
    co: dict[str, Any],
    *,
    at: str = "10:00",
    state: str = "on",
    skips: list[str] | None = None,
) -> dict[str, Any]:
    """A flow automation on its own line (as `POST /playbooks/{ref}/use` makes one)."""
    line = await a_line(su, co)
    ref = await su.fetchval(
        """INSERT INTO growth.automations (company_id, scope, sentence_fa, rule, state, sealed_at,
               kind, playbook, playbook_version, line, schedule, mode, story, skips)
           VALUES ($1, 'company', $2, '{}', $3, now(), 'flow', 'PB-0001', 2, $4, $5, 'auto', true, $6)
           RETURNING ref""",
        co["id"],
        f"ریلز روزانه‌ی {co['code']}",
        state,
        line["ref"],
        json.dumps({"mode": "fixed", "at": at, "days": None, "when_fa": ""}),
        json.dumps(skips or []),
    )
    return {"ref": ref, "line": line}


async def a_run(
    su: Any,
    co: dict[str, Any],
    line: dict[str, Any],
    when: datetime,
    *,
    state: str = "done",
    published: list[dict[str, Any]] | None = None,
    note: str | None = None,
    usd: float = 0.75,
) -> dict[str, Any]:
    row = await su.fetchrow(
        """INSERT INTO lines.runs (company_id, line_id, line_version, trigger, state, at,
               occurrence_at, published, note_fa, usd_equiv, ended_at)
           VALUES ($1, $2, 1, 'n8n', $3, $4::timestamptz, $4::timestamptz, $5, $6, $7,
                   $4::timestamptz + interval '80 minutes')
           RETURNING id, ref""",
        co["id"],
        line["id"],
        state,
        when,
        json.dumps(published or []),
        note,
        usd,
    )
    return dict(row)


def reel(media: str = "17900000000000001") -> list[dict[str, Any]]:
    return [
        {"platform": "instagram", "kind": "reel", "external_id": media,
         "at": datetime.now(UTC).isoformat(), "url": PERMALINK},
        {"platform": "instagram", "kind": "story", "external_id": media + "9",
         "at": datetime.now(UTC).isoformat(), "url": None},
    ]  # fmt: skip


async def a_member(su: Any, co: dict[str, Any], publish: dict[str, Any]) -> str:
    key = "w26_" + uuid.uuid4().hex[:8]
    gid = await su.fetchval(
        """INSERT INTO growth.groups (company_id, key, version, digest, title_fa, purpose_fa,
               definition)
           VALUES ($1, $2, 1, $3, 'ریلز روزانه', '', '{}') RETURNING id""",
        await holding_id(su),
        key,
        uuid.uuid4().hex + uuid.uuid4().hex,
    )
    await su.execute(
        "INSERT INTO growth.memberships (company_id, group_id, publish) VALUES ($1, $2, $3)",
        co["id"],
        gid,
        json.dumps(publish),
    )
    return key


async def a_routine(su: Any, co: dict[str, Any], *, kind: str, state: str) -> str:
    rule = {
        "trigger": {"kind": "schedule", "rrule": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"},
        "conditions": [],
        "actions": [{"kind": "notify.owner", "args": {"title_fa": "گزارش روز"}}],
    }
    return str(
        await su.fetchval(
            """INSERT INTO growth.automations (company_id, scope, sentence_fa, rule, state, sealed_at,
                   kind, source)
               VALUES ($1, 'company', 'هر روز ساعت ۹ گزارش بده', $2, $3,
                       CASE WHEN $3 = 'proposed' THEN NULL ELSE now() END, $4, $5)
               RETURNING ref""",
            co["id"],
            json.dumps(rule),
            state,
            kind,
            json.dumps({"routine": True, "order": None} if kind == "routine" else {}),
        )
    )


async def an_archive_rule(su: Any) -> str:
    return str(
        await su.fetchval(
            """INSERT INTO archive.automations (company_id, title_fa, on_event, actions)
               VALUES ($1, 'خبر سند تازه', 'filed', '[{"action": "notify", "args": {}}]')
               RETURNING ref""",
            await holding_id(su),
        )
    )


async def board(client: httpx.AsyncClient, owner: dict[str, str], **params: str) -> dict[str, Any]:
    r = await client.get("/api/v1/automations/board", headers=owner, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def item(b: dict[str, Any], ref: str) -> dict[str, Any]:
    found = [x for x in b["items"] if x["ref"] == ref]
    assert len(found) == 1, (ref, [x["ref"] for x in b["items"]])
    return found[0]


async def switch(hub: Hub, ref: str, state: str) -> bool:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        return await AB.switch(tx, hub, ref, state, OWNER)


# -------------------------------------------------------------- §59.10 board --
async def test_every_kind_is_on_the_board(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = await new_company()
    flow = await a_flow(su, co)
    run = await a_run(su, co, flow["line"], datetime.now(UTC) - timedelta(minutes=5), usd=1.25)
    plain = await a_line(su, co, schedule="FREQ=DAILY;BYHOUR=8;BYMINUTE=30")
    routine = await a_routine(su, co, kind="routine", state="on")
    proposed = await a_routine(su, co, kind="rule", state="proposed")
    key = await a_member(
        su, co, {"mode": "auto", "account": "pro.chart", "story": True, "at": "18:30"}
    )
    archive = await an_archive_rule(su)

    b = await board(client, owner)
    f = item(b, flow["ref"])
    assert f["kind"] == "flow" and f["state"] == "on" and f["switchable"] is True
    assert f["company"] == co["code"] and f["version"] == 2 and f["playbook"] == "PB-0001"
    assert f["opens"] == f"automation/{flow['ref']}"
    assert f["when_fa"] == "هر روز ساعت 10:00"
    assert f["last"]["state"] == "done" and f["cost_today_usd"] == pytest.approx(1.25)
    assert f["next_at"] is not None
    # the flow's own line is the flow's, never a second row
    assert not [x for x in b["items"] if x["ref"] == flow["line"]["ref"]]
    ln = item(b, plain["ref"])
    assert ln["kind"] == "line" and ln["opens"] == f"lines/{plain['ref']}" and ln["next_at"]
    rt = item(b, routine)
    assert rt["kind"] == "routine" and rt["state"] == "on" and rt["when_fa"].startswith("هر روز")
    pr = item(b, proposed)
    assert pr["kind"] == "rule" and pr["state"] == "proposed" and pr["switchable"] is False
    sp = item(b, f"SP:{key}:{co['code']}")
    assert sp["kind"] == "standing_publish" and sp["state"] == "on"
    assert sp["opens"] == f"groups/{key}" and "18:30" in sp["when_fa"]
    au = item(b, archive)
    assert au["kind"] == "archive" and au["state"] == "on"
    assert au["opens"] == f"archive-settings/automations/{archive}"
    assert [h["key"] for h in b["health"]] == [
        "n8n", "ighub", "publish_path", "helpers_browser", "aistudio", "workshop",
    ]  # fmt: skip
    assert b["today"]["runs"] >= 1 and b["today"]["cost_usd"] >= 1.25
    assert run["ref"]

    # one company, one kind
    mine = await board(client, owner, company=co["code"])
    assert {x["kind"] for x in mine["items"]} == {
        "flow",
        "line",
        "routine",
        "rule",
        "standing_publish",
    }
    only = await board(client, owner, company=co["code"], kind="standing_publish")
    assert [x["ref"] for x in only["items"]] == [f"SP:{key}:{co['code']}"]


async def test_the_switch_of_every_kind_that_is_not_a_flow(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = await new_company()
    key = await a_member(su, co, {"mode": "auto", "account": "pro.chart", "story": True, "at": "18:30",
                                  "since": "2026-11-01T00:00:00+00:00", "by": "owner"})  # fmt: skip
    sp = f"SP:{key}:{co['code']}"
    # the standing word off is «هر بار بپرس»; the word he gave is kept, so on gives it back
    assert await switch(hub, sp, "off") is True
    pub = json.loads(await su.fetchval(
        """SELECT m.publish FROM growth.memberships m JOIN growth.groups g ON g.id = m.group_id
           WHERE g.key = $1""", key))  # fmt: skip
    assert pub["mode"] == "ask" and pub["off"]["account"] == "pro.chart"
    assert item(await board(client, owner, company=co["code"]), sp)["state"] == "off"
    assert await switch(hub, sp, "on") is True
    pub = json.loads(await su.fetchval(
        """SELECT m.publish FROM growth.memberships m JOIN growth.groups g ON g.id = m.group_id
           WHERE g.key = $1""", key))  # fmt: skip
    assert pub["mode"] == "auto" and pub["account"] == "pro.chart" and pub["story"] is True
    assert pub["at"] == "18:30" and "off" not in pub and pub["since"] > "2026-11-02"
    assert item(await board(client, owner, company=co["code"]), sp)["state"] == "on"

    # a routine, a line, an archive rule
    routine = await a_routine(su, co, kind="routine", state="on")
    assert await switch(hub, routine, "off") is True
    assert (
        await su.fetchval("SELECT state FROM growth.automations WHERE ref = $1", routine) == "off"
    )
    line = await a_line(su, co, schedule="FREQ=DAILY;BYHOUR=8;BYMINUTE=30")
    assert await switch(hub, line["ref"], "off") is True
    assert (
        await su.fetchval("SELECT state FROM lines.lines WHERE ref = $1", line["ref"]) == "paused"
    )
    archive = await an_archive_rule(su)
    assert await switch(hub, archive, "off") is True
    assert (
        await su.fetchval("SELECT status FROM archive.automations WHERE ref = $1", archive)
        == "retired"
    )
    assert await switch(hub, archive, "on") is True
    assert (
        await su.fetchval("SELECT status FROM archive.automations WHERE ref = $1", archive)
        == "active"
    )
    # a rule of a sentence and a flow go on as before (routes/automations.py, the flow's own path)
    rule = await a_routine(su, co, kind="rule", state="proposed")
    assert await switch(hub, rule, "on") is False
    flow = await a_flow(su, co)
    assert await switch(hub, flow["ref"], "off") is False
    assert await switch(hub, "AT-999999", "off") is False

    changed = await su.fetch(
        """SELECT payload FROM core.outbox WHERE payload ->> 'type' = 'automation.changed'
             AND payload ->> 'ref' = ANY($1::text[])""",
        [sp, routine, line["ref"], archive],
    )
    assert len(changed) == 6

    # his audit of each: who and what, in plain words
    r = await client.get(f"/api/v1/automations/{sp}/audit", headers=owner)
    assert r.status_code == 200, r.text
    lines = r.json()
    assert [x["summary_fa"] for x in lines[:2]] == [
        "انتشار خودکار: از هر بار بپرس به خودکار", "انتشار خودکار: از خودکار به هر بار بپرس",
    ]  # fmt: skip
    assert {x["who_fa"] for x in lines} == {"مدیر کل"} and lines[0]["action"] == "group.publish"
    r = await client.get(f"/api/v1/automations/{archive}/audit", headers=owner, params={"limit": 1})
    assert [x["summary_fa"] for x in r.json()] == ["روشن و خاموش: از خاموش به روشن"]
    r = await client.get(f"/api/v1/automations/{line['ref']}/audit", headers=owner)
    assert r.json()[0]["summary_fa"] == "روشن و خاموش خط: از روشن به مکث"
    r = await client.get("/api/v1/automations/AT-999999/audit", headers=owner)
    assert r.status_code == 404
    r = await client.get("/api/v1/automations/XX-1/audit", headers=owner)
    assert r.status_code == 422


async def test_health_says_when_n8n_is_quiet(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = await new_company()
    await a_flow(su, co)
    holding = await holding_id(su)
    await su.execute(
        """INSERT INTO growth.flow_clock (company_id, last_tick_at) VALUES ($1, now() - interval '20 minutes')
           ON CONFLICT (company_id) DO UPDATE SET last_tick_at = EXCLUDED.last_tick_at""",
        holding,
    )
    n8n = next(h for h in (await board(client, owner))["health"] if h["key"] == "n8n")
    assert n8n == {"key": "n8n", "state": "warn", "note_fa": "n8n خاموش است؛ هاب خودش اجرا کرد"}
    await su.execute(
        "UPDATE growth.flow_clock SET last_tick_at = now() WHERE company_id = $1", holding
    )
    n8n = next(h for h in (await board(client, owner))["health"] if h["key"] == "n8n")
    assert n8n["state"] == "ok"
    # every note is plain Persian for the owner; nothing technical is his step
    for h in (await board(client, owner))["health"]:
        assert h["state"] in ("ok", "warn", "down") and h["note_fa"]
        assert "make " not in h["note_fa"] and "http" not in h["note_fa"]


# ------------------------------------------------------------ §59.9 the day --
async def test_the_day_in_one_line(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = await new_company()
    flow = await a_flow(su, co)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        tz = await owner_tz(tx)
    now = datetime.now(UTC)
    run = await a_run(su, co, flow["line"], now - timedelta(minutes=2), published=reel())
    await su.execute(
        """INSERT INTO lines.step_runs (company_id, run_id, pos, key, kind, state, output)
           VALUES ($1, $2, 0, 'topic', 'topic', 'done', $3)""",
        co["id"],
        run["id"],
        json.dumps({"text": TOPIC + "\nسه سطح، یک هفته"}),
    )
    await su.execute(
        """INSERT INTO growth.run_results (run_id, company_id, automation, permalink, comments,
               dms_sent, clicks)
           VALUES ($1, $2, $3, $4, 12, 9, 4)""",
        run["id"], co["id"], flow["ref"], PERMALINK,
    )  # fmt: skip
    r = await client.get("/api/v1/automations/today", headers=owner)
    assert r.status_code == 200, r.text
    day = r.json()
    assert day["day"] == today(tz).isoformat()
    assert f"ریلز «{TOPIC}» منتشر شد، ۱۲ کامنت، ۹ دایرکت، ۴ کلیک" in day["line_fa"]
    assert day["line_fa"].startswith("امروز: ")
    mine = next(x for x in day["items"] if x["automation"] == flow["ref"])
    assert mine["published"] == [{"kind": "reel", "url": PERMALINK}]
    assert (mine["comments"], mine["dms_sent"], mine["clicks"]) == (12, 9, 4)
    assert mine["cost_usd"] == pytest.approx(0.75) and mine["company_fa"]

    # a day nothing went out: why, in one line
    far = date(2090, 1, 1) + timedelta(days=random.randrange(3000))
    when = datetime(far.year, far.month, far.day, 9, 0, tzinfo=UTC)
    await a_run(su, co, flow["line"], when, state="failed", note="سقف بودجه‌ی امروز پر شد")
    r = await client.get(
        "/api/v1/automations/today", headers=owner, params={"day": far.isoformat()}
    )
    day = r.json()
    assert day["line_fa"].startswith("امروز چیزی منتشر نشد: ")
    assert "سقف بودجه‌ی امروز پر شد" in day["line_fa"]
    mine = next(x for x in day["items"] if x["automation"] == flow["ref"])
    assert mine["state"] == "failed" and mine["published"] == [] and mine["comments"] is None


async def test_the_summary_is_signed_and_said_once_a_day(
    client: httpx.AsyncClient, hub: Hub, su: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    secret = "test-n8n-secret-" + uuid.uuid4().hex
    monkeypatch.setattr(hub, "secrets", replace(hub.secrets, n8n_secret=secret))
    far = date(2090, 1, 1) + timedelta(days=random.randrange(3000))
    body = json.dumps({"day": far.isoformat()}).encode()
    url = "/internal/v1/flows/summary"
    ct = {"Content-Type": "application/json"}
    assert (await client.post(url, content=body, headers=ct)).status_code == 401
    bad = {signing.HEADER: signing.sign("wrong", body), **ct}
    assert (await client.post(url, content=body, headers=bad)).status_code == 401
    r = await client.post(
        url, content=body, headers={signing.HEADER: signing.sign(secret, body), **ct}
    )
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["notified"] is True and first["day"] == far.isoformat()
    assert first["line_fa"].startswith("امروز چیزی منتشر نشد")
    r = await client.post(
        url, content=body, headers={signing.HEADER: signing.sign(secret, body), **ct}
    )
    assert r.status_code == 200 and r.json()["notified"] is False
    assert (
        await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE action = 'automation.summary' AND target_ref = $1",
            far.isoformat(),
        )
        == 1
    )
    events = await su.fetch(
        """SELECT payload FROM core.outbox WHERE payload ->> 'type' = 'automation.summary'
             AND payload -> 'data' ->> 'day' = $1""",
        far.isoformat(),
    )
    assert len(events) == 1
    assert json.loads(events[0]["payload"])["data"]["line_fa"] == first["line_fa"]
    note = await su.fetchrow(
        """SELECT level, title_fa, body_fa FROM notify.notifications
           WHERE title_fa = $1 ORDER BY created_at DESC LIMIT 1""",
        AB.SUMMARY_TITLE_FA,
    )
    assert note is not None and note["level"] == "report"
    assert not any(c.isascii() and c.isalpha() for c in note["title_fa"] + note["body_fa"])
    assert AB.persian_only("امروز: ریلز «TABC روزانه» منتشر شد https://x.y/z، «F-0018»") == (
        "امروز: ریلز «روزانه» منتشر شد"
    )


# -------------------------------------------------------- §59.10 calendar --
async def test_the_calendar_has_runs_plans_and_skips(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        tz = await owner_tz(tx)
    d0 = today(tz)
    skipped = d0 + timedelta(days=3)
    co = await new_company()
    flow = await a_flow(su, co, at="10:00", skips=[skipped.isoformat()])
    gone = datetime.now(UTC) - timedelta(days=2)
    await a_run(su, co, flow["line"], gone, state="failed", note="یک قدم انجام نشد")
    r = await client.get(
        "/api/v1/automations/calendar", headers=owner,
        params={"from": (d0 - timedelta(days=2)).isoformat(), "to": (d0 + timedelta(days=6)).isoformat(),
                "company": co["code"]},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    days = {d["day"]: [e for e in d["items"] if e["ref"] == flow["ref"]] for d in r.json()["days"]}
    assert len(days) == 9
    ran = [e for es in days.values() for e in es if e["state"] == "failed"]
    assert len(ran) == 1
    assert [e["state"] for e in days[skipped.isoformat()]] == ["skipped"]
    for k in range(1, 7):
        d = (d0 + timedelta(days=k)).isoformat()
        assert [e["state"] for e in days[d]] == (["skipped"] if k == 3 else ["planned"]), d
    # off: nothing planned ahead
    await su.execute("UPDATE growth.automations SET state = 'off' WHERE ref = $1", flow["ref"])
    r = await client.get(
        "/api/v1/automations/calendar", headers=owner,
        params={"from": d0.isoformat(), "to": (d0 + timedelta(days=6)).isoformat(), "company": co["code"]},
    )  # fmt: skip
    assert not [e for d in r.json()["days"] for e in d["items"]]
    r = await client.get(
        "/api/v1/automations/calendar",
        headers=owner,
        params={"from": d0.isoformat(), "to": (d0 + timedelta(days=90)).isoformat()},
    )
    assert r.status_code == 422
    for params in ({"from": "0001-01-01"}, {"from": "9999-12-31"}):
        r = await client.get("/api/v1/automations/calendar", headers=owner, params=params)
        assert r.status_code == 422, r.text
    r = await client.get("/api/v1/automations/today", headers=owner, params={"day": "9999-12-31"})
    assert r.status_code == 422


def test_occurrences_follow_the_days_and_the_clock() -> None:
    start = datetime(2026, 11, 14, 0, 0, tzinfo=UTC)  # a Saturday
    got = AB.occurrences(
        {"days": ["SA", "MO"]}, "Asia/Tehran", start, start + timedelta(days=7), "18:30"
    )
    assert [t.isoformat() for t in got] == [
        "2026-11-14T15:00:00+00:00",
        "2026-11-16T15:00:00+00:00",
    ]
    assert AB.occurrences({}, "Asia/Tehran", start, start + timedelta(days=2), "bad") == []
    assert AB.skip_days(["2026-11-16", {"at": "2026-11-17T05:00:00Z"}, {"at": "x"}], "Asia/Tehran") == {
        date(2026, 11, 16), date(2026, 11, 17),
    }  # fmt: skip


# ------------------------------------------------------- §59.9 the results --
def test_the_stats_line_is_read_as_igb_prints_it() -> None:
    line = json.dumps({
        "post": {"id": "17900", "permalink": PERMALINK, "media_type": "VIDEO", "like_count": 40,
                 "comments_count": 12, "reach": None, "views": 900, "saved": 3, "shares": None},
        "rules": {"rule:comment:17900:طلا": {"sent": 7, "clicks": 3},
                  "rule:story_reply:179009:طلا": {"sent": 2, "clicks": None}},
    })  # fmt: skip
    got = RR.parse_stats("noise\n" + line)
    assert got == {
        "permalink": PERMALINK, "likes": 40, "comments": 12, "views": 900, "reach": None,
        "saves": 3, "shares": None, "dms_sent": 9, "clicks": 3,
    }  # fmt: skip
    assert RR.parse_stats("unknown command: stats") is None
    assert RR.stats_command("/srv/ig/bin/hq-publish", "17900", ["rule:comment:17900:a b"]) == (
        "/srv/ig/bin/hq-publish stats 17900 'rule:comment:17900:a b'"
    )
    base = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
    assert RR.next_read(base, base + timedelta(hours=3)) == base + timedelta(hours=4)
    assert RR.next_read(base, base + timedelta(hours=23, minutes=30)) == base + timedelta(hours=24)
    assert RR.next_read(base, base + timedelta(hours=25)) == base + timedelta(days=7)
    assert RR.next_read(base, base + timedelta(days=7, minutes=1)) is None


async def test_a_flow_run_that_published_gets_its_figures(
    hub: Hub, su: Any, new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = await new_company()
    flow = await a_flow(su, co)
    media = str(random.randrange(10**15, 10**16))
    run = await a_run(
        su, co, flow["line"], datetime.now(UTC) - timedelta(hours=2), published=reel(media)
    )
    await su.execute(
        """INSERT INTO growth.ig_posts (company_id, account, post_id, media_type, permalink,
               posted_at, likes, comments)
           VALUES ($1, 'pro.chart', $2, 'VIDEO', $3, now() - interval '2 hours', 5, 3)""",
        co["id"], media, PERMALINK,
    )  # fmt: skip
    out = await RR.read_due(hub)
    assert out["made"] >= 1
    row = await su.fetchrow("SELECT * FROM growth.run_results WHERE run_id = $1", run["id"])
    assert row["automation"] == flow["ref"] and row["permalink"] == PERMALINK
    assert (row["likes"], row["comments"]) == (5, 3)
    # what nobody gave is null, never 0
    assert row["dms_sent"] is None and row["clicks"] is None and row["views"] is None
    assert row["reads"] == 1 and row["read_at"] is not None
    assert row["next_read_at"] > datetime.now(UTC) + timedelta(minutes=50)
    # not due again within the hour
    await RR.read_due(hub)
    assert (
        await su.fetchval("SELECT reads FROM growth.run_results WHERE run_id = $1", run["id"]) == 1
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        got = await RR.results_of(tx, [run["id"]])
    assert got[run["id"]].likes == 5 and got[run["id"]].shares is None
