"""Publishing through the official APIs only (prompt 13 §2.3; contract §22.2
step 8, §22.7): one call of the Telegram Bot API or the Instagram Graph API
for the media studio. Code calls it (the worker, on hq-egress-api), never an
agent: the api decided the item may be published (a sealed series whose every
check passed, or the owner's sealed `media_publish` card).

    POST /v1/media/publish   multipart/form-data
      part `call` (JSON): {channel: "telegram" | "instagram", method, token, payload,
                           files?: [{part: "file0", name, mime, sha256}]}
      parts `file0`..`file9` (binary): the files a Telegram method uploads
      -> {outcome: ok | blocked | error, code, data, entries}

telegram   https://api.telegram.org/bot<token>/<method>, the bot an admin of the channel.
           getMe · getChat {chat_id} · sendVideo {chat_id, video: "attach://fileN",
           caption?, duration?, width?, height?, supports_streaming?} · sendPhoto
           {chat_id, photo: "attach://fileN", caption?} · sendMediaGroup {chat_id,
           media: [{type: photo|video, media: "attach://fileN", caption?}] (2-10)} ·
           deleteMessage {chat_id, message_id}. Plain captions only: no parse_mode, no
           markup, no buttons. A channel story has no Bot API method: it is a card
           with the file for the owner (any story method is refused here).
instagram  https://graph.instagram.com/<GRAPH_VERSION>/..., the access token in the
           Authorization header (never in a URL). me · create {ig_user_id, media_type:
           REELS | STORIES | IMAGE | CAROUSEL, video_url | image_url | children, caption?,
           is_carousel_item?, share_to_feed?} (is_ai_generated: true is always set
           here) · status {container_id} · publish {ig_user_id, creation_id} · limit
           {ig_user_id} · permalink {media_id}. Instagram fetches the file itself: a
           media URL is exactly https://<public host>/public/v1/media/<token> (the
           api's signed URL for that one file, ≤ 15 minutes). There is no delete:
           `delete` is refused and the api records `remove_by_hand`.

Sizes (enforced while the body streams in): the whole body ≤ 60 MB, a photo
≤ 10 MB, a video ≤ 50 MB (the Bot API's own upload limit); each declared file
must match its part (sha256), its type (magic bytes) and its use.

Answers: `ok` with the few fields the caller needs; `blocked` for anything
outside the allow-lists (`method_not_allowed`, `payload_not_allowed`,
`url_not_allowed`, `public_host_not_configured`, `bad_token`, `file_mismatch`,
`file_too_large`, `too_large`, `redirect_not_allowed`, the guard's own); `error`
with a stable code: `platform_limit` (the platform's own publishing limit;
`data.retry_after` in seconds when it is known), `no_channel` (the bot or the
account cannot post there: not an admin, chat not found, not a business
account, a permission missing), `auth_failed` (the token is refused),
`publish_error` otherwise (a container in ERROR or EXPIRED included, with
`data.status`).

The token arrives with the call and is held for that call only: it goes on the
request, never into an entry (host, status, sizes and time only), an error, a
log line or the answer (scrubbed in every form). No redirect is followed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from hq_egress.accounts import scrub
from hq_egress.guard import Blocked
from hq_egress.net import CALL_ENTRIES, Entry, FetchError, track
from hq_egress.proxy import entries_json
from hq_egress.support_out import BOT_TOKEN

log = logging.getLogger("hq_egress.media")
router = APIRouter()

TOOL = "media.publish"
TELEGRAM_API = "https://api.telegram.org"
GRAPH_API = "https://graph.instagram.com"
GRAPH_VERSION = "v23.0"  # pinned; a new version is a reviewed change
MAX_BODY = 60 * 1024 * 1024  # the whole multipart body
PHOTO_MAX = 10 * 1024 * 1024  # the Bot API's photo upload
VIDEO_MAX = 50 * 1024 * 1024  # the Bot API's upload limit for any file
ANSWER_MAX = 1024 * 1024
CALL_MAX = 64 * 1024  # the JSON part
MAX_FILES = 10
CAPTION_MAX = 1024  # Telegram's media caption
IG_CAPTION_MAX = 2200  # Instagram's own caption limit
IG_HASHTAGS_MAX = 30
IG_TOKEN = re.compile(r"^[A-Za-z0-9_.|-]{20,1024}$")
DIGITS = re.compile(r"^[0-9]{1,30}$")
CHAT_NAME = re.compile(r"^@[A-Za-z][A-Za-z0-9_]{4,31}$")
CHAT_ID = re.compile(r"^-100[0-9]{6,15}$")
PART = re.compile(r"^file[0-9]$")
ATTACH = re.compile(r"^attach://(file[0-9])$")
MEDIA_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,200}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MIMES = {"image/jpeg": "photo", "image/png": "photo", "video/mp4": "video"}
EXT = {"image/jpeg": "jpg", "image/png": "png", "video/mp4": "mp4"}
# Telegram's refusals that mean "this bot cannot post in this channel".
NO_CHANNEL = (
    "chat not found",
    "not enough rights",
    "bot is not a member",
    "have no rights to send",
    "need administrator rights",
    "bot was kicked",
    "chat_write_forbidden",
    "chat_admin_required",
)
# Instagram's rate and publishing limits (Graph API error codes; 2207042 = the
# content publishing limit), its token errors, its permission errors.
IG_LIMIT_CODES = frozenset({4, 9, 17, 32, 613})
IG_LIMIT_SUBCODES = frozenset({2207042})
IG_AUTH_CODES = frozenset({102, 190, 463, 467})
IG_NO_CHANNEL_CODES = frozenset({10})
_BOT_PATH = re.compile(r"/bot[0-9]{5,16}:[A-Za-z0-9_-]+")


class _NoTokenInLogs(logging.Filter):
    """A Telegram URL carries the bot token in its path; no level shows it."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except (TypeError, ValueError):
            return True
        clean = _BOT_PATH.sub("/bot[secret]", msg)
        if clean != msg:
            record.msg, record.args = clean, None
        return True


