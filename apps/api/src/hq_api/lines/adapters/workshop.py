"""⟨1.37⟩ `workshop`: one turn of the holding's workshop for a flow step (contract §59.2, §43).

The build from the script, the voice, the cover, the direction and the reference: Claude Code with
a whole computer (domain/hands.py), Opus 5.5 at the step's effort (`max` for the video), at most
60 minutes, rendering with at most two processes (the workshop's ground rules say it), and the
turn's tools only what the step needs (at most 10, §59.12). A step is one turn, never a direct
session: a work of its own for this run (`mode: on_server`, its folder fresh each run), so the
turn carries nothing of yesterday's.

The build is asynchronous: `run` starts the turn and parks the step (`data.wait = "callback"`);
the turn's end (workspace.after_job → `after_turn`) closes the work and its workspace and completes
the step through the engine's callback with the files the turn left in `out/` (the step's files),
its answer as the text, its tokens and cost. A turn that left no file, failed or ran out of time
fails the step with one plain line.

Settings: `effort` (low · medium · high · xhigh · max; default high), `tools` (Claude Code's tool
names, at most 10; default the build's seven), `seat` (the role whose employee drives the turn;
default the company's CEO), `outputs` (the files `out/` must hold, in words for the brief),
`files_from` (the steps whose files go to `in/`; default every input's), `rules_fa` (the step's
rules, added to the brief).
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from hq_api.domain import hands as HANDS
from hq_api.domain import servers as SV
from hq_api.domain import work as W
from hq_api.domain import workspace as WS
from hq_api.errors import ApiError
from hq_api.lines.adapters import _common as C
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register
from hq_api.principal import Principal

log = logging.getLogger("hq_api.lines.workshop")

SERVICE = Principal(kind="service", code="lines", role="service")
DEFAULT_EFFORT = "high"
DEFAULT_TOOLS = ("Bash", "Read", "Write", "Edit", "Glob", "Grep", "TodoWrite")
TOOLS_MAX = 10
TEXT_CHARS = 3000
DEFAULT_OUTPUTS = "video.mp4 (ریلز)، story.mp4 (همان ویدیو، حداکثر ۵۹٫۸ ثانیه) و cover.jpg"
NO_FILES_FA = "نوبت کارگاه بی هیچ فایلی در out/ تمام شد."
TIMED_OUT_FA = "نوبت کارگاه در ۶۰ دقیقه تمام نشد."
FAILED_FA = "نوبت کارگاه نشد: {why}"
OFF_FA = "کارگاه هلدینگ آماده نیست (سرور کارگاه وصل یا روشن نیست)."
NO_SEAT_FA = "این شرکت مدیرعامل یا نقشی فعال برای راندن کارگاه ندارد."


def effort_of(ctx: StepContext) -> str:
    got = str(C.setting(ctx, "effort") or ctx.step.get("effort") or DEFAULT_EFFORT)
    return got if got in HANDS.EFFORTS else DEFAULT_EFFORT


def tools_of(ctx: StepContext) -> list[str]:
    """The turn's short list (§59.12): the step's own, of the workshop's tools, at most 10."""
    raw = C.setting(ctx, "tools") or list(DEFAULT_TOOLS)
    names = [str(t) for t in raw] if isinstance(raw, list | tuple) else [str(raw)]
    got = [t for t in dict.fromkeys(names) if t in HANDS.ALLOWED_TOOLS][:TOOLS_MAX]
    return got or list(DEFAULT_TOOLS)


def files_of(ctx: StepContext) -> list[str]:
    """The files the turn takes into `in/`: those of the steps named in `files_from`, else of every
    input, each once, at most the workshop's 10."""
    named = C.setting(ctx, "files_from")
    keys = [named] if isinstance(named, str) else list(named or ctx.inputs)
    out: list[str] = []
    for k in keys:
        o = ctx.inputs.get(str(k))
        if o is None:
            continue
        for f in (o.file_id, *o.files):
            if f and str(f) not in out:
                out.append(str(f))
    return out[: HANDS.INPUTS_MAX]


