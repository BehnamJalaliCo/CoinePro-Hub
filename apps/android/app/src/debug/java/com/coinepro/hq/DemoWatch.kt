package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject

/**
 * Debug builds only: contract §28 ⟨1.10⟩ beside the outputs' bulk archive and delete ([OutputsDemo]).
 *
 * - **The catalogue (§28.2):** TradeYar's is done (products, automations, data, interfaces, code, risks; filed as `AR-000210`, delivered
 *   as `O-000170`); CoinePro FX has none (`404`) until the owner starts one, which reads `fx-main` for a few seconds and is done.
 * - **The watch (§28.3):** five protocols (the daily security sweep and app health, the weekly code review and growth memo, the monthly
 *   holding proposal) and their findings on `/oversight/findings`, each with its kind and proposed fix (a fix with a card or a session opens it; one without becomes a work item).
 * - **App error reports:** `POST /client/errors` takes a batch and says how many it kept.
 * - **A council that mostly failed (§28.4):** `W-000200`, TradeYar's "go through the server and extract everything", served on its own
 *   (it stays off the order lists): GPT failed with raw JSON, Gemini with an English recipe error, DeepSeek with a Persian reason;
 *   only Claude answered.
 */
internal class WatchDemo(private val store: MutableMap<String, Pair<Int, JsonElement>>) {
    private val catalogues = mutableMapOf<String, JsonObject>()
    private var startedAt = mutableMapOf<String, Long>()
    private var errorsKept = 0

    init {
        catalogues["TY"] = tradeyar()
        store["/deliverables/O-000170"] = 200 to catalogueOutput()
        val protocols = (store["/oversight/protocols"]?.second as? JsonArray).orEmpty()
        store["/oversight/protocols"] = 200 to JsonArray(protocols + PROTOCOLS.map { (ref, area, title) -> protocol(ref, area, title) })
        val page = store["/oversight/findings"]?.second as? JsonObject
        if (page != null) store["/oversight/findings"] = 200 to JsonObject(page + ("items" to JsonArray(page["items"]!!.jsonArray + findings())))
    }

    @Synchronized
    fun handle(method: String, path: String, body: JsonObject?): Pair<Int, JsonElement>? {
        Regex("^/companies/([A-Z]{2,5})/catalogue$").find(path)?.let { m ->
            val code = m.groupValues[1]
            return when (method) {
                "GET" -> catalogues[code]?.let { 200 to ripe(code, it) } ?: (404 to problem("not_found", "هنوز کاتالوگی برای این شرکت نیست."))
                "POST" -> {
                    if (catalogues[code]?.str("state") == "running") return 200 to catalogues.getValue(code)
                    startedAt[code] = System.currentTimeMillis()
                    val server = if (code == "TY") "ty-web" else if (code == "FX") "fx-main" else "${code.lowercase()}-main"
                    catalogues[code] = buildJsonObject {
                        put("company", code); put("at", HqClock.now().toString()); put("state", "running"); put("record", JsonNull); put("deliverable", JsonNull)
                        putJsonArray("servers") { add(buildJsonObject { put("id", "srv-${code.lowercase()}-1"); put("name", server); put("state", "running") }) }
                        put("sections", JsonArray(emptyList()))
                    }
                    200 to catalogues.getValue(code)
                }
                else -> null
            }
        }
        if (path == "/client/errors" && method == "POST") {
            val n = (body?.get("entries") as? JsonArray)?.size ?: 0
            errorsKept += n
            return 200 to buildJsonObject { put("accepted", n) }
        }
        // §28.4: the council that mostly failed, on its own work (not on the order lists).
        if (method == "GET") when (path) {
            "/work/W-000200", "/work/$FAILED_ID" -> return 200 to failedWork()
            "/work/$FAILED_ID/council", "/work/W-000200/council" -> return 200 to failedCouncil()
            "/work/$FAILED_ID/events", "/work/W-000200/events" -> return 200 to buildJsonObject { put("items", JsonArray(emptyList())); put("next_cursor", JsonNull) }
            "/work/$FAILED_ID/runs", "/work/W-000200/runs" -> return 200 to JsonArray(emptyList())
        }
        return null
    }

