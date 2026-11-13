package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.pct
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.BoardItem
import com.coinepro.hq.core.net.DmButton
import com.coinepro.hq.core.net.FlowSchedule
import com.coinepro.hq.core.net.FlowStep
import com.coinepro.hq.core.net.Health
import com.coinepro.hq.core.net.Playbook
import com.coinepro.hq.core.net.PlaybookChange
import com.coinepro.hq.core.net.PlaybookStats
import com.coinepro.hq.core.net.ReplyPolicy
import com.coinepro.hq.core.net.RunResults
import com.coinepro.hq.core.net.SiteLinks
import com.coinepro.hq.core.net.UseBrand
import com.coinepro.hq.core.net.UseBudget
import com.coinepro.hq.core.net.UseTime
import com.coinepro.hq.core.net.VersionRef
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.Locale

// Contract §59 ⟨1.37⟩ in the owner's words: the library of working groups (versions, the flow step by step, what one run hands over, the
// lessons) and the automations (the board, a flow's switch, hour, budget and replies, a run's timeline, the day). Pure functions: the
// unit tests read them. Money and percents are figures (Latin), counts are prose (Persian digits), as everywhere in the app.

// ================================================================ the library ==
/** «نسخه‌ی ۲». */
fun versionFa(v: Int?): String = "نسخه‌ی ${faNum(v ?: 1)}"

/** A version's state as a pill. */
fun versionStateFa(state: String): Pair<String, Tone> = when (state) {
    "sealed" -> "مُهر شده" to Tone.POS
    "retired" -> "کنار گذاشته" to Tone.SILVER
    else -> "پیش‌نویس" to Tone.GOLD
}

/** The library's three states as the owner names them (§59.1: «پیش‌نویس، مهرشده، کنارگذاشته»). */
val LIBRARY_STATES: List<Pair<String, String>> = listOf("sealed" to "مُهرشده", "draft" to "پیش‌نویس", "retired" to "بازنشسته")

/**
 * A card's one line of figures: «هر اجرا $0.84 · ۲۴ دقیقه · 95% موفق»; the parts the hub has not counted yet are left out, and a
 * playbook that never ran says so.
 */
fun statsLineFa(s: PlaybookStats): String {
    if (s.runs <= 0) return "هنوز اجرا نشده"
    val parts = listOfNotNull(
        s.avgCostUsd?.let { "هر اجرا ${usd(it)}" },
        s.avgMinutes?.let { "${faNum(Math.round(it).toInt())} دقیقه" },
        s.successPct?.let { "${pct(it)} موفق" },
    )
    return if (parts.isEmpty()) "${faNum(s.runs)} اجرا" else parts.joinToString(" · ")
}

/** «پرو-چارت و تریدیار» · «هنوز هیچ شرکتی»: who runs it. */
fun companiesLineFa(names: List<String>, count: Int = names.size): String = when {
    names.isEmpty() && count <= 0 -> "هنوز هیچ شرکتی"
    names.isEmpty() -> "${faNum(count)} شرکت"
    names.size <= 2 -> names.joinToString(" و ")
    else -> "${names.take(2).joinToString("، ")} و ${faNum(names.size - 2)} شرکت دیگر"
}

/** Persian text the way a search compares it: Arabic ی and ک made Persian, half-spaces and repeated spaces folded, lower case. */
fun foldFa(s: String): String = s.lowercase(Locale.ROOT).replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ').replace(Regex("\\s+"), " ").trim()

/**
 * The library as the filters show it, on the phone too (a hub before §59.1 ignores them): every word of [q] in the title or the purpose,
 * the [platform], the [state] and a [company] that is a member or the source. The order is the hub's.
 */
fun libraryFiltered(list: List<Playbook>, q: String?, platform: String?, state: String?, company: String?): List<Playbook> {
    val words = foldFa(q.orEmpty()).split(' ').filter { it.isNotBlank() }
    return list.filter { pb ->
        val text = foldFa(pb.titleFa + " " + pb.purposeFa)
        (words.all { it in text }) &&
            (platform == null || pb.platform == platform) &&
            (state == null || pb.state == state) &&
            (company == null || pb.source.company == company || pb.members.any { it.company == company })
    }
}

