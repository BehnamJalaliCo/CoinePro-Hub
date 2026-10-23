"""Prompt 14 laid on the deployed prompt 13 (r14f: prompts 11, 12 and 13 under
the archive). What only shows when they meet:

- «از هاب بپرس» (prompt 12 §2, contract §21.2) searches the archive's records
  too, within the asker's clearance (§23.9), filtered by the database before
  anything is ranked: a lower clearance never sees a higher record, and a
  record above `agents_max` never reaches the librarian (a model).
- The system roles that have a system charter run when code gives them work:
  the librarian (its ask) and the archivist (its items); the secretary only
  for a meeting; the report system never.
- knowledge.search kind `records` beside prompt 11's four-layer `knowledge`.
- The archivist's system prompt in the order prompt 13 set.
"""

from __future__ import annotations

import json
import random
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx
import pytest

from hq_api.archive import clearance as CL
from hq_api.domain import charter as CH
from hq_api.domain import corpus
from hq_api.hub import Hub
from hq_api.principal import Principal

from .conftest import agent_headers, idem
from .p10_support import holding_switch
from .p14_support import fakes, filed, pdf, reseed, upload
from .test_agents import run, step

OWNER = Principal(kind="owner", code="owner", role="owner")


@pytest.fixture(autouse=True)
async def _seeded_and_tidy(owner_db: Any, su: Any) -> Any:
    await reseed(owner_db)
    yield
    # The work these tests gave the system roles queued runs nobody executes here.
    await su.execute(
        """UPDATE agents.runs r SET state = 'refused', finished_at = now(), error_code = 'test_cleanup'
           FROM core.employees e WHERE e.id = r.employee_id AND r.state IN ('queued', 'running')
             AND e.code IN ('HQ-LIB', 'HQ-ARC', 'HQ-SEC')"""
    )


def _word() -> str:
    return f"omega{random.randint(10**6, 10**7)}"


def _passages(row: Any) -> list[dict[str, Any]]:
    p = row["passages"]
    return list(json.loads(p) if isinstance(p, str) else p or [])


async def _records(
    client: httpx.AsyncClient, h: dict[str, str], co: str, other: str, w: str
) -> dict[str, dict[str, Any]]:
    """One record at each level in a company, an internal one in another
    company and two in the holding, all matching the word `w`."""
    out: dict[str, dict[str, Any]] = {}
    async with fakes(ocr=False):
        for key, scope, level in (
            ("internal", co, None),
            ("confidential", co, "confidential"),
            ("secret", co, "secret"),
            ("other", other, None),
            ("hq_internal", "HQ", None),
            ("hq_confidential", "HQ", "confidential"),
        ):
            out[key] = await filed(
                client,
                h,
                scope,
                title=f"{w} {key} lease",
                text=f"the {w} lease of {key} ends in spring",
                level=level,
            )
    return out


