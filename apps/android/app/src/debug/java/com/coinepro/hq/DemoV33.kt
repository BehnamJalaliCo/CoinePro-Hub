package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import java.time.LocalDate
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * Debug builds only: contract §33 ⟨1.15⟩, money and the working style, in the hub's own shapes (`hq-api.v1.json`). Deterministic (every
 * day from [HqClock]), so the screenshots are the same on any machine.
 *
 * - **Usage (§33.1):** three weekly and two daily reports in the advisor's words, each with its pack.
 * - **Payments (§33.2):** TradeYar's ledger through its runner and two public addresses (one TRON address failing), fourteen payments in
 *   every status, paged; 30 days of reconcile. CoinePro FX reads one BSC address; Pro-Chart has no source yet.
 * - **Revenue (§33.3, §33.5):** eight months of MRR with cohorts, a forecast band, ROI and cost per output; four affiliate months.
 * - **Sales (§33.4):** seven leads of TradeYar across the default stages, its pipeline, a drafted follow-up the guard passes.
 * - **Journeys (§33.8), personas (§33.9):** three companies on their way; TradeYar's three personas, two suggestions and a message test.
 * - **Order report F-0045 (§33.7, §33.10):** a work split in three parts (one failed), and a work running on TradeYar's own server.
 */
internal class V33Demo {
    private val now = HqClock.now()
    private val today: LocalDate = LocalDate.ofInstant(now, ZoneOffset.UTC)
    private fun day(off: Long): String = today.plusDays(off).toString()
    private fun at(offDays: Long, h: Int = 9, m: Int = 0): String = today.plusDays(offDays).atTime(h, m).toInstant(ZoneOffset.UTC).toString()
    private fun ago(min: Long): String = now.minus(min, ChronoUnit.MINUTES).toString()
    private fun month(off: Long): String = today.withDayOfMonth(1).plusMonths(off).toString().take(7)

    // ------------------------------------------------------------ payments --
    private val sources = linkedMapOf(
        "TY" to mutableListOf(
            source("5b0c1e7a-0000-4000-8000-000000000001", "TY", "ledger", "ledger_v1", null, null, "tradeyar-main", "ok", ago(42), null),
            source("5b0c1e7a-0000-4000-8000-000000000002", "TY", "chain", "chain_read", "bsc_usdt", "0x8f3a91c2d4e5b6a7c8d9e0f1a2b3c4d5e6f7a9b1", null, "ok", ago(18), null),
            source("5b0c1e7a-0000-4000-8000-000000000003", "TY", "chain", "chain_read", "trc20_usdt", "TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE", null, "error", ago(380),
                "شبکه‌ی ترون جواب نداد؛ ساعت بعد دوباره خوانده میشود."),
        ),
        "FX" to mutableListOf(
            source("5b0c1e7a-0000-4000-8000-000000000004", "FX", "chain", "chain_read", "bsc_usdt", "0x2c7e0d1f4a3b5c6d7e8f9a0b1c2d3e4f5a6b7c8d", null, "ok", ago(55), null),
        ),
        "PC" to mutableListOf(),
    )
    private var srcSeq = 10

    private val payments: Map<String, List<JsonObject>> = mapOf(
        "TY" to listOf(
            pay(1, "TY", "u-7f21c9", "پلن ماهانه", "29.00", null, "bsc_usdt", 0, "matched"),
            pay(2, "TY", "u-a04d18", "پلن سه‌ماهه", "79.00", null, "trc20_usdt", 0, "pending_chain", note = "تراکنش هنوز 12 تأیید از 20 دارد."),
            pay(3, "TY", null, null, null, "45.00", "bsc_usdt", 1, "chain_only", note = "45 USDT به نشانی شرکت رسید ولی در دفتر شرکت مشتری‌ای برایش نیست."),
            pay(4, "TY", "u-3b9e02", "پلن ماهانه", "29.00", null, "bsc_usdt", 1, "matched"),
            pay(5, "TY", "u-c81f77", "پلن سالانه", "249.00", "199.00", "bsc_usdt", 2, "amount_mismatch", note = "پلن 249 USDT است ولی 199 USDT رسید."),
            pay(6, "TY", "u-55e0aa", "پلن ماهانه", "29.00", null, "trc20_usdt", 2, "matched"),
            pay(7, "TY", "u-9d14b3", "پلن سه‌ماهه", "79.00", null, null, 3, "ledger_only", note = "در دفتر شرکت تأیید شده ولی هیچ انتقالی روی زنجیره پیدا نشد."),
            pay(8, "TY", "u-e2c6f0", "پلن ماهانه", "29.00", null, "bsc_usdt", 4, "matched"),
            pay(9, "TY", "u-104b7d", "پلن ماهانه", null, null, null, 4, "matched", note = "پرداخت درون‌برنامه‌ای؛ شمرده میشود، جمع نمیشود."),
            pay(10, "TY", "u-7f21c9", "پلن ماهانه", "29.00", null, "bsc_usdt", 5, "matched"),
            pay(11, "TY", "u-6ab3d2", "پلن سه‌ماهه", "79.00", null, "bsc_usdt", 6, "matched"),
            pay(12, "TY", "u-f00e19", "پلن ماهانه", "29.00", null, "trc20_usdt", 7, "matched"),
            pay(13, "TY", "u-2d8c40", "پلن سالانه", "249.00", null, "bsc_usdt", 8, "matched"),
            pay(14, "TY", "u-88a1e5", "پلن ماهانه", "29.00", null, "bsc_usdt", 9, "matched"),
        ),
        "FX" to listOf(
            pay(21, "FX", "u-41c0de", "اشتراک سیگنال", "19.00", null, "bsc_usdt", 0, "matched"),
            pay(22, "FX", "u-0be7a2", "اشتراک سیگنال", "19.00", null, "bsc_usdt", 2, "matched"),
        ),
    )

