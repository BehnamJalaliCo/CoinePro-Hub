"""Examples for every operation of the OpenAPI document (prompt 04 §3).

Hand-written examples for the main request bodies; every other request body
and success response gets a deterministic example generated from its schema
(field-name hints and the contract's code patterns), so the generated web
and Android clients and their tests have realistic payloads everywhere.
"""

from __future__ import annotations

import copy
from typing import Any

UUID = "0195f1d2-7a3b-7c4d-8e5f-6a7b8c9d0e1f"
WHEN = "2026-10-17T05:42:00Z"

CURATED: dict[str, dict[str, Any]] = {
    "create_work": {
        "company": "TY",
        "department": "GROWTH",
        "title": "کمپین معرفی نسخه‌ی جدید",
        "brief": "هدف: ۲۰٪ ثبت‌نام بیشتر تا پایان ماه.",
        "kind": "one_off",
        "priority": "P2",
        "due_at": "2026-10-19T12:00:00Z",
        "budget": {"tokens": 200000, "usd": "4.000000"},
    },
    "create_company": {
        "code": "NV",
        "name_fa": "نوا",
        "name_en": "Nova",
        "color_index": 5,
        "template": "standard",
    },
    "propose_decision": {
        "kind": "hire",
        "title": "استخدام کارشناس سئو",
        "what": "یک کارشناس سئو برای دپارتمان رشد.",
        "why": "ترافیک ارگانیک سه ماه است ثابت مانده.",
        "risk": "low",
        "reversible": True,
        "quota_estimate": {"tokens": 2000000, "usd": "40.000000"},
        "payload": {
            "company": "TY",
            "department": "GROWTH",
            "title_fa": "کارشناس سئو",
            "title_en": "SEO Specialist",
            "reason": "رشد ارگانیک",
            "duties": ["پایش کلیدواژه‌ها", "پیشنهاد محتوا"],
            "model": "claude-sonnet-5-5",
            "effort": "high",
            "permissions": ["A0", "A1"],
            "quota_estimate_month": {"tokens": 2000000, "usd": "40.000000"},
        },
    },
    "approve_decision": {"note": "موافقم؛ از هفته‌ی بعد شروع شود."},
    "reject_decision": {"reason_code": "cost", "reason": "هزینه با بودجه‌ی این فصل نمیخواند."},
    "return_decision": {"note": "عدد برآورد مصرف را با منبع بیاور."},
    "send_message": {"body": "گزارش این هفته را تا فردا بفرست.", "links": {"work": "W-000789"}},
    "agent_message": {
        "body": "گزارش آماده است؛ خروجی O-000456 را ببینید.",
        "links": {"work": "W-000789"},
    },
    "rate_deliverable": {"score": 8, "comment": "خوب بود؛ منبع عددها را هم بنویس."},
    "set_kill_switch": {
        "scope": "company:TY",
        "state": "engaged",
        "reason": "رفتار غیرعادی در انتشار محتوا",
    },
    "agent_kill_switch": {"scope": "company:TY", "state": "engaged", "reason": "حادثه‌ی SEV1"},
    "delegate_work": {"to": "TY-GROWTH-MGR", "title": "اجرای کمپین", "budget": {"tokens": 100000}},
    "deliver_work": {
        "title": "پیش‌نویس کمپین",
        "summary": "سه پیام کلیدی و تقویم انتشار.",
        "body": "## پیام‌ها\n...",
        "produced_with": {
            "connection": "claude-max",
            "provider": "anthropic",
            "model": "claude-sonnet-5-5",
            "effort": "high",
        },
        "usage": {
            "input_tokens": 12000,
            "output_tokens": 1800,
            "cache_read_tokens": 30000,
            "cache_write_tokens": 4000,
            "equiv_cost_usd": "0.058000",
        },
        "evidence": [{"kind": "link", "ref": "https://example.org/draft", "note": "پیش‌نویس"}],
    },
    "request_work": {
        "department": "TECH",
        "title": "صفحه‌ی فرود کمپین",
        "brief": "یک صفحه‌ی فرود ساده.",
        "priority": "P3",
        "requested_by_work_id": UUID,
    },
    "set_activity": {
        "employee": "TY-GROWTH-01",
        "activity": "working",
        "note": "در حال نوشتن پیش‌نویس",
    },
    "raise_notification": {
        "level": "urgent",
        "title_fa": "خطای پرداخت در TradeYar",
        "body_fa": "۵٪ تراکنش‌ها رد میشوند.",
        "link_kind": "work",
        "link_ref": "W-000790",
    },
}

HINTS: dict[str, Any] = {
    "code": "TY",
    "company": "TY",
    "department": "GROWTH",
    "employee": "TY-GROWTH-01",
    "assignee": "TY-GROWTH-01",
    "producer": "TY-GROWTH-01",
    "actor": "TY-GROWTH-01",
    "to": "TY-GROWTH-MGR",
    "ref": "W-000789",
    "thread": "TY-CEO",
    "title": "گزارش هفتگی رشد",
    "title_fa": "گزارش هفتگی رشد",
    "title_en": "Weekly growth report",
    "name_fa": "تریدیار",
    "name_en": "TradeYar",
    "display_name": "آرش",
    "body": "متن پیام",
    "body_fa": "توضیح کوتاه",
    "summary": "خلاصه",
    "note": "یادداشت",
    "reason": "دلیل",
    "message_fa": "پیدا نشد.",
    "model": "claude-sonnet-5-5",
    "connection": "claude-max",
    "provider": "anthropic",
    "effort": "high",
    "timezone": "Asia/Tehran",
    "rrule": "FREQ=WEEKLY;BYDAY=SA;BYHOUR=10;BYMINUTE=0",
    "scope": "company:TY",
    "level": "decision",
    "status": "active",
    "priority": "P2",
    "kind": "one_off",
    "risk": "low",
    "resolution": "M-0001",
    "decision": "D-000123",
    "deliverable": "O-000456",
    "message_ref": "A-0142",
    "up_to_ref": "TY-CEO-0012",
    "source_url": "https://platform.claude.com/docs/en/about-claude/pricing",
    "as_of": "2026-10-16",
    "morning_report_at": "08:00:00",
    "device_name": "Pixel 9",
    "mime": "application/pdf",
    "sha256": "9f2b5c1a" * 8,
    "name": "report.pdf",
    "action": "decision.approve",
    "target": "D-000123",
}


