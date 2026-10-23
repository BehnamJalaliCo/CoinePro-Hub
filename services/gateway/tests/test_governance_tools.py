"""Prompt 11's governance tools in the gateway (agents/tools.md "Governance (v1.5,
prompt 11)"; contract §20.1, §20.3, §20.11).

§1, §3, §11: the meeting room's and the knowledge base's tools: what each one
sends to the api (redacted, with its Idempotency-Key), what the model gets back,
the shapes it refuses, and the api's refusals carried back with their stable
codes. §4-§10: each validated, redacted and sent to its internal route with the
run's own token; none writes the charter or the matrix, none leaves the hub.
The roles are the real charters (agents/roles)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, TOKEN, Stub, call, gate

from hq_common import tool_status
from hq_gateway import governance as GV
from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa

CEO = gate(employee="TY-CEO", kind="ceo", role="ceo", department=None, own_thread="TY-CEO")
OVR = gate(
    employee="HQ-OVR", company="HQ", kind="overseer", role="overseer", department="OVS",
    scope="holding",
)  # fmt: skip
ADV = gate(
    employee="HQ-ADV", company="HQ", kind="advisor", role="advisor", department=None,
    scope="holding",
)  # fmt: skip
SEC = gate(
    employee="HQ-SEC", company="HQ", kind="system", role="secretary", department="AIOPS",
    scope="holding", work_ref=None,
)  # fmt: skip
MAIL = "ali@example.com"  # what a model may echo; it never leaves the gateway
DRAFT = "0193e7a1-0000-7000-8000-0000000000d1"
CLAIM = "0193e7a1-0000-7000-8000-0000000000c1"


def said(text: str) -> str:
    """What the agent writes (with a customer's e-mail in it)."""
    return f"{text} {MAIL}"


def sent(text: str) -> str:
    """What reaches the api: the same text, redacted, never shortened."""
    return f"{text} [email]"


CHECKS = {"injection": True, "secrets": True, "conflicts": True, "policy": True}

# (who, tool, args, the api path (POST), the body the api gets, the api's answer, class, ref)
Case = tuple[dict[str, Any], str, dict[str, Any], str, dict[str, Any], dict[str, Any], str, str]
FIELDS = ("who", "tool", "args", "path", "body", "answer", "cls", "ref")
CASES: list[Case] = [
    (
        CEO,
        "meeting.statement",
        {
            "meeting": "MT-0001",
            "item": 2,
            "statement_md": said("بیانیه"),
            "claims": [
                {"text_fa": said("ادعا"),
                 "source": {"kind": "deliverable", "ref": "O-000077", "note": said("یادداشت")}},
                {"text_fa": "ادعای بی‌منبع"},
            ],
            "draft_md": said("پیش‌نویس مصوبه"),
            "stance": {"draft": DRAFT, "vote": "support", "reason_fa": said("دلیل")},
        },
        "/internal/v1/meetings/MT-0001/statement",
        {
            "item": 2,
            "statement_md": sent("بیانیه"),
            "claims": [
                {"text_fa": sent("ادعا"),
                 "source": {"kind": "deliverable", "ref": "O-000077", "note": sent("یادداشت")}},
                {"text_fa": "ادعای بی‌منبع"},
            ],
            "draft_md": sent("پیش‌نویس مصوبه"),
            "stance": {"vote": "support", "reason_fa": sent("دلیل"), "draft": DRAFT},
        },
        {"ref": "MT-0001/T3", "claims": [{"status": "sourced"}, {"status": "unsourced"}]},
        "A1",
        "MT-0001/T3",
    ),
    (
        OVR,
        "meeting.challenge",
        {
            "meeting": "MT-0001",
            "item": 2,
            "claim": CLAIM,
            "statement_md": said("چالش"),
            "claims": [{"text_fa": said("ادعای مخالف"), "source": {"kind": "metric", "ref": "uptime"}}],
        },
        "/internal/v1/meetings/MT-0001/challenge",
        {
            "item": 2,
            "statement_md": sent("چالش"),
            "claims": [{"text_fa": sent("ادعای مخالف"), "source": {"kind": "metric", "ref": "uptime"}}],
            "claim": CLAIM,
        },
        {"ref": "MT-0001/T4"},
        "A1",
        "MT-0001/T4",
    ),
    (
        ADV,
        "meeting.whisper",
        {
            "meeting": "MT-0001",
            "item": 1,
            "text_md": said("نجوا"),
            "sources": [{"kind": "knowledge", "ref": "K-0001", "note": said("منبع")}],
        },
        "/internal/v1/meetings/MT-0001/whisper",
        {
            "item": 1,
            "text_md": sent("نجوا"),
            "sources": [{"kind": "knowledge", "ref": "K-0001", "note": sent("منبع")}],
        },
        {"ref": "MT-0001/W1"},
        "A1",
        "MT-0001/W1",
    ),
    (
        CEO,
        "meeting.item",
        {
            "type": "board",
            "company": "TY",
            "title_fa": said("دستور"),
            "brief_md": said("شرح"),
            "sources": [{"kind": "work", "ref": "W-000101"}],
        },
        "/internal/v1/meetings/items",
        {
            "type": "board",
            "company": "TY",
            "title_fa": sent("دستور"),
            "brief_md": sent("شرح"),
            "sources": [{"kind": "work", "ref": "W-000101"}],
        },
        {"ref": "MI-0007", "meeting_type": "board"},
        "A1",
        "MI-0007",
    ),
    (
        SEC,
        "meeting.minutes",
        {"meeting": "MT-0001", "summary_md": said("خلاصه")},
        "/internal/v1/meetings/MT-0001/minutes",
        {"summary_md": sent("خلاصه")},
        {"ref": "MT-0001", "deliverable": "O-000090"},
        "A1",
        "MT-0001",
    ),
    (
        CEO,
        "knowledge.propose",
        {
            "layer": "company",
            "company": "TY",
            "kind": "playbook",
            "title_fa": said("روش"),
            "body_md": said("متن روش"),
            "sources": [{"kind": "work", "ref": "W-000101", "note": said("یادداشت")}],
            "valid_until": "2027-06-30",
        },
        "/internal/v1/knowledge",
        {
            "layer": "company",
            "kind": "playbook",
            "title_fa": sent("روش"),
            "body_md": sent("متن روش"),
            "sources": [{"kind": "work", "ref": "W-000101", "note": sent("یادداشت")}],
            "valid_until": "2027-06-30",
            "company": "TY",
        },
        {"ref": "K-0012", "version": 1, "status": "in_review"},
        "A1",
        "K-0012",
    ),
    (
        OVR,
        "knowledge.review",
        {"ref": "K-0012", "version": 1, "verdict": "pass", "checks": CHECKS,
         "notes_md": said("بازبینی")},
        "/internal/v1/knowledge/K-0012/review",
        {"version": 1, "verdict": "pass", "checks": CHECKS, "notes_md": sent("بازبینی")},
        {"ref": "K-0012", "version": 1, "status": "in_review"},
        "A2",
        "K-0012",
    ),
    (
        CEO,
        "knowledge.approve",
        {"ref": "K-0012", "version": 1},
        "/internal/v1/knowledge/K-0012/approve",
        {"version": 1},
        {"ref": "K-0012", "version": 1, "status": "approved"},
        "A2",
        "K-0012",
    ),
]  # fmt: skip
IDS = [c[1] for c in CASES]


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


def test_the_library_knows_the_new_tools() -> None:
    classes = {name: LIB.tools[name].cls for name in IDS}
    assert classes == {
        "meeting.statement": "A1", "meeting.challenge": "A1", "meeting.whisper": "A1",
        "meeting.item": "A1", "meeting.minutes": "A1", "knowledge.propose": "A1",
        "knowledge.review": "A2", "knowledge.approve": "A2",
    }  # fmt: skip
    assert all(name in T.TOOLS for name in IDS)
    # The secretary is a system role: its minutes and its activity, nothing else.
    assert set(LIB.allowed("secretary")) == {"meeting.minutes", "activity.set"}


@pytest.mark.parametrize(FIELDS, CASES, ids=IDS)
async def test_each_tool_reaches_its_api_path_redacted(
    mock: respx.MockRouter,
    gw: Gateway,
    who: dict[str, Any],
    tool: str,
    args: dict[str, Any],
    path: str,
    body: dict[str, Any],
    answer: dict[str, Any],
    cls: str,
    ref: str,
) -> None:
    s = Stub(mock, who)
    route = mock.post(f"{API}{path}").mock(return_value=httpx.Response(201, json=answer))
    out = await call(gw, tool, args)
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", cls, ref), out
    request = route.calls.last.request
    assert MAIL not in request.content.decode()
    assert json.loads(request.content) == body
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    key = request.headers["idempotency-key"]
    assert key
    assert s.opa_inputs[-1]["action"] == {"class": cls, "name": tool, "company": who["company"]}
    assert s.records[-1] == {
        "tool": tool, "class": cls, "outcome": "ok", "code": None, "ref": ref, "step": 1,
    }  # fmt: skip
    # The same call of the same step is the same write (a retry is not a second turn).
    await call(gw, tool, args)
    assert route.calls.last.request.headers["idempotency-key"] == key


@pytest.mark.parametrize(FIELDS, CASES, ids=IDS)
async def test_extra_keys_are_refused(
    mock: respx.MockRouter,
    gw: Gateway,
    who: dict[str, Any],
    tool: str,
    args: dict[str, Any],
    path: str,
    body: dict[str, Any],
    answer: dict[str, Any],
    cls: str,
    ref: str,
) -> None:
    Stub(mock, who)
    route = mock.post(f"{API}{path}").mock(return_value=httpx.Response(201, json=answer))
    out = await call(gw, tool, {**args, "company_id": "11111111-1111-1111-1111-111111111111"})
    assert (out["outcome"], out["code"]) == ("error", "invalid_args"), out
    assert not route.called


async def test_shapes_the_tools_refuse(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, CEO)
    route = mock.post(f"{API}/internal/v1/meetings/MT-0001/statement").mock(
        return_value=httpx.Response(201, json={"ref": "MT-0001/T5"})
    )
    statement = dict(CASES[0][2])
    claim = {"text_fa": "ادعا", "source": {"kind": "work", "ref": "W-000101"}}
    bad_statements = [
        {**statement, "claims": [claim] * 21},  # a 21st claim
        {**statement, "item": 0},
        {**statement, "item": True},  # a JSON true is not item 1
        {**statement, "meeting": "MT-1"},
        {**statement, "statement_md": ""},
        {**statement, "stance": {"vote": "veto", "reason_fa": "x"}},
        {**statement, "stance": {"draft": "D-000001", "vote": "support", "reason_fa": "x"}},
        {**statement, "claims": [{"text_fa": "x", "source": {"kind": "Work!", "ref": "W-1"}}]},
    ]
    for args in bad_statements:
        out = await call(gw, "meeting.statement", args)
        assert (out["outcome"], out["code"]) == ("error", "invalid_args"), args
    assert route.call_count == 0
    twenty = await call(gw, "meeting.statement", {**statement, "claims": [claim] * 20})
    assert (twenty["outcome"], route.call_count) == ("ok", 1)
    proposals = mock.post(f"{API}/internal/v1/knowledge").mock(
        return_value=httpx.Response(201, json={"ref": "K-0013"})
    )
    propose = dict(CASES[5][2])
    bad_proposals = [
        {**propose, "sources": []},  # no source
        {k: v for k, v in propose.items() if k != "sources"},
        {k: v for k, v in propose.items() if k != "valid_until"},  # no expiry
        {**propose, "layer": "employee"},  # the employee layer is memory.write
        {**propose, "kind": "support"},  # support articles are kb.propose's
        {**propose, "valid_until": "someday"},
        {**propose, "ref": "KB-0001"},
        {**propose, "department": "tech"},
        {**propose, "sources": [{"kind": "work", "ref": "W-000101"}] * 21},
    ]
    for args in bad_proposals:
        out = await call(gw, "knowledge.propose", args)
        assert (out["outcome"], out["code"]) == ("error", "invalid_args"), args
    assert not proposals.called
    Stub(mock, OVR)
    reviews = mock.post(f"{API}/internal/v1/knowledge/K-0012/review").mock(
        return_value=httpx.Response(201, json={"ref": "K-0012"})
    )
    review = dict(CASES[6][2])
    bad_reviews = [
        {**review, "checks": {**CHECKS, "secrets": "yes"}},  # a non-bool check
        {**review, "checks": {**CHECKS, "policy": 1}},
        {**review, "checks": {k: v for k, v in CHECKS.items() if k != "conflicts"}},
        {**review, "checks": {**CHECKS, "authority": True}},
        {**review, "verdict": "ok"},
        {**review, "version": 0},
        {**review, "version": "1"},
    ]
    for args in bad_reviews:
        out = await call(gw, "knowledge.review", args)
        assert (out["outcome"], out["code"]) == ("error", "invalid_args"), args
    assert not reviews.called


async def test_each_role_has_only_its_meeting_tools(mock: respx.MockRouter, gw: Gateway) -> None:
    refused = [
        (CEO, "meeting.challenge"), (CEO, "meeting.whisper"), (CEO, "meeting.minutes"),
        (CEO, "knowledge.review"), (ADV, "meeting.statement"), (ADV, "knowledge.propose"),
        (OVR, "meeting.whisper"), (OVR, "knowledge.approve"), (SEC, "meeting.statement"),
        (SEC, "knowledge.search"),
    ]  # fmt: skip
    for who, tool in refused:
        Stub(mock, who)
        out = await call(gw, tool, {})
        assert (out["outcome"], out["code"]) == ("denied", "tool_not_in_charter"), (who, tool)


async def test_knowledge_search_filters_the_knowledge_kind(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CEO)
    route = mock.get(f"{API}/internal/v1/knowledge/search").mock(
        return_value=httpx.Response(
            200,
            json={"items": [{"ref": "K-0012", "layer": "company", "valid_until": "2027-06-30",
                             "sources": [{"kind": "work", "ref": "W-000101"}]}]},
        )
    )  # fmt: skip
    out = await call(
        gw, "knowledge.search",
        {"q": "روش پاسخ", "kinds": ["knowledge"], "layer": "company", "kind": "playbook"},
    )  # fmt: skip
    assert (out["outcome"], out["class"]) == ("ok", "A0"), out
    params = route.calls.last.request.url.params
    sent_filters = (params["kinds"], params["layer"], params["kind"])
    assert sent_filters == ("knowledge", "company", "playbook")
    assert out["result"]["items"][0]["ref"] == "K-0012"
    # Without the filters nothing extra is sent.
    await call(gw, "knowledge.search", {"q": "روش پاسخ", "kinds": ["knowledge", "work"]})
    params = route.calls.last.request.url.params
    assert params.get_list("kinds") == ["knowledge", "work"]
    assert "layer" not in params and "kind" not in params
    for bad in ({"layer": "team"}, {"kind": "rumour"}, {"kinds": ["knowledge", "secrets"]}):
        out = await call(gw, "knowledge.search", {"q": "روش پاسخ", **bad})
        assert out["code"] == "invalid_args", bad


async def test_the_apis_refusals_come_back_with_their_codes(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CEO)
    mock.post(f"{API}/internal/v1/meetings/MT-0001/statement").mock(
        return_value=httpx.Response(
            409, json={"code": "meeting_not_live", "message_fa": "جلسه زنده نیست."}
        )
    )
    mock.post(f"{API}/internal/v1/knowledge").mock(
        return_value=httpx.Response(
            422,
            json={"code": "knowledge_expired", "message_fa": "منبع منقضی است.",
                  "fields": {"sources.0.ref": "K-0001 expired"}},
        )
    )  # fmt: skip
    out = await call(gw, "meeting.statement", CASES[0][2])
    assert (out["outcome"], out["code"], out["hint_fa"]) == (
        "error",
        "meeting_not_live",
        "جلسه زنده نیست.",
    ), out
    out = await call(gw, "knowledge.propose", CASES[5][2])
    assert (out["outcome"], out["code"]) == ("error", "knowledge_expired"), out
    assert out["fields"] == {"sources.0.ref": "K-0001 expired"}
    # An expired source cited in a statement is the same refusal.
    mock.post(f"{API}/internal/v1/meetings/MT-0002/statement").mock(
        return_value=httpx.Response(422, json={"code": "knowledge_expired"})
    )
    out = await call(gw, "meeting.statement", {**CASES[0][2], "meeting": "MT-0002"})
    assert (out["outcome"], out["code"]) == ("error", "knowledge_expired")


# ---------------------------------------------------------------- §4-§10 --
NOW = "2026-10-22T08:00:00+00:00"
SOURCE = {"kind": "metric", "ref": "analytics:dau", "note": ""}


class Api:
    def __init__(self, mock: respx.MockRouter) -> None:
        self.sent: list[tuple[str, str, Any, httpx.Headers]] = []
        mock.route(host="api.test", path__startswith="/internal/v1/governance/").mock(
            side_effect=self._answer
        )

    def _answer(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else dict(request.url.params)
        self.sent.append((request.method, request.url.path, body, request.headers))
        path = request.url.path
        if path.endswith("/okr/draft"):
            return httpx.Response(200, json={"decision": "D-000042", "objectives": ["OB-0001"]})
        if path.endswith("/risks"):
            return httpx.Response(
                201, json={"ref": "RK-0001", "score": 20, "status": "open", "version": 1}
            )
        if path.endswith("/authority"):
            return httpx.Response(200, json=[{"key": "hire.per_day", "limit": {"count_day": 5}}])
        return httpx.Response(200, json={"ok": True})


CALLS: list[tuple[str, dict[str, Any], str, str]] = [
    ("kpi.record", {"company": "TY", "key": "users.active", "value": 1200, "at": NOW, "source": SOURCE},
     "POST", "/internal/v1/governance/kpis/record"),
    ("okr.draft", {"company": "TY", "quarter": "1405-Q3", "objectives": [
        {"title_fa": "رشد", "key_results": [{"title_fa": "کاربر", "kpi": "users.active", "start": 1, "target": 2}]}]},
     "POST", "/internal/v1/governance/okr/draft"),
    ("okr.checkin", {"key_result": "KR-0001", "confidence": 0.7, "note_md": "خوب", "evidence": [SOURCE]},
     "POST", "/internal/v1/governance/okr/checkin"),
    ("outcome.note", {"ref": "OR-0001", "note_md": "نتیجه"}, "POST", "/internal/v1/governance/outcomes/note"),
    ("risk.raise", {"company": "TY", "title_fa": "ریسک", "category": "vendor", "likelihood": 4, "impact": 5},
     "POST", "/internal/v1/governance/risks"),
    ("risk.update", {"ref": "RK-0001", "version": 1, "impact": 2, "note": "کمتر شد"},
     "POST", "/internal/v1/governance/risks/update"),
    ("calendar.read", {"from": NOW, "to": NOW}, "GET", "/internal/v1/governance/calendar"),
    ("calendar.add", {"company": "TY", "kind": "campaign", "title_fa": "کمپین", "starts_at": NOW, "ends_at": NOW},
     "POST", "/internal/v1/governance/calendar"),
    ("authority.read", {}, "GET", "/internal/v1/governance/authority"),
    ("governance.read", {"what": "cards"}, "GET", "/internal/v1/governance/read"),
]  # fmt: skip


def test_the_ten_tools_are_live_and_in_the_ceos_charter() -> None:
    assert set(GV.TOOLS) <= set(T.TOOLS) and set(GV.TOOLS) <= tool_status.GATEWAY_TOOLS
    assert set(GV.TOOLS) <= set(LIB.allowed("ceo"))
    assert not {
        t for t in T.TOOLS if t.startswith(("charter.", "authority.")) and t != "authority.read"
    }


@pytest.mark.parametrize(("tool", "args", "method", "path"), CALLS)
async def test_each_tool_calls_its_route_with_the_runs_token(
    mock: respx.MockRouter, gw: Gateway, tool: str, args: dict[str, Any], method: str, path: str
) -> None:
    Stub(mock, CEO)
    api = Api(mock)
    out = await call(gw, tool, args)
    assert out["outcome"] == "ok", out
    (sent,) = api.sent
    assert (sent[0], sent[1]) == (method, path)
    assert sent[3]["authorization"] == f"Bearer {TOKEN}"
    if method == "POST":
        assert sent[3].get("idempotency-key")  # a retried step never writes twice


async def test_a_secret_in_a_risk_is_redacted_and_bad_input_is_refused(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CEO)
    api = Api(mock)
    key = "sk-ant-" + "a" * 40
    out = await call(gw, "risk.raise", {"company": "TY", "title_fa": "کلید", "body_md": f"کلید {key} نشت کرد",
                                        "category": "security", "likelihood": 3, "impact": 5})  # fmt: skip
    assert out["outcome"] == "ok"
    assert key not in api.sent[0][2]["body_md"]
    bad = await call(gw, "risk.raise", {"company": "TY", "title_fa": "x", "category": "weather",
                                        "likelihood": 9, "impact": 1})  # fmt: skip
    assert (bad["outcome"], bad["code"]) == ("error", "invalid_args")
    bad = await call(gw, "calendar.add", {"company": "TY", "kind": "deploy", "title_fa": "x",
                                          "starts_at": NOW, "ends_at": NOW})  # fmt: skip
    assert bad["code"] == "invalid_args"  # a deploy comes from its card, never from calendar.add
    bad = await call(
        gw, "kpi.record", {"company": "TY", "key": "users.active", "value": 1, "at": NOW}
    )
    assert bad["code"] == "invalid_args" and "source" in json.dumps(bad["fields"])


async def test_propose_carries_expected_and_the_cards_warnings(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CEO)
    seen: list[dict[str, Any]] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            201, json={"ref": "D-000050", "status": "pending", "warnings": ["expected_missing"]}
        )

    mock.post(f"{API}/internal/v1/decisions").mock(side_effect=answer)
    mock.get(f"{API}/internal/v1/work/ref/W-000101").mock(
        return_value=httpx.Response(
            200, json={"id": "11111111-1111-1111-1111-111111111111", "ref": "W-000101"}
        )
    )
    expected = {
        "metric_fa": "کاربر فعال",
        "kpi": "users.active",
        "baseline": 100,
        "target": 150,
        "by_days": 60,
    }
    out = await call(gw, "propose", {"kind": "proposal", "title_fa": "کمپین", "expected": expected})
    assert out["outcome"] == "ok" and seen[0]["expected"] == expected
    out = await call(gw, "propose", {"kind": "proposal", "title_fa": "بی‌قول"})
    assert out["result"]["warnings"] == ["expected_missing"] and "expected" not in seen[1]
    bad = await call(
        gw,
        "propose",
        {"kind": "proposal", "title_fa": "x", "expected": {**expected, "by_days": 45}},
    )
    assert bad["code"] == "invalid_args"
    for kind in ("authority_change", "risk_acceptance"):
        assert (await call(gw, "propose", {"kind": kind, "title_fa": "x"}))["outcome"] == "ok"
    assert (await call(gw, "propose", {"kind": "okr", "title_fa": "x"}))["code"] == "invalid_args"
