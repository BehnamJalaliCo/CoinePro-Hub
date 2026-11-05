"""POST /v1/chain/read (prompt 24, contract §33.2): the `chain-read` channel against recorded fake
answers of the public BSC nodes and TronGrid (no real call: the fetcher's client is a mock
transport; the guard still checks every name and address). Only the allow-listed hosts are ever
called; transfers are normalised to {tx_hash, idx, from, to, amount_usdt, block, confirmations,
at} with the amount a decimal string; an optional API key goes in a header only and never comes
back; the chain's refusals become stable codes."""

from __future__ import annotations

import ipaddress
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from hq_egress import chain_read as C
from hq_egress.app import State, build_app
from hq_egress.config import Settings
from hq_egress.guard import Guard
from hq_egress.net import Fetcher
from hq_egress.proxy import Buckets

LOCAL = ipaddress.ip_network("127.0.0.1/32")
HUB = "hq.coinepro.com"
BSC_HOSTS = ("bsc-dataseed.binance.org", "bsc-rpc.publicnode.com")
TRON_HOST = "api.trongrid.io"
# fake addresses (a pattern, nobody's wallet)
BSC_TO = "0x" + "ab" * 20
BSC_FROM = "0x" + "cd" * 20
TRON_TO = "T" + "A" * 33
TRON_FROM = "T" + "B" * 33
KEY = "tg-" + "K" * 30  # an API key's shape (fake)
HEAD = 50_000
HEAD_TS = 1_800_000_000  # 2027-01-15T08:00:00Z


def hx(n: int) -> str:
    return hex(n)


def block(n: int, ts: int) -> dict[str, Any]:
    return {"number": hx(n), "timestamp": hx(ts)}


def topic_to(address: str) -> str:
    return "0x" + "0" * 24 + address[2:].lower()


def bsc_log(
    tx: str, block_no: int, idx: int, usdt_wei: int, *, sender: str = BSC_FROM, to: str = BSC_TO
) -> dict[str, Any]:
    return {
        "address": C.BSC_USDT.upper().replace("0X", "0x"),  # a node may answer in any case
        "topics": [C.TRANSFER_TOPIC, topic_to(sender), topic_to(to)],
        "data": hx(usdt_wei),
        "blockNumber": hx(block_no),
        "transactionHash": tx,
        "logIndex": hx(idx),
        "removed": False,
    }


TX1 = "0x" + "11" * 32
TX2 = "0x" + "22" * 32
TX3 = "0x" + "33" * 32
TRON_TX1 = "a1" * 32
TRON_TX2 = "b2" * 32
TRON_OLD = "c3" * 32


