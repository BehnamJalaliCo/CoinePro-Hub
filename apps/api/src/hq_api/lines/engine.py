"""The line engine (contract §30.3): runs, steps, gates, caps.

One Temporal workflow `LineRun` per run calls `advance()` again and again;
each call does at most one step:

- the run's next pending step, in order, through `base.REGISTRY[kind].run(ctx)`
  with its own timeout and attempts (a step's StepFailed with `retry` is tried
  again while attempts remain; `retry=False` fails at once; an optional step
  that fails is skipped and the run goes on);
- an adapter with `reruns_input` (dedupe, quality) that fails with `retry`
  makes the step that wrote its input run again first (with a hint of why),
  up to its own `max_attempts`;
- a gate holds the run (`waiting`) and raises a `line_publish` card (A3): a
  `seal` step, a step with `gate: owner|ceo`, and a draft line's `publish`;
  the card's decision lets the run go on or ends it. A dry run has no gate;
- an adapter may answer `data.wait == "callback"` (the n8n step): the step
  waits for its signed callback (`on_callback`);
- before each step the holding's lock or kill switch, the company's daily
  token cap, the line's `tokens_per_run` and `opus_per_day` stop the run
  (`skipped`, with the reason in plain Persian); `runs_per_day` is counted
  when a run is made.

Costs are summed from the adapters' StepOutput (the router and the
substitutes already wrote the ledger: nothing is written to it here). The
database is the truth: a run the workflow lost is picked up by the tick.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import gate, recurrence
from hq_api.domain.gov_common import owner_tz
from hq_api.errors import ApiError
from hq_api.lines import adapters, learning, store
from hq_api.lines import templates as T
from hq_api.lines.base import REGISTRY, StepContext, StepFailed, StepOutput
from hq_api.principal import Principal

log = logging.getLogger("hq_api.lines.engine")

SERVICE = Principal(kind="service", code="lines", role="service")
WORKFLOW = "LineRun"
TERMINAL = ("done", "failed", "skipped", "cancelled")
LEAVING = ("publish", "deliver")  # ctx.dry: they answer without leaving
WAIT_MAX = timedelta(days=7)  # a gate or callback unanswered this long ends the run
LOOKBACK = timedelta(minutes=30)  # a schedule's occurrence the tick still makes
KICK_AFTER = timedelta(minutes=2)  # an open run no workflow moved, started again
CALLBACK = "callback"
CALLBACK_TRIES = 20  # an n8n answer that beat the step's parking looks again this often
CALLBACK_PAUSE_S = 0.5
TEST_TIMEOUT_S = 300  # the owner's «آزمودن» of one step waits at most this long
OVERDUE = "SELECT CAST(:t AS timestamptz) < now() - CAST(:w AS interval)"
LOCK_FA = {
    "holding": "هلدینگ قفل است (کلید توقف)؛ اجرا انجام نشد.",
    "company": "این شرکت قفل است؛ اجرا انجام نشد.",
    "deploy_freeze": "زمان استقرار است و کارها نگه داشته شده‌اند.",
}
VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\s*\}\}")


# ------------------------------------------------------------------ prompts --
def lookup(env: dict[str, Any], path: list[str]) -> Any:
    cur: Any = env
    for part in path:
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def render_prompt(text: str | None, env: dict[str, Any]) -> tuple[str | None, list[str]]:
    """`{{a.b.c}}` replaced from `env` by plain dotted lookup (never code); a
    variable with no value renders empty and is named in the second item."""
    if text is None:
        return None, []
    missing: list[str] = []

    def sub(m: re.Match[str]) -> str:
        v = lookup(env, m.group(1).split("."))
        if v is None or v == "" or v == [] or v == {}:
            missing.append(m.group(1))
            return ""
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return str(v)

    return VAR.sub(sub, text), list(dict.fromkeys(missing))


def output_of(s: dict[str, Any]) -> StepOutput:
    o = s["output"] or {}
    return StepOutput(
        text=o.get("text"),
        file_id=o.get("file_id"),
        files=tuple(str(f) for f in o.get("files") or []),
        data=dict(o.get("data") or {}),
        via=s["via"],
        tokens=int(s["tokens"]),
        usd_equiv=Decimal(s["usd_equiv"]),
    )


def dump_output(out: StepOutput) -> str:
    return store.dumps(
        {"text": out.text, "file_id": out.file_id, "files": list(out.files), "data": out.data}
    )


async def library_env(tx: Tx, ids: list[Any]) -> tuple[tuple[dict[str, Any], ...], dict[str, str]]:
    rows = await store.assets_of(tx, ids)
    assets = tuple(
        {
            "id": str(a["id"]),
            "kind": a["kind"],
            "title_fa": a["title_fa"],
            "config": a["config"] or {},
            "files": [str(f) for f in a["files"] or []],
        }
        for a in rows
    )
    by_kind: dict[str, list[str]] = {}
    for a in assets:
        cfg = a["config"]
        by_kind.setdefault(a["kind"], []).append(str(cfg.get("text") or a["title_fa"]))
    return assets, {k: "\n".join(v) for k, v in by_kind.items()}


async def environment(
    tx: Tx,
    run: dict[str, Any],
    body: dict[str, Any],
    sdef: dict[str, Any],
    done: dict[str, StepOutput],
    lib: dict[str, str],
) -> dict[str, Any]:
    company = await tx.one(
        "SELECT code, coalesce(name_fa, code) AS name_fa FROM core.companies WHERE id = :id",
        id=run["company_id"],
    )
    ins = await learning.prompt_vars(tx, run["line_id"])
    return {
        "company": {"name_fa": company["name_fa"], "code": company["code"]},
        "line": {"title_fa": body.get("title_fa") or run.get("title_fa")},
        "platform": body.get("platform") or run.get("platform"),
        "steps": {
            k: {"text": o.text, "data": o.data, "file_id": o.file_id, "files": list(o.files)}
            for k, o in done.items()
        },
        "settings": sdef.get("settings") or {},
        "library": lib,
        "insights": ins,
    }


# -------------------------------------------------------------------- gates --
def effective_gate(sdef: dict[str, Any], mode: str, dry: bool) -> str | None:
    """Who must seal this step before it runs: a dry run never waits; a gate
    the owner set always holds; a seal step holds a draft line (an auto line
    passes it); a draft line's publish waits for the owner."""
    if dry:
        return None
    g = sdef.get("gate") or "auto"
    if g in ("owner", "ceo"):
        return str(g)
    if sdef["kind"] == "seal":
        return None if mode == "auto" else "owner"
    if sdef["kind"] == "publish" and mode == "draft":
        return "owner"
    return None


