"""Backups as the API sees them (prompt 07 §1, contract §18.9).

The host's scripts (infra/backup: hourly.sh, restore-weekly.sh) write
metadata-only status files into the backup status directory, mounted
read-only in the worker (/hub-status). `ingest()` (Maintenance, every 5 min)
turns them into backup.* rows, the stream events `backup.done` /
`backup.failed` (topic `backups`) and the alerts:
- the newest successful hourly backup older than 2 h -> one urgent
  notification per episode (category data_loss, contract §5.4);
- an off-site destination failing (a run with ok: false) -> one `decision`
  notification per destination and episode (the urgent one follows at 2 h);
- the weekly restore test failing -> urgent;
- 7.1 §2.4: a failed `restic check` -> urgent (`backup:check:{at}`); no
  hourly.json while backup.runs has rows (the status file vanished, or the
  directory is no longer mounted) -> urgent; 7.1 §2.2: the OpenBao snapshot
  configured but not ok (its token lapsed or cannot be renewed) -> decision;
  7.1 §3: a destination's retention (forget/prune) failing -> decision.
Prometheus alerts on the same conditions from the host's textfile metrics,
independent of this worker (infra/observability/prometheus/rules).
`status()` builds the contract's BackupStatus from the rows. No restore is
possible through the API: the owner restores in their own terminal.

Oversight hook (prompt 08, protocol PR-070): `oversight_finding()` is the one
place that will raise the overseer's finding for the same conditions; until
the oversight tables exist it only logs.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import notify

log = logging.getLogger("hq_api.backups")

STALE_AFTER = timedelta(hours=2)
LINK_KIND = "backup"
RETENTION = {"hourly": 168, "daily": 90, "weekly": 52, "monthly": 36, "yearly": 10}
DESTINATIONS = ("local", "gdrive", "hetzner")


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def wal_failing(wal: dict[str, Any]) -> bool:
    """7.1 §1.1 (contract §18.13): failing archiving or a queue of more than 5."""
    ready = wal.get("ready_count")
    return bool(wal.get("failing")) or (isinstance(ready, int) and ready > 5)


async def oversight_finding(tx: Tx, kind: str, data: dict[str, Any]) -> None:
    """PR-070 (prompt 08 §2): the overseer's finding for a backup problem, once
    per open problem (the same key while it is still open)."""
    from hq_api.domain import oversight

    holding = await tx.first("SELECT id, code FROM core.companies WHERE kind = 'holding'")
    protocol = await tx.first(oversight.PROTOCOL_SQL + " WHERE p.ref = 'PR-070'")
    if holding is None:
        return
    since = data.get("last_ok_at") or "never"
    await oversight.raise_finding(
        tx,
        company_id=holding["id"],
        company_code=holding["code"],
        severity="critical",
        title_fa="backup ساعتی سالم یا تازه نیست",
        body_md=f"Backup problem `{kind}`: last good hourly backup {since}.",
        evidence=[{"kind": "metric", "ref": "backups.status", "note": f"{kind}: {since}"}],
        protocol=protocol,
        by_kind="system",
        by_code="PR-070",
        dedupe_key="PR-070:backup-hourly",
    )
    log.info("backup problem for PR-070", extra={"kind": kind, "data": data})


async def _alert(
    tx: Tx, company: Any, level: str, title: str, link_ref: str, body: str = ""
) -> dict[str, Any] | None:
    """One notification per link_ref, ever (an episode is named by its start)."""
    if await tx.scalar(
        "SELECT 1 FROM notify.notifications WHERE company_id = :co AND link_kind = :lk AND link_ref = :lr",
        co=company.id,
        lk=LINK_KIND,
        lr=link_ref[:100],
    ):
        return None
    return await notify.raise_notification(
        tx,
        company_id=company.id,
        company_code=company.code,
        level=level,
        title_fa=title[:300],
        body_fa=body[:2000],
        link_kind=LINK_KIND,
        link_ref=link_ref[:100],
        source_kind="service",
        source_code="backup",
    )


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z")


async def _more_alerts(tx: Tx, holding: Any, hourly: dict[str, Any] | None) -> list[dict[str, Any]]:
    """7.1 §2.2, §2.4 and §3: the conditions that used to pass without a word.
    Each is one notification per episode (its link_ref names the episode)."""
    rows: list[dict[str, Any]] = []

    async def told(
        level: str, title: str, ref: str, body: str, finding: str | None = None, data: Any = None
    ) -> None:
        row = await _alert(tx, holding, level, title, ref, body)
        if row:
            rows.append(row)
            if finding:
                await oversight_finding(tx, finding, data or {})

    if hourly is None:
        # The runs exist but their status file does not: the host's script, its
        # directory or the worker's mount broke, and every other alert is blind.
        last_run = await tx.scalar(
            "SELECT max(at) FROM backup.runs WHERE company_id = :co", co=holding.id
        )
        if last_run is not None:
            since = _iso(last_run)
            await told(
                "urgent",
                "خطر از دست رفتن داده: فایل وضعیت backup ساعتی (hourly.json) پیدا نمیشود",
                f"backup:missing:{since}",
                f"آخرین اجرای ثبت‌شده: {since}. وضعیت backup دیگر دیده نمیشود؛ "
                "systemctl list-timers 'coinepro-hq-*' و /home/Hub/backups/status را ببینید.",
                "missing",
                {"last_run_at": since},
            )
        return rows
    check = _obj(hourly.get("check"))
    if check.get("ok") is False:
        at = check.get("last_at") or hourly.get("at") or "unknown"
        await told(
            "urgent",
            "خطر از دست رفتن داده: restic check یک مخزن backup را سالم نیافت",
            f"backup:check:{at}",
            f"بررسی روزانه‌ی مخزن‌ها ({at}) شکست خورد؛ شاید snapshotهای آن مخزن باز نشوند. "
            "journalctl -u coinepro-hq-backup-hourly.service",
            "check",
            {"at": at},
        )
    bao = _obj(hourly.get("openbao_snapshot"))
    if bao.get("configured") and bao.get("ok") is not True:
        since = bao.get("last_at") or "never"
        await told(
            "decision",
            "snapshot ‏OpenBao در backup ساعتی گرفته نشد",
            f"backup:openbao:{since}",
            f"{bao.get('error') or 'خطا'}. آخرین snapshot موفق: {since}. "
            "توکن تازه: make openbao-snapshot-token (RUNBOOK §۱۸).",
        )
    for d in hourly.get("destinations") or []:
        if isinstance(d, dict) and d.get("configured") and d.get("retention_ok") is False:
            since = d.get("retention_last_ok_at") or "never"
            await told(
                "decision",
                f"نگهداری backup در مقصد {d.get('key')} اجرا نشد ({d.get('retention_error') or 'خطا'})",
                f"backup:forget:{d.get('key')}:{since}",
                "snapshotهای قدیمی پاک نمیشوند و جای مقصد کم‌کم پر میشود؛ backupها سر جایشان است.",
            )
    return rows


async def ingest(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """Read the status files into backup.*, emit the events, raise the alerts."""
    now = now or datetime.now(UTC)
    root = Path(hub.settings.hub_status_dir)
    hourly = _read(root / "hourly.json")
    snaps = _read(root / "snapshots.json")
    weekly = _read(root / "restore-weekly.json")
    holding = await hub.companies.holding()
    out: dict[str, Any] = {"runs": 0, "restore_tests": 0, "alerts": 0}
    push: list[Any] = []
    async with hub.db.tx([holding.id]) as tx:
        await tx.exec(
            """INSERT INTO backup.status (company_id, at, hourly, restore)
               VALUES (:co, now(), CAST(:h AS jsonb), CAST(:r AS jsonb))
               ON CONFLICT (company_id) DO UPDATE SET at = now(), hourly = EXCLUDED.hourly,
                   restore = EXCLUDED.restore""",
            co=holding.id,
            h=json.dumps(hourly or {}),
            r=json.dumps(weekly or {}),
        )
        if hourly and (at := _ts(hourly.get("at"))):
            ok = bool(hourly.get("ok"))
            dests = [d for d in hourly.get("destinations") or [] if isinstance(d, dict)]
            new = await tx.scalar(
                """INSERT INTO backup.runs (company_id, at, ok, snapshot, size_bytes, duration_s, error,
                       destinations)
                   VALUES (:co, :at, :ok, :snap, :size, :dur, :err, CAST(:d AS jsonb))
                   ON CONFLICT (company_id, at) DO NOTHING RETURNING id""",
                co=holding.id,
                at=at,
                ok=ok,
                snap=hourly.get("snapshot") or None,
                size=hourly.get("size_bytes"),
                dur=hourly.get("duration_s"),
                err=(str(hourly.get("error"))[:300] if hourly.get("error") else None),
                d=json.dumps(dests),
            )
            if new:
                out["runs"] = 1
                await events.emit(
                    tx,
                    holding.code,
                    "backup.done" if ok else "backup.failed",
                    str(hourly.get("snapshot") or "")[:64] or None,
                    {
                        "at": hourly.get("at"),
                        "ok": ok,
                        "error": hourly.get("error"),
                        "destinations": [
                            {"key": d.get("key"), "ok": d.get("ok")}
                            for d in dests
                            if d.get("configured")
                        ],
                    },
                )
                for d in dests:
                    if d.get("configured") and d.get("ok") is False:
                        since = d.get("last_ok_at") or "never"
                        row = await _alert(
                            tx,
                            holding,
                            "decision",
                            f"backup ساعتی به مقصد {d.get('key')} نرسید ({d.get('error') or 'خطا'})",
                            f"backup:dest:{d.get('key')}:{since}",
                            "نسخه‌ی محلی گرفته شد؛ اگر تا ۲ ساعت درست نشود، هشدار فوری میآید.",
                        )
                        if row:
                            out["alerts"] += 1
                            push.append(row)
        last_ok = _ts((hourly or {}).get("last_ok_at"))
        if hourly is not None and (last_ok is None or now - last_ok > STALE_AFTER):
            since = (hourly or {}).get("last_ok_at") or "never"
            row = await _alert(
                tx,
                holding,
                "urgent",
                "خطر از دست رفتن داده: backup ساعتی بیش از ۲ ساعت است موفق نشده",
                f"backup:stale:{since}",
                f"آخرین backup موفق: {since}. خطا: {(hourly or {}).get('error') or '-'}",
            )
            if row:
                out["alerts"] += 1
                push.append(row)
                await oversight_finding(tx, "stale", {"last_ok_at": since})
        wal = _obj((hourly or {}).get("wal"))
        if wal and wal_failing(wal):
            # At once, not after the 2 hours of a stale backup: pg_wal grows by
            # ~16 MB a minute and PITR is already cut (7.1 §1.1).
            since = wal.get("last_failed_at") or (hourly or {}).get("at") or "unknown"
            row = await _alert(
                tx,
                holding,
                "urgent",
                "خطر از دست رفتن داده: آرشیو WAL شکست میخورد",
                f"backup:wal:{since}",
                f"بازگشت به هر دقیقه (PITR) قطع است و pg_wal بزرگ میشود. "
                f"شکست‌ها: {wal.get('failed_count')}، در صف: {wal.get('ready_count')}.",
            )
            if row:
                out["alerts"] += 1
                push.append(row)
                await oversight_finding(tx, "wal", {"last_failed_at": since})
        for row in await _more_alerts(tx, holding, hourly):
            out["alerts"] += 1
            push.append(row)
        if snaps and isinstance(snaps.get("items"), list):
            listed: dict[str, list[dict[str, Any]]] = {}
            for s in snaps["items"]:
                if isinstance(s, dict) and s.get("destination") in DESTINATIONS and s.get("id"):
                    listed.setdefault(s["destination"], []).append(s)
            for dest, items in listed.items():
                ids = [str(s["id"]) for s in items]
                await tx.exec(
                    """DELETE FROM backup.snapshots
                       WHERE company_id = :co AND destination = :d AND NOT (snapshot_id = ANY(:ids))""",
                    co=holding.id,
                    d=dest,
                    ids=ids,
                )
                for s in items:
                    t = _ts(s.get("time"))
                    if t is None:
                        continue
                    await tx.exec(
                        """INSERT INTO backup.snapshots (company_id, destination, snapshot_id, time,
                               size_bytes, tags)
                           VALUES (:co, :d, :id, :t, :size, :tags)
                           ON CONFLICT (company_id, destination, snapshot_id) DO UPDATE
                               SET seen_at = now(), size_bytes = EXCLUDED.size_bytes""",
                        co=holding.id,
                        d=dest,
                        id=str(s["id"]),
                        t=t,
                        size=s.get("size_bytes"),
                        tags=[str(x) for x in s.get("tags") or []][:10],
                    )
        if weekly and (wat := _ts(weekly.get("at"))) and weekly.get("ok") is not None:
            wok = bool(weekly.get("ok"))
            new = await tx.scalar(
                """INSERT INTO backup.restore_tests (company_id, at, ok, duration_s, source, snapshot,
                       notes, detail)
                   VALUES (:co, :at, :ok, :dur, :src, :snap, :notes, CAST(:d AS jsonb))
                   ON CONFLICT (company_id, at) DO NOTHING RETURNING id""",
                co=holding.id,
                at=wat,
                ok=wok,
                dur=weekly.get("duration_s"),
                src=weekly.get("source") if weekly.get("source") in DESTINATIONS else None,
                snap=weekly.get("snapshot"),
                notes=(str(weekly.get("notes"))[:1000] if weekly.get("notes") else None),
                d=json.dumps({k: weekly.get(k) for k in ("db", "pitr", "snapshot_time")}),
            )
            if new:
                out["restore_tests"] = 1
                if not wok:
                    row = await _alert(
                        tx,
                        holding,
                        "urgent",
                        "خطر از دست رفتن داده: تست بازیابی هفتگی backup شکست خورد",
                        f"backup:restore:{weekly.get('at')}",
                        str(weekly.get("notes") or "")[:500],
                    )
                    if row:
                        out["alerts"] += 1
                        push.append(row)
                        await oversight_finding(tx, "restore_test", {"at": weekly.get("at")})
    pending: list[Any] = [r["id"] for r in push if r.get("push_now")]
    if pending:
        await notify.deliver_pending(hub, pending)
    return out


def _restore(weekly: dict[str, Any] | None) -> dict[str, Any]:
    w = weekly or {}
    pitr = _obj(w.get("pitr"))
    return {
        "last_at": w.get("at"),
        "ok": w.get("ok"),
        "duration_s": w.get("duration_s"),
        "notes": w.get("notes"),
        "source": w.get("source"),
        "pitr_target": pitr.get("target"),
    }


async def status(tx: Tx, holding_id: Any, now: datetime | None = None) -> dict[str, Any]:
    """The contract's BackupStatus (§18.9) from the latest rows."""
    now = now or datetime.now(UTC)
    row = await tx.first(
        "SELECT at, hourly, restore FROM backup.status WHERE company_id = :co", co=holding_id
    )
    h: dict[str, Any] = dict(row["hourly"]) if row else {}
    last_ok = await tx.first(
        """SELECT at, snapshot, size_bytes FROM backup.runs WHERE company_id = :co AND ok
           ORDER BY at DESC LIMIT 1""",
        co=holding_id,
    )
    last_at = _ts(h.get("at"))
    wal = _obj(h.get("wal"))
    dests = {d.get("key"): d for d in h.get("destinations") or [] if isinstance(d, dict)}
    destinations = []
    for key in DESTINATIONS:
        d = dests.get(key)
        if d is None and key == "hetzner":
            continue  # optional; listed only when switched on
        d = d or {}
        destinations.append(
            {
                "key": key,
                "configured": bool(d.get("configured", key == "local")),
                "last_ok_at": d.get("last_ok_at"),
                "used_bytes": d.get("used_bytes"),
                "quota_bytes": d.get("quota_bytes"),
                "ok": d.get("ok"),
                "error": d.get("error"),
            }
        )
    bao = _obj(h.get("openbao_snapshot"))
    lag = wal.get("lag_s")
    return {
        "hourly": {
            "last_at": h.get("at"),
            "next_at": (
                (last_at.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
                .isoformat()
                .replace("+00:00", "Z")
                if last_at
                else None
            ),
            "ok": h.get("ok"),
            "snapshot": h.get("snapshot"),
            "size_bytes": h.get("size_bytes"),
            "last_ok_at": (last_ok["at"].isoformat().replace("+00:00", "Z") if last_ok else None),
            "error": h.get("error"),
            "stale": last_ok is None or now - last_ok["at"] > STALE_AFTER,
        },
        "wal": {
            "last_archived_at": wal.get("last_archived_at"),
            "lag_s": int(lag) if isinstance(lag, int | float) else None,
            "failed_count": wal.get("failed_count"),
            "failing": wal_failing(wal) if wal else None,
            "ready_count": wal.get("ready_count"),
        },
        "base_backup": h.get("base_backup") if isinstance(h.get("base_backup"), dict) else None,
        "destinations": destinations,
        "retention": h.get("retention") if isinstance(h.get("retention"), dict) else RETENTION,
        "restore_test": _restore(dict(row["restore"]) if row else None),
        "openbao_snapshot": {
            "last_at": bao.get("last_at"),
            "ok": bao.get("ok"),
            "configured": bool(bao.get("configured")),
        },
        "check": h.get("check") if isinstance(h.get("check"), dict) else None,
        "encryption": "restic (AES-256)",
    }
