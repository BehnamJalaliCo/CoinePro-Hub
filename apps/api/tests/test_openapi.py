"""The OpenAPI 3.1 contract: committed file == code, documented operations,
and Schemathesis fuzzing of every operation without a single 5xx."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Callable
from typing import Any

from hq_api.openapi_export import PATH, render

from .conftest import agent_headers
from .test_control_treasury_stream import serve


def test_committed_document_matches_the_code(app: Any) -> None:
    """CI fails when openapi/hq-api.v1.json drifts from the code (`make openapi`)."""
    assert PATH.read_text(encoding="utf-8") == render(app.openapi())


def test_every_operation_is_documented(app: Any) -> None:
    doc = app.openapi()
    assert doc["openapi"].startswith("3.1")
    seen: set[str] = set()
    for path, item in doc["paths"].items():
        for method, op in item.items():
            where = f"{method.upper()} {path}"
            assert op.get("operationId") and op["operationId"] not in seen, where
            seen.add(op["operationId"])
            assert op.get("description"), f"{where}: no description"
            body = op.get("requestBody", {}).get("content", {}).get("application/json")
            assert body is None or "example" in body, f"{where}: no request example"
            if path not in ("/api/v1/health",) and not path.startswith(
                "/api/v1/auth/passkey/login"
            ):
                assert "401" in op["responses"] or "422" in op["responses"], (
                    f"{where}: no error responses"
                )
    assert len(seen) >= 100


async def _schemathesis(url: str, headers: dict[str, str], *args: str) -> tuple[int, str]:
    cmd = [
        sys.executable,
        "-m",
        "schemathesis.cli",
        "run",
        f"{url}/api/v1/openapi.json",
        "--url",
        url,
        "--checks",
        "not_a_server_error",
        "--max-examples",
        os.environ.get("HQ_FUZZ_EXAMPLES", "8"),
        # The SSE streams never end on their own (heartbeats keep them open).
        "--exclude-path-regex",
        "^/api/v1/(stream|threads/[^/]+/live)$",
        "--generation-database",
        "none",
        "--no-color",
        "--request-timeout",
        "30",
        "--seed",
        "4040",
        *args,
    ]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd="/tmp"
    )
    out, _ = await proc.communicate()
    return proc.returncode or 0, out.decode(errors="replace")


async def test_schemathesis_finds_no_server_errors(
    app: Any, owner: dict[str, str], new_company: Callable[..., Any], relay: None
) -> None:
    co = (await new_company())["code"]
    async with serve(app) as url:
        code, out = await _schemathesis(url, owner, "--include-path-regex", "^/api/v1/")
        assert code == 0, out[-6000:]
        code, out = await _schemathesis(
            url, await agent_headers(f"{co}-CEO"), "--include-path-regex", "^/internal/v1/"
        )
        assert code == 0, out[-6000:]
    assert json.dumps({"ok": True})
