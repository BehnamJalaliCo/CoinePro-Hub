"""Connectors of code and the lbank-v2 signer (prompt 10 §2.2-§2.3, contract
§19.1): a fake LBank (affiliate API over TLS, its public market API) that
checks every signature with the documented algorithm and answers in LBank's
documented envelope. No real exchange is called."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest
from test_egress import LOCAL, _ctx, _plain_guard, _tls

from hq_egress import connectors as K
from hq_egress.accounts import Account
from hq_egress.app import State, build_app
from hq_egress.config import Settings
from hq_egress.net import Fetcher
from hq_egress.proxy import Buckets
from hq_egress.signers import lbank_v2, lbank_v2_sign, split_pair

API_KEY = "ak-" + "Q" * 29
SECRET_KEY = "sk-" + "W" * 40
PAIR = f"{API_KEY}:{SECRET_KEY}"


class FakeLbank:
    """LBank's affiliate API and its kline, on 127.0.0.1 (TLS and plain)."""

    def __init__(self) -> None:
        self.seen: list[dict[str, Any]] = []
        self.missing_page: int | None = None  # a page that answers an error
        self.echo_key = False  # a hostile answer that carries the api key back
        self.server: asyncio.Server | None = None
        self.plain: asyncio.Server | None = None
        self.port = self.plain_port = 0

    async def start(self, ctx: Any) -> None:
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0, ssl=ctx)
        self.port = self.server.sockets[0].getsockname()[1]
        self.plain = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        self.plain_port = self.plain.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        for s in (self.server, self.plain):
            if s is not None:
                s.close()

    def answer(self, path: str, form: dict[str, str]) -> Any:
        if path.startswith("/v2/kline.do"):
            q = dict(parse_qsl(urlsplit(path).query))
            close = {"eth_usdt": "2000", "btc_usdt": "60000"}.get(q.get("symbol", ""), "1")
            return {"result": "true", "data": [[int(q.get("time", 0)), "1", "2", "0.5", close, "9"]],
                    "error_code": 0}  # fmt: skip
        if form.get("sign") != lbank_v2_sign(form, SECRET_KEY) or form.get("api_key") != API_KEY:
            return {
                "result": "false",
                "error_code": 10002,
                "msg": f"bad sign {form.get('api_key')}",
            }
        name = path.removeprefix("/affiliate-api/v2/")
        start = int(form.get("start", 0))
        if name == "commission/stats/symbol/list":
            return {"result": "true", "error_code": 0, "data": [
                {"coin": "usdt", "amount": "10.5"}, {"coin": "eth", "amount": "0.01"},
                {"coin": "USDT", "amount": "1.5"}]}  # fmt: skip
        if name == "invite/user/team/list":
            if self.missing_page is not None and start // 100 == self.missing_page:
                return {"result": "false", "error_code": 10009, "msg": "busy"}
            rows = [
                {"uid": API_KEY if self.echo_key else f"9{start + i:07d}",
                 "registerTime": 1792972800000, "totalAssetUsdt": "150" if i % 2 else "20",
                 "email": "x@example.com", "name": "Ali"}
                for i in range(min(100, 150 - start))
            ]  # fmt: skip
            return {"result": "true", "error_code": 0, "data": {"total": 150, "list": rows}}
        if name == "trade/user/team":
            return {"result": "true", "error_code": 0,
                    "data": {"volume": "125000.5", "fee": "80.25", "tradeUserCount": 7}}  # fmt: skip
        if name == "money/detail/list":
            return {"result": "true", "error_code": 0,
                    "data": {"total": 1, "list": [{"coin": "usdt", "amount": "300"}]}}  # fmt: skip
        if name == "invite/user/info":
            uid = form.get("uid", "")
            if uid.startswith("9"):
                return {"result": "true", "error_code": 0,
                        "data": {"isInvite": True, "uid": uid, "totalAssetUsdt": "120.5",
                                 "nickName": "Ali"}}  # fmt: skip
            return {"result": "true", "error_code": 0, "data": {}}
        return {"result": "false", "error_code": 404}

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except (asyncio.IncompleteReadError, ConnectionError):
            writer.close()
            return
        lines = head.decode("latin-1").split("\r\n")
        method, path, _ = lines[0].split(" ", 2)
        headers = {
            k.strip().lower(): v.strip()
            for k, _, v in (ln.partition(":") for ln in lines[1:] if ln)
        }
        raw = b""
        if int(headers.get("content-length") or 0):
            raw = await reader.readexactly(int(headers["content-length"]))
        form = dict(parse_qsl(raw.decode()))
        self.seen.append({"method": method, "path": path, "headers": headers, "form": form})
        body = json.dumps(self.answer(path, form)).encode()
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            + body
        )
        await writer.drain()
        writer.close()


