"""The MCP registry (prompt 07 §3, contract §18.7, §18.13) and the tool catalog.

An MCP server exists for the agents only after two owner seals: the
registration (🔏 `mcp.add`, the exact body: transport, URL, the tools with
their class, the companies) and the enable (🔏 `mcp.enable`, the key). The
gateway then lists the server's tools on each call; the first listing after
an enable is pinned (`listing_sha256`, and `pinned`: one digest per tool).
Any later difference switches the server off and raises a `tool_enable`
card (`{key, listing_sha256, diff}`); its approval (🔏 `decision.approve`)
re-enables the server with exactly that listing, and a listing that changes
again before the seal supersedes the card (7.1 §2.16). A tool missing from
the sealed registration is always refused. The server's secret is the
owner's (`make mcp-secret KEY=…` -> OpenBao kv/hq-api/tools/mcp/<key>); the
api hands it to the gateway for one call and it is in no listing, catalog or
log. A registration that moves the server to another host makes the stored
secret void until the owner writes it again (`secret_reset_at`).

A `container` server (prompt 12 §14, contract §21.11) is a compose service
on the internal network hq-mcp (profile `mcp`, infra/compose/mcp.yaml): a
stdio server behind mcp-proxy on :8080. Its registration is accepted only
when its key, image (pinned digest) and URL are exactly an entry of the
reviewed allow-list (infra/mcp/servers.yaml, mounted read-only:
HQ_MCP_ALLOWLIST) and it enables no banned or unreviewed tool, else `422`; a
server that needs the internet or a secret is `409 not_ready` (a later
version). It runs only while the `mcp` profile is on (hq.sh exports
MCP_CONTAINERS=on): until then its enable answers `409 not_ready`, mcp.call
`503 channel_not_configured`, and the catalog says so. A registration whose
image the allow-list no longer names is treated the same way (it is
registered again with the reviewed digest).
"""

from __future__ import annotations

import fnmatch
import hashlib
import ipaddress
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.schemas import Model
from hq_common.tool_status import GATEWAY_TOOLS, NOT_CONFIGURED, WEB_TOOLS

SERVER_KEY = r"^[a-z][a-z0-9-]{1,39}$"
TOOL_NAME = r"^[A-Za-z0-9_][A-Za-z0-9_.:/-]{0,127}$"
COMPANY = r"^[A-Z][A-Z0-9]{1,9}$"
SHA256 = r"^[0-9a-f]{64}$"
SECRET_PATH = "hq-api/tools/mcp/{key}"  # noqa: S105 - a KV path (the kv mount; policy hq-api)
CONTAINER_HOST = re.compile(r"^mcp-[a-z0-9-]{1,40}$")
INTERNAL_HOSTS = ("hq.coinepro.com",)
Class = Literal["A0", "A1", "A2", "A3"]
# Status reasons the code itself writes (and reads back).
TOOLS_CHANGED = "tools changed"
PROFILE_OFF = (
    "the mcp profile is off on this server (HQ_MCP=off, or it does not fit the memory "
    "budget): a container server cannot run"
)
PROFILE_OFF_FA = "پروفایل mcp روی این سرور خاموش است"
NOT_REVIEWED = (
    "the reviewed allow-list (infra/mcp/servers.yaml) no longer names this image: "
    "register the server again with the reviewed digest"
)
NOT_REVIEWED_FA = "تصویر این سرور دیگر همان بازبینی‌شده نیست"
LATER_VERSION = (
    "a container server that needs the internet or a secret is not runnable in this "
    "version (contract §21.11)"
)
ALLOWLIST_ENV = "HQ_MCP_ALLOWLIST"
DEFAULT_ALLOWLIST = "/app/mcp/servers.yaml"
CLASS_RANK = {"A0": 0, "A1": 1, "A2": 2, "A3": 3}
# An approved A3 card allows its one call for this long after the seal.
A3_CARD_HOURS = 24


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
        if self.transport == "container" and not self.image:
            raise ValueError("a container server names its image (the reviewed digest)")
        return self


def host_of(url: str) -> str:
    """The URL's host as a resolver reads it: lower case, without the root's
    trailing dot ("hq.coinepro.com." is "hq.coinepro.com")."""
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().rstrip(".")


