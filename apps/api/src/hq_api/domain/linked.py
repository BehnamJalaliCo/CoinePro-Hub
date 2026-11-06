"""Data along a company link (`linked.read`, A0), the owner, 2026-11-06: «شرکت‌ها بتونن دیتا به هم
بدهند … عین رگ انسان باید باشه».

A company reads another company's working data the way a cross-company request goes (contract
§35.6): while the owner's `links_enforced` is off (the default) any active company reads any other
active company; while it is on, only along an `on` link between the two (either way). The holding's
data is never read this way. Its own company any agent reads; the holding's readers (charter scope
`holding`: the advisor, the overseer, AI operations) read any company, as with every read tool. The
policy decides (OPA `hq.internal`, linked.rego); the api sends the facts (the company's kind and
state, whether the two are linked, whether links are enforced), never the caller's input.

What: its profile (who it is, what it does and has: `profile()`, reused by the capability brief),
its KPIs, its latest outputs (and one output's body), its latest deep catalogue in short, its
connections' state and daily figures (for Instagram the accounts seen on IG-Hub), its links.

Never customer data or a secret:
- no output of a department that holds customers' conversations (SALES: support and the CRM);
- a connection's state, figures and public handles only (never a token, a command, a setting that
  is not a public handle, or whether its secret is set);
- servers by name only (never an address); the catalogue's titles, summaries and counts only;
- every text masked again (hq_common.redact) before it leaves; the gateway masks once more.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from hq_api.db import Tx
from hq_api.domain import catalogue as CAT
from hq_api.domain import connections as CN
from hq_api.domain import gov_kpis as K
from hq_api.domain import links as L
from hq_common.redact import redact_async, scrub

What = Literal["profile", "kpis", "outputs", "catalogue", "connections", "links"]
# own: the caller's company; link: an `on` link; open: links are not enforced (any active company);
# holding: a holding reader
Via = Literal["own", "link", "open", "holding"]
WHATS: tuple[str, ...] = ("profile", "kpis", "outputs", "catalogue", "connections", "links")
MANDATE_MAX = 300  # a department's mandate in the profile
OUTPUTS = 20  # the latest outputs listed
SUMMARY_MAX = 400  # an output's or a catalogue section's summary
BODY_MAX = 12_000  # one output's body (the rest stays with its company)
DAYS = 14  # a connection's daily figures
# Departments whose outputs carry customers' words (the support desk, the CRM): never along a link.
CUSTOMER_DEPARTMENTS: tuple[str, ...] = ("SALES",)
REF = r"^O-[0-9]{4,}$"


# ------------------------------------------------------------------ shapes --
class LinkedKpi(BaseModel):
    key: str
    name_fa: str
    card: str
    unit: str
    direction: str
    value: float | None
    at: datetime | None
    target: float | None
    target_max: float | None
    state: Literal["ok", "stale", "no_source"]


class LinkedOutput(BaseModel):
    ref: str
    title: str
    summary: str
    producer: str  # the producer's title (Persian), never a person's data
    at: datetime


class LinkedOutputBody(LinkedOutput):
    body: str
    truncated: bool


class LinkedSection(BaseModel):
    key: str
    title_fa: str
    summary_fa: str | None
    count: int | None


class LinkedCatalogue(BaseModel):
    at: datetime
    state: Literal["running", "done", "failed"]
    deliverable: str | None
    sections: list[LinkedSection]


class LinkedDaily(BaseModel):
    day: date
    key: str
    value: float
    subject: str


class LinkedConnection(BaseModel):
    kind: str
    label_fa: str
    state: Literal["not_connected", "connected", "error"]
    last_read_at: datetime | None
    daily: list[LinkedDaily]
    # instagram: the accounts its daily figures name (the ones IG-Hub reads), else null
    accounts: list[str] | None = None


class LinkedLink(BaseModel):
    company: str
    name_fa: str | None
    kind: str
    purpose_fa: str
    outgoing: bool


class ProfileDepartment(BaseModel):
    code: str
    name_fa: str
    name_en: str
    mandate: str | None  # its mandate in one line (from, to, outputs), at most 300 characters
    manager: str | None  # the manager's employee code


class ProfileServer(BaseModel):
    name: str  # never an address


class ProfileConnection(BaseModel):
    kind: str
    label_fa: str
    state: Literal["not_connected", "connected", "error"]
    # the public handles of its settings only: accounts, channels, a site, a channel id, and the
    # server it is read through (`via`, e.g. IG-Hub of company IG); never a token or a command
    handles: dict[str, Any]
    accounts_seen: list[str] = []  # instagram: the accounts its figures named in the last 14 days


class ProfileLine(BaseModel):
    ref: str
    title_fa: str
    platform: str


class ProfileGroup(BaseModel):
    key: str
    title_fa: str
    state: Literal["on", "paused"]


class LinkedProfile(BaseModel):
    code: str
    name_fa: str | None
    name_en: str | None
    kind: str
    status: str
    departments: list[ProfileDepartment]
    sites: list[str]
    connections: list[ProfileConnection]
    servers: list[ProfileServer]
    lines: list[ProfileLine]  # the production lines that are on
    groups: list[ProfileGroup]  # the working groups it is in


class LinkedRead(BaseModel):
    """One read along a link: the field named by `what` is filled (`output` for `outputs` with a
    `ref`); `via` says why it was allowed: the caller's own company, an `on` link, or a holding
    reader. `note_fa` says plainly when there is nothing yet."""

    company: str
    name_fa: str
    what: What
    via: Via
    profile: LinkedProfile | None = None
    kpis: list[LinkedKpi] | None = None
    outputs: list[LinkedOutput] | None = None
    output: LinkedOutputBody | None = None
    catalogue: LinkedCatalogue | None = None
    connections: list[LinkedConnection] | None = None
    links: list[LinkedLink] | None = None
    note_fa: str | None = None


def _short(text: Any, limit: int = SUMMARY_MAX) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


# ----------------------------------------------------------------- reads --
async def kpis(tx: Tx, company_id: UUID, now: datetime | None = None) -> list[LinkedKpi]:
    """The company's active KPIs with their latest value (none is ever guessed: no value, no
    number)."""
    now = now or datetime.now(UTC)
    have = await K.available(tx)
    out = []
    for k in await K.company_kpis(tx, company_id):
        state = K.state_of(k, now, have)
        known = state != "no_source"
        out.append(
            LinkedKpi(
                key=k["key"],
                name_fa=k["name_fa"],
                card=k["card"],
                unit=k["unit"],
                direction=k["direction"],
                value=float(k["last_value"]) if known and k["last_value"] is not None else None,
                at=k["last_at"] if known else None,
                target=float(k["target"]) if k["target"] is not None else None,
                target_max=float(k["target_max"]) if k["target_max"] is not None else None,
                state=state,
            )
        )
    return out


_OUTPUT_SQL = """
    SELECT d.ref, d.title, d.summary, d.body, d.created_at, e.title_fa AS producer
    FROM cartable.deliverables d
    JOIN core.employees e ON e.id = d.producer_id
    JOIN work.work w ON w.id = d.work_id
    LEFT JOIN core.departments dep ON dep.id = w.department_id
    WHERE d.company_id = :co AND (dep.code IS NULL OR dep.code <> ALL(:hidden))"""


def _output(r: dict[str, Any]) -> LinkedOutput:
    return LinkedOutput(
        ref=r["ref"],
        title=_short(r["title"], 300),
        summary=_short(r["summary"]),
        producer=r["producer"],
        at=r["created_at"],
    )


async def outputs(tx: Tx, company_id: UUID) -> list[LinkedOutput]:
    """The company's latest deliverables (newest first): ref, title, a short summary, who made
    it (a title), when."""
    rows = await tx.all(
        _OUTPUT_SQL + " ORDER BY d.created_at DESC, d.ref DESC LIMIT :n",
        co=company_id,
        hidden=list(CUSTOMER_DEPARTMENTS),
        n=OUTPUTS,
    )
    return [_output(r) for r in rows]


async def output(tx: Tx, company_id: UUID, ref: str) -> LinkedOutputBody | None:
    """One deliverable with its body, only when it is that company's (and not a customer
    department's); None otherwise."""
    r = await tx.first(
        _OUTPUT_SQL + " AND d.ref = :ref", co=company_id, hidden=list(CUSTOMER_DEPARTMENTS), ref=ref
    )
    if r is None:
        return None
    body = str(r["body"] or r["summary"] or "")
    return LinkedOutputBody(
        **_output(r).model_dump(), body=body[:BODY_MAX], truncated=len(body) > BODY_MAX
    )