@pytest.fixture
async def lbank(tmp_path: Any) -> AsyncIterator[tuple[httpx.AsyncClient, FakeLbank, State]]:
    server_ctx, client_ctx = _tls(tmp_path)
    fake = FakeLbank()
    await fake.start(server_ctx)
    guard = _plain_guard()
    guard.extra_ports = {"site.test": frozenset({fake.plain_port})}  # the public API's test port
    settings = Settings(api_clients=(LOCAL,), hub_hosts=frozenset({"hq.coinepro.com"}),
                        lbank_public_url=f"http://site.test:{fake.plain_port}",
                        connector_wait_s=0.5)  # fmt: skip
    state = State(settings, guard, Buckets(), fetcher=Fetcher(guard, 5, ssl_context=client_ctx))
    transport = httpx.ASGITransport(app=build_app(state), client=("127.0.0.1", 5555))
    async with httpx.AsyncClient(transport=transport, base_url="http://egress") as c:
        yield c, fake, state
    await fake.stop()


def _account(fake: FakeLbank, **over: Any) -> dict[str, Any]:
    return {"key": "lbank-aff-ty", "site": "acct.test", "secret": PAIR, "ports": [fake.port],
            "inject": {"kind": "signer", "signer": "lbank-v2"}, **over}  # fmt: skip


def _call(endpoint: str, account: dict[str, Any] | None, **kw: Any) -> dict[str, Any]:
    return {"ctx": _ctx(actor="revenue-pull"), "adapter": "lbank-affiliate-v2",
            "tool": kw.pop("tool", "revenue.pull"), "endpoint": endpoint,
            "account": account, **kw}  # fmt: skip


def test_the_lbank_v2_signature_is_the_documented_one() -> None:
    form = {"startTime": "1", "endTime": "2"}
    signed = lbank_v2(form, PAIR, now_ms=1_700_000_000_000, echostr="e" * 35)
    payload = "&".join(f"{k}={signed.form[k]}" for k in sorted(signed.form) if k != "sign")
    md5 = hashlib.md5(payload.encode(), usedforsecurity=False).hexdigest().upper()
    assert signed.form["sign"] == hmac.new(SECRET_KEY.encode(), md5.encode(), "sha256").hexdigest()
    assert signed.form["api_key"] == API_KEY and SECRET_KEY not in json.dumps(signed.form)
    assert signed.headers == {"timestamp": "1700000000000", "signature_method": "HmacSHA256",
                              "echostr": "e" * 35}  # fmt: skip
    assert split_pair(PAIR) == (API_KEY, SECRET_KEY)
    with pytest.raises(ValueError):
        split_pair("no-colon-here")
    acct = Account.model_validate(
        {
            "key": "k1",
            "site": "acct.test",
            "secret": PAIR,
            "inject": {"kind": "signer", "signer": "lbank-v2"},
        }
    )
    assert {PAIR, API_KEY, SECRET_KEY} <= set(acct.secrets())
    assert acct.headers_for("acct.test", {}) == {}  # a signer injects nothing anywhere
    with pytest.raises(ValueError):
        Account.model_validate({"key": "k2", "site": "a.test", "secret": "x",
                                "inject": {"kind": "signer"}})  # fmt: skip
    with pytest.raises(ValueError):
        Account.model_validate({"key": "k3", "site": "a.test", "secret": "x",
                                "inject": {"kind": "bearer", "signer": "lbank-v2"}})  # fmt: skip


