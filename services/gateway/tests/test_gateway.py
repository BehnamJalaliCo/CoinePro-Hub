"""Tool Gateway (prompt 05 §3, §12): every refusal path, every tool, the error
mapping, redaction both ways and one audit row per call. The api and OPA are
stubbed (respx); the charters are the real ones (agents/, mounted read-only)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from hq_common import charters
from hq_gateway import tools as T
from hq_gateway.app import State, build_app, create_app
from hq_gateway.config import Settings
from hq_gateway.gateway import Gateway, Opa

API = "http://api.test"
OPA = "http://opa.test"
TOKEN = "hqa1.payload.signature"
WORKER = "worker-token-" + "x" * 40
LIB = charters.load()


def gate(**over: Any) -> dict[str, Any]:
    g = {
        "run_id": "0193e7a1-0000-7000-8000-000000000001",
        "employee": "TY-TECH-MGR",
        "company": "TY",
        "kind": "manager",
        "department": "TECH",
        "role": "cto",
        "charter_version": 1,
        "scope": "company",
        "status": "active",
        "lock": None,
        "own_thread": "TY-TECH-MGR",
        "work_ref": "W-000101",
        "escrow_classes": [],
        "model": "claude-sonnet-5-5",
        "effort": "high",
        "tool_calls": 1,
        "tool_calls_cap": 48,
        "step": 1,
        "step_tool_calls": 1,
        "step_tool_calls_cap": 8,
    }
    g.update(over)
    return g


class Stub:
    """The api and OPA as respx routes, recording what was sent."""

    def __init__(self, mock: respx.MockRouter, g: dict[str, Any] | None = None) -> None:
        self.mock = mock
        self.gate = g or gate()
        self.records: list[dict[str, Any]] = []
        self.opa_inputs: list[dict[str, Any]] = []
        self.opa_allow = True
        self.opa_reasons: list[str] = []
        mock.post(f"{API}/internal/v1/runs/self/reserve").mock(side_effect=self._reserve)
        mock.post(f"{API}/internal/v1/runs/self/tool-calls").mock(side_effect=self._record)
        mock.post(f"{OPA}/v1/data/hq/actions").mock(side_effect=self._opa)
        self.reserve_status = 200

    def _reserve(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        if self.reserve_status != 200:
            return httpx.Response(
                self.reserve_status,
                json={"code": "rate_limited" if self.reserve_status == 429 else "unauthenticated"},
            )
        return httpx.Response(200, json=self.gate)

    def _record(self, request: httpx.Request) -> httpx.Response:
        self.records.append(json.loads(request.content))
        return httpx.Response(204)

    def _opa(self, request: httpx.Request) -> httpx.Response:
        self.opa_inputs.append(json.loads(request.content)["input"])
        return httpx.Response(
            200, json={"result": {"allow": self.opa_allow, "deny_reasons": self.opa_reasons}}
        )


@pytest.fixture
def mock() -> AsyncIterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


async def call(gw: Gateway, tool: str, args: Any = None, step: int = 1) -> dict[str, Any]:
    return (await gw.call(TOKEN, step, 0, tool, args or {})).as_json()


def work_route(
    mock: respx.MockRouter, ref: str = "W-000101", wid: str = "11111111-1111-1111-1111-111111111111"
) -> None:
    mock.get(f"{API}/internal/v1/work/ref/{ref}").mock(
        return_value=httpx.Response(200, json={"id": wid, "ref": ref, "status": "in_progress"})
    )


# --------------------------------------------------------------- refusals --
async def test_no_running_run_and_caps(mock: respx.MockRouter, gw: Gateway) -> None:
    s = Stub(mock)
    s.reserve_status = 401
    assert (await call(gw, "work.get", {"ref": "W-000101"}))["code"] == "run_not_running"
    assert s.records == []  # a dead run's token: the api would refuse the audit row too
    s.reserve_status = 429
    out = await call(gw, "work.get", {"ref": "W-000101"})
    assert (out["outcome"], out["code"]) == ("denied", "rate_limited")
    # Nothing was carried out, but the refused call has its audit row (prompt 5.1 §2.3).
    assert s.records == [
        {
            "tool": "work.get",
            "class": "A0",
            "outcome": "denied",
            "code": "rate_limited",
            "ref": None,
            "step": 1,
        }
    ]


async def test_unknown_tool_and_the_implicit_done(mock: respx.MockRouter, gw: Gateway) -> None:
    s = Stub(mock)
    route = mock.get(f"{API}/internal/v1/work/ref/W-000101")
    for name in ("trade.execute", "done", "rm -rf /", "x" * 90, "work.get\n", "work.get.x", None):
        out = await call(gw, name, {"ref": "W-000101"})  # type: ignore[arg-type]
        assert (out["outcome"], out["code"]) == ("denied", "unknown_tool"), name
    assert [r["tool"] for r in s.records] == ["trade.execute", "done"] + ["unknown"] * 5
    assert all(r["outcome"] == "denied" for r in s.records)
    assert not route.called  # "work.get\n" never reaches the api uncounted


async def test_tool_outside_the_charter_is_refused(mock: respx.MockRouter, gw: Gateway) -> None:
    # The advisor writes only in thread A and to its memory: no deliver, propose, notify.
    s = Stub(
        mock, gate(employee="HQ-ADV", company="HQ", kind="advisor", role="advisor", scope="holding")
    )
    for tool in ("deliver", "propose", "notify", "work.delegate", "message.owner", "work.accept"):
        out = await call(gw, tool, {})
        assert (out["outcome"], out["code"]) == ("denied", "tool_not_in_charter"), tool
    assert s.opa_inputs == []  # refused before the policy is even asked
    # A role without a charter has no tools at all.
    Stub(mock, gate(role=None))
    assert (await call(gw, "work.get", {"ref": "W-000101"}))["code"] == "tool_not_in_charter"


async def test_policy_refusals(mock: respx.MockRouter, gw: Gateway) -> None:
    s = Stub(mock)
    s.opa_allow, s.opa_reasons = False, ["a2_needs_role_or_escrow"]
    out = await call(gw, "work.delegate", {"ref": "W-000101", "to": "TY-TECH-01", "title_fa": "x"})
    assert (out["outcome"], out["code"], out["class"]) == ("denied", "policy_denied", "A2")
    assert out["fields"]["reasons"] == "a2_needs_role_or_escrow"
    s.opa_reasons = ["company_locked"]
    assert (await call(gw, "deliver", {"work_ref": "W-000101", "title_fa": "t", "body_md": "b"}))[
        "code"
    ] == "company_locked"
    mock.post(f"{OPA}/v1/data/hq/actions").mock(return_value=httpx.Response(500))
    assert (await call(gw, "work.get", {"ref": "W-000101"}))["code"] == "policy_unavailable"


async def test_the_policy_input(mock: respx.MockRouter, gw: Gateway) -> None:
    # The same shape is evaluated by the real policy in infra/opa/policy/actions_test.rego
    # (test_locked_company_agent_raises_an_incident_from_the_gateway).
    s = Stub(mock, gate(lock="deploy_freeze", escrow_classes=["A0", "A1", "A2"]))
    mock.post(f"{API}/internal/v1/notifications").mock(
        return_value=httpx.Response(201, json={"id": "n1", "level": "urgent", "state": "sent"})
    )
    await call(gw, "notify", {"level": "urgent", "category": "service_down", "title_fa": "قطعی"})
    p = s.opa_inputs[-1]
    assert p["principal"] == {
        "kind": "agent",
        "code": "TY-TECH-MGR",
        "role": "manager",
        "company": "TY",
        "department": "TECH",
        "status": "active",
        "scope": "company",
    }
    assert p["action"] == {"class": "A2", "name": "notify", "company": "TY"}
    assert p["context"] == {
        "escrow_classes": ["A0", "A1", "A2"],
        "company_locked": True,
        "incident": True,
    }


async def test_invalid_arguments_never_echo_values(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock)
    out = await call(gw, "work.get", {"ref": "sk-ant-secret-value", "extra": 1})
    assert (out["outcome"], out["code"]) == ("error", "invalid_args")
    assert set(out["fields"]) == {"ref", "extra"}
    assert "sk-ant" not in json.dumps(out)
    for not_an_object in ("not an object", None, [], 7):
        out = await gw.call(TOKEN, 1, 0, "work.get", not_an_object)
        assert (out.code, out.fields) == ("invalid_args", {"args": "must be a JSON object"})
    for budget in (True, -5, "40000", {"tokens": True}, {"tokens": -1}, {"usd": "1"}):
        args = {"ref": "W-000101", "to": "TY-TECH-01", "title_fa": "x", "budget": budget}
        out = await gw.call(TOKEN, 1, 0, "work.delegate", args)
        assert out.code == "invalid_args", budget
    for quota in ({"usd": -1}, {"usd": False}, -3):
        out = await gw.call(
            TOKEN, 1, 0, "propose", {"kind": "proposal", "title_fa": "x", "quota_estimate": quota}
        )
        assert out.code == "invalid_args", quota


# ----------------------------------------------------------------- reads --
@pytest.mark.parametrize(
    ("tool", "args", "path", "params"),
    [
        ("company.state", {}, "/internal/v1/company/state", {}),
        ("health.sites", {"company": "TY"}, "/internal/v1/health/sites", {"company": "TY"}),
        (
            "treasury.usage",
            {"scope": "company", "period": "day"},
            "/internal/v1/treasury/usage",
            {"scope": "company", "period": "day"},
        ),
        (
            "knowledge.search",
            {"q": "درگاه", "kinds": ["decisions"]},
            "/internal/v1/knowledge/search",
            {"q": "درگاه", "kinds": "decisions"},
        ),
        ("memory.read", {}, "/internal/v1/memory", {}),
    ],
)
async def test_reads(
    mock: respx.MockRouter,
    gw: Gateway,
    tool: str,
    args: dict[str, Any],
    path: str,
    params: dict[str, str],
) -> None:
    Stub(mock)
    route = mock.get(f"{API}{path}").mock(
        return_value=httpx.Response(200, json={"items": [], "email": "x@y.z"})
    )
    out = await call(gw, tool, args)
    assert out["outcome"] == "ok", out
    assert out["result"]["email"] == "[redacted]"  # results are redacted on the way back
    sent = route.calls.last.request
    assert sent.headers["authorization"] == f"Bearer {TOKEN}"
    for k, v in params.items():
        assert sent.url.params.get(k) == v


async def test_holding_reads(mock: respx.MockRouter, gw: Gateway) -> None:
    s = Stub(
        mock,
        gate(
            employee="HQ-AIOPS-MGR",
            company="HQ",
            kind="manager",
            department="AIOPS",
            role="aiops_head",
            scope="holding",
        ),
    )
    mock.get(f"{API}/internal/v1/health/hub").mock(
        return_value=httpx.Response(200, json={"at": None, "data": {"disk_pct": 22}})
    )
    mock.get(f"{API}/internal/v1/audit/recent").mock(
        return_value=httpx.Response(200, json=[{"seq": 1}])
    )
    assert (await call(gw, "health.hub"))["result"]["data"] == {"disk_pct": 22}
    assert (await call(gw, "audit.recent", {"action": "tool", "since": "2026-10-17T00:00:00Z"}))[
        "outcome"
    ] == "ok"
    assert [r["class"] for r in s.records] == ["A0", "A0"]


async def test_backups_status_is_a_holding_read(mock: respx.MockRouter, gw: Gateway) -> None:
    """backups.status (prompt 07 §1): the platform SRE's charter has it; the
    answer is the api's metadata; a company role is not given the tool."""
    s = Stub(
        mock,
        gate(
            employee="HQ-SRE-01",
            company="HQ",
            kind="employee",
            department="AIOPS",
            role="hub_platform_sre",
            scope="holding",
        ),
    )
    route = mock.get(f"{API}/internal/v1/backups/status")
    route.mock(
        return_value=httpx.Response(
            200, json={"hourly": {"ok": True}, "encryption": "restic (AES-256)"}
        )
    )
    out = await call(gw, "backups.status")
    assert out["outcome"] == "ok" and out["class"] == "A0"
    assert out["result"]["hourly"] == {"ok": True}
    assert s.records[-1]["tool"] == "backups.status"
    Stub(mock, gate(role="cto"))
    out = await call(gw, "backups.status")
    assert (out["outcome"], out["code"]) == ("denied", "tool_not_in_charter")
    assert route.call_count == 1


