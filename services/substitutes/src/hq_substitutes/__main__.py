"""`python -m hq_substitutes`: one job (its JSON on the first stdin line), its
events as JSON lines on stdout. A line that is not a job ends in one `done`
with `error: "failed"`; nothing else is ever written to stdout or stderr."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator

from hq_substitutes.runner import BadJob, Settings, done, parse_job, run


def _lines() -> Iterator[str]:
    for line in sys.stdin:
        yield line.strip()


def main() -> int:
    lines = _lines()
    first = next(lines, "")
    try:
        job = parse_job(first)
    except BadJob as exc:
        print(json.dumps(done(False, error="failed", status_reason=f"bad job: {exc}")), flush=True)
        return 0
    for event in run(job, Settings.from_env(), lines):
        print(json.dumps(event, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