async def test_a_signed_pull_reduces_and_never_returns_the_secret(
    lbank: Any, caplog: pytest.LogCaptureFixture
) -> None:
    c, fake, _ = lbank
    caplog.set_level(logging.DEBUG)
    acct = _account(fake)
    span = {"startTime": 1792944000000, "endTime": 1793030399999}
    r = (await c.post("/v1/connectors/call", json=_call(
        "commission/stats/symbol/list", acct, params={**span, "tradeType": 10}))).json()  # fmt: skip
    assert r["outcome"] == "ok", r
    assert r["data"]["rows"] == [
        {"coin": "eth", "amount": "0.01"},
        {"coin": "usdt", "amount": "12"},
    ]
    sent = fake.seen[-1]
    assert (
        sent["method"] == "POST"
        and sent["path"] == "/affiliate-api/v2/commission/stats/symbol/list"
    )
    assert sent["form"]["tradeType"] == "10" and sent["headers"]["signature_method"] == "HmacSHA256"
    assert [e["host"] for e in r["entries"]] == ["acct.test"] and r["entries"][0][
        "tool"
    ] == "revenue.pull"
    # The team list: per invitee the UID, the day and meets_minimum only; the
    # balance, the e-mail and the name never leave egress.
    r = (await c.post("/v1/connectors/call", json=_call(
        "invite/user/team/list", acct, params={**span, "start": 0, "pageSize": 100},
        local={"min_balance": "100"}))).json()  # fmt: skip
    assert r["outcome"] == "ok" and r["data"]["total"] == 150 and len(r["data"]["rows"]) == 100
    assert set(r["data"]["rows"][0]) == {"uid", "invited_on", "meets_minimum"}
    assert [x["meets_minimum"] for x in r["data"]["rows"][:2]] == [False, True]
    assert r["data"]["rows"][0]["invited_on"] == "2026-10-26"
    blob = json.dumps(r)
    assert "150" not in blob.replace('"total": 150', "") and "Ali" not in blob and "@" not in blob
    # referral.check's endpoint: {invitee, meets_minimum}, never a balance.
    r = (await c.post("/v1/connectors/call", json=_call(
        "invite/user/info", acct, tool="referral.check", params={"uid": "90000001"},
        local={"min_balance": "100"}))).json()  # fmt: skip
    assert r["data"] == {"invitee": True, "meets_minimum": True}
    r = (await c.post("/v1/connectors/call", json=_call(
        "invite/user/info", acct, tool="referral.check", params={"uid": "12345"},
        local={"min_balance": "100"}))).json()  # fmt: skip
    assert r["data"] == {"invitee": False, "meets_minimum": None}
    # A hostile answer that carries the api key back: scrubbed.
    fake.echo_key = True
    r = (await c.post("/v1/connectors/call", json=_call(
        "invite/user/team/list", acct, params={**span, "start": 0, "pageSize": 100}))).json()  # fmt: skip
    assert r["outcome"] == "ok" and r["data"]["rows"][0]["uid"] == "[secret]"
    # Nothing anywhere holds the secret: answers, entries, logs.
    logs = "\n".join(rec.getMessage() for rec in caplog.records)
    for s in (PAIR, API_KEY, SECRET_KEY):
        assert s not in json.dumps(r) and s not in logs
    # The public market API: no account, GET, the close.
    r = (await c.post("/v1/connectors/call", json=_call(
        "kline", None, params={"symbol": "eth_usdt", "size": 1, "type": "day1", "time": 1792944000}))).json()  # fmt: skip
    assert r["outcome"] == "ok" and r["data"]["close"] == "2000"
    assert fake.seen[-1]["method"] == "GET" and "api_key" not in fake.seen[-1]["path"]


