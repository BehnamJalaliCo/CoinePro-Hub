package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.net.DeliverableQuery
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * Debug builds only: the outputs of contract §5.2 ⟨1.7.3⟩, which the web's mock has not got yet: every deliverable gains `category`,
 * `seen_at` and `filed_as`; `GET /deliverables` takes `seen`, `category`, `from`, `to`, `producer` and `q`; `POST /deliverables/seen`
 * and `POST /deliverables/{ref}/file` answer as the hub will; `GET /inbox/summary` adds `deliverables_unseen`. Three outputs are added
 * to the fixtures: the rule-based morning report as the hub writes it (worker/report.py, with its table of companies), and two of the
 * days before, seen (one filed), so the list has days to group by.
 */
internal class OutputsDemo(
    private val store: MutableMap<String, Pair<Int, JsonElement>>,
    /** ⟨1.31⟩ §49 the best hour of a company's account, as the demo's rule answers it. */
    private val bestHour: (String, String?) -> JsonObject? = { _, _ -> null },
) {
    private val seen = mutableMapOf<String, String>()
    private val filed = mutableMapOf<String, String>()
    private var nextRecord = 97

    // ⟨0.19.8⟩ §44.5 «تأیید و انتشار»: the publishes of the session's outputs, newest first, and the accounts of its company.
    private val published = mutableMapOf<String, MutableList<JsonObject>>()
    private val sessionOutputs = mutableMapOf("O-000950" to listOf("coineprofx", "coineprofx.academy"), "O-000951" to listOf("coineprofx"))
    /** ⟨0.19.9⟩ §45 outputs a working group's routine made (no session), with the group's name. Declared before `init` fills it. */
    private val groupOutputs = mutableMapOf<String, String>()
    private var nextJob = 30
    /** ⟨1.33⟩ The session each session output belongs to (the others: [SESSION]), the caption a package carries, and the outputs the
     *  publish desk shows (§55.2), in the order the demo made them. */
    private val orderOf = mutableMapOf<String, String>()
    private val captions = mutableMapOf<String, String>()
    private val deskSet = mutableListOf<String>()
    /** The companies whose publishing path is not set yet (the technical team's work, never the owner's). */
    private val noRoute = setOf("O-000970")
    /** ⟨1.31⟩ §51 the publications IG-Hub already holds (a cancel is asked of it: «در حال لغو»), and those whose file is still on its way. */
    private val held = mutableSetOf("jp-2", "jp-23")
    private val onItsWay = mutableSetOf("jp-11")

    init {
        val now = HqClock.now()
        fun at(minutes: Long) = now.minus(minutes, ChronoUnit.MINUTES).toString()
        val morning = deliverable(
            "O-000032", "HQ", "W-000131", sys(), "گزارش صبحگاهی ۱۴۰۵/۰۷/۲۵ / 2026-10-17",
            "11 تصمیم در انتظار، 6 خروجی تازه (5 بی‌امتیاز)، 3 پیام نخوانده.", MORNING, at(150),
            produced = buildJsonObject { put("label_fa", "قاعده‌محور، بدون مدل"); put("provider", "rules") },
        )
        val yesterday = deliverable(
            "O-000028", "TY", "W-000118", agent("TY-GROWTH-02", "TY", "GROWTH", "تحلیلگر کمپین"), "تحلیل نرخ تبدیل کمپین پاییز",
            "نرخ تبدیل ثبت‌نام به واریز در کمپین پاییز 3.1٪ بود، 0.6 واحد بالاتر از تابستان؛ بیشترین افت در مرحله‌ی تأیید هویت.",
            "## یافته‌ها\n- نرخ تبدیل: **3.1%** (تابستان 2.5%)\n- بیشترین افت: تأیید هویت (41% رها)\n\n## پیشنهاد\n1. پیام یادآوری ۲ ساعت بعد\n2. راهنمای تصویری تأیید هویت",
            at(60 * 24 + 200),
        )
        val earlier = deliverable(
            "O-000026", "FX", "W-000112", agent("FX-QUANT-02", "FX", "QUANT", "پایشگر سیگنال"), "گزارش هفتگی دقت سیگنال‌ها",
            "دقت هفته 68٪، در محدوده‌ی هدف؛ دو سیگنال طلا بی‌دلیل منقضی شدند.", "دقت هفته **68%**؛ جزئیات در پیوست پایش.", at(3 * 60 * 24 + 90),
        )
        for (d in listOf(morning, yesterday, earlier)) store["/deliverables/${d.str("ref")}"] = 200 to d
        // ⟨0.19.8⟩ §44.5 two outputs of a session, made by the workshop (opened by their ref; not in the lists): a reel and its cover
        // ready for «تأیید و انتشار», and the same with a story once the owner tapped (one published, one on its way, one refused).
        val media = agent("FX-MEDIA-01", "FX", "MEDIA", "مدیر رسانه")
        val reel = file("/demo/fx-reel-levels.mp4", "gold-levels-reel.mp4", "video/mp4", "video", "/demo/fx-reel-levels-poster.webp")
        val cover = file("/demo/fx-reel-levels-poster.webp", "gold-levels-cover.webp", "image/webp", "image")
        val story = file("/demo/ty-story-stoploss-poster.webp", "gold-levels-story.webp", "image/webp", "image")
        // ⟨1.31⟩ §53 a workshop turn's output says the model it ran on and how hard it thought
        val workshop = buildJsonObject { put("runtime", "workshop"); put("model", "claude-opus-5-5"); put("effort", "max") }
        for ((ref, files) in listOf("O-000950" to listOf(reel, cover), "O-000951" to listOf(reel, cover, story))) {
            val d = deliverable(
                ref, "FX", "W-000311", media, "خروجی کارگاه: ریلز «سطوح کلیدی طلا»",
                "ریلز ۶ ثانیه‌ای با گوینده آماده است؛ کاور و کپشن هم ساخته شد.",
                "ریلز **سطوح کلیدی طلا** آماده است.\n\n- ویدیو: ۶ ثانیه، عمودی، با صدای گوینده\n- کاور: تیتر با IRANYekanX\n\n**کپشن پیشنهادی:** سه سطحی که این هفته طلا را جابه‌جا میکند. #طلا #فارکس\n\nتأیید و انتشار؟",
                at(25), produced = workshop,
            )
            store["/deliverables/$ref"] = 200 to JsonObject(d + ("attachments" to JsonArray(files)))
        }
        // ⟨0.19.9⟩ §45 a working group's daily output (no session): the package went out on the owner's standing word
        val caption = file("/demo/fx-reel-levels-caption.txt", "caption.txt", "text/plain", "file")
        val daily = deliverable(
            "O-000952", "TY", "W-000340", agent("TY-MEDIA-02", "TY", "MEDIA", "سناریست"), "خروجی کارگاه: ریلز روز «حد ضرر در ۳۰ ثانیه»",
            "ریلز امروز کارگروه با کاور و کپشن آماده شد.",
            "ریلز **حد ضرر در ۳۰ ثانیه** آماده است: ویدیو، کاور و کپشن در همین خروجی.", at(40), produced = workshop,
        )
        store["/deliverables/O-000952"] = 200 to JsonObject(daily + ("attachments" to JsonArray(listOf(reel, cover, caption))))
        groupOutputs["O-000952"] = "تولید محتوای روزانه‌ی اینستاگرام"
        published["O-000952"] = mutableListOf(
            publish("O-000952", "jp-9", reel, "story", "tradeyar", "publishing", at = at(38), auto = true),
            publish("O-000952", "jp-8", reel, "reel", "tradeyar", "published", url = "https://www.instagram.com/reel/C9xStopLs/", at = at(38), cover = "gold-levels-cover.webp", auto = true),
        )
        // ⟨0.20.0⟩ §46 a reel set for this evening with its own comment word, and a carousel on its way
        val slide = file("/demo/ty-story-stoploss-poster.webp", "levels-2.jpg", "image/jpeg", "image")
        val timed = deliverable(
            "O-000953", "FX", "W-000312", media, "خروجی کارگاه: ریلز «نقطه‌ی ورود طلا»",
            "ریلز با کاور، کپشن و کلمه‌ی کامنت آماده است.", "ریلز **نقطه‌ی ورود طلا** آماده است.", at(20), produced = workshop,
        )
        store["/deliverables/O-000953"] = 200 to JsonObject(timed + ("attachments" to JsonArray(listOf(reel, cover, slide))))
        sessionOutputs["O-000953"] = listOf("coineprofx")
        published["O-000953"] = mutableListOf(
            publish("O-000953", "jp-11", cover, "carousel", "coineprofx", "publishing", at = at(2), count = 2),
            publish(
                "O-000953", "jp-10", reel, "reel", "coineprofx", "scheduled", at = at(5), cover = "gold-levels-cover.webp",
                scheduledAt = "2026-11-06T15:00:00Z", comment = "۷",
            ),
        )
        // ⟨1.31⟩ §51 the same session's next reel, set for this evening, in every state of a cancel: one he can still take back, one
        // taken back, one whose cancel is on its way to IG-Hub, and one IG-Hub would not cancel.
        val pngCover = file("/demo/fx-reel-resist-poster.webp", "entry-cover.png", "image/png", "image")
        val lastSlide = file("/demo/pc-landing-redesign.webp", "entry-slide.jpg", "image/jpeg", "image")
        val evening = HqClock.today().atTime(18, 30).atZone(java.time.ZoneId.of(com.coinepro.hq.core.format.OWNER_TZ)).toInstant().toString()
        val next = deliverable(
            "O-000954", "FX", "W-000313", media, "خروجی کارگاه: ریلز «حد سود در بازار طلا»",
            "ریلز فردا با کاور، استوری و اسلاید آماده است.", "ریلز **حد سود در بازار طلا** آماده است: ویدیو، کاور، استوری و یک اسلاید.", at(12), produced = workshop,
        )
        store["/deliverables/O-000954"] = 200 to JsonObject(next + ("attachments" to JsonArray(listOf(reel, pngCover, story, lastSlide))))
        sessionOutputs["O-000954"] = listOf("coineprofx")
        published["O-000954"] = mutableListOf(
            publish("O-000954", "jp-23", lastSlide, "post", "coineprofx", "scheduled", note = "لغو انجام نشد (IG-Hub جواب نداد)", at = at(6), scheduledAt = evening),
            publish("O-000954", "jp-22", story, "story", "coineprofx", "scheduled", note = "در حال لغو", at = at(7), scheduledAt = evening),
            publish("O-000954", "jp-21", pngCover, "post", "coineprofx", "cancelled", at = at(8), scheduledAt = evening),
            publish("O-000954", "jp-20", reel, "reel", "coineprofx", "scheduled", at = at(9), cover = "entry-cover.png", scheduledAt = evening),
        )
        published["O-000951"] = mutableListOf(
            publish("O-000951", "jp-3", story, "story", "coineprofx", "failed", note = "حساب امروز به سقف انتشار رسیده است.", at = at(4)),
            publish("O-000951", "jp-2", cover, "post", "coineprofx", "publishing", at = at(1)),
            publish("O-000951", "jp-1", reel, "reel", "coineprofx", "published", url = "https://www.instagram.com/reel/C9xGoldLv/", at = at(18), cover = "gold-levels-cover.webp"),
        )
        // ⟨1.33⟩ §55 the look: the reel the session F-0092 waits on, what the closed session F-0093 made, and the publish desk in every
        // state (a picture post, a reel of a company whose publishing path is not set, two in the queue, three that are done).
        val tyMedia = agent("TY-MEDIA-MGR", "TY", "MEDIA", "مدیر رسانه")
        val pcMedia = agent("PC-MEDIA-MGR", "PC", "MEDIA", "مدیر رسانه")
        val used = buildJsonObject { put("input_tokens", 212_000); put("output_tokens", 41_000); put("cache_read_tokens", 78_000); put("cost_usd", "3.84") }
        fun look(
            ref: String, company: String, producer: JsonObject, title: String, summary: String, body: String, minAgo: Long, files: List<JsonObject>,
            accounts: List<String>?, order: String? = null, caption: String? = null, group: String? = null, desk: Boolean = true,
        ) {
            val d = deliverable(ref, company, "W-000${ref.takeLast(3)}", producer, title, summary, body, at(minAgo), produced = workshop)
            store["/deliverables/$ref"] = 200 to JsonObject(d + mapOf("attachments" to JsonArray(files), "usage" to used))
            if (accounts != null && group == null) sessionOutputs[ref] = accounts
            if (order != null) orderOf[ref] = order
            if (caption != null) captions[ref] = caption
            if (group != null) groupOutputs[ref] = group
            if (desk) deskSet += ref
        }
        val stopReel = file("/demo/ty-story-stoploss.mp4", "reel-stoploss.mp4", "video/mp4", "video", "/demo/ty-story-stoploss-poster.webp", size = 32_183, seconds = 30)
        val stopCover = file("/demo/ty-story-stoploss-poster.webp", "cover.png", "image/png", "image", size = 11_962)
        look(
            "O-000967", "TY", tyMedia, "ریلز: حد ضرر را کجا بگذاریم", "ریلز ۳۰ ثانیه‌ای با کاور؛ آماده‌ی انتشار.",
            "## خلاصه\nریلز ۳۰ ثانیه‌ای با کاور؛ آماده‌ی انتشار.\n\n## متن گوینده\nحد ضرر را جایی بگذار که اگر بازار به آن رسید، دلیل ورودت دیگر درست نباشد؛ نه جایی که فقط دوست داری ضرر کمتر باشد.",
            40, listOf(stopReel, stopCover), listOf("tradeyar"), order = "F-0092", caption = "حد ضرر را کجا بگذاریم؟ سه قانون ساده.\n#تریدیار #حد_ضرر",
        )
        look(
            "O-000968", "TY", tyMedia, "ریلز: سطوح کلیدی طلا", "ریلز با کاور و متن گوینده ساخته شد.", "ریلز **سطوح کلیدی طلا** با کاور و متن گوینده ساخته و منتشر شد.",
            2_921, listOf(reel, cover, file("/demo/docs/gold-levels-script.pdf", "voice-script.pdf", "application/pdf", "document", size = 148_300)),
            listOf("tradeyar"), order = "F-0093", desk = false,
        )
        published["O-000968"] = mutableListOf(
            publish("O-000968", "jp-40", reel, "reel", "tradeyar", "published", url = "https://www.instagram.com/reel/C9xGoldKy/", at = at(2_915), cover = "gold-levels-cover.webp"),
        )
        look(
            "O-000969", "PC", pcMedia, "پست ۱: خط روند در یک نگاه", "پست ثابت معرفی ابزار خط روند.", "پست **خط روند در یک نگاه** با یک مثال واقعی از نمودار طلا آماده است.",
            26 * 60, listOf(file("/demo/pc-landing-redesign.webp", "post-01.jpg", "image/jpeg", "image", size = 19_810, w = 960, h = 600)),
            listOf("pro.chart"), caption = "خط روند را با یک مثال واقعی ببین.\n#پروچارت #تحلیل_تکنیکال",
        )
        look(
            "O-000970", "FX", media, "ریلز: مقاومت هفته", "ریلز هفتگی مقاومت طلا.", "ریلز **مقاومت هفته** آماده است.", 5 * 60,
            listOf(file("/demo/fx-reel-resist.mp4", "reel-fx.mp4", "video/mp4", "video", "/demo/fx-reel-resist-poster.webp", size = 108_223, seconds = 12)),
            null, caption = "مقاومت این هفته کجاست؟\n#فارکس",
        )
        val feeReel = file("/demo/fx-reel-resist.mp4", "reel-03.mp4", "video/mp4", "video", "/demo/fx-reel-resist-poster.webp", size = 108_223, seconds = 12)
        look("O-000971", "TY", tyMedia, "ریلز ۳: کارمزد را کجا ببینیم", "ریلز سوم هفته.", "ریلز **کارمزد را کجا ببینیم** آماده است.", 8 * 60 + 10, listOf(feeReel), listOf("tradeyar"), caption = "کارمزد هر معامله را کجا ببینیم.\n#تریدیار")
        published["O-000971"] = mutableListOf(publish("O-000971", "jp-41", feeReel, "reel", "tradeyar", "publishing", at = at(3)))
        val minuteReel = file("/demo/fx-reel-levels.mp4", "reel-02.mp4", "video/mp4", "video", "/demo/fx-reel-levels-poster.webp", size = 110_561, seconds = 6)
        look("O-000972", "TY", tyMedia, "ریلز ۲: حد ضرر در یک دقیقه", "ریلز دوم هفته.", "ریلز **حد ضرر در یک دقیقه** آماده است.", 8 * 60 + 5, listOf(minuteReel), listOf("tradeyar"), caption = "حد ضرر را کجا بگذاریم؟ یک دقیقه، یک قانون.\n#تریدیار #حد_ضرر", group = "تولید محتوای روزانه‌ی اینستاگرام")
        val tonight = HqClock.today().atTime(21, 30).atZone(java.time.ZoneId.of(com.coinepro.hq.core.format.OWNER_TZ)).toInstant().toString()
        published["O-000972"] = mutableListOf(publish("O-000972", "jp-42", minuteReel, "reel", "tradeyar", "scheduled", at = at(50), scheduledAt = tonight, auto = true))
        val motion13 = file("/demo/ty-story-stoploss.mp4", "motion-13.mp4", "video/mp4", "video", "/demo/ty-story-stoploss-poster.webp", size = 32_183, seconds = 2)
        look("O-000973", "PC", pcMedia, "موشن‌گرافی روز: باند بولینگر", "موشن‌گرافی امروز کارگروه.", "موشن‌گرافی **باند بولینگر** ساخته شد.", 3 * 60, listOf(motion13), listOf("pro.chart"), caption = "باند بولینگر چه میگوید؟\n#پروچارت", group = "موشن‌گرافی روزانه‌ی پرو-چارت")
        published["O-000973"] = mutableListOf(publish("O-000973", "jp-43", motion13, "reel", "pro.chart", "failed", note = "اینستاگرام این ویدیو را نپذیرفت: طولش باید دست‌کم ۳ ثانیه باشد.", at = at(120), auto = true))
        val slides = listOf("slide-1.jpg" to "/demo/fx-reel-levels-poster.webp", "slide-2.jpg" to "/demo/fx-reel-resist-poster.webp", "slide-3.jpg" to "/demo/ty-story-stoploss-poster.webp")
            .map { (n, id) -> file(id, n, "image/jpeg", "image", size = 8_530) }
        look("O-000974", "PC", pcMedia, "پست ۲: هشدار قیمت", "سه اسلاید آموزش هشدار قیمت.", "سه اسلاید **هشدار قیمت** آماده است.", 30 * 60, slides, listOf("pro.chart"), caption = "ساختن هشدار قیمت در سه قدم.\n#پروچارت #هشدار_قیمت")
        published["O-000974"] = mutableListOf(publish("O-000974", "jp-44", slides[0], "carousel", "pro.chart", "cancelled", at = at(20 * 60), count = 3))
        val motion12 = file("/demo/fx-reel-levels.mp4", "motion-12.mp4", "video/mp4", "video", "/demo/fx-reel-levels-poster.webp", size = 110_561, seconds = 6)
        look("O-000975", "PC", pcMedia, "موشن‌گرافی روز: واگرایی در RSI", "موشن‌گرافی دیروز کارگروه.", "موشن‌گرافی **واگرایی در RSI** ساخته و منتشر شد.", 26 * 60, listOf(motion12, file("/demo/fx-reel-levels-poster.webp", "cover-12.jpg", "image/jpeg", "image", size = 8_530)), listOf("pro.chart"), caption = "واگرایی در RSI را در سی ثانیه ببین.\n#پروچارت #RSI", group = "موشن‌گرافی روزانه‌ی پرو-چارت")
        published["O-000975"] = mutableListOf(publish("O-000975", "jp-45", motion12, "reel", "pro.chart", "published", url = "https://www.instagram.com/reel/C9xRsiDv/", at = at(22 * 60), cover = "cover-12.jpg", auto = true))
        // ⟨1.33⟩ the look: two of them are in the lists too (read already, so the «تازه» count stays), so a list shows media cards
        fun listed(ref: String): JsonElement = store.getValue("/deliverables/$ref").second
        val all = listOf(morning, listed("O-000967")) + list() + listed("O-000969") + yesterday + earlier
        store["/deliverables"] = 200 to page(all)
        seen["O-000967"] = at(12)
        seen["O-000969"] = at(20 * 60)
        // The demo's state: the earlier days read (one filed in the archive), and the polished morning report read this morning.
        seen["O-000030"] = at(240)
        seen["O-000028"] = at(60 * 24 + 100)
        seen["O-000026"] = at(3 * 60 * 24 + 30)
        filed["O-000026"] = "AR-000092"
    }

    private fun file(id: String, name: String, mime: String, kind: String, poster: String? = null, size: Long? = null, seconds: Int = 6, w: Int? = null, h: Int? = null) = buildJsonObject {
        put("id", id); put("name", name); put("mime", mime); put("size", size ?: if (kind == "video") 1_200_000 else 90_000); put("sha256", "demo"); put("kind", kind); put("status", "ready")
        if (kind == "video") { put("width", 1080); put("height", 1920); put("duration_s", seconds) } else if (kind == "image") { put("width", w ?: 1080); put("height", h ?: 1350) }
        if (poster != null) put("variants", buildJsonObject { put("poster", poster) })
    }

    private fun publish(
        output: String, job: String, f: JsonObject, kind: String, account: String, state: String, url: String? = null, note: String? = null, at: String,
        cover: String? = null, auto: Boolean = false, scheduledAt: String? = null, comment: String? = null, count: Int = 1,
    ) = buildJsonObject {
        put("auto", auto)
        // ⟨0.20.0⟩ §46 the time it is set for, the word viewers comment, a carousel's files
        put("scheduled_at", scheduledAt?.let(::JsonPrimitive) ?: JsonNull); put("comment", comment?.let(::JsonPrimitive) ?: JsonNull); put("files", count)
        put("job", job); put("output", output); put("file_id", f.str("id")); put("file_name", f.str("name")); put("channel", "instagram"); put("kind", kind)
        put("cover_name", cover?.let(::JsonPrimitive) ?: JsonNull)
        put("account", account); put("state", state); put("url", url?.let(::JsonPrimitive) ?: JsonNull); put("note_fa", note?.let(::JsonPrimitive) ?: JsonNull)
        put("at", at); put("published_at", if (state == "published") JsonPrimitive(at) else JsonNull)
    }

    /** `GET` the panel of an output (an output of no session: `order` null), `POST` the owner's tap. */
    private fun publishRoute(method: String, ref: String, body: JsonObject?): Pair<Int, JsonElement>? {
        val group = groupOutputs[ref]
        val company = store["/deliverables/$ref"]?.second?.str("company")
        val accounts = sessionOutputs[ref] ?: group?.let { listOf(if (company == "PC") "pro.chart" else "tradeyar") }
        if (method == "GET") return 200 to buildJsonObject {
            // a session's output names its session; one of the look's own outputs that is no session's names none
            put("order", if (accounts == null || group != null || (ref in deskSet && ref !in orderOf)) JsonNull else JsonPrimitive(orderOf[ref] ?: SESSION)); put("channel", "instagram")
            put("accounts", JsonArray(accounts.orEmpty().map(::JsonPrimitive))); put("ready", accounts != null)
            put("publishes", JsonArray(published[ref].orEmpty()))
            // ⟨0.19.9⟩ §45 an output that can go out is tapped here; a working group's carries its caption and the owner's standing word
            put("tap", accounts != null || ref in deskSet)
            put("caption", captions[ref]?.let(::JsonPrimitive) ?: if (group != null) JsonPrimitive("حد ضرر را در ۳۰ ثانیه یاد بگیر.\n#تریدیار #حد_ضرر") else JsonNull)
            // ⟨0.20.0⟩ §46 the comment rule the package carries (its `comment.txt`)
            put("comment", if (group != null) buildJsonObject {
                put("keywords", JsonArray(listOf(JsonPrimitive("۳۰")))); put("reply", "این هم آموزش کامل حد ضرر:"); put("link", "https://tradeyar.com/learn/stop-loss")
                put("button", JsonNull); put("public_replies", JsonArray(emptyList()))
            } else JsonNull)
            put("group", if (group != null) JsonPrimitive("pb_1") else JsonNull); put("group_fa", group?.let(::JsonPrimitive) ?: JsonNull)
            put("mode", if (group != null) JsonPrimitive("auto") else JsonNull)
            // ⟨1.31⟩ §49 the account's best hour, only when there is enough data (a time of the sheet)
            put("best", bestHour(if (ref in deskSet || ref in orderOf) company ?: "FX" else if (group != null) "TY" else "FX", accounts?.firstOrNull())?.takeIf { (it["enough"] as? JsonPrimitive)?.booleanOrNull == true } ?: JsonNull)
        }
        if (method != "POST" || accounts == null) return null
        val fileId = body?.str("file_id") ?: return null
        val files = (store["/deliverables/$ref"]?.second?.jsonObject?.get("attachments") as? JsonArray)?.map { it.jsonObject }.orEmpty()
        val f = files.firstOrNull { it.str("id") == fileId } ?: return null
        val kind = body.str("kind") ?: if (f.str("kind") == "video") "reel" else "post"
        val cover = files.firstOrNull { it.str("id") == body.str("cover_file_id") }?.str("name")
        val whenAt = body.str("scheduled_at")
        val word = ((body["comment"] as? JsonObject)?.get("keywords") as? JsonArray)?.firstOrNull()?.let { (it as? JsonPrimitive)?.content }
        val made = publish(
            ref, "jp-${nextJob++}", f, kind, body.str("account")?.removePrefix("@") ?: accounts.first(), if (whenAt != null) "scheduled" else "publishing",
            at = HqClock.now().toString(), cover = cover, scheduledAt = whenAt, comment = word, count = 1 + ((body["file_ids"] as? JsonArray)?.size ?: 0),
        )
        published.getOrPut(ref) { mutableListOf() }.add(0, made)
        return 202 to made
    }

    /** ⟨1.31⟩ §44.5 what the demo's session published, across its outputs, newest first (`OrderReport.publishes`). */
    fun sessionPublishes(order: String = SESSION): JsonArray =
        JsonArray(sessionOutputs.keys.filter { (orderOf[it] ?: SESSION) == order && (it !in deskSet || it in orderOf) }.flatMap { published[it].orEmpty() }.sortedByDescending { it.str("at").orEmpty() })

    // ------------------------------------------------------------------ ⟨1.33⟩ §55.2 the publish desk --
    private fun lite(f: JsonObject) = buildJsonObject { put("id", f.str("id")); put("name", f.str("name")); put("mime", f.str("mime")); put("size", f["size"] ?: JsonPrimitive(0)) }
    private fun companyFa(code: String?) = when (code) { "TY" -> "تریدیار"; "FX" -> "کوینه‌پرو FX"; "PC" -> "پرو-چارت"; else -> "هلدینگ کوینه‌پرو" }

    /**
     * Everything that can go out, is set to go out, or went out (§55.2), of the look's own outputs: an output's video with its cover,
     * else its picture, else its pictures together as a carousel. `ready` has no publication that stands, `queue` is held for its
     * hour or on its way, `done` is what went out, failed or was taken back (a failed or cancelled one is in `ready` again).
     */
    fun desk(company: String?): JsonObject {
        val ready = mutableListOf<JsonObject>()
        val queue = mutableListOf<JsonObject>()
        val done = mutableListOf<JsonObject>()
        for (ref in deskSet) {
            val d = store["/deliverables/$ref"]?.second?.jsonObject ?: continue
            val co = d.str("company")
            if (company != null && co != company) continue
            val files = (d["attachments"] as? JsonArray)?.map { it.jsonObject }.orEmpty()
            val video = files.firstOrNull { it.str("mime").orEmpty().startsWith("video/") }
            val images = files.filter { it.str("mime").orEmpty().startsWith("image/") }
            val main = video ?: images.firstOrNull() ?: continue
            val cover = if (video != null) images.firstOrNull { it.str("name").orEmpty().lowercase().startsWith("cover") } ?: images.singleOrNull() else null
            val group = groupOutputs[ref]
            val accounts = if (ref in noRoute) emptyList() else sessionOutputs[ref] ?: listOf(if (co == "PC") "pro.chart" else "tradeyar")
            val newest = published[ref].orEmpty().firstOrNull()
            fun card(state: String, p: JsonObject?, at: String?) = buildJsonObject {
                put("output", ref); put("title_fa", d.str("title")); put("company", co); put("company_fa", companyFa(co))
                put("order", orderOf[ref]?.let(::JsonPrimitive) ?: JsonNull); put("group_fa", group?.let(::JsonPrimitive) ?: JsonNull)
                put("file", lite(main)); put("cover", cover?.let(::lite) ?: JsonNull)
                put("files", if (video == null && images.size > 1) images.size else 1)
                put("kind", p?.str("kind") ?: if (video != null) "reel" else if (images.size > 1) "carousel" else "post"); put("channel", "instagram")
                put("account", accounts.singleOrNull()?.let(::JsonPrimitive) ?: JsonNull); put("accounts", JsonArray(accounts.map(::JsonPrimitive)))
                put("route_ready", ref !in noRoute); put("caption", captions[ref]?.let(::JsonPrimitive) ?: JsonNull); put("state", state)
                put("publish", p ?: JsonNull)
                put("best", bestHour(co.orEmpty(), accounts.firstOrNull())?.takeIf { (it["enough"] as? JsonPrimitive)?.booleanOrNull == true } ?: JsonNull)
                put("mode", if (group != null) JsonPrimitive("auto") else JsonNull); put("at", at ?: d.str("created_at"))
            }
            when (val state = newest?.str("state")) {
                null -> ready += card("ready", null, null)
                "scheduled", "publishing", "waiting_setup", "waiting_seal" -> queue += card(state, newest, newest.str("scheduled_at") ?: newest.str("at"))
                "failed", "cancelled" -> { done += card(state, newest, newest.str("at")); ready += card("ready", null, null) }
                else -> done += card(state, newest, newest.str("published_at") ?: newest.str("at"))
            }
        }
        return buildJsonObject {
            put("ready", JsonArray(ready.sortedByDescending { it.str("at").orEmpty() }))
            put("queue", JsonArray(queue.sortedBy { it.str("at").orEmpty() }))
            put("done", JsonArray(done.sortedByDescending { it.str("at").orEmpty() }))
        }
    }

    /**
     * ⟨1.31⟩ §51 «لغو»: one no runner has taken is cancelled at once; one IG-Hub holds keeps its state with «در حال لغو» (a second tap
     * answers the same); one that is out, failed or cancelled, or whose file is still on its way, is a `409 not_cancellable`.
     */
    private fun cancel(job: String): Pair<Int, JsonElement> {
        fun refuse(fa: String) = 409 to buildJsonObject { put("code", "not_cancellable"); put("message_fa", fa); put("status", 409); put("title", "Conflict"); put("type", "about:blank") }
        for (list in published.values) {
            val i = list.indexOfFirst { it.str("job") == job }
            if (i < 0) continue
            val p = list[i]
            val state = p.str("state")
            if (state != "scheduled" && state != "publishing") return refuse(
                when (state) { "published" -> "این پست منتشر شده است؛ برداشتنش از خود اینستاگرام انجام میشود."; "cancelled" -> "این انتشار پیش‌تر لغو شده است."; else -> "این انتشار دیگر در صف نیست." },
            )
            if (job in onItsWay) return refuse("فایل این انتشار هنوز در راه IG-Hub است؛ چند لحظه‌ی دیگر میشود لغوش کرد.")
            list[i] = JsonObject(p + if (job in held) mapOf("note_fa" to JsonPrimitive("در حال لغو")) else mapOf("state" to JsonPrimitive("cancelled"), "note_fa" to JsonNull))
            return 200 to list[i]
        }
        return 404 to buildJsonObject { put("code", "not_found"); put("message_fa", "این انتشار پیدا نشد."); put("status", 404); put("title", "Not found"); put("type", "about:blank") }
    }

    /** Answers the ⟨1.7.3⟩ reads and writes, or null to let the rest of the demo answer. */
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?, stepUp: String? = null): Pair<Int, JsonElement>? {
        Regex("^/deliverables/(O-\\d+)/publish$").find(path)?.let { m -> return publishRoute(method, m.groupValues[1], body) }
        Regex("^/publishes/([^/]+)/cancel$").find(path)?.let { m -> return if (method == "POST") cancel(m.groupValues[1]) else null }
        if (method == "GET" && path == "/deliverables") return 200 to page(filter(query).map(::view))
        if (method == "GET" && path.matches(Regex("^/deliverables/O-\\d+$"))) return store[path]?.let { 200 to view(it.second) }
        if (method == "GET" && path == "/inbox/summary") {
            val cur = store[path]?.second?.jsonObject ?: return null
            return 200 to JsonObject(cur + ("deliverables_unseen" to JsonPrimitive(list().count { it.str("ref") !in seen })))
        }
        if (method == "POST" && path == "/deliverables/seen") {
            val refs = body?.get("refs")?.jsonArray?.mapNotNull { it.jsonPrimitive.contentOrNull }.orEmpty()
            val on = body?.get("seen")?.jsonPrimitive?.booleanOrNull ?: true
            var n = 0
            for (r in refs) if (on && r !in seen) { seen[r] = HqClock.now().toString(); n++ } else if (!on && seen.remove(r) != null) n++
            return 200 to buildJsonObject { put("updated", n) }
        }
        // ⟨1.10⟩ §28.1: several filed at once, and deleted for good (the owner's passkey; only an Audit line stays).
        if (method == "POST" && path == "/deliverables/file") {
            val refs = body?.get("refs")?.jsonArray?.mapNotNull { it.jsonPrimitive.contentOrNull }.orEmpty()
            return 200 to buildJsonObject {
                put("records", JsonArray(refs.filter { r -> list().any { it.str("ref") == r } }.map { r ->
                    buildJsonObject { put("ref", r); put("record", filed.getOrPut(r) { "AR-%06d".format(nextRecord++) }) }
                }))
            }
        }
        if (method == "DELETE" && path == "/deliverables") {
            if (stepUp == null) return 403 to buildJsonObject { put("code", "step_up_required"); put("message_fa", "این کار تأیید با گذرکلید لازم دارد."); put("status", 403); put("title", "Forbidden"); put("type", "about:blank") }
            val refs = body?.get("refs")?.jsonArray?.mapNotNull { it.jsonPrimitive.contentOrNull }.orEmpty().toSet()
            val before = list()
            val kept = before.filter { it.str("ref") !in refs }
            store["/deliverables"] = 200 to page(kept)
            for (r in refs) { store.remove("/deliverables/$r"); seen.remove(r); filed.remove(r) }
            return 200 to buildJsonObject { put("deleted", before.size - kept.size) }
        }
        // ⟨1.19⟩ §37.2 one output erased for good: its preview first (nothing changes), then the sealed erase; its work stays.
        Regex("^/deliverables/(O-\\d+)/erase(/preview)?$").find(path)?.let { m ->
            val ref = m.groupValues[1]
            val d = list().firstOrNull { it.str("ref") == ref }?.jsonObject ?: return 404 to buildJsonObject {
                put("code", "not_found"); put("message_fa", "این خروجی پیدا نشد."); put("status", 404); put("title", "Not found"); put("type", "about:blank")
            }
            val files = (d["files"] as? JsonArray)?.size ?: 0
            val counts = buildJsonObject { put("files", files); put("outputs", 1); put("decisions", 0) }
            if (m.groupValues[2].isNotEmpty()) return if (method == "GET") 200 to buildJsonObject {
                put("ref", ref); put("kind", "output"); put("title_fa", d.str("title").orEmpty()); put("counts", counts)
                put("keeps_fa", JsonArray(listOf(JsonPrimitive("کاری که این خروجی از آن آمده میماند؛ قدمش میگوید «خروجی پاک شد»."), JsonPrimitive("یک خط در دفتر حسابرسی، بی متن خروجی."))))
            } else null
            if (method != "POST") return null
            if (stepUp == null) return 403 to buildJsonObject { put("code", "step_up_required"); put("message_fa", "این کار تأیید با گذرکلید لازم دارد."); put("status", 403); put("title", "Forbidden"); put("type", "about:blank") }
            store["/deliverables"] = 200 to page(list().filter { it.str("ref") != ref })
            store.remove("/deliverables/$ref"); seen.remove(ref); filed.remove(ref)
            return 200 to buildJsonObject { put("ref", ref); put("erased", counts) }
        }
        Regex("^/deliverables/(O-\\d+)/file$").find(path)?.let { m ->
            if (method != "POST") return null
            val ref = m.groupValues[1]
            val rec = filed.getOrPut(ref) { "AR-%06d".format(nextRecord++) }
            return 200 to buildJsonObject { put("record", rec) }
        }
        return null
    }

    private fun filter(query: Map<String, String?>): List<JsonElement> {
        val q = DeliverableQuery(
            seen = query["seen"]?.toBooleanStrictOrNull(), category = query["category"], unrated = query["unrated"] == "true",
            company = query["company"], producer = query["producer"], text = query["q"], from = query["from"], to = query["to"],
        )
        val decoded = list().map { com.coinepro.hq.core.net.Api.json.decodeFromJsonElement(com.coinepro.hq.core.net.Deliverable.serializer(), view(it)) }
        val keep = decoded.filter { q.matches(it, it.seenAt) }.map { it.ref }.toSet()
        return list().filter { it.str("ref") in keep }.sortedByDescending { it.str("created_at") }
    }

    /** A deliverable as a ⟨1.7.3⟩ hub serves it. */
    private fun view(e: JsonElement): JsonElement {
        val o = e.jsonObject
        val ref = o.str("ref")
        val producer = (o["producer"] as? JsonObject)?.str("code").orEmpty()
        return JsonObject(o + mapOf(
            "category" to JsonPrimitive(if (producer.endsWith("-SYS")) "report" else "work"),
            "seen_at" to (seen[ref]?.let(::JsonPrimitive) ?: JsonNull),
            "filed_as" to (filed[ref]?.let(::JsonPrimitive) ?: JsonNull),
        ))
    }

    private fun list(): List<JsonElement> = store["/deliverables"]?.second?.let { (it as? JsonObject)?.get("items") ?: it }?.jsonArray.orEmpty()

    private fun page(items: List<JsonElement>) = buildJsonObject { put("items", JsonArray(items)); put("next_cursor", JsonNull) }

    private fun JsonElement.str(k: String): String? = (jsonObject[k] as? JsonPrimitive)?.takeIf { it.isString }?.content

    private fun sys() = buildJsonObject { put("code", "HQ-SYS"); put("company", "HQ"); put("kind", "system"); put("department", JsonNull); put("title_fa", "سیستم") }

    private fun agent(code: String, co: String, dept: String, title: String) =
        buildJsonObject { put("code", code); put("company", co); put("kind", "employee"); put("department", dept); put("title_fa", title) }

    private fun deliverable(
        ref: String, company: String, work: String, producer: JsonObject, title: String, summary: String, body: String, at: String,
        produced: JsonObject = buildJsonObject { put("model", "claude-sonnet-5-5"); put("effort", "medium"); put("label_fa", "Sonnet 5.5 · medium") },
    ) = buildJsonObject {
        put("id", "o-${ref.lowercase()}"); put("ref", ref); put("company", company); put("work_id", "w-${work.lowercase()}"); put("work_ref", work)
        put("producer", producer); put("title", title); put("summary", summary); put("body", body)
        put("attachments", JsonArray(emptyList())); put("evidence", JsonArray(emptyList()))
        put("produced_with", produced); put("usage", JsonObject(emptyMap())); put("rating", JsonNull); put("created_at", at)
    }

    companion object {
        /** The session the demo's workshop outputs belong to (their panel's `order`). */
        const val SESSION = "F-0100"

        /** The morning report exactly as the hub's rule-based writer lays it out (worker/report.py `render`). */
        val MORNING = """
            # گزارش صبحگاهی — شنبه ۲۵ مهر ۱۴۰۵ (2026-10-17)

            > نسخه‌ی قاعده‌محور، بدون مدل: همه‌ی عددها مستقیم از دیتابیس هاب.

            ## صندوق‌ها
            - **کارتابل تصمیم:** 11 مورد در انتظار (ریسک بالا: 1، ریسک متوسط: 4، ریسک کم: 6)
            - **کارتابل خروجی:** 6 خروجی در ۲۴ ساعت گذشته؛ 5 خروجی هنوز امتیاز ندارد
            - **پیام‌ها:** 3 پیام نخوانده
            - **یادآوری کارتابل:** 11 کارت منتظر تو: 7 زیر ۲۴ ساعت، 3 بین ۱ تا ۳ روز، 1 بین ۳ تا ۷ روز، 0 بیش از ۷ روز.
            - **هدررفت دیروز:** 182400 توکن (${'$'}1.84)، 6.2% از کل روز

            ## شرکت‌ها
            | شرکت | تصمیم در انتظار | کار باز | عقب‌افتاده | خروجی تازه | فراخوانی مدل دیروز | توکن دیروز | هزینه‌ی دیروز (USD) | کلید توقف |
            |---|---|---|---|---|---|---|---|---|
            | هلدینگ کوینه‌پرو (HQ) | 3 | 12 | 1 | 2 | 412 | 1840221 | 4.1200 | — |
            | تریدیار (TY) | 4 | 18 | 2 | 1 | 655 | 2210934 | 6.0310 | — |
            | کوینه‌پرو FX (FX) | 3 | 9 | 0 | 2 | 389 | 1301229 | 3.2400 | — |
            | پرو-چارت (PC) | 1 | 7 | 0 | 1 | 120 | 402331 | 0.9900 | فعال |

            ## بودجه‌ها
            - TY · company:TY (month): به 72٪ رسیده

            ## بازیکن‌های ذخیره
            - ChatGPT Plus: 41 فراخوانی این ماه، معادل ${'$'}12.40
            - Google AI Pro: سهمیه‌ی امروز تمام شد

            **کلید توقف فعال:** PC
        """.trimIndent() + "\n"
    }
}
