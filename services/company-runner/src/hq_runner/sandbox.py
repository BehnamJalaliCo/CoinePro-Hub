"""⟨0.3.4⟩ The workshop's wall between the companies (contract §43.9).

Every turn of the holding's workshop runs as the same Linux user, so a turn of one company
could read another company's work folder, its Claude transcripts and the runner's own token.
Landlock (in the kernel since Linux 5.13; used from 5.19, ABI 2) closes those for the turn's
whole process tree. It needs no root, no package and no extra process.

    closed     every other work's folder (~/hq-workspace/*), the runner's own folder (its
               token, workspaces.json), this server's own ~/.claude and ~/.claude.json (other
               turns' transcripts, a login)
    open       everything else exactly as before, the turn's own folder, and its private area
               ~/hq-workspace/.hq/<ref>/ {home/, tmp/, job/}

Landlock only allows (it has no «deny this folder»), so the rule set is «every entry beside the
closed ones»: from `/` down to each closed path, every sibling gets a rule. A folder that holds
a closed path (`/`, `/home`, the home itself, `~/.config`) can therefore not be listed and
nothing new can be made directly in it. The home is where tools do that (`~/.npm`, `~/.cache`,
`~/.gitconfig.lock`), so the turn gets a home of its own: `home/` in its private area, with a
link to every entry of the real home that is not closed (small files are copied, so a tool that
rewrites its dotfile does it in the work's own home). The tools installed in the real home are
found as before; anything new lands in the work's home.

The owner, 2026-11-10: «نکته امنیتی هم اجرا بشه و کار راه بیفته نه اینکه گیر بکنه». So the wall
is `auto`: a kernel without it, a probe that fails or a walled session that does not start
leaves the turn running without the wall, and the result says so (`sandbox: {state, why}`).
HQ_RUNNER_SANDBOX=off switches it off on a server.

`python -m hq_runner sandbox-exec --protect P… --allow A… -- cmd…` is the wrapper: it puts the
wall around itself and becomes `cmd`.
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import errno
import json
import os
import re
import shlex
import shutil
import stat
import struct
import sys
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import hq_runner

# ------------------------------------------------------------------ Landlock --
SYS_CREATE_RULESET, SYS_ADD_RULE, SYS_RESTRICT_SELF = 444, 445, 446
CREATE_RULESET_VERSION = 1
RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38
MIN_ABI = 2  # REFER: before it a walled process can move no file between folders

ACCESS_V1 = (1 << 13) - 1  # execute, read, write, list, make and remove of every kind
ACCESS_REFER = 1 << 13  # ABI 2
ACCESS_TRUNCATE = 1 << 14  # ABI 3
ACCESS_IOCTL_DEV = 1 << 15  # ABI 5
FILE_ACCESS = (1 << 0) | (1 << 1) | (1 << 2) | ACCESS_TRUNCATE | ACCESS_IOCTL_DEV
SCOPE_SIGNAL = 1 << 1  # ABI 6: no signal to a process outside the wall

EXIT_NO_WALL = 126  # the wrapper could not put the wall up (the command was not run)


class SandboxError(RuntimeError):
    """The wall could not be put up; the message is the reason (English, for the report)."""


def _syscall(number: int, *args: Any) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    res = int(libc.syscall(ctypes.c_long(number), *args))
    if res < 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))
    return res


def abi() -> int:
    """Landlock's version on this kernel; 0 when it has none (or it is switched off)."""
    try:
        return _syscall(
            SYS_CREATE_RULESET, None, ctypes.c_size_t(0), ctypes.c_uint(CREATE_RULESET_VERSION)
        )
    except (OSError, AttributeError):
        return 0


def access_of(version: int) -> int:
    rights = ACCESS_V1
    if version >= 2:
        rights |= ACCESS_REFER
    if version >= 3:
        rights |= ACCESS_TRUNCATE
    if version >= 5:
        rights |= ACCESS_IOCTL_DEV
    return rights


