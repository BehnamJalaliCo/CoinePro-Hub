"""⟨0.3.0⟩ The `ledger` job (contract §33.2): the company's own payment
records, read on this server and nowhere else.

    args    {contract: "ledger_v1", since_cursor: str | null, limit: 1..500}
    result  data = {contract, rows: [{ext_id, customer, plan, amount_usdt,
                    network, tx_hash, paid_at, period_start, period_end, kind}],
                    next_cursor, has_more, count}

The shapes are the hub's output contract (apps/api/seed/payments/ledger_v1.yaml):
every value is a string or null, times are ISO 8601 UTC ending in Z, amounts
are decimal strings; the runner checks every row against the contract's rules
before anything leaves the server, and one broken row refuses the whole batch
(with the row and the column, never the value). `next_cursor` is opaque to
the hub (`t:<paid_at>`); a bare ISO time is also read as a cursor.

Everything the job needs lives on this server, in the runner's folder:

    ~/.config/hq-runner/ledger.env   mode 600: HQ_LEDGER_DSN (a SELECT-only role
                                     the company made), HQ_LEDGER_SALT
    ~/.config/hq-runner/ledger.sql   mode 600: the company's read-only query,
                                     written by this server's own Claude

No SQL text ever comes from the hub: the hub names the output contract and
the cursor, nothing else. The query runs as one statement inside a READ ONLY
transaction with a statement timeout, its one parameter `:since` bound (never
formatted into the text); its output columns must be exactly the contract's;
the `customer` column leaves this server only as HMAC-SHA256(salt, value) in
hex. A secret is never printed, logged or sent: a failure says only what to fix.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from hq_runner.config import config_path
from hq_runner.jobs import JobContext, JobError, JobResult

CONTRACT = "ledger_v1"
COLUMNS = (
    "ext_id",
    "customer",
    "plan",
    "amount_usdt",
    "network",
    "tx_hash",
    "paid_at",
    "period_start",
    "period_end",
    "kind",
)
MAX_LIMIT = 500  # the contract's response.max_rows
DEFAULT_LIMIT = 500
MAX_CURSOR = 200
CHECK_ROWS = 20  # ledger-check reads this many rows and checks them
CURSOR_PREFIX = "t:"
NETWORKS = ("bsc_usdt", "trc20_usdt")
KINDS = ("crypto", "store")
# The column rules of ledger_v1 (the hub's seed file is the source; these mirror it).
PATTERNS = {
    "ext_id": re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$"),
    "customer": re.compile(r"^[0-9a-f]{64}$"),
    "plan": re.compile(r"^[a-z0-9][a-z0-9_.-]{0,59}$"),
    "amount_usdt": re.compile(r"^[0-9]{1,12}(\.[0-9]{1,8})?$"),
}
TX_HASH = {
    "bsc_usdt": re.compile(r"^0x[0-9a-fA-F]{64}$"),
    "trc20_usdt": re.compile(r"^[0-9a-fA-F]{64}$"),
}
NULLABLE = ("amount_usdt", "network", "tx_hash", "period_start", "period_end")
STATEMENT_TIMEOUT_MS = 30_000
CONNECT_TIMEOUT_S = 10.0
MAX_SQL_BYTES = 64 * 1024
MIN_SALT_CHARS = 16
# `:since` as a whole token (never `::since`, never `:since_x`)
SINCE = re.compile(r"(?<![:\w]):since\b")
EXIT_CONFIG = 2
EXIT_QUERY = 1


class LedgerError(Exception):
    """A plain reason, in English for the terminal and Persian for the hub."""

    def __init__(self, en: str, fa: str, exit_code: int = EXIT_CONFIG) -> None:
        super().__init__(en)
        self.en = en
        self.fa = fa
        self.exit_code = exit_code


@dataclass(frozen=True)
class LedgerConfig:
    dsn: str
    salt: str
    sql: str

    def __repr__(self) -> str:  # never shows the DSN or the salt
        return "LedgerConfig(<hidden>)"


def folder(cfg_path: Path | None = None) -> Path:
    return (cfg_path or config_path()).parent


def _private_file(path: Path, what_fa: str) -> str:
    """The file's text, only when it is a regular file of this user with no
    access for anyone else (600 or stricter)."""
    try:
        st = path.lstat()
    except FileNotFoundError:
        raise LedgerError(
            f"{path} is missing", f"فایل {path.name} ({what_fa}) روی سرور نیست."
        ) from None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise LedgerError(
            f"{path} is not a regular file", f"{path.name} باید یک فایل معمولی باشد، نه پیوند."
        )
    if st.st_uid != os.getuid():
        raise LedgerError(
            f"{path} belongs to another user", f"{path.name} باید مال کاربر کاری runner باشد."
        )
    if st.st_mode & 0o077:
        raise LedgerError(
            f"{path} must be mode 600 (it is {oct(st.st_mode & 0o777)[2:]})",
            f"دسترسی {path.name} باید 600 باشد (الان {oct(st.st_mode & 0o777)[2:]} است).",
        )
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise LedgerError(f"{path} cannot be read", f"{path.name} خوانده نشد.") from None


def parse_env(text: str) -> dict[str, str]:
    """KEY=VALUE lines (`export`, quotes and comments allowed)."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def prepare_sql(text: str) -> str:
    """The query with `:since` as $1, one statement, ready to wrap."""
    sql = text.strip()
    while sql.endswith(";"):
        sql = sql[:-1].rstrip()
    if not sql:
        raise LedgerError("ledger.sql is empty", "ledger.sql خالی است.")
    if len(sql.encode()) > MAX_SQL_BYTES:
        raise LedgerError("ledger.sql is too long", "ledger.sql بیش از اندازه بلند است.")
    if not SINCE.search(sql):
        raise LedgerError(
            "ledger.sql must use the parameter :since",
            "ledger.sql باید پارامتر ‎:since را به کار ببرد (پرداخت‌های بعد از آن زمان).",
        )
    return SINCE.sub("$1", sql)


