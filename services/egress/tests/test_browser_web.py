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
import os
import ssl
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.async_api")

from hq_egress.browser_web import JobIn, Proxy, ProxyRelay, RunIn, Webd, run_recipe
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
# ⟨2026-11-17⟩ DeepSeek's answer with web search: each source mark is an <a> around
# span.ds-markdown-cite whose only visible text is its number (a hidden "-" before it).
CITED = """<html lang='fa' dir='rtl'><body><div class='ds-markdown'>
<p>بیت‌کوین سقف ۲۱ میلیون دارد<a href='https://src.test/cap' target='_blank'><span class='ds-markdown-cite'><span style='opacity:0'>-</span><span>1</span></span></a>.</p>
<p>راهنما: <a href='https://src.test/guide'>راهنمای کیف پول</a> و <a href='https://src.test/raw'>https://src.test/raw</a></p>
<p>منبع دوم<a href='https://src.test/two'><span class='ds-markdown-cite'><span>-</span><span>12</span></span></a></p>
</div></body></html>""".encode()
# A chat whose box is a form (chatgpt.com's composer): its send is a form submit.
CHAT_FORM = b"""<html><body>
<form id='f'><textarea id='prompt'></textarea><button id='send' type='submit'>Send</button></form>
<div id='out'></div>
<script>
document.getElementById('f').onsubmit = async (e) => {
  e.preventDefault();
  const r = await fetch('/api/answer', {method: 'POST', body: document.getElementById('prompt').value});
  document.getElementById('out').innerHTML = "<p class='answer'>" + await r.text() + "</p>";
};
</script></body></html>"""
# ⟨20.1⟩ ChatGPT as the hub's fa-IR profile sees it: Persian labels only, a
# contenteditable composer that sends on Enter, a stop button while it writes,
# the answer as a markdown block under a hidden Persian heading, then its
# action bar. The real chatgpt-web text task must read the answer, not the
# user's own words.
CHAT_FA = """<html lang='fa' dir='rtl'><body>
<main><div id='thread'></div>
<div contenteditable='true' id='prompt-textarea' aria-label='پیام خود را بنویسید'></div>
<button data-testid='send-button' aria-label='ارسال درخواست'>↑</button></main>
<script>
const box = document.getElementById('prompt-textarea');
const thread = document.getElementById('thread');
async function send() {
  const q = box.innerText.trim();
  if (!q) return;
  box.innerText = '';
  thread.innerHTML = "<article><h5 class='sr-only'>شما گفتید:</h5><div class='user'>" + q + "</div></article>";
  const stop = document.createElement('button');
  stop.setAttribute('data-testid', 'stop-button'); stop.setAttribute('aria-label', 'توقف پاسخ');
  document.querySelector('main').appendChild(stop);
  const r = await fetch('/api/answer', {method: 'POST', body: q});
  const t = await r.text();
  setTimeout(() => {
    stop.remove();
    thread.innerHTML += "<article><h6 class='sr-only'>ChatGPT گفت:</h6><div data-message-author-role='assistant'>"
      + "<div class='markdown prose'><p>" + t + "</p></div></div>"
      + "<div><button data-testid='copy-turn-action-button' aria-label='رونوشت'>⧉</button>"
      + "<button aria-label='بلند خواندن'>🔊</button></div></article>";
  }, 400);
}
box.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
document.querySelector('[data-testid=send-button]').onclick = send;
</script></body></html>""".encode()
LOGIN = b"<html><body><button data-testid='login-button'>Log in</button></body></html>"
# ⟨2026-11-18⟩ Search Console's export: a menu item whose click navigates to a file the site sends
# as an attachment (Chromium's download path ends the profile browser there; `capture` takes it)
EXPORT = b"""<html><body><div role='menuitem' aria-label='Download CSV' id='csv'
onclick="location.href='/export/san?x=1'">Download CSV</div></body></html>"""
ZIP = b"PK\x03\x04" + b"csv-export" * 8
BROKEN = b"<html><body><p>a redesigned page without the prompt box</p></body></html>"
# ⟨2026-11-15⟩ Gemini: the generated picture is a blob: URL the page revokes once it is drawn
REVOKED = b"""<html><body><div id='out'></div><script>
const c = document.createElement('canvas'); c.width = 40; c.height = 30;
const g = c.getContext('2d'); g.fillStyle = '#d02020'; g.fillRect(0, 0, 40, 30);
c.toBlob((b) => {
  const u = URL.createObjectURL(b);
  const img = document.createElement('img');
  img.className = 'gen';
  img.onload = () => { URL.revokeObjectURL(u); img.dataset.ready = '1'; };
  img.src = u;
  document.getElementById('out').appendChild(img);
}, 'image/png');
</script></body></html>"""


