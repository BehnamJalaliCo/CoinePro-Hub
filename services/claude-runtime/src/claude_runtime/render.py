"""Turn a message list into the single prompt the CLI receives on stdin.

The CLI's stream-json input accepts user turns only, so earlier turns of a
conversation are passed as a tagged transcript.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class _Message(Protocol):
    @property
    def role(self) -> str: ...

    @property
    def content(self) -> str: ...


def render(messages: Sequence[_Message]) -> str:
    if len(messages) == 1:
        return messages[0].content
    parts = ["<conversation>"]
    for m in messages:
        parts.append(f"<{m.role}>\n{m.content}\n</{m.role}>")
    parts.append("</conversation>")
    parts.append("Reply to the last user message as the assistant.")
    return "\n".join(parts)