    private fun reconcile(code: String, from: LocalDate, to: LocalDate): List<JsonObject> {
        val seed = code.sumOf { it.code }
        val out = mutableListOf<JsonObject>()
        var d = to
        while (!d.isBefore(from)) {
            val off = ChronoUnit.DAYS.between(d, today).toInt()
            val base = if (code == "PC") 0 else (2 + (off * 7 + seed) % 5)
            val lo = if (code == "TY" && off == 3) 1 else 0
            val co = if (code == "TY" && off == 1) 1 else 0
            val mm = if (code == "TY" && off == 2) 1 else 0
            val pc = if (code == "TY" && off == 0) 1 else 0
            out += jo(
                "company" to code, "day" to d.toString(), "ledger_count" to base + lo + mm + pc, "chain_count" to base + co + mm + pc, "matched" to base,
                "ledger_only" to lo, "chain_only" to co, "amount_mismatch" to mm, "pending_chain" to pc,
                "note_fa" to when {
                    lo > 0 -> "یک پرداخت تأییدشده بدون پول روی زنجیره؛ به مدیر مالی شرکت خبر داده شد."
                    co > 0 -> "یک انتقال بدون مشتری در دفتر؛ شرکت میتواند صاحبش را پیدا کند."
                    else -> ""
                },
            )
            d = d.minusDays(1)
        }
        return out
    }

    // ------------------------------------------------------------- revenue --
    private fun board(company: String?): JsonObject {
        val scale = when (company) { null -> 1.0; "TY" -> 0.62; "FX" -> 0.38; else -> 0.0 }
        if (scale == 0.0) return jo(
            "company" to company, "period" to "month", "months" to ja(emptyList()), "churn_rate" to null, "ltv_usdt" to null, "cac_usdt" to null,
            "payback_months" to null, "cohorts" to ja(emptyList()), "forecast" to ja(emptyList()), "forecast_basis_fa" to "", "roi" to roi(0.0, 0.0),
            "cost_per_output" to ja(emptyList()),
        )
        val mrr = listOf(1180.0, 1420.0, 1610.0, 1760.0, 2050.0, 2240.0, 2390.0, 2610.0).map { it * scale }
        val active = listOf(41, 49, 55, 60, 69, 75, 80, 87).map { (it * scale).toInt().coerceAtLeast(1) }
        val months = mrr.indices.map { i ->
            jo(
                "month" to month(i - 7L), "mrr_usdt" to "%.2f".format(java.util.Locale.US, mrr[i]), "new_customers" to (((9 + i % 3) * scale).toInt()),
                "churned" to (((3 + i % 2) * scale).toInt()), "active" to active[i], "arpu_usdt" to "%.2f".format(java.util.Locale.US, mrr[i] / active[i]),
            )
        }
        val last = mrr.last()
        val forecast = (1..3).map { k ->
            val m = last + 190 * scale * k
            jo("month" to month(k.toLong()), "mrr_usdt" to "%.2f".format(java.util.Locale.US, m), "low" to "%.2f".format(java.util.Locale.US, m - 120 * scale * k), "high" to "%.2f".format(java.util.Locale.US, m + 120 * scale * k))
        }
        val cohorts = (0 until 6).map { i ->
            jo("start_month" to month(i - 7L), "size" to ((12 - i) * scale).toInt().coerceAtLeast(1),
                "retained" to ja((0 until 6 - i).map { k -> JsonPrimitive(if (k == 0) 100.0 else (100.0 - k * (9 + i))) }))
        }
        return jo(
            "company" to company, "period" to "month", "months" to ja(months), "churn_rate" to 0.046, "ltv_usdt" to "%.2f".format(java.util.Locale.US, last / active.last() / 0.046),
            "cac_usdt" to "%.2f".format(java.util.Locale.US, 11.4), "payback_months" to 0.4, "cohorts" to ja(cohorts), "forecast" to ja(forecast),
            "forecast_basis_fa" to "روند خطی هولت روی 8 ماه درآمد؛ بازه با 1.28 برابر انحراف خطاهای گذشته. تخمین است، نه قول.",
            "roi" to roi(last, 312.0 * scale),
            "cost_per_output" to ja(listOf(
                jo("kind" to "line_run", "count" to (64 * scale).toInt(), "usd_each" to "0.42"),
                jo("kind" to "deliverable", "count" to (38 * scale).toInt(), "usd_each" to "1.85"),
                jo("kind" to "order", "count" to (11 * scale).toInt(), "usd_each" to "6.10"),
            )),
        )
    }

    private fun roi(revenue: Double, cost: Double) = jo(
        "revenue_usdt" to "%.2f".format(java.util.Locale.US, revenue),
        "cost_usd" to jo("tokens" to "%.2f".format(java.util.Locale.US, cost * 0.58), "voice" to "%.2f".format(java.util.Locale.US, cost * 0.07), "ads" to "%.2f".format(java.util.Locale.US, cost * 0.35), "servers" to null),
        "ratio" to if (cost > 0) Math.round(revenue / cost * 10) / 10.0 else null,
    )