def brief_of(ctx: StepContext) -> str:
    """The turn's ask: the step's prompt, its rules, what each earlier step left (texts, cut), and
    what `out/` must hold."""
    rules = list(ctx.step.get("rules_fa") or C.setting(ctx, "rules_fa") or [])
    lines = [(ctx.prompt or "").strip() or str(ctx.step.get("title_fa") or "")]
    if rules:
        lines += ["", "## قاعده‌های این قدم", *[f"- {r}" for r in rules]]
    texts = [(k, o.text) for k, o in ctx.inputs.items() if (o.text or "").strip()]
    if texts:
        lines += ["", "## آنچه قدم‌های قبل ساخته‌اند"]
        for k, t in texts:
            lines += [f"### {k}", str(t).strip()[:TEXT_CHARS]]
    outputs = str(C.setting(ctx, "outputs") or DEFAULT_OUTPUTS)
    lines += [
        "",
        "## تحویل",
        f"در out/ فقط این‌ها: {outputs}. یک ساخت نهایی، بی پیش‌نمایش. رندر با حداکثر ۲ پردازش "
        "هم‌زمان. این یک قدم از روند خودکار است: از کسی چیزی نپرس و منتظر تأیید نمان.",
    ]
    return "\n".join(lines).strip()[: HANDS.BRIEF_CHARS]


SEAT_SQL = """SELECT e.id, e.code, e.kind, e.role FROM core.employees e
    WHERE e.company_id = :co AND e.status = 'active' AND e.kind <> 'system'
      AND (CAST(:seat AS text) IS NULL OR e.role = :seat OR e.code = :seat OR e.kind = 'ceo')
    ORDER BY (CAST(:seat AS text) IS NOT NULL AND (e.role = :seat OR e.code = :seat)) DESC,
             (e.kind = 'ceo') DESC, e.code
    LIMIT 1"""


class Workshop:
    kind = "workshop"

    async def run(self, ctx: StepContext) -> StepOutput:
        brief = brief_of(ctx)
        if not brief:
            raise StepFailed("شرح کار کارگاه خالی است.", code="empty_prompt")
        effort, tools, file_ids = effort_of(ctx), tools_of(ctx), files_of(ctx)
        await C.check_unlocked(ctx.hub)
        co = await C.company_of(ctx)
        title = f"{ctx.run_ref} · {ctx.step.get('title_fa') or 'کارگاه'}"[:300]
        hub = ctx.hub
        try:
            async with hub.db.tx(await hub.companies.ids()) as tx:
                server = await HANDS.workshop_server(tx)
                if server is None:
                    raise StepFailed(OFF_FA, code="workshop_off", retry=True)
                seat = C.setting(ctx, "seat") or ctx.step.get("seat") or None
                emp = await tx.first(SEAT_SQL, co=co.id, seat=seat)
                if emp is None:
                    raise StepFailed(NO_SEAT_FA, code="no_seat")
                who = Principal(
                    kind="agent", code=str(emp["code"]), role=str(emp["role"] or emp["kind"]),
                    company=ctx.company, company_id=co.id, employee_id=emp["id"],
                )  # fmt: skip
                # the step's own work: its folder and its session are this run's alone
                w = await W.create(
                    tx, SERVICE, company_id=co.id, company_code=ctx.company, title=title,
                    brief=brief, kind="one_off", priority="P2", assignee_code=str(emp["code"]),
                    mode=WS.MODE,
                )  # fmt: skip
                step = {"run": ctx.run_ref, "key": str(ctx.step.get("key") or "workshop")}
                await tx.exec(
                    """UPDATE work.work SET run_meta = COALESCE(run_meta, '{}'::jsonb)
                           || jsonb_build_object('line_step', CAST(:m AS jsonb)) WHERE id = :id""",
                    id=w["id"],
                    m=json.dumps(step),
                )
                got = await HANDS.start(
                    tx, who, server, w, brief=brief, title=title, files=file_ids, effort=effort,
                    tools=tools, extra_args={"line_step": step},
                )  # fmt: skip
        except ApiError as exc:
            raise StepFailed(
                exc.message_fa or f"کارگاه این نوبت را نگرفت ({exc.code}).",
                code=exc.code,
                retry=exc.code in ("workshop_unavailable", "company_locked", "workspace_elsewhere"),
            ) from exc
        return StepOutput(
            text=f"ساخت در کارگاه شروع شد ({got.work_ref}).",
            via="workshop",
            data={
                "wait": "callback",
                "work": got.work_ref,
                "job": got.job,
                "effort": effort,
                "tools": tools,
                "model": HANDS.MODEL,
                "inputs": len(file_ids),
            },
        )


