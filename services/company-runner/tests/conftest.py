"""A fake hub for the runner's tests: the §26.4 runner routes on an httpx
MockTransport, recording every request."""

from __future__ import annotations

import asyncio
import json
import sys
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_runner.config import Config
from hq_runner.net import Route

HUB = "https://hq.coinepro.test"
TESTING = Path(__file__).resolve().parent.parent / "testing"
FAKE_CLAUDE = TESTING / "fake_claude.py"


def problem(status: int, code: str) -> httpx.Response:
    return httpx.Response(
        status,
        json={"type": "about:blank", "title": code, "status": status, "code": code},
        headers={"content-type": "application/problem+json"},
    )


@dataclass
class FakeHub:
    approve_after: int = 2
    expired: bool = False
    expires_in: int = 900
    tokens: set[str] = field(default_factory=lambda: {"hqr1_token_one_ABCDEFGHIJKLMNOP"})
    revoked: bool = False
    jobs: deque[dict[str, Any]] = field(default_factory=deque)
    cancels: list[str] = field(default_factory=list)
    events: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    requests: list[tuple[str, str, dict[str, str], Any]] = field(default_factory=list)
    files: dict[str, bytes] = field(default_factory=dict)
    token_polls: int = 0
    issued: bool = False
    rotations: int = 0
    gone_jobs: set[str] = field(default_factory=set)
    on_events: Callable[[str, list[dict[str, Any]]], None] | None = None

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def authed(self, request: httpx.Request) -> bool:
        auth = request.headers.get("authorization", "")
        return auth.startswith("Bearer ") and auth[7:] in self.tokens

    async def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, str(request.url), dict(request.headers), body))
        if path == "/api/v1/runners/pair":
            assert set(body) == {
                "company",
                "name",
                "hostname",
                "private_ip",
                "os",
                "runner_version",
            }
            return httpx.Response(
                200,
                json={
                    "device_code": "dev-123",
                    "user_code": "ABCD-1234",
                    "expires_in": self.expires_in,
                    "interval": 0,
                },
            )
        if path == "/api/v1/runners/token":
            assert body == {"device_code": "dev-123"}
            self.token_polls += 1
            if self.expired:
                return problem(410, "expired_token")
            if self.token_polls <= self.approve_after:
                return problem(428, "authorization_pending")
            if self.issued:
                return problem(400, "expired_token")
            self.issued = True
            return httpx.Response(
                200, json={"runner_token": "hqr1_token_one_ABCDEFGHIJKLMNOP", "server_id": "srv-7"}
            )
        if path.startswith(("/api/v1/runners/", "/api/v1/files/")):
            if self.revoked:
                return problem(410, "runner_revoked")
            if not self.authed(request):
                return problem(401, "unauthorized")
        if path == "/api/v1/runners/rotate":
            self.rotations += 1
            new = f"hqr1_rotated_{self.rotations}_ABCDEFGHIJKLMNOP"
            self.tokens = {new}
            return httpx.Response(200, json={"runner_token": new})
        if path == "/api/v1/runners/jobs/next":
            if self.cancels:
                c, self.cancels = self.cancels, []
                return httpx.Response(200, json={"job": None, "cancel": c})
            if self.jobs:
                return httpx.Response(200, json={"job": self.jobs.popleft()})
            await asyncio.sleep(0.02)
            return httpx.Response(204)
        if path.startswith("/api/v1/runners/jobs/"):
            jid, what = path.split("/")[5], path.split("/")[6]
            if jid in self.gone_jobs:
                return problem(409, "job_not_running")
            if what == "events":
                assert set(body) == {"events"}
                self.events.setdefault(jid, []).extend(body["events"])
                if self.on_events:
                    self.on_events(jid, body["events"])
                return httpx.Response(204)
            if what == "result":
                assert set(body) <= {"exit_code", "summary_fa", "usage", "data"}
                self.results[jid] = body
                return httpx.Response(204)
        if path == "/api/v1/runners/classify":
            cmd = body["cmd"]
            return httpx.Response(
                200, json={"category": "db_drop" if "DROP DATABASE" in cmd else None}
            )
        if path.startswith("/api/v1/files/"):
            data = self.files.get(path)
            return (
                httpx.Response(200, content=data) if data is not None else problem(404, "not_found")
            )
        return problem(404, "not_found")

    def texts(self, jid: str, type_: str = "stdout") -> list[str]:
        return [
            e["data"]["text"]
            for e in self.events.get(jid, [])
            if e["type"] == type_ and "text" in e["data"]
        ]

    def result_output(self, jid: str) -> Any:
        return self.results.get(jid, {}).get("data")


async def no_dns(host: str, port: int) -> list[str]:
    return []


async def fast_probe(host: str, port: int, limit_s: float) -> float:
    return 1.5


def make_route(hub: FakeHub, hub_ip: str | None = None) -> Route:
    return Route(HUB, hub_ip, transport=hub.transport(), probe=fast_probe, resolver=no_dns)


@pytest.fixture
def fake_hub() -> FakeHub:
    return FakeHub()


@pytest.fixture
def cfg_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "home" / ".config" / "hq-runner" / "config.json"
    monkeypatch.setenv("HQ_RUNNER_CONFIG", str(p))
    return p


@pytest.fixture
def cfg() -> Config:
    return Config(
        hub=HUB,
        runner_token="hqr1_token_one_ABCDEFGHIJKLMNOP",
        server_id="srv-7",
        company="FX",
        name="fx-main",
    )


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


@pytest.fixture
def python() -> str:
    return sys.executable
