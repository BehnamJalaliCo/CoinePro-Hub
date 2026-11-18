"""`python -m hq_egress.browser_web`: the profile browser (prompt 12 §9.1.5,
contract §21.13), opt-in profile `substitutes-web`, on hq-browser-web where
egress is its only peer.

The substitute players' signed-in browser profiles live here and nowhere
else: one persistent Chromium profile per account (chatgpt-web, gemini-web,
deepseek-web) in the volume only this service (and the owner's sign-in window,
`make <x>-web-login`) mounts; every file of it is 600 (umask 077) and it is
not in the backups. No model ever sees its cookies: a job returns the text
read from the page or the original file it downloads, nothing else.

    POST /v1/job     {account, recipe, prompt, timeout_s, proxy, max_file_bytes}
                     one reviewed recipe (hq_egress.recipes) in that profile
    POST /v1/run     web.browse's steps in a profile (the Claude fallback;
                     hq_egress.browser's rules, and only the recipe's hosts)
    POST /v1/logout  {account}: the profile wiped
    python -m hq_egress.browser_web login <account>
                     the owner's sign-in window (a visible browser on the
                     login image's display, at most 15 minutes)

One job per account at a time. The profile is opened for a job and closed
after it (no Chromium waits between jobs). A login page is `expired`: never
an automatic sign-in. A request to a host outside the recipe's own hosts is
aborted here, and egress's listener refuses it again.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
import re
import shutil
import socket
import stat
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urljoin, urlsplit

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from playwright.async_api import BrowserContext, Error, Page, Request, Route, async_playwright
from playwright.async_api import TimeoutError as PwTimeout
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from hq_common import heartbeat, logs
from hq_egress import browser as B
from hq_egress.hosts import covered

log = logging.getLogger("hq_egress.browser_web")
ACCOUNTS = (
    "chatgpt-web",
    "gemini-web",
    "deepseek-web",
    "aistudio-web",
    "pinterest-web",
    "youtube-web",
    "youtube-bj",
)
SANDBOX = os.environ.get("BROWSER_SANDBOX", "1") != "0"
# 2026-10-29 (the owner): jobs in a real window on the image's Xvfb, as the
# owner's sign-in window, not the headless shell the sites' bot check turns
# away (chatgpt.com's Cloudflare check never passed headless).
HEADED = os.environ.get("BROWSER_WEB_HEADED", "0") == "1"
XVFB_DISPLAY = ":99"
PROFILES = Path(os.environ.get("BROWSER_WEB_PROFILES", "/profiles"))
# ⟨2026-11-17⟩ a job's large attached file (an upload's video) while the page sends it
SPOOL = PROFILES / ".spool"
# ⟨2026-11-17⟩ a file the job names there (a long video and its thumbnail, put there before the job
# by the uploader): a plain name, never a path (substitutes_web.SPOOL_NAME)
SPOOL_NAME = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$"
# a read kept under a note (the answer's `notes`), at most
NOTE_CHARS = 4000
# `wait_sent`: the page has sent everything to a host once no request to it has been in flight
# for this long
SENT_QUIET_S = 15.0
LOGIN_S = 15 * 60
STEP_S = 30.0
# ⟨1.10.1⟩ a player's answer is read whole; this only stops a page gone wrong,
# and the answer then says it was cut (`[… cut at N characters]`)
READ_CHARS = 5_000_000
# ⟨2026-11-17⟩ a `read` with `links`: the answer's text with each http(s) link kept as markdown.
# A source mark (a link whose text is only a number, as DeepSeek's citations) becomes [n](url).
# The copy is laid out off screen so innerText keeps the answer's line breaks.
LINKS_JS = r"""(el) => {
  const c = el.cloneNode(true);
  for (const a of [...c.querySelectorAll('a[href]')]) {
    const href = a.href;
    if (!/^https?:/i.test(href)) continue;
    const t = (a.textContent || '').replace(/\s+/g, ' ').trim();
    let md;
    if (a.querySelector('[class*=cite]') || /^[\s\-\u2013]*\[?\d{1,3}\]?$/.test(t)) {
      md = ' [' + ((t.match(/\d{1,3}/) || ['\u2197'])[0]) + '](' + href + ')';
    } else if (!t || t === href) {
      md = href;
    } else {
      md = '[' + t.replace(/[\[\]]/g, '') + '](' + href + ')';
    }
    a.replaceWith(document.createTextNode(md));
  }
  const w = (el.clientWidth || 800) + 'px';
  c.style.cssText = 'position:absolute;left:-100000px;top:0;width:' + w;
  document.body.appendChild(c);
  const text = c.innerText;
  c.remove();
  return text;
}"""
# Where the owner's sign-in window opens (their own pages; nothing else).
LOGIN_PAGES = {
    "chatgpt-web": "https://chatgpt.com/",
    "gemini-web": "https://gemini.google.com/app",
    "deepseek-web": "https://chat.deepseek.com/",
    # prompt 22: AI Studio (the owner's Google account; speech) and Pinterest (read only)
    "aistudio-web": "https://aistudio.google.com/",
    "pinterest-web": "https://www.pinterest.com/",
    # ⟨2026-11-17⟩ YouTube Studio (the owner's Google account: DotCoin.me's Shorts)
    "youtube-web": "https://studio.youtube.com/",
    # ⟨2026-11-18⟩ @behnamjalali-tech's Studio (its own Google account, never youtube-web's)
    "youtube-bj": "https://studio.youtube.com/",
}
Account = Literal[
    "chatgpt-web",
    "gemini-web",
    "deepseek-web",
    "aistudio-web",
    "pinterest-web",
    "youtube-web",
    "youtube-bj",
]
B64_JS = """async (u) => {
  const r = await fetch(u);
  const b = new Uint8Array(await r.arrayBuffer());
  let s = '';
  for (let i = 0; i < b.length; i += 32768) s += String.fromCharCode(...b.subarray(i, i + 32768));
  return btoa(s);
}"""
# ⟨2026-11-15⟩ The picture an <img> shows, from its own pixels at its natural size, as a PNG: Gemini
# revokes the image's blob: URL once it is drawn, so fetching the URL fails (the page's own
# blob, so the canvas is never tainted).
PIXELS_JS = """async (img) => {
  if (!img.complete || !img.naturalWidth) await img.decode();
  const c = document.createElement('canvas');
  c.width = img.naturalWidth; c.height = img.naturalHeight;
  c.getContext('2d').drawImage(img, 0, 0);
  const blob = await new Promise((ok, no) =>
    c.toBlob(x => (x ? ok(x) : no(new Error('no pixels'))), 'image/png'));
  const b = new Uint8Array(await blob.arrayBuffer());
  let s = '';
  for (let i = 0; i < b.length; i += 32768) s += String.fromCharCode(...b.subarray(i, i + 32768));
  return btoa(s);
}"""


class Proxy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server: str
    username: str | None = None
    password: str | None = None


class JobIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account: Account
    recipe: dict[str, Any]
    prompt: str = Field(min_length=1, max_length=200_000)  # substitutes_web.PROMPT_CHARS
    timeout_s: float = Field(gt=0, le=1800)  # (⟨2026-11-17⟩ a set of slides: up to 25 min)
    proxy: Proxy
    max_file_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    # ⟨1.10⟩ §28.4 the hub's one retry: the page reloaded after the first goto
    reload: bool = False
    # prompt 22: the speaker and style of a tts job, how many results a search takes, the
    # files a cover is made from (hq_egress.substitutes_web.WebIn)
    voice: str | None = None
    style: str | None = None
    limit: int = Field(default=10, ge=1, le=30)
    files: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    # ⟨2026-11-17⟩ an upload's description (YouTube; the title is the prompt), its visibility (a
    # selector's `{visibility}`: PUBLIC or UNLISTED) and an uploaded video's id (`{video_id}` in
    # a goto's url)
    description: str | None = Field(default=None, max_length=5000)
    visibility: Literal["public", "unlisted"] | None = None
    video_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{11}$")
    # ⟨2026-11-17⟩ a long video's job: its files by name in this account's spool (after `files` in
    # the job's file order; the job's end removes them) and its tags (a fill's `{tags}`)
    spooled: list[Annotated[str, StringConstraints(pattern=SPOOL_NAME)]] = Field(
        default_factory=list, max_length=10
    )
    tags: str | None = Field(default=None, max_length=500)


class RunIn(B.RunIn):
    profile: Account
    allowed_hosts: list[str] = Field(min_length=1, max_length=30)


class LogoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account: Account


class StepFailed(Exception):
    def __init__(self, step: str, detail: str) -> None:
        super().__init__(detail)
        self.step = step
        self.detail = detail


def fail(error: str, detail: str, step: str | None = None) -> dict[str, Any]:
    return {"ok": False, "error": error, "detail": detail[:300], "step": step}


STALE_LOCK_S = 20 * 60
# ⟨2026-11-17⟩ until when the profile is open (epoch seconds), written by whoever opens it (a job
# here, the owner's sign-in window in its own container): another container's lock is live only
# while this says so
OPEN_MARK = ".hq-open-until"


def _lock_owner(profile: Path) -> tuple[str, int] | None:
    """Chromium's SingletonLock names its holder `<hostname>-<pid>`; None when there is none."""
    try:
        target = os.readlink(profile / "SingletonLock")
    except OSError:
        return None
    host, _, pid = target.rpartition("-")
    return host, int(pid) if pid.isdigit() else 0