for _name in ("httpx", "httpcore", "hq_egress"):
    logging.getLogger(_name).addFilter(_NoTokenInLogs())


class FileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    part: str = Field(pattern=PART.pattern)
    name: str = Field(min_length=1, max_length=120)
    mime: str = Field(min_length=3, max_length=60)
    sha256: str = Field(pattern=SHA256.pattern)


class CallIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Literal["telegram", "instagram"]
    method: str = Field(min_length=1, max_length=40)
    token: str = Field(min_length=1, max_length=1024, repr=False)
    payload: dict[str, Any] = Field(default_factory=dict)
    files: list[FileIn] = Field(default_factory=list, max_length=MAX_FILES)


class Refused(Exception):
    """Outside the allow-lists: `code` is the stable reason."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class Upload:
    part: str
    mime: str
    kind: str  # photo | video
    data: memoryview


# ------------------------------------------------------------ the request --
class TooLarge(Exception):
    pass


async def _read_body(request: Request) -> bytearray:
    """The body as it streams in, refused past MAX_BODY (never held whole first)."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_BODY:
        raise TooLarge
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY:
            raise TooLarge
        body += chunk
    return body


def _boundary(content_type: str) -> bytes:
    kind, _, params = content_type.partition(";")
    if kind.strip().lower() != "multipart/form-data":
        raise Refused("bad_request")
    for p in params.split(";"):
        k, _, v = p.strip().partition("=")
        if k.lower() == "boundary":
            v = v.strip().strip('"')
            if re.fullmatch(r"[0-9A-Za-z'()+_,./:=?-]{1,70}", v):
                return v.encode()
    raise Refused("bad_request")


def _disposition(value: str) -> tuple[str | None, bool]:
    """(name, has a filename) of a Content-Disposition: form-data header."""
    kind, _, rest = value.partition(";")
    if kind.strip().lower() != "form-data":
        return None, False
    name, has_file = None, False
    for p in rest.split(";"):
        k, _, v = p.strip().partition("=")
        k = k.lower()
        if k == "name":
            name = v.strip().strip('"')
        elif k in ("filename", "filename*"):
            has_file = True
    return name, has_file


