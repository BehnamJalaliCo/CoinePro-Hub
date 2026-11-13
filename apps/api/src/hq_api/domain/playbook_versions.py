"""⟨1.37⟩ A playbook's versions, its flow, its package and its lessons (contract §59.1, §59.3;
the owner, 2026-11-13: «یه نسخه‌ای ازش بسازیم که بتونیم توی شرکت‌های دیگه ازش استفاده بکنیم»).

    body        one row of owner.playbook_versions per version: the header (title, purpose,
                platform), the seats, routines, KPIs, connections and rules of §40.2, and the
                flow of §59.2 (`steps`), what one run hands over (`package`) and what went wrong
                once (`lessons`). A sealed body is frozen; a change makes the next version as a
                draft while the sealed one keeps running.
    current     the body a reader gets without a version: the newest sealed (or retired) one,
                else the newest draft. owner.playbooks mirrors it (title, purpose, platform,
                definition, version, state), so every reader from before 1.37 keeps working.
    compare     code's own lines between two bodies (never a model); a seal's `changelog_fa`.
    export      `coinepro.playbook/1`: the body without any company, account, link, narrator or
                member; import makes a new draft of such a file, dropping what the hub cannot run.

Pure helpers and the version rows; the playbooks module (domain/playbooks.py) builds on them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, get_args
from uuid import UUID

from pydantic import ValidationError

from hq_api.db import Tx
from hq_api.domain import flow_shapes as FS
from hq_api.errors import ApiError
from hq_api.lines.base import KINDS
from hq_api.talk.scrub import clean

FORMAT = "coinepro.playbook/1"
STEP_KINDS: tuple[str, ...] = KINDS  # the line engine's kinds (§30.2, §59.2)
MAX_STEPS, MAX_PACKAGE, MAX_LESSONS, MAX_STEP_RULES = 30, 20, 60, 30
MAX_SETTINGS_CHARS = 4_000
MAX_CHANGELOG = 40
FLOW_KEYS = ("steps", "package", "lessons")
DEFINITION_KEYS = ("seats", "routines", "kpis", "connections", "rules_fa", *FLOW_KEYS)
HEADER_KEYS = ("title_fa", "purpose_fa", "platform")
BODY_KEYS = (*HEADER_KEYS, *DEFINITION_KEYS)
FLOW_HELPERS = frozenset(get_args(FS.Helper))
EFFORTS = frozenset(get_args(FS.Effort))
KEY = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
ORDER_KEY = "_order"
OWNER_FA = "مدیر کل"
SEALED_FA = "این نسخه مُهر شده؛ تغییر، نسخه‌ی تازه میسازد"
VERSION_NOT_FOUND_FA = "این نسخه پیدا نشد."
NOT_A_PLAYBOOK_FA = "این فایل، فایل کارگروه (coinepro.playbook/1) نیست."
# a step's settings never carry what belongs to one company (§59.1 export)
PRIVATE_SETTINGS = frozenset({
    "account", "accounts", "company", "companies", "narrator", "voice", "voice_name", "link",
    "links", "url", "urls", "site", "channel", "member", "members", "handle", "username", "page",
    "chat", "chat_url", "file", "files", "file_id",
})  # fmt: skip
URL = re.compile(r"https?://|www\.", re.IGNORECASE)


def _text(v: Any, limit: int) -> str:
    return clean(" ".join(str(v or "").split()))[0][:limit]


def _slug(raw: Any, fallback: str) -> str | None:
    word = " ".join(str(raw or "").split()).lower().replace("-", "_").replace(" ", "_")
    word = re.sub(r"[^a-z0-9_]", "", word)[:41]
    if KEY.match(word):
        return word
    return fallback if KEY.match(fallback) else None


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


# ------------------------------------------------------------- the flow, checked --
def _settings(raw: Any, title: str, notes: list[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    try:
        text = json.dumps(raw, ensure_ascii=False)
    except (TypeError, ValueError):
        text = ""
    if not text or len(text) > MAX_SETTINGS_CHARS:
        notes.append(f"تنظیمات قدم «{title[:40]}» خوانده نشد و خالی ماند.")
        return {}
    return dict(json.loads(text))


def normalise_flow(
    raw: dict[str, Any], seats: list[dict[str, Any]], notes: list[str]
) -> dict[str, Any]:
    """The steps, the package and the lessons from what a model, the owner or a file wrote: a step
    of a kind the line engine runs (§30.2, §59.2), on a kept seat, with a helper the hub has;
    anything else dropped (or emptied) with a plain note. Each lesson's rule joins its step's
    `rules_fa`. Never refuses."""
    seat_keys = {str(s["seat"]) for s in seats}
    seat_of_role = {str(s["role"]): str(s["seat"]) for s in seats}
    steps: list[dict[str, Any]] = []
    keys: set[str] = set()
    raw_inputs: dict[str, list[Any]] = {}
    for i, s in enumerate(raw.get("steps") or []):
        if not isinstance(s, dict):
            continue
        if len(steps) >= MAX_STEPS:
            notes.append(f"بیش از {MAX_STEPS} قدم آمد؛ بقیه حذف شد.")
            break
        title = _text(s.get("title_fa"), 200) or _text(s.get("key"), 60) or f"قدم {i + 1}"
        kind = str(s.get("kind") or "").strip().lower()
        if kind not in STEP_KINDS:
            notes.append(f"قدم «{title[:40]}» حذف شد: هاب این نوع کار را اجرا نمیکند.")
            continue
        key = _slug(s.get("key"), f"step_{i + 1}") or f"step_{len(steps) + 1}"
        if key in keys:
            key = f"{key[:36]}_{len(steps) + 1}"
        if key in keys:
            continue
        helper = s.get("helper")
        if helper is not None and helper not in FLOW_HELPERS:
            if str(helper).strip():
                notes.append(
                    f"ابزار «{str(helper)[:30]}» در هاب نیست و از قدم «{title[:40]}» برداشته شد."
                )
            helper = None
        effort = s.get("effort") if s.get("effort") in EFFORTS else None
        seat_raw = str(s.get("seat") or "").strip()
        seat = _slug(seat_raw, "") or ""
        if seat not in seat_keys:
            seat = seat_of_role.get(seat_raw.lower(), "")
            if not seat and seat_raw:
                notes.append(f"جایگاه قدم «{title[:40]}» در کارگروه نیست؛ خالی ماند.")
        try:
            attempts = max(1, min(int(s.get("max_attempts") or 1), 3))
        except (TypeError, ValueError):
            attempts = 1
        try:
            timeout = int(s["timeout_s"]) if s.get("timeout_s") is not None else None
            timeout = None if timeout is None else max(10, min(timeout, 4 * 3600))
        except (TypeError, ValueError):
            timeout = None
        rules = [_text(x, 300) for x in s.get("rules_fa") or [] if isinstance(x, str)]
        item = {
            "key": key,
            "title_fa": title,
            "seat": seat,
            "kind": kind,
            "helper": helper,
            "model": _text(s.get("model"), 80) or None,
            "effort": effort,
            "input_fa": _text(s.get("input_fa"), 500),
            "output_fa": _text(s.get("output_fa"), 500),
            "rules_fa": [x for x in rules if x][:MAX_STEP_RULES],
            "inputs": [],
            "gate": "ask" if s.get("gate") == "ask" else "auto",
            "optional": bool(s.get("optional")),
            "max_attempts": attempts,
            "timeout_s": timeout,
            "settings": _settings(s.get("settings"), title, notes),
        }
        try:
            step = FS.FlowStep.model_validate(item).model_dump(mode="json")
        except ValidationError:
            notes.append(f"قدم «{title[:40]}» حذف شد: شکلش درست نیست.")
            continue
        keys.add(key)
        raw_inputs[key] = list(s.get("inputs") or []) if isinstance(s.get("inputs"), list) else []
        steps.append(step)
    for st in steps:
        st["inputs"] = list(
            dict.fromkeys(
                str(x) for x in raw_inputs.get(st["key"], []) if str(x) in keys and x != st["key"]
            )
        )
    package: list[dict[str, Any]] = []
    names: set[str] = set()
    for p in raw.get("package") or []:
        if not isinstance(p, dict) or len(package) >= MAX_PACKAGE:
            continue
        name = _text(p.get("name"), 120)
        if not name or name in names:
            continue
        names.add(name)
        step_key = str(p.get("step") or "")
        package.append({"name": name, "title_fa": _text(p.get("title_fa"), 200),
                        "step": step_key if step_key in keys else None,
                        "required": p.get("required") is not False})  # fmt: skip
    lessons: list[dict[str, Any]] = []
    for les in raw.get("lessons") or []:
        if not isinstance(les, dict) or len(lessons) >= MAX_LESSONS:
            continue
        title = _text(les.get("title_fa"), 300)
        if not title:
            notes.append(f"درس {len(lessons) + 1} حذف شد: عنوان ندارد.")
            continue
        step_key = str(les.get("step") or "")
        lessons.append({"n": len(lessons) + 1, "title_fa": title,
                        "cause_fa": _text(les.get("cause_fa"), 1000),
                        "fix_fa": _text(les.get("fix_fa"), 1000),
                        "rule_fa": _text(les.get("rule_fa"), 300),
                        "step": step_key if step_key in keys else None})  # fmt: skip
    by_key = {str(x["key"]): x for x in steps}
    for les in lessons:
        owner = by_key.get(str(les["step"] or ""))
        rule = les["rule_fa"]
        if (
            owner is not None
            and rule
            and rule not in owner["rules_fa"]
            and len(owner["rules_fa"]) < MAX_STEP_RULES
        ):
            owner["rules_fa"].append(rule)
    return {"steps": steps, "package": package, "lessons": lessons}


# --------------------------------------------------- lessons from a fault log, by code --
_HEADING = re.compile(r"^#{3}\s*[0-9۰-۹]+\s*[.)\-]\s*(.+?)\s*$")
_LABEL = re.compile(r"^\s*[-*]?\s*\*\*(?P<label>[^*:]+):?\*\*:?\s*(?P<rest>.*)$")
_LABELS = {"علت": "cause_fa", "رفع": "fix_fa", "درس": "rule_fa"}


def lessons_from_log(md: str | None) -> list[dict[str, Any]]:
    """A session's fault log (`### N. title` with «**علت:**», «**رفع:**», «**درس:**», as the hub's
    `<ORDER>_WORKING_GROUP_LOG.md` writes it) as lessons, by code. Nothing guessed: an entry
    without a title is left out, a missing part stays empty."""
    out: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    field: str | None = None
    for line in (md or "").splitlines():
        head = _HEADING.match(line)
        if head is not None:
            cur = {"title_fa": head.group(1).strip(), "cause_fa": "", "fix_fa": "", "rule_fa": ""}
            out.append(cur)
            field = None
            continue
        if cur is None:
            continue
        if line.startswith("#"):
            cur, field = None, None
            continue
        label = _LABEL.match(line)
        if label is not None:
            field = _LABELS.get(label.group("label").strip())
            if field is not None and label.group("rest").strip():
                cur[field] = label.group("rest").strip()
            continue
        bullet = line.strip().lstrip("-*").strip()
        if field is not None and bullet and line.startswith((" ", "\t")):
            cur[field] = f"{cur[field]} {bullet}".strip() if cur[field] else bullet
    return [
        {k: (_text(v, 1000) if isinstance(v, str) else v) for k, v in les.items()}
        for les in out
        if les["title_fa"]
    ][:MAX_LESSONS]


# ---------------------------------------------------------------- bodies --
def definition_of(d: dict[str, Any]) -> dict[str, Any]:
    """owner.playbooks.definition: the parts of a body that are not the row's own columns."""
    return {k: d.get(k) or [] for k in DEFINITION_KEYS}


