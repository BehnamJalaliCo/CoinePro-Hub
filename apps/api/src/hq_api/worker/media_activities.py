"""Temporal activities for owner media (prompt 6 §2-§3).

file_process     a video or audio upload: poster, key frames, sound track,
                 transcript (status processing -> ready | failed, then
                 file.ready / file.failed on the stream)
transcribe_file  POST /transcribe: the same transcription for one audio
                 file, awaited by the api

Each attempt is counted when it starts (a worker killed mid-way still counts),
and a file that used MAX_ATTEMPTS fails instead of being tried for ever. What
is stored or announced goes to the company the file belongs to at that moment
(read FOR SHARE, so an attachment that moves it waits, or comes first): a
variant never stays behind in the holding (06.1 §2).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from temporalio import activity
from temporalio.exceptions import ApplicationError

from hq_api import events
from hq_api.agents.clients import Router
from hq_api.domain import files as F
from hq_api.hub import Hub
from hq_api.worker import media as M
from hq_common import persian
from hq_common.redact import scrub

log = logging.getLogger("hq_api.worker.media")
STT_UNAVAILABLE = "SttUnavailable"
STT_BUSY = "SttBusy"
MAX_ATTEMPTS = 3  # as the worker's reconcile (_resume_files) counts them
BUSY_WAIT_FILE_S = 600.0  # an upload in the background may wait for the stt queue
BUSY_WAIT_TRANSCRIBE_S = 120.0  # the owner is waiting for /transcribe


class MediaActivities:
    def __init__(
        self,
        hub: Hub,
        router: Router,
        tx: Any,
        stt_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.hub = hub
        self.router = router
        self._tx = tx  # a callable opening a transaction over every company
        self.stt_transport = stt_transport  # tests: a fake stt service

    def all(self) -> list[Any]:
        return [self.file_process, self.transcribe_file]

    @contextlib.asynccontextmanager
    async def _beating(self) -> AsyncIterator[None]:
        async def beat() -> None:
            while True:
                await asyncio.sleep(10)
                activity.heartbeat()

        task = asyncio.create_task(beat()) if activity.in_activity() else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()

    async def _file(self, file_id: str) -> dict[str, Any]:
        async with self._tx() as tx:
            row = await F.load(tx, UUID(file_id))
            row["company"] = await tx.scalar(
                "SELECT code FROM core.companies WHERE id = :id", id=row["company_id"]
            )
        return row

    async def _synthetic(self, f: dict[str, Any]) -> bool:
        """⟨1.6⟩ made by the hub's TTS one-shot (a bake-off sample, a narration)."""
        async with self._tx() as tx:
            return bool(
                await tx.scalar(
                    """SELECT created_by_kind = 'service' AND created_by_code = 'tts'
                       FROM files.files WHERE id = :id""",
                    id=f["id"],
                )
            )

    async def _start(self, f: dict[str, Any]) -> int:
        """This attempt, counted before any work (06.1 §2)."""
        async with self._tx() as tx:
            n = await tx.scalar(
                """UPDATE files.processing SET attempts = attempts + 1, updated_at = now()
                   WHERE file_id = :id RETURNING attempts""",
                id=f["id"],
            )
        return int(n or 0)

    @staticmethod
    async def _owner_now(tx: Any, file_id: UUID) -> tuple[UUID, str]:
        """The file's company now, its row locked FOR SHARE until the end of
        `tx`: an attachment moving it (F.attach locks it FOR UPDATE) waits for
        this transaction, or has already committed and is seen here."""
        co: UUID = await tx.scalar("SELECT files.lock_company(:id)", id=file_id)
        code: str = await tx.scalar("SELECT code FROM core.companies WHERE id = :id", id=co)
        return co, code

    async def _has_variant(self, f: dict[str, Any], variant: str) -> bool:
        """A retried attempt keeps what an earlier one stored."""
        async with self._tx() as tx:
            return bool(
                await tx.scalar(
                    "SELECT 1 FROM files.files WHERE parent_id = :p AND variant = :v LIMIT 1",
                    p=f["id"],
                    v=variant,
                )
            )

    async def _store_variant(
        self, f: dict[str, Any], variant: str, data: bytes, at: float | None = None
    ) -> UUID:
        key, sha = await self.hub.storage.put(data)
        async with self._tx() as tx:
            company_id, _ = await self._owner_now(tx, f["id"])
            return await F.insert(
                tx,
                company_id=company_id,
                name=f"{variant}-{f['name']}"[:255],
                mime="image/jpeg",
                size=len(data),
                sha256=sha,
                storage_key=key,
                kind="image",
                by_kind="service",
                by_code="media",
                variant=variant,
                parent_id=f["id"],
                frame_at_s=at,
            )

    # ------------------------------------------------------------ speech --
    async def speech(
        self, wav: Path, busy_wait_s: float = BUSY_WAIT_FILE_S, *, punctuate: bool = True
    ) -> dict[str, Any]:
        """Whisper (stt), the normaliser (there and again here), then the
        punctuation pass; both texts are kept for the quality log.
        ⟨1.6⟩ `punctuate=False`: the hub's own synthetic voice (prompt 13 §4)
        is checked by its transcript only; no model reads it."""
        s = self.hub.settings
        res = await M.transcribe(
            s.stt_url,
            wav,
            busy_wait_s=busy_wait_s,
            transport=self.stt_transport,
            demand_dir=s.stt_demand_dir,
            cold_start_s=s.stt_cold_start_s,
        )
        normalised = persian.normalise(res.get("text") or "")
        final, punctuation, ratio = normalised, "off", None
        if punctuate and normalised and s.stt_punctuation and self.hub.secrets.llm_router_token:
            if scrub(normalised) != normalised:
                punctuation = "off"  # a secret was spoken: no model reads it
            else:
                final, punctuation, ratio = await self._punctuate(normalised)
        return {
            "text": final,
            "normalised": normalised,
            "punctuation": punctuation,
            "edit_ratio": ratio,
            "language": "fa",
            "duration_s": float(res.get("duration_s") or 0),
            "confidence": float(res.get("confidence") or 0),
            "segments": res.get("segments") or [],
            "engine": res.get("engine") or {},
        }

    async def _punctuate(self, text: str) -> tuple[str, str, float | None]:
        holding = await self.hub.companies.holding()
        call = await self.router.run(
            {
                "company_code": holding.code,
                "actor_ref": f"{holding.code}-SYS",
                "task_class": "stt_punctuation",
                "priority": 1,
                "model": self.hub.settings.stt_punctuation_model,
                "effort": "low",
                "system": M.PUNCTUATION_SYSTEM,
                "prompt": text,
                "timeout_s": 120,
                "max_output_tokens": min(8000, 2 * len(text) + 200),
                "meta": {"purpose": "stt_punctuation"},
            },
            120,
        )
        candidate = persian.normalise((call.text or "").strip())
        if not call.ok or not candidate:
            return text, "failed", None
        ok, ratio = M.accept_punctuation(text, candidate)
        if not ok:
            log.info("punctuation dropped", extra={"edit_ratio": ratio})
            return text, "rejected", ratio
        return candidate, "accepted", ratio

    async def _record(
        self, f: dict[str, Any], status: str, sp: dict[str, Any] | None, error: str | None
    ) -> None:
        stt = {}
        if sp is not None:
            stt = {k: sp[k] for k in ("engine", "duration_s", "confidence", "language")}
        async with self._tx() as tx:
            _, company = await self._owner_now(tx, f["id"])
            await tx.exec(
                """UPDATE files.processing SET status = :st, transcript = :t, transcript_normalised = :n,
                       punctuation = :p, punctuation_edit_ratio = :r, stt = stt || CAST(:stt AS jsonb),
                       error = :e, updated_at = now()
                   WHERE file_id = :id""",
                id=f["id"],
                st=status,
                t=sp["text"] if sp else None,
                n=sp["normalised"] if sp else None,
                p=sp["punctuation"] if sp else None,
                r=sp["edit_ratio"] if sp else None,
                stt=json.dumps(stt, ensure_ascii=False),
                e=(error or None) and error[:300],
            )
            await events.emit(
                tx,
                company,
                "file.ready" if status == "ready" else "file.failed",
                str(f["id"]),
                {"kind": f["kind"], "status": status},
            )
            if sp is not None and (sp.get("text") or "").strip():
                # ⟨1.9⟩ contract §27.3: a transcript was stored on the file
                await events.emit(
                    tx,
                    company,
                    "file.transcribed",
                    str(f["id"]),
                    {
                        "kind": f["kind"],
                        "chars": len(sp["text"]),
                        "duration_s": sp.get("duration_s"),
                        "engine": (sp.get("engine") or {}).get("model"),
                    },
                )

    # --------------------------------------------------------- activities --
    @activity.defn(name="file_process")
    async def file_process(self, file_id: str) -> dict[str, Any]:
        f = await self._file(file_id)
        if f["status"] != "processing":
            return {"file": file_id, "skipped": f["status"]}
        attempt = await self._start(f)
        if attempt > MAX_ATTEMPTS:
            await self._record(f, "failed", None, f"gave up after {MAX_ATTEMPTS} attempts")
            return {"file": file_id, "error": "attempts"}
        src = self.hub.storage.local_path(f["storage_key"])
        if f["kind"] == "document":
            # A PDF whose text the api never finished (it restarted between the
            # two transactions, prompt 07.1 §1.2): the same child, here.
            async with self._beating():
                status = await F.extract_text(self._tx, f["id"], src, count=False)
            return {"file": file_id, "text": status}
        root = Path(self.hub.settings.files_root)
        out: dict[str, Any] = {"file": file_id, "frames": 0}
        async with self._beating():
            try:
                sp: dict[str, Any] | None = None
                if f["kind"] == "video":
                    duration = float(f["duration_s"] or 0)
                    if not await self._has_variant(f, "poster"):
                        await self._store_variant(f, "poster", await M.poster(src, duration))
                    if not await self._has_variant(f, "frame"):
                        frames = await M.key_frames(src, duration)
                        for at, data in frames:
                            await self._store_variant(f, "frame", data, at)
                        out["frames"] = len(frames)
                with M.temp_file(root, ".wav") as wav:
                    if await M.sound_track(src, wav, f["kind"]):
                        try:
                            sp = await self.speech(wav, punctuate=not await self._synthetic(f))
                        except M.SttUnavailable as exc:
                            out["transcript"] = f"unavailable ({exc})"
                        except M.SttBusy as exc:
                            if attempt < MAX_ATTEMPTS:  # not "off": this file is tried again
                                raise ApplicationError(str(exc), type=STT_BUSY) from exc
                            out["transcript"] = f"busy ({exc})"
                await self._record(f, "ready", sp, None)
            except (ValueError, OSError, TimeoutError) as exc:
                log.warning("media processing failed", extra={"file": file_id})
                await self._record(f, "failed", None, str(exc))
                out["error"] = str(exc)[:200]
        return out

    @activity.defn(name="transcribe_file")
    async def transcribe_file(self, file_id: str) -> dict[str, Any]:
        f = await self._file(file_id)
        await self._start(f)
        src = self.hub.storage.local_path(f["storage_key"])
        root = Path(self.hub.settings.files_root)
        async with self._beating():
            with M.temp_file(root, ".wav") as wav:
                try:
                    has_sound = await M.sound_track(src, wav, "audio")
                except ValueError as exc:  # longer than the limit, found while decoding
                    await self._record(f, "failed", None, str(exc))
                    raise ApplicationError(str(exc), type="TooLong", non_retryable=True) from exc
                if not has_sound:
                    sp: dict[str, Any] = {
                        "text": "", "normalised": "", "punctuation": "off", "edit_ratio": None,
                        "language": "fa", "duration_s": float(f["duration_s"] or 0),
                        "confidence": 0.0, "segments": [], "engine": {},
                    }  # fmt: skip
                else:
                    try:
                        sp = await self.speech(wav, BUSY_WAIT_TRANSCRIBE_S)
                    except M.SttUnavailable as exc:
                        await self._record(f, "failed", None, "speech recognition is off")
                        raise ApplicationError(
                            str(exc), type=STT_UNAVAILABLE, non_retryable=True
                        ) from exc
                    except M.SttBusy as exc:
                        await self._record(f, "failed", None, "speech recognition is busy")
                        raise ApplicationError(str(exc), type=STT_BUSY, non_retryable=True) from exc
                    except ValueError as exc:
                        await self._record(f, "failed", None, str(exc))
                        raise ApplicationError(
                            str(exc), type="TooLong", non_retryable=True
                        ) from exc
        await self._record(f, "ready", sp, None)
        return sp
