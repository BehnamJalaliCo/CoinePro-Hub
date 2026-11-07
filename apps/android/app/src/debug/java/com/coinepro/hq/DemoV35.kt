package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * Debug builds only: contract §34–§35 ⟨1.16, 1.17⟩, every order a session and the owner's office. Deterministic (from [HqClock]).
 *
 * - **Sessions:** F-0101 the owner's turn (a step order: the CEO of TradeYar asks; a media manager and GPT in the room; a plan of four),
 *   F-0102 ready for his OK (the advisor's quarterly money report), F-0103 stuck (no one to hire yet: the secretary holds it and offers
 *   the hire), F-0104 and F-0105 moving; F-0098 and F-0099 closed in the archive.
 * - **The talk of each session** (CV-0501…): the holder's hello first; a turn with `to` is answered by that participant, `all` by every
 *   one present and then the holder's sum-up; while a turn is open the owner's words are the order's reply.
 * - **The office:** the open sessions, the first pending cards of the cartable, the month's money, two suggestions on any subject, and
 *   the canvas: the hub, TradeYar, CoinePro FX (placed by the owner) and Pro-Chart, with two links on and one off.
 * - ⟨1.18⟩ §36 **files in a session:** F-0101's second turn of the owner came with the covers' title font, a sample cover and the reels'
 *   brief (its «فایل‌ها»); a turn with `file_ids` takes the owner's uploads ([uploads]), the holder says he has them, and they join the
 *   order's files, newest first.
 */
internal class V35Demo(private val store: MutableMap<String, Pair<Int, JsonElement>>, private val uploads: Map<String, JsonObject> = emptyMap()) {
    private val now = HqClock.now()
    private fun at(minAgo: Long): String = now.minus(minAgo, ChronoUnit.MINUTES).toString()

    private class S(
        val ref: String, val text: String, var badge: String, var reason: String, var pace: String,
        val holder: Triple<String, String, String?>, var participants: MutableList<JsonObject>, var tasks: MutableList<JsonObject>,
        var turn: JsonObject?, val brief: Triple<String, String, String>, val opened: Long, var last: Long,
        var closedAt: String? = null, var hidden: Boolean = false, val blockers: List<JsonObject> = emptyList(), val outputs: List<JsonObject> = emptyList(),
        var steps: MutableList<JsonObject> = mutableListOf(),
        /** ⟨1.18⟩ the owner's files in the session, newest first. */
        val files: MutableList<JsonObject> = mutableListOf(),
        /** ⟨1.22⟩ §40.1 what the session remembers; §40.3 the playbook it was opened from. */
        var memory: String? = null,
        var source: String? = null,
    ) {
        val cv: String get() = "CV-05" + ref.takeLast(2)
    }

    private fun person(key: String, kind: String, title: String, company: String?) = jo("key" to key, "kind" to kind, "title_fa" to title, "company" to company)
    private fun task(id: String, n: Int, title: String, state: String, by: String = "agent", who: String? = null) =
        jo("id" to id, "n" to n, "title_fa" to title, "state" to state, "by" to by, "who_fa" to who, "work_ref" to null)
    private fun step(min: Long, who: String, what: String) = jo("at" to at(min), "who_fa" to who, "what_fa" to what)

    // ⟨1.18⟩ §36 the files of F-0101: the covers' title font (its family read by the hub), a sample cover, the reels' brief.
    private fun file(id: String, name: String, mime: String, size: Long, kind: String, w: Int? = null, h: Int? = null, family: String? = null) = jo(
        "id" to id, "name" to name, "mime" to mime, "size" to size, "sha256" to "demo", "kind" to kind, "status" to "ready", "variants" to jo(),
        "width" to w, "height" to h, "meta" to family?.let { jo("family" to it) },
    )
    private val tyFiles = listOf(
        file("/demo/fonts/titr-cover.ttf", "titr-cover.ttf", "font/ttf", 186_420, "font", family = "Titr Cover"),
        file("/demo/ty-story-stoploss-poster.webp", "نمونه‌ی کاور.webp", "image/webp", 11_962, "image", 360, 640),
        file("/demo/docs/reels-brief.pdf", "بریف ریلزها.pdf", "application/pdf", 248_310, "document"),
    )

