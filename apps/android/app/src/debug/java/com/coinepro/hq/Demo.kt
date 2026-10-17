package com.coinepro.hq

import android.content.Context
import android.graphics.BitmapFactory
import android.media.MediaMetadataRetriever
import android.net.Uri
import com.coinepro.hq.core.media.kindOf
import com.coinepro.hq.core.net.Api
import java.io.File
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer

/** Debug builds only: a demo holding served from the same fixtures as the web's `npm run dev:mock`
 *  (assets/demo-fixtures.json, made by scripts/dump_demo_fixtures.mjs). No network, no passkey. */
object Demo {
    const val available = true

    @Volatile private var appContext: Context? = null

    fun init(context: Context) { appContext = context.applicationContext }

    fun interceptor(): Interceptor = DemoInterceptor(requireNotNull(appContext) { "Demo.init not called" })
}

private class DemoInterceptor(private val context: Context) : Interceptor {
    private val now = Instant.now()
    private val store: MutableMap<String, Pair<Int, JsonElement>> = run {
        val text = context.assets.open("demo-fixtures.json").bufferedReader().use { it.readText() }
        Api.json.parseToJsonElement(text).jsonObject.mapValuesTo(LinkedHashMap()) { (_, v) ->
            v.jsonObject["status"]!!.jsonPrimitive.content.toInt() to resolve(v.jsonObject["body"]!!)
        }
    }

    /** "@-42m" → now − 42 minutes; "@3d" → today + 3 days (UTC date). */
    private fun resolve(e: JsonElement): JsonElement = when (e) {
        is JsonObject -> JsonObject(e.mapValues { resolve(it.value) })
        is JsonArray -> JsonArray(e.map(::resolve))
        is JsonPrimitive -> {
            val s = if (e.isString) e.content else null
            when {
                s != null && Regex("^@-?\\d+m$").matches(s) -> JsonPrimitive(now.plus(s.drop(1).dropLast(1).toLong(), ChronoUnit.MINUTES).toString())
                s != null && Regex("^@-?\\d+d$").matches(s) -> JsonPrimitive(LocalDate.now(ZoneOffset.UTC).plusDays(s.drop(1).dropLast(1).toLong()).toString())
                else -> e
            }
        }
    }

    @Synchronized
    override fun intercept(chain: Interceptor.Chain): Response {
        Thread.sleep(150)
        val req = chain.request()
        val path = req.url.encodedPath.removePrefix("/api/v1").let { java.net.URLDecoder.decode(it, "UTF-8") }
        if (req.method == "POST" && (path == "/files" || path == "/transcribe")) return respond(req, binary(req, path))
        val body = req.body?.let { b -> Buffer().also { b.writeTo(it) }.readUtf8() }?.takeIf { it.isNotBlank() }?.let { Api.json.parseToJsonElement(it).jsonObject }
        return respond(req, if (req.method == "GET") read(path, req.url.queryParameterNames.associateWith { req.url.queryParameter(it) }) else write(path, body))
    }

    private fun respond(req: okhttp3.Request, result: Pair<Int, JsonElement>): Response {
        val (status, out) = result
        return Response.Builder()
            .request(req).protocol(Protocol.HTTP_1_1).code(status).message("demo")
            .body(out.toString().toResponseBody("application/json".toMediaType()))
            .build()
    }

