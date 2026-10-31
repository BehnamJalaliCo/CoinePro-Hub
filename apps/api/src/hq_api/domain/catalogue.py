"""The company catalogue (contract §28.2 ⟨1.10⟩, prompt 19): a deep,
read-only extraction of everything a company runs on its own servers, not a
summary.

- A run asks every paired server of the company (§26) for one `claude` job
  per section, each on a fixed, exhaustive brief that reads and changes
  nothing; the answer of each job is one JSON section (tables, notes, a
  count). When the server's Claude Code is not there (or fails), the
  server's `map` job stands in for it (the inventory the runner reads
  itself: containers, units, cron, ports, repositories, sites).
- When every job ended, the sections of all servers are merged, the
  catalogue is rendered as one deliverable of the holding's system employee
  (category `report`) and filed in the archive as a `report` record; the
  difference from the company's previous catalogue goes with it.
- The CEO starts it when an order asks to "go through / extract everything"
  (tool `company.catalogue`); the owner from the app; the watch every week.
Nothing of a row's contents, no secret: the brief forbids them and every
answer is masked again here.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import servers as SV
from hq_api.errors import ApiError
from hq_api.principal import Principal

log = logging.getLogger("hq_api.catalogue")
SERVICE = Principal(kind="service", code="catalogue", role="service")
JOB_TIMEOUT_S = 1800
STALE = timedelta(hours=6)  # a job still waiting then (a server off) ends as failed
CELL_CHARS = 300
ROWS_PER_TABLE = 200

SECTIONS: tuple[tuple[str, str, str], ...] = (
    (
        "products",
        "محصولات و سرویس‌ها",
        "every container (image, state, ports, compose project), every compose project, every systemd "
        "service and timer that is not the operating system's own, every long-running process, every "
        "listening port (and which process holds it), every domain and site (web server config, "
        "certificates' names), and in one line what each one does for the company",
    ),
    (
        "automations",
        "اتوماسیون‌ها و زمان‌بندی‌ها",
        "every n8n workflow (name, trigger, its nodes in order, schedule, active or not, last run and "
        "its result, recent errors; read them through n8n's own CLI or API or its database read-only), "
        "every cron entry of every user, every systemd timer, every queue worker or scheduled job "
        "(Celery beat, node-cron, ...), and what each one does",
    ),
    (
        "data",
        "داده‌ها",
        "every database (engine, version, size), its schemas and tables with row counts (counts only, "
        "never a row's contents), every queue, cache and bucket or storage folder, and how big each is",
    ),
    (
        "interfaces",
        "رابط‌ها",
        "every API (its routes as the code or the OpenAPI document defines them), every bot and its "
        "commands, every webhook (in and out), every integration with a third party (the service's name "
        "and what it is used for; never a key, a token or a password)",
    ),
    (
        "code",
        "کد و خروجی‌ها",
        "every repository on the server (path, remote, branch, last commit date and message), the "
        "outputs and reports the company's software produces (where, how often, the latest), and the "
        "logs: the recurring errors of the last 7 days with how often each appears",
    ),
    (
        "risks",
        "ریسک‌ها",
        "certificates that expire within 30 days, services that fail or restart, ports open to the "
        "internet that need not be, packages with known CVEs (from the package manager and the lock "
        "files), disks above 80%, backups that are missing or older than a day",
    ),
)
SECTION_FA = {k: fa for k, fa, _ in SECTIONS}

BRIEF = """You are cataloguing this server for the owner of the holding (contract §28.2). READ ONLY:
run only commands that read (ls, cat, ps, ss, docker ps/inspect/compose ls, systemctl list-*/status,
journalctl, crontab -l, git log/status/remote, psql/mysql with SELECT on catalogs and count(*), n8n
export to stdout); never change, restart, install, write or delete anything, never print a secret,
a key, a token, a password or a row's contents (counts only). Be exhaustive: list every item, do not
summarise or sample; when there are more than {rows} of one kind, list the {rows} that matter most
and give the total.

