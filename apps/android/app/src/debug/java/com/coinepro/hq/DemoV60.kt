package com.coinepro.hq

import com.coinepro.hq.core.data.checkDraft
import com.coinepro.hq.core.data.draftChanges
import com.coinepro.hq.core.data.flowDraftOf
import com.coinepro.hq.core.data.foldSearch
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.FlowDef
import com.coinepro.hq.core.net.FlowDefSchedule
import com.coinepro.hq.core.net.FlowOptions
import com.coinepro.hq.core.net.ModelOption
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive

/**
 * Debug builds only: contracts §60 and §61 ⟨1.39⟩, the publish centre and the automations as data, with the day of the D6 mockup (the
 * owner's approval of 2026-11-17): four pages (@zaribsad of TradeYar, @theprochart of Pro-Chart, @ipoxxo.vpn and @dotcoin.me of IG-Hub),
 * fourteen automations on Opus 5.5 at extra-high effort (the owner's order), three pilots switched off.
 *
 * - **Today (Tehran):** @zaribsad's seven stories (two out), DotCoin's twelve slides (three out), Pro-Chart's 09:30 reel out, @ipoxxo.vpn's
 *   10:00 story held (its page closed), four reels set for their hours, three still to be made.
 * - **The archive:** the tree; @zaribsad's page over four days (a set a day, the reels, a story that failed); P-000214, «زی‌کش؛ حریم
 *   خصوصی در بلاک‌چین», whole (its caption, comment words, DM and buttons, the public replies in turn, its files, made by AF-0004 v2);
 *   P-000301, DotCoin's third slide, with its set; a search folds «بلاکچین» to the same hits.
 * - **«منتظر شما»:** Pro-Chart's news reel in «هر بار بپرس», till the end of the day.
 * - **The automations:** every flow's card; AF-0001 «ریلز روزانه‌ی پروچارت» v3 with its versions, its days, its health and its alerts
 *   (all closed); a save makes the next version (checked as the hub checks it); the wizard's kits and a new flow; the week.
 */
internal class V60Demo {
    private val tz: ZoneId = ZoneId.of(OWNER_TZ)
    private val today: LocalDate get() = HqClock.now().atZone(tz).toLocalDate()
    /** [hm] Tehran on the day [d] days from today, as an instant. */
    private fun t(d: Long, hm: String): String = LocalDate.from(today).plusDays(d).atTime(LocalTime.parse(hm)).atZone(tz).toInstant().toString()
    private fun day(d: Long) = today.plusDays(d).toString()

