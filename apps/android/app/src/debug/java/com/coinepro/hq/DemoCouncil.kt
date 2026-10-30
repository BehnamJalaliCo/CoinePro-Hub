package com.coinepro.hq

import android.content.Context
import android.net.Uri
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.net.StreamEvent
import java.io.File
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.put

/**
 * Debug builds only: contract §27 ⟨1.9⟩ beside [OrdersDemo] (which keeps the orders, their players and their councils).
 *
 * - The media council's two Creatives (`CR-0101` by GPT, `CR-0102` by Gemini, for W-000199), drawn once like the §21.13 creatives;
 *   `POST /creatives/{ref}/pick` makes one the owner's pick, `POST /creatives/{ref}/animate` makes a video of an image (generating,
 *   then in review a few seconds later). They stay off the creatives list, which keeps the web's fixtures as they are.
 * - Speech on the hub (§27.3): `/meta.speech.enabled`, the hub's transcript of the voice message and the voice notes
 *   (`GET /files/{id}/meta` with `transcript_fa`), and [transcribed]: an uploaded voice gets its transcript and `file.transcribed`.
 */
internal class CouncilDemo(
    private val context: Context,
    private val store: MutableMap<String, Pair<Int, JsonElement>>,
    private val files: MutableMap<String, JsonObject>,
) {
    private val creatives = linkedMapOf<String, JsonObject>()
    private val readyAt = mutableMapOf<String, Long>()

    init {
        // §27.3: the hub's speech to text is on.
        (store["/meta"]?.second as? JsonObject)?.let { m -> store["/meta"] = 200 to JsonObject(m + ("speech" to buildJsonObject { put("enabled", true) })) }
        // The voice message to FX's CEO: the hub's own words beside the phone's.
        val key = "/threads/FX-CEO/messages"
        (store[key]?.second as? JsonObject)?.let { page ->
            val items = (page["items"] as? JsonArray).orEmpty().map { e ->
                val m = e as JsonObject
                if (m.str("ref") != "FX-CEO-0008") m else JsonObject(m + ("attachments" to JsonArray((m["attachments"] as JsonArray).map { a ->
                    JsonObject((a as JsonObject) + ("transcript_fa" to JsonPrimitive(HUB_MESSAGE)))
                })))
            }
            store[key] = 200 to JsonObject(page + ("items" to JsonArray(items)))
        }
        for ((ref, player, model) in listOf(Triple("CR-0101", "gpt", "gpt-5.5"), Triple("CR-0102", "gemini", "gemini-3.8"))) creatives[ref] = creative(ref, player, model)
    }

    @Synchronized
    fun handle(method: String, path: String): Pair<Int, JsonElement>? {
        Regex("^/files/(.+)/meta$").find(path)?.let { m -> if (method == "GET") return meta(m.groupValues[1]) }
        val m = Regex("^/creatives/(CR-01\\d\\d)(/pick|/animate)?$").find(path) ?: return null
        val ref = m.groupValues[1]
        val x = creatives[ref]?.let(::ripe) ?: return 404 to problem("not_found", "این درخواست پیدا نشد.")
        return when (m.groupValues[2]) {
            "" -> if (method == "GET") 200 to rendered(x) else null
            "/pick" -> {
                if (x.str("state") !in setOf("review", "accepted")) return 409 to problem("validation_failed", "فقط نسخه‌ی آماده انتخاب میشود.", 409)
                // The owner's pick; the other versions of the same council step aside.
                val stamp = HqClock.now().toString()
                for ((r, y) in creatives.toMap()) if (y.str("work_ref") == x.str("work_ref") && y.str("kind") == x.str("kind")) {
                    creatives[r] = if (r == ref) y.with("state" to JsonPrimitive("accepted"), "picked_at" to JsonPrimitive(stamp), "updated_at" to JsonPrimitive(stamp))
                    else y.with("picked_at" to JsonNull)
                }
                200 to rendered(creatives.getValue(ref))
            }
            "/animate" -> {
                if (x.str("kind") != "image" || x["picked_at"] == null || x["picked_at"] is JsonNull) return 409 to problem("validation_failed", "ویدیو از تصویر انتخاب‌شده ساخته میشود.", 409)
                val n = (creatives.keys.mapNotNull { it.substringAfter('-').toIntOrNull() }.maxOrNull() ?: 100) + 1
                val v = "CR-%04d".format(n)
                val stamp = HqClock.now().toString()
                creatives[v] = x.with(
                    "id" to JsonPrimitive("cr$n"), "ref" to JsonPrimitive(v), "kind" to JsonPrimitive("video"), "duration_s" to JsonPrimitive(6), "player" to JsonPrimitive("gemini"),
                    "model" to JsonPrimitive("gemini-3.8"), "state" to JsonPrimitive("generating"), "files" to JsonArray(emptyList()), "composed" to JsonNull, "review_md" to JsonNull,
                    "prompt_md" to JsonPrimitive("Animate the picked image ($ref) into a 6 s teaser: slow push-in, the candles rising; no text, no letters."),
                    "created_at" to JsonPrimitive(stamp), "updated_at" to JsonPrimitive(stamp), "version" to JsonPrimitive(1), "picked_at" to JsonNull,
                )
                readyAt[v] = System.currentTimeMillis() + 8_000
                201 to creatives.getValue(v)
            }
            else -> null
        }
    }

    /** A live media council's version by [player] for [workRef] (an image now, or a video ready a few seconds later). */
    @Synchronized
    fun make(player: String, workRef: String, kind: String): String {
        val n = (creatives.keys.mapNotNull { it.substringAfter('-').toIntOrNull() }.maxOrNull() ?: 100) + 1
        val ref = "CR-%04d".format(n)
        var x = creative(ref, player, if (player == "gpt") "gpt-5.5" else "gemini-3.8").with(
            "work_ref" to JsonPrimitive(workRef), "created_at" to JsonPrimitive(HqClock.now().toString()), "updated_at" to JsonPrimitive(HqClock.now().toString()),
        )
        if (kind == "video") {
            x = x.with("kind" to JsonPrimitive("video"), "duration_s" to JsonPrimitive(6), "state" to JsonPrimitive("generating"))
            readyAt[ref] = System.currentTimeMillis() + 6_000
        }
        creatives[ref] = x
        return ref
    }

    /** §27.3: the hub's transcript of an uploaded voice, on the file and on every message that carries it; `file.transcribed` says so. */
    @Synchronized
    fun transcribed(id: String, words: String): List<StreamEvent> {
        files[id]?.let { files[id] = JsonObject(it + ("transcript_fa" to JsonPrimitive(words))) }
        for (key in store.keys.filter { Regex("^/threads/[^/]+/messages$").matches(it) }.toList()) {
            val page = store[key]?.second as? JsonObject ?: continue
            val items = (page["items"] as? JsonArray).orEmpty()
            if (items.none { (it as? JsonObject)?.get("attachments")?.toString()?.contains(id) == true }) continue
            store[key] = 200 to JsonObject(page + ("items" to JsonArray(items.map { e ->
                val m = e as JsonObject
                JsonObject(m + ("attachments" to JsonArray((m["attachments"] as? JsonArray).orEmpty().map { a ->
                    if ((a as JsonObject).str("id") == id) JsonObject(a + ("transcript_fa" to JsonPrimitive(words))) else a
                })))
            })))
        }
        return listOf(StreamEvent("demo-tr-${System.nanoTime()}", "file.transcribed", HqClock.now().toString(), "HQ", id, buildJsonObject { put("file", id) }))
    }

    // ------------------------------------------------------------------ files --
    private fun meta(id: String): Pair<Int, JsonElement> {
        files[id]?.let { return 200 to it }
        val notes = (store["/notes"]?.second as? JsonObject)?.get("items") as? JsonArray
        val note = notes.orEmpty().mapNotNull { it as? JsonObject }.firstOrNull { it.str("file_id") == id } ?: return 404 to problem("not_found", "این فایل پیدا نشد.")
        return 200 to buildJsonObject {
            put("id", id); put("name", "voice-${note.str("ref")}.m4a"); put("mime", "audio/mp4"); put("size", 13_163); put("sha256", "demo"); put("kind", "audio"); put("status", "ready")
            put("duration_s", 4.2); put("variants", JsonObject(emptyMap()))
            HUB_NOTES[note.str("ref")]?.let { put("transcript_fa", it) }
        }
    }

    // -------------------------------------------------------------- creatives --
    private fun creative(ref: String, player: String, model: String): JsonObject {
        val at = HqClock.now().minus(200, ChronoUnit.MINUTES).toString()
        return buildJsonObject {
            put("id", ref.lowercase()); put("ref", ref); put("company", "FX"); put("kind", "image")
            put("brief_md", "استوری اینستاگرام برای جلسه‌ی دوم دوره‌ی رایگان تحلیل طلا.")
            put("prompt_md", "Advertising image for CoinePro FX, aspect 9:16, in the brand palette. Gold candles rising, calm and premium. No text, no letters, no logos anywhere; keep the lower third calm for an overlay.")
            put("placement", "instagram_story"); put("aspect", "9:16"); put("duration_s", JsonNull)
            put("overlay", buildJsonObject { put("title_fa", "جلسه‌ی دوم: سطوح حمایت طلا"); put("body_fa", "شنبه ساعت ۲۰، زنده در تلگرام"); put("cta_fa", "یادآوری بگذار"); put("mark", true) })
            put("composed", JsonNull); put("player", player); put("model", model); put("path", "web"); put("state", "review")
            put("requested_by", buildJsonObject { put("kind", "agent"); put("code", "FX-CEO"); put("display_fa", "مدیرعامل کوینه‌پرو FX") })
            put("work_ref", "W-000199"); put("errand_ref", JsonNull); put("files", JsonArray(emptyList()))
            put("review_md", if (player == "gpt") "با brief میخواند؛ پایین قاب برای متن آرام است." else "رنگ‌ها گرم‌تر از پالت است؛ متن در حاشیه‌ی امن نشسته.")
            put("source", buildJsonObject { put("player", player); put("model", model); put("at", at) }); put("ai_generated", true)
            put("created_at", at); put("updated_at", at); put("version", 1)
        }
    }

    /** A video made from an image is generating for a few seconds, then waits for review (the demo's own film as its file). */
    private fun ripe(x: JsonObject): JsonObject {
        val ref = x.str("ref") ?: return x
        val due = readyAt[ref] ?: return x
        if (System.currentTimeMillis() < due) return x
        readyAt.remove(ref)
        val film = buildJsonObject {
            put("id", "/demo/fx-reel-levels.mp4"); put("name", "$ref.mp4"); put("mime", "video/mp4"); put("size", 1_200_000); put("sha256", "demo"); put("kind", "video"); put("status", "ready")
            put("duration_s", 6); put("variants", buildJsonObject { put("poster", "/demo/fx-reel-levels-poster.webp") })
        }
        val y = x.with("state" to JsonPrimitive("review"), "files" to JsonArray(listOf(film)), "review_md" to JsonPrimitive("ویدیوی شش‌ثانیه‌ای از تصویر انتخاب‌شده؛ قاب‌های کلیدی با brief میخوانند."))
        creatives[ref] = y
        return y
    }

    /** The picture and its composition with the hub's Persian text, drawn once into the cache. */
    private fun rendered(x: JsonObject): JsonObject {
        if (x.str("kind") != "image" || (x["files"] as? JsonArray).orEmpty().isNotEmpty()) return x
        val ref = x.str("ref") ?: return x
        val dir = File(context.cacheDir, "demo-creatives")
        return runCatching {
            val seed = DemoArt.seedOf(ref + x.str("player"))
            val raw = File(dir, "$ref-raw.jpg")
            val rawSize = DemoArt.render(context, "FX", "instagram_story", seed, null, raw)
            val comp = File(dir, "$ref-composed.jpg")
            val o = x["overlay"] as JsonObject
            val size = DemoArt.render(context, "FX", "instagram_story", seed, DemoArt.Overlay(o.str("title_fa").orEmpty(), o.str("body_fa"), o.str("cta_fa"), true), comp)
            val y = x.with("files" to JsonArray(listOf(fileRef(raw, rawSize))), "composed" to fileRef(comp, size))
            creatives[ref] = y
            y
        }.getOrDefault(x)
    }

    private fun fileRef(f: File, size: Pair<Int, Int>) = buildJsonObject {
        put("id", Uri.fromFile(f).toString()); put("name", f.name); put("mime", "image/jpeg"); put("size", f.length()); put("sha256", "demo"); put("kind", "image"); put("status", "ready")
        put("width", size.first); put("height", size.second); put("variants", JsonObject(emptyMap()))
    }

    private fun JsonObject.with(vararg kv: Pair<String, JsonElement>): JsonObject = JsonObject(this + kv)
    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
    private fun problem(code: String, fa: String, status: Int = 404) = buildJsonObject {
        put("code", code); put("message_fa", fa); put("status", status); put("title", code); put("type", "about:blank")
    }

    private companion object {
        /** The hub's own words for the voice message (punctuated, «کُند», «یک شاخه‌ی جدا»), beside the phone's. */
        const val HUB_MESSAGE = "صفحه‌ی ثبت‌نام هنوز کُند است؛ به مدیر فنی بگو تا فردا ظهر علتش را پیدا کند و اصلاح را در کارگاه کد، روی یک شاخه‌ی جدا، آماده کند. قبل از ادغام، خودم نگاه می‌کنم."
        val HUB_NOTES = mapOf(
            "NT-0005" to "برای نامه‌ی هفتگی پرو-چارت بپرس چرا pull درآمد دو هفته است که شکست می‌خورد، و کی درست می‌شود؟",
            "NT-0002" to "سه سرویس ایمیل تراکنشی برای تریدیار پیدا کن؛ برای حدود دویست هزار ایمیل در ماه.",
        )
    }
}
