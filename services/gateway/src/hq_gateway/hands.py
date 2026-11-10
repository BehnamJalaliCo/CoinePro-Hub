"""⟨2026-11-09⟩ The workshop: hands for any task (contract §43, agents/tools.md).

    workshop.run   A2  {brief, title?, work?, task?}
    workshop.stop  A1  {work?, reason?}     ⟨2026-11-10⟩ the caller stops its own running turn

The owner: «اپ وسیله‌ی ارتباط است؛ سرور کامپیوتر است و Claude روی سرور مغز و دست دارد». Every
working role hands any task none of its tools covers to the holding's workshop: Claude Code
with a whole computer (a locked-down user on the hub server, its own runner), in the work's own
folder. The api queues the turn on the workshop server for the run's work item (or `work`, one
assigned to the caller) and answers at once; the turn's answer and its `out/` files come back
as an output of that work by themselves, and the work's assignee gets a run to show the owner.
Nothing here waits for the turn: it may take up to 60 minutes.
"""

from __future__ import annotations

from pydantic import Field

from hq_gateway import tools as T

DONE_FA = (
    "کارگاه شروع کرد. همین حالا اجرایت را با done ببند؛ خروجی و فایل‌های out/ خودشان به همین کار "
    "برمیگردند و تو یک اجرای تازه میگیری تا به مالک نشانش بدهی."
)
BUSY_FA = "کارگاه هنوز روی همین کار است؛ کار تازه‌ای شروع نشد. اجرایت را ببند؛ خروجی خودش میرسد."


class WorkshopIn(T.In):
    brief: str = Field(min_length=1, max_length=20000)
    title: str | None = Field(default=None, max_length=300)
    work: str | None = Field(default=None, pattern=T.WORK_REF)
    # ⟨2026-11-10⟩ the plan task the turn is for (required in a step-by-step order, «با من»)
    task: int | None = Field(default=None, ge=1, le=99)


class WorkshopStopIn(T.In):
    work: str | None = Field(default=None, pattern=T.WORK_REF)
    reason: str | None = Field(default=None, max_length=300)


STOPPED_FA = "نوبت کارگاه متوقف شد. به مالک بگو متوقف شد و قدم بعد را از او بپرس."
NOTHING_FA = "کارگاه الان روی این کار نوبتی در حال اجرا ندارد؛ چیزی برای توقف نبود."


async def workshop_stop(api: T.Api, call: T.Call, a: WorkshopStopIn) -> T.Result:
    body: dict[str, object] = {}
    if a.work:
        body["work"] = a.work
    if a.reason:
        body["reason"] = await T._text(a.reason)
    resp = await api.request("POST", "/internal/v1/workshop/stop", call.token, json=body)
    r = T.from_response(resp, None)
    if r.outcome != "ok" or not isinstance(r.data, dict):
        return r
    r.ref = str(r.data.get("work_ref") or "") or None
    r.hint_fa = STOPPED_FA if r.data.get("stopped") else NOTHING_FA
    return r


async def workshop_run(api: T.Api, call: T.Call, a: WorkshopIn) -> T.Result:
    # Prose an agent writes leaves redacted, as every brief does.
    body: dict[str, object] = {"brief": await T._text(a.brief)}
    if a.title:
        body["title"] = await T._text(a.title)
    if a.work:
        body["work"] = a.work
    if a.task is not None:
        body["task"] = a.task
    resp = await api.request(
        "POST",
        "/internal/v1/workshop/runs",
        call.token,
        json=body,
        idem=call.idem(f"workshop.run:{a.work or call.gate.get('work_ref') or ''}"),
    )
    r = T.from_response(resp, None)
    if r.outcome != "ok" or not isinstance(r.data, dict):
        return r
    d = r.data
    r.ref = str(d.get("work_ref") or "") or None
    r.data = {k: d.get(k) for k in ("job", "work_ref", "state", "turn", "path")}
    r.hint_fa = BUSY_FA if d.get("state") == "working" else DONE_FA
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "workshop.run": (WorkshopIn, workshop_run),
    "workshop.stop": (WorkshopStopIn, workshop_stop),
}
T.TOOLS.update(TOOLS)