/** The versions newest first; a playbook from before §59.1 has only itself as its version. */
fun versionsOf(pb: Playbook): List<VersionRef> =
    pb.versions.sortedByDescending { it.version }.ifEmpty { listOf(VersionRef(version = pb.version, state = pb.state, at = pb.sealedAt ?: pb.createdAt)) }

/** The version a member runs, in words: «نسخه‌ی ۲» (the member's own when the hub says it, else the playbook's). */
fun memberVersionFa(pb: Playbook, memberVersion: Int?): String = versionFa(memberVersion ?: pb.version)

/** What a change between two versions is, in one Persian line (code's own words; the hub sends the before and after). */
fun changeLineFa(c: PlaybookChange): String {
    val what = when (c.part) {
        "title" -> "نام"
        "purpose" -> "هدف"
        "platform" -> "پلتفرم"
        "seat" -> "صندلی"
        "step" -> "قدم"
        "rule" -> "قاعده"
        "lesson" -> "درس"
        "package" -> "فایل بسته"
        "kpi" -> "شاخص"
        else -> "بخش"
    }
    val name = (c.afterFa ?: c.beforeFa)?.trim()?.take(80)?.let { " «$it»" }.orEmpty()
    return when (c.kind) {
        "added" -> "$what$name اضافه شد"
        "removed" -> "$what$name برداشته شد"
        else -> if (c.beforeFa != null && c.afterFa != null && c.part !in setOf("step", "seat", "lesson")) "$what: «${c.beforeFa.take(60)}» ← «${c.afterFa.take(60)}»"
        else "$what$name عوض شد"
    }
}

/** The steps of a flow in one line: «موضوع › نوشتن متن › کاور › صدا › …». */
fun flowLineFa(steps: List<FlowStep>): String = steps.joinToString(" › ") { it.titleFa.ifBlank { stepKindFa(it.kind) } }

/** A helper's or a model's name as the owner knows it (ChatGPT, Gemini, AI Studio, the workshop, the hub's code, IG-Hub). */
fun helperFa(helper: String?): String? = when (helper) {
    "gpt" -> "ChatGPT"
    "gemini" -> "Gemini"
    "aistudio" -> "AI Studio"
    "workshop" -> "کارگاه"
    "code" -> "کد هاب"
    "ighub" -> "IG-Hub"
    "deepseek" -> "DeepSeek"
    null, "", "model" -> null
    else -> helper
}

/** A model's id as its product name: «Opus 5.5», «Sonnet 5.5», «Gemini 3.8 Flash TTS». */
fun modelFa(model: String?): String? {
    if (model.isNullOrBlank()) return null
    if (model.startsWith("claude-")) return modelLabel(model)
    if (model.startsWith("gemini-")) {
        return model.removePrefix("gemini-").split('-').joinToString(" ") { p ->
            when {
                p.equals("tts", true) -> "TTS"
                p.firstOrNull()?.isDigit() == true -> p
                else -> p.replaceFirstChar { it.uppercase() }
            }
        }.let { "Gemini $it" }
    }
    return model
}

/** «ChatGPT» · «Opus 5.5 · بیشترین دقت» · «کارگاه · Opus 5.5 · بیشترین دقت»: who does a step and how hard. */
fun stepToolFa(helper: String?, model: String?, effort: String?): String? =
    listOfNotNull(helperFa(helper), modelFa(model), effortFa(effort)).distinct().joinToString(" · ").ifBlank { null }

/** The seat that owns a step, by its name in the playbook. */
fun stepSeatFa(pb: Playbook, step: FlowStep): String = seatTitleFa(pb, step.seat)

/** A playbook's export file name: its title (letters, digits and dashes) and the version. */
fun exportFileName(title: String, version: Int): String {
    val base = title.trim().replace(Regex("[\\\\/:*?\"<>|\\s]+"), "-").trim('-').take(48).ifBlank { "playbook" }
    return "$base-v$version.playbook.json"
}