The section to catalogue: {title} — {what}.

Answer with ONE JSON object and nothing else:
{{"summary_md": "two or three Persian sentences on what this section shows",
  "count": <how many items in total>,
  "tables": [{{"title_fa": "...", "columns": ["...", "..."], "rows": [["...", "..."], ...]}}],
  "notes_md": "Persian: anything that did not fit a table, and what you could not read and why"}}
Column names and notes in Persian; names, paths, commands and versions as they are."""


# ------------------------------------------------------------------ shapes --
class CatalogueTable(BaseModel):
    title_fa: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)


class CatalogueSection(BaseModel):
    key: str
    title_fa: str
    summary_md: str | None = None
    tables: list[CatalogueTable] = Field(default_factory=list)
    notes_md: str | None = None
    count: int | None = None


class CatalogueServer(BaseModel):
    id: str
    name: str
    state: Literal["queued", "running", "done", "failed"]
    reason_fa: str | None = None


class Catalogue(BaseModel):
    company: str
    at: datetime
    state: Literal["running", "done", "failed"]
    record: str | None = None
    deliverable: str | None = None
    reason_fa: str | None = None
    servers: list[CatalogueServer] = Field(default_factory=list)
    sections: list[CatalogueSection] = Field(default_factory=list)
    diff: dict[str, Any] | None = None


CAT_SQL = """
    SELECT k.*, c.code AS company FROM infra.catalogues k JOIN core.companies c ON c.id = k.company_id