    private val gaps = listOf(
        gap("TY", "lbank-ty-main", "lbank", month(-1), "1840.00", "1622.50", "open", "سلام، کمیسیون ماه گذشته‌ی حساب ما 217.50 USDT کمتر از گزارش خودتان است. لطفاً بررسی و تسویه کنید.", "W-000287"),
        gap("TY", "lbank-ty-main", "lbank", month(0), "960.00", "0.00", "waiting", null, null),
        gap("FX", "bitunix-fx", "bitunix", month(-1), "702.00", "699.10", "ok", null, null),
        gap("FX", "bitunix-fx", "bitunix", month(-2), "655.00", "580.00", "closed", null, null),
    )

    // --------------------------------------------------------------- usage --
    private fun pack(period: String, from: String, to: String, k: Double) = jo(
        "period" to period, "from" to from, "to" to to,
        "by_domain" to ja(listOf(
            jo("domain" to "content", "tokens" to (2_400_000 * k).toLong(), "usd_equiv" to 21.4 * k, "share" to 0.41),
            jo("domain" to "growth", "tokens" to (1_350_000 * k).toLong(), "usd_equiv" to 12.1 * k, "share" to 0.23),
            jo("domain" to "support", "tokens" to (980_000 * k).toLong(), "usd_equiv" to 8.7 * k, "share" to 0.17),
            jo("domain" to "ops", "tokens" to (640_000 * k).toLong(), "usd_equiv" to 5.9 * k, "share" to 0.11),
            jo("domain" to "tech", "tokens" to (420_000 * k).toLong(), "usd_equiv" to 4.3 * k, "share" to 0.08),
        )),
        "by_company" to ja(listOf(
            jo("company" to "TY", "tokens" to (3_100_000 * k).toLong(), "usd_equiv" to 27.8 * k, "share" to 0.53),
            jo("company" to "FX", "tokens" to (1_700_000 * k).toLong(), "usd_equiv" to 15.2 * k, "share" to 0.29),
            jo("company" to "PC", "tokens" to (990_000 * k).toLong(), "usd_equiv" to 9.4 * k, "share" to 0.18),
        )),
        "top_runs" to ja(listOf(
            jo("ref" to "R-004812", "role" to "نویسنده‌ی محتوای تریدیار", "tokens" to (310_000 * k).toLong()),
            jo("ref" to "R-004790", "role" to "تحلیلگر رشد کوینه‌پرو FX", "tokens" to (220_000 * k).toLong()),
            jo("ref" to "R-004771", "role" to "پشتیبان تریدیار", "tokens" to (160_000 * k).toLong()),
        )),
        "voice_usd" to 3.2 * k, "lines" to jo("runs" to (21 * k).toInt(), "tokens" to (1_100_000 * k).toLong()), "ads_spend_usd" to 18.0 * k,
        "vs_prev" to jo("tokens_pct" to 12.4, "usd_pct" to 9.8),
        "anomalies" to ja(listOf(jo("kind" to "spike", "note" to "مصرف توکن 12.4٪ بیشتر از دوره‌ی قبل است."))),
    )

    private val usage = mutableListOf(
        report("UR-0014", "week", at(-7, 0), at(0, 0), 1.0, ago(90), listOf(
            "این هفته 52 دلار خرج مدل‌ها شد؛ حدود 10% بیشتر از هفته‌ی قبل.",
            "بیشترین خرج با تولید محتوای تریدیار بود: 21 دلار، بیشترش برای ریلزهای آموزشی.",
            "پشتیبانی تریدیار 9 دلار خرج کرد؛ نیمی از پرسش‌ها تکراری بودند و پاسخ آماده داشتند.",
            "صدا فقط 3 دلار بود؛ گزارش‌های صوتی صبح ارزان مانده‌اند.",
        ), "اگر پاسخ‌های آماده‌ی پشتیبانی تریدیار اول بیایند، هفته‌ای حدود 4 دلار کم میشود."),
        report("UR-0012", "week", at(-14, 0), at(-7, 0), 0.9, at(-7, 6), listOf(
            "هفته‌ی آرامی بود: 47 دلار، بیشترش محتوا.", "کوینه‌پرو FX کمتر از همیشه مصرف کرد چون خط تولیدش دو روز خاموش بود.", "هیچ چیز غیرعادی دیده نشد.",
        ), "خلاصه‌ی خبرهای صبح را میشود با مدل ارزان‌تر نوشت؛ کیفیتش در آزمون فرقی نکرد."),
        report("UR-0010", "week", at(-21, 0), at(-14, 0), 0.8, at(-14, 6), listOf(
            "41 دلار خرج شد.", "رشد پرو-چارت بیشترین سهم را داشت، برای تحقیق رقبا.", "تبلیغات 14 دلار بود.",
        ), "تحقیق رقبا را هفته‌ای یک بار به‌جای هر روز اجرا کن."),
        report("UR-0013", "day", at(-1, 0), at(0, 0), 0.16, ago(300), listOf(
            "دیروز 8 دلار خرج شد، مثل روزهای قبل.", "بیشترش برای دو ریلز تریدیار بود.", "پشتیبانی کم کار داشت.",
        ), "ریلز دوم را میشد با همان متن اولی و صدای دیگر ساخت."),
        report("UR-0011", "day", at(-2, 0), at(-1, 0), 0.14, at(-1, 4), listOf(
            "7 دلار خرج شد.", "کوینه‌پرو FX گزارش هفتگی‌اش را نوشت.", "چیز غیرعادی‌ای نبود.",
        ), "گزارش هفتگی را کوتاه‌تر بخواه؛ نصف متن تکرار هفته‌ی قبل بود."),
    )
    private var usageSeq = 20

