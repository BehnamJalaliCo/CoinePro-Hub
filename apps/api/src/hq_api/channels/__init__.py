"""Delivery channels (contract §6): in-app (the stream), Web Push (VAPID),
FCM (Android) and Telegram (backup only). A channel without credentials is
simply off. Payloads carry a title, the level and a link, never a body or a
secret. Called only after the notification's transaction has committed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from hq_api.channels.fcm import FcmChannel
from hq_api.channels.telegram import TelegramChannel
from hq_api.channels.webpush import WebPushChannel, generate_vapid_keys
from hq_api.errors import ApiError

if TYPE_CHECKING:
    from hq_api.hub import Hub

log = logging.getLogger("hq_api.channels")

__all__ = ["Channels", "PushMessage", "generate_vapid_keys"]


@dataclass(frozen=True)
class PushMessage:
    title: str
    level: str
    company: str | None = None
    link_kind: str | None = None
    link_ref: str | None = None
    sound: bool = False
    count: int = 1

    def data(self) -> dict[str, str]:
        """The only fields a push may carry."""
        out = {"title": self.title, "level": self.level, "count": str(self.count)}
        for key in ("company", "link_kind", "link_ref"):
            value = getattr(self, key)
            if value:
                out[key] = str(value)
        if self.sound:
            out["sound"] = "1"
        return out


class Channels:
    def __init__(self, hub: Hub, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._hub = hub
        self._http = httpx.AsyncClient(timeout=10.0, transport=transport)
        self.web_push = WebPushChannel(hub, self._http)
        self.fcm = FcmChannel(hub, self._http)
        self.telegram = TelegramChannel(hub, self._http)

    async def aclose(self) -> None:
        await self._http.aclose()

    def status(self) -> dict[str, bool]:
        return {
            "in_app": True,
            "web_push": self.web_push.configured,
            "fcm": self.fcm.configured,
            "telegram": self.telegram.configured,
        }

    async def push(self, msg: PushMessage) -> dict[str, bool]:
        """Fan out to every configured push channel; True = at least one device got it."""
        result = {"web_push": False, "fcm": False, "telegram": False}
        for name, channel in (
            ("web_push", self.web_push),
            ("fcm", self.fcm),
            ("telegram", self.telegram),
        ):
            if not channel.configured:
                continue
            try:
                result[name] = await channel.send(msg)
            except ApiError:
                result[name] = False
            except Exception as exc:  # noqa: BLE001 - one channel failing never blocks the others
                log.warning(
                    "push channel failed", extra={"channel": name, "error": type(exc).__name__}
                )
        return result
