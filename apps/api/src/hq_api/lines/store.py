"""Lines, their versions, runs and the library in the database (contract §30.1);
the shapes the routes answer. The engine (engine.py) runs; this module reads,
writes and renders. Nothing here knows any company: a line is data.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import recurrence
from hq_api.errors import ApiError
from hq_api.lines import templates as T
from hq_api.principal import Principal

ASSET_KINDS = ("cover_folder", "voice", "prompt", "pattern", "music", "brand")
OPEN_RUNS = ("queued", "running", "waiting")
ENDED_RUNS = ("done", "failed", "skipped", "cancelled")
BODY_KEYS = (
    "template", "template_version", "platform", "channel", "title_fa", "schedule", "caps",
    "auto_after", "steps", "library",
)  # fmt: skip


# ------------------------------------------------------------------ shapes --
class Channel(BaseModel):
    kind: str = Field(default="", max_length=40)
    subject: str = Field(default="", max_length=200)


class RunBrief(BaseModel):
    ref: str
    state: str
    at: datetime


class Line(BaseModel):
    ref: str
    company: str
    name_fa: str
    template: str
    template_version: int
    platform: str
    channel: Channel
    title_fa: str
    schedule: str | None
    state: Literal["draft", "on", "paused"]
    mode: Literal["draft", "auto"]
    good_runs: int
    auto_after: int
    # ⟨as built⟩ the app offers «خودکار کن»: a draft line with auto_after good runs
    offer_auto: bool
    caps: T.Caps
    version: int
    steps: list[T.StepDef]
    library: list[UUID]
    copied_from: str | None
    next_at: datetime | None
    last_run: RunBrief | None
    created_at: datetime
    updated_at: datetime


class By(BaseModel):
    kind: str
    code: str


class LineVersion(BaseModel):
    line: str
    version: int
    body: dict[str, Any]
    by: By
    at: datetime
    note_fa: str | None


class StepOutputOut(BaseModel):
    text: str | None = None
    file_id: str | None = None
    files: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class StepRun(BaseModel):
    key: str
    kind: str
    title_fa: str
    state: Literal["pending", "running", "waiting", "done", "failed", "skipped"]
    attempt: int
    started_at: datetime | None
    ended_at: datetime | None
    output: StepOutputOut
    via: str
    tokens: int
    usd_equiv: Decimal
    error_fa: str | None
    # ⟨as built⟩ the gate it waited at, its seal, a copy of an earlier run's
    # output (a rerun), the prompt's variables that rendered empty
    gate: Literal["owner", "ceo"] | None
    sealed_at: datetime | None
    sealed_by: str | None
    reused: bool
    missing: list[str]


class LineCost(BaseModel):
    tokens: int
    usd_equiv: Decimal


class Published(BaseModel):
    platform: str
    kind: str
    external_id: str | None
    at: datetime | None
    url: str | None


class Metrics(BaseModel):
    h24: dict[str, Any] | None = None
    d7: dict[str, Any] | None = None


class LineRunOut(BaseModel):
    ref: str
    line: str
    company: str
    title_fa: str
    platform: str
    line_version: int
    trigger: Literal["schedule", "owner", "test", "n8n", "group"]
    dry: bool
    state: Literal["queued", "running", "waiting", "done", "failed", "skipped", "cancelled"]
    at: datetime
    ended_at: datetime | None
    steps: list[StepRun]
    cost: LineCost
    published: list[Published]
    metrics: Metrics
    note_fa: str | None
    # ⟨as built⟩ the open card of its gated step, the run it reran, its first step
    decision: str | None
    rerun_of: str | None
    from_step: str | None


class InsightsBest(BaseModel):
    hour: int | None = None
    length_bucket: str | None = None
    voice: str | None = None
    pattern_source: str | None = None


class Insights(BaseModel):
    """§31.1 a line's published runs ranked by its template's metric (code only)."""

    line: str
    metric: str
    window_runs: int
    best: InsightsBest
    top_hooks: list[str]
    lessons_fa: list[str]
    updated_at: datetime | None


class Asset(BaseModel):
    id: UUID
    company: str | None  # null: the holding's, for every company
    kind: Literal["cover_folder", "voice", "prompt", "pattern", "music", "brand"]
    title_fa: str
    config: dict[str, Any]
    files: list[UUID]
    version: int
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------- lines --
LINE_SQL = """
    SELECT l.*, c.code AS company, coalesce(c.name_fa, c.code) AS name_fa, c.kind AS company_kind
    FROM lines.lines l JOIN core.companies c ON c.id = l.company_id