    // --------------------------------------------------------------- sales --
    private val stages = listOf("new" to "جدید", "contacted" to "تماس گرفته شد", "qualified" to "واجد شرایط", "trial" to "آزمایشی", "paid" to "پرداخت کرد", "lost" to "از دست رفت")
    private val leads = linkedMapOf(
        "LD-000041" to lead("LD-000041", "support", "پرسش‌گر پلن سالانه", "sp-71c2", "trial", "249.00", at(1, 6), "یادآوری پایان دوره‌ی آزمایشی و پیشنهاد پلن سالانه", ago(30),
            listOf(ev(at(-6, 8), "created", "از گفت‌وگوی پشتیبانی ساخته شد."), ev(at(-4, 10), "stage", "تماس گرفته شد ← واجد شرایط"), ev(at(-1, 12), "stage", "واجد شرایط ← آزمایشی"))),
        "LD-000040" to lead("LD-000040", "telegram", "عضو کانال سیگنال", "tg-4471", "qualified", "79.00", at(2, 6), "معرفی پلن سه‌ماهه", ago(200), listOf(ev(at(-3, 9), "created", "از تلگرام آمد."))),
        "LD-000039" to lead("LD-000039", "payment", null, "u-c81f77", "contacted", null, null, null, ago(1440), listOf(ev(at(-1, 9), "created", "انتقالی بدون مشتری روی زنجیره رسید."))),
        "LD-000038" to lead("LD-000038", "site", "فرم مشاوره‌ی سایت", "site-0918", "new", null, at(0, 12), "اولین پیام خوش‌آمد", ago(500), listOf(ev(at(-1, 11), "created", "از فرم سایت."))),
        "LD-000037" to lead("LD-000037", "referral", "معرفی‌شده‌ی یک مشتری", "rf-22d0", "paid", "79.00", null, null, ago(4000), listOf(ev(at(-9, 9), "created", "معرفی شد."), ev(at(-3, 9), "payment", "79 USDT پرداخت کرد."))),
        "LD-000036" to lead("LD-000036", "telegram", "معامله‌گر تازه‌کار", "tg-9910", "lost", null, null, null, ago(6000), listOf(ev(at(-12, 9), "created", "از تلگرام آمد."), ev(at(-5, 9), "stage", "از دست رفت")), lost = "قیمت را زیاد دانست."),
        "LD-000035" to lead("LD-000035", "manual", "مدیر یک گروه آموزشی", "mg-0031", "qualified", "600.00", at(5, 6), "پیشنهاد پلن گروهی", ago(2500), listOf(ev(at(-8, 9), "created", "به دست تو ثبت شد."))),
    )
    private var leadSeq = 42

    private fun pipeline(code: String): JsonObject {
        val list = leads.values.filter { it.str("company") == code }
        fun value(xs: List<JsonObject>) = xs.sumOf { it.str("value_usdt")?.toDoubleOrNull() ?: 0.0 }
        val kinds = mapOf("paid" to "won", "lost" to "lost")
        val st = stages.map { (k, t) ->
            val xs = list.filter { it.str("stage") == k }
            jo("stage" to k, "title_fa" to t, "kind" to (kinds[k] ?: "open"), "count" to xs.size, "value_usdt" to "%.2f".format(java.util.Locale.US, value(xs)),
                "median_days" to if (kinds[k] == null && xs.isNotEmpty()) (2.0 + k.length % 4) else null)
        }
        val open = list.filter { it.str("stage") !in kinds }
        val won = list.count { it.str("stage") == "paid" }
        val lost = list.count { it.str("stage") == "lost" }
        return jo(
            "company" to code, "stages" to ja(st), "win_rate" to if (won + lost > 0) won.toDouble() / (won + lost) else null, "open_count" to open.size,
            "won_count" to won, "lost_count" to lost, "open_value_usdt" to "%.2f".format(java.util.Locale.US, value(open)), "total" to list.size,
        )
    }

    // ------------------------------------------------------- journey, personas --
    private val journeyStages = listOf(
        "founded" to "تأسیس", "server_ready" to "سرور آماده", "first_content" to "اولین محتوا", "first_visitor" to "اولین بازدیدکننده", "first_lead" to "اولین سرنخ",
        "first_payment" to "اولین پرداخت", "ten_paying" to "ده مشتری پرداخت‌کننده", "break_even" to "سربه‌سر",
    )
    private val evidence = listOf("company" to "TY", "server" to null, "line_run" to "RN-000118", "metric" to "visitors", "lead" to "LD-000012", "payment" to null, "customers" to "10", "month" to null)

    private fun journey(code: String): JsonObject {
        val reached = when (code) { "TY" -> 7; "FX" -> 6; "PC" -> 3; else -> 1 }
        val start = when (code) { "TY" -> 220L; "FX" -> 180L; "PC" -> 70L; else -> 300L }
        val st = journeyStages.mapIndexed { i, (k, t) ->
            val done = i < reached
            val (ek, er) = evidence[i]
            jo("key" to k, "title_fa" to t, "reached_at" to if (done) at(-(start - i * (start / 8)), 7) else null,
                "evidence" to if (done) jo("kind" to ek, "ref" to (if (ek == "company") code else er)) else null)
        }
        return jo(
            "company" to code, "stages" to ja(st), "current" to journeyStages[reached - 1].first, "days_in_stage" to (start / 8).toInt(),
            "next_fa" to when (code) {
                "TY" -> "برای سربه‌سر شدن، 9 مشتری پلن سالانه‌ی دیگر لازم است؛ پیگیری سرنخ‌های آزمایشی بیشترین اثر را دارد."
                "FX" -> "سه مشتری تا ده مشتری پرداخت‌کننده مانده؛ صفحه‌ی سیگنال رایگان را به خبرنامه وصل کن."
                "PC" -> "اولین سرنخ از سایت هنوز نیامده؛ فرم مشاوره را در صفحه‌ی اصلی بگذار."
                else -> null
            },
        )
    }

