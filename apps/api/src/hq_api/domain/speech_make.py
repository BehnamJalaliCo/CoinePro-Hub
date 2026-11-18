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

⟨2026-11-13⟩ The owner: «اول API، و اگر نشد نسخه‌ی وب». A voice is first asked of Gemini's own
API (the voice layer's engine `gemini-3.8-flash-tts`, contract §32.5: the worker's call through
egress with the voice key the owner gives in the app, its usage and price on the voice meter), with
the same speaker and the style as a reading instruction; only when that engine has no key, refuses
or fails is it AI Studio's web page, as before. The answer names the engine that spoke.

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

import asyncio
import logging
import re
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
# ⟨2026-11-18⟩ the API's quota spent on every key (the web page then answered «signed out» and one
# reel went out silent): said as what it is, with when it comes back and what not to do meanwhile
QUOTA_FA = (
    "سهمیه‌ی روزانه‌ی همه‌ی کلیدهای صدای Gemini تمام شده است؛ ورود به حساب لازم نیست. سهمیه "
    "نیمه‌شب آمریکا (ساعت ۱۱:۳۰ تهران) تازه می‌شود. ویدیو را بی‌صدا نساز و منتشر نکن: صبر کن و "
    "بعد از تازه شدن سهمیه همین ابزار را دوباره صدا بزن."
)
API_CODES: dict[str, str] = {}  # a job -> the API's last refusal code (while the job runs)
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


# ⟨2026-11-13⟩ the API first (see the module's doc)
API_ENGINE = "gemini-3.8-flash-tts"
# ⟨2026-11-13⟩ a passing refusal of Google's (F-0018: one upstream_error between two good voices)
# is tried once more before the web page, which may be signed out
API_TRIES = 2
API_RETRY_S = 3.0
API_RETRY_CODES = frozenset(
    {"upstream_error", "transport_down", "engine_crashed", "timeout", "rate_limited", "quota"}
)
# AI Studio's style presets (its 2026-11 page), as the API reads them: a reading instruction
STYLE_PRESETS = {
    "narration": "commanding, with rich vocal modulation and dramatic pauses",
    "friendly": "warm and neutral, with micro-pauses",
    "promote": "high energy, with elongated vowels",
    "podcast": "calm and measured",
    "whisper": "whispering quietly",
}


async def api_ready(hub: Any, tx: Tx) -> bool:
    """Whether Gemini's API may be asked (its key given; a failing one is still tried)."""
    from hq_api.voice import store as VS

    holding = await hub.companies.holding()
    st = (await VS.states(tx, holding.id)).get(API_ENGINE)
    return st is not None and st["state"] != "missing"


def api_text(text: str, style: str) -> str:
    """The text as the API is asked to read it: a style is an instruction before it (Gemini speech
    takes how to say it in the prompt, never as a setting)."""
    s = " ".join(style.split())
    if not s:
        return text
    how = STYLE_PRESETS.get(s.lower(), s)
    return f"Read the following Persian text aloud, in this manner: {how}.\n\n{text}"


# ⟨2026-11-13⟩ Gemini's speech refuses a long text in one request (F-0020: 844 characters were
# `upstream_error` on every try, 517 went through in 40 s): a longer text is read in parts, cut
# between its lines (then its sentences, then its words), and the parts are joined with a breath.
# ⟨2026-11-17⟩ The owner heard «تق» or a choke at the end of some paragraphs in every reel: each
# part's head click and tail noise burst were joined as they came (burst, digital silence, click).
# Every part, and a voice of one part too, is now cleaned first (voice/seams.py); the pause is a
# paragraph's, from one speech end to the next onset.
API_PART_CHARS = 480
PART_PAUSE_S = 0.35
SENTENCE_END = re.compile(r"(?<=[.!?؟؛…])\s+")


