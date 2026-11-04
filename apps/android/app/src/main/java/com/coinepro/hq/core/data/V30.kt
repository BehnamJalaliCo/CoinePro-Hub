package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.LineCaps
import com.coinepro.hq.core.net.StepDef
import com.coinepro.hq.designsystem.generated.DivanIcon
import java.time.LocalDate
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull

// Contract §30 ⟨1.12⟩ in the owner's words: platforms, step kinds, the states of lines and runs, a schedule, the variables of a prompt,
// a step's settings as text, and the week the calendar shows. Pure functions: the unit tests read them directly.

// ------------------------------------------------------------- platforms --
val PLATFORM_FA = mapOf(
    "instagram_reel" to "ریلز اینستاگرام",
    "instagram_post" to "پست اینستاگرام",
    "instagram_story" to "استوری اینستاگرام",
    "youtube_short" to "شورت یوتیوب",
    "youtube_long" to "ویدیوی یوتیوب",
    "telegram_post" to "پست تلگرام",
    "site_article" to "مقاله‌ی سایت",
)

fun platformFa(p: String?): String = PLATFORM_FA[p] ?: "خروجی"

fun platformIcon(p: String?): DivanIcon = when (p) {
    "instagram_reel", "youtube_short", "youtube_long" -> DivanIcon.VIDEO
    "instagram_post", "instagram_story" -> DivanIcon.IMAGE
    "telegram_post" -> DivanIcon.SEND
    "site_article" -> DivanIcon.REPORT
    else -> DivanIcon.DELIVERABLE
}

/** The channel's kind from the platform (`instagram_reel` → `instagram`); the hub keeps `channel.kind` as the owner's line names it. */
fun channelKindOf(platform: String): String = when {
    platform.startsWith("instagram") -> "instagram"
    platform.startsWith("youtube") -> "youtube"
    platform.startsWith("telegram") -> "telegram"
    platform.startsWith("site") -> "site"
    else -> platform
}

fun channelHintFa(platform: String): String = when (channelKindOf(platform)) {
    "instagram" -> "نام صفحه، مثلاً tradeyar"
    "youtube" -> "نام کانال"
    "telegram" -> "نام کانال تلگرام"
    "site" -> "نشانی سایت"
    else -> "نام کانال"
}

// ------------------------------------------------------------ step kinds --
val STEP_KIND_FA = mapOf(
    "gpt_text" to "نوشتن متن",
    "dedupe" to "بررسی تکراری",
    "tts" to "صدا",
    "pattern_search" to "جست‌وجوی الگو",
    "council_pick" to "انتخاب شورا",
    "opus_build" to "ساخت",
    "render" to "رندر",
    "cover" to "کاور",
    "quality" to "کنترل کیفیت",
    "publish" to "انتشار",
    "deliver" to "تحویل به تو",
    "n8n" to "خودکارساز",
    "seal" to "مُهر تو",
)

fun stepKindFa(kind: String?): String = STEP_KIND_FA[kind] ?: "مرحله"

fun stepKindIcon(kind: String?): DivanIcon = when (kind) {
    "gpt_text" -> DivanIcon.EDIT
    "dedupe" -> DivanIcon.FILTER
    "tts" -> DivanIcon.MIC
    "pattern_search" -> DivanIcon.SEARCH
    "council_pick" -> DivanIcon.DECISION
    "opus_build" -> DivanIcon.MODEL
    "render" -> DivanIcon.VIDEO
    "cover" -> DivanIcon.IMAGE
    "quality" -> DivanIcon.CHART
    "publish" -> DivanIcon.SEND
    "deliver" -> DivanIcon.DOWNLOAD
    "n8n" -> DivanIcon.SETTINGS
    "seal" -> DivanIcon.SEAL
    else -> DivanIcon.TASK
}

/** Does this kind take a prompt the owner writes (§30.2: the ones that call a model)? */
fun stepHasPrompt(s: StepDef): Boolean = s.promptFa != null || s.kind in setOf("gpt_text", "council_pick", "opus_build", "cover")

val GATE_FA = mapOf("auto" to "خودکار", "owner" to "مُهر تو", "ceo" to "مُهر مدیرعامل")
fun gateFa(g: String?): String = GATE_FA[g] ?: "خودکار"

