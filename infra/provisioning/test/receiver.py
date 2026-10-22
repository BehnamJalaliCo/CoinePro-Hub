"""The bench's stand-in for the hub's callback endpoint: every POST is kept
(its Authorization header and body) under /bench/out; it answers 204."""

from __future__ import annotations

import itertools
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

OUT = Path("/bench/out")
COUNT = itertools.count(1)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - the http.server API
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode()
        n = next(COUNT)
        (OUT / f"callback-{n}.json").write_text(
            json.dumps({"authorization": self.headers.get("Authorization"), "path": self.path,
                        "body": json.loads(body)})  # fmt: skip
        )
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_: object) -> None:
        pass


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    HTTPServer(("127.0.0.1", 8099), Handler).serve_forever()
