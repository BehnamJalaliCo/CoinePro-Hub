"""Prompt 10's revenue and growth tools (agents/tools.md v1.5, contract §19.10),
and the worker's connector (contract §19.1).

    revenue.read    A0  the radar: commission and referrals by day, company and
                        account, incomplete days marked, the treasury's cost
    funnel.read     A0  the funnel; a stage with no source is "not connected"
    rescue.update   A2  the rescue specialist moves a case along; it sends nothing
    feedback.tag    A2  files a conversation or an NPS wave in the feedback inbox
    referral.check  A0  {invitee, meets_minimum} only, never a balance: the api
                        grants one connector call (the company's signer
                        account), egress signs it and reduces the answer, the
                        api records it (and opens or closes a rescue case)

None of them sends anything to a customer. `connector_call` is not a tool:
it is the worker's own route (/v1/connectors/call, the worker's token, like
every call here) for the revenue pulls; the gateway asks the api for the
call's account with the worker's api service token, has egress carry it out
and logs its entries. The secret lives in that one call only.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from hq_gateway import tools as T
from hq_gateway import web

log = logging.getLogger("hq_gateway.revenue")
DAY = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
EXCHANGE = r"^[a-z][a-z0-9_-]{1,30}$"
ENTRY_KEYS = ("tool", "kind", "class", "method", "host", "status", "bytes_in", "bytes_out", "ms",
              "blocked_reason", "requests")  # fmt: skip


class RevenueReadIn(T.In):
    company: str | None = Field(default=None, pattern=T.CODE)
    from_: str = Field(alias="from", pattern=DAY)
    to: str = Field(pattern=DAY)
    by: Literal["day", "company", "account"] = "day"

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class FunnelReadIn(T.In):
    company: str = Field(pattern=T.CODE)
    period: Literal["week", "month"] = "week"


class RescueUpdateIn(T.In):
    ref: str = Field(pattern=r"^RC-[0-9]{6,}$")
    state: Literal["open", "contacted", "rescued", "lost", "opted_out"]
    note_fa: str = Field(min_length=1, max_length=1000)


class FeedbackTagIn(T.In):
    source_ref: str = Field(pattern=r"^(SC-[0-9]{6,}|NP-[0-9]{4}Q[1-4]-[A-Z][A-Z0-9]{1,9})$")
    kind: Literal["bug", "feature", "confusion", "complaint", "praise"]
    area: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    title_fa: str = Field(min_length=1, max_length=300)


class ReferralCheckIn(T.In):
    company: str = Field(pattern=T.CODE)
    exchange: str = Field(pattern=EXCHANGE)
    uid: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]{1,64}$")


async def revenue_read(api: T.Api, call: T.Call, a: RevenueReadIn) -> T.Result:
    body = a.model_dump(mode="json", by_alias=True, exclude_none=True)
    resp = await api.request("POST", "/internal/v1/revenue/read", call.token, json=body)
    r = T.from_response(resp, None)
    if r.outcome == "ok":
        r.ref = f"revenue:{(r.data or {}).get('company') or a.company or call.gate['company']}"
    return r


async def funnel_read(api: T.Api, call: T.Call, a: FunnelReadIn) -> T.Result:
    resp = await api.request(
        "POST", "/internal/v1/growth/funnel/read", call.token, json=a.model_dump(mode="json")
    )
    r = T.from_response(resp, None)
    if r.outcome == "ok":
        r.ref = f"funnel:{a.company}:{a.period}"
    return r


async def rescue_update(api: T.Api, call: T.Call, a: RescueUpdateIn) -> T.Result:
    body = {"state": a.state, "note_fa": await T._text(a.note_fa)}
    resp = await api.request(
        "POST", f"/internal/v1/growth/rescue/{a.ref}/update", call.token, json=body,
        idem=call.idem("rescue.update"),
    )  # fmt: skip
    return T.from_response(resp)


async def feedback_tag(api: T.Api, call: T.Call, a: FeedbackTagIn) -> T.Result:
    body = a.model_dump(mode="json")
    body["title_fa"] = await T._text(a.title_fa)
    resp = await api.request(
        "POST", "/internal/v1/feedback/tag", call.token, json=body, idem=call.idem("feedback.tag")
    )
    return T.from_response(resp)


def _entries(out: dict[str, Any], tool: str) -> list[dict[str, Any]]:
    rows = []
    for e in out.get("entries") or []:
        row = web._row(e, tool, "A0")
        if row is not None:
            rows.append(
                {k: row[k] for k in ENTRY_KEYS} | {"tool": tool, "kind": "request", "class": "A0"}
            )
    return rows[:20]


async def referral_check(api: T.Api, call: T.Call, a: ReferralCheckIn) -> T.Result:
    body = a.model_dump(mode="json")
    resp = await api.request("POST", "/internal/v1/growth/referral-check", call.token, json=body)
    r = T.from_response(resp, None)
    if r.outcome != "ok" or not isinstance(r.data, dict):
        return r if r.outcome != "ok" else T.Result("error", code="api_bad_answer")
    if r.data.get("done"):
        return T.Result("ok", ref=f"referral:{a.exchange}", data=_answer(r.data))
    grant = r.data.get("grant")
    if not isinstance(grant, dict) or api.egress is None:
        return T.Result("error", code="channel_not_configured")
    payload = {
        "ctx": {"company": call.gate["company"], "actor": call.gate["employee"],
                "run_id": str(call.gate.get("run_id")) if call.gate.get("run_id") else None,
                "cls": "A0", "max_bytes": int(grant.get("max_bytes") or 1)},
        "adapter": grant.get("adapter"),
        "tool": "referral.check",
        "endpoint": grant.get("endpoint"),
        "params": grant.get("params") or {},
        "local": grant.get("local") or {},
        "account": grant.get("account"),
    }  # fmt: skip
    out: dict[str, Any] = {}
    try:
        out = await api.egress.post("/v1/connectors/call", payload)
    except (httpx.HTTPError, ValueError):
        out = {"outcome": "error", "code": "egress_unreachable", "entries": []}
    finally:
        payload.pop("account", None)  # the secret lives for this call only
        grant.pop("account", None)
    raw = out.get("data")
    data: dict[str, Any] = raw if isinstance(raw, dict) else {}
    ok = out.get("outcome") == "ok" and isinstance(data.get("invitee"), bool)
    result = {
        **body,
        "reservation": grant.get("reservation"),
        "ok": ok,
        "invitee": data.get("invitee") if ok else None,
        "meets_minimum": data.get("meets_minimum") if ok else None,
        "error_code": None if ok else str(out.get("code") or "connector_failed")[:60].lower(),
        "entries": _entries(out, "referral.check"),
    }
    resp = await api.request(
        "POST", "/internal/v1/growth/referral-check/result", call.token, json=result
    )
    r = T.from_response(resp, None)
    if r.outcome != "ok" or not isinstance(r.data, dict):
        return r if r.outcome != "ok" else T.Result("error", code="api_bad_answer")
    return T.Result("ok", ref=f"referral:{a.exchange}", data=_answer(r.data))


def _answer(d: dict[str, Any]) -> dict[str, Any]:
    """Only {invitee, meets_minimum} (and the rescue case it moved): never a balance."""
    out = {"invitee": bool(d.get("invitee")), "meets_minimum": d.get("meets_minimum")}
    rescue = d.get("rescue")
    if isinstance(rescue, dict):
        out["rescue"] = {"ref": rescue.get("ref"), "state": rescue.get("state")}
    return out


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "revenue.read": (RevenueReadIn, revenue_read),
    "funnel.read": (FunnelReadIn, funnel_read),
    "rescue.update": (RescueUpdateIn, rescue_update),
    "feedback.tag": (FeedbackTagIn, feedback_tag),
    "referral.check": (ReferralCheckIn, referral_check),
}
T.TOOLS.update(TOOLS)


# ------------------------------------------------- the worker's connector --
class ConnectorCallIn(BaseModel):
    """The worker's call (never an agent's tool): one endpoint of an adapter."""

    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=10, max_length=2000)  # the worker's api service token
    company: str = Field(pattern=T.CODE)
    exchange: str = Field(pattern=EXCHANGE)
    adapter: str = Field(pattern=r"^[a-z][a-z0-9-]{1,40}$")
    endpoint: str = Field(pattern=r"^[a-z][a-z/._-]{1,60}$")
    tool: Literal["revenue.pull"] = "revenue.pull"
    params: dict[str, str | int] = Field(default_factory=dict, max_length=20)
    local: dict[str, str | int | float | None] = Field(default_factory=dict, max_length=10)


async def connector_call(api: T.Api, a: ConnectorCallIn) -> dict[str, Any]:
    """api (the account for this call, a reservation) -> egress (signs,
    sends, reduces, scrubs) -> api (the entries). Never the secret back."""
    if api.egress is None:
        return {"outcome": "error", "code": "channel_not_configured", "data": None}
    resp = await api.request(
        "POST",
        f"/internal/v1/egress/connectors/{a.adapter}/pull",
        a.token,
        json={"company": a.company, "exchange": a.exchange, "endpoint": a.endpoint, "tool": a.tool},
    )
    r = T.from_response(resp, None)
    if r.outcome != "ok" or not isinstance(r.data, dict):
        return {"outcome": r.outcome if r.outcome != "ok" else "error",
                "code": r.code or "api_bad_answer", "data": None}  # fmt: skip
    grant = r.data
    payload = {
        "ctx": {"company": a.company, "actor": "worker", "run_id": None, "cls": "A0",
                "max_bytes": int(grant.get("max_bytes") or 1)},
        "adapter": a.adapter,
        "tool": a.tool,
        "endpoint": a.endpoint,
        "params": a.params,
        "local": a.local,
        "account": grant.get("account"),
    }  # fmt: skip
    out: dict[str, Any] = {}
    try:
        out = await api.egress.post("/v1/connectors/call", payload)
    except (httpx.HTTPError, ValueError):
        out = {"outcome": "error", "code": "egress_unreachable", "entries": []}
    finally:
        payload.pop("account", None)
        grant.pop("account", None)
        entries = _entries(out, a.tool)
        if entries or grant.get("reservation"):
            await web.shielded(_log(api, a, entries, grant.get("reservation")))
    return {
        "outcome": out.get("outcome") or "error",
        "code": out.get("code"),
        "data": out.get("data"),
    }


async def _log(
    api: T.Api, a: ConnectorCallIn, entries: list[dict[str, Any]], reservation: Any
) -> None:
    body: dict[str, Any] = {"company": a.company, "entries": entries}
    if isinstance(reservation, str):
        body["reservation"] = reservation
    try:
        resp = await api.request(
            "POST", f"/internal/v1/egress/connectors/{a.adapter}/log", a.token, json=body
        )
        if resp.status_code != 204:
            log.warning("connector entries refused: %s", resp.status_code)
    except httpx.HTTPError as exc:
        log.error("connector entries not logged: %s", type(exc).__name__)