    private fun read(path: String, query: Map<String, String?>): Pair<Int, JsonElement> {
        val q = query.filterKeys { it !in setOf("limit", "cursor", "from", "to", "period") }.filterValues { it != null }.toSortedMap()
        val key = if (q.isEmpty()) path else path + "?" + q.entries.joinToString("&") { "${it.key}=${it.value}" }
        store[key]?.let { return it }
        if (path == "/decisions") return 200 to page(list("/decisions?status=all").filter { q["status"] == null || it.jsonObject.str("status") == q["status"] })
        if (path.matches(Regex("^/work/[^/]+/events$"))) return 200 to page(emptyList())
        if (path.startsWith("/work/")) return store["/work/w0"]!!
        if (path.matches(Regex("^/threads/[^/]+/messages$"))) return 200 to page(emptyList())
        Regex("^/workshop/sessions/(S-\\d+)/events$").find(path)?.let { m ->
            val ref = m.groupValues[1]
            val after = q["after"]?.toLongOrNull() ?: 0
            // Live demo: each poll may reveal the session's next scripted step, as the web's mock does.
            if (after > 0 && scripts[ref].orEmpty().isNotEmpty() && Math.random() < 0.8) reveal(ref, scripts.getValue(ref).removeAt(0))
            return 200 to page(list("/workshop/sessions/$ref/events").filter { it.jsonObject["seq"]!!.jsonPrimitive.long > after })
        }
        store[path]?.let { return it }
        return 404 to problem("not_found", "پیدا نشد.")
    }

    private fun write(path: String, body: JsonObject?): Pair<Int, JsonElement> {
        Regex("^/decisions/(D-\\d+)/(approve|reject|return)$").find(path)?.let { m ->
            val (ref, verdict) = m.destructured
            val status = mapOf("approve" to "approved", "reject" to "rejected", "return" to "returned").getValue(verdict)
            val stamp = Instant.now().toString()
            val updated = edit("/decisions/$ref") {
                it + mapOf(
                    "status" to JsonPrimitive(status),
                    "decided_at" to JsonPrimitive(stamp),
                    "decided_by" to buildJsonObject { put("kind", "owner"); put("code", "owner"); put("display_fa", "مدیر کل") },
                    "seal" to if (verdict == "approve") buildJsonObject { put("method", "passkey_uv"); put("sealed_at", stamp); put("step_up_id", "demo") } else JsonNull,
                    "resolution" to if (verdict == "approve") JsonPrimitive("M-0007") else JsonNull,
                )
            }
            replaceIn("/decisions?status=all", ref, updated)
            store["/decisions?status=pending"] = 200 to page(list("/decisions?status=all").filter { it.jsonObject.str("status") == "pending" })
            bumpInbox()
            return 200 to updated
        }
        Regex("^/deliverables/(O-\\d+)/rating$").find(path)?.let { m ->
            val ref = m.groupValues[1]
            val rating = buildJsonObject { put("score", body?.get("score")!!); put("comment", body["comment"] ?: JsonNull); put("history_count", 1); put("rated_at", Instant.now().toString()) }
            val updated = edit("/deliverables/$ref") { it + ("rating" to rating) }
            replaceIn("/deliverables", ref, updated)
            store["/deliverables?unrated=true"] = 200 to page(list("/deliverables").filter { it.jsonObject["rating"] == null || it.jsonObject["rating"] is JsonNull })
            bumpInbox()
            return 200 to updated
        }
        Regex("^/threads/([^/]+)/messages$").find(path)?.let { m ->
            val code = m.groupValues[1]
            val key = "/threads/$code/messages"
            val items = list(key)
            val attachments = body?.get("attachments")?.jsonArray.orEmpty().mapNotNull { files[it.jsonPrimitive.content] }
            val text = body?.str("body").orEmpty()
            val voice = text.isNotBlank() && attachments.any { it.str("kind") == "audio" }
            val msg = buildJsonObject {
                put("id", "m${System.nanoTime()}"); put("ref", "$code-%04d".format(items.size + 1)); put("thread", code); put("kind", if (voice) "voice_transcript" else "text")
                put("attachments", JsonArray(attachments))
                put("author", buildJsonObject { put("kind", "owner"); put("code", "owner"); put("display_fa", "مدیر کل") })
                put("body", body?.get("body") ?: JsonPrimitive("")); put("created_at", Instant.now().toString())
            }
            store[key] = 200 to page(items + msg)
            return 201 to buildJsonObject { put("message", msg); put("reply", buildJsonObject { put("state", "queued") }) }
        }
        if (path == "/owner/presence") {
            val p = edit("/owner/presence") { it + mapOf("khalvat" to (body?.get("khalvat") ?: JsonPrimitive(false)), "since" to JsonPrimitive(Instant.now().toString())) }
            edit("/inbox/summary") { it + ("khalvat" to p.jsonObject["khalvat"]!!) }
            return 200 to p
        }
        if (path == "/control/kill-switch") {
            val scope = body?.str("scope")
            val change = mapOf(
                "state" to (body?.get("state") ?: JsonPrimitive("released")), "reason" to (body?.get("reason") ?: JsonNull),
                "changed_at" to JsonPrimitive(Instant.now().toString()), "changed_by" to JsonPrimitive("owner"),
            )
            return 200 to edit("/control/state") { c ->
                if (scope == "holding") c + ("holding" to JsonObject(c["holding"]!!.jsonObject + change))
                else c + ("companies" to JsonArray(c["companies"]!!.jsonArray.map { k -> if (k.jsonObject.str("scope") == scope) JsonObject(k.jsonObject + change) else k }))
            }
        }
        if (path == "/work") {
            return 201 to JsonObject(store["/work/w0"]!!.second.jsonObject + mapOf(
                "id" to JsonPrimitive("w-new"), "ref" to JsonPrimitive("W-000130"), "title" to (body?.get("title") ?: JsonPrimitive("")),
                "company" to (body?.get("company") ?: JsonPrimitive("HQ")), "status" to JsonPrimitive("queued"), "created_at" to JsonPrimitive(Instant.now().toString()),
            ))
        }
        Regex("^/threads/([^/]+)/read$").find(path)?.let { m ->
            return 200 to (list("/threads").firstOrNull { it.jsonObject.str("code") == m.groupValues[1] } ?: JsonObject(emptyMap()))
        }
        workshop(path, body)?.let { return it }
        if (path == "/orders") return order(body)
        if (path == "/notifications/read-all") return 200 to buildJsonObject { put("updated", 0) }
        if (path == "/auth/logout") return 204 to JsonObject(emptyMap())
        return 200 to JsonObject(emptyMap())
    }