async def test_work_get_and_api_errors(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock)
    work_route(mock)
    out = await call(gw, "work.get", {"ref": "W-000101"})
    assert (out["outcome"], out["ref"]) == ("ok", "W-000101")
    for status, body, outcome, code in [
        (403, {"code": "policy_denied"}, "denied", "policy_denied"),
        (404, {"code": "not_found"}, "error", "not_found"),
        (409, {"code": "delegation_depth_exceeded"}, "error", "delegation_depth_exceeded"),
        (
            422,
            {"code": "validation_failed", "fields": {"to": "unknown"}},
            "error",
            "validation_failed",
        ),
        (423, {"code": "company_locked"}, "denied", "company_locked"),
        (500, None, "error", "http_500"),
    ]:
        mock.get(f"{API}/internal/v1/work/ref/W-000102").mock(
            return_value=httpx.Response(status, json=body)
            if body
            else httpx.Response(status, text="x")
        )
        out = await call(gw, "work.get", {"ref": "W-000102"})
        assert (out["outcome"], out["code"]) == (outcome, code), status
    assert out["fields"] == {}
    mock.get(f"{API}/internal/v1/work/ref/W-000103").mock(side_effect=httpx.ConnectError("down"))
    assert (await call(gw, "work.get", {"ref": "W-000103"}))["code"] == "api_unreachable"


