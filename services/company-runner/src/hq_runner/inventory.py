"""The `map` job: the server's inventory in the exact shape of contract §26.5,
collected with fixed read-only commands only. Every probe tolerates a missing
tool, a missing permission or a timeout: its part is then empty.

    {os, kernel, uptime_s, cpu: {cores, load1},
     memory: {total_mb, used_mb, swap_total_mb, swap_used_mb},
     disks: [{mount, total_gb, used_gb}],
     containers: [{name, image, state, health|null, project|null}],
     compose: [{project, path, services: [..]}],
     systemd: [{unit, state, timer: bool, next_at|null}],
     cron: [{user, schedule, cmd_masked}],
     ports: [{port, proto, bind, process, public: bool}],
     repos: [{path, remote, branch, dirty: bool, last_commit_at}],
     automations: [{kind: "n8n"|"cron"|"systemd"|"other", name, active: bool, detail}],
     sites: [{host, upstream}]}
"""

from __future__ import annotations

import asyncio
import contextlib
import getpass
import ipaddress
import json
import os
import platform
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hq_runner.jobs import JobContext, JobResult
from hq_runner.mask import Masker
from hq_runner.proc import capture

CaptureFn = Callable[[list[str]], Awaitable[str | None]]

MAP_KEYS = (
    "user",
    "os",
    "kernel",
    "uptime_s",
    "cpu",
    "memory",
    "disks",
    "containers",
    "compose",
    "systemd",
    "cron",
    "ports",
    "repos",
    "automations",
    "sites",
)
SKIP_DIRS = {
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".cache",
    "site-packages",
    "dist",
    "build",
}
LANG_ENV = {"LC_ALL": "C", "LANG": "C"}


# -- parsers (pure) -----------------------------------------------------------------
def parse_os_release(text: str) -> str | None:
    values = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"')
    return values.get("PRETTY_NAME") or values.get("NAME")


def parse_free(text: str) -> dict[str, int] | None:
    mem = swap = None
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] == "Mem:" and len(parts) >= 3:
            mem = (int(parts[1]), int(parts[2]))
        elif parts and parts[0] == "Swap:" and len(parts) >= 3:
            swap = (int(parts[1]), int(parts[2]))
    if mem is None:
        return None
    s = swap or (0, 0)
    return {"total_mb": mem[0], "used_mb": mem[1], "swap_total_mb": s[0], "swap_used_mb": s[1]}


def parse_meminfo(text: str) -> dict[str, int]:
    kb: dict[str, int] = {}
    for line in text.splitlines():
        m = re.match(r"(\w+):\s+(\d+)", line)
        if m:
            kb[m.group(1)] = int(m.group(2))
    total = kb.get("MemTotal", 0)
    avail = kb.get("MemAvailable", kb.get("MemFree", 0))
    return {
        "total_mb": total // 1024,
        "used_mb": max(0, total - avail) // 1024,
        "swap_total_mb": kb.get("SwapTotal", 0) // 1024,
        "swap_used_mb": max(0, kb.get("SwapTotal", 0) - kb.get("SwapFree", 0)) // 1024,
    }


def parse_df(text: str) -> list[dict[str, Any]]:
    """`df -P -B1` output."""
    out = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6 or not parts[1].isdigit():
            continue
        total, used, mount = int(parts[1]), int(parts[2]), " ".join(parts[5:])
        if total == 0 or mount.startswith(("/snap", "/boot/efi", "/run", "/dev", "/sys", "/proc")):
            continue
        out.append(
            {"mount": mount, "total_gb": round(total / 1e9, 1), "used_gb": round(used / 1e9, 1)}
        )
    return out


