package com.coinepro.hq.core.data

import com.coinepro.hq.core.net.Council
import com.coinepro.hq.core.net.CouncilMember
import com.coinepro.hq.core.net.Substitute

// Contract §27 ⟨1.9⟩: who plays an order (the router, Claude, or a substitute seat of §21.13) and the council of models. Pure: the
// owner's choice and the wire fields, a player's availability from `GET /substitutes`, the players a voice order names, a council's
// state in words and Claude's synthesis split into its parts.

/** One choice of «با کدام مدل؟». [player] and [mode] are what goes on the wire; [provider] picks the logo (null: the router's glyph). */
enum class PlayerOption(val key: String, val fa: String, val provider: String?, val player: String, val mode: String) {
    AUTO("auto", "خودکار", null, "auto", "single"),
    CLAUDE("claude", "Claude", "anthropic", "claude", "single"),
    GPT("gpt", "GPT", "openai", "gpt", "single"),
    GEMINI("gemini", "Gemini", "google", "gemini", "single"),
    DEEPSEEK("deepseek", "DeepSeek", "deepseek", "deepseek", "single"),
    COUNCIL("council", "شورای مدل‌ها", null, "auto", "council");

    /** A substitute seat (§21.13): its availability comes from `GET /substitutes`. */
    val substitute: Boolean get() = this == GPT || this == GEMINI || this == DEEPSEEK

    companion object {
        /** The option a work or an order carries; an unknown player (a newer hub) reads as the router's. */
        fun of(player: String?, mode: String?): PlayerOption =
            if (mode == "council") COUNCIL else entries.firstOrNull { it.key == player && it != COUNCIL } ?: AUTO
    }
}

/** A player's name in the app: the substitutes by their product, Claude by name, the router in words. */
fun playerFa(player: String?): String = when (player) {
    "claude" -> "Claude"; "gpt" -> "GPT"; "gemini" -> "Gemini"; "deepseek" -> "DeepSeek"; "auto", null, "" -> "خودکار"; else -> player
}

/** The logo's provider for a player. */
fun providerOfPlayer(player: String?): String? = when (player) {
    "claude" -> "anthropic"; "gpt" -> "openai"; "gemini" -> "google"; "deepseek" -> "deepseek"; else -> null
}

/** Whether a player can take an order now, and if not why, in the owner's words. [waits]: chosen anyway, the run waits for it up to
 *  30 minutes and then falls back to the router (§27.1). */
data class PlayerAvailability(val ok: Boolean, val stateFa: String? = null, val reasonFa: String? = null) {
    val waits: Boolean get() = !ok
}

/**
 * A player's availability from `GET /substitutes` (§21.13): the router and Claude always play. A substitute plays when it is `ready`
 * and signed in where its seats run (the CLI's sign-in for a player with a runner, the signed-in browser profile otherwise, or either
 * when one of them is signed in). Signed out, `limited` or `off` (or `error`) greys it with the reason. Unknown while the list loads.
 */
fun availabilityOf(option: PlayerOption, subs: List<Substitute>?): PlayerAvailability {
    if (!option.substitute) return PlayerAvailability(true)
    if (subs == null) return PlayerAvailability(true)
    val s = subs.firstOrNull { it.player == option.key } ?: return PlayerAvailability(false, "تعریف نشده", "این بازیکن روی هاب وصل نشده است.")
    return when (s.status) {
        "limited" -> PlayerAvailability(false, "محدود", s.statusReason ?: "سقف امروزش پر شده؛ تا ریست صبر میکند.")
        "off" -> PlayerAvailability(false, "خاموش", s.statusReason ?: "خاموش است.")
        "error" -> PlayerAvailability(false, "خطا", s.statusReason ?: "آخرین فراخوانی‌اش خطا داد.")
        else -> if (signedIn(s)) PlayerAvailability(true) else PlayerAvailability(false, "خارج", s.statusReason ?: "از حسابش خارج است؛ ورود دوباره با مالک است.")
    }
}

private fun signedIn(s: Substitute): Boolean {
    val cli = s.runner != null && s.login.state == "signed_in"
    val web = s.web.state == "signed_in"
    return cli || web
}

/** The players a council would seat now (§27.2): Claude, then every substitute that is available. */
fun councilSeats(subs: List<Substitute>?): List<PlayerOption> =
    listOf(PlayerOption.CLAUDE) + listOf(PlayerOption.GPT, PlayerOption.GEMINI, PlayerOption.DEEPSEEK).filter { subs != null && availabilityOf(it, subs).ok }

