"""The hub's runner API (contract §26.4), as the runner uses it.

Request bodies carry exactly the fields of §26.4 (the hub's models forbid
unknown fields). What §26.4 has no field for travels in headers and, on the
long-poll, in query parameters as well:
    X-HQ-Runner-Version   the runner's version (also in User-Agent)
    X-HQ-Runner-Via       "private" | "public": the route this request took
    X-HQ-Runner-Hub-Rtt-Ms  the last measured round trip to the hub, ms (§26.6 hub_rtt_ms)
    X-HQ-Runner-Job       the job a classify call belongs to
Errors are RFC 9457 problems with a stable `code`.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from hq_runner import __version__
from hq_runner.net import Route

log = logging.getLogger("hq_runner.hub")

API = "/api/v1"
LONG_POLL_S = 30.0


class HubError(Exception):
    def __init__(self, status: int, code: str | None = None, detail: str | None = None):
        self.status = status
        self.code = code
        self.detail = detail
        super().__init__(f"hub answered {status}" + (f" {code}" if code else ""))


class Transient(HubError):
    """Network error, 429 or 5xx: retry with backoff."""


class Unauthorized(HubError):
    """401: the runner token is not accepted any more; pair again."""


class Revoked(HubError):
    """410 or runner_revoked: the owner detached this server; stop."""


class JobGone(HubError):
    """The job is no longer running on the hub's side (cancelled or finished)."""


def problem_code(resp: httpx.Response) -> tuple[str | None, str | None]:
    try:
        body = resp.json()
    except ValueError:
        return None, None
    if not isinstance(body, dict):
        return None, None
    code = body.get("code") or body.get("error")
    detail = body.get("detail") or body.get("title")
    return (str(code) if code else None), (str(detail) if detail else None)


def classify_status(resp: httpx.Response, *, job_scoped: bool = False) -> HubError | None:
    """The error a response stands for, or None when it is a success."""
    status = resp.status_code
    if status < 400:
        return None
    code, detail = problem_code(resp)
    if status == 401:
        return Unauthorized(status, code, detail)
    if code in ("runner_revoked", "server_revoked", "server_detached"):
        return Revoked(status, code, detail)
    if job_scoped and (status in (404, 409) or (code or "").startswith("job_")):
        return JobGone(status, code, detail)
    if status == 410:
        return Revoked(status, code, detail)
    if status == 429 or status >= 500:
        return Transient(status, code, detail)
    return HubError(status, code, detail)


@dataclass
class Backoff:
    """Exponential backoff with full jitter."""

    base: float = 1.0
    cap: float = 60.0
    attempt: int = 0
    rand: Callable[[], float] = field(default=random.random)

    def next(self) -> float:
        delay = min(self.cap, self.base * float(2**self.attempt))
        self.attempt = min(self.attempt + 1, 16)
        return float(delay * (0.5 + self.rand() / 2))

    def reset(self) -> None:
        self.attempt = 0


@dataclass
class NextJob:
    job: dict[str, Any] | None
    cancels: list[str]


