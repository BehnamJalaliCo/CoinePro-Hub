package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.TalkAudio
import com.coinepro.hq.core.net.TalkCard
import com.coinepro.hq.core.net.TalkPersona
import com.coinepro.hq.core.net.VoiceEngine
import com.coinepro.hq.core.net.VoiceMeter
import com.coinepro.hq.core.net.VoicePrice
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import java.util.Locale
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull

// Contract §32 ⟨1.14⟩ in the owner's words: the personas, the modes, the cards, the light of each voice engine, the meter and its cap, the
// key kept out of the composer, the answer's stream, the order sentences are played in and the hands-free loop. Pure functions: the unit
// tests read them directly.

// ---------------------------------------------------------------- personas --
/** The four standing personas, in the order their faces sit at the top of the talk screen (§32.1). */
val FIXED_PERSONAS = listOf("secretary", "overseer", "assistant", "advisor")

val PERSONA_FA = mapOf("secretary" to "منشی هلدینگ", "overseer" to "ناظر کل", "assistant" to "دستیار شخصی", "advisor" to "مشاور کل", "manager" to "مدیر")

/** The role keys of a manager in the owner's words (the `+` face asks company, then role). */
val TALK_ROLE_FA = mapOf("ceo" to "مدیرعامل", "media" to "مدیر رسانه", "marketing" to "مدیر بازاریابی", "product" to "مدیر محصول", "sales" to "مدیر فروش", "finance" to "مدیر مالی", "tech" to "مدیر فنی", "support" to "مدیر پشتیبانی")

/** What a persona is called: the hub's title, else the standing name, else the role of a manager. */
fun personaTitle(p: TalkPersona): String = p.titleFa.ifBlank { PERSONA_FA[p.key] ?: TALK_ROLE_FA[p.role] ?: "مدیر" }

/** The title for a persona id (`secretary`, `ceo@TY`) when the hub's list has no entry for it. */
fun personaIdTitle(id: String, known: List<TalkPersona>): String =
    known.firstOrNull { it.id == id }?.let(::personaTitle) ?: PERSONA_FA[id] ?: (if (isPlayer(id)) participantKeyTitle(id) else null) ?: TALK_ROLE_FA[id.substringBefore('@')] ?: "مدیر"

/** The faces, in order: the standing four (always, even before the hub lists them), then every manager in the room. */
fun faceOrder(known: List<TalkPersona>, present: List<String>): List<TalkPersona> {
    val fixed = FIXED_PERSONAS.map { k -> known.firstOrNull { it.key == k } ?: TalkPersona(key = k, titleFa = PERSONA_FA.getValue(k)) }
    val managers = present.filter { it !in FIXED_PERSONAS }.map { id ->
        known.firstOrNull { it.id == id } ?: TalkPersona(key = "manager", role = id.substringBefore('@'), company = id.substringAfter('@', "").ifBlank { null }, titleFa = personaIdTitle(id, known))
    }
    return fixed + managers
}

val TALK_MODE_FA = mapOf("consult" to "مشورت", "work" to "جلسه‌ی کاری")
val TALK_MODE_HINT_FA = mapOf(
    "consult" to "فقط حرف میزنیم؛ هیچ کاری ساخته نمیشود.",
    "work" to "کارها جمع میشود و در پایان جلسه یک صورت‌جلسه پیشنهاد میشود.",
)

// ------------------------------------------------------------------- cards --
data class CardKindInfo(val fa: String, val run: String, val dismiss: String = "نه")

/** Each kind of card, what it is called and what its «اجرا کن» does. */
val CARD_KIND_FA: Map<String, CardKindInfo> = mapOf(
    "order" to CardKindInfo("فرمان", "فرمان بده"),
    "ask" to CardKindInfo("پرسش عمیق", "بپرس"),
    "hire" to CardKindInfo("استخدام", "اجرا کن"),
    "decision" to CardKindInfo("تصمیم", "برو به تصمیم"),
    "planner" to CardKindInfo("یادآوری", "در پلنر بگذار"),
    "rule" to CardKindInfo("قانون", "اجرا کن"),
    "automation" to CardKindInfo("اتوماسیون", "اجرا کن"),
    "minutes" to CardKindInfo("صورت‌جلسه", "اجرا کن"),
    "invite" to CardKindInfo("دعوت", "بیاور"),
    // ⟨1.17⟩ §35.4 the work done in place, from inside a session.
    "delegate" to CardKindInfo("سپردن", "بسپار"),
    "budget" to CardKindInfo("بودجه", "بودجه بده"),
    "group" to CardKindInfo("کارگروه", "به کارگروه ببر"),
    "line" to CardKindInfo("خط تولید", "راه بینداز"),
)

