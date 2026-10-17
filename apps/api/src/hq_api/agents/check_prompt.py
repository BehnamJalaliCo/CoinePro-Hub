"""`python -m hq_api.agents.check_prompt <role> < token`: a real prompt check
of one charter (prompt 05 §9.3), run inside the worker (make prompt-check).

One step call through llm-router as the caller on stdin (hq-ops), with the
charter's system prompt, the runtime protocol and a test question, checked
against the step schema; for the advisor also the answer phase (citations).
Nothing is stored anywhere but the router's ledger: no run, no message, no
session. Only metadata is printed (validity, tools, token counts), never the
prompt or the model's text.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import httpx

from hq_api.agents import protocol as P
from hq_api.config import Settings
from hq_api.db import Database
from hq_common import charters

QUESTIONS = {
    "advisor": "مدیر کل (آزمایش prompt، نه یک گفت‌وگوی واقعی): امروز وضعیت کلی هلدینگ چطور است؟ "
    "یک پاسخ کوتاه بده و اگر به چیزی استناد میکنی، ارجاعش را بیاور.",
}
DEFAULT_QUESTION = "آزمایش prompt: یک قدم اول معمولی برای نقش خودت بردار (فقط ابزارهای خواندنی)."


async def _values(db: Database, role: str) -> tuple[dict[str, str], str]:
    async with db.raw() as tx:
        ids = [r["id"] for r in await tx.all("SELECT id FROM core.companies")]
    async with db.tx(ids) as tx:
        emp = await tx.one(
            """SELECT e.code, e.title_fa, c.code AS company, c.name_fa, c.name_en, d.code AS department,
                      d.name_fa AS department_name_fa,
                      (SELECT m.code FROM core.employees m WHERE m.id = e.reports_to) AS manager,
                      (SELECT h.code FROM core.companies h WHERE h.kind = 'holding') AS holding
               FROM core.employees e JOIN core.companies c ON c.id = e.company_id
               LEFT JOIN core.departments d ON d.id = e.department_id
               WHERE e.role = :role AND e.status = 'active' ORDER BY e.created_at LIMIT 1""",
            role=role,
        )
    values = {
        "employee_code": emp["code"],
        "employee_title_fa": emp["title_fa"],
        "company_code": emp["company"],
        "company_name_fa": emp["name_fa"] or emp["company"],
        "company_name_en": emp["name_en"] or emp["company"],
        "holding_code": emp["holding"],
        "department_code": emp["department"] or "",
        "department_name_fa": emp["department_name_fa"] or "",
        "manager_code": emp["manager"] or "owner",
        "today_jalali": "",
        "today_gregorian": "",
        "owner_timezone": "Asia/Tehran",
    }
    return values, emp["company"]


def _usage(body: dict[str, Any]) -> dict[str, int]:
    u = body.get("usage") or {}
    return {
        k: int(u.get(k) or 0)
        for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
    }


async def check(role: str, token: str) -> dict[str, Any]:
    s = Settings()
    lib = charters.load()
    charter = lib.roles[role]
    db = Database.create(s, pool_size=1)
    try:
        values, company = await _values(db, role)
    finally:
        await db.close()
    advisor = charter.kind == "advisor"
    system = P.system_prompt(
        lib, charter, values, max_actions=s.agent_actions_per_step, answer_phase=advisor
    )
    context = (
        "# Trigger\nmessage (prompt check: nothing you do here is stored or carried out)\n\n"
        f"# Conversation (oldest first; answer the owner's latest)\n[check] owner: "
        f"{QUESTIONS.get(role, DEFAULT_QUESTION)}"
    )
    base = {
        "company_code": company,
        "actor_ref": values["employee_code"],
        "work_ref": "prompt-05-check",
        "role": charter.role,
        "task_class": "general",
        "priority": charter.priority,
        "model": charter.model,
        "effort": charter.effort,
        "timeout_s": s.agent_step_timeout_s,
        "meta": {"charter": charter.ref, "purpose": "prompt_check"},
    }
    out: dict[str, Any] = {"role": role, "charter": charter.ref, "model": charter.model}
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=s.llm_router_url, timeout=s.agent_step_timeout_s + 30) as c:
        messages = [{"role": "user", "content": context}]
        r = await c.post(
            "/v1/run",
            headers=headers,
            json={**base, "system": system, "messages": messages, "json_schema": P.STEP_SCHEMA},
        )
        body = r.json()
        step: dict[str, Any] = {"http": r.status_code, "status": body.get("status"), **_usage(body)}
        try:
            parsed = P.parse_step(body.get("json"), body.get("text"), s.agent_actions_per_step)
            tools = [a.tool for a in parsed.actions]
            step.update(
                schema_ok=True,
                tools=tools,
                tools_in_charter=all(t in charter.tools for t in tools),
                done=parsed.done,
                summary_chars=len(parsed.summary_fa),
            )
        except P.BadOutput as e:
            step.update(schema_ok=False, error=str(e)[:200])
        out["step"] = step
        if advisor and step.get("schema_ok"):
            messages += [
                {"role": "assistant", "content": json.dumps(body.get("json"), ensure_ascii=False)},
                {
                    "role": "user",
                    "content": "Results: none (a prompt check runs no tools). Now answer the owner.",
                },
            ]
            r = await c.post(
                "/v1/run",
                headers=headers,
                json={**base, "system": system + "\n\n" + P.ANSWER_PHASE, "messages": messages},
            )
            body = r.json()
            text, cites = P.split_answer(body.get("text") or "")
            out["answer"] = {
                "http": r.status_code,
                "status": body.get("status"),
                **_usage(body),
                "answer_chars": len(text),
                "citations_parsed": len(cites),
                "citations_block_streamed": P.CITATIONS_OPEN in text,
            }
    calls = [out["step"], *([out["answer"]] if "answer" in out else [])]
    out["tokens_in"] = sum(x["input_tokens"] + x["cache_read_tokens"] + x["cache_write_tokens"] for x in calls)
    out["tokens_out"] = sum(x["output_tokens"] for x in calls)
    return out


def main() -> None:  # pragma: no cover - CLI
    role = sys.argv[1] if len(sys.argv) > 1 else "advisor"
    token = sys.stdin.read().strip()
    print(json.dumps(asyncio.run(check(role, token)), ensure_ascii=False))


if __name__ == "__main__":  # pragma: no cover
    main()
