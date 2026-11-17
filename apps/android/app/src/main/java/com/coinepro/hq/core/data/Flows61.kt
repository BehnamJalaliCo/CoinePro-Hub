package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.FieldError
import com.coinepro.hq.core.net.FlowChange
import com.coinepro.hq.core.net.FlowDef
import com.coinepro.hq.core.net.FlowDefSchedule
import com.coinepro.hq.core.net.FlowOptions
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

// ⟨1.39⟩ Contract §61, the automations as data: what the board and the editor say, the editor's own checks (the hub's §61.4, so a
// wrong hour is said under its field before the save), what a save changes in the owner's words, and the save's body. Pure.

private val TEHRAN: ZoneId = ZoneId.of(OWNER_TZ)

/** The app's own words for a model's effort (§53: «زیاد · خیلی زیاد · بیشترین دقت»). */
fun flowEffortFa(e: String): String = effortFa(e) ?: e
fun flowKindFa(k: String): String = when (k) {
    "reel" -> "ریلز"; "stories" -> "استوری"; "short" -> "شورت"; "video" -> "ویدیو"; "article" -> "مقاله"; "tg_post" -> "پست تلگرام"; else -> k
}
fun flowStateFa(s: String): String = when (s) { "on" -> "روشن"; "off" -> "خاموش"; "paused" -> "مکث"; else -> s }
fun healthFa(state: String): String = when (state) { "ok" -> "سالم"; "warn" -> "نیاز به نگاه"; "down" -> "از کار افتاده"; else -> state }
fun alertKindFa(k: String): String = when (k) {
    "run_failed" -> "اجرا"; "cap_reached" -> "هزینه"; "page_held" -> "صفحه"; "login_expired" -> "ورود"; "clock_missed" -> "ساعت"; "late" -> "دیر"
    else -> k
}
fun alertTone(k: String): Tone = when (k) { "run_failed", "late" -> Tone.NEG; "login_expired", "page_held", "cap_reached" -> Tone.WARN; else -> Tone.NEUTRAL }

/** «Opus 5.5» from `claude-opus-5-5` when the hub sent no name. */
fun modelShort(id: String, nameFa: String = ""): String = nameFa.ifBlank {
    val m = Regex("claude-([a-z]+)-(\\d+)-(\\d+)").find(id) ?: return id
    "${m.groupValues[1].replaceFirstChar { it.uppercase() }} ${m.groupValues[2]}.${m.groupValues[3]}"
}

/** "$18.40" (Latin, as every price in the app). */
fun usdShort(v: Double): String = if (v >= 100 || v == Math.floor(v)) "$" + "%,.0f".format(java.util.Locale.US, v) else "$" + "%.2f".format(java.util.Locale.US, v)

// ------------------------------------------------------------------------------------------------------- the round --
/** Which week of the round [day] is (0-based), counted from the round's start in whole weeks. */
fun weekOfRound(s: FlowDefSchedule, day: LocalDate): Int {
    val n = s.hours.size.coerceAtLeast(1)
    val start = runCatching { LocalDate.parse(s.start) }.getOrNull() ?: return 0
    val weeks = Math.floorDiv(ChronoUnit.DAYS.between(start, day), 7L)
    return Math.floorMod(weeks, n.toLong()).toInt()
}

/** «هر روز ۱۲:۰۰» · «دور ۴ هفته: ۰۹:۳۰ · ۱۴:۰۰ · ۱۹:۳۰ · پربازدیدترین» · «۷ استوری · ۰۸:۳۰ تا ۲۲:۳۰». */
fun hoursLineFa(f: FlowDef): String {
    val s = f.schedule
    if (f.kind == "stories" && s.stories.isNotEmpty()) {
        val sorted = s.stories.sorted()
        return "${faNum(sorted.size)} استوری · ${faText(sorted.first())} تا ${faText(sorted.last())}"
    }
    val hs = s.hours
    if (hs.isEmpty()) return s.whenFa
    if (hs.distinct().size == 1 && hs.first() != null) return "هر روز ${faText(hs.first()!!)}"
    return "دور ${faNum(hs.size)} هفته: " + hs.joinToString(" · ") { it?.let(::faText) ?: "پربازدیدترین" }
}

