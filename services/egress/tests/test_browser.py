"""The browser service against a real Chromium (prompt 7.1 §1.4, §1.5, §2.17,
§2.20, §2.21 and §3): what a click lands on, what a signed-in session may
send, where an account's header goes (its own host, over https only), the
GETs that commit, what a screenshot masks, the files a call may keep, and
Chromium's own sandbox. Fake sites (plain and TLS) and egress's own proxy
run on the loopback; the browser reaches them only through the proxy, as in
production.

Runs where Playwright and its Chromium are installed:
`services/scripts/browser-test.sh` (the pinned Playwright image, no network,
production's user, capabilities and seccomp profile). Skipped in the
services test image.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import ipaddress
import os
import ssl
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.async_api")

from hq_egress import browser as B
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
LOGIN2 = (  # a login whose secret field is a text field (the policy's pass_selector)
    b"<html><body><form action='/session' method='post'><input id='user' name='user'>"
    b"<input id='pw2' name='pw2'><button type='submit' id='sub'>Go</button></form></body></html>"
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
GETS = (  # GETs that commit, from a link, a script and a choice that sends its form
    "<html><body><a id='answer' href='/forms/d/e/1FAI/formResponse?entry.1=yes'>Answer</a>"
    "<div id='hook'>Refresh</div><p id='out'>-</p>"
    "<form action='/billing/plan' method='post'><select id='plan' name='plan' "
    "onchange='this.form.submit()'><option>a</option><option>b</option></select></form>"
    "<button id='ok' type='button'>تاييد</button>"  # Arabic yeh: Persian «تایید»
    "<script>document.getElementById('hook').onclick = () => fetch('/webhook/7f1c2a')"
    ".then(() => { document.getElementById('out').textContent = 'sent'; })"
    ".catch(() => { document.getElementById('out').textContent = 'stopped'; });</script>"
    "</body></html>"
).encode()
BOX = "position:absolute;left:{x}px;top:{y}px;width:300px;height:60px;font-size:30px;"
MASKED = (
    "<html><body style='margin:0;background:#fff'>"
    f"<input type='password' id='pw' value='hunter2-visible' style='{BOX.format(x=20, y=20)}'>"
    f"<input id='pw2' value='also-masked-field' style='{BOX.format(x=20, y=120)}'>"
    f"<input id='plain' value='not masked' style='{BOX.format(x=20, y=220)}'>"
    "</body></html>"
).encode()
MAGENTA = [255, 0, 255]  # Playwright's mask colour


class Sites:
    """Every fake host on one loopback server (and its TLS twin); records
    Host, method, path and headers."""

    def __init__(self) -> None:
        self.port = 0
        self.tls_port = 0
        self.seen: list[dict[str, str]] = []
        self.servers: list[asyncio.Server] = []

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except (asyncio.IncompleteReadError, ConnectionError, ssl.SSLError):
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
        ctype = "text/html; charset=utf-8"
        pages = {"/checkout": CHECKOUT, "/login": LOGIN, "/login2": LOGIN2, "/app": APP,
                 "/gets": GETS, "/masked": MASKED}  # fmt: skip
        if path in pages:
            body = pages[path]
        elif path == "/redir":
            status, body = 302, b""
            extra = f"Location: http://other.test:{self.port}/landing\r\n"
        elif path == "/api/search":
            body = b"found"
        elif path == "/shows-secret":
            body = f"<html><body><p>Your key: {SECRET}</p></body></html>".encode()
        elif path == "/file-with-secret":
            ctype, body = "text/plain", f"config\nkey={SECRET}\n".encode()
        elif path == "/file":
            ctype, body = "application/octet-stream", b"\x00\x01plain file" * 10
        elif path == "/big-file":
            ctype, body = "application/octet-stream", b"x" * 50_000
        writer.write(
            f"HTTP/1.1 {status} X\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\n"
            f"{extra}Connection: close\r\n\r\n".encode()
            + body
        )
        with contextlib.suppress(ConnectionError):
            await writer.drain()
        writer.close()

    def at(self, host: str, path: str) -> list[dict[str, str]]:
        return [s for s in self.seen if s["host"] == host and s["path"] == path]


def _cert(tmp: Path) -> ssl.SSLContext:
    """A self-signed certificate for the fake hosts (the test context accepts it)."""
    key, cert = tmp / "k.pem", tmp / "c.pem"
    subprocess.run(  # fixed arguments, the image's own openssl
        ["/usr/bin/openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
         "-nodes", "-days", "1", "-subj", "/CN=acct.test", "-keyout", str(key), "-out", str(cert),
         "-addext", "subjectAltName=" + ",".join(f"DNS:{h}" for h in HOSTS)],
        check=True, capture_output=True,
    )  # fmt: skip
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(str(cert), str(key))
    return ctx


@pytest.fixture
async def world(tmp_path: Path) -> AsyncIterator[tuple[Sites, Browserd, dict[str, Any]]]:
    sites = Sites()
    plain = await asyncio.start_server(sites.handle, "127.0.0.1", 0)
    tls = await asyncio.start_server(sites.handle, "127.0.0.1", 0, ssl=_cert(tmp_path))
    sites.servers = [plain, tls]
    sites.port = plain.sockets[0].getsockname()[1]
    sites.tls_port = tls.sockets[0].getsockname()[1]

    async def resolve(host: str, port: int) -> list[str]:
        if host not in HOSTS:
            raise OSError("no such name")
        return ["127.0.0.1"]

    guard = Guard(
        hub_hosts=frozenset({"hq.coinepro.com"}),
        resolver=resolve,
        allow=(LOCAL,),
        extra_ports={h: frozenset({sites.port, sites.tls_port}) for h in HOSTS},
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
    d = Browserd(insecure_tls=True)
    await d.start()
    try:
        yield sites, d, login
    finally:
        await d.stop()
        pserver.close()
        for s in sites.servers:
            s.close()


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


def _account(port: int, **kw: Any) -> Account:
    return Account(
        key="acct",
        site="acct.test",
        secret=SECRET,
        **{
            "browse": {"kind": "header", "name": "X-Acct"},
            "allow": [{"methods": ["POST"], "path_prefix": "/api/search"}],
            "ports": [port],
            **kw,
        },
    )


async def test_a_signed_in_session_sends_only_the_listed_calls(world: Any) -> None:
    sites, d, login = world
    base = f"https://acct.test:{sites.tls_port}"
    steps = [
        {"do": "goto", "url": base + "/app"},
        {"do": "click", "target": "#find"},
        {"do": "wait", "text": "800"},
        {"do": "read"},
        {"do": "click", "target": "#load"},
        {"do": "wait", "text": "1500"},
        {"do": "read"},
    ]
    got = await d.run(_run(login, steps, account=_account(sites.tls_port)))
    assert "found" in got["steps"][3]["text"], got  # the listed call went
    (search,) = sites.at("acct.test", "/api/search")
    assert search["method"] == "POST" and search["x-acct"] == SECRET
    assert got["blocked"]["code"] == "needs_owner", got  # the other one did not
    assert got["blocked"]["reason"] == "commitment_request" and got["blocked"]["step"] >= 4
    assert not sites.at("acct.test", "/api/pay")
    assert SECRET not in str(got)


async def test_the_account_header_never_follows_a_redirect_nor_goes_in_clear(world: Any) -> None:
    sites, d, login = world
    got = await d.run(
        _run(
            login,
            [{"do": "goto", "url": f"https://acct.test:{sites.tls_port}/redir"}, {"do": "read"}],
            account=_account(sites.tls_port),
        )
    )
    assert got["steps"][0]["ok"] and "landed" in got["steps"][1]["text"], got
    assert got["final_url"].startswith("http://other.test:")
    (first,) = sites.at("acct.test", "/redir")
    assert first["x-acct"] == SECRET  # its own host gets it, over https
    (landing,) = sites.at("other.test", "/landing")
    assert "x-acct" not in landing  # the host it redirects to never does
    # Over plain http, its own host does not get it either (7.1 §2.17).
    got = await d.run(_run(login, [{"do": "goto", "url": f"http://acct.test:{sites.port}/app"}],
                           account=_account(sites.port)))  # fmt: skip
    assert got["steps"][0]["ok"], got
    assert "x-acct" not in sites.at("acct.test", "/app")[-1]


async def test_gets_that_commit_and_a_choice_that_submits(world: Any) -> None:
    """7.1 §2.21: a goto, a link and a page's own fetch to a GET that
    commits; a select whose onchange sends its form; a button in Arabic
    letters. None of them leaves."""
    sites, d, login = world
    base = f"http://shop.test:{sites.port}"
    page = {"do": "goto", "url": base + "/gets"}
    cases = [
        ([{"do": "goto", "url": base + "/forms/d/e/1FAI/formResponse?entry.1=a"}], 0,
         "form_response"),
        ([page, {"do": "click", "target": "#answer"}], 1, "commitment_link"),
        ([page, {"do": "click", "target": "#hook"}, {"do": "wait", "text": "1000"}], 1,
         "webhook_trigger"),
        ([page, {"do": "select", "target": "#plan", "text": "b"}], 1, "form_submit"),
        ([page, {"do": "click", "target": "#ok"}], 1, "commitment_button"),
    ]  # fmt: skip
    for steps, step, reason in cases:
        got = await d.run(_run(login, steps))
        blocked = got["blocked"] or {}
        assert (blocked.get("code"), blocked.get("reason")) == ("needs_owner", reason), (steps, got)
        # A page's own request may come while the next step (the wait) runs.
        assert step <= blocked["step"] <= step + 1, got
    assert not [s for s in sites.seen if "formResponse" in s["path"] or "webhook" in s["path"]]
    assert not sites.at("shop.test", "/billing/plan")


async def _pixel(d: Browserd, png: bytes, x: int, y: int) -> list[int]:
    """The colour of one pixel of a PNG, read by Chromium itself (a canvas)."""
    assert d.browser is not None
    page = await d.browser.new_page()
    try:
        await page.set_content("<canvas id='c'></canvas>")
        rgb: list[int] = await page.evaluate(
            """async ([src, x, y]) => {
                 const img = new Image(); img.src = src; await img.decode();
                 const c = document.getElementById('c'); c.width = img.width; c.height = img.height;
                 const g = c.getContext('2d'); g.drawImage(img, 0, 0);
                 return Array.from(g.getImageData(x, y, 1, 1).data.slice(0, 3));
               }""",
            ["data:image/png;base64," + base64.b64encode(png).decode(), x, y],
        )
        return rgb
    finally:
        await page.close()


async def test_screenshots_mask_secret_fields_and_a_page_that_shows_the_secret(
    world: Any,
) -> None:
    """7.1 §3: a real screenshot paints over password fields and the
    policy's secret field; a page that shows the secret gets no screenshot,
    and its text comes back scrubbed."""
    sites, d, login = world
    base = f"https://acct.test:{sites.tls_port}"
    acct = _account(sites.tls_port, browse={
        "kind": "form", "login_url": base + "/login2", "username": "bot",
        "user_selector": "#user", "pass_selector": "#pw2", "submit_selector": "#sub"})  # fmt: skip
    got = await d.run(_run(login, [{"do": "goto", "url": base + "/masked"}, {"do": "screenshot"}],
                           account=acct))  # fmt: skip
    assert all(s["ok"] for s in got["steps"]), got
    (shot,) = got["files"]
    png = base64.b64decode(shot["data_b64"])
    assert await _pixel(d, png, 170, 50) == MAGENTA  # input[type=password]
    assert await _pixel(d, png, 170, 150) == MAGENTA  # the policy's pass_selector
    assert await _pixel(d, png, 170, 250) != MAGENTA  # a plain field is not masked
    (signin,) = [s for s in sites.at("acct.test", "/session") if s["method"] == "POST"]
    assert signin  # the owner's login form was sent, by egress, before the steps
    got = await d.run(_run(login, [{"do": "goto", "url": base + "/shows-secret"}, {"do": "read"},
                                   {"do": "screenshot"}], account=acct))  # fmt: skip
    assert "[secret]" in got["steps"][1]["text"] and SECRET not in str(got)
    assert got["steps"][2] == {**got["steps"][2], "ok": False, "error": "secret_on_page"}
    assert got["files"] == []


async def test_files_one_cap_for_all_and_never_a_secret(world: Any) -> None:
    """7.1 §2.17, §2.20, §3: a file that holds the secret is dropped; a
    download beyond its cap is refused, not cut; the call's files share one cap."""
    sites, d, login = world
    base = f"https://acct.test:{sites.tls_port}"
    acct = _account(sites.tls_port)
    got = await d.run(_run(login, [{"do": "download", "url": base + "/file-with-secret"}],
                           account=acct))  # fmt: skip
    assert got["steps"][0]["error"] == "file_held_secret" and got["files"] == [], got
    got = await d.run(_run(login, [{"do": "download", "url": base + "/file"}], account=acct))
    assert got["steps"][0]["ok"] and got["files"][0]["size"] == 120, got
    got = await d.run(_run(login, [{"do": "download", "url": base + "/big-file"}],
                           max_download_bytes=10_000))  # fmt: skip
    assert got["steps"][0]["error"] == "download_too_large" and got["files"] == [], got
    got = await d.run(_run(login, [{"do": "goto", "url": base + "/masked"}, {"do": "screenshot"},
                                   {"do": "download", "url": base + "/file"}],
                           max_files_bytes=200))  # fmt: skip
    assert got["steps"][1]["error"] == "files_too_large" and got["files"] == [], got


