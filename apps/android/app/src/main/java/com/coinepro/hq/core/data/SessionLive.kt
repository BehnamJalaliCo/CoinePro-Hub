package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.net.ActivityLine
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.SessionActivity
import com.coinepro.hq.core.net.SessionTask
import com.coinepro.hq.core.net.SessionWorker
import com.coinepro.hq.core.net.StreamEvent
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// Contract §41 ⟨1.23⟩ in the owner's words: «از کجا بدونم کار میکنه، مثل خود کلود کد». The session shows who works now and each step
// as it is taken; when nobody works, why (he is asked, it is stuck with its fix, or it is quiet since a time) and «ادامه بده». The pace
// and the plan's progress are back in the head. Pure functions: the unit tests read them. Prose counts in Persian digits; a clock time
// stays a Latin figure where it is drawn.

/** The lines a session keeps, as the hub does (`last`, ≤ 30). */
const val ACTIVITY_MAX = 30

/** The lines the live panel shows under its head (newest at the bottom). */
const val PANEL_LINES = 4

// ------------------------------------------------------------------ the stream --
/** A `session.activity` event: the order, the new line (a run started, took a step or ended), and how many work on it now. */
data class ActivityEvent(val order: String, val line: ActivityLine?, val working: Int?)

/** A `session.activity` event of the stream as the app reads it (`{order, line, working}`; the order may come as the event's ref). */
fun activityEventOf(e: StreamEvent): ActivityEvent? {
    if (e.type != "session.activity") return null
    val order = e.data["order"].text()?.ifBlank { null } ?: e.ref?.ifBlank { null } ?: return null
    val line = (e.data["line"] as? JsonObject)?.let { runCatching { Api.json.decodeFromJsonElement(ActivityLine.serializer(), it) }.getOrNull() }
        ?.takeIf { it.textFa.isNotBlank() }
    val working = e.data["working"].text()?.trim()?.toDoubleOrNull()?.toInt()?.coerceAtLeast(0)
    return ActivityEvent(order, line, working)
}

private fun JsonElement?.text(): String? = (this as? JsonPrimitive)?.contentOrNull

// ------------------------------------------------------------------ the lines --
private fun millisOf(iso: String): Long? =
    if (iso.isBlank()) null else runCatching { java.time.OffsetDateTime.parse(iso).toInstant().toEpochMilli() }.getOrNull()
        ?: runCatching { java.time.Instant.parse(iso).toEpochMilli() }.getOrNull()

/** One line's identity: the same step heard on the stream and read again from the hub is one line (its time read as an instant). */
fun lineKey(l: ActivityLine): String = "${millisOf(l.at) ?: l.at}|${l.whoFa.trim()}|${l.textFa.trim()}"

/** Two lists of lines as one: each line once, in time order (a line without a time after the timed ones), the newest [max] kept. */
fun mergeLines(a: List<ActivityLine>, b: List<ActivityLine>, max: Int = ACTIVITY_MAX): List<ActivityLine> =
    (a + b).filter { it.textFa.isNotBlank() }.distinctBy(::lineKey).sortedBy { millisOf(it.at) ?: Long.MAX_VALUE }.takeLast(max)

/**
 * A stream event applied to what the screen holds: its line appended at once; nobody working (`working: 0`) makes the session quiet since
 * that line; someone working clears «stuck» and «waiting» (the work moves), and the one who spoke is doing what the line says. A worker
 * the screen does not know yet stands in from the line until the hub's own list comes (the same event refetches it).
 */
fun applyActivity(a: SessionActivity, ev: ActivityEvent): SessionActivity {
    val line = ev.line
    val lines = if (line != null) mergeLines(a.last, listOf(line)) else a.last
    val n = ev.working
    var working = when {
        n == 0 -> emptyList()
        line != null -> a.working.map { w -> if (w.whoFa.trim() == line.whoFa.trim()) w.copy(doingFa = line.textFa) else w }
        else -> a.working
    }
    if (n != null && n > working.size && line != null && line.whoFa.isNotBlank() && working.none { it.whoFa.trim() == line.whoFa.trim() }) {
        working = working + SessionWorker(whoFa = line.whoFa, startedAt = line.at, doingFa = line.textFa)
    }
    val moving = n != null && n > 0
    return a.copy(
        working = working,
        last = lines,
        idleSince = if (n == 0) line?.at?.ifBlank { null } ?: a.idleSince ?: HqClock.now().toString() else a.idleSince,
        waitingFa = if (moving) null else a.waitingFa,
        stuckFa = if (moving) null else a.stuckFa,
    )
}

/** The hub's answer over what the screen holds: its workers and state as they are, the lines of both (a line heard on the stream while
 *  the fetch was on its way is not lost). */
fun mergeFetched(fetched: SessionActivity, held: SessionActivity?): SessionActivity =
    if (held == null) fetched.copy(last = mergeLines(fetched.last, emptyList())) else fetched.copy(last = mergeLines(fetched.last, held.last))

/** A hub before ⟨1.23⟩ (no `/activity`): the panel read from the report: his turn, why it is stuck, or quiet since its last move; the
 *  report's steps as the lines. */
fun activityFromReport(r: OrderReport): SessionActivity {
    val lines = r.steps.map { ActivityLine(it.at, it.whoFa.takeIf { w -> w.trim() != SYSTEM_FA }.orEmpty(), oneLine(it.whatFa)) }
        .filter { it.textFa.isNotBlank() && it.textFa != "-" }
    val last = mergeLines(lines, emptyList())
    return when (sessionBadge(r)) {
        "your_turn" -> SessionActivity(last = last, waitingFa = oneLine(r.turn?.questionFa.orEmpty().ifBlank { briefOf(r).needFa }).ifBlank { "جواب تو" })
        "stuck" -> SessionActivity(last = last, stuckFa = sessionStatusLine(r).ifBlank { "کار جلو نمیرود." })
        else -> SessionActivity(last = last, idleSince = r.updatedAt.ifBlank { null } ?: last.lastOrNull()?.at)
    }
}

