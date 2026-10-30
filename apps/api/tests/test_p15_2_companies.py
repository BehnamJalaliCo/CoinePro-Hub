"""Prompt 15.2: delete a company made by mistake, the simple founding, read
many notifications, one finding per key, and the stream's longer topics
(contract §25 ⟨1.7.5⟩)."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api import events
from hq_api.domain import founding as F
from hq_api.domain import oversight as O
from hq_api.errors import ApiError
from hq_api.hub import Hub

from .conftest import idem, step_up
from .test_brand import mono, put_file
from .test_control_treasury_stream import serve
from .test_notifications import raise_
from .test_stream_topics import _first_comment

pytestmark = pytest.mark.usefixtures("relay")
API = "/api/v1"


def code_() -> str:
    return "Z" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXY") for _ in range(4))


async def blank(
    client: httpx.AsyncClient, h: dict[str, str], code: str, **more: Any
) -> httpx.Response:
    return await client.post(
        f"{API}/foundings",
        headers={**h, **idem()},
        json={"source": {"kind": "blank"}, "name_fa": "شرکت اشتباهی", "code": code, **more},
    )


# ------------------------------------------------------- simple founding --
async def test_a_blank_founding_registers_a_draft_company(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any
) -> None:
    h = owner_session["headers"]
    code = code_()
    r = await client.post(
        f"{API}/foundings", headers={**h, **idem()}, json={"source": {"kind": "blank"}}
    )
    assert r.status_code == 422  # a name and a code are needed
    # A colour slot is one company's: a taken one is refused up front.
    taken = await su.fetchval(
        "SELECT color_index FROM core.companies WHERE color_index IS NOT NULL LIMIT 1"
    )
    if taken:
        r = await blank(client, h, code, color_index=taken)
        assert r.status_code == 409 and "color_index" in r.json()["fields"]
    free = await su.fetchval(
        """SELECT min(s) FROM generate_series(1, 8) s
           WHERE s NOT IN (SELECT color_index FROM core.companies WHERE color_index IS NOT NULL)"""
    )
    r = await blank(client, h, code, tagline="فقط ثبت", color_index=free)
    assert r.status_code == 201, r.text
    f = r.json()
    assert (f["state"], f["company"], f["code"], f["name_fa"]) == (
        "sealed",
        code,
        code,
        "شرکت اشتباهی",
    )
    assert (f["tagline"], f["color_index"], f["audit_work"], f["proposal_work"]) == (
        "فقط ثبت", free, None, None,
    )  # fmt: skip
    co = (await client.get(f"{API}/companies/{code}", headers=h)).json()
    assert (co["status"], co["color_index"]) == ("draft", free)
    assert co["counts"]["employees_active"] > 0  # the standard template's seats
    drafts = (await client.get(f"{API}/companies?status=draft", headers=h)).json()
    assert code in {c["code"] for c in drafts}
    # The code is taken: by the company, and by an open founding.
    again = await blank(client, h, code)
    assert again.status_code == 409 and again.json()["code"] == "code_taken"
    other = code_()
    idea = await client.post(
        f"{API}/foundings",
        headers={**h, **idem()},
        json={"source": {"kind": "idea", "brief_md": "یک ایده"}, "name_fa": "نو", "code": other},
    )
    assert idea.status_code == 201, idea.text
    assert (await blank(client, h, other)).json()["code"] == "code_taken"
    # The proposer is told to keep the owner's name and code ...
    brief = await su.fetchval(
        "SELECT brief FROM work.work WHERE ref = $1", idea.json()["proposal_work"]
    )
    assert f"the code {other}" in brief and "keep them exactly" in brief
    # ... and a card with another code is refused.
    holding = await hub.companies.holding()
    payload = {"founding": idea.json()["ref"], "code": code_(), "name_fa": "نو", "departments": []}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        with pytest.raises(ApiError) as e:
            await F.check_proposal(tx, payload, holding.id)
    assert e.value.fields == {"payload.code": f"the owner chose {other}"}


async def test_a_founding_logo_becomes_the_brand(
    client: httpx.AsyncClient, owner_session: dict[str, Any], su: Any
) -> None:
    h = owner_session["headers"]
    bad = await blank(client, h, code_(), logo_file_id="00000000-0000-0000-0000-000000000001")
    assert bad.status_code == 422
    file_id = (await put_file(client, h, mono(), "image/png", "logo.png")).json()["id"]
    code = code_()
    r = await blank(client, h, code, logo_file_id=file_id)
    assert r.status_code == 201, r.text
    v = await su.fetchrow(
        """SELECT b.state, b.part, b.file_id FROM org.company_brands b
           JOIN core.companies c ON c.id = b.company_id WHERE c.code = $1""",
        code,
    )
    assert (v["state"], v["part"], str(v["file_id"])) == ("processing", "mark", file_id)
    moved = await su.fetchval(
        "SELECT c.code FROM files.files f JOIN core.companies c ON c.id = f.company_id WHERE f.id = $1",
        v["file_id"],
    )
    assert moved == code  # the logo is the company's now


# ------------------------------------------------------- delete a company --
async def test_a_company_without_history_is_deleted(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    code = code_()
    assert (await blank(client, h, code)).status_code == 201
    co_id = await su.fetchval("SELECT id FROM core.companies WHERE code = $1", code)
    # An order queued to its CEO (not done) is no history.
    r = await client.post(
        f"{API}/work",
        headers={**h, **idem()},
        json={"company": code, "title": "کار اشتباهی", "brief": "x", "priority": "P3"},
    )
    assert r.status_code == 201, r.text
    audited = await su.fetchval("SELECT count(*) FROM audit.entries WHERE company_id = $1", co_id)
    assert audited > 0
    key = idem()
    r = await client.delete(f"{API}/companies/{code}", headers={**h, **key})
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    tok = await step_up(hub, sid, "company.delete", code)
    r = await client.delete(f"{API}/companies/{code}", headers={**h, **tok, **key})
    assert r.status_code == 204, r.text
    assert not await su.fetchval("SELECT 1 FROM core.companies WHERE code = $1", code)
    for table in ("core.employees", "core.departments", "work.work", "core.foundings"):
        col = "new_company_id" if table == "core.foundings" else "company_id"
        n = await su.fetchval(f"SELECT count(*) FROM {table} WHERE {col} = $1", co_id)
        assert n == 0, table
    # Its audit rows stay; the deletion itself is audited on the holding.
    kept = await su.fetchval("SELECT count(*) FROM audit.entries WHERE company_id = $1", co_id)
    assert kept == audited
    row = await su.fetchrow(
        """SELECT a.summary, a.step_up, c.kind FROM audit.entries a JOIN core.companies c
           ON c.id = a.company_id WHERE a.action = 'company.delete' AND a.target_ref = $1""",
        code,
    )
    assert row["kind"] == "holding" and row["step_up"] and "شرکت اشتباهی (draft)" in row["summary"]
    removed = await su.fetchval(
        """SELECT data -> 'removed' ->> 'work.work' FROM owner.interactions
           WHERE action = 'company.delete' AND target_ref = $1""",
        code,
    )
    assert removed == "1"
    assert (await su.fetchrow("SELECT ok FROM audit.verify_chain()"))["ok"]
    # The same request again is a replay; the code is free again.
    again = await client.delete(f"{API}/companies/{code}", headers={**h, **tok, **key})
    assert again.status_code == 204 and again.headers.get("idempotent-replay") == "true"
    assert (await client.get(f"{API}/companies/{code}", headers=h)).status_code == 404
    assert (await blank(client, h, code)).status_code == 201


async def test_history_the_holding_and_unknown_codes_are_kept(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    co = await new_company()
    await su.execute(
        """INSERT INTO llm.usage (company_id, scope_type, scope_ref, period, period_start, calls,
               tokens, usd) VALUES ($1, 'company', $2, 'day', current_date, 1, 900, 0.01)""",
        co["id"],
        co["code"],
    )
    tok = await step_up(hub, sid, "company.delete", co["code"])
    r = await client.delete(f"{API}/companies/{co['code']}", headers={**h, **tok, **idem()})
    assert r.status_code == 409 and r.json()["code"] == "company_has_history", r.text
    assert r.json()["fields"] == {"history": ["treasury"]}
    assert await su.fetchval("SELECT 1 FROM core.companies WHERE id = $1", co["id"])
    holding = await hub.companies.holding()
    r = await client.delete(f"{API}/companies/{holding.code}", headers={**h, **idem()})
    assert r.status_code == 422
    r = await client.delete(f"{API}/companies/QQQQQQQQ", headers={**h, **idem()})
    assert r.status_code == 404
    r = await client.delete(f"{API}/companies/{co['code']}", headers=h)
    assert r.status_code == 422  # Idempotency-Key is required
    # Nothing but the purge may delete from an append-only table.
    with pytest.raises(Exception, match="append-only"):
        await su.execute("DELETE FROM control.kill_switches WHERE company_id = $1", co["id"])


# ---------------------------------------------------------- notifications --
async def test_many_notifications_read_in_one_request(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    ids = [str((await raise_(hub, co, "report", title_fa=f"گزارش {i}"))["id"]) for i in range(3)]
    r = await client.post(f"{API}/notifications/read", headers=owner, json={"ids": ids[:2] * 2})
    assert r.status_code == 200 and r.json() == {"updated": 2}
    r = await client.post(f"{API}/notifications/read", headers=owner, json={"ids": ids})
    assert r.json() == {"updated": 1}  # the read ones are skipped
    assert (
        await client.post(f"{API}/notifications/read", headers=owner, json={"ids": []})
    ).status_code == 422


# --------------------------------------------------------------- findings --
async def test_one_open_finding_per_key_updated_not_raised_again(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()

    async def find(sev: str, note: str) -> tuple[dict[str, Any], bool]:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            return await O.raise_finding(
                tx,
                company_id=co["id"],
                company_code=co["code"],
                severity=sev,
                title_fa="سلامت",
                body_md=note,
                evidence=[{"kind": "metric", "ref": "health", "note": note}],
                dedupe_key="PR-062:hub",
            )

    def notices() -> Any:
        return su.fetchval(
            "SELECT count(*) FROM notify.notifications WHERE company_id = $1 AND link_kind = 'finding'",
            co["id"],
        )

    first, created = await find("high", "disk 81%")
    assert created and await notices() == 1
    again, created = await find("high", "disk 84%")
    assert not created and again["ref"] == first["ref"] and await notices() == 1
    assert again["evidence"][0]["note"] == "disk 84%"
    lower, created = await find("medium", "disk 82%")
    assert not created and lower["ref"] == first["ref"]
    worse, created = await find("critical", "disk 93%")
    assert created and worse["ref"] != first["ref"] and await notices() == 2
    same, created = await find("high", "disk 89%")
    assert not created and same["ref"] == worse["ref"]  # the newest one is brought up to date
    level = await su.fetchval(
        "SELECT level FROM notify.notifications WHERE link_ref = $1", worse["ref"]
    )
    assert level == "report"  # its CEO answers it: no decision of the owner


def test_a_finding_an_employee_answers_is_a_report() -> None:
    assert O.notice_level({"answerable_kind": "agent"}) == "report"
    assert O.notice_level({"answerable_kind": "owner"}) == "decision"


# ----------------------------------------------------------------- stream --
async def test_all_topics_and_a_long_topic_list(app: Any, owner: dict[str, str]) -> None:
    every = ",".join(events.TOPICS)
    async with serve(app) as url:
        assert await _first_comment(url, owner, "all") == f": topics {every}"
        long = ",".join([*events.TOPICS, *(f"newer_{a}{b}" for a in "abcde" for b in "abcdefgh")])
        assert 200 < len(long) <= 1000
        assert await _first_comment(url, owner, long) == f": topics {every}"
