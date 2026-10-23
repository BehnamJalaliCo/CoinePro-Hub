"""Prompt 12 §9.1 (contract §21.13): the substitute players on the bench.
CI uses fake CLI results (the dispatcher's done body) and a fake egress for
the web path; nothing reaches ChatGPT, Gemini or DeepSeek, and no sign-in is
ever made."""

from __future__ import annotations

import base64
import io
import json
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from hq_api.domain import advisor as A
from hq_api.domain import creative_overlay as O
from hq_api.domain import substitutes as S
from hq_api.hub import Hub

from .conftest import agent_headers, body_bytes, idem, step_up, substitutes_headers
from .p10_fakes import holding_switch
from .test_p12a_advisor import _end_test_runs  # noqa: F401 - an autouse fixture here too


@asynccontextmanager
async def bench(su: Any, hub: Hub, *, cli: tuple[str, ...] = (), web: tuple[str, ...] = (),
                wait_s: int = 0) -> AsyncIterator[None]:  # fmt: skip
    """Players signed in for the block (the owner's sign-in, simulated in the
    test database), nothing else queued, the holding unlocked; then signed out
    and off again, as they are on the hub."""
    await su.execute(
        """UPDATE substitutes.calls SET state = 'skipped', state_reason = 'test', finished_at = now()
           WHERE state IN ('queued', 'running')"""
    )
    await su.execute(
        """UPDATE substitutes.players SET login_state = CASE WHEN player = ANY($1::text[]) THEN 'signed_in'
                                                             ELSE 'signed_out' END,
               status = CASE WHEN player = ANY($1::text[]) THEN 'ready' ELSE 'off' END,
               web_state = CASE WHEN player = ANY($2::text[]) THEN 'signed_in' ELSE 'signed_out' END,
               limited_until = NULL, web_last_job_at = NULL, web_last_failure = NULL""",
        list(cli),
        list(web),
    )
    saved = hub.settings
    hub.settings = replace(saved, substitute_wait_s=wait_s)
    try:
        async with holding_switch(su, "released"):
            yield
    finally:
        hub.settings = saved
        await su.execute(
            """UPDATE substitutes.players SET login_state = 'signed_out', status = 'off', web_state = 'signed_out',
                   limited_until = NULL, status_reason = NULL, web_last_failure = NULL"""
        )
        await restore_seats(su)


async def restore_seats(su: Any) -> None:
    """The table's caps again (a test widened one)."""
    for player, seats in S.DEFAULT_SEATS.items():
        for s in seats:
            await su.execute(
                "UPDATE substitutes.seats SET per_day = $3, enabled = $4 WHERE player = $1 AND seat = $2",
                player, s["seat"], s["per_day"], s["enabled"],
            )  # fmt: skip


async def per_day(su: Any, player: str, seat: str, room: int) -> None:
    """The seat's daily cap = what it used today + `room` (the database outlives a run)."""
    used = await su.fetchval(
        """SELECT count(*) FROM substitutes.calls WHERE player = $1 AND seat = $2 AND kind = 'call'
             AND day = (now() AT TIME ZONE 'Asia/Tehran')::date AND state IN ('queued', 'running', 'done')""",
        player,
        seat,
    )
    await su.execute(
        "UPDATE substitutes.seats SET per_day = $3, enabled = true WHERE player = $1 AND seat = $2",
        player,
        seat,
        int(used) + room,
    )


async def claim(client: httpx.AsyncClient) -> dict[str, Any]:
    r = await client.post("/internal/v1/substitutes/jobs/claim", headers=substitutes_headers())
    assert r.status_code == 200, r.text
    return dict(r.json())


async def done(client: httpx.AsyncClient, job: str, **body: Any) -> httpx.Response:
    return await client.post(
        f"/internal/v1/substitutes/jobs/{job}/done", headers=substitutes_headers(), json=body
    )


