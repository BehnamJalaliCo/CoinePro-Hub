"""`python -m llm_router`: serve the internal API."""

from __future__ import annotations

import uvicorn

from hq_common import logs
from llm_router.config import Settings
from llm_router.main import create_app


def main() -> None:
    settings = Settings()
    logs.setup("llm-router", settings.log_level)
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
