"""⟨1.39⟩ Contract §61 (prompt 39, P1): the automations as data, edited in the app, on one clock.

The owner: «بخش اتوماسیون خیلی مبتدیه و باید یک قسمت مهم آپ باشه با کلی فیچر … و با قابلیت
تغییرات». The code flows (FLOWS) are the seed of automations.flows; the code reads the rows; an hour
edited in the app is a new version and the next day starts at it, with nothing edited in n8n.
Every test makes its own company and flows (a live page's hour is never moved, prompt 39).
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from collections.abc import Callable
from dataclasses import fields, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from hq_api.domain import flow_defs as FD
from hq_api.domain import flows as FL
from hq_api.hub import Hub
from hq_api.lines import signing

from .conftest import agent_headers, idem
from .test_p21_secretary import no_model  # noqa: F401 - the fixture

TZ = ZoneInfo(FL.TEHRAN)
OPUS = "claude-opus-5-5"
ROW_ONLY = {"ref", "state", "paused_until", "skips", "days", "channel", "version"}


def migration() -> ModuleType:
    """The migration that made automations.flows (its seed runs again for a company made later)."""
    path = next((Path(__file__).resolve().parents[1] / "migrations" / "versions").glob(
        "*_automations_flows.py"))  # fmt: skip
    spec = importlib.util.spec_from_file_location("automations_flows_migration", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def seed(su: Any, monkeypatch: pytest.MonkeyPatch, *flows: FL.Flow) -> dict[str, str]:
    """Rows for these flows exactly as migration 0070 made the code flows' (their refs by key)."""
    monkeypatch.setattr(FL, "FLOWS", {f.key: f for f in flows})
    await su.execute(migration().seed_sql(FD.seed_rows()))
    rows = await su.fetch(
        "SELECT key, ref FROM automations.flows WHERE key = ANY($1::text[])", [f.key for f in flows]
    )
    return {r["key"]: r["ref"] for r in rows}


def a_flow(company: str, key: str, **over: Any) -> FL.Flow:
    base = FL.Flow(
        key=key, company=company, account=f"p39.{key}", title_fa="ریلز آزمایشی ۳۹",
        kit="/home/studio/kits/p39-test", start=date(2026, 11, 17), hours=("13:00",) * 4,
        story=False, trigger_at="09:00", usd_cap=Decimal("20"), model=OPUS, effort="xhigh",
        same_day=True, n8n="hqFlowP39Test",
    )  # fmt: skip
    return replace(base, **over)


def fk() -> str:
    return f"p{uuid.uuid4().hex[:10]}"


async def all_off(su: Any, *keys: str) -> None:
    await su.execute(
        "UPDATE automations.flows SET state = 'off', paused_until = NULL WHERE key = ANY($1::text[])",
        list(keys),
    )


def tomorrow() -> date:
    return datetime.now(TZ).date() + timedelta(days=1)


async def save(
    client: httpx.AsyncClient, owner: dict[str, str], ref: str, version: int, body: dict[str, Any]
) -> httpx.Response:
    return await client.patch(
        f"/api/v1/automations/flows/{ref}", headers={**owner, "If-Match": str(version)}, json=body
    )


# ------------------------------------------------------------------- the seed --
async def test_the_seed_is_every_code_flow_with_its_behaviour(
    su: Any, new_company: Callable[..., Any]
) -> None:
    """§61.1 every flow of FLOWS is a row (the pilots too), the same key and behaviour, version 1
    «ساخته شد از روند کدی هاب»; the seed runs again without a second row or version."""
    for code in sorted({f.company for f in FL.FLOWS.values()}):
        if not await su.fetchval("SELECT 1 FROM core.companies WHERE code = $1", code):
            await new_company(code=code)  # (the test DB has no IG)
    keys = list(FL.FLOWS)
    try:
        await su.execute(migration().seed_sql(FD.seed_rows()))
        versions = await su.fetchval("SELECT count(*) FROM automations.flow_versions")
        await su.execute(migration().seed_sql(FD.seed_rows()))
        assert await su.fetchval("SELECT count(*) FROM automations.flow_versions") == versions
        rows = {
            r["key"]: r
            for r in await su.fetch(FL.FLOW_SQL + " WHERE f.key = ANY($1::text[])", keys)
        }
        assert set(rows) == set(keys)
        for key, want in FL.FLOWS.items():
            got = FL.from_row(rows[key])
            assert got.ref.startswith("AF-") and len(got.ref) >= 7, key
            for f in fields(FL.Flow):
                if f.name in ROW_ONLY:
                    continue
                expected = getattr(want, f.name)
                if f.name == "effort":
                    expected = expected or "max"
                assert getattr(got, f.name) == expected, (key, f.name)
            assert got.days == FL.ALL_DAYS and got.channel == "instagram"
            v1 = await su.fetchrow(
                "SELECT note_fa, body, by_fa FROM automations.flow_versions"
                " WHERE flow_id = $1 AND version = 1",
                rows[key]["id"],
            )
            assert v1["note_fa"] == "ساخته شد از روند کدی هاب", key
            assert json.loads(v1["body"]) == FD.body_of(want), key
        # the pilots are rows too: an empty account publishes nothing, and the board skips them
        assert any(not FL.from_row(r).account for r in rows.values())
        off = await su.fetchval("SELECT flows_off FROM owner.settings WHERE id = 1")
        assert not set(off or []) & set(keys)
    finally:
        await all_off(su, *keys)


