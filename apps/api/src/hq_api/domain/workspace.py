"""The company workspace: a working computer per company (contract §33.10 ⟨1.15⟩).

A work with `mode: "on_server"` is done on its company's own server: when one of its runs starts and
the company has a paired server on runner >= 0.3.0 (data: seed/work/grok.yaml), the run hands the
turn to that server's own Claude Code (§26.2 `claude` job, `workspace: <work-ref>`) and ends without
a model call on the hub. The runner works in `~/hq-workspace/<work-ref>`, the same folder on every
turn: a later run of the work (the owner's budget, a child's output, a resume) resumes the same
Workshop session (`--resume`) in the same folder. A3 steps stop as `awaiting_seal` exactly as today
(the runner's PreToolUse hook asks the hub to classify every command).

- the turn's answer becomes the work's deliverable (the work delivered, like any output);
- a turn that fails marks the workspace failed: the work's next run is on the hub, as today;
- the owner stops it (`POST /work/{id}/stop`): the open job is cancelled (the runner kills its
  process group) and the workspace is stopped; nothing runs for the work until the owner sets
  another mode (`single` runs it on the hub) or cancels it;
- when the work closes the runner is told once (`closed` on its long-poll); it removes the folder
  `keep_days` (30) days later and logs it there. One workspace per work, never shared.

Without a paired server on 0.3.0 (or after a failed turn) the work runs on the hub as today.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import humanize as HZ
from hq_api.domain import servers as SV
from hq_api.domain import split as SP
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.workshop import server_sessions as SS

SERVICE = Principal(kind="service", code="workspace", role="service")
MODE = "on_server"
ENDED = ("stopped", "failed")
SKIP_TRIGGERS = ("talk", "meeting")
FAILED_REASON = "workspace_failed:"
DONE_REASON = "workshop_done:"  # ⟨2026-11-09⟩ §43 a workshop turn of the order itself ended
OUT_ONLY_FA = "فایل‌های این نوبت پیوست همین خروجی است."
WORKSHOP_FA = "کارگاه هلدینگ"
FILES_MAX = 20  # files a turn may send back (POST /runners/jobs/{id}/files holds it)
BRIEF_CHARS = 12000

State = Literal["starting", "working", "awaiting_seal", "idle", "delivered", "stopped", "failed"]


class WorkspaceProgress(BaseModel):
    """A work's workspace on its company's server, as the order report shows it."""

    work_ref: str
    server: str
    where_fa: str
    path: str
    state: State
    turns: int
    session_ref: str | None = None
    last_step_fa: str | None = None
    note_fa: str | None = None
    updated_at: datetime
    closed_at: datetime | None = None
    remove_after: datetime | None = None


class WorkStopped(BaseModel):
    work_ref: str
    workspace: State | None = None
    jobs_stopped: int = 0


def path_of(ref: str) -> str:
    return f"~/hq-workspace/{ref}"


def version_ok(version: str | None, minimum: str) -> bool:
    def parts(v: str | None) -> tuple[int, ...]:
        return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3])

    return bool(version) and parts(version) >= parts(minimum)


def runner_min() -> str:
    return str(SP.settings()["workspace"]["runner_min"])


async def of_work(tx: Tx, work_id: UUID, *, lock: bool = False) -> dict[str, Any] | None:
    return await tx.first(
        "SELECT * FROM work.workspaces WHERE work_id = :w" + (" FOR UPDATE" if lock else ""),  # noqa: S608
        w=work_id,
    )


async def eligible_server(
    tx: Tx, w: dict[str, Any], ws: dict[str, Any] | None
) -> dict[str, Any] | None:
    """The server a work's turn runs on: its workspace's own (a folder lives on one server), else
    the company's first paired server on runner >= runner_min (an online one first)."""
    minimum = runner_min()
    if ws is not None:
        s = await SV.load_server(tx, ws["server_id"])
        ok = SV.state_of(s) in ("online", "offline") and version_ok(s["runner_version"], minimum)
        return s if ok else None
    rows = await tx.all(
        """SELECT id, runner_version FROM infra.servers
           WHERE company_id = :co AND origin = 'attached' AND state IN ('online', 'offline')
           ORDER BY (state = 'online') DESC, created_at""",
        co=w["company_id"],
    )
    for r in rows:
        if version_ok(r["runner_version"], minimum):
            return await SV.load_server(tx, r["id"])
    return None


