"""Connectors of code (prompt 10 §2.3, contract §19.1): fixed endpoints of an
exchange's API, signed by a reviewed signer (signers.py), each answer reduced
to what the hub may keep BEFORE it leaves egress.

    lbank-affiliate-v2  LBank's affiliate API v2 (signer lbank-v2) and its
                        public market data (no key)

Every endpoint is listed here with the parameters it may send; nothing else
can be called through a connector, and a connector's account can call
nothing else. The privacy rules live in the reductions:
  invite/user/team/list   per invitee: the UID (the hub turns it into a
                          pseudonym at once), the invite day, and whether the
                          balance meets the company's minimum; the balance
                          itself is read here and dropped
  invite/user/info        {invitee, meets_minimum} only (referral.check)
  the others              sums: commission per coin, team volume and fees,
                          deposits per coin, a day's closing price

LBank's documented rate limit (5 requests in 10 s) is a token bucket per
account here, in the adapter (one process: the pulls and referral.check share
it). An answer that is not LBank's success shape is an error with its numeric
`error_code` only, never the upstream text.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

UTC8 = timezone(timedelta(hours=8))  # LBank's settlement zone (T+1)
COIN = re.compile(r"^[a-z0-9]{1,20}$")
UID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_ROWS = 500


class Malformed(ValueError):
    """The upstream answer does not have the documented shape."""


# ------------------------------------------------------------ reductions --
def _first(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def _amount(value: Any) -> str:
    d = _decimal(value)
    if d is None:
        raise Malformed("amount")
    return format(d.normalize(), "f")


def _coin(value: Any) -> str:
    coin = str(value or "").strip().lower().replace("_", "")
    if not COIN.match(coin):
        raise Malformed("coin")
    return coin


def _rows(data: Any) -> tuple[list[dict[str, Any]], int | None]:
    """A list answer: data itself, or data.list / records / rows (+ total)."""
    total = None
    if isinstance(data, dict):
        t = data.get("total")
        total = int(t) if isinstance(t, int | str) and str(t).isdigit() else None
        data = next((data[k] for k in ("list", "records", "rows") if isinstance(data.get(k), list)), None)
    if not isinstance(data, list) or len(data) > MAX_ROWS:
        raise Malformed("rows")
    if not all(isinstance(r, dict) for r in data):
        raise Malformed("row")
    return data, total


def _day(value: Any) -> str | None:
    """An invite time (epoch ms or s, or an ISO date) as its UTC+8 day."""
    if value is None:
        return None
    if isinstance(value, int | float) or (isinstance(value, str) and value.isdigit()):
        n = int(value)
        n = n // 1000 if n > 10**11 else n
        return datetime.fromtimestamp(n, UTC).astimezone(UTC8).date().isoformat()
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


ASSET_KEYS = ("totalAssetUsdt", "assetUsdt", "totalAssets", "totalAsset", "asset", "balance")


def _meets(row: dict[str, Any], local: dict[str, Any]) -> bool | None:
    """Whether the balance meets the minimum; the balance itself goes no further."""
    minimum = _decimal(local.get("min_balance"))
    balance = _decimal(_first(row, ASSET_KEYS))
    if minimum is None or balance is None:
        return None
    return balance >= minimum


def commission(data: Any, local: dict[str, Any]) -> dict[str, Any]:
    rows, total = _rows(data)
    out: dict[str, Decimal] = {}
    for r in rows:
        coin = _coin(_first(r, ("coin", "asset", "symbol", "currency")))
        amount = _decimal(_first(r, ("amount", "commission", "commissionAmount", "totalCommission")))
        if amount is None:
            raise Malformed("amount")
        out[coin] = out.get(coin, Decimal(0)) + amount
    return {
        "rows": [{"coin": c, "amount": format(a.normalize(), "f")} for c, a in sorted(out.items())],
        "page_rows": len(rows),
        "total": total,
    }


def team(data: Any, local: dict[str, Any]) -> dict[str, Any]:
    rows, total = _rows(data)
    kept = []
    for r in rows:
        uid = str(_first(r, ("uid", "openId", "userId", "inviteeUid")) or "")
        if not UID.match(uid):
            raise Malformed("uid")
        kept.append(
            {
                "uid": uid,
                "invited_on": _day(_first(r, ("registerTime", "inviteTime", "createTime", "regTime"))),
                "meets_minimum": _meets(r, local),
            }
        )
    return {"rows": kept, "page_rows": len(rows), "total": total}


def trade(data: Any, local: dict[str, Any]) -> dict[str, Any]:
    if isinstance(data, list):
        data = data[0] if len(data) == 1 and isinstance(data[0], dict) else {}
    if not isinstance(data, dict):
        raise Malformed("trade")
    volume = _decimal(_first(data, ("volume", "tradeAmount", "totalVolume", "volumeUsdt")))
    fees = _decimal(_first(data, ("fee", "fees", "tradeFee", "feeUsdt")))
    traders = _first(data, ("tradeUserCount", "activeUsers", "traders", "tradeUsers"))
    return {
        "volume_usdt": format(volume.normalize(), "f") if volume is not None else None,
        "fees_usdt": format(fees.normalize(), "f") if fees is not None else None,
        "active_traders": int(traders) if str(traders).isdigit() else None,
    }


def deposits(data: Any, local: dict[str, Any]) -> dict[str, Any]:
    rows, total = _rows(data)
    out: dict[str, Decimal] = {}
    for r in rows:
        coin = _coin(_first(r, ("coin", "asset", "currency", "symbol")))
        amount = _decimal(_first(r, ("amount", "depositAmount", "money")))
        if amount is None:
            raise Malformed("amount")
        out[coin] = out.get(coin, Decimal(0)) + amount
    return {
        "rows": [{"coin": c, "amount": format(a.normalize(), "f")} for c, a in sorted(out.items())],
        "page_rows": len(rows),
        "total": total,
    }


def user_info(data: Any, local: dict[str, Any]) -> dict[str, Any]:
    """referral.check: {invitee, meets_minimum}; never a balance, a name or anything else."""
    if data is None or data == {} or data == []:
        return {"invitee": False, "meets_minimum": None}
    if isinstance(data, list):
        data = data[0] if data and isinstance(data[0], dict) else {}
    if not isinstance(data, dict):
        raise Malformed("info")
    flag = _first(data, ("isInvite", "invited", "isInvitee", "inviteFlag", "isTeam"))
    invitee = flag in (True, 1, "1", "true", "True") if flag is not None else bool(
        _first(data, ("uid", "openId", "userId"))
    )
    return {"invitee": invitee, "meets_minimum": _meets(data, local) if invitee else None}


def kline(data: Any, local: dict[str, Any]) -> dict[str, Any]:
    """The day's candle: [time, open, high, low, close, volume] -> its close."""
    if not isinstance(data, list) or not data or not isinstance(data[0], list) or len(data[0]) < 5:
        raise Malformed("kline")
    return {"close": _amount(data[0][4]), "at": int(data[0][0]) if str(data[0][0]).isdigit() else None}


