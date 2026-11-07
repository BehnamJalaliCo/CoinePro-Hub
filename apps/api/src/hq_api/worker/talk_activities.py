"""⟨1.14⟩ Prompt 23, the worker's side of the owner's talk (contract §32.2,
§32.8): the worker alone reaches llm-router and the Tool Gateway.

    talk_turn      one persona turn (hq_api.talk.engine): the router steps,
                   the read tools, the sentences to the voice layer, the stream
    talk_plain     a turn the worker could not finish: the plain line (§32.2)
    talk_summary   the conversation's running summary every N turns (§32.8)
    session_memory ⟨1.22⟩ a session's memory folded from its last turns (§40.1)

Prompts, answers and tool payloads stay in memory: the activities return
metadata only (Temporal's history keeps nothing the owner said).
"""

from __future__ import annotations

from typing import Any

from temporalio import activity

from hq_api.domain import session_memory
from hq_api.hub import Hub
from hq_api.talk import engine, summary


class TalkActivities:
    def __init__(self, hub: Hub, router: Any, gateway: Any) -> None:
        self.hub = hub
        self.router = router
        self.gateway = gateway

    def all(self) -> list[Any]:
        return [self.talk_turn, self.talk_plain, self.talk_summary, self.session_memory]

    @activity.defn(name="session_memory")
    async def session_memory(self, order_ref: str) -> dict[str, Any]:
        return await session_memory.fold(
            self.hub, session_memory.router_call(self.router), order_ref
        )

    @activity.defn(name="talk_turn")
    async def talk_turn(self, turn_id: str) -> dict[str, Any]:
        return await engine.run_turn(self.hub, self.router, self.gateway, turn_id)

    @activity.defn(name="talk_plain")
    async def talk_plain(self, turn_id: str) -> dict[str, Any]:
        return await engine.unavailable(self.hub, turn_id)

    @activity.defn(name="talk_summary")
    async def talk_summary(self, ref: str) -> dict[str, Any]:
        return await summary.summarise(self.hub, self.router, ref)
