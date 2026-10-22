package com.coinepro.hq.core.format

import android.icu.text.SimpleDateFormat
import android.icu.util.TimeZone
import android.icu.util.ULocale
import java.time.Instant
import java.time.OffsetDateTime
import java.util.Date
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.roundToLong

// Digits: the text face (IRANYekanX FaNum) draws ASCII digits as Persian, so prose counts are plain ASCII
// here; figures (money, tokens, codes, model names) are set in the Latin face and stay Latin. Dates are
// Jalali in the owner's time zone. This mirrors apps/web/src/lib/format.ts.

const val OWNER_TZ = "Asia/Tehran"

/** The app's clock for what it shows: the system's, or one fixed instant in the screenshot tests so the images are the
 *  same on any day (the visual gate compares them in CI). The demo resolves its fixture times against it too. */
object HqClock {
    @Volatile var fixed: Instant? = null
    fun now(): Instant = fixed ?: Instant.now()
    fun millis(): Long = now().toEpochMilli()
    fun today(zone: java.time.ZoneId = java.time.ZoneId.of(OWNER_TZ)): java.time.LocalDate = java.time.LocalDate.ofInstant(now(), zone)
}

private val FA = ULocale("fa_IR@calendar=persian;numbers=latn")
private val TZ: TimeZone = TimeZone.getTimeZone(OWNER_TZ)

private fun pattern(p: String) = SimpleDateFormat(p, FA).apply { timeZone = TZ }

/** Parses the API's ISO-8601 instants ("2026-10-17T11:06:28.97Z", "+00:00"); a bare day ("2026-10-18", a week's key)
 *  is that day's start in the owner's zone. */
fun instant(iso: String?): Instant? = iso?.let {
    runCatching { OffsetDateTime.parse(it).toInstant() }.getOrNull()
        ?: runCatching { Instant.parse(it) }.getOrNull()
        ?: runCatching { java.time.LocalDate.parse(it).atStartOfDay(java.time.ZoneId.of(OWNER_TZ)).toInstant() }.getOrNull()
}

private fun fmt(p: String, iso: String?): String = instant(iso)?.let { pattern(p).format(Date.from(it)) } ?: "—"

/** "25 مهر" (drawn "۲۵ مهر"). */
fun jDate(iso: String?, withYear: Boolean = false): String = fmt(if (withYear) "d MMMM y" else "d MMMM", iso)

fun jWeekday(iso: String?): String = fmt("EEEE d MMMM", iso)

fun jTime(iso: String?): String = fmt("HH:mm", iso)

fun jDateTime(iso: String?): String = if (iso == null) "—" else "${jDate(iso)}، ${jTime(iso)}"

/** Owner-zone calendar day of an instant, ISO (for grouping). */
fun ownerDay(iso: String?): String = instant(iso)?.atZone(java.time.ZoneId.of(OWNER_TZ))?.toLocalDate()?.toString() ?: "—"

/** "5 دقیقه پیش" / "3 ساعت پیش" / date. */
fun ago(iso: String?, now: Long = HqClock.millis()): String {
    val t = instant(iso) ?: return "—"
    val s = ((now - t.toEpochMilli()) / 1000).coerceAtLeast(0)
    if (s < 45) return "همین الان"
    val m = (s / 60.0).roundToLong()
    if (m < 60) return "$m دقیقه پیش"
    val h = (m / 60.0).roundToLong()
    if (h < 24) return "$h ساعت پیش"
    val d = (h / 24.0).roundToLong()
    if (d < 7) return "$d روز پیش"
    return jDate(iso)
}

/** Time left until an instant (expiries, freezes, quota resets). */
fun until(iso: String?, now: Long = HqClock.millis()): String {
    val t = instant(iso) ?: return "—"
    val m = ((t.toEpochMilli() - now) / 60000.0).roundToLong()
    if (m <= 0) return "گذشته"
    if (m < 60) return "$m دقیقه مانده"
    val h = (m / 60.0).roundToLong()
    if (h < 48) return "$h ساعت مانده"
    return "${(h / 24.0).roundToLong()} روز مانده"
}

fun hoursUntil(iso: String?, now: Long = HqClock.millis()): Double? = instant(iso)?.let { (it.toEpochMilli() - now) / 3_600_000.0 }

/** 160K, 6.2M — a figure (Latin). */
fun tokens(n: Long?): String {
    if (n == null) return "—"
    val a = abs(n)
    fun trim(s: String) = s.removeSuffix(".0")
    return when {
        a >= 1_000_000 -> trim(String.format(Locale.US, if (a >= 10_000_000) "%.0f" else "%.1f", n / 1_000_000.0)) + "M"
        a >= 1_000 -> trim(String.format(Locale.US, if (a >= 100_000) "%.0f" else "%.1f", n / 1_000.0)) + "K"
        else -> n.toString()
    }
}

/** $2.94 — a figure (Latin). Accepts the API's decimal strings. */
fun usd(v: String?, digits: Int = 2): String {
    val n = v?.toDoubleOrNull() ?: return "—"
    return "$" + String.format(Locale.US, "%,.${digits}f", n)
}

fun usd(v: Double?, digits: Int = 2): String = usd(v?.toString(), digits)

/** "21٪" — prose (drawn with Persian digits). */
fun pct(v: Double?): String = if (v == null) "—" else "${v.roundToInt()}٪"

/** Persian decimal separator for prose numbers ("7٫9"). */
fun faDecimal(n: Double, digits: Int = 1): String = String.format(Locale.US, "%.${digits}f", n).replace('.', '٫')

/** "claude-sonnet-5-5" → "Sonnet 5.5" (model names stay Latin). */
fun modelLabel(id: String?): String {
    if (id.isNullOrBlank()) return "—"
    val m = Regex("^claude-([a-z]+)-(\\d+)(?:-(\\d+))?").find(id) ?: return id
    val (family, major, minor) = m.destructured
    return family.replaceFirstChar { it.uppercase() } + " " + major + if (minor.isNotEmpty()) ".$minor" else ""
}