# ⟨2026-11-18⟩ YouTube's upload as the browser sees it: the chosen file sent by fetch() (an
# image from another host too: a quiet job's proxy must still refuse it).
UPLOAD = b"""<html><body><input type='file' id='f'><button id='go'>Upload</button><p id='done'></p>
<img id='leak' src='https://other.test:PORT/img/1.png'>
<script>
document.getElementById('go').onclick = async () => {
  const r = await fetch('/up', {method: 'POST', body: document.getElementById('f').files[0]});
  document.getElementById('done').textContent = 'sent ' + await r.text();
};
</script></body></html>"""


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
        elif path.startswith("/c/"):
            body = CHAT_FORM
        elif path == "/fa":
            body = CHAT_FA
        elif path == "/cited":
            body = CITED
        elif path == "/to-login":
            status, extra = 302, "Location: /login\r\n"
        elif path == "/login":
            body = LOGIN
        elif path == "/broken":
            body = BROKEN
        elif path == "/revoked":
            body = REVOKED
        elif path == "/report":
            body = EXPORT
        elif path.startswith("/export/"):
            ctype, body = "application/zip", ZIP
            extra = 'Content-Disposition: attachment; filename="report-28d.zip"\r\n'
        elif path == "/api/answer":
            ctype, body = "text/plain; charset=utf-8", b"answer to: " + body_in[:40]
        elif path == "/upload":
            body = UPLOAD.replace(b"PORT", str(self.port).encode())
        elif path == "/up":
            ctype, body = "text/plain; charset=utf-8", str(len(body_in)).encode()
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


async def test_a_capture_takes_the_sites_file_without_a_download(world: Any) -> None:
    """⟨2026-11-18⟩ `capture`: the click's request to the named prefix is fetched by the profile
    browser (its own session, through the job's proxy), the body becomes the job's file under the
    site's own name, and the page gets an empty answer (no download starts); a prefix on another
    host is refused before anything is clicked."""
    import base64

    site, d, buckets, server, _ = world
    prefix = f"https://chat.test:{site.port}/export/"
    steps = [
        {"do": "goto", "url": "{start_url}"},
        {"do": "wait", "selector": "#csv", "timeout_s": 10},
        {"do": "capture", "selector": "[role=menuitem][aria-label='Download CSV']", "url": prefix,
         "timeout_s": 15},
    ]  # fmt: skip
    got = await d.job(_job(site, buckets, server, "/report", steps=steps))
    assert got["ok"] is True, got
    assert base64.b64decode(got["file"]["b64"]) == ZIP and got["file"]["name"] == "report-28d.zip"
    assert sum(1 for s in site.seen if s["path"].startswith("/export/")) == 1
    steps[-1] = {**steps[-1], "url": f"https://other.test:{site.port}/export/"}
    got = await d.job(_job(site, buckets, server, "/report", steps=steps))
    assert got["ok"] is False and "own hosts" in got["detail"]


