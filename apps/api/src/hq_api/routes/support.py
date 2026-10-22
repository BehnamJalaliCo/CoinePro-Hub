"""The support desk (prompt 10 §4-§6, contract §19.3-§19.4, §19.6). Empty
until those sections land; the foundation is hq_api.domain.support.

Owner (/api/v1):  /support/channels (+ /pause, PATCH If-Match, widening 🔏 support.channel),
                  /support/conversations (+ /reply, /teach: Idempotency-Key required; /close),
                  /support/queue, /support/kb (+ /approve 🔏 support.kb, /retire),
                  /support/history, /support/shadow (+ /{company}/run)
Agents (/internal/v1, internal_router): kb.search, kb.propose, support.draft,
                  support.handoff, support.mystery; OPA ops "support.read" (conversations,
                  proposed articles), "support.stats" (counts, masked quotes), "kb.read".
Tables: support.* (migration 0025). A customer's text is stored only through
domain.support.store_inbound (masked first); a model reads it only through
domain.support.model_view.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["support"])
internal_router = APIRouter(tags=["internal"])
