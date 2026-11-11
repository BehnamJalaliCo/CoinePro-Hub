"""Prompt 24 (contract §33.2-§33.3): crypto payments, read and reconciled, and the revenue board.

The chain is a fake egress (`payments_chain.OVERRIDE`) that answers `head` and `scan` as egress's
`chain-read` does; a company's ledger is a real paired runner (the routes of prompt 17) that answers
its `ledger` job with rows of the output contract (seed/payments/ledger_v1.yaml). The model router is
faked to fail loudly: no number here may ever come from a model.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
import pytest

from hq_api import workflows_client
from hq_api.domain import money_jobs as MJ
from hq_api.domain import payments as P
from hq_api.domain import payments_chain as PC
from hq_api.domain import payments_reconcile as PR
from hq_api.domain import revenue_board as RB
from hq_api.hub import Hub

from .conftest import agent_headers, idem, step_up
from .test_p17_runners import pair, take

API = "/api/v1"
BSC_ADDR = "0x" + "ab" * 20
TRON_ADDR = "T" + "J" * 33


def h64() -> str:
    return secrets.token_hex(32)


def bsc_hash() -> str:
    return "0x" + h64()


def customer(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def iso(d: datetime) -> str:
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def row(
    ext: str,
    who: str,
    amount: str | None,
    tx: str | None,
    paid: datetime,
    *,
    network: str | None = "bsc_usdt",
    kind: str = "crypto",
    days: int | None = 30,
    plan: str = "pro",
) -> dict[str, Any]:
    return {
        "ext_id": ext,
        "customer": customer(who),
        "plan": plan,
        "amount_usdt": amount,
        "network": network if kind == "crypto" else None,
        "tx_hash": tx,
        "paid_at": iso(paid),
        "period_start": iso(paid) if days else None,
        "period_end": iso(paid + timedelta(days=days)) if days else None,
        "kind": kind,
    }


def batch(rows: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    return {"contract": "ledger_v1", "rows": rows, "next_cursor": None, "has_more": False, **kw}


@pytest.fixture(autouse=True)
def no_model(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Numbers by code: a model call anywhere in this file is a failure."""
    calls: list[dict[str, Any]] = []

    async def refuse(hub: Any, req: dict[str, Any], timeout_s: float = 60.0) -> Any:
        calls.append(req)
        raise AssertionError(f"a model was called for numbers: {req.get('task_class')}")

    monkeypatch.setattr(workflows_client, "route_order", refuse)
    return calls


class FakeChain:
    """egress `chain-read`: a head and pages of transfers to the address."""

    def __init__(self) -> None:
        self.head = 1_000_000
        self.transfers: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.fail: str | None = None

    def add(
        self, tx: str, amount: str, at: datetime, *, conf: int = 50, to: str = BSC_ADDR
    ) -> None:
        self.transfers.append(
            {"tx_hash": tx, "idx": 0, "from": "0x" + "cd" * 20, "to": to, "amount_usdt": amount,
             "block": self.head - conf, "confirmations": conf, "at": iso(at)}
        )  # fmt: skip

    async def call(self, hub: Any, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(body)
        if self.fail:
            return {"outcome": "error", "code": self.fail, "data": None}
        now = datetime.now(UTC)
        if body["op"] == "head":
            return {"outcome": "ok", "data": {"head": self.head, "head_at": iso(now), "block_s": 3}}
        return {
            "outcome": "ok",
            "data": {
                "transfers": self.transfers,
                "scan_next": self.head + 1,
                "scan_fingerprint": None,
                "scanned_to_at": iso(now),
                "done": True,
            },
        }


@pytest.fixture
def chain(monkeypatch: pytest.MonkeyPatch) -> FakeChain:
    fake = FakeChain()
    monkeypatch.setattr(PC, "OVERRIDE", fake)
    return fake


async def add_source(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, Any], code: str, body: dict[str, Any]
) -> httpx.Response:
    raw = json.dumps(body).encode()
    su = await step_up(hub, owner["session_id"], "payment.source", hashlib.sha256(raw).hexdigest())
    return await client.post(
        f"{API}/companies/{code}/payment-sources",
        content=raw,
        headers={**owner["headers"], **su, **idem(), "Content-Type": "application/json"},
    )


async def chain_source(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, Any], code: str
) -> dict[str, Any]:
    r = await add_source(client, hub, owner, code, {"kind": "chain", "network": "bsc_usdt",
                                                    "address": BSC_ADDR})  # fmt: skip
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


async def ingest(hub: Hub, source_id: Any, rows: list[dict[str, Any]]) -> int:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        src = await P.load_source(tx, UUID(str(source_id)))
        return await P.ingest(tx, src, P.validate_batch(batch(rows)))