def _alive(pid: int) -> bool:
    """Whether a process of this container runs under `pid` (a zombie does not)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    with contextlib.suppress(OSError, IndexError):
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat.rsplit(")", 1)[1].split()[0] != "Z"
    return True


def _open_until(profile: Path) -> float:
    try:
        return float((profile / OPEN_MARK).read_text().strip())
    except (OSError, ValueError):
        return 0.0


def mark_open(profile: Path, seconds: float, now: float | None = None) -> None:
    now = time.time() if now is None else now
    with contextlib.suppress(OSError):
        (profile / OPEN_MARK).write_text(f"{now + seconds:.0f}")


def unmark_open(profile: Path) -> None:
    with contextlib.suppress(OSError):
        (profile / OPEN_MARK).unlink()


def clear_stale_lock(profile: Path, now: float | None = None, host: str | None = None) -> None:
    """A window or job that died leaves Chromium's Singleton* lock behind (it
    names the dead container), and Chromium then refuses the profile. The lock
    is stale, and removed before a launch: ⟨2026-11-17⟩ at once when another
    container holds it and no open mark of its own says it is still open (the
    owner's sign-in window left one pointing at its own dead hostname, and the
    next job failed with TargetClosedError), or when its process here is gone;
    in any case once it is older than 20 minutes (a job or a sign-in window
    lasts at most 15, a set of slides 25 under the account's own lock)."""
    now = time.time() if now is None else now
    host = socket.gethostname() if host is None else host
    owner = _lock_owner(profile)
    if owner is None:
        dead = False
    elif owner[0] == host:
        dead = not _alive(owner[1])
    else:
        dead = _open_until(profile) < now
    for p in profile.glob("Singleton*"):
        with contextlib.suppress(OSError):
            if dead or now - p.lstat().st_mtime > STALE_LOCK_S:
                p.unlink()


class Webd:
    def __init__(
        self,
        *,
        profiles: Path = PROFILES,
        sandbox: bool = SANDBOX,
        insecure_tls: bool = False,
        headed: bool = HEADED,
    ) -> None:
        """`insecure_tls`: tests only (their fake sites' own certificate)."""
        self.profiles = profiles
        self.sandbox = sandbox
        self.insecure_tls = insecure_tls
        self.headed = headed
        self.locks = {a: asyncio.Lock() for a in ACCOUNTS}
        self._pw: Any = None
        self._xvfb: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        os.umask(0o077)  # every file of every profile is 600
        if self.headed and not os.environ.get("DISPLAY"):
            self._xvfb = await asyncio.create_subprocess_exec(
                "Xvfb", XVFB_DISPLAY, "-screen", "0", "1280x900x24", "-nolisten", "tcp",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )  # fmt: skip
            os.environ["DISPLAY"] = XVFB_DISPLAY
        self._pw = await async_playwright().start()

    async def stop(self) -> None:
        if self._pw is not None:
            await self._pw.stop()
        if self._xvfb is not None and self._xvfb.returncode is None:
            self._xvfb.terminate()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._xvfb.wait(), 5)

    def ready(self) -> bool:
        return self._pw is not None

    def profile_dir(self, account: str) -> Path:
        if account not in ACCOUNTS:
            raise ValueError("unknown account")
        d = self.profiles / account
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
        return d

    async def open(
        self, account: str, proxy: Proxy, *, headless: bool | None = None, hold_s: float = LOGIN_S
    ) -> BrowserContext:
        """`headless`: None for a job's (headless unless `headed`). `hold_s`: how long the profile
        may stay open (its open mark; `close` removes it)."""
        profile = self.profile_dir(account)
        clear_stale_lock(profile)
        mark_open(profile, hold_s + 60)
        ctx: BrowserContext = await self._pw.chromium.launch_persistent_context(
            str(profile),
            headless=not self.headed if headless is None else headless,
            # 14.1 §1.5: no automation banner or flag the sites can see.
            ignore_default_args=["--enable-automation"],
            args=[*B.ARGS, "--disable-blink-features=AutomationControlled"],
            chromium_sandbox=self.sandbox,
            proxy=proxy.model_dump(exclude_none=True),
            accept_downloads=True,
            service_workers="block",
            viewport={"width": 1280, "height": 900},
            locale="fa-IR",
            ignore_https_errors=self.insecure_tls,
        )
        return ctx

    # ------------------------------------------------------------- a job --
    async def job(self, j: JobIn) -> dict[str, Any]:
        lock = self.locks[j.account]
        if lock.locked():
            return fail("busy", "one job per account at a time")
        async with lock:
            try:
                return await asyncio.wait_for(self._job(j), timeout=j.timeout_s + 5)
            except TimeoutError:
                return fail("timeout", "the job ran past its time")

    async def _job(self, j: JobIn) -> dict[str, Any]:
        hosts = frozenset(str(h).lower() for h in j.recipe.get("hosts") or [])
        if not hosts:
            return fail("recipe_failed", "a recipe without hosts")
        ctx = await self.open(j.account, j.proxy, hold_s=j.timeout_s)
        try:
            await ctx.route("**/*", _only(hosts))
            traffic = Traffic()
            traffic.watch(ctx)
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            return await run_recipe(page, ctx, j, hosts, traffic)
        finally:
            await self.close(ctx, j.account)
            shutil.rmtree(spool_dir(j.account), ignore_errors=True)

    async def close(self, ctx: BrowserContext, account: str) -> None:
        with contextlib.suppress(Error):
            await ctx.close()
        unmark_open(self.profiles / account)

    # -------------------------------------------------- a web.browse call --
    async def run(self, a: RunIn) -> dict[str, Any]:
        lock = self.locks[a.profile]
        if lock.locked():
            return {"code": "busy"}
        async with lock:
            hosts = frozenset(h.lower() for h in a.allowed_hosts)
            deadline = time.monotonic() + a.time_s
            ctx = await self.open(a.profile, Proxy(**a.proxy.model_dump()), hold_s=a.time_s)
            try:
                return await asyncio.wait_for(
                    B.steps_in(ctx, a, deadline, allowed=lambda h: covered(h, hosts)),
                    timeout=a.time_s + 3,
                )
            except TimeoutError:
                return {"steps": [], "error": "timeout"}
            finally:
                await self.close(ctx, a.profile)

    async def logout(self, account: str) -> dict[str, Any]:
        async with self.locks[account]:
            d = self.profile_dir(account)
            shutil.rmtree(d, ignore_errors=True)
            self.profile_dir(account)
        log.info("profile wiped", extra={"account": account})
        return {"ok": True}

    # --------------------------------------------- the owner's sign-in --
    async def login(self, account: str, proxy: Proxy, seconds: float = LOGIN_S) -> None:
        """A visible browser on the profile, for the owner to sign in; closed
        when the owner closes it, or after `seconds`. The hub never sees what
        the owner types."""
        ctx = await self.open(account, proxy, headless=False, hold_s=seconds)
        try:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            with contextlib.suppress(Error):
                await page.goto(LOGIN_PAGES[account], wait_until="domcontentloaded", timeout=60_000)
            closed: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

            def on_close(_c: Any) -> None:
                if not closed.done():
                    closed.set_result(True)

            ctx.on("close", on_close)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(closed, timeout=seconds)
        finally:
            await self.close(ctx, account)