    private val sessions = mutableListOf(
        S(
            "F-0101", "برای تریدیار هفته‌ی آموزش طلا را راه بینداز؛ مرحله به مرحله با من جلو برو.", "your_turn",
            "مدیرعامل تریدیار میپرسد: اول ریلزها منتشر شود یا پست‌ها؟", "step",
            Triple("ceo@TY", "مدیرعامل تریدیار", "TY"),
            mutableListOf(
                person("ceo@TY", "holder", "مدیرعامل تریدیار", "TY"),
                person("media@TY", "person", "مدیر رسانه‌ی تریدیار", "TY"),
                person("player:gpt", "player", "جی‌پی‌تی", null),
            ),
            mutableListOf(
                task("t1", 1, "برنامه‌ی هفته با سه ریلز، دو پست و یک مقاله", "done", who = "مدیرعامل تریدیار"),
                task("t2", 2, "ساخت سه ریلز آموزشی طلا", "done", who = "مدیر رسانه"),
                task("t3", 3, "نوشتن دو پست کانال", "doing", who = "مدیر رسانه"),
                task("t4", 4, "گزارش بازده تبلیغ در پایان هفته", "todo", by = "owner"),
            ),
            jo("question_fa" to "سه ریلز و دو پست آماده است؛ اول ریلزها منتشر شود یا پست‌ها؟", "at" to at(6), "by" to jo("code" to "TY-CEO", "kind" to "employee", "display_fa" to "مدیرعامل تریدیار"), "who_fa" to "مدیرعامل تریدیار"),
            Triple("برنامه نوشته شد و سه ریلز ساخته شد.", "دو پست کانال در حال نوشتن است.", "بگو اول ریلزها منتشر شود یا پست‌ها."),
            opened = 190, last = 6,
            steps = mutableListOf(
                step(188, "مدیرعامل تریدیار", "فرمان را گرفت و برنامه‌ی هفته را نوشت."),
                *tyFiles.map { step(120, "مدیر کل", "فایل از مدیر کل: ${it.str("name")}") }.toTypedArray(),
                step(100, "سامانه", "به مدیر رسانه‌ی تریدیار سپرده شد"),
                step(95, "مدیر رسانه", "سه ریلز آموزشی ساخته شد."), step(6, "مدیرعامل تریدیار", "سؤال از شما: اول ریلزها یا پست‌ها؟"),
            ),
            files = tyFiles.toMutableList(),
            memory = TY_MEMORY,
        ),
        S(
            "F-0102", "یک گزارش مالی سه‌ماهه برای همه‌ی شرکت‌ها آماده کن.", "ready", "گزارش آماده است و منتظر تأیید توست.", "auto",
            Triple("advisor", "مشاور کل", null),
            mutableListOf(person("advisor", "holder", "مشاور کل", null)),
            mutableListOf(task("u1", 1, "خواندن درآمد و خرج سه ماه هر شرکت", "done"), task("u2", 2, "مقایسه با سه ماه قبل", "done"), task("u3", 3, "نوشتن گزارش به زبان ساده", "done")),
            null, Triple("گزارش سه‌ماهه‌ی همه‌ی شرکت‌ها نوشته شد.", "منتظر تأیید توست.", "اگر راضی هستی، تأیید کن و ببند."),
            opened = 1500, last = 40,
            outputs = listOf(jo("ref" to "O-000201", "title_fa" to "گزارش مالی سه‌ماهه‌ی هلدینگ", "kind" to "report")),
            steps = mutableListOf(step(1495, "مشاور کل", "فرمان را گرفت و برنامه را نوشت."), step(45, "سامانه", "خروجی رسید: گزارش مالی سه‌ماهه‌ی هلدینگ")),
        ),
        S(
            "F-0103", "برای کوینه‌پرو FX یک پشتیبان تلگرامی بگذار که شب‌ها هم جواب بدهد.", "stuck", "کسی برای این کار نیست؛ اول استخدام لازم است.", "auto",
            Triple("secretary", "منشی هلدینگ", null),
            mutableListOf(person("secretary", "holder", "منشی هلدینگ", null)),
            mutableListOf(task("v1", 1, "استخدام پشتیبان تلگرام", "todo")),
            null, Triple("منشی فرمان را گرفت.", "منتظر استخدام است.", "استخدام را باز کن."),
            opened = 300, last = 280,
            blockers = listOf(jo("kind" to "hiring_closed", "title_fa" to "استخدام در کوینه‌پرو FX بسته است", "detail_fa" to "برای پشتیبان تلگرام باید استخدام باز شود؛ با یک ضربه بازش کن.", "since" to at(280),
                "fix" to jo("action" to "hiring.open", "label_fa" to "استخدام را باز کن", "target" to "FX"))),
        ),
        S(
            "F-0104", "سئوی سایت پرو-چارت را بهتر کن تا در جستجوی «چارت طلا» بالا بیاید.", "moving", "مدیرعامل پرو-چارت روی بررسی رقبا کار میکند.", "auto",
            Triple("ceo@PC", "مدیرعامل پرو-چارت", "PC"),
            mutableListOf(person("ceo@PC", "holder", "مدیرعامل پرو-چارت", "PC")),
            mutableListOf(task("w1", 1, "بررسی سه رقیب اول", "doing"), task("w2", 2, "فهرست صفحه‌هایی که باید بهتر شوند", "todo")),
            null, Triple("فرمان گرفته شد و برنامه نوشته شد.", "بررسی رقبا در جریان است.", "فعلاً چیزی لازم نیست."),
            opened = 720, last = 25,
            memory = PC_MEMORY,
        ),
        S(
            "F-0105", "برنامه‌ی سفر کاری استانبول برای هفته‌ی بعد.", "moving", "دستیار شخصی هتل‌ها را مقایسه میکند.", "auto",
            Triple("assistant", "دستیار شخصی", null),
            mutableListOf(person("assistant", "holder", "دستیار شخصی", null)),
            mutableListOf(), null, Triple("سه هتل پیدا شد.", "پرواز مقایسه میشود.", "فعلاً چیزی لازم نیست."),
            opened = 2000, last = 120,
        ),
        S(
            "F-0099", "یک لوگوی تازه برای هلدینگ.", "closed", "تأیید و بسته شد.", "auto",
            Triple("ceo@HQ", "مدیرعامل هلدینگ", "HQ"), mutableListOf(person("ceo@HQ", "holder", "مدیرعامل هلدینگ", "HQ")), mutableListOf(),
            null, Triple("لوگو با مُهر تو ثبت شد.", "—", "—"), opened = 9000, last = 7000, closedAt = at(7000),
        ),
        S(
            "F-0098", "کمپین نوروز برای همه‌ی شرکت‌ها.", "closed", "تأیید و بسته شد؛ خط تولید آن هنوز کار میکند.", "auto",
            Triple("ceo@TY", "مدیرعامل تریدیار", "TY"), mutableListOf(person("ceo@TY", "holder", "مدیرعامل تریدیار", "TY")), mutableListOf(),
            null, Triple("کمپین اجرا شد.", "—", "—"), opened = 20000, last = 15000, closedAt = at(15000),
        ),
    )