async def ledger_source_row(su: Any, company_id: Any) -> UUID:
    """A ledger source written straight into the table (the route needs a paired runner)."""
    rid: UUID = await su.fetchval(
        """INSERT INTO money.payment_sources (company_id, kind, adapter) VALUES ($1, 'ledger', 'ledger_v1')
           ON CONFLICT (company_id, adapter) WHERE kind = 'ledger' DO UPDATE SET enabled = true
           RETURNING id""",
        company_id,
    )
    return rid


# =================================================================== units ==
def test_the_contract_is_data_and_names_no_company() -> None:
    c = P.contract()
    assert set(c["columns"]) == {
        "ext_id", "customer", "plan", "amount_usdt", "network", "tx_hash", "paid_at",
        "period_start", "period_end", "kind",
    }  # fmt: skip
    text = (P.SEED / "ledger_v1.yaml").read_text(encoding="utf-8").lower()
    for word in ("select ", "from ", "password", "dsn"):
        assert word not in text, word


def test_a_good_batch_is_validated() -> None:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    rows = [
        row("p1", "a", "10.5", bsc_hash(), now),
        row("p2", "b", "20", h64(), now, network="trc20_usdt", days=None),
        row("s1", "c", None, None, now, kind="store"),
    ]
    b = P.validate_batch(batch(rows, next_cursor="c-2", has_more=True))
    assert [r.ext_id for r in b.rows] == ["p1", "p2", "s1"]
    assert b.rows[0].amount_usdt == Decimal("10.5") and b.rows[2].amount_usdt is None
    assert b.rows[1].period_start is None and b.next_cursor == "c-2" and b.has_more


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"amount_usdt": 10.5}, "متن"),  # a float, never: a decimal string
        ({"amount_usdt": "0"}, "صفر"),
        ({"tx_hash": "0x" + "zz" * 32}, "هش"),
        ({"network": "eth_usdt"}, "مجاز"),
        ({"customer": "alice@example.com"}, "قالب"),
        ({"period_end": "2026-09-01T00:00:00Z"}, "پایان"),
        ({"period_start": None}, "هر دو"),
        ({"kind": "store"}, "خالی"),
        ({"paid_at": "2026-10-01 10:00"}, "قالب"),
    ],
)
def test_one_broken_row_refuses_the_whole_batch(change: dict[str, Any], why: str) -> None:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    bad = {**row("p2", "b", "12", bsc_hash(), now), **change}
    with pytest.raises(P.LedgerBreak) as info:
        P.validate_batch(batch([row("p1", "a", "10", bsc_hash(), now), bad]))
    assert "ledger_v1" in info.value.reason_fa and why in info.value.reason_fa


def test_the_batch_shape_is_checked() -> None:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    good = row("p1", "a", "10", bsc_hash(), now)
    for doc in (
        {"contract": "ledger_v2", "rows": []},
        batch([{**good, "email": "x"}]),
        batch([good, good]),  # a repeated ext_id
        batch([good] * 501),
        batch([], has_more="yes"),
        batch([], next_cursor="x" * 201),
        "rows",
    ):
        with pytest.raises(P.LedgerBreak):
            P.validate_batch(doc)


def test_the_judge_of_one_ledger_row() -> None:
    paid = datetime(2026, 10, 1, 12, tzinfo=UTC)
    grace = timedelta(minutes=60)
    covered = PR.Coverage(paid - timedelta(days=7), paid + timedelta(hours=3))
    j = PR.judge
    assert (
        j(Decimal(10), paid, PR.Seen(Decimal(10), 20), covered, threshold=15, grace=grace)[0]
        == "matched"
    )
    assert (
        j(Decimal(10), paid, PR.Seen(Decimal(11), 20), covered, threshold=15, grace=grace)[0]
        == "matched"
    )
    st, got, note = j(
        Decimal(10), paid, PR.Seen(Decimal("7.5"), 20), covered, threshold=15, grace=grace
    )
    assert (st, got) == ("amount_mismatch", Decimal("7.5")) and "7.5" in (note or "")
    assert (
        j(Decimal(10), paid, PR.Seen(Decimal(10), 3), covered, threshold=15, grace=grace)[0]
        == "pending_chain"
    )
    assert j(Decimal(10), paid, None, covered, threshold=15, grace=grace)[0] == "ledger_only"
    # the scan has not passed the payment's time by the grace yet, or never read, or not that far back
    late = PR.Coverage(paid - timedelta(days=7), paid + timedelta(minutes=10))
    assert j(Decimal(10), paid, None, late, threshold=15, grace=grace)[0] == "pending_chain"
    assert j(Decimal(10), paid, None, None, threshold=15, grace=grace)[0] == "pending_chain"
    old = PR.Coverage(paid + timedelta(days=1), paid + timedelta(days=2))
    assert j(Decimal(10), paid, None, old, threshold=15, grace=grace)[0] == "pending_chain"