/** «متن › صدا › کاور › انتشار»: a template's or a line's steps in one line. */
fun stepsLineFa(steps: List<StepDef>): String = steps.filter { it.enabled }.joinToString(" › ") { stepKindFa(it.kind) }

// ----------------------------------------------------------------- states --
val LINE_STATE_FA: Map<String, Pair<String, Tone>> = mapOf(
    "draft" to ("آماده‌سازی" to Tone.SILVER),
    "on" to ("روشن" to Tone.POS),
    "paused" to ("مکث" to Tone.WARN),
)
fun lineStateFa(s: String?): String = LINE_STATE_FA[s]?.first ?: "آماده‌سازی"
fun lineStateTone(s: String?): Tone = LINE_STATE_FA[s]?.second ?: Tone.SILVER

fun lineModeFa(m: String?): String = if (m == "auto") "خودکار" else "با مُهر تو"
fun lineModeTone(m: String?): Tone = if (m == "auto") Tone.GOLD else Tone.LAPIS

/** A line's run state (§30.1 Run). */
val LINE_RUN_STATE_FA: Map<String, Pair<String, Tone>> = mapOf(
    "queued" to ("در صف" to Tone.SILVER),
    "running" to ("در کار" to Tone.GOLD),
    "waiting" to ("منتظر مُهر تو" to Tone.WARN),
    "done" to ("انجام شد" to Tone.POS),
    "failed" to ("انجام نشد" to Tone.NEG),
    "skipped" to ("رد شد" to Tone.SILVER),
    "cancelled" to ("لغو شد" to Tone.SILVER),
    // the calendar's items not yet run
    "scheduled" to ("در برنامه" to Tone.LAPIS),
)
fun lineRunStateFa(s: String?): String = LINE_RUN_STATE_FA[s]?.first ?: "در صف"
fun lineRunStateTone(s: String?): Tone = LINE_RUN_STATE_FA[s]?.second ?: Tone.SILVER

val STEP_STATE_FA: Map<String, Pair<String, Tone>> = mapOf(
    "pending" to ("در انتظار" to Tone.SILVER),
    "running" to ("در کار" to Tone.GOLD),
    "waiting" to ("منتظر تو" to Tone.WARN),
    "done" to ("تمام شد" to Tone.POS),
    "failed" to ("انجام نشد" to Tone.NEG),
    "skipped" to ("رد شد" to Tone.SILVER),
)
fun stepStateFa(s: String?): String = STEP_STATE_FA[s]?.first ?: "در انتظار"
fun stepStateTone(s: String?): Tone = STEP_STATE_FA[s]?.second ?: Tone.SILVER

/** Has the run ended (nothing more will happen to it)? */
fun lineRunEnded(state: String?): Boolean = state in setOf("done", "failed", "skipped", "cancelled")

fun runTriggerFa(t: String?): String = when (t) {
    "schedule" -> "طبق برنامه"
    "owner" -> "دستی"
    "test" -> "آزمایشی"
    "n8n" -> "از خودکارساز"
    "group" -> "از کارگروه"
    else -> "دستی"
}

// -------------------------------------------------------------- schedule --
private val DAY_FA = mapOf("MO" to "دوشنبه", "TU" to "سه‌شنبه", "WE" to "چهارشنبه", "TH" to "پنجشنبه", "FR" to "جمعه", "SA" to "شنبه", "SU" to "یکشنبه")

private fun rule(r: String): Map<String, String> = r.removePrefix("RRULE:").split(';').mapNotNull { kv -> kv.split('=').takeIf { it.size == 2 }?.let { it[0].trim().uppercase() to it[1].trim() } }.toMap()

