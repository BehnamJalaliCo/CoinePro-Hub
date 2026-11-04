"""Company kits: a ready company from one order (contract §31.2).

A kit is a file (apps/api/seed/kits/<key>.yaml), data, never naming a company:
its team template, the working groups it joins, its production lines (drafts),
its KPIs, and the connections it will use (created `not_connected`). `load`
validates every file; a broken file stops the start, not a later order.

`describe` is what a kit will make (nothing written); `create` makes it in
the caller's transaction, after the company row exists:
  - the team: the template's departments and leadership positions (the
    existing `templates.apply` path), all asleep;
  - the memberships of the kit's groups (seats resolved to the company's
    employees; an empty seat is the group tick's, as for any member);
  - the KPIs: the standard set plus the kit's own definitions (manual figures);
  - the connections, `not_connected`;
  - its lines as drafts through `hq_api.lines.store.create_line` (the lines
    engine, §30; imported when needed: while it is not there the lines are
    answered as `lines_pending`, never a failure).
A server is never created here (founding is separate). Rules only, no model.
"""

from __future__ import annotations

import importlib
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from pydantic import BaseModel, Field

from hq_api.db import Tx
from hq_api.domain import connections as CN
from hq_api.domain import gov_kpis, templates
from hq_api.domain import groups as GR
from hq_api.errors import ApiError

log = logging.getLogger("hq_api.kits")

KITS_DIR = Path(__file__).resolve().parents[3] / "seed" / "kits"
KEY = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
KPI_KEY = re.compile(r"^[a-z][a-z0-9_.]{1,60}$")
# §30.1: a line's platform is a string in data; these are the ones with an adapter.
PLATFORMS = (
    "instagram_reel", "instagram_post", "instagram_story", "youtube_short", "youtube_long",
    "telegram_post", "site_article",
)  # fmt: skip
TOP_KEYS = {
    "key", "title_fa", "purpose_fa", "team_template", "groups", "lines", "kpis", "connections",
    "defaults",
}  # fmt: skip
KPI_CARDS = gov_kpis.CARDS
MAX_LINES = 12
DEFAULT_CONFIG: dict[str, dict[str, Any]] = {"instagram": {"via": "ig_hub", "accounts": []}}
LINES_PENDING_FA = "موتور خط‌ها هنوز روی این هاب نیست؛ خط‌ها بعد از آمدنش ساخته میشود"


def _bad(key: str, why: str) -> ValueError:
    return ValueError(f"kit {key}: {why}")


def standard_kpis() -> dict[str, tuple[str, dict[str, Any]]]:
    """key -> (card, definition) of seed/kpis/standard.yaml's company cards."""
    out: dict[str, tuple[str, dict[str, Any]]] = {}
    for card, items in (gov_kpis.load_seed().get("company") or {}).items():
        for k in items or []:
            out[str(k["key"])] = (card, dict(k))
    return out