def input_keys(sdef: dict[str, Any]) -> list[str]:
    """The steps a step reads: its `inputs`, and every step its settings name
    (`<x>_from`, `of`), so an adapter finds what its settings point at."""
    keys = list(sdef.get("inputs") or [])
    for k, v in (sdef.get("settings") or {}).items():
        if (k.endswith("_from") or k == "of") and isinstance(v, str) and v not in keys:
            keys.append(v)
    return keys


def waits_for_callback(out: StepOutput) -> bool:
    """An adapter parks its step for a signed callback (the n8n step)."""
    return out.data.get("wait") == CALLBACK or out.data.get("waiting") is True


def holds_for_owner(out: StepOutput, cur: dict[str, Any], run: dict[str, Any]) -> bool:
    """§33.9 a step that finished but asks the owner before the run goes on (the `persona_test`
    step below its `min_score`): once, a dry run never waits, and after the owner's seal it passes."""
    return (
        out.data.get("hold") == "owner"
        and cur["sealed_at"] is None
        and not run["dry"]
        and not waits_for_callback(out)
    )


def step_def(body: dict[str, Any], key: str) -> dict[str, Any]:
    for s in body.get("steps") or []:
        if s["key"] == key:
            return T.StepDef.model_validate(s).model_dump()
    raise ApiError(409, "validation_failed", f"step {key} is not in this version of the line")


def preview_of(steps: list[dict[str, Any]], upto: int) -> dict[str, Any]:
    """What the card shows: the latest text before the gate and every file."""
    text, files = None, []
    for s in steps:
        if s["pos"] >= upto or s["state"] != "done":
            continue
        o = s["output"] or {}
        if o.get("text"):
            text = o["text"]
        files += [f for f in [o.get("file_id"), *(o.get("files") or [])] if f]
    return {"text": (text or "")[:2000] or None, "files": list(dict.fromkeys(files))[:10]}


async def _card(
    tx: Tx, run: dict[str, Any], step: dict[str, Any], sdef: dict[str, Any], g: str,
    steps: list[dict[str, Any]], why_fa: str | None = None,
) -> dict[str, Any]:  # fmt: skip
    from hq_api.domain import decisions as D

    publishing = sdef["kind"] in LEAVING
    what = (
        f"اجرای **{run['ref']}** از خط **{run['line_ref']}** ({run['platform']}) به گام "
        f"«{sdef['title_fa']}» رسیده و منتظر مُهر است."
    )
    why = why_fa or (
        "خط در حالت پیش‌نویس است؛ انتشار فقط با مُهر تو."
        if sdef["kind"] == "publish" and (sdef.get("gate") or "auto") == "auto"
        else "این گام مُهر میخواهد."
    )
    payload = {
        "run": run["ref"],
        "line": run["line_ref"],
        "step": sdef["key"],
        "kind": sdef["kind"],
        "gate": g,
        "platform": run["platform"],
        "title_fa": run["title_fa"][:300],
        "mode": run["mode"],
        "dry": run["dry"],
        "preview": preview_of(steps, step["pos"]),
    }
    din = D.DecisionIn(
        kind="line_publish",
        title=(f"انتشار {run['title_fa']}" if publishing else f"مُهر {run['title_fa']}")[:300],
        what=what,
        why=why,
        risk="low",
        payload=payload,
    )
    return await D.propose(
        tx,
        SERVICE,
        company_id=run["company_id"],
        company_code=run["company"],
        body=din,
        thread_code=None,
    )


# --------------------------------------------------------------------- caps --
def day_start(now: datetime | None = None) -> datetime:
    n = now or datetime.now(UTC)
    return n.replace(hour=0, minute=0, second=0, microsecond=0)


async def runs_today(tx: Tx, line_id: UUID) -> int:
    n = await tx.scalar(
        """SELECT count(*) FROM lines.runs WHERE line_id = :id AND NOT dry AND at >= :d
             AND (state NOT IN ('skipped', 'cancelled') OR started_at IS NOT NULL)""",
        id=line_id,
        d=day_start(),
    )
    return int(n or 0)


async def company_cap_reached(tx: Tx, hub: Any, company_id: UUID) -> bool:
    """§28.7 the company's daily token cap (its own, else the hub's default;
    0 = none) against what the ledger holds for it today (UTC)."""
    cap = await tx.scalar(
        "SELECT daily_token_cap FROM core.companies WHERE id = :co", co=company_id
    )
    cap = int(cap) if cap is not None else int(hub.settings.company_daily_token_cap)
    if cap <= 0:
        return False
    spent = await tx.scalar(
        """SELECT COALESCE(sum(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)
                               + COALESCE(cache_read_tokens, 0) + COALESCE(cache_write_tokens, 0)), 0)
           FROM llm.calls WHERE company_id = :co AND started_at >= :d""",
        co=company_id,
        d=day_start(),
    )
    return int(spent or 0) >= cap


