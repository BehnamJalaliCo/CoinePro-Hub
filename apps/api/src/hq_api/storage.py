"""File storage behind one interface (prompt 04 §2: local volume hq-files
today, an S3 backend later). Keys are opaque; the tenant check happens on
files.files before any byte is read."""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    async def put(self, data: bytes) -> tuple[str, str]:
        """Store bytes -> (storage_key, sha256)."""
        ...

    async def get(self, key: str) -> bytes: ...


class LocalStorage:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, key: str) -> Path:
        if not key or "/" in key or ".." in key:
            raise ValueError("bad storage key")
        return self._root / key[:2] / key

    async def put(self, data: bytes) -> tuple[str, str]:
        key = uuid.uuid4().hex
        sha = hashlib.sha256(data).hexdigest()
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            tmp = path.with_suffix(".tmp")
            with open(tmp, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            tmp.replace(path)

        await asyncio.to_thread(write)
        return key, sha

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)
