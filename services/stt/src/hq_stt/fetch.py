"""`python -m hq_stt.fetch [MODEL...]`: download the pinned model files once
into the models volume (compose job `stt-fetch`, the only part of stt with
internet access). Each file is fetched from its pinned repository revision,
checked against its pinned size and sha256, and only then moved into place;
files already present and correct are skipped. Exit code 1 on any mismatch.
"""

from __future__ import annotations

import hashlib
import logging
import sys
import time
from pathlib import Path

import httpx

from hq_common import logs
from hq_stt import lock
from hq_stt.config import Settings

log = logging.getLogger("hq_stt.fetch")
ATTEMPTS = 3


def fetch_file(
    client: httpx.Client, model: lock.PinnedModel, f: lock.PinnedFile, directory: Path
) -> bool:
    """True when the file had to be downloaded, False when it was already right."""
    target = directory / f.name
    if target.is_file() and target.stat().st_size == f.size and lock.sha256_of(target) == f.sha256:
        return False
    part = target.with_name(target.name + ".part")
    h = hashlib.sha256()
    size = 0
    with client.stream("GET", model.url(f)) as resp:
        resp.raise_for_status()
        with part.open("wb") as fh:
            for chunk in resp.iter_bytes(lock.CHUNK):
                size += len(chunk)
                if size > f.size:
                    break
                h.update(chunk)
                fh.write(chunk)
    if size != f.size or h.hexdigest() != f.sha256:
        part.unlink(missing_ok=True)
        raise lock.ModelInvalid(f"{model.name}: {f.name} downloaded bytes are not the pinned ones")
    part.replace(target)
    return True


def fetch(model: lock.PinnedModel, root: Path, client: httpx.Client) -> int:
    directory = root / model.name
    directory.mkdir(parents=True, exist_ok=True)
    fetched = 0
    for f in model.files:
        for attempt in range(1, ATTEMPTS + 1):
            try:
                if fetch_file(client, model, f, directory):
                    fetched += 1
                    log.info(
                        "fetched", extra={"model": model.name, "file": f.name, "bytes": f.size}
                    )
                break
            except httpx.HTTPError:
                if attempt == ATTEMPTS:
                    raise
                log.warning("retrying", extra={"model": model.name, "file": f.name})
                time.sleep(2 * attempt)
    lock.verify(model, directory)
    return fetched


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    s = Settings()
    logs.setup("stt-fetch", s.log_level)
    names = (argv if argv is not None else sys.argv[1:]) or [s.model]
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60, read=300)) as client:
        try:
            for name in names:
                model = lock.load(s.lock_file, name)
                n = fetch(model, Path(s.models_dir), client)
                print(f"stt-fetch: {name} ok ({n} file(s) downloaded, {model.revision[:12]})")
        except (lock.ModelInvalid, httpx.HTTPError) as exc:
            print(f"stt-fetch: FAILED: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
