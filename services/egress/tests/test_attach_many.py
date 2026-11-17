"""⟨2026-11-16⟩ Several files into a page's file input (DotCoin.me's cover: the owner's six
reference photos): ChatGPT's first file input takes ONE file ("Non-multiple file input can only
accept single file"), so a multiple input is used when there is one, else the files go one by one."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("playwright.async_api")

from hq_egress import browser_web as BW

pytestmark = pytest.mark.anyio


class Loc:
    def __init__(self, page: Page, sel: str) -> None:
        self.page, self.sel = page, sel

    @property
    def first(self) -> Loc:
        return self

    async def count(self) -> int:
        return 1 if self.sel.endswith("[multiple]") and self.page.multiple else 0

    async def set_input_files(self, files: list[dict[str, Any]], timeout: float) -> None:  # noqa: ASYNC109
        if len(files) > 1 and not self.sel.endswith("[multiple]"):
            raise RuntimeError("Non-multiple file input can only accept single file")
        self.page.sets.append((self.sel, [f["name"] for f in files]))


class Page:
    def __init__(self, multiple: bool) -> None:
        self.multiple = multiple
        self.sets: list[tuple[str, list[str]]] = []
        self.waits = 0

    def locator(self, sel: str) -> Loc:
        return Loc(self, sel)

    async def wait_for_timeout(self, ms: float) -> None:
        self.waits += 1


def job(n: int) -> Any:
    files = [{"name": f"ref{i}.jpg", "b64": base64.b64encode(b"x" * 10).decode()} for i in range(n)]
    return SimpleNamespace(files=files, max_file_bytes=1000)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_one_file_goes_as_before() -> None:
    page = Page(multiple=False)
    await BW._attach(page, "input[type=file]", job(1), 1000)  # type: ignore[arg-type]
    assert page.sets == [("input[type=file]", ["ref0.jpg"])]


async def test_several_files_go_one_by_one_into_a_single_input() -> None:
    page = Page(multiple=False)
    await BW._attach(page, "input[type=file]", job(4), 1000)  # type: ignore[arg-type]
    assert page.sets == [("input[type=file]", [f"ref{i}.jpg"]) for i in range(4)]
    assert page.waits == 4


async def test_several_files_go_at_once_into_a_multiple_input() -> None:
    page = Page(multiple=True)
    await BW._attach(page, "input[type=file]", job(6), 1000)  # type: ignore[arg-type]
    assert page.sets == [("input[type=file][multiple]", [f"ref{i}.jpg" for i in range(6)])]