# ------------------------------------------------------------- adapters --
@dataclass(frozen=True)
class Endpoint:
    path: str
    params: frozenset[str]
    reduce: Callable[[Any, dict[str, Any]], dict[str, Any]]
    local: frozenset[str] = frozenset()
    signed: bool = True
    method: str = "POST"


@dataclass(frozen=True)
class Adapter:
    name: str
    signer: str
    rate: int  # requests ...
    per_s: float  # ... in this many seconds (the exchange's documented limit)
    endpoints: dict[str, Endpoint]
    public_url: str  # the settings key of its keyless market API's base URL


SPAN = frozenset({"startTime", "endTime"})
PAGE = frozenset({"start", "pageSize"})
AFF = "/affiliate-api/v2/"
LBANK = Adapter(
    name="lbank-affiliate-v2",
    signer="lbank-v2",
    rate=5,
    per_s=10.0,
    endpoints={
        "commission/stats/symbol/list": Endpoint(
            AFF + "commission/stats/symbol/list", SPAN | PAGE | {"tradeType", "coin"}, commission
        ),
        "invite/user/team/list": Endpoint(
            AFF + "invite/user/team/list", SPAN | PAGE, team, local=frozenset({"min_balance"})
        ),
        "trade/user/team": Endpoint(AFF + "trade/user/team", SPAN | {"tradeType"}, trade),
        "money/detail/list": Endpoint(AFF + "money/detail/list", SPAN | PAGE | {"type"}, deposits),
        "invite/user/info": Endpoint(
            AFF + "invite/user/info", frozenset({"uid"}), user_info, local=frozenset({"min_balance"})
        ),
        "kline": Endpoint(
            "/v2/kline.do", frozenset({"symbol", "size", "type", "time"}), kline,
            signed=False, method="GET",
        ),  # fmt: skip
    },
    public_url="lbank_public_url",
)
ADAPTERS: dict[str, Adapter] = {LBANK.name: LBANK}


def succeeded(body: Any) -> tuple[bool, int | None]:
    """LBank's envelope: {result: true|"true", data, error_code: 0}."""
    if not isinstance(body, dict):
        return False, None
    code = body.get("error_code")
    code_n = int(code) if isinstance(code, int | str) and str(code).lstrip("-").isdigit() else None
    ok = body.get("result") in (True, "true") and code_n in (0, None)
    return ok, code_n


# --------------------------------------------------------------- the rate --
@dataclass
class Bucket:
    """`rate` requests per `per_s` seconds, refilled continuously."""

    rate: int
    per_s: float
    tokens: float = -1.0
    at: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        if self.tokens < 0:
            self.tokens = float(self.rate)

    def _refill(self) -> None:
        now = time.monotonic()
        self.tokens = min(float(self.rate), self.tokens + (now - self.at) * self.rate / self.per_s)
        self.at = now

    async def take(self, wait_s: float) -> float:
        """0 when a token was taken (waiting at most `wait_s`), else the
        seconds until one would be free."""
        async with self.lock:
            self._refill()
            need = (1 - self.tokens) * self.per_s / self.rate if self.tokens < 1 else 0.0
            if need > wait_s:
                return need
            if need > 0:
                await asyncio.sleep(need)
                self._refill()
            self.tokens -= 1
            return 0.0


class Buckets:
    def __init__(self) -> None:
        self._b: dict[tuple[str, str], Bucket] = {}

    def of(self, adapter: Adapter, key: str) -> Bucket:
        k = (adapter.name, key)
        if k not in self._b:
            self._b[k] = Bucket(adapter.rate, adapter.per_s)
        return self._b[k]