// ================================================================ the use form ==
/** The owner's form as he fills it (§59.4); [UseDraft.body] is what the hub takes. */
data class UseDraft(
    val version: Int? = null,
    val company: String? = null,
    val accounts: List<String> = emptyList(),
    val voice: String? = null,
    val styleFa: String = "",
    val brand: UseBrand? = null,
    val links: SiteLinks? = null,
    val replies: ReplyPolicy? = null,
    val time: UseTime = UseTime(),
    val budget: UseBudget = UseBudget(),
    val auto: Boolean = true,
) {
    fun body(): JsonObject = buildJsonObject {
        version?.let { put("version", it) }
        put("company", company.orEmpty())
        put("accounts", JsonArray(accounts.map { JsonPrimitive(it.trim().removePrefix("@")) }))
        if (!voice.isNullOrBlank()) put("narrator", buildJsonObject { put("voice", voice); styleFa.trim().ifEmpty { null }?.let { put("style_fa", it) } })
        brand?.let { put("brand", Api.jsonBody.encodeToJsonElement(UseBrand.serializer(), it)) }
        links?.let { put("links", Api.jsonBody.encodeToJsonElement(SiteLinks.serializer(), it)) }
        replies?.let { put("replies", repliesBody(it)) }
        put("time", buildJsonObject {
            put("mode", time.mode)
            if (time.mode == "fixed") clockOf(time.at)?.let { put("at", it) }
            time.days?.takeIf { it.isNotEmpty() }?.let { d -> put("days", JsonArray(d.map(::JsonPrimitive))) }
            put("story", time.story)
        })
        put("budget", buildJsonObject { put("per_run_usd", budget.perRunUsd); put("per_day_usd", budget.perDayUsd) })
        put("mode", if (auto) "auto" else "ask")
    }
}

/** What the form still lacks before the preview, each in one line (empty: ready). */
fun useMissingFa(d: UseDraft, publishes: Boolean): List<String> = buildList {
    if (d.company.isNullOrBlank()) add("شرکت را انتخاب کن.")
    if (publishes && d.accounts.isEmpty()) add("حساب انتشار را انتخاب کن.")
    if (d.time.mode == "fixed" && clockOf(d.time.at) == null) add("ساعت انتشار را مثل 18:30 بنویس.")
    if (d.budget.perRunUsd <= 0 || d.budget.perDayUsd <= 0) add("بودجه‌ی هر اجرا و هر روز باید بیشتر از صفر باشد.")
    if (d.budget.perDayUsd < d.budget.perRunUsd) add("بودجه‌ی روز از بودجه‌ی یک اجرا کمتر است.")
}

/** A dollar figure he typed («5»، «۷٫۵»، «$8.25») as a number; null when it is none. */
fun dollarsOf(raw: String?): Double? {
    val t = raw.orEmpty().trim().removePrefix("$").map { ch ->
        when (ch) { in '۰'..'۹' -> '0' + (ch - '۰'); in '٠'..'٩' -> '0' + (ch - '٠'); '٫', '،' -> '.'; else -> ch }
    }.joinToString("")
    return t.toDoubleOrNull()?.takeIf { it >= 0 && it < 10_000 }
}

/** A dollar figure as the form shows it back («5» or «7.5», never «5.0»). */
fun dollarsText(v: Double): String = if (v == Math.floor(v)) v.toLong().toString() else String.format(Locale.US, "%.2f", v).trimEnd('0').trimEnd('.')

/** «$5 هر اجرا · $8 هر روز». */
fun budgetFa(b: UseBudget): String = "${usd(b.perRunUsd)} هر اجرا · ${usd(b.perDayUsd)} هر روز"

/** «امروز $1.20 از $8.00»: what today spent against the day's cap; null when the hub did not say. */
fun spentFa(b: UseBudget): String? = b.spentTodayUsd?.let { "امروز ${usd(it)} از ${usd(b.perDayUsd)}" }

