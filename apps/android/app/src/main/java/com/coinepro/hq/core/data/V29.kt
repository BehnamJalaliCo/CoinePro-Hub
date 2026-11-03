package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.DEPT_FA
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.roleFa
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.net.DayValue
import com.coinepro.hq.core.net.Fix
import com.coinepro.hq.core.net.OrderRoute29
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToLong
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull

// Contract §29 ⟨1.11⟩ in the owner's words: the states, blockers, fixes, outputs, connections and employee states as plain Persian
// (§29.7: no refs, no service or tool names, no English terms in what the app writes), and the small rules the screens share (the
// preview line, a KPI's move, a figure, the long voice's chunks). Pure functions: the unit tests read them directly.

/** An order's state (§29.2) in words and its tone. */
val ORDER_STATE_FA: Map<String, Pair<String, Tone>> = mapOf(
    "received" to ("رسید" to Tone.NEUTRAL),
    "planned" to ("برنامه‌اش نوشته شد" to Tone.LAPIS),
    "in_progress" to ("در کار" to Tone.GOLD),
    "waiting" to ("منتظر" to Tone.WARN),
    "blocked" to ("گیر کرده" to Tone.NEG),
    "delivered" to ("تحویل شد" to Tone.POS),
    "failed" to ("انجام نشد" to Tone.NEG),
    "cancelled" to ("لغو شد" to Tone.SILVER),
)

fun orderStateFa(state: String?): String = ORDER_STATE_FA[state]?.first ?: "رسید"
fun orderStateTone(state: String?): Tone = ORDER_STATE_FA[state]?.second ?: Tone.NEUTRAL

/** An order that has ended: its end summary is filled (§29.2). */
fun orderEnded(state: String?): Boolean = state == "delivered" || state == "failed" || state == "cancelled"

/** A blocker's kind in words, when the hub sent no title. */
val BLOCKER_FA = mapOf(
    "no_employee" to "کسی برای این کار نیست",
    "hiring_closed" to "استخدام بسته است",
    "locked" to "شرکت یا کار قفل است",
    "series_unsealed" to "برنامه‌ی انتشار هنوز مُهر نشده",
    "budget" to "بودجه‌ی این کار کم آمد",
    "player_down" to "مدلی که خواستی الان در دسترس نیست",
    "connection_missing" to "اتصالی که لازم است وصل نیست",
    "no_progress" to "مدتی است پیشرفتی نیست",
    "talk_loop" to "حرف زیاد شد و خروجی نداد",
)

fun blockerFa(kind: String, title: String = ""): String = title.ifBlank { BLOCKER_FA[kind] ?: "کار ایستاده است" }

/** A fix's button, when the hub sent no label. */
val FIX_FA = mapOf(
    "hire" to "استخدام کن",
    "hiring.open" to "استخدام را باز کن",
    "lock.open" to "باز کن",
    "series.seal" to "مُهر برنامه",
    "series.propose" to "برنامه‌ی انتشار بخواه",
    "budget.add" to "بودجه بده",
    "player.auto" to "با مدل خودکار ادامه بده",
    "connection.guide" to "وصل کن",
    "media.on" to "ابزار رسانه را روشن کن",
)

fun fixFa(f: Fix): String = f.labelFa.ifBlank { FIX_FA[f.action] ?: "درستش کن" }

/** How a fix is done: posted to the order (§29.2), posted with the passkey, or opened where the owner does it (a card, a guide). */
enum class FixWay { POST, SIGNED, OPEN }

fun fixWay(f: Fix): FixWay = when (f.action) {
    "hiring.open" -> FixWay.SIGNED
    "series.seal" -> if (Refs.prefix(f.target) == "D") FixWay.OPEN else FixWay.SIGNED
    "lock.open", "connection.guide", "series.propose", "media.on" -> FixWay.OPEN
    else -> FixWay.POST
}

/** Where an opening fix goes (the company of the order, the group or the check gives [company]). */
fun fixRoute(f: Fix, company: String?): String? {
    val t = f.target?.trim()?.ifBlank { null }
    return when (f.action) {
        "series.seal" -> if (Refs.prefix(t) == "D") "cartable/$t" else "series"
        "series.propose" -> "series"
        "media.on" -> "studio"
        "lock.open" -> when {
            Refs.prefix(t) == "H" -> "oversight"
            company != null -> "companies/$company"
            else -> "control"
        }
        "connection.guide" -> {
            // The target is the kind, or `CODE/kind` / `CODE:kind`.
            val parts = t?.split('/', ':')?.filter { it.isNotBlank() }.orEmpty()
            val co = if (parts.size >= 2) parts[0] else company
            val kind = parts.lastOrNull()
            when {
                co == null -> null
                kind != null -> "companies/$co/connections/$kind"
                else -> "companies/$co/connections"
            }
        }
        "hire" -> company?.let { "companies/$it/people" }
        "hiring.open" -> "settings"
        else -> null
    }
}

