"""The public chain, read only (prompt 24, contract §33.2): USDT transfers TO an address.

Code calls it (the hub's worker, on hq-egress-api), never an agent. Channel `chain-read`:

    POST /v1/chain/read
      {channel: "chain-read", op: "head" | "scan", network: "bsc_usdt" | "trc20_usdt",
       address?, from_block?, max_span?, since_ms?, fingerprint?, key?}
      -> {outcome: ok | blocked | error, code, data, entries}

head  the chain's head: {head, head_at, block_s} (block_s: the measured seconds per block, so the
      caller can say how many blocks a number of days is).
scan  one page of USDT transfers to `address`, normalised to
        {tx_hash, idx, from, to, amount_usdt (a decimal string), block, confirmations, at}
      BSC: one `eth_getLogs` over [from_block, from_block + max_span) on the USDT BEP20 contract,
           Transfer topic, `to` = the address; the block times come from `eth_getBlockByNumber`.
      TRON: TronGrid's TRC20 transfers of the address (`only_to`), oldest first from `since_ms`
           (paged by `fingerprint`), each block read with `gettransactioninfobyid`.
      The answer also says where to continue (`scan_next` a block or a millisecond, and
      `scan_fingerprint`), the time the scan has reached (`scanned_to_at`) and whether it caught up
      with the head (`done`). Confirmations are head - block, by code; the thresholds (BSC 15,
      TRON 20) are the hub's data, not here.

Only the hosts of the settings are ever called (the public BSC JSON-RPC nodes and TronGrid), over
https on 443; the call names a network and an address, never a URL. No key is needed. An API key
for TronGrid's rate limit, if the owner adds one, arrives with the call (the hub reads it from
OpenBao for this one call; egress holds no secret of its own), goes in the `TRON-PRO-API-KEY`
header only and never into an entry, a log line, an error or the answer (scrubbed in every form).
The chain's own refusals are reduced to stable codes: `rate_limited`, `range_too_large`,
`upstream_error`; `blocked` is for anything outside the allow-lists here (`bad_network`,
`bad_address`, `bad_range`, `bad_token`, `op_not_allowed`) and the guard's own reasons.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from hq_egress.accounts import scrub
from hq_egress.guard import Blocked
from hq_egress.net import CALL_ENTRIES, Entry, FetchError, track
from hq_egress.proxy import entries_json

log = logging.getLogger("hq_egress.chain")
router = APIRouter()

TOOL = "chain.read"
CLS = "A0"  # public data, nothing is changed anywhere
ANSWER_MAX = 4 * 1024 * 1024
# The USDT token contracts (public) and the ERC-20 Transfer(address,address,uint256) topic.
BSC_USDT = "0x55d398326f99059ff775485246999027b3197955"
TRON_USDT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
DECIMALS = {"bsc_usdt": 18, "trc20_usdt": 6}
BSC_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
TRON_ADDRESS = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
KEY = re.compile(r"^[A-Za-z0-9._~-]{8,200}$")
FINGERPRINT = re.compile(r"^[A-Za-z0-9_=+/.-]{1,500}$")
TX_HEX = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_SPAN = 5000
MAX_LOGS = 100  # transfers of one answer (whole blocks only)
MAX_ENRICH = 30  # TRON: transactions whose block is looked up in one answer
PAGE = 200  # TRON page size


class CallIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Literal["chain-read"]
    op: str = Field(min_length=1, max_length=20)
    network: str = Field(min_length=1, max_length=20)
    address: str | None = Field(default=None, max_length=100)
    from_block: int | None = Field(default=None, ge=0, le=2**53)
    max_span: int | None = Field(default=None, ge=1, le=100_000)
    since_ms: int | None = Field(default=None, ge=0, le=2**53)
    fingerprint: str | None = Field(default=None, max_length=600)
    key: str | None = Field(default=None, max_length=300, repr=False)


class Refused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Upstream(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _answer(
    outcome: str, data: Any, entries: list[Entry], code: str | None, key: str | None
) -> JSONResponse:
    body = {
        "outcome": outcome,
        "code": code,
        "data": scrub(data, [key] if key else []),
        "entries": entries_json(entries),
    }
    return JSONResponse(body, status_code=200)


def _iso(seconds: int | float) -> str:
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _amount(raw: int, decimals: int) -> str:
    d = Decimal(raw).scaleb(-decimals)
    return format(d.normalize(), "f") if d != 0 else "0"


def _hex_int(value: Any) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{1,64}", value):
        raise Upstream("upstream_error")
    return int(value, 16)


# ------------------------------------------------------------ the request --
def _checked(a: CallIn) -> None:
    """Refused (a stable code) unless the call is inside the allow-lists."""
    if a.op not in ("head", "scan"):
        raise Refused("op_not_allowed")
    if a.network not in DECIMALS:
        raise Refused("bad_network")
    if a.key is not None and not KEY.match(a.key):
        raise Refused("bad_token")
    if a.key is not None and a.network != "trc20_usdt":
        raise Refused("bad_token")  # only TronGrid takes a key; the BSC nodes are keyless
    if a.op == "head":
        extras = (a.address, a.from_block, a.max_span, a.since_ms, a.fingerprint)
        if any(v is not None for v in extras):
            raise Refused("op_not_allowed")
        return
    pattern = BSC_ADDRESS if a.network == "bsc_usdt" else TRON_ADDRESS
    if a.address is None or not pattern.match(a.address):
        raise Refused("bad_address")
    if a.network == "bsc_usdt":
        if a.from_block is None or a.since_ms is not None or a.fingerprint is not None:
            raise Refused("bad_range")
        if a.max_span is not None and a.max_span > MAX_SPAN:
            raise Refused("bad_range")
    else:
        if a.since_ms is None or a.from_block is not None or a.max_span is not None:
            raise Refused("bad_range")
        if a.fingerprint is not None and not FINGERPRINT.match(a.fingerprint):
            raise Refused("bad_range")


# ------------------------------------------------------------------ calls --
async def _post_json(
    state: Any, url: str, doc: dict[str, Any], headers: dict[str, str]
) -> tuple[int, Any]:
    target = state.guard.target(url)
    await state.guard.addresses(target.host, target.port)
    got = await state.fetcher.fetch(
        "POST",
        url,
        tool=TOOL,
        cls=CLS,
        headers={"Content-Type": "application/json", "Accept": "application/json", **headers},
        content=json.dumps(doc).encode(),
        max_bytes=ANSWER_MAX,
    )
    if got.truncated:
        raise Upstream("upstream_error")
    try:
        return got.status, json.loads(bytes(got.body).decode("utf-8", "replace") or "null")
    except ValueError:
        return got.status, None


async def _get_json(state: Any, url: str, headers: dict[str, str]) -> tuple[int, Any]:
    target = state.guard.target(url)
    await state.guard.addresses(target.host, target.port)
    got = await state.fetcher.fetch(
        "GET",
        url,
        tool=TOOL,
        cls=CLS,
        headers={"Accept": "application/json", **headers},
        max_bytes=ANSWER_MAX,
    )
    if got.truncated:
        raise Upstream("upstream_error")
    try:
        return got.status, json.loads(bytes(got.body).decode("utf-8", "replace") or "null")
    except ValueError:
        return got.status, None


def _failure(status: int, parsed: Any) -> str:
    if status == 429:
        return "rate_limited"
    if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
        err = parsed["error"]
        text = str(err.get("message") or "").lower()
        if err.get("code") == -32005 or "range" in text or "limit exceeded" in text:
            return "range_too_large"
        if "rate" in text:
            return "rate_limited"
    return "upstream_error"


async def _rpc(state: Any, method: str, params: list[Any]) -> Any:
    """A JSON-RPC call on the first BSC node that answers; the next one after a failure."""
    last = "upstream_error"
    for host in state.settings.chain_bsc_hosts:
        try:
            status, parsed = await _post_json(
                state,
                f"https://{host}/",
                {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                {},
            )
        except FetchError:
            last = "upstream_error"
            continue
        if status == 200 and isinstance(parsed, dict) and "result" in parsed:
            return parsed["result"]
        last = _failure(status, parsed)
        if last == "range_too_large":
            break  # another node would refuse the same range
    raise Upstream(last)


def _block_time(block: Any) -> tuple[int, int]:
    """(number, unix seconds) of an `eth_getBlockByNumber` answer."""
    if not isinstance(block, dict):
        raise Upstream("upstream_error")
    return _hex_int(block.get("number")), _hex_int(block.get("timestamp"))


# -------------------------------------------------------------------- BSC --
async def _bsc_head(state: Any) -> tuple[int, int]:
    return _block_time(await _rpc(state, "eth_getBlockByNumber", ["latest", False]))


async def _bsc_block_s(state: Any, head: int, head_ts: int) -> float:
    """Seconds per block over the last 1 000 blocks (one more node call)."""
    back = min(1000, head)
    if back < 10:
        return 3.0
    _, ts = _block_time(await _rpc(state, "eth_getBlockByNumber", [hex(head - back), False]))
    return round(max(head_ts - ts, 1) / back, 3)


def _padded(address: str) -> str:
    return "0x" + "0" * 24 + address[2:].lower()


def _bsc_log(entry: Any, to: str) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise Upstream("upstream_error")
    topics = entry.get("topics")
    if (
        not isinstance(topics, list)
        or len(topics) != 3
        or str(topics[0]).lower() != TRANSFER_TOPIC
        or str(topics[2]).lower() != _padded(to)
        or str(entry.get("address") or "").lower() != BSC_USDT
        or entry.get("removed") is True
    ):
        raise Upstream("upstream_error")
    tx = str(entry.get("transactionHash") or "").lower()
    if not re.fullmatch(r"0x[0-9a-f]{64}", tx):
        raise Upstream("upstream_error")
    return {
        "tx_hash": tx,
        "idx": _hex_int(entry.get("logIndex")),
        "from": "0x" + str(topics[1])[-40:].lower(),
        "to": to.lower(),
        "raw": _hex_int(entry.get("data")),
        "block": _hex_int(entry.get("blockNumber")),
    }


async def _bsc_scan(state: Any, a: CallIn, entries: list[Entry]) -> dict[str, Any]:
    assert a.address is not None
    assert a.from_block is not None
    head, head_ts = await _bsc_head(state)
    start = a.from_block
    span = min(a.max_span or MAX_SPAN, MAX_SPAN)
    if start > head:
        return {
            "network": a.network, "head": head, "head_at": _iso(head_ts), "transfers": [],
            "scan_next": start, "scan_fingerprint": None, "scanned_to_at": _iso(head_ts),
            "done": True,
        }  # fmt: skip
    end = min(head, start + span - 1)
    got = await _rpc(
        state,
        "eth_getLogs",
        [
            {
                "fromBlock": hex(start),
                "toBlock": hex(end),
                "address": BSC_USDT,
                "topics": [TRANSFER_TOPIC, None, _padded(a.address)],
            }
        ],
    )
    if not isinstance(got, list):
        raise Upstream("upstream_error")
    logs = sorted((_bsc_log(x, a.address) for x in got), key=lambda x: (x["block"], x["idx"]))
    cut = False
    if len(logs) > MAX_LOGS:
        # whole blocks only: stop before the block that would pass the cap
        keep = logs[:MAX_LOGS]
        boundary = keep[-1]["block"]
        if logs[MAX_LOGS]["block"] == boundary:
            keep = [x for x in keep if x["block"] < boundary]
        if not keep:
            keep = [x for x in logs if x["block"] == logs[0]["block"]]
        logs, cut = keep, True
        end = logs[-1]["block"]
    times: dict[int, int] = {head: head_ts}
    for block in sorted({x["block"] for x in logs} - set(times)):
        number, ts = _block_time(await _rpc(state, "eth_getBlockByNumber", [hex(block), False]))
        times[number] = ts
    transfers = [
        {
            "tx_hash": x["tx_hash"],
            "idx": x["idx"],
            "from": x["from"],
            "to": x["to"],
            "amount_usdt": _amount(x["raw"], DECIMALS[a.network]),
            "block": x["block"],
            "confirmations": max(0, head - x["block"]),
            "at": _iso(times[x["block"]]),
        }
        for x in logs
    ]
    if end not in times:
        times[end] = _block_time(await _rpc(state, "eth_getBlockByNumber", [hex(end), False]))[1]
    return {
        "network": a.network,
        "head": head,
        "head_at": _iso(head_ts),
        "transfers": transfers,
        "scan_next": end + 1,
        "scan_fingerprint": None,
        "scanned_to_at": _iso(times[end]),
        "done": end >= head and not cut,
    }


# ------------------------------------------------------------------- TRON --
def _tron_headers(a: CallIn) -> dict[str, str]:
    return {"TRON-PRO-API-KEY": a.key} if a.key else {}


async def _tron_head(state: Any, a: CallIn) -> tuple[int, int]:
    host = state.settings.chain_tron_host
    try:
        status, parsed = await _post_json(
            state, f"https://{host}/wallet/getnowblock", {}, _tron_headers(a)
        )
    except FetchError:
        raise Upstream("upstream_error") from None
    raw = ((parsed or {}).get("block_header") or {}).get("raw_data") if status == 200 else None
    if not isinstance(raw, dict) or not isinstance(raw.get("number"), int):
        raise Upstream(_failure(status, parsed))
    ts = raw.get("timestamp")
    if not isinstance(ts, int):
        raise Upstream("upstream_error")
    return raw["number"], ts // 1000


def _tron_value(row: dict[str, Any], to: str) -> dict[str, Any] | None:
    """A TRC20 transfer row of the address's USDT, else None (another token, another direction)."""
    info = row.get("token_info")
    info = info if isinstance(info, dict) else {}
    if (
        str(info.get("address") or "") != TRON_USDT
        or str(row.get("type") or "Transfer") != "Transfer"
        or str(row.get("to") or "") != to
    ):
        return None
    tx = str(row.get("transaction_id") or "").lower()
    value = str(row.get("value") or "")
    ts = row.get("block_timestamp")
    sender = str(row.get("from") or "")
    if (
        not TX_HEX.match(tx)
        or not value.isdigit()
        or not isinstance(ts, int)
        or not TRON_ADDRESS.match(sender)
    ):
        raise Upstream("upstream_error")
    return {"tx_hash": tx, "from": sender, "raw": int(value), "ts_ms": ts}


