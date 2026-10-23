"""Request fingerprints for the waste report (prompt 12 §8, contract §21.7).

The ledger keeps HASHES only, never the text: `request_sha256` of the whole
request (model, system, turns, schema; an image by its bytes' digest) finds a
duplicate call; `prefix_sha256` of what a prompt cache would hold (model and
system) finds a cache miss. Both go into llm.calls.meta.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from llm_router.schemas import RunRequest


def _turns(req: RunRequest) -> list[Any]:
    out: list[Any] = []
    for m in req.as_messages():
        if isinstance(m.content, str):
            out.append([m.role, m.content])
            continue
        blocks = []
        for b in m.content:
            data = b.model_dump(mode="json")
            raw = data.get("data")
            if isinstance(raw, str) and len(raw) > 256:  # an image: its digest, not its bytes
                data["data"] = hashlib.sha256(raw.encode()).hexdigest()
            blocks.append(data)
        out.append([m.role, blocks])
    return out


def of(req: RunRequest, model: str | None) -> dict[str, str]:
    """{request_sha256, prefix_sha256?} of a request (hex digests only)."""
    body = {
        "model": model,
        "effort": req.effort,
        "system": req.system or "",
        "turns": _turns(req),
        "schema": req.json_schema,
    }
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    out = {"request_sha256": hashlib.sha256(raw.encode()).hexdigest()}
    if req.system:
        prefix = json.dumps([model, req.system], ensure_ascii=False, separators=(",", ":"))
        out["prefix_sha256"] = hashlib.sha256(prefix.encode()).hexdigest()
    return out
