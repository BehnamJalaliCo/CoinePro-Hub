"""⟨1.15⟩ Prompt 24 (contract §33.2): crypto payments, read and reconciled. The sources, the
ledger's output contract and the read of a company's own records.

What the companies do (review of 2026-11-05): users pay USDT on chain to the company's public
wallet and submit the transaction hash; there is no processor and no webhook. The hub reads two
independent sources and reconciles them (payments_reconcile.py):

- a `ledger` source: the company's own records, through its runner (a `ledger` job, §26). The
  query lives on the company server; the hub holds only the OUTPUT contract
  (seed/payments/ledger_v1.yaml) and validates every returned row against it. One broken row
  refuses the whole batch: nothing of it is stored and the source shows a plain Persian reason.
- a `chain` source: a public address on BSC or TRON, read through egress (payments_chain.py).

Money is read, never moved: nothing here approves, rejects, refunds or extends anything in a
company system, signs a transaction or holds a key.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import yaml
from pydantic import Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import servers as SV
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import CODE, Model

log = logging.getLogger("hq_api.payments")

SEED = Path(__file__).resolve().parents[3] / "seed" / "payments"
SERVICE = Principal(kind="service", code="money", role="service")
Network = Literal["bsc_usdt", "trc20_usdt"]
SourceKind = Literal["ledger", "chain"]
Status = Literal["matched", "ledger_only", "chain_only", "amount_mismatch", "pending_chain"]
LEDGER_ADAPTER = "ledger_v1"
CHAIN_ADAPTER = "chain-read"
STATUSES = ("matched", "ledger_only", "chain_only", "amount_mismatch", "pending_chain")
ZERO = Decimal(0)


# ------------------------------------------------------------------- data --
@lru_cache(maxsize=1)
def cfg() -> dict[str, Any]:
    """seed/payments/chain.yaml: thresholds, lookbacks and the reconcile numbers (data)."""
    doc = yaml.safe_load((SEED / "chain.yaml").read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return doc


@lru_cache(maxsize=1)
def contract() -> dict[str, Any]:
    """seed/payments/ledger_v1.yaml: the output contract of a company's ledger."""
    doc = yaml.safe_load((SEED / "ledger_v1.yaml").read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    assert doc.get("contract") == LEDGER_ADAPTER
    return doc


def networks() -> dict[str, dict[str, Any]]:
    n = cfg()["networks"]
    assert isinstance(n, dict)
    return n


def now() -> datetime:
    return datetime.now(UTC)


# ----------------------------------------------------------------- shapes --
class PayPaymentSource(Model):
    id: UUID
    company: str
    kind: SourceKind
    adapter: str
    network: Network | None = None
    address: str | None = None
    state: Literal["not_configured", "ok", "error"]
    last_read_at: datetime | None = None
    last_error_fa: str | None = None
    # additive: the source can be paused, and a ledger source can name its runner's server
    enabled: bool = True
    server: str | None = None


class PayPaymentSourceIn(Model):
    kind: SourceKind
    network: Network | None = None
    address: str | None = Field(default=None, min_length=20, max_length=80)
    server: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool = True


class PayPayment(Model):
    id: UUID
    company: str
    source: UUID
    ext_id: str
    customer: str | None = None
    plan: str | None = None
    amount_usdt: Decimal | None = None
    network: Network | None = None
    tx_hash: str | None = None
    paid_at: datetime
    period_start: datetime | None = None
    period_end: datetime | None = None
    status: Status
    checked_at: datetime
    # additive: the amount that reached the address, and a short Persian note
    chain_amount: Decimal | None = None
    note_fa: str | None = None


class PayReconcile(Model):
    company: str
    day: str
    ledger_count: int
    chain_count: int
    matched: int
    ledger_only: int
    chain_only: int
    amount_mismatch: int
    note_fa: str
    pending_chain: int = 0


class PayReadResult(Model):
    source: PayPaymentSource
    queued: bool = False
    transfers: int = 0
    payments: int = 0
    pages: int = 0


# ----------------------------------------------------------- the contract --
class LedgerBreak(ValueError):
    """A batch that does not keep ledger_v1: the whole batch is refused."""

    def __init__(self, reason_fa: str) -> None:
        super().__init__(reason_fa)
        self.reason_fa = reason_fa


@dataclass(frozen=True)
class LedgerRow:
    ext_id: str
    customer: str
    plan: str
    amount_usdt: Decimal | None
    network: str | None
    tx_hash: str | None
    paid_at: datetime
    period_start: datetime | None
    period_end: datetime | None
    kind: str


@dataclass(frozen=True)
class LedgerBatch:
    rows: list[LedgerRow]
    next_cursor: str | None
    has_more: bool


def _break(n: int | None, col: str | None, why: str) -> LedgerBreak:
    where = f"ردیف {n}، ستون {col}" if n is not None and col else "پاسخ دفتر"
    return LedgerBreak(
        f"{where}: با قرارداد ledger_v1 نمی‌خواند ({why}). هیچ‌چیز از این دسته ذخیره نشد."
    )


def _timestamp(text: str, n: int, col: str) -> datetime:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        raise _break(n, col, "زمان نادرست") from None


def _column(n: int, col: str, spec: dict[str, Any], value: Any) -> Any:
    """One value against its column spec (type, nullability, length, pattern, enum)."""
    if value is None:
        if not spec.get("nullable"):
            raise _break(n, col, "خالی")
        return None
    if not isinstance(value, str):
        raise _break(n, col, "باید متن باشد")  # a decimal is a string, never a float
    if len(value) > int(spec.get("max_length", 500)):
        raise _break(n, col, "بیش از حد بلند")
    if spec.get("pattern") and not re.fullmatch(spec["pattern"], value):
        raise _break(n, col, "قالب نادرست")
    if spec.get("enum") and value not in spec["enum"]:
        raise _break(n, col, "مقدار مجاز نیست")
    return value


def validate_batch(doc: Any) -> LedgerBatch:
    """The runner's answer against seed/payments/ledger_v1.yaml, or LedgerBreak."""
    spec = contract()
    if not isinstance(doc, dict) or doc.get("contract") != LEDGER_ADAPTER:
        raise _break(None, None, "قرارداد ledger_v1 نیست")
    rows = doc.get("rows")
    limit = int(spec["response"]["max_rows"])
    if not isinstance(rows, list) or len(rows) > limit:
        raise _break(None, None, f"rows باید فهرستی حداکثر {limit} ردیفی باشد")
    cursor = doc.get("next_cursor")
    cursor_spec = spec["response"]["next_cursor"]
    if cursor is not None and (
        not isinstance(cursor, str) or len(cursor) > cursor_spec["max_length"]
    ):
        raise _break(None, None, "next_cursor")
    has_more = doc.get("has_more", False)
    if not isinstance(has_more, bool):
        raise _break(None, None, "has_more")
    columns: dict[str, dict[str, Any]] = spec["columns"]
    out: list[LedgerRow] = []
    seen: set[str] = set()
    for n, raw in enumerate(rows, 1):
        if not isinstance(raw, dict) or set(raw) != set(columns):
            raise _break(n, "همه‌ی ستون‌ها", "ستون کم یا اضافه")
        v = {col: _column(n, col, columns[col], raw[col]) for col in columns}
        rules = spec["kinds"][v["kind"]]
        for col in rules.get("required", []):
            if v[col] is None:
                raise _break(n, col, "برای این نوع پرداخت لازم است")
        for col in rules.get("null", []):
            if v[col] is not None:
                raise _break(n, col, "برای این نوع پرداخت باید خالی باشد")
        if v["tx_hash"] is not None and not re.fullmatch(
            rules["tx_hash_by_network"][v["network"]], v["tx_hash"]
        ):
            raise _break(n, "tx_hash", "قالب هش این شبکه نیست")
        amount: Decimal | None = None
        if v["amount_usdt"] is not None:
            try:
                amount = Decimal(v["amount_usdt"])
            except InvalidOperation:  # (the pattern already refuses this)
                raise _break(n, "amount_usdt", "عدد نیست") from None
            if amount <= 0:
                raise _break(n, "amount_usdt", "باید بزرگ‌تر از صفر باشد")
        start = _timestamp(v["period_start"], n, "period_start") if v["period_start"] else None
        end = _timestamp(v["period_end"], n, "period_end") if v["period_end"] else None
        if (start is None) != (end is None):
            raise _break(n, "period_start", "هر دو ستون دوره یا هیچ‌کدام")
        if start is not None and end is not None and end <= start:
            raise _break(n, "period_end", "پایان دوره باید بعد از شروعش باشد")
        if v["ext_id"] in seen:
            raise _break(n, "ext_id", "تکراری در همین دسته")
        seen.add(v["ext_id"])
        out.append(
            LedgerRow(
                ext_id=v["ext_id"],
                customer=v["customer"],
                plan=v["plan"],
                amount_usdt=amount,
                network=v["network"],
                tx_hash=v["tx_hash"].lower() if v["tx_hash"] else None,
                paid_at=_timestamp(v["paid_at"], n, "paid_at"),
                period_start=start,
                period_end=end,
                kind=v["kind"],
            )
        )
    return LedgerBatch(out, cursor, has_more)


# ---------------------------------------------------------------- sources --
SOURCE_SQL = """
    SELECT s.*, c.code AS company, sv.name AS server_name
    FROM money.payment_sources s JOIN core.companies c ON c.id = s.company_id
    LEFT JOIN infra.servers sv ON sv.id = s.server_id
"""


def render_source(r: dict[str, Any]) -> PayPaymentSource:
    return PayPaymentSource(
        id=r["id"],
        company=r["company"],
        kind=r["kind"],
        adapter=r["adapter"],
        network=r["network"],
        address=r["address"],
        state=r["state"],
        last_read_at=r["last_read_at"],
        last_error_fa=r["last_error_fa"],
        enabled=r["enabled"],
        server=r.get("server_name"),
    )


def render_payment(r: dict[str, Any]) -> PayPayment:
    return PayPayment(
        id=r["id"],
        company=r["company"],
        source=r["source_id"],
        ext_id=r["ext_id"],
        customer=r["customer"],
        plan=r["plan"],
        amount_usdt=r["amount_usdt"],
        network=r["network"],
        tx_hash=r["tx_hash"],
        paid_at=r["paid_at"],
        period_start=r["period_start"],
        period_end=r["period_end"],
        status=r["status"],
        checked_at=r["checked_at"],
        chain_amount=r["chain_amount"],
        note_fa=r["note_fa"],
    )


async def load_source(tx: Tx, source_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        SOURCE_SQL + " WHERE s.id = :id" + (" FOR UPDATE OF s" if lock else ""), id=source_id
    )


async def list_sources(tx: Tx, company_id: UUID) -> list[dict[str, Any]]:
    return await tx.all(
        SOURCE_SQL
        + " WHERE s.company_id = :co ORDER BY s.kind, s.network NULLS FIRST, s.created_at",
        co=company_id,
    )


def valid_address(network: str, address: str) -> bool:
    return bool(re.fullmatch(networks()[network]["address_pattern"], address))


async def paired_runner(tx: Tx, company_id: UUID, name: str | None = None) -> dict[str, Any] | None:
    """The company's runner server a ledger is read through: the named one, else the first
    online one, else the first paired one. None when no runner is paired."""
    if name:
        row = await tx.first(
            """SELECT id FROM infra.servers WHERE company_id = :co AND origin = 'attached'
                 AND lower(name) = lower(:n) AND state IS DISTINCT FROM 'revoked'""",
            co=company_id,
            n=name,
        )
    else:
        row = await tx.first(
            """SELECT id FROM infra.servers WHERE company_id = :co AND origin = 'attached'
                 AND state IN ('online', 'offline')
               ORDER BY (state = 'online') DESC, created_at LIMIT 1""",
            co=company_id,
        )
    return await SV.load_server(tx, row["id"]) if row else None


async def put_source(
    tx: Tx, company_id: UUID, company_code: str, body: PayPaymentSourceIn
) -> tuple[dict[str, Any], bool]:
    """Adds a source, or changes the one that is already there (a ledger source: the runner's
    server and whether it is on; a chain source: whether it is on). A ledger source needs the
    runner paired (§33.2)."""
    server_id: UUID | None = None
    if body.kind == "ledger":
        if body.network is not None or body.address is not None:
            raise ApiError(422, "validation_failed", fields={"address": "not for a ledger source"})
        runner = await paired_runner(tx, company_id, body.server)
        if runner is None:
            raise ApiError(
                409,
                "not_ready",
                "no paired runner",
                fields={"server": "no paired runner"},
                message_fa="برای خواندن دفتر شرکت، اول runner سرور شرکت باید جفت شود.",
            )
        server_id = runner["id"] if body.server else None
        existing = await tx.first(
            """SELECT id FROM money.payment_sources
               WHERE company_id = :co AND kind = 'ledger' AND adapter = :a""",
            co=company_id,
            a=LEDGER_ADAPTER,
        )
        if existing is None:
            row = await tx.one(
                """INSERT INTO money.payment_sources (company_id, kind, adapter, server_id, enabled)
                   VALUES (:co, 'ledger', :a, :sv, :en) RETURNING id""",
                co=company_id,
                a=LEDGER_ADAPTER,
                sv=server_id,
                en=body.enabled,
            )
        else:
            row = await tx.one(
                """UPDATE money.payment_sources SET server_id = :sv, enabled = :en, updated_at = now()
                   WHERE id = :id RETURNING id""",
                id=existing["id"],
                sv=server_id,
                en=body.enabled,
            )
        return await load_source(tx, row["id"]), existing is None
    if body.network is None or body.address is None:
        raise ApiError(
            422, "validation_failed", fields={"network": "required", "address": "required"}
        )
    if body.server is not None:
        raise ApiError(422, "validation_failed", fields={"server": "not for a chain source"})
    if not valid_address(body.network, body.address):
        raise ApiError(
            422,
            "validation_failed",
            fields={"address": "not an address of this network"},
            message_fa="نشانی کیف پول برای این شبکه درست نیست.",
        )
    address = body.address.lower() if body.network == "bsc_usdt" else body.address
    existing = await tx.first(
        """SELECT id FROM money.payment_sources
           WHERE company_id = :co AND kind = 'chain' AND network = :n AND address = :a""",
        co=company_id,
        n=body.network,
        a=address,
    )
    if existing is None:
        row = await tx.one(
            """INSERT INTO money.payment_sources (company_id, kind, adapter, network, address, enabled)
               VALUES (:co, 'chain', :ad, :n, :a, :en) RETURNING id""",
            co=company_id,
            ad=CHAIN_ADAPTER,
            n=body.network,
            a=address,
            en=body.enabled,
        )
    else:
        row = await tx.one(
            """UPDATE money.payment_sources SET enabled = :en, updated_at = now()
               WHERE id = :id RETURNING id""",
            id=existing["id"],
            en=body.enabled,
        )
    return await load_source(tx, row["id"]), existing is None


async def mark(
    tx: Tx, source: dict[str, Any], *, error_fa: str | None, read: bool, **cols: Any
) -> None:
    """A source after a read: ok (and when) or error (and why)."""
    sets = ["updated_at = now()"]
    params: dict[str, Any] = {"id": source["id"]}
    for key, value in cols.items():
        sets.append(f"{key} = :{key}")
        params[key] = value
    if error_fa is None:
        sets += ["state = 'ok'", "last_error_fa = NULL"]
        if read:
            sets.append("last_read_at = now()")
    else:
        sets += ["state = 'error'", "last_error_fa = :err"]
        params["err"] = error_fa[:500]
    await tx.exec(
        f"UPDATE money.payment_sources SET {', '.join(sets)} WHERE id = :id",  # noqa: S608 - names
        **params,
    )


# ----------------------------------------------------------------- ledger --
def version_ok(version: str | None, minimum: str) -> bool:
    def parts(v: str | None) -> tuple[int, ...]:
        return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3])

    return parts(version) >= parts(minimum)


