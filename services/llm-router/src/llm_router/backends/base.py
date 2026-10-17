"""Backend contract shared by claude-runtime and LiteLLM."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from llm_router.pricing import Usage
from llm_router.registry import Connection

# Final statuses a backend may report (the ledger adds rejected_budget).
OK, ERROR, REFUSAL, TIMEOUT, RATE_LIMITED, QUOTA = (
    "ok",
    "error",
    "refusal",
    "timeout",
    "rate_limited",
    "quota_exhausted",
)


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class BackendCall:
    call_id: str
    connection: Connection
    model: str
    effort: str | None
    system: str | None
    messages: tuple[ChatMessage, ...]
    json_schema: dict[str, Any] | None
    timeout_s: int
    actor_ref: str | None = None  # who calls (the fake backend's scripts use it)
    max_output_tokens: int | None = None  # hard output cap of this call, when asked


@dataclass
class BackendResult:
    status: str
    text: str | None = None
    structured: Any = None
    model: str | None = None
    usage: Usage | None = None
    sdk_cost_usd: Decimal | None = None  # subscription: SDK total_cost_usd
    compare_cost_usd: Decimal | None = None  # API: LiteLLM's own figure, for comparison only
    error_class: str | None = None
    quota_resets_at: float | None = None
    stop_reason: str | None = None
    effort_applied: bool | None = None
    # Subscription only: the run's latest rate-limit state (Quota Controller source).
    rate_limit: dict[str, Any] | None = None


@dataclass(frozen=True)
class Delta:
    text: str


class Backend(Protocol):
    async def run(self, call: BackendCall) -> BackendResult: ...

    def stream(self, call: BackendCall) -> AsyncIterator[Delta | BackendResult]: ...
