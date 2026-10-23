"""Files that must never leave the hub for a model (prompt 12 §2, §9.1; the
rule of contract §21.2): a file the secret scan flags is left out WHOLE, never
masked line by line, from "ask the hub"'s corpus and from a substitute
player's read-only checkout.

    flagged(path, text) -> bool   by its name (.env, keys, credential stores)
                                  or by its content (hq_common.redact's
                                  secret shapes: keys, tokens, private keys,
                                  KEY=value secrets)
    prune(root) -> int            every flagged file under root removed (the
                                  checkout is a throwaway copy), and every
                                  file that is not text or is over MAX_BYTES
    python -m hq_common.secret_files <dir>
                                  prune(<dir>); prints only the count

Standard library only (it also runs in the substitute runner's image).
"""

from __future__ import annotations

import fnmatch
import os
import sys
from pathlib import Path

from hq_common.redact import scrub

MAX_BYTES = 200 * 1024
# Names that hold credentials whatever they contain (case-insensitive).
NAME_RULES = (
    ".env",
    ".env.*",
    "*.env",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "*.kdbx",
    "*.gpg",
    "*.asc",
    "id_rsa*",
    "id_dsa*",
    "id_ecdsa*",
    "id_ed25519*",
    "credentials",
    "credentials.*",
    "*credentials*.json",
    "secrets",
    "secrets.*",
    "*.secret",
    "*.secrets",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "_netrc",
    ".git-credentials",
    ".htpasswd",
    "kubeconfig",
    "*.kubeconfig",
    "service-account*.json",
    "*serviceaccount*.json",
    "*.tfstate",
    "*.tfstate.*",
    "terraform.tfvars",
    "auth.json",
    "oauth_creds.json",
    ".dockercfg",
    "config.json.bak",
)
# Directory parts that are never read (tooling state, other people's code).
SKIP_DIRS = frozenset(
    {".git", "node_modules", "vendor", "dist", "build", ".venv", "venv", "__pycache__", ".ssh",
     ".gnupg", ".aws", ".kube", ".docker"}
)  # fmt: skip


def name_flagged(path: str | os.PathLike[str]) -> bool:
    p = Path(path)
    name = p.name.lower()
    if any(part.lower() in SKIP_DIRS for part in p.parts[:-1]):
        return True
    return any(fnmatch.fnmatchcase(name, rule) for rule in NAME_RULES)


def flagged(path: str | os.PathLike[str], text: str | None) -> bool:
    """Whether a file is left out: its name says it holds credentials, or the
    secret scan finds one in its text. `text` None = not readable as text
    (binary): left out too."""
    if name_flagged(path):
        return True
    if text is None:
        return True
    return scrub(text, secrets_only=True) != text


def _text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def prune(root: str | os.PathLike[str]) -> int:
    """Remove every flagged, binary or oversized file and every symlink under
    `root` (a throwaway checkout); returns how many files were removed."""
    base = Path(root)
    removed = 0
    for dirpath, dirnames, filenames in os.walk(base, topdown=True, followlinks=False):
        here = Path(dirpath)
        for d in list(dirnames):
            full = here / d
            if d.lower() in SKIP_DIRS or full.is_symlink():
                dirnames.remove(d)
                removed += _remove_tree(full)
        for f in filenames:
            full = here / f
            rel = full.relative_to(base)
            if full.is_symlink() or not full.is_file() or flagged(rel, _text(full)):
                try:
                    full.unlink()
                    removed += 1
                except OSError:
                    continue
    return removed


def _remove_tree(path: Path) -> int:
    if path.is_symlink():
        path.unlink(missing_ok=True)
        return 1
    n = 0
    for dirpath, dirnames, filenames in os.walk(path, topdown=False):
        for f in filenames:
            (Path(dirpath) / f).unlink(missing_ok=True)
            n += 1
        for d in dirnames:
            target = Path(dirpath) / d
            if target.is_symlink():
                target.unlink(missing_ok=True)
            else:
                target.rmdir()
    path.rmdir()
    return n


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not Path(argv[1]).is_dir():
        print("usage: python -m hq_common.secret_files <dir>", file=sys.stderr)
        return 2
    print(prune(argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