def check_url(transport: str, url: str) -> None:
    """`http`: an https URL of a public host on port 443 (the egress guard
    checks the address again at every connection); `container`:
    http://mcp-<name>:<port>/… on the internal network hq-mcp."""
    parts = urlsplit(url)
    host = host_of(url)
    if parts.username or parts.password:
        raise ValueError("no credentials in the URL (the secret goes to OpenBao)")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("not a valid port") from exc
    if transport == "container":
        if parts.scheme != "http" or not CONTAINER_HOST.fullmatch(host) or not port:
            raise ValueError("a container server is http://mcp-<name>:<port>/<path>")
        return
    if parts.scheme != "https" or not host or "." not in host:
        raise ValueError("an http server needs an https URL with a public host name")
    if port not in (None, 443):
        raise ValueError("an http server is reached on port 443 only")
    if host in INTERNAL_HOSTS or host.endswith((".internal", ".local", ".localhost")):
        raise ValueError("not a host of the hub")
    if any(host.endswith("." + h) for h in INTERNAL_HOSTS):
        raise ValueError("not a host of the hub")
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return
    raise ValueError("a host name, not an address")


# ------------------------------------------------------- the allow-list --
@dataclass(frozen=True)
class AllowedServer:
    """One entry of infra/mcp/servers.yaml: the only container servers the
    hub runs (a reviewed change adds one)."""

    key: str
    image: str
    url: str
    tools: dict[str, str]  # name -> the lowest class a registration may seal
    banned: tuple[str, ...]  # fnmatch patterns: never enabled
    needs_internet: bool
    needs_secret: bool

    def is_banned(self, name: str) -> bool:
        return any(fnmatch.fnmatchcase(name, pattern) for pattern in self.banned)


_ALLOWED: dict[tuple[str, float], dict[str, AllowedServer]] = {}


def allowlist_path() -> Path:
    return Path(os.environ.get(ALLOWLIST_ENV, DEFAULT_ALLOWLIST))


def allowlist(path: Path | None = None) -> dict[str, AllowedServer]:
    """The reviewed allow-list by key; empty when the file is missing or
    unreadable (fail closed: no container server is accepted then)."""
    path = path or allowlist_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    cached = _ALLOWED.get((str(path), mtime))
    if cached is not None:
        return cached
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        out = {
            str(e["key"]): AllowedServer(
                key=str(e["key"]),
                image=str(e["image"]),
                url=str(e["url"]),
                tools={str(t["name"]): str(t["class"]) for t in e.get("tools") or []},
                banned=tuple(str(b) for b in e.get("banned_tools") or []),
                # Unsaid is the safe side: not runnable in this version.
                needs_internet=bool(e.get("needs_internet", True)),
                needs_secret=bool(e.get("needs_secret", True)),
            )
            for e in data.get("servers") or []
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError):
        return {}
    _ALLOWED.clear()
    _ALLOWED[(str(path), mtime)] = out
    return out


def check_container(body: McpServerIn) -> None:
    """A `container` registration is exactly a reviewed entry: its key, image
    digest and URL, no secret, no banned or unreviewed tool enabled and no
    class below the reviewed one. Checked before the seal is spent."""
    entry = allowlist().get(body.key)
    if entry is None:
        raise ApiError(
            422,
            "validation_failed",
            fields={"key": "not a reviewed container server (infra/mcp/servers.yaml)"},
        )
    if entry.needs_internet or entry.needs_secret:
        raise ApiError(409, "not_ready", LATER_VERSION)
    if body.image != entry.image:
        raise ApiError(
            422,
            "validation_failed",
            fields={"image": "not the reviewed image digest of this server"},
        )
    if body.url != entry.url:
        raise ApiError(
            422, "validation_failed", fields={"url": f"the reviewed address is {entry.url}"}
        )
    if body.auth_header is not None:
        raise ApiError(
            422, "validation_failed", fields={"auth_header": "a container server takes no secret"}
        )
    bad: list[str] = []
    for t in body.tools:
        if not t.enabled:
            continue
        reviewed = entry.tools.get(t.name)
        if entry.is_banned(t.name):
            bad.append(f"{t.name}: always off")
        elif reviewed is None:
            bad.append(f"{t.name}: not a reviewed tool of this server")
        elif CLASS_RANK[t.cls] < CLASS_RANK.get(reviewed, 3):
            bad.append(f"{t.name}: its class is at least {reviewed}")
    if bad:
        raise ApiError(422, "validation_failed", fields={"tools": "; ".join(bad)[:500]})


def runnable(row: dict[str, Any], containers_on: bool) -> str | None:
    """None when the server may run on this build, else why not: a
    `container` server while the mcp profile is off, or whose sealed image or
    address is no longer the reviewed one."""
    if row["transport"] != "container":
        return None
    if not containers_on:
        return PROFILE_OFF
    entry = allowlist().get(str(row["key"]))
    if entry is None or entry.image != row["image"] or entry.url != row["url"]:
        return NOT_REVIEWED
    return None


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


class ListedTool(BaseModel):
    name: str
    description: str


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
    listed_tools: list[ListedTool] | None
    listed_at: datetime | None
    added_at: datetime
    enabled_at: datetime | None
    version: int