def test_holt_on_a_fixed_series() -> None:
    values, sigma = RB.holt([100.0, 110.0, 120.0, 130.0, 140.0], 0.5, 0.3, 3)
    assert [round(v, 6) for v in values] == [150.0, 160.0, 170.0] and sigma == 0.0
    values, sigma = RB.holt([100.0, 120.0, 110.0, 150.0], 0.5, 0.3, 1)
    # by hand: l1=120 b1=20; f2=140 r=-30 l2=125 b2=15.5; f3=140.5 r=9.5
    assert round(sigma, 6) == 19.75
    l3 = 0.5 * 150 + 0.5 * 140.5
    b3 = 0.3 * (l3 - 125) + 0.7 * 15.5
    assert round(values[0], 6) == round(l3 + b3, 6)


def test_mrr_is_spread_over_the_period() -> None:
    start = datetime(2026, 1, 16, tzinfo=UTC)
    pays = [RB.Pay("a", Decimal(31), start, start + timedelta(days=31))]
    jan = RB.mrr(pays, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC))
    feb = RB.mrr(pays, datetime(2026, 2, 1, tzinfo=UTC), datetime(2026, 3, 1, tzinfo=UTC))
    assert round(jan, 6) == Decimal(16) and round(feb, 6) == Decimal(15)


# ============================================================ the sources ==
async def test_a_source_needs_the_step_up_and_a_public_address(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = await new_company()
    h = owner_session["headers"]
    body = {"kind": "chain", "network": "bsc_usdt", "address": BSC_ADDR}
    r = await client.post(f"{API}/companies/{co['code']}/payment-sources", json=body, headers=h)
    assert (r.status_code, r.json()["code"]) == (403, "step_up_required")
    # a step-up for another body is refused
    su = await step_up(hub, owner_session["session_id"], "payment.source", "0" * 64)
    r = await client.post(
        f"{API}/companies/{co['code']}/payment-sources", json=body, headers={**h, **su}
    )
    assert (r.status_code, r.json()["code"]) == (403, "step_up_invalid")
    src = await chain_source(client, hub, owner_session, co["code"])
    assert (
        src["kind"] == "chain" and src["state"] == "not_configured" and src["address"] == BSC_ADDR
    )
    assert src["adapter"] == "chain-read" and "key" not in json.dumps(src).lower()
    # the same address again changes the one already there
    again = await add_source(client, hub, owner_session, co["code"],
                             {**body, "address": BSC_ADDR.upper().replace("0X", "0x"), "enabled": False})  # fmt: skip
    assert (
        again.status_code == 201 and again.json()["id"] == src["id"] and not again.json()["enabled"]
    )
    bad = await add_source(client, hub, owner_session, co["code"],
                           {"kind": "chain", "network": "trc20_usdt", "address": BSC_ADDR})  # fmt: skip
    assert bad.status_code == 422 and bad.json()["message_fa"]
    tron = await add_source(client, hub, owner_session, co["code"],
                            {"kind": "chain", "network": "trc20_usdt", "address": TRON_ADDR})  # fmt: skip
    assert tron.status_code == 201
    # a ledger source needs the company's runner paired
    led = await add_source(client, hub, owner_session, co["code"], {"kind": "ledger"})
    assert led.status_code == 409 and "runner" in led.json()["message_fa"]
    r = await client.get(f"{API}/companies/{co['code']}/payment-sources", headers=h)
    assert r.status_code == 200 and {s["network"] for s in r.json()} == {"bsc_usdt", "trc20_usdt"}
    # the holding takes no payments
    holding = await hub.companies.holding()
    r = await client.get(f"{API}/companies/{holding.code}/payment-sources", headers=h)
    assert r.status_code == 404


# ======================================================= the ledger, read ==
async def test_the_ledger_is_read_through_the_runner_and_validated(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any],
    new_company: Callable[..., Any], su: Any,
) -> None:  # fmt: skip
    co = await new_company()
    rn = await pair(client, hub, owner_session, co)
    h = owner_session["headers"]
    # an old runner cannot read a ledger
    src = await add_source(client, hub, owner_session, co["code"], {"kind": "ledger"})
    assert src.status_code == 201, src.text
    sid = src.json()["id"]
    r = await client.post(f"{API}/payment-sources/{sid}/read", headers=h)
    assert r.status_code == 422  # Idempotency-Key is required
    r = await client.post(f"{API}/payment-sources/{sid}/read", headers={**h, **idem()})
    assert r.status_code == 200 and not r.json()["queued"]
    assert "0.3.0" in r.json()["source"]["last_error_fa"] and r.json()["source"]["state"] == "error"
    await su.execute("UPDATE infra.servers SET runner_version = '0.3.0' WHERE id = $1",
                     UUID(rn["server"]["id"]))  # fmt: skip
    rn["h"] = {**rn["h"], "X-HQ-Runner-Version": "0.3.0"}
    r = await client.post(f"{API}/payment-sources/{sid}/read", headers={**h, **idem()})
    assert r.status_code == 200 and r.json()["queued"], r.text
    job = await take(client, rn)
    assert job["kind"] == "ledger"
    assert job["args"] == {"contract": "ledger_v1", "since_cursor": None, "limit": 500}
    now = datetime.now(UTC) - timedelta(days=1)
    rows = [
        row("L-1", "ali", "25", bsc_hash(), now),
        row("S-1", "sara", None, None, now, kind="store"),
    ]
    r = await client.post(
        f"{API}/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "data": batch(rows, next_cursor="after-L-1")},
        headers=rn["h"],
    )
    assert r.status_code == 200, r.text
    got = await su.fetch(
        "SELECT ext_id, kind, status, amount_usdt FROM money.payments WHERE company_id = $1 ORDER BY ext_id",
        co["id"],
    )
    assert [(g["ext_id"], g["kind"], g["status"]) for g in got] == [
        ("L-1", "crypto", "pending_chain"), ("S-1", "store", "matched"),
    ]  # fmt: skip
    s = await su.fetchrow("SELECT * FROM money.payment_sources WHERE id = $1", UUID(sid))
    assert (s["cursor"], s["pending_job_id"], s["state"]) == ("after-L-1", None, "ok")
    # the store's buyer is a paid lead (§33.4)
    lead = await su.fetchrow(
        "SELECT l.stage, l.paid_at, l.source FROM sales.leads l WHERE l.company_id = $1 AND l.contact = $2",
        co["id"], customer("sara"),
    )  # fmt: skip
    assert lead["stage"] == "paid" and lead["paid_at"] is not None and lead["source"] == "payment"
    # the next read asks from the cursor; a broken batch refuses everything of it
    r = await client.post(f"{API}/payment-sources/{sid}/read", headers={**h, **idem()})
    job = await take(client, rn)
    assert job["args"]["since_cursor"] == "after-L-1"
    broken = [row("L-2", "reza", "30", bsc_hash(), now), {**row("L-3", "x", "1", bsc_hash(), now),
                                                           "amount_usdt": 1.0}]  # fmt: skip
    r = await client.post(
        f"{API}/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "data": batch(broken)},
        headers=rn["h"],
    )
    assert r.status_code == 200
    assert (
        await su.fetchval(
            "SELECT count(*) FROM money.payments WHERE company_id = $1 AND ext_id = 'L-2'", co["id"]
        )
        == 0
    )
    s = await su.fetchrow("SELECT * FROM money.payment_sources WHERE id = $1", UUID(sid))
    assert (
        s["state"] == "error" and "ledger_v1" in s["last_error_fa"] and s["cursor"] == "after-L-1"
    )
    # the job's audit names the contract only
    audits = await su.fetch(
        "SELECT summary FROM audit.entries WHERE target_ref = $1", str(job["id"])
    )
    assert audits and all("ledger ledger_v1" in a["summary"] for a in audits)
    assert all(customer("reza") not in a["summary"] for a in audits)