register(Workshop())


# ----------------------------------------------------------- the turn's end --
async def after_turn(hub: Any, job_id: UUID) -> bool:
    """A workshop turn ended (workspace.after_job, after its result was committed): a line step's
    turn completes its step and closes its own work; True when it was one. Never raises."""
    try:
        return await _after_turn(hub, job_id)
    except Exception:
        log.exception("a line step's workshop turn was not completed", extra={"job": str(job_id)})
        return True


async def _after_turn(hub: Any, job_id: UUID) -> bool:
    body: dict[str, Any]
    async with hub.db.tx(await hub.companies.ids()) as tx:
        j = await SV.load_job(tx, job_id)
        args = j.get("args") or {}
        step = args.get("line_step")
        if j["kind"] != "claude" or not isinstance(step, dict) or not args.get("workspace"):
            return False
        wid = await tx.scalar("SELECT id FROM work.work WHERE ref = :r", r=args["workspace"])
        if wid is None:
            return True
        w = await W.load(tx, wid, lock=True)
        ws = await WS.of_work(tx, w["id"], lock=True)
        if ws is None or ws["state"] in ("delivered", *WS.ENDED):
            return True  # its end was heard already
        tokens = W.effective_tokens(*WS._usage(j.get("usage") or {}))
        if tokens:
            try:
                async with tx.conn.begin_nested():
                    await W.add_usage(tx, w, tokens, Decimal(0))
            except Exception:  # noqa: BLE001 - a booking refused never costs the step
                log.info("workshop step tokens not booked", extra={"work": w["ref"]})
        files = await WS.made_files(tx, j, w["company_id"]) if j["state"] == "done" else []
        said = (await SV.full_answer(tx, hub, j)).strip() if j["state"] == "done" else ""
        usd = await tx.scalar(
            "SELECT COALESCE(SUM(equiv_cost_usd), 0) FROM llm.calls WHERE work_ref = :w",
            w=w["ref"],
        )
        ok = j["state"] == "done" and bool(files)
        await tx.exec(
            "UPDATE work.workspaces SET state = :s, updated_at = now() WHERE id = :id",
            id=ws["id"],
            s="delivered" if ok else "failed",
        )
        evidence = [{"kind": "log", "ref": f"line_run:{step.get('run')}:{step.get('key')}",
                     "note": f"{len(files)} files from job {job_id}"}]  # fmt: skip
        if w["status"] not in W.CLOSED:
            await tx.exec(
                """UPDATE work.work SET evidence = CAST(:e AS jsonb), status = :s,
                       closed_at = now() WHERE id = :id""",
                id=w["id"],
                e=json.dumps(evidence),
                s="done" if ok else "failed",
            )
        rows = await tx.all(
            "SELECT id, name, mime FROM files.files WHERE id = ANY(CAST(:ids AS uuid[]))",
            ids=files,
        )
        names = {str(r["id"]): str(r["name"]) for r in rows}
        video = next((str(r["id"]) for r in rows if str(r["mime"]).startswith("video/")
                      and not str(r["name"]).lower().startswith("story")), None)  # fmt: skip
        if ok:
            body = {"ok": True, "text": (said or WS.OUT_ONLY_FA)[:4000], "files": files,
                    "file_id": video or files[0],
                    "data": {"work": w["ref"], "job": str(job_id), "names": names}}  # fmt: skip
        else:
            if j["state"] == "done":
                why = NO_FILES_FA
            elif j.get("error_code") == "timed_out":
                why = TIMED_OUT_FA
            else:
                from hq_api.domain import humanize as HZ

                why = FAILED_FA.format(
                    why=HZ.humanize(str(j.get("summary_fa") or "")) or j["state"]
                )
            body = {"ok": False, "error_fa": why[:900]}
        body.update(run=step.get("run"), step=step.get("key"), tokens=int(tokens),
                    usd_equiv=str(Decimal(str(usd or 0))), via="workshop")  # fmt: skip
    from hq_api.lines import engine as LE

    try:
        await LE.on_callback(hub, body)
    except ApiError:
        log.info("the workshop step was not waiting", extra={"job": str(job_id)})
    return True
