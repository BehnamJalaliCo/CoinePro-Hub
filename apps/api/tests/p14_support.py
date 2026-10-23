"""Shared helpers of the prompt 14 (archive) tests: fakes for OpenBao transit
and the OCR service, uploads, the archive's own step-ups, records."""

from __future__ import annotations

import hashlib
import io
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx

from hq_api.archive import ocr as OCR
from hq_api.archive import store as ST
from hq_api.archive.jobs import _pdf_overlay
from hq_api.hub import Hub

from .conftest import idem, step_up

SAMPLES = Path("/w/ocr/tests/samples")
SEED_WORDS = "abandon ability able about above absent absorb abstract absurd abuse access accident"


class FakeVault:
    """OpenBao transit in a dict: a fresh key per file, wrapped as an opaque id."""

    def __init__(self) -> None:
        self.keys: dict[str, bytes] = {}
        self.unwraps = 0

    async def new_key(self) -> tuple[bytes, str]:
        dek = os.urandom(32)
        wrapped = f"vault:v1:{uuid.uuid4().hex}"
        self.keys[wrapped] = dek
        return dek, wrapped

    async def unwrap(self, wrapped: str) -> bytes:
        self.unwraps += 1
        return self.keys[wrapped]


class FakeOcr:
    """The OCR service: the text it would read, by the bytes' sha256."""

    def __init__(self) -> None:
        self.texts: dict[str, str] = {}
        self.calls = 0

    def learn(self, data: bytes, text: str) -> None:
        self.texts[hashlib.sha256(data).hexdigest()] = text

    async def run(self, data: bytes, mime: str) -> dict[str, Any]:
        self.calls += 1
        text = self.texts.get(hashlib.sha256(data).hexdigest(), "")
        return {
            "state": "ok",
            "pages": [
                {
                    "n": 1,
                    "text": text,
                    "confidence": 0.91 if text else 0.0,
                    "words": len(text.split()),
                }
            ],
            "confidence": 0.91 if text else 0.0,
            "engine": {"name": "tesseract", "version": "fake"},
        }


@asynccontextmanager
async def fakes(ocr: bool = True) -> AsyncIterator[tuple[FakeVault, FakeOcr | None]]:
    v = FakeVault()
    o = FakeOcr() if ocr else None
    ST.OVERRIDE_VAULT, OCR.OVERRIDE = v, o
    try:
        yield v, o
    finally:
        ST.OVERRIDE_VAULT, OCR.OVERRIDE = None, None


def pdf(text: str) -> bytes:
    """A small PDF whose text layer holds `text` (ASCII)."""
    return _pdf_overlay(595.0, 842.0, text)


def png(seed: int = 0) -> bytes:
    from PIL import Image

    img = Image.new("RGB", (64 + seed % 7, 48), (200, 180 + seed % 50, 160))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


async def upload(
    client: httpx.AsyncClient, headers: dict[str, str], data: bytes, mime: str, name: str = "doc"
) -> str:
    r = await client.post(
        "/api/v1/files",
        content=data,
        headers={**headers, **idem(), "Content-Type": mime, "X-File-Name": name},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def body_bytes(body: Any) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode()


async def schema_put(
    client: httpx.AsyncClient,
    hub: Hub,
    session: dict[str, Any],
    part: str,
    key: str,
    body: Any,
    *,
    version: int | None = None,
    action: str = "archive.schema",
    dry_run: bool = False,
    stepped: bool = True,
) -> httpx.Response:
    content = body_bytes(body)
    headers = {**session["headers"], "Content-Type": "application/json"}
    if version is None:
        headers["If-None-Match"] = "*"
    else:
        headers["If-Match"] = str(version)
    if stepped and not dry_run:
        headers.update(
            await step_up(hub, session["session_id"], action, hashlib.sha256(content).hexdigest())
        )
    return await client.put(
        f"/api/v1/archive/schema/{part}/{key}" + ("?dry_run=1" if dry_run else ""),
        content=content,
        headers=headers,
    )


async def record(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    scope: str,
    cls: str,
    title: str,
    metadata: dict[str, Any],
    file_ids: list[str],
    level: str | None = None,
    file: bool = True,
    parties: list[dict[str, str]] | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {
        "scope": scope,
        "class": cls,
        "title_fa": title,
        "metadata": metadata,
        "file_ids": file_ids,
        "file": file,
    }
    if level:
        body["level"] = level
    if parties:
        body["parties"] = parties
    return await client.post("/api/v1/archive/records", json=body, headers={**headers, **idem()})


async def filed(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    scope: str,
    *,
    title: str = "سند آزمایشی",
    text: str = "a document",
    level: str | None = None,
    cls: str = "other",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fid = await upload(client, headers, pdf(text), "application/pdf", "doc.pdf")
    r = await record(
        client,
        headers,
        scope=scope,
        cls=cls,
        title=title,
        metadata=metadata or {"subject": title},
        file_ids=[fid],
        level=level,
    )
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


def stored_path(hub: Hub, key: str) -> Path:
    return hub.storage.local_path(key)


def txf(hub: Hub) -> Callable[[], Any]:
    from hq_api.archive.common import wide_txf

    return wide_txf(hub)