    /** A run the owner started is done a few seconds later, with the same sections TradeYar's has (FX's own words). */
    private fun ripe(code: String, k: JsonObject): JsonObject {
        val t0 = startedAt[code] ?: return k
        if (k.str("state") != "running" || System.currentTimeMillis() - t0 < 7_000) return k
        val done = if (code == "TY") tradeyar() else fx()
        catalogues[code] = done
        startedAt.remove(code)
        return done
    }

    // ------------------------------------------------------------- catalogue --
    private fun tradeyar(): JsonObject = catalogue("TY", "ty-web", -95, "AR-000210", "O-000170", listOf(
        section("products", "محصولات و سرویس‌ها", 7, "سایت و پنل تریدیار روی **ty-web**، با شش کانتینر و دو سرویس systemd؛ همه پشت Caddy.",
            table("کانتینرها و سرویس‌ها", listOf("نام", "نوع", "پورت", "دامنه", "کار"),
                row("tradeyar-web", "compose", "127.0.0.1:3000", "tradeyar.com", "سایت و پنل کاربر"),
                row("tradeyar-api", "compose", "127.0.0.1:8000", "api.tradeyar.com", "API سیگنال و حساب"),
                row("tradeyar-worker", "compose", "—", "—", "صف ارسال سیگنال و ایمیل"),
                row("postgres", "compose", "127.0.0.1:5432", "—", "دیتابیس اصلی"),
                row("redis", "compose", "127.0.0.1:6379", "—", "کش و صف"),
                row("n8n", "compose", "127.0.0.1:5678", "flow.tradeyar.com", "اتوماسیون‌ها"),
                row("caddy.service", "systemd", "80, 443", "—", "TLS و پراکسی"),
            )),
        section("automations", "اتوماسیون‌ها و زمان‌بندی‌ها", 9, "شش workflow در n8n و سه cron؛ یکی از workflowها در ۲۴ ساعت گذشته سه بار خطا داد.",
            table("n8n", listOf("workflow", "تریگر", "گره‌ها", "زمان‌بندی", "آخرین اجرا", "خطا"),
                row("signal-broadcast", "webhook", 14, "—", "۱۲ دقیقه پیش", "—"),
                row("daily-digest-email", "cron", 9, "08:00", "امروز ۰۸:۰۰", "—"),
                row("kyc-reminder", "cron", 6, "every 2h", "۴۰ دقیقه پیش", "3 × SMTP timeout"),
                row("telegram-sync", "webhook", 11, "—", "۳ دقیقه پیش", "—"),
                row("churn-winback", "cron", 8, "Sat 10:00", "شنبه", "—"),
                row("invoice-export", "manual", 5, "—", "۶ روز پیش", "—"),
            ),
            table("cron و timer", listOf("زمان", "فرمان", "کاربر"),
                row("0 3 * * *", "pg_dump → /backup", "tradeyar"),
                row("*/10 * * * *", "certbot renew --dry-run", "root"),
                row("30 4 * * 0", "docker image prune -f", "tradeyar"),
            )),
        section("data", "داده", 5, "دیتابیس **tradeyar** با ۴۱ جدول؛ بزرگ‌ترها پایین آمده‌اند (فقط تعداد ردیف، بی محتوا).",
            table("بزرگ‌ترین جدول‌ها", listOf("جدول", "ردیف", "اندازه"),
                row("signals", 1284331, "2.1 GB"), row("signal_deliveries", 9821140, "6.4 GB"), row("users", 48210, "38 MB"),
                row("subscriptions", 51877, "22 MB"), row("kyc_documents", 31120, "11 MB"),
            )),
        section("interfaces", "رابط‌ها", 4, "API با ۳۸ مسیر، ربات تلگرام با ۹ دستور و دو webhook بیرونی (فقط نام).",
            table("", listOf("رابط", "نوع", "جزئیات"),
                row("api.tradeyar.com", "REST", "۳۸ مسیر؛ /v1/signals، /v1/auth، /v1/billing…"),
                row("@TradeYarBot", "Telegram", "/start /signals /plan /support …"),
                row("Zarinpal", "webhook", "پرداخت اشتراک"),
                row("Kavenegar", "integration", "پیامک یادآوری"),
            )),
        section("code", "کد", 3, "سه ریپو؛ آخرین commit سایت دیروز. در لاگ API یک خطای تکراری: `TimeoutError` در ارسال ایمیل.",
            table("", listOf("ریپو", "شاخه", "آخرین commit"),
                row("tradeyar-web", "main", "دیروز · fix pricing table"),
                row("tradeyar-api", "main", "۳ روز پیش · signals pagination"),
                row("tradeyar-bot", "main", "۲ هفته پیش · plan command"),
            )),
        section("risks", "ریسک‌ها", 3, "سه ریسک؛ هیچ‌کدام بحرانی نیست.",
            table("", listOf("ریسک", "شدت", "چه باید کرد"),
                row("گواهی flow.tradeyar.com تا ۹ روز دیگر", "متوسط", "تمدید خودکار Caddy را بررسی کن"),
                row("Pillow 10.2 با CVE-2026-3311", "بالا", "به 11.1 ارتقا"),
                row("پورت 5678 روی IP خصوصی باز", "کم", "فقط 127.0.0.1"),
            )),
    ))

