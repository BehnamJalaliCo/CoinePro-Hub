"""⟨0.3.0⟩ contract §33.2: the `ledger` job and `hq-runner ledger-check`.

The query, the DSN and the salt live only on the server, in files of mode
600; the job binds `:since`, runs read-only with a statement timeout, checks
the output columns against ledger_v1 and hashes the customer. A real
Postgres (the services test environment) checks the read-only role and the
privileges check end to end; without it those tests are skipped."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from conftest import FakeHub, make_route, run
from test_run import drive

from hq_runner import cli, ledger
from hq_runner.config import Config
from hq_runner.runner import Runner

SALT = "s" * 32
DSN = "postgresql://hq_ledger_ro:Sup3rS3cretPw@db.internal:5432/payments"
SQL = (
    "SELECT id AS ext_id, user_id AS customer, plan, amount AS amount_usdt, net AS network,\n"
    "       tx AS tx_hash, paid AS paid_at, ps AS period_start, pe AS period_end, k AS kind\n"
    "FROM payments WHERE (CAST(:since AS timestamptz) IS NULL OR paid > CAST(:since AS timestamptz));\n"
)
T0 = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)


def write_files(
    base: Path, env: str | None = None, sql: str | None = SQL, mode: int = 0o600
) -> None:
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, text in (
        (
            "ledger.env",
            env if env is not None else f"HQ_LEDGER_DSN={DSN}\nHQ_LEDGER_SALT='{SALT}'\n",
        ),
        ("ledger.sql", sql),
    ):
        if text is None:
            continue
        p = base / name
        p.write_text(text, encoding="utf-8")
        os.chmod(p, mode)


# ------------------------------------------------------------ a fake driver --
class Attr:
    def __init__(self, name: str) -> None:
        self.name = name


class Rec(dict[str, Any]):
    pass


class FakeTx:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    async def start(self) -> None:
        self.conn.log.append("BEGIN READ ONLY" if self.conn.readonly else "BEGIN")

    async def rollback(self) -> None:
        self.conn.log.append("ROLLBACK")


class FakeStmt:
    def __init__(self, conn: FakeConn, sql: str) -> None:
        self.conn, self.sql = conn, sql

    def get_attributes(self) -> list[Attr]:
        return [Attr(n) for n in self.conn.columns]

    async def fetch(self, *params: Any) -> list[Rec]:
        self.conn.params = params
        since, limit = params
        rows = [r for r in self.conn.rows if since is None or r["paid_at"] > since]
        rows.sort(key=lambda r: (r["paid_at"], r["ext_id"]))
        return [Rec(r) for r in rows[:limit]]


class FakeConn:
    def __init__(self, rows: list[dict[str, Any]], columns: tuple[str, ...] = ledger.COLUMNS):
        self.rows, self.columns = rows, columns
        self.log: list[str] = []
        self.params: tuple[Any, ...] = ()
        self.readonly = False
        self.closed = False
        self.writable = {"powerful": False, "db_create": False, "schema_create": 0, "writable": 0}

    def transaction(self, readonly: bool = False) -> FakeTx:
        self.readonly = readonly
        return FakeTx(self)

    async def execute(self, sql: str) -> None:
        self.log.append(sql)

    async def prepare(self, sql: str) -> FakeStmt:
        self.log.append(sql)
        return FakeStmt(self, sql)

    async def fetchval(self, sql: str) -> int:
        return 1

    async def fetchrow(self, sql: str) -> dict[str, Any]:
        return self.writable

    async def close(self) -> None:
        self.closed = True


def payment(i: int, at: datetime, **extra: Any) -> dict[str, Any]:
    return {
        "ext_id": f"P{i:04d}",
        "customer": 1000 + i,
        "plan": "pro",
        "amount_usdt": Decimal("49.990000"),
        "network": "bsc_usdt",
        "tx_hash": f"0x{i:064x}",
        "paid_at": at,
        "period_start": at.date(),
        "period_end": (at + timedelta(days=30)).date(),
        "kind": "crypto",
        **extra,
    }


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> list[FakeConn]:
    made: list[FakeConn] = []
    rows = [payment(i, T0 + timedelta(hours=i)) for i in range(5)]

    async def connect(lc: ledger.LedgerConfig) -> FakeConn:
        assert lc.dsn == DSN and lc.salt == SALT
        conn = FakeConn(list(made[0].rows) if made else rows)
        made.append(conn)
        return conn

    monkeypatch.setattr(ledger, "connect", connect)
    return made


def ledger_job(jid: str, **args: Any) -> dict[str, Any]:
    return {"id": jid, "kind": "ledger", "args": {"contract": "ledger_v1", **args}}


def drive_one(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, job: dict[str, Any]
) -> dict[str, Any]:
    fake_hub.jobs.append(job)
    runner = Runner(cfg, make_route(fake_hub), cfg_path=cfg_path, persist_state=False)
    run(drive(runner, lambda: job["id"] in fake_hub.results))
    return fake_hub.results[job["id"]]


# --------------------------------------------------------------- the job --
def test_the_ledger_job_reads_hashes_and_pages(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, fake_db: list[FakeConn]
) -> None:
    write_files(cfg_path.parent)
    res = drive_one(fake_hub, cfg, cfg_path, ledger_job("l1", since=None, limit=3))
    assert res["exit_code"] == 0, res
    out = res["data"]
    assert out["contract"] == "ledger_v1" and out["count"] == 3 and out["more"] is True
    row = out["rows"][0]
    assert list(row) == list(ledger.COLUMNS)
    assert row["customer"] == hmac.new(SALT.encode(), b"1000", hashlib.sha256).hexdigest()
    assert row["amount_usdt"] == "49.990000" and row["paid_at"] == T0.isoformat()
    assert row["period_start"] == "2026-11-01" and row["period_end"] == "2026-12-01"
    assert out["next_since"] == (T0 + timedelta(hours=2)).isoformat()
    conn = fake_db[0]
    # One statement, `:since` bound as $1 (never in the text), read only, with a timeout.
    assert conn.log[0] == "BEGIN READ ONLY"
    assert conn.log[1] == f"SET LOCAL statement_timeout = {ledger.STATEMENT_TIMEOUT_MS}"
    query = next(s for s in conn.log if s.startswith("SELECT * FROM ("))
    assert ":since" not in query and "CAST($1 AS timestamptz)" in query and ";" not in query
    assert query.endswith("ORDER BY paid_at, ext_id LIMIT $2")
    assert conn.params == (None, 4) and conn.log[-1] == "ROLLBACK" and conn.closed
    # Nothing secret in what reached the hub.
    sent = json.dumps(fake_hub.requests, default=str)
    assert "Sup3rS3cretPw" not in sent and SALT not in sent
    assert all(len(r["customer"]) == 64 and r["customer"] != "1000" for r in out["rows"])

    # The next page from the cursor.
    res = drive_one(fake_hub, cfg, cfg_path, ledger_job("l2", since=out["next_since"], limit=3))
    out2 = res["data"]
    assert [r["ext_id"] for r in out2["rows"]] == ["P0003", "P0004"] and out2["more"] is False
    assert fake_db[1].params[0] == T0 + timedelta(hours=2)
    # Nothing new: the cursor stays where it was.
    res = drive_one(fake_hub, cfg, cfg_path, ledger_job("l3", since=out2["next_since"]))
    assert res["data"]["rows"] == [] and res["data"]["next_since"] == out2["next_since"]


def test_a_page_never_splits_rows_of_one_time() -> None:
    same = T0 + timedelta(hours=1)
    rows = [payment(0, T0), payment(1, same), payment(2, same), payment(3, same)]
    kept, more = ledger.page(rows, 2)
    assert [r["ext_id"] for r in kept] == ["P0000"] and more  # P0001 waits for the next page
    kept, more = ledger.page(rows[1:], 2)
    assert len(kept) == 2 and more  # all of one time: nothing is dropped for ever
    kept, more = ledger.page(rows, 10)
    assert len(kept) == 4 and not more


@pytest.mark.parametrize(
    ("columns", "says"),
    [
        (ledger.COLUMNS[:-1], "missing: kind"),
        ((*ledger.COLUMNS, "email"), "1 extra column(s)"),
        ((*ledger.COLUMNS[:-1], "plan"), "missing: kind"),
    ],
)
def test_the_output_columns_must_be_exactly_the_contracts(
    fake_hub: FakeHub,
    cfg: Config,
    cfg_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    columns: tuple[str, ...],
    says: str,
) -> None:
    write_files(cfg_path.parent)

    async def connect(lc: ledger.LedgerConfig) -> FakeConn:
        return FakeConn([payment(1, T0)], columns)

    monkeypatch.setattr(ledger, "connect", connect)
    res = drive_one(fake_hub, cfg, cfg_path, ledger_job("c1"))
    assert res["exit_code"] == ledger.EXIT_CONFIG and "ledger_v1" in res["summary_fa"]
    assert says in res["summary_fa"] and "data" not in res
    assert "email" not in res["summary_fa"]  # an extra column's name never leaves the server


@pytest.mark.parametrize(
    ("setup", "says"),
    [
        ("missing_env", "ledger.env"),
        ("missing_sql", "ledger.sql"),
        ("open_mode", "600"),
        ("no_dsn", "HQ_LEDGER_DSN"),
        ("short_salt", "HQ_LEDGER_SALT"),
        ("no_since", ":since"),
        ("empty_sql", "خالی"),
        ("symlink", "پیوند"),
    ],
)
def test_the_job_fails_with_a_plain_reason_and_no_secret(
    fake_hub: FakeHub,
    cfg: Config,
    cfg_path: Path,
    fake_db: list[FakeConn],
    tmp_path: Path,
    setup: str,
    says: str,
) -> None:
    base = cfg_path.parent
    if setup == "missing_env":
        write_files(base, env=None)
        (base / "ledger.env").unlink()
    elif setup == "missing_sql":
        write_files(base, sql=None)
    elif setup == "open_mode":
        write_files(base, mode=0o644)
    elif setup == "no_dsn":
        write_files(base, env=f"HQ_LEDGER_SALT={SALT}\n")
    elif setup == "short_salt":
        write_files(base, env=f"export HQ_LEDGER_DSN={DSN}\nHQ_LEDGER_SALT=abc\n")
    elif setup == "no_since":
        write_files(base, sql="SELECT 1;")
    elif setup == "empty_sql":
        write_files(base, sql=" ;\n")
    elif setup == "symlink":
        write_files(base, sql=None)
        real = tmp_path / "elsewhere.sql"
        real.write_text(SQL, encoding="utf-8")
        os.chmod(real, 0o600)
        (base / "ledger.sql").symlink_to(real)
    res = drive_one(fake_hub, cfg, cfg_path, ledger_job("e1"))
    assert res["exit_code"] == ledger.EXIT_CONFIG and says in res["summary_fa"], res
    assert not fake_db  # nothing was connected
    sent = json.dumps(fake_hub.requests, default=str)
    assert "Sup3rS3cretPw" not in sent and SALT not in sent


@pytest.mark.parametrize(
    ("args", "says"),
    [
        ({"contract": "ledger_v2"}, "ledger_v1"),
        ({"contract": "ledger_v1", "limit": 5001}, "5000"),
        ({"contract": "ledger_v1", "limit": True}, "5000"),
        ({"contract": "ledger_v1", "since": "yesterday"}, "ISO 8601"),
        ({"contract": "ledger_v1", "since": 5}, "ISO 8601"),
    ],
)
def test_bad_arguments_are_refused(
    fake_hub: FakeHub,
    cfg: Config,
    cfg_path: Path,
    fake_db: list[FakeConn],
    args: dict[str, Any],
    says: str,
) -> None:
    write_files(cfg_path.parent)
    res = drive_one(fake_hub, cfg, cfg_path, {"id": "a1", "kind": "ledger", "args": args})
    assert res["exit_code"] == 2 and says in res["summary_fa"] and not fake_db


def test_a_database_error_says_its_code_never_its_text(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_files(cfg_path.parent)

    class InsufficientPrivilegeError(Exception):
        sqlstate = "42501"

    class Failing(FakeConn):
        async def prepare(self, sql: str) -> FakeStmt:
            raise InsufficientPrivilegeError("permission denied for table secret_payments")

    async def connect(lc: ledger.LedgerConfig) -> FakeConn:
        return Failing([])

    monkeypatch.setattr(ledger, "connect", connect)
    res = drive_one(fake_hub, cfg, cfg_path, ledger_job("d1"))
    assert res["exit_code"] == ledger.EXIT_QUERY
    assert "42501 InsufficientPrivilegeError" in res["summary_fa"]
    assert "secret_payments" not in json.dumps(fake_hub.requests, default=str)


def test_units() -> None:
    assert ledger.parse_env('# c\nexport A=1\nB = "two"\n\nC\n') == {"A": "1", "B": "two"}
    assert ledger.prepare_sql("x = :since AND y::since_t = :since_x AND :since;") == (
        "x = $1 AND y::since_t = :since_x AND $1"
    )
    assert ledger.pseudonym(SALT, None) is None
    assert ledger.plain(datetime(2026, 1, 1, 12)) == "2026-01-01T12:00:00+00:00"
    assert ledger.plain(1.5) == "1.5" and ledger.plain(uuid.UUID(int=1)).endswith("1")
    assert repr(ledger.LedgerConfig(DSN, SALT, SQL)) == "LedgerConfig(<hidden>)"
    assert ledger.parse_since("2026-11-01T10:00:00") == T0


# ------------------------------------------------------------- ledger-check --
def test_ledger_check_prints_ok_or_the_reason(
    cfg_path: Path, fake_db: list[FakeConn], monkeypatch: pytest.MonkeyPatch
) -> None:
    write_files(cfg_path.parent)
    out = io.StringIO()
    assert cli.ledger_check(cfg_path, out) == 0 and out.getvalue() == "ok\n"

    async def writable(lc: ledger.LedgerConfig) -> FakeConn:
        conn = FakeConn([])
        conn.writable = {**conn.writable, "writable": 3}
        return conn

    monkeypatch.setattr(ledger, "connect", writable)
    out = io.StringIO()
    assert cli.ledger_check(cfg_path, out) == 1
    assert out.getvalue() == "error: the ledger role can write: write access to a table or view\n"

    os.chmod(cfg_path.parent / "ledger.env", 0o640)
    out = io.StringIO()
    assert cli.ledger_check(cfg_path, out) == 1
    assert "must be mode 600 (it is 640)" in out.getvalue()
    assert "Sup3rS3cretPw" not in out.getvalue()


# --------------------------------------------------- against a real Postgres --
PG_HOST = os.environ.get("TEST_DB_HOST")
needs_pg = pytest.mark.skipif(
    not (PG_HOST and os.environ.get("POSTGRES_PASSWORD")), reason="no test Postgres"
)


async def _admin(db: str = "postgres") -> Any:
    import asyncpg

    return await asyncpg.connect(
        host=PG_HOST, user="postgres", password=os.environ["POSTGRES_PASSWORD"], database=db
    )


@pytest.fixture
def real_db() -> Any:
    """A throwaway database with a ledger table, a SELECT-only role and a
    role that can write; dropped afterwards."""
    db = f"ledger_{uuid.uuid4().hex[:8]}"
    ro_pw, rw_pw = uuid.uuid4().hex, uuid.uuid4().hex

    async def up() -> None:
        a = await _admin()
        await a.execute(f"CREATE DATABASE {db}")
        await a.execute(f"CREATE ROLE {db}_ro LOGIN PASSWORD '{ro_pw}'")
        await a.execute(f"CREATE ROLE {db}_rw LOGIN PASSWORD '{rw_pw}'")
        await a.close()
        c = await _admin(db)
        await c.execute(
            """REVOKE CREATE ON SCHEMA public FROM PUBLIC;
               CREATE TABLE pay (id int PRIMARY KEY, uid text, plan text, amount numeric(18, 6),
                                 net text, tx text, paid timestamptz, ps date, pe date, k text);"""
        )
        await c.executemany(
            "INSERT INTO pay VALUES ($1, $2, 'pro', 49.99, 'trc20_usdt', $3, $4, $5, $6, 'crypto')",
            [
                (i, f"u{i}", f"tx{i}", T0 + timedelta(minutes=i), T0.date(), T0.date())
                for i in range(1, 8)
            ],
        )
        await c.execute(f"GRANT SELECT ON pay TO {db}_ro")
        await c.execute(f"GRANT SELECT, INSERT ON pay TO {db}_rw")
        await c.close()

    async def down() -> None:
        a = await _admin()
        await a.execute(f"DROP DATABASE IF EXISTS {db} WITH (FORCE)")
        await a.execute(f"DROP ROLE IF EXISTS {db}_ro")
        await a.execute(f"DROP ROLE IF EXISTS {db}_rw")
        await a.close()

    asyncio.run(up())
    yield {
        "ro": f"postgresql://{db}_ro:{ro_pw}@{PG_HOST}:5432/{db}",
        "rw": f"postgresql://{db}_rw:{rw_pw}@{PG_HOST}:5432/{db}",
        "secret": ro_pw,
    }
    asyncio.run(down())


REAL_SQL = (
    "SELECT id::text AS ext_id, uid AS customer, plan, amount AS amount_usdt, net AS network,\n"
    "       tx AS tx_hash, paid AS paid_at, ps AS period_start, pe AS period_end, k AS kind\n"
    "FROM pay WHERE (CAST(:since AS timestamptz) IS NULL OR paid > CAST(:since AS timestamptz))\n"
)


@needs_pg
def test_real_ledger_read_and_check(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, real_db: dict[str, str]
) -> None:
    base = cfg_path.parent
    write_files(base, env=f"HQ_LEDGER_DSN={real_db['ro']}\nHQ_LEDGER_SALT={SALT}\n", sql=REAL_SQL)
    out = io.StringIO()
    assert cli.ledger_check(cfg_path, out) == 0, out.getvalue()
    assert out.getvalue().endswith("ok\n")
    res = drive_one(fake_hub, cfg, cfg_path, ledger_job("r1", since=None, limit=5))
    data = res["data"]
    assert res["exit_code"] == 0 and data["count"] == 5 and data["more"] is True
    assert data["rows"][0]["customer"] == hmac.new(SALT.encode(), b"u1", hashlib.sha256).hexdigest()
    assert data["rows"][0]["amount_usdt"] == "49.990000"
    res = drive_one(fake_hub, cfg, cfg_path, ledger_job("r2", since=data["next_since"], limit=5))
    assert [r["ext_id"] for r in res["data"]["rows"]] == ["6", "7"]
    assert real_db["secret"] not in json.dumps(fake_hub.requests, default=str)

    # A query that writes is stopped by the READ ONLY transaction (the role can, here).
    write_files(
        base,
        env=f"HQ_LEDGER_DSN={real_db['rw']}\nHQ_LEDGER_SALT={SALT}\n",
        sql="WITH w AS (INSERT INTO pay (id) VALUES (99) RETURNING 1) " + REAL_SQL,
    )
    res = drive_one(fake_hub, cfg, cfg_path, ledger_job("r3"))
    assert res["exit_code"] == ledger.EXIT_QUERY
    # ledger-check refuses the role that can write.
    out = io.StringIO()
    assert cli.ledger_check(cfg_path, out) == 1
    assert "can write: write access to a table or view" in out.getvalue()
