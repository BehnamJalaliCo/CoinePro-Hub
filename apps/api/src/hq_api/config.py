"""Settings from the environment (non-secret). Secrets come from OpenBao."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from hq_common import oversight_share


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    db_host: str = field(default_factory=lambda: _env("DB_HOST", "postgres"))
    db_port: int = field(default_factory=lambda: _int("DB_PORT", 5432))
    db_name: str = field(default_factory=lambda: _env("DB_NAME", "hq"))
    db_user: str = field(default_factory=lambda: _env("DB_USER", "hq_api"))
    db_password: str = field(default_factory=lambda: _env("DB_PASSWORD"), repr=False)
    db_pool_size: int = field(default_factory=lambda: _int("DB_POOL_SIZE", 8))
    nats_url: str = field(default_factory=lambda: _env("NATS_URL", "nats://nats:4222"))
    nats_user: str = field(default_factory=lambda: _env("NATS_USER", "hq"))
    nats_password: str = field(default_factory=lambda: _env("NATS_PASSWORD"), repr=False)
    temporal_address: str = field(default_factory=lambda: _env("TEMPORAL_ADDRESS", "temporal:7233"))
    temporal_namespace: str = field(default_factory=lambda: _env("TEMPORAL_NAMESPACE", "default"))
    task_queue: str = field(default_factory=lambda: _env("HQ_TASK_QUEUE", "hq-core"))
    opa_url: str = field(default_factory=lambda: _env("OPA_URL", "http://opa:8181"))
    openbao_addr: str = field(default_factory=lambda: _env("OPENBAO_ADDR", "http://openbao:8200"))
    approle_file: str = field(
        default_factory=lambda: _env("OPENBAO_APPROLE_FILE", "/run/secrets/hq/approle.json")
    )
    # Public origin (https://<domain>) and WebAuthn RP id (<domain>). Empty
    # while the hub has no domain: login is then off (503 origin_not_configured).
    public_origin: str = field(default_factory=lambda: _env("HQ_PUBLIC_ORIGIN").rstrip("/"))
    rp_id: str = field(default_factory=lambda: _env("HQ_WEBAUTHN_RP_ID"))
    rp_name: str = field(default_factory=lambda: _env("HQ_WEBAUTHN_RP_NAME", "CoinePro HQ"))
    files_root: str = field(default_factory=lambda: _env("HQ_FILES_ROOT", "/data/files"))
    # Append-only anchors of the audit chain head, outside Postgres (backup set).
    audit_anchor_file: str = field(default_factory=lambda: _env("HQ_AUDIT_ANCHOR_FILE"))
    # Extra WebAuthn origins for the Android app ("android:apk-key-hash:..."), comma-separated.
    android_origins: str = field(default_factory=lambda: _env("HQ_ANDROID_ORIGINS"))
    listen_port: int = field(default_factory=lambda: _int("PORT", 8000))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "info"))
    max_body_bytes: int = field(default_factory=lambda: _int("HQ_MAX_BODY_BYTES", 1024 * 1024))
    max_file_bytes: int = field(default_factory=lambda: _int("HQ_MAX_FILE_BYTES", 25 * 1024 * 1024))
    # Speech to text (prompt 6 §3): the self-hosted Whisper service, reached by the
    # worker only (empty: the stt profile is off); the light model's punctuation pass.
    stt_url: str = field(default_factory=lambda: _env("STT_URL"))
    stt_punctuation: bool = field(default_factory=lambda: _env("STT_PUNCTUATION", "on") == "on")
    stt_punctuation_model: str = field(
        default_factory=lambda: _env("STT_PUNCTUATION_MODEL", "claude-haiku-5-5")
    )
    # How long POST /transcribe waits for the worker (a 15-minute recording on CPU).
    transcribe_wait_s: int = field(default_factory=lambda: _int("HQ_TRANSCRIBE_WAIT_S", 600))
    # The academy (prompt 08 §7): the judge of eval answers (a lighter model;
    # QC's for a case marked sensitive) and the monthly cap, a share of the
    # holding's budget (every company's monthly envelope), else a fixed default.
    academy_judge_model: str = field(
        default_factory=lambda: _env("ACADEMY_JUDGE_MODEL", "claude-haiku-5-5")
    )
    academy_qc_model: str = field(
        default_factory=lambda: _env("ACADEMY_QC_MODEL", "claude-sonnet-5-5")
    )
    academy_budget_share: float = field(
        default_factory=lambda: float(_env("ACADEMY_BUDGET_SHARE", "0.05"))
    )
    academy_monthly_tokens: int = field(
        default_factory=lambda: _int("ACADEMY_MONTHLY_TOKENS", 1_000_000)
    )
    # MCP calls (prompt 07 §3): per run and per company per owner day.
    mcp_calls_per_run: int = field(default_factory=lambda: _int("HQ_MCP_CALLS_PER_RUN", 20))
    mcp_calls_per_company_day: int = field(
        default_factory=lambda: _int("HQ_MCP_CALLS_PER_COMPANY_DAY", 300)
    )
    # The agents' internet (prompt 07 §2.8): caps per run and per company per day
    # (requests = egress log rows; browser seconds = web.browse sessions).
    egress_run_requests: int = field(default_factory=lambda: _int("EGRESS_RUN_REQUESTS", 150))
    egress_run_bytes: int = field(
        default_factory=lambda: _int("EGRESS_RUN_BYTES", 64 * 1024 * 1024)
    )
    egress_run_browser_s: int = field(default_factory=lambda: _int("EGRESS_RUN_BROWSER_S", 300))
    egress_day_requests: int = field(default_factory=lambda: _int("EGRESS_DAY_REQUESTS", 5000))
    egress_day_bytes: int = field(
        default_factory=lambda: _int("EGRESS_DAY_BYTES", 2 * 1024 * 1024 * 1024)
    )
    egress_call_bytes: int = field(
        default_factory=lambda: _int("EGRESS_CALL_BYTES", 20 * 1024 * 1024)
    )
    # Sessions (contract §2): sliding 30 days, absolute 90 days.
    session_sliding_days: int = 30
    session_absolute_days: int = 90
    step_up_ttl_s: int = 120
    challenge_ttl_s: int = 300
    enrolment_ttl_s: int = 900
    # Rate limits (per minute)
    auth_rate_per_ip: int = field(default_factory=lambda: _int("HQ_AUTH_RATE_PER_IP", 30))
    rate_per_principal: int = field(default_factory=lambda: _int("HQ_RATE_PER_PRINCIPAL", 1200))
    # Background loops in the api process
    outbox_relay: bool = field(default_factory=lambda: _env("HQ_OUTBOX_RELAY", "1") == "1")
    # The agent runtime (worker, prompt 05)
    llm_router_url: str = field(
        default_factory=lambda: _env("LLM_ROUTER_URL", "http://llm-router:8000")
    )
    gateway_url: str = field(default_factory=lambda: _env("GATEWAY_URL", "http://gateway:8080"))
    api_internal_url: str = field(
        default_factory=lambda: _env("HQ_API_INTERNAL_URL", "http://api:8000")
    )
    prometheus_url: str = field(
        default_factory=lambda: _env("PROMETHEUS_URL", "http://prometheus:9090")
    )
    hub_status_dir: str = field(default_factory=lambda: _env("HQ_HUB_STATUS_DIR", "/hub-status"))
    # The Chief Overseer (prompt 08 §2): protocol runs handed to a model per
    # owner day (the rest are code, skipped or deferred), and each run's token
    # budget, never above the assignee's charter (overseer v2: 200K a run).
    oversight_model_runs_per_day: int = field(
        default_factory=lambda: _int("HQ_OVERSIGHT_MODEL_RUNS_PER_DAY", 3)
    )
    oversight_run_tokens: int = field(
        default_factory=lambda: _int("HQ_OVERSIGHT_RUN_TOKENS", 60_000)
    )
    # The oversight share (prompt 08 §2.3, contract §18.1 v1.4.4): the overseer
    # and QC together use at most this share of AGENT_DAILY_TOKEN_CAP (llm-router
    # enforces it; once spent, only critical protocols run, the rest are deferred).
    oversight_daily_share: float = field(
        default_factory=lambda: oversight_share.parse_share(_env("OVERSIGHT_DAILY_SHARE"))
    )
    # Off: the protocols' schedules exist but stay paused (tests).
    oversight_schedules: bool = field(
        default_factory=lambda: _env("HQ_OVERSIGHT_SCHEDULES", "on") == "on"
    )
    # Real-model spend of all agent runs per UTC day (input + output + cache
    # tokens); a run is refused once the day's total reaches it. 0 means nothing:
    # every run is refused (prompt 08.1; never "no cap").
    agent_daily_token_cap: int = field(
        default_factory=lambda: _int("AGENT_DAILY_TOKEN_CAP", 2_000_000)
    )
    agent_max_run_s: int = field(default_factory=lambda: _int("AGENT_MAX_RUN_S", 3000))
    # The token budget of an incident's work (site checks): the responder's run stops at it.
    incident_budget_tokens: int = field(
        default_factory=lambda: _int("AGENT_INCIDENT_BUDGET_TOKENS", 60_000)
    )
    # An agent's work request (work.request, prompt 5.1 §2.6): the new root work's
    # token budget is the requester's budget left, at most this; and a request
    # made from requested work may go this many hops deep, no further.
    agent_request_budget_tokens: int = field(
        default_factory=lambda: _int("AGENT_REQUEST_BUDGET_TOKENS", 60_000)
    )
    agent_request_chain_max: int = field(default_factory=lambda: _int("AGENT_REQUEST_CHAIN_MAX", 2))
    agent_step_timeout_s: int = field(default_factory=lambda: _int("AGENT_STEP_TIMEOUT_S", 300))
    agent_actions_per_step: int = field(default_factory=lambda: _int("AGENT_ACTIONS_PER_STEP", 8))
    agent_tool_calls_per_run: int = field(
        default_factory=lambda: _int("AGENT_TOOL_CALLS_PER_RUN", 48)
    )
    agent_dispatch_interval_s: float = field(
        default_factory=lambda: float(_env("AGENT_DISPATCH_INTERVAL_S", "3"))
    )
    # The CEOs' daily report runs (prompt 05 §6): built, off until the owner says so.
    ceo_daily_reports: bool = field(
        default_factory=lambda: _env("HQ_CEO_DAILY_REPORTS", "off") == "on"
    )
    # The morning report rewritten by a model (prompt 05 §6); off = rule-based only.
    morning_report_llm: bool = field(
        default_factory=lambda: _env("HQ_MORNING_REPORT_LLM", "on") == "on"
    )
    # The Code Workshop's runtime (contract §17.3): "" until the owner chooses
    # (managed | self_hosted); the model and effort a session gets by default.
    workshop_runtime: str = field(default_factory=lambda: _env("WORKSHOP_RUNTIME", ""))
    workshop_model: str = field(default_factory=lambda: _env("WORKSHOP_MODEL", "claude-opus-5-5"))
    workshop_effort: str = field(default_factory=lambda: _env("WORKSHOP_EFFORT", "high"))

    @property
    def login_configured(self) -> bool:
        """Passkeys need a real domain over HTTPS (contract §2)."""
        parts = urlsplit(self.public_origin)
        return bool(
            self.rp_id
            and parts.scheme == "https"
            and parts.hostname is not None
            and (parts.hostname == self.rp_id or parts.hostname.endswith("." + self.rp_id))
        )