    // ------------------------------------------------------------- the talk --
    // ⟨0.17.0⟩ [source] `system`: a step the hub wrote into the talk by itself (a progress line, «… آمد.»), drawn as one quiet line.
    private fun turn(cv: String, n: Int, by: String, text: String, min: Long, cards: List<JsonObject> = emptyList(), files: List<JsonObject> = emptyList(), source: String = "typed") = jo(
        "id" to "T-${cv.removePrefix("CV-")}-$n", "conversation" to cv, "n" to n, "by" to by, "source" to source,
        "text" to (if (by == "owner") text else ""), "show_md" to (if (by == "owner") null else text), "say_fa" to null,
        "cards" to JsonArray(cards), "audio" to JsonArray(emptyList()), "state" to "done", "at" to at(min), "files" to JsonArray(files),
    )

    private val hireCard = jo(
        "id" to "TC-501", "turn" to "T-0503-1", "kind" to "hire", "title_fa" to "استخدام: پشتیبان تلگرام برای کوینه‌پرو FX", "body_fa" to "یک پشتیبان که شب‌ها هم جواب بدهد؛ حقوق در سقف پاکت ماه.",
        "payload" to jo("title_fa" to "پشتیبان تلگرام", "company" to "FX"), "state" to "offered", "made" to JsonArray(emptyList()), "reason_fa" to null,
    )
    private val lineCard = jo(
        "id" to "TC-502", "turn" to "T-0501-4", "kind" to "delegate", "title_fa" to "بسپار به مدیر رسانه: دو پست کانال", "body_fa" to "دو پست کانال درباره‌ی پیوت طلا، پیش از انتشار برای تو.",
        "payload" to jo("text_fa" to "دو پست کانال درباره‌ی پیوت طلا بنویس", "company" to "TY"), "state" to "done", "made" to JsonArray(listOf(JsonPrimitive("W-000310"))), "reason_fa" to null,
    )

    private val turnsBy: MutableMap<String, MutableList<JsonObject>> = mutableMapOf(
        "CV-0501" to mutableListOf(
            turn("CV-0501", 1, "ceo@TY", "سلام. فرمان هفته‌ی آموزش طلا را گرفتم. **برنامه:** سه ریلز، دو پست و یک مقاله. چون گفتی مرحله به مرحله، هر قدم را با تو جلو میبرم.", 188),
            turn("CV-0501", 2, "media@TY", "مدیر رسانه‌ی تریدیار آمد.", 150, source = "system"),
            turn("CV-0501", 3, "owner", "خوب است. ریلزها را بساز و نظر جی‌پی‌تی را هم درباره‌ی متن‌ها بپرس. تیتر کاورها با این فونت باشد؛ نمونه‌ی کاور و بریف هم پیوست است.", 120, files = tyFiles),
            turn("CV-0501", 4, "player:gpt", "متن ریلزها روشن است؛ پیشنهاد میکنم در ریلز دوم یک مثال عددی از پیوت هفته‌ی قبل بیاید.", 110, listOf(lineCard)),
            turn("CV-0501", 5, "media@TY", "سه ریلز آموزشی ساخته شد و تیتر کاورها با فونت «Titr Cover» نوشته شد.", 95, source = "system"),
            turn("CV-0501", 6, "ceo@TY", "سه ریلز آماده شد و تیتر کاورها با فونتی که دادی نوشته شد؛ دو پست را به مدیر رسانه سپردم. **سؤال:** اول ریلزها منتشر شود یا پست‌ها؟", 6),
        ),
        "CV-0502" to mutableListOf(
            turn("CV-0502", 1, "advisor", "سلام. گزارش مالی سه‌ماهه را مینویسم؛ عددها از دفتر هر شرکت میآید.", 1490),
            turn("CV-0502", 2, "advisor", "گزارش آماده است: درآمد همه‌ی شرکت‌ها ۱۲٪ بالاتر از سه ماه قبل، خرج مدل‌ها ۸٪ پایین‌تر. فایل در «نتیجه» است.", 40),
        ),
        "CV-0503" to mutableListOf(
            turn("CV-0503", 1, "secretary", "سلام. در کوینه‌پرو FX کسی برای پشتیبانی تلگرام نیست؛ اول باید یک نفر استخدام شود. این کارت را بزن تا استخدام شروع شود.", 290, listOf(hireCard)),
        ),
        "CV-0504" to mutableListOf(turn("CV-0504", 1, "ceo@PC", "سلام. اول سه رقیب اول «چارت طلا» را بررسی میکنم و بعد فهرست صفحه‌ها را میفرستم.", 700)),
        "CV-0505" to mutableListOf(turn("CV-0505", 1, "assistant", "سلام. سه هتل نزدیک مترو پیدا کردم؛ حالا پرواز را مقایسه میکنم.", 1990)),
    )