async def busy_job(tx: Tx, ws: dict[str, Any]) -> dict[str, Any] | None:
    if ws.get("session_id") is None:
        return None
    return await SS.open_job(tx, ws["session_id"])


def compose(
    w: dict[str, Any], run: dict[str, Any], first: bool, split: dict[str, Any] | None
) -> str:
    """The turn's brief for the server's Claude (Persian for the owner's reading, the rules plain)."""
    lines = [
        f"# کار {w['ref']}: {w['title']}",
        "",
        "تو روی سرور خود این شرکت کار میکنی، در پوشه‌ی ماندگار همین کار "
        f"({path_of(w['ref'])}). همه‌ی فایل‌های کار را همین‌جا نگه دار؛ نوبت بعدی همین پوشه را میبیند.",
        "وقتی خروجی آماده شد، پاسخ نهایی‌ات خود خروجی است (فارسی، Markdown، با شواهد: فایل، "
        "commit، لینک یا عدد). اگر برای ادامه به تصمیم مالک نیاز است، همان را روشن بنویس و بایست.",
        "هر کار ویرانگر (پاک کردن دیتابیس، volume، backup، دیسک، یا تغییر SSH، کاربرها و فایروال) "
        "منتظر مُهر مالک میماند؛ دورش نزن. هیچ رمزی را چاپ نکن.",
        "",
    ]
    if first:
        lines += ["## شرح کار", (w.get("brief") or "")[:BRIEF_CHARS]]
    else:
        lines += [
            "## ادامه",
            f"این نوبت تازه‌ی همین کار است (دلیل: {run.get('reason') or run.get('trigger')}).",
            "از جایی که ماندی ادامه بده. شرح کار، اگر عوض شده باشد:",
            (w.get("brief") or "")[:BRIEF_CHARS],
        ]
    if w.get("progress_note"):
        lines += ["", f"آخرین گزارش پیشرفت: {w['progress_note'][:1000]}"]
    if split:
        lines += [
            "",
            "## بخش‌های موازی این کار",
            json.dumps(split, ensure_ascii=False)[:BRIEF_CHARS],
        ]
    return "\n".join(lines)


