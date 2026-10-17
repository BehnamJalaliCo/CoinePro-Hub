"""Bridge llm-router's events into the live stream (contract §7, §13).

Durable pull consumers on llm-router's JetStream streams:
    HQ_LLM     hq.llm.<CO>.call.started|finished  -> hq.core.<CO>.llm.call_started|call_finished
                                                     (types llm.call.started|llm.call.finished)
    HQ_ALERTS  hq.alerts.budget.<CO>               -> hq.core.<CO>.budget.alert (type budget.alert)
                                                     + owner notification (70/90 report, 100 urgent)
               hq.alerts.llm.anomaly               -> urgent owner notification
               hq.alerts.llm.cost_ratio            -> 🔵 report owner notification (prompt 04 §9.1)
               hq.alerts.quota                     -> hq.core.<HQ>.budget.alert (kind quota)
                                                     + 🔵 report, once per change (prompt 05 §8)
Only allow-listed metadata keys are forwarded; no text field ever crosses.
Nats-Msg-Id = <source stream>:<sequence>, so redeliveries are de-duplicated.
New consumers start at new messages (old retained events are not replayed).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from typing import Any

from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy
from nats.js.errors import NotFoundError

from hq_api import events
from hq_api.domain import notify
from hq_api.hub import Hub

log = logging.getLogger("hq_api.worker.bridge")

SOURCES = (
    ("HQ_LLM", "hq.llm.>", "hq-core-bridge-llm"),
    ("HQ_ALERTS", "hq.alerts.>", "hq-core-bridge-alerts"),
)
CODE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
CALL_KEYS = frozenset(
    {
        "call_id",
        "company",
        "actor_ref",
        "work_ref",
        "department",
        "task_class",
        "priority",
        "connection",
        "model",
        "effort",
        "fallback_from",
        "started_at",
        "status",
        "cost_usd",
        "equiv_cost_usd",
        "latency_ms",
        "error_class",
    }
)
USAGE_KEYS = frozenset(
    {
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "thinking_tokens",
        "cache_write_1h_tokens",
    }
)
QUOTA_KEYS = frozenset(
    {
        "status",
        "previous",
        "connection",
        "window",
        "utilization",
        "resets_at",
        "source",
        "at",
    }
)
QUOTA_FA = {"ok": "عادی", "warning": "هشدار", "limited": "محدود"}
BUDGET_KEYS = frozenset(
    {
        "level",
        "percent",
        "company",
        "scope_type",
        "scope_ref",
        "period",
        "tokens_used",
        "usd_used",
        "token_limit",
        "usd_limit",
        "at",
    }
)
MAX_VALUE = 200


def _scalar(value: Any) -> bool:
    return (
        value is None
        or isinstance(value, bool | int | float)
        or (isinstance(value, str) and len(value) <= MAX_VALUE)
    )


def pick(payload: dict[str, Any], keys: frozenset[str]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k in keys and _scalar(v)}


def call_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = pick(payload, CALL_KEYS)
    usage = payload.get("usage")
    if isinstance(usage, dict):
        data["usage"] = {
            k: v for k, v in usage.items() if k in USAGE_KEYS and isinstance(v, int | None)
        }
    return data


class Bridge:
    def __init__(self, hub: Hub, *, batch: int = 50, idle_s: float = 2.0) -> None:
        self.hub = hub
        self.batch = batch
        self.idle_s = idle_s
        self._subs: dict[str, Any] = {}

    async def subscribe(self) -> int:
        """Bind the durable consumers whose streams exist; returns how many are bound."""
        bus = self.hub.bus
        if bus is None or not bus.connected:
            return 0
        for stream, subject, durable in SOURCES:
            if stream in self._subs:
                continue
            try:
                self._subs[stream] = await bus.js.pull_subscribe(
                    subject,
                    durable=durable,
                    stream=stream,
                    config=ConsumerConfig(
                        deliver_policy=DeliverPolicy.NEW,
                        ack_policy=AckPolicy.EXPLICIT,
                        ack_wait=60,
                        max_deliver=20,
                    ),
                )
            except NotFoundError:
                log.info("stream not there yet; will retry", extra={"stream": stream})
        return len(self._subs)

    async def drain_once(self) -> int:
        done = 0
        for stream, sub in list(self._subs.items()):
            try:
                msgs = await sub.fetch(self.batch, timeout=1)
            except TimeoutError:
                continue
            for msg in msgs:
                try:
                    await self.handle(stream, msg)
                except Exception:  # noqa: BLE001 - redelivered later (ack_wait)
                    log.warning("bridge could not forward an event", extra={"stream": stream})
                    with contextlib.suppress(Exception):
                        await msg.nak(delay=10)
                    continue
                await msg.ack()
                done += 1
        return done

    async def run(self) -> None:
        while True:
            try:
                if len(self._subs) < len(SOURCES):
                    await self.subscribe()
                if await self.drain_once() == 0:
                    await asyncio.sleep(self.idle_s)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - keep bridging
                log.warning("bridge pass failed")
                await asyncio.sleep(5)

    async def _company(self, code: Any) -> Any:
        if isinstance(code, str) and CODE.match(code):
            c = await self.hub.companies.find(code)
            if c is not None:
                return c
        return await self.hub.companies.holding()

    async def handle(self, stream: str, msg: Any) -> None:
        try:
            payload = json.loads(msg.data)
        except ValueError:
            return
        if not isinstance(payload, dict):
            return
        seq = int(msg.metadata.sequence.stream)
        msg_id = f"{stream}:{seq}"
        parts = msg.subject.split(".")
        assert self.hub.bus is not None
        if (
            stream == "HQ_LLM"
            and len(parts) == 5
            and parts[3] == "call"
            and parts[4] in ("started", "finished")
        ):
            company = await self._company(payload.get("company") or parts[2])
            data = call_data(payload)
            env = events.envelope(
                company.code, f"llm.call.{parts[4]}", str(data.get("call_id") or ""), data
            )
            await self.hub.bus.publish(
                f"hq.core.{company.code}.llm.call_{parts[4]}", env, msg_id=msg_id
            )
            return
        if stream != "HQ_ALERTS":
            return
        if len(parts) == 4 and parts[2] == "budget":
            company = await self._company(payload.get("company") or parts[3])
            data = pick(payload, BUDGET_KEYS)
            ref = f"{data.get('scope_type')}:{data.get('scope_ref')}:{data.get('period')}"
            env = events.envelope(company.code, "budget.alert", ref, data)
            await self.hub.bus.publish(f"hq.core.{company.code}.budget.alert", env, msg_id=msg_id)
            level = int(data.get("level") or 0)
            await self._notify(
                company,
                "urgent" if level >= 100 else "report",
                f"بودجه‌ی {data.get('scope_type')}:{data.get('scope_ref')} ({data.get('period')}) به {level}٪ رسید",
                "treasury",
                f"budget:{ref}",
            )
        elif msg.subject == "hq.alerts.llm.anomaly":
            company = await self._company(payload.get("company"))
            actor = str(payload.get("actor_ref") or "?")[:64]
            await self._notify(
                company,
                "urgent",
                f"مصرف غیرعادی مدل: {actor} ({payload.get('calls_this_hour')} فراخوانی در ساعت)",
                "treasury",
                f"actor:{actor}",
            )
        elif msg.subject == "hq.alerts.quota":
            company = await self.hub.companies.holding()
            data = pick(payload, QUOTA_KEYS)
            paused = payload.get("paused_priorities")
            data["paused_priorities"] = (
                [p for p in paused if isinstance(p, str)][:5] if isinstance(paused, list) else []
            )
            data["kind"] = "quota"
            ref = f"quota:{data.get('connection')}"
            env = events.envelope(company.code, "budget.alert", ref, data)
            await self.hub.bus.publish(f"hq.core.{company.code}.budget.alert", env, msg_id=msg_id)
            status = str(data.get("status") or "ok")
            util = data.get("utilization")
            pct = (
                f" ({round(float(util) * 100)}٪ {data.get('window') or ''})"
                if util not in (None, "")
                else ""
            )
            paused_fa = "، ".join(data["paused_priorities"]) or "هیچ"
            await self._notify(
                company,
                "report",
                f"سهمیه‌ی اشتراک: {QUOTA_FA.get(status, status)}{pct}؛ متوقف: {paused_fa}"[:300],
                "treasury",
                f"quota:{status}:{data.get('at')}"[:100],
            )
        elif msg.subject == "hq.alerts.llm.cost_ratio":
            company = await self.hub.companies.holding()
            model = str(payload.get("model") or "?")[:100]
            await self._notify(
                company,
                "report",
                f"برآورد هزینه‌ی SDK یک ساعت بیش از دو برابر جدول قیمت ماست ({payload.get('ratio')}×، {model})",
                "treasury",
                f"cost_ratio:{payload.get('connection')}:{model}"[:100],
            )

    async def _notify(
        self, company: Any, level: str, title: str, link_kind: str, link_ref: str
    ) -> None:
        """One notification per alert; a redelivered alert within 10 minutes is not repeated."""
        async with self.hub.db.tx(await self.hub.companies.ids()) as tx:
            dup = await tx.scalar(
                """SELECT 1 FROM notify.notifications WHERE company_id = :co AND level = :l AND link_kind = :lk
                     AND link_ref = :lr AND title_fa = :t AND created_at > now() - interval '10 minutes'""",
                co=company.id,
                l=level,
                lk=link_kind,
                lr=link_ref[:100],
                t=title[:300],
            )
            if dup:
                return
            row = await notify.raise_notification(
                tx,
                company_id=company.id,
                company_code=company.code,
                level=level,
                title_fa=title[:300],
                link_kind=link_kind,
                link_ref=link_ref[:100],
                source_kind="service",
                source_code="llm-router",
            )
        if row.get("push_now"):
            await notify.deliver_pending(self.hub, [row["id"]])
