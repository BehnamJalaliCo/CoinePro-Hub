"""The hub's voice (prompt 13 §4, contract §22.3, §22.7): one registry,
`media.voices`, for the media items' narration and the spoken briefings of
§21.4 alike, and the bake-off that fills it with measured numbers.

A voice is an engine and speaker pair with its licence as its own card states
it. `runtime` names how the TTS image runs it ({"piper_voice": ...}); a voice
without one is a candidate the hub cannot run (gated, over the memory budget,
or not trained yet): `note_fa` says why, and it can never be activated. A
voice whose licence is not commercial is activated only with the owner's
explicit `accept_non_commercial`, and every use shows `licence_commercial`.

The bake-off: the same fixed Persian scripts (numbers and percentages, Latin
terms, crypto words, one long sentence, a 60-second reel) spoken by every
runnable voice; the TTS one-shot measures the real-time factor and the peak
memory of each sample on the hub's CPU and sends the Ogg back, which goes
through §17.1 like any audio file; the owner listens blind in the app and
scores 1-10. The daily schedule only queues what is missing and does
nothing while the holding is locked; the one-shot's claim answers 204 then.

The owner's own voice (POST /media/voices/reference): 1-3 minutes of the
owner's clean speech, an owner file that is never attached, never sent
anywhere and never read by an agent; only an installed cloning engine on the
hub would read it (none is installed: the cloning candidates are gated and
over the memory budget, see `note_fa`).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import gate
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.speech import fa_speech_script

SERVICE = Principal(kind="service", code="voices", role="service")
TTS = Principal(kind="service", code="tts", role="service")
ROUND = 1  # the scripts' version: a new script set is a new round
RECLAIM_MIN = 15
MAX_ATTEMPTS = 3
REFERENCE_MIN_S, REFERENCE_MAX_S = 60, 180
NARRATION_MAX = 6000  # characters of one item's narration
PIPER_REPO = "rhasspy/piper-voices"
PIPER_REVISION = "5041a7a49ae5b3a0f30e6837769eb03fdbb231bd"
HUB_CPU = "Hetzner CPX42, 8 vCPU AMD EPYC, 1 thread per job"

# The fixed bake-off scripts (prompt 13 §4.2). text_fa is what the owner sees;
# each voice speaks fa_speech_script(text_fa), exactly what the hub feeds it.
SCRIPTS: tuple[dict[str, str], ...] = (
    {
        "key": "numbers",
        "title_fa": "عدد و درصد",
        "text_fa": (
            "قیمت بیت‌کوین امروز $64,250 است، یعنی 2.35% بالاتر از دیروز. "
            "حجم معاملات بیست‌وچهار ساعت گذشته 1.2 میلیارد دلار بود و 18% آن در یک ساعت انجام شد. "
            "کارمزد شبکه به $0.85 رسید و 1,204 تراکنش در صف ماند."
        ),
    },
    {
        "key": "latin",
        "title_fa": "اصطلاح لاتین",
        "text_fa": (
            "شاخص RSI روی نمودار روزانه‌ی Bitcoin به محدوده‌ی اشباع خرید رسیده و MACD هم "
            "واگرایی منفی نشان میدهد. Ethereum هنوز زیر میانگین متحرک دویست‌روزه است و "
            "پشتیبانی بعدی آن روی ناحیه‌ی Fibonacci قرار دارد."
        ),
    },
    {
        "key": "crypto",
        "title_fa": "کلمه‌های کریپتو",
        "text_fa": (
            "امروز این واژه‌ها را ساده توضیح میدهیم: کیف پول سخت‌افزاری، عبارت بازیابی، "
            "استیبل‌کوین، صرافی غیرمتمرکز، استخراج، هاوینگ، نقدشوندگی، لوریج، لیکوئید شدن، "
            "حد ضرر و قرارداد هوشمند."
        ),
    },
    {
        "key": "long",
        "title_fa": "یک جمله‌ی بلند",
        "text_fa": (
            "اگر پیش از هر معامله حد ضرر را مشخص کنی، حجم هر موقعیت را با توجه به کل سرمایه‌ات "
            "بسنجی، از اهرم بیش از اندازه دوری کنی، خبرهای مهم اقتصادی را در تقویم ببینی و بعد "
            "از هر معامله دلیل ورود و خروج را در دفترچه‌ات بنویسی، کم‌کم می‌بینی که تصمیم‌هایت "
            "آرام‌تر، منظم‌تر و قابل دفاع‌تر شده‌اند و دیگر با هر نوسان کوچک بازار نگران نمیشوی."
        ),
    },
    {
        "key": "reel60",
        "title_fa": "متن شصت ثانیه‌ای ریلز",
        "text_fa": (
            "سلام، امروز در یک دقیقه یاد میگیریم حد ضرر چیست و چرا مهم است.\n"
            "حد ضرر قیمتی است که از قبل تعیین میکنی تا اگر بازار خلاف پیش‌بینی‌ات رفت، "
            "معامله خودکار بسته شود.\n"
            "فرض کن بیت‌کوین را در قیمت شصت هزار دلار خریده‌ای و حد ضرر را پنجاه و هشت هزار "
            "دلار گذاشته‌ای. اگر قیمت به آن‌جا برسد، فقط حدود سه درصد از این معامله را از دست "
            "میدهی، نه همه‌ی سرمایه را.\n"
            "سه نکته را یادت باشد. اول، حد ضرر را پیش از ورود بنویس، نه وسط هیجان بازار. "
            "دوم، آن را جایی بگذار که منطق تحلیلت باطل میشود، نه یک عدد دلخواه. "
            "سوم، بعد از ورود، حد ضرر را از روی ترس جابه‌جا نکن.\n"
            "معامله‌گرهای حرفه‌ای هم ضرر میکنند؛ فرقشان این است که ضرر را کوچک نگه میدارند.\n"
            "این محتوا آموزشی است و توصیه‌ی مالی نیست. معامله در بازارهای مالی ریسک از دست "
            "دادن سرمایه دارد.\n"
            "اگر این ویدیو برایت مفید بود، آن را برای دوستت بفرست."
        ),
    },
)

_PIPER_LICENCE = "MIT (weights, rhasspy/piper-voices); dataset CC0-1.0 (its MODEL_CARD)"
# The registry's starting rows (data, not code paths). The Piper numbers are
# the hub's own measurement (prompt 12 §4: 121 words; prompt 13 bake-off).
SEED: tuple[dict[str, Any], ...] = (
    {
        "id": "piper-amir",
        "engine": "piper",
        "name_fa": "پایپر · امیر (مرد)",
        "licence": _PIPER_LICENCE,
        "licence_commercial": True,
        "speaker": "model",
        "runtime": {"piper_voice": "fa_IR-amir-medium"},
        "source": {
            "repo": PIPER_REPO,
            "revision": PIPER_REVISION,
            "path": "fa/fa_IR/amir/medium",
            "onnx_sha256": "fb815380d969ea372b0b21b0de14421f58fe481047e153e69685d079b6e1a9d1",
        },
        "sort": 10,
        "active": True,  # the voice prompt 12 speaks with, until the owner chooses (§0.9 #2)
        "note_fa": "صدای فعلی گزارش‌های صوتی؛ تا انتخاب مالک پیش‌فرض است.",
    },
    {
        "id": "piper-ganji",
        "engine": "piper",
        "name_fa": "پایپر · گنجی (مرد)",
        "licence": _PIPER_LICENCE,
        "licence_commercial": True,
        "speaker": "model",
        "runtime": {"piper_voice": "fa_IR-ganji-medium"},
        "source": {
            "repo": PIPER_REPO,
            "revision": PIPER_REVISION,
            "path": "fa/fa_IR/ganji/medium",
            "onnx_sha256": "6a98504bb77dc2fd3a863c977d37e67a6a525fdf661917385d569a3ff78e6cae",
        },
        "sort": 11,
    },
    {
        "id": "piper-ganji-adabi",
        "engine": "piper",
        "name_fa": "پایپر · گنجی ادبی (مرد)",
        "licence": _PIPER_LICENCE,
        "licence_commercial": True,
        "speaker": "model",
        "runtime": {"piper_voice": "fa_IR-ganji_adabi-medium"},
        "source": {
            "repo": PIPER_REPO,
            "revision": PIPER_REVISION,
            "path": "fa/fa_IR/ganji_adabi/medium",
            "onnx_sha256": "e9073b41ae65759dcf95778e569c8f3780406dac99549436f6ab8e7d2336ed72",
        },
        "sort": 12,
    },
    {
        "id": "piper-reza-ibrahim",
        "engine": "piper",
        "name_fa": "پایپر · رضا ابراهیم (مرد)",
        "licence": _PIPER_LICENCE,
        "licence_commercial": True,
        "speaker": "model",
        "runtime": {"piper_voice": "fa_IR-reza_ibrahim-medium"},
        "source": {
            "repo": PIPER_REPO,
            "revision": PIPER_REVISION,
            "path": "fa/fa_IR/reza_ibrahim/medium",
            "onnx_sha256": "99f0c31464a2120831ca87d079e10a9a2b3e426cc1ee662d80ff9042df15cd3c",
        },
        "sort": 13,
    },
    {
        "id": "piper-gyro",
        "engine": "piper",
        "name_fa": "پایپر · ژیرو (مرد)",
        "licence": 'MIT (weights, rhasspy/piper-voices); dataset licence not stated on its MODEL_CARD ("See URL")',
        "licence_commercial": False,
        "speaker": "model",
        "runtime": None,  # not shipped in the TTS image (voice.lock.json)
        "source": {
            "repo": PIPER_REPO,
            "revision": PIPER_REVISION,
            "path": "fa/fa_IR/gyro/medium",
            "onnx_sha256": "37dfae43c82ee38ca9e6aac4ffef76a74d6b282ccbc397b27761f35d355c99ba",
        },
        "sort": 14,
        "note_fa": (
            "لایسنس داده‌ی آموزشش روی کارتش نیامده؛ تا روشن شدن نه تجاری حساب میشود "
            "و نه در image صدا گذاشته شده."
        ),
    },
    {
        "id": "manatts-piper",
        "engine": "piper",
        "name_fa": "پایپر آموزش‌دیده روی ManaTTS (زن)",
        "licence": "ManaTTS corpus CC0-1.0; Piper (VITS) MIT",
        "licence_commercial": True,
        "speaker": "model",
        "runtime": None,
        "source": {
            "dataset": "MahtaFetrat/Mana-TTS",
            "architecture": "Piper/VITS fine-tune from fa_IR-amir-medium",
        },
        "sort": 20,
        "note_fa": (
            "هنوز آموزش ندیده: آموزش روی ۸۶ ساعت ManaTTS حدود ۲۴ تا ۴۸ ساعت GPU میخواهد "
            "(برآورد ۱۵ تا ۷۰ دلار کرایه)؛ کرایه‌ی GPU تصمیم مالک است (§۰.۹ بند ۳)."
        ),
    },
    {
        "id": "parsvoice-xtts",
        "engine": "xtts",
        "name_fa": "ParsVoice-XTTS · گوینده‌های خود مدل",
        "licence": (
            "Coqui Public Model License 1.0.0 (non-commercial; the card's header says MIT, "
            "its licence section CPML)"
        ),
        "licence_commercial": False,
        "speaker": "model",
        "clones": True,
        "runtime": None,
        "source": {
            "repo": "MohammadJRanjbar/ParsVoice-XTTS",
            "base": "coqui/XTTS-v2",
            "gated": True,
        },
        "sort": 30,
        "note_fa": (
            "انتخاب مالک (۲۰۲۶-۱۰-۲۲). دانلودش gated است و با حساب Hugging Face خود مالک باز میشود؛ "
            "XTTS-v2 روی CPU حدود ۲٫۵ تا ۳ گیگ حافظه میخواهد و از بودجه‌ی پروفایل tts بیرون است. "
            "غیرتجاری: بی انتخاب صریح مالک فعال نمیشود."
        ),
    },
    {
        "id": "parsvoice-xtts-owner",
        "engine": "xtts",
        "name_fa": "ParsVoice-XTTS · صدای خود مالک",
        "licence": "Coqui Public Model License 1.0.0 (non-commercial)",
        "licence_commercial": False,
        "speaker": "owner",
        "clones": True,
        "runtime": None,
        "source": {"repo": "MohammadJRanjbar/ParsVoice-XTTS", "reference": "the owner's recording"},
        "sort": 31,
        "note_fa": "منتظر نمونه‌ی صدای مالک و نصب موتور (همان دو مانع ParsVoice-XTTS).",
    },
    {
        "id": "chatterbox-fa",
        "engine": "chatterbox",
        "name_fa": "Chatterbox فارسی · گوینده‌ی مدل",
        "licence": "CC BY-NC 4.0 (Thomcles/Chatterbox-TTS-Persian-Farsi)",
        "licence_commercial": False,
        "speaker": "model",
        "clones": True,
        "runtime": None,
        "source": {
            "repo": "Thomcles/Chatterbox-TTS-Persian-Farsi",
            "base": "ResembleAI/chatterbox",
            "gated": True,
        },
        "sort": 40,
        "note_fa": (
            "دانلودش gated است (حساب Hugging Face مالک)؛ مدل ۵۰۰ میلیون پارامتری روی CPU از "
            "بودجه‌ی حافظه‌ی tts بیرون است. غیرتجاری."
        ),
    },
    {
        "id": "chatterbox-fa-owner",
        "engine": "chatterbox",
        "name_fa": "Chatterbox فارسی · صدای خود مالک",
        "licence": "CC BY-NC 4.0 (Thomcles/Chatterbox-TTS-Persian-Farsi)",
        "licence_commercial": False,
        "speaker": "owner",
        "clones": True,
        "runtime": None,
        "source": {
            "repo": "Thomcles/Chatterbox-TTS-Persian-Farsi",
            "reference": "the owner's recording",
        },
        "sort": 41,
        "note_fa": "منتظر نمونه‌ی صدای مالک و نصب موتور.",
    },
)
# The hub's own measurements of the Piper voices (the bake-off of 2026-10-23
# on this CPX42, the image coinepro-hq/tts; RUNBOOK §31.6): voice -> (rtf, peak MiB).
MEASURED: dict[str, tuple[float, float]] = {}
MEASURED_AT = datetime(2026, 10, 23, tzinfo=UTC)

# Called when a narration is ready (the media studio moves its item on):
# (tx, job row, file id). The voice side knows no media item.
ON_NARRATION: list[Callable[[Tx, dict[str, Any], UUID], Awaitable[None]]] = []


# ------------------------------------------------------------------ seed --
async def seed(tx: Tx, holding_id: UUID) -> int:
    """The starting rows, once (later measurements, scores and the owner's
    choice survive); the measured numbers fill a row still unmeasured, and
    the default voice is active only while no voice is."""
    added = 0
    has_active = bool(await tx.scalar("SELECT 1 FROM media.voices WHERE status = 'active'"))
    for v in SEED:
        rtf, mem = MEASURED.get(v["id"], (None, None))
        if v["id"] == "piper-amir" and rtf is None:
            rtf, mem = 0.1, 253.0  # prompt 12 §4's measurement (RUNBOOK §30)
        active = bool(v.get("active")) and not has_active and rtf is not None
        row = await tx.first(
            """INSERT INTO media.voices (id, company_id, engine, name_fa, licence, licence_commercial,
                   speaker, clones, runtime, source, rtf, mem_mb, measured_at, measured_on, status,
                   activated_at, note_fa, sort)
               VALUES (:id, :co, :eng, :name, :lic, :com, :sp, :cl, CAST(:rt AS jsonb), CAST(:src AS jsonb),
                       :rtf, :mem, CASE WHEN CAST(:rtf AS numeric) IS NULL THEN NULL ELSE CAST(:at AS timestamptz) END,
                       CASE WHEN CAST(:rtf AS numeric) IS NULL THEN NULL ELSE :on END,
                       :st, CASE WHEN :st = 'active' THEN now() END, :note, :sort)
               ON CONFLICT (id) DO NOTHING RETURNING id""",
            id=v["id"],
            co=holding_id,
            eng=v["engine"],
            name=v["name_fa"],
            lic=v["licence"],
            com=v["licence_commercial"],
            sp=v["speaker"],
            cl=bool(v.get("clones")),
            rt=json.dumps(v["runtime"]) if v.get("runtime") else None,
            src=json.dumps(v.get("source") or {}),
            rtf=rtf,
            mem=mem,
            at=MEASURED_AT,
            on=HUB_CPU,
            st="active" if active else "candidate",
            note=v.get("note_fa"),
            sort=int(v.get("sort", 100)),
        )
        if row is not None:
            added += 1
            has_active = has_active or active
        elif rtf is not None:
            await tx.exec(
                """UPDATE media.voices SET rtf = :rtf, mem_mb = :mem, measured_at = CAST(:at AS timestamptz),
                       measured_on = :on WHERE id = :id AND measured_at IS NULL""",
                rtf=rtf,
                mem=mem,
                at=MEASURED_AT,
                on=HUB_CPU,
                id=v["id"],
            )
    return added


# ------------------------------------------------------------- rendering --
VOICE_SQL = "SELECT v.* FROM media.voices v"


async def samples_of(tx: Tx, ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    from hq_api.domain import files as F

    rows = await tx.all(
        """SELECT DISTINCT ON (s.voice_id, s.script_key) s.voice_id, s.script_key, s.file_id, s.duration_s,
                  s.synth_s, s.peak_mb, s.round
           FROM media.voice_samples s WHERE s.voice_id = ANY(:ids)
           ORDER BY s.voice_id, s.script_key, s.round DESC, s.at DESC""",
        ids=ids,
    )
    refs = await F.refs(tx, [r["file_id"] for r in rows])
    titles = {s["key"]: s for s in SCRIPTS}
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        s = titles.get(r["script_key"])
        out.setdefault(r["voice_id"], []).append(
            {
                "script": r["script_key"],
                "title_fa": s["title_fa"] if s else r["script_key"],
                "text_fa": s["text_fa"] if s else "",
                "file": refs.get(r["file_id"]),
                "duration_s": float(r["duration_s"]),
                "rtf": round(float(r["synth_s"]) / float(r["duration_s"]), 3),
                "peak_mb": float(r["peak_mb"]) if r["peak_mb"] is not None else None,
            }
        )
    order = [s["key"] for s in SCRIPTS]
    for v in out.values():
        v.sort(key=lambda x: order.index(x["script"]) if x["script"] in order else 99)
    return out


def render(r: dict[str, Any], samples: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": r["id"],
        "engine": r["engine"],
        "name_fa": r["name_fa"],
        "licence": r["licence"],
        "licence_commercial": r["licence_commercial"],
        "rtf": float(r["rtf"]) if r["rtf"] is not None else None,
        "mem_mb": float(r["mem_mb"]) if r["mem_mb"] is not None else None,
        "owner_score": r["owner_score"],
        "status": r["status"],
        "speaker": r["speaker"],
        "clones": r["clones"],
        "installed": r["runtime"] is not None,
        "samples": samples,
        "note_fa": r["note_fa"],
        "measured_at": r["measured_at"],
        "measured_on": r["measured_on"],
        "version": r["version"],
    }


async def all_voices(tx: Tx) -> list[dict[str, Any]]:
    rows = await tx.all(VOICE_SQL + " ORDER BY v.sort, v.id")
    samples = await samples_of(tx, [r["id"] for r in rows])
    return [render(r, samples.get(r["id"], [])) for r in rows]


async def one(tx: Tx, voice_id: str, *, lock: bool = False) -> dict[str, Any]:
    row = await tx.first(
        VOICE_SQL + " WHERE v.id = :id" + (" FOR UPDATE" if lock else ""), id=voice_id
    )
    if row is None:
        raise ApiError(404, "not_found", f"no voice {voice_id}")
    return row


async def active(tx: Tx) -> dict[str, Any] | None:
    row: dict[str, Any] | None = await tx.first(VOICE_SQL + " WHERE v.status = 'active'")
    return row


async def briefing_voice(tx: Tx, settings: Any) -> dict[str, str]:
    """The voice block of a briefing (contract §21.4): the registry's active
    voice when the TTS image runs it, else prompt 12's configured default."""
    from hq_api.domain import briefings as B

    v = await active(tx)
    name = ((v or {}).get("runtime") or {}).get("piper_voice") if v else None
    if v is None or not name or v["engine"] != "piper":
        return B.voice(settings)
    return {"engine": "piper", "version": B.PIPER_VERSION, "voice": name, "license": v["licence"]}


