"""`publish`: the platform's API, through egress (§30.2). Dry runs answer without leaving.

By the line's platform:
- `instagram_*`: IG-Hub's dedicated API (docs/server-prompts/IGHUB_PUBLISH_API.md). The base URL and
  paths are the Instagram connection's config (`base_url`, `account`, `reel_path`, `story_path`,
  `post_path`, `insights_path`), the bearer token is OpenBao `kv/hq/growth/<company>/instagram`. The
  media and the cover go as the hub's signed `/public/v1/media/<token>` URLs (15 minutes: IG-Hub
  fetches them when the call arrives). A reply `cover_set: false` is returned as `data.cover_set =
  false`, so the line's `deliver` step sends the cover to the owner.
- `youtube_*`: the Data API v3 resumable upload through egress's `youtube` media channel; OAuth client
  id, secret and refresh token in OpenBao `kv/hq/growth/<company>/youtube`.
- `telegram_post`: the Bot API through the same publisher the studio uses (studio_publish.py).
- `site_article`: WordPress REST when `settings.site = {kind: wordpress, base_url, user}` says so
  (the application password in OpenBao `kv/hq/growth/<company>/site`), else a plain failure.

Settings: `kind` (reel | story | post | short | video | article | message), `media_from`,
`cover_from`, `text_from` (input step keys), `publish_at` (ISO) or `delay_min` after `after`'s time,
`privacy` (YouTube). Output `data.published` = {platform, kind, external_id, at, url} for the run.
`insights(ctx, published)` reads the post's figures (Instagram, YouTube); `Publish.insights` is the
engine's entry to it (learning.read_metrics, with the run's list of published entries).
"""

from __future__ import annotations

import contextlib
import json
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import UUID

from hq_api.domain import connections as CN
from hq_api.domain import studio as ST
from hq_api.domain import studio_publish as SP
from hq_api.lines.adapters import _common as C
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

DEFAULT_PATHS = {
    "reel_path": "/v1/publish/reel",
    "story_path": "/v1/publish/story",
    "post_path": "/v1/publish/post",
    "insights_path": "/v1/insights/{id}",
}
KIND_OF_PLATFORM = {
    "instagram_reel": "reel",
    "instagram_story": "story",
    "instagram_post": "post",
    "youtube_short": "short",
    "youtube_long": "video",
    "telegram_post": "message",
    "site_article": "article",
}
IG_CAPTION = 2200
TG_CAPTION = 1024
SHORT_MAX_S = 60.0
YT_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - a public endpoint, not a secret
YT_STATS = "https://www.googleapis.com/youtube/v3/videos?part=statistics&id={id}"
PUBLISH_ERRORS_FA = {
    "platform_limit": "سقف انتشار پلتفرم پر شده؛ بعداً دوباره امتحان می‌شود.",
    "auth_failed": "دسترسی حساب پذیرفته نشد؛ مالک باید اتصال را دوباره بسازد.",
    "no_channel": "حساب اجازه‌ی انتشار در این کانال را ندارد.",
    "publish_error": "پلتفرم انتشار را نپذیرفت.",
    "account_not_configured": "حساب انتشار هنوز تنظیم نشده است.",
}


# ---------------------------------------------------------------- the inputs --
def media_of(ctx: StepContext) -> Any:
    src = C.input_with(ctx, "file_id", C.setting(ctx, "media_from", "render"))
    if src is None or not src.file_id:
        raise StepFailed("فایلی برای انتشار از مرحله‌های قبل نرسید.", code="no_media")
    return src


def cover_of(ctx: StepContext) -> Any:
    key = C.setting(ctx, "cover_from", "cover")
    src = ctx.inputs.get(key)
    return src if src is not None and src.file_id else None


