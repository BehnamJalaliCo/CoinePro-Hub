import json
import logging
import time
from pathlib import Path

import httpx
import pytest

from hq_common import heartbeat, logs, tokens
from hq_common.openbao import OpenBaoClient, OpenBaoError, SecretNotFound


def test_tokens_roundtrip() -> None:
    tok = tokens.new_token()
    assert len(tok) == 64
    assert tokens.matches(tok, tokens.digest(tok))
    assert not tokens.matches(tok + "x", tokens.digest(tok))
    assert not tokens.matches(tok, "")


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer abc", "abc"),
        ("bearer  abc ", "abc"),
        ("Basic abc", None),
        ("Bearer ", None),
        (None, None),
    ],
)
def test_bearer(header: str | None, expected: str | None) -> None:
    assert tokens.bearer(header) == expected


def test_json_formatter_redacts_content_fields() -> None:
    fmt = logs.JsonFormatter("svc")
    rec = logging.makeLogRecord(
        {"msg": "call finished", "levelname": "INFO", "prompt": "SECRET PROMPT", "call_id": "c1"}
    )
    line = json.loads(fmt.format(rec))
    assert line["prompt"] == "[redacted]"
    assert line["call_id"] == "c1"
    assert "SECRET PROMPT" not in fmt.format(rec)


def test_json_formatter_drops_exception_message() -> None:
    fmt = logs.JsonFormatter("svc")
    try:
        raise ValueError("SECRET PROMPT inside an error")
    except ValueError:
        import sys

        rec = logging.makeLogRecord(
            {"msg": "boom", "levelname": "ERROR", "exc_info": sys.exc_info()}
        )
    out = fmt.format(rec)
    assert "SECRET PROMPT" not in out
    assert json.loads(out)["exc_type"] == "ValueError"


async def test_heartbeat_writes_and_removes(tmp_path: Path) -> None:
    path = tmp_path / "hb.json"
    states = iter([{"ok": True}, {"ok": False}])

    async def check() -> dict[str, object]:
        return next(states)

    import asyncio

    task = asyncio.create_task(heartbeat.run(check, path=path, interval=0.05))
    await asyncio.sleep(0.02)
    assert heartbeat.is_fresh(path)
    await asyncio.sleep(0.08)
    assert not path.exists()
    task.cancel()
    assert not heartbeat.is_fresh(tmp_path / "missing.json")


def _bao_transport(calls: list[str], kv_status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/v1/auth/approle/login":
            body = json.loads(request.content)
            if body != {"role_id": "r", "secret_id": "s"}:
                return httpx.Response(400)
            return httpx.Response(200, json={"auth": {"client_token": "t", "lease_duration": 3600}})
        if request.headers.get("X-Vault-Token") != "t":
            return httpx.Response(403)
        if kv_status != 200:
            return httpx.Response(kv_status)
        return httpx.Response(200, json={"data": {"data": {"k": "v"}}})

    return httpx.MockTransport(handler)


async def test_openbao_login_and_read(tmp_path: Path) -> None:
    creds = tmp_path / "approle.json"
    creds.write_text(json.dumps({"role_id": "r", "secret_id": "s"}))
    calls: list[str] = []
    client = OpenBaoClient("http://bao", creds, transport=_bao_transport(calls))
    assert await client.read_kv("svc/config") == {"k": "v"}
    assert await client.read_kv("svc/config") == {"k": "v"}
    assert calls.count("POST /v1/auth/approle/login") == 1  # token reused
    await client.aclose()


async def test_openbao_errors(tmp_path: Path) -> None:
    creds = tmp_path / "approle.json"
    creds.write_text(json.dumps({"role_id": "r", "secret_id": "s"}))
    client = OpenBaoClient("http://bao", creds, transport=_bao_transport([], kv_status=404))
    with pytest.raises(SecretNotFound):
        await client.read_kv("missing")
    missing = OpenBaoClient("http://bao", tmp_path / "nope.json", transport=_bao_transport([]))
    with pytest.raises(OpenBaoError):
        await missing.read_kv("x")
    assert time.time() > 0
