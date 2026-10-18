"""A mock Hetzner Cloud API over real HTTP (the hcloud library talks to it as
to api.hetzner.cloud): the subset the provisioner uses, every request
recorded, failures injectable, pre-existing (unlabelled) resources seeded.
No money, no real server: CI never calls Hetzner."""

from __future__ import annotations

import base64
import hashlib
import itertools
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

NOW = "2026-10-18T00:00:00+00:00"
PRICING = {
    "currency": "EUR",
    "vat_rate": "19.00",
    "server_types": [
        {
            "id": 45,
            "name": "cpx42",
            "prices": [
                {
                    "location": "fsn1",
                    "price_hourly": {"net": "0.0420000000", "gross": "0.0499800000"},
                    "price_monthly": {"net": "26.4900000000", "gross": "31.5231000000"},
                },
                {
                    "location": "nbg1",
                    "price_hourly": {"net": "0.0420000000", "gross": "0.0499800000"},
                    "price_monthly": {"net": "26.4900000000", "gross": "31.5231000000"},
                },
            ],
        }
    ],
    "primary_ips": [
        {
            "type": "ipv4",
            "prices": [
                {
                    "location": "fsn1",
                    "price_hourly": {"net": "0.0008000000", "gross": "0.0009520000"},
                    "price_monthly": {"net": "0.5000000000", "gross": "0.5950000000"},
                }
            ],
        }
    ],
}


def md5_fingerprint(public_key: str) -> str:
    h = hashlib.md5(base64.b64decode(public_key.split()[1]), usedforsecurity=False).hexdigest()
    return ":".join(h[i : i + 2] for i in range(0, 32, 2))


