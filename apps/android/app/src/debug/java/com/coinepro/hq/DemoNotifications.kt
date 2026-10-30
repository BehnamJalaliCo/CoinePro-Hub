package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject

/**
 * Debug builds only: notifications as the hub serves them (contract §6, `routes/notifications.py`), with what the owner met on the phone:
 * the overseer's finding on the hub's own health raised every hour with the same title (level `decision`, link `finding`), a meeting that
 * started (link `meeting`, MT-…), a founding whose server is ready, a learning question, and a read history (a budget alert raised three
 * times). `GET /notifications` filters by `unread`, `level` and pages by `limit`; `POST /notifications/{id}/read`, `/read-all` (`before`,
 * `level`) and `/answer` change them as the hub does.
 */
internal class NotificationsDemo(private val store: MutableMap<String, Pair<Int, JsonElement>>) {
    private val rows = mutableListOf<JsonObject>()

    init {
        fun at(m: Long) = HqClock.now().minus(m, ChronoUnit.MINUTES).toString()
        val finding = "یافته‌ی جدی ناظر کل: سلامت خود هاب — down: otel-collector, tempo; disk 90.4%"
        val body = "پایش ساعتی سلامت هاب: دو سرویس پایش پایین‌اند و دیسک از ۹۰٪ گذشته. مسئول: مهندس پلتفرم هلدینگ."
        // The overseer's hourly finding: five times since this morning, each a new FI-… with the same words.
        for ((i, m) in listOf(44L, 104L, 164L, 224L, 284L).withIndex()) {
            rows += n("f${i + 1}", "decision", "HQ", finding, body, "finding", "FI-%04d".format(212 - i), at(m))
        }
        // The fixtures' own: a card waiting, the morning report (read), an incident (read), a learning question.
        val base = store["/notifications"]?.second?.jsonObject?.get("items")?.jsonArray.orEmpty().map { it.jsonObject }
        rows += base
        rows += n("m1", "info", "HQ", "جلسه‌ی هیئت‌مدیره‌ی هلدینگ شروع شد", "MT-0012 · مدیر کل حاضر است، دستورِ جلسه سه بند دارد", "meeting", "MT-0012", at(26))
        rows += n("c1", "decision", "HQ", "سرور تأسیس C-0001 آماده‌ی ورود توست", "وارد شو، Claude Code را باز کن و شرکت را فعال کن.", "founding", "C-0001", at(70))
        // Read: the same budget alert three times yesterday, and the backup.
        val budget = "بودجه‌ی company:TY (2026-10) به 72٪ رسید"
        for ((i, m) in listOf(1300L, 1360L, 1420L).withIndex()) {
            rows += n("b${i + 1}", "report", "TY", budget, "", "treasury", "budget:company:TY:month", at(m), read = at(m - 20))
        }
        rows += n("k1", "info", "HQ", "پشتیبان ساعتی انجام شد", "۱۲ پایگاه داده، ۴۱۰ مگابایت", "backup", "BK-0091", at(1500), read = at(1490))
        rows.sortByDescending { it.str("created_at") }
    }

    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        if (method == "GET" && path == "/notifications") {
            val unread = query["unread"]?.toBooleanStrictOrNull()
            val level = query["level"]
            val limit = query["limit"]?.toIntOrNull() ?: 50
            val hit = rows.filter { (unread == null || (it.str("read_at") == null) == unread) && (level == null || it.str("level") == level) }
            return 200 to buildJsonObject { put("items", JsonArray(hit.take(limit))); put("next_cursor", JsonNull) }
        }
        if (method != "POST") return null
        val stamp = HqClock.now().toString()
        Regex("^/notifications/([^/]+)/read$").find(path)?.let { m ->
            val i = rows.indexOfFirst { it.str("id") == m.groupValues[1] }
            if (i < 0) return 404 to problem("not_found", "این اعلان پیدا نشد.")
            if (rows[i].str("read_at") == null) rows[i] = JsonObject(rows[i] + mapOf("read_at" to JsonPrimitive(stamp), "state" to JsonPrimitive("read")))
            return 200 to rows[i]
        }
        if (path == "/notifications/read-all") {
            val before = body?.get("before")?.jsonPrimitive?.contentOrNull
            val level = body?.get("level")?.jsonPrimitive?.contentOrNull
            var n = 0
            for ((i, r) in rows.withIndex()) {
                if (r.str("read_at") != null || (level != null && r.str("level") != level) || (before != null && r.str("created_at")!! > before)) continue
                rows[i] = JsonObject(r + mapOf("read_at" to JsonPrimitive(stamp), "state" to JsonPrimitive("read")))
                n++
            }
            return 200 to buildJsonObject { put("updated", n) }
        }
        Regex("^/notifications/([^/]+)/answer$").find(path)?.let { m ->
            val i = rows.indexOfFirst { it.str("id") == m.groupValues[1] }
            if (i < 0) return 404 to problem("not_found", "این اعلان پیدا نشد.")
            if (rows[i].str("answer") != null) return 409 to problem("validation_failed", "به این پرسش جواب داده شده.")
            rows[i] = JsonObject(rows[i] + mapOf("answer" to (body?.get("choice_id") ?: JsonNull), "read_at" to JsonPrimitive(rows[i].str("read_at") ?: stamp)))
            return 200 to rows[i]
        }
        return null
    }

    private fun n(id: String, level: String, co: String, title: String, body: String, kind: String?, ref: String?, at: String, read: String? = null) = buildJsonObject {
        put("id", id); put("level", level); put("company", co); put("title_fa", title); put("body_fa", body)
        put("link", if (kind != null) buildJsonObject { put("kind", kind); put("ref", ref) } else JsonNull)
        put("created_at", at); put("read_at", read); put("choices", JsonNull); put("answer", JsonNull); put("state", if (read != null) "read" else "delivered")
        putJsonObject("delivered") { put("in_app", true); put("web_push", false); put("fcm", false); put("telegram", false) }
    }

    private fun problem(code: String, fa: String) = buildJsonObject { put("code", code); put("message_fa", fa); put("status", 404); put("title", code); put("type", "about:blank") }

    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.content
}
