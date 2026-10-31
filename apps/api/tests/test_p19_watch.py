"""Prompt 19 (contract §28 ⟨1.10⟩): the owner's clean-up of outputs, the
company catalogue, the watch and the council's robustness. Runners, the
substitutes' CLI and web path and the model are fakes; nothing leaves."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from hq_api.domain import catalogue as CAT
from hq_api.domain import players as PL
from hq_api.domain import substitutes as S
from hq_api.domain import watch as WATCH
from hq_api.hub import Hub
from hq_api.routes.deliverables import delete_target

from .conftest import agent_headers, idem, step_up
from .test_p12a_advisor import _end_test_runs  # noqa: F401 - an autouse fixture here too
from .test_p12a_substitutes import FakeEgress, bench, claim, done, per_day, png
from .test_p15_app_feedback import _deliverable
from .test_p17_runners import pair, take

pytestmark = pytest.mark.usefixtures("relay")


# ------------------------------------------------------------ §28.1 outputs --
async def test_the_owner_files_several_and_deletes_for_good_with_a_step_up(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    a = await _deliverable(su, co["id"], system=False)
    b = await _deliverable(su, co["id"], system=False)
    keep = await _deliverable(su, co["id"], system=False)
    # several filed at once, idempotent per ref
    r = await client.post(
        "/api/v1/deliverables/file", headers=h, json={"refs": [b["ref"], a["ref"]]}
    )
    assert r.status_code == 200, r.text
    filed = {x["ref"]: x["record"] for x in r.json()["records"]}
    assert set(filed) == {a["ref"], b["ref"]} and all(v.startswith("AR-") for v in filed.values())
    again = await client.post("/api/v1/deliverables/file", headers=h, json={"refs": [a["ref"]]})
    assert again.json()["records"] == [{"ref": a["ref"], "record": filed[a["ref"]]}]
    missing = await client.post(
        "/api/v1/deliverables/file", headers=h, json={"refs": ["O-999999999"]}
    )
    assert missing.status_code == 404
    # a rating, an attachment only it carries, and an attachment another one shares
    await client.post(f"/api/v1/deliverables/{a['ref']}/rating", headers={**h, **idem()},
                      json={"score": 7})  # fmt: skip
    own = await su.fetchval(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key, created_by_kind,
               created_by_code) VALUES ($1, 'a.txt', 'text/plain', 1, $2, $3, 'agent', 'x') RETURNING id""",
        co["id"], "0" * 64, uuid.uuid4().hex,
    )  # fmt: skip
    shared = await su.fetchval(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key, created_by_kind,
               created_by_code) VALUES ($1, 's.txt', 'text/plain', 1, $2, $3, 'agent', 'x') RETURNING id""",
        co["id"], "1" * 64, uuid.uuid4().hex,
    )  # fmt: skip
    await su.execute("ALTER TABLE cartable.deliverables DISABLE TRIGGER deliverables_immutable")
    try:
        await su.execute("UPDATE cartable.deliverables SET attachments = $2 WHERE id = $1",
                         a["id"], [own, shared])  # fmt: skip
        await su.execute("UPDATE cartable.deliverables SET attachments = $2 WHERE id = $1",
                         keep["id"], [shared])  # fmt: skip
    finally:
        await su.execute("ALTER TABLE cartable.deliverables ENABLE TRIGGER deliverables_immutable")
    refs = [b["ref"], a["ref"]]
    body = {"refs": refs}
    # no step-up, or one for other refs: refused
    r = await client.request("DELETE", "/api/v1/deliverables", headers=h, json=body)
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    wrong = await step_up(hub, owner_session["session_id"], "deliverables.delete",
                          delete_target([a["ref"]]))  # fmt: skip
    r = await client.request("DELETE", "/api/v1/deliverables", headers={**h, **wrong}, json=body)
    assert r.status_code == 403 and r.json()["code"] == "step_up_invalid"
    target = delete_target(refs)
    assert (
        target
        == hashlib.sha256(json.dumps(sorted(refs), separators=(",", ":")).encode()).hexdigest()
    )
    su_tok = await step_up(hub, owner_session["session_id"], "deliverables.delete", target)
    r = await client.request("DELETE", "/api/v1/deliverables", headers={**h, **su_tok}, json=body)
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": 2}
    ids = [a["id"], b["id"]]
    assert (
        await su.fetchval("SELECT count(*) FROM cartable.deliverables WHERE id = ANY($1)", ids) == 0
    )
    assert (
        await su.fetchval(
            "SELECT count(*) FROM cartable.ratings WHERE deliverable_id = ANY($1)", ids
        )
        == 0
    )
    assert await su.fetchval("SELECT count(*) FROM files.files WHERE id = $1", own) == 0
    assert await su.fetchval("SELECT count(*) FROM files.files WHERE id = $1", shared) == 1
    assert (
        await su.fetchval("SELECT count(*) FROM cartable.deliverables WHERE id = $1", keep["id"])
        == 1
    )
    # the archive keeps what was filed; the audit keeps a tombstone
    assert await su.fetchval(
        "SELECT count(*) FROM archive.records WHERE ref = ANY($1)", list(filed.values())
    ) == 2  # fmt: skip
    stone = await su.fetchrow(
        """SELECT summary, step_up, action_class FROM audit.entries
           WHERE action = 'deliverable.delete' AND target_ref = $1""",
        a["ref"],
    )
    gone = json.loads(stone["summary"])
    assert (
        gone["ref"] == a["ref"] and gone["company"] == co["code"] and gone["deleted_by"] == "owner"
    )
    assert stone["step_up"] is True and stone["action_class"] == "A3"
    assert (await client.get(f"/api/v1/deliverables/{a['ref']}", headers=h)).status_code == 404
    # nothing else may delete: the guard still refuses everyone but the function
    with pytest.raises(Exception) as info:
        await su.execute("DELETE FROM cartable.deliverables WHERE id = $1", keep["id"])
    assert getattr(info.value, "sqlstate", None) == "HQA01"


# ---------------------------------------------------------- §28.2 catalogue --
SECTION_ANSWER = {
    "summary_md": "دو کانتینر و یک سایت.",
    "count": 2,
    "tables": [{"title_fa": "کانتینرها", "columns": ["نام", "ایمیج"],
                "rows": [["web", "nginx:1.27"], ["api", "tradeyar/api:3.1"]]}],
    "notes_md": "رمز پایگاه داده OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz0123456789 خوانده نشد.",
}  # fmt: skip


async def _answer(
    client: httpx.AsyncClient, rn: dict[str, Any], job: dict[str, Any], **body: Any
) -> None:
    r = await client.post(f"/api/v1/runners/jobs/{job['id']}/result", headers=rn["h"], json=body)
    assert r.status_code == 200, r.text


async def test_a_catalogue_runs_on_every_server_and_is_filed_with_its_diff(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    assert (
        await client.get(f"/api/v1/companies/{co['code']}/catalogue", headers=h)
    ).status_code == 404
    rn = await pair(client, hub, owner_session, co, "app-1")
    r = await client.post(f"/api/v1/companies/{co['code']}/catalogue", headers=h)
    assert r.status_code == 202, r.text
    cat = r.json()
    assert cat["state"] == "running" and [s["name"] for s in cat["servers"]] == ["app-1"]
    again = await client.post(f"/api/v1/companies/{co['code']}/catalogue", headers=h)
    assert again.json()["at"] == cat["at"]  # a run still going is answered as it is
    jobs = [await take(client, rn) for _ in CAT.SECTIONS]
    assert {j["kind"] for j in jobs} == {"claude"}
    assert all(
        "READ ONLY" in j["args"]["brief"] and "never change" in j["args"]["brief"] for j in jobs
    )
    for j in jobs[:-1]:
        await _answer(client, rn, j, exit_code=0, summary_fa="ok",
                      data={"result_fa": "```json\n" + json.dumps(SECTION_ANSWER, ensure_ascii=False) + "\n```"})  # fmt: skip
    # Claude Code is missing for the last one: the runner's map stands in
    await _answer(client, rn, jobs[-1], exit_code=127, error="claude_missing")
    m = await take(client, rn)
    assert m["kind"] == "map"
    await _answer(client, rn, m, exit_code=0, data={"map": {
        "containers": [{"name": "web", "image": "nginx:1.27", "state": "running", "ports": "443"}],
        "cron": [{"user": "app", "schedule": "*/5 * * * *", "command": "python sync.py"}],
    }})  # fmt: skip
    got = (await client.get(f"/api/v1/companies/{co['code']}/catalogue", headers=h)).json()
    assert got["state"] == "done", got
    assert got["record"] and got["record"].startswith("AR-") and got["deliverable"].startswith("O-")
    keys = [s["key"] for s in got["sections"]]
    assert keys == [k for k, _, _ in CAT.SECTIONS if k in keys] and "risks" in keys
    products = next(s for s in got["sections"] if s["key"] == "products")
    assert ["web", "nginx:1.27"] in products["tables"][0]["rows"]
    assert all("sk-abcdef" not in (s.get("notes_md") or "") for s in got["sections"])
    dl = await su.fetchrow(
        """SELECT d.body, d.category, c.kind FROM cartable.deliverables d
           JOIN core.companies c ON c.id = d.company_id WHERE d.ref = $1""",
        got["deliverable"],
    )
    assert (
        dl["category"] == "report"
        and dl["kind"] == "holding"
        and "| web | nginx:1.27 |" in dl["body"]
    )
    # the next run: what changed is named (and goes to the CEO when the watch ran it)
    r = await client.post(f"/api/v1/companies/{co['code']}/catalogue", headers=h)
    assert r.json()["state"] == "running" and r.json()["at"] != cat["at"]
    changed = {**SECTION_ANSWER, "tables": [{"title_fa": "کانتینرها", "columns": ["نام", "ایمیج"],
                                             "rows": [["web", "nginx:1.27"], ["bot", "tradeyar/bot:1"]]}]}  # fmt: skip
    for _ in CAT.SECTIONS:
        j = await take(client, rn)
        await _answer(client, rn, j, exit_code=0,
                      data={"result_fa": json.dumps(changed, ensure_ascii=False)})  # fmt: skip
    got = (await client.get(f"/api/v1/companies/{co['code']}/catalogue", headers=h)).json()
    assert got["state"] == "done" and got["diff"]["products"]["added"] == ["bot"]
    assert got["diff"]["products"]["removed"] == ["api"]


async def test_a_company_without_a_server_and_who_may_start_one(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    r = await client.post(
        f"/api/v1/companies/{co['code']}/catalogue", headers=owner_session["headers"]
    )
    assert r.status_code == 202 and r.json()["state"] == "failed" and r.json()["reason_fa"]
    # the CEO starts its own company's (company.catalogue); a manager may not
    await pair(client, hub, owner_session, co, "db-1")
    ceo = await agent_headers(f"{co['code']}-CEO")
    r = await client.post("/internal/v1/catalogue", headers={**ceo, **idem()}, json={"start": True})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "running" and r.json()["company"] == co["code"]
    mgr = await agent_headers(f"{co['code']}-TECH-MGR")
    r = await client.post("/internal/v1/catalogue", headers={**mgr, **idem()}, json={"start": True})
    assert r.status_code == 403
    other = await new_company()
    r = await client.post("/internal/v1/catalogue", headers={**ceo, **idem()},
                          json={"company": other["code"], "start": True})  # fmt: skip
    assert r.status_code == 403
    ovr = await agent_headers("HQ-OVR")
    r = await client.post(
        "/internal/v1/catalogue", headers={**ovr, **idem()}, json={"company": co["code"]}
    )
    assert r.status_code == 200 and r.json()["state"] == "running"  # the running one, not a second
    await su.execute(
        "UPDATE infra.server_jobs SET state = 'cancelled' WHERE company_id = $1 AND state = 'queued'",
        co["id"],
    )


# ----------------------------------------------------- §28.3 the apps' errors --
async def test_the_apps_report_their_errors_masked_once_and_the_overseer_reads_them(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str]
) -> None:
    version = f"4.{uuid.uuid4().hex[:6]}"
    at = datetime.now(UTC).isoformat()
    entries = [
        {"id": 1, "at": at, "kind": "http", "level": "error", "app": version, "screen": "deliverables",
         "method": "GET", "path": "/api/v1/deliverables", "status": 500, "code": "internal_error",
         "message": "token=ghp_abcdefghijklmnopqrstuvwxyz0123456789 failed", "requestId": "abc-123"},
        {"id": 2, "at": at, "kind": "crash", "level": "error", "app": version, "message": "NPE"},
    ]  # fmt: skip
    r = await client.post("/api/v1/client/errors", headers=owner,
                          json={"app": "android", "version": version, "entries": entries})  # fmt: skip
    assert r.status_code == 200 and r.json() == {"accepted": 2}, r.text
    r = await client.post("/api/v1/client/errors", headers=owner,
                          json={"app": "android", "version": version, "entries": entries[:1]})  # fmt: skip
    assert r.json() == {"accepted": 0}  # the same entry is kept once
    got = (await client.get("/api/v1/client/errors", headers=owner,
                            params={"app": "android", "version": version})).json()  # fmt: skip
    assert len(got["items"]) == 2
    http = next(x for x in got["items"] if x["kind"] == "http")
    assert "ghp_abcdef" not in http["message"] and "ghp_abcdef" not in json.dumps(http["entry"])
    assert http["entry"]["requestId"] == "abc-123" and http["status"] == 500
    ovr = await agent_headers("HQ-OVR")
    r = await client.get("/internal/v1/client/errors", headers=ovr, params={"version": version})
    assert r.status_code == 200 and len(r.json()["items"]) == 2
    adv = await agent_headers("HQ-ADV")
    assert (await client.get("/internal/v1/client/errors", headers=adv)).status_code == 403
    bad = await client.post("/api/v1/client/errors", headers=owner,
                            json={"app": "ios", "version": "1", "entries": entries})  # fmt: skip
    assert bad.status_code == 422


async def test_a_watch_finding_carries_its_kind_and_the_proposed_fix(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    ovr = await agent_headers("HQ-OVR")
    r = await client.post(
        "/internal/v1/oversight/findings",
        headers={**ovr, **idem()},
        json={"company": co["code"], "protocol": "PR-140", "severity": "high",
              "title_fa": "پورت ۵۴۳۲ از اینترنت باز است", "body_md": "ss -tlnp: 0.0.0.0:5432",
              "kind": "security", "fix_md": "بستن پورت در فایروال هتزنر",
              "fix": {"kind": "work", "summary_fa": "بستن پورت ۵۴۳۲"}},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    f = (await client.get(f"/api/v1/oversight/findings/{r.json()['ref']}", headers=owner)).json()
    assert f["kind"] == "security" and f["fix_md"].startswith("بستن")
    assert f["fix"] == {"kind": "work", "ref": None, "summary_fa": "بستن پورت ۵۴۳۲"}


# ------------------------------------------------------ §28.2-§28.3 the watch --
class FakeRouter:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, Any]] = []

    async def run(self, req: dict[str, Any], timeout_s: float) -> Any:
        self.calls.append(req)
        text = self.text

        class Call:
            ok = True
            model = "claude-sonnet-5-5"
            input_tokens = 10
            output_tokens = 10
            status = "ok"

        c = Call()
        c.text = text  # type: ignore[attr-defined]
        return c


async def test_the_watch_runs_each_duty_once_per_period(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    await pair(client, hub, owner_session, co, "ops-1")
    month = datetime.now(UTC).strftime("%Y-%m")
    router = FakeRouter(json.dumps({"title_fa": "پیشنهاد هلدینگ", "body_md": "۱. فروش متقابل",
                                    "fix_md": "شروع با یک کمپین مشترک"}, ensure_ascii=False))  # fmt: skip
    now = datetime.now(UTC)
    first = await WATCH.sweep(hub, router, now)
    second = await WATCH.sweep(hub, router, now)
    tz = await su.fetchval("SELECT timezone FROM owner.settings WHERE id = 1")
    week = WATCH.owner_week(now, tz)
    keys = {r["key"] for r in await su.fetch(
        "SELECT key FROM ops.watch_runs WHERE key LIKE $1", f"%:{co['code']}:%")}  # fmt: skip
    assert keys == {f"catalogue:{co['code']}:{week}", f"growth_memo:{co['code']}:{week}"}
    assert second["catalogues"] == 0 and second["growth_memos"] == 0 and second["proposal"] is None
    cat = await su.fetchrow(
        "SELECT state, started_by_code FROM infra.catalogues WHERE company_id = $1", co["id"]
    )
    assert cat["state"] == "running" and cat["started_by_code"] == "watch"
    memo = await su.fetchrow(
        """SELECT w.brief, e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE w.title = $1""",
        f"یادداشت رشد هفته‌ی {co['code']}",
    )
    assert memo["code"] == "HQ-ADV" and "THREE highest-value moves" in memo["brief"]
    if first["proposal"] is not None and first["proposal"].get("proposed"):
        f = await su.fetchrow(
            "SELECT kind, raised_by_code, fix_md FROM oversight.findings WHERE dedupe_key = $1",
            f"holding_proposal:{month}",
        )
        assert f["kind"] == "holding" and f["raised_by_code"] == "dceo" and f["fix_md"]
        assert router.calls[0]["meta"]["purpose"] == "dceo_proposal"
    await su.execute(
        "UPDATE infra.server_jobs SET state = 'cancelled' WHERE company_id = $1 AND state = 'queued'",
        co["id"],
    )
    await su.execute(
        """UPDATE agents.runs r SET state = 'refused', finished_at = now(), error_code = 'test_cleanup'
           FROM work.work w WHERE w.id = r.work_id AND r.state = 'queued' AND w.title LIKE 'یادداشت رشد%'"""
    )


# --------------------------------------------------- §28.4 council robustness --
REFUSAL = json.dumps({"type": "error", "status": 400, "error": {"type": "invalid_request_error",
    "message": "The 'gpt-5.3' model is not supported when using Codex with a ChatGPT account."}})  # fmt: skip


async def _council(
    client: httpx.AsyncClient, owner: dict[str, str], co: str, **extra: Any
) -> dict[str, Any]:
    r = await client.post("/api/v1/work", headers={**owner, **idem()},
                          json={"company": co, "title": "تحلیل شورا", "brief": "بازار را بررسی کن.",
                                "mode": "council", **extra})  # fmt: skip
    assert r.status_code == 201, r.text
    return dict(r.json())


async def _members(client: httpx.AsyncClient, owner: dict[str, str], wid: str) -> dict[str, Any]:
    r = await client.get(f"/api/v1/work/{wid}/council", headers=owner)
    assert r.status_code == 200, r.text
    return {"_": r.json(), **{m["player"]: m for m in r.json()["members"]}}


async def test_a_refused_model_is_retried_once_with_another_and_the_reason_is_persian(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    async with bench(su, hub, cli=("gpt",)):
        await per_day(su, "gpt", "assistant_errand", 5)
        w = await _council(client, owner, co)
        job = (await claim(client))["job"]
        assert job["model"] == "gpt-5.3"
        r = await done(client, job["id"], ok=False, error="failed", status_reason=REFUSAL)
        assert r.status_code == 200 and r.json()["state"] == "queued", r.text
        call = await su.fetchrow("SELECT * FROM substitutes.calls WHERE id = $1::uuid", job["id"])
        assert call["attempt"] == 2 and call["model"] != "gpt-5.3" and call["input_md"]
        models = {m["id"]: m["available"] for m in json.loads(
            await su.fetchval("SELECT models FROM substitutes.players WHERE player = 'gpt'"))}  # fmt: skip
        assert models["gpt-5.3"] is False
        assert await su.fetchval(
            "SELECT count(*) FROM substitutes.calls WHERE player = 'gpt' AND kind = 'models' AND state = 'queued'"
        ) >= 1  # fmt: skip
        m = await _members(client, owner, w["id"])
        assert m["gpt"]["state"] == "queued" and m["gpt"]["reason_code"] == "model_refused"
        assert "پشتیبانی نمیشود" in m["gpt"]["reason"] and "{" not in m["gpt"]["reason"]
        nxt = (await claim(client))["job"]
        if nxt["kind"] == "models":  # the model check may come first
            await done(client, nxt["id"], ok=True, models=["gpt-5.5"])
            nxt = (await claim(client))["job"]
        assert nxt["id"] == job["id"] and nxt["model"] != "gpt-5.3"
        # refused again: no third try; the member fails in plain Persian
        r = await done(client, job["id"], ok=False, error="failed", status_reason=REFUSAL)
        assert r.json()["state"] == "failed"
        m = await _members(client, owner, w["id"])
        assert m["gpt"]["state"] == "failed" and "{" not in m["gpt"]["reason"]
        raw = await su.fetchval(
            "SELECT state_reason FROM substitutes.calls WHERE id = $1::uuid", job["id"]
        )
        assert raw.startswith("model_refused")


class RecipeEgress(FakeEgress):
    """The web path failing at the same step each time; the second answer
    carries the page's screenshot."""

    def __init__(self) -> None:
        super().__init__(
            {"ok": False, "error": "recipe_failed", "detail": "no prompt box", "step": "2:fill"},
            {"ok": False, "error": "recipe_failed", "detail": "no prompt box", "step": "2:fill",
             "screenshot": {"mime": "image/png", "b64": png(64, 64)}},
        )  # fmt: skip


