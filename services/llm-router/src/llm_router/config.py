"""Settings from the environment (non-secret). Secrets come from OpenBao."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    db_host: str = field(default_factory=lambda: os.environ.get("DB_HOST", "postgres"))
    db_port: int = field(default_factory=lambda: _int("DB_PORT", 5432))
    db_name: str = field(default_factory=lambda: os.environ.get("DB_NAME", "hq"))
    db_user: str = field(default_factory=lambda: os.environ.get("DB_USER", "llm_router"))
    db_password: str = field(default_factory=lambda: os.environ.get("DB_PASSWORD", ""), repr=False)
    nats_url: str = field(default_factory=lambda: os.environ.get("NATS_URL", "nats://nats:4222"))
    nats_user: str = field(default_factory=lambda: os.environ.get("NATS_USER", "hq"))
    nats_password: str = field(
        default_factory=lambda: os.environ.get("NATS_PASSWORD", ""), repr=False
    )
    openbao_addr: str = field(
        default_factory=lambda: os.environ.get("OPENBAO_ADDR", "http://openbao:8200")
    )
    approle_file: str = field(
        default_factory=lambda: os.environ.get(
            "OPENBAO_APPROLE_FILE", "/run/secrets/hq/approle.json"
        )
    )
    runtime_url: str = field(
        default_factory=lambda: os.environ.get("RUNTIME_URL", "http://claude-runtime:8100")
    )
    listen_port: int = field(default_factory=lambda: _int("PORT", 8000))
    # Admission (prompt 03 §3)
    max_concurrency: int = field(default_factory=lambda: _int("LLM_MAX_CONCURRENCY", 3))
    reserved_high: int = field(default_factory=lambda: _int("LLM_RESERVED_HIGH", 1))
    p4_max_waiting: int = field(default_factory=lambda: _int("LLM_P4_MAX_WAITING", 4))
    max_waiting: int = field(default_factory=lambda: _int("LLM_MAX_WAITING", 32))
    queue_retry_after_s: int = field(default_factory=lambda: _int("LLM_QUEUE_RETRY_AFTER_S", 30))
    # Request limits (per caller overrides live in OpenBao)
    max_body_bytes: int = field(default_factory=lambda: _int("LLM_MAX_BODY_BYTES", 512 * 1024))
    max_timeout_s: int = field(default_factory=lambda: _int("LLM_MAX_TIMEOUT_S", 600))
    # Ceiling of a request's max_output_tokens (what the models accept everywhere).
    max_output_tokens: int = field(default_factory=lambda: _int("LLM_MAX_OUTPUT_TOKENS", 32_000))
    default_rpm: int = field(default_factory=lambda: _int("LLM_DEFAULT_RPM", 60))
    default_max_input_chars: int = field(
        default_factory=lambda: _int("LLM_DEFAULT_MAX_INPUT_CHARS", 200_000)
    )
    # Ledger housekeeping
    transcript_retention_days: int = field(
        default_factory=lambda: _int("LLM_TRANSCRIPT_RETENTION_DAYS", 30)
    )
    registry_ttl_s: int = field(default_factory=lambda: _int("LLM_REGISTRY_TTL_S", 30))
    # Anomaly rule (prompt 03 §6)
    anomaly_factor: float = field(
        default_factory=lambda: float(os.environ.get("LLM_ANOMALY_FACTOR", "3"))
    )
    anomaly_min_calls: int = field(default_factory=lambda: _int("LLM_ANOMALY_MIN_CALLS", 30))
    anomaly_interval_s: int = field(default_factory=lambda: _int("LLM_ANOMALY_INTERVAL_S", 300))
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "info"))
    # Test environments only: answer connections of kind 'fake' (prompt 05 §2).
    fake_backend: bool = field(default_factory=lambda: os.environ.get("LLM_FAKE_BACKEND") == "1")
    # Quota Controller (prompt 05 §8): ledger-window thresholds in tokens; 0 = off
    # (the SDK's own rate-limit events are the primary source).
    quota_warn_5h: int = field(default_factory=lambda: _int("LLM_QUOTA_WARN_TOKENS_5H", 0))
    quota_limit_5h: int = field(default_factory=lambda: _int("LLM_QUOTA_LIMIT_TOKENS_5H", 0))
    quota_warn_7d: int = field(default_factory=lambda: _int("LLM_QUOTA_WARN_TOKENS_7D", 0))
    quota_limit_7d: int = field(default_factory=lambda: _int("LLM_QUOTA_LIMIT_TOKENS_7D", 0))
    quota_interval_s: int = field(default_factory=lambda: _int("LLM_QUOTA_INTERVAL_S", 60))