async def catalogue(tx: Tx, company_id: UUID) -> LinkedCatalogue | None:
    """The latest finished deep catalogue (else the latest at all, with its state): each section's
    title, short summary and count, never its tables."""
    row = await tx.first(
        CAT.CAT_SQL
        + """ WHERE k.company_id = :co
              ORDER BY k.state = 'done' DESC, k.created_at DESC LIMIT 1""",
        co=company_id,
    )
    if row is None:
        return None
    sections = []
    for x in row["sections"] or []:
        s = CAT.stored(x)
        sections.append(
            LinkedSection(
                key=str(s.get("key") or ""),
                title_fa=str(s.get("title_fa") or ""),
                summary_fa=_short(s["summary_fa"]) if s.get("summary_fa") else None,
                count=s.get("count"),
            )
        )
    return LinkedCatalogue(
        at=row["created_at"],
        state=row["state"],
        deliverable=row["deliverable_ref"],
        sections=sections,
    )


def _accounts(daily: list[Any]) -> list[str]:
    return sorted({str(d.subject).lstrip("@").lower() for d in daily if d.subject})


async def connections(tx: Tx, company: Any) -> list[LinkedConnection]:
    """Every connection's state and its last DAYS days of figures (no config, no secret); for
    Instagram the accounts the figures name (those IG-Hub reads for the company)."""
    return [
        LinkedConnection(
            kind=c.kind,
            label_fa=c.label_fa,
            state=c.state,
            last_read_at=c.last_read_at,
            daily=[LinkedDaily(**d.model_dump()) for d in c.daily],
            accounts=_accounts(c.daily) if c.kind == "instagram" else None,
        )
        for c in await CN.list_for(tx, company, days=DAYS)
    ]