/** What the chosen option means, in one sentence. */
fun optionNoteFa(option: PlayerOption, availability: PlayerAvailability, seats: Int): String = when {
    option == PlayerOption.AUTO -> "مسیریاب مدل برای هر قدم خودش انتخاب میکند، مثل همیشه."
    option == PlayerOption.CLAUDE -> "همه‌ی فراخوانی‌های مدل این کار با مدل‌های Claude."
    option == PlayerOption.COUNCIL ->
        "همان شرح، جدا از هم، به Claude و هر بازیکن آماده (الان $seats بازیکن) میرود؛ Claude جمع‌بندی مینویسد: کجا هم‌نظرند، کجا نه و چرا، و پیشنهاد. یک پاکت بودجه برای همه."
    !availability.ok ->
        "${option.fa} الان ${availability.stateFa}: ${availability.reasonFa} کار تا ۳۰ دقیقه منتظرش میماند و بعد خودکار میشود؛ اعلانش میاید."
    else -> "هر فراخوانی مدل این کار به ${option.fa} میرود، در سقف روزانه‌ی جایگاهش و با همان پوشاندن داده‌ها."
}

// ------------------------------------------------------------- voice --
/** What a voice order named: the option and the words that named it («با جمنای»). */
data class Recognised(val option: PlayerOption, val phrase: String)

/** Persian as the phone and the hub write it: Arabic ي/ك as ی/ک, the tatweel gone, one space. The half-space stays (a phrase is shown
 *  as it was written); the patterns take a half-space, a space or nothing between a word's parts. */
fun normaliseFa(s: String): String = s.replace('ي', 'ی').replace('ك', 'ک').replace("\u0640", "").replace(Regex("[ \\t\\n]+"), " ").trim()

/** A gap inside a word as it may be written: a half-space, a space or nothing. */
private const val G = "[\u200c ]?"

private val COUNCIL_WORDS = listOf(
    Regex("شورای?${G}مدل${G}ها"), Regex("شورای مدل"), Regex("(^| )شورا($| |[،,.؟!:؛])"), Regex("همه${G}ی?${G}مدل${G}ها"), Regex("با هم مشارکت کن"),
    Regex("با هم (بسازن|بنویسن|انجام بدن|کار کنن)"), Regex("\\bcouncil\\b", RegexOption.IGNORE_CASE),
)

private val PLAYER_WORDS: List<Pair<PlayerOption, Regex>> = listOf(
    PlayerOption.GPT to Regex("(چت${G})?جی${G}پی${G}تی|chat${G}gpt|\\bgpt\\b", RegexOption.IGNORE_CASE),
    PlayerOption.GEMINI to Regex("جمنای|جمینای|جیمنای|جیمینای|جمینی|جمنی|\\bgemini\\b", RegexOption.IGNORE_CASE),
    PlayerOption.DEEPSEEK to Regex("دیپ${G}سیک|\\bdeep${G}seek\\b", RegexOption.IGNORE_CASE),
    PlayerOption.CLAUDE to Regex("کلود|کلاد|\\bclaude\\b", RegexOption.IGNORE_CASE),
)

/**
 * The player a voice order names (§27.1: «با جی‌پی‌تی / با جمنای / با دیپ‌سیک / شورا»), as the phone or the hub wrote the words: the
 * council when the order asks the models together, otherwise the first player named (with «با» before it when said so). Null when the
 * order names none: the router plays. The owner sees what was heard and can change it before the order goes.
 */
fun recogniseOption(text: String): Recognised? {
    val t = normaliseFa(text)
    if (t.isEmpty()) return null
    COUNCIL_WORDS.firstNotNullOfOrNull { it.find(t) }?.let { return Recognised(PlayerOption.COUNCIL, it.value.trim(' ', '،', ',', '.', '؟', '!')) }
    val hit = PLAYER_WORDS.mapNotNull { (o, r) -> r.find(t)?.let { o to it } }.minByOrNull { it.second.range.first } ?: return null
    val (option, m) = hit
    val before = t.substring(0, m.range.first).trimEnd()
    val phrase = if (before.endsWith(" با") || before == "با") "با ${m.value}" else m.value
    return Recognised(option, phrase.trim())
}

/**
 * ⟨1.9⟩ A voice order goes as words (`POST /orders`): the hub reads «با جمنای» from them. When the owner's choice differs from what the
 * hub set on a work the order made, that work is changed to it (`PATCH /work/{id}` with `player` and `mode`, §27.1). Returns how many
 * works were changed; a work that cannot be read or changed is left as the hub made it.
 */
suspend fun com.coinepro.hq.core.net.Api.applyPlayer(order: com.coinepro.hq.core.net.Order, option: PlayerOption): Int {
    var changed = 0
    for (r in order.routes) {
        val ref = r.workRef?.takeIf { r.kind == "work" } ?: continue
        try {
            val w = workOne(ref)
            if (w.player == option.player && w.mode == option.mode) continue
            patchWork(w, com.coinepro.hq.core.net.WorkPatch(player = option.player, mode = option.mode))
            changed++
        } catch (_: com.coinepro.hq.core.net.ApiException) {
            continue
        }
    }
    return changed
}

