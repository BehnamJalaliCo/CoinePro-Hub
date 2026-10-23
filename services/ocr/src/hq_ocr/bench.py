"""`python -m hq_ocr.bench FILE [MIME]`: one OCR job on FILE, in the ocr image
with the pinned traineddata mounted, and its numbers as one JSON line: pages,
seconds, seconds per page, mean confidence, words, and the container's
memory peak (cgroup v2 memory.peak, MiB). Run each file in a fresh container
(`make ocr-bench`), so the peak is that job's. Prints no text of the page.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hq_ocr import engine, lock
from hq_ocr.config import Settings

MIMES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp",
         ".tif": "image/tiff", ".pdf": "application/pdf"}  # fmt: skip


def peak_mib() -> float | None:
    for name in ("memory.peak", "memory.max_usage_in_bytes"):
        p = Path("/sys/fs/cgroup") / name
        if p.is_file():
            try:
                return round(int(p.read_text().strip()) / 1048576, 1)
            except ValueError:
                return None
    return None


def main(argv: list[str]) -> int:  # pragma: no cover - run in the image
    s = Settings()
    path = Path(argv[0])
    mime = argv[1] if len(argv) > 1 else MIMES[path.suffix.lower()]
    pinned = lock.load(s.lock_file, s.model)
    tessdata = str(Path(s.models_dir) / pinned.name)
    lock.verify(pinned, Path(tessdata))
    data = path.read_bytes()
    kind = engine.detect(mime, data[: engine.HEAD_BYTES])
    got = engine.run(
        engine.Job(data=data, kind=kind, max_pages=s.default_pages, langs=s.langs,
                   tessdata=tessdata, timeout_s=s.job_timeout_s,
                   page_long_side_px=s.page_long_side_px, threads=s.threads, tmp_dir=s.tmp_dir)
    )  # fmt: skip
    pages = len(got.pages)
    print(
        json.dumps(
            {
                "file": path.name,
                "set": pinned.name,
                "pages": pages,
                "seconds": got.seconds,
                "s_per_page": round(got.seconds / pages, 2) if pages else None,
                "confidence": got.confidence,
                "words": sum(p["words"] for p in got.pages),
                "peak_mib": peak_mib(),
            }
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