class Traffic:
    """⟨2026-11-17⟩ A job's requests in flight, per host: an upload has ended once none to its host
    is in flight and none has started or ended for SENT_QUIET_S (`wait_sent`)."""

    def __init__(self) -> None:
        self.live: dict[Request, str] = {}
        self.seen: dict[str, int] = {}
        self.moved: dict[str, float] = {}

    def watch(self, ctx: BrowserContext) -> None:
        ctx.on("request", self.started)
        ctx.on("requestfinished", self.ended)
        ctx.on("requestfailed", self.ended)

    def started(self, req: Request) -> None:
        host = (urlsplit(req.url).hostname or "").lower()
        self.live[req] = host
        self.seen[host] = self.seen.get(host, 0) + 1
        self.moved[host] = time.monotonic()

    def ended(self, req: Request) -> None:
        host = self.live.pop(req, None)
        if host is not None:
            self.moved[host] = time.monotonic()

    def in_flight(self, host: str) -> int:
        return sum(1 for h in self.live.values() if h == host)

    async def sent(self, host: str, ms: float) -> str:
        """Until the page has sent everything to `host`; what it saw, as a short note. A host the
        page never reached has nothing to wait for (the note says so)."""
        start = time.monotonic()
        end = start + ms / 1000
        while True:
            if not self.seen.get(host):
                return f"no request to {host} seen"
            quiet = time.monotonic() - self.moved.get(host, 0.0)
            if self.in_flight(host) == 0 and quiet >= SENT_QUIET_S:
                return (
                    f"sent: {self.seen[host]} requests to {host}, quiet after "
                    f"{time.monotonic() - start:.0f} s"
                )
            if time.monotonic() >= end:
                raise StepFailed("wait_sent", f"still sending to {host}")
            await asyncio.sleep(1.0)


