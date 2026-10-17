"""The Code Workshop's control plane (contract §17.3, rules 1-7), in the
caller's transaction. Nothing here talks to a runtime (workshop.service does,
outside any transaction).

  workspaces  data (seed/workspaces.yaml, then the owner's PUT): a repository
              and its policy (branch prefix hq/, merge and deploy with the
              owner's seal)
  grants      the owner's permission (🔏, or the seal of a code_session
              decision): actions, driver, a USD cap per session, an expiry
  sessions    one Claude Code session under a grant; `area` is the part of
              the repository it writes ("" = all), `held` why it waits
  events      append-only, numbered per session: summaries and metadata,
              masked (rule 7); the full transcript goes to file storage
  approvals   push, PR and commands outside the allow-list wait for the owner

Enforced here: a session only under a live grant and by its driver; the
session's USD cap (rule 4); a kill switch or deploy freeze of the company
pauses its sessions and refuses new ones (5); one writing session per area
of a repository, the others wait (6); every change audited (7).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import yaml
from pydantic import BaseModel

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, actor
from hq_api.workshop.runtime import RuntimeEvent, SessionSpec
from hq_common.redact import redact, scrub

SEED_FILE = Path(__file__).resolve().parents[3] / "seed" / "workspaces.yaml"
ACTIONS = ("read", "edit", "run", "push_branch", "open_pr")
WRITE_ACTIONS = ("edit", "push_branch", "open_pr")
FINAL = ("done", "failed", "stopped")
ACTIVE = ("starting", "working", "waiting_approval", "idle")
# The only keys an event's data may carry: metadata, never content (rule 7).
DATA_KEYS: dict[str, tuple[str, ...]] = {
    "message": ("chars", "attachments"),
    "progress": ("step",),
    "command": ("cmd", "exit_code"),
    "file_change": ("path", "added", "removed"),
    "approval_request": ("approval_id", "action", "detail"),
    "approval_result": ("approval_id", "action", "allowed", "note"),
    "state": ("state", "held", "reason"),
    "error": ("code", "cmd"),
}
SYSTEM_ACTOR = ("system", "workshop")
DEFAULT_POLICY: dict[str, Any] = {
    "branch_prefix": "hq/",
    "may_open_pr": True,
    "merge": "owner_seal",
    "deploy": "owner_seal",
}
MAX_GRANT_DAYS = 90

# An audit sink: ctx.audit inside a request, direct_audit(who) elsewhere.
Audit = Callable[..., Awaitable[None]]


def direct_audit(who: Principal) -> Audit:
    async def rec(tx: Tx, **entry: Any) -> None:
        await audit.record(tx, who, **entry)

    return rec


# ------------------------------------------------------------------ models --
class Policy(BaseModel):
    branch_prefix: str
    may_open_pr: bool
    merge: Literal["owner_seal"]
    deploy: Literal["owner_seal"]


class Workspace(BaseModel):
    id: UUID
    code: str
    company: str
    repo: str
    default_branch: str
    title_fa: str
    policy: Policy
    status: Literal["active", "paused"]


class Grant(BaseModel):
    id: UUID
    ref: str
    workspace: str
    actions: list[str]
    driver: Actor | None
    budget_usd: float
    expires_at: datetime
    granted_by: Actor
    decision_ref: str | None
    revoked_at: datetime | None


class Usage(BaseModel):
    usd: float
    input_tokens: int
    output_tokens: int


class CodeSession(BaseModel):
    id: UUID
    ref: str
    workspace: str
    grant: str
    title: str
    brief: str
    opened_by: Actor
    driver: Actor
    runtime: str
    model: str
    effort: str
    state: Literal["starting", "working", "waiting_approval", "idle", "done", "failed", "stopped"]
    branch: str | None
    pr_url: str | None
    usage: Usage
    created_at: datetime
    updated_at: datetime
    # ⟨additive⟩ the repository area it writes ("" = all), why it waits, its transcript
    area: str = ""
    held: Literal["work_lock", "company_locked", "budget"] | None = None
    transcript_file: UUID | None = None


class SessionEvent(BaseModel):
    seq: int
    at: datetime
    type: Literal[
        "message", "progress", "command", "file_change", "approval_request",
        "approval_result", "state", "error",
    ]  # fmt: skip
    actor: Actor
    summary_fa: str
    data: dict[str, Any]


# ---------------------------------------------------------------- render --
WORKSPACE_SQL = """
    SELECT w.*, c.code AS company
    FROM workshop.workspaces w JOIN core.companies c ON c.id = w.company_id