/** What the secretary may make (§29.4). */
val OUTPUT_KIND_FA = mapOf(
    "post" to "پست", "reel" to "ریلز", "story" to "استوری", "article" to "مقاله", "report" to "گزارش", "plan" to "برنامه",
    "code" to "کد", "answer" to "پاسخ", "other" to "خروجی",
)

fun outputKindFa(kind: String?): String = OUTPUT_KIND_FA[kind] ?: "خروجی"

/**
 * The secretary's line (§29.4): the hub's own words when it sent them; otherwise built from the route the same way:
 * «→ تریدیار/رسانه + IG-Hub؛ خروجی: 3 ریلز؛ بودجه: 400K واحد مصرف». [name] gives a company's name, [dept] a department's.
 */
fun routeLineFa(r: OrderRoute29, name: (String) -> String, dept: (String) -> String = { DEPT_FA[it] ?: it }): String {
    if (r.previewFa.isNotBlank()) return r.previewFa
    val first = r.companies.firstOrNull()?.let { co -> name(co) + (r.department?.let { "/" + dept(it) } ?: "") } ?: "هلدینگ"
    val with = r.collaborators.filter { it !in r.companies.take(1) }.joinToString(" + ") { name(it) }
    val out = (r.count?.let { "$it " } ?: "") + outputKindFa(r.outputKind)
    return buildString {
        append("→ ").append(first)
        if (with.isNotBlank()) append(" + ").append(with)
        append("؛ خروجی: ").append(out)
        r.budgetTokens?.let { append("؛ بودجه: ").append(tokens(it)).append(" واحد مصرف") }
        if (r.mode == "council") append("؛ با شورا")
    }
}