/** «هر روز ساعت 09:00» · «شنبه و سه‌شنبه ساعت 18:30» · «بدون برنامه» from an RRULE (DAILY or WEEKLY with BYDAY, BYHOUR, BYMINUTE). */
fun scheduleFa(rrule: String?): String {
    if (rrule.isNullOrBlank()) return "بدون برنامه"
    val p = rule(rrule)
    val hours = (p["BYHOUR"] ?: "9").split(',').mapNotNull { it.trim().toIntOrNull() }.ifEmpty { listOf(9) }
    val min = p["BYMINUTE"]?.toIntOrNull() ?: 0
    val times = hours.joinToString(" و ") { String.format(java.util.Locale.US, "%02d:%02d", it, min) }
    return when (p["FREQ"]) {
        "DAILY" -> "هر روز ساعت $times"
        "WEEKLY" -> {
            val days = (p["BYDAY"] ?: "SA").split(',').mapNotNull { DAY_FA[it.trim()] }
            (if (days.isEmpty()) "هر هفته" else "هر " + days.joinToString(" و ")) + " ساعت $times"
        }
        else -> "طبق برنامه‌ی ثبت‌شده"
    }
}

/** Ready-made schedules the editor offers (an RRULE in the owner's zone; free text is still allowed). */
val SCHEDULE_PRESETS: List<String> = listOf(
    "FREQ=DAILY;BYHOUR=9;BYMINUTE=0",
    "FREQ=DAILY;BYHOUR=18;BYMINUTE=0",
    "FREQ=WEEKLY;BYDAY=SA,TU;BYHOUR=18;BYMINUTE=0",
    "FREQ=WEEKLY;BYDAY=SA;BYHOUR=10;BYMINUTE=0",
)

// ------------------------------------------------------- prompt variables --
/** The variables a step's prompt may use: the keys of the steps before it (their outputs), and the step's own inputs first. */
fun promptVariables(steps: List<StepDef>, index: Int): List<String> {
    val own = steps.getOrNull(index)?.inputs.orEmpty()
    val before = steps.take(index).map { it.key }
    return (own + before).distinct().filter { it != steps.getOrNull(index)?.key }
}

/** The `{{variables}}` a text names. */
fun variablesIn(text: String?): List<String> = Regex("\\{\\{\\s*([A-Za-z0-9_.]+)\\s*}}").findAll(text.orEmpty()).map { it.groupValues[1] }.distinct().toList()

/** [text] with `{{key}}` added at its end (a space between). */
fun withVariable(text: String, key: String): String = (if (text.isBlank() || text.endsWith(" ") || text.endsWith("\n")) text else "$text ") + "{{$key}}"

// ------------------------------------------------------------- settings --
val SETTING_FA = mapOf(
    "voice" to "گوینده", "text_from" to "متن از مرحله‌ی", "cover_folder" to "پوشه‌ی کاور", "max_files" to "حداکثر تصویر", "kind" to "نوع انتشار",
    "media_from" to "رسانه از مرحله‌ی", "cover_from" to "کاور از مرحله‌ی", "in_min" to "بعد از چند دقیقه", "after" to "بعد از مرحله‌ی", "delay_min" to "تأخیر (دقیقه)",
    "privacy" to "حریم", "site" to "سایت",
    "speaker" to "گوینده", "style" to "سبک خواندن", "folder" to "پوشه‌ی کاور", "where" to "کجا", "when" to "چه وقت", "at" to "ساعت", "time" to "ساعت انتشار",
    "story_same_day" to "استوری همان روز", "max_chars" to "حداکثر حرف", "min_chars" to "حداقل حرف", "language" to "زبان",
    "threshold" to "آستانه‌ی شباهت", "count" to "تعداد", "query" to "عبارت جست‌وجو", "workflow" to "کار خودکارساز", "banned_words" to "واژه‌های ممنوع",
    "aspect" to "قاب", "duration_s" to "مدت (ثانیه)",
)

fun settingLabelFa(key: String): String = SETTING_FA[key] ?: key

/** A setting's value as the editor's text (a string as it is, a number or flag in Latin digits, a list or object as compact JSON). */
fun settingText(e: JsonElement?): String = when (e) {
    null, JsonNull -> ""
    is JsonPrimitive -> e.contentOrNull ?: ""
    else -> e.toString()
}