class Chain:
    """The fake nodes: BSC JSON-RPC by method, TronGrid by path. Everything seen is recorded."""

    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []
        self.bsc_logs: list[dict[str, Any]] = []
        self.bsc_down: set[str] = set()
        self.bsc_error: dict[str, Any] | None = None
        self.tron_rows: list[dict[str, Any]] = []
        self.tron_meta: dict[str, Any] = {}
        self.tron_status = 200
        self.tron_blocks = {TRON_TX1: 49_990, TRON_TX2: 49_999}
        self.block_times = {HEAD: HEAD_TS, 49_990: HEAD_TS - 60, 49_000: HEAD_TS - 3000}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        assert request.url.scheme == "https"
        host = request.url.host
        if host in BSC_HOSTS:
            return self.bsc(host, request)
        assert host == TRON_HOST, host
        return self.tron(request)

    # ---- BSC
    def bsc(self, host: str, request: httpx.Request) -> httpx.Response:
        assert "TRON-PRO-API-KEY" not in request.headers
        if host in self.bsc_down:
            return httpx.Response(503, text="<html>down</html>")
        doc = json.loads(request.content)
        method, params = doc["method"], doc["params"]
        if method == "eth_getBlockByNumber":
            n = HEAD if params[0] == "latest" else int(params[0], 16)
            ts = self.block_times.get(n, HEAD_TS - (HEAD - n) * 3)
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": block(n, ts)})
        assert method == "eth_getLogs"
        if self.bsc_error:
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": self.bsc_error})
        flt = params[0]
        assert flt["address"] == C.BSC_USDT and flt["topics"][0] == C.TRANSFER_TOPIC
        assert flt["topics"][1] is None and flt["topics"][2] == topic_to(BSC_TO)
        lo, hi = int(flt["fromBlock"], 16), int(flt["toBlock"], 16)
        hits = [x for x in self.bsc_logs if lo <= int(x["blockNumber"], 16) <= hi]
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": hits})

    # ---- TRON
    def tron(self, request: httpx.Request) -> httpx.Response:
        if self.tron_status != 200:
            return httpx.Response(self.tron_status, json={"Error": "x"})
        path = request.url.path
        if path == "/wallet/getnowblock":
            return httpx.Response(
                200,
                json={"block_header": {"raw_data": {"number": HEAD, "timestamp": HEAD_TS * 1000}}},
            )
        if path == "/wallet/gettransactioninfobyid":
            tx = json.loads(request.content)["value"]
            n = self.tron_blocks.get(tx)
            return httpx.Response(200, json={"id": tx, **({"blockNumber": n} if n else {})})
        assert request.method == "GET"
        assert path == f"/v1/accounts/{TRON_TO}/transactions/trc20"
        q = dict(request.url.params)
        assert q["only_to"] == "true" and q["contract_address"] == C.TRON_USDT
        assert q["order_by"] == "block_timestamp,asc" and q["limit"] == "200"
        body: dict[str, Any] = {"data": self.tron_rows, "success": True, "meta": self.tron_meta}
        return httpx.Response(200, json=body)


def tron_row(
    tx: str, ts: int, value: int, *, token: str = C.TRON_USDT, to: str = TRON_TO
) -> dict[str, Any]:
    return {
        "transaction_id": tx,
        "token_info": {"symbol": "USDT", "address": token, "decimals": 6, "name": "Tether USD"},
        "block_timestamp": ts * 1000,
        "from": TRON_FROM,
        "to": to,
        "type": "Transfer",
        "value": str(value),
    }


@pytest.fixture
async def egress() -> AsyncIterator[tuple[httpx.AsyncClient, Chain]]:
    table = {h: ["142.250.0.95"] for h in (*BSC_HOSTS, TRON_HOST)}

    async def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise OSError("no such name")
        return table[host]

    guard = Guard(hub_hosts=frozenset({HUB}), resolver=resolve)
    chain = Chain()
    fetcher = Fetcher(guard, 5)
    await fetcher.http.aclose()
    fetcher.http = httpx.AsyncClient(transport=httpx.MockTransport(chain), follow_redirects=False)
    settings = Settings(api_clients=(LOCAL,), hub_hosts=frozenset({HUB}))
    state = State(settings, guard, Buckets(), fetcher=fetcher)
    transport = httpx.ASGITransport(app=build_app(state), client=("127.0.0.1", 5555))
    async with httpx.AsyncClient(transport=transport, base_url="http://egress") as c:
        yield c, chain
    await fetcher.aclose()


def bsc_call(op: str = "scan", **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"channel": "chain-read", "op": op, "network": "bsc_usdt"}
    if op == "scan":
        body |= {"address": BSC_TO, "from_block": 49_000}
    return body | over


def tron_call(op: str = "scan", **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"channel": "chain-read", "op": op, "network": "trc20_usdt"}
    if op == "scan":
        body |= {"address": TRON_TO, "since_ms": (HEAD_TS - 86_400) * 1000}
    return body | over


async def post(c: httpx.AsyncClient, body: dict[str, Any]) -> dict[str, Any]:
    r = await c.post("/v1/chain/read", json=body)
    assert r.status_code == 200, r.text
    assert KEY not in r.text
    out: dict[str, Any] = r.json()
    return out


