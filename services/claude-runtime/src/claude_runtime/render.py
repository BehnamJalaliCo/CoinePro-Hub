"""Turn a message list into the single prompt the CLI receives on stdin.

The CLI's stream-json input accepts user turns only, so earlier turns of a
conversation are passed as a tagged transcript.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol


class _Message(Protocol):
    @property
    def role(self) -> str: ...

    @property
    def content(self) -> str: ...

    @property
    def parts(self) -> tuple[Any, ...]: ...


def render(messages: Sequence[_Message]) -> str:
    if len(messages) == 1:
        return messages[0].content
    parts = ["<conversation>"]
    for m in messages:
        parts.append(f"<{m.role}>\n{m.content}\n</{m.role}>")
    parts.append("</conversation>")
    parts.append("Reply to the last user message as the assistant.")
    return "\n".join(parts)


def render_blocks(messages: Sequence[_Message]) -> list[dict[str, Any]]:
    """The same as render(), as Anthropic content blocks: a turn's images stay
    where they were among its text (prompt 06 §2). Adjacent text is merged."""
    blocks: list[dict[str, Any]] = []

    def text(t: str) -> None:
        if blocks and blocks[-1]["type"] == "text":
            blocks[-1]["text"] += t
        else:
            blocks.append({"type": "text", "text": t})

    def turn(m: _Message) -> None:
        for p in m.parts or (m.content,):
            if isinstance(p, str):
                text(p)
            else:
                blocks.append(
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": p.media_type, "data": p.data},
                    }
                )

    if len(messages) == 1:
        turn(messages[0])
        return blocks
    text("<conversation>")
    for m in messages:
        text(f"\n<{m.role}>\n")
        turn(m)
        text(f"\n</{m.role}>")
    text("\n</conversation>\nReply to the last user message as the assistant.")
    return blocks