/** Whom a rule applies to (§29.3): everyone, the overseer, some roles or some companies. */
fun appliesToFa(e: JsonElement?, name: (String) -> String = com.coinepro.hq.core.link.CompanyNames::of): String {
    fun list(k: String): List<String> = ((e as? JsonObject)?.get(k) as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
    return when {
        e is JsonPrimitive && e.contentOrNull == "all" -> "برای همه"
        e is JsonPrimitive && e.contentOrNull == "overseer" -> "برای ناظر"
        list("roles").isNotEmpty() -> "برای " + list("roles").joinToString("، ") { roleFa(it) }
        list("companies").isNotEmpty() -> "برای " + list("companies").joinToString("، ") { name(it) }
        else -> "برای همه"
    }
}

val RULE_STATUS_FA = mapOf("proposed" to "منتظر مُهر", "sealed" to "مُهر شد؛ اجرا میشود", "retired" to "بازنشسته")

/** An employee's state (§29.14) in words and its tone. */
val EMPLOYEE_STATE_FA: Map<String, Pair<String, Tone>> = mapOf(
    "idle" to ("آماده" to Tone.SILVER),
    "thinking" to ("در حال فکر" to Tone.LAPIS),
    "working" to ("در حال کار" to Tone.GOLD),
    "waiting" to ("منتظر" to Tone.WARN),
    "stuck" to ("گیر کرده" to Tone.NEG),
    "done" to ("امروز تحویل داد" to Tone.POS),
)

/** The state to show: the hub's (§29.14), or one read from the older `activity` (a hub before ⟨1.11⟩). */
fun employeeStateOf(state: String?, activity: String?): String = state?.takeIf { it in EMPLOYEE_STATE_FA } ?: when (activity) {
    "working" -> "working"
    "waiting" -> "waiting"
    "error" -> "stuck"
    else -> "idle"
}

fun employeeStateFa(state: String): String = EMPLOYEE_STATE_FA[state]?.first ?: "آماده"
fun employeeStateTone(state: String): Tone = EMPLOYEE_STATE_FA[state]?.second ?: Tone.SILVER

/** The medallion's ring for a state (the avatar draws working, waiting and error). */
fun avatarStateOf(state: String): String = when (state) {
    "thinking", "working" -> "working"
    "waiting" -> "waiting"
    "stuck" -> "error"
    else -> "idle"
}

/** A connection's kind (§29.12) in Persian. */
val CONNECTION_KIND_FA = mapOf(
    "search_console" to "سرچ کنسول گوگل", "ga4" to "گوگل آنالیتیکس", "instagram" to "اینستاگرام", "telegram" to "تلگرام",
    "youtube" to "یوتیوب", "x" to "ایکس", "pagespeed" to "سرعت سایت", "trends" to "ترندهای گوگل", "bing" to "بینگ",
    "play_console" to "کنسول گوگل‌پلی",
)

fun connectionKindFa(kind: String, label: String = ""): String = label.ifBlank { CONNECTION_KIND_FA[kind] ?: kind }

val CONNECTION_STATE_FA: Map<String, Pair<String, Tone>> = mapOf(
    "connected" to ("وصل" to Tone.POS),
    "not_connected" to ("وصل نیست" to Tone.NEUTRAL),
    "error" to ("خطا دارد" to Tone.NEG),
)

/** A connection's daily figure (its key) in Persian; an unknown key stays as it came (Latin, isolated by the screen). */
val METRIC_FA = mapOf(
    "impressions" to "نمایش", "clicks" to "کلیک", "ctr" to "نرخ کلیک", "position" to "جایگاه میانگین", "sessions" to "بازدید",
    "users" to "کاربر", "new_users" to "کاربر تازه", "conversions" to "تبدیل", "followers" to "دنبال‌کننده", "reach" to "دسترسی",
    "views" to "بازدید", "likes" to "پسند", "comments" to "نظر", "shares" to "اشتراک", "saves" to "ذخیره", "subscribers" to "مشترک",
    "members" to "عضو", "posts" to "پست", "score" to "امتیاز", "lcp_ms" to "بارگذاری اصلی", "installs" to "نصب", "rating" to "امتیاز",
    "revenue" to "درآمد", "interest" to "علاقه‌ی جست‌وجو",
)

fun metricFa(key: String): String = METRIC_FA[key] ?: key

val RUN_STATE_FA: Map<String, Pair<String, Tone>> = mapOf(
    "queued" to ("در صف" to Tone.NEUTRAL),
    "done" to ("انجام شد" to Tone.POS),
    "failed" to ("انجام نشد" to Tone.NEG),
    "skipped" to ("رد شد" to Tone.SILVER),
)

val SUGGESTION_SOURCE_FA = mapOf("council" to "از شورای مشاوران", "group" to "از کارگروه", "advisor" to "از مشاور کل")

/** A council member's role (§29.8). */
val COUNCIL_ROLE_FA = mapOf("captain" to "کاپیتان", "researcher" to "پژوهشگر", "numbers" to "حساب و عدد", "devil" to "منتقد")

/** A figure as Latin text: a whole number with thousands separators, a fraction with up to two decimals, a percent unit as `%`;
 *  a string as it is; nothing as a dash. */
fun figureText(e: JsonElement?, unit: String = ""): String {
    val p = e as? JsonPrimitive ?: return "—"
    if (e is JsonNull) return "—"
    if (p.isString) return p.content.ifBlank { "—" } + unitSuffix(unit)
    if (p.booleanOrNull != null) return p.content
    val d = p.doubleOrNull ?: return p.content
    return numberText(d, unit)
}

fun numberText(d: Double, unit: String = ""): String {
    if (!d.isFinite()) return "—"
    // A `percent` figure may come as a fraction (0..1), as the contract's shares do; `%` is already a percent.
    val v = if (unit == "percent" && abs(d) <= 1.0) d * 100 else d
    val body = when {
        abs(v - v.roundToLong()) < 1e-9 -> String.format(Locale.US, "%,d", v.roundToLong())
        abs(v) >= 100 -> String.format(Locale.US, "%,.0f", v)
        abs(v) >= 10 -> String.format(Locale.US, "%,.1f", v)
        else -> String.format(Locale.US, "%,.2f", v).trimEnd('0').trimEnd('.')
    }
    return body + unitSuffix(unit)
}

private fun unitSuffix(unit: String): String = when (unit) {
    "", "count", "number" -> ""
    "%", "percent" -> "%"
    else -> " $unit"
}

/** A KPI's move over its series: the first and the last day that have a figure, and the change in percent of the first (null when
 *  there are not two figures, or the first is zero). */
data class KpiMove(val first: Double, val last: Double, val pct: Double?)

fun kpiMove(series: List<DayValue>): KpiMove? {
    val xs = series.mapNotNull { it.value }
    if (xs.size < 2) return null
    val a = xs.first(); val b = xs.last()
    return KpiMove(a, b, if (a == 0.0) null else (b - a) / abs(a) * 100)
}

/** "+12%" / "−4%" (Latin, with a real minus). */
fun moveText(pct: Double): String {
    val r = Math.round(pct)
    return when {
        r > 0 -> "+$r%"
        r < 0 -> "−${-r}%"
        else -> "0%"
    }
}

/** §29.5 the long voice's rules on the phone. */
object LongVoiceRules {
    /** After a minute of dictation the audio goes to the hub (the phone's recogniser is for short words). */
    const val PHONE_LIMIT_S = 60.0
    /** One chunk of audio: at most 90 s by contract; cut a little earlier so a slow stop never passes it. */
    const val CHUNK_S = 85.0
    /** The hub's `STT_SESSION_MAX_S` default: 20 minutes. */
    const val MAX_S = 1200.0

    /** The recogniser's quiet end (nothing more heard, a pause) restarts it; anything else is a failure. */
    fun restartAfter(code: Int): Boolean = code == 7 /* ERROR_NO_MATCH */ || code == 6 /* ERROR_SPEECH_TIMEOUT */

    /** How many chunks a recording of [seconds] makes. */
    fun chunks(seconds: Double): Int = if (seconds <= 0) 0 else kotlin.math.ceil(seconds / CHUNK_S).toInt()

    /** The text so far and the next piece the recogniser heard, joined with one space. */
    fun join(text: String, piece: String): String {
        val a = text.trimEnd(); val b = piece.trim()
        return when {
            b.isEmpty() -> a
            a.isEmpty() -> b
            else -> "$a $b"
        }
    }
}
