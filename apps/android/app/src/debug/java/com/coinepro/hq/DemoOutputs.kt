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
internal class OutputsDemo(private val store: MutableMap<String, Pair<Int, JsonElement>>) {
    private val seen = mutableMapOf<String, String>()
    private val filed = mutableMapOf<String, String>()
    private var nextRecord = 97

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
        val all = listOf<JsonElement>(morning) + list() + yesterday + earlier
        store["/deliverables"] = 200 to page(all)
        // The demo's state: the earlier days read (one filed in the archive), and the polished morning report read this morning.
        seen["O-000030"] = at(240)
        seen["O-000028"] = at(60 * 24 + 100)
        seen["O-000026"] = at(3 * 60 * 24 + 30)
        filed["O-000026"] = "AR-000092"
    }

    /** Answers the ⟨1.7.3⟩ reads and writes, or null to let the rest of the demo answer. */
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?, stepUp: String? = null): Pair<Int, JsonElement>? {
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

    private companion object {
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
