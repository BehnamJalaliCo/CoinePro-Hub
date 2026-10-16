"""Run a multi-statement SQL script inside the current Alembic transaction.

asyncpg prepares every statement and rejects scripts with several commands,
so migrations hand the script to the raw driver connection, which uses the
simple query protocol on the same connection and transaction.
"""

from __future__ import annotations

from typing import Any

from alembic import op


def execute_script(sql: str) -> None:
    dbapi_conn: Any = op.get_bind().connection.dbapi_connection
    dbapi_conn.run_async(lambda conn: conn.execute(sql))
