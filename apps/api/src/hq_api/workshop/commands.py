"""What a workshop session may run on its own, what it must ask, and what it
never runs (contract §17.3 rules 1-3).

A session works on a fresh clone in its own sandbox. Reading, editing,
testing and committing on its own branch need nobody; pushing its branch,
opening a PR and anything outside the allow-list wait for the owner
(an approval_request); a push to any branch but `hq/<session-ref>`, a
force push, and anything that reaches production or credentials is refused
outright, whoever asks.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Literal

Verdict = Literal["allow", "ask", "deny"]

# Plain reading, editing and checking inside the clone.
ALLOW_PROGRAMS = frozenset(
    {
        "ls", "cat", "head", "tail", "wc", "grep", "rg", "find", "sed", "awk", "diff", "pwd",
        "echo", "true", "test", "sort", "uniq", "tree", "stat", "file", "jq",
        "python", "python3", "pytest", "ruff", "mypy", "black", "isort", "coverage", "tox",
        "node", "npm", "npx", "pnpm", "yarn", "tsc", "eslint", "prettier", "vitest", "jest",
        "go", "cargo", "make", "gradle", "./gradlew", "mvn", "pip", "uv",
    }
)  # fmt: skip
ALLOW_GIT = frozenset(
    {"status", "diff", "log", "show", "add", "commit", "branch", "checkout", "switch",
     "restore", "rev-parse", "ls-files", "blame", "stash", "fetch", "pull", "merge-base"}
)  # fmt: skip
# Never, whoever asks: production, credentials, other hosts, containers, cloud.
DENY_PROGRAMS = frozenset(
    {
        "ssh", "scp", "sftp", "rsync", "telnet", "nc", "ncat", "socat", "sudo", "su",
        "docker", "podman", "kubectl", "helm", "terraform", "ansible", "ansible-playbook",
        "aws", "gcloud", "az", "hcloud", "doctl", "flyctl", "vercel", "netlify", "heroku",
        "psql", "mysql", "redis-cli", "mongosh", "bao", "vault", "openssl",
    }
)  # fmt: skip
# Credential files and the process environment: never read, whatever the command.
SECRET_HINT = re.compile(
    r"((^|[\s/=])\.env(\.|\b)|id_rsa|id_ed25519|\.ssh/|\.aws/|\.netrc|\.git-credentials|"
    r"/proc/[^/\s]+/environ|\bprintenv\b|^\s*env(\s|$)|\bset\s*$)",
    re.IGNORECASE,
)
SHELL_CHAINS = re.compile(r"(;|&&|\|\||\||`|\$\()")


@dataclass(frozen=True)
class Ruling:
    verdict: Verdict
    action: str = "command"  # push_branch | open_pr | command
    reason: str = ""


def _words(cmd: str) -> list[str]:
    try:
        return shlex.split(cmd)
    except ValueError:
        return []


def classify(cmd: str, *, session_ref: str, branch_prefix: str = "hq/") -> Ruling:
    """The ruling on one shell command of a session (no execution here)."""
    text = cmd.strip()
    own_branch = f"{branch_prefix}{session_ref}"
    if not text:
        return Ruling("deny", reason="empty")
    if SECRET_HINT.search(text):
        return Ruling("deny", reason="touches credentials or environment files")
    parts = [p.strip() for p in re.split(r"&&|;|\|\||\|", text) if p.strip()]
    if SHELL_CHAINS.search(text) and len(parts) > 1:
        rulings = [classify(p, session_ref=session_ref, branch_prefix=branch_prefix) for p in parts]
        for r in rulings:
            if r.verdict == "deny":
                return r
        asks = [r for r in rulings if r.verdict == "ask"]
        return asks[0] if asks else Ruling("allow")
    if "`" in text or "$(" in text:
        return Ruling("ask", reason="command substitution")
    words = _words(text)
    if not words:
        return Ruling("ask", reason="unparsed")
    program = words[0]
    if program in DENY_PROGRAMS:
        return Ruling("deny", reason=f"{program} is never run in the workshop")
    if program in ("curl", "wget"):
        return Ruling("ask", reason="network access")
    if program == "git":
        sub = next((w for w in words[1:] if not w.startswith("-")), "")
        if sub == "push":
            if any(w in ("-f", "--force", "--force-with-lease", "--mirror", "--all", "--tags")
                   for w in words) or any(w.startswith("+") for w in words[2:]):  # fmt: skip
                return Ruling("deny", reason="force pushes and bulk pushes are refused")
            targets = [w for w in words[2:] if not w.startswith("-") and w not in ("origin",)]
            refs = [t.split(":")[-1] for t in targets] or [own_branch]
            if any(r.removeprefix("refs/heads/") != own_branch for r in refs):
                return Ruling("deny", reason=f"only {own_branch} may be pushed")
            return Ruling("ask", action="push_branch", reason=f"push {own_branch}")
        if sub in ("remote", "config", "reset", "clean", "rebase", "filter-branch", "gc"):
            return Ruling("ask", reason=f"git {sub}")
        if sub in ALLOW_GIT:
            return Ruling("allow")
        return Ruling("ask", reason=f"git {sub}")
    if program == "gh":
        if words[1:3] == ["pr", "create"]:
            return Ruling("ask", action="open_pr", reason="open a pull request")
        if words[1:3] in (["pr", "view"], ["pr", "list"], ["pr", "diff"], ["pr", "checks"]):
            return Ruling("allow")
        if words[1:3] in (["pr", "merge"], ["release", "create"], ["repo", "delete"]):
            return Ruling("deny", reason="merge, release and delete stay with the owner's seal")
        return Ruling("ask", reason="gh " + " ".join(words[1:3]))
    if program in ALLOW_PROGRAMS:
        return Ruling("allow")
    return Ruling("ask", reason=f"{program} is outside the allow-list")
