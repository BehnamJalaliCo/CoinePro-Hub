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
        /** ⟨0.19.0⟩ in the lists (the office, «جلسه‌ها»); the dense session the screenshots read is not, so the lists stay as they were. */
        val listed: Boolean = true,
        /** ⟨1.32⟩ §54 the holder does this session's work himself (a direct session). */
        val direct: Boolean = false,
        /** ⟨1.36⟩ §58.2 closed, it left its working group in the library. */
        var playbookKept: Boolean = false,
    ) {
        val cv: String get() = "CV-05" + ref.takeLast(2)
    }

    private fun person(key: String, kind: String, title: String, company: String?) = jo("key" to key, "kind" to kind, "title_fa" to title, "company" to company)
    private fun task(id: String, n: Int, title: String, state: String, by: String = "agent", who: String? = null, work: String? = null) =
        jo("id" to id, "n" to n, "title_fa" to title, "state" to state, "by" to by, "who_fa" to who, "work_ref" to work)
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
                step(95, "مدیر رسانه", "سه ریلز آموزشی ساخته شد."), step(6, "مدیرعامل تریدیار", "سؤال از تو: اول ریلزها یا پست‌ها؟"),
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
            null, Triple("کمپین اجرا شد.", "—", "—"), opened = 20000, last = 15000, closedAt = at(15000), playbookKept = true,
        ),
        // ⟨0.19.0⟩ The owner's real session, as dense as his (F-0011, 2026-11-08): nine steps of his own, the media director's long notes,
        // two hires approved, many of the hub's own lines (one with a ref in it), two results together, a short budget; two at work now.
        S(
            "F-0100", "برای پرو-چارت یک کارگروه ریلز راه بینداز؛ مرحله‌ها را در پیام نوشتم.", "moving", "مدیر رسانه ریلز آزمایشی را میسازد.", "auto",
            Triple("ceo@PC", "مدیرعامل پرو-چارت", "PC"),
            mutableListOf(
                person("ceo@PC", "holder", "مدیرعامل پرو-چارت", "PC"),
                person("media@PC", "person", "مدیر رسانه‌ی پرو-چارت", "PC"),
            ),
            REELS_STEPS.mapIndexed { i, t -> task("r${i + 1}", i + 1, t, if (i < 2) "done" else if (i == 2) "doing" else "todo", by = "owner") }.toMutableList(),
            null, Triple("موضوع‌ها پیدا شد و دو استخدام تأیید شد.", "ریلز آزمایشی ساخته میشود.", "فعلاً چیزی لازم نیست."),
            opened = 75, last = 4,
            blockers = listOf(jo("kind" to "budget", "title_fa" to "بودجه‌ی این کار کم است", "detail_fa" to "ریلز آزمایشی ۸۲٪ بودجه‌اش را خرج کرده؛ برای صداگذاری کم میآید.", "since" to at(30),
                "fix" to jo("action" to "budget.add", "label_fa" to "بودجه بده", "target" to null)),
                jo("kind" to "connection_missing", "title_fa" to "اینستاگرام پرو-چارت هنوز وصل نیست", "detail_fa" to "برای انتشار ساعت ۱۸ (مرحله‌ی هشتم) اتصال اینستاگرام لازم است.", "since" to at(20),
                    "fix" to jo("action" to "connection.guide", "label_fa" to "وصل کن", "target" to "instagram"))),
            outputs = listOf(
                jo("ref" to "O-000123", "title_fa" to "متن ریلز آزمایشی «سه اشتباه رایج در چارت طلا»", "kind" to "reel"),
                jo("ref" to "O-000124", "title_fa" to "کاور ریلز آزمایشی", "kind" to "other"),
            ),
            steps = mutableListOf(
                step(68, "سامانه", "به مدیر رسانه‌ی پرو-چارت سپرده شد"),
                step(61, "سامانه", "جواب آمد (O-000122-): نکته‌های مدیر رسانه درباره‌ی ریلزها"),
                step(48, "سامانه", "کار W-000412 «ریلز آزمایشی» شروع شد"),
                step(41, "سامانه", "خروجی رسید: متن ریلز آزمایشی «سه اشتباه رایج در چارت طلا»"),
                step(40, "سامانه", "خروجی رسید: کاور ریلز آزمایشی"),
                step(36, "سامانه", "بودجه‌ی ریلز آزمایشی به ۸۲٪ رسید"),
                step(31, "سامانه", "صداگذاری منتظر بودجه ماند (W-000413)"),
                step(22, "سامانه", "زیرنویس ریلز آزمایشی به تدوینگر سپرده شد"),
            ),
            listed = false,
        ),
        // ⟨1.33⟩ §54, §55.1 the redesigned session, in the states the lists above do not hold (none of them in the lists): a workshop
        // turn that builds a motion graphic against its hour, a direct session whose holder works himself, one ready for his OK with
        // a reel to publish, and a closed one that ends with what it made.
        S(
            "F-0090", "برای پرو-چارت یک موشن‌گرافی ۳۰ ثانیه‌ای درباره‌ی اندیکاتور ATR بساز.", "moving", "کارگاه موشن‌گرافی را میسازد.", "auto",
            Triple("media@PC", "مدیر رسانه‌ی پرو-چارت", "PC"),
            mutableListOf(person("media@PC", "holder", "مدیر رسانه‌ی پرو-چارت", "PC")),
            mutableListOf(
                task("m1", 1, "نوشتن سناریو", "done", who = "نویسنده"),
                task("m2", 2, "ساخت موشن‌گرافی در کارگاه", "doing", who = "سازنده‌ی موشن‌گرافی", work = "W-000390"),
                task("m3", 3, "بازبینی و تحویل", "todo"),
            ),
            null, Triple("سناریو نوشته شد.", "کارگاه موشن‌گرافی را میسازد.", "فعلاً چیزی لازم نیست."),
            opened = 90, last = 1,
            steps = mutableListOf(step(88, "منشی هلدینگ", "فرمان را به رسانه‌ی پرو-چارت سپرد."), step(70, "نویسنده", "سناریوی موشن‌گرافی را نوشت.")),
            listed = false,
        ),
        S(
            "F-0091", "برای تریدیار کپشن سه ریلز این هفته را بنویس.", "moving", "مدیر رسانه خودش کپشن‌ها را مینویسد.", "auto",
            Triple("media@TY", "مدیر رسانه‌ی تریدیار", "TY"),
            mutableListOf(person("media@TY", "holder", "مدیر رسانه‌ی تریدیار", "TY")),
            mutableListOf(task("d1", 1, "کپشن سه ریلز", "doing", who = "مدیر رسانه", work = "W-000391"), task("d2", 2, "هشتگ‌ها", "todo")),
            null, Triple("فرمان گرفته شد.", "مدیر رسانه کپشن‌ها را مینویسد.", "فعلاً چیزی لازم نیست."),
            opened = 30, last = 1,
            steps = mutableListOf(step(29, "منشی هلدینگ", "فرمان را به مدیر رسانه‌ی تریدیار سپرد.")),
            listed = false, direct = true,
        ),
        S(
            "F-0092", "برای تریدیار یک ریلز درباره‌ی جای درست حد ضرر بساز.", "ready", "ریلز آماده است و منتظر تأیید توست.", "auto",
            Triple("media@TY", "مدیر رسانه‌ی تریدیار", "TY"),
            mutableListOf(person("media@TY", "holder", "مدیر رسانه‌ی تریدیار", "TY")),
            mutableListOf(task("p1", 1, "نوشتن متن", "done", who = "نویسنده"), task("p2", 2, "ساخت ریلز", "done", who = "سازنده‌ی ریلز")),
            null, Triple("ریلز ۳۰ ثانیه‌ای با کاور ساخته شد.", "منتظر تأیید توست.", "اگر خوب است، تأیید کن تا منتشر شود."),
            opened = 210, last = 40,
            outputs = listOf(jo("ref" to "O-000967", "title_fa" to "ریلز: حد ضرر را کجا بگذاریم", "kind" to "reel")),
            steps = mutableListOf(
                step(208, "منشی هلدینگ", "فرمان را به رسانه‌ی تریدیار سپرد."), step(170, "نویسنده", "متن ریلز را نوشت."),
                step(41, "سامانه", "خروجی رسید: ریلز: حد ضرر را کجا بگذاریم"),
            ),
            listed = false,
        ),
        S(
            "F-0093", "برای تریدیار ریلز «سطوح کلیدی طلا» را بساز و منتشر کن.", "closed", "تأیید و بسته شد.", "auto",
            Triple("media@TY", "مدیر رسانه‌ی تریدیار", "TY"),
            mutableListOf(person("media@TY", "holder", "مدیر رسانه‌ی تریدیار", "TY")),
            mutableListOf(task("c1", 1, "نوشتن متن گوینده", "done", who = "نویسنده"), task("c2", 2, "ساخت ریلز و کاور", "done", who = "سازنده‌ی ریلز")),
            null, Triple("ریلز ساخته و منتشر شد.", "—", "—"),
            opened = 3_016, last = 2_905, closedAt = at(2_905),
            outputs = listOf(jo("ref" to "O-000968", "title_fa" to "ریلز: سطوح کلیدی طلا", "kind" to "reel")),
            steps = mutableListOf(step(3_014, "منشی هلدینگ", "فرمان را به رسانه‌ی تریدیار سپرد."), step(2_921, "سامانه", "خروجی رسید: ریلز: سطوح کلیدی طلا")),
            listed = false, playbookKept = true,
        ),
        // ⟨1.36⟩ §58.1 the owner's turn with a long question (the owner: «وقتی سوال میپرسه … نوشته هام دیده نمیشه»), its reel delivered
        // just before it: the card shows three lines and «بیشتر», folds to one while he writes, and «خروجی آخر» opens the reel.
        S(
            "F-0096", "برای تریدیار ریلز «حد ضرر را کجا بگذاریم» را بساز؛ قدم به قدم با من.", "your_turn", "مدیر رسانه‌ی تریدیار میپرسد: شروع ریلز با سؤال باشد یا با عدد؟", "step",
            Triple("media@TY", "مدیر رسانه‌ی تریدیار", "TY"),
            mutableListOf(person("media@TY", "holder", "مدیر رسانه‌ی تریدیار", "TY")),
            mutableListOf(task("l1", 1, "متن و صدای ریلز", "done", who = "نویسنده"), task("l2", 2, "نسخه‌ی اول ریلز", "done", who = "سازنده‌ی ریلز"), task("l3", 3, "کاور و کپشن", "doing"), task("l4", 4, "تأیید و انتشار", "todo")),
            jo("question_fa" to LONG_QUESTION_FA, "at" to at(3), "by" to jo("code" to "TY-MEDIA-02", "kind" to "employee", "display_fa" to "مدیر رسانه‌ی تریدیار"), "who_fa" to "مدیر رسانه‌ی تریدیار"),
            Triple("نسخه‌ی اول ریلز ساخته شد.", "کاور و کپشن منتظر جواب توست.", "بگو شروع ریلز با سؤال باشد یا با عدد."),
            opened = 150, last = 3,
            outputs = listOf(jo("ref" to "O-000967", "title_fa" to "ریلز: حد ضرر را کجا بگذاریم", "kind" to "reel")),
            steps = mutableListOf(
                step(148, "منشی هلدینگ", "فرمان را به رسانه‌ی تریدیار سپرد."), step(110, "نویسنده", "متن ریلز را نوشت."),
                step(41, "سامانه", "خروجی رسید: ریلز: حد ضرر را کجا بگذاریم"), step(3, "مدیر رسانه‌ی تریدیار", "سؤال از تو: شروع ریلز با سؤال باشد یا با عدد؟"),
            ),
            listed = false,
        ),
        // ⟨2026-11-11⟩ The owner's 12-hour stall (Pro-Chart's daily reels, «با من», task 3 of 18), in its two states: F-0094 while the
        // draft waits in ChatGPT's queue (an outside call at work, in the «الان» bar), F-0095 the next morning, when nothing ran after
        // «… از ChatGPT خواسته شد و در صف است» and the hub still said «آرام» (the page says «ایستاده» with «ادامه بده»).
        S(
            "F-0094", "هر روز یک ریلز آموزشی برای پرو-چارت بساز؛ قدم به قدم با من جلو برو.", "moving", "مدیرعامل پرو-چارت: $DRAFT_ASKED_FA", "step",
            Triple("ceo@PC", "مدیرعامل پرو-چارت", "PC"),
            mutableListOf(person("ceo@PC", "holder", "مدیرعامل پرو-چارت", "PC")),
            reelsPlan("q"), null,
            Triple("سناریست استخدام شد و گوینده یک‌بار برای همیشه تنظیم شد.", "پیش‌نویس متن ریلز اول در صف ChatGPT است.", "فعلاً چیزی لازم نیست."),
            opened = 40, last = 4,
            steps = mutableListOf(step(38, "منشی هلدینگ", "فرمان را به مدیرعامل پرو-چارت سپرد."), step(4, "مدیرعامل پرو-چارت", DRAFT_ASKED_FA)),
            listed = false,
        ),
        S(
            "F-0095", "به هرچه میگویم دقت کن و هر روز یک ریلز برای پرو-چارت بساز؛ قدم به قدم با من.", "moving", "مدیرعامل پرو-چارت: $STALLED_FA", "step",
            Triple("ceo@PC", "مدیرعامل پرو-چارت", "PC"),
            mutableListOf(person("ceo@PC", "holder", "مدیرعامل پرو-چارت", "PC")),
            reelsPlan("s"), null,
            Triple("سناریست استخدام شد و گوینده یک‌بار برای همیشه تنظیم شد.", "پیش‌نویس متن ریلز اول از ChatGPT خواسته شد.", "فعلاً چیزی لازم نیست."),
            opened = 830, last = 812,
            steps = mutableListOf(
                step(828, "منشی هلدینگ", "فرمان را به مدیرعامل پرو-چارت سپرد."),
                step(815, "مدیرعامل پرو-چارت", "سؤال از تو: گام ۱ انجام شد؛ گام ۲ را شروع کنم؟"),
                step(813, "مدیر کل", "خودت تصمیم بگیر و ادامه بده"),
                step(812, "مدیرعامل پرو-چارت", STALLED_FA),
            ),
            listed = false,
        ),
    )

    /** The eighteen tasks of the daily reels' plan, two done and the third in hand. */
    private fun reelsPlan(id: String) = REELS_PLAN.mapIndexed { i, t -> task("$id${i + 1}", i + 1, t, when { i < 2 -> "done"; i == 2 -> "doing"; else -> "todo" }, who = "مدیرعامل پرو-چارت") }.toMutableList()

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
        "CV-0590" to mutableListOf(
            turn("CV-0590", 1, "owner", "برای پرو-چارت یک موشن‌گرافی ۳۰ ثانیه‌ای درباره‌ی اندیکاتور ATR بساز.", 90),
            turn("CV-0590", 2, "media@PC", "سناریو آماده شد و ساخت را به کارگاه سپردم. تا یک ساعت دیگر فایل همین‌جا میرسد.", 68),
        ),
        "CV-0591" to mutableListOf(
            turn("CV-0591", 1, "owner", "برای تریدیار کپشن سه ریلز این هفته را بنویس.", 30),
            turn("CV-0591", 2, "media@TY", "خودم مینویسم؛ تا چند دقیقه‌ی دیگر هر سه کپشن همین‌جاست.", 28),
        ),
        "CV-0592" to mutableListOf(
            turn("CV-0592", 1, "owner", "برای تریدیار یک ریلز درباره‌ی جای درست حد ضرر بساز.", 210),
            turn("CV-0592", 2, "media@TY", "ریلز ساخته شد و با کاورش پایین همین صفحه است. اگر خوب است، تأیید کن تا منتشر شود.", 40),
        ),
        "CV-0593" to mutableListOf(
            turn("CV-0593", 1, "owner", "برای تریدیار ریلز «سطوح کلیدی طلا» را بساز و منتشر کن.", 3_016),
            turn("CV-0593", 2, "media@TY", "ریلز ساخته شد؛ با کاور و متن گوینده در همین جلسه است و منتشر شد.", 2_920),
            turn("CV-0593", 3, "owner", "خوب است؛ ببند.", 2_910),
        ),
        "CV-0594" to mutableListOf(
            turn("CV-0594", 1, "owner", "هر روز یک ریلز آموزشی برای پرو-چارت بساز؛ قدم به قدم با من جلو برو.", 40),
            turn("CV-0594", 2, "ceo@PC", "سلام. سناریست را استخدام میکنم، گوینده را یک‌بار تنظیم میکنم و هر قدم را با تو جلو میبرم.", 38),
            turn("CV-0594", 3, "owner", "خودت تصمیم بگیر و ادامه بده", 6),
            turn("CV-0594", 4, "ceo@PC", DRAFT_ASKED_FA, 4, source = "system"),
        ),
        "CV-0595" to mutableListOf(
            turn("CV-0595", 1, "owner", "به هرچه میگویم دقت کن و هر روز یک ریلز برای پرو-چارت بساز؛ قدم به قدم با من.", 830),
            turn("CV-0595", 2, "ceo@PC", "روش موضوع بدون تکرار: سناریست هر روز با ChatGPT موضوع پیشنهاد میدهد و با دفتر موضوعات ثبت میکند؛ موضوع تکراری خودکار رد میشود.", 818, source = "system"),
            turn("CV-0595", 3, "ceo@PC", "**سؤال از تو** · گام ۱ انجام شد (استخدام سناریست و روش موضوع روزانه). تأیید یا اصلاح؟ اگر تأیید است، گام ۲ (متن گوینده و تنظیم یک‌بارِ صدا) را شروع کنم؟", 815, source = "system"),
            turn("CV-0595", 4, "ceo@PC", "سناریست ریلز پرو-چارت استخدام شد و به همین جلسه آمد.", 815, source = "system"),
            turn("CV-0595", 5, "owner", "خودت تصمیم بگیر و ادامه بده", 813),
            turn("CV-0595", 6, "ceo@PC", STALLED_FA, 812, source = "system"),
        ),
        "CV-0500" to mutableListOf(
            turn("CV-0500", 1, "owner", REELS_STEPS.mapIndexed { i, t -> "${i + 1} - $t" }.joinToString("\n", prefix = "این کارگروه ریلز پرو-چارت است؛ مرحله به مرحله:\n"), 70),
            turn("CV-0500", 2, "media@PC", "مدیر رسانه‌ی پرو-چارت آمد.", 69, source = "system"),
            turn("CV-0500", 3, "media@PC", REELS_NOTES, 62),
            turn("CV-0500", 4, "ceo@PC", "کارت استخدام تأیید شد: تدوینگر ریلز", 56, source = "system"),
            turn("CV-0500", 5, "ceo@PC", "کارت استخدام تأیید شد: صداپیشه", 55, source = "system"),
            turn("CV-0500", 6, "ceo@PC", "دو استخدام تأیید شد؛ مدیر رسانه ریلز آزمایشی را میسازد و نسخه‌ی اول را همین‌جا میبینی. مرحله‌ی سوم در کار است.", 50),
        ),
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
        *(if (s.playbookKept) arrayOf("playbook_kept" to KEPT_REF, "playbook_kept_fa" to KEPT_FA) else emptyArray()),
    )

    private fun brief(s: S) = jo("done_fa" to s.brief.first, "now_fa" to s.brief.second, "need_fa" to s.brief.third)

    /** ⟨1.31⟩ What the rest of the demo adds to a session's report: its standing routines (§50) and its publishes (§44.5, §51). */
    @Volatile var extras: ((String) -> Map<String, JsonElement>)? = null

    private fun report(s: S) = JsonObject(base(s) + extras?.invoke(s.ref).orEmpty())

    private fun base(s: S) = jo(
        "ref" to s.ref, "text_fa" to s.text, "at" to at(s.opened),
        "state" to when { s.closedAt != null -> "delivered"; s.turn != null -> "waiting"; s.blockers.isNotEmpty() -> "blocked"; else -> "in_progress" },
        "ack" to jo("at" to at(s.opened - 2), "by" to null, "plan_fa" to s.brief.second, "assigned" to JsonArray(emptyList()), "due_at" to null),
        "route" to jo("companies" to JsonArray(listOfNotNull(s.holder.third?.let { JsonPrimitive(it) })), "output_kind" to "other", "preview_fa" to "", "why_fa" to "", "kind" to "work"),
        "steps" to JsonArray(s.steps), "blockers" to JsonArray(s.blockers), "outputs" to JsonArray(s.outputs), "summary" to null, "updated_at" to at(s.last),
        "pace" to s.pace, "conversation_ref" to s.cv, "turn" to s.turn,
        "session" to jo(
            "state" to (if (s.closedAt != null) "closed" else "open"), "badge" to s.badge, "reason_fa" to s.reason, "closed_at" to s.closedAt, "hidden" to s.hidden, "source" to s.source,
            *(if (s.playbookKept) arrayOf("playbook_kept" to KEPT_REF, "playbook_kept_fa" to KEPT_FA) else emptyArray()),
        ),
        "brief" to brief(s), "tasks" to JsonArray(s.tasks), "participants" to JsonArray(s.participants), "files" to JsonArray(s.files),
        "memory_md" to s.memory,
        // ⟨1.32⟩ §54 (a hub before it does not say the word)
        *(if (LookDemo.old55) emptyArray() else arrayOf("direct" to s.direct)),
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

    private fun open() = sessions.filter { it.closedAt == null && !it.hidden && it.listed }

    /** ⟨1.24⟩ §42.3 for [V42Demo]'s summary: each open session's badge and its holder's company. */
    @Synchronized
    fun liveBadges(): List<Pair<String, String?>> = open().map { it.badge to it.holder.third }

    // -------------------------------------------------------------- routes --
    @Synchronized
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        if (path == "/sessions" && method == "GET") {
            val list = when (query["state"]) {
                "closed" -> sessions.filter { it.closedAt != null && !it.hidden && it.listed }
                "all" -> sessions.filter { it.listed }
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
        liveWork(method, path, query)?.let { return it }
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
                // ⟨1.36⟩ §58.2 people beyond the holder, or an output: its working group is drafted and stays in the library
                if (s.participants.size > 1 || s.outputs.isNotEmpty()) s.playbookKept = true
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
            // ⟨1.23⟩ §41 the work, live, and «ادامه بده».
            action == "activity" && method == "GET" -> return 200 to activity(s)
            action == "nudge" && method == "POST" -> {
                if (s.closedAt != null) return 409 to problem(409, "order_ended", "این جلسه بسته است؛ اول بازش کن.")
                nudge(s)
                return 200 to activity(s)
            }
        }
        return null
    }

    // ------------------------------------------------- ⟨1.23⟩ §41 the work, live --
    // F-0104 is at work (its CEO and his SEO specialist, each at a step; a new line about every two seconds on the stream, in a loop);
    // F-0101 waits for the owner; F-0103 is stuck (why, and what fixes it); the others are quiet since their last move. «ادامه بده» wakes
    // the holder with the plan's next task: he works a few steps on the stream, then the session is quiet again.
    private class Live(
        val workers: MutableList<JsonObject> = mutableListOf(), val lines: MutableList<JsonObject> = mutableListOf(), var idleSince: String? = null,
        val script: ArrayDeque<Pair<String, String>> = ArrayDeque(), val loop: Boolean = false,
        /** ⟨1.24⟩ §42.2 the step in progress (its line's id): its end is sent as the same line, done, before the next one begins. */
        var running: String? = null, var steps: Int = 0,
    )

    /** A line of the work; ⟨1.24⟩ with [id] and [state] the hub's additive fields (a step's end updates its own line). */
    private fun line(at: String, who: String, text: String, id: String? = null, state: String? = null) =
        if (id == null) jo("at" to at, "who_fa" to who, "text_fa" to text)
        else jo("at" to at, "who_fa" to who, "text_fa" to text, "id" to id, "kind" to "step", "state" to state)
    private fun worker(who: String, company: String?, work: String, startedMin: Long, step: Int, doing: String, kind: String = "run", cap: Int? = null, last: String? = null) =
        jo(
            "who_fa" to who, "company_fa" to company, "work_title_fa" to work, "started_at" to at(startedMin), "step" to step, "doing_fa" to doing,
            // ⟨1.33⟩ §55.1 what kind of turn it is, its time cap, and the last thing it did in the owner's words
            "kind" to kind, "cap_s" to cap, "last_fa" to last, "last_at" to last?.let { now.minusSeconds(12).toString() },
        )

    private val live: MutableMap<String, Live> = mutableMapOf(
        "F-0104" to Live(
            workers = mutableListOf(
                worker("مدیرعامل پرو-چارت", "پرو-چارت", "سئوی سایت پرو-چارت", 14, 6, "فهرست صفحه‌هایی که باید بهتر شوند را مرتب میکند"),
                worker("کارشناس سئوی پرو-چارت", "پرو-چارت", "بررسی سه رقیب اول «چارت طلا»", 4, 3, "صفحه‌ی اول tradingview.com را میخواند"),
            ),
            // ⟨1.24⟩ F-0104 speaks the additive line: each step done (a tick) and the one in progress running (an arc).
            lines = mutableListOf(
                line(at(14), "مدیرعامل پرو-چارت", "کار «سئوی سایت پرو-چارت» را شروع کرد", "F-0104-1", "done"),
                line(at(13), "مدیرعامل پرو-چارت", "سایت pro-chart.com را خواند", "F-0104-2", "done"),
                line(at(12), "مدیرعامل پرو-چارت", "از ChatGPT پرسید کدام صفحه‌ها کمتر دیده میشوند", "F-0104-3", "done"),
                line(at(10), "مدیرعامل پرو-چارت", "سه رقیب اول را در جستجوی «چارت طلا» پیدا کرد", "F-0104-4", "done"),
                line(at(8), "مدیرعامل پرو-چارت", "بررسی رقبا را به کارشناس سئو سپرد", "F-0104-5", "done"),
                line(at(4), "کارشناس سئوی پرو-چارت", "کار «بررسی سه رقیب اول» را شروع کرد", "F-0104-6", "done"),
                line(at(3), "کارشناس سئوی پرو-چارت", "صفحه‌ی اول investing.com را خواند", "F-0104-7", "done"),
                line(at(2), "مدیرعامل پرو-چارت", "عنوان هشت صفحه‌ی سایت را خواند", "F-0104-8", "done"),
                line(at(1), "کارشناس سئوی پرو-چارت", "از Gemini پرسید کدام کلیدواژه‌ها جا مانده‌اند", "F-0104-9", "done"),
                line(now.minusSeconds(20).toString(), "مدیرعامل پرو-چارت", "فهرست صفحه‌هایی که باید بهتر شوند را مرتب میکند", "F-0104-10", "running"),
            ),
            running = "F-0104-10", steps = 10,
            script = ArrayDeque(listOf(
                "کارشناس سئوی پرو-چارت" to "صفحه‌ی اول tradingview.com را خواند",
                "مدیرعامل پرو-چارت" to "توضیح متای سه صفحه را دوباره نوشت",
                "کارشناس سئوی پرو-چارت" to "جدول مقایسه‌ی سه رقیب را ساخت",
                "مدیرعامل پرو-چارت" to "از DeepSeek پرسید عنوان‌ها طبیعی‌اند یا نه",
                "کارشناس سئوی پرو-چارت" to "خروجی «مقایسه‌ی رقبا» را تحویل داد",
                "مدیرعامل پرو-چارت" to "صفحه‌ی «چارت طلا» را برای نوشتن دوباره علامت زد",
            )),
            loop = true,
        ),
        // ⟨1.33⟩ a workshop turn, 23 minutes into its hour, and the holder's own direct turn
        "F-0090" to Live(
            workers = mutableListOf(worker("سازنده‌ی موشن‌گرافی", "پرو-چارت", "ساخت موشن‌گرافی ATR", 23, 0, "موشن‌گرافی را میسازد", kind = "workshop", cap = 3600, last = "صحنه‌ی ۳ را رندر میکند")),
            lines = mutableListOf(
                line(at(22), "سازنده‌ی موشن‌گرافی", "کار را در کارگاه شروع کرد", "F-0090-1", "done"),
                line(at(9), "سازنده‌ی موشن‌گرافی", "صحنه‌ی ۲ را رندر کرد", "F-0090-2", "done"),
                line(now.minusSeconds(12).toString(), "سازنده‌ی موشن‌گرافی", "صحنه‌ی ۳ را رندر میکند", "F-0090-3", "running"),
            ),
            running = "F-0090-3", steps = 3,
            script = ArrayDeque(listOf(
                "سازنده‌ی موشن‌گرافی" to "فایل «scene-4.tsx» را مینویسد", "سازنده‌ی موشن‌گرافی" to "دستور اجرا میکند",
                "سازنده‌ی موشن‌گرافی" to "صحنه‌ی ۴ را رندر میکند", "سازنده‌ی موشن‌گرافی" to "صحنه‌ی ۳ را رندر میکند",
            )),
            loop = true,
        ),
        "F-0091" to Live(
            workers = mutableListOf(worker("مدیر رسانه‌ی تریدیار", "تریدیار", "کپشن سه ریلز", 6, 0, "روی فرمان کار میکند", kind = "direct", cap = 3600, last = "فایل «caption.md» را مینویسد")),
            lines = mutableListOf(line(now.minusSeconds(8).toString(), "مدیر رسانه‌ی تریدیار", "فایل «caption.md» را مینویسد", "F-0091-1", "running")),
            running = "F-0091-1", steps = 1,
            script = ArrayDeque(listOf("مدیر رسانه‌ی تریدیار" to "کپشن ریلز دوم را مینویسد", "مدیر رسانه‌ی تریدیار" to "فایل «caption.md» را مینویسد")),
            loop = true,
        ),
        // ⟨2026-11-11⟩ an outside call at work: the draft of the text waits in ChatGPT's queue (its deadline is its cap)
        "F-0094" to Live(
            workers = mutableListOf(worker("ChatGPT", "پرو-چارت", "پیش‌نویس متن ریلز اول", 4, 0, "در صف ChatGPT: پیش‌نویس متن", kind = "call", cap = 900)),
            lines = mutableListOf(
                line(at(5), "مدیرعامل پرو-چارت", "دوباره سر کار آمد", "F-0094-1", "done"),
                line(at(4), "مدیرعامل پرو-چارت", "از ChatGPT پرسید", "F-0094-2", "done"),
            ),
        ),
        "F-0100" to Live(
            workers = mutableListOf(
                worker("مدیر رسانه‌ی پرو-چارت", "پرو-چارت", "ریلز آزمایشی «سه اشتباه رایج در چارت طلا»", 22, 7, "زیرنویس ریلز آزمایشی را مینویسد"),
                worker("تدوینگر ریلز", "پرو-چارت", "زیرنویس و برش ریلز آزمایشی", 6, 2, "برش‌های ریلز را با متن هم‌زمان میکند"),
            ),
            lines = mutableListOf(
                line(at(48), "مدیر رسانه‌ی پرو-چارت", "کار «ریلز آزمایشی» را شروع کرد"),
                line(at(46), "مدیر رسانه‌ی پرو-چارت", "از ChatGPT پرسید کدام اشتباه چارت طلا بیشتر دیده میشود"),
                line(at(43), "مدیر رسانه‌ی پرو-چارت", "متن ریلز را نوشت"),
                line(at(41), "مدیر رسانه‌ی پرو-چارت", "خروجی «متن ریلز آزمایشی» را تحویل داد"),
                line(at(40), "مدیر رسانه‌ی پرو-چارت", "کاور را با Gemini در AI Studio ساخت"),
                line(at(31), "مدیر رسانه‌ی پرو-چارت", "صداگذاری را برای بودجه نگه داشت"),
                line(at(6), "تدوینگر ریلز", "کار «زیرنویس و برش» را شروع کرد"),
                line(at(3), "مدیر رسانه‌ی پرو-چارت", "زیرنویس بخش اول را نوشت"),
                line(at(1), "تدوینگر ریلز", "برش اول ریلز را ساخت"),
            ),
        ),
    )

    private fun liveOf(s: S): Live = live.getOrPut(s.ref) {
        // The quiet ones: their report's steps as the lines (the hub's own, «سامانه», are not a step of anyone's work).
        Live(
            lines = s.steps.filter { it.str("who_fa") != "سامانه" }.map { line(it.str("at").orEmpty(), it.str("who_fa").orEmpty(), it.str("what_fa").orEmpty()) }.toMutableList(),
            idleSince = s.closedAt ?: at(s.last),
        )
    }

    private fun activity(s: S): JsonObject {
        val l = liveOf(s)
        val working = s.closedAt == null && l.workers.isNotEmpty()
        val waiting = if (!working && s.closedAt == null) s.turn?.str("question_fa") else null
        val stuck = if (!working && s.closedAt == null && s.turn == null && s.badge == "stuck") STUCK_FA[s.ref] ?: s.reason else null
        val old = LookDemo.old55
        // ⟨1.33⟩ §55.1 a turn near its hour ([LookDemo.ring]); a hub before §55 says neither a worker's kind, cap and last line nor the mood
        val workers = (if (working) l.workers else emptyList()).map { w ->
            when {
                old -> JsonObject(w - setOf("kind", "cap_s", "last_fa", "last_at"))
                LookDemo.ring == "late" && w.str("kind") == "workshop" -> JsonObject(w + ("started_at" to JsonPrimitive(at(56))))
                else -> w
            }
        }
        // by the hub's own rule: someone works (still thinking until a run's first step, or a turn's first act); else it waits for
        // the owner; else it is stuck; else calm
        val mood = when {
            working -> if (l.workers.any { w ->
                when (w.str("kind") ?: "run") {
                    "run" -> ((w["step"] as? JsonPrimitive)?.contentOrNull?.toIntOrNull() ?: 0) > 0
                    "call" -> true
                    else -> w.str("last_fa") != null
                }
            }) "working" else "thinking"
            waiting != null -> "waiting"
            stuck != null -> "stuck"
            else -> "idle"
        }
        return JsonObject(
            jo(
                "working" to JsonArray(workers),
                "last" to JsonArray(l.lines.takeLast(30)),
                "idle_since" to (if (working) null else l.idleSince),
                "waiting_fa" to waiting,
                "stuck_fa" to stuck,
            ) + if (old) emptyMap() else mapOf("mood" to JsonPrimitive(mood), "mood_fa" to JsonPrimitive(MOOD_FA.getValue(mood))),
        )
    }

    // ------------------------------------------------- ⟨1.33⟩ «نگه دار»: the owner's stop of a live work --
    /** The live works a session's plan names, by their id; the workers he stopped, by session («ادامه بده» brings them back). */
    private val liveWorks = mapOf("W-000390" to "F-0090", "W-000391" to "F-0091")
    private val held = mutableMapOf<String, List<JsonObject>>()
    private fun workId(ref: String) = "w-" + ref.lowercase()
    private fun workOf(ref: String, s: S) = jo(
        "id" to workId(ref), "ref" to ref, "company" to (s.holder.third ?: "HQ"), "title" to (s.tasks.firstOrNull { it.str("work_ref") == ref }?.str("title_fa") ?: s.text.take(60)),
        "status" to "in_progress", "created_at" to at(s.opened), "updated_at" to at(s.last),
    )

    /** `GET /work?q=W-…`, `GET /work/{id}` and `POST /work/{id}/stop` of a session's live work: the work stays open, its workers leave. */
    private fun liveWork(method: String, path: String, query: Map<String, String?>): Pair<Int, JsonElement>? {
        if (path == "/work" && method == "GET") {
            val ref = query["q"]?.takeIf { it in liveWorks } ?: return null
            val s = sessions.firstOrNull { it.ref == liveWorks[ref] } ?: return null
            return 200 to jo("items" to JsonArray(listOf(workOf(ref, s))), "next_cursor" to null)
        }
        val m = Regex("^/work/(w-w-0003\\d\\d)(/stop)?$").find(path) ?: return null
        val ref = liveWorks.keys.firstOrNull { workId(it) == m.groupValues[1] } ?: return null
        val s = sessions.firstOrNull { it.ref == liveWorks[ref] } ?: return null
        if (m.groupValues[2].isEmpty()) return if (method == "GET") 200 to workOf(ref, s) else null
        if (method != "POST") return null
        val l = liveOf(s)
        if (l.workers.isNotEmpty()) { held[s.ref] = l.workers.toList(); l.workers.clear() }
        l.idleSince = HqClock.now().toString()
        l.running?.let { id -> val i = l.lines.indexOfFirst { it.str("id") == id }; if (i >= 0) l.lines[i] = JsonObject(l.lines[i] + ("state" to JsonPrimitive("done"))) }
        s.badge = "moving"; s.reason = "به دستور تو نگه داشته شد."
        return 200 to jo("work_ref" to ref, "jobs_stopped" to 1, "workspace" to "stopped")
    }

    /** «ادامه بده»: the holder takes the plan's next task now; a few steps follow on the stream. */
    private fun nudge(s: S) {
        val l = liveOf(s)
        if (l.workers.isNotEmpty()) return
        // what he held goes on from where it was: the same workers, a new start
        held.remove(s.ref)?.let { back ->
            l.workers += back.map { w -> JsonObject(w + ("started_at" to JsonPrimitive(HqClock.now().toString()))) }
            l.idleSince = null
            s.reason = "${s.holder.second} دوباره دست به کار شد."; s.last = 0
            return
        }
        val next = s.tasks.firstOrNull { it.str("state") == "doing" } ?: s.tasks.firstOrNull { it.str("state") == "todo" }
        val task = next?.str("title_fa") ?: "قدم بعد"
        l.workers += worker(s.holder.second, companyFa(s.holder.third), s.text.take(60), 0, 1, "کار بعدی برنامه: $task")
        l.lines += line(now.toString(), s.holder.second, "دوباره دست به کار شد: $task")
        l.idleSince = null
        l.script.addAll(listOf(s.holder.second to "برنامه را از «$task» ادامه داد", s.holder.second to "یک قدم از «$task» را برداشت"))
        s.badge = "moving"; s.reason = "${s.holder.second} دوباره دست به کار شد."; s.last = 0
    }

    private var liveSeq = 0

    /** The stream's `session.activity` lines (from [DemoLive], about every two seconds): each working session's next scripted step. */
    @Synchronized
    fun tick(tick: Int): List<com.coinepro.hq.core.net.StreamEvent> {
        if (tick % 3 != 0) return emptyList()
        val out = mutableListOf<com.coinepro.hq.core.net.StreamEvent>()
        for ((ref, l) in live) {
            val s = sessions.firstOrNull { it.ref == ref && it.closedAt == null } ?: continue
            // an outside call takes no steps of its own: it is there until its answer comes
            if (l.workers.isNotEmpty() && l.workers.all { it.str("kind") == "call" }) continue
            val nowIso = HqClock.now().toString()
            val step = l.script.removeFirstOrNull()
            if (step == null) {
                if (l.workers.isEmpty()) continue
                l.workers.clear(); l.idleSince = nowIso
                out += activityEvent(s, line(nowIso, s.holder.second, "این قدم تمام شد؛ منتظر کار بعدی است"), 0)
                l.lines += line(nowIso, s.holder.second, "این قدم تمام شد؛ منتظر کار بعدی است")
                continue
            }
            if (l.loop) l.script.addLast(step)
            val (who, text) = step
            // ⟨1.24⟩ the step in progress ends first (the same line, done), then the next begins (running).
            l.running?.let { id ->
                val i = l.lines.indexOfFirst { it.str("id") == id }
                if (i >= 0) {
                    l.lines[i] = JsonObject(l.lines[i] + ("state" to JsonPrimitive("done")))
                    out += activityEvent(s, l.lines[i], l.workers.size)
                }
            }
            val ln = if (l.running != null) line(nowIso, who, text, "$ref-${++l.steps}", "running").also { l.running = "$ref-${l.steps}" } else line(nowIso, who, text)
            l.lines += ln
            while (l.lines.size > 30) l.lines.removeAt(0)
            val i = l.workers.indexOfFirst { it.str("who_fa") == who }
            if (i >= 0) {
                val n = ((l.workers[i]["step"] as? JsonPrimitive)?.contentOrNull?.toIntOrNull() ?: 0) + 1
                val turn = l.workers[i].str("kind").let { it == "workshop" || it == "direct" }
                l.workers[i] = JsonObject(
                    l.workers[i] + if (turn) mapOf("last_fa" to JsonPrimitive(text), "last_at" to JsonPrimitive(nowIso)) else mapOf("step" to JsonPrimitive(n), "doing_fa" to JsonPrimitive(text)),
                )
            }
            out += activityEvent(s, ln, l.workers.size)
        }
        return out
    }

    private fun activityEvent(s: S, ln: JsonObject, working: Int) = com.coinepro.hq.core.net.StreamEvent(
        // No company on the demo's lines: the demo's own run script already stirs each company's ring, and the screenshots of the
        // holding (seeded with the stream's first beats) stay as they were. The session reads its order from the data.
        "demo-sa-${++liveSeq}", "session.activity", HqClock.now().toString(), null, s.ref,
        jo("order" to s.ref, "line" to ln, "working" to working),
    )

    init { DemoLive.sessions = this }

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
        /** ⟨0.19.0⟩ the owner's nine steps of the reels working group (his own words, the plan of F-0100). */
        val REELS_STEPS = listOf(
            "موضوع هر ریلز با ChatGPT پیدا شود",
            "متن ریلز نوشته و با جی‌پی‌تی خوانده شود",
            "یک ریلز آزمایشی ساخته شود",
            "کاور با Gemini در AI Studio ساخته شود",
            "صداگذاری با صداپیشه",
            "زیرنویس و برش با تدوینگر",
            "پیش از انتشار به تأیید مدیر کل برسد",
            "هر روز ساعت ۱۸ در اینستاگرام منتشر شود",
            "گزارش هفتگی بازدید و دنبال‌کننده",
        )

        /** ⟨0.19.0⟩ the media director's long notes (a long answer of an agent, as they are). */
        const val REELS_NOTES = "نکته‌های من درباره‌ی این کارگروه:\n\n" +
            "- **موضوع‌ها:** از ChatGPT ده موضوع گرفتم؛ سه تا برای شروع بهترند: «سه اشتباه رایج در چارت طلا»، «حمایت و مقاومت در یک دقیقه» و «چرا تایم‌فریم مهم است».\n" +
            "- **ساخت:** هر ریلز ۳۰ تا ۴۵ ثانیه، با کاور یکدست و فونت تیتر پرو-چارت.\n" +
            "- **آدم‌ها:** برای صداگذاری و برش یک صداپیشه و یک تدوینگر لازم است؛ کارت استخدام هر دو را برای مدیرعامل گذاشتم.\n" +
            "- **زمان انتشار:** ساعت ۱۸ بیشترین بازدید را دارد؛ آخر هفته‌ها یک ریلز بیشتر.\n\n" +
            "اول یک ریلز آزمایشی میسازم تا لحن و طول را با هم ببینیم؛ بعد بقیه را پشت سر هم."

        /** ⟨2026-11-11⟩ The holder's last word of the owner's 12-hour stall, as it was (F-0095), and the same word while the draft is in
         *  ChatGPT's queue (F-0094). */
        const val STALLED_FA = "گام ۲ در جریان است. موضوع اول («معرفی ابزارهای ترسیم روی نمودار پرو-چارت») ثبت شد. گوینده‌ی ثابت پرو-چارت " +
            "(Kore، فارسی معیار و گرم) یک‌بار برای همیشه تنظیم شد. پیش‌نویس متن ۱ تا ۱:۳۰ دقیقه با شعار «پرو چارت؛ همیشه با نمودار» و " +
            "کلمه‌ی کامنت «چارت» از ChatGPT خواسته شد و در صف است."
        /** ⟨1.36⟩ §58.2 what a closed session left in the library, as the hub says it (the draft of the library's demo). */
        const val KEPT_REF = "PB-0002"
        const val KEPT_FA = "کارگروه این جلسه در کتابخانه ماند"

        /** ⟨1.36⟩ §58.1 a long question of the holder's (F-0096): more than three lines on a phone. */
        const val LONG_QUESTION_FA = "نسخه‌ی اول ریلز حد ضرر آماده است و خودش را همین بالا میبینی. پیش از اینکه کاور و کپشن را نهایی کنم سه چیز را باید بدانم.\n" +
            "یک: ریلز با یک سؤال از بیننده شروع شود یا با عدد ۸۰ درصد معامله‌گرهایی که حد ضرر را اشتباه میگذارند؟\n" +
            "دو: زیرنویس فارسی کامل باشد یا فقط کلمه‌های کلیدی روی تصویر بیاید؟\n" +
            "سه: آخر ریلز دعوت به کانال تلگرام باشد یا دعوت به دنبال کردن صفحه؟\n" +
            "اگر روی صدای گوینده یا سرعت برش هم نظری داری همین‌جا بگو. اول از همه این را بگو: با سؤال شروع کنیم یا با عدد؟"
        const val DRAFT_ASKED_FA = "پیش‌نویس متن ریلز اول از ChatGPT خواسته شد و در صف است؛ تا جوابش برسد، کاور را آماده میکنم."

        /** The eighteen steps of Pro-Chart's daily reels («با من»). */
        val REELS_PLAN = listOf(
            "استخدام سناریست و روش موضوع روزانه", "متن گوینده و تنظیم یک‌بار صدا", "پیش‌نویس متن ریلز اول با ChatGPT", "خواندن متن با صدای گوینده",
            "موشن‌گرافی ریلز اول", "کاور ریلز اول", "کپشن و کلمه‌ی کامنت", "تأیید و انتشار ریلز اول", "خواندن بازخورد ریلز اول",
            "موضوع روز دوم", "متن روز دوم", "صدا و موشن‌گرافی روز دوم", "انتشار روز دوم", "پیدا کردن بهترین ساعت انتشار",
            "کارگروه روزانه‌ی ریلز", "انتشار خودکار هر روز", "گزارش هفته‌ی اول", "جمع‌بندی و بستن",
        )

        /** ⟨1.33⟩ §55.1 the mood in a word, as the hub says it. */
        val MOOD_FA = mapOf("thinking" to "فکر میکند", "working" to "کار میکند", "waiting" to "منتظر تو", "stuck" to "گیر کرده", "idle" to "آرام")

        /** ⟨1.23⟩ §41.3 why a stuck session is stuck, in plain words, and what fixes it (as the hub's sweep writes it). */
        val STUCK_FA = mapOf(
            "F-0103" to "کسی برای پشتیبان تلگرام نیست و استخدام در کوینه‌پرو FX بسته است؛ استخدام را باز کن تا منشی ادامه دهد.",
        )

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