async def test_github_read_is_off_and_guarded(
    mock: respx.MockRouter, gw: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Off until the owner decides on a token; before that it already reads
    only an allowed repository and only a path inside it (prompt 5.1 §3)."""
    Stub(mock)
    repo = "BehnamJalaliCo/CoinePro-Hub"
    out = await call(gw, "github.read", {"repo": repo, "what": "commits"})
    assert (out["outcome"], out["code"]) == ("denied", "repo_not_allowed")
    monkeypatch.setenv("GITHUB_READ_REPOS", f"{repo.lower()}, other/repo")
    out = await call(gw, "github.read", {"repo": repo, "what": "commits"})
    assert (out["outcome"], out["code"]) == ("error", "channel_not_configured")
    for path in ("../secrets", "a/../../b", "/etc/passwd", "a\\b", "x\x00y"):
        out = await call(gw, "github.read", {"repo": repo, "what": "file", "path": path})
        assert (out["outcome"], out["code"]) == ("error", "invalid_args"), path
    out = await call(gw, "github.read", {"repo": "not a repo", "what": "commits"})
    assert out["code"] == "invalid_args"


# ---------------------------------------------------------------- writes --
async def test_deliver_redacts_what_leaves(mock: respx.MockRouter, gw: Gateway) -> None:
    s = Stub(mock)
    work_route(mock)
    route = mock.post(f"{API}/internal/v1/work/11111111-1111-1111-1111-111111111111/deliver").mock(
        return_value=httpx.Response(
            200, json={"deliverable": "O-000077", "work": {}, "closed_children": []}
        )
    )
    body = "خلاصه‌ی حادثه\n\nمشتری ali@example.com با 09121234567 تماس گرفت؛ کلید sk-ant-oat01-ABCDEFGHIJKLMNOP"
    out = await call(
        gw,
        "deliver",
        {
            "work_ref": "W-000101",
            "title_fa": "گزارش",
            "body_md": body,
            "evidence": [{"kind": "metric", "ref": "uptime", "note": "99%"}],
        },
    )
    assert (out["outcome"], out["ref"]) == ("ok", "O-000077")
    sent = json.loads(route.calls.last.request.content)
    raw = json.dumps(sent, ensure_ascii=False)
    for leaked in ("ali@example.com", "09121234567", "sk-ant-oat01"):
        assert leaked not in raw
    assert sent["summary"] == "خلاصه‌ی حادثه" and sent["produced_with"] == {
        "model": "claude-sonnet-5-5",
        "effort": "high",
    }
    assert route.calls.last.request.headers["idempotency-key"]
    assert s.records[-1] == {
        "tool": "deliver",
        "class": "A1",
        "outcome": "ok",
        "code": None,
        "ref": "O-000077",
        "step": 1,
    }
    # The same action replayed carries the same idempotency key.
    again = await call(
        gw, "deliver", {"work_ref": "W-000101", "title_fa": "گزارش", "body_md": body}
    )
    assert again["outcome"] == "ok"
    keys = {c.request.headers["idempotency-key"] for c in route.calls}
    assert len(keys) == 1


async def test_outgoing_text_is_never_cut(mock: respx.MockRouter, gw: Gateway) -> None:
    """What an agent writes leaves complete: only scrubbed, never shortened (prompt 5.1 §1.2)."""
    Stub(mock)
    work_route(mock)
    deliver = mock.post(
        f"{API}/internal/v1/work/11111111-1111-1111-1111-111111111111/deliver"
    ).mock(
        return_value=httpx.Response(200, json={"deliverable": "O-000078", "closed_children": []})
    )
    email = "ali" + "@" + "example.com"
    paragraph = "گزارش کامل این هفته: سرویس‌ها سالم ماندند و هیچ هشداری نبود. "
    body = "خلاصه\n\n" + paragraph * (149_000 // len(paragraph)) + f" تماس: {email} "
    body = body + "پ" * (150_000 - len(body))
    assert len(body) == 150_000
    out = await call(gw, "deliver", {"work_ref": "W-000101", "title_fa": "گزارش", "body_md": body})
    assert out["outcome"] == "ok"
    sent = json.loads(deliver.calls.last.request.content)
    assert sent["body"] == body.replace(email, "[email]")  # complete, the e-mail masked
    assert "[cut]" not in sent["body"]

    decisions = mock.post(f"{API}/internal/v1/decisions").mock(
        return_value=httpx.Response(201, json={"ref": "D-000034", "status": "pending"})
    )
    items = [{"n": i, "label": f"مورد {i}"} for i in range(100)]
    what = "ش" * 20_000
    out = await call(
        gw,
        "propose",
        {"kind": "proposal", "title_fa": "فهرست", "what_md": what, "payload": {"items": items}},
    )
    assert out["outcome"] == "ok"
    sent = json.loads(decisions.calls.last.request.content)
    assert sent["payload"] == {"items": items} and sent["what"] == what
    deep: dict[str, Any] = {}
    cur = deep
    for _ in range(20):
        cur["x"] = {}
        cur = cur["x"]
    out = await call(gw, "propose", {"kind": "proposal", "title_fa": "عمیق", "payload": deep})
    assert (out["outcome"], out["code"]) == ("error", "invalid_args")  # refused, not flattened

    thread = mock.post(f"{API}/internal/v1/threads/TY-TECH/messages").mock(
        return_value=httpx.Response(201, json={"ref": "TY-TECH-0003", "citations": [], "meta": {}})
    )
    text = "ب" * 50_000
    out = await call(gw, "message.thread", {"thread": "TY-TECH", "body_md": text})
    assert out["outcome"] == "ok"
    assert json.loads(thread.calls.last.request.content)["body"] == text

    # Above the contract's cap: refused with the field named, never cut and sent.
    calls = len(deliver.calls)
    out = await call(
        gw, "deliver", {"work_ref": "W-000101", "title_fa": "گزارش", "body_md": "x" * 200_001}
    )
    assert (out["outcome"], out["code"]) == ("error", "invalid_args") and "body_md" in out["fields"]
    assert len(deliver.calls) == calls


async def test_deliver_to_unknown_work(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock)
    mock.get(f"{API}/internal/v1/work/ref/W-000999").mock(
        return_value=httpx.Response(404, json={"code": "not_found"})
    )
    out = await call(gw, "deliver", {"work_ref": "W-000999", "title_fa": "t", "body_md": "b"})
    assert (out["outcome"], out["code"]) == ("error", "not_found")


@pytest.mark.parametrize("quota", [{"tokens": 50000, "usd": 1.5}, 50000, None])
async def test_propose(mock: respx.MockRouter, gw: Gateway, quota: Any) -> None:
    Stub(mock)
    work_route(mock)
    route = mock.post(f"{API}/internal/v1/decisions").mock(
        return_value=httpx.Response(201, json={"ref": "D-000033", "status": "pending"})
    )
    args = {
        "kind": "hire",
        "title_fa": "استخدام SRE",
        "what_md": "w",
        "why_md": "y",
        "risk": "low",
        "reversible": True,
        "payload": {"company": "TY", "department": "TECH", "role": "sre"},
    }
    if quota is not None:
        args["quota_estimate"] = quota
    out = await call(gw, "propose", args)
    assert out["result"] == {"decision": "D-000033", "status": "pending", "kind": "hire"}
    sent = json.loads(route.calls.last.request.content)
    assert sent["work_id"] == "11111111-1111-1111-1111-111111111111"
    assert sent["title"] == "استخدام SRE" and sent["payload"]["role"] == "sre"
    assert sent["quota_estimate"] == ({"tokens": 50000} if quota == 50000 else quota)


@pytest.mark.parametrize("quota", [True, {"tokens": True}, "lots"])
async def test_propose_quota_is_never_guessed(
    mock: respx.MockRouter, gw: Gateway, quota: Any
) -> None:
    Stub(mock)
    work_route(mock)
    route = mock.post(f"{API}/internal/v1/decisions")
    args = {"kind": "proposal", "title_fa": "پیشنهاد", "quota_estimate": quota}
    out = await call(gw, "propose", args)
    assert out["outcome"] == "error" and out["code"] == "invalid_args"  # a boolean is not 1 token
    assert not route.called


async def test_messages_owner_and_thread(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock)
    post = mock.post(f"{API}/internal/v1/threads/TY-TECH-MGR/messages").mock(
        return_value=httpx.Response(
            201, json={"ref": "TY-TECH-MGR-0004", "citations": [], "meta": {}}
        )
    )
    note = mock.post(f"{API}/internal/v1/notifications").mock(
        return_value=httpx.Response(201, json={"id": "n", "level": "report", "state": "queued"})
    )
    out = await call(gw, "message.owner", {"body_md": "سلام", "links": {"work": "W-000101"}})
    assert out["ref"] == "TY-TECH-MGR-0004"
    assert json.loads(post.calls.last.request.content)["links"] == {"work": "W-000101"}
    sent = json.loads(note.calls.last.request.content)
    assert sent["level"] == "report" and sent["link_ref"] == "TY-TECH-MGR-0004"
    thread = mock.post(f"{API}/internal/v1/threads/TY-TECH/messages").mock(
        return_value=httpx.Response(
            201,
            json={
                "ref": "TY-TECH-0002",
                "citations": [{"kind": "decision", "ref": "D-1"}],
                "meta": {"citations_dropped": 1},
            },
        )
    )
    out = await call(
        gw,
        "message.thread",
        {
            "thread": "TY-TECH",
            "body_md": "به تیم",
            "citations": [{"kind": "decision", "ref": "D-1"}, {"kind": "work", "ref": "W-404"}],
        },
    )
    assert out["result"]["citations_kept"] == 1 and out["result"]["citations_dropped"] == 1
    assert len(json.loads(thread.calls.last.request.content)["citations"]) == 2
    Stub(mock, gate(own_thread=None))
    assert (await call(gw, "message.owner", {"body_md": "x"}))["code"] == "no_thread"


async def test_memory_write(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock)
    route = mock.post(f"{API}/internal/v1/memory").mock(
        return_value=httpx.Response(201, json={"id": 9})
    )
    out = await call(
        gw, "memory.write", {"note_md": "مالک گزارش کوتاه میخواهد", "tags": ["pref", " "]}
    )
    assert (out["ref"], out["result"]) == ("memory:9", {"note": 9})
    assert json.loads(route.calls.last.request.content)["tags"] == ["pref"]


async def test_work_lifecycle(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock)
    work_route(mock)
    base = f"{API}/internal/v1/work/11111111-1111-1111-1111-111111111111"
    for action in ("accept", "progress", "fail"):
        mock.post(f"{base}/{action}").mock(
            return_value=httpx.Response(200, json={"status": "in_progress"})
        )
    assert (await call(gw, "work.accept", {"ref": "W-000101", "note": "شروع"}))["result"][
        "status"
    ] == "in_progress"
    assert mock.routes  # accept + the note as progress
    assert (await call(gw, "work.progress", {"ref": "W-000101", "note": "نیمه", "pct": 50}))[
        "ref"
    ] == "W-000101"
    assert (await call(gw, "work.fail", {"ref": "W-000101", "reason": "نشد", "decline": True}))[
        "outcome"
    ] == "ok"
    deleg = mock.post(f"{base}/delegate").mock(
        return_value=httpx.Response(201, json={"ref": "W-000102"})
    )
    out = await call(
        gw,
        "work.delegate",
        {
            "ref": "W-000101",
            "to": "TY-TECH-01",
            "title_fa": "پایش",
            "brief_md": "b",
            "budget": 40000,
        },
    )
    assert out["result"] == {"work": "W-000102", "parent": "W-000101", "assignee": "TY-TECH-01"}
    assert json.loads(deleg.calls.last.request.content)["budget"] == {"tokens": 40000}
    await call(
        gw,
        "work.delegate",
        {
            "ref": "W-000101",
            "to": "TY-TECH-01",
            "title_fa": "پایش",
            "budget": {"tokens": 10, "usd": 0.5},
        },
    )
    assert json.loads(deleg.calls.last.request.content)["budget"] == {"tokens": 10, "usd": 0.5}
    await call(gw, "work.delegate", {"ref": "W-000101", "to": "TY-TECH-01", "title_fa": "بی‌بودجه"})
    assert "budget" not in json.loads(deleg.calls.last.request.content)
    mock.get(f"{API}/internal/v1/work/ref/W-000555").mock(
        return_value=httpx.Response(404, json={"code": "not_found"})
    )
    assert (
        await call(gw, "work.delegate", {"ref": "W-000555", "to": "TY-TECH-01", "title_fa": "x"})
    )["code"] == "not_found"
    assert (await call(gw, "work.accept", {"ref": "W-000555"}))["code"] == "not_found"


@pytest.mark.parametrize(
    ("to", "expected"),
    [
        ("FX", {"company": "FX"}),
        ("TY-GROWTH", {"department": "GROWTH"}),
        ("FX-GROWTH", {"company": "FX", "department": "GROWTH"}),
        ("TY-GROWTH-MGR", {"to": "TY-GROWTH-MGR"}),
    ],
)
async def test_work_request_targets(
    mock: respx.MockRouter, gw: Gateway, to: str, expected: dict[str, str]
) -> None:
    Stub(mock)
    work_route(mock)
    route = mock.post(f"{API}/internal/v1/work").mock(
        return_value=httpx.Response(
            201, json={"work": {"ref": "W-000200", "assignee": {"code": "X"}}, "decision": None}
        )
    )
    out = await call(gw, "work.request", {"to": to, "title_fa": "درخواست", "brief_md": "b"})
    assert out["result"] == {"work": "W-000200", "assignee": "X"}
    sent = json.loads(route.calls.last.request.content)
    assert {k: sent[k] for k in expected} == expected
    assert sent["requested_by_work_id"] == "11111111-1111-1111-1111-111111111111"


async def test_activity_and_notify(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock)
    act = mock.post(f"{API}/internal/v1/activity").mock(
        return_value=httpx.Response(200, json={"code": "TY-TECH-MGR"})
    )
    assert (await call(gw, "activity.set", {"state": "idle"}))["result"] == {"activity": "sleeping"}
    assert json.loads(act.calls.last.request.content) == {
        "employee": "TY-TECH-MGR",
        "activity": "sleeping",
        "note": None,
    }
    note = mock.post(f"{API}/internal/v1/notifications").mock(
        return_value=httpx.Response(201, json={"id": "n2", "level": "decision", "state": "queued"})
    )
    out = await call(
        gw,
        "notify",
        {
            "level": "info",
            "title_fa": "اطلاع",
            "body_fa": "تماس 09121234567",
            "link": {"kind": "work", "ref": "W-000101"},
        },
    )
    assert out["result"] == {"level": "decision", "state": "queued"}
    sent = json.loads(note.calls.last.request.content)
    assert "09121234567" not in sent["body_fa"] and sent["link_kind"] == "work"


async def test_slow_tools_time_out(mock: respx.MockRouter) -> None:
    import asyncio

    Stub(mock)

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    mock.get(f"{API}/internal/v1/health/sites").mock(side_effect=slow)
    gw = Gateway(LIB, T.Api(API, 5), Opa(OPA), tool_timeout_s=0.1)
    assert (await call(gw, "health.sites"))["code"] == "tool_timeout"


async def test_audit_failures_never_fail_the_call(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock)
    mock.post(f"{API}/internal/v1/runs/self/tool-calls").mock(return_value=httpx.Response(500))
    mock.get(f"{API}/internal/v1/memory").mock(return_value=httpx.Response(200, json=[]))
    assert (await call(gw, "memory.read"))["outcome"] == "ok"
    mock.post(f"{API}/internal/v1/runs/self/tool-calls").mock(side_effect=httpx.ConnectError("x"))
    assert (await call(gw, "memory.read"))["outcome"] == "ok"


async def test_any_failure_is_an_outcome_with_its_audit_row(
    mock: respx.MockRouter, gw: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prompt 5.1 §2.3: no exception reaches a 500 without an audit row."""
    s = Stub(mock)

    async def broken(api: T.Api, call: T.Call, a: Any) -> T.Result:
        raise KeyError("id")

    monkeypatch.setitem(T.TOOLS, "memory.read", (T.Empty, broken))
    out = await call(gw, "memory.read")
    assert (out["outcome"], out["code"], out["class"]) == ("error", "internal_error", "A0")
    assert s.records[-1] == {
        "tool": "memory.read",
        "class": "A0",
        "outcome": "error",
        "code": "internal_error",
        "ref": None,
        "step": 1,
    }
    # The api answering something that is not the expected object: the same.
    monkeypatch.undo()
    mock.get(f"{API}/internal/v1/work/ref/W-000101").mock(
        return_value=httpx.Response(200, json=["not", "an", "object"])
    )
    out = await call(gw, "deliver", {"work_ref": "W-000101", "title_fa": "t", "body_md": "b"})
    assert out["code"] == "api_bad_answer" and s.records[-1]["code"] == "api_bad_answer"
    mock.post(f"{API}/internal/v1/runs/self/reserve").mock(
        return_value=httpx.Response(200, json=["no gate"])
    )
    n = len(s.records)
    assert (await call(gw, "memory.read"))["code"] == "internal_error"
    assert len(s.records) == n + 1


async def test_one_deadline_for_the_whole_call(mock: respx.MockRouter) -> None:
    import asyncio
    import time

    s = Stub(mock)

    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=s.gate)

    mock.post(f"{API}/internal/v1/runs/self/reserve").mock(side_effect=hang)
    gw = Gateway(LIB, T.Api(API, 10), Opa(OPA), tool_timeout_s=10, deadline_s=0.8)
    t0 = time.monotonic()
    out = await call(gw, "memory.read")
    assert out["code"] == "tool_timeout" and time.monotonic() - t0 < 1.0
    assert s.records[-1]["code"] == "tool_timeout"
    assert Settings().deadline_s < 40  # below the worker's timeout for a gateway call


