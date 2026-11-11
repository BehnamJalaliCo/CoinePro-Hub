"""A conversation's running summary (contract §32.8): every N turns (data:
seed/talk/personas.yaml `summary.every_turns`), one call of the task class
`talk_summary` with a light model folds the turns since the last summary into
it. The summary feeds the next turns' context (talk.context), so a long
conversation stays cheap. Run by the worker after a turn (activity
`talk_summary`); a failure leaves the old summary (the next turn tries again).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from hq_api.talk import data, store
from hq_api.talk.scrub import clean

log = logging.getLogger("hq_api.talk.summary")

TASK_CLASS = "talk_summary"
SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary_fa"],
    "properties": {"summary_fa": {"type": "string", "maxLength": 3000}},
}
SYSTEM = (
    "You keep the running summary of a conversation between a holding's owner and the holding's personas. "
    "Write plain Persian, at most 12 short lines: what was discussed, what the owner decided or asked, what is "
    "still open. Keep refs (W-, F-, D-, CV-) and figures as written, in Latin digits. No new facts, no advice. "
    'Answer {"summary_fa": "..."} only.'
)


async def summarise(hub: Any, router: Any, ref: str) -> dict[str, Any]:
    spec = data.summary_spec()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        conv = await store.conversation(tx, ref)
        upto = int(conv["summary_upto"])
        if int(conv["turns"]) - upto < spec["every_turns"] or router is None:
            return {"summarised": False}
        # audit 2026-11-11: fold only up to the first turn still being written (a player's answer
        # may take minutes while the next turn is done): summary_upto never passes a turn that
        # is not in the summary yet. A turn streaming for over an hour is skipped, as it was.
        rows = await tx.all(
            """SELECT n, by_kind, persona, text, show_md FROM talk.turns
               WHERE conversation_id = :c AND n > :u AND state <> 'streaming'
                 AND n < COALESCE((SELECT min(n) FROM talk.turns
                                   WHERE conversation_id = :c AND n > :u AND state = 'streaming'
                                     AND at > now() - interval '1 hour'), 2147483647)
               ORDER BY n""",
            c=conv["id"],
            u=upto,
        )
        holding = await hub.companies.holding()
    if not rows:
        return {"summarised": False}
    lines = [
        ("مالک: " + r["text"])
        if r["by_kind"] == "owner"
        else f"{r['persona']}: {r['show_md'] or ''}"
        for r in rows
    ]
    prompt = json.dumps(
        {
            "summary_so_far": conv["summary_fa"] or "",
            "new_turns": [clean(x)[0][:2000] for x in lines],
        },
        ensure_ascii=False,
    )
    body: dict[str, Any] = {
        "company_code": holding.code,
        "actor_ref": "talk:summary",
        "task_class": TASK_CLASS,
        "priority": 3,
        "effort": spec["effort"],
        "system": SYSTEM,
        "prompt": prompt,
        "json_schema": SCHEMA,
        "max_output_tokens": spec["max_output_tokens"],
        "timeout_s": 60,
        "meta": {"purpose": "talk_summary", "trigger": "talk"},
    }
    if spec["model"]:
        body["model"] = spec["model"]
    call = await router.run(body, 60)
    out = call.structured if isinstance(call.structured, dict) else None
    if out is None and call.text:
        try:
            out = json.loads(call.text)
        except ValueError:
            out = None
    text = clean(str((out or {}).get("summary_fa") or "").strip())[0][:4000] if call.ok else ""
    if not text:
        log.info("talk summary not made", extra={"ref": ref, "status": call.status})
        return {"summarised": False}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await tx.exec(
            """UPDATE talk.conversations SET summary_fa = :s, summary_upto = :u,
                   tokens = tokens + :t, updated_at = now() WHERE id = :id""",
            s=text,
            u=int(rows[-1]["n"]),
            t=call.tokens,
            id=conv["id"],
        )
    return {"summarised": True}
