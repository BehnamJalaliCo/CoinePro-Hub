#!/usr/bin/env python3
"""DotCoin.me's SEO day as ONE package (stdlib only): what the day's session changed in the site's
source, checked by the same rules on both sides.

The session (kit dotcoin-seo, user studio) works in a git copy of the site's source taken by the
hub (the input pack's site.tar, its commit in BASE). `make` turns its changes into package.zip:

    manifest.json   {"version": 1, "day", "base", "files": [{"path", "action", "sha256",
                     "base_sha256"}], "new_urls", "changed_urls", "index_first", "topic"}
    files/<path>    each changed file, whole

`check` is the hub host's gate (seo.py) and the session's own self-check before it delivers. Only
the site's content and the SEO automation's own state may change: a new lesson, edits to lessons,
fixed pages, exchange texts and the glossary, and seo/auto/*. Never a deletion, never a slug or URL
change, never build.py, a template, CSS or JS, never a long-video slug (kit dotcoin-longform's
topics.md: its lesson is made with its video), never a /go/ link inside a lesson.

    seo_pack.py make  SITE_REPO BASE OUT.zip --day YYYY-MM-DD [--topic «…»] [--index-first /learn/x/ …]
    seo_pack.py check PACKAGE.zip SITE_REPO        -> prints ok or each error; exit 1 on an error
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

SITE = "automations/sites/dotcoin"
# path -> what may happen to it ("add" a new file, "edit" an existing one)
RULES = [
    (re.compile(rf"^{SITE}/content/articles/[a-z0-9]+(?:-[a-z0-9]+){{0,7}}\.md$"), {"add", "edit"}),
    (re.compile(rf"^{SITE}/content/auto/[a-z0-9]+(?:-[a-z0-9]+){{0,11}}\.md$"), {"edit"}),
    (re.compile(rf"^{SITE}/content/pages/[a-z0-9-]+\.md$"), {"edit"}),
    (re.compile(rf"^{SITE}/content/exchanges/[a-z0-9-]+\.md$"), {"edit"}),
    (re.compile(rf"^{SITE}/content/glossary\.txt$"), {"edit"}),
    (re.compile(rf"^{SITE}/seo/auto/[A-Za-z0-9_-]+\.(md|json|jsonl)$"), {"add", "edit"}),
]
MAX_FILES, MAX_BYTES, MAX_TOTAL = 40, 400_000, 4_000_000
MAX_NEW_LESSONS = 3
URL_RE = re.compile(r"^/[a-z0-9/_-]*$")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=60)


def at_base(repo: Path, base: str, path: str) -> bytes | None:
    r = git(repo, "show", f"{base}:{path}")
    return r.stdout if r.returncode == 0 else None


def rule_of(path: str) -> set[str] | None:
    return next((acts for rx, acts in RULES if rx.fullmatch(path)), None)


TOPICS = "automations/kits/dotcoin-longform/topics.md"


def reserved(repo: Path, text: str | None = None) -> dict[str, str]:
    """The long-video lessons' slugs (kit dotcoin-longform's topics.md: the copy in `repo`, or the
    text given, the workshop's own): slug -> its keyword."""
    p = repo / TOPICS
    if text is None and p.is_file():
        text = p.read_text("utf-8")
    out: dict[str, str] = {}
    if text:
        for line in text.splitlines():
            m = re.match(r"^\|\s*\d+\s*\|[^|]*\|\s*`([a-z0-9-]+)`\s*\|\s*([^|]*)\|", line)
            if m:
                out[m.group(1)] = m.group(2).strip()
    return out


def sync_module(repo: Path):
    """The site sync's own article validator (sync.py), the one rule for every lesson."""
    sys.path.insert(0, str(repo / SITE))
    import sync  # noqa: E402

    return sync


def repo_lessons(repo: Path, sync) -> dict[str, dict]:
    """slug -> front matter of every lesson in this copy of the site (by hand and the hub's)."""
    out: dict[str, dict] = {}
    for d in ("articles", "auto"):
        for p in sorted((repo / SITE / "content" / d).glob("*.md")):
            try:
                out[p.stem] = sync.parse(p.read_text("utf-8"))[0]
            except (ValueError, OSError):
                continue
    return out


def url_of(path: str) -> str | None:
    m = re.match(rf"^{SITE}/content/(?:articles|auto)/([a-z0-9-]+)\.md$", path)
    if m:
        return f"/learn/{m.group(1)}/"
    m = re.match(rf"^{SITE}/content/pages/([a-z0-9-]+)\.md$", path)
    if m:
        page = m.group(1)
        return {"home": "/", "404": None}.get(page, f"/{page}/")
    m = re.match(rf"^{SITE}/content/exchanges/([a-z0-9-]+)\.md$", path)
    if m:
        return f"/exchanges/{m.group(1)}/"
    if path.endswith("content/glossary.txt"):
        return "/glossary/"
    return None


