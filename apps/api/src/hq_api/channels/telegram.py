"""Telegram bot: a backup channel only. It carries an alert line and "open
the app" - never an approve/reject action, a button or a link that acts:
no approval is ever possible from Telegram (contract §6)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from hq_api.errors import ApiError

if TYPE_CHECKING:
    from hq_api.channels import PushMessage
    from hq_api.hub import Hub

log = logging.getLogger("hq_api.channels.telegram")
API = "https://api.telegram.org"
MARK = {"urgent": "🔴", "decision": "🟡", "report": "🔵", "info": "🟢", "learning": "🟣"}
FOOTER = "برای جزئیات، اپ CoinePro HQ را باز کن. (فقط اطلاع؛ تأیید از تلگرام ممکن نیست.)"


def render(msg: PushMessage) -> str:
    company = f" [{msg.company}]" if msg.company else ""
    return f"{MARK.get(msg.level, '')} {msg.title}{company}\n{FOOTER}"


class TelegramChannel:
    def __init__(self, hub: Hub, http: httpx.AsyncClient) -> None:
        self._hub = hub
        self._http = http

    @property
    def configured(self) -> bool:
        return self._hub.secrets.telegram_ready

    async def send(self, msg: PushMessage) -> bool:
        if not self.configured:
            raise ApiError(503, "channel_not_configured", "telegram")
        sec = self._hub.secrets
        try:
            resp = await self._http.post(
                f"{API}/bot{sec.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": sec.telegram_chat_id,
                    "text": render(msg),
                    "disable_web_page_preview": True,
                    "disable_notification": not msg.sound,
                },
            )
        except httpx.HTTPError as exc:
            # The URL carries the bot token: only the error type is logged.
            log.warning("telegram send failed", extra={"error": type(exc).__name__})
            return False
        return resp.status_code == 200
