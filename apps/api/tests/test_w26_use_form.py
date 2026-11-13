"""⟨1.37⟩ Contract §59.4 (prompt 38): «در شرکت دیگر به کار ببر», one form.

`dry` is only the preview (each day in plain Persian, the first publish time, the cost, the
warnings the hub settles itself); without it the membership (its version pinned), the line, the
standing word and the flow automation are made in one transaction; a company that already runs the
playbook's flow is a 409. The narrator's sample is a short voice, made once a day.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from hq_api.domain import flow_auto as FA
from hq_api.domain import speech_make as SM
from hq_api.hub import Hub

from .conftest import idem
from .test_w26_flow_automation import (
    API,
    STEPS,
    a_playbook,
    form,
    quiet_flows,  # noqa: F401 - the fixture
)


async def test_the_preview_says_each_day_and_makes_nothing(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], owner_db: Any,
    new_company: Any, su: Any,
) -> None:  # fmt: skip
    owner = owner_session["headers"]
    pref = await a_playbook(hub, owner_db)
    co = await new_company()
    body = {**form(co["code"]), "dry": True}
    r = await client.post(f"{API}/playbooks/{pref}/use", json=body, headers=owner)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["lines_fa"][0].startswith("شروع: ۹۰ دقیقه پیش از ساعت انتشار")
    assert any("سناریو و متن" in x and "ChatGPT" in x for x in p["lines_fa"])
    assert any("@pro.chart" in x and "استوری" in x for x in p["lines_fa"])
    assert p["first_at"] is not None and p["cost_estimate_usd"] is None
    warned = {w["key"]: w for w in p["warnings"]}
    assert warned["publish_path"]["by_hub"] is True  # no Instagram path registered yet
    assert warned["seats"]["by_hub"] is True and "استخدام" in warned["seats"]["text_fa"]
    assert not await su.fetchval("SELECT 1 FROM growth.memberships WHERE company_id = $1", co["id"])
    assert not await su.fetchval("SELECT 1 FROM growth.automations WHERE playbook = $1", pref)


@pytest.mark.usefixtures("quiet_flows")
async def test_the_form_makes_the_member_its_line_its_word_and_its_flow(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], owner_db: Any,
    new_company: Any, su: Any,
) -> None:  # fmt: skip
    owner = owner_session["headers"]
    pref = await a_playbook(hub, owner_db)
    co = await new_company()
    body = form(co["code"], narrator={"voice": "Charon", "style_fa": "آرام"})
    r = await client.post(f"{API}/playbooks/{pref}/use", json=body, headers={**owner, **idem()})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["playbook"]["ref"] == pref
    assert out["member"]["company"] == co["code"]
    auto = out["automation"]
    assert auto["kind"] == "flow" and auto["state"] == "on" and auto["version"] == 1
    assert auto["mode"] == "auto" and auto["account"] == "pro.chart" and auto["story"] is True
    assert auto["schedule"]["at"] == "09:30" and auto["budget"]["per_day_usd"] == 8
    m = await su.fetchrow(
        "SELECT * FROM growth.memberships WHERE company_id = $1 AND automation = $2",
        co["id"], auto["ref"],
    )  # fmt: skip
    assert m is not None and m["version"] == 1 and m["state"] == "on"
    word = json.loads(m["publish"])
    assert word["mode"] == "auto" and word["account"] == "pro.chart" and word["story"] is True
    assert word["at"] == "09:30" and word["best"] is False
    line = await su.fetchrow("SELECT * FROM lines.lines WHERE ref = $1", auto["line"])
    assert line["template"] == "flow" and line["template_version"] == 1
    assert line["state"] == "on" and line["mode"] == "auto" and line["schedule"] is None
    assert line["platform"] == "instagram_reel"
    assert json.loads(line["channel"]) == {"kind": "instagram", "subject": "@pro.chart"}
    assert [s["key"] for s in json.loads(line["steps"])] == [s["key"] for s in STEPS]
    row = await su.fetchrow("SELECT * FROM growth.automations WHERE ref = $1", auto["ref"])
    assert row["kind"] == "flow" and row["playbook"] == pref and row["sealed_at"] is not None
    assert row["scope"] == "company" and row["company_id"] == co["id"]
    narrator = await su.fetchrow("SELECT * FROM media.narrators WHERE company_id = $1", co["id"])
    assert narrator["voice"] == "Charon" and narrator["style_fa"] == "آرام"
    assert (
        await su.fetchval(
            """SELECT count(*) FROM audit.entries WHERE action = 'playbook.use' AND target_ref = $1
             AND action_class = 'A3'""",
            pref,
        )
        == 1
    )
    # the same company again: 409, nothing made twice
    r = await client.post(f"{API}/playbooks/{pref}/use", json=form(co["code"]),
                          headers={**owner, **idem()})  # fmt: skip
    assert r.status_code == 409 and r.json()["message_fa"] == FA.TAKEN_FA
    r = await client.post(f"{API}/playbooks/{pref}/use", json={**form(co["code"]), "dry": True},
                          headers=owner)  # fmt: skip
    assert r.status_code == 409
    assert (
        await su.fetchval("SELECT count(*) FROM growth.automations WHERE playbook = $1", pref) == 1
    )


async def test_the_form_refuses_what_does_not_hold(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], owner_db: Any,
    new_company: Any,
) -> None:  # fmt: skip
    owner = owner_session["headers"]
    co = await new_company()
    draft = await a_playbook(hub, owner_db, sealed=False)
    r = await client.post(f"{API}/playbooks/{draft}/use", json=form(co["code"]),
                          headers={**owner, **idem()})  # fmt: skip
    assert r.status_code == 409 and r.json()["message_fa"] == FA.NO_VERSION_FA
    pref = await a_playbook(hub, owner_db)
    fixed = form(co["code"], time={"mode": "fixed", "story": True})
    r = await client.post(f"{API}/playbooks/{pref}/use", json=fixed, headers={**owner, **idem()})
    assert r.status_code == 422
    r = await client.post(f"{API}/playbooks/{pref}/use", json=form(co["code"]), headers=owner)
    assert r.status_code == 422  # no Idempotency-Key
    no_steps = await a_playbook(hub, owner_db, steps=[])
    r = await client.post(f"{API}/playbooks/{no_steps}/use", json=form(co["code"]),
                          headers={**owner, **idem()})  # fmt: skip
    assert r.status_code == 422 and r.json()["message_fa"] == FA.NO_STEPS_FA
    r = await client.post(f"{API}/playbooks/{pref}/use", json=form("NOPE1"),
                          headers={**owner, **idem()})  # fmt: skip
    assert r.status_code == 404


async def test_the_narrators_sample_is_made_once_a_day(
    client: httpx.AsyncClient, owner_session: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    owner = owner_session["headers"]
    asked: list[dict[str, Any]] = []

    async def api_speak(hub: Any, job: dict[str, Any]) -> tuple[bytes, str]:
        asked.append(job)
        return b"OggS" + uuid.uuid4().bytes, "audio/ogg"

    monkeypatch.setattr(SM, "api_speak", api_speak)
    words = f"سلام، این صدای آزمایشی {uuid.uuid4().hex[:6]} است و کمی بیشتر از هشت ثانیه " * 3
    body = {"voice": "charon", "style_fa": "آرام", "text_fa": words}
    r = await client.post(f"{API}/narrators/sample", json=body, headers={**owner, **idem()})
    assert r.status_code == 200, r.text
    f = r.json()["file"]
    assert f["mime"] == "audio/ogg" and f["name"].startswith("narrator-charon")
    assert len(asked) == 1 and asked[0]["voice"] == "Charon" and len(asked[0]["text"]) <= 100
    again = await client.post(f"{API}/narrators/sample", json=body, headers={**owner, **idem()})
    assert again.json()["file"]["id"] == f["id"] and len(asked) == 1
    r = await client.post(f"{API}/narrators/sample", json={"voice": "Nobody"},
                          headers={**owner, **idem()})  # fmt: skip
    assert r.status_code == 422
