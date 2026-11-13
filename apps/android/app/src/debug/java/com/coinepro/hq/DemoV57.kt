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
 * Debug builds only: contract §57 ⟨1.35⟩, the session's team, one person at a time.
 *
 * - **The team (§57.1):** every session has its holder first and the people present (players left out). The content session of the
 *   demo is F-0094, Pro-Chart's daily reels: its holder at work (the draft in ChatGPT's queue), the scriptwriter filled and at work with
 *   a side talk of four lines (his last one unread), «کارگردان» and «موشن‌گرافی» empty, and the company's narrator (Kore). The other
 *   sessions are no content sessions here, so their screenshots keep the row only where someone besides the holder is present.
 * - **A side talk (§57.2, §57.3):** a page newest last (reading it marks the seat read); the owner's word is a side line at once, and the
 *   seat answers a few seconds later (the next read shows it). The holder's code is a 409 with the hub's sentence; a code that is no seat
 *   of the session a 404 of the hub's own.
 * - **A hire (§57.5):** an empty media seat filled at once; [TeamDemo.refuse] makes the hub refuse it (the month's envelope).
 */
internal object TeamDemo {
    @Volatile var refuse: Boolean = false
    fun reset() { refuse = false }
}

internal class V57Demo(private val v35: V35Demo, private val narrator: (String) -> JsonObject?) {
    private fun at(minAgo: Long): String = HqClock.now().minus(minAgo, ChronoUnit.MINUTES).toString()

    private class SeatState(
        var key: String, val role: String?, val roleFa: String, val holder: Boolean, var employee: JsonObject?, var state: String,
        val lines: MutableList<JsonObject> = mutableListOf(), var read: Int = 0,
        /** The seat's answer to the owner's last word, and when it lands (wall clock). */
        var pending: Pair<Long, String>? = null,
    )

    private val teams = mutableMapOf<String, MutableList<SeatState>>()
    private var lineSeq = 0

    private fun employee(code: String, title: String, company: String?) = jo("code" to code, "title_fa" to title, "company" to company)
    private fun line(who: String, whoFa: String, text: String, at: String) =
        jo("id" to "SL-%04d".format(++lineSeq), "at" to at, "who" to who, "who_fa" to whoFa, "text" to text, "work_ref" to null)

    /** The team of [order], made the first time it is asked for. */
    private fun team(order: String): MutableList<SeatState>? {
        teams[order]?.let { return it }
        val look = v35.look(order) ?: return null
        val seats = mutableListOf<SeatState>()
        val content = order in CONTENT
        seats += SeatState(
            if (content) "PC-CEO" else look.holder, null, "مسئول جلسه", true,
            employee(if (content) "PC-CEO" else look.holder, look.holderFa, look.company), if (content) "working" else "idle",
        )
        if (content) {
            val writer = SeatState("PC-SCR-01", "scriptwriter", "نویسنده", false, employee("PC-SCR-01", "سناریست پرو-چارت", "PC"), "working")
            val who = "سناریست پرو-چارت"
            writer.lines += line("owner", "مدیر کل", "متن ریلز اول را کوتاه‌تر کن؛ زیر یک دقیقه، و جمله‌ی اولش یک سؤال باشد.", at(30))
            writer.lines += line("seat", who, "باشه. نسخه‌ی ۴۵ ثانیه‌ای را مینویسم که با «خط روند را کجا بکشیم؟» شروع میشود؛ شعار «پرو چارت؛ همیشه با نمودار» آخرش میماند.", at(27))
            writer.lines += line("owner", "مدیر کل", "کلمه‌ی کامنت «چارت» باشد و کپشن هم کوتاه.", at(12))
            writer.lines += line("seat", who, "گذاشتم. پیش‌نویس تازه در صف ChatGPT است؛ جوابش که آمد همین‌جا میگویم و به مسئول جلسه هم میدهم.", at(6))
            writer.read = 3
            seats += writer
            seats += SeatState("role:video_director", "video_director", "کارگردان", false, null, "empty")
            seats += SeatState("role:motion_designer", "motion_designer", "موشن‌گرافی", false, null, "empty")
        }
        for (p in look.participants) {
            if (p.str("kind") != "person") continue
            val key = p.str("key") ?: continue
            val title = p.str("title_fa").orEmpty()
            seats += SeatState(key, null, title, false, employee(key, title, p.str("company")), "idle")
        }
        teams[order] = seats
        return seats
    }

    /** A seat's answer that is due now lands in its side talk. */
    private fun land(s: SeatState) {
        val (due, text) = s.pending ?: return
        if (System.currentTimeMillis() < due) return
        s.lines += line("seat", s.employee?.str("title_fa").orEmpty(), text, HqClock.now().toString())
        s.pending = null
        s.state = "idle"
    }

    private fun seatJson(s: SeatState): JsonObject {
        land(s)
        val last = s.lines.lastOrNull()
        return jo(
            "key" to s.key, "role" to s.role, "role_fa" to s.roleFa, "holder" to s.holder, "employee" to s.employee, "state" to s.state,
            "last" to last?.let { jo("at" to it.str("at"), "who" to it.str("who"), "text" to it.str("text")?.take(160)) },
            "unread" to s.lines.drop(s.read).count { it.str("who") == "seat" },
        )
    }

    private fun teamJson(order: String, seats: List<SeatState>): JsonObject {
        val company = v35.look(order)?.company
        return jo("seats" to JsonArray(seats.map(::seatJson)), "narrator" to if (order in CONTENT && company != null) narrator(company) else null)
    }

    @Synchronized
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        val m = Regex("^/orders/(F-\\d+)/team(?:/(hire)|/([^/]+)/(lines|say))?$").find(path) ?: return null
        val order = m.groupValues[1]
        val seats = team(order) ?: return 404 to problem(404, "not_found", "این جلسه پیدا نشد.", "no such order")
        if (m.groupValues[2] == "hire") {
            if (method != "POST") return null
            val role = body?.str("role").orEmpty()
            val s = seats.firstOrNull { it.role == role && it.employee == null }
                ?: return 422 to JsonObject(problem(422, "validation_failed", "این جایگاه در این جلسه خالی نیست.") + ("fields" to jo("role" to "no empty seat of this role")))
            if (TeamDemo.refuse) return 409 to problem(409, "envelope_exhausted", "پاکت این ماه پرو-چارت پر است؛ استخدام تازه به ماه بعد میماند.")
            val (code, title) = HIRES.getValue(role)
            s.key = code
            s.employee = employee(code, title, "PC")
            s.state = "idle"
            return 200 to teamJson(order, seats)
        }
        if (m.groupValues[3].isEmpty()) return if (method == "GET") 200 to teamJson(order, seats) else null
        val code = m.groupValues[3]
        val s = seats.firstOrNull { it.key == code && it.employee != null } ?: return 404 to problem(404, "not_found", "این آدم در این جلسه نیست.", "no such seat")
        if (m.groupValues[4] == "lines") {
            if (method != "GET") return null
            land(s)
            val limit = (query["limit"]?.toIntOrNull() ?: 50).coerceIn(1, 200)
            val before = query["before"]?.toIntOrNull()?.coerceIn(0, s.lines.size)
            val end = before ?: s.lines.size
            val start = (end - limit).coerceAtLeast(0)
            // the newest page read: the seat is read
            if (before == null) s.read = s.lines.size
            return 200 to jo("items" to JsonArray(s.lines.subList(start, end).toList()), "next_cursor" to if (start > 0) start.toString() else null)
        }
        if (method != "POST") return null
        if (s.holder) return 409 to problem(409, "validation_failed", "با مسئول جلسه از همین جای نوشتن حرف بزن.")
        val text = body?.str("text")?.trim().orEmpty()
        if (text.isEmpty()) return 422 to problem(422, "validation_failed", "حرفت را بنویس.")
        val said = line("owner", "مدیر کل", text.take(4_000), HqClock.now().toString())
        s.lines += said
        s.read = s.lines.size
        s.state = "working"
        s.pending = System.currentTimeMillis() + 3_500 to "باشه؛ همین را در کارم میگذارم و نتیجه را همین‌جا میگویم."
        return 200 to jo("line" to said, "work_ref" to "W-000431", "woken" to true)
    }

    private companion object {
        /** The demo's content sessions (§57.1): Pro-Chart's daily reels. */
        val CONTENT = setOf("F-0094")
        /** Who a hire of each media role brings into the session. */
        val HIRES = mapOf(
            "scriptwriter" to ("PC-SCR-02" to "سناریست دوم پرو-چارت"),
            "video_director" to ("PC-DIR-01" to "کارگردان پرو-چارت"),
            "motion_designer" to ("PC-MOT-01" to "موشن‌گرافیست پرو-چارت"),
        )
    }

    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
    private fun jo(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(kv.associate { (k, v) ->
        k to when (v) {
            null -> JsonNull; is JsonElement -> v; is String -> JsonPrimitive(v); is Number -> JsonPrimitive(v); is Boolean -> JsonPrimitive(v)
            else -> error("unsupported ${v::class}")
        }
    })
    private fun problem(status: Int, code: String, fa: String, detail: String? = null) =
        jo("code" to code, "message_fa" to fa, "status" to status, "title" to code, "type" to "about:blank", "detail" to detail)
}
