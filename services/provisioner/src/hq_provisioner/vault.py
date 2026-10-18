"""OpenBao, read at the moment of work (synchronous: the provisioner's steps
are a thread). Its AppRole may only read kv/provisioning/* and its own api
token at kv/provisioner/config.

kv/provisioning/hetzner   {token}            (the owner: make hetzner-token)
kv/provisioning/ssh-keys  {keys: [public]}   (the owner: make owner-ssh-key)
kv/provisioner/config     {api_token}        (provision.sh; its digest is in hq-api)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import httpx

from hq_common.openbao import OpenBaoError, SecretNotFound

HETZNER = "provisioning/hetzner"
SSH_KEYS = "provisioning/ssh-keys"
CONFIG = "provisioner/config"
PUBLIC_KEY_TYPES = (
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
)


class NotConfigured(Exception):
    """The owner has not given it yet (make hetzner-token / make owner-ssh-key)."""


class Secrets(Protocol):
    def hetzner_token(self) -> str: ...
    def owner_keys(self) -> list[str]: ...
    def api_token(self) -> str: ...


def public_keys(raw: Any) -> list[str]:
    """The owner's public keys, each one line and one known type; anything
    else (a private key, an option, a second line) is dropped."""
    out: list[str] = []
    for item in raw if isinstance(raw, list) else []:
        key = str(item).strip()
        parts = key.split()
        if (
            "\n" in key
            or "PRIVATE" in key.upper()
            or len(parts) < 2
            or parts[0] not in PUBLIC_KEY_TYPES
            or len(key) > 2000
        ):
            continue
        if key not in out:
            out.append(key)
    return out


class Vault:
    def __init__(
        self, addr: str, approle_file: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.addr = addr.rstrip("/")
        self.approle_file = Path(approle_file)
        self.transport = transport

    def _read(self, path: str) -> dict[str, Any]:
        try:
            creds = json.loads(self.approle_file.read_text())
        except (OSError, ValueError) as exc:
            raise OpenBaoError("cannot read the AppRole file") from exc
        with httpx.Client(base_url=self.addr, timeout=10, transport=self.transport) as c:
            r = c.post(
                "/v1/auth/approle/login",
                json={"role_id": creds["role_id"], "secret_id": creds["secret_id"]},
            )
            if r.status_code != 200:
                raise OpenBaoError(f"AppRole login failed (HTTP {r.status_code})")
            token = r.json()["auth"]["client_token"]
            r = c.get(f"/v1/kv/data/{path}", headers={"X-Vault-Token": token})
            # A short-lived login per read: nothing stays in memory between steps.
            c.post("/v1/auth/token/revoke-self", headers={"X-Vault-Token": token})
        if r.status_code == 404:
            raise SecretNotFound(path)
        if r.status_code != 200:
            raise OpenBaoError(f"KV read {path} failed (HTTP {r.status_code})")
        data: dict[str, Any] = r.json()["data"]["data"]
        return data

    def hetzner_token(self) -> str:
        try:
            token = str(self._read(HETZNER).get("token") or "")
        except SecretNotFound as exc:
            raise NotConfigured("no Hetzner API token yet (make hetzner-token)") from exc
        if not token:
            raise NotConfigured("no Hetzner API token yet (make hetzner-token)")
        return token

    def owner_keys(self) -> list[str]:
        try:
            keys = public_keys(self._read(SSH_KEYS).get("keys"))
        except SecretNotFound as exc:
            raise NotConfigured("no SSH public key of the owner yet (make owner-ssh-key)") from exc
        if not keys:
            raise NotConfigured("no SSH public key of the owner yet (make owner-ssh-key)")
        return keys

    def api_token(self) -> str:
        token = str(self._read(CONFIG).get("api_token") or "")
        if not token:
            raise NotConfigured("no api token for the provisioner (make up provisions it)")
        return token