# ======================================================== the chain, read ==
async def test_the_chain_is_read_through_egress_and_reconciled(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any],
    new_company: Callable[..., Any], su: Any, chain: FakeChain,
) -> None:  # fmt: skip
    co = await new_company()
    h = owner_session["headers"]
    src = await chain_source(client, hub, owner_session, co["code"])
    lsid = await ledger_source_row(su, co["id"])
    paid = datetime.now(UTC) - timedelta(days=2)
    t_ok, t_short, t_orphan, t_missing = bsc_hash(), bsc_hash(), bsc_hash(), bsc_hash()
    chain.add(t_ok, "40", paid)
    chain.add(t_short, "15", paid)
    chain.add(t_orphan, "9.5", paid)
    await ingest(hub, lsid, [
        row("M-1", "ali", "40", t_ok, paid), row("M-2", "sara", "20", t_short, paid),
        row("M-3", "reza", "150", t_missing, paid),
    ])  # fmt: skip
    r = await client.post(f"{API}/payment-sources/{src['id']}/read", headers={**h, **idem()})
    assert r.status_code == 200, r.text
    assert r.json()["transfers"] == 3 and r.json()["source"]["state"] == "ok"
    assert chain.calls[0] == {"channel": "chain-read", "op": "head", "network": "bsc_usdt"}
    assert chain.calls[1]["op"] == "scan" and chain.calls[1]["address"] == BSC_ADDR
    assert all("key" not in c for c in chain.calls)
    r = await client.get(f"{API}/companies/{co['code']}/payments", headers=h)
    by = {p["ext_id"]: p for p in r.json()["items"]}
    assert by["M-1"]["status"] == "matched"
    assert by["M-2"]["status"] == "amount_mismatch" and Decimal(by["M-2"]["chain_amount"]) == 15
    assert by["M-3"]["status"] == "ledger_only"
    orphan = by[f"chain:{t_orphan}"]
    assert orphan["status"] == "chain_only" and orphan["customer"] is None
    r = await client.get(f"{API}/companies/{co['code']}/reconcile", headers=h)
    day = next(d for d in r.json() if d["day"] == paid.date().isoformat())
    assert (day["ledger_count"], day["chain_count"], day["matched"], day["ledger_only"],
            day["chain_only"], day["amount_mismatch"]) == (3, 3, 1, 1, 1, 1)  # fmt: skip
    assert day["note_fa"]
    # a chain that answers badly: the owner's read is a 502, the reason stays on the source
    chain.fail = "rate_limited"
    r = await client.post(f"{API}/payment-sources/{src['id']}/read", headers={**h, **idem()})
    assert (
        r.status_code == 502 and r.json()["code"] == "connector_failed" and r.json()["message_fa"]
    )
    s = await su.fetchrow("SELECT state, last_error_fa FROM money.payment_sources WHERE id = $1",
                          UUID(src["id"]))  # fmt: skip
    assert s["state"] == "error" and "محدودیت" in s["last_error_fa"]
    # the scheduled read records the error and raises nothing
    out = await MJ.read_due(hub)
    assert out["errors"] >= 1