async def test_a_revoked_blob_image_is_taken_from_its_pixels(world: Any) -> None:
    """⟨2026-11-15⟩ Gemini revokes the blob: URL of its picture once it is drawn; the step takes
    the picture from the element itself (a PNG at its natural size), not a failed fetch."""
    import base64
    import struct

    site, d, buckets, server, _ = world
    steps = [
        {"do": "goto", "url": "{start_url}"},
        {"do": "wait", "selector": "img.gen[data-ready='1']", "timeout_s": 10},
        {"do": "download_image", "selector": "img.gen", "attr": "src"},
    ]
    got = await d.job(_job(site, buckets, server, "/revoked", steps=steps))
    assert got["ok"] is True, got
    png = base64.b64decode(got["file"]["b64"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", png[16:24]) == (40, 30)  # the IHDR: its own full size


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


async def test_a_read_with_links_keeps_source_marks_as_markdown_links(world: Any) -> None:
    site, d, buckets, server, _ = world
    steps = [{"do": "goto", "url": "{start_url}"},
             {"do": "read", "selector": ".ds-markdown", "links": True}]  # fmt: skip
    got = await d.job(_job(site, buckets, server, "/cited", task="text", steps=steps))
    assert got["ok"] is True, got
    text = got["text_md"]
    assert "[1](https://src.test/cap)" in text
    assert "[12](https://src.test/two)" in text
    assert "[راهنمای کیف پول](https://src.test/guide)" in text
    assert "https://src.test/raw" in text and "[https://src.test/raw]" not in text
    assert "\n" in text  # the paragraphs keep their line breaks
    plain = [{"do": "goto", "url": "{start_url}"}, {"do": "read", "selector": ".ds-markdown"}]
    got = await d.job(_job(site, buckets, server, "/cited", task="text", steps=plain))
    assert "src.test/cap" not in got["text_md"]  # without `links` the old plain text


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
    assert seen["headless"] is True


# 2026-10-29: a headed profile browser runs its jobs in a window on its own
# Xvfb (started once, stopped with it); the sign-in window stays as it is.
async def test_a_headed_profile_browser_opens_windows_on_its_own_display(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hq_egress.browser_web as BW

    seen: list[dict[str, Any]] = []
    spawned: list[tuple[str, ...]] = []

    class Chromium:
        async def launch_persistent_context(self, user_data_dir: str, **kw: Any) -> object:
            seen.append(kw)
            return object()

    class PW:
        chromium = Chromium()

        async def start(self) -> PW:
            return self

        async def stop(self) -> None:
            pass

    class Proc:
        returncode: int | None = None

        def terminate(self) -> None:
            self.returncode = -15

        async def wait(self) -> int:
            return -15

    proc = Proc()

    async def spawn(*args: str, **_: Any) -> Proc:
        spawned.append(args)
        return proc

    monkeypatch.setenv("DISPLAY", "")  # restored after the test, whatever start() sets
    monkeypatch.delenv("DISPLAY")
    monkeypatch.setattr(BW.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(BW, "async_playwright", PW)
    d = Webd(profiles=tmp_path, headed=True)
    await d.start()
    assert spawned and spawned[0][:2] == ("Xvfb", BW.XVFB_DISPLAY)
    assert os.environ["DISPLAY"] == BW.XVFB_DISPLAY
    await d.open("chatgpt-web", Proxy(server="http://egress:3132"))
    await d.open("chatgpt-web", Proxy(server="http://egress:3132"), headless=True)
    assert [k["headless"] for k in seen] == [False, True]
    await d.stop()
    assert proc.returncode == -15


# A dead window's or job's Chromium lock is cleared once it is stale (20 min).
def test_a_stale_profile_lock_is_cleared_and_a_fresh_one_kept(tmp_path: Path) -> None:
    from hq_egress.browser_web import STALE_LOCK_S, clear_stale_lock, mark_open

    (tmp_path / "SingletonLock").symlink_to("deadhost-34")
    (tmp_path / "Default").mkdir()
    lstat_mtime = (tmp_path / "SingletonLock").lstat().st_mtime
    # another container's window, still open by its own mark: kept for now
    mark_open(tmp_path, 900, now=lstat_mtime)
    clear_stale_lock(tmp_path, now=lstat_mtime + 60, host="here")
    assert (tmp_path / "SingletonLock").is_symlink()
    clear_stale_lock(tmp_path, now=lstat_mtime + STALE_LOCK_S + 1, host="here")
    assert not (tmp_path / "SingletonLock").is_symlink() and (tmp_path / "Default").is_dir()


# ⟨2026-11-17⟩ The owner's sign-in window left SingletonLock, SingletonCookie and SingletonSocket
# pointing at its own dead container, and the next job failed with TargetClosedError: a lock of
# another host with no open mark, or of a process gone here, is stale at once.
def test_a_dead_hosts_or_dead_processes_lock_is_cleared_at_once(tmp_path: Path) -> None:
    import os

    from hq_egress.browser_web import OPEN_MARK, clear_stale_lock, mark_open, unmark_open

    def lock(target: str) -> None:
        for name, to in (
            ("SingletonLock", target),
            ("SingletonCookie", "123"),
            ("SingletonSocket", "/tmp/.org.chromium.Chromium.x/SingletonSocket"),
        ):
            (tmp_path / name).symlink_to(to)  # fmt: skip

    def left() -> list[str]:
        return sorted(p.name for p in tmp_path.glob("Singleton*"))

    lock("b733aced772e-41")  # the sign-in container, gone: no open mark
    clear_stale_lock(tmp_path, host="here")
    assert left() == []
    lock("b733aced772e-41")  # its mark ran out
    mark_open(tmp_path, 60, now=1000.0)
    clear_stale_lock(tmp_path, now=2000.0, host="here")
    assert left() == []
    lock("b733aced772e-41")  # a window open right now in the other container: kept
    mark_open(tmp_path, 900)
    clear_stale_lock(tmp_path, host="here")
    assert left() == ["SingletonCookie", "SingletonLock", "SingletonSocket"]
    unmark_open(tmp_path)
    assert not (tmp_path / OPEN_MARK).exists()
    for p in tmp_path.glob("Singleton*"):
        p.unlink()
    lock(f"here-{os.getpid()}")  # this container's own live Chromium: kept
    clear_stale_lock(tmp_path, host="here")
    assert len(left()) == 3
    for p in tmp_path.glob("Singleton*"):
        p.unlink()
    lock("here-999999999")  # this container's, its process gone
    clear_stale_lock(tmp_path, host="here")
    assert left() == []


def test_a_youtube_job_names_its_visibility_and_video(tmp_path: Path) -> None:
    """⟨2026-11-17⟩ `{visibility}` in a selector is the job's (PUBLIC or UNLISTED), `{video_id}` in
    a goto the uploaded video's; a job without them fails the step, never guesses."""
    from pydantic import ValidationError as PydanticValidationError

    from hq_egress.browser_web import JobIn, StepFailed, _fill, _selector

    base = {"account": "youtube-web", "recipe": {"start_url": "https://studio.youtube.com/"},
            "prompt": "t", "timeout_s": 60, "proxy": {"server": "http://egress:3132"}}  # fmt: skip
    j = JobIn.model_validate({**base, "visibility": "unlisted", "video_id": "abcDEF12_-x"})
    st = {"do": "click", "selector": "tp-yt-paper-radio-button[name='{visibility}']"}
    assert _selector(st, j) == "tp-yt-paper-radio-button[name='UNLISTED']"
    url = "https://studio.youtube.com/video/{video_id}/edit"
    assert _fill(url, j) == "https://studio.youtube.com/video/abcDEF12_-x/edit"
    bare = JobIn.model_validate(base)
    with pytest.raises(StepFailed):
        _selector(st, bare)
    with pytest.raises(StepFailed):
        _fill(url, bare)
    with pytest.raises(PydanticValidationError):
        JobIn.model_validate({**base, "visibility": "private"})


# 2026-10-29: a profile account may send a plain form on its own listed pages
# (the owner's chat with the site), and nowhere else.
async def test_a_profile_sends_its_chat_form_only_on_its_listed_pages(world: Any) -> None:
    site, d, buckets, server, _ = world

    def run(path: str, submit_on: list[str]) -> RunIn:
        key, secret = buckets.open("web.browse", "A0", 10_000_000, hosts=frozenset({"chat.test"}))
        return RunIn(
            profile="chatgpt-web",
            allowed_hosts=["chat.test"],
            steps=[
                {"do": "goto", "url": f"https://chat.test:{site.port}{path}"},
                {"do": "type", "target": "#prompt", "text": "hello"},
                {"do": "click", "target": "#send"},
                {"do": "wait", "target": ".answer"},
                {"do": "read"},
            ],
            proxy={"server": server, "username": key, "password": secret},
            account={
                "key": "chatgpt-web",
                "site": "chat.test",
                "browse": {"kind": "profile"},
                "allow": [{"methods": ["POST"], "path_prefix": "/api/"}],
                "submit_on": submit_on,
            },
            time_s=10,
        )

    for path, submit_on in (("/c/one", []), ("/c/two", ["/c/one"])):
        got = await d.run(run(path, submit_on))
        assert got["blocked"] == {"step": 2, "code": "needs_owner", "reason": "form_submit"}, got
    assert not [s for s in site.seen if s["path"] == "/api/answer"]
    got = await d.run(run("/c/one", ["/c/one"]))
    assert got["blocked"] is None and "answer to: hello" in got["steps"][4]["text"], got


def _chatgpt_text_steps() -> list[dict[str, Any]]:
    """The reviewed chatgpt-web text task as it is in the repository (shorter
    waits: the fake page answers at once)."""
    from hq_egress import recipes as RC

    recipes = Path(os.environ.get("HQ_EGRESS_RECIPES", "/recipes"))
    if not recipes.is_dir():
        pytest.skip("the recipes are mounted by browser-test.sh (HQ_EGRESS_RECIPES)")
    steps = [
        s.model_dump(exclude_none=True) for s in RC.load(recipes)["chatgpt-web"].tasks["text"].steps
    ]
    for s in steps:
        if "timeout_s" in s:
            s["timeout_s"] = min(float(s["timeout_s"]), 10)
    return steps


async def test_chatgpts_real_text_task_reads_the_answer_on_a_persian_page(world: Any) -> None:
    """⟨20.1⟩ the reviewed chatgpt-web text task on a page with Persian labels
    only: sent with Enter, read by structure, never the user's own words."""
    site, d, buckets, server, _ = world
    steps = _chatgpt_text_steps()
    got = await d.job(_job(site, buckets, server, "/fa", task="text", steps=steps))
    assert got["ok"] is True, got
    assert got["text_md"].strip().startswith("answer to: a calm sea"), got
    assert "شما گفتید" not in got["text_md"] and "ChatGPT" not in got["text_md"]


# ⟨2026-11-18⟩ a big upload runs without request interception: the proxy's credential stays in a
# loopback relay (never in Chrome, so Playwright never turns Chrome's Fetch domain on) and the egress
# proxy alone keeps the job to its own hosts. With interception an upload's body is copied into
# Chrome's browser process (YouTube's 710 MB long video killed it at browser-web's memory cap).
async def test_the_relay_adds_the_jobs_credential_to_connect_only() -> None:
    heads: list[bytes] = []

    async def upstream(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        heads.append(await r.readuntil(b"\r\n\r\n"))
        w.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        while data := await r.read(1024):
            w.write(data[::-1])
            await w.drain()
        w.close()

    up = await asyncio.start_server(upstream, "127.0.0.1", 0)
    relay = ProxyRelay(Proxy(server=f"http://127.0.0.1:{up.sockets[0].getsockname()[1]}",
                             username="job-key", password="s3cret"))  # fmt: skip
    url = await relay.start()
    host, port = url.removeprefix("http://").split(":")
    try:
        r, w = await asyncio.open_connection(host, int(port))
        w.write(
            b"CONNECT chat.test:443 HTTP/1.1\r\nHost: chat.test:443\r\nProxy-Authorization: Basic x\r\n\r\n"
        )
        assert (await r.readuntil(b"\r\n\r\n")).startswith(b"HTTP/1.1 200")
        w.write(b"ping")
        assert await r.readexactly(4) == b"gnip"
        w.close()
        head = heads[0].decode()
        assert (
            head.startswith("CONNECT chat.test:443 HTTP/1.1\r\n") and "Host: chat.test:443" in head
        )
        auths = [ln for ln in head.split("\r\n") if ln.lower().startswith("proxy-authorization:")]
        assert auths == ["Proxy-Authorization: Basic am9iLWtleTpzM2NyZXQ="]  # job-key:s3cret, once
        r, w = await asyncio.open_connection(host, int(port))
        w.write(b"GET http://chat.test/ HTTP/1.1\r\nHost: chat.test\r\n\r\n")
        assert (await r.readuntil(b"\r\n\r\n")).startswith(b"HTTP/1.1 405")
        assert len(heads) == 1  # never reached the egress proxy
    finally:
        await relay.stop()
        up.close()
    with pytest.raises(OSError):
        await asyncio.open_connection(host, int(port))
    with pytest.raises(ValueError):
        ProxyRelay(Proxy(server="http://egress:3132"))  # no credential: nothing to relay


def _chrome_anon_mib() -> int:
    """Chrome's browser process (no --type=): its anonymous memory now, in MiB."""
    top = 0
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            if b"chrom" not in cmd[0] or any(a.startswith(b"--type=") for a in cmd):
                continue
            for ln in Path(f"/proc/{pid}/status").read_text().splitlines():
                if ln.startswith("RssAnon:"):
                    top = max(top, int(ln.split()[1]) // 1024)
        except OSError:
            continue
    return top


def _upload_job(site: Site, buckets: Buckets, server: str, data: bytes, intercept: bool) -> JobIn:
    import base64

    j = _job(site, buckets, server, "/upload", task="upload_long", steps=[
        {"do": "goto", "url": "{start_url}"},
        {"do": "attach", "selector": "#f", "file": 0, "timeout_s": 20},
        {"do": "click", "selector": "#go"},
        {"do": "wait", "selector": "#done:has-text('sent')", "timeout_s": 25 if not intercept else 10},
        {"do": "read", "selector": "#done"},
    ])  # fmt: skip
    j.recipe["intercept"] = intercept
    j.files = [{"name": "video.mp4", "b64": base64.b64encode(data).decode()}]
    j.max_file_bytes = len(data) + 1
    return j


async def test_a_quiet_upload_is_never_copied_into_the_browser(
    world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    site, d, buckets, server, profiles = world
    monkeypatch.setattr("hq_egress.browser_web.SPOOL", profiles / ".spool")  # (a file over 16 MB)
    data = os.urandom(32 * 1024 * 1024)
    seen: list[Proxy] = []
    real = d.open

    async def spy(account: str, proxy: Proxy, **kw: Any) -> Any:
        seen.append(proxy)
        return await real(account, proxy, **kw)

    d.open = spy  # type: ignore[method-assign]
    peaks: dict[bool, int] = {}
    results: dict[bool, dict[str, Any]] = {}
    for intercept in (True, False):
        peak = 0
        job = asyncio.create_task(d.job(_upload_job(site, buckets, server, data, intercept)))
        while not job.done():
            peak = max(peak, _chrome_anon_mib())
            await asyncio.sleep(0.05)
        peaks[intercept], results[intercept] = peak, job.result()
    # intercepted (the job as before), the body piles up in Chrome's browser process and the upload
    # stalls (10 s are not enough for 32 MB); quiet, it goes out at once and Chrome stays small
    got = results[False]
    assert got["ok"] is True and got["text_md"].strip() == f"sent {len(data)}", (peaks, got)
    assert peaks[False] < 100 and peaks[True] > 2 * peaks[False] + 100, peaks
    # the quiet browser held no credential (so no Fetch domain): the relay on loopback had it
    assert seen[0].username and seen[1].username is None
    assert seen[1].server.startswith("http://127.0.0.1:") and seen[1].server != server
    # the egress proxy alone still refuses a host outside the job's own (the page's other.test image)
    assert not [s for s in site.seen if s["host"] == "other.test"]


async def test_a_dead_page_says_so_instead_of_a_bare_error(world: Any) -> None:
    site, d, buckets, server, _ = world
    j = _job(site, buckets, server, "/chat")
    ctx = await d.open("chatgpt-web", j.proxy, hold_s=30)
    try:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.close()
        got = await run_recipe(page, ctx, j, frozenset({"chat.test"}))
    finally:
        await d.close(ctx, "chatgpt-web")
    assert (got["ok"], got["error"], got["step"]) == (False, "recipe_failed", "0:goto"), got
    assert "the page crashed or the browser was closed" in got["detail"], got
    assert "Error: " in got["detail"] and "screenshot" not in got


# ⟨2026-11-21⟩ The owner's sign-in window (another container) holds the profile with a live open
# mark: a job answers «busy» and never opens the same profile beside it (two Chromiums on one
# profile broke youtube-bj, and Google dropped the owner's fresh sign-in).
def test_a_profile_held_by_the_sign_in_window_is_busy(tmp_path: Path) -> None:
    from hq_egress.browser_web import held_elsewhere, mark_open, unmark_open

    assert not held_elsewhere(tmp_path, now=1000.0, host="here")  # no lock at all
    (tmp_path / "SingletonLock").symlink_to("signinbox-77")
    assert not held_elsewhere(tmp_path, now=1000.0, host="here")  # no open mark: a dead window
    mark_open(tmp_path, 900, now=1000.0)
    assert held_elsewhere(tmp_path, now=1500.0, host="here")
    assert not held_elsewhere(tmp_path, now=2000.0, host="here")  # its mark ran out
    assert not held_elsewhere(tmp_path, now=1500.0, host="signinbox")  # our own lock
    unmark_open(tmp_path)
    assert not held_elsewhere(tmp_path, now=1500.0, host="here")


async def test_a_job_on_a_profile_held_by_the_sign_in_window_is_busy(tmp_path: Path) -> None:
    from hq_egress.browser_web import JobIn, Webd, mark_open

    d = Webd(profiles=tmp_path)
    prof = d.profile_dir("youtube-bj")
    (prof / "SingletonLock").symlink_to("signinbox-77")
    mark_open(prof, 900)
    j = JobIn.model_validate(
        {"account": "youtube-bj", "recipe": {"hosts": ["youtube.com"], "steps": []},
         "prompt": "x", "timeout_s": 30, "proxy": {"server": "http://egress:3133"}}
    )  # fmt: skip
    got = await d.job(j)
    assert got["ok"] is False and got["error"] == "busy"


# ⟨2026-11-21⟩ youtube-bj runs in youtube-web's profile (dotcoin.me, an editor of the channel): the
# same directory and the SAME lock (never two Chromiums on one profile), and its logout never wipes it.
async def test_an_account_sharing_a_profile_shares_its_lock_and_never_wipes_it(
    tmp_path: Path,
) -> None:
    from hq_egress.browser_web import PROFILE_OF, Webd

    assert PROFILE_OF == {"youtube-bj": "youtube-web"}
    d = Webd(profiles=tmp_path)
    assert d.profile_dir("youtube-bj") == d.profile_dir("youtube-web") == tmp_path / "youtube-web"
    assert d.locks["youtube-bj"] is d.locks["youtube-web"]
    assert d.locks["chatgpt-web"] is not d.locks["youtube-web"]
    (tmp_path / "youtube-web" / "Cookies").write_text("signed in")
    got = await d.logout("youtube-bj")
    assert got["ok"] is False and (tmp_path / "youtube-web" / "Cookies").is_file()
    async with d.locks["youtube-web"]:
        j_busy = d.locks["youtube-bj"].locked()
    assert j_busy
