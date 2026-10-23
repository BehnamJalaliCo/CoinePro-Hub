"""Prompt 12 §2 (contract §21.2): «از هاب بپرس» on prompt 11's knowledge.

The corpus (the hub's repository from disk, the workspaces' with the hub's
existing git access; no secret file ever in it), the owner's ask (code finds
the passages; nothing found costs nothing), the librarian's answer (every
citation checked against the retrieved set), the agents' kinds docs, code and
notes (a CTO reads only its own company's code), and the launch gate.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api.domain import ask as AK
from hq_api.domain import corpus
from hq_api.hub import Hub
from hq_api.worker.activities import _ScopedTx
from hq_api.worker.owner_tools_activities import OwnerToolsActivities

from .conftest import agent_headers, idem
from .p10_support import holding_switch
from .test_p12b_cards import Repo, sh

KEY = "AKIA" + "Z" * 16  # an AWS-shaped key, made at run time (never in the source)


def txf(hub: Hub) -> Callable[[], Any]:
    return lambda: _ScopedTx(hub)


def word() -> str:
    return f"xq{random.randint(10**6, 10**7)}"


@pytest.fixture(autouse=True)
async def _end_librarian_runs(su: Any) -> Any:
    yield
    await su.execute(
        """UPDATE agents.runs r SET state = 'done', finished_at = now()
           FROM core.employees e WHERE e.id = r.employee_id AND r.state = 'running'
             AND r.reason = 'test' AND e.code IN ('HQ-LIB', 'HQ-ADV')"""
    )
    # The work these tests gave them queued runs nobody executes here.
    await su.execute(
        """UPDATE agents.runs r SET state = 'refused', finished_at = now(), error_code = 'test_cleanup'
           FROM core.employees e WHERE e.id = r.employee_id AND r.state = 'queued'
             AND e.code IN ('HQ-LIB', 'HQ-ADV')"""
    )


def hub_repo(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    sh(root, "init", "-q", "-b", "main", str(root))
    for path, text in files.items():
        p = root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "hub")
    return root


@pytest.fixture
async def settings_for(hub: Hub, tmp_path: Path) -> Any:
    """The hub's settings pointed at a local hub repository and file:// remotes."""
    real = hub.settings

    def point(repo: Path | None) -> None:
        hub.settings = replace(
            real,
            hub_repo=str(repo) if repo else "",
            git_mirrors=str(tmp_path / "mirrors"),
            git_remote=f"file://{tmp_path / 'remote'}/{{repo}}.git",
        )

    try:
        yield point
    finally:
        hub.settings = real


async def _workspace(su: Any, co: dict[str, Any], tmp_path: Path, text: str) -> str:
    name = f"acme/{co['code'].lower()}"
    r = Repo(tmp_path / "remote", name)
    (r.work / "src").mkdir(exist_ok=True)
    (r.work / "src" / "engine.py").write_text(text)
    sh(r.work, "add", ".")
    sh(r.work, "commit", "-q", "-m", "engine")
    sh(r.work, "push", "-q", "origin", "main")
    await su.execute(
        """INSERT INTO workshop.workspaces (company_id, code, repo, default_branch, title_fa, policy)
           VALUES ($1, $2, $3, 'main', 'ریپوی آزمایشی', '{}')""",
        co["id"],
        f"{co['code']}-APP",
        name,
    )
    return name


async def test_a_dotenv_with_a_key_never_enters_the_corpus(
    hub: Hub, su: Any, tmp_path: Path, settings_for: Any
) -> None:
    w = word()
    repo = hub_repo(
        tmp_path / "hub",
        {
            "docs/ops/RUNBOOK.md": f"# دفترچه\n\nبرای پشتیبان‌گیری {w} اجرا میشود.\n",
            "apps/api/app.py": f"def {w}():\n    return 1\n",
            ".env": f"AWS_ACCESS_KEY_ID={KEY}\n",
            "infra/settings.py": f"AWS = '{KEY}'\n",
            "node_modules/x/index.js": f"var {w} = 1;\n",
            "package-lock.json": "{}\n",
            "logo.png": "not really a png\n",
        },
    )
    settings_for(repo)
    async with holding_switch(su, "released"):
        out = await corpus.build(hub, txf(hub))
    hub_out = next(r for r in out["sources"] if r["source"] == "hub")
    assert hub_out["state"] == "indexed" and hub_out["excluded_secret"] == 2, hub_out
    files = {
        r["path"]: r
        for r in await su.fetch(
            """SELECT f.path, f.state, f.kind, f.chunks FROM knowledge.corpus_files f
               JOIN knowledge.corpus_sources s ON s.id = f.source_id WHERE s.key = 'hub'"""
        )
    }
    assert files[".env"]["state"] == "secret" and files["infra/settings.py"]["state"] == "secret"
    assert (
        files["docs/ops/RUNBOOK.md"]["kind"] == "doc"
        and files["docs/ops/RUNBOOK.md"]["state"] == "indexed"
    )
    assert files["apps/api/app.py"]["kind"] == "code"
    assert not {"node_modules/x/index.js", "package-lock.json", "logo.png"} & set(files)
    assert not await su.fetchval(
        "SELECT count(*) FROM knowledge.corpus_chunks WHERE body LIKE $1", f"%{KEY}%"
    )
    # Incremental: the same commit again reads nothing.
    async with holding_switch(su, "released"):
        again = await corpus.build(hub, txf(hub))
    assert next(r for r in again["sources"] if r["source"] == "hub").get("unchanged") is True


