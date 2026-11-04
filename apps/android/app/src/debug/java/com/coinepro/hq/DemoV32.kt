package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.net.StreamEvent
import java.time.LocalDate
import java.time.ZoneId
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * Debug builds only: contract §32 ⟨1.14⟩, talk. Deterministic (every time from [HqClock]); the screenshots are the same on any machine.
 *
 * - **Personas (§32.1):** the secretary, the overseer, the assistant, the advisor and a manager template, each with a voice.
 * - **Conversations:** CV-0001 with the secretary (consult: an order card offered, one done, a spoken turn), CV-0002 in work mode with the
 *   CEO of TradeYar brought in (a hire card and the minutes card with its tasks), CV-0003 with the overseer, CV-0004 an old one.
 * - **A turn (§32.2):** the answer is stored at once and the app plays it back as a script (no network stream, no sound); words that
 *   ask for work («بساز»، «فرمان») make an order card, «صورت‌جلسه» a minutes card, as the hub's rules do before any model.
 * - **Voice (§32.5–32.6):** three engines (the best, the cheaper, the local one), their voices, the month's meter with a cap, the price
 *   that doubles on 1 January; a key saved turns the light yellow and, a moment later on the stream, green.
 */
internal class V32Demo {
    private val now = HqClock.now()
    private val tehran = ZoneId.of("Asia/Tehran")
    private val today: LocalDate = LocalDate.ofInstant(now, tehran)
    private fun at(off: Long, h: Int, m: Int = 0): String = today.plusDays(off).atTime(h, m).atZone(tehran).toInstant().toString()

    private fun persona(key: String, role: String, title: String, company: String?, engine: String, voice: String, face: String? = null, consultOnly: Boolean = false) = jo(
        "key" to key, "role" to role, "title_fa" to title, "company" to company,
        "voice" to jo("engine" to engine, "voice" to voice, "rate" to 1.0), "brain" to jo("task_class" to "talk_turn", "effort" to "medium"),
        "tools" to ja(listOf("work.list", "decisions.list", "orders.today").map { JsonPrimitive(it) }), "face" to face, "consult_only" to consultOnly,
    )

    private val personas = mutableListOf(
        persona("secretary", "holding_secretary", "منشی هلدینگ", null, "gemini-3.8-flash-tts", "Kore"),
        persona("overseer", "overseer", "ناظر کل", null, "gemini-3.8-flash-lite-tts", "Charon", consultOnly = true),
        persona("assistant", "assistant", "دستیار شخصی", null, "piper", "fa-male-1"),
        persona("advisor", "advisor", "مشاور کل", null, "gemini-3.8-flash-tts", "Orus", consultOnly = true),
        persona("manager", "ceo", "مدیرعامل تریدیار", "TY", "gemini-3.8-flash-tts", "Puck"),
    )

    private fun engine(key: String, title: String, provider: String, model: String, languages: Int, rank: String, state: String, reason: String?, audioOut: Double, next: Double?, voices: List<Triple<String, String, Boolean>>) = jo(
        "key" to key, "title_fa" to title, "provider" to provider, "model" to model, "languages" to languages, "rank_fa" to rank,
        "key_pattern" to (if (provider == "google") "AIza[0-9A-Za-z_-]{35}" else null), "state" to state, "reason_fa" to reason, "checked_at" to at(0, 6),
        "price" to jo(
            "text_in_per_m" to (if (provider == "google") "0.5" else "0"), "audio_out_per_m" to (if (provider == "google") audioOut.toString() else "0"), "audio_tokens_per_s" to 25,
            "valid_until" to (if (next != null) "2026-12-31" else null),
            "next" to (if (next != null) jo("from" to "2027-01-01", "text_in_per_m" to "1.0", "audio_out_per_m" to next.toString()) else null),
            "source_url" to "https://ai.google.dev/pricing", "as_of" to "2026-11-01",
        ),
        "voices" to ja(voices.map { (n, g, _) -> jo("name" to n, "gender_fa" to g, "sample_file" to null) }),
    )