// ================================================================== the links ==
/**
 * A reply's link as the hub builds it (§59.5): the url with `utm_source`, `utm_medium`, `utm_campaign` and `utm_content` added; a
 * parameter the url already has is kept as it is. Shown in the form so the owner sees what each path sends.
 */
fun utmLink(url: String, source: String, medium: String, campaign: String, content: String?): String {
    val trimmed = url.trim()
    if (trimmed.isEmpty()) return ""
    val hash = trimmed.substringAfter('#', "").let { if (it.isEmpty()) "" else "#$it" }
    val noHash = trimmed.substringBefore('#')
    val have = noHash.substringAfter('?', "").split('&').filter { it.isNotBlank() }.map { it.substringBefore('=') }.toSet()
    val add = listOfNotNull(
        ("utm_source" to source).takeIf { "utm_source" !in have && source.isNotBlank() },
        ("utm_medium" to medium).takeIf { "utm_medium" !in have && medium.isNotBlank() },
        ("utm_campaign" to campaign).takeIf { "utm_campaign" !in have && campaign.isNotBlank() },
        content?.let { ("utm_content" to it).takeIf { "utm_content" !in have && content.isNotBlank() } },
    ).joinToString("&") { (k, v) -> "$k=" + java.net.URLEncoder.encode(v, "UTF-8").replace("+", "%20") }
    if (add.isEmpty()) return trimmed
    val sep = if ('?' in noHash) (if (noHash.endsWith('?') || noHash.endsWith('&')) "" else "&") else "?"
    return noHash + sep + add + hash
}

/** The three paths' links of one section (null: the site), as the form previews them: comment, story, DM. */
fun pathLinks(links: SiteLinks, section: String?, campaign: String, day: String?): List<Pair<String, String>> {
    val url = links.sections.firstOrNull { it.key == section }?.url ?: links.site.url
    if (url.isBlank()) return emptyList()
    val m = links.utm.medium
    return listOf("کامنت" to m.comment, "استوری" to m.story, "دایرکت" to m.dm).map { (fa, medium) ->
        fa to utmLink(url, links.utm.source, medium, campaign, day)
    }
}

/** What is wrong with the links he typed, each in one line (empty: fine): an https site, https sections with short keys. */
fun linksProblemsFa(links: SiteLinks): List<String> = buildList {
    if (!links.site.url.startsWith("https://")) add("نشانی سایت باید با https:// شروع شود.")
    for (s in links.sections) {
        if (!s.url.startsWith("https://")) add("نشانی «${s.titleFa.ifBlank { s.key }}» باید با https:// شروع شود.")
        if (!Regex("^[a-z0-9_]{1,24}$").matches(s.key)) add("نام کوتاه «${s.titleFa.ifBlank { s.key }}» فقط حرف کوچک لاتین، عدد و _ باشد.")
    }
    if (links.sections.map { it.key }.toSet().size != links.sections.size) add("دو بخش یک نام کوتاه دارند.")
    if (links.sections.size > 30) add("بیشتر از ۳۰ بخش نمیشود.")
}

/** A section's short key from its title or url («آموزش» → «section_2» when no Latin word is there). */
fun sectionKey(titleFa: String, url: String, taken: Set<String>): String {
    val fromUrl = url.substringAfter("://", "").substringAfter('/', "").substringBefore('?').substringBefore('#').trim('/')
        .substringAfterLast('/').lowercase(Locale.ROOT).replace(Regex("[^a-z0-9_]+"), "_").trim('_').take(24)
    val base = fromUrl.ifBlank { foldFa(titleFa).lowercase(Locale.ROOT).replace(Regex("[^a-z0-9_]+"), "_").trim('_').take(24) }.ifBlank { "section" }
    if (base !in taken) return base
    var n = 2
    while ("${base.take(21)}_$n" in taken) n++
    return "${base.take(21)}_$n"
}

// ================================================================ the replies ==
/** Instagram's DM: at most 640 letters, at most three buttons, each title at most 20 (§59.6). */
const val DM_MAX = 640
const val DM_BUTTONS_MAX = 3
const val DM_BUTTON_TITLE_MAX = 20
const val POOL_MIN = 10
const val POOL_MAX = 30

