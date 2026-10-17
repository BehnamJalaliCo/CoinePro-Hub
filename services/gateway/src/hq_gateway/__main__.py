"""`python -m hq_gateway`: the Tool Gateway on :8080 (hq-core only)."""

from __future__ import annotations

import uvicorn

from hq_common import logs
from hq_gateway.app import create_app
from hq_gateway.config import Settings


def main() -> None:
    s = Settings()
    logs.setup("tool-gateway", s.log_level)
    uvicorn.run(
        create_app(s),
        host="0.0.0.0",
        port=s.listen_port,
        log_config=None,
        access_log=False,
        proxy_headers=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
