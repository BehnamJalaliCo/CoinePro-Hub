"""`python -m hq_api.openapi_export [--check]`: write (or verify) the committed
OpenAPI 3.1 document, openapi/hq-api.v1.json — the source of the web
(Orval) and Android clients. CI fails when the file and the code disagree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from hq_api.app import create_app

PATH = Path(__file__).resolve().parents[2] / "openapi" / "hq-api.v1.json"


def document() -> dict[str, Any]:
    return create_app().openapi()


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    text = render(document())
    if "--check" in argv:
        current = PATH.read_text(encoding="utf-8") if PATH.exists() else ""
        if current != text:
            print(
                "openapi: openapi/hq-api.v1.json is out of date; run `make openapi`",
                file=sys.stderr,
            )
            return 1
        print("openapi: hq-api.v1.json matches the code")
        return 0
    PATH.write_text(text, encoding="utf-8")
    print(f"openapi: wrote {PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
