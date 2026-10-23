"""The corpus of «از هاب بپرس» (prompt 12 §2.1, contract §21.2). Code, no model.

What it holds
  - the hub's own repository, read from disk (a read-only mount of its git
    directory, HQ_HUB_REPO): `docs/`, `contracts/`, `agents/` (RUNBOOK is in
    docs/ops) and the root's README/CLAUDE.md are kind `doc`, the rest `code`;
  - the default branch of every Code Workshop workspace repository, fetched
    with the hub's EXISTING git access (the workspace's token, the same one
    that pushes hq/<ref>; deploy_diff.remote): kind `code`, under the
    workspace's company (RLS: a CTO reads only its own company's code). A
    repository the hub cannot read stays `not_indexed` and every answer says so.
  The records (resolutions, decisions, deliverables, work, messages) are not
  copied: they are searched where they live (always current), with the same
  Persian normalisation (core.fa_normalize: ی/ي, ک/ك, ZWNJ) and pg_trgm.

Files: text only, at most 200 KB; vendor, node_modules, dist (and the like),
lockfiles and binaries never. A file in which the secret scan (hq_common.redact,
the rules of the redaction of §16.6) finds anything, or a secret file by its
name (.env, keys), is left out ENTIRELY (state `secret`, no passage).
Passages: about 60 lines, with path, line numbers and commit. The build is
incremental (a file whose blob did not change is kept). No embeddings, no
vector store (an embedding model does not fit the CPU and memory budget).

The nightly build (worker, 03:30 Tehran) asks the launch gate first and does
nothing while the holding is locked (no git call either).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from hq_api import audit
from hq_api.db import Tx
from hq_api.domain import deploy_diff as DD
from hq_common.redact import scrub

log = logging.getLogger("hq_api.corpus")

MAX_FILE = 200 * 1024
CHUNK_LINES = 60
MAX_CHUNK_CHARS = 20_000
MAX_LINE = 4000  # a longer line: minified or generated, not read
BATCH = 200
DOC_PREFIXES = ("docs/", "contracts/", "agents/")
DOC_ROOT_FILES = {"README.md", "CLAUDE.md"}
EXCLUDED_DIRS = {
    "vendor",
    "node_modules",
    "dist",
    "build",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".next",
    "target",
    "coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".gradle",
}
LOCKFILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "go.sum",
    "composer.lock",
    "Gemfile.lock",
    "uv.lock",
    "bun.lockb",
    "gradle.lockfile",
    "npm-shrinkwrap.json",
}
BINARY_EXT = {
    "png", "jpg", "jpeg", "gif", "webp", "ico", "bmp", "tif", "tiff", "svg", "psd", "ai",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt",
    "zip", "gz", "tgz", "bz2", "xz", "7z", "rar", "zst", "tar",
    "jar", "war", "class", "so", "dll", "dylib", "exe", "bin", "dat", "o", "a", "pyc", "wasm",
    "db", "sqlite", "sqlite3",
    "woff", "woff2", "ttf", "otf", "eot",
    "mp3", "mp4", "m4a", "wav", "ogg", "opus", "flac", "webm", "mov", "avi", "mkv",
    "onnx", "pt", "pth", "npz", "npy", "parquet", "pkl", "h5",
    "apk", "aab", "keystore", "jks",
}  # fmt: skip
# A secret file by its name is never read (whatever the scan would say).
SECRET_NAME = re.compile(
    r"^(\.env(\..+)?|.*\.(pem|key|p12|pfx|crt|cer|der|asc|gpg|kdbx)|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?"
    r"|\.npmrc|\.pypirc|\.netrc|\.git-credentials|credentials(\..+)?|secrets?\.(ya?ml|json|toml))$",
    re.IGNORECASE,
)
SAFE_ENV_NAMES = {".env.example", ".env.sample", ".env.template"}
SAFE_DIR = {
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "safe.directory",
    "GIT_CONFIG_VALUE_0": "*",
}
STOPWORDS = {
    # Persian (after core.fa_normalize: ی, ک, no ZWNJ)
    "چه", "چی", "چرا", "کی", "کجا", "کدام", "ایا", "را", "از", "به", "در", "با", "که", "این",
    "ان", "برای", "تا", "و", "یا", "است", "هست", "بود", "شد", "شده", "می", "ما", "من", "تو",
    "درباره", "مورد", "های", "ها", "ی", "هم", "یک", "بر", "اینکه", "چطور", "چگونه", "چند",
    "گفتیم", "کردیم", "داریم", "دارد", "باید", "بگو", "بپرس",
    # English
    "the", "a", "an", "of", "to", "in", "on", "for", "what", "why", "how", "is", "are", "was",
    "did", "do", "does", "we", "our", "about", "and", "or", "which", "who", "when", "where",
}  # fmt: skip
WORD = re.compile(r"[^\W_]+")  # letters and digits (Persian ones too); never ؟ or ،
MAX_TERMS = 8
TOP = 20
TOKEN_CAP = 24_000
CHARS_PER_TOKEN = 2.5  # Persian text is dense; an estimate on the safe side
PASSAGE_CHARS = 2400
RECORD_KINDS = ("resolution", "decision", "deliverable", "work", "message")
FILE_KINDS = ("doc", "code")
ALL_KINDS = (*RECORD_KINDS, *FILE_KINDS)


# ------------------------------------------------------------- the files --
def file_kind(path: str, source_kind: str) -> str:
    if source_kind == "hub" and (path.startswith(DOC_PREFIXES) or path in DOC_ROOT_FILES):
        return "doc"
    return "code"


def excluded(path: str) -> str | None:
    """Why a path is never read (None: it may be)."""
    p = PurePosixPath(path)
    if any(part in EXCLUDED_DIRS for part in p.parts[:-1]):
        return "excluded_dir"
    name = p.name
    if name in LOCKFILES or name.endswith((".lock", ".lockb")):
        return "lockfile"
    if name.lower() not in SAFE_ENV_NAMES and SECRET_NAME.match(name):
        return "secret_name"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in BINARY_EXT or name.endswith((".min.js", ".min.css")):
        return "binary"
    return None


def has_secret(text: str) -> bool:
    """The secret scan: anything the redaction's secret rules would mask."""
    return scrub(text, secrets_only=True) != text