"""
GRANT_SQL = """
    SELECT g.*, w.code AS workspace, d.ref AS decision_ref
    FROM workshop.grants g JOIN workshop.workspaces w ON w.id = g.workspace_id
    LEFT JOIN cartable.decisions d ON d.id = g.decision_id
"""
SESSION_SQL = """
    SELECT s.*, w.code AS workspace, w.repo, w.default_branch, w.policy, c.code AS company,
           g.ref AS grant_ref, g.actions, g.budget_usd
    FROM workshop.sessions s JOIN workshop.workspaces w ON w.id = s.workspace_id
    JOIN workshop.grants g ON g.id = s.grant_id JOIN core.companies c ON c.id = s.company_id
"""


def _actor(kind: str | None, code: str | None) -> Actor:
    a = actor(kind, code)
    assert a is not None
    return a


def policy_of(r: dict[str, Any]) -> dict[str, Any]:
    return {**DEFAULT_POLICY, **(r.get("policy") or {})}


def render_workspace(r: dict[str, Any]) -> Workspace:
    return Workspace(
        id=r["id"],
        code=r["code"],
        company=r["company"],
        repo=r["repo"],
        default_branch=r["default_branch"],
        title_fa=r["title_fa"],
        policy=Policy(**policy_of(r)),
        status=r["status"],
    )


def render_grant(r: dict[str, Any]) -> Grant:
    return Grant(
        id=r["id"],
        ref=r["ref"],
        workspace=r["workspace"],
        actions=list(r["actions"]),
        driver=actor(r["driver_kind"], r["driver_code"]),
        budget_usd=float(r["budget_usd"]),
        expires_at=r["expires_at"],
        granted_by=_actor(r["granted_by_kind"], r["granted_by_code"]),
        decision_ref=r["decision_ref"],
        revoked_at=r["revoked_at"],
    )


def render_session(r: dict[str, Any]) -> CodeSession:
    return CodeSession(
        id=r["id"],
        ref=r["ref"],
        workspace=r["workspace"],
        grant=r["grant_ref"],
        title=r["title"],
        brief=r["brief"],
        opened_by=_actor(r["opened_by_kind"], r["opened_by_code"]),
        driver=_actor(r["driver_kind"], r["driver_code"]),
        runtime=r["runtime"],
        model=r["model"],
        effort=r["effort"],
        state=r["state"],
        branch=r["branch"],
        pr_url=r["pr_url"],
        usage=Usage(
            usd=float(r["usd"]),
            input_tokens=int(r["input_tokens"]),
            output_tokens=int(r["output_tokens"]),
        ),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        area=r["area"],
        held=r["held"],
        transcript_file=r["transcript_file_id"],
    )


def render_event(r: dict[str, Any]) -> SessionEvent:
    return SessionEvent(
        seq=r["seq"],
        at=r["at"],
        type=r["type"],
        actor=_actor(r["actor_kind"], r["actor_code"]),
        summary_fa=r["summary_fa"],
        data=r["data"],
    )


def spec(r: dict[str, Any]) -> SessionSpec:
    policy = policy_of(r)
    return SessionSpec(
        ref=r["ref"],
        workspace=r["workspace"],
        repo=r["repo"],
        default_branch=r["default_branch"],
        branch=f"{policy['branch_prefix']}{r['ref']}",
        title=r["title"],
        brief=r["brief"],
        model=r["model"],
        effort=r["effort"],
        budget_usd=Decimal(r["budget_usd"]),
        actions=list(r["actions"]),
        branch_prefix=policy["branch_prefix"],
        external_id=r["external_id"],
        cursor=r["external_cursor"],
    )


# ------------------------------------------------------------- workspaces --
def load_seed() -> list[dict[str, Any]]:
    data = yaml.safe_load(SEED_FILE.read_text(encoding="utf-8")) or {}
    return list(data.get("workspaces") or [])


async def seed(tx: Tx) -> int:
    """Adds the seed's workspaces that are missing; never overwrites an edit.
    A workspace of a company this hub does not have is skipped."""
    added = 0
    for w in load_seed():
        co = await tx.scalar("SELECT id FROM core.companies WHERE code = :c", c=w["company"])
        if co is None:
            continue
        added += await tx.exec(
            """INSERT INTO workshop.workspaces (company_id, code, repo, default_branch, title_fa, policy)
               VALUES (:co, :code, :repo, :branch, :title, CAST(:policy AS jsonb))
               ON CONFLICT (code) DO NOTHING""",
            co=co,
            code=w["code"],
            repo=w["repo"],
            branch=w.get("default_branch", "main"),
            title=w["title_fa"],
            policy=json.dumps({**DEFAULT_POLICY, **(w.get("policy") or {})}),
        )
    return added


async def workspace(tx: Tx, code: str) -> dict[str, Any]:
    return await tx.one(WORKSPACE_SQL + " WHERE w.code = :c", c=code, not_found="not_found")


async def put_workspaces(
    tx: Tx, rec: Audit, items: list[dict[str, Any]], company_ids: dict[str, UUID]
) -> list[dict[str, Any]]:
    """The owner's list replaces the current one: listed workspaces are added
    or updated; one left out is paused (never deleted: its sessions and
    grants stay on record). A workspace keeps its company."""
    for i in items:
        co = company_ids.get(i["company"])
        if co is None:
            raise ApiError(422, "validation_failed", fields={"company": f"unknown {i['company']}"})
        cur = await tx.first(
            "SELECT id, company_id FROM workshop.workspaces WHERE code = :c FOR UPDATE", c=i["code"]
        )
        args = {
            "repo": i["repo"],
            "branch": i["default_branch"],
            "title": i["title_fa"],
            "policy": json.dumps({**DEFAULT_POLICY, **(i.get("policy") or {})}),
            "status": i["status"],
        }
        if cur is None:
            await tx.exec(
                """INSERT INTO workshop.workspaces (company_id, code, repo, default_branch, title_fa,
                       policy, status)
                   VALUES (:co, :code, :repo, :branch, :title, CAST(:policy AS jsonb), :status)""",
                co=co,
                code=i["code"],
                **args,
            )
            change = "added"
        else:
            if cur["company_id"] != co:
                raise ApiError(
                    422, "validation_failed", fields={"company": f"{i['code']} keeps its company"}
                )
            n = await tx.exec(
                """UPDATE workshop.workspaces SET repo = :repo, default_branch = :branch,
                       title_fa = :title, policy = CAST(:policy AS jsonb), status = :status,
                       updated_at = now()
                   WHERE id = :id AND (repo, default_branch, title_fa, policy, status)
                         IS DISTINCT FROM (:repo, :branch, :title, CAST(:policy AS jsonb), :status)""",
                id=cur["id"],
                **args,
            )
            if not n:
                continue
            change = "updated"
        await rec(
            tx,
            company_id=co,
            action="workshop.workspaces",
            action_class="A2",
            target_kind="workspace",
            target_ref=i["code"],
            summary=f"{change}: {i['repo']}@{i['default_branch']} {i['status']}",
            step_up=True,
        )
    for gone in await tx.all(
        """SELECT id, code, company_id FROM workshop.workspaces
           WHERE status = 'active' AND NOT code = ANY(:listed) FOR UPDATE""",
        listed=sorted(i["code"] for i in items),
    ):
        await tx.exec(
            "UPDATE workshop.workspaces SET status = 'paused', updated_at = now() WHERE id = :id",
            id=gone["id"],
        )
        await rec(
            tx,
            company_id=gone["company_id"],
            action="workshop.workspaces",
            action_class="A2",
            target_kind="workspace",
            target_ref=gone["code"],
            summary="left out of the list: paused",
            step_up=True,
        )
    return await tx.all(WORKSPACE_SQL + " ORDER BY c.code, w.code")


# ----------------------------------------------------------------- grants --
async def create_grant(
    tx: Tx,
    who: Principal,
    rec: Audit,
    *,
    workspace_code: str,
    actions: list[str],
    driver_code: str | None,
    budget_usd: Decimal,
    expires_at: datetime,
    decision_id: UUID | None = None,
    sealed: bool = True,
) -> dict[str, Any]:
    """Only the owner grants: directly (🔏), or by sealing a code_session
    decision, whose effect calls this with the owner as `who`."""
    if not who.is_owner:
        raise ApiError(403, "forbidden", "only the owner grants the workshop")
    ws = await workspace(tx, workspace_code)
    if ws["status"] != "active":
        raise ApiError(409, "validation_failed", fields={"workspace": "paused"})
    if not actions or set(actions) - set(ACTIONS):
        raise ApiError(
            422, "validation_failed", fields={"actions": f"some of {', '.join(ACTIONS)}"}
        )
    if "open_pr" in actions and not policy_of(ws)["may_open_pr"]:
        raise ApiError(422, "validation_failed", fields={"actions": "this workspace opens no PR"})
    now = datetime.now(UTC)
    if expires_at <= now or expires_at > now + timedelta(days=MAX_GRANT_DAYS, minutes=5):
        raise ApiError(
            422,
            "validation_failed",
            fields={"expires_at": f"in the future, at most {MAX_GRANT_DAYS} days"},
        )
    if driver_code and not await tx.scalar(
        """SELECT 1 FROM core.employees
           WHERE code = :c AND company_id = :co AND status = 'active' AND kind <> 'system'""",
        c=driver_code,
        co=ws["company_id"],
    ):
        raise ApiError(
            422,
            "validation_failed",
            fields={"driver": "an active employee of the workspace's company"},
        )
    row = await tx.one(
        """INSERT INTO workshop.grants (company_id, workspace_id, actions, driver_kind, driver_code,
               budget_usd, expires_at, granted_by_kind, granted_by_code, decision_id)
           VALUES (:co, :ws, :actions, :dk, :dc, :usd, :exp, 'owner', 'owner', :dec)
           RETURNING id""",
        co=ws["company_id"],
        ws=ws["id"],
        actions=sorted(set(actions), key=ACTIONS.index),
        dk="agent" if driver_code else None,
        dc=driver_code,
        usd=budget_usd,
        exp=expires_at,
        dec=decision_id,
    )
    g = await tx.one(GRANT_SQL + " WHERE g.id = :id", id=row["id"])
    await rec(
        tx,
        company_id=ws["company_id"],
        action="workshop.grant",
        action_class="A2",
        target_kind="grant",
        target_ref=g["ref"],
        summary=f"{workspace_code}: {','.join(g['actions'])}; ${budget_usd}/session; "
        f"driver {driver_code or 'owner'}" + (f"; by {g['decision_ref']}" if decision_id else ""),
        step_up=sealed,
    )
    return g


async def revoke_grant(
    tx: Tx, who: Principal, rec: Audit, ref: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Immediate; its running sessions stop (returned for the runtime)."""
    g = await tx.one(GRANT_SQL + " WHERE g.ref = :r FOR UPDATE OF g", r=ref, not_found="not_found")
    if g["revoked_at"] is None:
        await tx.exec(
            """UPDATE workshop.grants SET revoked_at = now(), revoked_by_kind = :k,
                   revoked_by_code = :c
               WHERE id = :id""",
            id=g["id"],
            k="owner" if who.is_owner else "service",
            c=who.code,
        )
        await rec(
            tx,
            company_id=g["company_id"],
            action="workshop.revoke",
            action_class="A1",
            target_kind="grant",
            target_ref=ref,
            summary="revoked; its running sessions stop",
        )
    running = await tx.all(
        SESSION_SQL + " WHERE s.grant_id = :g AND s.state <> ALL(:final) ORDER BY s.created_at",
        g=g["id"],
        final=list(FINAL),
    )
    stopped = [
        await finish(tx, s, "stopped", "grant_revoked", "مجوز لغو شد؛ سشن متوقف شد")
        for s in running
    ]
    return await tx.one(GRANT_SQL + " WHERE g.id = :id", id=g["id"]), stopped