async def test_a_failed_sign_in_has_its_own_code(world: Any) -> None:
    sites, d, login = world
    elsewhere = _account(sites.tls_port, browse={
        "kind": "form", "login_url": f"https://other.test:{sites.tls_port}/login2",
        "pass_selector": "#pw2"})  # fmt: skip
    got = await d.run(_run(login, [{"do": "read"}], account=elsewhere))
    assert got["code"] == "sign_in_failed" and got["steps"] == [], got
    missing = _account(sites.tls_port, browse={
        "kind": "form", "login_url": f"https://acct.test:{sites.tls_port}/login2",
        "pass_selector": "#no-such-field"})  # fmt: skip
    got = await d.run(RunIn(steps=[{"do": "read"}], proxy=login, time_s=3, account=missing))
    assert got["code"] == "sign_in_failed", got


def _userns(pid: int | str) -> str:
    return os.readlink(f"/proc/{pid}/ns/user")


def _renderers() -> dict[str, bytes]:
    """Chromium's renderer processes in this container: pid -> command line."""
    out: dict[str, bytes] = {}
    for pid in (p for p in os.listdir("/proc") if p.isdigit()):
        with contextlib.suppress(OSError):
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes()
            if b"--type=renderer" in cmd:
                out[pid] = cmd
    return out