async def stop_reason(
    tx: Tx, hub: Any, run: dict[str, Any], caps: dict[str, Any], sdef: dict[str, Any]
) -> str | None:
    if (lock := await gate.automation_lock(tx, run["company_id"])) is not None:
        return LOCK_FA.get(lock, LOCK_FA["holding"])
    if int(run["tokens"]) >= int(caps.get("tokens_per_run", 0)):
        return f"سقف توکن این اجرا ({int(caps.get('tokens_per_run', 0)):,}) پر شد."
    if await company_cap_reached(tx, hub, run["company_id"]):
        return "سقف توکن امروز این شرکت پر است؛ اجرا ماند تا فردا."
    if sdef["kind"] == "opus_build":
        n = await tx.scalar(
            """SELECT count(*) FROM lines.step_runs s JOIN lines.runs r ON r.id = s.run_id
               WHERE r.line_id = :line AND s.kind = 'opus_build' AND NOT s.reused
                 AND s.started_at >= :d AND s.run_id <> :run""",
            line=run["line_id"],
            d=day_start(),
            run=run["id"],
        )
        if int(n or 0) >= int(caps.get("opus_per_day", 0)):
            return "سقف ساخت روزانه‌ی این خط پر است؛ اجرا ماند تا فردا."
    return None


# --------------------------------------------------------------- run states --
async def _emit(tx: Tx, run: dict[str, Any], **data: Any) -> None:
    await events.emit(
        tx, run["company"], "line_run.updated", run["ref"], {"line": run["line_ref"], **data}
    )


async def _end(tx: Tx, run: dict[str, Any], state: str, note_fa: str | None) -> None:
    await tx.exec(
        """UPDATE lines.step_runs SET state = 'skipped', ended_at = coalesce(ended_at, now())
           WHERE run_id = :id AND state IN ('pending', 'running', 'waiting')""",
        id=run["id"],
    )
    await tx.exec(
        """UPDATE lines.runs SET state = :s, note_fa = :n, ended_at = now(), updated_at = now()
           WHERE id = :id""",
        id=run["id"],
        s=state,
        n=(note_fa or None) and note_fa[:1000],
    )
    await _emit(tx, run, state=state)


async def _withdraw(tx: Tx, run: dict[str, Any], note: str) -> None:
    """A run that ends while its card waits: the card is withdrawn."""
    d = await tx.first(
        """UPDATE cartable.decisions SET status = 'withdrawn', decided_at = now(),
               decided_by_kind = 'service', decided_by_code = 'system', note = :n
           WHERE id = :id AND status = 'pending' AND kind = 'line_publish' RETURNING ref""",
        id=run["decision_id"],
        n=note[:500],
    )
    if d is not None:
        await events.emit(
            tx, run["company"], "decision.decided", d["ref"],
            {"status": "withdrawn", "kind": "line_publish"},
        )  # fmt: skip


async def _finish(tx: Tx, hub: Any, run: dict[str, Any]) -> str:
    """Every step done or skipped: the run is done; a sealed real run that
    published counts a good run of its line."""
    good = bool(run["sealed"]) and not run["dry"] and bool(run["published"])
    await tx.exec(
        """UPDATE lines.runs SET state = 'done', ended_at = now(), updated_at = now(), counted = :g,
               note_fa = coalesce(note_fa, :n) WHERE id = :id""",
        id=run["id"],
        g=good,
        n="آزمایش کامل انجام شد؛ چیزی منتشر نشد." if run["dry"] else "انجام شد.",
    )
    if good:
        line = await tx.first(
            """UPDATE lines.lines SET good_runs = good_runs + 1 WHERE id = :id
               RETURNING ref, good_runs, auto_after, mode""",
            id=run["line_id"],
        )
        if line is not None:
            await events.emit(
                tx, run["company"], "line.updated", line["ref"],
                {"good_runs": line["good_runs"],
                 "offer_auto": line["mode"] == "draft" and line["good_runs"] >= line["auto_after"]},
            )  # fmt: skip
    await _emit(tx, run, state="done")
    return "done"


