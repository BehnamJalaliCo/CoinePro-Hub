package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import java.time.LocalDate
import java.time.ZoneId
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * Debug builds only: contract §31 ⟨1.13⟩, growth. Deterministic (every day from [HqClock]), so the screenshots are the same on any machine.
 *
 * - **Insights (§31.1):** twelve published reels ranked by views: the best hour, length, speaker and pattern, three hooks, three lessons.
 * - **Kits (§31.2):** a channel-media company and a newsletter brand; the preview and the creation answer what is left to connect.
 * - **Newsletter (§31.3):** TradeYar (a list under and one over its limit, a sent campaign with A/B subjects, a scheduled one), FX (one list).
 * - **SEO (§31.4):** three keywords with 30 days of ranks, two competitors with followers and new pages.
 * - **Campaign calendar (§31.5):** lines, a newsletter, an ad and a campaign this week, one conflict and a holiday; campaigns add, change, delete.
 * - **Ads (§31.6):** TradeYar's Google account with one running and one paused campaign (paused by a rule), two rules; resume and cap raising.
 * - **Automations (§31.7):** one on, one proposed; the compiler reads a sentence by rules and refuses what is outside the allow-list.
 */
internal class V31Demo {
    private val now = HqClock.now()
    private val tehran = ZoneId.of("Asia/Tehran")
    private val today: LocalDate = LocalDate.ofInstant(now, tehran)
    private fun day(off: Long): String = today.plusDays(off).toString()
    private fun at(off: Long, h: Int, m: Int = 0): String = today.plusDays(off).atTime(h, m).atZone(tehran).toInstant().toString()
    private val last30 = (29 downTo 0L).map { day(-it) }

    private val kits = listOf(
        kit("media_channel", "شرکت رسانه‌ی کانال‌محور", "یک شرکت تازه که هر روز برای کانال‌هایش (اینستاگرام، تلگرام و سایت) محتوا میسازد و منتشر میکند، با تیم محتوا و عددهای واقعی.",
            listOf("content"), listOf(kl("instagram_reel", "instagram_reel", "ریلز آموزشی"), kl("telegram_post", "telegram_post", "پست روزانه‌ی کانال"), kl("site_article", "site_article", "مقاله‌ی هفتگی")),
            listOf("reach", "followers", "published"), listOf("instagram", "telegram", "search_console")),
        kit("newsletter_brand", "برند خبرنامه‌ای", "شرکتی که مخاطبش را در فهرست ایمیل خودش نگه میدارد و هفته‌ای یک خبرنامه با مقاله‌ی سایت میفرستد.",
            listOf("content"), listOf(kl("site_article", "site_article", "مقاله‌ی هفتگی"), kl("newsletter", "newsletter", "خبرنامه‌ی هفتگی")),
            listOf("subscribers", "opens", "clicks"), listOf("search_console", "ga4")),
    )

    private val newsletters = linkedMapOf(
        "TY" to jo(
            "lists" to ja(listOf(jo("id" to 1, "name" to "مشترکان خبرنامه‌ی تریدیار", "subscribers" to 1840, "size_limit" to 2000), jo("id" to 2, "name" to "کاربران آزمایشی", "subscribers" to 5200, "size_limit" to 2000))),
            "campaigns" to ja(listOf(
                jo("id" to 11, "list" to 1, "subject" to "خلاصه‌ی بازار طلا در هفته‌ای که گذشت", "subject_b" to "هفته‌ی طلا در ۵ دقیقه", "state" to "sent", "scheduled_at" to at(-3, 7), "sent" to 1790, "opens" to 742, "clicks" to 188, "body_md" to "خلاصه‌ی هفته."),
                jo("id" to 12, "list" to 1, "subject" to "سه نکته برای معامله‌ی هفته‌ی بعد", "subject_b" to null, "state" to "scheduled", "scheduled_at" to at(2, 7), "sent" to null, "opens" to null, "clicks" to null, "body_md" to "سه نکته."),
            )),
        ),
        "FX" to jo("lists" to ja(listOf(jo("id" to 3, "name" to "خبرنامه‌ی کوینه‌پرو FX", "subscribers" to 920, "size_limit" to 2000))), "campaigns" to ja(emptyList())),
        "PC" to jo("lists" to ja(emptyList()), "campaigns" to ja(emptyList())),
    )
    private var nlSeq = 20