def grant_alive(g: dict[str, Any]) -> bool:
    expires: datetime = g["expires_at"]
    return g["revoked_at"] is None and expires > datetime.now(UTC)


# --------------------------------------------------------------- sessions --
def overlaps(a: str, b: str) -> bool:
    """Two areas of a repository overlap when one contains the other ("" = all)."""
    a, b = a.strip("/"), b.strip("/")
    return a == "" or b == "" or a == b or a.startswith(b + "/") or b.startswith(a + "/")


async def lock_holder(
    tx: Tx, ws_id: UUID, area: str, exclude: UUID | None = None
) -> dict[str, Any] | None:
    """The writing session already holding an overlapping area (rule 6)."""
    rows = await tx.all(
        """SELECT id, ref, area FROM workshop.sessions
           WHERE workspace_id = :ws AND writes AND state = ANY(:active)
             AND held IS DISTINCT FROM 'work_lock' AND id IS DISTINCT FROM CAST(:ex AS uuid)
           ORDER BY created_at""",
        ws=ws_id,
        active=list(ACTIVE),
        ex=exclude,
    )
    return next((r for r in rows if overlaps(r["area"], area)), None)


async def open_session(
    tx: Tx,
    who: Principal,
    rec: Audit,
    *,
    grant_ref: str,
    title: str,
    brief: str,
    area: str,
    model: str,
    effort: str,
    runtime: str,
) -> dict[str, Any]:
    """The session record (state starting); held = work_lock when another
    writing session holds its area. The caller starts it on the runtime."""
    g = await tx.one(
        GRANT_SQL + " WHERE g.ref = :r FOR SHARE OF g", r=grant_ref, not_found="not_found"
    )
    if not grant_alive(g):
        raise ApiError(409, "validation_failed", fields={"grant": "revoked or expired"})
    if who.is_agent:
        if g["driver_kind"] != "agent" or g["driver_code"] != who.code:
            raise ApiError(403, "policy_denied", "only the grant's driver opens a session under it")
    elif not who.is_owner:
        raise ApiError(403, "forbidden")
    ws = await tx.one(WORKSPACE_SQL + " WHERE w.id = :id", id=g["workspace_id"])
    if ws["status"] != "active":
        raise ApiError(409, "validation_failed", fields={"workspace": "paused"})
    if await tx.scalar("SELECT control.lock_state(:co)", co=ws["company_id"]) is not None:
        raise ApiError(423, "company_locked", "a kill switch or a deploy freeze holds this company")
    writes = bool(set(g["actions"]) & set(WRITE_ACTIONS))
    # One writer per area of a repository (OPERATING_MODEL §1.5), serialised per workspace.
    await tx.exec("SELECT pg_advisory_xact_lock(hashtext(:k))", k=f"workshop:{ws['id']}")
    holder = await lock_holder(tx, ws["id"], area) if writes else None
    driver = (g["driver_kind"], g["driver_code"]) if g["driver_kind"] else ("owner", "owner")
    row = await tx.one(
        """INSERT INTO workshop.sessions (company_id, workspace_id, grant_id, title, brief, area,
               writes, opened_by_kind, opened_by_code, driver_kind, driver_code, runtime, model,
               effort, held)
           VALUES (:co, :ws, :g, :title, :brief, :area, :writes, :ok, :oc, :dk, :dc, :rt, :model,
                   :effort, :held)
           RETURNING id""",
        co=ws["company_id"],
        ws=ws["id"],
        g=g["id"],
        title=scrub(title),
        brief=scrub(brief),
        area=area.strip("/"),
        writes=writes,
        ok=who.kind,
        oc=who.code,
        dk=driver[0],
        dc=driver[1],
        rt=runtime,
        model=model,
        effort=effort,
        held="work_lock" if holder else None,
    )
    s = await load(tx, row["id"])
    await append(
        tx,
        s,
        "state",
        f"در صف: {holder['ref']} همین بخش ریپو را مینویسد" if holder else "سشن ساخته شد",
        {"state": "starting", "held": "work_lock" if holder else None},
        actor=(who.kind, who.code),
    )
    await rec(
        tx,
        company_id=ws["company_id"],
        action="workshop.session",
        action_class="A1",
        target_kind="code_session",
        target_ref=s["ref"],
        summary=f"{ws['code']} under {grant_ref}"
        + (f"; waits for {holder['ref']}" if holder else ""),
    )
    s = await load(tx, row["id"])
    await emit_state(tx, s)
    return s