fun cardInfo(kind: String): CardKindInfo = CARD_KIND_FA[kind] ?: CardKindInfo("کارت", "اجرا کن")

/** A card's state in words and tone; an offered card says nothing (its buttons are there). */
fun cardStateFa(state: String): Pair<String, Tone>? = when (state) {
    "done" -> "انجام شد" to Tone.POS
    "dismissed" -> "کنار گذاشته شد" to Tone.SILVER
    "failed" -> "انجام نشد" to Tone.NEG
    else -> null
}

/** The route of the first thing a card made (an order, a decision…), for the «ببین» beside «انجام شد». */
fun madeRoute(ref: String): String? = com.coinepro.hq.core.data.Refs.normalize(ref)

/** The fields of a card's payload the owner may edit, with the words that name them. Keys the hub adds that are not here stay as they are. */
val PAYLOAD_FIELD_FA = mapOf(
    "title" to "عنوان", "title_fa" to "عنوان", "brief" to "شرح", "brief_fa" to "شرح", "body" to "متن", "body_fa" to "متن", "text" to "متن", "text_fa" to "متن",
    "question" to "پرسش", "question_fa" to "پرسش", "summary" to "خلاصه", "summary_fa" to "خلاصه", "due" to "موعد", "due_at" to "موعد", "due_date" to "موعد",
    "company" to "شرکت", "department" to "دپارتمان", "at" to "زمان", "note" to "یادداشت", "note_fa" to "یادداشت", "sentence_fa" to "جمله",
)

/** One editable field of a payload: where it sits ([path]: a key, or `tasks/2/title`), its words, its value. */
data class PayloadField(val path: List<String>, val label: String, val value: String, val group: String? = null)

/** The payload's top-level text fields, and the fields of each object of a list (the minutes' tasks), in the order the hub wrote them. */
fun payloadFields(payload: JsonObject): List<PayloadField> = buildList {
    for ((k, v) in payload) {
        when {
            v is JsonPrimitive && v.contentOrNull != null && k in PAYLOAD_FIELD_FA && v.isString -> add(PayloadField(listOf(k), PAYLOAD_FIELD_FA.getValue(k), v.content))
            v is kotlinx.serialization.json.JsonArray -> v.forEachIndexed { i, item ->
                val o = item as? JsonObject ?: return@forEachIndexed
                for ((ik, iv) in o) {
                    if (iv is JsonPrimitive && iv.isString && ik in PAYLOAD_FIELD_FA) add(PayloadField(listOf(k, i.toString(), ik), PAYLOAD_FIELD_FA.getValue(ik), iv.content, group = "مورد ${i + 1}"))
                }
            }
            else -> Unit
        }
    }
}

/** The payload with the owner's edits written back at their paths; everything else is kept as the hub sent it. */
fun applyPayloadEdits(payload: JsonObject, edits: Map<List<String>, String>): JsonObject {
    fun put(e: JsonElement, path: List<String>, value: String): JsonElement = when {
        path.isEmpty() -> JsonPrimitive(value)
        e is JsonObject -> JsonObject(e.mapValues { (k, v) -> if (k == path.first()) put(v, path.drop(1), value) else v })
        e is kotlinx.serialization.json.JsonArray -> kotlinx.serialization.json.JsonArray(e.mapIndexed { i, v -> if (i.toString() == path.first()) put(v, path.drop(1), value) else v })
        else -> e
    }
    var out: JsonElement = payload
    for ((path, v) in edits) out = put(out, path, v)
    return out as JsonObject
}

// -------------------------------------------------------- engines, the light --
/** The light of one engine (§32.5): green `ok`, yellow `checking`, red `missing` and `failing`, amber `capped`. */
enum class Light { OK, CHECKING, RED, CAPPED }

