from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from conftest import run

from hq_runner.inventory import (
    MAP_KEYS,
    Inventory,
    parse_caddyfile,
    parse_crontab,
    parse_nginx,
    parse_ss,
)
from hq_runner.mask import Masker

SHAPE = {
    "cpu": {"cores", "load1"},
    "memory": {"total_mb", "used_mb", "swap_total_mb", "swap_used_mb"},
    "disks": {"mount", "total_gb", "used_gb"},
    "containers": {"name", "image", "state", "health", "project"},
    "compose": {"project", "path", "services"},
    "systemd": {"unit", "state", "timer", "next_at"},
    "cron": {"user", "schedule", "cmd_masked"},
    "ports": {"port", "proto", "bind", "process", "public"},
    "repos": {"path", "remote", "branch", "dirty", "last_commit_at"},
    "automations": {"kind", "name", "active", "detail"},
    "sites": {"host", "upstream"},
}

DOCKER_PS = "\n".join(
    json.dumps(c)
    for c in [
        {
            "Names": "fx-api-1",
            "Image": "fx/api:1",
            "State": "running",
            "Status": "Up 2 hours (healthy)",
            "Labels": "com.docker.compose.project=fx,com.docker.compose.service=api",
        },
        {
            "Names": "fx-celery-beat-1",
            "Image": "fx/api:1",
            "State": "running",
            "Status": "Up 2 hours",
            "Labels": "com.docker.compose.project=fx,com.docker.compose.service=celery-beat",
        },
        {
            "Names": "n8n",
            "Image": "n8nio/n8n:1.80",
            "State": "exited",
            "Status": "Exited (0) 1 day ago",
            "Labels": "",
        },
    ]
)
OUTPUTS: dict[str, str] = {
    "free -m": "              total used free\nMem:  15990 6000 9990\nSwap:  8191 100 8091\n",
    "df": "Filesystem 1-blocks Used Available Capacity Mounted on\n/dev/sda1 160000000000 40000000000 120000000000 25% /\n"
    "/dev/sda15 100000 1 99999 1% /boot/efi\n",
    "docker ps": DOCKER_PS,
    "docker compose": json.dumps(
        [
            {
                "Name": "fx",
                "Status": "running(2)",
                "ConfigFiles": "/home/forex/CoinePro-FX/docker-compose.yml",
            }
        ]
    ),
    "systemctl list-units": "docker.service loaded active running Docker\nssh.service loaded active running OpenSSH\n",
    "systemctl list-timers": json.dumps(
        [{"next": 1793400000000000, "unit": "certbot.timer", "activates": "certbot.service"}]
    ),
    "crontab -l": "# m h dom mon dow command\nMAILTO=me\nAPI_TOKEN=abc"
    "def123456\n"
    "0 3 * * * bash scripts/backup.sh --password=supersecret\n@reboot /usr/bin/true\n",
    "ss": 'tcp LISTEN 0 4096 0.0.0.0:443 0.0.0.0:* users:(("caddy",pid=1,fd=3))\n'
    "tcp LISTEN 0 4096 127.0.0.1:5432 0.0.0.0:*\n"
    "tcp LISTEN 0 4096 [::]:22 [::]:*\n"
    "tcp LISTEN 0 4096 10.10.1.2:9100 0.0.0.0:*\n"
    "udp UNCONN 0 0 127.0.0.53%lo:53 0.0.0.0:*\n",
}


def fake_run(calls: list[list[str]]) -> Any:
    async def runner(argv: list[str]) -> str | None:
        calls.append(argv)
        line = " ".join(argv)
        if argv[0] == "git":
            sub = argv[3]
            return {
                "remote": "https://ci:ghp_abcdefghijklmnopqrstuvwxyz0123456789@github.com/o/fx.git\n",
                "branch": "main\n",
                "status": " M README.md\n",
                "log": "2026-10-30T10:00:00+00:00\n",
            }[sub]
        for key, out in OUTPUTS.items():
            if line.startswith(key):
                return out
        return None

    return runner


@pytest.fixture
def fake_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "root"
    (root / "etc/nginx/sites-enabled").mkdir(parents=True)
    (root / "etc/caddy").mkdir(parents=True)
    (root / "proc").mkdir()
    (root / "etc/os-release").write_text('NAME="Ubuntu"\nPRETTY_NAME="Ubuntu 24.04.1 LTS"\n')
    (root / "proc/uptime").write_text("12345.67 999.0\n")
    (root / "proc/loadavg").write_text("0.42 0.30 0.20 1/300 4242\n")
    (root / "etc/nginx/sites-enabled/fx").write_text(
        "server {\n  listen 443 ssl;\n  server_name coineprofx.com www.coineprofx.com;\n"
        "  location / { proxy_pass http://127.0.0.1:8000; }\n}\n"
    )
    (root / "etc/caddy/Caddyfile").write_text(
        "api.example.com {\n  reverse_proxy localhost:9000\n}\n"
    )
    home = tmp_path / "home"
    (home / "CoinePro-FX/.git").mkdir(parents=True)
    (home / "a/b/c/d/too-deep/.git").mkdir(parents=True)
    (home / "node_modules/x/.git").mkdir(parents=True)
    return root, home