async def load(tx: Tx, session_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        SESSION_SQL + " WHERE s.id = :id" + (" FOR UPDATE OF s" if lock else ""), id=session_id
    )


async def by_ref(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        SESSION_SQL + " WHERE s.ref = :r" + (" FOR UPDATE OF s" if lock else ""),
        r=ref,
        not_found="not_found",
    )


async def emit_state(tx: Tx, s: dict[str, Any]) -> None:
    await events.emit(
        tx,
        s["company"],
        "workshop.session",
        s["ref"],
        {"state": s["state"], "workspace": s["workspace"], "held": s["held"]},
    )


def clean(type_: str, data: dict[str, Any]) -> dict[str, Any]:
    """Only the metadata keys of the type, masked and cut (rule 7)."""
    keep = {k: v for k, v in data.items() if k in DATA_KEYS.get(type_, ()) and v is not None}
    out: dict[str, Any] = redact(keep, max_string=500)
    return out


async def append(
    tx: Tx,
    s: dict[str, Any],
    type_: str,
    summary: str,
    data: dict[str, Any] | None = None,
    *,
    actor: tuple[str, str] = SYSTEM_ACTOR,
) -> int:
    """One event with the next seq (the seq update locks the session row)."""
    seq: int = await tx.scalar(
        "UPDATE workshop.sessions SET last_seq = last_seq + 1 WHERE id = :id RETURNING last_seq",
        id=s["id"],
    )
    await tx.exec(
        """INSERT INTO workshop.events (session_id, company_id, seq, type, actor_kind, actor_code,
               summary_fa, data)
           VALUES (:s, :co, :seq, :t, :ak, :ac, :sum, CAST(:data AS jsonb))""",
        s=s["id"],
        co=s["company_id"],
        seq=seq,
        t=type_,
        ak=actor[0],
        ac=actor[1][:64],
        sum=scrub(summary)[:2000],
        data=json.dumps(clean(type_, data or {}), ensure_ascii=False),
    )
    return seq


