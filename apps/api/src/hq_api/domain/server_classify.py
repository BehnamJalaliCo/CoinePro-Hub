"""What a command on a company server is (contract §26.3), by pattern only.

Pure functions, no database and no I/O, so the table of cases is tested on
its own and the runner's Claude Code hook gets the same answer the hub gives
an `exec` before queueing it (POST /runners/classify).

    classify(cmd)          the destructive category, or None
    classify_detail(cmd)   (category, the pattern's name), or None
    classify_path(path)    the category of writing a file there (server.write)
    is_deploy(cmd)         whether the hub counts it as a deploy (a deploy
                           freeze refuses it)

The six categories (each waits for the owner's seal when the policy lists it):

    db_drop        DROP DATABASE / TABLE / SCHEMA, TRUNCATE, dropdb,
                   FLUSHALL / FLUSHDB, dropDatabase()
    volume_delete  docker volume rm / prune, docker compose down -v,
                   docker system prune --volumes, docker rm -v, rm -r of a
                   data or volume path, find … -delete there
    backup_delete  rm of a backup path, restic forget / prune, borg delete /
                   prune, rclone delete / purge, aws s3 rm, gsutil rm
    disk_wipe      mkfs, wipefs, fdisk, sfdisk, gdisk, parted, dd of=/dev/…,
                   shred or a redirect onto a block device, blkdiscard,
                   rm -r of / or a system directory
    access_change  sshd_config, authorized_keys, sudoers, /etc/passwd and
                   /etc/shadow (written, not read), useradd / userdel /
                   usermod / passwd / chpasswd …, ufw, iptables, ip6tables,
                   nft, firewall-cmd (their read-only listings excepted),
                   stopping or disabling ssh
    server_delete  hcloud server delete, the Hetzner API's DELETE of a server

`shutdown -h now` and `poweroff` are NOT destructive (the server comes back
when the owner starts it; nothing is lost): they run free. Listing commands
(`fdisk -l`, `parted -l`, `ufw status`, `iptables -L`, `nft list …`) are
read-only and run free too.

A command is split into its simple commands (`;`, `&&`, `||`, `|`, newlines,
`$(…)` and backticks) and each is read without its prefixes (sudo, env,
nice, nohup, timeout, xargs …), so `cd /srv && sudo rm -rf data/` is caught.
A command that another one runs is read for what it runs: `bash -c '…'`,
`su -c '…'`, `eval '…'`, `flock f -c '…'`, `docker exec <ct> …`,
`docker compose exec <svc> …` and `kubectl exec … -- …`.
Matching is case-insensitive for SQL. A pattern names what it caught; the
seal card shows it.
"""

from __future__ import annotations

import posixpath
import re
import shlex

CATEGORIES = (
    "db_drop",
    "volume_delete",
    "backup_delete",
    "disk_wipe",
    "access_change",
    "server_delete",
)