    // ------------------------------------------------------------- the canvas --
    private val nodes = mutableListOf(
        jo("code" to "HQ", "name_fa" to "هلدینگ کوینه‌پرو", "kind" to "holding", "x" to null, "y" to null, "line_fa" to "ستاد همه‌ی شرکت‌ها", "open_sessions" to 2),
        jo("code" to "TY", "name_fa" to "تریدیار", "kind" to "company", "x" to null, "y" to null, "line_fa" to "هفته‌ی آموزش طلا در جریان است", "open_sessions" to 1),
        jo("code" to "FX", "name_fa" to "کوینه‌پرو FX", "kind" to "company", "x" to 0.2, "y" to 0.7, "line_fa" to "منتظر استخدام پشتیبان", "open_sessions" to 1),
        jo("code" to "PC", "name_fa" to "پرو-چارت", "kind" to "company", "x" to null, "y" to null, "line_fa" to "سئو در جریان است", "open_sessions" to 1),
    )
    private val links = mutableListOf(
        jo("id" to "LK-1", "from" to "TY", "to" to "FX", "kind" to "publishes", "purpose_fa" to "ریلزهای تریدیار در کانال کوینه‌پرو FX هم منتشر میشود", "state" to "on", "open_works" to 2, "updated_at" to at(300)),
        jo("id" to "LK-2", "from" to "PC", "to" to "TY", "kind" to "feeds", "purpose_fa" to "داده‌ی چارت پرو-چارت به سیگنال‌های تریدیار میرسد", "state" to "on", "open_works" to 1, "updated_at" to at(900)),
        jo("id" to "LK-3", "from" to "FX", "to" to "PC", "kind" to "sells", "purpose_fa" to "اشتراک پرو-چارت در کوینه‌پرو FX فروخته میشود", "state" to "off", "open_works" to 0, "updated_at" to at(5000)),
    )
    private var linkSeq = 4

    // -------------------------------------------------------------- shapes --
    private fun card(s: S) = jo(
        "ref" to s.ref, "conversation_ref" to s.cv, "title_fa" to s.text.take(80),
        "holder" to jo("code" to s.holder.first, "title_fa" to s.holder.second, "company" to s.holder.third, "company_fa" to companyFa(s.holder.third)),
        "badge" to s.badge, "reason_fa" to s.reason, "brief" to brief(s), "pace" to s.pace, "participants" to JsonArray(s.participants),
        "tasks" to jo("done" to s.tasks.count { it.str("state") == "done" }, "total" to s.tasks.count { it.str("state") != "dropped" }),
        "opened_at" to at(s.opened), "last_at" to at(s.last), "closed_at" to s.closedAt, "hidden" to s.hidden, "source" to s.source,
    )

    private fun brief(s: S) = jo("done_fa" to s.brief.first, "now_fa" to s.brief.second, "need_fa" to s.brief.third)

    private fun report(s: S) = jo(
        "ref" to s.ref, "text_fa" to s.text, "at" to at(s.opened),
        "state" to when { s.closedAt != null -> "delivered"; s.turn != null -> "waiting"; s.blockers.isNotEmpty() -> "blocked"; else -> "in_progress" },
        "ack" to jo("at" to at(s.opened - 2), "by" to null, "plan_fa" to s.brief.second, "assigned" to JsonArray(emptyList()), "due_at" to null),
        "route" to jo("companies" to JsonArray(listOfNotNull(s.holder.third?.let { JsonPrimitive(it) })), "output_kind" to "other", "preview_fa" to "", "why_fa" to "", "kind" to "work"),
        "steps" to JsonArray(s.steps), "blockers" to JsonArray(s.blockers), "outputs" to JsonArray(s.outputs), "summary" to null, "updated_at" to at(s.last),
        "pace" to s.pace, "conversation_ref" to s.cv, "turn" to s.turn,
        "session" to jo("state" to (if (s.closedAt != null) "closed" else "open"), "badge" to s.badge, "reason_fa" to s.reason, "closed_at" to s.closedAt, "hidden" to s.hidden, "source" to s.source),
        "brief" to brief(s), "tasks" to JsonArray(s.tasks), "participants" to JsonArray(s.participants), "files" to JsonArray(s.files),
        "memory_md" to s.memory,
    )

