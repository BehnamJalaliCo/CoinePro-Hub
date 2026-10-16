"""OPA client (infra/opa/policy). Fail-closed: if OPA cannot answer, the
request is denied (prompt 04 §5)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from hq_api.errors import ApiError

log = logging.getLogger("hq_api.policy")


@dataclass(frozen=True)
class Verdict:
    allow: bool
    reasons: tuple[str, ...]


class Policy:
    def __init__(
        self, url: str, *, timeout: float = 2.0, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=url.rstrip("/"), timeout=timeout, transport=transport
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def query(self, package: str, input_: dict[str, Any]) -> Verdict:
        try:
            resp = await self._http.post(f"/v1/data/hq/{package}", json={"input": input_})
            resp.raise_for_status()
            result = resp.json().get("result") or {}
        except (httpx.HTTPError, ValueError) as exc:
            log.error(
                "opa unavailable; denying (fail-closed)",
                extra={"package": package, "error": type(exc).__name__},
            )
            return Verdict(False, ("policy_unavailable",))
        allow = result.get("allow") is True
        reasons = tuple(sorted(str(r) for r in result.get("deny_reasons") or ()))
        return Verdict(allow and not reasons, reasons)

    async def require(self, package: str, input_: dict[str, Any]) -> None:
        v = await self.query(package, input_)
        if not v.allow:
            if "policy_unavailable" in v.reasons:
                raise ApiError(503, "policy_denied", "policy service unavailable (fail-closed)")
            raise ApiError(403, "policy_denied", ", ".join(v.reasons) or "denied")

    async def healthy(self) -> bool:
        try:
            return (await self._http.get("/health")).status_code == 200
        except httpx.HTTPError:
            return False
