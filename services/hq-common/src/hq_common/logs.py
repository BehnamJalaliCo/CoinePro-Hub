"""Structured JSON logging.

Rule: prompt and response text never reach a log line. Code logs metadata
only, and the formatter drops any extra field whose name suggests content
(prompt, messages, system, text, ...) as a second line of defence.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

# Extra fields that must never be written, whatever the caller passes.
CONTENT_FIELDS = frozenset(
    {"prompt", "messages", "system", "text", "content", "response", "result", "completion"}
)
_STANDARD = frozenset(vars(logging.makeLogRecord({})).keys()) | {
    "message",
    "asctime",
    "color_message",
}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "service": self._service,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key in _STANDARD or key.startswith("_"):
                continue
            if key.lower() in CONTENT_FIELDS:
                entry[key] = "[redacted]"
                continue
            entry[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            # Exception type only: messages can carry request content.
            entry["exc_type"] = record.exc_info[0].__name__
        return json.dumps(entry, default=str, ensure_ascii=False)


def setup(service: str, level: str = "info") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "LiteLLM", "litellm", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # Access logs carry only method/path/status; keep them, in JSON.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True
