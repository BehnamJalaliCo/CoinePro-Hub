"""NATS JetStream events: metadata only, never prompt or response text.

Subjects (company code in the subject, so the future live stream can
subscribe per company):
    hq.llm.<COMPANY>.call.started
    hq.llm.<COMPANY>.call.finished
    hq.alerts.budget.<COMPANY>
    hq.alerts.llm.anomaly
    hq.alerts.llm.cost_ratio   (SDK estimate vs our price table, see cost_ratio.py)
A publish failure never fails a call; it is counted and logged.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import nats
from nats.js.api import RetentionPolicy, StorageType, StreamConfig

log = logging.getLogger("llm_router.events")

STREAMS = (
    StreamConfig(
        name="HQ_LLM",
        subjects=["hq.llm.>"],
        retention=RetentionPolicy.LIMITS,
        storage=StorageType.FILE,
        max_age=7 * 24 * 3600,
        max_bytes=512 * 1024 * 1024,
    ),
    StreamConfig(
        name="HQ_ALERTS",
        subjects=["hq.alerts.>"],
        retention=RetentionPolicy.LIMITS,
        storage=StorageType.FILE,
        max_age=30 * 24 * 3600,
        max_bytes=256 * 1024 * 1024,
    ),
)


class Events:
    def __init__(self, url: str, user: str, password: str, on_failure: Any = None) -> None:
        self._url, self._user, self._password = url, user, password
        self._nc: Any = None
        self._js: Any = None
        self._on_failure = on_failure

    @property
    def connected(self) -> bool:
        return bool(self._nc is not None and self._nc.is_connected)

    async def connect(self) -> None:
        self._nc = await nats.connect(
            self._url,
            user=self._user,
            password=self._password,
            name="llm-router",
            max_reconnect_attempts=-1,
            connect_timeout=5,
        )
        self._js = self._nc.jetstream()
        for cfg in STREAMS:
            try:
                await self._js.add_stream(cfg)
            except Exception:  # noqa: BLE001 - exists with other settings: update it
                await self._js.update_stream(cfg)

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()

    async def publish(self, subject: str, payload: dict[str, Any]) -> bool:
        if self._js is None:
            return False
        try:
            await self._js.publish(subject, json.dumps(payload, default=str).encode(), timeout=2)
            return True
        except Exception as exc:  # noqa: BLE001 - events are best effort
            log.warning(
                "event publish failed", extra={"subject": subject, "error_type": type(exc).__name__}
            )
            if self._on_failure:
                self._on_failure(subject)
            return False


def call_subject(company_code: str, kind: str) -> str:
    return f"hq.llm.{company_code}.call.{kind}"


def budget_subject(company_code: str) -> str:
    return f"hq.alerts.budget.{company_code}"


ANOMALY_SUBJECT = "hq.alerts.llm.anomaly"
COST_RATIO_SUBJECT = "hq.alerts.llm.cost_ratio"
