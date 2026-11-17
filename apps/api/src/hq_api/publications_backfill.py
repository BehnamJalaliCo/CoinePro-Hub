"""⟨1.39⟩ §60.1 `make publications-backfill`: one `media.publications` row per chain of every
`publish` job there is (done, failed, cancelled and pending), from the tables a fresh start keeps
(the jobs, the files, the topics, a flow's run where it still is). Idempotent: run it again and a
chain with its row only gains what it lacks. Then a reel without a cover gets its frame. Prints the
counts, per account, as JSON lines."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from hq_api.config import Settings
from hq_api.domain import publications as PB
from hq_api.principal import Principal
from hq_common import logs

SERVICE = Principal(kind="service", code="publications", role="service")


async def run(hub: Any) -> dict[str, Any]:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await PB.backfill(tx)
        holding = await tx.scalar("SELECT id FROM core.companies WHERE kind = 'holding' LIMIT 1")
        if holding is not None:
            from hq_api import audit

            await audit.record(
                tx, SERVICE, company_id=holding, action="publications.backfill",
                action_class="A1", target_kind="table", target_ref="media.publications",
                summary=f"chains {out['chains']}, made {out['made']}, updated {out['updated']}, "
                f"skipped {out['skipped']}"[:500],
            )  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        refs = [
            str(r["ref"])
            for r in await tx.all(
                """SELECT ref FROM media.publications WHERE thumb_file_id IS NULL
                     AND files @> '[{"role": "video"}]'::jsonb ORDER BY created_at"""
            )
        ]
    frames = 0
    for ref in refs:
        if await PB.make_thumb(hub, ref):
            frames += 1
    out["frames"] = frames
    return out


async def _main() -> dict[str, Any]:  # pragma: no cover - CLI
    from hq_api.__main__ import build

    hub, _ = await build(Settings())
    try:
        return await run(hub)
    finally:
        if hub.bus is not None:
            await hub.bus.close()
        await hub.db.close()


def main() -> None:  # pragma: no cover - CLI
    s = Settings()
    logs.setup("publications-backfill", s.log_level)
    out = asyncio.run(_main())
    for account, n in out["rows_per_account"].items():
        print(json.dumps({"account": account, "rows": n,
                          "chains_now": out["chains_per_account"].get(account, 0)}))  # fmt: skip
    print(json.dumps({k: v for k, v in out.items() if not isinstance(v, dict)}))


if __name__ == "__main__":  # pragma: no cover
    main()