# Whole-command patterns (they may span a pipeline or sit inside quotes,
# e.g. `psql -c "DROP TABLE x"` or `docker exec db redis-cli FLUSHALL`).
_I = re.IGNORECASE
TEXT_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("db_drop", "drop database/table/schema",
     re.compile(r"\bdrop\s+(?:database|table|schema)\b", _I)),
    ("db_drop", "truncate table", re.compile(r"\btruncate\s+(?:table\s+)?(?!-)[\w\"`.]+", _I)),
    ("db_drop", "dropdb", re.compile(r"(?:^|[\s;&|(`/'\"])dropdb\b")),
    ("db_drop", "flushall/flushdb", re.compile(r"\bflush(?:all|db)\b", _I)),
    ("db_drop", "dropDatabase()", re.compile(r"\.dropdatabase\s*\(", _I)),
    ("volume_delete", "docker volume rm/prune",
     re.compile(r"\b(?:docker|podman)\s+volume\s+(?:rm|remove|prune)\b")),
    ("volume_delete", "docker compose down -v",
     re.compile(r"\bdocker(?:-compose|\s+compose)\b[^;&|\n]*\bdown\b[^;&|\n]*\s(?:-v|--volumes)\b")),
    ("volume_delete", "docker system prune --volumes",
     re.compile(r"\bdocker\s+system\s+prune\b[^;&|\n]*--volumes\b")),
    ("volume_delete", "docker rm -v/--volumes",
     re.compile(r"\b(?:docker|podman)\s+(?:container\s+)?rm\b[^;&|\n]*\s(?:-[a-z]*v[a-z]*|--volumes)\b")),
    ("backup_delete", "restic forget/prune", re.compile(r"\brestic\b[^;&|\n]*\b(?:forget|prune)\b")),
    ("backup_delete", "borg delete/prune", re.compile(r"\bborg\s+(?:delete|prune)\b")),
    ("backup_delete", "rclone delete/purge",
     re.compile(r"\brclone\s+(?:delete|deletefile|purge|rmdirs)\b")),
    ("backup_delete", "object storage rm",
     re.compile(r"\b(?:aws\s+s3\s+(?:rm|rb)|gsutil\s+(?:-m\s+)?(?:rm|rb)|s3cmd\s+(?:del|rm|rb))\b")),
    ("disk_wipe", "dd of=/dev/", re.compile(r"\bdd\b[^;&|\n]*\bof=/dev/(?!null\b|zero\b|stdout\b)")),
    ("disk_wipe", "redirect onto a block device",
     re.compile(r">\s*/dev/(?:sd[a-z]|nvme\d|vd[a-z]|xvd[a-z]|hd[a-z]|md\d|mapper/)")),
    ("disk_wipe", "shred a device", re.compile(r"\bshred\b[^;&|\n]*\s/dev/")),
    ("server_delete", "hcloud server delete", re.compile(r"\bhcloud\s+server\s+delete\b")),
    ("server_delete", "Hetzner API delete server",
     re.compile(r"(?:-X\s*DELETE|--request\s+DELETE)[^;&|\n]*api\.hetzner\.cloud/v1/servers/"
                r"|api\.hetzner\.cloud/v1/servers/[^;&|\n]*(?:-X\s*DELETE|--request\s+DELETE)")),
    ("access_change", "sshd_config", re.compile(r"sshd_config")),
    ("access_change", "authorized_keys", re.compile(r"authorized_keys")),
    ("access_change", "sudoers", re.compile(r"/etc/sudoers")),
    ("access_change", "/etc/ssh", re.compile(r"/etc/ssh(?:/|(?![\w.-]))")),
    ("access_change", "/etc/passwd or /etc/shadow", re.compile(r"/etc/(?:passwd|shadow|group|gshadow)\b")),
)  # fmt: skip

# Programs: argv[0] of a simple command (its basename).
DISK_TOOLS = {
    "mkfs",
    "wipefs",
    "fdisk",
    "sfdisk",
    "gdisk",
    "sgdisk",
    "cfdisk",
    "parted",
    "blkdiscard",
}
USER_TOOLS = {
    "useradd", "userdel", "usermod", "adduser", "deluser", "passwd", "chpasswd", "chage",
    "groupadd", "groupdel", "groupmod", "gpasswd", "visudo", "addgroup", "delgroup",
}  # fmt: skip
FIREWALL_TOOLS = {"ufw", "iptables", "ip6tables", "iptables-restore", "ip6tables-restore", "nft",
                  "firewall-cmd"}  # fmt: skip
# What only reads (a sensitive path named by a reader is not a change).
READERS = {
    "cat", "less", "more", "head", "tail", "grep", "egrep", "fgrep", "rg", "ls", "stat", "wc",
    "diff", "sha256sum", "md5sum", "file", "test", "[", "awk", "sed", "sshd", "ssh-keygen",
    "getent", "id", "who", "w", "last", "lastlog", "find", "du", "df", "echo", "printf",
}  # fmt: skip
PREFIXES = {"sudo", "doas", "env", "nice", "ionice", "nohup", "time", "timeout", "exec", "command",
            "builtin", "xargs", "stdbuf", "setsid", "chronic", "flock", "su", "busybox"}  # fmt: skip
