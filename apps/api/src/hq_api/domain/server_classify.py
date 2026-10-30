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
Matching is case-insensitive for SQL. A pattern names what it caught; the
seal card shows it.
"""

from __future__ import annotations

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
    ("db_drop", "dropdb", re.compile(r"(?:^|[\s;&|(`/])dropdb\b")),
    ("db_drop", "flushall/flushdb", re.compile(r"\bflush(?:all|db)\b", _I)),
    ("db_drop", "dropDatabase()", re.compile(r"\.dropdatabase\s*\(", _I)),
    ("volume_delete", "docker volume rm/prune",
     re.compile(r"\bdocker\s+volume\s+(?:rm|remove|prune)\b")),
    ("volume_delete", "docker compose down -v",
     re.compile(r"\bdocker(?:-compose|\s+compose)\b[^;&|\n]*\bdown\b[^;&|\n]*\s(?:-v|--volumes)\b")),
    ("volume_delete", "docker system prune --volumes",
     re.compile(r"\bdocker\s+system\s+prune\b[^;&|\n]*--volumes\b")),
    ("volume_delete", "docker rm -v",
     re.compile(r"\bdocker\s+(?:container\s+)?rm\b[^;&|\n]*\s-[a-z]*v[a-z]*\b")),
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
    ("access_change", "/etc/ssh", re.compile(r"/etc/ssh/")),
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
            "builtin", "xargs", "stdbuf", "setsid", "chronic", "flock", "su"}  # fmt: skip
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
_REDIRECT = re.compile(r"(?:^|\s)\d?>{1,2}\s*(\S+)")


def _segments(cmd: str) -> list[list[str]]:
    """The simple commands of a command line, each as argv without prefixes."""
    out: list[list[str]] = []
    for part in _SPLIT.split(cmd):
        part = part.strip()
        if not part:
            continue
        try:
            argv = shlex.split(part, comments=False, posix=True)
        except ValueError:
            argv = part.split()
        while argv and (argv[0] in PREFIXES or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", argv[0])):
            head = argv.pop(0)
            if head == "timeout" and argv and re.fullmatch(r"[0-9.]+[smhd]?", argv[0]):
                argv.pop(0)
            while argv and argv[0].startswith("-") and head in PREFIXES:
                flag = argv.pop(0)
                takes_value = head in ("sudo", "su", "nice", "ionice", "flock")
                if takes_value and flag in ("-u", "-n", "-c", "-g") and argv:
                    argv.pop(0)
        if argv:
            out.append(argv)
    return out


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
    if (
        prog == "systemctl"
        and len(args) >= 2
        and args[0] in ("stop", "disable", "mask", "kill")
        and any(re.fullmatch(r"sshd?(?:\.service|\.socket)?", a) for a in args[1:])
    ):
        return "access_change", f"systemctl {args[0]} ssh"
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
    readers_only = bool(segments) and all(_base(a[0]) in READERS for a in segments)
    redirects = [m.group(1) for m in _REDIRECT.finditer(text)]
    for category, name, rx in TEXT_RULES:
        if not rx.search(text):
            continue
        if (
            category == "access_change"
            and readers_only
            and not any(rx.search(r) for r in redirects)
        ):
            continue  # reading a sensitive file changes nothing
        return category, name
    return None


def classify(cmd: str) -> str | None:
    """The destructive category of `cmd` (§26.3), or None: it runs free."""
    hit = classify_detail(cmd)
    return hit[0] if hit else None


def classify_path(path: str) -> tuple[str, str] | None:
    """Writing a file there (server.write): an access change for the
    server's SSH, users or firewall; anything else runs free."""
    p = (path or "").strip()
    for name, rx in SENSITIVE_WRITE_PATHS:
        if rx.search(p):
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