    /** ⟨1.19⟩ the sessions erased for good. */
    private val erased = mutableSetOf<String>()

    private fun eraseCounts(s: S) = jo(
        "turns" to (turnsBy[s.cv]?.size ?: 0), "files" to s.files.size, "outputs" to s.outputs.size,
        "works" to maxOf(1, s.tasks.size), "notifications" to s.steps.size.coerceAtMost(3),
    )

    /** The holder's word on the owner's files: a font is named by its family. */
    private fun filesHeard(sent: List<JsonObject>): String {
        val family = sent.firstOrNull { it.str("kind") == "font" }?.let { (it["meta"] as? JsonObject)?.str("family") }
        val n = sent.size.toString().map { if (it in '0'..'9') '۰' + (it - '0') else it }.joinToString("")
        return if (family != null) "فونت «$family» را گرفتم؛ تیتر کاورها با همین نوشته میشود. فایل‌ها کنار این فرمان ماند و هر کار آن را میبیند."
        else "$n فایل را گرفتم و کنار این فرمان گذاشتم؛ هر کار این فرمان آن‌ها را میبیند."
    }

    private fun conv(s: S) = jo(
        "ref" to s.cv, "title_fa" to s.text.take(60), "persona" to s.holder.first, "present" to JsonArray(s.participants.map { JsonPrimitive(it.str("key")) }),
        "mode" to "work", "started_at" to at(s.opened), "last_turn_at" to at(s.last), "turns" to (turnsBy[s.cv]?.size ?: 0), "order_ref" to s.ref, "closed_at" to s.closedAt,
    )

    private fun companyFa(code: String?): String? = when (code) { "TY" -> "تریدیار"; "FX" -> "کوینه‌پرو FX"; "PC" -> "پرو-چارت"; "HQ" -> "هلدینگ"; else -> null }

    private fun canvas() = jo("nodes" to JsonArray(nodes), "links" to JsonArray(links))

    private fun open() = sessions.filter { it.closedAt == null && !it.hidden }