"""


def render(c: dict[str, Any]) -> Catalogue:
    servers: dict[str, dict[str, Any]] = {}
    for j in c["jobs"] or []:
        s = servers.setdefault(
            j["server"], {"id": j["server"], "name": j.get("server_name") or "", "jobs": []}
        )
        s["jobs"].append(j)
    out = []
    for s in servers.values():
        states = [j["state"] for j in s["jobs"]]
        if all(x == "queued" for x in states):
            st = "queued"
        elif any(x in ("queued", "running") for x in states):
            st = "running"
        elif any(x == "done" for x in states):
            st = "done"
        else:
            st = "failed"
        why = next((j.get("reason_fa") for j in s["jobs"] if j.get("reason_fa")), None)
        out.append(CatalogueServer(id=s["id"], name=s["name"], state=st, reason_fa=why))
    return Catalogue(
        company=c["company"],
        at=c["created_at"],
        state=c["state"],
        record=c["record_ref"],
        deliverable=c["deliverable_ref"],
        reason_fa=c["reason_fa"],
        servers=out,
        sections=[CatalogueSection.model_validate(x) for x in c["sections"] or []],
        diff=c["diff"],
    )


async def latest(tx: Tx, company_id: UUID) -> dict[str, Any] | None:
    return await tx.first(
        CAT_SQL + " WHERE k.company_id = :co ORDER BY k.created_at DESC LIMIT 1", co=company_id
    )


async def _paired(tx: Tx, company_id: UUID) -> list[dict[str, Any]]:
    return await tx.all(
        SV.SERVER_SQL
        + """ WHERE s.company_id = :co AND s.origin = 'attached'
                AND s.state IN ('online', 'offline') ORDER BY s.name""",
        co=company_id,
    )


# ------------------------------------------------------------------- start --
async def start(
    tx: Tx, hub: Any, company: Any, *, by_kind: str, by_code: str
) -> tuple[dict[str, Any], bool]:
    """(the catalogue, started now?). A run still going is answered as it is."""
    current = await latest(tx, company.id)
    if current is not None and current["state"] == "running":
        return current, False
    await SV.check_lock(tx, company.id, deploy=False)
    servers = await _paired(tx, company.id)
    jobs: list[dict[str, Any]] = []
    for s in servers:
        for key, title, what in SECTIONS:
            j = await SV.create_job(
                tx,
                server=s,
                kind="claude",
                args={
                    "brief": BRIEF.format(title=title, what=what, rows=ROWS_PER_TABLE),
                    "title": f"کاتالوگ {company.code}: {title}",
                    "timeout_s": JOB_TIMEOUT_S,
                    "max_turns": 60,
                },
                actor_kind="service",
                actor_code="catalogue",
                summary=f"کاتالوگ شرکت: {title}",
                timeout_s=JOB_TIMEOUT_S,
            )
            jobs.append(_job_entry(j, s, key))
    state = "running" if jobs else "failed"
    row = await tx.one(
        """INSERT INTO infra.catalogues (company_id, state, reason_fa, jobs, previous_id,
               started_by_kind, started_by_code, finished_at)
           VALUES (:co, :st, :why, CAST(:jobs AS jsonb), :prev, :bk, :bc,
                   CASE WHEN :st = 'failed' THEN now() END)
           RETURNING id""",
        co=company.id,
        st=state,
        why=None
        if jobs
        else "این شرکت هنوز سرور جفت‌شده‌ای ندارد؛ اول runner را روی سرورش نصب کنید.",
        jobs=json.dumps(jobs, ensure_ascii=False),
        prev=_done_id(current),
        bk=by_kind,
        bc=by_code[:64],
    )
    c = await tx.one(CAT_SQL + " WHERE k.id = :id", id=row["id"])
    await _emit(tx, c)
    return c, True


def _done_id(c: dict[str, Any] | None) -> UUID | None:
    if c is None:
        return None
    out: UUID | None = c["id"] if c["state"] == "done" else c["previous_id"]
    return out


def _job_entry(j: dict[str, Any], s: dict[str, Any], section: str) -> dict[str, Any]:
    return {
        "job": str(j["id"]),
        "server": str(s["id"]),
        "server_name": s["name"],
        "section": section,
        "kind": j["kind"],
        "state": "queued",
    }


async def _emit(tx: Tx, c: dict[str, Any]) -> None:
    await events.emit(
        tx,
        c["company"],
        "catalogue.updated",
        c["company"],
        {"state": c["state"], "record": c["record_ref"], "deliverable": c["deliverable_ref"]},
    )


# ---------------------------------------------------------- a job's answer --
def parse_section(key: str, text: str) -> dict[str, Any]:
    """One job's answer as a section: its JSON object (masked, capped), or
    the text itself as the summary when it is not one."""
    title = SECTION_FA.get(key, key)
    obj: Any = None
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
        except ValueError:
            obj = None
    if not isinstance(obj, dict):
        return {"key": key, "title_fa": title, "summary_md": SV.mask(text or "")[:4000],
                "tables": [], "notes_md": None, "count": None}  # fmt: skip
    tables = []
    for t in obj.get("tables") or []:
        if not isinstance(t, dict):
            continue
        cols = [SV.mask(str(c))[:80] for c in (t.get("columns") or [])][:20]
        rows = [
            [_cell(v) for v in r][:20] for r in (t.get("rows") or [])[:ROWS_PER_TABLE] if isinstance(r, list)
        ]  # fmt: skip
        tables.append({"title_fa": SV.mask(str(t.get("title_fa") or ""))[:200] or None,
                       "columns": cols, "rows": rows})  # fmt: skip
    count = obj.get("count")
    return {
        "key": key,
        "title_fa": title,
        "summary_md": SV.mask(str(obj.get("summary_md") or ""))[:4000] or None,
        "tables": tables[:20],
        "notes_md": SV.mask(str(obj.get("notes_md") or ""))[:4000] or None,
        "count": int(count) if isinstance(count, int | float) else None,
    }


def _cell(v: Any) -> Any:
    if isinstance(v, bool | int | float) or v is None:
        return v
    return SV.mask(str(v))[:CELL_CHARS]


def map_sections(m: dict[str, Any]) -> list[dict[str, Any]]:
    """The runner's own inventory (§26.5) as sections, when Claude Code could
    not catalogue the server."""
    m = m or {}

    def rows(key: str, cols: list[str]) -> list[list[Any]]:
        items = m.get(key) or []
        out = []
        for it in items[:ROWS_PER_TABLE]:
            if isinstance(it, dict):
                out.append([_cell(it.get(c)) for c in cols])
            else:
                out.append([_cell(it)] + [None] * (len(cols) - 1))
        return out

    def table(title: str, key: str, cols: list[str]) -> dict[str, Any] | None:
        r = rows(key, cols)
        return {"title_fa": title, "columns": cols, "rows": r} if r else None

    def section(key: str, *tables: dict[str, Any] | None) -> dict[str, Any]:
        ts = [t for t in tables if t]
        return {
            "key": key,
            "title_fa": SECTION_FA[key],
            "summary_md": "از نقشه‌ی خود runner (Claude Code روی این سرور در دسترس نبود).",
            "tables": ts,
            "notes_md": None,
            "count": sum(len(t["rows"]) for t in ts) or None,
        }

    return [
        section(
            "products",
            table("کانتینرها", "containers", ["name", "image", "state", "ports"]),
            table("پروژه‌های compose", "compose", ["name", "status", "config_files"]),
            table("سرویس‌های systemd", "units", ["name", "state", "description"]),
            table("پورت‌ها", "ports", ["port", "proto", "process"]),
            table("سایت‌ها", "sites", ["name", "root", "server"]),
        ),
        section(
            "automations",
            table("cron", "cron", ["user", "schedule", "command"]),
            table("timerها", "timers", ["name", "next", "unit"]),
            table("اتوماسیون‌ها", "automations", ["name", "kind", "state"]),
        ),
        section(
            "code", table("مخزن‌ها", "repositories", ["path", "remote", "branch", "last_commit"])
        ),
    ]


async def by_job(tx: Tx, job_id: UUID) -> dict[str, Any] | None:
    return await tx.first(
        CAT_SQL + " WHERE k.jobs @> CAST(:j AS jsonb) FOR UPDATE OF k",
        j=json.dumps([{"job": str(job_id)}]),
    )


async def on_job(tx: Tx, hub: Any, job_id: UUID) -> bool:
    """A job of a running catalogue ended: its entry, a map in place of a
    Claude Code that is not there, and the end of the run once every job
    ended. True when the catalogue is done now (the caller files it)."""
    c = await by_job(tx, job_id)
    if c is None or c["state"] != "running":
        return False
    j = await SV.load_job(tx, job_id)
    jobs = [dict(x) for x in c["jobs"]]
    sections = [dict(x) for x in c["sections"] or []]
    for e in jobs:
        if e["job"] != str(job_id) or e["state"] in SV.FINAL:
            continue
        e["state"] = j["state"] if j["state"] in SV.FINAL else "running"
        if j["state"] == "done" and e["kind"] == "claude":
            text = str((j["result"] or {}).get("result_fa") or "")
            sec = parse_section(e["section"], text)
            sec["server"] = e["server"]
            sec["server_name"] = e["server_name"]
            sections.append(sec)
        elif j["state"] == "done" and e["kind"] == "map":
            srv = await SV.load_server(tx, UUID(e["server"]))
            for sec in map_sections(srv["map"] or {}):
                sections.append({**sec, "server": e["server"], "server_name": e["server_name"]})
        elif j["state"] in ("failed", "cancelled"):
            e["reason_fa"] = _job_reason(j)
            if e["kind"] == "claude":  # the section says it was not read, and why
                sections.append({
                    "key": e["section"], "title_fa": SECTION_FA.get(e["section"], e["section"]),
                    "summary_md": None, "tables": [], "count": None,
                    "notes_md": f"این بخش روی این سرور خوانده نشد: {e['reason_fa']}",
                    "server": e["server"], "server_name": e["server_name"],
                })  # fmt: skip
            if e["kind"] == "claude" and not any(
                x["server"] == e["server"] and x["kind"] == "map" for x in jobs
            ):
                srv = await SV.load_server(tx, UUID(e["server"]))
                m = await SV.create_job(
                    tx, server=srv, kind="map", args={}, actor_kind="service",
                    actor_code="catalogue", summary="کاتالوگ: نقشه‌ی سرور به جای Claude Code",
                )  # fmt: skip
                jobs.append(_job_entry(m, srv, "*"))
    await tx.exec(
        """UPDATE infra.catalogues SET jobs = CAST(:jobs AS jsonb), sections = CAST(:s AS jsonb),
               updated_at = now() WHERE id = :id""",
        jobs=json.dumps(jobs, ensure_ascii=False),
        s=json.dumps(sections, ensure_ascii=False, default=str),
        id=c["id"],
    )
    if all(x["state"] in SV.FINAL for x in jobs):
        await finish(tx, hub, c["id"])
        return True
    await _emit(tx, await tx.one(CAT_SQL + " WHERE k.id = :id", id=c["id"]))
    return False


def _job_reason(j: dict[str, Any]) -> str:
    if j["state"] == "cancelled":
        return "کار لغو شد (کلید توقف یا مالک)."
    if j.get("exit_code") == 127:
        return "Claude Code روی این سرور نصب نیست؛ نقشه‌ی runner به جایش آمد."
    if j.get("error_code") == "timeout":
        return "کار به سقف زمانش رسید."
    return "کار روی سرور تمام نشد؛ نقشه‌ی runner به جایش آمد."


# ------------------------------------------------------------------ the end --
def merged(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The sections of every server, one per key in the fixed order; a table
    of one server keeps the server's name in its title."""
    servers = {s.get("server") for s in sections}
    out = []
    for key, title, _ in SECTIONS:
        parts = [s for s in sections if s["key"] == key]
        if not parts:
            continue
        tables = []
        summaries, notes = [], []
        count = 0
        counted = False
        for p in parts:
            tag = p.get("server_name") or ""
            for t in p["tables"]:
                name = t.get("title_fa") or title
                tables.append({**t, "title_fa": f"{tag} · {name}" if len(servers) > 1 else name})
            if p.get("summary_md"):
                summaries.append(
                    f"**{tag}:** {p['summary_md']}" if len(servers) > 1 else p["summary_md"]
                )
            if p.get("notes_md"):
                notes.append(f"**{tag}:** {p['notes_md']}" if len(servers) > 1 else p["notes_md"])
            if p.get("count") is not None:
                count += int(p["count"])
                counted = True
        out.append(
            {
                "key": key,
                "title_fa": title,
                "summary_md": "\n\n".join(summaries) or None,
                "tables": tables,
                "notes_md": "\n\n".join(notes) or None,
                "count": count if counted else None,
            }
        )
    return out


