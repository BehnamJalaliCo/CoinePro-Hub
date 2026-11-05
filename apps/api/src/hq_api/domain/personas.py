"""Personas and the message test (contract §33.9 ⟨1.15⟩).

Personas are a company's data: the owner writes and edits them; up to MAX_SUGGESTED can be proposed
from the company's approved knowledge by ONE mid-model call and are saved only when the owner keeps
one (a `POST` with `source: kb_suggested`). A message is tested by ONE call for all personas (task
class `persona_test`, a strict schema); code checks the answer (every persona exactly once, the score
a whole number 0..100) before anything is stored or shown. Numbers and the gate are code: the model
only plays the personas. The same function serves the route and the line step `persona_test`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import workflows_client
from hq_api.db import Tx
from hq_api.domain.automations import MODEL as MID_MODEL
from hq_api.errors import ApiError
from hq_common.redact import scrub

log = logging.getLogger("hq_api.personas")

TASK_CLASS = "persona_test"
MAX_PERSONAS = 8  # a company's personas (a test is one call for all of them)
MAX_SUGGESTED = 4
MAX_TEXT = 8000
MAX_OUTPUT_TOKENS = 3000
KB_ENTRIES = 12
KB_CHARS = 700
SOURCES = ("owner", "kb_suggested")

BAD_ANSWER_FA = "پاسخ مدل قابل‌اعتماد نبود؛ کمی بعد دوباره امتحان کنید."
DOWN_FA = "مدل در دسترس نبود؛ کمی بعد دوباره امتحان کنید."


# ------------------------------------------------------------------ shapes --
class PersonaRecord(BaseModel):
    """One persona of a company."""

    id: UUID
    company: str
    name_fa: str
    summary_fa: str
    pains_fa: list[str]
    objections_fa: list[str]
    channel_fa: str
    source: str
    version: int


class PersonaDraft(BaseModel):
    """A persona as the model proposed it; nothing is saved."""

    name_fa: str
    summary_fa: str
    pains_fa: list[str]
    objections_fa: list[str]
    channel_fa: str


class PersonaSuggestion(BaseModel):
    """Up to four proposals from the company's knowledge; the owner keeps the ones he likes."""

    company: str
    personas: list[PersonaDraft]
    basis_fa: str


class PersonaTestResult(BaseModel):
    persona: UUID
    name_fa: str
    score: int = Field(ge=0, le=100)
    would_act: bool
    objection_fa: str | None = None
    fix_fa: str | None = None


class PersonaTest(BaseModel):
    """A message tested against the company's personas (one model call for all of them)."""

    id: UUID
    text: str
    results: list[PersonaTestResult]
    average: int = Field(ge=0, le=100)
    lowest: int = Field(ge=0, le=100)
    at: datetime


# ----------------------------------------------------------------- helpers --
def clean(s: Any, limit: int) -> str:
    """The model's or the owner's text as one tidy, secret-free line of at most `limit` characters."""
    return " ".join(scrub(str(s or "")).split())[:limit]


def clean_list(items: Any, limit: int, n: int = 8) -> list[str]:
    out: list[str] = []
    for x in items if isinstance(items, list) else []:
        t = clean(x, limit)
        if t and t not in out:
            out.append(t)
    return out[:n]


def record(r: dict[str, Any], code: str) -> PersonaRecord:
    def lst(v: Any) -> list[str]:
        return [str(x) for x in (json.loads(v) if isinstance(v, str) else v or [])]

    return PersonaRecord(
        id=r["id"],
        company=code,
        name_fa=r["name_fa"],
        summary_fa=r["summary_fa"],
        pains_fa=lst(r["pains_fa"]),
        objections_fa=lst(r["objections_fa"]),
        channel_fa=r["channel_fa"],
        source=r["source"],
        version=r["version"],
    )


async def active(tx: Tx, company_id: UUID) -> list[dict[str, Any]]:
    return await tx.all(
        """SELECT * FROM growth.personas WHERE company_id = :co AND archived_at IS NULL
           ORDER BY created_at, id""",
        co=company_id,
    )