    // ------------------------------------------------------------------ ⟨1.3⟩ --
    /** Uploaded files by id (a file:// URL in the app's cache), so a sent message can show what was attached. */
    private val files = mutableMapOf<String, JsonObject>()
    private val scripts = mutableMapOf<String, MutableList<JsonObject>>().apply {
        for ((k, v) in store) if (k.startsWith("#script:")) put(k.removePrefix("#script:"), v.second.jsonObject["items"]!!.jsonArray.map { it.jsonObject }.toMutableList())
    }
    private var said = 0

    private fun binary(req: okhttp3.Request, path: String): Pair<Int, JsonElement> {
        val bytes = Buffer().also { req.body!!.writeTo(it) }.readByteArray()
        val mime = req.body?.contentType()?.let { "${it.type}/${it.subtype}" } ?: "application/octet-stream"
        val name = req.header("X-File-Name")?.let { java.net.URLDecoder.decode(it, "UTF-8") } ?: "voice.m4a"
        val f = File(context.cacheDir, "demo-files/${System.nanoTime()}-${name.replace(Regex("[^\\p{L}\\p{N}._-]"), "_")}").apply { parentFile?.mkdirs(); writeBytes(bytes) }
        val id = Uri.fromFile(f).toString()
        val kind = kindOf(mime)
        val seconds = if (kind == "audio" || kind == "video") runCatching {
            MediaMetadataRetriever().run { try { setDataSource(f.absolutePath); extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toDouble()?.div(1000) } finally { release() } }
        }.getOrNull() else null
        val bounds = if (kind == "image") BitmapFactory.Options().apply { inJustDecodeBounds = true }.also { BitmapFactory.decodeFile(f.absolutePath, it) } else null
        val transcript = if (path == "/transcribe") TRANSCRIPTS.getValue(req.url.queryParameter("purpose") ?: "message").let { it[said++ % it.size] } else null
        val ref = buildJsonObject {
            put("id", id); put("name", name); put("mime", mime); put("size", bytes.size); put("sha256", "demo"); put("kind", kind); put("status", "ready")
            putJsonObject("variants") {}
            seconds?.let { put("duration_s", it) }
            bounds?.takeIf { it.outWidth > 0 }?.let { put("width", it.outWidth); put("height", it.outHeight) }
            transcript?.let { put("transcript", it) }
        }
        files[id] = ref
        if (path == "/files") return 201 to ref
        return 200 to buildJsonObject {
            put("text", transcript); put("language", "fa"); put("duration_s", seconds ?: 6.4); put("confidence", 0.94); put("file_id", id)
            putJsonArray("segments") { add(buildJsonObject { put("start_s", 0); put("end_s", seconds ?: 6.4); put("text", transcript) }) }
            putJsonObject("engine") { put("name", "faster-whisper"); put("model", "large-v3-turbo"); put("version", "demo") }
        }
    }

