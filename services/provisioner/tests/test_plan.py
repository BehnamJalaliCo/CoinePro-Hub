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
        software=["claude-code", "node-lts", "work-user", "ssh-hardening", "system-upgrade"]
    )
    assert P.problems(plan) == []
    assert P.ordered(plan["software"]) == [
        "system-upgrade",
        "work-user",
        "ssh-hardening",
        "node-lts",
        "claude-code",
    ]


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