    private val personas = linkedMapOf(
        "TY" to mutableListOf(
            persona("a1e0c3d2-0000-4000-8000-000000000001", "TY", "معامله‌گر تازه‌کار", "تازه با بازار آشنا شده و از ضرر اولش میترسد؛ دنبال راهی ساده و مطمئن است.",
                listOf("نمیداند حد ضرر را کجا بگذارد", "وقت تحلیل روزانه ندارد"), listOf("سیگنال‌ها قبلاً به او ضرر داده‌اند", "قیمت پلن برایش زیاد است"), "کانال تلگرام و ریلز اینستاگرام", "owner"),
            persona("a1e0c3d2-0000-4000-8000-000000000002", "TY", "معامله‌گر پاره‌وقت", "شغل دیگری دارد و عصرها معامله میکند؛ به گزارش کوتاه و قابل اعتماد نیاز دارد.",
                listOf("فرصت‌ها را در ساعت کاری از دست میدهد"), listOf("به هشدارهای زیاد اعتماد ندارد"), "خبرنامه‌ی ایمیلی", "owner"),
            persona("a1e0c3d2-0000-4000-8000-000000000003", "TY", "مدیر گروه آموزشی", "برای شاگردانش ابزار و تحلیل میخواهد؛ تصمیم خرید گروهی با اوست.",
                listOf("ابزار گروهی ساده ندارد"), listOf("پشتیبانی فارسی کند است"), "معرفی دهان‌به‌دهان", "kb_suggested"),
        ),
        "FX" to mutableListOf(),
        "PC" to mutableListOf(),
    )
    private var personaSeq = 10

    // ---------------------------------------------------------- order F-0045 --
    private val report45 = jo(
        "ref" to "F-0045", "text_fa" to "یک گزارش کامل از بازار طلا برای مشتری‌های تریدیار آماده کن: تحلیل فنی، خبرها و یک ریلز کوتاه.", "at" to ago(240), "updated_at" to ago(6),
        "state" to "in_progress",
        "ack" to jo("at" to ago(238), "by" to jo("kind" to "agent", "code" to "TY-CEO", "display_fa" to "مدیرعامل تریدیار"),
            "plan_fa" to "کار را به سه بخش مستقل میدهم که همزمان پیش بروند؛ بعد یکی همه را در یک گزارش ادغام میکند. ریلز روی سرور خود تریدیار ساخته میشود.", "assigned" to ja(emptyList())),
        "route" to jo("companies" to ja(listOf(JsonPrimitive("TY"))), "department" to "CONTENT", "collaborators" to ja(emptyList()), "output_kind" to "report", "player" to "auto",
            "budget_tokens" to 600_000, "mode" to "parallel"),
        "steps" to ja(listOf(jo("at" to ago(238), "who_fa" to "مدیرعامل تریدیار", "what_fa" to "کار را به سه بخش موازی تقسیم کرد."))),
        "blockers" to ja(emptyList()), "outputs" to ja(emptyList()), "summary" to null,
        "parts" to ja(listOf(jo(
            "work_ref" to "W-000300", "state" to "running", "proposed_by" to "TY-CEO", "created_at" to ago(236), "merge_queued_at" to null,
            "parts" to ja(listOf(
                jo("n" to 1, "ref" to "W-000301", "title_fa" to "تحلیل فنی طلا در هفته‌ی گذشته", "role" to "analyst", "assignee" to "TY-ANL-1", "who_fa" to "تحلیلگر بازار تریدیار",
                    "state" to "delivered", "status" to "done", "progress_pct" to 100, "output_ref" to "O-000061", "output_title_fa" to "تحلیل فنی طلا: حمایت 2310 و مقاومت 2385",
                    "failed_fa" to null, "budget_tokens" to 200_000, "tokens_used" to 142_000),
                jo("n" to 2, "ref" to "W-000302", "title_fa" to "خبرهای مهم اقتصادی هفته", "role" to "researcher", "assignee" to "TY-RES-1", "who_fa" to "پژوهشگر تریدیار",
                    "state" to "working", "status" to "in_progress", "progress_pct" to 60, "output_ref" to null, "output_title_fa" to null, "failed_fa" to null, "budget_tokens" to 200_000, "tokens_used" to 88_000),
                jo("n" to 3, "ref" to "W-000303", "title_fa" to "نمودار مقایسه‌ی طلا و دلار", "role" to "designer", "assignee" to "TY-DSG-1", "who_fa" to "طراح تصویر تریدیار",
                    "state" to "failed", "status" to "failed", "progress_pct" to null, "output_ref" to null, "output_title_fa" to null,
                    "failed_fa" to "داده‌ی قیمت دلار برای سه روز آخر در دسترس نبود؛ نمودار ناقص میشد.", "budget_tokens" to 200_000, "tokens_used" to 31_000),
            )),
        ))),
        "workspaces" to ja(listOf(jo(
            "work_ref" to "W-000304", "server" to "tradeyar-main", "path" to "~/hq-workspace/W-000304", "state" to "working", "turns" to 7,
            "last_step_fa" to "متن ریلز نوشته شد و صدای آن در حال ساخت است.", "note_fa" to null, "where_fa" to "تریدیار · سرور اصلی",
            "session_ref" to "S-000221", "updated_at" to ago(6), "closed_at" to null, "remove_after" to null,
        ))),
    )

