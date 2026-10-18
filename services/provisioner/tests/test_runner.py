"""The provisioner's run against a mock Hetzner (prompt 09 §4 acceptance):
nothing without the seal, nothing unlabelled touched, no root password, every
step reported, a failed step resumable, nothing made twice or deleted."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from prov_fake_hetzner import FakeHetzner
from prov_support import (  # noqa: F401 - pytest fixtures
    HETZNER_TOKEN,
    OWNER_KEY,
    FakeApi,
    Secrets,
    api_fixture,
    fake_fixture,
    make_plan,
    secrets_fixture,
    settings_fixture,
)

from hq_common import provisioning as P
from hq_provisioner import cloudinit
from hq_provisioner.config import Settings
from hq_provisioner.hetzner import Hetzner, fingerprint
from hq_provisioner.runner import STEPS, Runner

ALL = [k for k, _ in STEPS]


def runner(settings: Settings, secrets_: Secrets, api: FakeApi) -> Runner:
    return Runner(
        settings, secrets_, api.hub(), sleep=lambda _s: None, pins=cloudinit.Pins(wait_s=1)
    )


def created(fake: FakeHetzner, kind: str) -> list[dict[str, Any]]:
    return [b for m, p, b in fake.requests if m == "POST" and p == f"/v1/{kind}"]


def test_a_sealed_plan_is_built_step_by_step(
    fake: FakeHetzner, api: FakeApi, secrets_: Secrets, settings: Settings
) -> None:
    plan = make_plan()
    rid = api.add(plan)
    r = runner(settings, secrets_, api)
    assert r.tick() is True and r.tick() is False  # one run, then nothing to do
    assert api.step_states(rid) == [x for k in ALL for x in ((k, "running"), (k, "done"))]
    assert api.finished == [{"run": rid, "state": "done",
                             "login": {"ssh": "ssh nx@" + api.servers[0]["ipv4"], "then": ["claude"]}}]  # fmt: skip
    # The server: the plan's type, place and image, the owner's key, labelled, no root password.
    [srv] = created(fake, "servers")
    assert (srv["name"], srv["server_type"], srv["location"], srv["image"]) == (
        "nx-app-1",
        "cpx42",
        "fsn1",
        "ubuntu-24.04",
    )
    assert srv["labels"] == {
        "managed-by": "coinepro-hq",
        "coinepro-hq/plan": "pv-0001",
        "coinepro-hq/company": "nx",
    }
    assert len(srv["ssh_keys"]) == 1 and srv["firewalls"] and srv["networks"]
    assert "root_password" not in json.dumps(srv) and "password" not in srv
    # The firewall: exactly the sealed rules, labelled; the company's own network.
    [fw] = created(fake, "firewalls")
    assert fw["labels"]["managed-by"] == "coinepro-hq"
    assert [(x["port"], x["source_ips"]) for x in fw["rules"]] == [
        ("22", ["198.51.100.7/32"]),
        ("443", ["0.0.0.0/0", "::/0"]),
    ]
    [net] = created(fake, "networks")
    assert net["name"] == "coinepro-hq-nx" and net["subnets"][0]["network_zone"] == "eu-central"
    # The callback token: only its sha256 went to the hub; the plaintext only into the user data.
    [cb] = api.callbacks
    token = srv["user_data"].split("printf '%s' ", 1)[1].split(" ", 1)[0].strip("'")
    assert cb["token_sha256"] == hashlib.sha256(
        token.encode()
    ).hexdigest() and token not in json.dumps(cb)
    # Nothing secret anywhere the hub or Hetzner logs: the Hetzner token went in a header only.
    reported = json.dumps([api.steps, api.servers, api.finished])
    assert HETZNER_TOKEN not in reported and token not in reported
    assert HETZNER_TOKEN not in json.dumps([b for _, _, b in fake.requests])
    assert api.auth == {"Bearer svc-provisioner-token"}
    # The deploy key the server reported is shown for the owner to add (public half only).
    verify = next(s for s in api.steps if s["key"] == "verify" and s["state"] == "done")
    assert any("deploy key" in line and "ssh-ed25519" in line for line in verify["log_tail"])


def test_without_the_seal_nothing_is_called(
    fake: FakeHetzner, api: FakeApi, secrets_: Secrets, settings: Settings
) -> None:
    plan = make_plan()
    unsealed = api.add(plan, sealed="")
    changed = dict(plan, type="ccx63")  # changed after the owner saw it; digest left stale
    tampered = api.add(changed)
    r = runner(settings, secrets_, api)
    r.tick()
    r.tick()
    assert fake.requests == [] and secrets_.reads == 0  # no Hetzner call, not even the token read
    assert [f["error"]["code"] for f in api.finished] == ["seal_mismatch", "seal_mismatch"]
    assert {f["run"] for f in api.finished} == {unsealed, tampered}


def test_existing_resources_without_our_label_are_never_touched(
    fake: FakeHetzner, api: FakeApi, secrets_: Secrets, settings: Settings
) -> None:
    # The project already holds the hub, its production neighbours, a firewall
    # of theirs and the owner's own upload of the same public key.
    neighbours = [fake.seed_server(n) for n in ("hub", "pro-chart", "coinepro-fx", "tradeyar")]
    theirs = fake.seed_firewall("neighbours")
    owner_key = fake.seed_ssh_key("owner-laptop", OWNER_KEY, fingerprint(OWNER_KEY))
    rid = api.add(make_plan())
    runner(settings, secrets_, api).tick()
    assert api.finished[-1]["state"] == "done"
    touched = {p for m, p in fake.writes()}
    for sid in neighbours:
        assert not any(f"/servers/{sid}" in p for p in touched)
    assert not any(f"/firewalls/{theirs}" in p for p in touched)
    assert created(fake, "ssh_keys") == []  # the owner's key is used as it is
    assert created(fake, "servers")[0]["ssh_keys"] == [owner_key]
    # No delete, rebuild or power action exists in what was sent.
    assert not [m for m, _ in fake.writes() if m in ("DELETE", "PUT")]
    assert not [
        p
        for _, p in fake.writes()
        if any(a in p for a in ("rebuild", "poweroff", "reset", "rescue", "delete"))
    ]
    assert rid in {f["run"] for f in api.finished}


@pytest.mark.parametrize(
    ("step", "path"),
    [("ssh-key", r"/v1/ssh_keys"), ("firewall", r"/v1/firewalls"), ("server", r"/v1/servers")],
)
def test_a_failed_step_is_reported_and_resumable(
    fake: FakeHetzner, api: FakeApi, secrets_: Secrets, settings: Settings, step: str, path: str
) -> None:
    fake.fail[("POST", path)] = 1
    plan = make_plan()
    rid = api.add(plan)
    r = runner(settings, secrets_, api)
    r.tick()
    assert api.finished[-1]["state"] == "failed" and api.finished[-1]["error"]["step"] == step
    failed = [s for s in api.steps if s["state"] == "failed"]
    assert failed[-1]["key"] == step and "Hetzner" in failed[-1]["log_tail"][0]
    # The hub hands the run out again, with the steps it already has as done.
    done = [{"key": k, "state": s} for k, s in api.step_states(rid) if s == "done"]
    api.runs[rid]["steps"] = done
    api.queue.append(rid)
    r.tick()
    assert api.finished[-1]["state"] == "done"
    # Nothing was made twice (the failed POST made nothing).
    assert (len(fake.servers), len(fake.firewalls), len(fake.networks)) == (1, 1, 1)


def test_resuming_after_the_server_exists_never_makes_another(
    fake: FakeHetzner, api: FakeApi, secrets_: Secrets, settings: Settings
) -> None:
    api.polls_until_callback = 10**6  # the server never reports: cloud-init times out
    settings = Settings(**{**settings.__dict__, "callback_wait_s": 0.0})
    plan = make_plan()
    rid = api.add(plan)
    r = runner(settings, secrets_, api)
    r.tick()
    assert api.finished[-1]["error"] == {"step": "cloud-init", "code": "callback_timeout"}
    api.polls_until_callback = 0
    api.runs[rid]["steps"] = [
        {"key": k, "state": "done"} for k in ("ssh-key", "firewall", "server", "boot")
    ]
    api.queue.append(rid)
    r.tick()
    assert api.finished[-1]["state"] == "done"
    assert (
        len(created(fake, "servers")) == 1 and len(api.callbacks) == 1
    )  # the token stays the one in the user data


def test_a_server_made_before_and_gone_now_is_not_made_again(
    fake: FakeHetzner, api: FakeApi, secrets_: Secrets, settings: Settings
) -> None:
    rid = api.add(
        make_plan(), steps=[{"key": k, "state": "done"} for k in ("ssh-key", "firewall", "server")]
    )
    runner(settings, secrets_, api).tick()
    assert api.finished[-1]["error"] == {"step": "server", "code": "server_gone"}
    assert created(fake, "servers") == [] and rid


def test_a_root_password_from_hetzner_stops_the_run(
    fake: FakeHetzner, api: FakeApi, secrets_: Secrets, settings: Settings
) -> None:
    fake.root_password = "Zr7-" + "x" * 20
    api.add(make_plan())
    runner(settings, secrets_, api).tick()
    assert api.finished[-1]["error"] == {"step": "server", "code": "refused"}
    assert fake.root_password not in json.dumps(api.steps)


def test_not_configured_and_a_failed_report(
    fake: FakeHetzner, api: FakeApi, secrets_: Secrets, settings: Settings
) -> None:
    secrets_.token = None
    api.add(make_plan())
    r = runner(settings, secrets_, api)
    r.tick()
    assert api.finished[-1]["error"]["code"] == "not_configured" and fake.requests == []
    secrets_.token = HETZNER_TOKEN
    plan = make_plan()
    report = api.ok_report(plan)
    report["results"][3] = {"key": "ssh-hardening", "ok": False, "version": None, "note": "failed"}
    api.report = report
    api.add(plan)
    r.tick()
    assert api.finished[-1]["error"] == {"step": "verify", "code": "verify_failed"}
    failed = [s for s in api.steps if s["state"] == "failed"][-1]
    assert "ssh-hardening" in failed["log_tail"][0]


def test_pricing_and_the_project_listing(fake: FakeHetzner) -> None:
    hz = Hetzner(HETZNER_TOKEN, fake.url, poll_s=0.01)  # type: ignore[attr-defined]
    price = hz.pricing("cpx42", "fsn1")
    assert price["monthly_eur"] == "26.99" and price["server_monthly_net"] == "26.49"
    assert price["ipv4_monthly_net"] == "0.50" and price["currency"] == "EUR"
    with pytest.raises(LookupError):
        hz.pricing("cpx42", "sin")
    fake.seed_server("hub")
    ours = fake.seed_server("nx-app-1", P.labels(make_plan()))
    listing = {s["id"]: s for s in hz.servers()}
    assert listing[ours]["ours"] is True and listing[ours]["plan"] == "pv-0001"
    assert [s["ours"] for s in listing.values()].count(False) == 1
