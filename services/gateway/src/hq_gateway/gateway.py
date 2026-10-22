"""One tool call, end to end (prompt 05 §3, prompt 5.1 §2.3).

reserve   the run's own gate: running run, caps per step and per run (api,
          agents.runs), the employee, its charter role, its lock state
catalog   unknown tool -> denied; A3/A4 never exist here
charter   tool outside the role's charter (agents/roles/<role>.md) -> denied
policy    hq.actions (OPA): the tool's class by role and escrow, A4 never,
          a locked company (kill switch or deploy freeze) refuses writes
validate  the tool's input model (field errors back, never the values)
carry out through the internal API with the run's agent token; mcp.call
          (class `per tool`) first asks the api for the server and the class
          the owner sealed for that tool, then the policy decides on that
          class; an A3 tool becomes the owner's decision instead, and runs
          only as the one call of an approved card (hq_gateway.mcp); a server
          over http is reserved at the egress gate first (data guard, limits)
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
import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from hq_common.charters import IMPLICIT_TOOLS, Library
from hq_common.redact import fit_async, mask_secrets
from hq_gateway import (
    founding,  # noqa: F401 - registers server.plan (prompt 09)
    inquiries,  # noqa: F401 - inquiries, errands, planner, workshop.read
    oversight,  # noqa: F401 - registers the overseer's tools (prompt 08)
    people,  # noqa: F401 - registers stars, lessons, stories, hire.decide
    revenue,  # noqa: F401 - prompt 10: revenue.read, funnel.read, rescue, feedback, referral
    web,  # registers the internet tools (web.*, http.request)
)
from hq_gateway import mcp as M
from hq_gateway import tools as T

log = logging.getLogger("hq_gateway")
TOOL_NAME = re.compile(r"[a-z][a-z_]*(?:\.[a-z_]+)?")  # always fullmatch: "work.get\n" is no tool
AUDIT_CODE = re.compile(r"[a-z][a-z0-9_]{1,60}")
RESERVE_STRINGS = 500  # what /internal/v1/egress/reserve takes in one list


@dataclass(frozen=True)
class Refused:
    """An MCP call that did not run, and why (a step outcome's code)."""

    outcome: str
    code: str
    hint_fa: str | None = None


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
        mcp_opener: M.Opener | None = None,
    ) -> None:
        self.lib = library
        self.api = api
        self.opa = opa
        self.mcp_opener = mcp_opener
        self.max_result_chars = max_result_chars
        self.tool_timeout_s = tool_timeout_s
        self.deadline_s = deadline_s
        self.audit_timeout_s = min(audit_timeout_s, deadline_s / 4)

    async def call(self, token: str, step: int, index: int, tool: Any, args: Any) -> Outcome:
        name = tool_name(tool)
        catalog = self.lib.tools.get(name)
        cls = catalog.cls if catalog else None
        gate: dict[str, Any] = {}
        out = Outcome("error", cls, "cancelled", None, None, {})  # if the call is cancelled
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
        finally:
            # Whatever happened, cancellation included, the call has its audit row
            # (shielded: a second cancel does not lose it). A per-call class (an
            # MCP tool's sealed class, an A0/A2 tool's decided class) stays;
            # otherwise the catalog's.
            per_call = (
                catalog is not None and (catalog.per_tool or bool(catalog.classes)) and out.cls
            )
            out.cls = out.cls if per_call else cls
            if out.code != "run_not_running":  # the api audits nothing for a dead run's token
                await asyncio.shield(self._record(token, name, out, step))
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
        # The overseer's holds (prompt 08 §2): a held employee or work item only
        # reads; a held tool does not run at all. Only the owner releases.
        held = [str(h) for h in gate.get("held") or []]
        whole = [h for h in held if not h.startswith("tool:")]
        if (whole and catalog.cls != "A0") or f"tool:{name}" in held:
            return Outcome(
                "denied", catalog.cls, "held", None, None, {"holds": ",".join(whole)[:200]}
            )
        if catalog.per_tool:
            return await self._mcp(token, gate, step, index, name, args)
        cls = catalog.cls
        parsed: Any = None
        if catalog.classes:
            # A0/A2: the input decides the class (unknown = the higher one).
            parsed, fields = T.validate(name, args)
            if parsed is None:
                return Outcome("error", catalog.cls, "invalid_args", None, None, fields)
            cls = T.call_class(name, parsed, catalog.cls)
            if cls not in catalog.classes:
                cls = catalog.cls
        denied = await self._policy(gate, name, cls, args)
        if denied is not None:
            return denied
        if parsed is None:
            parsed, fields = T.validate(name, args)
            if parsed is None:
                return Outcome("error", cls, "invalid_args", None, None, fields)
        _, handler = T.TOOLS[name]
        call = T.Call(token=token, gate=gate, step=step, index=index, cls=cls)
        try:
            r = await asyncio.wait_for(handler(self.api, call, parsed), timeout=self.tool_timeout_s)
        except TimeoutError:
            return Outcome("error", cls, "tool_timeout", None, None, {})
        except httpx.HTTPError:
            return Outcome("error", cls, "api_unreachable", None, None, {})
        result, truncated = (
            await fit_async(r.data, self.max_result_chars) if r.data is not None else (None, False)
        )
        return Outcome(
            r.outcome, cls, r.code, r.ref, result, r.fields, truncated, hint_fa=r.hint_fa
        )

    async def _policy(
        self,
        gate: dict[str, Any],
        name: str,
        cls: str,
        args: Any,
        approved_decision: str | None = None,
    ) -> Outcome | None:
        """hq.actions for one call of class `cls`: None when allowed. An A3
        call carries the approved card the api consumed for it."""
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
                "action": {"class": cls, "name": name, "company": gate["company"]},
                "context": {
                    "escrow_classes": gate.get("escrow_classes") or [],
                    # An answer without its lock field counts as locked (the safe side).
                    "company_locked": "lock" not in gate or gate["lock"] is not None,
                    "incident": name == "notify"
                    and isinstance(args, dict)
                    and args.get("level") == "urgent"
                    and bool(args.get("category")),
                    **({"approved_decision": approved_decision} if approved_decision else {}),
                },
            }
        )
        if not allowed:
            code = (
                "company_locked"
                if reasons == ["company_locked"]
                else ("policy_unavailable" if "policy_unavailable" in reasons else "policy_denied")
            )
            return Outcome("denied", cls, code, None, None, {"reasons": ",".join(reasons)[:200]})
        return None

    # -------------------------------------------------------------- mcp.call --
    async def _mcp(
        self, token: str, gate: dict[str, Any], step: int, index: int, name: str, args: Any
    ) -> Outcome:
        """resolve (api: enabled, the company may, the sealed class; an A3 tool
        becomes a decision there, or the approved card's one call) -> policy on
        that class -> reserve at the egress gate (http) -> open the server ->
        its listing must be the pinned one -> call -> labelled, redacted data."""
        parsed, fields = T.validate(name, args)
        if parsed is None:
            return Outcome("error", None, "invalid_args", None, None, fields)
        canon = json.dumps(parsed.args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        # What an A3 card shows the owner: the arguments with only their
        # secrets masked (recipients and amounts stay; contract §18.13).
        shown = mask_secrets(parsed.args)  # at most 20000 characters: no thread needed
        resp = await self.api.request(
            "POST",
            "/internal/v1/tools/mcp/resolve",
            token,
            json={
                "server": parsed.server,
                "tool": parsed.tool,
                "args_sha256": hashlib.sha256(canon.encode()).hexdigest(),
                "preview": json.dumps(shown, ensure_ascii=False, sort_keys=True)[:20000],
                "args": shown,
            },
        )
        ref = f"mcp:{parsed.server}/{parsed.tool}"[:80]
        r = T.from_response(resp, None)
        if r.outcome != "ok" or not isinstance(r.data, dict):
            code = r.code or "api_bad_answer"
            return Outcome(r.outcome, None, code, ref, None, r.fields, hint_fa=r.hint_fa)
        d = r.data
        cls = str(d.get("class") or "")
        approved: str | None = None
        if d.get("decision") and not d.get("server"):  # an A3 tool: the owner decides
            decision = str(d["decision"])[:40]
            return Outcome(
                "denied",
                "A3",
                "a3_requires_decision",
                decision,
                {"decision": decision},
                {},
                hint_fa=str(d.get("message_fa") or "")[:300] or None,
            )
        if cls == "A3" and isinstance(d.get("decision"), str):
            approved = str(d["decision"])[:40]  # the approved card's one call
        elif cls not in ("A0", "A1", "A2"):
            return Outcome("error", None, "api_bad_answer", ref, None, {})
        denied = await self._policy(gate, name, cls, args, approved)
        if denied is not None:
            denied.ref = ref
            return denied
        srv = d.get("server") or {}
        spec = M.ServerSpec(
            key=str(srv.get("key") or parsed.server),
            transport=str(srv.get("transport") or ""),
            url=str(srv.get("url") or ""),
            listing_sha256=srv.get("listing_sha256"),
            auth_header=srv.get("auth_header"),
            secret=srv.get("secret"),
            call_id=uuid.uuid4().hex,
            cls=cls,
        )
        del d, srv, r, resp  # the secret lives in `spec` only
        if self.mcp_opener is None:
            return Outcome("denied", cls, "channel_not_configured", ref, None, {})
        reservation: Any = None
        if spec.transport == "http":
            # Like every internet call (RUNBOOK §20): the data guard on what
            # would leave and the run's and company's limits, before CONNECT.
            refused, reservation = await self._mcp_reserve(token, spec, cls, parsed)
            if refused is not None:
                refused.ref = ref
                return refused
        started = time.monotonic()
        try:
            out = await asyncio.wait_for(
                self._mcp_session(token, spec, parsed.tool, parsed.args), self.tool_timeout_s
            )
        except M.NotConfigured:
            return Outcome("denied", cls, "channel_not_configured", ref, None, {})
        except TimeoutError:
            return Outcome("error", cls, "tool_timeout", ref, None, {})
        except Exception:  # noqa: BLE001 - a server's failure: never its details or the secret
            log.warning("mcp call failed", extra={"server": spec.key, "tool": parsed.tool})
            return Outcome("error", cls, "mcp_unreachable", ref, None, {})
        finally:
            await web.shielded(self._mcp_egress_log(token, spec, reservation))
        ms = int((time.monotonic() - started) * 1000)
        log.info("mcp call", extra={"server": spec.key, "tool": parsed.tool, "ms": ms})
        if isinstance(out, Refused):
            return Outcome(out.outcome, cls, out.code, ref, None, {}, hint_fa=out.hint_fa)
        result, truncated = await fit_async(out, self.max_result_chars)
        failed = bool(out.get("is_error"))
        return Outcome(
            "error" if failed else "ok",
            cls,
            "mcp_tool_error" if failed else None,
            ref,
            result,
            {},
            truncated,
        )

    async def _mcp_reserve(
        self, token: str, spec: M.ServerSpec, cls: str, parsed: Any
    ) -> tuple[Outcome | None, Any]:
        """(refusal, reservation): the egress gate's reserve for one call to
        an http server, as for web.* and http.request: everything that would
        leave (the tool's name and its arguments, keys and values) through the
        data guard, the limits, and the call's row written before it leaves."""
        strings = web._strings(parsed.tool, parsed.args)  # the web tools' own walk
        if len(strings) > RESERVE_STRINGS:  # the gate takes 500: the rest as one, all read
            strings = [*strings[: RESERVE_STRINGS - 1], "\n".join(strings[RESERVE_STRINGS - 1 :])]
        resp = await self.api.request(
            "POST",
            "/internal/v1/egress/reserve",
            token,
            json={
                "tool": "mcp.call",
                "class": cls,
                "strings": strings,
                "method": "POST",
                "url": spec.url,
            },
        )
        r = T.from_response(resp, None)
        if r.outcome != "ok":
            return Outcome(
                r.outcome, cls, r.code or "api_bad_answer", None, None, r.fields, hint_fa=r.hint_fa
            ), None
        grant = r.data if isinstance(r.data, dict) else {}
        return None, grant.get("reservation")

    async def _mcp_egress_log(
        self, token: str, spec: M.ServerSpec, reservation: Any = None
    ) -> None:
        """The proxied connections of one MCP call, from egress to the egress
        log (an http server only; a failure here never fails the call); they
        settle the call's reservation."""
        egress = getattr(self.api, "egress", None)
        if spec.transport != "http" or egress is None:
            return
        try:
            out = await egress.post("/v1/proxy/drain", {"call_id": spec.call_id})
            if isinstance(out, dict):  # in the log's shape, rows beyond 200 summed
                await web.log_entries(self.api, token, "mcp.call", spec.cls, out, reservation)
        except Exception:  # noqa: BLE001 - logged as missing, the call stands
            log.warning("mcp egress entries not logged", extra={"server": spec.key})

    async def _mcp_session(
        self, token: str, spec: M.ServerSpec, tool: str, args: dict[str, Any]
    ) -> dict[str, Any] | Refused:
        """The call itself, or a refusal: the server's listing differs from the
        one pinned after the owner's seal (the api switches it off), the api
        could not be told (nothing runs, and that is no listing change), or
        the tool is not on the server."""
        assert self.mcp_opener is not None
        async with self.mcp_opener(spec) as session:
            try:
                listing = M.listing_of(await M.list_all(session))
            except M.ListingTooLong:
                return Refused("error", "mcp_tool_error")
            if spec.listing_sha256 != listing.sha256:
                resp = await self.api.request(
                    "POST",
                    f"/internal/v1/tools/mcp/{spec.key}/listing",
                    token,
                    json={
                        "listing_sha256": listing.sha256,
                        "tools": listing.names[:500],
                        "listing": listing.tools[:500],
                    },
                )
                if resp.status_code != 200:
                    r = T.from_response(resp, None)
                    return Refused(r.outcome, r.code or "api_bad_answer", r.hint_fa)
                try:
                    body = resp.json()
                except ValueError:
                    body = None
                if not isinstance(body, dict) or body.get("status") not in (
                    "enabled", "disabled", "pending",
                ):  # fmt: skip
                    return Refused("error", "api_bad_answer")
                if body["status"] != "enabled":
                    return Refused("denied", "mcp_tools_changed")
            if tool not in listing.names:
                return Refused("denied", "mcp_tool_missing")
            result = await session.call_tool(tool, args)
        return M.render(spec.key, tool, result)

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
