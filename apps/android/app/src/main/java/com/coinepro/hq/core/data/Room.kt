package com.coinepro.hq.core.data

import com.coinepro.hq.core.net.DeskCard
import com.coinepro.hq.core.net.MemberPublish
import com.coinepro.hq.core.net.Playbook
import com.coinepro.hq.core.net.PublishDesk
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull

// Contract §58 ⟨1.36⟩ in the owner's words: «وقتی سوال میپرسه من میخوام بنویسم نوشته هام دیده نمیشه … من اصلا فضایی از صفحه ندارم که خروجی
// رو ببینم»; «بستن جلسه که بایگانی شد حداقل اون رویه و کارگروه … توی اپ بمونه»; «میز انتشار … وسط دفتره آیا درسته؟». What the apps read
// of it, as pure functions (the unit tests read them). Prose counts in Persian digits; a clock and a size are Latin figures.

// ------------------------------------------------------------------ §58.1 room to write --
/** How many lines the question card shows before «بیشتر». */
const val QUESTION_LINES = 3

/** The share of the screen the opened question may take; past it, it scrolls inside itself. */
const val QUESTION_MAX_SHARE = 0.4f

/** The question folded to its first line (while the owner writes): its first line of words, never an empty one. */
fun questionFirstLine(q: String): String = q.lineSequence().map { it.trim() }.firstOrNull { it.isNotEmpty() }.orEmpty()

/** «خروجی آخر: ریلز حد ضرر» (the chip of the session's newest output on the question card). */
fun latestOutputFa(title: String): String = "خروجی آخر: ${quietLine(title).ifBlank { "بی‌عنوان" }}"

// ------------------------------------------------------- §58.2 the working group stays --
/** The one line of a closed session that left its working group in the library. */
const val PLAYBOOK_KEPT_FA = "کارگروه این جلسه در کتابخانه ماند"

/** Whether the hub says the session left its working group: `playbook_kept` true (or "true"), or a `playbook` it names (a ref, or an
 *  object with one). Anything else, or nothing, is no. */
fun playbookKept(kept: JsonElement?, playbook: JsonElement?): Boolean {
    val k = (kept as? JsonPrimitive)?.let { it.booleanOrNull ?: it.contentOrNull?.trim()?.equals("true", ignoreCase = true) } == true
    return k || refOf(playbook) != null
}

// --------------------------------------------------------------- §58.4 what stays --
/** A size the sweep freed: a number of bytes, or one written as a string; also inside the archived record. Null when none is said. */
fun freedBytesOf(k: DeskCard): Long? {
    fun read(e: JsonElement?): Long? = (e as? JsonPrimitive)?.let { it.longOrNull ?: it.contentOrNull?.trim()?.toDoubleOrNull()?.toLong() }
    return (read(k.freedBytes) ?: read((k.archived as? JsonObject)?.get("freed_bytes")))?.takeIf { it > 0 }
}

/** Whether the card's package was filed to the archive: `archived` true, or a record (an object or its ref). */
fun deskArchived(k: DeskCard): Boolean = when (val a = k.archived) {
    is JsonPrimitive -> a.booleanOrNull ?: (a.isString && !a.contentOrNull.isNullOrBlank())
    is JsonObject -> true
    else -> false
} || freedBytesOf(k) != null

/** «بایگانی شد · 48 MB آزاد شد» on a done card (the size a figure); «بایگانی شد» while the sweep has not run. Null when not archived. */
fun deskArchivedFa(k: DeskCard): String? {
    if (!deskArchived(k)) return null
    val freed = freedBytesOf(k) ?: return "بایگانی شد"
    return "بایگانی شد · ${com.coinepro.hq.core.media.fileSize(freed)} آزاد شد"
}

// --------------------------------------------------------------- §58.5 the desk's page --
/** The office's one line: «انتشار: ۲ آماده · ۱ در صف». */
fun deskHomeLineFa(d: PublishDesk): String = "انتشار: ${faNum(d.ready.size)} آماده · ${faNum(d.queue.size)} در صف"

/** A channel by the name the owner uses. */
fun channelFa(channel: String): String = when (channel.lowercase()) {
    "instagram" -> "اینستاگرام"
    "youtube" -> "یوتیوب"
    "telegram" -> "تلگرام"
    "x", "twitter" -> "ایکس"
    "site", "web" -> "سایت"
    "linkedin" -> "لینکدین"
    else -> channel
}

/** The channels of the desk, Instagram first, then as they come; today Instagram alone (also on an empty desk). */
fun deskChannels(d: PublishDesk): List<String> {
    val seen = (d.ready + d.queue + d.done).map { it.channel.ifBlank { "instagram" } }.distinct()
    return (listOf("instagram") + seen).distinct()
}

/** The desk of one channel. */
fun deskOf(d: PublishDesk, channel: String): PublishDesk {
    fun mine(k: DeskCard) = k.channel.ifBlank { "instagram" } == channel
    return PublishDesk(d.ready.filter(::mine), d.queue.filter(::mine), d.done.filter(::mine))
}

// ------------------------------------------------- §58.3 publishing by itself, in a line --
/** The daily hour of an RRULE («HH:MM», the owner's zone), or null when it is no daily rule with an hour. */
fun dailyHour(rrule: String?): String? {
    if (rrule.isNullOrBlank()) return null
    val p = rrule.trim().removePrefix("RRULE:").split(';').mapNotNull { kv ->
        kv.split('=').takeIf { it.size == 2 }?.let { it[0].trim().uppercase() to it[1].trim().uppercase() }
    }.toMap()
    if (p["FREQ"] != "DAILY" || p["INTERVAL"]?.toIntOrNull()?.let { it > 1 } == true) return null
    val hour = p["BYHOUR"]?.split(',')?.mapNotNull { it.trim().toIntOrNull() }?.minOrNull() ?: return null
    val minute = p["BYMINUTE"]?.split(',')?.firstOrNull()?.trim()?.toIntOrNull() ?: 0
    return String.format(java.util.Locale.US, "%02d:%02d", hour, minute)
}

/**
 * A sealed working group's day in one line, for one member company: «هر روز 09:00: ساخت ← انتشار خودکار ← اینستاگرام» (its standing word
 * «انتشار خودکار», else «تأیید تو»; the contract's «→», drawn as the app's Persian flows are, pointing the way the words read). The
 * hour is the earliest daily routine's, else the publish hour; a group with no daily routine says its first routine's time. Null for a
 * group that does not publish to Instagram.
 */
fun groupFlowFa(pb: Playbook, publish: MemberPublish): String? {
    if (!publishes(pb)) return null
    val hour = pb.routines.mapNotNull { dailyHour(it.schedule) }.minOrNull() ?: publish.at?.trim()?.ifBlank { null }
    val head = when {
        hour != null -> "هر روز $hour"
        pb.routines.isNotEmpty() -> routineTimeFa(pb.routines.first().schedule)
        else -> "هر روز"
    }
    return "$head: ساخت ← ${if (publish.auto) "انتشار خودکار" else "تأیید تو"} ← اینستاگرام"
}
