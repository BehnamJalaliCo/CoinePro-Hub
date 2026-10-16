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
            data: dict[str, Any] = resp.json()["data"]["data"]
            return data
        raise OpenBaoError(f"KV read {path} failed after re-login")
