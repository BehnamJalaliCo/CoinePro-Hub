"""Rule-based site checks and the hub's own health (prompt 05 §4, contract §16.4).

No model runs here. Every 5 minutes (Temporal Schedule hq-site-checks):
  - each enabled site that is due gets ONE public GET or HEAD, 10 s timeout,
    User-Agent CoinePro-HQ-Monitor/1; redirects are followed only on the same
    host (a redirect to another domain is recorded as it is); status, latency
    and the TLS certificate's days left are kept (ops.checks, 30 days);
  - 3 failures in a row open an incident and ONE work item: the company's SRE
    (charter sre) if hired, else its CTO (charter cto); for the holding, its
    Hub Platform SRE if hired, else the Head of AI Operations - with the last
    checks as evidence. An open incident never opens another one. A healthy
    check closes the incident. A healthy site wakes nobody.
  - the hub's own snapshot (ops.hub_health) for the health.hub tool: scrape
    targets up/down and restarts (Prometheus), disk, memory, the certificate,
    the last backup and restore test (status files of the backup scripts);
    containers come from socket-free host metrics, never the Docker socket.
Roles are found by charter (core.employees.role) and the department code in
the charter file - nothing here knows a company, a department or a URL.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import ssl
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import work as W
from hq_api.hub import Hub
from hq_api.principal import Principal

log = logging.getLogger("hq_api.agents.checks")
SITE_CHECKS = Principal(kind="service", code="site-checks", role="service")
USER_AGENT = "CoinePro-HQ-Monitor/1"
TIMEOUT_S = 10.0
FAILURES_TO_OPEN = 3
MAX_REDIRECTS = 5
MAX_BODY = 256 * 1024
TLS_CACHE_S = 3600.0
PARALLEL = 8
# Who answers an incident: (charter that watches, charter that leads), first hired wins.
RESPONDERS = {"company": ("sre", "cto"), "holding": ("hub_platform_sre", "aiops_head")}


@dataclass
class Result:
    ok: bool
    status: int | None
    latency_ms: int | None
    tls_days_left: int | None
    error_code: str | None


class Checker:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, tls: bool = True) -> None:
        self._transport = transport
        self._tls = tls
        self._tls_cache: dict[str, tuple[float, int | None]] = {}

    async def check(self, site: dict[str, Any]) -> Result:
        url, method = site["url"], site["method"]
        expect = site["expect"] or {}
        want = int(expect.get("status", 200))
        contains = expect.get("contains")
        started = time.monotonic()
        host = urlsplit(url).hostname or ""
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=TIMEOUT_S,
                follow_redirects=False,
                headers={"User-Agent": USER_AGENT},
            ) as http:
                resp, error = await self._fetch(http, method, url, host)
        except httpx.TimeoutException:
            return Result(False, None, None, None, "timeout")
        except httpx.ConnectError as exc:
            code = (
                "dns_error"
                if _is_dns(exc)
                else ("tls_error" if "SSL" in str(exc) else "connect_error")
            )
            return Result(False, None, None, None, code)
        except httpx.HTTPError:
            return Result(False, None, None, None, "http_error")
        latency = int((time.monotonic() - started) * 1000)
        days = await self._tls_days(host) if urlsplit(url).scheme == "https" else None
        if error is not None:
            return Result(False, resp.status_code if resp else None, latency, days, error)
        assert resp is not None
        if resp.status_code != want:
            return Result(False, resp.status_code, latency, days, "unexpected_status")
        if contains and method == "GET" and contains not in resp.text[:MAX_BODY]:
            return Result(False, resp.status_code, latency, days, "missing_text")
        return Result(True, resp.status_code, latency, days, None)

    async def _fetch(
        self, http: httpx.AsyncClient, method: str, url: str, host: str
    ) -> tuple[httpx.Response | None, str | None]:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            resp = await http.request(method, current)
            if resp.status_code not in (301, 302, 303, 307, 308) or "location" not in resp.headers:
                return resp, None
            nxt = urljoin(current, resp.headers["location"])
            if (urlsplit(nxt).hostname or "") != host:
                return resp, None  # another domain: reported as it is, never followed
            current = nxt
        return resp, "too_many_redirects"

    async def _tls_days(self, host: str) -> int | None:
        if not self._tls or not host:
            return None
        hit = self._tls_cache.get(host)
        if hit and time.monotonic() - hit[0] < TLS_CACHE_S:
            return hit[1]
        days = await asyncio.to_thread(_cert_days_left, host)
        self._tls_cache[host] = (time.monotonic(), days)
        return days


def _is_dns(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "name or service not known" in text
        or "nodename" in text
        or "getaddrinfo" in text
        or ("name resolution" in text)
    )


def _cert_days_left(host: str) -> int | None:
    ctx = ssl.create_default_context()
    try:
        with (
            socket.create_connection((host, 443), timeout=TIMEOUT_S) as sock,
            ctx.wrap_socket(sock, server_hostname=host) as tls,
        ):
            cert = tls.getpeercert()
    except (OSError, ssl.SSLError):
        return None
    not_after = cert.get("notAfter") if cert else None
    if not isinstance(not_after, str):
        return None
    expires = ssl.cert_time_to_seconds(not_after)
    return int((expires - time.time()) // 86400)


# ------------------------------------------------------------- the round --
async def run_round(hub: Hub, checker: Checker, *, now: datetime | None = None) -> dict[str, Any]:
    """One round of checks; returns counts (metadata only)."""
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await tx.scalar("SELECT ops.ensure_check_partitions(2)")
        due = await tx.all(
            """SELECT s.id, s.company_id, c.code AS company, c.kind AS company_kind, s.url, s.kind,
                      s.method, s.expect, s.consecutive_failures, s.canary
               FROM ops.sites s JOIN core.companies c ON c.id = s.company_id
               WHERE s.enabled AND c.status = 'active'
                 AND (s.last_checked_at IS NULL
                      OR s.last_checked_at < now() - make_interval(secs => s.interval_s - 30))
               ORDER BY s.last_checked_at NULLS FIRST LIMIT 200"""
        )
    sem = asyncio.Semaphore(PARALLEL)

    async def one(site: dict[str, Any]) -> tuple[dict[str, Any], Result]:
        async with sem:
            return site, await checker.check(site)

    results = await asyncio.gather(*(one(s) for s in due))
    opened = closed = failed = 0
    for site, r in results:
        o, c = await record(hub, site, r)
        opened += o
        closed += c
        failed += not r.ok
    closed += await close_unmonitored(hub)
    return {"checked": len(results), "failed": failed, "opened": opened, "closed": closed}


async def close_unmonitored(hub: Hub) -> int:
    """A site switched off (by the owner, or a canary by the seed) is no longer
    watched, so its open incident is closed: nothing could ever close it."""
    async with hub.db.tx(await hub.companies.ids()) as tx:
        rows = await tx.all(
            """SELECT i.id, i.ref, i.work_id, s.company_id, s.url FROM ops.incidents i
               JOIN ops.sites s ON s.id = i.site_id
               WHERE i.closed_at IS NULL AND NOT s.enabled
               FOR UPDATE OF i"""
        )
        for r in rows:
            await _close(tx, r, r, why="monitoring switched off")
    return len(rows)


async def record(hub: Hub, site: dict[str, Any], r: Result) -> tuple[int, int]:
    """Store one result; open or close the site's incident. (opened, closed)."""
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await tx.exec(
            """INSERT INTO ops.checks (site_id, company_id, at, ok, status, latency_ms, tls_days_left, error_code)
               VALUES (:s, :co, clock_timestamp(), :ok, :st, :lat, :tls, :err)""",
            s=site["id"],
            co=site["company_id"],
            ok=r.ok,
            st=r.status,
            lat=r.latency_ms,
            tls=r.tls_days_left,
            err=r.error_code,
        )
        fails = await tx.scalar(
            """UPDATE ops.sites SET consecutive_failures = CASE WHEN :ok THEN 0 ELSE consecutive_failures + 1 END,
                   last_checked_at = now()
               WHERE id = :s RETURNING consecutive_failures""",
            s=site["id"],
            ok=r.ok,
        )
        incident = await tx.first(
            "SELECT * FROM ops.incidents WHERE site_id = :s AND closed_at IS NULL FOR UPDATE",
            s=site["id"],
        )
        if r.ok and incident is not None:
            await _close(tx, site, incident)
            return 0, 1
        if not r.ok and incident is not None:
            await tx.exec(
                """UPDATE ops.incidents SET checks_failed = checks_failed + 1, last_status = :st,
                       last_error = :err WHERE id = :id""",
                id=incident["id"],
                st=r.status,
                err=r.error_code,
            )
            return 0, 0
        if not r.ok and int(fails) >= FAILURES_TO_OPEN:
            await _open(hub, tx, site, r, int(fails))
            return 1, 0
    return 0, 0