# (schema title, property) -> value, where the name alone is ambiguous.
CONTEXT: dict[tuple[str, str], Any] = {
    ("EmployeeRef", "code"): "TY-GROWTH-01",
    ("EmployeeRef", "kind"): "employee",
    ("Employee", "code"): "TY-GROWTH-01",
    ("Employee", "kind"): "employee",
    ("Employee", "activity"): "working",
    ("EmployeeDetail", "code"): "TY-GROWTH-01",
    ("EmployeeDetail", "kind"): "employee",
    ("ChartNode", "code"): "TY-CEO",
    ("ChartNode", "kind"): "ceo",
    ("Thread", "code"): "TY-CEO",
    ("Thread", "kind"): "ceo",
    ("Message", "ref"): "TY-CEO-0012",
    ("Message", "thread"): "TY-CEO",
    ("SearchHit", "ref"): "TY-CEO-0012",
    ("Decision", "ref"): "D-000123",
    ("Decision", "kind"): "hire",
    ("Decision", "status"): "pending",
    ("Deliverable", "ref"): "O-000456",
    ("Resolution", "ref"): "M-0001",
    ("Work", "ref"): "W-000789",
    ("WorkDetail", "ref"): "W-000789",
    ("Work", "status"): "in_progress",
    ("WorkDetail", "status"): "in_progress",
    ("ChainStep", "ref"): "W-000789",
    ("ChainStep", "status"): "in_progress",
    ("Company", "kind"): "company",
    ("Department", "code"): "GROWTH",
    ("Actor", "code"): "TY-CEO",
    ("Actor", "kind"): "agent",
    ("AuditEntry", "action"): "decision.approve",
}


def _resolve(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        return dict(components.get(ref.rsplit("/", 1)[1], {}))
    return schema


def example(
    schema: dict[str, Any],
    components: dict[str, Any],
    name: str = "",
    depth: int = 0,
    parent: str = "",
) -> Any:
    s = _resolve(schema, components)
    if (parent, name) in CONTEXT:
        return CONTEXT[(parent, name)]
    if depth > 6:
        return None
    if "example" in s:
        return copy.deepcopy(s["example"])
    if s.get("examples"):
        return copy.deepcopy(s["examples"][0])
    if "const" in s:
        return s["const"]
    if s.get("enum"):
        return s["enum"][0]
    for key in ("anyOf", "oneOf"):
        if key in s:
            options = [o for o in s[key] if _resolve(o, components).get("type") != "null"]
            return example(options[0], components, name, depth + 1, parent) if options else None
    if "allOf" in s:
        merged: dict[str, Any] = {}
        for part in s["allOf"]:
            value = example(part, components, name, depth + 1)
            if isinstance(value, dict):
                merged.update(value)
        return merged
    t = s.get("type")
    if t == "object" or "properties" in s:
        props = s.get("properties") or {}
        title = str(s.get("title", ""))
        return {k: example(v, components, k, depth + 1, title) for k, v in props.items()}
    if t == "array":
        item = example(s.get("items") or {}, components, name.rstrip("s"), depth + 1)
        return [] if item is None else [item]
    if t == "string":
        fmt = s.get("format")
        if fmt == "date-time":
            return WHEN
        if fmt == "date":
            return "2026-10-17"
        if fmt == "uuid":
            return UUID
        if fmt in ("binary", "byte"):
            return "..."
        if name in HINTS and isinstance(HINTS[name], str):
            return HINTS[name]
        if name.endswith("_usd") or name in ("usd", "usd_used"):
            return "2.410000"
        return "x" * max(1, int(s.get("minLength", 1)))
    if t == "integer":
        return int(
            s.get("minimum", s.get("exclusiveMinimum", 0) + 1 if "exclusiveMinimum" in s else 1)
        )
    if t == "number":
        return float(s.get("minimum", 1))
    if t == "boolean":
        return False
    return None


def add_examples(doc: dict[str, Any]) -> dict[str, Any]:
    components = doc.get("components", {}).get("schemas", {})
    for path_item in doc.get("paths", {}).values():
        for op in path_item.values():
            if not isinstance(op, dict):
                continue
            body = op.get("requestBody", {}).get("content", {}).get("application/json")
            if body is not None and "example" not in body:
                curated = CURATED.get(str(op.get("operationId")))
                body["example"] = (
                    curated if curated is not None else example(body.get("schema", {}), components)
                )
            for code, resp in (op.get("responses") or {}).items():
                if not str(code).startswith("2"):
                    continue
                content = (resp.get("content") or {}).get("application/json")
                if content is not None and "example" not in content and content.get("schema"):
                    content["example"] = example(content["schema"], components)
    return doc
