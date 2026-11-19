"""⟨2026-11-19⟩ A page's own Telegram channel: posts made for Telegram, not the reels' copies.

The owner (2026-11-19) for t.me/behnamjalali_tech: «فعالیت به شدت قوی … با محتوای مخصوص خود تلگرام».
A `tg_post` flow's session (the kit, e.g. automations/kits/bjtech-telegram) delivers the day's
package in out/: `telegram.txt` (JSON: the posts, each at its Tehran hour) and the files it names. Then:

    check()   the package as Telegram takes it: its HTML subset (b i u s code pre a blockquote
              tg-spoiler …, https links only), the visible lengths in UTF-16 units (a message 4096,
              a caption 1024), link buttons only, polls (2-10 options, a quiz names its answer),
              each named file present, of its kind and size, the hours in order on the day, and
              never a topic the channel has had (the hub's no-repeat rule, per channel). A package
              with a fault is never half sent: the session is told every fault, once per turn.
    queue()   each post becomes a publication (media.publications: channel telegram, kind tg_post,
              state scheduled at its hour; a breaking post's hour is now); the session closes.
    tick()    the worker, every minute (hq-telegram-tick): the bot's own rights in the channel are
              read first (getMe, then getChatMember of the bot: an administrator that may post);
              while it may not, nothing is sent and the posts wait, said on the connection; once it
              may, each due post goes out through egress (POST /v1/media/publish, the Bot API), once
              (a post is marked `publishing` before its first call and never sent twice), and a post
              whose hour is long past when it could go (STALE) is cancelled with its reason.

The bot's token is the company's Telegram connection's secret (kv/hq/growth/<CODE>/telegram: the
owner's app route, the worker reads it); the page's channel is that connection's `channels` entry
whose `page` is the flow's account. Rule-based: no model, no outside call but the Bot API through
egress.
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from zoneinfo import ZoneInfo

from hq_api import audit
from hq_api.db import Tx
from hq_api.principal import Principal

log = logging.getLogger("hq_api.tg_posts")
_WHO = Principal(kind="service", code="telegram", role="service")

TG_FILE = "telegram.txt"
# ⟨2026-11-19⟩ the workshop's runner delivers .txt, never .json (outbox.TYPES): the manifest is the same
# JSON in telegram.txt; a telegram.txt (a runner that delivers it) is read too
TG_FILES = (TG_FILE, "telegram.json")
TG_FILE_MAX = 256 * 1024
TEHRAN = ZoneInfo("Asia/Tehran")
CONNECTION = "telegram"
POSTS_MAX, PARTS_MAX = 12, 4
GAP = timedelta(minutes=15)  # between two posts of a day
TEXT_MAX, CAPTION_MAX, BUTTON_TEXT = 4096, 1024, 64
BUTTON_ROWS, BUTTONS_PER_ROW = 4, 3
POLL_QUESTION, POLL_OPTION, POLL_EXPLANATION = 300, 100, 200
TOPIC_MAX = 300
PHOTO_MAX, FILE_MAX = 10 * 1024 * 1024, 50 * 1024 * 1024  # the Bot API's own upload limits
KINDS = {
    "photo": ("image/jpeg", "image/png"),
    "video": ("video/mp4",),
    "voice": ("audio/ogg",),
    "document": ("application/pdf",),
}
TYPES = (
    "brief",
    "tool",
    "prompt",
    "poll",
    "table",
    "clip",
    "voice",
    "tip",
    "longread",
    "breaking",
    "post",
)
# a post later than this after its hour when it could finally go is not sent (old news hurts)
STALE = {"breaking": timedelta(hours=3), "brief": timedelta(hours=4)}
STALE_DEFAULT = timedelta(hours=10)
STUCK = timedelta(minutes=15)  # `publishing` this long: its call never answered (never resent)
RIGHTS_OK_TTL, RIGHTS_NO_TTL = timedelta(hours=6), timedelta(minutes=5)
LINK = re.compile(r"^https://[^\s<>\"']{3,1000}$")
HM = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
CHAT = re.compile(r"^(@[A-Za-z][A-Za-z0-9_]{4,31}|-100[0-9]{6,15})$")
BOT_TOKEN = re.compile(r"^[0-9]{5,16}:[A-Za-z0-9_-]{30,64}$")
NS = uuid.UUID("6f1c7d0e-3b7a-4e55-9a51-1f0c4b7e2a19")  # a post's publication key (chain[1])

WAIT_RIGHTS_FA = "منتظر دسترسی ربات: ربات باید مدیر کانال باشد با اجازه‌ی «Post Messages»"
WAIT_TOKEN_FA = "منتظر توکن ربات تلگرام (اتصال تلگرام شرکت در اپ)"  # noqa: S105 - a sentence, not a secret
STALE_FA = "منتشر نشد: زمانش گذشته بود ({why})"
STUCK_FA = "جواب تلگرام نرسید؛ شاید رفته باشد، دوباره فرستاده نمیشود"
FAILED_FA = "تلگرام نپذیرفت: {why}"
PACKAGE_FA = (
    "بسته‌ی تلگرام امروز پذیرفته نشد و هیچ پستی نرفت. این‌ها را درست کن، telegram.txt و فایل‌ها را "
    "دوباره در out/ بگذار و تحویل بده (قاعده‌ها: کیت، بخش «telegram.txt»):\n{errors}"
)
NO_CHANNEL_FA = "کانال تلگرام این پیج در اتصال تلگرام شرکت نیست (channels: page، chat)"


# ------------------------------------------------------------------ the HTML Telegram reads --
ALLOWED = {
    "b": (),
    "strong": (),
    "i": (),
    "em": (),
    "u": (),
    "ins": (),
    "s": (),
    "strike": (),
    "del": (),
    "code": ("class",),
    "pre": (),
    "a": ("href",),
    "blockquote": ("expandable",),
    "tg-spoiler": (),
    "span": ("class",),
}


def utf16(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


class _Html(HTMLParser):
    """Telegram's HTML subset (https://core.telegram.org/bots/api#html-style): its tags only, its
    attributes only, links https only, every tag closed in order; the visible text kept."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.open: list[str] = []
        self.errors: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ALLOWED:
            self.errors.append(f"تگ <{tag}> در HTML تلگرام نیست")
            return
        for k, v in attrs:
            if k not in ALLOWED[tag]:
                self.errors.append(f"ویژگی {k} روی <{tag}> مجاز نیست")
            elif tag == "a" and not LINK.match(str(v or "")):
                self.errors.append(f"لینک <a> باید https باشد: {str(v)[:60]}")
            elif tag == "span" and v != "tg-spoiler":
                self.errors.append('<span> فقط با class="tg-spoiler"')
            elif tag == "code" and not re.fullmatch(r"language-[a-z0-9_+-]{1,30}", str(v or "")):
                self.errors.append("class روی <code> فقط language-…")
        if tag == "a" and not any(k == "href" for k, _ in attrs):
            self.errors.append("<a> بی href")
        self.open.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag not in ALLOWED:
            return
        if not self.open or self.open[-1] != tag:
            self.errors.append(f"</{tag}> بی‌جا بسته شده")
            return
        self.open.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.errors.append(f"<{tag}/> در HTML تلگرام نیست (برای خط تازه، خود خط تازه)")

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def read_html(raw: str) -> tuple[str, list[str]]:
    """(the visible text, the faults) of a post's HTML."""
    p = _Html()
    try:
        p.feed(raw)
        p.close()
    except Exception as exc:  # noqa: BLE001 - an HTML the parser cannot read is a fault, said
        return "", [f"HTML خوانده نشد: {type(exc).__name__}"]
    errors = list(dict.fromkeys(p.errors))
    if p.open:
        errors.append("تگ‌های بازمانده: " + "، ".join(f"<{t}>" for t in p.open))
    bare = re.search(r"&(?!(lt|gt|amp|quot|#[0-9]{1,7}|#x[0-9a-fA-F]{1,6});)", raw)
    if bare:
        errors.append("«&» تنها در متن باید &amp; نوشته شود")
    return "".join(p.text), errors  # (the parser decoded the character references)


