"""One tool call, end to end (prompt 05 §3, prompt 5.1 §2.3).

reserve   the run's own gate: running run, caps per step and per run (api,
          agents.runs), the employee, its charter role, its lock state
catalog   unknown tool -> denied; A3/A4 never exist here
charter   tool outside the role's charter (agents/roles/<role>.md) -> denied
policy    hq.actions (OPA): the tool's class by role and escrow, A4 never,
          a locked company (kill switch or deploy freeze) refuses writes
validate  the tool's input model (field errors back, never the values)
carry out through the internal API with the run's agent token
redact    the result (keys, tokens, e-mails, phones, ...), size-capped
audit     one row per call, whatever happened (a refusal at reserve, a cap,
          an exception, a timeout): tool, class, outcome, code, ref - no
          input, no output. Only a token whose run is not running cannot be
          audited (the api refuses it, as it refused the call).

The whole call has one deadline (GATEWAY_DEADLINE_S, below the worker's own
timeout for a gateway call), so the worker never reports a failure for a
write that was carried out.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from hq_common.charters import IMPLICIT_TOOLS, Library
from hq_common.redact import fit_async
from hq_gateway import tools as T

log = logging.getLogger("hq_gateway")
TOOL_NAME = re.compile(r"[a-z][a-z_]*(?:\.[a-z_]+)?")  # always fullmatch: "work.get\n" is no tool
AUDIT_CODE = re.compile(r"[a-z][a-z0-9_]{1,60}")


@dataclass
class Outcome:
    outcome: str
    cls: str | None
    code: str | None
    ref: str | None
    result: Any
    fields: dict[str, str]
    truncated: bool = False
    hint_fa: str | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "class": self.cls,
            "code": self.code,
            "ref": self.ref,
            "result": self.result,
            "fields": self.fields,
            "truncated": self.truncated,
            "hint_fa": self.hint_fa,
        }


class Opa:
    def __init__(self, url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._http = httpx.AsyncClient(base_url=url.rstrip("/"), timeout=2.0, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def actions(self, input_: dict[str, Any]) -> tuple[bool, list[str]]:
        """hq.actions; fail-closed (no answer = denied)."""
        try:
            resp = await self._http.post("/v1/data/hq/actions", json={"input": input_})
            resp.raise_for_status()
            result = resp.json().get("result") or {}
        except (httpx.HTTPError, ValueError, AttributeError):
            return False, ["policy_unavailable"]
        reasons = sorted(str(r) for r in result.get("deny_reasons") or ())
        return result.get("allow") is True and not reasons, reasons


def tool_name(tool: Any) -> str:
    """The tool's name as sent, or "unknown" for anything that is not one."""
    if isinstance(tool, str) and len(tool) <= 40 and TOOL_NAME.fullmatch(tool):
        return tool
    return "unknown"


