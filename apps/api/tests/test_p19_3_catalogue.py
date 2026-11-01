"""Prompt 19.3 (contract §28.6): the catalogue job reads with an allow-list
(runner 0.2.1 hands it to Claude Code), the commands still refused are
listed in the section's notes, every answer passes the hub's whole masker,
and the overseer's PR-030 finding on old catalogue outputs closes once they
are made again, masked."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api.domain import catalogue as CAT
from hq_api.domain import servers as SV
from hq_api.errors import ApiError
from hq_api.hub import Hub

from .test_p12a_advisor import _end_test_runs  # noqa: F401 - an autouse fixture here too
from .test_p17_runners import pair, take
from .test_p19_2_catalogue import GOOD, _answer, fenced

pytestmark = pytest.mark.usefixtures("relay")


# ------------------------------------------------------------- §28.6 --
def test_the_job_carries_the_read_allow_list() -> None:
    args = CAT._claude_args("TY", "automations")
    allow = args["allowed_tools"]
    for want in ("Read", "Glob", "Grep", "Bash(crontab -l)", "Bash(systemctl list-timers:*)",
                 "Bash(docker compose ls:*)", "Bash(docker exec:*)", "Bash(find /etc:*)",
                 "Bash(n8n export:workflow --all:*)", "Bash(journalctl --since:*)"):  # fmt: skip
        assert want in allow, want
    assert not any(
        t.startswith(("Bash(rm", "Bash(sudo", "Bash(psql", "Write", "Edit")) for t in allow
    )
    assert SV.allowed_tools_ok(allow)
    assert "اجرا نشد" in args["brief"]
    with pytest.raises(ApiError):
        SV.check_args("claude", {"brief": "x", "allowed_tools": ["Bash(a) ; (b)"]})
    with pytest.raises(ApiError):
        SV.check_args("claude", {"brief": "x", "allowed_tools": "Read"})


def test_the_catalogue_masks_secrets_and_personal_data_but_keeps_a_git_host() -> None:
    answer = {**GOOD, "tables": [{"title_fa": "مخزن‌ها", "columns": ["مسیر", "remote", "نگه‌دار"],
              "rows": [["/srv/app", "git@github.com:CoinePro/app.git", "ali.rezaei@coinepro.com"],
                       ["/srv/bot", "https://user:hunter2pass@git.example.com/b.git", "09121234567"]]}],
              "notes_fa": ["کلید OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwx در فایل env بود."]}  # fmt: skip
    sec, _ = CAT.parse_answer("code", fenced(answer))
    rows = sec["tables"][0]["rows"]
    assert rows[0][1] == "ssh://github.com/CoinePro/app.git"  # the host stays, no address
    assert "ali.rezaei" not in rows[0][2] and "[email]" in rows[0][2]
    assert "hunter2pass" not in rows[1][1] and "09121234567" not in rows[1][2]
    assert "sk-proj-" not in sec["notes_fa"][0]
    body = CAT.markdown("TY", CAT.merged([{**sec, "server": "s", "server_name": "a"}]), None)
    assert CAT.scrub(body) == body  # what the overseer reads finds nothing


async def test_refused_commands_are_listed_and_findings_on_old_outputs_close(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    rn = await pair(client, hub, owner_session, co, "fx-1")
    await client.post(f"/api/v1/companies/{co['code']}/catalogue", headers=h)
    jobs = [await take(client, rn) for _ in CAT.SECTIONS]
    assert all(j["args"]["allowed_tools"] == list(CAT.ALLOWED_TOOLS) for j in jobs)
    first = jobs[0]
    r = await client.post(f"/api/v1/runners/jobs/{first['id']}/events", headers=rn["h"], json={"events": [
        {"seq": 1, "type": "session_event", "data": {"type": "command", "data": {
            "cmd": "sudo cat /etc/shadow", "tool_use_id": "t1"}}},
        {"seq": 2, "type": "session_event", "data": {"type": "progress", "data": {
            "tool_use_id": "t1", "is_error": True,
            "text": "Claude requested permissions to use Bash, but you haven't granted it yet."}}},
        {"seq": 3, "type": "session_event", "data": {"type": "command", "data": {
            "cmd": "crontab -l", "tool_use_id": "t2"}}},
        {"seq": 4, "type": "session_event", "data": {"type": "progress", "data": {
            "tool_use_id": "t2", "is_error": False, "text": "*/5 * * * * sync"}}},
    ]})  # fmt: skip
    assert r.status_code == 200, r.text
    # an answer with a person's address, as the outputs the overseer flagged had
    leaky = {**GOOD, "notes_fa": ["مسئول پشتیبان: ali.rezaei@coinepro.com"]}
    for j in jobs:
        await _answer(client, rn, j, fenced(leaky))
    got = (await client.get(f"/api/v1/companies/{co['code']}/catalogue", headers=h)).json()
    assert got["state"] == "done"
    key = next(k for k, t, _ in CAT.SECTIONS if t in first["args"]["title"])
    notes = next(s for s in got["sections"] if s["key"] == key)["notes_fa"]
    assert any("اجرا نشد: sudo cat /etc/shadow" in n for n in notes)
    assert not any("crontab -l" in n for n in notes)  # it ran
    assert all("ali.rezaei" not in " ".join(s["notes_fa"]) for s in got["sections"])
    # an output of before 19.2 that the overseer flagged (PR-030), and its finding
    old = got["deliverable"]
    async with su.transaction():  # as it was stored before 19.2 (the guards stand aside)
        await su.execute("SET LOCAL session_replication_role = replica")
        await su.execute(
            "UPDATE cartable.deliverables SET body = body || $2 WHERE ref = $1",
            old,
            "\n\nمسئول: ali.rezaei@coinepro.com",
        )
    holding = await su.fetchrow("SELECT id FROM core.companies WHERE kind = 'holding'")
    fref = await su.fetchval(
        """INSERT INTO oversight.findings (company_id, severity, title_fa, body_md, evidence,
               answerable_kind, answerable_code, raised_by_kind, raised_by_code, dedupe_key, due_at)
           VALUES ($1, 'critical', 'الگوی رمز یا داده‌ی حساس در خروجی ایجنت', 'x',
                   $2::jsonb, 'owner', 'owner', 'system', 'PR-030', $3, now() + interval '1 day')
           RETURNING ref""",
        holding["id"],
        json.dumps([{"kind": "link", "ref": old, "note": "pattern"}]),
        f"PR-030:secret:{old}",
    )
    out = await CAT.rerender_all(hub)
    mine = next(x for x in out if x.get("company") == co["code"])
    assert mine["deliverable"] != old  # an unclean output is made again, masked
    assert {"findings_closed": [fref]} in out or any(
        fref in (x.get("findings_closed") or []) for x in out
    )
    f = await su.fetchrow("SELECT status FROM oversight.findings WHERE ref = $1", fref)
    assert f["status"] == "closed"
    body = await su.fetchval(
        "SELECT body FROM cartable.deliverables WHERE ref = $1", mine["deliverable"]
    )
    assert CAT.scrub(body) == body
    # the overseer does not read the superseded output again
    from datetime import UTC, datetime

    from hq_api.domain import oversight_checks as OC

    async with hub.db.tx(await hub.companies.ids()) as tx:
        hold = await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding'")
        cos = {r["code"]: r["id"] for r in await tx.all("SELECT id, code FROM core.companies")}
        ctx = OC.CheckCtx(tx, hold["id"], hold["code"], cos, datetime.now(UTC), {})
        checked = await OC.CHECKS["PR-030"](ctx)
    assert not any(old in p.body_md for p in checked.problems)