def restrict(paths: Iterable[str]) -> int:
    """Puts the wall around this process (and every process it starts): only `paths` (each a
    file, or a folder with everything beneath it) can be opened, made in or removed from.
    Returns how many rules were added. It cannot be taken down again."""
    version = abi()
    if version < MIN_ABI:
        raise SandboxError(f"this kernel has no Landlock (ABI {version}, {MIN_ABI} needed)")
    rights = access_of(version)
    scoped = SCOPE_SIGNAL if version >= 6 else 0
    attr = struct.pack("QQQ", rights, 0, scoped)
    size = 24 if version >= 6 else 16 if version >= 4 else 8
    try:
        ruleset = _syscall(
            SYS_CREATE_RULESET,
            ctypes.create_string_buffer(attr[:size], size),
            ctypes.c_size_t(size),
            ctypes.c_uint(0),
        )
    except OSError as exc:
        raise SandboxError(f"landlock_create_ruleset: {exc.strerror}") from exc
    added = 0
    try:
        for path in dict.fromkeys(paths):
            try:
                fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
            except OSError:
                continue  # gone, or not this user's to open anyway
            try:
                is_dir = stat.S_ISDIR(os.fstat(fd).st_mode)
                allowed = rights if is_dir else rights & FILE_ACCESS
                rule = struct.pack("<Qi", allowed, fd)
                with contextlib.suppress(OSError):
                    _syscall(
                        SYS_ADD_RULE,
                        ctypes.c_int(ruleset),
                        ctypes.c_int(RULE_PATH_BENEATH),
                        ctypes.create_string_buffer(rule, len(rule)),
                        ctypes.c_uint(0),
                    )
                    added += 1
            finally:
                os.close(fd)
        if not added:
            raise SandboxError("no path could be opened for the wall")
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            raise SandboxError("prctl(PR_SET_NO_NEW_PRIVS) failed")
        try:
            _syscall(SYS_RESTRICT_SELF, ctypes.c_int(ruleset), ctypes.c_uint(0))
        except OSError as exc:
            raise SandboxError(f"landlock_restrict_self: {exc.strerror}") from exc
    finally:
        os.close(ruleset)
    return added


# --------------------------------------------------------------- what is open --
def _real(path: str | Path) -> str:
    return os.path.realpath(str(path))


def _beneath(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def open_paths(protect: Iterable[str | Path], allow: Iterable[str | Path]) -> list[str]:
    """Every path that gets a rule: all that exists beside the closed paths, and `allow` (the
    turn's own folders, which may lie inside a closed one). A symbolic link gets no rule: what
    it points to is open under its own name, or closed."""
    closed = sorted({_real(p) for p in protect})
    out: list[str] = []

    def holds_closed(path: str) -> bool:
        return any(c != path and _beneath(c, path) for c in closed)

    def walk(folder: str) -> None:
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            return
        for name in names:
            path = os.path.join(folder, name)
            if os.path.islink(path) or path in closed:
                continue
            if holds_closed(path):
                if os.path.isdir(path):
                    walk(path)
                continue
            out.append(path)

    if closed:
        walk("/")
    else:
        out.append("/")
    out += [_real(a) for a in allow]
    return list(dict.fromkeys(out))


# -------------------------------------------------------------- the turn's home --
COPY_MAX = 1024 * 1024  # a dotfile this small is copied (a tool may rewrite it); else linked


def make_home(real_home: str | Path, home: Path, protect: Iterable[str | Path]) -> None:
    """The turn's own home: a link to every entry of the real home that is not closed (a small
    file is copied; a folder that holds a closed path becomes a folder of the same kind, one
    level deeper). What the work itself put there stays; a link whose target is gone goes."""
    closed = {_real(p) for p in protect}

    def mirror(src: str, dst: Path) -> None:
        dst.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            entries = list(os.scandir(src))
        except OSError:
            entries = []
        for e in entries:
            real = _real(e.path)
            if any(_beneath(real, c) for c in closed):
                continue
            target = dst / e.name
            if e.is_dir(follow_symlinks=False) and any(_beneath(c, real) for c in closed):
                if target.is_symlink() or (target.exists() and not target.is_dir()):
                    target.unlink()  # the session's own file or link where a folder goes
                mirror(e.path, target)
                continue
            try:
                small_file = (
                    e.is_file(follow_symlinks=False)
                    and e.stat(follow_symlinks=False).st_size <= COPY_MAX
                )
            except OSError:
                continue
            if small_file:
                try:
                    if target.is_symlink():
                        target.unlink()
                    if not target.exists() or e.stat().st_mtime > target.stat().st_mtime:
                        shutil.copy2(e.path, target)
                except OSError:
                    pass
                continue
            if target.is_symlink():
                if os.readlink(target) == e.path:
                    continue
                target.unlink()
            elif target.exists():
                continue  # the work's own
            with contextlib.suppress(OSError):
                os.symlink(e.path, target)
        for t in dst.iterdir():
            if t.is_symlink() and not t.exists():
                with contextlib.suppress(OSError):
                    t.unlink()

    mirror(str(real_home), home)


# ----------------------------------------------------------- Claude's sessions --
def project_dir(cwd: str | Path) -> str:
    """The folder name Claude Code keeps a project's sessions under."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def carry_session(
    src_home: str | Path, dst_home: str | Path, cwd: str | Path, session: str
) -> bool:
    """A session started on one side of the wall is found on the other (`--resume`): its file
    (and its folder of side files) is copied when the other side has none, or an older one."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", str(session)):
        return False
    rel = Path(".claude") / "projects" / project_dir(cwd)
    src, dst = Path(src_home) / rel, Path(dst_home) / rel
    moved = False
    for name, is_dir in ((f"{session}.jsonl", False), (str(session), True)):
        s, d = src / name, dst / name
        try:
            if is_dir:
                if s.is_dir() and not s.is_symlink():
                    shutil.copytree(s, d, dirs_exist_ok=True, symlinks=True)
                    moved = True
            elif (
                s.is_file()
                and not s.is_symlink()
                and (not d.exists() or s.stat().st_mtime > d.stat().st_mtime)
            ):
                d.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copy2(s, d)
                moved = True
        except OSError:
            continue
    return moved


