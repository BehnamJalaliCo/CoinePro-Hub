"""CodeCortex's native stdio MCP server over one indexed repository copy
(prompt 12 §14.6), launched by mcp-proxy. The native server, not the `cortex
mcp` console script: that one adds the semantic-edit tools. The repository
copy is mounted read-only; only its .codecortex state (the index the one-shot
job index.py builds, CodeCortex's manifest lock and its runtime files) is
writable. A call re-checks the copy's files, which never change between two
runs of the job, so nothing is re-indexed while answering.

    python serve.py /index/<repo>
"""

from __future__ import annotations

import sys
from pathlib import Path

from codecortex.mcp.server import run_stdio

if __name__ == "__main__":
    run_stdio(Path(sys.argv[1]))