# Shells: `bash -c '<cmd>'` runs <cmd>.
SHELLS = {"bash", "sh", "dash", "zsh", "ksh", "mksh", "ash", "fish"}
_SHELL_VALUE_OPTS = ("-o", "+o", "-O", "+O", "--rcfile", "--init-file")
# `docker exec` / `docker compose exec` options that take a value (before the container).
_EXEC_VALUE_FLAGS = ("-e", "--env", "--env-file", "-u", "--user", "-w", "--workdir",
                     "--detach-keys", "--index")  # fmt: skip
# Global options of docker / podman / compose that take a value (before the verb).
_CLI_VALUE_FLAGS = ("-H", "--host", "-c", "--context", "--config", "-l", "--log-level", "-f",
                    "--file", "-p", "--project-name", "--env-file", "--profile",
                    "--project-directory", "--ansi", "--parallel", "--progress")  # fmt: skip
# How deep a command inside a command inside … is read.
_DEPTH = 6
# rm -r of these is the disk (or the system) gone.
SYSTEM_DIRS = re.compile(
    r"^(?:/|/\*|~|~/|~/\*|\$HOME/?|/(?:bin|boot|etc|home|lib|lib64|opt|root|sbin|srv|usr|var)/?\*?)$"
)
DATA_PATHS = re.compile(
    r"^/var/lib/docker(?:/|$)|^/var/lib/(?:postgresql|mysql|mariadb|redis|mongodb|clickhouse|"
    r"timescaledb|influxdb|elasticsearch)(?:/|$)|(?:^|/)(?:data|pgdata|pg_data|postgres[-_]data|"
    r"db[-_]data|mysql[-_]data|redis[-_]data|volumes?|_data)(?:/|$|\*)"
)
BACKUP_PATHS = re.compile(
    r"backup|(?:^|/)bak(?:/|$)|\.bak\b|\.hq-bak\b|(?:^|/)dumps?(?:/|$)|\.dump\b|snapshots?(?:/|$)"
    r"|\.sql(?:\.gz|\.zst|\.xz)?$|\.tar\.(?:gz|zst|xz)$",
    _I,
)
SENSITIVE_WRITE_PATHS = (
    ("sshd_config", re.compile(r"sshd_config")),
    ("authorized_keys", re.compile(r"authorized_keys")),
    ("sudoers", re.compile(r"/etc/sudoers")),
    ("/etc/ssh", re.compile(r"^/etc/ssh/")),
    ("/etc/passwd or /etc/shadow", re.compile(r"^/etc/(?:passwd|shadow|group|gshadow)$")),
    ("firewall rules", re.compile(r"^/etc/(?:ufw|iptables|nftables)(?:/|\.conf$)")),
)
_SPLIT = re.compile(r"\|\||&&|[;|\n&]|\$\(|`|\)")
# `2>&1`, `>&2`, `<&0`: a descriptor copy, not a command separator and not a file.
_FD_DUP = re.compile(r"\d*[<>]&\d+-?")
_REDIRECT = re.compile(r"(?:^|\s)\d?>{1,2}\s*(\S+)")