# --------------------------------------------------------- owner's acts --
async def score(tx: Tx, who: Principal, voice_id: str, value: int) -> dict[str, Any]:
    v = await one(tx, voice_id, lock=True)
    await tx.exec(
        "UPDATE media.voices SET owner_score = :s, scored_at = now() WHERE id = :id",
        s=value,
        id=v["id"],
    )
    await audit.record(
        tx, who, company_id=v["company_id"], action="voice.score", action_class="A1",
        target_kind="voice", target_ref=v["id"], summary=f"{value}/10",
    )  # fmt: skip
    return await one(tx, voice_id)


async def activate(
    tx: Tx, who: Principal, voice_id: str, *, accept_non_commercial: bool, step_up: bool
) -> dict[str, Any]:
    """The owner's choice (🔏 voice.activate): an installed, measured voice;
    a non-commercial one only with accept_non_commercial."""
    v = await one(tx, voice_id, lock=True)
    if v["status"] == "retired":
        raise ApiError(409, "validation_failed", f"{voice_id} is retired")
    if v["runtime"] is None or v["measured_at"] is None:
        raise ApiError(409, "not_ready", f"{voice_id} is not installed and measured on the hub")
    if not v["licence_commercial"] and not accept_non_commercial:
        raise ApiError(
            422,
            "validation_failed",
            "a non-commercial voice is activated only with the owner's explicit acceptance",
            fields={"accept_non_commercial": "required for a non-commercial licence"},
        )
    if v["status"] != "active":
        await tx.exec("UPDATE media.voices SET status = 'candidate' WHERE status = 'active'")
        await tx.exec(
            "UPDATE media.voices SET status = 'active', activated_at = now() WHERE id = :id",
            id=v["id"],
        )
    await audit.record(
        tx, who, company_id=v["company_id"], action="voice.activate", action_class="A2",
        target_kind="voice", target_ref=v["id"], step_up=step_up,
        summary="non-commercial, accepted by the owner" if not v["licence_commercial"] else "commercial",
    )  # fmt: skip
    return await one(tx, voice_id)