    // -------------------------------------------------------------- routes --
    @Synchronized
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        if (path == "/sessions" && method == "GET") {
            val list = when (query["state"]) {
                "closed" -> sessions.filter { it.closedAt != null && !it.hidden }
                "all" -> sessions
                else -> open()
            }
            return 200 to jo("items" to JsonArray(list.map(::card)), "next_cursor" to null)
        }
        if (path == "/office" && method == "GET") {
            val pending = ((store["/decisions?status=pending"]?.second as? JsonObject)?.get("items") as? JsonArray).orEmpty()
            return 200 to jo(
                "sessions" to JsonArray(open().map(::card)), "approvals" to JsonArray(pending.take(10)), "approvals_total" to pending.size,
                "money" to jo("revenue_month_usd" to "4820.00", "spend_month_usd" to "312.40", "budget_month_usd" to "600.00", "line_fa" to "درآمد این ماه 9٪ بالاتر از ماه قبل است و خرج مدل‌ها زیر نصف سقف ماه مانده."),
                "critical" to JsonArray(emptyList()),
                "suggestions" to JsonArray(listOf(
                    jo("id" to "sg-35-1", "kind" to "effective", "company" to "FX", "title_fa" to "پشتیبانی شبانه‌ی کوینه‌پرو FX را با یک نفر پاره‌وقت راه بینداز", "why_fa" to "۴۰٪ پیام‌های مشتری بعد از ساعت ۱۰ شب میرسد و تا صبح بی‌جواب میماند.", "impact_fa" to "پاسخ شبانه و مشتری راضی‌تر", "cost_fa" to "یک استخدام در سقف پاکت ماه", "source" to "advisor", "state" to "new", "created_at" to at(400)),
                    jo("id" to "sg-35-2", "kind" to "good", "company" to "HQ", "title_fa" to "یک جلسه‌ی ماهانه‌ی بازبینی قراردادهای اجاره", "why_fa" to "دو قرارداد ماه آینده تمدید میشود.", "impact_fa" to "هیچ تمدیدی جا نمیماند", "cost_fa" to "یک ساعت در ماه", "source" to "advisor", "state" to "new", "created_at" to at(800)),
                )),
                "canvas" to canvas(),
            )
        }
        if (path == "/links") return when (method) {
            "GET" -> 200 to canvas()
            "POST" -> {
                val l = jo("id" to "LK-${linkSeq++}", "from" to body?.str("from"), "to" to body?.str("to"), "kind" to (body?.str("kind") ?: "serves"), "purpose_fa" to body?.str("purpose_fa").orEmpty(), "state" to "on", "open_works" to 0, "updated_at" to now.toString())
                links.add(l)
                201 to l
            }
            else -> null
        }
        Regex("^/links/([^/]+)$").find(path)?.let { m ->
            if (method != "PATCH") return null
            val i = links.indexOfFirst { it.str("id") == m.groupValues[1] }
            if (i < 0) return 404 to problem(404, "not_found", "این پیوند پیدا نشد.")
            links[i] = JsonObject(links[i] + (body ?: JsonObject(emptyMap())).filterKeys { it in setOf("kind", "purpose_fa", "state") } + ("updated_at" to JsonPrimitive(now.toString())))
            return 200 to links[i]
        }
        Regex("^/canvas/nodes/([^/]+)$").find(path)?.let { m ->
            if (method != "PUT") return null
            val i = nodes.indexOfFirst { it.str("code") == m.groupValues[1] }
            if (i < 0) return 404 to problem(404, "not_found", "این شرکت روی بوم نیست.")
            nodes[i] = JsonObject(nodes[i] + mapOf("x" to (body?.get("x") ?: JsonNull), "y" to (body?.get("y") ?: JsonNull)))
            return 200 to nodes[i]
        }
        Regex("^/talk/conversations/(CV-05\\d\\d)(/turns)?$").find(path)?.let { m ->
            val s = sessions.firstOrNull { it.cv == m.groupValues[1] } ?: return 404 to problem(404, "not_found", "این گفتگو پیدا نشد.")
            val ts = turnsBy.getOrPut(s.cv) { mutableListOf() }
            if (m.groupValues[2].isEmpty()) return if (method == "GET") 200 to JsonObject(conv(s) + ("turns_page" to jo("items" to JsonArray(ts), "next_cursor" to null))) else null
            if (method != "POST") return null
            val text = body?.str("text").orEmpty().trim()
            // ⟨1.18⟩ §36.2 the owner's own uploads (at most 10); an id the demo never took is a 422, as on the hub.
            val ids = (body?.get("file_ids") as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
            if (ids.size > 10) return 422 to problem(422, "validation_failed", "در هر پیام حداکثر ۱۰ فایل میرود.")
            val sent = ids.map { id -> uploads[id] ?: return 422 to problem(422, "validation_failed", "این فایل پیدا نشد؛ دوباره بفرستش.") }
            ts.add(turn(s.cv, ts.size + 1, "owner", text, 0, files = sent))
            // §36.3 the files belong to the order: a step each, and the newest first among its files.
            for (f in sent) s.steps.add(step(0, "مدیر کل", "فایل از مدیر کل: ${f.str("name")}"))
            s.files.addAll(0, sent.reversed())
            val to = body?.str("to")
            val speakers = when (to) {
                null -> listOf(s.holder.first)
                "all" -> s.participants.map { it.str("key")!! }.filter { it != s.holder.first }.take(5) + s.holder.first
                else -> listOf(to)
            }
            var last: JsonObject? = null
            for (who in speakers) {
                val sum = to == "all" && who == s.holder.first
                val said = when {
                    sum -> "جمع‌بندی: همه موافق‌اند که اول ریلزها منتشر شود و پست‌ها فردا."
                    sent.isNotEmpty() -> filesHeard(sent)
                    else -> "شنیدم؛ در نسخه‌ی نمایشی جواب واقعی ساخته نمیشود."
                }
                last = turn(s.cv, ts.size + 1, who, said, 0)
                ts.add(last)
            }
            s.last = 0
            return 202 to jo("turn" to (last ?: ts.last()), "events" to null)
        }
        val m = Regex("^/orders/(F-0\\d{3})(/[a-z]+)?(/[^/]+)?$").find(path) ?: return null
        // ⟨1.19⟩ §37.1 an erased session answers 404 everywhere, as on the hub.
        if (m.groupValues[1] in erased) return 404 to problem(404, "not_found", "این جلسه پاک شده است.")
        val s = sessions.firstOrNull { it.ref == m.groupValues[1] } ?: return null
        val action = m.groupValues[2].removePrefix("/")
        val sub = m.groupValues[3].removePrefix("/").ifBlank { null }
        when {
            action == "report" && method == "GET" -> return 200 to report(s)
            action == "talk" && method == "POST" -> return 200 to jo("conversation_ref" to s.cv)
            action == "pace" && method == "POST" -> {
                val p = body?.str("pace")
                if (p != "step" && p != "auto") return 422 to problem(422, "validation_failed", "روش کار «با من» یا «خودکار» است.")
                s.pace = p
                return 200 to report(s)
            }
            action == "reply" && method == "POST" -> {
                if (s.closedAt != null) return 409 to problem(409, "order_ended", "این جلسه بسته است؛ اول بازش کن.")
                val text = body?.str("text").orEmpty()
                s.steps.add(step(0, "مدیر کل", text))
                val ts = turnsBy.getOrPut(s.cv) { mutableListOf() }
                ts.add(turn(s.cv, ts.size + 1, "owner", text, 0))
                ts.add(turn(s.cv, ts.size + 1, s.holder.first, "باشد؛ همین را انجام میدهم و قدم بعد را میگویم.", 0))
                s.turn = null; s.badge = "moving"; s.reason = "${s.holder.second} قدم بعد را برمیدارد."; s.last = 0
                return 200 to report(s)
            }
            action == "participants" && method == "POST" && sub == null -> {
                val kind = body?.str("kind") ?: "person"
                val key0 = body?.str("key").orEmpty()
                val key = if (kind == "player") "player:$key0" else key0
                if (s.participants.none { it.str("key") == key }) s.participants.add(person(key, kind, "", key.substringAfter('@', "").ifBlank { null }))
                return 200 to report(s)
            }
            action == "participants" && method == "DELETE" && sub != null -> {
                if (sub == s.holder.first) return 409 to problem(409, "holder", "مسئول جلسه بیرون نمیرود.")
                s.participants.removeAll { it.str("key") == sub }
                return 200 to report(s)
            }
            action == "tasks" && method == "POST" && sub == null -> {
                val t = task("o${s.tasks.size + 1}", (s.tasks.maxOfOrNull { (it["n"] as JsonPrimitive).content.toInt() } ?: 0) + 1, body?.str("title_fa").orEmpty(), "todo", by = "owner")
                s.tasks.add(t)
                return 201 to t
            }
            action == "tasks" && method == "PATCH" && sub != null -> {
                val i = s.tasks.indexOfFirst { it.str("id") == sub }
                if (i < 0) return 404 to problem(404, "not_found", "این کار پیدا نشد.")
                s.tasks[i] = JsonObject(s.tasks[i] + (body ?: JsonObject(emptyMap())).filterKeys { it in setOf("title_fa", "state", "n") })
                return 200 to s.tasks[i]
            }
            action == "close" && method == "POST" -> {
                s.closedAt = now.toString(); s.badge = "closed"; s.reason = if (body?.str("verdict") == "cancel") "لغو و بایگانی شد." else "تأیید و بسته شد."; s.turn = null
                return 200 to report(s)
            }
            action == "reopen" && method == "POST" -> { s.closedAt = null; s.badge = "moving"; s.reason = "دوباره باز شد؛ ${s.holder.second} خبر دارد."; return 200 to report(s) }
            // ⟨1.19⟩ §37.1 what erasing takes and what stays (nothing changes), then the erase itself.
            action == "erase" && sub == "preview" && method == "GET" -> return 200 to jo(
                "ref" to s.ref, "kind" to "session", "title_fa" to s.text.take(80), "counts" to eraseCounts(s),
                "keeps_fa" to JsonArray(listOf(
                    JsonPrimitive("خط تولید یا کارگروهی که این جلسه راه انداخت میماند؛ آن را در صفحه‌ی خودش پاک کن."),
                    JsonPrimitive("یک خط در دفتر حسابرسی، بی متن فرمان."),
                    JsonPrimitive("عددهای توکن و پول، که خزانه هنوز باید جمعشان را داشته باشد."),
                )),
            )
            action == "erase" && sub == null && method == "POST" -> {
                val counts = eraseCounts(s)
                sessions.remove(s); turnsBy.remove(s.cv); erased += s.ref
                return 200 to jo("ref" to s.ref, "erased" to counts)
            }
            action == "hide" && method == "POST" -> { s.hidden = true; return 200 to report(s) }
            action == "unhide" && method == "POST" -> { s.hidden = false; return 200 to report(s) }
        }
        return null
    }

