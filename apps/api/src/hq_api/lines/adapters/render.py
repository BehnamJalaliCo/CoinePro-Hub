"""`render`: the spec to a video or an image (§30.2).

`settings.where = "media"` (default): the media studio's renderer (prompt 13, compose profile
`media`). The build's spec becomes a studio item of its kind (a composition stored by the studio's own
checks, the direction, the voice file), a final render job is queued through `studio.queue_render`
and read here until the render worker has produced the file. The item is then put on hold so the
studio's review does not wait on it (the line's own `quality` and seal gate come next).
With the profile off, the step fails plainly.

`settings.where = "company"`: a job on the company's own server through its runner (§26.1b):
`settings.server` (server ref) and `settings.command` (reads the spec JSON on stdin, prints the
produced file's path as its last line). The runner cannot send a binary file back to the hub today,
so this output carries `data.remote_path` and no `file_id`; it is for lines whose publish also runs
on that server.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any
from uuid import UUID

from hq_api.domain import servers as SV
from hq_api.domain import studio as ST
from hq_api.lines.adapters import _common as C
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

KIND_OF_PLATFORM = {
    "instagram_reel": "reel",
    "instagram_story": "story",
    "instagram_post": "post",
    "youtube_short": "reel",
    "youtube_long": "reel",
    "telegram_post": "post",
}
WAIT_S = 600
POLL_S = 5.0
JOB_FINAL = ("done", "failed", "cancelled", "timeout", "expired")


def spec_of(ctx: StepContext) -> dict[str, Any]:
    named = ctx.inputs.get(str(C.setting(ctx, "spec_from", "")))
    src = named or next(
        (o for o in reversed(list(ctx.inputs.values())) if (o.data or {}).get("spec")), None
    )
    spec = ((src.data if src is not None else None) or {}).get("spec")
    if not isinstance(spec, dict) or not spec.get("composition"):
        raise StepFailed("مشخصات ساخت (spec) از مرحله‌ی ساخت نرسید.", code="no_spec")
    return spec


def voice_of(ctx: StepContext) -> str | None:
    key = C.setting(ctx, "voice_from")
    if key and key in ctx.inputs:
        return ctx.inputs[key].file_id
    for out in ctx.inputs.values():
        if out.file_id and str((out.data or {}).get("mime") or "").startswith("audio/"):
            return out.file_id
    return None


class Render:
    kind = "render"

    async def run(self, ctx: StepContext) -> StepOutput:
        spec = spec_of(ctx)
        where = str(C.setting(ctx, "where", "media"))
        if where == "company":
            return await self._company(ctx, spec)
        if where != "media":
            raise StepFailed(
                "جای رندر باید «استودیوی رسانه» یا «سرور شرکت» باشد.", code="bad_where"
            )
        if not getattr(ctx.hub.settings, "media", False):
            raise StepFailed(
                "رندر خاموش است: پروفایل «media» در هاب روشن نیست و مالک باید روشنش کند.",
                code="media_off",
            )
        await C.check_unlocked(ctx.hub)
        return await self._studio(ctx, spec)

    # ---------------------------------------------------------- the studio --
    async def _studio(self, ctx: StepContext, spec: dict[str, Any]) -> StepOutput:
        hub = ctx.hub
        co = await C.company_of(ctx)
        kind = KIND_OF_PLATFORM.get(ctx.platform, "reel")
        voice = voice_of(ctx)
        comp, direction = spec["composition"], spec.get("direction") or {}
        title = str(spec.get("title") or ctx.step.get("title_fa") or ctx.run_ref)[:300]
        async with hub.db.tx([co.id]) as tx:
            row = await tx.one(
                """INSERT INTO media.items (company_id, kind, title_fa, state, one_off, brief_md,
                       direction, voice_file_id, created_by_kind, created_by_code)
                   VALUES (:co, :k, :t, 'rendering', true, :b, CAST(:d AS jsonb), :v, 'service', 'lines')
                   RETURNING id, ref""",
                co=co.id,
                k=kind,
                t=title,
                b=f"خط تولید {ctx.line_ref}، اجرای {ctx.run_ref}",
                d=ST.canonical(
                    {
                        "shots": direction.get("shots") or [],
                        "by": {"kind": "service", "code": "lines"},
                    }
                ),
                v=UUID(voice) if voice else None,
            )
            item = await ST.load_item(tx, row["ref"], lock=True)
            try:
                rep = await ST.check_composition(tx, item, str(comp["format"]), str(comp["source"]))
            except Exception as exc:  # the studio's refusal, told plainly
                raise StepFailed(
                    f"استودیو ترکیب‌بندی را نپذیرفت: {str(exc)[:200]}", code="composition_refused"
                ) from exc
            cid = await tx.scalar(
                """INSERT INTO media.compositions (company_id, item_id, n, format, sha256, source, report,
                       by_kind, by_code)
                   VALUES (:co, :i, 1, :f, :sha, :src, CAST(:rep AS jsonb), 'service', 'lines')
                   RETURNING id""",
                co=co.id,
                i=item["id"],
                f=comp["format"],
                sha=rep.sha256,
                src=comp["source"],
                rep=ST.canonical(rep.as_dict()),
            )
            await tx.exec(
                "UPDATE media.items SET composition_id = :c, assets = :a WHERE id = :id",
                c=cid,
                a=[UUID(a) for a in rep.assets],
                id=item["id"],
            )
            item = await ST.load_item(tx, row["ref"], lock=True)
            queued = await ST.queue_render(tx, hub, item, purpose="final", by="lines")
        if queued is None:
            raise StepFailed("رندر در صف نرفت.", code="not_queued", retry=True)
        job_id = queued["job"]
        waited = 0.0
        limit = float(C.timeout_of(ctx, WAIT_S))
        while True:
            async with hub.db.tx([co.id]) as tx:
                j = await tx.first("SELECT * FROM media.render_jobs WHERE id = :id", id=job_id)
                if j is not None and j["state"] == "done":
                    it = await ST.load_item(tx, row["ref"])
                    fid = it.get("render_file_id")
                    if fid is None:
                        raise StepFailed(
                            "رندر تمام شد ولی فایلی نداشت.", code="no_output", retry=True
                        )
                    await tx.exec(
                        "UPDATE media.items SET state = 'held', state_note_fa = :n WHERE id = :id",
                        n="ساخته‌شده برای خط تولید؛ بازبینی و انتشار با خود خط است.",
                        id=it["id"],
                    )
                    outs = [o for o in (it.get("outputs") or []) if o.get("file_id")]
                    return StepOutput(
                        file_id=str(fid),
                        files=tuple(dict.fromkeys(str(o["file_id"]) for o in outs)) or (str(fid),),
                        via="media-studio",
                        data={"item": it["ref"], "job": str(job_id), "where": "media",
                              "width": (outs[0].get("width") if outs else None),
                              "height": (outs[0].get("height") if outs else None),
                              "duration_s": (outs[0].get("duration_s") if outs else None)},
                    )  # fmt: skip
            if j is not None and j["state"] in ("failed", "cancelled"):
                raise StepFailed(
                    "رندر ناموفق بود: " + _fa_error(str(j.get("error") or "")),
                    code="render_failed",
                    retry="schema" not in str(j.get("error") or ""),
                )
            if waited >= limit:
                raise StepFailed("رندر به موقع تمام نشد.", code="timeout", retry=True)
            await C.sleep(POLL_S)
            waited += POLL_S

    # ---------------------------------------------------------- the company --
    async def _company(self, ctx: StepContext, spec: dict[str, Any]) -> StepOutput:
        server_ref = str(C.setting(ctx, "server", "") or "")
        command = str(C.setting(ctx, "command", "") or "").strip()
        if not server_ref or not command:
            raise StepFailed(
                "برای رندر روی سرور شرکت، «سرور» و «دستور» در تنظیمات مرحله لازم است.",
                code="not_set",
            )
        hub = ctx.hub
        co = await C.company_of(ctx)
        payload = base64.b64encode(json.dumps(spec, ensure_ascii=False).encode()).decode()
        cmd = f"printf %s '{payload}' | base64 -d | {command}"
        async with hub.db.tx([co.id]) as tx:
            try:
                server = await SV.load_server(tx, server_ref, company=ctx.company)
                job = await SV.create_job(
                    tx, server=server, kind="exec", args={"cmd": cmd},
                    actor_kind="service", actor_code="lines",
                    summary=f"رندر {ctx.run_ref}", timeout_s=C.timeout_of(ctx, WAIT_S),
                )  # fmt: skip
            except Exception as exc:  # locked, detached or unknown: told plainly
                raise StepFailed(
                    f"کار روی سرور شرکت شروع نشد: {getattr(exc, 'code', type(exc).__name__)}",
                    code="server_unavailable",
                    retry=True,
                ) from exc
        waited, limit = 0.0, float(C.timeout_of(ctx, WAIT_S))
        while True:
            async with hub.db.tx([co.id]) as tx:
                j = await SV.load_job(tx, job["id"])
            if j["state"] in JOB_FINAL:
                break
            if waited >= limit:
                raise StepFailed("رندر روی سرور شرکت به موقع تمام نشد.", code="timeout", retry=True)
            await C.sleep(POLL_S)
            waited += POLL_S
        if j["state"] != "done":
            raise StepFailed("رندر روی سرور شرکت ناموفق بود.", code="render_failed", retry=True)
        out = str((j.get("result") or {}).get("stdout") or j.get("summary_out") or "").strip()
        path = out.splitlines()[-1].strip() if out else ""
        if not path.startswith("/"):
            raise StepFailed("دستور رندر مسیر فایل را چاپ نکرد.", code="no_path")
        return StepOutput(
            text=path,
            via="company-runner",
            data={"where": "company", "remote_path": path, "job": str(job["id"])},
        )


def _fa_error(error: str) -> str:
    if error.startswith("schema") or "composition" in error:
        return "ترکیب‌بندی با قواعد رندر نخواند."
    if error.startswith("too_large"):
        return "فایل خروجی از سقف پلتفرم بزرگ‌تر شد."
    if error.startswith("runtime_violation"):
        return "ترکیب‌بندی کار ممنوعی کرد."
    return re.sub(r"[^\w\s:.-]", "", error)[:120] or "نامشخص"


register(Render())
