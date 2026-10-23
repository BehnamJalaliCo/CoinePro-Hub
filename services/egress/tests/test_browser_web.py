"""The profile browser against a real Chromium (prompt 12 §9.1.5, contract
§21.13): a fake site that plays ChatGPT on the loopback (TLS), reached only
through egress's own profile listener with a job's bucket, as in production.
A recipe downloads the original image; a login page is `expired` (never a
sign-in); a broken page is `recipe_failed` with its step; a foreign host is
refused; the profile persists between jobs, its files are 600, logout wipes
it; no cookie is ever in a result.

Runs where Playwright and its Chromium are installed:
`services/scripts/browser-test.sh`. Skipped in the services test image.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import ssl
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.async_api")

from hq_egress.browser_web import JobIn, Proxy, RunIn, Webd
from hq_egress.guard import Guard
from hq_egress.proxy import Buckets
from hq_egress.proxy import Proxy as EgressProxy

LOCAL = ipaddress.ip_network("127.0.0.1/32")
HOSTS = ("chat.test", "other.test")
COOKIE = "COOKIE-SECRET-123"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4
CHAT = b"""<html><body>
<textarea id='prompt'></textarea><button id='send'>Send</button>
<div id='out'></div>
<img src='https://other.test:PORT/track.png' id='tracker'>
<script>
document.getElementById('send').onclick = async () => {
  const q = document.getElementById('prompt').value;
  const out = document.getElementById('out');
  out.innerHTML = "<button id='stop'>Stop</button>";
  const r = await fetch('/api/answer', {method: 'POST', body: q});
  const t = await r.text();
  setTimeout(() => {
    out.innerHTML = "<p class='answer'>" + t + "</p><img class='gen' src='/img/1.png'>";
  }, 300);
};
</script></body></html>"""
LOGIN = b"<html><body><button data-testid='login-button'>Log in</button></body></html>"
BROKEN = b"<html><body><p>a redesigned page without the prompt box</p></body></html>"


class Site:
    def __init__(self) -> None:
        self.port = 0
        self.seen: list[dict[str, str]] = []
        self.server: asyncio.Server | None = None

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
        body_in = b""
        if int(headers.get("content-length") or 0):
            body_in = await reader.readexactly(int(headers["content-length"]))
        host = headers.get("host", "").split(":")[0]
        self.seen.append({"host": host, "method": method, "path": path,
                          "cookie": headers.get("cookie", "")})  # fmt: skip
        status, ctype, body, extra = 200, "text/html; charset=utf-8", b"", ""
        if path == "/chat":
            body = CHAT.replace(b"PORT", str(self.port).encode())
            extra = f"Set-Cookie: sess={COOKIE}; Max-Age=3600; Secure; HttpOnly; Path=/\r\n"
        elif path == "/to-login":
            status, extra = 302, "Location: /login\r\n"
        elif path == "/login":
            body = LOGIN
        elif path == "/broken":
            body = BROKEN
        elif path == "/api/answer":
            ctype, body = "text/plain; charset=utf-8", b"answer to: " + body_in[:40]
        elif path == "/img/1.png":
            ctype, body = "image/png", PNG
        elif path == "/whoami":
            body = f"<html><body><p id='who'>{'yes' if COOKIE in headers.get('cookie', '') else 'no'}</p></body></html>".encode()
        else:
            status, body = 404, b"no"
        writer.write(
            f"HTTP/1.1 {status} X\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\n"
            f"{extra}Connection: close\r\n\r\n".encode()
            + body
        )
        with contextlib.suppress(ConnectionError):
            await writer.drain()
        writer.close()


def _cert(tmp: Path) -> ssl.SSLContext:
    key, cert = tmp / "k.pem", tmp / "c.pem"
    subprocess.run(  # fixed arguments, the image's own openssl
        ["/usr/bin/openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
         "-nodes", "-days", "1", "-subj", "/CN=chat.test", "-keyout", str(key), "-out", str(cert),
         "-addext", "subjectAltName=" + ",".join(f"DNS:{h}" for h in HOSTS)],
        check=True, capture_output=True,
    )  # fmt: skip
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(str(cert), str(key))
    return ctx


@pytest.fixture
async def world(tmp_path: Path) -> AsyncIterator[tuple[Site, Webd, Buckets, str, Path]]:
    site = Site()
    site.server = await asyncio.start_server(site.handle, "127.0.0.1", 0, ssl=_cert(tmp_path))
    site.port = site.server.sockets[0].getsockname()[1]

    async def resolve(host: str, port: int) -> list[str]:
        if host not in HOSTS:
            raise OSError("no such name")
        return ["127.0.0.1"]

    guard = Guard(
        hub_hosts=frozenset({"hq.coinepro.com"}),
        resolver=resolve,
        allow=(LOCAL,),
        extra_ports={h: frozenset({site.port}) for h in HOSTS},
    )
    buckets = Buckets()
    proxy = EgressProxy(guard, buckets, mode="profile", clients=(LOCAL,))
    pserver = await proxy.serve("127.0.0.1", 0)
    server = f"http://127.0.0.1:{pserver.sockets[0].getsockname()[1]}"
    profiles = tmp_path / "profiles"
    d = Webd(profiles=profiles, insecure_tls=True)
    await d.start()
    try:
        yield site, d, buckets, server, profiles
    finally:
        await d.stop()
        pserver.close()
        site.server.close()


def _job(site: Site, buckets: Buckets, server: str, start: str, task: str = "image",
         steps: list[dict[str, Any]] | None = None) -> JobIn:  # fmt: skip
    key, secret = buckets.open("substitute.web", "A2", 50_000_000, hosts=frozenset({"chat.test"}))
    recipe = {
        "key": "chatgpt-web",
        "version": "2026-10-22.1",
        "start_url": f"https://chat.test:{site.port}{start}",
        "hosts": ["chat.test"],
        "expired": {"url_contains": ["/login"], "selectors": ["[data-testid=login-button]"]},
        "task": task,
        "timeout_s": 30,
        "steps": steps
        or [
            {"do": "goto", "url": "{start_url}"},
            {"do": "wait", "selector": "#prompt", "timeout_s": 10},
            {"do": "fill", "selector": "#prompt", "text": "{prompt}"},
            {"do": "click", "selector": "#send"},
            {"do": "wait", "selector": "#stop", "timeout_s": 5, "optional": True},
            {"do": "wait", "selector": "img.gen", "timeout_s": 10},
            {"do": "read", "selector": ".answer"},
            {"do": "download_image", "selector": "img.gen", "attr": "src"},
        ],
    }
    return JobIn(
        account="chatgpt-web",
        recipe=recipe,
        prompt="a calm sea at dawn, no text",
        timeout_s=30,
        proxy=Proxy(server=server, username=key, password=secret),
        max_file_bytes=1_000_000,
    )


async def test_a_recipe_downloads_the_original_image(world: Any) -> None:
    site, d, buckets, server, _ = world
    got = await d.job(_job(site, buckets, server, "/chat"))
    assert got["ok"] is True, got
    assert got["text_md"].startswith("answer to: a calm sea")
    import base64

    assert base64.b64decode(got["file"]["b64"]) == PNG
    assert COOKIE not in json.dumps(got)  # never a cookie in a result
    # The tracker on another host never left (the route and the bucket both refuse it).
    assert not [s for s in site.seen if s["host"] == "other.test"]


async def test_the_profile_persists_its_files_are_600_and_logout_wipes_it(world: Any) -> None:
    site, d, buckets, server, profiles = world
    assert (await d.job(_job(site, buckets, server, "/chat")))["ok"] is True
    who = [{"do": "goto", "url": "{start_url}"}, {"do": "read", "selector": "#who"}]
    got = await d.job(_job(site, buckets, server, "/whoami", task="text", steps=who))
    assert got["text_md"] == "yes"  # the session of the last job is still there
    files = [p for p in (profiles / "chatgpt-web").rglob("*") if p.is_file()]
    assert files
    assert all(p.stat().st_mode & 0o077 == 0 for p in files), [
        (str(p), oct(p.stat().st_mode)) for p in files if p.stat().st_mode & 0o077
    ]
    assert (await d.logout("chatgpt-web")) == {"ok": True}
    got = await d.job(_job(site, buckets, server, "/whoami", task="text", steps=who))
    assert got["text_md"] == "no"


async def test_a_login_page_is_expired_never_a_sign_in(world: Any) -> None:
    site, d, buckets, server, _ = world
    got = await d.job(_job(site, buckets, server, "/to-login"))
    assert (got["ok"], got["error"], got["step"]) == (False, "expired", "0:goto"), got
    assert not [s for s in site.seen if s["method"] == "POST"]  # nothing was typed or sent


async def test_a_broken_page_names_its_failing_step(world: Any) -> None:
    site, d, buckets, server, _ = world
    got = await d.job(_job(site, buckets, server, "/broken"))
    assert (got["ok"], got["error"], got["step"]) == (False, "recipe_failed", "1:wait"), got


async def test_a_foreign_host_is_refused(world: Any) -> None:
    site, d, buckets, server, _ = world
    steps = [{"do": "goto", "url": f"https://other.test:{site.port}/chat"}]
    got = await d.job(_job(site, buckets, server, "/chat", task="text", steps=steps))
    assert (got["ok"], got["error"]) == (False, "recipe_failed")
    assert "own hosts" in got["detail"]
    key, secret = buckets.open("web.browse", "A0", 10_000_000, hosts=frozenset({"chat.test"}))
    run = RunIn(
        profile="chatgpt-web",
        allowed_hosts=["chat.test"],
        steps=[{"do": "goto", "url": f"https://other.test:{site.port}/chat"}],
        proxy={"server": server, "username": key, "password": secret},
        account={"key": "chatgpt-web", "site": "chat.test", "browse": {"kind": "profile"}},
        time_s=10,
    )
    got = await d.run(run)
    assert got["steps"][0]["error"] == "host_not_allowed"
    assert not [s for s in site.seen if s["host"] == "other.test"]


# Prompt 14.1 §1.5: the profile jobs hide the automation flag.
async def test_profile_jobs_hide_the_automation_flag(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    class Chromium:
        async def launch_persistent_context(self, user_data_dir: str, **kw: Any) -> object:
            seen.update(kw, user_data_dir=user_data_dir)
            return object()

    class PW:
        chromium = Chromium()

    d = Webd(profiles=tmp_path)
    d._pw = PW()  # type: ignore[assignment]
    await d.open("chatgpt-web", Proxy(server="http://egress:3132"))
    assert seen["ignore_default_args"] == ["--enable-automation"]
    assert "--disable-blink-features=AutomationControlled" in seen["args"]
    assert seen["user_data_dir"] == str(tmp_path / "chatgpt-web")