# ---------------------------------------------------------- the reference --
async def reference(tx: Tx) -> dict[str, Any] | None:
    from hq_api.domain import files as F

    r = await tx.first(
        "SELECT * FROM media.voice_references WHERE state <> 'superseded' ORDER BY created_at DESC LIMIT 1"
    )
    if r is None:
        return None
    ref = (await F.refs(tx, [r["file_id"]])).get(r["file_id"])
    state = r["state"]
    if state == "processing" and ref is not None and ref.status == "ready":
        state = "ready"
    if ref is not None and ref.status == "failed":
        state = "rejected"
    return {
        "file": ref,
        "duration_s": float(r["duration_s"]),
        "created_at": r["created_at"],
        "state": state,
        "reason_fa": r["reason_fa"] or ("فایل خوانده نشد" if state == "rejected" else None),
    }


async def set_reference(tx: Tx, who: Principal, file_id: UUID) -> dict[str, Any]:
    """The owner's own voice: an owner audio upload of 1-3 minutes, never
    attached to a message (so no agent reads it) and never sent anywhere."""
    f = await tx.first(
        """SELECT f.id, f.company_id, f.kind, f.variant, f.created_by_kind, f.duration_s,
                  COALESCE(p.status, 'ready') AS status
           FROM files.files f LEFT JOIN files.processing p ON p.file_id = f.id WHERE f.id = :id""",
        id=file_id,
    )
    holding = await tx.scalar("SELECT id FROM core.companies WHERE kind = 'holding'")
    if (
        f is None
        or f["kind"] != "audio"
        or f["variant"] != "original"
        or f["created_by_kind"] != "owner"
        or f["company_id"] != holding
    ):
        raise ApiError(
            422, "validation_failed", fields={"file_id": "an audio file of your own, not attached"}
        )
    if await tx.scalar(
        "SELECT 1 FROM msg.messages WHERE attachments @> ARRAY[CAST(:f AS uuid)]", f=file_id
    ):
        raise ApiError(
            422, "validation_failed", fields={"file_id": "already attached to a message"}
        )
    dur = float(f["duration_s"] or 0)
    if not REFERENCE_MIN_S <= dur <= REFERENCE_MAX_S:
        raise ApiError(
            422,
            "validation_failed",
            f"the reference is {dur:.0f} s; 1 to 3 minutes of clean speech",
            fields={"duration_s": f"between {REFERENCE_MIN_S} and {REFERENCE_MAX_S} seconds"},
        )
    await tx.exec(
        "UPDATE media.voice_references SET state = 'superseded', updated_at = now() WHERE state <> 'superseded'"
    )
    state = (
        "ready"
        if f["status"] == "ready"
        else ("rejected" if f["status"] == "failed" else "processing")
    )
    await tx.exec(
        """INSERT INTO media.voice_references (company_id, file_id, duration_s, state)
           VALUES (:co, :f, :d, :st)""",
        co=holding,
        f=file_id,
        d=dur,
        st=state,
    )
    await audit.record(
        tx, who, company_id=holding, action="voice.reference", action_class="A1",
        target_kind="file", target_ref=str(file_id), summary=f"{dur:.0f} s",
    )  # fmt: skip
    out = await reference(tx)
    assert out is not None
    return out


