"""Temporal activities of prompt 12, part A (contract §21.1, §21.13).

advisor_sweep          every 2 min: memos whose run ended without memo.write
                       are `failed`; the automatic memos of the owner's
                       qualifying cards (at most 3 a day); the proactive
                       triggers (rules, no model). Rule-only until it would
                       wake the advisor: while the holding is locked no memo
                       is made and every new trigger is recorded `deferred`.
substitute_web_jobs    every minute: the queued web seat calls, one per player
                       at a time and >= 60 s apart, through egress's signed-in
                       browser profiles. Nothing while the holding is locked
                       (the owner's sealed profile wipes still run: local only).
substitute_daily       daily 09:15 (Tehran): on the 15th of the Jalali month a
                       signed-in paid player behind its value ratio gets one
                       `report` notification; the CLIs' model lists are asked
                       for (one `models` job per signed-in player) unless locked.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from temporalio import activity

from hq_api.domain import advisor, gate
from hq_api.domain import substitutes as S
from hq_api.hub import Hub

log = logging.getLogger("hq_api.worker.management")


class EgressWeb:
    """The worker's client for egress's substitute web path (the interface
    of prompt 12 §9.1: POST /v1/substitutes/web, /v1/substitutes/web/logout)."""

    def __init__(self, base_url: str, transport: Any = None) -> None:
        self.base = base_url.rstrip("/")
        self._transport = transport

    async def _post(self, path: str, body: dict[str, Any], limit_s: float) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=limit_s) as http:
                resp = await http.post(self.base + path, json=body)
            out = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("substitute web call failed", extra={"error": type(exc).__name__})
            return {"ok": False, "error": "off", "detail": "egress did not answer"}
        return out if isinstance(out, dict) else {"ok": False, "error": "failed"}

    async def web(self, *, account: str, task: str, prompt: str, timeout_s: int) -> dict[str, Any]:
        return await self._post(
            "/v1/substitutes/web",
            {"account": account, "task": task, "prompt": prompt, "timeout_s": timeout_s},
            limit_s=timeout_s + 30,
        )

    async def web_logout(self, *, account: str) -> dict[str, Any]:
        return await self._post("/v1/substitutes/web/logout", {"account": account}, limit_s=60)


# Tests put a fake egress here.
OVERRIDE: Any = None


class ManagementActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx

    def all(self) -> list[Any]:
        return [self.advisor_sweep, self.substitute_web_jobs, self.substitute_daily]

    @activity.defn(name="advisor_sweep")
    async def advisor_sweep(self) -> dict[str, Any]:
        return await advisor.sweep(self.hub)

    @activity.defn(name="substitute_web_jobs")
    async def substitute_web_jobs(self) -> dict[str, Any]:
        egress = OVERRIDE or EgressWeb(self.hub.settings.support_egress_url)
        return await S.web_jobs(self.hub, egress)

    @activity.defn(name="substitute_daily")
    async def substitute_daily(self) -> dict[str, Any]:
        async with self._tx() as tx:
            behind = await S.behind_check(tx, self.hub)
            lock = await gate.holding_lock(tx)
            asked = 0 if lock is not None else await S.ask_models(tx, self.hub)
        return {"behind_notified": behind, "models_jobs": asked, "locked": lock}