/**
 * The hub's warm pool (§59.6, 37.2): what fills a policy's own public replies up to ten, in this order. They go out IN TURN (IG-Hub
 * 1806b86, `rules.public_turn`): ten people in a row get ten different replies, then the first again. The hub's own list is the one sent.
 */
val PUBLIC_POOL_FA: List<String> = listOf(
    "برو دایرکتت رو چک کن، فرستادم برات؛ موفق باشی 🤍",
    "فرستادم! یه سر به دایرکتت بزن 🙌",
    "دایرکتت رو ببین، همه‌چی اون‌جاست 💌",
    "برات ارسال شد ✅ امیدوارم به کارت بیاد 🌱",
    "توی دایرکت منتظرته 🎁 روز خوبی داشته باشی",
    "ارسال شد 🚀 دایرکت رو چک کن",
    "لینکش آماده‌ست، توی دایرکتته 🔗💛",
    "حله! برات فرستادیم 😊 دایرکت رو ببین",
    "جوابت رفت توی دایرکت 📬 ممنون که همراهمونی",
    "دایرکتت رو باز کن، یه چیز خوب برات فرستادیم ✨",
)

/** His own public replies first, filled up to ten from the pool (the same rule as the hub's); the order is the order they go out in. */
fun poolFilled(own: List<String>): List<String> {
    val mine = own.map { it.trim() }.filter { it.isNotEmpty() }.distinct()
    val more = PUBLIC_POOL_FA.filter { it !in mine }
    return (mine + more).take(maxOf(POOL_MIN, mine.size)).take(POOL_MAX)
}

/** What the hub would refuse in a policy, each in one line (empty: fine); [sections] are the company's link keys. */
fun replyProblemsFa(p: ReplyPolicy, sections: Set<String>): List<String> = buildList {
    if (p.dmTemplate.textFa.length > DM_MAX) add("متن دایرکت ${faNum(p.dmTemplate.textFa.length)} حرف است؛ اینستاگرام تا ${faNum(DM_MAX)} حرف نشان میدهد.")
    if (p.dmTemplate.buttons.size > DM_BUTTONS_MAX) add("زیر دایرکت حداکثر ${faNum(DM_BUTTONS_MAX)} دکمه میرود.")
    for (b in p.dmTemplate.buttons) {
        if (b.titleFa.isBlank()) add("یک دکمه نام ندارد.")
        if (b.titleFa.length > DM_BUTTON_TITLE_MAX) add("نام دکمه‌ی «${b.titleFa.take(24)}» بیشتر از ${faNum(DM_BUTTON_TITLE_MAX)} حرف است.")
        if (b.section != null && b.section !in sections) add("دکمه‌ی «${b.titleFa}» به بخشی میرود که در لینک‌های شرکت نیست.")
    }
    if (p.section != null && p.section !in sections) add("بخش لینک دایرکت در لینک‌های شرکت نیست.")
    if (p.publicPool.size > POOL_MAX) add("جواب‌های عمومی حداکثر ${faNum(POOL_MAX)} تا.")
    if (p.repeat.mode == "after_days" && (p.repeat.days == null || p.repeat.days !in 1..365)) add("«دوباره بعد از چند روز» بین ۱ و ۳۶۵ باشد.")
}

/** The policy as the hub takes it (`PUT /automations/{ref}/replies`, and the form's `replies`). */
fun repliesBody(p: ReplyPolicy): JsonObject = buildJsonObject {
    put("comment", buildJsonObject { put("match", p.comment.match) })
    put("story", p.story)
    put("dm", p.dm)
    put("public_pool", JsonArray(p.publicPool.map { it.trim() }.filter { it.isNotEmpty() }.distinct().map(::JsonPrimitive)))
    put("dm_template", buildJsonObject {
        put("text_fa", p.dmTemplate.textFa.trim())
        put("buttons", JsonArray(p.dmTemplate.buttons.filter { it.titleFa.isNotBlank() }.map { b ->
            buildJsonObject { put("title_fa", b.titleFa.trim()); b.section?.let { put("section", it) } }
        }))
    })
    put("per_video_dm", p.perVideoDm)
    put("repeat", buildJsonObject { put("mode", p.repeat.mode); if (p.repeat.mode == "after_days") p.repeat.days?.let { put("days", it) } })
    p.section?.let { put("section", it) }
}

