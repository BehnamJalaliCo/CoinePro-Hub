package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull

// Contract §37 ⟨1.19⟩: erasing for good. The owner, 2026-11-06: «… یه گزینه حذف هم داشته باشه که اصلا شاید یه سشن رو من میخوام پاک کنم
// اصلا نباشه و قابلیت پاک کردن از بایگانی هم بذار». Hiding (§35) stays; erasing is for good, the owner's alone, and sealed (🔏).

/** What can be erased: a session (§37.1), an archive record or one output (§37.2); each with its seal's action. */
enum class EraseKind(val key: String, val action: String, val fa: String) {
    SESSION("session", "session.erase", "جلسه"),
    RECORD("archive_record", "archive.erase", "سند بایگانی"),
    OUTPUT("output", "output.erase", "خروجی"),
    ;

    companion object {
        fun of(key: String?): EraseKind? = entries.firstOrNull { it.key == key || (key == "record" && it == RECORD) }
    }
}

/** `GET …/erase/preview`: nothing changes. [counts] by name (`turns`, `files`, `outputs`, `works`, `notifications`, and whatever a kind
 *  adds); [keepsFa] says in plain Persian what stays. */
@Serializable
data class ErasePreview(
    val ref: String = "",
    val kind: String = "session",
    val titleFa: String = "",
    val counts: JsonObject = JsonObject(emptyMap()),
    val keepsFa: List<String> = emptyList(),
)

/** `POST …/erase` → what went. */
@Serializable
data class EraseOut(val ref: String = "", val erased: JsonObject = JsonObject(emptyMap()))

/** The counts the owner reads, in the order he reads them, with their Persian nouns. */
private val COUNT_FA = linkedMapOf(
    "turns" to "گفته", "files" to "فایل", "outputs" to "خروجی", "works" to "کار", "notifications" to "اعلان",
    "versions" to "نسخه", "decisions" to "تصمیم", "steps" to "قدم", "records" to "سند",
)

private fun faDigits(s: String): String = s.map { if (it in '0'..'9') '۰' + (it - '0') else it }.joinToString("")

/** «۱۲ گفته، ۳ فایل، ۲ خروجی»: every count above zero, in Persian digits (a count in a sentence); empty when there is none. */
fun eraseCountsFa(counts: JsonObject): String =
    COUNT_FA.mapNotNull { (k, fa) -> (counts[k] as? JsonPrimitive)?.longOrNull?.takeIf { it > 0 }?.let { "${faDigits(it.toString())} $fa" } }.joinToString("، ")

/** An `erase` decision card's payload (§37.3): the preview the card is bound to, flat or under `preview`, and the agent's reason. */
data class EraseCard(val kind: EraseKind?, val ref: String, val preview: ErasePreview, val whyFa: String?)

fun eraseCardOf(d: Decision): EraseCard {
    val p = d.payload
    val inner = (p["preview"] as? JsonObject) ?: p
    fun s(o: JsonObject, k: String) = (o[k] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
    val preview = ErasePreview(
        ref = s(inner, "ref") ?: s(p, "ref").orEmpty(),
        kind = s(inner, "kind") ?: s(p, "kind") ?: "session",
        titleFa = s(inner, "title_fa") ?: s(p, "title_fa").orEmpty(),
        counts = (inner["counts"] as? JsonObject) ?: (p["counts"] as? JsonObject) ?: JsonObject(emptyMap()),
        keepsFa = ((inner["keeps_fa"] ?: p["keeps_fa"]) as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }.orEmpty(),
    )
    // The kind as the card says it; a card that says none is drawn as a session's, and erases nothing by itself.
    return EraseCard(EraseKind.of(s(p, "kind") ?: s(inner, "kind")), preview.ref, preview, s(p, "why_fa"))
}

/** The decision kind an agent's erase proposal is (§37.3). */
const val ERASE_KIND = "erase"
