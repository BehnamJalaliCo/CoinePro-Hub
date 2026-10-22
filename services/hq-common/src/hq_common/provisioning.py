"""Server plans (contract §18.8, §18.16): the one definition the api and the
provisioner share, so a seal means the same bytes on both sides.

- `digest(plan)`: sha256 of the plan's canonical JSON (sorted keys, no
  spaces, UTF-8, ensure_ascii off) without `digest`, `state`, `decision_ref`
  and `run`. The owner's seal is bound to it; the provisioner recomputes it
  before touching anything, so a plan changed after the seal never runs.
- `SOFTWARE`: the fixed list of software keys, each a reviewed cloud-init
  template (infra/provisioning/templates/<key>.sh), in the order they run.
- `problems(plan, ssh_sources=...)`: what is wrong with a plan (empty: it
  may be sealed). Review 9.2 (§18.16): any tcp range that contains 22 is SSH
  and its sources must lie inside the owner's addresses
  (owner_settings.provision_ssh_sources); a source set that covers the whole
  address space (all rules together) is refused except on 80 and 443; the
  work user is a new account, never one of Ubuntu's base system;
  ssh-hardening, unattended-upgrades and work-user are always in a plan.
- `LABELS`: every Hetzner resource the provisioner makes carries these; it
  never touches a resource without `managed-by=coinepro-hq`.
"""

from __future__ import annotations

import hashlib
import ipaddress
import itertools
import json
import re
from typing import Any

Net = ipaddress.IPv4Network | ipaddress.IPv6Network

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
# Always in a plan (§18.16): the owner logs in as the work user, with keys
# only, and security updates come on their own.
REQUIRED: tuple[str, ...] = ("unattended-upgrades", "work-user", "ssh-hardening")
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
SSH_PORT = 22
# The only ports that may be open to the whole internet (a web server).
PUBLIC_PORTS = frozenset({80, 443})
# Every account and group of Ubuntu 24.04's base system (the server image's
# /etc/passwd and /etc/group) and those the plan's own steps make. The work
# user is a NEW account: reusing one of these would give a system account
# NOPASSWD sudo and lock the owner out (review 9.2 §2.2).
SYSTEM_NAMES = frozenset(
    {
        # /etc/passwd
        "root", "daemon", "bin", "sys", "sync", "games", "man", "lp", "mail", "news", "uucp",
        "proxy", "www-data", "backup", "list", "irc", "gnats", "nobody", "ubuntu", "sshd",
        "systemd-network", "systemd-resolve", "systemd-timesync", "systemd-coredump",
        "systemd-oom", "messagebus", "syslog", "uuidd", "tss", "tcpdump", "landscape",
        "pollinate", "polkitd", "fwupd-refresh", "usbmux", "dhcpcd", "dnsmasq", "lxd",
        "chrony", "ntp", "postfix", "statd", "cloud-init",
        # /etc/group
        "adm", "tty", "disk", "kmem", "dialout", "fax", "voice", "cdrom", "floppy", "tape",
        "sudo", "audio", "dip", "operator", "src", "shadow", "utmp", "video", "sasl", "plugdev",
        "staff", "users", "nogroup", "systemd-journal", "input", "sgx", "kvm", "render",
        "crontab", "netdev", "rdma", "admin", "ssl-cert", "wheel",
        # made by the plan's own steps (docker, node-exporter)
        "docker", "prometheus",
    }
)  # fmt: skip
RESERVED_USERS = SYSTEM_NAMES  # prompt 9's name
_WHOLE: tuple[Net, ...] = (ipaddress.ip_network("0.0.0.0/0"), ipaddress.ip_network("::/0"))
_MAPPED = ipaddress.ip_network("::ffff:0:0/96")

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


def system_name(user: str) -> bool:
    """A name Ubuntu's base system (or a step of ours) already uses."""
    return user in SYSTEM_NAMES or user.startswith(("systemd-", "_"))


def default_work_user(code: str) -> str:
    """The work user of a company's server when nobody named one: `<code>-ops`."""
    return f"{code.lower()}-ops"


def covers_everything(nets: list[Net]) -> bool:
    """Whether the networks together are the whole IPv4 or the whole IPv6 space."""
    for whole in _WHOLE:
        fam = [n for n in nets if n.version == whole.version]
        if fam and list(ipaddress.collapse_addresses(fam)) == [whole]:  # type: ignore[type-var]
            return True
    return False


def port_range(port: Any) -> tuple[int, int] | None:
    """`22` -> (22, 22), `8000-8100` -> (8000, 8100); None if it is not one."""
    m = _PORT.match(str(port or ""))
    if not m:
        return None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    if lo > 65535 or hi > 65535 or hi < lo:
        return None
    return lo, hi


