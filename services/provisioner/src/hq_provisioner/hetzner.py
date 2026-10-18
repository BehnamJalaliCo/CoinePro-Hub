"""Hetzner Cloud through the official `hcloud` library, restricted to what the
provisioner may do (prompt 09 §0.3):

- it CREATES resources, each with the label managed-by=coinepro-hq (plus the
  plan and company), and looks them up by those labels to resume;
- it CHANGES only resources with that label (the firewall's rules, back to
  the sealed plan's), never one it did not make;
- it never deletes, rebuilds, powers off or rescues anything (no such call
  exists here), never attaches to an existing network, never creates a root
  password (the owner's public key is always given);
- an existing key with the owner's fingerprint (the owner's own upload) is
  used as it is, never changed.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from hcloud import APIException, Client
from hcloud.firewalls import FirewallRule
from hcloud.images import Image
from hcloud.locations import Location
from hcloud.networks import NetworkSubnet
from hcloud.server_types import ServerType

from hq_common import provisioning as P
from hq_provisioner import __version__

ZONES = {"fsn1": "eu-central", "nbg1": "eu-central", "hel1": "eu-central", "ash": "us-east",
         "hil": "us-west", "sin": "ap-southeast"}  # fmt: skip


class Refused(Exception):
    """Something the provisioner must never do (an unlabelled resource, a root password)."""


@dataclass
class Built:
    id: int
    name: str
    status: str
    ipv4: str | None
    ipv6: str | None
    private_ip: str | None
    labels: dict[str, str]
    created: bool = False


def fingerprint(public_key: str) -> str:
    """Hetzner's fingerprint of a public key: MD5 of the key blob, hex pairs."""
    blob = base64.b64decode(public_key.split()[1])
    digest = hashlib.md5(blob, usedforsecurity=False).hexdigest()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def selector(labels: dict[str, str], *keys: str) -> str:
    return ",".join(f"{k}={labels[k]}" for k in (P.LABEL_MANAGED, *keys))


def _ours(labels: dict[str, str] | None) -> bool:
    return (labels or {}).get(P.LABEL_MANAGED) == P.MANAGED_BY


