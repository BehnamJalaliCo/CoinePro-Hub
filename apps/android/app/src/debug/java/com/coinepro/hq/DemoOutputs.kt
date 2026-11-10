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
internal class OutputsDemo(
    private val store: MutableMap<String, Pair<Int, JsonElement>>,
    /** ⟨1.31⟩ §49 the best hour of a company's account, as the demo's rule answers it. */
    private val bestHour: (String, String?) -> JsonObject? = { _, _ -> null },
) {
    private val seen = mutableMapOf<String, String>()
    private val filed = mutableMapOf<String, String>()
    private var nextRecord = 97

    // ⟨0.19.8⟩ §44.5 «تأیید و انتشار»: the publishes of the session's outputs, newest first, and the accounts of its company.
    private val published = mutableMapOf<String, MutableList<JsonObject>>()
    private val sessionOutputs = mutableMapOf("O-000950" to listOf("coineprofx", "coineprofx.academy"), "O-000951" to listOf("coineprofx"))
    /** ⟨0.19.9⟩ §45 outputs a working group's routine made (no session), with the group's name. Declared before `init` fills it. */
    private val groupOutputs = mutableMapOf<String, String>()
    private var nextJob = 30
    /** ⟨1.31⟩ §51 the publications IG-Hub already holds (a cancel is asked of it: «در حال لغو»), and those whose file is still on its way. */
    private val held = mutableSetOf("jp-2", "jp-23")
    private val onItsWay = mutableSetOf("jp-11")

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
        // ⟨0.19.8⟩ §44.5 two outputs of a session, made by the workshop (opened by their ref; not in the lists): a reel and its cover
        // ready for «تأیید و انتشار», and the same with a story once the owner tapped (one published, one on its way, one refused).
        val media = agent("FX-MEDIA-01", "FX", "MEDIA", "مدیر رسانه")
        val reel = file("/demo/fx-reel-levels.mp4", "gold-levels-reel.mp4", "video/mp4", "video", "/demo/fx-reel-levels-poster.webp")
        val cover = file("/demo/fx-reel-levels-poster.webp", "gold-levels-cover.webp", "image/webp", "image")
        val story = file("/demo/ty-story-stoploss-poster.webp", "gold-levels-story.webp", "image/webp", "image")
        // ⟨1.31⟩ §53 a workshop turn's output says the model it ran on and how hard it thought
        val workshop = buildJsonObject { put("runtime", "workshop"); put("model", "claude-opus-5-5"); put("effort", "max") }
        for ((ref, files) in listOf("O-000950" to listOf(reel, cover), "O-000951" to listOf(reel, cover, story))) {
            val d = deliverable(
                ref, "FX", "W-000311", media, "خروجی کارگاه: ریلز «سطوح کلیدی طلا»",
                "ریلز ۶ ثانیه‌ای با گوینده آماده است؛ کاور و کپشن هم ساخته شد.",
                "ریلز **سطوح کلیدی طلا** آماده است.\n\n- ویدیو: ۶ ثانیه، عمودی، با صدای گوینده\n- کاور: تیتر با IRANYekanX\n\n**کپشن پیشنهادی:** سه سطحی که این هفته طلا را جابه‌جا میکند. #طلا #فارکس\n\nتأیید و انتشار؟",
                at(25), produced = workshop,
            )
            store["/deliverables/$ref"] = 200 to JsonObject(d + ("attachments" to JsonArray(files)))
        }
        // ⟨0.19.9⟩ §45 a working group's daily output (no session): the package went out on the owner's standing word
        val caption = file("/demo/fx-reel-levels-caption.txt", "caption.txt", "text/plain", "file")
        val daily = deliverable(
            "O-000952", "TY", "W-000340", agent("TY-MEDIA-02", "TY", "MEDIA", "سناریست"), "خروجی کارگاه: ریلز روز «حد ضرر در ۳۰ ثانیه»",
            "ریلز امروز کارگروه با کاور و کپشن آماده شد.",
            "ریلز **حد ضرر در ۳۰ ثانیه** آماده است: ویدیو، کاور و کپشن در همین خروجی.", at(40), produced = workshop,
        )
        store["/deliverables/O-000952"] = 200 to JsonObject(daily + ("attachments" to JsonArray(listOf(reel, cover, caption))))
        groupOutputs["O-000952"] = "تولید محتوای روزانه‌ی اینستاگرام"
        published["O-000952"] = mutableListOf(
            publish("O-000952", "jp-9", reel, "story", "tradeyar", "publishing", at = at(38), auto = true),
            publish("O-000952", "jp-8", reel, "reel", "tradeyar", "published", url = "https://www.instagram.com/reel/C9xStopLs/", at = at(38), cover = "gold-levels-cover.webp", auto = true),
        )
        // ⟨0.20.0⟩ §46 a reel set for this evening with its own comment word, and a carousel on its way
        val slide = file("/demo/ty-story-stoploss-poster.webp", "levels-2.jpg", "image/jpeg", "image")
        val timed = deliverable(
            "O-000953", "FX", "W-000312", media, "خروجی کارگاه: ریلز «نقطه‌ی ورود طلا»",
            "ریلز با کاور، کپشن و کلمه‌ی کامنت آماده است.", "ریلز **نقطه‌ی ورود طلا** آماده است.", at(20), produced = workshop,
        )
        store["/deliverables/O-000953"] = 200 to JsonObject(timed + ("attachments" to JsonArray(listOf(reel, cover, slide))))
        sessionOutputs["O-000953"] = listOf("coineprofx")
        published["O-000953"] = mutableListOf(
            publish("O-000953", "jp-11", cover, "carousel", "coineprofx", "publishing", at = at(2), count = 2),
            publish(
                "O-000953", "jp-10", reel, "reel", "coineprofx", "scheduled", at = at(5), cover = "gold-levels-cover.webp",
                scheduledAt = "2026-11-06T15:00:00Z", comment = "۷",
            ),
        )
        // ⟨1.31⟩ §51 the same session's next reel, set for this evening, in every state of a cancel: one he can still take back, one
        // taken back, one whose cancel is on its way to IG-Hub, and one IG-Hub would not cancel.
        val pngCover = file("/demo/fx-reel-resist-poster.webp", "entry-cover.png", "image/png", "image")
        val lastSlide = file("/demo/pc-landing-redesign.webp", "entry-slide.jpg", "image/jpeg", "image")
        val evening = HqClock.today().atTime(18, 30).atZone(java.time.ZoneId.of(com.coinepro.hq.core.format.OWNER_TZ)).toInstant().toString()
        val next = deliverable(
            "O-000954", "FX", "W-000313", media, "خروجی کارگاه: ریلز «حد سود در بازار طلا»",
            "ریلز فردا با کاور، استوری و اسلاید آماده است.", "ریلز **حد سود در بازار طلا** آماده است: ویدیو، کاور، استوری و یک اسلاید.", at(12), produced = workshop,
        )
        store["/deliverables/O-000954"] = 200 to JsonObject(next + ("attachments" to JsonArray(listOf(reel, pngCover, story, lastSlide))))
        sessionOutputs["O-000954"] = listOf("coineprofx")
        published["O-000954"] = mutableListOf(
            publish("O-000954", "jp-23", lastSlide, "post", "coineprofx", "scheduled", note = "لغو انجام نشد (IG-Hub جواب نداد)", at = at(6), scheduledAt = evening),
            publish("O-000954", "jp-22", story, "story", "coineprofx", "scheduled", note = "در حال لغو", at = at(7), scheduledAt = evening),
            publish("O-000954", "jp-21", pngCover, "post", "coineprofx", "cancelled", at = at(8), scheduledAt = evening),
            publish("O-000954", "jp-20", reel, "reel", "coineprofx", "scheduled", at = at(9), cover = "entry-cover.png", scheduledAt = evening),
        )
        published["O-000951"] = mutableListOf(
            publish("O-000951", "jp-3", story, "story", "coineprofx", "failed", note = "حساب امروز به سقف انتشار رسیده است.", at = at(4)),
            publish("O-000951", "jp-2", cover, "post", "coineprofx", "publishing", at = at(1)),
            publish("O-000951", "jp-1", reel, "reel", "coineprofx", "published", url = "https://www.instagram.com/reel/C9xGoldLv/", at = at(18), cover = "gold-levels-cover.webp"),
        )
        val all = listOf<JsonElement>(morning) + list() + yesterday + earlier
        store["/deliverables"] = 200 to page(all)
        // The demo's state: the earlier days read (one filed in the archive), and the polished morning report read this morning.
        seen["O-000030"] = at(240)
        seen["O-000028"] = at(60 * 24 + 100)
        seen["O-000026"] = at(3 * 60 * 24 + 30)
        filed["O-000026"] = "AR-000092"
    }

    private fun file(id: String, name: String, mime: String, kind: String, poster: String? = null) = buildJsonObject {
        put("id", id); put("name", name); put("mime", mime); put("size", if (kind == "video") 1_200_000 else 90_000); put("sha256", "demo"); put("kind", kind); put("status", "ready")
        if (kind == "video") { put("width", 1080); put("height", 1920); put("duration_s", 6) } else { put("width", 1080); put("height", 1350) }
        if (poster != null) put("variants", buildJsonObject { put("poster", poster) })
    }

    private fun publish(
        output: String, job: String, f: JsonObject, kind: String, account: String, state: String, url: String? = null, note: String? = null, at: String,
        cover: String? = null, auto: Boolean = false, scheduledAt: String? = null, comment: String? = null, count: Int = 1,
    ) = buildJsonObject {
        put("auto", auto)
        // ⟨0.20.0⟩ §46 the time it is set for, the word viewers comment, a carousel's files
        put("scheduled_at", scheduledAt?.let(::JsonPrimitive) ?: JsonNull); put("comment", comment?.let(::JsonPrimitive) ?: JsonNull); put("files", count)
        put("job", job); put("output", output); put("file_id", f.str("id")); put("file_name", f.str("name")); put("channel", "instagram"); put("kind", kind)
        put("cover_name", cover?.let(::JsonPrimitive) ?: JsonNull)
        put("account", account); put("state", state); put("url", url?.let(::JsonPrimitive) ?: JsonNull); put("note_fa", note?.let(::JsonPrimitive) ?: JsonNull)
        put("at", at); put("published_at", if (state == "published") JsonPrimitive(at) else JsonNull)
    }

    /** `GET` the panel of an output (an output of no session: `order` null), `POST` the owner's tap. */
    private fun publishRoute(method: String, ref: String, body: JsonObject?): Pair<Int, JsonElement>? {
        val group = groupOutputs[ref]
        val accounts = sessionOutputs[ref] ?: group?.let { listOf("tradeyar") }
        if (method == "GET") return 200 to buildJsonObject {
            put("order", if (accounts == null || group != null) JsonNull else JsonPrimitive(SESSION)); put("channel", "instagram")
            put("accounts", JsonArray(accounts.orEmpty().map(::JsonPrimitive))); put("ready", accounts != null)
            put("publishes", JsonArray(published[ref].orEmpty()))
            // ⟨0.19.9⟩ §45 every output is tapped here; a working group's carries its caption and the owner's standing word
            put("tap", true)
            put("caption", if (group != null) JsonPrimitive("حد ضرر را در ۳۰ ثانیه یاد بگیر.\n#تریدیار #حد_ضرر") else JsonNull)
            // ⟨0.20.0⟩ §46 the comment rule the package carries (its `comment.txt`)
            put("comment", if (group != null) buildJsonObject {
                put("keywords", JsonArray(listOf(JsonPrimitive("۳۰")))); put("reply", "این هم آموزش کامل حد ضرر:"); put("link", "https://tradeyar.com/learn/stop-loss")
                put("button", JsonNull); put("public_replies", JsonArray(emptyList()))
            } else JsonNull)
            put("group", if (group != null) JsonPrimitive("pb_1") else JsonNull); put("group_fa", group?.let(::JsonPrimitive) ?: JsonNull)
            put("mode", if (group != null) JsonPrimitive("auto") else JsonNull)
            // ⟨1.31⟩ §49 the account's best hour, only when there is enough data (a time of the sheet)
            put("best", bestHour(if (group != null) "TY" else "FX", accounts?.firstOrNull())?.takeIf { (it["enough"] as? JsonPrimitive)?.booleanOrNull == true } ?: JsonNull)
        }
        if (method != "POST" || accounts == null) return null
        val fileId = body?.str("file_id") ?: return null
        val files = (store["/deliverables/$ref"]?.second?.jsonObject?.get("attachments") as? JsonArray)?.map { it.jsonObject }.orEmpty()
        val f = files.firstOrNull { it.str("id") == fileId } ?: return null
        val kind = body.str("kind") ?: if (f.str("kind") == "video") "reel" else "post"
        val cover = files.firstOrNull { it.str("id") == body.str("cover_file_id") }?.str("name")
        val whenAt = body.str("scheduled_at")
        val word = ((body["comment"] as? JsonObject)?.get("keywords") as? JsonArray)?.firstOrNull()?.let { (it as? JsonPrimitive)?.content }
        val made = publish(
            ref, "jp-${nextJob++}", f, kind, body.str("account")?.removePrefix("@") ?: accounts.first(), if (whenAt != null) "scheduled" else "publishing",
            at = HqClock.now().toString(), cover = cover, scheduledAt = whenAt, comment = word, count = 1 + ((body["file_ids"] as? JsonArray)?.size ?: 0),
        )
        published.getOrPut(ref) { mutableListOf() }.add(0, made)
        return 202 to made
    }

    /** ⟨1.31⟩ §44.5 what the demo's session published, across its outputs, newest first (`OrderReport.publishes`). */
    fun sessionPublishes(): JsonArray =
        JsonArray(sessionOutputs.keys.flatMap { published[it].orEmpty() }.sortedByDescending { it.str("at").orEmpty() })

    /**
     * ⟨1.31⟩ §51 «لغو»: one no runner has taken is cancelled at once; one IG-Hub holds keeps its state with «در حال لغو» (a second tap
     * answers the same); one that is out, failed or cancelled, or whose file is still on its way, is a `409 not_cancellable`.
     */
    private fun cancel(job: String): Pair<Int, JsonElement> {
        fun refuse(fa: String) = 409 to buildJsonObject { put("code", "not_cancellable"); put("message_fa", fa); put("status", 409); put("title", "Conflict"); put("type", "about:blank") }
        for (list in published.values) {
            val i = list.indexOfFirst { it.str("job") == job }
            if (i < 0) continue
            val p = list[i]
            val state = p.str("state")
            if (state != "scheduled" && state != "publishing") return refuse(
                when (state) { "published" -> "این پست منتشر شده است؛ برداشتنش از خود اینستاگرام انجام میشود."; "cancelled" -> "این انتشار پیش‌تر لغو شده است."; else -> "این انتشار دیگر در صف نیست." },
            )
            if (job in onItsWay) return refuse("فایل این انتشار هنوز در راه IG-Hub است؛ چند لحظه‌ی دیگر میشود لغوش کرد.")
            list[i] = JsonObject(p + if (job in held) mapOf("note_fa" to JsonPrimitive("در حال لغو")) else mapOf("state" to JsonPrimitive("cancelled"), "note_fa" to JsonNull))
            return 200 to list[i]
        }
        return 404 to buildJsonObject { put("code", "not_found"); put("message_fa", "این انتشار پیدا نشد."); put("status", 404); put("title", "Not found"); put("type", "about:blank") }
    }

    /** Answers the ⟨1.7.3⟩ reads and writes, or null to let the rest of the demo answer. */
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?, stepUp: String? = null): Pair<Int, JsonElement>? {
        Regex("^/deliverables/(O-\\d+)/publish$").find(path)?.let { m -> return publishRoute(method, m.groupValues[1], body) }
        Regex("^/publishes/([^/]+)/cancel$").find(path)?.let { m -> return if (method == "POST") cancel(m.groupValues[1]) else null }
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
        // ⟨1.19⟩ §37.2 one output erased for good: its preview first (nothing changes), then the sealed erase; its work stays.
        Regex("^/deliverables/(O-\\d+)/erase(/preview)?$").find(path)?.let { m ->
            val ref = m.groupValues[1]
            val d = list().firstOrNull { it.str("ref") == ref }?.jsonObject ?: return 404 to buildJsonObject {
                put("code", "not_found"); put("message_fa", "این خروجی پیدا نشد."); put("status", 404); put("title", "Not found"); put("type", "about:blank")
            }
            val files = (d["files"] as? JsonArray)?.size ?: 0
            val counts = buildJsonObject { put("files", files); put("outputs", 1); put("decisions", 0) }
            if (m.groupValues[2].isNotEmpty()) return if (method == "GET") 200 to buildJsonObject {
                put("ref", ref); put("kind", "output"); put("title_fa", d.str("title").orEmpty()); put("counts", counts)
                put("keeps_fa", JsonArray(listOf(JsonPrimitive("کاری که این خروجی از آن آمده میماند؛ قدمش میگوید «خروجی پاک شد»."), JsonPrimitive("یک خط در دفتر حسابرسی، بی متن خروجی."))))
            } else null
            if (method != "POST") return null
            if (stepUp == null) return 403 to buildJsonObject { put("code", "step_up_required"); put("message_fa", "این کار تأیید با گذرکلید لازم دارد."); put("status", 403); put("title", "Forbidden"); put("type", "about:blank") }
            store["/deliverables"] = 200 to page(list().filter { it.str("ref") != ref })
            store.remove("/deliverables/$ref"); seen.remove(ref); filed.remove(ref)
            return 200 to buildJsonObject { put("ref", ref); put("erased", counts) }
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

    companion object {
        /** The session the demo's workshop outputs belong to (their panel's `order`). */
        const val SESSION = "F-0100"

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
