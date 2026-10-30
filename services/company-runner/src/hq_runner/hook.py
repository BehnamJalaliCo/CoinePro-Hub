"""`hq-runner classify-hook`: the PreToolUse hook of a `claude` job.

Claude Code runs it before every Bash call with the call as JSON on stdin
({tool_name, tool_input: {command}, ...}). It asks the hub
(POST /runners/classify {cmd}) and:
  - category null   exit 0, the call goes ahead
  - a category      exit 2, the call is blocked; the message on stderr goes back
                    to Claude. The hub raises the owner's seal card.
  - hub unreachable exit 2 as well (fail closed): an unclassified command never runs.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, TextIO

import httpx

from hq_runner import __version__
from hq_runner.config import Config, load
from hq_runner.hub import API, classify_status, problem_code
from hq_runner.net import sync_transport

BLOCKED = (
    "Blocked by HQ: this command is in the seal-required category '{category}'. "
    "The owner has been asked to approve it in the HQ app; do not retry it or work around it. "
    "Stop and report that the step is waiting for the owner's seal. / "
    "این دستور مُهر مالک میخواهد و در اپ ستاد منتظر تأیید است."
)
UNREACHABLE = (
    "Blocked by HQ: the command could not be classified ({reason}), so it was not run. "
    "Try again later. / دستور طبقه‌بندی نشد و اجرا نشد."
)


def classify(
    cfg: Config,
    cmd: str,
    *,
    via: str,
    job_id: str | None,
    transport: httpx.BaseTransport | None = None,
) -> str | None:
    """The hub's category for `cmd`, or None. Raises RuntimeError when it cannot tell."""
    pinned = cfg.hub_ip if via == "private" else None
    headers = {
        "Authorization": f"Bearer {cfg.runner_token}",
        "User-Agent": f"hq-runner/{__version__}",
        "X-HQ-Runner-Version": __version__,
        "X-HQ-Runner-Via": via,
    }
    if job_id:
        headers["X-HQ-Runner-Job"] = job_id
    tr = transport or sync_transport(cfg.hub, pinned, cfg.ca_file)
    try:
        with httpx.Client(base_url=cfg.hub.rstrip("/"), transport=tr, timeout=20.0) as client:
            resp = client.post(API + "/runners/classify", json={"cmd": cmd}, headers=headers)
    except httpx.HTTPError as exc:
        raise RuntimeError(type(exc).__name__) from exc
    err = classify_status(resp)
    if err is not None:
        code, _ = problem_code(resp)
        raise RuntimeError(f"hub answered {resp.status_code}{' ' + code if code else ''}")
    body: Any = resp.json()
    cat = body.get("category") if isinstance(body, dict) else None
    return str(cat) if cat else None


def _record(cmd: str, category: str) -> None:
    path = os.environ.get("HQ_RUNNER_HOOK_EVENTS")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"cmd": cmd, "category": category}) + "\n")
    except OSError:
        pass


def main(
    job_id: str | None,
    *,
    stdin: TextIO | None = None,
    stderr: TextIO | None = None,
    transport: httpx.BaseTransport | None = None,
) -> int:
    err_out = stderr or sys.stderr
    try:
        payload = json.load(stdin or sys.stdin)
    except ValueError:
        print(UNREACHABLE.format(reason="bad hook input"), file=err_out)
        return 2
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    cmd = str((payload.get("tool_input") or {}).get("command") or "")
    if not cmd.strip():
        return 0
    try:
        env_cfg = os.environ.get("HQ_RUNNER_CONFIG")
        cfg = load(Path(env_cfg) if env_cfg else None)
    except (OSError, ValueError):
        cfg = None
    if cfg is None:
        print(UNREACHABLE.format(reason="runner not paired"), file=err_out)
        return 2
    via = os.environ.get("HQ_RUNNER_VIA") or ("private" if cfg.hub_ip else "public")
    try:
        category = classify(
            cfg,
            cmd,
            via=via,
            job_id=job_id or os.environ.get("HQ_RUNNER_JOB_ID"),
            transport=transport,
        )
    except RuntimeError as exc:
        if via == "private" and transport is None:
            try:
                category = classify(cfg, cmd, via="public", job_id=job_id)
            except RuntimeError as exc2:
                print(UNREACHABLE.format(reason=str(exc2)), file=err_out)
                return 2
        else:
            print(UNREACHABLE.format(reason=str(exc)), file=err_out)
            return 2
    if category:
        _record(cmd, category)
        print(BLOCKED.format(category=category), file=err_out)
        return 2
    return 0