def check_files(repo: Path, base: str, files: dict[str, bytes], actions: dict[str, str],
                topics_text: str | None = None) -> list[str]:
    """Every rule on the changed files against the repo at `base` (the session's copy, or the hub's
    worktree, which holds the same history)."""
    errs: list[str] = []
    if not files:
        return ["the package changes nothing"]
    if len(files) > MAX_FILES:
        errs.append(f"{len(files)} files: at most {MAX_FILES}")
    if sum(len(b) for b in files.values()) > MAX_TOTAL:
        errs.append("the package is too big")
    sync = sync_module(repo)
    stems: dict[str, list[str]] = {}  # slug -> the lesson files that carry it now
    for d in ("articles", "auto"):
        for p in (repo / SITE / "content" / d).glob("*.md"):
            stems.setdefault(p.stem, []).append(str(p.relative_to(repo)))
    long_slugs = reserved(repo, topics_text)
    if not long_slugs:
        errs.append("the long videos' topics.md was not found (its slugs are reserved)")
    new_lessons = 0
    for path, data in files.items():
        act = actions.get(path, "")
        allowed = rule_of(path)
        if allowed is None:
            errs.append(f"{path}: not a file the SEO day may change")
            continue
        if act not in allowed:
            errs.append(f"{path}: may not be {act or 'touched'}ed")
            continue
        old = at_base(repo, base, path)
        if act == "add" and old is not None:
            errs.append(f"{path}: exists already (an edit, not a new file)")
        if act == "edit" and old is None:
            errs.append(f"{path}: not in the site at {base[:10]}")
        if len(data) > MAX_BYTES:
            errs.append(f"{path}: over {MAX_BYTES} bytes")
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            errs.append(f"{path}: not UTF-8")
            continue
        low = text.lower()
        if "<script" in low or "<iframe" in low or "javascript:" in low or "<style" in low:
            errs.append(f"{path}: raw HTML or script")
        if path.endswith((".json",)):
            try:
                json.loads(text)
            except ValueError:
                errs.append(f"{path}: not valid JSON")
            continue
        if path.endswith(".jsonl"):
            for n, line in enumerate(text.splitlines(), 1):
                if line.strip():
                    try:
                        json.loads(line)
                    except ValueError:
                        errs.append(f"{path}:{n}: not a JSON line")
                        break
            continue
        if "/content/articles/" in path or "/content/auto/" in path:
            slug = Path(path).stem
            # every other lesson's slug; this one's too when another file carries it
            others = {x for x in stems if x != slug} | ({slug} if any(f != path for f in stems.get(slug, [])) else set())
            meta, e, _ = sync.validate(text, others)
            errs += [f"{path}: {x}" for x in e]
            if meta.get("slug") != slug:
                errs.append(f"{path}: its slug must be its file name ({slug})")
            if act == "edit" and old is not None:
                try:
                    was = sync.parse(old.decode("utf-8"))[0]
                except ValueError:
                    was = {}
                if was.get("slug") and was.get("slug") != meta.get("slug"):
                    errs.append(f"{path}: a lesson's slug never changes")
                for k in ("youtube", "reel", "idea", "date"):
                    if was.get(k) and was.get(k) != meta.get(k):
                        errs.append(f"{path}: `{k}` is set by the hub, never by the SEO day")
            if act == "add":
                new_lessons += 1
                if slug in long_slugs:
                    errs.append(f"{path}: `{slug}` is a long video's lesson (topics.md); pick another cluster")
                kw = sync.norm(meta.get("keyword") or "")
                if kw and any(kw == sync.norm(k) for k in long_slugs.values()):
                    errs.append(f"{path}: its keyword is a long video's topic (topics.md)")
                for s, m in repo_lessons(repo, sync).items():
                    if s != slug and sync.topics(meta) & sync.topics(m, aliases=True):
                        errs.append(f"{path}: the same topic as /learn/{s}/ (never a second article)")
                        break
        elif text.startswith("---"):
            try:
                sync.parse(text)
            except ValueError as e:
                errs.append(f"{path}: {e}")
        if re.search(r"\]\((?:https://dotcoin\.me)?/go/", text) and "/content/pages/" not in path:
            errs.append(f"{path}: a /go/ link (sponsored links live in the templates)")
    if new_lessons > MAX_NEW_LESSONS:
        errs.append(f"{new_lessons} new lessons in one day: at most {MAX_NEW_LESSONS}")
    return errs