// ------------------------------------------------------------------ the panel --
enum class LivePanel { WORKING, WAITING, STUCK, IDLE }

/** What the panel says: someone works; else the owner is asked; else it is stuck; else it is quiet. */
fun livePanelOf(a: SessionActivity): LivePanel = when {
    a.working.isNotEmpty() -> LivePanel.WORKING
    !a.waitingFa.isNullOrBlank() -> LivePanel.WAITING
    !a.stuckFa.isNullOrBlank() -> LivePanel.STUCK
    else -> LivePanel.IDLE
}

/** «مدیر رسانه دارد کار میکند · قدم ۳» (no step before the hub names one). */
fun workingHeadFa(w: SessionWorker): String = buildString {
    append(w.whoFa.trim().ifBlank { "یک همکار" })
    append(" دارد کار میکند")
    if (w.step > 0) append(" · قدم ").append(faNum(w.step))
}

/** The others at work at the same time: «همزمان: نویسنده · قدم ۲»; null when only one works. */
fun othersFa(working: List<SessionWorker>): String? = working.drop(1).takeIf { it.isNotEmpty() }?.joinToString("، ", prefix = "همزمان: ") { w ->
    w.whoFa.trim().ifBlank { "یک همکار" } + if (w.step > 0) " · قدم ${faNum(w.step)}" else ""
}

/** The last [n] lines, oldest first (the panel draws the newest at the bottom). */
fun recentLines(a: SessionActivity, n: Int = PANEL_LINES): List<ActivityLine> = a.last.takeLast(n)

/** A line as the panel reads it: its words, and who said it when it is not [lead] (two at work: whose step it was). */
fun lineFa(l: ActivityLine, lead: String?): String {
    val text = oneLine(l.textFa)
    val who = l.whoFa.trim()
    return if (who.isBlank() || who == lead?.trim() || text.startsWith(who)) text else "$who: $text"
}

/** How long a run has been going: «۴۰ ثانیه»، «۱۲ دقیقه»، «۱ ساعت و ۵ دقیقه». Null without a start. */
fun elapsedFa(startedAt: String, now: Long = HqClock.millis()): String? {
    val t = millisOf(startedAt) ?: return null
    val s = ((now - t) / 1000).coerceAtLeast(0)
    if (s < 60) return "${faNum(s.toInt())} ثانیه"
    val m = s / 60
    if (m < 60) return "${faNum(m.toInt())} دقیقه"
    val h = m / 60
    val rest = m % 60
    return "${faNum(h.toInt())} ساعت" + if (rest > 0) " و ${faNum(rest.toInt())} دقیقه" else ""
}

/** A past time in words: «همین الان»، «۵ دقیقه پیش»، «۲ ساعت پیش»، «۳ روز پیش». Null without a time. */
fun sinceFa(iso: String?, now: Long = HqClock.millis()): String? {
    val t = millisOf(iso.orEmpty()) ?: return null
    val s = ((now - t) / 1000).coerceAtLeast(0)
    if (s < 45) return "همین الان"
    val m = Math.round(s / 60.0)
    if (m < 60) return "${faNum(m.toInt())} دقیقه پیش"
    val h = Math.round(m / 60.0)
    if (h < 24) return "${faNum(h.toInt())} ساعت پیش"
    return "${faNum(Math.round(h / 24.0).toInt())} روز پیش"
}

/** «آرام · آخرین کار ۵ دقیقه پیش» (since the hub's idle time, else the last line's). */
fun idleFa(a: SessionActivity, now: Long = HqClock.millis()): String =
    (a.idleSince ?: a.last.lastOrNull()?.at)?.let { sinceFa(it, now) }?.let { "آرام · آخرین کار $it" } ?: "آرام"

// ------------------------------------------------------------------ the plan --
/** Where the plan stands: the task in hand ([n], the first in work, else the first not done), of [total] (dropped ones out), [done]. */
data class PlanProgress(val n: Int, val total: Int, val done: Int) {
    val finished: Boolean get() = done >= total
    val fraction: Float get() = if (total <= 0) 0f else (done.toFloat() / total).coerceIn(0f, 1f)
}

/** The plan's progress; null without a plan. */
fun planProgress(tasks: List<SessionTask>): PlanProgress? {
    val live = orderedTasks(tasks).filter { it.state != "dropped" }
    if (live.isEmpty()) return null
    val done = live.count { it.state == "done" }
    val doing = live.indexOfFirst { it.state == "doing" }
    val next = live.indexOfFirst { it.state != "done" }
    val n = when { doing >= 0 -> doing + 1; next >= 0 -> next + 1; else -> live.size }
    return PlanProgress(n, live.size, done)
}

/** «کار ۳ از ۹»; the whole plan done: «کار ۹ از ۹ · تمام». */
fun planProgressFa(p: PlanProgress): String =
    if (p.finished) "کار ${faNum(p.total)} از ${faNum(p.total)} · تمام" else "کار ${faNum(p.n)} از ${faNum(p.total)}"

/** The title of the task in hand (for the reader and the progress's label). */
fun taskInHand(tasks: List<SessionTask>): SessionTask? = planProgress(tasks)?.takeIf { !it.finished }?.let { p ->
    orderedTasks(tasks).filter { it.state != "dropped" }.getOrNull(p.n - 1)
}

/** What the switch of pace says (the same words the details sheet has always said). */
fun paceToastFa(pace: String): String = if (pace == "step") "از این به بعد قدم‌به‌قدم با تو." else "از این به بعد خودش تا آخر میرود."
