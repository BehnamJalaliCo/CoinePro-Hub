"""Prompt 21 part 3 (contract §29.12): connections. The secret is never
returned (only set or missing) and lives in OpenBao alone; the one-page
guides; each reader through a fake egress writes growth.metrics_daily (the
Google readers sign their own RS256 assertion); a failing reader leaves a
Persian `last_error_fa`; Instagram is read through IG-Hub's runner job; the
channels' seed (TY's signal channel, every Instagram account on IG-Hub,
an unknown code skipped). Nothing leaves the test."""

from __future__ import annotations

import base64
import json
import secrets as _secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from hq_api.domain import connections as CN
from hq_api.domain import humanize as H
from hq_api.hub import Hub
from hq_api.routes import connections as CR
from hq_common.openbao import SecretNotFound

from .conftest import signed_put, step_up
from .p10_fakes import holding_switch

TOKEN = "123456:" + "T" * 35  # a Telegram bot's token (fake)
ACCESS = "ya29." + "A" * 40  # a Google access token (fake)
YT_KEY = "AIza" + "K" * 35


class FakeBao:
    def __init__(self, data: dict[str, str] | None = None) -> None:
        self.data = dict(data or {})
        self.writes: list[tuple[str, dict[str, Any]]] = []

    async def read_kv(self, path: str) -> dict[str, Any]:
        if path not in self.data:
            raise SecretNotFound(path)
        return {"secret": self.data[path]}

    async def write_kv(self, path: str, data: dict[str, Any]) -> None:
        self.writes.append((path, data))
        self.data[path] = data["secret"]


def service_account() -> tuple[str, rsa.RSAPublicKey]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    sa = {"type": "service_account", "client_email": "reader@proj.iam.gserviceaccount.com",
          "private_key": pem, "token_uri": "https://oauth2.googleapis.com/token"}  # fmt: skip
    return json.dumps(sa), key.public_key()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class FakeEgress:
    """The egress service's POST /v1/http, answered by URL (nothing leaves)."""

    def __init__(self, public: rsa.RSAPublicKey | None = None) -> None:
        self.public = public
        self.calls: list[dict[str, Any]] = []
        self.fail: dict[str, int] = {}  # a host -> the HTTP status it answers

    async def request(self, method: str, url: str, *, company: str, **kw: Any) -> CN.Answer:
        self.calls.append({"method": method, "url": url, "company": company, **kw})
        host = urlsplit(url).hostname or ""
        entry = {"tool": "http.request", "kind": "request", "class": "A0", "method": method,
                 "host": host, "status": 200, "bytes_in": 10, "bytes_out": 0, "ms": 5}  # fmt: skip
        if host in self.fail:
            return CN.Answer("ok", self.fail[host], json.dumps({"error": "no"}), None, [entry])
        acct = kw.get("account") or {}
        if host == "oauth2.googleapis.com":
            form = parse_qs(str(kw.get("body")))
            assertion = form["assertion"][0]
            head, claims, sig = assertion.split(".")
            assert self.public is not None
            self.public.verify(_b64d(sig), f"{head}.{claims}".encode(), padding.PKCS1v15(),
                               hashes.SHA256())  # fmt: skip
            scope = json.loads(_b64d(claims))["scope"]
            assert scope.endswith(".readonly")
            return CN.Answer("ok", 200, json.dumps({"access_token": ACCESS, "expires_in": 3600}),
                             None, [entry])  # fmt: skip
        if host == "api.telegram.org":
            assert acct.get("secret") == TOKEN
            chat = parse_qs(urlsplit(url).query)["chat_id"][0]
            body = {"ok": True, "result": 1500 if chat == "@ty_signal" else 300}
            return CN.Answer("ok", 200, json.dumps(body), None, [entry])
        if host == "searchconsole.googleapis.com":
            assert acct.get("secret") == ACCESS and kw["json_body"]["dimensions"] == ["date"]
            rows = [{"keys": ["2026-10-30"], "clicks": 40, "impressions": 2000, "ctr": 0.02,
                     "position": 9.5}]  # fmt: skip
            return CN.Answer("ok", 200, json.dumps({"rows": rows}), None, [entry])
        if host == "analyticsdata.googleapis.com":
            assert acct.get("secret") == ACCESS
            rows = [{"dimensionValues": [{"value": "20261101"}],
                     "metricValues": [{"value": "320"}, {"value": "250"}, {"value": "7"}]}]  # fmt: skip
            return CN.Answer("ok", 200, json.dumps({"rows": rows}), None, [entry])
        if host == "www.googleapis.com" and "/youtube/" in url:
            assert acct.get("secret") == YT_KEY and acct["inject"]["name"] == "X-goog-api-key"
            stats = {"subscriberCount": "880", "viewCount": "120000", "videoCount": "42"}
            return CN.Answer("ok", 200, json.dumps({"items": [{"statistics": stats}]}), None, [entry])
        if host == "www.googleapis.com" and "/pagespeedonline/" in url:
            lh = {"lighthouseResult": {"categories": {"performance": {"score": 0.87}},
                  "audits": {"largest-contentful-paint": {"numericValue": 2350.4},
                             "cumulative-layout-shift": {"numericValue": 0.031}}}}  # fmt: skip
            return CN.Answer("ok", 200, json.dumps(lh), None, [entry])
        return CN.Answer("error", None, "", "fetch_failed", [entry])