async def hand_over(hub: Any, run: dict[str, Any], emp: dict[str, Any]) -> str | None:
    """The run of an `on_server` work: its turn on the company's server (a note for the run), or
    None when the work runs on the hub (another mode, no paired server on 0.3.0, a workspace that
    was stopped or failed, a locked company)."""
    if run.get("work_id") is None or run.get("trigger") in SKIP_TRIGGERS:
        return None
    async with hub.db.tx(await hub.companies.ids()) as tx:
        w = await W.load(tx, run["work_id"], lock=True)
        if w.get("mode") != MODE or w["status"] in W.CLOSED:
            return None
        ws = await of_work(tx, w["id"], lock=True)
        if ws is not None and ws["state"] == "stopped":
            # the owner stopped it: nothing runs for it until the owner sets another mode
            return f"workspace {w['ref']}: stopped by the owner"
        if ws is not None and ws["state"] in ENDED:
            return None
        if ws is not None and (j := await busy_job(tx, ws)) is not None:
            return f"workspace {w['ref']}: a turn is still {j['state']} on the server"
        server = await eligible_server(tx, w, ws)
        if server is None:
            if ws is None and not await tx.scalar(
                "SELECT 1 FROM work.work_events WHERE work_id = :w AND kind = 'workspace_unavailable'",
                w=w["id"],
            ):
                await W.event(tx, w, "workspace_unavailable", SERVICE, {"runner_min": runner_min()})
            return None
        split = await SP.merge_brief(tx, w["id"])
        brief = compose(w, run, ws is None or ws.get("session_id") is None, split)
        conf = SP.settings()["workspace"]
        extra = {"workspace": w["ref"]}
        try:
            async with tx.conn.begin_nested():
                if ws is None or ws.get("session_id") is None:
                    s, job = await SS.open_session(
                        tx,
                        SERVICE,
                        server=server,
                        driver=emp["code"],
                        title=f"{w['ref']}: {w['title']}"[:300],
                        brief=brief,
                        cwd=path_of(w["ref"]),
                        actor=("agent", emp["code"]),
                        work_ref=w["ref"],
                        extra_args=extra,
                        timeout_s=int(conf["turn_timeout_s"]),
                    )
                    session_id = s["id"]
                else:
                    from hq_api.workshop import domain as WD

                    s = await WD.load(tx, ws["session_id"])
                    job = await SS.steer(
                        tx,
                        SERVICE,
                        s,
                        brief,
                        extra_args=extra,
                        timeout_s=int(conf["turn_timeout_s"]),
                    )
                    session_id = s["id"]
        except ApiError as exc:  # a lock, a detached server, a finished session: the hub runs it
            await W.event(tx, w, "workspace_unavailable", SERVICE, {"code": exc.code})
            if ws is not None and exc.status != 423:  # its session cannot go on: the hub from now
                await _set(tx, ws, "failed", "نشست روی سرور دیگر ادامه پیدا نمیکند")
            return None
        if ws is None:
            ws = await tx.one(
                """INSERT INTO work.workspaces (company_id, work_id, work_ref, server_id, session_id,
                       state, turns, last_job_id)
                   VALUES (:co, :w, :ref, :s, :sess, 'starting', 1, :j) RETURNING *""",
                co=w["company_id"],
                w=w["id"],
                ref=w["ref"],
                s=server["id"],
                sess=session_id,
                j=job["id"],
            )
        else:  # steer() moved the workspace on (its turn, its job)
            ws = await tx.one("SELECT * FROM work.workspaces WHERE id = :id", id=ws["id"])
        if w["status"] == "queued":
            await W.set_status(tx, w, "in_progress", accepted_at=datetime.now(UTC))
        await W.event(
            tx, w, "workspace_turn", SERVICE,
            {"server": server["name"], "job": str(job["id"]), "turn": ws["turns"]},
        )  # fmt: skip
        await audit.record(
            tx,
            SERVICE,
            company_id=w["company_id"],
            action="workspace.turn",
            action_class="A2",
            target_kind="work",
            target_ref=w["ref"],
            summary=f"turn {ws['turns']} on {server['company']}:{server['name']} in "
            f"{path_of(w['ref'])}; job {job['id']}",
        )
        await events.emit(
            tx, w["company"], "work.updated", w["ref"],
            {"workspace": "starting", "server": server["name"], "turn": ws["turns"]},
        )  # fmt: skip
        return f"workspace {w['ref']}: turn {ws['turns']} on {server['name']} (job {job['id']})"


