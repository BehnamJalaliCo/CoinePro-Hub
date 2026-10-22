"""Prompt 07 §1 (contract §18.9): the host backup's status files become
backup.* rows, stream events and alerts; the owner and the holding readers
see BackupStatus; nothing restores through the API."""

from __future__ import annotations

import json
import random
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api.domain import backups
from hq_api.hub import Hub

from .conftest import agent_headers


def iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z")


@pytest.fixture
def whub(wk: dict[str, Any], tmp_path: Path) -> Iterator[Hub]:
    """The worker's hub (hq_worker: it alone writes backup.*), reading tmp_path."""
    h: Hub = wk["hub"]
    real = h.settings
    h.settings = replace(real, hub_status_dir=str(tmp_path))
    yield h
    h.settings = real


@pytest.fixture
def status_dir(whub: Hub, tmp_path: Path) -> Path:
    return tmp_path


def hourly(
    at: datetime, *, ok: bool, last_ok: datetime | None, gdrive_ok: bool | None = True
) -> dict[str, Any]:
    snap = f"{random.getrandbits(64):016x}" + "0" * 48
    return {
        "at": iso(at),
        "ok": ok,
        "snapshot": snap if ok else None,
        "size_bytes": 123456,
        "duration_s": 42,
        "error": None if ok else "an off-site copy failed",
        "last_ok_at": iso(last_ok) if last_ok else None,
        "destinations": [
            {"key": "local", "configured": True, "ok": True, "error": None, "last_ok_at": iso(at),
             "used_bytes": 1000, "quota_bytes": None},
            {"key": "gdrive", "configured": True, "ok": gdrive_ok,
             "error": None if gdrive_ok else "copy failed",
             "last_ok_at": iso(last_ok) if last_ok else None, "used_bytes": 900, "quota_bytes": 6 * 10**12},
        ],
        "wal": {"last_archived_at": iso(at - timedelta(seconds=30)), "lag_s": 30, "failed_count": 0},
        "base_backup": {"last_at": iso(at - timedelta(hours=3)), "count": 2},
        "openbao_snapshot": {"configured": False, "last_at": None, "ok": None},
        "check": {"last_at": iso(at), "ok": True},
        "retention": {"hourly": 168, "daily": 90, "weekly": 52, "monthly": 36, "yearly": 10},
        "encryption": "restic (AES-256)",
    }  # fmt: skip


def write(d: Path, name: str, data: dict[str, Any]) -> None:
    (d / f"{name}.json").write_text(json.dumps(data))


async def _notes(su: Any, link_ref: str) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in await su.fetch(
            "SELECT level, title_fa FROM notify.notifications WHERE link_kind = 'backup' AND link_ref = $1",
            link_ref,
        )
    ]


