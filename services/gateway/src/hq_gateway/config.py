"""Settings from the environment (non-secret). The worker's token digest is a file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    api_url: str = field(
        default_factory=lambda: os.environ.get("GATEWAY_API_URL", "http://api:8000")
    )
    opa_url: str = field(default_factory=lambda: os.environ.get("OPA_URL", "http://opa:8181"))
    # The egress service (prompt 07 §2), for the internet tools; empty = not wired.
    egress_url: str = field(default_factory=lambda: os.environ.get("EGRESS_URL", ""))
    # SHA-256 (hex) of the worker's token, installed by make up (600, uid 10001).
    worker_token_file: str = field(
        default_factory=lambda: os.environ.get(
            "GATEWAY_WORKER_TOKEN_FILE", "/run/secrets/hq/worker-token.sha256"
        )
    )
    listen_port: int = field(default_factory=lambda: _int("PORT", 8080))
    call_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("GATEWAY_CALL_TIMEOUT_S", "10"))
    )
    tool_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("GATEWAY_TOOL_TIMEOUT_S", "25"))
    )
    # The whole call (reserve, policy, the tool, the audit row): kept below the
    # worker's timeout for a gateway call (40 s), so a write that was carried
    # out is never reported to the worker as a failure.
    deadline_s: float = field(
        default_factory=lambda: float(os.environ.get("GATEWAY_DEADLINE_S", "30"))
    )
    max_result_chars: int = field(default_factory=lambda: _int("GATEWAY_MAX_RESULT_CHARS", 16_000))
    # A 200,000-character deliverable (the contract's cap) in Persian is ~400 KB
    # of UTF-8 JSON and up to ~800 KB with 4-byte characters: room for it.
    max_body_bytes: int = field(
        default_factory=lambda: _int("GATEWAY_MAX_BODY_BYTES", 2 * 1024 * 1024)
    )
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "info"))
    # MCP (prompt 07 §3): an `http` server is reached only through the egress
    # service's forward proxy; empty = such servers are not configured.
    egress_proxy_url: str = field(default_factory=lambda: os.environ.get("EGRESS_PROXY_URL", ""))
    mcp_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("MCP_CALL_TIMEOUT_S", "20"))
    )
