"""The substitute players' web path at egress (prompt 12 §9.1.5, contract
§21.13): ChatGPT, Gemini and DeepSeek in the hub's signed-in browser profiles.

    POST /v1/substitutes/web          {account, task, prompt, timeout_s}
                                      one job: the account's reviewed recipe
                                      (hq_egress.recipes) run by the profile
                                      browser (browser-web) in that profile
    POST /v1/substitutes/web/logout   {account}: the profile wiped

The worker calls both (hq-egress-api; the api's job queue decides when, the
holding lock first). One job per account at a time (`busy` otherwise). The
profile browser's every connection goes through egress's listener on :3132
with this job's bucket, which reaches only the recipe's own hosts; its
entries go to egress's own log as host, status and size (never a path, a
cookie or a prompt). The answer carries the text read from the page or the
original file, never a cookie or the page's other content. ⟨1.10⟩ §28.4: a
`recipe_failed` answer carries ONE screenshot of the page as the failed step
left it (JPEG, the viewport only, ≤ 2 MB), for the overseer and the SRE who
fix the recipe; `reload: true` (the hub's one retry) reloads the page after
the recipe's first `goto`.
web.browse with a profile account (the Claude fallback when a recipe fails)
runs in the same profile browser, on the same hosts only (profile_browse).
"""

from __future__ import annotations

import base64
import logging
import re
import time
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from hq_common.redact import scrub
from hq_egress.guard import Blocked
from hq_egress.hosts import covered
from hq_egress.net import Entry, track
from hq_egress.recipes import MAX_IMAGES, NOTE, TASK_FILE_BYTES, Account, TaskName
from hq_egress.rules import get_commitment

log = logging.getLogger("hq_egress.substitutes_web")
router = APIRouter()
# `unsupported`: the job carries files and the recipe's task has no step that attaches them
# (never sent without them: a video "of the attached image" made from the text alone is wrong)
ERRORS = ("expired", "recipe_failed", "timeout", "busy", "off", "unsupported")
DETAIL_CHARS = 300
SCREENSHOT_BYTES = 2 * 1024 * 1024
MIME_OK = (
    "image/png", "image/jpeg", "image/webp", "image/gif", "video/mp4", "video/webm",
    "audio/wav", "audio/mpeg", "audio/ogg", "audio/flac",
)  # fmt: skip
MAX_JOB_FILES = 10
# The hub's own cap on a call's question (TEXT_LIMIT, substitutes.calls.input_md); a long_read
# seat or a work's brief longer than the old 20 000 was refused here with a 422 every time
PROMPT_CHARS = 200_000
# ⟨2026-11-17⟩ a file already in the profile browser's spool (a long video, its thumbnail): a plain
# name of that account's spool directory, never a path (browser_web.SPOOL_NAME)
SPOOL_NAME = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$"
SpoolName = Annotated[str, StringConstraints(pattern=SPOOL_NAME)]
# what the pages of an upload's job add to its bucket, beyond its files (Studio's own heavy pages;
# a long upload's 25 minutes of them)
PAGES_BYTES = 64 * 1024 * 1024
UPLOAD_PAGES_BYTES = {"upload": 64 * 1024 * 1024, "upload_long": 256 * 1024 * 1024}
# an answer's `notes` (a step's read kept apart: whether a thumbnail was taken) and `skipped` (the
# optional steps that did not happen), as the profile browser gave them, capped
NOTES = 10
NOTE_CHARS = 4000
PARTIAL_CHARS = 300


class JobFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    b64: str = Field(min_length=1)


class WebIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account: Account
    task: TaskName
    prompt: str = Field(min_length=1, max_length=PROMPT_CHARS)
    # prompt 22: what a lines step adds to a job (the prompt is then the text to speak, the
    # query to search or the cover's brief): the speaker, a style note, how many results, and
    # the files a cover is made from (named, base64; at most 10)
    voice: str | None = Field(default=None, min_length=1, max_length=80)
    style: str | None = Field(default=None, max_length=2000)
    limit: int = Field(default=10, ge=1, le=30)
    files: list[JobFile] = Field(default_factory=list, max_length=MAX_JOB_FILES)
    # ⟨2026-11-17⟩ an upload's description (YouTube: at most 5,000 characters; the title is the
    # prompt)
    description: str | None = Field(default=None, max_length=5000)
    # ⟨2026-11-17⟩ an upload's visibility (none: the upload stops before publishing) and the
    # uploaded video a later task acts on
    visibility: Literal["public", "unlisted"] | None = None
    video_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{11}$")
    # ⟨2026-11-17⟩ a long video's job: its files by name, already in the profile browser's spool
    # (the uploader copied them there; never base64 through two JSON hops), after `files` in the
    # job's file order; and its tags (comma-separated; YouTube: at most 500 characters)
    spooled: list[SpoolName] = Field(default_factory=list, max_length=MAX_JOB_FILES)
    tags: str | None = Field(default=None, max_length=500)
    timeout_s: int = Field(default=300, ge=10, le=1800)  # (⟨2026-11-17⟩ slides: up to 25 min)
    # ⟨1.10⟩ §28.4 the hub's one retry after a recipe failure
    reload: bool = False


class LogoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account: Account


def failed(
    error: str,
    detail: str,
    *,
    step: str | None = None,
    version: str | None = None,
    screenshot: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    assert error in ERRORS
    body: dict[str, Any] = {
        "ok": False,
        "error": error,
        "detail": scrub(detail)[:DETAIL_CHARS],
        "step": step,
        "recipe_version": version,
    }
    if screenshot is not None and error == "recipe_failed":
        body["screenshot"] = screenshot
    return JSONResponse({**body, **(extra or {})})


def extras(got: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    """⟨2026-11-17⟩ What a job says beside its answer: `notes` (named reads), `skipped` (the
    optional steps that did not happen) and, for a failed job, `partial` (the text read before it
    failed: an upload's link), each masked and capped; nothing when the job said none."""
    out: dict[str, Any] = {}
    notes = got.get("notes")
    if isinstance(notes, dict):
        kept = {
            str(k): scrub(str(v))[:NOTE_CHARS]
            for k, v in list(notes.items())[:NOTES]
            if re.fullmatch(NOTE, str(k))
        }
        if kept:
            out["notes"] = kept
    skipped = got.get("skipped")
    if isinstance(skipped, list) and skipped:
        out["skipped"] = [str(x)[:60] for x in skipped[:50]]
    text = got.get("partial")
    if partial and isinstance(text, str) and text:
        out["partial"] = scrub(text)[:PARTIAL_CHARS]
    return out


def screenshot_of(got: dict[str, Any]) -> dict[str, str] | None:
    """The profile browser's screenshot, checked by content: a JPEG or PNG
    of at most SCREENSHOT_BYTES, else none."""
    shot = got.get("screenshot")
    if not isinstance(shot, dict):
        return None
    try:
        data = base64.b64decode(str(shot.get("b64") or ""), validate=True)
    except ValueError:
        return None
    mime = sniff(data) if data and len(data) <= SCREENSHOT_BYTES else None
    if mime not in ("image/jpeg", "image/png"):
        return None
    return {"mime": mime, "b64": base64.b64encode(data).decode()}


@router.post("/v1/substitutes/web")
async def web(a: WebIn, request: Request) -> JSONResponse:
    state = request.app.state.egress
    s = state.settings
    recipe = state.recipes.get(a.account)
    if recipe is None:
        return failed("off", "no reviewed recipe for this account")
    version = recipe.version
    if a.task not in recipe.tasks:
        return failed("recipe_failed", f"the recipe has no {a.task} task", version=version)
    if (a.files or a.spooled) and not any(st.do == "attach" for st in recipe.tasks[a.task].steps):
        return failed(
            "unsupported",
            f"the recipe's {a.task} task cannot attach files",
            step="attach",
            version=version,
        )
    # ⟨2026-11-17⟩ an upload's video may be over the usual cap (its own, TASK_FILE_BYTES)
    file_cap = max(s.web_file_bytes, TASK_FILE_BYTES.get(a.task, 0))
    if any(len(f.b64) * 3 // 4 > file_cap for f in a.files):
        return failed("unsupported", "a file is over its cap", step="attach", version=version)
    if len(a.files) + len(a.spooled) > MAX_JOB_FILES:
        return failed("unsupported", "too many files", step="attach", version=version)
    lock = state.web_locks[a.account]
    if lock.locked():
        return failed("busy", "one job per account at a time", version=version)
    job = recipe.for_job(a.task)
    timeout = min(float(a.timeout_s), float(job["timeout_s"]))
    async with lock:
        key, password = state.buckets.open(
            "substitute.web",
            "A2",
            # the pages and the file (⟨2026-11-17⟩ a set of slides: each of its pictures; a long
            # video: each spooled file, at most its cap)
            # (an upload: the video going out, and Studio's own heavy pages)
            file_cap * (MAX_IMAGES if a.task == "slides" else max(1, len(a.spooled)))
            + PAGES_BYTES
            + UPLOAD_PAGES_BYTES.get(a.task, 0),
            site=recipe.site,
            hosts=recipe.own_hosts(),
            ttl_s=timeout + 120,
        )
        payload = {
            "account": a.account,
            "recipe": job,
            # The api masked it already; masked again here, whatever came.
            "prompt": scrub(a.prompt),
            "timeout_s": timeout,
            "proxy": {"server": s.web_proxy_url, "username": key, "password": password},
            "max_file_bytes": file_cap,
            "reload": a.reload,
            "voice": a.voice,
            "style": scrub(a.style) if a.style else None,
            "limit": a.limit,
            "files": [f.model_dump() for f in a.files],
            "description": scrub(a.description) if a.description else None,
            "visibility": a.visibility,
            "video_id": a.video_id,
            # (only when the job has them: an older profile browser refuses fields it lacks)
            **({"spooled": list(a.spooled)} if a.spooled else {}),
            **({"tags": scrub(a.tags)} if a.tags else {}),
        }
        start = time.monotonic()
        try:
            resp = await state.internal.post(
                s.web_browser_url.rstrip("/") + "/v1/job", json=payload, timeout=timeout + 30
            )
            got = resp.json() if resp.status_code in (200, 503) else None
        except (httpx.HTTPError, ValueError):
            got = None
        finally:
            _log_entries(a.account, state.buckets.drain(key), time.monotonic() - start)
    return _job_answer(got, version, s.web_file_bytes)


def _job_answer(got: Any, version: str, max_bytes: int) -> JSONResponse:
    if not isinstance(got, dict):
        return failed("off", "the profile browser is not running", version=version)
    if got.get("ok") is not True:
        err = str(got.get("error") or "recipe_failed")
        err = err if err in ERRORS else "recipe_failed"
        step = got.get("step")
        return failed(
            err,
            str(got.get("detail") or err),
            step=str(step)[:60] if step is not None else None,
            version=version,
            screenshot=screenshot_of(got) if err == "recipe_failed" else None,
            extra=extras(got, partial=True),
        )
    text = got.get("text_md")
    file = got.get("file") if isinstance(got.get("file"), dict) else None
    # ⟨2026-11-17⟩ a set of slides: every picture checked as the one file is
    many = [f for f in got.get("files") or [] if isinstance(f, dict)][:MAX_IMAGES]
    files: list[dict[str, str]] = []
    for one in many or ([file] if file is not None else []):
        try:
            data = base64.b64decode(str(one.get("b64") or ""), validate=True)
        except ValueError:
            return failed("recipe_failed", "the file was not readable", version=version)
        if not data or len(data) > max_bytes:
            return failed("recipe_failed", "no file, or one over its cap", version=version)
        mime = sniff(data)
        if mime is None:
            return failed(
                "recipe_failed",
                "the download is not an image, a video or an audio file",
                version=version,
            )
        name = str(one.get("name") or "file")[:120]
        files.append({"name": name, "mime": mime, "b64": base64.b64encode(data).decode()})
    file = files[0] if files else None
    if text is None and file is None:
        return failed("recipe_failed", "the recipe read nothing", version=version)
    return JSONResponse(
        {
            "ok": True,
            # ⟨1.10.1⟩ whole (the profile browser reads up to READ_CHARS; the hub keeps a
            # long answer in its file store)
            "text_md": scrub(str(text)) if text is not None else None,
            "file": file,
            **({"files": files} if many else {}),
            "recipe_version": version,
            **extras(got),
        }
    )


def sniff(data: bytes) -> str | None:
    """The type by content (never by the site's name or header): the
    processing of §17.1 checks it again before anything uses the file."""
    head = data[:16]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    if head[:4] == b"OggS":
        return "audio/ogg"
    if head[:4] == b"fLaC":
        return "audio/flac"
    if head[4:8] == b"ftyp":
        return "video/mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    return None


@router.post("/v1/substitutes/web/logout")
async def web_logout(a: LogoutIn, request: Request) -> JSONResponse:
    state = request.app.state.egress
    s = state.settings
    async with state.web_locks[a.account]:
        try:
            resp = await state.internal.post(
                s.web_browser_url.rstrip("/") + "/v1/logout",
                json={"account": a.account},
                timeout=30,
            )
            got = resp.json() if resp.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            got = None
    if not isinstance(got, dict) or got.get("ok") is not True:
        return JSONResponse({"ok": False, "error": "off"})
    log.info("web profile wiped", extra={"account": a.account})
    return JSONResponse({"ok": True})


def _log_entries(account: str, entries: list[Entry], seconds: float) -> None:
    """A web job's connections in egress's own log: hosts and sizes only."""
    hosts = sorted({e.host for e in entries})[:20]
    blocked = sorted({f"{e.host}:{e.blocked_reason}" for e in entries if e.blocked_reason})[:20]
    log.info(
        "substitute web job",
        extra={
            "account": account,
            "connections": len(entries),
            "hosts": hosts,
            "blocked": blocked,
            "bytes_in": sum(e.bytes_in for e in entries),
            "bytes_out": sum(e.bytes_out for e in entries),
            "s": round(seconds, 1),
        },
    )


async def profile_browse(state: Any, a: Any) -> JSONResponse:
    """web.browse with a signed-in profile's account: its steps in that
    profile, in the profile browser, on the recipe's own hosts only (any other
    host is refused before the browser starts, and by the bucket after)."""
    from hq_egress.app import _host, _secrets, answer, browse_result  # here: app imports us

    s = state.settings
    recipe = state.recipes.get(a.account.key)
    first = next((st.url for st in a.steps if st.url), None) or "about:blank"
    if recipe is None:
        e = track(Entry("web.browse", "BROWSE", _host(first), kind="browse", cls=a.ctx.cls,
                        blocked_reason="policy_denied"))  # fmt: skip
        return answer("blocked", None, [e], "policy_denied")
    own = recipe.own_hosts()
    for i, st in enumerate(a.steps):
        if not st.url:
            continue
        host = (urlsplit(st.url).hostname or "").lower().rstrip(".")
        try:
            if not st.url.startswith("https://") or not covered(host, own):
                raise Blocked("host_not_allowed")
            state.guard.target(st.url)
            why = get_commitment(st.url)
            if why:
                raise Blocked("needs_owner", why)
        except Blocked as b:
            e = track(Entry("web.browse", "GOTO", _host(st.url), kind="browse", cls=a.ctx.cls,
                            blocked_reason=b.reason))  # fmt: skip
            data = {"step": i, "code": b.reason}
            return answer("blocked", data, [e], b.reason)
    lock = state.web_locks.get(a.account.key)
    if lock is not None and lock.locked():
        e = track(Entry("web.browse", "BROWSE", _host(first), kind="browse", cls=a.ctx.cls))
        e.status = 503
        return answer("error", None, [e], "browser_busy")
    secrets = _secrets(a)
    time_s = max(1.0, min(a.time_s, s.browse_call_s, s.call_deadline_s - 4))
    key, password = state.buckets.open(
        "web.browse", a.ctx.cls, a.ctx.max_bytes, site=recipe.site, hosts=own
    )
    payload = {
        "profile": a.account.key,
        "allowed_hosts": sorted(own),
        "steps": [st.model_dump(exclude_none=True) for st in a.steps],
        "proxy": {"server": s.web_proxy_url, "username": key, "password": password},
        "account": a.account.model_dump(),
        "time_s": time_s,
        "max_download_bytes": min(a.ctx.max_bytes, s.max_call_bytes),
        "max_files_bytes": min(a.ctx.max_bytes, s.browse_files_bytes),
    }
    session = track(Entry("web.browse", "BROWSE", _host(first), kind="browse", cls=a.ctx.cls))
    start = time.monotonic()
    got: Any = None
    try:
        if lock is not None:
            async with lock:
                got = await _post_run(state, payload, time_s + 10)
        else:
            got = await _post_run(state, payload, time_s + 10)
    finally:
        entries = [track(e) for e in state.buckets.drain(key)]
        session.ms = int((time.monotonic() - start) * 1000)
    return browse_result(got, [session, *entries], session, secrets)


async def _post_run(state: Any, payload: dict[str, Any], timeout: float) -> Any:  # noqa: ASYNC109
    try:
        resp = await state.internal.post(
            state.settings.web_browser_url.rstrip("/") + "/v1/run", json=payload, timeout=timeout
        )
    except httpx.HTTPError:
        return None
    try:
        return resp.json() if resp.status_code in (200, 503) else None
    except ValueError:
        return None