# ------------------------------------------------------------ making a run --
async def start_run(
    tx: Tx,
    line: dict[str, Any],
    *,
    trigger: str,
    who: Principal,
    dry: bool = False,
    from_step: str | None = None,
    source: dict[str, Any] | None = None,
    occurrence_at: datetime | None = None,
) -> dict[str, Any]:
    """A run of the line's current version (`queued`), or `skipped` at once
    with its reason (a lock, `runs_per_day`). `from_step`: the steps before it
    reuse the outputs of `source` (a run of this line; default its latest run
    that has them) and are not run again."""
    body = await store.version_body(tx, line["id"], line["version"])
    keys = [s["key"] for s in body["steps"]]
    if from_step is not None and from_step not in keys:
        raise ApiError(422, "validation_failed", fields={"from_step": "a step of this line"})
    reason = None
    if (lock := await gate.automation_lock(tx, line["company_id"])) is not None:
        reason = LOCK_FA.get(lock, LOCK_FA["holding"])
    elif not dry and await runs_today(tx, line["id"]) >= int(body["caps"].get("runs_per_day", 0)):
        reason = f"سقف اجرای روزانه‌ی این خط ({int(body['caps'].get('runs_per_day', 0))}) پر است."
    row = await tx.one(
        """INSERT INTO lines.runs (company_id, line_id, line_version, trigger, dry, state,
               occurrence_at, rerun_of, from_step, note_fa, ended_at, by_kind, by_code)
           VALUES (:co, :line, :v, :trigger, :dry, :state, :occ, :rerun, :from_step, :note,
                   CASE WHEN :state = 'skipped' THEN now() END, :bk, :bc)
           RETURNING ref""",
        co=line["company_id"],
        line=line["id"],
        v=line["version"],
        trigger=trigger,
        dry=dry,
        state="skipped" if reason else "queued",
        occ=occurrence_at,
        rerun=source["id"] if source and from_step else None,
        from_step=from_step,
        note=reason,
        bk=who.kind,
        bc=who.code,
    )
    run = await store.load_run(tx, row["ref"])
    reuse: dict[str, dict[str, Any]] = {}
    if from_step is not None and not reason:
        src = source or await tx.first(
            """SELECT * FROM lines.runs WHERE line_id = :line AND id <> :id
               ORDER BY at DESC, ref DESC LIMIT 1""",
            line=line["id"],
            id=run["id"],
        )
        if src is not None:
            reuse = {
                s["key"]: s for s in await store.step_rows(tx, src["id"]) if s["state"] == "done"
            }
    before = True
    for pos, s in enumerate(body["steps"]):
        before = before and s["key"] != from_step
        copy = reuse.get(s["key"]) if before and from_step is not None else None
        state = "skipped" if reason or not s.get("enabled", True) else "pending"
        await tx.exec(
            """INSERT INTO lines.step_runs (company_id, run_id, pos, key, kind, state, output, via,
                   reused, ended_at)
               VALUES (:co, :run, :pos, :key, :kind, :state, CAST(:output AS jsonb), :via, :reused,
                       CASE WHEN :reused THEN now() END)""",
            co=line["company_id"],
            run=run["id"],
            pos=pos,
            key=s["key"],
            kind=s["kind"],
            state="done" if copy is not None and state == "pending" else state,
            output=store.dumps(copy["output"] if copy is not None else {}),
            via=copy["via"] if copy is not None else "",
            reused=copy is not None and state == "pending",
        )
    await events.emit(
        tx, line["company"], "line_run.updated", run["ref"],
        {"line": line["ref"], "state": run["state"], "dry": dry, "trigger": trigger},
    )  # fmt: skip
    return run


async def kick(hub: Any, ref: str) -> None:
    """The run's workflow, best effort after commit (the tick catches up)."""
    client = getattr(hub, "temporal", None)
    if client is None:
        return
    from temporalio.common import WorkflowIDConflictPolicy

    try:
        await client.start_workflow(
            WORKFLOW,
            ref,
            id=f"line-run-{ref}",
            task_queue=hub.settings.task_queue,
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )
    except Exception:  # noqa: BLE001 - the lines tick starts it again
        log.warning("could not start a line run", extra={"ref": ref})


async def wake(hub: Any, ref: str) -> None:
    """A waiting run's workflow told to look again (a seal, a callback)."""
    client = getattr(hub, "temporal", None)
    if client is None:
        return
    try:
        await client.get_workflow_handle(f"line-run-{ref}").signal("wake")
    except Exception:  # noqa: BLE001 - it looks again by itself within minutes
        log.info("could not wake a line run", extra={"ref": ref})


# ---------------------------------------------------------------- advancing --
async def _ids(hub: Any) -> list[UUID]:
    ids: list[UUID] = await hub.companies.ids()
    return ids


