"""⟨1.37⟩ What the flow's step adapters share (contract §59.2): the run's own row (its day and its
publish time), the flow automation its line belongs to (§59.7: the account, the story, the reply
policy), the ledger it writes in (§47) and the labelled parts of a script.

Every read goes through `ctx.hub.db`; tests replace `FLOW_OVERRIDE`/`RUN_OVERRIDE` or answer these
queries with their fake transaction.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from hq_api.db import Tx
from hq_api.lines.base import StepContext

TEHRAN = "Asia/Tehran"
FLOW_SQL = """SELECT a.ref, a.company_id, a.sentence_fa, a.playbook, a.playbook_version, a.line,
       a.schedule, a.budget, a.replies, a.mode, a.account, a.story, a.state,
       p.group_id, p.title_fa AS playbook_fa
FROM growth.automations a LEFT JOIN owner.playbooks p ON p.ref = a.playbook
WHERE a.kind = 'flow' AND a.line = :line ORDER BY a.created_at DESC LIMIT 1"""
RUN_SQL = "SELECT id, ref, occurrence_at, at, dry FROM lines.runs WHERE ref = :r"


def _j(raw: Any) -> Any:
    return json.loads(raw) if isinstance(raw, str) else raw


async def flow_of(tx: Tx, ctx: StepContext) -> dict[str, Any] | None:
    """The flow automation the run's line belongs to (None: a line of its own)."""
    row = await tx.first(FLOW_SQL, line=ctx.line_ref)
    if row is None:
        return None
    got = dict(row)
    for k in ("schedule", "budget", "replies"):
        got[k] = _j(got.get(k))
    return got


async def run_of(tx: Tx, ctx: StepContext) -> dict[str, Any] | None:
    row = await tx.first(RUN_SQL, r=ctx.run_ref)
    return dict(row) if row is not None else None


async def zone_of(tx: Tx) -> str:
    try:
        from hq_api.domain.gov_common import owner_tz

        return str(await owner_tz(tx) or TEHRAN)
    except Exception:  # noqa: BLE001 - the owner's zone, else Tehran's
        return TEHRAN


def when_of(run: dict[str, Any] | None) -> datetime | None:
    """The run's publish time (the occurrence it was made for), else None."""
    at = (run or {}).get("occurrence_at")
    if isinstance(at, str):
        at = datetime.fromisoformat(at.replace("Z", "+00:00"))
    return at if isinstance(at, datetime) else None


def day_of(run: dict[str, Any] | None, tz: str) -> date:
    """The run's day in the owner's zone (its publish time's, else when it was made, else today)."""
    at = when_of(run) or (run or {}).get("at") or datetime.now(UTC)
    if isinstance(at, str):
        at = datetime.fromisoformat(at.replace("Z", "+00:00"))
    try:
        zone = ZoneInfo(tz)
    except Exception:  # noqa: BLE001 - an unknown zone: Tehran's
        zone = ZoneInfo(TEHRAN)
    return at.astimezone(zone).date() if at.tzinfo else at.date()


def scope_of(
    ctx_company_id: Any, flow: dict[str, Any] | None, run: dict[str, Any] | None
) -> dict[str, Any]:
    """The ledger (§47) a flow run writes in: its working group's (the playbook's group), else the
    company's own loose list; the run is the line run (its topic is freed when the run is skipped)."""
    return {
        "company_id": (flow or {}).get("company_id") or ctx_company_id,
        "group_id": (flow or {}).get("group_id"),
        "group_key": None,
        "run_id": (run or {}).get("id"),
        "order_ref": None,
    }


# ------------------------------------------------------- the parts of a script --
# The script step (gpt_text with `settings.parts`) answers in labelled parts, one label a line, a
# part going on until the next label: `voice:` (what the narrator says), `caption:`, `keyword:`
# (the word the video says aloud), `match:` (`any`: every comment), `reply:` (the DM) and one
# `public:` line for each public reply. Persian labels are read too.
LABELS = {
    "voice": ("voice", "script", "narration", "متن", "متن گوینده", "سناریو", "گوینده"),
    "caption": ("caption", "کپشن"),
    "keyword": ("keyword", "word", "کلمه", "کلمه‌ی کامنت", "کلمه کامنت"),
    "match": ("match", "تطبیق"),
    "reply": ("reply", "dm", "دایرکت", "پیام", "جواب دایرکت"),
    "public": ("public", "عمومی", "جواب عمومی"),
    "topic": ("topic", "موضوع"),
}
_LABEL = re.compile(r"^\s*[-*#]*\s*([^:：]{1,24})\s*[:：]\s*(.*)$")
PART_KEYS = tuple(LABELS)


def _label(name: str) -> str | None:
    n = " ".join(name.strip().strip("*#").split()).lower()
    return next((k for k, names in LABELS.items() if n in names), None)


def script_parts(text: str | None) -> dict[str, Any]:
    """{voice, caption, keyword, match, reply, public: [..], topic} of a labelled answer (a JSON
    object with those keys is read as well); {} when it has no labels."""
    raw = (text or "").strip()
    if not raw:
        return {}
    if raw.startswith(("{", "```")):
        try:
            start, end = raw.find("{"), raw.rfind("}")
            obj = json.loads(raw[start : end + 1])
        except ValueError:
            obj = None
        if isinstance(obj, dict):
            got: dict[str, Any] = {k: str(obj[k]).strip() for k in PART_KEYS if k != "public"
                                   and isinstance(obj.get(k), str | int | float)}  # fmt: skip
            pub = obj.get("public") or obj.get("public_replies") or []
            got["public"] = (
                [str(x).strip() for x in pub if str(x).strip()] if isinstance(pub, list) else []
            )
            return got
    parts: dict[str, list[str]] = {}
    public: list[str] = []
    cur: str | None = None
    for line in raw.splitlines():
        m = _LABEL.match(line)
        key = _label(m.group(1)) if m else None
        if key is not None and m is not None:
            cur = key
            value = m.group(2).strip()
            if key == "public":
                if value:
                    public.append(value)
            elif value:
                parts.setdefault(key, []).append(value)
            else:
                parts.setdefault(key, [])
            continue
        if cur is None or not line.strip():
            if cur in ("voice", "caption", "reply") and not line.strip():
                parts.setdefault(cur, []).append("")
            continue
        if cur == "public":
            public.append(line.strip().lstrip("-*0123456789.) ").strip())
        else:
            parts.setdefault(cur, []).append(line.rstrip())
    if not parts and not public:
        return {}
    out: dict[str, Any] = {k: "\n".join(v).strip() for k, v in parts.items()}
    out["public"] = [x for x in public if x]
    return out