async def test_a_broken_recipe_is_tried_once_more_then_fails_with_a_screenshot_and_is_skipped(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    async with bench(su, hub, web=("deepseek",)):
        await per_day(su, "deepseek", "third_opinion", 5)
        w = await _council(client, owner, co)
        fake = RecipeEgress()
        await S.web_jobs(hub, fake)
        call = await su.fetchrow(
            "SELECT * FROM substitutes.calls WHERE purpose_kind = 'council' AND purpose_ref = $1",
            w["ref"],
        )
        assert call["state"] == "queued" and call["attempt"] == 2 and call["input_md"]
        m = await _members(client, owner, w["id"])
        assert m["deepseek"]["reason_code"] == "recipe_retry"
        await su.execute("UPDATE substitutes.players SET web_last_job_at = NULL")
        await S.web_jobs(hub, fake)
        assert fake.calls[1].get("reload") is True and "reload" not in fake.calls[0]
        call = await su.fetchrow("SELECT * FROM substitutes.calls WHERE id = $1", call["id"])
        assert call["state"] == "failed" and call["state_reason"] == "recipe_failed: 2:fill"
        shot = json.loads(call["result"])["screenshot_file"]
        f = await su.fetchrow("SELECT mime, company_id FROM files.files WHERE id = $1::uuid", shot)
        assert f["mime"] == "image/png"
        m = await _members(client, owner, w["id"])
        assert (
            m["deepseek"]["state"] == "failed" and m["deepseek"]["reason_code"] == "recipe_failed"
        )
        assert "تصویر صفحه" in m["deepseek"]["reason"]
        subs = {
            p["player"]: p for p in (await client.get("/api/v1/substitutes", headers=owner)).json()
        }
        assert (
            subs["deepseek"]["web"]["state"] == "error" and subs["deepseek"]["web"]["error_until"]
        )
        # the next council skips it with that reason up front
        w2 = await _council(client, owner, co, title="شورای دوم")
        m2 = await _members(client, owner, w2["id"])
        assert m2["deepseek"]["state"] == "skipped" and m2["deepseek"]["reason_code"] == "error"
        await su.execute("UPDATE substitutes.players SET web_error_until = NULL")


async def test_one_answer_is_said_plainly_and_the_synthesis_does_not_wait(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    async with bench(su, hub, cli=("gpt",)):
        await per_day(su, "gpt", "assistant_errand", 5)
        w = await _council(client, owner, co)
        job = (await claim(client))["job"]
        await done(
            client, job["id"], ok=False, error="timeout", status_reason="the CLI ran past its time"
        )
    ceo = await agent_headers(f"{co}-CEO")
    r = await client.post(
        f"/internal/v1/work/{w['id']}/deliver",
        headers={**ceo, **idem()},
        json={"title": "نظر Claude", "summary": "s", "body": "پاسخ Claude"},
    )
    assert r.status_code == 200, r.text
    m = await _members(client, owner, w["id"])
    c = m["_"]
    assert c["state"] == "done" and c["synthesis_ref"] == r.json()["deliverable"]
    assert c["note_fa"] and "فقط Claude" in c["note_fa"]
    assert m["gpt"]["reason_code"] == "timeout" and m["gpt"]["reason"] == PL.REASON_FA["timeout"]
    assert await su.fetchval(
        "SELECT synthesis_work_id FROM work.councils WHERE work_id = $1", uuid.UUID(w["id"])
    ) is None  # fmt: skip


def test_reasons_are_persian_and_never_the_providers_json() -> None:
    assert PL.reason_of(None) == (None, None)
    code, fa = PL.reason_of(f"provider: {REFUSAL}")
    assert code == "model_refused" and "{" not in (fa or "")
    assert PL.reason_of("per_day")[0] == "per_day"
    assert PL.reason_of("policy_denied: customer data")[0] == "policy_denied"
    assert (
        PL.reason_of("recipe_failed: 2:fill; retrying with the page reloaded")[0] == "recipe_retry"
    )
    assert PL.reason_of("something odd")[0] == "failed"
    assert S.provider_text(REFUSAL) == (
        "provider: The 'gpt-5.3' model is not supported when using Codex with a ChatGPT account."
    )
    assert S.refused_model(REFUSAL) and not S.refused_model("the quota is used up")
    assert base64.b64decode(png(8, 8))[:4] == b"\x89PNG"
