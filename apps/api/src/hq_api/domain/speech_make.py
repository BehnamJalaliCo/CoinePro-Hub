"""`speech.make` (A1): a voice from Google AI Studio for the media roles, outside the production
lines. The owner, 2026-11-06: the voices for content used to come from AI Studio, and the hub was
not connected to it.

The one call is the lines' own (lines/adapters/tts.speak): the egress recipe `aistudio-web` in the
hub's browser profile, signed in once by the owner with `make aistudio-web-login`; the speaker is
one of AI Studio's prebuilt voices (default Kore), with an optional style note. The audio becomes
the agent's company's file (§17.1 processing gives it a transcript, so `files.read` hears it).

A generation takes up to a few minutes, longer than one tool call may wait: the api starts a job
(the worker's Temporal workflow `SpeechMake`, id `speech-<company>-<job>`), answers `running` with
the job id, and the agent asks again with `{job}`. Without a worker (tests, a bare api) the job
runs inline and the first answer is final. The file and the audit rows are in the database; the
job's own answer lives with its workflow.

The sign-in state. Nothing records whether the `aistudio-web` profile is signed in: the owner's
`make aistudio-web-login` reports the substitute players' profiles only (report-signin.sh exits
for the lines' profiles), and egress has no state route. So `speech_state()` reads the last answer
AI Studio gave the hub: every `speech.make` writes it on the holding's audit trail (action
`speech.account`), and a production line's `tts` step keeps its own outcome (lines.step_runs). A
voice made means signed in; the login page (`expired`) means signed out; nothing in the last 30
days is `unknown`. A fresh sign-in is seen at the next voice made: a `signed_out` answer only holds
new jobs back for SIGNED_OUT_HOLD, then they try again.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from hq_api import audit, workflows_client
from hq_api.db import Tx
from hq_api.domain import files as F
from hq_api.lines.adapters import tts
from hq_api.lines.base import StepFailed
from hq_api.principal import Principal

log = logging.getLogger("hq_api.speech_make")

ACCOUNT = tts.ACCOUNT  # "aistudio-web"
WORKFLOW = "SpeechMake"
SERVICE = Principal(kind="service", code="speech", role="service")
ROLES: tuple[str, ...] = (
    "media_director",
    "voice_producer",
    "video_director",
    "motion_designer",
    "scriptwriter",
    "ceo",  # ⟨2026-11-12⟩ a media order without a media director is the CEO's (policy media.rego)
)
STATE_DAYS = 30  # an answer older than this says nothing about the sign-in
SIGNED_OUT_HOLD = timedelta(minutes=10)  # a signed-out answer holds new jobs back this long
TIMEOUT_S = 240  # the recipe's own cap for one generation
State = Literal["signed_in", "signed_out", "unknown"]

SIGNED_OUT_FA = (
    "گوگل ای‌آی استودیو در مرورگر هاب وارد نشده است؛ مالک باید یک بار با دستور "
    "make aistudio-web-login وارد شود. تا آن وقت از این راه صدایی ساخته نمی‌شود."
)
RUNNING_FA = "صدا در حال ساخت است؛ چند دقیقه بعد همین ابزار را با همین job دوباره صدا بزن."
# a StepFailed code of tts.speak -> the tool's refusal code
CODES = {
    "expired": "signed_out",
    "browser_off": "channel_not_configured",
    "holding_locked": "company_locked",
    "empty_text": "invalid_args",
    "too_long": "invalid_args",
    "timeout": "timeout",
    "recipe_failed": "recipe_failed",
    "not_audio": "recipe_failed",
    "no_file": "recipe_failed",
}


def workflow_id(company: str, job: str) -> str:
    return f"speech-{company}-{job}"


# ------------------------------------------------------------ the state --
async def _last_answer(tx: Tx) -> tuple[State, datetime] | None:
    """The last answer AI Studio gave the hub about its sign-in (state, when), or None."""
    since = datetime.now(UTC) - timedelta(days=STATE_DAYS)
    ours = await tx.first(
        """SELECT e.summary, e.at FROM audit.entries e
           WHERE e.company_id = (SELECT id FROM core.companies WHERE kind = 'holding' LIMIT 1)
             AND e.at > :since AND e.action = 'speech.account' AND e.target_ref = :acc
           ORDER BY e.at DESC LIMIT 1""",
        since=since,
        acc=ACCOUNT,
    )
    line = await tx.first(
        """SELECT CASE WHEN s.state = 'done' THEN 'signed_in' ELSE 'signed_out' END AS summary,
                  s.ended_at AS at
           FROM lines.step_runs s
           WHERE s.kind = 'tts' AND s.ended_at > :since AND s.reused = false
             AND (s.state = 'done' OR (s.state = 'failed' AND s.error_fa LIKE :login))
           ORDER BY s.ended_at DESC LIMIT 1""",
        since=since,
        login=f"%{ACCOUNT}-login%",
    )
    found = [
        r for r in (ours, line) if r is not None and r["summary"] in ("signed_in", "signed_out")
    ]
    if not found:
        return None
    last = max(found, key=lambda r: r["at"])
    return last["summary"], last["at"]


async def speech_state(tx: Tx) -> dict[str, State]:
    """{"aistudio": "signed_in" | "signed_out" | "unknown"}: the last answer AI Studio gave the hub
    (a voice made or its login page, by `speech.make` or a line's `tts` step, in the last 30 days),
    else unknown. Needs a transaction that reaches every company (the lines' steps are theirs):
    `hub.db.tx(await hub.companies.ids())`."""
    last = await _last_answer(tx)
    return {"aistudio": last[0] if last is not None else "unknown"}


async def held_back(tx: Tx, now: datetime | None = None) -> bool:
    """Whether AI Studio answered `signed out` within SIGNED_OUT_HOLD (no new job tries then)."""
    last = await _last_answer(tx)
    now = now or datetime.now(UTC)
    return last is not None and last[0] == "signed_out" and now - last[1] < SIGNED_OUT_HOLD


# ------------------------------------------------------------- the wake --
# ⟨2026-11-11⟩ a voice that ends after the run that asked for it ended wakes that run's work's
# assignee, as a finished workshop turn does (`workshop_done:`): the holder never waits forever
DONE_REASON = "speech_done:"
FAILED_REASON = "speech_failed:"
CALLER_SQL = """
SELECT r.id, r.state, r.work_id, w.company_id, w.assignee_id
FROM agents.runs r
JOIN core.employees e ON e.id = r.employee_id
JOIN work.work w ON w.id = r.work_id
JOIN agents.steps s ON s.run_id = r.id
CROSS JOIN LATERAL jsonb_array_elements(s.actions) a
WHERE e.code = :by AND r.created_at > now() - interval '1 day'
  AND a ->> 'tool' = 'speech.make' AND a ->> 'ref' = :job
ORDER BY s.at LIMIT 1
"""


async def wake_caller(hub: Any, job: dict[str, Any], *, done: bool) -> str | None:
    """The run that started this job, when it has ended: its work's assignee gets a run
    (`speech_done:<job>` / `speech_failed:<job>`), or the work's session says why not (a lock,
    nobody assigned). None when there is nothing to wake (the run still works and asks again
    itself, the job was not a run's, the answer was final at once). Never raises."""
    from hq_api.domain import order_report as OR

    reason = f"{DONE_REASON if done else FAILED_REASON}{job['job']}"[:200]
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            run = await tx.first(CALLER_SQL, by=str(job.get("by") or ""), job=str(job["job"]))
            if run is None or run["state"] in ("queued", "running"):
                return None
            if (
                await tx.scalar("SELECT work.wake_assignee(:w, :r)", w=run["work_id"], r=reason)
                is not None
            ):
                return reason
            ref = await OR.order_of_work(tx, run["work_id"])
            rep = await OR.ensure(tx, ref) if ref else None
            if rep is None or rep.get("ended_at") is not None:
                return None
            lock = await tx.scalar("SELECT control.lock_state(:co)", co=run["company_id"])
            if lock is not None:
                why = "شرکت قفل است و تا قفل باز نشود کار راه نمیافتد"
            elif run["assignee_id"] is None:
                why = "کار مسئولی ندارد"
            else:
                why = "کار راه نیفتاد؛ «ادامه بده» را بزن"
            head = "صدای گوینده آماده شد" if done else "ساخت صدا به نتیجه نرسید"
            await OR._append_steps(tx, rep["id"], [OR._step("سامانه", f"{head} ولی {why}")])
    except Exception:  # noqa: BLE001 - the voice is made; a wake that fails never undoes it
        log.warning("the voice's caller could not be woken", extra={"job": str(job["job"])})
    return None


# ------------------------------------------------------------- the job --
async def _record(
    hub: Any, job: dict[str, Any], *, account: State | None, summary: str, file_id: UUID | None
) -> None:
    """The outcome on the company's audit trail and, when it says anything of the sign-in, the
    account's state on the holding's."""
    holding = await hub.companies.holding()
    company_id = UUID(str(job["company_id"]))
    async with hub.db.tx([company_id, holding.id]) as tx:
        await audit.record(
            tx,
            SERVICE,
            company_id=company_id,
            action="speech.made",
            action_class="A1",
            target_kind="file" if file_id else "speech",
            target_ref=str(file_id or job["job"]),
            # ⟨2026-11-11⟩ the job named: the session reads a voice as pending until this row
            summary=f"{job['by']}: {summary} (job {job['job']})"[:500],
        )
        if account is not None:
            await audit.record(
                tx,
                SERVICE,
                company_id=holding.id,
                action="speech.account",
                action_class="A0",
                target_kind="account",
                target_ref=ACCOUNT,
                summary=account,
            )


async def make(hub: Any, job: dict[str, Any]) -> dict[str, Any]:
    """One job: `job` = {job, company_id, company, by, text, voice, style}. The audio as the
    company's file, or a plain Persian refusal; both recorded."""
    voice, style, text = str(job["voice"]), str(job.get("style") or ""), str(job["text"])
    try:
        data, mime = await tts.speak(hub, text, voice=voice, style=style, timeout_s=TIMEOUT_S)
    except StepFailed as e:
        code = CODES.get(e.code, "failed")
        hint = SIGNED_OUT_FA if code == "signed_out" else e.reason_fa
        account: State | None = "signed_out" if code == "signed_out" else None
        await _record(hub, job, account=account, summary=f"failed: {code}", file_id=None)
        await wake_caller(hub, job, done=False)
        return {"job": job["job"], "state": "failed", "code": code, "hint_fa": hint}
    company_id = UUID(str(job["company_id"]))
    key, sha = await hub.storage.put(data)
    async with hub.db.tx([company_id]) as tx:
        fid = await F.insert(
            tx,
            company_id=company_id,
            name=f"speech-{str(job['job'])[:8]}.{tts.ext(mime)}",
            mime=mime,
            size=len(data),
            sha256=sha,
            storage_key=key,
            kind="audio",
            by_kind="agent",
            by_code=str(job["by"]),
        )
        await tx.exec(  # §17.1: the media worker's pass (length, transcript)
            """INSERT INTO files.processing (file_id, company_id, stt)
               VALUES (:f, :co, CAST('{}' AS jsonb))""",
            f=fid,
            co=company_id,
        )
    await workflows_client.file_uploaded(hub, str(fid))
    await _record(
        hub,
        job,
        account="signed_in",
        summary=f"done: AI Studio {voice}, {len(text)} chars",
        file_id=fid,
    )
    await wake_caller(hub, job, done=True)
    return {
        "job": job["job"],
        "state": "done",
        "file_id": str(fid),
        "mime": mime,
        "bytes": len(data),
        "voice": voice,
        "style": style,
        "narrator": bool(job.get("narrator")),
        "engine": "aistudio",
    }
