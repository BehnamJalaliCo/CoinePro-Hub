"""⟨1.37⟩ Contract §59.7, §59.11 (prompt 38): n8n's tick is signed.

`hq-flows` (automations/n8n/hq-flows.json) POSTs `/internal/v1/flows/tick` each minute with
`X-HQ-Signature: t=<ts>,v1=hmac_sha256(secret, "<t>.<body>")` (kv/hq/n8n); an unsigned or
wrongly signed tick is a 401 and changes nothing; a signed one stamps the clock. The workflow file
holds no model key and calls no model.
"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api.hub import Hub
from hq_api.lines import signing

TICK = "/internal/v1/flows/tick"
# the repository's automations/ (the test image mounts only apps/api: then the check is skipped)
WORKFLOW = (
    Path(__file__).resolve().parents[1].parent.parent / "automations" / "n8n" / "hq-flows.json"
)


async def last_tick(su: Any) -> Any:
    return await su.fetchval(
        """SELECT f.last_tick_at FROM growth.flow_clock f JOIN core.companies c
               ON c.id = f.company_id WHERE c.kind = 'holding'"""
    )


async def test_an_unsigned_tick_is_refused_and_a_signed_one_stamps_the_clock(
    client: httpx.AsyncClient, hub: Hub, su: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "test-n8n-secret-" + "x" * 16
    monkeypatch.setattr(hub, "secrets", replace(hub.secrets, n8n_secret=secret))
    before = await last_tick(su)
    body = b'{"at": "now"}'
    r = await client.post(TICK, content=body, headers={"Content-Type": "application/json"})
    assert r.status_code == 401
    bad = signing.sign("another-secret", body)
    r = await client.post(TICK, content=body, headers={signing.HEADER: bad})
    assert r.status_code == 401
    old = signing.sign(secret, body, now=int(time.time()) - 3600)
    r = await client.post(TICK, content=body, headers={signing.HEADER: old})
    assert r.status_code == 401
    tampered = signing.sign(secret, body)
    r = await client.post(TICK, content=b'{"at": "later"}', headers={signing.HEADER: tampered})
    assert r.status_code == 401
    assert await last_tick(su) == before
    r = await client.post(TICK, content=body, headers={signing.HEADER: signing.sign(secret, body)})
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "n8n"
    after = await last_tick(su)
    assert after is not None and after != before
    assert abs((after - datetime.now(UTC)).total_seconds()) < 60


def test_the_workflow_ticks_each_minute_signed_and_calls_no_model() -> None:
    if not WORKFLOW.is_file():
        pytest.skip("automations/ is not mounted here")
    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    assert wf["name"] == "hq-flows"
    nodes = {n["name"]: n for n in wf["nodes"]}
    crons = {n["parameters"]["rule"]["interval"][0]["expression"]
             for n in nodes.values() if n["type"].endswith("scheduleTrigger")}  # fmt: skip
    assert crons == {"* * * * *", "30 21 * * *"} and wf["settings"]["timezone"] == "Asia/Tehran"
    urls = {n["parameters"]["url"] for n in nodes.values() if n["type"].endswith("httpRequest")}
    assert urls == {"http://api:8000/internal/v1/flows/tick",
                    "http://api:8000/internal/v1/flows/summary"}  # fmt: skip
    code = " ".join(n["parameters"]["jsCode"] for n in nodes.values() if n["type"].endswith("code"))
    assert "HQ_SIGNING_SECRET" in code and "createHmac('sha256'" in code
    text = WORKFLOW.read_text(encoding="utf-8").lower()
    assert not any(w in text for w in ("openai", "anthropic", "gemini", "api_key", "apikey"))
