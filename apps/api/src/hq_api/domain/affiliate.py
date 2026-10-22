"""The hub's side of an affiliate connector (prompt 10 §2.3, contract §19.1).

The exchange's own API is spoken only in egress (services/egress
hq_egress/connectors.py: the fixed endpoints, the lbank-v2 signer, the rate
limit and the privacy reductions). This module drives it, one settlement day
at a time, through the worker's only way out:

    worker --(gateway token)--> gateway POST /v1/connectors/call
        gateway --(the worker's api token)--> api POST /internal/v1/egress/connectors/{adapter}/pull
            (the account and its secret for this one call, an egress-log reservation)
        gateway --> egress POST /v1/connectors/call   (signs, sends, reduces, scrubs)
        gateway --> api POST /internal/v1/egress/connectors/{adapter}/log
    worker <-- the reduced data, never the secret

lbank-affiliate-v2, one day D (LBank settles T+1 at UTC+8; D is a UTC+8
calendar day): commission by coin (`tradeType=10`), the team list of D's new
invitees (100 a page, `start + pageSize`), the team's volume and fees, the
deposits, and for each coin other than USDT the day's closing price from the
exchange's public kline (`price_source`). A failed call, an answer of the
wrong shape or a page that never came makes D `complete: false` with its
gaps; a later pull fills it.

Every page's figures (already reduced in egress) and their SHA-256 are kept
in the day's `source.pages`, so PR-103 can reconcile the radar's figures
with them (revenue_checks.py).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import httpx

log = logging.getLogger("hq_api.affiliate")

UTC8 = timezone(timedelta(hours=8))
PAGE_SIZE = 100
MAX_PAGES = 100  # 10 000 new invitees in one day: beyond it the day stays incomplete
SETTLE_HOURS = 0  # LBank: day D is settled from D+1 00:00 UTC+8 (T+1)
INCOMPLETE_ALERT_HOURS = 36
USDT = "usdt"


@dataclass(frozen=True)
class AdapterSpec:
    name: str
    signer: str
    endpoints: tuple[str, ...]


ADAPTERS: dict[str, AdapterSpec] = {
    "lbank-affiliate-v2": AdapterSpec(
        "lbank-affiliate-v2",
        "lbank-v2",
        (
            "commission/stats/symbol/list",
            "invite/user/team/list",
            "trade/user/team",
            "money/detail/list",
            "invite/user/info",
            "kline",
        ),
    )
}
PUBLIC_ENDPOINTS = frozenset({"kline"})  # keyless market data: no account, no secret


class ConnectorError(Exception):
    """A connector call that did not answer ok: a stable code (and its data)."""

    def __init__(self, code: str, data: Any = None) -> None:
        super().__init__(code)
        self.code = code
        self.data = data


class Connector(Protocol):
    async def call(
        self,
        *,
        company: str,
        exchange: str,
        adapter: str,
        endpoint: str,
        tool: str,
        params: dict[str, Any],
        local: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class GatewayConnector:
    """The real connector: the gateway's /v1/connectors/call (worker token),
    carrying the worker's api service token for the gateway's api calls. A
    `rate_limited` answer waits as long as egress says, a few times."""

    def __init__(
        self,
        base_url: str,
        gateway_token: Callable[[], str],
        api_token: Callable[[], str],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 40.0,
        retries: int = 6,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._http = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=timeout_s)
        self._gateway_token = gateway_token
        self._api_token = api_token
        self._retries = retries
        self._sleep = sleep

    async def aclose(self) -> None:
        await self._http.aclose()

    async def call(
        self,
        *,
        company: str,
        exchange: str,
        adapter: str,
        endpoint: str,
        tool: str,
        params: dict[str, Any],
        local: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token, api_token = self._gateway_token(), self._api_token()
        if not token or not api_token:
            raise ConnectorError("not_configured")
        body = {
            "token": api_token,
            "company": company,
            "exchange": exchange,
            "adapter": adapter,
            "endpoint": endpoint,
            "tool": tool,
            "params": params,
            "local": local or {},
        }
        for attempt in range(self._retries + 1):
            try:
                resp = await self._http.post(
                    "/v1/connectors/call",
                    json=body,
                    headers={"Authorization": f"Bearer {token}"},
                )
                out = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ConnectorError("gateway_unreachable") from exc
            if not isinstance(out, dict):
                raise ConnectorError("gateway_bad_answer")
            if out.get("outcome") == "ok" and isinstance(out.get("data"), dict):
                data: dict[str, Any] = out["data"]
                return data
            code = str(out.get("code") or "connector_failed")[:60]
            raw = out.get("data")
            data_out: dict[str, Any] = raw if isinstance(raw, dict) else {}
            if code == "rate_limited" and attempt < self._retries:
                await self._sleep(float(min(30, max(1, int(data_out.get("retry_after_s") or 2)))))
                continue
            raise ConnectorError(code, data_out)
        raise ConnectorError("rate_limited")


# --------------------------------------------------------------- the day --
def day_span(day: date) -> tuple[int, int]:
    """[start, end] of a UTC+8 day in epoch milliseconds (LBank's startTime/endTime)."""
    start = datetime.combine(day, time(0, 0), UTC8)
    end = start + timedelta(days=1) - timedelta(milliseconds=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def settled_at(day: date) -> datetime:
    """When day D is settled (T+1 at UTC+8): D+1 00:00 UTC+8."""
    return datetime.combine(day + timedelta(days=1), time(0, 0), UTC8) + timedelta(
        hours=SETTLE_HOURS
    )


def last_settled_day(now: datetime | None = None) -> date:
    """The most recent settled day (yesterday in UTC+8)."""
    now = now or datetime.now(UTC)
    return now.astimezone(UTC8).date() - timedelta(days=1)


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def page_hash(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class DayPull:
    day: date
    commission: dict[str, Decimal] = field(default_factory=dict)  # coin -> amount
    prices: dict[str, tuple[Decimal, str]] = field(default_factory=dict)  # coin -> (usdt, source)
    deposits: dict[str, Decimal] = field(default_factory=dict)
    fees_usdt: Decimal | None = None
    volume_usdt: Decimal | None = None
    active_traders: int | None = None
    invitees: list[dict[str, Any]] = field(default_factory=list)  # uid, invited_on, meets_minimum
    gaps: list[dict[str, Any]] = field(default_factory=list)
    pages: list[dict[str, Any]] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    requests: int = 0

    @property
    def complete(self) -> bool:
        return not self.gaps

    @property
    def answered(self) -> bool:
        """At least one call answered (else the pull failed for this day)."""
        return bool(self.pages)

    def by_coin(self) -> list[dict[str, Any]]:
        out = []
        for coin, amount in sorted(self.commission.items()):
            price = self.prices.get(coin)
            usdt = (amount * price[0]).quantize(Decimal("0.00000001")) if price else None
            out.append(
                {
                    "coin": coin,
                    "amount": str(amount),
                    "usdt": str(usdt) if usdt is not None else None,
                    "price_source": price[1] if price else None,
                }
            )
        return out

    def commission_usdt(self) -> Decimal:
        total = Decimal(0)
        for row in self.by_coin():
            if row["usdt"] is not None:
                total += Decimal(row["usdt"])
        return total

    def deposits_usdt(self) -> Decimal | None:
        """USDT deposits only are summed (another coin's value would need its
        own price; it is listed in the source, not guessed)."""
        if not self.deposits and "money/detail/list" not in self.endpoints:
            return None
        return self.deposits.get(USDT, Decimal(0))

    def new_invitees(self) -> int:
        return len(self.invitees)

    def min_balance_invitees(self) -> int | None:
        """Of D's new invitees, those whose balance meets the sealed minimum;
        None when no minimum is sealed (meets_minimum unknown for all)."""
        if self.invitees and all(i.get("meets_minimum") is None for i in self.invitees):
            return None
        return sum(1 for i in self.invitees if i.get("meets_minimum") is True)


async def _paged(
    conn: Connector,
    pull: DayPull,
    base: dict[str, Any],
    endpoint: str,
    params: dict[str, Any],
    local: dict[str, Any] | None,
    on_page: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    pull.endpoints.append(endpoint)
    seen = 0
    for page in range(MAX_PAGES):
        try:
            pull.requests += 1
            data = await conn.call(
                **base,
                endpoint=endpoint,
                params={**params, "start": page * PAGE_SIZE, "pageSize": PAGE_SIZE},
                local=local,
            )
        except ConnectorError as e:
            pull.gaps.append({"endpoint": endpoint, "page": page, "error": e.code})
            return
        rows = int(data.get("page_rows") or 0)
        seen += rows
        pull.pages.append(
            {"endpoint": endpoint, "page": page, "sha256": page_hash(data), "rows": rows,
             "sums": on_page(data)}
        )  # fmt: skip
        total = data.get("total")
        if rows < PAGE_SIZE or (isinstance(total, int) and seen >= total):
            return
    pull.gaps.append({"endpoint": endpoint, "page": MAX_PAGES, "error": "too_many_pages"})


async def pull_day(
    conn: Connector,
    *,
    company: str,
    exchange: str,
    adapter: str,
    day: date,
    min_balance: str | None,
) -> DayPull:
    """Every endpoint of one settlement day; nothing is guessed: what did not
    answer is a gap and the day is incomplete."""
    if adapter not in ADAPTERS:
        raise ConnectorError("unknown_adapter")
    pull = DayPull(day)
    start, end = day_span(day)
    span = {"startTime": start, "endTime": end}
    base: dict[str, Any] = {
        "company": company,
        "exchange": exchange,
        "adapter": adapter,
        "tool": "revenue.pull",
    }

    def commission_page(data: dict[str, Any]) -> dict[str, Any]:
        sums: dict[str, str] = {}
        for r in data.get("rows") or []:
            amount = _dec(r.get("amount"))
            coin = str(r.get("coin") or "")
            if amount is None or not coin:
                continue
            pull.commission[coin] = pull.commission.get(coin, Decimal(0)) + amount
            sums[coin] = str(amount)
        return sums

    def team_page(data: dict[str, Any]) -> dict[str, Any]:
        rows = [r for r in data.get("rows") or [] if isinstance(r, dict) and r.get("uid")]
        pull.invitees.extend(
            {"uid": str(r["uid"]), "invited_on": r.get("invited_on"), "meets_minimum": r.get("meets_minimum")}
            for r in rows
        )  # fmt: skip
        return {
            "invitees": len(rows),
            "min_balance": sum(1 for r in rows if r.get("meets_minimum") is True),
        }

    def deposit_page(data: dict[str, Any]) -> dict[str, Any]:
        sums: dict[str, str] = {}
        for r in data.get("rows") or []:
            amount = _dec(r.get("amount"))
            coin = str(r.get("coin") or "")
            if amount is None or not coin:
                continue
            pull.deposits[coin] = pull.deposits.get(coin, Decimal(0)) + amount
            sums[coin] = str(amount)
        return sums

    await _paged(conn, pull, base, "commission/stats/symbol/list", {**span, "tradeType": 10},
                 None, commission_page)  # fmt: skip
    if not pull.answered:  # the account itself failed (no secret, a bad key, unreachable)
        return pull
    local = {"min_balance": min_balance} if min_balance is not None else None
    await _paged(conn, pull, base, "invite/user/team/list", span, local, team_page)
    pull.endpoints.append("trade/user/team")
    try:
        pull.requests += 1
        t = await conn.call(**base, endpoint="trade/user/team", params={**span, "tradeType": 10})
        pull.volume_usdt, pull.fees_usdt = _dec(t.get("volume_usdt")), _dec(t.get("fees_usdt"))
        traders = t.get("active_traders")
        pull.active_traders = traders if isinstance(traders, int) else None
        pull.pages.append({"endpoint": "trade/user/team", "page": 0, "sha256": page_hash(t), "rows": 1,
                           "sums": {"volume_usdt": t.get("volume_usdt"), "fees_usdt": t.get("fees_usdt")}})  # fmt: skip
    except ConnectorError as e:
        pull.gaps.append({"endpoint": "trade/user/team", "page": 0, "error": e.code})
    await _paged(conn, pull, base, "money/detail/list", span, None, deposit_page)
    # Prices: USDT is par; every other coin at the day's close (keyless kline).
    pull.prices[USDT] = (Decimal(1), "par")
    for coin in sorted(c for c in pull.commission if c != USDT):
        symbol = f"{coin}_usdt"
        if "kline" not in pull.endpoints:
            pull.endpoints.append("kline")
        try:
            pull.requests += 1
            k = await conn.call(
                **base,
                endpoint="kline",
                params={"symbol": symbol, "size": 1, "type": "day1", "time": start // 1000},
            )
        except ConnectorError as e:
            pull.gaps.append({"endpoint": "kline", "page": 0, "error": e.code, "coin": coin})
            continue
        close = _dec(k.get("close"))
        if close is None or close <= 0:
            pull.gaps.append({"endpoint": "kline", "page": 0, "error": "no_price", "coin": coin})
            continue
        pull.prices[coin] = (close, f"{exchange}:kline:{symbol}:{day.isoformat()}")
        pull.pages.append({"endpoint": "kline", "page": 0, "sha256": page_hash(k), "rows": 1,
                           "sums": {coin: str(close)}})  # fmt: skip
    return pull
