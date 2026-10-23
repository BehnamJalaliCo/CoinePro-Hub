"""Prompt 13 §3, §4, §5 (agents/tools.md v1.6): the legal counsel's tools and
a media item's voice; the charters and the catalog agree (every charter's
tools are in tools.md; media.review is the media director's only; email.draft
and mail.read are the legal counsel's only)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, Stub, call, gate

from hq_common import tool_status
from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa

COUNSEL = gate(
    employee="HQ-LGL", company="HQ", kind="employee", role="legal_counsel", department="LEGAL",
    scope="holding", own_thread="L",
)  # fmt: skip
VOICE = gate(employee="TY-MEDIA-01", kind="employee", role="voice_producer", department="MEDIA")
STAFF = gate(employee="TY-GROWTH-01", kind="employee", role="sre", department="GROWTH")
LEGAL_ONLY = ("email.draft", "mail.read", "case.open", "case.note")


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


# ------------------------------------------------------- charters & catalog --
def test_every_charter_tool_is_in_the_catalog_and_the_exclusive_ones_stay_exclusive() -> None:
    assert not [p for p in LIB.problems if "not in agents/tools.md" in p], LIB.problems
    for role, charter in LIB.roles.items():
        raw = set(charter.tools)
        assert raw <= set(LIB.tools) | {"done"}, (role, raw - set(LIB.tools))
    holders = {t: sorted(r for r, c in LIB.roles.items() if t in c.tools) for t in LIB.tools}
    assert holders["media.review"] == ["media_director"]
    assert holders["email.draft"] == ["legal_counsel"] and holders["mail.read"] == ["legal_counsel"]
    assert holders["media.voice"] == ["voice_producer"]
    assert {"case.open", "case.note"} <= set(LIB.roles["legal_counsel"].tools)
    assert (
        LIB.roles["legal_counsel"].scope == "holding"
        and LIB.roles["legal_counsel"].department == "LEGAL"
    )
    assert LIB.tools["email.draft"].cls == "A1" and LIB.tools["mail.read"].cls == "A0"
    assert LIB.tools["media.voice"].cls == "A2"
    assert set(LEGAL_ONLY) | {"media.voice"} <= tool_status.GATEWAY_TOOLS


async def test_another_role_has_none_of_the_counsels_tools(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, STAFF)
    for tool in LEGAL_ONLY:
        out = await call(gw, tool, {"case": "LC-0001", "ref": "LC-0001"})
        assert (out["outcome"], out["code"]) == ("denied", "tool_not_in_charter"), tool


# ----------------------------------------------------------------- legal --
async def test_an_email_draft_keeps_its_addresses_and_redacts_its_text(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, COUNSEL)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            201,
            json={"case": "LC-0001", "decision": "D-000123", "digest": "a" * 64,
                  "email": "0193e7a1-0000-7000-8000-000000000009", "from": "legal@example.org",
                  "state": "waiting_seal"},
        )  # fmt: skip

    route = mock.post(f"{API}/internal/v1/legal/cases/LC-0001/emails").mock(side_effect=handle)
    out = await call(
        gw,
        "email.draft",
        {
            "case": "LC-0001",
            "to": ["support@example.com"],
            "subject": "Appeal",
            "body_md": "Our customer ali@example.net wrote to us.",
            "lang": "en",
        },
    )
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", "D-000123"), out
    assert out["result"]["state"] == "waiting_seal" and "nothing was sent" in out["result"]["note"]
    assert seen[0]["to"] == ["support@example.com"] and "ali@example.net" not in seen[0]["body_md"]
    bad = await call(
        gw,
        "email.draft",
        {"case": "LC-0001", "to": ["not an address"], "subject": "x", "body_md": "y", "lang": "en"},
    )
    assert (bad["outcome"], bad["code"]) == ("error", "invalid_args") and route.call_count == 1


async def test_case_open_note_and_mail_read_reach_the_api(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, COUNSEL)
    case = {"ref": "LC-0002", "company": "TY", "title_fa": "t", "kind": "takedown", "status": "open",
            "counsel": "HQ-LGL", "deadlines": [], "timeline": [{"kind": "note"}] * 9, "brief_md": "x"}  # fmt: skip
    opened = mock.post(f"{API}/internal/v1/legal/cases").mock(
        return_value=httpx.Response(201, json=case)
    )
    noted = mock.post(f"{API}/internal/v1/legal/cases/LC-0002/notes").mock(
        return_value=httpx.Response(200, json=case)
    )
    mock.get(f"{API}/internal/v1/legal/cases/LC-0002/mail").mock(
        return_value=httpx.Response(200, json={"case": "LC-0002", "status": "open", "emails": []})
    )
    out = await call(
        gw,
        "case.open",
        {"company": "TY", "title_fa": "حذف پست", "kind": "takedown", "brief_md": "x",
         "counterpart": {"name": "Meta", "channel": "form"}},
    )  # fmt: skip
    assert (
        out["outcome"] == "ok" and out["ref"] == "LC-0002" and len(out["result"]["timeline"]) == 5
    )
    body = json.loads(opened.calls[0].request.content)
    assert "link" not in body and "link" not in body["counterpart"]
    note = await call(
        gw,
        "case.note",
        {"ref": "LC-0002", "kind": "note", "summary_fa": "مهلت",
         "deadline": {"at": "2031-01-05T09:00:00Z", "what_fa": "پایان مهلت"}},
    )  # fmt: skip
    assert note["outcome"] == "ok"
    sent = json.loads(noted.calls[0].request.content)
    assert "ref" not in sent and sent["deadline"]["what_fa"] == "پایان مهلت"
    read = await call(gw, "mail.read", {"case": "LC-0002"})
    assert (read["outcome"], read["class"], read["ref"]) == ("ok", "A0", "LC-0002")
    assert (await call(gw, "mail.read", {"case": "W-1"}))["code"] == "invalid_args"


async def test_the_counsels_own_case_only_is_the_apis_answer(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, COUNSEL)
    mock.get(f"{API}/internal/v1/legal/cases/LC-0009/mail").mock(
        return_value=httpx.Response(404, json={"code": "not_found", "message_fa": "پیدا نشد."})
    )
    out = await call(gw, "mail.read", {"case": "LC-0009"})
    assert (out["outcome"], out["code"]) == ("error", "not_found")


# ----------------------------------------------------------------- voice --
async def test_media_voice_queues_the_narration(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, VOICE)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            202,
            json={"job": "j-1", "item": "MI-0001", "state": "queued", "spoken_chars": 20,
                  "voice": {"id": "piper-amir", "name_fa": "پایپر", "licence": "MIT",
                            "licence_commercial": True}},
        )  # fmt: skip

    mock.post(f"{API}/internal/v1/media/voice").mock(side_effect=handle)
    out = await call(gw, "media.voice", {"ref": "MI-0001", "text_fa": "قیمت بالا رفت."})
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A2", "j-1"), out
    assert out["result"]["voice"]["licence_commercial"] is True
    assert seen == [{"ref": "MI-0001", "text_fa": "قیمت بالا رفت."}]
    Stub(mock, STAFF)
    no = await call(gw, "media.voice", {"ref": "MI-0001", "text_fa": "x"})
    assert (no["outcome"], no["code"]) == ("denied", "tool_not_in_charter")