def _only(hosts: frozenset[str]) -> Any:
    """Abort every request outside the recipe's own hosts (data: and blob:
    never leave the page)."""

    async def handle(route: Route) -> None:
        url = route.request.url
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
        if url.startswith(("http:", "https:")) and not covered(host, hosts):
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    return handle


async def expired(page: Page, rule: dict[str, Any]) -> bool:
    """Whether the page is a login page (the profile is signed out or its
    session expired)."""
    url = page.url.lower()
    host = (urlsplit(url).hostname or "").lower()
    if any(str(x).lower() in url for x in rule.get("url_contains") or []):
        return True
    if host and any(host == str(h).lower() for h in rule.get("hosts") or []):
        return True
    for sel in rule.get("selectors") or []:
        with contextlib.suppress(Error):
            if await page.locator(str(sel)).first.is_visible():
                return True
    return False


def _fill(template: str | None, j: JobIn) -> str:
    url = (template or "").replace("{start_url}", str(j.recipe.get("start_url") or ""))
    if "{video_id}" in url:  # ⟨2026-11-17⟩ an uploaded video's own page (YouTube Studio)
        if not j.video_id:
            raise StepFailed("goto", "the job names no video")
        url = url.replace("{video_id}", j.video_id)
    return url


VOICE_NAME = re.compile(r"[A-Za-z][A-Za-z' -]{0,39}")


