"""Renders the bench's user data with the provisioner's own renderer (run in
the services test image: PYTHONPATH has hq_common and hq_provisioner):

    render.py OUT_DIR TEMPLATES_DIR

full.sh       every software key, the callback to the bench's receiver
bad-docker.sh the same with a wrong Docker key fingerprint (must stop there)
"""

from __future__ import annotations

import base64
import secrets
import struct
import sys
from dataclasses import replace
from pathlib import Path

from hq_common import provisioning as P
from hq_provisioner import cloudinit

blob = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + bytes(range(32))
OWNER = f"ssh-ed25519 {base64.b64encode(blob).decode()} owner@bench"
PLAN = {
    "id": "bench",
    "ref": "PV-0001",
    "founding": None,
    "company": "BX",
    "name": "bx-bench-1",
    "type": "cpx42",
    "location": "fsn1",
    "image": "ubuntu-24.04",
    "private_network": True,
    "firewall": [{"direction": "in", "protocol": "tcp", "port": "22", "sources": ["198.51.100.7/32"]}],
    "software": list(P.SOFTWARE),
    "work_user": "bx",
    "repo": "behnamjalalico/bench-repo",
    "monthly_eur": "26.99",
}


def main() -> None:
    out, templates = Path(sys.argv[1]), sys.argv[2]
    out.mkdir(parents=True, exist_ok=True)
    pins = cloudinit.Pins(wait_s=2)
    for name, p in (("full", pins), ("bad-docker", replace(pins, docker_key_fpr="0" * 40))):
        ud = cloudinit.render(
            PLAN,
            run_id="run-bench",
            owner_keys=[OWNER],
            callback_url="http://127.0.0.1:8099/cb",
            callback_token=secrets.token_urlsafe(32),
            templates=templates,
            pins=p,
        )
        (out / f"{name}.sh").write_text(ud)
    (out / "steps").write_text(" ".join(P.ordered(PLAN["software"])))  # type: ignore[arg-type]
    print(f"render: {len(ud.encode())} bytes of user data, {len(PLAN['software'])} steps")


if __name__ == "__main__":
    main()
