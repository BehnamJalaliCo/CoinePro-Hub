"""The archive's files (prompt 14 §3, contract §23.1, §23.4, §23.12).

Intake (`POST /archive/intake`, and every record made from file ids):
uploads arrive through §17.1 (`POST /files`); intake reads each one once,
outside any transaction: its text (a PDF's own text layer in a child
process; an image's or a scan's OCR through the worker, when the `ocr`
profile is on), then the secret scan (archive.scan) over its name and text.
A secret refuses it: `422 secret_in_document`, and an owner upload still
waiting in the holding is destroyed at once (bytes, variants, extracted
text); nothing of it is logged. What passes is an `archive.intake` row:
hashes, text, pages, the rule-based suggestion.

Ingest: the bytes are copied into the archive's own object in the same file
store (the hq-files volume: in the hourly backup and on the Drive). A level
with `encrypt` (seed: `secret`) is encrypted before it is written: AES-256-GCM
with a fresh data key from OpenBao transit `archive-secret`
(datakey/plaintext); only the wrapped key is kept, the transit key never
leaves OpenBao. Once the record holds its copy, an owner upload still
waiting in the holding is taken over (its bytes and variants removed), so a
secret's plaintext stays nowhere and a disposal destroys every copy.

Reading: the stored bytes are checked against stored_sha256, decrypted when
encrypted and checked against sha256; a level with `watermark` is served
watermarked (viewer, time, ref) from a child process, the original
untouched.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from hq_api import media
from hq_api.archive import ocr as OCR
from hq_api.archive import scan
from hq_api.archive.common import J
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_common import persian, untrusted

log = logging.getLogger("hq_api.archive")

TRANSIT_KEY = "archive-secret"
NONCE = 12
TEXT_MAX = 400_000
LOW_CONFIDENCE = 0.6  # a page below this is marked for the archivist
DOC_LIMITS = untrusted.Limits(write_mb=0, network=False)
MARK_LIMITS = untrusted.Limits(memory_mb=320, write_mb=120, network=False)
OVERRIDE_VAULT: Any = None  # tests: a stand-in for OpenBao transit


# ------------------------------------------------------------ the vault --
class Vault:
    """Envelope encryption with OpenBao transit (the key never leaves it)."""

    def __init__(self, bao: Any) -> None:
        self.bao = bao

    async def new_key(self) -> tuple[bytes, str]:
        dek, wrapped = await self.bao.transit_datakey(TRANSIT_KEY)
        return bytes(dek), str(wrapped)

    async def unwrap(self, wrapped: str) -> bytes:
        return bytes(await self.bao.transit_decrypt(TRANSIT_KEY, wrapped))


def vault(hub: Any) -> Any:
    if OVERRIDE_VAULT is not None:
        return OVERRIDE_VAULT
    bao = getattr(hub, "bao", None)
    if bao is None or not hasattr(bao, "transit_datakey"):
        return None
    return Vault(bao)


def encrypt(dek: bytes, data: bytes, aad: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(NONCE)
    return nonce + AESGCM(dek).encrypt(nonce, data, aad)


def decrypt(dek: bytes, blob: bytes, aad: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(dek).decrypt(blob[:NONCE], blob[NONCE:], aad)


# ---------------------------------------------------------------- intake --
UPLOAD_SQL = """
    SELECT f.id, f.company_id, f.name, f.mime, f.size, f.sha256, f.storage_key, f.kind, f.variant,
           f.created_by_kind, c.kind AS company_kind, COALESCE(p.status, 'ready') AS status,
           p.text AS processed_text,
           EXISTS (SELECT 1 FROM msg.messages m WHERE m.attachments @> ARRAY[f.id]) AS attached
    FROM files.files f JOIN core.companies c ON c.id = f.company_id
    LEFT JOIN files.processing p ON p.file_id = f.id
