"""`python -m hq_ocr.fetch [SET...]`: download the pinned traineddata once into
the models volume (compose job `ocr-fetch`, the only part of ocr with
internet access, on hq-fetch). Each file comes from its pinned repository
revision, is checked against its pinned size and sha256, and only then moved
into place; a file already there and right is skipped. Exit 1 on a mismatch.
Standard library only (the ocr image has no pip packages).
"""

from __future__ import annotations

import hashlib
import logging
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from hq_common import logs
from hq_ocr import lock
from hq_ocr.config import Settings

log = logging.getLogger("hq_ocr.fetch")
ATTEMPTS = 3
Opener = Callable[[str], BinaryIO]


def _open(url: str) -> BinaryIO:
    if not url.startswith(lock.RAW_HOST + "/"):  # the pinned host only, https only
        raise lock.ModelInvalid(f"not a pinned url: {url[:80]}")
    resp: BinaryIO = urllib.request.urlopen(url, timeout=120)  # noqa: S310 - https, checked above
    return resp


def fetch_file(
    pinned: lock.PinnedSet, f: lock.PinnedFile, directory: Path, opener: Opener = _open
) -> bool:
    """True when the file had to be downloaded, False when it was already right."""
    target = directory / f.name
    if target.is_file() and target.stat().st_size == f.size and lock.sha256_of(target) == f.sha256:
        return False
    part = target.with_name(target.name + ".part")
    h = hashlib.sha256()
    size = 0
    with opener(pinned.url(f)) as resp, part.open("wb") as fh:
        while chunk := resp.read(lock.CHUNK):
            size += len(chunk)
            if size > f.size:
                break
            h.update(chunk)
            fh.write(chunk)
    if size != f.size or h.hexdigest() != f.sha256:
        part.unlink(missing_ok=True)
        raise lock.ModelInvalid(f"{pinned.name}: {f.name} downloaded bytes are not the pinned ones")
    part.replace(target)
    return True


def fetch(pinned: lock.PinnedSet, root: Path, opener: Opener = _open) -> int:
    directory = root / pinned.name
    directory.mkdir(parents=True, exist_ok=True)
    fetched = 0
    for f in pinned.files:
        for attempt in range(1, ATTEMPTS + 1):
            try:
                if fetch_file(pinned, f, directory, opener):
                    fetched += 1
                    log.info("fetched", extra={"set": pinned.name, "file": f.name, "bytes": f.size})
                break
            except (urllib.error.URLError, OSError):
                if attempt == ATTEMPTS:
                    raise
                log.warning("retrying", extra={"set": pinned.name, "file": f.name})
                time.sleep(2 * attempt)
    lock.verify(pinned, directory)
    return fetched


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    s = Settings()
    logs.setup("ocr-fetch", s.log_level)
    names = (argv if argv is not None else sys.argv[1:]) or [s.model]
    try:
        for name in names:
            pinned = lock.load(s.lock_file, name)
            n = fetch(pinned, Path(s.models_dir))
            print(f"ocr-fetch: {pinned.name} ok ({n} file(s) downloaded, {pinned.revision[:12]})")
    except (lock.ModelInvalid, urllib.error.URLError, OSError) as exc:
        print(f"ocr-fetch: FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
