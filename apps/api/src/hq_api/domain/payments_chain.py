"""⟨1.15⟩ Prompt 24 (contract §33.2): the public chain, read through egress (`chain-read`).

The worker (or an owner's explicit read) calls egress with a network and a public address; egress
answers one page of USDT transfers TO that address, normalised. This module walks the pages (at
most `max_pages_per_read` per read), stores the transfers, and keeps how far the scan has covered
(`scan_from_at`, `scanned_to_at`) so a payment is called `ledger_only` only where the scan really
looked. The thresholds, the lookback and the overlap are data (seed/payments/chain.yaml).
No key is needed; an optional TronGrid key is read from OpenBao for one call and never kept.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

import httpx

from hq_api.db import Tx
from hq_api.domain import payments as P
from hq_common.openbao import OpenBaoError, SecretNotFound

log = logging.getLogger("hq_api.payments.chain")

TIMEOUT_S = 40.0
CHANNEL = "chain-read"

ERROR_FA = {
    "rate_limited": "سرویس عمومی زنجیره فعلاً محدودیت گذاشت؛ دفعه‌ی بعد دوباره خوانده میشود.",
    "range_too_large": "گره عمومی زنجیره بازه‌ی خواندن را زیاد دانست؛ دفعه‌ی بعد دوباره خوانده میشود.",
    "upstream_error": "گره عمومی زنجیره پاسخ درست نداد؛ دفعه‌ی بعد دوباره خوانده میشود.",
    "call_timeout": "گره عمومی زنجیره دیر پاسخ داد؛ دفعه‌ی بعد دوباره خوانده میشود.",
    "egress_down": "سرویس egress در دسترس نیست؛ زنجیره خوانده نشد.",
}


class Egress(Protocol):
    async def call(self, hub: Any, body: dict[str, Any]) -> dict[str, Any]: ...


class EgressChain:
    """POST /v1/chain/read on egress (the worker is on hq-egress-api)."""

    async def call(self, hub: Any, body: dict[str, Any]) -> dict[str, Any]:
        url = hub.settings.support_egress_url.rstrip("/") + "/v1/chain/read"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as http:
                resp = await http.post(url, json=body)
            out = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("chain egress call failed", extra={"error": type(exc).__name__})
            return {"outcome": "error", "code": "egress_down", "data": None}
        if not isinstance(out, dict):
            return {"outcome": "error", "code": "egress_down", "data": None}
        return out


OVERRIDE: Egress | None = None  # tests put a fake egress here


def egress() -> Egress:
    return OVERRIDE or EgressChain()


class ChainReadError(Exception):
    """A read that failed: the stable code and the plain Persian reason."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
        self.reason_fa = ERROR_FA.get(code, ERROR_FA["upstream_error"])


async def api_key(hub: Any) -> str | None:
    """The optional TronGrid key for one call; None when the owner never added one."""
    bao = getattr(hub, "bao", None)
    if bao is None:
        return None
    try:
        data = await bao.read_kv(P.cfg()["read"]["api_key_path"])
    except SecretNotFound:
        return None
    except OpenBaoError:
        log.warning("openbao could not be read for a chain call")
        return None
    return str(data.get("secret") or "").strip() or None


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


async def _call(hub: Any, body: dict[str, Any], key: str | None) -> dict[str, Any]:
    if key:
        body = {**body, "key": key}
    out = await egress().call(hub, {"channel": CHANNEL, **body})
    del body
    if out.get("outcome") != "ok" or not isinstance(out.get("data"), dict):
        raise ChainReadError(str(out.get("code") or "upstream_error"))
    data: dict[str, Any] = out["data"]
    return data


