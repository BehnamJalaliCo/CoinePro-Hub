#!/usr/bin/env python3
"""A fake Claude Code CLI for the runner's tests: speaks `claude -p … --output-format
stream-json --verbose` without calling any model, and runs PreToolUse hooks from
`--settings` the way the real CLI does (JSON on stdin; exit code 2 blocks the
call and its stderr goes back to the model).

The brief chooses the behaviour:
    [[bash:<command>]]   a Bash tool call with that command (hooks run first)
    [[fake:sleep]]       never finishes (cancel and timeout tests)
    [[fake:error]]       ends with an error result and exit code 1
    [[tool:NAME:{json}]] one MCP call of that tool of the server in --mcp-config (the hub's
                         tools of a direct session), after initialize and tools/list
    [[fake:spend:N]]     N assistant messages of 10 000 tokens each (every one
                         repeated once, as Claude Code repeats a message's usage
                         on each content block), then never finishes (token cap)
    anything else        one text answer, then a success result with usage
If FAKE_CLAUDE_RECORD is set, argv, cwd and the settings file go to that JSON file.
`--help` prints the options a real CLI lists (FAKE_CLAUDE_EFFORTS: the levels of --effort).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid


def arg(name: str) -> str | None:
    argv = sys.argv[1:]
    return argv[argv.index(name) + 1] if name in argv else None


def emit(obj: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def run_hooks(settings: dict[str, object], session: str, command: str) -> tuple[bool, str]:
    """(allowed, message) after the PreToolUse hooks that match Bash."""
    hooks = settings.get("hooks") if isinstance(settings, dict) else None
    groups = hooks.get("PreToolUse", []) if isinstance(hooks, dict) else []
    payload = {
        "session_id": session,
        "transcript_path": "/dev/null",
        "cwd": os.getcwd(),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": "fake"},
    }
    for group in groups:
        if not re.fullmatch(str(group.get("matcher", ".*")) or ".*", "Bash"):
            continue
        for hook in group.get("hooks", []):
            proc = subprocess.run(  # noqa: S602 - hook commands are shell lines, like the real CLI
                hook["command"],
                shell=True,
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=int(hook.get("timeout", 60)),
                check=False,
            )
            if proc.returncode == 2:
                return False, proc.stderr.strip()
    return True, ""


def mcp_calls(brief: str) -> list[str]:
    """`[[tool:<name>:<json args>]]`: speak MCP to the first server of `--mcp-config` as the
    real CLI does (initialize, the initialized notice, tools/list, then each call) and say what
    came back. Nothing when the brief names no tool or no server was configured."""
    wanted = re.findall(r"\[\[tool:([A-Za-z0-9_-]+):(\{.*?\})\]\]", brief)
    config = arg("--mcp-config")
    if not wanted:
        return []
    if not config:
        return ["mcp -> no server configured"]
    with open(config) as fh:
        servers = json.load(fh)["mcpServers"]
    name, spec = next(iter(servers.items()))
    proc = subprocess.Popen(
        [spec["command"], *spec.get("args", [])],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, **spec.get("env", {})},
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    n = 0

    def ask(method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        nonlocal n
        n += 1
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": n, "method": method,
                                     "params": params or {}}) + "\n")  # fmt: skip
        proc.stdin.flush()
        return dict(json.loads(proc.stdout.readline()))

    out: list[str] = []
    try:
        client = {"name": "fake-claude", "version": "0"}
        init = ask(
            "initialize",
            {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": client},
        )
        out.append(f"mcp {name} -> {init['result']['serverInfo']['name']}")
        notice = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        proc.stdin.write(json.dumps(notice) + "\n")
        proc.stdin.flush()
        listed = ask("tools/list")["result"]["tools"]
        out.append("tools -> " + ",".join(sorted(t["name"] for t in listed)))
        for tool, raw in wanted:
            got = ask("tools/call", {"name": tool, "arguments": json.loads(raw)})
            res = got.get("result") or {}
            text = (res.get("content") or [{}])[0].get("text", "")
            out.append(f"call {tool} -> error={res.get('isError')} {text}")
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
    return out


HELP = """Usage: claude [options] [prompt]

Options:
  --model <model>            Model for the current session
  --effort <level>           Effort level for the current session
                             ({levels})
  --resume [value]           Resume a conversation by session ID
