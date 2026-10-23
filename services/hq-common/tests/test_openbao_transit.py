"""OpenBao transit for the archive's secret level (prompt 14 §3): a fresh
data key wrapped by `archive-secret`, unwrapped for one read; the transit key
never leaves OpenBao and no error carries a key or a plaintext."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from hq_common.openbao import OpenBaoClient, OpenBaoError

DEK = bytes(range(32))


def _transport(calls: list[str], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/v1/auth/approle/login":
            return httpx.Response(200, json={"auth": {"client_token": "t", "lease_duration": 3600}})
        if status != 200:
            return httpx.Response(status, json={"errors": ["no"]})
        if request.url.path == "/v1/transit/datakey/plaintext/archive-secret":
            assert json.loads(request.content) == {"bits": 256}
            return httpx.Response(
                200,
                json={"data": {"plaintext": base64.b64encode(DEK).decode(), "ciphertext": "vault:v1:abc"}},
            )
        if request.url.path == "/v1/transit/decrypt/archive-secret":
            assert json.loads(request.content) == {"ciphertext": "vault:v1:abc"}
            return httpx.Response(200, json={"data": {"plaintext": base64.b64encode(DEK).decode()}})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _creds(tmp_path: Path) -> Path:
    p = tmp_path / "approle.json"
    p.write_text(json.dumps({"role_id": "r", "secret_id": "s"}))
    return p


async def test_a_data_key_is_wrapped_by_transit_and_unwrapped_for_one_read(tmp_path: Path) -> None:
    calls: list[str] = []
    bao = OpenBaoClient("http://bao", _creds(tmp_path), transport=_transport(calls))
    dek, wrapped = await bao.transit_datakey("archive-secret")
    assert dek == DEK and wrapped == "vault:v1:abc"
    assert await bao.transit_decrypt("archive-secret", wrapped) == DEK
    assert calls.count("POST /v1/auth/approle/login") == 1
    await bao.aclose()


async def test_a_refused_transit_call_names_only_its_path_and_status(tmp_path: Path) -> None:
    bao = OpenBaoClient("http://bao", _creds(tmp_path), transport=_transport([], status=500))
    with pytest.raises(OpenBaoError) as info:
        await bao.transit_decrypt("archive-secret", "vault:v1:abc")
    assert str(info.value) == "transit decrypt failed (HTTP 500)"
    await bao.aclose()