"""


def waiting_upload(f: dict[str, Any]) -> bool:
    """An owner upload still in the holding, attached nowhere: the archive may
    take it over (or destroy it when it holds a secret)."""
    return (
        f["created_by_kind"] == "owner" and f["company_kind"] == "holding" and not f["attached"]
    )


@dataclass
class Intake:
    file_id: UUID
    name: str
    mime: str
    size: int
    sha256: str
    storage_key: str
    pages: int | None
    text_state: str
    text: str | None
    ocr_confidence: float | None
    low_pages: list[int] = field(default_factory=list)
    suggestion: dict[str, Any] | None = None
    waiting: bool = False
    ocr_wanted: bool = False


async def _text_of(hub: Any, f: dict[str, Any], path: Path) -> dict[str, Any]:
    """(text, text_state, pages, confidence, low pages, ocr_wanted) of one upload."""
    out: dict[str, Any] = {"text": None, "text_state": "none", "pages": None,
                           "confidence": None, "low": [], "ocr_wanted": False}  # fmt: skip
    if f["mime"] == "application/pdf":
        got = await untrusted.run(
            "hq_api.archive.jobs:doc_text_job", kwargs={"path": str(path)}, limits=DOC_LIMITS
        )
        if got.ok and isinstance(got.value, dict):
            out["pages"] = got.value.get("pages")
            if got.value.get("text"):
                out["text"] = persian.normalise(got.value["text"])[:TEXT_MAX]
                out["text_state"] = "text_layer"
                return out
        elif not got.ok:
            out["text_state"] = "failed"
            return out
    elif f["kind"] != "image":
        return out  # audio, video: their transcript is §17.2's
    else:
        out["pages"] = 1
    # A scanned PDF or an image: OCR on the hub, when the profile is on.
    res = await OCR.through_worker(hub, f["storage_key"], f["mime"])
    if res is None:
        out["ocr_wanted"] = True  # the profile is off or busy: the queue takes it later
        return out
    if res.get("state") == "ok":
        out.update(OCR.as_text(res, LOW_CONFIDENCE))
        out["text_state"] = "ocr"
    elif res.get("state") == "failed":
        out["text_state"] = "failed"
    else:
        out["ocr_wanted"] = True
    return out


async def destroy_upload(hub: Any, txf: Any, f: dict[str, Any]) -> None:
    """An owner upload the archive refused or took over: its bytes, its
    variants' bytes and its extracted text are gone (the rows stay, as every
    files.files row does; GET /files answers 404 for the content)."""
    async with txf() as tx:
        rows = await tx.all(
            "SELECT storage_key FROM files.files WHERE id = :f OR parent_id = :f", f=f["id"]
        )
        await tx.exec(
            "UPDATE files.processing SET text = NULL, transcript = NULL, updated_at = now() WHERE file_id = :f",
            f=f["id"],
        )
    for r in rows:
        await hub.storage.destroy(r["storage_key"])


async def intake(
    hub: Any, txf: Any, who: Principal, file_ids: list[UUID], *, holding_ok: bool
) -> list[Intake]:
    """Each file once (an earlier intake is reused): text, secret scan, hashes."""
    from hq_api.archive import suggest

    out: list[Intake] = []
    for fid in dict.fromkeys(file_ids):
        async with txf() as tx:
            f = await tx.first(UPLOAD_SQL + " WHERE f.id = :id", id=fid)
            done = await tx.first("SELECT * FROM archive.intake WHERE file_id = :id", id=fid)
        if f is None or f["variant"] != "original":
            raise ApiError(422, "validation_failed", fields={"file_ids": f"unknown file {fid}"})
        if f["status"] != "ready":
            raise ApiError(409, "not_ready", f"file {fid} is still being processed")
        waiting = waiting_upload(f)
        if waiting and not holding_ok:
            raise ApiError(422, "validation_failed", fields={"file_ids": f"not yours to file: {fid}"})
        if done is not None:
            out.append(Intake(
                file_id=fid, name=done["name"], mime=done["mime"], size=int(done["size_bytes"]),
                sha256=done["sha256"], storage_key=f["storage_key"], pages=done["pages"],
                text_state=done["text_state"], text=done["text"],
                ocr_confidence=float(done["ocr_confidence"]) if done["ocr_confidence"] is not None else None,
                low_pages=list(done["low_conf_pages"] or []), suggestion=J(done["suggestion"]),
                waiting=waiting, ocr_wanted=done["text_state"] == "none" and f["kind"] in ("image", "document"),
            ))  # fmt: skip
            continue
        path = hub.storage.local_path(f["storage_key"])
        if not await asyncio.to_thread(path.exists):
            raise ApiError(409, "not_ready", f"file {fid} has no content any more")
        t = await _text_of(hub, f, path)
        found = scan.kinds(f["name"]) or scan.kinds(t["text"])
        if found:
            # Red line 1: nothing of it stays and nothing of it is logged.
            if waiting:
                await destroy_upload(hub, txf, f)
            log.warning("archive intake refused a file", extra={"kinds": found})
            raise ApiError(
                422,
                "secret_in_document",
                "a secret pattern was found; the file is not stored",
                fields={"file_ids": str(fid), "kinds": ",".join(found)},
            )
        async with txf() as tx:
            sug = await suggest.rules(tx, t["text"] or "", f["name"])
            await tx.exec(
                """INSERT INTO archive.intake (company_id, file_id, name, mime, size_bytes, sha256, pages,
                       text_state, ocr_confidence, low_conf_pages, text, suggestion, by_kind, by_code)
                   VALUES (:co, :f, :n, :m, :s, :h, :p, :ts, :oc, :lp, :t, CAST(:sg AS jsonb), :bk, :bc)
                   ON CONFLICT (file_id) DO NOTHING""",
                co=f["company_id"], f=fid, n=f["name"][:255], m=f["mime"], s=int(f["size"]), h=f["sha256"],
                p=t["pages"], ts=t["text_state"], oc=t["confidence"], lp=t["low"], t=t["text"],
                sg=_dumps(sug), bk=who.kind if who.kind in ("owner", "agent", "service") else "system",
                bc=who.code[:64],
            )  # fmt: skip
        out.append(Intake(
            file_id=fid, name=f["name"], mime=f["mime"], size=int(f["size"]), sha256=f["sha256"],
            storage_key=f["storage_key"], pages=t["pages"], text_state=t["text_state"], text=t["text"],
            ocr_confidence=t["confidence"], low_pages=t["low"], suggestion=sug, waiting=waiting,
            ocr_wanted=t["ocr_wanted"],
        ))  # fmt: skip
    return out


def _dumps(v: Any) -> str | None:
    import json

    return None if v is None else json.dumps(v, ensure_ascii=False, default=str)


# ---------------------------------------------------------------- ingest --
@dataclass
class Stored:
    intake: Intake
    storage_key: str
    stored_sha256: str
    encrypted: bool
    wrapped_dek: str | None


async def ingest(hub: Any, items: list[Intake], *, encrypt_it: bool) -> list[Stored]:
    """The archive's own copy of each file (encrypted for an `encrypt` level),
    written before the record's transaction; `discard` removes them again if
    that transaction fails."""
    v = vault(hub) if encrypt_it else None
    if encrypt_it and v is None:
        raise ApiError(
            503,
            "channel_not_configured",
            "the archive-secret key (OpenBao transit) is not available on this hub",
        )
    stored: list[Stored] = []
    try:
        for it in items:
            data = await hub.storage.get(it.storage_key)
            if hashlib.sha256(data).hexdigest() != it.sha256:
                raise ApiError(409, "seal_mismatch", f"file {it.file_id} changed since its intake")
            wrapped = None
            if encrypt_it:
                dek, wrapped = await v.new_key()
                data = encrypt(dek, data, str(it.file_id).encode())
                del dek
            key, sha = await hub.storage.put(data)
            stored.append(Stored(it, key, sha, encrypt_it, wrapped))
    except BaseException:
        await discard(hub, stored)
        raise
    return stored


async def discard(hub: Any, stored: list[Stored]) -> None:
    for s in stored:
        await hub.storage.destroy(s.storage_key)


def manifest(files: list[dict[str, Any]]) -> str:
    """SHA-256 of the sorted "<sha256>  <name>" lines (contract §23.1)."""
    lines = sorted(f"{f['sha256']}  {f['name']}" for f in files)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


# --------------------------------------------------------------- reading --
async def read(hub: Any, f: dict[str, Any]) -> bytes:
    """The file's plaintext, checked against both hashes."""
    if f["destroyed_at"] is not None or not f["storage_key"]:
        raise ApiError(404, "not_found", "the file was destroyed")
    try:
        blob = await hub.storage.get(f["storage_key"])
    except OSError as exc:
        raise ApiError(404, "not_found", "file content missing") from exc
    if hashlib.sha256(blob).hexdigest() != f["stored_sha256"]:
        raise ApiError(409, "seal_mismatch", "the stored file does not match its hash (fixity)")
    if not f["encrypted"]:
        return blob
    v = vault(hub)
    if v is None:
        raise ApiError(503, "channel_not_configured", "the archive-secret key is not available")
    dek = await v.unwrap(f["wrapped_dek"])
    data = decrypt(dek, blob, str(f["file_id"]).encode())
    del dek
    if hashlib.sha256(data).hexdigest() != f["sha256"]:
        raise ApiError(409, "seal_mismatch", "the decrypted file does not match its hash")
    return data


