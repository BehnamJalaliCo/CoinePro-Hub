package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.ClaudeAccount
import com.coinepro.hq.core.net.Limits
import com.coinepro.hq.core.net.Notification
import com.coinepro.hq.core.net.Office
import com.coinepro.hq.core.net.SessionCard
import com.coinepro.hq.core.net.TodayMeter
import java.time.ZoneId

// ⟨1.0.1⟩ Part C, the look, in the owner's words (the web's lib/api/v55.ts and lib/notify.ts, rule for rule): the command sheet's
// templates and the words of its order, the ready answers of a question, the three states of a session, the three levels of a
// notification and a machine-written title said in Persian, and the limits block of the treasury. Pure functions: the unit tests
// read them.

// ==================================================================================================== C2.1 the command ==
/** A company the owner picked by its mark: its code for the hub, its name for the words. */
data class CommandCompany(val code: String, val nameFa: String)

/** A template only fills the starting text; the path is the same one path. */
data class CommandTemplate(val key: String, val label: String, val make: String)

val COMMAND_TEMPLATES = listOf(
    CommandTemplate("reel", "ریلز اینستاگرام", "یک ریلز اینستاگرام بساز: "),
    CommandTemplate("motion", "موشن‌گرافی", "یک موشن‌گرافی بساز: "),
)

const val COMMAND_FA = "چه میخواهی؟"
const val COMMAND_PLACEHOLDER_FA = "بنویس چه میخواهی؛ درباره‌ی هر چیزی"
const val ROUTINE_TEMPLATE_FA = "کارمند ۲۴ ساعته"
const val ROUTINE_PLACEHOLDER_FA = "مثلاً: هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده"

/** «تریدیار», «تریدیار و پرو-چارت», «تریدیار، پرو-چارت و کوینه‌پرو FX». */
fun namesFa(names: List<String>): String = when (names.size) {
    0 -> ""
    1 -> names[0]
    else -> names.dropLast(1).joinToString("، ") + " و " + names.last()
}

/** «برای {شرکت} یک ریلز اینستاگرام بساز: »; with no company picked the holding decides, and the text names none. */
fun templateText(t: CommandTemplate, names: List<String>): String = if (names.isEmpty()) t.make else "برای ${namesFa(names)} ${t.make}"

/** The words of an order that goes to the holding for several companies (or to a hub that takes no company with an order): the
 *  companies named in front, unless the owner's words name them all already. */
fun commandWords(text: String, names: List<String>): String {
    val t = text.trim()
    return if (names.isNotEmpty() && !names.all { t.contains(it) }) "برای ${namesFa(names)}: $t" else t
}

/** «باز کن» is on once there is something to send (the hub takes three letters at least). */
fun commandReady(text: String): Boolean = text.trim().length >= 3

// ======================================================================================= C2.2 / C3 the ready answers ==
const val DECIDE_YOURSELF_FA = "خودت تصمیم بگیر و ادامه بده"
private val QUOTED = Regex("«([^«»]{1,80})»")
private val YA = Regex("\\sیا\\s")
private val TAIL_MARKS = Regex("[؟?.!]+\\s*$")
private val CLAUSE = Regex("[:؛\\n]|[؟?.!]\\s")
private val OPTION = Regex("\\s+یا\\s+|،\\s*")

/**
 * The two or three answers a question offers by itself: the hub's quick replies when the report carries them; else, for a question
 * that names two or three options with «یا», those options (the quoted ones first: «الف»، «ب» یا «پ»). Nothing for an open question.
 */
fun readyAnswers(question: String?, quick: List<String>? = null): List<String> {
    val given = quick.orEmpty().map { it.trim() }.filter { it.isNotEmpty() }
    if (given.isNotEmpty()) return given.take(3)
    val q = question.orEmpty().trim()
    if (q.isEmpty() || !YA.containsMatchIn(q)) return emptyList()
    val quoted = QUOTED.findAll(q).map { it.groupValues[1].trim() }.filter { it.isNotEmpty() }.toList()
    if (quoted.size in 2..3) return quoted
    // «امروز منتشر کنم یا فردا صبح؟» → the clause around «یا», cut at the sentence marks before it.
    val tail = q.replace(TAIL_MARKS, "").split(CLAUSE).lastOrNull().orEmpty()
    val parts = tail.split(OPTION).map { it.trim() }.filter { it.isNotEmpty() }
    return if (parts.size in 2..3 && parts.all { it.length <= 48 }) parts else emptyList()
}

// ============================================================================================== C3.1 the three states ==
/** Three states only: what waits for the owner (his turn, or ready for his approval), what is being worked on (a session stuck on
 *  something that is not his says so in its own line), and what is finished. */
fun state3(badge: String): String = when (badge) {
    "closed" -> "done"
    "your_turn", "ready" -> "waiting"
    else -> "working"
}

val STATE3_FA = mapOf("waiting" to "منتظر تو", "working" to "در کار", "done" to "تمام")

