"""Idempotency-Key (contract §1): same key + same body within 24 h returns
the first result; same key with another body -> 409 idempotency_conflict.

The key is claimed inside the mutation's own transaction: if the mutation
rolls back, so does the claim. A concurrent duplicate waits on the unique
index and then sees the stored response.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal


@dataclass
class Idem:
    principal: str
    key: UUID
    method: str
    path: str
    body_sha256: str
    replay: JSONResponse | None = None

    async def store(self, tx: Tx, status_code: int, body: Any) -> None:
        await tx.exec(
            """UPDATE core.idempotency_keys SET status_code = :sc, response = CAST(:resp AS jsonb)
               WHERE principal = :p AND key = :k""",
            sc=status_code,
            resp=json.dumps(body, default=str, ensure_ascii=False),
            p=self.principal,
            k=self.key,
        )


def read_key(request: Request, *, required: bool) -> UUID | None:
    raw = request.headers.get("idempotency-key")
    if not raw:
        if required:
            raise ApiError(422, "validation_failed", fields={"Idempotency-Key": "required"})
        return None
    try:
        return UUID(raw)
    except ValueError as exc:
        raise ApiError(
            422, "validation_failed", fields={"Idempotency-Key": "must be a UUID"}
        ) from exc


async def claim(tx: Tx, request: Request, who: Principal, *, required: bool = False) -> Idem | None:
    key = read_key(request, required=required)
    if key is None:
        return None
    body = await request.body()
    idem = Idem(
        principal=f"{who.kind}:{who.code}",
        key=key,
        method=request.method,
        path=request.url.path,
        body_sha256=hashlib.sha256(body).hexdigest(),
    )
    inserted = await tx.first(
        """INSERT INTO core.idempotency_keys (principal, key, method, path, body_sha256)
           VALUES (:p, :k, :m, :path, :b)
           ON CONFLICT (principal, key) DO UPDATE
               SET method = EXCLUDED.method, path = EXCLUDED.path,
                   body_sha256 = EXCLUDED.body_sha256, status_code = NULL, response = NULL,
                   created_at = now()
               WHERE core.idempotency_keys.created_at < now() - make_interval(hours => 24)
           RETURNING key""",
        p=idem.principal,
        k=key,
        m=idem.method,
        path=idem.path,
        b=idem.body_sha256,
    )
    if inserted is not None:
        return idem
    prev = await tx.one(
        """SELECT method, path, body_sha256, status_code, response FROM core.idempotency_keys
           WHERE principal = :p AND key = :k""",
        p=idem.principal,
        k=key,
    )
    if (prev["method"], prev["path"], prev["body_sha256"]) != (
        idem.method,
        idem.path,
        idem.body_sha256,
    ):
        raise ApiError(409, "idempotency_conflict")
    if prev["status_code"] is None:
        raise ApiError(
            409, "idempotency_conflict", "the first request with this key is still running"
        )
    idem.replay = JSONResponse(
        prev["response"], status_code=prev["status_code"], headers={"Idempotent-Replay": "true"}
    )
    return idem
