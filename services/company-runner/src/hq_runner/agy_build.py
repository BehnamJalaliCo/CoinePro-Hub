#!/usr/bin/env python3
"""⟨0.4.0⟩ `agy-build`: Antigravity (`agy`, Gemini 4 Hydrogen) as the BUILDER inside a workshop turn.

The owner, 2026-11-27: the new pages are directed and edited by Claude (script, storyboard,
voice, frame-sheet reviews, final approval) and BUILT by Hydrogen on its own Google quota. A
Claude turn of the workshop (the studio user, behind the Landlock wall) runs this command:

    agy-build <workdir> <brief.md> [--resume <conversation_id>] [--model M] [--timeout S]
              [--detach]
    agy-build --wait <workdir> [--max S]      follow a detached build (exit 3: still running)
    agy-build --status <workdir>              one line: running|SUCCESS|ERROR …
    agy-build --stop <workdir>                stop a detached build

It runs `agy` headless (stream-json in and out; the brief goes in on stdin, never on argv where
every process of this user could read it) in <workdir>, on gemini-4-hydrogen-xhigh unless told
otherwise, prints a short log (tools, commands, the model's words), and ends with

    AGY_CONVERSATION_ID=<id>       (pass it to --resume with review notes as the next brief)
    AGY_STATUS=SUCCESS|ERROR|TIMEOUT|STOPPED
    AGY_TOKENS=<total>

Exit 0 on SUCCESS. Everything is also kept in <workdir>/.agy/ (run.jsonl: the raw stream,
log.txt, state.json, response.md). A Bash call of Claude Code ends after 10 minutes at most,
and a Hydrogen build takes 5-25: `--detach` starts it and returns at once; `--wait` follows it
for up to `--max` seconds (default 540) and can be called again.

Stdlib only: it runs with the system Python as well as with the runner's.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "gemini-4-hydrogen-xhigh"
DEFAULT_TIMEOUT_S = 3000
WAIT_MAX_S = 540
STATE_DIR = ".agy"
LOG_TEXT = 400  # characters of one line of the short log
EXIT_RUNNING = 3


def find_agy(configured: str | None = None) -> str | None:
    """The CLI: the configured path, HQ_RUNNER_AGY_BIN, PATH, then ~/.local/bin/agy."""
    for cand in (configured, os.environ.get("HQ_RUNNER_AGY_BIN")):
        if cand:
            return cand
    found = shutil.which("agy")
    if found:
        return found
    for p in (Path.home() / ".local/bin/agy", Path("/home/studio/.local/bin/agy")):
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def user_line(text: str) -> bytes:
    """One stream-json input message of agy (its own form: `event`, then a Claude-like message)."""
    msg = {"event": "user", "message": {"role": "user", "content": text}}
    return (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")


def argv_for(
    agy: str,
    *,
    model: str | None,
    resume: str | None,
    timeout_s: int | None,
    effort: str | None = None,
    skip_permissions: bool = True,
) -> list[str]:
    """agy headless: stream-json in (the brief on stdin) and out. No `-p`: with
    `--input-format stream-json` each stdin line is a turn, and `-p` would swallow the next flag."""
    argv = [agy, "--input-format", "stream-json", "--output-format", "stream-json"]
    if model:
        argv += ["--model", model]
    if effort:
        argv += ["--effort", effort]
    if resume:
        argv += ["--conversation", resume]
    if timeout_s:
        argv += ["--print-timeout", f"{int(timeout_s)}s"]
    if skip_permissions:
        # headless agy cannot ask; it runs as the workshop's own user, behind the wall
        argv.append("--dangerously-skip-permissions")
    return argv


def _cut(text: str, n: int = LOG_TEXT) -> str:
    t = " ".join(str(text).split())
    return t if len(t) <= n else t[:n] + "…"


def tool_line(info: dict[str, Any]) -> str:
    """A tool step in one line: its name and its most telling parameter."""
    name = str(info.get("name") or "tool")
    params = info.get("parameters") if isinstance(info.get("parameters"), dict) else {}
    for key in ("CommandLine", "Path", "TargetFile", "AbsolutePath", "Url", "Query", "Prompt"):
        if params.get(key):
            return f"{name}: {_cut(str(params[key]), 240)}"
    return name if not params else f"{name}: {_cut(json.dumps(params, ensure_ascii=False), 240)}"


class Stream:
    """agy's stream-json, read line by line: the conversation, the text so far, the final result,
    and a short human log line per step."""

    def __init__(self) -> None:
        self.conversation_id: str | None = None
        self.model: str | None = None
        self.result: dict[str, Any] | None = None
        self.text: dict[int, str] = {}
        self.usage: dict[str, int] = {}
        self.steps: dict[int, dict[str, Any]] = {}
        self.files: list[str] = []

    def add(self, obj: dict[str, Any]) -> list[str]:
        """The short log lines this object adds (none for most)."""
        ev = obj.get("event")
        out: list[str] = []
        if ev == "init":
            init = obj.get("init") or {}
            self.conversation_id = obj.get("conversation_id") or self.conversation_id
            self.model = init.get("model") or self.model
            out.append(f"start {self.model} conversation {self.conversation_id}")
        elif ev == "step_update":
            st = obj.get("step_update") or {}
            self.conversation_id = st.get("conversation_id") or self.conversation_id
            idx = int(st.get("step_index") or 0)
            kind, state = st.get("step_type"), st.get("state")
            if kind == "agent_response":
                if st.get("text_delta"):
                    self.text[idx] = self.text.get(idx, "") + str(st["text_delta"])
                if state == "DONE":
                    if isinstance(st.get("usage"), dict):
                        self.steps[idx] = {"usage": st["usage"]}
                    if self.text.get(idx, "").strip():
                        out.append(f"say: {_cut(self.text[idx])}")
            elif kind in ("tool", "subagent"):
                info = st.get("tool_info") if isinstance(st.get("tool_info"), dict) else {}
                if not info:
                    info = {"name": st.get("tool_name")}
                if state == "ACTIVE":
                    out.append(f"tool {tool_line(info)}")
                elif state == "DONE":
                    name = str(info.get("name") or st.get("tool_name") or "")
                    params = info.get("parameters") if isinstance(info.get("parameters"), dict) else {}
                    path = params.get("Path") or params.get("TargetFile")
                    if name in FILE_TOOLS and path and str(path) not in self.files:
                        self.files.append(str(path))
                    secs = st.get("duration_seconds")
                    took = f" ({secs:.0f}s)" if isinstance(secs, int | float) and secs >= 5 else ""
                    if took:
                        out.append(f"done {name}{took}")
                elif state in ("ERROR", "FAILED", "CANCELLED"):
                    out.append(f"tool {info.get('name')} {state}")
        elif ev == "result":
            res = obj.get("result") or {}
            self.result = res
            self.conversation_id = res.get("conversation_id") or self.conversation_id
            if isinstance(res.get("usage"), dict):
                self.usage = {k: int(v) for k, v in res["usage"].items() if isinstance(v, int)}
            status = res.get("status")
            line = f"end {status}"
            if res.get("error"):
                line += f": {_cut(str(res['error']))}"
            if res.get("denied_actions"):
                line += f" (denied: {_cut(json.dumps(res['denied_actions']), 200)})"
            out.append(line)
        return out

    @property
    def status(self) -> str:
        return str((self.result or {}).get("status") or "")

    @property
    def response(self) -> str:
        if self.result and self.result.get("response"):
            return str(self.result["response"])
        return "".join(self.text[k] for k in sorted(self.text))

    @property
    def total_tokens(self) -> int:
        u = self.usage
        if u.get("total_tokens"):
            return int(u["total_tokens"])
        return sum(int(u.get(k) or 0) for k in ("input_tokens", "output_tokens", "thinking_tokens"))


FILE_TOOLS = {"write_file", "write_to_file", "edit_file", "replace_file_content", "multi_replace_file_content"}


# ---------------------------------------------------------------- the command --
def _state_dir(workdir: Path) -> Path:
    d = workdir / STATE_DIR
    d.mkdir(mode=0o700, exist_ok=True)
    return d


def _write_state(d: Path, **kv: Any) -> dict[str, Any]:
    path = d / "state.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    state.update(kv)
    tmp = d / "state.json.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return state


def _read_state(workdir: Path) -> dict[str, Any]:
    try:
        return dict(json.loads((workdir / STATE_DIR / "state.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def _alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _say(line: str, log: Any) -> None:
    stamp = time.strftime("%H:%M:%S", time.gmtime())
    text = f"[{stamp}] {line}"
    print(text, flush=True)
    if log is not None:
        log.write(text + "\n")
        log.flush()


def run(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    brief_path = Path(args.brief)
    if not workdir.is_dir():
        print(f"agy-build: no such folder {workdir}", file=sys.stderr)
        return 2
    try:
        brief = brief_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"agy-build: cannot read the brief {brief_path}: {exc}", file=sys.stderr)
        return 2
    if not brief.strip():
        print("agy-build: the brief is empty", file=sys.stderr)
        return 2
    agy = find_agy(args.agy)
    if not agy:
        print("agy-build: the agy CLI was not found on this server", file=sys.stderr)
        return 127
    d = _state_dir(workdir)
    st = _read_state(workdir)
    if _alive(st.get("pid")) and st.get("status") == "running" and st.get("pid") != os.getpid():
        print(f"agy-build: a build is already running in {workdir} (pid {st['pid']}); "
              "use --wait or --stop", file=sys.stderr)  # fmt: skip
        return 4
    argv = argv_for(agy, model=args.model, resume=args.resume, timeout_s=args.timeout)
    started = time.time()
    _write_state(d, pid=os.getpid(), status="running", started=started, ended=None,
                 conversation_id=args.resume, model=args.model, brief=str(brief_path),
                 exit=None, tokens=None)  # fmt: skip
    stream = Stream()
    stopped = False
    with open(d / "log.txt", "a", encoding="utf-8") as log, open(d / "run.jsonl", "a", encoding="utf-8") as raw:
        _say(f"agy-build {args.model} in {workdir}" + (f" resume {args.resume}" if args.resume else ""), log)
        proc = subprocess.Popen(
            argv, cwd=str(workdir), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, start_new_session=True,
        )  # fmt: skip
        _write_state(d, agy_pid=proc.pid)

        def stop(_sig: int, _frm: Any) -> None:
            nonlocal stopped
            stopped = True
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGTERM)

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
        proc.stdin.write(user_line(brief))
        proc.stdin.close()
        for line in proc.stdout:
            s = line.decode("utf-8", "replace").strip()
            if not s:
                continue
            raw.write(s + "\n")
            raw.flush()
            try:
                obj = json.loads(s)
            except ValueError:
                _say(_cut(s), log)
                continue
            if isinstance(obj, dict):
                for out in stream.add(obj):
                    _say(out, log)
                if stream.conversation_id and not st.get("cid_written"):
                    _write_state(d, conversation_id=stream.conversation_id)
                    st["cid_written"] = True
        err = proc.stderr.read().decode("utf-8", "replace")
        code = proc.wait()
        if err.strip():
            for ln in err.strip().splitlines()[-5:]:
                _say(f"stderr: {_cut(ln)}", log)
        status = stream.status or ("STOPPED" if stopped else "ERROR")
        if stopped:
            status = "STOPPED"
        elif status != "SUCCESS" and time.time() - started >= args.timeout - 5:
            status = "TIMEOUT"
        response = stream.response
        (d / "response.md").write_text(response, encoding="utf-8")
        _write_state(d, status=status, ended=time.time(), exit=code, tokens=stream.total_tokens,
                     conversation_id=stream.conversation_id or args.resume, files=stream.files)  # fmt: skip
        _say(f"response: {_cut(response, 1500)}", log)
        for line in (
            f"AGY_CONVERSATION_ID={stream.conversation_id or args.resume or ''}",
            f"AGY_STATUS={status}",
            f"AGY_TOKENS={stream.total_tokens}",
        ):
            _say(line, log)
    return 0 if status == "SUCCESS" else 1


def detach(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    if not workdir.is_dir():
        print(f"agy-build: no such folder {workdir}", file=sys.stderr)
        return 2
    st = _read_state(workdir)
    if _alive(st.get("pid")) and st.get("status") == "running":
        print(f"agy-build: a build is already running in {workdir} (pid {st['pid']})", file=sys.stderr)
        return 4
    d = _state_dir(workdir)
    rest = [str(workdir), str(Path(args.brief).resolve()), "--model", args.model,
            "--timeout", str(args.timeout)]
    if args.resume:
        rest += ["--resume", args.resume]
    if args.agy:
        rest += ["--agy", args.agy]
    out = open(d / "detached.out", "a", encoding="utf-8")  # noqa: SIM115 - the child keeps it
    # this same file as a script (stdlib only), in a session of its own: the Bash call that
    # started it may end long before the build does
    proc = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), *rest],
        stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
        cwd=str(workdir),
    )  # fmt: skip
    _write_state(d, pid=proc.pid, status="running", started=time.time(), ended=None)
    print(f"agy-build: started in the background (pid {proc.pid}). Follow it with: "
          f"agy-build --wait {workdir}")  # fmt: skip
    return 0


def _offset_file(workdir: Path) -> Path:
    return workdir / STATE_DIR / "wait.offset"


def wait(workdir: Path, max_s: int) -> int:
    log = workdir / STATE_DIR / "log.txt"
    off_file = _offset_file(workdir)
    try:
        off = int(off_file.read_text())
    except (OSError, ValueError):
        off = 0
    end = time.time() + max_s
    while True:
        with contextlib.suppress(OSError):
            with open(log, "rb") as f:
                f.seek(off)
                chunk = f.read()
            if chunk:
                cut = chunk.rfind(b"\n") + 1
                if cut:
                    sys.stdout.write(chunk[:cut].decode("utf-8", "replace"))
                    sys.stdout.flush()
                    off += cut
                    off_file.write_text(str(off))
        st = _read_state(workdir)
        if st.get("status") and st.get("status") != "running":
            print(f"AGY_STATUS={st['status']}")
            return 0 if st["status"] == "SUCCESS" else 1
        if st.get("status") == "running" and not _alive(st.get("pid")):
            _write_state(workdir / STATE_DIR, status="ERROR", ended=time.time())
            print("agy-build: the build process is gone without a result\nAGY_STATUS=ERROR")
            return 1
        if not st:
            print("agy-build: no build in this folder", file=sys.stderr)
            return 2
        if time.time() >= end:
            print(f"agy-build: still running; call again: agy-build --wait {workdir}")
            return EXIT_RUNNING
        time.sleep(5)


def status(workdir: Path) -> int:
    st = _read_state(workdir)
    if not st:
        print("none")
        return 2
    alive = _alive(st.get("pid"))
    s = st.get("status")
    if s == "running" and not alive:
        s = "ERROR (process gone)"
    print(f"{s} conversation={st.get('conversation_id') or ''} tokens={st.get('tokens') or 0}")
    return 0 if s == "SUCCESS" else EXIT_RUNNING if s == "running" else 1


def stop_build(workdir: Path) -> int:
    st = _read_state(workdir)
    for key in ("pid", "agy_pid"):
        pid = st.get(key)
        if _alive(pid):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(int(pid), signal.SIGTERM)
    print("stopped")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agy-build", description=__doc__.split("\n\n")[0])
    p.add_argument("workdir", nargs="?")
    p.add_argument("brief", nargs="?")
    p.add_argument("--resume", default=None, help="the conversation_id of an earlier build")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="seconds (default 3000)")
    p.add_argument("--detach", action="store_true", help="start in the background, return at once")
    p.add_argument("--wait", metavar="WORKDIR", default=None)
    p.add_argument("--max", type=int, default=WAIT_MAX_S, help="seconds --wait follows (default 540)")
    p.add_argument("--status", metavar="WORKDIR", default=None)
    p.add_argument("--stop", metavar="WORKDIR", default=None)
    p.add_argument("--agy", default=None, help=argparse.SUPPRESS)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser().parse_args(argv)
    if os.geteuid() == 0:
        print("agy-build: never as root", file=sys.stderr)
        return 2
    if args.wait:
        return wait(Path(args.wait).resolve(), max(1, args.max))
    if args.status:
        return status(Path(args.status).resolve())
    if args.stop:
        return stop_build(Path(args.stop).resolve())
    if not args.workdir or not args.brief:
        parser().print_usage(sys.stderr)
        return 2
    if args.detach:
        return detach(args)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