/** «هر کامنتی» · «فقط کلمه» · «هر ویدیو خودش انتخاب میکند». */
fun commentMatchFa(m: String): String = when (m) {
    "any" -> "هر کامنتی"
    "word" -> "فقط با کلمه"
    else -> "هر ویدیو خودش انتخاب میکند"
}

/** «هر نفر سالی یک بار» · «دوباره بعد از ۳۰ روز». */
fun repeatFa(p: ReplyPolicy): String =
    if (p.repeat.mode == "after_days" && p.repeat.days != null) "هر نفر دوباره بعد از ${faNum(p.repeat.days)} روز" else "هر نفر سالی یک بار برای هر قاعده"

/** The DM's text with the day's topic in it, as a person reads it (`{topic}`). */
fun dmTextFor(text: String, topic: String?): String = text.replace("{topic}", topic?.ifBlank { null } ?: "موضوع امروز")

/** The buttons of a DM as the preview draws them: titles, cut to Instagram's 20 letters, at most three. */
fun dmButtonsFor(buttons: List<DmButton>): List<String> = buttons.filter { it.titleFa.isNotBlank() }.take(DM_BUTTONS_MAX).map { it.titleFa.trim().take(DM_BUTTON_TITLE_MAX) }

// ============================================================== the automations ==
/** The board's kinds, in the order it shows them, with their names. */
val BOARD_KINDS: List<Pair<String, String>> = listOf(
    "flow" to "کارگروه‌های خودکار",
    "standing_publish" to "انتشار خودکار",
    "routine" to "روال‌های دائمی",
    "line" to "خط‌های تولید",
    "rule" to "اتوماسیون از یک جمله",
    "archive" to "قاعده‌های بایگانی",
)

fun boardKindFa(kind: String): String = BOARD_KINDS.firstOrNull { it.first == kind }?.second ?: "دیگر"

/** One automation's kind, in a row's facts: «کارگروه خودکار» · «انتشار خودکار» · «روال دائمی» · «خط تولید» · «از یک جمله» · «بایگانی». */
fun boardKindOneFa(kind: String): String? = when (kind) {
    "flow" -> "کارگروه خودکار"
    "standing_publish" -> "انتشار خودکار"
    "routine" -> "روال دائمی"
    "line" -> "خط تولید"
    "rule" -> "از یک جمله"
    "archive" -> "بایگانی"
    else -> null
}

/** The board in its groups, each in the hub's order; a kind this app does not know goes under «دیگر». */
fun boardGroups(items: List<BoardItem>): List<Pair<String, List<BoardItem>>> {
    val known = BOARD_KINDS.mapNotNull { (k, fa) -> items.filter { it.kind == k }.takeIf { it.isNotEmpty() }?.let { fa to it } }
    val other = items.filter { i -> BOARD_KINDS.none { it.first == i.kind } }
    return if (other.isEmpty()) known else known + ("دیگر" to other)
}

/** An automation's state as a pill. */
fun autoStateFa(state: String): Pair<String, Tone> = when (state) {
    "on" -> "روشن" to Tone.POS
    "paused" -> "مکث" to Tone.WARN
    "proposed" -> "منتظر مُهر تو" to Tone.GOLD
    else -> "خاموش" to Tone.SILVER
}

/** The road's parts by name. */
fun healthKeyFa(key: String): String = when (key) {
    "n8n" -> "n8n"
    "ighub" -> "IG-Hub"
    "publish_path" -> "مسیر انتشار"
    "helpers_browser" -> "مرورگر کمک‌کارها"
    "aistudio" -> "AI Studio"
    "workshop" -> "کارگاه"
    "budget" -> "بودجه"
    else -> key
}