async def test_status_files_become_the_api_and_one_event_per_run(
    client: httpx.AsyncClient, owner: dict[str, str], whub: Hub, su: Any, status_dir: Path
) -> None:
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=random.randint(0, 3000))
    h = hourly(now, ok=True, last_ok=now)
    write(status_dir, "hourly", h)
    write(status_dir, "snapshots", {"at": iso(now), "items": [
        {"id": h["snapshot"], "short_id": h["snapshot"][:8], "time": iso(now), "destination": "local",
         "tags": ["hourly"], "size_bytes": 123456},
        {"id": h["snapshot"], "short_id": h["snapshot"][:8], "time": iso(now), "destination": "gdrive",
         "tags": ["hourly"], "size_bytes": 123456},
    ]})  # fmt: skip
    write(status_dir, "restore-weekly", {
        "at": iso(now - timedelta(days=1)), "ok": True, "duration_s": 300, "source": "gdrive",
        "snapshot": h["snapshot"], "notes": "database set, files and PITR ok",
        "pitr": {"ok": True, "target": "2026-10-17 01:02:03 UTC"}, "db": {"ok": True},
    })  # fmt: skip
    out = await backups.ingest(whub, now=now + timedelta(minutes=5))
    assert out["runs"] == 1 and out["restore_tests"] in (0, 1) and out["alerts"] == 0
    again = await backups.ingest(whub, now=now + timedelta(minutes=10))
    assert again["runs"] == 0  # the same run is stored (and announced) once
    events = await su.fetchval(
        "SELECT count(*) FROM core.outbox WHERE subject LIKE '%.backup.done' AND payload->>'ref' = $1",
        h["snapshot"][:64],
    )
    assert events == 1

    r = await client.get("/api/v1/backups/status", headers=owner)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["hourly"]["ok"] is True and s["hourly"]["snapshot"] == h["snapshot"]
    assert s["hourly"]["next_at"] and s["wal"]["lag_s"] == 30
    assert {d["key"]: d["configured"] for d in s["destinations"]} == {"local": True, "gdrive": True}
    assert s["retention"] == {"hourly": 168, "daily": 90, "weekly": 52, "monthly": 36, "yearly": 10}
    assert s["restore_test"]["ok"] is True and s["restore_test"]["pitr_target"]
    assert s["openbao_snapshot"] == {"last_at": None, "ok": None, "configured": False}
    assert s["encryption"] == "restic (AES-256)"
    assert "password" not in r.text and "token" not in r.text
    snaps = await client.get("/api/v1/backups/snapshots?destination=gdrive", headers=owner)
    assert snaps.status_code == 200
    assert [x["destination"] for x in snaps.json()["items"]] == ["gdrive"]
    # No way to restore through the API.
    assert (await client.post("/api/v1/backups/restore", headers=owner, json={})).status_code in (
        404,
        405,
    )


async def test_a_failed_destination_and_a_stale_backup_alert_once(
    whub: Hub, su: Any, status_dir: Path
) -> None:
    now = datetime.now(UTC).replace(microsecond=0) + timedelta(days=random.randint(1, 300))
    last_ok = now - timedelta(hours=3)
    write(status_dir, "hourly", hourly(now, ok=False, last_ok=last_ok, gdrive_ok=False))
    out = await backups.ingest(whub, now=now + timedelta(minutes=1))
    assert out["runs"] == 1 and out["alerts"] == 2
    failed = await su.fetchval(
        """SELECT count(*) FROM core.outbox WHERE subject LIKE '%.backup.failed'
           AND payload->'data'->>'at' = $1""",
        iso(now),
    )
    assert failed == 1
    dest = await _notes(su, f"backup:dest:gdrive:{iso(last_ok)}")
    stale = await _notes(su, f"backup:stale:{iso(last_ok)}")
    assert [n["level"] for n in dest] == ["decision"] and "gdrive" in dest[0]["title_fa"]
    assert [n["level"] for n in stale] == ["urgent"] and "۲ ساعت" in stale[0]["title_fa"]
    # The next failed run of the same episode raises nothing new.
    write(
        status_dir,
        "hourly",
        hourly(now + timedelta(hours=1), ok=False, last_ok=last_ok, gdrive_ok=False),
    )
    out = await backups.ingest(whub, now=now + timedelta(hours=1, minutes=1))
    assert out["runs"] == 1 and out["alerts"] == 0
    assert len(await _notes(su, f"backup:stale:{iso(last_ok)}")) == 1