async def test_refusals_carry_the_apis_persian_hint(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock)
    work_route(mock)
    hint = "استخدام بسته است؛ کمبود تیم را در خروجی‌ات بنویس"
    mock.post(f"{API}/internal/v1/decisions").mock(
        return_value=httpx.Response(
            403,
            json={"code": "hiring_closed", "title": "Hiring is closed", "message_fa": hint},
        )
    )
    args = {
        "kind": "hire",
        "title_fa": "استخدام SRE",
        "payload": {"company": "TY", "department": "TECH", "role": "sre"},
    }
    out = await call(gw, "propose", args)
    assert (out["outcome"], out["code"], out["hint_fa"]) == ("denied", "hiring_closed", hint)
    # Field errors and hints are scrubbed like everything else the model reads.
    email = "ali" + "@" + "example.com"
    mock.get(f"{API}/internal/v1/work/ref/W-000104").mock(
        return_value=httpx.Response(
            422,
            json={
                "code": "validation_failed",
                "fields": {"to": f"no employee {email}"},
                "message_fa": f"ورودی نادرست ({email})" + "ـ" * 400,
            },
        )
    )
    out = await call(gw, "work.get", {"ref": "W-000104"})
    assert out["fields"] == {"to": "no employee [email]"}
    assert email not in out["hint_fa"] and len(out["hint_fa"]) == T.HINT_CHARS
    assert (await call(gw, "work.get", {"ref": "W-000101"}))["hint_fa"] is None


