"""python -m hq_media_render <command>:

courier claim          claim one job into the job volume; prints its id (nothing: no job)
courier send <id>      send a rendered job's outputs (or its failure) back; clear it
render <id>            draw one job (no network); writes out/manifest.json
bench reel|lottie|design [dir]   the acceptance numbers, offline
probe                  proves this container has no network (exit 1 if it has)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

import httpx


async def _courier(argv: list[str]) -> int:
    from hq_media_render import courier as C

    s = C.Settings()
    token = await C.api_token(s)
    async with httpx.AsyncClient(
        base_url=s.api_url, headers={"Authorization": f"Bearer {token}"}, timeout=120
    ) as client:
        del token
        if argv[:1] == ["claim"]:
            job = await C.claim(client, s.jobs)
            if job:
                print(job)
            return 0
        if argv[:1] == ["send"] and len(argv) == 2:
            print(json.dumps(await C.send(client, s.jobs, argv[1])))
            return 0
    print(__doc__, file=sys.stderr)
    return 2


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    for noisy in ("httpx", "httpcore"):  # request lines: refs only, still kept quiet
        logging.getLogger(noisy).setLevel(logging.WARNING)
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    if cmd == "courier":
        return asyncio.run(_courier(rest))
    if cmd == "render" and len(rest) == 1:
        from hq_media_render import render

        return asyncio.run(render.main(rest[0]))
    if cmd == "bench":
        from hq_media_render import bench

        return bench.main(rest)
    if cmd == "probe":
        from hq_media_render import probe

        return probe.main()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
