#!/usr/bin/env python3
"""A fake Claude Code CLI for tests: speaks the SDK's stream-json protocol
without calling any model, so tests never spend subscription quota.

The real SDK (claude-agent-sdk) drives it through `cli_path`. Behaviour is
chosen by a marker in the prompt:
    [[fake:quota]]    usage limit (rate_limit_event rejected + 429)
    [[fake:ratelimit]] transient 429 without usage-limit wording
    [[fake:error]]    error result
    [[fake:refusal]]  refusal stop reason
    [[fake:auth]]     authentication_failed
    [[fake:auth401]]  API error 401 only (no assistant error)
    [[fake:sleep]]    never answers (timeouts)
    anything else     "OK" with usage and total_cost_usd
If FAKE_CLAUDE_RECORD is set, argv and selected env go to that JSON file.
Never used in production: only when RUNTIME_CLI_PATH points here.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid

SESSION = str(uuid.uuid4())


def emit(obj: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()
    if obj.get("type") == "result" and obj.get("is_error"):
        # Like the real CLI: a failed run ends with an error result, then exit 1
        # (the SDK turns that into ResultError after yielding the result).
        sys.exit(1)


def record() -> None:
    path = os.environ.get("FAKE_CLAUDE_RECORD")
    if not path:
        return
    argv = sys.argv[1:]
    system_file = (
        argv[argv.index("--system-prompt-file") + 1] if "--system-prompt-file" in argv else None
    )
    data = {
        "argv": argv,
        "cwd": os.getcwd(),
        "home": os.environ.get("HOME"),
        "has_oauth_token": bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")),
        "has_api_key": "ANTHROPIC_API_KEY" in os.environ,
        "system_prompt": open(system_file).read() if system_file else None,  # noqa: SIM115
        "cwd_entries": os.listdir(os.getcwd()),
    }
    with open(path, "w") as fh:
        json.dump(data, fh)


def arg(name: str) -> str | None:
    argv = sys.argv[1:]
    return argv[argv.index(name) + 1] if name in argv else None


def result(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "result",
        "subtype": "success",
        "duration_ms": 12,
        "duration_api_ms": 10,
        "is_error": False,
        "num_turns": 1,
        "session_id": SESSION,
        "stop_reason": "end_turn",
        "uuid": str(uuid.uuid4()),
    }
    base.update(kw)
    return base


def answer(prompt: str) -> None:
    model = arg("--model") or "claude-sonnet-5-5"
    emit({"type": "system", "subtype": "init", "session_id": SESSION, "model": model, "tools": []})
    if "[[fake:sleep]]" in prompt:
        time.sleep(3600)
    if "[[fake:quota]]" in prompt:
        reset = int(time.time()) + 3600
        emit(
            {
                "type": "rate_limit_event",
                "uuid": str(uuid.uuid4()),
                "session_id": SESSION,
                "rate_limit_info": {
                    "status": "rejected",
                    "resetsAt": reset,
                    "rateLimitType": "five_hour",
                },
            }
        )
        emit(
            {
                "type": "assistant",
                "session_id": SESSION,
                "error": "rate_limit",
                "message": {
                    "model": model,
                    "content": [{"type": "text", "text": f"Claude AI usage limit reached|{reset}"}],
                },
            }
        )
        emit(
            result(
                is_error=True, api_error_status=429, result=f"Claude AI usage limit reached|{reset}"
            )
        )
        return
    if "[[fake:ratelimit]]" in prompt:
        emit(
            {
                "type": "assistant",
                "session_id": SESSION,
                "error": "rate_limit",
                "message": {
                    "model": model,
                    "content": [{"type": "text", "text": "Too many requests"}],
                },
            }
        )
        emit(result(is_error=True, api_error_status=429, result="Too many requests"))
        return
    if "[[fake:auth]]" in prompt:
        emit(
            {
                "type": "assistant",
                "session_id": SESSION,
                "error": "authentication_failed",
                "message": {"model": model, "content": [{"type": "text", "text": "Invalid token"}]},
            }
        )
        emit(result(is_error=True, result="Invalid token"))
        return
    if "[[fake:auth401]]" in prompt:
        emit(
            result(
                is_error=True,
                api_error_status=401,
                result="API Error: 401 authentication_error",
                terminal_reason="api_error",
            )
        )
        return
    if "[[fake:error]]" in prompt:
        emit(result(subtype="error_during_execution", is_error=True))
        return
    if "[[fake:refusal]]" in prompt:
        emit(
            {
                "type": "assistant",
                "session_id": SESSION,
                "message": {
                    "model": model,
                    "content": [{"type": "text", "text": "I can't help with that."}],
                },
            }
        )
        emit(result(stop_reason="refusal", result="I can't help with that."))
        return
    text = "OK"
    if "--include-partial-messages" in sys.argv:
        for piece in ("O", "K"):
            emit(
                {
                    "type": "stream_event",
                    "uuid": str(uuid.uuid4()),
                    "session_id": SESSION,
                    "event": {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": piece},
                    },
                }
            )
    emit(
        {
            "type": "assistant",
            "session_id": SESSION,
            "message": {"model": model, "content": [{"type": "text", "text": text}]},
        }
    )
    usage = {
        "input_tokens": 12,
        "output_tokens": 3,
        "cache_read_input_tokens": 5,
        "cache_creation_input_tokens": 7,
        "cache_creation": {"ephemeral_1h_input_tokens": 4, "ephemeral_5m_input_tokens": 3},
        "output_tokens_details": {"thinking_tokens": 2},
    }
    structured = {"answer": "OK"} if arg("--json-schema") else None
    emit(
        result(
            result=text,
            usage=usage,
            total_cost_usd=0.0000123,
            structured_output=structured,
            modelUsage={model: {"inputTokens": 12, "outputTokens": 3}},
        )
    )


def main() -> None:
    if "-v" in sys.argv or "--version" in sys.argv:
        print("2.1.286 (Claude Code)")
        return
    record()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if msg.get("type") == "control_request":
            req = msg["request"]
            response: dict[str, object] = {}
            if req.get("subtype") == "initialize":
                response = {"commands": [], "models": [], "account": {}}
            emit(
                {
                    "type": "control_response",
                    "response": {
                        "subtype": "success",
                        "request_id": msg["request_id"],
                        "response": response,
                    },
                }
            )
        elif msg.get("type") == "user":
            content = msg["message"]["content"]
            prompt = (
                content
                if isinstance(content, str)
                else " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            )
            answer(prompt)


if __name__ == "__main__":
    main()