"""


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def body_of(row: dict[str, Any]) -> dict[str, Any]:
    """The line as a version keeps it (what a revert puts back)."""
    out = {k: row[k] for k in BODY_KEYS}
    out["library"] = [str(x) for x in row["library"] or []]
    return out


async def load(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        LINE_SQL + " WHERE l.ref = :ref" + (" FOR UPDATE OF l" if lock else ""), ref=ref
    )


async def by_id(tx: Tx, line_id: UUID) -> dict[str, Any]:
    return await tx.one(LINE_SQL + " WHERE l.id = :id", id=line_id)


async def of_company(tx: Tx, company_id: UUID) -> list[dict[str, Any]]:
    return await tx.all(LINE_SQL + " WHERE l.company_id = :co ORDER BY l.created_at", co=company_id)


def next_at(row: dict[str, Any], tz: str, now: datetime | None = None) -> datetime | None:
    if row["state"] != "on" or not row["schedule"]:
        return None
    try:
        return recurrence.next_at(recurrence.parse(row["schedule"]), tz, now or datetime.now(UTC))
    except ApiError:
        return None


async def render(tx: Tx, row: dict[str, Any], tz: str) -> Line:
    last = await tx.first(
        "SELECT ref, state, at FROM lines.runs WHERE line_id = :id ORDER BY at DESC, ref DESC LIMIT 1",
        id=row["id"],
    )
    return Line(
        ref=row["ref"],
        company=row["company"],
        name_fa=row["name_fa"],
        template=row["template"],
        template_version=row["template_version"],
        platform=row["platform"],
        channel=Channel.model_validate(row["channel"] or {}),
        title_fa=row["title_fa"],
        schedule=row["schedule"],
        state=row["state"],
        mode=row["mode"],
        good_runs=row["good_runs"],
        auto_after=row["auto_after"],
        offer_auto=row["mode"] == "draft" and row["good_runs"] >= row["auto_after"],
        caps=T.Caps.model_validate(row["caps"]),
        version=row["version"],
        steps=[T.StepDef.model_validate(s) for s in row["steps"]],
        library=list(row["library"] or []),
        copied_from=row["copied_from"],
        next_at=next_at(row, tz),
        last_run=RunBrief(**last) if last else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def write_version(tx: Tx, row: dict[str, Any], who: Principal, note_fa: str | None) -> None:
    await tx.exec(
        """INSERT INTO lines.line_versions (company_id, line_id, version, body, by_kind, by_code,
               note_fa)
           VALUES (:co, :line, :v, CAST(:body AS jsonb), :bk, :bc, :note)""",
        co=row["company_id"],
        line=row["id"],
        v=row["version"],
        body=dumps(body_of(row)),
        bk=who.kind,
        bc=who.code,
        note=(note_fa or None) and note_fa[:500],
    )


async def check_library(tx: Tx, company_id: UUID, ids: list[UUID]) -> None:
    """Every asset active and of this company or the holding."""
    if not ids:
        return
    n = await tx.scalar(
        """SELECT count(*) FROM lines.assets a JOIN core.companies c ON c.id = a.company_id
           WHERE a.id = ANY(CAST(:ids AS uuid[])) AND a.state = 'active'
             AND (a.company_id = :co OR c.kind = 'holding')""",
        ids=[str(i) for i in ids],
        co=company_id,
    )
    if int(n or 0) != len(set(ids)):
        raise ApiError(
            422, "validation_failed", fields={"library": "an asset of this company or the holding"}
        )


async def insert_line(
    tx: Tx,
    who: Principal,
    *,
    company_id: UUID,
    template: T.LineTemplate,
    platform: str,
    channel: dict[str, Any],
    title_fa: str,
    copied_from: str | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A `draft` line from a template (or from another line's body, a copy)."""
    src = body or {
        "template_version": template.version,
        "schedule": template.defaults.schedule,
        "caps": template.defaults.caps.model_dump(),
        "auto_after": template.defaults.auto_after,
        "steps": [s.model_dump() for s in template.steps],
        "library": [],
    }
    lid = await tx.scalar(
        """INSERT INTO lines.lines (company_id, template, template_version, platform, channel,
               title_fa, schedule, caps, auto_after, steps, library, copied_from)
           VALUES (:co, :tpl, :tv, :platform, CAST(:channel AS jsonb), :title, :schedule,
                   CAST(:caps AS jsonb), :auto_after, CAST(:steps AS jsonb),
                   CAST(:library AS uuid[]), :copied)
           RETURNING id""",
        co=company_id,
        tpl=template.key,
        tv=src["template_version"],
        platform=platform,
        channel=dumps(channel),
        title=title_fa,
        schedule=src["schedule"],
        caps=dumps(src["caps"]),
        auto_after=src["auto_after"],
        steps=dumps(src["steps"]),
        library=[str(x) for x in src["library"]],
        copied=copied_from,
    )
    row = await by_id(tx, lid)
    await write_version(
        tx, row, who, f"از روی {copied_from}" if copied_from else f"از قالب {template.key}"
    )
    return row


