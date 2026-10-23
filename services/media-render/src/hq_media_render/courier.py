"""`courier claim` / `courier send <id>`: the render worker's only contact with
the hub, on hq-media (the api and OpenBao, nothing else). The renderer itself
has no network at all; the two meet in the job volume:

    /jobs/<id>/job.json       the job as the api gave it
    /jobs/<id>/files/<file>   its assets and voice, each checked by size and sha256
    /jobs/<id>/out/           what the renderer made, with manifest.json

claim  POST /internal/v1/media/render/claim: 204 = nothing (always while the
       holding or the job's company is locked): nothing is written and nothing
       printed; else the files are fetched and the job id is printed.
send   the outputs (streamed from disk), then `done` with the metrics and any
       violations, or `fail` with the error; then the job's folder is removed.

The api token comes from OpenBao (AppRole of service `media`, kv
media/config); it is held in the client's headers only, never printed,
logged or written.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from hq_media_render.spec import SpecError, parse

log = logging.getLogger("hq_media_render.courier")
CHUNK = 1024 * 1024
MAX_FILE = 300 * 1024 * 1024
BASE = "/internal/v1/media/render"


@dataclass(frozen=True)
class Settings:
    api_url: str = field(
        default_factory=lambda: os.environ.get("HQ_API_INTERNAL_URL", "http://api:8000")
    )
    openbao_addr: str = field(
        default_factory=lambda: os.environ.get("OPENBAO_ADDR", "http://openbao:8200")
    )
    approle_file: str = field(
        default_factory=lambda: os.environ.get(
            "OPENBAO_APPROLE_FILE", "/run/secrets/hq/approle.json"
        )
    )
    token_path: str = field(
        default_factory=lambda: os.environ.get("MEDIA_TOKEN_PATH", "media/config")
    )
    jobs: Path = field(default_factory=lambda: Path(os.environ.get("MEDIA_JOBS_DIR", "/jobs")))


class CourierError(Exception):
    pass


async def api_token(s: Settings) -> str:
    from hq_common.openbao import OpenBaoClient

    bao = OpenBaoClient(s.openbao_addr, s.approle_file)
    try:
        data: dict[str, Any] = await bao.read_kv(s.token_path)
    finally:
        await bao.aclose()
    token = data.get("api_token")
    if not token:
        raise CourierError("no api_token at the media path in OpenBao")
    return str(token)


def _job_dir(root: Path, job_id: str) -> Path:
    if Path(job_id).name != job_id or not job_id or job_id.startswith("."):
        raise CourierError("bad job id")
    return root / job_id


async def claim(client: httpx.AsyncClient, root: Path) -> str | None:
    """Claim one job and lay it out in the volume; its id, or None."""
    r = await client.post(f"{BASE}/claim")
    if r.status_code == 204:
        return None
    r.raise_for_status()
    data = r.json()
    try:
        job = parse(data)
    except SpecError as exc:
        jid = str(data.get("id") or "") if isinstance(data, dict) else ""
        if jid:
            await fail(client, jid, f"bad_job: {str(exc)[:200]}")
        raise CourierError("the api handed out a job out of shape") from exc
    d = _job_dir(root, job.id)
    shutil.rmtree(d, ignore_errors=True)
    (d / "files").mkdir(parents=True, mode=0o700)
    try:
        for f in job.files():
            await _fetch(client, job.id, f.id, f.sha256, f.size, d / "files" / f.id)
    except CourierError as exc:
        shutil.rmtree(d, ignore_errors=True)
        await fail(client, job.id, f"fetch_failed: {str(exc)[:200]}")
        return None
    (d / "job.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    log.info("claimed", extra={"job": job.id, "item": job.item, "files": len(job.files())})
    return job.id


async def _fetch(
    client: httpx.AsyncClient, job_id: str, file_id: str, sha: str, size: int | None, dest: Path
) -> None:
    h = hashlib.sha256()
    n = 0
    cap = size if size is not None else MAX_FILE
    async with client.stream("GET", f"{BASE}/{job_id}/files/{file_id}") as r:
        if r.status_code != 200:
            raise CourierError(f"file {file_id}: HTTP {r.status_code}")
        with dest.open("wb") as fh:
            async for chunk in r.aiter_bytes(CHUNK):
                n += len(chunk)
                if n > cap:
                    raise CourierError(f"file {file_id}: larger than listed")
                h.update(chunk)
                fh.write(chunk)
    if h.hexdigest() != sha or (size is not None and n != size):
        raise CourierError(f"file {file_id}: sha256 or size differs")


async def _chunks(path: Path) -> AsyncIterator[bytes]:
    """The file streamed from the volume (a reel never sits whole in memory)."""
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            yield chunk


async def fail(client: httpx.AsyncClient, job_id: str, error: str) -> None:
    r = await client.post(f"{BASE}/{job_id}/fail", json={"error": error[:300]})
    if r.status_code >= 400:
        log.warning("fail not accepted", extra={"job": job_id, "status": r.status_code})


async def send(client: httpx.AsyncClient, root: Path, job_id: str) -> dict[str, Any]:
    """Send what the renderer made (or that it failed), then clear the folder."""
    d = _job_dir(root, job_id)
    try:
        manifest_path = d / "out" / "manifest.json"
        if not manifest_path.is_file():
            await fail(client, job_id, "render_killed: no result (timeout or memory)")
            return {"job": job_id, "status": "failed", "error": "render_killed"}
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        if m.get("status") != "done":
            error = str(m.get("error") or "render_failed")
            await fail(client, job_id, error)
            return {"job": job_id, "status": "failed", "error": error.split(":")[0]}
        sent = 0
        for o in m.get("outputs") or []:
            path = d / "out" / Path(str(o["path"])).name
            params = {"name": o["name"], "kind": o["kind"]}
            for k in ("width", "height", "duration_s"):
                if o.get(k) is not None:
                    params[k] = str(o[k])
            r = await client.post(
                f"{BASE}/{job_id}/output",
                params=params,
                content=_chunks(path),
                headers={
                    "Content-Type": str(o["mime"]),
                    "Content-Length": str(path.stat().st_size),
                },
            )
            if r.status_code >= 400:
                await fail(
                    client, job_id, f"upload_refused: {o['name']} {o['kind']} HTTP {r.status_code}"
                )
                return {"job": job_id, "status": "failed", "error": "upload_refused"}
            sent += 1
        r = await client.post(
            f"{BASE}/{job_id}/done",
            json={"metrics": m.get("metrics") or {}, "violations": m.get("violations") or []},
        )
        r.raise_for_status()
        return {"job": job_id, "status": "done", "outputs": sent,
                "violations": len(m.get("violations") or [])}  # fmt: skip
    finally:
        shutil.rmtree(d, ignore_errors=True)
