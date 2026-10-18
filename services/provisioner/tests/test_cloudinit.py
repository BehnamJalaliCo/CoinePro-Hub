"""The user data: reviewed templates, quoted values, no long-lived secret."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from hq_provisioner import cloudinit

from .conftest import OWNER_KEY, TEMPLATES, make_plan, public_key

TOKEN = "T" * 43
BASH = shutil.which("bash") or "/bin/bash"


def render(**over: object) -> str:
    args: dict[str, object] = {
        "run_id": "run-1",
        "owner_keys": [OWNER_KEY],
        "callback_url": "https://hq.example.test/api/v1/provisioning/callback",
        "callback_token": TOKEN,
        "templates": TEMPLATES,
    }
    args.update(over)
    plan = args.pop("plan", make_plan())
    return cloudinit.render(plan, **args)  # type: ignore[arg-type]


def test_user_data_carries_public_values_and_a_single_use_token_only() -> None:
    ud = render()
    assert ud.startswith("#!/bin/bash\n") and len(ud.encode()) <= cloudinit.MAX_BYTES
    # The token appears once: written to a 0600 file, shredded after the callback.
    assert ud.count(TOKEN) == 1 and "callback.token" in ud
    assert OWNER_KEY in ud and "PRIVATE KEY" not in ud
    # No password of any kind is set, and nothing from the hub's secrets.
    assert not re.search(r"chpasswd|--password|root_password|passwd [^-]", ud)
    assert "hz-" not in ud and "svc-provisioner" not in ud
    # Every software key's template, in the fixed order, once.
    steps = re.search(r"^STEPS='([^']*)'$", ud, re.M)
    assert steps is not None
    assert steps.group(1).split() == [
        "system-upgrade", "unattended-upgrades", "work-user", "ssh-hardening", "private-network",
        "hetzner-firewall", "git", "docker", "node-lts", "claude-code", "repo-clone", "node-exporter",
    ]  # fmt: skip
    for key in steps.group(1).split():
        assert ud.count(f"step_{key.replace('-', '_')}() {{") == 1
    assert "CLAUDE_CODE_VERSION=2.1.294" in ud and "NODE_VERSION=24.21.0" in ud


def test_only_the_chosen_keys_are_rendered() -> None:
    ud = render(plan=make_plan(software=["system-upgrade", "work-user", "ssh-hardening"], repo=None,
                               private_network=False))  # fmt: skip
    assert "step_docker" not in ud and "step_claude_code" not in ud and "step_ssh_hardening" in ud


@pytest.mark.parametrize(
    ("over", "match"),
    [
        ({"owner_keys": ["-----BEGIN OPENSSH " + "PRIVATE KEY----- abc"]}, "public keys"),
        ({"owner_keys": [OWNER_KEY, 'command="rm -rf /" ' + OWNER_KEY]}, "public keys"),
        ({"owner_keys": []}, "public keys"),
        ({"callback_token": "short"}, "one-time"),
        ({"callback_url": "http://hq.example.test/cb"}, "HTTPS"),
        ({"run_id": "run 1; rm -rf /"}, "bad run id"),
        ({"plan": make_plan(software=["rootkit"])}, "problems"),
    ],
)
def test_refused_inputs(over: dict[str, object], match: str) -> None:
    with pytest.raises(cloudinit.RenderError, match=match):
        render(**over)


def test_values_are_quoted_and_templates_take_no_input(tmp_path: Path) -> None:
    # A comment in the plan is not executed: it never reaches the script at all.
    plan = make_plan()
    plan["firewall"][0]["note_fa"] = "$(touch /tmp/pwned)"
    plan["digest"] = __import__("hq_common.provisioning", fromlist=["digest"]).digest(plan)
    assert "/tmp/pwned" not in render(plan=plan)
    # A key with a comment full of shell is quoted as one value.
    ud = render(owner_keys=[public_key(3, "a'b$(id)`x`")])
    assert "OWNER_KEYS='ssh-ed25519 " in ud and "'\"'\"'" in ud
    # A template that would end the heredoc early is refused.
    bad = tmp_path / "t"
    shutil.copytree(TEMPLATES, bad)
    (bad / "git.sh").write_text("step_git() { true; }\nCOINEPRO_PROVISION_EOF\n")
    with pytest.raises(cloudinit.RenderError, match="end marker"):
        render(templates=bad)


@pytest.mark.skipif(shutil.which("bash") is None, reason="no bash in this image")
def test_the_rendered_scripts_parse(tmp_path: Path) -> None:
    ud = render()
    outer = tmp_path / "user-data.sh"
    outer.write_text(ud)
    subprocess.run([BASH, "-n", str(outer)], check=True)
    inner = ud.split("<<'COINEPRO_PROVISION_EOF'\n", 1)[1].split("\nCOINEPRO_PROVISION_EOF\n", 1)[0]
    (tmp_path / "inner.sh").write_text(inner)
    subprocess.run([BASH, "-n", str(tmp_path / "inner.sh")], check=True)