# ----------------------------------------------------------------- jobs --
def spoken(script_key: str) -> str:
    s = next(x for x in SCRIPTS if x["key"] == script_key)
    return fa_speech_script(s["text_fa"])


async def queue_bakeoff(tx: Tx) -> dict[str, Any]:
    """The bake-off schedule (daily): queue what is missing for every
    runnable voice of this round; nothing at all while the holding is locked."""
    if (lock := await gate.holding_lock(tx)) is not None:
        return gate.skipped(lock)
    has_reference = bool(
        await tx.scalar("SELECT 1 FROM media.voice_references WHERE state = 'ready'")
    )
    rows = await tx.all(
        "SELECT id, company_id, speaker FROM media.voices WHERE runtime IS NOT NULL AND status <> 'retired'"
    )
    queued = 0
    for v in rows:
        if v["speaker"] == "owner" and not has_reference:
            continue
        for s in SCRIPTS:
            n = await tx.exec(
                """INSERT INTO media.speech_jobs (company_id, kind, voice_id, script_key, round, script,
                       created_by_kind, created_by_code)
                   VALUES (:co, 'sample', :v, :k, :r, :s, 'service', 'voices')
                   ON CONFLICT (voice_id, script_key, round) WHERE kind = 'sample' DO NOTHING""",
                co=v["company_id"],
                v=v["id"],
                k=s["key"],
                r=ROUND,
                s=spoken(s["key"]),
            )
            queued += int(n or 0)
    return {"queued": queued, "voices": len(rows)}


