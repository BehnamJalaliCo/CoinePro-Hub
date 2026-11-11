package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.net.Blocker
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.SessionActivity
import com.coinepro.hq.core.net.SessionTask
import com.coinepro.hq.core.net.SessionWorker

// ⟨1.0.1⟩ Part C, the session redesigned (C2.2; contract §54, §55.1), in the owner's words (the web's look/session.tsx, rule for
// rule): the mood light, the plan as a line of parts, the build ring of a workshop or direct turn, the «الان» bar's sentence and the
// work a «نگه دار» stops, the one sentence of a knot, and how long a closed session took. Pure functions: the unit tests read them.

// ====================================================================================================== the mood ==
/** The mood as the page says it: the hub's five, and «تمام» for a closed session. */
val MOOD_FA = mapOf("thinking" to "فکر میکند", "working" to "کار میکند", "waiting" to "منتظر تو", "stuck" to "گیر کرده", "idle" to "آرام", "done" to "تمام")

private val KNOWN_MOODS = setOf("thinking", "working", "waiting", "stuck", "idle")

/**
 * The session's mood: the hub's own word when it sends one (§55.1); on an older hub it is read from what the activity says (`stuck_fa`
 * → stuck, `waiting_fa` → waiting, someone works → working, else idle); with no activity at all, from the session's badge. A closed
 * session is «تمام». [asked]: the holder's question is open.
 */
fun moodOf(a: SessionActivity?, closed: Boolean, badge: String? = null, asked: Boolean = false): String {
    if (closed) return "done"
    if (a != null) {
        a.mood?.takeIf { it in KNOWN_MOODS }?.let { return it }
        return when {
            !a.stuckFa.isNullOrBlank() -> "stuck"
            !a.waitingFa.isNullOrBlank() -> "waiting"
            a.working.isNotEmpty() -> "working"
            asked -> "waiting"
            else -> "idle"
        }
    }
    if (asked || badge == "your_turn") return "waiting"
    return when (badge) { "stuck" -> "stuck"; "moving" -> "working"; else -> "idle" }
}

/** The word beside the light: the hub's own (`mood_fa`) when it sent the mood, else the app's. */
fun moodWordFa(mood: String, a: SessionActivity?): String =
    if (mood != "done" && a?.mood == mood) a.moodFa?.trim()?.ifBlank { null } ?: MOOD_FA.getValue(mood) else MOOD_FA[mood] ?: MOOD_FA.getValue("idle")

// ============================================================================================ the plan, in a line ==
private fun openTasks(tasks: List<SessionTask>) = tasks.filter { it.state != "dropped" }.sortedBy { it.n }

/** «کار ۳ از ۴»: the task the session is on (the last one once all are done) and how many there are; null with no plan. */
fun taskOf(tasks: List<SessionTask>): Pair<Int, Int>? {
    val live = openTasks(tasks)
    if (live.isEmpty()) return null
    val done = live.count { it.state == "done" }
    return minOf(live.size, done + 1) to live.size
}

fun taskFa(t: Pair<Int, Int>): String = "کار ${t.first} از ${t.second}"

/** «کار ۳ از ۴ ایستاده»: the task that stands still while the session waits for the owner; null when its plan is done or it has none. */
fun standingTaskFa(tasks: List<SessionTask>): String? {
    val live = openTasks(tasks)
    val done = live.count { it.state == "done" }
    return if (live.isNotEmpty() && done < live.size) "کار ${done + 1} از ${live.size} ایستاده" else null
}

/**
 * The plan as parts, in order: `done` (silver), `waiting` (the ONE part that waits for the owner: gold), `todo` (empty). [waiting]:
 * the session waits for the owner (his answer, or his approval), so its first open part is his. A line of the plan the owner wrote
 * himself (`by` = owner) is not a part that waits for him: a plan he dictated is not painted gold.
 */
fun segmentsOf(tasks: List<SessionTask>, waiting: Boolean): List<String> {
    val live = openTasks(tasks)
    val first = live.indexOfFirst { it.state != "done" }
    return live.mapIndexed { i, t ->
        when {
            t.state == "done" -> "done"
            waiting && i == first -> "waiting"
            else -> "todo"
        }
    }
}

/** What a screen reader hears of the segmented line. */
fun segmentsFa(parts: List<String>): String =
    "${parts.count { it == "done" }} کار از ${parts.size} انجام شده" + if ("waiting" in parts) "؛ یک بخش منتظر تو است" else ""

// =================================================================================================== time, in words ==
/** «۲ ساعت و ۱۰ دقیقه», «۴۰ دقیقه», «۳ روز»: how long something took (a count in a sentence). Null without both ends. */
fun tookFa(from: String?, to: String?): String? {
    val a = instant(from) ?: return null
    val b = instant(to) ?: return null
    val m = Math.round((b.toEpochMilli() - a.toEpochMilli()) / 60_000.0)
    if (m < 0) return null
    if (m < 1) return "کمتر از یک دقیقه"
    if (m < 60) return "$m دقیقه"
    val h = m / 60
    val r = m % 60
    if (h >= 48) return "${Math.round(h / 24.0)} روز"
    return if (r > 0) "$h ساعت و $r دقیقه" else "$h ساعت"
}