def content_of(ctx: StepContext) -> dict[str, Any]:
    """caption, hashtags, title, description from the build (or the text input)."""
    src = C.input_with(ctx, "data", C.setting(ctx, "text_from", "build"))
    d = (src.data if src is not None else None) or {}
    caption = str(d.get("caption") or (src.text if src is not None else "") or "").strip()
    return {
        "caption": caption,
        "hashtags": list(d.get("hashtags") or []),
        "title": str(d.get("title") or "").strip(),
        "description": str(d.get("description") or "").strip(),
    }


def full_caption(c: dict[str, Any], limit: int) -> str:
    tags = " ".join(c["hashtags"])
    text = c["caption"] if not tags or tags in c["caption"] else f"{c['caption']}\n\n{tags}"
    return text[:limit]


def when_of(ctx: StepContext) -> datetime | None:
    """The time to publish: `publish_at`, else `delay_min` after the `after` step's time."""
    at = C.setting(ctx, "publish_at")
    if at:
        try:
            return datetime.fromisoformat(str(at).replace("Z", "+00:00"))
        except ValueError as exc:
            raise StepFailed("زمان انتشار خوانده نشد.", code="bad_time") from exc
    if C.setting(ctx, "in_min") is not None:  # scheduled: this many minutes from now
        return C.now() + timedelta(minutes=int(C.setting(ctx, "in_min")))
    after = ctx.inputs.get(str(C.setting(ctx, "after", "")))
    base = (after.data or {}).get("published", {}).get("at") if after is not None else None
    if base and C.setting(ctx, "delay_min") is not None:
        return datetime.fromisoformat(str(base).replace("Z", "+00:00")) + timedelta(
            minutes=int(C.setting(ctx, "delay_min"))
        )
    return None