    private fun fx(): JsonObject = catalogue("FX", "fx-main", 0, "AR-000211", null, listOf(
        section("products", "محصولات و سرویس‌ها", 5, "موتور سیگنال فارکس و پنل ادمین روی **fx-main**؛ همه در docker compose.",
            table("کانتینرها", listOf("نام", "پورت", "کار"),
                row("api", "127.0.0.1:8000", "FastAPI"), row("worker", "—", "Celery"), row("beat", "—", "زمان‌بندی"),
                row("timescaledb", "127.0.0.1:5432", "داده‌ی کندل"), row("redis", "127.0.0.1:6379", "صف و کش"),
            )),
        section("risks", "ریسک‌ها", 1, "حافظه‌ی سرور در اوج به ۸۷٪ میرسد؛ LSTM خاموش بماند.",
            table("", listOf("ریسک", "شدت"), row("RAM 87% در اوج", "متوسط"))),
    ))

    private fun catalogue(code: String, server: String, minutes: Long, record: String?, out: String?, sections: List<JsonObject>) = buildJsonObject {
        put("company", code); put("at", HqClock.now().plus(minutes, ChronoUnit.MINUTES).toString()); put("state", "done")
        put("record", record?.let(::JsonPrimitive) ?: JsonNull); put("deliverable", out?.let(::JsonPrimitive) ?: JsonNull)
        putJsonArray("servers") { add(buildJsonObject { put("id", "srv-${code.lowercase()}-1"); put("name", server); put("state", "done") }) }
        put("sections", JsonArray(sections))
    }

    private fun section(key: String, title: String, count: Int, summary: String, vararg tables: JsonObject) = buildJsonObject {
        put("key", key); put("title_fa", title); put("count", count); put("summary_md", summary); put("tables", JsonArray(tables.toList()))
    }

    private fun table(title: String, columns: List<String>, vararg rows: JsonArray) = buildJsonObject {
        if (title.isNotEmpty()) put("title_fa", title)
        put("columns", JsonArray(columns.map(::JsonPrimitive)))
        put("rows", JsonArray(rows.toList()))
    }

    private fun row(vararg cells: Any) = buildJsonArray { for (x in cells) add(if (x is Number) JsonPrimitive(x) else JsonPrimitive(x.toString())) }

    private fun catalogueOutput() = buildJsonObject {
        put("id", "o-o-000170"); put("ref", "O-000170"); put("company", "TY"); put("work_id", JsonNull); put("work_ref", JsonNull)
        putJsonObject("producer") { put("code", "TY-CEO"); put("company", "TY"); put("kind", "ceo"); put("department", JsonNull); put("title_fa", "مدیرعامل تریدیار") }
        put("title", "کاتالوگ کامل تریدیار"); put("summary", "هفت سرویس، نه اتوماسیون، ۴۱ جدول، چهار رابط، سه ریپو و سه ریسک روی ty-web.")
        put("body", "## کاتالوگ\nجزئیات در سند بایگانی AR-000210.")
        put("attachments", JsonArray(emptyList())); put("evidence", JsonArray(emptyList())); put("produced_with", JsonObject(emptyMap())); put("usage", JsonObject(emptyMap()))
        put("rating", JsonNull); put("created_at", HqClock.now().minus(95, ChronoUnit.MINUTES).toString())
    }