def body_of(
    d: dict[str, Any],
    *,
    note_fa: str | None = None,
    summary_fa: str | None = None,
    order: str | None = None,
) -> dict[str, Any]:
    """A version's stored body from a normalised shape, with the drafter's note and summary
    and the session it was drafted in (`order`), if any."""
    out: dict[str, Any] = {k: d.get(k) for k in HEADER_KEYS}
    out.update(definition_of(d))
    out["note_fa"] = (note_fa or "")[:2000] or None
    if summary_fa:
        out["summary_fa"] = _text(summary_fa, 300)
    if order:
        out["order"] = order
    return out


def shape_of(body: dict[str, Any]) -> dict[str, Any]:
    """A body without its version's own words (the note, the summary): what a copy starts from."""
    return {k: body.get(k) for k in BODY_KEYS}


@dataclass
class Version:
    id: UUID
    version: int
    state: str
    body: dict[str, Any]
    changelog_fa: list[str]
    by_fa: str
    at: datetime
    sealed_at: datetime | None


VERSION_SQL = """SELECT id, version, state, body, changelog_fa, by_fa, at, sealed_at
                 FROM owner.playbook_versions WHERE playbook_id = :p"""


def _version(r: Any) -> Version:
    return Version(
        id=r["id"],
        version=int(r["version"]),
        state=str(r["state"]),
        body=dict(_j(r["body"]) or {}),
        changelog_fa=list(r["changelog_fa"] or []),
        by_fa=str(r["by_fa"] or ""),
        at=r["at"],
        sealed_at=r["sealed_at"],
    )