# ------------------------------------------------------------------- BSC --
async def test_bsc_head(egress: tuple[httpx.AsyncClient, Chain]) -> None:
    c, chain = egress
    out = await post(c, bsc_call("head"))
    assert out["outcome"] == "ok" and out["code"] is None
    assert out["data"] == {"network": "bsc_usdt", "head": HEAD, "head_at": "2027-01-15T08:00:00Z"}
    assert [e["host"] for e in out["entries"]] == [BSC_HOSTS[0]]
    assert {r.url.host for r in chain.seen} <= set(BSC_HOSTS)


async def test_bsc_scan_normalises_the_transfers_and_counts_confirmations_by_code(
    egress: tuple[httpx.AsyncClient, Chain],
) -> None:
    c, chain = egress
    # 25.5 USDT in a block 10 behind the head; 1000 USDT 1010 blocks back (two logs, one tx)
    chain.bsc_logs = [
        bsc_log(TX2, 49_990, 7, 25_500_000_000_000_000_000),
        bsc_log(TX1, 49_000, 3, 1_000 * 10**18),
        bsc_log(TX1, 49_000, 4, 5 * 10**17),
    ]
    out = await post(c, bsc_call())
    assert out["outcome"] == "ok"
    d = out["data"]
    assert d["head"] == HEAD and d["done"] is True and d["scan_next"] == HEAD + 1
    assert d["scan_fingerprint"] is None and d["scanned_to_at"] == d["head_at"]
    assert d["transfers"] == [
        {"tx_hash": TX1, "idx": 3, "from": BSC_FROM, "to": BSC_TO, "amount_usdt": "1000",
         "block": 49_000, "confirmations": 1000, "at": "2027-01-15T07:10:00Z"},
        {"tx_hash": TX1, "idx": 4, "from": BSC_FROM, "to": BSC_TO, "amount_usdt": "0.5",
         "block": 49_000, "confirmations": 1000, "at": "2027-01-15T07:10:00Z"},
        {"tx_hash": TX2, "idx": 7, "from": BSC_FROM, "to": BSC_TO, "amount_usdt": "25.5",
         "block": 49_990, "confirmations": 10, "at": "2027-01-15T07:59:00Z"},
    ]  # fmt: skip
    assert all(isinstance(t["amount_usdt"], str) for t in d["transfers"])


async def test_bsc_scan_is_paged_by_block_range(egress: tuple[httpx.AsyncClient, Chain]) -> None:
    c, chain = egress
    chain.bsc_logs = [bsc_log(TX1, 49_000, 0, 10**18), bsc_log(TX2, 49_900, 0, 2 * 10**18)]
    out = await post(c, bsc_call(from_block=48_000, max_span=1_500))  # 48000..49499
    d = out["data"]
    assert [t["tx_hash"] for t in d["transfers"]] == [TX1]
    assert d["scan_next"] == 49_500 and d["done"] is False
    assert d["scanned_to_at"] != d["head_at"]
    out = await post(c, bsc_call(from_block=d["scan_next"], max_span=1_500))
    d = out["data"]
    assert [t["tx_hash"] for t in d["transfers"]] == [TX2]
    assert d["scan_next"] == HEAD + 1
    assert d["done"] is True


async def test_bsc_scan_past_the_head_waits(egress: tuple[httpx.AsyncClient, Chain]) -> None:
    c, _ = egress
    out = await post(c, bsc_call(from_block=HEAD + 10))
    assert out["data"]["transfers"] == [] and out["data"]["done"] is True
    assert out["data"]["scan_next"] == HEAD + 10


async def test_bsc_scan_cuts_at_a_whole_block_when_busy(
    egress: tuple[httpx.AsyncClient, Chain],
) -> None:
    c, chain = egress
    chain.bsc_logs = [bsc_log(TX1, 49_000 + i, 0, 10**18) for i in range(150)]
    out = await post(c, bsc_call(max_span=1_000))
    d = out["data"]
    assert len(d["transfers"]) == C.MAX_LOGS
    assert d["done"] is False and d["scan_next"] == 49_000 + C.MAX_LOGS


