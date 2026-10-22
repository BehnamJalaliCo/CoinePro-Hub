"""hq_common.provisioning: the seal's digest and what a plan may contain."""

from __future__ import annotations

import copy

import pytest
from prov_support import make_plan

from hq_common import provisioning as P


def test_the_digest_covers_the_plan_and_nothing_else() -> None:
    plan = make_plan()
    d = plan["digest"]
    # State, decision and run change as the plan moves on; the seal does not.
    moved = {**plan, "state": "running", "decision_ref": "D-000999", "run": "r1", "digest": "x"}
    assert P.digest(moved) == d
    # Any real change voids it: a port, a source, a key, the type.
    for change in (
        lambda p: p["firewall"][0].update(port="2222"),
        lambda p: p["firewall"][0]["sources"].append("0.0.0.0/0"),
        lambda p: p["software"].remove("docker"),
        lambda p: p.update(type="ccx33"),
        lambda p: p.update(work_user="other"),
    ):
        p = copy.deepcopy(plan)
        change(p)
        assert P.digest(p) != d
    # Canonical: key order and spacing do not matter; Persian stays UTF-8.
    assert P.digest(dict(reversed(list(plan.items())))) == d
    assert "SSH مالک".encode() in P.canonical(plan)


def test_a_good_plan_has_no_problems_and_runs_in_the_fixed_order() -> None:
    plan = make_plan(
        software=[
            "claude-code", "node-lts", "work-user", "ssh-hardening", "system-upgrade",
            "unattended-upgrades",
        ]
    )  # fmt: skip
    assert P.problems(plan) == []
    assert P.ordered(plan["software"]) == [
        "system-upgrade",
        "unattended-upgrades",
        "work-user",
        "ssh-hardening",
        "node-lts",
        "claude-code",
    ]


def rule(port: str | None, *sources: str, proto: str = "tcp") -> dict[str, object]:
    return {"direction": "in", "protocol": proto, "port": port, "sources": list(sources)}


OWNER_SSH = rule("22", "198.51.100.7/32")


@pytest.mark.parametrize(
    ("firewall", "fragment"),
    [
        # Review 9.2 §2.1: SSH reached through a wide range beside a good 22 rule.
        ([OWNER_SSH, rule("1-65535", "0.0.0.0/0", "::/0")], "SSH open to the whole internet"),
        # ... or the whole internet in two halves.
        ([rule("22", "0.0.0.0/1", "128.0.0.0/1")], "SSH open to the whole internet"),
        # ... or in two rules: all the rules of a port together.
        (
            [OWNER_SSH, rule("8080", "0.0.0.0/1"), rule("8000-8100", "128.0.0.0/1")],
            "tcp 8080 open to the whole internet",
        ),
        ([OWNER_SSH, rule("53", "::/0", proto="udp")], "udp 53 open to the whole internet"),
        ([OWNER_SSH, rule(None, "0.0.0.0/0", proto="icmp")], "icmp open to the whole internet"),
        ([OWNER_SSH, rule("80-443", "0.0.0.0/0")], "tcp 81-442 open to the whole internet"),
        ([rule("22", "::ffff:0:0/96")], "IPv4-mapped"),
        ([rule("443", "0.0.0.0/0")], "no rule for SSH"),
    ],
)
def test_nothing_but_80_and_443_is_open_to_the_world(
    firewall: list[dict[str, object]], fragment: str
) -> None:
    problems = P.problems(make_plan(firewall=firewall))
    assert any(fragment in p for p in problems), problems


def test_80_and_443_may_be_open_to_the_world() -> None:
    plan = make_plan(
        firewall=[OWNER_SSH, rule("80", "0.0.0.0/0", "::/0"), rule("443", "0.0.0.0/0", "::/0"),
                  rule("443", "::/0", proto="udp")]  # fmt: skip
    )
    assert P.problems(plan) == []


def test_ssh_comes_only_from_the_owners_addresses() -> None:
    owner = ["198.51.100.0/24", "2001:db8:7::/48"]
    assert P.problems(make_plan(), ssh_sources=owner) == []
    # Any tcp range that contains 22 is SSH: its sources too.
    for fw in (
        [rule("22", "203.0.113.5/32")],
        [OWNER_SSH, rule("20-30", "203.0.113.0/24")],
        [rule("22", "198.51.100.0/23")],  # wider than the owner's
        [rule("22", "2001:db8::/32")],
    ):
        problems = P.problems(make_plan(firewall=fw), ssh_sources=owner)
        assert any("outside the owner's addresses" in p for p in problems), (fw, problems)
    assert P.problems(make_plan(firewall=[rule("22", "2001:db8:7:1::/64")]), ssh_sources=owner) == []
    # No owner's address yet: no SSH at all can be sealed.
    problems = P.problems(make_plan(), ssh_sources=[])
    assert any("needs the owner's addresses first" in p for p in problems)
    # A port range without 22 is not SSH.
    assert not P.is_ssh(rule("23-8000", "0.0.0.0/32")) and P.is_ssh(rule("1-22", "1.2.3.4/32"))