async def versions(tx: Tx, playbook_id: UUID, *, lock: bool = False) -> list[Version]:
    """Every body of a playbook, newest first."""
    sql = VERSION_SQL + " ORDER BY version DESC" + (" FOR UPDATE" if lock else "")
    return [_version(r) for r in await tx.all(sql, p=playbook_id)]


def current(vs: list[Version]) -> Version | None:
    """The body a reader gets without a version: the newest sealed (or retired), else the newest
    draft."""
    return next((v for v in vs if v.state != "draft"), vs[0] if vs else None)


def newest_draft(vs: list[Version]) -> Version | None:
    return vs[0] if vs and vs[0].state == "draft" else None


def at_version(vs: list[Version], version: int | None) -> Version | None:
    if version is None:
        return current(vs)
    v = next((x for x in vs if x.version == version), None)
    if v is None:
        raise ApiError(404, "not_found", "unknown version", message_fa=VERSION_NOT_FOUND_FA)
    return v


async def insert_version(
    tx: Tx,
    row: dict[str, Any],
    version: int,
    body: dict[str, Any],
    *,
    by_kind: str = "owner",
    by_fa: str = OWNER_FA,
) -> None:
    await tx.exec(
        """INSERT INTO owner.playbook_versions (company_id, playbook_id, version, state, body,
               by_kind, by_fa)
           VALUES (:co, :p, :v, 'draft', CAST(:b AS jsonb), :bk, :bf)""",
        co=row["company_id"],
        p=row["id"],
        v=version,
        b=json.dumps(body, ensure_ascii=False),
        bk=by_kind,
        bf=by_fa[:200],
    )


