package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.MemberPublish
import com.coinepro.hq.core.net.Playbook
import com.coinepro.hq.core.net.PlaybookRoutine
import com.coinepro.hq.core.net.PlaybookSeat
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull

// Contract §40 ⟨1.22⟩ in the owner's words: a session's memory, the working group drafted from it (a playbook), its library, and what
// giving it to another company or platform takes. Pure functions: the unit tests read them. A ref (PB-…, F-…) is a key here and never
// a word the owner reads.

// --------------------------------------------------------------- platforms --
/** The platforms in the order the pickers show them; «همه» is `any`. */
val PB_PLATFORMS: List<String> = listOf("instagram", "youtube", "telegram", "site", "any")

/** A platform's name (a picker's chip); `any` is «همه». */
fun pbPlatformFa(p: String?): String = when (p) {
    "instagram" -> "اینستاگرام"
    "youtube" -> "یوتیوب"
    "telegram" -> "تلگرام"
    "site" -> "سایت"
    "any", null, "" -> "همه"
    else -> p
}

/** A platform in a sentence: «اینستاگرام», or «همه‌ی پلتفرم‌ها» for `any`. */
fun pbPlatformLineFa(p: String?): String = if (p == null || p == "any" || p.isBlank()) "همه‌ی پلتفرم‌ها" else pbPlatformFa(p)

// ------------------------------------------------------------------ states --
/** A playbook's state as a pill. */
fun playbookStateFa(state: String): Pair<String, Tone> = when (state) {
    "sealed" -> "مُهر شده" to Tone.POS
    "retired" -> "بازنشسته" to Tone.SILVER
    else -> "پیش‌نویس" to Tone.GOLD
}

/** A member company's state: at work, or paused. */
fun memberStateFa(state: String): Pair<String, Tone> = if (state == "paused") "ایستاده" to Tone.SILVER else "در کار" to Tone.POS

// ----------------------------------------------------------------- helpers --
/** A seat's helper: its product name and the provider whose logo it carries (AI Studio is Google's). */
data class Helper(val key: String, val name: String, val provider: String?)

fun helperOf(key: String): Helper = when (key) {
    "gpt" -> Helper(key, "ChatGPT", "openai")
    "gemini" -> Helper(key, "Gemini", "google")
    "deepseek" -> Helper(key, "DeepSeek", "deepseek")
    "aistudio" -> Helper(key, "AI Studio", "google")
    else -> Helper(key, key, null)
}

// ------------------------------------------------------------------ counts --
/** A count in prose, in Persian digits («۲»). */
fun faNum(n: Int): String = n.toString().map { if (it in '0'..'9') '۰' + (it - '0') else it }.joinToString("")

/** «۲ شرکت» · «هنوز هیچ شرکتی»: the companies a playbook runs in. */
fun membersFa(n: Int): String = if (n <= 0) "هنوز هیچ شرکتی" else "${faNum(n)} شرکت"

/** The seat a routine is for, by its name. */
fun seatTitleFa(pb: Playbook, seat: String): String = pb.seats.firstOrNull { it.seat == seat }?.titleFa?.ifBlank { null } ?: seat

// ---------------------------------------------------------------- schedule --
private val DAYS_FA = mapOf("SA" to "شنبه", "SU" to "یکشنبه", "MO" to "دوشنبه", "TU" to "سه‌شنبه", "WE" to "چهارشنبه", "TH" to "پنجشنبه", "FR" to "جمعه")
private val DAY_ORDER = listOf("SA", "SU", "MO", "TU", "WE", "TH", "FR")

/**
 * A routine's time in plain Persian from its RRULE (the owner's zone): «هر روز ساعت 09:00», «هر شنبه و سه‌شنبه ساعت 18:00», «هر ماه،
 * روز ۱ ساعت 10:00», «هر ۲ روز ساعت 08:30», «هر ساعت». The clock is a figure (Latin digits); the counts are prose (Persian). A rule this
 * does not read is «طبق برنامه‌ی خودش», never the raw rule.
 */