async def test_every_written_field_is_scrubbed(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock)
    work_route(mock)
    email = "ali" + "@" + "example.com"
    deliver = mock.post(
        f"{API}/internal/v1/work/11111111-1111-1111-1111-111111111111/deliver"
    ).mock(return_value=httpx.Response(200, json={"deliverable": "O-000079"}))
    await call(
        gw,
        "deliver",
        {
            "work_ref": "W-000101",
            "title_fa": "گزارش",
            "body_md": "b",
            "evidence": [{"kind": "link", "ref": f"mailto:{email}", "note": f"از {email}"}],
        },
    )
    assert email not in deliver.calls.last.request.content.decode()
    memory = mock.post(f"{API}/internal/v1/memory").mock(
        return_value=httpx.Response(201, json={"id": 10})
    )
    await call(gw, "memory.write", {"note_md": "یادداشت", "tags": [email]})
    assert json.loads(memory.calls.last.request.content)["tags"] == ["[email]"]
    note = mock.post(f"{API}/internal/v1/notifications").mock(
        return_value=httpx.Response(201, json={"id": "n3", "level": "info", "state": "queued"})
    )
    await call(
        gw, "notify", {"level": "info", "title_fa": "t", "link": {"kind": "work", "ref": email}}
    )
    assert json.loads(note.calls.last.request.content)["link_ref"] == "[email]"


