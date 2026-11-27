"""⟨0.4.0⟩ A workshop turn on Antigravity (`agy`, Gemini 4 Hydrogen) in place of Claude Code.

The owner, 2026-11-27: the new pages are built only with Antigravity on Gemini 4 Hydrogen (0
Claude tokens), and when the hub's Claude accounts are out every automation turn goes there
instead (not one second without automations). The hub keeps the job a `claude` job (its
session, workspace, outbox, wake-ups and results are the same); a job whose `model` starts with
`gemini-` is run here instead of claude_job.run_claude:

    agy --input-format stream-json --output-format stream-json --model M
        [--conversation <id>] --print-timeout <s>s --dangerously-skip-permissions
        (the brief on stdin as agy's own stream-json `user` event, never on argv)

- The turn's agy home: `.gemini` in the work's private home (the wall's own home), with this
  server's agy login copied in (newer files only) and this turn's MCP config (the hub's tools,
  the same tools_bridge server as a Claude turn's). The real ~/.gemini is closed behind the wall:
  another company's agy conversations are never readable. Its conversations stay with the work,
  so the next turn of the work resumes them.
- The session id the hub keeps is `agy:<conversation_id>`; a resume that is not one (a Claude
  session of the same work, before a fallback) is dropped and the turn starts afresh in the same
  folder (and the other way round in claude_job).
- Each stream-json line becomes SessionEvents of the same shapes a Claude turn sends (state,
  message, command, file_change, progress); usage goes back under the agy model, `executor:
  agy`, never as a Claude account's.
- Headless agy cannot ask for a permission, so it runs with --dangerously-skip-permissions: only
  as the workshop's own unprivileged user, behind the wall when the server has one. The hub's
  destructive-command hook is Claude Code's (PreToolUse); agy has no hook in --settings, so its
  commands are not classified by the hub (the wall and the user's own rights are the limit).
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any

from hq_runner import outbox, sandbox, tools_bridge
from hq_runner import workspace as workspace_state
from hq_runner.agy_build import FILE_TOOLS, Stream, argv_for, as_dict, find_agy, user_line
from hq_runner.config import config_path
from hq_runner.hub import HubError
from hq_runner.jobs import JobContext, JobError, JobResult, _cwd, _timeout
from hq_runner.mask import Masker, StreamMasker
from hq_runner.proc import ProcResult, run_streamed
from hq_runner.workspace import WorkspaceError, prepare

AGY_PREFIX = "agy:"  # the hub's session id of an agy conversation
EVENT_TEXT = 64_000
MAX_ANSWER_CHARS = 8_000_000
JSON_LINE_BYTES = 64 * 1024 * 1024
EXIT_TOKEN_CAP = 125
DEFAULT_TIMEOUT_S = 3600
MAX_TIMEOUT_S = 4 * 3600
# what of this server's agy login a turn's own home takes (never its conversations)
LOGIN_FILES = (
    ".gemini/antigravity-cli/antigravity-oauth-token",
    ".gemini/antigravity-cli/settings.json",
    ".gemini/antigravity-cli/jetski_state.pbtxt",
    ".gemini/antigravity-cli/installation_id",
    ".gemini/config/config.json",
)
CONTINUED_FA = (
    "(یادداشت ستاد: بخش قبلی این کار با مدل دیگری انجام شد و گفت‌وگوی آن اینجا نیست؛ "
    "وضعیت کار را از "
    "فایل‌های همین پوشه بخوان و از همان‌جا ادامه بده.)\n\n"
)


def is_agy(model: Any) -> bool:
    return isinstance(model, str) and model.startswith("gemini-")


def conversation_of(resume: Any) -> str | None:
    """The agy conversation a resume names (`agy:<id>`), else None (a Claude session's id)."""
    if isinstance(resume, str) and resume.startswith(AGY_PREFIX):
        cid = resume[len(AGY_PREFIX) :]
        if cid and len(cid) <= 100 and all(c.isalnum() or c in "-_" for c in cid):
            return cid
    return None


def _cut(text: str, n: int = EVENT_TEXT) -> str:
    return text if len(text) <= n else text[:n] + "…"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def session_events(
    obj: dict[str, Any], masker: Masker, text: dict[int, str]
) -> list[dict[str, Any]]:
    """One agy stream-json object as SessionEvent-shaped items {type, at, summary_fa, data}, the
    shapes claude_job sends. `text`: the agent's words so far per step (deltas)."""
    at = _now()
    out: list[dict[str, Any]] = []

    def ev(type_: str, summary: str, data: dict[str, Any]) -> None:
        out.append({"type": type_, "at": at, "summary_fa": summary, "data": masker.value(data)})

    kind = obj.get("event")
    if kind == "init":
        init = obj.get("init") or {}
        cid = obj.get("conversation_id")
        ev("state", "نشست Hydrogen (Antigravity) روی سرور آغاز شد.",
           {"state": "working", "session_id": f"{AGY_PREFIX}{cid}" if cid else None,
            "model": init.get("model"), "cwd": init.get("cwd"), "executor": "agy"})  # fmt: skip
    elif kind == "step_update":
        st = obj.get("step_update") or {}
        idx = int(st.get("step_index") or 0)
        step, state = st.get("step_type"), st.get("state")
        tool_id = f"agy-{idx}"
        if step == "agent_response":
            if st.get("text_delta"):
                text[idx] = text.get(idx, "") + str(st["text_delta"])
            if state == "DONE" and text.get(idx, "").strip():
                ev("message", "پیام Hydrogen", {"role": "assistant", "text": _cut(text[idx])})
        elif step in ("tool", "subagent"):
            info = as_dict(st.get("tool_info"))
            name = str(info.get("name") or st.get("tool_name") or "tool")
            params = as_dict(info.get("parameters"))
            if state == "ACTIVE":
                if name == "run_command":
                    ev("command", "دستور",
                       {"cmd": _cut(str(params.get("CommandLine") or "")),
                        "tool_use_id": tool_id})  # fmt: skip
                elif name in FILE_TOOLS:
                    ev("file_change", "تغییر فایل",
                       {"path": params.get("Path") or params.get("TargetFile"), "tool": name,
                        "tool_use_id": tool_id})  # fmt: skip
                else:
                    ev("progress", f"ابزار {name}",
                       {"tool": name, "input": _cut(json.dumps(params, ensure_ascii=False), 1000),
                        "tool_use_id": tool_id})  # fmt: skip
            elif state in ("DONE", "ERROR", "FAILED", "CANCELLED"):
                ev("progress", "نتیجه‌ی ابزار",
                   {"tool_use_id": tool_id, "is_error": state != "DONE",
                    "text": _cut(str(info.get("output") or ""))})  # fmt: skip
    elif kind == "result":
        res = obj.get("result") or {}
        failed = res.get("status") != "SUCCESS"
        cid = res.get("conversation_id")
        secs = res.get("duration_seconds")
        ev("state",
           "نشست Hydrogen با خطا تمام شد." if failed else "نشست Hydrogen تمام شد.",
           {"state": "failed" if failed else "done",
            "session_id": f"{AGY_PREFIX}{cid}" if cid else None, "num_turns": res.get("num_turns"),
            "duration_ms": int(secs * 1000) if isinstance(secs, int | float) else None,
            "stop_reason": res.get("status"), "error": _cut(str(res.get("error") or ""), 2000),
            "result": _cut(str(res.get("response") or ""))})  # fmt: skip
    return out


class AgyMeter:
    """The turn's tokens so far, from each agent step's usage (input + output + thinking)."""

    def __init__(self) -> None:
        self.by_step: dict[int, dict[str, int]] = {}

    def add(self, obj: dict[str, Any]) -> None:
        if obj.get("event") != "step_update":
            return
        st = obj.get("step_update") or {}
        u = st.get("usage")
        if st.get("state") != "DONE" or not isinstance(u, dict):
            return

        def n(k: str) -> int:
            v = u.get(k)
            return max(0, int(v)) if isinstance(v, int | float) and not isinstance(v, bool) else 0

        self.by_step[int(st.get("step_index") or 0)] = {
            "input_tokens": n("input_tokens"),
            "output_tokens": n("output_tokens"),
            "thinking_tokens": n("thinking_tokens"),
            "cache_read_tokens": n("cache_read_tokens"),
        }

    def sum(self, k: str) -> int:
        return sum(m[k] for m in self.by_step.values())

    @property
    def total(self) -> int:
        return self.sum("input_tokens") + self.sum("output_tokens") + self.sum("thinking_tokens")


def usage_of(
    res: dict[str, Any] | None, meter: AgyMeter, model: str, session_id: str | None
) -> dict[str, Any]:
    """The turn's usage as the hub takes it, under the agy model (never a Claude account)."""
    u = (res or {}).get("usage") if isinstance((res or {}).get("usage"), dict) else None

    def n(k: str) -> int:
        if u is not None:
            v = u.get(k)
            return max(0, int(v)) if isinstance(v, int | float) and not isinstance(v, bool) else 0
        return meter.sum(k)

    return {
        "input_tokens": n("input_tokens"),
        "output_tokens": n("output_tokens"),
        "cache_read_tokens": n("cache_read_tokens"),
        "cache_write_tokens": 0,
        "thinking_tokens": n("thinking_tokens"),
        "cost_usd": 0.0,
        "model": model,
        "session_id": session_id,
        "executor": "agy",
    }


def agy_mcp_config(sock: Path, key: str) -> dict[str, Any]:
    """agy's mcp_config.json: tools_bridge's server in agy's own form (no `type`)."""
    cfg = tools_bridge.mcp_config(sock, key)
    servers = {
        name: {k: v for k, v in s.items() if k != "type"} | {"disabled": False}
        for name, s in cfg["mcpServers"].items()
    }
    return {"mcpServers": servers}


def agy_home(home: Path, real_home: Path, mcp: dict[str, Any]) -> None:
    """The turn's own `.gemini` in `home`: a real folder (never a link to the shared one), this
    server's login copied in when newer, and this turn's MCP config (written anew each turn: an
    older turn's key never stays)."""
    g = home / ".gemini"
    if os.path.lexists(g) and (g.is_symlink() or not g.is_dir()):
        sandbox.remove(g)
    for d in (g, g / "antigravity-cli", g / "config"):
        if os.path.lexists(d) and (d.is_symlink() or not d.is_dir()):
            sandbox.remove(d)
        d.mkdir(mode=0o700, exist_ok=True)
    for rel in LOGIN_FILES:
        src, dst = real_home / rel, home / rel
        try:
            if not src.is_file():
                continue
            if dst.is_symlink() or (dst.exists() and not dst.is_file()):
                sandbox.remove(dst)
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                sandbox.copy_file(src, dst)
                os.chmod(dst, 0o600)
        except OSError:
            continue
    cfg = g / "config" / "mcp_config.json"
    if os.path.lexists(cfg):
        sandbox.remove(cfg)
    sandbox.write_new(cfg, json.dumps(mcp))
    os.chmod(cfg, 0o600)


async def _relay(cancel: asyncio.Event, stop: asyncio.Event) -> None:
    await cancel.wait()
    stop.set()


async def run_agy(ctx: JobContext) -> JobResult:
    from hq_runner.claude_job import _wall, token_cap  # one wall, one cap for both executors

    args = ctx.args
    brief = args.get("brief")
    if not isinstance(brief, str) or not brief.strip():
        raise JobError("شرح کار (brief) داده نشده است.")
    model = str(args.get("model"))
    workspace = args.get("workspace")
    if workspace is not None:
        try:
            cwd = str(await asyncio.to_thread(prepare, workspace, ctx.cfg_path))
        except WorkspaceError:
            raise JobError(
                "نام محیط کاری (workspace) باید شماره‌ی یک کار باشد، مثل W-000123."
            ) from None
        ctx.sink.emit("progress", {"text": f"workspace {workspace} (agy {model})"})
        try:
            await outbox.fetch(ctx, Path(cwd), args.get("inputs"))
        except HubError as exc:
            raise JobError("یک فایل ورودی این نوبت از ستاد دریافت نشد؛ نوبت شروع نشد.") from exc
    else:
        cwd = _cwd(args.get("cwd"))
    timeout = _timeout(args, DEFAULT_TIMEOUT_S, MAX_TIMEOUT_S)
    cap = token_cap(args.get("token_cap"))
    agy = find_agy(os.environ.get("HQ_RUNNER_AGY_BIN"))
    if not agy:
        raise JobError("Antigravity (agy) روی این سرور پیدا نشد؛ نوبت Hydrogen اجرا نشد.", 127)
    resume_raw = args.get("session_id") or args.get("resume")
    resume = conversation_of(resume_raw)
    if resume_raw and resume is None:
        # a Claude session of this work (before a fallback): agy cannot take it up
        brief = CONTINUED_FA + brief
        ctx.sink.emit("progress", {"text": "resume dropped: the earlier session was not agy's"})
    real_home = Path.home()
    walled = workspace is not None and args.get("sandbox") == "auto"
    wall: sandbox.Plan | None = None
    wall_why: str | None = None
    if walled:
        wall, wall_why = await _wall(
            ctx, str(workspace), Path(cwd), agy, True, extra_protect=[str(real_home / ".gemini")]
        )
        ctx.sink.emit(
            "progress", {"text": "sandbox on" if wall is not None else f"sandbox off: {wall_why}"}
        )
    tools_on = args.get("tools") == "hub"
    tool_calls = 0

    async def list_tools() -> dict[str, Any]:
        try:
            resp = await ctx.hub.request(
                "GET", f"/runners/jobs/{ctx.id}/tools", job_scoped=True, job_id=ctx.id,
                read_timeout=60.0,
            )  # fmt: skip
        except HubError as exc:
            return {"tools": [], "error": exc.code or str(exc.status)}
        got = resp.json()
        return got if isinstance(got, dict) else {"tools": []}

    async def call_tool(name: str, call_args: dict[str, Any]) -> dict[str, Any]:
        nonlocal tool_calls
        tool_calls += 1
        try:
            resp = await ctx.hub.request(
                "POST", f"/runners/jobs/{ctx.id}/tools/call",
                json={"name": name, "args": call_args}, job_scoped=True, job_id=ctx.id,
                read_timeout=170.0,
            )  # fmt: skip
        except HubError as exc:
            return dict(tools_bridge.UNREACHABLE, detail=exc.code or str(exc.status))
        got = resp.json()
        return got if isinstance(got, dict) else dict(tools_bridge.UNREACHABLE)

    stream = Stream()
    meter = AgyMeter()
    texts: dict[int, str] = {}
    files_changed: list[str] = []
    capped = False
    stop = asyncio.Event()
    relay = asyncio.ensure_future(_relay(ctx.cancel, stop))
    stdout_masker = StreamMasker(ctx.masker)

    def on_stdout(line: str) -> None:
        nonlocal capped
        s = line.strip()
        if not s:
            return
        try:
            obj = json.loads(s)
        except ValueError:
            ctx.sink.emit("stdout", {"text": stdout_masker.line(line)})
            return
        if not isinstance(obj, dict):
            return
        stream.add(obj)
        meter.add(obj)
        if cap is not None and not capped and meter.total > cap:
            capped = True
            ctx.sink.emit(
                "session_event",
                {"type": "state", "at": _now(),
                 "summary_fa": "نشست Hydrogen به سقف توکنش رسید و متوقف شد.",
                 "data": {"state": "failed", "token_cap": cap, "tokens": meter.total}},
            )  # fmt: skip
            stop.set()
        for item in session_events(obj, ctx.masker, texts):
            if item["type"] == "file_change" and item["data"].get("path"):
                path = str(item["data"]["path"])
                if path not in files_changed:
                    files_changed.append(path)
            ctx.sink.emit("session_event", item)

    async def session(plan: sandbox.Plan | None) -> ProcResult:
        key = secrets.token_urlsafe(32)
        made_tmp: Path | None = None
        if plan is None:
            own = (ctx.cfg_path or config_path()).resolve().parent
            own.mkdir(parents=True, exist_ok=True, mode=0o700)
            made_tmp = Path(tempfile.mkdtemp(prefix="hq-agy-", dir=own))
            os.chmod(made_tmp, 0o700)
            job_dir = made_tmp
            if workspace is not None:
                # the work's own agy home even without the wall: its conversations stay with it
                home = workspace_state.root() / sandbox.PRIVATE / str(workspace) / "home"
                home.mkdir(parents=True, exist_ok=True, mode=0o700)
                protect = [str(workspace_state.root()), str(own), str(real_home / ".claude"),
                           str(real_home / ".gemini")]  # fmt: skip
                await asyncio.to_thread(sandbox.make_home, real_home, home, protect)
            else:
                home = made_tmp / "home"
                home.mkdir(mode=0o700)
        else:
            job_dir, home = plan.job, plan.home
        tools_sock = job_dir / "tools.sock"
        mcp = agy_mcp_config(tools_sock, key) if tools_on else {"mcpServers": {}}
        await asyncio.to_thread(agy_home, home, real_home, mcp)
        argv = argv_for(agy, model=model, resume=resume, timeout_s=timeout)
        env = {
            k: v
            for k, v in ctx.env.items()
            if k not in ("XDG_CONFIG_HOME", "CLAUDE_CODE_OAUTH_TOKEN")
        }
        if plan is None:
            env.update(
                {
                    "HOME": str(home),
                    "HQ_RUNNER_CONFIG": str((ctx.cfg_path or config_path()).resolve()),
                }
            )
        else:
            env = sandbox.env_of(plan, env)
        env.update({"HQ_RUNNER_VIA": ctx.via, "HQ_RUNNER_JOB_ID": ctx.id})
        tools_server: asyncio.AbstractServer | None = None
        try:
            if tools_on:
                tools_server = await tools_bridge.serve(tools_sock, list_tools, call_tool, key)
            if plan is not None:
                argv = sandbox.wrap(plan, argv)
            return await run_streamed(
                argv,
                cwd=cwd,
                env=env,
                limit_s=timeout + 60,  # agy's own --print-timeout ends it first, with a result
                cancel=stop,
                on_stdout=on_stdout,
                on_stderr=ctx.line_sink("stderr"),
                max_line=JSON_LINE_BYTES,
                stdin_data=user_line(brief),
            )
        finally:
            if tools_server is not None:
                tools_server.close()
                with contextlib.suppress(Exception):
                    await tools_server.wait_closed()
            if made_tmp is not None:
                await asyncio.to_thread(sandbox.remove_quietly, made_tmp)
            if plan is not None:
                await asyncio.to_thread(sandbox.remove_quietly, plan.tmp)
            # the MCP config holds this turn's key: never left for the next turn
            with contextlib.suppress(OSError):
                (home / ".gemini" / "config" / "mcp_config.json").unlink()

    try:
        res = await session(wall)
        if (
            wall is not None
            and res.reason is None
            and not capped
            and not ctx.cancel.is_set()
            and stream.conversation_id is None
            and res.exit_code != 0
        ):
            broken = await sandbox.recheck(wall, dict(ctx.env), agy)
            if broken is not None:
                wall, wall_why = None, "the walled session did not start"
                ctx.sink.emit(
                    "progress", {"text": f"sandbox off: {wall_why} ({broken}); starting without it"}
                )
                res = await session(None)
    finally:
        relay.cancel()
    result = as_dict(stream.result)
    sid = f"{AGY_PREFIX}{stream.conversation_id}" if stream.conversation_id else None
    usage = usage_of(result or None, meter, model, sid) if (result or meter.by_step) else None
    exit_code = res.exit_code
    if capped and not ctx.cancel.is_set():
        exit_code = EXIT_TOKEN_CAP
    status = stream.status
    if status != "SUCCESS" and exit_code == 0:
        exit_code = 1
    whole = (
        stream.response
        if status == "SUCCESS"
        else (stream.response or str(result.get("error") or ""))
    )
    cut = len(whole) > MAX_ANSWER_CHARS
    answer = ctx.masker.text(whole[:MAX_ANSWER_CHARS] if cut else whole)
    output: dict[str, Any] = {
        "session_id": sid,
        "result_fa": answer,
        "answer_chars": len(whole),
        "answer_truncated": cut,
        "files_changed": files_changed,
        "num_turns": result.get("num_turns"),
        "stop_reason": status or res.reason,
        "executor": "agy",
        "model": model,
    }
    if result.get("error"):
        output["error_detail"] = ctx.masker.text(str(result["error"]))[:2000]
    if result.get("denied_actions"):
        output["denied_actions"] = result["denied_actions"]
    if cap is not None:
        output["token_cap"] = cap
        output["token_cap_reached"] = capped
    if workspace is not None:
        output["workspace"] = {"ref": workspace, "path": cwd}
    if tools_on:
        output["tool_calls"] = tool_calls
    if walled:
        output["sandbox"] = (
            {"state": "on", "kind": "landlock"}
            if wall is not None
            else {"state": "off", "why": wall_why or "unknown"}
        )
    sent_n = 0
    after_post = None
    timed_out = res.reason == "timeout" or status == "TIMEOUT"
    if (
        workspace is not None
        and (exit_code == 0 or timed_out)
        and not ctx.cancel.is_set()
        and not capped
    ):
        files, skipped, marks = await outbox.send(ctx, Path(cwd), str(workspace))
        if marks:
            after_post = functools.partial(
                workspace_state.mark_sent, str(workspace), marks, "", ctx.cfg_path
            )
        sent_n = len(files)
        if files:
            output["files"] = files
        if skipped:
            output["files_skipped"] = skipped[: outbox.MAX_FILES * 2]
    if capped and not ctx.cancel.is_set():
        summary = f"نشست Hydrogen به سقف {cap} توکن رسید و متوقف شد."
    elif timed_out:
        summary = "نشست Hydrogen به سقف زمان رسید و متوقف شد."
    elif res.reason == "cancelled":
        summary = "نشست Hydrogen لغو شد."
    elif exit_code == 0:
        summary = "نشست Hydrogen (Antigravity) روی سرور تمام شد."
    else:
        summary = f"نشست Hydrogen با کد خروج {exit_code} تمام شد."
        if result.get("error"):
            summary += " " + ctx.masker.text(str(result["error"]))[:300]
    if cut:
        summary += f" جواب {len(whole)} نویسه بود و فقط {MAX_ANSWER_CHARS} نویسه‌ی اول آن آمد."
    if sent_n:
        summary += f" {sent_n} فایل از out/ به ستاد رفت."
    return JobResult(exit_code, summary, usage=usage, output=output, after_post=after_post)


_INSTALLED: list[float | bool] = [0.0, False]
INSTALLED_TTL_S = 300.0


def installed() -> bool:
    """Whether this server runs agy turns: the CLI and this user's agy login are here, and
    HQ_RUNNER_AGY is not `off`. The runner tells the hub so on every request (X-HQ-Runner-Agy):
    the hub sends a Gemini turn only to a runner that can run it. Read again every 5 minutes."""
    now = time.monotonic()
    if now - float(_INSTALLED[0]) < INSTALLED_TTL_S and _INSTALLED[0]:
        return bool(_INSTALLED[1])
    off = os.environ.get("HQ_RUNNER_AGY", "").strip().lower() in ("off", "0", "no", "false")
    ok = (
        not off
        and bool(find_agy(os.environ.get("HQ_RUNNER_AGY_BIN")))
        and (Path.home() / LOGIN_FILES[0]).is_file()
    )
    _INSTALLED[:] = [now, ok]
    return ok
