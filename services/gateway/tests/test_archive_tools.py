"""Prompt 14 §9 (agents/tools.md v1.7, contract §23.11): the archive's tools.
The charters and the catalog agree (search, read, file and link are the
archivist's and the legal counsel's; a hold is the counsel's alone); each tool
sends exactly what the api expects, refuses a bad ref before any call, and
gives back only what the agent needs."""

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

ARCHIVIST = gate(
    employee="HQ-ARC",
    company="HQ",
    kind="system",
    role="archivist",
    department=None,
    scope="holding",
    own_thread=None,
)
COUNSEL = gate(
    employee="HQ-LGL",
    company="HQ",
    kind="employee",
    role="legal_counsel",
    department="LEGAL",
    scope="holding",
    own_thread="L",
)
STAFF = gate(employee="TY-GROWTH-01", kind="employee", role="sre", department="GROWTH")
ARCHIVE = ("archive.search", "archive.read", "archive.file", "archive.link", "archive.hold")
FILE_ID = "0193e7a1-0000-7000-8000-00000000000a"


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=8000, tool_timeout_s=2)


# ------------------------------------------------------- charters & catalog --
def test_the_archive_tools_are_the_archivists_and_the_counsels_with_their_classes() -> None:
    assert not [p for p in LIB.problems if p.startswith("archivist")], LIB.problems
    arc = LIB.roles["archivist"]
    assert (arc.kind, arc.scope, arc.department) == ("system", "holding", None)
    holders = {t: {r for r, c in LIB.roles.items() if t in c.tools} for t in ARCHIVE}
    for tool in ("archive.search", "archive.read", "archive.file", "archive.link"):
        assert holders[tool] == {"archivist", "legal_counsel"}, (tool, holders[tool])
    # The archivist never holds (and nobody has a tool that seals, releases or disposes).
    assert holders["archive.hold"] == {"legal_counsel"}
    assert not {t for t in LIB.tools if t.startswith("archive.")} - set(ARCHIVE)
    classes = {t: LIB.tools[t].cls for t in ARCHIVE}
    assert classes == {
        "archive.search": "A0",
        "archive.read": "A0",
        "archive.file": "A1",
        "archive.link": "A1",
        "archive.hold": "A2",
    }
    assert set(ARCHIVE) <= tool_status.GATEWAY_TOOLS
    assert set(ARCHIVE) <= set(T.TOOLS)


async def test_another_role_has_none_of_the_archive_tools(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, STAFF)
    for tool in ARCHIVE:
        out = await call(gw, tool, {"ref": "AR-000001"})
        assert (out["outcome"], out["code"]) == ("denied", "tool_not_in_charter"), tool
    Stub(mock, ARCHIVIST)
    out = await call(
        gw,
        "archive.hold",
        {"title_fa": "x", "case": "LC-0001", "reason_md": "x", "scope": {"records": ["AR-000001"]}},
    )
    assert (out["outcome"], out["code"]) == ("denied", "tool_not_in_charter")


# ------------------------------------------------------------ search, read --
async def test_search_sends_its_filters_and_a_bad_party_never_reaches_the_api(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, ARCHIVIST)
    seen: list[dict[str, str]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "ref": "AR-000123",
                        "title_fa": "قرارداد",
                        "class": "contract",
                        "scope": "TY",
                        "level": "internal",
                        "snippet_fa": "…",
                        "score": 0.4,
                    }
                ],
                "next_cursor": None,
            },
        )

    route = mock.get(f"{API}/internal/v1/archive/search").mock(side_effect=handle)
    out = await call(
        gw,
        "archive.search",
        {
            "q": "قرارداد افیلیت",
            "scope": "TY",
            "class": "contract",
            "party": "PT-0007",
            "from": "2026-01-01",
            "to": "2026-10-23",
            "limit": 5,
        },
    )
    assert (out["outcome"], out["class"]) == ("ok", "A0"), out
    assert out["result"]["items"][0]["ref"] == "AR-000123"
    assert seen[0] == {
        "q": "قرارداد افیلیت",
        "scope": "TY",
        "class": "contract",
        "party": "PT-0007",
        "from": "2026-01-01",
        "to": "2026-10-23",
        "limit": "5",
    }
    for bad in ({"party": "PT-7"}, {"class": "Contract"}, {"scope": "ty"}, {"from": "1404-08-01x"}):
        r = await call(gw, "archive.search", bad)
        assert (r["outcome"], r["code"]) == ("error", "invalid_args"), bad
    assert route.call_count == 1


