#!/usr/bin/env python3
"""A fake Antigravity CLI (`agy`) for the runner's tests: speaks `agy --input-format stream-json
--output-format stream-json …` (one `{"event": "user", "message": …}` line on stdin) without
calling any model, in agy's own event shapes (init, step_update, result).

The brief chooses the behaviour:
    [[cmd:<command>]]    a run_command step (the command is run, its output reported)
    [[write:<name>]]     a write_file step: <name> is written in the cwd
    [[tool:NAME:{json}]] one MCP call of the first server of $HOME/.gemini/config/mcp_config.json
    [[fake:sleep]]       never finishes (cancel and timeout tests)
    [[fake:error]]       ends with an ERROR result and exit code 1
    anything else        one text answer, then a SUCCESS result with usage
If FAKE_AGY_RECORD is set, argv, cwd, HOME, the stdin line and the MCP config go to that file.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fake_claude import mcp_calls


def arg(name: str) -> str | None:
    argv = sys.argv[1:]
    return argv[argv.index(name) + 1] if name in argv else None


def emit(obj: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main() -> int:
    line = sys.stdin.readline()
    msg = json.loads(line)
    if msg.get("event") != "user":
        emit({"event": "result", "result": {"status": "ERROR",
              "error": 'stream input message is missing the "event" field'}})  # fmt: skip
        return 1
    brief = str(msg["message"]["content"])
    home = os.environ.get("HOME", "")
    mcp_path = os.path.join(home, ".gemini", "config", "mcp_config.json")
    mcp = json.load(open(mcp_path)) if os.path.isfile(mcp_path) else None  # noqa: SIM115
    if os.environ.get("FAKE_AGY_RECORD"):
        with open(os.environ["FAKE_AGY_RECORD"], "w") as fh:
            json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "home": home, "brief": brief,
                       "mcp": mcp, "login": os.path.isfile(os.path.join(
                           home, ".gemini", "antigravity-cli", "antigravity-oauth-token"))}, fh)  # fmt: skip
    cid = arg("--conversation") or str(uuid.uuid4())
    model = arg("--model") or "gemini-4-hydrogen-low"
    emit({"event": "init", "conversation_id": cid,
          "init": {"model": model, "cwd": os.getcwd(), "tools": ["run_command", "write_file"],
                   "permission_mode": "bypass"}})  # fmt: skip
    emit({"event": "step_update", "step_update": {"conversation_id": cid, "step_index": 0,
          "state": "DONE", "step_type": "user_input"}})  # fmt: skip
    if "[[fake:sleep]]" in brief:
        time.sleep(3600)
    i = 1
    usage = {"input_tokens": 100, "output_tokens": 20, "thinking_tokens": 5, "cache_read_tokens": 7,
             "total_tokens": 125}  # fmt: skip
    for cmd in re.findall(r"\[\[cmd:(.*?)\]\]", brief):
        info = {"name": "run_command", "parameters": {"CommandLine": cmd}}
        emit({"event": "step_update", "step_update": {"conversation_id": cid, "step_index": i,
              "state": "ACTIVE", "step_type": "tool", "tool_name": "run_command", "tool_info": info}})  # fmt: skip
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False).stdout  # noqa: S602
        emit({"event": "step_update", "step_update": {"conversation_id": cid, "step_index": i,
              "state": "DONE", "step_type": "tool", "tool_name": "run_command",
              "tool_info": {**info, "output": f"Command output:\n{out}"}}})  # fmt: skip
        i += 1
    for name in re.findall(r"\[\[write:(.*?)\]\]", brief):
        path = os.path.join(os.getcwd(), name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("made by fake agy\n")
        info = {"name": "write_file", "parameters": {"Path": path}}
        for state in ("ACTIVE", "DONE"):
            emit({"event": "step_update", "step_update": {"conversation_id": cid, "step_index": i,
                  "state": state, "step_type": "tool", "tool_name": "write_file", "tool_info": info}})  # fmt: skip
        i += 1
    said = ["Done."]
    if re.search(r"\[\[tool:", brief):
        if mcp is None:
            said.append("mcp -> no server configured")
        else:
            cfg = os.path.join(os.environ.get("TMPDIR", "/tmp"), f"fake-agy-mcp-{os.getpid()}.json")
            with open(cfg, "w") as fh:
                json.dump(mcp, fh)
            sys.argv += ["--mcp-config", cfg]
            said += mcp_calls(brief)
    text = " ".join(said)
    if "[[fake:error]]" in brief:
        emit({"event": "result", "result": {"conversation_id": cid, "status": "ERROR", "response": "",
              "error": "model request failed", "num_turns": 1, "usage": usage}})  # fmt: skip
        return 1
    for k, part in enumerate((text[: len(text) // 2], text[len(text) // 2 :])):
        emit({"event": "step_update", "step_update": {"conversation_id": cid, "step_index": i,
              "state": "ACTIVE" if k == 0 else "DONE", "step_type": "agent_response",
              "text_delta": part, **({"usage": usage} if k else {})}})  # fmt: skip
    emit({"event": "result", "result": {"conversation_id": cid, "status": "SUCCESS", "response": text,
          "duration_seconds": 1.5, "num_turns": 1, "usage": usage}})  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