async def ingest(tx: Tx, src: dict[str, Any], batch: LedgerBatch) -> int:
    """The validated rows into money.payments: one per company, source and ext_id. A row whose
    hash, amount or network changed is judged again; a store's in-app billing is counted, never
    reconciled. Returns the rows that were new."""
    new = 0
    for r in batch.rows:
        store = r.kind == "store"
        row = await tx.one(
            """INSERT INTO money.payments (company_id, source_id, ext_id, origin, kind, customer,
                   plan, amount_usdt, network, tx_hash, paid_at, period_start, period_end,
                   status, note_fa)
               VALUES (:co, :s, :e, 'ledger', :k, :cu, :pl, :am, :nw, :tx, :pa, :ps, :pe, :st, :nt)
               ON CONFLICT (company_id, source_id, ext_id) DO UPDATE SET
                   kind = EXCLUDED.kind, customer = EXCLUDED.customer, plan = EXCLUDED.plan,
                   amount_usdt = EXCLUDED.amount_usdt, network = EXCLUDED.network,
                   tx_hash = EXCLUDED.tx_hash, paid_at = EXCLUDED.paid_at,
                   period_start = EXCLUDED.period_start, period_end = EXCLUDED.period_end,
                   status = CASE WHEN (money.payments.tx_hash, money.payments.amount_usdt,
                                       money.payments.network, money.payments.kind)
                                      IS NOT DISTINCT FROM (EXCLUDED.tx_hash, EXCLUDED.amount_usdt,
                                                            EXCLUDED.network, EXCLUDED.kind)
                                 THEN money.payments.status ELSE EXCLUDED.status END
               RETURNING (xmax = 0) AS inserted""",
            co=src["company_id"],
            s=src["id"],
            e=r.ext_id,
            k=r.kind,
            cu=r.customer,
            pl=r.plan,
            am=r.amount_usdt,
            nw=r.network,
            tx=r.tx_hash,
            pa=r.paid_at,
            ps=r.period_start,
            pe=r.period_end,
            st="matched" if store else "pending_chain",
            nt="پرداخت درون‌برنامه‌ی فروشگاه؛ شمرده میشود، جمع نمیشود و با زنجیره تطبیق نمیشود."
            if store
            else None,
        )
        if row["inserted"]:
            new += 1
            if store:  # an in-app purchase is paid by the store: its lead is paid (§33.4)
                await _lead_paid(tx, src["company_id"], r.customer, None)
    return new