async def create_line(
    tx: Tx,
    *,
    company_id: UUID,
    template_key: str,
    platform: str,
    title_fa: str,
    channel: dict[str, Any] | None = None,
    by: str = "kit",
) -> dict[str, Any]:
    """A `draft` line from a template for one company (§30.5, §31.2 the company
    kit): the line row with its `ref`. `by` names who made it (a service's code,
    or "owner"); nothing runs until the owner turns the line on."""
    template = T.get(template_key)
    if not T.KEY.match(platform):
        raise ApiError(422, "validation_failed", fields={"platform": "a platform key"})
    title = (title_fa or "").strip()
    if not 1 <= len(title) <= 200:
        raise ApiError(422, "validation_failed", fields={"title_fa": "1 to 200 letters"})
    ch = Channel.model_validate(channel or {}).model_dump()
    who = (
        Principal(kind="owner", code="owner", role="owner")
        if by == "owner"
        else Principal(kind="service", code=by[:64] or "kit", role="service")
    )
    row = await insert_line(
        tx, who, company_id=company_id, template=template, platform=platform, channel=ch,
        title_fa=title,
    )  # fmt: skip
    await events.emit(
        tx, row["company"], "line.updated", row["ref"], {"state": "draft", "new": True}
    )
    return row


def caps_rise(old: dict[str, Any], new: dict[str, Any]) -> bool:
    return any(int(new.get(k, 0)) > int(old.get(k, 0)) for k in T.Caps.model_fields)


async def update(
    tx: Tx, who: Principal, row: dict[str, Any], change: dict[str, Any], note_fa: str | None
) -> dict[str, Any]:
    """A new version with `change` (keys of BODY_KEYS) applied; unchanged: none."""
    new = {**body_of(row), **change}
    if new == body_of(row):
        return row
    if "steps" in change:
        try:
            T.check_steps([T.StepDef.model_validate(s) for s in new["steps"]])
        except ValueError as exc:
            raise ApiError(422, "validation_failed", fields={"steps": str(exc)[:200]}) from exc
    T.check_schedule(new["schedule"])
    await check_library(tx, row["company_id"], [UUID(str(x)) for x in new["library"]])
    await tx.exec(
        """UPDATE lines.lines SET template_version = :tv, channel = CAST(:channel AS jsonb),
               title_fa = :title, schedule = :schedule, caps = CAST(:caps AS jsonb),
               auto_after = :auto_after, steps = CAST(:steps AS jsonb),
               library = CAST(:library AS uuid[]), version = version + 1, updated_at = now()
           WHERE id = :id""",
        id=row["id"],
        tv=new["template_version"],
        channel=dumps(new["channel"]),
        title=new["title_fa"],
        schedule=new["schedule"],
        caps=dumps(new["caps"]),
        auto_after=new["auto_after"],
        steps=dumps(new["steps"]),
        library=[str(x) for x in new["library"]],
    )
    out = await by_id(tx, row["id"])
    await write_version(tx, out, who, note_fa)
    return out


