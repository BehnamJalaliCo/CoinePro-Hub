"""Errors as RFC 9457 problem+json (contract §1, §14).

Every error carries a stable machine `code` and a short Persian
`message_fa` for the UI. Database rules (triggers, constraints, RLS) are
mapped to the same codes, so a rule broken anywhere surfaces identically.
Internal details never reach the client: a 500 says only `internal_error`.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("hq_api.errors")

PROBLEM_JSON = "application/problem+json"

# code -> (default HTTP status, title, message_fa)
CODES: dict[str, tuple[int, str, str]] = {
    "unauthenticated": (401, "Unauthenticated", "ورود لازم است."),
    "forbidden": (403, "Forbidden", "اجازه‌ی این کار را نداری."),
    "csrf_rejected": (403, "CSRF rejected", "درخواست از مبدأ معتبر نیامده است."),
    "step_up_required": (403, "Step-up required", "این کار تأیید دوباره با کلید عبور لازم دارد."),
    "step_up_invalid": (403, "Step-up invalid", "تأیید دوباره معتبر نیست یا منقضی شده است."),
    "origin_not_configured": (
        503,
        "Origin not configured",
        "ورود هنوز فعال نیست؛ دامنه و HTTPS تنظیم نشده‌اند.",
    ),
    "not_found": (404, "Not found", "پیدا نشد."),
    "version_conflict": (
        409,
        "Version conflict",
        "این مورد در این فاصله تغییر کرده است؛ دوباره بارگذاری کن.",
    ),
    "idempotency_conflict": (
        409,
        "Idempotency conflict",
        "این کلید تکرار قبلاً با درخواست دیگری استفاده شده است.",
    ),
    "validation_failed": (422, "Validation failed", "اطلاعات ارسال‌شده درست نیست."),
    "evidence_required": (422, "Evidence required", "بستن کار بدون خروجی یا شاهد ممکن نیست."),
    "delegation_depth_exceeded": (
        409,
        "Delegation depth exceeded",
        "ارجاع بیش از دو مرحله مجاز نیست.",
    ),
    "budget_exceeded": (
        409,
        "Budget exceeded",
        "بودجه‌ی این کار از باقیمانده‌ی کار بالادستی بیشتر است.",
    ),
    "company_locked": (423, "Company locked", "این شرکت فعلاً قفل است (کلید توقف یا توقف deploy)."),
    "decision_not_pending": (409, "Decision not pending", "این تصمیم قبلاً گرفته شده است."),
    "policy_denied": (403, "Policy denied", "طبق سیاست‌های هلدینگ این کار مجاز نیست."),
    "policy_unavailable": (
        503,
        "Policy unavailable",
        "سرویس سیاست‌ها پاسخ نداد؛ کمی بعد دوباره امتحان کن.",
    ),
    "precondition_required": (
        428,
        "Precondition required",
        "نسخه‌ی فعلی (If-Match) لازم است؛ اول آن را بخوان.",
    ),
    "rate_limited": (429, "Rate limited", "درخواست‌ها زیاد است؛ کمی بعد دوباره امتحان کن."),
    "channel_not_configured": (503, "Channel not configured", "این کانال هنوز تنظیم نشده است."),
    # ⟨1.4.1⟩ live replies are switched off; the stored reply still arrives in the thread
    "live_unavailable": (
        503,
        "Live unavailable",
        "پاسخ زنده خاموش است؛ پاسخ در همین گفت‌وگو ذخیره میشود.",
    ),
    # ⟨1.4.2⟩ an agent proposed a hire while hiring is closed (contract §18.11); this
    # text reaches the model through the Tool Gateway
    "hiring_closed": (403, "Hiring closed", "استخدام بسته است؛ کمبود تیم را در خروجی‌ات بنویس."),
    # ⟨1.4.3⟩ a feature the contract names that this server build does not serve yet
    "not_ready": (409, "Not ready", "این قابلیت هنوز روی این سرور آماده نیست."),
    # ⟨1.3⟩ the Code Workshop runs nowhere until the owner chooses its runtime (§17.7)
    "runtime_not_configured": (
        503,
        "Runtime not configured",
        "کارگاه کد هنوز روشن نیست: محل اجرای سشن‌ها را مدیر کل باید انتخاب کند.",
    ),
    # prompt 07 §2: the agents' internet (egress)
    "needs_owner": (
        403,
        "Needs the owner",
        "این یک تعهد بیرونی به نام هلدینگ است؛ با propose برای مالک پیشنهادش بده.",
    ),
    "internal_data": (
        403,
        "Internal data",
        "داده‌ی داخلی (کد کارمند، ارجاع، ایمیل، تلفن یا رمز) نباید از هاب بیرون برود؛ بدون آن تکرار کن.",
    ),
    "egress_limit": (429, "Egress limit", "سقف اینترنت این اجرا یا امروز شرکت پر شده است."),
    "account_not_configured": (
        409,
        "Account not configured",
        "این حساب سرویس هنوز رمز ندارد؛ مالک باید آن را روی سرور بگذارد.",
    ),
    "internal_error": (500, "Internal error", "خطای داخلی؛ به تیم فنی گزارش شد."),
}

# SQLSTATEs raised by our own triggers (migrations/versions/0001_core_org.py).
SQLSTATE_CODES: dict[str, str] = {
    "HQD01": "delegation_depth_exceeded",
    "HQB01": "budget_exceeded",
    "HQE01": "evidence_required",
    "HQS01": "decision_not_pending",
    "HQA01": "validation_failed",
    "HQI01": "validation_failed",
    "HQV01": "validation_failed",
    "HQN01": "not_found",
}


class Problem(BaseModel):
    type: str
    title: str
    status: int
    code: str
    detail: str | None = None
    message_fa: str
    fields: dict[str, str] | None = None
    request_id: str | None = None


class ApiError(Exception):
    def __init__(
        self,
        status: int | None,
        code: str,
        detail: str | None = None,
        *,
        fields: dict[str, str] | None = None,
        message_fa: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        default_status, _, _ = CODES.get(code, CODES["internal_error"])
        self.status = status or default_status
        self.code = code
        self.detail = detail
        self.fields = fields
        self.message_fa = message_fa
        self.headers = headers
        super().__init__(f"{code}: {detail or ''}")


def problem_response(request: Request, err: ApiError) -> JSONResponse:
    _, title, message_fa = CODES.get(err.code, CODES["internal_error"])
    body = Problem(
        type=f"urn:coinepro-hq:problem:{err.code}",
        title=title,
        status=err.status,
        code=err.code,
        detail=err.detail,
        message_fa=err.message_fa or message_fa,
        fields=err.fields,
        request_id=getattr(request.state, "request_id", None),
    )
    return JSONResponse(
        body.model_dump(exclude_none=True),
        status_code=err.status,
        media_type=PROBLEM_JSON,
        headers=err.headers,
    )


def sqlstate_of(exc: DBAPIError) -> str | None:
    orig: Any = exc.orig
    for candidate in (orig, getattr(orig, "__cause__", None)):
        state = getattr(candidate, "sqlstate", None) or getattr(candidate, "pgcode", None)
        if isinstance(state, str):
            return state
    return None


def db_message(exc: DBAPIError) -> str:
    """The trigger's own message (our triggers never include secrets or bodies)."""
    orig: Any = exc.orig
    cause = getattr(orig, "__cause__", None)
    msg = getattr(cause, "message", None) or str(orig)
    return str(msg).splitlines()[0][:300]