async def _lead_paid(
    tx: Tx, company_id: UUID, customer: str | None, amount: Decimal | None
) -> None:
    """§33.4: a payment of a pseudonym sets its lead `paid` (one is made when there is none). A
    lead that cannot be written never stops the payments (its own savepoint)."""
    if not customer:
        return
    from hq_api.domain import leads

    try:
        async with tx.conn.begin_nested():
            await leads.from_payment(tx, company_id, customer, amount)
    except ApiError as exc:
        log.warning("lead of a payment refused", extra={"code": exc.code})


async def collect(tx: Tx, src: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    """A finished `ledger` job of this source: validated against ledger_v1 and stored, the cursor
    moved (one broken row refuses the whole batch, with a plain reason on the source)."""
    out: dict[str, Any] = {"ingested": 0, "rows": 0, "error": None, "has_more": False}
    await tx.exec(
        "UPDATE money.payment_sources SET pending_job_id = NULL WHERE id = :id", id=src["id"]
    )
    if job["state"] != "done":
        why = "لغو شد" if job["state"] == "cancelled" else "شکست خورد"
        out["error"] = f"خواندن دفتر روی سرور شرکت {why}؛ runner و پرونده‌ی ledger.sql را ببین."
        await mark(tx, src, error_fa=out["error"], read=True)
        return out
    try:
        batch = validate_batch(job["result"])
    except LedgerBreak as b:
        out["error"] = b.reason_fa
        await mark(tx, src, error_fa=b.reason_fa, read=True)
        return out
    out["ingested"] = await ingest(tx, src, batch)
    out["rows"] = len(batch.rows)
    out["has_more"] = batch.has_more
    cursor = batch.next_cursor if batch.next_cursor is not None else src["cursor"]
    await mark(tx, src, error_fa=None, read=True, cursor=cursor)
    out["cursor"] = cursor
    return out


async def on_job_finished(tx: Tx, job: dict[str, Any]) -> None:
    """servers.finish calls this for a `ledger` job: the rows are stored at once (the next read
    then asks for the next page when there is one)."""
    src = await tx.first(SOURCE_SQL + " WHERE s.pending_job_id = :j FOR UPDATE OF s", j=job["id"])
    if src is None:
        return
    try:
        async with tx.conn.begin_nested():
            got = await collect(tx, src, job)
            if got["has_more"] and got["error"] is None:  # the next page at once
                await queue_ledger(tx, {**src, "cursor": got["cursor"]})
    except Exception:
        log.exception("ledger job could not be collected")
        return
    await emit_read(
        tx, src, rows=got["rows"], ingested=got["ingested"], error=got["error"] is not None
    )


async def read_ledger(tx: Tx, src: dict[str, Any]) -> dict[str, Any]:
    """One step of a ledger source: collect the finished job (validate it, store it, move the
    cursor) and queue the next one. Never waits for the runner. Returns what happened."""
    out: dict[str, Any] = {"ingested": 0, "queued": False, "error": None}
    if src["pending_job_id"]:
        job = await SV.load_job(tx, src["pending_job_id"])
        if job["state"] in SV.OPEN:
            out["waiting"] = True
            return out
        got = await collect(tx, src, job)
        out.update(ingested=got["ingested"], rows=got["rows"], error=got["error"])
        if got["error"] is not None or not got["has_more"]:
            return out
        src = {**src, "pending_job_id": None, "cursor": got["cursor"]}
    return {**out, **await queue_ledger(tx, src)}


async def queue_ledger(tx: Tx, src: dict[str, Any]) -> dict[str, Any]:
    """The next `ledger` job of this source on the company's runner (runner 0.3.0 or later):
    {queued, error}. A company locked (kill switch) refuses it (423 from servers)."""
    out: dict[str, Any] = {"queued": False, "error": None}
    conf = cfg()["read"]
    runner = await paired_runner(tx, src["company_id"], src.get("server_name"))
    if runner is None:
        out["error"] = "runner شرکت جفت نیست؛ دفتر پرداخت خوانده نمیشود."
        await mark(tx, src, error_fa=out["error"], read=False)
        return out
    if not version_ok(runner["runner_version"], conf["runner_min_version"]):
        out["error"] = (
            f"runner این سرور قدیمی است؛ خواندن دفتر نسخه‌ی {conf['runner_min_version']} به بالا میخواهد."
        )
        await mark(tx, src, error_fa=out["error"], read=False)
        return out
    job = await SV.create_job(
        tx,
        server=runner,
        kind="ledger",
        args={
            "contract": LEDGER_ADAPTER,
            "since_cursor": src["cursor"],
            "limit": int(conf["ledger_limit"]),
        },
        actor_kind=SERVICE.kind,
        actor_code=SERVICE.code,
        summary="خواندن دفتر پرداخت",
        timeout_s=int(conf["ledger_timeout_s"]),
    )
    await tx.exec(
        "UPDATE money.payment_sources SET pending_job_id = :j WHERE id = :id",
        id=src["id"],
        j=job["id"],
    )
    out["queued"] = True
    return out


async def emit_read(tx: Tx, src: dict[str, Any], **data: Any) -> None:
    await events.emit(
        tx,
        src["company"],
        "payment.read",
        str(src["id"]),
        {"source": str(src["id"]), "kind": src["kind"], **data},
    )


def company_code_arg(code: str) -> str:
    if not re.fullmatch(CODE, code):
        raise ApiError(422, "validation_failed", fields={"company": "a company code"})
    return code