def api_parts(text: str, limit: int = API_PART_CHARS) -> list[str]:
    """The text in parts of at most `limit` characters, never cutting inside a word."""
    units: list[str] = []
    for line in (x.strip() for x in text.splitlines()):
        if not line:
            continue
        if len(line) <= limit:
            units.append(line)
            continue
        for piece in SENTENCE_END.split(line):
            piece = piece.strip()
            while len(piece) > limit:
                cut = piece.rfind(" ", 0, limit)
                cut = cut if cut > 0 else limit
                units.append(piece[:cut].strip())
                piece = piece[cut:].strip()
            if piece:
                units.append(piece)
    parts: list[str] = []
    cur = ""
    for u in units:
        if cur and len(cur) + 1 + len(u) > limit:
            parts.append(cur)
            cur = u
        else:
            cur = f"{cur}\n{u}" if cur else u
    if cur:
        parts.append(cur)
    return parts


async def _pcm_of(data: bytes, fmt: str = "s16le") -> bytes:
    """Any audio file as mono samples at the API's rate (24 kHz) by ffmpeg: 16-bit PCM, or 32-bit
    float (`f32le`, nothing clipped: Gemini's decoded Opus goes past full scale)."""
    import tempfile
    from pathlib import Path

    from hq_api import media as ME
    from hq_api.voice import audio as AU

    with tempfile.TemporaryDirectory(prefix="speech-") as tmp:
        src, out = Path(tmp) / "in.audio", Path(tmp) / "out.pcm"
        await asyncio.to_thread(src.write_bytes, data)
        code, _, _ = await ME.run_tool(
            "ffmpeg", "-hide_banner", "-nostdin", "-y", "-threads", ME.FF_THREADS,
            *ME.ff_input(src),
            "-f", fmt, "-ar", str(AU.PCM_RATE), "-ac", "1", str(out),
            limit_s=AU.ENCODE_LIMIT_S,
        )  # fmt: skip
        if code != 0 or not out.is_file():
            raise AU.EncodeFailed("ffmpeg")
        return await asyncio.to_thread(out.read_bytes)


async def join_audio(clips: list[bytes]) -> tuple[bytes, str]:
    """The parts (or one clip) as one Ogg/Opus voice: each cleaned of its head click and tail
    burst, levels matched, a paragraph's pause between them (voice/seams.py)."""
    from hq_api.voice import audio as AU
    from hq_api.voice import seams

    raws = [await _pcm_of(c, "f32le") for c in clips]
    pcm, info = await asyncio.to_thread(seams.f32_to_s16, raws, AU.PCM_RATE, PART_PAUSE_S)
    log.info("speech seams cleaned", extra=info)
    return await AU.pcm_to_opus(pcm), AU.OGG


async def cleaned(data: bytes, mime: str, *, job: str = "") -> tuple[bytes, str]:
    """One voice cleaned at its seams (no head click, no tail burst) as Ogg/Opus; as it came when
    it cannot be read. Never raises."""
    try:
        return await join_audio([data])
    except Exception as exc:  # noqa: BLE001 - the voice as it came, rather than none
        log.warning("speech not cleaned", extra={"job": job, "error": type(exc).__name__})
        return data, mime


async def api_speak(hub: Any, job: dict[str, Any]) -> tuple[bytes, str] | None:
    """The voice from Gemini's API: (audio, mime), or None when that engine has no key, is off or
    fails (the web page is tried then). A long text is read in parts and joined; every part, and a
    single one too, is cleaned at its seams. Never raises."""
    name = f"speech-{str(job['job'])[:8]}"
    parts = api_parts(str(job["text"]))
    if len(parts) <= 1:
        got = await _api_text(hub, job, str(job["text"]), name)
        return None if got is None else await cleaned(*got, job=str(job["job"]))
    clips: list[bytes] = []
    for i, part in enumerate(parts, 1):
        got = await _api_text(hub, job, part, f"{name}-{i}")
        if got is None:
            log.info("speech by the API: a part failed", extra={"job": str(job["job"]), "part": i})
            return None
        clips.append(got[0])
    try:
        return await join_audio(clips)
    except Exception as exc:  # noqa: BLE001 - the web page is the fallback
        log.warning(
            "speech parts not joined", extra={"job": str(job["job"]), "error": type(exc).__name__}
        )
        return None