_VALUE_FLAGS: dict[str, tuple[str, ...]] = {
    "sudo": ("-u", "-g", "-C", "-h", "-p", "-U", "-r", "-t", "-D", "-R", "--user", "--group",
             "--host", "--prompt", "--chroot", "--chdir", "--close-from", "--role", "--type",
             "--other-user"),
    "doas": ("-u", "-C"),
    "nice": ("-n",),
    "ionice": ("-c", "-n", "-t", "-p"),
    "flock": ("-w", "--timeout", "--wait", "-E", "--conflict-exit-code"),
    "timeout": ("-s", "--signal", "-k", "--kill-after"),
    "env": ("-u", "--unset", "-C", "--chdir"),
    "xargs": ("-I", "-n", "-P", "-d", "-a", "-L", "-s", "-E", "--max-args", "--max-procs",
              "--delimiter", "--arg-file", "--max-lines", "--max-chars"),
    "stdbuf": ("-i", "-o", "-e"),
}  # fmt: skip
_SU_COMMAND = ("-c", "--command", "--session-command")
_SYSTEMCTL_VALUE_FLAGS = ("-H", "--host", "-M", "--machine", "-s", "--signal", "-p",
                          "--property", "-t", "--type", "--state", "-n", "--lines", "-o",
                          "--output", "--kill-whom", "--root")  # fmt: skip
_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")
_DURATION = re.compile(r"[0-9.]+[smhd]?")


def _split(part: str) -> list[str]:
    try:
        return shlex.split(part, comments=False, posix=True)
    except ValueError:
        # An unbalanced quote (a quoted `;` split the line): read the words without their quotes.
        return [w for w in (t.strip("'\"") for t in part.split()) if w]


def _segments(cmd: str, depth: int = 0) -> list[list[str]]:
    """The simple commands of a command line, each as argv without prefixes."""
    out: list[list[str]] = []
    for part in _SPLIT.split(_FD_DUP.sub(" ", cmd)):
        part = part.strip()
        if part:
            out.extend(_unwrap(_split(part), depth))
    return out


def _inner(code: str, depth: int) -> list[list[str]]:
    """The simple commands of a command given as text (`bash -c '…'`, `eval …`)."""
    if not code.strip() or depth >= _DEPTH:
        return []
    return _segments(code, depth + 1)


def _value_of(args: list[str], names: tuple[str, ...]) -> list[str] | None:
    """The value of the first of these options in args (`-c x`, `--command=x`), or None."""
    for i, a in enumerate(args):
        if a in names:
            return args[i + 1 : i + 2]
        for n in names:
            if n.startswith("--") and a.startswith(n + "="):
                return [a[len(n) + 1 :]]
    return None


def _shell_command(args: list[str]) -> list[str] | None:
    """What `bash [opts] -c '<cmd>' [$0 $1 …]` runs (with its arguments), or None (a script)."""
    i = 0
    while i < len(args):
        a = args[i]
        if a in _SHELL_VALUE_OPTS:
            i += 2
            continue
        if a == "-c" or (a.startswith("-") and not a.startswith("--") and "c" in a[1:]):
            return args[i + 1 :]
        if a.startswith(("-", "+")):
            i += 1
            continue
        return None
    return None


def _exec_tail(argv: list[str]) -> list[str] | None:
    """The command `docker exec <ct> …`, `docker compose exec <svc> …` or
    `kubectl exec … -- …` runs inside the container, or None."""
    name = _base(argv[0])
    args = argv[1:]
    if name == "kubectl":
        if "exec" in args and "--" in args:
            return args[args.index("--") + 1 :]
        return None
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in _CLI_VALUE_FLAGS else 1
    rest = args[i:]
    if name in ("docker", "podman") and rest[:1] in (["compose"], ["container"]):
        rest = rest[1:]
        i = 0
        while i < len(rest) and rest[i].startswith("-"):
            i += 2 if rest[i] in _CLI_VALUE_FLAGS else 1
        rest = rest[i:]
    if rest[:1] != ["exec"]:
        return None
    rest = rest[1:]
    i = 0
    while i < len(rest) and rest[i].startswith("-"):
        if rest[i] == "--":
            i += 1
            break
        i += 2 if rest[i] in _EXEC_VALUE_FLAGS else 1
    return rest[i + 1 :] if i < len(rest) else []


