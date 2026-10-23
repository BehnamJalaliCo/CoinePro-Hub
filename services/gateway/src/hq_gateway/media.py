"""The media studio's tools (prompt 13 §2, contract §22.2, agents/tools.md):

    media.item      A1  write the current step of a media item (its role's)
    media.render    A2  queue the item's render in the sandboxed render worker
    media.voice     A2  the item's narration with the hub's own voice
    media.review    A2  the media director's review (the `qc` check)
    series.propose  A1  a publishing series for the owner's seal
"""

from __future__ import annotations

from hq_gateway import tools as T

TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {}
T.TOOLS.update(TOOLS)