async def test_ask_the_hub_finds_records_only_within_the_askers_clearance(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co, other = await new_company(), await new_company()
    h = owner_session["headers"]
    w = _word()
    recs = await _records(client, h, co["code"], other["code"], w)
    ref = {k: v["ref"] for k, v in recs.items()}

    # The owner's ask: every scope, up to `agents_max` (confidential), never the secret one.
    async with holding_switch(su, "released"):
        r = await client.post(
            "/api/v1/ask", headers={**h, **idem()}, json={"q": f"{w} lease کی تمام میشود؟"}
        )
    assert r.status_code == 202, r.text
    a = r.json()
    assert a["state"] == "answering", a
    row = await su.fetchrow("SELECT passages, found FROM knowledge.asks WHERE ref = $1", a["ref"])
    got = {p["ref"]: p for p in _passages(row) if p["kind"] == "record"}
    assert set(got) == {ref[k] for k in ref if k != "secret"}, got.keys()
    assert row["found"] == len(_passages(row))
    stored = json.dumps(_passages(row), ensure_ascii=False)
    assert ref["secret"] not in stored and f"{w} secret" not in stored
    assert "of confidential ends in spring" in got[ref["confidential"]]["text"]  # its content

    # The librarian's answer cites a record: the citation stands.
    r = await client.post(
        "/internal/v1/ask/answer",
        headers={**await agent_headers("HQ-LIB"), **idem()},
        json={
            "ask": a["ref"],
            "answer_md": f"اجاره در بهار تمام میشود ({ref['confidential']}).",
            "citations": [
                {"kind": "record", "ref": ref["confidential"]},
                {"kind": "record", "ref": ref["secret"]},  # never retrieved: dropped
            ],
        },
    )
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["state"] == "done" and done["citations_dropped"] == 1
    assert [(c["kind"], c["ref"]) for c in done["citations"]] == [("record", ref["confidential"])]

    # A lower clearance never sees a higher record: retrieval under an
    # agent's clearance (the default role: internal in its own company), and
    # under internal everywhere.
    q = f"{w} lease"
    async with hub.db.tx(await hub.companies.ids()) as tx:
        own = CL.Clearance(everything=False, code="X", grants={str(co["id"]): 10})
        seen_own, _ = await corpus.retrieve(
            tx, q, kinds=["record"], company_ids=None, clearance=own
        )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        everywhere = CL.Clearance(everything=False, code="X", grants={"*": 10})
        seen_all, _ = await corpus.retrieve(
            tx, q, kinds=["record"], company_ids=None, clearance=everywhere
        )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        owner_cap = await CL.for_ask(tx, OWNER)
        nothing, _ = await corpus.retrieve(tx, q, kinds=["record"], company_ids=None)
    mine = {p["ref"] for p in seen_own if w in p["title"]}
    assert mine == {ref["internal"]}
    assert {p["ref"] for p in seen_all if w in p["title"]} == {
        ref["internal"],
        ref["other"],
        ref["hq_internal"],
    }
    assert owner_cap.setting() == {"code": None, "grants": {"*": 20}}
    assert not [p for p in nothing if p["kind"] == "record"]  # no clearance: no record

    # The librarian's own knowledge.search (its clearance: internal in the holding).
    lib = await agent_headers("HQ-LIB")
    r = await client.get(
        "/internal/v1/knowledge/search", headers=lib, params={"q": w, "kinds": ["records"]}
    )
    assert r.status_code == 200, r.text
    assert {x["ref"] for x in r.json()} == {ref["hq_internal"]}


async def test_records_and_the_four_layers_in_one_knowledge_search(
    client: httpx.AsyncClient,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    """Prompt 11's `knowledge` and 14's `records` in one call, each under its
    own rule: the approved entry of the company's layer and the records within
    the CEO's clearance."""
    co = await new_company()
    h = owner_session["headers"]
    w = _word()
    async with fakes(ocr=False):
        low = await filed(client, h, co["code"], title=f"{w} memo", text=f"{w} memo")
        high = await filed(
            client, h, co["code"], title=f"{w} plan", text=f"{w} plan", level="confidential"
        )
    await su.execute(
        """INSERT INTO knowledge.entries (company_id, layer, kind, title_fa, body_md, sources,
               valid_until, status, approved_by_kind, approved_by_code, approved_at,
               created_by_kind, created_by_code)
           VALUES ($1, 'company', 'fact', $2, $3, '[{"kind": "work", "ref": "W-000001"}]',
                   CURRENT_DATE + 30, 'approved', 'owner', 'owner', now(), 'owner', 'owner')""",
        co["id"],
        f"قاعده‌ی {w}",
        f"متن قاعده‌ی {w}",
    )
    ceo = await agent_headers(f"{co['code']}-CEO")
    r = await client.get(
        "/internal/v1/knowledge/search",
        headers=ceo,
        params={"q": w, "kinds": ["knowledge", "records"]},
    )
    assert r.status_code == 200, r.text
    kinds = {(x["kind"], x["ref"].split("@")[0]) for x in r.json()}
    assert ("record", low["ref"]) in kinds and ("record", high["ref"]) not in kinds
    assert any(k != "record" for k, _ in kinds), kinds  # the layer's entry beside them
    assert all(x["kind"] != "record" or x["layer"] is None for x in r.json())


async def test_system_roles_with_a_system_charter_run_and_the_secretary_only_in_a_meeting(
    client: httpx.AsyncClient,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    agents: Any,
) -> None:
    """agents.queue_run (0029) queues a system role with a role; the runner
    runs it with a system charter, the secretary only for a meeting."""

    async def queue(code: str) -> Any:
        return await su.fetchval(
            """SELECT agents.queue_run(e.id, 'work', NULL, NULL, 'p14f', 'P3')
               FROM core.employees e WHERE e.code = $1""",
            code,
        )

    assert await queue("HQ-SYS") is None  # the report system: no charter, never
    async with holding_switch(su, "released"):
        sec = await queue("HQ-SEC")
        assert sec is not None
        c = await agents.runner.claim(str(sec))
        assert (c.state, c.final, c.code) == ("final", "refused", "employee_inactive")

        # The librarian answers an owner's ask in its own run (task class ask_hub).
        co = await new_company()
        h = owner_session["headers"]
        w = _word()
        async with fakes(ocr=False):
            rec = await filed(client, h, co["code"], title=f"{w} lease", text=f"{w} lease ends")
        a = (
            await client.post("/api/v1/ask", headers={**h, **idem()}, json={"q": f"{w} lease"})
        ).json()
        assert a["state"] == "answering", a
        lib_run = await su.fetchval(
            """SELECT r.id FROM agents.runs r JOIN knowledge.asks k ON k.work_id = r.work_id
               WHERE k.ref = $1 AND r.state = 'queued'""",
            a["ref"],
        )
        assert lib_run is not None
        agents.fake.enqueue(
            "HQ-LIB",
            step(
                "پاسخ",
                (
                    "ask.answer",
                    {
                        "ask": a["ref"],
                        "answer_md": f"اجاره تمام میشود ({rec['ref']}).",
                        "citations": [{"kind": "record", "ref": rec["ref"]}],
                    },
                ),
            ),
            "پاسخ دادم.",
        )
        out = await run(agents, lib_run)
        assert out["state"] == "done", out
        got = (await client.get(f"/api/v1/ask/{a['ref']}", headers=h)).json()
        assert got["state"] == "done" and got["citations"][0]["ref"] == rec["ref"]

        # The archivist's item (an owner's import): its prompt in prompt 13's order.
        fid = await upload(client, h, pdf(f"{w} invoice"), "application/pdf", "inv.pdf")
        imp = await client.post(
            "/api/v1/archive/import",
            json={"scope": co["code"], "file_ids": [fid]},
            headers={**h, **idem()},
        )
        assert imp.status_code in (200, 201, 202), imp.text
        arc_run = await su.fetchval(
            """SELECT r.id FROM agents.runs r JOIN core.employees e ON e.id = r.employee_id
               WHERE e.code = 'HQ-ARC' AND r.state = 'queued' ORDER BY r.queued_at DESC LIMIT 1"""
        )
        assert arc_run is not None
        agents.fake.enqueue("HQ-ARC", step("دیدم.", ("activity.set", {"state": "working"})))
        calls = len(agents.fake.calls)
        out = await run(agents, arc_run)
        assert out["state"] in ("done", "failed"), out
    system = next(c.system for c in agents.fake.calls[calls:] if c.actor_ref == "HQ-ARC")
    assert system is not None and system.startswith("# Who you are")
    sealed = "# اساسنامه‌ی هلدینگ"
    charter_at = system.index(sealed) if sealed in system else system.index(CH.FALLBACK_TITLE)
    assert 0 < charter_at < system.index("# Your role")
    assert "# Your department" not in system  # the archivist has none
    assert uuid.UUID(str(arc_run))


def test_the_archive_reads_jalali_dates_with_prompt_11s_calendar() -> None:
    """14's rule-based suggestion used the advisor's Jalali converter, which
    prompt 11 replaced with gov_common's: a Jalali date still becomes its
    Gregorian day."""
    from hq_api.archive import suggest as SG
    from hq_api.worker.jalali import to_jalali

    (got,) = SG.dates("قرارداد از ۱۴۰۵/۰۷/۰۱ شروع میشود")
    assert to_jalali(date.fromisoformat(got)) == (1405, 7, 1)
    assert SG.dates("۱۴۰۵/۱۲/۳۱") == []  # 1405 is not a leap year: no such day