async def create(
    tx: Tx, company_id: UUID, *, name_fa: str, summary_fa: str, pains_fa: list[str],
    objections_fa: list[str], channel_fa: str, source: str,
) -> dict[str, Any]:  # fmt: skip
    if len(await active(tx, company_id)) >= MAX_PERSONAS:
        raise ApiError(
            409,
            "validation_failed",
            f"at most {MAX_PERSONAS} personas",
            message_fa=f"هر شرکت حداکثر {MAX_PERSONAS} پرسونا دارد؛ یکی را بایگانی کنید.",
        )
    row = await tx.first(
        """INSERT INTO growth.personas (company_id, name_fa, summary_fa, pains_fa, objections_fa,
                                        channel_fa, source)
           VALUES (:co, :n, :s, CAST(:p AS jsonb), CAST(:o AS jsonb), :c, :src) RETURNING *""",
        co=company_id,
        n=clean(name_fa, 100),
        s=clean(summary_fa, 1000),
        p=json.dumps(clean_list(pains_fa, 300), ensure_ascii=False),
        o=json.dumps(clean_list(objections_fa, 300), ensure_ascii=False),
        c=clean(channel_fa, 200),
        src=source,
    )
    assert row is not None
    return row


# ------------------------------------------------------------------ the call --
async def ask(hub: Any, req: dict[str, Any]) -> tuple[Any, int]:
    """One router call through the worker (the api cannot reach the router). (the answer, tokens);
    the answer is None when the model was not there or said nothing usable."""
    answer = await workflows_client.route_order(hub, req, timeout_s=85)
    if not isinstance(answer, dict):
        return None, 0
    tokens = int(answer.get("input_tokens") or 0) + int(answer.get("output_tokens") or 0)
    return answer.get("routes"), tokens


def _request(
    hub_code: str, purpose: str, system: str, prompt: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    return {
        "company_code": hub_code,
        "actor_ref": f"{hub_code}-PERSONAS",
        "task_class": TASK_CLASS,
        "priority": 1,
        "model": MID_MODEL,
        "effort": "low",
        "system": system,
        "prompt": json.dumps(prompt, ensure_ascii=False),
        "json_schema": schema,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "timeout_s": 80,
        "meta": {"purpose": purpose},
    }


def _str_list(max_items: int, max_len: int = 300) -> dict[str, Any]:
    return {
        "type": "array",
        "maxItems": max_items,
        "items": {"type": "string", "minLength": 1, "maxLength": max_len},
    }


# ----------------------------------------------------------------- suggest --
SUGGEST_SYSTEM = (
    "تو پژوهشگر بازار هستی. از روی دانشی که درباره‌ی یک شرکت داده شده، حداکثر چهار مخاطب نمونه "
    "(پرسونا) پیشنهاد بده؛ هر کدام با نام کوتاه، خلاصه، دردها، ایرادهایی که پیش از خرید می‌گیرد و "
    "کانالی که او را پیدا می‌کند. فقط بر پایه‌ی همان دانش بنویس؛ عدد، آمار یا ادعای تازه نساز. همه‌چیز "
    'فارسی. پاسخ: {"routes": {"personas": [...]}} و هیچ متن دیگر.'
)
SUGGEST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["routes"],
    "properties": {
        "routes": {
            "type": "object",
            "additionalProperties": False,
            "required": ["personas"],
            "properties": {
                "personas": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": MAX_SUGGESTED,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "name_fa",
                            "summary_fa",
                            "pains_fa",
                            "objections_fa",
                            "channel_fa",
                        ],
                        "properties": {
                            "name_fa": {"type": "string", "minLength": 1, "maxLength": 100},
                            "summary_fa": {"type": "string", "minLength": 1, "maxLength": 1000},
                            "pains_fa": _str_list(5),
                            "objections_fa": _str_list(5),
                            "channel_fa": {"type": "string", "maxLength": 200},
                        },
                    },
                }
            },
        }
    },
}


