"""Test support (imported by the tests: the services share one pytest run,
so no conftest or package here). Fixtures: a mock Hetzner over HTTP, the hub's internal api as a mock
transport, the owner's secrets as a stub, and a valid plan."""

from __future__ import annotations

import base64
import os
import struct
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from prov_fake_hetzner import FakeHetzner

from hq_common import provisioning as P
from hq_provisioner.config import Settings
from hq_provisioner.hub import Hub
from hq_provisioner.vault import NotConfigured

TEMPLATES = os.environ.get(
    "HQ_PROVISION_TEMPLATES",
    str(Path(__file__).resolve().parents[3] / "infra" / "provisioning" / "templates"),
)
HETZNER_TOKEN = "hz-" + "Q" * 61  # a stand-in; the real one only ever lives in OpenBao


def public_key(seed: int, comment: str = "owner@laptop") -> str:
    blob = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + bytes([seed]) * 32
    return f"ssh-ed25519 {base64.b64encode(blob).decode()} {comment}"


OWNER_KEY = public_key(7)


def make_plan(**over: Any) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "id": "0193e7a1-0000-7000-8000-0000000000a1",
        "ref": "PV-0001",
        "founding": "C-0001",
        "company": "NX",
        "name": "nx-app-1",
        "type": "cpx42",
        "location": "fsn1",
        "image": "ubuntu-24.04",
        "private_network": True,
        "firewall": [
            {
                "direction": "in",
                "protocol": "tcp",
                "port": "22",
                "sources": ["198.51.100.7/32"],
                "note_fa": "SSH مالک",
            },
            {
                "direction": "in",
                "protocol": "tcp",
                "port": "443",
                "sources": ["0.0.0.0/0", "::/0"],
                "note_fa": "وب",
            },
        ],
        "software": list(P.SOFTWARE),
        "work_user": "nx",
        "repo": "behnamjalalico/nx-app",
        "monthly_eur": "26.99",
        "state": "sealed",
        "decision_ref": "D-000101",
        "run": None,
    }
    plan.update(over)
    plan["digest"] = P.digest(plan)
    return plan


class Secrets:
    def __init__(self) -> None:
        self.token: str | None = HETZNER_TOKEN
        self.keys: list[str] = [OWNER_KEY]
        self.reads = 0

    def hetzner_token(self) -> str:
        self.reads += 1
        if not self.token:
            raise NotConfigured("no Hetzner API token yet (make hetzner-token)")
        return self.token

    def owner_keys(self) -> list[str]:
        if not self.keys:
            raise NotConfigured("no SSH public key of the owner yet (make owner-ssh-key)")
        return list(self.keys)

    def api_token(self) -> str:
        return "svc-provisioner-token"


class FakeApi:
    """The api's internal provisioning endpoints (prompt 09, fork P9a's side)."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.queue: list[str] = []
        self.steps: list[dict[str, Any]] = []
        self.servers: list[dict[str, Any]] = []
        self.finished: list[dict[str, Any]] = []
        self.callbacks: list[dict[str, Any]] = []
        self.auth: set[str] = set()
        self.polls_until_callback = 2
        self.report: dict[str, Any] | None = None  # what the new server reports

    def add(self, plan: dict[str, Any], steps: list[dict[str, Any]] | None = None,
            sealed: str | None = None) -> str:  # fmt: skip
        rid = f"run-{len(self.runs) + 1}"
        self.runs[rid] = {"id": rid, "state": "sealed", "plan": plan,
                          "sealed_digest": plan["digest"] if sealed is None else sealed,
                          "steps": steps or [], "polls": 0}  # fmt: skip
        self.queue.append(rid)
        return rid

    def ok_report(self, plan: dict[str, Any]) -> dict[str, Any]:
        return {
            "received_at": "2026-10-18T00:20:00+00:00",
            "failed": False,
            "results": [
                {"key": k, "ok": True, "version": "v", "note": None}
                for k in P.ordered(plan["software"])
            ],
            "deploy_key": public_key(9, "coinepro-deploy@nx-app-1"),
        }

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.auth.add(request.headers.get("authorization", ""))
        path = request.url.path
        body = __import__("json").loads(request.content) if request.content else None
        if path == "/internal/v1/provisioning/runs/next":
            if not self.queue:
                return httpx.Response(204)
            run = self.runs[self.queue.pop(0)]
            return httpx.Response(200, json={"run": {k: v for k, v in run.items() if k != "polls"}})
        rid = path.split("/")[5] if path.count("/") >= 5 else ""
        run = self.runs.get(rid)
        if run is None:
            return httpx.Response(404, json={"code": "not_found"})
        if path.endswith("/steps"):
            self.steps.append({"run": rid, **body})
            return httpx.Response(204)
        if path.endswith("/server"):
            self.servers.append({"run": rid, **body})
            return httpx.Response(204)
        if path.endswith("/callback"):
            self.callbacks.append({"run": rid, **body})
            return httpx.Response(204)
        if path.endswith("/finish"):
            self.finished.append({"run": rid, **body})
            return httpx.Response(204)
        # GET the run: the server's report arrives after a few polls
        run["polls"] += 1
        ci = None
        if run["polls"] >= self.polls_until_callback:
            ci = self.report if self.report is not None else self.ok_report(run["plan"])
        return httpx.Response(200, json={"id": rid, "state": "running", "cloud_init": ci})

    def hub(self) -> Hub:
        return Hub(
            "http://api.test",
            lambda: "svc-provisioner-token",
            transport=httpx.MockTransport(self.handle),
        )

    def step_states(self, rid: str) -> list[tuple[str, str]]:
        return [(s["key"], s["state"]) for s in self.steps if s["run"] == rid]


@pytest.fixture(name="fake")
def fake_fixture() -> Iterator[FakeHetzner]:
    f = FakeHetzner()
    f.url = f.start()  # type: ignore[attr-defined]
    yield f
    f.stop()


@pytest.fixture(name="api")
def api_fixture() -> FakeApi:
    return FakeApi()


@pytest.fixture(name="secrets_")
def secrets_fixture() -> Secrets:
    return Secrets()


@pytest.fixture(name="settings")
def settings_fixture(fake: FakeHetzner) -> Settings:
    return Settings(
        hetzner_url=fake.url,  # type: ignore[attr-defined]
        templates_dir=TEMPLATES,
        callback_url="https://hq.example.test/api/v1/provisioning/callback",
        poll_s=0.01,
        boot_wait_s=5,
        callback_wait_s=5,
        hetzner_poll_s=0.01,
    )
