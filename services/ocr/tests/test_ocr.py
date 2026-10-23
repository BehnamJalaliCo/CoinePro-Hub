"""ocr (prompt 14 §4, §11): the HTTP API and its refusals with a stand-in
engine, the TSV reader, the header checks, the pinned-traineddata fetch and
check; and, where Tesseract and the pinned traineddata are present (the ocr
image: `make ocr-test`), real OCR of the committed Persian scan: an image and
an image-only PDF give searchable text with a confidence in 0..1.

Written as unittest cases with plain asserts, so the services gate (pytest,
no Tesseract: the real cases skip) and the ocr image (python -m unittest,
standard library only) run the same file.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import Any

from hq_ocr import engine as E
from hq_ocr import fetch as F
from hq_ocr import lock as L
from hq_ocr import main as M
from hq_ocr.config import Settings

SAMPLES = Path(__file__).resolve().parent / "samples"
MODELS = Path(os.environ.get("OCR_MODELS_DIR", "/models"))
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def fold_words(text: str) -> list[str]:
    """Comparable words: the hub's Persian normaliser when it is importable
    (ي/ك folded, ZWNJ joins ignored), digits as Latin, punctuation dropped."""
    try:
        from hq_common import persian

        words = persian.words(text)
    except ImportError:  # pragma: no cover - hq-common is in both images
        t = text.replace("ي", "ی").replace("ك", "ک").replace("‌", "")
        words = [w for w in re.split(r"[^\w]+", t) if w]
    return [w.translate(_DIGITS) for w in words if w.translate(_DIGITS).strip()]


def raised(kind: type[Exception], fn: Any) -> Any:
    """The exception `fn()` raised (it must raise one of `kind`)."""
    try:
        fn()
    except kind as exc:
        return exc
    raise AssertionError(f"{kind.__name__} not raised")


def real_ready() -> bool:
    if not E.available():
        return False
    try:
        pinned = L.load(Settings().lock_file)
        L.verify(pinned, MODELS / pinned.name)
    except (L.ModelInvalid, OSError):
        return False
    return True


TSV = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    "1\t1\t0\t0\t0\t0\t0\t0\t10\t10\t-1\t\n"
    "5\t1\t1\t1\t1\t1\t0\t0\t1\t1\t90\tبسمه\n"
    "5\t1\t1\t1\t1\t2\t0\t0\t1\t1\t80\tتعالی\n"
    "5\t1\t1\t2\t1\t1\t0\t0\t1\t1\t70\t‎IP‏\n"
    "5\t1\t1\t2\t2\t1\t0\t0\t1\t1\t-1\t \n"
    "5\t1\t2\t1\t1\t1\t0\t0\t1\t1\t60\tend\n"
    "garbage line\n"
)


class TsvAndHeaders(unittest.TestCase):
    def test_tsv_is_read_in_reading_order_with_its_mean_confidence(self) -> None:
        text, conf, words = E.parse_tsv(TSV)
        assert text == "بسمه تعالی\n\nIP\n\nend"  # direction marks dropped
        assert words == 4
        assert conf == 0.75
        assert E.parse_tsv("level\n") == ("", None, 0)

    def test_the_type_is_the_bytes_and_the_header_together(self) -> None:
        assert E.detect("image/png", PNG_1x1) == "png"
        assert E.detect("application/pdf; x=1", b"%PDF-1.7\n") == "pdf"
        for ctype, head in (
            ("image/png", b"%PDF-1.7"),  # the header lies
            ("image/gif", b"GIF89a"),  # not a type we take
            (None, PNG_1x1),
            ("text/plain", b"hello"),
        ):
            exc = raised(E.OcrError, lambda c=ctype, h=head: E.detect(c, h))
            assert (exc.status, exc.code) == (415, "unsupported_type")
        assert E.sniff(b"II*\x00rest") == "tiff"
        assert E.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"
        assert E.sniff(b"\xff\xd8\xff\xe0") == "jpeg"

    def test_image_pixels_from_the_header(self) -> None:
        assert E.image_pixels("png", PNG_1x1) == 1
        big_png = PNG_1x1[:16] + (20000).to_bytes(4, "big") + (20000).to_bytes(4, "big")
        assert E.image_pixels("png", big_png) == 400_000_000
        # A JPEG: SOI, an APP0 segment, then SOF0 with 3000 x 2000.
        jpeg = (
            b"\xff\xd8"
            + b"\xff\xe0\x00\x04ab"
            + b"\xff\xc0\x00\x11\x08"
            + (2000).to_bytes(2, "big")
            + (3000).to_bytes(2, "big")
            + b"\x00" * 12
        )
        assert E.image_pixels("jpeg", jpeg) == 6_000_000
        vp8x = (
            b"RIFF\x00\x00\x00\x00WEBPVP8X"
            + b"\x00" * 8
            + (99).to_bytes(3, "little")
            + (49).to_bytes(3, "little")
        )
        assert E.image_pixels("webp", vp8x) == 5000
        assert E.image_pixels("tiff", b"II*\x00") is None
        assert E.image_pixels("jpeg", b"\xff\xd8\x00") is None


class Pinned(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _lock(self, data: bytes) -> Path:
        p = self.tmp / "lock.json"
        p.write_text(
            json.dumps(
                {
                    "default": "t",
                    "models": {
                        "t": {
                            "repo": "tesseract-ocr/tessdata_fast",
                            "revision": "a" * 40,
                            "licence": "Apache-2.0",
                            "files": {
                                "fas.traineddata": {
                                    "size": len(data),
                                    "sha256": hashlib.sha256(data).hexdigest(),
                                }
                            },
                        }
                    },
                }
            )
        )
        return p

    def test_the_repository_lock_pins_fas_and_eng_with_their_revision(self) -> None:
        for name in ("fast", "best"):
            pinned = L.load(Settings().lock_file, name)
            assert re.fullmatch(r"[0-9a-f]{40}", pinned.revision)
            assert {f.lang for f in pinned.files} == {"fas", "eng"}
            assert all(re.fullmatch(r"[0-9a-f]{64}", f.sha256) and f.size > 0 for f in pinned.files)
            assert pinned.licence == "Apache-2.0"
            assert all(
                pinned.url(f).startswith(L.RAW_HOST + "/tesseract-ocr/") for f in pinned.files
            )
        assert L.load(Settings().lock_file).name == L.default_name(Settings().lock_file)
        raised(L.ModelInvalid, lambda: L.load(Settings().lock_file, "nope"))

    def test_fetch_takes_only_the_pinned_bytes_and_skips_what_is_right(self) -> None:
        data = b"traineddata" * 100
        pinned = L.load(self._lock(data), "t")
        calls: list[str] = []

        def opener(payload: bytes) -> Any:
            def open_(url: str) -> Any:
                calls.append(url)
                return io.BytesIO(payload)

            return open_

        raised(L.ModelInvalid, lambda: F.fetch(pinned, self.tmp / "m", opener(data + b"x")))
        assert not (self.tmp / "m" / "t" / "fas.traineddata").exists()
        assert not list((self.tmp / "m" / "t").glob("*.part"))
        raised(L.ModelInvalid, lambda: F.fetch(pinned, self.tmp / "m", opener(b"X" * len(data))))
        assert F.fetch(pinned, self.tmp / "m", opener(data)) == 1
        assert F.fetch(pinned, self.tmp / "m", opener(b"never read")) == 0  # already right
        assert len(calls) == 3
        L.verify(pinned, self.tmp / "m" / "t")
        (self.tmp / "m" / "t" / "fas.traineddata").write_bytes(b"tampered")
        raised(L.ModelInvalid, lambda: L.verify(pinned, self.tmp / "m" / "t"))
        raised(L.ModelInvalid, lambda: F._open("http://example.com/fas.traineddata"))


class Http(unittest.TestCase):
    """The API with a stand-in engine (no Tesseract needed)."""

    def setUp(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.release = threading.Event()
        self.started = threading.Event()
        self.block = False
        real_run = E.run

        def fake_run(job: E.Job) -> E.Result:
            self.calls.append((job.kind, job.max_pages))
            if self.block:
                self.started.set()
                self.release.wait(10)
            return E.Result(
                pages=[{"n": 1, "text": "متن", "confidence": 0.9, "words": 1}],
                confidence=0.9,
                seconds=0.01,
            )

        E.run = fake_run  # type: ignore[assignment]
        self.addCleanup(setattr, E, "run", real_run)
        settings = replace(Settings(), max_bytes=4096, max_pixels=100)
        self.service = M.Service(settings, verify=False)
        self.server = M.serve(self.service, "127.0.0.1", 0)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self, body: bytes, ctype: str, query: str = "") -> tuple[int, dict[str, Any]]:
        req = urllib.request.Request(  # noqa: S310 - a local test server
            f"{self.base}/v1/ocr{query}", data=body, method="POST", headers={"Content-Type": ctype}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_an_image_is_read_and_the_engine_is_named(self) -> None:
        status, body = self.post(PNG_1x1, "image/png")
        assert status == 200, body
        assert body["pages"][0]["text"] == "متن" and body["confidence"] == 0.9
        eng = body["engine"]
        assert eng["name"] == "tesseract" and eng["langs"] == ["eng", "fas"]
        assert set(eng["traineddata"]) == {"eng", "fas"}
        assert all(re.fullmatch(r"[0-9a-f]{64}", v) for v in eng["traineddata"].values())
        assert self.calls == [("png", 50)]
        status, _ = self.post(b"%PDF-1.4\n%%EOF\n", "application/pdf", "?max_pages=3")
        assert status == 200 and self.calls[-1] == ("pdf", 3)

    def test_refusals_have_stable_codes(self) -> None:
        assert self.post(b"GIF89a....", "image/gif") == (415, {"error": "unsupported_type"})
        assert self.post(b"%PDF-1.4", "image/png") == (415, {"error": "unsupported_type"})
        assert self.post(b"x" * 5000, "image/png") == (413, {"error": "too_large"})
        big = PNG_1x1[:16] + (100).to_bytes(4, "big") + (100).to_bytes(4, "big") + PNG_1x1[24:]
        assert self.post(big, "image/png") == (413, {"error": "too_large"})  # pixels
        assert self.post(PNG_1x1, "image/png", "?max_pages=0") == (400, {"error": "bad_request"})
        assert self.post(PNG_1x1, "image/png", "?max_pages=x") == (400, {"error": "bad_request"})
        assert self.calls == []  # none of these reached the engine

    def test_one_job_at_a_time_the_second_is_busy(self) -> None:
        self.block = True
        results: list[tuple[int, dict[str, Any]]] = []
        first = threading.Thread(target=lambda: results.append(self.post(PNG_1x1, "image/png")))
        first.start()
        assert self.started.wait(10)
        assert self.post(PNG_1x1, "image/png") == (429, {"error": "busy"})
        self.release.set()
        first.join(10)
        assert results and results[0][0] == 200
        self.block = False
        assert self.post(PNG_1x1, "image/png")[0] == 200  # the slot is free again

    def test_health_and_unknown_paths(self) -> None:
        with urllib.request.urlopen(f"{self.base}/healthz", timeout=5) as resp:  # noqa: S310
            health = json.loads(resp.read())
        assert health["ok"] is True and health["langs"] == ["eng", "fas"]
        exc = raised(
            urllib.error.HTTPError,
            lambda: urllib.request.urlopen(f"{self.base}/v1/other", timeout=5),  # noqa: S310
        )
        assert exc.code == 404


@unittest.skipUnless(real_ready(), "needs Tesseract and the pinned traineddata (make ocr-test)")
class RealTesseract(unittest.TestCase):
    """The committed Persian scan through real Tesseract 5 (fas + eng)."""

    def run_job(self, name: str, mime: str) -> E.Result:
        s = Settings()
        pinned = L.load(s.lock_file, s.model)
        data = (SAMPLES / name).read_bytes()
        return E.run(
            E.Job(
                data=data,
                kind=E.detect(mime, data[: E.HEAD_BYTES]),
                max_pages=5,
                langs="fas+eng",
                tessdata=str(MODELS / pinned.name),
                timeout_s=120,
                page_long_side_px=s.page_long_side_px,
            )
        )

    def recall(self, got: E.Result) -> float:
        truth = fold_words((SAMPLES / "scan_fa.txt").read_text("utf-8"))
        words = set(fold_words(" ".join(p["text"] for p in got.pages)))
        return sum(w in words for w in truth) / len(truth)

    def test_the_persian_scan_gives_searchable_text(self) -> None:
        got = self.run_job("scan_fa.png", "image/png")
        assert len(got.pages) == 1
        assert self.recall(got) >= 0.8, self.recall(got)
        assert got.confidence is not None and 0 < got.confidence <= 1
        text = " ".join(p["text"] for p in got.pages)
        for word in ("قرارداد", "آرمان", "دلار"):  # what a search for the record would type
            assert word in fold_words(text), word

    def test_an_image_only_pdf_is_rasterised_and_read(self) -> None:
        got = self.run_job("scan_fa.pdf", "application/pdf")
        assert len(got.pages) == 1
        assert self.recall(got) >= 0.8, self.recall(got)
        assert got.confidence is not None and 0 < got.confidence <= 1

    def test_a_broken_pdf_is_unreadable(self) -> None:
        s = Settings()
        job = E.Job(
            data=b"%PDF-1.4\nnot a pdf at all\n",
            kind="pdf",
            max_pages=1,
            langs="fas+eng",
            tessdata=str(MODELS / L.load(s.lock_file, s.model).name),
            timeout_s=30,
            page_long_side_px=1000,
        )
        exc = raised(E.OcrError, lambda: E.run(job))
        assert (exc.status, exc.code) == (422, "unreadable")

    def test_the_service_answers_over_http_with_the_real_engine(self) -> None:
        service = M.Service(Settings())
        server = M.serve(service, "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_address[1]}/v1/ocr",
                data=(SAMPLES / "scan_fa.png").read_bytes(),
                method="POST",
                headers={"Content-Type": "image/png"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
                body = json.loads(resp.read())
        finally:
            server.shutdown()
            server.server_close()
        assert body["engine"]["version"].startswith("5.")
        assert 0 < body["confidence"] <= 1 and body["pages"][0]["words"] > 10


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