fun lightOf(state: String): Light = when (state) {
    "ok" -> Light.OK
    "checking" -> Light.CHECKING
    "capped" -> Light.CAPPED
    else -> Light.RED
}

fun lightFa(state: String): String = when (state) {
    "ok" -> "آماده"
    "checking" -> "در حال سنجش"
    "capped" -> "سقف ماه پر شد"
    "missing" -> "کلید ندارد"
    else -> "کار نمیکند"
}

/** What to do about a light that is not green, in one sentence, from the state and the hub's reason. */
fun lightFix(state: String, reason: String?): String? {
    val r = reason.orEmpty()
    return when {
        state == "ok" -> null
        state == "checking" -> "کلید رسید و دارد سنجیده میشود؛ چند ثانیه صبر کن."
        state == "capped" -> "سقف ماه پر شده است. اگر میخواهی، سقف را از کنتور بالا ببر؛ تا آن موقع صدای بعدیِ زنجیره حرف میزند."
        state == "missing" -> "با دکمه‌ی کلید، کلید را بده."
        "کلید درست نیست" in r -> "کلید تازه از AI Studio بگیر و با دکمه‌ی کلید بده."
        "دسترسی ندارد" in r -> "در پروژه‌ی گوگل دسترسی به مدل صدا را روشن کن، یا کلیدی از پروژه‌ی دیگر بده."
        "صورتحساب" in r -> "صورتحساب پروژه را در گوگل فعال کن؛ بعد دوباره بسنج."
        "سهمیه" in r -> "سهمیه‌ی گوگل تمام شده؛ کمی بعد دوباره بسنج یا سهمیه را بالا ببر."
        else -> "کلید را دوباره بده یا بسنج."
    }
}

/** The engines the room speaks with: each present persona's own engine, once, in order. */
fun enginesInUse(personas: List<TalkPersona>, present: List<String>): List<String> =
    (present.ifEmpty { FIXED_PERSONAS }).mapNotNull { id -> personas.firstOrNull { it.id == id }?.voice?.engine?.takeIf { it.isNotBlank() } }.distinct()

/** The state shown for an engine now: what the last stream event said overrides what the list held. */
fun lightState(engine: VoiceEngine, live: Map<String, Pair<String, String?>>): Pair<String, String?> = live[engine.key] ?: (engine.state to engine.reasonFa)

// --------------------------------------------------------------- the key --
/** The shape of a Google API key (§32.5), used until the hub's list brings its own. */
const val GOOGLE_KEY_PATTERN = "AIza[0-9A-Za-z_-]{35}"

/** The patterns of every engine (each engine of a provider carries the same one). */
fun keyPatterns(engines: List<VoiceEngine>): List<String> = (engines.mapNotNull { it.keyPattern?.takeIf { p -> p.isNotBlank() } } + GOOGLE_KEY_PATTERN).distinct()

/** The key-shaped string in [text], or null: it is moved to the secure sheet and never reaches the composer, a turn, a log or a model. */
fun extractKey(text: String, patterns: List<String>): String? {
    if (text.length < 8) return null
    for (p in patterns) {
        val re = runCatching { Regex(p) }.getOrNull() ?: continue
        re.find(text)?.let { return it.value }
    }
    return null
}

fun containsKey(text: String, patterns: List<String>): Boolean = extractKey(text, patterns) != null

/** [text] without the key in it, spaces tidied. */
fun withoutKey(text: String, key: String): String = text.replace(key, "").replace(Regex("\\s{2,}"), " ").trim()

/** The provider an engine belongs to (for `PUT /voice/providers/{provider}/secret`). */
fun providerOf(engines: List<VoiceEngine>, engine: String?): String = engines.firstOrNull { it.key == engine }?.provider?.takeIf { it != "local" } ?: "google"

// ----------------------------------------------------------- meter and cap --
/** 0.4 → "0.4", 0.42 → "0.42", 10.0 → "10", 0.0049 → "<0.01": at most two decimals, Latin digits. */
fun usdNumber(v: Double): String {
    if (v > 0 && v < 0.01) return "0.01"
    val s = String.format(Locale.US, "%.2f", v)
    return s.trimEnd('0').trimEnd('.')
}