def _unwrap(argv: list[str], depth: int) -> list[list[str]]:
    """argv without its prefixes; a command another one runs is read for what it runs."""
    argv = list(argv)
    while argv:
        name = _base(argv[0])
        if _ASSIGN.fullmatch(argv[0]):
            argv.pop(0)
            continue
        if name in SHELLS:
            inner = _shell_command(argv[1:])
            if inner is None:
                return [argv]
            # The code, then its arguments ($0 $1 …) as the words they are.
            return _inner(" ".join(inner[:1] + [shlex.quote(w) for w in inner[1:]]), depth)
        if name == "eval":
            return _inner(" ".join(argv[1:]), depth)
        if name in ("docker", "podman", "docker-compose", "kubectl"):
            tail = _exec_tail(argv)
            if tail is None:
                return [argv]
            argv = tail
            continue
        if name not in PREFIXES:
            return [argv]
        argv.pop(0)
        if name == "su":
            # `su [-] [user] -c '<cmd>'` runs <cmd>; a plain `su` runs nothing to read.
            value = _value_of(argv, _SU_COMMAND)
            return _inner(value[0], depth) if value else []
        while argv and argv[0].startswith("-"):
            flag = argv.pop(0)
            if flag == "--":
                break
            # Only these flags take a value (`sudo -n` does not: it means non-interactive).
            if flag in _VALUE_FLAGS.get(name, ()) and argv:
                argv.pop(0)
        if name == "timeout" and argv and _DURATION.fullmatch(argv[0]):
            argv.pop(0)  # the duration
        if name == "flock" and argv:
            argv.pop(0)  # the lock file or descriptor
            value = _value_of(argv[:2], ("-c", "--command"))
            if value is not None:
                return _inner(value[0], depth) if value else []
    return []


def _base(arg: str) -> str:
    return arg.rsplit("/", 1)[-1]


def _recursive(flags: list[str]) -> bool:
    return any(
        f in ("--recursive", "-r", "-R")
        or (f.startswith("-") and not f.startswith("--") and ("r" in f or "R" in f))
        for f in flags
    )


def _rm(argv: list[str]) -> tuple[str, str] | None:
    flags = [a for a in argv[1:] if a.startswith("-") and a != "--"]
    paths = [a for a in argv[1:] if not a.startswith("-")]
    rec = _recursive(flags)
    for p in paths:
        if rec and SYSTEM_DIRS.match(p.rstrip("/") or "/"):
            return "disk_wipe", "rm -r of a system directory"
        if BACKUP_PATHS.search(p):
            return "backup_delete", "rm of a backup path"
        if rec and DATA_PATHS.search(p):
            return "volume_delete", "rm -r of a data or volume path"
    return None


def _find_delete(argv: list[str]) -> tuple[str, str] | None:
    if "-delete" not in argv and not ("-exec" in argv and "rm" in argv):
        return None
    paths = [a for a in argv[1:] if not a.startswith("-")][:1]
    for p in paths:
        if BACKUP_PATHS.search(p):
            return "backup_delete", "find -delete in a backup path"
        if DATA_PATHS.search(p):
            return "volume_delete", "find -delete in a data path"
        if SYSTEM_DIRS.match(p.rstrip("/") or "/"):
            return "disk_wipe", "find -delete of a system directory"
    return None


def _firewall_read_only(prog: str, a: list[str]) -> bool:
    """A firewall tool that only lists (ufw status, iptables -L, nft list …)."""
    if prog == "ufw":
        return bool(a) and a[0] in ("status", "show", "version", "app")
    if prog in ("iptables", "ip6tables"):
        listing = ("-L", "--list", "-S", "--list-rules", "-C", "--check", "-V", "--version")
        return any(x in listing or x.startswith("-L") for x in a)
    if prog == "nft":
        return bool(a) and a[0] in ("list", "-a", "--version", "-v") and "flush" not in a
    if prog == "firewall-cmd":
        return any(x.startswith(("--list", "--get", "--query", "--state")) for x in a)
    return False