class Gateway:
    def __init__(
        self,
        library: Library,
        api: T.Api,
        opa: Opa,
        *,
        max_result_chars: int = 16_000,
        tool_timeout_s: float = 25.0,
        deadline_s: float = 30.0,
        audit_timeout_s: float = 4.0,
    ) -> None:
        self.lib = library
        self.api = api
        self.opa = opa
        self.max_result_chars = max_result_chars
        self.tool_timeout_s = tool_timeout_s
        self.deadline_s = deadline_s
        self.audit_timeout_s = min(audit_timeout_s, deadline_s / 4)

    async def call(self, token: str, step: int, index: int, tool: Any, args: Any) -> Outcome:
        name = tool_name(tool)
        catalog = self.lib.tools.get(name)
        cls = catalog.cls if catalog else None
        gate: dict[str, Any] = {}
        try:
            out = await asyncio.wait_for(
                self._call(token, step, index, name, catalog, args, gate),
                timeout=self.deadline_s - self.audit_timeout_s,
            )
        except TimeoutError:
            out = Outcome("error", cls, "tool_timeout", None, None, {})
        except Exception:
            log.exception("tool call failed", extra={"tool": name, "step": step})
            out = Outcome("error", cls, "internal_error", None, None, {})
        out.cls = cls
        if out.code != "run_not_running":  # the api audits nothing for a dead run's token
            await self._record(token, name, out, step)
        log.info(
            "tool call",
            extra={
                "run_id": gate.get("run_id"),
                "employee": gate.get("employee"),
                "tool": name,
                "class": out.cls,
                "outcome": out.outcome,
                "code": out.code,
                "step": step,
            },
        )
        return out

    async def _call(
        self,
        token: str,
        step: int,
        index: int,
        name: str,
        catalog: Any,
        args: Any,
        gate: dict[str, Any],
    ) -> Outcome:
        gate_resp = await self.api.request(
            "POST", "/internal/v1/runs/self/reserve", token, json={"tool": name, "step": step}
        )
        if gate_resp.status_code != 200:
            # No running run behind the token, or a cap reached: nothing is carried out.
            r = T.from_response(gate_resp, None)
            return Outcome("denied", None, r.code, None, None, {}, hint_fa=r.hint_fa)
        body = gate_resp.json()
        if not isinstance(body, dict):
            raise ValueError("reserve answered no object")
        gate.update(body)
        return await self._decide(token, gate, step, index, name, catalog, args)

    async def _decide(
        self,
        token: str,
        gate: dict[str, Any],
        step: int,
        index: int,
        name: str,
        catalog: Any,
        args: Any,
    ) -> Outcome:
        if catalog is None or name in IMPLICIT_TOOLS or name not in T.TOOLS:
            return Outcome("denied", None, "unknown_tool", None, None, {})
        if catalog.cls in ("A3", "A4"):
            code = "a4_forbidden_for_ai" if catalog.cls == "A4" else "a3_requires_decision"
            return Outcome("denied", catalog.cls, code, None, None, {})
        if name not in self.lib.allowed(gate.get("role")):
            return Outcome("denied", catalog.cls, "tool_not_in_charter", None, None, {})
        allowed, reasons = await self.opa.actions(
            {
                "principal": {
                    "kind": "agent",
                    "code": gate["employee"],
                    "role": gate["kind"],
                    "company": gate["company"],
                    "department": gate.get("department"),
                    "status": gate.get("status", "active"),
                    "scope": gate.get("scope", "company"),
                },
                "action": {"class": catalog.cls, "name": name, "company": gate["company"]},
                "context": {
                    "escrow_classes": gate.get("escrow_classes") or [],
                    "company_locked": gate.get("lock") is not None,
                    "incident": name == "notify"
                    and isinstance(args, dict)
                    and args.get("level") == "urgent"
                    and bool(args.get("category")),
                },
            }
        )
        if not allowed:
            code = (
                "company_locked"
                if reasons == ["company_locked"]
                else ("policy_unavailable" if "policy_unavailable" in reasons else "policy_denied")
            )
            return Outcome(
                "denied", catalog.cls, code, None, None, {"reasons": ",".join(reasons)[:200]}
            )
        parsed, fields = T.validate(name, args)
        if parsed is None:
            return Outcome("error", catalog.cls, "invalid_args", None, None, fields)
        _, handler = T.TOOLS[name]
        call = T.Call(token=token, gate=gate, step=step, index=index)
        try:
            r = await asyncio.wait_for(handler(self.api, call, parsed), timeout=self.tool_timeout_s)
        except TimeoutError:
            return Outcome("error", catalog.cls, "tool_timeout", None, None, {})
        except httpx.HTTPError:
            return Outcome("error", catalog.cls, "api_unreachable", None, None, {})
        result, truncated = (
            await fit_async(r.data, self.max_result_chars) if r.data is not None else (None, False)
        )
        return Outcome(
            r.outcome, catalog.cls, r.code, r.ref, result, r.fields, truncated, hint_fa=r.hint_fa
        )

    async def _record(self, token: str, name: str, out: Outcome, step: int) -> None:
        try:
            resp = await asyncio.wait_for(
                self.api.request(
                    "POST",
                    "/internal/v1/runs/self/tool-calls",
                    token,
                    json={
                        "tool": name,
                        "class": out.cls,
                        "outcome": out.outcome,
                        "code": out.code if out.code and AUDIT_CODE.fullmatch(out.code) else None,
                        "ref": (out.ref or "")[:80] or None,
                        "step": step,
                    },
                ),
                timeout=self.audit_timeout_s,
            )
            if resp.status_code != 204:
                log.warning(
                    "tool call not audited", extra={"status": resp.status_code, "tool": name}
                )
        except (TimeoutError, httpx.HTTPError):
            log.warning("tool call not audited (api unreachable)", extra={"tool": name})