@pytest.fixture
def egress(hub: Hub) -> Any:
    yield
    CN.OVERRIDE = None
    hub.bao = None


async def metrics(su: Any, company_id: UUID, kind: str) -> dict[tuple[str, str], float]:
    rows = await su.fetch(
        "SELECT key, subject, value FROM growth.metrics_daily WHERE company_id = $1 AND kind = $2",
        company_id,
        kind,
    )
    return {(r["key"], r["subject"]): float(r["value"]) for r in rows}


async def conn(su: Any, company_id: UUID, kind: str) -> Any:
    return await su.fetchrow(
        "SELECT * FROM growth.connections WHERE company_id = $1 AND kind = $2", company_id, kind
    )


async def put_config(su: Any, company_id: UUID, kind: str, config: dict[str, Any], **cols: Any) -> None:
    await su.execute(
        """INSERT INTO growth.connections (company_id, kind, label_fa, config, secret_set)
           VALUES ($1, $2, 'اتصال', $3::jsonb, $4)
           ON CONFLICT (company_id, kind) DO UPDATE SET config = EXCLUDED.config,
               secret_set = EXCLUDED.secret_set, last_error_fa = NULL, pending = NULL""",
        company_id,
        kind,
        json.dumps(config),
        bool(cols.get("secret_set", True)),
    )