async def after_job(hub: Any, job_id: UUID) -> None:
    """A workspace turn ended (after the runner's result was committed): its answer is the work's
    deliverable; a failure sends the work back to the hub; a cancel is a stop."""
    from hq_api.domain import players as PL

    async with hub.db.tx(await hub.companies.ids()) as tx:
        j = await SV.load_job(tx, job_id)
        if j["kind"] != "claude" or not (j.get("args") or {}).get("workspace"):
            return
        ws = await tx.first(
            """SELECT * FROM work.workspaces WHERE work_ref = :ref
                 AND (last_job_id = :j OR session_id = :sess) FOR UPDATE""",
            ref=j["args"]["workspace"],
            j=job_id,
            sess=j["session_id"],
        )
        if ws is None or ws["state"] in ("delivered", *ENDED):
            return
        w = await W.load(tx, ws["work_id"], lock=True)
        tokens = W.effective_tokens(*_usage(j.get("usage") or {}))
        hands = bool((j.get("args") or {}).get("hands"))  # ⟨2026-11-09⟩ §43 the workshop
        # ⟨2026-11-10⟩ §43.9 the wall between the companies' turns: what the runner says of it
        wall, wall_why = wall_of(j) if hands else (None, None)
        if wall == "off":
            # never in the way of the work (the owner: «کار راه بیفته نه اینکه گیر بکنه»); said
            # where the holding's technical team reads, never to the owner
            await audit.record(
                tx,
                SERVICE,
                company_id=(await hub.companies.holding()).id,
                action="workshop.sandbox_off",
                action_class="A1",
                target_kind="work",
                target_ref=w["ref"],
                summary=f"a workshop turn of {w['ref']} ran without the wall between companies"
                f" on {j['server_name']}: {wall_why}"[:500],
            )
        if tokens:
            await W.add_usage(
                tx, w, tokens, Decimal(0)
            )  # the server's own login: tokens, no hub money
            if hands and w.get("budget_tokens") is not None:
                # ⟨2026-11-10⟩ the workshop has no token cap (the owner's decision): what a turn
                # spent is shown on the work but not taken from the budget of its assignee's own
                # runs (a long turn left the next run a cap of zero)
                await tx.exec(
                    "UPDATE work.work SET budget_tokens = budget_tokens + :t WHERE id = :id",
                    t=tokens,
                    id=w["id"],
                )
        if j["state"] == "done":
            said = (await SV.full_answer(tx, hub, j)).strip()
            answer = said or (j["summary_fa"] or "")
            # ⟨2026-11-09⟩ the files the turn left in `out/` (runner >= 0.3.2), checked
            files = await made_files(tx, j, w["company_id"])
            if files and not answer:
                answer = OUT_ONLY_FA
            state: State = "idle"
            # a workshop turn of the order itself leaves it open: its holder shows the owner
            close = not (hands and w["parent_id"] is None)
            # ⟨1.32⟩ §54 a direct turn is the session's own holder: what it says is its word in
            # the session, and only what it made (files in `out/`) is an output
            direct = hands and bool((j.get("args") or {}).get("direct"))
            if direct:
                from hq_api.domain import direct as DR

                if files and (w["status"] in W.OPEN or w["status"] == "delivered"):
                    await PL.deliver(
                        tx,
                        w,
                        title=f"خروجی جلسه: {w['title']}"[:300],
                        body=said or OUT_ONLY_FA,
                        produced_with={
                            "runtime": "workshop",
                            "direct": True,
                            "server": j["server_name"],
                            "workspace": w["ref"],
                            "job": str(j["id"]),
                            "session": j.get("session_ref"),
                            "files": len(files),
                            **({"sandbox": wall} if wall else {}),
                            **made_with(j),
                        },
                        hub=hub,
                        attachments=files,
                        close=False,
                    )
                await DR.after_turn(tx, hub, j, w, answer=said, files=files)
            elif (w["status"] in W.OPEN or w["status"] == "delivered") and answer:
                await PL.deliver(  # a long answer goes whole into an attachment
                    tx,
                    w,
                    title=(f"خروجی کارگاه: {w['title']}" if hands
                           else f"خروجی روی سرور: {w['title']}")[:300],
                    body=answer,
                    produced_with={
                        "runtime": "workshop" if hands else "company_server",
                        "server": j["server_name"],
                        "workspace": w["ref"],
                        "job": str(j["id"]),
                        "session": j.get("session_ref"),
                        **({"files": len(files)} if files else {}),
                        **({"sandbox": wall} if wall else {}),
                        # ⟨1.31⟩ §53 the model the turn ran on and how hard it thought, as the
                        # runner applied it (absent from a runner < 0.3.5)
                        **made_with(j),
                    },
                    hub=hub,
                    attachments=files,
                    close=close,
                )  # fmt: skip
                state = "delivered" if close else "idle"
                if close:
                    await SP.after_part(tx, w["id"])
                    await SP.after_parent(tx, w["id"])
                else:  # the holder tells the owner what is ready and asks «تأیید یا اصلاح؟»
                    await _wake_or_say(tx, w, f"{DONE_REASON}{w['ref']}")
            await _set(tx, ws, state, None)
        elif j["state"] == "cancelled":
            await _close_direct(tx, j)
            await _set(tx, ws, "stopped", HZ.humanize(j["summary_fa"]) or "متوقف شد")
        else:
            await _close_direct(tx, j)
            note = HZ.humanize(j["summary_fa"]) or "کار روی سرور به نتیجه نرسید"
            await _set(tx, ws, "failed", note)
            await W.event(
                tx, w, "workspace_failed", SERVICE,
                {"job": str(j["id"]), "code": j["error_code"], "note_fa": note[:500]},
            )  # fmt: skip
            if hands:
                # ⟨2026-11-10⟩ what the turn had already made is not lost with it: the files it
                # left in `out/` (a turn stopped at its hour sends them, runner >= 0.3.3) come as
                # an unfinished output of the work, which stays open
                files = await made_files(tx, j, w["company_id"])
                if files and (w["status"] in W.OPEN or w["status"] == "delivered"):
                    await PL.deliver(
                        tx,
                        w,
                        title=f"خروجی ناتمام کارگاه: {w['title']}"[:300],
                        body=f"{note}\n\n{OUT_ONLY_FA}",
                        produced_with={
                            "runtime": "workshop",
                            "server": j["server_name"],
                            "workspace": w["ref"],
                            "job": str(j["id"]),
                            "session": j.get("session_ref"),
                            "files": len(files),
                            "unfinished": True,
                            **({"sandbox": wall} if wall else {}),
                        },
                        hub=hub,
                        attachments=files,
                        close=False,
                    )
                # ⟨2026-11-09⟩ never a silent stop: the holder gets a run now and says why (60
                # minutes, an error); a fix is the next workshop.run (a fresh session, same folder)
                await _wake_or_say(tx, w, f"{FAILED_REASON}{w['ref']}")
            elif w["status"] in W.OPEN and w["assignee_id"] is not None:
                # the next run is on the hub, as today: a `resume` the worker turns into one run
                await W.event(tx, w, W.RESUME, SERVICE, {"why": f"{FAILED_REASON}{w['ref']}"})
        await events.emit(tx, w["company"], "work.updated", w["ref"], {"workspace": ws["state"]})