def parse_multipart(body: bytearray, content_type: str) -> dict[str, memoryview]:
    """A strict multipart/form-data reader: named parts only, each at most once,
    the data as views of the one buffer (a 50 MB video is never copied here)."""
    boundary = _boundary(content_type)
    delim = b"--" + boundary
    view = memoryview(body)
    if not bytes(view[: len(delim) + 2]) == delim + b"\r\n":
        raise Refused("bad_request")
    pos = len(delim) + 2
    parts: dict[str, memoryview] = {}
    sep = b"\r\n" + delim
    while True:
        head_end = body.find(b"\r\n\r\n", pos)
        if head_end == -1 or head_end - pos > 4096:
            raise Refused("bad_request")
        headers = bytes(view[pos:head_end]).decode("utf-8", "replace").split("\r\n")
        name = None
        for line in headers:
            k, _, v = line.partition(":")
            if k.strip().lower() == "content-disposition":
                name, _ = _disposition(v)
        end = body.find(sep, head_end + 4)
        if end == -1 or name is None or name in parts or len(parts) >= MAX_FILES + 1:
            raise Refused("bad_request")
        parts[name] = view[head_end + 4 : end]
        after = end + len(sep)
        tail = bytes(view[after : after + 2])
        if tail == b"--":
            return parts
        if tail != b"\r\n":
            raise Refused("bad_request")
        pos = after + 2


def _magic_ok(mime: str, data: memoryview) -> bool:
    head = bytes(data[:12])
    if mime == "image/jpeg":
        return head.startswith(b"\xff\xd8\xff")
    if mime == "image/png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "video/mp4":
        return head[4:8] == b"ftyp"
    return False


def uploads(call: CallIn, parts: dict[str, memoryview]) -> dict[str, Upload]:
    """Every file part declared in `files`, matching its sha256 and its type."""
    got = {k: v for k, v in parts.items() if k != "call"}
    if set(got) - {f.part for f in call.files} or {f.part for f in call.files} - set(got):
        raise Refused("file_mismatch")
    out: dict[str, Upload] = {}
    for f in call.files:
        if f.part in out:
            raise Refused("file_mismatch")
        data = got[f.part]
        kind = MIMES.get(f.mime)
        if kind is None or not _magic_ok(f.mime, data):
            raise Refused("file_mismatch")
        if len(data) > (PHOTO_MAX if kind == "photo" else VIDEO_MAX):
            raise Refused("file_too_large")
        if hashlib.sha256(data).hexdigest() != f.sha256:
            raise Refused("file_mismatch")
        out[f.part] = Upload(f.part, f.mime, kind, data)
    return out


# --------------------------------------------------------------- telegram --
TELEGRAM_KEYS: dict[str, frozenset[str]] = {
    "getMe": frozenset(),
    "getChat": frozenset({"chat_id"}),
    "sendVideo": frozenset(
        {"chat_id", "video", "caption", "duration", "width", "height", "supports_streaming"}
    ),
    "sendPhoto": frozenset({"chat_id", "photo", "caption"}),
    "sendMediaGroup": frozenset({"chat_id", "media"}),
    "deleteMessage": frozenset({"chat_id", "message_id"}),
}
TELEGRAM_REQUIRED: dict[str, frozenset[str]] = {
    "getChat": frozenset({"chat_id"}),
    "sendVideo": frozenset({"chat_id", "video"}),
    "sendPhoto": frozenset({"chat_id", "photo"}),
    "sendMediaGroup": frozenset({"chat_id", "media"}),
    "deleteMessage": frozenset({"chat_id", "message_id"}),
}
TELEGRAM_CLASS = {"getMe": "A0", "getChat": "A0"}  # every other method is the publication itself