    // ------------------------------------------------- ⟨1.22⟩ §40 for [V40Demo] --
    /** What the playbooks' demo reads of a session: its words, company, holder and talk. */
    data class Look(val ref: String, val text: String, val company: String?, val holder: String, val holderFa: String, val cv: String, val participants: List<JsonObject>)

    @Synchronized
    fun look(order: String): Look? = sessions.firstOrNull { it.ref == order && it.ref !in erased }?.let {
        Look(it.ref, it.text, it.holder.third, it.holder.first, it.holder.second, it.cv, it.participants.toList())
    }

    /** Turns of a session's talk ([by], words, minutes ago, cards), after the ones it has; the holder speaks when [by] is null. */
    @Synchronized
    fun append(order: String, turns: List<Triple<String?, String, Pair<Long, List<JsonObject>>>>, stepFa: String? = null) {
        val s = sessions.firstOrNull { it.ref == order } ?: return
        val ts = turnsBy.getOrPut(s.cv) { mutableListOf() }
        for ((by, text, rest) in turns) ts.add(turn(s.cv, ts.size + 1, by ?: s.holder.first, text, rest.first, rest.second))
        if (stepFa != null) { s.steps.add(step(0, s.holder.second, stepFa)); s.last = 0 }
    }

    /** A card in any session's talk, by its id. */
    @Synchronized
    fun card(id: String): JsonObject? = turnsBy.values.asSequence().flatten().flatMap { ((it["cards"] as? JsonArray).orEmpty()).asSequence() }
        .mapNotNull { it as? JsonObject }.firstOrNull { it.str("id") == id }

    /** The card [id] replaced by [upd] wherever it is. */
    @Synchronized
    fun setCard(id: String, upd: JsonObject) {
        for (ts in turnsBy.values) for (i in ts.indices) {
            val cards = (ts[i]["cards"] as? JsonArray) ?: continue
            val at = cards.indexOfFirst { (it as? JsonObject)?.str("id") == id }
            if (at >= 0) ts[i] = JsonObject(ts[i] + ("cards" to JsonArray(cards.toMutableList().also { it[at] = upd })))
        }
    }

