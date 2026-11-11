"""⟨0.3.2⟩ A workspace turn's deliverables (contract §43, the holding's workshop).

When a `claude` job with `args.workspace` ends well (⟨0.3.3⟩ or is stopped at its time limit:
what it had made is not lost), the files the session left in `out/` of
the work's folder go to the hub, one request each (POST /runners/jobs/{id}/files, raw body,
while the job still runs), and the result names them (`files`): the hub attaches them to the
turn's output in the owner's session. The same folder serves every turn of the work, so a file
already sent with the same bytes is not sent again (workspaces.json keeps `sent: {path: sha256}`).

Only regular files under `out/` (no symbolic link, nothing hidden), at most MAX_FILES a turn,
of the types the hub takes for a deliverable, each within its size: video (mp4, webm, mov ≤ 200
MB), image (png, jpeg, webp ≤ 20 MB), PDF (≤ 30 MB), text, Markdown and ZIP (≤ 50 MB), audio
(≤ 25 MB). Anything else is listed in `files_skipped` with why, never sent. The hub checks the
type by the bytes again and refuses what it does not take.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import hashlib
import logging
import os
import stat
from pathlib import Path
from typing import Any, BinaryIO

from hq_runner import workspace as WSP
from hq_runner.hub import HubError, JobGone, with_retry

log = logging.getLogger("hq_runner.outbox")

OUT = "out"
MAX_FILES = 20
MB = 1024 * 1024
# extension -> (Content-Type, the hub's limit for it)
TYPES: dict[str, tuple[str, int]] = {
    ".mp4": ("video/mp4", 200 * MB),
    ".m4v": ("video/mp4", 200 * MB),
    ".webm": ("video/webm", 200 * MB),
    ".mov": ("video/quicktime", 200 * MB),
    ".png": ("image/png", 20 * MB),
    ".jpg": ("image/jpeg", 20 * MB),
    ".jpeg": ("image/jpeg", 20 * MB),
    ".webp": ("image/webp", 20 * MB),
    ".pdf": ("application/pdf", 30 * MB),
    ".md": ("text/markdown", 50 * MB),
    ".markdown": ("text/markdown", 50 * MB),
    ".txt": ("text/plain", 50 * MB),
    ".zip": ("application/zip", 50 * MB),
    ".m4a": ("audio/mp4", 25 * MB),
    ".mp3": ("audio/mpeg", 25 * MB),
    ".wav": ("audio/wav", 25 * MB),
    ".ogg": ("audio/ogg", 25 * MB),
    ".opus": ("audio/ogg", 25 * MB),
}
TYPE_FA = "این نوع فایل تحویل‌دادنی نیست"
SIZE_FA = "از سقف اندازه‌ی این نوع بزرگ‌تر است"
MANY_FA = f"بیش از {MAX_FILES} فایل در یک نوبت"
REFUSED_FA = "ستاد این فایل را نپذیرفت"


Listed = tuple[Path, str, str, str, tuple[int, int]]  # path, name, type, sha256, (dev, inode)
READ_ONCE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def sha256_of(fh: BinaryIO) -> str:
    h = hashlib.sha256()
    while chunk := fh.read(1 << 20):
        h.update(chunk)
    return h.hexdigest()


def open_listed(path: Path, root: Path | None, ident: tuple[int, int] | None) -> BinaryIO | None:
    """The file itself, opened once and never through a link (contract §43.9: the session, or a
    process it left running, may swap a name for a link to the runner's token between the list
    and the upload): None unless it is a regular file inside `root` (the real out/), or the very
    file (`ident`) the list saw. Everything is read from this one descriptor."""
    try:
        fd = os.open(path, READ_ONCE)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        ok = stat.S_ISREG(st.st_mode)
        if ok and ident is not None:
            ok = (st.st_dev, st.st_ino) == ident
        if ok and root is not None and os.path.isdir("/proc/self/fd"):
            ok = Path(os.readlink(f"/proc/self/fd/{fd}")).is_relative_to(root)
        if ok:
            return os.fdopen(fd, "rb")
    except OSError:
        pass
    os.close(fd)
    return None


def candidates(folder: Path, sent: dict[str, str]) -> tuple[list[Listed], list[dict[str, str]]]:
    """(the files to send: path, its name under out/, Content-Type, sha256, its (device,
    inode); the files skipped: {name, why}). Files already sent with the same bytes are
    neither."""
    out = folder / OUT
    if out.is_symlink() or not out.is_dir():
        return [], []
    root = out.resolve()
    send: list[Listed] = []
    skipped: list[dict[str, str]] = []
    for path in sorted(out.rglob("*")):
        rel = path.relative_to(out).as_posix()
        if any(part.startswith(".") for part in path.relative_to(out).parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        if not path.resolve().is_relative_to(root):
            continue
        kind = TYPES.get(path.suffix.lower())
        if kind is None:
            skipped.append({"name": rel, "why": TYPE_FA})
            continue
        fh = open_listed(path, root, None)
        if fh is None:
            continue
        with fh:
            st = os.fstat(fh.fileno())
            if st.st_size > kind[1]:
                skipped.append({"name": rel, "why": SIZE_FA})
                continue
            digest = sha256_of(fh)
        if sent.get(rel) == digest:
            continue
        if len(send) >= MAX_FILES:
            skipped.append({"name": rel, "why": MANY_FA})
            continue
        send.append((path, rel, kind[0], digest, (st.st_dev, st.st_ino)))
    return send, skipped


async def send(
    ctx: Any, folder: Path, ref: str
) -> tuple[list[str], list[dict[str, str]], dict[str, str]]:
    """Sends the turn's new files in `out/` -> (the hub's file ids, the files skipped, and
    ⟨0.3.3⟩ what to record as sent {name: sha256} once the hub has taken the turn's result: a
    file recorded before that was never sent again when the result did not arrive, and reached
    no output at all)."""
    sent = await asyncio.to_thread(WSP.sent_of, ref, ctx.cfg_path)
    todo, skipped = await asyncio.to_thread(candidates, folder, sent)
    ids: list[str] = []
    marks: dict[str, str] = {}
    for path, rel, ctype, digest, ident in todo:
        # the file the list saw, opened once: the upload reads this descriptor, not the name
        fh = await asyncio.to_thread(open_listed, path, None, ident)
        if fh is None:
            log.warning("job %s: a file of out/ changed before it was sent", ctx.id)
            skipped.append({"name": rel, "why": REFUSED_FA})
            continue
        try:
            ref_: dict[str, Any] | None = await with_retry(
                functools.partial(ctx.hub.upload_file, ctx.id, fh, rel, ctype)
            )
        except JobGone:
            log.warning("job %s ended while its files were being sent", ctx.id)
            break
        except HubError as exc:
            log.warning("job %s: a file of out/ was refused (%s)", ctx.id, exc.code or exc.status)
            skipped.append({"name": rel, "why": REFUSED_FA})
            continue
        finally:
            fh.close()
        fid = str((ref_ or {}).get("id") or "")
        if not fid:
            skipped.append({"name": rel, "why": REFUSED_FA})
            continue
        ids.append(fid)
        marks[rel] = digest
        ctx.sink.emit("progress", {"text": f"out/{rel} sent"})
    return ids, skipped, marks


# ------------------------------------------------------------------ inputs --
IN = "in"
MAX_INPUTS = 10
MAX_INPUT_BYTES = 200 * MB
INPUT_FA = "فایل ورودی «{name}» از ستاد دریافت نشد."


def safe_name(name: Any, i: int) -> str:
    """A file name of its own inside `in/`: no folder, nothing hidden, never empty."""
    base = Path(str(name or "")).name.strip().lstrip(".")
    base = "".join(c for c in base if c >= " " and c not in '\\/:*?"<>|')[:120].strip()
    return base or f"input-{i}"


async def fetch(ctx: Any, folder: Path, inputs: Any) -> list[str]:
    """⟨0.3.3⟩ contract §43.8: the hub files a turn takes with it (the narration, a logo, the
    owner's upload of the session) are downloaded into `in/` of the work's folder before the
    session starts, from the job's own route with the runner's token. Returns their names;
    raises HubError when one cannot be fetched (the turn does not start half-fed)."""
    if not isinstance(inputs, list) or not inputs:
        return []
    box = folder / IN
    # The folder is the session's to change (and a process it left may still run), so every
    # name in it is opened through one descriptor of in/ itself, never followed: a link the
    # session planted at in/ or at a file's name never sends the hub's bytes elsewhere.
    try:
        if box.is_symlink():
            raise HubError(0, "bad_input_dir", "in/ is a symbolic link")
        box.mkdir(exist_ok=True, mode=0o700)
        dfd = os.open(box, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        raise HubError(0, "bad_input_dir", type(exc).__name__) from exc
    names: list[str] = []
    try:
        for i, f in enumerate(inputs[:MAX_INPUTS], 1):
            if not isinstance(f, dict) or not isinstance(f.get("url"), str):
                continue
            name = safe_name(f.get("name"), i)
            while name in names:
                name = f"{i}-{name}"
            part = f".{name}.part"
            try:
                await with_retry(
                    functools.partial(ctx.hub.download, f["url"], part, MAX_INPUT_BYTES, dir_fd=dfd)
                )
                # a rename replaces a link at the name itself, never what it points to
                os.replace(part, name, src_dir_fd=dfd, dst_dir_fd=dfd)
            except OSError as exc:
                raise HubError(0, "bad_input", type(exc).__name__) from exc
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(part, dir_fd=dfd)
            names.append(name)
            ctx.sink.emit("progress", {"text": f"in/{name} received"})
    finally:
        os.close(dfd)
    return names
