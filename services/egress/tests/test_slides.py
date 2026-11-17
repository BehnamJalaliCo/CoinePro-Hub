"""⟨2026-11-17⟩ A set of slides made in ONE ChatGPT chat (the owner: ChatGPT designs 10 to 15
story slides at once, each a picture of its own): every made picture is taken in order, each
source once, none of the asker's own attached files; egress checks each one as it checks a file."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from hq_egress import recipes as R
from hq_egress import substitutes_web as SW

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 40


def _data(b: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(b).decode()


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


# ------------------------------------------------------------------ the recipe --
def test_chatgpts_slides_task_loads_with_its_long_wait() -> None:
    path = Path(os.environ.get("HQ_EGRESS_RECIPES", "/recipes")) / "chatgpt-web.yaml"
    if not path.is_file():
        pytest.skip("the recipes are mounted by test-env.sh (HQ_EGRESS_RECIPES)")
    recipe = R.Recipe.model_validate(yaml.safe_load(path.read_text()))
    task = recipe.tasks["slides"]
    assert task.timeout_s <= R.TASK_CAP_S["slides"] == 1500
    dos = [s.do for s in task.steps]
    assert dos[-1] == "download_images"
    attach = next(s for s in task.steps if s.do == "attach")
    assert attach.optional  # a set may carry references, or none


def test_only_the_slides_task_waits_past_ten_minutes() -> None:
    # ⟨2026-11-17⟩ and a long video's upload (up to 1 GB through Studio)
    assert {k for k, v in R.TASK_CAP_S.items() if v > 600} == {"slides", "upload_long"}


# ------------------------------------------------------------- egress's answer --
def test_every_slide_is_checked_and_passed_on_in_order() -> None:
    got = {
        "ok": True,
        "file": {"name": "slide_01.png", "b64": _b64(PNG)},
        "files": [
            {"name": "slide_01.png", "b64": _b64(PNG)},
            {"name": "slide_02.jpg", "b64": _b64(JPG)},
        ],
    }
    body = json.loads(SW._job_answer(got, "3", 1000).body)
    assert body["ok"] is True
    assert [f["name"] for f in body["files"]] == ["slide_01.png", "slide_02.jpg"]
    assert [f["mime"] for f in body["files"]] == ["image/png", "image/jpeg"]
    assert body["file"]["name"] == "slide_01.png"


def test_one_bad_slide_fails_the_set() -> None:
    got = {
        "ok": True,
        "file": {"name": "slide_01.png", "b64": _b64(PNG)},
        "files": [
            {"name": "slide_01.png", "b64": _b64(PNG)},
            {"name": "slide_02.txt", "b64": _b64(b"not a picture at all")},
        ],
    }
    body = json.loads(SW._job_answer(got, "3", 1000).body)
    assert body["ok"] is False


def test_a_one_file_answer_has_no_set() -> None:
    got = {"ok": True, "file": {"name": "image", "b64": _b64(PNG)}}
    body = json.loads(SW._job_answer(got, "3", 1000).body)
    assert body["file"]["mime"] == "image/png"
    assert "files" not in body


def test_a_slides_job_may_wait_up_to_half_an_hour() -> None:
    a = SW.WebIn(account="chatgpt-web", task="slides", prompt="12 slides", timeout_s=1620)
    assert a.timeout_s == 1620


# -------------------------------------------------------- the profile browser --
try:
    from hq_egress import browser_web as BW
except ImportError:  # (the browser's own image has Playwright; egress's has not)
    BW = None  # type: ignore[assignment]
needs_browser = pytest.mark.skipif(BW is None, reason="no Playwright here")


class El:
    def __init__(self, src: str, in_user: bool) -> None:
        self.src, self.in_user = src, in_user

    async def get_attribute(self, attr: str, timeout: float) -> str:  # noqa: ASYNC109
        return self.src


class Loc:
    def __init__(self, els: list[El]) -> None:
        self.els = els

    async def evaluate_all(self, js: str, attr: str) -> list[int]:
        # what MADE_JS does on the page: not in the asker's message, each source once
        seen: set[str] = set()
        out = []
        for i, e in enumerate(self.els):
            if e.in_user or e.src in seen:
                continue
            seen.add(e.src)
            out.append(i)
        return out

    def nth(self, i: int) -> El:
        return self.els[i]


class Page:
    def __init__(self, els: list[El]) -> None:
        self.els = els
        self.url = "https://chatgpt.com/c/1"

    def locator(self, sel: str) -> Loc:
        return Loc(self.els)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@needs_browser
@pytest.mark.anyio
async def test_every_made_picture_is_taken_in_order_without_the_attached_ones() -> None:
    els = [
        El(_data(b"ref-a"), in_user=True),  # the job's own attached files
        El(_data(b"ref-b"), in_user=True),
        El(_data(PNG + b"1"), in_user=False),
        El(_data(PNG + b"1"), in_user=False),  # the site's twin of the same blob
        El(_data(JPG + b"2"), in_user=False),
        El(_data(PNG + b"3"), in_user=False),
    ]
    j = SimpleNamespace(max_file_bytes=10_000)
    got = await BW._images(Page(els), None, "img", "src", 1000, j, frozenset())  # type: ignore[arg-type]
    assert [f["name"] for f in got] == ["slide_01.png", "slide_02.jpg", "slide_03.png"]
    assert base64.b64decode(got[1]["b64"]) == JPG + b"2"


@needs_browser
@pytest.mark.anyio
async def test_no_more_than_fifteen_pictures_are_taken() -> None:
    els = [El(_data(PNG + bytes([i])), in_user=False) for i in range(20)]
    j = SimpleNamespace(max_file_bytes=10_000)
    got = await BW._images(Page(els), None, "img", "src", 1000, j, frozenset())  # type: ignore[arg-type]
    assert len(got) == BW.MAX_IMAGES == R.MAX_IMAGES == 15


@needs_browser
@pytest.mark.anyio
async def test_an_answer_without_a_made_picture_fails_the_step() -> None:
    j = SimpleNamespace(max_file_bytes=10_000)
    with pytest.raises(BW.StepFailed):
        await BW._images(Page([El(_data(b"r"), in_user=True)]), None, "img", "src", 1000, j,  # type: ignore[arg-type]
                         frozenset())  # fmt: skip


def test_the_slides_task_asks_again_in_the_same_chat_before_taking_the_set() -> None:
    path = Path(os.environ.get("HQ_EGRESS_RECIPES", "/recipes")) / "chatgpt-web.yaml"
    if not path.is_file():
        pytest.skip("the recipes are mounted by test-env.sh (HQ_EGRESS_RECIPES)")
    steps = R.Recipe.model_validate(yaml.safe_load(path.read_text())).tasks["slides"].steps
    dos = [s.do for s in steps]
    assert dos.index("more_images") < dos.index("download_images")
    more = steps[dos.index("more_images")]
    assert more.composer and more.busy and more.selector


def test_more_images_needs_its_composer_and_its_busy_control() -> None:
    with pytest.raises(ValueError):
        R.RStep(do="more_images", selector="img")
    with pytest.raises(ValueError):
        R.RStep(do="read", selector="p", composer="div")
    R.RStep(do="more_images", selector="img", composer="div[contenteditable=true]", busy="button")


class Chat:
    """A chat that answers each «continue» with `per_turn` new pictures."""

    def __init__(self, first: int, per_turn: int) -> None:
        self.made, self.per_turn = first, per_turn
        self.sent: list[str] = []

    def locator(self, sel: str) -> Any:
        chat = self

        class L:
            @property
            def first(self) -> Any:
                return self

            async def evaluate_all(self, js: str, attr: str) -> list[int]:
                return list(range(chat.made))

            async def fill(self, text: str, timeout: float) -> None:  # noqa: ASYNC109
                chat.sent.append(text)

            async def press(self, key: str, timeout: float) -> None:  # noqa: ASYNC109
                chat.made += chat.per_turn

            async def wait_for(self, state: str, timeout: float) -> None:  # noqa: ASYNC109
                return None

        return L()

    async def wait_for_timeout(self, ms: float) -> None:
        return None


@needs_browser
@pytest.mark.anyio
async def test_a_short_answer_is_continued_until_the_set_is_whole() -> None:
    chat = Chat(first=1, per_turn=1)
    j = SimpleNamespace(limit=12)
    await BW._more_images(chat, "img", "div", "button", 1_500_000, j)  # type: ignore[arg-type]
    assert chat.made == 12 and len(chat.sent) == 11
    assert "slide 2 of 12" in chat.sent[0] and "slide 12 of 12" in chat.sent[-1]


@needs_browser
@pytest.mark.anyio
async def test_a_whole_set_asks_nothing_more_and_a_stuck_chat_stops() -> None:
    whole = Chat(first=12, per_turn=1)
    await BW._more_images(whole, "img", "div", "button", 1_500_000, SimpleNamespace(limit=12))  # type: ignore[arg-type]
    assert whole.sent == []
    stuck = Chat(first=1, per_turn=0)  # never makes another: at most one ask per missing slide
    await BW._more_images(stuck, "img", "div", "button", 1_500_000, SimpleNamespace(limit=4))  # type: ignore[arg-type]
    assert len(stuck.sent) == 4