async def ingest(tx: Tx, session_id: UUID, items: list[RuntimeEvent]) -> dict[str, Any]:
    """What the runtime reported, applied: events, state, usage, approvals and
    the budget (rule 4). Returns {"session", "interrupt", "finished"}; on
    `interrupt` the caller stops the session on its runtime."""
    s = await load(tx, session_id, lock=True)
    if s["state"] in FINAL:
        return {"session": s, "interrupt": False, "finished": False}
    paused = s["held"] in ("company_locked", "budget")
    for ev in items:
        sets: dict[str, Any] = {}
        if ev.usd is not None and Decimal(ev.usd) > Decimal(s["usd"]):
            sets["usd"] = Decimal(ev.usd)
        if ev.tokens:
            sets["input_tokens"] = int(s["input_tokens"]) + ev.tokens[0]
            sets["output_tokens"] = int(s["output_tokens"]) + ev.tokens[1]
        if ev.branch:
            sets["branch"] = ev.branch
        if ev.pr_url:
            sets["pr_url"] = ev.pr_url
        if ev.state and ev.state not in FINAL and not paused:
            sets["state"] = ev.state
        if sets:
            cols = ", ".join(f"{k} = :{k}" for k in sets)
            await tx.exec(
                f"UPDATE workshop.sessions SET {cols} WHERE id = :id",  # noqa: S608 - fixed keys
                id=s["id"],
                **sets,
            )
        if ev.type:
            data = dict(ev.data)
            if ev.approval is not None:
                ap = await tx.one(
                    """INSERT INTO workshop.approvals (session_id, company_id, action, detail,
                           external_id)
                       VALUES (:s, :co, :a, :d, :x) RETURNING ref""",
                    s=s["id"],
                    co=s["company_id"],
                    a=ev.approval.action,
                    d=scrub(ev.approval.detail)[:2000],
                    x=ev.approval.external_id,
                )
                data["approval_id"] = ap["ref"]
                await events.emit(
                    tx,
                    s["company"],
                    "workshop.approval",
                    s["ref"],
                    {
                        "approval_id": ap["ref"],
                        "action": ev.approval.action,
                        "workspace": s["workspace"],
                    },
                )
            await append(tx, s, ev.type, ev.summary_fa, data, actor=ev.actor)
        s = await load(tx, s["id"])
        if "state" in sets:
            await emit_state(tx, s)
        if ev.state in FINAL:
            code = None if ev.state == "done" else "runtime_error"
            s = await finish(tx, s, str(ev.state), code, ev.summary_fa or str(ev.state))
            return {"session": s, "interrupt": False, "finished": True}
        if ev.held == "budget" or Decimal(s["usd"]) >= Decimal(s["budget_usd"]):
            return {"session": await budget_stop(tx, s), "interrupt": True, "finished": True}
    return {"session": s, "interrupt": paused, "finished": False}