async def versions(tx: Tx, row: dict[str, Any]) -> list[LineVersion]:
    rows = await tx.all(
        """SELECT * FROM lines.line_versions WHERE line_id = :id ORDER BY version DESC""",
        id=row["id"],
    )
    return [
        LineVersion(
            line=row["ref"],
            version=r["version"],
            body=r["body"],
            by=By(kind=r["by_kind"], code=r["by_code"]),
            at=r["at"],
            note_fa=r["note_fa"],
        )
        for r in rows
    ]


async def version_body(tx: Tx, line_id: UUID, version: int) -> dict[str, Any]:
    r = await tx.one(
        "SELECT body FROM lines.line_versions WHERE line_id = :id AND version = :v",
        id=line_id,
        v=version,
    )
    body: dict[str, Any] = r["body"]
    return body


async def set_state(tx: Tx, row: dict[str, Any], state: str) -> dict[str, Any]:
    await tx.exec(
        "UPDATE lines.lines SET state = :s, updated_at = now() WHERE id = :id",
        s=state,
        id=row["id"],
    )
    return await by_id(tx, row["id"])


async def set_mode(tx: Tx, row: dict[str, Any], mode: str) -> dict[str, Any]:
    await tx.exec(
        "UPDATE lines.lines SET mode = :m, updated_at = now() WHERE id = :id", m=mode, id=row["id"]
    )
    return await by_id(tx, row["id"])


# -------------------------------------------------------------------- runs --
RUN_SQL = """
    SELECT r.*, l.ref AS line_ref, l.title_fa, l.platform, l.mode, l.caps AS line_caps,
           c.code AS company, d.ref AS decision_ref, p.ref AS rerun_ref
    FROM lines.runs r JOIN lines.lines l ON l.id = r.line_id
    JOIN core.companies c ON c.id = r.company_id
    LEFT JOIN cartable.decisions d ON d.id = r.decision_id
    LEFT JOIN lines.runs p ON p.id = r.rerun_of
"""


async def load_run(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        RUN_SQL + " WHERE r.ref = :ref" + (" FOR UPDATE OF r" if lock else ""), ref=ref
    )


async def step_rows(tx: Tx, run_id: UUID) -> list[dict[str, Any]]:
    return await tx.all("SELECT * FROM lines.step_runs WHERE run_id = :id ORDER BY pos", id=run_id)


def step_titles(body: dict[str, Any]) -> dict[str, str]:
    return {s["key"]: s.get("title_fa") or s["key"] for s in body.get("steps") or []}


def render_step(s: dict[str, Any], title_fa: str) -> StepRun:
    o = s["output"] or {}
    return StepRun(
        key=s["key"],
        kind=s["kind"],
        title_fa=title_fa,
        state=s["state"],
        attempt=s["attempt"],
        started_at=s["started_at"],
        ended_at=s["ended_at"],
        output=StepOutputOut(
            text=o.get("text"),
            file_id=o.get("file_id"),
            files=[str(f) for f in o.get("files") or []],
            data=o.get("data") or {},
        ),
        via=s["via"],
        tokens=int(s["tokens"]),
        usd_equiv=Decimal(s["usd_equiv"]),
        error_fa=s["error_fa"],
        gate=s["gate"],
        sealed_at=s["sealed_at"],
        sealed_by=s["sealed_by"],
        reused=s["reused"],
        missing=list(s["missing"] or []),
    )


async def render_run(tx: Tx, r: dict[str, Any]) -> LineRunOut:
    body = await version_body(tx, r["line_id"], r["line_version"])
    titles = step_titles(body)
    steps = [render_step(s, titles.get(s["key"], s["key"])) for s in await step_rows(tx, r["id"])]
    m = r["metrics"] or {}
    return LineRunOut(
        ref=r["ref"],
        line=r["line_ref"],
        company=r["company"],
        title_fa=r["title_fa"],
        platform=r["platform"],
        line_version=r["line_version"],
        trigger=r["trigger"],
        dry=r["dry"],
        state=r["state"],
        at=r["at"],
        ended_at=r["ended_at"],
        steps=steps,
        cost=LineCost(tokens=int(r["tokens"]), usd_equiv=Decimal(r["usd_equiv"])),
        published=[Published.model_validate(p) for p in r["published"] or []],
        metrics=Metrics(h24=m.get("h24"), d7=m.get("d7")),
        note_fa=r["note_fa"],
        decision=r["decision_ref"],
        rerun_of=r["rerun_ref"],
        from_step=r["from_step"],
    )