/** «۶ دقیقه منتظر», «۲ ساعت منتظر»: how long something has waited for him (a count in a sentence). */
fun waitedFa(iso: String?, now: Long = HqClock.millis()): String? {
    val t = instant(iso) ?: return null
    val m = ((now - t.toEpochMilli()).coerceAtLeast(0) / 60_000.0).let { Math.round(it) }
    if (m < 1) return "همین الان"
    if (m < 60) return "$m دقیقه منتظر"
    val h = Math.round(m / 60.0)
    return if (h < 48) "$h ساعت منتظر" else "${Math.round(h / 24.0)} روز منتظر"
}

/** «کار ۳ از ۴ ایستاده»: the task that stands still while the session waits; null when its plan is done or it has none. */
fun standingFa(s: SessionCard): String? = if (s.tasks.total > 0 && s.tasks.done < s.tasks.total) "کار ${s.tasks.done + 1} از ${s.tasks.total} ایستاده" else null

/** «کار ۳ از ۴» of a session's card (the one being worked on; a finished plan says its last). */
fun taskLineFa(s: SessionCard): String? =
    if (s.tasks.total <= 0) null else "کار ${minOf(s.tasks.total, s.tasks.done + if (state3(s.badge) == "done") 0 else 1)} از ${s.tasks.total}"

/** What waits for the owner: sessions in his turn or ready for his approval, and the cards for his decision. The same count the
 *  pulse shows. */
fun turnCount(o: Office): Int =
    sortSessions(o.sessions).count { state3(it.badge) == "waiting" } + maxOf(o.approvalsTotal, o.approvals.size)

// ============================================================================================= C3.5 the three levels ==
/** Three levels: «فوری» (red, it rings), «تصمیم» (gold), «خبر» (silent: the hub's report, info and learning together). */
val LEVELS3 = listOf("urgent", "decision", "news")
val LEVEL3_FA = mapOf("urgent" to "فوری", "decision" to "تصمیم", "news" to "خبر")
/** The hub's levels a row of the settings stands for. */
val LEVEL3_OF = mapOf("urgent" to listOf("urgent"), "decision" to listOf("decision"), "news" to listOf("report", "info", "learning"))

fun level3(level: String): String = when (level) { "urgent" -> "urgent"; "decision" -> "decision"; else -> "news" }

/** It wants something of the owner: urgent or a decision, not read yet and not answered. */
fun asksOwner(n: Notification): Boolean = n.readAt == null && n.answer == null && level3(n.level) != "news"

private fun dayOf(millis: Long): java.time.LocalDate = java.time.Instant.ofEpochMilli(millis).atZone(ZoneId.of(OWNER_TZ)).toLocalDate()

/** «امروز», «دیروز», else the date: the day a row belongs to, on the owner's calendar. */
fun dayLabelFa(iso: String?, now: Long = HqClock.millis()): String {
    val t = instant(iso) ?: return "—"
    val day = dayOf(t.toEpochMilli())
    val today = dayOf(now)
    return when (day) {
        today -> "امروز"
        today.minusDays(1) -> "دیروز"
        else -> jDate(iso)
    }
}

private val COMPANY_KEY = Regex("\\bcompany:([A-Z][A-Z0-9]{1,9})\\b")
private val PERIOD = Regex("\\s*\\(\\d{4}-\\d{2}\\)")
private val DOWN = Regex("\\bdown:\\s*([a-z0-9_.-]+(?:\\s*,\\s*[a-z0-9_.-]+)*)", RegexOption.IGNORE_CASE)
private val DISK = Regex("\\bdisk\\s+(\\d+(?:\\.\\d+)?)\\s*%", RegexOption.IGNORE_CASE)
private val CPU_MEM = Regex("\\b(cpu|memory|ram)\\s+(\\d+(?:\\.\\d+)?)\\s*%", RegexOption.IGNORE_CASE)
private val WORD_N = mapOf(1 to "یک", 2 to "دو", 3 to "سه", 4 to "چهار", 5 to "پنج")

/**
 * A title (or a line) the machine wrote, said in Persian: «disk 90.4%» is «دیسک ۹۰٪ پر است», «down: a, b» is «دو سرویس پایین است»,
 * «company:TY» is the company's name, a bare period «(2026-10)» goes. What it does not know it leaves as it is. The raw text stays
 * one tap away (the caller shows it when this differs from it).
 */