    private val owner = buildJsonObject { put("kind", "owner"); put("code", "owner"); put("display_fa", "مدیر کل") }
    private val sys = buildJsonObject { put("kind", "system"); put("code", "HQ-SYS"); put("display_fa", "سیستم") }

    private fun step(type: String, actor: JsonElement, summary: String, data: JsonObject = JsonObject(emptyMap())) =
        buildJsonObject { put("type", type); put("actor", actor); put("summary_fa", summary); put("data", data) }

    private fun session(ref: String): JsonObject = store["/workshop/sessions/$ref"]!!.second.jsonObject

    private fun saveSession(s: JsonObject) {
        val ref = s.str("ref")!!
        store["/workshop/sessions/$ref"] = 200 to s
        val all = list("/workshop/sessions")
        store["/workshop/sessions"] = 200 to page(if (all.any { it.jsonObject.str("ref") == ref }) all.map { if (it.jsonObject.str("ref") == ref) s else it } else listOf(s) + all)
    }

    /** One step happens now: numbered, stamped, and the session's state follows it. */
    private fun reveal(ref: String, e: JsonObject): JsonObject {
        val key = "/workshop/sessions/$ref/events"
        val items = list(key)
        val now = Instant.now().toString()
        val ev = JsonObject(e + mapOf("seq" to JsonPrimitive((items.lastOrNull()?.jsonObject?.get("seq")?.jsonPrimitive?.long ?: 0) + 1), "at" to JsonPrimitive(now)))
        store[key] = 200 to page(items + ev)
        val s = session(ref)
        val state = when {
            e.str("type") == "approval_request" -> "waiting_approval"
            e.str("type") == "state" -> e["data"]!!.jsonObject.str("state") ?: s.str("state")
            s.str("state") == "starting" -> "working"
            else -> s.str("state")
        }
        val usd = (s["usage"]!!.jsonObject["usd"]!!.jsonPrimitive.content.toDouble() + 0.07).let { Math.round(it * 100) / 100.0 }
        saveSession(JsonObject(s + mapOf("state" to JsonPrimitive(state), "updated_at" to JsonPrimitive(now), "usage" to JsonObject(s["usage"]!!.jsonObject + ("usd" to JsonPrimitive(usd))))))
        return ev
    }

