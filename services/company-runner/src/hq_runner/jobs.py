"""Job kinds (contract §26.2, §26.1b) except `map` (inventory.py) and
`claude` (claude_job.py).

A handler returns a JobResult. Its `output` (map, file, publish answer,
network check, Claude session) goes back as `data` of
POST …/result {exit_code, summary_fa, usage?, data?}.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import hashlib
import ipaddress
import json
import os
import shutil
import socket
import tempfile
import time
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hq_runner.config import Config
from hq_runner.events import EventSink
from hq_runner.hub import Hub, HubError
from hq_runner.mask import Masker, StreamMasker
from hq_runner.net import tcp_probe
from hq_runner.proc import LineFn, ProcResult, capture, run_streamed

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PUBLISH_FILE_BYTES = 1024 * 1024 * 1024
EXEC_DEFAULT_TIMEOUT_S = 600
EXEC_MAX_TIMEOUT_S = 3600
PUBLISH_DEFAULT_TIMEOUT_S = 900
NETCHECK_TIMEOUT_S = 3.0


class JobError(Exception):
    """A job that cannot run as asked; its message is the Persian summary."""

    def __init__(self, summary_fa: str, exit_code: int = 2):
        super().__init__(summary_fa)
        self.summary_fa = summary_fa
        self.exit_code = exit_code


@dataclass
class JobResult:
    exit_code: int
    summary_fa: str
    usage: dict[str, Any] | None = None
    output: dict[str, Any] | None = None


@dataclass
class JobContext:
    job: dict[str, Any]
    hub: Hub
    sink: EventSink
    cancel: asyncio.Event
    masker: Masker
    cfg: Config
    cfg_path: Path | None = None
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))

    @property
    def id(self) -> str:
        return str(self.job["id"])

    @property
    def args(self) -> dict[str, Any]:
        a = self.job.get("args")
        return a if isinstance(a, dict) else {}

    @property
    def via(self) -> str:
        return self.hub.route.via

    def line_sink(self, type_: str) -> LineFn:
        sm = StreamMasker(self.masker)

        def on_line(line: str) -> None:
            self.sink.emit(type_, {"text": sm.line(line)})

        return on_line


Handler = Callable[[JobContext], Coroutine[Any, Any, JobResult]]


def _timeout(args: dict[str, Any], default: int, maximum: int) -> int:
    raw = args.get("timeout_s", default)
    try:
        val = int(raw)
    except (TypeError, ValueError):
        raise JobError("timeout_s نامعتبر است.") from None
    return max(1, min(val, maximum))


def _cwd(raw: Any) -> str:
    path = Path(str(raw or "~")).expanduser()
    if not path.is_dir():
        raise JobError(f"پوشه‌ی کار پیدا نشد: {path}")
    return str(path)


def _summary(res: ProcResult, what: str) -> str:
    if res.reason == "timeout":
        return f"{what} به سقف زمان رسید و متوقف شد."
    if res.reason == "cancelled":
        return f"{what} لغو شد."
    if res.exit_code == 0:
        return f"{what} با موفقیت تمام شد."
    return f"{what} با کد خروج {res.exit_code} تمام شد."


# -- exec ----------------------------------------------------------------------------
async def run_exec(ctx: JobContext) -> JobResult:
    args = ctx.args
    cmd = args.get("cmd")
    if not isinstance(cmd, str) or not cmd.strip():
        raise JobError("دستوری برای اجرا داده نشده است.")
    timeout = _timeout(args, EXEC_DEFAULT_TIMEOUT_S, EXEC_MAX_TIMEOUT_S)
    argv = ["bash", "-lc", cmd]
    if args.get("sudo"):
        argv = ["sudo", "-n", "--", *argv]
    res = await run_streamed(
        argv,
        cwd=_cwd(args.get("cwd")),
        env=ctx.env,
        limit_s=timeout,
        cancel=ctx.cancel,
        on_stdout=ctx.line_sink("stdout"),
        on_stderr=ctx.line_sink("stderr"),
    )
    ctx.sink.emit("progress", {"exit": {"code": res.exit_code, "duration_ms": res.duration_ms}})
    return JobResult(res.exit_code, _summary(res, "دستور"))


# -- read / write ----------------------------------------------------------------------
def _file_path(args: dict[str, Any]) -> Path:
    raw = args.get("path")
    if not isinstance(raw, str) or not raw.strip():
        raise JobError("مسیر فایل داده نشده است.")
    return Path(raw).expanduser()


async def run_read(ctx: JobContext) -> JobResult:
    path = _file_path(ctx.args)
    try:
        st = path.stat()
    except FileNotFoundError:
        raise JobError(f"فایل پیدا نشد: {path}", 1) from None
    except PermissionError:
        raise JobError(f"اجازه‌ی خواندن این فایل نیست: {path}", 1) from None
    if not path.is_file():
        raise JobError(f"این مسیر فایل نیست: {path}", 1)
    if st.st_size > MAX_FILE_BYTES:
        raise JobError("فایل از سقف ۲۰ مگابایت بزرگ‌تر است.", 1)
    try:
        data = await asyncio.to_thread(path.read_bytes)
    except PermissionError:
        raise JobError(f"اجازه‌ی خواندن این فایل نیست: {path}", 1) from None
    out: dict[str, Any] = {
        "path": str(path),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mode": oct(st.st_mode & 0o7777),
        "modified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
    }
    try:
        out["encoding"], out["content"] = "utf8", data.decode("utf-8")
    except UnicodeDecodeError:
        out["encoding"], out["content"] = "base64", base64.b64encode(data).decode()
    return JobResult(0, f"فایل خوانده شد ({len(data)} بایت).", output=out)


def _write_content(args: dict[str, Any]) -> bytes:
    if isinstance(args.get("content_b64"), str):
        try:
            return base64.b64decode(args["content_b64"], validate=True)
        except (binascii.Error, ValueError):
            raise JobError("content_b64 معتبر نیست.") from None
    if isinstance(args.get("content"), str):
        if args.get("encoding") == "base64":
            try:
                return base64.b64decode(args["content"], validate=True)
            except (binascii.Error, ValueError):
                raise JobError("محتوای base64 معتبر نیست.") from None
        return str(args["content"]).encode("utf-8")
    raise JobError("محتوای فایل داده نشده است.")


def _write_file(path: Path, data: bytes, mode: int | None) -> str | None:
    backup: str | None = None
    old_mode: int | None = None
    if path.exists():
        if not path.is_file():
            raise JobError(f"این مسیر فایل نیست: {path}", 1)
        bak = path.with_name(path.name + ".hq-bak")
        shutil.copy2(path, bak)
        backup, old_mode = str(bak), path.stat().st_mode & 0o7777
    elif not path.parent.is_dir():
        raise JobError(f"پوشه‌ی فایل وجود ندارد: {path.parent}", 1)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".hq-tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode if mode is not None else (old_mode if old_mode is not None else 0o644))
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
    return backup


async def run_write(ctx: JobContext) -> JobResult:
    path = _file_path(ctx.args)
    data = _write_content(ctx.args)
    if len(data) > MAX_FILE_BYTES:
        raise JobError("محتوا از سقف ۲۰ مگابایت بزرگ‌تر است.", 1)
    mode: int | None = None
    if ctx.args.get("mode") is not None:
        try:
            raw_mode = ctx.args["mode"]
            mode = int(raw_mode, 8) if isinstance(raw_mode, str) else int(raw_mode)
        except (TypeError, ValueError):
            raise JobError("mode نامعتبر است.") from None
    try:
        backup = await asyncio.to_thread(_write_file, path, data, mode)
    except PermissionError:
        raise JobError(f"اجازه‌ی نوشتن این فایل نیست: {path}", 1) from None
    out = {
        "path": str(path),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "backup": backup,
    }
    note = " (نسخه‌ی قبلی در ‎.hq-bak ماند)" if backup else ""
    return JobResult(0, f"فایل نوشته شد{note}.", output=out)


# -- publish (§26.1b) ------------------------------------------------------------------
def parse_publish_answer(stdout_lines: list[str]) -> dict[str, Any] | None:
    """The last stdout line that is a JSON object with external_id."""
    for line in reversed(stdout_lines):
        s = line.strip()
        if not (s.startswith("{") and s.endswith("}")):
            continue
        try:
            obj = json.loads(s)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("external_id") not in (None, ""):
            return {"external_id": str(obj["external_id"]), "url": obj.get("url")}
    return None


async def run_publish(ctx: JobContext) -> JobResult:
    args = ctx.args
    command = args.get("command")
    if not isinstance(command, str) or not command.strip():
        raise JobError("دستور انتشار این سرور تعیین نشده است.")
    files = args.get("files") or []
    if not isinstance(files, list):
        raise JobError("فهرست فایل‌ها نامعتبر است.")
    timeout = _timeout(args, PUBLISH_DEFAULT_TIMEOUT_S, EXEC_MAX_TIMEOUT_S)
    workdir = Path(tempfile.mkdtemp(prefix="hq-publish-"))
    os.chmod(workdir, 0o700)
    try:
        paths: list[str] = []
        for i, f in enumerate(files, 1):
            url = f.get("url") if isinstance(f, dict) else f
            if not isinstance(url, str) or not url:
                raise JobError("نشانی یکی از فایل‌ها خالی است.")
            raw_name = (f.get("name") if isinstance(f, dict) else None) or Path(
                url.split("?")[0]
            ).name
            name = os.path.basename(str(raw_name)) or f"file-{i}"
            dest = workdir / f"{i:02d}-{name}"
            try:
                await ctx.hub.download(url, dest, MAX_PUBLISH_FILE_BYTES)
            except HubError as exc:
                raise JobError(
                    f"فایل {i} از ستاد گرفته نشد ({exc.code or exc.status}).", 1
                ) from exc
            ctx.sink.emit("progress", {"text": f"downloaded file {i}: {dest.name}"})
            paths.append(str(dest))
        caption = str(args.get("caption") or "")
        caption_file = workdir / "caption.txt"
        caption_file.write_text(caption, encoding="utf-8")
        env = dict(ctx.env)
        env.update(
            {
                "HQ_PUBLISH_DIR": str(workdir),
                "HQ_PUBLISH_FILES": "\n".join(paths),
                "HQ_PUBLISH_COUNT": str(len(paths)),
                "HQ_PUBLISH_CAPTION": caption,
                "HQ_PUBLISH_CAPTION_FILE": str(caption_file),
                "HQ_PUBLISH_META": json.dumps(args.get("meta") or {}, ensure_ascii=False),
                "HQ_JOB_ID": ctx.id,
            }
        )
        for i, p in enumerate(paths, 1):
            env[f"HQ_PUBLISH_FILE_{i}"] = p
        out_lines: list[str] = []
        to_hub = ctx.line_sink("stdout")

        def on_stdout(line: str) -> None:
            out_lines.append(line)
            del out_lines[:-50]
            to_hub(line)

        res = await run_streamed(
            ["bash", "-lc", command],
            cwd=_cwd(args.get("cwd")),
            env=env,
            limit_s=timeout,
            cancel=ctx.cancel,
            on_stdout=on_stdout,
            on_stderr=ctx.line_sink("stderr"),
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if res.exit_code != 0:
        return JobResult(res.exit_code, _summary(res, "انتشار"))
    answer = parse_publish_answer(out_lines)
    if answer is None:
        return JobResult(1, "دستور انتشار تمام شد ولی پاسخ {external_id, url} نداد.")
    return JobResult(0, "منتشر شد.", output=answer)


# -- netcheck (§26.6) -------------------------------------------------------------------
@dataclass
class Target:
    name: str
    ip: str
    ports: list[int]
    to: str | None = None  # the hub's key for the link, echoed back when given


def _port(p: Any) -> int:
    if isinstance(p, bool) or not isinstance(p, int) or not 0 < p < 65536:
        raise JobError(f"پورت نامعتبر: {p}")
    return p


def parse_targets(raw: Any) -> list[Target]:
    """§26.6 targets [{name, ip, ports}]; one-port items [{to, host, port}] are
    accepted too and grouped by address."""
    if not isinstance(raw, list) or len(raw) > 256:
        raise JobError("فهرست مقصدها نامعتبر است.")
    out: list[Target] = []
    by_key: dict[tuple[str, str], Target] = {}
    for t in raw:
        if not isinstance(t, dict):
            raise JobError("یکی از مقصدها نامعتبر است.")
        raw_ip = t.get("ip", t.get("host", ""))
        try:
            ip = str(ipaddress.ip_address(str(raw_ip).strip()))
        except ValueError:
            raise JobError(f"نشانی IP نامعتبر: {raw_ip}") from None
        if "ports" in t:
            ports_raw = t.get("ports") or []
            if not isinstance(ports_raw, list) or len(ports_raw) > 32:
                raise JobError("فهرست پورت‌ها نامعتبر است (حداکثر ۳۲).")
            ports = [_port(p) for p in ports_raw]
        else:
            ports = [_port(t.get("port"))]
        to = str(t["to"]) if t.get("to") is not None else None
        name = str(t.get("name") or to or ip)
        key = (name, ip)
        if key in by_key:
            by_key[key].ports += [p for p in ports if p not in by_key[key].ports]
            continue
        by_key[key] = Target(name, ip, ports, to)
        out.append(by_key[key])
    if sum(len(t.ports) for t in out) > 512:
        raise JobError("تعداد پورت‌ها بیش از اندازه است.")
    return out


async def ping(ip: str) -> tuple[bool, float | None, str | None] | None:
    """One ICMP echo with the system ping; None when ping is not available."""
    if not shutil.which("ping"):
        return None
    flag = "-6" if ":" in ip else "-4"
    start = time.monotonic()
    out = await capture(["ping", flag, "-n", "-c", "1", "-W", "2", ip], limit_s=5)
    ms = (time.monotonic() - start) * 1000
    if out is None:
        return False, None, "no reply"
    for part in out.split():
        if part.startswith("time="):
            with contextlib.suppress(ValueError):
                ms = float(part[5:])
    return True, round(ms, 1), None


async def run_netcheck(
    ctx: JobContext, probe: Callable[..., Awaitable[float]] = tcp_probe
) -> JobResult:
    """TCP connect to every port (3 s) and one ping per address where ping exists;
    the hub's private address is always included."""
    targets = parse_targets(ctx.args.get("targets", []))
    if ctx.cfg.hub_ip and not any(t.ip == ctx.cfg.hub_ip for t in targets):
        targets.insert(0, Target("hub", ctx.cfg.hub_ip, [ctx.hub.route.port]))
    limit = NETCHECK_TIMEOUT_S
    if ctx.args.get("timeout_ms") is not None:
        with contextlib.suppress(TypeError, ValueError):
            limit = min(10.0, max(0.5, float(ctx.args["timeout_ms"]) / 1000))
    sem = asyncio.Semaphore(16)

    def row(
        t: Target, port: int | None, ok: bool, ms: float | None, err: str | None
    ) -> dict[str, Any]:
        r: dict[str, Any] = {
            "name": t.name,
            "ip": t.ip,
            "port": port,
            "ok": ok,
            "ms": ms,
            "error": err,
        }
        if t.to is not None:
            r["to"] = t.to
        return r

    async def tcp(t: Target, port: int) -> dict[str, Any]:
        async with sem:
            try:
                ms = await probe(t.ip, port, limit)
                return row(t, port, True, round(ms, 1), None)
            except TimeoutError:
                err = "timeout"
            except OSError as exc:
                err = exc.strerror or type(exc).__name__
            return row(t, port, False, None, err)

    async def icmp(t: Target) -> dict[str, Any] | None:
        async with sem:
            r = await ping(t.ip)
        if r is None:
            return None
        ok, ms, err = r
        return row(t, None, ok, ms, err)

    tasks: list[Awaitable[dict[str, Any] | None]] = []
    seen_ping: set[str] = set()
    for t in targets:
        if t.ip not in seen_ping:
            seen_ping.add(t.ip)
            tasks.append(icmp(t))
        tasks.extend(tcp(t, p) for p in t.ports)
    results = [r for r in await asyncio.gather(*tasks) if r is not None]
    out = {"from": ctx.cfg.name or socket.gethostname(), "via": ctx.via, "results": results}
    failed = sum(1 for r in results if not r["ok"])
    # The check itself succeeded either way; what did not answer is in the results.
    if failed:
        return JobResult(0, f"سنجش شبکه: {failed} مورد از {len(results)} جواب نداد.", output=out)
    return JobResult(0, f"سنجش شبکه: هر {len(results)} مورد جواب داد.", output=out)