@pytest.mark.parametrize(
    "user",
    ["mail", "proxy", "backup", "news", "list", "irc", "games", "man", "lp", "uucp", "syslog",
     "tss", "www-data", "docker", "prometheus", "systemd-foo", "sudo", "adm"],
)  # fmt: skip
def test_the_work_user_is_never_a_system_account(user: str) -> None:
    problems = P.problems(make_plan(work_user=user))
    assert any("work_user" in p for p in problems), problems


def test_the_default_work_user_is_code_ops() -> None:
    for code in ("MAIL", "PROXY", "BACKUP", "TSS", "NX", "LP"):
        user = P.default_work_user(code)
        assert user == f"{code.lower()}-ops" and not P.system_name(user)
        assert P.problems(make_plan(work_user=user)) == []


def test_hardening_updates_and_the_work_user_are_always_in_a_plan() -> None:
    for key in P.REQUIRED:
        software = [k for k in P.SOFTWARE if k != key]
        problems = P.problems(make_plan(software=software))
        assert any("always in a plan" in p and key in p for p in problems), problems


def test_covers_everything() -> None:
    import ipaddress

    nets = [ipaddress.ip_network(n) for n in ("0.0.0.0/2", "64.0.0.0/2", "128.0.0.0/1")]
    assert P.covers_everything(nets)  # type: ignore[arg-type]
    assert not P.covers_everything(nets[:2])  # type: ignore[arg-type]
    assert P.covers_everything([ipaddress.ip_network("::/1"), ipaddress.ip_network("8000::/1")])


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"software": ["system-upgrade", "rootkit"]}, "unknown keys rootkit"),
        ({"software": ["ssh-hardening"]}, "ssh-hardening needs work-user"),
        ({"software": ["claude-code", "work-user"]}, "claude-code needs node-lts"),
        (
            {"software": ["node-exporter", "private-network"], "private_network": False},
            "private-network needs private_network",
        ),
        ({"software": ["repo-clone", "git", "work-user"], "repo": None}, "repo-clone needs a repo"),
        ({"software": ["git", "git"]}, "a key twice"),
        ({"image": "debian-12"}, "image: only ubuntu-24.04"),
        ({"work_user": "root"}, "work_user"),
        ({"name": "Bad_Name"}, "name"),
        ({"location": "mars"}, "location"),
        (
            {
                "firewall": [
                    {"direction": "in", "protocol": "tcp", "port": "22", "sources": ["0.0.0.0/0"]}
                ]
            },
            "SSH open to the whole internet",
        ),
        (
            {
                "firewall": [
                    {
                        "direction": "out",
                        "protocol": "tcp",
                        "port": "443",
                        "sources": ["10.0.0.0/8"],
                    }
                ]
            },
            "only 'in'",
        ),
        (
            {
                "firewall": [
                    {"direction": "in", "protocol": "tcp", "port": "443", "sources": ["0.0.0.0/0"]}
                ]
            },
            "no rule for SSH",
        ),
        (
            {
                "firewall": [
                    {
                        "direction": "in",
                        "protocol": "tcp",
                        "port": "70000",
                        "sources": ["1.2.3.4/32"],
                    }
                ]
            },
            "a port or a range",
        ),
        (
            {
                "firewall": [
                    {"direction": "in", "protocol": "tcp", "port": "22", "sources": ["1.2.3.4/24"]}
                ]
            },
            "is not a CIDR",
        ),
    ],
)
def test_what_a_plan_may_not_contain(change: dict[str, object], fragment: str) -> None:
    problems = P.problems(make_plan(**change))
    assert any(fragment in p for p in problems), problems


def test_labels_are_ours_and_valid() -> None:
    labels = P.labels(make_plan(), run="run-1")
    assert labels == {
        "managed-by": "coinepro-hq",
        "coinepro-hq/plan": "pv-0001",
        "coinepro-hq/company": "nx",
        "coinepro-hq/run": "run-1",
    }
    with pytest.raises(ValueError, match="cannot label"):
        P.label_value("---")