async def test_read_gives_the_record_without_storage_and_caps_its_text(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, COUNSEL)
    record = {
        "ref": "AR-000123",
        "scope": "TY",
        "class": "contract",
        "title_fa": "قرارداد",
        "level": "confidential",
        "state": "sealed",
        "metadata": {"end": "2027-01-01"},
        "masked": ["iban"],
        "current_version": 1,
        "created_by": {"kind": "owner"},
        "versions": [
            {
                "n": 1,
                "state": "current",
                "sealed": True,
                "manifest_sha256": "b" * 64,
                "files": [
                    {
                        "file_id": FILE_ID,
                        "name": "c.pdf",
                        "mime": "application/pdf",
                        "sha256": "a" * 64,
                        "storage_key": "secret-key",
                        "pages": 3,
                        "text_state": "text_layer",
                        "ocr_confidence": None,
                    }
                ],
            }
        ],
        "text": "متن " * 5000,
    }
    seen: list[dict[str, str]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=record)

    route = mock.get(f"{API}/internal/v1/archive/records/AR-000123").mock(side_effect=handle)
    out = await call(gw, "archive.read", {"ref": "AR-000123", "version": 1})
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A0", "AR-000123"), out
    assert seen == [{"version": "1"}]
    got = out["result"]
    assert "storage_key" not in json.dumps(got) and "created_by" not in got
    assert got["versions"][0]["files"][0]["text_state"] == "text_layer"
    assert got["text_truncated"] is True and len(got["text"]) <= 12_000
    bad = await call(gw, "archive.read", {"ref": "AR-123"})
    assert (bad["outcome"], bad["code"]) == ("error", "invalid_args") and route.call_count == 1
    # A record above the reader's clearance: the api's answer, nothing more.
    mock.get(f"{API}/internal/v1/archive/records/AR-000999").mock(
        return_value=httpx.Response(404, json={"code": "not_found"})
    )
    gone = await call(gw, "archive.read", {"ref": "AR-000999"})
    assert (gone["outcome"], gone["code"], gone["result"]) == ("error", "not_found", None)


