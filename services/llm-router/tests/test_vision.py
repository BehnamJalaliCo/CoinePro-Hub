"""Images a model may see (prompt 06 §2, contract §17.1): content blocks of
bytes only, strictly checked, passed to every backend, never ledgered."""

from __future__ import annotations

import base64
import json
from typing import Any

import asyncpg
import pytest
from pydantic import ValidationError

from hq_common import vision
from llm_router.backends import claude_runtime, litellm_backend
from llm_router.backends.base import BackendCall, ChatMessage, ImagePart
from llm_router.backends.fake import FakeBackend as Fake
from llm_router.schemas import RunRequest

from .conftest import FakeBackend
from .test_api_and_backends import BODY, auth, client, make_state

# The smallest valid PNG (1x1, transparent), JPEG and WebP headers: tests only
# check magic bytes, so a header plus padding stands for a bigger picture.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 60
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 40


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def image(data: bytes = PNG, media_type: str = "image/png") -> dict[str, str]:
    return {"type": "image", "media_type": media_type, "data": b64(data)}


def req(*content: Any, **kw: Any) -> RunRequest:
    base: dict[str, Any] = {
        "company_code": "TY",
        "actor_ref": "TY-TECH-01",
        "department": "TECH",
        "task_class": "general",
        "priority": 2,
        "messages": [{"role": "user", "content": list(content)}],
        "timeout_s": 30,
    }
    base.update(kw)
    return RunRequest(**base)


def test_blocks_are_checked_strictly() -> None:
    r = req({"type": "text", "text": "این عکس چیست؟"}, image(), image(JPEG, "image/jpeg"))
    assert [i.media_type for i in r.images()] == ["image/png", "image/jpeg"]
    assert r.input_chars() == len("این عکس چیست؟")  # text only
    assert r.images()[0].size == len(PNG)
    assert "data=" not in repr(r.images()[0])  # bytes never in a repr (logs)
    bad: list[tuple[Any, ...]] = [
        (image(PNG, "image/jpeg"),),  # bytes are not what the type says
        (image(b"GIF89a" + b"\x00" * 20, "image/png"),),  # not an allowed format
        ({"type": "image", "media_type": "image/png", "data": "not base64!"},),
        ({"type": "image", "media_type": "image/gif", "data": b64(PNG)},),
        ({"type": "image", "media_type": "image/png", "data": b64(PNG), "url": "http://x"},),
        ({"type": "image_url", "image_url": {"url": "https://x/y.png"}},),  # no URLs, ever
        (image(PNG[:8] + b"\x00" * (vision.MAX_IMAGE_BYTES + 1)),),  # over 5 MiB
        tuple(image() for _ in range(vision.MAX_IMAGES + 1)),  # over 20 images
    ]
    for content in bad:
        with pytest.raises(ValidationError):
            req(*content)
    with pytest.raises(ValidationError):  # 20 MiB together
        req(*[image(PNG[:8] + b"\x00" * (vision.MAX_IMAGE_BYTES - 8)) for _ in range(5)])
    with pytest.raises(ValidationError):  # images come from the user only
        RunRequest(
            **{
                **BODY,
                "prompt": None,
                "messages": [
                    {"role": "assistant", "content": [image()]},
                    {"role": "user", "content": "x"},
                ],
            }
        )
    with pytest.raises(ValidationError):
        RunRequest(**{**BODY, "prompt": None, "messages": [{"role": "user", "content": []}]})
    assert vision.sniff(WEBP) == "image/webp" and vision.sniff(b"") is None


def test_backends_get_the_blocks_in_order() -> None:
    m = req({"type": "text", "text": "اول"}, image(), {"type": "text", "text": "دوم"}).messages
    assert m is not None
    parts = m[0].parts()
    assert parts[0] == "اول" and isinstance(parts[1], ImagePart) and parts[2] == "دوم"
    msg = ChatMessage("user", m[0].text(), parts)
    assert msg.content == "اول\n\nدوم"
    assert claude_runtime._content(msg) == [
        {"type": "text", "text": "اول"},
        {"type": "image", "media_type": "image/png", "data": b64(PNG)},
        {"type": "text", "text": "دوم"},
    ]
    lite = litellm_backend._content(msg)
    assert isinstance(lite, list) and lite[1] == {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{b64(PNG)}"},
    }
    plain = ChatMessage("user", "فقط متن")
    assert claude_runtime._content(plain) == litellm_backend._content(plain) == "فقط متن"
    conn: Any = None
    call = BackendCall("c", conn, "m", None, None, (msg,), None, 10, "TY-TECH-01")
    fake = Fake()
    out = fake._result(call)
    assert out.usage is not None and out.usage.input_tokens >= vision.TOKENS_PER_IMAGE
    assert fake.calls[0].messages[0].parts == parts


async def test_the_router_passes_images_and_never_ledgers_them(
    su: asyncpg.Connection, make_service: Any
) -> None:
    backend = FakeBackend()
    svc = make_service(subscription=backend)
    r = req({"type": "text", "text": "این عکس"}, image(), store_transcript=True)
    resp = await svc.run(r, "t", 10_000)
    assert resp.status == "ok"
    sent = backend.calls[0].messages[-1]
    assert sent.content == "این عکس" and isinstance(sent.parts[1], ImagePart)
    row = await su.fetchrow("SELECT meta FROM llm.calls WHERE id = $1", resp.call_id)
    assert json.loads(row["meta"])["images"] == 1
    t = await su.fetchrow("SELECT request FROM llm.transcripts WHERE call_id = $1", resp.call_id)
    stored = json.loads(t["request"])
    assert b64(PNG) not in json.dumps(stored)
    assert stored["messages"][0]["content"][1] == {
        "type": "image",
        "media_type": "image/png",
        "bytes": len(PNG),
    }


async def test_a_request_with_images_fits_the_body_cap(
    su: asyncpg.Connection, settings: Any, make_service: Any
) -> None:
    state = make_state(settings, make_service())
    big = PNG[:8] + b"\x00" * (3 * 1024 * 1024)  # a 3 MiB picture, ~4 MiB in base64
    body = {
        **BODY,
        "prompt": None,
        "messages": [{"role": "user", "content": [{"type": "text", "text": "ببین"}, image(big)]}],
    }
    async with client(state) as c:
        r = await c.post("/v1/run", headers=auth(), json=body)
        assert r.status_code == 200, r.text[:200]
        bad = await c.post(
            "/v1/run",
            headers=auth(),
            json={**body, "messages": [{"role": "user", "content": [image(PNG, "image/webp")]}]},
        )
        assert bad.status_code == 422 and b64(PNG) not in bad.text