    private val keywords = mutableListOf(
        jo("id" to 1, "company" to "TY", "phrase" to "سیگنال رایگان طلا", "site" to "tradeyar.example", "target_url" to "https://tradeyar.example/gold-signal", "state" to "on"),
        jo("id" to 2, "company" to "TY", "phrase" to "آموزش تحلیل تکنیکال", "site" to "tradeyar.example", "target_url" to null, "state" to "on"),
        jo("id" to 3, "company" to "FX", "phrase" to "قیمت لحظه‌ای طلا", "site" to "coinepro-fx.example", "target_url" to "https://coinepro-fx.example/gold", "state" to "on"),
    )
    private val competitors = mutableListOf(
        jo("id" to 1, "company" to "TY", "name_fa" to "سیگنال‌یار", "site" to "signalyar.example", "instagram" to "signalyar", "youtube" to null, "telegram" to "signalyar_ch", "state" to "on"),
        jo("id" to 2, "company" to "TY", "name_fa" to "بورس‌نما", "site" to "boursnama.example", "instagram" to null, "youtube" to "boursnama", "telegram" to null, "state" to "on"),
        jo("id" to 3, "company" to "FX", "name_fa" to "طلاسنج", "site" to "talasanj.example", "instagram" to "talasanj", "youtube" to null, "telegram" to null, "state" to "on"),
    )
    private var seoSeq = 10

    private val campaigns = mutableListOf(
        jo("id" to 1, "company" to "TY", "title_fa" to "هفته‌ی آموزش طلا", "goal_fa" to "هزار دنبال‌کننده‌ی تازه", "starts" to day(4), "ends" to day(10), "channels" to ja(listOf(JsonPrimitive("instagram_reel"), JsonPrimitive("telegram_post"))), "budget" to 2_000_000, "state" to "planned"),
        jo("id" to 2, "company" to "FX", "title_fa" to "معرفی صفحه‌ی سیگنال رایگان", "goal_fa" to "ورودی جست‌وجو ۱۵٪ بیشتر", "starts" to day(5), "ends" to day(11), "channels" to ja(listOf(JsonPrimitive("site_article"))), "budget" to null, "state" to "planned"),
    )
    private var campSeq = 10

    private val adCampaigns = mutableListOf(
        adCampaign("c-77", "جست‌وجوی سیگنال طلا", "on", null, 800_000.0, 2.6),
        adCampaign("c-81", "بازاریابی مجدد بازدیدکنندگان", "paused", "بازده کمتر از 1.2 بود و 7 روز ماند؛ قاعده‌ی «بازده پایین» متوقفش کرد.", 500_000.0, 0.9),
    )
    private val adRules = mutableListOf(
        jo("id" to 1, "company" to "TY", "scope" to "account", "daily_cap" to 1_000_000, "window_days" to 7, "min_roas" to 1.2, "min_spend_before_judging" to 2_000_000, "action" to "pause", "state" to "on"),
        jo("id" to 2, "company" to "TY", "scope" to "c-77", "daily_cap" to 1_200_000, "window_days" to 3, "min_roas" to 1.5, "min_spend_before_judging" to 1_000_000, "action" to "notify", "state" to "on"),
    )
    private var ruleSeq = 10