    private fun workshop(path: String, body: JsonObject?): Pair<Int, JsonElement>? {
        Regex("^/workshop/sessions/(S-\\d+)/(messages|stop|approvals/([^/]+))$").find(path)?.let { m ->
            val ref = m.groupValues[1]
            val s = session(ref)
            val driver = s["driver"]!!
            val script = scripts.getOrPut(ref) { mutableListOf() }
            when (m.groupValues[2]) {
                "stop" -> { script.clear(); reveal(ref, step("state", owner, "مدیر کل متوقف کرد؛ شاخه میماند", buildJsonObject { put("state", "stopped") })); return 200 to session(ref) }
                "messages" -> {
                    val e = reveal(ref, step("message", owner, body?.str("body").orEmpty()))
                    if (s.str("state") !in setOf("done", "failed", "stopped")) script.add(0, step("message", driver, "دریافت شد؛ همین را اعمال میکنم و نتیجه را میگویم."))
                    return 201 to e
                }
            }
            val id = m.groupValues[3]
            val events = list("/workshop/sessions/$ref/events").map { it.jsonObject }
            val request = events.firstOrNull { it.str("type") == "approval_request" && it["data"]!!.jsonObject.str("approval_id") == id }
            if (request == null || events.any { it.str("type") == "approval_result" && it["data"]!!.jsonObject.str("approval_id") == id }) return 409 to problem("conflict", "این درخواست قبلاً جواب گرفته.")
            val allow = body?.get("allow")?.jsonPrimitive?.content == "true"
            val e = reveal(ref, step("approval_result", owner, if (allow) "مدیر کل اجازه داد" else "مدیر کل اجازه نداد", buildJsonObject { put("approval_id", id); put("allow", allow) }))
            saveSession(JsonObject(session(ref) + ("state" to JsonPrimitive("working"))))
            val branch = s.str("branch") ?: "hq/$ref"
            when {
                !allow -> script += listOf(step("message", driver, "باشد؛ دست نگه میدارم. اگر راه دیگری مد نظرت است بگو."), step("state", sys, "منتظر راهنمایی", buildJsonObject { put("state", "idle") }))
                request["data"]!!.jsonObject.str("action") == "push_branch" -> script += listOf(
                    step("command", driver, "push شد به $branch", buildJsonObject { put("cmd", "git push origin $branch"); put("exit_code", 0); put("duration_s", 3) }),
                    step("approval_request", driver, "اجازه‌ی باز کردن PR", buildJsonObject { put("approval_id", "AP-%04d".format(id.removePrefix("AP-").toInt() + 10)); put("action", "open_pr"); put("detail", "PR: $branch → main") }),
                )
                else -> {
                    val repo = list("/workshop/workspaces").firstOrNull { it.jsonObject.str("code") == s.str("workspace") }?.jsonObject?.str("repo")
                    val pr = "https://github.com/$repo/pull/4${ref.takeLast(1)}"
                    saveSession(JsonObject(session(ref) + ("pr_url" to JsonPrimitive(pr))))
                    script += listOf(step("progress", driver, "PR باز شد؛ ادغام و انتشار با مُهر تو", buildJsonObject { put("pr_url", pr) }), step("state", sys, "تمام شد", buildJsonObject { put("state", "done") }))
                }
            }
            return 201 to e
        }
        if (path == "/workshop/sessions") {
            val grant = list("/workshop/grants?active=true").firstOrNull { it.jsonObject.str("ref") == body?.str("grant") }?.jsonObject
                ?: return 409 to problem("grant_not_active", "این مجوز فعال نیست.")
            val ref = "S-%04d".format(list("/workshop/sessions").size + 1)
            val driver = grant["driver"]?.takeIf { it !is JsonNull } ?: owner
            val now = Instant.now().toString()
            val s = buildJsonObject {
                put("id", "s-$ref"); put("ref", ref); put("workspace", grant.str("workspace")); put("grant", grant.str("ref")); put("title", body?.str("title")); put("brief", body?.str("brief"))
                put("opened_by", owner); put("driver", driver); put("runtime", "managed"); put("model", "claude-sonnet-5-5"); put("effort", "high"); put("state", "starting")
                put("branch", "hq/$ref"); put("pr_url", JsonNull); putJsonObject("usage") { put("usd", 0.0); put("input_tokens", 0); put("output_tokens", 0) }; put("created_at", now); put("updated_at", now)
            }
            saveSession(s)
            store["/workshop/sessions/$ref/events"] = 200 to page(emptyList())
            scripts[ref] = mutableListOf(
                step("state", sys, "جلسه شروع شد؛ کلون تازه", buildJsonObject { put("state", "working") }),
                step("message", driver, "شروع کردم: ${body?.str("title")}. اول کد مربوط را میخوانم و اندازه میگیرم."),
                step("command", driver, "نقشه‌ی ریپو خوانده شد", buildJsonObject { put("cmd", "git log --oneline -20 && ls"); put("exit_code", 0); put("duration_s", 2) }),
                step("progress", driver, "فایل‌های مرتبط پیدا شد؛ در حال نوشتن اصلاح."),
            )
            return 201 to s
        }
        if (path == "/workshop/grants") {
            val key = "/workshop/grants?active=true"
            val code = body?.str("driver")
            val d = list("/employees").map { it.jsonObject }.firstOrNull { it.str("code") == code }
            val g = buildJsonObject {
                put("id", "g${System.nanoTime()}"); put("ref", "G-%04d".format(list(key).size + 1))
                for (k in listOf("workspace", "actions", "budget_usd", "expires_at")) body?.get(k)?.let { put(k, it) }
                put("driver", d?.let { buildJsonObject { put("kind", it.str("kind")); put("code", it.str("code")); put("display_fa", it.str("title_fa")) } } ?: JsonNull)
                put("granted_by", owner); put("decision_ref", JsonNull); put("revoked_at", JsonNull)
            }
            store[key] = 200 to JsonArray(listOf<JsonElement>(g) + list(key))
            return 201 to g
        }
        Regex("^/workshop/grants/(G-\\d+)/revoke$").find(path)?.let { m ->
            val key = "/workshop/grants?active=true"
            val g = list(key).firstOrNull { it.jsonObject.str("ref") == m.groupValues[1] }?.jsonObject ?: return 404 to problem("not_found", "پیدا نشد.")
            store[key] = 200 to JsonArray(list(key).filter { it.jsonObject.str("ref") != m.groupValues[1] })
            for (s in list("/workshop/sessions").map { it.jsonObject }) {
                if (s.str("grant") == g.str("ref") && s.str("state") !in setOf("done", "failed", "stopped")) {
                    scripts[s.str("ref")!!]?.clear()
                    reveal(s.str("ref")!!, step("state", owner, "مجوز ${g.str("ref")} لغو شد؛ جلسه متوقف شد", buildJsonObject { put("state", "stopped") }))
                }
            }
            return 200 to JsonObject(g + ("revoked_at" to JsonPrimitive(Instant.now().toString())))
        }
        return null
    }