async def _close_direct(tx: Tx, j: dict[str, Any]) -> None:
    """⟨1.32⟩ §54 a direct turn that was stopped or failed: its own run ends with it."""
    if (j.get("args") or {}).get("direct"):
        from hq_api.domain import direct as DR

        await DR.close_run(tx, j)


async def _wake_or_say(tx: Tx, w: dict[str, Any], reason: str) -> None:
    """⟨2026-11-10⟩ The work's assignee gets a run for what the turn left, or its order's session
    says why not (a lock, nobody assigned): a workshop turn never ends in silence."""
    from hq_api.domain import order_report as OR
    from hq_api.domain import session_activity as SA

    if await tx.scalar("SELECT work.wake_assignee(:w, :r)", w=w["id"], r=reason) is not None:
        return
    ref = await OR.order_of_work(tx, w["id"])
    rep = await OR.ensure(tx, ref) if ref else None
    if rep is None or rep.get("ended_at") is not None:
        return
    lock = await tx.scalar("SELECT control.lock_state(:co)", co=w["company_id"])
    if lock is not None:
        why = "شرکت قفل است و تا قفل باز نشود کار راه نمیافتد"
    elif w.get("assignee_id") is None:
        why = "کار مسئولی ندارد"
    else:
        why = "کار راه نیفتاد؛ «ادامه بده» را بزنید"
    await OR._append_steps(tx, rep["id"], [OR._step(SA.SYSTEM_FA, f"کار کارگاه تمام شد ولی {why}")])


def made_with(j: dict[str, Any]) -> dict[str, str]:
    """⟨1.31⟩ §53 {model, effort} of a turn: the model the hub asked for and the effort its
    runner says it passed to Claude Code (a runner older than 0.3.5 passes none and says none)."""
    args, result = j.get("args") or {}, j.get("result") or {}
    out: dict[str, str] = {}
    if isinstance(args.get("model"), str) and args.get("hands"):
        out["model"] = str(args["model"])[:64]
    if result.get("effort") in ("low", "medium", "high", "xhigh", "max"):
        out["effort"] = str(result["effort"])
    return out


