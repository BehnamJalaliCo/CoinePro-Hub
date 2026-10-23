"""The CodeCortex index job (prompt 12 §14.6): one-shot, the same image as the
server, `network_mode: none`. Rule-only: no model and no outside call, so it
runs while the holding's kill switch is engaged too (it reads the hub's own
repositories and writes only its own volume).

For each repository mounted read-only under /src/<name> it keeps a copy on the
repositories volume (/index/<name>: a git copy of what the hub reads, checked
out at the source's HEAD, every branch fetched for PR intelligence), then
refreshes CodeCortex's incremental index in /index/<name>/.codecortex, which
is the repository's own state volume (the server mounts the copies read-only
and only that state read-write). A copy already indexed at the source's HEAD
is left alone unless `--full`; nothing is ever written to /src.

    python index.py [--full]        prints one JSON line per repository
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SRC = Path(os.environ.get("CODECORTEX_SRC", "/src"))
INDEX = Path(os.environ.get("CODECORTEX_INDEX", "/index"))
MARKER = ".hq-indexed"
# Nothing of CodeCortex reaches out or writes back into the code: telemetry,
# dependency documentation, rewrites and generated precision indexes off.
CONFIG = {
    "telemetry": False,
    "dependency_docs": {"enabled": False},
    "structural": {"allow_apply": False},
    "precision_index": {"auto_generate": False},
}


GIT = "/usr/bin/git"
REFS = "+refs/heads/*:refs/remotes/origin/*"


def git(*args: str) -> str:
    # Fixed arguments of this file and the mounted paths; never a shell.
    out = subprocess.run(  # noqa: S603
        [GIT, *args], check=True, capture_output=True, text=True, timeout=900
    )
    return out.stdout.strip()


def sync(src: Path, dst: Path) -> str:
    """The copy at the source's HEAD; returns that commit. `dst` may already
    hold .codecortex (the state volume's mount point), so no `git clone`."""
    if not (dst / ".git").exists():
        dst.mkdir(parents=True, exist_ok=True)
        git("-C", str(dst), "init", "--quiet")
        git("-C", str(dst), "remote", "add", "origin", str(src))
    git("-C", str(dst), "fetch", "--quiet", "--prune", "origin", REFS)
    head = git("-C", str(src), "rev-parse", "HEAD")
    git("-C", str(dst), "fetch", "--quiet", "origin", head)
    git("-C", str(dst), "checkout", "--quiet", "--force", "--detach", head)
    git("-C", str(dst), "clean", "-q", "-f", "-d", "-x", "-e", ".codecortex", "-e", MARKER)
    return head


def index(dst: Path) -> dict[str, Any]:
    from codecortex.indexing.incremental_graph import IncrementalGraphIndex

    state = dst / ".codecortex"
    for sub in ("runtime", "memory", "cache"):
        (state / sub).mkdir(parents=True, exist_ok=True)
    (state / "config.json").write_text(json.dumps(CONFIG, sort_keys=True), encoding="utf-8")
    graph, stats = IncrementalGraphIndex(dst).refresh()
    return {
        "tracked": stats.index.tracked,
        "files_reparsed": stats.files_reparsed,
        "full_rebuild": stats.full_rebuild,
        "graph_nodes": len(graph.nodes),
        "graph_edges": len(graph.edges),
    }


def main(full: bool) -> int:
    failed = 0
    for src in sorted(p for p in SRC.iterdir() if (p / ".git").exists()):
        dst = INDEX / src.name
        try:
            head = sync(src, dst)
            marker = dst / MARKER
            if not full and marker.exists() and marker.read_text().strip() == head:
                print(json.dumps({"repo": src.name, "commit": head, "skipped": "unchanged"}))
                continue
            out = index(dst)
            marker.write_text(head + "\n", encoding="utf-8")
            print(json.dumps({"repo": src.name, "commit": head, **out}))
        except (OSError, subprocess.SubprocessError) as exc:
            failed = 1
            print(json.dumps({"repo": src.name, "error": type(exc).__name__}))
    return failed


if __name__ == "__main__":
    sys.exit(main("--full" in sys.argv[1:]))
