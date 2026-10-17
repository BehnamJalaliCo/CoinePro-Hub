"""One model call on the Claude subscription through the official Agent SDK.

Safety of every run (prompt 03 §4):
  - no tools at all (`tools=[]`), no MCP servers, no skills, no plugins,
    no settings files or CLAUDE.md (`setting_sources=[]`)
  - the system prompt REPLACES Claude Code's own; it is passed as a file in
    the run directory, so it never shows up in a process argument list
  - a fresh, empty working directory and HOME under the container's tmpfs,
    deleted after the run; the container has no repo, no Docker socket and
    no route to the internal network
  - CLAUDE_CODE_OAUTH_TOKEN reaches only the CLI child process
Usage comes from the SDK result (`usage`, `total_cost_usd`).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    RateLimitEvent,
    ResultError,
    ResultMessage,
    StreamEvent,
    TextBlock,
    query,
)

from claude_runtime.quota import OK, TIMEOUT, Signals, Verdict, classify
from claude_runtime.render import render

log = logging.getLogger("claude_runtime.runner")

CHILD_ENV = {
    "DISABLE_AUTOUPDATER": "1",
    "DISABLE_TELEMETRY": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",
}


@dataclass(frozen=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True)
class RunSpec:
    call_id: str
    model: str
    effort: str | None
    system: str | None
    messages: tuple[Message, ...]
    json_schema: dict[str, Any] | None
    timeout_s: int
    max_output_tokens: int | None = None


@dataclass
class Outcome:
    status: str
    text: str | None = None
    structured: Any = None
    model: str | None = None
    usage: dict[str, int | None] | None = None
    total_cost_usd: float | None = None
    stop_reason: str | None = None
    error_class: str | None = None
    quota_resets_at: float | None = None
    duration_ms: int = 0
    effort_applied: bool | None = None
    # The latest rate-limit state the CLI reported during the run (Quota
    # Controller source, prompt 05 §8): status, window, utilization, reset.
    rate_limit: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "text": self.text,
            "structured": self.structured,
            "model": self.model,
            "usage": self.usage,
            "total_cost_usd": self.total_cost_usd,
            "stop_reason": self.stop_reason,
            "error_class": self.error_class,
            "quota_resets_at": self.quota_resets_at,
            "duration_ms": self.duration_ms,
            "effort_applied": self.effort_applied,
            "rate_limit": self.rate_limit,
        }


@dataclass(frozen=True)
class Delta:
    text: str


RATE_LIMIT_STATUSES = ("allowed", "allowed_warning", "rejected")


def rate_limit_of(info: Any) -> dict[str, Any] | None:
    """Metadata only, with types checked (the CLI's raw dict is never passed on)."""
    status = getattr(info, "status", None)
    if status not in RATE_LIMIT_STATUSES:
        return None
    kind = getattr(info, "rate_limit_type", None)
    util = getattr(info, "utilization", None)
    resets = getattr(info, "resets_at", None)
    return {
        "status": status,
        "window": kind if isinstance(kind, str) and len(kind) <= 40 else None,
        "utilization": float(util) if isinstance(util, int | float) and 0 <= util <= 1 else None,
        "resets_at": float(resets) if isinstance(resets, int | float) and resets > 0 else None,
    }


def usage_from(raw: dict[str, Any] | None) -> dict[str, int | None] | None:
    if not raw:
        return None
    by_ttl = raw.get("cache_creation")
    written_1h = by_ttl.get("ephemeral_1h_input_tokens") if isinstance(by_ttl, dict) else None
    details = raw.get("output_tokens_details")
    thinking = details.get("thinking_tokens") if isinstance(details, dict) else None
    return {
        "input_tokens": int(raw.get("input_tokens") or 0),
        "output_tokens": int(raw.get("output_tokens") or 0),
        "cache_read_tokens": int(raw.get("cache_read_input_tokens") or 0),
        "cache_write_tokens": int(raw.get("cache_creation_input_tokens") or 0),
        # Part of cache_write_tokens written with the 1-hour TTL (priced higher).
        "cache_write_1h_tokens": int(written_1h) if written_1h is not None else None,
        # Thinking tokens are part of output_tokens; reported separately only
        # when the CLI gives output_tokens_details (else NULL in the ledger).
        "thinking_tokens": int(thinking) if thinking else None,
    }


class ClaudeRunner:
    def __init__(
        self,
        oauth_token: Callable[[], str | None],
        workdir_root: str | Path,
        *,
        cli_path: str | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self._oauth_token = oauth_token
        self._root = Path(workdir_root)
        self._cli_path = cli_path
        self._sem = asyncio.Semaphore(max_concurrency)
        self.active = 0
        self.stderr_lines = 0

    def _options(
        self, spec: RunSpec, run_dir: Path, token: str, *, stream: bool
    ) -> ClaudeAgentOptions:
        system_file = run_dir / "system.txt"
        system_file.write_text(spec.system or "")
        (run_dir / "work").mkdir()
        (run_dir / "home").mkdir()
        options = ClaudeAgentOptions(
            tools=[],
            allowed_tools=[],
            mcp_servers={},
            strict_mcp_config=True,
            setting_sources=[],
            skills=[],
            plugins=[],
            system_prompt={"type": "file", "path": str(system_file)},
            model=spec.model,
            effort=spec.effort,  # type: ignore[arg-type]
            max_turns=3 if spec.json_schema else 1,
            cwd=str(run_dir / "work"),
            env={
                **CHILD_ENV,
                "HOME": str(run_dir / "home"),
                "CLAUDE_CODE_OAUTH_TOKEN": token,
                # The CLI's own output cap: the call stops there (prompt 5.1 §2.6).
                **(
                    {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(spec.max_output_tokens)}
                    if spec.max_output_tokens
                    else {}
                ),
            },
            include_partial_messages=stream,
            stderr=self._count_stderr,
            cli_path=self._cli_path,
        )
        if spec.json_schema:
            options.output_format = {"type": "json_schema", "schema": spec.json_schema}
        return options

    def _count_stderr(self, _line: str) -> None:
        # CLI stderr may echo request details; it is counted, never logged.
        self.stderr_lines += 1

    async def run(self, spec: RunSpec) -> Outcome:
        result: Outcome | None = None
        async for item in self.stream(spec, partial=False):
            if isinstance(item, Outcome):
                result = item
        assert result is not None
        return result

    async def stream(
        self, spec: RunSpec, *, partial: bool = True
    ) -> AsyncIterator[Delta | Outcome]:
        token = self._oauth_token()
        if not token:
            yield Outcome("error", error_class="not_configured", model=spec.model)
            return
        async with self._sem:
            self.active += 1
            run_dir = self._root / f"{spec.call_id}-{uuid.uuid4().hex[:8]}"
            run_dir.mkdir(parents=True, mode=0o700)
            started = time.monotonic()
            try:
                async for item in self._execute(spec, run_dir, token, partial):
                    if isinstance(item, Outcome):
                        item.duration_ms = int((time.monotonic() - started) * 1000)
                    yield item
            finally:
                self.active -= 1
                shutil.rmtree(run_dir, ignore_errors=True)

    async def _execute(
        self, spec: RunSpec, run_dir: Path, token: str, partial: bool
    ) -> AsyncIterator[Delta | Outcome]:
        signals = Signals()
        rate_limit: dict[str, Any] | None = None
        texts: list[str] = []
        model: str | None = None
        result: ResultMessage | None = None
        error_text = ""
        options = self._options(spec, run_dir, token, stream=partial)
        prompt = render(spec.messages)
        try:
            async with asyncio.timeout(spec.timeout_s):
                stream = cast(AsyncGenerator[Any, None], query(prompt=prompt, options=options))
                async with contextlib.aclosing(stream) as messages:
                    async for msg in messages:
                        if isinstance(msg, StreamEvent):
                            delta = (msg.event or {}).get("delta") or {}
                            if partial and delta.get("type") == "text_delta" and delta.get("text"):
                                yield Delta(delta["text"])
                        elif isinstance(msg, AssistantMessage):
                            model = msg.model or model
                            if msg.error:
                                signals.assistant_errors.append(msg.error)
                            texts += [b.text for b in msg.content if isinstance(b, TextBlock)]
                        elif isinstance(msg, RateLimitEvent):
                            info = msg.rate_limit_info
                            rate_limit = rate_limit_of(info) or rate_limit
                            if info.status == "rejected":
                                signals.rejected_resets_at.append(
                                    float(info.resets_at) if info.resets_at else None
                                )
                        elif isinstance(msg, ResultMessage):
                            result = msg
        except TimeoutError:
            yield Outcome(TIMEOUT, error_class="timeout", model=spec.model)
            return
        except ResultError as exc:
            # A failed run ends with an error result and a non-zero exit: the
            # SDK yields that result, then raises. Classify it like any other
            # result so the reason (auth, quota, API status) is not lost.
            log.warning(
                "cli reported an error result",
                extra={
                    "call_id": spec.call_id,
                    "subtype": exc.subtype,
                    "terminal_reason": exc.terminal_reason,
                    "api_error_status": exc.api_error_status,
                    "assistant_errors": signals.assistant_errors,
                },
            )
            if result is None:
                signals.result_seen = True
                signals.is_error = True
                signals.subtype = exc.subtype
                signals.api_error_status = exc.api_error_status
                error_text = exc.result or ""
        except Exception as exc:  # noqa: BLE001 - CLI/SDK failures become an error result
            log.warning(
                "sdk run failed", extra={"call_id": spec.call_id, "error_type": type(exc).__name__}
            )
            yield Outcome("error", error_class=f"sdk_{type(exc).__name__}", model=spec.model)
            return

        text = result.result if result and result.result is not None else "".join(texts)
        if result is not None:
            signals.result_seen = True
            signals.is_error = result.is_error
            signals.subtype = result.subtype
            signals.stop_reason = result.stop_reason
            signals.api_error_status = result.api_error_status
            if result.model_usage:
                model = next(iter(result.model_usage), model)
        signals.text = text or error_text
        verdict: Verdict = classify(signals)
        yield Outcome(
            status=verdict.status,
            text=text if verdict.status == OK or verdict.status == "refusal" else None,
            structured=result.structured_output if result else None,
            model=model or spec.model,
            usage=usage_from(result.usage if result else None),
            total_cost_usd=result.total_cost_usd if result else None,
            stop_reason=result.stop_reason if result else None,
            error_class=verdict.error_class,
            quota_resets_at=verdict.resets_at,
            effort_applied=spec.effort is not None,
            rate_limit=rate_limit,
        )