def _int(value: Any, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise Refused("payload_not_allowed")
    return value


def _caption(value: Any, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise Refused("payload_not_allowed")
    return value


def _chat(value: Any) -> str:
    text = str(value) if isinstance(value, int) and not isinstance(value, bool) else value
    if not isinstance(text, str) or not (CHAT_NAME.match(text) or CHAT_ID.match(text)):
        raise Refused("payload_not_allowed")
    return text


def _attach(value: Any, files: dict[str, Upload], kind: str, used: set[str]) -> str:
    m = ATTACH.match(value) if isinstance(value, str) else None
    if m is None or m.group(1) not in files or m.group(1) in used:
        raise Refused("file_mismatch")
    if files[m.group(1)].kind != kind:
        raise Refused("file_mismatch")
    used.add(m.group(1))
    return m.group(1)


def telegram_request(
    method: str, payload: dict[str, Any], files: dict[str, Upload]
) -> tuple[list[tuple[str, Any]], list[tuple[str, Upload]]]:
    """(the fields, the files by their field name) of one Bot API call,
    or Refused. A file field carries the part's bytes (sendVideo's `video`,
    sendPhoto's `photo`); a media group refers to its parts by attach://."""
    if "story" in method.lower():
        raise Refused("method_not_allowed")  # no channel story in the Bot API: a card
    allowed = TELEGRAM_KEYS.get(method)
    if allowed is None:
        raise Refused("method_not_allowed")
    if set(payload) - allowed or not TELEGRAM_REQUIRED.get(method, frozenset()) <= set(payload):
        raise Refused("payload_not_allowed")
    fields: list[tuple[str, Any]] = []
    out: list[tuple[str, Upload]] = []
    used: set[str] = set()
    if "chat_id" in payload:
        fields.append(("chat_id", _chat(payload["chat_id"])))
    if method == "sendVideo":
        out.append(("video", files[_attach(payload["video"], files, "video", used)]))
        for k, (low, high) in {"duration": (1, 36000), "width": (1, 10000),
                               "height": (1, 10000)}.items():  # fmt: skip
            if k in payload:
                fields.append((k, _int(payload[k], low, high)))
        if "supports_streaming" in payload:
            if not isinstance(payload["supports_streaming"], bool):
                raise Refused("payload_not_allowed")
            fields.append(("supports_streaming", payload["supports_streaming"]))
    elif method == "sendPhoto":
        out.append(("photo", files[_attach(payload["photo"], files, "photo", used)]))
    elif method == "sendMediaGroup":
        media = payload["media"]
        if not isinstance(media, list) or not 2 <= len(media) <= MAX_FILES:
            raise Refused("payload_not_allowed")
        items = []
        for m in media:
            if not isinstance(m, dict) or set(m) - {"type", "media", "caption"}:
                raise Refused("payload_not_allowed")
            if m.get("type") not in ("photo", "video"):
                raise Refused("payload_not_allowed")
            part = _attach(m.get("media"), files, m["type"], used)
            item = {"type": m["type"], "media": f"attach://{part}"}
            if "caption" in m:
                item["caption"] = _caption(m["caption"], CAPTION_MAX)
            items.append(item)
            out.append((part, files[part]))
        fields.append(("media", json.dumps(items, ensure_ascii=False)))
    elif method == "deleteMessage":
        fields.append(("message_id", _int(payload["message_id"], 1, 2**53)))
    if "caption" in payload:
        fields.append(("caption", _caption(payload["caption"], CAPTION_MAX)))
    if set(files) - used:
        raise Refused("file_mismatch")  # every uploaded file is used, and only once
    return fields, out


def _form_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def multipart(fields: list[tuple[str, Any]], files: list[tuple[str, Upload]]) -> tuple[bytes, str]:
    """The Bot API body: plain fields, then the files with generic names (a
    file's own name never leaves the hub)."""
    boundary = "hq-" + secrets.token_hex(16)
    pieces: list[bytes | memoryview] = []
    for k, v in fields:
        pieces.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
        )
        pieces.append(_form_value(v).encode() + b"\r\n")
    for name, up in files:
        pieces.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                f'filename="{name}.{EXT[up.mime]}"\r\nContent-Type: {up.mime}\r\n\r\n'
            ).encode()
        )
        pieces.append(up.data)  # a view of the request's buffer: joined once, below
        pieces.append(b"\r\n")
    pieces.append(f"--{boundary}--\r\n".encode())
    return b"".join(pieces), f"multipart/form-data; boundary={boundary}"