class Hub:
    def __init__(self, route: Route, token: Callable[[], str | None]):
        self.route = route
        self.token = token

    def headers(self, auth: bool, job_id: str | None = None) -> dict[str, str]:
        h = {
            "User-Agent": f"hq-runner/{__version__}",
            "X-HQ-Runner-Version": __version__,
            "X-HQ-Runner-Via": self.route.via,
            "Accept": "application/json",
        }
        if self.route.rtt_ms is not None:
            h["X-HQ-Runner-Hub-Rtt-Ms"] = f"{self.route.rtt_ms:.1f}"
        if job_id:
            h["X-HQ-Runner-Job"] = job_id
        tok = self.token() if auth else None
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        return h

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, str] | None = None,
        auth: bool = True,
        read_timeout: float | None = None,
        job_scoped: bool = False,
        job_id: str | None = None,
    ) -> httpx.Response:
        for attempt in range(2):
            used = self.token() if auth else None
            client = self.route.client()
            try:
                resp = await client.request(
                    method,
                    path if path.startswith("http") else API + path,
                    json=json,
                    params=params,
                    headers=self.headers(auth, job_id),
                    timeout=read_timeout if read_timeout is not None else httpx.USE_CLIENT_DEFAULT,
                )
            except httpx.ConnectError as exc:
                await self.route.connect_failed()
                raise Transient(0, "connect_error", type(exc).__name__) from exc
            except httpx.TransportError as exc:
                raise Transient(0, "network_error", type(exc).__name__) from exc
            err = classify_status(resp, job_scoped=job_scoped)
            # A request that raced a token rotation is retried once with the new token.
            if isinstance(err, Unauthorized) and auth and attempt == 0 and self.token() != used:
                continue
            if err is not None:
                raise err
            return resp
        raise AssertionError("unreachable")  # pragma: no cover

    # -- pairing (unauthenticated) ------------------------------------------------
    async def pair(self, body: dict[str, Any]) -> dict[str, Any]:
        resp = await self.request("POST", "/runners/pair", json=body, auth=False)
        return dict(resp.json())

    async def token_poll(self, device_code: str) -> httpx.Response:
        """The raw answer: 428 while pending, 200 once approved."""
        client = self.route.client()
        try:
            return await client.post(
                API + "/runners/token",
                json={"device_code": device_code},
                headers=self.headers(auth=False),
            )
        except httpx.ConnectError as exc:
            await self.route.connect_failed()
            raise Transient(0, "connect_error", type(exc).__name__) from exc
        except httpx.TransportError as exc:
            raise Transient(0, "network_error", type(exc).__name__) from exc

    # -- the runner's own calls (bearer) --------------------------------------------
    async def rotate(self) -> str:
        resp = await self.request("POST", "/runners/rotate")
        token = resp.json().get("runner_token")
        if not token:
            raise HubError(resp.status_code, "bad_rotate_answer")
        return str(token)

    async def next_job(self, slots: int) -> NextJob:
        params = {"via": self.route.via, "slots": str(slots)}
        if self.route.rtt_ms is not None:
            params["hub_rtt_ms"] = f"{self.route.rtt_ms:.1f}"
        resp = await self.request(
            "GET", "/runners/jobs/next", params=params, read_timeout=LONG_POLL_S + 15
        )
        if resp.status_code == 204 or not resp.content:
            return NextJob(None, [])
        body = resp.json()
        if not isinstance(body, dict):
            return NextJob(None, [])
        job = body.get("job")
        if job is None and "kind" in body and "id" in body:
            job = body
        cancels: list[str] = []
        for key in ("cancel", "cancels", "cancelled"):
            val = body.get(key)
            if isinstance(val, list):
                cancels += [str(v) for v in val]
            elif isinstance(val, str | int) and not isinstance(val, bool):
                cancels.append(str(val))
        if isinstance(job, dict) and job.get("state") == "cancelled":
            cancels.append(str(job.get("id")))
            job = None
        return NextJob(job if isinstance(job, dict) else None, cancels)

    async def post_events(self, job_id: str, events: list[dict[str, Any]]) -> None:
        await self.request(
            "POST", f"/runners/jobs/{job_id}/events", json={"events": events}, job_scoped=True
        )

    async def post_result(self, job_id: str, body: dict[str, Any]) -> None:
        await self.request("POST", f"/runners/jobs/{job_id}/result", json=body, job_scoped=True)

    async def classify(self, cmd: str, job_id: str | None = None) -> str | None:
        resp = await self.request("POST", "/runners/classify", json={"cmd": cmd}, job_id=job_id)
        cat = resp.json().get("category")
        return str(cat) if cat else None

    def same_origin(self, url: str) -> bool:
        a, b = urlsplit(self.route.hub), urlsplit(urljoin(self.route.hub + "/", url))
        return (a.scheme, a.hostname, a.port) == (b.scheme, b.hostname, b.port)

    async def download(self, url: str, dest: Path, max_bytes: int) -> int:
        """Downloads a hub URL (absolute on the hub, or a hub path) with the
        runner token. A URL on any other host is refused: the token never leaves."""
        if not self.same_origin(url):
            raise HubError(0, "foreign_url", "files are fetched from the hub only")
        full = urljoin(self.route.hub + "/", url.lstrip("/")) if not url.startswith("http") else url
        client = self.route.client()
        size = 0
        try:
            async with client.stream("GET", full, headers=self.headers(True), timeout=300) as resp:
                err = classify_status(resp, job_scoped=True)
                if err is not None:
                    await resp.aread()
                    raise err
                with dest.open("wb") as fh:
                    async for chunk in resp.aiter_bytes(1 << 16):
                        size += len(chunk)
                        if size > max_bytes:
                            raise HubError(0, "file_too_large")
                        fh.write(chunk)
        except httpx.TransportError as exc:
            raise Transient(0, "network_error", type(exc).__name__) from exc
        return size


async def with_retry[T](
    op: Callable[[], Any],
    *,
    attempts: int = 8,
    backoff: Backoff | None = None,
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> T:
    """Retries `op` on Transient errors with backoff; other errors pass through."""
    bo = backoff or Backoff(base=0.5, cap=30.0)
    for i in range(attempts):
        try:
            result: T = await op()
            return result
        except Transient:
            if i == attempts - 1:
                raise
            await sleep(bo.next())
    raise AssertionError("unreachable")  # pragma: no cover
