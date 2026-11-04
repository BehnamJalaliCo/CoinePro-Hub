"""`deliver`: a file and a line of text to the owner (§30.2). Dry runs answer without leaving.

Two ways, both the hub's own: an app card (a notification of level `report` that opens the run,
`owner_action`) and, when the hub's Telegram backup channel is configured, the same line in the
owner's Telegram (that channel carries a line and «open the app», never a file or an action: the
file is on the card's run). Sending the file itself into the owner's private Telegram chat would need
an egress method for it (the media path posts to channels only) and is not built.

Settings: `file_from` (input step key of the file, default: the last input with a file),
`only_if` = `cover_not_set` (do nothing unless the publish step named in `check` answered
`cover_set = false`; the `instagram_reel` template uses it), `check` (that step's key, default
`publish`). The line: the step's prompt, else a plain default naming the file's step.
"""

from __future__ import annotations

from typing import Any

from hq_api.domain import notify
from hq_api.lines.adapters import _common as C
from hq_api.lines.base import StepContext, StepOutput, register

DEFAULT_LINE = "فایل «{title}» برای خط «{line}» آماده است و باید دستی منتشر یا تکمیل شود."
COVER_LINE = (
    "کاور ریل خط «{line}» را اینستاگرام نپذیرفت؛ فایل کاور را از اجرای خط بردار و دستی بگذار."
)


def skipped(ctx: StepContext) -> bool:
    """`only_if` is not met: nothing to deliver."""
    if C.setting(ctx, "only_if") != "cover_not_set":
        return False
    checked = ctx.inputs.get(str(C.setting(ctx, "check", "publish")))
    return (checked.data or {}).get("cover_set") is not False if checked is not None else True


class Deliver:
    kind = "deliver"

    async def run(self, ctx: StepContext) -> StepOutput:
        if skipped(ctx):
            return StepOutput(
                text="لازم نبود: کاور گذاشته شد.", via="deliver", data={"skipped": True}
            )
        src = C.input_with(ctx, "file_id", C.setting(ctx, "file_from"))
        title = str(ctx.step.get("title_fa") or ctx.run_ref)
        default = COVER_LINE if C.setting(ctx, "only_if") == "cover_not_set" else DEFAULT_LINE
        line = (ctx.prompt or "").strip() or default.format(
            title=title, line=str(ctx.channel.get("subject") or ctx.line_ref)
        )
        data: dict[str, Any] = {
            "line": line,
            "file_id": src.file_id if src is not None else None,
            "run": ctx.run_ref,
        }
        if ctx.dry:
            return StepOutput(text="آزمایشی: به مالک چیزی فرستاده نشد.\n" + line, via="dry",
                              data={**data, "dry": True})  # fmt: skip
        await C.check_unlocked(ctx.hub)
        hub = ctx.hub
        co = await C.company_of(ctx)
        async with hub.db.tx(await hub.companies.ids()) as tx:
            row = await notify.raise_notification(
                tx,
                company_id=co.id,
                company_code=co.code,
                level="report",
                title_fa=line[:200],
                body_fa=f"اجرای {ctx.run_ref} را در اپ باز کن؛ فایل همان‌جاست.",
                link_kind="line_run",
                link_ref=ctx.run_ref,
                source_kind="service",
                source_code="lines",
                owner_action=True,
            )
        if row.get("push_now"):
            await notify.deliver_pending(hub, [row["id"]])
        telegram = False
        channels = getattr(hub, "channels", None)
        if channels is not None and channels.telegram.configured:
            from hq_api.channels import PushMessage

            sent = await channels.push(
                PushMessage(
                    title=line[:200],
                    level="report",
                    company=co.code,
                    link_kind="line_run",
                    link_ref=ctx.run_ref,
                )
            )
            telegram = bool(sent.get("telegram"))
        return StepOutput(
            text=line, via="deliver", data={**data, "card": str(row["id"]), "telegram": telegram}
        )


register(Deliver())
