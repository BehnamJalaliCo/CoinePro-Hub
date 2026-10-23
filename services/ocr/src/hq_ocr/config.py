"""Settings from the environment (non-secret; ocr has no secret at all)."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

LOCK_FILE = Path(__file__).resolve().parents[2] / "model.lock.json"
MB = 1024 * 1024


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    listen_port: int = field(default_factory=lambda: _int("PORT", 8088))
    # A set of traineddata named in model.lock.json ("" = the lock's default).
    model: str = field(default_factory=lambda: os.environ.get("OCR_MODEL", ""))
    models_dir: str = field(default_factory=lambda: os.environ.get("OCR_MODELS_DIR", "/models"))
    lock_file: str = field(default_factory=lambda: os.environ.get("OCR_LOCK_FILE", str(LOCK_FILE)))
    langs: str = field(default_factory=lambda: os.environ.get("OCR_LANGS", "fas+eng"))
    # A raw body over this is 413 before a byte of it is read.
    max_bytes: int = field(default_factory=lambda: _int("OCR_MAX_BYTES", 30 * MB))
    # One job's wall clock (every page of a PDF together): 504 beyond it.
    job_timeout_s: int = field(default_factory=lambda: _int("OCR_JOB_TIMEOUT_S", 120))
    default_pages: int = field(default_factory=lambda: _int("OCR_DEFAULT_PAGES", 50))
    max_pages: int = field(default_factory=lambda: _int("OCR_MAX_PAGES", 200))
    # An image above this many pixels is refused before Tesseract decodes it.
    max_pixels: int = field(default_factory=lambda: _int("OCR_MAX_PIXELS", 40_000_000))
    # A PDF page is rasterised with its long side at this many pixels (A4 at 300 dpi).
    page_long_side_px: int = field(default_factory=lambda: _int("OCR_PAGE_PX", 3508))
    threads: int = field(default_factory=lambda: _int("OCR_THREADS", 1))
    tmp_dir: str = field(default_factory=tempfile.gettempdir)
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "info"))
