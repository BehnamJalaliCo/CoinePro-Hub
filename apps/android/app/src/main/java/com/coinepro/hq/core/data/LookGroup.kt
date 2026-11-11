package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.net.RoutineRun
import java.time.DayOfWeek
import java.time.Instant
import java.time.ZoneId
import java.time.ZonedDateTime

// ⟨1.0.1⟩ Part C, the working group in the look (C3.4), in the owner's words (the web's look/group.tsx, rule for rule): when a
// routine runs next (worked out from its own schedule, on the owner's clock), its last seven runs as dots, what a member's tile says
// (its last run, whether something of it runs now, and why it stands still), and the one-line summary of a draft for its seal.
// Pure functions: the unit tests read them.

// =============================================================================================== the next run ==
private val BYDAY = mapOf(
    "MO" to DayOfWeek.MONDAY, "TU" to DayOfWeek.TUESDAY, "WE" to DayOfWeek.WEDNESDAY, "TH" to DayOfWeek.THURSDAY,
    "FR" to DayOfWeek.FRIDAY, "SA" to DayOfWeek.SATURDAY, "SU" to DayOfWeek.SUNDAY,
)

/**
 * When a schedule (an RRULE of the hub's: hourly, daily, weekly on its days, monthly on its day; the owner's zone) runs next, as an
 * instant; null when it cannot be read.
 */
fun nextRun(schedule: String?, now: Long = HqClock.millis()): String? {
    if (schedule.isNullOrBlank()) return null
    val k = schedule.removePrefix("RRULE:").split(';').mapNotNull { p -> p.split('=').takeIf { it.size == 2 }?.let { it[0].trim().uppercase() to it[1].trim() } }.toMap()
    val h = (k["BYHOUR"] ?: "0").split(',').first().toIntOrNull()?.takeIf { it in 0..23 } ?: return null
    val m = (k["BYMINUTE"] ?: "0").split(',').first().toIntOrNull()?.takeIf { it in 0..59 } ?: return null
    val zone = ZoneId.of(OWNER_TZ)
    val at = Instant.ofEpochMilli(now).atZone(zone)
    fun day(d: Long, hour: Int = h): ZonedDateTime = at.toLocalDate().plusDays(d).atTime(hour, m).atZone(zone)
    fun iso(t: ZonedDateTime) = t.toInstant().toString()
    return when (k["FREQ"]?.uppercase()) {
        "HOURLY" -> (0L..1L).map { at.withMinute(m).withSecond(0).withNano(0).plusHours(it) }.firstOrNull { it.isAfter(at) }?.let(::iso)
        "DAILY" -> (0L..1L).map { day(it) }.firstOrNull { it.isAfter(at) }?.let(::iso)
        "WEEKLY" -> {
            val days = k["BYDAY"].orEmpty().split(',').mapNotNull { BYDAY[it.trim().uppercase()] }
            (0L..7L).map { day(it) }.firstOrNull { t -> t.isAfter(at) && (if (days.isEmpty()) t.dayOfWeek == at.dayOfWeek else t.dayOfWeek in days) }?.let(::iso)
        }
        "MONTHLY" -> {
            val dom = k["BYMONTHDAY"]?.toIntOrNull()?.takeIf { it in 1..28 } ?: 1
            (0L..1L).map { at.toLocalDate().withDayOfMonth(1).plusMonths(it).withDayOfMonth(dom).atTime(h, m).atZone(zone) }.firstOrNull { it.isAfter(at) }?.let(::iso)
        }
        else -> null
    }
}

/** The soonest next run among several schedules. */
fun soonestRun(schedules: List<String>, now: Long = HqClock.millis()): String? = schedules.mapNotNull { nextRun(it, now) }.minOrNull()

// ============================================================================================ the last seven runs ==
val RUN_FA = mapOf("done" to "انجام شد", "failed" to "ناموفق", "skipped" to "رد شد", "queued" to "در صف")

const val RUN_DOTS = 7

/** The last seven runs of a routine, oldest first (what the dots draw, left to right). */
fun lastSeven(runs: List<RoutineRun>): List<RoutineRun> = runs.sortedBy { it.at }.takeLast(RUN_DOTS)

/** What a screen reader hears of the dots. */
fun runDotsFa(label: String, runs: List<RoutineRun>): String {
    val last = lastSeven(runs)
    if (last.isEmpty()) return "$label: هنوز نوبتی نداشته"
    val failed = last.count { it.state == "failed" }
    return "$label: ${last.size} نوبت آخر" + if (failed > 0) "، $failed ناموفق" else "، همه بی‌خطا"
}

// =================================================================================================== a member ==
const val MEMBER_STILL_FA = "این شرکت در کارگروه ایستاده است؛ روال‌هایش اجرا نمیشوند."

/**
 * What a member's tile says of its runs: its [last] run that is over, whether something of it runs now ([running]: a run in the
 * queue), and, when it stands still, [why] in one line (what its last run said when it failed, else that it was stopped).
 */
data class MemberLook(val last: RoutineRun?, val running: Boolean, val why: String?)

/** [runs]: the group's runs in any order (null: this hub does not serve them). [on]: the member is at work in the group. */
fun memberLook(company: String, on: Boolean, runs: List<RoutineRun>?): MemberLook {
    val mine = runs.orEmpty().filter { it.company == company }.sortedByDescending { it.at }
    val last = mine.firstOrNull { it.state != "queued" }
    val running = on && mine.any { it.state == "queued" }
    val why = if (on) null else last?.takeIf { it.state == "failed" }?.noteFa?.trim()?.ifBlank { null } ?: MEMBER_STILL_FA
    return MemberLook(last, running, why)
}

/** The state of a member as a word beside its shape: «در کار» while a run of it is going, «فعال», «ایستاده». */
fun memberWordFa(on: Boolean, running: Boolean): String = if (!on) "ایستاده" else if (running) "در کار" else "فعال"

// ============================================================================================ the draft's summary ==
/** «۳ جایگاه», «۲ روال», «۱ اتصال»: what a seal starts, as facts for one line (a count in a sentence). */
fun sealSummary(seats: Int, routines: Int, connections: Int): List<String> =
    listOfNotNull("$seats جایگاه", "$routines روال", if (connections > 0) "$connections اتصال" else null)
