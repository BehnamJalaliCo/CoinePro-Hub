package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.AdCampaign
import com.coinepro.hq.core.net.CompetitorDaily
import com.coinepro.hq.core.net.RankDaily
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// Contract §31 ⟨1.13⟩ in the owner's words: the metric of a line's lessons, the newsletter's and automation's states, the kinds on the
// campaign calendar, an ad campaign's figures, a keyword's move and a competitor's figures. Pure functions: the unit tests read them directly.

val GROWTH_METRIC_FA = mapOf("views" to "بازدید", "reach" to "دیده‌شدن", "clicks" to "کلیک", "watch_s" to "ثانیه‌ی تماشا")
fun growthMetricFa(m: String?): String = GROWTH_METRIC_FA[m] ?: "نتیجه"

val NL_STATE_FA: Map<String, Pair<String, Tone>> = mapOf(
    "draft" to ("پیش‌نویس" to Tone.SILVER), "scheduled" to ("زمان‌بندی‌شده" to Tone.LAPIS), "sending" to ("در حال ارسال" to Tone.SILVER),
    "sent" to ("فرستاده شد" to Tone.POS), "cancelled" to ("لغو شد" to Tone.SILVER),
)

val CAL_KIND31_FA = mapOf("line" to "خط تولید", "newsletter" to "خبرنامه", "ad" to "تبلیغ", "campaign" to "کمپین", "manual" to "دستی")

/** The state of a calendar item in words (a line's run state, a campaign's, or an ad's). */
fun calStateFa(state: String?): Pair<String, Tone> = LINE_RUN_STATE_FA[state] ?: when (state) {
    "planned" -> "برنامه‌ریزی‌شده" to Tone.LAPIS
    "running" -> "در جریان" to Tone.SILVER
    "paused" -> "متوقف" to Tone.WARN
    "sent" -> "فرستاده شد" to Tone.POS
    else -> (state.orEmpty().ifBlank { "در برنامه" }) to Tone.SILVER
}

val AD_PLATFORM_FA = mapOf("google_ads" to "تبلیغات گوگل", "meta_ads" to "تبلیغات متا")
fun adPlatformFa(p: String?): String = AD_PLATFORM_FA[p] ?: (p ?: "تبلیغات")

val AD_ACTION_FA = mapOf("pause" to "متوقف کن", "notify" to "فقط خبر بده")

/** An ad campaign's last-30-days figures: what it spent, what came back, and the return (revenue over spend; null with nothing spent). */
data class AdFigures(val spend: Double, val revenue: Double, val clicks: Long, val conversions: Long) {
    val roas: Double? get() = if (spend > 0) revenue / spend else null
}

fun adFigures(c: AdCampaign): AdFigures = AdFigures(c.days.sumOf { it.spend }, c.days.sumOf { it.revenue }, c.days.sumOf { it.clicks }, c.days.sumOf { it.conversions })

/** «2.6×» (a return, Latin). */
fun roasText(r: Double?): String = if (r == null) "—" else String.format(java.util.Locale.US, "%.1f×", r)

/** A keyword's latest position, its position about a week before, and the move in places (positive: it rose). */
data class RankMove(val latest: Double?, val before: Double?, val approximate: Boolean) {
    val up: Int? get() = if (latest != null && before != null) (before - latest).toInt() else null
}

fun rankMove(rows: List<RankDaily>, keyword: String): RankMove {
    val mine = rows.filter { it.keyword.contentOrNull == keyword }.sortedBy { it.day }
    val withPos = mine.filter { it.position != null }
    val last = withPos.lastOrNull()
    val before = withPos.lastOrNull { last != null && it.day <= java.time.LocalDate.parse(last.day).minusDays(7).toString() } ?: withPos.firstOrNull()?.takeIf { it !== last }
    return RankMove(last?.position, before?.position, last?.source == "searxng")
}

/** A competitor's figure [key]: the latest value and the change since the first day in the window; null when it has none. */
fun competitorFigure(rows: List<CompetitorDaily>, competitor: String, key: String): Pair<Double, Double>? {
    val mine = rows.filter { it.competitor.contentOrNull == competitor && it.key == key }.sortedBy { it.day }
    val last = mine.lastOrNull() ?: return null
    return last.value to (last.value - mine.first().value)
}

/** New pages a competitor published in the window (the sum of the daily counts). */
fun competitorNewPages(rows: List<CompetitorDaily>, competitor: String): Double = rows.filter { it.competitor.contentOrNull == competitor && it.key == "new_pages" }.sumOf { it.value }

val COMPETITOR_KEY_FA = mapOf("followers" to "دنبال‌کننده", "subscribers" to "مشترک", "posts" to "پست", "new_pages" to "صفحه‌ی تازه")

val ACTION_KIND_FA = mapOf(
    "work.create" to "کار تازه میسازد", "line.run" to "یک خط تولید را اجرا میکند", "line.pause" to "یک خط تولید را مکث میکند", "notify.owner" to "به تو خبر میدهد",
    "notify.lead" to "به مدیر همان شرکت خبر میدهد", "ad.pause" to "تبلیغ را متوقف میکند", "n8n.run" to "یک کار خودکارساز را اجرا میکند",
)

/** An automation's rule in a line of words, for when the hub sent no `preview_fa`: «هر شنبه ساعت 10:00 › خط تولید را اجرا میکند». */
fun ruleLineFa(rule: JsonObject): String {
    val t = rule["trigger"] as? JsonObject
    val when_ = when ((t?.get("kind") as? JsonPrimitive)?.contentOrNull) {
        "schedule" -> scheduleFa((t["rrule"] as? JsonPrimitive)?.contentOrNull)
        "event" -> "وقتی رویداد ${(t["type"] as? JsonPrimitive)?.contentOrNull.orEmpty()} بیاید"
        "metric" -> "وقتی ${(t["key"] as? JsonPrimitive)?.contentOrNull.orEmpty()} ${(t["op"] as? JsonPrimitive)?.contentOrNull.orEmpty()} ${(t["value"] as? JsonPrimitive)?.contentOrNull.orEmpty()} شد"
        else -> "هر وقت شرطش برسد"
    }
    val acts = ((rule["actions"] as? JsonArray).orEmpty()).mapNotNull { ((it as? JsonObject)?.get("kind") as? JsonPrimitive)?.contentOrNull }.map { ACTION_KIND_FA[it] ?: it }
    return when_ + (if (acts.isNotEmpty()) " › " + acts.joinToString(" و ") else "")
}

val AUTO_STATE_FA: Map<String, Pair<String, Tone>> = mapOf("proposed" to ("منتظر مُهر" to Tone.GOLD), "on" to ("روشن" to Tone.POS), "off" to ("خاموش" to Tone.SILVER))

/** A company code the kit form accepts: a capital letter, then capitals and digits, 2 to 10 in all. */
fun validCompanyCode(s: String): Boolean = Regex("^[A-Z][A-Z0-9]{1,9}$").matches(s)
