"""The gateway's own MCP client against one container server (prompt 12 §14,
`make mcp-test`): run inside the gateway image (its hq_gateway.mcp.SdkOpener,
the same code path as mcp.call), on a throwaway internal network with the
server. Prints one JSON object: the listing (names, digest) and, when asked,
one tool call's result as the gateway renders it for a model.

    python -m ... selftest_client.py URL [TOOL JSON_ARGS]
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from hq_gateway.mcp import SdkOpener, ServerSpec, list_all, listing_of, render


async def main(url: str, tool: str | None, args: dict[str, Any]) -> dict[str, Any]:
    spec = ServerSpec(key="selftest", transport="container", url=url, listing_sha256=None)
    opener = SdkOpener(proxy_url=None, timeout_s=60)
    out: dict[str, Any] = {}
    async with opener(spec) as session:
        listing = listing_of(await list_all(session))
        out["tools"] = listing.names
        out["listing_sha256"] = listing.sha256
        if tool:
            result = await session.call_tool(tool, args)
            out["call"] = render("selftest", tool, result)
    return out


if __name__ == "__main__":
    target = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else None
    arguments = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
    print(json.dumps(asyncio.run(main(target, name, arguments)), ensure_ascii=False))
