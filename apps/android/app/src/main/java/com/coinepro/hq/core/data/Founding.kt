package com.coinepro.hq.core.data

import android.content.Context
import android.content.SharedPreferences

/** How a new company starts (the wizard's second step). */
enum class FoundingPath { IDEA, REPO, REGISTER }

/**
 * What the owner fills in the founding wizard: who the company is, how it starts, its brand. Nothing reaches the hub until the last
 * step: an idea or a repository becomes `POST /foundings` (§18.8, the audit and proposal go to the cartable), «فقط ثبت کن» becomes
 * `POST /companies` 🔏 `company.create` (§3.1).
 */
data class FoundingDraft(
    val nameFa: String = "",
    val code: String = "",
    val tagline: String = "",
    val path: FoundingPath? = null,
    val idea: String = "",
    val repo: String = "",
    /** The English name the hub keeps beside the Persian one; empty → the code. */
    val nameEn: String = "",
    /** A slot of the companies' palette (1–8); null → the hub picks a free one. */
    val colorIndex: Int? = null,
    /** The logo, once uploaded (`POST /files`). */
    val logoFileId: String? = null,
)

/** The wizard's rules and the brief it writes; each error is the sentence shown under its field. */
object FoundingRules {
    /** 2–4 Latin capitals: what the owner chooses (the hub itself takes up to 10, `^[A-Z][A-Z0-9]{1,9}$`). */
    val CODE = Regex("^[A-Z]{2,4}$")
    private val PERSIAN = Regex("[\\u0600-\\u06FF]")
    private val REPO = Regex("^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
    private val LATIN_NAME = Regex("^[A-Za-z0-9][A-Za-z0-9 .&'-]{0,79}$")
    const val STEPS = 4

    /** What the code field keeps of what was typed: Latin letters, upper case, four at most. */
    fun cleanCode(input: String): String = input.uppercase().filter { it in 'A'..'Z' }.take(4)

    fun nameError(name: String): String? {
        val n = name.trim()
        return when {
            n.isEmpty() -> "نام شرکت را بنویس."
            n.length < 2 -> "نام دست‌کم دو حرف است."
            n.length > 60 -> "نام حداکثر ۶۰ حرف است."
            !PERSIAN.containsMatchIn(n) -> "نام فارسی بنویس؛ نام لاتین جدا میاید."
            else -> null
        }
    }

    /** [taken]: the codes of every company and of every founding still open (the hub refuses a code twice). */
    fun codeError(code: String, taken: Set<String>): String? = when {
        code.isEmpty() -> "یک کد ۲ تا ۴ حرفی لاتین بده، مثل IG."
        !CODE.matches(code) -> "کد فقط ۲ تا ۴ حرف لاتین بزرگ است (A تا Z)."
        code == "HQ" -> "HQ کد هلدینگ است."
        code in taken -> "$code را شرکت یا تأسیس دیگری دارد."
        else -> null
    }

    fun taglineError(t: String): String? {
        val s = t.trim()
        return when {
            s.isEmpty() -> "در یک خط بگو چه میکند."
            s.length < 6 -> "کمی روشن‌تر؛ دست‌کم چند کلمه."
            s.length > 140 -> "یک خط، حداکثر ۱۴۰ حرف."
            else -> null
        }
    }

    fun nameEnError(n: String): String? = n.trim().takeIf { it.isNotEmpty() && !LATIN_NAME.matches(it) }?.let { "نام لاتین فقط حروف و عدد لاتین است." }

    /** `owner/name` from what was pasted: a GitHub URL (with or without https, `.git` or a trailing slash) or `owner/name`. */
    fun repo(input: String): String? {
        val s = input.trim().removePrefix("https://").removePrefix("http://").removePrefix("www.").removePrefix("github.com/")
            .removeSuffix("/").removeSuffix(".git")
        return s.takeIf { REPO.matches(it) }
    }

    fun pathError(d: FoundingDraft): String? = when (d.path) {
        null -> "یکی از سه راه را انتخاب کن."
        FoundingPath.IDEA -> if (d.idea.trim().length < 20) "ایده را کمی بیشتر بگو: مشتری، کار اصلی و درآمد (دست‌کم یک جمله)." else null
        FoundingPath.REPO -> if (repo(d.repo) == null) "آدرس ریپو مثل github.com/owner/name یا owner/name است." else null
        FoundingPath.REGISTER -> nameEnError(d.nameEn)
    }

    /** The first step [d] cannot leave yet (1-based), or null when every step is complete. */
    fun firstIncomplete(d: FoundingDraft, taken: Set<String>): Int? = (1..STEPS).firstOrNull { errors(it, d, taken).isNotEmpty() }

    /** Field → sentence, for one step (1: who, 2: how it starts, 3: brand, optional, 4: review). */
    fun errors(step: Int, d: FoundingDraft, taken: Set<String>): Map<String, String> = when (step) {
        1 -> listOfNotNull(nameError(d.nameFa)?.let { "name" to it }, codeError(d.code, taken)?.let { "code" to it }, taglineError(d.tagline)?.let { "tagline" to it }).toMap()
        2 -> pathError(d)?.let { mapOf("path" to it) }.orEmpty()
        3 -> if (d.colorIndex != null && d.colorIndex !in 1..8) mapOf("color" to "رنگ یکی از هشت رنگ است.") else emptyMap()
        4 -> (1..3).flatMap { errors(it, d, taken).entries }.associate { it.key to it.value }
        else -> emptyMap()
    }

    /** The founding's `brief_md`: the owner's name, code and line first (the hub's `POST /foundings` takes only `source`), then the
     *  idea or what the owner wants from the repository. [FoundingBrief.parse] reads it back. */
    fun brief(d: FoundingDraft): String = buildString {
        append(FoundingBrief.NAME).append(d.nameFa.trim()).append('\n')
        append(FoundingBrief.CODE).append(d.code).append('\n')
        append(FoundingBrief.LINE).append(d.tagline.trim().replace('\n', ' '))
        val body = if (d.path == FoundingPath.IDEA) d.idea.trim() else ""
        if (body.isNotEmpty()) append("\n\n").append(body)
    }
}

/** The owner's name, code and one line, as the wizard writes them at the top of a founding's brief. */
object FoundingBrief {
    const val NAME = "نام: "
    const val CODE = "کد: "
    const val LINE = "در یک خط: "