    // ------------------------------------------------------------ the watch --
    private fun protocol(ref: String, area: String, title: String) = buildJsonObject {
        put("id", "p-${ref.lowercase()}"); put("ref", ref); put("title_fa", title); put("area", area); put("check_md", "see §28.3"); put("method", "llm")
        put("schedule", if (ref == "PR-134") "FREQ=MONTHLY;BYMONTHDAY=1;BYHOUR=9" else if (ref == "PR-132" || ref == "PR-133") "FREQ=WEEKLY;BYDAY=SA;BYHOUR=9" else "FREQ=DAILY;BYHOUR=6")
        put("scope", "holding"); put("evidence_md", ""); put("severity", "high"); put("answerable", "ceo"); put("status", "active"); put("version", 1); put("sealed_at", JsonNull)
        putJsonObject("last_run") { put("at", HqClock.now().minus(200, ChronoUnit.MINUTES).toString()); put("result", "fail"); put("findings", 1) }
    }

    private fun findings(): List<JsonObject> {
        fun f(ref: String, co: String, protocol: String, kind: String?, sev: String, status: String, title: String, body: String, fix: String, fixRef: String? = null, fixKind: String = "work", min: Long) = buildJsonObject {
            put("id", "f-${ref.lowercase()}"); put("ref", ref); put("company", co); put("protocol", protocol); put("severity", sev); put("status", status)
            put("title_fa", title); put("body_md", body); put("evidence", JsonArray(emptyList()))
            putJsonObject("answerable") { put("kind", "ceo"); put("code", "$co-CEO"); put("display_fa", "مدیرعامل") }
            put("due_at", HqClock.now().plus(1, ChronoUnit.DAYS).toString()); put("opened_at", HqClock.now().minus(min, ChronoUnit.MINUTES).toString())
            put("closed_at", JsonNull); put("history", JsonArray(emptyList()))
            if (kind != null) put("kind", kind)
            put("fix_md", fix)
            if (fixRef != null) putJsonObject("fix") { put("kind", fixKind); put("ref", fixRef) }
        }
        return listOf(
            f("FI-0020", "TY", "PR-130", "security", "high", "open", "Pillow 10.2 با CVE-2026-3311 در tradeyar-api",
                "در lock فایل API تریدیار نسخه‌ی آسیب‌پذیر Pillow هست؛ مسیر آپلود مدارک KYC از آن استفاده میکند.",
                "ارتقای Pillow به 11.1 در tradeyar-api، اجرای تست‌های آپلود، انتشار با مُهر تو.", min = 180),
            f("FI-0021", "FX", "PR-130", "security", "medium", "open", "پورت 5678 روی IP خصوصی fx-main باز است",
                "n8n روی 10.10.1.2:5678 گوش میدهد؛ فهرست مورد انتظار فقط 127.0.0.1 است.",
                "در compose پورت را به 127.0.0.1 ببند و سرویس را دوباره بالا بیاور.", min = 240),
            f("FI-0022", "HQ", "PR-131", null, "high", "open", "۱۲ خطای decode در صفحه‌ی خروجی‌ها (اندروید 0.9.0)",
                "خطاخوان ۱۲ گوشی همین خطا را فرستاده: `$.items[3].usage` عدد به‌جای شیء. علت در `deliverables.py` خط 212 است.",
                "در API، `usage` خالی را `{}` بفرست نه `0`؛ یک تست قرارداد اضافه شود.", min = 95),
            f("FI-0023", "TY", "PR-132", "code", "medium", "open", "تست نداشتن مسیر لغو اشتراک در tradeyar-api",
                "بازبینی هفتگی: `billing/cancel.py` بی‌تست است و یک except خالی خطای پرداخت را میبلعد.",
                "دو تست برای لغو اشتراک و حذف except خالی.", min = 600),
            f("FI-0024", "TY", "PR-133", "growth", "info", "open", "یادآوری KYC دو ساعت بعد از ثبت‌نام",
                "مشاور کل: ۴۱٪ کاربران در تأیید هویت رها میکنند؛ یادآوری زودتر و راهنمای تصویری بیشترین اثر را دارد (+۰.۶ واحد تبدیل).",
                "کار برای تیم رشد تریدیار: یادآوری پیامکی دو ساعت بعد و راهنمای تصویری تأیید هویت.", min = 1300),
            f("FI-0025", "HQ", "PR-134", "holding", "low", "open", "سیگنال‌های FX در ربات تریدیار",
                "مدیر کل دیجیتال: کاربران پلن طلایی تریدیار سیگنال فارکس هم میخواهند؛ API سیگنال FX آماده‌ی اشتراک است.",
                "پیشنهاد هلدینگ: یک آزمون یک‌ماهه با ۲۰۰ کاربر و تقسیم درآمد ۵۰/۵۰.", min = 2900),
        )
    }