def markdown(company: str, sections: list[dict[str, Any]], diff: dict[str, Any] | None) -> str:
    lines = [f"# کاتالوگ کامل شرکت {company}", ""]
    if diff:
        lines += ["## تغییر نسبت به کاتالوگ قبلی", ""]
        for key, d in diff.items():
            add, gone = d.get("added") or [], d.get("removed") or []
            lines.append(
                f"- **{SECTION_FA.get(key, key)}:** {len(add)} مورد تازه، {len(gone)} مورد حذف‌شده"
                + (f" (تازه: {'، '.join(map(str, add[:10]))})" if add else "")
            )
        lines.append("")
    for s in sections:
        lines += [f"## {s['title_fa']}" + (f" ({s['count']})" if s.get("count") else ""), ""]
        if s.get("summary_md"):
            lines += [str(s["summary_md"]), ""]
        for t in s["tables"]:
            cols = t.get("columns") or []
            if t.get("title_fa"):
                lines += [f"### {t['title_fa']}", ""]
            if cols:
                lines.append("| " + " | ".join(cols) + " |")
                lines.append("|" + "---|" * len(cols))
            for r in t.get("rows") or []:
                cells = [
                    ("—" if v is None else str(v)).replace("|", "/").replace("\n", " ") for v in r
                ]
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
        if s.get("notes_md"):
            lines += [str(s["notes_md"]), ""]
    return "\n".join(lines)[:200_000]


