"""What the speaker tells an adapter without changing the base interface of `Engine.speak`."""

from __future__ import annotations

import contextvars

# The stored sentence's file name: the audio is a file of the conversation.
FILE_NAME: contextvars.ContextVar[str] = contextvars.ContextVar("voice_file_name", default="voice")
