"""Client for claude-runtime (the Claude subscription via the Agent SDK)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from typing import Any

import httpx

from llm_router.backends.base import ERROR, TIMEOUT, BackendCall, BackendResult, Delta
from llm_router.pricing import Usage

GRACE_S = 15  # the runtime enforces timeout_s itself; this only guards the socket


def _payload(call: BackendCall) -> dict[str, Any]:
    return {
        "call_id": call.call_id,
        "model": call.model,
        "effort": call.effort,
        "system": call.system,
        "messages": [{"role": m.role, "content": m.content} for m in call.messages],
        "json_schema": call.json_schema,
        "timeout_s": call.timeout_s,
    }


def result_from_json(d: dict[str, Any]) -> BackendResult:
    u = d.get("usage") or None
    usage = (
        Usage(
            input_tokens=int(u.get("input_tokens") or 0),
            output_tokens=int(u.get("output_tokens") or 0),
            cache_read_tokens=int(u.get("cache_read_tokens") or 0),
            cache_write_tokens=int(u.get("cache_write_tokens") or 0),
            thinking_tokens=u.get("thinking_tokens"),
            cache_write_1h_tokens=u.get("cache_write_1h_tokens"),
        )
        if u
        else None
    )
    cost = d.get("total_cost_usd")
    return BackendResult(
        status=d.get("status", ERROR),
        text=d.get("text"),
        structured=d.get("structured"),
        model=d.get("model"),
        usage=usage,
        sdk_cost_usd=Decimal(str(cost)) if cost is not None else None,
        error_class=d.get("error_class"),
        quota_resets_at=d.get("quota_resets_at"),
        stop_reason=d.get("stop_reason"),
        effort_applied=d.get("effort_applied"),
        rate_limit=d.get("rate_limit") if isinstance(d.get("rate_limit"), dict) else None,
    )


class ClaudeRuntimeBackend:
    def __init__(
        self,
        base_url: str,
        token: Callable[[], str],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._http = httpx.AsyncClient(base_url=base_url, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}"}

    async def run(self, call: BackendCall) -> BackendResult:
        try:
            resp = await self._http.post(
                "/v1/run",
                json=_payload(call),
                headers=self._headers(),
                timeout=call.timeout_s + GRACE_S,
            )
        except httpx.TimeoutException:
            return BackendResult(TIMEOUT, error_class="runtime_timeout")
        except httpx.HTTPError:
            return BackendResult(ERROR, error_class="runtime_unreachable")
        if resp.status_code != 200:
            return BackendResult(ERROR, error_class=f"runtime_http_{resp.status_code}")
        return result_from_json(resp.json())

    async def stream(self, call: BackendCall) -> AsyncIterator[Delta | BackendResult]:
        try:
            async with self._http.stream(
                "POST",
                "/v1/run/stream",
                json=_payload(call),
                headers=self._headers(),
                timeout=call.timeout_s + GRACE_S,
            ) as resp:
                if resp.status_code != 200:
                    yield BackendResult(ERROR, error_class=f"runtime_http_{resp.status_code}")
                    return
                event = ""
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        data = json.loads(line[5:].strip())
                        if event == "delta":
                            yield Delta(data.get("text", ""))
                        elif event == "result":
                            yield result_from_json(data)
                            return
                yield BackendResult(ERROR, error_class="runtime_stream_ended")
        except httpx.TimeoutException:
            yield BackendResult(TIMEOUT, error_class="runtime_timeout")
        except httpx.HTTPError:
            yield BackendResult(ERROR, error_class="runtime_unreachable")