def _rules(rules: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Rules as Hetzner answers them (every field present)."""
    return [{"direction": r.get("direction"), "protocol": r.get("protocol"), "port": r.get("port"),
             "source_ips": r.get("source_ips") or [], "destination_ips": r.get("destination_ips") or [],
             "description": r.get("description")} for r in rules or []]  # fmt: skip


def _match(labels: dict[str, str], selector: str | None) -> bool:
    if not selector:
        return True
    for part in selector.split(","):
        k, _, v = part.partition("=")
        if labels.get(k) != v:
            return False
    return True


class FakeHetzner:
    def __init__(self) -> None:
        self.ids = itertools.count(1000)
        self.requests: list[tuple[str, str, Any]] = []
        self.ssh_keys: dict[int, dict[str, Any]] = {}
        self.firewalls: dict[int, dict[str, Any]] = {}
        self.networks: dict[int, dict[str, Any]] = {}
        self.servers: dict[int, dict[str, Any]] = {}
        self.fail: dict[tuple[str, str], int] = {}  # (method, path regex) -> remaining failures
        self.root_password: str | None = None  # what POST /servers answers
        self.boot_polls = 1  # GETs of a new server before it is running
        self._polls: dict[int, int] = {}
        self._server: ThreadingHTTPServer | None = None
        self.lock = threading.Lock()

    # --------------------------------------------------------------- seeds --
    def seed_server(self, name: str, labels: dict[str, str] | None = None) -> int:
        sid = next(self.ids)
        self.servers[sid] = self._server_obj(sid, name, labels or {}, "running")
        return sid

    def seed_firewall(self, name: str, labels: dict[str, str] | None = None) -> int:
        fid = next(self.ids)
        self.firewalls[fid] = {"id": fid, "name": name, "labels": labels or {}, "rules": [],
                               "applied_to": [], "created": NOW}  # fmt: skip
        return fid

    def seed_ssh_key(self, name: str, public_key: str, fingerprint: str) -> int:
        kid = next(self.ids)
        self.ssh_keys[kid] = {"id": kid, "name": name, "public_key": public_key,
                              "fingerprint": fingerprint, "labels": {}, "created": NOW}  # fmt: skip
        return kid

    # ------------------------------------------------------------- objects --
    def _action(self, command: str) -> dict[str, Any]:
        return {"id": next(self.ids), "command": command, "status": "success", "progress": 100,
                "started": NOW, "finished": NOW, "resources": [], "error": None}  # fmt: skip

    def _server_obj(self, sid: int, name: str, labels: dict[str, str], status: str,
                    private: list[dict[str, Any]] | None = None) -> dict[str, Any]:  # fmt: skip
        return {
            "id": sid,
            "name": name,
            "status": status,
            "created": NOW,
            "labels": labels,
            "public_net": {
                "ipv4": {
                    "id": sid,
                    "ip": f"203.0.113.{sid % 250}",
                    "blocked": False,
                    "dns_ptr": "",
                },
                "ipv6": {"id": sid, "ip": "2001:db8::/64", "blocked": False, "dns_ptr": []},
                "floating_ips": [],
                "firewalls": [],
            },
            "private_net": private or [],
            "server_type": {"id": 45, "name": "cpx42"},
            "image": {"id": 161547269, "name": "ubuntu-24.04", "type": "system"},
            "protection": {"delete": False, "rebuild": False},
            "rescue_enabled": False,
            "locked": False,
            "volumes": [],
            "load_balancers": [],
            "included_traffic": 0,
            "outgoing_traffic": 0,
            "ingoing_traffic": 0,
        }

    @staticmethod
    def _page(key: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        return {key: items, "meta": {"pagination": {"page": 1, "per_page": 50, "previous_page": None,
                "next_page": None, "last_page": 1, "total_entries": len(items)}}}  # fmt: skip

    # ------------------------------------------------------------ requests --
    def handle(
        self, method: str, path: str, query: dict[str, list[str]], body: Any
    ) -> tuple[int, Any]:
        with self.lock:
            self.requests.append((method, path, body))
            for (m, pattern), left in list(self.fail.items()):
                if m == method and re.fullmatch(pattern, path) and left > 0:
                    self.fail[(m, pattern)] = left - 1
                    return 500, {"error": {"code": "server_error", "message": "injected failure"}}
            return self._route(method, path, query, body)

    def _route(self, method: str, path: str, q: dict[str, list[str]], body: Any) -> tuple[int, Any]:
        sel = (q.get("label_selector") or [None])[0]
        if path == "/v1/pricing" and method == "GET":
            return 200, {"pricing": PRICING}
        if path == "/v1/ssh_keys":
            if method == "GET":
                fp = (q.get("fingerprint") or [None])[0]
                items = [k for k in self.ssh_keys.values() if (not fp or k["fingerprint"] == fp)
                         and _match(k["labels"], sel)]  # fmt: skip
                return 200, self._page("ssh_keys", items)
            kid = next(self.ids)
            key = {"id": kid, "name": body["name"], "public_key": body["public_key"],
                   "fingerprint": md5_fingerprint(body["public_key"]), "labels": body.get("labels") or {}, "created": NOW}  # fmt: skip
            self.ssh_keys[kid] = key
            return 201, {"ssh_key": key}
        if path == "/v1/firewalls":
            if method == "GET":
                return 200, self._page(
                    "firewalls", [f for f in self.firewalls.values() if _match(f["labels"], sel)]
                )
            fid = next(self.ids)
            fw = {"id": fid, "name": body["name"], "labels": body.get("labels") or {},
                  "rules": _rules(body.get("rules")), "applied_to": [], "created": NOW}  # fmt: skip
            self.firewalls[fid] = fw
            return 201, {"firewall": fw, "actions": [self._action("set_firewall_rules")]}
        if m := re.fullmatch(r"/v1/firewalls/(\d+)/actions/set_rules", path):
            self.firewalls[int(m.group(1))]["rules"] = _rules(body.get("rules"))
            return 201, {"actions": [self._action("set_firewall_rules")]}
        if path == "/v1/networks":
            if method == "GET":
                return 200, self._page(
                    "networks", [n for n in self.networks.values() if _match(n["labels"], sel)]
                )
            nid = next(self.ids)
            net = {"id": nid, "name": body["name"], "ip_range": body["ip_range"],
                   "subnets": [{**s, "gateway": "10.20.0.1"} for s in body.get("subnets") or []],
                   "routes": [], "servers": [], "labels": body.get("labels") or {}, "created": NOW,
                   "protection": {"delete": False}, "expose_routes_to_vswitch": False}  # fmt: skip
            self.networks[nid] = net
            return 201, {"network": net}
        if m := re.fullmatch(r"/v1/networks/(\d+)/actions/add_subnet", path):
            self.networks[int(m.group(1))]["subnets"].append({**body, "gateway": "10.20.0.1"})
            return 201, {"action": self._action("add_subnet")}
        if path == "/v1/servers":
            if method == "GET":
                return 200, self._page(
                    "servers", [s for s in self.servers.values() if _match(s["labels"], sel)]
                )
            sid = next(self.ids)
            private = [{"network": n, "ip": "10.20.1.2", "alias_ips": [], "mac_address": "86:00:00:00:00:01"}
                       for n in body.get("networks") or []]  # fmt: skip
            server = self._server_obj(
                sid, body["name"], body.get("labels") or {}, "initializing", private
            )
            server["_create"] = body
            self.servers[sid] = server
            self._polls[sid] = 0
            out = {k: v for k, v in server.items() if not k.startswith("_")}
            return 201, {"server": out, "action": self._action("create_server"), "next_actions": [],
                         "root_password": self.root_password}  # fmt: skip
        if m := re.fullmatch(r"/v1/servers/(\d+)", path):
            sid = int(m.group(1))
            server = self.servers.get(sid)
            if server is None:
                return 404, {"error": {"code": "not_found", "message": "server not found"}}
            if server["status"] != "running":
                self._polls[sid] = self._polls.get(sid, 0) + 1
                if self._polls[sid] >= self.boot_polls:
                    server["status"] = "running"
            return 200, {"server": {k: v for k, v in server.items() if not k.startswith("_")}}
        if m := re.fullmatch(r"/v1/actions/(\d+)", path):
            return 200, {"action": {**self._action("x"), "id": int(m.group(1))}}
        return 404, {"error": {"code": "not_found", "message": f"{method} {path}"}}

    # -------------------------------------------------------------- server --
    def start(self) -> str:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _do(self) -> None:
                parts = urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                body = json.loads(raw) if raw else None
                status, out = fake.handle(self.command, parts.path, parse_qs(parts.query), body)
                data = json.dumps(out).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = do_DELETE = _do

            def log_message(self, *_: Any) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    # ------------------------------------------------------------- queries --
    def writes(self) -> list[tuple[str, str]]:
        return [(m, p) for m, p, _ in self.requests if m != "GET"]
