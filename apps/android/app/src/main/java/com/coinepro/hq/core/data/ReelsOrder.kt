package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.isRealModel
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.net.BestHour
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.MemberPublish
import com.coinepro.hq.core.net.Narrator
import com.coinepro.hq.core.net.SessionPublish
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull

// Contract §47–§53 ⟨1.31⟩ in the owner's words: the ledger of topics, the narrator, the best hour, a standing routine, a scheduled post
// taken back, a picture that goes out as a JPEG, and how hard the workshop thought. Pure functions: the unit tests read them.

/** Latin digits as Persian ones («21:00» → «۲۱:۰۰»): an hour or a count the owner reads in a sentence. */
fun faDigits(s: String): String = s.map { if (it in '0'..'9') '۰' + (it - '0') else it }.joinToString("")

// ------------------------------------------------------------------ §47 the ledger --
/** «۴۲ موضوع · ۴۰ نمونه», or that nothing is in the ledger yet. */
fun ledgerCountsFa(topics: Int, references: Int): String =
    if (topics <= 0 && references <= 0) "هنوز چیزی ثبت نشده" else "${faNum(topics.coerceAtLeast(0))} موضوع · ${faNum(references.coerceAtLeast(0))} نمونه"

/** Where a line of the ledger came from, as a quiet word; a source this app does not know says nothing. */
fun topicSourceFa(source: String): String = when (source) {
    "claim" -> "ثبت کارمند"
    "package" -> "از بسته‌ی منتشرشده"
    "owner" -> "افزوده‌ی شما"
    else -> ""
}

/** A link as the owner typed it, when it is one (`http://` or `https://`). */
fun linkOf(raw: String): String? = raw.trim().takeIf { Regex("^https?://\\S+\\.\\S+$", RegexOption.IGNORE_CASE).matches(it) }

/**
 * The line the owner adds himself («این را قبلاً گفته‌ایم»), of the kind of the filter he is on: a topic is its words; a reference is its
 * link, with its words when he wrote any. Null while there is nothing to add yet (no words; a reference without its link).
 */
fun topicBody(kind: String, text: String, url: String): JsonObject? {
    val title = text.trim().take(300)
    if (kind == "reference") {
        val link = linkOf(url) ?: return null
        return buildJsonObject {
            put("kind", JsonPrimitive("reference"))
            put("url", JsonPrimitive(link.take(2000)))
            if (title.isNotEmpty()) put("title_fa", JsonPrimitive(title))
        }
    }
    if (title.length < 2) return null
    return buildJsonObject { put("kind", JsonPrimitive("topic")); put("title_fa", JsonPrimitive(title)) }
}

// ------------------------------------------------------------------ §48 the narrator --
/** The narrator in one line: «Charon · آرام و مطمئن», or that none is set (a model then chooses each time). */
fun narratorLineFa(n: Narrator): String =
    if (!n.set) "تنظیم نشده؛ هر بار مدل انتخاب میکند" else listOfNotNull(n.voice.ifBlank { null }, n.styleFa.trim().ifBlank { null }).joinToString(" · ")

fun genderFa(gender: String): String = when (gender) { "female" -> "زن"; "male" -> "مرد"; else -> "" }

/** The one step of the owner there is here: the hub fell out of its account of the speech service. Null otherwise. */
fun narratorStepFa(n: Narrator): String? =
    if (n.aistudio == "signed_out") "گوینده‌ی هاب از حسابش بیرون افتاده؛ یک بار ورود شما لازم است." else null

/** `PUT /companies/{code}/narrator`: the voice, and the style when he wrote one (at most 500 letters). */
fun narratorBody(voice: String, styleFa: String?): JsonObject = buildJsonObject {
    put("voice", JsonPrimitive(voice.trim()))
    styleFa?.split(Regex("\\s+"))?.filter { it.isNotEmpty() }?.joinToString(" ")?.take(500)?.ifBlank { null }?.let { put("style_fa", JsonPrimitive(it)) }
}

// ------------------------------------------------------------------ §49 the best hour --
/** The hour as he reads it («۲۱:۰۰»); null when the hub named none. */
fun bestClockFa(b: BestHour?): String? = b?.hour?.let { clockOf(it) ?: it.trim().ifBlank { null } }?.let(::faDigits)

/**
 * What stands under «بهترین ساعت، خودکار»: with enough data, the hour and what it rests on; without, what is missing and what the hub
 * does till then (his fixed hour [fixedAt] when he set one, else the moment the package is ready).
 */
fun bestHourLines(b: BestHour, fixedAt: String?): List<String> {
    val clock = bestClockFa(b)
    return if (b.enough && clock != null) listOfNotNull("بهترین ساعت این حساب: $clock", b.noteFa.trim().ifBlank { null })
    else listOfNotNull(
        b.noteFa.trim().ifBlank { null },
        if (clockOf(fixedAt) != null) "تا آن وقت: ساعت ثابت شما" else "تا آن وقت: همان لحظه‌ی آماده شدن",
    )
}

