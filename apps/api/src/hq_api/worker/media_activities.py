"""Temporal activities for owner media (prompt 6 §2-§3).

file_process     a video or audio upload: poster, key frames, sound track,
                 transcript (status processing -> ready | failed, then
                 file.ready / file.failed on the stream)
transcribe_file  POST /transcribe: the same transcription for one audio
                 file, awaited by the api
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

    async def _store_variant(
        self, f: dict[str, Any], variant: str, data: bytes, at: float | None = None
    ) -> UUID:
        key, sha = await self.hub.storage.put(data)
        async with self._tx() as tx:
            return await F.insert(
                tx,
                company_id=f["company_id"],
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
    async def speech(self, wav: Path) -> dict[str, Any]:
        """Whisper (stt), the normaliser (there and again here), then the
        punctuation pass; both texts are kept for the quality log."""
        s = self.hub.settings
        res = await M.transcribe(s.stt_url, wav, transport=self.stt_transport)
        normalised = persian.normalise(res.get("text") or "")
        final, punctuation, ratio = normalised, "off", None
        if normalised and s.stt_punctuation and self.hub.secrets.llm_router_token:
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
            await tx.exec(
                """UPDATE files.processing SET status = :st, transcript = :t, transcript_normalised = :n,
                       punctuation = :p, punctuation_edit_ratio = :r, stt = stt || CAST(:stt AS jsonb),
                       error = :e, attempts = attempts + 1, updated_at = now()
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
                f["company"],
                "file.ready" if status == "ready" else "file.failed",
                str(f["id"]),
                {"kind": f["kind"], "status": status},
            )

    # --------------------------------------------------------- activities --
    @activity.defn(name="file_process")
    async def file_process(self, file_id: str) -> dict[str, Any]:
        f = await self._file(file_id)
        if f["status"] != "processing":
            return {"file": file_id, "skipped": f["status"]}
        src = self.hub.storage.local_path(f["storage_key"])
        root = Path(self.hub.settings.files_root)
        out: dict[str, Any] = {"file": file_id, "frames": 0}
        async with self._beating():
            try:
                sp: dict[str, Any] | None = None
                if f["kind"] == "video":
                    await self._store_variant(f, "poster", await M.poster(src, float(f["duration_s"] or 0)))
                    frames = await M.key_frames(src, float(f["duration_s"] or 0))
                    for at, data in frames:
                        await self._store_variant(f, "frame", data, at)
                    out["frames"] = len(frames)
                with M.temp_file(root, ".wav") as wav:
                    if await M.sound_track(src, wav):
                        try:
                            sp = await self.speech(wav)
                        except M.SttUnavailable as exc:
                            out["transcript"] = f"unavailable ({exc})"
                await self._record(f, "ready", sp, None)
            except (ValueError, OSError, TimeoutError) as exc:
                log.warning("media processing failed", extra={"file": file_id})
                await self._record(f, "failed", None, str(exc))
                out["error"] = str(exc)[:200]
        return out

    @activity.defn(name="transcribe_file")
    async def transcribe_file(self, file_id: str) -> dict[str, Any]:
        f = await self._file(file_id)
        src = self.hub.storage.local_path(f["storage_key"])
        root = Path(self.hub.settings.files_root)
        async with self._beating():
            with M.temp_file(root, ".wav") as wav:
                if not await M.sound_track(src, wav):
                    sp: dict[str, Any] = {
                        "text": "", "normalised": "", "punctuation": "off", "edit_ratio": None,
                        "language": "fa", "duration_s": float(f["duration_s"] or 0),
                        "confidence": 0.0, "segments": [], "engine": {},
                    }  # fmt: skip
                else:
                    try:
                        sp = await self.speech(wav)
                    except M.SttUnavailable as exc:
                        await self._record(f, "failed", None, "speech recognition is off")
                        raise ApplicationError(
                            str(exc), type=STT_UNAVAILABLE, non_retryable=True
                        ) from exc
                    except ValueError as exc:
                        await self._record(f, "failed", None, str(exc))
                        raise ApplicationError(
                            str(exc), type="TooLong", non_retryable=True
                        ) from exc
        await self._record(f, "ready", sp, None)
        return sp
