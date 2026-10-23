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

    def scratch(self) -> Path:
        """A new temporary path on the same volume (for a streamed upload)."""
        ...

    async def commit(self, tmp: Path) -> tuple[str, str, int]:
        """Move a finished temporary file in -> (storage_key, sha256, size)."""
        ...

    def local_path(self, key: str) -> Path:
        """Where the bytes are (ffmpeg, Range reads); S3 would download first."""
        ...

    async def destroy(self, key: str) -> bool:
        """The bytes are gone (prompt 14 §5: a disposal the owner sealed, an
        archive intake that took an upload over, a secret refused). True when
        there was something to remove."""
        ...


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

    def scratch(self) -> Path:
        tmp = self._root / "tmp"
        tmp.mkdir(parents=True, exist_ok=True, mode=0o700)
        return tmp / f"{uuid.uuid4().hex}.part"

    async def commit(self, tmp: Path) -> tuple[str, str, int]:
        key = uuid.uuid4().hex
        path = self._path(key)

        def move() -> tuple[str, int]:
            digest = hashlib.sha256()
            size = 0
            with open(tmp, "rb") as fh:
                for block in iter(lambda: fh.read(1024 * 1024), b""):
                    digest.update(block)
                    size += len(block)
                os.fsync(fh.fileno())
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            tmp.replace(path)
            return digest.hexdigest(), size

        sha, size = await asyncio.to_thread(move)
        return key, sha, size

    def local_path(self, key: str) -> Path:
        return self._path(key)

    async def destroy(self, key: str) -> bool:
        path = self._path(key)

        def remove() -> bool:
            try:
                path.unlink()
            except FileNotFoundError:
                return False
            return True

        return await asyncio.to_thread(remove)
