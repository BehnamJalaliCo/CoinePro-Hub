"""OCR on the hub (prompt 14 §4, contract §23.9).

The `ocr` service (services/ocr: Tesseract 5 with `fas` + `eng`, pinned
traineddata, no internet, the opt-in profile `ocr`) is reached by the worker
only, on the internal network hq-ocr (`HQ_OCR_URL`; empty: the profile is off).
One job at a time: the service answers 429 to a second one, and the queue
(the worker's ArchiveOcrQueue) takes one file per pass.

    through_worker(hub, storage_key, mime) -> result | None
        the api's path (an intake): a Temporal workflow runs the activity on
        the worker and the api waits up to archive_ocr_wait_s. None: the
        profile is off, busy, or the wait ran out (the queue takes it later).
    run(settings, data, mime) -> result     the worker's path (activity, queue)
    as_text(result, low) -> {text, confidence, low, pages}

A result is {"state": "ok"|"off"|"busy"|"failed", "pages": [...], ...}.
OCR is code (no model, no outside call): rule-only, so the queue may run
while the holding is locked; the text it finds is scanned for secrets like
any other before it is kept.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from hq_common import persian

log = logging.getLogger("hq_api.archive.ocr")
OVERRIDE: Any = None  # tests: an object with `async run(data, mime) -> dict`
TIMEOUT_S = 150.0
MAX_PAGES = 50


async def run(settings: Any, data: bytes, mime: str) -> dict[str, Any]:
    if OVERRIDE is not None:
        out: dict[str, Any] = await OVERRIDE.run(data, mime)
        return out
    url = getattr(settings, "ocr_url", "") or ""
    if not url:
        return {"state": "off"}
    try:
        async with httpx.AsyncClient(base_url=url.rstrip("/"), timeout=TIMEOUT_S) as c:
            resp = await c.post(
                "/v1/ocr",
                params={"max_pages": MAX_PAGES},
                content=data,
                headers={"Content-Type": mime},
            )
    except httpx.HTTPError as exc:
        log.warning("ocr unreachable", extra={"error": type(exc).__name__})
        return {"state": "busy"}
    if resp.status_code == 429:
        return {"state": "busy"}
    if resp.status_code != 200:
        code = ""
        try:
            code = str(resp.json().get("error") or "")[:40]
        except ValueError:
            pass
        return {"state": "failed", "error": code or f"http_{resp.status_code}"}
    body = resp.json()
    return {"state": "ok", **body}


async def through_worker(hub: Any, storage_key: str, mime: str) -> dict[str, Any] | None:
    """The api's path: the worker reads the file and asks the service."""
    if OVERRIDE is not None:
        data = await hub.storage.get(storage_key)
        res = await run(hub.settings, data, mime)
        return res if res.get("state") in ("ok", "failed") else None
    from hq_api import workflows_client

    try:
        res = await workflows_client.archive_ocr(
            hub, storage_key, mime, hub.settings.archive_ocr_wait_s
        )
    except Exception:  # noqa: BLE001 - no worker, a timeout: the queue takes it
        return None
    return res if res.get("state") in ("ok", "failed") else None


def as_text(res: dict[str, Any], low: float) -> dict[str, Any]:
    pages = res.get("pages") or []
    texts = [str(p.get("text") or "") for p in pages]
    text = persian.normalise("\n\n".join(t for t in texts if t.strip()))
    conf = res.get("confidence")
    lows = [
        int(p.get("n") or i + 1)
        for i, p in enumerate(pages)
        if p.get("confidence") is not None and float(p["confidence"]) < low
    ]
    return {
        "text": text[:400_000] or None,
        "confidence": max(0.0, min(1.0, float(conf))) if conf is not None else None,
        "low": lows,
        "pages": len(pages) or None,
    }
