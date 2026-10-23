"""Prompt 12, the joins of its two parts (contract §21.6, §21.9, §21.13):
the deploy card's real diff (part B, §7) gets the substitutes' second code
review (part A, §9.1) and shows it as `deploy.second_review`; a sampled claim
(part B, §12) gets its cross-check, and a disagreement sends it back to the
overseer without any claim verdict; a company's CEO reaches its seats; the
OKR trigger reads prompt 11's key results as prompt 11 computes them."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx

from hq_api.domain import advisor as A
from hq_api.domain import substitutes as S
from hq_api.hub import Hub

from .conftest import agent_headers, idem, step_up
from .test_p12a_advisor import _end_test_runs  # noqa: F401 - an autouse fixture here too
from .test_p12a_substitutes import bench, claim, done, per_day
from .test_p12b_cards import KEY, card, repo  # noqa: F401 - `repo` is a fixture
from .test_p12b_people import _deliverable_of, _fact_checker


async def test_the_deploy_cards_diff_gets_a_second_review_that_never_approves_or_blocks(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    owner_session: dict[str, Any],
    repo: Any,  # noqa: F811 - the fixture
) -> None:
    co, name = repo["co"], repo["name"]
    head = repo["repo"].change(21, f"print('three')\nAWS = '{KEY}'\n")
    tech = await agent_headers(f"{co['code']}-TECH-MGR")
    async with bench(su, hub, cli=("gpt",)):
        await per_day(su, "gpt", "code_review", 5)
        body = card(name, 21, head)
        # A proposer's own second_review is never kept (it is the api's).
        body["payload"]["second_review"] = {"player": "gpt", "findings": [], "verified": True}
        r = await client.post("/internal/v1/decisions", headers={**tech, **idem()}, json=body)
        assert r.status_code == 201, r.text
        ref = r.json()["ref"]
        assert r.json()["payload"]["second_review"] is None
        call = await su.fetchrow(
            """SELECT * FROM substitutes.calls WHERE purpose_kind = 'decision' AND purpose_ref = $1
                 AND seat = 'code_review'""",
            ref,
        )
        assert call is not None and call["state"] == "queued" and call["caller_code"] == "deploy-review"
        job = (await claim(client))["job"]
        assert job["id"] == str(call["id"]) and job["checkout"] == {"repo": name, "head_sha": head}
        # The review reads the card's masked diff: the key never reaches it.
        assert "print('three')" in job["input_md"] and KEY not in job["input_md"]
        assert "logo.bin" in job["input_md"] and "(binary file, no patch)" in job["input_md"]
        finding = {"path": "app.py", "line": 2, "severity": "high", "title_fa": "کلید در کد",
                   "detail_md": "a key in the source"}  # fmt: skip
        ok = await done(client, job["id"], ok=True, findings=[finding])
        assert ok.status_code == 200 and ok.json()["state"] == "done", ok.text
        shown = await client.get(f"/api/v1/decisions/{ref}", headers=owner_session["headers"])
        review = shown.json()["payload"]["second_review"]
        assert review["player"] == "gpt" and review["verified"] == 0
        assert review["findings"][0]["path"] == "app.py" and review["findings"][0]["verified"] is None
        # It never approves or blocks: the seal works as without it, and no
        # unverified finding reaches the card's risk note.
        seal = await step_up(hub, owner_session["session_id"], "decision.approve", ref)
        approved = await client.post(
            f"/api/v1/decisions/{ref}/approve",
            headers={**owner_session["headers"], **idem(), **seal},
            json={},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved" and approved.json()["risk_note"] is None


async def test_a_deploy_card_without_a_diff_queues_no_review(
    su: Any, client: httpx.AsyncClient, repo: Any  # noqa: F811 - the fixture
) -> None:
    co = repo["co"]
    head = repo["repo"].change(22, "print('x')\n")
    tech = await agent_headers(f"{co['code']}-TECH-MGR")
    # A repository the hub cannot read: no diff, so nothing to review.
    r = await client.post(
        "/internal/v1/decisions", headers={**tech, **idem()}, json=card("acme/unreadable", 22, head)
    )
    assert r.status_code == 201, r.text
    assert r.json()["payload"]["diff_unavailable"] == "no_access"
    assert r.json()["payload"]["second_review"] is None
    assert not await su.fetchval(
        "SELECT count(*) FROM substitutes.calls WHERE purpose_kind = 'decision' AND purpose_ref = $1",
        r.json()["ref"],
    )


async def _post_claim(client: httpx.AsyncClient, fc: dict[str, str], **body: Any) -> dict[str, Any]:
    r = await client.post("/internal/v1/claims", headers={**fc, **idem()}, json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


async def test_a_disagreeing_cross_check_sends_the_claim_back_to_the_overseer_and_never_decides(
    hub: Hub, su: Any, client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    author = f"{co['code']}-GROWTH-MGR"
    fc = await agent_headers(await _fact_checker(su))
    dl = await _deliverable_of(su, author)
    overseer = await su.fetchval(
        """SELECT e.code FROM core.employees e JOIN core.companies c ON c.id = e.company_id
           WHERE e.kind = 'overseer' AND e.status = 'active' AND c.kind = 'holding'
           ORDER BY e.created_at LIMIT 1"""
    )
    async with bench(su, hub, cli=("gpt",)):
        await per_day(su, "gpt", "overseer_cross_check", 5)
        # Not sampled (no protocol): no cross-check.
        plain = await _post_claim(client, fc, deliverable=dl, claim_md="ادعای بی‌نمونه", verdict="confirmed")
        assert not await su.fetchval(
            "SELECT count(*) FROM substitutes.calls WHERE purpose_kind = 'claim' AND purpose_ref = $1",
            plain["ref"],
        )
        # Sampled (PR-001): its second check is queued, without the verdict.
        sampled = await _post_claim(client, fc, deliverable=dl, claim_md="کاربران ۲۰٪ رشد کردند",
                                    verdict="confirmed", protocol="PR-001")  # fmt: skip
        job = (await claim(client))["job"]
        assert job["seat"] == "overseer_cross_check" and "۲۰٪" in job["input_md"]
        assert "confirmed" not in job["input_md"].split("Claim:")[1]
        claims_before = await su.fetchval("SELECT count(*) FROM quality.claims")
        answer = json.dumps({"verdict": "refuted", "reason_md": "the report says 12%"})
        ok = await done(client, job["id"], ok=True, text_md=answer)
        assert ok.status_code == 200 and ok.json()["state"] == "done", ok.text
        # Back to the overseer, as work; no claim row and no verdict from it.
        back = await su.fetchrow(
            """SELECT w.id, w.brief, e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
               JOIN substitutes.calls c ON c.reply_work_id = w.id WHERE c.id = $1::uuid""",
            job["id"],
        )
        try:
            assert back is not None and back["code"] == overseer
            assert sampled["ref"] in back["brief"] and "never evidence" in back["brief"]
            assert await su.fetchval("SELECT count(*) FROM quality.claims") == claims_before
            assert await su.fetchval(
                "SELECT count(*) FROM audit.entries WHERE action = 'claim.returned' AND target_ref = $1",
                sampled["ref"],
            ) == 1
            # The overseer decides it again: the same claim is not checked again.
            oc = await agent_headers(overseer)
            again = await _post_claim(client, oc, deliverable=dl, claim_md="کاربران ۲۰٪ رشد کردند",
                                      verdict="refuted", protocol="PR-001",
                                      evidence=[{"kind": "metric", "ref": "growth.users", "note": "۱۲٪"}])  # fmt: skip
            assert not await su.fetchval(
                "SELECT count(*) FROM substitutes.calls WHERE purpose_kind = 'claim' AND purpose_ref = $1",
                again["ref"],
            )
            # An agreeing cross-check stays on its call: nothing goes back.
            other = await _post_claim(client, fc, deliverable=dl, claim_md="درآمد ثابت ماند",
                                      verdict="unverifiable", protocol="PR-001")  # fmt: skip
            job2 = (await claim(client))["job"]
            await done(client, job2["id"], ok=True,
                       text_md=json.dumps({"verdict": "unverifiable", "reason_md": "-"}))  # fmt: skip
            row = await su.fetchrow("SELECT reply_work_id FROM substitutes.calls WHERE id = $1::uuid", job2["id"])
            assert row["reply_work_id"] is None and other["verdict"] == "unverifiable"
        finally:
            if back is not None:
                await su.execute(
                    """UPDATE agents.runs SET state = 'refused', finished_at = now(), error_code = 'test_cleanup'
                       WHERE work_id = $1 AND state = 'queued'""",
                    back["id"],
                )


def test_cross_verdicts_are_read_by_code() -> None:
    assert S.cross_verdict('ok {"verdict": "refuted", "reason_md": "x"} done') == ("refuted", "x")
    assert S.cross_verdict('{"verdict": "maybe"}') == (None, "")
    assert S.cross_verdict("no json") == (None, "")


async def test_a_companys_ceo_reaches_its_seats(
    client: httpx.AsyncClient, hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    """The players and seats are the holding's rows: a CEO's call (its own
    company's scope) still finds them and is queued, written for its company."""
    co = await new_company()
    ceo = await agent_headers(f"{co['code']}-CEO")
    async with bench(su, hub, cli=("gpt",)):
        await per_day(su, "gpt", "assistant_errand", 5)
        r = await client.post(
            "/internal/v1/substitutes/call", headers=ceo,
            json={"seat": "assistant_errand", "input_md": "این عنوان را کوتاه کن: گزارش هفته."},
        )  # fmt: skip
        assert r.status_code == 200 and r.json()["state"] == "queued", r.text
        row = await su.fetchrow(
            "SELECT company_id, caller_code FROM substitutes.calls WHERE id = $1::uuid", r.json()["call"]
        )
        assert row["company_id"] == co["id"] and row["caller_code"] == f"{co['code']}-CEO"
        job = (await claim(client))["job"]
        await done(client, job["id"], ok=False, error="failed")


def test_okr_progress_is_prompt_11s() -> None:
    assert A.OKR_TABLE == "governance.key_results"
    assert A.okr_progress(0, 100, 25) == 0.25
    assert A.okr_progress(100, 0, 75) == 0.25  # a falling target
    assert A.okr_progress(0, 100, None) == 0.0 and A.okr_progress(0, 100, 150) == 1.0
    assert A.okr_progress(5, 5, 5) == 1.0 and A.okr_progress(5, 5, 4) == 0.0
    start, end = A.quarter_span("1405-Q3") or (None, None)
    assert start == date(2026, 9, 23) and end == date(2026, 12, 22)
