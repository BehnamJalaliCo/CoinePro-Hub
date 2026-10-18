"""The pinned models (services/stt/model.lock.json): for each model a Hugging Face
repository, an exact commit revision, and the size and sha256 of every file.
Fetching downloads exactly those bytes; serving refuses anything else."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

CHUNK = 1024 * 1024


class ModelInvalid(Exception):
    """A model file is missing or its bytes are not the pinned ones."""


@dataclass(frozen=True)
class PinnedFile:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class PinnedModel:
    name: str
    repo: str
    revision: str
    licence: str
    files: tuple[PinnedFile, ...]

    def url(self, file: PinnedFile) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/{self.revision}/{file.name}"


def load(path: str | Path, name: str) -> PinnedModel:
    data = json.loads(Path(path).read_text("utf-8"))
    try:
        m = data["models"][name]
    except KeyError as exc:
        raise ModelInvalid(f"model {name!r} is not pinned in {path}") from exc
    files = tuple(
        PinnedFile(fname, int(f["size"]), str(f["sha256"])) for fname, f in m["files"].items()
    )
    return PinnedModel(name, m["repo"], m["revision"], m.get("licence", ""), files)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def verify(model: PinnedModel, directory: Path) -> None:
    """Every pinned file present with its exact size and sha256, else ModelInvalid."""
    for f in model.files:
        path = directory / f.name
        if not path.is_file():
            raise ModelInvalid(f"{model.name}: {f.name} is missing (run the stt-fetch job)")
        if path.stat().st_size != f.size:
            raise ModelInvalid(f"{model.name}: {f.name} has the wrong size")
        if sha256_of(path) != f.sha256:
            raise ModelInvalid(f"{model.name}: {f.name} does not match its pinned sha256")
