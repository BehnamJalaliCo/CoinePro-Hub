"""The fake model (prompt 05 §2): a backend for connections of kind 'fake'.

Test environments only: the router registers it when LLM_FAKE_BACKEND=1 (or a
test passes it in), and production never seeds a 'fake' connection, so CI
makes no real model call. Answers are pre-written:

  - per actor: `enqueue(actor_ref, answer, ...)`; each call of that actor takes
    the next one (an answer is a dict -> structured JSON, a str -> text, or a
    BackendResult as it is);
  - a callable `script(call) -> answer | None` decides when the queue is empty;
  - otherwise a harmless default: {"summary_fa": ..., "actions": [], "done": true}
    when a JSON schema is asked for, else the text "OK".
Usage is deterministic (about one token per 4 characters), so budgets and
limits can be tested exactly.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Callable
from typing import Any

from hq_common import vision
from llm_router.backends.base import OK, BackendCall, BackendResult, Delta, ImagePart
from llm_router.pricing import Usage

Answer = dict[str, Any] | str | BackendResult
DEFAULT_STEP = {"summary_fa": "پاسخ آزمایشی", "actions": [], "done": True}


def image_tokens(call: BackendCall) -> int:
    """A rough count for the images a call carries (hq_common.vision)."""
    n = sum(1 for m in call.messages for p in m.parts if isinstance(p, ImagePart))
    return n * vision.TOKENS_PER_IMAGE


def tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


class FakeBackend:
    def __init__(self, script: Callable[[BackendCall], Answer | None] | None = None) -> None:
        self.script = script
        self.queues: dict[str, deque[Answer]] = defaultdict(deque)
        self.calls: list[BackendCall] = []

    def enqueue(self, actor_ref: str, *answers: Answer) -> None:
        self.queues[actor_ref].extend(answers)

    def _answer(self, call: BackendCall) -> Answer:
        q = self.queues.get(call.actor_ref or "")
        if q:
            return q.popleft()
        if self.script is not None:
            got = self.script(call)
            if got is not None:
                return got
        return dict(DEFAULT_STEP) if call.json_schema else "OK"

    def _result(self, call: BackendCall) -> BackendResult:
        self.calls.append(call)
        answer = self._answer(call)
        if isinstance(answer, BackendResult):
            return answer
        prompt = (call.system or "") + "".join(m.content for m in call.messages)
        if isinstance(answer, dict):
            text = json.dumps(answer, ensure_ascii=False)
            structured: Any = answer
        else:
            text, structured = answer, None
        stop = "end_turn"
        if call.max_output_tokens and tokens(text) > call.max_output_tokens:
            # As a real model does: the output stops at the cap, unfinished.
            text, structured, stop = text[: call.max_output_tokens * 4], None, "max_tokens"
        return BackendResult(
            OK,
            text=text,
            structured=structured,
            model=call.model,
            usage=Usage(
                input_tokens=tokens(prompt) + image_tokens(call), output_tokens=tokens(text)
            ),
            stop_reason=stop,
            effort_applied=call.effort is not None,
        )

    async def run(self, call: BackendCall) -> BackendResult:
        return self._result(call)

    async def stream(self, call: BackendCall) -> AsyncIterator[Delta | BackendResult]:
        result = self._result(call)
        text = result.text or ""
        for i in range(0, len(text), 16):
            yield Delta(text[i : i + 16])
        yield result