async def _tron_block(state: Any, a: CallIn, tx_hash: str) -> int | None:
    host = state.settings.chain_tron_host
    try:
        status, parsed = await _post_json(
            state, f"https://{host}/wallet/gettransactioninfobyid", {"value": tx_hash},
            _tron_headers(a),
        )  # fmt: skip
    except FetchError:
        return None
    if status != 200 or not isinstance(parsed, dict):
        return None
    n = parsed.get("blockNumber")
    return n if isinstance(n, int) and n >= 0 else None


async def _tron_scan(state: Any, a: CallIn, entries: list[Entry]) -> dict[str, Any]:
    assert a.address is not None
    assert a.since_ms is not None
    head, head_ts = await _tron_head(state, a)
    host = state.settings.chain_tron_host
    query = (
        f"only_to=true&contract_address={TRON_USDT}&min_timestamp={a.since_ms}"
        f"&order_by=block_timestamp,asc&limit={PAGE}"
    )
    if a.fingerprint:
        query += f"&fingerprint={a.fingerprint}"
    try:
        status, parsed = await _get_json(
            state, f"https://{host}/v1/accounts/{a.address}/transactions/trc20?{query}",
            _tron_headers(a),
        )  # fmt: skip
    except FetchError:
        raise Upstream("upstream_error") from None
    if status != 200 or not isinstance(parsed, dict) or not isinstance(parsed.get("data"), list):
        raise Upstream(_failure(status, parsed))
    parsed_rows = (_tron_value(x, a.address) for x in parsed["data"] if isinstance(x, dict))
    rows = [r for r in parsed_rows if r]
    meta = parsed.get("meta")
    fingerprint = meta.get("fingerprint") if isinstance(meta, dict) else None
    more = isinstance(fingerprint, str) and bool(FINGERPRINT.match(fingerprint))
    transfers = []
    looked = 0
    for r in rows:
        block: int | None = None
        # a block is looked up only where the confirmation is not obviously deep already
        if (head_ts * 1000 - r["ts_ms"]) < 3 * 3600 * 1000 and looked < MAX_ENRICH:
            looked += 1
            block = await _tron_block(state, a, r["tx_hash"])
        if block is None:
            # older than a few hours: far past any threshold; the time gives the depth
            confirmations = max(0, (head_ts * 1000 - r["ts_ms"]) // 3000)
            block = max(0, head - confirmations)
        else:
            confirmations = max(0, head - block)
        transfers.append(
            {
                "tx_hash": r["tx_hash"],
                "idx": 0,
                "from": r["from"],
                "to": a.address,
                "amount_usdt": _amount(r["raw"], DECIMALS[a.network]),
                "block": block,
                "confirmations": confirmations,
                "at": _iso(r["ts_ms"] // 1000),
            }
        )
    reached = (rows[-1]["ts_ms"] if rows else head_ts * 1000) if more else head_ts * 1000
    return {
        "network": a.network,
        "head": head,
        "head_at": _iso(head_ts),
        "transfers": transfers,
        "scan_next": a.since_ms if more else head_ts * 1000,
        "scan_fingerprint": fingerprint if more else None,
        "scanned_to_at": _iso(reached // 1000),
        "done": not more,
    }


# ---------------------------------------------------------------- the call --
@router.post("/v1/chain/read")
async def chain_read(a: CallIn, request: Request) -> JSONResponse:
    state = request.app.state.egress
    entries: list[Entry] = []
    ctx_token = CALL_ENTRIES.set(entries)
    secret = a.key
    try:
        async with asyncio.timeout(state.settings.call_deadline_s):
            return await _call(state, a, entries)
    except TimeoutError:
        code = "call_timeout"
    except Exception as exc:  # noqa: BLE001 - the answer must still carry the entries
        log.warning("chain.read failed: %s", type(exc).__name__)
        code = "upstream_error"
    finally:
        CALL_ENTRIES.reset(ctx_token)
    for e in entries:
        if e.status is None and e.blocked_reason is None:
            e.blocked_reason = code
    return _answer("error", None, entries, code, secret)


async def _call(state: Any, a: CallIn, entries: list[Entry]) -> JSONResponse:
    secret = a.key
    try:
        _checked(a)
        if a.network == "bsc_usdt":
            if a.op == "head":
                head, ts = await _bsc_head(state)
                data: dict[str, Any] = {
                    "network": a.network,
                    "head": head,
                    "head_at": _iso(ts),
                    "block_s": await _bsc_block_s(state, head, ts),
                }
            else:
                data = await _bsc_scan(state, a, entries)
        elif a.op == "head":
            head, ts = await _tron_head(state, a)
            data = {"network": a.network, "head": head, "head_at": _iso(ts), "block_s": 3.0}
        else:
            data = await _tron_scan(state, a, entries)
    except Refused as r:
        track(Entry(TOOL, "POST", "-", blocked_reason=r.code, cls=CLS))
        return _answer("blocked", None, entries, r.code, secret)
    except Blocked as b:
        track(Entry(TOOL, "POST", "-", blocked_reason=b.reason, cls=CLS))
        return _answer("blocked", None, entries, b.reason, secret)
    except Upstream as u:
        return _answer("error", None, entries, u.code, secret)
    except (InvalidOperation, ValueError, KeyError):
        return _answer("error", None, entries, "upstream_error", secret)
    return _answer("ok", data, entries, None, secret)