# ------------------------------------------------------------- watermark --
async def watermarked(hub: Any, data: bytes, mime: str, text: str) -> tuple[bytes, str]:
    if mime != "application/pdf" and not mime.startswith("image/"):
        return data, mime
    src, dst = hub.storage.scratch(), hub.storage.scratch()
    try:
        await asyncio.to_thread(src.write_bytes, data)
        got = await untrusted.run(
            "hq_api.archive.jobs:watermark_job",
            kwargs={"src": str(src), "out": str(dst), "mime": mime, "text": text,
                    "font_dir": hub.settings.fonts_dir},  # fmt: skip
            limits=MARK_LIMITS,
        )
        if not got.ok or not isinstance(got.value, dict):
            raise ApiError(422, "validation_failed", "the file could not be watermarked")
        return await asyncio.to_thread(dst.read_bytes), str(got.value["mime"])
    finally:
        src.unlink(missing_ok=True)
        dst.unlink(missing_ok=True)


async def destroy_files(hub: Any, keys: list[str]) -> int:
    n = 0
    for k in keys:
        if k and await hub.storage.destroy(k):
            n += 1
    return n


async def file_row(tx: Tx, record_id: UUID, file_id: UUID, version: int | None) -> dict[str, Any]:
    row = await tx.first(
        """SELECT * FROM archive.record_files WHERE record_id = :r AND file_id = :f
             AND (CAST(:v AS int) IS NULL OR version_n = :v)
           ORDER BY version_n DESC LIMIT 1""",
        r=record_id,
        f=file_id,
        v=version,
    )
    if row is None:
        raise ApiError(404, "not_found", "no such file in this record")
    return row