def validate(key: str, d: dict[str, Any]) -> None:
    """A kit file's shape; raises ValueError naming the first fault."""
    if not isinstance(d, dict):
        raise _bad(key, "not an object")
    extra = set(d) - TOP_KEYS
    if extra:
        raise _bad(key, f"unknown keys {sorted(extra)}")
    if d.get("key") != key or not KEY.match(key):
        raise _bad(key, "`key` must equal the file name (lower snake case)")
    for f in ("title_fa", "purpose_fa"):
        if not isinstance(d.get(f), str) or not d[f].strip():
            raise _bad(key, f"`{f}` is required")
    tpl = d.get("team_template")
    if not isinstance(tpl, str) or templates.template(tpl) is None or tpl == "holding":
        raise _bad(key, f"unknown team_template {tpl!r}")
    groups = d.get("groups") or []
    known = {k for k, _ in GR.load_files()}
    if not isinstance(groups, list) or any(g not in known for g in groups):
        raise _bad(key, f"groups must be keys of seed/groups: {groups!r}")
    lines = d.get("lines") or []
    if not isinstance(lines, list) or len(lines) > MAX_LINES:
        raise _bad(key, f"lines: a list of at most {MAX_LINES}")
    for ln in lines:
        if not isinstance(ln, dict) or set(ln) - {"template", "platform", "title_fa"}:
            raise _bad(key, f"a line is {{template, platform, title_fa}}: {ln!r}")
        if not KEY.match(str(ln.get("template"))) or ln.get("platform") not in PLATFORMS:
            raise _bad(key, f"line template or platform unknown: {ln!r}")
        if not isinstance(ln.get("title_fa"), str) or not ln["title_fa"].strip():
            raise _bad(key, f"a line needs title_fa: {ln!r}")
    std = standard_kpis()
    seen: set[str] = set()
    for k in d.get("kpis") or []:
        name = k if isinstance(k, str) else (k or {}).get("key")
        if not isinstance(name, str) or not KPI_KEY.match(name) or name in seen:
            raise _bad(key, f"kpi key invalid or repeated: {name!r}")
        seen.add(name)
        if isinstance(k, str):
            if k not in std:
                raise _bad(key, f"kpi {k} is not in seed/kpis/standard.yaml (define it)")
            continue
        if k.get("source", "manual") != "manual":
            raise _bad(key, f"kpi {name}: a kit defines manual figures only")
        if not isinstance(k.get("name_fa"), str) or not k["name_fa"].strip():
            raise _bad(key, f"kpi {name}: name_fa is required")
        if k.get("direction", "up") not in ("up", "down", "range"):
            raise _bad(key, f"kpi {name}: direction")
        if k.get("card", "growth") not in KPI_CARDS:
            raise _bad(key, f"kpi {name}: card")
    conns = d.get("connections") or []
    if (
        not isinstance(conns, list)
        or any(c not in CN.KINDS for c in conns)
        or len(set(conns)) != len(conns)
    ):
        raise _bad(key, f"connections must be distinct kinds of the connections: {conns!r}")
    if not isinstance(d.get("defaults", {}), dict):
        raise _bad(key, "`defaults` is an object")


