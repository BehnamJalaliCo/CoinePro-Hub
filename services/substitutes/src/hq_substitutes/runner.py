"""One job of a substitute player (contract §21.13; the interface of prompt 12
§9.1 between the api and the host dispatcher).

    job = parse_job(first stdin line)
    for event in run(job, Settings.from_env(), more_lines): print(json.dumps(event))

Kinds:
- `call`: the seat's masked question to the CLI, the prompt on the CLI's own
  stdin (never in argv). Codex runs `codex exec --json` in its read-only
  sandbox, in the empty working directory (a code review: the read-only
  checkout); Gemini runs headless with a system settings file that registers
  no core tool (a code review: the read-only file tools only).
- `models`: what the CLI offers under the subscription. Codex: its model
  catalog as the account sees it (`codex debug models`, the `list` ones).
  Gemini has no listing: one job probes the one `model` it names with a word.
- `login`: the CLI's own headless sign-in under a pseudo terminal. Codex: its
  device code (`codex login --device-auth`); Gemini: its browserless
  authorization code (NO_BROWSER), the owner's code then arriving as one more
  stdin line `{"code": ...}` from the dispatcher. Never printed or logged.
- `logout`: the stored sign-in removed.

Every outcome ends in exactly one `done` event; a CLI's own words never reach
it but as a short, scrubbed reason (no token, no code, no prompt).
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import pty
import re
import select
import signal
import subprocess
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from hq_common.redact import scrub

KINDS = ("call", "login", "logout", "models")
RUNNERS = ("codex_cli", "gemini_cli")
PLAYERS = {"codex_cli": "gpt", "gemini_cli": "gemini"}
SEVERITIES = ("low", "medium", "high", "critical")
MAX_INPUT = 400_000  # characters of a masked question (a long read)
MAX_OUTPUT = 200_000  # characters read back from a CLI
MAX_FINDINGS = 50
REASON_CHARS = 200
LOGIN_URL_WAIT_S = 90.0
# The one constant instruction on Gemini's command line: the question itself
# arrives on stdin (Gemini appends stdin to -p).
GEMINI_PROMPT = "Answer the request given on standard input."
ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,80}$")
URL = re.compile(r"https://[A-Za-z0-9.-]+(?:/[^\s\x1b\"'<>]*)?")
USER_CODE = re.compile(r"\b([A-Z0-9]{4,5}-[A-Z0-9]{4,5})\b")
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[@-Z\\-_]")
LIMIT_WORDS = (
    "usage limit",
    "rate limit",
    "rate_limit",
    "quota",
    "resource_exhausted",
    "resource exhausted",
    "too many requests",
    "429",
)
SIGNED_OUT_WORDS = (
    "not logged in",
    "login required",
    "log in",
    "please login",
    "sign in",
    "unauthenticated",
    "unauthorized",
    "401",
    "manual authorization is required",
    "please set an auth method",
    "invalid_grant",
    "token has been expired or revoked",
    "refresh token",
)
MODEL_MISSING_WORDS = ("model not found", "not found", "unknown model", "not supported", "404")


class BadJob(ValueError):
    """The job line is not a job of this interface."""


@dataclass(frozen=True)
class Job:
    id: str
    kind: str
    player: str
    runner: str
    seat: str | None
    model: str | None
    input_md: str | None
    checkout: dict[str, str] | None
    login: dict[str, str] | None
    timeout_s: int


def parse_job(line: str) -> Job:
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as exc:
        raise BadJob("not JSON") from exc
    j = raw.get("job", raw) if isinstance(raw, dict) else None
    if not isinstance(j, dict):
        raise BadJob("not an object")
    kind, runner = j.get("kind"), j.get("runner")
    if kind not in KINDS or runner not in RUNNERS:
        raise BadJob("kind or runner")
    if not isinstance(j.get("id"), str) or not ID.fullmatch(j["id"]):
        raise BadJob("id")
    if j.get("player") != PLAYERS[runner]:
        raise BadJob("player")
    model = j.get("model")
    if model is not None and (not isinstance(model, str) or not MODEL.fullmatch(model)):
        raise BadJob("model")
    text = j.get("input_md")
    if text is not None and (not isinstance(text, str) or len(text) > MAX_INPUT):
        raise BadJob("input_md")
    if kind == "call" and not text:
        raise BadJob("a call needs its input")
    checkout = j.get("checkout")
    if checkout is not None and not (
        isinstance(checkout, dict)
        and isinstance(checkout.get("repo"), str)
        and re.fullmatch(r"^[0-9a-f]{7,64}$", str(checkout.get("head_sha", "")))
    ):
        raise BadJob("checkout")
    login = j.get("login")
    if kind == "login" and not (isinstance(login, dict) and ID.fullmatch(str(login.get("id", "")))):
        raise BadJob("login")
    timeout = j.get("timeout_s", 300)
    if not isinstance(timeout, int) or not 5 <= timeout <= 1800:
        raise BadJob("timeout_s")
    seat = j.get("seat")
    return Job(
        id=j["id"],
        kind=kind,
        player=j["player"],
        runner=runner,
        seat=seat if isinstance(seat, str) else None,
        model=model,
        input_md=text,
        checkout=checkout,
        login=login if kind == "login" else None,
        timeout_s=timeout,
    )


@dataclass(frozen=True)
class Settings:
    codex_bin: str = "codex"
    gemini_bin: str = "gemini"
    gemini_etc: Path = Path("/etc/gemini-cli")
    auth_dir: Path = Path("/auth")
    work_dir: Path = Path("/work")
    checkout_dir: Path = Path("/checkout")
    schema_dir: Path = Path("/app/substitutes/schemas")

    @classmethod
    def from_env(cls) -> Settings:
        e = os.environ
        return cls(
            codex_bin=e.get("HQ_CODEX_BIN", "codex"),
            gemini_bin=e.get("HQ_GEMINI_BIN", "gemini"),
            gemini_etc=Path(e.get("HQ_GEMINI_ETC", "/etc/gemini-cli")),
            auth_dir=Path(e.get("HQ_SUBSTITUTE_AUTH", "/auth")),
            work_dir=Path(e.get("HQ_SUBSTITUTE_WORK", "/work")),
            checkout_dir=Path(e.get("HQ_SUBSTITUTE_CHECKOUT", "/checkout")),
            schema_dir=Path(e.get("HQ_SUBSTITUTE_SCHEMAS", "/app/substitutes/schemas")),
        )


def done(
    ok: bool,
    *,
    text_md: str | None = None,
    findings: list[dict[str, Any]] | None = None,
    usage: dict[str, Any] | None = None,
    error: str | None = None,
    limited_until: str | None = None,
    status_reason: str | None = None,
    models: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "event": "done",
        "ok": ok,
        "text_md": text_md,
        "findings": findings,
        "usage": usage,
        "error": None if ok else (error or "failed"),
        "limited_until": limited_until,
        "status_reason": _reason(status_reason) if status_reason else None,
        "models": models,
    }


def _reason(text: str) -> str:
    """A short, scrubbed reason: never a token, a code or the prompt."""
    clean = scrub(ANSI.sub("", text)).replace("\n", " ").strip()
    return clean[:REASON_CHARS]


# ------------------------------------------------------------------ the env --
def _env(job: Job, s: Settings, *, review: bool = False) -> dict[str, str]:
    """A small, fixed environment for the CLI (nothing of the container's own)."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "TERM": "dumb",
        "NO_COLOR": "1",
        "NO_UPDATE_NOTIFIER": "1",
        "HOME": str(s.work_dir / ".home"),
    }
    if job.runner == "codex_cli":
        env["CODEX_HOME"] = str(s.auth_dir / "codex")
    else:
        env["GEMINI_CLI_HOME"] = str(s.auth_dir / "gemini")
        env["NO_BROWSER"] = "true"
        name = "review.json" if review else "settings.json"
        env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"] = str(s.gemini_etc / name)
    return env


