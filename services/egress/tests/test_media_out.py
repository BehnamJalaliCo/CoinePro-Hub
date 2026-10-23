"""POST /v1/media/publish (prompt 13 §2.3; contract §22.2 step 8, §22.7): one
call of the Telegram Bot API or the Instagram Graph API, against a fake
Telegram and a fake Graph API (no real call: the fetcher's client is a mock
transport; the guard still checks every name and address)."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from hq_egress import media_out as M
from hq_egress.app import State, build_app
from hq_egress.config import Settings, public_host
from hq_egress.guard import Guard
from hq_egress.net import Fetcher
from hq_egress.proxy import Buckets

LOCAL = ipaddress.ip_network("127.0.0.1/32")
BOT = "123456789:AAH" + "x" * 32  # a bot token's shape (fake)
IG = "IGAA" + "Z" * 60  # an Instagram user access token's shape (fake)
HOST = "hq.coinepro.com"
SIGNED = f"https://{HOST}/public/v1/media/" + "s" * 43
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00\x01" * 600
JPG = b"\xff\xd8\xff\xe0" + b"\x10" * 900
PNG = b"\x89PNG\r\n\x1a\n" + b"\x20" * 700


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Fakes:
    """Telegram by chat (@coine_channel ok, @flood_chan 429, @missing_chan not
    found, @norights_ch no rights, @badtoken_ch 401, @boom_channel a server
    error echoing the token); the Graph API by user or container id."""

    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.url.host == "api.telegram.org":
            return self.telegram(request)
        return self.graph(request)

    # ------------------------------------------------------------ telegram --
    def form(self, request: httpx.Request) -> dict[str, Any]:
        ctype = request.headers["content-type"]
        if ctype.startswith("application/json"):
            return dict(json.loads(request.content))
        return {
            k: bytes(v) for k, v in M.parse_multipart(bytearray(request.content), ctype).items()
        }

    def telegram(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        f = self.form(request)
        chat = f.get("chat_id")
        chat = chat.decode() if isinstance(chat, bytes) else chat
        refusals = {
            "@flood_chan": (429, {"ok": False, "error_code": 429,
                                  "description": "Too Many Requests: retry after 17",
                                  "parameters": {"retry_after": 17}}),
            "@missing_chan": (400, {"ok": False, "description": "Bad Request: chat not found"}),
            "@norights_ch": (403, {"ok": False,
                                   "description": "Forbidden: bot is not a member of the channel chat"}),
            "@badtoken_ch": (401, {"ok": False, "description": "Unauthorized"}),
            "@boom_channel": (500, {"ok": False, "description": f"oops /bot{BOT}/x {BOT}"}),
        }  # fmt: skip
        if chat in refusals:
            status, doc = refusals[chat]
            return httpx.Response(status, json=doc)
        msg = {"message_id": 42, "date": 1700000000,
               "chat": {"id": -1001234567890, "type": "channel", "username": "coine_channel"}}  # fmt: skip
        if method == "sendMediaGroup":
            return httpx.Response(200, json={"ok": True, "result": [
                {**msg, "message_id": 43}, {**msg, "message_id": 44}]})  # fmt: skip
        if method in ("sendVideo", "sendPhoto"):
            return httpx.Response(200, json={"ok": True, "result": msg})
        if method == "getChat":
            return httpx.Response(200, json={"ok": True, "result": {
                "id": -1001234567890, "type": "channel", "username": "coine_channel",
                "title": "Coine", "invite_link": "https://t.me/+x"}})  # fmt: skip
        if method == "deleteMessage":
            return httpx.Response(200, json={"ok": True, "result": True})
        return httpx.Response(200, json={"ok": True, "result": {
            "id": 1, "is_bot": True, "username": "coine_media_bot", "first_name": "x"}})  # fmt: skip

    # --------------------------------------------------------------- graph --
    def graph(self, request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == f"Bearer {IG}"
        assert IG not in str(request.url)
        path = request.url.path.split("/")[2:]  # after /v23.0
        if request.method == "GET" and path == ["me"]:
            return httpx.Response(200, json={"user_id": "17841400000000001",
                                             "username": "coine.pro", "id": "9"})  # fmt: skip
        user = path[0]
        errors = {
            "1111": (400, {"error": {"message": f"Invalid OAuth access token {IG}",
                                     "type": "OAuthException", "code": 190}}, {}),
            "2222": (400, {"error": {"message": "Application request limit reached",
                                     "type": "OAuthException", "code": 4}}, {"Retry-After": "60"}),
            "3333": (400, {"error": {"message": "(#10) Application does not have permission",
                                     "type": "OAuthException", "code": 10}}, {}),
            "4444": (400, {"error": {"message": "Invalid parameter", "type": "OAuthException",
                                     "code": 100}}, {}),
        }  # fmt: skip
        if user in errors:
            status, doc, headers = errors[user]
            return httpx.Response(status, json=doc, headers=headers)
        if request.method == "POST" and path[1:] == ["media"]:
            return httpx.Response(200, json={"id": "9001"})
        if request.method == "POST" and path[1:] == ["media_publish"]:
            return httpx.Response(200, json={"id": "18000"})
        if path[1:] == ["content_publishing_limit"]:
            usage = 50 if user == "5555" else 3
            return httpx.Response(200, json={"data": [{"quota_usage": usage,
                                  "config": {"quota_total": 50, "quota_duration": 86400}}]})  # fmt: skip
        if user == "9003":
            return httpx.Response(
                302, headers={"Location": "https://graph.instagram.com/v23.0/9001"}
            )
        if request.url.params.get("fields") == "status_code,status":
            code = {"9001": "FINISHED", "9002": "ERROR", "9004": "IN_PROGRESS"}[user]
            return httpx.Response(
                200, json={"status_code": code, "status": f"{code}: x", "id": user}
            )
        return httpx.Response(200, json={"id": user, "permalink": "https://www.instagram.com/reel/abc/",
                                         "media_type": "VIDEO", "timestamp": "2026-10-23T08:00:00+0000"})  # fmt: skip


@pytest.fixture
async def egress() -> AsyncIterator[tuple[httpx.AsyncClient, Fakes]]:
    table = {"api.telegram.org": ["149.154.167.220"], "graph.instagram.com": ["157.240.0.63"]}

    async def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise OSError("no such name")
        return table[host]

    guard = Guard(hub_hosts=frozenset({HOST}), resolver=resolve)
    fakes = Fakes()
    fetcher = Fetcher(guard, 5)
    await fetcher.http.aclose()
    fetcher.http = httpx.AsyncClient(transport=httpx.MockTransport(fakes), follow_redirects=False)
    settings = Settings(api_clients=(LOCAL,), hub_hosts=frozenset({HOST}), public_host=HOST)
    state = State(settings, guard, Buckets(), fetcher=fetcher)
    transport = httpx.ASGITransport(app=build_app(state), client=("127.0.0.1", 5555))
    async with httpx.AsyncClient(transport=transport, base_url="http://egress") as c:
        yield c, fakes
    await fetcher.aclose()


async def post(
    c: httpx.AsyncClient, call: dict[str, Any], files: dict[str, tuple[bytes, str]] | None = None
) -> httpx.Response:
    parts: dict[str, Any] = {
        "call": (None, json.dumps(call, ensure_ascii=False), "application/json")
    }
    for name, (data, mime) in (files or {}).items():
        parts[name] = (f"{name}.bin", data, mime)
    return await c.post("/v1/media/publish", files=parts)


def tg(method: str, payload: dict[str, Any], files: dict[str, tuple[bytes, str]] | None = None,
       token: str = BOT) -> dict[str, Any]:  # fmt: skip
    meta = [{"part": k, "name": f"{k}.x", "mime": m, "sha256": sha(d)}
            for k, (d, m) in (files or {}).items()]  # fmt: skip
    return {"channel": "telegram", "method": method, "token": token, "payload": payload,
            "files": meta}  # fmt: skip


def ig(method: str, payload: dict[str, Any], token: str = IG) -> dict[str, Any]:
    return {"channel": "instagram", "method": method, "token": token, "payload": payload}


def no_secret(text: str) -> None:
    for s in (BOT, BOT.split(":")[1], IG):
        assert s not in text


CAPTION = "چرا حد ضرر مهم است؟ ترید پرریسک است و ممکن است سرمایه از دست برود. #آموزش"


# ---------------------------------------------------------------- telegram --
async def test_a_reel_goes_to_the_channel_as_a_video_and_the_token_never_comes_back(
    egress: Any, caplog: pytest.LogCaptureFixture
) -> None:
    c, fakes = egress
    caplog.set_level(logging.DEBUG)
    files = {"file0": (MP4, "video/mp4")}
    r = await post(c, tg("sendVideo", {"chat_id": "@coine_channel", "video": "attach://file0",
                                       "caption": CAPTION, "duration": 30, "width": 1080,
                                       "height": 1920, "supports_streaming": True}, files), files)  # fmt: skip
    out = r.json()
    assert (r.status_code, out["outcome"], out["code"]) == (200, "ok", None), out
    assert out["data"] == {"message_id": 42, "chat_id": -1001234567890,
                           "chat_username": "coine_channel", "date": 1700000000}  # fmt: skip
    sent = fakes.seen[-1]
    assert sent.url.path == f"/bot{BOT}/sendVideo"
    form = fakes.form(sent)
    assert form["video"] == MP4 and form["caption"].decode() == CAPTION
    assert form["supports_streaming"] == b"true" and form["width"] == b"1080"
    assert "parse_mode" not in form and "reply_markup" not in form
    assert b'filename="video.mp4"' in sent.content and b"file0.bin" not in sent.content
    [entry] = out["entries"]
    assert entry["tool"] == "media.publish" and entry["host"] == "api.telegram.org"
    assert entry["class"] == "A3" and entry["status"] == 200 and entry["bytes_out"] > len(MP4)
    no_secret(r.text)
    no_secret(caplog.text)


async def test_a_photo_a_media_group_and_a_delete(egress: Any) -> None:
    c, fakes = egress
    one = {"file0": (JPG, "image/jpeg")}
    r = await post(c, tg("sendPhoto", {"chat_id": -1001234567890, "photo": "attach://file0",
                                       "caption": CAPTION}, one), one)  # fmt: skip
    assert r.json()["outcome"] == "ok" and fakes.form(fakes.seen[-1])["photo"] == JPG
    two = {"file0": (PNG, "image/png"), "file1": (MP4, "video/mp4")}
    r = await post(c, tg("sendMediaGroup", {"chat_id": "@coine_channel", "media": [
        {"type": "photo", "media": "attach://file0", "caption": CAPTION},
        {"type": "video", "media": "attach://file1"}]}, two), two)  # fmt: skip
    out = r.json()
    assert out["outcome"] == "ok" and out["data"]["message_ids"] == [43, 44], out
    form = fakes.form(fakes.seen[-1])
    assert form["file0"] == PNG and form["file1"] == MP4
    assert json.loads(form["media"]) == [
        {"type": "photo", "media": "attach://file0", "caption": CAPTION},
        {"type": "video", "media": "attach://file1"},
    ]
    r = await post(c, tg("deleteMessage", {"chat_id": "@coine_channel", "message_id": 42}))
    assert r.json()["outcome"] == "ok" and r.json()["data"] == {"result": True}
    assert json.loads(fakes.seen[-1].content) == {"chat_id": "@coine_channel", "message_id": 42}
    assert r.json()["entries"][0]["class"] == "A3"


async def test_get_me_and_get_chat_are_reads_with_a_few_fields(egress: Any) -> None:
    c, _ = egress
    r = await post(c, tg("getMe", {}))
    assert r.json()["data"] == {"id": 1, "is_bot": True, "username": "coine_media_bot"}
    assert r.json()["entries"][0]["class"] == "A0"
    r = await post(c, tg("getChat", {"chat_id": "@coine_channel"}))
    assert r.json()["data"] == {"id": -1001234567890, "type": "channel",
                                "username": "coine_channel", "title": "Coine"}  # fmt: skip


V = {"file0": (MP4, "video/mp4")}


@pytest.mark.parametrize(
    ("method", "payload", "files", "meta", "code"),
    [
        (
            "sendVideo",
            {
                "chat_id": "@coine_channel",
                "video": "attach://file0",
                "reply_markup": {"inline_keyboard": []},
            },
            V,
            None,
            "payload_not_allowed",
        ),
        (
            "sendVideo",
            {"chat_id": "@coine_channel", "video": "attach://file0", "parse_mode": "HTML"},
            V,
            None,
            "payload_not_allowed",
        ),
        (
            "sendVideo",
            {"chat_id": "coine_channel", "video": "attach://file0"},
            V,
            None,
            "payload_not_allowed",
        ),
        (
            "sendVideo",
            {"chat_id": "@coine_channel", "video": "attach://file0", "caption": "x" * 1025},
            V,
            None,
            "payload_not_allowed",
        ),
        (
            "sendVideo",
            {"chat_id": "@coine_channel", "video": "attach://file1"},
            V,
            None,
            "file_mismatch",
        ),
        (
            "sendPhoto",
            {"chat_id": "@coine_channel", "photo": "attach://file0"},
            V,
            None,
            "file_mismatch",
        ),
        (
            "sendVideo",
            {"chat_id": "@coine_channel", "video": "attach://file0"},
            V,
            [{"part": "file0", "name": "v", "mime": "video/mp4", "sha256": "0" * 64}],
            "file_mismatch",
        ),
        (
            "sendVideo",
            {"chat_id": "@coine_channel", "video": "attach://file0"},
            {"file0": (JPG, "video/mp4")},
            None,
            "file_mismatch",
        ),
        (
            "sendVideo",
            {"chat_id": "@coine_channel", "video": "attach://file0"},
            {},
            [{"part": "file0", "name": "v", "mime": "video/mp4", "sha256": sha(MP4)}],
            "file_mismatch",
        ),
        (
            "sendVideo",
            {"chat_id": "@coine_channel", "video": "attach://file0"},
            {"file0": (MP4, "video/quicktime")},
            None,
            "file_mismatch",
        ),
        ("getMe", {}, V, None, "file_mismatch"),
        (
            "sendMediaGroup",
            {"chat_id": "@coine_channel", "media": [{"type": "video", "media": "attach://file0"}]},
            V,
            None,
            "payload_not_allowed",
        ),
        ("sendStory", {"chat_id": "@coine_channel"}, {}, None, "method_not_allowed"),
        ("postStory", {"chat_id": "@coine_channel"}, {}, None, "method_not_allowed"),
        ("sendMessage", {"chat_id": "@coine_channel", "text": "x"}, {}, None, "method_not_allowed"),
        ("forwardMessage", {"chat_id": "@coine_channel"}, {}, None, "method_not_allowed"),
    ],
)
async def test_telegram_outside_its_allow_lists_is_blocked_before_it_leaves(
    egress: Any, method: str, payload: dict[str, Any], files: dict[str, Any],
    meta: list[dict[str, Any]] | None, code: str,
) -> None:  # fmt: skip
    c, fakes = egress
    call = tg(method, payload, files)
    if meta is not None:
        call["files"] = meta
    r = await post(c, call, files)
    out = r.json()
    assert (out["outcome"], out["code"]) == ("blocked", code), out
    assert fakes.seen == []
    assert out["entries"][0]["blocked_reason"] == code
    no_secret(r.text)


async def test_a_bad_token_shape_is_refused(egress: Any) -> None:
    c, fakes = egress
    r = await post(c, tg("getMe", {}, token="not-a-token"))
    assert (r.json()["outcome"], r.json()["code"]) == ("blocked", "bad_token")
    r = await post(c, ig("me", {}, token="short"))
    assert (r.json()["outcome"], r.json()["code"]) == ("blocked", "bad_token")
    assert fakes.seen == []


async def test_the_size_caps_hold_while_the_body_streams_in(
    egress: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, fakes = egress
    monkeypatch.setattr(M, "VIDEO_MAX", 1000)
    monkeypatch.setattr(M, "PHOTO_MAX", 500)
    for data, mime, field in ((MP4, "video/mp4", "video"), (JPG, "image/jpeg", "photo")):
        f = {"file0": (data, mime)}
        method = "sendVideo" if field == "video" else "sendPhoto"
        r = await post(c, tg(method, {"chat_id": "@coine_channel", field: "attach://file0"}, f), f)
        assert (r.json()["outcome"], r.json()["code"]) == ("blocked", "file_too_large")
    monkeypatch.setattr(M, "MAX_BODY", 2000)
    big = {"file0": (MP4 + b"\x00" * 2000, "video/mp4")}
    r = await post(
        c, tg("sendVideo", {"chat_id": "@coine_channel", "video": "attach://file0"}, big), big
    )
    assert r.status_code == 413 and r.json()["code"] == "too_large"
    assert fakes.seen == []
    no_secret(r.text)


@pytest.mark.parametrize(
    ("chat", "code", "extra"),
    [
        ("@flood_chan", "platform_limit", {"retry_after": 17}),
        ("@missing_chan", "no_channel", {}),
        ("@norights_ch", "no_channel", {}),
        ("@badtoken_ch", "auth_failed", {}),
        ("@boom_channel", "publish_error", {}),
    ],
)
async def test_telegrams_refusals_have_stable_codes_and_never_the_token(
    egress: Any, chat: str, code: str, extra: dict[str, Any]
) -> None:
    c, _ = egress
    f = {"file0": (MP4, "video/mp4")}
    r = await post(c, tg("sendVideo", {"chat_id": chat, "video": "attach://file0"}, f), f)
    out = r.json()
    assert (out["outcome"], out["code"]) == ("error", code), out
    for k, v in extra.items():
        assert out["data"][k] == v
    no_secret(r.text)


# --------------------------------------------------------------- instagram --
async def test_an_instagram_reel_is_a_container_then_a_publish_always_ai_generated(
    egress: Any, caplog: pytest.LogCaptureFixture
) -> None:
    c, fakes = egress
    caplog.set_level(logging.DEBUG)
    r = await post(c, ig("me", {}))
    assert r.json()["data"] == {"user_id": "17841400000000001", "username": "coine.pro", "id": "9"}
    assert fakes.seen[-1].url.params["fields"] == "user_id,username"
    r = await post(c, ig("limit", {"ig_user_id": "17841"}))
    assert r.json()["outcome"] == "ok" and r.json()["data"]["quota_usage"] == 3
    r = await post(c, ig("create", {"ig_user_id": "17841", "media_type": "REELS", "video_url": SIGNED,
                                    "caption": CAPTION, "share_to_feed": True}))  # fmt: skip
    assert r.json() | {"entries": None} == {"outcome": "ok", "code": None,
                                            "data": {"container_id": "9001"}, "entries": None}  # fmt: skip
    assert json.loads(fakes.seen[-1].content) == {
        "is_ai_generated": True, "media_type": "REELS", "video_url": SIGNED,
        "share_to_feed": True, "caption": CAPTION,
    }  # fmt: skip
    assert r.json()["entries"][0]["class"] == "A3"
    r = await post(c, ig("status", {"container_id": "9004"}))
    assert r.json()["data"]["status_code"] == "IN_PROGRESS"
    r = await post(c, ig("status", {"container_id": "9001"}))
    assert r.json()["outcome"] == "ok" and r.json()["data"]["status_code"] == "FINISHED"
    r = await post(c, ig("publish", {"ig_user_id": "17841", "creation_id": "9001"}))
    assert r.json()["data"] == {"media_id": "18000"}
    assert json.loads(fakes.seen[-1].content) == {"creation_id": "9001"}
    r = await post(c, ig("permalink", {"media_id": "18000"}))
    assert r.json()["data"]["permalink"] == "https://www.instagram.com/reel/abc/"
    no_secret(r.text)
    no_secret(caplog.text)


@pytest.mark.parametrize(
    ("payload", "body"),
    [
        (
            {"media_type": "STORIES", "video_url": SIGNED},
            {"is_ai_generated": True, "media_type": "STORIES", "video_url": SIGNED},
        ),
        (
            {"media_type": "STORIES", "image_url": SIGNED},
            {"is_ai_generated": True, "media_type": "STORIES", "image_url": SIGNED},
        ),
        (
            {"media_type": "IMAGE", "image_url": SIGNED, "caption": CAPTION},
            {"is_ai_generated": True, "image_url": SIGNED, "caption": CAPTION},
        ),
        (
            {"media_type": "IMAGE", "image_url": SIGNED, "is_carousel_item": True},
            {"is_ai_generated": True, "image_url": SIGNED, "is_carousel_item": True},
        ),
        (
            {"media_type": "CAROUSEL", "children": ["9001", 9005], "caption": CAPTION},
            {
                "is_ai_generated": True,
                "media_type": "CAROUSEL",
                "children": "9001,9005",
                "caption": CAPTION,
            },
        ),
    ],
)
async def test_instagram_stories_images_and_carousels(
    egress: Any, payload: dict[str, Any], body: dict[str, Any]
) -> None:
    c, fakes = egress
    r = await post(c, ig("create", {"ig_user_id": "17841", **payload}))
    assert r.json()["outcome"] == "ok", r.json()
    assert json.loads(fakes.seen[-1].content) == body


@pytest.mark.parametrize(
    "payload",
    [
        {
            "media_type": "REELS",
            "video_url": "https://evil.example.com/public/v1/media/" + "s" * 43,
        },
        {"media_type": "REELS", "video_url": f"http://{HOST}/public/v1/media/" + "s" * 43},
        {"media_type": "REELS", "video_url": f"https://{HOST}/public/v1/media/short"},
        {"media_type": "REELS", "video_url": SIGNED + "?x=1"},
        {"media_type": "REELS", "video_url": f"https://{HOST}/api/v1/files/abc" + "s" * 30},
        {
            "media_type": "REELS",
            "video_url": f"https://{HOST}.evil.com/public/v1/media/" + "s" * 43,
        },
        {"media_type": "IMAGE", "image_url": f"https://{HOST}/public/v1/media/../../x" + "s" * 30},
    ],
)
async def test_instagram_media_urls_are_only_the_hubs_signed_ones(
    egress: Any, payload: dict[str, Any]
) -> None:
    c, fakes = egress
    r = await post(c, ig("create", {"ig_user_id": "17841", **payload}))
    assert (r.json()["outcome"], r.json()["code"]) == ("blocked", "url_not_allowed"), r.json()
    assert fakes.seen == []


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        (
            "create",
            {
                "ig_user_id": "17841",
                "media_type": "REELS",
                "video_url": SIGNED,
                "image_url": SIGNED,
            },
        ),
        (
            "create",
            {
                "ig_user_id": "17841",
                "media_type": "STORIES",
                "video_url": SIGNED,
                "caption": CAPTION,
            },
        ),
        ("create", {"ig_user_id": "17841", "media_type": "VIDEO", "video_url": SIGNED}),
        (
            "create",
            {
                "ig_user_id": "17841",
                "media_type": "REELS",
                "video_url": SIGNED,
                "is_ai_generated": False,
            },
        ),
        ("create", {"ig_user_id": "17841", "media_type": "CAROUSEL", "children": ["9001"]}),
        ("create", {"ig_user_id": "me/../x", "media_type": "REELS", "video_url": SIGNED}),
        (
            "create",
            {
                "ig_user_id": "17841",
                "media_type": "IMAGE",
                "image_url": SIGNED,
                "caption": "#a " * 31,
            },
        ),
        ("publish", {"ig_user_id": "17841", "creation_id": "9001", "access_token": "x"}),
        ("status", {"container_id": "9001?x"}),
    ],
)
async def test_instagram_outside_its_allow_lists_is_blocked(
    egress: Any, method: str, payload: dict[str, Any]
) -> None:
    c, fakes = egress
    r = await post(c, ig(method, payload))
    assert (r.json()["outcome"], r.json()["code"]) == ("blocked", "payload_not_allowed"), r.json()
    assert fakes.seen == []


async def test_nothing_deletes_on_instagram_and_no_story_has_a_bot_method(egress: Any) -> None:
    c, fakes = egress
    for call in (
        ig("delete", {"media_id": "18000"}),
        tg("sendStory", {"chat_id": "@coine_channel"}),
    ):
        r = await post(c, call)
        assert (r.json()["outcome"], r.json()["code"]) == ("blocked", "method_not_allowed")
    f = {"file0": (MP4, "video/mp4")}
    r = await post(
        c, {**ig("create", {"ig_user_id": "17841"}), "files": tg("x", {}, f)["files"]}, f
    )
    assert (r.json()["outcome"], r.json()["code"]) == ("blocked", "payload_not_allowed")
    assert fakes.seen == []


async def test_without_a_public_host_every_instagram_call_is_refused(egress: Any) -> None:
    c, fakes = egress
    state = c._transport.app.state.egress  # type: ignore[attr-defined]
    state.settings = Settings(api_clients=(LOCAL,), hub_hosts=frozenset({HOST}), public_host="")
    r = await post(c, ig("me", {}))
    assert (r.json()["outcome"], r.json()["code"]) == ("blocked", "public_host_not_configured")
    assert fakes.seen == []
    assert [public_host(x) for x in ("hq.coinepro.com", "https://HQ.coinepro.com", ":80", "",
                                     "hq.coinepro.com:443", "hq.coinepro.com:8443", "localhost")] == [
        HOST, HOST, "", "", HOST, "", ""]  # fmt: skip


@pytest.mark.parametrize(
    ("method", "payload", "code", "extra"),
    [
        (
            "create",
            {"ig_user_id": "1111", "media_type": "REELS", "video_url": SIGNED},
            "auth_failed",
            {"error_code": 190},
        ),
        (
            "create",
            {"ig_user_id": "2222", "media_type": "REELS", "video_url": SIGNED},
            "platform_limit",
            {"retry_after": 60},
        ),
        (
            "create",
            {"ig_user_id": "3333", "media_type": "REELS", "video_url": SIGNED},
            "no_channel",
            {"error_code": 10},
        ),
        (
            "create",
            {"ig_user_id": "4444", "media_type": "REELS", "video_url": SIGNED},
            "publish_error",
            {"error_code": 100},
        ),
        ("status", {"container_id": "9002"}, "publish_error", {"status_code": "ERROR"}),
        ("limit", {"ig_user_id": "5555"}, "platform_limit", {"quota_usage": 50, "quota_total": 50}),
    ],
)
async def test_instagrams_refusals_have_stable_codes_and_never_the_token(
    egress: Any, method: str, payload: dict[str, Any], code: str, extra: dict[str, Any]
) -> None:
    c, _ = egress
    r = await post(c, ig(method, payload))
    out = r.json()
    assert (out["outcome"], out["code"]) == ("error", code), out
    for k, v in extra.items():
        assert out["data"][k] == v
    no_secret(r.text)


async def test_no_redirect_is_followed(egress: Any) -> None:
    c, fakes = egress
    r = await post(c, ig("status", {"container_id": "9003"}))
    out = r.json()
    assert (out["outcome"], out["code"]) == ("blocked", "redirect_not_allowed"), out
    assert len(fakes.seen) == 1
    assert out["entries"][-1]["blocked_reason"] == "redirect_not_allowed"


# ------------------------------------------------------------- the request --
async def test_a_request_that_is_not_one_call_is_invalid_and_echoes_nothing(egress: Any) -> None:
    c, fakes = egress
    r = await c.post("/v1/media/publish", json=tg("getMe", {}))
    assert r.status_code == 422 and r.json()["code"] == "invalid_args"
    r = await c.post("/v1/media/publish", files={"file0": ("a", MP4, "video/mp4")})
    assert r.status_code == 422
    r = await c.post("/v1/media/publish",
                     files={"call": (None, '{"channel": "sms", "token": "' + BOT + '"}')})  # fmt: skip
    assert r.status_code == 422
    no_secret(r.text)
    assert fakes.seen == []


async def test_only_the_api_network_may_call_it(egress: Any) -> None:
    c, _ = egress
    state = c._transport.app.state.egress  # type: ignore[attr-defined]
    outside = httpx.ASGITransport(app=build_app(state), client=("172.30.9.5", 1))
    async with httpx.AsyncClient(transport=outside, base_url="http://egress") as o:
        r = await post(o, tg("getMe", {}))
    assert r.status_code == 403


def test_the_multipart_reader_keeps_views_of_one_buffer() -> None:
    body = bytearray(
        b'--b1\r\nContent-Disposition: form-data; name="call"\r\n\r\n{}\r\n'
        b'--b1\r\nContent-Disposition: form-data; name="file0"; filename="x"\r\n'
        b"Content-Type: video/mp4\r\n\r\n" + MP4 + b"\r\n--b1--\r\n"
    )
    parts = M.parse_multipart(body, 'multipart/form-data; boundary="b1"')
    assert bytes(parts["call"]) == b"{}" and bytes(parts["file0"]) == MP4
    assert parts["file0"].obj is body
    for bad in (b"garbage", body.replace(b"--b1--", b"--b1xx"),
                body.replace(b'name="file0"', b'name="call"')):  # fmt: skip
        with pytest.raises(M.Refused):
            M.parse_multipart(bytearray(bad), "multipart/form-data; boundary=b1")
    with pytest.raises(M.Refused):
        M.parse_multipart(body, "application/json")