fun usdText(v: Double): String = "${usdNumber(v)} $"

/** The counter's words: «0.42 $ از 10 $ این ماه», or without the cap «0.42 $ این ماه» (numbers stay Latin). */
fun meterChip(m: VoiceMeter?, period: String = "month"): String {
    val m1 = m ?: return "کنتور صدا"
    val spent = usdText(m1.voiceUsd)
    val per = if (period == "today") "امروز" else "این ماه"
    return if (m1.capUsd != null) "$spent از ${usdText(m1.capUsd)} $per" else "$spent $per"
}

/** How much of the cap is spent, 0..1 (more than 1 is clamped); null with no cap. */
fun capFraction(m: VoiceMeter?): Float? = m?.capUsd?.takeIf { it > 0 }?.let { (m.voiceUsd / it).toFloat().coerceIn(0f, 1f) }

/** The meter's tone: calm until the owner's warning point, then warm, then red at the cap. */
fun meterTone(m: VoiceMeter?, warnAt: Double = 0.8): Tone {
    val cap = m?.capUsd?.takeIf { it > 0 } ?: return Tone.NEUTRAL
    val f = m.voiceUsd / cap
    return when {
        f >= 1.0 -> Tone.NEG
        f >= warnAt -> Tone.WARN
        else -> Tone.POS
    }
}

val CAP_PRESETS = listOf(5.0, 10.0, 20.0)

/** The cap the owner typed (Latin or Persian digits, a point or a Persian decimal mark); null when it is not a sensible number. */
fun parseCap(text: String): Double? {
    val t = text.trim().map { ch ->
        when (ch) {
            in '۰'..'۹' -> '0' + (ch - '۰')
            in '٠'..'٩' -> '0' + (ch - '٠')
            '٫', ',', '،' -> '.'
            else -> ch
        }
    }.joinToString("")
    val v = t.toDoubleOrNull() ?: return null
    return v.takeIf { it > 0 && it <= 100_000 }
}

private val GREGORIAN_FA = listOf("ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر")

/** The scheduled price change in words: «از 1 ژانویه قیمت دو برابر میشود» (null with no change ahead). */
fun priceChangeFa(price: VoicePrice): String? {
    val next = price.next ?: return null
    val from = runCatching { LocalDate.parse(next.from.take(10)) }.getOrNull() ?: return null
    val base = price.audioOutPerM.takeIf { it > 0 } ?: return null
    val ratio = next.audioOutPerM / base
    val how = when {
        ratio in 1.95..2.05 -> "دو برابر میشود"
        ratio in 2.95..3.05 -> "سه برابر میشود"
        ratio in 1.45..1.55 -> "یک‌ونیم برابر میشود"
        ratio > 1.05 -> "${String.format(Locale.US, "%.1f", ratio).trimEnd('0').trimEnd('.')} برابر میشود"
        ratio < 0.95 -> "ارزان‌تر میشود"
        else -> "عوض میشود"
    }
    return "از ${from.dayOfMonth} ${GREGORIAN_FA[from.monthValue - 1]} قیمت $how"
}

/** Days from [today] to the scheduled price change, or null (§32.6: the app warns 14 days before). */
fun daysToPriceChange(price: VoicePrice, today: LocalDate): Long? {
    val from = runCatching { LocalDate.parse(price.next?.from.orEmpty().take(10)) }.getOrNull() ?: return null
    return ChronoUnit.DAYS.between(today, from).takeIf { it >= 0 }
}

/** The warning the app shows 14 days before a price change (and on the day), else null. */
fun priceWarning(engines: List<VoiceEngine>, inUse: List<String>, today: LocalDate): String? =
    engines.filter { it.key in inUse }.firstNotNullOfOrNull { e ->
        val d = daysToPriceChange(e.price, today)
        if (d != null && d <= 14) priceChangeFa(e.price) else null
    }

/** The honest line under the meter's details (§32.6). */
const val METER_HONEST_FA = "این عدد توکن‌های خود گوگل ضربدر جدول قیمت است؛ صورتحساب گوگل (مالیات، ارز) ممکن است کمی فرق کند."

