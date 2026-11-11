package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.OWNER_TZ
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Debug builds only: contract §55 ⟨1.33⟩, what the 1.0.1 look reads, in every new state so the screenshots and the demo show each one.
 *
 * - **The limits (§55.3, `GET /treasury/limits`):** the owner's Claude accounts and today's meter. The demo's own state is the everyday
 *   one (the main account works, the second is ready, the day is calm). [LookDemo.limits] asks for the others: `both-full` (every
 *   account full, the queue waits), `warm` (the main one full, the second works; the day past 70 %), `near` (one off, one unknown; the
 *   day past 90 %), `full-day` (the day's cap is reached), `unknown` (no figure read yet), `old` (a hub before §55: the route answers 404).
 * - **The command sheet's order:** with [LookDemo.orderFails] the hub refuses a new order (503 with its Persian sentence), so the
 *   sheet's failure is seen; an order that names its company goes on to the demo's own order route.
 * - **The pulse's series:** the demo's live summary carries a 24-hour series for each figure of the office pulse ([LookDemo.series]).
 * - **The session (§54, §55.1):** [LookDemo.ring] `late` puts the workshop turn of F-0090 at 56 of its 60 minutes; [LookDemo.old55] is a
 *   hub before §55 (no mood, no kind of turn, no `direct`): the app reads the mood from what the activity says.
 * - **The publish desk (§55.2, `GET /publish-desk`):** [LookDemo.desk] `full` (the outputs' own desk, [OutputsDemo.desk]), `empty`,
 *   `old` (the route answers 404).
 * - **A sealed working group's runs:** `GET /groups/pb_1/runs` (TradeYar's last runs, one in the queue; CoinePro FX's that failed) and
 *   `POST /groups/pb_1/members/{code}` (a member started again, or held).
 */
internal object LookDemo {
    @Volatile var limits: String = "calm"
    @Volatile var orderFails: Boolean = false
    @Volatile var series: Boolean = true
    @Volatile var ring: String = "calm"
    @Volatile var old55: Boolean = false
    @Volatile var desk: String = "full"

    fun reset() { limits = "calm"; orderFails = false; series = true; ring = "calm"; old55 = false; desk = "full" }

    /** The last 24 hours of the pulse's figures, oldest first (an hour apart), ending on what the pulse shows now. */
    fun pulseSeries(working: Int, sessions: Int, waiting: Int): JsonObject = buildJsonObject {
        fun line(last: Int, shape: List<Int>) = JsonArray(shape.map { JsonPrimitive(maxOf(0, last + it)) } + JsonPrimitive(last))
        put("working", line(working, listOf(-5, -5, -4, -5, -3, -2, -1, 0, 1, 2, 1, 0, -1, 0, 1, 2, 3, 2, 1, 1, 0, -1, 0)))
        put("sessions", line(sessions, listOf(-2, -2, -2, -1, -1, -1, 0, 0, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0)))
        put("waiting", line(waiting, listOf(-9, -9, -8, -8, -8, -7, -6, -6, -5, -5, -4, -4, -3, -3, -3, -2, -2, -2, -1, -1, -1, 0, 0)))
        put("until", HqClock.now().toString())
    }
}

internal class V55Demo(
    /** The publish desk of the outputs' demo, for a company or for all. */
    private val desk: (String?) -> JsonObject = { JsonObject(emptyMap()) },
    /** A member of a sealed working group started again or held (the playbooks' demo follows): group key, company, state. */
    private val member: (String, String, String) -> Boolean = { _, _, _ -> false },
) {
    private fun inMin(n: Long): String = HqClock.now().plus(n, ChronoUnit.MINUTES).toString()
    private fun agoMin(n: Long): String = HqClock.now().minus(n, ChronoUnit.MINUTES).toString()

    /** Midnight of the owner's zone: when today's meter starts again. */
    private fun nextMidnight(): String {
        val zone = ZoneId.of(OWNER_TZ)
        return HqClock.now().atZone(zone).toLocalDate().plusDays(1).atStartOfDay(zone).toInstant().toString()
    }

    private fun account(key: String, name: String, state: String, utilization: String?, resetsIn: Long?, read: Boolean = true) = buildJsonObject {
        put("key", key); put("name_fa", name); put("state", state); put("utilization", utilization); put("window_fa", "پنجره‌ی پنج‌ساعته")
        put("resets_at", resetsIn?.let(::inMin)); put("observed_at", if (read) agoMin(2) else null)
    }

    private fun meter(spent: Long, cap: Long, note: String) = buildJsonObject {
        val share = if (cap > 0) spent.toDouble() / cap else 0.0
        put("spent", spent); put("cap", cap); put("share", String.format(java.util.Locale.US, "%.4f", share))
        put("state", when { share >= 1 -> "full"; share >= 0.9 -> "near"; share >= 0.7 -> "warm"; else -> "calm" })
        put("resets_at", nextMidnight()); put("note_fa", note)
    }

    private fun limits(): JsonObject {
        val main = "اکانت اصلی"
        val second = "اکانت دوم"
        fun out(accounts: List<JsonObject>, waiting: Boolean, today: JsonObject) = buildJsonObject { put("accounts", JsonArray(accounts)); put("waiting", waiting); put("today", today) }
        return when (LookDemo.limits) {
            "both-full" -> out(listOf(account("main", main, "full", "1", 130), account("second", second, "full", "0.98", 220)), true, meter(546_000, 600_000, "مصرف امروز به ۹۰٪ سقف نزدیک شده؛ کارهای کم‌اهمیت به فردا میروند."))
            "warm" -> out(listOf(account("main", main, "full", "1", 65), account("second", second, "working", "0.41", 190)), false, meter(456_000, 600_000, "از ۷۰٪ سقف امروز گذشته‌ای؛ هنوز جا هست."))
            "near" -> out(listOf(account("main", main, "off", null, null, read = false), account("second", second, "working", null, null)), false, meter(558_000, 600_000, "مصرف امروز به ۹۰٪ سقف نزدیک شده؛ کارهای کم‌اهمیت به فردا میروند."))
            "full-day" -> out(listOf(account("main", main, "ready", "0.74", 95), account("second", second, "ready", "0.12", 240)), false, meter(612_000, 600_000, "سقف امروز پر شد؛ فقط کارهای فوری اجرا میشوند."))
            "unknown" -> out(listOf(account("main", main, "ready", null, null, read = false), account("second", second, "ready", null, null, read = false)), false, meter(0, 600_000, "مصرف امروز آرام است."))
            else -> out(listOf(account("main", main, "working", "0.62", 148), account("second", second, "ready", "0.08", 263)), false, meter(412_000, 600_000, "مصرف امروز آرام است."))
        }
    }

    private fun problem(status: Int, code: String, fa: String, detail: String? = null) = buildJsonObject {
        put("type", "about:blank"); put("title", code); put("status", status); put("code", code); put("message_fa", fa)
        if (detail != null) put("detail", detail)
    }

    // ------------------------------------------------------------------ a sealed working group's runs --
    private var runSeq = 0
    private fun run(company: String, routine: String, minAgo: Long, state: String, note: String = "") = buildJsonObject {
        put("id", "0193c0de-55a0-7000-8000-%012d".format(++runSeq)); put("group", "pb_1"); put("company", company); put("routine", routine)
        put("at", agoMin(minAgo)); put("work_ref", null as String?); put("state", state); put("note_fa", note)
    }
    private val day = 24 * 60L
    /** TradeYar: the day's topic and cover over the last days (one skipped, one failed), the reels of the week, and today's cover in
     *  the queue. CoinePro FX: three that failed, after which the group stood still there. */
    private val runs: List<JsonObject> by lazy {
        val ty = (1L..8L).flatMap { d ->
            listOf(
                run("TY", "topic", d * day - 180, if (d == 4L) "skipped" else "done", if (d == 4L) "تعطیل رسمی بود؛ نوبت رد شد." else ""),
                run("TY", "cover", d * day - 60, if (d == 2L) "failed" else "done", if (d == 2L) "کاور آن روز ساخته نشد؛ سازنده‌ی تصویر جواب نداد." else ""),
            )
        } + listOf(1L, 3L, 6L).map { d -> run("TY", "reels", d * day - 1_000, "done") } + run("TY", "weekly", 2 * day - 700, "done")
        val fx = (9L..11L).map { d -> run("FX", "topic", d * day, "failed", "سه نوبت پشت هم بسته‌ای تحویل نشد؛ کارگروه در این شرکت ایستاد.") }
        ty + run("TY", "topic", 180, "done") + run("TY", "cover", 2, "queued") + fx
    }

    /** §55 and the command sheet's order; what is not its own goes on (null) to the rest of the demo. */
    @Synchronized
    fun handle(method: String, path: String, body: JsonObject?, query: Map<String, String?> = emptyMap()): Pair<Int, JsonElement>? {
        // §55.2 the publish desk (a hub before it has no such route: the framework's own 404)
        if (path == "/publish-desk" && method == "GET") return when (LookDemo.desk) {
            "old" -> 404 to problem(404, "not_found", "پیدا نشد.", "Not Found")
            "empty" -> 200 to buildJsonObject { put("ready", JsonArray(emptyList())); put("queue", JsonArray(emptyList())); put("done", JsonArray(emptyList())) }
            else -> {
                val company = query["company"]
                if (company != null && company !in setOf("HQ", "TY", "FX", "PC")) 404 to problem(404, "not_found", "این شرکت پیدا نشد.", "no such company")
                else 200 to desk(company)
            }
        }
        if (path == "/groups/pb_1/runs" && method == "GET") return 200 to JsonArray(runs.filter { query["company"] == null || (it["company"] as? JsonPrimitive)?.content == query["company"] }.sortedByDescending { (it["at"] as JsonPrimitive).content })
        Regex("^/groups/(pb_\\d+)/members/([A-Z]{2,5})$").find(path)?.let { m ->
            if (method != "PUT") return null
            val state = (body?.get("state") as? JsonPrimitive)?.content ?: "on"
            return if (member(m.groupValues[1], m.groupValues[2], state)) 200 to buildJsonObject { put("group", m.groupValues[1]); put("company", m.groupValues[2]); put("state", state) }
            else 404 to problem(404, "not_found", "این شرکت عضو این کارگروه نیست.", "no such member")
        }
        if (path == "/orders" && method == "POST" && LookDemo.orderFails) return 503 to problem(503, "hub_unavailable", "ستاد الان جواب نمیدهد؛ کمی بعد دوباره بزن.")
        if (path == "/treasury/limits" && method == "GET") {
            // A hub before §55 has no such route: the framework's own 404.
            return if (LookDemo.limits == "old") 404 to problem(404, "not_found", "پیدا نشد.", "Not Found") else 200 to limits()
        }
        return null
    }
}