def load_files(root: Path | None = None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted((root or KITS_DIR).glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        validate(path.stem, data)
        out[path.stem] = data
    return out


@lru_cache(maxsize=1)
def _cached() -> str:
    return json.dumps(load_files(), ensure_ascii=False)


def kits() -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = json.loads(_cached())
    return data


def kit(key: str) -> dict[str, Any]:
    d = kits().get(key)
    if d is None:
        raise ApiError(404, "not_found", f"kit {key}")
    return d


# ------------------------------------------------------------------ shapes --
class KitDepartment(BaseModel):
    code: str
    name_fa: str


class KitTeam(BaseModel):
    departments: list[KitDepartment]
    positions: int  # the CEO, one manager per department, the extra positions: asleep


class KitGroup(BaseModel):
    key: str
    title_fa: str


class KitLine(BaseModel):
    template: str
    platform: str
    title_fa: str
    ref: str | None = None  # the draft line's ref once made
    why_fa: str | None = None  # why a line is pending


class KitKpi(BaseModel):
    key: str
    name_fa: str
    card: str
    unit: str = ""
    manual: bool


class KitConnection(BaseModel):
    kind: str
    label_fa: str


class KitSummary(BaseModel):
    """What a kit makes (nothing about any company)."""

    key: str
    title_fa: str
    purpose_fa: str
    team_template: str
    team: KitTeam
    groups: list[KitGroup]
    lines: list[KitLine]
    kpis: list[KitKpi]
    connections: list[KitConnection]
    todo_fa: list[str] = Field(description="what the owner still has to do after it")


class KitCard(BaseModel):
    """The kit preview card of an order report (§31.2): the secretary's draft
    of «یک شرکت تازه …»; nothing exists until the owner seals."""

    kit: str
    title_fa: str
    name_fa: str | None = None
    sealed: bool = False
    summary: KitSummary


# -------------------------------------------------------------- describing --
def kpi_entries(d: dict[str, Any]) -> list[dict[str, Any]]:
    """The kit's KPIs as {key, name_fa, card, source, unit, ...} (resolved)."""
    std = standard_kpis()
    out: list[dict[str, Any]] = []
    for k in d.get("kpis") or []:
        if isinstance(k, str):
            card, base = std[k]
            out.append({**base, "card": card, "extra": False})
        else:
            out.append({"source": "manual", "card": "growth", **k, "extra": True})
    return out


def connection_entries(d: dict[str, Any]) -> list[dict[str, str]]:
    return [{"kind": c, "label_fa": CN.LABEL_FA.get(c, c)} for c in d.get("connections") or []]


def todo_of(d: dict[str, Any]) -> list[str]:
    """What the owner still has to do after the company exists (plain Persian)."""
    todo = [
        f"اتصال «{c['label_fa']}» را در صفحه‌ی اتصال‌های شرکت وصل کنید" for c in connection_entries(d)
    ]
    if d.get("lines"):
        todo.append("هر خط تولید پیش‌نویس است؛ بعد از وصل شدن حساب‌ها یکی‌یکی آن را روشن کنید")
    todo.append("جاهای خالی تیم با استخدام خودکار پر میشود؛ استخدام باید باز باشد")
    todo.append("سرور شرکت جدا و با تأسیس ساخته میشود؛ با این فرمان سروری ساخته نشد")
    return todo


def describe(key: str) -> KitSummary:
    """What the kit makes, independent of any company (GET /kits/{key})."""
    d = kit(key)
    t = templates.template(d["team_template"]) or {}
    depts = [
        {"code": x["code"], "name_fa": x["name_fa"]}
        for x in sorted(t.get("departments") or [], key=lambda x: int(x.get("sort", 100)))
    ]
    lead = t.get("leadership") or {}
    positions = (
        (1 if lead.get("ceo") else 0)
        + (
            sum(1 for x in t.get("departments") or [] if x.get("manager", True) is not False)
            if lead.get("managers")
            else 0
        )
        + len(lead.get("extra") or [])
    )
    files = dict(GR.load_files())
    return KitSummary(
        key=d["key"],
        title_fa=d["title_fa"],
        purpose_fa=d["purpose_fa"],
        team_template=d["team_template"],
        team=KitTeam(departments=[KitDepartment(**x) for x in depts], positions=positions),
        groups=[KitGroup(key=g, title_fa=files[g]["title_fa"]) for g in d.get("groups") or []],
        lines=[KitLine(**x) for x in d.get("lines") or []],
        kpis=[
            KitKpi(
                key=e["key"],
                name_fa=e["name_fa"],
                card=e["card"],
                unit=e.get("unit") or "",
                manual=e.get("source") == "manual",
            )
            for e in kpi_entries(d)
        ],
        connections=[KitConnection(**c) for c in connection_entries(d)],
        todo_fa=todo_of(d),
    )


# ---------------------------------------------------------------- creating --
def _ref_of(line: Any) -> str | None:
    ref = line.get("ref") if isinstance(line, dict) else getattr(line, "ref", None)
    return str(ref) if ref else None


async def _join_groups(tx: Tx, company_id: UUID, keys: list[str]) -> tuple[list[str], list[str]]:
    joined: list[str] = []
    missing: list[str] = []
    for key in keys:
        g = await tx.first("SELECT * FROM growth.groups WHERE key = :k", k=key)
        if g is None or g["state"] != "on":
            missing.append(key)
            continue
        roles = sorted({s["role"] for s in g["definition"]["seats"]})
        holders = await GR.seat_holders(tx, company_id, roles)
        seats = [
            {"seat": s["seat"], "role": s["role"], "employee": holders.get(s["role"])}
            for s in g["definition"]["seats"]
        ]
        await tx.exec(
            """INSERT INTO growth.memberships (company_id, group_id, seats)
               VALUES (:co, :g, CAST(:s AS jsonb)) ON CONFLICT (group_id, company_id) DO NOTHING""",
            co=company_id,
            g=g["id"],
            s=json.dumps(seats, ensure_ascii=False),
        )
        joined.append(key)
    return joined, missing


async def _add_kpis(tx: Tx, company_id: UUID, d: dict[str, Any]) -> int:
    """The standard set, then the kit's own definitions (never over an existing key)."""
    n = await gov_kpis.seed_company(tx, company_id, "company")
    for e in kpi_entries(d):
        if not e["extra"]:
            continue
        if await tx.scalar(
            "SELECT 1 FROM governance.kpis WHERE company_id = :co AND key = :k",
            co=company_id,
            k=e["key"],
        ):
            continue
        row = gov_kpis._definition(e, e["card"], "standard")
        await gov_kpis._insert(tx, company_id, row)
        n += 1
    return n


async def _add_connections(tx: Tx, company_id: UUID, d: dict[str, Any]) -> int:
    n = 0
    for c in connection_entries(d):
        made = await tx.scalar(
            """INSERT INTO growth.connections (company_id, kind, label_fa, config, origin)
               VALUES (:co, :k, :l, CAST(:c AS jsonb), 'seed')
               ON CONFLICT (company_id, kind) DO NOTHING RETURNING id""",
            co=company_id,
            k=c["kind"],
            l=c["label_fa"][:200],
            c=json.dumps(DEFAULT_CONFIG.get(c["kind"], {}), ensure_ascii=False),
        )
        n += 1 if made else 0
    return n


async def _add_lines(
    tx: Tx, company_id: UUID, d: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The kit's lines as drafts. (made, pending): pending when the engine is
    not on this hub, or a line was refused (its reason, never silent)."""
    wanted = list(d.get("lines") or [])
    if not wanted:
        return [], []
    try:  # the lines engine (§30), when it is on this hub
        create_line = importlib.import_module("hq_api.lines.store").create_line
    except (ImportError, AttributeError):
        return [], [{**x, "why_fa": LINES_PENDING_FA} for x in wanted]
    made: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for x in wanted:
        try:
            async with tx.conn.begin_nested():
                line = await create_line(
                    tx,
                    company_id=company_id,
                    template_key=x["template"],
                    platform=x["platform"],
                    title_fa=x["title_fa"],
                    channel=None,
                    by="kit",
                )
        except Exception as e:  # noqa: BLE001 - one refused line must not undo the company
            why = e.code if isinstance(e, ApiError) else type(e).__name__
            log.warning("a kit line was refused", extra={"template": x["template"], "why": why})
            pending.append({**x, "why_fa": "این خط ساخته نشد؛ از صفحه‌ی خط‌ها دوباره بسازید"})
            continue
        made.append({**x, "ref": _ref_of(line)})
    return made, pending


async def create(tx: Tx, company_id: UUID, company_code: str, key: str) -> dict[str, Any]:
    """Everything of the kit but the company row, in the caller's transaction."""
    d = kit(key)
    added = await templates.apply(tx, company_id, company_code, d["team_template"])
    joined, groups_pending = await _join_groups(tx, company_id, list(d.get("groups") or []))
    kpis = await _add_kpis(tx, company_id, d)
    connections = await _add_connections(tx, company_id, d)
    lines, lines_pending = await _add_lines(tx, company_id, d)
    out: dict[str, Any] = {
        "team": added,
        "groups": joined,
        "kpis": kpis,
        "connections": connections,
        "lines": lines,
        "todo_fa": todo_of(d),
    }
    if lines_pending:
        out["lines_pending"] = lines_pending
    if groups_pending:
        out["groups_pending"] = groups_pending
    return out