fun humanize(text: String?, companyName: (String) -> String? = { null }): String {
    if (text.isNullOrEmpty()) return ""
    var t = COMPANY_KEY.replace(text) { m -> companyName(m.groupValues[1]) ?: m.groupValues[1] }
    t = PERIOD.replace(t, "")
    t = DOWN.replace(t) { m -> val n = m.groupValues[1].split(",").size; "${WORD_N[n] ?: faDigits(n.toString())} سرویس پایین است" }
    t = DISK.replace(t) { m -> "دیسک ${faDigits(Math.round(m.groupValues[1].toDouble()).toString())}٪ پر است" }
    t = CPU_MEM.replace(t) { m -> "${if (m.groupValues[1].equals("cpu", true)) "پردازنده" else "حافظه"} ${faDigits(Math.round(m.groupValues[2].toDouble()).toString())}٪ پر است" }
    if (t != text) t = t.replace(Regex("\\s*[—–]\\s*"), "؛ ").replace(Regex("\\s*;\\s*"), "؛ ").replace(Regex("\\s*,\\s*"), "، ").replace(Regex("؛\\s*؛"), "؛").replace(Regex("\\s{2,}"), " ").trim()
    return t
}

// ================================================================================================= C3.6 the limits ==
/** «۲ ساعت و ۱۰ دقیقه دیگر», «۴۰ دقیقه دیگر», «کمتر از یک دقیقه دیگر»; null once the moment has passed. A count in a sentence. */
fun inFa(iso: String?, now: Long = HqClock.millis()): String? {
    val t = instant(iso) ?: return null
    val ms = t.toEpochMilli() - now
    if (ms <= 0) return null
    val m = Math.round(ms / 60_000.0)
    if (m < 1) return "کمتر از یک دقیقه دیگر"
    val h = m / 60
    val r = m % 60
    return when {
        h == 0L -> "$m دقیقه دیگر"
        h >= 24 -> { val d = h / 24; val hh = h % 24; if (hh > 0) "$d روز و $hh ساعت دیگر" else "$d روز دیگر" }
        r > 0 -> "$h ساعت و $r دقیقه دیگر"
        else -> "$h ساعت دیگر"
    }
}

/** The earliest reset among the accounts that are full: when the queue moves again. */
fun queueOpensAt(l: Limits): String? = l.accounts.filter { it.state == "full" && it.resetsAt != null }.mapNotNull { it.resetsAt }.minOrNull()

/** The newest moment any account's figure was read; null when none has been read yet. */
fun limitsReadAt(l: Limits): String? = l.accounts.mapNotNull { it.observedAt }.maxOrNull()

/** One account's share as the ring draws it: a full one is whole whatever its figure says; one that is off draws nothing. */
fun accountShare(a: ClaudeAccount): Float? = when (a.state) {
    "off" -> null
    "full" -> maxOf(a.utilization ?: 1.0, 1.0).toFloat()
    else -> a.utilization?.toFloat()
}

/** «62%» in the middle of an account's ring; «—» when the hub has not read it. */
fun accountPercent(a: ClaudeAccount): String = a.utilization?.let { "${Math.round(it.coerceIn(0.0, 1.0) * 100)}%" } ?: "—"

/** Today's share of the daily cap (it may pass 1): the hub's own figure, else spent over cap. */
fun meterShare(t: TodayMeter): Double = t.share ?: if (t.cap > 0) t.spent.toDouble() / t.cap else 0.0

/** `calm` · `warm` (past 70 %) · `near` (past 90 %) · `full`: the hub's own word, else read from the share. */
fun meterState(t: TodayMeter): String = t.state?.takeIf { it in METER_FA } ?: meterShare(t).let { s ->
    when { s >= 1.0 -> "full"; s >= 0.9 -> "near"; s >= 0.7 -> "warm"; else -> "calm" }
}

val METER_FA = mapOf("calm" to "آرام", "warm" to "از ۷۰٪ گذشت", "near" to "نزدیک سقف", "full" to "سقف پر شد")

/** «هر دو اکانت پر است» for two, «همه‌ی اکانت‌ها پر است» for any other number (the accounts are data, never a fixed two). */
fun allFullFa(count: Int): String = if (count == 2) "هر دو اکانت پر است" else "همه‌ی اکانت‌ها پر است"

/** «تا آخر ماه میرسم یا نه»: this month's pace against its cap. `pos` · `warn` · `neg`, and the sentence. The month is the hub's own
 *  (a calendar month, UTC). Null without a cap. */
fun monthVerdict(used: Long, limit: Long?, now: Long = HqClock.millis()): Pair<String, String>? {
    if (limit == null || limit <= 0) return null
    val date = java.time.Instant.ofEpochMilli(now).atZone(java.time.ZoneOffset.UTC).toLocalDate()
    val day = date.dayOfMonth
    val days = date.lengthOfMonth()
    val perDay = used.toDouble() / maxOf(1, day)
    val end = perDay * days
    return when {
        used >= limit -> "neg" to "سقف این ماه پر شده است."
        end > limit -> "neg" to "با این آهنگ، حدود روز ${minOf(days, Math.ceil(limit / perDay).toInt())} ماه به سقف میرسی."
        end > limit * 0.9 -> "warn" to "با این آهنگ، آخر ماه به سقف نزدیک میشوی."
        else -> "pos" to "با این آهنگ، آخر ماه زیر سقف میمانی."
    }
}
