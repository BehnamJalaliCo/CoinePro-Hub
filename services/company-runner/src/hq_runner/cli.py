"""Command line: pair, run, status, unpair (and the internal classify-hook).

Output is English; the one instruction the owner acts on is also in Persian.
The runner token is never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import platform
import socket
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TextIO

from hq_runner import __version__
from hq_runner import config as config_mod
from hq_runner.config import DEFAULT_HUB, Config
from hq_runner.hub import Hub, HubError, Transient, classify_status, problem_code
from hq_runner.inventory import parse_os_release
from hq_runner.net import Route, hub_parts, source_address_towards

EXIT_USAGE = 2


def _os_name() -> str:
    try:
        text = Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        text = ""
    return parse_os_release(text) or f"{platform.system()} {platform.release()}"


def _private_ip(hub_ip: str | None) -> str | None:
    return source_address_towards(hub_ip or "10.10.1.4")


def _banner(code: str, minutes: int, out: TextIO) -> None:
    line = "=" * 44
    print(line, file=out)
    print(f"   HQ pairing code:   {code}", file=out)
    print(line, file=out)
    print(
        "این کد را در اپ ستاد تأیید کنید (شرکت ← سرورها ← وصل کردن سرور) / "
        "Approve this code in the HQ app (Company → Servers → Attach server).",
        file=out,
    )
    print(f"The code expires in {minutes} minutes. Waiting for approval...", file=out)
    out.flush()


async def pair(
    *,
    hub: str,
    hub_ip: str | None,
    company: str,
    name: str,
    cfg_path: Path | None = None,
    route: Route | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
    out: TextIO = sys.stdout,
    min_interval: float = 1.0,
) -> int:
    """Device-authorisation pairing (contract §26.1). Returns an exit code."""
    rt = route or Route(hub, hub_ip)
    try:
        await rt.select()
        api = Hub(rt, lambda: None)
        body = {
            "company": company,
            "name": name,
            "hostname": socket.gethostname(),
            "private_ip": _private_ip(hub_ip),
            "os": _os_name(),
            "runner_version": __version__,
        }
        try:
            answer = await api.pair(body)
        except HubError as exc:
            print(
                f"error: the hub refused pairing ({exc.status} {exc.code or ''}) "
                f"{exc.detail or ''}".rstrip(),
                file=out,
            )
            return 1
        device_code = str(answer["device_code"])
        expires_in = float(answer.get("expires_in", 900))
        interval = max(min_interval, float(answer.get("interval", 5)))
        print(f"Connected to {rt.host} via the {rt.via} network.", file=out)
        _banner(str(answer["user_code"]), max(1, int(expires_in // 60)), out)
        deadline = clock() + expires_in
        while clock() < deadline:
            await sleep(interval)
            try:
                resp = await api.token_poll(device_code)
            except Transient:
                continue
            if resp.status_code == 428:
                continue
            code, detail = problem_code(resp)
            if resp.status_code == 429 or code == "slow_down":
                interval += 5
                continue
            if resp.status_code == 200:
                data = resp.json()
                cfg = Config(
                    hub=rt.hub,
                    hub_ip=hub_ip,
                    server_id=str(data["server_id"]),
                    runner_token=str(data["runner_token"]),
                    company=company,
                    name=name,
                )
                config_mod.save(cfg, cfg_path)
                print(
                    f"Paired: server {cfg.server_id} of {company}. Credentials saved to "
                    f"{cfg_path or config_mod.config_path()} (mode 600).",
                    file=out,
                )
                print(
                    "Next: enable the service (see README) and check `hq-runner status`.", file=out
                )
                return 0
            if code in ("access_denied", "denied"):
                print("error: the owner declined this pairing.", file=out)
                return 1
            if code in ("expired_token", "expired", "code_expired") or resp.status_code in (
                400,
                404,
                410,
            ):
                print(
                    "error: the pairing code expired or is no longer valid; "
                    "run `hq-runner pair` again.",
                    file=out,
                )
                return 1
            err = classify_status(resp)
            print(
                f"error: unexpected answer from the hub ({resp.status_code} {code or ''} "
                f"{detail or ''})".rstrip(),
                file=out,
            )
            if err is not None and not isinstance(err, Transient):
                return 1
        print(
            "error: the pairing code expired before it was approved; run `hq-runner pair` again.",
            file=out,
        )
        return 1
    finally:
        await rt.aclose()


def status(cfg_path: Path | None, out: TextIO = sys.stdout, now: float | None = None) -> int:
    cfg = config_mod.load(cfg_path)
    print(f"hq-runner {__version__}", file=out)
    if cfg is None:
        print("state:    not paired (run `hq-runner pair --company CODE --name NAME`)", file=out)
        return 1
    st = config_mod.load_state(cfg_path)
    now = now or time.time()
    last_ok = st.get("last_ok_at")
    if cfg.state == "revoked":
        state = "revoked (detached in HQ; pair again to use this server)"
    elif st.get("state") == "online" and isinstance(last_ok, int | float) and now - last_ok <= 90:
        state = "online"
    else:
        state = "offline"
    print(f"state:    {state}", file=out)
    print(f"server:   {cfg.server_id} ({cfg.company or '?'} · {cfg.name or '?'})", file=out)
    print(
        f"hub:      {cfg.hub}" + (f" (private address {cfg.hub_ip})" if cfg.hub_ip else ""),
        file=out,
    )
    if st.get("via"):
        rtt = st.get("hub_rtt_ms")
        print(
            f"via:      {st['via']}" + (f", round trip {rtt} ms" if rtt is not None else ""),
            file=out,
        )
    if isinstance(last_ok, int | float):
        print(f"last ok:  {int(now - last_ok)} s ago", file=out)
    rotated = int((now - cfg.rotated_at) // 3600)
    print(f"token:    stored (mode 600), rotated {rotated} h ago", file=out)
    return 0 if state == "online" else 1


def unpair(cfg_path: Path | None, out: TextIO = sys.stdout) -> int:
    cfg = config_mod.load(cfg_path)
    removed = config_mod.remove(cfg_path)
    if not removed:
        print("Nothing to remove: this server is not paired.", file=out)
        return 0
    sid = cfg.server_id if cfg else "?"
    print(
        f"Removed this runner's credentials (server {sid}). The runner can no longer work.",
        file=out,
    )
    print("Stop the service: sudo systemctl disable --now hq-runner@$USER", file=out)
    print(
        "In the HQ app, detach the server too (Company → Servers → Detach) so the hub revokes it.",
        file=out,
    )
    return 0


def run(cfg_path: Path | None) -> int:
    from hq_runner.runner import Runner

    cfg = config_mod.load(cfg_path)
    if cfg is None:
        print(
            "error: not paired; run `hq-runner pair --company CODE --name NAME` first",
            file=sys.stderr,
        )
        return EXIT_USAGE
    route = Route(cfg.hub, cfg.hub_ip, ca_file=cfg.ca_file)
    runner = Runner(cfg, route, cfg_path=cfg_path)
    return asyncio.run(runner.run())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hq-runner", description="CoinePro HQ job runner for a company server."
    )
    p.add_argument("--version", action="version", version=f"hq-runner {__version__}")
    p.add_argument("--config", help="path of config.json (default ~/.config/hq-runner/config.json)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser(
        "pair", help="pair this server with the hub (the owner approves a short code)"
    )
    pp.add_argument("--company", required=True, help="the company code, e.g. FX")
    pp.add_argument("--name", required=True, help="a name for this server")
    pp.add_argument("--hub", default=DEFAULT_HUB)
    pp.add_argument(
        "--hub-ip", help="the hub's private address, e.g. 10.10.1.4 (TLS keeps the hub's name)"
    )
    pp.add_argument("--force", action="store_true", help="pair again even if already paired")
    sub.add_parser("run", help="run the runner (the systemd service runs this)")
    sub.add_parser("status", help="show whether the runner is online (never prints the token)")
    sub.add_parser("unpair", help="remove this runner's stored credentials")
    hp = sub.add_parser("classify-hook", help=argparse.SUPPRESS)
    hp.add_argument("--job")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    cfg_path = Path(args.config).expanduser() if args.config else None
    if cfg_path is not None:
        os.environ["HQ_RUNNER_CONFIG"] = str(cfg_path.resolve())
    if args.cmd == "pair":
        try:
            hub_parts(args.hub)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE
        existing = config_mod.load(cfg_path)
        if existing is not None and existing.state != "revoked" and not args.force:
            print(
                f"error: already paired as server {existing.server_id}; "
                "run `hq-runner unpair` first or pass --force",
                file=sys.stderr,
            )
            return EXIT_USAGE
        return asyncio.run(
            pair(
                hub=args.hub.rstrip("/"),
                hub_ip=args.hub_ip,
                company=args.company,
                name=args.name,
                cfg_path=cfg_path,
            )
        )
    if args.cmd == "run":
        return run(cfg_path)
    if args.cmd == "status":
        return status(cfg_path)
    if args.cmd == "unpair":
        return unpair(cfg_path)
    if args.cmd == "classify-hook":
        from hq_runner import hook

        return hook.main(args.job)
    return EXIT_USAGE  # pragma: no cover
