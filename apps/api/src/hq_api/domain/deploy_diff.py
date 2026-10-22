"""The real diff on a deploy card (prompt 12 §7, contract §21.6). A service,
not a model: the api reads the repository with the hub's EXISTING git access
(the owner's decision: no new GitHub token), i.e. the Code Workshop's token
of the workspace whose repository it is (OpenBao hq-api/workshop/github/<ws>,
the same one that pushes hq/<ref>). A repository the hub cannot read is
`diff: null, diff_unavailable: "no_access"`; the card stays bound to its
top-level `head_sha` either way.

    attach(hub, payload)   when the card is proposed: fetch, check head_sha
                           (not in the repository -> 422), build the diff
    head_now(hub, payload) the PR branch's head now (git ls-remote)
    recheck(hub, ...)      every 15 minutes for pending cards, and once more
                           before the seal: a new push sets the card aside
    file_patch(...)        one file's whole patch (<= 2000 lines), masked

Bounds: <= 300 files, <= 400 patch lines per file, <= 256 KB of patches in
all; a binary file has no patch. Every patch line in which the secret scan
(hq_common.redact) finds anything is masked and its file is
`secret_masked: true`. The token travels in git's environment
(GIT_CONFIG_*), never in argv, a file or a log.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hq_api.errors import ApiError
from hq_common.redact import scrub

log = logging.getLogger("hq_api.deploy_diff")

MAX_FILES = 300
MAX_LINES = 400
MAX_BYTES = 256 * 1024
FILE_LINES = 2000  # GET /decisions/{ref}/diff?file=
TOO_LARGE_FILES = 20_000
DEPTH = 200
WORKSPACE_KV = "hq-api/workshop/github/{workspace}"
PR_NUMBER = re.compile(r"/pull/([0-9]{1,9})(?:[/?#].*)?$")
NO_ACCESS = re.compile(
    r"(Authentication failed|could not read Username|Repository not found|"
    r"terminal prompts disabled|HTTP 40[13]|returned error: 40[134]|does not appear to be a git repository|"
    r"Permission denied)",
    re.IGNORECASE,
)
STATUS = {
    "A": "added",
    "M": "modified",
    "D": "removed",
    "R": "renamed",
    "C": "added",
    "T": "modified",
}


class GitError(Exception):
    def __init__(self, kind: str, message: str = "") -> None:
        super().__init__(message or kind)
        self.kind = kind  # no_access | fetch_failed | missing


# ------------------------------------------------------------ the remote --
async def remote(
    hub: Any, repo: str, company_id: Any = None
) -> tuple[str, str, dict[str, str]] | None:
    """(workspace code, remote URL, extra git env) for a repository the hub
    reads (a workspace of the proposer's company, when given), else None (no
    workspace, or an https remote without its token)."""
    async with hub.db.tx(await hub.companies.ids()) as tx:
        ws = await tx.first(
            """SELECT code, repo, default_branch FROM workshop.workspaces
               WHERE (lower(repo) = lower(:r) OR lower(code) = lower(:r)
                      OR lower(split_part(repo, '/', 2)) = lower(:r))
                 AND (CAST(:co AS uuid) IS NULL OR company_id = :co)
               ORDER BY lower(repo) = lower(:r) DESC, code LIMIT 1""",
            r=repo.strip(),
            co=company_id,
        )
    if ws is None:
        return None
    url = hub.settings.git_remote.format(repo=ws["repo"])
    env: dict[str, str] = {}
    if url.startswith("https://"):
        token = await _token(hub, ws["code"])
        if not token:
            return None
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraHeader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
        }
        del token, basic
    return f"{ws['code']}:{ws['default_branch']}", url, env


async def _token(hub: Any, workspace: str) -> str | None:
    if getattr(hub, "bao", None) is None:
        return None
    try:
        data = await hub.bao.read_kv(WORKSPACE_KV.format(workspace=workspace))
    except Exception:  # noqa: BLE001 - no token: the hub has no access
        return None
    token = (data or {}).get("token")
    return str(token) if token else None


# ------------------------------------------------------------------- git --
async def git(
    *args: str, cwd: Path | None = None, env: dict[str, str] | None = None, limit_s: int = 120
) -> str:
    base = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": tempfile.gettempdir(),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_ASKPASS": "/bin/false",
        "LC_ALL": "C",
    }
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd) if cwd else None,
        env={**base, **(env or {})},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), limit_s)
    except TimeoutError as exc:
        proc.kill()
        raise GitError("fetch_failed", "git timed out") from exc
    if proc.returncode != 0:
        text = err.decode(errors="replace")[-2000:]
        kind = "no_access" if NO_ACCESS.search(text) else "fetch_failed"
        if "unknown revision" in text or "bad object" in text or "not a valid object" in text:
            kind = "missing"
        raise GitError(kind, text.splitlines()[-1] if text else "git failed")
    return out.decode(errors="replace")


def mirror_dir(hub: Any, workspace: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", workspace.split(":")[0])
    return Path(hub.settings.git_mirrors) / f"{safe}.git"


def pr_number(pr_url: str) -> int | None:
    m = PR_NUMBER.search(pr_url or "")
    return int(m.group(1)) if m else None


async def _fetch(hub: Any, where: Path, url: str, env: dict[str, str], refspecs: list[str]) -> None:
    if not await asyncio.to_thread((where / "HEAD").exists):
        await asyncio.to_thread(where.mkdir, parents=True, exist_ok=True)
        await git("init", "--bare", "-q", str(where))
    await git(
        "fetch", "--no-tags", "--quiet", f"--depth={DEPTH}", url, *refspecs,
        cwd=where, env=env, limit_s=hub.settings.git_timeout_s,
    )  # fmt: skip


async def _has(where: Path, sha: str) -> bool:
    try:
        await git("cat-file", "-e", f"{sha}^{{commit}}", cwd=where)
    except GitError:
        return False
    return True


async def ensure(hub: Any, payload: dict[str, Any], company_id: Any = None) -> tuple[Path, str]:
    """The mirror holding the base branch and the card's head_sha; returns
    (mirror, base sha). Raises GitError (no_access, fetch_failed, missing)."""
    found = await remote(hub, str(payload.get("repo") or ""), company_id)
    if found is None:
        raise GitError("no_access", "the hub cannot read this repository")
    workspace, url, env = found
    branch = workspace.split(":", 1)[1] or "main"
    where = mirror_dir(hub, workspace)
    head = str(payload["head_sha"])
    specs = [f"+refs/heads/{branch}:refs/hq/base"]
    n = pr_number(str(payload.get("pr_url") or ""))
    if n is not None:
        specs.append(f"+refs/pull/{n}/head:refs/hq/pr-{n}")
    try:
        await _fetch(hub, where, url, env, specs)
    except GitError:
        if n is None:
            raise
        await _fetch(hub, where, url, env, specs[:1])  # no PR ref: the base, then the sha
    if not await _has(where, head):
        try:
            await _fetch(hub, where, url, env, [head])
        except GitError as exc:
            if exc.kind == "no_access":
                raise
        if not await _has(where, head):
            raise GitError("missing", "head_sha is not in the repository")
    base_tip = (await git("rev-parse", "refs/hq/base", cwd=where)).strip()
    try:
        base = (await git("merge-base", base_tip, head, cwd=where)).strip()
    except GitError:
        base = base_tip  # shallow history: the base branch's tip
    return where, base or base_tip


# ------------------------------------------------------------- the diff --
def mask(lines: list[str]) -> tuple[list[str], bool]:
    """Patch lines with every line holding a secret masked."""
    out, masked = [], False
    for line in lines:
        clean = scrub(line, secrets_only=True)
        if clean != line:
            masked = True
            out.append(clean)
        else:
            out.append(line)
    return out, masked


def _numstat(raw: str) -> list[dict[str, Any]]:
    """`git diff --numstat -z -M` -> [{path, old_path?, additions, deletions, binary}]."""
    parts = raw.split("\0")
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(parts):
        head = parts[i]
        if not head:
            i += 1
            continue
        adds, dels, path = [*head.split("\t", 2), "", ""][:3]
        old = None
        if path == "":  # a rename: "adds\tdels\t" then old, new
            old, path = parts[i + 1], parts[i + 2]
            i += 3
        else:
            i += 1
        binary = adds == "-" and dels == "-"
        out.append(
            {
                "path": path,
                "old_path": old,
                "additions": 0 if binary else int(adds or 0),
                "deletions": 0 if binary else int(dels or 0),
                "binary": binary,
            }
        )
    return out


def _statuses(raw: str) -> dict[str, str]:
    parts = raw.split("\0")
    out: dict[str, str] = {}
    i = 0
    while i < len(parts):
        code = parts[i]
        if not code:
            i += 1
            continue
        letter = code[0]
        if letter in ("R", "C"):
            out[parts[i + 2]] = STATUS[letter]
            i += 3
        else:
            out[parts[i + 1]] = STATUS.get(letter, "modified")
            i += 2
    return out


async def patch_of(where: Path, base: str, head: str, f: dict[str, Any]) -> list[str]:
    paths = [f["old_path"], f["path"]] if f.get("old_path") else [f["path"]]
    raw = await git("diff", "--no-color", "-M", base, head, "--", *paths, cwd=where)
    lines = raw.splitlines()
    start = next((i for i, x in enumerate(lines) if x.startswith("@@")), len(lines))
    return lines[start:]


async def build(where: Path, base: str, head: str) -> dict[str, Any] | None:
    """The `diff` object (None when the change is too large to list)."""
    stats = _numstat(await git("diff", "--numstat", "-z", "-M", base, head, cwd=where))
    if len(stats) > TOO_LARGE_FILES:
        return None
    statuses = _statuses(await git("diff", "--name-status", "-z", "-M", base, head, cwd=where))
    files: list[dict[str, Any]] = []
    used = 0
    truncated = len(stats) > MAX_FILES
    for f in stats[:MAX_FILES]:
        row: dict[str, Any] = {
            "path": f["path"],
            "status": statuses.get(f["path"], "modified"),
            "additions": f["additions"],
            "deletions": f["deletions"],
            "binary": f["binary"],
            "patch": None,
            "truncated": False,
            "secret_masked": False,
        }
        if not f["binary"]:
            lines = await patch_of(where, base, head, f)
            if len(lines) > MAX_LINES:
                lines, row["truncated"] = lines[:MAX_LINES], True
            lines, row["secret_masked"] = mask(lines)
            text = "\n".join(lines)
            size = len(text.encode())
            if used + size > MAX_BYTES:
                row["truncated"], truncated = True, True
                text = None  # type: ignore[assignment]
            else:
                used += size
            row["patch"] = text
        files.append(row)
    return {
        "base_sha": base,
        "head_sha": head,
        "total_files": len(stats),
        "total_additions": sum(f["additions"] for f in stats),
        "total_deletions": sum(f["deletions"] for f in stats),
        "truncated": truncated,
        "fetched_at": datetime.now(UTC).isoformat(),
        "files": files,
    }


async def attach(hub: Any, payload: dict[str, Any], company_id: Any = None) -> dict[str, Any]:
    """The payload with the api's `diff` / `diff_unavailable` (whatever the
    proposer sent there is replaced). A head_sha not in the repository -> 422."""
    out = {k: v for k, v in payload.items() if k not in ("diff", "diff_unavailable")}
    head = str(out.get("head_sha") or "")
    if not re.fullmatch(r"[0-9a-f]{7,64}", head):
        return out  # validate_payload answers 422 for head_sha
    try:
        where, base = await ensure(hub, out, company_id)
        full = (await git("rev-parse", f"{head}^{{commit}}", cwd=where)).strip()
        diff = await build(where, base, full)
    except GitError as exc:
        if exc.kind == "missing":
            raise ApiError(
                422, "validation_failed", fields={"payload.head_sha": "not in the repository"}
            ) from exc
        log.info("deploy diff unavailable", extra={"why": exc.kind})
        out["diff_unavailable"] = exc.kind
        return out
    if diff is None:
        out["diff_unavailable"] = "too_large"
    else:
        out["diff"] = diff
    return out


async def file_patch(
    hub: Any, payload: dict[str, Any], path: str, company_id: Any = None
) -> dict[str, Any]:
    """One file's whole patch (<= 2000 lines), masked like the card's."""
    diff = payload.get("diff") or {}
    row = next((f for f in diff.get("files") or [] if f["path"] == path), None)
    if row is None:
        raise ApiError(404, "not_found", "no such file in the card's diff")
    out = {**row, "truncated": False}
    if row.get("binary"):
        return {**out, "patch": None}
    try:
        where, _ = await ensure(hub, payload, company_id)
        stats = _numstat(
            await git(
                "diff",
                "--numstat",
                "-z",
                "-M",
                diff["base_sha"],
                diff["head_sha"],
                "--",
                path,
                cwd=where,
            )
        )
        f = next((s for s in stats if s["path"] == path), {"path": path, "old_path": None})
        lines = await patch_of(where, diff["base_sha"], diff["head_sha"], f)
    except GitError as exc:
        raise ApiError(409, "not_ready", f"the repository cannot be read now ({exc.kind})") from exc
    if len(lines) > FILE_LINES:
        lines, out["truncated"] = lines[:FILE_LINES], True
    lines, out["secret_masked"] = mask(lines)
    out["patch"] = "\n".join(lines)
    return out


# ---------------------------------------------------------- the binding --
async def head_now(hub: Any, payload: dict[str, Any], company_id: Any = None) -> str | None:
    """The PR branch's head now, or None when it cannot be read (no access,
    no PR number, the network): then nothing is set aside."""
    n = pr_number(str(payload.get("pr_url") or ""))
    if n is None:
        return None
    found = await remote(hub, str(payload.get("repo") or ""), company_id)
    if found is None:
        return None
    _, url, env = found
    try:
        raw = await git("ls-remote", url, f"refs/pull/{n}/head", env=env, limit_s=60)
    except GitError:
        return None
    first = raw.split()
    return first[0] if first else None


def moved(payload: dict[str, Any], now_sha: str | None) -> bool:
    head = str(payload.get("head_sha") or "")
    return bool(now_sha and head and not now_sha.startswith(head) and not head.startswith(now_sha))


async def before_seal(hub: Any, ref: str) -> None:
    """Once more before the owner's seal: a pending deploy card whose PR
    branch moved is set aside now, so the approval answers 409
    decision_not_pending. A head that cannot be read sets nothing aside."""
    from hq_api import workflows_client
    from hq_api.domain import decisions as D

    async with hub.db.tx(await hub.companies.ids()) as tx:
        d = await tx.first(D.DECISION_SQL + " WHERE d.ref = :r", r=ref)
    if d is None or d["kind"] != "deploy" or d["status"] != "pending":
        return
    now_sha = await head_now(hub, d["payload"] or {}, d["company_id"])
    if not moved(d["payload"] or {}, now_sha):
        return
    async with hub.db.tx(await hub.companies.ids()) as tx:
        done = await set_aside(tx, d, str(now_sha))
    if done:
        try:
            await workflows_client.decision_decided(hub, ref)
        except Exception:  # noqa: BLE001 - reconcile_decisions catches up
            log.warning("could not signal %s", ref)


async def set_aside(tx: Any, d: dict[str, Any], now_sha: str) -> bool:
    """A new push supersedes the card: withdrawn, the proposer is told."""
    from hq_api import audit, events
    from hq_api.domain import decisions as D
    from hq_api.domain import work as W
    from hq_api.principal import Principal

    n = await tx.exec(
        """UPDATE cartable.decisions SET status = 'withdrawn', decided_at = now(), decided_by_kind = 'service',
               decided_by_code = 'deploy-diff', note = :note
           WHERE id = :id AND status = 'pending'""",
        id=d["id"],
        note=f"superseded: a new push on the PR branch ({now_sha[:12]}); a new card with the new diff is needed",
    )
    if not n:
        return False
    await events.emit(
        tx, d["company"], "decision.updated", d["ref"], {"status": "withdrawn", "why": "superseded"}
    )
    await D.post_system_message(
        tx,
        d["thread_code"],
        f"کارت {d['ref']} کنار رفت: push تازه روی شاخه‌ی PR ({now_sha[:12]}). کارت تازه با diff تازه لازم است.",
        {"decision": d["ref"]},
    )
    if d["proposer_kind"] == "agent":
        await W.create(
            tx,
            Principal(kind="service", code="deploy-diff", role="service"),
            company_id=d["company_id"],
            company_code=d["company"],
            title=f"کارت deploy {d['ref']} کنار رفت: push تازه"[:300],
            brief=(
                f"سرشاخه‌ی PR کارت {d['ref']} دیگر {d['payload'].get('head_sha')} نیست ({now_sha[:12]}). "
                "اگر هنوز deploy لازم است، کارت تازه با head_sha تازه بساز."
            ),
            kind="one_off",
            priority="P3",
            assignee_code=d["proposer_code"],
        )
    await audit.record(
        tx,
        audit.SYSTEM,
        company_id=d["company_id"],
        action="decision.superseded",
        action_class="A1",
        target_kind="decision",
        target_ref=d["ref"],
        summary=f"new push {now_sha[:12]} on the PR branch",
    )
    return True
