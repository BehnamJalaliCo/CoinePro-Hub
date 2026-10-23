"""`probe`: the render container's own proof that it has no network: no
interface but loopback, and no TCP connection to the api, OpenBao, the
internet or a production neighbour opens (by name or by address)."""

from __future__ import annotations

import json
import socket
from pathlib import Path

TARGETS = (
    ("api", 8000),
    ("openbao", 8200),
    ("postgres", 5432),
    ("172.30.0.1", 9100),
    ("1.1.1.1", 443),
    ("8.8.8.8", 53),
    ("10.10.1.1", 443),
    ("169.254.169.254", 80),
)


def reaches(host: str, port: int, timeout: float = 2.0) -> str | None:
    """None when no connection opens; else what answered."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return None  # not even a name: no DNS
    for family, kind, proto, _, addr in infos:
        with socket.socket(family, kind, proto) as s:
            s.settimeout(timeout)
            try:
                s.connect(addr)
            except OSError:
                continue
            return f"{host}:{port}"
    return None


def run() -> dict[str, object]:
    ifaces = (
        sorted(p.name for p in Path("/sys/class/net").iterdir())
        if Path("/sys/class/net").exists()
        else []
    )
    reached = [r for r in (reaches(h, p) for h, p in TARGETS) if r]
    return {
        "interfaces": ifaces,
        "reached": reached,
        "isolated": not reached and ifaces in ([], ["lo"]),
    }


def main() -> int:
    out = run()
    print(json.dumps(out))
    return 0 if out["isolated"] else 1