# --------------------------------------------------------------------- the plan --
PRIVATE = ".hq"  # ~/hq-workspace/.hq/<ref>: never a work's folder (a ref starts with W-)
SOCK_MAX = 100  # a unix socket's path fits 108 bytes; a longer one goes through its folder's fd


@dataclass
class Plan:
    """One walled turn: what is closed, what is open, and the turn's private area."""

    ref: str
    work: Path
    private: Path
    protect: list[str]
    allow: list[str] = field(default_factory=list)

    @property
    def home(self) -> Path:
        return self.private / "home"

    @property
    def tmp(self) -> Path:
        return self.private / "tmp"

    @property
    def job(self) -> Path:
        return self.private / "job"

    @property
    def sock(self) -> Path:
        return self.job / "hook.sock"


def plan(
    ref: str,
    work: Path,
    workspaces: Path,
    cfg_path: Path,
    claude: str | None,
    real_home: Path | None = None,
) -> Plan:
    home = real_home or Path.home()
    private = workspaces / PRIVATE / ref
    protect = [str(workspaces), str(cfg_path.parent), str(home / ".claude")]
    protect += [str(p) for p in home.glob(".claude.json*")]
    allow = [str(work), str(private)]
    if claude:
        # a CLI installed inside ~/.claude (its old place) stays runnable, and only it
        binary = _real(claude)
        if _beneath(binary, _real(home / ".claude")):
            allow.append(os.path.dirname(binary))
    return Plan(ref, work, private, protect, allow)


def _own_dir(d: Path, *, empty: bool) -> None:
    """A real folder at `d` (`empty`: emptied). The private area is the walled session's to
    change, so what it left at the name (a file, a link) is removed, never kept or followed: a
    file planted at tmp/ must not make the next turn's setup fail and run it without the wall."""
    try:
        st = os.lstat(d)
    except FileNotFoundError:
        st = None
    if st is not None and not stat.S_ISDIR(st.st_mode):
        d.unlink()
    elif st is not None and empty:
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not stat.S_ISDIR(os.lstat(d).st_mode):
        raise SandboxError(f"{d} is not a folder")
    os.chmod(d, 0o700)


def prepare(p: Plan, real_home: Path | None = None) -> None:
    """The private area on the disk: its home (links to the real one), an empty tmp and an
    empty job folder (settings, the hook's log and socket)."""
    _own_dir(p.private, empty=False)
    _own_dir(p.home, empty=False)
    for d in (p.tmp, p.job):
        _own_dir(d, empty=True)
    make_home(real_home or Path.home(), p.home, p.protect)


# the wrapper is this same installation of the runner, found without PYTHONPATH (which the
# turn's own Python would inherit)
BOOT = (
    "import sys; sys.path.insert(0, sys.argv.pop(1)); "
    "from hq_runner.cli import main; sys.exit(main(sys.argv[1:]))"
)


def wrap(p: Plan, argv: list[str]) -> list[str]:
    """`argv` behind the wall."""
    out = [sys.executable, "-c", BOOT, package_root(), "sandbox-exec"]
    for c in p.protect:
        out += ["--protect", c]
    for a in p.allow:
        out += ["--allow", a]
    return [*out, "--", *argv]