async def advance(hub: Any, ref: str) -> dict[str, Any]:
    """At most one step of the run; {"state": the run's state after it}."""
    adapters.load()
    async with hub.db.tx(await _ids(hub)) as tx:
        found = await tx.first(store.RUN_SQL + " WHERE r.ref = :ref FOR UPDATE OF r", ref=ref)
        if found is None:
            return {"state": "missing"}
        run = found
        if run["state"] in TERMINAL:
            return {"state": run["state"]}
        steps = await store.step_rows(tx, run["id"])
        if run["state"] == "waiting":
            w = next((s for s in steps if s["state"] == "waiting"), None)
            if w is not None:
                since = w["started_at"] or run["updated_at"]
                if w["gate"] is None:  # a callback: the step's own timeout_s
                    body = await store.version_body(tx, run["line_id"], run["line_version"])
                    sdef = step_def(body, w["key"])
                    limit = timedelta(seconds=int(sdef["timeout_s"]))
                    if await tx.scalar(OVERDUE, t=since, w=limit):
                        await tx.exec(
                            "UPDATE lines.step_runs SET state = 'running' WHERE id = :id",
                            id=w["id"],
                        )
                        await tx.exec(
                            "UPDATE lines.runs SET state = 'running' WHERE id = :id", id=run["id"]
                        )
                        late = StepFailed(
                            "پاسخ گردش کار در زمان خودش نرسید.", code="timeout", retry=True
                        )
                        state = await _failed(tx, run, {**w, "state": "running"}, sdef, late, steps)
                        return {"state": state}
                    return {"state": "waiting"}
                if await tx.scalar(OVERDUE, t=since, w=WAIT_MAX):
                    await _withdraw(tx, run, "بی پاسخ ماند")
                    await _end(tx, run, "cancelled", "یک هفته بی پاسخ ماند و بسته شد.")
                    return {"state": "cancelled"}
                return {"state": "waiting"}
        step = next((s for s in steps if s["state"] in ("pending", "running")), None)
        if step is None:
            return {"state": await _finish(tx, hub, run)}
        body = await store.version_body(tx, run["line_id"], run["line_version"])
        sdef = step_def(body, step["key"])
        if (why := await stop_reason(tx, hub, run, body["caps"], sdef)) is not None:
            await _withdraw(tx, run, why)
            await _end(tx, run, "skipped", why)
            return {"state": "skipped"}
        g = effective_gate(sdef, run["mode"], run["dry"])
        if g is not None and step["sealed_at"] is None:
            d = await _card(tx, run, step, sdef, g, steps)
            await tx.exec(
                """UPDATE lines.step_runs SET state = 'waiting', gate = :g, decision_id = :d,
                       started_at = now() WHERE id = :id""",
                id=step["id"],
                g=g,
                d=d["id"],
            )
            await tx.exec(
                """UPDATE lines.runs SET state = 'waiting', decision_id = :d,
                       started_at = coalesce(started_at, now()), updated_at = now()
                   WHERE id = :id""",
                id=run["id"],
                d=d["id"],
            )
            await _emit(tx, run, state="waiting", step=step["key"], decision=d["ref"])
            return {"state": "waiting"}
        if step["state"] == "running" and step["attempt"] >= sdef["max_attempts"]:
            # the last attempt never answered (the worker stopped mid-step)
            state = await _failed(
                tx, run, step, sdef,
                StepFailed("گام نیمه‌کاره ماند و دیگر تلاشی نمانده.", code="lost"), steps,
            )  # fmt: skip
            return {"state": state}
        attempt = int(step["attempt"]) + 1
        done = {s["key"]: output_of(s) for s in steps if s["state"] == "done"}
        assets, lib = await library_env(tx, body.get("library") or [])
        env = await environment(tx, run, body, sdef, done, lib)
        prompt, missing = render_prompt(sdef.get("prompt_fa"), env)
        if step["hint_fa"]:
            prompt = f"{prompt or ''}\n\n{step['hint_fa']}".strip()
        await tx.exec(
            """UPDATE lines.step_runs SET state = 'running', attempt = :a, started_at = now(),
                   ended_at = NULL, missing = CAST(:missing AS text[]) WHERE id = :id""",
            id=step["id"],
            a=attempt,
            missing=missing,
        )
        await tx.exec(
            """UPDATE lines.runs SET state = 'running', started_at = coalesce(started_at, now()),
                   updated_at = now() WHERE id = :id""",
            id=run["id"],
        )
        await _emit(tx, run, state="running", step=step["key"], attempt=attempt)
        ctx = StepContext(
            run_ref=run["ref"],
            line_ref=run["line_ref"],
            company=run["company"],
            platform=run["platform"],
            channel=dict(body.get("channel") or {}),
            step={
                **sdef,
                "_sealed": {"by": step["sealed_by"], "at": str(step["sealed_at"])}
                if step["sealed_at"]
                else None,
            },
            prompt=prompt,
            inputs={k: done[k] for k in input_keys(sdef) if k in done},
            library=assets,
            dry=bool(run["dry"]),
            hub=hub,
        )
    out, err = await call(ctx, sdef)
    async with hub.db.tx(await _ids(hub)) as tx:
        run = await store.load_run(tx, ref, lock=True)
        cur = await tx.first(
            "SELECT * FROM lines.step_runs WHERE run_id = :r AND key = :k",
            r=run["id"],
            k=sdef["key"],
        )
        if (
            run["state"] != "running"
            or cur is None
            or cur["state"] != "running"
            or (cur["attempt"] != attempt)
        ):
            return {"state": run["state"]}  # cancelled (or moved on) meanwhile
        steps = await store.step_rows(tx, run["id"])
        if err is not None:
            return {"state": await _failed(tx, run, cur, sdef, err, steps)}
        assert out is not None
        return {"state": await _done(tx, hub, run, cur, sdef, out)}


async def call(
    ctx: StepContext, sdef: dict[str, Any]
) -> tuple[StepOutput | None, StepFailed | None]:
    """The step's adapter under its timeout; never raises."""
    adapter = REGISTRY.get(sdef["kind"])
    if adapter is None:
        return None, StepFailed(
            f"ابزار گام «{sdef['kind']}» هنوز آماده نیست.", code="no_adapter", retry=False
        )
    try:
        limit = min(int(sdef["timeout_s"]), T.MAX_TIMEOUT_S)
        out = await asyncio.wait_for(adapter.run(ctx), timeout=limit)
    except StepFailed as exc:
        return None, exc
    except TimeoutError:
        return None, StepFailed(
            f"گام در {min(int(sdef['timeout_s']), T.MAX_TIMEOUT_S)} ثانیه تمام نشد.",
            code="timeout",
            retry=True,
        )
    except Exception as exc:  # noqa: BLE001 - an adapter's bug fails its step, never the engine
        log.warning("line step raised", extra={"kind": sdef["kind"], "error": type(exc).__name__})
        return None, StepFailed("گام با خطای پیش‌بینی‌نشده ایستاد.", code="error", retry=True)
    answer: object = out  # an adapter outside the types may answer anything
    if not isinstance(answer, StepOutput):
        return None, StepFailed("گام پاسخ درستی نداد.", code="bad_output", retry=False)
    return answer, None


