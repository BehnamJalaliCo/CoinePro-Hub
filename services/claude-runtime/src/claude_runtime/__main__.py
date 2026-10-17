"""`python -m claude_runtime`: serve the internal API (hq-llm network only)."""

from __future__ import annotations

import uvicorn

from claude_runtime.config import Settings
from claude_runtime.main import create_app
from hq_common import logs


def main() -> None:
    settings = Settings()
    logs.setup("claude-runtime", settings.log_level)
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",
        port=settings.listen_port,
        log_config=None,
        server_header=False,
        proxy_headers=False,
        # No uvicorn access line: it carries full paths with query strings.
        access_log=False,
        timeout_graceful_shutdown=30,
    )


if __name__ == "__main__":
    main()
