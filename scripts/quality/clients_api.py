#!/usr/bin/env python3
"""The owner's two apps against the hub's OpenAPI (handoff 2026-11-05, bug 1).

The Android app asked `GET /work/{id}/tree-events?limit=500` while the hub takes at most 200: a 422 the owner saw as a
work page without its tree. This gate reads every call the apps make, as written in their sources, and fails when:

- the path (with its method) is not in `apps/api/openapi/hq-api.v1.json` (a 404/405 waiting to happen), or
- a literal `limit` (a call's own, or a Kotlin function's default) is above the route's `maximum`, or above the
  hub-wide page ceiling of 200 where the route declares none.

No dependency beyond the standard library; it runs in `make check` and on every push.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "apps/api/openapi/hq-api.v1.json"
ANDROID = ROOT / "apps/android/app/src/main/java"
WEB = ROOT / "apps/web/src"
PAGE_CEILING = 200  # apps/api/src/hq_api/pagination.py MAX_LIMIT

KT_CALL = re.compile(r'\b(get|post|listAny|postUnit|put|patch|delete|del)[A-Za-z]*\("(/[^"]*)"')
KT_DEFAULT = re.compile(
    r'fun (?:Api\.)?(\w+)\(([^)]*?\blimit: Int = (\d+)[^)]*)\)[^={]*=\s*(?:get|listAny)\("(/[^"]*)"'
)
KT_VERB = {"get": "GET", "listAny": "GET", "post": "POST", "postUnit": "POST", "put": "PUT", "patch": "PATCH",
           "delete": "DELETE", "del": "DELETE"}


def norm(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


def load_spec() -> dict[tuple[str, str], int | None]:
    doc = json.loads(SPEC.read_text())
    out: dict[tuple[str, str], int | None] = {}
    for path, ops in doc["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        for method, op in ops.items():
            limit_max = None
            for p in op.get("parameters", []):
                if p.get("name") == "limit":
                    limit_max = p.get("schema", {}).get("maximum", PAGE_CEILING)
            out[(method.upper(), norm(path[len("/api/v1"):]))] = limit_max
    return out


def kt_path(raw: str) -> str:
    return re.sub(r"\$\{[^}]*\}|\$[A-Za-z_]+", "{}", raw).split("?")[0]


def check_android(spec, errors: list[str]) -> int:
    n = 0
    for f in sorted(ANDROID.rglob("*.kt")):
        s = f.read_text()
        rel = f.relative_to(ROOT)
        if f.parent.name == "net":
            for m in KT_CALL.finditer(s):
                n += 1
                verb, path = KT_VERB[m.group(1)], kt_path(m.group(2))
                if (verb, path) not in spec:
                    errors.append(f"{rel}: {verb} {m.group(2)} is not in the hub's OpenAPI")
                line = s[m.end(): s.find("\n", m.end())]
                cap = spec.get(("GET", path))
                for lim in re.findall(r'"limit" to (\d+)', line):
                    if cap is not None and int(lim) > cap:
                        errors.append(f"{rel}: GET {m.group(2)} sends limit={lim}, the hub takes at most {cap}")
        for m in KT_DEFAULT.finditer(s):
            cap = spec.get(("GET", kt_path(m.group(4))))
            if cap is not None and int(m.group(3)) > cap:
                errors.append(f"{rel}: {m.group(1)}() defaults to limit={m.group(3)}, the hub takes at most {cap}")
        for m in re.finditer(r"\blimit = (\d+)\b", s):
            if int(m.group(1)) > PAGE_CEILING:
                errors.append(f"{rel}: passes limit = {m.group(1)}, above the hub's page ceiling {PAGE_CEILING}")
    return n


def _template_end(s: str, k: int) -> int:
    depth, e = 0, k + 1
    while e < len(s):
        if s.startswith("${", e):
            depth += 1
            e += 2
            continue
        if s[e] == "}" and depth:
            depth -= 1
        elif s[e] == "`" and not depth:
            return e
        e += 1
    return e


def web_path(raw: str) -> tuple[str, str]:
    """(the path with `{}` for each interpolated segment, the query text) of a template literal."""
    out, query, i = "", "", 0
    while i < len(raw):
        if raw.startswith("${", i):
            depth, j = 0, i + 1
            while j < len(raw):
                if raw[j] == "{":
                    depth += 1
                elif raw[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            inner = raw[i + 2: j]
            if inner.startswith("qs(") or ("?" in inner and "'" in inner):
                query += inner
            else:
                out += "{}"
            i = j + 1
        else:
            out += raw[i]
            i += 1
    path, _, rest = out.partition("?")
    return path, query + rest


def check_web(spec, errors: list[str]) -> int:
    n = 0
    for f in sorted(WEB.rglob("*.ts*")):
        if "mock" in f.name or ".test." in f.name:
            continue
        s, rel = f.read_text(), f.relative_to(ROOT)
        for m in re.finditer(r"\bcall<", s):
            k, depth = m.end(), 1
            while depth and k < len(s):
                depth += {"<": 1, ">": -1}.get(s[k], 0)
                k += 1
            mm = re.match(r"\(\s*'([A-Z]+)',\s*", s[k:])
            if not mm:
                continue
            k += mm.end()
            if k >= len(s) or s[k] not in "`'":
                continue
            e = s.index("'", k + 1) if s[k] == "'" else _template_end(s, k)
            path, query = web_path(s[k + 1: e])
            if path.startswith("{}"):  # a base passed in (`${path}/…`): its caller's literal is checked instead
                continue
            n += 1
            verb = mm.group(1)
            if (verb, path) not in spec:
                errors.append(f"{rel}: {verb} {path} is not in the hub's OpenAPI")
            cap = spec.get((verb, path))
            for lim in re.findall(r"limit:\s*(?:[^,}]*\?\s*)?(\d+)", query) + re.findall(r"limit=(\d+)", query):
                if cap is not None and int(lim) > cap:
                    errors.append(f"{rel}: {verb} {path} sends limit={lim}, the hub takes at most {cap}")
    return n


def main() -> int:
    spec = load_spec()
    errors: list[str] = []
    a = check_android(spec, errors)
    w = check_web(spec, errors)
    for e in errors:
        print(f"FAIL {e}")
    print(f"clients-api: {a} Android calls, {w} web calls checked against {len(spec)} operations")
    if a < 100 or w < 100:  # the parser stopped seeing the calls: fail rather than pass on nothing
        print("FAIL clients-api: too few calls found; the call patterns changed, update scripts/quality/clients_api.py")
        return 1
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