async def test_bsc_falls_over_to_the_next_node(egress: tuple[httpx.AsyncClient, Chain]) -> None:
    c, chain = egress
    chain.bsc_down = {BSC_HOSTS[0]}
    chain.bsc_logs = [bsc_log(TX1, 49_990, 0, 10**18)]
    out = await post(c, bsc_call())
    assert out["outcome"] == "ok" and len(out["data"]["transfers"]) == 1
    assert {r.url.host for r in chain.seen} == set(BSC_HOSTS)


async def test_bsc_node_refusals_are_stable_codes(egress: tuple[httpx.AsyncClient, Chain]) -> None:
    c, chain = egress
    chain.bsc_error = {"code": -32005, "message": "query returned more than 10000 results"}
    out = await post(c, bsc_call())
    assert out["outcome"] == "error" and out["code"] == "range_too_large" and out["data"] is None
    chain.bsc_error = {"code": -32000, "message": "internal"}
    assert (await post(c, bsc_call()))["code"] == "upstream_error"
    chain.bsc_down = set(BSC_HOSTS)
    assert (await post(c, bsc_call()))["code"] == "upstream_error"


async def test_a_log_that_is_not_ours_is_an_upstream_error(
    egress: tuple[httpx.AsyncClient, Chain],
) -> None:
    c, chain = egress
    bad = bsc_log(TX1, 49_990, 0, 10**18)
    bad["topics"][2] = topic_to("0x" + "ee" * 20)  # not to our address
    chain.bsc_logs = [bad]
    assert (await post(c, bsc_call()))["code"] == "upstream_error"


# ------------------------------------------------------------------ TRON --
async def test_tron_head_and_the_optional_key_in_a_header_only(
    egress: tuple[httpx.AsyncClient, Chain],
) -> None:
    c, chain = egress
    out = await post(c, tron_call("head", key=KEY))
    assert out["data"] == {"network": "trc20_usdt", "head": HEAD, "head_at": "2027-01-15T08:00:00Z"}
    (seen,) = chain.seen
    assert seen.headers["TRON-PRO-API-KEY"] == KEY
    assert KEY not in str(seen.url) and KEY not in seen.content.decode()
    out = await post(c, tron_call("head"))  # no key needed
    assert out["outcome"] == "ok"
    assert "TRON-PRO-API-KEY" not in chain.seen[-1].headers


async def test_tron_scan_normalises_and_filters(egress: tuple[httpx.AsyncClient, Chain]) -> None:
    c, chain = egress
    chain.tron_rows = [
        tron_row(TRON_OLD, HEAD_TS - 5 * 3600, 49_000_000),  # 49 USDT, five hours old
        tron_row(TRON_TX1, HEAD_TS - 60, 29_990_000),  # 29.99
        tron_row("d4" * 32, HEAD_TS - 50, 5_000_000, token="T" + "Z" * 33),  # another token
        tron_row("e5" * 32, HEAD_TS - 40, 5_000_000, to=TRON_FROM),  # not to our address
        tron_row(TRON_TX2, HEAD_TS - 10, 1_000_000_000_000),  # 1,000,000 USDT
    ]
    out = await post(c, tron_call(key=KEY))
    assert out["outcome"] == "ok"
    d = out["data"]
    assert d["done"] is True and d["scan_fingerprint"] is None
    assert d["scan_next"] == HEAD_TS * 1000 and d["scanned_to_at"] == d["head_at"]
    got = {t["tx_hash"]: t for t in d["transfers"]}
    assert set(got) == {TRON_OLD, TRON_TX1, TRON_TX2}
    assert got[TRON_TX1] == {
        "tx_hash": TRON_TX1, "idx": 0, "from": TRON_FROM, "to": TRON_TO, "amount_usdt": "29.99",
        "block": 49_990, "confirmations": 10, "at": "2027-01-15T07:59:00Z",
    }  # fmt: skip
    assert got[TRON_TX2]["amount_usdt"] == "1000000" and got[TRON_TX2]["confirmations"] == 1
    # five hours old: its depth comes from the time, no block lookup was spent on it
    assert got[TRON_OLD]["amount_usdt"] == "49" and got[TRON_OLD]["confirmations"] > 5000
    looked = [
        json.loads(r.content)["value"]
        for r in chain.seen
        if r.url.path == "/wallet/gettransactioninfobyid"
    ]
    assert TRON_OLD not in looked and {TRON_TX1, TRON_TX2} <= set(looked)
    assert {r.url.host for r in chain.seen} == {TRON_HOST}
    assert all(r.headers["TRON-PRO-API-KEY"] == KEY for r in chain.seen)