async def test_the_corpus_build_does_nothing_while_the_holding_is_locked(
    hub: Hub, su: Any, tmp_path: Path, settings_for: Any
) -> None:
    repo = hub_repo(tmp_path / "hub", {"docs/a.md": f"# {word()}\n"})
    settings_for(repo)
    before = await su.fetchval("SELECT max(updated_at) FROM knowledge.corpus_sources")
    acts = OwnerToolsActivities(hub, txf(hub))
    async with holding_switch(su, "engaged"):
        out = await acts.corpus_nightly()
        swept = await acts.ask_sweep()
    assert out == {"skipped": True, "reason": "holding_locked"}
    assert swept == {"skipped": True, "reason": "holding_locked"}
    assert await su.fetchval("SELECT max(updated_at) FROM knowledge.corpus_sources") == before


async def test_a_question_answered_by_a_resolution_cites_its_m_ref(
    hub: Hub, su: Any, client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    w = word()
    holding = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
    m = await su.fetchval(
        """INSERT INTO cartable.resolutions (ref, company_id, title, body, sealed_by_kind, sealed_by_code)
           VALUES (cartable.next_resolution_ref(), $1, $2, $3, 'owner', 'owner') RETURNING ref""",
        holding,
        f"بودجه‌ی تبلیغات {w}",
        f"بودجه‌ی تبلیغات {w} برای فصل پاییز ۲۰۰ دلار تصویب شد.",
    )
    q = f"مصوبه‌ی {w} درباره‌ی بودجه چه بود؟"
    async with holding_switch(su, "released"):
        r = await client.post("/api/v1/ask", headers={**owner, **idem()}, json={"q": q})
    assert r.status_code == 202, r.text
    a = r.json()
    assert a["state"] == "answering" and a["found"] >= 1
    row = await su.fetchrow("SELECT passages, work_id FROM knowledge.asks WHERE ref = $1", a["ref"])
    passages = json.loads(row["passages"]) if isinstance(row["passages"], str) else row["passages"]
    assert passages[0]["kind"] == "resolution" and passages[0]["ref"] == m
    meta = await su.fetchval("SELECT run_meta FROM work.work WHERE id = $1", row["work_id"])
    meta = json.loads(meta) if isinstance(meta, str) else meta
    assert meta == {"task_class": "ask_hub", "owner_zone": "direct", "ask": a["ref"]}
    assert (
        await su.fetchval(
            "SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id WHERE w.id = $1",
            row["work_id"],
        )
        == "HQ-LIB"
    )
    # The librarian's answer: the M-… citation stands, an invented one is dropped.
    lib = await agent_headers("HQ-LIB")
    r = await client.post(
        "/internal/v1/ask/answer",
        headers={**lib, **idem()},
        json={
            "ask": a["ref"],
            "answer_md": f"بودجه‌ی تبلیغات پاییز ۲۰۰ دلار است ({m}).",
            "citations": [
                {"kind": "resolution", "ref": m},
                {"kind": "decision", "ref": "D-999999"},
            ],
        },
    )
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["state"] == "done" and done["citations_dropped"] == 1
    assert [c["ref"] for c in done["citations"]] == [m]
    got = (await client.get(f"/api/v1/ask/{a['ref']}", headers=owner)).json()
    assert got["state"] == "done" and got["answer_md"].startswith("بودجه")
    listed = (await client.get("/api/v1/ask", headers=owner)).json()["items"]
    assert any(x["ref"] == a["ref"] for x in listed)


async def test_an_answer_with_only_invented_citations_fails(
    hub: Hub, su: Any, client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    w = word()
    holding = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
    await su.execute(
        """INSERT INTO cartable.resolutions (ref, company_id, title, body, sealed_by_kind, sealed_by_code)
           VALUES (cartable.next_resolution_ref(), $1, $2, 'متن', 'owner', 'owner')""",
        holding,
        f"قرارداد {w}",
    )
    async with holding_switch(su, "released"):
        a = (
            await client.post(
                "/api/v1/ask", headers={**owner, **idem()}, json={"q": f"قرارداد {w}"}
            )
        ).json()
    r = await client.post(
        "/internal/v1/ask/answer",
        headers={**await agent_headers("HQ-LIB"), **idem()},
        json={
            "ask": a["ref"],
            "answer_md": "ساختگی",
            "citations": [{"kind": "resolution", "ref": "M-999999"}],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "failed" and r.json()["answer_md"] == AK.NO_VALID_ANSWER
    assert r.json()["citations"] == [] and r.json()["citations_dropped"] == 1


async def test_a_question_with_no_answer_spends_no_token(
    hub: Hub, su: Any, client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    calls = await su.fetchval("SELECT count(*) FROM llm.calls")
    work = await su.fetchval("SELECT count(*) FROM work.work")
    # Even with the holding locked: nothing found needs no model.
    async with holding_switch(su, "engaged"):
        r = await client.post(
            "/api/v1/ask", headers={**owner, **idem()}, json={"q": f"{word()} {word()} {word()}"}
        )
    assert r.status_code == 202, r.text
    a = r.json()
    assert a["state"] == "done" and a["found"] == 0 and a["usage"]["tokens"] == 0
    assert a["answer_md"].startswith(AK.NOTHING_FOUND)
    assert await su.fetchval("SELECT count(*) FROM llm.calls") == calls
    assert await su.fetchval("SELECT count(*) FROM work.work") == work


async def test_an_ask_that_needs_the_librarian_waits_for_the_launch(
    hub: Hub, su: Any, client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    w = word()
    holding = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
    await su.execute(
        """INSERT INTO cartable.resolutions (ref, company_id, title, body, sealed_by_kind, sealed_by_code)
           VALUES (cartable.next_resolution_ref(), $1, $2, 'متن', 'owner', 'owner')""",
        holding,
        f"سیاست {w}",
    )
    async with holding_switch(su, "engaged"):
        r = await client.post("/api/v1/ask", headers={**owner, **idem()}, json={"q": f"سیاست {w}"})
    assert r.status_code == 423, r.text
    assert not await su.fetchval("SELECT count(*) FROM knowledge.asks WHERE q = $1", f"سیاست {w}")


async def test_messages_are_read_only_in_the_owners_ask(
    hub: Hub, su: Any, client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    w = word()
    r = await client.post(
        "/api/v1/threads/A/messages",
        headers={**owner, **idem()},
        json={"body": f"یادم باشد {w} را بخرم"},
    )
    assert r.status_code == 201, r.text
    async with holding_switch(su, "released"):
        a = (
            await client.post("/api/v1/ask", headers={**owner, **idem()}, json={"q": f"خرید {w}"})
        ).json()
    passages = await su.fetchval(
        "SELECT passages::text FROM knowledge.asks WHERE ref = $1", a["ref"]
    )
    assert a["found"] >= 1 and '"kind": "message"' in passages
    # The librarian's own search never reads messages (the advisor's alone).
    lib = await agent_headers("HQ-LIB")
    r = await client.get(
        "/internal/v1/knowledge/search", headers=lib, params={"q": w, "kinds": ["messages"]}
    )
    assert r.status_code == 403, r.text
    r = await client.get(
        "/internal/v1/knowledge/search", headers=lib, params={"q": w, "kinds": ["docs", "code"]}
    )
    assert r.status_code == 200 and all(h["kind"] in ("doc", "code") for h in r.json())
    # Notes: the advisor only.
    r = await client.get(
        "/internal/v1/knowledge/search", headers=lib, params={"q": w, "kinds": ["notes"]}
    )
    assert r.status_code == 403


async def test_the_fx_cto_never_sees_ty_code(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    tmp_path: Path,
    settings_for: Any,
    new_company: Callable[..., Any],
) -> None:
    fx, ty = await new_company(), await new_company()
    w_fx, w_ty = word(), word()
    await _workspace(su, fx, tmp_path, f"def fx_{w_fx}():\n    return 'fx'\n")
    await _workspace(su, ty, tmp_path, f"def ty_{w_ty}():\n    return 'ty'\n")
    settings_for(None)  # no hub repository: `not_indexed`, the workspaces still are
    async with holding_switch(su, "released"):
        out = await corpus.build(hub, txf(hub))
    states = {r["source"]: r["state"] for r in out["sources"]}
    assert states["hub"] == "not_indexed"
    assert states[f"{fx['code']}-APP"] == "indexed" and states[f"{ty['code']}-APP"] == "indexed"
    cto = await agent_headers(f"{fx['code']}-TECH-MGR")
    own = await client.get(
        "/internal/v1/knowledge/search", headers=cto, params={"q": f"fx_{w_fx}", "kinds": ["code"]}
    )
    assert own.status_code == 200, own.text
    assert own.json() and all(h["company"] == fx["code"] for h in own.json())
    assert own.json()[0]["path"] == "src/engine.py" and own.json()[0]["lines"] == [1, 2]
    other = await client.get(
        "/internal/v1/knowledge/search", headers=cto, params={"q": f"ty_{w_ty}", "kinds": ["code"]}
    )
    assert other.status_code == 200 and other.json() == []
    # Naming the other company is 403, the same as a company that does not exist.
    for code in (ty["code"], "NOPE"):
        r = await client.get(
            "/internal/v1/knowledge/search",
            headers=cto,
            params={"q": f"ty_{w_ty}", "kinds": ["code"], "company": code},
        )
        assert r.status_code == 403, (code, r.text)
    # The advisor (holding scope) reads both; a repository the hub cannot read is listed.
    adv = await agent_headers("HQ-ADV")
    both = await client.get(
        "/internal/v1/knowledge/search", headers=adv, params={"q": f"ty_{w_ty}", "kinds": ["code"]}
    )
    assert both.status_code == 200 and both.json()[0]["company"] == ty["code"]
    await su.execute(
        """INSERT INTO workshop.workspaces (company_id, code, repo, default_branch, title_fa, policy)
           VALUES ($1, $2, $3, 'main', 'بی‌دسترسی', '{}')""",
        fx["id"],
        f"{fx['code']}-WEB",
        f"acme/{fx['code'].lower()}-web",
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert f"acme/{fx['code'].lower()}-web" in await corpus.not_indexed(tx, [fx["id"]])


def test_passages_are_cut_into_sixty_lines_with_their_numbers() -> None:
    text = "\n".join(f"line {i}" for i in range(1, 131)) + "\n"
    parts = corpus.chunks(text)
    assert [(a, b) for a, b, _ in parts] == [(1, 60), (61, 120), (121, 130)]
    assert corpus.excluded("vendor/a.py") == "excluded_dir"
    assert corpus.excluded("web/yarn.lock") == "lockfile"
    assert corpus.excluded("infra/compose/.env") == "secret_name"
    assert corpus.excluded("infra/compose/.env.example") is None
    assert corpus.excluded("id_rsa") == "secret_name"
    assert corpus.excluded("design/logo.png") == "binary"
    assert corpus.classify(b"\0\1\2")[0] == "skipped"
    assert corpus.classify(f"x = '{KEY}'".encode())[0] == "secret"
    assert corpus.need(1) == 1 and corpus.need(4) == 2


def test_citations_are_checked_against_the_retrieved_set() -> None:
    passages = [
        {"kind": "resolution", "ref": "M-0007", "text": "t", "key": "M-0007"},
        {"kind": "code", "repo": "acme/x", "path": "a.py", "lines": [61, 120], "commit": "abcdef1",
         "text": "def f(): ...", "key": "acme/x/a.py:61-120"},
    ]  # fmt: skip
    cited = [
        AK.AnswerCitation(kind="resolution", ref="M-0007"),
        AK.AnswerCitation(kind="code", path="a.py", lines=[70, 75]),
        AK.AnswerCitation(kind="code", path="a.py", lines=[1, 10]),  # outside the passage
        AK.AnswerCitation(kind="decision", ref="D-000001"),  # never retrieved
    ]
    kept, dropped = AK.check_citations(passages, cited)
    assert dropped == 2
    assert kept[1] == {"kind": "code", "snippet": "def f(): ...", "repo": "acme/x", "path": "a.py",
                       "lines": [61, 120], "commit": "abcdef1"}  # fmt: skip
