"""The pinned traineddata (services/ocr/model.lock.json): for each set a
repository of the tesseract-ocr project, an exact revision, and the size and
sha256 of every file. Fetching downloads exactly those bytes; serving refuses
anything else."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

CHUNK = 1024 * 1024
# The raw file host of the pinned repositories (the only host ocr-fetch reaches).
RAW_HOST = "https://raw.githubusercontent.com"


class ModelInvalid(Exception):
    """A traineddata file is missing or its bytes are not the pinned ones."""


@dataclass(frozen=True)
class PinnedFile:
    name: str
    size: int
    sha256: str

    @property
    def lang(self) -> str:
        return self.name.removesuffix(".traineddata")


@dataclass(frozen=True)
class PinnedSet:
    name: str
    repo: str
    revision: str
    licence: str
    files: tuple[PinnedFile, ...]

    def url(self, file: PinnedFile) -> str:
        return f"{RAW_HOST}/{self.repo}/{self.revision}/{file.name}"

    def sha256s(self) -> dict[str, str]:
        return {f.lang: f.sha256 for f in self.files}


def default_name(path: str | Path) -> str:
    return str(json.loads(Path(path).read_text("utf-8"))["default"])


def load(path: str | Path, name: str = "") -> PinnedSet:
    data = json.loads(Path(path).read_text("utf-8"))
    name = name or str(data["default"])
    try:
        m = data["models"][name]
    except KeyError as exc:
        raise ModelInvalid(f"traineddata set {name!r} is not pinned in {path}") from exc
    files = tuple(
        PinnedFile(fname, int(f["size"]), str(f["sha256"])) for fname, f in m["files"].items()
    )
    return PinnedSet(name, m["repo"], m["revision"], m.get("licence", ""), files)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def verify(pinned: PinnedSet, directory: Path) -> None:
    """Every pinned file present with its exact size and sha256, else ModelInvalid."""
    for f in pinned.files:
        p = directory / f.name
        if not p.is_file():
            raise ModelInvalid(f"{pinned.name}: {f.name} is missing (run make ocr-fetch)")
        if p.stat().st_size != f.size or sha256_of(p) != f.sha256:
            raise ModelInvalid(f"{pinned.name}: {f.name} is not the pinned file")