async def test_a_recent_success_is_not_stale_and_a_failed_restore_test_is_urgent(
    whub: Hub, su: Any, status_dir: Path
) -> None:
    now = datetime.now(UTC).replace(microsecond=0) + timedelta(days=random.randint(301, 600))
    write(status_dir, "hourly", hourly(now, ok=True, last_ok=now))
    at = iso(now - timedelta(hours=1))
    write(status_dir, "restore-weekly", {
        "at": at, "ok": False, "duration_s": 120, "source": "local", "snapshot": "ab" * 32,
        "notes": "db: restore-test: FAIL: hq: pg_restore failed; pitr: ok",
        "pitr": {"ok": True}, "db": {"ok": False},
    })  # fmt: skip
    out = await backups.ingest(whub, now=now + timedelta(minutes=30))
    assert out["restore_tests"] == 1 and out["alerts"] == 1
    assert [n["level"] for n in await _notes(su, f"backup:restore:{at}")] == ["urgent"]
    row = await su.fetchrow(
        "SELECT ok, source, notes FROM backup.restore_tests WHERE at = $1", now - timedelta(hours=1)
    )
    assert row["ok"] is False and row["source"] == "local" and "pg_restore" in row["notes"]
    out = await backups.ingest(whub, now=now + timedelta(minutes=35))
    assert out["alerts"] == 0  # once


async def test_backups_status_for_holding_readers_only(
    client: httpx.AsyncClient, whub: Hub, su: Any, status_dir: Path, new_company: Callable[..., Any]
) -> None:
    ceo = f"{(await new_company())['code']}-CEO"
    now = datetime.now(UTC).replace(microsecond=0)
    write(status_dir, "hourly", hourly(now, ok=True, last_ok=now))
    await backups.ingest(whub, now=now)
    r = await client.get("/internal/v1/backups/status", headers=await agent_headers("HQ-ADV"))
    assert r.status_code == 200 and r.json()["encryption"] == "restic (AES-256)"
    r = await client.get("/internal/v1/backups/status", headers=await agent_headers(ceo))
    assert r.status_code == 403
    await su.execute(
        """UPDATE agents.runs r SET state = 'done', finished_at = now() FROM core.employees e
           WHERE e.id = r.employee_id AND e.code = ANY($1) AND r.state = 'running' AND r.reason = 'test'""",
        ["HQ-ADV", ceo],
    )