async def knowledge_of(tx: Tx, company_id: UUID) -> list[dict[str, Any]]:
    """The company's approved knowledge, newest first (titles and the start of each body)."""
    return await tx.all(
        """SELECT ref, title_fa, left(body_md, :n) AS body FROM knowledge.entries
           WHERE company_id = :co AND status = 'approved' AND layer IN ('company', 'department')
           ORDER BY approved_at DESC NULLS LAST LIMIT :k""",
        co=company_id,
        n=KB_CHARS,
        k=KB_ENTRIES,
    )


def draft_of(raw: Any) -> PersonaDraft | None:
    if not isinstance(raw, dict):
        return None
    name, summary = clean(raw.get("name_fa"), 100), clean(raw.get("summary_fa"), 1000)
    if not name or not summary:
        return None
    return PersonaDraft(
        name_fa=name,
        summary_fa=summary,
        pains_fa=clean_list(raw.get("pains_fa"), 300, 5),
        objections_fa=clean_list(raw.get("objections_fa"), 300, 5),
        channel_fa=clean(raw.get("channel_fa"), 200),
    )


async def suggest(hub: Any, company: Any) -> PersonaSuggestion:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        kb = await knowledge_of(tx, company.id)
    if not kb:
        raise ApiError(
            422,
            "validation_failed",
            "the company has no approved knowledge",
            message_fa="برای پیشنهاد پرسونا، شرکت باید دانش تأییدشده داشته باشد؛ ابتدا پایگاه دانش را پر کنید.",
            fields={"knowledge": "empty"},
        )
    prompt = {
        "company": company.name_fa or company.code,
        "knowledge": [
            {"title": clean(k["title_fa"], 200), "text": clean(k["body"], KB_CHARS)} for k in kb
        ],
    }
    got, _ = await ask(
        hub, _request(company.code, "persona_suggest", SUGGEST_SYSTEM, prompt, SUGGEST_SCHEMA)
    )
    items = got.get("personas") if isinstance(got, dict) else None
    drafts = [d for d in (draft_of(x) for x in items or []) if d is not None][:MAX_SUGGESTED]
    if not drafts:
        # 422 as the leads' draft and the automations do: the model gave nothing usable (never a 5xx)
        raise ApiError(
            422, "validation_failed", "no usable personas", message_fa=BAD_ANSWER_FA,
            fields={"personas": "not made"},
        )  # fmt: skip
    return PersonaSuggestion(
        company=company.code,
        personas=drafts,
        basis_fa=f"بر پایه‌ی {len(kb)} نوشته‌ی تأییدشده‌ی دانش شرکت؛ تا نگه نداشته‌اید ذخیره نمیشود.",
    )


# -------------------------------------------------------------------- test --
TEST_SYSTEM = (
    "تو نقش چند مخاطب را بازی می‌کنی. برای هر مخاطب (با شناسه‌ی کوتاهش) پیام را بخوان و مثل خود او "
    "قضاوت کن: score عدد صحیح ۰ تا ۱۰۰ برای اینکه پیام او را قانع می‌کند، would_act یعنی آیا او همان "
    "لحظه اقدام می‌کند، objection_fa بزرگ‌ترین ایرادی که می‌گیرد (یا null) و fix_fa یک اصلاح کوتاه برای "
    "متن پیام (یا null). برای هر مخاطب دقیقاً یک نتیجه بده، همه‌چیز فارسی و صادقانه؛ تعریف الکی نکن. "
    'پاسخ: {"routes": {"results": [...]}} و هیچ متن دیگر.'
)


def test_schema(ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["routes"],
        "properties": {
            "routes": {
                "type": "object",
                "additionalProperties": False,
                "required": ["results"],
                "properties": {
                    "results": {
                        "type": "array",
                        "minItems": len(ids),
                        "maxItems": len(ids),
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["persona", "score", "would_act", "objection_fa", "fix_fa"],
                            "properties": {
                                "persona": {"type": "string", "enum": ids},
                                "score": {"type": "integer", "minimum": 0, "maximum": 100},
                                "would_act": {"type": "boolean"},
                                "objection_fa": {"type": ["string", "null"], "maxLength": 400},
                                "fix_fa": {"type": ["string", "null"], "maxLength": 400},
                            },
                        },
                    }
                },
            }
        },
    }