    private val autos = mutableListOf(
        jo("ref" to "AU-0001", "company" to "TY", "sentence_fa" to "هر شنبه ساعت 10 یک ریلز آموزشی بساز و اگر دنبال‌کننده‌ها کم شدند خبرم کن", "state" to "on",
            "runs" to ja(listOf(jo("at" to at(-3, 9, 30), "state" to "done", "note_fa" to "خط ریلز اجرا شد."), jo("at" to at(-10, 9, 30), "state" to "done", "note_fa" to "خط ریلز اجرا شد."))),
            "last_run_at" to at(-3, 9, 30), "n8n_workflow" to null,
            "rule" to jo("trigger" to jo("kind" to "schedule", "rrule" to "FREQ=WEEKLY;BYDAY=SA;BYHOUR=10;BYMINUTE=0"), "conditions" to ja(emptyList()), "actions" to ja(listOf(jo("kind" to "line.run", "args" to jo("line" to "LN-0001"))))),
            "preview_fa" to "هر شنبه ساعت 10:00 خط «ریلز طلای تریدیار» را اجرا میکند."),
        jo("ref" to "AU-0002", "company" to "FX", "sentence_fa" to "اگر بازده تبلیغ زیر یک و دو شد تبلیغ را متوقف کن", "state" to "proposed", "runs" to 0, "last_run_at" to null, "n8n_workflow" to null,
            "rule" to jo("trigger" to jo("kind" to "metric", "key" to "roas", "op" to "<", "value" to 1.2, "window" to 7), "conditions" to ja(emptyList()), "actions" to ja(listOf(jo("kind" to "ad.pause", "args" to jo()), jo("kind" to "notify.lead", "args" to jo())))),
            "preview_fa" to "اگر بازده تبلیغ در هفت روز کمتر از 1.2 شد، تبلیغ را متوقف میکند و به مدیر رشد خبر میدهد."),
    )
    private var autoSeq = 3

