package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * Debug builds only: contract §38.3 ⟨1.20⟩, the owner's «سرویس‌ها». A hub of 16 GB with a 12 GB budget: the core services, and the
 * optional ones — video and covers, the hub's plain voice, the newsletter and n8n on; speech to text, OCR, MCP and tracing off. Speech to
 * text (3.5 GB) does not fit until something is turned off: the job is `refused` with what holds the memory, largest first; the swap
 * (`turn_off`) goes in the same job. A job answers `done` on its first read.
 */
internal class V38Demo {
    private class Svc(val key: String, val title: String, val what: String, var on: Boolean, val cap: Int, val used: Int?, val optional: Boolean, val note: String? = null)

    private val services = mutableListOf(
        Svc("media", "ساخت ویدیو و کاور", "ریلز، کاور و ویدیوی کوتاه را میسازد.", true, 3072, 1840, true),
        Svc("tts", "صدای ساده‌ی هاب", "وقتی سقف صدای جمینای پر شد، هاب با صدای خودش حرف میزند.", true, 512, 210, true),
        Svc("stt", "تبدیل گفتار به متن", "صدای تو را روی خود هاب به متن دقیق فارسی برمیگرداند.", false, 3584, null, true),
        Svc("ocr", "خواندن اسکن بایگانی", "متن سندهای اسکن‌شده‌ی بایگانی را میخواند تا جستجو شوند.", false, 1024, null, true),
        Svc("newsletter", "خبرنامه", "خبرنامه‌ی ایمیلی شرکت‌ها را میفرستد.", true, 256, 90, true),
        Svc("automations", "خودکارسازی (n8n)", "کارهای قاعده‌محور و تکراری را بی‌هوش مصنوعی انجام میدهد.", true, 768, 420, true),
        Svc("mcp", "ابزارهای بیرونی (MCP)", "ابزارهای بیرونی را به ایجنت‌ها وصل میکند.", false, 384, null, true),
        Svc("tracing", "ردگیری", "مسیر هر درخواست را برای عیب‌یابی نگه میدارد.", false, 1536, null, true, note = "فقط وقتی چیزی خراب است لازم میشود."),
        Svc("api", "هسته‌ی هاب", "همه‌ی کارهای اپ و ایجنت‌ها از این میگذرد.", true, 1024, 610, false),
        Svc("worker", "کارگر", "کارهای پس‌زمینه و گزارش‌ها را اجرا میکند.", true, 1024, 540, false),
        Svc("postgres", "پایگاه داده", "حافظه‌ی همیشگی هلدینگ.", true, 2048, 1320, false),
        Svc("redis", "صف و حافظه‌ی کوتاه", "صف کارها و خبرهای زنده.", true, 256, 64, false),
        Svc("caddy", "دروازه", "اتصال امن اپ و وب به هاب.", true, 128, 40, false),
        Svc("openbao", "گاوصندوق رمزها", "کلیدها و رمزها را نگه میدارد.", true, 256, 120, false),
    )
    private val total = 16384
    private val budget = 12288
    private val jobs = mutableMapOf<String, JsonObject>()
    private var seq = 1

    private fun caps() = services.filter { it.on }.sumOf { it.cap }
    private fun free() = budget - caps()

    private fun view(s: Svc) = jo(
        "key" to s.key, "title_fa" to s.title, "what_fa" to s.what, "state" to if (s.on) "on" else "off", "optional" to s.optional,
        "mem_cap_mb" to s.cap, "mem_used_mb" to if (s.on) s.used else null, "can_toggle" to s.optional, "note_fa" to s.note,
    )

    private fun page() = jo(
        "memory" to jo("total_mb" to total, "budget_mb" to budget, "caps_mb" to caps(), "free_mb" to free()),
        "services" to JsonArray(services.map(::view)), "at" to HqClock.now().minus(40, ChronoUnit.SECONDS).toString(),
    )

    @Synchronized
    fun handle(method: String, path: String, body: JsonObject?): Pair<Int, JsonElement>? {
        if (path == "/hub/services" && method == "GET") return 200 to page()
        Regex("^/hub/jobs/(HJ-\\d+)$").find(path)?.let { m ->
            if (method != "GET") return null
            val j = jobs[m.groupValues[1]] ?: return 404 to problem(404, "not_found", "این کار پیدا نشد.")
            // A queued job has run by the time it is read.
            val done = if ((j["state"] as? JsonPrimitive)?.contentOrNull == "queued") JsonObject(j + ("state" to JsonPrimitive("done"))) else j
            jobs[m.groupValues[1]] = done
            return 200 to done
        }
        Regex("^/hub/services/([a-z_]+)$").find(path)?.let { m ->
            if (method != "POST") return null
            val s = services.firstOrNull { it.key == m.groupValues[1] } ?: return 404 to problem(404, "not_found", "این سرویس پیدا نشد.")
            if (!s.optional) return 422 to problem(422, "validation_failed", "سرویس‌های هسته همیشه روشن‌اند.")
            val on = (body?.get("on") as? JsonPrimitive)?.booleanOrNull ?: return 422 to problem(422, "validation_failed", "روشن یا خاموش؟")
            val off = (body?.get("turn_off") as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
            for (k in off) services.firstOrNull { it.key == k && it.optional }?.on = false
            val ref = "HJ-%04d".format(seq++)
            val job = if (on && !s.on && s.cap > free()) {
                val blocking = services.filter { it.optional && it.on }.sortedByDescending { it.cap }.map { jo("key" to it.key, "title_fa" to it.title, "mem_cap_mb" to it.cap) }
                jo("ref" to ref, "state" to "refused", "result_fa" to "جا نیست؛ این‌ها جا را گرفته‌اند", "blocking" to JsonArray(blocking))
            } else {
                s.on = on
                jo("ref" to ref, "state" to "queued", "result_fa" to if (on) "${s.title} روشن شد." else "${s.title} خاموش شد.", "blocking" to JsonArray(emptyList()))
            }
            jobs[ref] = job
            return 202 to job
        }
        return null
    }

    private fun jo(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(kv.associate { (k, v) ->
        k to when (v) {
            null -> JsonNull; is JsonElement -> v; is String -> JsonPrimitive(v); is Number -> JsonPrimitive(v); is Boolean -> JsonPrimitive(v)
            else -> error("unsupported ${v::class}")
        }
    })
    private fun problem(status: Int, code: String, fa: String) = jo("code" to code, "message_fa" to fa, "status" to status, "title" to code, "type" to "about:blank")
}