def diff_of(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> dict[str, Any]:
    """Per section: the items (first column of every table) that appeared or
    went since the previous catalogue."""

    def items(sections: list[dict[str, Any]]) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for s in sections:
            bag = out.setdefault(s["key"], set())
            for t in s.get("tables") or []:
                for r in t.get("rows") or []:
                    if r and r[0] is not None:
                        bag.add(str(r[0]))
        return out

    a, b = items(old), items(new)
    out = {}
    for key in sorted(set(a) | set(b)):
        added = sorted(b.get(key, set()) - a.get(key, set()))
        removed = sorted(a.get(key, set()) - b.get(key, set()))
        if added or removed:
            out[key] = {"added": added[:100], "removed": removed[:100]}
    return out


async def finish(tx: Tx, hub: Any, catalogue_id: UUID) -> None:
    """Every job ended: the merged sections, the diff, the deliverable of the
    holding's system employee; the archive record is filed after commit."""
    from hq_api.domain import players
    from hq_api.domain import work as W

    c = await tx.one(CAT_SQL + " WHERE k.id = :id FOR UPDATE OF k", id=catalogue_id)
    sections = merged(c["sections"] or [])
    if not any(s["tables"] or s.get("summary_md") for s in sections):
        await tx.exec(
            """UPDATE infra.catalogues SET state = 'failed', reason_fa = :r, finished_at = now(),
                   updated_at = now() WHERE id = :id""",
            r="هیچ سروری جواب نداد؛ دلیل هر سرور کنارش آمده است.",
            id=c["id"],
        )
        await _emit(tx, await tx.one(CAT_SQL + " WHERE k.id = :id", id=c["id"]))
        return
    previous = (
        await tx.first("SELECT sections FROM infra.catalogues WHERE id = :p", p=c["previous_id"])
        if c["previous_id"]
        else None
    )
    diff = diff_of(previous["sections"], sections) if previous else None
    holding = await hub.companies.holding()
    sys_code = f"{holding.code}-SYS"
    w = await W.create(
        tx,
        SERVICE,
        company_id=holding.id,
        company_code=holding.code,
        title=f"کاتالوگ کامل شرکت {c['company']}",
        brief=f"The deep catalogue of {c['company']} (contract §28.2), produced by code from its servers.",
        kind="one_off",
        priority="P3",
        assignee_code=sys_code,
    )
    w = await W.load(tx, w["id"])
    dl = await players.deliver(
        tx,
        {**w, "company": holding.code},
        title=f"کاتالوگ کامل شرکت {c['company']}",
        body=markdown(c["company"], sections, diff),
        produced_with={
            "label_fa": "کاتالوگ از سرورهای شرکت (Claude Code و نقشه‌ی runner)",
            "source": "catalogue",
            "company": c["company"],
        },
    )
    await tx.exec(
        """UPDATE infra.catalogues SET state = 'done', sections = CAST(:s AS jsonb), diff = CAST(:d AS jsonb),
               deliverable_ref = :dl, work_id = :w, finished_at = now(), updated_at = now()
           WHERE id = :id""",
        s=json.dumps(sections, ensure_ascii=False, default=str),
        d=json.dumps(diff, ensure_ascii=False) if diff is not None else None,
        dl=dl["ref"],
        w=w["id"],
        id=c["id"],
    )
    if diff and c["started_by_code"] == "watch":
        await _diff_to_ceo(tx, c, dl["ref"], diff)
    await _emit(tx, await tx.one(CAT_SQL + " WHERE k.id = :id", id=c["id"]))


async def _diff_to_ceo(tx: Tx, c: dict[str, Any], ref: str, diff: dict[str, Any]) -> None:
    """The weekly refresh's difference goes to the company's CEO as work."""
    from hq_api.domain import work as W

    ceo = await tx.first(
        """SELECT code FROM core.employees WHERE company_id = :co AND kind = 'ceo' AND status = 'active'""",
        co=c["company_id"],
    )
    if ceo is None:
        return
    await W.create(
        tx,
        SERVICE,
        company_id=c["company_id"],
        company_code=c["company"],
        title=f"تغییرهای این هفته‌ی کاتالوگ {c['company']}",
        brief=(
            f"The weekly catalogue of your company changed ({ref}). Read what appeared and what went, "
            "decide what needs attention, and report to the owner in one short note; nothing else.\n\n"
            + json.dumps(diff, ensure_ascii=False)[:8000]
        ),
        kind="one_off",
        priority="P4",
        assignee_code=ceo["code"],
    )


async def file_done(hub: Any, catalogue_id: UUID) -> str | None:
    """After the commit: the catalogue's deliverable filed in the archive as a
    `report` record (idempotent), its ref kept on the catalogue."""
    from hq_api.archive import deliverables as AD
    from hq_api.routes.deliverables import DELIVERABLE_SQL

    ids = await hub.companies.ids()
    async with hub.db.tx(ids) as tx:
        c = await tx.first(CAT_SQL + " WHERE k.id = :id", id=catalogue_id)
        if c is None or c["state"] != "done" or not c["deliverable_ref"] or c["record_ref"]:
            return c["record_ref"] if c else None
        dl = await tx.one(DELIVERABLE_SQL + " WHERE dl.ref = :r", r=c["deliverable_ref"])
    try:
        record = await AD.file(hub, lambda: hub.db.tx(ids), SERVICE, dict(dl))
    except ApiError as exc:
        log.warning(
            "catalogue: not filed", extra={"catalogue": str(catalogue_id), "code": exc.code}
        )
        return None
    async with hub.db.tx(ids) as tx:
        await tx.exec(
            "UPDATE infra.catalogues SET record_ref = :r, updated_at = now() WHERE id = :id",
            r=record,
            id=catalogue_id,
        )
        c = await tx.one(CAT_SQL + " WHERE k.id = :id", id=catalogue_id)
        await _emit(tx, c)
    return str(record)


async def after_job(hub: Any, job_id: UUID) -> None:
    """The runner's result route, after its own commit: the catalogue that
    job belongs to, if any (never fails the runner's call)."""
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            c = await by_job(tx, job_id)
            if c is None:
                return
            done = await on_job(tx, hub, job_id)
        if done:
            await file_done(hub, c["id"])
    except Exception:
        log.exception("catalogue: a job's answer was not applied", extra={"job": str(job_id)})


async def sweep(tx: Tx, hub: Any, now: datetime | None = None) -> int:
    """A run whose jobs still wait after STALE (a server off): they are
    cancelled, so the catalogue ends with what came."""
    now = now or datetime.now(UTC)
    n = 0
    for c in await tx.all(
        CAT_SQL + " WHERE k.state = 'running' AND k.created_at < :t", t=now - STALE
    ):
        for e in c["jobs"]:
            if e["state"] in SV.FINAL:
                continue
            j = await SV.load_job(tx, UUID(e["job"]), lock=True)
            if j["state"] in SV.OPEN:
                await SV.cancel(
                    tx, j, "catalogue_timeout", "کاتالوگ بیش از ۶ ساعت منتظر این سرور ماند"
                )
            await on_job(tx, hub, UUID(e["job"]))
        n += 1
    return n