async def store_page(tx: Tx, src: dict[str, Any], page: dict[str, Any]) -> int:
    """The page's transfers into money.chain_transfers (a later scan only raises the
    confirmations); returns the transfers that were new."""
    new = 0
    for t in page.get("transfers") or []:
        row = await tx.one(
            """INSERT INTO money.chain_transfers (company_id, source_id, network, tx_hash, idx,
                   from_address, to_address, amount_usdt, block, confirmations, at)
               VALUES (:co, :s, :n, :h, :i, :f, :t, :a, :b, :c, :at)
               ON CONFLICT (source_id, tx_hash, idx) DO UPDATE SET
                   block = EXCLUDED.block,
                   confirmations = GREATEST(money.chain_transfers.confirmations,
                                            EXCLUDED.confirmations)
               RETURNING (xmax = 0) AS inserted""",
            co=src["company_id"],
            s=src["id"],
            n=src["network"],
            h=str(t["tx_hash"]).lower(),
            i=int(t.get("idx") or 0),
            f=str(t["from"]),
            t=str(t["to"]),
            a=Decimal(str(t["amount_usdt"])),
            b=int(t["block"]),
            c=int(t["confirmations"]),
            at=_at(str(t["at"])),
        )
        new += 1 if row["inserted"] else 0
    return new


def _start(net: str, head: dict[str, Any]) -> tuple[int, datetime]:
    """Where the first scan of a new address starts: the lookback, in blocks (BSC) or in
    milliseconds (TRON), and the time it corresponds to."""
    conf = P.networks()[net]
    head_at = _at(str(head["head_at"]))
    back = timedelta(days=int(conf["lookback_days"]))
    from_at = head_at - back
    if net == "bsc_usdt":
        block_s = max(float(head.get("block_s") or 3.0), 0.1)
        return max(0, int(head["head"]) - int(back.total_seconds() / block_s)), from_at
    return int(from_at.timestamp() * 1000), from_at


def _caught_up(net: str, scan_next: int) -> int:
    """After a scan reached the head, the next one restarts this far back (the overlap)."""
    conf = P.networks()[net]
    if net == "bsc_usdt":
        return max(0, scan_next - int(conf["overlap_blocks"]))
    return max(0, scan_next - int(conf["overlap_seconds"]) * 1000)


async def read_chain(hub: Any, source_id: Any) -> dict[str, Any]:
    """Reads one chain source up to `max_pages_per_read` pages. Each page is stored in its own
    transaction, so a failure keeps what was read. Returns {"transfers", "pages", "done"} and
    raises ChainReadError (the source is then marked with its plain reason first)."""
    conf = P.cfg()["read"]
    ids = await hub.companies.ids()
    async with hub.db.tx(ids) as tx:
        src = await P.load_source(tx, source_id)
    net = src["network"]
    nconf = P.networks()[net]
    key = await api_key(hub) if net == "trc20_usdt" else None
    out = {"transfers": 0, "pages": 0, "done": False}
    try:
        scan_next, fingerprint = src["scan_next"], src["scan_fingerprint"]
        first_from: datetime | None = None
        if scan_next is None:
            head = await _call(hub, {"op": "head", "network": net}, key)
            scan_next, first_from = _start(net, head)
        while out["pages"] < int(conf["max_pages_per_read"]):
            body: dict[str, Any] = {"op": "scan", "network": net, "address": src["address"]}
            if net == "bsc_usdt":
                body |= {"from_block": scan_next, "max_span": int(nconf["span_blocks"])}
            else:
                body |= {"since_ms": scan_next}
                if fingerprint:
                    body["fingerprint"] = fingerprint
            page = await _call(hub, body, key)
            out["pages"] += 1
            done = bool(page.get("done"))
            scan_next = int(page["scan_next"])
            fingerprint = page.get("scan_fingerprint")
            if done:
                scan_next, fingerprint = _caught_up(net, scan_next), None
            async with hub.db.tx(ids) as tx:
                out["transfers"] += await store_page(tx, src, page)
                await P.mark(
                    tx,
                    src,
                    error_fa=None,
                    read=done,
                    scan_next=scan_next,
                    scan_fingerprint=fingerprint,
                    scanned_to_at=_at(str(page["scanned_to_at"])),
                    **({"scan_from_at": first_from} if first_from is not None else {}),
                )
            first_from = None  # (set once, with the first page)
            if done:
                out["done"] = True
                break
    except ChainReadError as exc:
        async with hub.db.tx(ids) as tx:
            await P.mark(tx, src, error_fa=exc.reason_fa, read=False)
        raise
    return out