# ----------------------------------------------------------------- the step --
class Publish:
    kind = "publish"

    async def run(self, ctx: StepContext) -> StepOutput:
        platform = ctx.platform
        kind = str(C.setting(ctx, "kind", KIND_OF_PLATFORM.get(platform, "post")))
        at = when_of(ctx)
        if ctx.dry:
            return await self._dry(ctx, platform, kind, at)
        await C.check_unlocked(ctx.hub)
        if platform.startswith("instagram_"):
            pub = await self._instagram(ctx, kind, at)
        elif platform.startswith("youtube_"):
            pub = await self._youtube(ctx, kind, at)
        elif platform == "telegram_post":
            pub = await self._telegram(ctx)
        elif platform == "site_article":
            pub = await self._site(ctx, at)
        else:
            raise StepFailed(
                f"انتشار برای پلتفرم «{platform}» هنوز ساخته نشده.", code="no_platform"
            )
        pub.update(platform=platform, kind=kind, at=(at or C.now()).isoformat())
        extra = {k: pub.pop(k) for k in ("cover_set",) if k in pub}
        return StepOutput(
            text=pub.get("url") or f"منتشر شد ({pub.get('external_id')})",
            via=pub.pop("via"),
            data={"published": pub, **extra},
        )

    async def insights(self, ctx: StepContext, published: list[dict[str, Any]]) -> dict[str, Any]:
        """The engine's 24h/7d read (learning.read_metrics): the run's published entries come as a
        list; the figures are the line's own post's (its platform's kind, not a story that follows
        a reel), else the first entry with an id. The module function reads one entry."""
        ids = [p for p in published if isinstance(p, dict) and p.get("external_id")]
        main = KIND_OF_PLATFORM.get(ctx.platform)
        entry = next((p for p in ids if p.get("kind") == main), ids[0] if ids else None)
        return await insights(ctx, entry) if entry is not None else {}

    # ---------------------------------------------------------------- dry --
    async def _dry(
        self, ctx: StepContext, platform: str, kind: str, at: datetime | None
    ) -> StepOutput:
        media = C.input_with(ctx, "file_id", C.setting(ctx, "media_from", "render"))
        cover = cover_of(ctx)
        return StepOutput(
            text="آزمایشی: چیزی منتشر نشد.",
            via="dry",
            data={
                "dry": True,
                "would_publish": {
                    "platform": platform,
                    "kind": kind,
                    "at": at.isoformat() if at else None,
                    "has_media": bool(media and media.file_id),
                    "has_cover": cover is not None,
                    "caption_chars": len(full_caption(content_of(ctx), IG_CAPTION)),
                },
            },
        )

    # ---------------------------------------------------------- instagram --
    async def _connection(self, ctx: StepContext, kind: str) -> dict[str, Any]:
        co = await C.company_of(ctx)
        async with ctx.hub.db.tx([co.id]) as tx:
            row = await tx.first(
                "SELECT config FROM growth.connections WHERE company_id = :co AND kind = :k",
                co=co.id,
                k=kind,
            )
        cfg = (row or {}).get("config") or {}
        return json.loads(cfg) if isinstance(cfg, str) else dict(cfg)

    async def _instagram(self, ctx: StepContext, kind: str, at: datetime | None) -> dict[str, Any]:
        cfg = await self._connection(ctx, "instagram")
        base = str(cfg.get("base_url") or "").rstrip("/")
        if not base.startswith("https://"):
            raise StepFailed(
                "اتصال اینستاگرام هنوز آدرس API ای‌جی‌هاب را ندارد (در اتصال‌های شرکت ثبت شود).",
                code="not_connected",
            )
        token = str(
            (await C.bao_dict(ctx.hub, f"hq/growth/{ctx.company}/instagram")).get("secret") or ""
        )
        if not token:
            raise StepFailed("توکن API ای‌جی‌هاب برای این شرکت ثبت نشده است.", code="no_token")
        media, cover = media_of(ctx), cover_of(ctx)
        text = content_of(ctx)
        body: dict[str, Any] = {
            "kind": kind,
            "account": cfg.get("account"),
            "client_ref": f"{ctx.run_ref}:{ctx.step.get('key')}",
            "media_url": SP.public_url(ctx.hub, UUID(str(media.file_id))),
            "publish_at": at.isoformat() if at else None,
        }
        if kind != "story":
            body["caption"] = full_caption(text, IG_CAPTION)
            if cover is not None:
                body["cover_url"] = SP.public_url(ctx.hub, UUID(str(cover.file_id)))
        path = str(
            cfg.get(f"{kind}_path") or DEFAULT_PATHS.get(f"{kind}_path", DEFAULT_PATHS["post_path"])
        )
        url = base + path
        ans = await CN.http_for(ctx.hub).request(
            "POST",
            url,
            company=ctx.company,
            headers={"Content-Type": "application/json", "Idempotency-Key": body["client_ref"]},
            json_body=body,
            account={"key": "lines-ighub", "site": urlsplit(url).hostname or "", "secret": token,
                     "inject": {"kind": "bearer"}},
        )  # fmt: skip
        doc = _json(ans.body)
        if ans.outcome != "ok":
            raise StepFailed(
                _egress_fa(ans.code, "ای‌جی‌هاب"), code=str(ans.code or "egress"), retry=True
            )
        if ans.status in (401, 403):
            raise StepFailed("ای‌جی‌هاب توکن را نپذیرفت.", code="auth_failed")
        if ans.status == 429:
            raise StepFailed(PUBLISH_ERRORS_FA["platform_limit"], code="platform_limit", retry=True)
        if not ans.status or not 200 <= ans.status < 300:
            why = str(doc.get("error_fa") or doc.get("message") or doc.get("error") or "")[:200]
            raise StepFailed(
                "ای‌جی‌هاب انتشار را نپذیرفت" + (f": {why}" if why else "."),
                code="publish_error",
                retry=ans.status is not None and ans.status >= 500,
            )
        pub: dict[str, Any] = {
            "external_id": str(doc.get("id") or "") or None,
            "url": doc.get("url") or None,
            "via": "ig-hub",
        }
        if kind != "story" and cover is not None:
            pub["cover_set"] = doc.get("cover_set", True) is not False
        return pub

    # ------------------------------------------------------------ youtube --
    async def _youtube_token(self, ctx: StepContext) -> str:
        s = await C.bao_dict(ctx.hub, f"hq/growth/{ctx.company}/youtube")
        if isinstance(s.get("secret"), str) and s["secret"].lstrip().startswith("{"):
            with contextlib.suppress(ValueError):
                s = {**s, **json.loads(s["secret"])}
        need = ("client_id", "client_secret", "refresh_token")
        if not all(s.get(k) for k in need):
            raise StepFailed(
                "اتصال یوتیوب کامل نیست (شناسه، رمز یا توکن تازه‌سازی ثبت نشده).",
                code="not_connected",
            )
        form = (
            "&".join(f"{k}={quote(str(s[k]), safe='')}" for k in need) + "&grant_type=refresh_token"
        )
        ans = await CN.http_for(ctx.hub).request(
            "POST", YT_TOKEN_URL, company=ctx.company,
            headers={"Content-Type": "application/x-www-form-urlencoded"}, body=form,
        )  # fmt: skip
        access = _json(ans.body).get("access_token")
        if ans.outcome != "ok" or ans.status != 200 or not isinstance(access, str) or not access:
            raise StepFailed(
                "یوتیوب دسترسی را تازه نکرد؛ اتصال باید دوباره ساخته شود.", code="auth_failed"
            )
        return access

    async def _youtube(self, ctx: StepContext, kind: str, at: datetime | None) -> dict[str, Any]:
        media, text = media_of(ctx), content_of(ctx)
        duration = float((media.data or {}).get("duration_s") or 0)
        if kind == "short" and duration > SHORT_MAX_S:
            raise StepFailed("این ویدیو از ۶۰ ثانیه بلندتر است و شورت نمی‌شود.", code="too_long")
        first = text["caption"].splitlines()[0] if text["caption"] else ""
        title = (text["title"] or first)[:100]
        if not title:
            raise StepFailed("عنوان ویدیوی یوتیوب خالی است.", code="no_title")
        desc = text["description"] or full_caption(text, 4900)
        if kind == "short" and "#shorts" not in desc.lower():
            desc = (desc + "\n\n#Shorts").strip()
        tags = [t.lstrip("#") for t in text["hashtags"]][:30]
        access = await self._youtube_token(ctx)
        co = await C.company_of(ctx)
        data, row = await C.file_bytes(ctx.hub, co.id, str(media.file_id))
        payload: dict[str, Any] = {"title": title, "description": desc, "tags": tags,
                                   "privacy": str(C.setting(ctx, "privacy", "public"))}  # fmt: skip
        if at is not None:
            payload["publish_at"] = at.isoformat().replace("+00:00", "Z")
        out = await SP.publisher().call(
            ctx.hub,
            {"channel": "youtube", "method": "upload", "token": access, "payload": payload},
            [(str(row["name"]), data, "video/mp4")],
        )
        del access
        if out.get("outcome") != "ok":
            code = str(out.get("code") or "publish_error")
            raise StepFailed(PUBLISH_ERRORS_FA.get(code, PUBLISH_ERRORS_FA["publish_error"]), code=code,
                             retry=code in ("platform_limit", "publish_error"))  # fmt: skip
        vid = str((out.get("data") or {}).get("video_id") or "")
        url = f"https://www.youtube.com/{'shorts/' if kind == 'short' else 'watch?v='}{vid}"
        return {"external_id": vid, "url": url, "via": "youtube-api"}

    # ----------------------------------------------------------- telegram --
    async def _telegram(self, ctx: StepContext) -> dict[str, Any]:
        src = C.input_with(ctx, "file_id", C.setting(ctx, "media_from", "cover"))
        if src is None or not src.file_id:
            raise StepFailed("پست تلگرام یک تصویر یا ویدیو لازم دارد.", code="no_media")
        key = ST.account_key("telegram", ctx.company)
        acct, token = await SP._account(ctx.hub, key)
        if acct is None or not token:
            raise StepFailed(
                "حساب ربات تلگرام این شرکت تنظیم نشده است.", code="account_not_configured"
            )
        chat = SP.telegram_chat(SP.channel_of(acct))
        if chat is None:
            raise StepFailed(
                "کانال تلگرام این شرکت در حساب ربات ثبت نشده است.", code="account_not_configured"
            )
        co = await C.company_of(ctx)
        data, row = await C.file_bytes(ctx.hub, co.id, str(src.file_id))
        mime = str(row["mime"])
        video = mime == "video/mp4"
        if not video and mime not in ("image/jpeg", "image/png"):
            raise StepFailed("نوع فایل برای تلگرام پذیرفته نیست.", code="bad_media")
        cap = (
            full_caption(content_of(ctx), TG_CAPTION - len(SP.AI_LABEL) - 2) + "\n\n" + SP.AI_LABEL
        ).strip()
        payload: dict[str, Any] = {"chat_id": chat, "caption": cap}
        if video:
            payload.update(video="attach://file0", supports_streaming=True)
        else:
            payload.update(photo="attach://file0")
        out = await SP.publisher().call(
            ctx.hub,
            {"channel": "telegram", "method": "sendVideo" if video else "sendPhoto", "token": token,
             "payload": payload},
            [(str(row["name"]), data, mime)],
        )  # fmt: skip
        del token
        if out.get("outcome") != "ok":
            code = str(out.get("code") or "publish_error")
            raise StepFailed(PUBLISH_ERRORS_FA.get(code, PUBLISH_ERRORS_FA["publish_error"]), code=code,
                             retry=code == "platform_limit")  # fmt: skip
        mid = (out.get("data") or {}).get("message_id")
        name = chat[1:] if chat.startswith("@") else None
        return {
            "external_id": str(mid) if mid is not None else None,
            "url": f"https://t.me/{name}/{mid}" if name and mid is not None else None,
            "via": "telegram-bot",
        }

    # --------------------------------------------------------------- site --
    async def _site(self, ctx: StepContext, at: datetime | None) -> dict[str, Any]:
        site = C.setting(ctx, "site") or {}
        if (
            not isinstance(site, dict)
            or site.get("kind") != "wordpress"
            or not site.get("base_url")
        ):
            raise StepFailed("انتشار در سایت هنوز وصل نشده.", code="not_connected")
        base = str(site["base_url"]).rstrip("/")
        if not base.startswith("https://"):
            raise StepFailed("آدرس سایت باید با https شروع شود.", code="not_connected")
        secret = str(
            (await C.bao_dict(ctx.hub, f"hq/growth/{ctx.company}/site")).get("secret") or ""
        )
        if not secret or not site.get("user"):
            raise StepFailed("نام کاربری یا رمز برنامه‌ی وردپرس ثبت نشده است.", code="no_token")
        src = C.first_input(ctx, C.setting(ctx, "text_from"))
        text = str(src.text if src is not None else "").strip()
        if not text:
            raise StepFailed("متنی برای انتشار در سایت نیست.", code="no_text")
        title = (text.splitlines()[0].lstrip("# ").strip())[:150]
        body: dict[str, Any] = {
            "title": title,
            "content": text,
            "status": "future" if at is not None else str(C.setting(ctx, "status", "publish")),
        }
        if at is not None:
            body["date_gmt"] = at.strftime("%Y-%m-%dT%H:%M:%S")
        url = base + "/wp-json/wp/v2/posts"
        ans = await CN.http_for(ctx.hub).request(
            "POST", url, company=ctx.company, headers={"Content-Type": "application/json"},
            json_body=body,
            account={"key": "lines-site", "site": urlsplit(url).hostname or "", "secret": secret,
                     "inject": {"kind": "basic", "username": str(site["user"])}},
        )  # fmt: skip
        doc = _json(ans.body)
        if ans.outcome != "ok":
            raise StepFailed(
                _egress_fa(ans.code, "سایت"), code=str(ans.code or "egress"), retry=True
            )
        if ans.status in (401, 403):
            raise StepFailed("سایت نام کاربری یا رمز برنامه را نپذیرفت.", code="auth_failed")
        if not ans.status or not 200 <= ans.status < 300:
            raise StepFailed(
                "سایت نوشته را نپذیرفت.", code="publish_error", retry=(ans.status or 0) >= 500
            )
        return {
            "external_id": str(doc.get("id") or "") or None,
            "url": doc.get("link"),
            "via": "wordpress",
        }