async def test_a_failed_chain_read_gives_its_key_back(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any],
    new_company: Callable[..., Any], chain: FakeChain,
) -> None:  # fmt: skip
    """Audit 2026-11-11: the app retries a failed read with the same Idempotency-Key; the
    claim committed before the chain read must not answer it 409 «still running» for 24 h."""
    co = await new_company()
    h = owner_session["headers"]
    src = await chain_source(client, hub, owner_session, co["code"])
    key = idem()
    chain.fail = "rate_limited"
    r = await client.post(f"{API}/payment-sources/{src['id']}/read", headers={**h, **key})
    assert r.status_code == 502, r.text
    chain.fail = None
    r = await client.post(f"{API}/payment-sources/{src['id']}/read", headers={**h, **key})
    assert r.status_code == 200, r.text
    again = await client.post(f"{API}/payment-sources/{src['id']}/read", headers={**h, **key})
    assert again.status_code == 200 and again.headers.get("Idempotent-Replay") == "true"


async def test_the_four_reconcile_cases_alert_the_ceo_and_fin_once(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any],
    new_company: Callable[..., Any], su: Any, chain: FakeChain,
) -> None:  # fmt: skip
    co = await new_company()
    src = await chain_source(client, hub, owner_session, co["code"])
    lsid = await ledger_source_row(su, co["id"])
    paid = datetime.now(UTC) - timedelta(days=1)
    ok, short, orphan = bsc_hash(), bsc_hash(), bsc_hash()
    chain.add(ok, "30", paid)
    chain.add(short, "5", paid)
    chain.add(orphan, "12", paid)
    shallow = bsc_hash()
    chain.add(shallow, "30", paid, conf=3)  # not deep enough yet
    await ingest(hub, lsid, [
        row("A-1", "ali", "30", ok, paid), row("A-2", "sara", "10", short, paid),
        row("A-3", "reza", "250", bsc_hash(), paid), row("A-4", "mina", "50", bsc_hash(), paid),
        row("A-5", "nima", "30", shallow, paid),
    ])  # fmt: skip
    await PC.read_chain(hub, UUID(src["id"]))
    out = await MJ.reconcile_company(hub, co["id"])
    assert out["counts"]["matched"] == 1 and out["counts"]["amount_mismatch"] == 1
    assert out["counts"]["ledger_only"] == 2 and out["counts"]["chain_only"] == 1
    assert out["counts"]["pending_chain"] == 1
    assert out["alerts"] == 4 and out["critical"] == 1
    works = await su.fetch(
        """SELECT w.title, e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE w.company_id = $1 ORDER BY w.created_at""",
        co["id"],
    )
    assignees = {w["code"] for w in works}
    assert assignees == {f"{co['code']}-CEO", f"{co['code']}-FIN-MGR"}
    assert len(works) == 6  # three kinds, each to both
    # the owner sees one critical line only (the ledger_only above 100 USDT)
    notes = await su.fetch(
        "SELECT level, domain, critical_reason, owner_visible, body_fa FROM notify.notifications "
        "WHERE company_id = $1 AND source_code = 'money'",
        co["id"],
    )
    assert len(notes) == 1 and notes[0]["critical_reason"] == "money" and notes[0]["owner_visible"]
    assert notes[0]["domain"] == "revenue" and "250" in notes[0]["body_fa"]
    alerts = await su.fetch(
        "SELECT kind, critical FROM money.alerts WHERE company_id = $1", co["id"]
    )
    assert sorted((a["kind"], a["critical"]) for a in alerts) == [
        ("amount_mismatch", False), ("chain_only", False), ("ledger_only", False), ("ledger_only", True),
    ]  # fmt: skip
    events = await su.fetch(
        "SELECT subject FROM core.outbox WHERE subject = $1", f"hq.core.{co['code']}.payment.alert"
    )
    assert len(events) == 4
    # told once: a second reconcile alerts nothing new
    again = await MJ.reconcile_company(hub, co["id"])
    assert again["alerts"] == 0 and again["critical"] == 0
    # §33.4: the matched customer's lead is paid; the money without a customer is a lead to claim
    leads = {
        r["contact"]: r
        for r in await su.fetch(
            "SELECT contact, stage, source FROM sales.leads WHERE company_id = $1", co["id"]
        )
    }
    assert leads[customer("ali")]["stage"] == "paid"
    assert leads["tx-" + orphan[2:42]]["stage"] == "new"
    assert customer("reza") not in leads  # money that never arrived makes no paid lead
    # a ledger row that later claims the orphan's hash: the derived row goes
    await ingest(hub, lsid, [row("A-6", "omid", "12", orphan, paid)])
    await MJ.reconcile_company(hub, co["id"])
    st = await su.fetch(
        "SELECT ext_id, status FROM money.payments WHERE company_id = $1 AND tx_hash = $2",
        co["id"], orphan,
    )  # fmt: skip
    assert [(s["ext_id"], s["status"]) for s in st] == [("A-6", "matched")]


