"""The private route (contract §26.1a): TLS keeps the hub's name while the TCP
connection goes to the private IP, and the public fallback."""

from __future__ import annotations

import asyncio
import shutil
import ssl
import subprocess
from pathlib import Path
from typing import Any

import httpcore
import httpx
import pytest
from conftest import run

from hq_runner.net import PinnedAsyncBackend, Route, async_transport, hub_parts, sync_transport

HOST = "hq.coinepro.test"


class RecordingBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.hosts: list[str] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> Any:
        self.hosts.append(host)
        raise httpcore.ConnectError("recorded")


def test_pinned_backend_only_rewrites_the_hub_host() -> None:
    rec = RecordingBackend()
    b = PinnedAsyncBackend(HOST, "10.10.1.4", inner=rec)
    for h in (HOST, "HQ.Coinepro.Test", "github.com"):
        with pytest.raises(httpcore.ConnectError):
            run(b.connect_tcp(h, 443))
    assert rec.hosts == ["10.10.1.4", "10.10.1.4", "github.com"]


def test_route_prefers_private_and_falls_back_to_public() -> None:
    async def ok(host: str, port: int, limit_s: float) -> float:
        return 0.42

    async def down(host: str, port: int, limit_s: float) -> float:
        if host == "10.10.1.4":
            raise TimeoutError
        return 12.0

    async def public_dns(host: str, port: int) -> list[str]:
        return ["203.0.113.10"]

    async def hosts_line(host: str, port: int) -> list[str]:
        return ["10.10.1.4"]

    r = Route(f"https://{HOST}", "10.10.1.4", probe=ok, resolver=public_dns)
    st = run(r.select())
    assert (st.via, st.pinned_ip, st.rtt_ms) == ("private", "10.10.1.4", 0.4)

    r = Route(f"https://{HOST}", "10.10.1.4", probe=down, resolver=public_dns)
    st = run(r.select())
    assert (st.via, st.pinned_ip, st.rtt_ms) == ("public", None, 12.0)

    # Without --hub-ip, an /etc/hosts line pointing at the private address still counts as private.
    assert (
        run(Route(f"https://{HOST}", None, probe=ok, resolver=hosts_line).select()).via == "private"
    )
    assert (
        run(Route(f"https://{HOST}", None, probe=ok, resolver=public_dns).select()).via == "public"
    )


def test_connect_failure_moves_to_public_then_back(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]
    private_up = [True]

    async def probe(host: str, port: int, limit_s: float) -> float:
        if host == "10.10.1.4" and not private_up[0]:
            raise OSError("unreachable")
        return 1.0

    async def dns(host: str, port: int) -> list[str]:
        return ["203.0.113.10"]

    async def scenario() -> list[str]:
        r = Route(f"https://{HOST}", "10.10.1.4", probe=probe, resolver=dns, clock=lambda: now[0])
        seen = [(await r.select()).via]
        private_up[0] = False
        await r.connect_failed()
        seen.append(r.via)
        private_up[0] = True
        now[0] += 10
        await r.refresh()
        seen.append(r.via)  # not retried yet
        now[0] += 400
        await r.refresh()
        seen.append(r.via)
        await r.aclose()
        return seen

    assert run(scenario()) == ["private", "public", "public", "private"]


def test_hub_url_rules() -> None:
    assert hub_parts("https://hq.coinepro.com") == ("https", "hq.coinepro.com", 443)
    assert hub_parts("http://127.0.0.1:8080")[2] == 8080
    for bad in ("http://hq.coinepro.com", "ftp://x", "hq.coinepro.com"):
        with pytest.raises(ValueError):
            hub_parts(bad)


@pytest.fixture(scope="module")
def cert(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    if not shutil.which("openssl"):
        pytest.skip("openssl missing")
    d = tmp_path_factory.mktemp("tls")
    crt, key = d / "hub.crt", d / "hub.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "2",
            "-subj",
            f"/CN={HOST}",
            "-addext",
            f"subjectAltName=DNS:{HOST}",
            "-keyout",
            str(key),
            "-out",
            str(crt),
        ],
        check=True,
        capture_output=True,
    )
    return crt, key


async def tls_hub(crt: Path, key: Path, seen: dict[str, Any]) -> asyncio.Server:
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(crt, key)

    def sni(sock: ssl.SSLObject, name: str | None, _: ssl.SSLContext) -> None:
        seen["sni"] = name

    ctx.sni_callback = sni  # type: ignore[assignment]

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = (await reader.readuntil(b"\r\n\r\n")).decode()
        seen["host"] = next(
            line.split(":", 1)[1].strip()
            for line in head.split("\r\n")
            if line.lower().startswith("host:")
        )
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
        await writer.drain()
        writer.close()

    return await asyncio.start_server(handle, "127.0.0.1", 0, ssl=ctx)


def test_tls_to_the_private_ip_keeps_the_hub_name_and_verifies_it(cert: tuple[Path, Path]) -> None:
    crt, key = cert

    async def scenario() -> dict[str, Any]:
        seen: dict[str, Any] = {}
        server = await tls_hub(crt, key, seen)
        port = server.sockets[0].getsockname()[1]
        hub = f"https://{HOST}:{port}"
        try:
            # The hostname does not resolve at all: only the pinned IP can reach it.
            async with httpx.AsyncClient(
                transport=async_transport(hub, "127.0.0.1", str(crt))
            ) as c:
                resp = await c.get(f"{hub}/api/v1/runners/ping")
            seen["status"] = resp.status_code
            # Verification is on: without the hub's CA the same connection is refused.
            async with httpx.AsyncClient(transport=async_transport(hub, "127.0.0.1")) as c:
                with pytest.raises(httpx.ConnectError, match="CERTIFICATE_VERIFY_FAILED"):
                    await c.get(f"{hub}/")
            # The synchronous client used by the Claude hook does the same.
            seen["sync"] = await asyncio.to_thread(
                lambda: (
                    httpx.Client(transport=sync_transport(hub, "127.0.0.1", str(crt)))
                    .get(f"{hub}/")
                    .status_code
                )
            )
        finally:
            server.close()
        return seen

    seen = run(scenario())
    assert seen["status"] == 200 and seen["sync"] == 200
    assert seen["sni"] == HOST
    assert seen["host"].startswith(HOST)