fun healthTone(state: String): Tone = when (state) { "ok" -> Tone.POS; "warn" -> Tone.WARN; else -> Tone.NEG }

/** The road in one line: «همه‌ی مسیر سالم است», or the worst part's own words. */
fun healthLineFa(list: List<Health>): Pair<String, Tone> {
    val worst = list.firstOrNull { it.state == "down" } ?: list.firstOrNull { it.state == "warn" }
    return when {
        list.isEmpty() -> "سلامت مسیر هنوز خوانده نشده" to Tone.SILVER
        worst == null -> "همه‌ی مسیر سالم است" to Tone.POS
        else -> "${healthKeyFa(worst.key)}: ${worst.noteFa.ifBlank { if (worst.state == "down") "قطع" else "نیاز به نگاه" }}" to healthTone(worst.state)
    }
}

/** A flow's time: the hub's own words, else «هر روز، بهترین ساعت» · «هر روز ساعت 18:30». */
fun scheduleFa(s: FlowSchedule): String = s.whenFa.ifBlank {
    val days = s.days?.takeIf { it.isNotEmpty() && it.size < 7 }?.let { d -> d.mapNotNull { DAY_FA[it] }.joinToString(" و ") }
    val head = if (days.isNullOrBlank()) "هر روز" else "هر $days"
    if (s.mode == "best") "$head، بهترین ساعت" else "$head ساعت ${clockOf(s.at) ?: "—"}"
}

private val DAY_FA = mapOf("SA" to "شنبه", "SU" to "یکشنبه", "MO" to "دوشنبه", "TU" to "سه‌شنبه", "WE" to "چهارشنبه", "TH" to "پنجشنبه", "FR" to "جمعه")
/** The week's days in the owner's order, for a picker. */
val WEEK_DAYS: List<Pair<String, String>> = listOf("SA", "SU", "MO", "TU", "WE", "TH", "FR").map { it to DAY_FA.getValue(it) }

/** «خودکار کامل» or «قبل از انتشار بپرس». */
fun flowModeFa(mode: String): String = if (mode == "ask") "قبل از انتشار بپرس" else "خودکار کامل"

/** A step's cost and minutes in one line: «$0.42 · ۳ دقیقه». */
fun stepCostFa(costUsd: Double?, startedAt: String?, endedAt: String?): String? {
    val minutes = minutesBetween(startedAt, endedAt)
    return listOfNotNull(costUsd?.takeIf { it > 0.0 }?.let { usd(it) }, minutes?.let { if (it < 1) "کمتر از یک دقیقه" else "${faNum(it)} دقیقه" }).joinToString(" · ").ifBlank { null }
}

/** Whole minutes between two instants; null when either is missing. */
fun minutesBetween(a: String?, b: String?): Int? {
    val x = com.coinepro.hq.core.format.instant(a) ?: return null
    val y = com.coinepro.hq.core.format.instant(b) ?: return null
    return ((y.toEpochMilli() - x.toEpochMilli()) / 60_000).toInt().coerceAtLeast(0)
}

/** A run's figures as label and value («—» for what IG-Hub does not give yet), in the order the owner reads them. */
fun resultsRowsFa(r: RunResults?): List<Pair<String, String>> {
    fun n(v: Int?) = v?.let { faNum(it) } ?: "—"
    return listOf(
        "کامنت" to n(r?.comments),
        "دایرکت فرستاده" to n(r?.dmsSent),
        "کلیک" to n(r?.clicks),
        "بازدید" to n(r?.views),
        "دیده‌شدن" to n(r?.reach),
        "لایک" to n(r?.likes),
    )
}

/** «۱۲ کامنت، ۹ دایرکت، ۴ کلیک»: a run's short line; null when nothing is counted yet. */
fun resultsLineFa(r: RunResults?): String? {
    if (r == null) return null
    val parts = listOfNotNull(r.comments?.let { "${faNum(it)} کامنت" }, r.dmsSent?.let { "${faNum(it)} دایرکت" }, r.clicks?.let { "${faNum(it)} کلیک" })
    return parts.joinToString("، ").ifBlank { null }
}