// ----------------------------------------------------------- council --
/** A member's state in words, and whether it is still moving. */
fun memberStateFa(m: CouncilMember): String = when (m.state) {
    "queued" -> "در صف"; "working" -> "کار میکند"; "done" -> "تحویل داد"; "failed" -> "ناموفق"; "skipped" -> "کنار ماند"; else -> m.state
}

/** ⟨1.10⟩ §28.4 a member's reason as the app shows it: [text] in Persian, and [raw] (the hub's own words) behind «جزئیات» when the
 *  reason was not Persian (raw JSON, an English error) and the app said «پاسخ نداد» instead. */
data class MemberReason(val text: String, val raw: String? = null)

/** Persian as given; raw JSON or an English sentence becomes «پاسخ نداد» with the original kept for «جزئیات». */
fun memberReasonFa(reason: String?): MemberReason? {
    val r = reason?.trim()?.takeIf { it.isNotEmpty() } ?: return null
    val json = r.startsWith("{") || r.startsWith("[") || Regex("\\{\\s*\"\\w+\"\\s*:").containsMatchIn(r)
    val persian = r.count { it in '\u0600'..'\u06FF' }
    val latin = r.count { it in 'a'..'z' || it in 'A'..'Z' }
    return if (json || persian == 0 || persian * 2 < latin) MemberReason(NO_ANSWER, r) else MemberReason(r)
}

private const val NO_ANSWER = "پاسخ نداد"

/** ⟨1.10⟩ §28.4 a council that ended with one answer says so plainly («فقط Claude پاسخ داد»), and does not pretend there was a council. */
fun soloAnswerFa(c: Council): String? {
    val moving = c.members.any { it.state == "queued" || it.state == "working" }
    val done = c.members.filter { it.state == "done" }
    if (moving || c.members.size < 2 || done.size != 1) return null
    return "فقط ${playerFa(done.single().player)} پاسخ داد"
}

/** The council's state in words. */
fun councilStateFa(c: Council): String = when (c.state) {
    "running" -> "بازیکن‌ها کار میکنند"
    "synthesising" -> "Claude جمع‌بندی مینویسد"
    "done" -> when {
        c.mediaCouncil -> "منتظر انتخاب تو"
        soloAnswerFa(c) != null -> "فقط یک پاسخ"
        else -> "جمع‌بندی آماده است"
    }
    "failed" -> "ناموفق"
    else -> c.state
}

/** How many answered, of the members that play (a skipped one is not waited for): «۲ از ۳ پاسخ داده‌اند». */
fun councilProgressFa(c: Council): String {
    val playing = c.members.filter { it.state != "skipped" }
    val done = playing.count { it.state == "done" }
    val skipped = c.members.size - playing.size
    val base = if (playing.isEmpty()) "هیچ بازیکنی نماند" else "$done از ${playing.size} پاسخ داده‌اند"
    return if (skipped > 0) "$base؛ $skipped بازیکن کنار ماند" else base
}

/** The kinds of the synthesis's parts (§27.2): where the players agree, where they differ and why, the recommendation, each answer. */
enum class SynthKind { AGREE, DIFFER, RECOMMEND, ANSWERS, OTHER }

data class SynthSection(val kind: SynthKind, val title: String, val body: String)

/** Claude's synthesis split at its `##` headings, each heading read for what it is; text before the first heading is [SynthKind.OTHER]. */
fun synthesisSections(md: String): List<SynthSection> {
    val out = mutableListOf<SynthSection>()
    var title: String? = null
    val body = StringBuilder()
    fun flush() {
        val b = body.toString().trim()
        if (title != null || b.isNotEmpty()) out += SynthSection(kindOf(title.orEmpty()), title.orEmpty(), b)
        body.clear()
    }
    for (line in md.lines()) {
        val h = Regex("^##\\s+(.+)$").find(line)
        if (h != null && !line.startsWith("###")) { flush(); title = h.groupValues[1].trim() } else body.appendLine(line)
    }
    flush()
    return out.filter { it.body.isNotBlank() || it.title.isNotBlank() }
}

private fun kindOf(title: String): SynthKind {
    val t = normaliseFa(title)
    return when {
        Regex("هم${G}نظر|توافق|اتفاق نظر|agree", RegexOption.IGNORE_CASE).containsMatchIn(t) -> SynthKind.AGREE
        Regex("فرق|تفاوت|اختلاف|differ", RegexOption.IGNORE_CASE).containsMatchIn(t) -> SynthKind.DIFFER
        Regex("پیشنهاد|توصیه|recommend", RegexOption.IGNORE_CASE).containsMatchIn(t) -> SynthKind.RECOMMEND
        Regex("پاسخ|جواب|answer", RegexOption.IGNORE_CASE).containsMatchIn(t) -> SynthKind.ANSWERS
        else -> SynthKind.OTHER
    }
}