async def write_draft(
    tx: Tx, v: Version, body: dict[str, Any], *, by_kind: str = "owner", by_fa: str = OWNER_FA
) -> None:
    """A draft's body replaced (never a sealed one's: the callers check)."""
    await tx.exec(
        """UPDATE owner.playbook_versions SET body = CAST(:b AS jsonb), by_kind = :bk, by_fa = :bf,
               at = now() WHERE id = :id AND state = 'draft'""",
        id=v.id,
        b=json.dumps(body, ensure_ascii=False),
        bk=by_kind,
        bf=by_fa[:200],
    )


async def mirror(tx: Tx, playbook_id: UUID) -> dict[str, Any]:
    """owner.playbooks follows its current body (title, purpose, platform, definition, version,
    the draft note) and its state (`sealed` once a version is; `retired` stays)."""
    vs = await versions(tx, playbook_id)
    cur = current(vs)
    if cur is None:
        return dict(await tx.one("SELECT * FROM owner.playbooks WHERE id = :id", id=playbook_id))
    b = cur.body
    row = await tx.one(
        """UPDATE owner.playbooks SET title_fa = :t, purpose_fa = :p, platform = :pl,
               definition = CAST(:d AS jsonb), version = :v,
               state = CASE WHEN state = 'retired' THEN 'retired' ELSE :st END,
               note_fa = CASE WHEN :has_note THEN :note ELSE note_fa END, updated_at = now()
           WHERE id = :id RETURNING *""",
        id=playbook_id,
        t=str(b.get("title_fa") or "")[:200] or "کارگروه",
        p=str(b.get("purpose_fa") or "")[:2000],
        pl=str(b.get("platform") or "any"),
        d=json.dumps(definition_of(b), ensure_ascii=False),
        v=cur.version,
        st="draft" if cur.state == "draft" else "sealed",
        has_note="note_fa" in b,
        note=(str(b.get("note_fa") or "")[:2000] or None),
    )
    return dict(row)