class Hetzner:
    def __init__(self, token: str, url: str, poll_s: float = 2.0, timeout: float = 30) -> None:
        self.c = Client(
            token=token,
            api_endpoint=url,
            application_name="coinepro-hq-provisioner",
            application_version=__version__,
            poll_interval=poll_s,
            timeout=timeout,
        )
        self.poll_s = poll_s

    # ------------------------------------------------------------ ssh keys --
    def ssh_keys(self, keys: list[str], labels: dict[str, str]) -> tuple[list[Any], list[str]]:
        """The Hetzner keys for the owner's public keys (and what was done)."""
        out: list[Any] = []
        notes: list[str] = []
        base = {P.LABEL_MANAGED: P.MANAGED_BY}
        for key in keys:
            fp = fingerprint(key)
            found = self.c.ssh_keys.get_all(fingerprint=fp)
            if found:
                out.append(found[0])
                notes.append(f"ssh key {fp[:11]}… already in the project (used as it is)")
                continue
            name = f"coinepro-hq-owner-{fp.replace(':', '')[:12]}"
            out.append(self.c.ssh_keys.create(name=name, public_key=key, labels=base))
            notes.append(f"ssh key {fp[:11]}… registered as {name}")
        return out, notes

    # ------------------------------------------------------------ firewall --
    @staticmethod
    def rules(plan: dict[str, Any]) -> list[FirewallRule]:
        out = []
        for r in plan.get("firewall") or []:
            out.append(
                FirewallRule(
                    direction="in",
                    protocol=r["protocol"],
                    source_ips=[str(ipaddress.ip_network(s)) for s in r["sources"]],
                    port=str(r["port"]) if r["protocol"] in ("tcp", "udp") else None,
                    description=str(r.get("note_fa") or "")[:250] or None,
                )
            )
        return out

    def firewall(self, plan: dict[str, Any], labels: dict[str, str]) -> tuple[Any, str]:
        found = self.c.firewalls.get_all(label_selector=selector(labels, P.LABEL_PLAN))
        rules = self.rules(plan)
        if found:
            fw = found[0]
            if not _ours(fw.labels):
                raise Refused("a firewall without our label")
            self.c.firewalls.set_rules(fw, rules)
            return fw, f"firewall {fw.name} (ours) set to the sealed plan's {len(rules)} rule(s)"
        name = f"coinepro-hq-{labels[P.LABEL_PLAN]}"
        resp = self.c.firewalls.create(name=name, rules=rules, labels=labels)  # type: ignore[arg-type]
        for action in resp.actions or []:
            action.wait_until_finished()
        return resp.firewall, f"firewall {name} created with {len(rules)} rule(s)"

    # ------------------------------------------------------------- network --
    def network(
        self, plan: dict[str, Any], labels: dict[str, str], ip_range: str
    ) -> tuple[Any, str]:
        """The company's OWN private network (never an existing one: joining the
        hub's would change a production network; the owner can do that)."""
        zone = ZONES[plan["location"]]
        found = self.c.networks.get_all(label_selector=selector(labels, P.LABEL_COMPANY))
        net_range = ipaddress.ip_network(ip_range)
        subnet = str(next(net_range.subnets(new_prefix=24)))
        if found:
            net = found[0]
            if not _ours(net.labels):
                raise Refused("a network without our label")
            if not any(s.network_zone == zone for s in net.subnets or []):
                used = {s.ip_range for s in net.subnets or []}
                free = next(str(s) for s in net_range.subnets(new_prefix=24) if str(s) not in used)
                self.c.networks.add_subnet(
                    net, NetworkSubnet(type="cloud", ip_range=free, network_zone=zone)
                ).wait_until_finished()
                return net, f"network {net.name} (ours): subnet {free} added in {zone}"
            return net, f"network {net.name} (ours) reused"
        name = f"coinepro-hq-{labels[P.LABEL_COMPANY]}"
        company_labels = {P.LABEL_MANAGED: P.MANAGED_BY, P.LABEL_COMPANY: labels[P.LABEL_COMPANY]}
        net = self.c.networks.create(
            name=name,
            ip_range=str(net_range),
            subnets=[NetworkSubnet(type="cloud", ip_range=subnet, network_zone=zone)],
            labels=company_labels,
        )
        return net, f"network {name} created ({net_range}, subnet {subnet} in {zone})"

    # -------------------------------------------------------------- server --
    def find_server(self, labels: dict[str, str]) -> Any | None:
        found = self.c.servers.get_all(label_selector=selector(labels, P.LABEL_PLAN))
        if not found:
            return None
        if not _ours(found[0].labels):
            raise Refused("a server without our label")
        return found[0]

    def create_server(
        self,
        plan: dict[str, Any],
        labels: dict[str, str],
        *,
        user_data: str,
        ssh_keys: list[Any],
        firewall: Any,
        network: Any | None,
    ) -> Any:
        if not ssh_keys:
            raise Refused("no owner key: Hetzner would make a root password")
        resp = self.c.servers.create(
            name=plan["name"],
            server_type=ServerType(name=plan["type"]),
            image=Image(name=P.IMAGE),
            location=Location(name=plan["location"]),
            ssh_keys=ssh_keys,
            firewalls=[firewall],
            networks=[network] if network is not None else None,
            user_data=user_data,
            labels=labels,
            start_after_create=True,
        )
        if resp.root_password:
            # Never stored, never logged; the owner is told to reset access.
            raise Refused("Hetzner answered with a root password although a key was given")
        if resp.action is not None:
            resp.action.wait_until_finished()
        return resp.server

    def wait_running(self, server_id: int, timeout_s: float) -> Any:
        deadline = time.monotonic() + timeout_s
        while True:
            server = self.c.servers.get_by_id(server_id)
            if server.status == "running":
                return server
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"server {server_id} is {server.status} after {int(timeout_s)} s"
                )
            time.sleep(self.poll_s)

    @staticmethod
    def built(server: Any, created: bool = False) -> Built:
        pub = server.public_net
        private = server.private_net[0].ip if server.private_net else None
        return Built(
            id=int(server.id),
            name=server.name,
            status=server.status,
            ipv4=pub.ipv4.ip if pub and pub.ipv4 else None,
            ipv6=pub.ipv6.ip if pub and pub.ipv6 else None,
            private_ip=private,
            labels=dict(server.labels or {}),
            created=created,
        )

    # --------------------------------------------------- read-only: PR-063 --
    def servers(self) -> list[dict[str, Any]]:
        """Every server of the project (labels decide what is ours; the api's
        protocol PR-063 compares ours with the sealed plans)."""
        out = []
        for s in self.c.servers.get_all():
            b = self.built(s)
            out.append(
                {
                    "id": b.id,
                    "name": b.name,
                    "status": b.status,
                    "ipv4": b.ipv4,
                    "labels": b.labels,
                    "ours": _ours(b.labels),
                    "plan": b.labels.get(P.LABEL_PLAN),
                    "created": s.created.isoformat() if s.created is not None else None,
                }
            )
        return out

    # ------------------------------------------------------------- pricing --
    def pricing(self, server_type: str, location: str) -> dict[str, Any]:
        """The monthly cost in EUR of one server of `server_type` at
        `location`, with its primary IPv4 (Hetzner bills it apart)."""
        data = self.c.request("GET", "/pricing")["pricing"]
        server = next(
            (t for t in data.get("server_types", []) if t.get("name") == server_type), None
        )
        if server is None:
            raise LookupError(f"unknown server type {server_type}")
        price = next((p for p in server.get("prices", []) if p.get("location") == location), None)
        if price is None:
            raise LookupError(f"{server_type} is not offered in {location}")
        ipv4 = Decimal("0")
        ipv4_gross = Decimal("0")
        for ip in data.get("primary_ips", []):
            if ip.get("type") == "ipv4":
                p = next((x for x in ip.get("prices", []) if x.get("location") == location), None)
                if p:
                    ipv4 = Decimal(str(p["price_monthly"]["net"]))
                    ipv4_gross = Decimal(str(p["price_monthly"]["gross"]))
        net = Decimal(str(price["price_monthly"]["net"]))
        gross = Decimal(str(price["price_monthly"]["gross"]))
        return {
            "type": server_type,
            "location": location,
            "currency": data.get("currency", "EUR"),
            "server_monthly_net": str(net.quantize(Decimal("0.01"))),
            "ipv4_monthly_net": str(ipv4.quantize(Decimal("0.01"))),
            "monthly_eur": str((net + ipv4).quantize(Decimal("0.01"))),
            "monthly_eur_gross": str((gross + ipv4_gross).quantize(Decimal("0.01"))),
            "vat_rate": str(data.get("vat_rate", "")),
            "source": "hetzner /pricing",
        }


def message(exc: Exception) -> str:
    """A step's error for the log: Hetzner's code and message, never a token."""
    if isinstance(exc, APIException):
        return f"Hetzner {exc.code}: {str(exc.message)[:200]}"
    return f"{type(exc).__name__}: {str(exc)[:200]}"