# -------------------------------------------------------------- file, link --
async def test_file_makes_a_draft_keeps_identifiers_and_masks_credentials(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    s = Stub(mock, ARCHIVIST)
    seen: list[tuple[dict[str, Any], str | None]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append((json.loads(request.content), request.headers.get("idempotency-key")))
        return httpx.Response(
            201,
            json={
                "ref": "AR-000124",
                "state": "draft",
                "class": "contract",
                "level": "internal",
                "missing": ["end"],
                "suggestion": None,
                "id": "x",
                "metadata": {"a": 1},
            },
        )

    route = mock.post(f"{API}/internal/v1/archive/records").mock(side_effect=handle)
    args = {
        "scope": "TY",
        "class": "contract",
        "title_fa": "قرارداد با ali@example.net",
        "file_ids": [FILE_ID],
        "metadata": {
            "iban": "IR820540102680020817909002",
            "amount": {"amount": "1200.50", "currency": "USDT"},
            "notes": "api_key=sk-proj-abcdefghijklmnopqrstuvwxyz0123",
        },
        "parties": [{"party": "PT-0003", "role_fa": "طرف دوم"}],
        "links": [{"kind": "evidence_for", "to": {"kind": "decision", "ref": "D-000123"}}],
        "note_fa": "تاریخ از صفحه‌ی ۲",
    }
    out = await call(gw, "archive.file", args)
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", "AR-000124"), out
    body, key = seen[0]
    assert key  # the api requires an Idempotency-Key
    assert body["class"] == "contract" and body["scope"] == "TY" and body["file_ids"] == [FILE_ID]
    assert body["metadata"]["iban"] == "IR820540102680020817909002"  # the api masks it, not us
    assert body["metadata"]["amount"] == {"amount": "1200.50", "currency": "USDT"}
    assert "sk-proj-" not in json.dumps(body)
    assert "ali@example.net" not in body["title_fa"]
    assert body["links"] == [
        {"kind": "evidence_for", "to": {"kind": "decision", "ref": "D-000123"}}
    ]
    assert "level" not in body and "folder" not in body
    assert set(out["result"]) == {"ref", "state", "class", "level", "missing", "suggestion", "note"}
    assert s.records[-1]["tool"] == "archive.file" and s.records[-1]["class"] == "A1"
    for bad in (
        {**args, "file_ids": ["not-a-uuid"]},
        {**args, "file_ids": [FILE_ID, FILE_ID]},
        {**args, "scope": "ty"},
        {**args, "metadata": {"Bad Key": "x"}},
        {**args, "folder": "FP-1"},
        {**args, "links": [{"kind": "about", "to": {"kind": "planet", "ref": "X-1"}}]},
        {k: v for k, v in args.items() if k != "class"},
    ):
        r = await call(gw, "archive.file", bad)
        assert (r["outcome"], r["code"]) == ("error", "invalid_args"), bad
    assert route.call_count == 1


async def test_a_secret_in_a_file_comes_back_as_its_code_only(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, ARCHIVIST)
    mock.post(f"{API}/internal/v1/archive/records").mock(
        return_value=httpx.Response(
            422,
            json={
                "code": "secret_in_document",
                "fields": {"file_ids.0": "a secret pattern"},
                "message_fa": "این فایل الگوی رمز دارد و ذخیره نشد.",
            },
        )
    )
    out = await call(
        gw,
        "archive.file",
        {"scope": "HQ", "class": "other", "title_fa": "x", "file_ids": [FILE_ID]},
    )
    assert (out["outcome"], out["code"]) == ("error", "secret_in_document"), out
    assert out["fields"] == {"file_ids.0": "a secret pattern"} and out["hint_fa"]


async def test_link_posts_one_link_and_a_sealed_record_says_so(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, COUNSEL)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.headers.get("idempotency-key")
        return httpx.Response(
            201,
            json={
                "kind": "about",
                "to_kind": "case",
                "to_ref": "LC-0001",
                "title_fa": "پرونده",
                "at": "2026-10-23T10:00:00Z",
                "by": "HQ-LGL",
                "sealed": False,
                "inverse": False,
            },
        )

    mock.post(f"{API}/internal/v1/archive/records/AR-000123/links").mock(side_effect=handle)
    out = await call(
        gw,
        "archive.link",
        {"ref": "AR-000123", "kind": "about", "to": {"kind": "case", "ref": "LC-0001"}},
    )
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", "AR-000123"), out
    assert seen == [{"kind": "about", "to": {"kind": "case", "ref": "LC-0001"}}]
    mock.post(f"{API}/internal/v1/archive/records/AR-000200/links").mock(
        return_value=httpx.Response(409, json={"code": "sealed_record"})
    )
    sealed = await call(
        gw,
        "archive.link",
        {"ref": "AR-000200", "kind": "about", "to": {"kind": "work", "ref": "W-000001"}},
    )
    assert (sealed["outcome"], sealed["code"]) == ("error", "sealed_record")
    bad = await call(
        gw, "archive.link", {"ref": "AR-000123", "kind": "about", "to": {"kind": "case"}}
    )
    assert (bad["outcome"], bad["code"]) == ("error", "invalid_args")


# -------------------------------------------------------------------- hold --
async def test_the_counsel_holds_for_its_case_and_a_hold_must_name_what_it_covers(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    s = Stub(mock, COUNSEL)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            201,
            json={
                "ref": "LH-0001",
                "title_fa": "اختلاف با شریک",
                "case": "LC-0001",
                "state": "active",
                "scope": {"classes": ["contract"]},
                "records": 4,
                "record_refs": ["AR-000001"],
                "placed_at": "2026-10-23T10:00:00Z",
                "reason_md": "x",
            },
        )

    route = mock.post(f"{API}/internal/v1/archive/holds").mock(side_effect=handle)
    args = {
        "title_fa": "اختلاف با شریک",
        "case": "LC-0001",
        "reason_md": "ادعای شریک درباره‌ی قرارداد؛ تماس: ali@example.net",
        "scope": {"classes": ["contract"], "parties": ["PT-0003"], "from": "2026-01-01"},
    }
    out = await call(gw, "archive.hold", args)
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A2", "LH-0001"), out
    assert seen[0]["case"] == "LC-0001" and "ali@example.net" not in seen[0]["reason_md"]
    assert seen[0]["scope"] == {
        "classes": ["contract"],
        "parties": ["PT-0003"],
        "from": "2026-01-01",
    }
    assert out["result"]["records"] == 4 and "only the owner releases" in out["result"]["note"]
    # hq.actions saw an A2 call of the counsel's own name for it
    assert s.opa_inputs[-1]["action"] == {"class": "A2", "name": "archive.hold", "company": "HQ"}
    for bad in (
        {**args, "scope": {}},
        {**args, "scope": {"from": "2026-01-01"}},
        {**args, "scope": {"records": ["AR-1"]}},
        {**args, "scope": {"classes": ["contract"], "from": "2026-02-01", "to": "2026-01-01"}},
        {**args, "case": "D-000001"},
        {k: v for k, v in args.items() if k != "case"},
    ):
        r = await call(gw, "archive.hold", bad)
        assert (r["outcome"], r["code"]) == ("error", "invalid_args"), bad
    assert route.call_count == 1


async def test_knowledge_search_takes_kind_records(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, STAFF)
    seen: list[list[str]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.get_list("kinds"))
        return httpx.Response(200, json=[])

    mock.get(f"{API}/internal/v1/knowledge/search").mock(side_effect=handle)
    out = await call(gw, "knowledge.search", {"q": "قرارداد", "kinds": ["records", "work"]})
    assert out["outcome"] == "ok" and seen == [["records", "work"]]
