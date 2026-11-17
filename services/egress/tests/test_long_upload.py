"""⟨2026-11-17⟩ A long YouTube video in the profile browser: its files are already in the account's
spool (the uploader put them there; a 300 MB video never travels base64 through two JSON hops), each
attach step takes the one file it names, a noted read is kept beside the answer, the optional steps
that did not happen are listed, and `wait_sent` holds the job until the page has sent everything to
the upload host (a closed page would end the upload)."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.async_api")

from pydantic import ValidationError

from hq_egress import browser_web as BW

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Loc:
    def __init__(self, page: Page, sel: str) -> None:
        self.page, self.sel = page, sel

    @property
    def first(self) -> Loc:
        return self

    def nth(self, _i: int) -> Loc:
        return self

    async def count(self) -> int:
        return 1 if self.sel in self.page.texts else 0

    async def inner_text(self, timeout: float) -> str:  # noqa: ASYNC109
        return self.page.texts[self.sel]

    async def set_input_files(self, files: Any, timeout: float) -> None:  # noqa: ASYNC109
        if self.sel in self.page.missing:
            raise BW.Error("no such input")
        self.page.sets.append(
            (self.sel, files if isinstance(files, str) else [f["name"] for f in files])
        )

    async def click(self, timeout: float) -> None:  # noqa: ASYNC109
        if self.sel in self.page.missing:
            raise BW.Error("no such element")
        self.page.clicks.append(self.sel)

    async def press_sequentially(self, text: str, delay: float, timeout: float) -> None:  # noqa: ASYNC109
        self.page.typed.append((self.sel, text))

    async def fill(self, text: str, timeout: float) -> None:  # noqa: ASYNC109
        self.page.filled.append((self.sel, text))

    async def is_visible(self) -> bool:
        return False


class Page:
    url = "https://studio.test/upload"

    def __init__(self) -> None:
        self.sets: list[tuple[str, Any]] = []
        self.clicks: list[str] = []
        self.typed: list[tuple[str, str]] = []
        self.filled: list[tuple[str, str]] = []
        self.texts: dict[str, str] = {}
        self.missing: set[str] = set()

    def locator(self, sel: str) -> Loc:
        return Loc(self, sel)

    async def wait_for_timeout(self, ms: float) -> None:
        return None

    async def screenshot(self, **_: Any) -> bytes:
        return b"\xff\xd8\xff" + b"\x00" * 8


def job(**over: Any) -> BW.JobIn:
    base: dict[str, Any] = {
        "account": "youtube-web", "recipe": {"hosts": ["studio.test"], "steps": []}, "prompt": "t",
        "timeout_s": 60, "proxy": {"server": "http://egress:3132"}, "max_file_bytes": 1000,
    }  # fmt: skip
    base.update(over)
    return BW.JobIn.model_validate(base)


@pytest.fixture
def spool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(BW, "SPOOL", tmp_path / ".spool")
    d = tmp_path / ".spool" / "youtube-web"
    d.mkdir(parents=True)
    (d / "lesson.mp4").write_bytes(b"v" * 500)
    (d / "lesson-thumb.jpg").write_bytes(b"\xff\xd8\xff" + b"t" * 10)
    return d


# ------------------------------------------------------------------ spooled files --
async def test_each_attach_takes_the_spooled_file_it_names(spool: Path) -> None:
    page = Page()
    j = job(spooled=["lesson.mp4", "lesson-thumb.jpg"])
    await BW._attach(page, "input[type=file]", j, 1000, 0)  # type: ignore[arg-type]
    await BW._attach(page, "#file-loader", j, 1000, 1)  # type: ignore[arg-type]
    assert page.sets == [
        ("input[type=file]", str(spool / "lesson.mp4")),
        ("#file-loader", str(spool / "lesson-thumb.jpg")),
    ]
    with pytest.raises(BW.StepFailed, match="no file 2"):
        await BW._attach(page, "#x", j, 1000, 2)  # type: ignore[arg-type]
    # several spooled files and no choice: refused, never a guess which input takes which
    with pytest.raises(BW.StepFailed):
        await BW._attach(page, "#x", j, 1000)  # type: ignore[arg-type]
    # one spooled file alone goes in as before
    await BW._attach(page, "#one", job(spooled=["lesson.mp4"]), 1000)  # type: ignore[arg-type]
    assert page.sets[-1] == ("#one", str(spool / "lesson.mp4"))


async def test_a_carried_file_is_picked_by_its_place_before_the_spooled_ones(spool: Path) -> None:
    page = Page()
    carried = [{"name": "cover.png", "b64": base64.b64encode(b"\x89PNG").decode()}]
    j = job(files=carried, spooled=["lesson.mp4"])
    await BW._attach(page, "#a", j, 1000, 0)  # type: ignore[arg-type]
    await BW._attach(page, "#b", j, 1000, 1)  # type: ignore[arg-type]
    assert page.sets == [("#a", ["cover.png"]), ("#b", str(spool / "lesson.mp4"))]


async def test_a_spooled_file_is_a_plain_file_of_the_spool_within_its_cap(
    spool: Path, tmp_path: Path
) -> None:
    (tmp_path / "secret").write_bytes(b"s")
    os.symlink(tmp_path / "secret", spool / "link.mp4")
    (spool / "big.mp4").write_bytes(b"b" * 1001)
    (spool / "empty.mp4").write_bytes(b"")
    (spool / "dir.mp4").mkdir()
    for name, why in (("gone.mp4", "missing"), ("link.mp4", "plain file"),
                      ("big.mp4", "over its cap"), ("empty.mp4", "empty"),
                      ("dir.mp4", "plain file"), ("..", "name")):  # fmt: skip
        with pytest.raises(BW.StepFailed, match=why):
            BW.spooled_path("youtube-web", name, 1000)
    assert BW.spooled_path("youtube-web", "lesson.mp4", 1000) == str(spool / "lesson.mp4")
    # the job itself names plain names only
    for bad in ("../x", "a/b.mp4", ".hidden", "/etc/passwd", ""):
        with pytest.raises(ValidationError):
            job(spooled=[bad])
    with pytest.raises(ValidationError):
        job(spooled=["v.mp4"] * 11)


async def test_the_jobs_end_removes_its_spooled_files(
    spool: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = BW.Webd(profiles=spool.parent.parent)

    class Ctx:
        def __init__(self) -> None:
            self.pages: list[Any] = []

        async def route(self, *_: Any) -> None:
            return None

        def on(self, *_: Any) -> None:
            return None

        async def new_page(self) -> Page:
            return Page()

        async def close(self) -> None:
            return None

    async def fake_open(*_: Any, **__: Any) -> Ctx:
        return Ctx()

    async def fake_run(*_: Any) -> dict[str, Any]:
        assert (spool / "lesson.mp4").exists()  # kept while the page sends it
        return {"ok": True, "text_md": "x", "file": None}

    monkeypatch.setattr(d, "open", fake_open)
    monkeypatch.setattr(BW, "run_recipe", fake_run)
    got = await d._job(job(spooled=["lesson.mp4"]))
    assert got["ok"] is True and not spool.exists()  # noqa: ASYNC240


# ------------------------------------------------------------ notes and skipped --
async def test_a_noted_read_and_the_skipped_steps_come_back_beside_the_answer(spool: Path) -> None:
    page = Page()
    page.texts = {
        "#thumb-area": "Custom thumbnail uploaded",
        "a.link": "https://youtu.be/abcDEF12_-x",
    }
    page.missing = {"#file-loader"}
    steps = [
        {"do": "attach", "selector": "input[type=file]", "file": 0},
        {"do": "attach", "selector": "#file-loader", "file": 1, "optional": True},
        {"do": "read", "selector": "#thumb-area", "note": "thumbnail", "optional": True},
        {"do": "read", "selector": "#nothing", "note": "other", "optional": True},
        {"do": "fill", "selector": "#tags", "text": "{tags}", "typed": True},
        {"do": "read", "selector": "a.link"},
    ]
    j = job(spooled=["lesson.mp4", "lesson-thumb.jpg"], tags="بیت‌کوین, بلاکچین,",
            recipe={"hosts": ["studio.test"], "steps": steps})  # fmt: skip
    got = await BW.run_recipe(page, None, j, frozenset({"studio.test"}))  # type: ignore[arg-type]
    assert got["ok"] is True and got["text_md"] == "https://youtu.be/abcDEF12_-x"
    assert got["notes"] == {"thumbnail": "Custom thumbnail uploaded"}
    assert got["skipped"] == ["1:attach", "3:read"]
    assert page.typed == [("#tags", "بیت‌کوین, بلاکچین,")] and page.clicks == ["#tags"]
    # a job without tags: its tag step fails (an optional one is skipped), never types nothing
    j = job(spooled=["lesson.mp4"], recipe={"hosts": ["studio.test"], "steps": steps[4:]})
    got = await BW.run_recipe(Page(), None, j, frozenset({"studio.test"}))  # type: ignore[arg-type]
    assert (got["ok"], got["step"]) == (False, "0:fill")


async def test_a_failed_job_gives_the_text_it_had_read(spool: Path) -> None:
    page = Page()
    page.texts = {"a.link": "https://youtu.be/abcDEF12_-x"}
    page.missing = {"#done-button"}
    steps = [{"do": "read", "selector": "a.link"}, {"do": "click", "selector": "#done-button"}]
    j = job(recipe={"hosts": ["studio.test"], "steps": steps})
    got = await BW.run_recipe(page, None, j, frozenset({"studio.test"}))  # type: ignore[arg-type]
    assert (got["ok"], got["error"], got["step"]) == (False, "recipe_failed", "1:click")
    assert got["partial"] == "https://youtu.be/abcDEF12_-x" and "screenshot" in got


# ---------------------------------------------------------------------- wait_sent --
class _Req:
    """A request as Playwright gives it to the context's events (hashable by identity)."""

    def __init__(self, url: str) -> None:
        self.url = url