async def test_failing_wal_archiving_is_one_urgent_alert_at_once(
    whub: Hub, su: Any, status_dir: Path, client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    """7.1 §1.1: the last failure newer than the last success (or > 5 segments
    waiting) is a data-loss alarm at once, not after the 2 hours of a stale
    backup; the status shows wal.failing and wal.ready_count."""
    now = datetime.now(UTC).replace(microsecond=0) + timedelta(days=random.randint(301, 600))
    failed_at = iso(now - timedelta(minutes=4))
    run = hourly(now, ok=False, last_ok=now - timedelta(minutes=50))
    run["error"] = "WAL archiving is failing"
    run["wal"] = {
        "last_archived_at": iso(now - timedelta(minutes=20)), "lag_s": 1200, "failed_count": 7,
        "last_failed_at": failed_at, "failing": True, "ready_count": 9,
    }  # fmt: skip
    write(status_dir, "hourly", run)
    out = await backups.ingest(whub, now=now + timedelta(minutes=1))
    notes = await _notes(su, f"backup:wal:{failed_at}")
    assert [n["level"] for n in notes] == ["urgent"] and "WAL" in notes[0]["title_fa"]
    assert out["alerts"] == 1  # the run is 50 minutes old: not stale yet, still told at once
    assert await _notes(su, f"backup:stale:{run['last_ok_at']}") == []
    await backups.ingest(whub, now=now + timedelta(minutes=2))  # the same episode: told once
    assert len(await _notes(su, f"backup:wal:{failed_at}")) == 1
    wal = (await client.get("/api/v1/backups/status", headers=owner)).json()["wal"]
    assert wal["failing"] is True and wal["ready_count"] == 9 and wal["failed_count"] == 7
    # A queue alone (> 5 waiting, no failure yet) is failing too.
    assert backups.wal_failing({"failing": False, "ready_count": 6})
    assert not backups.wal_failing({"failing": False, "ready_count": 5})


async def test_a_failed_restic_check_is_one_urgent_alert(whub: Hub, su: Any, status_dir: Path) -> None:
    """7.1 §2.4: `restic check` failing (hourly.json check.ok false) is urgent
    at once, one per check (backup:check:{at}); the run itself was ok."""
    now = datetime.now(UTC).replace(microsecond=0) + timedelta(days=random.randint(601, 4000))
    run = hourly(now, ok=True, last_ok=now)
    run["check"] = {"last_at": iso(now), "ok": False}
    write(status_dir, "hourly", run)
    out = await backups.ingest(whub, now=now + timedelta(minutes=1))
    notes = await _notes(su, f"backup:check:{iso(now)}")
    assert [n["level"] for n in notes] == ["urgent"] and "restic check" in notes[0]["title_fa"]
    assert out["alerts"] == 1
    assert (await backups.ingest(whub, now=now + timedelta(minutes=6)))["alerts"] == 0


async def test_a_missing_hourly_json_while_runs_exist_is_urgent(
    whub: Hub, su: Any, status_dir: Path
) -> None:
    """7.1 §2.4: backup.runs has rows but hourly.json is gone (the script, its
    directory or the worker's mount broke): urgent, once per last run."""
    # Later than every other test's runs, so this run is the newest one.
    at = (datetime.now(UTC) + timedelta(days=5000)).replace(microsecond=0)
    write(status_dir, "hourly", hourly(at, ok=True, last_ok=at))
    assert (await backups.ingest(whub, now=at))["alerts"] == 0
    (status_dir / "hourly.json").unlink()
    out = await backups.ingest(whub, now=at + timedelta(minutes=5))
    notes = await _notes(su, f"backup:missing:{iso(at)}")
    assert [n["level"] for n in notes] == ["urgent"] and "hourly.json" in notes[0]["title_fa"]
    assert out["alerts"] == 1
    assert (await backups.ingest(whub, now=at + timedelta(minutes=10)))["alerts"] == 0


async def test_openbao_snapshot_and_retention_failures_are_decisions(
    whub: Hub, su: Any, status_dir: Path
) -> None:
    """7.1 §2.2: the OpenBao snapshot configured but not ok (token lapsed or not
    renewable); 7.1 §3: a destination's forget/prune failing. Each a decision,
    once per episode; the same fields healthy raise nothing."""
    now = datetime.now(UTC).replace(microsecond=0) + timedelta(days=random.randint(601, 4000))
    snap_at = iso(now - timedelta(days=33))
    ret_at = iso(now - timedelta(hours=5))
    run = hourly(now, ok=True, last_ok=now)
    run["openbao_snapshot"] = {"configured": True, "last_at": snap_at, "ok": False,
                               "error": "the raft snapshot failed (token expired or revoked?)"}  # fmt: skip
    run["destinations"][0] |= {"retention_ok": True, "retention_error": None, "retention_last_ok_at": iso(now)}
    run["destinations"][1] |= {"retention_ok": False, "retention_error": "forget failed (kept everything)",
                               "retention_last_ok_at": ret_at}  # fmt: skip
    write(status_dir, "hourly", run)
    out = await backups.ingest(whub, now=now + timedelta(minutes=1))
    bao = await _notes(su, f"backup:openbao:{snap_at}")
    ret = await _notes(su, f"backup:forget:gdrive:{ret_at}")
    assert [n["level"] for n in bao] == ["decision"] and "OpenBao" in bao[0]["title_fa"]
    assert [n["level"] for n in ret] == ["decision"] and "gdrive" in ret[0]["title_fa"]
    assert await _notes(su, f"backup:forget:local:{iso(now)}") == []
    assert out["alerts"] == 2
    assert (await backups.ingest(whub, now=now + timedelta(minutes=6)))["alerts"] == 0
    healthy = hourly(now + timedelta(hours=1), ok=True, last_ok=now + timedelta(hours=1))
    healthy["openbao_snapshot"] = {"configured": True, "last_at": iso(now), "ok": True}
    write(status_dir, "hourly", healthy)
    assert (await backups.ingest(whub, now=now + timedelta(hours=1, minutes=1)))["alerts"] == 0