async def test_connector_refusals(lbank: Any) -> None:
    c, fake, _ = lbank
    acct = _account(fake)
    cases = [
        (_call("money/withdraw", acct), "unknown_endpoint"),
        ({**_call("trade/user/team", acct), "adapter": "lbank-trading"}, "unknown_endpoint"),
        (_call("trade/user/team", None), "policy_denied"),  # a signed endpoint needs its signer
        (_call("trade/user/team", {**acct, "inject": {"kind": "bearer"}}), "policy_denied"),
        (
            _call("kline", acct, params={"symbol": "eth_usdt"}),
            "policy_denied",
        ),  # keyless stays keyless
        (_call("trade/user/team", acct, params={"withdraw": 1}), "invalid_args"),
        (_call("trade/user/team", acct, local={"min_balance": 1}), "invalid_args"),
    ]
    for body, code in cases:
        r = (await c.post("/v1/connectors/call", json=body)).json()
        assert r["code"] == code, (body["endpoint"], r)
        assert PAIR not in json.dumps(r) and SECRET_KEY not in json.dumps(r)
    # A bad signature (another secret): LBank's error code only, never its text.
    r = (await c.post("/v1/connectors/call", json=_call(
        "trade/user/team", {**acct, "secret": "ak-other:sk-other-secret"}))).json()  # fmt: skip
    assert (r["outcome"], r["code"], r["data"]) == (
        "error",
        "upstream_error",
        {"error_code": 10002},
    )
    assert "bad sign" not in json.dumps(r) and "ak-other" not in json.dumps(r)
    r = (await c.post("/v1/connectors/call", json=_call(
        "trade/user/team", {**acct, "secret": "no-colon"}))).json()  # fmt: skip
    assert r["code"] == "account_not_configured" and "no-colon" not in json.dumps(r)
    # A missing page is an error the hub records as an incomplete day.
    fake.missing_page = 1
    r = (await c.post("/v1/connectors/call", json=_call(
        "invite/user/team/list", acct, params={"start": 100, "pageSize": 100}))).json()  # fmt: skip
    assert (r["code"], r["data"]) == ("upstream_error", {"error_code": 10009})


@pytest.mark.parametrize("tool", ["/v1/http", "/v1/read", "/v1/browse"])
async def test_a_signer_account_is_refused_outside_a_connector(lbank: Any, tool: str) -> None:
    c, fake, _ = lbank
    url = f"https://acct.test:{fake.port}/affiliate-api/v2/trade/user/team"
    body: dict[str, Any] = {"ctx": _ctx(cls="A2"), "account": _account(fake)}
    if tool == "/v1/http":
        body.update(method="GET", url=url)
    elif tool == "/v1/read":
        body["url"] = url
    else:
        body["steps"] = [{"do": "goto", "url": url}]
    n = len(fake.seen)
    r = (await c.post(tool, json=body)).json()
    assert (r["outcome"], r["code"]) == ("blocked", "policy_denied"), r
    assert r["entries"][0]["blocked_reason"] == "policy_denied" and len(fake.seen) == n
    assert PAIR not in json.dumps(r)


async def test_the_documented_rate_limit_is_a_bucket_per_account() -> None:
    b = K.Bucket(5, 10.0)
    assert [await b.take(0) for _ in range(5)] == [0.0] * 5
    wait = await b.take(0)
    assert 1.5 < wait <= 2.0  # one token every 2 s
    buckets = K.Buckets()
    assert buckets.of(K.LBANK, "a") is buckets.of(K.LBANK, "a")
    assert buckets.of(K.LBANK, "a") is not buckets.of(K.LBANK, "b")


async def test_a_busy_account_answers_rate_limited(lbank: Any) -> None:
    c, fake, state = lbank
    acct = _account(fake)
    bucket = state.rates.of(K.LBANK, acct["key"])
    bucket.tokens = 0.0
    r = (await c.post("/v1/connectors/call", json=_call("trade/user/team", acct))).json()
    assert (r["outcome"], r["code"]) == ("error", "rate_limited") and r["data"][
        "retry_after_s"
    ] >= 1
    assert not fake.seen


def test_reductions_refuse_shapes_they_do_not_know() -> None:
    with pytest.raises(K.Malformed):
        K.commission({"list": [{"coin": "eth"}]}, {})
    with pytest.raises(K.Malformed):
        K.team({"list": [{"uid": "x y"}]}, {})
    with pytest.raises(K.Malformed):
        K.kline([], {})
    assert K.succeeded({"result": True, "error_code": 0}) == (True, 0)
    assert K.succeeded({"result": "true", "error_code": "10001"}) == (False, 10001)
    assert K.succeeded(["x"]) == (False, None)
    assert K.trade({"volume": "1.50", "fee": None}, {}) == {
        "volume_usdt": "1.5", "fees_usdt": None, "active_traders": None,
    }  # fmt: skip
