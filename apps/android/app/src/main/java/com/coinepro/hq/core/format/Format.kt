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

/** ⟨1.5⟩ The day of the Jalali month in the owner's zone (§21.13: a substitute behind on the 15th). */
fun jDayOfMonth(millis: Long = HqClock.millis()): Int = pattern("d").format(Date(millis)).toIntOrNull() ?: 1

fun jTime(iso: String?): String = fmt("HH:mm", iso)

/** The Jalali month's name ("مهر") of a "YYYY-MM" key (the middle of that month, so the name is the one most of it falls in). */
fun jMonth(month: String?): String = if (month == null || month.length < 7) "—" else fmt("MMMM", "${month.take(7)}-15")

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

/** "21%" — ⟨1.0.1⟩ C0.4: a percent is a figure (Latin tabular digits), like money and a rank; the app's text draws it so. */
fun pct(v: Double?): String = if (v == null) "—" else "${v.roundToInt()}%"

/**
 * ⟨1.0.1⟩ C0.4: [text] as one isolated left-to-right run (U+2066 … U+2069), for a Latin token (money, a percent, a ref like O-000152,
 * P0, a file name, a handle) inside a Persian string that stays a string (a toast, a label built by a formatter, a content
 * description). On a screen nothing more is needed: the app's `Text` isolates every such token itself (designsystem/Text.kt).
 * A dash, an empty string and a run already isolated come back as they are.
 */
fun ltr(text: String?): String = when {
    text.isNullOrEmpty() -> ""
    text == "—" || text.startsWith('\u2066') -> text
    else -> "\u2066$text\u2069"
}

/** [text] without the isolate marks [ltr] added (for a value that is sent, compared or copied). */
fun unltr(text: String): String = text.replace("\u2066", "").replace("\u2069", "")

/**
 * A share as a percent, whichever way the hub sends it: a fraction (0..1, the contract's form: `uptime_24h`, accuracy, progress) or,
 * from an older service, already a percent (`uptime_24h` 99.8). A value above 1 is taken as a percent, so it is never scaled twice
 * («10000.0%»). A share is never above 100%.
 */
fun percentOf(v: Double): Double = (if (v > 1.0) v else v * 100).coerceIn(0.0, 100.0)

/** [percentOf] as a Latin figure: "38%", "99.8%" with [digits]; null or not a number is a dash. */
fun percentText(v: Double?, digits: Int = 0): String =
    if (v == null || !v.isFinite()) "—" else String.format(Locale.US, "%.${digits}f%%", percentOf(v))

/** A site's uptime: "100%" when whole (or none), else one decimal ("99.8%"). */
fun uptimeText(v: Double?): String {
    if (v == null || !v.isFinite()) return "—"
    val p = percentOf(v)
    return if (p >= 99.95 || p == 0.0) "${p.roundToInt()}%" else String.format(Locale.US, "%.1f%%", p)
}

/** Persian decimal separator for prose numbers ("7٫9"). */
fun faDecimal(n: Double, digits: Int = 1): String = String.format(Locale.US, "%.${digits}f", n).replace('.', '٫')

/** "claude-sonnet-5-5" → "Sonnet 5.5" (model names stay Latin). */
/** A ledger row's model is a real model: Claude Code records its own local messages (an interruption, an API error notice) as
 *  `<synthetic>`, with no tokens and no cost, so such a placeholder never shows as a model (mirrors the web's isRealModel). */
fun isRealModel(id: String?): Boolean = !id.isNullOrBlank() && !id.startsWith("<")

fun modelLabel(id: String?): String {
    if (id.isNullOrBlank()) return "—"
    val m = Regex("^claude-([a-z]+)-(\\d+)(?:-(\\d+))?").find(id) ?: return id
    val (family, major, minor) = m.destructured
    return family.replaceFirstChar { it.uppercase() } + " " + major + if (minor.isNotEmpty()) ".$minor" else ""
}