def _prepare(job: Job, s: Settings) -> None:
    os.umask(0o077)  # every file the CLI writes (its sign-in too) is 600
    for d in (s.work_dir / ".home", s.auth_dir / "codex", s.auth_dir / "gemini"):
        try:
            d.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError:
            continue


def estimate(text: str | None) -> int:
    return math.ceil(len(text or "") / 4)


# ------------------------------------------------------------------ errors --
def classify(text: str) -> str:
    low = text.lower()
    if any(w in low for w in LIMIT_WORDS):
        return "limited"
    if any(w in low for w in SIGNED_OUT_WORDS):
        return "signed_out"
    return "failed"


_AGAIN_AT = re.compile(r"try again (?:at|after)\s+(\d{1,2}):(\d{2})\s*([ap]m)?", re.I)
_AGAIN_IN = re.compile(
    r"(?:try again|resets?|reset)\s+in\s+(?:about\s+)?(\d+(?:\.\d+)?)\s*"
    r"(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d)\b",
    re.I,
)
_RETRY_AFTER = re.compile(r"retry[- ]after[\"':= ]+(\d{1,6})", re.I)


def limited_until(text: str, now: datetime | None = None) -> str | None:
    """When a quota message says the limit lifts, as an ISO time (UTC)."""
    now = now or datetime.now(UTC)
    m = _AGAIN_IN.search(text)
    if m:
        n, unit = float(m.group(1)), m.group(2).lower()[0]
        secs = n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
        return (now + timedelta(seconds=secs)).replace(microsecond=0).isoformat()
    m = _RETRY_AFTER.search(text)
    if m:
        return (now + timedelta(seconds=int(m.group(1)))).replace(microsecond=0).isoformat()
    m = _AGAIN_AT.search(text)
    if m:
        hour, minute, half = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
        if half == "pm" and hour < 12:
            hour += 12
        if half == "am" and hour == 12:
            hour = 0
        if hour > 23 or minute > 59:
            return None
        at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if at <= now:
            at += timedelta(days=1)
        return at.isoformat()
    return None


