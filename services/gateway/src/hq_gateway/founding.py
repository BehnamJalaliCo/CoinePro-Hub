"""The agents' server plan (agents/tools.md v2; contract §18.8; prompt 09 §3).

    server.plan  A1  a CTO for its company, the platform SRE for any company
                     or a founding: a server plan with its monthly cost; the
                     owner seals it on its digest, the provisioner (code, not
                     an agent) builds it

Software keys are the fixed reviewed list (hq_common.provisioning.SOFTWARE):
an unknown key is refused here, before the api is asked. Registered with the
gateway's tools on import (gateway.py).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from hq_common import provisioning as P
from hq_gateway import tools as T


class FirewallRuleIn(T.In):
    direction: Literal["in"] = "in"
    protocol: Literal["tcp", "udp", "icmp"]
    port: str | None = Field(default=None, max_length=11)
    sources: list[str] = Field(min_length=1, max_length=100)
    note_fa: str = Field(default="", max_length=200)


class ServerPlanIn(T.In):
    ref: str | None = Field(default=None, pattern=r"^PV-[0-9]{4,}$")
    founding: str | None = Field(default=None, pattern=r"^C-[0-9]{4,}$")
    company: str = Field(pattern=T.CODE)
    name: str = Field(min_length=1, max_length=63)
    type: str = Field(min_length=2, max_length=10)
    location: str = Field(min_length=2, max_length=10)
    private_network: bool = False
    firewall: list[FirewallRuleIn] = Field(default_factory=list, max_length=50)
    software: list[str] = Field(min_length=1, max_length=20)
    work_user: str = Field(min_length=2, max_length=32)
    repo: str | None = Field(default=None, max_length=200)

    @field_validator("software")
    @classmethod
    def _known(cls, v: list[str]) -> list[str]:
        unknown = sorted({k for k in v if k not in P.SOFTWARE})
        if unknown:
            raise ValueError(f"unknown software keys: {', '.join(unknown)[:200]}")
        return v


PLAN_FIELDS = (
    "ref", "founding", "company", "name", "type", "location", "monthly_eur", "digest", "state",
    "decision_ref", "problems",
)  # fmt: skip


async def server_plan(api: T.Api, call: T.Call, a: ServerPlanIn) -> T.Result:
    body: dict[str, Any] = a.model_dump(mode="json")
    for rule in body["firewall"]:
        rule["note_fa"] = await T._text(rule["note_fa"])
    resp = await api.request(
        "POST",
        "/internal/v1/provisioning/plans",
        call.token,
        json=body,
        idem=call.idem("server.plan"),
    )
    r = T.from_response(resp, None)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = str(r.data.get("ref") or "") or None
        r.data = {k: r.data.get(k) for k in PLAN_FIELDS}
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "server.plan": (ServerPlanIn, server_plan),
}

# Registered with the gateway's tools (tools.py itself knows nothing of these).
T.TOOLS.update(TOOLS)