# ------------------------------------------------------------------- http --
async def test_http_api_authenticates_the_runtime(mock: respx.MockRouter, tmp_path: Path) -> None:
    digest = tmp_path / "worker-token.sha256"
    digest.write_text(hashlib.sha256(WORKER.encode()).hexdigest())
    state = State(Settings(worker_token_file=str(digest), max_body_bytes=2000))
    state.load_digest()
    state.gateway = Gateway(LIB, T.Api(API, 5), Opa(OPA))
    Stub(mock)
    mock.get(f"{API}/internal/v1/memory").mock(return_value=httpx.Response(200, json=[]))
    transport = httpx.ASGITransport(app=build_app(state))
    async with httpx.AsyncClient(transport=transport, base_url="http://gw") as c:
        assert (await c.get("/v1/health")).status_code == 401
        bad = {"Authorization": "Bearer wrong"}
        assert (await c.post("/v1/tools/call", headers=bad, json={})).status_code == 401
        good = {"Authorization": f"Bearer {WORKER}"}
        assert (await c.get("/v1/health", headers=good)).json()["roles"] == len(LIB.roles)
        r = await c.post(
            "/v1/tools/call",
            headers=good,
            json={"token": TOKEN, "step": 1, "tool": "memory.read", "args": {}},
        )
        assert r.status_code == 200 and r.json()["outcome"] == "ok"
        r = await c.post(
            "/v1/tools/call",
            headers=good,
            json={"token": TOKEN, "step": 0, "tool": "x", "secret": "s3cr3t"},
        )
        assert r.status_code == 422 and "s3cr3t" not in r.text
        big = await c.post(
            "/v1/tools/call",
            headers=good,
            content=b"{" + b" " * 3000 + b"}",
            params={},
        )
        assert big.status_code == 413

        async def chunked() -> Any:  # no Content-Length: capped while it is read
            for _ in range(10):
                yield b" " * 500

        big = await c.post("/v1/tools/call", headers=good, content=chunked())
        assert big.status_code == 413
        assert "content-length" not in {k.lower() for k in big.request.headers}

        async def small() -> Any:
            yield json.dumps(
                {"token": TOKEN, "step": 1, "tool": "memory.read", "args": {}}
            ).encode()

        r = await c.post(
            "/v1/tools/call", headers={**good, "Content-Type": "application/json"}, content=small()
        )
        assert r.status_code == 200 and r.json()["outcome"] == "ok", r.text
    no_digest = State(Settings(worker_token_file=str(tmp_path / "missing")))
    no_digest.load_digest()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=build_app(no_digest)), base_url="http://gw"
    ) as c:
        assert (
            await c.get("/v1/health", headers={"Authorization": f"Bearer {WORKER}"})
        ).status_code == 401