def _message(result: Any) -> dict[str, Any]:
    doc = result if isinstance(result, dict) else {}
    raw = doc.get("chat")
    chat: dict[str, Any] = raw if isinstance(raw, dict) else {}
    return {
        "message_id": doc.get("message_id"),
        "chat_id": chat.get("id"),
        "chat_username": chat.get("username"),
        "date": doc.get("date"),
    }


def telegram_result(method: str, result: Any) -> Any:
    if method in ("sendVideo", "sendPhoto"):
        return _message(result)
    if method == "sendMediaGroup":
        msgs = [_message(m) for m in result] if isinstance(result, list) else []
        first = msgs[0] if msgs else {}
        return {
            "message_ids": [m["message_id"] for m in msgs],
            "chat_id": first.get("chat_id"),
            "chat_username": first.get("chat_username"),
            "date": first.get("date"),
        }
    if method == "getMe" and isinstance(result, dict):
        return {k: result.get(k) for k in ("id", "username", "is_bot") if k in result}
    if method == "getChat" and isinstance(result, dict):
        return {k: result.get(k) for k in ("id", "type", "username", "title") if k in result}
    return {"result": result if isinstance(result, bool) else bool(result)}


def telegram_outcome(method: str, status: int, body: Any) -> tuple[str, str | None, Any]:
    doc = body if isinstance(body, dict) else {}
    description = str(doc.get("description") or "")[:200]
    if status == 200 and doc.get("ok") is True:
        return "ok", None, telegram_result(method, doc.get("result"))
    raw = doc.get("parameters")
    params: dict[str, Any] = raw if isinstance(raw, dict) else {}
    if status == 429:
        retry = params.get("retry_after")
        retry_s = retry if isinstance(retry, int) and not isinstance(retry, bool) else 30
        return "error", "platform_limit", {"status": 429, "retry_after": max(1, retry_s)}
    if status in (401, 404):
        return "error", "auth_failed", {"status": status}
    low = description.lower()
    if status in (400, 403) and any(m in low for m in NO_CHANNEL):
        return "error", "no_channel", {"status": status, "description": description}
    return "error", "publish_error", {"status": status, "description": description}


# -------------------------------------------------------------- instagram --
IG_METHODS = ("me", "create", "status", "publish", "limit", "permalink")
IG_KEYS: dict[str, frozenset[str]] = {
    "me": frozenset(),
    "create": frozenset(
        {
            "ig_user_id",
            "media_type",
            "video_url",
            "image_url",
            "children",
            "caption",
            "is_carousel_item",
            "share_to_feed",
        }
    ),
    "status": frozenset({"container_id"}),
    "publish": frozenset({"ig_user_id", "creation_id"}),
    "limit": frozenset({"ig_user_id"}),
    "permalink": frozenset({"media_id"}),
}
IG_CLASS = {"me": "A0", "status": "A0", "limit": "A0", "permalink": "A0"}


def _digits(value: Any) -> str:
    text = str(value) if isinstance(value, int) and not isinstance(value, bool) else value
    if not isinstance(text, str) or not DIGITS.match(text):
        raise Refused("payload_not_allowed")
    return text


def _media_url(value: Any, public_host: str) -> str:
    """Exactly https://<public host>/public/v1/media/<token>: the api's signed
    URL for that one file (contract §22.2); nothing else is ever handed out."""
    prefix = f"https://{public_host}/public/v1/media/"
    if not isinstance(value, str) or not value.startswith(prefix):
        raise Refused("url_not_allowed")
    if not MEDIA_TOKEN.match(value[len(prefix) :]):
        raise Refused("url_not_allowed")
    return value


def _ig_caption(value: Any) -> str:
    text = _caption(value, IG_CAPTION_MAX)
    if text.count("#") > IG_HASHTAGS_MAX:
        raise Refused("payload_not_allowed")
    return text


