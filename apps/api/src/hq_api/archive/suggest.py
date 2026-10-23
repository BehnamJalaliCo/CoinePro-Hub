"""Rule-based suggestions for a draft (prompt 14 §4, contract §23.9): code,
never a model. From a file's text: Jalali and Gregorian dates, amounts with
their unit, an IBAN (شبا), a national code, a registration number, a class
by its key words, and the parties of the registry whose names appear. A
suggestion is only shown to the person who files; it is never filed by
itself (red line 4).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from hq_api.db import Tx

_FA = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
JALALI = re.compile(r"(?<![0-9])(1[34][0-9]{2})[/\-.](0?[1-9]|1[0-2])[/\-.](0?[1-9]|[12][0-9]|3[01])(?![0-9])")
GREG = re.compile(r"(?<![0-9])(20[0-9]{2}|19[0-9]{2})[/\-.](0?[1-9]|1[0-2])[/\-.](0?[1-9]|[12][0-9]|3[01])(?![0-9])")
GREG_DMY = re.compile(r"(?<![0-9])(0?[1-9]|[12][0-9]|3[01])[/.](0?[1-9]|1[0-2])[/.](20[0-9]{2})(?![0-9])")
UNITS = {
    "usdt": "USDT", "تتر": "USDT", "usd": "USD", "$": "USD", "دلار": "USD", "eur": "EUR", "€": "EUR",
    "یورو": "EUR", "ریال": "IRR", "rial": "IRR", "irr": "IRR", "تومان": "IRT", "toman": "IRT",
    "درهم": "AED", "aed": "AED", "لیر": "TRY", "try": "TRY",
}  # fmt: skip
AMOUNT = re.compile(
    r"(?:(\$|€)\s?([0-9][0-9,٬]*(?:\.[0-9]+)?)|([0-9][0-9,٬]*(?:\.[0-9]+)?)\s?"
    r"(usdt|usd|eur|irr|aed|try|rial|toman|دلار|یورو|ریال|تومان|تتر|درهم|لیر))",
    re.I,
)
IBAN = re.compile(r"(?<![A-Z0-9])IR\s?([0-9]{2}(?:\s?[0-9]){22})(?![0-9])", re.I)
NATIONAL = re.compile(r"(?:کد\s?ملی|شناسه\s?ملی|national\s?(?:id|code))\D{0,6}([0-9]{10,11})(?![0-9])", re.I)
REGISTRATION = re.compile(r"(?:شماره\s?ثبت|ثبت\s?شده\s?به\s?شماره|registration\s?(?:no|number))\D{0,6}([0-9]{3,12})", re.I)
CLASS_WORDS = (
    ("affiliate_agreement", ("افیلیت", "affiliate", "referral", "رفرال", "همکاری در فروش")),
    ("invoice", ("فاکتور", "صورتحساب", "رسید پرداخت", "invoice", "receipt")),
    ("license", ("مجوز", "پروانه", "license", "licence")),
    ("domain", ("دامنه", "domain", "registrar")),
    ("company_registration", ("آگهی تاسیس", "آگهی تأسیس", "ثبت شرکت", "اساسنامه شرکت", "certificate of incorporation")),
    ("legal_correspondence", ("اخطاریه", "اظهارنامه", "notice of", "takedown", "appeal")),
    ("contract", ("قرارداد", "contract", "agreement", "طرفین")),
)
MAX_TEXT = 60_000


def _jalali(y: int, m: int, d: int) -> str | None:
    from hq_api.domain.advisor import jalali_to_gregorian

    try:
        return jalali_to_gregorian(y, m, d).isoformat()
    except ValueError:
        return None


def dates(text: str) -> list[str]:
    t = text.translate(_FA)[:MAX_TEXT]
    out: list[str] = []
    for m in JALALI.finditer(t):
        g = _jalali(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if g:
            out.append(g)
    for m in GREG.finditer(t):
        try:
            out.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat())
        except ValueError:
            pass
    for m in GREG_DMY.finditer(t):
        try:
            out.append(date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat())
        except ValueError:
            pass
    return list(dict.fromkeys(out))[:20]


def amounts(text: str) -> list[dict[str, str]]:
    t = text.translate(_FA)[:MAX_TEXT]
    out = []
    for m in AMOUNT.finditer(t):
        unit = (m.group(1) or m.group(4) or "").lower()
        raw = (m.group(2) or m.group(3) or "").replace(",", "").replace("٬", "")
        cur = UNITS.get(unit)
        if cur and raw:
            out.append({"amount": raw, "currency": cur})
    return out[:10]


async def rules(tx: Tx, text: str, name: str = "") -> dict[str, Any] | None:
    blob = f"{name}\n{text}"
    if not blob.strip():
        return None
    low = blob.lower()
    cls = next((k for k, words in CLASS_WORDS if any(w in low for w in words)), None)
    found_dates = dates(blob)
    found_amounts = amounts(blob)
    t = blob.translate(_FA)
    ibans = ["IR" + re.sub(r"\s", "", m.group(1)) for m in IBAN.finditer(t)][:5]
    national = [m.group(1) for m in NATIONAL.finditer(t)][:5]
    registration = [m.group(1) for m in REGISTRATION.finditer(t)][:5]
    parties: list[dict[str, str]] = []
    for p in await tx.all(
        "SELECT ref, name_fa, name_en FROM archive.parties WHERE status = 'active' ORDER BY ref LIMIT 500"
    ):
        names = [n for n in (p["name_fa"], p["name_en"]) if n and len(n) >= 3]
        if any(n.lower() in low for n in names):
            parties.append({"party": p["ref"], "role_fa": ""})
    metadata: dict[str, Any] = {}
    if cls == "invoice":
        if found_dates:
            metadata["date"] = found_dates[0]
        if found_amounts:
            metadata["amount"] = found_amounts[0]
    elif cls in ("contract", "affiliate_agreement"):
        if found_dates:
            metadata["start"] = found_dates[0]
        if len(found_dates) > 1:
            metadata["end"] = found_dates[-1]
        if cls == "contract" and found_amounts:
            metadata["value"] = found_amounts[0]
    elif cls in ("license", "domain") and found_dates:
        metadata["expires_at"] = max(found_dates)
    elif cls == "company_registration":
        if registration:
            metadata["registration_no"] = registration[0]
        if found_dates:
            metadata["registered_at"] = found_dates[0]
    first_line = next((ln.strip() for ln in text.splitlines() if len(ln.strip()) >= 4), "")
    title = (first_line or name or "")[:120] or None
    note = []
    if found_dates:
        note.append("تاریخ‌ها: " + "، ".join(found_dates[:5]))
    if found_amounts:
        note.append("مبلغ‌ها: " + "، ".join(f"{a['amount']} {a['currency']}" for a in found_amounts[:3]))
    if ibans:
        note.append(f"شبا: {len(ibans)} مورد")
    if national:
        note.append(f"کد ملی: {len(national)} مورد")
    if registration:
        note.append("شماره‌ی ثبت: " + "، ".join(registration[:3]))
    return {
        "class": cls,
        "title_fa": title,
        "metadata": metadata,
        "parties": parties[:10],
        "by": "rules",
        "note_fa": " · ".join(note) or "از متن چیزی برای پیشنهاد پیدا نشد",
        "found": {"dates": found_dates, "amounts": found_amounts, "ibans": len(ibans),
                  "national_codes": len(national), "registration_numbers": registration},  # fmt: skip
    }