fun routineTimeFa(rrule: String?): String {
    if (rrule.isNullOrBlank()) return "بدون زمان"
    val p = rrule.trim().removePrefix("RRULE:").split(';').mapNotNull { kv ->
        kv.split('=').takeIf { it.size == 2 }?.let { it[0].trim().uppercase() to it[1].trim().uppercase() }
    }.toMap()
    val every = p["INTERVAL"]?.toIntOrNull()?.takeIf { it > 1 }
    val hours = p["BYHOUR"]?.split(',')?.mapNotNull { it.trim().toIntOrNull() }.orEmpty()
    val minute = p["BYMINUTE"]?.split(',')?.firstOrNull()?.trim()?.toIntOrNull() ?: 0
    val clock = if (hours.isEmpty()) "" else " ساعت " + hours.sorted().joinToString(" و ") { String.format(java.util.Locale.US, "%02d:%02d", it, minute) }
    return when (p["FREQ"]) {
        "HOURLY" -> if (every != null) "هر ${faNum(every)} ساعت" else "هر ساعت"
        "DAILY" -> (if (every != null) "هر ${faNum(every)} روز" else "هر روز") + clock
        "WEEKLY" -> {
            val days = p["BYDAY"]?.split(',')?.map { it.trim().takeLast(2) }?.filter { it in DAYS_FA }?.sortedBy { DAY_ORDER.indexOf(it) }.orEmpty()
            val head = when {
                days.isEmpty() && every != null -> "هر ${faNum(every)} هفته"
                days.isEmpty() -> "هر هفته"
                every != null -> "هر ${faNum(every)} هفته، " + days.joinToString(" و ") { DAYS_FA.getValue(it) }
                else -> "هر " + days.joinToString(" و ") { DAYS_FA.getValue(it) }
            }
            head + clock
        }
        "MONTHLY" -> {
            val day = p["BYMONTHDAY"]?.split(',')?.mapNotNull { it.trim().toIntOrNull() }.orEmpty()
            val head = if (every != null) "هر ${faNum(every)} ماه" else "هر ماه"
            head + (if (day.isEmpty()) "" else "، روز " + day.joinToString(" و ") { if (it < 0) "آخر" else faNum(it) }) + clock
        }
        else -> "طبق برنامه‌ی خودش"
    }
}

// ----------------------------------------------------------------- library --
/** The library in its groups: sealed first (the ones at work), then drafts, then the retired; each as the hub sends it (newest first). */
fun libraryGroups(list: List<Playbook>): List<Pair<String, List<Playbook>>> {
    val known = listOf("sealed" to "مُهر شده و در کار", "draft" to "پیش‌نویس", "retired" to "بازنشسته")
    val out = known.mapNotNull { (state, fa) -> list.filter { it.state == state }.takeIf { it.isNotEmpty() }?.let { fa to it } }
    val other = list.filter { p -> known.none { it.first == p.state } }
    return if (other.isEmpty()) out else out + ("دیگر" to other)
}

/** The playbooks drafted from one session (newest first), for its «جزئیات». */
fun playbooksOf(order: String, list: List<Playbook>): List<Playbook> = list.filter { it.source.order == order }

// ------------------------------------------------------------------- apply --
/** The companies [pb] can be given to: every running company but the holding and those already members. */
fun applyTargets(pb: Playbook, companies: List<Company>): List<Company> =
    companies.filter { it.kind != "holding" && it.status != "archived" && pb.members.none { m -> m.company == it.code } }

/** «بدون تغییر» (`as_is`): only a sealed playbook with its group; the hub refuses it otherwise. */
fun canApplyAsIs(pb: Playbook): Boolean = pb.sealed && pb.group != null

/** The body of `POST /playbooks/{ref}/apply`: as is, only the company (the platform and the note go with a new session only). */
fun applyBody(company: String, platform: String?, noteFa: String?, asIs: Boolean, publish: MemberPublish? = null): JsonObject = buildJsonObject {
    put("company", JsonPrimitive(company))
    if (asIs) {
        put("as_is", JsonPrimitive(true))
        // ⟨0.19.9⟩ §45 his standing word for that company, given with the gift
        if (publish != null) put("publish", publishRule(publish))
    } else {
        if (!platform.isNullOrBlank()) put("platform", JsonPrimitive(platform))
        noteFa?.trim()?.ifBlank { null }?.let { put("note_fa", JsonPrimitive(it.take(2000))) }
    }
}

/**
 * ⟨0.19.9⟩ §45 The owner's standing word as the hub takes it (`PUT …/publish`, and `publish` of a seal or an as-is gift): the mode,
 * the account only when he named one, `story` only on `auto`.
 */
fun publishRule(p: MemberPublish): JsonObject = buildJsonObject {
    put("mode", JsonPrimitive(if (p.auto) "auto" else "ask"))
    if (p.auto) {
        p.account?.trim()?.removePrefix("@")?.ifBlank { null }?.let { put("account", JsonPrimitive(it)) }
        if (p.story) put("story", JsonPrimitive(true))
        // ⟨0.20.0⟩ §46 the hour, only when it reads as one («18:30»)
        clockOf(p.at)?.let { put("at", JsonPrimitive(it)) }
    }
}

/** «HH:MM» as the hub takes it, from what he typed (Persian or Latin digits, «۱۸:۳۰», «9:5» is not one); null when it is no hour. */
fun clockOf(raw: String?): String? {
    val t = raw.orEmpty().trim().map { ch -> if (ch in '۰'..'۹') '0' + (ch - '۰') else if (ch in '٠'..'٩') '0' + (ch - '٠') else ch }.joinToString("")
    val m = Regex("^([01]?\\d|2[0-3]):([0-5]\\d)$").find(t) ?: return null
    return "%02d:%s".format(m.groupValues[1].toInt(), m.groupValues[2])
}

/** A seal's body: empty, or his standing word for the session's company. */
fun sealBody(publish: MemberPublish?): JsonObject = buildJsonObject { if (publish != null) put("publish", publishRule(publish)) }