"""


def main() -> int:
    if "--help" in sys.argv[1:]:
        # FAKE_CLAUDE_EFFORTS: the levels this CLI lists for --effort ("" = an older CLI without it)
        levels = os.environ.get("FAKE_CLAUDE_EFFORTS", "low, medium, high, xhigh, max")
        sys.stdout.write(HELP.format(levels=levels) if levels else "Usage: claude [options]\n")
        return 0
    if "--version" in sys.argv:
        print("2.1.294 (Claude Code)")
        return 0
    brief = arg("-p") or ""
    from_stdin = not brief or brief.startswith("--")
    if from_stdin:  # ⟨0.3.4⟩ behind the wall the brief comes on stdin, never in argv
        brief = sys.stdin.read()
    if "[[fake:wallfail]]" in brief and os.environ.get("HQ_RUNNER_SANDBOX_STATE") == "on":
        print("fake: cannot start behind the wall", file=sys.stderr)
        return 1
    settings_path = arg("--settings")
    settings = json.load(open(settings_path)) if settings_path else {}  # noqa: SIM115
    session = arg("--resume") or str(uuid.uuid4())
    record = os.environ.get("FAKE_CLAUDE_RECORD")
    if record:
        with open(record, "w") as fh:
            json.dump(
                {
                    "argv": sys.argv[1:],
                    "cwd": os.getcwd(),
                    "settings": settings,
                    "brief_on_stdin": from_stdin,
                    "home": os.environ.get("HOME"),
                    "tmpdir": os.environ.get("TMPDIR"),
                    "runner_config_env": os.environ.get("HQ_RUNNER_CONFIG"),
                    # which account ran it (a digest, never the token)
                    "oauth_sha8": hashlib.sha256(
                        os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").encode()
                    ).hexdigest()[:8],
                },
                fh,
            )
    model = arg("--model") or "claude-sonnet-5-5"
    emit(
        {
            "type": "system",
            "subtype": "init",
            "session_id": session,
            "model": model,
            "cwd": os.getcwd(),
            "tools": ["Bash", "Edit"],
        }
    )
    if "[[fake:sleep]]" in brief:
        time.sleep(3600)
    spend = re.search(r"\[\[fake:spend:(\d+)\]\]", brief)
    if spend:
        for i in range(int(spend.group(1))):
            message = {
                "id": f"msg_{i}",
                "model": model,
                "content": [{"type": "text", "text": f"step {i}"}],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 1000,
                    "cache_read_input_tokens": 7000,
                    "cache_creation_input_tokens": 1000,
                },
            }
            emit({"type": "assistant", "session_id": session, "message": message})
            emit({"type": "assistant", "session_id": session, "message": message})
            time.sleep(0.05)
        time.sleep(3600)
    for i, command in enumerate(re.findall(r"\[\[bash:(.+?)\]\]", brief)):
        tool_id = f"toolu_{i}"
        emit(
            {
                "type": "assistant",
                "session_id": session,
                "message": {
                    "model": model,
                    "content": [
                        {
                            "type": "tool_use",
                            "id": tool_id,
                            "name": "Bash",
                            "input": {"command": command},
                        }
                    ],
                },
            }
        )
        allowed, message = run_hooks(settings, session, command)
        if allowed:
            content, is_error = f"(fake) ran: {command}", False
        else:
            content, is_error = f"PreToolUse:Bash hook error: {message}", True
        emit(
            {
                "type": "user",
                "session_id": session,
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": content,
                            "is_error": is_error,
                        }
                    ],
                },
            }
        )
    seen = []
    for path in re.findall(r"\[\[fake:read:(.+?)\]\]", brief):
        try:
            with open(path) as fh:
                seen.append(f"read {path} -> {fh.read().strip()}")
        except OSError as exc:
            seen.append(f"read {path} -> {type(exc).__name__}")
    for path in re.findall(r"\[\[fake:write:(.+?)\]\]", brief):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as fh:
                fh.write("made")
            seen.append(f"write {path} -> ok")
        except OSError as exc:
            seen.append(f"write {path} -> {type(exc).__name__}")
    seen += mcp_calls(brief)
    if seen:
        emit(
            {
                "type": "assistant",
                "session_id": session,
                "message": {
                    "id": "msg_seen",
                    "model": model,
                    "content": [{"type": "text", "text": "\n".join(seen)}],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            }
        )
    if "[[fake:error]]" in brief:
        emit(
            {
                "type": "result",
                "subtype": "error_during_execution",
                "is_error": True,
                "session_id": session,
                "num_turns": 1,
                "duration_ms": 5,
                "result": "failed",
            }
        )
        return 1
    emit(
        {
            "type": "assistant",
            "session_id": session,
            "message": {
                "model": model,
                "content": [{"type": "text", "text": "Done. DB_PASSWORD=hunter2hunter2"}],
            },
        }
    )
    emit(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "session_id": session,
            "num_turns": 2,
            "duration_ms": 12,
            "stop_reason": "end_turn",
            # a long answer when the test asks for one (FAKE_CLAUDE_ANSWER_CHARS)
            "result": "Done." + "ب" * int(os.environ.get("FAKE_CLAUDE_ANSWER_CHARS") or 0),
            "usage": {
                "input_tokens": 120,
                "output_tokens": 30,
                "cache_read_input_tokens": 50,
                "cache_creation_input_tokens": 70,
                "output_tokens_details": {"thinking_tokens": 4},
            },
            "total_cost_usd": 0.0123,
            "modelUsage": {model: {"inputTokens": 120, "outputTokens": 30}},
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