async def budget_stop(tx: Tx, s: dict[str, Any]) -> dict[str, Any]:
    """Rule 4: at its cap the session stops and the owner is asked."""
    from hq_api.domain import notify

    await tx.exec("UPDATE workshop.sessions SET held = 'budget' WHERE id = :id", id=s["id"])
    s = await finish(
        tx,
        await load(tx, s["id"]),
        "stopped",
        "budget_reached",
        f"سقف بودجه‌ی سشن رسید (${float(s['usd']):.2f} از ${float(s['budget_usd']):.2f})؛"
        " سشن متوقف شد",
    )
    await notify.raise_notification(
        tx,
        company_id=s["company_id"],
        company_code=s["company"],
        level="decision",
        title_fa=f"سشن {s['ref']} به سقف بودجه رسید",
        body_fa=f"${float(s['usd']):.2f} از ${float(s['budget_usd']):.2f}؛ برای ادامه، سشن تازه"
        " زیر همین مجوز یا مجوز تازه با سقف بیشتر.",
        link_kind="code_session",
        link_ref=s["ref"],
    )
    return s


async def finish(
    tx: Tx, s: dict[str, Any], state: str, code: str | None, summary: str
) -> dict[str, Any]:
    if s["state"] in FINAL:
        return s
    await tx.exec(
        """UPDATE workshop.sessions SET state = :st, error_code = :code, finished_at = now()
           WHERE id = :id""",
        id=s["id"],
        st=state,
        code=code,
    )
    failed = code is not None
    await append(
        tx,
        s,
        "error" if failed else "state",
        summary,
        {"code": code} if failed else {"state": state},
    )
    s = await load(tx, s["id"])
    await emit_state(tx, s)
    return s


