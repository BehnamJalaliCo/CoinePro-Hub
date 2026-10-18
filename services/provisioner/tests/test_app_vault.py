"""The provisioner's API (the api only) and its OpenBao reads."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from prov_fake_hetzner import FakeHetzner
from prov_support import (  # noqa: F401 - pytest fixtures
    OWNER_KEY,
    Secrets,
    fake_fixture,
    public_key,
    secrets_fixture,
    settings_fixture,
)

from hq_common.openbao import OpenBaoError
from hq_provisioner.app import build_app
from hq_provisioner.config import Settings
from hq_provisioner.vault import NotConfigured, Vault, public_keys


def client(
    settings: Settings, secrets_: Secrets, ip: str, wake: threading.Event | None = None
) -> TestClient:
    app = build_app(settings, secrets_, wake or threading.Event())
    return TestClient(app, client=(ip, 41000))


def test_only_the_api_network_may_call(
    fake: FakeHetzner, settings: Settings, secrets_: Secrets
) -> None:
    ok = client(settings, secrets_, "172.30.10.4")
    r = ok.get("/v1/pricing", params={"type": "cpx42", "location": "fsn1"})
    assert r.status_code == 200 and r.json()["monthly_eur"] == "26.99"
    assert client(settings, secrets_, "172.30.8.9").get("/v1/servers").status_code == 403
    assert client(settings, secrets_, "10.10.1.2").post("/v1/wake").status_code == 403
    assert ok.get("/v1/pricing", params={"type": "x;rm", "location": "fsn1"}).status_code == 422
    assert ok.get("/v1/pricing", params={"type": "cpx42", "location": "sin"}).status_code == 422
    assert ok.get("/v1/servers").json() == {"items": []}
    wake = threading.Event()
    assert (
        client(settings, secrets_, "172.30.10.4", wake).post("/v1/wake").status_code == 202
        and wake.is_set()
    )


def test_without_the_owners_token_it_says_so(
    fake: FakeHetzner, settings: Settings, secrets_: Secrets
) -> None:
    secrets_.token = None
    c = client(settings, secrets_, "172.30.10.4")
    for r in (
        c.get("/v1/pricing", params={"type": "cpx42", "location": "fsn1"}),
        c.get("/v1/servers"),
    ):
        assert r.status_code == 503 and r.json()["code"] == "channel_not_configured"
    fake.fail[("GET", "/v1/pricing")] = 1
    secrets_.token = "t"
    assert (
        c.get("/v1/pricing", params={"type": "cpx42", "location": "fsn1"}).json()["code"]
        == "hetzner_unavailable"
    )


def test_public_keys_only() -> None:
    marker = "PRIVATE " + "KEY"  # a stand-in, built so no scanner takes it for a leak
    priv = f"-----BEGIN OPENSSH {marker}-----\nb3BlbnNzaC1rZXktdjE=\n-----END OPENSSH {marker}-----"
    keys = public_keys(
        [OWNER_KEY, OWNER_KEY, priv, "ssh-dss AAAA x", 'from="*" ' + OWNER_KEY, public_key(2)]
    )
    assert keys == [OWNER_KEY, public_key(2)]
    assert public_keys("not a list") == []


def bao(secrets: dict[str, dict[str, object]], calls: list[str]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/v1/auth/approle/login":
            body = json.loads(request.content)
            if body != {"role_id": "r", "secret_id": "s"}:
                return httpx.Response(400)
            return httpx.Response(200, json={"auth": {"client_token": "tok", "lease_duration": 60}})
        if request.url.path == "/v1/auth/token/revoke-self":
            return httpx.Response(204)
        assert request.headers["x-vault-token"] == "tok"
        path = request.url.path.removeprefix("/v1/kv/data/")
        if path not in secrets:
            return httpx.Response(404)
        return httpx.Response(200, json={"data": {"data": secrets[path]}})

    return httpx.MockTransport(handle)


def test_the_vault_reads_at_the_moment_of_work(tmp_path: Path) -> None:
    creds = tmp_path / "approle.json"
    creds.write_text(json.dumps({"role_id": "r", "secret_id": "s"}))
    calls: list[str] = []
    data: dict[str, dict[str, object]] = {
        "provisioning/hetzner": {"token": "hz"},
        "provisioning/ssh-keys": {"keys": [OWNER_KEY, "-----BEGIN " + "PRIVATE KEY-----"]},
        "provisioner/config": {"api_token": "svc"},
    }
    v = Vault("http://bao.test", str(creds), transport=bao(data, calls))
    assert v.hetzner_token() == "hz" and v.owner_keys() == [OWNER_KEY] and v.api_token() == "svc"
    # A fresh login per read, revoked right after: no token waits in memory.
    assert (
        calls.count("POST /v1/auth/approle/login") == 3
        and calls.count("POST /v1/auth/token/revoke-self") == 3
    )
    for path in ("provisioning/hetzner", "provisioning/ssh-keys"):
        data.pop(path)
    with pytest.raises(NotConfigured, match="make hetzner-token"):
        v.hetzner_token()
    with pytest.raises(NotConfigured, match="make owner-ssh-key"):
        v.owner_keys()
    data["provisioning/ssh-keys"] = {"keys": []}
    with pytest.raises(NotConfigured):
        v.owner_keys()
    with pytest.raises(OpenBaoError, match="AppRole file"):
        Vault("http://bao.test", str(tmp_path / "missing.json")).hetzner_token()