# ------------------------------------------------------------------ the package --
@dataclass
class Post:
    n: int
    type: str
    topic: str
    at: datetime | None  # None: now (a breaking post)
    parts: list[dict[str, Any]] = field(default_factory=list)

    def files(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in self.parts:
            for k in ("photo", "video", "voice", "document"):
                if m.get(k):
                    out.append(m[k])
            out.extend(m.get("photos") or [])
        return out


def _buttons(raw: Any, where: str, errors: list[str]) -> list[list[dict[str, str]]]:
    if raw in (None, []):
        return []
    rows = raw if isinstance(raw, list) and raw and isinstance(raw[0], list) else [raw]
    if not isinstance(raw, list) or not 1 <= len(rows) <= BUTTON_ROWS:
        errors.append(f"{where}: دکمه‌ها حداکثر {BUTTON_ROWS} ردیف")
        return []
    out: list[list[dict[str, str]]] = []
    for row in rows:
        if not isinstance(row, list) or not 1 <= len(row) <= BUTTONS_PER_ROW:
            errors.append(f"{where}: هر ردیف ۱ تا {BUTTONS_PER_ROW} دکمه")
            continue
        got = []
        for b in row:
            if not isinstance(b, dict) or set(b) != {"text", "url"}:
                errors.append(f"{where}: هر دکمه فقط text و url")
                continue
            text, url = str(b["text"]).strip(), str(b["url"]).strip()
            if not text or utf16(text) > BUTTON_TEXT:
                errors.append(f"{where}: متن دکمه ۱ تا {BUTTON_TEXT} نویسه")
            if not LINK.match(url):
                errors.append(f"{where}: لینک دکمه باید https باشد ({url[:60]})")
            got.append({"text": text, "url": url})
        out.append(got)
    return out


def _file(
    name: Any, kind: str, files: dict[str, dict[str, Any]], where: str, errors: list[str]
) -> dict[str, Any] | None:
    if not isinstance(name, str) or not NAME.fullmatch(name):
        errors.append(f"{where}: نام فایل {kind} درست نیست")
        return None
    f = files.get(name.lower())
    if f is None:
        errors.append(f"{where}: فایل {name} در out/ نیست")
        return None
    if str(f["mime"]) not in KINDS[kind]:
        errors.append(f"{where}: {name} از نوع {kind} نیست ({f['mime']})")
        return None
    cap = PHOTO_MAX if kind == "photo" else FILE_MAX
    if not 0 < int(f["size"] or 0) <= cap:
        errors.append(f"{where}: {name} بزرگ‌تر از {cap // (1024 * 1024)} مگابایت است")
        return None
    return {"name": str(f["name"]), "file_id": str(f["id"]), "mime": str(f["mime"])}


def _part(
    m: Any, files: dict[str, dict[str, Any]], where: str, errors: list[str], last: bool
) -> dict[str, Any] | None:
    if not isinstance(m, dict):
        errors.append(f"{where}: باید یک شیء JSON باشد")
        return None
    mains = [k for k in ("photo", "photos", "video", "voice", "document", "poll") if m.get(k)]
    if len(mains) > 1:
        errors.append(f"{where}: هر پیام فقط یکی از photo، photos، video، voice، document یا poll")
        return None
    main = mains[0] if mains else "text"
    out: dict[str, Any] = {"kind": main}
    text = m.get("text")
    if text is not None and (not isinstance(text, str) or not text.strip()):
        errors.append(f"{where}: text خالی است")
        text = None
    if main == "text" and text is None:
        errors.append(f"{where}: پیام بی متن و بی فایل")
        return None
    if text is not None:
        if main == "poll":
            errors.append(f"{where}: نظرسنجی متن ندارد (سؤال و گزینه‌ها و توضیح خودش)")
        visible, faults = read_html(text)
        errors.extend(f"{where}: {e}" for e in faults)
        cap = TEXT_MAX if main == "text" else CAPTION_MAX
        if utf16(visible) > cap:
            errors.append(f"{where}: متن {utf16(visible)} نویسه است؛ حداکثر {cap}")
        out["text"] = text
    if main in ("photo", "video", "voice", "document"):
        got = _file(m.get(main), "photo" if main == "photo" else main, files, where, errors)
        if got:
            out[main] = got
    elif main == "photos":
        pics = m.get("photos")
        if not isinstance(pics, list) or not 2 <= len(pics) <= 10:
            errors.append(f"{where}: آلبوم ۲ تا ۱۰ عکس")
        else:
            got_all = [_file(p, "photo", files, where, errors) for p in pics]
            out["photos"] = [g for g in got_all if g]
    elif main == "poll":
        out["poll"] = _poll(m["poll"], where, errors)
    buttons = _buttons(m.get("buttons"), where, errors)
    if buttons:
        if main in ("photos", "poll"):
            errors.append(f"{where}: آلبوم و نظرسنجی دکمه نمیگیرند")
        elif not last:
            errors.append(f"{where}: دکمه‌ها فقط روی آخرین پیام پست")
        else:
            out["buttons"] = buttons
    preview = m.get("preview", False)
    if main == "text":
        if preview not in (False, True) and not (isinstance(preview, str) and LINK.match(preview)):
            errors.append(f"{where}: preview یا true/false است یا یک لینک https")
        out["preview"] = preview
    if m.get("silent") is True:
        out["silent"] = True
    if m.get("above") is True and main in ("photo", "video"):
        out["above"] = True
    extra = set(m) - {
        "photo",
        "photos",
        "video",
        "voice",
        "document",
        "poll",
        "text",
        "buttons",
        "preview",
        "silent",
        "above",
    }
    if extra:
        errors.append(f"{where}: کلیدهای ناشناخته: {', '.join(sorted(extra))}")
    return out


def _poll(raw: Any, where: str, errors: list[str]) -> dict[str, Any]:
    p = raw if isinstance(raw, dict) else {}
    q = str(p.get("question") or "").strip()
    opts = [str(o).strip() for o in p.get("options") or [] if str(o).strip()]
    if not q or utf16(q) > POLL_QUESTION:
        errors.append(f"{where}: سؤال نظرسنجی ۱ تا {POLL_QUESTION} نویسه")
    if not 2 <= len(opts) <= 10 or any(utf16(o) > POLL_OPTION for o in opts):
        errors.append(f"{where}: نظرسنجی ۲ تا ۱۰ گزینه، هر کدام حداکثر {POLL_OPTION} نویسه")
    if len(set(opts)) != len(opts):
        errors.append(f"{where}: گزینه‌ی تکراری")
    out: dict[str, Any] = {"question": q, "options": opts}
    if "quiz" in p:
        quiz = p["quiz"]
        if not isinstance(quiz, int) or isinstance(quiz, bool) or not 0 <= quiz < len(opts):
            errors.append(f"{where}: quiz شماره‌ی گزینه‌ی درست است (از ۰)")
        else:
            out["quiz"] = quiz
        if p.get("explanation"):
            visible, faults = read_html(str(p["explanation"]))
            errors.extend(f"{where}: توضیح نظرسنجی: {e}" for e in faults)
            if utf16(visible) > POLL_EXPLANATION:
                errors.append(f"{where}: توضیح نظرسنجی حداکثر {POLL_EXPLANATION} نویسه")
            out["explanation"] = str(p["explanation"])
    elif p.get("multiple") is True:
        out["multiple"] = True
    return out


def fold(text: str) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", " ", text or "")).lower()
    t = t.translate(str.maketrans("يكۀة‌", "یکههه"))
    return " ".join(re.sub(r"[^\w\s]", " ", t).split())


def check(
    doc: Any,
    files: dict[str, dict[str, Any]],
    *,
    day: date,
    first: datetime | None,
    asap: bool = False,
    done: list[str] | None = None,
) -> tuple[list[Post], list[str]]:
    """The day's posts as they will go, or every fault (Persian, for the session). `first`: the
    flow's hour (no post before it); `asap`: a breaking package (one post, at once); `done`: the
    channel's topics already out or queued (never one again)."""
    errors: list[str] = []
    raw_posts = doc.get("posts") if isinstance(doc, dict) else None
    if not isinstance(raw_posts, list) or not raw_posts:
        return [], ['telegram.txt باید {"posts": [...]} با دست‌کم یک پست باشد']
    if len(raw_posts) > (1 if asap else POSTS_MAX):
        errors.append(f"حداکثر {1 if asap else POSTS_MAX} پست در یک بسته")
    seen = {fold(t) for t in done or [] if fold(t)}
    posts: list[Post] = []
    last_at: datetime | None = None
    topics: set[str] = set()
    for i, raw in enumerate(raw_posts[: (1 if asap else POSTS_MAX)], 1):
        where = f"پست {i}"
        if not isinstance(raw, dict):
            errors.append(f"{where}: باید یک شیء JSON باشد")
            continue
        kind = str(raw.get("type") or "post")
        if kind not in TYPES:
            errors.append(f"{where}: type یکی از {', '.join(TYPES)}")
        topic = " ".join(str(raw.get("topic") or "").split())
        if not topic or len(topic) > TOPIC_MAX:
            errors.append(f"{where}: topic (موضوع یک‌خطی، حداکثر {TOPIC_MAX} نویسه) لازم است")
        elif fold(topic) in seen or fold(topic) in topics:
            errors.append(f"{where}: موضوع «{topic[:80]}» در این کانال تکراری است")
        topics.add(fold(topic))
        at: datetime | None = None
        if not asap:
            hm = str(raw.get("at") or "")
            if not HM.fullmatch(hm):
                errors.append(f"{where}: at به شکل ۰۸:۳۰ (وقت تهران)")
            else:
                at = datetime.combine(day, datetime.strptime(hm, "%H:%M").time(), TEHRAN)
                if first is not None and at < first:
                    errors.append(f"{where}: {hm} پیش از ساعت شروع اتوماسیون است")
                if last_at is not None and at < last_at + GAP:
                    errors.append(f"{where}: دست‌کم {GAP.seconds // 60} دقیقه بعد از پست قبلی")
                last_at = at
        raw_parts = raw.get("parts")
        msgs = raw_parts if isinstance(raw_parts, list) else [raw]
        if not 1 <= len(msgs) <= PARTS_MAX:
            errors.append(f"{where}: parts ۱ تا {PARTS_MAX} پیام")
            msgs = msgs[:PARTS_MAX]
        parts = []
        for k, m in enumerate(msgs, 1):
            body = (
                {x: v for x, v in m.items() if x not in ("n", "type", "topic", "at", "parts")}
                if isinstance(m, dict)
                else m
            )
            got = _part(
                body,
                files,
                where if len(msgs) == 1 else f"{where}، پیام {k}",
                errors,
                last=k == len(msgs),
            )
            if got:
                parts.append(got)
        posts.append(Post(n=i, type=kind, topic=topic, at=at, parts=parts))
    return posts, list(dict.fromkeys(errors))


def visible_text(post: Post) -> str:
    """What the post says (the app's caption and search; never the raw HTML)."""
    out = []
    for m in post.parts:
        if m.get("text"):
            out.append(read_html(m["text"])[0])
        if m.get("poll"):
            out.append(
                m["poll"]["question"] + "\n" + "\n".join(f"• {o}" for o in m["poll"]["options"])
            )
    return "\n\n".join(x.strip() for x in out if x.strip())[:5000]


# ------------------------------------------------------------------ the Bot API calls --
def _markup(rows: list[list[dict[str, str]]]) -> dict[str, Any]:
    return {
        "inline_keyboard": [[{"text": b["text"], "url": b["url"]} for b in row] for row in rows]
    }


def calls(
    post: dict[str, Any], chat: str
) -> list[tuple[str, dict[str, Any], list[dict[str, Any]]]]:
    """(method, payload, files in part order) of each message of a stored post."""
    out = []
    for m in post.get("parts") or []:
        kind = m["kind"]
        p: dict[str, Any] = {"chat_id": chat}
        files: list[dict[str, Any]] = []
        if kind == "text":
            method = "sendMessage"
            p["text"] = m["text"]
            preview = m.get("preview", False)
            p["link_preview_options"] = (
                {"is_disabled": True}
                if preview is False
                else {"url": preview, "prefer_large_media": True}
                if isinstance(preview, str)
                else {"prefer_large_media": True}
            )
        elif kind == "photos":
            method = "sendMediaGroup"
            files = list(m["photos"])
            p["media"] = [
                {
                    "type": "photo",
                    "media": f"attach://file{i}",
                    **(
                        {"caption": m["text"], "parse_mode": "HTML"}
                        if i == 0 and m.get("text")
                        else {}
                    ),
                }
                for i in range(len(files))
            ]
        elif kind == "poll":
            method = "sendPoll"
            q = m["poll"]
            p.update(question=q["question"], options=list(q["options"]), is_anonymous=True)
            if "quiz" in q:
                p.update(type="quiz", correct_option_id=q["quiz"])
                if q.get("explanation"):
                    p.update(explanation=q["explanation"], explanation_parse_mode="HTML")
            elif q.get("multiple"):
                p["allows_multiple_answers"] = True
        else:
            method = {
                "photo": "sendPhoto",
                "video": "sendVideo",
                "voice": "sendVoice",
                "document": "sendDocument",
            }[kind]
            files = [m[kind]]
            p[kind] = "attach://file0"
            if m.get("text"):
                p["caption"] = m["text"]
            if kind == "video":
                p["supports_streaming"] = True
            if m.get("above"):
                p["show_caption_above_media"] = True
        if m.get("text") and kind not in ("photos", "poll"):
            p["parse_mode"] = "HTML"
        if m.get("buttons"):
            p["reply_markup"] = _markup(m["buttons"])
        if m.get("silent"):
            p["disable_notification"] = True
        out.append((method, p, files))
    return out


# ------------------------------------------------------------------ the channel --
async def channel_of(tx: Tx, company_id: Any, page: str) -> str | None:
    """The page's channel in its company's Telegram connection (`channels[].page` = the account)."""
    cfg = await tx.scalar(
        "SELECT config FROM growth.connections WHERE company_id = :co AND kind = :k",
        co=company_id,
        k=CONNECTION,
    )
    cfg = json.loads(cfg) if isinstance(cfg, str) else (cfg or {})
    for ch in cfg.get("channels") or []:
        if (
            isinstance(ch, dict)
            and str(ch.get("page") or "") == page
            and CHAT.fullmatch(str(ch.get("chat") or ""))
        ):
            return str(ch["chat"])
    return None


async def connected(tx: Tx, company_id: Any, page: str) -> str | None:
    """None when the page's channel and the bot's token are set, else why not (Persian)."""
    row = await tx.first(
        "SELECT secret_set FROM growth.connections WHERE company_id = :co AND kind = :k",
        co=company_id,
        k=CONNECTION,
    )
    if row is None or not row["secret_set"]:
        return WAIT_TOKEN_FA
    if await channel_of(tx, company_id, page) is None:
        return NO_CHANNEL_FA
    return None


# ------------------------------------------------------------------ the session's order --
REELS_SQL = """SELECT coalesce(nullif(topic_fa, ''), title_fa) AS t FROM media.publications
    WHERE account = :a AND channel = 'instagram' AND kind IN ('reel', 'story')
      AND state IN ('scheduled', 'publishing', 'published') AND at > now() - interval '3 days'
    GROUP BY 1 ORDER BY max(at) DESC LIMIT 12"""


async def reel_topics(tx: Tx, account: str) -> list[str]:
    """The page's own reels and stories of the last three days (a Telegram post never copies them)."""
    return [
        " ".join(str(r["t"]).split())[:90] for r in await tx.all(REELS_SQL, a=account) if r["t"]
    ]


def brief(flow: Any, day: date, at: datetime, done: list[str] | None, ig: list[str] | None) -> str:
    """A Telegram day's order: the kit makes the day's posts; the hub checks them, keeps each for its
    hour and sends it to the channel."""
    from hq_api.domain import flows as FL

    reels = (
        "\nریلزها و استوری‌های اینستاگرام همین پیج در سه روز اخیر (کپی آن‌ها در تلگرام ممنوع؛ همان خبر فقط "
        "با زاویه و محتوای مخصوص تلگرام، عمیق‌تر یا کاربردی‌تر): " + "، ".join(f"«{t}»" for t in ig)
        if ig
        else ""
    )
    return (
        f"{flow.title_fa}، {FL.fa_day(day)} (اولین پست {FL.at_fa(at)} به وقت تهران)\n\n"
        "این فرمان را اتوماسیون هاب داده است، به دستور مدیر کل. کار خودکار است: از کسی چیزی نپرس، "
        "order.ask نزن و منتظر تأیید نمان.\n"
        f"روند، قاعده‌ها و ابزارها در کیت ثابت است: {flow.kit}/README.md. اول همان را بخوان و قدم‌به‌قدم "
        "انجام بده؛ هیچ فایلی از کیت را عوض نکن.\n"
        "تحویل: out/telegram.txt (پست‌های امروز، هر کدام با ساعتش به وقت تهران) و همه‌ی فایل‌هایی که نام "
        "برده (عکس، ویدیو، صدا، PDF)؛ telegram.txt آخر از همه. ستاد بسته را بررسی میکند، هر پست را در "
        "ساعت خودش در کانال تلگرام منتشر میکند و این جلسه را میبندد. اگر بسته ایرادی داشت، فهرست کامل "
        "ایرادها به همین جلسه برمیگردد و هیچ پستی نیمه‌کاره نمیرود."
        + FL.no_repeat(done).replace("این پیج", "این کانال تلگرام")
        + reels
        + (f"\n\n{flow.note_fa}" if flow.note_fa else "")
    )


# ------------------------------------------------------------------ queue (the flow's package) --
async def read_manifest(hub: Any, f: dict[str, Any]) -> Any:
    if int(f["size"] or 0) > TG_FILE_MAX or hub is None:
        return None
    data: bytes = await hub.storage.get(f["storage_key"])
    try:
        return json.loads(data[:TG_FILE_MAX].decode("utf-8").lstrip("﻿"))
    except (UnicodeDecodeError, ValueError):
        return None


async def done_topics(tx: Tx, account: str) -> list[str]:
    from hq_api.domain import flows as FL

    rows = await tx.all(FL.DONE_SQL, a=account, k=["tg_post"])
    return [str(r["t"]) for r in rows if r["t"]]


async def queue(
    tx: Tx, hub: Any, w: dict[str, Any], meta: dict[str, Any], pkg: dict[str, Any]
) -> str:
    """The day's package in: checked; every post a scheduled publication (or the session told every
    fault and woken, the run left open); the session closes. 'queued' | 'open'."""
    from hq_api.domain import flows as FL
    from hq_api.domain import order_report as OR
    from hq_api.domain import publications as P

    doc = await read_manifest(hub, pkg["manifest"])
    day = date.fromisoformat(str(meta["day"]))
    first = datetime.fromisoformat(str(meta["publish_at"])) if not meta.get("asap") else None
    done = await done_topics(tx, str(meta.get("account") or ""))
    posts: list[Post] = []
    if doc is None:
        errors = ["telegram.txt خوانده نشد (JSON درست، UTF-8، حداکثر ۲۵۶ کیلوبایت)"]
    else:
        posts, errors = check(
            doc, pkg["files"], day=day, first=first, asap=bool(meta.get("asap")), done=done
        )
    order = str(meta.get("order") or "") or None
    if errors:
        if meta.get("tg_errors_for") == str(pkg["manifest"]["id"]):
            return "open"  # (told once for this package; a new telegram.txt is checked again)
        meta["tg_errors_for"] = str(pkg["manifest"]["id"])
        await tx.exec(
            "UPDATE work.work SET run_meta = jsonb_set(run_meta, '{flow}', CAST(:m AS jsonb)) WHERE id = :w",
            w=w["id"],
            m=json.dumps(meta, ensure_ascii=False, default=str),
        )
        rep = await OR.ensure(tx, order) if order else None
        text = PACKAGE_FA.format(errors="\n".join(f"- {e}" for e in errors[:30]))
        if rep is not None:
            await OR._append_steps(tx, rep["id"], [OR._step("سامانه", text[:3900])])
        await tx.scalar(
            "SELECT work.wake_assignee(:w, :r)", w=w["id"], r=f"tg_package:{order or w['ref']}"
        )
        return "open"
    chat = await channel_of(tx, w["company_id"], str(meta.get("account") or ""))
    now = datetime.now(UTC)
    made = []
    for post in posts:
        at = now if post.at is None else post.at.astimezone(UTC)
        stored = {"type": post.type, "parts": post.parts}
        files = [{**f, "role": "attachment"} for f in post.files()]
        thumb = next((f["file_id"] for f in post.files() if f["mime"].startswith("image/")), None)
        caption = visible_text(post)
        title = P.first_line(post.topic) or P.first_line(caption) or "پست تلگرام"
        ref = await tx.scalar(
            P.INSERT_SQL,
            co=w["company_id"],
            channel="telegram",
            account=str(meta.get("account") or ""),
            kind="tg_post",
            state="scheduled",
            note=None,
            scheduled_at=at,
            published_at=None,
            url=None,
            ext=None,
            title=title[:200],
            topic=post.topic[:300],
            caption=caption,
            comment=None,
            story_word=None,
            files=json.dumps(files, ensure_ascii=False),
            thumb=thumb,
            set_key=f"tg:{meta.get('key')}:{meta.get('day')}" if len(posts) > 1 else None,
            set_n=post.n if len(posts) > 1 else None,
            source=json.dumps(
                {
                    "flow_key": meta.get("key"),
                    "day": meta.get("day"),
                    "work": w["ref"],
                    "order": order,
                    "n": post.n,
                    "type": post.type,
                    "chat": chat,
                    "post": stored,
                },
                ensure_ascii=False,
                default=str,
            ),
            chain=[str(uuid.uuid5(NS, f"{w['id']}:{post.n}"))],
            search=P.search_of(title, post.topic, caption, [], None),
            created_at=None,
        )
        if ref is not None:
            row = await tx.one("SELECT * FROM media.publications WHERE id = :id", id=ref)
            await P._emit(tx, dict(row))
            made.append(str(row["ref"]))
    meta["sent"] = now.isoformat()
    meta["telegram"] = "queued"
    meta["topic_fa"] = " / ".join(p.topic for p in posts)[:300]
    await tx.exec(
        "UPDATE work.work SET run_meta = jsonb_set(run_meta, '{flow}', CAST(:m AS jsonb)) WHERE id = :w",
        w=w["id"],
        m=json.dumps(meta, ensure_ascii=False, default=str),
    )
    await audit.record(
        tx,
        FL.FLOW,
        company_id=w["company_id"],
        action="flow.publish",
        action_class="A3",
        target_kind="order" if order else "deliverable",
        target_ref=order or str(pkg["d"]["ref"]),
        summary=f"{meta.get('key')} {meta.get('day')}: {len(made)} Telegram posts of {w['ref']} queued for "
        f"{chat or '(no channel yet)'} ({', '.join(made)[:300]})"[:500],
    )
    if order:
        from hq_api.domain import sessions as SE

        rep = await OR.ensure(tx, order)
        if rep is not None and rep.get("closed_at") is None:
            await SE.close(
                tx, order, "ok", f"اتوماسیون تلگرام: {len(made)} پست زمان‌بندی شد", hub=hub
            )
    return "queued"


# ------------------------------------------------------------------ the worker's tick --
@dataclass
class Rights:
    ok: bool
    why: str
    at: float


RIGHTS: dict[tuple[str, str], Rights] = {}  # (company code, chat) -> the bot's last read rights

DUE_SQL = """SELECT p.*, c.code AS company FROM media.publications p JOIN core.companies c ON c.id = p.company_id
    WHERE p.channel = 'telegram' AND p.kind = 'tg_post' AND p.state = 'scheduled' AND p.scheduled_at <= :now
      AND coalesce((p.source ->> 'retry_at')::timestamptz, p.scheduled_at) <= :now
    ORDER BY p.scheduled_at, p.set_n NULLS FIRST LIMIT 20"""
STUCK_SQL = """SELECT * FROM media.publications WHERE channel = 'telegram' AND kind = 'tg_post'
    AND state = 'publishing' AND updated_at < :t"""


async def read_secret(hub: Any, company: str) -> str | None:
    from hq_api.domain import connections as CN

    token = await CN.read_secret(getattr(hub, "bao", None), company, CONNECTION)
    return token if token and BOT_TOKEN.fullmatch(token) else None


def _code(out: dict[str, Any]) -> str:
    return str(out.get("code") or out.get("error") or "publish_error")


async def rights(hub: Any, company: str, chat: str, token: str, *, fresh: bool = False) -> Rights:
    """The bot's own rights in the channel: getMe, then getChatMember of the bot (an administrator
    with can_post_messages, or the channel's creator). Kept RIGHTS_OK_TTL when it may post, re-read
    every RIGHTS_NO_TTL while it may not (so it starts by itself once the owner made it admin)."""
    from hq_api.domain import studio_publish as SP

    key = (company, chat)
    got = RIGHTS.get(key)
    ttl = RIGHTS_OK_TTL if got and got.ok else RIGHTS_NO_TTL
    if got and not fresh and time.monotonic() - got.at < ttl.total_seconds():
        return got
    pub = SP.publisher()
    me = await pub.call(
        hub, {"channel": "telegram", "method": "getMe", "token": token, "payload": {}}, []
    )
    if me.get("outcome") != "ok" or not isinstance((me.get("data") or {}).get("id"), int):
        why = "توکن ربات پذیرفته نشد" if _code(me) == "auth_failed" else f"getMe: {_code(me)}"
        RIGHTS[key] = Rights(False, why, time.monotonic())
        return RIGHTS[key]
    bot = int(me["data"]["id"])
    mem = await pub.call(
        hub,
        {
            "channel": "telegram",
            "method": "getChatMember",
            "token": token,
            "payload": {"chat_id": chat, "user_id": bot},
        },
        [],
    )
    data = mem.get("data") or {}
    ok = mem.get("outcome") == "ok" and (
        data.get("status") == "creator"
        or (data.get("status") == "administrator" and data.get("can_post_messages") is True)
    )
    why = (
        ""
        if ok
        else (
            WAIT_RIGHTS_FA
            if mem.get("outcome") != "ok" or data.get("status") != "administrator"
            else "ربات مدیر است ولی اجازه‌ی «Post Messages» ندارد"
        )
    )
    if got is None or got.ok != ok:
        log.info(
            "telegram rights",
            extra={"company": company, "chat": chat, "ok": ok, "status": data.get("status")},
        )
    RIGHTS[key] = Rights(ok, why, time.monotonic())
    return RIGHTS[key]


async def _note(hub: Any, row: dict[str, Any], note: str | None, **src: Any) -> None:
    from hq_api.domain import publications as P

    async with hub.db.tx([row["company_id"]]) as tx:
        await tx.exec(
            """UPDATE media.publications SET state_note_fa = :n, updated_at = now(),
                   source = source || CAST(:s AS jsonb) WHERE id = :id AND state = 'scheduled'""",
            id=row["id"],
            n=note,
            s=json.dumps(src, ensure_ascii=False, default=str),
        )
        got = await tx.first("SELECT * FROM media.publications WHERE id = :id", id=row["id"])
        if got is not None and row.get("state_note_fa") != note:
            await P._emit(tx, dict(got))


async def _finish(hub: Any, row: dict[str, Any], state: str, note: str | None, **cols: Any) -> None:
    from hq_api.domain import publications as P

    async with hub.db.tx([row["company_id"]]) as tx:
        await tx.exec(
            """UPDATE media.publications SET state = :st, state_note_fa = :n, updated_at = now(),
                   published_at = coalesce(CAST(:pub AS timestamptz), published_at),
                   external_id = coalesce(:ext, external_id), url = coalesce(:url, url),
                   source = source || CAST(:s AS jsonb)
               WHERE id = :id""",
            id=row["id"],
            st=state,
            n=note,
            pub=cols.get("published_at"),
            ext=cols.get("external_id"),
            url=cols.get("url"),
            s=json.dumps(cols.get("source") or {}, ensure_ascii=False, default=str),
        )
        got = await tx.one("SELECT * FROM media.publications WHERE id = :id", id=row["id"])
        await P._emit(tx, dict(got))
        if state in ("published", "failed", "cancelled"):
            await audit.record(
                tx,
                _WHO,
                company_id=row["company_id"],
                action=f"telegram.{state}",
                action_class="A3",
                target_kind="publication",
                target_ref=str(row["ref"]),
                summary=f"{(row.get('source') or {}).get('chat')} {state}: {row['title_fa']}"
                f"{' ' + str(cols.get('url')) if cols.get('url') else ''}{' (' + note + ')' if note else ''}"[
                    :500
                ],
            )


def _src(row: dict[str, Any]) -> dict[str, Any]:
    s = row.get("source")
    return json.loads(s) if isinstance(s, str) else dict(s or {})


async def _send(hub: Any, row: dict[str, Any], chat: str, token: str) -> tuple[str, dict[str, Any]]:
    """Every message of the post not sent yet, in order: ('ok' | 'retry' | 'rights' | 'failed', info)."""
    from hq_api.domain import studio_publish as SP

    src = _src(row)
    sent: list[int] = [int(x) for x in src.get("sent_ids") or []]
    pub = SP.publisher()
    for i, (method, payload, files) in enumerate(calls(src.get("post") or {}, chat)):
        if i < len(sent):
            continue
        blobs = [
            (f["name"], await SP._bytes(hub, row["company_id"], f["file_id"]), f["mime"])
            for f in files
        ]
        out = await pub.call(
            hub,
            {"channel": "telegram", "method": method, "token": token, "payload": payload},
            blobs,
        )
        del blobs
        data = out.get("data") or {}
        if out.get("outcome") == "ok":
            ids = data.get("message_ids") or [data.get("message_id")]
            sent.extend(int(x) for x in ids if isinstance(x, int))
            continue
        code = _code(out)
        info = {
            "sent_ids": sent,
            "code": code,
            "description": str(data.get("description") or "")[:200],
            "retry_after": data.get("retry_after"),
        }
        if code == "platform_limit":
            return "retry", info
        if code in ("no_channel", "auth_failed"):
            return "rights", info
        return "failed", info
    return "ok", {"sent_ids": sent}


def stale_after(row: dict[str, Any]) -> timedelta:
    return STALE.get(str(_src(row).get("type") or ""), STALE_DEFAULT)


async def tick(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """The worker's minute: what is due goes out, after the bot's rights are read."""
    now = now or datetime.now(UTC)
    out: dict[str, Any] = {"sent": [], "waiting": 0, "stale": [], "failed": []}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        for r in await tx.all(STUCK_SQL, t=now - STUCK):
            await tx.exec(
                """UPDATE media.publications SET state = 'failed', state_note_fa = :n, updated_at = now()
                   WHERE id = :id AND state = 'publishing'""",
                id=r["id"],
                n=STUCK_FA,
            )
            out["failed"].append(str(r["ref"]))
        rows = [dict(r) for r in await tx.all(DUE_SQL, now=now)]
    tokens: dict[str, str | None] = {}
    for row in rows:
        company, src = str(row["company"]), _src(row)
        chat = str(src.get("chat") or "")
        if not CHAT.fullmatch(chat):
            async with hub.db.tx([row["company_id"]]) as tx:
                chat = await channel_of(tx, row["company_id"], str(row["account"])) or ""
            if not chat:
                await _note(hub, row, NO_CHANNEL_FA)
                out["waiting"] += 1
                continue
            src["chat"] = chat
        if now - row["scheduled_at"] > stale_after(row):
            why = row.get("state_note_fa") or "دیر رسید"
            await _finish(hub, row, "cancelled", STALE_FA.format(why=why)[:500])
            out["stale"].append(str(row["ref"]))
            continue
        if company not in tokens:
            tokens[company] = await read_secret(hub, company)
        token = tokens[company]
        if token is None:
            await _note(hub, row, WAIT_TOKEN_FA)
            out["waiting"] += 1
            continue
        r = await rights(hub, company, chat, token)
        if not r.ok:
            await _note(hub, row, r.why)
            out["waiting"] += 1
            continue
        async with hub.db.tx([row["company_id"]]) as tx:  # once: marked before its first call
            took = await tx.scalar(
                """UPDATE media.publications SET state = 'publishing', state_note_fa = NULL, updated_at = now(),
                       source = source || CAST(:s AS jsonb)
                   WHERE id = :id AND state = 'scheduled' RETURNING id""",
                id=row["id"],
                s=json.dumps({"chat": chat}),
            )
        if took is None:
            continue
        row["source"] = {**src, "chat": chat}
        try:
            state, info = await _send(hub, row, chat, token)
        except Exception as exc:  # noqa: BLE001 - one post that cannot be sent never stops the others
            log.warning(
                "telegram post not sent",
                extra={"ref": str(row["ref"]), "error": type(exc).__name__},
            )
            await _finish(
                hub, row, "failed", FAILED_FA.format(why=f"خطای ستاد ({type(exc).__name__})")
            )
            out["failed"].append(str(row["ref"]))
            continue
        ids = info.get("sent_ids") or []
        name = chat[1:] if chat.startswith("@") else None
        url = f"https://t.me/{name}/{ids[0]}" if name and ids else None
        if state == "ok":
            await _finish(
                hub,
                row,
                "published",
                None,
                published_at=datetime.now(UTC),
                external_id=str(ids[0]) if ids else None,
                url=url,
                source={"sent_ids": ids},
            )
            out["sent"].append(str(row["ref"]))
            continue
        back = {"sent_ids": ids, "last_code": info.get("code")}
        if state in ("retry", "rights"):
            wait = int(info.get("retry_after") or 60) if state == "retry" else 300
            if state == "rights":
                RIGHTS.pop((company, chat), None)  # read again: it may have lost its rights
            back["retry_at"] = (datetime.now(UTC) + timedelta(seconds=wait)).isoformat()
            async with hub.db.tx([row["company_id"]]) as tx:
                await tx.exec(
                    """UPDATE media.publications SET state = 'scheduled', updated_at = now(),
                           state_note_fa = :n, source = source || CAST(:s AS jsonb) WHERE id = :id""",
                    id=row["id"],
                    s=json.dumps(back),
                    n=WAIT_RIGHTS_FA if state == "rights" else None,
                )
            out["waiting"] += 1
            continue
        why = info.get("description") or info.get("code") or "?"
        await _finish(
            hub,
            row,
            "failed",
            FAILED_FA.format(why=why)[:500],
            url=url,
            external_id=str(ids[0]) if ids else None,
            source=back,
        )
        out["failed"].append(str(row["ref"]))
    return out