async def next_in_line(tx: Tx, ws_id: UUID) -> list[dict[str, Any]]:
    """Waiting sessions whose area is free now (rule 6), oldest first, released."""
    await tx.exec("SELECT pg_advisory_xact_lock(hashtext(:k))", k=f"workshop:{ws_id}")
    waiting = await tx.all(
        SESSION_SQL
        + " WHERE s.workspace_id = :ws AND s.held = 'work_lock' AND s.state = 'starting'"
        " ORDER BY s.created_at",
        ws=ws_id,
    )
    released = []
    for w in waiting:
        if await lock_holder(tx, ws_id, w["area"], exclude=w["id"]) is None:
            await tx.exec("UPDATE workshop.sessions SET held = NULL WHERE id = :id", id=w["id"])
            s = await load(tx, w["id"])
            await append(tx, s, "state", "نوبت این سشن رسید", {"state": "starting"})
            await emit_state(tx, s)
            released.append(s)
    return released


async def pause_locked(tx: Tx) -> list[dict[str, Any]]:
    """Rule 5: the sessions of a company under a kill switch or a deploy
    freeze pause (held company_locked). Called where either is engaged."""
    rows = await tx.all(
        SESSION_SQL
        + """ WHERE s.state = ANY(:active) AND s.held IS NULL
              AND control.lock_state(s.company_id) IS NOT NULL
              ORDER BY s.created_at""",
        active=list(ACTIVE),
    )
    paused = []
    for r in rows:
        await tx.exec(
            "UPDATE workshop.sessions SET held = 'company_locked', state = 'idle' WHERE id = :id",
            id=r["id"],
        )
        s = await load(tx, r["id"])
        await append(
            tx,
            s,
            "state",
            "کلید توقف یا توقف deploy شرکت: سشن متوقف ماند",
            {"state": "idle", "held": "company_locked"},
        )
        await emit_state(tx, s)
        paused.append(s)
    return paused


