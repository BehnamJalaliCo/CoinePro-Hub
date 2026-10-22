"""One run of one SEALED plan, step by step (contract §18.8 ProvisionRun):

ssh-key -> firewall -> server -> boot -> cloud-init -> verify -> login

Before any Hetzner call the plan's digest is recomputed (hq_common.provisioning)
and must equal the one the owner sealed: a plan changed after the seal never
runs. Every step is reported to the hub (running, done or failed, with a short
log); a failed run stops there and can be handed out again: the Hetzner steps
find what they made by its labels, done steps are not repeated, nothing is
made twice and nothing is ever deleted.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from hq_common import provisioning as P
from hq_provisioner import cloudinit
from hq_provisioner.config import Settings
from hq_provisioner.hetzner import Built, Hetzner, Refused, message
from hq_provisioner.hub import Hub
from hq_provisioner.vault import NotConfigured, Secrets

log = logging.getLogger("hq_provisioner.runner")

STEPS: tuple[tuple[str, str], ...] = (
    ("ssh-key", "کلید SSH مالک"),
    ("firewall", "فایروال هتزنر"),
    ("server", "ساخت سرور"),
    ("boot", "روشن شدن"),
    ("cloud-init", "نصب‌ها روی سرور"),
    ("verify", "بررسی نسخه‌ها و سخت‌سازی"),
    ("login", "آماده‌ی ورود مالک"),
)


class StepFailed(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Runner:
    def __init__(
        self,
        settings: Settings,
        secrets_: Secrets,
        hub: Hub,
        hetzner: Callable[[str], Hetzner] | None = None,
        *,
        pins: cloudinit.Pins | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.s = settings
        self.secrets = secrets_
        self.hub = hub
        self.hetzner = hetzner or (
            lambda token: Hetzner(token, settings.hetzner_url, settings.hetzner_poll_s)
        )
        self.pins = pins
        self.sleep = sleep

    # ----------------------------------------------------------------- loop --
    def tick(self) -> bool:
        """Run the next sealed plan, if there is one."""
        run = self.hub.next_run()
        if run is None:
            return False
        self.execute(run)
        return True

    def execute(self, run: dict[str, Any]) -> str:
        run_id = str(run["id"])
        plan = dict(run.get("plan") or {})
        sealed = str(run.get("sealed_digest") or "")
        # The seal, again, here: nothing is touched for a plan that differs.
        if not sealed or P.digest(plan) != sealed or plan.get("digest") != sealed:
            return self._fail(
                run_id, "ssh-key", "seal_mismatch", "the plan is not the one the owner sealed"
            )
        # The owner's SSH addresses as the api knows them (§18.16): every SSH
        # source of the plan lies inside them, checked here too.
        sources = run.get("ssh_sources")
        problems = P.problems(plan, ssh_sources=sources if isinstance(sources, list) else None)
        if problems:
            return self._fail(run_id, "ssh-key", "plan_invalid", "; ".join(problems)[:300])
        done = {s.get("key") for s in run.get("steps") or [] if s.get("state") == "done"}
        try:
            keys = self.secrets.owner_keys()
            hz = self.hetzner(self.secrets.hetzner_token())
        except NotConfigured as exc:
            return self._fail(run_id, "ssh-key", "not_configured", str(exc))
        except Exception as exc:  # noqa: BLE001 - OpenBao sealed or down: reported, resumable
            return self._fail(run_id, "ssh-key", "not_configured", message(exc))
        labels = P.labels(plan)
        ctx: dict[str, Any] = {"labels": labels, "keys": keys}
        for key, _title in STEPS:
            started = now()
            try:
                if key not in done:
                    self.hub.step(run_id, {"key": key, "state": "running", "started_at": started})
                notes = getattr(self, "_" + key.replace("-", "_"))(
                    hz, run_id, plan, ctx, key in done
                )
            except StepFailed as exc:
                return self._fail(run_id, key, exc.code, exc.detail, started)
            except Refused as exc:
                return self._fail(run_id, key, "refused", str(exc), started)
            except NotConfigured as exc:
                return self._fail(run_id, key, "not_configured", str(exc), started)
            except Exception as exc:  # noqa: BLE001 - Hetzner or the hub: reported, resumable
                return self._fail(run_id, key, "error", message(exc), started)
            if key not in done:
                try:
                    self.hub.step(
                        run_id,
                        {
                            "key": key,
                            "state": "done",
                            "started_at": started,
                            "finished_at": now(),
                            "log_tail": [n[:300] for n in notes][-10:],
                        },
                    )
                except Exception as exc:  # noqa: BLE001 - the hub: reported, resumable
                    return self._fail(run_id, key, "error", message(exc), started)
        try:
            self.hub.finish(run_id, {"state": "done", "login": ctx["login"]})
        except Exception as exc:  # noqa: BLE001 - the api's reaper fails the run later
            log.warning(
                "provisioning: done, not reported", extra={"run": run_id, "detail": message(exc)}
            )
            return "unreported"
        log.info("provisioned", extra={"run": run_id, "plan": plan["ref"]})
        return "done"

    def _fail(
        self, run_id: str, key: str, code: str, detail: str, started: str | None = None
    ) -> str:
        """The step and the run as failed. Never raises: if the hub cannot be
        told, the run stays `running` and the api's reaper fails it after its
        quiet time (review 9.2 §2.3)."""
        log.warning("provisioning step failed", extra={"run": run_id, "step": key, "code": code})
        try:
            self.hub.step(
                run_id,
                {
                    "key": key,
                    "state": "failed",
                    "started_at": started or now(),
                    "finished_at": now(),
                    "log_tail": [f"{code}: {detail}"[:300]],
                },
            )
            self.hub.finish(run_id, {"state": "failed", "error": {"step": key, "code": code}})
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "provisioning: the failure was not reported",
                extra={"run": run_id, "step": key, "detail": message(exc)},
            )
            return "unreported"
        return "failed"

    # ---------------------------------------------------------------- steps --
    def _ssh_key(
        self, hz: Hetzner, run_id: str, plan: dict[str, Any], ctx: dict[str, Any], _done: bool
    ) -> list[str]:
        ctx["ssh_keys"], notes = hz.ssh_keys(ctx["keys"], ctx["labels"])
        return notes

    def _firewall(
        self, hz: Hetzner, run_id: str, plan: dict[str, Any], ctx: dict[str, Any], _done: bool
    ) -> list[str]:
        ctx["firewall"], note = hz.firewall(plan, ctx["labels"])
        notes = [note]
        ctx["network"] = None
        if plan.get("private_network"):
            ctx["network"], n = hz.network(plan, ctx["labels"], self.s.network_range)
            notes.append(n)
        return notes

    def _server(
        self, hz: Hetzner, run_id: str, plan: dict[str, Any], ctx: dict[str, Any], done: bool
    ) -> list[str]:
        server = hz.find_server(ctx["labels"])
        if server is None and done:
            # Made before and gone now (removed in the Hetzner console): never
            # made again on our own; a new server is a new sealed plan.
            raise StepFailed("server_gone", "the plan's server no longer exists in the project")
        if server is not None:
            ctx["server"] = hz.built(server)
            return [f"server {server.name} (ours) already exists: resumed, not made again"]
        # The one-time callback token: made here, its sha256 to the hub, the
        # plaintext only into this server's user data.
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(UTC) + timedelta(seconds=self.s.callback_ttl_s)).isoformat(
            timespec="seconds"
        )
        self.hub.callback(run_id, hashlib.sha256(token.encode()).hexdigest(), expires)
        user_data = cloudinit.render(
            plan,
            run_id=run_id,
            owner_keys=ctx["keys"],
            callback_url=self.s.callback_url,
            callback_token=token,
            templates=self.s.templates_dir,
            pins=self.pins,
        )
        del token
        server = hz.create_server(
            plan,
            ctx["labels"],
            user_data=user_data,
            ssh_keys=ctx["ssh_keys"],
            firewall=ctx["firewall"],
            network=ctx["network"],
        )
        ctx["server"] = hz.built(server, created=True)
        where = f"{plan['type']}, {plan['location']}, {P.IMAGE}"
        n = len(P.ordered(plan["software"]))
        return [
            f"server {plan['name']} created ({where}), no root password",
            f"user data {len(user_data.encode())} bytes: the plan's {n} software step(s)",
        ]

    def _boot(
        self, hz: Hetzner, run_id: str, plan: dict[str, Any], ctx: dict[str, Any], _done: bool
    ) -> list[str]:
        b: Built = ctx["server"]
        server = hz.wait_running(b.id, self.s.boot_wait_s)
        ctx["server"] = b = hz.built(server, created=b.created)
        self.hub.server(
            run_id,
            {
                "hetzner_id": b.id,
                "name": b.name,
                "ipv4": b.ipv4,
                "ipv6": b.ipv6,
                "private_ip": b.private_ip,
                "labels": b.labels,
            },
        )
        # No SSH from the hub (no route, by design): the server's own callback
        # (next step) proves sshd is up with the hardened config.
        return [
            f"running: {b.ipv4 or '-'} / {b.ipv6 or '-'}"
            + (f", private {b.private_ip}" if b.private_ip else "")
        ]

    def _cloud_init(
        self, hz: Hetzner, run_id: str, plan: dict[str, Any], ctx: dict[str, Any], _done: bool
    ) -> list[str]:
        deadline = time.monotonic() + self.s.callback_wait_s
        while True:
            state = self.hub.run(run_id)
            ci = state.get("cloud_init") or {}
            if ci.get("received_at"):
                ctx["cloud_init"] = ci
                return [f"the server reported at {ci['received_at']}"]
            if time.monotonic() > deadline:
                raise StepFailed(
                    "callback_timeout", "no report from the server within its token's 60 minutes"
                )
            self.sleep(self.s.poll_s)

    def _verify(
        self, hz: Hetzner, run_id: str, plan: dict[str, Any], ctx: dict[str, Any], _done: bool
    ) -> list[str]:
        ci = ctx.get("cloud_init") or (self.hub.run(run_id).get("cloud_init") or {})
        results = {r.get("key"): r for r in ci.get("results") or [] if isinstance(r, dict)}
        wanted = P.ordered(plan["software"])
        missing = [k for k in wanted if k not in results]
        failed = [k for k in wanted if k in results and not results[k].get("ok")]
        notes = [
            f"{k}: {results[k].get('version') or 'ok'}"
            + (f" ({results[k]['note']})" if results[k].get("note") else "")
            for k in wanted
            if k in results
        ]
        if failed or missing or ci.get("failed"):
            raise StepFailed(
                "verify_failed",
                "; ".join(
                    ([f"failed: {', '.join(failed)}"] if failed else [])
                    + ([f"not run: {', '.join(missing)}"] if missing else [])
                )
                or "the server reported a failure",
            )
        if ci.get("deploy_key"):
            notes.append(
                "deploy key for the repo (add it read-only): " + str(ci["deploy_key"])[:200]
            )
        return notes

    def _login(
        self, hz: Hetzner, run_id: str, plan: dict[str, Any], ctx: dict[str, Any], _done: bool
    ) -> list[str]:
        b: Built = ctx["server"]
        then = ["claude"] if "claude-code" in plan["software"] else []
        ctx["login"] = {"ssh": f"ssh {plan['work_user']}@{b.ipv4 or b.ipv6}", "then": then}
        return [ctx["login"]["ssh"], *then]
