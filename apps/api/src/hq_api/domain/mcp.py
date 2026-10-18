"""The MCP registry (prompt 07 §3, contract §18.7) and the tool catalog.

An MCP server exists for the agents only after two owner seals: the
registration (🔏 `mcp.add`, the exact body: transport, URL, the tools with
their class, the companies) and the enable (🔏 `mcp.enable`, the key). The
gateway then lists the server's tools on each call; the first listing after
an enable is pinned (`listing_sha256`), and any later difference switches the
server off until the owner seals it again. A tool missing from the sealed
registration is always refused. The server's secret is the owner's
(`make mcp-secret KEY=…` -> OpenBao kv/hq-api/tools/mcp/<key>); the api hands
it to the gateway for one call and it is in no listing, catalog or log.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.schemas import Model
from hq_common.tool_status import GATEWAY_TOOLS, NOT_CONFIGURED, WEB_TOOLS

SERVER_KEY = r"^[a-z][a-z0-9-]{1,39}$"
TOOL_NAME = r"^[A-Za-z0-9_][A-Za-z0-9_.:/-]{0,127}$"
COMPANY = r"^[A-Z][A-Z0-9]{1,9}$"
SECRET_PATH = "hq-api/tools/mcp/{key}"  # noqa: S105 - a KV path (the kv mount; policy hq-api)
CONTAINER_HOST = re.compile(r"^mcp-[a-z0-9-]{1,40}$")
INTERNAL_HOSTS = ("hq.coinepro.com",)
Class = Literal["A0", "A1", "A2", "A3"]


# ------------------------------------------------------------------- input --
class McpToolIn(Model):
    name: str = Field(pattern=TOOL_NAME)
    cls: Class = Field(alias="class")
    enabled: bool = True

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class McpServerIn(Model):
    """A registration, sealed as it is (🔏 `mcp.add` = SHA-256 of the body)."""

    key: str = Field(pattern=SERVER_KEY)
    title_fa: str = Field(min_length=1, max_length=200)
    transport: Literal["http", "container"]
    url: str = Field(min_length=8, max_length=500)
    image: str | None = Field(default=None, max_length=300)
    tools: list[McpToolIn] = Field(min_length=1, max_length=100)
    companies: Literal["all"] | list[str] = "all"
    # The header the server's secret goes into (`Authorization` -> "Bearer <secret>").
    auth_header: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9-]{0,60}$")

    @field_validator("companies")
    @classmethod
    def _codes(cls, v: Any) -> Any:
        if isinstance(v, list):
            if not 1 <= len(v) <= 100 or any(not re.fullmatch(COMPANY, c) for c in v):
                raise ValueError("'all' or a list of company codes")
            return sorted(set(v))
        return v

    @model_validator(mode="after")
    def _shape(self) -> McpServerIn:
        names = [t.name for t in self.tools]
        if len(set(names)) != len(names):
            raise ValueError("each tool once")
        check_url(self.transport, self.url)
        return self


def check_url(transport: str, url: str) -> None:
    """`http`: an https URL of a public host (the egress guard checks the
    address again at every connection); `container`: http://mcp-<name>:<port>/…
    on the internal network hq-mcp."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.username or parts.password:
        raise ValueError("no credentials in the URL (the secret goes to OpenBao)")
    if transport == "container":
        if parts.scheme != "http" or not CONTAINER_HOST.fullmatch(host) or not parts.port:
            raise ValueError("a container server is http://mcp-<name>:<port>/<path>")
        return
    if parts.scheme != "https" or not host or "." not in host:
        raise ValueError("an http server needs an https URL with a public host name")
    if host in INTERNAL_HOSTS or host.endswith((".internal", ".local", ".localhost")):
        raise ValueError("not a host of the hub")
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return
    raise ValueError("a host name, not an address")


def registration_sha256(body: McpServerIn) -> str:
    canon = json.dumps(
        body.model_dump(mode="json", by_alias=True), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canon.encode()).hexdigest()


# ------------------------------------------------------------------ output --
class McpToolOut(BaseModel):
    name: str
    cls: Class = Field(serialization_alias="class")
    enabled: bool


class McpServer(BaseModel):
    id: UUID
    key: str
    title_fa: str
    transport: Literal["http", "container"]
    url: str
    image: str | None
    tools: list[McpToolOut]
    companies: Literal["all"] | list[str]
    status: Literal["pending", "enabled", "disabled"]
    status_reason: str | None
    has_secret: bool
    auth_header: str | None
    listed_tools: list[str] | None
    listed_at: datetime | None
    added_at: datetime
    enabled_at: datetime | None
    version: int


def render(r: dict[str, Any], has_secret: bool) -> McpServer:
    return McpServer(
        id=r["id"],
        key=r["key"],
        title_fa=r["title_fa"],
        transport=r["transport"],
        url=r["url"],
        image=r["image"],
        tools=[
            McpToolOut(name=t["name"], cls=t["class"], enabled=bool(t.get("enabled", True)))
            for t in (r["tools"] or [])
        ],
        companies=list(r["companies"]) if r["companies"] is not None else "all",
        status=r["status"],
        status_reason=r["status_reason"],
        has_secret=has_secret,
        auth_header=r["auth_header"],
        listed_tools=list(r["listed_tools"]) if r["listed_tools"] is not None else None,
        listed_at=r["listed_at"],
        added_at=r["added_at"],
        enabled_at=r["enabled_at"],
        version=r["version"],
    )


async def has_secret(hub: Any, key: str) -> bool:
    if getattr(hub, "bao", None) is None:
        return False
    try:
        data = await hub.bao.read_kv(SECRET_PATH.format(key=key))
    except Exception:  # noqa: BLE001 - not there (or OpenBao away): no secret
        return False
    return bool(data.get("token"))