    /**
     * §40.3 a new session for [company] from the playbook [pb]: held by its CEO, the owner's first word the playbook (as the hub writes it),
     * the holder's hello, its source the playbook. → its ref and its talk.
     */
    @Synchronized
    fun openFrom(pb: String, title: String, company: String, companyFa: String, text: String): Pair<String, String> {
        val n = (sessions.mapNotNull { it.ref.removePrefix("F-").toIntOrNull() }.maxOrNull() ?: 105).coerceAtLeast(105) + 1
        val ref = "F-0" + n.toString().padStart(3, '0')
        val holder = "ceo@$company"
        val holderFa = "مدیرعامل $companyFa"
        val s = S(
            ref, text.lineSequence().first().trim(), "moving", "$holderFa کارگروه «$title» را برای شرکتش جور میکند.", "auto",
            Triple(holder, holderFa, company), mutableListOf(person(holder, "holder", holderFa, company)), mutableListOf(),
            null, Triple("کارگروه «$title» رسید.", "$holderFa جایگاه‌ها را با آدم‌های شرکت جور میکند.", "فعلاً چیزی لازم نیست."),
            opened = 0, last = 0, steps = mutableListOf(step(0, "مدیر کل", "این جلسه از کارگروه «$title» باز شد")),
            memory = "- این جلسه از کارگروه $pb «$title» باز شد", source = pb,
        )
        sessions.add(0, s)
        turnsBy[s.cv] = mutableListOf(
            turn(s.cv, 1, "owner", text, 0),
            turn(s.cv, 2, holder, "سلام. کارگروه «$title» را گرفتم؛ جایگاه‌ها را با آدم‌های $companyFa جور میکنم و پیش‌نویسش را همین‌جا برای مُهر تو میگذارم.", 0),
        )
        return ref to s.cv
    }

    // ------------------------------------------------------------- helpers --
    companion object {
        /** ⟨1.22⟩ §40.1 what F-0101 remembers, as the hub's small model writes it (its headings; a ref kept, the app hides it). */
        const val TY_MEMORY = "## تصمیم‌ها\n" +
            "- هفته‌ی آموزش طلا: سه ریلز، دو پست کانال و یک مقاله.\n" +
            "- روش کار «با من»: هر قدم پیش از قدم بعد به تأیید مدیر کل میرسد.\n" +
            "- تیتر کاورها با فونت «Titr Cover» که مدیر کل داد.\n\n" +
            "## چه کسی چه میکند\n" +
            "- مدیرعامل تریدیار: مسئول جلسه؛ برنامه و زمان انتشار.\n" +
            "- مدیر رسانه‌ی تریدیار: سه ریلز (ساخته شد) و دو پست کانال (W-000310).\n" +
            "- جی‌پی‌تی: متن ریلزها را پیش از انتشار میخواند؛ در ریلز دوم یک مثال عددی از پیوت هفته‌ی قبل.\n\n" +
            "## ابزارها و کمک‌ها\n" +
            "- موضوع هر ریلز را مدیر رسانه با ChatGPT پیدا میکند.\n" +
            "- کاورها با Gemini در AI Studio ساخته میشوند.\n\n" +
            "## نکته‌های باز\n" +
            "- اول ریلزها منتشر شود یا پست‌ها؟ منتظر جواب مدیر کل.\n" +
            "- گزارش بازده تبلیغ در پایان هفته، با عدد."

        /** What F-0104 remembers; its playbook (PB-0002) is drafted from it. */
        const val PC_MEMORY = "## تصمیم‌ها\n" +
            "- هر هفته سه رقیب اول «چارت طلا» بررسی میشوند.\n" +
            "- هفته‌ای دو مقاله‌ی آموزشی؛ هر کدام با منبع.\n\n" +
            "## چه کسی چه میکند\n" +
            "- مدیرعامل پرو-چارت: مسئول جلسه و تأیید پیش از انتشار.\n" +
            "- کارشناس سئو: بررسی رقبا و فهرست صفحه‌هایی که باید بهتر شوند.\n" +
            "- نویسنده‌ی مقاله: دو مقاله در هفته.\n\n" +
            "## ابزارها و کمک‌ها\n" +
            "- موضوع مقاله‌ها را نویسنده با ChatGPT پیدا میکند و DeepSeek متن را میسنجد.\n\n" +
            "## نکته‌های باز\n" +
            "- کارگروه PB-0002 «سئوی هفتگی سایت» منتظر مُهر مدیر کل است."

        /** A font's family as the demo reads it: its file name without the extension, words capitalised («titr-cover.ttf» → «Titr Cover»). */
        fun familyOf(name: String): String =
            name.substringBeforeLast('.').split('-', '_', ' ').filter { it.isNotBlank() }.joinToString(" ") { w -> w.replaceFirstChar { it.uppercase() } }.ifBlank { name }
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