def classify(raw: bytes) -> tuple[str, str | None]:
    """(state, text): `indexed` with its text, `secret`, or `skipped`."""
    if b"\0" in raw[:8192]:
        return "skipped", None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "skipped", None
    if any(len(line) > MAX_LINE for line in text.split("\n")):
        return "skipped", None
    if has_secret(text):
        return "secret", None
    return "indexed", text


def chunks(text: str) -> list[tuple[int, int, str]]:
    """~60-line passages: (first line, last line, text)."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    out = []
    for i in range(0, len(lines), CHUNK_LINES):
        part = lines[i : i + CHUNK_LINES]
        body = "\n".join(part)
        if not body.strip():
            continue
        out.append((i + 1, i + len(part), body[:MAX_CHUNK_CHARS]))
    return out


@dataclass
class Entry:
    path: str
    blob: str
    size: int


def parse_tree(raw: str) -> list[Entry]:
    """`git ls-tree -r -l -z` -> blobs (submodules and symlinks left out)."""
    out = []
    for rec in raw.split("\0"):
        if not rec or "\t" not in rec:
            continue
        meta, path = rec.split("\t", 1)
        parts = meta.split()
        if len(parts) < 4 or parts[1] != "blob" or parts[0] == "120000":
            continue
        try:
            size = int(parts[3])
        except ValueError:
            continue
        out.append(Entry(path=path, blob=parts[2], size=size))
    return out


async def read_blobs(git_args: list[str], env: dict[str, str], shas: list[str]) -> dict[str, bytes]:
    """The blobs' contents in one `git cat-file --batch` process."""
    if not shas:
        return {}
    import os
    import tempfile

    base = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": tempfile.gettempdir(),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "LC_ALL": "C",
    }
    proc = await asyncio.create_subprocess_exec(
        "git",
        *git_args,
        "cat-file",
        "--batch",
        env={**base, **env},
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await asyncio.wait_for(proc.communicate(("\n".join(shas) + "\n").encode()), 300)
    blobs: dict[str, bytes] = {}
    pos = 0
    while pos < len(out):
        nl = out.index(b"\n", pos)
        header = out[pos:nl].decode(errors="replace").split()
        pos = nl + 1
        if len(header) < 3 or header[1] != "blob":
            continue  # "<sha> missing"
        size = int(header[2])
        blobs[header[0]] = out[pos : pos + size]
        pos += size + 1
    return blobs


# ---------------------------------------------------------------- sources --
def hub_git_dir(root: str) -> Path | None:
    p = Path(root)
    if (p / "HEAD").is_file() and (p / "objects").is_dir():
        return p
    if (p / ".git" / "HEAD").is_file():
        return p / ".git"
    return None


def corpus_mirror(hub: Any, workspace: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", workspace)
    return Path(hub.settings.git_mirrors) / "corpus" / f"{safe}.git"


async def _source(
    tx: Tx, *, company_id: UUID, key: str, kind: str, repo: str, branch: str | None
) -> dict[str, Any]:
    row = await tx.first("SELECT * FROM knowledge.corpus_sources WHERE key = :k FOR UPDATE", k=key)
    if row is None:
        row = await tx.one(
            """INSERT INTO knowledge.corpus_sources (company_id, key, kind, repo, branch)
               VALUES (:co, :k, :kind, :repo, :b) RETURNING *""",
            co=company_id,
            k=key,
            kind=kind,
            repo=repo,
            b=branch,
        )
    elif row["repo"] != repo or row["branch"] != branch:
        row = await tx.one(
            "UPDATE knowledge.corpus_sources SET repo = :repo, branch = :b, updated_at = now() "
            "WHERE id = :id RETURNING *",
            repo=repo,
            b=branch,
            id=row["id"],
        )
    return row


async def _not_indexed(tx: Tx, src: dict[str, Any], state: str, reason: str) -> dict[str, Any]:
    await tx.exec(
        """UPDATE knowledge.corpus_sources SET state = :st, state_reason = :r, built_at = now(),
               updated_at = now() WHERE id = :id""",
        st=state,
        r=reason[:300],
        id=src["id"],
    )
    return {"source": src["key"], "state": state, "reason": reason[:300]}


async def index_tree(
    tx: Tx,
    src: dict[str, Any],
    git_args: list[str],
    env: dict[str, str],
    commit: str,
) -> dict[str, Any]:
    """One repository at `commit`: new and changed files read, removed ones
    dropped, unchanged ones kept (incremental)."""
    raw = await DD.git(*git_args, "ls-tree", "-r", "-l", "-z", commit, env=env, limit_s=120)
    wanted: dict[str, Entry] = {}
    skipped = 0
    secret_named: list[Entry] = []
    for e in parse_tree(raw):
        why = excluded(e.path)
        if why == "secret_name":
            secret_named.append(e)
        elif why is not None or e.size > MAX_FILE:
            skipped += 1
        else:
            wanted[e.path] = e
    have = {
        r["path"]: r
        for r in await tx.all(
            "SELECT id, path, blob_sha, state FROM knowledge.corpus_files WHERE source_id = :s",
            s=src["id"],
        )
    }
    keep = {e.path for e in [*wanted.values(), *secret_named]}
    gone = [r["id"] for p, r in have.items() if p not in keep]
    if gone:
        await tx.exec("DELETE FROM knowledge.corpus_files WHERE id = ANY(:ids)", ids=gone)
    for e in secret_named:  # left out by its name: no content is read
        old = have.get(e.path)
        if old is not None and old["blob_sha"] == e.blob and old["state"] == "secret":
            continue
        if old is not None:
            await tx.exec("DELETE FROM knowledge.corpus_files WHERE id = :id", id=old["id"])
        await tx.exec(
            """INSERT INTO knowledge.corpus_files (company_id, source_id, path, blob_sha, size, kind, state,
                   reason, commit) VALUES (:co, :s, :p, :b, :size, :k, 'secret', 'secret_name', :c)""",
            co=src["company_id"], s=src["id"], p=e.path, b=e.blob, size=e.size,
            k=file_kind(e.path, src["kind"]), c=commit,
        )  # fmt: skip
    todo = [
        e
        for p, e in wanted.items()
        if p not in have or have[p]["blob_sha"] != e.blob or have[p]["state"] == "skipped"
    ]
    added = 0
    for i in range(0, len(todo), BATCH):
        part = todo[i : i + BATCH]
        blobs = await read_blobs(git_args, env, [e.blob for e in part])
        for e in part:
            old = have.get(e.path)
            if old is not None:
                await tx.exec("DELETE FROM knowledge.corpus_files WHERE id = :id", id=old["id"])
            content = blobs.get(e.blob, b"\0")
            state, text = (
                await asyncio.to_thread(classify, content)
                if len(content) > 20_000
                else classify(content)
            )
            pieces = chunks(text) if text is not None else []
            if state == "indexed" and not pieces:
                state = "skipped"
            f = await tx.one(
                """INSERT INTO knowledge.corpus_files (company_id, source_id, path, blob_sha, size, kind,
                       state, reason, chunks, commit)
                   VALUES (:co, :s, :p, :b, :size, :k, :st, :r, :n, :c) RETURNING id, kind""",
                co=src["company_id"], s=src["id"], p=e.path, b=e.blob, size=e.size,
                k=file_kind(e.path, src["kind"]), st=state,
                r={"secret": "secret_scan", "skipped": "not_text"}.get(state),
                n=len(pieces) if state == "indexed" else 0, c=commit,
            )  # fmt: skip
            for a, b, body in pieces if state == "indexed" else []:
                await tx.exec(
                    """INSERT INTO knowledge.corpus_chunks (company_id, file_id, source_id, kind, repo, path,
                           line_from, line_to, commit, body)
                       VALUES (:co, :f, :s, :k, :repo, :p, :a, :b, :c, :body)""",
                    co=src["company_id"], f=f["id"], s=src["id"], k=f["kind"], repo=src["repo"],
                    p=e.path, a=a, b=b, c=commit, body=body,
                )  # fmt: skip
            added += 1
    counts = await tx.one(
        """SELECT count(*) FILTER (WHERE state = 'indexed') AS files,
                  COALESCE(sum(chunks), 0) AS chunks,
                  count(*) FILTER (WHERE state = 'secret') AS secret,
                  count(*) FILTER (WHERE state = 'skipped') AS skipped
           FROM knowledge.corpus_files WHERE source_id = :s""",
        s=src["id"],
    )
    await tx.exec(
        """UPDATE knowledge.corpus_sources SET commit = :c, state = 'indexed', state_reason = NULL,
               files = :f, chunks = :n, excluded_secret = :sec, skipped = :sk, built_at = now(),
               updated_at = now() WHERE id = :id""",
        c=commit,
        f=int(counts["files"]),
        n=int(counts["chunks"]),
        sec=int(counts["secret"]),
        sk=int(counts["skipped"]) + skipped,
        id=src["id"],
    )
    return {
        "source": src["key"],
        "state": "indexed",
        "commit": commit,
        "read": added,
        "removed": len(gone),
        "files": int(counts["files"]),
        "chunks": int(counts["chunks"]),
        "excluded_secret": int(counts["secret"]),
    }


async def build_hub(tx: Tx, hub: Any) -> dict[str, Any]:
    holding = await hub.companies.holding()
    root = str(getattr(hub.settings, "hub_repo", "") or "")
    src = await _source(
        tx, company_id=holding.id, key="hub", kind="hub", repo="CoinePro-Hub", branch=None
    )
    where = hub_git_dir(root) if root else None
    if where is None:
        return await _not_indexed(tx, src, "not_indexed", "the hub's repository is not on disk")
    args = [f"--git-dir={where}"]
    try:
        commit = (await DD.git(*args, "rev-parse", "HEAD", env=SAFE_DIR)).strip()
    except DD.GitError as exc:
        return await _not_indexed(tx, src, "failed", f"git: {exc.kind}")
    if src["commit"] == commit and src["state"] == "indexed":
        return {"source": "hub", "state": "indexed", "commit": commit, "unchanged": True}
    return await index_tree(tx, src, args, SAFE_DIR, commit)


async def build_workspace(tx: Tx, hub: Any, ws: dict[str, Any]) -> dict[str, Any]:
    src = await _source(
        tx,
        company_id=ws["company_id"],
        key=ws["code"],
        kind="workspace",
        repo=ws["repo"],
        branch=ws["default_branch"],
    )
    found = await DD.remote(hub, ws["code"], ws["company_id"])
    if found is None:
        return await _not_indexed(tx, src, "not_indexed", "the hub cannot read this repository")
    _, url, env = found
    where = corpus_mirror(hub, ws["code"])
    try:
        if not await asyncio.to_thread((where / "HEAD").exists):
            await asyncio.to_thread(where.mkdir, parents=True, exist_ok=True)
            await DD.git("init", "--bare", "-q", str(where))
        await DD.git(
            "fetch", "--no-tags", "--quiet", "--depth=1", url,
            f"+refs/heads/{ws['default_branch']}:refs/hq/corpus",
            cwd=where, env=env, limit_s=hub.settings.git_timeout_s,
        )  # fmt: skip
        commit = (await DD.git("rev-parse", "refs/hq/corpus", cwd=where)).strip()
    except DD.GitError as exc:
        state = "not_indexed" if exc.kind == "no_access" else "failed"
        return await _not_indexed(tx, src, state, f"git: {exc.kind}")
    del env  # the mirror is read locally from here on
    if src["commit"] == commit and src["state"] == "indexed":
        return {"source": ws["code"], "state": "indexed", "commit": commit, "unchanged": True}
    return await index_tree(tx, src, [f"--git-dir={where}"], {}, commit)


async def build(hub: Any, tx_factory: Any) -> dict[str, Any]:
    """The nightly build: the hub's repository, then every active workspace's
    (one transaction each, so one repository's failure keeps the others)."""
    out: list[dict[str, Any]] = []
    async with tx_factory() as tx:
        out.append(await build_hub(tx, hub))
        workspaces = await tx.all(
            """SELECT code, repo, default_branch, company_id FROM workshop.workspaces
               WHERE status = 'active' ORDER BY code"""
        )
    for ws in workspaces:
        try:
            async with tx_factory() as tx:
                out.append(await build_workspace(tx, hub, dict(ws)))
        except Exception as exc:  # noqa: BLE001 - one repository never stops the others
            log.warning("corpus: %s failed: %s", ws["code"], type(exc).__name__)
            out.append({"source": ws["code"], "state": "failed", "reason": type(exc).__name__})
    async with tx_factory() as tx:
        holding = await hub.companies.holding()
        await audit.record(
            tx,
            audit.SYSTEM,
            company_id=holding.id,
            action="corpus.build",
            action_class="A0",
            target_kind="corpus",
            target_ref="nightly",
            summary=json.dumps(
                {
                    r["source"]: r.get("chunks", r.get("state"))
                    for r in out
                    if isinstance(r.get("source"), str)
                },
                ensure_ascii=False,
            )[:500],
        )
    return {"sources": out}


async def not_indexed(tx: Tx, company_ids: list[UUID] | None = None) -> list[str]:
    """The workspace repositories the corpus cannot answer from (never built,
    no access, or failed)."""
    rows = await tx.all(
        """SELECT w.repo FROM workshop.workspaces w
           LEFT JOIN knowledge.corpus_sources s ON s.key = w.code
           WHERE w.status = 'active' AND (s.id IS NULL OR s.state <> 'indexed')
             AND (CAST(:cos AS uuid[]) IS NULL OR w.company_id = ANY(:cos))
           ORDER BY w.repo""",
        cos=company_ids,
    )
    return list(dict.fromkeys(str(r["repo"]) for r in rows))


# ---------------------------------------------------------------- search --
async def terms(tx: Tx, q: str) -> list[str]:
    """The query's words after the Persian normalisation, without stopwords."""
    norm = str(await tx.scalar("SELECT core.fa_normalize(:q)", q=q) or "")
    out: list[str] = []
    for w in WORD.findall(norm):
        w = w.strip("_")
        if len(w) < 2 or w in STOPWORDS or w in out:
            continue
        out.append(w)
    return out[:MAX_TERMS]


async def patterns(tx: Tx, words: list[str]) -> list[str]:
    pats = await tx.scalar(
        "SELECT array_agg('%' || core.like_escape(t) || '%') FROM unnest(CAST(:t AS text[])) t",
        t=words,
    )
    return list(pats or [])


HITS = (
    "(SELECT count(*) FROM unnest(CAST(:pats AS text[])) p WHERE {norm} LIKE p) AS hits, "
    "(SELECT COALESCE(array_agg(p), '{{}}') FROM unnest(CAST(:pats AS text[])) p WHERE {norm} LIKE p) AS matched"
)

RECORD_SQL = {  # kind: (alias, the normalised text, the select)
    "resolution": (
        "r",
        "core.fa_normalize(r.title || ' ' || r.body)",
        """SELECT 'resolution' AS kind, r.ref, c.code AS company, r.company_id, r.title,
                  r.body AS text, r.sealed_at AS at, {hits}
           FROM cartable.resolutions r JOIN core.companies c ON c.id = r.company_id""",
    ),
    "decision": (
        "d",
        "core.fa_normalize(d.title || ' ' || d.what || ' ' || d.why)",
        """SELECT 'decision' AS kind, d.ref, c.code AS company, d.company_id, d.title,
                  d.what || E'\\n' || d.why AS text, d.created_at AS at, {hits}
           FROM cartable.decisions d JOIN core.companies c ON c.id = d.company_id""",
    ),
    "deliverable": (
        "o",
        "core.fa_normalize(o.title || ' ' || o.summary || ' ' || left(o.body, 20000))",
        """SELECT 'deliverable' AS kind, o.ref, c.code AS company, o.company_id, o.title,
                  o.summary || E'\\n' || left(o.body, 4000) AS text, o.created_at AS at, {hits}
           FROM cartable.deliverables o JOIN core.companies c ON c.id = o.company_id""",
    ),
    "work": (
        "w",
        "core.fa_normalize(w.title || ' ' || w.brief)",
        """SELECT 'work' AS kind, w.ref, c.code AS company, w.company_id, w.title,
                  w.brief AS text, w.created_at AS at, {hits}
           FROM work.work w JOIN core.companies c ON c.id = w.company_id""",
    ),
    "message": (
        "m",
        "core.fa_normalize(m.body)",
        """SELECT 'message' AS kind, m.ref, c.code AS company, m.company_id, t.title_fa AS title,
                  m.body AS text, m.created_at AS at, {hits}
           FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
           JOIN core.companies c ON c.id = m.company_id""",
    ),
}
CHUNK_SQL = """
    SELECT ch.kind, ch.repo, ch.path, ch.line_from, ch.line_to, ch.commit, c.code AS company,
           ch.company_id, ch.path AS title, ch.body AS text, f.indexed_at AS at, {hits},
           ts_rank(ch.search, to_tsquery('simple', :tsq)) AS rank
    FROM knowledge.corpus_chunks ch
    JOIN knowledge.corpus_files f ON f.id = ch.file_id
    JOIN core.companies c ON c.id = ch.company_id
    WHERE ch.norm LIKE ANY(CAST(:pats AS text[])) AND ch.kind = ANY(:kinds)
      AND (CAST(:cos AS uuid[]) IS NULL OR ch.company_id = ANY(:cos))
    ORDER BY hits DESC, rank DESC, ch.path, ch.line_from LIMIT :lim
"""


def rank_rows(rows: list[dict[str, Any]]) -> None:
    """Order the candidates by their words' weight (a rare word counts more:
    log(1 + N / df) over the candidates), then the text rank, then newest."""
    n = len(rows) or 1
    df: dict[str, int] = {}
    for r in rows:
        for p in set(r.get("matched") or []):
            df[p] = df.get(p, 0) + 1
    for r in rows:
        r["score"] = sum(math.log(1 + n / df[p]) for p in set(r.get("matched") or []))

    def order(r: dict[str, Any]) -> tuple[Any, ...]:
        at = r.get("at")
        return (-r["score"], -float(r.get("rank") or 0), -(at.timestamp() if at else 0))

    rows.sort(key=order)


def tsquery(words: list[str]) -> str:
    safe = [re.sub(r"[^\w]", "", w) for w in words]
    return " | ".join(f"{w}:*" for w in safe if w) or "''"


def need(n_terms: int) -> int:
    """How many of the query's words a passage must hold."""
    return 1 if n_terms <= 2 else 2


async def chunk_hits(
    tx: Tx, words: list[str], kinds: list[str], company_ids: list[UUID] | None, limit: int
) -> list[dict[str, Any]]:
    wanted = [k for k in kinds if k in FILE_KINDS]
    if not words or not wanted:
        return []
    pats = await patterns(tx, words)
    rows = await tx.all(
        CHUNK_SQL.format(hits=HITS.format(norm="ch.norm")),
        pats=pats,
        tsq=tsquery(words),
        kinds=wanted,
        cos=company_ids,
        lim=limit,
    )
    return [dict(r) for r in rows]


async def record_hits(
    tx: Tx, words: list[str], kinds: list[str], company_ids: list[UUID] | None, limit: int
) -> list[dict[str, Any]]:
    if not words:
        return []
    pats = await patterns(tx, words)
    out: list[dict[str, Any]] = []
    for k in kinds:
        if k not in RECORD_SQL:
            continue
        alias, norm, sql = RECORD_SQL[k]
        rows = await tx.all(
            sql.format(hits=HITS.format(norm=norm))
            + f" WHERE {norm} LIKE ANY(CAST(:pats AS text[]))"
            + f" AND (CAST(:cos AS uuid[]) IS NULL OR {alias}.company_id = ANY(:cos))"
            + " ORDER BY hits DESC, at DESC NULLS LAST LIMIT :lim",
            pats=pats,
            cos=company_ids,
            lim=limit,
        )
        out += [dict(r) for r in rows]
    return out


def cite_key(p: dict[str, Any]) -> str:
    if p["kind"] in FILE_KINDS:
        return f"{p['repo']}/{p['path']}:{p['lines'][0]}-{p['lines'][1]}"
    return str(p["ref"])


def passage(n: int, r: dict[str, Any]) -> dict[str, Any]:
    """A retrieved passage as the librarian sees it (masked) and as a
    citation is checked against it."""
    text = scrub(str(r.get("text") or ""))[:PASSAGE_CHARS]
    out: dict[str, Any] = {
        "n": n,
        "kind": r["kind"],
        "company": r["company"],
        "title": scrub(str(r.get("title") or ""))[:200],
        "text": text,
        "at": r["at"].isoformat() if hasattr(r.get("at"), "isoformat") else None,
    }
    if r["kind"] in FILE_KINDS:
        out.update(
            repo=r["repo"],
            path=r["path"],
            lines=[int(r["line_from"]), int(r["line_to"])],
            commit=r["commit"],
        )
    else:
        out["ref"] = r["ref"]
    out["key"] = cite_key(out)
    return out


async def retrieve(
    tx: Tx,
    q: str,
    *,
    kinds: list[str],
    company_ids: list[UUID] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """The owner's ask: the top passages (<= 20, <= 24K tokens), by code."""
    words = await terms(tx, q)
    if not words:
        return [], words
    rows = await record_hits(tx, words, [k for k in kinds if k in RECORD_KINDS], company_ids, 40)
    rows += await chunk_hits(tx, words, kinds, company_ids, 60)
    rank_rows(rows)
    floor = need(len(words))
    rows = [r for r in rows if int(r["hits"]) >= floor]
    out: list[dict[str, Any]] = []
    tokens = 0
    seen: set[str] = set()
    for r in rows:
        p = passage(len(out) + 1, r)
        if p["key"] in seen:
            continue
        cost = int(len(p["text"]) / CHARS_PER_TOKEN) + 30
        if out and tokens + cost > TOKEN_CAP:
            break
        seen.add(p["key"])
        out.append(p)
        tokens += cost
        if len(out) >= TOP:
            break
    return out, words


async def suggestions(tx: Tx, words: list[str]) -> list[str]:
    """Nothing found: the nearest words of the record titles and the corpus
    paths (trigram similarity, as pg_trgm counts it), so the owner can ask
    again with other words."""
    if not words:
        return []
    rows = await tx.all(
        """SELECT DISTINCT w FROM (
               SELECT regexp_split_to_table(core.fa_normalize(title), '\\s+') AS w
                 FROM cartable.resolutions
               UNION ALL SELECT regexp_split_to_table(core.fa_normalize(title), '\\s+')
                 FROM cartable.decisions
               UNION ALL SELECT regexp_split_to_table(core.fa_normalize(title_fa), '\\s+')
                 FROM knowledge.entries
               UNION ALL SELECT regexp_split_to_table(lower(path), '[/._-]+')
                 FROM knowledge.corpus_files WHERE state = 'indexed'
           ) x WHERE length(w) BETWEEN 3 AND 40 LIMIT 20000"""
    )
    vocab = {str(r["w"]) for r in rows} - set(words)
    scored: dict[str, float] = {}
    for t in words:
        tg = trigrams(t)
        for w in vocab:
            s = similarity(tg, trigrams(w))
            if s >= SUGGEST_AT and s > scored.get(w, 0):
                scored[w] = s
    return [w for w, _ in sorted(scored.items(), key=lambda x: (-x[1], x[0]))[:5]]


SUGGEST_AT = 0.3


def trigrams(word: str) -> set[str]:
    """pg_trgm's trigrams of one word (two spaces before, one after)."""
    s = f"  {word.lower()} "
    return {s[i : i + 3] for i in range(len(s) - 2)}


def similarity(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0