async def _done(
    tx: Tx, hub: Any, run: dict[str, Any], cur: dict[str, Any], sdef: dict[str, Any],
    out: StepOutput,
) -> str:  # fmt: skip
    held = holds_for_owner(out, cur, run)
    waiting = waits_for_callback(out) or held
    await tx.exec(
        """UPDATE lines.step_runs SET state = :s, output = CAST(:o AS jsonb), via = :via,
               tokens = tokens + :t, usd_equiv = usd_equiv + :u, error_fa = NULL, hint_fa = NULL,
               ended_at = CASE WHEN :s = 'done' THEN now() END WHERE id = :id""",
        id=cur["id"],
        s="waiting" if waiting else "done",
        o=dump_output(out),
        via=(out.via or "")[:120],
        t=max(0, int(out.tokens)),
        u=max(Decimal(0), out.usd_equiv),
    )
    published: list[dict[str, Any]] = []
    if sdef["kind"] == "publish" and not run["dry"] and not waiting:
        published = published_of(run, sdef, out)
    await tx.exec(
        """UPDATE lines.runs SET tokens = tokens + :t, usd_equiv = usd_equiv + :u,
               published = published || CAST(:p AS jsonb), state = :s, updated_at = now()
           WHERE id = :id""",
        id=run["id"],
        t=max(0, int(out.tokens)),
        u=max(Decimal(0), out.usd_equiv),
        p=store.dumps(published),
        s="waiting" if waiting else "running",
    )
    if published:
        await learning.record_features(tx, run, await owner_tz(tx), published)
        from hq_api.domain import live

        await live.publish_flow(tx, run, published)  # ⟨1.24⟩ §42.2 to the world, on the map
    card: dict[str, Any] | None = None
    if held:  # §33.9 the owner's card, with the objections; the run waits for his seal
        steps = await store.step_rows(tx, run["id"])
        card = await _card(
            tx,
            run,
            cur,
            sdef,
            "owner",
            steps,
            why_fa=str(out.data.get("why_fa") or "")[:2000] or None,
        )
        await tx.exec(
            "UPDATE lines.step_runs SET gate = 'owner', decision_id = :d WHERE id = :id",
            id=cur["id"],
            d=card["id"],
        )
        await tx.exec(
            "UPDATE lines.runs SET decision_id = :d WHERE id = :id", id=run["id"], d=card["id"]
        )
    await audit.record(
        tx,
        SERVICE,
        company_id=run["company_id"],
        action="line.step",
        action_class="A3" if published else "A1",
        target_kind="line_run",
        target_ref=f"{run['ref']}:{sdef['key']}",
        summary=f"{sdef['kind']} {'waiting' if waiting else 'done'} via {out.via or '-'}"
        + (f", {out.tokens} tokens" if out.tokens else "")
        + (" (dry)" if run["dry"] and sdef["kind"] in LEAVING else ""),
    )
    await _emit(
        tx,
        run,
        state="waiting" if waiting else "running",
        step=sdef["key"],
        step_state="waiting" if held else "done",
        **({"decision": card["ref"]} if card else {}),
    )
    return "waiting" if waiting else "running"


def published_of(
    run: dict[str, Any], sdef: dict[str, Any], out: StepOutput
) -> list[dict[str, Any]]:
    now = datetime.now(UTC).isoformat()
    given = out.data.get("published")
    items = (
        given
        if isinstance(given, list) and given
        else [given if isinstance(given, dict) else out.data]
    )
    return [
        {
            "platform": str(p.get("platform") or run["platform"]),
            "kind": str(p.get("kind") or (sdef.get("settings") or {}).get("kind") or "post"),
            "external_id": (str(p["external_id"]) if p.get("external_id") else None),
            "at": p.get("at") or now,
            "url": p.get("url"),
        }
        for p in items
        if isinstance(p, dict)
    ]


def _producer(
    sdef: dict[str, Any], steps: list[dict[str, Any]], cur: dict[str, Any]
) -> dict[str, Any] | None:
    """The step that wrote this step's input: the one its settings read
    (`text_from`, `of`), else its first input, else the nearest earlier step
    that ran."""
    st = sdef.get("settings") or {}
    named = [v for v in (st.get("text_from"), st.get("of")) if isinstance(v, str)]
    for key in [*named, *(sdef.get("inputs") or [])]:
        found = next((s for s in steps if s["key"] == key and s["pos"] < cur["pos"]), None)
        if found is not None:
            return found
    earlier = [s for s in steps if s["pos"] < cur["pos"] and s["state"] == "done"]
    return earlier[-1] if earlier else None


async def _failed(
    tx: Tx, run: dict[str, Any], cur: dict[str, Any], sdef: dict[str, Any], err: StepFailed,
    steps: list[dict[str, Any]],
) -> str:  # fmt: skip
    reason = (err.reason_fa or "گام نشد.")[:900]
    adapter = REGISTRY.get(sdef["kind"])
    again = err.retry and int(cur["attempt"]) < int(sdef["max_attempts"])
    producer = (
        _producer(sdef, steps, cur) if again and getattr(adapter, "reruns_input", False) else None
    )
    if again and producer is not None and not producer["reused"]:
        # the input is made again first: from its step up to this one, all pending
        await tx.exec(
            """UPDATE lines.step_runs SET state = 'pending', attempt = 0, ended_at = NULL,
                   sealed_at = NULL, sealed_by = NULL, gate = NULL, decision_id = NULL
               WHERE run_id = :run AND pos >= :a AND pos < :b AND state IN ('done', 'failed')
                 AND NOT reused""",
            run=run["id"],
            a=producer["pos"],
            b=cur["pos"],
        )
        await tx.exec(
            "UPDATE lines.step_runs SET hint_fa = :h WHERE id = :id",
            id=producer["id"],
            h=f"بار قبل: {reason} متنی تازه و متفاوت بنویس."[:500],
        )
    if again:
        await tx.exec(
            """UPDATE lines.step_runs SET state = 'pending', error_fa = :e, ended_at = now()
               WHERE id = :id""",
            id=cur["id"],
            e=reason,
        )
        await tx.exec(
            "UPDATE lines.runs SET state = 'running', updated_at = now() WHERE id = :id",
            id=run["id"],
        )
        await _emit(tx, run, state="running", step=sdef["key"], step_state="retry")
        return "running"
    await tx.exec(
        """UPDATE lines.step_runs SET state = :s, error_fa = :e, ended_at = now() WHERE id = :id""",
        id=cur["id"],
        s="skipped" if sdef.get("optional") else "failed",
        e=reason,
    )
    await audit.record(
        tx,
        SERVICE,
        company_id=run["company_id"],
        action="line.step",
        action_class="A1",
        target_kind="line_run",
        target_ref=f"{run['ref']}:{sdef['key']}",
        summary=f"{sdef['kind']} failed ({err.code})"
        + (", optional: skipped" if sdef.get("optional") else ""),
    )
    if sdef.get("optional"):
        await tx.exec(
            "UPDATE lines.runs SET state = 'running', updated_at = now() WHERE id = :id",
            id=run["id"],
        )
        await _emit(tx, run, state="running", step=sdef["key"], step_state="skipped")
        return "running"
    await _end(tx, run, "failed", f"گام «{sdef['title_fa']}» نشد: {reason}")
    return "failed"