def _in_place(argv: list[str]) -> bool:
    """`sed -i`, `perl -i`: the named files are written, not read."""
    return _base(argv[0]) in ("sed", "perl") and any(
        a == "--in-place" or a.startswith("--in-place=") or re.fullmatch(r"-[A-Za-z]*i\S*", a)
        for a in argv[1:]
    )


_SSH_UNIT = re.compile(r"sshd?(?:\.service|\.socket)?")


def _systemctl_words(args: list[str]) -> list[str]:
    """systemctl's verb and units, without its options (`systemctl --now disable ssh`)."""
    words: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in _SYSTEMCTL_VALUE_FLAGS:
            i += 2
            continue
        if not a.startswith("-"):
            words.append(a)
        i += 1
    return words


def _writes(argv: list[str]) -> bool:
    """A reader that writes or deletes: `sed -i`, `find … -delete` or `find … -exec`."""
    if _in_place(argv):
        return True
    return _base(argv[0]) == "find" and any(
        a in ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf",
              "-fls")
        for a in argv[1:]
    )  # fmt: skip


def _program(argv: list[str]) -> tuple[str, str] | None:
    prog = _base(argv[0])
    args = argv[1:]
    if prog in ("rm", "unlink", "rmdir", "srm"):
        return _rm(argv)
    if prog == "find":
        return _find_delete(argv)
    if prog.startswith("mkfs") or prog in ("wipefs", "blkdiscard"):
        return "disk_wipe", prog
    if prog in ("fdisk", "sfdisk", "gdisk", "sgdisk", "cfdisk"):
        if any(a in ("-l", "--list", "-s", "--show-size", "-v", "--version", "-p") for a in args):
            return None
        return "disk_wipe", prog
    if prog == "parted":
        if "-l" in args or "--list" in args or (args and args[-1] in ("print", "p")):
            return None
        return "disk_wipe", "parted"
    if prog in USER_TOOLS:
        if prog == "passwd" and any(a in ("-S", "--status") for a in args):
            return None
        return "access_change", prog
    if prog in FIREWALL_TOOLS:
        return None if _firewall_read_only(prog, args) else ("access_change", prog)
    if prog == "systemctl":
        words = _systemctl_words(args)
        if (
            len(words) >= 2
            and words[0] in ("stop", "disable", "mask", "kill")
            and any(_SSH_UNIT.fullmatch(a) for a in words[1:])
        ):
            return "access_change", f"systemctl {words[0]} ssh"
    if prog == "service" and len(args) >= 2 and _SSH_UNIT.fullmatch(args[0]) and args[1] == "stop":
        return "access_change", "service ssh stop"
    if argv[0].startswith("/etc/init.d/") and _SSH_UNIT.fullmatch(prog) and args[:1] == ["stop"]:
        return "access_change", "init.d ssh stop"
    if prog == "docker" and args[:2] == ["volume", "rm"]:
        return "volume_delete", "docker volume rm"
    return None


def classify_detail(cmd: str) -> tuple[str, str] | None:
    """(category, pattern) of the first destructive part of `cmd`, or None."""
    if not cmd or not cmd.strip():
        return None
    text = cmd[:100_000]
    segments = _segments(text)
    for argv in segments:
        hit = _program(argv)
        if hit is not None:
            return hit
    readers_only = bool(segments) and all(
        _base(a[0]) in READERS and not _writes(a) for a in segments
    )
    # The text as written, with its paths' `//` and `/./` folded, and as the commands it runs
    # (`bash -c "dropdb x"` reads as `dropdb x`).
    texts = [text, _fold(text), "\n".join(" ".join(a) for a in segments)]
    redirects = [m.group(1) for t in texts[:2] for m in _REDIRECT.finditer(_FD_DUP.sub(" ", t))]
    for category, name, rx in TEXT_RULES:
        if not any(rx.search(t) for t in texts):
            continue
        if (
            category == "access_change"
            and readers_only
            and not any(rx.search(r) for r in redirects)
        ):
            continue  # reading a sensitive file changes nothing
        return category, name
    return None