async def test_create_app_starts_and_stops(tmp_path: Path) -> None:
    digest = tmp_path / "d"
    digest.write_text(hashlib.sha256(WORKER.encode()).hexdigest())
    app = create_app(Settings(worker_token_file=str(digest), api_url=API, opa_url=OPA))
    async with app.router.lifespan_context(app):
        assert app.state.gw.gateway is not None and app.state.gw.worker_digest


# ------------------------------------------------------ review of 5.1 (§B) --
async def test_a_large_persian_output_passes_the_http_body_cap(
    mock: respx.MockRouter, tmp_path: Path
) -> None:
    """Through the real HTTP app with the default body cap: a 200,000-character
    Persian deliverable (about 400 KB as UTF-8 JSON) reaches the api whole
    (prompt 5.1 review, blocker 2)."""
    digest = tmp_path / "worker-token.sha256"
    digest.write_text(hashlib.sha256(WORKER.encode()).hexdigest())
    state = State(Settings(worker_token_file=str(digest)))
    assert state.settings.max_body_bytes >= 1024 * 1024
    state.load_digest()
    state.gateway = Gateway(LIB, T.Api(API, 5), Opa(OPA))
    Stub(mock)
    work_route(mock)
    deliver = mock.post(
        f"{API}/internal/v1/work/11111111-1111-1111-1111-111111111111/deliver"
    ).mock(
        return_value=httpx.Response(200, json={"deliverable": "O-000079", "closed_children": []})
    )
    body = ("گزارش فارسی بلند با جزئیات کامل. " * 7000)[:200_000]
    assert len(body) == 200_000
    payload = {
        "token": TOKEN,
        "step": 1,
        "tool": "deliver",
        "args": {"work_ref": "W-000101", "title_fa": "گزارش", "body_md": body},
    }
    raw = json.dumps(payload, ensure_ascii=False).encode()
    assert len(raw) > 256 * 1024
    transport = httpx.ASGITransport(app=build_app(state))
    async with httpx.AsyncClient(transport=transport, base_url="http://gw") as c:
        r = await c.post(
            "/v1/tools/call",
            headers={"Authorization": f"Bearer {WORKER}", "Content-Type": "application/json"},
            content=raw,
        )
    assert r.status_code == 200, r.text[:200]
    assert r.json()["outcome"] == "ok"
    assert json.loads(deliver.calls.last.request.content)["body"] == body


