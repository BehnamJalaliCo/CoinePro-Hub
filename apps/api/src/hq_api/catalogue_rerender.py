"""`python -m hq_api.catalogue_rerender [--all]` (make catalogue-rerender):
prompt 19.2, every finished company catalogue rebuilt in the one section
shape from its jobs' stored answers; each company's latest catalogue gets a
new deliverable and archive record rendered from the structure (`--all`:
every catalogue). Idempotent: running it again renders again, nothing is
lost (old deliverables and records stay). Prints one JSON line per
catalogue: counts and refs only, never a section's contents.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from hq_api.config import Settings
from hq_api.domain import catalogue as CAT
from hq_common import logs


async def _main(deliver_all: bool) -> list[dict[str, Any]]:  # pragma: no cover - CLI
    from hq_api.__main__ import build

    hub, _ = await build(Settings())
    try:
        return await CAT.rerender_all(hub, deliver_all=deliver_all)
    finally:
        if hub.bus is not None:
            await hub.bus.close()
        await hub.db.close()


def main() -> None:  # pragma: no cover - CLI
    s = Settings()
    logs.setup("catalogue-rerender", s.log_level)
    out = asyncio.run(_main("--all" in sys.argv[1:]))
    for line in out:
        print(json.dumps(line, ensure_ascii=False))
    print(json.dumps({"catalogues": len(out), "errors": sum(1 for x in out if "error" in x)}))
    if any("error" in x for x in out):
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
