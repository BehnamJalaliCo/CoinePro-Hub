"""`python -m hq_ocr`: serve the internal API (network hq-ocr only)."""

from __future__ import annotations

import sys

from hq_common import logs
from hq_ocr import lock
from hq_ocr.config import Settings
from hq_ocr.main import Service, serve


def main() -> int:  # pragma: no cover - the process itself
    settings = Settings()
    logs.setup("ocr", settings.log_level)
    try:
        service = Service(settings)
    except lock.ModelInvalid as exc:
        # Never read a document with traineddata whose bytes are not the pinned ones.
        print(f"ocr: refusing to start: {exc}", file=sys.stderr)
        return 2
    server = serve(service)
    print(f"ocr: listening on :{settings.listen_port} ({service.pinned.name}, {service.version})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