def package_root() -> str:
    return str(Path(hq_runner.__file__).resolve().parent.parent)


def env_of(p: Plan, env: dict[str, str]) -> dict[str, str]:
    """The turn's environment behind the wall: its own home and tmp, and the hook's socket in
    place of the runner's config (which it cannot read)."""
    out = {k: v for k, v in env.items() if k not in ("HQ_RUNNER_CONFIG", "CLAUDE_CONFIG_DIR")}
    out.update(
        {
            "HOME": str(p.home),
            "TMPDIR": str(p.tmp),
            "HQ_RUNNER_HOOK_SOCK": str(p.sock),
            "HQ_RUNNER_SANDBOX_STATE": "on",
        }
    )
    return out


# -------------------------------------------------------------------- the probe --
PROBE_TTL_S = 3600.0
_probe: dict[str, tuple[float, str | None]] = {}

PROBE_CODE = """
import os, sys
work, closed = sys.argv[1], sys.argv[2:]
open(os.path.join(work, ".hq-probe"), "w").close()
os.remove(os.path.join(work, ".hq-probe"))
open(os.path.join(os.environ["TMPDIR"], "probe"), "w").close()
os.listdir(os.environ["HOME"])
for c in closed:
    try:
        os.listdir(c)
    except PermissionError:
        continue
    except OSError:
        continue
    sys.exit(3)
print("hq-wall-ok")
"""


def switched_off(env: dict[str, str] | None = None) -> bool:
    value = (env or os.environ).get("HQ_RUNNER_SANDBOX", "").strip().lower()
    return value in ("off", "0", "no", "false")


async def probe(p: Plan, env: dict[str, str], claude: str | None) -> str | None:
    """None when a walled process can work in the turn's folder, cannot list what is closed,
    and can start the CLI; else the reason. Remembered for an hour per server."""
    key = "|".join(sorted(p.protect))
    seen = _probe.get(key)
    now = time.monotonic()
    if seen is not None and now - seen[0] < PROBE_TTL_S:
        return seen[1]
    why = await _probe_once(p, env, claude)
    _probe[key] = (now, why)
    return why


async def _run(argv: list[str], env: dict[str, str], cwd: str, limit_s: float) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), limit_s)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, 9)
        await proc.wait()
        return 124, "timed out"
    return int(proc.returncode or 0), out.decode("utf-8", "replace")[-400:]


async def _probe_once(p: Plan, env: dict[str, str], claude: str | None) -> str | None:
    walled = env_of(p, env)
    closed = [c for c in p.protect if os.path.isdir(c)]  # noqa: ASYNC240 - a local stat
    try:
        code, out = await _run(
            wrap(p, [sys.executable, "-c", PROBE_CODE, str(p.work), *closed]),
            walled,
            str(p.work),
            30.0,
        )
    except OSError as exc:
        return f"the wrapper did not start: {type(exc).__name__}"
    if code != 0 or "hq-wall-ok" not in out:
        return "the probe failed: " + " ".join(out.split())[-200:]
    # the hook is this runner's own code, started by the CLI behind the wall
    hook = [sys.executable, "-c", BOOT, package_root(), "classify-hook"]
    code, out = await _run(wrap(p, hook), walled, str(p.work), 30.0)
    if code != 2 or "bad hook input" not in out:
        return "the hook did not start behind the wall: " + " ".join(out.split())[-200:]
    if claude:
        try:
            code, out = await _run(wrap(p, [claude, "--version"]), walled, str(p.work), 60.0)
        except OSError as exc:
            return f"the CLI did not start behind the wall: {type(exc).__name__}"
        if code != 0:
            return "the CLI did not start behind the wall: " + " ".join(out.split())[-200:]
    return None