def is_ssh(rule: Any) -> bool:
    """Any tcp range that contains 22 is SSH."""
    if not isinstance(rule, dict) or rule.get("protocol") != "tcp":
        return False
    rng = port_range(rule.get("port"))
    return rng is not None and rng[0] <= SSH_PORT <= rng[1]


def _nets(rule: dict[str, Any]) -> list[Net]:
    out: list[Net] = []
    for s in rule.get("sources") or []:
        try:
            out.append(ipaddress.ip_network(str(s), strict=True))
        except ValueError:
            continue
    return out


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
        if isinstance(net, ipaddress.IPv6Network) and net.subnet_of(_MAPPED):  # type: ignore[arg-type]
            out.append(f"{where}.sources: {str(s)[:50]!r} is IPv4-mapped (write it as IPv4)")
    return out


def _exposure(rules: list[Any]) -> list[str]:
    """Ports open to the whole address space, all rules together (two halves
    of the internet are the internet); only 80 and 443 may be."""
    by_proto: dict[str, list[tuple[tuple[int, int], list[Net]]]] = {}
    for r in rules:
        if not isinstance(r, dict) or r.get("protocol") not in ("tcp", "udp", "icmp"):
            continue
        rng = (0, 0) if r["protocol"] == "icmp" else port_range(r.get("port"))
        if rng is not None:
            by_proto.setdefault(str(r["protocol"]), []).append((rng, _nets(r)))
    out: list[str] = []
    for proto, items in sorted(by_proto.items()):
        # Elementary port intervals: inside each, the same rules apply.
        cuts = sorted(
            {lo for (lo, _), _ in items}
            | {hi + 1 for (_, hi), _ in items}
            | ({p for x in PUBLIC_PORTS for p in (x, x + 1)} if proto != "icmp" else set())
        )
        for a, b in itertools.pairwise(cuts):
            hi = b - 1
            nets = [n for (lo2, hi2), ns in items if lo2 <= a and hi <= hi2 for n in ns]
            if not nets or (proto != "icmp" and a == hi and a in PUBLIC_PORTS):
                continue
            if not covers_everything(nets):
                continue
            if proto == "tcp" and a <= SSH_PORT <= hi:
                out.append("firewall: SSH open to the whole internet (name the owner's addresses)")
            elif proto == "icmp":
                out.append("firewall: icmp open to the whole internet (only 80 and 443 may be)")
            else:
                ports = str(a) if a == hi else f"{a}-{hi}"
                out.append(
                    f"firewall: {proto} {ports} open to the whole internet (only 80 and 443 may be)"
                )
    return out


def _ssh_problems(rules: list[Any], ssh_sources: list[str] | None) -> list[str]:
    """SSH only from inside the owner's own addresses (when the caller knows them)."""
    if ssh_sources is None:
        return []
    owner: list[Net] = []
    for s in ssh_sources:
        try:
            owner.append(ipaddress.ip_network(str(s), strict=False))
        except ValueError:
            continue
    out: list[str] = []
    for i, r in enumerate(rules):
        if not is_ssh(r):
            continue
        if not owner:
            out.append(
                f"firewall.{i}: SSH needs the owner's addresses first "
                "(owner settings: provision_ssh_sources)"
            )
            continue
        outside = [
            str(n)
            for n in _nets(r)
            if not any(n.version == o.version and n.subnet_of(o) for o in owner)  # type: ignore[arg-type]
        ]
        if outside:
            out.append(
                f"firewall.{i}: SSH from {', '.join(outside)[:120]}, outside the owner's "
                "addresses (provision_ssh_sources)"
            )
    return out


def problems(plan: dict[str, Any], *, ssh_sources: list[str] | None = None) -> list[str]:
    """Everything that stops a plan from being sealed (and from running).
    `ssh_sources`: the owner's addresses (owner_settings.provision_ssh_sources)
    when the caller knows them; every SSH source must lie inside them."""
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
    if not _USER.match(user) or system_name(user):
        out.append(
            "work_user: lowercase, 2 to 32 characters, a new account "
            "(not a system account or group of Ubuntu)"
        )
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
    absent = [k for k in REQUIRED if k not in chosen]
    if absent:
        out.append(f"software: always in a plan: {', '.join(absent)}")
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
    out += _exposure(rules)
    out += _ssh_problems(rules, ssh_sources)
    if not any(is_ssh(r) for r in rules):
        out.append("firewall: no rule for SSH (22) from the owner's addresses: nobody could log in")
    return out