async def drive(hub: Any, ref: str, *, limit: int = 200) -> dict[str, Any]:
    """advance() until the run waits or ends (tests, and the step-by-step
    workflow's own loop does the same with a wait between)."""
    out: dict[str, Any] = {"state": "queued"}
    for _ in range(limit):
        out = await advance(hub, ref)
        if out["state"] not in ("queued", "running"):
            return out
    return out


# ------------------------------------------------------------ the owner acts --
async def on_card_decided(
    tx: Tx, d: dict[str, Any], verdict: str, note: str | None, who: Principal
) -> None:
    """decisions.decide()'s hook for a line_publish card, in its transaction:
    approved -> the step runs next; rejected or returned -> the run ends."""
    p = d["payload"] or {}
    run = await tx.first(store.RUN_SQL + " WHERE r.ref = :ref FOR UPDATE OF r", ref=p.get("run"))
    if run is None or run["state"] != "waiting":
        return
    step = await tx.first(
        "SELECT * FROM lines.step_runs WHERE run_id = :r AND key = :k AND decision_id = :d",
        r=run["id"],
        k=p.get("step"),
        d=d["id"],
    )
    if step is None or step["state"] != "waiting":
        return
    if verdict == "approved":
        await tx.exec(
            """UPDATE lines.step_runs SET state = 'pending', sealed_at = now(), sealed_by = :by
               WHERE id = :id""",
            id=step["id"],
            by=who.code[:64],
        )
        await tx.exec(
            "UPDATE lines.runs SET state = 'running', sealed = true, updated_at = now() WHERE id = :id",
            id=run["id"],
        )
        await _emit(tx, run, state="running", step=step["key"], sealed=True)
        return
    word = "رد کرد" if verdict == "rejected" else "برگرداند"
    who_fa = "مالک" if who.is_owner else who.code
    await tx.exec(
        "UPDATE lines.step_runs SET state = 'failed', error_fa = :e, ended_at = now() WHERE id = :id",
        id=step["id"],
        e=(f"{who_fa} {word}" + (f": {note}" if note else ""))[:1000],
    )
    await _end(tx, run, "cancelled", (f"{who_fa} {word}" + (f": {note}" if note else ""))[:1000])


async def cancel(tx: Tx, run: dict[str, Any]) -> None:
    if run["state"] in TERMINAL:
        raise ApiError(409, "validation_failed", f"{run['ref']} is {run['state']}")
    await _withdraw(tx, run, "اجرا لغو شد")
    await _end(tx, run, "cancelled", "مالک لغو کرد.")


async def on_callback(hub: Any, body: dict[str, Any]) -> dict[str, Any]:
    """n8n's signed answer to a waiting `n8n` step: done with its output, or
    failed (then the step's attempts and `optional` decide, as for any step).

    A fast workflow can answer before the engine has parked the step (the
    adapter sends the webhook, then a second transaction marks it `waiting`):
    while the n8n step is still `running`, the answer looks again for a few
    seconds instead of being refused and lost."""
    for _ in range(CALLBACK_TRIES):
        got = await _on_callback(hub, body)
        if got is not None:
            return got
        await asyncio.sleep(CALLBACK_PAUSE_S)
    raise ApiError(409, "validation_failed", "this step waits for no callback")


async def _on_callback(hub: Any, body: dict[str, Any]) -> dict[str, Any] | None:
    """The callback applied, or None while the step is not parked yet."""
    async with hub.db.tx(await _ids(hub)) as tx:
        run = await store.load_run(tx, str(body["run"]), lock=True)
        cur = await tx.first(
            "SELECT * FROM lines.step_runs WHERE run_id = :r AND key = :k",
            r=run["id"],
            k=body["step"],
        )
        bdy = await store.version_body(tx, run["line_id"], run["line_version"])
        if cur is not None and run["state"] == "running" and cur["state"] == "running":
            if step_def(bdy, cur["key"])["kind"] == "n8n":
                return None  # the webhook was sent, the engine parks the step in a moment
        if run["state"] != "waiting" or cur is None or cur["state"] != "waiting" or cur["gate"]:
            raise ApiError(409, "validation_failed", "this step waits for no callback")
        sdef = step_def(bdy, cur["key"])
        await tx.exec("UPDATE lines.runs SET state = 'running' WHERE id = :id", id=run["id"])
        run = await store.load_run(tx, run["ref"])
        await tx.exec("UPDATE lines.step_runs SET state = 'running' WHERE id = :id", id=cur["id"])
        cur = {**cur, "state": "running"}
        if body.get("ok"):
            prev = cur["output"] or {}
            out = StepOutput(
                text=body.get("text") if body.get("text") is not None else prev.get("text"),
                file_id=body.get("file_id") or prev.get("file_id"),
                files=tuple(str(f) for f in body.get("files") or prev.get("files") or []),
                data={
                    **(prev.get("data") or {}),
                    **(body.get("data") or {}),
                    "wait": None,
                    "waiting": False,
                },
                via="n8n",
            )
            state = await _done(tx, hub, run, cur, sdef, out)
        else:
            steps = await store.step_rows(tx, run["id"])
            err = StepFailed(str(body.get("error_fa") or "گردش کار n8n نشد."), retry=False)
            state = await _failed(tx, run, cur, sdef, err, steps)
    await wake(hub, run["ref"])
    return {"run": run["ref"], "step": cur["key"], "state": state}