def wall_of(j: dict[str, Any]) -> tuple[str | None, str | None]:
    """⟨2026-11-10⟩ §43.9 (state, why) of a workshop turn's wall, as its runner reported it:
    `on`, `off` with the reason, or (None, None) from a runner that does not know it (< 0.3.4)."""
    box = (j.get("result") or {}).get("sandbox")
    if not isinstance(box, dict) or box.get("state") not in ("on", "off"):
        return None, None
    why = str(box.get("why") or "")[:300] if box["state"] == "off" else None
    return str(box["state"]), why


async def made_files(tx: Tx, j: dict[str, Any], company_id: Any) -> list[str]:
    """⟨2026-11-09⟩ The files a workspace turn sent from `out/` (its result's `files`), checked:
    made by this job, in the work's company, originals. Anything else named there is dropped."""
    raw = (j.get("result") or {}).get("files") or []
    ids = [str(x) for x in raw if isinstance(x, str) and re.fullmatch(r"[0-9a-f-]{36}", x)]
    if not ids:
        return []
    rows = await tx.all(
        """SELECT id FROM files.files WHERE id = ANY(CAST(:ids AS uuid[])) AND company_id = :co
             AND variant = 'original' AND meta->>'job' = :job ORDER BY created_at""",
        ids=ids[:FILES_MAX],
        co=company_id,
        job=str(j["id"]),
    )
    return [str(r["id"]) for r in rows]


def _usage(u: dict[str, Any]) -> tuple[int, int, int, int]:
    def n(*keys: str) -> int:
        for k in keys:
            v = u.get(k)
            if isinstance(v, int | float) and not isinstance(v, bool):
                return max(0, int(v))
        return 0

    return (
        n("input_tokens"),
        n("output_tokens"),
        n("cache_read_tokens", "cache_read_input_tokens"),
        n("cache_write_tokens", "cache_creation_input_tokens"),
    )


async def _set(tx: Tx, ws: dict[str, Any], state: str, note: str | None) -> None:
    await tx.exec(
        "UPDATE work.workspaces SET state = :st, note_fa = :n, updated_at = now() WHERE id = :id",
        st=state,
        n=(note or None) and note[:1000],
        id=ws["id"],
    )
    ws["state"] = state


async def stop(tx: Tx, who: Principal, w: dict[str, Any]) -> WorkStopped:
    """The owner's stop: the workspace's open turn cancelled (its process group killed by the
    runner) and the workspace stopped: no later run of the work does anything until the owner sets
    another mode (`single`: on the hub) or cancels it. The work itself stays open. Idempotent."""
    jobs = 0
    ws = await of_work(tx, w["id"], lock=True)
    if ws is not None:
        if (j := await busy_job(tx, ws)) is not None:
            job = await SV.load_job(tx, j["id"], lock=True)
            await SV.cancel(tx, job, "workspace_stopped", "مالک کار روی سرور را متوقف کرد")
            jobs = 1
        if ws.get("session_id") is not None:
            await tx.exec(
                """UPDATE workshop.sessions SET state = 'stopped', finished_at = now()
                   WHERE id = :s AND state NOT IN ('done', 'failed', 'stopped')""",
                s=ws["session_id"],
            )
        if ws["state"] not in ENDED:
            await _set(tx, ws, "stopped", "مالک متوقفش کرد")
    await W.event(tx, w, "stopped", who, {"jobs": jobs})
    await audit.record(
        tx,
        who,
        company_id=w["company_id"],
        action="work.stop",
        action_class="A2",
        target_kind="work",
        target_ref=w["ref"],
        summary=f"stopped: {jobs} server turn(s)",
    )
    await events.emit(tx, w["company"], "work.updated", w["ref"], {"stopped": True})
    return WorkStopped(
        work_ref=w["ref"],
        workspace=ws["state"] if ws is not None else None,
        jobs_stopped=jobs,
    )


