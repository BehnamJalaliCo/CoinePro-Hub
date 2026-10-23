"""`python -m hq_egress.relay`: the sign-in window's TCP relay (prompt 12
§9.1.5): RELAY_LISTEN (the container's 6080, published on the host's
127.0.0.1 only) to RELAY_TARGET (the window's noVNC), byte for byte, for at
most RELAY_SECONDS, then it exits. Nothing is read, logged or kept.
Standard library only."""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys


async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    try:
        while chunk := await src.read(65536):
            dst.write(chunk)
            await dst.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        with contextlib.suppress(Exception):
            dst.close()


def _split(addr: str) -> tuple[str, int]:
    host, _, port = addr.rpartition(":")
    if not host or not port.isdigit():
        raise ValueError(f"not host:port: {addr}")
    return host, int(port)


async def serve(listen: str, target: str, seconds: float) -> None:
    t_host, t_port = _split(target)

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            up_r, up_w = await asyncio.wait_for(asyncio.open_connection(t_host, t_port), 10)
        except (OSError, TimeoutError):
            writer.close()
            return
        await asyncio.gather(_pipe(reader, up_w), _pipe(up_r, writer))

    host, port = _split(listen)
    server = await asyncio.start_server(handle, host, port)
    async with server:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(server.serve_forever(), timeout=seconds)


def main() -> int:
    listen = os.environ.get("RELAY_LISTEN", "0.0.0.0:6080")
    target = os.environ.get("RELAY_TARGET", "coinepro-hq-web-login:6080")
    seconds = float(os.environ.get("RELAY_SECONDS", "960"))
    asyncio.run(serve(listen, target, seconds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