def from_db_error(exc: DBAPIError) -> ApiError:
    state = sqlstate_of(exc) or ""
    if state in SQLSTATE_CODES:
        return ApiError(None, SQLSTATE_CODES[state], db_message(exc))
    if state == "23505":
        return ApiError(409, "validation_failed", "duplicate value")
    if state in ("23503", "23514", "23502", "23P01") or state.startswith("22"):
        return ApiError(422, "validation_failed", f"the data breaks a database rule ({state})")
    if state == "42501":
        return ApiError(403, "forbidden", "row-level security denied the change")
    if state in ("40001", "40P01", "55P03"):
        return ApiError(409, "version_conflict", "concurrent change; retry")
    if state == "57014":
        return ApiError(503, "internal_error", "the database took too long")
    return ApiError(500, "internal_error")


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return problem_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for e in exc.errors()[:20]:
            loc = ".".join(str(p) for p in e.get("loc", ()) if p not in ("body", "query", "path"))
            fields[loc or "request"] = str(e.get("msg", "invalid"))[:200]
        return problem_response(request, ApiError(422, "validation_failed", fields=fields))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "unauthenticated",
            403: "forbidden",
            404: "not_found",
            405: "not_found",
            413: "validation_failed",
            415: "validation_failed",
            429: "rate_limited",
        }.get(exc.status_code, "internal_error" if exc.status_code >= 500 else "validation_failed")
        return problem_response(request, ApiError(exc.status_code, code, str(exc.detail)[:200]))

    @app.exception_handler(DBAPIError)
    async def _db(request: Request, exc: DBAPIError) -> JSONResponse:
        err = from_db_error(exc)
        if err.status >= 500:
            # SQLSTATE and the statement's first words only: values never reach a log.
            stmt = str(getattr(exc, "statement", "") or "").split()[:4]
            log.error(
                "database error", extra={"sqlstate": sqlstate_of(exc), "statement": " ".join(stmt)}
            )
        return problem_response(request, err)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled error", exc_info=exc)
        return problem_response(request, ApiError(500, "internal_error"))


def responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries for problem+json errors."""
    return {
        c: {"model": Problem, "content": {PROBLEM_JSON: {}}, "description": "Problem"}
        for c in codes
    }
