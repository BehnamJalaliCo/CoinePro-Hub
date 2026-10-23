"""The archive's two cards (prompt 14 §2, §5; contract §23.11, §23.12).

archive_schema    an agent's proposed schema change: the payload is the exact
                  PUT body {part, key, base_version, body, impact}, checked
                  against the closed vocabulary when it is proposed; sealed by
                  the owner (decision.approve step-up on the card's ref), the
                  same body is applied, unless that schema row changed since
                  `base_version` (a new key: since it came to exist): then the
                  card is void (409 decision_not_pending) and nothing changes.
archive_disposal  the weekly disposal card (code only; retention.apply_disposal).
"""

from __future__ import annotations

from typing import Any

from hq_api import audit, events
from hq_api.archive import clearance as CL
from hq_api.archive import schema as SC
from hq_api.archive import vocab as V
from hq_api.archive.common import OWNER, holding, invalid
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal


def _base_ok(part: str, key: str, row: dict[str, Any] | None, base: int | None) -> bool:
    if part in V.REF_PARTS and key == "new":
        return base is None
    if row is None:
        return base is None
    return bool(base == row["version"])


async def check_proposal(tx: Tx, payload: dict[str, Any]) -> dict[str, Any]:
    part, key, base = payload["part"], payload["key"], payload.get("base_version")
    row = await SC.current(tx, part, key)
    if not _base_ok(part, key, row, base):
        raise invalid(
            {
                "payload.base_version": f"the current version is {row['version'] if row else 'none (a new key)'}"
            }
        )
    checked = await SC.check(tx, part, key, payload["body"], row)
    await CL.full(tx)
    impact = await SC.impact(tx, part, key, checked)
    await tx.exec("SELECT set_config('app.clearance', '', true)")
    return {**payload, "impact": impact}


async def after_change(tx: Tx, part: str, key: str, impact: dict[str, int]) -> None:
    """The stream's schema.changed; a class that left filed records without a
    newly required field gets the archivist one work item «تکمیل N سند»."""
    from hq_api.archive import retention as RT

    h = await holding(tx)
    await events.emit(tx, h["code"], "schema.changed", key, {"part": part})
    if part == "classes" and impact.get("missing_required"):
        await RT.archivist_work(
            tx,
            f"تکمیل {impact['missing_required']} سند بایگانی ({key})",
            f"The class `{key}` has a new required field; {impact['missing_required']} filed record(s) miss it. "
            "Read each one (archive.read) and give the owner the value and where it is in the document, in "
            "your deliverable; you never change a filed record yourself.",
        )


async def apply(tx: Tx, d: dict[str, Any], who: Principal) -> str:
    """At the seal, in the deciding transaction -> a line for the resolution."""
    await CL.full(tx)
    if d["kind"] == "archive_disposal":
        from hq_api.archive import retention as RT

        out = await RT.apply_disposal(tx, d)
        line = f"امحا شد: {len(out['disposed'])} سند"
        if out["skipped"]:
            line += "؛ کنار ماند: " + "، ".join(
                f"{x['ref']} ({x['why']})" for x in out["skipped"][:30]
            )
        return line[:3000]
    p = d["payload"] or {}
    part, key, base = p["part"], p["key"], p.get("base_version")
    row = await SC.current(tx, part, key, lock=True)
    if not _base_ok(part, key, row, base):
        raise ApiError(
            409,
            "decision_not_pending",
            f"{d['ref']}: the schema row changed since; this card is void",
        )
    checked = await SC.check(tx, part, key, p["body"], row)
    impact = await SC.impact(tx, part, key, checked)
    new = await SC.apply(tx, OWNER if who.is_owner else who, part, key, checked, row)
    new_key = SC.row_key(part, new)
    await after_change(tx, part, new_key, impact)
    await audit.record(
        tx,
        who,
        company_id=new["company_id"],
        action="archive.schema",
        action_class="A2",
        target_kind=f"archive_{part}",
        target_ref=new_key,
        summary=f"{d['ref']} v{new['version']}",
        step_up=True,
    )
    return f"طرح بایگانی: {part}/{new_key} نسخه‌ی {new['version']} (اثر: {impact['records']} سند)"