/** A sample's cost, said before the owner plays it again. */
fun sampleCostFa(usd: Double): String = if (usd <= 0) "رایگان بود" else "این نمونه حدود ${usdText(usd)} خرج داشت"

val TALK_PERIOD_FA = mapOf("today" to "امروز", "month" to "این ماه")

/** Seconds as «2 دقیقه و 5 ثانیه» for the meter's lines (Latin figures). */
fun secondsFa(s: Double): String {
    val t = s.toLong().coerceAtLeast(0)
    return when {
        t < 60 -> "$t ثانیه"
        t % 60 == 0L -> "${t / 60} دقیقه"
        else -> "${t / 60} دقیقه و ${t % 60} ثانیه"
    }
}

// ------------------------------------------------------------ the stream --
/** One event of a turn's answer (§32.2): the text as it is written, a finished sentence, the sentence's audio, a card, an invitation, the meter, the end. */
sealed interface TalkEvent {
    data class Text(val delta: String) : TalkEvent
    data class Say(val text: String) : TalkEvent
    data class Audio(val audio: TalkAudio) : TalkEvent
    data class CardOffered(val card: TalkCard) : TalkEvent
    data class Invite(val role: String, val company: String?) : TalkEvent
    data class Meter(val usd: Double?, val raw: JsonObject) : TalkEvent
    /** The hub is running a tool (a quiet sound plays); not part of the contract's list, read when sent. */
    data class Tool(val running: Boolean) : TalkEvent
    data object Done : TalkEvent
    data class Error(val code: String, val reasonFa: String) : TalkEvent
}