# ---------------------------------------------------------------- calendar --
async def calendar(
    tx: Tx, start: datetime, end: datetime, tz: str, company_id: UUID | None
) -> list[dict[str, Any]]:
    """Every `on` line's occurrences in [start, end) and the runs already made
    there (a run of the occurrence, or any run in the window)."""
    lines = await tx.all(
        LINE_SQL + " WHERE (CAST(:co AS uuid) IS NULL OR l.company_id = :co)", co=company_id
    )
    runs = await tx.all(
        """SELECT r.ref, r.state, r.at, r.occurrence_at, r.line_id FROM lines.runs r
           WHERE r.at >= :s AND r.at < :e AND (CAST(:co AS uuid) IS NULL OR r.company_id = :co)""",
        s=start - timedelta(hours=1),
        e=end,
        co=company_id,
    )
    by_occ = {(r["line_id"], r["occurrence_at"]): r for r in runs if r["occurrence_at"]}
    z = recurrence.zone(tz)
    days: dict[str, list[dict[str, Any]]] = {}
    for line in lines:
        occ: list[datetime] = []
        if line["state"] == "on" and line["schedule"]:
            try:
                occ = recurrence.occurrences(recurrence.parse(line["schedule"]), tz, start, end)
            except ApiError:
                occ = []
        for at in occ:
            run = by_occ.get((line["id"], at))
            days.setdefault(at.astimezone(z).date().isoformat(), []).append(
                {
                    "line": line["ref"],
                    "company": line["company"],
                    "platform": line["platform"],
                    "at": at,
                    "state": run["state"] if run else "planned",
                    "run": run["ref"] if run else None,
                }
            )
        for r in runs:  # runs off the schedule (the owner's, a test)
            if r["line_id"] == line["id"] and r["occurrence_at"] is None and r["at"] >= start:
                days.setdefault(r["at"].astimezone(z).date().isoformat(), []).append(
                    {
                        "line": line["ref"],
                        "company": line["company"],
                        "platform": line["platform"],
                        "at": r["at"],
                        "state": r["state"],
                        "run": r["ref"],
                    }
                )
    return [
        {"day": d, "items": sorted(items, key=lambda i: (i["at"], i["line"]))}
        for d, items in sorted(days.items())
    ]


# ----------------------------------------------------------------- library --
ASSET_SQL = """
    SELECT a.*, c.code AS company, c.kind AS company_kind
    FROM lines.assets a JOIN core.companies c ON c.id = a.company_id
"""


def render_asset(r: dict[str, Any]) -> Asset:
    return Asset(
        id=r["id"],
        company=None if r["company_kind"] == "holding" else r["company"],
        kind=r["kind"],
        title_fa=r["title_fa"],
        config=r["config"] or {},
        files=list(r["files"] or []),
        version=r["version"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


async def load_asset(tx: Tx, asset_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        ASSET_SQL
        + " WHERE a.id = :id AND a.state = 'active'"
        + (" FOR UPDATE OF a" if lock else ""),
        id=asset_id,
    )


async def assets_of(tx: Tx, ids: list[UUID] | list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    return await tx.all(
        ASSET_SQL
        + " WHERE a.id = ANY(CAST(:ids AS uuid[])) AND a.state = 'active' ORDER BY a.created_at",
        ids=[str(i) for i in ids],
    )


async def check_files(tx: Tx, ids: list[UUID]) -> None:
    if not ids:
        return
    n = await tx.scalar(
        "SELECT count(*) FROM files.files WHERE id = ANY(CAST(:ids AS uuid[])) AND variant = 'original'",
        ids=[str(i) for i in ids],
    )
    if int(n or 0) != len(set(ids)):
        raise ApiError(422, "validation_failed", fields={"files": "uploaded files (POST /files)"})
