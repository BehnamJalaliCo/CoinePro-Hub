"""`cover`: the cover image from the page's cover folder and the content (§30.2).

ChatGPT web (the egress recipe `chatgpt-web`, task `cover`): the cover folder's images (an `Asset` of
kind `cover_folder` in the line's library; `settings.cover_folder` names one by id, else the first) go
into the chat with the brief (the step's prompt, with the content filled in) and the generated image
comes back as a file. No silent switch to another generator: a signed-out ChatGPT, a page that
changed or no image are plain failures. Settings: `cover_folder` (asset id, optional), `max_files`
(default 6).
"""

from __future__ import annotations

import base64
from typing import Any

from hq_api.lines.adapters import _common as C
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

ACCOUNT = "chatgpt-web"
FILE_CAP = 5 * 1024 * 1024
IMAGE_MIMES = ("image/png", "image/jpeg", "image/webp")


def folder_of(ctx: StepContext) -> dict[str, Any]:
    want = C.setting(ctx, "cover_folder")
    folders = [a for a in ctx.library if a.get("kind") == "cover_folder"]
    if want:
        folders = [a for a in folders if str(a.get("id")) == str(want)]
    if not folders:
        raise StepFailed(
            "پوشه‌ی کاور برای این خط انتخاب نشده؛ در کتابخانه یک «پوشه‌ی کاور» اضافه و به خط وصل کن.",
            code="no_cover_folder",
        )
    return folders[0]


class Cover:
    kind = "cover"

    async def run(self, ctx: StepContext) -> StepOutput:
        brief = (ctx.prompt or "").strip()
        if not brief:
            raise StepFailed("متن درخواست کاور خالی است.", code="empty_prompt")
        folder = folder_of(ctx)
        co = await C.company_of(ctx)
        files: list[dict[str, str]] = []
        for fid in list(folder.get("files") or [])[: int(C.setting(ctx, "max_files", 6))]:
            data, row = await C.file_bytes(ctx.hub, co.id, str(fid))
            if str(row["mime"]) in IMAGE_MIMES and len(data) <= FILE_CAP:
                files.append({"name": str(row["name"]), "b64": base64.b64encode(data).decode()})
        if not files:
            raise StepFailed("در پوشه‌ی کاور تصویری قابل‌استفاده نیست.", code="empty_folder")
        got = await C.web_job(
            ctx.hub,
            account=ACCOUNT,
            task="cover",
            prompt=brief,
            timeout_s=C.timeout_of(ctx, 270),
            files=files,
        )
        data, _name, mime = C.decode_b64(got.get("file"))
        if not mime.startswith("image/"):
            raise StepFailed("چیزی که از ChatGPT آمد تصویر نبود.", code="not_image", retry=True)
        fid = await C.store_file(
            ctx.hub, co.id, data, name=f"{ctx.run_ref}-cover.{mime.split('/')[1]}", mime=mime
        )
        return StepOutput(
            file_id=str(fid),
            files=(str(fid),),
            via=ACCOUNT,
            data={"folder": str(folder.get("id")), "from_files": len(files), "mime": mime},
        )


register(Cover())