def load_config(cfg_path: Path | None = None) -> LedgerConfig:
    base = folder(cfg_path)
    env = parse_env(_private_file(base / "ledger.env", "تنظیمات دفتر"))
    dsn, salt = env.get("HQ_LEDGER_DSN", ""), env.get("HQ_LEDGER_SALT", "")
    if not dsn:
        raise LedgerError(
            "HQ_LEDGER_DSN is missing in ledger.env", "HQ_LEDGER_DSN در ledger.env نیست."
        )
    if len(salt) < MIN_SALT_CHARS:
        raise LedgerError(
            f"HQ_LEDGER_SALT is missing or shorter than {MIN_SALT_CHARS} characters",
            "HQ_LEDGER_SALT در ledger.env نیست یا خیلی کوتاه است "
            "(یک مقدار تصادفی ۳۲ بایتی بگذارید).",
        )
    sql = prepare_sql(_private_file(base / "ledger.sql", "پرس‌وجوی دفتر"))
    return LedgerConfig(dsn=dsn, salt=salt, sql=sql)


def pseudonym(salt: str, value: Any) -> str | None:
    if value is None:
        return None
    return hmac.new(salt.encode(), str(value).encode(), hashlib.sha256).hexdigest()


def plain(value: Any) -> Any:
    """A column value as JSON: ISO 8601 times, decimal strings."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=UTC)
        return dt.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        return format(Decimal(repr(value)), "f")
    return str(value)


def utc_z(value: Any) -> str | None:
    """A time (or a date: its midnight) as ISO 8601 UTC ending in Z."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("not a time") from None
    if isinstance(value, datetime):
        dt = (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day, tzinfo=UTC)
    else:
        raise ValueError("not a time")
    text = dt.strftime("%Y-%m-%dT%H:%M:%S")
    return text + (f".{dt.microsecond:06d}" if dt.microsecond else "") + "Z"


def amount_text(value: Any) -> str | None:
    """A decimal string of at most 8 decimals (trailing zeros beyond them dropped)."""
    if value is None:
        return None
    if isinstance(value, float):
        value = Decimal(repr(value))
    try:
        d = Decimal(str(value).strip())
    except ArithmeticError:
        raise ValueError("not a number") from None
    if not d.is_finite():
        raise ValueError("not a number")
    text = format(d, "f")
    if "." in text and len(text.split(".")[1]) > 8:
        text = text.rstrip("0").rstrip(".")
    return text