async def test_the_sandbox_is_on_and_the_heap_capped(world: Any) -> None:
    """7.1 §2.20: Chromium runs sandboxed (its renderers in user namespaces
    of their own), each renderer's heap is capped, WebRTC uses no direct UDP."""
    _, d, _ = world
    assert B.SANDBOX and d.browser is not None
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in B.ARGS
    page = await d.browser.new_page()
    try:
        limit = await page.evaluate("performance.memory.jsHeapSizeLimit")
        assert limit < 2 * B.JS_HEAP_MB * 1024 * 1024, limit  # Chromium's default is ~4 GB
        renderers = _renderers()
        assert renderers and all(b"--no-sandbox" not in cmd for cmd in renderers.values())
        assert all(_userns(p) != _userns("self") for p in renderers), renderers
    finally:
        await page.close()


async def test_without_the_sandbox_every_call_has_its_own_browser(
    world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fallback (BROWSER_SANDBOX=0): a --no-sandbox process is never
    shared between calls (so never between companies)."""
    sites, _, login = world
    d = Browserd(sandbox=False, insecure_tls=True)
    launched: list[Any] = []
    real = d._launch

    async def counting() -> Any:
        b = await real()
        launched.append(b)
        return b

    monkeypatch.setattr(d, "_launch", counting)
    await d.start()
    try:
        assert d.browser is None and d.ready()
        for _ in range(2):
            got = await d.run(_run(login, [{"do": "goto", "url": f"http://shop.test:{sites.port}/"},
                                           {"do": "read"}]))  # fmt: skip
            assert "landed" in got["steps"][1]["text"], got
        assert len(launched) == 2 and not any(b.is_connected() for b in launched)
    finally:
        await d.stop()
