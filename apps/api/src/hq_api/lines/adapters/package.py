"""⟨1.37⟩ `package`: the day's package as one output, by code (contract §59.2, §45.2, §59.6).

Next to the video, its story cut and the cover (the files the build left, else the cover step's
image), code writes three texts:
- `caption.txt`: the script step's caption (its `caption:` part, else the build's own caption.txt);
- `comment.txt` (the session's format, §46) from the flow's reply policy: `keyword:` the word the
  script says aloud, `match: any` when the policy (or, with `per_video`, that video) says so,
  `reply:` the day's DM (`{topic}` filled), `link:` the section's link with the comment path's
  UTM, and ten or more `public:` lines in the order they go out (the video's own first, then the
  policy's, then the hub's pool: site_links.fill_pool);
- `topic.txt`: the day's topic.
The three rules the publish step sends after the post is out (`data.rules`: comment, story_reply,
dm, each with its own UTM and the policy's `cooldown_days`) are made here by the same code.

Settings: `script_from` (the script step; else the input whose output has `parts`), `topic_from`
(else the input of a `topic` step, else the script's `topic:`), `keyword` (when the script names
none), `files_from` (the build's step; else every input's files).
"""

from __future__ import annotations

from typing import Any

from hq_api.domain import session_publish as SPB
from hq_api.domain import site_links as SL
from hq_api.lines.adapters import _common as C
from hq_api.lines.adapters import _flow as FW
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

TEXT_MAX = 64 * 1024
NO_VIDEO_FA = "ویدیویی برای بسته از قدم ساخت نرسید."
NO_CAPTION_FA = "کپشنی برای بسته نیست (نه در سناریو، نه در خروجی ساخت)."


def _parts(ctx: StepContext) -> dict[str, Any]:
    named = ctx.inputs.get(str(C.setting(ctx, "script_from") or ""))
    src = named or next((o for o in ctx.inputs.values() if (o.data or {}).get("parts")), None)
    got = (src.data or {}).get("parts") if src is not None else None
    if isinstance(got, dict):
        return got
    return FW.script_parts(src.text) if src is not None else {}


def _topic(ctx: StepContext, parts: dict[str, Any]) -> str:
    named = ctx.inputs.get(str(C.setting(ctx, "topic_from") or ""))
    src = named or next((o for o in ctx.inputs.values() if (o.data or {}).get("topic")), None)
    text = (src.data or {}).get("topic") or src.text if src is not None else None
    return " ".join(str(text or parts.get("topic") or "").split())[:300]


def _file_ids(ctx: StepContext) -> list[str]:
    named = C.setting(ctx, "files_from")
    keys = [named] if isinstance(named, str) else list(named or ctx.inputs)
    out: list[str] = []
    for k in keys:
        o = ctx.inputs.get(str(k))
        for f in (o.file_id, *o.files) if o is not None else ():
            if f and str(f) not in out:
                out.append(str(f))
    if named:  # the cover step's image too, when the build left none
        for o in ctx.inputs.values():
            for f in (o.file_id, *o.files):
                if f and str(f) not in out:
                    out.append(str(f))
    return out


async def _text(ctx: StepContext, company_id: Any, f: dict[str, Any] | None) -> str:
    if f is None or int(f.get("size") or 0) > TEXT_MAX:
        return ""
    data, _row = await C.file_bytes(ctx.hub, company_id, str(f["id"]))
    return data.decode("utf-8", errors="replace").replace("﻿", "").strip()