    /** Rules first, like the hub (§17.4): a named company, then the kind of work from known words. */
    private fun order(body: JsonObject?): Pair<Int, JsonElement> {
        val text = body?.str("text").orEmpty()
        val co = when {
            Regex("تریدیار|tradeyar", RegexOption.IGNORE_CASE).containsMatchIn(text) -> "TY"
            Regex("پرو-?چارت|pro-?chart", RegexOption.IGNORE_CASE).containsMatchIn(text) -> "PC"
            Regex("FX|اف‌?ایکس", RegexOption.IGNORE_CASE).containsMatchIn(text) -> "FX"
            else -> null
        }
        val routes = mutableListOf<JsonObject>()
        fun route(company: String, to: String, kind: String, vararg refs: Pair<String, String>) = buildJsonObject { put("company", company); put("to", to); put("kind", kind); for ((k, v) in refs) put(k, v) }
        if ("جلسه" in text) routes += route("HQ", "HQ-ADV", "meeting")
        if (co != null && Regex("کد|شاخه|باگ|اصلاح|کارگاه").containsMatchIn(text)) {
            val live = list("/workshop/sessions").map { it.jsonObject }.firstOrNull { it.str("workspace")!!.startsWith(co) && it.str("state") in setOf("working", "waiting_approval", "idle") }
            routes += route(co, "$co-TECH-MGR", "work", "work_ref" to "W-000106")
            routes += if (live != null) route(co, "$co-TECH-MGR", "code", "session_ref" to live.str("ref")!!) else route(co, "$co-TECH-MGR", "code", "decision_ref" to "D-000020")
        } else if (co != null) routes += route(co, "$co-CEO", "work", "work_ref" to "W-000106")
        if (routes.isEmpty()) routes += route("HQ", "HQ-ADV", "question")
        val who = mapOf("work" to "کار", "code" to "کارگاه کد", "meeting" to "جلسه", "question" to "پرسش از مشاور کل")
        val o = buildJsonObject {
            put("ref", "F-%04d".format(list("/orders").size + 1)); put("text", text); put("source", body?.get("source") ?: JsonPrimitive("text")); put("file_id", body?.get("file_id") ?: JsonNull)
            put("created_at", Instant.now().toString()); put("routes", JsonArray(routes))
            put("summary_fa", "رسید: " + routes.joinToString("، ") { "${who[it.str("kind")]} (${it.str("company")})" } + ".")
        }
        store["/orders"] = 200 to page(listOf<JsonElement>(o) + list("/orders"))
        return 201 to o
    }