async def test_a_reserve_answer_without_its_lock_counts_as_locked(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    g = gate()
    del g["lock"]
    s = Stub(mock, g)
    mock.get(f"{API}/internal/v1/memory").mock(return_value=httpx.Response(200, json=[]))
    await call(gw, "memory.read", {})
    assert s.opa_inputs[-1]["context"]["company_locked"] is True
    s.gate = gate()  # lock: null -> not locked
    await call(gw, "memory.read", {})
    assert s.opa_inputs[-1]["context"]["company_locked"] is False


async def test_a_cancelled_call_still_has_its_audit_row(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    s = Stub(mock)
    started = asyncio.Event()

    async def slow(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.sleep(30)
        return httpx.Response(200, json={})

    mock.get(f"{API}/internal/v1/work/ref/W-000101").mock(side_effect=slow)
    task = asyncio.create_task(gw.call(TOKEN, 1, 0, "work.get", {"ref": "W-000101"}))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [(r["tool"], r["outcome"], r["code"]) for r in s.records] == [
        ("work.get", "error", "cancelled")
    ]


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
async def test_infinite_or_nan_money_is_invalid_args(
    mock: respx.MockRouter, gw: Gateway, bad: float
) -> None:
    Stub(mock)
    out = await call(
        gw,
        "propose",
        {"kind": "proposal", "title_fa": "x", "quota_estimate": {"usd": bad}},
    )
    assert (out["outcome"], out["code"]) == ("error", "invalid_args")


# ---------------------------------------------------------- files.read --
FILE_ID = "0193e7a1-0000-7000-8000-00000000f11e"


async def test_files_read_shows_a_file_and_the_pictures_to_attach(mock: respx.MockRouter) -> None:
    s = Stub(mock)
    gw = Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000)  # the real charters
    secret_phone = "0912" + "345" + "6789"
    frames = [f"0193e7a1-0000-7000-8000-0000000000{i:02d}" for i in range(14)]
    route = mock.get(f"{API}/internal/v1/files/{FILE_ID}/meta")
    route.mock(
        return_value=httpx.Response(
            200,
            json={
                "id": FILE_ID,
                "name": "passport-scan-ali.jpg",
                "sha256": "a" * 64,
                "mime": "video/mp4",
                "size": 1234,
                "kind": "video",
                "status": "ready",
                "duration_s": 31.5,
                "variants": {"poster": frames[0]},
                "frames": [{"id": f, "at_s": 2.5 * i} for i, f in enumerate(frames)],
                "transcript": f"شماره‌ی من {secret_phone} است",
            },
        )
    )
    out = await call(gw, "files.read", {"file_id": FILE_ID})
    assert out["outcome"] == "ok" and out["ref"] == f"file:{FILE_ID}" and out["class"] == "A0"
    r = out["result"]
    assert "name" not in r and "sha256" not in r  # no file name or hash for the model
    assert secret_phone not in json.dumps(r, ensure_ascii=False)  # the transcript is masked
    assert r["view"] == {"variant": "original", "image_file_ids": frames[:13]}
    assert r["frames_at_s"] == [2.5 * i for i in range(13)]  # where each one is (s)
    assert s.records[-1]["tool"] == "files.read" and s.records[-1]["outcome"] == "ok"
    # An image: its agent copy (<= 1568 px, no EXIF; the original is never
    # loaded); still processing: nothing yet; no frames: the poster; a PDF: its text.
    agent, thumb = frames[2], frames[3]
    image = {"kind": "image", "status": "ready", "mime": "image/png", "agent": agent}
    for meta, args, want in (
        (image, {}, [agent]),
        ({**image, "variants": {"thumb": thumb}}, {"variant": "thumb"}, [thumb]),
        ({"kind": "image", "status": "ready"}, {}, []),  # no agent copy: nothing to show
        ({"kind": "video", "status": "processing"}, {}, []),
        ({"kind": "video", "status": "ready", "variants": {"poster": frames[1]}}, {}, [frames[1]]),
        (
            {
                "kind": "video",
                "status": "ready",
                "frames": frames,
                "variants": {"poster": frames[1]},
            },
            {"variant": "poster"},
            [frames[1]],
        ),
        ({"kind": "audio", "status": "ready", "transcript": "سلام"}, {}, []),
        ({"kind": "document", "status": "ready", "text": f"قرارداد {secret_phone}"}, {}, []),
    ):
        route.mock(return_value=httpx.Response(200, json={"id": FILE_ID, **meta}))
        got = await call(gw, "files.read", {"file_id": FILE_ID, **args})
        assert got["result"]["view"] == {
            "variant": args.get("variant", "original"),
            "image_file_ids": want,
        }, meta
    assert "قرارداد" in got["result"]["text"] and secret_phone not in got["result"]["text"]
    bad = await call(gw, "files.read", {"file_id": FILE_ID, "variant": "agent"})
    assert (bad["outcome"], bad["code"]) == ("error", "invalid_args")
    # Another company's file: the api's 403 passes through as denied.
    route.mock(return_value=httpx.Response(403, json={"code": "policy_denied"}))
    out = await call(gw, "files.read", {"file_id": FILE_ID})
    assert (out["outcome"], out["code"]) == ("denied", "policy_denied")
    route.mock(return_value=httpx.Response(200, json=["not", "an", "object"]))
    assert (await call(gw, "files.read", {"file_id": FILE_ID}))["code"] == "api_bad_answer"
    bad = await call(gw, "files.read", {"file_id": "../../etc/passwd"})
    assert (bad["outcome"], bad["code"]) == ("error", "invalid_args")


async def test_the_old_file_view_name_is_unknown(mock: respx.MockRouter, gw: Gateway) -> None:
    """Prompt 6 built it as file.view; the tool is files.read (agents/tools.md,
    review of 6): the old name is refused before the api is asked."""
    Stub(mock)
    route = mock.get(f"{API}/internal/v1/files/{FILE_ID}/meta")
    out = await call(gw, "file.view", {"file_id": FILE_ID})
    assert out["outcome"] == "denied" and out["code"] == "unknown_tool"
    assert not route.called