    // -------------------------------------------------------------- handler --
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        if (path == "/orders/F-0045/report" && method == "GET") return 200 to report45
        if (method == "POST" && Regex("^/work/[^/]+/stop$").matches(path)) return 200 to jo("work_ref" to "W-000304", "jobs_stopped" to 1, "workspace" to "stopped")
        if (path == "/work" && method == "GET" && query["q"] == "W-000304") return 200 to jo(
            "items" to ja(listOf(jo("id" to "5b0c1e7a-0000-4000-8000-000000000304", "ref" to "W-000304", "company" to "TY", "title" to "ساخت ریلز طلا روی سرور تریدیار", "status" to "in_progress",
                "kind" to "task", "priority" to "normal", "created_at" to ago(236)))),
            "next_cursor" to null,
        )
        // §33.2 payments
        Regex("^/companies/([A-Z0-9]+)/payment-sources$").find(path)?.let { m ->
            val list = sources[m.groupValues[1]] ?: return 404 to problem(404, "not_found", "این شرکت پیدا نشد.")
            if (method == "GET") return 200 to ja(list)
            if (method == "POST") {
                val b = body ?: JsonObject(emptyMap())
                val kind = b.str("kind") ?: "chain"
                val existing = list.indexOfFirst { it.str("kind") == kind && (kind == "ledger" || (it.str("network") == b.str("network") && it.str("address") == b.str("address"))) }
                val enabled = (b["enabled"] as? JsonPrimitive)?.contentOrNull?.toBooleanStrictOrNull() ?: true
                if (existing >= 0) {
                    list[existing] = list[existing].with("enabled" to enabled, "server" to (if (kind == "ledger") b.str("server") else null))
                    return 201 to list[existing]
                }
                val s = source("5b0c1e7a-0000-4000-8000-0000000000${srcSeq++}", m.groupValues[1], kind, if (kind == "ledger") "ledger_v1" else "chain_read",
                    b.str("network"), b.str("address"), b.str("server"), "not_configured", null, null).with("enabled" to enabled)
                list += s
                return 201 to s
            }
        }
        Regex("^/payment-sources/([^/]+)/read$").find(path)?.let { m ->
            if (method != "POST") return null
            val src = sources.values.flatten().firstOrNull { it.str("id") == m.groupValues[1] } ?: return 404 to problem(404, "not_found", "این منبع پیدا نشد.")
            val ledger = src.str("kind") == "ledger"
            return 200 to jo("source" to src.with("last_read_at" to now.toString(), "state" to "ok", "last_error_fa" to null), "queued" to ledger, "payments" to 0, "transfers" to if (ledger) 0 else 3, "pages" to if (ledger) 0 else 1)
        }
        Regex("^/companies/([A-Z0-9]+)/payments$").find(path)?.let { m ->
            if (method != "GET") return null
            val all = payments[m.groupValues[1]].orEmpty().filter { query["status"] == null || it.str("status") == query["status"] }
            val limit = query["limit"]?.toIntOrNull()?.coerceIn(1, 200) ?: 50
            val from = query["cursor"]?.toIntOrNull() ?: 0
            val page = all.drop(from).take(limit)
            return 200 to jo("items" to ja(page), "next_cursor" to if (from + limit < all.size) "${from + limit}" else null)
        }
        Regex("^/companies/([A-Z0-9]+)/reconcile$").find(path)?.let { m ->
            if (method != "GET") return null
            val to = query["to"]?.let(LocalDate::parse) ?: today
            val from = query["from"]?.let(LocalDate::parse) ?: to.minusDays(29)
            return 200 to ja(reconcile(m.groupValues[1], from, to))
        }
        // §33.3, §33.5
        if (path == "/revenue/board" && method == "GET") return 200 to board(query["company"])
        if (path == "/revenue/affiliate-gaps" && method == "GET") return 200 to ja(gaps.filter { (query["company"] == null || it.str("company") == query["company"]) && (query["state"] == null || it.str("state") == query["state"]) })
        // §33.1
        if (path == "/usage/reports") {
            if (method == "GET") return 200 to jo("items" to ja(usage.filter { query["period"] == null || it.str("period") == query["period"] }), "next_cursor" to null)
            if (method == "POST") {
                val period = body?.str("period") ?: "day"
                val r = report("UR-%04d".format(usageSeq++), period, if (period == "week") at(-7, 0) else at(-1, 0), at(0, 0), if (period == "week") 1.0 else 0.16, now.toString(),
                    listOf("همین حالا نوشته شد: مصرف مثل گزارش قبل است.", "بیشترین خرج هنوز با محتوای تریدیار است.", "چیز غیرعادی‌ای دیده نشد."), "پاسخ‌های آماده‌ی پشتیبانی را اول بیاور.")
                usage.add(0, r)
                return 201 to r
            }
        }
        // §33.4
        Regex("^/companies/([A-Z0-9]+)/leads$").find(path)?.let { m ->
            val code = m.groupValues[1]
            if (method == "GET") return 200 to jo("items" to ja(leads.values.filter { it.str("company") == code && (query["stage"] == null || it.str("stage") == query["stage"]) }.sortedByDescending { it.str("updated_at") }), "next_cursor" to null)
            if (method == "POST") {
                val ref = "LD-%06d".format(leadSeq++)
                val b = body ?: JsonObject(emptyMap())
                val l = lead(ref, b.str("source") ?: "manual", b.str("name_fa"), b.str("contact") ?: "mn-%04d".format(leadSeq), "new", (b["value_usdt"] as? JsonPrimitive)?.contentOrNull,
                    b.str("next_at"), b.str("next_fa"), now.toString(), listOf(ev(now.toString(), "created", b.str("note_fa") ?: "به دست تو ثبت شد."))).with("company" to code)
                leads[ref] = l
                return 201 to l
            }
        }
        Regex("^/leads/(LD-\\d+)(/draft)?$").find(path)?.let { m ->
            val l = leads[m.groupValues[1]] ?: return 404 to problem(404, "not_found", "این سرنخ پیدا نشد.")
            if (m.groupValues[2].isNotEmpty() && method == "POST") return 200 to jo(
                "lead" to l.str("ref"), "draft_fa" to "سلام، دوره‌ی آزمایشی شما فردا تمام میشود. اگر تحلیل‌های روزانه به کارتان آمده، پلن سالانه 249 USDT است و دو ماهش رایگان حساب میشود. هر سؤالی بود همین‌جا بپرسید.",
                "guard_ok" to true, "blocked_reasons" to ja(emptyList()), "sent" to false,
            )
            if (method == "GET") return 200 to l
            if (method == "PATCH") {
                val b = body ?: JsonObject(emptyMap())
                var x = l
                for (k in listOf("stage", "name_fa", "value_usdt", "next_at", "next_fa", "lost_reason_fa")) if (k in b) x = x.with(k to b[k])
                b.str("note_fa")?.let { n -> x = x.with("events" to ja((x["events"] as? JsonArray).orEmpty() + ev(now.toString(), "note", n))) }
                x = x.with("version" to ((x["version"] as? JsonPrimitive)?.contentOrNull?.toIntOrNull() ?: 1) + 1, "updated_at" to now.toString())
                leads[l.str("ref")!!] = x
                return 200 to x
            }
        }
        Regex("^/companies/([A-Z0-9]+)/pipeline$").find(path)?.let { m -> if (method == "GET") return 200 to pipeline(m.groupValues[1]) }
        // §33.8
        Regex("^/companies/([A-Z0-9]+)/journey$").find(path)?.let { m -> if (method == "GET") return 200 to journey(m.groupValues[1]) }
        if (path == "/journeys" && method == "GET") {
            val js = listOf("TY", "FX", "PC").map { journey(it) }
            val events = js.flatMap { j ->
                (j["stages"] as JsonArray).map { it as JsonObject }.filter { it.str("reached_at") != null }
                    .map { s -> jo("at" to s.str("reached_at"), "company" to j.str("company"), "stage" to s.str("key"), "title_fa" to s.str("title_fa")) }
            }.sortedByDescending { it.str("at") }
            return 200 to jo("journeys" to ja(js), "timeline" to ja(events))
        }
        // §33.9
        Regex("^/companies/([A-Z0-9]+)/personas(/suggest|/test)?$").find(path)?.let { m ->
            val code = m.groupValues[1]
            val list = personas.getOrPut(code) { mutableListOf() }
            when {
                m.groupValues[2].isEmpty() && method == "GET" -> return 200 to ja(list)
                m.groupValues[2].isEmpty() && method == "POST" -> {
                    val b = body ?: JsonObject(emptyMap())
                    val p = persona("a1e0c3d2-0000-4000-8000-0000000000${personaSeq++}", code, b.str("name_fa").orEmpty(), b.str("summary_fa").orEmpty(),
                        strs(b["pains_fa"]), strs(b["objections_fa"]), b.str("channel_fa").orEmpty(), b.str("source") ?: "owner")
                    list += p
                    return 201 to p
                }
                m.groupValues[2] == "/suggest" && method == "POST" -> return 200 to suggestion(code)
                m.groupValues[2] == "/test" && method == "POST" -> return 200 to test(code, body?.str("text").orEmpty())
            }
        }
        Regex("^/personas/([^/]+)$").find(path)?.let { m ->
            val id = m.groupValues[1]
            val (code, list) = personas.entries.firstOrNull { e -> e.value.any { it.str("id") == id } }?.let { it.key to it.value } ?: return 404 to problem(404, "not_found", "این مخاطب پیدا نشد.")
            val i = list.indexOfFirst { it.str("id") == id }
            if (method == "DELETE") { list.removeAt(i); return 204 to JsonObject(emptyMap()) }
            if (method == "PATCH") {
                var p = list[i]
                for ((k, v) in body.orEmpty()) if (v !is JsonNull) p = p.with(k to v)
                p = p.with("version" to ((p["version"] as? JsonPrimitive)?.contentOrNull?.toIntOrNull() ?: 1) + 1, "company" to code)
                list[i] = p
                return 200 to p
            }
        }
        return null
    }

    private fun suggestion(code: String) = jo(
        "company" to code, "basis_fa" to "از 42 مقاله‌ی دانشنامه و 180 گفت‌وگوی پشتیبانی سه ماه اخیر.",
        "personas" to ja(listOf(
            jo("name_fa" to "سرمایه‌گذار محتاط", "summary_fa" to "بیشتر از سود، حفظ سرمایه برایش مهم است؛ قبل از هر خرید سؤال زیاد میپرسد.",
                "pains_fa" to ja(listOf(JsonPrimitive("از نوسان شدید میترسد"))), "objections_fa" to ja(listOf(JsonPrimitive("سابقه‌ی سیگنال‌ها را میخواهد"))), "channel_fa" to "سایت و پشتیبانی"),
            jo("name_fa" to "دانشجوی اقتصاد", "summary_fa" to "میخواهد تحلیل یاد بگیرد، نه فقط سیگنال بگیرد؛ بودجه‌اش کم است.",
                "pains_fa" to ja(listOf(JsonPrimitive("منبع آموزشی فارسی منظم ندارد"))), "objections_fa" to ja(listOf(JsonPrimitive("پلن ماهانه برایش گران است"))), "channel_fa" to "اینستاگرام"),
        )),
    )

    private fun test(code: String, text: String): JsonObject {
        val list = personas[code].orEmpty()
        val scores = listOf(78, 52, 34)
        val res = list.mapIndexed { i, p ->
            val s = scores[i % scores.size]
            jo("persona" to p.str("id"), "name_fa" to p.str("name_fa"), "score" to s, "would_act" to (s >= 60),
                "objection_fa" to when (i) { 0 -> null; 1 -> "معلوم نیست هشدارها چند بار در روز میاید."; else -> "از پشتیبانی گروهی حرفی نزده." },
                "fix_fa" to when (i) { 0 -> "یک نمونه‌ی واقعی از سود هفته‌ی قبل اضافه کن."; 1 -> "بنویس فقط روزی یک گزارش کوتاه میاید."; else -> "یک خط درباره‌ی پلن گروهی و پشتیبانی فارسی بنویس." })
        }
        val avg = if (res.isEmpty()) 0 else scores.take(res.size).sum() / res.size
        return jo("id" to "c0ffee00-0000-4000-8000-000000000001", "text" to text, "results" to ja(res), "average" to avg, "lowest" to (scores.take(res.size).minOrNull() ?: 0), "at" to now.toString())
    }

    // ------------------------------------------------------------- builders --
    private fun source(id: String, co: String, kind: String, adapter: String, network: String?, address: String?, server: String?, state: String, read: String?, err: String?) = jo(
        "id" to id, "company" to co, "kind" to kind, "adapter" to adapter, "network" to network, "address" to address, "server" to server, "enabled" to true,
        "state" to state, "last_read_at" to read, "last_error_fa" to err,
    )

    private fun pay(n: Int, co: String, customer: String?, plan: String?, amount: String?, chain: String?, network: String?, daysAgo: Long, status: String, note: String? = null): JsonObject {
        val paid = today.minusDays(daysAgo).atTime(14 - n % 6, 10 + n).toInstant(ZoneOffset.UTC)
        return jo(
            "id" to "9a7e0000-0000-4000-8000-%012d".format(n), "company" to co, "source" to "5b0c1e7a-0000-4000-8000-000000000001", "ext_id" to "ord-%05d".format(4800 - n),
            "customer" to customer, "plan" to plan, "amount_usdt" to amount, "chain_amount" to (chain ?: amount.takeIf { network != null }), "network" to network,
            "tx_hash" to network?.let { if (it == "bsc_usdt") "0x" + "%064x".format(n * 7919L) else "%064x".format(n * 104729L) },
            "paid_at" to paid.toString(), "period_start" to paid.toString(), "period_end" to paid.plus(30, ChronoUnit.DAYS).toString(), "status" to status,
            "checked_at" to ago(15), "note_fa" to note,
        )
    }

    private fun gap(co: String, account: String, exchange: String, month: String, due: String, received: String, state: String, draft: String?, work: String?): JsonObject {
        val g = (due.toDouble() - received.toDouble()).coerceAtLeast(0.0)
        return jo(
            "company" to co, "account" to account, "exchange" to exchange, "month" to "$month-01", "due_usdt" to due, "received_usdt" to received,
            "gap_usdt" to "%.2f".format(java.util.Locale.US, g), "gap_pct" to if (due.toDouble() > 0) Math.round(g / due.toDouble() * 1000) / 10.0 else 0.0,
            "settles_on" to LocalDate.parse("$month-01").plusMonths(1).plusDays(9).toString(), "state" to state, "draft_fa" to draft, "work_ref" to work,
        )
    }

    private fun report(ref: String, period: String, from: String, to: String, k: Double, at: String, lines: List<String>, saving: String) = jo(
        "ref" to ref, "period" to period, "from" to from, "to" to to, "pack" to pack(period, from, to, k),
        "text" to jo("lines_fa" to ja(lines.map(::JsonPrimitive)), "saving_fa" to saving), "words" to "model", "at" to at,
    )

    private fun lead(ref: String, source: String, name: String?, contact: String, stage: String, value: String?, nextAt: String?, nextFa: String?, updated: String, events: List<JsonObject>, lost: String? = null) = jo(
        "ref" to ref, "company" to "TY", "source" to source, "name_fa" to name, "contact" to contact, "stage" to stage, "value_usdt" to value, "next_at" to nextAt,
        "next_fa" to nextFa, "assignee" to jo("kind" to "agent", "code" to "TY-SAL-1", "display_fa" to "کارشناس فروش تریدیار"), "lost_reason_fa" to lost,
        "events" to ja(events), "created_at" to (events.firstOrNull()?.str("at") ?: updated), "updated_at" to updated, "version" to 1,
    )

    private fun ev(at: String, kind: String, note: String) = jo("at" to at, "kind" to kind, "note_fa" to note)

    private fun persona(id: String, co: String, name: String, summary: String, pains: List<String>, objections: List<String>, channel: String, source: String) = jo(
        "id" to id, "company" to co, "name_fa" to name, "summary_fa" to summary, "pains_fa" to ja(pains.map(::JsonPrimitive)),
        "objections_fa" to ja(objections.map(::JsonPrimitive)), "channel_fa" to channel, "source" to source, "version" to 1,
    )

    // ------------------------------------------------------------- helpers --
    private fun strs(e: JsonElement?): List<String> = (e as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }.orEmpty()
    private fun JsonObject?.orEmpty(): JsonObject = this ?: JsonObject(emptyMap())
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
