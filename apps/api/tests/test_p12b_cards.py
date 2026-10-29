"""Prompt 12 §7, §11 (contract §21.6, §21.8, §21.12): the deploy card's real
diff on a local bare repository, its binding to head_sha; quick notes and
their promotion; cartable reminders; the owner's new settings blocks."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api import workflows_client
from hq_api.domain import deploy_diff as DD
from hq_api.domain import notes as N
from hq_api.hub import Hub
from hq_api.worker.activities import _ScopedTx
from hq_api.worker.mgmt_activities import MgmtActivities

from .conftest import agent_headers, idem, step_up
from .p10_support import holding_switch
from .test_files_media import audio


@pytest.fixture(autouse=True)
def _speech_on(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    """⟨1.7.3⟩ /transcribe answers 503 at once while speech is off: these tests
    exercise the recogniser's path (the worker is faked), so speech is on."""
    if not hub.settings.stt_url:
        monkeypatch.setattr(hub, "settings", replace(hub.settings, stt_url="http://stt.test"))


KEY = "AKIA" + "Q" * 16  # an AWS-shaped key, made at run time (never in the source)


def sh(cwd: Path, *args: str) -> str:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(cwd), "PATH": "/usr/bin:/bin"}  # fmt: skip
    return subprocess.run(
        ["/usr/bin/git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True
    ).stdout.strip()


class Repo:
    """A bare repository `owner/name` served as file://, with a PR ref."""

    def __init__(self, root: Path, name: str) -> None:
        self.bare = root / f"{name}.git"
        self.bare.parent.mkdir(parents=True, exist_ok=True)
        sh(root, "init", "--bare", "-q", "-b", "main", str(self.bare))
        self.work = root / f"{name}-work"
        sh(root, "clone", "-q", str(self.bare), str(self.work))
        sh(self.work, "checkout", "-q", "-b", "main")
        (self.work / "app.py").write_text("print('one')\n")
        (self.work / "README.md").write_text("# app\n")
        sh(self.work, "add", ".")
        sh(self.work, "commit", "-q", "-m", "base")
        sh(self.work, "push", "-q", "origin", "main")

    def change(self, pr: int, text: str) -> str:
        sh(self.work, "checkout", "-q", "-B", f"pr-{pr}", "main")
        (self.work / "app.py").write_text(text)
        (self.work / "logo.bin").write_bytes(bytes(range(256)) * 4)
        sh(self.work, "add", ".")
        sh(self.work, "commit", "-q", "-m", f"change {pr}")
        sh(self.work, "push", "-q", "-f", "origin", f"HEAD:refs/pull/{pr}/head")
        return sh(self.work, "rev-parse", "HEAD")


@pytest.fixture
async def repo(hub: Hub, su: Any, tmp_path: Path, new_company: Callable[..., Any]) -> Any:
    co = await new_company()
    name = f"acme/{co['code'].lower()}"
    r = Repo(tmp_path / "remote", name)
    await su.execute(
        """INSERT INTO workshop.workspaces (company_id, code, repo, default_branch, title_fa, policy)
           VALUES ($1, $2, $3, 'main', 'ریپوی آزمایشی', '{}')""",
        co["id"],
        f"{co['code']}-APP",
        name,
    )
    real = hub.settings
    hub.settings = replace(
        real,
        git_mirrors=str(tmp_path / "mirrors"),
        git_remote=f"file://{tmp_path / 'remote'}/{{repo}}.git",
    )
    try:
        yield {"co": co, "repo": r, "name": name}
    finally:
        hub.settings = real


def card(name: str, pr: int, head: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "repo": name,
        "pr_url": f"https://github.com/{name}/pull/{pr}",
        "diff_stat": "1 file",
    }
    if head is not None:
        payload["head_sha"] = head
    return {"kind": "deploy", "title": "deploy app", "risk": "medium", "payload": payload}


async def test_the_card_carries_the_real_diff_with_the_key_masked(
    hub: Hub, su: Any, client: httpx.AsyncClient, owner: dict[str, str], repo: Any
) -> None:
    co, name = repo["co"], repo["name"]
    head = repo["repo"].change(7, f"print('two')\nAWS = '{KEY}'\n")
    tech = await agent_headers(f"{co['code']}-TECH-MGR")
    r = await client.post(
        "/internal/v1/decisions", headers={**tech, **idem()}, json=card(name, 7, head)
    )
    assert r.status_code == 201, r.text
    p = r.json()["payload"]
    assert p["head_sha"] == head and "diff_unavailable" not in p
    diff = p["diff"]
    assert diff["head_sha"] == head and diff["total_files"] == 2 and not diff["truncated"]
    files = {f["path"]: f for f in diff["files"]}
    app = files["app.py"]
    assert app["status"] == "modified" and app["additions"] == 2 and app["deletions"] == 1
    assert (
        app["secret_masked"] is True and KEY not in app["patch"] and "print('two')" in app["patch"]
    )
    assert files["logo.bin"]["binary"] is True and files["logo.bin"]["patch"] is None
    assert files["logo.bin"]["status"] == "added"
    one = await client.get(f"/api/v1/decisions/{r.json()['ref']}/diff?file=app.py", headers=owner)
    assert (
        one.status_code == 200
        and one.json()["truncated"] is False
        and KEY not in one.json()["patch"]
    )
    missing = await client.get(
        f"/api/v1/decisions/{r.json()['ref']}/diff?file=nope.py", headers=owner
    )
    assert missing.status_code == 404


async def test_head_sha_is_required_and_must_be_in_the_repository(
    client: httpx.AsyncClient, repo: Any
) -> None:
    co, name = repo["co"], repo["name"]
    head = repo["repo"].change(8, "print('x')\n")
    tech = await agent_headers(f"{co['code']}-TECH-MGR")
    r = await client.post(
        "/internal/v1/decisions", headers={**tech, **idem()}, json=card(name, 8, None)
    )
    assert r.status_code == 422 and "head_sha" in r.text
    r = await client.post(
        "/internal/v1/decisions", headers={**tech, **idem()}, json=card(name, 8, "ab" * 20)
    )
    assert r.status_code == 422 and "not in the repository" in r.text
    forged = card(name, 8, head)
    forged["payload"]["diff"] = {"files": [], "total_files": 0}
    forged["payload"]["diff_unavailable"] = "too_large"
    r = await client.post("/internal/v1/decisions", headers={**tech, **idem()}, json=forged)
    assert r.status_code == 201, r.text  # the proposer never writes the diff: the api's replaces it
    assert (
        r.json()["payload"]["diff"]["total_files"] == 2
        and "diff_unavailable" not in r.json()["payload"]
    )


async def test_a_repository_the_hub_cannot_read_is_no_access_and_stays_bound(
    client: httpx.AsyncClient, repo: Any
) -> None:
    co = repo["co"]
    tech = await agent_headers(f"{co['code']}-TECH-MGR")
    r = await client.post(
        "/internal/v1/decisions",
        headers={**tech, **idem()},
        json=card("nobody/elsewhere", 3, "cd" * 20),
    )
    assert r.status_code == 201, r.text
    p = r.json()["payload"]
    assert p["diff_unavailable"] == "no_access" and "diff" not in p and p["head_sha"] == "cd" * 20


async def test_a_new_push_sets_the_card_aside(
    hub: Hub, su: Any, client: httpx.AsyncClient, owner_session: dict[str, Any], repo: Any
) -> None:
    co, name = repo["co"], repo["name"]
    tech = await agent_headers(f"{co['code']}-TECH-MGR")
    head = repo["repo"].change(9, "print('nine')\n")
    first = await client.post(
        "/internal/v1/decisions", headers={**tech, **idem()}, json=card(name, 9, head)
    )
    head2 = repo["repo"].change(10, "print('ten')\n")
    second = await client.post(
        "/internal/v1/decisions", headers={**tech, **idem()}, json=card(name, 10, head2)
    )
    assert first.status_code == second.status_code == 201
    acts = MgmtActivities(hub, lambda: _ScopedTx(hub))
    async with holding_switch(su, "engaged"):
        assert (await acts.deploy_recheck())["skipped"] is True  # no git call while locked
    async with holding_switch(su, "released"):
        quiet = await acts.deploy_recheck()
        assert first.json()["ref"] not in quiet["set_aside"]
        repo["repo"].change(9, "print('nine, again')\n")
        out = await acts.deploy_recheck()
    assert first.json()["ref"] in out["set_aside"] and second.json()["ref"] not in out["set_aside"]
    row = await su.fetchrow(
        "SELECT status, note FROM cartable.decisions WHERE ref = $1", first.json()["ref"]
    )
    assert row["status"] == "withdrawn" and "new push" in row["note"]
    told = await su.fetchval(
        "SELECT count(*) FROM work.work w JOIN core.employees e ON e.id = w.assignee_id"
        " WHERE e.code = $1 AND w.title LIKE $2",
        f"{co['code']}-TECH-MGR",
        f"%{first.json()['ref']}%",
    )
    assert told == 1
    # once more before the seal: a push between the check and the approval
    repo["repo"].change(10, "print('ten, again')\n")
    h = owner_session["headers"]
    ref = second.json()["ref"]
    su_h = await step_up(hub, owner_session["session_id"], "decision.approve", ref)
    r = await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**h, **idem(), **su_h}, json={}
    )
    assert r.status_code == 409 and r.json()["code"] == "decision_not_pending"


