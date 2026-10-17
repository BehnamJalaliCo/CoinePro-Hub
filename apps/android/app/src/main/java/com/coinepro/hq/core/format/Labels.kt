package com.coinepro.hq.core.format

import com.coinepro.hq.core.net.Actor
import com.coinepro.hq.designsystem.generated.DivanIcon

// Persian labels for contract enums (mirrors apps/web/src/lib/labels.ts).

enum class Tone { NEUTRAL, GOLD, POS, NEG, WARN, LAPIS, LEARN, SILVER }

data class Kind(val fa: String, val icon: DivanIcon)

val DECISION_KIND = mapOf(
    "hire" to Kind("استخدام", DivanIcon.HIRE),
    "dismissal" to Kind("برکناری", DivanIcon.DISMISS),
    "recurring_approval" to Kind("کار دائمی", DivanIcon.TIME),
    "deploy" to Kind("انتشار (deploy)", DivanIcon.SERVER),
    "a3_action" to Kind("اقدام بیرونی", DivanIcon.SHARE),
    "proposal" to Kind("پیشنهاد رشد", DivanIcon.CHART),
    "budget_change" to Kind("تغییر بودجه", DivanIcon.BUDGET),
    "evaluation" to Kind("ارزیابی", DivanIcon.RATE),
)

fun decisionKind(k: String) = DECISION_KIND[k] ?: Kind(k, DivanIcon.DECISION)

val DECISION_STATUS = mapOf(
    "pending" to "منتظر مُهر",
    "approved" to "مُهر شد",
    "rejected" to "رد شد",
    "returned" to "برگشت خورد",
    "expired" to "منقضی",
    "withdrawn" to "پس گرفته شد",
)

data class Risk(val fa: String, val tone: Tone)

val RISK = mapOf(
    "low" to Risk("ریسک کم", Tone.POS),
    "medium" to Risk("ریسک متوسط", Tone.WARN),
    "high" to Risk("ریسک بالا", Tone.NEG),
)

fun risk(r: String) = RISK[r] ?: RISK.getValue("medium")

val WORK_STATUS = mapOf(
    "queued" to "در صف",
    "in_progress" to "در حال انجام",
    "waiting" to "منتظر",
    "delivered" to "تحویل شد",
    "done" to "تمام شد",
    "cancelled" to "لغو شد",
    "failed" to "ناموفق",
)

val WORK_KIND = mapOf("one_off" to "یک‌باره", "recurring" to "دائمی", "event" to "رویدادمحور", "project" to "پروژه")

data class Level(val fa: String, val icon: DivanIcon, val tone: Tone)

val LEVEL = mapOf(
    "urgent" to Level("فوری", DivanIcon.URGENT, Tone.NEG),
    "decision" to Level("تصمیم", DivanIcon.LEVEL_DECISION, Tone.WARN),
    "report" to Level("گزارش", DivanIcon.LEVEL_REPORT, Tone.LAPIS),
    "info" to Level("اطلاع", DivanIcon.INFO, Tone.POS),
    "learning" to Level("یادگیری", DivanIcon.LEARNING, Tone.LEARN),
)

fun level(l: String) = LEVEL[l] ?: LEVEL.getValue("info")

val EMPLOYEE_KIND = mapOf(
    "ceo" to "مدیرعامل",
    "manager" to "مدیر",
    "employee" to "کارمند",
    "advisor" to "مشاور کل",
    "overseer" to "ناظر کل",
    "assistant" to "دستیار",
    "inspector" to "بازرس کیفیت",
    "system" to "سیستم",
)

val ACTIVITY = mapOf("working" to "در حال کار", "waiting" to "منتظر", "idle" to "آماده", "sleeping" to "خواب", "error" to "خطا")

val DEPT_ICON = mapOf(
    "TECH" to DivanIcon.SERVER, "GROWTH" to DivanIcon.CHART, "SALES" to DivanIcon.MESSAGES, "PRODUCT" to DivanIcon.DELIVERABLE,
    "FIN" to DivanIcon.TREASURY, "QUANT" to DivanIcon.BUDGET, "AIOPS" to DivanIcon.MODEL, "HR" to DivanIcon.DEPARTMENT, "OVS" to DivanIcon.SEARCH,
)

/** `llm.connections.status` (LLM layer): enabled, disabled or quota_exhausted. */
val CONNECTION_STATUS = mapOf(
    "enabled" to ("روشن" to Tone.POS),
    "quota_exhausted" to ("سهمیه تمام" to Tone.WARN),
    "disabled" to ("خاموش" to Tone.NEUTRAL),
)

fun actorFa(a: Actor?): String = when {
    a == null -> "—"
    !a.displayFa.isNullOrBlank() -> a.displayFa
    a.kind == "owner" -> "مدیر کل"
    a.kind == "system" -> "سیستم"
    else -> a.code
}

/** Avatar kind of an agent code ("FX-CEO", "FX-TECH-MGR", "HQ-ADV"). */
fun agentKindOf(code: String, kind: String? = null): String = when {
    kind == "owner" -> "owner"
    code == "HQ-ADV" || kind == "advisor" -> "advisor"
    code == "HQ-OVR" || kind == "overseer" -> "overseer"
    code == "HQ-PA" || kind == "assistant" -> "assistant"
    code.endsWith("-CEO") -> "ceo"
    code.endsWith("-MGR") -> "manager"
    else -> kind?.takeIf { it in EMPLOYEE_KIND } ?: "employee"
}

/** Department segment of an agent code ("FX-TECH-MGR" → "TECH"). */
fun deptOf(code: String): String? = code.split('-').getOrNull(1)

/** Charter role keys (the files in agents/roles) as the owner reads them. */
val ROLE_FA = mapOf(
    "ceo" to "مدیرعامل", "manager" to "مدیر", "cto" to "مدیر فنی", "sre" to "مهندس پایداری", "growth" to "مدیر رشد", "sales" to "فروش", "support" to "پشتیبانی",
    "quant" to "کوانت", "advisor" to "مشاور کل", "overseer" to "ناظر کل", "assistant" to "دستیار", "inspector" to "بازرس کیفیت", "fact_checker" to "راستی‌آزما",
    "security_analyst" to "تحلیلگر امنیت", "aiops_head" to "مدیر عملیات AI", "ai_safety" to "ایمنی AI", "hub_platform_sre" to "پایداری پلتفرم هاب",
)

fun roleFa(r: String): String = if (r == "all") "همه" else ROLE_FA[r] ?: r

val DEPT_FA = mapOf(
    "TECH" to "فنی", "GROWTH" to "رشد", "SALES" to "فروش", "PRODUCT" to "محصول", "FIN" to "مالی", "QUANT" to "کوانت", "AIOPS" to "عملیات AI", "HR" to "منابع انسانی", "OVS" to "نظارت",
)
