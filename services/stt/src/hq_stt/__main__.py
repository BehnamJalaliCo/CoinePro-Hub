"""`python -m hq_stt`: serve the internal API (network hq-stt only)."""

from __future__ import annotations

import sys

import uvicorn

from hq_common import logs
from hq_stt.config import Settings
from hq_stt.lock import ModelInvalid
from hq_stt.main import create_app


def main() -> int:
    settings = Settings()
    logs.setup("stt", settings.log_level)
    try:
        app = create_app(settings)
    except ModelInvalid as exc:
        # Never serve a model whose bytes are not the pinned ones.
        print(f"stt: refusing to start: {exc}", file=sys.stderr)
        return 2
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.listen_port,
        log_config=None,
        server_header=False,
        proxy_headers=False,
        access_log=False,
        timeout_graceful_shutdown=30,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