def check_shape(m: dict[str, Any]) -> None:
    assert tuple(m) == MAP_KEYS
    for key, fields in SHAPE.items():
        if key in ("cpu", "memory"):
            if m[key] is not None:
                assert set(m[key]) == fields, key
        else:
            assert isinstance(m[key], list), key
            for item in m[key]:
                assert set(item) == fields, (key, item)


def test_map_shape_and_content(fake_root: tuple[Path, Path]) -> None:
    root, home = fake_root
    calls: list[list[str]] = []
    inv = Inventory(Masker(), run=fake_run(calls), home=home, root=root)
    m = run(inv.collect())
    check_shape(m)
    assert m["os"] == "Ubuntu 24.04.1 LTS" and m["uptime_s"] == 12345 and m["cpu"]["load1"] == 0.42
    assert m["memory"] == {
        "total_mb": 15990,
        "used_mb": 6000,
        "swap_total_mb": 8191,
        "swap_used_mb": 100,
    }
    assert m["disks"] == [{"mount": "/", "total_gb": 160.0, "used_gb": 40.0}]
    assert m["containers"][0] == {
        "name": "fx-api-1",
        "image": "fx/api:1",
        "state": "running",
        "health": "healthy",
        "project": "fx",
    }
    assert m["compose"] == [
        {
            "project": "fx",
            "path": "/home/forex/CoinePro-FX/docker-compose.yml",
            "services": ["api", "celery-beat"],
        }
    ]
    timer = next(s for s in m["systemd"] if s["timer"])
    assert timer["unit"] == "certbot.timer" and timer["next_at"].endswith("Z")
    assert [c["schedule"] for c in m["cron"]] == ["0 3 * * *", "@reboot"]
    assert "supersecret" not in json.dumps(m) and "abcdef123456" not in json.dumps(m)
    ports = {(p["port"], p["bind"]): p for p in m["ports"]}
    assert ports[(443, "0.0.0.0")]["public"] and ports[(443, "0.0.0.0")]["process"] == "caddy"
    assert not ports[(5432, "127.0.0.1")]["public"] and ports[(22, "::")]["public"]
    assert not ports[(9100, "10.10.1.2")]["public"] and ports[(53, "127.0.0.53")]["proto"] == "udp"
    assert [r["path"] for r in m["repos"]] == [str(home / "CoinePro-FX")]
    repo = m["repos"][0]
    assert repo["dirty"] and repo["branch"] == "main" and "ghp_" not in repo["remote"]
    kinds = {(a["kind"], a["name"]) for a in m["automations"]}
    assert (
        ("n8n", "n8n") in kinds
        and ("other", "fx-celery-beat-1") in kinds
        and ("systemd", "certbot.timer") in kinds
    )
    assert any(a["kind"] == "cron" for a in m["automations"])
    assert {"host": "coineprofx.com", "upstream": "http://127.0.0.1:8000"} in m["sites"]
    assert {"host": "api.example.com", "upstream": "localhost:9000"} in m["sites"]
    # Only fixed read-only commands; git never takes locks.
    allowed = {"free", "df", "docker", "systemctl", "crontab", "ss", "git"}
    assert {c[0] for c in calls} <= allowed
    assert all(c[3] in ("remote", "branch", "status", "log") for c in calls if c[0] == "git")


def test_map_tolerates_missing_tools(tmp_path: Path) -> None:
    async def nothing(argv: list[str]) -> None:
        return None

    m = run(Inventory(Masker(), run=nothing, home=tmp_path, root=tmp_path).collect())
    check_shape(m)
    assert m["containers"] == [] and m["ports"] == [] and m["memory"] is None


def test_map_on_this_machine() -> None:
    m = run(Inventory(Masker()).collect())
    check_shape(m)
    assert m["cpu"]["cores"]


@pytest.mark.skipif(not shutil.which("git"), reason="git missing")
def test_map_real_git_repo(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin",
    }
    for cmd in (
        ["init", "-q", "-b", "main"],
        ["remote", "add", "origin", "https://github.com/o/p.git"],
        ["commit", "-q", "--allow-empty", "-m", "x"],
    ):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, env=env)
    (repo / "new.txt").write_text("x")
    m = run(Inventory(Masker(), home=tmp_path, root=tmp_path).collect())
    assert m["repos"] == [
        {
            "path": str(repo),
            "remote": "https://github.com/o/p.git",
            "branch": "main",
            "dirty": True,
            "last_commit_at": m["repos"][0]["last_commit_at"],
        }
    ]
    assert m["repos"][0]["last_commit_at"]
    assert not (repo / ".git/index.lock").exists()


def test_parsers_edge_cases() -> None:
    assert parse_crontab("* * * * *\n", "u", Masker()) == []
    sys_cron = parse_crontab(
        "SHELL=/bin/sh\n17 * * * * root cd / && run-parts /etc/cron.hourly\n",
        "root",
        Masker(),
        system=True,
    )
    assert sys_cron == [
        {
            "user": "root",
            "schedule": "17 * * * *",
            "cmd_masked": "cd / && run-parts /etc/cron.hourly",
        }
    ]
    assert parse_ss("garbage\n") == []
    assert parse_nginx("server { server_name _; root /var/www; }") == []
    assert parse_caddyfile(
        "(snippet) {\n  log\n}\n:8080 {\n respond ok\n}\nhttps://a.b, c.d {\n reverse_proxy /api/* app:80\n}\n"
    ) == [{"host": "a.b", "upstream": "app:80"}, {"host": "c.d", "upstream": "app:80"}]