/** Saturday = 0: «هر روز», «۵ روز», or the days themselves. */
fun daysLineFa(days: List<Int>): String = when {
    days.size >= 7 -> "هر روز"
    days.isEmpty() -> "هیچ روز"
    days.size <= 3 -> days.sorted().joinToString("، ") { J_WEEKDAY_FA[it] }
    else -> "${faNum(days.size)} روز هفته"
}

/** «ساخت از ۰۰:۳۰ شروع میشود و ریلز تا ۱۰:۰۰ آماده است» for the editor's start line. */
fun triggerLineFa(s: FlowDefSchedule, publishAt: String?): String {
    val start = faText(s.triggerAt.ifBlank { "—" })
    val at = publishAt?.let(::faText)
    return if (at != null) "ساخت از $start شروع میشود و ${if (s.sameDay) "همان روز" else "روز بعد"} ساعت $at منتشر میشود."
    else "ساخت از $start شروع میشود."
}

/** The month's estimate the editor shows beside the day's line. */
fun monthEstimate(usdCap: Double): Double = usdCap * 30

// ---------------------------------------------------------------------------------------------------- the editor --
/** What the owner is editing: the save-able fields only (the rest is the hub's). */
data class FlowDraft(
    val hours: List<String?>,
    val bestWeek: Boolean,
    val days: List<Int>,
    val stories: List<String>,
    val triggerAt: String,
    val sameDay: Boolean,
    val start: String,
    val model: String,
    val effort: String,
    val usdCap: Double,
    val cycle: List<String>,
    val storyWordMode: String,
    val storyWord: String,
    val noteFa: String,
)

fun flowDraftOf(f: FlowDef): FlowDraft = FlowDraft(
    hours = f.schedule.hours, bestWeek = f.schedule.bestWeek, days = f.schedule.days.sorted(), stories = f.schedule.stories,
    triggerAt = f.schedule.triggerAt, sameDay = f.schedule.sameDay, start = f.schedule.start, model = f.model, effort = f.effort,
    usdCap = f.budget.usdCap, cycle = f.cycle, storyWordMode = f.storyWordMode, storyWord = f.storyWord.orEmpty(), noteFa = f.noteFa.orEmpty(),
)

private val HM = Regex("^([01]\\d|2[0-3]):[0-5]\\d$")
fun isHour(s: String?): Boolean = s != null && HM.matches(s)
private fun minutes(hm: String): Int = hm.substring(0, 2).toInt() * 60 + hm.substring(3, 5).toInt()

/**
 * The hub's §61.4, said under each field before the save (the hub checks again and its word wins). [reels] the minutes of the other
 * flows' reels of the same account (a story never on their minute).
 */