async def _api_text(
    hub: Any, job: dict[str, Any], text: str, name: str
) -> tuple[bytes, str] | None:
    """One text through the API, tried again after a passing refusal."""
    from hq_api.voice import speaker as SP
    from hq_api.voice.base import EngineFailed

    for attempt in range(API_TRIES):
        got, again = await _api_once(hub, job, name, SP, EngineFailed, text=text)
        if got is not None or not again:
            return got
        if attempt < API_TRIES - 1:
            await asyncio.sleep(API_RETRY_S)
    return None


async def _api_once(
    hub: Any, job: dict[str, Any], name: str, SP: Any, EngineFailed: Any, *, text: str | None = None
) -> tuple[tuple[bytes, str] | None, bool]:
    """One try of the API: ((audio, mime) | None, whether another try may help)."""
    try:
        holding = await hub.companies.holding()
        async with hub.db.tx(await hub.companies.ids()) as tx:
            if not await api_ready(hub, tx):
                return None, False  # no key given yet: the web page, as before
        spoke = await SP.speak_one(
            hub, API_ENGINE, api_text(text if text is not None else str(job["text"]),
                                      str(job.get("style") or "")),
            str(job["voice"]), 1.0, kind="speech", persona=f"speech.make {job['by']}"[:80],
            conversation_ref=None, turn_id=None, seq=None, name=name,
        )  # fmt: skip
        async with hub.db.tx([holding.id]) as tx:
            row = await tx.first(
                "SELECT storage_key, mime FROM files.files WHERE id = CAST(:id AS uuid)",
                id=spoke.out.file_id,
            )
        if row is None:
            return None, False
        data = await hub.storage.get(str(row["storage_key"]))
        return (data, str(row["mime"] or "audio/ogg")), False
    except EngineFailed as exc:
        log.info("speech by the API failed", extra={"job": str(job["job"]), "code": exc.code})
        API_CODES[str(job["job"])] = str(exc.code or "")
        return None, exc.code in API_RETRY_CODES and exc.code != "quota"
    except Exception as exc:  # noqa: BLE001 - the web page is the fallback, never an error here
        log.warning(
            "speech by the API crashed", extra={"job": str(job["job"]), "error": type(exc).__name__}
        )
        return None, True


async def make(hub: Any, job: dict[str, Any]) -> dict[str, Any]:
    """One job: `job` = {job, company_id, company, by, text, voice, style}. The audio as the
    company's file, or a plain Persian refusal; both recorded. The API first, the web page after."""
    voice, style, text = str(job["voice"]), str(job.get("style") or ""), str(job["text"])
    engine = "gemini_api"
    got = await api_speak(hub, job)
    api_code = API_CODES.pop(str(job["job"]), "")
    try:
        if got is None:
            engine = "aistudio"
            got = await tts.speak(hub, text, voice=voice, style=style, timeout_s=TIMEOUT_S)
        data, mime = got
    except StepFailed as e:
        code = CODES.get(e.code, "failed")
        hint = SIGNED_OUT_FA if code == "signed_out" else e.reason_fa
        account: State | None = "signed_out" if code == "signed_out" else None
        if api_code == "quota":  # (the page's own answer is not the reason the voice is missing)
            code, hint = "quota", QUOTA_FA
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
            # ⟨2026-11-13⟩ the session it was made for: the session's next turn gets it in `in/`
            meta={"order_id": str(job["order_id"]), "made_by": "speech.make"}
            if job.get("order_id")
            else None,
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
        # the API says nothing of the web page's sign-in
        account="signed_in" if engine == "aistudio" else None,
        summary=f"done: {'AI Studio' if engine == 'aistudio' else 'Gemini API'} {voice}, "
        f"{len(text)} chars",
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
        "engine": engine,
    }