    private val engines = mutableListOf(
        engine("gemini-3.8-flash-tts", "جمینای فلش", "google", "gemini-3.8-flash-preview-tts", 130, "بهترین کیفیت", "ok", null, 9.0, 18.0,
            listOf(Triple("Kore", "زن", true), Triple("Zephyr", "زن", true), Triple("Charon", "مرد", true), Triple("Orus", "مرد", true), Triple("Puck", "مرد جوان", true))),
        engine("gemini-3.8-flash-lite-tts", "جمینای فلش لایت", "google", "gemini-3.8-flash-lite-preview-tts", 101, "حدود یک‌سوم ارزان‌تر", "ok", null, 6.0, 12.0,
            listOf(Triple("Kore", "زن", true), Triple("Charon", "مرد", true), Triple("Puck", "مرد جوان", true))),
        engine("piper", "صدای ساده‌ی هاب", "local", "piper-fa", 1, "محلی و رایگان؛ همیشه آخرین زنجیره", "ok", null, 0.0, null,
            listOf(Triple("fa-male-1", "مرد", true), Triple("fa-female-1", "زن", true))),
    )

    private fun turn(cv: String, n: Int, by: String, source: String, text: String, show: String? = null, say: String? = null, cards: List<JsonObject> = emptyList(), audio: Int = 0, off: Long = 0, h: Int = 9, m: Int = 0, state: String = "done") = jo(
        "id" to "T-%s-%d".format(cv.removePrefix("CV-"), n), "conversation" to cv, "n" to n, "by" to by, "source" to source, "text" to text, "say_fa" to say, "show_md" to show,
        "cards" to ja(cards), "audio" to ja((0 until audio).map { jo("seq" to it, "file_id" to "demo-talk-$cv-$n-$it", "seconds" to 3.4 + it, "engine" to "gemini-3.8-flash-tts") }),
        "tokens" to jo("input" to 5400, "output" to 380, "cache_read" to 4800, "cache_write" to 0),
        "voice" to (if (audio > 0) jo("engine" to "gemini-3.8-flash-tts", "seconds" to 3.4 * audio, "audio_tokens" to 85 * audio, "usd" to "0.0008") else null),
        "state" to state, "reason_fa" to null, "at" to at(off, h, m),
    )

    private fun card(id: String, turn: String, kind: String, title: String, body: String, payload: JsonObject, state: String = "offered", made: List<String> = emptyList()) = jo(
        "id" to id, "turn" to turn, "kind" to kind, "title_fa" to title, "body_fa" to body, "payload" to payload, "state" to state, "made" to ja(made.map { JsonPrimitive(it) }), "reason_fa" to null,
    )

    private val orderPayload = jo("title_fa" to "ریلز آموزشی درباره‌ی پیوت طلا", "brief_fa" to "یک ریلز ۳۰ ثانیه‌ای برای اینستاگرام تریدیار درباره‌ی نقطه‌ی پیوت طلا بسازید و پیش از انتشار برای من بفرستید.", "company" to "TY", "department" to "MEDIA", "priority" to "normal")

    private val minutesPayload = jo(
        "summary_fa" to "درباره‌ی هفته‌ی آموزش طلا و بودجه‌ی تبلیغ حرف زدیم. قرار شد ریلزها از شنبه شروع شود و تبلیغ فقط با بازده بالاتر از یک‌ونیم ادامه پیدا کند.",
        "decisions" to ja(listOf("هفته‌ی آموزش طلا از شنبه شروع میشود", "بودجه‌ی تبلیغ این هفته ۲ میلیون تومان است", "ریلزها پیش از انتشار برای مدیر کل میآید").map { JsonPrimitive(it) }),
        "tasks" to ja(listOf(
            jo("title_fa" to "سه ریلز آموزشی طلا بسازید", "company" to "TY", "department" to "MEDIA", "due" to "شنبه"),
            jo("title_fa" to "گزارش بازده تبلیغ هفته را بفرستید", "company" to "TY", "department" to "GROWTH", "due" to "چهارشنبه"),
        )),
    )