def _listed(r: dict[str, Any]) -> list[ListedTool] | None:
    if r.get("listing") is not None:
        return [
            ListedTool(name=str(t.get("name", "")), description=str(t.get("description") or ""))
            for t in r["listing"]
        ]
    if r.get("listed_tools") is not None:  # listed before 7.1: names only
        return [ListedTool(name=n, description="") for n in r["listed_tools"]]
    return None


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
        listed_tools=_listed(r),
        listed_at=r["listed_at"],
        added_at=r["added_at"],
        enabled_at=r["enabled_at"],
        version=r["version"],
    )


_FRACTION = re.compile(r"(\.\d{6})\d+")


def _written_at(meta: dict[str, Any]) -> datetime | None:
    raw = meta.get("created_time")
    if not isinstance(raw, str):
        return None
    try:  # RFC 3339 with nanoseconds: cut to microseconds
        return datetime.fromisoformat(_FRACTION.sub(r"\1", raw.replace("Z", "+00:00")))
    except ValueError:
        return None


async def _stored(hub: Any, row: dict[str, Any]) -> str | None:
    """The server's secret in OpenBao, or None: not there, OpenBao away, or
    written before the registration moved the server to another host."""
    bao = getattr(hub, "bao", None)
    if bao is None:
        return None
    path = SECRET_PATH.format(key=row["key"])
    reset = row.get("secret_reset_at")
    try:
        if reset is None:
            data = await bao.read_kv(path)
        else:
            data, meta = await bao.read_kv_meta(path)
            written = _written_at(meta)
            if written is None or written <= reset:
                return None
    except Exception:  # noqa: BLE001 - not there (or OpenBao away): no secret
        return None
    token = data.get("token") if isinstance(data, dict) else None
    return str(token) if token else None


async def has_secret(hub: Any, row: dict[str, Any]) -> bool:
    return await _stored(hub, row) is not None


async def secret(hub: Any, row: dict[str, Any]) -> str | None:
    return await _stored(hub, row)


async def load(tx: Tx, key: str, *, lock: bool = False) -> dict[str, Any] | None:
    if lock:
        return await tx.first("SELECT * FROM tools.mcp_servers WHERE key = :k FOR UPDATE", k=key)
    return await tx.first("SELECT * FROM tools.mcp_servers WHERE key = :k", k=key)


async def put(
    tx: Tx, body: McpServerIn, by: str, known_companies: set[str]
) -> tuple[dict[str, Any], bool]:
    """(row, changed): a new registration, or a new version of one, pending
    until enabled. The same body again changes nothing (an enabled server
    stays enabled). Another host voids the stored secret."""
    if isinstance(body.companies, list):
        unknown = sorted(set(body.companies) - known_companies)
        if unknown:
            raise ApiError(422, "validation_failed", fields={"companies": f"unknown: {unknown}"})
    sha = registration_sha256(body)
    prev = await load(tx, body.key, lock=True)
    if prev is not None and prev["registration_sha256"] == sha:
        return prev, False
    moved = prev is not None and host_of(prev["url"]) != host_of(body.url)
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
        "sha": sha,
        "by": by,
        "first": None,
        "again": "registration changed",
        "moved": moved,
    }
    row: dict[str, Any] = await tx.one(
        """INSERT INTO tools.mcp_servers (key, title_fa, transport, url, image, tools, companies,
               auth_header, registration_sha256, added_by, status_reason)
           VALUES (:k, :t, :tr, :u, :i, CAST(:tools AS jsonb), :co, :ah, :sha, :by, :first)
           ON CONFLICT (key) DO UPDATE SET
               title_fa = EXCLUDED.title_fa, transport = EXCLUDED.transport, url = EXCLUDED.url,
               image = EXCLUDED.image, tools = EXCLUDED.tools, companies = EXCLUDED.companies,
               auth_header = EXCLUDED.auth_header,
               registration_sha256 = EXCLUDED.registration_sha256,
               status = 'pending', status_reason = :again,
               listing_sha256 = NULL, pinned = NULL, enabled_at = NULL, updated_at = now(),
               secret_reset_at = CASE WHEN :moved THEN now()
                                      ELSE tools.mcp_servers.secret_reset_at END
           RETURNING *""",
        **values,
    )
    return row, True


