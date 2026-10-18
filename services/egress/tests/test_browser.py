"""The browser service against a real Chromium (prompt 7.1 §1.4, §1.5): what
a click lands on, what a signed-in session may send, and where an account's
header goes. Fake sites and egress's own proxy run on the loopback; the
browser reaches them only through the proxy, as in production.

Runs where Playwright and its Chromium are installed:
`services/scripts/browser-test.sh` (the pinned Playwright image, no network).
Skipped in the services test image.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
from collections.abc import AsyncIterator
from typing import Any

import pytest

pytest.importorskip("playwright.async_api")

from hq_egress.accounts import Account
from hq_egress.browser import Browserd, RunIn
from hq_egress.guard import Guard
from hq_egress.proxy import Buckets, Proxy

LOCAL = ipaddress.ip_network("127.0.0.1/32")
HOSTS = ("shop.test", "acct.test", "other.test")
SECRET = "acct-browse-" + "S" * 24
CHECKOUT = (
    b"<html><body><form action='/order' method='post'><input name='addr'>"
    b"<button type='submit' id='go'><span id='inner'>Continue</span></button></form></body></html>"
)
LOGIN = (
    b"<html><body><form action='/session' method='post'><input name='user'>"
    b"<input type='password' name='pw'><button type='submit' id='sub'>Go</button></form>"
    b"<label for='sub' id='lbl'>Next</label></body></html>"
)
APP = (
    b"<html><body><div id='find'>Find</div><div id='load'>Load</div><p id='out'>-</p><script>"
    b"const out = document.getElementById('out');"
    b"document.getElementById('find').onclick = () => fetch('/api/search', {method: 'POST', body: 'q'})"
    b".then(r => r.text()).then(t => { out.textContent = t; });"
    b"document.getElementById('load').onclick = () => fetch('/api/pay', {method: 'POST', body: 'x'})"
    b".then(() => { out.textContent = 'sent'; }).catch(() => { out.textContent = 'stopped'; });"
    b"</script></body></html>"
)


class Sites:
    """Every fake host on one loopback server; records Host, method, path, headers."""

    def __init__(self) -> None:
        self.port = 0
        self.seen: list[dict[str, str]] = []
        self.server: asyncio.Server | None = None

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except (asyncio.IncompleteReadError, ConnectionError):
            writer.close()
            return
        lines = head.decode("latin-1").split("\r\n")
        method, path, _ = lines[0].split(" ", 2)
        headers = {
            k.strip().lower(): v.strip()
            for k, _, v in (ln.partition(":") for ln in lines[1:] if ln)
        }
        if int(headers.get("content-length") or 0):
            await reader.readexactly(int(headers["content-length"]))
        host = headers.get("host", "").split(":")[0]
        self.seen.append({**headers, "host": host, "method": method, "path": path})
        status, extra, body = 200, "", b"<html><body><p>landed</p></body></html>"
        if path == "/checkout":
            body = CHECKOUT
        elif path == "/login":
            body = LOGIN
        elif path == "/app":
            body = APP
        elif path == "/redir":
            status, body = 302, b""
            extra = f"Location: http://other.test:{self.port}/landing\r\n"
        elif path == "/api/search":
            body = b"found"
        writer.write(
            f"HTTP/1.1 {status} X\r\nContent-Type: text/html\r\nContent-Length: {len(body)}\r\n"
            f"{extra}Connection: close\r\n\r\n".encode()
            + body
        )
        with contextlib.suppress(ConnectionError):
            await writer.drain()
        writer.close()

    def at(self, host: str, path: str) -> list[dict[str, str]]:
        return [s for s in self.seen if s["host"] == host and s["path"] == path]


@pytest.fixture
async def world() -> AsyncIterator[tuple[Sites, Browserd, dict[str, Any]]]:
    sites = Sites()
    sites.server = await asyncio.start_server(sites.handle, "127.0.0.1", 0)
    sites.port = sites.server.sockets[0].getsockname()[1]

    async def resolve(host: str, port: int) -> list[str]:
        if host not in HOSTS:
            raise OSError("no such name")
        return ["127.0.0.1"]

    guard = Guard(
        hub_hosts=frozenset({"hq.coinepro.com"}),
        resolver=resolve,
        allow=(LOCAL,),
        extra_ports={h: frozenset({sites.port}) for h in HOSTS},
    )
    buckets = Buckets()
    proxy = Proxy(guard, buckets, mode="browser", clients=(LOCAL,))
    pserver = await proxy.serve("127.0.0.1", 0)
    key, secret = buckets.open("web.browse", "A0", 10_000_000)
    login = {
        "server": f"http://127.0.0.1:{pserver.sockets[0].getsockname()[1]}",
        "username": key,
        "password": secret,
    }
    d = Browserd()
    await d.start()
    try:
        yield sites, d, login
    finally:
        await d.stop()
        pserver.close()
        sites.server.close()


def _run(login: dict[str, Any], steps: list[dict[str, Any]], **kw: Any) -> RunIn:
    return RunIn(steps=steps, proxy=login, time_s=12, **kw)


async def test_a_click_is_judged_by_its_activation_target(world: Any) -> None:
    sites, d, login = world
    base = f"http://shop.test:{sites.port}"
    # A span inside a checkout form's submit button is that button.
    got = await d.run(_run(login, [{"do": "goto", "url": base + "/checkout"},
                                   {"do": "click", "target": "#inner"}]))  # fmt: skip
    assert got["steps"][0]["ok"], got
    assert got["blocked"] == {"step": 1, "code": "needs_owner", "reason": "commitment_form"}
    # A label is the control it labels: the submit of a password form.
    got = await d.run(_run(login, [{"do": "goto", "url": base + "/login"},
                                   {"do": "click", "target": "#lbl"}]))  # fmt: skip
    assert got["blocked"]["reason"] == "credentials_or_payment_form", got
    assert not [s for s in sites.seen if s["method"] == "POST"]


def _account(port: int) -> Account:
    return Account(
        key="acct",
        site="acct.test",
        secret=SECRET,
        browse={"kind": "header", "name": "X-Acct"},
        allow=[{"methods": ["POST"], "path_prefix": "/api/search"}],
        ports=[port],
    )


async def test_a_signed_in_session_sends_only_the_listed_calls(world: Any) -> None:
    sites, d, login = world
    base = f"http://acct.test:{sites.port}"
    steps = [
        {"do": "goto", "url": base + "/app"},
        {"do": "click", "target": "#find"},
        {"do": "wait", "text": "800"},
        {"do": "read"},
        {"do": "click", "target": "#load"},
        {"do": "wait", "text": "1500"},
        {"do": "read"},
    ]
    got = await d.run(_run(login, steps, account=_account(sites.port)))
    assert "found" in got["steps"][3]["text"], got  # the listed call went
    (search,) = sites.at("acct.test", "/api/search")
    assert search["method"] == "POST" and search["x-acct"] == SECRET
    assert got["blocked"]["code"] == "needs_owner", got  # the other one did not
    assert got["blocked"]["reason"] == "commitment_request" and got["blocked"]["step"] >= 4
    assert not sites.at("acct.test", "/api/pay")
    assert SECRET not in str(got)


async def test_the_account_header_never_follows_a_redirect(world: Any) -> None:
    sites, d, login = world
    got = await d.run(
        _run(
            login,
            [{"do": "goto", "url": f"http://acct.test:{sites.port}/redir"}, {"do": "read"}],
            account=_account(sites.port),
        )
    )
    assert got["steps"][0]["ok"] and "landed" in got["steps"][1]["text"], got
    assert got["final_url"].startswith("http://other.test:")
    (first,) = sites.at("acct.test", "/redir")
    assert first["x-acct"] == SECRET  # its own host gets it
    (landing,) = sites.at("other.test", "/landing")
    assert "x-acct" not in landing  # the host it redirects to never does
