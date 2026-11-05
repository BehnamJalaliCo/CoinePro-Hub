package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.DEPT_FA
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.AffiliateGap
import com.coinepro.hq.core.net.DecisionImpact
import com.coinepro.hq.core.net.Journey
import com.coinepro.hq.core.net.JourneyStage
import com.coinepro.hq.core.net.PayRow
import com.coinepro.hq.core.net.PayReconcile
import com.coinepro.hq.core.net.PersonaScore
import com.coinepro.hq.core.net.RevCohort
import com.coinepro.hq.core.net.SalesLead
import com.coinepro.hq.core.net.SalesPersona
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt

// Contract §33 ⟨1.15⟩ in the owner's words: the payment states, the money units, a decision's impact chip, a lead's stage, the journey
// and the message test. Pure functions: the unit tests read them directly.

// ---------------------------------------------------------------- figures --
/** A money figure in Latin digits with a thousands separator: whole when it is whole, else two decimals ("1,240", "12.50"). */
fun moneyFigure(v: Double): String {
    val whole = abs(v - v.roundToInt()) < 0.005
    return String.format(Locale.US, if (whole) "%,.0f" else "%,.2f", v)
}

/** "1,240 USDT"; a dash when there is no figure. */
fun usdtText(v: Double?): String = if (v == null) "—" else moneyFigure(v) + " USDT"

/** A signed figure: "+120", "−22" (the true minus sign). */
fun signedFigure(v: Double): String = (if (v < 0) "−" else "+") + moneyFigure(abs(v))

/** A rate given as a fraction (0.04) or already a percent (4): "4%". */
fun rateText(v: Double?, digits: Int = 0): String =
    if (v == null) "—" else String.format(Locale.US, "%.${digits}f%%", if (abs(v) <= 1.0) v * 100 else v)

/** A cohort's retention values as percents, whichever way the hub writes them (all at most 1 means fractions). */
fun retainedPercents(c: RevCohort): List<Double> = if (c.retained.all { it <= 1.0 }) c.retained.map { it * 100 } else c.retained

/** A hash or address in short form: «0x12ab…9f3c». The full text is never needed to recognise it. */
fun shortHash(s: String?): String = when {
    s.isNullOrBlank() -> "—"
    s.length <= 14 -> s
    else -> s.take(6) + "…" + s.takeLast(4)
}

// --------------------------------------------------------------- payments --
/** matched · ledger_only · chain_only · amount_mismatch · pending_chain, in the owner's words. */
val PAY_STATUS_FA: Map<String, Pair<String, Tone>> = mapOf(
    "matched" to ("تطبیق‌شده" to Tone.POS),
    "ledger_only" to ("بی‌پول" to Tone.NEG),
    "chain_only" to ("بی‌مشتری" to Tone.WARN),
    "amount_mismatch" to ("مبلغ کم" to Tone.WARN),
    "pending_chain" to ("در انتظار زنجیره" to Tone.LAPIS),
)

/** The problems first, the matched last. */
val PAY_STATUS_ORDER = listOf("ledger_only", "chain_only", "amount_mismatch", "pending_chain", "matched")

fun payStatusFa(s: String?): String = PAY_STATUS_FA[s]?.first ?: "نامشخص"
fun payStatusTone(s: String?): Tone = PAY_STATUS_FA[s]?.second ?: Tone.SILVER

/** What each state means, in one plain line (shown when a chip is chosen). */
val PAY_STATUS_HINT_FA = mapOf(
    "matched" to "پرداخت هم در دفتر شرکت هست و هم روی زنجیره، با مبلغ درست.",
    "ledger_only" to "شرکت پرداخت را تأیید کرده، ولی پولی روی زنجیره پیدا نشد.",
    "chain_only" to "پولی روی زنجیره رسیده، ولی مشتری‌ای برایش در دفتر شرکت نیست.",
    "amount_mismatch" to "پول رسیده، ولی کمتر از قیمت بسته است.",
    "pending_chain" to "تراکنش هنوز به تعداد تأیید لازم نرسیده؛ بعداً دوباره خوانده میشود.",
)

val PAY_NETWORK_FA = mapOf("bsc_usdt" to "BSC", "trc20_usdt" to "TRON")
fun payNetworkFa(n: String?): String? = n?.let { PAY_NETWORK_FA[it] ?: it }

val PAY_SOURCE_KIND_FA = mapOf("ledger" to "دفتر خود شرکت", "chain" to "زنجیره‌ی عمومی")
val PAY_SOURCE_STATE_FA: Map<String, Pair<String, Tone>> = mapOf(
    "ok" to ("سالم" to Tone.POS), "error" to ("خطا" to Tone.NEG), "not_configured" to ("تنظیم نشده" to Tone.SILVER),
)

/** How many rows of each status, for the filter chips. */
fun payCounts(rows: List<PayRow>): Map<String, Int> = rows.groupingBy { it.status }.eachCount()

/** A day of the reconcile list: how many of its payments matched, and how many did not. */
fun reconcileProblems(r: PayReconcile): Int = r.ledgerOnly + r.chainOnly + r.amountMismatch

