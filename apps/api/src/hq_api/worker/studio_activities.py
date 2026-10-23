"""Temporal activities of the media studio (prompt 13 §2, contract §22.2).

media_sweep      every 5 minutes (hq-media-sweep): the sealed series'
                 schedules make their items, due items are published through
                 the official APIs, published items are re-checked by rule
                 (the overseer's daily sample, §2.6). It asks the launch gate
                 first and does nothing at all while the holding is locked:
                 no item, no work, no outside call, no model.
media_publish    one item now (after its card's approval; also gated).
media_unpublish  the owner's sealed request to take an item down (the owner's
                 own act, started by the api: it only removes).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import activity

from hq_api.domain import gate, oversight
from hq_api.domain import studio as S
from hq_api.domain import studio_checks as K
from hq_api.domain import studio_publish as P
from hq_api.hub import Hub

log = logging.getLogger("hq_api.worker.studio")
SAMPLE_PER_COMPANY_DAY = 5
RECHECK_AFTER = timedelta(hours=1)


class StudioActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx

    def all(self) -> list[Any]:
        return [self.media_sweep, self.media_publish, self.media_unpublish]

    @activity.defn(name="media_sweep")
    async def media_sweep(self) -> dict[str, Any]:
        async with self._tx() as tx:
            if (lock := await gate.holding_lock(tx)) is not None:
                return gate.skipped(lock)
            made = await S.tick_series(tx, self.hub)
        published = await P.publish_due(self.hub)
        unpublished = await P.unpublish_due(self.hub)
        sampled = await self.recheck()
        return {**made, **published, **unpublished, "rechecked": sampled}

    @activity.defn(name="media_publish")
    async def media_publish(self, ref: str) -> dict[str, Any]:
        return await P.publish_due(self.hub, only=ref)

    @activity.defn(name="media_unpublish")
    async def media_unpublish(self, ref: str) -> dict[str, Any]:
        del ref  # every pending request is carried out
        return await P.unpublish_due(self.hub)

    async def recheck(self) -> dict[str, Any]:
        """The overseer's daily sample by rule (§2.6): items published an hour
        ago or more are checked again (red lines, risk warning, facts, brand);
        a failure opens a finding and pauses the series until the owner."""
        out: dict[str, Any] = {"checked": [], "failed": []}
        async with self._tx() as tx:
            if (lock := await gate.holding_lock(tx)) is not None:
                return gate.skipped(lock)
            rows = await tx.all(
                S.ITEM_SQL
                + """ WHERE i.state = 'published' AND NOT (i.render_meta ? 'rechecked')
                        AND i.updated_at < :before ORDER BY i.updated_at LIMIT 20 FOR UPDATE OF i SKIP LOCKED""",
                before=datetime.now(UTC) - RECHECK_AFTER,
            )
            per: dict[Any, int] = {}
            for item in rows:
                n = await tx.scalar(
                    """SELECT count(*) FROM media.items WHERE company_id = :co
                         AND (render_meta->'rechecked'->>'at')::timestamptz > now() - interval '24 hours'""",
                    co=item["company_id"],
                )
                if int(n or 0) + per.get(item["company_id"], 0) >= SAMPLE_PER_COMPANY_DAY:
                    continue
                per[item["company_id"]] = per.get(item["company_id"], 0) + 1
                t = await K.texts(tx, item)
                fmt = S.fmt_of(item)
                results = [
                    await K.red_lines(tx, self.hub, item, t),
                    K.risk_warning(item, fmt, t),
                    K.facts(item, t),
                    await K.brand(tx, item, fmt),
                ]
                bad = [r for r in results if r["result"] == "fail"]
                meta = {
                    **(item.get("render_meta") or {}),
                    "rechecked": {"at": datetime.now(UTC), "ok": not bad, "results": results},
                }
                await tx.exec(
                    "UPDATE media.items SET render_meta = CAST(:m AS jsonb) WHERE id = :id",
                    id=item["id"],
                    m=S.canonical(meta),
                )
                out["checked"].append(item["ref"])
                if not bad:
                    continue
                out["failed"].append(item["ref"])
                f, _ = await oversight.raise_finding(
                    tx,
                    company_id=item["company_id"],
                    company_code=item["company"],
                    severity="high",
                    title_fa=f"پست منتشرشده‌ی {item['ref']} چک {bad[0]['key']} را رد نمیکند"[:200],
                    body_md="\n".join(f"- {r['key']}: {r['note_fa']}" for r in bad),
                    evidence=[
                        {"kind": "media_item", "ref": item["ref"], "note": "the item's own record"}
                    ],
                    dedupe_key=f"media:{item['ref']}",
                )
                if item.get("series_id"):
                    await tx.exec(
                        """UPDATE media.series SET status = 'paused', status_note_fa = :n
                           WHERE id = :id AND status = 'sealed'""",
                        id=item["series_id"],
                        n=f"ناظر کل بعد از یافته‌ی {f['ref']} ({item['ref']}) متوقفش کرد؛ تا تصمیم تو متوقف میماند."[
                            :500
                        ],
                    )
        return out