/** A member's standing word in one line; with «بهترین ساعت» the hub chooses the hour ([best]: that hour, when it is known). */
fun standingLineFa(p: MemberPublish, best: BestHour? = null): String = when {
    !p.auto -> "هر بار بپرس"
    else -> listOfNotNull(
        "خودکار",
        // the hour first: the line is one row, and the hour is what he looks for
        if (p.best) listOfNotNull("بهترین ساعت", bestClockFa(best?.takeIf { it.enough })).joinToString(" ") else clockOf(p.at)?.let { "ساعت $it" },
        p.account?.let { "⁦@$it⁩" }, "استوری هم".takeIf { p.story },
    ).joinToString(" · ")
}

/** «بهترین ساعت (۲۱:۰۰)» as a time of the publish sheet: offered when the panel carries an hour for the account he chose. */
fun bestChoice(best: BestHour?, account: String?): BestHour? =
    best?.takeIf { it.at != null && (it.account == null || account == null || it.account.equals(account.removePrefix("@"), ignoreCase = true)) }

// ------------------------------------------------------------------ §50 a standing routine --
/** `POST /routines`: the sentence, and the session it is said in when its ref is an order's (the hub takes no other). */
fun routineBody(sentence: String, order: String?, company: String? = null): JsonObject = buildJsonObject {
    put("sentence_fa", JsonPrimitive(sentence.trim().take(1000)))
    order?.takeIf { Regex("^F-\\d{4,}$").matches(it) }?.let { put("order", JsonPrimitive(it)) }
    company?.takeIf { Regex("^[A-Z][A-Z0-9]{1,9}$").matches(it) }?.let { put("company", JsonPrimitive(it)) }
}

/** A sentence long enough to send (the hub takes three letters at least). */
fun routineReady(sentence: String): Boolean = sentence.trim().length >= 3

// ------------------------------------------------------------------ §51 a scheduled post taken back --
/** The hub's word on a publication whose cancel is on its way to IG-Hub (its state stays till the answer). */
const val CANCELLING_FA = "در حال لغو"

fun cancelling(p: SessionPublish): Boolean = p.state != "cancelled" && p.noteFa?.trim() == CANCELLING_FA

/** «لغو» is offered on a publication that has its job and is not out yet (set for an hour, or on its way), unless it is being cancelled. */
fun cancellable(p: SessionPublish): Boolean = !p.job.isNullOrBlank() && (p.state == "scheduled" || p.state == "publishing") && !cancelling(p)

/** A publication's state in a word, for a list of them. */
fun publishStateFa(state: String): String = when (state) {
    "publishing" -> "در حال انتشار"
    "scheduled" -> "زمان‌بندی شد"
    "published" -> "منتشر شد"
    "failed" -> "انجام نشد"
    "waiting_seal" -> "منتظر مُهر"
    "waiting_setup" -> "در حال وصل شدن"
    "cancelled" -> "لغو شد"
    else -> state
}

/** The answer of a cancel in the list it came from: the same job replaced, everything else as it was. */
fun withPublish(list: List<SessionPublish>, out: SessionPublish): List<SessionPublish> =
    if (out.job != null && list.any { it.job == out.job }) list.map { if (it.job == out.job) out else it } else list

// ------------------------------------------------------------------ §52 a picture goes out as a JPEG --
private val NOT_JPEG_MIME = setOf("image/png", "image/webp", "image/heic")
private val NOT_JPEG_EXT = listOf(".png", ".webp", ".heic")

/** A picture Instagram does not take as it is (PNG, WebP, HEIC by its type or its name): the hub sends a JPEG made from it. */
fun goesAsJpeg(f: FileRef?): Boolean {
    if (f == null) return false
    val name = f.name.trim().lowercase()
    return f.mime.trim().lowercase() in NOT_JPEG_MIME || NOT_JPEG_EXT.any { name.endsWith(it) }
}

const val JPEG_LINE_FA = "این تصویر هنگام انتشار خودکار به JPEG تبدیل میشود."

// ------------------------------------------------------------------ §53 effort --
/** How hard the model thought, in a word; null for a level this app does not know (nothing is shown then). */
fun effortFa(effort: String?): String? = when (effort?.trim()?.lowercase()) {
    "low" -> "کم"
    "medium" -> "متوسط"
    "high" -> "زیاد"
    "xhigh" -> "خیلی زیاد"
    "max" -> "بیشترین دقت"
    else -> null
}

/**
 * How an output was made, from its `produced_with`: the model by the app's own name and its effort («Opus 5.5 · بیشترین دقت») when the
 * hub says both; else the hub's own label («قاعده‌محور، بدون مدل»); else the model alone. Null when it says none of these.
 */
fun madeWithFa(producedWith: JsonObject): String? {
    fun s(k: String) = (producedWith[k] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.ifBlank { null }
    val model = s("model")?.takeIf(::isRealModel)
    val effort = effortFa(s("effort"))
    return when {
        model != null && effort != null -> "${modelLabel(model)} · $effort"
        s("label_fa") != null -> s("label_fa")
        model != null -> modelLabel(model)
        else -> null
    }
}