    // -------------------------------------------------------------- routes --
    /** The §31 routes; null for everything else (the rest of the demo answers it). */
    @Synchronized
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        Regex("^/lines/(LN-\\d+)/insights$").find(path)?.let { m ->
            if (method != "GET") return null
            return 200 to jo(
                "line" to m.groupValues[1], "metric" to "views", "window_runs" to 12,
                "best" to jo("hour" to 18, "length_bucket" to "25 تا 35 ثانیه", "voice" to "Kore", "pattern_source" to "پینترست"),
                "top_hooks" to ja(listOf("طلا دوباره به 2000 دلار رسید؛ خریدارها هنوز هستند؟", "سه اشتباه رایج وقتی قیمت به حمایت میرسد", "این عدد را قبل از هر معامله‌ی طلا نگاه کن").map { JsonPrimitive(it) }),
                "lessons_fa" to ja(listOf("ریلزهای ساعت 18 حدود 40% بیشتر از ساعت 10 دیده شدند.", "متن‌های 25 تا 35 ثانیه‌ای بیشتر تا آخر دیده میشوند.", "قلاب با یک عدد در سه ثانیه‌ی اول، ذخیره‌ی بیشتری گرفت.").map { JsonPrimitive(it) }),
                "updated_at" to at(0, 6),
            )
        }
        if (path == "/kits" && method == "GET") return 200 to ja(kits)
        if (path == "/companies/from-kit/preview" && method == "POST") {
            val kit = kits.firstOrNull { it.str("key") == body?.str("kit") } ?: return 404 to problem(404, "not_found", "این بسته پیدا نشد.")
            val name = body?.str("name_fa").orEmpty()
            return 200 to jo(
                "preview_fa" to "شرکت «$name» با تیم آماده‌ی رسانه، ${kit.arr("lines").size} خط تولید پیش‌نویس و ${kit.arr("kpis").size} شاخص ساخته میشود. هیچ خطی بدون مُهر تو منتشر نمیکند.",
                "team_fa" to ja(listOf("مدیرعامل", "مدیر محتوا", "نویسنده", "طراح تصویر", "تحلیلگر عملکرد").map { JsonPrimitive(it) }),
                "todo_fa" to ja(todo(kit)),
            )
        }
        if (path == "/companies/from-kit" && method == "POST") {
            val kit = kits.firstOrNull { it.str("key") == body?.str("kit") } ?: return 404 to problem(404, "not_found", "این بسته پیدا نشد.")
            val code = body?.str("code").orEmpty()
            if (!Regex("^[A-Z][A-Z0-9]{1,9}$").matches(code)) return 422 to problem(422, "validation_failed", "کد شرکت باید حرف انگلیسی بزرگ باشد.")
            return 201 to jo(
                "company" to jo("code" to code, "name_fa" to body?.str("name_fa")),
                "lines" to ja(kit.arr("lines").indices.map { JsonPrimitive("LN-%04d".format(40 + it)) }),
                "todo_fa" to ja(todo(kit)),
            )
        }
        Regex("^/companies/([^/]+)/newsletter(/campaigns)?$").find(path)?.let { m ->
            val n = newsletters[m.groupValues[1]] ?: return 404 to problem(404, "not_found", "این شرکت پیدا نشد.")
            if (m.groupValues[2].isEmpty() && method == "GET") return 200 to n
            if (m.groupValues[2].isNotEmpty() && method == "POST") {
                val c = jo("id" to nlSeq++, "list" to body?.get("list"), "subject" to body?.str("subject"), "subject_b" to body?.str("subject_b"), "state" to "draft", "scheduled_at" to null, "sent" to null, "opens" to null, "clicks" to null, "body_md" to body?.str("body_md"))
                newsletters[m.groupValues[1]] = n.with("campaigns" to ja(listOf<JsonElement>(c) + n.arr("campaigns")))
                return 201 to c
            }
        }
        Regex("^/newsletter/campaigns/(\\d+)(/schedule)?$").find(path)?.let { m ->
            for ((co, n) in newsletters) {
                val camps = n.arr("campaigns")
                val c = camps.firstOrNull { (it["id"] as? JsonPrimitive)?.contentOrNull == m.groupValues[1] } ?: continue
                if (m.groupValues[2].isEmpty() && method == "GET") return 200 to c
                if (m.groupValues[2].isNotEmpty() && method == "POST") {
                    val upd = c.with("state" to "scheduled", "scheduled_at" to body?.str("at"))
                    newsletters[co] = n.with("campaigns" to ja(camps.map { if (it === c) upd else it }))
                    return 200 to upd
                }
            }
            return 404 to problem(404, "not_found", "این خبرنامه پیدا نشد.")
        }
        Regex("^/companies/([^/]+)/(keywords|ranks|competitors)(/daily|/\\d+)?$").find(path)?.let { m ->
            val co = m.groupValues[1]
            val id = m.groupValues[3].removePrefix("/").toIntOrNull()
            when (m.groupValues[2]) {
                "keywords" -> when (method) {
                    "GET" -> return 200 to ja(keywords.filter { it.str("company") == co })
                    "POST" -> { val k = jo("id" to seoSeq++, "company" to co, "phrase" to body?.str("phrase"), "site" to body?.str("site"), "target_url" to body?.str("target_url"), "state" to "on"); keywords += k; return 201 to k }
                    "PUT" -> { val i = keywords.indexOfFirst { it.int("id") == id }; if (i < 0) return 404 to problem(404, "not_found", "پیدا نشد."); keywords[i] = keywords[i].with("state" to (body?.str("state") ?: "on")); return 200 to keywords[i] }
                    "DELETE" -> { keywords.removeAll { it.int("id") == id }; return 200 to jo() }
                }
                "ranks" -> if (method == "GET") return 200 to ja(keywords.filter { it.str("company") == co }.flatMap { k ->
                    last30.mapIndexed { i, d ->
                        val base = when (k.int("id")) { 1 -> 14.0; 2 -> 28.0; else -> 9.0 }
                        jo("keyword" to k.int("id"), "day" to d, "source" to "search_console", "position" to (if (k.int("id") == 2 && i < 2) null else Math.round(base - i * 0.12 + Math.sin(i * 1.7) * 1.4).coerceAtLeast(1)), "url" to k.str("target_url"))
                    }
                })
                "competitors" -> when {
                    m.groupValues[3] == "/daily" && method == "GET" -> return 200 to ja(competitors.filter { it.str("company") == co }.flatMap { c ->
                        last30.flatMapIndexed { i, d ->
                            listOf(
                                jo("competitor" to c.int("id"), "day" to d, "key" to "followers", "value" to 21_000 + c.int("id") * 3000 + i * (if (c.int("id") == 1) 38 else 12) + (if (i > 26 && c.int("id") == 1) 900 else 0), "source" to "instagram"),
                                jo("competitor" to c.int("id"), "day" to d, "key" to "new_pages", "value" to (if (i % 6 == 0) 3 else 0), "source" to "sitemap"),
                            )
                        }
                    })
                    method == "GET" -> return 200 to ja(competitors.filter { it.str("company") == co })
                    method == "POST" -> { val c = jo("id" to seoSeq++, "company" to co, "name_fa" to body?.str("name_fa"), "site" to body?.str("site"), "instagram" to body?.str("instagram"), "youtube" to body?.str("youtube"), "telegram" to body?.str("telegram"), "state" to "on"); competitors += c; return 201 to c }
                    method == "DELETE" -> { competitors.removeAll { it.int("id") == id }; return 200 to jo() }
                }
            }
            return null
        }
        // The campaign calendar: lines, a newsletter, an ad and campaigns; one conflict and a holiday.
        if (path == "/campaign-calendar" && method == "GET") {
            val from = query["from"] ?: day(-7)
            val to = query["to"] ?: day(30)
            val co = query["company"]
            val items = (listOf(
                ci(-1, at(-1, 18), "TY", "line", "LN-0001", "ریلز طلای تریدیار", "instagram_reel", "done", null),
                ci(0, at(0, 18), "TY", "line", "LN-0001", "ریلز طلای تریدیار", "instagram_reel", "scheduled", null),
                ci(0, at(0, 19), "TY", "line", "LN-0004", "پست استوری تریدیار", "instagram_reel", "scheduled", "دو پست روی یک کانال در کمتر از دو ساعت"),
                ci(1, at(1, 9), "FX", "line", "LN-0002", "پست روزانه‌ی کانال کوینه‌پرو", "telegram_post", "scheduled", null),
                ci(2, at(2, 7), "TY", "newsletter", "NL-12", "سه نکته برای معامله‌ی هفته‌ی بعد", null, "scheduled", null),
                ci(3, at(3, 8), "TY", "ad", "google_ads/c-77", "کمپین جست‌وجوی سیگنال طلا", "google_ads", "running", null),
                ci(4, null, "TY", "campaign", "CP-1", "هفته‌ی آموزش طلا", null, "planned", "هم‌زمان با تعطیلی رسمی؛ مخاطب کم است"),
                ci(5, null, "FX", "campaign", "CP-2", "معرفی صفحه‌ی سیگنال رایگان", null, "planned", null),
            ) + campaigns.filter { false }.map { it }).filter { (co == null || it.str("company") == co) && it.str("day")!! >= from && it.str("day")!! <= to }
            return 200 to ja(items)
        }
        Regex("^/campaigns(?:/(\\d+))?$").find(path)?.let { m ->
            val id = m.groupValues[1].toIntOrNull()
            return when {
                id == null && method == "GET" -> 200 to ja(campaigns.filter { query["company"] == null || it.str("company") == query["company"] })
                id == null && method == "POST" -> { val c = (body ?: jo()).with("id" to campSeq++, "state" to "planned"); campaigns += c; 201 to c }
                method == "PUT" -> { val i = campaigns.indexOfFirst { it.int("id") == id }; if (i < 0) 404 to problem(404, "not_found", "پیدا نشد.") else { campaigns[i] = campaigns[i].with(*(body ?: jo()).entries.map { it.key to it.value }.toTypedArray()); 200 to campaigns[i] } }
                method == "DELETE" -> { campaigns.removeAll { it.int("id") == id }; 200 to jo() }
                else -> null
            }
        }
        Regex("^/companies/([^/]+)/(ads|ad-rules)(?:/(\\d+))?$").find(path)?.let { m ->
            val co = m.groupValues[1]
            val id = m.groupValues[3].toIntOrNull()
            if (m.groupValues[2] == "ads" && method == "GET") return 200 to (if (co != "TY") jo("accounts" to ja(emptyList()), "campaigns" to ja(emptyList())) else jo(
                "accounts" to ja(listOf(jo("company" to "TY", "platform" to "google_ads", "account_id" to "123-456-7890", "state" to "connected"), jo("company" to "TY", "platform" to "meta_ads", "account_id" to "act_5521", "state" to "not_connected"))),
                "campaigns" to ja(adCampaigns),
            ))
            if (m.groupValues[2] == "ad-rules") return when {
                id == null && method == "GET" -> 200 to ja(adRules.filter { it.str("company") == co })
                id == null && method == "POST" -> { val r = (body ?: jo()).with("id" to ruleSeq++, "company" to co); adRules += r; 201 to r }
                method == "PUT" -> { val i = adRules.indexOfFirst { it.int("id") == id }; if (i < 0) 404 to problem(404, "not_found", "پیدا نشد.") else { adRules[i] = adRules[i].with(*(body ?: jo()).entries.map { it.key to it.value }.toTypedArray()); 200 to adRules[i] } }
                method == "DELETE" -> { adRules.removeAll { it.int("id") == id }; 200 to jo() }
                else -> null
            }
        }
        Regex("^/ads/campaigns/([^/]+)/([^/]+)/resume$").find(path)?.let { m ->
            if (method != "POST") return null
            val i = adCampaigns.indexOfFirst { it.str("platform") == m.groupValues[1] && it.str("id") == m.groupValues[2] }
            if (i < 0) return 404 to problem(404, "not_found", "این کمپین پیدا نشد.")
            adCampaigns[i] = adCampaigns[i].with("state" to "on", "paused_reason_fa" to null)
            return 200 to adCampaigns[i]
        }
        if (path == "/automations/compile" && method == "POST") {
            val s = body?.str("sentence_fa").orEmpty()
            if (s.isBlank()) return 422 to problem(422, "validation_failed", "یک جمله بنویس.")
            return 200 to compile(s)
        }
        if (path == "/automations") return when (method) {
            "GET" -> 200 to ja(autos.map { it.with("runs" to it.arr("runs").size.let { n -> if (it["runs"] is JsonArray) n else it["runs"] }) })
            "POST" -> {
                val a = jo("ref" to "AU-%04d".format(autoSeq++), "company" to body?.str("company"), "sentence_fa" to body?.str("sentence_fa"), "rule" to body?.get("rule"), "state" to "proposed", "runs" to 0, "last_run_at" to null, "n8n_workflow" to null,
                    "preview_fa" to compile(body?.str("sentence_fa").orEmpty()).str("preview_fa"))
                autos.add(0, a)
                201 to a
            }
            else -> null
        }
        Regex("^/automations/(AU-\\d+)(/seal|/state)?$").find(path)?.let { m ->
            val i = autos.indexOfFirst { it.str("ref") == m.groupValues[1] }
            if (i < 0) return 404 to problem(404, "not_found", "این اتوماسیون پیدا نشد.")
            return when {
                m.groupValues[2].isEmpty() && method == "GET" -> 200 to autos[i]
                m.groupValues[2] == "/seal" && method == "POST" -> { autos[i] = autos[i].with("state" to "on"); 200 to autos[i] }
                m.groupValues[2] == "/state" && method == "POST" ->
                    if (autos[i].str("state") == "proposed") 409 to problem(409, "conflict", "اول مُهر کن.") else { autos[i] = autos[i].with("state" to (if (body?.str("state") == "off") "off" else "on")); 200 to autos[i] }
                else -> null
            }
        }
        return null
    }

    // ------------------------------------------------------------ the data --
    private fun kl(template: String, platform: String, title: String) = jo("template" to template, "platform" to platform, "title_fa" to title)
    private fun kit(key: String, title: String, purpose: String, groups: List<String>, lines: List<JsonObject>, kpis: List<String>, connections: List<String>) = jo(
        "key" to key, "title_fa" to title, "purpose_fa" to purpose, "team_template" to "media_company", "groups" to ja(groups.map { JsonPrimitive(it) }), "lines" to ja(lines),
        "kpis" to ja(kpis.map { JsonPrimitive(it) }), "connections" to ja(connections.map { JsonPrimitive(it) }), "defaults" to jo(),
    )
    private val connectionFa = mapOf("instagram" to "اینستاگرام", "telegram" to "تلگرام", "search_console" to "کنسول جست‌وجو", "ga4" to "آمار سایت")
    private fun todo(kit: JsonObject): List<JsonElement> =
        (kit["connections"] as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.contentOrNull }.map { JsonPrimitive("اتصال ${connectionFa[it] ?: it} را وصل کن تا عددهایش بیاید.") } + JsonPrimitive("یک سرور برای شرکت از بخش تأسیس درخواست کن.")

    private fun ci(off: Long, atIso: String?, co: String, kind: String, ref: String, title: String, platform: String?, state: String, conflict: String?) = jo(
        "day" to day(off), "at" to atIso, "company" to co, "kind" to kind, "ref" to ref, "title_fa" to title, "platform" to platform, "state" to state, "conflict_fa" to conflict,
    )

    private fun adCampaign(id: String, title: String, state: String, reason: String?, spend: Double, roas: Double) = jo(
        "platform" to "google_ads", "id" to id, "title_fa" to title, "state" to state, "paused_reason_fa" to reason,
        "days" to ja(last30.mapIndexed { i, d ->
            val s = Math.round(spend + Math.sin(i.toDouble()) * spend * 0.2)
            jo("platform" to "google_ads", "campaign_id" to id, "day" to d, "spend" to s, "clicks" to 40 + (i % 7) * 6, "conversions" to 2 + (i % 4), "revenue" to Math.round(s * roas), "roas" to Math.round((roas + Math.cos(i.toDouble()) * 0.3) * 100) / 100.0)
        }),
    )

    /** The sentence as the hub's compiler would read it, by rules: the trigger, the allowed actions, and what it refuses. */
    private fun compile(s: String): JsonObject {
        val refused = mutableListOf<String>()
        if (Regex("حذف|پاک|پرداخت|انتقال پول").containsMatchIn(s)) refused += "این کار در فهرست کارهای مجاز نیست؛ فقط ساخت کار، اجرا یا مکث خط، خبر دادن و توقف تبلیغ ممکن است."
        val metric = Regex("بازده|دنبال‌کننده").containsMatchIn(s)
        val trigger = if (metric) jo("kind" to "metric", "key" to (if (s.contains("بازده")) "roas" else "followers"), "op" to "<", "value" to (if (s.contains("بازده")) 1.2 else 12000), "window" to 7)
        else jo("kind" to "schedule", "rrule" to (if (s.contains("هر روز")) "FREQ=DAILY;BYHOUR=9;BYMINUTE=0" else "FREQ=WEEKLY;BYDAY=SA;BYHOUR=10;BYMINUTE=0"))
        val actions = mutableListOf<JsonElement>()
        val said = mutableListOf<String>()
        if (s.contains("تبلیغ") && Regex("متوقف|مکث").containsMatchIn(s)) { actions += jo("kind" to "ad.pause", "args" to jo()); said += "تبلیغ را متوقف میکند" }
        if (Regex("بساز|اجرا").containsMatchIn(s)) { actions += jo("kind" to "line.run", "args" to jo()); said += "خط تولید را اجرا میکند" }
        if (s.contains("خبر")) { actions += jo("kind" to "notify.owner", "args" to jo()); said += "به تو خبر میدهد" }
        if (actions.isEmpty() && refused.isEmpty()) refused += "نفهمیدم چه کاری باید انجام شود؛ مثلاً بنویس «هر شنبه یک ریلز بساز»."
        val when_ = if (metric) "وقتی ${if (s.contains("بازده")) "بازده تبلیغ" else "دنبال‌کننده‌ها"} کمتر از ${if (s.contains("بازده")) "1.2" else "12000"} شد"
        else if (s.contains("هر روز")) "هر روز ساعت 09:00" else "هر شنبه ساعت 10:00"
        val preview = if (actions.isEmpty()) "" else "$when_، ${said.joinToString(" و ")}. کاری جز این نمیکند و بدون مُهر تو اجرا نمیشود."
        return jo("rule" to jo("trigger" to trigger, "conditions" to ja(emptyList()), "actions" to ja(actions)), "preview_fa" to preview, "refused_fa" to ja(refused.map { JsonPrimitive(it) }))
    }

    // ------------------------------------------------------------- helpers --
    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
    private fun JsonObject.int(k: String): Int = (this[k] as? JsonPrimitive)?.contentOrNull?.toIntOrNull() ?: 0
    private fun JsonObject.arr(k: String): List<JsonObject> = (this[k] as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()
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