# ------------------------------------------------------------------ compare --
PART_FA = {
    "title": "نام", "purpose": "هدف", "platform": "پلتفرم", "seat": "صندلی", "step": "قدم",
    "rule": "قاعده", "lesson": "درس", "package": "فایل بسته", "kpi": "شاخص", "routine": "روال",
    "connection": "اتصال",
}  # fmt: skip


def _change(
    part: str, key: str, kind: str, before: str | None, after: str | None
) -> FS.PlaybookChange:
    return FS.PlaybookChange.model_validate(
        {"part": part, "key": key[:120], "kind": kind, "before_fa": before, "after_fa": after}
    )


def _keyed(
    out: list[FS.PlaybookChange],
    part: str,
    a: list[dict[str, Any]],
    b: list[dict[str, Any]],
    key: str,
    name: str,
) -> None:
    before = {str(x.get(key)): x for x in a if isinstance(x, dict)}
    after = {str(x.get(key)): x for x in b if isinstance(x, dict)}
    for k, x in after.items():
        if k not in before:
            out.append(_change(part, k, "added", None, str(x.get(name) or k)))
        elif before[k] != x:
            out.append(
                _change(part, k, "changed", str(before[k].get(name) or k), str(x.get(name) or k))
            )
    for k, x in before.items():
        if k not in after:
            out.append(_change(part, k, "removed", str(x.get(name) or k), None))


def _texts(out: list[FS.PlaybookChange], part: str, a: list[Any], b: list[Any]) -> None:
    sa, sb = [str(x) for x in a or []], [str(x) for x in b or []]
    out += [_change(part, x, "added", None, x) for x in sb if x not in sa]
    out += [_change(part, x, "removed", x, None) for x in sa if x not in sb]


def compare(a: dict[str, Any], b: dict[str, Any]) -> list[FS.PlaybookChange]:
    """What differs from body `a` to body `b`, by code: the header, then each keyed part (added,
    changed, removed) and the steps' order."""
    from hq_api.domain.playbooks import PLATFORM_FA

    out: list[FS.PlaybookChange] = []
    for part, k in (("title", "title_fa"), ("purpose", "purpose_fa")):
        x, y = str(a.get(k) or ""), str(b.get(k) or "")
        if x != y:
            out.append(_change(part, k, "changed", x or None, y or None))
    pa, pb = str(a.get("platform") or "any"), str(b.get("platform") or "any")
    if pa != pb:
        out.append(
            _change(
                "platform", "platform", "changed", PLATFORM_FA.get(pa, pa), PLATFORM_FA.get(pb, pb)
            )
        )
    _keyed(out, "seat", a.get("seats") or [], b.get("seats") or [], "seat", "title_fa")
    _keyed(out, "step", a.get("steps") or [], b.get("steps") or [], "key", "title_fa")
    sa = [str(s.get("key")) for s in a.get("steps") or [] if isinstance(s, dict)]
    sb = [str(s.get("key")) for s in b.get("steps") or [] if isinstance(s, dict)]
    common_a, common_b = [k for k in sa if k in sb], [k for k in sb if k in sa]
    if common_a != common_b:
        titles = {str(s.get("key")): str(s.get("title_fa") or s.get("key"))
                  for s in [*(a.get("steps") or []), *(b.get("steps") or [])] if isinstance(s, dict)}  # fmt: skip
        out.append(_change("step", ORDER_KEY, "changed", " › ".join(titles[k] for k in common_a),
                           " › ".join(titles[k] for k in common_b)))  # fmt: skip
    _keyed(out, "routine", a.get("routines") or [], b.get("routines") or [], "key", "title_fa")
    _keyed(out, "kpi", a.get("kpis") or [], b.get("kpis") or [], "key", "title_fa")
    _keyed(out, "package", a.get("package") or [], b.get("package") or [], "name", "name")
    _keyed(out, "lesson", a.get("lessons") or [], b.get("lessons") or [], "title_fa", "title_fa")
    _texts(out, "rule", a.get("rules_fa") or [], b.get("rules_fa") or [])
    _texts(out, "connection", a.get("connections") or [], b.get("connections") or [])
    return out


