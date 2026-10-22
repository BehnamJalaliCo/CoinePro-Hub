"""`python -m hq_egress.browser`: the headless browser service (prompt 07 §2.1),
in its own container on hq-browser, where egress is its only peer.

Chromium (Playwright) runs with its own sandbox ON (7.1): a non-root user,
Playwright's seccomp profile (infra/browser/seccomp_profile.json, which lets
Chromium make its user namespaces; compose adds only CAP_SYS_CHROOT to the
bounding set, which the non-root user never holds outside them). It runs
once, and every web.browse call gets a fresh context (its own empty profile:
no cookies, cache or storage of any other call), closed when the call ends,
at most BROWSER_MAX_SESSIONS at a time. Should the sandbox ever be switched
off (BROWSER_SANDBOX=0), every call launches a browser process of its own:
a `--no-sandbox` process is never shared between calls, so never between
companies. Each renderer's JavaScript heap is capped
(`--js-flags=--max-old-space-size`), WebRTC sends no UDP around the proxy.

All its traffic goes through egress's proxy with that call's own credential
(the container has no other way out). Before a click, a typed text or a
choice, the target is examined (rules.commitment); every request the page
sends is examined too (`_route`): a GET that commits (rules.get_commitment)
and, while signed in, any call other than GET/HEAD the account's policy does
not list are aborted, and the step is `needs_owner`. A service account signs
in as its policy says (cookie, header for its host only over https, or a
login form egress fills); a failed sign-in is `sign_in_failed`. The secret is
masked in screenshots (a page that shows it gets none), scrubbed from every
text before it is cut, and a file that holds it is dropped. The files of one
call (screenshots and downloads) have one total cap, and a download beyond
its cap is refused, never silently cut.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import html
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urljoin, urlsplit

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from playwright.async_api import Browser, BrowserContext, Error, Page, Route, async_playwright
from playwright.async_api import TimeoutError as PwTimeout
from pydantic import BaseModel, ConfigDict, Field

from hq_common import heartbeat, logs
from hq_egress.accounts import Account, forms_of, holds_secret, scrub, scrub_cut
from hq_egress.rules import FACTS_JS, commitment, get_commitment

log = logging.getLogger("hq_egress.browser")
MAX_SESSIONS = int(os.environ.get("BROWSER_MAX_SESSIONS", "2"))
SANDBOX = os.environ.get("BROWSER_SANDBOX", "1") != "0"
JS_HEAP_MB = int(os.environ.get("BROWSER_JS_HEAP_MB", "192"))
READ_CHARS = 20_000
TITLE_CHARS = 300
MAX_REDIRECTS = 5
READ_METHODS = ("GET", "HEAD")
ARGS = [
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-sync",
    "--disable-quic",
    "--disable-features=Translate,MediaRouter,OptimizationHints,AutofillServerCommunication",
    "--no-first-run",
    "--renderer-process-limit=4",
    # WebRTC: no UDP that does not go through the proxy (there is none), so
    # no candidate leaks an address and no peer is reached around egress.
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    f"--js-flags=--max-old-space-size={JS_HEAP_MB}",
]


class Proxy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server: str
    username: str
    password: str


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[dict[str, Any]] = Field(min_length=1, max_length=30)
    proxy: Proxy
    account: Account | None = None
    time_s: float = Field(default=20, gt=0, le=120)
    max_download_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    # Every file of the call together (screenshots and downloads, 7.1).
    max_files_bytes: int = Field(default=16 * 1024 * 1024, ge=1)


class Refused(Exception):
    """A step that may not go on: `code` is the step's error."""

    def __init__(self, code: str, reason: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.reason = reason


class Browserd:
    def __init__(self, *, sandbox: bool = SANDBOX, insecure_tls: bool = False) -> None:
        """`insecure_tls`: tests only (their fake sites' own certificate)."""
        self.sandbox = sandbox
        self.insecure_tls = insecure_tls
        self.browser: Browser | None = None  # shared only when sandboxed
        self.slots = asyncio.Semaphore(MAX_SESSIONS)
        self._pw: Any = None

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        if self.sandbox:
            self.browser = await self._launch()

    async def _launch(self) -> Browser:
        browser: Browser = await self._pw.chromium.launch(
            headless=True,
            args=ARGS,
            chromium_sandbox=self.sandbox,
            proxy={"server": "http://per-context"},
        )
        return browser

    def ready(self) -> bool:
        if self.sandbox:
            return self.browser is not None and self.browser.is_connected()
        return self._pw is not None

    async def stop(self) -> None:
        if self.browser is not None:
            await self.browser.close()
        if self._pw is not None:
            await self._pw.stop()

    async def run(self, a: RunIn) -> dict[str, Any]:
        try:
            await asyncio.wait_for(self.slots.acquire(), timeout=5)
        except TimeoutError:
            return {"code": "busy"}
        try:
            return await asyncio.wait_for(self._run(a), timeout=a.time_s + 3)
        except TimeoutError:
            return {"steps": [], "error": "timeout"}
        finally:
            self.slots.release()

    async def _run(self, a: RunIn) -> dict[str, Any]:
        # Sandboxed: one shared process, a fresh context per call. Not
        # sandboxed: a process of this call's own, closed with it.
        own = None if self.sandbox else await self._launch()
        browser = own or self.browser
        assert browser is not None
        try:
            return await self._session(browser, a)
        finally:
            if own is not None:
                with contextlib.suppress(Error):
                    await own.close()

    async def _session(self, browser: Browser, a: RunIn) -> dict[str, Any]:
        deadline = time.monotonic() + a.time_s
        secrets = a.account.secrets() if a.account else []
        ctx = await browser.new_context(
            proxy=a.proxy.model_dump(),
            accept_downloads=True,
            service_workers="block",
            viewport={"width": 1280, "height": 800},
            locale="fa-IR",
            ignore_https_errors=self.insecure_tls,
        )
        out: dict[str, Any] = {"steps": [], "files": [], "files_bytes": 0, "blocked": None}
        mask_selectors = ["input[type=password]"]
        at = {"step": 0}
        try:
            try:  # the owner's own login form (its URL is the policy's, on the account's site)
                await _sign_in(ctx, a.account, deadline, mask_selectors)
            except (Error, ValueError) as exc:  # PwTimeout is an Error
                log.warning("sign-in failed: %s", type(exc).__name__)
                return {"code": "sign_in_failed", "steps": [], "files": [],
                        "error": type(exc).__name__}  # fmt: skip
            await ctx.route("**/*", _route(a.account, deadline, out, at))
            page = await ctx.new_page()
            for i, step in enumerate(a.steps):
                at["step"] = i
                left = deadline - time.monotonic()
                if left <= 0.5:
                    out["steps"].append(
                        {"i": i, "do": step.get("do"), "ok": False, "error": "time_up"}
                    )
                    break
                res = await _step(page, ctx, i, step, min(left, 10) * 1000, a, mask_selectors, out)
                if (out["blocked"] or {}).get("step") == i:  # a request the route stopped
                    res = {**res, "ok": False, "error": "needs_owner"}
                out["steps"].append(res)
                if out["blocked"] or not res.get("ok"):
                    break
            out["final_url"] = page.url
            with contextlib.suppress(Error):
                out["title"] = scrub_cut(await page.title(), secrets, TITLE_CHARS)[0]
        finally:
            await ctx.close()
        files = out.pop("files")
        out.pop("files_bytes", None)
        clean = scrub(out, secrets)
        clean["files"] = files
        return dict(clean)


async def _sign_in(
    ctx: BrowserContext, account: Account | None, deadline: float, masks: list[str]
) -> None:
    if account is None or account.browse is None:
        return
    b = account.browse
    if b.kind == "cookie":
        await ctx.add_cookies(
            [
                {
                    "name": b.name or "session",
                    "value": account.secret,
                    "domain": "." + account.site,
                    "path": "/",
                    "secure": True,  # over https only
                    "httpOnly": True,
                }
            ]
        )
    elif b.kind == "form" and b.login_url and b.pass_selector:
        host = (urlsplit(b.login_url).hostname or "").lower()
        if not (b.login_url.startswith("https://") and account.covers(host)):
            raise ValueError("the login form must be on the account's own site (https)")
        masks.append(b.pass_selector)
        page = await ctx.new_page()
        ms = max(1000.0, (deadline - time.monotonic()) * 1000 / 2)
        await page.goto(b.login_url, wait_until="domcontentloaded", timeout=ms)
        if b.user_selector and b.username:
            await page.fill(b.user_selector, b.username, timeout=ms)
        await page.fill(b.pass_selector, account.secret, timeout=ms)
        if b.submit_selector:
            await page.click(b.submit_selector, timeout=ms)
            with contextlib.suppress(PwTimeout):
                await page.wait_for_load_state("domcontentloaded", timeout=ms)
        await page.close()


def _stop(out: dict[str, Any], step: int, reason: str, method: str) -> None:
    if out["blocked"] is None:
        out["blocked"] = {"step": step, "code": "needs_owner", "reason": reason,
                          "method": method[:10]}  # fmt: skip


def _account_header(account: Account | None) -> str | None:
    b = account.browse if account is not None else None
    return (b.name or "authorization").lower() if b is not None and b.kind == "header" else None


def _route(
    account: Account | None, deadline: float, out: dict[str, Any], at: dict[str, int]
) -> Any:
    """Every request the session sends (contract §18.13, 7.1): a GET that
    commits is aborted; while signed in, so is a call the account's policy
    does not list, and the account's header goes to its own host over https,
    one hop at a time."""
    header = _account_header(account)

    async def handle(route: Route) -> None:
        req = route.request
        method = req.method.upper()
        reason = None
        if account is not None and not account.allows(method, req.url):
            reason = "commitment_request"
        elif method in READ_METHODS:
            reason = get_commitment(req.url)
        if reason:
            _stop(out, at["step"], reason, method)
            await route.abort("blockedbyclient")
            return
        if account is None:
            await route.continue_()
            return
        parts = urlsplit(req.url)
        host = (parts.hostname or "").lower().rstrip(".")
        inject = header is not None and parts.scheme == "https" and account.covers(host)
        if not inject and method in READ_METHODS:
            await route.continue_()
            return
        # The account's own host (or a listed call): sent here one hop at a
        # time. route.continue_(headers=) would put the header on every
        # redirect too, to whatever host it names.
        headers = dict(req.headers)
        if inject:
            assert header is not None
            headers[header] = account.secret
        try:
            resp = await route.fetch(
                headers=headers,
                max_redirects=0,
                timeout=max(1000.0, (deadline - time.monotonic()) * 1000),
            )
        except Error:
            with contextlib.suppress(Error):
                await route.abort("failed")
            return
        await route.fulfill(response=resp)

    return handle


async def _facts(page: Page, target: str, ms: float) -> dict[str, Any]:
    loc = page.locator(target).first
    facts: dict[str, Any] = await loc.evaluate(FACTS_JS, timeout=ms)
    return facts


async def _shows_secret(page: Page, secrets: list[str]) -> bool:
    """Whether the page (any frame) shows a form of a secret as text: its
    screenshot would show it, which no mask can know where (7.1). The check
    runs here, never in the page: the page never sees the secret."""
    if not secrets:
        return False
    forms = forms_of(secrets)
    for frame in page.frames:
        try:
            doc = await frame.content()
        except Error:
            return True  # cannot tell: the safe side
        text = html.unescape(doc)
        if any(f in doc or f in text for f in forms):
            return True
    return False


async def _step(
    page: Page,
    ctx: BrowserContext,
    i: int,
    step: dict[str, Any],
    ms: float,
    a: RunIn,
    masks: list[str],
    out: dict[str, Any],
) -> dict[str, Any]:
    do = str(step.get("do"))
    target = step.get("target")
    text = step.get("text")
    url = step.get("url")
    res: dict[str, Any] = {"i": i, "do": do, "ok": True}
    secrets = a.account.secrets() if a.account else []
    try:
        if do in ("click", "type", "select") or (do == "download" and target and not url):
            if not target:
                return {**res, "ok": False, "error": "target_required"}
            facts = await _facts(page, str(target), ms)
            reason = commitment(facts, do)
            if reason:
                out["blocked"] = {"step": i, "code": "needs_owner", "reason": reason}
                return {**res, "ok": False, "error": "needs_owner"}
        if do in ("goto", "download") and isinstance(url, str):
            reason = get_commitment(url)  # a GET that commits (7.1)
            if reason:
                out["blocked"] = {"step": i, "code": "needs_owner", "reason": reason}
                return {**res, "ok": False, "error": "needs_owner"}
        if do == "goto":
            if not (isinstance(url, str) and url.startswith(("http://", "https://"))):
                return {**res, "ok": False, "error": "bad_url"}
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=ms)
            res["status"] = resp.status if resp else None
        elif do == "click":
            await page.locator(str(target)).first.click(timeout=ms)
            with contextlib.suppress(PwTimeout):
                await page.wait_for_load_state("domcontentloaded", timeout=min(ms, 5000))
        elif do == "type":
            await page.locator(str(target)).first.fill(str(text or ""), timeout=ms)
        elif do == "select":
            await page.locator(str(target)).first.select_option(str(text or ""), timeout=ms)
        elif do == "scroll":
            dy = str(text or "2000")
            await page.mouse.wheel(0, int(dy) if dy.lstrip("-").isdigit() else 2000)
        elif do == "wait":
            if target:
                await page.wait_for_selector(str(target), timeout=ms)
            else:
                wait = int(str(text)) if str(text or "").isdigit() else 1000
                await page.wait_for_timeout(min(wait, 5000, ms))
        elif do == "read":
            body = await page.inner_text("body", timeout=ms)
            res["text"], res["truncated"] = scrub_cut(body, secrets, READ_CHARS)
        elif do == "screenshot":
            if await _shows_secret(page, secrets):
                return {**res, "ok": False, "error": "secret_on_page"}
            png = await page.screenshot(
                type="png", timeout=ms, mask=[page.locator(s) for s in masks]
            )
            _keep(out, a, _file("screenshot", i, f"screenshot-{i + 1}.png", "image/png", png))
        elif do == "download":
            cap = min(a.max_download_bytes, max(0, a.max_files_bytes - out["files_bytes"]))
            data, name, mime = await _download(page, ctx, target, url, ms, cap, a.account)
            if holds_secret(data, secrets):
                return {**res, "ok": False, "error": "file_held_secret"}
            _keep(out, a, _file("download", i, name, mime, data))
        else:
            return {**res, "ok": False, "error": "unknown_step"}
    except Refused as r:
        if r.code == "needs_owner":
            out["blocked"] = {"step": i, "code": "needs_owner", "reason": r.reason}
        return {**res, "ok": False, "error": r.code}
    except PwTimeout:
        return {**res, "ok": False, "error": "timeout"}
    except Error as exc:
        return {**res, "ok": False, "error": type(exc).__name__}
    res["url"] = page.url
    return res