fun checkDraft(d: FlowDraft, kind: String, o: FlowOptions, reels: List<String> = emptyList()): List<FieldError> {
    val out = ArrayList<FieldError>()
    if (!isHour(d.triggerAt)) out += FieldError("trigger_at", "ساعت باید به شکل ۱۴:۰۰ باشد")
    d.hours.forEachIndexed { i, h -> if (h != null && !isHour(h)) out += FieldError("hours.$i", "ساعت باید به شکل ۱۴:۰۰ باشد") }
    if (kind != "stories" && d.hours.isEmpty()) out += FieldError("hours", "دست‌کم یک ساعت انتشار لازم است")
    if (d.sameDay && isHour(d.triggerAt)) {
        val t = minutes(d.triggerAt)
        d.hours.forEachIndexed { i, h ->
            if (h != null && isHour(h) && minutes(h) - t < 90) out += FieldError("hours.$i", "هر ساعت انتشار باید دست‌کم ۹۰ دقیقه بعد از شروع ساخت باشد")
        }
        if (kind == "stories") d.stories.forEachIndexed { i, h ->
            if (isHour(h) && minutes(h) - t < 90) out += FieldError("stories.$i", "هر ساعت انتشار باید دست‌کم ۹۰ دقیقه بعد از شروع ساخت باشد")
        }
    }
    if (kind == "stories") {
        if (d.stories.isEmpty()) out += FieldError("stories", "دست‌کم یک استوری لازم است")
        if (d.stories.size > o.storiesMax) out += FieldError("stories", "حداکثر ${faNum(o.storiesMax)} استوری")
        val seen = HashSet<String>()
        d.stories.forEachIndexed { i, h ->
            when {
                !isHour(h) -> out += FieldError("stories.$i", "ساعت باید به شکل ۱۴:۰۰ باشد")
                !seen.add(h) -> out += FieldError("stories.$i", "این ساعت دو بار آمده است")
                h in reels -> out += FieldError("stories.$i", "این ساعت با ریلز ${faText(h)} همین پیج هم‌دقیقه است")
            }
        }
    }
    if (d.days.isEmpty()) out += FieldError("days", "دست‌کم یک روز هفته")
    if (d.usdCap < o.usdCap.min || d.usdCap > o.usdCap.max) out += FieldError("usd_cap", "هشدار هزینه‌ی روز باید بین ${faNum(o.usdCap.min)} و ${faNum(o.usdCap.max)} دلار باشد")
    if (o.models.isNotEmpty() && o.models.none { it.id == d.model }) out += FieldError("model", "این مدل در فهرست مجاز نیست")
    if (d.effort !in o.efforts) out += FieldError("effort", "این تلاش شناخته نیست")
    if (d.cycle.size > o.cycleMax) out += FieldError("cycle", "حداکثر ${faNum(o.cycleMax)} نوع")
    if (d.noteFa.length > o.noteMax) out += FieldError("note_fa", "حداکثر ${faNum(o.noteMax)} حرف")
    if (d.storyWordMode == "fixed" && d.storyWord.isBlank()) out += FieldError("story_word", "کلمه‌ی ثابت را بنویس")
    return out
}

private fun hoursFa(hs: List<String?>) = hs.joinToString(" · ") { it?.let(::faText) ?: "پربازدیدترین" }
private fun bool(b: Boolean) = if (b) "روشن" else "خاموش"

/** What a save changes, a line each, in the owner's words (the sheet «چه عوض میشود»). */
fun draftChanges(before: FlowDraft, after: FlowDraft, modelName: (String) -> String = { modelShort(it) }): List<FlowChange> {
    val out = ArrayList<FlowChange>()
    fun add(field: String, label: String, b: String, a: String) { if (b != a) out += FlowChange(field, label, b, a) }
    val n = maxOf(before.hours.size, after.hours.size)
    if (before.hours != after.hours) {
        if (before.hours.size == after.hours.size && n > 1) for (i in 0 until n) {
            add("hours.$i", "ساعت انتشار · هفته‌ی ${faNum(i + 1)}", before.hours[i]?.let(::faText) ?: "پربازدیدترین", after.hours[i]?.let(::faText) ?: "پربازدیدترین")
        } else add("hours", "ساعت انتشار", hoursFa(before.hours), hoursFa(after.hours))
    }
    add("best_week", "پربازدیدترین ساعت", bool(before.bestWeek), bool(after.bestWeek))
    add("days", "روزهای هفته", daysLineFa(before.days), daysLineFa(after.days))
    add("stories", "ساعت استوری‌ها", before.stories.joinToString(" · ", transform = ::faText), after.stories.joinToString(" · ", transform = ::faText))
    add("trigger_at", "شروع ساخت", faText(before.triggerAt), faText(after.triggerAt))
    add("same_day", "همان روز بساز", bool(before.sameDay), bool(after.sameDay))
    add("model", "مدل", modelName(before.model), modelName(after.model))
    add("effort", "تلاش", flowEffortFa(before.effort), flowEffortFa(after.effort))
    add("usd_cap", "هشدار هزینه‌ی روز", usdShort(before.usdCap), usdShort(after.usdCap))
    add("cycle", "چرخه‌ی نوع روز", before.cycle.joinToString(" · ").ifEmpty { "—" }, after.cycle.joinToString(" · ").ifEmpty { "—" })
    add("story_word", "کلمه‌ی ریپلای", wordFa(before), wordFa(after))
    add("note_fa", "یادداشت", if (before.noteFa.isBlank()) "—" else "${faNum(before.noteFa.length)} حرف", if (after.noteFa.isBlank()) "—" else "${faNum(after.noteFa.length)} حرف")
    add("start", "شروع دور", before.start, after.start)
    return out
}