# --------------------------------------------------------------- insights --
async def insights(ctx: Any, published: dict[str, Any]) -> dict[str, Any]:
    """The post's figures now (the engine calls it 24 h and 7 d after publishing and keeps the
    answer in Run.metrics). `ctx` has `hub`, `company`; `published` is the run's published entry."""
    platform = str(published.get("platform") or "")
    ext = str(published.get("external_id") or "")
    if not ext:
        return {}
    if platform.startswith("instagram_"):
        co = await ctx.hub.companies.by_code(ctx.company)
        async with ctx.hub.db.tx([co.id]) as tx:
            row = await tx.first(
                "SELECT config FROM growth.connections WHERE company_id = :co AND kind = 'instagram'",
                co=co.id,
            )
        cfg = (row or {}).get("config") or {}
        cfg = json.loads(cfg) if isinstance(cfg, str) else cfg
        base = str(cfg.get("base_url") or "").rstrip("/")
        token = str(
            (await C.bao_dict(ctx.hub, f"hq/growth/{ctx.company}/instagram")).get("secret") or ""
        )
        if not base or not token:
            return {}
        url = base + str(cfg.get("insights_path") or DEFAULT_PATHS["insights_path"]).format(
            id=quote(ext, safe="")
        )
        ans = await CN.http_for(ctx.hub).request(
            "GET", url, company=ctx.company,
            account={"key": "lines-ighub", "site": urlsplit(url).hostname or "", "secret": token,
                     "inject": {"kind": "bearer"}},
        )  # fmt: skip
        doc = _json(ans.body)
        return _numbers(doc) if ans.outcome == "ok" and ans.status == 200 else {}
    if platform.startswith("youtube_"):
        fake = type("Ctx", (), {"hub": ctx.hub, "company": ctx.company})()
        access = await Publish()._youtube_token(fake)
        ans = await CN.http_for(ctx.hub).request(
            "GET", YT_STATS.format(id=quote(ext, safe="")), company=ctx.company,
            account={"key": "lines-youtube", "site": "www.googleapis.com", "secret": access,
                     "inject": {"kind": "bearer"}},
        )  # fmt: skip
        items = _json(ans.body).get("items") or []
        stats = items[0].get("statistics", {}) if items and isinstance(items[0], dict) else {}
        return _numbers(stats)
    return {}


def _numbers(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        k: int(v)
        for k, v in doc.items()
        if isinstance(v, (int, str)) and re.fullmatch(r"\d{1,15}", str(v))
    }


def _json(body: str) -> dict[str, Any]:
    try:
        doc = json.loads(body or "{}")
    except ValueError:
        return {}
    return doc if isinstance(doc, dict) else {}


def _egress_fa(code: str | None, who: str) -> str:
    if code in ("host_not_allowed", "policy_denied", "needs_owner"):
        return f"آدرس {who} در فهرست مجاز خروجی هاب نیست."
    if code == "egress_unavailable":
        return "سرویس خروجی هاب در دسترس نیست."
    return f"{who} جواب نداد."


register(Publish())