def _failure(text: str, *, model_probe: bool = False) -> dict[str, Any]:
    kind = classify(text)
    if model_probe and kind == "failed" and any(w in text.lower() for w in MODEL_MISSING_WORDS):
        return done(True, models=[])
    return done(
        False,
        error=kind,
        limited_until=limited_until(text) if kind == "limited" else None,
        status_reason=f"{kind}: {text}",
    )


# --------------------------------------------------------------- processes --
@dataclass
class Ran:
    rc: int | None  # None: the timeout stopped it
    out: str
    err: str


def run_cli(argv: list[str], stdin: str, cwd: Path, env: dict[str, str], timeout: float) -> Ran:
    """One CLI process: `stdin` on its stdin (never in argv), its own process
    group, killed whole when it runs past `timeout`."""
    proc = subprocess.Popen(  # noqa: S603 - argv is ours, never the input
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
        start_new_session=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        out, err = proc.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill(proc)
        proc.communicate()
        return Ran(None, "", "")
    return Ran(proc.returncode, out[:MAX_OUTPUT], err[-20_000:])


def _kill(proc: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()


# ------------------------------------------------------------------- codex --
def codex_argv(job: Job, s: Settings, cwd: Path) -> list[str]:
    argv = [
        s.codex_bin,
        "exec",
        "--json",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--color",
        "never",
        "-C",
        str(cwd),
    ]
    if job.model:
        argv += ["-m", job.model]
    schema = s.schema_dir / "findings.json"
    if job.seat == "code_review" and schema.is_file():
        argv += ["--output-schema", str(schema)]
    return [*argv, "-"]  # the prompt from stdin


def parse_codex(out: str) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """(final text, usage, error) from `codex exec --json` (JSONL events).
    `error` events also report retries ("Reconnecting... 2/5"): only a turn
    without a final message, or a failed turn, is an error."""
    text: str | None = None
    usage = {"input_tokens": 0, "output_tokens": 0}
    seen = False
    errors: list[str] = []
    failed = False
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        t = str(ev.get("type", ""))
        raw_item = ev.get("item")
        item: dict[str, Any] = raw_item if isinstance(raw_item, dict) else {}
        if t == "item.completed" and item.get("type") in ("agent_message", "assistant_message"):
            text = str(item.get("text") or "")
        u = ev.get("usage")
        if t == "turn.completed" and isinstance(u, dict):
            seen = True
            usage["input_tokens"] += int(u.get("input_tokens") or 0)
            usage["output_tokens"] += int(u.get("output_tokens") or 0)
        if t in ("error", "turn.failed"):
            failed = failed or t == "turn.failed"
            raw_err = ev.get("error")
            err: dict[str, Any] = raw_err if isinstance(raw_err, dict) else ev
            errors.append(str(err.get("message") or t))
    error = " | ".join(errors) if errors and (failed or text is None) else None
    return text, (usage if seen else None), error


# ------------------------------------------------------------------ gemini --
def gemini_argv(job: Job, s: Settings) -> list[str]:
    argv = [s.gemini_bin, "-p", GEMINI_PROMPT, "-o", "json", "--approval-mode", "plan"]
    if job.model:
        argv += ["-m", job.model]
    return argv


def parse_gemini(out: str) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """(response, usage, error) from `gemini -o json`."""
    start = out.find("{")
    try:
        data = json.loads(out[start:]) if start >= 0 else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return None, None, out.strip()[-500:] or "no output"
    err = data.get("error")
    if isinstance(err, dict):
        return None, None, str(err.get("message") or err.get("type") or "error")
    usage = None
    models = (
        (data.get("stats") or {}).get("models") if isinstance(data.get("stats"), dict) else None
    )
    if isinstance(models, dict) and models:
        inp = out_t = 0
        for m in models.values():
            tok = m.get("tokens") if isinstance(m, dict) else None
            if isinstance(tok, dict):
                inp += int(tok.get("prompt") or tok.get("input") or 0)
                out_t += int(tok.get("candidates") or 0) + int(tok.get("thoughts") or 0)
        usage = {"input_tokens": inp, "output_tokens": out_t}
    resp = data.get("response")
    return (str(resp) if resp is not None else None), usage, None


# ---------------------------------------------------------------- findings --
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def findings_of(text: str) -> list[dict[str, Any]]:
    """The review's findings: `{findings: [...]}` or `[...]`, in the text or
    in a fenced block; malformed items dropped, at most MAX_FINDINGS."""
    candidates = [text, *(m.group(1) for m in _FENCE.finditer(text))]
    for lo, hi in (("{", "}"), ("[", "]")):
        a, b = text.find(lo), text.rfind(hi)
        if 0 <= a < b:
            candidates.append(text[a : b + 1])
    for c in candidates:
        try:
            data = json.loads(c)
        except (json.JSONDecodeError, TypeError):
            continue
        items = data.get("findings") if isinstance(data, dict) else data
        if isinstance(items, list):
            return [f for f in (_finding(i) for i in items) if f][:MAX_FINDINGS]
    return []


def _finding(i: Any) -> dict[str, Any] | None:
    if not isinstance(i, dict):
        return None
    path, line, sev = i.get("path"), i.get("line"), str(i.get("severity", "")).lower()
    title, detail = i.get("title_fa") or i.get("title"), i.get("detail_md") or i.get("detail")
    if not isinstance(path, str) or not path or len(path) > 500 or path.startswith("/"):
        return None
    if ".." in path.split("/"):
        return None
    if isinstance(line, bool) or not isinstance(line, int) or line < 0:
        return None
    if sev not in SEVERITIES or not isinstance(title, str) or not title.strip():
        return None
    return {
        "path": path,
        "line": line,
        "severity": sev,
        "title_fa": scrub(title.strip())[:200],
        "detail_md": scrub(str(detail or ""))[:4000],
    }


# --------------------------------------------------------------------- run --
def run(job: Job, s: Settings, more: Iterable[str] = ()) -> Iterator[dict[str, Any]]:
    _prepare(job, s)
    if job.kind == "call":
        yield _call(job, s)
    elif job.kind == "models":
        yield _models(job, s)
    elif job.kind == "logout":
        yield _logout(job, s)
    else:
        yield from _login(job, s, iter(more))


def _cwd(job: Job, s: Settings) -> Path | None:
    if job.checkout is None:
        return s.work_dir
    d = s.checkout_dir
    try:
        if d.is_dir() and any(d.iterdir()):
            return d
    except OSError:
        return None
    return None


def signed_in(job: Job, s: Settings) -> bool:
    """Whether the CLI has a stored sign-in: without one it is never started
    (signed out, Codex would fall back to the API host and Gemini would ask
    for a sign-in it cannot get here)."""
    if job.runner == "codex_cli":
        creds = s.auth_dir / "codex" / "auth.json"
    else:
        creds = s.auth_dir / "gemini" / ".gemini" / "oauth_creds.json"
    try:
        return creds.is_file() and creds.stat().st_size > 0
    except OSError:
        return False


def _call(job: Job, s: Settings) -> dict[str, Any]:
    if not signed_in(job, s):
        return done(False, error="signed_out", status_reason="no stored sign-in")
    cwd = _cwd(job, s)
    if cwd is None:
        return done(False, error="no_access", status_reason="no checkout for this repository")
    review = job.seat == "code_review" and job.checkout is not None
    if job.runner == "codex_cli":
        argv = codex_argv(job, s, cwd)
        parse = parse_codex
    else:
        argv = gemini_argv(job, s)
        parse = parse_gemini
    ran = run_cli(argv, job.input_md or "", cwd, _env(job, s, review=review), job.timeout_s)
    if ran.rc is None:
        return done(False, error="timeout", status_reason="the CLI ran past its timeout")
    text, usage, error = parse(ran.out)
    if error or ran.rc != 0 or text is None:
        return _failure(
            " | ".join(x for x in (error, ran.err.strip()[-2000:]) if x) or f"exit {ran.rc}"
        )
    estimated = usage is None
    if usage is None:
        usage = {"input_tokens": estimate(job.input_md), "output_tokens": estimate(text)}
    findings = findings_of(text) if job.seat == "code_review" else None
    return done(
        True,
        text_md=scrub(text)[:MAX_OUTPUT],
        findings=findings,
        usage={**usage, "estimated": estimated},
    )


def _models(job: Job, s: Settings) -> dict[str, Any]:
    if not signed_in(job, s):
        return done(False, error="signed_out", status_reason="no stored sign-in")
    if job.runner == "codex_cli":
        ran = run_cli([s.codex_bin, "debug", "models"], "", s.work_dir, _env(job, s), job.timeout_s)
        if ran.rc is None:
            return done(False, error="timeout", status_reason="the model listing ran too long")
        if ran.rc != 0:
            return _failure(ran.err or ran.out or f"exit {ran.rc}")
        try:
            data = json.loads(ran.out[ran.out.find("{") :])
        except json.JSONDecodeError:
            return done(False, error="failed", status_reason="the model listing was not JSON")
        items = data.get("models") if isinstance(data, dict) else None
        slugs = [
            str(m["slug"])
            for m in items or []
            if isinstance(m, dict) and m.get("slug") and m.get("visibility", "list") == "list"
        ]
        return done(True, models=sorted(set(slugs)))
    if not job.model:
        return done(
            False,
            error="not_ready",
            status_reason="Gemini CLI has no model listing: one job probes one model",
        )
    probe = Job(**{**job.__dict__, "kind": "call", "input_md": "ok", "seat": None})
    ran = run_cli(gemini_argv(probe, s), "Reply with the word ok.", s.work_dir, _env(job, s), 60)
    if ran.rc is None:
        return done(False, error="timeout", status_reason="the model probe ran too long")
    text, _usage, error = parse_gemini(ran.out)
    if error or ran.rc != 0 or text is None:
        return _failure(error or ran.err or f"exit {ran.rc}", model_probe=True)
    return done(True, models=[job.model])


def _logout(job: Job, s: Settings) -> dict[str, Any]:
    if job.runner == "codex_cli":
        ran = run_cli([s.codex_bin, "logout"], "", s.work_dir, _env(job, s), 30)
        gone = [s.auth_dir / "codex" / "auth.json"]
    else:
        ran = Ran(0, "", "")
        gone = [
            s.auth_dir / "gemini" / ".gemini" / n
            for n in ("oauth_creds.json", "google_accounts.json")
        ]
    for f in gone:
        try:
            f.unlink(missing_ok=True)
        except OSError:
            return done(
                False, error="failed", status_reason="the stored sign-in could not be removed"
            )
    if ran.rc is None:
        return done(False, error="timeout", status_reason="sign-out ran too long")
    return done(True)


# ------------------------------------------------------------------- login --
def _login(job: Job, s: Settings, more: Iterator[str]) -> Iterator[dict[str, Any]]:
    """The CLI's own headless sign-in, under a pseudo terminal (Gemini asks for
    its code only on a terminal). What it prints is read for the URL (and the
    device code); nothing of it is printed back but those two."""
    assert job.login is not None
    if job.runner == "codex_cli":
        argv, method = [s.codex_bin, "login", "--device-auth"], "device_code"
    else:
        argv, method = [s.gemini_bin], "auth_code"
    env = {**_env(job, s), "TERM": "xterm"}
    session = Pty(argv, s.work_dir, env)
    deadline = time.monotonic() + job.timeout_s
    try:
        url, code = session.read_until_url(
            min(deadline, time.monotonic() + LOGIN_URL_WAIT_S), method == "device_code"
        )
        if url is None:
            session.close()
            yield _login_failure(session.seen, "the CLI offered no headless sign-in")
            return
        yield {
            "event": "login_started",
            "method": method,
            "verification_url": url,
            "user_code": code if method == "device_code" else None,
        }
        if method == "auth_code":
            pasted = _owner_code(more)
            if pasted is None:
                session.close()
                yield done(False, error="timeout", status_reason="no code arrived")
                return
            session.write(pasted + "\r")
            del pasted
        yield session.wait_signed_in(job, s, deadline)
    finally:
        session.close()


def _owner_code(more: Iterator[str]) -> str | None:
    """The next stdin line {"code": ...} (the dispatcher's relay of the
    owner's pasted code), or None (no line, or {"cancel": true})."""
    for line in more:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        code = msg.get("code") if isinstance(msg, dict) else None
        if isinstance(code, str) and 4 <= len(code) <= 512 and code.isprintable():
            return code.strip()
        return None
    return None


def _login_failure(seen: str, default: str) -> dict[str, Any]:
    kind = classify(seen) if seen else "failed"
    if kind == "failed":
        return done(False, error="not_ready", status_reason=default)
    return done(False, error=kind, status_reason=f"{kind} while signing in")


class Pty:
    """A process on a pseudo terminal; its output kept only in memory."""

    def __init__(self, argv: list[str], cwd: Path, env: dict[str, str]) -> None:
        self.master, slave = pty.openpty()
        self.proc = subprocess.Popen(  # noqa: S603 - fixed argv
            argv,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=cwd,
            env=env,
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave)
        self.seen = ""

    def _read(self, until: float) -> bool:
        left = until - time.monotonic()
        if left <= 0:
            return False
        ready, _, _ = select.select([self.master], [], [], min(left, 1.0))
        if not ready:
            return self.proc.poll() is None
        try:
            chunk = os.read(self.master, 65536)
        except OSError:
            return False
        if not chunk:
            return False
        self.seen = (self.seen + ANSI.sub("", chunk.decode("utf-8", "replace")))[-50_000:]
        return True

    def read_until_url(self, until: float, want_code: bool) -> tuple[str | None, str | None]:
        while time.monotonic() < until:
            url = URL.search(self.seen)
            code = USER_CODE.search(self.seen) if want_code else None
            if url and (code or not want_code):
                rest = self.seen[url.end() :]
                if want_code or "authorization code" in rest.lower() or "code:" in rest.lower():
                    return url.group(0).rstrip(".,)"), code.group(1) if code else None
            if not self._read(until) and self.proc.poll() is not None:
                break
        url = URL.search(self.seen)
        code = USER_CODE.search(self.seen) if want_code else None
        if url and (code or not want_code):
            return url.group(0).rstrip(".,)"), code.group(1) if code else None
        return None, None

    def write(self, text: str) -> None:
        os.write(self.master, text.encode())

    def wait_signed_in(self, job: Job, s: Settings, deadline: float) -> dict[str, Any]:
        """Done when the CLI stored its sign-in (Gemini's creds file; Codex's
        auth.json, or its own exit 0); failed when it says so."""
        creds = (
            s.auth_dir / "codex" / "auth.json"
            if job.runner == "codex_cli"
            else s.auth_dir / "gemini" / ".gemini" / "oauth_creds.json"
        )
        mark = len(self.seen)
        while time.monotonic() < deadline:
            if creds.is_file() and creds.stat().st_size > 0:
                return done(True)
            rc = self.proc.poll()
            if rc is not None:
                if rc == 0 and job.runner == "codex_cli":
                    return done(True)
                return _login_failure(self.seen[mark:], "the sign-in did not complete")
            if "failed to authenticate" in self.seen[mark:].lower():
                return done(False, error="failed", status_reason="the code was not accepted")
            self._read(deadline)
        return done(False, error="timeout", status_reason="the sign-in was not completed in time")

    def close(self) -> None:
        if self.proc.poll() is None:
            _kill(self.proc)
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.proc.wait(timeout=5)
        with contextlib.suppress(OSError):
            os.close(self.master)
