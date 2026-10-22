"""Shared fakes of prompt 10's revenue and growth tests: an affiliate connector
that answers as egress's lbank-affiliate-v2 reductions do (no real exchange),
a model router that counts its calls, and the
setup of one company's affiliate account."""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

from hq_api.domain import affiliate as A

SIGNER_SECRET = "ak-" + "P" * 29 + ":" + "sk-" + "R" * 40


class FakeConnector:
    """`call` as GatewayConnector's: the reduced data, or ConnectorError."""

    def __init__(self, *, usdt: str = "12", eth: str | None = "0.01", invitees: int = 150) -> None:
        self.usdt, self.eth, self.invitees = usdt, eth, invitees
        self.missing_page: int | None = None
        self.fail_all = False
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append({"endpoint": endpoint, "params": params, "local": local, "tool": tool})
        if self.fail_all:
            raise A.ConnectorError("upstream_error", {"error_code": 10002})
        if endpoint == "commission/stats/symbol/list":
            rows = [{"coin": "usdt", "amount": self.usdt}]
            if self.eth is not None:
                rows.append({"coin": "eth", "amount": self.eth})
            return {"rows": rows, "page_rows": len(rows), "total": None}
        if endpoint == "invite/user/team/list":
            start = int(params["start"])
            if self.missing_page is not None and start // 100 == self.missing_page:
                raise A.ConnectorError("upstream_error", {"error_code": 10009})
            day = datetime.fromtimestamp(int(params["startTime"]) / 1000, A.UTC8).date()
            n = max(0, min(100, self.invitees - start))
            minimum = (local or {}).get("min_balance")
            rows = [
                {"uid": f"9{start + i:07d}", "invited_on": day.isoformat(),
                 "meets_minimum": (i % 2 == 1) if minimum is not None else None}
                for i in range(n)
            ]  # fmt: skip
            return {"rows": rows, "page_rows": n, "total": self.invitees}
        if endpoint == "trade/user/team":
            return {"volume_usdt": "125000.5", "fees_usdt": "80.25", "active_traders": 7}
        if endpoint == "money/detail/list":
            return {"rows": [{"coin": "usdt", "amount": "300"}], "page_rows": 1, "total": 1}
        if endpoint == "kline":
            return {"close": "2000", "at": int(params["time"])}
        if endpoint == "invite/user/info":
            ours = str(params["uid"]).startswith("9")
            return {"invitee": ours, "meets_minimum": True if ours else None}
        raise A.ConnectorError("unknown_endpoint")


class Call:
    def __init__(self, text: str, ok: bool = True) -> None:
        self.text, self.ok, self.status = text, ok, "ok" if ok else "error"


class FakeRouter:
    """llm-router's /v1/run as the worker calls it; never a real model."""

    def __init__(self, answer: str = "[]") -> None:
        self.answer = answer
        self.bodies: list[dict[str, Any]] = []

    async def run(self, body: dict[str, Any], timeout_s: int) -> Call:
        self.bodies.append(body)
        return Call(self.answer)


async def affiliate_account(
    su: Any, co: dict[str, Any], *, exchange: str = "lbank", min_balance: str | None = "۱۰۰"
) -> dict[str, Any]:
    """A signer service account, the company's revenue account (made 100 days
    ago) and, unless None, its sealed minimum balance article."""
    key = f"lbank-aff-{co['code'].lower()}"
    await su.execute(
        """INSERT INTO tools.accounts (key, site, title_fa, companies, policy)
           VALUES ($1, 'affiliate.lbank.test', 'افیلیت LBank', ARRAY[$2]::text[], $3::jsonb)
           ON CONFLICT (key) DO NOTHING""",
        key,
        co["code"],
        json.dumps({"inject": {"kind": "signer", "signer": "lbank-v2"}}),
    )
    acct = await su.fetchrow(
        """INSERT INTO revenue.accounts (company_id, exchange, adapter, service_account, title_fa,
               created_by_kind, created_by_code, created_at)
           VALUES ($1, $2, 'lbank-affiliate-v2', $3, 'افیلیت', 'owner', 'owner', now() - interval '100 days')
           RETURNING *""",
        co["id"],
        exchange,
        key,
    )
    if min_balance is not None:
        await su.execute(
            """INSERT INTO support.kb_articles (company_id, kind, key, question_fa, answer_md, status,
                   approved_at, sha256, proposed_by_kind, proposed_by_code)
               VALUES ($1, 'policy', 'vip.min_balance', 'حداقل موجودی VIP چقدر است؟', $2, 'approved',
                       now(), $3, 'owner', 'owner')""",
            co["id"],
            f"حداقل موجودی برای VIP {min_balance} USDT است.",
            hashlib.sha256(co["code"].encode()).hexdigest(),
        )
    return {**dict(acct), "company": co["code"], "key": key}


@contextlib.asynccontextmanager
async def holding_switch(su: Any, state: str) -> AsyncIterator[None]:
    """The holding's kill switch set to `state` for the block, then restored."""
    row = await su.fetchrow(
        """SELECT k.company_id, k.state FROM control.kill_switches k
           JOIN core.companies c ON c.id = k.company_id WHERE c.kind = 'holding'"""
    )
    await su.execute(
        "UPDATE control.kill_switches SET state = $2 WHERE company_id = $1",
        row["company_id"],
        state,
    )
    try:
        yield
    finally:
        await su.execute(
            "UPDATE control.kill_switches SET state = $2 WHERE company_id = $1",
            row["company_id"],
            row["state"],
        )


def settled(days_back: int = 0) -> date:
    return A.last_settled_day(datetime.now(UTC)) - timedelta(days=days_back)