private fun wordFa(d: FlowDraft) = if (d.storyWordMode == "fixed") "همیشه «${d.storyWord}»" else "تازه هر روز"

/** The PATCH body of a save: only what changed (§61.3); the schedule's fields together under `schedule`. */
fun patchBody(before: FlowDraft, after: FlowDraft, noteChange: String? = null): JsonObject = buildJsonObject {
    val sched = buildJsonObject {
        if (before.hours != after.hours) put("hours", JsonArray(after.hours.map { if (it == null) JsonNull else JsonPrimitive(it) }))
        if (before.bestWeek != after.bestWeek) put("best_week", JsonPrimitive(after.bestWeek))
        if (before.days != after.days) put("days", JsonArray(after.days.sorted().map { JsonPrimitive(it) }))
        if (before.stories != after.stories) put("stories", JsonArray(after.stories.map { JsonPrimitive(it) }))
        if (before.triggerAt != after.triggerAt) put("trigger_at", JsonPrimitive(after.triggerAt))
        if (before.sameDay != after.sameDay) put("same_day", JsonPrimitive(after.sameDay))
        if (before.start != after.start) put("start", JsonPrimitive(after.start))
    }
    if (sched.isNotEmpty()) put("schedule", sched)
    if (before.model != after.model) put("model", JsonPrimitive(after.model))
    if (before.effort != after.effort) put("effort", JsonPrimitive(after.effort))
    if (before.usdCap != after.usdCap) put("usd_cap", JsonPrimitive(after.usdCap))
    if (before.cycle != after.cycle) put("cycle", JsonArray(after.cycle.map { JsonPrimitive(it) }))
    if (before.storyWordMode != after.storyWordMode) put("story_word_mode", JsonPrimitive(after.storyWordMode))
    if (before.storyWord != after.storyWord) put("story_word", if (after.storyWord.isBlank()) JsonNull else JsonPrimitive(after.storyWord.trim()))
    if (before.noteFa != after.noteFa) put("note_fa", if (after.noteFa.isBlank()) JsonNull else JsonPrimitive(after.noteFa.trim()))
    noteChange?.trim()?.ifEmpty { null }?.let { put("note_change_fa", JsonPrimitive(it)) }
}

/** A rollback on a hub before §61 P2: the earlier version's body saved again as an edit (its editable fields only). */
fun rollbackBody(body: JsonObject): JsonObject = buildJsonObject {
    val keep = setOf("schedule", "model", "effort", "usd_cap", "cycle", "story_word_mode", "story_word", "note_fa", "title_fa")
    body.forEach { (k, v) -> if (k in keep) put(k, v) }
}

/** When the next one is, from now: «امروز ۱۳:۰۰», «فردا ۱۰:۰۰», else the day. */
fun nextWhenFa(iso: String?, nowMs: Long): String {
    val d = tehranDate(iso) ?: return "—"
    val today = Instant.ofEpochMilli(nowMs).atZone(TEHRAN).toLocalDate()
    val day = when (d) { today -> "امروز"; today.plusDays(1) -> "فردا"; else -> jDayFa(d) }
    return "$day ${faHour(iso)}"
}