async def test_payments_list_pages_and_filters(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any],
    new_company: Callable[..., Any], su: Any,
) -> None:  # fmt: skip
    co = await new_company()
    lsid = await ledger_source_row(su, co["id"])
    base = datetime.now(UTC) - timedelta(days=10)
    await ingest(hub, lsid, [row(f"P-{i}", f"c{i}", "5", bsc_hash(), base + timedelta(hours=i))
                             for i in range(5)])  # fmt: skip
    h = owner_session["headers"]
    url = f"{API}/companies/{co['code']}/payments"
    assert (await client.get(url, params={"limit": 201}, headers=h)).status_code == 422
    r = await client.get(url, params={"limit": 2}, headers=h)
    first = r.json()
    assert [p["ext_id"] for p in first["items"]] == ["P-4", "P-3"] and first["next_cursor"]
    r = await client.get(url, params={"limit": 2, "cursor": first["next_cursor"]}, headers=h)
    assert [p["ext_id"] for p in r.json()["items"]] == ["P-2", "P-1"]
    r = await client.get(url, params={"status": "matched"}, headers=h)
    assert r.json()["items"] == []
    day = (base + timedelta(hours=2)).date().isoformat()
    r = await client.get(url, params={"from": day, "to": day}, headers=h)
    assert r.status_code == 200 and r.json()["items"]
    assert (await client.get(url, params={"from": "yesterday"}, headers=h)).status_code == 422
    r = await client.get(f"{API}/companies/{co['code']}/reconcile",
                         params={"from": "2026-01-01", "to": "2025-01-01"}, headers=h)  # fmt: skip
    assert r.status_code == 422