# ------------------------------------------------------- an hour, a version --
async def test_an_hour_edited_is_a_version_and_the_next_day_starts_at_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance 6 and 8: 13:00 → 14:00 is version 2 with its audit; the hub's clock (no n8n tick)
    starts the next day at 14:00, a second call is a no-op and n8n's own call answers that order;
    the first version's body saved again puts 13:00 back (version 3)."""
    co = await new_company()
    key = fk()
    ref = (await seed(su, monkeypatch, a_flow(co["code"], key)))[key]
    secret = "test-n8n-secret-" + "y" * 16
    monkeypatch.setattr(hub, "secrets", replace(hub.secrets, n8n_secret=secret))
    try:
        r = await client.get(f"/api/v1/automations/flows/{ref}", headers=owner)
        assert r.status_code == 200, r.text
        page = r.json()
        assert page["version"] == 1 and page["schedule"]["hours"] == ["13:00"] * 4
        assert page["legacy_ref"] == f"N8:{key}" and page["model_fa"] == "Opus 5.5"
        assert page["state"] == "on" and page["kind"] == "reel" and page["next"] is not None

        r = await save(client, owner, ref, 1,
                       {"schedule": {"hours": ["14:00"] * 4}, "note_change_fa": "ساعت تازه"})  # fmt: skip
        assert r.status_code == 200, r.text
        assert r.json()["version"] == 2 and r.json()["schedule"]["hours"] == ["14:00"] * 4
        v2 = await su.fetchrow(
            """SELECT v.changes, v.note_fa, v.by_fa FROM automations.flow_versions v
               JOIN automations.flows f ON f.id = v.flow_id WHERE f.ref = $1 AND v.version = 2""",
            ref,
        )
        (change,) = json.loads(v2["changes"])
        assert change["field"] == "schedule.hours" and change["label_fa"]
        assert change["before_fa"].startswith("۱۳:۰۰") and change["after_fa"].startswith("۱۴:۰۰")
        assert v2["note_fa"] == "ساعت تازه" and v2["by_fa"] == "مدیر کل"
        audit = await su.fetchval(
            """SELECT summary FROM audit.entries WHERE action = 'automation.flow.update'
                 AND target_ref = $1 ORDER BY seq DESC LIMIT 1""",
            ref,
        )
        assert '"13:00"' in audit and '"14:00"' in audit

        # the clock: no n8n tick; the backup starts the day at its trigger, the post at 14:00
        day = tomorrow()
        async with hub.db.tx(await hub.companies.ids()) as tx:
            row = await FL.flow_by_key(tx, key)
        assert row is not None
        at = FL.trigger_of(row, day) + timedelta(minutes=1)
        orders = await FL.clock(hub, at)
        assert len(orders) == 1, orders
        meta = json.loads(await su.fetchval(
            "SELECT run_meta -> 'flow' FROM work.work WHERE run_meta -> 'flow' ->> 'order' = $1",
            orders[0]))  # fmt: skip
        assert meta["day"] == day.isoformat()
        assert (
            datetime.fromisoformat(meta["publish_at"]).astimezone(TZ).strftime("%H:%M") == "14:00"
        )
        assert await FL.clock(hub, at + timedelta(minutes=1)) == []
        # n8n's per-flow workflow still calls: nothing new
        body = json.dumps({"day": day.isoformat()}, separators=(",", ":")).encode()
        r = await client.post(
            f"/internal/v1/flows/{key}/run", content=body,
            headers={signing.HEADER: signing.sign(secret, body),
                     "Idempotency-Key": str(FL.n8n_key(key, day)),
                     "Content-Type": "application/json"},
        )  # fmt: skip
        # (it comes at its own old hour, before the row's: 39.1 makes it a no-op)
        assert r.status_code == 202 and r.json()["reason"] == "before_trigger", r.text
        assert await su.fetchval(
            """SELECT count(*) FROM work.work WHERE parent_id IS NULL
                 AND run_meta -> 'flow' ->> 'key' = $1 AND run_meta -> 'flow' ->> 'day' = $2""",
            key, day.isoformat(),
        ) == 1  # fmt: skip

        # §59.7.1 the old ref, the board and the day's page answer as for 1.2.0
        r = await client.get(f"/api/v1/automations/N8:{key}", headers=owner)
        assert r.status_code == 200 and r.json()["state"] == "on", r.text
        board = (await client.get("/api/v1/automations/board?kind=n8n", headers=owner)).json()
        (card,) = [i for i in board["items"] if i["ref"] == f"N8:{key}"]
        assert card["kind"] == "n8n" and card["state"] == "on" and card["last"]["state"]
        run = await client.get(f"/api/v1/line-runs/{orders[0]}", headers=owner)
        assert run.status_code == 200 and run.json()["automation"] == f"N8:{key}", run.text

        # «برگشت به این نسخه»: version 1's body saved again as version 3, 13:00 again
        r = await client.post(f"/api/v1/automations/flows/{ref}/rollback", headers=owner,
                              json={"version": 1})  # fmt: skip
        assert r.status_code == 200 and r.json()["version"] == 3, r.text
        assert r.json()["schedule"]["hours"] == ["13:00"] * 4
        got = (await client.get(f"/api/v1/automations/flows/{ref}/versions", headers=owner)).json()
        assert [v["version"] for v in got] == [3, 2, 1]
        assert got[0]["note_fa"] == "برگشت به نسخه‌ی ۱" and got[0]["changes"][0][
            "after_fa"
        ].startswith("۱۳:۰۰")
        assert got[-1]["note_fa"] == "ساخته شد از روند کدی هاب"
        assert await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE action = 'automation.flow.rollback' AND target_ref = $1",
            ref,
        ) == 1  # fmt: skip
        r = await client.post(f"/api/v1/automations/flows/{ref}/rollback", headers=owner,
                              json={"version": 9})  # fmt: skip
        assert r.status_code == 404, r.text
        async with hub.db.tx(await hub.companies.ids()) as tx:
            row = await FL.flow_by_key(tx, key)
            assert row is not None
            at2, _ = await FL.slot_of(tx, row, day + timedelta(days=1), co["id"])
        assert at2.astimezone(TZ).strftime("%H:%M") == "13:00"
        assert await su.fetchval(
            """SELECT count(*) FROM automations.flow_versions v JOIN automations.flows f
                 ON f.id = v.flow_id WHERE f.ref = $1""",
            ref,
        ) == 3  # fmt: skip
    finally:
        await all_off(su, key)