class Package:
    kind = "package"

    async def run(self, ctx: StepContext) -> StepOutput:
        parts = _parts(ctx)
        topic = _topic(ctx, parts)
        co = await C.company_of(ctx)
        hub = ctx.hub
        ids = _file_ids(ctx)
        async with hub.db.tx(await hub.companies.ids()) as tx:
            rows = (
                await tx.all(
                    """SELECT id, name, mime, size FROM files.files
                       WHERE id = ANY(CAST(:ids AS uuid[])) AND company_id = :co""",
                    ids=ids,
                    co=co.id,
                )
                if ids
                else []
            )
            flow = await FW.flow_of(tx, ctx)
            run = await FW.run_of(tx, ctx)
            links = await SL.load_links(tx, co.id, ctx.company)
            tz = await FW.zone_of(tx)
        by_name: dict[str, dict[str, Any]] = {}
        for r in sorted((dict(x) for x in rows), key=lambda x: ids.index(str(x["id"]))):
            by_name.setdefault(str(r["name"] or "").strip().lower(), r)
        files = list(by_name.values())
        videos = [f for f in files if str(f["mime"]).startswith("video/")]
        story = next((f for f in videos if str(f["name"]).lower().startswith("story")), None)
        video = next((f for f in videos if f is not story), story)
        if video is None:
            raise StepFailed(NO_VIDEO_FA, code="no_video")
        images = [f for f in files if str(f["mime"]).startswith("image/")]
        cover = next((f for f in images if str(f["name"]).lower().startswith("cover")),
                     images[0] if images else None)  # fmt: skip
        built_comment = SPB.parse_comment(await _text(ctx, co.id, by_name.get("comment.txt")))
        caption = str(parts.get("caption") or "").strip() or await _text(
            ctx, co.id, by_name.get("caption.txt")
        )
        if not caption:
            raise StepFailed(NO_CAPTION_FA, code="no_caption")
        caption = caption[: SPB.CAPTION_MAX]
        topic = topic or (await _text(ctx, co.id, by_name.get("topic.txt"))).split("\n")[0]
        policy = SL.lenient((flow or {}).get("replies"))
        keyword = str(
            parts.get("keyword")
            or C.setting(ctx, "keyword")
            or ((built_comment or {}).get("keywords") or [""])[0]
            or ""
        ).strip()[:100]
        said_any = str(parts.get("match") or "").strip().lower() in SPB.ANY_WORDS | {"any"} or (
            (built_comment or {}).get("match") == "any"
        )
        match = policy.comment.match
        match_any = match == "any" or (match == "per_video" and (said_any or not keyword))
        reply = str(parts.get("reply") or (built_comment or {}).get("reply") or "")
        dm_text = SL.day_dm(policy, topic, reply)
        own = list(parts.get("public") or (built_comment or {}).get("public_replies") or [])
        public = SL.fill_pool(policy.public_pool, first=own)
        name = SL.flow_name((flow or {}).get("ref") or ctx.line_ref)
        day = FW.day_of(run, tz)
        rules = SL.flow_rules(
            policy, links, flow=name, day=day, keyword=keyword or None, match_any=match_any,
            dm_text=dm_text, public=public, story=bool((flow or {}).get("story", True)),
        )  # fmt: skip
        texts = {
            "caption.txt": caption,
            "comment.txt": SL.comment_txt(rules.get("comment"), dm_text, public),
            "topic.txt": (topic or "") + "\n",
        }
        made: dict[str, str] = {}
        for fname, body in texts.items():
            fid = await C.store_file(hub, co.id, body.encode(), name=fname, mime="text/plain")
            made[fname] = str(fid)
        out_files = [str(video["id"])]
        if story is not None and story is not video:
            out_files.append(str(story["id"]))
        if cover is not None:
            out_files.append(str(cover["id"]))
        out_files += list(made.values())
        names = [str(video["name"]), *([str(story["name"])] if story and story is not video else []),
                 *([str(cover["name"])] if cover else []), *made]  # fmt: skip
        return StepOutput(
            text="بسته: " + "، ".join(names),
            file_id=str(video["id"]),
            files=tuple(out_files),
            via="code",
            data={
                "video": str(video["id"]),
                "story": str(story["id"]) if story is not None else None,
                "cover": str(cover["id"]) if cover is not None else None,
                "caption": caption,
                "topic": topic,
                "keyword": keyword or None,
                "match_any": match_any,
                "dm_text": dm_text,
                "public": public,
                "rules": rules,
                "texts": made,
                "day": SL.day_code(day),
                "flow": name,
            },
        )


register(Package())
