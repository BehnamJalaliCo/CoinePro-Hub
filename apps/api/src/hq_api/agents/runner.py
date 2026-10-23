"""The agent runtime (prompt 05 §2): one run of one employee for one trigger.

A run is a record first (agents.runs, state queued, written by the triggers of
migration 0008). Then:

  claim     queued -> running, at most one running run per employee; refused
            (with an audit row) when there is no charter, the employee is not
            active, the company or the holding is locked, the day's real-model
            cap is spent, or the work's budget is used up. Caps of the run:
            steps from the charter, tokens = min(charter, the work's budget
            left, the recurring escrow's cap). Model and effort: the charter's
            default sits above the holding-wide default; any company,
            department, role or employee assignment overrides it (§1.13).
  execute   step by step, all in one activity, so the conversation never
            leaves memory (Temporal history keeps no prompt, no output, no
            payload): lock and budget checked before every step; one model call
            through llm-router with the step JSON schema; actions through the
            Tool Gateway with the run's own hqa1 token (minted here, never
            stored); the step recorded (Persian summary + tool metadata);
            usage booked on the run and the work. Out of steps or tokens before
            `done`: a partial deliverable (when the role may deliver), else failed.
            The advisor (and every reply to the owner) is streamed live.
  finish    done | failed | refused, the employee back to sleep, run.finished.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.exc import DBAPIError

from hq_api import audit, events
from hq_api.agents import protocol as P
from hq_api.agents.clients import Gateway, LivePush, ModelCall, Router
from hq_api.db import Tx
from hq_api.domain import academy as AC
from hq_api.domain import decisions as D
from hq_api.domain import departments as DM
from hq_api.domain import files as F
from hq_api.domain import oversight as O
from hq_api.domain import role_drafts as RD
from hq_api.domain import skills as SK
from hq_api.errors import sqlstate_of
from hq_api.hub import Hub
from hq_api.routes.messages import LINK_TABLES
from hq_api.security import agent_tokens
from hq_api.worker.jalali import jalali_long
from hq_common import oversight_share
from hq_common.charters import Charter
from hq_common.redact import redact_async, scrub, scrub_async

log = logging.getLogger("hq_api.agents.runner")


async def masked_json(value: Any) -> str:
    """A record for the prompt, masked as a value (strings, dict keys, values
    under secret keys) BEFORE it becomes JSON text: dumped first, a secret at
    the start of a line would sit behind a "\\n" escape (prompt 5.1 review)."""
    plain = json.loads(json.dumps(value, ensure_ascii=False, default=str))
    return json.dumps(await redact_async(plain), ensure_ascii=False)


IMAGE_TOKENS = 1_600  # Anthropic's rough figure for one image of up to ~1568 px
MAX_IMAGES = 20  # per request (the router's limit), so per run


def viewed_images(results: list[dict[str, Any]]) -> list[UUID]:
    """The images files.read asked to show (the gateway checked the tenant; the
    runner reads them again under its own scope)."""
    out: list[UUID] = []
    for r in results:
        if r.get("tool") != "files.read" or r.get("outcome") != "ok":
            continue
        view = (r.get("result") or {}).get("view") or {}
        for raw in view.get("image_file_ids") or []:
            with contextlib.suppress(ValueError, TypeError):
                out.append(UUID(str(raw)))
    return out


def prompt_tokens(system: str, messages: list[dict[str, Any]]) -> int:
    """A cautious estimate of a prompt's tokens (about four characters each,
    plus a fixed amount per image block)."""
    chars, images = len(system), 0
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            chars += len(content)
            continue
        for block in content:
            if block.get("type") == "image":
                images += 1
            else:
                chars += len(block.get("text") or "")
    return chars // 4 + images * IMAGE_TOKENS


FINAL = ("done", "failed", "refused")
CONTEXT_CHARS = 24_000
THREAD_MESSAGES = 12
# The router's task class of a run comes from the charter's KIND (data in
# agents/roles), never from a role name (contract hard rule 1).
TASK_CLASS_OF_KIND = {"advisor": "advisor"}
ALERT_TASK = "ops_alert"
# ⟨1.5⟩ the classes work.run_meta may name (prompt 12 §15, contract §21.0).
RUN_TASK_CLASSES = frozenset(
    {
        "advisor_memo",
        "advisor_proactive",
        "advisor_review",
        "ask_hub",
        "ceo_letter",
        "hr_eval",
        "dceo_predict",
        "dceo_principles",
        # ⟨1.6⟩ the media studio's steps (prompt 13 §2)
        "media_script",
        "media_direction",
        "media_motion",
        "media_review",
        "ui_design",
        # ⟨1.6⟩ prompt 13 §3: a case's work, a reply's reading (legal.wake)
        "legal_case",
        "legal_email",
    }
)
# ⟨1.6⟩ a role's own class when nothing more specific names one.
TASK_CLASS_OF_ROLE = {"legal_counsel": "legal_case"}
HEARTBEAT_EVERY_S = 20.0  # the run activity's heartbeat_timeout is 3 minutes
MIN_OUTPUT_TOKENS = 256  # a step needs at least this much room to answer at all
LIVE_SCRUB_CHARS = 6_000  # a live delta shows 4,000; a little more is masked for context


@dataclass
class Claim:
    state: str  # running | busy | final
    final: str | None = None
    code: str | None = None


@dataclass
class RunCtx:
    """Everything one run needs, loaded at the start of execute."""

    run: dict[str, Any]
    emp: dict[str, Any]
    charter: Charter
    token: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    images: int = 0  # image blocks sent in this run (at most MAX_IMAGES)
    used_tokens: int = 0
    delivered: bool = False
    replied: str | None = None  # the message ref of a reply in the trigger thread
    summaries: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)  # "SK-001@3": in the system prompt
    addenda: list[str] = field(default_factory=list)  # sealed teachings ("TE-0001")
    # An oversight protocol run's ref and severity (prompt 08 §2.3): llm-router
    # lets a `critical` one go on once the oversight share is spent.
    oversight: dict[str, str] = field(default_factory=dict)
    # ⟨1.5⟩ what the code that made the run's work tells it (work.run_meta):
    # its router task class and the owner-zone flag (prompt 12 §15), a memo's mode.
    run_meta: dict[str, Any] = field(default_factory=dict)
    # ⟨1.6⟩ the charters of the run's company: the files plus its role drafts
    # (contract §22.5); None = the files only
    lib: Any = None

    @property
    def token_cap(self) -> int:
        """The run's token cap, never above its charter's tokens_per_run
        (overseer v2 and advisor v3: 200K), whatever the claim recorded."""
        cap = self.charter.limits.tokens_per_run
        return min(int(self.run["token_cap"] or cap), cap)


class Runner:
    def __init__(
        self,
        hub: Hub,
        router: Router,
        gateway: Gateway,
        live: LivePush | None = None,
        *,
        heartbeat: Callable[[], None] | None = None,
    ) -> None:
        self.hub = hub
        self.router = router
        self.gateway = gateway
        self.live = live
        self.heartbeat = heartbeat or (lambda: None)
        self.heartbeat_every_s = HEARTBEAT_EVERY_S
        self.s = hub.settings

    async def _tx(self) -> Any:
        return self.hub.db.tx(await self.hub.companies.ids())

    # --------------------------------------------------------------- claim --
    async def claim(self, run_id: str) -> Claim:
        lib = self.hub.charters
        async with await self._tx() as tx:
            run = await tx.first(
                "SELECT * FROM agents.runs WHERE id = CAST(:id AS uuid) FOR UPDATE", id=run_id
            )
            if run is None:
                return Claim("final", "failed", "unknown_run")
            if run["state"] == "running":
                return Claim("running")  # a retried claim of our own
            if run["state"] in FINAL:
                return Claim("final", run["state"], run["error_code"])
            emp = await self._employee(tx, run["employee_id"])
            if lib is not None and lib.get(emp["role"]) is None:
                # ⟨1.6⟩ a role written on demand runs from its draft (§22.5)
                lib = await RD.overlay(tx, lib, emp["company_id"], running=True)
            charter = lib.get(emp["role"]) if lib is not None else None
            refuse = None
            if charter is None:
                refuse = "no_charter"
            elif emp["status"] != "active" or emp["kind"] == "system":
                refuse = "employee_inactive"
            else:
                lock = await tx.scalar("SELECT control.lock_state(:co)", co=run["company_id"])
                if lock is not None:  # kill switch (holding or company) or a deploy freeze
                    refuse = "locked"
                elif (
                    # 0 (or less) means nothing at all, not "no cap" (prompt 08.1)
                    self.s.agent_daily_token_cap <= 0
                    or await self._spent_today(tx) >= self.s.agent_daily_token_cap
                ):
                    refuse = "daily_cap"
                elif run["work_id"] is not None:
                    refuse = await self._work_refusal(tx, run["work_id"])
            if refuse is None and await tx.scalar(
                "SELECT 1 FROM agents.runs WHERE employee_id = :e AND state = 'running'",
                e=run["employee_id"],
            ):
                return Claim("busy")
            caps: dict[str, Any] = {}
            if refuse is None:
                assert charter is not None
                caps = await self._caps(tx, run, charter)
                if caps["token_cap"] <= 0:
                    refuse = "budget_used_up"
            if refuse is not None:
                await self._finish(tx, run, emp, "refused", refuse, note=None, start=False)
                return Claim("final", "refused", refuse)
            assert charter is not None
            model, effort = await self._model(tx, emp, charter)
            ttl = min(agent_tokens.MAX_TTL_S, self.s.agent_max_run_s + 120)
            await tx.exec(
                """UPDATE agents.runs SET state = 'running', started_at = now(), priority = :prio,
                       charter_role = :role, charter_version = :ver, model = :model, effort = :effort,
                       steps_cap = :steps, token_cap = :tokens, tool_calls_cap = :calls,
                       step_tool_calls_cap = :per_step,
                       token_expires_at = now() + make_interval(secs => :ttl)
                   WHERE id = :id""",
                id=run["id"],
                prio=caps["priority"],
                role=charter.role,
                ver=charter.version,
                model=model,
                effort=effort,
                steps=charter.limits.steps_per_run,
                tokens=caps["token_cap"],
                calls=self.s.agent_tool_calls_per_run,
                per_step=self.s.agent_actions_per_step,
                ttl=ttl,
            )
            await self._activity(tx, emp, "working", f"run {str(run['id'])[:8]}")
            await events.emit(
                tx,
                emp["company"],
                "run.started",
                str(run["id"]),
                {
                    "employee": emp["code"],
                    "trigger": run["trigger"],
                    "work": await self._work_ref(tx, run["work_id"]),
                    "charter": f"{charter.role}@{charter.version}",
                },
            )
        return Claim("running")

    async def _work_refusal(self, tx: Tx, work_id: UUID) -> str | None:
        """A run for work that is closed (done, cancelled, failed) or whose
        dollar budget is spent has nothing to do (prompt 5.1 §2.6)."""
        w = await tx.first(
            "SELECT status, budget_usd, usd_used FROM work.work WHERE id = :id", id=work_id
        )
        if w is None or w["status"] in ("done", "cancelled", "failed"):
            return "work_closed"
        if w["budget_usd"] is not None and Decimal(w["usd_used"]) >= Decimal(w["budget_usd"]):
            return "budget_used_up"
        return None

    async def _employee(self, tx: Tx, employee_id: UUID) -> dict[str, Any]:
        return await tx.one(
            """SELECT e.id, e.code, e.kind, e.status, e.role, e.title_fa, e.company_id, c.code AS company,
                      c.kind AS company_kind, c.name_fa AS company_name_fa, c.name_en AS company_name_en,
                      d.code AS department, d.name_fa AS department_name_fa, r.code AS manager
               FROM core.employees e JOIN core.companies c ON c.id = e.company_id
               LEFT JOIN core.departments d ON d.id = e.department_id
               LEFT JOIN core.employees r ON r.id = e.reports_to
               WHERE e.id = :id""",
            id=employee_id,
        )

    async def _spent_today(self, tx: Tx) -> int:
        n = await tx.scalar(
            # Every agent call of today (UTC) from the router's ledger, call by call:
            # a run that started before midnight still counts what it spends after.
            # Everything the model read or wrote: through the subscription most of
            # the input arrives as cache writes and reads, not as input_tokens.
            """SELECT COALESCE(sum(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)
                                   + COALESCE(cache_read_tokens, 0) + COALESCE(cache_write_tokens, 0)), 0)
               FROM llm.calls
               WHERE started_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
                 AND meta ? 'run_id'"""
        )
        return int(n or 0)

    async def _caps(self, tx: Tx, run: dict[str, Any], charter: Charter) -> dict[str, Any]:
        token_cap = charter.limits.tokens_per_run
        priority = charter.priority
        if run["work_id"] is not None:
            w = await tx.one(
                """SELECT w.priority, w.budget_tokens, w.tokens_used, w.recurrence_of,
                          (SELECT COALESCE(sum(c.budget_tokens), 0) FROM work.work c WHERE c.parent_id = w.id)
                              AS given,
                          (SELECT e.token_cap_per_run FROM work.escrows e
                            WHERE e.work_id = COALESCE(w.recurrence_of, w.id) AND e.status = 'active') AS escrow_cap
                   FROM work.work w WHERE w.id = :id""",
                id=run["work_id"],
            )
            priority = w["priority"] if run["trigger"] != "message" else priority
            if w["budget_tokens"] is not None:
                token_cap = min(
                    token_cap, int(w["budget_tokens"]) - int(w["tokens_used"]) - int(w["given"])
                )
            if w["escrow_cap"] is not None:
                token_cap = min(token_cap, int(w["escrow_cap"]))
        return {"token_cap": max(token_cap, 0), "priority": priority}

    async def _model(
        self, tx: Tx, emp: dict[str, Any], charter: Charter
    ) -> tuple[str | None, str | None]:
        """(model, effort) the run asks for: the charter's default overrides the
        holding-wide default only; company, department, role and employee
        assignments override the charter (a new connection resets the model)."""
        rows = await tx.all(
            """SELECT a.scope_type, a.scope_ref, cn.key AS connection, a.model, a.effort
               FROM llm.assignments a LEFT JOIN llm.connections cn ON cn.id = a.connection_id"""
        )
        by = {(r["scope_type"], r["scope_ref"]): r for r in rows}
        holding = (await self.hub.companies.holding()).code
        co, dept, code = emp["company"], emp["department"], emp["code"]
        chain: list[tuple[str, str]] = [("company", co)]
        if dept:
            chain.append(("department", f"{co}-{dept}"))
        chain += [
            ("role", charter.role),
            ("role", f"{co}:{charter.role}"),
            ("role", code),
            ("role", f"{co}:{code}"),
        ]
        base = by.get(("holding", holding)) or {}
        connection = base.get("connection")
        model: str | None = charter.model
        effort: str | None = charter.effort
        for key in chain:
            a = by.get(key)
            if a is None:
                continue
            if a["connection"] is not None and a["connection"] != connection:
                connection, model = a["connection"], None
            if a["model"] is not None:
                model = a["model"]
            if a["effort"] is not None:
                effort = a["effort"]
        return model, effort

    async def _work_ref(self, tx: Tx, work_id: UUID | None) -> str | None:
        if work_id is None:
            return None
        ref: str | None = await tx.scalar("SELECT ref FROM work.work WHERE id = :id", id=work_id)
        return ref

    # ------------------------------------------------------------- execute --
    async def execute(self, run_id: str) -> dict[str, Any]:
        """All the steps of a claimed run. Returns metadata only."""
        lib = self.hub.charters
        async with await self._tx() as tx:
            run = await tx.one("SELECT * FROM agents.runs WHERE id = CAST(:id AS uuid)", id=run_id)
            if run["state"] != "running":
                return {"state": run["state"], "skipped": True}
            emp = await self._employee(tx, run["employee_id"])
            if lib is not None and lib.get(run["charter_role"]) is None:
                lib = await RD.overlay(tx, lib, emp["company_id"], running=True)
        charter = lib.get(run["charter_role"]) if lib is not None else None
        if charter is None:
            return await self.finish(run_id, "failed", "no_charter")
        expires = run["token_expires_at"] or datetime.now(UTC)
        token = agent_tokens.mint(
            self.hub.secrets.agent_token_key,
            emp["code"],
            str(run["id"]),
            ttl_s=max(60, int((expires - datetime.now(UTC)).total_seconds())),
        )
        rc = RunCtx(run=run, emp=emp, charter=charter, token=token, lib=lib)
        if run["work_id"] is not None:
            async with await self._tx() as tx:
                meta = await tx.scalar(
                    "SELECT run_meta FROM work.work WHERE id = :id", id=run["work_id"]
                )
            rc.run_meta = dict(meta) if isinstance(meta, dict) else {}
        deadline = time.monotonic() + self.s.agent_max_run_s
        try:
            outcome = await self._steps(rc, deadline)
        except Exception:
            log.exception("run failed", extra={"run_id": run_id})
            outcome = ("failed", "runtime_error", None)
        state, code, note = outcome
        return await self.finish(
            run_id, state, code, note=note, partial=state == "done" and code == "limit_reached"
        )

    async def _steps(self, rc: RunCtx, deadline: float) -> tuple[str, str | None, str | None]:
        run, charter = rc.run, rc.charter
        system = P.system_prompt(
            rc.lib or self.hub.charters,  # _common first, then the charter (file or draft)
            charter,
            await self._values(rc.emp),
            max_actions=self.s.agent_actions_per_step,
            answer_phase=charter.kind == "advisor" and run["trigger"] == "message",
            payloads=D.PAYLOADS,
            after_charter=await self._skills(rc),
        )
        # The owner's sealed standing orders (prompt 08 §2.7): the overseer's own
        # and those for every role, after the charter; a proposed one never.
        async with await self._tx() as tx:
            orders = O.orders_section(await O.sealed_orders(tx, charter.kind))
            if charter.role in oversight_share.ROLES and run["work_id"] is not None:
                proto = await tx.first(
                    """SELECT r.protocol_ref, p.severity FROM oversight.protocol_runs r
                       JOIN oversight.protocols p ON p.id = r.protocol_id
                       WHERE r.work_id = :w ORDER BY r.started_at DESC LIMIT 1""",
                    w=run["work_id"],
                )
                if proto is not None:
                    rc.oversight = {
                        "protocol": proto["protocol_ref"],
                        "severity": proto["severity"],
                    }
        if orders:
            system += "\n\n" + orders
        if await self._devil(rc):
            from hq_api.domain.advisor import DEVIL_INSTRUCTION

            system += "\n\n" + DEVIL_INSTRUCTION
        text, image_ids = await self._context(rc)
        rc.messages = [{"role": "user", "content": await self._with_images(rc, text, image_ids)}]
        live_thread = await self._reply_thread(rc)
        advisor = charter.kind == "advisor"
        steps_cap = int(run["steps_cap"] or charter.limits.steps_per_run)
        token_cap = rc.token_cap
        per_step = charter.limits.tokens_per_step
        # The advisor's streamed answer is a step too: it counts inside the cap.
        research_steps = steps_cap - 1 if advisor and live_thread else steps_cap
        if live_thread:
            await self._live(live_thread, rc, "reply.started", {})
        done = False
        n = 0
        bad_outputs = 0
        while n < research_steps and not done:
            if await self._locked(run["company_id"]):
                return (
                    "refused",
                    "locked",
                    "a kill switch or a deploy freeze was engaged during the run",
                )
            if time.monotonic() > deadline:
                break
            left = token_cap - rc.used_tokens
            if left < min(per_step, token_cap) // 4 or left <= 0:
                break
            # Hard: the next prompt plus its capped output must fit in what is left.
            room = min(per_step, left - prompt_tokens(system, rc.messages))
            if room < MIN_OUTPUT_TOKENS:
                break
            if await self._daily_cap_reached():
                return "failed", "daily_cap", "the hub's daily agent token cap was reached"
            n += 1
            self.heartbeat()
            call = await self._model_step(rc, system, n, max_output=room)
            if not call.ok:
                await self._book(rc, call)  # a failed call's tokens are spent too
                await self._record_step(rc, n, "", [], call)
                if call.code in ("quota_throttled", "company_locked", "budget_exhausted"):
                    return "failed", str(call.code), None
                return "failed", (call.code or "model_error")[:40], None
            await self._book(rc, call)
            try:
                step = P.parse_step(call.structured, call.text, self.s.agent_actions_per_step)
            except P.BadOutput:
                bad_outputs += 1
                await self._record_step(rc, n, "", [], call)
                if bad_outputs >= 2:
                    return "failed", "invalid_output", None
                rc.messages += [
                    {"role": "assistant", "content": scrub((call.text or "")[:4000]) or "{}"},
                    {
                        "role": "user",
                        "content": "Your answer was not the JSON object of the protocol. "
                        "Answer again with exactly that object.",
                    },
                ]
                continue
            summary = scrub(step.summary_fa)  # stored and shown to the owner
            rc.summaries.append(summary)
            results = []
            for i, action in enumerate(step.actions):
                self.heartbeat()
                out = await self.gateway.call(rc.token, n, i, action.tool, action.args)
                results.append({"tool": action.tool, **out})
                await self._after_action(rc, action, out, live_thread)
            await self._record_step(rc, n, summary, results, call)
            # "done" next to an action refused for its arguments is not done: the
            # model gets the field errors and one more step to fix them.
            fixable = any(r.get("code") == "invalid_args" for r in results)
            done = step.done and not fixable
            rc.messages += [
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "summary_fa": summary,
                            "actions": [{"tool": a.tool, "args": a.args} for a in step.actions],
                            "done": step.done,
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "user",
                    "content": await self._with_images(
                        rc,
                        P.trim(
                            P.render_results(
                                results,
                                steps_left=steps_cap - n,
                                tokens_left=max(token_cap - rc.used_tokens, 0),
                            ),
                            CONTEXT_CHARS,
                        ),
                        viewed_images(results),
                    ),
                },
            ]
        if advisor and live_thread and rc.replied is None:
            return await self._answer(rc, system, n + 1, live_thread, deadline)
        if live_thread and rc.replied is None and not done:
            await self._live(live_thread, rc, "reply.failed", {"code": "no_reply"})
        if done:
            return "done", None, None
        return await self._partial(rc, n)

    async def _daily_cap_reached(self) -> bool:
        """The hub's daily agent token cap, checked before EVERY model call
        (prompt 5.1 §2.6), not only when a run is claimed."""
        if self.s.agent_daily_token_cap <= 0:  # 0 = nothing at all (prompt 08.1)
            return True
        async with await self._tx() as tx:  # every company's runs (RLS)
            return await self._spent_today(tx) >= self.s.agent_daily_token_cap

    async def _model_step(
        self, rc: RunCtx, system: str, n: int, *, max_output: int | None = None
    ) -> ModelCall:
        run, emp, charter = rc.run, rc.emp, rc.charter
        body = {
            "company_code": emp["company"],
            "actor_ref": emp["code"],
            "work_ref": await self._scalar_work_ref(run["work_id"]),
            "department": emp["department"],
            "role": charter.role,
            "employee": emp["code"],
            "task_class": self._task_class(rc),
            "priority": run["priority"],
            "system": system,
            "messages": rc.messages,
            "json_schema": P.STEP_SCHEMA,
            "timeout_s": self.s.agent_step_timeout_s,
            "meta": {
                "charter": f"{charter.role}@{charter.version}",
                "run_id": str(run["id"]),
                "step": n,
                "trigger": run["trigger"],
                "skills": rc.skills,
                "addenda": rc.addenda,
                **rc.oversight,
                **self._zone(rc),
            },
        }
        if max_output:
            body["max_output_tokens"] = max_output  # the step's hard cap (§2.6)
        if run["model"]:
            body["model"] = run["model"]
        if run["effort"]:
            body["effort"] = run["effort"]
        return await self._with_heartbeat(self.router.run(body, self.s.agent_step_timeout_s))

    def _task_class(self, rc: RunCtx) -> str:
        # ⟨1.5⟩ a run the code made for one purpose names its class (prompt 12:
        # advisor_memo, advisor_proactive...); never one an agent chose.
        named = rc.run_meta.get("task_class")
        if isinstance(named, str) and named in RUN_TASK_CLASSES:
            return named
        if rc.charter.kind in TASK_CLASS_OF_KIND:
            return TASK_CLASS_OF_KIND[rc.charter.kind]
        if rc.charter.role in TASK_CLASS_OF_ROLE:
            return TASK_CLASS_OF_ROLE[rc.charter.role]
        return ALERT_TASK if rc.run["trigger"] == "alert" else "general"

    @staticmethod
    def _zone(rc: RunCtx) -> dict[str, str]:
        """The owner-zone flag llm-router reads (prompt 12 §15): `auto` stops
        at the zone's share, `direct` (the owner asked) always runs."""
        zone = rc.run_meta.get("owner_zone")
        return {"owner_zone": zone} if zone in ("auto", "direct") else {}

    async def _devil(self, rc: RunCtx) -> bool:
        """The advisor's devil's advocate for this run only (contract §21.1):
        a devil memo, or the owner's latest message in thread A asked for it."""
        if rc.charter.kind != "advisor":
            return False
        if rc.run_meta.get("mode") == "devil":
            return True
        if rc.run["trigger"] != "message" or rc.run["thread_id"] is None:
            return False
        async with await self._tx() as tx:
            mode = await tx.scalar(
                """SELECT m.meta->>'mode' FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
                   WHERE m.thread_id = :t AND t.code = 'A' AND m.author_kind = 'owner'
                   ORDER BY m.seq DESC LIMIT 1""",
                t=rc.run["thread_id"],
            )
        return bool(mode == "devil")

    async def _with_heartbeat(self, aw: Awaitable[ModelCall]) -> ModelCall:
        """A model call (a step, or the advisor's streamed answer) beating the
        activity's heartbeat while it waits, far inside its 3-minute timeout."""
        task = asyncio.ensure_future(aw)
        while True:
            done, _ = await asyncio.wait({task}, timeout=self.heartbeat_every_s)
            if done:
                return task.result()
            self.heartbeat()

    async def _scalar_work_ref(self, work_id: UUID | None) -> str | None:
        if work_id is None:
            return None
        async with await self._tx() as tx:
            return await self._work_ref(tx, work_id)

    async def _after_action(
        self, rc: RunCtx, action: P.Action, out: dict[str, Any], live_thread: str | None
    ) -> None:
        if out.get("outcome") != "ok":
            return
        if action.tool == "deliver":
            rc.delivered = True
        if action.tool in ("message.thread", "message.owner") and live_thread:
            args = action.args if isinstance(action.args, dict) else {}
            target = args.get("thread") if action.tool == "message.thread" else live_thread
            if target == live_thread and out.get("ref"):
                body = args.get("body_md")
                if isinstance(body, str):  # masked like everything the owner sees live
                    # cut before masking: a 50,000-char body never blocks the event loop
                    text = scrub(body[:LIVE_SCRUB_CHARS])[:4000]
                    await self._live(live_thread, rc, "reply.delta", {"text": text})
                rc.replied = str(out["ref"])
                await self._live(live_thread, rc, "reply.done", {"message_ref": rc.replied})

    async def _answer(
        self, rc: RunCtx, system: str, n: int, thread: str, deadline: float
    ) -> tuple[str, str | None, str | None]:
        """The advisor's answer, streamed live, then stored with its citations.
        It is a step like the others: lock, time, tokens and the daily cap are
        checked before it, and its output is capped like a step's."""
        system = system + "\n\n" + P.ANSWER_PHASE
        messages = [*rc.messages, {"role": "user", "content": "Write the answer to the owner now."}]
        left = rc.token_cap - rc.used_tokens
        room = min(rc.charter.limits.tokens_per_step, left - prompt_tokens(system, messages))
        stop: tuple[str, str | None, str | None] | None = None
        if await self._locked(rc.run["company_id"]):
            stop = (
                "refused",
                "locked",
                "a kill switch or a deploy freeze was engaged during the run",
            )
        elif time.monotonic() > deadline:
            stop = ("failed", "time_limit", None)
        elif room < MIN_OUTPUT_TOKENS:
            stop = ("failed", "token_cap", None)
        elif await self._daily_cap_reached():
            stop = ("failed", "daily_cap", "the hub's daily agent token cap was reached")
        if stop is not None:
            await self._live(thread, rc, "reply.failed", {"code": stop[1]})
            return stop
        flt = P.StreamFilter()
        masked = P.ScrubBuffer()
        chunks: list[str] = []
        assert self.live is not None

        async with self.live.open(thread, rc.token) as send:

            def on_delta(text: str) -> None:
                self.heartbeat()  # a long answer keeps the activity alive (§2.5)
                chunks.append(text)
                visible = masked.feed(flt.feed(text))
                if visible:
                    send("reply.delta", {"text": visible})

            body = {
                "company_code": rc.emp["company"],
                "actor_ref": rc.emp["code"],
                "role": rc.charter.role,
                "employee": rc.emp["code"],
                "task_class": self._task_class(rc),
                "priority": rc.run["priority"],
                "system": system,
                "messages": messages,
                "timeout_s": self.s.agent_step_timeout_s,
                "max_output_tokens": room,
                "meta": {
                    "charter": f"{rc.charter.role}@{rc.charter.version}",
                    "run_id": str(rc.run["id"]),
                    "step": n,
                    "trigger": rc.run["trigger"],
                    "purpose": "answer",
                    "skills": rc.skills,
                    "addenda": rc.addenda,
                    **self._zone(rc),
                },
            }
            if rc.run["model"]:
                body["model"] = rc.run["model"]
            if rc.run["effort"]:
                body["effort"] = rc.run["effort"]
            self.heartbeat()
            call = await self._with_heartbeat(
                self.router.stream(body, self.s.agent_step_timeout_s, on_delta)
            )
            tail = masked.feed(flt.flush()) + masked.flush()
            if tail:
                send("reply.delta", {"text": tail})
            if not call.ok:
                await self._book(rc, call)  # a failed call's tokens are spent too
                await self._record_step(rc, n, "", [], call)
                send("reply.failed", {"code": call.code or "model_error"})
                return "failed", (call.code or "model_error")[:40], None
            await self._book(rc, call)
            text = call.text or "".join(chunks)
            answer, citations = P.split_answer(text)
            if not answer:
                await self._record_step(rc, n, "", [], call)
                send("reply.failed", {"code": "empty_answer"})
                return "failed", "empty_answer", None
            out = await self.gateway.call(
                rc.token,
                n,
                0,
                "message.thread",
                {"thread": thread, "body_md": answer, "citations": citations},
            )
            await self._record_step(
                rc, n, "پاسخ نهایی به مدیر کل نوشته شد", [{"tool": "message.thread", **out}], call
            )
            if out.get("outcome") == "ok":
                rc.replied = str(out.get("ref"))
                send("reply.done", {"message_ref": rc.replied})
                return "done", None, None
            send("reply.failed", {"code": out.get("code") or "not_stored"})
            return "failed", str(out.get("code") or "not_stored")[:40], None

    async def _partial(self, rc: RunCtx, n: int) -> tuple[str, str | None, str | None]:
        """Out of steps or tokens before `done`: what was done so far, delivered."""
        work_ref = await self._scalar_work_ref(rc.run["work_id"])
        if rc.delivered or work_ref is None or "deliver" not in rc.charter.tools:
            return ("done" if rc.delivered else "failed"), "limit_reached", None
        async with await self._tx() as tx:
            status = await tx.scalar("SELECT status FROM work.work WHERE ref = :r", r=work_ref)
        if status not in ("queued", "in_progress", "waiting"):
            return "done", "limit_reached", None
        body = "سقف قدم یا توکن این اجرا پیش از پایان کار رسید. آنچه انجام شد:\n\n" + "\n".join(
            f"{i}. {s}" for i, s in enumerate(rc.summaries, 1) if s
        )
        out = await self.gateway.call(
            rc.token,
            max(n, 1),
            self.s.agent_actions_per_step - 1,
            "deliver",
            {"work_ref": work_ref, "title_fa": "خروجی ناقص: سقف اجرا رسید", "body_md": body},
        )
        if out.get("outcome") == "ok":
            return "done", "limit_reached", "partial deliverable " + str(out.get("ref") or "")
        return "failed", "limit_reached", None

    # ------------------------------------------------------------- context --
    async def _skills(self, rc: RunCtx) -> str:
        """The role's active skills and the owner's sealed rules for the role
        and for this employee, after the charter (prompt 08 §6-§7). Only what
        really went into the prompt is kept on the run and named on each model
        call (8.1 §2.12-§2.13: the section is bounded, at most 30 of each)."""
        async with await self._tx() as tx:
            active = await SK.active_for(
                tx, rc.charter.role, rc.emp["company"], rc.emp["department"]
            )
            addenda = await AC.addenda_for(tx, rc.charter.role, rc.emp["code"])
            sec = SK.prompt_section(active, addenda)
            rc.skills = sec.skills
            rc.addenda = [str(a["ref"]) for a in sec.addenda]  # teaching refs (llm meta)
            # ⟨1.6⟩ the department's identity comes first in this section: after
            # the charter, before the skills (contract §22.1); its version is kept.
            identity, identity_doc = await DM.identity(
                tx,
                await tx.scalar(
                    "SELECT department_id FROM core.employees WHERE id = :e",
                    e=rc.run["employee_id"],
                ),
            )
            await tx.exec(
                """UPDATE agents.runs SET skills = :s, addenda = :a, identity_doc = :doc
                   WHERE id = :id""",
                s=rc.skills,
                a=[a["id"] for a in sec.addenda],
                doc=identity_doc,
                id=rc.run["id"],
            )
        return "\n\n".join(x for x in (identity, sec.text) if x)

    async def _values(self, emp: dict[str, Any]) -> dict[str, str]:
        holding = await self.hub.companies.holding()
        async with await self._tx() as tx:
            tz = (
                await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
            )
        today = datetime.now(UTC).date()
        return {
            "employee_code": emp["code"],
            "employee_title_fa": emp["title_fa"],
            "company_code": emp["company"],
            "company_name_fa": emp["company_name_fa"] or emp["company"],
            "company_name_en": emp["company_name_en"] or emp["company"],
            "holding_code": holding.code,
            "department_code": emp["department"] or "",
            "department_name_fa": emp["department_name_fa"] or "",
            "manager_code": emp["manager"] or "owner",
            "today_jalali": jalali_long(today),
            "today_gregorian": today.isoformat(),
            "owner_timezone": tz,
        }

    async def read_scope(self, rc: RunCtx) -> list[UUID]:
        """The companies a run may read: its charter's scope (prompt 5.1 §1.1),
        every company for a holding charter in the holding, else its own."""
        holding = await self.hub.companies.holding()
        # ⟨1.6⟩ a role draft reads its own company only, whatever its scope says
        # (as its principal does: security/deps.py reads the files only)
        filed = self.hub.charters is not None and rc.charter.role in self.hub.charters.roles
        if rc.charter.scope == "holding" and filed and rc.emp["company_id"] == holding.id:
            return await self.hub.companies.ids()
        return [rc.emp["company_id"]]

    async def _context(self, rc: RunCtx) -> tuple[str, list[UUID]]:
        """The trigger and what the role needs to act on it (never a secret),
        and the images it should see (attached photos, a video's key frames,
        newest first). Read in a transaction scoped to the charter (RLS), and
        every record a message points at is filtered by that scope too."""
        run, emp = rc.run, rc.emp
        images: list[UUID] = []
        parts = [f"# Trigger\n{run['trigger']} ({run['reason']})"]
        scope = await self.read_scope(rc)
        async with self.hub.db.tx(scope) as tx:
            lock = await tx.scalar("SELECT control.lock_state(:co)", co=run["company_id"])
            presence = await tx.one("SELECT khalvat FROM owner.presence WHERE id = 1")
            parts.append(
                f"Company {emp['company']}: lock={lock or 'none'}; owner in Khalvat: {presence['khalvat']}"
            )
            if run["work_id"] is not None:
                parts.append(
                    "# Work\n" + await masked_json(await self._work_brief(tx, run["work_id"]))
                )
            if run["thread_id"] is not None:
                msgs = await tx.all(
                    """SELECT ref, author_kind, author_code, body, links, attachments, kind
                       FROM msg.messages WHERE thread_id = :t ORDER BY seq DESC LIMIT :n""",
                    t=run["thread_id"],
                    n=THREAD_MESSAGES,
                )
                seen = await self._visible_links(tx, msgs, scope)
                media = await self._attachments(tx, msgs)
                for m in msgs:  # newest first: the latest photos are the ones seen
                    for fid in m["attachments"] or []:
                        images += media.get(fid, ("", []))[1]
                lines = []
                for m in reversed(msgs):
                    who = "owner" if m["author_kind"] == "owner" else m["author_code"]
                    shown = {k: v for k, v in (m["links"] or {}).items() if (k, v) in seen}
                    links = f" links={json.dumps(shown)}" if shown else ""
                    voice = " (spoken)" if m["kind"] == "voice_transcript" else ""
                    att = "".join(
                        f"\n    attached {media[f][0]}"
                        for f in m["attachments"] or []
                        if f in media
                    )
                    lines.append(f"[{m['ref']}] {who}{voice}{links}: {m['body'][:3000]}{att}")
                parts.append(
                    "# Conversation (oldest first; answer the owner's latest)\n" + "\n".join(lines)
                )
                decision = next(
                    (
                        m["links"]["decision"]
                        for m in msgs
                        if ("decision", (m["links"] or {}).get("decision")) in seen
                    ),
                    None,
                )
                if decision:
                    d = await tx.first(
                        """SELECT d.ref, c.code AS company, d.kind, d.title, d.what, d.why, d.risk, d.reversible,
                                  d.quota_tokens, d.quota_usd, d.payload, d.status, d.proposer_code
                           FROM cartable.decisions d JOIN core.companies c ON c.id = d.company_id
                           WHERE d.ref = :r AND d.company_id = ANY(:scope)""",
                        r=decision,
                        scope=scope,
                    )
                    if d:
                        parts.append("# Decision card to review\n" + await masked_json(d))
                errand = next(
                    (
                        m["links"]["errand"]
                        for m in msgs
                        if ("errand", (m["links"] or {}).get("errand")) in seen
                    ),
                    None,
                )
                if errand:  # ⟨1.4⟩ the owner's errand this conversation is about (§18.3)
                    e = await tx.first(
                        """SELECT e.ref, e.title_fa, e.brief_md, e.status, e.due_at, e.steps,
                                  (SELECT d.ref FROM cartable.decisions d WHERE d.id = e.decision_id)
                                      AS decision
                           FROM owner.errands e WHERE e.ref = :r AND e.company_id = ANY(:scope)""",
                        r=errand,
                        scope=scope,
                    )
                    if e:
                        steps = list(e.pop("steps") or [])
                        e["brief_md"] = (e["brief_md"] or "")[:4000]
                        e["steps_done"] = len(steps)
                        e["last_steps"] = [
                            {"kind": s.get("kind"), "summary_fa": str(s.get("summary_fa"))[:300]}
                            for s in steps[-5:]
                        ]
                        parts.append(
                            "# Errand (record its steps with errand.step, end with errand.finish)\n"
                            + await masked_json(e)
                        )
            notes = await tx.all(
                "SELECT note FROM core.employee_memory WHERE employee_id = :e ORDER BY id DESC LIMIT 5",
                e=emp["id"],
            )
        if notes:
            parts.append(
                "# Your memory (latest first)\n" + "\n".join(f"- {n['note'][:500]}" for n in notes)
            )
        # What a model reads never carries a secret or personal data (prompt 5.1
        # §2.1): cut first (bounded work), masked, then trimmed to size.
        raw = "\n\n".join(parts)
        text = P.trim(await scrub_async(raw[: CONTEXT_CHARS * 2]), CONTEXT_CHARS)
        return text, list(dict.fromkeys(images))

    async def _attachments(
        self, tx: Tx, msgs: list[dict[str, Any]]
    ) -> dict[UUID, tuple[str, list[UUID]]]:
        """For each attached file the run may read (RLS): a line for the prompt
        (kind, size, its transcript; never its name, never EXIF) and the image
        files to show: a photo's `agent` variant, a video's key frames (or its
        poster). Audio and video reach the model as text and frames only."""
        ids = list({f for m in msgs for f in m["attachments"] or []})
        if not ids:
            return {}
        rows = await tx.all(
            F.FILE_SQL + " WHERE f.id = ANY(:ids) AND f.variant = 'original'", ids=ids
        )
        shown = await tx.all(
            """SELECT parent_id, id, variant FROM files.files
               WHERE parent_id = ANY(:ids) AND variant IN ('agent', 'frame', 'poster')
               ORDER BY parent_id, frame_at_s NULLS FIRST, created_at""",
            ids=ids,
        )
        out: dict[UUID, tuple[str, list[UUID]]] = {}
        for r in rows:
            mine = [v for v in shown if v["parent_id"] == r["id"]]
            ref = F.render(r)
            if ref.kind == "image":
                line = f"image {ref.width}x{ref.height} (file:{ref.id}; shown below)"
                pics = [v["id"] for v in mine if v["variant"] == "agent"]
            elif ref.kind == "video":
                frames = [v["id"] for v in mine if v["variant"] == "frame"]
                pics = frames or [v["id"] for v in mine if v["variant"] == "poster"]
                line = f"video {ref.duration_s or 0:.0f} s (file:{ref.id}; {len(pics)} key frames shown below)"
            elif ref.kind == "audio":
                line, pics = f"audio {ref.duration_s or 0:.0f} s (file:{ref.id})", []
            else:
                line, pics = f"document {ref.mime} (file:{ref.id})", []
            if ref.status == "processing":
                line += " - still being processed"
            if ref.transcript:
                line += f"\n    transcript: {ref.transcript[:4000]}"
            out[r["id"]] = (line, pics)
        return out

    async def _with_images(self, rc: RunCtx, text: str, ids: list[UUID]) -> Any:
        """A user turn: the text alone, or the text and image blocks (bytes read
        under the run's read scope, at most MAX_IMAGES in the whole run)."""
        room = MAX_IMAGES - rc.images
        if not ids or room <= 0:
            return text
        async with self.hub.db.tx(await self.read_scope(rc)) as tx:
            rows = await tx.all(
                """SELECT id, mime, storage_key FROM files.files
                   WHERE id = ANY(:ids) AND kind = 'image'
                     AND variant IN ('agent', 'frame', 'poster', 'thumb')""",
                ids=ids,
            )
        by_id = {r["id"]: r for r in rows}
        blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for fid in ids:
            r = by_id.get(fid)
            if r is None or len(blocks) > room:
                continue
            data = await self.hub.storage.get(r["storage_key"])
            blocks.append(
                {
                    "type": "image",
                    "media_type": r["mime"],
                    "data": base64.b64encode(data).decode("ascii"),
                }
            )
        rc.images += len(blocks) - 1
        return blocks if len(blocks) > 1 else text

    async def _visible_links(
        self, tx: Tx, msgs: list[dict[str, Any]], scope: list[UUID]
    ) -> set[tuple[str, Any]]:
        """The (kind, ref) links of `msgs` that resolve inside the run's read
        scope; a pointer to anything else never reaches the prompt."""
        seen: set[tuple[str, Any]] = set()
        for m in msgs:
            corrects = (m["links"] or {}).get("corrects")
            if corrects:
                seen.add(("corrects", corrects))  # a message of this same thread
        for kind, table in LINK_TABLES.items():
            refs = sorted(
                {
                    str(m["links"][kind])
                    for m in msgs
                    if isinstance((m["links"] or {}).get(kind), str)
                }
            )
            if refs:
                rows = await tx.all(
                    f"SELECT ref FROM {table} WHERE ref = ANY(:refs) AND company_id = ANY(:scope)",  # noqa: S608
                    refs=refs,
                    scope=scope,
                )
                seen |= {(kind, r["ref"]) for r in rows}
        return seen

    async def _work_brief(self, tx: Tx, work_id: UUID) -> dict[str, Any]:
        w = await tx.one(
            """SELECT w.ref, c.code AS company, d.code AS department, w.kind, w.title, w.brief, w.priority,
                      w.status, w.depth, w.due_at, w.budget_tokens, w.tokens_used, w.evidence,
                      w.created_by_kind || ':' || w.created_by_code AS created_by,
                      (SELECT ref FROM work.work p WHERE p.id = w.parent_id) AS parent
               FROM work.work w JOIN core.companies c ON c.id = w.company_id
               LEFT JOIN core.departments d ON d.id = w.department_id WHERE w.id = :id""",
            id=work_id,
        )
        w["children"] = await tx.all(
            """SELECT w.ref, e.code AS assignee, w.status, w.title FROM work.work w
               LEFT JOIN core.employees e ON e.id = w.assignee_id WHERE w.parent_id = :id ORDER BY w.created_at""",
            id=work_id,
        )
        w["deliverables"] = await tx.all(
            """SELECT d.ref, d.title, left(d.summary, 400) AS summary, e.code AS producer
               FROM cartable.deliverables d JOIN core.employees e ON e.id = d.producer_id
               WHERE d.work_id = ANY(ARRAY(SELECT id FROM work.work WHERE id = :id OR parent_id = :id))
               ORDER BY d.created_at""",
            id=work_id,
        )
        w["brief"] = (w["brief"] or "")[:8000]
        return w

    async def _reply_thread(self, rc: RunCtx) -> str | None:
        """The thread a reply goes to live: the owner's message trigger."""
        if rc.run["trigger"] != "message" or rc.run["thread_id"] is None or self.live is None:
            return None
        async with await self._tx() as tx:
            code: str | None = await tx.scalar(
                "SELECT code FROM msg.threads WHERE id = :t", t=rc.run["thread_id"]
            )
        return code

    async def _live(self, thread: str, rc: RunCtx, type_: str, data: dict[str, Any]) -> None:
        if self.live is None:
            return
        try:
            async with self.live.open(thread, rc.token) as send:
                send(type_, data)
        except Exception:  # noqa: BLE001 - a live update never fails the run
            log.warning("live update not sent", extra={"type": type_})

    async def _locked(self, company_id: UUID) -> bool:
        """A kill switch (holding or company) or a deploy freeze (contract §16.6)."""
        async with self.hub.db.raw() as tx:
            state = await tx.scalar("SELECT control.lock_state(:co)", co=company_id)
        return state is not None

    # ------------------------------------------------------------ records --
    async def _book(self, rc: RunCtx, call: ModelCall) -> None:
        """A step's usage on the run and on its work (budget accounting)."""
        rc.used_tokens += call.tokens
        usd = Decimal(call.equiv_cost_usd or 0) + Decimal(call.cost_usd or 0)
        async with await self._tx() as tx:
            await tx.exec(
                """UPDATE agents.runs SET input_tokens = input_tokens + :i, output_tokens = output_tokens + :o,
                       cache_read_tokens = cache_read_tokens + :cr, cache_write_tokens = cache_write_tokens + :cw,
                       equiv_cost_usd = equiv_cost_usd + :eq, cost_usd = cost_usd + :c
                   WHERE id = :id""",
                id=rc.run["id"],
                i=call.input_tokens,
                o=call.output_tokens,
                cr=call.cache_read_tokens,
                cw=call.cache_write_tokens,
                eq=Decimal(call.equiv_cost_usd or 0),
                c=Decimal(call.cost_usd or 0),
            )
        if rc.run["work_id"] is not None and call.tokens:
            try:
                async with await self._tx() as tx:
                    await tx.exec(
                        "UPDATE work.work SET tokens_used = tokens_used + :t, usd_used = usd_used + :u WHERE id = :id",
                        id=rc.run["work_id"],
                        t=call.tokens,
                        u=usd,
                    )
            except DBAPIError as exc:
                if sqlstate_of(exc) != "HQB01":  # only "no budget left" ends the run's tokens
                    raise
                log.warning(
                    "work spending refused (budget used up)", extra={"run_id": str(rc.run["id"])}
                )
                rc.used_tokens = max(rc.used_tokens, rc.token_cap)

    async def _record_step(
        self, rc: RunCtx, n: int, summary: str, results: list[dict[str, Any]], call: ModelCall
    ) -> None:
        actions = [
            {
                "tool": str(r.get("tool"))[:40],
                "class": r.get("class"),
                "outcome": r.get("outcome"),
                **({"ref": str(r["ref"])[:80]} if r.get("ref") else {}),
                **({"code": str(r["code"])[:60]} if r.get("code") else {}),
            }
            for r in results
        ]
        usage = {
            "input": call.input_tokens,
            "output": call.output_tokens,
            "cache_read": call.cache_read_tokens,
            "cache_write": call.cache_write_tokens,
            "model": call.model,
            "status": call.status,
        }
        async with await self._tx() as tx:
            await tx.exec(
                """INSERT INTO agents.steps (run_id, company_id, n, summary_fa, actions, usage, call_id)
                   VALUES (:r, :co, :n, :s, CAST(:a AS jsonb), CAST(:u AS jsonb), CAST(:c AS uuid))
                   ON CONFLICT (run_id, n) DO NOTHING""",
                r=rc.run["id"],
                co=rc.run["company_id"],
                n=n,
                s=summary[:2000],
                a=json.dumps(actions, ensure_ascii=False),
                u=json.dumps(usage),
                c=call.call_id,
            )
            await tx.exec(
                "UPDATE agents.runs SET steps = greatest(steps, :n) WHERE id = :id",
                id=rc.run["id"],
                n=n,
            )
            await events.emit(
                tx,
                rc.emp["company"],
                "run.step",
                str(rc.run["id"]),
                {"employee": rc.emp["code"], "n": n, "actions": [a["tool"] for a in actions]},
            )

    async def _activity(self, tx: Tx, emp: dict[str, Any], activity: str, note: str | None) -> None:
        await tx.exec(
            "UPDATE core.employees SET activity = :a, activity_note = :n, activity_at = now() WHERE id = :id",
            id=emp["id"],
            a=activity,
            n=note,
        )
        await events.emit(
            tx, emp["company"], "activity.changed", emp["code"], {"activity": activity}
        )

    # -------------------------------------------------------------- finish --
    async def finish(
        self,
        run_id: str,
        state: str,
        code: str | None,
        *,
        note: str | None = None,
        partial: bool = False,
    ) -> dict[str, Any]:
        async with await self._tx() as tx:
            run = await tx.one(
                "SELECT * FROM agents.runs WHERE id = CAST(:id AS uuid) FOR UPDATE", id=run_id
            )
            if run["state"] in FINAL:
                return {"state": run["state"], "code": run["error_code"]}
            emp = await self._employee(tx, run["employee_id"])
            await self._finish(tx, run, emp, state, code, note=note, partial=partial)
        return {"state": state, "code": code}

    async def _finish(
        self,
        tx: Tx,
        run: dict[str, Any],
        emp: dict[str, Any],
        state: str,
        code: str | None,
        *,
        note: str | None,
        start: bool = True,
        partial: bool = False,
    ) -> None:
        await tx.exec(
            """UPDATE agents.runs SET state = :st, error_code = :code, note = :note, partial = :partial,
                   finished_at = now(), started_at = COALESCE(started_at, CASE WHEN :st = 'done' THEN now() END)
               WHERE id = :id""",
            id=run["id"],
            st=state,
            code=code,
            note=(note or "")[:1000] or None,
            partial=partial,
        )
        busy = await tx.scalar(
            "SELECT 1 FROM agents.runs WHERE employee_id = :e AND state = 'running' AND id <> :id",
            e=emp["id"],
            id=run["id"],
        )
        if not busy and start:
            await self._activity(tx, emp, "sleeping" if state != "failed" else "error", None)
        if state == "refused":
            await audit.record(
                tx,
                audit.SYSTEM,
                company_id=run["company_id"],
                action="run.refused",
                action_class="A0",
                target_kind="run",
                target_ref=str(run["id"]),
                summary=f"{emp['code']}: {code}"[:500],
            )
        await events.emit(
            tx,
            emp["company"],
            "run.finished",
            str(run["id"]),
            {"employee": emp["code"], "state": state, "code": code, "partial": partial},
        )