def _fold(text: str) -> str:
    """`/etc//passwd` and `/etc/./shadow` as `/etc/passwd` and `/etc/shadow` (URLs kept)."""
    return re.sub(r"(?<![:/])/(?:\.?/)+", "/", text)


def classify(cmd: str) -> str | None:
    """The destructive category of `cmd` (§26.3), or None: it runs free."""
    hit = classify_detail(cmd)
    return hit[0] if hit else None


def classify_path(path: str) -> tuple[str, str] | None:
    """Writing a file there (server.write): an access change for the
    server's SSH, users or firewall; anything else runs free."""
    p = (path or "").strip()
    paths = [p]
    if p:
        # `/etc//passwd`, `/etc/./shadow` and `/etc/ssh/../passwd` are the same files.
        norm = posixpath.normpath(p)
        paths.append("/" + norm.lstrip("/") if norm.startswith("/") else norm)
    for name, rx in SENSITIVE_WRITE_PATHS:
        if any(rx.search(x) for x in paths):
            return "access_change", name
    return None


# ------------------------------------------------------------------ deploys --
# Units that are the server's own plumbing, not an application: restarting
# them is not a deploy (stopping ssh is an access change, above).
SYSTEM_UNITS = re.compile(
    r"^(?:ssh|sshd|cron|crond|docker|containerd|systemd-[\w-]+|ufw|fail2ban|networking|chrony|"
    r"chronyd|ntp|rsyslog|snapd|unattended-upgrades|getty@[\w-]+|dbus|polkit)(?:\.service)?$"
)
DEPLOY_TEXT = (
    re.compile(r"\bdocker(?:-compose|\s+compose)\b[^;&|\n]*\b(?:up|pull|build|restart|create)\b"),
    re.compile(r"\bdocker\s+(?:stack\s+deploy|service\s+update)\b"),
    re.compile(r"\bgit\b[^;&|\n]*\b(?:pull|checkout|switch|reset\s+--hard)\b"),
    re.compile(r"(?:^|[\s/;&|])(?:deploy|release|rollout|redeploy)[\w.-]*\.sh\b"),
    re.compile(r"\bmake\s+(?:deploy|release|up|rollout)\b"),
    re.compile(r"\bkubectl\s+(?:apply|rollout|set\s+image|replace)\b"),
    re.compile(r"\bhelm\s+(?:upgrade|install|rollback)\b"),
    re.compile(r"\bansible-playbook\b"),
    re.compile(r"\bpm2\s+(?:restart|reload|deploy|start)\b"),
    re.compile(r"\b(?:npm|pnpm|yarn)\s+(?:run\s+)?deploy\b"),
    re.compile(r"\balembic\s+upgrade\b|\bmanage\.py\s+migrate\b"),
)


def is_deploy(cmd: str) -> bool:
    """Whether the hub counts `cmd` as a deploy (contract §26.3: a deploy
    freeze refuses it): docker compose up / pull / build / restart, git pull
    (and checkout / reset --hard) of a working tree, systemctl restart /
    reload / start of an application unit, deploy scripts and tools,
    database migrations."""
    if not cmd or not cmd.strip():
        return False
    text = cmd[:100_000]
    if any(rx.search(text) for rx in DEPLOY_TEXT):
        return True
    starts = ("restart", "reload", "start", "try-restart", "reload-or-restart")
    for argv in _segments(text):
        prog = _base(argv[0])
        args = [a for a in argv[1:] if not a.startswith("-")]
        if (
            prog == "systemctl"
            and args
            and args[0] in starts
            and any(not SYSTEM_UNITS.match(u) for u in args[1:])
        ):
            return True
        if (
            prog == "service"
            and len(argv) >= 3
            and argv[2] in ("restart", "reload", "start")
            and not SYSTEM_UNITS.match(argv[1])
        ):
            return True
    return False
