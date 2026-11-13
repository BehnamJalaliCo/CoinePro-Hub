package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.OWNER_TZ
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * Debug builds only: contract §47 to §50 ⟨1.31⟩, what the reels order still lacked.
 *
 * - **The ledger (§47.4):** TradeYar's in the working group «کمپین مناسبتی» holds 42 topics and 40 outside samples (two pages; lines from
 *   the routine's own claim, from a package that went out, and added by the owner); CoinePro FX's is empty. Adding one already said is a
 *   `409 topic_taken` that names the earlier line and its day; a sample needs its link; a freed line leaves the list.
 * - **The narrator (§48):** TradeYar's is set (Charon, «آرام و مطمئن»); ⟨1.35⟩ Pro-Chart's too (Kore, «فارسی معیار و گرم»: what its reels
 *   session F-0094 set once, §57's «گوینده» chip); CoinePro FX has none, and there the hub is out of its account of the speech service
 *   (the owner's one step). A voice the service does not have is a 422.
 * - **The best hour (§49):** TradeYar's account has enough posts (21:00); CoinePro FX's has too few yet; Pro-Chart's was never read.
 * - **A standing routine (§50):** F-0100 (Pro-Chart's reels session) has one on and one off (its last runs failed); `POST /routines` makes
 *   one from a sentence that names a time, on at once, and refuses any other with the hub's own words; `/automations/{ref}/state`
 *   switches these.
 *
 * A scheduled post taken back (§51), the best hour of a publish sheet and the effort of an output (§53) are in [OutputsDemo].
 */
internal class V47Demo(private val v35: V35Demo) {
    private val zone = ZoneId.of(OWNER_TZ)
    private fun at(minAgo: Long): String = HqClock.now().minus(minAgo, ChronoUnit.MINUTES).toString()
    private fun day(daysAgo: Int, minute: Int = 0): String = HqClock.now().minus(daysAgo.toLong(), ChronoUnit.DAYS).minus(minute.toLong(), ChronoUnit.MINUTES).toString()

    // ------------------------------------------------------------------ §47 the ledger --
    private var seq = 1
    private fun entry(kind: String, title: String, url: String?, at: String, source: String, by: String) = jo(
        "id" to "0193c0de-47a0-7000-8000-%012d".format(seq++), "kind" to kind, "title_fa" to title, "url" to url, "at" to at, "by" to by, "source" to source,
        "work_ref" to if (source == "owner") null else "W-%06d".format(300 + seq), "output" to if (source == "package") "O-%06d".format(900 + seq) else null,
    )

    private val ledgers: MutableMap<Pair<String, String>, MutableList<JsonObject>> = mutableMapOf(
        ("pb_1" to "TY") to run {
            val themes = listOf("حد ضرر", "حد سود", "حمایت و مقاومت", "واگرایی در RSI", "میانگین متحرک", "کندل‌های برگشتی")
            val angles = listOf("در ۳۰ ثانیه", "برای تازه‌کارها", "در بازار طلا", "در تایم‌فریم روزانه", "با یک مثال واقعی", "و سه اشتباه رایج", "و وقتی جواب نمیدهد")
            val topics = (0 until 42).map { i ->
                val source = when { i == 2 || i == 9 -> "owner"; i % 5 == 3 -> "package"; else -> "claim" }
                entry("topic", "${themes[i % themes.size]} ${angles[i / themes.size]}", null, day(i, 95), source, if (source == "owner") "owner" else "TY-MEDIA-02")
            }
            val looks = listOf("نمودار شمعی با خط طلایی", "تیتر درشت روی زمینه‌ی تیره", "شمارش معکوس سه قدم", "مقایسه‌ی قبل و بعد", "متن متحرک روی چارت")
            val samples = (0 until 40).map { i ->
                entry("reference", "نمونه‌ی موشن: ${looks[i % looks.size]}", "https://www.pinterest.com/pin/${7036810 + i * 7919}${i % 10}/", day(i, 110), if (i == 4) "owner" else "claim", if (i == 4) "owner" else "TY-MEDIA-02")
            }
            (topics + samples).toMutableList()
        },
        ("pb_1" to "FX") to mutableListOf(),
    )

    /** A title as the hub compares it: letters unified, marks and spaces dropped, the words in any order. */
    private fun words(title: String): Set<String> = title.replace('ي', 'ی').replace('ك', 'ک').replace("‌", "")
        .map { ch -> if (ch in '۰'..'۹') '0' + (ch - '۰') else if (ch in '٠'..'٩') '0' + (ch - '٠') else ch }.joinToString("")
        .split(Regex("[\\s،؛.!؟?«»:()\\-]+")).filter { it.isNotBlank() && it !in FILLERS }.toSet()

    private fun ledgerRoute(method: String, key: String, code: String, id: String?, query: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        val list = ledgers[key to code] ?: return 404 to problem(404, "not_found", "این شرکت عضو این کارگروه نیست.")
        if (id != null) {
            if (method != "DELETE") return null
            val e = list.firstOrNull { it.str("id") == id } ?: return 404 to problem(404, "not_found", "این خط در دفتر نیست.")
            list.remove(e)
            return 200 to e
        }
        if (method == "GET") {
            val kind = query["kind"]
            val q = query["q"]?.trim().orEmpty()
            val rows = list.filter { (kind == null || it.str("kind") == kind) && (q.isEmpty() || it.str("title_fa").orEmpty().contains(q)) }
            val from = query["cursor"]?.toIntOrNull() ?: 0
            val limit = (query["limit"]?.toIntOrNull() ?: 50).coerceIn(1, 200)
            return 200 to jo(
                "items" to JsonArray(rows.drop(from).take(limit)), "topics" to list.count { it.str("kind") == "topic" },
                "references" to list.count { it.str("kind") == "reference" }, "next_cursor" to (from + limit).takeIf { it < rows.size }?.toString(),
            )
        }
        if (method != "POST") return null
        val kind = body?.str("kind") ?: "topic"
        val title = body?.str("title_fa")?.trim().orEmpty()
        val url = body?.str("url")?.trim()?.ifBlank { null }
        if (kind == "reference" && url == null) return 422 to JsonObject(problem(422, "validation_failed", "نمونه بدون لینک ثبت نمیشود.") + ("fields" to jo("url" to "a reference needs its address")))
        if (kind == "topic" && title.length < 2) return 422 to problem(422, "validation_failed", "موضوع را بنویس.")
        val hit = list.firstOrNull { e ->
            e.str("kind") == kind && if (kind == "reference") e.str("url")?.trimEnd('/') == url?.trimEnd('/') else words(e.str("title_fa").orEmpty()) == words(title)
        }
        if (hit != null) {
            val said = hit.str("at").orEmpty().take(10)
            return 409 to JsonObject(
                problem(409, "topic_taken", "این پیش‌تر گفته شده: «${hit.str("title_fa")}» ($said). یک موضوع تازه انتخاب کن.") +
                    ("fields" to jo("title_fa" to "taken: «${hit.str("title_fa")}» ($said)", "recent" to list.filter { it.str("kind") == kind }.take(5).joinToString("؛ ") { it.str("title_fa").orEmpty() })),
            )
        }
        val made = entry(kind, title, url, HqClock.now().toString(), "owner", "owner")
        list.add(0, made)
        return 201 to made
    }

    // ------------------------------------------------------------------ §48 the narrator --
    private val voices = JsonArray(VOICES.map { (n, g, t) -> jo("name" to n, "gender" to g, "trait_fa" to t) })
    private val narrators = mutableMapOf(
        "TY" to jo("voice" to "Charon", "style_fa" to "آرام و مطمئن", "by" to "owner", "updated_at" to at(4_300)),
        "PC" to jo("voice" to "Kore", "style_fa" to "فارسی معیار و گرم", "by" to "ceo@PC", "updated_at" to at(820)),
    )

    /** ⟨1.35⟩ §57.1 the narrator of [code] as a session's team carries it (`TeamNarrator`), when one is set. */
    @Synchronized
    fun teamNarrator(code: String): JsonObject? = narrators[code]?.let { n ->
        val voice = n.str("voice").orEmpty()
        val trait = VOICES.firstOrNull { it.first == voice }?.third
        jo("company" to code, "voice" to voice, "voice_fa" to if (trait != null) "$voice ($trait)" else voice, "style_fa" to n.str("style_fa"))
    }

    private fun narrator(code: String): JsonObject {
        val n = narrators[code]
        return jo(
            "company" to code, "set" to (n != null), "voice" to (n?.str("voice") ?: "Kore"), "style_fa" to (n?.str("style_fa") ?: ""),
            "by" to n?.str("by"), "updated_at" to n?.str("updated_at"), "voices" to voices,
            // the hub's sign-in is one for all; the demo shows each state on a company of its own
            "aistudio" to when (code) { "TY" -> "signed_in"; "FX" -> "signed_out"; else -> "unknown" },
        )
    }

    // ------------------------------------------------------------------ §49 the best hour --
    /** The next time the clock reads [hour] in the owner's zone. */
    private fun next(hour: Int, minute: Int = 0): String {
        val now = HqClock.now().atZone(zone)
        val t = now.toLocalDate().atTime(hour, minute).atZone(zone).let { if (it.isAfter(now)) it else it.plusDays(1) }
        return t.toInstant().toString()
    }

    /** As the hub's rule answers it: enough posts name an hour; too few say how many there are; never read says so. */
    fun bestHour(code: String, account: String?): JsonObject? = when (code) {
        "TY" -> jo(
            "account" to "tradeyar", "hour" to "21:00", "at" to next(21), "enough" to true, "posts" to 38, "days" to 90, "basis" to "likes_comments",
            "note_fa" to "از روی لایک و کامنت 38 پست در 90 روز اخیر (بازدید و reach هنوز خوانده نمیشود)", "read_at" to at(260),
        )
        "FX" -> if (account == null || account == "coineprofx") jo(
            "account" to "coineprofx", "hour" to null, "at" to null, "enough" to false, "posts" to 7, "days" to 19, "basis" to "likes_comments",
            "note_fa" to "هنوز داده‌ی کافی نیست (7 پست در 19 روز؛ دست‌کم 12 پست در 28 روز لازم است)", "read_at" to at(260),
        ) else unread(account)
        "PC" -> unread(account ?: "pro.chart")
        else -> null
    }

    private fun unread(account: String) = jo(
        "account" to account, "hour" to null, "at" to null, "enough" to false, "posts" to 0, "days" to 0, "basis" to "likes_comments",
        "note_fa" to "آمار پست‌های این حساب هنوز از IG-Hub خوانده نشده است", "read_at" to null,
    )

    // ------------------------------------------------------------------ §50 standing routines --
    private var routineSeq = 903
    private fun routine(ref: String, order: String?, company: String?, sentence: String, whenFa: String, what: String, state: String, nextAt: String?, runs: Int, last: String?, note: String? = null) = jo(
        "ref" to ref, "company" to company, "sentence_fa" to sentence, "when_fa" to whenFa, "preview_fa" to what, "state" to state,
        "next_at" to nextAt.takeIf { state == "on" }, "last_run_at" to last, "runs" to runs, "order" to order, "note_fa" to note,
    )

    private val routines = mutableListOf(
        routine(
            "AT-0902", "F-0100", "PC", "هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده", "هر روز ساعت 09:00",
            "یک کار تازه برای «کارشناس سئوی پرو-چارت» با عنوان «رتبه‌های سئوی سایت را ببین و خلاصه بده» ساخته میشود", "on", next(9), 6, at(190),
        ),
        routine(
            "AT-0901", "F-0100", "PC", "هر جمعه ساعت ۲۰ گزارش بازدید ریلزها را برایم بفرست", "هر جمعه ساعت 20:00",
            "برای تو این خبر فرستاده میشود: «گزارش بازدید ریلزهای هفته»", "off", null, 2, at(5_900),
            note = "دو نوبت پشت سر هم انجام نشد: آمار اینستاگرام خوانده نشد.",
        ),
    )

    /** The standing routines asked for in a session, newest first (`OrderReport.routines`). */
    @Synchronized
    fun routinesOf(order: String): JsonArray = JsonArray(routines.filter { it.str("order") == order })

    private fun makeRoutine(body: JsonObject?): Pair<Int, JsonElement> {
        val sentence = body?.str("sentence_fa")?.trim().orEmpty()
        if (sentence.length < 3) return 422 to problem(422, "validation_failed", "جمله‌ی روال را بنویس.")
        val plain = sentence.replace('ي', 'ی').map { ch -> if (ch in '۰'..'۹') '0' + (ch - '۰') else ch }.joinToString("")
        val weekday = WEEKDAYS.firstOrNull { "هر $it" in plain }
        val daily = listOf("هر روز", "روزانه", "هر صبح", "هر شب").any { it in plain }
        // a sentence that names no time is more (or less) than a routine: the hub's own words, and nothing is made
        if (weekday == null && !daily) return 422 to problem(
            422, "validation_failed",
            "این جمله یک روال زمان‌دار ساده نیست (مثلاً «هر روز ساعت ۹ رتبه‌های سئوی پروچارت را ببین و خلاصه بده»). قاعده‌ای که با یک رویداد یا عدد شروع میشود یا خط تولید و تبلیغ را تغییر میدهد، از «خودکارسازی» با مُهر تو ساخته میشود.",
        )
        val hour = Regex("ساعت\\s*(\\d{1,2})").find(plain)?.groupValues?.get(1)?.toIntOrNull()?.takeIf { it in 0..23 } ?: 9
        val order = body?.str("order")
        val look = order?.let(v35::look)
        val what = sentence.substringAfter("ساعت", sentence).trim().replace(Regex("^[\\d۰-۹:]+\\s*"), "").ifBlank { sentence }
        val made = routine(
            "AT-%04d".format(routineSeq++), order, body?.str("company") ?: look?.company, sentence,
            (if (weekday != null) "هر $weekday" else "هر روز") + " ساعت %02d:00".format(hour),
            "یک کار تازه برای «${look?.holderFa ?: "مدیرعامل"}» با عنوان «$what» ساخته میشود", "on", next(hour), 0, null,
        )
        routines.add(0, made)
        // the session says so, as the hub does
        if (order != null) v35.append(order, emptyList(), stepFa = "روال دائمی ساخته شد: ${made.str("when_fa")}، $what")
        return 201 to made
    }

    // ------------------------------------------------------------------ routes --
    @Synchronized
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        Regex("^/groups/([a-z0-9_]+)/members/([A-Z][A-Z0-9]{1,9})/topics(?:/([^/]+))?$").find(path)?.let { m ->
            return ledgerRoute(method, m.groupValues[1], m.groupValues[2], m.groupValues[3].ifBlank { null }, query, body)
        }
        Regex("^/companies/([A-Z][A-Z0-9]{1,9})/narrator$").find(path)?.let { m ->
            val code = m.groupValues[1]
            if (code !in COMPANIES) return 404 to problem(404, "not_found", "این شرکت را نمیشناسم.")
            if (method == "GET") return 200 to narrator(code)
            if (method != "PUT") return null
            val asked = body?.str("voice")?.trim().orEmpty()
            val name = VOICES.firstOrNull { it.first.equals(asked, ignoreCase = true) }?.first
                ?: return 422 to JsonObject(
                    problem(422, "validation_failed", "صدای «$asked» در ای‌آی استودیو نیست؛ یکی از صداهای آماده مثل ${VOICES.take(6).joinToString("، ") { it.first }}.") +
                        ("fields" to jo("voice" to "not one of AI Studio's prebuilt voices")),
                )
            narrators[code] = jo("voice" to name, "style_fa" to body?.str("style_fa").orEmpty().trim().take(500), "by" to "owner", "updated_at" to HqClock.now().toString())
            return 200 to narrator(code)
        }
        Regex("^/companies/([A-Z][A-Z0-9]{1,9})/best-hour$").find(path)?.let { m ->
            if (method != "GET") return null
            return bestHour(m.groupValues[1], query["account"]?.removePrefix("@"))?.let { 200 to it } ?: (404 to problem(404, "not_found", "این شرکت را نمیشناسم."))
        }
        if (path == "/routines") return when (method) {
            "GET" -> 200 to JsonArray(routines.filter { (query["order"] == null || it.str("order") == query["order"]) && (query["company"] == null || it.str("company") == query["company"]) })
            "POST" -> makeRoutine(body)
            else -> null
        }
        Regex("^/automations/(AT-09\\d\\d)/state$").find(path)?.let { m ->
            if (method != "POST") return null
            val i = routines.indexOfFirst { it.str("ref") == m.groupValues[1] }
            if (i < 0) return null
            val on = body?.str("state") == "on"
            val r = routines[i]
            if (r.str("state") == "proposed") return 409 to problem(409, "validation_failed", "این روال هنوز مُهر نشده است.")
            val hour = Regex("(\\d{2}):").find(r.str("when_fa").orEmpty())?.groupValues?.get(1)?.toIntOrNull() ?: 9
            // switched on again, its failures are forgotten and it has a next run; off, it has none
            routines[i] = JsonObject(r + mapOf("state" to JsonPrimitive(if (on) "on" else "off"), "next_at" to (if (on) JsonPrimitive(next(hour)) else JsonNull), "note_fa" to (if (on) JsonNull else (r["note_fa"] ?: JsonNull))))
            val now = routines[i]
            return 200 to jo(
                "ref" to now.str("ref"), "company" to now.str("company"), "sentence_fa" to now.str("sentence_fa"), "rule" to jo(), "state" to now.str("state"),
                "runs" to now["runs"], "last_run_at" to now.str("last_run_at"), "n8n_workflow" to null, "preview_fa" to now.str("preview_fa"), "routine" to true, "order" to now.str("order"),
            )
        }
        return null
    }

    companion object {
        private val COMPANIES = setOf("HQ", "TY", "FX", "PC")
        private val FILLERS = setOf("آموزش", "معرفی", "ویدیو", "چیست", "ریلز")
        private val WEEKDAYS = listOf("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "هفته")

        /** The prebuilt speakers as the hub lists them (name, whose voice, its character). */
        private val VOICES = listOf(
            Triple("Zephyr", "female", "روشن"), Triple("Puck", "male", "سرزنده"), Triple("Charon", "male", "اطلاع‌رسان"), Triple("Kore", "female", "محکم"),
            Triple("Fenrir", "male", "پرشور"), Triple("Leda", "female", "جوان"), Triple("Orus", "male", "محکم"), Triple("Aoede", "female", "نرم و هوایی"),
            Triple("Callirrhoe", "female", "راحت"), Triple("Autonoe", "female", "روشن"), Triple("Enceladus", "male", "نفس‌دار"), Triple("Iapetus", "male", "شفاف"),
            Triple("Umbriel", "male", "راحت"), Triple("Algieba", "male", "نرم"), Triple("Despina", "female", "نرم"), Triple("Erinome", "female", "شفاف"),
            Triple("Algenib", "male", "خش‌دار"), Triple("Rasalgethi", "male", "اطلاع‌رسان"), Triple("Laomedeia", "female", "سرزنده"), Triple("Achernar", "female", "آرام"),
            Triple("Alnilam", "male", "محکم"), Triple("Schedar", "male", "یکنواخت"), Triple("Gacrux", "female", "پخته"), Triple("Pulcherrima", "female", "رو به جلو"),
            Triple("Achird", "male", "دوستانه"), Triple("Zubenelgenubi", "male", "خودمانی"), Triple("Vindemiatrix", "female", "ملایم"), Triple("Sadachbia", "male", "پرجنب‌وجوش"),
            Triple("Sadaltager", "male", "دانا"), Triple("Sulafat", "female", "گرم"),
        )
    }

    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
    private fun jo(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(kv.associate { (k, v) ->
        k to when (v) {
            null -> JsonNull; is JsonElement -> v; is String -> JsonPrimitive(v); is Number -> JsonPrimitive(v); is Boolean -> JsonPrimitive(v)
            else -> error("unsupported ${v::class}")
        }
    })
    private fun problem(status: Int, code: String, fa: String) = jo("code" to code, "message_fa" to fa, "status" to status, "title" to code, "type" to "about:blank")
}