def instagram_request(
    method: str, payload: dict[str, Any], public_host: str
) -> tuple[str, str, dict[str, Any] | None]:
    """(verb, URL, JSON body) of one Graph API call, or Refused."""
    if method not in IG_METHODS:
        raise Refused("method_not_allowed")  # `delete` included: no such API
    if set(payload) - IG_KEYS[method]:
        raise Refused("payload_not_allowed")
    base = f"{GRAPH_API}/{GRAPH_VERSION}"
    if method == "me":
        return "GET", f"{base}/me?fields=user_id,username", None
    if method == "status":
        return (
            "GET",
            f"{base}/{_digits(payload.get('container_id'))}?fields=status_code,status",
            None,
        )
    if method == "permalink":
        media = _digits(payload.get("media_id"))
        return "GET", f"{base}/{media}?fields=id,permalink,media_type,timestamp", None
    user = _digits(payload.get("ig_user_id"))
    if method == "limit":
        return "GET", f"{base}/{user}/content_publishing_limit?fields=quota_usage,config", None
    if method == "publish":
        return (
            "POST",
            f"{base}/{user}/media_publish",
            {"creation_id": _digits(payload.get("creation_id"))},
        )
    # create: one container, always labelled AI-generated (contract §22.2)
    kind = payload.get("media_type")
    body: dict[str, Any] = {"is_ai_generated": True}
    video, image = payload.get("video_url"), payload.get("image_url")
    item = payload.get("is_carousel_item", False)
    if not isinstance(item, bool):
        raise Refused("payload_not_allowed")
    if kind == "REELS":
        if video is None or image is not None or "children" in payload or item:
            raise Refused("payload_not_allowed")
        body.update(media_type="REELS", video_url=_media_url(video, public_host))
        if "share_to_feed" in payload:
            if not isinstance(payload["share_to_feed"], bool):
                raise Refused("payload_not_allowed")
            body["share_to_feed"] = payload["share_to_feed"]
    elif kind == "STORIES":
        if (video is None) == (image is None) or "children" in payload or item:
            raise Refused("payload_not_allowed")
        if "caption" in payload or "share_to_feed" in payload:
            raise Refused("payload_not_allowed")  # a story takes no caption
        body["media_type"] = "STORIES"
        if video is not None:
            body["video_url"] = _media_url(video, public_host)
        else:
            body["image_url"] = _media_url(image, public_host)
    elif kind == "IMAGE":
        if image is None or video is not None or "children" in payload:
            raise Refused("payload_not_allowed")
        if "share_to_feed" in payload or (item and "caption" in payload):
            raise Refused("payload_not_allowed")
        body["image_url"] = _media_url(image, public_host)  # a single image takes no media_type
        if item:
            body["is_carousel_item"] = True
    elif kind == "CAROUSEL":
        children = payload.get("children")
        if video is not None or image is not None or item or "share_to_feed" in payload:
            raise Refused("payload_not_allowed")
        if not isinstance(children, list) or not 2 <= len(children) <= 10:
            raise Refused("payload_not_allowed")
        body.update(media_type="CAROUSEL", children=",".join(_digits(c) for c in children))
    else:
        raise Refused("payload_not_allowed")
    if "caption" in payload:
        body["caption"] = _ig_caption(payload["caption"])
    return "POST", f"{base}/{user}/media", body


def _ig_error(status: int, doc: dict[str, Any], headers: dict[str, str]) -> tuple[str, Any]:
    raw = doc.get("error")
    err: dict[str, Any] = raw if isinstance(raw, dict) else {}
    code = err.get("code") if isinstance(err.get("code"), int) else None
    sub = err.get("error_subcode") if isinstance(err.get("error_subcode"), int) else None
    message = str(err.get("message") or "")[:200]
    data: dict[str, Any] = {"status": status, "error_code": code, "error_subcode": sub,
                            "message": message}  # fmt: skip
    if code in IG_LIMIT_CODES or sub in IG_LIMIT_SUBCODES or status == 429:
        retry = headers.get("retry-after", "")
        if retry.isdigit():
            data["retry_after"] = max(1, int(retry))
        return "platform_limit", data
    if code in IG_AUTH_CODES or status == 401:
        return "auth_failed", data
    low = message.lower()
    if (
        code in IG_NO_CHANNEL_CODES
        or (code is not None and 200 <= code <= 299)
        or "business" in low
        or "professional account" in low
        or "permission" in low
    ):
        return "no_channel", data
    return "publish_error", data