async def narrate(
    tx: Tx, who: Principal, *, company_id: UUID, ref: str, text_fa: str, voice_id: str | None
) -> dict[str, Any]:
    """media.voice (A2): a media item's narration with the active voice (or
    the one its series names). A non-commercial voice is refused unless it
    is the active one the owner chose (`licence_not_chosen`)."""
    v = await (one(tx, voice_id) if voice_id else active(tx))
    if v is None:
        raise ApiError(409, "not_ready", "no active voice yet")
    if v["runtime"] is None or v["measured_at"] is None:
        raise ApiError(409, "not_ready", f"{v['id']} is not installed on the hub")
    if not v["licence_commercial"] and v["status"] != "active":
        raise ApiError(
            409, "validation_failed", f"{v['id']} is non-commercial and not the owner's choice",
            fields={"voice_id": "licence_not_chosen"},
        )  # fmt: skip
    if await tx.scalar("SELECT to_regclass('media.items') IS NOT NULL") and not await tx.scalar(
        "SELECT 1 FROM media.items WHERE ref = :r AND company_id = :co", r=ref, co=company_id
    ):
        raise ApiError(404, "not_found", f"no media item {ref}")
    script = fa_speech_script(text_fa)
    if len(script) > NARRATION_MAX:
        raise ApiError(
            422,
            "validation_failed",
            fields={"text_fa": f"at most {NARRATION_MAX} characters spoken"},
        )
    await tx.exec(
        """UPDATE media.speech_jobs SET state = 'cancelled', updated_at = now()
           WHERE kind = 'narration' AND subject_ref = :r AND company_id = :co AND state = 'queued'""",
        r=ref,
        co=company_id,
    )
    job = await tx.one(
        """INSERT INTO media.speech_jobs (company_id, kind, voice_id, subject_ref, script, created_by_kind,
               created_by_code)
           VALUES (:co, 'narration', :v, :r, :s, :bk, :bc) RETURNING id, state""",
        co=company_id,
        v=v["id"],
        r=ref,
        s=script,
        bk=who.kind,
        bc=who.code,
    )
    await audit.record(
        tx, who, company_id=company_id, action="media.voice", action_class="A2",
        target_kind="media_item", target_ref=ref, summary=f"{v['id']}, {len(script)} chars",
    )  # fmt: skip
    return {
        "job": str(job["id"]),
        "item": ref,
        "state": job["state"],
        "voice": {"id": v["id"], "name_fa": v["name_fa"], "licence": v["licence"],
                  "licence_commercial": v["licence_commercial"]},
        "spoken_chars": len(script),
    }  # fmt: skip