# ----------------------------------------------------------------- seeds --
async def test_the_channels_seed_ty_signal_ig_hub_and_unknown_codes_skipped(
    hub: Hub, su: Any, new_company: Callable[..., Any], tmp_path: Path
) -> None:
    data = CN.channels_file()
    ty = [c for c in data["channels"] if c["company"] == "TY"]
    tg = next(c for c in ty if c["kind"] == "telegram")
    assert tg["config"]["channels"][0]["role"] == "signal"  # the signal channel is TradeYar's
    insta = [c for c in data["channels"] if c["kind"] == "instagram"]
    assert insta and all(c["config"]["via"] == "ig_hub" for c in insta)
    assert data["ig_hub"] == {"company": "IG", "server": "IG-Hub"}
    # as migrated: TY has its signal channel; its Instagram is on IG-Hub
    row = await su.fetchrow(
        """SELECT k.config, k.state, k.origin FROM growth.connections k
           JOIN core.companies c ON c.id = k.company_id WHERE c.code = 'TY' AND k.kind = 'telegram'"""
    )
    cfg = json.loads(row["config"])
    assert cfg["channels"][0]["role"] == "signal" and row["origin"] == "seed"
    assert row["state"] == "not_connected"  # the owner fills the handle and the bot later
    ig = await su.fetchrow(
        """SELECT k.config FROM growth.connections k JOIN core.companies c ON c.id = k.company_id
           WHERE c.code = 'TY' AND k.kind = 'instagram'"""
    )
    assert json.loads(ig["config"])["server"] == {"company": "IG", "name": "IG-Hub"}
    # a seed of its own: a known code is added once, an unknown one skipped
    co = await new_company()
    (tmp_path / "c.yaml").write_text(
        "channels:\n"
        f"  - {{company: {co['code']}, kind: instagram, label_fa: آزمایش, config: {{via: ig_hub}}}}\n"
        "  - {company: ZZNOPE, kind: telegram, label_fa: هیچ}\n",
        encoding="utf-8",
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await CN.seed(tx, tmp_path / "c.yaml") == 1
        assert await CN.seed(tx, tmp_path / "c.yaml") == 0  # only added, never overwritten
    mine = await conn(su, co["id"], "instagram")
    assert json.loads(mine["config"])["via"] == "ig_hub"
    assert not await su.fetchval(
        "SELECT 1 FROM growth.connections k JOIN core.companies c ON c.id = k.company_id "
        "WHERE c.code = 'ZZNOPE'"
    )


# ---------------------------------------------------------- owner routes --
async def test_the_secret_is_never_returned_only_set_or_missing(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
    egress: Any,
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    co = await new_company()
    c = co["code"]
    listed = (await client.get(f"/api/v1/companies/{c}/connections", headers=h)).json()
    assert [x["kind"] for x in listed] == list(CN.KINDS)  # every kind, in the contract's order
    assert all(x["state"] == "not_connected" and x["secret"] == "missing" for x in listed)
    body = {"config": {"channels": [{"title_fa": "کانال اصلی", "chat": "@main_ch"}]}}
    plain = await client.put(f"/api/v1/companies/{c}/connections/telegram", headers=h, json=body)
    assert plain.status_code == 403  # it widens what is read: a step-up
    r = await signed_put(client, hub, owner_session, f"/api/v1/companies/{c}/connections/telegram",
                         body, "connection.config")  # fmt: skip
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "not_connected" and r.json()["missing_fa"] == ["رمز اتصال"]
    narrower = await client.put(
        f"/api/v1/companies/{c}/connections/telegram", headers=h, json={"config": {"channels": []}}
    )
    assert narrower.status_code == 200, narrower.text  # nothing more is read: no step-up
    leaked = await client.put(
        f"/api/v1/companies/{c}/connections/telegram", headers=h, json={"config": {"token": "x"}}
    )
    assert leaked.status_code == 422  # a secret never goes into the config
    hub.bao = FakeBao()
    no_su = await client.put(f"/api/v1/companies/{c}/connections/telegram/secret", headers=h,
                             json={"secret": TOKEN})  # fmt: skip
    assert no_su.status_code == 403
    su_h = await step_up(hub, sid, "connection.secret", f"{c}:telegram")
    r = await client.put(f"/api/v1/companies/{c}/connections/telegram/secret", headers={**h, **su_h},
                         json={"secret": TOKEN})  # fmt: skip
    assert r.status_code == 200 and r.json() == {"company": c, "kind": "telegram", "secret": "set"}
    assert hub.bao.writes == [(f"hq/growth/{c}/telegram", {"secret": TOKEN})]
    r = await client.get(f"/api/v1/companies/{c}/connections", headers=h)
    assert TOKEN not in r.text and TOKEN.split(":")[1] not in r.text
    tg = next(x for x in r.json() if x["kind"] == "telegram")
    assert tg["secret"] == "set"
    ig = await client.put(
        f"/api/v1/companies/{c}/connections/instagram/secret",
        headers={**h, **await step_up(hub, sid, "connection.secret", f"{c}:instagram")},
        json={"secret": "x" * 20},
    )
    assert ig.status_code == 422  # Instagram never has a token on the hub
    audit = await su.fetch(
        "SELECT summary FROM audit.entries WHERE target_ref = $1 AND action = 'connection.secret'",
        f"{c}:telegram",
    )
    assert audit and all(TOKEN not in a["summary"] for a in audit)


@pytest.mark.parametrize("kind", CN.KINDS)
async def test_every_kind_has_its_one_page_guide(
    client: httpx.AsyncClient, owner: dict[str, str], kind: str
) -> None:
    r = await client.get(f"/api/v1/connections/guides/{kind}", headers=owner)
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["kind"] == kind and H.is_persian_answer(g["body_md"], threshold=0.6)
    assert H.check(g["body_md"]) == [] and H.check(g["title_fa"]) == []
    assert "گام" in g["body_md"] or "هنوز ساخته نشده" in g["body_md"]


async def test_an_unknown_guide_is_refused(client: httpx.AsyncClient, owner: dict[str, str]) -> None:
    assert (await client.get("/api/v1/connections/guides/myspace", headers=owner)).status_code == 422


# ---------------------------------------------------------------- readers --
async def test_each_reader_through_egress_writes_its_daily_figures(
    hub: Hub, su: Any, new_company: Callable[..., Any], egress: Any
) -> None:
    co = await new_company()
    c, cid = co["code"], co["id"]
    sa, public = service_account()
    fake = FakeEgress(public)
    CN.OVERRIDE = fake
    hub.bao = FakeBao(
        {
            f"hq/growth/{c}/telegram": TOKEN,
            f"hq/growth/{c}/search_console": sa,
            f"hq/growth/{c}/ga4": sa,
            f"hq/growth/{c}/youtube": YT_KEY,
        }
    )
    await put_config(su, cid, "telegram", {"channels": [
        {"role": "signal", "title_fa": "کانال سیگنال", "chat": "@ty_signal"},
        {"title_fa": "کانال دوم", "chat": "@ty_news"}, {"title_fa": "بی نشانی", "chat": None}]})  # fmt: skip
    await put_config(su, cid, "search_console", {"site_url": "sc-domain:example.com"})
    await put_config(su, cid, "ga4", {"property_id": "123456789"})
    await put_config(su, cid, "youtube", {"channel_id": "UC123"})
    await put_config(su, cid, "pagespeed", {"urls": ["https://example.com/"]}, secret_set=False)
    async with holding_switch(su, "released"):
        for kind in ("telegram", "search_console", "ga4", "youtube", "pagespeed"):
            after = await CN.read_one(hub, cid, kind)
            assert after["state"] == "connected" and after["last_error_fa"] is None, (kind, after)
            assert after["last_read_at"] is not None and after["secret_set"] is (kind != "pagespeed")
    assert await metrics(su, cid, "telegram") == {
        ("followers", "@ty_signal"): 1500.0, ("followers", "@ty_news"): 300.0
    }  # fmt: skip
    sc = await metrics(su, cid, "search_console")
    assert sc == {("clicks", "sc-domain:example.com"): 40.0,
                  ("impressions", "sc-domain:example.com"): 2000.0,
                  ("ctr", "sc-domain:example.com"): 2.0,
                  ("position", "sc-domain:example.com"): 9.5}  # fmt: skip
    ga = await metrics(su, cid, "ga4")
    assert ga == {("sessions", "123456789"): 320.0, ("users", "123456789"): 250.0,
                  ("conversions", "123456789"): 7.0}  # fmt: skip
    assert await metrics(su, cid, "youtube") == {
        ("followers", "UC123"): 880.0, ("views", "UC123"): 120000.0, ("videos", "UC123"): 42.0
    }  # fmt: skip
    ps = await metrics(su, cid, "pagespeed")
    assert ps[("performance", "https://example.com/")] == 87.0
    assert ps[("lcp_ms", "https://example.com/")] == 2350.0
    assert ps[("cls", "https://example.com/")] == 0.031
    # every call went out through egress, logged, and only as its company
    assert {x["company"] for x in fake.calls} == {c}
    hosts = {r["host"] for r in await su.fetch(
        "SELECT host FROM egress.log WHERE company_id = $1 AND actor = 'growth-read'", cid)}  # fmt: skip
    assert {"api.telegram.org", "oauth2.googleapis.com", "searchconsole.googleapis.com",
            "analyticsdata.googleapis.com", "www.googleapis.com"} <= hosts  # fmt: skip
    # no figure or row holds a secret
    dump = json.dumps([dict(r) for r in await su.fetch(
        "SELECT * FROM growth.connections WHERE company_id = $1", cid)], default=str)  # fmt: skip
    assert TOKEN not in dump and ACCESS not in dump and "PRIVATE KEY" not in dump


async def test_a_failing_reader_leaves_a_persian_error(
    hub: Hub, su: Any, new_company: Callable[..., Any], egress: Any
) -> None:
    co = await new_company()
    c, cid = co["code"], co["id"]
    sa, public = service_account()
    fake = FakeEgress(public)
    fake.fail = {"api.telegram.org": 401, "searchconsole.googleapis.com": 403}
    CN.OVERRIDE = fake
    hub.bao = FakeBao({f"hq/growth/{c}/telegram": TOKEN, f"hq/growth/{c}/search_console": sa,
                       f"hq/growth/{c}/ga4": "not json"})  # fmt: skip
    await put_config(su, cid, "telegram", {"channels": [{"title_fa": "کانال", "chat": "@ty_signal"}]})
    await put_config(su, cid, "search_console", {"site_url": "https://example.com/"})
    await put_config(su, cid, "ga4", {"property_id": "42"})
    await put_config(su, cid, "x", {"handle": "@tradeyar"}, secret_set=False)
    async with holding_switch(su, "released"):
        for kind in ("telegram", "search_console", "ga4", "x"):
            after = await CN.read_one(hub, cid, kind)
            err = after["last_error_fa"]
            assert after["state"] == "error" and err, (kind, after)
            assert H.check(err) == [] and H.is_persian_answer(err), err
    assert (await conn(su, cid, "x"))["last_error_fa"] == CN.NOT_BUILT_FA
    assert "توکن" in (await conn(su, cid, "telegram"))["last_error_fa"]
    assert "JSON" in (await conn(su, cid, "ga4"))["last_error_fa"]
    # a locked company reads nothing: no outside call
    calls = len(fake.calls)
    await su.execute("UPDATE control.kill_switches SET state = 'engaged' WHERE company_id = $1", cid)
    try:
        async with holding_switch(su, "released"):
            after = await CN.read_one(hub, cid, "telegram")
    finally:
        await su.execute(
            "UPDATE control.kill_switches SET state = 'released' WHERE company_id = $1", cid
        )
    assert len(fake.calls) == calls and "کلید توقف" in after["last_error_fa"]


async def test_instagram_is_read_through_ig_hubs_runner_job(
    hub: Hub, su: Any, new_company: Callable[..., Any], egress: Any
) -> None:
    ig, co = await new_company(), await new_company()
    server = await su.fetchval(
        """INSERT INTO infra.servers (company_id, origin, name, state, last_seen_at)
           VALUES ($1, 'attached', 'IG-Hub', 'online', now()) RETURNING id""",
        ig["id"],
    )
    cmd = f"cat /srv/ig/daily-{_secrets.token_hex(4)}.json"
    cfg = {"via": "ig_hub", "accounts": ["@tradeyar"], "command": cmd,
           "server": {"company": ig["code"], "name": "IG-Hub"}}  # fmt: skip
    await put_config(su, co["id"], "instagram", cfg, secret_set=False)
    CN.OVERRIDE = FakeEgress()
    async with holding_switch(su, "released"):
        first = await CN.read_one(hub, co["id"], "instagram")
        job = await su.fetchrow(
            "SELECT id, kind, args, actor_code, state FROM infra.server_jobs WHERE server_id = $1",
            server,
        )
        assert job["kind"] == "exec" and json.loads(job["args"])["cmd"] == cmd
        assert job["actor_code"] == "growth-read" and job["state"] == "queued"
        assert json.loads(first["pending"])["job_id"] == str(job["id"])
        assert first["last_read_at"] is None and first["last_error_fa"] is None
        again = await CN.read_one(hub, co["id"], "instagram")  # still running: no second job
        assert await su.fetchval("SELECT count(*) FROM infra.server_jobs WHERE server_id = $1",
                                 server) == 1  # fmt: skip
        assert again["pending"] is not None
        out = {"day": "2026-11-02", "accounts": [
            {"account": "tradeyar", "followers": 5400, "reach": 12000, "views": 30000},
            {"account": "someone_else", "followers": 1}]}  # fmt: skip
        await su.execute("UPDATE infra.server_jobs SET state = 'done', finished_at = now() WHERE id = $1",
                         job["id"])  # fmt: skip
        await su.execute(
            """INSERT INTO infra.server_job_events (job_id, company_id, seq, type, data)
               VALUES ($1, $2, 1, 'stdout', $3::jsonb)""",
            job["id"], ig["id"], json.dumps({"text": json.dumps(out)}),
        )  # fmt: skip
        done = await CN.read_one(hub, co["id"], "instagram")
    assert done["state"] == "connected" and done["pending"] is None and done["last_read_at"]
    figures = await metrics(su, co["id"], "instagram")
    assert figures == {("followers", "tradeyar"): 5400.0, ("reach", "tradeyar"): 12000.0,
                       ("views", "tradeyar"): 30000.0}  # fmt: skip
    # a command that is not read-only is never run
    await put_config(su, co["id"], "instagram", {**cfg, "command": "rm -rf /srv/ig"}, secret_set=False)
    async with holding_switch(su, "released"):
        bad = await CN.read_one(hub, co["id"], "instagram")
    assert bad["state"] == "error" and "فقط‌خواندنی" in bad["last_error_fa"]
    assert await su.fetchval("SELECT count(*) FROM infra.server_jobs WHERE server_id = $1",
                             server) == 1  # fmt: skip


async def test_the_daily_read_reads_once_a_day_and_the_owners_test_reads_now(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    egress: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    co = await new_company()
    fake = FakeEgress()
    CN.OVERRIDE = fake
    hub.bao = FakeBao({f"hq/growth/{co['code']}/telegram": TOKEN})
    await put_config(su, co["id"], "telegram", {"channels": [{"title_fa": "کانال", "chat": "@ty_news"}]})
    async with holding_switch(su, "released"):
        out = await CN.read_due(hub)
        mine = [x for x in fake.calls if x["company"] == co["code"]]
        assert len(mine) == 1 and out["read"] >= 1
        await CN.read_due(hub)  # read today already
        assert len([x for x in fake.calls if x["company"] == co["code"]]) == 1

        async def inline(h: Any, company_id: Any, kind: str) -> None:
            await CN.read_one(h, company_id, kind)

        monkeypatch.setattr(CR, "run_test", inline)
        r = await client.post(f"/api/v1/companies/{co['code']}/connections/telegram/test",
                              headers=owner)  # fmt: skip
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "connected" and r.json()["daily"][0]["key"] == "followers"
    assert len([x for x in fake.calls if x["company"] == co["code"]]) == 2
    none = await client.post(f"/api/v1/companies/{co['code']}/connections/bing/test", headers=owner)
    assert none.status_code == 404


def test_widening_is_any_new_value() -> None:
    assert CN.widens({}, {"site_url": "https://a"})
    assert CN.widens({"channels": [{"chat": "@a"}]}, {"channels": [{"chat": "@a"}, {"chat": "@b"}]})
    assert not CN.widens({"channels": [{"chat": "@a"}, {"chat": "@b"}]}, {"channels": [{"chat": "@a"}]})
    assert CN.widens({"site_url": "https://a"}, {"site_url": "https://b"})