class RowError(ValueError):
    """One row against ledger_v1: the row number and the column, never the value."""

    def __init__(self, n: int, column: str, why: str) -> None:
        super().__init__(f"row {n}, column {column}: {why}")
        self.n, self.column, self.why = n, column, why


def contract_row(n: int, raw: dict[str, Any], salt: str) -> dict[str, Any]:
    """One database row as a ledger_v1 row, checked by every rule of the contract."""
    out: dict[str, Any] = {}
    for col in COLUMNS:
        value = raw.get(col)
        try:
            if value is None:
                out[col] = None
            elif col == "customer":
                out[col] = pseudonym(salt, value)
            elif col == "amount_usdt":
                out[col] = amount_text(value)
            elif col in ("paid_at", "period_start", "period_end"):
                out[col] = utc_z(value)
            elif col == "plan":
                out[col] = str(value).strip().lower()
            else:
                out[col] = str(plain(value)).strip()
        except ValueError as exc:
            raise RowError(n, col, str(exc)) from None
        if out[col] is None and col not in NULLABLE:
            raise RowError(n, col, "empty")
        rule = PATTERNS.get(col)
        if out[col] is not None and rule is not None and not rule.fullmatch(out[col]):
            raise RowError(n, col, "wrong format")
    if out["kind"] not in KINDS:
        raise RowError(n, "kind", "must be crypto or store")
    if out["network"] is not None and out["network"] not in NETWORKS:
        raise RowError(n, "network", "must be bsc_usdt or trc20_usdt")
    if out["tx_hash"] is not None and len(out["tx_hash"]) > 80:
        raise RowError(n, "tx_hash", "too long")
    if out["kind"] == "crypto":
        for col in ("amount_usdt", "network", "tx_hash"):
            if out[col] is None:
                raise RowError(n, col, "required for a crypto payment")
        if not TX_HASH[out["network"]].fullmatch(out["tx_hash"]):
            raise RowError(n, "tx_hash", "not a hash of its network")
        if Decimal(out["amount_usdt"]) <= 0:
            raise RowError(n, "amount_usdt", "must be above zero")
    else:
        for col in ("amount_usdt", "network", "tx_hash"):
            if out[col] is not None:
                raise RowError(n, col, "must be empty for a store payment")
    if (out["period_start"] is None) != (out["period_end"] is None):
        raise RowError(n, "period_start", "both period columns or neither")
    if out["period_start"] is not None and utc_z_key(out["period_end"]) <= utc_z_key(
        out["period_start"]
    ):
        raise RowError(n, "period_end", "must be after period_start")
    return out