    private companion object {
        val TRANSCRIPTS = mapOf(
            "message" to listOf(
                "سلام. گزارش امروز دقت سیگنال‌های طلا را تا ساعت پنج بفرست و اگر افت ادامه داشت، دو پیشنهاد اصلاح هم کنارش بگذار.",
                "این عکس را ببین؛ رنگ دکمه‌ی خرید در حالت شب خوانا نیست. با تیم طراحی هماهنگ کن و نسخه‌ی اصلاح‌شده را نشانم بده.",
            ),
            "order" to listOf(
                "به مدیر فنی کوینه‌پرو FX بگو کندی صفحه‌ی ثبت‌نام را تا فردا ظهر بررسی کند و اصلاحش را در کارگاه کد روی شاخه‌ی جدا آماده کند.",
                "برای پنجشنبه یک جلسه با مدیرعامل‌های تریدیار و پرو-چارت بگذار؛ موضوع: برنامه‌ی رشد سه ماه آینده.",
            ),
            "note" to listOf("یادداشت: از مشاور کل بپرس هزینه‌ی کارگاه کد در ماه اول چقدر شد."),
        )
    }

    private fun bumpInbox() {
        val pending = list("/decisions?status=all").count { it.jsonObject.str("status") == "pending" }
        val unrated = list("/deliverables").count { it.jsonObject["rating"] == null || it.jsonObject["rating"] is JsonNull }
        edit("/inbox/summary") { it + mapOf("decisions_pending" to JsonPrimitive(pending), "deliverables_unrated" to JsonPrimitive(unrated)) }
    }

    private fun edit(key: String, f: (JsonObject) -> Map<String, JsonElement>): JsonElement {
        val (status, cur) = store[key] ?: (200 to JsonObject(emptyMap()))
        val next = JsonObject(f(cur.jsonObject))
        store[key] = status to next
        return next
    }

    private fun list(key: String): List<JsonElement> = store[key]?.second?.let { (it as? JsonObject)?.get("items") ?: it }?.jsonArray.orEmpty()

    private fun replaceIn(key: String, ref: String, item: JsonElement) {
        store[key] = 200 to page(list(key).map { if (it.jsonObject.str("ref") == ref) item else it })
    }

    private fun page(items: List<JsonElement>): JsonObject = buildJsonObject { put("items", JsonArray(items)); put("next_cursor", JsonNull) }

    private fun problem(code: String, fa: String) = buildJsonObject { put("code", code); put("message_fa", fa); put("status", 404); put("title", code); put("type", "about:blank") }

    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.content
}
