"""Minimal OpenBao client: AppRole login and KV v2 reads.

The AppRole credentials come from a JSON file mounted read-only into the
container ({"role_id": ..., "secret_id": ...}). The client token is kept in
memory only and renewed by logging in again when it expires.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx


class OpenBaoError(RuntimeError):
    pass


class SecretNotFound(OpenBaoError):
    pass


class OpenBaoClient:
    def __init__(
        self,
        addr: str,
        approle_file: str | Path,
        *,
        kv_mount: str = "kv",
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._addr = addr.rstrip("/")
        self._approle_file = Path(approle_file)
        self._kv_mount = kv_mount
        self._http = httpx.AsyncClient(base_url=self._addr, timeout=timeout, transport=transport)
        self._token: str | None = None
        self._token_expires_at = 0.0

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _login(self) -> None:
        try:
            creds = json.loads(self._approle_file.read_text())
        except (OSError, ValueError) as exc:
            raise OpenBaoError(f"cannot read AppRole file {self._approle_file}") from exc
        resp = await self._http.post(
            "/v1/auth/approle/login",
            json={"role_id": creds["role_id"], "secret_id": creds["secret_id"]},
        )
        if resp.status_code != 200:
            raise OpenBaoError(f"AppRole login failed (HTTP {resp.status_code})")
        auth = resp.json()["auth"]
        self._token = auth["client_token"]
        # Renew a minute early (or halfway through very short TTLs).
        ttl = int(auth.get("lease_duration") or 0)
        self._token_expires_at = time.time() + max(ttl - 60, ttl // 2)

    async def _headers(self) -> dict[str, str]:
        if self._token is None or time.time() >= self._token_expires_at:
            await self._login()
        assert self._token is not None
        return {"X-Vault-Token": self._token}

    async def read_kv(self, path: str) -> dict[str, Any]:
        """Read the latest version of a KV v2 secret (`path` relative to the mount)."""
        data, _ = await self.read_kv_meta(path)
        return data

    async def read_kv_meta(self, path: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """The latest version of a KV v2 secret and its version metadata
        (`created_time`, `version`, ...): when the value was written."""
        for attempt in (1, 2):
            resp = await self._http.get(
                f"/v1/{self._kv_mount}/data/{path}", headers=await self._headers()
            )
            if resp.status_code == 403 and attempt == 1:
                self._token = None  # token revoked or expired early: log in again
                continue
            if resp.status_code == 404:
                raise SecretNotFound(path)
            if resp.status_code != 200:
                raise OpenBaoError(f"KV read {path} failed (HTTP {resp.status_code})")
            body = resp.json()["data"]
            data: dict[str, Any] = body["data"]
            meta: dict[str, Any] = body.get("metadata") or {}
            return data, meta
        raise OpenBaoError(f"KV read {path} failed after re-login")

    async def write_kv(self, path: str, data: dict[str, Any]) -> None:
        """Write a new version of a KV v2 secret. The value never appears in an
        error message (only the path and the HTTP status)."""
        for attempt in (1, 2):
            resp = await self._http.post(
                f"/v1/{self._kv_mount}/data/{path}",
                json={"data": data},
                headers=await self._headers(),
            )
            if resp.status_code == 403 and attempt == 1:
                self._token = None
                continue
            if resp.status_code not in (200, 204):
                raise OpenBaoError(f"KV write {path} failed (HTTP {resp.status_code})")
            return
        raise OpenBaoError(f"KV write {path} failed after re-login")

    async def _transit(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """One call to the transit engine (prompt 14 §3). Neither the key nor
        any plaintext ever appears in an error: only the path and the status."""
        for attempt in (1, 2):
            resp = await self._http.post(
                f"/v1/transit/{path}", json=body, headers=await self._headers()
            )
            if resp.status_code == 403 and attempt == 1:
                self._token = None
                continue
            if resp.status_code != 200:
                raise OpenBaoError(f"transit {path.split('/')[0]} failed (HTTP {resp.status_code})")
            data: dict[str, Any] = resp.json()["data"]
            return data
        raise OpenBaoError(f"transit {path.split('/')[0]} failed after re-login")

    async def transit_datakey(self, key: str) -> tuple[bytes, str]:
        """A fresh 256-bit data key: (its bytes, the same key wrapped by the
        transit key `key`). The transit key itself never leaves OpenBao."""
        import base64

        data = await self._transit(f"datakey/plaintext/{key}", {"bits": 256})
        return base64.b64decode(data["plaintext"]), str(data["ciphertext"])

    async def transit_decrypt(self, key: str, ciphertext: str) -> bytes:
        """A wrapped data key back as bytes (for one read, never stored)."""
        import base64

        data = await self._transit(f"decrypt/{key}", {"ciphertext": ciphertext})
        return base64.b64decode(data["plaintext"])
