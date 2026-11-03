package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * Debug builds only: contract §29 ⟨1.11⟩, the owner sees the business. Deterministic (every time from [HqClock], every figure fixed),
 * so the screenshots are the same on any machine.
 *
 * - **The home (§29.13):** an effective suggestion (TradeYar's weekly gold reels, from the content group), a good one (FX's free-signal
 *   page, from the council), a real move (TradeYar's search clicks 412 → 587), the morning in five lines, the content group's
 *   followers per company over 14 days, four orders in their states, and one critical item (Pro-Chart's site down 20 minutes).
 *   `POST /home/suggestions/{id}` runs (an order is made), defers or refuses with a reason.
 * - **Order reports (§29.2):** `F-0041` at work with its plan and steps, `F-0042` blocked (its publishing series unsealed, its budget
 *   short), `F-0043` delivered with its end summary and output, `F-0044` waiting; `POST /orders/{ref}/fix` clears a blocker.
 * - **The secretary (§29.4):** `POST /orders/preview` reads the company, the output and its count from the words, as the hub's rules do.
 * - **Rules (§29.3):** one sealed with its counts, one proposed, one retired; `POST /rules` makes a proposed one; the seal, a new version
 *   and retiring work.
 * - **Long voice (§29.5):** a session takes its chunks and answers the whole text.
 * - **The council v2 (§29.8):** `W-000222` (TradeYar's gold subscription), its roles, fact pack and the captain's plan.
 * - **Readiness, groups and connections (§29.9, §29.11, §29.12):** the content group with three member companies (Pro-Chart paused),
 *   seats, routines, runs, KPIs and the week's experiment; each company's connections with their daily figures and guides.
 * - **Employee state (§29.14):** every chart node and employee carries a state; TradeYar's graphic designer is stuck with its fix.
 */
internal class V29Demo(private val store: MutableMap<String, Pair<Int, JsonElement>>) {
    private val now = HqClock.now()
    private fun at(minAgo: Long): String = now.minus(minAgo, ChronoUnit.MINUTES).toString()
    private fun day(ago: Long): String = LocalDate.ofInstant(now, ZoneId.of("Asia/Tehran")).minusDays(ago).toString()

    private val suggestions = linkedMapOf<String, JsonObject>()
    private val reports = linkedMapOf<String, JsonObject>()
    private val rules = mutableListOf<JsonObject>()
    private val members = linkedMapOf<String, JsonObject>()
    private val routines = linkedMapOf<String, JsonObject>()
    private val connections = linkedMapOf<String, MutableList<JsonObject>>()
    private val sessions = mutableMapOf<String, Int>()
    private var ruleSeq = 30

    init {
        suggestions["sg-1"] = suggestion("sg-1", "effective", "TY", "سه ریلز هفتگی درباره‌ی سیگنال طلا در اینستاگرام تریدیار",
            "ریلزهای آموزشی طلا در دو هفته‌ی گذشته 3 برابر پست‌های معمولی دیده شدند و بیشتر دنبال‌کننده‌های تازه از همین ریلزها آمدند.",
            "حدود 1,200 دنبال‌کننده‌ی تازه در ماه", "حدود 400K واحد مصرف در هفته", "group", 180)
        suggestions["sg-2"] = suggestion("sg-2", "good", "FX", "صفحه‌ی «سیگنال رایگان طلا» برای جست‌وجوی گوگل",
            "جست‌وجوی «سیگنال طلا» در ماه گذشته 18% بیشتر شد و کوینه‌پرو FX هنوز صفحه‌ای برایش ندارد.",
            "ورودی جست‌وجو تا 15% بیشتر", "یک مقاله و یک صفحه، کمتر از 150K واحد مصرف", "council", 600)
        for (r in listOf(report41(), report42(), report43(), report44())) reports[r.str("ref")!!] = r
        rules += rule("SO-021", "هیچ پستی بدون منبع برای عددهایش منتشر نشود.", jo("roles" to ja(listOf(JsonPrimitive("media_director"), JsonPrimitive("scriptwriter")))), "sealed", "voice", 4300, jo("applied" to 46, "violations" to 2, "fixed" to 2))
        rules += rule("SO-022", "به هر پیام کاربر در پشتیبانی حداکثر دو ساعت بعد پاسخ داده شود.", jo("companies" to ja(listOf(JsonPrimitive("TY"), JsonPrimitive("FX")))), "proposed", "text", 40, null)
        rules += rule("SO-019", "هیچ کمپینی بیش از پنج درصد بودجه‌ی ماه را در یک روز خرج نکند.", JsonPrimitive("all"), "retired", "text", 12000, null)
        for (m in listOf(member("TY", "on", 9000, listOf("TY-MEDIA-MGR", "TY-MEDIA-01", "TY-MEDIA-02", "TY-MEDIA-03", "TY-GROWTH-02", "TY-GROWTH-01")),
            member("FX", "on", 9000, listOf("FX-MEDIA-MGR", "FX-MEDIA-01", null, null, "FX-GROWTH-MGR", null)),
            member("PC", "paused", 7000, listOf(null, null, null, null, "PC-GROWTH-MGR", null)))) members[m.str("company")!!] = m
        for (r in ROUTINES) routines[r.str("key")!!] = r
        connections["TY"] = mutableListOf(
            connection("TY", "search_console", "connected", "set", 300, null, listOf("clicks" to 587.0, "impressions" to 21_430.0, "ctr" to 2.7, "position" to 14.2)),
            connection("TY", "instagram", "connected", "set", 280, null, listOf("followers" to 12_480.0, "reach" to 48_200.0)),
            connection("TY", "telegram", "connected", "set", 270, null, listOf("members" to 9_350.0, "views" to 31_800.0)),
            connection("TY", "ga4", "error", "set", 1500, "دسترسی به گزارش‌ها رد شد؛ حساب سرویس هنوز به این ویژگی اضافه نشده.", emptyList()),
            connection("TY", "youtube", "not_connected", "missing", null, null, emptyList()),
            connection("TY", "pagespeed", "connected", "set", 400, null, listOf("score" to 86.0)),
        )
        connections["FX"] = mutableListOf(
            connection("FX", "search_console", "connected", "set", 310, null, listOf("clicks" to 1_204.0, "impressions" to 52_900.0)),
            connection("FX", "instagram", "connected", "set", 290, null, listOf("followers" to 8_940.0, "reach" to 22_100.0)),
            connection("FX", "telegram", "not_connected", "missing", null, null, emptyList()),
            connection("FX", "ga4", "not_connected", "missing", null, null, emptyList()),
        )
        connections["PC"] = mutableListOf(
            connection("PC", "search_console", "not_connected", "missing", null, null, emptyList()),
            connection("PC", "instagram", "not_connected", "missing", null, null, emptyList()),
        )
        states()
    }

    /** The §29 routes; null for everything else (the rest of the demo answers it). */
    @Synchronized
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        // The home and its suggestions.
        if (path == "/home" && method == "GET") return 200 to home()
        Regex("^/home/suggestions/([^/]+)$").find(path)?.let { m ->
            val id = m.groupValues[1]
            val s = suggestions[id] ?: return 404 to problem(404, "not_found", "این پیشنهاد پیدا نشد.")
            val action = body?.str("action") ?: "later"
            val updated = when (action) {
                "run" -> s.with("state" to "run", "order_ref" to "F-0045")
                "no" -> s.with("state" to "no", "reason_fa" to (body?.str("reason_fa") ?: ""))
                else -> s.with("state" to "later")
            }
            suggestions[id] = updated
            return 200 to (if (action == "run") updated.with("order_ref" to "F-0045") else updated)
        }
        // Orders: the secretary's preview, the reports and their fixes.
        if (path == "/orders/preview" && method == "POST") return 200 to preview(body?.str("text").orEmpty())
        Regex("^/orders/(F-\\d+)/report$").find(path)?.let { m ->
            return reports[m.groupValues[1]]?.let { 200 to it } ?: (404 to problem(404, "not_found", "گزارش این فرمان پیدا نشد."))
        }
        Regex("^/orders/(F-\\d+)/fix$").find(path)?.let { m ->
            val ref = m.groupValues[1]
            val r = reports[ref] ?: return 404 to problem(404, "not_found", "این فرمان پیدا نشد.")
            val action = body?.str("action")
            val left = r.arr("blockers").filter { (it["fix"] as? JsonObject)?.str("action") != action }
            val step = jo("at" to HqClock.now().toString(), "who_fa" to "مدیر کل", "what_fa" to (if (action == "budget.add") "بودجه را بیشتر کرد" else "مانع را برداشت"))
            reports[ref] = r.with("blockers" to ja(left), "steps" to ja(r.arr("steps") + step), "state" to (if (left.isEmpty()) "in_progress" else r.str("state")))
            return 200 to reports.getValue(ref)
        }
        // The owner's rules (standing orders): the list, a new one, a new version, retiring, and the standing order's own seal.
        if (path == "/rules") return when (method) {
            "GET" -> 200 to ja(rules.sortedByDescending { it.str("created_at") })
            "POST" -> {
                val text = body?.str("text").orEmpty().trim().trimEnd('.', '،', ' ') + "."
                val r = rule("SO-0${++ruleSeq}", text, JsonPrimitive("all"), "proposed", body?.str("source") ?: "text", 0, null)
                rules += r
                201 to r
            }
            else -> null
        }
        Regex("^/(?:rules|oversight/orders)/(SO-\\d+)(/seal|/retire)?$").find(path)?.let { m ->
            val ref = m.groupValues[1]
            val i = rules.indexOfFirst { it.str("ref") == ref }
            if (i < 0) return null
            val r = rules[i]
            val out = when {
                m.groupValues[2] == "/seal" -> r.with("status" to "sealed", "sealed_at" to HqClock.now().toString())
                m.groupValues[2] == "/retire" -> r.with("status" to "retired")
                method == "PUT" -> r.with("text_md" to (body?.str("text_md") ?: body?.str("text") ?: r.str("text_md")), "version" to ((r["version"] as? JsonPrimitive)?.contentOrNull?.toIntOrNull() ?: 1) + 1, "status" to "sealed", "sealed_at" to HqClock.now().toString())
                else -> return if (method == "GET") 200 to r else null
            }
            rules[i] = out
            return 200 to out
        }
        // Long voice: a session, its chunks, the whole text.
        if (path == "/transcribe/sessions" && method == "POST") {
            val id = "stt-${sessions.size + 1}"
            sessions[id] = 0
            return 201 to jo("id" to id, "expires_at" to HqClock.now().plus(30, ChronoUnit.MINUTES).toString(), "max_s" to 1200)
        }
        Regex("^/transcribe/sessions/([^/]+)/chunks/(\\d+)$").find(path)?.let { m ->
            sessions[m.groupValues[1]] = (sessions[m.groupValues[1]] ?: 0) + 1
            return 200 to JsonObject(emptyMap())
        }
        Regex("^/transcribe/sessions/([^/]+)/finish$").find(path)?.let { m ->
            val n = sessions.remove(m.groupValues[1]) ?: 0
            return 200 to jo("text" to LONG_TEXT, "duration_s" to 95.0 * maxOf(1, n), "chunks" to n, "segments" to ja(emptyList()))
        }
        // The council v2.
        if (method == "GET") when (path) {
            "/work/W-000222", "/work/$COUNCIL_ID" -> return 200 to councilWork()
            "/work/$COUNCIL_ID/council", "/work/W-000222/council" -> return 200 to councilV2()
            "/work/$COUNCIL_ID/events", "/work/W-000222/events" -> return 200 to jo("items" to ja(emptyList()), "next_cursor" to null)
            "/work/$COUNCIL_ID/runs", "/work/W-000222/runs" -> return 200 to ja(emptyList())
        }
        // Readiness, groups, connections.
        Regex("^/companies/([A-Z]{2,5})/readiness$").find(path)?.let { m -> return 200 to readiness(m.groupValues[1]) }
        if (path == "/groups" && method == "GET") return 200 to ja(listOf(group()))
        if (path == "/groups/content" && method == "GET") return 200 to group()
        if (path == "/groups/content/members" && method == "GET") return 200 to ja(members.values.toList())
        Regex("^/groups/content/members/([A-Z]{2,5})$").find(path)?.let { m ->
            val co = m.groupValues[1]
            val x = members[co] ?: return 404 to problem(404, "not_found", "این شرکت عضو نیست.")
            members[co] = x.with("state" to (body?.str("state") ?: x.str("state")))
            return 200 to members.getValue(co)
        }
        Regex("^/groups/content/routines/([a-z_]+)$").find(path)?.let { m ->
            val k = m.groupValues[1]
            val x = routines[k] ?: return 404 to problem(404, "not_found", "این کار روتین پیدا نشد.")
            routines[k] = x.with("state" to (body?.str("state") ?: x.str("state")))
            return 200 to routines.getValue(k)
        }
        if (path == "/groups/content/runs" && method == "GET") return 200 to ja(runs().filter { query["company"] == null || it.str("company") == query["company"] })
        if (path == "/groups/content/kpis" && method == "GET") return 200 to ja(kpis().filter { query["company"] == null || it.str("company") == query["company"] })
        if (path == "/groups/content/experiments" && method == "GET") return 200 to ja(experiments().filter { query["company"] == null || it.str("company") == query["company"] })
        Regex("^/companies/([A-Z]{2,5})/connections$").find(path)?.let { m -> return 200 to ja(connections[m.groupValues[1]].orEmpty()) }
        Regex("^/companies/([A-Z]{2,5})/connections/([a-z_0-9]+)(/secret|/test)?$").find(path)?.let { m ->
            val co = m.groupValues[1]; val kind = m.groupValues[2]
            val list = connections.getOrPut(co) { mutableListOf() }
            val i = list.indexOfFirst { it.str("kind") == kind }.takeIf { it >= 0 } ?: run { list += connection(co, kind, "not_connected", "missing", null, null, emptyList()); list.lastIndex }
            val x = list[i]
            list[i] = when (m.groupValues[3]) {
                "/secret" -> x.with("secret" to "set")
                "/test" -> x.with("state" to "connected", "last_error_fa" to null, "last_read_at" to HqClock.now().toString())
                else -> x.with("config" to (body?.get("config") as? JsonObject ?: x["config"]))
            }
            return when (m.groupValues[3]) {
                "/test" -> 200 to jo("ok" to true, "message_fa" to "وصل است؛ از فردا هر روز خوانده میشود.", "state" to "connected")
                "/secret" -> 200 to JsonObject(emptyMap())
                else -> 200 to list[i]
            }
        }
        Regex("^/connections/guides/([a-z_0-9]+)$").find(path)?.let { m -> return 200 to guide(m.groupValues[1]) }
        return null
    }

    // ------------------------------------------------------------------ home --
    private fun home(): JsonObject = jo(
        "cards" to jo(
            "effective" to suggestions["sg-1"],
            "good" to suggestions["sg-2"],
            "progress" to jo(
                "id" to "pg-1", "company" to "TY", "title_fa" to "کلیک‌های جست‌وجوی گوگل تریدیار بعد از سه مقاله‌ی آموزشی",
                "before" to jo("value" to 412, "at" to day(15)), "after" to jo("value" to 587, "at" to day(1)),
                "kpi" to "clicks", "source" to "search_console", "work_ref" to null,
            ),
        ),
        "morning" to ja(MORNING.map(::JsonPrimitive)),
        "groups" to ja(listOf(jo(
            "key" to "content", "title_fa" to "تولید محتوا و انتشار",
            "companies" to ja(listOf("TY" to "تریدیار", "FX" to "کوینه‌پرو FX", "PC" to "پرو-چارت").map { (co, name) ->
                jo("code" to co, "name_fa" to name, "kpi" to jo("key" to "followers", "title_fa" to "دنبال‌کننده‌ی اینستاگرام", "unit" to "", "series" to series(co, "followers")))
            }),
        ))),
        "orders" to ja(listOf(
            jo("ref" to "F-0041", "text_fa" to "برای تریدیار سه ریلز درباره‌ی سیگنال طلا بساز و در اینستاگرام منتشر کن.", "state" to "in_progress", "summary_fa" to ""),
            jo("ref" to "F-0042", "text_fa" to "برنامه‌ی انتشار هفتگی پرو-چارت را آماده کن.", "state" to (reports["F-0042"]?.str("state") ?: "blocked"), "summary_fa" to "گیر کرده: برنامه‌ی انتشار هنوز مُهر نشده."),
            jo("ref" to "F-0043", "text_fa" to "گزارش رقبای صرافی در 30 روز گذشته.", "state" to "delivered", "summary_fa" to "تحویل شد: کارمزد، کمپین‌ها و تغییرات سه رقیب، هر ادعا با منبع."),
            jo("ref" to "F-0044", "text_fa" to "مقاله‌ی آموزشی سطوح حمایت طلا برای سایت کوینه‌پرو FX.", "state" to "waiting", "summary_fa" to ""),
        )),
        "critical" to ja(listOf(jo(
            "id" to "n-crit-1", "level" to "urgent", "company" to "PC", "title_fa" to "سایت پرو-چارت 20 دقیقه است در دسترس نیست",
            "body_fa" to "مدیر فنی پرو-چارت روی آن است؛ کاربران الان نمیتوانند وارد شوند. اگر تا نیم ساعت دیگر برنگشت، خبر میدهیم.",
            "created_at" to at(20), "link" to jo("kind" to "server", "ref" to null), "domain" to "infra", "owner_visible" to true, "critical_reason" to "product_down",
        ))),
    )

    private fun suggestion(id: String, kind: String, co: String, title: String, why: String, impact: String, cost: String, source: String, ago: Long) = jo(
        "id" to id, "kind" to kind, "company" to co, "title_fa" to title, "why_fa" to why, "impact_fa" to impact, "cost_fa" to cost, "source" to source,
        "state" to "new", "reason_fa" to null, "order_ref" to null, "created_at" to at(ago),
    )

    /** 14 days of a KPI per company, fixed (a gap on one day for Pro-Chart: a day without a figure is a gap, never a zero). */
    private fun series(co: String, key: String): JsonArray {
        val base = when (co to key) { "TY" to "followers" -> 11_200.0; "FX" to "followers" -> 8_100.0; "PC" to "followers" -> 3_900.0
            "TY" to "clicks" -> 380.0; "FX" to "clicks" -> 960.0; else -> 120.0 }
        val step = when (co) { "TY" -> 0.0068; "FX" -> 0.0074; else -> 0.0021 }
        return ja((13 downTo 0).map { d ->
            val i = 13 - d
            val wobble = ((i * 7 + co.length * 3) % 5 - 2) * 0.002
            val v = if (co == "PC" && d == 6) null else Math.round(base * (1 + step * i + wobble)).toDouble()
            jo("day" to day(d.toLong()), "value" to v)
        })
    }

    // --------------------------------------------------------------- orders --
    private fun route(cos: List<String>, dept: String?, with: List<String>, kind: String, count: Int?, budget: Long, preview: String, why: String) = jo(
        "companies" to ja(cos.map(::JsonPrimitive)), "department" to dept, "collaborators" to ja(with.map(::JsonPrimitive)), "output_kind" to kind,
        "count" to count, "budget_tokens" to budget, "mode" to "single", "player" to "auto", "preview_fa" to preview, "confidence" to 0.9, "why_fa" to why, "kind" to "work",
    )

    private fun step(ago: Long, who: String, what: String) = jo("at" to at(ago), "who_fa" to who, "what_fa" to what)

    private fun report41() = jo(
        "ref" to "F-0041", "text_fa" to "برای تریدیار سه ریلز درباره‌ی سیگنال طلا بساز و در اینستاگرام منتشر کن.", "at" to at(150), "state" to "in_progress",
        "ack" to jo(
            "at" to at(148), "by" to jo("kind" to "agent", "code" to "TY-MEDIA-MGR", "display_fa" to "مدیر رسانه‌ی تریدیار"),
            "plan_fa" to "سناریست سه متن کوتاه از سیگنال‌های این هفته مینویسد، کارگردان ویدیو هر کدام را 30 ثانیه میسازد و پنجشنبه و جمعه ساعت 20 در برنامه‌ی انتشار مُهرشده منتشر میشوند.",
            "assigned" to ja(listOf(jo("company" to "TY", "code" to "TY-MEDIA-01", "title_fa" to "سناریست"), jo("company" to "TY", "code" to "TY-MEDIA-03", "title_fa" to "کارگردان ویدیو"))),
            "due_at" to now.plus(2, ChronoUnit.DAYS).toString(),
        ),
        "route" to route(listOf("TY"), "MEDIA", emptyList(), "reel", 3, 400_000, "→ تریدیار/رسانه و طراحی؛ خروجی: 3 ریلز؛ بودجه: 400K واحد مصرف", ""),
        "steps" to ja(listOf(
            step(150, "منشی هلدینگ", "فرمان رسید و به مدیر رسانه‌ی تریدیار سپرده شد."),
            step(148, "مدیر رسانه", "برنامه را نوشت: سه ریلز، پنجشنبه و جمعه."),
            step(120, "سناریست", "متن ریلز اول را نوشت و برای بازبینی گذاشت."),
            step(64, "کارگردان ویدیو", "ریلز اول را ساخت؛ بازبینی کیفیت قبول شد."),
            step(15, "سناریست", "متن ریلز دوم را نوشت."),
        )),
        "blockers" to ja(emptyList()), "outputs" to ja(listOf(jo("ref" to "O-000071", "title_fa" to "ریلز اول: سه سطح حمایت طلا در این هفته", "kind" to "reel"))),
        "summary" to null, "updated_at" to at(15),
    )

    private fun report42() = jo(
        "ref" to "F-0042", "text_fa" to "برنامه‌ی انتشار هفتگی پرو-چارت را آماده کن.", "at" to at(1440), "state" to "blocked",
        "ack" to jo("at" to at(1435), "by" to jo("kind" to "agent", "code" to "PC-CEO", "display_fa" to "مدیرعامل پرو-چارت"),
            "plan_fa" to "یک برنامه‌ی انتشار هفتگی برای اینستاگرام و تلگرام: سه پست و دو استوری در هفته، با موضوع‌های آموزشی نمودار.",
            "assigned" to ja(listOf(jo("company" to "PC", "code" to "PC-GROWTH-MGR", "title_fa" to "مدیر رشد"))), "due_at" to now.plus(1, ChronoUnit.DAYS).toString()),
        "route" to route(listOf("PC"), "GROWTH", emptyList(), "plan", null, 250_000, "→ پرو-چارت/رشد؛ خروجی: برنامه؛ بودجه: 250K واحد مصرف", ""),
        "steps" to ja(listOf(
            step(1440, "منشی هلدینگ", "فرمان رسید و به مدیرعامل پرو-چارت سپرده شد."),
            step(1435, "مدیرعامل پرو-چارت", "برنامه را نوشت و به مدیر رشد سپرد."),
            step(900, "مدیر رشد", "پیش‌نویس برنامه‌ی انتشار را برای مُهر فرستاد."),
            step(420, "ناظر", "کار ایستاد: پیش از مُهر برنامه، چیزی منتشر نمیشود."),
        )),
        "blockers" to ja(listOf(
            jo("kind" to "series_unsealed", "title_fa" to "برنامه‌ی انتشار پرو-چارت هنوز مُهر نشده", "detail_fa" to "تا مُهر تو، هیچ پستی ساخته یا منتشر نمیشود. کارت آن در کارتابل منتظر است.",
                "since" to at(900), "fix" to jo("action" to "series.seal", "label_fa" to "دیدن و مُهر برنامه", "target" to "D-000031")),
            jo("kind" to "budget", "title_fa" to "بودجه‌ی این فرمان کم آمد", "detail_fa" to "سه پیش‌نویس ساخته شد و بودجه‌ی 250K تمام شد؛ برای بقیه 100K دیگر لازم است.",
                "since" to at(420), "fix" to jo("action" to "budget.add", "label_fa" to "100K دیگر بده", "target" to "100000")),
        )),
        "outputs" to ja(emptyList()), "summary" to null, "updated_at" to at(420),
    )

    private fun report43() = jo(
        "ref" to "F-0043", "text_fa" to "گزارش رقبای صرافی در 30 روز گذشته.", "at" to at(3000), "state" to "delivered",
        "ack" to jo("at" to at(2995), "by" to jo("kind" to "agent", "code" to "TY-CEO", "display_fa" to "مدیرعامل تریدیار"),
            "plan_fa" to "مدیر رشد کارمزد و کمپین‌های سه رقیب اصلی را جمع میکند و تحلیلگر تغییرات محصولشان را؛ هر ادعا با منبع.",
            "assigned" to ja(listOf(jo("company" to "TY", "code" to "TY-GROWTH-MGR", "title_fa" to "مدیر رشد"), jo("company" to "TY", "code" to "TY-GROWTH-02", "title_fa" to "تحلیلگر کمپین"))),
            "due_at" to at(1500)),
        "route" to route(listOf("TY"), "GROWTH", emptyList(), "report", null, 300_000, "→ تریدیار/رشد؛ خروجی: گزارش؛ بودجه: 300K واحد مصرف", ""),
        "steps" to ja(listOf(
            step(3000, "منشی هلدینگ", "فرمان رسید و به مدیرعامل تریدیار سپرده شد."),
            step(2995, "مدیرعامل تریدیار", "برنامه را نوشت و کار را بین مدیر رشد و تحلیلگر تقسیم کرد."),
            step(2200, "تحلیلگر کمپین", "تغییرات محصول سه رقیب را با منبع تحویل داد."),
            step(1600, "مدیر رشد", "گزارش نهایی را نوشت و تحویل داد."),
        )),
        "blockers" to ja(emptyList()),
        "outputs" to ja(listOf(jo("ref" to "O-000046", "title_fa" to "رقبای صرافی در 30 روز: کارمزد، کمپین و محصول", "kind" to "report"))),
        "summary" to jo(
            "done_fa" to "گزارش سه رقیب تحویل شد: دو رقیب کارمزد معامله‌ی آنی را 10% کم کردند و یکی اپ موبایل تازه داد. هر ادعا منبع دارد.",
            "left_fa" to "کمپین‌های تلگرامی رقیب سوم هنوز بررسی نشده؛ مدیر رشد هفته‌ی بعد اضافه میکند.",
            "need_fa" to "اگر کاهش کارمزد را بخواهی، یک فرمان بده تا اثرش روی درآمد حساب شود.",
        ),
        "updated_at" to at(1600),
    )

    private fun report44() = jo(
        "ref" to "F-0044", "text_fa" to "مقاله‌ی آموزشی سطوح حمایت طلا برای سایت کوینه‌پرو FX.", "at" to at(400), "state" to "waiting",
        "ack" to null, "route" to route(listOf("FX"), "MEDIA", emptyList(), "article", 1, 150_000, "→ کوینه‌پرو FX/رسانه و طراحی؛ خروجی: 1 مقاله؛ بودجه: 150K واحد مصرف", ""),
        "steps" to ja(listOf(step(400, "منشی هلدینگ", "فرمان رسید و به مدیر رسانه‌ی کوینه‌پرو FX سپرده شد."))),
        "blockers" to ja(listOf(jo("kind" to "no_progress", "title_fa" to "ده دقیقه گذشت و برنامه‌ای نوشته نشد", "detail_fa" to "مدیرعامل کوینه‌پرو FX بیدار شد تا کار را راه بیندازد.", "since" to at(390), "fix" to null))),
        "outputs" to ja(emptyList()), "summary" to null, "updated_at" to at(390),
    )

    /** The secretary's rules, as the hub reads the words: the company, the output and its count, the department that owns it. */
    private fun preview(text: String): JsonObject {
        val co = when {
            Regex("پرو-?چارت|pro-?chart", RegexOption.IGNORE_CASE).containsMatchIn(text) -> "PC"
            Regex("FX|اف‌?ایکس|کوینه", RegexOption.IGNORE_CASE).containsMatchIn(text) -> "FX"
            else -> "TY"
        }
        val name = mapOf("TY" to "تریدیار", "FX" to "کوینه‌پرو FX", "PC" to "پرو-چارت").getValue(co)
        val kind = when {
            Regex("ریلز|کلیپ|ویدیو").containsMatchIn(text) -> "reel"
            Regex("استوری").containsMatchIn(text) -> "story"
            Regex("پست").containsMatchIn(text) -> "post"
            Regex("مقاله").containsMatchIn(text) -> "article"
            Regex("گزارش").containsMatchIn(text) -> "report"
            Regex("برنامه").containsMatchIn(text) -> "plan"
            else -> "other"
        }
        val count = Regex("(\\d+)|(یک|دو|سه|چهار|پنج|شش|هفت|هشت|نه|ده)\\s").find(text)?.let { m ->
            m.groupValues[1].toIntOrNull() ?: listOf("یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه", "ده").indexOf(m.groupValues[2]).plus(1).takeIf { it > 0 }
        }
        val media = kind in setOf("reel", "story", "post", "article")
        val dept = if (media) "MEDIA" else "GROWTH"
        val with = if (media && co != "FX" && Regex("اینستاگرام|انتشار|منتشر").containsMatchIn(text)) listOf("FX") else emptyList()
        val budget = when (kind) { "reel" -> 400_000L; "article" -> 150_000L; "post", "story" -> 120_000L; else -> 250_000L }
        val out = mapOf("reel" to "ریلز", "story" to "استوری", "post" to "پست", "article" to "مقاله", "report" to "گزارش", "plan" to "برنامه").getOrDefault(kind, "کار")
        val line = "→ $name/${if (media) "رسانه و طراحی" else "رشد"}" + (if (with.isNotEmpty()) " + کوینه‌پرو FX/انتشار" else "") +
            "؛ خروجی: ${count?.let { "$it " } ?: ""}$out؛ بودجه: ${budget / 1000}K واحد مصرف"
        return route(listOf(co), dept, with, kind, count, budget, line,
            if (media) "تولید محتوا با مدیر رسانه‌ی همان شرکت است؛ انتشار در اینستاگرام از راه کوینه‌پرو FX." else "این کار با دپارتمان رشد همان شرکت است.")
    }

    // ----------------------------------------------------------------- rules --
    private fun rule(ref: String, text: String, applies: JsonElement, status: String, source: String, ago: Long, counts: JsonObject?) = jo(
        "id" to "so-$ref", "ref" to ref, "text_md" to text, "source" to source, "file_id" to null, "applies_to" to applies, "status" to status, "version" to 1,
        "sealed_at" to (if (status == "sealed") at(ago - 5) else null), "created_at" to at(ago), "counts" to counts,
    )

    // --------------------------------------------------------------- council --
    private fun councilWork() = jo(
        "id" to COUNCIL_ID, "ref" to "W-000222", "company" to "TY", "title" to "برای فروش اشتراک طلایی تریدیار در سه ماه آینده چه کنیم؟",
        "brief" to "یک پرسش بیرونی: بازار، رقبا و قیمت. شورا با بسته‌ی واقعیت‌ها.", "kind" to "one_off", "priority" to "P2", "status" to "delivered",
        "assignee" to jo("code" to "TY-CEO", "company" to "TY", "kind" to "ceo", "department" to null, "title_fa" to "مدیرعامل تریدیار"),
        "created_by" to jo("kind" to "owner", "code" to "owner", "display_fa" to "مدیر کل"), "created_at" to at(500), "updated_at" to at(60),
        "player" to "auto", "mode" to "council",
    )

    private fun councilV2() = jo(
        "work_ref" to "W-000222", "state" to "done", "synthesis_ref" to null, "round" to 3,
        "roles" to jo("claude" to "captain", "gemini" to "researcher", "deepseek" to "numbers", "gpt" to "devil"),
        "fact_pack_ref" to "FP-0007",
        "fact_pack" to jo(
            "company" to "TY", "at" to at(510),
            "figures" to ja(listOf(
                jo("key" to "subscribers_gold", "title_fa" to "مشترک‌های طلایی فعال", "value" to 318, "source" to "hub", "at" to day(1)),
                jo("key" to "followers", "title_fa" to "دنبال‌کننده‌ی اینستاگرام", "value" to 12_480, "source" to "instagram", "at" to day(1)),
                jo("key" to "clicks", "title_fa" to "کلیک جست‌وجوی هفته", "value" to 587, "source" to "search_console", "at" to day(1)),
                jo("key" to "members", "title_fa" to "عضو کانال تلگرام", "value" to 9_350, "source" to "telegram", "at" to day(1)),
            )),
            "recent_posts" to ja(emptyList()), "notes_fa" to "قیمت اشتراک طلایی از شهریور ثابت مانده و نرخ تمدید ماه گذشته 71% بود.",
        ),
        "plan_md" to PLAN_MD,
        "members" to ja(listOf(
            jo("player" to "claude", "model" to "claude-sonnet-5-5", "state" to "done", "deliverable_ref" to "O-000081"),
            jo("player" to "gemini", "model" to "gemini-3.8", "state" to "done", "deliverable_ref" to "O-000082"),
            jo("player" to "deepseek", "model" to "deepseek-v3.2", "state" to "done", "deliverable_ref" to "O-000083"),
            jo("player" to "gpt", "model" to "gpt-5.5", "state" to "done", "deliverable_ref" to "O-000084"),
        )),
    )

    // ------------------------------------------------------- groups and more --
    private fun group(): JsonObject = jo(
        "key" to "content", "title_fa" to "تولید محتوا و انتشار",
        "purpose_fa" to "هر روز محتوای درست برای هر شرکت ساخته و در کانال‌هایش منتشر شود؛ با عدد سنجیده شود و هر هفته یک آزمایش، تا دنبال‌کننده و ورودی واقعی بیشتر شود.",
        "seats" to ja(SEATS.map { (k, role, title) -> jo("seat" to k, "role" to role, "title_fa" to title, "count" to 1) }),
        "routines" to ja(routines.values.toList()),
        "kpis" to ja(listOf(
            jo("key" to "followers", "title_fa" to "دنبال‌کننده‌ی اینستاگرام", "unit" to "", "source" to "instagram"),
            jo("key" to "clicks", "title_fa" to "کلیک جست‌وجوی گوگل", "unit" to "", "source" to "search_console"),
        )),
        "connections" to ja(listOf("instagram", "telegram", "search_console").map(::JsonPrimitive)), "eligible" to "has_channel", "state" to "on",
    )

    private fun member(co: String, state: String, joined: Long, who: List<String?>) = jo(
        "group" to "content", "company" to co, "state" to state, "joined_at" to at(joined),
        "seats" to ja(SEATS.mapIndexed { i, (k, _, _) -> jo("seat" to k, "employee" to who.getOrNull(i)) }),
    )

    private fun runs(): List<JsonObject> = listOf(
        Triple("TY", "daily_ideas", 70L) to ("done" to "سه ایده نوشته شد؛ یکی به ریلز تبدیل شد."),
        Triple("FX", "daily_ideas", 72L) to ("done" to "سه ایده نوشته شد."),
        Triple("TY", "daily_numbers", 160L) to ("done" to "عددهای دیروز خوانده و در گزارش صبح آمد."),
        Triple("FX", "daily_numbers", 161L) to ("failed" to "اتصال تلگرام وصل نیست؛ عدد کانال خوانده نشد."),
        Triple("PC", "daily_ideas", 75L) to ("skipped" to "پرو-چارت در کارگروه مکث کرده."),
        Triple("TY", "weekly_plan", 2900L) to ("done" to "برنامه‌ی هفته نوشته و برای مُهر رفت."),
    ).mapIndexed { i, (k, v) ->
        jo("id" to "rr-$i", "group" to "content", "company" to k.first, "routine" to k.second, "at" to at(k.third), "work_ref" to null, "state" to v.first, "note_fa" to v.second)
    }

    private fun kpis(): List<JsonObject> = listOf("TY", "FX", "PC").flatMap { co ->
        listOf(
            jo("key" to "followers", "title_fa" to "دنبال‌کننده‌ی اینستاگرام", "unit" to "", "company" to co, "series" to series(co, "followers")),
            jo("key" to "clicks", "title_fa" to "کلیک جست‌وجوی گوگل", "unit" to "", "company" to co, "series" to series(co, "clicks")),
        )
    }

    private fun experiments(): List<JsonObject> = listOf(
        jo("id" to "ex-1", "group" to "content", "company" to "TY", "week" to day(6), "hypothesis_fa" to "ریلزهای 30 ثانیه‌ای با زیرنویس فارسی 20% بیشتر از ریلزهای بدون زیرنویس دیده میشوند.",
            "metric" to "reach", "target" to "20%", "result" to "26%", "kept" to true),
        jo("id" to "ex-2", "group" to "content", "company" to "FX", "week" to day(2), "hypothesis_fa" to "انتشار ساعت 21 به‌جای 18 کلیک تلگرام را بیشتر میکند.",
            "metric" to "clicks", "target" to "10%", "result" to null, "kept" to null),
    )

    private fun readiness(co: String): JsonObject {
        fun check(key: String, ok: Boolean, title: String, detail: String, fix: JsonObject? = null) = jo("key" to key, "ok" to ok, "title_fa" to title, "detail_fa" to detail, "fix" to fix)
        val checks = when (co) {
            "TY" -> listOf(
                check("seats", true, "همه‌ی صندلی‌ها پر است", "شش نفر، همه فعال."),
                check("hiring", true, "استخدام خودکار روشن است", "صندلی خالی با منشور همان نقش پر میشود."),
                check("envelope", true, "بودجه‌ی ماه تعیین شده", ""),
                check("series", true, "برای هر کانال یک برنامه‌ی انتشار مُهرشده", "اینستاگرام و تلگرام."),
                check("connections", true, "کانال‌های انتشار وصل‌اند", "اینستاگرام و تلگرام."),
                check("media", true, "ابزار ساخت تصویر و صدا آماده است", ""),
            )
            "FX" -> listOf(
                check("seats", false, "سه صندلی خالی است", "طراح گرافیک، کارگردان ویدیو و تحلیلگر رشد.", jo("action" to "hire", "label_fa" to "پر کن", "target" to "FX")),
                check("hiring", true, "استخدام خودکار روشن است", ""),
                check("series", false, "تلگرام برنامه‌ی انتشار ندارد", "", jo("action" to "series.propose", "label_fa" to "برنامه بخواه", "target" to "FX/telegram")),
                check("connections", false, "تلگرام وصل نیست", "عدد کانال خوانده نمیشود.", jo("action" to "connection.guide", "label_fa" to "وصل کن", "target" to "FX/telegram")),
                check("media", true, "ابزار ساخت تصویر و صدا آماده است", ""),
            )
            else -> listOf(
                check("seats", false, "پنج صندلی خالی است", "", jo("action" to "hire", "label_fa" to "پر کن", "target" to co)),
                check("connections", false, "اینستاگرام وصل نیست", "", jo("action" to "connection.guide", "label_fa" to "وصل کن", "target" to "$co/instagram")),
                check("runner", false, "دستیار سرور شرکت آفلاین است", "مدیر فنی شرکت در جریان است."),
            )
        }
        return jo("company" to co, "group" to "content", "ready" to checks.all { (it["ok"] as JsonPrimitive).content == "true" }, "checks" to ja(checks))
    }

    private fun connection(co: String, kind: String, state: String, secret: String, readAgo: Long?, error: String?, figures: List<Pair<String, Double>>) = jo(
        "company" to co, "kind" to kind, "label_fa" to "", "state" to state, "config" to jo(), "secret" to secret,
        "last_read_at" to readAgo?.let { at(it) }, "last_error_fa" to error,
        "daily" to ja(figures.map { (k, v) -> jo("day" to day(1), "key" to k, "value" to v) }),
    )

    private fun guide(kind: String): JsonObject {
        val (title, fields) = when (kind) {
            "search_console" -> "وصل کردن سرچ کنسول گوگل" to listOf(jo("key" to "site_url", "label_fa" to "نشانی سایت", "hint_fa" to "https://tradeyar.com", "required" to true))
            "ga4" -> "وصل کردن گوگل آنالیتیکس" to listOf(jo("key" to "property_id", "label_fa" to "شناسه‌ی ویژگی", "hint_fa" to "properties/123456789", "required" to true))
            "instagram" -> "وصل کردن اینستاگرام" to listOf(jo("key" to "account", "label_fa" to "نام حساب", "hint_fa" to "@tradeyar", "required" to true))
            "telegram" -> "وصل کردن کانال تلگرام" to listOf(jo("key" to "channel", "label_fa" to "نام کانال", "hint_fa" to "@tradeyar_signals", "required" to true))
            else -> "وصل کردن" to emptyList()
        }
        return jo(
            "kind" to kind, "title_fa" to title,
            "body_md" to "1. حساب کاربری فقط‌خواندنی هلدینگ را در تنظیمات همین سرویس اضافه کن.\n2. نشانی یا نام حساب را این‌جا بنویس.\n3. کلید را یک بار بگذار؛ هیچ‌وقت نشان داده نمیشود.\n4. «آزمایش اتصال» را بزن. از فردا هر روز خوانده میشود.",
            "fields" to ja(fields), "secret_label_fa" to "کلید دسترسی",
        )
    }

    /** §29.14: every chart node and employee gets a state; one is stuck, with its fix. */
    private fun states() {
        fun stateOf(code: String, activity: String?): String = STATES[code] ?: when (activity) { "working" -> "working"; "waiting" -> "waiting"; "error" -> "stuck"; else -> "idle" }
        fun stamp(o: JsonObject): JsonObject {
            val code = o.str("code") ?: return o
            val s = stateOf(code, o.str("activity"))
            val kids = (o["children"] as? JsonArray)?.map { (it as? JsonObject)?.let(::stamp) ?: it }
            return JsonObject(o + mapOf("state" to JsonPrimitive(s), "stuck" to (if (s == "stuck") STUCK else JsonNull)) + (if (kids != null) mapOf("children" to JsonArray(kids)) else emptyMap()))
        }
        for (key in store.keys.toList()) {
            val (status, body) = store.getValue(key)
            when {
                Regex("^/org/[A-Z]+/chart$").matches(key) -> (body as? JsonObject)?.let { b ->
                    store[key] = status to JsonObject(b + ("roots" to JsonArray((b["roots"] as? JsonArray).orEmpty().map { (it as? JsonObject)?.let(::stamp) ?: it })))
                }
                Regex("^/employees/[A-Z0-9-]+$").matches(key) -> (body as? JsonObject)?.let { store[key] = status to stamp(it) }
                key.startsWith("/employees") -> (body as? JsonObject)?.let { b ->
                    val items = (b["items"] as? JsonArray) ?: return@let
                    store[key] = status to JsonObject(b + ("items" to JsonArray(items.map { (it as? JsonObject)?.let(::stamp) ?: it })))
                }
            }
        }
    }

    // ---------------------------------------------------------------- helpers --
    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
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

    companion object {
        /** Not a UUID: the orders' demo leaves it to this one. */
        const val COUNCIL_ID = "w-000222"

        /** A long dictation the hub turned into words (the long voice's session). */
        const val LONG_TEXT = "برای تریدیار یک برنامه‌ی محتوای یک‌ماهه بنویس: هر هفته سه ریلز آموزشی درباره‌ی طلا، دو پست از سیگنال‌های موفق هفته با منبع، و یک لایو کوتاه پنجشنبه‌ها. انتشار در اینستاگرام و تلگرام باشد و هر جمعه عددهای هفته را با هفته‌ی قبل مقایسه کن. بودجه از سقف ماه بیشتر نشود."

        val MORNING = listOf(
            "دیروز 4 خروجی تحویل شد: 2 ریلز تریدیار، یک مقاله‌ی کوینه‌پرو FX و گزارش رقبای صرافی.",
            "بهترین حرکت: کلیک‌های جست‌وجوی تریدیار به 587 رسید؛ 42% بیشتر از دو هفته پیش.",
            "دنبال‌کننده‌های اینستاگرام کوینه‌پرو FX به 8,940 رسید؛ 120 نفر بیشتر از پریروز.",
            "یک فرمان تو ایستاده: برنامه‌ی انتشار پرو-چارت هنوز مُهر نشده.",
            "منتظر تو: 2 کارت در کارتابل و یک قانون تازه برای مُهر.",
        )

        val SEATS = listOf(
            Triple("lead", "media_director", "مدیر رسانه"), Triple("writer", "scriptwriter", "سناریست"), Triple("designer", "visual_designer", "طراح گرافیک"),
            Triple("video", "video_director", "کارگردان ویدیو"), Triple("publisher", "growth_manager", "انتشار و کانال‌ها"), Triple("analyst", "growth_analyst", "تحلیلگر رشد"),
        )

        private fun r(key: String, title: String, seat: String, rrule: String, state: String = "on") = JsonObject(mapOf(
            "key" to JsonPrimitive(key), "title_fa" to JsonPrimitive(title), "seat" to JsonPrimitive(seat), "schedule" to JsonPrimitive(rrule),
            "brief_md" to JsonPrimitive(""), "max_tokens" to JsonPrimitive(60_000), "state" to JsonPrimitive(state),
        ))

        val ROUTINES = listOf(
            r("daily_ideas", "سه ایده‌ی محتوای امروز", "writer", "FREQ=DAILY;BYHOUR=9"),
            r("daily_numbers", "عددهای دیروز از اتصال‌ها", "analyst", "FREQ=DAILY;BYHOUR=8"),
            r("weekly_plan", "برنامه‌ی انتشار هفته", "lead", "FREQ=WEEKLY;BYDAY=SA;BYHOUR=10"),
            r("weekly_experiment", "آزمایش هفته", "analyst", "FREQ=WEEKLY;BYDAY=SA;BYHOUR=11", "paused"),
        )

        /** Fixed states beside the fixtures' activity: someone thinking, someone done, the designer stuck. */
        val STATES = mapOf("TY-MEDIA-01" to "thinking", "TY-MEDIA-02" to "stuck", "TY-GROWTH-02" to "done", "TY-CEO" to "waiting", "FX-CEO" to "idle")

        val STUCK = JsonObject(mapOf(
            "reason_fa" to JsonPrimitive("برای ساختن تصویرهای ریلز، برنامه‌ی انتشار مُهرشده لازم است؛ کارت آن منتظر مُهر توست."),
            "fix" to JsonObject(mapOf("action" to JsonPrimitive("series.seal"), "label_fa" to JsonPrimitive("دیدن و مُهر برنامه"), "target" to JsonPrimitive("D-000031"))),
        ))

        val PLAN_MD = """
            1. اشتراک طلایی را با «یک هفته‌ی رایگان» برای دنبال‌کننده‌های اینستاگرام عرضه کن؛ پژوهشگر نشان داد سه رقیب همین کار را کرده‌اند.
            2. قیمت را تا سه ماه ثابت نگه دار و به‌جایش گزارش هفتگی طلا را به اشتراک اضافه کن (حساب و عدد: تمدید تا 8% بیشتر).
            3. هر هفته دو ریلز از سیگنال‌های موفق، با منبع؛ منتقد: بدون منبع اعتماد را از دست میدهیم.
            4. بعد از سه ماه، با عددهای تمدید تصمیم بگیر.

            | چه کسی | چه کاری | تا کی |
            |---|---|---|
            | مدیر رشد تریدیار | پیشنهاد هفته‌ی رایگان | 7 روز |
            | مدیر رسانه | دو ریلز هفتگی | هر هفته |
            | تحلیلگر | گزارش تمدید | پایان ماه |
        """.trimIndent()
    }
}
