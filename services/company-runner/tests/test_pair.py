from __future__ import annotations

import io
import json
import stat
from pathlib import Path

from conftest import FakeHub, make_route, run

from hq_runner.cli import pair, status, unpair
from hq_runner.config import load


async def instant(_: float) -> None:
    return None


def test_pair_pending_then_approved(fake_hub: FakeHub, cfg_path: Path) -> None:
    out = io.StringIO()
    code = run(
        pair(
            hub="https://hq.coinepro.test",
            hub_ip=None,
            company="FX",
            name="fx-main",
            cfg_path=cfg_path,
            route=make_route(fake_hub),
            sleep=instant,
            out=out,
        )
    )
    assert code == 0
    assert fake_hub.token_polls == 3  # two 428 authorization_pending, then the token
    text = out.getvalue()
    assert "ABCD-1234" in text
    assert "اپ ستاد" in text and "Approve this code in the HQ app" in text
    assert "hqr1_token_one" not in text  # the token is never printed
    cfg = load(cfg_path)
    assert cfg is not None and cfg.server_id == "srv-7" and cfg.company == "FX"
    assert stat.S_IMODE(cfg_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(cfg_path.parent.stat().st_mode) == 0o700
    pair_req = next(r for r in fake_hub.requests if r[1].endswith("/runners/pair"))
    assert pair_req[3]["company"] == "FX" and pair_req[3]["runner_version"]
    assert pair_req[2]["x-hq-runner-via"] == "public"
    assert "authorization" not in pair_req[2]


def test_pair_reports_private_route(fake_hub: FakeHub, cfg_path: Path) -> None:
    out = io.StringIO()
    code = run(
        pair(
            hub="https://hq.coinepro.test",
            hub_ip="10.10.1.4",
            company="FX",
            name="fx",
            cfg_path=cfg_path,
            route=make_route(fake_hub, "10.10.1.4"),
            sleep=instant,
            out=out,
        )
    )
    assert code == 0
    assert all(r[2]["x-hq-runner-via"] == "private" for r in fake_hub.requests)
    cfg = load(cfg_path)
    assert cfg is not None and cfg.hub_ip == "10.10.1.4"


def test_pair_expired_on_hub(cfg_path: Path) -> None:
    hub = FakeHub(expired=True)
    out = io.StringIO()
    code = run(
        pair(
            hub="https://hq.coinepro.test",
            hub_ip=None,
            company="FX",
            name="fx",
            cfg_path=cfg_path,
            route=make_route(hub),
            sleep=instant,
            out=out,
        )
    )
    assert code == 1
    assert "expired" in out.getvalue()
    assert not cfg_path.exists()


def test_pair_expires_locally_while_pending(cfg_path: Path) -> None:
    hub = FakeHub(approve_after=10**6, expires_in=5)
    ticks = iter(range(1000))
    out = io.StringIO()
    code = run(
        pair(
            hub="https://hq.coinepro.test",
            hub_ip=None,
            company="FX",
            name="fx",
            cfg_path=cfg_path,
            route=make_route(hub),
            sleep=instant,
            out=out,
            clock=lambda: float(next(ticks)),
        )
    )
    assert code == 1
    assert 1 <= hub.token_polls <= 6
    assert not cfg_path.exists()


def test_status_and_unpair_never_print_the_token(fake_hub: FakeHub, cfg_path: Path) -> None:
    run(
        pair(
            hub="https://hq.coinepro.test",
            hub_ip=None,
            company="FX",
            name="fx-main",
            cfg_path=cfg_path,
            route=make_route(fake_hub),
            sleep=instant,
            out=io.StringIO(),
        )
    )
    state = cfg_path.with_name("state.json")
    state.write_text(
        json.dumps({"state": "online", "via": "private", "hub_rtt_ms": 0.4, "last_ok_at": 1000.0})
    )
    out = io.StringIO()
    assert status(cfg_path, out, now=1010.0) == 0
    text = out.getvalue()
    assert "online" in text and "srv-7" in text and "via:      private" in text
    assert "hqr1_token_one" not in text
    out = io.StringIO()
    assert status(cfg_path, out, now=5000.0) == 1
    assert "offline" in out.getvalue()
    out = io.StringIO()
    assert unpair(cfg_path, out) == 0
    assert not cfg_path.exists() and not state.exists()
    assert "hqr1_token_one" not in out.getvalue()