# ---------------------------------------------------------- the close --
async def sweep(tx: Tx) -> int:
    """A workspace whose work closed gets its close time and the day the runner removes it."""
    keep = int(SP.settings()["workspace"]["keep_days"])
    rows = await tx.all(
        """UPDATE work.workspaces ws
           SET closed_at = COALESCE(w.closed_at, now()),
               remove_after = COALESCE(w.closed_at, now()) + make_interval(days => :k),
               updated_at = now()
           FROM work.work w
           WHERE w.id = ws.work_id AND ws.closed_at IS NULL
             AND w.status IN ('done', 'cancelled', 'failed')
           RETURNING ws.id""",
        k=keep,
    )
    return len(rows)


async def closed_for(tx: Tx, server_id: UUID) -> list[dict[str, Any]]:
    """The closes the server's runner has not been told yet, once each (its long-poll), logged."""
    await sweep(tx)
    rows = await tx.all(
        """UPDATE work.workspaces SET close_sent_at = now(), updated_at = now()
           WHERE server_id = :s AND closed_at IS NOT NULL AND close_sent_at IS NULL
           RETURNING company_id, work_ref, closed_at, remove_after""",
        s=server_id,
    )
    for r in rows:
        await audit.record(
            tx,
            SERVICE,
            company_id=r["company_id"],
            action="workspace.close",
            action_class="A1",
            target_kind="work",
            target_ref=r["work_ref"],
            summary=f"the runner was told; it removes {path_of(r['work_ref'])} after "
            f"{r['remove_after'].date().isoformat()}",
        )
    return [
        {"workspace": r["work_ref"], "closed_at": r["closed_at"].astimezone(UTC).isoformat()}
        for r in rows
    ]


# --------------------------------------------------------------- reading --
PROGRESS_SQL = """
    SELECT ws.*, s.name AS server_name, c.name_fa AS company_fa, c.code AS company,
           (SELECT count(*) FROM infra.servers o WHERE o.company_id = ws.company_id
              AND o.state IS DISTINCT FROM 'revoked') AS servers,
           j.state AS job_state, ses.ref AS session_ref,
           (SELECT sc.kind FROM core.companies sc WHERE sc.id = s.company_id) AS server_kind,
           (SELECT e.summary_fa FROM workshop.events e WHERE e.session_id = ws.session_id
             ORDER BY e.seq DESC LIMIT 1) AS last_step
    FROM work.workspaces ws JOIN infra.servers s ON s.id = ws.server_id
    JOIN core.companies c ON c.id = ws.company_id
    LEFT JOIN infra.server_jobs j ON j.id = ws.last_job_id
    LEFT JOIN workshop.sessions ses ON ses.id = ws.session_id
"""


def live_state(r: dict[str, Any]) -> State:
    if r["state"] in ("starting", "working", "awaiting_seal", "idle") and r.get("job_state"):
        js = r["job_state"]
        if js == "awaiting_seal":
            return "awaiting_seal"
        if js == "running":
            return "working"
        if js == "queued":
            return "starting"
        if js == "cancelled":
            return "stopped"
        if js == "failed":
            return "failed"
    return r["state"]  # type: ignore[no-any-return]


def render(r: dict[str, Any]) -> WorkspaceProgress:
    company = r["company_fa"] or r["company"]
    where = f"{company} · {r['server_name']}" if int(r["servers"] or 0) > 1 else company
    if r.get("server_kind") == "holding":  # ⟨2026-11-09⟩ §43 the holding's workshop
        where = WORKSHOP_FA
    return WorkspaceProgress(
        work_ref=r["work_ref"],
        server=r["server_name"],
        where_fa=where,
        path=path_of(r["work_ref"]),
        state=live_state(r),
        turns=int(r["turns"]),
        session_ref=r["session_ref"],
        last_step_fa=HZ.humanize(r["last_step"])[:300] if r["last_step"] else None,
        note_fa=r["note_fa"],
        updated_at=r["updated_at"],
        closed_at=r["closed_at"],
        remove_after=r["remove_after"],
    )


async def progress(tx: Tx, work_ids: list[UUID]) -> list[WorkspaceProgress]:
    rows = await tx.all(
        PROGRESS_SQL + " WHERE ws.work_id = ANY(:ids) ORDER BY ws.created_at", ids=work_ids
    )
    return [render(r) for r in rows]
