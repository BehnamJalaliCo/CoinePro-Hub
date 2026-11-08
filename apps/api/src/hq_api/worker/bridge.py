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

⟨1.24⟩ §42.2 `llm.tick` (topic `llm`): the call events of each company summed in 5 s windows
(aligned to the clock), one tick per company that had a call in the window, nothing when idle;
its `day` (the Token Treasury's UTC day: tokens, effective tokens with a cache read at a tenth,
dollars, the company's daily budget and its share) and `in_flight` read from the ledger.
Nats-Msg-Id = llm.tick:<company>:<window start>.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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


# ------------------------------------------------------------------ llm.tick --
TICK_S = 5
TOKEN_KINDS = (
    ("input", "input_tokens"),
    ("output", "output_tokens"),
    ("cache_read", "cache_read_tokens"),
    ("cache_write", "cache_write_tokens"),
    ("thinking", "thinking_tokens"),
)


def _usd(v: Any) -> Decimal:
    try:
        return Decimal(str(v)) if v not in (None, "") else Decimal(0)
    except InvalidOperation:
        return Decimal(0)


@dataclass
class Window:
    """One company's calls in one 5 s window: the calls that finished (they carry the tokens)."""

    start: int
    calls: int = 0
    tokens: dict[str, int] = field(default_factory=lambda: {k: 0 for k, _ in TOKEN_KINDS})
    usd: Decimal = Decimal(0)


class Ticks:
    """The 5 s windows of the router's call events, per company (contract §42.2 llm.tick)."""

    def __init__(self, window_s: int = TICK_S) -> None:
        self.window_s = window_s
        self._open: dict[tuple[str, int], Window] = {}

    def add(self, company: str, kind: str, data: dict[str, Any], now: float | None = None) -> None:
        start = int((time.time() if now is None else now) // self.window_s) * self.window_s
        w = self._open.setdefault((company, start), Window(start))
        if kind != "finished":
            return  # a call that started only opens the window (in_flight is read from the ledger)
        w.calls += 1
        raw = data.get("usage")
        usage: dict[str, Any] = raw if isinstance(raw, dict) else {}
        for key, src in TOKEN_KINDS:
            n = usage.get(src)
            w.tokens[key] += int(n) if isinstance(n, int) and n > 0 else 0
        w.usd += _usd(data.get("cost_usd")) + _usd(data.get("equiv_cost_usd"))

    def due(self, now: float | None = None) -> list[tuple[str, Window]]:
        """The windows that ended (taken out)."""
        t = time.time() if now is None else now
        keys = [k for k, w in self._open.items() if w.start + self.window_s <= t]
        return [(k[0], self._open.pop(k)) for k in sorted(keys, key=lambda k: (k[1], k[0]))]


DAY_SQL = """
    SELECT c.code AS company,
           COALESCE(sum(COALESCE(l.input_tokens, 0) + COALESCE(l.output_tokens, 0)
                        + COALESCE(l.cache_read_tokens, 0) + COALESCE(l.cache_write_tokens, 0)), 0) AS tokens,
           COALESCE(sum(COALESCE(l.cache_read_tokens, 0)), 0) AS cache_read,
           COALESCE(sum(COALESCE(l.cost_usd, 0) + COALESCE(l.equiv_cost_usd, 0)), 0) AS usd,
           count(*) FILTER (WHERE l.status = 'running'
                              AND l.started_at > now() - interval '30 minutes') AS in_flight,
           (SELECT b.usd_limit FROM llm.budgets b
             WHERE b.company_id = c.id AND b.scope_type = 'company' AND b.scope_ref = c.code
               AND b.period = 'day' AND b.enabled) AS budget_usd
    FROM core.companies c LEFT JOIN llm.calls l ON l.company_id = c.id AND l.started_at >= :day
    WHERE c.code = ANY(:codes)
    GROUP BY c.id, c.code
"""


def tick_data(company: str, w: Window, day: dict[str, Any] | None, window_s: int) -> dict[str, Any]:
    """The `llm.tick` event's data (§42.2): the window's calls and tokens by kind, and the day.
    Money as §1 has it: decimal strings of 6 places."""
    from hq_api.domain.live import effective, usd

    d = day or {}
    tokens, cache = int(d.get("tokens") or 0), int(d.get("cache_read") or 0)
    spent = usd(d.get("usd"))
    budget = usd(d["budget_usd"]) if d.get("budget_usd") is not None else None
    return {
        "company": company,
        "window_s": window_s,
        "calls": w.calls,
        "in_flight": int(d.get("in_flight") or 0),
        "tokens": dict(w.tokens),
        "equiv_usd": str(usd(w.usd)),
        "day": {
            "tokens": tokens,
            "effective_tokens": effective(tokens, cache),
            "equiv_usd": str(spent),
            "budget_usd": str(budget) if budget is not None else None,
            "pct": round(float(100 * spent / budget), 1) if budget else None,
        },
    }


class Bridge:
    def __init__(self, hub: Hub, *, batch: int = 50, idle_s: float = 2.0) -> None:
        self.hub = hub
        self.batch = batch
        self.idle_s = idle_s
        self._subs: dict[str, Any] = {}
        self.ticks = Ticks()

    async def flush_ticks(self, now: float | None = None) -> int:
        """`llm.tick` for each company whose window ended; returns how many went out."""
        due = self.ticks.due(now)
        bus = self.hub.bus
        if not due or bus is None or not bus.connected:
            return 0
        day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        async with self.hub.db.tx(await self.hub.companies.ids()) as tx:
            rows = await tx.all(DAY_SQL, day=day, codes=sorted({c for c, _ in due}))
        days = {r["company"]: dict(r) for r in rows}
        for code, w in due:
            env = events.envelope(
                code, "llm.tick", None, tick_data(code, w, days.get(code), self.ticks.window_s)
            )
            await bus.publish(f"hq.core.{code}.llm.tick", env, msg_id=f"llm.tick:{code}:{w.start}")
        return len(due)

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
                drained = await self.drain_once()
                await self.flush_ticks()
                if drained == 0:
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
            self.ticks.add(company.code, parts[4], data)  # ⟨1.24⟩ §42.2 its 5 s window
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