def test_patch_bounds_and_masks() -> None:
    lines, masked = DD.mask(["+ok", f"+key {KEY}", " ctx"])
    assert masked and KEY not in lines[1] and lines[0] == "+ok"
    assert (
        DD.pr_number("https://github.com/a/b/pull/12") == 12 and DD.pr_number("https://x/y") is None
    )
    assert DD.moved({"head_sha": "abc1234"}, "abc1234ffff") is False
    assert (
        DD.moved({"head_sha": "abc1234"}, "fff") is True
        and DD.moved({"head_sha": "abc"}, None) is False
    )
    stats = DD._numstat("1\t2\ta.py\0-\t-\tb.bin\0" + "3\t0\t\0old.py\0new.py\0")
    assert [s["path"] for s in stats] == ["a.py", "b.bin", "new.py"] and stats[1]["binary"]
    assert DD._statuses("M\0a.py\0A\0b.bin\0R100\0old.py\0new.py\0") == {
        "a.py": "modified", "b.bin": "added", "new.py": "renamed",
    }  # fmt: skip


# ------------------------------------------------------------------ notes --
async def test_notes_are_made_edited_archived_and_promoted(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    assert (
        await client.post("/api/v1/notes", headers=owner, json={"text_md": "x"})
    ).status_code == 422
    r = await client.post(
        "/api/v1/notes", headers={**owner, **idem()},
        json={"text_md": "پیگیری قیمت سرور تازه", "tags": ["سرور", "سرور", " هزینه "]},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    assert r.json()["tags"] == ["سرور", "هزینه"] and r.json()["ref"].startswith("NT-")
    n = r.json()
    nomatch = await client.patch(f"/api/v1/notes/{n['ref']}", headers=owner, json={"text_md": "y"})
    assert nomatch.status_code == 428
    edited = await client.patch(
        f"/api/v1/notes/{n['ref']}",
        headers={**owner, "If-Match": str(n["version"])},
        json={"text_md": "پیگیری قیمت"},
    )
    assert edited.status_code == 200 and edited.json()["version"] == n["version"] + 1
    found = await client.get("/api/v1/notes?q=پیگیری&status=open", headers=owner)
    assert any(x["ref"] == n["ref"] for x in found.json()["items"])
    nocompany = await client.post(
        f"/api/v1/notes/{n['ref']}/promote", headers=owner, json={"to": "work"}
    )
    assert nocompany.status_code == 422
    promoted = await client.post(
        f"/api/v1/notes/{n['ref']}/promote",
        headers=owner,
        json={"to": "work", "company": co["code"]},
    )
    assert promoted.status_code == 200, promoted.text
    link = promoted.json()["promoted_to"]
    assert (
        promoted.json()["status"] == "promoted"
        and link["kind"] == "work"
        and link["ref"].startswith("W-")
    )
    brief = await su.fetchval("SELECT brief FROM work.work WHERE ref = $1", link["ref"])
    assert brief == "پیگیری قیمت"
    again = await client.post(
        f"/api/v1/notes/{n['ref']}/promote", headers=owner, json={"to": "errand"}
    )
    assert again.status_code == 409
    other = (
        await client.post(
            "/api/v1/notes", headers={**owner, **idem()}, json={"text_md": "خرید هدیه"}
        )
    ).json()
    errand = await client.post(
        f"/api/v1/notes/{other['ref']}/promote", headers=owner, json={"to": "errand"}
    )
    assert errand.status_code == 200 and errand.json()["promoted_to"]["kind"] == "errand"
    third = (
        await client.post("/api/v1/notes", headers={**owner, **idem()}, json={"text_md": "بایگانی"})
    ).json()
    archived = await client.patch(
        f"/api/v1/notes/{third['ref']}",
        headers={**owner, "If-Match": "1"},
        json={"status": "archived"},
    )
    assert archived.status_code == 200 and archived.json()["status"] == "archived"


async def test_a_voice_with_save_becomes_a_note(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake(hub: Any, file_id: str, timeout_s: int) -> dict[str, Any]:
        return {"text": "یادم باشد قرارداد را بخوانم", "duration_s": 2.0, "confidence": 0.9, "segments": [],
                "engine": {"name": "faster-whisper", "model": "fake", "version": "0"}}  # fmt: skip

    monkeypatch.setattr(workflows_client, "transcribe", fake)
    r = await client.post(
        "/api/v1/transcribe?purpose=note&save=true",
        content=audio(tmp_path, "wav", 2),
        headers={**owner, **idem(), "Content-Type": "audio/wav"},
    )
    assert r.status_code == 200, r.text
    ref = r.json()["note_ref"]
    notes = (await client.get("/api/v1/notes?status=open", headers=owner)).json()["items"]
    note = next(x for x in notes if x["ref"] == ref)
    assert note["source"] == "voice" and note["file_id"] == r.json()["file_id"]
    plain = await client.post(
        "/api/v1/transcribe?purpose=note",
        content=audio(tmp_path, "wav", 2),
        headers={**owner, **idem(), "Content-Type": "audio/wav"},
    )
    assert plain.status_code == 200 and plain.json()["note_ref"] is None


# -------------------------------------------------------------- reminders --
def test_reminder_thresholds() -> None:
    t0 = datetime(2031, 1, 1, tzinfo=UTC)
    cfg = N.DEFAULT
    assert N.due_kinds(t0, t0 + timedelta(hours=10), t0 + timedelta(hours=3), cfg) == []
    assert N.due_kinds(t0, t0 + timedelta(hours=10), t0 + timedelta(hours=5), cfg) == [
        "half",
        "before_expiry",
    ]
    assert N.due_kinds(t0, t0 + timedelta(days=4), t0 + timedelta(days=2), cfg) == ["half"]
    assert N.due_kinds(t0, None, t0 + timedelta(hours=23), cfg) == []
    assert N.due_kinds(t0, None, t0 + timedelta(hours=80), cfg) == ["age_24h", "age_72h"]
    assert N.due_kinds(t0, None, t0 + timedelta(days=8), cfg)[-1] == "age_7d"


async def _card(su: Any, company_id: Any, **kw: Any) -> dict[str, Any]:
    return dict(
        await su.fetchrow(
            """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind, proposer_code,
                   created_at, expires_at, approver_kind, approver_code)
               VALUES ($1, 'proposal', 'A1', 'یک پیشنهاد', 'agent', 'x', $2, $3, $4, $5) RETURNING id, ref""",
            company_id,
            kw.get("created_at", datetime.now(UTC)),
            kw.get("expires_at"),
            kw.get("approver_kind"),
            kw.get("approver_code"),
        )
    )


async def test_each_threshold_reminds_once_held_in_khalvat_and_never_for_a_ceo_card(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    now = datetime.now(UTC)
    old = await _card(su, co["id"], created_at=now - timedelta(hours=30))
    ceo = await _card(su, co["id"], created_at=now - timedelta(hours=30), approver_kind="agent",
                      approver_code=f"{co['code']}-CEO")  # fmt: skip
    acts = MgmtActivities(hub, lambda: _ScopedTx(hub))
    async with holding_switch(su, "engaged"):
        assert (await acts.cartable_reminders())["skipped"] is True
    await su.execute("UPDATE owner.presence SET khalvat = true WHERE id = 1")
    try:
        async with holding_switch(su, "released"):
            first = await acts.cartable_reminders()
            again = await acts.cartable_reminders()
    finally:
        await su.execute("UPDATE owner.presence SET khalvat = false WHERE id = 1")
    assert (
        f"{old['ref']}:age_24h" in first["reminded"]
        and f"{old['ref']}:age_24h" not in again["reminded"]
    )
    assert not any(x.startswith(ceo["ref"]) for x in first["reminded"])
    state = await su.fetchval(
        "SELECT state FROM notify.notifications WHERE link_ref = $1 AND level = 'decision' ORDER BY created_at DESC LIMIT 1",
        old["ref"],
    )
    assert state == "held"  # Khalvat holds it
    d = (await client.get(f"/api/v1/decisions/{old['ref']}", headers=owner)).json()
    assert d["waiting_h"] >= 30 and [x["kind"] for x in d["reminders"]] == ["age_24h"]
    async with hub.db.tx(await hub.companies.ids()) as tx:
        line = await N.morning_line(tx)
    assert "کارت منتظر تو" in line


# --------------------------------------------------------------- settings --
async def test_the_new_settings_blocks(client: httpx.AsyncClient, owner: dict[str, str]) -> None:
    s = (await client.get("/api/v1/owner/settings", headers=owner)).json()
    assert s["audio_briefings"]["morning"] is True and s["ceo_weekly_letter"]["day"] == "sa"
    assert s["reminders"]["ages_h"] == [24, 72, 168]
    r = await client.put(
        "/api/v1/owner/settings", headers={**owner, "If-Match": str(s["version"])},
        json={"audio_briefings": {"ceo_letters": False}, "reminders": {"ages_h": [72, 24]}},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["audio_briefings"] == {"morning": True, "ceo_letters": False}
    assert out["reminders"]["ages_h"] == [24, 72] and out["reminders"]["fraction"] == 0.5
    bad = await client.put(
        "/api/v1/owner/settings", headers={**owner, "If-Match": str(out["version"])},
        json={"ceo_weekly_letter": {"at": "25:00"}},
    )  # fmt: skip
    assert bad.status_code == 422
    back = await client.put(
        "/api/v1/owner/settings", headers={**owner, "If-Match": str(out["version"])},
        json={"audio_briefings": {"ceo_letters": True}, "reminders": {"ages_h": [24, 72, 168]}},
    )  # fmt: skip
    assert back.status_code == 200