/** «0:42», «23:05», «1:02:10»: a running timer, a Latin figure. */
fun timerFig(startedAt: String?, now: Long = HqClock.millis()): String {
    val t = instant(startedAt)?.toEpochMilli() ?: now
    val s = ((now - t) / 1000).coerceAtLeast(0)
    val h = s / 3600
    fun two(n: Long) = n.toString().padStart(2, '0')
    return if (h > 0) "$h:${two(s % 3600 / 60)}:${two(s % 60)}" else "${s / 60}:${two(s % 60)}"
}

// ================================================================================================ the «الان» bar ==
/** A workshop turn or the holder's own direct turn, with its time cap: it is shown as the build ring. */
fun isTurn(w: SessionWorker): Boolean = (w.kind == "workshop" || w.kind == "direct") && (w.capS ?: 0) > 0

/** How far a turn is into its time cap: its [share] (0..1), the minute it is in, the cap in minutes, and whether it is past 90 percent. */
data class TurnTime(val share: Float, val min: Int, val capMin: Int, val late: Boolean)

fun turnTime(w: SessionWorker, now: Long = HqClock.millis()): TurnTime {
    val cap = maxOf(60, w.capS ?: 3600)
    val started = instant(w.startedAt)?.toEpochMilli() ?: now
    val spent = ((now - started) / 1000.0).coerceAtLeast(0.0)
    val share = (spent / cap).coerceAtMost(1.0).toFloat()
    val capMin = Math.round(cap / 60.0).toInt()
    return TurnTime(share, minOf(capMin, (spent / 60).toInt()), capMin, share >= 0.9f)
}

/** What the worker does, as one whole sentence: the last thing a live turn did, else what it is doing, else its work's title. */
fun sentenceOf(w: SessionWorker): String =
    w.lastFa?.trim()?.ifBlank { null } ?: w.doingFa.trim().ifBlank { null } ?: w.workTitleFa.trim()

/** What a worker's turn is, in a word beside his name: «کارگاه», «سرور شرکت»; nothing for a run, and nothing for a direct turn (the
 *  holder himself works). */
fun workerKindFa(w: SessionWorker): String? = when (w.kind) { "workshop" -> "کارگاه"; "server" -> "سرور شرکت"; else -> null }

const val DIRECT_NOW_FA = "دارد روی فرمان تو کار میکند"

/** The facts over the bar's sentence: who, his company (when his name does not say it), what kind of turn, and how many others work. */
fun nowFacts(w: SessionWorker, count: Int): List<String> = listOfNotNull(
    w.whoFa.trim().ifBlank { "یک همکار" },
    if (w.kind == "direct") DIRECT_NOW_FA else w.companyFa?.trim()?.ifBlank { null }?.takeIf { it !in w.whoFa },
    if (w.kind == "direct") null else workerKindFa(w),
    if (count > 1) "و ${count - 1} نفر دیگر" else null,
)

/** The worker the bar speaks of: a turn first (its ring is the bar's mark), else the first one. */
fun leadWorker(working: List<SessionWorker>): SessionWorker? = working.firstOrNull(::isTurn) ?: working.firstOrNull()

private val WORKSPACE_LIVE = setOf("starting", "working", "awaiting_seal", "idle")

/**
 * The work a «نگه دار» stops: the task in hand, else the live workspace, else the first open task that names its work, else the first
 * split part, else the last task that names one. Null: the report names no work (the bar has no «نگه دار» then).
 */
fun liveWorkRef(o: OrderReport): String? {
    fun ref(t: SessionTask) = t.workRef?.trim()?.ifBlank { null }
    return o.tasks.firstOrNull { it.state == "doing" && ref(it) != null }?.let(::ref)
        ?: o.workspaces.firstOrNull { it.state in WORKSPACE_LIVE && it.workRef.isNotBlank() }?.workRef
        ?: o.tasks.firstOrNull { it.state == "todo" && ref(it) != null }?.let(::ref)
        ?: o.parts.firstOrNull { it.workRef.isNotBlank() }?.workRef
        ?: o.tasks.filter { ref(it) != null }.maxByOrNull { it.n }?.let(::ref)
}

const val HELD_FA = "کار نگه داشته شد"
const val HELD_HINT_FA = "هر وقت خواستی «ادامه بده» را بزن؛ از همان‌جا ادامه پیدا میکند."

// =================================================================================================== the «گره» card ==
/** The knot the card leads with: the first blocker that has a fix, else the first one. */
fun leadKnot(blockers: List<Blocker>): Blocker? = blockers.firstOrNull { it.fix != null } ?: blockers.firstOrNull()

/** One whole sentence of why the session stands still: the hub's own (`stuck_fa`), else the leading knot's title and detail. */
fun knotWhy(stuckFa: String?, blockers: List<Blocker>): String? {
    stuckFa?.trim()?.ifBlank { null }?.let { return it }
    val b = leadKnot(blockers) ?: return null
    return listOfNotNull(b.titleFa.trim().ifBlank { null }, b.detailFa.trim().ifBlank { null }).joinToString("؛ ").ifBlank { null }
}

// ==================================================================================================== the details ==
/** §54 what a direct session's details say; nothing else changes for the owner. */
const val DIRECT_FA = "مسئول این جلسه خودش کار را انجام میدهد (جلسه‌ی مستقیم)"

/** The quiet line where the composer was, once a session is closed. */
const val CLOSED_FA = "این جلسه بسته شده و فقط خواندنی است؛ برای ادامه، دوباره بازش کن."
