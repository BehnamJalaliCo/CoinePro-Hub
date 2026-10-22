"""What a provisioned bench server must look like (run as root inside it):

    check.py done <work_user> <steps...>       every step ok, one callback
    check.py failed <work_user> <failed_step>  stopped there, the callback says so
                                               (and, per step, nothing it guards ran)
    check.py rebooted                           the upgrade's single reboot

Prints one line per check; exits non-zero on the first that fails.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

STATE = Path("/var/lib/coinepro-provision")
OUT = Path("/bench/out")


def ok(cond: bool, what: str) -> None:
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        sys.exit(1)


def results() -> dict[str, dict[str, object]]:
    lines = (STATE / "results.jsonl").read_text().splitlines()
    return {r["key"]: r for r in (json.loads(x) for x in lines if x.strip())}


def callbacks() -> list[dict[str, object]]:
    return [json.loads(p.read_text()) for p in sorted(OUT.glob("callback-*.json"))]


def done(user: str, steps: list[str]) -> None:
    r = results()
    for key in steps:
        ok(bool(r.get(key, {}).get("ok")), f"step {key}: ok ({r.get(key, {}).get('version')})")
    ok(not (STATE / "failed").exists(), "no step failed")
    cbs = callbacks()
    ok(len(cbs) == 1, f"one callback to the hub (got {len(cbs)})")
    cb = cbs[0]
    body = cb["body"]
    ok(isinstance(cb["authorization"], str) and cb["authorization"].startswith("Bearer "),
       "the token went in the Authorization header")  # fmt: skip
    ok(cb["path"] == "/cb", "not in the URL")
    ok([x["key"] for x in body["results"]] == steps, "the callback lists every step in order")
    ok(body["failed"] is False and body["run"] == "run-bench", "the run, not failed")
    ok(not (STATE / "callback.token").exists(), "the one-time token is gone from the server")
    ok(body["ssh_host_keys"] and all(k.startswith(("ssh-", "ecdsa-")) for k in body["ssh_host_keys"]),
       "the server's host keys are reported (for the owner's first login)")  # fmt: skip
    raw = json.dumps(cbs)
    ok("PRIVATE" not in raw, "no private key in what the server sent")
    if "work-user" in steps:
        home = Path(f"/home/{user}")
        keys = (home / ".ssh/authorized_keys").read_text().split("\n")
        ok(any(k.startswith("ssh-ed25519 ") for k in keys), "the owner's public key is the work user's")
        st = subprocess.run(["passwd", "-S", user], capture_output=True, text=True, check=True)
        ok(st.stdout.split()[1] == "L", "the work user has no password (locked)")
        sudo = Path(f"/etc/sudoers.d/90-coinepro-{user}")
        ok(subprocess.run(["visudo", "-cqf", str(sudo)], check=False).returncode == 0, "sudoers valid")
    if "ssh-hardening" in steps:
        conf = Path("/etc/ssh/sshd_config.d/10-coinepro.conf").read_text()
        for line in ("PermitRootLogin no", "PasswordAuthentication no", f"AllowUsers {user}"):
            ok(line in conf, f"sshd: {line}")
        ok(subprocess.run(["sshd", "-t"], check=False).returncode == 0, "sshd -t accepts the config")
        st = subprocess.run(["passwd", "-S", "root"], capture_output=True, text=True, check=True)
        ok(st.stdout.split()[1] == "L", "root has no usable password")
        ok(not Path("/root/.ssh/authorized_keys").exists(), "root takes no key login")
    if "docker" in steps:
        ok(Path("/etc/apt/keyrings/docker.gpg").exists(), "Docker's key (fingerprint checked) is trusted")
    if "node-lts" in steps:
        v = subprocess.run(["/usr/local/bin/node", "--version"], capture_output=True, text=True, check=True)
        ok(v.stdout.strip() == "v24.21.0", f"node {v.stdout.strip()} (the pinned build, sha256 checked)")
    if "claude-code" in steps:
        ok(r["claude-code"]["version"].startswith("2.1.294"), "Claude Code, the pinned version")  # type: ignore[union-attr]
    if "repo-clone" in steps:
        ok(Path(f"/home/{user}/.ssh/coinepro_deploy.pub").exists(), "a deploy key made on the server")
        ok(body["deploy_key"] and body["deploy_key"].startswith("ssh-ed25519 "), "its PUBLIC half reported")
    if "node-exporter" in steps:
        ok("10.20.1.2:9100" in Path("/etc/default/prometheus-node-exporter").read_text(),
           "node-exporter on the private address only")  # fmt: skip
    if "chatwoot" in steps:
        env = Path("/opt/chatwoot/.env")
        ok(env.stat().st_mode & 0o077 == 0, "chatwoot: its secrets are root's only (0600)")
        lines = dict(x.split("=", 1) for x in env.read_text().splitlines() if "=" in x)
        ok(len(lines.get("SECRET_KEY_BASE", "")) == 128, "chatwoot: SECRET_KEY_BASE made on the server")
        ok(Path("/opt/chatwoot/docker-compose.yml").exists(), "chatwoot: the Community compose is written")
        docker = Path("/bench/log/docker").read_text() if Path("/bench/log/docker").exists() else ""
        ok("compose up" not in docker and "compose pull" not in docker,
           "chatwoot: nothing started at build time (the owner's chatwoot-start does)")  # fmt: skip
        ok(Path("/usr/local/sbin/chatwoot-start").stat().st_mode & 0o777 == 0o750, "chatwoot-start")
    ok(Path("/var/log/coinepro-provision.log").stat().st_mode & 0o077 == 0, "the log is root's only")
    systemctl = Path("/bench/log/systemctl").read_text() if Path("/bench/log/systemctl").exists() else ""
    ok("reboot" not in systemctl or (STATE / "rebooted").exists(), "no reboot unless the upgrade needed it")


def failed(user: str, step: str) -> None:
    r = results()
    ok(r.get(step, {}).get("ok") is False, f"{step} reported as failed")
    ok((STATE / "failed").exists(), "the run knows it failed")
    ok(not (STATE / f"{step}.done").exists(), f"{step} is not marked done")
    cbs = callbacks()
    ok(len(cbs) == 1 and cbs[0]["body"]["failed"] is True, "the hub was told: failed")
    order = list(r)
    ok(order[-1] == step, "the steps after it did not run")
    systemctl = Path("/bench/log/systemctl").read_text() if Path("/bench/log/systemctl").exists() else ""
    if step == "node-lts":
        ok(not Path("/usr/local/bin/node").exists(), "no node installed from the tampered tarball")
        ok(not list(Path("/usr/local/lib").glob("nodejs/node-v*")), "nothing of it unpacked")
        ok(not (STATE / "node.tar.xz").exists(), "the tampered tarball is gone")
    if step in ("work-user", "ssh-hardening"):
        # Root keeps its key login: nothing that would lock the owner out ran.
        ok(Path("/root/.ssh/authorized_keys").exists(), "root's authorized_keys are untouched")
        ok("reload ssh" not in systemctl and "restart ssh" not in systemctl, "ssh was not reloaded")
        ok(not Path("/etc/ssh/sshd_config.d/10-coinepro.conf").exists(),
           "no hardened sshd config left behind")  # fmt: skip
    if step == "work-user":
        ok(not Path(f"/etc/sudoers.d/90-coinepro-{user}").exists(), "no sudo for the existing account")
        ok("ssh-hardening" not in r, "ssh-hardening did not run")


def rebooted() -> None:
    log = Path("/bench/log/systemctl").read_text()
    ok(log.count("reboot") == 1, "the upgrade rebooted this server once")
    ok("enable coinepro-provision.service" in log, "and set up the rest of the build after the boot")
    ok(callbacks() == [], "no callback before the build is complete")


if __name__ == "__main__":
    what = sys.argv[1]
    if what == "done":
        done(sys.argv[2], sys.argv[3:])
    elif what == "failed":
        failed(sys.argv[2], sys.argv[3])
    else:
        rebooted()
