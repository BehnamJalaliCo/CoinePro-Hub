"""⟨2026-11-10⟩ Direct sessions, step 1 (the owner's decisions of 2026-11-10).

The owner: «این برو بیا و هی مهر بکن و اینو مجوز بده و بروکراسی اداری بازی توی شرکت آزار و اذیت
میده منو … مثل همین سشنی که من با تو صحبت میکنم». A hire he asked for in his own session is made
at once (no CEO card, no seal); the narrator of content is on (what he switched off is his own
voice talk with the app); a session is direct by default; a workshop turn takes hub files with
it (the narration into the reel).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx

from hq_api.domain import capabilities as CAP
from hq_api.domain import direct as DR
from hq_api.domain import hiring as HI
from hq_api.domain import order_turns as OT
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p17_runners import poll, take
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_w14_workshop import png, refuse_queued, run_ask, send_file, workshop


def hire(co: str, title: str = "سناریست") -> dict[str, Any]:
    return {
        "kind": "hire",
        "title": f"استخدام {title}",
        "payload": {
            "company": co,
            "department": "TECH",
            "role": "sre",
            "title_fa": title,
            "title_en": "Specialist",
            "reason": "the owner asked for it in the session",
            "model": "claude-sonnet-5-5",
            "effort": "low",
            "quota_estimate_month": {"tokens": 2_000_000},
        },
    }


async def set_hiring(su: Any, state: str) -> None:
    await su.execute(
        """INSERT INTO core.hiring (company_id, state, mode)
           SELECT id, $1, CASE WHEN $1 = 'open' THEN 'proposals' END FROM core.companies
           WHERE kind = 'holding'
           ON CONFLICT (company_id) DO UPDATE SET state = EXCLUDED.state, mode = EXCLUDED.mode""",
        state,
    )


async def test_a_hire_the_owner_asked_for_in_his_session_is_made_at_once(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    await set_hiring(su, "closed")  # even with hiring closed: his word in his session opens it
    try:
        # a session whose order says nothing of a hire: the old rule holds
        plain = await post_order(
            client, owner, f"برای {co} {words()} وضع کامل شرکت را بررسی کن و گزارش بده"
        )
        [route] = plain["routes"]
        holder = route["to"]
        wid = str(await su.fetchval("SELECT id FROM work.work WHERE ref = $1", route["work_ref"]))
        r = await client.post(
            "/internal/v1/decisions",
            headers={**(await agent_headers(holder)), **idem()},
            json={**hire(co), "work_id": wid},
        )
        assert r.status_code == 403 and r.json()["code"] == "hiring_closed", r.text

        # he says it in the session («استخدام»): the hire is his decision already
        r = await client.post(
            f"/api/v1/orders/{plain['ref']}/reply",
            headers={**owner, **idem()},
            json={"text": "یک سناریست استخدام کن که هر روز متن بنویسد"},
        )
        assert r.status_code == 200, r.text
        before = await su.fetchval(
            "SELECT count(*) FROM core.employees e JOIN core.companies c ON c.id = e.company_id "
            "WHERE c.code = $1 AND e.status = 'active'",
            co,
        )
        r = await client.post(
            "/internal/v1/decisions",
            headers={**(await agent_headers(holder)), **idem()},
            json={**hire(co), "work_id": wid},
        )
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["status"] == "approved" and d["approver"] is None, d
        row = await su.fetchrow(
            "SELECT decided_by_kind, note, seal_at FROM cartable.decisions WHERE ref = $1", d["ref"]
        )
        assert row["decided_by_kind"] == "service" and plain["ref"] in row["note"]
        assert row["seal_at"] is None  # no fingerprint of his was asked for
        after = await su.fetchval(
            "SELECT count(*) FROM core.employees e JOIN core.companies c ON c.id = e.company_id "
            "WHERE c.code = $1 AND e.status = 'active'",
            co,
        )
        assert after == before + 1
        # no card waits for anyone, and the session says who came
        rep = (await client.get(f"/api/v1/orders/{plain['ref']}/report", headers=owner)).json()
        assert rep["cards"] == []
        assert any("استخدام شد و به همین جلسه آمد" in s["what_fa"] for s in rep["steps"]), rep[
            "steps"
        ]
        assert any(p["key"].startswith("sre@") for p in rep["participants"]), rep["participants"]
        # an agent of another company, or outside any session, gets nothing from his word
        other = (await new_company())["code"]
        r = await client.post(
            "/internal/v1/decisions",
            headers={**(await agent_headers(f"{other}-CEO")), **idem()},
            json=hire(other),
        )
        assert r.status_code == 403 and r.json()["code"] == "hiring_closed", r.text
    finally:
        await set_hiring(su, "open")


def test_the_owners_dont_hire_is_never_read_as_a_hire() -> None:
    for said in (
        ["یک سناریست استخدام کن"],
        ["Hire a writer"],
        ["کار را شروع کن", "۲. استخدام طراح"],
    ):
        assert HI.asks_for_a_hire(said), said
    for said in (
        ["کسی را استخدام نکن، خودت بساز"],
        ["استخدام\u200cنکنید"],
        ["بدون استخدام جلو برو"],
        ["نیازی به استخدام نیست"],
        ["هیچ کس استخدام نشود"],
        ["Do not hire anyone"],
        ["ریلز را بساز"],
    ):
        assert not HI.asks_for_a_hire(said), said
    # a «نه» of before and a «بله» of now: his later plain word asks for one
    assert HI.asks_for_a_hire(["استخدام نکن", "حالا یک طراح استخدام کن"])


async def test_the_narrator_is_on_and_a_session_is_direct(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    lib = hub.charters
    for role in ("media_director", "video_director", "motion_designer", "scriptwriter"):
        assert "speech.make" in lib.roles[role].tools, role
        assert "workshop.stop" in lib.roles[role].tools, role
    common = (lib.common if hasattr(lib, "common") else "") or ""
    async with hub.db.tx(await hub.companies.ids()) as tx:
        brief = await CAP.brief(tx, co["id"], n8n_up=True)
    assert brief["narration"]["tool"] == "speech.make"
    assert brief["narration"]["state"] in ("signed_in", "signed_out", "unknown")
    assert "speech.make" in brief["how"]["narration"] and "files" in brief["how"]["narration"]
    assert "voice is off" not in brief["how"]["video"]
    assert "voice" not in brief  # his own voice talk with the app is still never mentioned
    del common
    out = await post_order(
        client, owner, f"برای {co['code']} {words()} وضع کامل شرکت را بررسی کن و گزارش بده"
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        held = await OT.talk_brief(tx, out["ref"])
        workshop = await DR.server_for(tx) is not None
    # ⟨2026-11-11⟩ direct only when the workshop can hold a direct turn now (runner >= 0.3.5)
    assert held is not None and held["direct"] is workshop
    assert ("direct_rule" in held) is workshop
    assert "do not raise a card" in OT.DIRECT_RULE and "workshop" in OT.DIRECT_RULE
    assert "`queued`" in held["async_rule"]
    assert "step_rule" not in held  # a general order: only «با من» carries the step rule


async def test_a_workshop_turn_takes_hub_files_with_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    """The narration (or a logo) goes into the reel: `workshop.run files` → the job's `inputs`,
    fetched by that job's own runner; a file of another company is refused."""
    co = (await new_company())["code"]
    rn = await workshop(client, hub, owner_session, su)
    out = await post_order(
        client, owner, f"برای {co} {words()} وضع کامل شرکت را بررسی کن و گزارش بده"
    )
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)
    r = await run_ask(client, holder, {"work": work_ref, "brief": "یک کاور بساز"})
    assert r.status_code == 201, r.text
    job = await take(client, rn)
    assert "inputs" not in job["args"]
    r = await send_file(client, rn, job["id"], "voice.png", "image/png", png())
    assert r.status_code == 201, r.text
    made = r.json()["id"]
    await refuse_queued(su, str(wid))
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "تمام شد.",
              "data": {"session_id": "cs-in-1", "result_fa": "ساخته شد.", "files": [made]}},
        headers=rn["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text

    # a file of some other company is not this work's to take
    other = await new_company()
    foreign = await su.fetchval(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key, variant,
               created_by_kind, created_by_code)
           SELECT $1, 'x.png', 'image/png', size, repeat('a', 64), storage_key || '.other',
                  'original', 'owner', 'owner' FROM files.files WHERE id = $2 RETURNING id""",
        other["id"],
        uuid.UUID(made),
    )
    r = await run_ask(
        client,
        holder,
        {"work": work_ref, "brief": "ریلز را با این فایل بساز", "files": [str(foreign)]},
    )
    assert r.status_code == 422 and "files" in r.json()["fields"], r.text

    # a runner that cannot take input files (< 0.3.3) is not sent a turn that needs them: the
    # agent reads why at once, in place of a reel made silent again
    r = await run_ask(
        client, holder, {"work": work_ref, "brief": "ریلز را با این فایل بساز", "files": [made]}
    )
    assert r.status_code == 409 and r.json()["code"] == "workshop_unavailable", r.text
    assert "input files" in r.json()["fields"]["files"]
    rn["h"] = {**rn["h"], "X-HQ-Runner-Version": "0.3.4"}
    assert (await poll(client, rn)).status_code in (200, 204)  # the runner was updated

    r = await run_ask(
        client, holder, {"work": work_ref, "brief": "ریلز را با این فایل بساز", "files": [made]}
    )
    assert r.status_code == 201, r.text
    nxt = await take(client, rn)
    [inp] = nxt["args"]["inputs"]
    assert inp["file_id"] == made and inp["name"] == "voice.png" and inp["mime"] == "image/png"
    assert inp["url"] == f"/api/v1/runners/jobs/{nxt['id']}/inputs/{made}"
    assert "in/voice.png" in nxt["args"]["brief"]
    got = await client.get(inp["url"], headers=rn["h"])
    assert got.status_code == 200 and got.content[:8] == b"\x89PNG\r\n\x1a\n"
    # only what the job names, only for that job's runner
    bad = await client.get(f"/api/v1/runners/jobs/{nxt['id']}/inputs/{foreign}", headers=rn["h"])
    assert bad.status_code == 404, bad.text
    assert (await client.get(inp["url"])).status_code in (401, 403)


async def test_a_workshop_turn_asks_for_the_wall_and_says_when_it_ran_without(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    """§43.9: every workshop turn asks its runner for the wall between companies (`sandbox:
    auto`); a runner that could not put it up still does the work, and that is written where
    the holding's technical team reads (never a blocker, never the owner's)."""
    co = (await new_company())["code"]
    rn = await workshop(client, hub, owner_session, su)
    out = await post_order(
        client, owner, f"برای {co} {words()} وضع کامل شرکت را بررسی کن و گزارش بده"
    )
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)

    async def a_turn(session: str, box: dict[str, Any] | None) -> dict[str, Any]:
        r = await run_ask(client, holder, {"work": work_ref, "brief": f"بساز {session}"})
        assert r.status_code == 201, r.text
        job = await take(client, rn)
        assert job["args"]["sandbox"] == "auto" and job["args"]["hands"] is True
        await refuse_queued(su, str(wid))
        data = {"session_id": session, "result_fa": f"ساخته شد {session}."}
        r = await client.post(
            f"/api/v1/runners/jobs/{job['id']}/result",
            json={"exit_code": 0, "summary_fa": "تمام شد.",
                  "data": data | ({"sandbox": box} if box else {})},
            headers=rn["h"],
        )  # fmt: skip
        assert r.status_code == 200, r.text
        return job

    async def last_output() -> dict[str, Any]:
        raw = await su.fetchval(
            """SELECT produced_with FROM cartable.deliverables WHERE work_id = $1
               ORDER BY created_at DESC LIMIT 1""",
            wid,
        )
        return json.loads(raw) if isinstance(raw, str) else dict(raw or {})

    async def said_off() -> int:
        return int(
            await su.fetchval(
                """SELECT count(*) FROM audit.entries
                   WHERE action = 'workshop.sandbox_off' AND target_ref = $1""",
                work_ref,
            )
        )

    await a_turn("cs-wall-1", {"state": "on", "kind": "landlock"})
    assert (await last_output())["sandbox"] == "on" and await said_off() == 0
    await a_turn("cs-wall-2", {"state": "off", "why": "this kernel has no Landlock"})
    assert (await last_output())["sandbox"] == "off" and await said_off() == 1
    summary = await su.fetchval(
        "SELECT summary FROM audit.entries WHERE action = 'workshop.sandbox_off' AND target_ref = $1",
        work_ref,
    )
    assert "no Landlock" in summary
    # a runner that does not know the wall yet (< 0.3.4) says nothing, and nothing is claimed
    await a_turn("cs-wall-3", None)
    assert "sandbox" not in await last_output() and await said_off() == 1
    # the session itself reads no blocker and no line about it
    rep = (await client.get(f"/api/v1/orders/{out['ref']}/report", headers=owner)).json()
    assert rep["blockers"] == [] and "sandbox" not in json.dumps(rep, ensure_ascii=False).lower()
