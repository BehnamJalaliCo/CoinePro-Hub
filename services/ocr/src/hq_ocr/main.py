"""The internal API (network hq-ocr: the worker only; no port published).

    POST /v1/ocr?max_pages=N   raw body (<= 30 MB), Content-Type image/png,
                               image/jpeg, image/webp, image/tiff or
                               application/pdf (its first max_pages pages,
                               default 50) -> 200 {pages: [{n, text,
                               confidence, words}], confidence, seconds,
                               engine: {name, version, langs, traineddata}}
    GET  /healthz              {ok, version, langs}

One job at a time: a request that arrives while one runs answers 429 busy
(the worker's queue runs at concurrency 1 and retries later). Errors are
JSON {"error": code}: 400 bad_request, 404 not_found, 413 too_large,
415 unsupported_type, 422 unreadable, 429 busy, 503 model_invalid,
504 timeout. Text is returned raw (the worker applies the Persian
normaliser); no text, file name or byte of a document is ever logged.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from hq_ocr import engine, lock
from hq_ocr.config import Settings

log = logging.getLogger("hq_ocr")


class Service:
    """What the handler needs: settings, the verified traineddata, one slot."""

    def __init__(self, settings: Settings, *, verify: bool = True) -> None:
        self.settings = settings
        self.pinned = lock.load(settings.lock_file, settings.model)
        self.tessdata = str(Path(settings.models_dir) / self.pinned.name)
        self.model_ok = True
        if verify:
            lock.verify(self.pinned, Path(self.tessdata))  # raises ModelInvalid
        self.slot = threading.Lock()
        self.version = engine.version()
        self.langs = sorted(settings.langs.split("+"))

    def engine_info(self) -> dict[str, Any]:
        sums = self.pinned.sha256s()
        return {
            "name": "tesseract",
            "version": self.version,
            "langs": self.langs,
            "traineddata": {lang: sums.get(lang) for lang in self.langs},
            "set": self.pinned.name,
            "revision": self.pinned.revision,
        }

    def max_pages(self, query: str) -> int:
        raw = parse_qs(query).get("max_pages", [""])[-1]
        if raw == "":
            return min(self.settings.default_pages, self.settings.max_pages)
        if not raw.isdigit() or not 1 <= int(raw) <= self.settings.max_pages:
            raise engine.OcrError(400, "bad_request")
        return int(raw)

    def ocr(self, content_type: str | None, data: bytes, max_pages: int) -> dict[str, Any]:
        kind = engine.detect(content_type, data[: engine.HEAD_BYTES])
        if kind != "pdf":
            pixels = engine.image_pixels(kind, data[: engine.HEAD_BYTES])
            if pixels is not None and pixels > self.settings.max_pixels:
                raise engine.OcrError(413, "too_large")
        got = engine.run(
            engine.Job(
                data=data,
                kind=kind,
                max_pages=max_pages,
                langs=self.settings.langs,
                tessdata=self.tessdata,
                timeout_s=self.settings.job_timeout_s,
                page_long_side_px=self.settings.page_long_side_px,
                threads=self.settings.threads,
                tmp_dir=self.settings.tmp_dir,
            )
        )
        log.info(
            "ocr",
            extra={"kind": kind, "pages": len(got.pages), "seconds": got.seconds,
                   "bytes": len(data), "confidence": got.confidence},
        )  # fmt: skip
        return {
            "pages": got.pages,
            "confidence": got.confidence,
            "seconds": got.seconds,
            "engine": self.engine_info(),
        }


def make_handler(service: Service) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "hq-ocr"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return  # no access log: the path and status are all it would say

        def _send(self, status: int, body: dict[str, Any]) -> None:
            raw = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            if status in (413, 429):
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path in ("/healthz", "/health"):
                ok = service.model_ok
                self._send(
                    200 if ok else 503,
                    {"ok": ok, "version": service.version, "langs": service.langs},
                )
                return
            self._send(404, {"error": "not_found"})

        def do_POST(self) -> None:
            url = urlsplit(self.path)
            if url.path != "/v1/ocr":
                self._send(404, {"error": "not_found"})
                return
            length = self.headers.get("Content-Length")
            if self.headers.get("Transfer-Encoding") or length is None or not length.isdigit():
                self._send(400, {"error": "bad_request"})
                self.close_connection = True
                return
            size = int(length)
            if size > service.settings.max_bytes:
                self._send(413, {"error": "too_large"})  # nothing of it is read
                return
            if size == 0:
                self._send(400, {"error": "bad_request"})
                return
            if not service.slot.acquire(blocking=False):
                self._send(429, {"error": "busy"})
                return
            try:
                data = self.rfile.read(size)
                if len(data) != size:
                    self._send(400, {"error": "bad_request"})
                    return
                self._send(
                    200,
                    service.ocr(
                        self.headers.get("Content-Type"), data, service.max_pages(url.query)
                    ),
                )
            except engine.OcrError as exc:
                self._send(exc.status, {"error": exc.code})
            except Exception:  # never a stack trace or a document out
                log.exception("ocr failed")
                self._send(422, {"error": "unreadable"})
            finally:
                service.slot.release()

    return Handler


def serve(service: Service, host: str = "0.0.0.0", port: int | None = None) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port if port is not None else service.settings.listen_port),
                                 make_handler(service))  # fmt: skip
    server.daemon_threads = True
    return server