/** «۱۲ از ۱۴ تطبیق شد» for a reconcile day; null when the day had no payment at all. */
fun reconcileLine(r: PayReconcile): String? {
    val total = maxOf(r.ledgerCount, r.chainCount, r.matched + reconcileProblems(r))
    return if (total == 0) null else "${r.matched} از $total تطبیق شد"
}

val REVENUE_SOURCE_FA = mapOf(
    "affiliate" to "کمیسیون افیلیت", "payments" to "پرداخت مشتریان", "payment" to "پرداخت مشتریان", "crypto" to "پرداخت مشتریان", "chain" to "پرداخت مشتریان",
)
fun revenueSourceFa(s: String): String = REVENUE_SOURCE_FA[s] ?: s

/** The kinds of what one output costs (§33.3 `cost_per_output`). */
val COST_PER_FA = mapOf("line_run" to "هر اجرای خط تولید", "deliverable" to "هر خروجی", "order" to "هر فرمان")

// ------------------------------------------------------------------ usage --
fun usagePeriodFa(p: String?): String = when (p) { "week" -> "هفتگی"; "day" -> "روزانه"; else -> "گزارش" }

/** A change since the last period as words: «۱۲٪ بیشتر از قبل»; null when the hub gave none. */
fun vsPrevFa(pct: Double?): String? = when {
    pct == null -> null
    abs(pct) < 1.0 -> "تقریباً مثل دوره‌ی قبل"
    pct > 0 -> String.format(Locale.US, "%.0f%% بیشتر از دوره‌ی قبل", pct)
    else -> String.format(Locale.US, "%.0f%% کمتر از دوره‌ی قبل", abs(pct))
}

fun domainFa(d: String): String = DOMAIN_FA[d.lowercase()] ?: DEPT_FA[d.uppercase()] ?: d
private val DOMAIN_FA = mapOf(
    "content" to "محتوا", "growth" to "رشد", "tech" to "فنی", "media" to "رسانه", "sales" to "فروش", "fin" to "مالی", "legal" to "حقوقی",
    "ops" to "عملیات", "research" to "پژوهش", "support" to "پشتیبانی", "hr" to "منابع انسانی", "oversight" to "نظارت", "advisor" to "مشاور",
)

// ------------------------------------------------------------------ leads --
val LEAD_STAGE_FA = mapOf("new" to "تازه", "contacted" to "تماس گرفته شد", "qualified" to "واجد شرایط", "trial" to "آزمایشی", "paid" to "پرداخت کرد", "lost" to "از دست رفت")
fun leadStageFa(key: String, title: String? = null): String = title?.takeIf { it.isNotBlank() } ?: LEAD_STAGE_FA[key] ?: key

fun leadStageTone(key: String): Tone = when (key) {
    "paid" -> Tone.POS
    "lost" -> Tone.SILVER
    "trial", "qualified" -> Tone.GOLD
    "contacted" -> Tone.LAPIS
    else -> Tone.NEUTRAL
}

val LEAD_SOURCE_FA = mapOf("support" to "پشتیبانی", "telegram" to "تلگرام", "site" to "سایت", "payment" to "پرداخت", "referral" to "معرفی", "manual" to "دستی")
fun leadSourceFa(s: String): String = LEAD_SOURCE_FA[s] ?: s

val LEAD_EVENT_FA = mapOf("created" to "ساخته شد", "stage" to "مرحله عوض شد", "note" to "یادداشت", "contact" to "تماس", "draft" to "پیش‌نویس پیگیری", "payment" to "پرداخت", "reminder" to "یادآوری")
fun leadEventFa(k: String): String = LEAD_EVENT_FA[k] ?: k

/** A lead's title: its display name, else its pseudonym. */
fun leadTitle(l: SalesLead): String = l.nameFa?.takeIf { it.isNotBlank() } ?: l.contact.ifBlank { l.ref }

/** The leads still open (neither paid nor lost), the ones with the nearest next step first. */
fun openLeads(list: List<SalesLead>): List<SalesLead> =
    list.filter { it.stage != "paid" && it.stage != "lost" }.sortedWith(compareBy({ it.nextAt ?: "9999" }, { it.createdAt }))

val GAP_STATE_FA: Map<String, Pair<String, Tone>> = mapOf("open" to ("باز" to Tone.WARN), "followup" to ("در پیگیری" to Tone.LAPIS), "paid" to ("تسویه شد" to Tone.POS))

/** The gap of an affiliate month in USDT (due minus received; never below zero). */
fun gapUsdt(g: AffiliateGap): Double = (g.dueUsdt - g.receivedUsdt).coerceAtLeast(0.0)

// --------------------------------------------------------------- decisions --
/** The impact over its horizon, as a monthly figure (the cards are compared on one scale). Revenue counts for, cost against. */
fun impactMonthly(i: DecisionImpact): Double {
    val net = (i.revenueUsdt ?: 0.0) - (i.costUsd ?: 0.0)
    return if (i.horizonDays <= 0) net else net * 30.0 / i.horizonDays
}