async def claim(tx: Tx) -> dict[str, Any] | None:
    """The oldest queued job (narration before samples) for the TTS one-shot;
    None while the holding is locked or when nothing waits."""
    if await gate.holding_lock(tx) is not None:
        return None
    row = await tx.first(
        """SELECT j.id, j.kind, j.voice_id, j.script_key, j.subject_ref, j.script, j.attempts, v.engine, v.runtime
           FROM media.speech_jobs j JOIN media.voices v ON v.id = j.voice_id
           WHERE (j.state = 'queued'
                  OR (j.state = 'claimed' AND j.claimed_at < now() - make_interval(mins => :m)))
           ORDER BY j.kind = 'narration' DESC, j.created_at LIMIT 1 FOR UPDATE OF j SKIP LOCKED""",
        m=RECLAIM_MIN,
    )
    if row is None:
        return None
    if int(row["attempts"]) >= MAX_ATTEMPTS or row["runtime"] is None:
        await tx.exec(
            """UPDATE media.speech_jobs SET state = 'failed', updated_at = now(),
                   error = CASE WHEN :ni THEN 'not installed' ELSE 'too many attempts' END WHERE id = :id""",
            ni=row["runtime"] is None,
            id=row["id"],
        )
        return None
    await tx.exec(
        """UPDATE media.speech_jobs SET state = 'claimed', claimed_at = now(), attempts = attempts + 1,
               updated_at = now() WHERE id = :id""",
        id=row["id"],
    )
    rt = row["runtime"] if isinstance(row["runtime"], dict) else json.loads(row["runtime"])
    return {
        "id": row["id"],
        "kind": row["kind"],
        "ref": row["subject_ref"] or f"{row['voice_id']}/{row['script_key']}",
        "engine": row["engine"],
        "voice": rt.get("piper_voice"),
        "script": row["script"],
    }