# ========================================================== revenue board ==
async def test_the_revenue_board_on_fixed_data(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    lsid = await ledger_source_row(su, co["id"])
    # months M0..M5 (M5 is "now"'s month); a 30-day plan starting on the 1st of each month
    now = datetime(2026, 7, 20, tzinfo=UTC)
    rows = []

    def month(i: int) -> datetime:
        return datetime(2026, 1 + i, 1, tzinfo=UTC)

    def plan(ext: str, who: str, amount: str, i: int) -> dict[str, Any]:
        start = month(i)
        end = month(i + 1)
        return {**row(ext, who, amount, bsc_hash(), start), "period_end": iso(end)}

    # ali pays every month (Jan..Jul); sara Jan..Mar then leaves; reza from Mar on
    for i in range(7):
        rows.append(plan(f"ali-{i}", "ali", "10", i))
    for i in range(3):
        rows.append(plan(f"sara-{i}", "sara", "20", i))
    for i in range(2, 7):
        rows.append(plan(f"reza-{i}", "reza", "30", i))
    await ingest(hub, lsid, rows)
    # everything arrived on chain
    await su.execute(
        "UPDATE money.payments SET status = 'matched', chain_amount = amount_usdt WHERE company_id = $1",
        co["id"],
    )
    await su.execute(
        """INSERT INTO growth.ad_daily (company_id, platform, campaign_id, day, spend)
           VALUES ($1, 'google_ads', 'c1', '2026-06-10', 45)""",
        co["id"],
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        b = await RB.build(tx, co["id"], co["code"], now=now)
    by = {m.month: m for m in b.months}
    assert list(by) == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]
    assert by["2026-01"].mrr_usdt == Decimal("30.000000") and by["2026-01"].active == 2
    assert by["2026-01"].new_customers == 2 and by["2026-03"].new_customers == 1
    assert by["2026-03"].mrr_usdt == Decimal("60.000000") and by["2026-03"].active == 3
    # sara's coverage ended on Apr 1: churned in April (the month her last period ended at its end)
    assert by["2026-04"].churned == 1 and sum(m.churned for m in b.months) == 1
    assert by["2026-04"].arpu_usdt == Decimal("20.000000")
    # churn over the last 3 complete months (Apr, May, Jun): 1 churned / 6 active
    assert b.churn_rate == round(1 / 6, 4)
    assert b.ltv_usdt == (Decimal(120) / 6 / Decimal(repr(round(1 / 6, 4)))).quantize(RB.Q6)
    # CAC of June: 45 USD of ads / 0 new customers -> none; payback none
    assert b.cac_usdt is None and b.payback_months is None
    jan = next(c for c in b.cohorts if c.start_month == "2026-01")
    assert jan.size == 2 and jan.retained[:4] == [100.0, 100.0, 100.0, 50.0]
    # six complete months: a forecast with a band, and a basis that says so
    assert len(b.forecast) == 3 and b.forecast[0].month == "2026-07"
    assert all(f.low <= f.mrr_usdt <= f.high for f in b.forecast)
    assert "هولت" in b.forecast_basis_fa
    assert b.roi.revenue_usdt == sum((m.mrr_usdt for m in b.months), Decimal(0))
    assert b.roi.cost_usd.ads == Decimal("45.000000") and b.roi.cost_usd.servers is None
    assert {c.kind for c in b.cost_per_output} == {"line_run", "deliverable", "order"}
    # with fewer than 4 complete months there is no forecast
    async with hub.db.tx(await hub.companies.ids()) as tx:
        early = await RB.build(tx, co["id"], co["code"], now=datetime(2026, 3, 15, tzinfo=UTC))
    assert (
        early.forecast == []
        and "۴" not in early.forecast_basis_fa
        and "4" in early.forecast_basis_fa
    )
    assert early.ltv_usdt is None  # fewer than 3 complete months


async def test_cac_and_payback(hub: Hub, new_company: Callable[..., Any], su: Any) -> None:
    co = await new_company()
    lsid = await ledger_source_row(su, co["id"])
    may = datetime(2026, 5, 3, tzinfo=UTC)
    await ingest(
        hub, lsid, [row("n-1", "a", "20", bsc_hash(), may), row("n-2", "b", "20", bsc_hash(), may)]
    )
    await su.execute("UPDATE money.payments SET status = 'matched', chain_amount = amount_usdt "
                     "WHERE company_id = $1", co["id"])  # fmt: skip
    await su.execute(
        """INSERT INTO growth.ad_daily (company_id, platform, campaign_id, day, spend)
           VALUES ($1, 'meta_ads', 'c9', '2026-05-04', 30)""",
        co["id"],
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        b = await RB.build(tx, co["id"], co["code"], now=datetime(2026, 6, 10, tzinfo=UTC))
    may_row = next(m for m in b.months if m.month == "2026-05")
    assert may_row.new_customers == 2
    assert b.cac_usdt == Decimal("15.000000")
    assert b.payback_months == round(15 / float(may_row.arpu_usdt or 1), 2)


async def test_the_board_route_and_the_summary_by_source(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any],
    new_company: Callable[..., Any], su: Any,
) -> None:  # fmt: skip
    co = await new_company()
    lsid = await ledger_source_row(su, co["id"])
    paid = datetime.now(UTC) - timedelta(days=2)
    await ingest(hub, lsid, [row("B-1", "a", "12.5", bsc_hash(), paid),
                             row("B-2", "b", None, None, paid, kind="store")])  # fmt: skip
    await su.execute("UPDATE money.payments SET status = 'matched', chain_amount = amount_usdt "
                     "WHERE company_id = $1 AND kind = 'crypto'", co["id"])  # fmt: skip
    h = owner_session["headers"]
    r = await client.get(f"{API}/revenue/board", params={"company": co["code"]}, headers=h)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["company"] == co["code"] and b["period"] == "month" and b["months"]
    assert isinstance(b["months"][-1]["mrr_usdt"], str)  # money as a decimal string (§1)
    assert (await client.get(f"{API}/revenue/board", headers=h)).json()["company"] is None
    assert (
        await client.get(f"{API}/revenue/board", params={"company": "NOPE1"}, headers=h)
    ).status_code == 404
    r = await client.get(
        f"{API}/revenue/summary", params={"period": "week", "company": co["code"]}, headers=h
    )
    assert r.status_code == 200, r.text
    src = {s["company"]: s for s in r.json()["by_source"]}
    assert Decimal(src[co["code"]]["payments_usdt"]) == Decimal("12.5")
    assert (
        src[co["code"]]["store_payments"] == 1 and Decimal(src[co["code"]]["affiliate_usdt"]) == 0
    )


# ============================================================ permissions ==
async def test_the_company_s_ceo_and_fin_read_their_own_company_only(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any],
    new_company: Callable[..., Any], su: Any,
) -> None:  # fmt: skip
    a, b = await new_company(), await new_company()
    lsid = await ledger_source_row(su, a["id"])
    await ingest(hub, lsid, [row("Q-1", "x", "7", bsc_hash(), datetime.now(UTC))])
    url = "/internal/v1/money/read"
    for code in (f"{a['code']}-CEO", f"{a['code']}-FIN-MGR"):
        hh = await agent_headers(code)
        r = await client.post(url, json={"what": "payments"}, headers=hh)
        assert r.status_code == 200, r.text
        assert [p["ext_id"] for p in r.json()["items"]] == ["Q-1"]
        for what in ("sources", "reconcile", "board", "leads", "pipeline", "affiliate_gaps"):
            assert (await client.post(url, json={"what": what}, headers=hh)).status_code == 200, (
                what
            )
        r = await client.post(url, json={"what": "payments", "company": b["code"]}, headers=hh)
        assert (r.status_code, r.json()["code"]) == (403, "policy_denied")
    r = await client.post(url, json={"what": "payments", "limit": 201},
                          headers=await agent_headers(f"{a['code']}-CEO"))  # fmt: skip
    assert r.status_code == 422
    tech = await agent_headers(f"{a['code']}-TECH-MGR")
    assert (await client.post(url, json={"what": "payments"}, headers=tech)).status_code == 403
    sales = await agent_headers(f"{a['code']}-SALES-MGR")
    assert (await client.post(url, json={"what": "leads"}, headers=sales)).status_code == 200
    assert (await client.post(url, json={"what": "board"}, headers=sales)).status_code == 403
    adv = await agent_headers("HQ-ADV")
    r = await client.post(url, json={"what": "board", "company": b["code"]}, headers=adv)
    assert r.status_code == 200 and r.json()["company"] == b["code"]
    assert (
        await client.post(url, json={"what": "payments", "company": a["code"]}, headers=adv)
    ).status_code == 403
    # agents never reach the owner's routes
    r = await client.get(
        f"{API}/companies/{a['code']}/payments", headers=await agent_headers(f"{a['code']}-CEO")
    )
    assert r.status_code in (401, 403)