async def responder(hub: Hub, tx: Tx, company_id: Any, company_kind: str) -> dict[str, Any] | None:
    """The employee an incident goes to (by charter; nothing knows a code)."""
    lib = hub.charters
    for role in RESPONDERS["holding" if company_kind == "holding" else "company"]:
        charter = lib.get(role) if lib is not None else None
        row = await tx.first(
            """SELECT e.id, e.code, e.kind FROM core.employees e
               LEFT JOIN core.departments d ON d.id = e.department_id
               WHERE e.company_id = :co AND e.role = :role AND e.status = 'active'
                 AND (CAST(:dept AS text) IS NULL OR d.code = :dept)
               ORDER BY e.kind = 'employee' DESC, e.hired_at LIMIT 1""",
            co=company_id,
            role=role,
            dept=charter.department if charter else None,
        )
        if row is not None:
            return row
    return None


async def _open(hub: Hub, tx: Tx, site: dict[str, Any], r: Result, fails: int) -> None:
    every = await tx.scalar(
        """SELECT bool_and(consecutive_failures >= :n) FROM ops.sites
           WHERE company_id = :co AND enabled AND NOT canary""",
        co=site["company_id"],
        n=FAILURES_TO_OPEN,
    )
    severity = "sev1" if every and not site["canary"] else "sev2"
    inc = await tx.one(
        """INSERT INTO ops.incidents (company_id, site_id, severity, checks_failed, last_status, last_error)
           VALUES (:co, :s, :sev, :n, :st, :err) RETURNING id, ref""",
        co=site["company_id"],
        s=site["id"],
        sev=severity,
        n=fails,
        st=r.status,
        err=r.error_code,
    )
    last = await tx.all(
        """SELECT at, ok, status, latency_ms, tls_days_left, error_code FROM ops.checks
           WHERE site_id = :s ORDER BY at DESC LIMIT :n""",
        s=site["id"],
        n=FAILURES_TO_OPEN,
    )
    who = await responder(hub, tx, site["company_id"], site["company_kind"])
    work_ref = None
    if who is not None:
        lines = "\n".join(
            f"- {c['at']:%Y-%m-%d %H:%M:%S}Z status={c['status'] or '-'} error={c['error_code'] or '-'}"
            f" latency_ms={c['latency_ms'] or '-'}"
            f" tls_days_left={'-' if c['tls_days_left'] is None else c['tls_days_left']}"
            for c in last
        )
        brief = (
            f"Rule-based checks found {site['url']} failing {fails} times in a row "
            f"(incident {inc['ref']}, {severity}{', canary test' if site['canary'] else ''}).\n\n"
            f"Last checks (UTC):\n{lines}\n\n"
            "Establish what is failing, since when, how badly and for whom; classify the severity; "
            "deliver an incident note with evidence. Any restart, rollback or config change is A3: propose it."
        )
        w = await W.create(
            tx,
            SITE_CHECKS,
            company_id=site["company_id"],
            company_code=site["company"],
            title=f"Incident {inc['ref']}: {site['url']} is failing"[:300],
            brief=brief,
            kind="event",
            priority="P0" if severity == "sev1" else "P3",
            assignee_code=who["code"],
            budget=W.BudgetIn(tokens=hub.settings.incident_budget_tokens),
        )
        await tx.exec(
            "UPDATE work.work SET evidence = CAST(:ev AS jsonb) WHERE id = :id",
            id=w["id"],
            ev=json.dumps(
                [
                    {
                        "kind": "log",
                        "ref": f"incident:{inc['ref']}",
                        "note": f"{fails} failed checks",
                    },
                    *(
                        {
                            "kind": "metric",
                            "ref": f"check:{c['at']:%Y-%m-%dT%H:%M:%SZ}",
                            "note": f"status={c['status'] or '-'} error={c['error_code'] or '-'}",
                        }
                        for c in last
                    ),
                ]
            ),
        )
        await tx.exec(
            "UPDATE ops.incidents SET work_id = :w WHERE id = :id", id=inc["id"], w=w["id"]
        )
        work_ref = w["ref"]
    await audit.record(
        tx,
        audit.SYSTEM,
        company_id=site["company_id"],
        action="incident.open",
        action_class="A1",
        target_kind="incident",
        target_ref=inc["ref"],
        summary=f"{site['url']}: {fails} failures, {severity}"
        + (f", work {work_ref}" if work_ref else ", no responder"),
    )
    if work_ref:
        await events.emit(
            tx,
            site["company"],
            "work.updated",
            work_ref,
            {"incident": inc["ref"], "severity": severity, "opened": True},
        )