async def unhold_if_free(tx: Tx, s: dict[str, Any]) -> dict[str, Any]:
    """A session paused by a lock goes on once the lock is lifted (423 before)."""
    if s["held"] != "company_locked":
        return s
    if await tx.scalar("SELECT control.lock_state(:co)", co=s["company_id"]) is not None:
        raise ApiError(423, "company_locked", "a kill switch or a deploy freeze holds this company")
    await tx.exec("UPDATE workshop.sessions SET held = NULL WHERE id = :id", id=s["id"])
    s = await load(tx, s["id"])
    await append(tx, s, "state", "قفل شرکت برداشته شد؛ سشن ادامه میدهد", {"state": s["state"]})
    await emit_state(tx, s)
    return s


async def answer_approval(
    tx: Tx,
    who: Principal,
    rec: Audit,
    s: dict[str, Any],
    ref: str,
    allow: bool,
    note: str | None,
    step_up_id: UUID | None,
) -> dict[str, Any]:
    ap = await tx.one(
        "SELECT * FROM workshop.approvals WHERE ref = :r AND session_id = :s FOR UPDATE",
        r=ref,
        s=s["id"],
        not_found="not_found",
    )
    if ap["state"] != "pending":
        raise ApiError(409, "decision_not_pending", f"{ref} is {ap['state']}")
    await tx.exec(
        """UPDATE workshop.approvals SET state = :st, decided_at = now(), decided_by_kind = 'owner',
               decided_by_code = :c, note = :n, step_up_id = :su
           WHERE id = :id""",
        id=ap["id"],
        st="allowed" if allow else "denied",
        c=who.code,
        n=note,
        su=step_up_id,
    )
    await append(
        tx,
        s,
        "approval_result",
        ("اجازه داده شد: " if allow else "رد شد: ") + ap["action"],
        {"approval_id": ref, "action": ap["action"], "allowed": allow, "note": note},
        actor=(who.kind, who.code),
    )
    pending = await tx.scalar(
        "SELECT count(*) FROM workshop.approvals WHERE session_id = :s AND state = 'pending'",
        s=s["id"],
    )
    if not pending and s["state"] == "waiting_approval":
        await tx.exec("UPDATE workshop.sessions SET state = 'working' WHERE id = :id", id=s["id"])
        await emit_state(tx, await load(tx, s["id"]))
    await rec(
        tx,
        company_id=s["company_id"],
        action="workshop.approval",
        action_class="A2" if allow else "A1",
        target_kind="approval",
        target_ref=f"{s['ref']}/{ref}",
        summary=f"{ap['action']}: {'allowed' if allow else 'denied'}",
        step_up=step_up_id is not None,
    )
    return dict(ap)


async def store_transcript(tx: Tx, storage: Any, s: dict[str, Any], data: bytes) -> UUID | None:
    """Rule 7: the full (masked) transcript in file storage, owner-readable."""
    if not data or s["transcript_file_id"]:
        return None
    key, sha = await storage.put(data)
    fid: UUID = await tx.scalar(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key,
               created_by_kind, created_by_code)
           VALUES (:co, :name, 'application/x-ndjson', :size, :sha, :key, 'service', 'workshop')
           RETURNING id""",
        co=s["company_id"],
        name=f"{s['ref']}-transcript.jsonl",
        size=len(data),
        sha=sha,
        key=key,
    )
    await tx.exec(
        "UPDATE workshop.sessions SET transcript_file_id = :f WHERE id = :id", f=fid, id=s["id"]
    )
    return fid