async def test_step(
    hub: Any, line_ref: str, key: str, given: dict[str, dict[str, Any]] | None
) -> dict[str, Any]:
    """One step alone, now, nothing kept but the answer: its inputs from
    `given`, else from the line's latest run; publish and deliver run dry.
    The step is prepared in a transaction and run outside it."""
    adapters.load()
    async with hub.db.tx(await _ids(hub)) as tx:
        line = await store.load(tx, line_ref)
        body = await store.version_body(tx, line["id"], line["version"])
        sdef = step_def(body, key)
        done: dict[str, StepOutput] = {}
        last = await tx.first(
            "SELECT id FROM lines.runs WHERE line_id = :id ORDER BY at DESC, ref DESC LIMIT 1",
            id=line["id"],
        )
        if last is not None:
            done = {
                s["key"]: output_of(s)
                for s in await store.step_rows(tx, last["id"])
                if s["state"] == "done"
            }
        for k, v in (given or {}).items():
            done[k] = StepOutput(
                text=v.get("text"),
                file_id=v.get("file_id"),
                files=tuple(str(f) for f in v.get("files") or []),
                data=dict(v.get("data") or {}),
            )
        assets, lib = await library_env(tx, body.get("library") or [])
        fake_run = {
            "company_id": line["company_id"], "line_id": line["id"], "title_fa": line["title_fa"],
            "platform": line["platform"],
        }  # fmt: skip
        env = await environment(tx, fake_run, body, sdef, done, lib)
    prompt, missing = render_prompt(sdef.get("prompt_fa"), env)
    ctx = StepContext(
        run_ref="RN-TEST",
        line_ref=line["ref"],
        company=line["company"],
        platform=line["platform"],
        channel=dict(body.get("channel") or {}),
        step={**sdef, "_sealed": None},
        prompt=prompt,
        inputs={k: done[k] for k in input_keys(sdef) if k in done},
        library=assets,
        dry=True,
        hub=hub,
    )
    out, err = await call(ctx, {**sdef, "timeout_s": min(int(sdef["timeout_s"]), TEST_TIMEOUT_S)})
    return {
        "step": key,
        "kind": sdef["kind"],
        "state": "done" if out is not None else "failed",
        "prompt": prompt,
        "missing": missing,
        "output": {
            "text": out.text, "file_id": out.file_id, "files": list(out.files), "data": out.data,
        } if out is not None else None,
        "via": out.via if out is not None else "",
        "tokens": out.tokens if out is not None else 0,
        "usd_equiv": str(out.usd_equiv if out is not None else Decimal(0)),
        "error_fa": err.reason_fa if err is not None else None,
    }  # fmt: skip


# --------------------------------------------------------------------- tick --
def due_occurrence(rule: recurrence.Rule, tz: str, now: datetime) -> datetime | None:
    found = recurrence.occurrences(rule, tz, now - LOOKBACK, now + timedelta(seconds=1))
    return found[-1] if found else None


async def tick(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """Every 5 minutes (hq-lines-tick): a run for each `on` line whose schedule
    is due (once per occurrence, in the owner's zone); open runs that no
    workflow moves are started again; the 24h and 7d reads."""
    now = now or datetime.now(UTC)
    out: dict[str, Any] = {"made": 0, "skipped": 0, "kicked": 0}
    made: list[str] = []
    async with hub.db.tx(await _ids(hub)) as tx:
        if (lock := await gate.holding_lock(tx)) is not None:
            return gate.skipped(lock)
        tz = await owner_tz(tx)
        for line in await tx.all(
            store.LINE_SQL + " WHERE l.state = 'on' AND l.schedule IS NOT NULL"
        ):
            try:
                occ = due_occurrence(recurrence.parse(line["schedule"]), tz, now)
            except ApiError:
                continue
            if occ is None or await tx.scalar(
                "SELECT 1 FROM lines.runs WHERE line_id = :id AND occurrence_at = :o",
                id=line["id"],
                o=occ,
            ):
                continue
            run = await start_run(tx, line, trigger="schedule", who=SERVICE, occurrence_at=occ)
            await tx.exec(
                "UPDATE lines.lines SET last_due_at = :o WHERE id = :id", o=occ, id=line["id"]
            )
            if run["state"] == "skipped":
                out["skipped"] += 1
            else:
                out["made"] += 1
                made.append(run["ref"])
        stale = await tx.all(
            """SELECT ref FROM lines.runs WHERE state IN ('queued', 'running')
                 AND updated_at < :t ORDER BY at LIMIT 50""",
            t=now - KICK_AFTER,
        )
    for ref in made + [r["ref"] for r in stale]:
        await kick(hub, ref)
    out["kicked"] = len(stale)
    out["metrics"] = await learning.read_metrics(hub, now)
    return out