def instagram_outcome(
    method: str, status: int, body: Any, headers: dict[str, str]
) -> tuple[str, str | None, Any]:
    doc = body if isinstance(body, dict) else {}
    if not 200 <= status < 300 or "error" in doc:
        code, data = _ig_error(status, doc, headers)
        return "error", code, data
    if method == "me":
        return "ok", None, {k: doc.get(k) for k in ("user_id", "username", "id") if k in doc}
    if method == "create":
        return "ok", None, {"container_id": doc.get("id")}
    if method == "publish":
        return "ok", None, {"media_id": doc.get("id")}
    if method == "permalink":
        keep = ("id", "permalink", "media_type", "timestamp")
        return "ok", None, {k: doc.get(k) for k in keep if k in doc}
    if method == "status":
        state = {"status_code": doc.get("status_code"), "status": doc.get("status")}
        if state["status_code"] in ("ERROR", "EXPIRED"):
            return "error", "publish_error", state
        return "ok", None, {**state, "id": doc.get("id")}
    # limit: {data: [{quota_usage, config: {quota_total, quota_duration}}]}
    raw_rows = doc.get("data")
    rows: list[Any] = raw_rows if isinstance(raw_rows, list) else []
    row: dict[str, Any] = rows[0] if rows and isinstance(rows[0], dict) else {}
    raw_cfg = row.get("config")
    cfg: dict[str, Any] = raw_cfg if isinstance(raw_cfg, dict) else {}
    usage, total = row.get("quota_usage"), cfg.get("quota_total")
    out = {"quota_usage": usage, "quota_total": total, "quota_duration": cfg.get("quota_duration")}
    if isinstance(usage, int) and isinstance(total, int) and usage >= total:
        return "error", "platform_limit", out
    return "ok", None, out


# ------------------------------------------------------------------ route --
def _answer(
    outcome: str,
    data: Any,
    entries: list[Entry],
    code: str | None,
    token: str | None,
    status: int = 200,
) -> JSONResponse:
    body = {
        "outcome": outcome,
        "code": code,
        "data": scrub(data, [token]) if token else data,
        "entries": entries_json(entries),
    }
    return JSONResponse(body, status_code=status)


def _entries() -> list[Entry]:
    """The entries of the call being served (the same list, even while empty)."""
    call = CALL_ENTRIES.get()
    return call if call is not None else []


def _host(channel: str) -> str:
    return "api.telegram.org" if channel == "telegram" else "graph.instagram.com"


@dataclass
class Prepared:
    verb: str
    url: str
    headers: dict[str, str]
    content: bytes | None
    cls: str


@router.post("/v1/media/publish")
async def publish(request: Request) -> JSONResponse:
    state = request.app.state.egress
    entries: list[Entry] = []
    ctx_token = CALL_ENTRIES.set(entries)
    token: str | None = None
    try:
        try:
            body = await _read_body(request)
        except TooLarge:
            track(Entry(TOOL, "POST", "?", blocked_reason="too_large", cls="A3"))
            return _answer("blocked", None, entries, "too_large", None, 413)
        try:
            parts = parse_multipart(body, request.headers.get("content-type", ""))
            raw = parts.get("call")
            if raw is None or len(raw) > CALL_MAX:
                raise Refused("bad_request")
            call = CallIn.model_validate_json(bytes(raw))
        except (Refused, ValidationError, ValueError):
            return JSONResponse(
                {"outcome": "error", "code": "invalid_args", "data": None, "entries": []}, 422
            )
        token = call.token
        async with asyncio.timeout(state.settings.media_deadline_s):
            prepared = await _prepare(state, call, parts)
            # The request's buffer goes before the upload: one copy of a video
            # is in memory while it is sent, not two.
            del parts, raw, body
            if isinstance(prepared, JSONResponse):
                return prepared
            return await _send(state, call, prepared)
    except TimeoutError:
        code = "call_timeout"
    except Exception as exc:  # noqa: BLE001 - the answer must still carry the entries
        log.warning("media.publish failed: %s", type(exc).__name__)
        code = "publish_error"
    finally:
        CALL_ENTRIES.reset(ctx_token)
    for e in entries:
        if e.status is None and e.blocked_reason is None:
            e.blocked_reason = code
    return _answer("error", None, entries, code, token)


