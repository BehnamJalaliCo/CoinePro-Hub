"""The runtime's clients: llm-router (every model call), the Tool Gateway
(every action) and the api (the live stream of a reply being written).

No prompt, model output or tool payload is ever logged here.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class ModelCall:
    """What a step costs and returns (metadata the run keeps; text stays in memory)."""

    ok: bool
    status: str
    code: str | None
    call_id: str | None
    model: str | None
    effort: str | None
    connection: str | None
    structured: Any
    text: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    equiv_cost_usd: str | None = None
    cost_usd: str | None = None
    retry_after: int | None = None

    @property
    def tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


def _model_call(status_code: int, body: Any, retry: str | None = None) -> ModelCall:
    if status_code != 200 or not isinstance(body, dict):
        code = body.get("error") if isinstance(body, dict) else None
        return ModelCall(
            ok=False,
            status="refused",
            code=str(code or f"router_http_{status_code}")[:40],
            call_id=body.get("call_id") if isinstance(body, dict) else None,
            model=None,
            effort=None,
            connection=None,
            structured=None,
            text=None,
            retry_after=int(retry) if retry and retry.isdigit() else None,
        )
    usage = body.get("usage") or {}
    return ModelCall(
        ok=body.get("status") == "ok",
        status=str(body.get("status")),
        code=body.get("error_class") if body.get("status") != "ok" else None,
        call_id=body.get("call_id"),
        model=body.get("model"),
        effort=body.get("effort"),
        connection=body.get("connection"),
        structured=body.get("json"),
        text=body.get("text"),
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cache_read_tokens=int(usage.get("cache_read_tokens") or 0),
        cache_write_tokens=int(usage.get("cache_write_tokens") or 0),
        equiv_cost_usd=body.get("equiv_cost_usd"),
        cost_usd=body.get("cost_usd"),
    )


class Router:
    """llm-router's /v1/run and /v1/run/stream as the caller hq-agents."""

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

    async def run(self, body: dict[str, Any], timeout_s: int) -> ModelCall:
        try:
            resp = await self._http.post(
                "/v1/run", json=body, headers=self._headers(), timeout=timeout_s + 30
            )
        except httpx.TimeoutException:
            return ModelCall(False, "timeout", "router_timeout", None, None, None, None, None, None)
        except httpx.HTTPError:
            return ModelCall(
                False, "error", "router_unreachable", None, None, None, None, None, None
            )
        try:
            data = resp.json()
        except ValueError:
            data = None
        return _model_call(resp.status_code, data, resp.headers.get("retry-after"))

    async def stream(
        self, body: dict[str, Any], timeout_s: int, on_delta: Callable[[str], Any]
    ) -> ModelCall:
        """The answer streamed: `on_delta(text)` per chunk; the end event is the result."""
        try:
            async with self._http.stream(
                "POST",
                "/v1/run/stream",
                json=body,
                headers=self._headers(),
                timeout=timeout_s + 30,
            ) as resp:
                if resp.status_code != 200:
                    try:
                        data = json.loads(await resp.aread())
                    except ValueError:
                        data = None
                    return _model_call(resp.status_code, data, resp.headers.get("retry-after"))
                event = ""
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        data = json.loads(line[5:].strip())
                        if event == "delta":
                            result = on_delta(str(data.get("text", "")))
                            if asyncio.iscoroutine(result):
                                await result
                        elif event == "end":
                            return _model_call(200, data)
        except httpx.TimeoutException:
            return ModelCall(False, "timeout", "router_timeout", None, None, None, None, None, None)
        except httpx.HTTPError:
            return ModelCall(
                False, "error", "router_unreachable", None, None, None, None, None, None
            )
        return ModelCall(False, "error", "stream_ended", None, None, None, None, None, None)


class Gateway:
    """The Tool Gateway's POST /v1/tools/call (the runtime is its only caller)."""

    def __init__(
        self,
        base_url: str,
        token: Callable[[], str],
        timeout_s: float = 40.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout_s, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def call(
        self, agent_token: str, step: int, index: int, tool: str, args: Any
    ) -> dict[str, Any]:
        try:
            resp = await self._http.post(
                "/v1/tools/call",
                json={
                    "token": agent_token,
                    "step": step,
                    "index": index,
                    "tool": tool,
                    "args": args,
                },
                headers={"Authorization": f"Bearer {self._token()}"},
            )
        except httpx.HTTPError:
            return {"outcome": "error", "class": None, "code": "gateway_unreachable", "ref": None}
        if resp.status_code != 200:
            return {
                "outcome": "error",
                "class": None,
                "code": f"gateway_http_{resp.status_code}",
                "ref": None,
            }
        out: dict[str, Any] = resp.json()
        return out


class LivePush:
    """One streamed POST /internal/v1/threads/{code}/live for a reply being
    written (NDJSON events), fed from a queue; never stored anywhere."""

    def __init__(
        self,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = base_url
        self._transport = transport

    @contextlib.asynccontextmanager
    async def open(
        self, thread: str, agent_token: str
    ) -> AsyncIterator[Callable[[str, dict[str, Any]], None]]:
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        async def body() -> AsyncIterator[bytes]:
            while True:
                item = await queue.get()
                if item is None:
                    return
                yield item

        def send(type_: str, data: dict[str, Any]) -> None:
            queue.put_nowait(
                (json.dumps({"type": type_, **data}, ensure_ascii=False) + "\n").encode()
            )

        async with httpx.AsyncClient(base_url=self._base, transport=self._transport) as http:

            async def post() -> None:
                with contextlib.suppress(httpx.HTTPError):
                    await http.post(
                        f"/internal/v1/threads/{thread}/live",
                        content=body(),
                        headers={
                            "Authorization": f"Bearer {agent_token}",
                            "X-Request-ID": str(uuid.uuid4()),
                            "Content-Type": "application/x-ndjson",
                        },
                        timeout=httpx.Timeout(30.0, read=None, write=None),
                    )

            task = asyncio.create_task(post())
            try:
                yield send
            finally:
                queue.put_nowait(None)
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(task, timeout=15)