def _labels(raw: str) -> dict[str, str]:
    out = {}
    for item in raw.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def parse_docker_ps(text: str) -> list[dict[str, Any]]:
    """`docker ps -a --format '{{json .}}'`: one object per line. `service`
    (the compose service) is kept for the compose list and dropped afterwards."""
    out = []
    for line in text.splitlines():
        try:
            c = json.loads(line)
        except ValueError:
            continue
        status = str(c.get("Status", ""))
        health = None
        m = re.search(r"\((healthy|unhealthy|health: starting)\)", status)
        if m:
            health = "starting" if "starting" in m.group(1) else m.group(1)
        labels = _labels(str(c.get("Labels", "")))
        out.append(
            {
                "name": str(c.get("Names", "")).split(",")[0],
                "image": str(c.get("Image", "")),
                "state": str(c.get("State", "")).lower()
                or ("running" if status.startswith("Up") else "exited"),
                "health": health,
                "project": labels.get("com.docker.compose.project") or None,
                "service": labels.get("com.docker.compose.service"),
            }
        )
    return out


def parse_compose_ls(text: str, containers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        items = json.loads(text)
    except ValueError:
        return []
    out = []
    for it in items if isinstance(items, list) else []:
        project = str(it.get("Name", ""))
        files = str(it.get("ConfigFiles", "")).split(",")
        services = sorted(
            {c["service"] for c in containers if c["project"] == project and c.get("service")}
        )
        out.append(
            {
                "project": project,
                "path": files[0] if files and files[0] else None,
                "services": services,
            }
        )
    return out


def _usec_to_iso(usec: Any) -> str | None:
    try:
        val = int(usec)
    except (TypeError, ValueError):
        return None
    if val <= 0:
        return None
    return datetime.fromtimestamp(val / 1e6, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_units(text: str) -> list[dict[str, Any]]:
    """`systemctl list-units --type=service --no-legend --plain`: UNIT LOAD ACTIVE SUB DESC."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0].endswith(".service"):
            out.append({"unit": parts[0], "state": parts[3], "timer": False, "next_at": None})
    return out


def parse_timers_json(text: str) -> list[dict[str, Any]]:
    try:
        items = json.loads(text)
    except ValueError:
        return []
    out = []
    for t in items if isinstance(items, list) else []:
        unit = t.get("unit")
        if not unit:
            continue
        out.append(
            {
                "unit": unit,
                "state": "active",
                "timer": True,
                "next_at": _usec_to_iso(t.get("next")),
                "activates": t.get("activates"),
            }
        )
    return out


def parse_timers_text(text: str) -> list[dict[str, Any]]:
    out = []
    for line in text.splitlines():
        parts = line.split()
        timers = [i for i, p in enumerate(parts) if p.endswith(".timer")]
        if timers:
            i = timers[-1]
            out.append(
                {
                    "unit": parts[i],
                    "state": "active",
                    "timer": True,
                    "next_at": None,
                    "activates": parts[i + 1] if i + 1 < len(parts) else None,
                }
            )
    return out


_CRON_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*=")


def parse_crontab(
    text: str, user: str, masker: Masker, *, system: bool = False
) -> list[dict[str, Any]]:
    """A user crontab, or a system one (/etc/crontab, /etc/cron.d) with its user field.
    Variable lines are skipped (they are not jobs and may hold secrets)."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or _CRON_ENV.match(s):
            continue
        parts = s.split()
        if parts[0].startswith("@"):
            schedule, rest = parts[0], parts[1:]
        elif len(parts) >= 6:
            schedule, rest = " ".join(parts[:5]), parts[5:]
        else:
            continue
        owner = user
        if system and rest:
            owner, rest = rest[0], rest[1:]
        if not rest:
            continue
        out.append({"user": owner, "schedule": schedule, "cmd_masked": masker.text(" ".join(rest))})
    return out


def _bind_public(addr: str) -> bool:
    if addr in ("*", "0.0.0.0", "::", "[::]"):
        return True
    with contextlib.suppress(ValueError):
        ip = ipaddress.ip_address(addr.strip("[]"))
        return not (ip.is_loopback or ip.is_private or ip.is_link_local)
    return False


def parse_ss(text: str) -> list[dict[str, Any]]:
    """`ss -ltunpH`: Netid State Recv-Q Send-Q Local Peer [Process]."""
    out = []
    seen = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        proto = parts[0].lower()
        if proto not in ("tcp", "udp"):
            continue
        local = parts[4]
        bind, _, port_s = local.rpartition(":")
        if not port_s.isdigit():
            continue
        bind = bind.split("%")[0].strip("[]") or "*"
        if bind.startswith("::ffff:"):
            bind = bind[7:]
        m = re.search(r'users:\(\("([^"]+)"', line)
        key = (proto, bind, int(port_s))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "port": int(port_s),
                "proto": proto,
                "bind": bind,
                "process": m.group(1) if m else None,
                "public": _bind_public(bind),
            }
        )
    return sorted(out, key=lambda p: (p["port"], p["proto"], p["bind"]))