async def _prepare(
    state: Any, call: CallIn, parts: dict[str, memoryview]
) -> Prepared | JSONResponse:
    """The one request of the call, or the refusal (an entry and `blocked`)."""
    token = call.token
    host = _host(call.channel)
    headers: dict[str, str] = {"Accept": "application/json"}
    try:
        if call.channel == "telegram":
            cls = TELEGRAM_CLASS.get(call.method, "A3")
            if not BOT_TOKEN.match(token):
                raise Refused("bad_token")
            files = uploads(call, parts)
            fields, out = telegram_request(call.method, call.payload, files)
            verb, url = "POST", f"{TELEGRAM_API}/bot{token}/{call.method}"
            content: bytes | None
            if out:
                content, headers["Content-Type"] = multipart(fields, out)
            else:
                content = json.dumps(dict(fields), ensure_ascii=False).encode()
                headers["Content-Type"] = "application/json"
        else:
            cls = IG_CLASS.get(call.method, "A3")
            if call.files or set(parts) - {"call"}:
                raise Refused("payload_not_allowed")  # Instagram fetches its file by URL
            if not state.settings.public_host:
                raise Refused("public_host_not_configured")
            if not IG_TOKEN.match(token):
                raise Refused("bad_token")
            verb, url, doc = instagram_request(
                call.method, call.payload, state.settings.public_host
            )
            headers["Authorization"] = f"Bearer {token}"
            content = None
            if doc is not None:
                content = json.dumps(doc, ensure_ascii=False).encode()
                headers["Content-Type"] = "application/json"
        # The guard first, by name and every address (the connection checks it again).
        target = state.guard.target(url)
        await state.guard.addresses(target.host, target.port)
    except Refused as r:
        track(Entry(TOOL, "POST", host, blocked_reason=r.code, cls="A3"))
        return _answer("blocked", None, _entries(), r.code, token)
    except Blocked as b:
        track(Entry(TOOL, "POST", host, blocked_reason=b.reason, cls="A3"))
        return _answer("blocked", None, _entries(), b.reason, token)
    return Prepared(verb, url, headers, content, cls)


async def _send(state: Any, call: CallIn, req: Prepared) -> JSONResponse:
    token = call.token
    entries = _entries()

    def no_redirect(_verb: str, current: str) -> str | None:
        return None if current == req.url else "redirect"

    start = time.monotonic()
    try:
        got = await state.fetcher.fetch(
            req.verb,
            req.url,
            tool=TOOL,
            cls=req.cls,
            headers=req.headers,
            content=req.content,
            max_bytes=ANSWER_MAX,
            check=no_redirect,
        )
    except Blocked as b:
        reason = b.reason
        if b.reason == "needs_owner" and b.detail == "redirect":
            reason = "redirect_not_allowed"
            if entries:
                entries[-1].blocked_reason = reason
        return _answer("blocked", None, entries, reason, token)
    except FetchError:
        if entries:
            entries[-1].ms = entries[-1].ms or int((time.monotonic() - start) * 1000)
        return _answer("error", None, entries, "publish_error", token)
    finally:
        req.content = None
    if got.status in (301, 302, 303, 307, 308):
        if entries:
            entries[-1].blocked_reason = "redirect_not_allowed"
        return _answer("blocked", None, entries, "redirect_not_allowed", token)
    try:
        parsed: Any = json.loads(bytes(got.body).decode("utf-8", "replace") or "null")
    except ValueError:
        parsed = None
    if call.channel == "telegram":
        outcome, code, data = telegram_outcome(call.method, got.status, parsed)
    else:
        outcome, code, data = instagram_outcome(call.method, got.status, parsed, got.headers)
    return _answer(outcome, data, entries, code, token)