    private val convs = mutableListOf(
        conv("CV-0001", "امروز چه چیزهایی منتظر من است؟", "secretary", listOf("secretary"), "consult", -0, 8, 5, "درباره‌ی کارهای امروز و یک ریلز آموزشی حرف زدیم.", 1),
        conv("CV-0002", "هفته‌ی آموزش طلا با مدیرعامل تریدیار", "ceo@TY", listOf("secretary", "ceo@TY"), "work", -1, 15, 4, null, 2),
        conv("CV-0003", "ریسک‌های این هفته", "overseer", listOf("overseer"), "consult", -2, 11, 3, "ناظر کل سه ریسک باز را با شاهد گفت.", 0),
        conv("CV-0004", "برنامه‌ی سفر استانبول", "assistant", listOf("assistant"), "consult", -6, 17, 2, "سه پیشنهاد هتل زیر ۱۵۰ یورو.", 0),
    )

    private fun conv(ref: String, title: String, persona: String, present: List<String>, mode: String, off: Long, h: Int, turns: Int, summary: String?, open: Int) = jo(
        "ref" to ref, "title_fa" to title, "persona" to persona, "present" to ja(present.map { JsonPrimitive(it) }), "mode" to mode,
        "started_at" to at(off, h - 1), "last_turn_at" to at(off, h, 20), "turns" to turns, "summary_fa" to summary,
        "cost" to jo("tokens" to 18400 * turns, "usd_equiv" to "0.0" + (turns * 7), "voice_usd" to "0.0" + (turns * 3)), "open_cards" to open,
    )

    private val turnsBy = mutableMapOf(
        "CV-0001" to mutableListOf(
            turn("CV-0001", 1, "owner", "typed", "امروز چه چیزهایی منتظر من است؟", off = 0, h = 8, m = 50),
            turn("CV-0001", 2, "secretary", "typed", "", show = "صبح بخیر. امروز **سه چیز** منتظر توست:\n\n- یک تصمیم استخدام در تریدیار (ریسک متوسط)\n- ایمیل دوم حقوقی که فقط مُهر تو را میخواهد\n- ریلز آموزشی طلا که دیروز تحویل شد و نمره‌ات را میخواهد\n\nاز کدام شروع کنیم؟", say = "صبح بخیر. امروز سه چیز منتظر توست: یک تصمیم استخدام، یک ایمیل حقوقی و یک ریلز آماده‌ی نمره. از کدام شروع کنیم؟", audio = 2, off = 0, h = 8, m = 51),
            turn("CV-0001", 3, "owner", "hold", "یک ریلز آموزشی درباره‌ی پیوت طلا برای تریدیار بساز", off = 0, h = 8, m = 53),
            turn("CV-0001", 4, "secretary", "typed", "", show = "حتماً. این فرمان را آماده کردم؛ تا نزنی «فرمان بده»، هیچ‌کاری شروع نمیشود. متن و دپارتمان را میتوانی عوض کنی.", say = "فرمان ریلز را آماده کردم. هر وقت خواستی بزن فرمان بده.",
                cards = listOf(card("TC-101", "T-0001-4", "order", "فرمان: ریلز آموزشی پیوت طلا", "برای تریدیار، دپارتمان رسانه و طراحی؛ فوریت معمولی.", orderPayload)), audio = 1, off = 0, h = 8, m = 54),
            turn("CV-0001", 5, "owner", "typed", "قبلی را هم یادآوری کن", off = 0, h = 8, m = 56),
            turn("CV-0001", 6, "secretary", "typed", "", show = "فرمان گزارش هفتگی دیروز ساخته شد و به مدیر رشد رفت.", say = "گزارش هفتگی دیروز رفته است.",
                cards = listOf(card("TC-100", "T-0001-6", "order", "فرمان: گزارش هفتگی رشد", "برای تریدیار، دپارتمان رشد.", jo("title_fa" to "گزارش هفتگی رشد"), state = "done", made = listOf("F-000231"))), audio = 1, off = 0, h = 8, m = 57),
        ),
        "CV-0002" to mutableListOf(
            turn("CV-0002", 1, "secretary", "typed", "", show = "مدیرعامل تریدیار آمد.", off = -1, h = 14, m = 40),
            turn("CV-0002", 2, "owner", "handsfree", "برای هفته‌ی آموزش طلا چه برنامه‌ای داری؟", off = -1, h = 14, m = 42),
            turn("CV-0002", 3, "ceo@TY", "typed", "", show = "هفته‌ی آموزش طلا از **شنبه** شروع میشود: سه ریلز، دو پست کانال و یک مقاله. بودجه‌ی تبلیغ ۲ میلیون تومان است و اگر بازده زیر ۱٫۲ بیاید، متوقفش میکنم.\n\nیک نفر هم برای ساخت ریلزها کم داریم.", say = "هفته‌ی آموزش از شنبه شروع میشود؛ سه ریلز، دو پست و یک مقاله. یک نفر هم برای ریلزها کم داریم.",
                cards = listOf(card("TC-201", "T-0002-3", "hire", "استخدام: طراح ریلز", "یک طراح ریلز برای رسانه‌ی تریدیار؛ حقوق در سقف پاکت ماه.", jo("title_fa" to "طراح ریلز", "note_fa" to "برای هفته‌ی آموزش طلا"))), audio = 2, off = -1, h = 14, m = 43),
            turn("CV-0002", 4, "owner", "typed", "جلسه را جمع کن", off = -1, h = 15, m = 2),
            turn("CV-0002", 5, "ceo@TY", "typed", "", show = "این هم صورت‌جلسه‌ی امروز.", say = "صورت‌جلسه آماده است.", cards = listOf(card("TC-202", "T-0002-5", "minutes", "صورت‌جلسه‌ی هفته‌ی آموزش طلا", "خلاصه، تصمیم‌ها و دو کار؛ موعد و دپارتمان را عوض کن، بعد اجرا کن.", minutesPayload)), off = -1, h = 15, m = 3),
        ),
        "CV-0003" to mutableListOf(
            turn("CV-0003", 1, "owner", "typed", "کدام شرکت از پروتکل‌ها عقب است؟", off = -2, h = 11, m = 0),
            turn("CV-0003", 2, "overseer", "typed", "", show = "فعلاً **فاکس** از همه عقب‌تر است: دو بررسی امنیتی هفته را رد کرده. شاهد: گزارش‌های ۱۴ و ۱۶ آبان.", say = "فاکس از همه عقب‌تر است؛ دو بررسی امنیتی را رد کرده.", audio = 1, off = -2, h = 11, m = 1),
            turn("CV-0003", 3, "owner", "typed", "ممنون", off = -2, h = 11, m = 20),
        ),
        "CV-0004" to mutableListOf(
            turn("CV-0004", 1, "owner", "typed", "سه هتل زیر ۱۵۰ یورو در استانبول پیدا کن", off = -6, h = 17, m = 0),
            turn("CV-0004", 2, "assistant", "typed", "", show = "سه گزینه پیدا کردم؛ همه نزدیک مترو.", say = "سه هتل پیدا کردم.", off = -6, h = 17, m = 20),
        ),
    )