def utc_z_key(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def cursor_of(paid_at: Any) -> str | None:
    t = utc_z(paid_at)
    return None if t is None else CURSOR_PREFIX + t


def check_columns(names: list[str]) -> None:
    if len(names) != len(set(names)) or set(names) != set(COLUMNS):
        missing = [c for c in COLUMNS if c not in names]
        extra = sorted({n for n in names if n not in COLUMNS})
        dupes = sorted({n for n in names if names.count(n) > 1})
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append(f"{len(extra)} extra column(s)")
        if dupes:
            parts.append(f"{len(dupes)} repeated column(s)")
        raise LedgerError(
            "ledger.sql columns differ from ledger_v1 (" + "; ".join(parts) + ")",
            "ستون‌های خروجی ledger.sql با قرارداد ledger_v1 یکی نیست (" + "؛ ".join(parts) + ").",
        )


def parse_since(value: Any) -> datetime | None:
    """The cursor the hub sends back (`t:<time>`, or a bare ISO 8601 time) as a time."""
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_CURSOR:
        raise JobError("since_cursor باید متنی که runner داده (یا null) باشد.")
    text = value.removeprefix(CURSOR_PREFIX)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise JobError("since_cursor یک نشانگر درست runner (زمان ISO 8601) نیست.") from None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_limit(value: Any) -> int:
    if value is None:
        return DEFAULT_LIMIT
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_LIMIT:
        raise JobError(f"limit باید عددی از ۱ تا {MAX_LIMIT} باشد.")
    return value


def _db_reason(exc: BaseException) -> LedgerError:
    """A database failure without its message (which may name a company's
    table): its SQLSTATE and class only."""
    code = getattr(exc, "sqlstate", None)
    name = type(exc).__name__
    tag = f"{code} {name}" if code else name
    if code == "57014":
        return LedgerError(
            "the query ran past its statement timeout",
            "پرس‌وجوی دفتر از سقف زمانش گذشت و متوقف شد.",
            EXIT_QUERY,
        )
    if code == "25006":
        return LedgerError(
            "the query tried to write (the transaction is read only)",
            "پرس‌وجوی دفتر خواست بنویسد؛ فقط خواندن مجاز است.",
            EXIT_QUERY,
        )
    if isinstance(exc, OSError | TimeoutError) or name in (
        "InvalidPasswordError",
        "InvalidAuthorizationSpecificationError",
        "ConnectionDoesNotExistError",
        "CannotConnectNowError",
        "InvalidCatalogNameError",
    ):
        return LedgerError(
            f"cannot connect to the ledger database ({tag})",
            f"به دیتابیس دفتر وصل نشد ({tag})؛ HQ_LEDGER_DSN را بسنجید.",
            EXIT_QUERY,
        )
    return LedgerError(
        f"the ledger query failed ({tag})", f"پرس‌وجوی دفتر خطا داد ({tag}).", EXIT_QUERY
    )


def _driver() -> Any:
    try:
        import asyncpg  # only the ledger needs a database driver
    except ImportError:
        raise LedgerError(
            "asyncpg is not installed (reinstall the runner from requirements.lock)",
            "کتابخانه‌ی asyncpg روی این سرور نصب نیست؛ "
            "runner را از requirements.lock دوباره نصب کنید.",
        ) from None
    return asyncpg


async def connect(lc: LedgerConfig) -> Any:
    asyncpg = _driver()
    try:
        return await asyncpg.connect(
            dsn=lc.dsn,
            timeout=CONNECT_TIMEOUT_S,
            command_timeout=STATEMENT_TIMEOUT_MS / 1000 + 5,
            server_settings={"application_name": "hq-runner-ledger"},
        )
    except Exception as exc:  # noqa: BLE001 - never the driver's text: it may carry the DSN
        raise _db_reason(exc) from None


async def _read_only(conn: Any) -> Any:
    tr = conn.transaction(readonly=True)
    await tr.start()
    await conn.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
    await conn.execute("SET LOCAL lock_timeout = 5000")
    return tr


def page(rows: list[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], bool]:
    """At most `limit` rows ordered by paid_at; when more exist, the rows that
    share the last kept paid_at with the first one left out are kept for the
    next page too (so a `paid_at > since` query never skips one), unless
    that would leave nothing."""
    if len(rows) <= limit:
        return rows, False
    kept = rows[:limit]
    boundary = rows[limit]["paid_at"]
    trimmed = [r for r in kept if r["paid_at"] != boundary]
    return (trimmed or kept), True


async def read(lc: LedgerConfig, since: datetime | None, limit: int) -> dict[str, Any]:
    conn = await connect(lc)
    try:
        tr = await _read_only(conn)
        try:
            stmt = await conn.prepare(
                f"SELECT * FROM ({lc.sql}) AS hq_ledger ORDER BY paid_at, ext_id LIMIT $2"  # noqa: S608 - the server's own file, never the hub's text
            )
            check_columns([a.name for a in stmt.get_attributes()])
            records = await stmt.fetch(since, limit + 1)
        finally:
            with contextlib.suppress(Exception):
                await tr.rollback()
    except LedgerError:
        raise
    except Exception as exc:  # noqa: BLE001 - its SQLSTATE and class only, never its text
        raise _db_reason(exc) from None
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(conn.close(), 5)
    raw = [dict(r.items()) for r in records]
    rows, more = page(raw, limit)
    try:
        out = [contract_row(n, r, lc.salt) for n, r in enumerate(rows, 1)]
    except RowError as exc:
        raise LedgerError(
            f"ledger.sql output breaks ledger_v1 at {exc}; nothing was sent",
            f"خروجی ledger.sql در ردیف {exc.n}، ستون {exc.column} با قرارداد ledger_v1 "
            "نمی‌خواند؛ هیچ ردیفی فرستاده نشد.",
            EXIT_QUERY,
        ) from None
    if len({r["ext_id"] for r in out}) != len(out):
        raise LedgerError(
            "ledger.sql returned the same ext_id twice in one batch",
            "ledger.sql یک ext_id را در یک دسته دو بار داد.",
            EXIT_QUERY,
        )
    cursor = cursor_of(rows[-1]["paid_at"]) if rows else (cursor_of(since) if since else None)
    return {
        "contract": CONTRACT,
        "rows": out,
        "next_cursor": cursor,
        "has_more": more,
        "count": len(out),
    }


async def run_ledger(ctx: JobContext) -> JobResult:
    args = ctx.args
    if args.get("contract") != CONTRACT:
        raise JobError(f"قرارداد خروجی دفتر باید {CONTRACT} باشد.")
    since = parse_since(args.get("since_cursor", args.get("since")))
    limit = parse_limit(args.get("limit"))
    try:
        lc = await asyncio.to_thread(load_config, ctx.cfg_path)
        out = await read(lc, since, limit)
    except LedgerError as exc:
        raise JobError(exc.fa, exc.exit_code) from None
    more = " (ادامه دارد)" if out["has_more"] else ""
    return JobResult(0, f"دفتر پرداخت خوانده شد: {out['count']} ردیف{more}.", output=out)


# -- hq-runner ledger-check -----------------------------------------------------------
WRITABLE_SQL = """
SELECT
  (SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolbypassrls
     FROM pg_roles WHERE rolname = current_user) AS powerful,
  has_database_privilege(current_database(), 'CREATE') AS db_create,
  (SELECT count(*) FROM pg_namespace n
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND n.nspname NOT LIKE 'pg\\_toast%' AND n.nspname NOT LIKE 'pg\\_temp%'
      AND has_schema_privilege(n.oid, 'CREATE')) AS schema_create,
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND n.nspname NOT LIKE 'pg\\_toast%' AND n.nspname NOT LIKE 'pg\\_temp%'
      AND has_table_privilege(c.oid, 'INSERT, UPDATE, DELETE, TRUNCATE')) AS writable
"""


async def check(cfg_path: Path | None = None) -> list[str]:
    """Files and their modes, a connection, SELECT 1, a role that cannot
    write anywhere, and the query's columns (prepared, not run). Raises
    LedgerError with the first reason; returns warnings (a schema the role
    could create in: the job's READ ONLY transaction still stops that, but
    the company may want to close it)."""
    lc = await asyncio.to_thread(load_config, cfg_path)
    conn = await connect(lc)
    warnings: list[str] = []
    try:
        tr = await _read_only(conn)
        try:
            if await conn.fetchval("SELECT 1") != 1:
                raise LedgerError("SELECT 1 did not answer 1", "SELECT 1 جواب درست نداد.")
            w = await conn.fetchrow(WRITABLE_SQL)
            found = [
                k
                for k, bad in (
                    ("superuser or role/database creation", w["powerful"]),
                    ("CREATE on the database", w["db_create"]),
                    ("write access to a table or view", w["writable"]),
                )
                if bad
            ]
            if found:
                raise LedgerError(
                    "the ledger role can write: " + ", ".join(found),
                    "نقش دفتر دسترسی نوشتن دارد؛ فقط SELECT مجاز است.",
                )
            if w["schema_create"]:
                warnings.append(
                    f"the ledger role may create objects in {w['schema_create']} schema(s); "
                    "the job's READ ONLY transaction still stops any write"
                )
            stmt = await conn.prepare(
                f"SELECT * FROM ({lc.sql}) AS hq_ledger ORDER BY paid_at, ext_id LIMIT $2"  # noqa: S608 - the server's own file
            )
            check_columns([a.name for a in stmt.get_attributes()])
            # the first rows, checked like a batch (they stay on this server)
            for n, r in enumerate(await stmt.fetch(None, CHECK_ROWS), 1):
                try:
                    contract_row(n, dict(r.items()), lc.salt)
                except RowError as exc:
                    raise LedgerError(
                        f"ledger.sql output breaks ledger_v1 at {exc}",
                        f"خروجی ledger.sql در ردیف {exc.n}، ستون {exc.column} "
                        "با ledger_v1 نمی‌خواند.",
                        EXIT_QUERY,
                    ) from None
        finally:
            with contextlib.suppress(Exception):
                await tr.rollback()
    except LedgerError:
        raise
    except Exception as exc:  # noqa: BLE001 - its SQLSTATE and class only, never its text
        raise _db_reason(exc) from None
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(conn.close(), 5)
    return warnings