def parse_nginx(text: str) -> list[dict[str, Any]]:
    """server blocks: each server_name with the block's first proxy_pass (or root)."""
    out = []
    text = re.sub(r"#[^\n]*", "", text)
    for block in _blocks(text, "server"):
        names: list[str] = []
        for m in re.finditer(r"\bserver_name\s+([^;]+);", block):
            names += [n for n in m.group(1).split() if n not in ("_", '""', "localhost")]
        up = re.search(r"\bproxy_pass\s+([^;]+);", block) or re.search(r"\broot\s+([^;]+);", block)
        upstream = up.group(1).strip() if up else None
        out += [{"host": n, "upstream": upstream} for n in names]
    return out


def _blocks(text: str, keyword: str) -> list[str]:
    out = []
    for m in re.finditer(rf"\b{keyword}\s*\{{", text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        out.append(text[m.end() : i - 1])
    return out


def parse_caddyfile(text: str) -> list[dict[str, Any]]:
    """Top-level site blocks `host[, host] {` with their first reverse_proxy."""
    out = []
    depth = 0
    current: list[str] = []
    upstream: str | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip() if not raw.strip().startswith("#") else ""
        if not line:
            continue
        if depth == 0 and line.endswith("{"):
            head = line[:-1].strip()
            current = (
                []
                if head.startswith("(") or not head
                else [
                    h.strip().removeprefix("https://").removeprefix("http://")
                    for h in head.split(",")
                    if h.strip()
                ]
            )
            upstream = None
        elif depth >= 1 and upstream is None:
            m = re.match(r"reverse_proxy\s+(?:\S*\s+)?([^\s{]+)", line)
            if m and not m.group(1).startswith("/"):
                upstream = m.group(1)
            elif m:
                parts = line.split()
                upstream = parts[2] if len(parts) > 2 else None
        depth += line.count("{") - line.count("}")
        if depth == 0 and current:
            out += [
                {"host": h, "upstream": upstream} for h in current if h and not h.startswith(":")
            ]
            current = []
    return out


# -- collector ------------------------------------------------------------------------
class Inventory:
    def __init__(
        self,
        masker: Masker,
        *,
        run: CaptureFn | None = None,
        home: Path | None = None,
        root: Path = Path("/"),
    ) -> None:
        self.masker = masker
        self.run = run or (
            lambda argv: capture(argv, env={**os.environ, **LANG_ENV, "GIT_OPTIONAL_LOCKS": "0"})
        )
        self.home = home or Path.home()
        self.root = root

    def _read(self, rel: str) -> str | None:
        try:
            return (self.root / rel.lstrip("/")).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    async def collect(self) -> dict[str, Any]:
        containers = await self.containers()
        compose_raw = await self.run(["docker", "compose", "ls", "-a", "--format", "json"])
        compose = parse_compose_ls(compose_raw, containers) if compose_raw else []
        systemd = await self.systemd()
        cron = await self.cron()
        repos = await self.repos()
        result: dict[str, Any] = {
            "user": getpass.getuser(),
            "os": parse_os_release(self._read("/etc/os-release") or "") or platform.system(),
            "kernel": platform.release(),
            "uptime_s": self.uptime(),
            "cpu": self.cpu(),
            "memory": await self.memory(),
            "disks": await self.disks(),
            "containers": [
                {k: c[k] for k in ("name", "image", "state", "health", "project")}
                for c in containers
            ],
            "compose": compose,
            "systemd": [{k: s[k] for k in ("unit", "state", "timer", "next_at")} for s in systemd],
            "cron": cron,
            "ports": await self.ports(),
            "repos": repos,
            "automations": self.automations(containers, systemd, cron),
            "sites": self.sites(repos),
        }
        return result

    def uptime(self) -> int | None:
        text = self._read("/proc/uptime")
        try:
            return int(float(text.split()[0])) if text else None
        except (ValueError, IndexError):
            return None

    def cpu(self) -> dict[str, Any]:
        load = None
        text = self._read("/proc/loadavg")
        with contextlib.suppress(ValueError, IndexError, AttributeError):
            load = float(text.split()[0]) if text else None
        return {"cores": os.cpu_count(), "load1": load}

    async def memory(self) -> dict[str, int] | None:
        out = await self.run(["free", "-m"])
        parsed = parse_free(out) if out else None
        if parsed is None:
            text = self._read("/proc/meminfo")
            parsed = parse_meminfo(text) if text else None
        return parsed

    async def disks(self) -> list[dict[str, Any]]:
        out = await self.run(
            [
                "df",
                "-P",
                "-B1",
                "-x",
                "tmpfs",
                "-x",
                "devtmpfs",
                "-x",
                "squashfs",
                "-x",
                "overlay",
                "-x",
                "efivarfs",
            ]
        )
        return parse_df(out) if out else []

    async def containers(self) -> list[dict[str, Any]]:
        out = await self.run(["docker", "ps", "-a", "--no-trunc", "--format", "{{json .}}"])
        return parse_docker_ps(out) if out else []

    async def systemd(self) -> list[dict[str, Any]]:
        units = await self.run(
            [
                "systemctl",
                "list-units",
                "--type=service",
                "--state=running,failed",
                "--no-legend",
                "--plain",
                "--no-pager",
            ]
        )
        out = parse_units(units) if units else []
        timers = await self.run(
            ["systemctl", "list-timers", "--all", "--no-pager", "--output=json"]
        )
        parsed = parse_timers_json(timers) if timers else []
        if not timers:
            text = await self.run(
                ["systemctl", "list-timers", "--all", "--no-legend", "--plain", "--no-pager"]
            )
            parsed = parse_timers_text(text) if text else []
        return out + parsed

    async def cron(self) -> list[dict[str, Any]]:
        user = getpass.getuser()
        out: list[dict[str, Any]] = []
        mine = await self.run(["crontab", "-l"])
        if mine:
            out += parse_crontab(mine, user, self.masker)
        system = self._read("/etc/crontab")
        if system:
            out += parse_crontab(system, "root", self.masker, system=True)
        cron_d = self.root / "etc" / "cron.d"
        with contextlib.suppress(OSError):
            for f in sorted(cron_d.iterdir()):
                if f.is_file() and not f.name.startswith("."):
                    with contextlib.suppress(OSError):
                        out += parse_crontab(
                            f.read_text(errors="replace"), "root", self.masker, system=True
                        )
        return out

    async def ports(self) -> list[dict[str, Any]]:
        out = await self.run(["ss", "-ltunpH"])
        return parse_ss(out) if out else []

    def find_repos(self, max_depth: int = 3) -> list[Path]:
        found: list[Path] = []

        def walk(d: Path, depth: int) -> None:
            if (d / ".git").exists():
                found.append(d)
                return
            if depth >= max_depth:
                return
            with contextlib.suppress(OSError):
                for child in sorted(d.iterdir()):
                    if child.name.startswith(".") or child.name in SKIP_DIRS:
                        continue
                    if child.is_dir() and not child.is_symlink():
                        walk(child, depth + 1)

        walk(self.home, 0)
        return found[:100]

    async def repo(self, path: Path) -> dict[str, Any]:
        p = str(path)
        remote = await self.run(["git", "-C", p, "remote", "get-url", "origin"])
        if remote is None:
            remotes = await self.run(["git", "-C", p, "remote", "-v"])
            remote = remotes.split()[1] if remotes and len(remotes.split()) > 1 else None
        branch = await self.run(["git", "-C", p, "branch", "--show-current"])
        status = await self.run(
            ["git", "-C", p, "status", "--porcelain", "--untracked-files=normal"]
        )
        last = await self.run(["git", "-C", p, "log", "-1", "--format=%cI"])
        return {
            "path": p,
            "remote": self.masker.text(remote.strip()) if remote else None,
            "branch": (branch.strip() or None) if branch else None,
            "dirty": bool(status and status.strip()),
            "last_commit_at": (last.strip() or None) if last else None,
        }

    async def repos(self) -> list[dict[str, Any]]:
        return list(await asyncio.gather(*(self.repo(p) for p in self.find_repos())))

    def n8n_processes(self) -> list[str]:
        out = []
        proc = self.root / "proc"
        with contextlib.suppress(OSError):
            for d in proc.iterdir():
                if not d.name.isdigit():
                    continue
                with contextlib.suppress(OSError):
                    cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
                    if re.search(r"(^|/|\s)n8n(\s|$)", cmd):
                        out.append(d.name)
        return out

    def automations(
        self,
        containers: list[dict[str, Any]],
        systemd: list[dict[str, Any]],
        cron: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for c in containers:
            image = c["image"].lower()
            if "n8n" in image:
                out.append(
                    {
                        "kind": "n8n",
                        "name": c["name"],
                        "active": c["state"] == "running",
                        "detail": c["image"],
                    }
                )
            elif re.search(r"(celery.*beat|beat|scheduler|cron)", c["name"].lower()):
                out.append(
                    {
                        "kind": "other",
                        "name": c["name"],
                        "active": c["state"] == "running",
                        "detail": c["image"],
                    }
                )
        if not any(a["kind"] == "n8n" for a in out):
            pids = self.n8n_processes()
            if pids:
                out.append(
                    {"kind": "n8n", "name": "n8n", "active": True, "detail": f"process {pids[0]}"}
                )
        for t in systemd:
            if t["timer"]:
                out.append(
                    {
                        "kind": "systemd",
                        "name": t["unit"],
                        "active": True,
                        "detail": t.get("activates"),
                    }
                )
        for j in cron:
            out.append(
                {
                    "kind": "cron",
                    "name": j["cmd_masked"][:80],
                    "active": True,
                    "detail": j["schedule"],
                }
            )
        return out

    def sites(self, repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        candidates: list[tuple[str, Path]] = []
        for d in ("etc/nginx/sites-enabled", "etc/nginx/conf.d"):
            with contextlib.suppress(OSError):
                candidates += [
                    ("nginx", f) for f in sorted((self.root / d).iterdir()) if f.is_file()
                ]
        candidates.append(("caddy", self.root / "etc/caddy/Caddyfile"))
        for r in repos:
            base = Path(r["path"])
            for sub in (base, *(base / s for s in ("caddy", "nginx", "deploy", "infra", "docker"))):
                candidates.append(("caddy", sub / "Caddyfile"))
                with contextlib.suppress(OSError):
                    candidates += [
                        ("nginx", f)
                        for f in sorted(sub.glob("*.conf"))
                        if "nginx" in str(f).lower()
                    ]
        seen = set()
        for kind, f in candidates:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for s in parse_caddyfile(text) if kind == "caddy" else parse_nginx(text):
                key = (s["host"], s["upstream"])
                if key not in seen:
                    seen.add(key)
                    out.append(s)
        return out


async def run_map(ctx: JobContext, inventory: Inventory | None = None) -> JobResult:
    inv = inventory or Inventory(ctx.masker)
    data = await inv.collect()
    summary = (
        f"نقشه‌ی سرور: {len(data['containers'])} کانتینر، {len(data['repos'])} ریپو، "
        f"{len(data['ports'])} پورت باز."
    )
    return JobResult(0, summary, output={"map": data})
