"""The new server's cloud-init user data, rendered from the reviewed
templates (infra/provisioning/templates/<key>.sh): no template takes input;
every value goes once through shlex.quote into one block of assignments.

What the user data carries: the plan's ref, the run, the work user, the repo,
the owner's PUBLIC keys, the pinned versions and checksums, the callback URL
and the one-time callback token (valid 60 minutes, single use). Never a root
password, a private key, the Hetzner token or any long-lived secret.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hq_common import provisioning as P
from hq_provisioner.vault import public_keys

MAX_BYTES = 32 * 1024  # Hetzner's user data limit
END = "COINEPRO_PROVISION_EOF"
TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
RUN = re.compile(r"^[A-Za-z0-9-]{1,64}$")


@dataclass(frozen=True)
class Pins:
    """Versions and checksums baked into the user data (reviewed with the
    templates; nothing is fetched unpinned)."""

    node_version: str = "24.21.0"
    node_sha256_x64: str = "fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6"
    node_sha256_arm64: str = "6ad1325edbdb5649c379b75a237147a666c95d4f9ae8d340fef2d1575d289ad2"
    # The same Claude Code as the hub's own runtime (claude-agent-sdk bundles it).
    claude_code_version: str = "2.1.294"
    # Docker's apt signing key (download.docker.com/linux/ubuntu/gpg).
    docker_key_fpr: str = "9DC858229FC7DD38854AE2D88D81803C0EBFCD88"
    # GitHub's published host key (api.github.com/meta), no trust on first use.
    github_host_key: str = (
        "github.com ssh-ed25519 "
        "AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
    )
    wait_s: int = 60


class RenderError(ValueError):
    pass


def _template(root: Path, name: str) -> str:
    text = (root / f"{name}.sh").read_text(encoding="utf-8")
    if END in text:
        raise RenderError(f"template {name} contains the end marker")
    return text.rstrip("\n") + "\n"


def render(
    plan: dict[str, Any],
    *,
    run_id: str,
    owner_keys: list[str],
    callback_url: str,
    callback_token: str,
    templates: str | Path,
    pins: Pins | None = None,
) -> str:
    """The user data of one run of one sealed plan."""
    pins = pins or Pins()
    if P.problems(plan):
        raise RenderError("the plan has problems; it is never rendered")
    keys = public_keys(owner_keys)
    if not keys or len(keys) != len(owner_keys):
        raise RenderError("only the owner's public keys go to a server")
    if not TOKEN.match(callback_token):
        raise RenderError("the callback token is not a one-time random token")
    if not RUN.match(run_id):
        raise RenderError("bad run id")
    if not callback_url.startswith("https://") and not callback_url.startswith("http://127.0.0.1"):
        raise RenderError("the callback goes to the hub over HTTPS")
    for v in (pins.node_version, pins.claude_code_version):
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", v):
            raise RenderError("a pinned version is not x.y.z")
    root = Path(templates)
    steps = P.ordered(plan["software"])
    values = {
        "PLAN_REF": plan["ref"],
        "RUN_ID": run_id,
        "WORK_USER": plan["work_user"],
        "REPO": plan.get("repo") or "",
        "STEPS": " ".join(steps),
        "OWNER_KEYS": "\n".join(keys),
        "CALLBACK_URL": callback_url,
        "NODE_VERSION": pins.node_version,
        "NODE_SHA256_X64": pins.node_sha256_x64,
        "NODE_SHA256_ARM64": pins.node_sha256_arm64,
        "CLAUDE_CODE_VERSION": pins.claude_code_version,
        "DOCKER_KEY_FPR": pins.docker_key_fpr,
        "GITHUB_HOST_KEY": pins.github_host_key,
        "WAIT_S": str(int(pins.wait_s)),
    }
    block = "".join(f"{k}={shlex.quote(str(v))}\n" for k, v in values.items())
    body = (
        "#!/bin/bash\n"
        f"# CoinePro HQ provisioning of {plan['name']} (plan {plan['ref']}, run {run_id}).\n"
        "# Rendered by the provisioner from infra/provisioning/templates; the values:\n"
        + block
        + _template(root, "_header")
        + "".join(_template(root, k) for k in steps)
        + _template(root, "_footer")
    )
    if END in block:
        raise RenderError("a value contains the end marker")
    user_data = (
        "#!/bin/bash\n"
        f"# CoinePro HQ: the build of {plan['name']} (plan {plan['ref']}). cloud-init user data.\n"
        "# Writes the provisioning script and runs it; the token below is single use,\n"
        "# valid 60 minutes, and is shredded after the callback.\n"
        "set -euo pipefail\n"
        "install -d -m 0700 /var/lib/coinepro-provision\n"
        "umask 077\n"
        f"printf '%s' {shlex.quote(callback_token)} >/var/lib/coinepro-provision/callback.token\n"
        "install -d -m 0755 /usr/local/sbin\n"
        f"cat >/usr/local/sbin/coinepro-provision <<'{END}'\n" + body + f"{END}\n"
        "chmod 0700 /usr/local/sbin/coinepro-provision\n"
        "exec /usr/local/sbin/coinepro-provision\n"
    )
    size = len(user_data.encode())
    if size > MAX_BYTES:
        raise RenderError(f"user data is {size} bytes; Hetzner takes at most {MAX_BYTES}")
    if "PRIVATE KEY" in user_data:
        raise RenderError("a private key in the user data")
    return user_data