def checked_results(got: Any, labels: dict[str, dict[str, Any]]) -> list[PersonaTestResult] | None:
    """The model's results, or None when they are not exactly one per persona with sane numbers."""
    items = got.get("results") if isinstance(got, dict) else None
    if not isinstance(items, list) or len(items) != len(labels):
        return None
    seen: dict[str, PersonaTestResult] = {}
    for it in items:
        if not isinstance(it, dict) or it.get("persona") not in labels or it["persona"] in seen:
            return None
        score, act = it.get("score"), it.get("would_act")
        if isinstance(score, bool) or not isinstance(score, int | float) or not 0 <= score <= 100:
            return None
        if not isinstance(act, bool):
            return None
        p = labels[it["persona"]]
        seen[it["persona"]] = PersonaTestResult(
            persona=p["id"],
            name_fa=p["name_fa"],
            score=round(score),
            would_act=act,
            objection_fa=clean(it.get("objection_fa"), 400) or None,
            fix_fa=clean(it.get("fix_fa"), 400) or None,
        )
    return [seen[k] for k in labels]  # the personas' own order


async def run_test(
    hub: Any, company: Any, text: str, *, source: str = "owner", run_ref: str | None = None
) -> tuple[PersonaTest, int]:
    """ONE model call for all the company's personas. (the stored test, tokens). 422 when the
    company has no persona or the text is empty; 422 when the model failed or answered badly (the
    caller decides what that means: the owner's explicit test, or a step that may retry)."""
    message = scrub(text).strip()[:MAX_TEXT]
    if not message:
        raise ApiError(
            422, "validation_failed", fields={"text": "empty"}, message_fa="متن پیام خالی است."
        )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        rows = await active(tx, company.id)
    if not rows:
        raise ApiError(
            422,
            "validation_failed",
            "the company has no personas",
            message_fa="برای این شرکت پرسونایی تعریف نشده؛ ابتدا پرسونا بسازید.",
            fields={"personas": "none"},
        )
    labels = {f"p{i + 1}": r for i, r in enumerate(rows)}
    prompt = {
        "company": company.name_fa or company.code,
        "message": message,
        "personas": [
            {
                "persona": k,
                "name": r["name_fa"],
                "summary": r["summary_fa"],
                "pains": r["pains_fa"],
                "objections": r["objections_fa"],
                "channel": r["channel_fa"],
            }
            for k, r in labels.items()
        ],
    }
    got, tokens = await ask(
        hub, _request(company.code, "persona_test", TEST_SYSTEM, prompt, test_schema(list(labels)))
    )
    if got is None:
        raise ApiError(
            422, "validation_failed", "the model did not answer", message_fa=DOWN_FA,
            fields={"results": "not made"},
        )  # fmt: skip
    results = checked_results(got, labels)
    if results is None:
        raise ApiError(
            422, "validation_failed", "the model's answer failed the check", message_fa=BAD_ANSWER_FA,
            fields={"results": "not made"},
        )  # fmt: skip
    scores = [r.score for r in results]
    async with hub.db.tx(await hub.companies.ids()) as tx:
        row = await tx.first(
            """INSERT INTO growth.persona_tests (company_id, message, results, source, run_ref, tokens)
               VALUES (:co, :m, CAST(:r AS jsonb), :s, :run, :t) RETURNING id, at""",
            co=company.id,
            m=message,
            r=json.dumps([r.model_dump(mode="json") for r in results], ensure_ascii=False),
            s=source,
            run=run_ref,
            t=tokens,
        )
    assert row is not None
    return (
        PersonaTest(
            id=row["id"],
            text=message,
            results=results,
            average=round(sum(scores) / len(scores)),
            lowest=min(scores),
            at=row["at"],
        ),
        tokens,
    )
