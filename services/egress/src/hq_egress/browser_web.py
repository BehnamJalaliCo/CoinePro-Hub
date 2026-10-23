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
import shutil
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from playwright.async_api import BrowserContext, Error, Page, Route, async_playwright
from playwright.async_api import TimeoutError as PwTimeout
from pydantic import BaseModel, ConfigDict, Field

from hq_common import heartbeat, logs
from hq_egress import browser as B
from hq_egress.hosts import covered

log = logging.getLogger("hq_egress.browser_web")
ACCOUNTS = ("chatgpt-web", "gemini-web", "deepseek-web")
SANDBOX = os.environ.get("BROWSER_SANDBOX", "1") != "0"
PROFILES = Path(os.environ.get("BROWSER_WEB_PROFILES", "/profiles"))
LOGIN_S = 15 * 60
STEP_S = 30.0
READ_CHARS = 200_000
# Where the owner's sign-in window opens (their own pages; nothing else).
LOGIN_PAGES = {
    "chatgpt-web": "https://chatgpt.com/",
    "gemini-web": "https://gemini.google.com/app",
    "deepseek-web": "https://chat.deepseek.com/",
}
B64_JS = """async (u) => {
  const r = await fetch(u);
  const b = new Uint8Array(await r.arrayBuffer());
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
    account: Literal["chatgpt-web", "gemini-web", "deepseek-web"]
    recipe: dict[str, Any]
    prompt: str = Field(min_length=1, max_length=20_000)
    timeout_s: float = Field(gt=0, le=900)
    proxy: Proxy
    max_file_bytes: int = Field(default=25 * 1024 * 1024, ge=1)


class RunIn(B.RunIn):
    profile: Literal["chatgpt-web", "gemini-web", "deepseek-web"]
    allowed_hosts: list[str] = Field(min_length=1, max_length=30)


class LogoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account: Literal["chatgpt-web", "gemini-web", "deepseek-web"]


class StepFailed(Exception):
    def __init__(self, step: str, detail: str) -> None:
        super().__init__(detail)
        self.step = step
        self.detail = detail


def fail(error: str, detail: str, step: str | None = None) -> dict[str, Any]:
    return {"ok": False, "error": error, "detail": detail[:300], "step": step}


STALE_LOCK_S = 20 * 60


def clear_stale_lock(profile: Path, now: float | None = None) -> None:
    """A window or job that died leaves Chromium's Singleton* lock behind (it
    names the dead container), and Chromium then refuses the profile. A lock
    older than 20 minutes is stale: a job or a sign-in window lasts at most 15."""
    now = time.time() if now is None else now
    for p in profile.glob("Singleton*"):
        with contextlib.suppress(OSError):
            if now - p.lstat().st_mtime > STALE_LOCK_S:
                p.unlink()


class Webd:
    def __init__(
        self,
        *,
        profiles: Path = PROFILES,
        sandbox: bool = SANDBOX,
        insecure_tls: bool = False,
    ) -> None:
        """`insecure_tls`: tests only (their fake sites' own certificate)."""
        self.profiles = profiles
        self.sandbox = sandbox
        self.insecure_tls = insecure_tls
        self.locks = {a: asyncio.Lock() for a in ACCOUNTS}
        self._pw: Any = None

    async def start(self) -> None:
        os.umask(0o077)  # every file of every profile is 600
        self._pw = await async_playwright().start()

    async def stop(self) -> None:
        if self._pw is not None:
            await self._pw.stop()

    def ready(self) -> bool:
        return self._pw is not None

    def profile_dir(self, account: str) -> Path:
        if account not in ACCOUNTS:
            raise ValueError("unknown account")
        d = self.profiles / account
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
        return d

    async def open(self, account: str, proxy: Proxy, *, headless: bool = True) -> BrowserContext:
        profile = self.profile_dir(account)
        clear_stale_lock(profile)
        ctx: BrowserContext = await self._pw.chromium.launch_persistent_context(
            str(profile),
            headless=headless,
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
        ctx = await self.open(j.account, j.proxy)
        try:
            await ctx.route("**/*", _only(hosts))
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            return await run_recipe(page, ctx, j, hosts)
        finally:
            with contextlib.suppress(Error):
                await ctx.close()

    # -------------------------------------------------- a web.browse call --
    async def run(self, a: RunIn) -> dict[str, Any]:
        lock = self.locks[a.profile]
        if lock.locked():
            return {"code": "busy"}
        async with lock:
            hosts = frozenset(h.lower() for h in a.allowed_hosts)
            deadline = time.monotonic() + a.time_s
            ctx = await self.open(a.profile, Proxy(**a.proxy.model_dump()))
            try:
                return await asyncio.wait_for(
                    B.steps_in(ctx, a, deadline, allowed=lambda h: covered(h, hosts)),
                    timeout=a.time_s + 3,
                )
            except TimeoutError:
                return {"steps": [], "error": "timeout"}
            finally:
                with contextlib.suppress(Error):
                    await ctx.close()

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
        ctx = await self.open(account, proxy, headless=False)
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
            with contextlib.suppress(Error):
                await ctx.close()


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
    return (template or "").replace("{start_url}", str(j.recipe.get("start_url") or ""))


async def run_recipe(
    page: Page, ctx: BrowserContext, j: JobIn, hosts: frozenset[str]
) -> dict[str, Any]:
    """The recipe's steps; the first failing one is `recipe_failed` with that
    step (or `expired` when the page is a login page)."""
    rule = j.recipe.get("expired") or {}
    deadline = time.monotonic() + j.timeout_s
    text: str | None = None
    file: dict[str, Any] | None = None
    steps = j.recipe.get("steps") or []
    for i, st in enumerate(steps):
        do = str(st.get("do"))
        tag = f"{i}:{do}"
        left = deadline - time.monotonic()
        if left <= 0:
            return fail("timeout", "the job ran past its time", tag)
        ms = min(float(st.get("timeout_s") or STEP_S), left) * 1000
        try:
            got = await _recipe_step(page, ctx, st, ms, j, hosts)
        except (PwTimeout, Error, StepFailed, ValueError) as exc:
            if await expired(page, rule):
                return fail("expired", "the profile shows a login page: sign in again", tag)
            if st.get("optional"):
                continue
            why = exc.detail if isinstance(exc, StepFailed) else type(exc).__name__
            return fail("recipe_failed", f"step {tag} failed: {why}", tag)
        if do == "goto" and await expired(page, rule):
            return fail("expired", "the profile shows a login page: sign in again", tag)
        if isinstance(got, str):
            text = got
        elif isinstance(got, dict):
            file = got
    if text is None and file is None:
        return fail("recipe_failed", "the recipe read nothing", None)
    return {"ok": True, "text_md": text, "file": file}


async def _recipe_step(
    page: Page,
    ctx: BrowserContext,
    st: dict[str, Any],
    ms: float,
    j: JobIn,
    hosts: frozenset[str],
) -> str | dict[str, Any] | None:
    do = str(st.get("do"))
    sel = str(st.get("selector") or "")
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
        await page.locator(sel).first.fill(j.prompt, timeout=ms)
    elif do == "press":
        await page.locator(sel).first.press(str(st.get("key")), timeout=ms)
    elif do == "pause":
        await page.wait_for_timeout(min(int(st.get("ms") or 1000), 5000))
    elif do == "read":
        loc = page.locator(sel)
        n = await loc.count()
        if n == 0:
            raise StepFailed(do, "nothing to read")
        return str(await loc.nth(n - 1).inner_text(timeout=ms))[:READ_CHARS]
    elif do == "download_image":
        return await _image(page, ctx, sel, str(st.get("attr") or "src"), ms, j, hosts)
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
    src = await loc.nth(n - 1).get_attribute(attr, timeout=ms)
    if not src:
        raise StepFailed("download_image", "the image has no source")
    if src.startswith("data:"):
        _, _, b64 = src.partition(",")
        data = base64.b64decode(b64)
    elif src.startswith("blob:"):
        data = base64.b64decode(await page.evaluate(B64_JS, src))
    else:
        url = src if "://" in src else urljoin(page.url, src)
        host = (urlsplit(url).hostname or "").lower()
        if not url.startswith("https://") or not covered(host, hosts):
            raise StepFailed("download_image", "not one of the site's own hosts")
        resp = await ctx.request.get(url, timeout=ms, max_redirects=0)
        try:
            data = await resp.body()
        finally:
            await resp.dispose()
    return _file(data[: j.max_file_bytes + 1], src.rsplit("/", 1)[-1][:60] or "image", j)


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