# --------------------------------------------------------------- profile --
_HANDLE = re.compile(r"^@?[A-Za-z0-9_.\-]{2,64}$")
_URL = re.compile(r"^https?://[^\s/@:?#]+(:[0-9]{1,5})?(/[^\s?#@]*)?$")  # no credentials, no query


def _handle(v: Any) -> str | None:
    s = str(v or "").strip()
    return s if _HANDLE.match(s) and scrub(s) == s else None


def _public_url(v: Any) -> str | None:
    s = str(v or "").strip()
    return s if _URL.match(s) and scrub(s) == s else None


def handles(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    """The public handles of a connection's settings (an allow-list, never a token, a command, an
    address with credentials or an internal id): Instagram's accounts and the server it is read
    through, Telegram's channels by their public @name, a site, YouTube's channel id."""
    out: dict[str, Any] = {}
    accounts = [a for a in (_handle(x) for x in config.get("accounts") or []) if a]
    if accounts:
        out["accounts"] = [a.lstrip("@").lower() for a in accounts]
    if kind == "instagram" and config.get("via") == "ig_hub":
        given = config.get("server")
        srv: dict[str, Any] = given if isinstance(given, dict) else {}
        out["via"] = {
            "server": _handle(srv.get("name")) or "IG-Hub",
            "company": _handle(srv.get("company")) or "IG",
        }
    chans = []
    for c in config.get("channels") or []:
        if not isinstance(c, dict):
            continue
        chat = _handle(c.get("chat"))
        name = chat if chat and chat.startswith("@") else None  # a numeric id is not public
        title = _short(c.get("title_fa"), 120) if c.get("title_fa") else None
        if name or title:
            chans.append({"chat": name, "title_fa": title, "role": _handle(c.get("role"))})
    if chans:
        out["channels"] = chans
    site = _public_url(config.get("site_url"))
    if site:
        out["site_url"] = site
    for key in ("channel_id", "handle"):
        v = _handle(config.get(key))
        if v:
            out[key] = v
    urls = [u for u in (_public_url(x) for x in config.get("urls") or []) if u]
    if urls:
        out["urls"] = urls
    return out


def _mandate(m: Any) -> str | None:
    """A department's mandate in one line: what it turns into what, and its outputs."""
    if not isinstance(m, dict):
        return None
    frm, to = str(m.get("from_fa") or "").strip(), str(m.get("to_fa") or "").strip()
    head = f"از «{frm}» به «{to}»" if frm and to else (frm or to)
    outs = "، ".join(str(x).strip() for x in m.get("outputs_fa") or [] if str(x).strip())
    text = "؛ ".join(p for p in (head, f"خروجی‌ها: {outs}" if outs else "") if p)
    return _short(text, MANDATE_MAX) if text else None


async def profile(tx: Tx, company_id: UUID) -> dict[str, Any]:
    """Who a company is and what it does and has, in plain data (masked; never a secret, an
    address or customer data): code, names, kind, status; its active departments (the mandate in
    one line, the manager's code); its checked sites; its connections (state, public handles, and
    for Instagram the server it is read through and the accounts seen); its servers by name; its
    production lines that are on; the working groups it is in.

    Needs a transaction that reaches the company and the holding (the working groups are the
    holding's rows): `hub.db.tx(await hub.companies.ids())`."""
    co = await tx.one(
        "SELECT id, code, name_fa, name_en, kind, status FROM core.companies WHERE id = :c",
        c=company_id,
        not_found="not_found",
    )
    depts = await tx.all(
        """SELECT d.code, d.name_fa, d.name_en, d.mandate,
                  (SELECT m.code FROM core.employees m
                   WHERE m.department_id = d.id AND m.kind IN ('manager', 'inspector')
                     AND m.status <> 'dismissed' ORDER BY m.created_at LIMIT 1) AS manager
           FROM core.departments d
           WHERE d.company_id = :c AND d.status = 'active' ORDER BY d.sort, d.code""",
        c=company_id,
    )
    sites = await tx.all(
        "SELECT url FROM ops.sites WHERE company_id = :c AND enabled ORDER BY url", c=company_id
    )
    conns = await tx.all(
        "SELECT * FROM growth.connections WHERE company_id = :c ORDER BY kind", c=company_id
    )
    seen = [
        str(r["account"])
        for r in await tx.all(
            """SELECT DISTINCT lower(ltrim(subject, '@')) AS account FROM growth.metrics_daily
               WHERE company_id = :c AND kind = 'instagram' AND subject <> ''
                 AND day > current_date - CAST(:d AS int)
               ORDER BY 1""",
            c=company_id,
            d=DAYS,
        )
    ]
    servers = await tx.all(
        """SELECT name FROM infra.servers WHERE company_id = :c
             AND (state IS NULL OR state <> 'revoked') ORDER BY lower(name)""",
        c=company_id,
    )
    lines = await tx.all(
        """SELECT ref, title_fa, platform FROM lines.lines
           WHERE company_id = :c AND state = 'on' ORDER BY ref""",
        c=company_id,
    )
    groups = await tx.all(
        """SELECT g.key, g.title_fa, m.state FROM growth.memberships m
           JOIN growth.groups g ON g.id = m.group_id
           WHERE m.company_id = :c AND g.state = 'on' ORDER BY g.key""",
        c=company_id,
    )
    out = LinkedProfile(
        code=co["code"],
        name_fa=co["name_fa"],
        name_en=co["name_en"],
        kind=co["kind"],
        status=co["status"],
        departments=[
            ProfileDepartment(
                code=d["code"],
                name_fa=d["name_fa"],
                name_en=d["name_en"],
                mandate=_mandate(d["mandate"]),
                manager=d["manager"],
            )
            for d in depts
        ],
        sites=[str(r["url"]) for r in sites if _public_url(r["url"])],
        connections=[
            ProfileConnection(
                kind=r["kind"],
                label_fa=r["label_fa"],
                state=CN.state_of(r["kind"], r),
                handles=handles(r["kind"], dict(r["config"] or {})),
                accounts_seen=seen if r["kind"] == "instagram" else [],
            )
            for r in conns
            if r["kind"] in CN.KINDS
        ],
        servers=[ProfileServer(name=r["name"]) for r in servers],
        lines=[ProfileLine(**r) for r in lines],
        groups=[ProfileGroup(**r) for r in groups],
    )
    masked: dict[str, Any] = await redact_async(out.model_dump(mode="json"))
    return masked


async def links(tx: Tx, company_id: UUID) -> list[LinkedLink]:
    return [LinkedLink(**x) for x in await L.links_of(tx, company_id)]


EMPTY_FA = {
    "profile": "",
    "kpis": "این شرکت هنوز شاخصی ندارد.",
    "outputs": "این شرکت هنوز خروجی‌ای ندارد.",
    "catalogue": "برای این شرکت هنوز فهرست کاملی ساخته نشده است.",
    "connections": "این شرکت هنوز اتصالی ندارد.",
    "links": "این شرکت هنوز به شرکت دیگری وصل نیست.",
}


async def read(tx: Tx, company: Any, what: str, ref: str | None, via: str) -> LinkedRead | None:
    """The answer for `what` (masked again); None for an output `ref` that is not that company's."""
    out = LinkedRead(
        company=company.code,
        name_fa=company.name_fa or company.name_en or company.code,
        what=what,
        via=via,
    )
    empty = False
    if what == "profile":
        out.profile = LinkedProfile.model_validate(await profile(tx, company.id))
    elif what == "kpis":
        out.kpis = await kpis(tx, company.id)
        empty = not out.kpis
    elif what == "outputs" and ref:
        out.output = await output(tx, company.id, ref)
        if out.output is None:
            return None
    elif what == "outputs":
        out.outputs = await outputs(tx, company.id)
        empty = not out.outputs
    elif what == "catalogue":
        out.catalogue = await catalogue(tx, company.id)
        empty = out.catalogue is None
    elif what == "connections":
        out.connections = await connections(tx, company)
        empty = not any(c.state != "not_connected" for c in out.connections)
    else:
        out.links = await links(tx, company.id)
        empty = not out.links
    if empty:
        out.note_fa = EMPTY_FA[what]
    masked = await redact_async(out.model_dump(mode="json"))
    return LinkedRead.model_validate(masked)
