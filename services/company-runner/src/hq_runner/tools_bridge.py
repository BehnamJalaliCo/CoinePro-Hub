"""⟨0.3.5⟩ The hub's tools inside a direct session (contract §54).

A direct session is the holder of an owner's session working as one Claude Code session on the
workshop. What it does with the hub (read a figure, make the narrator's voice, ask the owner,
name today's topic, ...) goes through the hub's own Tool Gateway, as for any agent. This module
is the path between the two, in two halves:

    `hq-runner mcp-tools`   a small MCP server (stdio, JSON-RPC 2.0, one JSON a line) that
                            Claude Code starts from `--mcp-config`. It holds no secret: every
                            `tools/list` and `tools/call` is one JSON line to the job's own
                            unix socket (HQ_RUNNER_TOOLS_SOCK).
    serve()                 that socket, in the runner: `{op: "list"}` and `{op: "call", name,
                            args}` are carried to the hub with the runner's own token
                            (`GET /runners/jobs/{id}/tools`, `POST …/tools/call`). The token
                            never goes behind the workshop's wall.

The session names a tool `mcp__hq__<name>`; the hub maps the name back to its own tool, and
its gateway decides the call (the role's tools, the policy, the class, the audit row).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TextIO

import hq_runner
from hq_runner.sandbox import _short

SERVER = "hq"  # the MCP server's name: its tools are mcp__hq__<name>
ALLOW = f"mcp__{SERVER}"  # the permission that lets the session call them without asking
SOCK_ENV = "HQ_RUNNER_TOOLS_SOCK"
LINE = 4 * 1024 * 1024
CALL_TIMEOUT_S = 175.0
PROTOCOL = "2025-06-18"
UNREACHABLE = {"outcome": "error", "class": None, "code": "hub_unreachable", "ref": None}

Lister = Callable[[], Awaitable[dict[str, Any]]]
Caller = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def mcp_config(sock: Path) -> dict[str, Any]:
    """What `--mcp-config` reads: this same installation of the runner as the one MCP server."""
    root = str(Path(hq_runner.__file__).resolve().parent.parent)
    return {
        "mcpServers": {
            SERVER: {
                "type": "stdio",
                "command": sys.executable,
                "args": ["-m", "hq_runner", "mcp-tools"],
                "env": {"PYTHONPATH": root, SOCK_ENV: str(sock)},
            }
        }
    }


# ------------------------------------------------------------- the runner's side --
async def serve(path: Path, lister: Lister, caller: Caller) -> asyncio.AbstractServer:
    """The job's tools socket: one JSON line in, one JSON line out, for this turn only."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        answer: dict[str, Any] = dict(UNREACHABLE, code="bad_request")
        try:
            line = await asyncio.wait_for(reader.readline(), 30)
            obj = json.loads(line or b"{}")
            if isinstance(obj, dict) and obj.get("op") == "list":
                answer = await lister()
            elif isinstance(obj, dict) and obj.get("op") == "call":
                args = obj.get("args")
                answer = await caller(
                    str(obj.get("name") or ""), args if isinstance(args, dict) else {}
                )
        except (ValueError, TimeoutError, asyncio.LimitOverrunError):
            pass
        except Exception as exc:  # noqa: BLE001 - the session gets an answer whatever happened
            answer = dict(UNREACHABLE, detail=type(exc).__name__)
        with contextlib.suppress(Exception):
            writer.write(json.dumps(answer, ensure_ascii=False).encode() + b"\n")
            await writer.drain()
        with contextlib.suppress(Exception):
            writer.close()

    with contextlib.suppress(FileNotFoundError):
        path.unlink()  # noqa: ASYNC240 - one local unlink
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with _short(path) as short:
            sock.bind(short)
        os.chmod(path, 0o600)
        return await asyncio.start_unix_server(handle, sock=sock, limit=LINE)
    except BaseException:
        sock.close()
        raise


# ----------------------------------------------------------- the session's side --
def ask(sock_path: str, obj: dict[str, Any], timeout: float = CALL_TIMEOUT_S) -> dict[str, Any]:
    """One question to the runner over the job's socket; an error object when it cannot be asked."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s, _short(sock_path) as short:
            s.settimeout(timeout)
            s.connect(short)
            s.sendall(json.dumps(obj, ensure_ascii=False).encode() + b"\n")
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(1 << 16)
                if not chunk:
                    break
                data += chunk
                if len(data) > LINE:
                    break
        got = json.loads(data or b"{}")
    except (OSError, ValueError) as exc:
        return dict(UNREACHABLE, detail=type(exc).__name__)
    return got if isinstance(got, dict) else dict(UNREACHABLE)


def _result(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def tool_rows(listed: dict[str, Any]) -> list[dict[str, Any]]:
    """The hub's list as MCP names it."""
    out = []
    for t in listed.get("tools") or []:
        if not isinstance(t, dict) or not isinstance(t.get("name"), str):
            continue
        schema = t.get("input_schema")
        out.append(
            {
                "name": t["name"],
                "description": str(t.get("description") or "")[:4000],
                "inputSchema": schema if isinstance(schema, dict) else {"type": "object"},
            }
        )
    return out


def call_result(got: dict[str, Any]) -> dict[str, Any]:
    """The gateway's outcome as the session reads it: the whole outcome as text; an error when
    it is not `ok` (the session reads the code, the fields and the Persian hint)."""
    shown = {k: v for k, v in got.items() if v is not None and k != "detail"}
    return {
        "content": [{"type": "text", "text": json.dumps(shown, ensure_ascii=False)}],
        "isError": got.get("outcome") != "ok",
    }


def answer_of(msg: Any, sock_path: str) -> dict[str, Any] | None:
    """One JSON-RPC message in, its answer out (None for a notification)."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _error(None, -32600, "invalid request")
    method, req_id = msg.get("method"), msg.get("id")
    if "id" not in msg:
        return None  # a notification (notifications/initialized, cancelled, ...)
    raw = msg.get("params")
    params: dict[str, Any] = raw if isinstance(raw, dict) else {}
    if method == "initialize":
        return _result(
            req_id,
            {
                "protocolVersion": str(params.get("protocolVersion") or PROTOCOL),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER, "version": hq_runner.__version__},
            },
        )
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": tool_rows(ask(sock_path, {"op": "list"}, 60.0))})
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or not name:
            return _error(req_id, -32602, "a tool's name is needed")
        args = params.get("arguments")
        got = ask(
            sock_path, {"op": "call", "name": name, "args": args if isinstance(args, dict) else {}}
        )
        return _result(req_id, call_result(got))
    return _error(req_id, -32601, f"unknown method: {method}")


def main(stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    """`hq-runner mcp-tools`: serve MCP on stdio until the session closes it."""
    src, out = stdin or sys.stdin, stdout or sys.stdout
    sock_path = os.environ.get(SOCK_ENV, "")
    for line in src:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply: dict[str, Any] | None = _error(None, -32700, "parse error")
        else:
            reply = answer_of(msg, sock_path)
        if reply is not None:
            out.write(json.dumps(reply, ensure_ascii=False) + "\n")
            out.flush()
    return 0
