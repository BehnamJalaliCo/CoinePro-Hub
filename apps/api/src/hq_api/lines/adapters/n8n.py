"""`n8n`: a named n8n workflow; the step waits for its signed callback (§30.2, §30.4).

First rule (n8n), last AI: this is for rule work (fetching, formatting, filing). n8n holds no model
key and calls no model.

The contract with the engine:

1. This adapter POSTs the workflow's webhook `{n8n_url}/webhook/<settings.workflow>` (n8n's own
   base URL is `HQ_N8N_URL`, default the compose service `http://n8n:5678`, reached on the hub's
   internal network, never published) with the body below, signed by `lines.signing.sign` (header
   `X-HQ-Signature`, secret `secret` of OpenBao `kv/hq/n8n`).
2. It returns `StepOutput(data={"waiting": true, "token": <run_ref>:<step key>, ...})`. The ENGINE
   reads `data["waiting"]` as «park this step as `waiting`» and keeps the step until the callback.
3. n8n answers with `POST /internal/v1/lines/callback`, signed the same way, body
   `{"token": "<run_ref>:<step key>", "ok": true|false, "text": "...", "data": {...},
   "error_fa": "..."}` (the demo workflow `automations/n8n/line-callback-demo.json` does exactly
   this). The ENGINE verifies the signature (`lines.signing.verify`), finds the step by `token` and
   finishes it with that text and data (or fails it with `error_fa`).

Body sent to n8n: {"token", "run", "line", "company", "platform", "step", "prompt", "settings",
"inputs": {<step key>: {"text" (≤ 4000 chars), "file_id", "data"}},
"callback": "http://api:8000/internal/v1/lines/callback" (HQ_LINES_CALLBACK_URL)}.
A dry run does not call n8n (rule steps may have effects) and answers with `data.dry`.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from hq_api.lines import signing
from hq_api.lines.adapters import _common as C
from hq_api.lines.base import StepContext, StepFailed, StepOutput, register

DEFAULT_URL = "http://n8n:5678"
# /internal never goes through Caddy: n8n reaches the api on the hub's internal network
DEFAULT_CALLBACK = "http://api:8000/internal/v1/lines/callback"
TEXT_CAP = 4000
TIMEOUT_S = 20.0
SEND_OVERRIDE: Any = None  # tests: an async callable (url, body: bytes, headers) -> (status, text)


def base_url() -> str:
    return os.environ.get("HQ_N8N_URL", DEFAULT_URL).rstrip("/")


def summary(ctx: StepContext) -> dict[str, Any]:
    return {
        "token": f"{ctx.run_ref}:{ctx.step.get('key')}",
        "run": ctx.run_ref,
        "line": ctx.line_ref,
        "company": ctx.company,
        "platform": ctx.platform,
        "step": ctx.step.get("key"),
        "prompt": ctx.prompt,
        "settings": ctx.step.get("settings") or {},
        "inputs": {
            k: {"text": (o.text or "")[:TEXT_CAP] or None, "file_id": o.file_id, "data": o.data}
            for k, o in ctx.inputs.items()
        },
        "callback": os.environ.get("HQ_LINES_CALLBACK_URL", DEFAULT_CALLBACK),
    }


async def _post(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
    if SEND_OVERRIDE is not None:
        return await SEND_OVERRIDE(url, body, headers)  # type: ignore[no-any-return]
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, trust_env=False) as http:
            resp = await http.post(url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        raise StepFailed(
            "n8n در دسترس نیست (سرویس خاموش یا شبکه قطع است).", code="n8n_down", retry=True
        ) from exc
    return resp.status_code, resp.text[:300]


class N8n:
    kind = "n8n"

    async def run(self, ctx: StepContext) -> StepOutput:
        workflow = str(C.setting(ctx, "workflow", "") or "").strip()
        if not workflow or not all(c.isalnum() or c in "-_" for c in workflow):
            raise StepFailed(
                "نام گردش‌کار n8n در تنظیمات مرحله نیست یا نادرست است.", code="no_workflow"
            )
        body_doc = summary(ctx)
        if ctx.dry:
            return StepOutput(text="آزمایشی: n8n صدا زده نشد.", via="dry",
                              data={"dry": True, "workflow": workflow, "token": body_doc["token"]})  # fmt: skip
        await C.check_unlocked(ctx.hub)
        secret = str((await C.bao_dict(ctx.hub, "hq/n8n")).get("secret") or "")
        if not secret:
            raise StepFailed("رمز امضای n8n در OpenBao (kv/hq/n8n) ثبت نشده است.", code="no_secret")
        body = json.dumps(body_doc, ensure_ascii=False, sort_keys=True).encode()
        headers = {"Content-Type": "application/json", signing.HEADER: signing.sign(secret, body)}
        del secret
        status, _ = await _post(f"{base_url()}/webhook/{workflow}", body, headers)
        if not 200 <= status < 300:
            raise StepFailed(
                f"n8n گردش‌کار «{workflow}» را نپذیرفت (کد {status}).", code="n8n_refused",
                retry=status >= 500,
            )  # fmt: skip
        return StepOutput(
            via="n8n",
            data={"waiting": True, "token": body_doc["token"], "workflow": workflow},
        )


register(N8n())