/** «+120 USDT/ماه»: what the card moves, in the unit the hub gave (revenue in USDT; a cost alone in USD), over its horizon. */
fun impactText(i: DecisionImpact): String {
    val rev = i.revenueUsdt
    val cost = i.costUsd
    val (value, unit) = when {
        rev != null && cost == null -> rev to "USDT"
        rev == null && cost != null -> -cost to "USD"
        rev != null && cost != null -> (rev - cost) to "USDT"
        else -> return "—"
    }
    val per = when {
        i.horizonDays in 28..31 -> "/ماه"
        i.horizonDays == 7 -> "/هفته"
        i.horizonDays == 1 -> "/روز"
        else -> " در ${i.horizonDays} روز"
    }
    return signedFigure(value) + " " + unit + per
}

val IMPACT_KIND_FA = mapOf("measured" to "اندازه‌گیری‌شده", "estimate" to "تخمین")

/** Whether a card has a figure to show at all (an impact with neither revenue nor cost is nothing). */
fun hasImpact(i: DecisionImpact?): Boolean = i != null && (i.revenueUsdt != null || i.costUsd != null)

/** The sort «بیشترین اثر»: the biggest monthly figure either way first, a card with none last. */
fun impactSortKey(i: DecisionImpact?): Double = if (hasImpact(i)) -abs(impactMonthly(i!!)) else Double.MAX_VALUE

// ---------------------------------------------------------------- parallel --
val PART_STATE_FA: Map<String, Pair<String, Tone>> = mapOf(
    "queued" to ("در صف" to Tone.SILVER), "working" to ("در حال کار" to Tone.GOLD), "waiting" to ("منتظر" to Tone.LAPIS),
    "done" to ("تمام شد" to Tone.POS), "failed" to ("ناموفق" to Tone.NEG),
)
val MERGE_STATE_FA: Map<String, Pair<String, Tone>> = mapOf(
    "waiting" to ("منتظر بخش‌ها" to Tone.SILVER), "working" to ("در حال ادغام" to Tone.GOLD), "done" to ("ادغام شد" to Tone.POS), "failed" to ("ناموفق" to Tone.NEG),
)

/** A progress that may be a fraction or a percent, as a percent 0..100. */
fun progressPercent(v: Double?): Double? = v?.let { if (it <= 1.0) it * 100 else it }?.coerceIn(0.0, 100.0)

/** The parts finished, as «2 از 3». */
fun partsDoneLine(parts: List<com.coinepro.hq.core.net.ReportPart>): String = "${parts.count { it.state == "done" }} از ${parts.size}"

// ------------------------------------------------------------------ journey --
/** The index of the current stage in a journey (the first stage not yet reached when `current` names none). */
fun journeyCurrentIndex(j: Journey): Int {
    val i = j.stages.indexOfFirst { it.key == j.current }
    if (i >= 0) return i
    val firstOpen = j.stages.indexOfFirst { it.reachedAt == null }
    return if (firstOpen < 0) j.stages.lastIndex else firstOpen
}

/** How many stages are behind the company. */
fun journeyReached(j: Journey): Int = j.stages.count { it.reachedAt != null }

/** Where a stage's evidence opens in the app; null when the evidence has no page of its own. */
fun evidenceRoute(company: String, s: JourneyStage): String? {
    val e = s.evidence ?: return null
    return when (e.kind) {
        "company" -> "companies/$company"
        "server" -> "companies/$company/servers"
        "line", "line_run" -> if (e.ref.startsWith("LN-")) "lines/${e.ref}" else "companies/$company/lines"
        "deliverable", "output" -> "outputs/${e.ref}"
        "lead" -> if (e.ref.startsWith("LD-")) "leads/${e.ref}" else "companies/$company/sales"
        "payment", "revenue", "revenue_board" -> "companies/$company/money"
        "analytics", "connection" -> "companies/$company/connections"
        else -> "companies/$company"
    }
}

val EVIDENCE_KIND_FA = mapOf(
    "company" to "شرکت", "server" to "سرور", "line" to "خط تولید", "line_run" to "اجرای خط", "deliverable" to "خروجی", "output" to "خروجی", "lead" to "سرنخ",
    "payment" to "پرداخت", "revenue" to "درآمد", "revenue_board" to "درآمد", "analytics" to "آمار", "connection" to "اتصال",
)

// ---------------------------------------------------------------- personas --
/** A message-test score: 70 and over reads well, 40 to 69 so-so, below that badly. */
fun scoreTone(score: Double): Tone = when {
    score >= 70 -> Tone.POS
    score >= 40 -> Tone.WARN
    else -> Tone.NEG
}

/** The persona a score belongs to, by id first and then by name; null when neither is in the list. */
fun personaOf(list: List<SalesPersona>, s: PersonaScore): SalesPersona? {
    val key = (s.persona as? kotlinx.serialization.json.JsonPrimitive)?.content.orEmpty()
    return list.firstOrNull { (it.id).content == key } ?: list.firstOrNull { it.nameFa == key }
}

/** How many of the personas would act on the message. */
fun wouldActCount(results: List<PersonaScore>): Int = results.count { it.wouldAct }

val PERSONA_SOURCE_FA = mapOf("owner" to "از طرف تو", "kb_suggested" to "پیشنهاد دانش شرکت")