def _selector(st: dict[str, Any], j: JobIn) -> str:
    """⟨2026-11-13⟩ A step's selector, with `{voice}` and `{style}` as the job's own (AI Studio's
    2026-11 page picks a speaker card and a style preset by name). A voice is a plain name; each
    value is quoted for the CSS string it stands in. A selector that names an empty value fails
    the step (an `optional` one is skipped: no style, no preset)."""
    sel = str(st.get("selector") or "")
    visibility = j.visibility.upper() if j.visibility else None
    for key, value in (("{voice}", j.voice), ("{style}", j.style), ("{visibility}", visibility)):
        if key not in sel:
            continue
        v = (value or "").strip()
        if not v:
            raise StepFailed(str(st.get("do")), f"the job names no {key.strip('{}')}")
        if key == "{voice}" and not VOICE_NAME.fullmatch(v):
            raise StepFailed(str(st.get("do")), "the voice is not a plain name")
        sel = sel.replace(key, v.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"'))
    return sel


async def run_recipe(
    page: Page,
    ctx: BrowserContext,
    j: JobIn,
    hosts: frozenset[str],
    traffic: Traffic | None = None,
) -> dict[str, Any]:
    """The recipe's steps; the first failing one is `recipe_failed` with that
    step (or `expired` when the page is a login page). ⟨2026-11-17⟩ Beside its answer a job says
    which optional steps did not happen (`skipped`) and what its noted reads found (`notes`); a
    failed one also gives the text it had read so far (`partial`: an upload's link)."""
    rule = j.recipe.get("expired") or {}
    deadline = time.monotonic() + j.timeout_s
    text: str | None = None
    file: dict[str, Any] | None = None
    files: list[dict[str, Any]] = []  # ⟨2026-11-17⟩ a set of slides (download_images)
    notes: dict[str, str] = {}
    skipped: list[str] = []
    steps = j.recipe.get("steps") or []
    reloaded = False
    traffic = traffic or Traffic()

    def said(out: dict[str, Any]) -> dict[str, Any]:
        if notes:
            out["notes"] = notes
        if skipped:
            out["skipped"] = skipped
        if text and not out.get("ok"):
            out["partial"] = text[:300]
        return out

    for i, st in enumerate(steps):
        do = str(st.get("do"))
        tag = f"{i}:{do}"
        left = deadline - time.monotonic()
        if left <= 0:
            return said(fail("timeout", "the job ran past its time", tag))
        ms = min(float(st.get("timeout_s") or STEP_S), left) * 1000
        try:
            got = await _recipe_step(page, ctx, st, ms, j, hosts, traffic)
            if do == "goto" and j.reload and not reloaded:
                reloaded = True  # ⟨1.10⟩ the retry: a fresh load of the page
                await page.reload(wait_until="load", timeout=ms)
        except (PwTimeout, Error, StepFailed, ValueError) as exc:
            if await expired(page, rule):
                return said(fail("expired", "the profile shows a login page: sign in again", tag))
            if st.get("optional"):
                skipped.append(tag)
                continue
            why = exc.detail if isinstance(exc, StepFailed) else type(exc).__name__
            out = said(fail("recipe_failed", f"step {tag} failed: {why}", tag))
            shot = await screenshot(page)
            if shot is not None:
                out["screenshot"] = shot
            return out
        if do == "goto" and await expired(page, rule):
            return said(fail("expired", "the profile shows a login page: sign in again", tag))
        if isinstance(got, str) and st.get("note"):
            notes[str(st["note"])] = got[:NOTE_CHARS]
        elif isinstance(got, str):
            text = got
        elif isinstance(got, dict):
            file = got
        elif isinstance(got, list) and got:
            files, file = got, got[0]
    if text is None and file is None:
        return said(fail("recipe_failed", "the recipe read nothing", None))
    done: dict[str, Any] = {"ok": True, "text_md": text, "file": file}
    if files:
        done["files"] = files
    return said(done)


SCREENSHOT_BYTES = 2 * 1024 * 1024


async def screenshot(page: Page) -> dict[str, str] | None:
    """⟨1.10⟩ §28.4 the viewport as the failed step left it (JPEG), for the
    overseer and the SRE who fix the recipe; none when it cannot be taken
    or is over 2 MB. Never the full page, never a cookie."""
    try:
        data = await page.screenshot(type="jpeg", quality=60, full_page=False, timeout=5000)
    except (PwTimeout, Error):
        return None
    if not data or len(data) > SCREENSHOT_BYTES:
        return None
    return {"mime": "image/jpeg", "b64": base64.b64encode(data).decode()}


async def _recipe_step(
    page: Page,
    ctx: BrowserContext,
    st: dict[str, Any],
    ms: float,
    j: JobIn,
    hosts: frozenset[str],
    traffic: Traffic | None = None,
) -> str | dict[str, Any] | list[dict[str, Any]] | None:
    do = str(st.get("do"))
    sel = _selector(st, j)
    if do == "goto":
        url = _fill(st.get("url"), j)
        host = (urlsplit(url).hostname or "").lower()
        if not url.startswith("https://") or not covered(host, hosts):
            raise StepFailed(do, "not one of the site's own hosts")
        await page.goto(url, wait_until="domcontentloaded", timeout=ms)
    elif do == "wait":
        await page.locator(sel).first.wait_for(state=st.get("state") or "visible", timeout=ms)
    elif do == "wait_gone":
        await page.locator(sel).first.wait_for(state="hidden", timeout=ms)
    elif do == "click":
        await page.locator(sel).first.click(timeout=min(ms, 5000) if st.get("optional") else ms)
    elif do == "click_unless":
        if await page.locator(str(st.get("unless"))).count() == 0:
            await page.locator(sel).first.click(timeout=ms)
    elif do == "fill":
        given = {
            "{style}": j.style or "",
            "{voice}": j.voice or "",
            "{description}": j.description or "",
            "{tags}": j.tags or "",
        }
        value = given.get(str(st.get("text")), j.prompt)
        if st.get("text") == "{tags}" and not value:
            raise StepFailed(do, "the job names no tags")
        if st.get("typed"):  # ⟨2026-11-17⟩ key by key (a tag box makes a tag of each comma)
            box = page.locator(sel).first
            await box.click(timeout=min(ms, 10_000))
            await box.press_sequentially(value, delay=20, timeout=ms)
        else:
            await page.locator(sel).first.fill(value, timeout=ms)
    elif do == "select":
        await _select(page, sel, j.voice, ms)
    elif do == "attach":
        pick = st.get("file")
        await _attach(page, sel, j, ms, int(pick) if pick is not None else None)
    elif do == "wait_sent":
        url = str(st.get("url") or "")
        host = (urlsplit(url).hostname or "").lower()
        if not url.startswith("https://") or not covered(host, hosts):
            raise StepFailed(do, "not one of the site's own hosts")
        return await (traffic or Traffic()).sent(host, ms)
    elif do == "collect":
        return await _collect(page, sel, j.limit, ms)
    elif do == "press":
        await page.locator(sel).first.press(str(st.get("key")), timeout=ms)
    elif do == "pause":
        await page.wait_for_timeout(min(int(st.get("ms") or 1000), 5000))
    elif do == "read":
        loc, n = page.locator(sel), 0
        # ⟨20.1⟩ the selector, then each `alt` in turn: the first that matches
        for cand in [sel, *[str(a) for a in st.get("alt") or []]]:
            loc = page.locator(cand)
            n = await loc.count()
            if n:
                break
        if n == 0:
            raise StepFailed(do, "nothing to read")
        if st.get("links"):
            text = str(await loc.nth(n - 1).evaluate(LINKS_JS, timeout=ms))
        else:
            text = str(await loc.nth(n - 1).inner_text(timeout=ms))
        if len(text) > READ_CHARS:
            return text[:READ_CHARS] + f"\n[… cut at {READ_CHARS} characters]"
        return text
    elif do in ("download_image", "download_media"):
        return await _image(page, ctx, sel, str(st.get("attr") or "src"), ms, j, hosts)
    elif do == "download_images":
        return await _images(page, ctx, sel, str(st.get("attr") or "src"), ms, j, hosts)
    elif do == "more_images":
        await _more_images(page, sel, str(st.get("composer")), str(st.get("busy")), ms, j)
    elif do == "capture":
        return await _capture(page, ctx, sel, str(st.get("url") or ""), ms, j, hosts)
    elif do == "download":
        async with page.expect_download(timeout=ms) as info:
            await page.locator(sel).first.click(timeout=ms)
        dl = await info.value
        path = await dl.path()
        data = await asyncio.to_thread(lambda: Path(path).read_bytes()[: j.max_file_bytes + 1])
        return _file(data, dl.suggested_filename or "download", j)
    else:
        raise StepFailed(do, "unknown step")
    return None


async def _select(page: Page, sel: str, option: str | None, ms: float) -> None:
    """Choose `option` (the job's voice) in a control: a native <select> by its label, else a
    listbox opened by a click whose option is found by role and name (structure, not a language)."""
    if not option:
        raise StepFailed("select", "the job names no option")
    ctl = page.locator(sel).first
    tag = str(await ctl.evaluate("e => e.tagName.toLowerCase()", timeout=ms))
    if tag == "select":
        await ctl.select_option(label=option, timeout=ms)
        return
    await ctl.click(timeout=ms)
    await page.get_by_role("option", name=option, exact=False).first.click(timeout=ms)


ATTACH_GAP_MS = 2500  # between two files put one by one: the site takes each in
# ⟨2026-11-17⟩ a file over this (a Short's video) goes in from a file of its own on the profiles'
# volume, not from memory: Playwright refuses a buffer over 50 MB and would spool it to /tmp,
# which is a small tmpfs here
SPOOL_BYTES = 16 * 1024 * 1024


async def _attach(page: Page, sel: str, j: JobIn, ms: float, pick: int | None = None) -> None:
    """The job's files into a file input (decoded here; none outside the job). ⟨2026-11-17⟩ `pick`:
    only that one of the job's files (its carried files first, then its spooled ones); a spooled
    file goes in from its own path in this account's spool."""
    if not j.files and not j.spooled:
        raise StepFailed("attach", "the job carries no files")
    if pick is not None:
        if pick >= len(j.files) + len(j.spooled):
            raise StepFailed("attach", f"the job has no file {pick}")
        if pick >= len(j.files):
            path = spooled_path(j.account, j.spooled[pick - len(j.files)], j.max_file_bytes)
            await page.locator(sel).first.set_input_files(path, timeout=ms)
            return
        carried = [j.files[pick]]
    elif j.spooled:
        paths = [spooled_path(j.account, n, j.max_file_bytes) for n in j.spooled]
        if j.files or len(paths) > 1:
            raise StepFailed("attach", "a job with spooled files names which one each step takes")
        await page.locator(sel).first.set_input_files(paths[0], timeout=ms)
        return
    else:
        carried = j.files[:10]
    payload: list[dict[str, Any]] = []
    for f in carried:
        data = base64.b64decode(str(f.get("b64") or ""), validate=True)
        if len(data) > j.max_file_bytes:
            raise StepFailed("attach", "a file is over its cap")
        name = Path(str(f.get("name") or "file")).name[:120] or "file"
        payload.append({"name": name, "mimeType": _mime_of(name), "buffer": data})
    if len(payload) == 1 and len(payload[0]["buffer"]) > SPOOL_BYTES:
        # (the page reads the file while it uploads, after this step: the job's end removes it)
        path = await asyncio.to_thread(_spool, j.account, payload[0]["name"], payload[0]["buffer"])
        await page.locator(sel).first.set_input_files(path, timeout=ms)
        return
    if len(payload) == 1:
        await page.locator(sel).first.set_input_files(payload, timeout=ms)
        return
    # ⟨2026-11-16⟩ several files (DotCoin.me's cover: the owner's six reference photos): the
    # page's first file input takes ONE file (Playwright: "Non-multiple file input can only accept
    # single file"), so a multiple input is used when there is one, else the files go one by one
    # into the same input (the composer keeps each as its own attachment)
    multi = page.locator(f"{sel}[multiple]")
    if await multi.count():
        await multi.first.set_input_files(payload, timeout=ms)
        return
    for one in payload:
        await page.locator(sel).first.set_input_files([one], timeout=ms)
        await page.wait_for_timeout(ATTACH_GAP_MS)


def spool_dir(account: str) -> Path:
    """⟨2026-11-17⟩ Where a job's large file waits while the page uploads it: the profiles'
    volume (one job per account at a time; the job's end removes it)."""
    return SPOOL / account


def spooled_path(account: str, name: str, cap: int) -> str:
    """⟨2026-11-17⟩ The path of a file the job names in this account's spool: a plain name of that
    directory (never a path, a link or anything but a plain file), of 1 byte up to the job's cap."""
    if not re.fullmatch(SPOOL_NAME, name):
        raise StepFailed("attach", "not a spooled file's name")
    base = spool_dir(account)
    path = base / name
    try:
        st = path.lstat()
    except OSError:
        raise StepFailed("attach", "a spooled file is missing") from None
    if not stat.S_ISREG(st.st_mode) or path.resolve().parent != base.resolve():
        raise StepFailed("attach", "a spooled file is not a plain file of the spool")
    if not 0 < st.st_size <= cap:
        raise StepFailed("attach", "a spooled file is empty or over its cap")
    return str(path)


def _spool(account: str, name: str, data: bytes) -> str:
    d = spool_dir(account)
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = d / name
    path.write_bytes(data)
    return str(path)


def _mime_of(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
        "gif": "image/gif", "mp4": "video/mp4", "txt": "text/plain", "pdf": "application/pdf",
    }.get(ext, "application/octet-stream")  # fmt: skip


COLLECT_JS = """(els, n) => els.slice(0, n).map(e => {
  const a = e.matches('a') ? e : e.querySelector('a');
  const img = e.matches('img') ? e : e.querySelector('img');
  const best = (img && (img.currentSrc || img.src)) || '';
  const title = (img && img.alt) || e.innerText.trim().slice(0, 200);
  return {image: best, link: a ? a.href : '', title};
})"""


async def _collect(page: Page, sel: str, limit: int, ms: float) -> str:
    """Up to `limit` items (pins): the image URL, the link and the title, as JSON text. Nothing
    is clicked or posted: a read."""
    import json

    await page.locator(sel).first.wait_for(state="visible", timeout=ms)
    items = await page.locator(sel).evaluate_all(COLLECT_JS, limit)
    rows = [i for i in items if i.get("image") or i.get("link")]
    if not rows:
        raise StepFailed("collect", "no items on the page")
    return json.dumps(rows, ensure_ascii=False)


async def _image(
    page: Page,
    ctx: BrowserContext,
    sel: str,
    attr: str,
    ms: float,
    j: JobIn,
    hosts: frozenset[str],
) -> dict[str, Any]:
    """The original of the last matching image: its data, its blob, or its
    URL on the site's own hosts (fetched with the profile's own session)."""
    loc = page.locator(sel)
    n = await loc.count()
    if n == 0:
        raise StepFailed("download_image", "no image")
    el = loc.nth(n - 1)
    src = await el.get_attribute(attr, timeout=ms)
    if not src:
        raise StepFailed("download_image", "the image has no source")
    data = await _fetch(page, ctx, el, src, ms, hosts, "download_image")
    return _file(data[: j.max_file_bytes + 1], src.rsplit("/", 1)[-1][:60] or "image", j)


# ⟨2026-11-17⟩ the made pictures of a chat, in order: each source once (the site shows a twin of
# the same blob), never a picture of the asker's own message (the files a job attached)
MADE_JS = """(els, attr) => {
  const seen = new Set(), out = [];
  els.forEach((e, i) => {
    if (e.closest('[data-message-author-role="user"]')) return;
    const src = e.getAttribute(attr) || '';
    if (!src || seen.has(src)) return;
    seen.add(src);
    out.push(i);
  });
  return out;
}"""
MAX_IMAGES = 15  # (recipes.MAX_IMAGES)
EXT = ((b"\x89PNG", "png"), (b"\xff\xd8\xff", "jpg"), (b"RIFF", "webp"))


async def _images(
    page: Page,
    ctx: BrowserContext,
    sel: str,
    attr: str,
    ms: float,
    j: JobIn,
    hosts: frozenset[str],
) -> list[dict[str, Any]]:
    """⟨2026-11-17⟩ Every picture the answer made, in the order shown (at most MAX_IMAGES), named
    slide_01, slide_02 … (the owner: ChatGPT designs a day's story slides in one chat)."""
    loc = page.locator(sel)
    picked = list(await loc.evaluate_all(MADE_JS, attr))[:MAX_IMAGES]
    if not picked:
        raise StepFailed("download_images", "no image")
    out = []
    for k, i in enumerate(picked, 1):
        el = loc.nth(int(i))
        src = await el.get_attribute(attr, timeout=ms)
        if not src:
            raise StepFailed("download_images", "an image has no source")
        data = await _fetch(page, ctx, el, src, ms, hosts, "download_images")
        ext = next((e for magic, e in EXT if data.startswith(magic)), "png")
        out.append(_file(data[: j.max_file_bytes + 1], f"slide_{k:02d}.{ext}", j))
    return out


NEXT_SLIDE = (
    "Continue the same set now: make slide {k} of {n} as its own separate image (one image only, "
    "the same series and style, the exact Persian text given for slide {k}). Do not ask anything."
)


async def _more_images(page: Page, sel: str, composer: str, busy: str, ms: float, j: JobIn) -> None:
    """⟨2026-11-17⟩ ChatGPT may end its answer after fewer pictures than the set asks for (a first
    real run: one sheet for twelve slides). While the chat holds fewer made pictures than the job's
    `limit`, the next slide is asked for in the same chat, once per missing slide at most, within
    the step's time (the time left for the download is kept)."""
    want = min(int(j.limit or 1), MAX_IMAGES)
    end = time.monotonic() + ms / 1000 - 60
    for _ in range(want):
        have = len(await page.locator(sel).evaluate_all(MADE_JS, "src"))
        left = end - time.monotonic()
        if have >= want or left <= 30:
            return
        box = page.locator(composer).first
        await box.fill(NEXT_SLIDE.format(k=have + 1, n=want), timeout=30_000)
        await box.press("Enter", timeout=10_000)
        with contextlib.suppress(PwTimeout):
            await page.locator(busy).first.wait_for(state="visible", timeout=20_000)
        wait_s = max(1.0, end - time.monotonic())
        await page.locator(busy).first.wait_for(state="hidden", timeout=wait_s * 1000)
        await page.wait_for_timeout(3000)


async def _fetch(
    page: Page,
    ctx: BrowserContext,
    el: Any,
    src: str,
    ms: float,
    hosts: frozenset[str],
    step: str,
) -> bytes:
    """One picture's bytes: its data URL, its blob (or, a revoked blob, the shown picture
    itself), or its URL on the site's own hosts with the profile's own session."""
    if src.startswith("data:"):
        _, _, b64 = src.partition(",")
        return base64.b64decode(b64)
    if src.startswith("blob:"):
        try:
            return base64.b64decode(await page.evaluate(B64_JS, src))
        except Error:
            # the blob is revoked (Gemini): the shown picture itself, from its element
            return base64.b64decode(await el.evaluate(PIXELS_JS, timeout=ms))
    url = src if "://" in src else urljoin(page.url, src)
    host = (urlsplit(url).hostname or "").lower()
    if not url.startswith("https://") or not covered(host, hosts):
        raise StepFailed(step, "not one of the site's own hosts")
    resp = await ctx.request.get(url, timeout=ms, max_redirects=0)
    try:
        body: bytes = await resp.body()
        return body
    finally:
        await resp.dispose()


DISPOSITION_NAME = re.compile(r"filename\*?=(?:UTF-8'')?\"?([^\";]{1,120})", re.I)


async def _capture(
    page: Page, ctx: BrowserContext, sel: str, prefix: str, ms: float, j: JobIn,
    hosts: frozenset[str],
) -> dict[str, Any]:  # fmt: skip
    """⟨2026-11-18⟩ A file a site sends as a download (Search Console's CSV export): click `sel`;
    the first request whose URL starts with `prefix` (on the recipe's own hosts) is made by the
    profile browser itself (its own session, through the job's proxy) and its body kept as the
    job's file, while the page is answered with an empty 204, so no download ever starts
    (Chromium's download path ends the profile browser with SIGTRAP here: seen 2026-11-18)."""
    host = (urlsplit(prefix).hostname or "").lower()
    if not prefix.startswith("https://") or not covered(host, hosts):
        raise StepFailed("capture", "not one of the site's own hosts")
    got: asyncio.Future[tuple[int, bytes, str]] = asyncio.get_running_loop().create_future()

    def match(url: str) -> bool:
        return url.startswith(prefix)

    async def grab(route: Route) -> None:
        if not got.done():
            try:
                resp = await route.fetch(timeout=ms, max_redirects=0)
                body = await resp.body()
                got.set_result((resp.status, body, resp.headers.get("content-disposition") or ""))
            except Error as exc:
                got.set_exception(StepFailed("capture", type(exc).__name__))
        await route.fulfill(status=204, body=b"")

    await ctx.route(match, grab)
    try:
        await page.locator(sel).first.click(timeout=ms)
        status, body, disposition = await asyncio.wait_for(got, timeout=ms / 1000)
    except TimeoutError:
        raise StepFailed("capture", "the site sent nothing") from None
    finally:
        await ctx.unroute(match, grab)
    if status != 200 or not body:
        raise StepFailed("capture", f"the site answered {status}")
    m = DISPOSITION_NAME.search(disposition)
    return _file(body[: j.max_file_bytes + 1], (m.group(1) if m else "export").strip(), j)


def _file(data: bytes, name: str, j: JobIn) -> dict[str, Any]:
    if len(data) > j.max_file_bytes:
        raise StepFailed("download", "the file is over its cap")
    return {"name": name[:120], "b64": base64.b64encode(data).decode()}


def build_app(d: Webd) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await d.start()

        async def check() -> dict[str, Any]:
            return {"ok": d.ready()}

        beat = asyncio.create_task(heartbeat.run(check))
        try:
            yield
        finally:
            beat.cancel()
            await d.stop()

    app = FastAPI(
        title="browser-web", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )

    @app.post("/v1/job")
    async def job(j: JobIn) -> JSONResponse:
        return JSONResponse(await d.job(j))

    @app.post("/v1/run")
    async def run(a: RunIn) -> JSONResponse:
        got = await d.run(a)
        return JSONResponse(got, status_code=503 if got.get("code") == "busy" else 200)

    @app.post("/v1/logout")
    async def logout(a: LogoutIn) -> JSONResponse:
        return JSONResponse(await d.logout(a.account))

    return app


async def _login(account: str) -> int:
    d = Webd(profiles=PROFILES)
    await d.start()
    try:
        server = os.environ.get("BROWSER_WEB_LOGIN_PROXY", "http://egress:3133")
        await d.login(account, Proxy(server=server))
    finally:
        await d.stop()
    return 0


def main(argv: list[str]) -> int:
    logs.setup("browser-web", os.environ.get("LOG_LEVEL", "info"))
    if len(argv) >= 2 and argv[1] == "login":
        if len(argv) != 3 or argv[2] not in ACCOUNTS:
            print(
                f"usage: python -m hq_egress.browser_web login {'|'.join(ACCOUNTS)}",
                file=sys.stderr,
            )
            return 2
        return asyncio.run(_login(argv[2]))
    uvicorn.run(
        build_app(Webd()),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8096")),
        log_config=None,
        access_log=False,
        server_header=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