async def secret(hub: Any, key: str) -> str | None:
    if getattr(hub, "bao", None) is None:
        return None
    try:
        data = await hub.bao.read_kv(SECRET_PATH.format(key=key))
    except Exception:  # noqa: BLE001 - not there: the call goes without one
        return None
    token = data.get("token")
    return str(token) if token else None


async def load(tx: Tx, key: str, *, lock: bool = False) -> dict[str, Any] | None:
    if lock:
        return await tx.first("SELECT * FROM tools.mcp_servers WHERE key = :k FOR UPDATE", k=key)
    return await tx.first("SELECT * FROM tools.mcp_servers WHERE key = :k", k=key)


async def put(tx: Tx, body: McpServerIn, by: str, known_companies: set[str]) -> dict[str, Any]:
    """A new registration, or a new version of one: pending until enabled."""
    if isinstance(body.companies, list):
        unknown = sorted(set(body.companies) - known_companies)
        if unknown:
            raise ApiError(422, "validation_failed", fields={"companies": f"unknown: {unknown}"})
    tools = json.dumps([t.model_dump(by_alias=True) for t in body.tools])
    values: dict[str, Any] = {
        "k": body.key,
        "t": body.title_fa,
        "tr": body.transport,
        "u": body.url,
        "i": body.image,
        "tools": tools,
        "co": body.companies if isinstance(body.companies, list) else None,
        "ah": body.auth_header,
        "sha": registration_sha256(body),
        "by": by,
    }
    row: dict[str, Any] = await tx.one(
        """INSERT INTO tools.mcp_servers (key, title_fa, transport, url, image, tools, companies,
               auth_header, registration_sha256, added_by)
           VALUES (:k, :t, :tr, :u, :i, CAST(:tools AS jsonb), :co, :ah, :sha, :by)
           ON CONFLICT (key) DO UPDATE SET
               title_fa = EXCLUDED.title_fa, transport = EXCLUDED.transport, url = EXCLUDED.url,
               image = EXCLUDED.image, tools = EXCLUDED.tools, companies = EXCLUDED.companies,
               auth_header = EXCLUDED.auth_header,
               registration_sha256 = EXCLUDED.registration_sha256,
               status = 'pending', status_reason = 'registration changed',
               listing_sha256 = NULL, enabled_at = NULL, updated_at = now()
           RETURNING *""",
        **values,
    )
    return row


async def set_status(
    tx: Tx, key: str, status: str, reason: str | None, *, enable: bool = False
) -> dict[str, Any]:
    row = await load(tx, key, lock=True)
    if row is None:
        raise ApiError(404, "not_found")
    updated: dict[str, Any] = await tx.one(
        """UPDATE tools.mcp_servers SET status = :st, status_reason = :r, updated_at = now(),
               enabled_at = CASE WHEN :en THEN now() ELSE enabled_at END,
               listing_sha256 = CASE WHEN :en THEN NULL ELSE listing_sha256 END
           WHERE key = :k RETURNING *""",
        st=status,
        r=reason,
        en=enable,
        k=key,
    )
    return updated


def sealed_tool(row: dict[str, Any], name: str) -> dict[str, Any] | None:
    for t in row["tools"] or []:
        if t.get("name") == name and t.get("enabled", True):
            return dict(t)
    return None


# ----------------------------------------------------------------- catalog --
class CatalogTool(BaseModel):
    name: str
    source: Literal["internal", "web", "mcp"]
    cls: str = Field(serialization_alias="class")  # "A0/A2": decided per call
    per_call: bool
    input: str
    description: str
    roles: list[str]
    status: Literal["live", "off", "channel_not_configured", "pending"]
    server: str | None = None


def catalog(lib: Any, servers: list[dict[str, Any]]) -> list[CatalogTool]:
    """Every tool of agents/tools.md (and each sealed MCP tool): its class, the
    roles whose charters grant it, and whether this build carries it out."""
    roles: dict[str, list[str]] = {}
    for role, charter in sorted(lib.roles.items()):
        for t in charter.tools:
            roles.setdefault(t, []).append(role)
    live_mcp = any(s["status"] == "enabled" for s in servers)
    out: list[CatalogTool] = []
    for name, t in lib.tools.items():
        if name in NOT_CONFIGURED:
            status = "channel_not_configured"
        elif name == "mcp.call":
            status = "live" if live_mcp else "off"
        else:
            status = "live" if name in GATEWAY_TOOLS else "off"
        out.append(
            CatalogTool(
                name=name,
                source="web" if name in WEB_TOOLS else ("mcp" if t.per_tool else "internal"),
                cls="per tool" if t.per_tool else ("/".join(t.classes) if t.classes else t.cls),
                per_call=bool(t.classes) or t.per_tool,
                input=t.input,
                description=t.description[:500],
                roles=roles.get(name, []),
                status=status,
            )
        )
    mcp_roles = roles.get("mcp.call", [])
    for s in sorted(servers, key=lambda r: r["key"]):
        state = {"enabled": "live", "pending": "pending"}.get(s["status"], "off")
        for tool in s["tools"] or []:
            out.append(
                CatalogTool(
                    name=f"{s['key']}/{tool['name']}",
                    source="mcp",
                    cls=str(tool["class"]),
                    per_call=False,
                    input="{server, tool, args}",
                    description=s["title_fa"][:500],
                    roles=mcp_roles,
                    status=state if tool.get("enabled", True) else "off",
                    server=s["key"],
                )
            )
    return out