async def test_tron_scan_is_paged_by_fingerprint(egress: tuple[httpx.AsyncClient, Chain]) -> None:
    c, chain = egress
    chain.tron_rows = [tron_row(TRON_TX1, HEAD_TS - 60, 1_000_000)]
    chain.tron_meta = {"at": 1, "page_size": 1, "fingerprint": "fp-1_ABC"}
    d = (await post(c, tron_call()))["data"]
    assert d["done"] is False and d["scan_fingerprint"] == "fp-1_ABC"
    assert d["scan_next"] == (HEAD_TS - 86_400) * 1000  # the same start; the fingerprint continues
    assert d["scanned_to_at"] == "2027-01-15T07:59:00Z"
    chain.tron_meta = {}
    d = (await post(c, tron_call(fingerprint="fp-1_ABC")))["data"]
    assert d["done"] is True


async def test_tron_refusals_are_stable_codes(egress: tuple[httpx.AsyncClient, Chain]) -> None:
    c, chain = egress
    chain.tron_status = 429
    assert (await post(c, tron_call()))["code"] == "rate_limited"
    chain.tron_status = 500
    assert (await post(c, tron_call()))["code"] == "upstream_error"


# --------------------------------------------------------------- the lists --
@pytest.mark.parametrize(
    ("body", "code"),
    [
        (bsc_call(network="eth_usdt"), "bad_network"),
        (bsc_call(op="send"), "op_not_allowed"),
        (bsc_call(address="0x12"), "bad_address"),
        (bsc_call(address=None), "bad_address"),
        (bsc_call(from_block=None), "bad_range"),
        (bsc_call(max_span=5001), "bad_range"),
        (bsc_call(since_ms=5), "bad_range"),
        (bsc_call(key=KEY), "bad_token"),  # the BSC nodes are keyless
        (bsc_call("head", address=BSC_TO), "op_not_allowed"),
        (tron_call(address=BSC_TO), "bad_address"),
        (tron_call(since_ms=None), "bad_range"),
        (tron_call(from_block=3), "bad_range"),
        (tron_call(fingerprint="no spaces allowed"), "bad_range"),
        (tron_call(key="x"), "bad_token"),
    ],
)
async def test_anything_outside_the_allow_lists_is_blocked_without_a_call(
    egress: tuple[httpx.AsyncClient, Chain], body: dict[str, Any], code: str
) -> None:
    c, chain = egress
    out = await post(c, body)
    assert out["outcome"] == "blocked" and out["code"] == code
    assert chain.seen == []


async def test_a_url_or_an_unknown_field_is_rejected_by_the_shape(
    egress: tuple[httpx.AsyncClient, Chain],
) -> None:
    c, chain = egress
    r = await c.post("/v1/chain/read", json=bsc_call(url="https://evil.example/"))
    assert r.status_code == 422
    assert chain.seen == []


def test_the_hosts_are_data_not_a_url_the_caller_names() -> None:
    s = Settings()
    assert s.chain_bsc_hosts == BSC_HOSTS and s.chain_tron_host == TRON_HOST


def test_amounts_are_decimal_strings() -> None:
    cases: list[tuple[int, int, str]] = [
        (10**18, 18, "1"), (1, 18, "0.000000000000000001"), (0, 6, "0"), (1_500_000, 6, "1.5"),
        (123_456_789_012, 6, "123456.789012"),
    ]  # fmt: skip
    for raw, dec, text in cases:
        assert C._amount(raw, dec) == text