    private var cvSeq = 5
    private var cardSeq = 300
    private var moneyCap: Double? = 10.0
    private var warnAt = 0.8
    private var spent = 0.42
    private var keyed = false

    private val meter = mapOf(
        "month" to { jo(
            "period" to "month", "voice_usd" to usd(spent), "cap_usd" to moneyCap?.let { usd(it) }, "projected_usd" to usd(spent * 30.0 / today.dayOfMonth.coerceAtLeast(1)),
            "by_engine" to ja(listOf(
                jo("engine" to "gemini-3.8-flash-tts", "usd" to "0.37", "seconds" to 214, "audio_tokens" to 5350),
                jo("engine" to "gemini-3.8-flash-lite-tts", "usd" to "0.05", "seconds" to 61, "audio_tokens" to 1525),
                jo("engine" to "piper", "usd" to "0", "seconds" to 42, "audio_tokens" to 0),
            )),
            "by_persona" to ja(listOf(jo("persona" to "secretary", "usd" to "0.29", "seconds" to 150), jo("persona" to "ceo@TY", "usd" to "0.09", "seconds" to 71), jo("persona" to "overseer", "usd" to "0.04", "seconds" to 54))),
            "talk_tokens" to 184200, "talk_usd_equiv" to "1.07", "price_note_fa" to "از 1 ژانویه قیمت دو برابر میشود", "updated_at" to at(0, 8, 30),
        ) },
        "today" to { jo(
            "period" to "today", "voice_usd" to "0.06", "cap_usd" to null, "projected_usd" to "0.06",
            "by_engine" to ja(listOf(jo("engine" to "gemini-3.8-flash-tts", "usd" to "0.06", "seconds" to 33, "audio_tokens" to 825))),
            "by_persona" to ja(listOf(jo("persona" to "secretary", "usd" to "0.06", "seconds" to 33))),
            "talk_tokens" to 41200, "talk_usd_equiv" to "0.21", "price_note_fa" to null, "updated_at" to at(0, 8, 30),
        ) },
    )