async def test_the_players_are_seeded_signed_out_and_off_with_the_tables_seats(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    await restore_seats(su)
    r = await client.get("/api/v1/substitutes", headers=owner)
    assert r.status_code == 200, r.text
    players = {p["player"]: p for p in r.json()}
    assert set(players) == {"gpt", "gemini", "deepseek"}
    for p in players.values():
        assert p["login"]["state"] == "signed_out" and p["status"] == "off"
        assert p["web"]["state"] == "signed_out"
    gpt = {s["seat"]: s for s in players["gpt"]["seats"]}
    assert (gpt["advisor_second_opinion"]["per_day"], gpt["code_review"]["per_day"]) == (3, 10)
    assert gpt["assistant_errand"]["model"] == "gpt-5.3" and gpt["creative"]["via"] == "web"
    gem = {s["seat"]: s for s in players["gemini"]["seats"]}
    assert gem["code_review"]["enabled"] is False and gem["creative"]["per_day_video"] == 3
    ds = {s["seat"]: s for s in players["deepseek"]["seats"]}
    assert set(ds) == {"quick_search", "third_opinion"} and all(
        s["via"] == "web" for s in ds.values()
    )
    assert (
        players["deepseek"]["runner"] is None
        and players["deepseek"]["month"]["value_ratio"] is None
    )
    assert players["gpt"]["month"]["price_usd"] == "20.00"
    conns = {c["key"]: c for c in (await client.get("/api/v1/connections", headers=owner)).json()}
    for key in ("chatgpt-plus", "gemini-pro", "deepseek-free"):
        assert conns[key]["kind"] == "subscription" and conns[key]["status"] == "disabled"


async def test_a_fake_cli_answers_and_a_spent_quota_makes_the_player_limited_never_claude(
    client: httpx.AsyncClient, hub: Hub, su: Any
) -> None:
    pa = await agent_headers("HQ-PA")
    async with bench(su, hub, cli=("gpt",)):
        await per_day(su, "gpt", "assistant_errand", 5)
        r = await client.post(
            "/internal/v1/substitutes/call", headers=pa,
            json={"seat": "assistant_errand", "input_md": "این متن را خلاصه کن: گزارش هفته خوب بود."},
        )  # fmt: skip
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "queued"
        call = r.json()["call"]
        job = (await claim(client))["job"]
        assert job["id"] == call and job["runner"] == "codex_cli" and job["model"] == "gpt-5.3"
        assert "گزارش هفته" in job["input_md"] and job["kind"] == "call"
        assert (await claim(client))["job"] is None  # one at a time for both players
        ok = await done(client, call, ok=True, text_md="خلاصه: هفته‌ی خوب.",
                        usage={"input_tokens": 40, "output_tokens": 12, "estimated": False})  # fmt: skip
        assert ok.status_code == 200 and ok.json()["state"] == "done", ok.text
        row = await su.fetchrow("SELECT * FROM substitutes.calls WHERE id = $1::uuid", call)
        assert row["input_md"] is None and json.loads(row["result"])["source"]["player"] == "gpt"
        ledger = await su.fetchrow(
            "SELECT caller, task_class, input_tokens, meta FROM llm.calls WHERE meta->>'substitute_call' = $1",
            call,
        )
        assert (ledger["caller"], ledger["task_class"], ledger["input_tokens"]) == (
            "substitutes",
            "sub_errand",
            40,
        )
        # The answer that came after `queued` goes back to the assistant as work.
        reply = await su.fetchrow(
            """SELECT w.brief, e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
               JOIN substitutes.calls c ON c.reply_work_id = w.id WHERE c.id = $1::uuid""",
            call,
        )
        assert reply["code"] == "HQ-PA" and "never evidence" in reply["brief"]
        # A spent quota: the player is limited, the seat skipped, nothing moves to Claude.
        r2 = await client.post(
            "/internal/v1/substitutes/call", headers=pa,
            json={"seat": "assistant_errand", "input_md": "یک پیش‌نویس ایمیل بنویس."},
        )  # fmt: skip
        job2 = (await claim(client))["job"]
        runs_before = await su.fetchval("SELECT count(*) FROM agents.runs")
        lim = await done(client, job2["id"], ok=False, error="limited",
                         limited_until=(datetime.now(UTC) + timedelta(hours=3)).isoformat())  # fmt: skip
        assert lim.json()["state"] == "skipped"
        p = await su.fetchrow(
            "SELECT status, limited_until FROM substitutes.players WHERE player = 'gpt'"
        )
        assert p["status"] == "limited" and p["limited_until"] > datetime.now(UTC)
        r3 = await client.post(
            "/internal/v1/substitutes/call", headers=pa,
            json={"seat": "assistant_errand", "input_md": "یکی دیگر."},
        )  # fmt: skip
        assert r3.status_code == 429 and r3.json()["code"] == "rate_limited", r3.text
        assert (
            await su.fetchval(
                "SELECT count(*) FROM llm.calls WHERE meta->>'substitute_call' = $1", job2["id"]
            )
            == 0
        )
        # The only run woken is the assistant's own reply work (never a Claude seat).
        assert await su.fetchval("SELECT count(*) FROM agents.runs") - runs_before <= 1
        assert r2.status_code == 200


async def test_customer_data_or_an_internal_name_never_reaches_a_substitute(
    client: httpx.AsyncClient, hub: Hub, su: Any
) -> None:
    pa, adv = await agent_headers("HQ-PA"), await agent_headers("HQ-ADV")
    async with bench(su, hub, cli=("gpt",), web=("deepseek",)):
        for text in ("به ali.rezaei@example.com ایمیل بزن", "شماره‌ی مشتری ۰۹۱۲۳۴۵۶۷۸۹ است",
                     "the key is sk-ant-api03-" + "x" * 40):  # fmt: skip
            r = await client.post("/internal/v1/substitutes/call", headers=pa,
                                  json={"seat": "assistant_errand", "input_md": text})  # fmt: skip
            assert r.status_code == 403 and r.json()["code"] == "policy_denied", (text, r.text)
        for q in ("قیمت امروز بیت‌کوین D-000123", "TY-CEO چه گفت", "بازار فارکس امروز HQ-ADV"):
            r = await client.post("/internal/v1/substitutes/call", headers=adv,
                                  json={"seat": "quick_search", "input_md": q})  # fmt: skip
            assert r.status_code == 403 and r.json()["code"] == "policy_denied", (q, r.text)
        ok = await client.post("/internal/v1/substitutes/call", headers=adv,
                               json={"seat": "quick_search", "input_md": "نرخ تورم آمریکا در ماه گذشته"})  # fmt: skip
        assert ok.status_code == 200 and ok.json()["state"] == "queued", ok.text
        # A seat the role may not use.
        ceo = await client.post("/internal/v1/substitutes/call", headers=await agent_headers("HQ-ADV"),
                                json={"seat": "creative", "kind": "image", "placement": "banner",
                                      "input_md": "تصویر"})  # fmt: skip
        assert ceo.status_code == 403
        # Repository code only in code_review.
        bad = await client.post("/internal/v1/substitutes/call", headers=adv,
                                json={"seat": "long_read", "input_md": "x", "repo": "coinepro-hub",
                                      "head_sha": "a" * 40})  # fmt: skip
        assert bad.status_code == 422


async def test_the_second_and_third_opinions_never_see_the_memo_and_agrees_is_code(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    from .test_p12a_advisor import _card, _memo_body

    co = (await new_company())["code"]
    async with bench(su, hub, cli=("gpt",), web=("deepseek",)):
        await per_day(su, "gpt", "advisor_second_opinion", 1)
        await per_day(su, "deepseek", "third_opinion", 5)
        ref = await _card(client, co, risk="low")
        memo = (await client.post(f"/api/v1/decisions/{ref}/memo", headers=owner, json={})).json()
        calls = {
            r["seat"]: r
            for r in await su.fetch(
                "SELECT * FROM substitutes.calls WHERE purpose_kind = 'memo' AND purpose_ref = $1",
                memo["ref"],
            )
        }
        assert set(calls) == {"advisor_second_opinion", "third_opinion"}
        facts = await su.fetchval("SELECT facts FROM advisor.memos WHERE ref = $1", memo["ref"])
        for c in calls.values():
            assert c["state"] == "queued"
            assert (
                ref in c["input_md"]
                and "against" not in c["input_md"]
                and 'summary_fa": "خلاصه' not in c["input_md"]
            )
            assert json.loads(facts)["card"]["ref"] in c["input_md"]
        # The advisor writes `approve`; GPT says approve (agrees), DeepSeek reject (differs).
        d = (await client.get(f"/api/v1/decisions/{ref}", headers=owner)).json()
        adv = await agent_headers("HQ-ADV")
        w = await client.post(
            "/internal/v1/advisor/memos",
            headers={**adv, **idem()},
            json=_memo_body(ref, d["version"]),
        )
        assert w.status_code == 200, w.text
        job = (await claim(client))["job"]
        assert job["seat"] == "advisor_second_opinion"
        answer = json.dumps({"recommendation": "approve", "confidence": 0.6, "summary_fa": "موافقم",
                             "key_points": ["هزینه کم"]}, ensure_ascii=False)  # fmt: skip
        await done(
            client,
            job["id"],
            ok=True,
            text_md=answer,
            usage={"input_tokens": 300, "output_tokens": 50},
        )
        async with hub.db.tx(await hub.companies.ids()) as tx:
            third = await tx.one(
                "SELECT * FROM substitutes.calls WHERE id = :id", id=calls["third_opinion"]["id"]
            )
            await tx.exec(
                "UPDATE substitutes.calls SET state = 'running', claimed_at = now() WHERE id = :id",
                id=third["id"],
            )
            await S.finish(tx, hub, third["id"], S.DoneIn(ok=True, text_md=json.dumps(
                {"recommendation": "reject", "confidence": 0.8, "summary_fa": "مخالفم", "key_points": ["ریسک بالا"]},
                ensure_ascii=False)), via="web")  # fmt: skip
        m = (await client.get(f"/api/v1/decisions/{ref}/memo", headers=owner)).json()
        assert m["second_opinion"]["agrees"] is True and m["second_opinion"]["player"] == "gpt"
        assert m["second_opinion"]["differences"] == []
        assert m["third_opinion"]["agrees"] is False and m["third_opinion"]["differences"] == [
            "ریسک بالا"
        ]
        # The seat's daily cap: the next memo's second opinion is skipped (null).
        ref2 = await _card(client, co, risk="low")
        memo2 = (await client.post(f"/api/v1/decisions/{ref2}/memo", headers=owner, json={})).json()
        skipped = await su.fetchrow(
            """SELECT state, state_reason FROM substitutes.calls WHERE purpose_ref = $1
               AND seat = 'advisor_second_opinion'""",
            memo2["ref"],
        )
        assert (skipped["state"], skipped["state_reason"]) == ("skipped", "per_day")
        assert memo2["second_opinion"] is None


async def test_a_model_the_cli_does_not_offer_is_unavailable_and_its_seat_moves(
    client: httpx.AsyncClient, hub: Hub, su: Any, owner: dict[str, str]
) -> None:
    models = [{"id": "gpt-5.5", "label": "GPT 5.5", "tier": "strong", "available": True},
              {"id": "gpt-5.5-pro", "label": "GPT 5.5 Pro", "tier": "strong", "available": True},
              {"id": "gpt-5.3", "label": "GPT 5.3", "tier": "light", "available": True}]  # fmt: skip
    await su.execute(
        "UPDATE substitutes.players SET models = $1::jsonb WHERE player = 'gpt'", json.dumps(models)
    )
    try:
        async with bench(su, hub, cli=("gpt",)):
            async with hub.db.tx(await hub.companies.ids()) as tx:
                assert await S.ask_models(tx, hub) == 1
            job = (await claim(client))["job"]
            assert job["kind"] == "models"
            await done(client, job["id"], ok=True, models=["gpt-5.5-pro", "gpt-5.3"])
            gpt = next(
                p
                for p in (await client.get("/api/v1/substitutes", headers=owner)).json()
                if p["player"] == "gpt"
            )
            avail = {m["id"]: m["available"] for m in gpt["models"]}
            assert avail == {"gpt-5.5": False, "gpt-5.5-pro": True, "gpt-5.3": True}
            seats = {s["seat"]: s["model"] for s in gpt["seats"]}
            assert (
                seats["advisor_second_opinion"] == "gpt-5.5-pro"
                and seats["assistant_errand"] == "gpt-5.3"
            )
            async with hub.db.tx(await hub.companies.ids()) as tx:
                lines = await S.report_lines(tx)
            assert any("در دسترس نیست" in line and "GPT 5.5" in line for line in lines)
    finally:
        await su.execute(
            "UPDATE substitutes.players SET models = $1::jsonb WHERE player = 'gpt'",
            json.dumps([dict(m, available=True) for m in models if m["id"] != "gpt-5.5-pro"]),
        )
        await su.execute(
            "UPDATE substitutes.seats SET model = 'gpt-5.5' WHERE player = 'gpt' AND model = 'gpt-5.5-pro'"
        )


async def test_the_cli_sign_in_from_the_app_is_sealed_short_and_never_shows_the_code(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    conn = await su.fetchval("SELECT id FROM llm.connections WHERE key = 'gemini-pro'")
    url = f"/api/v1/connections/{conn}/login"
    assert (await client.post(url, headers=h)).status_code == 403  # no step-up
    off = await client.post(
        url, headers={**h, **await step_up(hub, sid, "connection.login", str(conn))}
    )
    assert (
        off.status_code == 409 and off.json()["code"] == "not_ready" and "gemini-login" in off.text
    )
    ds = await su.fetchval("SELECT id FROM llm.connections WHERE key = 'deepseek-free'")
    web_only = await client.post(f"/api/v1/connections/{ds}/login",
                                 headers={**h, **await step_up(hub, sid, "connection.login", str(ds))})  # fmt: skip
    assert web_only.status_code == 409
    saved = hub.settings
    hub.settings = replace(saved, substitutes_runner=True)
    try:
        async with bench(su, hub):
            hub.settings = replace(saved, substitutes_runner=True)
            r = await client.post(
                url, headers={**h, **await step_up(hub, sid, "connection.login", str(conn))}
            )
            assert r.status_code == 201, r.text
            login = r.json()
            assert login["state"] == "waiting" and login["connection"] == "gemini-pro"
            job = (await claim(client))["job"]
            assert job["kind"] == "login" and job["login"]["id"] == login["id"]
            started = await client.post(
                f"/internal/v1/substitutes/logins/{login['id']}/started", headers=substitutes_headers(),
                json={"method": "auth_code", "verification_url": "https://accounts.google.com/o/oauth2/x"},
            )  # fmt: skip
            assert started.status_code == 200
            got = (await client.get(f"{url}/{login['id']}", headers=h)).json()
            assert got["method"] == "auth_code" and got["verification_url"].startswith("https://")
            code = "4/0Ab-" + "q" * 30
            put = await client.post(f"{url}/{login['id']}/code", headers=h, json={"code": code})
            assert put.status_code == 200 and code not in put.text
            first = await client.post(
                f"/internal/v1/substitutes/logins/{login['id']}/code", headers=substitutes_headers()
            )
            again = await client.post(
                f"/internal/v1/substitutes/logins/{login['id']}/code", headers=substitutes_headers()
            )
            assert first.json()["code"] == code and again.json()["code"] is None  # handed over once
            assert (await done(client, job["id"], ok=True)).json()["state"] == "done"
            p = await su.fetchrow(
                "SELECT login_state, status FROM substitutes.players WHERE player = 'gemini'"
            )
            assert tuple(p) == ("signed_in", "ready")
            # After its 10 minutes a code is refused.
            r2 = await client.post(
                url, headers={**h, **await step_up(hub, sid, "connection.login", str(conn))}
            )
            late = r2.json()
            await su.execute(
                "UPDATE substitutes.logins SET method = 'auth_code', expires_at = now() - interval '1 second' WHERE id = $1::uuid",
                late["id"],
            )
            refused = await client.post(f"{url}/{late['id']}/code", headers=h, json={"code": code})
            assert refused.status_code == 409, refused.text
            audit = await su.fetch(
                "SELECT summary FROM audit.entries WHERE target_ref = 'gemini-pro'"
            )
            assert audit and all(code not in (a["summary"] or "") for a in audit)
            assert (
                await su.fetchval(
                    "SELECT count(*) FROM substitutes.logins WHERE code IS NOT NULL AND player = 'gemini'"
                )
                == 0
            )
            out = await client.post(f"/api/v1/connections/{conn}/logout",
                                    headers={**h, **await step_up(hub, sid, "connection.logout", str(conn))})  # fmt: skip
            assert out.status_code == 200 and out.json()["login"]["state"] == "signed_out"
    finally:
        hub.settings = saved


async def test_seats_are_sealed_on_their_body_and_need_if_match(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    gpt = next(
        p
        for p in (await client.get("/api/v1/substitutes", headers=h)).json()
        if p["player"] == "gpt"
    )
    seats = [
        {k: s[k] for k in ("seat", "via", "model", "enabled", "per_day")} for s in gpt["seats"]
    ]
    for s in seats:
        if s["seat"] == "creative":
            s["per_day_video"] = 0
    seats[0]["per_day"] = 4
    raw = body_bytes(seats)
    target = __import__("hashlib").sha256(raw).hexdigest()
    no_seal = await client.put("/api/v1/substitutes/gpt/seats", headers={**h, "If-Match": str(gpt["version"]),
                               "Content-Type": "application/json"}, content=raw)  # fmt: skip
    assert no_seal.status_code == 403
    no_match = await client.put("/api/v1/substitutes/gpt/seats", headers={**h, "Content-Type": "application/json",
                                **await step_up(hub, sid, "substitute.seats", target)}, content=raw)  # fmt: skip
    assert no_match.status_code == 428
    ok = await client.put(
        "/api/v1/substitutes/gpt/seats",
        headers={**h, "If-Match": str(gpt["version"]), "Content-Type": "application/json",
                 **await step_up(hub, sid, "substitute.seats", target)},
        content=raw,
    )  # fmt: skip
    assert ok.status_code == 200, ok.text
    assert {s["seat"]: s["per_day"] for s in ok.json()["seats"]}[seats[0]["seat"]] == 4
    seats[0]["per_day"] = 3
    raw = body_bytes(seats)
    await client.put(
        "/api/v1/substitutes/gpt/seats",
        headers={**h, "If-Match": str(ok.json()["version"]), "Content-Type": "application/json",
                 **await step_up(hub, sid, "substitute.seats", __import__("hashlib").sha256(raw).hexdigest())},
        content=raw,
    )  # fmt: skip


class FakeEgress:
    def __init__(self, *answers: dict[str, Any]) -> None:
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []
        self.logouts: list[str] = []

    async def web(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(kw)
        return self.answers.pop(0)

    async def web_logout(self, *, account: str) -> dict[str, Any]:
        self.logouts.append(account)
        return {"ok": True}


def png(w: int = 1024, h: int = 1024) -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 90, 160)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


async def test_the_web_path_makes_a_creative_with_the_hubs_overlay_and_never_publishes(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    async with bench(su, hub, web=("gpt",)):
        await per_day(su, "gpt", "creative", 5)
        r = await client.post(
            "/api/v1/creatives", headers={**owner, **idem()},
            json={"company": co, "kind": "image", "brief_md": "تبلیغ دوره‌ی آموزش رایگان", "placement": "instagram_story",
                  "overlay": {"title_fa": "دوره‌ی رایگان", "body_fa": "ثبت‌نام از امروز", "cta_fa": "همین حالا", "mark": True}},
        )  # fmt: skip
        assert r.status_code == 201, r.text
        cr = r.json()
        assert cr["state"] == "queued" and cr["aspect"] == "9:16" and cr["ai_generated"] is True
        assert "Do not put any text" in cr["prompt_md"]
        fake = FakeEgress({"ok": True, "file": {"name": "image.png", "mime": "image/png", "b64": png()},
                           "recipe_version": "2"})  # fmt: skip
        out = await S.web_jobs(hub, fake)
        assert (
            out["ran"] == 1
            and fake.calls[0]["account"] == "chatgpt-web"
            and fake.calls[0]["task"] == "image"
        )
        assert "Do not put any text" in fake.calls[0]["prompt"]
        got = (await client.get(f"/api/v1/creatives/{cr['ref']}", headers=owner)).json()
        assert got["state"] == "review" and got["composed"]["mime"] == "image/png", got["review_md"]
        assert (got["composed"]["width"], got["composed"]["height"]) == (1080, 1920)
        assert got["files"] and got["source"]["player"] == "gpt"
        # Accepting is not publishing: no send of any kind was made.
        sends = await su.fetchval("SELECT count(*) FROM growth.sends")
        acc = await client.post(
            f"/api/v1/creatives/{cr['ref']}/accept", headers=owner, json={"note": "خوب"}
        )
        assert acc.status_code == 200 and acc.json()["state"] == "accepted"
        assert await su.fetchval("SELECT count(*) FROM growth.sends") == sends
        assert (
            await client.post(f"/api/v1/creatives/{cr['ref']}/reject", headers=owner, json={})
        ).status_code == 409
        # An expired profile: the seat is skipped, ONE notification, no sign-in attempt.
        await su.execute(
            "UPDATE substitutes.players SET web_last_job_at = NULL WHERE player = 'gpt'"
        )
        a = (await client.post("/api/v1/creatives", headers={**owner, **idem()},
                               json={"company": co, "kind": "image", "brief_md": "بنر", "placement": "banner"})).json()  # fmt: skip
        b = (await client.post("/api/v1/creatives", headers={**owner, **idem()},
                               json={"company": co, "kind": "image", "brief_md": "بنر دوم", "placement": "banner"})).json()  # fmt: skip
        since = await su.fetchval("SELECT clock_timestamp()")
        expired = FakeEgress(
            {"ok": False, "error": "expired", "detail": "a sign-in page", "step": "open"}
        )
        await S.web_jobs(hub, expired)
        p = await su.fetchrow("SELECT web_state FROM substitutes.players WHERE player = 'gpt'")
        assert p["web_state"] == "expired"
        states = {
            x["ref"]: x["state"]
            for x in (await client.get(f"/api/v1/creatives?company={co}", headers=owner)).json()[
                "items"
            ]
        }
        assert states[a["ref"]] == "failed"
        await S.web_jobs(hub, FakeEgress())  # the second one is skipped without egress
        states = {
            x["ref"]: x["state"]
            for x in (await client.get(f"/api/v1/creatives?company={co}", headers=owner)).json()[
                "items"
            ]
        }
        assert states[b["ref"]] == "failed"
        n = await su.fetchval(
            "SELECT count(*) FROM notify.notifications WHERE link_kind = 'substitute' AND link_ref = 'gpt' AND created_at >= $1",
            since,
        )
        assert n == 1
        # A broken recipe: the call fails with its step; nothing carries a cookie.
        await su.execute(
            "UPDATE substitutes.players SET web_state = 'signed_in', web_last_job_at = NULL WHERE player = 'gpt'"
        )
        c = (await client.post("/api/v1/creatives", headers={**owner, **idem()},
                               json={"company": co, "kind": "image", "brief_md": "پست", "placement": "telegram_post"})).json()  # fmt: skip
        broken = FakeEgress(
            {
                "ok": False,
                "error": "recipe_failed",
                "detail": "no prompt box",
                "step": "paste_prompt",
            }
        )
        await S.web_jobs(hub, broken)
        got = (await client.get(f"/api/v1/creatives/{c['ref']}", headers=owner)).json()
        assert got["state"] == "failed" and "recipe_failed" in got["review_md"]
        fail = await su.fetchval(
            "SELECT web_last_failure FROM substitutes.players WHERE player = 'gpt'"
        )
        assert fail == "recipe_failed: paste_prompt" and "cookie" not in fail.lower()
        # The owner's sealed web sign-out wipes the profile through egress.
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await S.web_logout(tx, "gpt")
        wipe = FakeEgress()
        await S.web_jobs(hub, wipe)
        assert wipe.logouts == ["chatgpt-web"]


async def test_the_web_path_does_nothing_while_the_holding_is_locked(hub: Hub, su: Any) -> None:
    async with bench(su, hub, web=("deepseek",)):
        async with hub.db.tx(await hub.companies.ids()) as tx:
            holding = await hub.companies.holding()
            await su.execute(
                "UPDATE substitutes.seats SET per_day = 1000 WHERE player = 'deepseek'"
            )
            call = await S.seat_call(tx, hub, A.SERVICE, seat="quick_search", input_md="سوال عمومی",
                                     company_id=holding.id)  # fmt: skip
        assert call["state"] == "queued"
        fake = FakeEgress()
        async with holding_switch(su, "engaged"):
            out = await S.web_jobs(hub, fake)
        assert out["skipped"] is True and out["reason"] == "holding_locked" and fake.calls == []
        await su.execute(
            "UPDATE substitutes.seats SET per_day = 60 WHERE player = 'deepseek' AND seat = 'quick_search'"
        )
        await su.execute(
            "UPDATE substitutes.seats SET per_day = 5 WHERE player = 'deepseek' AND seat = 'third_opinion'"
        )


def test_the_overlay_is_set_in_iranyekanx_inside_the_safe_zone(tmp_path: Any) -> None:
    overlay = {"title_fa": "دوره‌ی آموزش رایگان فارکس", "body_fa": "ثبت‌نام از امروز برای همه باز است",
               "cta_fa": "همین حالا", "mark": True}  # fmt: skip
    left, top, right, bottom = O.safe_rect("instagram_story")
    assert (top, bottom) == (0.14 * 1920, 1920 - 0.20 * 1920)
    boxes = O.layout("instagram_story", overlay)
    assert {b.role for b in boxes} == {"title", "body", "cta"}
    for b in boxes:
        assert top < b.y - b.size * 0.9 and b.y <= bottom and b.x <= right, b
    svg = O.svg("instagram_story", overlay, None, {"ink": "#111216", "accent": "#0E9F6E"}, None)
    assert 'font-family="IRANYekanX"' in svg and 'direction="rtl"' in svg and "دوره‌ی آموزش" in svg
    out = tmp_path / "o.png"
    info = O.compose_job(svg, str(out), "/fonts")
    assert info["fonts"] >= 1 and out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    from PIL import Image

    img = Image.open(out)
    assert img.size == (1080, 1920)
    # Text pixels (white) only inside the safe zone: none in the covered bands.
    px = img.convert("RGB").load()
    white = [
        (x, y) for y in range(0, 1920, 4) for x in range(0, 1080, 4) if px[x, y] == (255, 255, 255)
    ]
    assert white and all(top <= y <= bottom and left <= x <= right for x, y in white)
    # No text is ever asked of the image model.
    assert "Do not put any text" in S.template_prompt("بنر", "banner", "image", None)
    assert re.search(r"aspect 9:16", S.template_prompt("استوری", "instagram_story", "image", None))


async def test_a_second_review_waits_for_the_cto_and_approval_is_the_same_without_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    from .test_p12a_advisor import _card

    co = (await new_company())["code"]
    h = owner_session["headers"]
    async with bench(su, hub, cli=("gpt",)):
        await per_day(su, "gpt", "code_review", 5)
        with_review, without = (
            await _card(client, co, risk="low"),
            await _card(client, co, risk="low"),
        )
        async with hub.db.tx(await hub.companies.ids()) as tx:
            cid = await su.fetchval("SELECT id FROM core.companies WHERE code = $1", co)
            call = await S.queue_code_review(tx, hub, A.SERVICE, company_id=cid, repo="coinepro-hub",
                                             head_sha="a" * 40, diff_md="diff --git a/x b/x",
                                             purpose=("decision", with_review))  # fmt: skip
        job = (await claim(client))["job"]
        assert (
            job["checkout"] == {"repo": "coinepro-hub", "head_sha": "a" * 40}
            and job["seat"] == "code_review"
        )
        await done(client, job["id"], ok=True, findings=[{"path": "x.py", "line": 3, "severity": "high",
                                                          "title_fa": "خطا", "detail_md": "..."}])  # fmt: skip
        async with hub.db.tx(await hub.companies.ids()) as tx:
            review = await S.second_review(tx, with_review)
        assert (
            review is not None
            and review["verified"] == 0
            and review["findings"][0]["verified"] is None
        )
        assert call["state"] == "queued"
        for ref in (with_review, without):
            r = await client.post(
                f"/api/v1/decisions/{ref}/approve", headers={**h, **idem()}, json={}
            )
            assert r.status_code == 200 and r.json()["status"] == "approved", r.text
            assert r.json()["risk_note"] is None  # nothing unverified reaches the card


async def test_a_paid_player_behind_on_the_15th_gets_one_report_and_nothing_widens(
    hub: Hub, su: Any
) -> None:
    async with bench(su, hub, cli=("gpt", "gemini")):
        seats_before = await su.fetch(
            "SELECT player, seat, enabled, per_day FROM substitutes.seats ORDER BY 1, 2"
        )
        # The owner's price table (§10) for GPT's models; Gemini's stays empty:
        # its equivalent is unknown, so it is never called behind.
        await su.execute(
            """UPDATE llm.connections SET pricing = '{"gpt-5.5": {"input_per_mtok": "1", "output_per_mtok": "8"}}'
               WHERE key = 'chatgpt-plus'"""
        )
        try:
            async with hub.db.tx(await hub.companies.ids()) as tx:
                not_15th = await S.behind_check(tx, hub, datetime(2026, 11, 5, 9, tzinfo=UTC))
                first = await S.behind_check(tx, hub, datetime(2026, 11, 6, 9, tzinfo=UTC))
                second = await S.behind_check(tx, hub, datetime(2026, 11, 6, 10, tzinfo=UTC))
        finally:
            await su.execute("UPDATE llm.connections SET pricing = '{}' WHERE key = 'chatgpt-plus'")
        assert not_15th == 0 and first <= 1 and second == 0  # one per player and Jalali month
        assert (
            await su.fetchval(
                "SELECT count(*) FROM notify.notifications WHERE link_ref LIKE 'substitute-behind:gemini:%'"
            )
            == 0
        )
        month = S.month_key(S.owner_day())
        n = await su.fetchval(
            "SELECT count(*) FROM notify.notifications WHERE link_kind = 'substitute' AND link_ref = $1",
            f"substitute-behind:gpt:{month}",
        )
        assert n == 1
        # A free account (DeepSeek) and a signed-out player are never "behind".
        assert (
            await su.fetchval(
                "SELECT count(*) FROM notify.notifications WHERE link_ref LIKE 'substitute-behind:deepseek:%'"
            )
            == 0
        )
        assert (
            await su.fetch(
                "SELECT player, seat, enabled, per_day FROM substitutes.seats ORDER BY 1, 2"
            )
            == seats_before
        )
