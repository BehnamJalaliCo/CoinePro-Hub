"""Prometheus metrics (per-app registry). Labels never include actors or text."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class Metrics:
    def __init__(self) -> None:
        r = self.registry = CollectorRegistry()
        self.calls = Counter(
            "llm_calls_total",
            "Model calls by final status",
            ["company", "connection", "model", "status", "priority"],
            registry=r,
        )
        self.tokens = Counter(
            "llm_tokens_total",
            "Tokens by kind",
            ["company", "connection", "model", "kind"],
            registry=r,
        )
        self.cost = Counter(
            "llm_cost_usd_total",
            "USD: real API cost or subscription equivalent",
            ["company", "connection", "kind"],
            registry=r,
        )
        self.latency = Histogram(
            "llm_call_latency_seconds",
            "End-to-end call latency",
            ["connection", "model"],
            registry=r,
            buckets=(0.5, 1, 2, 5, 10, 20, 40, 80, 160, 320, 640),
        )
        self.queue_depth = Gauge(
            "llm_queue_depth", "Waiting requests by priority", ["priority"], registry=r
        )
        self.active = Gauge("llm_active_calls", "Calls holding a concurrency slot", registry=r)
        self.capacity = Gauge("llm_concurrency_capacity", "Configured concurrency", registry=r)
        self.breaker_state = Gauge(
            "llm_breaker_state", "0 closed, 1 half-open, 2 open", ["connection"], registry=r
        )
        self.quota_exhausted = Gauge(
            "llm_connection_quota_exhausted",
            "1 while the quota is used up",
            ["connection"],
            registry=r,
        )
        self.budget_rejections = Counter(
            "llm_budget_rejections_total", "P4 calls refused by a budget", ["company"], registry=r
        )
        self.budget_alerts = Counter(
            "llm_budget_alerts_total", "Budget threshold alerts", ["company", "level"], registry=r
        )
        self.queue_rejections = Counter(
            "llm_queue_rejections_total",
            "Requests refused by admission",
            ["priority", "reason"],
            registry=r,
        )
        self.rate_limited = Counter(
            "llm_caller_rate_limited_total", "Caller rate-limit refusals", ["caller"], registry=r
        )
        self.anomalies = Counter("llm_anomaly_alerts_total", "Usage anomaly alerts", registry=r)
        self.event_failures = Counter(
            "llm_event_publish_failures_total", "NATS publish failures", registry=r
        )
        # Our price table vs the SDK's own estimate (subscription calls).
        self.sdk_cost_ratio = Gauge(
            "llm_sdk_cost_ratio",
            "SDK cost estimate / our priced cost, rolling 1 h",
            ["connection", "model"],
            registry=r,
        )
        self.sdk_cost = Counter(
            "llm_sdk_cost_usd_total",
            "SDK's own cost estimate (comparison only)",
            ["connection", "model"],
            registry=r,
        )
        self.priced_cost = Counter(
            "llm_priced_cost_usd_total",
            "Our priced cost for the calls that also carry an SDK estimate",
            ["connection", "model"],
            registry=r,
        )
        self.cost_ratio_alerts = Counter(
            "llm_cost_ratio_alerts_total", "SDK/price-table drift alerts", registry=r
        )