    private fun usd(v: Double): String = String.format(java.util.Locale.US, "%.2f", v)

    // -------------------------------------------------------------- routes --
    /** The §32 routes; null for everything else (the rest of the demo answers it). */
    @Synchronized
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        if (path == "/talk/personas" && method == "GET") return 200 to ja(personas)
        Regex("^/talk/personas/([^/]+)$").find(path)?.let { m ->
            if (method != "PUT") return null
            val i = personas.indexOfFirst { it.str("key") == m.groupValues[1] || (it.str("role") + "@" + it.str("company")) == m.groupValues[1] }
            if (i < 0) return 404 to problem(404, "not_found", "این نقش پیدا نشد.")
            val v = personas[i]["voice"] as JsonObject
            personas[i] = personas[i].with("voice" to jo("engine" to (body?.str("engine") ?: v.str("engine")), "voice" to (body?.str("voice") ?: v.str("voice")), "rate" to 1.0))
            return 200 to personas[i]
        }
        if (path == "/talk/conversations") return when (method) {
            "GET" -> {
                val p = query["persona"]?.takeIf { it.isNotBlank() }
                val q = query["q"]?.trim()?.takeIf { it.isNotBlank() }
                val rows = convs.filter { c ->
                    (p == null || c.str("persona") == p || (c["present"] as JsonArray).any { (it as JsonPrimitive).content == p }) &&
                        (q == null || c.str("title_fa").orEmpty().contains(q) || c.str("summary_fa").orEmpty().contains(q) || turnsBy[c.str("ref")].orEmpty().any { it.str("text").orEmpty().contains(q) || it.str("show_md").orEmpty().contains(q) })
                }.sortedByDescending { it.str("last_turn_at") }
                200 to jo("items" to ja(rows), "next_cursor" to null)
            }
            "POST" -> {
                val persona = body?.str("persona") ?: "secretary"
                val id = if (persona == "manager") "${body?.str("role")}@${body?.str("company")}" else persona
                val ref = "CV-%04d".format(cvSeq++)
                val c = conv(ref, "", id, listOf(id), body?.str("mode") ?: "consult", 0, 9, 0, null, 0)
                convs.add(0, c)
                turnsBy[ref] = mutableListOf()
                201 to c
            }
            else -> null
        }
        Regex("^/talk/conversations/(CV-\\d+)$").find(path)?.let { m ->
            val i = convs.indexOfFirst { it.str("ref") == m.groupValues[1] }
            if (i < 0) return 404 to problem(404, "not_found", "این گفتگو پیدا نشد.")
            return when (method) {
                "GET" -> {
                    val ts = turnsBy[m.groupValues[1]].orEmpty()
                    200 to convs[i].with("turns" to ts.size, "turns_page" to jo("items" to ja(ts), "next_cursor" to null))
                }
                "PATCH" -> { convs[i] = convs[i].with(*listOfNotNull(body?.str("mode")?.let { "mode" to it }, body?.str("title_fa")?.let { "title_fa" to it }).toTypedArray()); 200 to convs[i] }
                else -> null
            }
        }
        Regex("^/talk/conversations/(CV-\\d+)/(turns|invite|minutes)$").find(path)?.let { m ->
            if (method != "POST") return null
            val ref = m.groupValues[1]
            val i = convs.indexOfFirst { it.str("ref") == ref }
            if (i < 0) return 404 to problem(404, "not_found", "این گفتگو پیدا نشد.")
            val ts = turnsBy.getOrPut(ref) { mutableListOf() }
            val who = convs[i].str("persona") ?: "secretary"
            when (m.groupValues[2]) {
                "turns" -> {
                    val text = body?.str("text").orEmpty().trim()
                    if (Regex("AIza[0-9A-Za-z_-]{35}").containsMatchIn(text)) return 422 to problem(422, "validation_failed", "کلید را با دکمه‌ی کلید بدهید.")
                    val n = ts.size + 1
                    ts.add(turn(ref, n, "owner", body?.str("source") ?: "typed", text, off = 0, h = 9, m = n % 50))
                    val answer = answer(ref, n + 1, who, text)
                    ts.add(answer)
                    spent += 0.0123
                    convs[i] = convs[i].with("turns" to ts.size, "last_turn_at" to at(0, 9, 55))
                    DemoLive.after(2) { listOf(event("talk.turn", answer.str("id"), mapOf("conversation" to ref, "state" to "done")), event("voice.meter", null, (meter.getValue("month")() as JsonObject))) }
                    return 202 to jo("turn" to answer.with("state" to "streaming"), "events" to "/api/v1/talk/turns/${answer.str("id")}/events")
                }
                "invite" -> {
                    val id = "${body?.str("role")}@${body?.str("company")}"
                    val present = (convs[i]["present"] as JsonArray).map { (it as JsonPrimitive).content }.let { if (id in it) it else it + id }
                    ts.add(turn(ref, ts.size + 1, "secretary", "typed", "", show = "مدیرعامل تریدیار آمد.", off = 0, h = 9, m = 30))
                    convs[i] = convs[i].with("persona" to id, "present" to ja(present.map { JsonPrimitive(it) }), "turns" to ts.size)
                    return 200 to convs[i]
                }
                else -> {
                    val c = card("TC-${cardSeq++}", "", "minutes", "صورت‌جلسه‌ی گفتگو", "خلاصه و کارهای این گفتگو.", minutesPayload)
                    ts.add(turn(ref, ts.size + 1, who, "typed", "", show = "صورت‌جلسه آماده است.", say = "صورت‌جلسه آماده است.", cards = listOf(c), off = 0, h = 9, m = 40))
                    return 200 to c
                }
            }
        }
        Regex("^/talk/turns/([^/]+)/stop$").find(path)?.let { return if (method == "POST") 200 to jo("state" to "stopped") else null }
        Regex("^/talk/cards/([^/]+)/(run|dismiss)$").find(path)?.let { m ->
            if (method != "POST") return null
            val id = m.groupValues[1]
            var found: JsonObject? = null
            for ((cv, ts) in turnsBy) for (ti in ts.indices) {
                val cards = ts[ti]["cards"] as JsonArray
                val ci = cards.indexOfFirst { (it as JsonObject).str("id") == id }
                if (ci >= 0) {
                    val old = cards[ci] as JsonObject
                    val done = m.groupValues[2] == "run"
                    val made = if (done) listOf(if (old.str("kind") == "minutes") "F-000240" else if (old.str("kind") == "hire") "D-000091" else "F-000232") else emptyList()
                    val upd = old.with("state" to (if (done) "done" else "dismissed"), "made" to ja(made.map { JsonPrimitive(it) }))
                    ts[ti] = ts[ti].with("cards" to JsonArray(cards.toMutableList().also { it[ci] = upd }))
                    found = upd
                    if (cv.isNotBlank()) Unit
                }
            }
            val card = found ?: return 404 to problem(404, "not_found", "این کارت پیدا نشد.")
            return 200 to jo("made" to card["made"], "card" to card)
        }