/**
 * A working group publishes on Instagram (or on any platform): only then is the standing word offered, and offered **on**, as the
 * owner asked («به صورت خودکار از روز دوم انجام بشه»).
 */
fun publishes(pb: Playbook): Boolean = pb.platform == "instagram" || pb.platform == "any"

/** The accounts a refusal names («one of: @a, @b»): the company has several and he has to pick one. */
fun accountsNamed(field: String?): List<String> =
    Regex("@([A-Za-z0-9._]+)").findAll(field.orEmpty()).map { it.groupValues[1].trimEnd('.') }.distinct().toList()

// -------------------------------------------------------------------- edit --
/**
 * The owner's light edit of a draft (`PATCH /playbooks/{ref}`): only what changed from [before], each list whole. Null when nothing
 * changed. Seats and routines go as the hub serialises them (every field written), so a seat's model or a routine's budget stays.
 */
fun playbookPatch(before: Playbook, after: Playbook): JsonObject? {
    val out = buildJsonObject {
        if (after.titleFa.trim() != before.titleFa) put("title_fa", JsonPrimitive(after.titleFa.trim()))
        if (after.purposeFa.trim() != before.purposeFa) put("purpose_fa", JsonPrimitive(after.purposeFa.trim()))
        if (after.platform != before.platform) put("platform", JsonPrimitive(after.platform))
        if (after.seats != before.seats) put("seats", JsonArray(after.seats.map { Api.jsonBody.encodeToJsonElement(PlaybookSeat.serializer(), it) }))
        if (after.routines != before.routines) {
            put("routines", JsonArray(after.routines.map { Api.jsonBody.encodeToJsonElement(PlaybookRoutine.serializer(), it.copy(briefMd = it.briefMd.trim())) }))
        }
        if (after.rulesFa != before.rulesFa) put("rules_fa", JsonArray(after.rulesFa.map { it.trim() }.filter { it.isNotEmpty() }.map(::JsonPrimitive)))
    }
    return out.takeIf { it.isNotEmpty() }
}

/** A draft without the seat [seat], and without its routines: a routine on no seat is one the hub would drop anyway. */
fun withoutSeat(pb: Playbook, seat: String): Playbook =
    pb.copy(seats = pb.seats.filter { it.seat != seat }, routines = pb.routines.filter { it.seat != seat })

/** A draft is ready to seal when it has a title and at least one seat (the hub fills an empty seat, but a group of no one is nothing). */
fun canSeal(pb: Playbook): Boolean = pb.draft && pb.titleFa.isNotBlank() && pb.seats.isNotEmpty()

// --------------------------------------------------------------- the card --
/** The `playbook` card's payload: the playbook it points at and, from the holder's rewrite in words, the whole new draft. */
data class PlaybookCard(val ref: String, val draft: Playbook?)

/** Reads a card's payload `{playbook, draft?}`; null when it names no playbook (the card is then drawn as any card). */
fun playbookCardOf(payload: JsonObject): PlaybookCard? {
    val ref = (payload["playbook"] as? JsonPrimitive)?.contentOrNull?.trim()?.uppercase()?.ifBlank { null } ?: return null
    val draft = (payload["draft"] as? JsonObject)?.let { d ->
        runCatching { Api.json.decodeFromJsonElement(Playbook.serializer(), JsonObject(d + ("ref" to JsonPrimitive(ref)))) }.getOrNull()
    }
    return PlaybookCard(ref, draft)
}

// ------------------------------------------------------------------ memory --
/** The session's memory is shown folded past this many lines (a tap opens it all). */
const val MEMORY_FOLD_LINES = 8

/** Whether a memory is long enough to fold. */
fun memoryFolds(md: String): Boolean = md.trim().lines().size > MEMORY_FOLD_LINES || md.length > 600

private val REF_IN_TEXT = Regex("(?<![A-Za-z0-9-])[A-Z]{1,3}-\\d{3,10}(?![A-Za-z0-9-])(?:[ \\t]*(?=«))?")

private val SPACE_BEFORE_MARK = Regex("(?<=\\S)[ \\t]+(?=[:،؛.)])")
private val SPACES = Regex("(?<=\\S)[ \\t]{2,}")

/**
 * The hub's Markdown as the owner reads it (§34.4: no ref is a word on his screen): the session's memory, and the playbook the hub writes
 * as the owner's first word of a session that adapts it. The hub keeps the refs for the people in the session; here a ref right before its
 * title in «» or right after its own word goes («کارگروه PB-0002 «سئو»» → «کارگروه «سئو»», «# کارگروه PB-0001: …» → «# کارگروه: …»), any
 * other one becomes its word («W-000310 ساخته شد» → «کار ساخته شد»). Figures, a list's indentation and everything else stay as written.
 */
fun withoutRefs(md: String): String = REF_IN_TEXT.replace(md) { m ->
    val word = madeFa(m.value.trim())
    if (md.getOrNull(m.range.last + 1) == '«' || md.substring(0, m.range.first).trimEnd().endsWith(word)) "" else word
}.replace(SPACE_BEFORE_MARK, "").replace(SPACES, " ")