def _keep(out: dict[str, Any], a: RunIn, f: dict[str, Any]) -> None:
    """A file joins the call's files within their total cap (7.1)."""
    if out["files_bytes"] + f["size"] > a.max_files_bytes:
        raise Refused("files_too_large")
    out["files"].append(f)
    out["files_bytes"] += f["size"]


async def _download(
    page: Page,
    ctx: BrowserContext,
    target: Any,
    url: Any,
    ms: float,
    cap: int,
    account: Account | None,
) -> tuple[bytes, str, str]:
    """A file, whole: one beyond `cap` is refused (`download_too_large`),
    never cut short in silence (7.1)."""
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return await _fetch_file(ctx, url, ms, cap, account)
    async with page.expect_download(timeout=ms) as info:
        await page.locator(str(target)).first.click(timeout=ms)
    dl = await info.value
    path = await dl.path()
    # One byte past the cap tells a file that does not fit (never a silent cut).
    data = await asyncio.to_thread(lambda: open(path, "rb").read(cap + 1))  # noqa: SIM115
    if len(data) > cap:
        raise Refused("download_too_large")
    return data, (dl.suggested_filename or "download")[:120], "application/octet-stream"


async def _fetch_file(
    ctx: BrowserContext, url: str, ms: float, cap: int, account: Account | None
) -> tuple[bytes, str, str]:
    """A download by URL. The context's request API does not pass the page's
    route, so it is judged here, hop by hop: a GET that commits is refused,
    the account's header goes to its own host over https only."""
    header = _account_header(account)
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        reason = get_commitment(current)
        if reason:
            raise Refused("needs_owner", reason)
        parts = urlsplit(current)
        host = (parts.hostname or "").lower().rstrip(".")
        headers = {}
        if header and account is not None and parts.scheme == "https" and account.covers(host):
            headers[header] = account.secret
        resp = await ctx.request.get(current, timeout=ms, max_redirects=0, headers=headers or None)
        try:
            location = resp.headers.get("location")
            if resp.status in (301, 302, 303, 307, 308) and location:
                current = urljoin(current, location)
                continue
            declared = resp.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > cap:
                raise Refused("download_too_large")
            data = await resp.body()
            if len(data) > cap:
                raise Refused("download_too_large")
            name = (urlsplit(current).path.rsplit("/", 1)[-1] or "download")[:120]
            mime = resp.headers.get("content-type", "application/octet-stream").split(";")[0]
            return data, name, mime
        finally:
            await resp.dispose()
    raise Refused("too_many_redirects")


def _file(kind: str, step: int, name: str, mime: str, data: bytes) -> dict[str, Any]:
    return {
        "kind": kind,
        "step": step,
        "name": name,
        "mime": mime,
        "size": len(data),
        "data_b64": base64.b64encode(data).decode(),
    }


def build_app(d: Browserd) -> FastAPI:
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
        title="browser", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )

    @app.post("/v1/run")
    async def run(a: RunIn) -> JSONResponse:
        got = await d.run(a)
        return JSONResponse(got, status_code=503 if got.get("code") == "busy" else 200)

    return app


def main() -> None:
    logs.setup("browser", os.environ.get("LOG_LEVEL", "info"))
    uvicorn.run(
        build_app(Browserd()),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8095")),
        log_config=None,
        access_log=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