async def set_status(
    tx: Tx,
    key: str,
    status: str,
    reason: str | None,
    *,
    enable: bool = False,
    containers_on: bool = False,
) -> dict[str, Any]:
    row = await load(tx, key, lock=True)
    if row is None:
        raise ApiError(404, "not_found")
    if enable and (why := runnable(row, containers_on)) is not None:
        raise ApiError(409, "not_ready", why)
    updated: dict[str, Any] = await tx.one(
        """UPDATE tools.mcp_servers SET status = :st, status_reason = :r, updated_at = now(),
               enabled_at = CASE WHEN :en THEN now() ELSE enabled_at END,
               listing_sha256 = CASE WHEN :en THEN NULL ELSE listing_sha256 END,
               pinned = CASE WHEN :en THEN NULL ELSE pinned END
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


def for_company(row: dict[str, Any], company: str | None) -> bool:
    """Whether the server's registration lets `company` use it."""
    return row["companies"] is None or (company is not None and company in row["companies"])


# ------------------------------------------------------------ the listing --
def diff(pinned: list[dict[str, Any]] | None, listing: list[dict[str, Any]]) -> dict[str, Any]:
    """The tools a listing adds, removes and changes against the sealed one
    (a changed digest: its description, schemas, title or annotations)."""
    old = {str(t["name"]): str(t.get("sha256") or "") for t in pinned or []}
    new = {str(t["name"]): str(t.get("sha256") or "") for t in listing}
    return {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "changed": sorted(n for n in set(old) & set(new) if old[n] != new[n]),
    }


async def withdraw_cards(tx: Tx, key: str, note: str) -> list[dict[str, Any]]:
    """Every pending `tool_enable` card of the server becomes `withdrawn`
    (never deleted): what it would seal is no longer what the server is."""
    rows = await tx.all(
        """UPDATE cartable.decisions d
              SET status = 'withdrawn', decided_at = now(), decided_by_kind = 'service',
                  decided_by_code = 'system', note = :note
             FROM core.companies c
            WHERE c.id = d.company_id AND d.kind = 'tool_enable' AND d.status = 'pending'
              AND d.payload ->> 'key' = :k
        RETURNING d.ref, d.company_id, c.code AS company""",
        k=key,
        note=note[:5000],
    )
    from hq_api import events  # here: events imports nothing of the domain

    for r in rows:
        await events.emit(
            tx,
            r["company"],
            "decision.updated",
            r["ref"],
            {"status": "withdrawn", "kind": "tool_enable", "note": note[:300]},
        )
    return [dict(r) for r in rows]


async def sealed_listing(tx: Tx, d: dict[str, Any]) -> dict[str, Any]:
    """The server a `tool_enable` card would re-enable, locked; 409
    decision_not_pending when it is no longer what the card shows (another
    listing since, another registration, or not switched off for its tools)."""
    p = d["payload"]
    row = await load(tx, str(p.get("key") or ""), lock=True)
    if (
        row is None
        or row["status"] != "disabled"
        or row["status_reason"] != TOOLS_CHANGED
        or row["listed_sha256"] != p.get("listing_sha256")
        or row["registration_sha256"] != p.get("registration_sha256")
    ):
        raise ApiError(
            409, "decision_not_pending", f"{d['ref']} is superseded: the server changed since"
        )
    return row


async def enable_listing(tx: Tx, row: dict[str, Any]) -> dict[str, Any]:
    """Re-enabled with exactly the listing the owner sealed on the card."""
    out: dict[str, Any] = await tx.one(
        """UPDATE tools.mcp_servers SET status = 'enabled', status_reason = NULL,
               listing_sha256 = listed_sha256, pinned = listing, enabled_at = now(),
               updated_at = now()
           WHERE key = :k RETURNING *""",
        k=row["key"],
    )
    return out


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


def catalog(
    lib: Any, servers: list[dict[str, Any]], containers_on: bool = False
) -> list[CatalogTool]:
    """Every tool of agents/tools.md (and each sealed MCP tool): its class, the
    roles whose charters grant it, and whether this build carries it out (a
    `container` server's tools only while it can run here)."""
    roles: dict[str, list[str]] = {}
    for role, charter in sorted(lib.roles.items()):
        for t in charter.tools:
            roles.setdefault(t, []).append(role)
    live_mcp = any(s["status"] == "enabled" and runnable(s, containers_on) is None for s in servers)
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
        description = s["title_fa"]
        why = runnable(s, containers_on)
        if why is not None:
            # Registered, sealed or not, it cannot run here (prompt 12 §14).
            state = "channel_not_configured"
            label = PROFILE_OFF_FA if why == PROFILE_OFF else NOT_REVIEWED_FA
            description = f"{label} ({why.split(':')[0]}) · {description}"
        for tool in s["tools"] or []:
            out.append(
                CatalogTool(
                    name=f"{s['key']}/{tool['name']}",
                    source="mcp",
                    cls=str(tool["class"]),
                    per_call=False,
                    input="{server, tool, args}",
                    description=description[:500],
                    roles=mcp_roles,
                    status=state if tool.get("enabled", True) else "off",
                    server=s["key"],
                )
            )
    return out