def line_fa(c: FS.PlaybookChange) -> str:
    """One change as the owner reads it (the app's own words for the same lines)."""
    what = PART_FA.get(c.part, "بخش")
    if c.part == "step" and c.key == ORDER_KEY:
        return "ترتیب قدم‌ها عوض شد"
    name = (c.after_fa or c.before_fa or "").strip()[:80]
    named = f" «{name}»" if name else ""
    if c.kind == "added":
        return f"{what}{named} اضافه شد"
    if c.kind == "removed":
        return f"{what}{named} برداشته شد"
    if (
        c.before_fa is not None
        and c.after_fa is not None
        and c.part in ("title", "purpose", "platform")
    ):
        return f"{what}: «{c.before_fa[:60]}» ← «{c.after_fa[:60]}»"
    return f"{what}{named} عوض شد"


def changelog(prev: dict[str, Any] | None, body: dict[str, Any]) -> list[str]:
    """A sealed version's `changelog_fa`: code's lines against the version before it, then the
    drafter's own summary line when it gave one."""
    lines = [line_fa(c) for c in compare(prev, body)] if prev is not None else []
    if len(lines) > MAX_CHANGELOG:
        lines = [*lines[: MAX_CHANGELOG - 1], f"و {len(lines) - MAX_CHANGELOG + 1} تغییر دیگر"]
    summary = _text(body.get("summary_fa"), 300)
    return [*lines, summary] if summary else lines


# ------------------------------------------------------------- export / import --
def _private(settings: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in settings.items():
        if k.lower() in PRIVATE_SETTINGS or (isinstance(v, str) and URL.search(v)):
            continue
        out[k] = _private(v) if isinstance(v, dict) else v
    return out


def export_doc(body: dict[str, Any], version: int) -> dict[str, Any]:
    """`coinepro.playbook/1`: the body without a company, an account, a link, a narrator or a
    member (a step's settings lose every such key and every web address)."""
    steps = [{**s, "settings": _private(dict(s.get("settings") or {}))}
             for s in body.get("steps") or [] if isinstance(s, dict)]  # fmt: skip
    return {
        "format": FORMAT,
        "version": version,
        "exported_at": datetime.now(UTC).isoformat(),
        "playbook": {
            "title_fa": body.get("title_fa") or "",
            "purpose_fa": body.get("purpose_fa") or "",
            "platform": body.get("platform") or "any",
            "seats": body.get("seats") or [],
            "steps": steps,
            "package": body.get("package") or [],
            "routines": body.get("routines") or [],
            "kpis": body.get("kpis") or [],
            "connections": body.get("connections") or [],
            "rules_fa": body.get("rules_fa") or [],
            "lessons": body.get("lessons") or [],
        },
    }


def export_name(title: str, version: int) -> str:
    """`<title>-v<n>.playbook.json`: the title as a file name (no path or control characters)."""
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", title)
    name = "-".join(name.split())[:80] or "playbook"
    return f"{name}-v{version}.playbook.json"


def read_doc(raw: Any) -> dict[str, Any]:
    """A playbook file's JSON (bytes or already parsed): 422 for anything not
    `coinepro.playbook/1` with a `playbook` object."""
    doc = raw
    if isinstance(raw, bytes | str):
        try:
            doc = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            doc = None
    if (
        not isinstance(doc, dict)
        or doc.get("format") != FORMAT
        or not isinstance(doc.get("playbook"), dict)
    ):
        raise ApiError(422, "validation_failed", fields={"file": f"not a {FORMAT} file"},
                       message_fa=NOT_A_PLAYBOOK_FA)  # fmt: skip
    return doc