# ---------------------------------------------------------------- §61.4 checks --
async def test_a_save_holds_only_what_it_may(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance 7: 422 invalid_flow with one Persian line per field; a stale If-Match is 409."""
    co = await new_company()
    reel, st = fk(), fk()
    page = f"p39.{reel}"
    refs = await seed(
        su, monkeypatch, a_flow(co["code"], reel, account=page),
        a_flow(co["code"], st, account=page, hours=("10:00",), stories=("10:00", "16:30"),
               trigger_at="02:30"),
    )  # fmt: skip
    ref = refs[st]
    try:
        cases: list[tuple[dict[str, Any], str, str]] = [
            ({"schedule": {"trigger_at": "9:5"}}, "schedule.trigger_at", FD.HOUR_FA),
            ({"schedule": {"hours": ["25:00"]}}, "schedule.hours", "ساعت باید به شکل ۱۴:۰۰ باشد"),
            ({"effort": "low"}, "effort", FD.EFFORT_BAD_FA),
            ({"usd_cap": 0}, "usd_cap", "سقف روز باید بین ۱ و ۵۰۰ دلار باشد"),
            ({"usd_cap": 501}, "usd_cap", "سقف روز باید بین ۱ و ۵۰۰ دلار باشد"),
            ({"schedule": {"stories": [f"{h:02d}:10" for h in range(4, 20)]}},
             "schedule.stories", "حداکثر ۱۵ استوری"),
            ({"schedule": {"stories": ["10:00", "10:00"]}}, "schedule.stories",
             "این ساعت دو بار آمده است: ۱۰:۰۰"),
            ({"schedule": {"stories": ["13:00", "16:30"]}}, "schedule.stories",
             "این ساعت با ریلز ۱۳:۰۰ همین پیج هم‌دقیقه است"),
            ({"schedule": {"stories": ["03:00"]}}, "schedule.stories",
             "هر ساعت انتشار باید دست‌کم ۹۰ دقیقه بعد از شروع ساخت باشد"),
            ({"schedule": {"days": []}}, "schedule.days", FD.DAYS_FA),
            ({"model": "gpt-5.5"}, "model", FD.MODEL_FA),
            ({"note_fa": "ن" * 2001}, "note_fa", FD.NOTE_FA),
        ]  # fmt: skip
        for body, field, line in cases:
            r = await save(client, owner, ref, 1, body)
            assert r.status_code == 422, (body, r.text)
            got = r.json()
            assert got["code"] == "invalid_flow", got
            assert {"field": field, "message_fa": line} in got["errors"], (body, got["errors"])
        # a reel of the same page moved onto a story's minute: refused the other way round
        r = await save(client, owner, refs[reel], 1, {"schedule": {"hours": ["16:30"] * 4}})
        assert r.status_code == 422 and r.json()["errors"] == [
            {
                "field": "schedule.hours",
                "message_fa": "این ساعت با استوری ۱۶:۳۰ همین پیج هم‌دقیقه است",
            }
        ], r.text
        # If-Match: needed, and the version read
        r = await client.patch(f"/api/v1/automations/flows/{ref}", headers=owner, json={})
        assert r.status_code == 428, r.text
        ok = await save(client, owner, ref, 1, {"schedule": {"stories": ["10:00", "17:00"]}})
        assert ok.status_code == 200 and ok.json()["version"] == 2, ok.text
        stale = await save(client, owner, ref, 1, {"schedule": {"stories": ["10:00", "18:00"]}})
        assert stale.status_code == 409 and stale.json()["code"] == "version_conflict", stale.text
        # nothing changed: no new version
        same = await save(client, owner, ref, 2, {"schedule": {"stories": ["10:00", "17:00"]}})
        assert same.status_code == 200 and same.json()["version"] == 2, same.text
    finally:
        await all_off(su, reel, st)


# ------------------------------------------------------------- the controls --
async def test_the_switch_the_pause_the_skip_and_run_now(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§61.2-§61.3: a skipped or paused day makes nothing (n8n's call too); run-now makes the day,
    a second one is 409 already_ran with it; the board's switch of `N8:<key>` writes `state`."""
    co = await new_company()
    key = fk()
    ref = (await seed(su, monkeypatch, a_flow(co["code"], key)))[key]
    day = tomorrow()
    base = f"/api/v1/automations/flows/{ref}"

    async def n8n_call(d: date) -> dict[str, Any]:
        r = await client.post(f"/api/v1/flows/{key}/run", headers={**owner, **idem()},
                              json={"day": d.isoformat()})  # fmt: skip
        assert r.status_code == 201, r.text
        return dict(r.json())

    try:
        r = await client.post(f"{base}/skip", headers=owner, json={"day": day.isoformat()})
        assert r.status_code == 200, r.text
        assert (await n8n_call(day))["why_fa"] == FL.SKIPPED_WHY_FA
        r = await client.post(f"{base}/skip", headers=owner,
                              json={"day": day.isoformat(), "skip": False})  # fmt: skip
        assert r.status_code == 200, r.text
        past = (day - timedelta(days=3)).isoformat()
        r = await client.post(f"{base}/skip", headers=owner, json={"day": past})
        assert r.status_code == 422 and r.json()["code"] == "invalid_flow", r.text

        until = day + timedelta(days=2)
        r = await client.post(f"{base}/pause", headers=owner, json={"until": until.isoformat()})
        assert r.status_code == 200 and r.json()["state"] == "paused", r.text
        assert r.json()["paused_until"] == until.isoformat()
        assert (await n8n_call(day))["order"] == ""
        assert await FL.clock(hub, FL.trigger_of(FL.FLOWS[key], day) + timedelta(minutes=1)) == []
        r = await client.post(f"{base}/state", headers=owner, json={"state": "on"})
        assert r.status_code == 200 and r.json()["state"] == "on", r.text
        assert r.json()["paused_until"] is None

        r = await client.post(f"{base}/run-now", headers=owner, json={"day": day.isoformat()})
        assert r.status_code == 422, r.text  # (Idempotency-Key)
        key1 = idem()
        r = await client.post(f"{base}/run-now", headers={**owner, **key1},
                              json={"day": day.isoformat()})  # fmt: skip
        assert r.status_code == 201, r.text
        run = r.json()["run"]
        assert run["ref"].startswith("F-")
        again = await client.post(f"{base}/run-now", headers={**owner, **key1},
                                  json={"day": day.isoformat()})  # fmt: skip
        assert again.json() == r.json()  # (the same key: the same answer)
        second = await client.post(f"{base}/run-now", headers={**owner, **idem()},
                                   json={"day": day.isoformat()})  # fmt: skip
        assert second.status_code == 409 and second.json()["code"] == "already_ran", second.text
        assert second.json()["run"]["ref"] == run["ref"]

        # the board's switch (1.2.0) writes the row's state; flows_off is not touched
        r = await client.post(f"/api/v1/automations/N8:{key}/state", headers=owner,
                              json={"state": "off"})  # fmt: skip
        assert r.status_code == 200 and r.json()["state"] == "off", r.text
        assert await su.fetchval("SELECT state FROM automations.flows WHERE ref = $1", ref) == "off"
        assert key not in (await su.fetchval("SELECT flows_off FROM owner.settings WHERE id = 1"))
        assert (await n8n_call(day + timedelta(days=1)))["why_fa"] == FL.OFF_WHY_FA
        # the owner's own run-now still runs it (a pilot is off for the clock, run by hand)
        r = await client.post(f"{base}/run-now", headers={**owner, **idem()},
                              json={"day": (day + timedelta(days=2)).isoformat()})  # fmt: skip
        assert r.status_code == 201, r.text
        actions = {
            r["action"]
            for r in await su.fetch("SELECT action FROM audit.entries WHERE target_ref = $1", ref)
        }
        assert {"automation.flow.skip", "automation.flow.pause", "automation.flow.state"} <= actions
        audit = await client.get(f"/api/v1/automations/N8:{key}/audit", headers=owner)
        assert audit.status_code == 200 and any(
            a["action"] == "automation.flow.state" for a in audit.json()
        ), audit.text
    finally:
        await all_off(su, key)


# ---------------------------------------------------------- the list, options --
async def test_the_list_and_the_options(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    co = await new_company()
    one, two, pilot = fk(), fk(), fk()
    await seed(su, monkeypatch, a_flow(co["code"], one), a_flow(co["code"], two),
               a_flow(co["code"], pilot, account="", n8n=""))  # fmt: skip
    try:
        # a flow no n8n workflow started (a pilot, run by hand) is seeded off: the clock skips it
        states = dict(await su.fetch(
            "SELECT key, state FROM automations.flows WHERE key = ANY($1::text[])", [one, pilot]))  # fmt: skip
        assert states == {one: "on", pilot: "off"}
        await all_off(su, two)
        r = await client.get(f"/api/v1/automations/flows?company={co['code']}", headers=owner)
        assert r.status_code == 200, r.text
        got = r.json()
        assert [i["key"] for i in got["items"]] == [one, two, pilot]  # (the off ones last)
        assert {"items", "health", "today"} <= set(got) and got["health"]
        item = got["items"][0]
        assert item["budget"]["usd_cap"] == 20 and item["budget"]["month_estimate_usd"] == 600
        assert item["today"] == {"runs": 0, "published": 0, "cost_usd": 0.0}
        r = await client.get("/api/v1/automations/flows/options", headers=owner)
        assert r.status_code == 200, r.text
        opts = r.json()
        assert {"id": OPUS, "name_fa": "Opus 5.5", "efforts": ["high", "xhigh", "max"]} in opts[
            "models"
        ]
        assert opts["usd_cap"] == {"min": 1, "max": 500} and opts["stories_max"] == 15
        assert opts["cycle_max"] == 7 and opts["note_max"] == 2000
        assert any(k["key"] == "p39-test" for k in opts["kits"])
        r = await client.get("/api/v1/automations/flows/AF-999999", headers=owner)
        assert r.status_code == 404, r.text
    finally:
        await all_off(su, one, two, pilot)


# ------------------------------------------------------------ owner and RLS --
async def test_the_routes_are_the_owners_and_a_company_sees_only_its_rows(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance 9."""
    a, b = await new_company(), await new_company()
    key = fk()
    ref = (await seed(su, monkeypatch, a_flow(b["code"], key)))[key]
    try:
        agent = await agent_headers(f"{b['code']}-CEO")
        for method, path, body in (
            ("GET", "/api/v1/automations/flows", None),
            ("GET", "/api/v1/automations/flows/options", None),
            ("GET", f"/api/v1/automations/flows/{ref}", None),
            ("PATCH", f"/api/v1/automations/flows/{ref}", {}),
            ("POST", f"/api/v1/automations/flows/{ref}/state", {"state": "off"}),
            ("POST", f"/api/v1/automations/flows/{ref}/run-now", {}),
        ):
            r = await client.request(method, path, headers={**agent, "If-Match": "1"}, json=body)
            assert r.status_code in (401, 403), (path, r.status_code)
        async with hub.db.tx([a["id"]]) as tx:
            assert not await tx.scalar(
                "SELECT count(*) FROM automations.flows WHERE company_id = :b", b=b["id"]
            )
            assert not await tx.scalar(
                "SELECT count(*) FROM automations.flow_versions WHERE company_id = :b", b=b["id"]
            )
        async with hub.db.tx([b["id"]]) as tx:
            assert await tx.scalar(
                "SELECT count(*) FROM automations.flows WHERE company_id = :b", b=b["id"]
            )
    finally:
        await all_off(su, key)


# ------------------------------------------------------ 39.1: cost, n8n, alerts --
async def test_a_day_past_its_cap_goes_on_with_an_alert_and_no_notice(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§1.5 of 39.1 (the owner, 2026-11-17): a run past `usd_cap` is never held: over_cap is always
    False, the day keeps no `budget_cap` in «منتظر شما», a `cap_reached` alert opens on the flow's
    page, and nobody is notified; a cap is one tap up and down, the budget has no envelope."""
    co = await new_company()
    key = fk()
    ref = (await seed(su, monkeypatch, a_flow(co["code"], key)))[key]
    day = tomorrow()
    try:
        r = await client.post(f"/api/v1/flows/{key}/run", headers={**owner, **idem()},
                              json={"day": day.isoformat()})  # fmt: skip
        assert r.status_code == 201, r.text
        order, work_ref = r.json()["order"], r.json()["work"]
        w = await su.fetchrow("SELECT id, company_id FROM work.work WHERE ref = $1", work_ref)
        await su.execute(
            """INSERT INTO llm.calls (id, started_at, finished_at, company_id, actor_ref, work_ref,
                   task_class, priority, caller, provider, model, cost_usd, equiv_cost_usd, status)
               VALUES (gen_random_uuid(), now(), now(), $1, 'X', $2, 'server_claude', 3,
                       'company_runner', 'anthropic', 'claude-opus-5-5', 0, 25, 'ok')""",
            w["company_id"], work_ref,
        )  # fmt: skip
        for _ in range(2):
            async with hub.db.tx(await hub.companies.ids()) as tx:
                assert await FL.over_cap(tx, w["id"]) is False
        alerts = await su.fetch(
            """SELECT a.kind, a.notified_at FROM automations.alerts a
               JOIN automations.flows f ON f.id = a.flow_id WHERE f.ref = $1 AND a.closed_at IS NULL""",
            ref,
        )
        assert [(x["kind"], x["notified_at"]) for x in alerts] == [("cap_reached", None)]
        assert not await su.fetchval(
            "SELECT count(*) FROM notify.notifications WHERE link_ref = ANY($1::text[])",
            [order, ref],
        )
        waiting = (await client.get("/api/v1/publications/waiting", headers=owner)).json()
        assert all(x["kind"] == "publish_ask" for x in waiting["items"])
        health = (await client.get(f"/api/v1/automations/flows/{ref}/health", headers=owner)).json()
        assert [a["kind"] for a in health["alerts"]] == ["cap_reached"] and health[
            "state"
        ] == "warn"
        page = (await client.get(f"/api/v1/automations/flows/{ref}", headers=owner)).json()
        assert page["budget"]["envelope_usd"] is None and page["budget"]["over_envelope"] is False
        assert page["alerts_open"] == 1
        for v, cap in ((1, 300), (2, 5)):
            r = await save(client, owner, ref, v, {"usd_cap": cap})
            assert r.status_code == 200 and r.json()["budget"]["usd_cap"] == cap, r.text
    finally:
        await all_off(su, key)


async def test_an_n8n_call_before_the_rows_hour_or_for_an_off_flow_makes_nothing(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§1 of 39.1: the per-flow workflows (flow-*.json) still call at their old hours; the row
    decides: before its build hour (two minutes' grace) or off, paused, a day skipped: 202
    `{started: false, reason}` and no order."""
    co = await new_company()
    key = fk()
    now = datetime.now(TZ)
    later = (now + timedelta(hours=3)).strftime("%H:%M")
    if (now + timedelta(hours=3)).date() != now.date():
        later = "23:59"
    ref = (await seed(su, monkeypatch, a_flow(co["code"], key, trigger_at=later,
                                              hours=("23:59",) * 4)))[key]  # fmt: skip
    secret = "test-n8n-secret-" + "z" * 16
    monkeypatch.setattr(hub, "secrets", replace(hub.secrets, n8n_secret=secret))
    today = now.date()

    async def call(day: date) -> httpx.Response:
        body = json.dumps({"day": day.isoformat()}, separators=(",", ":")).encode()
        return await client.post(
            f"/internal/v1/flows/{key}/run", content=body,
            headers={signing.HEADER: signing.sign(secret, body),
                     "Idempotency-Key": str(FL.n8n_key(key, day)), "Content-Type": "application/json"},
        )  # fmt: skip

    def made(day: date) -> Any:
        return su.fetchval(
            """SELECT count(*) FROM work.work WHERE run_meta -> 'flow' ->> 'key' = $1
                 AND run_meta -> 'flow' ->> 'day' = $2""",
            key, day.isoformat(),
        )  # fmt: skip

    try:
        if later != "23:59" or now.strftime("%H:%M") < "23:57":
            r = await call(today)
            assert r.status_code == 202 and r.json() == {
                "started": False,
                "reason": "before_trigger",
            }, r.text
            assert await made(today) == 0
        await su.execute("UPDATE automations.flows SET state = 'off' WHERE ref = $1", ref)
        r = await call(today)
        assert r.status_code == 202 and r.json() == {"started": False, "reason": "off"}, r.text
        await su.execute(
            "UPDATE automations.flows SET state = 'on', skips = ARRAY[$2::date] WHERE ref = $1",
            ref, today,
        )  # fmt: skip
        r = await call(today)
        assert r.status_code == 202 and r.json()["reason"] == "skipped", r.text
        assert await made(today) == 0
    finally:
        await all_off(su, key)


async def test_a_late_day_notifies_the_owner_once_after_an_hour_then_closes(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§61.6: a publish hour gone without its package is `late` (on the page only); an hour later
    with no run left, ONE notification; when the package goes out the alert closes by itself."""
    from hq_api.domain import flow_alerts as AL

    co = await new_company()
    key = fk()
    ref = (await seed(su, monkeypatch, a_flow(co["code"], key, hours=("14:00",) * 4)))[key]
    day = datetime.now(TZ).date()
    at = datetime.combine(day, datetime.min.time(), TZ).replace(hour=14)
    try:
        await AL.sweep(hub, at + timedelta(minutes=20))
        rows = await su.fetch(
            """SELECT a.* FROM automations.alerts a JOIN automations.flows f ON f.id = a.flow_id
               WHERE f.ref = $1 AND a.kind = 'late'""",
            ref,
        )
        assert len(rows) == 1 and rows[0]["notified_at"] is None and rows[0]["closed_at"] is None
        said = "SELECT count(*) FROM notify.notifications WHERE link_kind = 'automation' AND link_ref = $1"
        assert await su.fetchval(said, ref) == 0
        for minutes in (61, 75):
            await AL.sweep(hub, at + timedelta(minutes=minutes))
        assert await su.fetchval(said, ref) == 1
        title = await su.fetchval(
            "SELECT title_fa FROM notify.notifications WHERE link_kind = 'automation' AND link_ref = $1",
            ref,
        )
        assert "امروز منتشر نشد" in title
        # the day's package went out: closed by itself
        r = await client.post(f"/api/v1/flows/{key}/run", headers={**owner, **idem()},
                              json={"day": day.isoformat()})  # fmt: skip
        assert r.status_code == 201, r.text
        await su.execute(
            """UPDATE work.work SET run_meta = jsonb_set(run_meta, '{flow,sent}', to_jsonb(now()::text))
               WHERE ref = $1""",
            r.json()["work"],
        )
        await AL.sweep(hub, at + timedelta(minutes=80))
        row = await su.fetchrow(
            """SELECT a.closed_at, a.closed_fa FROM automations.alerts a
               JOIN automations.flows f ON f.id = a.flow_id WHERE f.ref = $1 AND a.kind = 'late'""",
            ref,
        )
        assert row["closed_at"] is not None and row["closed_fa"] == AL.CLOSED_SENT_FA
        assert await su.fetchval(said, ref) == 1
    finally:
        await all_off(su, key)


async def test_the_p2_pages_kits_a_new_automation_and_the_week(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§61.3, §61.5, §61.7: runs, graph, kits (and a kit's map), «بساز و روشن کن», «کیت تازه», the
    week; the options name the workshop runner's models, Fable 5.2 too."""
    from .test_w19_publish_time import connected

    ig, co = await new_company(), await new_company()
    await connected(client, hub, owner_session, ig, co["code"])
    key = fk()
    ref = (await seed(su, monkeypatch, a_flow(co["code"], key)))[key]
    made: list[str] = [key]
    try:
        r = await client.post(f"/api/v1/flows/{key}/run", headers={**owner, **idem()},
                              json={"day": tomorrow().isoformat()})  # fmt: skip
        assert r.status_code == 201, r.text
        runs = (await client.get(f"/api/v1/automations/flows/{ref}/runs", headers=owner)).json()
        assert [x["run"] for x in runs["items"]] == [r.json()["order"]] and runs["next"] is None
        assert runs["items"][0]["day"] == tomorrow().isoformat()
        g = (await client.get(f"/api/v1/automations/flows/{ref}/graph", headers=owner)).json()
        assert g["nodes"] and g["lanes"][0] == "n8n"
        opts = (await client.get("/api/v1/automations/flows/options", headers=owner)).json()
        assert {m["id"]: m["name_fa"] for m in opts["models"]} == {
            "claude-opus-5-5": "Opus 5.5", "claude-fable-5-2": "Fable 5.2"}  # fmt: skip
        kits = (await client.get("/api/v1/automations/kits", headers=owner)).json()
        assert any(k["key"] == "p39-test" for k in kits)
        r = await client.get("/api/v1/automations/kits/p39-test/graph", headers=owner)
        assert r.status_code == 200 and r.json()["nodes"], r.text
        assert (
            await client.get("/api/v1/automations/kits/none/graph", headers=owner)
        ).status_code == 404
        body = {"account": "pro.chart", "kit": "p39-test", "title_fa": "ریلز تازه‌ی آزمایشی",
                "schedule": {"hours": ["18:10"], "trigger_at": "11:00", "same_day": True},
                "model": "claude-fable-5-2", "effort": "xhigh", "usd_cap": 15}  # fmt: skip
        r = await client.post("/api/v1/automations/flows", headers={**owner, **idem()}, json=body)
        assert r.status_code == 201, r.text
        new = r.json()
        made.append(new["key"])
        assert new["state"] == "on" and new["version"] == 1 and new["model_fa"] == "Fable 5.2"
        assert new["account"] == "pro.chart" and new["kind"] == "reel"
        v1 = (
            await client.get(f"/api/v1/automations/flows/{new['ref']}/versions", headers=owner)
        ).json()
        assert v1[0]["note_fa"] == "ساخته شد از کیت p39-test"
        bad = {**body, "usd_cap": 0, "account": "nobody.page"}
        r = await client.post("/api/v1/automations/flows", headers={**owner, **idem()}, json=bad)
        assert r.status_code == 422 and r.json()["errors"][0]["field"] == "account", r.text
        r = await client.post("/api/v1/automations/kits/request", headers={**owner, **idem()},
                              json={"account": "pro.chart", "note_fa": "یک کیت استوری آموزشی"})  # fmt: skip
        assert r.status_code == 201 and r.json()["order"].startswith("F-"), r.text
        week = (await client.get("/api/v1/automations/week", headers=owner)).json()
        assert len(week["by_day"]) == 7 and {"runs", "published", "cost_usd"} <= set(week["totals"])
        assert any(a["account"] == f"p39.{key}" and a["flows"] == 1 for a in week["accounts"])
    finally:
        await all_off(su, *made)