/** The edited text back as a value of the same kind as [old] (a number stays a number, a list or object is parsed; else a string). */
fun settingFrom(text: String, old: JsonElement?): JsonElement = when (old) {
    is JsonPrimitive -> when {
        old.isString -> JsonPrimitive(text)
        old.booleanOrNull != null -> JsonPrimitive(text.trim().equals("true", ignoreCase = true))
        old.longOrNull != null -> text.trim().toLongOrNull()?.let { JsonPrimitive(it) } ?: text.trim().toDoubleOrNull()?.let { JsonPrimitive(it) } ?: old
        old.doubleOrNull != null -> text.trim().toDoubleOrNull()?.let { JsonPrimitive(it) } ?: old
        else -> JsonPrimitive(text)
    }
    is JsonObject, is JsonArray -> runCatching { Api.json.parseToJsonElement(text) }.getOrNull()?.takeIf { it::class == old::class } ?: old
    else -> JsonPrimitive(text)
}

/** The setting [key] of a step as text. */
fun StepDef.setting(key: String): String = settingText(settings[key])

fun StepDef.withSetting(key: String, value: JsonElement): StepDef = copy(settings = JsonObject(settings + (key to value)))

// ----------------------------------------------------------------- caps --
/** Did any cap rise from [old] to [new]? (A rise is 🔏 `line.caps`; a null cap is no limit, so null over a number is a rise.) */
fun capsRaised(old: LineCaps, new: LineCaps): Boolean {
    fun up(a: Long?, b: Long?): Boolean = (a != null && b == null) || (a != null && b != null && b > a)
    return up(old.runsPerDay?.toLong(), new.runsPerDay?.toLong()) || up(old.tokensPerRun, new.tokensPerRun) || up(old.opusPerDay?.toLong(), new.opusPerDay?.toLong())
}

/** The body of `PUT /lines/{ref}` for the parts the owner edited. */
fun lineBody(titleFa: String, schedule: String?, steps: List<StepDef>, caps: LineCaps, library: List<String>? = null, noteFa: String? = null): JsonObject {
    val out = mutableMapOf<String, JsonElement>()
    out["title_fa"] = JsonPrimitive(titleFa)
    out["schedule"] = schedule?.let { JsonPrimitive(it) } ?: JsonNull
    out["steps"] = Api.json.encodeToJsonElement(ListSerializer(StepDef.serializer()), steps)
    out["caps"] = Api.json.encodeToJsonElement(LineCaps.serializer(), caps)
    if (library != null) out["library"] = JsonArray(library.map { JsonPrimitive(it) })
    if (!noteFa.isNullOrBlank()) out["note_fa"] = JsonPrimitive(noteFa)
    return JsonObject(out)
}

// ---------------------------------------------------------------- library --
val ASSET_KIND_FA = mapOf(
    "cover_folder" to "پوشه‌ی کاور", "voice" to "صدا", "prompt" to "پرامپت", "pattern" to "الگو", "music" to "موسیقی", "brand" to "نشان",
)
fun assetKindFa(kind: String?): String = ASSET_KIND_FA[kind] ?: "فایل"

/** The kinds the library page offers, in order. */
val LIBRARY_KINDS = listOf("cover_folder", "voice", "prompt", "pattern")

fun assetKindIcon(kind: String?): DivanIcon = when (kind) {
    "cover_folder" -> DivanIcon.IMAGE
    "voice" -> DivanIcon.MIC
    "prompt" -> DivanIcon.EDIT
    "pattern" -> DivanIcon.SEARCH
    "music" -> DivanIcon.MIC
    else -> DivanIcon.ATTACH
}

// --------------------------------------------------------------- calendar --
/** The week (Saturday to Friday) [offset] weeks from the one that holds today, as the calendar asks it: from and to are days. */
fun calendarWeek(offset: Int = 0, today: LocalDate = HqClock.today()): Pair<String, String> {
    val sinceSaturday = (today.dayOfWeek.value + 1) % 7
    val start = today.minusDays(sinceSaturday.toLong()).plusWeeks(offset.toLong())
    return start.toString() to start.plusDays(6).toString()
}

/** Cost text of a run or step: «12.4K واحد، $0.31» (Latin figures), blank when there is none. */
fun costText(tokens: Long, usd: JsonPrimitive?): String {
    val parts = mutableListOf<String>()
    if (tokens > 0) parts += com.coinepro.hq.core.format.tokens(tokens) + " واحد"
    usd?.contentOrNull?.toDoubleOrNull()?.takeIf { it > 0 }?.let { parts += com.coinepro.hq.core.format.usd(it) }
    return parts.joinToString("، ")
}
