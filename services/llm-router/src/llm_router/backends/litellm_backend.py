"""API providers through LiteLLM, used as an in-process library (MIT part only).

Every API connection is disabled in prompt 03; this path is exercised by the
tests with a stubbed `acompletion`. Keys are read from OpenBao (the
connection's secret_ref) at call time and never logged. Cost is computed from
our own price table by the router; LiteLLM's figure is kept for comparison.
LiteLLM is imported lazily: it is large and unused while APIs are off.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal
from typing import Any

from llm_router.backends.base import (
    ERROR,
    OK,
    QUOTA,
    RATE_LIMITED,
    REFUSAL,
    TIMEOUT,
    BackendCall,
    BackendResult,
    ChatMessage,
    Delta,
)
from llm_router.pricing import Usage
from llm_router.registry import Connection

PROVIDER_PREFIX = {
    "anthropic": "anthropic",
    "openai": "openai",
    "gemini": "gemini",
    # prompt 12 §9 (contract §21.14): the providers a new connection may name
    "google": "gemini",
    "deepseek": "deepseek",
    "mistral": "mistral",
    "openai_compatible": "openai",
}

ReadSecret = Callable[[str], Awaitable[dict[str, Any]]]


def _litellm() -> Any:
    import litellm

    litellm.telemetry = False
    litellm.suppress_debug_info = True
    return litellm


def _content(m: ChatMessage) -> str | list[dict[str, Any]]:
    """A turn in the OpenAI-style form LiteLLM takes: its text, or its ordered
    parts, an image as a base64 data URI (bytes only; nothing is fetched)."""
    if not m.parts:
        return m.content
    return [
        {"type": "text", "text": p}
        if isinstance(p, str)
        else {"type": "image_url", "image_url": {"url": f"data:{p.media_type};base64,{p.data}"}}
        for p in m.parts
    ]


def model_name(conn: Connection, model: str) -> str:
    prefix = PROVIDER_PREFIX.get(conn.provider)
    if prefix is None:
        raise ValueError(f"no LiteLLM mapping for provider {conn.provider!r}")
    return f"{prefix}/{model}"


def usage_from(u: Any) -> Usage:
    if u is None:
        return Usage()
    prompt = int(getattr(u, "prompt_tokens", 0) or 0)
    completion = int(getattr(u, "completion_tokens", 0) or 0)
    p_details = getattr(u, "prompt_tokens_details", None)
    cached = int(getattr(p_details, "cached_tokens", 0) or 0) if p_details else 0
    cache_write = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
    c_details = getattr(u, "completion_tokens_details", None)
    reasoning = getattr(c_details, "reasoning_tokens", None) if c_details else None
    return Usage(
        input_tokens=max(prompt - cached - cache_write, 0),
        output_tokens=completion,
        cache_read_tokens=cached,
        cache_write_tokens=cache_write,
        thinking_tokens=int(reasoning) if reasoning is not None else None,
    )


def classify_error(exc: Exception) -> tuple[str, str]:
    """(ledger status, error_class) for a LiteLLM exception, by class name."""
    name = type(exc).__name__
    if name == "RateLimitError":
        text = str(getattr(exc, "message", "")).lower()
        if "quota" in text or "insufficient" in text or "billing" in text:
            return QUOTA, name
        return RATE_LIMITED, name
    if name in ("Timeout", "APITimeoutError"):
        return TIMEOUT, name
    if name == "ContentPolicyViolationError":
        return REFUSAL, name
    return ERROR, name


class LiteLLMBackend:
    def __init__(self, read_secret: ReadSecret, completion: Any = None) -> None:
        self._read_secret = read_secret
        self._completion = completion  # injectable for tests

    async def _kwargs(self, call: BackendCall, *, stream: bool) -> dict[str, Any]:
        conn = call.connection
        if not conn.secret_ref:
            raise ValueError(f"connection {conn.key} has no secret_ref")
        secret = await self._read_secret(conn.secret_ref.removeprefix("kv/"))
        messages: list[dict[str, Any]] = []
        if call.system:
            messages.append({"role": "system", "content": call.system})
        messages += [{"role": m.role, "content": _content(m)} for m in call.messages]
        kwargs: dict[str, Any] = {
            "model": model_name(conn, call.model),
            "messages": messages,
            "api_key": secret["api_key"],
            "timeout": call.timeout_s,
            "num_retries": 0,
        }
        if conn.api_base:
            kwargs["api_base"] = conn.api_base
        if call.max_output_tokens:
            kwargs["max_tokens"] = call.max_output_tokens
        if call.effort:
            kwargs["reasoning_effort"] = call.effort
        if call.json_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": call.json_schema},
            }
        if stream:
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}
        return kwargs

    def _acompletion(self) -> Any:
        return self._completion or _litellm().acompletion

    async def run(self, call: BackendCall) -> BackendResult:
        try:
            resp = await self._acompletion()(**await self._kwargs(call, stream=False))
        except Exception as exc:  # noqa: BLE001 - every provider error is classified
            status, error_class = classify_error(exc)
            return BackendResult(status, error_class=error_class)
        choice = resp.choices[0]
        text = choice.message.content
        finish = getattr(choice, "finish_reason", None)
        compare = None
        if self._completion is None:
            try:
                compare = Decimal(str(_litellm().completion_cost(completion_response=resp)))
            except Exception:  # noqa: BLE001 - comparison only
                compare = None
        return BackendResult(
            status=REFUSAL if finish == "content_filter" else OK,
            text=text,
            model=getattr(resp, "model", None) or call.model,
            usage=usage_from(getattr(resp, "usage", None)),
            compare_cost_usd=compare,
            stop_reason=finish,
            effort_applied=bool(call.effort),
        )

    async def stream(self, call: BackendCall) -> AsyncIterator[Delta | BackendResult]:
        try:
            chunks = await self._acompletion()(**await self._kwargs(call, stream=True))
            parts: list[str] = []
            usage = None
            finish = None
            async for chunk in chunks:
                if getattr(chunk, "usage", None):
                    usage = chunk.usage
                for choice in chunk.choices or []:
                    piece = getattr(choice.delta, "content", None)
                    if piece:
                        parts.append(piece)
                        yield Delta(piece)
                    finish = getattr(choice, "finish_reason", None) or finish
        except Exception as exc:  # noqa: BLE001
            status, error_class = classify_error(exc)
            yield BackendResult(status, error_class=error_class)
            return
        yield BackendResult(
            status=REFUSAL if finish == "content_filter" else OK,
            text="".join(parts),
            model=call.model,
            usage=usage_from(usage),
            stop_reason=finish,
            effort_applied=bool(call.effort),
        )
