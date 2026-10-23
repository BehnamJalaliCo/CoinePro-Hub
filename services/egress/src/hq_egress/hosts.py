"""Host matching shared by egress's proxy and the profile browser (prompt 12
§9.1): standard library only (the browser images carry no other egress code)."""

from __future__ import annotations


def covered(host: str, hosts: frozenset[str]) -> bool:
    """`host` is one of `hosts` or a subdomain of one."""
    host = host.lower().rstrip(".")
    return any(host == h or host.endswith("." + h) for h in hosts)