    data class Parsed(val nameFa: String?, val code: String?, val tagline: String?, val body: String)

    fun parse(md: String?): Parsed {
        val lines = md.orEmpty().lines()
        var name: String? = null
        var code: String? = null
        var line: String? = null
        var i = 0
        while (i < lines.size) {
            val l = lines[i].trim()
            when {
                l.startsWith(NAME.trim()) -> name = l.removePrefix(NAME.trim()).trim().ifBlank { null }
                l.startsWith(CODE.trim()) -> code = l.removePrefix(CODE.trim()).trim().takeIf { FoundingRules.CODE.matches(it) }
                l.startsWith(LINE.trim()) -> line = l.removePrefix(LINE.trim()).trim().ifBlank { null }
                else -> break
            }
            i++
        }
        val body = lines.drop(i).joinToString("\n").trim()
        return Parsed(name, code, line, body)
    }
}

/** The logo and colour chosen in the wizard for a founding whose company does not exist yet (the hub makes it at the seal); used
 *  on the founding's «مُهر شرکت» step. Only a file id and a palette slot, nothing else. */
class FoundingBrandStore private constructor(private val prefs: SharedPreferences?) {
    constructor(context: Context) : this(context.getSharedPreferences("hq.founding", Context.MODE_PRIVATE))

    data class Pending(val fileId: String?, val colorIndex: Int?)

    private val memory = mutableMapOf<String, Pending>()

    fun get(ref: String): Pending? = if (prefs == null) memory[ref] else prefs.getString(ref, null)?.let(::decode)