async def job(tx: Tx, job_id: UUID, *, lock: bool = True) -> dict[str, Any]:
    row = await tx.first(
        "SELECT * FROM media.speech_jobs WHERE id = :id"  # noqa: S608 - constant SQL, bound value
        + (" FOR UPDATE" if lock else ""),
        id=job_id,
    )
    if row is None:
        raise ApiError(404, "not_found", "no such job")
    return row


async def finish(
    tx: Tx,
    j: dict[str, Any],
    *,
    file_id: UUID,
    duration_s: float,
    synth_s: float | None,
    peak_mb: float | None,
) -> dict[str, Any]:
    """The audio is stored (§17.1, by the route): the sample and the voice's
    measurement, or the narration's hook."""
    if j["state"] not in ("claimed", "queued"):
        raise ApiError(409, "validation_failed", f"the job is {j['state']}")
    await tx.exec(
        """UPDATE media.speech_jobs SET state = 'done', file_id = :f, error = NULL, updated_at = now(),
               result = CAST(:r AS jsonb) WHERE id = :id""",
        f=file_id,
        r=json.dumps({"duration_s": duration_s, "synth_s": synth_s, "peak_mb": peak_mb}),
        id=j["id"],
    )
    if j["kind"] == "sample":
        await tx.exec(
            """INSERT INTO media.voice_samples (company_id, voice_id, script_key, round, job_id, file_id,
                   duration_s, synth_s, peak_mb)
               VALUES (:co, :v, :k, :r, :j, :f, :d, :s, :p)""",
            co=j["company_id"],
            v=j["voice_id"],
            k=j["script_key"],
            r=j["round"],
            j=j["id"],
            f=file_id,
            d=duration_s,
            s=synth_s or 0,
            p=peak_mb,
        )
        # The voice's numbers: the real-time factor over this round's samples
        # (work seconds / audio seconds) and the highest peak memory.
        await tx.exec(
            """UPDATE media.voices v SET rtf = m.rtf, mem_mb = COALESCE(m.peak, v.mem_mb),
                   measured_at = now(), measured_on = :on
               FROM (SELECT round(sum(synth_s) / NULLIF(sum(duration_s), 0), 3) AS rtf, max(peak_mb) AS peak
                     FROM media.voice_samples WHERE voice_id = :v AND round = :r) m
               WHERE v.id = :v AND m.rtf IS NOT NULL""",
            v=j["voice_id"],
            r=j["round"],
            on=HUB_CPU,
        )
    else:
        for hook in ON_NARRATION:
            await hook(tx, j, file_id)
        code = await tx.scalar("SELECT code FROM core.companies WHERE id = :id", id=j["company_id"])
        await events.emit(
            tx, code, "media.voice", j["subject_ref"], {"job": str(j["id"]), "file": str(file_id)}
        )
    await audit.record(
        tx, TTS, company_id=j["company_id"], action="voice.audio", action_class="A1",
        target_kind="speech_job", target_ref=str(j["id"]),
        summary=f"{j['kind']} {j['voice_id']}: {duration_s:.1f} s",
    )  # fmt: skip
    return {"job": str(j["id"]), "state": "done", "file": str(file_id)}


async def fail(tx: Tx, j: dict[str, Any], error: str) -> None:
    import re

    final = int(j["attempts"]) >= MAX_ATTEMPTS
    await tx.exec(
        """UPDATE media.speech_jobs SET state = CASE WHEN :final THEN 'failed' ELSE 'queued' END,
               error = :e, claimed_at = NULL, updated_at = now() WHERE id = :id""",
        final=final,
        e=re.sub(r"[^A-Za-z0-9 _.:-]", "", error)[:300] or "failed",
        id=j["id"],
    )