def read_package(zpath: Path) -> tuple[dict, dict[str, bytes], list[str]]:
    errs: list[str] = []
    try:
        z = zipfile.ZipFile(zpath)
    except (zipfile.BadZipFile, OSError) as e:
        return {}, {}, [f"not a zip: {e}"]
    with z:
        names = z.namelist()
        if "manifest.json" not in names:
            return {}, {}, ["no manifest.json"]
        if sum(i.file_size for i in z.infolist()) > MAX_TOTAL + 200_000:
            return {}, {}, ["the package unpacks too big"]
        try:
            man = json.loads(z.read("manifest.json"))
        except ValueError:
            return {}, {}, ["manifest.json is not JSON"]
        files: dict[str, bytes] = {}
        for f in man.get("files") or []:
            path = str(f.get("path") or "")
            if ".." in path.split("/") or path.startswith("/"):
                errs.append(f"bad path {path[:60]}")
                continue
            name = f"files/{path}"
            if name not in names:
                errs.append(f"{path}: listed, not in the zip")
                continue
            data = z.read(name)
            if sha(data) != f.get("sha256"):
                errs.append(f"{path}: sha256 differs from the manifest")
            files[path] = data
        extra = [n for n in names if n != "manifest.json" and n[6:] not in files]
        if extra:
            errs.append(f"files not in the manifest: {extra[:3]}")
    for k in ("new_urls", "changed_urls", "index_first"):
        for u in man.get(k) or []:
            if not URL_RE.fullmatch(str(u)):
                errs.append(f"{k}: bad url {str(u)[:60]}")
    if not re.fullmatch(r"[0-9a-f]{7,40}", str(man.get("base") or "")):
        errs.append("manifest: no base commit")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(man.get("day") or "")):
        errs.append("manifest: no day")
    return man, files, errs


def check(zpath: Path, repo: Path, topics_text: str | None = None) -> tuple[dict, dict[str, bytes], list[str]]:
    man, files, errs = read_package(zpath)
    if errs:
        return man, files, errs
    actions = {str(f["path"]): str(f.get("action") or "") for f in man["files"]}
    if git(repo, "cat-file", "-e", f"{man['base']}^{{commit}}").returncode:
        return man, files, [f"base {man['base'][:10]} is not in this repository"]
    for f in man["files"]:  # the hub's own copy at base is what the session started from
        if f.get("action") == "edit":
            old = at_base(repo, man["base"], str(f["path"]))
            if old is None or sha(old) != f.get("base_sha256"):
                errs.append(f"{f['path']}: the session's starting copy is not the one at base")
    if errs:
        return man, files, errs
    return man, files, check_files(repo, man["base"], files, actions, topics_text)


def make(repo: Path, base: str, out: Path, day: str, topic: str = "", index_first: list[str] | None = None,
         hub_base: str = "") -> int:
    """The session's changes since `base` (a ref of the session's own copy, committed or not) ->
    package.zip, checked first. `hub_base`: the hub's commit the copy was taken from (the pack's
    BASE), written in the manifest."""
    git(repo, "add", "-A")
    r = git(repo, "diff", "--cached", "--name-status", "--no-renames", base)
    files: dict[str, bytes] = {}
    actions: dict[str, str] = {}
    bad: list[str] = []
    for line in r.stdout.decode().splitlines():
        st, _, path = line.partition("\t")
        if st == "D":
            bad.append(f"{path}: deleted (the SEO day never deletes)")
            continue
        files[path] = (repo / path).read_bytes()
        actions[path] = "add" if st == "A" else "edit"
    errs = bad + check_files(repo, base, files, actions)
    if errs:
        for e in errs:
            print(f"error: {e}")
        print("NOT OK: nothing packed")
        return 1
    urls = {p: url_of(p) for p in files}
    man = {
        "version": 1, "day": day, "base": hub_base or base, "topic": topic,
        "files": [{"path": p, "action": actions[p], "sha256": sha(b),
                   "base_sha256": sha(at_base(repo, base, p) or b"") if actions[p] == "edit" else None}
                  for p, b in sorted(files.items())],
        "new_urls": sorted({u for p, u in urls.items() if u and actions[p] == "add"}),
        "changed_urls": sorted({u for p, u in urls.items() if u and actions[p] == "edit"}),
        "index_first": [u for u in (index_first or []) if URL_RE.fullmatch(u)][:10],
    }  # fmt: skip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(man, ensure_ascii=False, indent=1))
        for p, b in sorted(files.items()):
            z.writestr(f"files/{p}", b)
    out.write_bytes(buf.getvalue())
    print(f"ok: {len(files)} files, new {man['new_urls']}, changed {len(man['changed_urls'])} -> {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("repo")
    m.add_argument("base")
    m.add_argument("out")
    m.add_argument("--day", required=True)
    m.add_argument("--topic", default="")
    m.add_argument("--index-first", nargs="*", default=[])
    m.add_argument("--hub-base", default="", help="the pack's BASE (the hub's commit of site.tar)")
    c = sub.add_parser("check")
    c.add_argument("package")
    c.add_argument("repo")
    a = ap.parse_args()
    if a.cmd == "make":
        return make(Path(a.repo).resolve(), a.base, Path(a.out).resolve(), a.day, a.topic, a.index_first, a.hub_base)
    man, files, errs = check(Path(a.package).resolve(), Path(a.repo).resolve())
    for e in errs:
        print(f"error: {e}")
    print("ok" if not errs else "NOT OK")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