async def _close(
    tx: Tx, site: dict[str, Any], incident: dict[str, Any], *, why: str = "healthy again"
) -> None:
    await tx.exec("UPDATE ops.incidents SET closed_at = now() WHERE id = :id", id=incident["id"])
    if incident["work_id"] is not None:
        w = await W.load(tx, incident["work_id"])
        await W.event(
            tx, w, "incident_closed", SITE_CHECKS, {"incident": incident["ref"], "why": why}
        )
    await audit.record(
        tx,
        audit.SYSTEM,
        company_id=site["company_id"],
        action="incident.close",
        action_class="A1",
        target_kind="incident",
        target_ref=incident["ref"],
        summary=f"{site['url']} {why}",
    )


async def purge_old_checks(hub: Hub, keep_days: int = 30) -> int:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        n: int = await tx.scalar("SELECT ops.drop_old_check_partitions(:k)", k=keep_days)
    return n


# ----------------------------------------------------------- hub health --
async def hub_snapshot(
    hub: Hub, *, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, Any]:
    """The hub's own health for health.hub: metadata only, nothing secret."""
    data: dict[str, Any] = {}
    # Containers: socket-free host metrics (infra/observability/container-metrics.sh).
    queries = {
        "up": 'max by (service) (hq_container_up{oneshot="false"})',
        "restarts_24h": 'max by (service) (increase(hq_container_restarts_total{oneshot="false"}[24h]))',
        "disk_used_pct": '100 * (1 - node_filesystem_avail_bytes{mountpoint="/"}'
        ' / node_filesystem_size_bytes{mountpoint="/"})',
        "memory_used_pct": "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)",
        "load1": "node_load1",
    }
    try:
        async with httpx.AsyncClient(
            base_url=hub.settings.prometheus_url, timeout=5.0, transport=transport
        ) as http:
            for key, q in queries.items():
                resp = await http.get("/api/v1/query", params={"query": q})
                vec = (
                    resp.json().get("data", {}).get("result", []) if resp.status_code == 200 else []
                )
                if key in ("up", "restarts_24h"):
                    data[key] = {
                        str(v["metric"].get("service", "?")): float(v["value"][1]) for v in vec[:100]
                    }
                elif vec:
                    data[key] = round(float(vec[0]["value"][1]), 1)
    except (httpx.HTTPError, ValueError, KeyError):
        data["prometheus"] = "unreachable"
    if isinstance(data.get("up"), dict):
        up = data["up"]
        data["services_up"] = f"{sum(1 for v in up.values() if v >= 1)}/{len(up)}"
        data["restarts_24h"] = {k: int(v) for k, v in (data.get("restarts_24h") or {}).items() if v}
    status_dir = Path(hub.settings.hub_status_dir)
    for name in ("backup", "restore-test"):
        p = status_dir / f"{name}.json"
        try:
            s = json.loads(p.read_text())
        except (OSError, ValueError):
            data[name.replace("-", "_")] = None
            continue
        at = s.get("at")
        age = None
        if isinstance(at, str):
            try:
                age = round(
                    (
                        datetime.now(UTC) - datetime.fromisoformat(at.replace("Z", "+00:00"))
                    ).total_seconds()
                    / 3600,
                    1,
                )
            except ValueError:
                age = None
        data[name.replace("-", "_")] = {
            k: s.get(k) for k in ("at", "ok", "size_bytes", "duration_s", "stamp") if k in s
        } | {"age_hours": age}
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        cert = await tx.scalar(
            """SELECT k.tls_days_left FROM ops.checks k JOIN ops.sites s ON s.id = k.site_id
               WHERE s.company_id = :co AND NOT s.canary AND k.tls_days_left IS NOT NULL
               ORDER BY k.at DESC LIMIT 1""",
            co=holding.id,
        )
        data["certificate_days_left"] = cert
        quota = await tx.first(
            """SELECT q.status FROM llm.quota_status q JOIN llm.connections cn ON cn.id = q.connection_id
               WHERE cn.kind = 'claude_subscription' ORDER BY q.changed_at DESC LIMIT 1"""
        )
        data["subscription_quota"] = quota["status"] if quota else "ok"
        await tx.exec(
            """INSERT INTO ops.hub_health (company_id, at, data) VALUES (:co, now(), CAST(:d AS jsonb))
               ON CONFLICT (company_id) DO UPDATE SET at = now(), data = EXCLUDED.data""",
            co=holding.id,
            d=json.dumps(data, default=str),
        )
    return data
