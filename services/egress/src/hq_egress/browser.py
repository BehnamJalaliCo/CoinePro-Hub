"""`python -m hq_egress.browser`: the headless browser service (prompt 07 §2.1),
in its own container on hq-browser, where egress is its only peer.

Chromium (Playwright) runs once; every web.browse call gets a fresh context
(its own empty profile: no cookies, cache or storage of any other call),
closed when the call ends, at most BROWSER_MAX_SESSIONS at a time. All its
traffic goes through egress's proxy with that call's own credential (the
container has no other way out). Before a click, a typed text or a choice,
the target is examined (rules.commitment): an external commitment stops
the call with `needs_owner`. A service account signs in as its policy says
(cookie, header for its host only, or a login form egress fills); the
secret is masked in screenshots and scrubbed from every text. While signed
in, every request is checked on its way out (`_guard`): a call other than
GET/HEAD the account's policy does not list is aborted and the step is
`needs_owner`; the account's header goes only to its own host, one hop at a
time (a redirect comes back to the browser and is checked as a new request).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from playwright.async_api import Browser, BrowserContext, Error, Page, Route, async_playwright
from playwright.async_api import TimeoutError as PwTimeout
from pydantic import BaseModel, ConfigDict, Field

from hq_common import heartbeat, logs
from hq_egress.accounts import Account, scrub
from hq_egress.rules import FACTS_JS, commitment

log = logging.getLogger("hq_egress.browser")
MAX_SESSIONS = int(os.environ.get("BROWSER_MAX_SESSIONS", "2"))
READ_CHARS = 20_000
ARGS = [
    "--no-sandbox",  # no user namespaces in a cap_drop ALL container; the container is the sandbox
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


class Browserd:
    def __init__(self) -> None:
        self.browser: Browser | None = None
        self.slots = asyncio.Semaphore(MAX_SESSIONS)
        self._pw: Any = None

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(
            headless=True, args=ARGS, proxy={"server": "http://per-context"}
        )

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
        assert self.browser is not None
        deadline = time.monotonic() + a.time_s
        secrets = [a.account.secret] if a.account else []
        ctx = await self.browser.new_context(
            proxy=a.proxy.model_dump(),
            accept_downloads=True,
            service_workers="block",
            viewport={"width": 1280, "height": 800},
            locale="fa-IR",
        )
        out: dict[str, Any] = {"steps": [], "files": [], "blocked": None}
        mask_selectors = ["input[type=password]"]
        at = {"step": 0}
        try:
            await _sign_in(ctx, a.account, deadline, mask_selectors)
            if a.account is not None:
                await ctx.route("**/*", _guard(a.account, deadline, out, at))
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
                if (out["blocked"] or {}).get("step") == i:  # a request the guard stopped
                    res = {**res, "ok": False, "error": "needs_owner"}
                out["steps"].append(res)
                if out["blocked"] or not res.get("ok"):
                    break
            out["final_url"] = page.url
            with contextlib.suppress(Error):
                out["title"] = (await page.title())[:300]
        finally:
            await ctx.close()
        files = out.pop("files")
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
                    "secure": True,
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


def _guard(account: Account, deadline: float, out: dict[str, Any], at: dict[str, int]) -> Any:
    """Every request of a signed-in session (contract §18.13, 7.1)."""
    b = account.browse
    header = (b.name or "authorization").lower() if b is not None and b.kind == "header" else None

    async def handle(route: Route) -> None:
        req = route.request
        method = req.method.upper()
        if not account.allows(method, req.url):
            if out["blocked"] is None:
                out["blocked"] = {
                    "step": at["step"],
                    "code": "needs_owner",
                    "reason": "commitment_request",
                    "method": method[:10],
                }
            await route.abort("blockedbyclient")
            return
        host = (urlsplit(req.url).hostname or "").lower().rstrip(".")
        inject = header is not None and account.covers(host)
        if not inject and method in ("GET", "HEAD"):
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
    try:
        if do in ("click", "type", "select") or (do == "download" and target and not url):
            if not target:
                return {**res, "ok": False, "error": "target_required"}
            facts = await _facts(page, str(target), ms)
            reason = commitment(facts, do)
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
            res["text"] = body[:READ_CHARS]
            res["truncated"] = len(body) > READ_CHARS
        elif do == "screenshot":
            png = await page.screenshot(
                type="png", timeout=ms, mask=[page.locator(s) for s in masks]
            )
            out["files"].append(_file("screenshot", i, f"screenshot-{i + 1}.png", "image/png", png))
        elif do == "download":
            data, name, mime = await _download(page, ctx, target, url, ms, a.max_download_bytes)
            out["files"].append(_file("download", i, name, mime, data))
        else:
            return {**res, "ok": False, "error": "unknown_step"}
    except PwTimeout:
        return {**res, "ok": False, "error": "timeout"}
    except Error as exc:
        return {**res, "ok": False, "error": type(exc).__name__}
    res["url"] = page.url
    return res


async def _download(
    page: Page, ctx: BrowserContext, target: Any, url: Any, ms: float, cap: int
) -> tuple[bytes, str, str]:
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        resp = await ctx.request.get(url, timeout=ms, max_redirects=5)
        data = (await resp.body())[:cap]
        name = (urlsplit(url).path.rsplit("/", 1)[-1] or "download")[:120]
        mime = resp.headers.get("content-type", "application/octet-stream").split(";")[0]
        return data, name, mime
    async with page.expect_download(timeout=ms) as info:
        await page.locator(str(target)).first.click(timeout=ms)
    dl = await info.value
    path = await dl.path()
    data = await asyncio.to_thread(lambda: open(path, "rb").read(cap))  # noqa: SIM115
    return data, (dl.suggested_filename or "download")[:120], "application/octet-stream"


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
            return {"ok": d.browser is not None and d.browser.is_connected()}

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