def _req(url: str) -> Any:
    return _Req(url)


async def test_wait_sent_holds_the_job_until_the_upload_host_is_quiet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(BW, "SENT_QUIET_S", 0.0)
    t = BW.Traffic()
    assert await t.sent("upload.test", 1000) == "no request to upload.test seen"
    chunk = _req("https://upload.test/upload/studio?x=1")
    t.started(chunk)  # type: ignore[arg-type]
    t.started(_req("https://studio.test/page"))  # type: ignore[arg-type]
    assert t.in_flight("upload.test") == 1
    with pytest.raises(BW.StepFailed, match="still sending"):
        await t.sent("upload.test", 10)  # a chunk still in flight past the step's time
    t.ended(chunk)  # type: ignore[arg-type]
    got = await t.sent("upload.test", 1000)
    assert got.startswith("sent: 1 requests to upload.test")
    # the step itself names one of the recipe's hosts
    page = Page()
    j = job(recipe={"hosts": ["studio.test"], "steps": [
        {"do": "wait_sent", "url": "https://upload.test/", "note": "sent"},
        {"do": "read", "selector": "a"}]})  # fmt: skip
    page.texts = {"a": "link"}
    got = await BW.run_recipe(page, None, j, frozenset({"studio.test"}), t)  # type: ignore[arg-type]
    assert (got["ok"], got["step"]) == (False, "0:wait_sent")
    got = await BW.run_recipe(page, None, j, frozenset({"studio.test", "upload.test"}), t)  # type: ignore[arg-type]
    assert got["ok"] is True and got["notes"]["sent"].startswith("sent: 1 requests")