async def test_nothing_runs_while_the_holding_is_locked(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    from .p10_fakes import holding_switch

    async with holding_switch(su, "engaged"):
        assert (await MJ.read_due(hub)).get("locked") == 1
        assert (await MJ.reconcile_all(hub)).get("locked") == 1
        assert (await MJ.weekly(hub)).get("locked") == 1


async def test_the_owner_s_weekly_line(hub: Hub, new_company: Callable[..., Any], su: Any) -> None:
    co = await new_company()
    lsid = await ledger_source_row(su, co["id"])
    await ingest(hub, lsid, [row("W-1", "x", "7", bsc_hash(), datetime.now(UTC))])
    out = await MJ.weekly(hub)
    assert out["sent"] == 1
    n = await su.fetchrow("SELECT level, domain, body_fa, owner_visible FROM notify.notifications WHERE id = $1",
                          UUID(out["id"]))  # fmt: skip
    assert n["level"] == "report" and n["domain"] == "revenue" and n["owner_visible"]
    assert n["body_fa"].startswith("پرداخت‌ها:")


def test_the_schedules_and_the_stream_topic() -> None:
    from hq_api import events
    from hq_api.worker import schedules as S

    ids = {d.id: d for d in S.p24m_fixed()}
    assert set(ids) == set(S.P24M) and set(S.P24M) <= set(S.FIXED)
    assert ids[S.USAGE_DAILY].args == ("day",) and ids[S.USAGE_WEEKLY].args == ("week",)
    cal = ids[S.USAGE_DAILY].spec.calendars[0]
    assert (cal.hour[0].start, cal.minute[0].start, ids[S.USAGE_DAILY].spec.time_zone_name) == (
        7, 55, "Asia/Tehran",
    )  # fmt: skip
    wk = ids[S.USAGE_WEEKLY].spec.calendars[0]
    assert (wk.day_of_week[0].start, wk.hour[0].start, wk.minute[0].start) == (6, 9, 0)
    assert set(events.TOPICS["money"]) >= {"payment.", "lead.", "usage.", "journey."}
