#!/usr/bin/env python3
"""A fake Claude Code CLI for the runner's tests: speaks `claude -p … --output-format
stream-json --verbose` without calling any model, and runs PreToolUse hooks from
`--settings` the way the real CLI does (JSON on stdin; exit code 2 blocks the
call and its stderr goes back to the model).

The brief chooses the behaviour:
    [[bash:<command>]]   a Bash tool call with that command (hooks run first)
    [[fake:sleep]]       never finishes (cancel and timeout tests)
    [[fake:error]]       ends with an error result and exit code 1
    anything else        one text answer, then a success result with usage
If FAKE_CLAUDE_RECORD is set, argv, cwd and the settings file go to that JSON file.
"""

from __future__ import annotations

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


def main() -> int:
    if "--version" in sys.argv:
        print("2.1.294 (Claude Code)")
        return 0
    brief = arg("-p") or ""
    settings_path = arg("--settings")
    settings = json.load(open(settings_path)) if settings_path else {}  # noqa: SIM115
    session = arg("--resume") or str(uuid.uuid4())
    record = os.environ.get("FAKE_CLAUDE_RECORD")
    if record:
        with open(record, "w") as fh:
            json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "settings": settings}, fh)
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