        if (path == "/voice/engines" && method == "GET") return 200 to ja(engines)
        Regex("^/voice/engines/([^/]+)/voices$").find(path)?.let { m ->
            val e = engines.firstOrNull { it.str("key") == m.groupValues[1] } ?: return 404 to problem(404, "not_found", "این موتور پیدا نشد.")
            return 200 to e["voices"]!!
        }
        Regex("^/voice/engines/([^/]+)/(check|price)$").find(path)?.let { m ->
            val i = engines.indexOfFirst { it.str("key") == m.groupValues[1] }
            if (i < 0) return 404 to problem(404, "not_found", "این موتور پیدا نشد.")
            if (m.groupValues[2] == "check" && method == "POST") {
                setState(i, "checking", null)
                DemoLive.after(3) { listOf(settle(i)) }
                return 200 to engines[i]
            }
            if (m.groupValues[2] == "price" && method == "PUT") return 200 to engines[i]
            return null
        }
        if (path == "/voice/meter" && method == "GET") return 200 to (meter[query["period"]] ?: meter.getValue("month"))()
        Regex("^/voice/providers/([^/]+)/secret$").find(path)?.let { m ->
            return when (method) {
                "PUT" -> {
                    val secret = body?.str("secret").orEmpty()
                    if (secret.length < 8) return 422 to problem(422, "validation_failed", "کلید درست نیست.")
                    keyed = true
                    engines.indices.filter { engines[it].str("provider") == m.groupValues[1] }.forEach { i ->
                        setState(i, "checking", null)
                        DemoLive.after(3 + i) { listOf(settle(i)) }
                    }
                    202 to jo("state" to "checking")
                }
                "DELETE" -> { engines.indices.filter { engines[it].str("provider") == m.groupValues[1] }.forEach { setState(it, "missing", null) }; 204 to JsonNull }
                else -> null
            }
        }
        if (path == "/voice/sample" && method == "POST") {
            return 200 to jo("file_id" to "demo-sample-${body?.str("voice")}", "seconds" to 3.2, "usd" to (if (body?.str("engine") == "piper") "0" else "0.0009"), "engine" to body?.str("engine"))
        }
        if (path == "/owner/settings" && method == "PUT") {
            (body?.get("voice") as? JsonObject)?.let { v ->
                moneyCap = (v["month_cap_usd"] as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull()
                (v["warn_at"] as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull()?.let { warnAt = it }
            }
            return null
        }
        return null
    }

    private fun setState(i: Int, state: String, reason: String?) { engines[i] = engines[i].with("state" to state, "reason_fa" to reason) }

    /** After a key or a check, the engine settles and the stream says so (`voice.engine`). */
    private fun settle(i: Int): StreamEvent {
        val key = engines[i].str("key")
        setState(i, "ok", null)
        return event("voice.engine", key, jo("engine" to key, "state" to "ok", "reason_fa" to null))
    }

    private fun answer(cv: String, n: Int, who: String, said: String): JsonObject {
        val order = Regex("بساز|فرمان|بنویس|آماده کن").containsMatchIn(said)
        val minutes = Regex("صورت.?جلسه").containsMatchIn(said)
        val cards = mutableListOf<JsonObject>()
        if (order) cards += card("TC-${cardSeq++}", "", "order", "فرمان: ${said.take(40)}", "برای تریدیار؛ تا نزنی «فرمان بده» چیزی شروع نمیشود.", jo("title_fa" to said.take(60), "brief_fa" to said, "company" to "TY", "department" to "MEDIA"))
        if (minutes) cards += card("TC-${cardSeq++}", "", "minutes", "صورت‌جلسه", "خلاصه، تصمیم‌ها و کارها.", minutesPayload)
        val show = when {
            order -> "باشد؛ فرمان را آماده کردم و منتظر «فرمان بده» ات هستم."
            minutes -> "صورت‌جلسه آماده است؛ موعد و دپارتمان هر کار را میتوانی عوض کنی."
            else -> "شنیدم. در حالت نمایشی جواب واقعی ساخته نمیشود؛ روی سرور، جواب با داده‌ی واقعی و صدای خودم میآید."
        }
        return turn(cv, n, who, "typed", "", show = show, say = show.take(120), cards = cards, audio = 1, off = 0, h = 9, m = n % 50)
    }

    // ------------------------------------------------------------- helpers --
    private fun event(type: String, ref: String?, data: JsonObject) = StreamEvent("demo-$type-${ref.orEmpty()}", type, HqClock.now().toString(), null, ref, data)
    private fun event(type: String, ref: String?, data: Map<String, String>) = event(type, ref, jo(*data.map { it.key to it.value }.toTypedArray()))
    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
    private fun JsonObject.with(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(this + jo(*kv))
    private fun ja(xs: List<JsonElement>) = JsonArray(xs)
    private fun jo(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(kv.associate { (k, v) ->
        k to when (v) {
            null -> JsonNull; is JsonElement -> v; is String -> JsonPrimitive(v); is Number -> JsonPrimitive(v); is Boolean -> JsonPrimitive(v)
            else -> error("unsupported ${v::class}")
        }
    })
    private fun problem(status: Int, code: String, fa: String) = jo("code" to code, "message_fa" to fa, "status" to status, "title" to code, "type" to "about:blank")
}