    fun put(ref: String, p: Pending) {
        if (p.fileId == null && p.colorIndex == null) return forget(ref)
        if (prefs == null) memory[ref] = p else prefs.edit().putString(ref, encode(p)).apply()
    }

    fun forget(ref: String) { if (prefs == null) memory.remove(ref) else prefs.edit().remove(ref).apply() }

    companion object {
        fun memory() = FoundingBrandStore(null)
        fun encode(p: Pending): String = "${p.fileId.orEmpty()}|${p.colorIndex ?: ""}"
        fun decode(s: String): Pending? = s.split('|', limit = 2).takeIf { it.size == 2 }?.let { Pending(it[0].ifBlank { null }, it[1].toIntOrNull()) }
    }
}

/** A founding's stages and, for the one it is in, what is happening in plain words and whose turn it is (§18.8, §18.16). */
object FoundingStages {
    data class Stage(val state: String, val fa: String)
    data class Now(val title: String, val body: String, val ownersTurn: Boolean)

    /** The stepper: an idea has no audit, its first stage is the proposal being written. */
    fun of(sourceKind: String): List<Stage> = listOf(
        Stage("auditing", if (sourceKind == "repo") "ممیزی" else "نوشتن پیشنهاد"),
        Stage("proposed", "مُهر پیشنهاد"),
        Stage("sealed", "طرح سرور"),
        Stage("provisioning", "ساخت سرور"),
        Stage("ready_for_login", "ورود تو"),
        Stage("active", "فعال"),
    )

    fun now(state: String, sourceKind: String, hasAudit: Boolean): Now = when (state) {
        "auditing" -> if (sourceKind == "repo" && !hasAudit) Now(
            "ممیزی فقط‌خواندنی ریپو در جریان است",
            "مهندس پلتفرم کد را میخواند (معماری، کیفیت، امنیت، تست، بدهی فنی) و با شواهد گزارش میدهد؛ هیچ چیز اجرا یا push نمیشود. بعد پیشنهاد نوشته میشود. کاری از تو لازم نیست.",
            false,
        ) else Now(
            "پیشنهاد در حال نوشتن است",
            "مدیر AI Ops " + (if (sourceKind == "repo") "از روی ممیزی" else "از روی ایده‌ات") + " نام، ساختار، تیم، بودجه و نقشه‌ی راه ۹۰ روزه را مینویسد و برای مُهر به کارتابلت میفرستد. کاری از تو لازم نیست.",
            false,
        )
        "proposed" -> Now("پیشنهاد آماده است؛ نوبت توست", "در کارتابل بخوانش: مُهر کنی شرکت ساخته میشود؛ میتوانی برگردانی یا رد کنی. هنوز هیچ هزینه‌ای نیست.", true)
        "sealed" -> Now("شرکت ساخته شد؛ نوبت طرح سرور", "طرح سرور با قیمت واقعی همین پایین است و با مُهر جدای تو ساخته میشود. شرکت بی‌سرور هم ثبت است.", true)
        "provisioning" -> Now("سرور در حال ساخت است", "قدم‌به‌قدم همین پایین؛ چند دقیقه طول میکشد. اگر قدمی شکست بخورد، با همان مُهر از همان قدم ادامه میدهد.", false)
        "ready_for_login" -> Now("سرور آماده است؛ نوبت توست", "خودت وارد سرور شو و Claude Code را با حساب خودت باز کن، بعد شرکت را فعال کن. رمز هیچ‌وقت به ایجنت نمیرسد.", true)
        "active" -> Now("شرکت فعال است", "مدیرعامل شروع کرده؛ شرکت در ستاره‌ها و نظارت است. از صفحه‌ی شرکت دنبالش کن.", false)
        "cancelled" -> Now("این تأسیس لغو شد", "ممیزی و پیشنهاد در سوابق میماند؛ کارت‌هایش از کارتابل برداشته شد.", false)
        else -> Now("وضعیت: $state", "", false)
    }
}
