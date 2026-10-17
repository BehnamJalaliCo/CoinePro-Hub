"""Secrets from OpenBao (never logged, never returned by any endpoint).

kv/hq-api/config            agent_token_key (hex), service_tokens {name: sha256}
kv/hq-api/webpush           private_key_pem, public_key (base64url), subject
kv/hq-api/channels/fcm      service_account_json (empty -> channel off)
kv/hq-api/channels/telegram bot_token, chat_id (empty -> channel off)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from hq_common.openbao import OpenBaoClient, OpenBaoError, SecretNotFound

log = logging.getLogger("hq_api.secrets")


@dataclass
class Secrets:
    agent_token_key: bytes = field(default=b"", repr=False)
    service_tokens: dict[str, str] = field(default_factory=dict, repr=False)
    vapid_private_pem: str = field(default="", repr=False)
    vapid_public_key: str = ""
    vapid_subject: str = ""
    fcm_service_account: dict[str, Any] | None = field(default=None, repr=False)
    telegram_bot_token: str = field(default="", repr=False)
    telegram_chat_id: str = field(default="", repr=False)

    @property
    def web_push_ready(self) -> bool:
        return bool(self.vapid_private_pem and self.vapid_public_key)

    @property
    def fcm_ready(self) -> bool:
        return bool(self.fcm_service_account and self.fcm_service_account.get("project_id"))

    @property
    def telegram_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


async def _read(bao: OpenBaoClient, path: str) -> dict[str, Any]:
    try:
        return await bao.read_kv(path)
    except SecretNotFound:
        return {}


async def load(bao: OpenBaoClient, *, api_config: bool = True) -> Secrets:
    """`api_config=False` for the worker: it needs only the push channels and its
    OpenBao policy (hq-worker) does not grant kv/hq-api/config."""
    try:
        cfg = await _read(bao, "hq-api/config") if api_config else {}
        push = await _read(bao, "hq-api/webpush")
        fcm = await _read(bao, "hq-api/channels/fcm")
        tg = await _read(bao, "hq-api/channels/telegram")
    except OpenBaoError:
        log.warning("openbao unavailable; secrets not (re)loaded")
        raise
    sa_raw = str(fcm.get("service_account_json") or "")
    sa: dict[str, Any] | None = None
    if sa_raw:
        try:
            sa = json.loads(sa_raw)
        except ValueError:
            log.warning("fcm service account is not valid JSON; channel stays off")
    return Secrets(
        agent_token_key=bytes.fromhex(str(cfg.get("agent_token_key") or "")),
        service_tokens={str(k): str(v) for k, v in (cfg.get("service_tokens") or {}).items()},
        vapid_private_pem=str(push.get("private_key_pem") or ""),
        vapid_public_key=str(push.get("public_key") or ""),
        vapid_subject=str(push.get("subject") or ""),
        fcm_service_account=sa,
        telegram_bot_token=str(tg.get("bot_token") or ""),
        telegram_chat_id=str(tg.get("chat_id") or ""),
    )
