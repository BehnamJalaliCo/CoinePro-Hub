"""Server plans (contract §18.8): the one definition the api and the
provisioner share, so a seal means the same bytes on both sides.

- `digest(plan)`: sha256 of the plan's canonical JSON (sorted keys, no
  spaces, UTF-8, ensure_ascii off) without `digest`, `state`, `decision_ref`
  and `run`. The owner's seal is bound to it; the provisioner recomputes it
  before touching anything, so a plan changed after the seal never runs.
- `SOFTWARE`: the fixed list of software keys, each a reviewed cloud-init
  template (infra/provisioning/templates/<key>.sh), in the order they run.
- `problems(plan)`: what is wrong with a plan (empty: it may be sealed).
- `LABELS`: every Hetzner resource the provisioner makes carries these; it
  never touches a resource without `managed-by=coinepro-hq`.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from typing import Any

MANAGED_BY = "coinepro-hq"
LABEL_MANAGED = "managed-by"
LABEL_PLAN = "coinepro-hq/plan"
LABEL_COMPANY = "coinepro-hq/company"
LABEL_RUN = "coinepro-hq/run"

# Run order: upgrade first (it may reboot this new server, during the build
# only), then the user and SSH, then the tools, then what needs them.
SOFTWARE: tuple[str, ...] = (
    "system-upgrade",
    "unattended-upgrades",
    "work-user",
    "ssh-hardening",
    "private-network",
    "hetzner-firewall",
    "git",
    "docker",
    "node-lts",
    "claude-code",
    "repo-clone",
    "node-exporter",
)
# key -> the keys it needs in the same plan
NEEDS: dict[str, tuple[str, ...]] = {
    "ssh-hardening": ("work-user",),  # no root login: the owner logs in as the work user
    "claude-code": ("node-lts", "work-user"),
    "docker": ("work-user",),
    "repo-clone": ("git", "work-user"),
    "node-exporter": ("private-network",),  # metrics on the private address only
}
LOCATIONS = frozenset({"fsn1", "nbg1", "hel1", "ash", "hil", "sin"})
IMAGE = "ubuntu-24.04"
UNSIGNED = ("digest", "state", "decision_ref", "run")
RESERVED_USERS = frozenset({"root", "admin", "ubuntu", "daemon", "bin", "sys", "nobody", "sshd"})

_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_TYPE = re.compile(r"^[a-z]{2,4}[0-9]{1,3}$")
_USER = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$")
_PORT = re.compile(r"^([1-9][0-9]{0,4})(?:-([1-9][0-9]{0,4}))?$")
_LABEL_VALUE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,61}[A-Za-z0-9])?$")


def canonical(plan: dict[str, Any]) -> bytes:
    body = {k: v for k, v in plan.items() if k not in UNSIGNED}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(plan: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(plan)).hexdigest()


def label_value(text: str) -> str:
    """A Hetzner label value made from our own refs and codes (lowercase)."""
    v = re.sub(r"[^a-z0-9._-]", "-", str(text).lower()).strip("-._")[:63]
    if not _LABEL_VALUE.match(v):
        raise ValueError(f"cannot label {text!r}")
    return v


def labels(plan: dict[str, Any], run: str | None = None) -> dict[str, str]:
    out = {
        LABEL_MANAGED: MANAGED_BY,
        LABEL_PLAN: label_value(plan["ref"]),
        LABEL_COMPANY: label_value(plan["company"]),
    }
    if run:
        out[LABEL_RUN] = label_value(run)[:36]
    return out


def ordered(software: list[str]) -> list[str]:
    """The plan's keys in the order the templates run (unknown keys dropped:
    problems() refuses them before any seal)."""
    chosen = set(software)
    return [k for k in SOFTWARE if k in chosen]


def _rule_problems(i: int, rule: Any) -> list[str]:
    where = f"firewall.{i}"
    if not isinstance(rule, dict):
        return [f"{where}: not an object"]
    out: list[str] = []
    if rule.get("direction") != "in":
        out.append(f"{where}.direction: only 'in' (outbound stays open)")
    proto = rule.get("protocol")
    if proto not in ("tcp", "udp", "icmp"):
        out.append(f"{where}.protocol: tcp, udp or icmp")
    port = str(rule.get("port") or "")
    if proto in ("tcp", "udp"):
        m = _PORT.match(port)
        if not m or int(m.group(1)) > 65535 or (m.group(2) and int(m.group(2)) > 65535):
            out.append(f"{where}.port: a port or a range like 8000-8100")
        elif m.group(2) and int(m.group(2)) < int(m.group(1)):
            out.append(f"{where}.port: an empty range")
    sources = rule.get("sources")
    if not isinstance(sources, list) or not sources or len(sources) > 100:
        out.append(f"{where}.sources: 1 to 100 CIDRs")
        return out
    for s in sources:
        try:
            net = ipaddress.ip_network(str(s), strict=True)
        except ValueError:
            out.append(f"{where}.sources: {str(s)[:50]!r} is not a CIDR")
            continue
        if proto == "tcp" and port == "22" and net.prefixlen == 0:
            out.append(f"{where}: SSH open to the whole internet (name the owner's addresses)")
    return out


def problems(plan: dict[str, Any]) -> list[str]:
    """Everything that stops a plan from being sealed (and from running)."""
    out: list[str] = []
    if not _NAME.match(str(plan.get("name") or "")):
        out.append("name: lowercase letters, digits and '-' (Hetzner server name)")
    if not _TYPE.match(str(plan.get("type") or "")):
        out.append("type: a Hetzner server type such as cpx42")
    if plan.get("location") not in LOCATIONS:
        out.append(f"location: one of {', '.join(sorted(LOCATIONS))}")
    if plan.get("image") != IMAGE:
        out.append(f"image: only {IMAGE}")
    if not isinstance(plan.get("private_network"), bool):
        out.append("private_network: true or false")
    user = str(plan.get("work_user") or "")
    if not _USER.match(user) or user in RESERVED_USERS:
        out.append("work_user: lowercase, 2 to 32 characters, not a system user")
    repo = plan.get("repo")
    if repo is not None and not _REPO.match(str(repo)):
        out.append("repo: owner/name")
    for key in ("ref", "company"):
        try:
            label_value(str(plan.get(key) or ""))
        except ValueError:
            out.append(f"{key}: missing")
    software = plan.get("software")
    if not isinstance(software, list) or not software:
        out.append("software: at least one key")
        software = []
    unknown = [str(k) for k in software if k not in SOFTWARE]
    if unknown:
        out.append(f"software: unknown keys {', '.join(sorted(unknown))[:200]}")
    if len(set(software)) != len(software):
        out.append("software: a key twice")
    chosen = set(software)
    for key, needs in NEEDS.items():
        missing = [n for n in needs if key in chosen and n not in chosen]
        if missing:
            out.append(f"software: {key} needs {', '.join(missing)}")
    if "private-network" in chosen and plan.get("private_network") is not True:
        out.append("software: private-network needs private_network: true")
    if "repo-clone" in chosen and not repo:
        out.append("software: repo-clone needs a repo")
    rules = plan.get("firewall")
    if not isinstance(rules, list) or len(rules) > 50:
        out.append("firewall: a list of at most 50 rules")
        rules = []
    for i, rule in enumerate(rules):
        out += _rule_problems(i, rule)
    ssh = [
        r
        for r in rules
        if isinstance(r, dict) and r.get("protocol") == "tcp" and str(r.get("port")) == "22"
    ]
    if "work-user" in chosen and not ssh:
        out.append("firewall: no rule for SSH (22) from the owner's addresses: nobody could log in")
    return out
