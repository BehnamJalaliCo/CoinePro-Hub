"""⟨1.8⟩ Code Workshop sessions that run on a company's own server (contract
§26.2 `server.claude`, §26.5 `runtime: "company_server"`), in the caller's
transaction.

The session is the Workshop's own record (its events, its stop, the owner's
messages) and each turn is a `claude` job on the server's runner: the runner
starts the server's own Claude Code (`claude -p … --output-format
stream-json`) in the repository folder `cwd`, under that repository's
CLAUDE.md, and streams its events back as SessionEvents. An owner message
resumes it (`--resume` with the Claude session id the runner reported) as
the next job. A session has no workspace or grant: the server is its place,
the owner's order (or an agent's server.claude) its permission, and every
destructive command inside it still waits for the seal (§26.3).

The session is `starting` while its job is queued, `working` while it runs,
`idle` when the turn ended (a message resumes it), `failed` when the job
failed, `stopped` when the owner stopped it or a kill switch cancelled it.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from hq_api import audit
from hq_api.db import Tx
from hq_api.domain import servers as SV
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.workshop import domain as D
from hq_common.redact import scrub

MODEL = "claude-code"  # the server's own login decides the model
EFFORT = "high"
TURN_TIMEOUT_S = 3600


def default_cwd(server: dict[str, Any]) -> str | None:
    """The repository the hub picks when the owner names none: the first
    repository of the server's latest map."""
    repos = ((server.get("map") or {}).get("repos")) or []
    for r in repos:
        if isinstance(r, dict) and isinstance(r.get("path"), str) and r["path"].startswith("/"):
            return str(r["path"])[:500]
    return None


async def check_driver(tx: Tx, server: dict[str, Any], driver: str | None) -> None:
    if driver and not await tx.scalar(
        """SELECT 1 FROM core.employees
           WHERE code = :c AND company_id = :co AND status = 'active' AND kind <> 'system'""",
        c=driver,
        co=server["company_id"],
    ):
        raise ApiError(
            422,
            "validation_failed",
            fields={"driver": "an active employee of the server's company"},
        )


async def open_session(
    tx: Tx,
    who: Principal,
    *,
    server: dict[str, Any],
    driver: str | None,
    title: str,
    brief: str,
    cwd: str | None,
    attachments: list[str] | None = None,
    actor: tuple[str, str] | None = None,
    on_behalf: str | None = None,
    work_ref: str | None = None,
    request_id: str | None = None,
    holding_driver: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The session and its first `claude` job (423 while the company is
    locked: nothing is made). `actor`: who the job runs as (the driver, or
    the owner; for a cross-company request, that company's CEO)."""
    await check_driver(tx, server, driver)
    if SV.state_of(server) == "revoked":
        raise ApiError(409, "validation_failed", fields={"server": "detached (revoked)"})
    await SV.check_lock(tx, server["company_id"], deploy=False)
    where = cwd or default_cwd(server)
    dk, dc = ("agent", driver) if driver else ("owner", "owner")
    row = await tx.one(
        """INSERT INTO workshop.sessions (company_id, title, brief, area, writes, opened_by_kind,
               opened_by_code, driver_kind, driver_code, runtime, model, effort, server_id, cwd)
           VALUES (:co, :title, :brief, '', true, :ok, :oc, :dk, :dc, 'company_server', :model,
                   :effort, :srv, :cwd)
           RETURNING id""",
        co=server["company_id"],
        title=scrub(title)[:300],
        brief=scrub(brief)[:20000],
        ok=who.kind,
        oc=who.code,
        dk=dk,
        dc=dc,
        model=MODEL,
        effort=EFFORT,
        srv=server["id"],
        cwd=where,
    )
    s = await D.load(tx, row["id"])
    await D.append(
        tx,
        s,
        "state",
        f"سشن روی سرور {server['company']}:{server['name']} ساخته شد",
        {"state": "starting"},
        actor=(who.kind, who.code),
    )
    if attachments:
        await D.append(
            tx,
            s,
            "message",
            "پیوست‌های شرح کار",
            {"attachments": [str(a) for a in attachments]},
            actor=(who.kind, who.code),
        )
    ak, ac = actor or (dk, dc)
    job = await SV.create_job(
        tx,
        server=server,
        kind="claude",
        args={
            "brief": brief,
            "title": title,
            "cwd": where,
            "session_ref": s["ref"],
            "resume": None,
            "attachments": [str(a) for a in attachments or []],
        },
        actor_kind=ak,
        actor_code=ac,
        on_behalf=on_behalf,
        work_ref=work_ref,
        summary=title,
        timeout_s=TURN_TIMEOUT_S,
        session_id=s["id"],
        request_id=request_id,
    )
    await audit.record(
        tx,
        who,
        company_id=server["company_id"],
        action="workshop.session",
        action_class="A1",
        target_kind="code_session",
        target_ref=s["ref"],
        summary=f"company_server {server['company']}:{server['name']} in {where or '~'}; "
        f"driver {dc}; job {job['id']}",
        request_id=request_id,
    )
    s = await D.load(tx, s["id"])
    await D.emit_state(tx, s)
    return s, job


async def open_job(tx: Tx, session_id: UUID) -> dict[str, Any] | None:
    return await tx.first(
        """SELECT id, state FROM infra.server_jobs
           WHERE session_id = :s AND state IN ('queued', 'running', 'awaiting_seal')
           ORDER BY created_at DESC LIMIT 1""",
        s=session_id,
    )


async def steer(
    tx: Tx, who: Principal, s: dict[str, Any], text: str, request_id: str | None = None
) -> dict[str, Any]:
    """An owner's (or the driver's) message: the next turn, resuming the
    server's Claude session. 409 while a turn still runs; 423 while locked."""
    if s["state"] in D.FINAL:
        raise ApiError(409, "validation_failed", fields={"session": f"{s['ref']} is {s['state']}"})
    if await open_job(tx, s["id"]) is not None:
        raise ApiError(
            409,
            "validation_failed",
            fields={"session": f"{s['ref']} is working; wait for its turn"},
        )
    server = await SV.load_server(tx, s["server_id"])
    last = await tx.first(
        """SELECT actor_kind, actor_code, on_behalf_code, work_ref FROM infra.server_jobs
           WHERE session_id = :s ORDER BY created_at DESC LIMIT 1""",
        s=s["id"],
    )
    ak, ac = (
        (last["actor_kind"], last["actor_code"]) if last else (s["driver_kind"], s["driver_code"])
    )
    if who.is_owner and s["driver_kind"] == "owner":
        ak, ac = "owner", "owner"
    return await SV.create_job(
        tx,
        server=server,
        kind="claude",
        args={
            "brief": text,
            "cwd": s["cwd"],
            "session_ref": s["ref"],
            "resume": s["external_id"],
        },
        actor_kind=ak,
        actor_code=ac,
        on_behalf=last["on_behalf_code"] if last else None,
        work_ref=last["work_ref"] if last else None,
        summary=text[:300],
        timeout_s=TURN_TIMEOUT_S,
        session_id=s["id"],
        request_id=request_id,
    )


async def stop(tx: Tx, s: dict[str, Any]) -> None:
    """The session was stopped: its open job is cancelled (the runner kills
    the process group on its next poll)."""
    j = await open_job(tx, s["id"])
    if j is not None:
        job = await SV.load_job(tx, j["id"], lock=True)
        await SV.cancel(tx, job, "session_stopped", "سشن متوقف شد؛ کار لغو شد")
