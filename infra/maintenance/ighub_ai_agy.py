#!/usr/bin/env python3
"""IG-Hub's Gemini replies, the second writer (owner 2026-11-27: the new pages oneoxxo and fxbyfx
answer comments and DMs with Google's Gemini only, never Claude).

IG-Hub writes each answer with Gemini's API itself (ighub/ai.py on IG-Hub). When the API gives no
answer (both of the owner's keys, both models) a task waits there as `agy`; this script, run by
coinepro-hq-ighub-agy.timer every few minutes, takes those tasks over SSH
(`ighub.admin ai-pending`), has Antigravity (agy, Gemini 4 Hydrogen, the owner's own Google
account) write them, and hands each answer back (`ighub.admin ai-answer ID`): IG-Hub checks it
exactly as it checks the API's, then queues it at a person's pace. Nothing is sent from here.

agy runs as a plain print: no tools allowed (never --dangerously-skip-permissions), in a
throwaway empty folder, in its terminal sandbox. With no task waiting, this is one SSH call.

    python3 -I ighub_ai_agy.py            take and write what waits
    python3 -I ighub_ai_agy.py --try FILE write one {"system", "user"} prompt, print the answer
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile

SSH = [
    "ssh", "-4", "-p", "1367", "-i", "/home/Hub/.config/ig-hub/id_ed25519",
    "-o", "IdentitiesOnly=yes", "-o", "UserKnownHostsFile=/home/Hub/.config/ig-hub/known_hosts",
    "-o", "ConnectTimeout=20", "-o", "BatchMode=yes", "ighub@91.107.166.193",
]  # fmt: skip
ADMIN = (
    'sudo -u igapp bash -c "set -a; . /etc/ig-hub/ig-hub.env; set +a; cd /srv/ig-hub/backend;'
    ' .venv/bin/python -m ighub.admin {}"'
)
AGY = "/home/Hub/.local/bin/agy"
MODEL = "gemini-4-hydrogen-medium"
TAKE = 5


def admin(args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv
        [*SSH, ADMIN.format(args)], input=stdin, capture_output=True, text=True, timeout=120
    )


def write(system: str, user: str) -> str:
    prompt = (
        f"{system}\n\n---\n\n{user}\n\nDo not use any tools or files. Reply with the JSON object"
        " only."
    )
    with tempfile.TemporaryDirectory(prefix="agy-ighub-") as d:
        r = subprocess.run(  # noqa: S603 - fixed argv, the prompt is one argument
            [
                AGY, "--sandbox", "--disable-slash-commands", "--print-timeout", "150s",
                "--output-format", "json", "--model", MODEL, "-p", prompt,
            ],  # fmt: skip
            cwd=d, capture_output=True, text=True, timeout=200,
        )  # fmt: skip
    if r.returncode != 0:
        raise RuntimeError(f"agy rc={r.returncode}: {r.stderr.strip()[:200]}")
    out = json.loads(r.stdout)
    if out.get("status") != "SUCCESS":
        raise RuntimeError(f"agy status {out.get('status')}")
    return str(out.get("response") or "")


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "--try":
        with open(argv[2], encoding="utf-8") as fh:
            p = json.load(fh)
        print(write(p["system"], p["user"]))
        return 0
    got = admin(f"ai-pending {TAKE}")
    if got.returncode != 0:
        print(f"ai-pending failed: {got.stderr.strip()[:300]}", file=sys.stderr)
        return 1
    tasks = json.loads(got.stdout or "[]")
    failed = 0
    for t in tasks:
        tid = int(t["id"])
        try:
            answer = write(str(t["system"]), str(t["user"]))
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as e:
            print(f"task {tid}: agy did not write it ({e})", file=sys.stderr)
            failed += 1
            continue
        a = admin(f"ai-answer {tid} agy:{MODEL}", stdin=answer)
        print(f"task {tid}: {(a.stdout or a.stderr).strip()[:300]}")
    return 1 if failed and failed == len(tasks) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