async def check(cfg_path: Path | None = None) -> str | None:
    """`hq-runner sandbox-check`: None when the wall works on this server, else the reason."""
    from hq_runner import workspace
    from hq_runner.claude_job import find_claude
    from hq_runner.config import config_path, load

    if switched_off():
        return "switched off on this server (HQ_RUNNER_SANDBOX)"
    version = abi()
    if version < MIN_ABI:
        return f"this kernel has no Landlock (ABI {version}, {MIN_ABI} needed)"
    path = (cfg_path or config_path()).resolve()
    try:
        cfg = load(path)
    except (OSError, ValueError):
        cfg = None
    claude = find_claude(cfg.claude_bin if cfg is not None else None)
    base = workspace.root()
    work = base / PRIVATE / "check" / "work"
    try:
        work.mkdir(parents=True, exist_ok=True, mode=0o700)
        p = plan("check", work, base, path, claude)
        prepare(p)
        return await _probe_once(p, dict(os.environ), claude)
    except (SandboxError, OSError) as exc:
        return str(exc) or type(exc).__name__
    finally:
        shutil.rmtree(base / PRIVATE / "check", ignore_errors=True)


def forget_probe() -> None:
    _probe.clear()


def distrust(p: Plan, why: str) -> None:
    """A walled session did not start: the wall stays down on this server for an hour."""
    _probe["|".join(sorted(p.protect))] = (time.monotonic(), why)


# ------------------------------------------------------------- the hook's socket --
@contextlib.contextmanager
def _short(path: str | Path) -> Any:
    """A socket's path that fits: itself, or the same file through its folder's descriptor."""
    text = str(path)
    if len(text.encode()) <= SOCK_MAX:
        yield text
        return
    fd = os.open(os.path.dirname(text), os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        yield f"/proc/self/fd/{fd}/{os.path.basename(text)}"
    finally:
        os.close(fd)


Classify = Callable[[str], Awaitable[tuple[str | None, str | None]]]
HOOK_LINE = 1024 * 1024


async def serve_hook(path: Path, classify: Classify) -> asyncio.AbstractServer:
    """The hook behind the wall cannot read the runner's token: it asks here, one JSON line
    `{cmd}` for one `{category, error}`, and the runner asks the hub."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        answer: dict[str, Any] = {"category": None, "error": "bad request"}
        try:
            line = await asyncio.wait_for(reader.readline(), 30)
            obj = json.loads(line or b"{}")
            cmd = obj.get("cmd") if isinstance(obj, dict) else None
            if isinstance(cmd, str) and cmd.strip():
                category, error = await classify(cmd)
                answer = {"category": category, "error": error}
        except (ValueError, TimeoutError, asyncio.LimitOverrunError):
            pass
        except Exception as exc:  # noqa: BLE001 - the hook gets an answer whatever happened
            answer = {"category": None, "error": type(exc).__name__}
        with contextlib.suppress(Exception):
            writer.write(json.dumps(answer).encode() + b"\n")
            await writer.drain()
        with contextlib.suppress(Exception):
            writer.close()

    import socket

    with contextlib.suppress(FileNotFoundError):
        path.unlink()  # noqa: ASYNC240 - one local unlink
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with _short(path) as short:
            sock.bind(short)
        os.chmod(path, 0o600)
        return await asyncio.start_unix_server(handle, sock=sock, limit=HOOK_LINE)
    except BaseException:
        sock.close()
        raise


def ask_hook_socket(
    sock_path: str, cmd: str, timeout: float = 45.0
) -> tuple[str | None, str | None]:
    """The hook's side: (category, error)."""
    import socket

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s, _short(sock_path) as short:
            s.settimeout(timeout)
            s.connect(short)
            s.sendall(json.dumps({"cmd": cmd}).encode() + b"\n")
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
        obj = json.loads(data or b"{}")
    except (OSError, ValueError) as exc:
        return None, type(exc).__name__
    if not isinstance(obj, dict):
        return None, "bad answer"
    category = obj.get("category")
    error = obj.get("error")
    return (str(category) if category else None), (str(error) if error else None)


# ------------------------------------------------------------------ the wrapper --
def exec_main(protect: list[str], allow: list[str], argv: list[str]) -> int:
    """`hq-runner sandbox-exec`: the wall, then the command in this same process."""
    if not argv:
        print("hq-sandbox: no command", file=sys.stderr)
        return EXIT_NO_WALL
    try:
        restrict(open_paths(protect, allow))
    except SandboxError as exc:
        print(f"hq-sandbox: {exc}", file=sys.stderr)
        return EXIT_NO_WALL
    try:
        os.execvpe(argv[0], argv, os.environ)  # noqa: S606 - the wrapper becomes the command
    except OSError as exc:
        why = errno.errorcode.get(exc.errno or 0, str(exc.errno))
        print(f"hq-sandbox: {shlex.quote(argv[0])}: {why}", file=sys.stderr)
    return 127  # the command could not be started