    // ------------------------------------------------- the council of §28.4 --
    private fun failedWork() = buildJsonObject {
        put("id", FAILED_ID); put("ref", "W-000200"); put("company", "TY"); put("title", "سرور تریدیار را بگرد و همه‌چیز را دربیاور")
        put("brief", "هرچه روی سرور تریدیار هست: سرویس‌ها، اتوماسیون‌ها، داده و ریسک‌ها."); put("kind", "one_off"); put("priority", "P2"); put("status", "delivered")
        putJsonObject("assignee") { put("code", "TY-CEO"); put("company", "TY"); put("kind", "ceo"); put("department", JsonNull); put("title_fa", "مدیرعامل تریدیار") }
        putJsonObject("created_by") { put("kind", "owner"); put("code", "owner"); put("display_fa", "مالک") }
        put("created_at", HqClock.now().minus(300, ChronoUnit.MINUTES).toString()); put("updated_at", HqClock.now().minus(240, ChronoUnit.MINUTES).toString())
        put("player", "auto"); put("mode", "council")
    }

    private fun failedCouncil() = buildJsonObject {
        put("work_ref", "W-000200"); put("state", "done"); put("synthesis_ref", JsonNull)
        putJsonArray("members") {
            add(buildJsonObject { put("player", "claude"); put("model", "claude-sonnet-5-5"); put("state", "done"); put("deliverable_ref", "O-000170") })
            add(buildJsonObject { put("player", "gpt"); put("model", "gpt-5.3"); put("state", "failed"); put("reason", """{"error":{"type":"invalid_request_error","code":"model_not_found","message":"The model `gpt-5.3` is not supported when using Codex with a ChatGPT account."}}""") })
            add(buildJsonObject { put("player", "gemini"); put("model", "gemini-3.8"); put("state", "failed"); put("reason", "recipe_failed: selector [data-test-id=send-button] not found after 30000ms") })
            add(buildJsonObject { put("player", "deepseek"); put("model", "deepseek-v3.2"); put("state", "failed"); put("reason", "مرورگر هاب از حساب DeepSeek بیرون آمده بود؛ یک بار دوباره امتحان شد و نشد. تا ورود دوباره کنار میماند.") })
        }
    }

    private fun problem(code: String, fa: String) = buildJsonObject { put("code", code); put("message_fa", fa); put("status", 404); put("title", code); put("type", "about:blank") }

    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.content

    private companion object {
        /** Not a UUID: the orders' demo leaves it to this one. */
        const val FAILED_ID = "w-000200"

        val PROTOCOLS = listOf(
            Triple("PR-130", "security", "پایش امنیتی روزانه: پورت، CVE، TLS، ورود ناموفق، رمز در ریپو، backup"),
            Triple("PR-131", "quality", "سلامت اپ: خطاهایی که اپ‌ها فرستاده‌اند"),
            Triple("PR-132", "quality", "بازبینی کد هفتگی هر ریپو"),
            Triple("PR-133", "product", "یادداشت رشد هفتگی مشاور کل"),
            Triple("PR-134", "owner", "پیشنهاد هلدینگ ماهانه‌ی مدیر کل دیجیتال"),
        )
    }
}