private fun JsonObject.str(vararg keys: String): String? = keys.firstNotNullOfOrNull { k -> (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull }
private fun JsonObject.num(vararg keys: String): Double? = keys.firstNotNullOfOrNull { k -> (this[k] as? JsonPrimitive)?.let { it.doubleOrNull ?: it.contentOrNull?.toDoubleOrNull() } }

/**
 * An SSE event of `GET /talk/turns/{id}/events` as the app reads it. The data is JSON; a text that is not an object stands for the
 * delta or sentence itself. An event the app does not know is null (it is ignored, never a failure).
 */
fun parseTalkEvent(type: String?, data: String): TalkEvent? {
    val el = runCatching { Api.json.parseToJsonElement(data) }.getOrNull()
    val o = el as? JsonObject ?: JsonObject(emptyMap())
    val raw = (el as? JsonPrimitive)?.contentOrNull ?: data
    return when (type) {
        "text" -> TalkEvent.Text(o.str("delta", "text", "d") ?: if (el is JsonPrimitive) raw else return null)
        "say" -> TalkEvent.Say(o.str("text", "say_fa", "sentence") ?: if (el is JsonPrimitive) raw else return null)
        "audio" -> {
            val id = o.str("file_id") ?: return null
            TalkEvent.Audio(TalkAudio(o.num("seq")?.toInt() ?: 0, id, o.num("seconds") ?: 0.0, o.str("engine").orEmpty()))
        }
        "card" -> {
            val c = (o["card"] as? JsonObject) ?: o
            val card = runCatching { Api.json.decodeFromJsonElement(TalkCard.serializer(), c) }.getOrNull() ?: return null
            TalkEvent.CardOffered(card)
        }
        "invite" -> {
            val role = o.str("role") ?: return null
            TalkEvent.Invite(role, o.str("company"))
        }
        "meter" -> TalkEvent.Meter(o.num("voice_usd", "usd"), o)
        "tool", "tool_start" -> TalkEvent.Tool(true)
        "tool_end", "tool_done" -> TalkEvent.Tool(false)
        "done" -> TalkEvent.Done
        "error" -> TalkEvent.Error(o.str("code") ?: "error", o.str("reason_fa", "message_fa") ?: "جواب ساخته نشد؛ دوباره بگو.")
        else -> null
    }
}

// ------------------------------------------------------ playing in order --
/**
 * Sentences are played in the order of their `seq`, however the audio events arrive: [offer] holds a sentence until all before it have
 * been played, [drain] hands over those that are ready. A sentence that never comes (the hub spoke the next one in text only) is
 * stepped over by [skip] after a wait, so the voice never stalls on a gap.
 */
class AudioOrder<T> {
    private val waiting = sortedMapOf<Int, T>()
    private var next = 0
    val pending: Int get() = waiting.size

    fun offer(seq: Int, item: T) {
        if (seq >= next) waiting[seq] = item
    }

    fun drain(): List<T> {
        val out = mutableListOf<T>()
        while (true) {
            val item = waiting.remove(next) ?: break
            out += item
            next++
        }
        return out
    }

    /** Gives up on the missing sentence: the lowest one waiting is next. Returns what became ready. */
    fun skip(): List<T> {
        if (waiting.isEmpty()) return emptyList()
        val lowest = waiting.firstKey()
        next = lowest
        return drain()
    }

    fun reset() { waiting.clear(); next = 0 }
}

// ------------------------------------------------------------ hands-free --
/** The silence that ends a hands-free turn (`TALK_SILENCE_MS`, §32.7). */
const val TALK_SILENCE_MS = 1_200L

/** The loop of hands-free talk: listen → the owner speaks → silence ends the turn → the answer is spoken → listen again. */
enum class HandsFree { OFF, LISTENING, HEARING, SENT, ANSWERING }

enum class HandsFreeEvent { TOGGLE_ON, TOGGLE_OFF, SPEECH_STARTED, SILENCE, SENT_OK, SEND_FAILED, ANSWER_STARTED, ANSWER_ENDED, BARGE_IN }

fun handsFreeNext(s: HandsFree, e: HandsFreeEvent): HandsFree = when {
    e == HandsFreeEvent.TOGGLE_OFF -> HandsFree.OFF
    e == HandsFreeEvent.TOGGLE_ON -> if (s == HandsFree.OFF) HandsFree.LISTENING else s
    s == HandsFree.OFF -> HandsFree.OFF
    s == HandsFree.LISTENING && e == HandsFreeEvent.SPEECH_STARTED -> HandsFree.HEARING
    s == HandsFree.HEARING && e == HandsFreeEvent.SILENCE -> HandsFree.SENT
    s == HandsFree.SENT && e == HandsFreeEvent.SENT_OK -> HandsFree.ANSWERING
    s == HandsFree.SENT && e == HandsFreeEvent.SEND_FAILED -> HandsFree.LISTENING
    s == HandsFree.ANSWERING && e == HandsFreeEvent.ANSWER_ENDED -> HandsFree.LISTENING
    // The owner spoke over the answer: the answer stops and what he says is the next turn.
    s == HandsFree.ANSWERING && e == HandsFreeEvent.BARGE_IN -> HandsFree.HEARING
    // Silence with nothing said: keep listening.
    s == HandsFree.HEARING && e == HandsFreeEvent.ANSWER_ENDED -> HandsFree.HEARING
    else -> s
}

/** Whether the microphone is open in this state (it stays open while the answer plays, to hear a barge-in). */
fun HandsFree.micOpen(): Boolean = this == HandsFree.LISTENING || this == HandsFree.HEARING || this == HandsFree.ANSWERING

val HANDS_FREE_FA = mapOf(
    HandsFree.OFF to "دست‌آزاد خاموش است",
    HandsFree.LISTENING to "گوش میدهم…",
    HandsFree.HEARING to "میشنوم…",
    HandsFree.SENT to "فرستادم…",
    HandsFree.ANSWERING to "جواب میدهد؛ هر وقت خواستی حرف بزن.",
)

/** A turn's `source` for how the owner gave it. */
const val SOURCE_TYPED = "typed"
const val SOURCE_HOLD = "hold"
const val SOURCE_HANDSFREE = "handsfree"

// ----------------------------------------------------- conversations list --
/** A conversation as the list shows it: its title, else the persona and the date. */
fun conversationTitle(titleFa: String, personaTitle: String): String = titleFa.ifBlank { "گفتگو با $personaTitle" }

/** The conversations of [persona] first-used first, the newest conversation of each persona for the face tap. */
fun latestOf(conversations: List<com.coinepro.hq.core.net.TalkConversation>, persona: String): com.coinepro.hq.core.net.TalkConversation? =
    conversations.filter { it.persona == persona || persona in it.presentIds }.maxByOrNull { it.lastTurnAt ?: it.startedAt ?: "" }