    private fun jo(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(kv.associate { (k, v) -> k to el(v) })
    private fun el(v: Any?): JsonElement = when (v) {
        null -> JsonNull; is JsonElement -> v; is String -> JsonPrimitive(v); is Number -> JsonPrimitive(v); is Boolean -> JsonPrimitive(v)
        is List<*> -> JsonArray(v.map(::el)); is Map<*, *> -> JsonObject(v.entries.associate { (k, x) -> k.toString() to el(x) })
        else -> error("unsupported ${v::class}")
    }
    private fun problem(status: Int, code: String, fa: String, errors: List<Pair<String, String>> = emptyList()) =
        jo("code" to code, "message_fa" to fa, "status" to status, "title" to code, "type" to "about:blank",
            "errors" to errors.map { mapOf("field" to it.first, "message_fa" to it.second) })

    // ---------------------------------------------------------------------------------------------------- the rows --
    private data class Row(
        val ref: String, val company: String, val account: String, val kind: String, var state: String, val d: Long, val hm: String,
        val title: String, val automation: String? = null, val note: String? = null, val set: Triple<Int, Int, String?>? = null,
        val caption: String? = null, val words: List<String> = emptyList(), val storyWord: String? = null, val filesN: Int = 3,
        val url: Boolean = false,
    )

    private val companyFa = mapOf("TY" to "تریدیار", "PC" to "پروچارت", "IG" to "IG-Hub", "FX" to "کوینه‌پرو اف‌ایکس")
    private val companyOf = mapOf("zaribsad" to "TY", "theprochart" to "PC", "ipoxxo.vpn" to "IG", "dotcoin.me" to "IG")

    private val rows: MutableList<Row> = mutableListOf(
        // today
        Row("P-000310", "TY", "zaribsad", "story", "published", 0, "08:30", "۷ استوری امروز", "AF-0005", set = Triple(7, 2, "13:30"), storyWord = "سود", filesN = 7),
        Row("P-000301", "IG", "dotcoin.me", "story", "published", 0, "09:00", "درس امروز: «کیف پول سرد»", "AF-0012", set = Triple(12, 3, "12:30"), storyWord = "سرد", filesN = 12),
        Row("P-000300", "PC", "theprochart", "reel", "published", 0, "09:30", "اندیکاتور RSI در سه دقیقه", "AF-0001", url = true,
            caption = "RSI را در سه دقیقه یاد بگیر: کجا خرید، کجا فروش و کجا صبر.", words = listOf("RSI")),
        Row("P-000302", "IG", "ipoxxo.vpn", "story", "held", 0, "10:00", "لینک کانال تلگرام", "AF-0009", note = "صفحه بسته است؛ به محض باز شدن پیج میرود", storyWord = "لینک", filesN = 1),
        Row("P-000303", "TY", "zaribsad", "reel", "scheduled", 0, "12:00", "کمپین صرافی: هدیه‌ی ثبت‌نام", "AF-0003", caption = "هدیه‌ی ثبت‌نام این هفته؛ کلمه‌ی «هدیه» را کامنت کن.", words = listOf("هدیه")),
        Row("P-000304", "IG", "ipoxxo.vpn", "reel", "scheduled", 0, "12:00", "پروکسی رایگان امروز", "AF-0007"),
        Row("P-000305", "IG", "dotcoin.me", "reel", "scheduled", 0, "13:00", "کیف پول سرد چیست؟", "AF-0010", caption = "کیف پول سرد: کلید شما، نه بلاک‌چین، دارایی را نگه میدارد.", words = listOf("سرد")),
        Row("P-000306", "IG", "ipoxxo.vpn", "reel", "scheduled", 0, "21:30", "سه راه برای اینترنت آزاد", "AF-0008"),
        // yesterday and before (@zaribsad's page)
        Row("P-000214", "TY", "zaribsad", "reel", "published", -1, "19:00", "زی‌کش؛ حریم خصوصی در بلاک‌چین", "AF-0004", url = true,
            caption = "زی‌کش؛ ارزی که تراکنش‌هایش را فقط فرستنده و گیرنده میبینند. در این ریلز: چطور ساخته شد، چه فرقی با بیت‌کوین دارد و قیمت امروزش.\nکلمه‌ی «زی‌کش» را کامنت کن تا لینک ثبت‌نام را بفرستیم.",
            words = listOf("زی‌کش", "زیکش", "zcash")),
        Row("P-000209", "TY", "zaribsad", "story", "published", -1, "08:30", "کلمه‌ی دیروز: «لایه دو»", "AF-0005", set = Triple(7, 7, null), storyWord = "لایه دو", filesN = 7),
        Row("P-000211", "TY", "zaribsad", "reel", "published", -1, "12:00", "آموزش: حد ضرر چیست؟", "AF-0003", url = true, caption = "حد ضرر یعنی خروج پیش از آنکه ضرر بزرگ شود.", words = listOf("ضرر")),
        Row("P-000188", "TY", "zaribsad", "reel", "published", -3, "12:00", "خبر و بازار هفته", "AF-0003", url = true),
        Row("P-000190", "TY", "zaribsad", "story", "failed", -3, "15:30", "استوری ۴", "AF-0005", note = "اینستاگرام عکس را نپذیرفت", filesN = 1),
        Row("P-000192", "TY", "zaribsad", "reel", "published", -3, "19:00", "معرفی ارز: اتریوم", "AF-0004", url = true),
        Row("P-000160", "TY", "zaribsad", "story", "published", -4, "08:30", "کلمه‌ی ۲۲ آبان: «بلاکچین»", "AF-0005", set = Triple(7, 7, null), storyWord = "بلاکچین", filesN = 7),
        Row("P-000162", "TY", "zaribsad", "reel", "published", -5, "12:00", "آموزش: لایه دو چیست؟", "AF-0003", url = true, caption = "لایه دو تراکنش‌ها را روی بلاک‌چین اصلی سبک‌تر میکند."),
        Row("P-000120", "PC", "theprochart", "reel", "published", -7, "19:30", "داده‌ی آن‌چین در نمودار", "AF-0001", url = true, words = listOf("بلاک‌چین")),
        Row("P-000312", "IG", "dotcoin.me", "story", "scheduled", 1, "09:00", "درس فردا: بلاک‌چین به زبان ساده", "AF-0012", set = Triple(12, 0, "09:00"), filesN = 12),
    )

    private fun card(r: Row): JsonObject = jo(
        "ref" to r.ref, "company" to r.company, "company_fa" to companyFa[r.company], "channel" to "instagram", "account" to r.account,
        "kind" to r.kind, "state" to r.state, "state_note_fa" to r.note, "at" to t(r.d, r.hm), "title_fa" to r.title,
        "thumb_file_id" to null, "files_n" to r.filesN, "url" to if (r.url) "https://instagram.com/p/${r.ref.lowercase()}" else null,
        "set_key" to r.set?.let { "${r.account}:${day(r.d)}:O-${r.ref.drop(2)}" },
        "set" to r.set?.let { mapOf("n" to it.first, "done" to it.second, "next_at" to it.third?.let { h -> t(r.d, h) }) },
        "automation" to r.automation, "automation_fa" to r.automation?.let { a -> flows.firstOrNull { it.ref == a }?.titleFa },
    )

    private fun planned(): List<JsonObject> = listOf(
        jo("automation" to "AF-0004", "automation_fa" to "ریلز معرفی ارز ضریب صد", "account" to "zaribsad", "kind" to "reel", "title_fa" to "ریلز معرفی ارز ضریب صد", "build_at" to t(0, "14:00"), "publish_at" to t(0, "19:00"), "state" to "planned"),
        jo("automation" to "AF-0002", "automation_fa" to "ریلز دوم پروچارت", "account" to "theprochart", "kind" to "reel", "title_fa" to "ریلز دوم پروچارت", "build_at" to t(0, "16:30"), "publish_at" to t(0, "19:30"), "state" to "planned"),
        jo("automation" to "AF-0011", "automation_fa" to "ریلز اطلاع‌رسانی دات‌کوین", "account" to "dotcoin.me", "kind" to "reel", "title_fa" to "ریلز اطلاع‌رسانی دات‌کوین", "build_at" to t(0, "15:00"), "publish_at" to t(0, "20:30"), "state" to "planned"),
    )

    private fun todayAnswer(q: Map<String, String?>): JsonObject {
        val acc = q["account"]
        val items = rows.filter { it.d == 0L && (acc == null || it.account == acc) }.sortedBy { it.hm }
        val next = items.filter { it.state == "scheduled" }.minByOrNull { it.hm }
        return jo(
            "day" to day(0), "items" to items.map(::card), "planned" to planned().filter { acc == null || it["account"]?.jsonPrimitive?.content == acc },
            "next" to next?.let(::card), "counts" to mapOf("published" to 6, "scheduled" to 19, "held" to items.count { it.state == "held" }, "failed" to 0),
        )
    }

    private fun tree() = jo("companies" to listOf(
        mapOf("code" to "TY", "name_fa" to "تریدیار", "mark_file_id" to null, "total" to 72, "accounts" to listOf(
            mapOf("channel" to "instagram", "account" to "zaribsad", "avatar_file_id" to null, "total" to 72, "by_kind" to mapOf("reel" to 21, "story" to 51), "automations" to 3))),
        mapOf("code" to "PC", "name_fa" to "پروچارت", "mark_file_id" to null, "total" to 30, "accounts" to listOf(
            mapOf("channel" to "instagram", "account" to "theprochart", "avatar_file_id" to null, "total" to 30, "by_kind" to mapOf("reel" to 28, "story" to 2), "automations" to 2))),
        mapOf("code" to "IG", "name_fa" to "IG-Hub", "mark_file_id" to null, "total" to 9, "accounts" to listOf(
            mapOf("channel" to "instagram", "account" to "ipoxxo.vpn", "avatar_file_id" to null, "total" to 6, "by_kind" to mapOf("reel" to 2, "story" to 4), "automations" to 3),
            mapOf("channel" to "instagram", "account" to "dotcoin.me", "avatar_file_id" to null, "total" to 3, "by_kind" to mapOf("story" to 3), "automations" to 3))),
    ))

    private fun list(q: Map<String, String?>): JsonObject {
        val search = q["q"]?.let(::foldSearch)?.ifEmpty { null }
        val from = q["from"]?.let(LocalDate::parse)
        val to = q["to"]?.let(LocalDate::parse)
        val hits = rows.filter { r ->
            (q["account"] == null || r.account == q["account"]) && (q["company"] == null || r.company == q["company"]) &&
                (q["kind"] == null || r.kind == q["kind"]) && (q["state"] == null || r.state == q["state"]) &&
                (q["automation"] == null || r.automation == q["automation"]) &&
                (from == null || !today.plusDays(r.d).isBefore(from)) && (to == null || !today.plusDays(r.d).isAfter(to))
        }.mapNotNull { r ->
            if (search == null) return@mapNotNull card(r)
            val (match, text) = listOf("title" to r.title, "caption" to (r.caption ?: ""), "word" to (r.words + listOfNotNull(r.storyWord)).joinToString(" "))
                .firstOrNull { foldSearch(it.second).contains(search) } ?: return@mapNotNull null
            JsonObject(card(r) + mapOf("match" to JsonPrimitive(match), "snippet_fa" to JsonPrimitive(text.lines().first().take(80))))
        }.sortedByDescending { it["at"]?.jsonPrimitive?.content }
        return jo("items" to hits, "next" to null)
    }

    private fun item(ref: String): JsonObject? {
        val r = rows.firstOrNull { it.ref == ref } ?: return null
        val files = if (r.set != null) (1..r.set.first).map { mapOf("role" to "slide", "file_id" to "FS-${r.ref}-$it", "name" to "slide_$it.jpg", "mime" to "image/jpeg", "size" to 412_000, "n" to it) }
        else if (r.kind == "reel") listOf(
            mapOf("role" to "video", "file_id" to "FV-${r.ref}", "name" to "reel.mp4", "mime" to "video/mp4", "size" to 24_100_000, "n" to null),
            mapOf("role" to "cover", "file_id" to "FC-${r.ref}", "name" to "cover.jpg", "mime" to "image/jpeg", "size" to 380_000, "n" to null),
            mapOf("role" to "image", "file_id" to "FT-${r.ref}", "name" to "caption.txt", "mime" to "text/plain", "size" to 1_200, "n" to null),
        ) else listOf(mapOf("role" to "image", "file_id" to "FI-${r.ref}", "name" to "story.jpg", "mime" to "image/jpeg", "size" to 390_000, "n" to null))
        val comment = if (r.ref == "P-000214") mapOf(
            "keywords" to r.words, "match" to "contains", "reply" to "سلام! لینک ثبت‌نام با هدیه‌ی خوش‌آمد این‌جاست. اگر سؤالی بود همین‌جا بپرس.",
            "link" to "https://weex.com/register?vipCode=zarib", "buttons" to listOf(
                mapOf("title" to "ثبت‌نام در WEEX", "url" to "https://weex.com/register?vipCode=zarib"),
                mapOf("title" to "ثبت‌نام در LBank", "url" to "https://lbank.com/ref/zarib"),
            ),
            "public_replies" to listOf("لینک رو دایرکت فرستادیم", "دایرکتت رو ببین", "فرستاده شد؛ توی دایرکت"),
        ) else if (r.words.isNotEmpty()) mapOf("keywords" to r.words, "match" to "contains", "reply" to "لینک همین‌جاست.", "link" to null, "buttons" to emptyList<Any>(), "public_replies" to listOf("دایرکت رو ببین"))
        else null
        val set = r.set?.let { s -> (1..s.first).map { n ->
            val hm = if (r.account == "dotcoin.me") DOTCOIN[n - 1] else ZARIB[(n - 1) % ZARIB.size]
            mapOf("ref" to if (n == 3) r.ref else "${r.ref}-$n", "n" to n, "at" to t(r.d, hm), "state" to if (n <= s.second) "published" else "scheduled", "file_id" to null)
        } }
        val pubAt = if (r.state == "published") t(r.d, r.hm) else null
        return jo(
            "ref" to r.ref, "company" to r.company, "company_fa" to companyFa[r.company], "channel" to "instagram", "account" to r.account,
            "kind" to r.kind, "state" to r.state, "state_note_fa" to r.note, "scheduled_at" to t(r.d, r.hm), "published_at" to pubAt,
            "at" to t(r.d, r.hm), "url" to if (r.url) "https://instagram.com/p/${r.ref.lowercase()}" else null, "external_id" to null,
            "title_fa" to r.title, "topic_fa" to if (r.ref == "P-000214") "معرفی ارز" else null, "caption" to r.caption, "comment" to comment,
            "story_word" to r.storyWord, "seo" to null, "files" to files, "thumb_file_id" to null,
            "set_key" to r.set?.let { "${r.account}:${day(r.d)}:O-${r.ref.drop(2)}" }, "set" to set,
            "source" to mapOf("automation" to r.automation, "automation_fa" to r.automation?.let { a -> flows.firstOrNull { it.ref == a }?.titleFa },
                "flow_key" to r.automation?.let { a -> flows.firstOrNull { it.ref == a }?.key }, "version" to if (r.ref == "P-000214") 2 else 1,
                "day" to day(r.d), "order" to null, "work" to null, "output" to "O-${r.ref.drop(2)}", "session" to null, "job_id" to "J-${r.ref}"),
            "insights" to null, "created_at" to t(r.d, "00:30"), "updated_at" to t(r.d, r.hm),
        )
    }

    private fun calendar(q: Map<String, String?>): JsonObject {
        val from = LocalDate.parse(q["from"] ?: day(-30))
        val to = LocalDate.parse(q["to"] ?: day(30))
        val days = generateSequence(from) { it.plusDays(1) }.takeWhile { !it.isAfter(to) }.map { d ->
            val off = d.toEpochDay() - today.toEpochDay()
            when {
                off > 0 -> mapOf("day" to d.toString(), "published" to 0, "scheduled" to if (off == 1L) 12 else 0, "held" to 0, "failed" to 0, "planned" to if (off == 1L) 18 else 30, "accounts" to ACCOUNTS)
                off == 0L -> mapOf("day" to d.toString(), "published" to 6, "scheduled" to 19, "held" to 1, "failed" to 0, "planned" to 4, "accounts" to ACCOUNTS)
                off >= -3 -> mapOf("day" to d.toString(), "published" to listOf(3, 10, 13)[(off + 3).toInt()], "scheduled" to 0, "held" to 0, "failed" to if (off == -3L) 1 else 0, "planned" to 0,
                    "accounts" to listOf("zaribsad", "theprochart", "ipoxxo.vpn").take((off + 5).toInt().coerceIn(1, 3)))
                else -> mapOf("day" to d.toString(), "published" to (1 + Math.floorMod(d.dayOfMonth * 7, 4)), "scheduled" to 0, "held" to 0, "failed" to 0, "planned" to 0, "accounts" to listOf("zaribsad"))
            }
        }.toList()
        return jo("days" to days)
    }

    private var waiting = true
    private fun waitingList() = jo("items" to if (!waiting) emptyList() else listOf(mapOf(
        "id" to "W-0001", "kind" to "publish_ask", "title_fa" to "فدرال رزرو و بازار امروز", "account" to "theprochart", "at" to t(0, "11:05"),
        "deadline_at" to t(0, "23:59"),
        "publication" to mapOf("ref" to "P-000307", "company" to "PC", "company_fa" to "پروچارت", "channel" to "instagram", "account" to "theprochart",
            "kind" to "reel", "state" to "scheduled", "at" to t(0, "19:30"), "title_fa" to "فدرال رزرو و بازار امروز", "files_n" to 3,
            "automation" to null, "automation_fa" to "ریلز خبری پروچارت"),
        "actions" to listOf(mapOf("key" to "publish", "label_fa" to "انتشار ۱۹:۳۰", "primary" to true), mapOf("key" to "skip", "label_fa" to "این بار نه", "primary" to false)),
    )))

    // ----------------------------------------------------------------------------------------------- the automations --
    private data class F(
        val ref: String, val key: String, val company: String, val account: String, var titleFa: String, val kit: String, val kitFa: String,
        val kind: String, var hours: List<String?>, var trigger: String, var sameDay: Boolean, var cap: Double, var state: String = "on",
        var stories: List<String> = emptyList(), var cycle: List<String> = emptyList(), var wordMode: String = "fresh", var word: String? = null,
        var bestWeek: Boolean = false, var days: List<Int> = listOf(0, 1, 2, 3, 4, 5, 6), val start: String = "2026-11-14",
        var model: String = OPUS, var effort: String = "xhigh", var note: String? = null, var version: Int = 1,
        val health: Pair<String, String> = "ok" to "همه چیز سر وقت", val todayCost: Double = 0.0, val month: Double = 0.0,
        var pausedUntil: String? = null, val pair: String? = null,
    )

    private val flows: MutableList<F> = mutableListOf(
        F("AF-0001", "prochart_reels", "PC", "theprochart", "ریلز روزانه‌ی پروچارت", "prochart-reels", "ریلز آموزشی پروچارت", "reel",
            listOf("09:30", "14:00", "19:30", null), "00:30", true, 10.0, bestWeek = true, version = 3, todayCost = 4.1, month = 15.6),
        F("AF-0002", "prochart_reels_2", "PC", "theprochart", "ریلز دوم پروچارت", "prochart-reels", "ریلز آموزشی پروچارت", "reel",
            listOf("19:30", "09:30", "14:00", null), "16:30", true, 10.0, bestWeek = true, pair = "prochart_reels", month = 12.2),
        F("AF-0003", "zaribsad_noon", "TY", "zaribsad", "ریلز چرخشی ضریب صد", "zaribsad-noon", "ریلز چرخشی", "reel",
            listOf("12:00", "12:00", "12:00", "12:00"), "07:00", true, 100.0, cycle = listOf("آموزش", "کمپین صرافی", "خبر و بازار"), start = "2026-11-16", todayCost = 6.2, month = 41.0),
        F("AF-0004", "zaribsad_coin", "TY", "zaribsad", "ریلز معرفی ارز ضریب صد", "zaribsad-coin", "ریلز معرفی ارز", "reel",
            listOf("19:00", "19:00", "19:00", "19:00"), "14:00", true, 100.0, version = 2, month = 58.0),
        F("AF-0005", "zaribsad_stories", "TY", "zaribsad", "استوری‌های روزانه‌ی ضریب صد", "zaribsad-stories", "استوری روزانه", "stories",
            listOf("08:30"), "06:00", true, 60.0, stories = ZARIB, todayCost = 3.9, month = 19.5),
        F("AF-0006", "zaribsad_fabletest", "TY", "", "آزمایش فیبل ۵.۲: ریلز زی‌کش (منتشر نمی‌شود)", "zaribsad-coin", "ریلز معرفی ارز", "reel",
            listOf("12:00"), "08:00", true, 100.0, state = "off"),
        F("AF-0007", "ipoxxo_reels", "IG", "ipoxxo.vpn", "ریلز اول آی‌پی‌اکسو", "ipoxxo-reels", "ریلز آی‌پی‌اکسو", "reel",
            listOf("12:00", "12:00", "12:00", "12:00"), "21:00", false, 100.0, start = "2026-11-16", month = 8.4),
        F("AF-0008", "ipoxxo_reels_2", "IG", "ipoxxo.vpn", "ریلز دوم آی‌پی‌اکسو", "ipoxxo-reels", "ریلز آی‌پی‌اکسو", "reel",
            listOf("21:30", "19:30", "23:00", null), "23:30", false, 100.0, bestWeek = true, start = "2026-11-16", month = 7.9),
        F("AF-0009", "ipoxxo_stories", "IG", "ipoxxo.vpn", "استوری‌های روزانه‌ی آی‌پی‌اکسو", "ipoxxo-stories", "استوری روزانه", "stories",
            listOf("10:00"), "02:30", true, 40.0, stories = listOf("10:00", "16:30", "21:00"), wordMode = "fixed", word = "لینک", start = "2026-11-16",
            health = "warn" to "صفحه بسته است؛ ۱ استوری نگه‌داشته", month = 5.7),
        F("AF-0010", "dotcoin_reels", "IG", "dotcoin.me", "ریلز آموزشی دات‌کوین", "dotcoin-reels", "ریلز آموزشی", "reel",
            listOf("13:00", "13:00", "13:00", "13:00"), "00:30", true, 100.0, cycle = listOf("آموزشی"), start = "2026-11-17", todayCost = 10.6, month = 10.6),
        F("AF-0011", "dotcoin_reels_2", "IG", "dotcoin.me", "ریلز اطلاع‌رسانی دات‌کوین", "dotcoin-reels", "ریلز خبری", "reel",
            listOf("20:30", "20:30", "20:30", "20:30"), "15:00", true, 100.0, cycle = listOf("اطلاع‌رسانی"), start = "2026-11-17"),
        F("AF-0012", "dotcoin_stories", "IG", "dotcoin.me", "۱۲ اسلاید روزانه‌ی دات‌کوین", "dotcoin-stories", "۱۲ اسلاید استوری", "stories",
            listOf("09:00"), "07:00", true, 60.0, stories = DOTCOIN, start = "2026-11-17", todayCost = 2.1, month = 2.1),
        F("AF-0013", "dotcoin_pilot", "IG", "", "نمونه‌ی ۱۰ ثانیه‌ای دات‌کوین برای مدیر کل (منتشر نمی‌شود)", "dotcoin-reels", "ریلز آموزشی", "reel",
            listOf("12:00"), "08:00", true, 100.0, state = "off"),
        F("AF-0014", "ipoxxo_pilot", "IG", "", "نمونه‌ی آی‌پی‌اکسو (منتشر نمی‌شود)", "ipoxxo-reels", "ریلز آی‌پی‌اکسو", "reel",
            listOf("12:00"), "08:00", true, 100.0, state = "off"),
    )

    private fun hourOf(f: F, d: LocalDate): String? {
        if (f.kind == "stories") return f.stories.minOrNull()
        val weeks = Math.floorDiv(d.toEpochDay() - LocalDate.parse(f.start).toEpochDay(), 7L)
        return f.hours.getOrNull(Math.floorMod(weeks, f.hours.size.toLong()).toInt()) ?: "19:30"
    }

    private fun nextOf(f: F): Map<String, Any?>? {
        if (f.state != "on" || f.account.isBlank()) return null
        val now = HqClock.now()
        for (k in 0L..7L) {
            val d = today.plusDays(k)
            val h = hourOf(f, d) ?: return null
            val pub = d.atTime(LocalTime.parse(h)).atZone(tz).toInstant()
            if (pub.isAfter(now)) {
                val buildDay = if (f.sameDay) d else d.minusDays(1)
                return mapOf("build_at" to buildDay.atTime(LocalTime.parse(f.trigger)).atZone(tz).toInstant().toString(), "publish_at" to pub.toString(),
                    "kind_fa" to f.cycle.takeIf { it.size > 1 }?.let { it[Math.floorMod(d.toEpochDay(), it.size.toLong()).toInt()] })
            }
        }
        return null
    }

    private fun def(f: F): JsonObject = jo(
        "ref" to f.ref, "key" to f.key, "company" to f.company, "company_fa" to companyFa[f.company], "channel" to "instagram", "account" to f.account,
        "title_fa" to f.titleFa, "kit" to f.kit, "kit_fa" to f.kitFa, "kind" to f.kind, "state" to f.state, "paused_until" to f.pausedUntil,
        "schedule" to mapOf("hours" to f.hours, "best_week" to f.bestWeek, "days" to f.days, "stories" to f.stories, "trigger_at" to f.trigger,
            "same_day" to f.sameDay, "start" to f.start, "when_fa" to ""),
        "model" to f.model, "model_fa" to if (f.model == OPUS) "Opus 5.5" else "Fable 5.2", "effort" to f.effort,
        "budget" to mapOf("usd_cap" to f.cap, "month_estimate_usd" to f.cap * 30, "envelope_usd" to null, "envelope_left_usd" to null, "over_envelope" to false),
        "cycle" to f.cycle, "story_word_mode" to f.wordMode, "story_word" to f.word, "note_fa" to f.note, "pair" to f.pair, "recipe" to null,
        "version" to f.version, "next" to nextOf(f),
        "today" to mapOf("runs" to if (f.todayCost > 0) 1 else 0, "published" to rows.count { it.d == 0L && it.automation == f.ref && it.state == "published" }, "cost_usd" to f.todayCost),
        "month_cost_usd" to f.month, "health" to mapOf("state" to f.health.first, "note_fa" to f.health.second), "alerts_open" to if (f.health.first == "ok") 0 else 1,
        "legacy_ref" to "N8:${f.key}", "created_at" to t(-3, "10:00"), "updated_at" to t(0, "08:00"),
    )

    private val options get() = jo(
        "models" to listOf(mapOf("id" to OPUS, "name_fa" to "Opus 5.5", "efforts" to listOf("high", "xhigh", "max")), mapOf("id" to FABLE, "name_fa" to "Fable 5.2", "efforts" to listOf("high", "xhigh", "max"))),
        "efforts" to listOf("high", "xhigh", "max"), "usd_cap" to mapOf("min" to 1, "max" to 500), "stories_max" to 15, "cycle_max" to 7, "note_max" to 2000,
        "kits" to listOf(
            mapOf("key" to "dotcoin-reels", "title_fa" to "ریلز آموزشی", "about_fa" to "موضوع از بانک، متن و کاور با ChatGPT، ویدیو در کارگاه", "kinds" to listOf("reel"), "avg_usd" to 10, "avg_minutes" to 80, "used_on" to listOf("dotcoin.me")),
            mapOf("key" to "dotcoin-stories", "title_fa" to "۱۲ اسلاید استوری", "about_fa" to "یک درس در ۱۲ اسلاید، هر ساعت یکی، کلمه‌ی ریپلای", "kinds" to listOf("stories"), "avg_usd" to 6, "avg_minutes" to 40, "used_on" to listOf("dotcoin.me")),
            mapOf("key" to "dotcoin-news", "title_fa" to "ریلز خبری", "about_fa" to "خبر همان روز؛ همان روز ساخته میشود", "kinds" to listOf("reel"), "avg_usd" to 9, "avg_minutes" to 70, "used_on" to listOf("dotcoin.me")),
            mapOf("key" to "zaribsad-coin", "title_fa" to "ریلز معرفی ارز", "about_fa" to "ارز، ساخت، مزیت‌ها، قیمت امروز و دعوت به صرافی", "kinds" to listOf("reel"), "avg_usd" to 14, "avg_minutes" to 120, "used_on" to listOf("zaribsad")),
            mapOf("key" to "zaribsad-noon", "title_fa" to "ریلز چرخشی", "about_fa" to "هر روز یک نوع: آموزش، کمپین، خبر و بازار", "kinds" to listOf("reel"), "avg_usd" to 8, "avg_minutes" to 90, "used_on" to listOf("zaribsad")),
            mapOf("key" to "zaribsad-stories", "title_fa" to "استوری روزانه", "about_fa" to "چند استوری تصویری، ساعت هر کدام جدا", "kinds" to listOf("stories"), "avg_usd" to 4, "avg_minutes" to 30, "used_on" to listOf("zaribsad", "ipoxxo.vpn")),
        ),
    )

    private val versions: MutableMap<String, MutableList<JsonObject>> = mutableMapOf(
        "AF-0001" to mutableListOf(
            jo("version" to 3, "at" to t(-1, "21:10"), "by_fa" to "تو", "note_fa" to null, "changes" to listOf(mapOf("field" to "model", "label_fa" to "مدل", "before_fa" to "Fable 5.2", "after_fa" to "Opus 5.5")), "body" to null),
            jo("version" to 2, "at" to t(-2, "18:20"), "by_fa" to "Claude سرور هاب", "note_fa" to "رندر ۴۵ ثانیه‌ای بیش از ۵ دلار شد", "changes" to listOf(mapOf("field" to "usd_cap", "label_fa" to "هشدار هزینه‌ی روز", "before_fa" to "$5", "after_fa" to "$10")),
                "body" to mapOf("usd_cap" to 10, "model" to FABLE)),
            jo("version" to 1, "at" to t(-3, "10:00"), "by_fa" to "ساخته شد", "note_fa" to "از روند کدی هاب؛ همان ساعت‌ها و همان رفتار", "changes" to emptyList<Any>(), "body" to mapOf("usd_cap" to 5, "model" to FABLE)),
        ),
    )

    private fun runs(ref: String) = jo("items" to if (ref != "AF-0001") emptyList() else listOf(
        mapOf("run" to "F-0040", "day" to day(0), "state" to "done", "topic_fa" to "اندیکاتور RSI در سه دقیقه", "started_at" to t(0, "00:30"), "ended_at" to t(0, "01:38"), "cost_usd" to 4.1,
            "publications" to listOfNotNull(rows.firstOrNull { it.ref == "P-000300" }?.let(::card)), "note_fa" to "منتشر شد"),
        mapOf("run" to "F-0036", "day" to day(-1), "state" to "done", "topic_fa" to "حمایت و مقاومت با یک ابزار", "started_at" to t(-1, "00:30"), "ended_at" to t(-1, "01:41"), "cost_usd" to 4.5,
            "publications" to emptyList<Any>(), "note_fa" to "منتشر شد · پربازدیدترین ساعت"),
        mapOf("run" to "F-0031", "day" to day(-2), "state" to "skipped", "topic_fa" to null, "started_at" to null, "ended_at" to null, "cost_usd" to 0, "publications" to emptyList<Any>(), "note_fa" to "این نوبت را رد کردی"),
        mapOf("run" to "F-0027", "day" to day(-3), "state" to "done", "topic_fa" to "۳ الگوی شمعی برای شروع", "started_at" to t(-3, "00:30"), "ended_at" to t(-3, "20:05"), "cost_usd" to 7.0,
            "publications" to emptyList<Any>(), "note_fa" to "رندر در کارگاه ایستاد؛ دوباره ساخته شد و ۲۰:۱۰ رفت"),
    ), "next" to null)

    private fun health(ref: String): JsonObject {
        val f = flows.first { it.ref == ref }
        return jo("state" to f.health.first, "note_fa" to f.health.second, "last_run" to (runs(ref)["items"] as JsonArray).firstOrNull(),
            "success_30d" to mapOf("ok" to 3, "all" to 3), "cost" to mapOf("today" to f.todayCost, "month" to f.month), "next" to nextOf(f),
            "alerts" to if (ref != "AF-0001") emptyList() else listOf(
                mapOf("kind" to "run_failed", "state" to "closed", "opened_at" to t(-3, "18:02"), "closed_at" to t(-3, "20:10"), "note_fa" to "رندر در کارگاه ایستاد؛ خودش دوباره ساخت و ۲۰:۱۰ رفت"),
                mapOf("kind" to "login_expired", "state" to "closed", "opened_at" to t(-2, "09:12"), "closed_at" to t(-2, "09:40"), "note_fa" to "ورود ChatGPT منقضی شد؛ تیم فنی دوباره وارد شد"),
                mapOf("kind" to "clock_missed", "state" to "closed", "opened_at" to t(-2, "13:00"), "closed_at" to t(-2, "13:10"), "note_fa" to "تیک ساعت ۱۰ دقیقه نیامد؛ پشتیبان هاب سر وقت اجرا کرد"),
            ))
    }

    private fun week(): JsonObject {
        val sat = today.minusDays(((today.dayOfWeek.value + 1) % 7).toLong())
        return jo("from" to sat.toString(), "to" to sat.plusDays(6).toString(), "totals" to mapOf("runs" to 44, "published" to 41, "cost_usd" to 121),
            "by_day" to (0L..6L).map { i -> val d = sat.plusDays(i); val off = d.toEpochDay() - today.toEpochDay()
                mapOf("day" to d.toString(), "published" to if (off > 0) 0 else listOf(3, 10, 13, 6, 0, 0, 0)[i.toInt()], "planned" to if (off > 0) 30 else 0) },
            "accounts" to listOf(
                mapOf("company" to "TY", "company_fa" to "تریدیار", "account" to "zaribsad", "runs" to 26, "published" to 24, "cost_usd" to 64, "flows" to 3, "best" to card(rows.first { it.ref == "P-000214" })),
                mapOf("company" to "PC", "company_fa" to "پروچارت", "account" to "theprochart", "runs" to 7, "published" to 6, "cost_usd" to 27, "flows" to 2, "best" to card(rows.first { it.ref == "P-000300" })),
                mapOf("company" to "IG", "company_fa" to "IG-Hub", "account" to "ipoxxo.vpn", "runs" to 9, "published" to 8, "cost_usd" to 22, "flows" to 3, "best" to null),
                mapOf("company" to "IG", "company_fa" to "IG-Hub", "account" to "dotcoin.me", "runs" to 2, "published" to 3, "cost_usd" to 8, "flows" to 3, "best" to null),
            ))
    }

    private fun graph(): JsonObject = jo(
        "lanes" to listOf("n8n", "hub", "chatgpt", "voice", "workshop", "ighub"),
        "nodes" to listOf(
            mapOf("key" to "clock", "title_fa" to "ساعت هاب", "kind" to "n8n", "helper" to "code", "lane" to "hub", "col" to 0, "row" to 0, "note_fa" to "شروع ساخت", "model" to null),
            mapOf("key" to "topic", "title_fa" to "خبر روز", "kind" to "workshop", "helper" to "code", "lane" to "hub", "col" to 1, "row" to 0, "note_fa" to "از بانک موضوع", "model" to null),
            mapOf("key" to "script", "title_fa" to "متن و کاور", "kind" to "workshop", "helper" to "gpt", "lane" to "chatgpt", "col" to 2, "row" to 0, "note_fa" to "ChatGPT", "model" to null),
            mapOf("key" to "voice", "title_fa" to "گوینده", "kind" to "workshop", "helper" to "gemini", "lane" to "voice", "col" to 3, "row" to 0, "note_fa" to "AI Studio", "model" to null),
            mapOf("key" to "render", "title_fa" to "ویدیو", "kind" to "workshop", "helper" to "workshop", "lane" to "workshop", "col" to 4, "row" to 0, "note_fa" to "کارگاه", "model" to OPUS),
            mapOf("key" to "publish", "title_fa" to "انتشار", "kind" to "publish", "helper" to "ighub", "lane" to "ighub", "col" to 5, "row" to 0, "note_fa" to "IG-Hub", "model" to null),
        ),
        "edges" to listOf(mapOf("source" to "clock", "target" to "topic", "label_fa" to ""), mapOf("source" to "topic", "target" to "script", "label_fa" to ""),
            mapOf("source" to "script", "target" to "voice", "label_fa" to ""), mapOf("source" to "voice", "target" to "render", "label_fa" to ""),
            mapOf("source" to "render", "target" to "publish", "label_fa" to "")),
    )

    private fun patch(f: F, body: JsonObject): Pair<Int, JsonElement> {
        val before = Api.json.decodeFromJsonElement(FlowDef.serializer(), def(f))
        body["schedule"]?.let { s -> s as JsonObject
            s["hours"]?.let { f.hours = it.jsonArray.map { h -> (h as? JsonPrimitive)?.takeIf { p -> p.isString }?.content } }
            s["best_week"]?.let { f.bestWeek = it.jsonPrimitive.boolean }
            s["days"]?.let { f.days = it.jsonArray.map { d -> d.jsonPrimitive.int } }
            s["stories"]?.let { f.stories = it.jsonArray.map { h -> h.jsonPrimitive.content } }
            s["trigger_at"]?.let { f.trigger = it.jsonPrimitive.content }
            s["same_day"]?.let { f.sameDay = it.jsonPrimitive.boolean }
        }
        body["model"]?.let { f.model = it.jsonPrimitive.content }
        body["effort"]?.let { f.effort = it.jsonPrimitive.content }
        body["usd_cap"]?.let { f.cap = it.jsonPrimitive.double }
        body["cycle"]?.let { f.cycle = it.jsonArray.map { c -> c.jsonPrimitive.content } }
        body["story_word_mode"]?.let { f.wordMode = it.jsonPrimitive.content }
        body["story_word"]?.let { f.word = (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content }
        body["note_fa"]?.let { f.note = (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content }
        val after = Api.json.decodeFromJsonElement(FlowDef.serializer(), def(f))
        val o = Api.json.decodeFromJsonElement(FlowOptions.serializer(), options)
        val errs = checkDraft(flowDraftOf(after), after.kind, o)
        if (errs.isNotEmpty()) {
            // the hub refuses the whole save: put it back
            restore(f, before)
            return 422 to problem(422, "invalid_flow", "بعضی از تنظیم‌ها درست نیست.", errs.map { it.field to it.messageFa })
        }
        f.version += 1
        val changes = draftChanges(flowDraftOf(before), flowDraftOf(after)) { if (it == OPUS) "Opus 5.5" else "Fable 5.2" }
        versions.getOrPut(f.ref) { mutableListOf() }.add(0, jo("version" to f.version, "at" to HqClock.now().toString(), "by_fa" to "تو",
            "note_fa" to body["note_change_fa"]?.jsonPrimitive?.content, "changes" to changes.map { mapOf("field" to it.field, "label_fa" to it.labelFa, "before_fa" to it.beforeFa, "after_fa" to it.afterFa) }, "body" to null))
        return 200 to def(f)
    }

    private fun restore(f: F, d: FlowDef) {
        f.hours = d.schedule.hours; f.bestWeek = d.schedule.bestWeek; f.days = d.schedule.days; f.stories = d.schedule.stories
        f.trigger = d.schedule.triggerAt; f.sameDay = d.schedule.sameDay; f.model = d.model; f.effort = d.effort; f.cap = d.budget.usdCap
        f.cycle = d.cycle; f.wordMode = d.storyWordMode; f.word = d.storyWord; f.note = d.noteFa
    }

    @Suppress("CyclomaticComplexMethod")
    fun handle(method: String, path: String, q: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        if (path.startsWith("/publications")) return when {
            path == "/publications/today" -> 200 to todayAnswer(q)
            path == "/publications/tree" -> 200 to tree()
            path == "/publications/calendar" -> 200 to calendar(q)
            path == "/publications/waiting" -> 200 to waitingList()
            path.startsWith("/publications/waiting/") && method == "POST" -> { waiting = false; 200 to jo("ok" to true) }
            path == "/publications" -> 200 to list(q)
            else -> Regex("^/publications/(P-\\d+)$").find(path)?.let { m -> item(m.groupValues[1])?.let { 200 to it } }
                ?: (404 to problem(404, "not_found", "این انتشار پیدا نشد."))
        }
        if (path == "/automations/week") return 200 to week()
        if (Regex("^/automations/kits/[^/]+/graph$").matches(path)) return 200 to graph()
        if (path == "/automations/kits/request" && method == "POST") return 200 to jo("order" to "F-0041", "title_fa" to "کیت تازه برای ${body?.get("account")?.jsonPrimitive?.content ?: "پیج"}")
        if (!path.startsWith("/automations/flows")) return null
        if (path == "/automations/flows" && method == "GET") {
            val acc = q["account"]; val co = q["company"]
            val items = flows.filter { (acc == null || it.account == acc) && (co == null || it.company == co) }.map(::def)
            return 200 to jo("items" to items, "health" to listOf(
                mapOf("key" to "n8n", "state" to "ok", "note_fa" to "ساعت هاب سر وقت است"), mapOf("key" to "ighub", "state" to "ok", "note_fa" to "IG-Hub جواب میدهد"),
                mapOf("key" to "workshop", "state" to "ok", "note_fa" to "کارگاه آماده است"), mapOf("key" to "helpers_browser", "state" to "ok", "note_fa" to "ChatGPT وارد است"),
                mapOf("key" to "aistudio", "state" to "warn", "note_fa" to "AI Studio از حساب بیرون افتاده؛ گوینده‌ی ریلزها یک ورود تو در مرورگر هاب میخواهد"),
            ), "today" to mapOf("runs" to 7, "published" to 6, "cost_usd" to 18.4))
        }
        if (path == "/automations/flows" && method == "POST") {
            val b = body ?: JsonObject(emptyMap())
            val n = flows.size + 1
            val f = F("AF-%04d".format(n), "new_$n", companyOf[b["account"]?.jsonPrimitive?.content] ?: "IG", b["account"]?.jsonPrimitive?.content ?: "dotcoin.me",
                b["title_fa"]?.jsonPrimitive?.content ?: "اتوماسیون تازه", b["kit"]?.jsonPrimitive?.content ?: "dotcoin-news", "ریلز خبری", "reel",
                listOf("17:00"), "15:30", true, b["usd_cap"]?.jsonPrimitive?.double ?: 15.0, start = day(1))
            flows += f
            return 200 to def(f)
        }
        if (path == "/automations/flows/options") return 200 to options
        val m = Regex("^/automations/flows/(AF-\\d{4})(?:/(.+))?$").find(path) ?: return 404 to problem(404, "not_found", "این اتوماسیون پیدا نشد.")
        val f = flows.firstOrNull { it.ref == m.groupValues[1] } ?: return 404 to problem(404, "not_found", "این اتوماسیون پیدا نشد.")
        return when (m.groupValues[2]) {
            "" -> if (method == "PATCH") patch(f, body ?: JsonObject(emptyMap())) else 200 to def(f)
            "state" -> { f.state = body?.get("state")?.jsonPrimitive?.content ?: f.state; 200 to def(f) }
            "pause" -> { f.state = "paused"; f.pausedUntil = body?.get("until")?.jsonPrimitive?.content; 200 to def(f) }
            "skip" -> 200 to def(f)
            "run-now" -> 200 to jo("run" to mapOf("ref" to "F-0042", "at" to HqClock.now().toString(), "state" to "running", "topic_fa" to null, "note_fa" to "ساخت شروع شد", "cost_usd" to null))
            "versions" -> 200 to JsonArray(versions[f.ref] ?: listOf(jo("version" to f.version, "at" to t(-3, "10:00"), "by_fa" to "ساخته شد", "note_fa" to "از روند کدی هاب", "changes" to emptyList<Any>(), "body" to null)))
            "rollback" -> { f.version += 1; 200 to def(f) }
            "runs" -> 200 to runs(f.ref)
            "health" -> 200 to health(f.ref)
            "graph" -> 200 to graph()
            else -> 404 to problem(404, "not_found", "Not Found")
        }
    }

    private companion object {
        const val OPUS = "claude-opus-5-5"
        const val FABLE = "claude-fable-5-2"
        val ZARIB = listOf("08:30", "10:30", "13:30", "15:30", "17:30", "20:30", "22:30")
        val DOTCOIN = listOf("09:00", "10:15", "11:30", "12:30", "14:00", "15:00", "16:00", "17:15", "18:30", "19:30", "21:30", "23:00")
        val ACCOUNTS = listOf("zaribsad", "theprochart", "ipoxxo.vpn", "dotcoin.me")
    }
}
