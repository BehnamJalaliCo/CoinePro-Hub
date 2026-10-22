package com.coinepro.hq

import android.content.Context
import android.graphics.BitmapFactory
import android.media.MediaMetadataRetriever
import android.net.Uri
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.modelLabel
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
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.intOrNull
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
    private val now = HqClock.now()
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
                s != null && Regex("^@-?\\d+d$").matches(s) -> JsonPrimitive(LocalDate.ofInstant(HqClock.now(), ZoneOffset.UTC).plusDays(s.drop(1).dropLast(1).toLong()).toString())
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
        val query = req.url.queryParameterNames.associateWith { req.url.queryParameter(it) }
        val version = req.header("If-Match")?.trim('"')?.toIntOrNull()
        if (req.method == "GET") {
            v17Read(path, query)?.let { return respond(req, it) }
            v16Read(path, query)?.let { return respond(req, it) }
            ownerToolsRead(path, query)?.let { return respond(req, it) }
        } else {
            v17Write(req.method, path, body, version, req.header("Idempotency-Key"), req.header("X-Step-Up"))?.let { return respond(req, it.status to it.body, it.headers) }
            v16Write(req.method, path, body, version, req.header("Idempotency-Key"))?.let { return respond(req, it.status to it.body, it.headers) }
            ownerToolsWrite(req.method, path, body, version)?.let { return respond(req, it) }
        }
        return respond(req, if (req.method == "GET") read(path, query) else write(path, body))
    }

    private fun respond(req: okhttp3.Request, result: Pair<Int, JsonElement>, headers: Map<String, String> = emptyMap()): Response {
        val (status, out) = result
        return Response.Builder()
            .request(req).protocol(Protocol.HTTP_1_1).code(status).message("demo")
            .apply { for ((k, v) in headers) header(k, v) }
            .body(out.toString().toResponseBody("application/json".toMediaType()))
            .build()
    }

    private fun read(path: String, query: Map<String, String?>): Pair<Int, JsonElement> {
        fun key(drop: Set<String>): String {
            val q = query.filterKeys { it !in drop }.filterValues { it != null }.toSortedMap()
            return if (q.isEmpty()) path else path + "?" + q.entries.joinToString("&") { "${it.key}=${it.value}" }
        }
        Regex("^/provisioning/runs/([^/]+)$").find(path)?.let { m -> return advanceRun(m.groupValues[1]) }
        Regex("^/companies/([A-Z0-9]+)/brand(/versions)?$").find(path)?.let { m -> return brandRead(m.groupValues[1], m.groupValues[2].isNotEmpty()) }
        // A parameter that selects (⟨1.4⟩ period=month, from=HQ-ADV) matches first; ranges and paging never do.
        store[key(setOf("limit", "cursor"))]?.let { return it }
        val q = query.filterKeys { it !in setOf("limit", "cursor", "from", "to", "period") }.filterValues { it != null }.toSortedMap()
        store[key(setOf("limit", "cursor", "from", "to", "period"))]?.let { return it }
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
            val stamp = HqClock.now().toString()
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
            if (verdict == "approve") { decided16(updated.jsonObject); decided17(updated.jsonObject) }
            return 200 to updated
        }
        Regex("^/deliverables/(O-\\d+)/rating$").find(path)?.let { m ->
            val ref = m.groupValues[1]
            val rating = buildJsonObject { put("score", body?.get("score")!!); put("comment", body["comment"] ?: JsonNull); put("history_count", 1); put("rated_at", HqClock.now().toString()) }
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
                put("body", body?.get("body") ?: JsonPrimitive("")); put("created_at", HqClock.now().toString())
            }
            store[key] = 200 to page(items + msg)
            return 201 to buildJsonObject { put("message", msg); put("reply", buildJsonObject { put("state", "queued") }) }
        }
        if (path == "/owner/presence") {
            val p = edit("/owner/presence") { it + mapOf("khalvat" to (body?.get("khalvat") ?: JsonPrimitive(false)), "since" to JsonPrimitive(HqClock.now().toString())) }
            edit("/inbox/summary") { it + ("khalvat" to p.jsonObject["khalvat"]!!) }
            return 200 to p
        }
        if (path == "/control/kill-switch") {
            val scope = body?.str("scope")
            val change = mapOf(
                "state" to (body?.get("state") ?: JsonPrimitive("released")), "reason" to (body?.get("reason") ?: JsonNull),
                "changed_at" to JsonPrimitive(HqClock.now().toString()), "changed_by" to JsonPrimitive("owner"),
            )
            return 200 to edit("/control/state") { c ->
                if (scope == "holding") c + ("holding" to JsonObject(c["holding"]!!.jsonObject + change))
                else c + ("companies" to JsonArray(c["companies"]!!.jsonArray.map { k -> if (k.jsonObject.str("scope") == scope) JsonObject(k.jsonObject + change) else k }))
            }
        }
        if (path == "/work") {
            return 201 to JsonObject(store["/work/w0"]!!.second.jsonObject + mapOf(
                "id" to JsonPrimitive("w-new"), "ref" to JsonPrimitive("W-000130"), "title" to (body?.get("title") ?: JsonPrimitive("")),
                "company" to (body?.get("company") ?: JsonPrimitive("HQ")), "status" to JsonPrimitive("queued"), "created_at" to JsonPrimitive(HqClock.now().toString()),
            ))
        }
        Regex("^/threads/([^/]+)/read$").find(path)?.let { m ->
            return 200 to (list("/threads").firstOrNull { it.jsonObject.str("code") == m.groupValues[1] } ?: JsonObject(emptyMap()))
        }
        workshop(path, body)?.let { return it }
        brand(path, body)?.let { return it }
        v14(path, body)?.let { return it }
        hiring(path, body)?.let { return it }
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
        val now = HqClock.now().toString()
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
            val now = HqClock.now().toString()
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
            return 200 to JsonObject(g + ("revoked_at" to JsonPrimitive(HqClock.now().toString())))
        }
        return null
    }

    // ------------------------------------------------------------------ ⟨1.4⟩ --
    private val stamp: JsonPrimitive get() = JsonPrimitive(HqClock.now().toString())

    /** Replaces the item with [ref] (or [idKey]) in a list or page stored at [key], returning the updated item. */
    private fun update(key: String, ref: String, idKey: String = "ref", f: (JsonObject) -> Map<String, JsonElement>): JsonObject? {
        val (status, cur) = store[key] ?: return null
        var hit: JsonObject? = null
        val items = list(key).map { e -> if (e.jsonObject.str(idKey) == ref) JsonObject(f(e.jsonObject)).also { hit = it } else e }
        store[key] = status to (if (cur is JsonObject && cur.containsKey("items")) page(items) else JsonArray(items))
        return hit
    }

    private fun prepend(key: String, item: JsonObject) {
        val (status, cur) = store[key] ?: (200 to JsonArray(emptyList()))
        store[key] = status to (if (cur is JsonObject && cur.containsKey("items")) page(listOf(item) + list(key)) else JsonArray(listOf(item) + list(key)))
    }

    private fun v14(path: String, body: JsonObject?): Pair<Int, JsonElement>? {
        Regex("^/oversight/holds/(H-\\d+)/(release|cancel)$").find(path)?.let { m ->
            val (ref, verb) = m.destructured
            val h = list("/oversight/holds?state=held").firstOrNull { it.jsonObject.str("ref") == ref }?.jsonObject ?: return 404 to problem("not_found", "پیدا نشد.")
            store["/oversight/holds?state=held"] = 200 to JsonArray(list("/oversight/holds?state=held").filter { it.jsonObject.str("ref") != ref })
            edit("/oversight/summary") { it + ("holds_waiting" to JsonPrimitive(list("/oversight/holds?state=held").size)) }
            return 200 to JsonObject(h + mapOf("state" to JsonPrimitive(if (verb == "release") "released" else "cancelled"), "decided_by" to owner, "decided_at" to stamp))
        }
        Regex("^/oversight/findings/(FI-\\d+)/status$").find(path)?.let { m ->
            val st = body?.get("status") ?: JsonPrimitive("closed")
            val step = buildJsonObject { put("at", stamp); put("by", owner); put("status", st); put("note", body?.get("note") ?: JsonPrimitive("")) }
            return 200 to (update("/oversight/findings", m.groupValues[1]) { f ->
                f + mapOf("status" to st, "history" to JsonArray(f["history"]?.jsonArray.orEmpty() + step)) +
                    (if (st.jsonPrimitive.content in setOf("verified", "closed")) mapOf("closed_at" to stamp) else emptyMap())
            } ?: return 404 to problem("not_found", "پیدا نشد."))
        }
        if (path == "/oversight/orders") {
            val o = buildJsonObject {
                put("id", "so${System.nanoTime()}"); put("ref", "SO-%03d".format(list("/oversight/orders").size + 3)); put("text_md", body?.get("text_md") ?: JsonPrimitive(""))
                put("source", body?.get("source") ?: JsonPrimitive("text")); put("file_id", body?.get("file_id") ?: JsonNull); put("applies_to", body?.get("applies_to") ?: JsonPrimitive("overseer"))
                put("status", "proposed"); put("version", 1); put("sealed_at", JsonNull); put("created_at", stamp)
            }
            prepend("/oversight/orders", o)
            return 201 to o
        }
        Regex("^/oversight/orders/(SO-\\d+)/(seal|retire)$").find(path)?.let { m ->
            val seal = m.groupValues[2] == "seal"
            return 200 to (update("/oversight/orders", m.groupValues[1]) { it + mapOf("status" to JsonPrimitive(if (seal) "sealed" else "retired")) + (if (seal) mapOf("sealed_at" to stamp) else emptyMap()) }
                ?: return 404 to problem("not_found", "پیدا نشد."))
        }
        Regex("^/errands/(E-\\d+)/cancel$").find(path)?.let { m ->
            return 200 to (update("/errands", m.groupValues[1]) { it + ("status" to JsonPrimitive("cancelled")) } ?: return 404 to problem("not_found", "پیدا نشد."))
        }
        if (path == "/skills") {
            val s = buildJsonObject {
                put("id", "sk${System.nanoTime()}"); put("ref", "SK-%03d".format(list("/skills").size + 1)); put("name_fa", body?.get("name_fa") ?: JsonPrimitive(""))
                put("summary_fa", JsonPrimitive(body?.str("body_md").orEmpty().take(120))); put("body_md", body?.get("body_md") ?: JsonPrimitive(""))
                putJsonArray("resources") {}; putJsonObject("scope") { put("roles", body?.get("roles") ?: JsonArray(emptyList())); put("companies", body?.get("companies") ?: JsonPrimitive("all")); putJsonArray("departments") {} }
                put("version", 1); put("status", "in_review"); put("review", JsonNull); put("eval", JsonNull); put("created_by", owner); put("created_at", stamp); put("activated_at", JsonNull)
            }
            prepend("/skills", s)
            return 201 to s
        }
        Regex("^/skills/(SK-\\d+)/(activate|retire)$").find(path)?.let { m ->
            val (ref, verb) = m.destructured
            val cur = list("/skills").firstOrNull { it.jsonObject.str("ref") == ref }?.jsonObject ?: return 404 to problem("not_found", "پیدا نشد.")
            if (verb == "activate" && cur.str("status") != "approved") return 409 to problem("not_approved", "این مهارت هنوز بررسی و آزمون را نگذرانده است.")
            return 200 to update("/skills", ref) { it + mapOf("status" to JsonPrimitive(if (verb == "activate") "active" else "retired")) + (if (verb == "activate") mapOf("activated_at" to stamp) else emptyMap()) }!!
        }
        if (path == "/academy/teach") {
            val text = body?.str("text").orEmpty()
            val t = buildJsonObject {
                put("id", "te${System.nanoTime()}"); put("ref", "TE-%04d".format(list("/academy/teach").size + 1)); put("target", body?.get("target") ?: JsonNull)
                put("source", body?.get("source") ?: JsonPrimitive("text")); put("text_md", text); put("file_id", body?.get("file_id") ?: JsonNull)
                // The demo skips the AI-ops rewrite: the proposal and its eval arrive at once.
                putJsonObject("proposal") { put("kind", "charter_rule"); put("diff_md", "+ $text") }
                putJsonObject("eval_run") { put("score", 92); put("baseline", 90); put("passed", true) }
                put("status", "proposed"); put("created_at", stamp)
            }
            prepend("/academy/teach", t)
            return 201 to t
        }
        Regex("^/academy/teach/(TE-\\d+)/(approve|reject)$").find(path)?.let { m ->
            return 200 to (update("/academy/teach", m.groupValues[1]) { it + ("status" to JsonPrimitive(if (m.groupValues[2] == "approve") "approved" else "rejected")) }
                ?: return 404 to problem("not_found", "پیدا نشد."))
        }
        Regex("^/tools/mcp/([^/]+)/(enable|disable)$").find(path)?.let { m ->
            val on = m.groupValues[2] == "enable"
            return 200 to (update("/tools/mcp", m.groupValues[1], idKey = "key") { s ->
                s + mapOf("status" to JsonPrimitive(if (on) "enabled" else "disabled"), "tools" to JsonArray(s["tools"]!!.jsonArray.map { JsonObject(it.jsonObject + ("enabled" to JsonPrimitive(on))) }))
            } ?: return 404 to problem("not_found", "پیدا نشد."))
        }
        if (path == "/foundings") {
            val src = body?.get("source")?.jsonObject
            val ref = "C-%04d".format(list("/foundings").size + 1)
            val f = buildJsonObject {
                put("id", "fo${System.nanoTime()}"); put("ref", ref); put("name_fa", JsonNull); put("name_en", JsonNull); put("code", JsonNull)
                put("source", src ?: JsonNull); put("state", "auditing"); put("audit", JsonNull); put("proposal", JsonNull); put("decision_ref", JsonNull); put("plan", JsonNull); put("company", JsonNull)
                put("created_at", stamp); put("updated_at", stamp)
            }
            prepend("/foundings", f)
            store["/foundings/$ref"] = 200 to f
            return 201 to f
        }
        Regex("^/foundings/(C-\\d+)/(activate|cancel)$").find(path)?.let { m ->
            val (ref, verb) = m.destructured
            // ⟨1.4.6⟩ §18.8: no active brand → 409 not_ready, unless the owner activates without it.
            val brand = store["/foundings/$ref"]?.second?.jsonObject?.get("brand") as? JsonObject
            if (verb == "activate" && brand?.str("state") != "active" && (body?.get("skip_brand") as? JsonPrimitive)?.booleanOrNull != true) {
                return 409 to buildJsonObject {
                    put("code", "not_ready"); put("message_fa", "شرکت هنوز مُهر ندارد؛ نشانش را از لوگوی PNG بساز یا بدون مُهر فعال کن.")
                    putJsonArray("missing") { add(JsonPrimitive("brand")) }; put("status", 409); put("title", "Not ready"); put("type", "about:blank")
                }
            }
            // §18.16: cancelling returns a sealed but unrun plan to `proposed`.
            val planRef = store["/foundings/$ref"]?.second?.jsonObject?.str("plan")
            val plan = planRef?.let { store["/provisioning/plans/$it"]?.second?.jsonObject }
            if (verb == "cancel" && plan?.str("state") == "sealed") store["/provisioning/plans/$planRef"] = 200 to JsonObject(plan + mapOf("state" to JsonPrimitive("proposed"), "sealed_at" to JsonNull))
            val f = saveFounding(ref) { it + mapOf("state" to JsonPrimitive(if (verb == "activate") "active" else "cancelled"), "updated_at" to stamp) } ?: return 404 to problem("not_found", "پیدا نشد.")
            return 200 to f
        }
        Regex("^/provisioning/plans/(PV-\\d+)/seal$").find(path)?.let { m ->
            val ref = m.groupValues[1]
            val pl = store["/provisioning/plans/$ref"]?.second?.jsonObject ?: return 404 to problem("not_found", "پیدا نشد.")
            // No price, no seal (§18.16).
            if (pl["monthly_eur"] !is JsonPrimitive || (pl["problems"] as? JsonArray)?.isNotEmpty() == true) return 409 to problem("price_unknown", "قیمت این طرح هنوز معلوم نیست؛ بدون قیمت مُهر نمیشود.")
            val id = "r${System.nanoTime()}"
            // The steps a build goes through are the hub's; the finished demo build lends its list.
            val template = store["/provisioning/runs/r1"]!!.second.jsonObject["steps"]!!.jsonArray
            store["/provisioning/runs/$id"] = 200 to buildJsonObject {
                put("id", id); put("plan", ref); put("state", "queued"); put("server", JsonNull); put("login", JsonNull); put("error", JsonNull)
                put("steps", JsonArray(template.map { s ->
                    JsonObject(s.jsonObject + mapOf("state" to JsonPrimitive("pending"), "started_at" to JsonNull, "finished_at" to JsonNull, "log_tail" to JsonArray(emptyList())))
                }))
            }
            val sealed = JsonObject(pl + mapOf("state" to JsonPrimitive("running"), "run" to JsonPrimitive(id), "decision_ref" to JsonPrimitive("D-000025"), "sealed_at" to stamp))
            store["/provisioning/plans/$ref"] = 200 to sealed
            pl.str("founding")?.let { saveFounding(it) { f -> f + mapOf("state" to JsonPrimitive("provisioning"), "updated_at" to stamp) } }
            return 200 to sealed
        }
        Regex("^/provisioning/runs/([^/]+)/resume$").find(path)?.let { m ->
            val id = m.groupValues[1]
            val r = store["/provisioning/runs/$id"]?.second?.jsonObject ?: return 404 to problem("not_found", "پیدا نشد.")
            if (r.str("state") != "failed") return 409 to problem("conflict", "فقط ساخت شکست‌خورده ادامه پیدا میکند.")
            val steps = r["steps"]!!.jsonArray.map { it.jsonObject }.toMutableList()
            val i = steps.indexOfFirst { it.str("state") == "failed" }
            if (i >= 0) steps[i] = JsonObject(steps[i] + mapOf("state" to JsonPrimitive("running"), "started_at" to stamp, "finished_at" to JsonNull))
            val next = JsonObject(r + mapOf("state" to JsonPrimitive("running"), "error" to JsonNull, "steps" to JsonArray(steps)))
            store["/provisioning/runs/$id"] = 200 to next
            return 200 to next
        }
        return null
    }

    // ---------------------------------------------------------------- ⟨1.4.6⟩ --
    // The companies' brands (§18.14), as the web's mock-brand.ts: an upload is traced about three seconds later with another
    // company's two-colour mark; a file named like a photo fails `no_background`, one named "complex" `too_complex` above detail 1.
    private val tracing = mutableMapOf<String, Long>()
    private val traced = mutableMapOf<String, Pair<String, String>>()

    private fun versions(code: String): List<JsonObject> = list("/companies/$code/brand/versions").map { it.jsonObject }

    private fun brandRead(code: String, all: Boolean): Pair<Int, JsonElement> {
        val now = System.currentTimeMillis()
        val due = tracing.filter { (k, at) -> k.startsWith("$code/") && now - at >= 3_000 }.keys
        if (due.isNotEmpty()) saveBrand(code, versions(code).map { v -> if ("$code/${v.int("version")}" in due) trace(v) else v })
        due.forEach(tracing::remove)
        return store[if (all) "/companies/$code/brand/versions" else "/companies/$code/brand"]
            ?: (200 to if (all) JsonArray(emptyList()) else buildJsonObject { put("active", JsonNull); put("proposed", JsonNull) })
    }

    /** The versions, and everything that shows them: the company's view, /brands, `brand_version` and `Founding.brand`. */
    private fun saveBrand(code: String, all: List<JsonObject>) {
        val sorted = all.sortedByDescending { it.int("version") }
        store["/companies/$code/brand/versions"] = 200 to JsonArray(sorted)
        val active = sorted.firstOrNull { it.str("state") == "active" }
        val proposed = sorted.firstOrNull { it.str("state") == "proposed" && it.int("version") > (active?.int("version") ?: 0) }
        store["/companies/$code/brand"] = 200 to buildJsonObject { put("active", active ?: JsonNull); put("proposed", proposed ?: JsonNull) }
        if (active != null) edit("/brands") { b ->
            val one = buildJsonObject { put("version", active["version"]!!); for (k in listOf("mark", "wordmark", "ink", "accent", "accent_night", "accent_day")) put(k, active[k] ?: JsonNull) }
            b + ("companies" to JsonObject((b["companies"] as? JsonObject).orEmpty() + (code to one)))
        }
        val version = active?.get("version") ?: JsonNull
        store["/companies/$code"]?.let { (st, co) -> store["/companies/$code"] = st to JsonObject(co.jsonObject + ("brand_version" to version)) }
        update("/companies", code, idKey = "code") { it + ("brand_version" to version) }
        val fb = buildJsonObject {
            put("state", if (active != null) "active" else if (proposed != null) "proposed" else "missing"); put("version", (active ?: proposed)?.get("version") ?: JsonNull)
        }
        for (ref in list("/foundings").map { it.jsonObject }.filter { it.str("company") == code }.mapNotNull { it.str("ref") }) saveFounding(ref) { it + ("brand" to fb) }
    }

    private fun startBrand(code: String, source: JsonObject, part: String, options: JsonObject?, name: String): JsonObject {
        val all = versions(code)
        val version = (all.maxOfOrNull { it.int("version") } ?: 0) + 1
        val v = buildJsonObject {
            put("company", code); put("version", version); put("state", "processing"); put("source", source)
            put("mark", JsonNull); put("wordmark", JsonNull); put("ink", "#111216"); put("accent", JsonNull); put("accent_night", JsonNull); put("accent_day", JsonNull)
            putJsonArray("palette") {}
            putJsonObject("options") { options?.get("colors")?.let { put("colors", it) }; put("detail", options?.get("detail") ?: JsonPrimitive(3)) }
            put("checks", JsonNull); put("digest", ""); put("status_reason", JsonNull); put("created_at", stamp); put("activated_at", JsonNull)
        }
        tracing["$code/$version"] = System.currentTimeMillis()
        traced["$code/$version"] = part to name
        saveBrand(code, all + v)
        return v
    }

    private fun trace(v: JsonObject): JsonObject {
        val code = v.str("company")!!
        val (part, name) = traced["$code/${v.int("version")}"] ?: ("mark" to "logo.png")
        val opts = v["options"]!!.jsonObject
        val detail = opts.int("detail").coerceIn(1, 5)
        if (Regex("photo|عکس|img_", RegexOption.IGNORE_CASE).containsMatchIn(name)) return JsonObject(v + mapOf("state" to JsonPrimitive("failed"), "status_reason" to JsonPrimitive("no_background")))
        if (Regex("complex|پیچیده", RegexOption.IGNORE_CASE).containsMatchIn(name) && detail > 1) return JsonObject(v + mapOf("state" to JsonPrimitive("failed"), "status_reason" to JsonPrimitive("too_complex")))
        val donor = (store["/brands"]!!.second.jsonObject["companies"] as JsonObject).entries.first { (c, b) -> c != code && b.jsonObject.str("accent") != null }.value.jsonObject
        val prev = versions(code).firstOrNull { it.str("state") == "active" }
        // One colour asked for: every layer is the body.
        fun mono(m: JsonElement): JsonElement = if (opts.int("colors") != 1 || m !is JsonObject) m else {
            val ink = m["layers"]!!.jsonArray.map { it.jsonObject }.firstOrNull { it.str("role") == "ink" }?.str("color") ?: "#111216"
            JsonObject(m + ("layers" to JsonArray(m["layers"]!!.jsonArray.map { JsonObject(it.jsonObject + mapOf("role" to JsonPrimitive("ink"), "color" to JsonPrimitive(ink))) })))
        }
        val mark = mono(if (part == "mark") donor["mark"]!! else prev?.get("mark") ?: donor["mark"]!!)
        val wordmark = mono(if (part == "wordmark") donor["wordmark"] ?: JsonNull else prev?.get("wordmark") ?: JsonNull)
        val layers = mark.jsonObject["layers"]!!.jsonArray.map { it.jsonObject }
        val ink = layers.firstOrNull { it.str("role") == "ink" }?.str("color") ?: "#111216"
        val accent = layers.firstOrNull { it.str("role") == "accent" }?.str("color")
        val night = accent?.let { passing(it, night = true) }
        val day = accent?.let { passing(it, night = false) }
        val min = listOf(1.6, 1.3, 1.1, 0.9, 0.7)[detail - 1]
        val warnings = buildList {
            if (Regex("\\.(jpe?g|webp)$", RegexOption.IGNORE_CASE).containsMatchIn(name)) add("بدون شفافیت")
            if (min < 1) add("در اندازه‌ی کوچک جزئیات گم میشود")
            if (night != null) add("رنگ امضا روی زمینه‌ی شب کم‌کنتراست بود؛ برای شب روشن‌تر شد")
            if (day != null) add("رنگ امضا روی زمینه‌ی روز کم‌کنتراست بود؛ برای روز تیره‌تر شد")
        }
        val bytes = listOf(mark, wordmark).sumOf { m -> (m as? JsonObject)?.get("layers")?.jsonArray?.sumOf { it.jsonObject.str("d")?.length ?: 0 } ?: 0 }
        return JsonObject(v + mapOf(
            "state" to JsonPrimitive("proposed"), "mark" to mark, "wordmark" to wordmark, "ink" to JsonPrimitive(ink), "accent" to JsonPrimitive(accent),
            "accent_night" to JsonPrimitive(night), "accent_day" to JsonPrimitive(day),
            "options" to buildJsonObject { put("colors", opts["colors"] ?: JsonPrimitive(layers.map { it.str("color") }.distinct().size)); put("detail", detail) },
            "palette" to JsonArray(listOfNotNull(
                buildJsonObject { put("hex", ink); put("share", if (accent != null) 0.64 else 1.0) },
                accent?.let { buildJsonObject { put("hex", it); put("share", 0.36) } },
            )),
            "checks" to buildJsonObject {
                put("paths_bytes", bytes); put("min_feature_px_16", min); put("iou", 0.9 + detail * 0.015)
                put("contrast_night", accent?.let { contrast(it, PAGE_NIGHT) }); put("contrast_day", accent?.let { contrast(it, PAGE_DAY) })
                putJsonArray("warnings") { warnings.forEach { add(JsonPrimitive(it)) } }
            },
            "digest" to JsonPrimitive(Api.sha256("$code/${v.int("version")}/$mark/$wordmark/$ink/$accent/$night/$day")),
        ))
    }

    private fun brand(path: String, body: JsonObject?): Pair<Int, JsonElement>? {
        Regex("^/companies/([A-Z0-9]+)/brand$").find(path)?.let { m ->
            val id = body?.str("file_id") ?: return 422 to problem("validation_failed", "فایل لوگو لازم است.")
            val f = files[id]
            val name = f?.str("name") ?: "logo.png"
            val source = buildJsonObject {
                put("kind", "upload"); put("file_id", id); put("path", JsonNull); put("sha256", f?.str("sha256") ?: "demo")
                put("width", f?.get("width") ?: JsonPrimitive(1024)); put("height", f?.get("height") ?: JsonPrimitive(1024)); put("has_alpha", !Regex("\\.jpe?g$", RegexOption.IGNORE_CASE).containsMatchIn(name))
            }
            return 202 to startBrand(m.groupValues[1], source, body.str("part") ?: "mark", body["options"] as? JsonObject, name)
        }
        Regex("^/companies/([A-Z0-9]+)/brand/(\\d+)/(retrace|activate)$").find(path)?.let { m ->
            val (code, ver, verb) = m.destructured
            val v = versions(code).firstOrNull { it.int("version") == ver.toInt() } ?: return 404 to problem("not_found", "این نسخه پیدا نشد.")
            if (verb == "retrace") {
                val (part, name) = traced["$code/$ver"] ?: ("mark" to "logo.png")
                return 202 to startBrand(code, v["source"]!!.jsonObject, part, body?.get("options") as? JsonObject ?: v["options"] as? JsonObject, name)
            }
            if (v.str("state") != "proposed") return 409 to problem("brand_not_proposed", "این نسخه هنوز آماده‌ی مُهر نیست.")
            val next = versions(code).map { x ->
                when {
                    x.int("version") == ver.toInt() -> JsonObject(x + mapOf("state" to JsonPrimitive("active"), "activated_at" to stamp))
                    x.str("state") == "active" -> JsonObject(x + ("state" to JsonPrimitive("retired")))
                    else -> x
                }
            }
            saveBrand(code, next)
            return 200 to next.first { it.int("version") == ver.toInt() }
        }
        return null
    }

    private fun lum(hex: String): Double {
        val ch = (0..2).map { hex.removePrefix("#").substring(it * 2, it * 2 + 2).toInt(16) / 255.0 }.map { if (it <= 0.04045) it / 12.92 else Math.pow((it + 0.055) / 1.055, 2.4) }
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    }

    private fun contrast(a: String, b: String): Double = (maxOf(lum(a), lum(b)) + 0.05) / (minOf(lum(a), lum(b)) + 0.05)

    /** The accent made lighter (night) or darker (day) until it passes 3:1 on that page; null when it already does. */
    private fun passing(accent: String, night: Boolean): String? {
        val page = if (night) PAGE_NIGHT else PAGE_DAY
        if (contrast(accent, page) >= 3) return null
        val rgb = (0..2).map { accent.removePrefix("#").substring(it * 2, it * 2 + 2).toInt(16) }
        for (i in 1..50) {
            val c = "#" + rgb.joinToString("") { v -> "%02X".format(Math.round(v + ((if (night) 255 else 0) - v) * i * 0.02).toInt()) }
            if (contrast(c, page) >= 3) return c
        }
        return null
    }

    private fun saveFounding(ref: String, f: (JsonObject) -> Map<String, JsonElement>): JsonObject? {
        val next = update("/foundings", ref, f = f) ?: return null
        store["/foundings/$ref"] = 200 to next
        return next
    }

    /** Live demo, as the web's mock: each poll of a running build finishes one step and starts the next; the last one
     *  leaves the server ready for the owner's own login. Log lines come from the plan being built. */
    private fun advanceRun(id: String): Pair<Int, JsonElement> {
        val (_, cur) = store["/provisioning/runs/$id"] ?: return 404 to problem("not_found", "پیدا نشد.")
        var r = cur.jsonObject
        // The first poll starts a queued run.
        if (r.str("state") == "queued") {
            val steps = r["steps"]!!.jsonArray.map { it.jsonObject }.toMutableList()
            steps[0] = JsonObject(steps[0] + mapOf("state" to JsonPrimitive("running"), "started_at" to stamp))
            r = JsonObject(r + mapOf("state" to JsonPrimitive("running"), "steps" to JsonArray(steps)))
            store["/provisioning/runs/$id"] = 200 to r
            return 200 to r
        }
        if (r.str("state") != "running") return 200 to r
        val plan = store["/provisioning/plans/${r.str("plan")}"]!!.second.jsonObject
        val steps = r["steps"]!!.jsonArray.map { it.jsonObject }.toMutableList()
        val i = steps.indexOfFirst { it.str("state") != "done" }
        if (i >= 0) {
            steps[i] = JsonObject(steps[i] + mapOf("state" to JsonPrimitive("done"), "finished_at" to stamp, "log_tail" to JsonArray(logFor(steps[i].str("key")!!, plan).map { JsonPrimitive(it) })))
            if (i + 1 < steps.size) steps[i + 1] = JsonObject(steps[i + 1] + mapOf("state" to JsonPrimitive("running"), "started_at" to stamp))
            r = JsonObject(r + ("steps" to JsonArray(steps)))
            if (steps[i].str("key") == "server") r = JsonObject(r + ("server" to buildJsonObject { put("name", plan.str("name")); put("ipv4", "203.0.113.31"); put("ipv6", "2001:db8::31"); put("private_ip", "10.10.1.6")
                // The demo build lends the finished one's host keys.
                put("host_keys", store["/provisioning/runs/r1"]?.second?.jsonObject?.get("server")?.jsonObject?.get("host_keys") ?: JsonArray(emptyList()))
            }))
        }
        if (steps.all { it.str("state") == "done" }) {
            r = JsonObject(r + mapOf("state" to JsonPrimitive("done"), "login" to buildJsonObject { put("ssh", "ssh ${plan.str("work_user")}@203.0.113.31"); putJsonArray("then") { add(JsonPrimitive("claude")) } }))
            store["/provisioning/plans/${r.str("plan")}"] = 200 to JsonObject(plan + ("state" to JsonPrimitive("done")))
            plan.str("founding")?.let { saveFounding(it) { f -> f + mapOf("state" to JsonPrimitive("ready_for_login"), "updated_at" to stamp) } }
        }
        store["/provisioning/runs/$id"] = 200 to r
        return 200 to r
    }

    /** The last lines a step leaves (§18.16), as the web's mock writes them from the plan being built. */
    private fun logFor(key: String, plan: JsonObject): List<String> = when (key) {
        "ssh-key" -> listOf("owner key registered (label managed-by=coinepro-hq)")
        "firewall" -> listOf("firewall fw-${plan.str("name")!!.replace(Regex("-\\d+$"), "")}") + plan["firewall"]!!.jsonArray.map { w ->
            val port = w.jsonObject.str("port")
            "in ${w.jsonObject.str("protocol")}${port?.let { " $it" } ?: ""} from ${if (w.jsonObject["sources"]!!.jsonArray.any { it.jsonPrimitive.content == "owner" }) "owner IPs" else "any"}"
        }
        "server" -> listOf("${plan.str("type")} · ${plan.str("location")} · ${plan.str("image")}", "no root password")
        "boot" -> listOf("running", "ssh answers")
        "cloud-init" -> listOf("apt full-upgrade ✓ · unattended-upgrades ✓", "docker 28.x ✓ · node 22 LTS ✓", "claude-code ✓ · repo cloned ✓")
        "verify" -> listOf("ssh: keys only, root login off", "auto security updates on")
        else -> listOf("ready")
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
            put("created_at", HqClock.now().toString()); put("routes", JsonArray(routes))
            put("summary_fa", "رسید: " + routes.joinToString("، ") { "${who[it.str("kind")]} (${it.str("company")})" } + ".")
        }
        store["/orders"] = 200 to page(listOf<JsonElement>(o) + list("/orders"))
        return 201 to o
    }

    private companion object {
        /** The page surfaces a brand's accent is checked against (design/tokens, night and day). */
        const val PAGE_NIGHT = "#0B0D14"
        const val PAGE_DAY = "#F3EEE3"

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

    // ---------------------------------------------------------------- ⟨1.4.4⟩ --
    // The owner's tools on existing APIs (docs/GAP_ANALYSIS_v2.md §5A): the fixtures hold whole lists, the demo filters and pages them.
    private fun ownerToolsRead(path: String, q: Map<String, String?>): Pair<Int, JsonElement>? {
        fun has(o: JsonObject, k: String, v: String?) = v == null || o.str(k) == v
        when (path) {
            "/runs" -> return 200 to page(list("/runs").map { it.jsonObject }.filter { has(it, "employee", q["employee"]) && has(it, "state", q["state"]) && has(it, "company", q["company"]) })
            "/resolutions" -> {
                val text = q["q"]?.trim().orEmpty()
                return 200 to page(list("/resolutions").map { it.jsonObject }.filter { r ->
                    has(r, "company", q["company"]) && (text.isEmpty() || listOf("ref", "title", "body").any { r.str(it).orEmpty().contains(text) })
                })
            }
            "/search/messages" -> {
                val text = q["q"]?.trim().orEmpty()
                if (text.length < 2) return 422 to problem("validation_failed", "دست‌کم دو حرف.")
                val hits = store.keys.filter { it.matches(Regex("^/threads/[^/]+/messages$")) }.flatMap { key ->
                    val thread = key.removePrefix("/threads/").removeSuffix("/messages")
                    list(key).map { it.jsonObject }.filter { it.str("body").orEmpty().contains(text) }.map { m ->
                        buildJsonObject {
                            put("id", m["id"] ?: JsonPrimitive(m.str("ref"))); put("ref", m["ref"]!!); put("thread", thread); put("author", m["author"]!!)
                            put("body", m["body"] ?: JsonPrimitive("")); put("kind", m["kind"] ?: JsonPrimitive("text")); put("created_at", m["created_at"]!!); put("rank", 1.0)
                        }
                    }
                }.sortedByDescending { it.str("created_at") }
                return 200 to page(hits.take(20))
            }
            "/ops/sites" -> return 200 to JsonArray(list("/ops/sites").filter { has(it.jsonObject, "company", q["company"]) })
            "/ops/incidents" -> return 200 to JsonArray(list("/ops/incidents").map { it.jsonObject }.filter { i ->
                has(i, "company", q["company"]) && (q["open"] == null || (q["open"] == "true") == (i["closed_at"] == null || i["closed_at"] is JsonNull))
            })
            "/treasury/calls" -> {
                val all = list("/treasury/calls").map { it.jsonObject }.filter { has(it, "company", q["company"]) && has(it, "actor", q["actor"]) && has(it, "status", q["status"]) }
                val at = q["cursor"]?.toIntOrNull() ?: 0
                val n = q["limit"]?.toIntOrNull() ?: 25
                return 200 to buildJsonObject { put("items", JsonArray(all.drop(at).take(n))); put("next_cursor", if (at + n < all.size) JsonPrimitive("${at + n}") else JsonNull) }
            }
            "/planner" -> {
                // A view over work (§4): the wide fixture cut to [from, to] and to the scope's company or department.
                val scope = q["scope"] ?: "owner"
                val (kind, ref) = if (':' in scope) scope.substringBefore(':') to scope.substringAfter(':') else "owner" to ""
                val from = q["from"]; val to = q["to"]
                val days = (store["/planner"]!!.second.jsonObject["days"]!!.jsonArray).map { it.jsonObject }
                    .filter { d -> (from == null || d.str("date")!! >= from) && (to == null || d.str("date")!! <= to) }
                    .map { d -> JsonObject(d + ("items" to JsonArray(d["items"]!!.jsonArray.filter { it ->
                        val i = it.jsonObject
                        when (kind) { "company" -> i.str("company") == ref; "department" -> "${i.str("company")}-${i.str("department")}" == ref; else -> true }
                    }))) }
                return 200 to buildJsonObject { put("scope", scope); put("timezone", "Asia/Tehran"); put("days", JsonArray(days)) }
            }
        }
        Regex("^/work/([^/]+)/runs$").find(path)?.let { m ->
            val id = m.groupValues[1]
            val ref = store["/work/$id"]?.second?.jsonObject?.str("ref") ?: list("/work").map { it.jsonObject }.firstOrNull { it.str("id") == id || it.str("ref") == id }?.str("ref")
            return 200 to JsonArray(store.filterKeys { it.matches(Regex("^/runs/run-\\d+$")) }.values.map { it.second.jsonObject }.filter { it.str("work_ref") == ref })
        }
        return null
    }

    private fun ownerToolsWrite(method: String, path: String, body: JsonObject?, version: Int?): Pair<Int, JsonElement>? {
        fun conflict() = 409 to buildJsonObject { put("code", "version_conflict"); put("message_fa", "این مورد جای دیگری عوض شده؛ دوباره باز کن."); put("status", 409); put("title", "version_conflict"); put("type", "about:blank") }
        when {
            method == "POST" && path == "/resolutions" -> {
                val r = buildJsonObject {
                    put("id", "r${System.nanoTime()}"); put("ref", "M-%04d".format(list("/resolutions").size + 4)); put("company", JsonNull)
                    put("title", body?.get("title") ?: JsonPrimitive("")); put("body", body?.get("body") ?: JsonPrimitive(""))
                    put("source", buildJsonObject { body?.str("source_message")?.let { put("message", it) } }); put("sealed_by", owner); put("sealed_at", stamp)
                    put("sent_to", JsonArray(emptyList())); put("follow_up_work_id", JsonNull)
                }
                prepend("/resolutions", r)
                return 201 to r
            }
            method == "PUT" && path == "/notification-settings" -> {
                val cur = store["/notification-settings"]!!.second.jsonObject
                val v = cur["version"]!!.jsonPrimitive.content.toInt()
                if (version != v) return conflict()
                return 200 to edit("/notification-settings") { mapOf("matrix" to (body?.get("matrix") ?: JsonObject(emptyMap())), "version" to JsonPrimitive(v + 1)) }
            }
            method == "POST" && path == "/control/deploy-freeze" -> {
                val co = body?.str("company") ?: return 422 to problem("validation_failed", "شرکت لازم است.")
                val until = body.str("until")!!
                val active = Instant.parse(until).isAfter(HqClock.now())
                edit("/control/state") { c ->
                    val rest = c["deploy_freezes"]!!.jsonArray.filter { it.jsonObject.str("company") != co }
                    c + ("deploy_freezes" to JsonArray(if (active) rest + buildJsonObject { put("company", co); put("until", until); put("reason", body["reason"] ?: JsonPrimitive("")); put("created_by", "owner") } else rest))
                }
                return 200 to buildJsonObject { put("company", co); put("active", active); put("until", until) }
            }
            method == "PUT" && path == "/budgets" -> {
                val rows = body?.get("budgets")?.jsonArray.orEmpty().map { it.jsonObject }
                store["/budgets"] = 200 to JsonArray(list("/budgets").map { b ->
                    val o = b.jsonObject
                    val hit = rows.firstOrNull { it.str("company") == o.str("company") && it.str("scope_type") == o.str("scope_type") && it.str("period") == o.str("period") }
                    if (hit == null) o else JsonObject(o + mapOf("token_limit" to (hit["token_limit"] ?: JsonNull), "usd_limit" to (hit["usd_limit"] ?: JsonNull)))
                })
                hiring(path, body)
                return 200 to JsonArray(list("/budgets"))
            }
        }
        Regex("^/work/([^/]+)(/cancel|/complete)?$").find(path)?.let { m ->
            if (method == "GET") return null
            val id = m.groupValues[1]
            val key = "/work/$id"
            val w = store[key]?.second?.jsonObject ?: return 404 to problem("not_found", "این کار پیدا نشد.")
            val v = w["version"]?.jsonPrimitive?.content?.toIntOrNull() ?: 1
            val change: Map<String, JsonElement> = when (m.groupValues[2]) {
                "/cancel" -> mapOf("status" to JsonPrimitive("cancelled"))
                "/complete" -> mapOf("status" to JsonPrimitive("done"), "progress_pct" to JsonPrimitive(100))
                else -> { if (version != v) return conflict(); body ?: JsonObject(emptyMap()) }
            }
            if (m.groupValues[2].isNotEmpty() && w.str("status") in setOf("done", "cancelled", "failed")) return 409 to problem("validation_failed", "این کار بسته است.")
            val next = JsonObject(w + change + mapOf("version" to JsonPrimitive(v + 1), "updated_at" to stamp))
            store[key] = 200 to next
            update("/work", w.str("ref")!!) { it + change }
            return 200 to next
        }
        Regex("^/employees/([A-Z0-9-]+)/(pause|resume|dismiss)$").find(path)?.let { m ->
            val (code, verb) = m.destructured
            val e = store["/employees/$code"]?.second?.jsonObject ?: return 404 to problem("not_found", "این کارمند پیدا نشد.")
            val status = mapOf("pause" to "paused", "resume" to "active", "dismiss" to "dismissed").getValue(verb)
            val next = JsonObject(e + ("status" to JsonPrimitive(status)) + (if (verb == "dismiss") mapOf("dismissed_at" to stamp, "activity" to JsonPrimitive("sleeping")) else emptyMap()))
            store["/employees/$code"] = 200 to next
            if (verb != "dismiss") return 200 to next
            val open = list("/work").count { it.jsonObject["assignee"]?.let { a -> (a as? JsonObject)?.str("code") } == code && it.jsonObject.str("status") !in setOf("done", "cancelled", "failed", "delivered") }
            return 200 to buildJsonObject { put("employee", next); put("work_returned", open); put("transfer_work", "W-0002%02d".format(list("/work").size)) }
        }
        Regex("^/connections/([^/]+)(/secret)?$").find(path)?.let { m ->
            val id = m.groupValues[1]
            val c = list("/connections").map { it.jsonObject }.firstOrNull { it.str("id") == id } ?: return 404 to problem("not_found", "این اتصال پیدا نشد.")
            if (m.groupValues[2].isNotEmpty()) {
                update("/connections", id, idKey = "id") { it + ("has_secret_ref" to JsonPrimitive(true)) }
                return 200 to buildJsonObject { put("connection", c.str("key")); put("stored", true) }
            }
            val v = c["version"]?.jsonPrimitive?.content?.toIntOrNull() ?: 1
            if (version != v) return conflict()
            return 200 to update("/connections", id, idKey = "id") { it + (body ?: JsonObject(emptyMap())) + ("version" to JsonPrimitive(v + 1)) }!!
        }
        if (method == "PUT" && path == "/ops/sites") {
            val co = body?.str("company") ?: return 422 to problem("validation_failed", "شرکت لازم است.")
            val rows = body["sites"]!!.jsonArray.map { it.jsonObject }
            if (rows.any { r -> listOf("localhost", "127.", "10.", "192.168.").any { r.str("url").orEmpty().contains(it) } }) return 422 to problem("validation_failed", "نشانی داخلی یا خصوصی پایش نمیشود.")
            val urls = rows.mapNotNull { it.str("url") }.toSet()
            val kept = list("/ops/sites").map { it.jsonObject }.map { x ->
                if (x.str("company") != co || x["canary"]?.jsonPrimitive?.content == "true") x
                else rows.firstOrNull { it.str("url") == x.str("url") }?.let { JsonObject(x + it) } ?: JsonObject(x + ("enabled" to JsonPrimitive(false)))
            }
            val added = rows.filter { r -> kept.none { it.str("company") == co && it.str("url") == r.str("url") } }.map { r ->
                JsonObject(r + mapOf("id" to JsonPrimitive("site-$co-${r.str("url")}"), "company" to JsonPrimitive(co), "canary" to JsonPrimitive(false), "consecutive_failures" to JsonPrimitive(0), "last" to JsonNull, "uptime_24h" to JsonNull, "version" to JsonPrimitive(1)))
            }
            store["/ops/sites"] = 200 to JsonArray(kept + added)
            return 200 to JsonArray((kept + added).filter { it.str("company") == co && (it.str("url") in urls || it["canary"]?.jsonPrimitive?.content == "true") })
        }
        if (method == "POST" && path == "/companies") {
            val code = body?.str("code") ?: return 422 to problem("validation_failed", "کد لازم است.")
            if (list("/companies").any { it.jsonObject.str("code") == code }) return 409 to problem("conflict", "این کد قبلاً گرفته شده.")
            val c = buildJsonObject {
                put("id", "co-$code"); put("code", code); put("kind", "company"); put("name_fa", body["name_fa"]!!); put("name_en", body["name_en"]!!); put("color_index", 4)
                put("status", "active"); put("template", "standard"); put("kill_switch", "released"); put("deploy_freeze_until", JsonNull); put("version", 1); put("created_at", stamp)
                put("counts", buildJsonObject { put("decisions_pending", 0); put("employees_active", 0); put("work_open", 0) })
            }
            store["/companies"] = 200 to JsonArray(list("/companies") + c)
            store["/companies/$code"] = 200 to c
            return 201 to c
        }
        return null
    }

    // ---------------------------------------------------------------- ⟨1.4.2⟩ --
    /** Hiring starts with the owner (contract §18.11): open to the CEOs' proposals, close, or hire directly. */
    private fun hiring(path: String, body: JsonObject?): Pair<Int, JsonElement>? {
        val system = buildJsonObject { put("kind", "system"); put("code", "system"); put("display_fa", "سیستم") }
        when (path) {
            "/owner/hiring/start" -> {
                val mode = body?.str("mode") ?: "proposals"
                val missing = store["/owner/hiring"]?.second?.jsonObject?.get("envelopes")?.jsonArray.orEmpty()
                    .map { it.jsonObject }.filter { it["tokens_month"] == null || it["tokens_month"] is JsonNull }.mapNotNull { it.str("company") }
                if (mode == "delegated" && missing.isNotEmpty()) {
                    return 422 to buildJsonObject {
                        put("code", "envelope_required"); put("message_fa", "برای ${missing.joinToString("، ")} پاکت ماهانه تعیین نشده است."); put("status", 422)
                        put("title", "envelope_required"); put("type", "about:blank")
                    }
                }
                return 200 to edit("/owner/hiring") {
                    it + mapOf("state" to JsonPrimitive("open"), "mode" to JsonPrimitive(mode), "changed_at" to stamp, "changed_by" to owner)
                }
            }
            "/budgets" -> {
                // Company month budgets are the hiring envelopes (contract §9, §18.11).
                val set = body?.get("budgets")?.jsonArray.orEmpty().map { it.jsonObject }
                    .filter { it.str("scope_type") == "company" && it.str("period") == "month" }.associate { it.str("company")!! to (it["token_limit"] ?: JsonNull) }
                edit("/owner/hiring") { h ->
                    h + ("envelopes" to JsonArray(h["envelopes"]?.jsonArray.orEmpty().map { e ->
                        val co = e.jsonObject.str("company")
                        if (co != null && co in set) JsonObject(e.jsonObject + ("tokens_month" to set.getValue(co))) else e
                    }))
                }
                return 200 to JsonArray(emptyList())
            }
            "/stories/seen" -> {
                val refs = body?.get("refs")?.jsonArray.orEmpty().map { it.jsonPrimitive.content }.toSet()
                storyEdit { st -> if (st.str("ref") in refs) JsonObject(st + ("seen" to JsonPrimitive(true))) else st }
                return 200 to buildJsonObject { put("updated", refs.size) }
            }
            "/owner/hiring/close" -> {
                val withdrawn = mutableListOf<JsonElement>()
                for (d in list("/decisions?status=all").map { it.jsonObject }.filter { it.str("kind") == "hire" && it.str("status") == "pending" }) {
                    val ref = d.str("ref")!!
                    val u = JsonObject(d + mapOf("status" to JsonPrimitive("withdrawn"), "decided_at" to stamp, "decided_by" to system, "note" to JsonPrimitive("مالک: استخدام با شروع خود مالک")))
                    replaceIn("/decisions?status=all", ref, u)
                    store["/decisions/$ref"] = 200 to u
                    withdrawn += JsonPrimitive(ref)
                }
                store["/decisions?status=pending"] = 200 to page(list("/decisions?status=all").filter { it.jsonObject.str("status") == "pending" })
                bumpInbox()
                return 200 to edit("/owner/hiring") {
                    it + mapOf("state" to JsonPrimitive("closed"), "mode" to JsonNull, "changed_at" to stamp, "changed_by" to owner, "withdrawn" to JsonArray(it["withdrawn"]?.jsonArray.orEmpty() + withdrawn))
                }
            }
            "/org/hires" -> {
                val b = body ?: return 422 to problem("validation_failed", "بدنه خالی است.")
                val company = b.str("company").orEmpty()
                val department = b.str("department").orEmpty()
                val role = list("/roles").map { it.jsonObject }.firstOrNull { it.str("role") == b.str("role") }
                val kind = list("/companies").map { it.jsonObject }.firstOrNull { it.str("code") == company }?.str("kind")
                val fits = role != null && kind != null && role.str("kind") == "employee" &&
                    role.str("scope") == (if (kind == "holding") "holding" else "company") && (role.str("department") ?: department) == department
                if (!fits) return 422 to problem("validation_failed", "این نقش با این شرکت و دپارتمان نمیخواند.")
                val n = list("/employees").count { it.jsonObject.str("company") == company && it.jsonObject.str("department") == department && it.jsonObject.str("kind") == "employee" } + 1
                val ref = "D-%06d".format(list("/decisions?status=all").size + 30)
                val model = b.str("model") ?: role!!.str("model")!!
                val effort = b.str("effort") ?: role!!.str("effort")!!
                val emp = JsonObject(list("/employees").first { it.jsonObject.str("kind") == "employee" }.jsonObject + mapOf(
                    "id" to JsonPrimitive("e-$ref"), "code" to JsonPrimitive("$company-$department-%02d".format(n)), "company" to JsonPrimitive(company),
                    "department" to JsonPrimitive(department), "kind" to JsonPrimitive("employee"), "title_fa" to b["title_fa"]!!,
                    "title_en" to (b["title_en"] ?: role!!["title_en"]!!), "activity" to JsonPrimitive("idle"), "activity_at" to stamp, "activity_note" to JsonNull,
                    "hired_at" to stamp, "hired_by_decision" to JsonPrimitive(ref),
                    "model" to buildJsonObject { put("connection", "claude-max"); put("model", model); put("effort", effort) },
                    "score" to buildJsonObject { put("value", JsonNull); put("owner_avg", JsonNull); put("rank_in_department", JsonNull); put("trend", JsonArray(emptyList())) },
                ))
                val dec = JsonObject(list("/decisions?status=all").first().jsonObject + mapOf(
                    "id" to JsonPrimitive("d-$ref"), "ref" to JsonPrimitive(ref), "kind" to JsonPrimitive("hire"), "company" to JsonPrimitive(company),
                    "status" to JsonPrimitive("approved"), "title" to JsonPrimitive("استخدام ${b.str("title_fa")}"), "proposer" to owner, "created_at" to stamp,
                    "what" to JsonPrimitive("${b.str("title_fa")} (${role!!.str("title_en")}) در دپارتمان $department."),
                    "why" to (b["reason"] ?: JsonPrimitive("استخدام مستقیم مالک")), "payload" to JsonObject(b + mapOf("model" to JsonPrimitive(model), "effort" to JsonPrimitive(effort))),
                    "seal" to buildJsonObject { put("method", "passkey_uv"); put("sealed_at", stamp); put("step_up_id", "demo") },
                    "decided_at" to stamp, "decided_by" to owner, "note" to JsonNull, "resolution" to JsonPrimitive("M-0008"), "effect_status" to JsonPrimitive("applied"),
                    "thread" to JsonNull, "expires_at" to JsonNull,
                ))
                prepend("/employees", emp)
                if (store.containsKey("/employees?company=$company")) prepend("/employees?company=$company", emp)
                store["/employees/${emp.str("code")}"] = 200 to emp
                prepend("/decisions?status=all", dec)
                store["/decisions/$ref"] = 200 to dec
                addStory(buildJsonObject {
                    put("id", "st-$ref"); put("ref", "ST-%06d".format(200 + list("/decisions?status=all").size)); put("company", company); put("kind", "hire"); put("author", system)
                    put("title_fa", "${b.str("title_fa")} به تیم پیوست"); put("body_fa", b["reason"] ?: JsonPrimitive("استخدام مستقیم مالک"))
                    put("figures", JsonArray(listOf(
                        buildJsonObject { put("label_fa", "مدل"); put("value", modelLabel(model)) },
                        buildJsonObject { put("label_fa", "effort"); put("value", effort) },
                    )))
                    put("links", buildJsonObject { put("employee", emp.str("code")); put("decision", ref) })
                    put("media", JsonNull); put("created_at", stamp); put("expires_at", JsonPrimitive(HqClock.now().plusSeconds(86_400).toString())); put("seen", false); put("welcomed", false)
                })
                return 201 to buildJsonObject { put("employee", emp); put("decision", dec) }
            }
        }
        Regex("^/stories/(ST-\\d+)/welcome$").find(path)?.let { m ->
            var hit: JsonObject? = null
            storyEdit { st -> if (st.str("ref") == m.groupValues[1]) JsonObject(st + ("welcomed" to JsonPrimitive(true))).also { hit = it } else st }
            return hit?.let { 200 to it } ?: (404 to problem("not_found", "پیدا نشد."))
        }
        Regex("^/employees/([A-Z0-9-]+)/dismiss$").find(path)?.let { m ->
            val code = m.groupValues[1]
            val e = store["/employees/$code"]?.second?.jsonObject ?: return 404 to problem("not_found", "پیدا نشد.")
            val gone = JsonObject(e + mapOf("status" to JsonPrimitive("dismissed"), "dismissed_at" to stamp))
            store["/employees/$code"] = 200 to gone
            return 200 to buildJsonObject { put("employee", gone); put("work_returned", 0); put("transfer_work", JsonNull) }
        }
        return null
    }

    /** Rewrites every story in the rings (contract §18.12) and recounts each ring's unseen. */
    private fun storyEdit(f: (JsonObject) -> JsonObject) {
        val rings = list("/stories").map { r ->
            val items = r.jsonObject["items"]!!.jsonArray.map { f(it.jsonObject) }
            JsonObject(r.jsonObject + mapOf("items" to JsonArray(items), "unseen" to JsonPrimitive(items.count { it.jsonObject["seen"]?.jsonPrimitive?.content != "true" })))
        }
        store["/stories"] = 200 to JsonArray(rings)
    }

    private fun addStory(st: JsonObject) {
        val co = st.str("company")
        val rings = list("/stories").map { it.jsonObject }
        val hit = rings.any { it.str("company") == co }
        val next = if (hit) rings.map { r -> if (r.str("company") == co) JsonObject(r + mapOf("items" to JsonArray(r["items"]!!.jsonArray + st), "latest_at" to st["created_at"]!!)) else r }
        else listOf(buildJsonObject { put("company", co); put("unseen", 0); put("latest_at", st["created_at"]!!); put("items", JsonArray(listOf(st))) }) + rings
        store["/stories"] = 200 to JsonArray(next)
        storyEdit { it }
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

    private fun JsonObject.int(k: String): Int = (this[k] as? JsonPrimitive)?.intOrNull ?: 0

    // ------------------------------------------------------------------ ⟨1.5⟩ --
    // Revenue and support (contract §19), as the web's mock-v16.ts: the fixtures hold whole lists and every conversation with
    // its messages; the demo filters them, and every outbound text it "sends" goes through the same guard the hub runs (§19.6),
    // reduced to what a demo needs. Companies, channels and exchanges are data here too.
    private class Reply(val status: Int, val body: JsonElement, val headers: Map<String, String> = emptyMap())

    private val replies = mutableMapOf<String, Reply>()
    private val pulledAt = mutableMapOf<String, Long>()
    private var msgSeq = 100

    private fun problem16(status: Int, code: String, fa: String, extra: JsonObject = JsonObject(emptyMap())) =
        JsonObject(buildJsonObject { put("type", "about:blank"); put("title", code); put("status", status); put("code", code); put("message_fa", fa) } + extra)

    private fun JsonObject.at(k: String): Instant = runCatching { Instant.parse(str(k)) }.getOrDefault(Instant.EPOCH)

    private val conversationKey = Regex("^/support/conversations/SC-\\d+$")

    /** Every conversation with its messages (the fixtures hold each one whole). */
    private fun conversations(): List<JsonObject> = store.keys.filter { conversationKey.matches(it) }.map { store[it]!!.second.jsonObject }

    private fun convOut(c: JsonObject): JsonObject =
        JsonObject(c - "messages" + ("last_message_at" to (c["messages"]?.jsonArray?.lastOrNull()?.jsonObject?.get("at") ?: c["opened_at"] ?: JsonNull)))

    /** The teaching queue (§19.3): what waits for the owner, oldest first, with the agent's draft or refused message. */
    private fun queue(): List<JsonObject> = conversations().filter { it.str("state") == "waiting_owner" }.map { c ->
        val reason = (c["handoff"] as? JsonObject)?.str("reason")
        buildJsonObject {
            put("conversation", c["ref"]!!); put("company", c["company"]!!)
            put("kind", when (reason) { "blocked" -> "blocked"; "low_confidence" -> "low_confidence"; else -> "handoff" })
            put("since", (c["handoff"] as? JsonObject)?.get("at") ?: c["opened_at"]!!)
            put("draft", c["messages"]!!.jsonArray.map { it.jsonObject }.lastOrNull { it.str("author") == "agent" && it.str("status") in setOf("draft", "blocked") } ?: JsonNull)
        }
    }.sortedBy { it.at("since") }

    private fun channelOf(company: String?, kind: String?): JsonObject? = list("/support/channels").map { it.jsonObject }.firstOrNull { it.str("company") == company && it.str("kind") == kind }

    private fun saveChannel(next: JsonObject) {
        store["/support/channels"] = 200 to JsonArray(list("/support/channels").map { val o = it.jsonObject; if (o.str("company") == next.str("company") && o.str("kind") == next.str("kind")) next else o })
    }

    /** Replaces the [index]th item of a stored list (versions of one ref share it, so the position is the identity). */
    private fun replaceAt(key: String, index: Int, item: JsonObject) {
        val items = list(key).toMutableList()
        items[index] = item
        store[key] = 200 to JsonArray(items)
    }

    /** The next ref of a kind ("KB-0013"): one past the highest the list holds. */
    private fun nextRef(key: String, prefix: String, width: Int): String =
        prefix + "%0${width}d".format((list(key).mapNotNull { it.jsonObject.str("ref")?.substringAfter('-')?.toIntOrNull() }.maxOrNull() ?: 0) + 1)

    private fun tmplSealed(ref: String?): Boolean {
        val (r, v) = (ref ?: return false).split('@').let { it[0] to it.getOrNull(1) }
        return list("/growth/templates").map { it.jsonObject }.any { it.str("ref") == r && it["version"]?.jsonPrimitive?.content == v && it.str("status") == "sealed" }
    }

    private fun norm(u: String) = u.trim().replace(Regex("[.,،؛)»]+$"), "").replace(Regex("/+$"), "").lowercase()

    /** The outbound guard (§19.6), as far as the demo needs it: links must be exactly approved; no profit promise; never ask for a seed. */
    private fun guard(company: String, text: String): List<String> {
        val out = linkedSetOf<String>()
        val approved = list("/support/kb").map { it.jsonObject }
            .filter { it.str("company") == company && it.str("status") == "approved" && it.str("kind") in setOf("official_link", "referral") }
            .flatMap { a -> a["links"]?.jsonArray.orEmpty().mapNotNull { (it as? JsonObject)?.str("url")?.let(::norm) } }.toSet()
        for (m in Regex("https?://[^\\s«»\"']+", RegexOption.IGNORE_CASE).findAll(text)) if (norm(m.value) !in approved) out += "unknown_link"
        if (Regex("سود\\s*‌?تضمینی|guaranteed\\s+profit", RegexOption.IGNORE_CASE).containsMatchIn(text)) out += "profit_promise"
        if (Regex("\\bseed\\b", RegexOption.IGNORE_CASE).containsMatchIn(text)) out += "asks_secret"
        if (text.length > 2000) out += "too_long"
        return out.toList()
    }

    private fun v16Read(path: String, q: Map<String, String?>): Pair<Int, JsonElement>? {
        fun has(o: JsonObject, k: String) = q[k] == null || o.str(k) == q[k]
        val notFound = 404 to problem16(404, "not_found", "پیدا نشد.")
        return when (path) {
            "/revenue/summary" -> store["/revenue/summary?" + listOfNotNull(q["company"]?.let { "company=$it" }, "period=${q["period"] ?: "month"}").joinToString("&")] ?: notFound
            "/revenue/days" -> 200 to JsonArray(list("/revenue/days").map { it.jsonObject }.filter { d ->
                has(d, "company") && has(d, "account") && (q["from"] == null || d.str("day")!! >= q["from"]!!) && (q["to"] == null || d.str("day")!! <= q["to"]!!)
            }.takeLast(400))
            "/growth/funnel" -> store["/growth/funnel?company=${q["company"]}&period=${if (q["period"] == "week") "week" else "month"}"] ?: notFound
            "/growth/rescue" -> 200 to page(list("/growth/rescue").map { it.jsonObject }.filter { has(it, "company") && has(it, "state") }.sortedByDescending { it.at("opened_at") })
            "/growth/templates", "/growth/rules", "/growth/nps", "/support/channels" -> 200 to JsonArray(list(path).filter { has(it.jsonObject, "company") })
            "/support/conversations" -> {
                val text = q["q"]?.trim().orEmpty()
                200 to page(conversations().filter { c ->
                    has(c, "company") && has(c, "state") && has(c, "channel") && (text.isEmpty() || listOf(
                        c.str("ref"), (c["customer"] as? JsonObject)?.str("display_name"), (c["customer"] as? JsonObject)?.str("handle_masked"),
                        c["tags"]?.jsonArray?.joinToString(" ") { it.jsonPrimitive.content }, c["messages"]?.jsonArray?.joinToString(" ") { it.jsonObject.str("body").orEmpty() },
                    ).joinToString(" ").contains(text))
                }.map(::convOut).sortedByDescending { it.at("last_message_at") })
            }
            "/support/queue" -> 200 to JsonArray(queue())
            "/support/kb" -> {
                val text = q["q"]?.trim().orEmpty()
                200 to JsonArray(list("/support/kb").map { it.jsonObject }.filter { a ->
                    has(a, "company") && has(a, "kind") && has(a, "status") && (text.isEmpty() || listOf(
                        a.str("ref"), a.str("question_fa"), a.str("answer_md"), a["variants"]?.jsonArray?.joinToString(" ") { it.jsonPrimitive.content }, a.str("key"),
                    ).joinToString(" ").contains(text))
                })
            }
            "/feedback" -> 200 to page(list("/feedback").map { it.jsonObject }.filter { has(it, "company") && has(it, "kind") && has(it, "state") }.sortedByDescending { it.int("count") })
            else -> null
        }
    }

    private fun v16Write(method: String, path: String, body: JsonObject?, version: Int?, idempotency: String?): Reply? {
        fun gone(fa: String = "پیدا نشد.") = Reply(404, problem16(404, "not_found", fa))
        fun conflict(fa: String) = Reply(409, problem16(409, "version_conflict", fa))
        // ---- revenue (§19.1)
        if (method == "POST" && path == "/revenue/accounts") {
            val b = body ?: return Reply(422, problem16(422, "validation_failed", "بدنه خالی است."))
            val all = list("/revenue/accounts").map { it.jsonObject }
            val i = all.indexOfFirst { it.str("company") == b.str("company") && it.str("exchange") == b.str("exchange") }
            if (i >= 0) {
                val next = JsonObject(all[i] + b + ("version" to JsonPrimitive(all[i].int("version") + 1)))
                replaceAt("/revenue/accounts", i, next)
                return Reply(200, next)
            }
            val n = JsonObject(buildJsonObject {
                put("id", "ra-${b.str("company").orEmpty().lowercase()}-${b.str("exchange")}"); put("status", "not_configured"); put("last_pull_at", JsonNull); put("last_error", JsonNull); put("version", 1)
            } + b)
            store["/revenue/accounts"] = 200 to JsonArray(list("/revenue/accounts") + n)
            return Reply(201, n)
        }
        Regex("^/revenue/accounts/([^/]+)/pull$").find(path)?.let { m ->
            val id = m.groupValues[1]
            val all = list("/revenue/accounts").map { it.jsonObject }
            val i = all.indexOfFirst { it.str("id") == id }.takeIf { it >= 0 } ?: return gone("این حساب پیدا نشد.")
            val a = all[i]
            if (a.str("status") == "not_configured") return Reply(409, problem16(409, "account_not_configured", "این حساب هنوز کلید ندارد؛ در ترمینال خودت make account-secret را بزن."))
            val last = pulledAt[id]
            val nowMs = System.currentTimeMillis()
            if (last != null && nowMs - last < 60_000) {
                val wait = ((60_000 - (nowMs - last)) / 1000 + 1).toString()
                return Reply(429, problem16(429, "rate_limited", "همین الان pull شد."), mapOf("Retry-After" to wait))
            }
            pulledAt[id] = nowMs
            if (a.str("status") == "ok") replaceAt("/revenue/accounts", i, JsonObject(a + ("last_pull_at" to stamp)))
            return Reply(202, buildJsonObject { put("account", id); put("state", "queued") })
        }
        // ---- support desk (§19.3)
        Regex("^/support/channels/([A-Z0-9]+)/([a-z_]+)(/pause)?$").find(path)?.let { m ->
            val (co, kind, pause) = m.destructured
            val ch = channelOf(co, kind) ?: return gone("این کانال پیدا نشد.")
            if (pause.isNotEmpty()) {
                val next = JsonObject(ch + mapOf("state" to JsonPrimitive("paused"), "paused_reason" to JsonPrimitive("مالک متوقف کرد."), "version" to JsonPrimitive(ch.int("version") + 1)))
                saveChannel(next)
                return Reply(200, next)
            }
            if (version == null) return Reply(428, problem16(428, "precondition_required", "نسخه‌ی کانال همراه درخواست نیامد."))
            if (version != ch.int("version")) return conflict("کانال همین حالا عوض شده؛ دوباره نگاه کن.")
            var next = ch
            if (body?.str("state") == "live" && ch.str("state") != "live") {
                if (ch["live_since"] == null || ch["live_since"] is JsonNull) return Reply(409, problem16(409, "shadow_not_passed", "این کانال هرگز go-live نگرفته است."))
                next = JsonObject(next + mapOf("state" to JsonPrimitive("live"), "paused_reason" to JsonNull))
            }
            body?.str("auto_send")?.let { next = JsonObject(next + ("auto_send" to JsonPrimitive(it))) }
            next = JsonObject(next + ("version" to JsonPrimitive(ch.int("version") + 1)))
            saveChannel(next)
            return Reply(200, next)
        }
        Regex("^/support/conversations/(SC-\\d+)/(reply|teach|close)$").find(path)?.let { m ->
            val (ref, verb) = m.destructured
            val key = "/support/conversations/$ref"
            val c = store[key]?.second?.jsonObject ?: return gone("این گفت‌وگو پیدا نشد.")
            if (verb == "close") {
                val next = JsonObject(c + ("state" to JsonPrimitive("closed")))
                store[key] = 200 to next
                return Reply(200, convOut(next))
            }
            val idem = idempotency.orEmpty()
            replies[idem]?.let { return it }
            val text = (if (verb == "reply") body?.str("body") else body?.str("answer_md"))?.trim().orEmpty()
            if (text.isEmpty()) return Reply(422, problem16(422, "validation_failed", "متن خالی است."))
            val company = c.str("company").orEmpty()
            val reasons = guard(company, text)
            if (reasons.isNotEmpty()) return Reply(422, problem16(422, "send_blocked", "نگهبان خروجی این پیام را رد کرد.", buildJsonObject { putJsonArray("blocked_reasons") { reasons.forEach { add(JsonPrimitive(it)) } } }))
            val live = channelOf(company, c.str("channel"))?.str("state") == "live"
            if (verb == "reply" && !live) return Reply(409, problem16(409, "channel_not_live", "این کانال روشن نیست."))
            val send = verb == "reply" || (c.str("state") == "waiting_owner" && live)
            val messages = c["messages"]?.jsonArray.orEmpty()
            val out = if (send) buildJsonObject {
                put("id", "$ref-m${++msgSeq}"); put("conversation", ref); put("at", stamp); put("direction", "out"); put("author", "owner"); put("body", text); put("status", "sent")
                putJsonArray("kb_refs") {}; put("confidence", JsonNull); putJsonObject("checks") { put("guard", "pass"); put("grounded", JsonNull) }; putJsonArray("blocked_reasons") {}
            } else null
            val conv = if (out != null) JsonObject(c + mapOf("messages" to JsonArray(messages + out), "state" to JsonPrimitive("answered"), "last_message_at" to stamp)).also { store[key] = 200 to it } else c
            var result: JsonElement = out ?: JsonNull
            if (verb == "teach") {
                val asked = conv["messages"]!!.jsonArray.map { it.jsonObject }.lastOrNull { it.str("direction") == "in" }?.str("body").orEmpty()
                val generalise = (body?.get("generalise") as? JsonPrimitive)?.booleanOrNull == true
                val article = buildJsonObject {
                    val r = nextRef("/support/kb", "KB-", 4)
                    put("id", "kb-$r"); put("ref", r); put("company", company); put("version", 1); put("kind", "faq"); put("key", JsonNull)
                    put("question_fa", (if (generalise) asked.replace(Regex("[@#]\\S+|\\d{4,}"), "…") else asked).take(140))
                    putJsonArray("variants") {}; put("answer_md", text); putJsonArray("variables") {}; putJsonArray("links") {}; putJsonArray("codes") {}
                    put("status", "proposed"); putJsonObject("source") { put("kind", "owner_answer"); put("ref", ref) }; put("approved_at", JsonNull)
                    put("expires_at", HqClock.now().plus(180, ChronoUnit.DAYS).toString()); put("uses_30d", 0); put("sha256", Api.sha256(text))
                }
                prepend("/support/kb", article)
                result = buildJsonObject { put("message", out ?: JsonNull); put("article", article) }
            }
            return Reply(201, result).also { if (idem.isNotEmpty()) replies[idem] = it }
        }
        // ---- knowledge and the shadow test (§19.4)
        if (method == "POST" && path == "/support/kb") {
            val b = body ?: return Reply(422, problem16(422, "validation_failed", "بدنه خالی است."))
            val prev = b.str("ref")?.let { r -> list("/support/kb").map { it.jsonObject }.firstOrNull { it.str("ref") == r } }
            val ref = prev?.str("ref") ?: nextRef("/support/kb", "KB-", 4)
            val a = JsonObject(buildJsonObject {
                put("id", "kb-$ref-${(prev?.int("version") ?: 0) + 1}"); put("ref", ref); put("version", (prev?.int("version") ?: 0) + 1); put("key", JsonNull)
                putJsonArray("variants") {}; putJsonArray("variables") {}; putJsonArray("links") {}; putJsonArray("codes") {}
            } + b + buildJsonObject {
                put("ref", ref); put("status", "proposed"); putJsonObject("source") { put("kind", "owner"); put("ref", JsonNull) }; put("approved_at", JsonNull)
                put("expires_at", HqClock.now().plus(180, ChronoUnit.DAYS).toString()); put("uses_30d", 0); put("sha256", Api.sha256(b.str("answer_md").orEmpty()))
            })
            prepend("/support/kb", a)
            return Reply(201, a)
        }
        Regex("^/support/kb/(KB-\\d+)/(approve|retire)$").find(path)?.let { m ->
            val (ref, verb) = m.destructured
            val all = list("/support/kb").map { it.jsonObject }
            val i = all.indexOfFirst { it.str("ref") == ref && (if (verb == "approve") it.str("status") == "proposed" else it.str("status") != "retired") }
            if (i < 0) return Reply(409, problem16(409, "validation_failed", if (verb == "approve") "این مقاله منتظر تأیید نیست." else "این مقاله قبلاً بازنشسته شده."))
            val next = if (verb == "approve") JsonObject(all[i] + mapOf("status" to JsonPrimitive("approved"), "approved_at" to stamp, "expires_at" to JsonPrimitive(HqClock.now().plus(180, ChronoUnit.DAYS).toString())))
            else JsonObject(all[i] + ("status" to JsonPrimitive("retired")))
            // An approved version retires the version it replaces.
            store["/support/kb"] = 200 to JsonArray(all.mapIndexed { j, a ->
                when {
                    j == i -> next
                    verb == "approve" && a.str("ref") == ref && a.str("status") == "approved" -> JsonObject(a + ("status" to JsonPrimitive("retired")))
                    else -> a
                }
            })
            return Reply(200, next)
        }
        if (method == "POST" && path == "/support/history") {
            val co = body?.str("company") ?: return Reply(422, problem16(422, "validation_failed", "شرکت لازم است."))
            val r = list("/support/shadow").map { it.jsonObject }.firstOrNull { it.str("company") == co }
            val v = (r?.str("suite")?.substringAfter('@')?.toIntOrNull() ?: 0) + 1
            return Reply(201, buildJsonObject { put("suite", "support-shadow-$co@$v"); put("cases", 100) })
        }
        Regex("^/support/shadow/([A-Z0-9]+)/run$").find(path)?.let { m ->
            val co = m.groupValues[1]
            val all = list("/support/shadow").map { it.jsonObject }
            val i = all.indexOfFirst { it.str("company") == co }
            if (i < 0) return Reply(409, problem16(409, "validation_failed", "برای این شرکت هنوز تاریخچه‌ای داده نشده؛ اول خروجی گفت‌وگوها را بده."))
            val runId = "er-sh-${co.lowercase()}-${System.currentTimeMillis()}"
            replaceAt("/support/shadow", i, JsonObject(all[i] + mapOf("run_id" to JsonPrimitive(runId), "at" to stamp)))
            return Reply(202, buildJsonObject { put("run_id", runId) })
        }
        // ---- templates and lifecycle rules (§19.5)
        if (method == "POST" && path == "/growth/templates") {
            val b = body ?: return Reply(422, problem16(422, "validation_failed", "بدنه خالی است."))
            val prev = b.str("ref")?.let { r -> list("/growth/templates").map { it.jsonObject }.firstOrNull { it.str("ref") == r } }
            val ref = prev?.str("ref") ?: nextRef("/growth/templates", "TM-", 4)
            val version = (prev?.int("version") ?: 0) + 1
            val t = JsonObject(b + buildJsonObject {
                put("id", "tm-$ref-$version"); put("ref", ref); put("version", version); put("status", "proposed"); put("sealed_at", JsonNull); put("sha256", Api.sha256(b.str("body_fa").orEmpty()))
            })
            // A new template version rests the rules that send its older one until both are sealed (§19.5).
            if (prev != null) store["/growth/rules"] = 200 to JsonArray(list("/growth/rules").map { val r = it.jsonObject; if (r.str("template")?.startsWith("$ref@") == true && r.str("status") == "active") JsonObject(r + ("status" to JsonPrimitive("paused"))) else r })
            prepend("/growth/templates", t)
            return Reply(201, t)
        }
        Regex("^/growth/templates/(TM-\\d+)/seal$").find(path)?.let { m ->
            val all = list("/growth/templates").map { it.jsonObject }
            val i = all.indexOfFirst { it.str("ref") == m.groupValues[1] && it.str("status") == "proposed" }
            if (i < 0) return Reply(409, problem16(409, "validation_failed", "این قالب منتظر مُهر نیست."))
            val next = JsonObject(all[i] + mapOf("status" to JsonPrimitive("sealed"), "sealed_at" to stamp))
            replaceAt("/growth/templates", i, next)
            return Reply(200, next)
        }
        if (method == "POST" && path == "/growth/rules") {
            val b = body ?: return Reply(422, problem16(422, "validation_failed", "بدنه خالی است."))
            val prev = b.str("ref")?.let { r -> list("/growth/rules").map { it.jsonObject }.firstOrNull { it.str("ref") == r } }
            val ref = prev?.str("ref") ?: nextRef("/growth/rules", "LR-", 4)
            val version = (prev?.int("version") ?: 0) + 1
            val r = JsonObject(b + buildJsonObject {
                put("id", "lr-$ref-$version"); put("ref", ref); put("version", version); put("status", "proposed"); put("decision_ref", JsonNull); put("sent_30d", 0); put("opt_outs_30d", 0)
            })
            prepend("/growth/rules", r)
            return Reply(201, r)
        }
        Regex("^/growth/rules/(LR-\\d+)/(seal|pause|resume)$").find(path)?.let { m ->
            val (ref, verb) = m.destructured
            val all = list("/growth/rules").map { it.jsonObject }
            val i = all.indexOfFirst { it.str("ref") == ref }.takeIf { it >= 0 } ?: return gone("این قاعده پیدا نشد.")
            if (verb != "pause" && !tmplSealed(all[i].str("template"))) return Reply(409, problem16(409, "template_not_sealed", "قالب ${all[i].str("template")} هنوز مُهر نشده است."))
            val next = JsonObject(all[i] + ("status" to JsonPrimitive(if (verb == "pause") "paused" else "active")))
            replaceAt("/growth/rules", i, next)
            return Reply(200, next)
        }
        // ---- feedback (§19.7) and intake (§19.8)
        Regex("^/feedback/(FB-\\d+)$").find(path)?.let { m ->
            if (method != "PATCH") return null
            val all = list("/feedback").map { it.jsonObject }
            val i = all.indexOfFirst { it.str("ref") == m.groupValues[1] }.takeIf { it >= 0 } ?: return gone()
            if (version == null) return Reply(428, problem16(428, "precondition_required", "نسخه همراه درخواست نیامد."))
            if (version != all[i].int("version")) return conflict("این مورد همین حالا عوض شده؛ دوباره نگاه کن.")
            val next = JsonObject(all[i] + (body ?: JsonObject(emptyMap())) + ("version" to JsonPrimitive(all[i].int("version") + 1)))
            store["/feedback"] = 200 to page(all.mapIndexed { j, x -> if (j == i) next else x })
            return Reply(200, next)
        }
        if (method == "POST" && path == "/intake/sources") {
            val b = body ?: return Reply(422, problem16(422, "validation_failed", "بدنه خالی است."))
            val hit = list("/intake/sources").map { it.jsonObject }.firstOrNull { it.str("company") == b.str("company") && it.str("kind") == b.str("kind") }
            if (hit != null) return Reply(201, hit)
            val s = buildJsonObject {
                put("company", b["company"]!!); put("kind", b["kind"]!!); put("configured", false); put("last_event_at", JsonNull); put("events_24h", 0); put("rejected_24h", 0)
            }
            store["/intake/sources"] = 200 to JsonArray(list("/intake/sources") + s)
            return Reply(201, s)
        }
        return null
    }

    /** What sealing a §19.9 card does in the demo: the channel goes live, the template is sealed, the rule runs if its template is. */
    private fun decided16(d: JsonObject) {
        val p = d["payload"] as? JsonObject ?: return
        when (d.str("kind")) {
            "support_go_live" -> channelOf(p.str("company"), p.str("channel"))?.let { c ->
                saveChannel(JsonObject(c + mapOf("state" to JsonPrimitive("live"), "live_since" to stamp, "auto_send" to (p["auto_send"] ?: JsonPrimitive("kb_verbatim")), "version" to JsonPrimitive(c.int("version") + 1))))
            }
            "message_template" -> (p["template"] as? JsonObject)?.let { t ->
                val all = list("/growth/templates").map { it.jsonObject }
                val i = all.indexOfFirst { it.str("ref") == t.str("ref") && it.int("version") == t.int("version") }
                if (i >= 0) replaceAt("/growth/templates", i, JsonObject(all[i] + mapOf("status" to JsonPrimitive("sealed"), "sealed_at" to stamp)))
            }
            "lifecycle_rule" -> (p["rule"] as? JsonObject)?.let { r ->
                val all = list("/growth/rules").map { it.jsonObject }
                val i = all.indexOfFirst { it.str("ref") == r.str("ref") }
                if (i >= 0 && tmplSealed(all[i].str("template"))) replaceAt("/growth/rules", i, JsonObject(all[i] + ("status" to JsonPrimitive("active"))))
            }
        }
    }

    // ------------------------------------------------------------------ ⟨1.5⟩ §20 --
    // Governance (contract §20), as the web's mock-v17.ts: the fixtures hold whole lists (meetings with their turns, every charter
    // version, knowledge with the expired and the support view, OKRs, outcomes, risks, the calendar, the authority matrix); the demo
    // filters them and answers every write the mock answers. Rules the hub runs as code (the budget estimate, claim checks, conflict
    // rules, the batch eligibility) are reduced to what a demo needs. Companies are data here too.
    private val meetingScripts = mutableMapOf<String, MutableList<JsonObject>>().apply {
        for ((k, v) in store) if (k.startsWith("#script:MT-")) put(k.removePrefix("#script:"), v.second.jsonObject["items"]!!.jsonArray.map { it.jsonObject }.toMutableList())
    }
    /** The live meeting reveals its next turn only after a pause, like the web's mock (one per poll, ≥ 8 s apart). */
    private var lastReveal = System.currentTimeMillis()
    private var turnSeq = 200
    private var resolutionSeq = 20
    private var batchSeq = 1
    private val inspector = buildJsonObject { put("kind", "agent"); put("code", "HQ-OVS-MGR"); put("display_fa", "بازرس کل") }

    private fun operating(): List<JsonObject> = list("/companies").map { it.jsonObject }.filter { it.str("kind") != "holding" }
    private fun nameOf(code: String?): String = list("/companies").map { it.jsonObject }.firstOrNull { it.str("code") == code }?.str("name_fa") ?: code.orEmpty()
    private fun agent(code: String, fa: String) = buildJsonObject { put("kind", "agent"); put("code", code); put("display_fa", fa) }
    private fun ceo(c: String) = agent("$c-CEO", "مدیرعامل ${nameOf(c)}")
    private fun tech(c: String) = agent("$c-TECH-MGR", "مدیر فنی ${nameOf(c)}")
    private fun JsonObject.long(k: String): Long = (this[k] as? JsonPrimitive)?.content?.toDoubleOrNull()?.toLong() ?: 0L
    private fun JsonObject.obj(k: String): JsonObject = this[k] as? JsonObject ?: JsonObject(emptyMap())
    private fun JsonObject.arr(k: String): List<JsonObject> = (this[k] as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()
    private fun ms(iso: String?): Long = iso?.let { runCatching { Instant.parse(it).toEpochMilli() }.getOrNull() } ?: 0L
    private fun ahead(minutes: Long): JsonPrimitive = JsonPrimitive(HqClock.now().plus(minutes, ChronoUnit.MINUTES).toString())
    private fun pad(prefix: String, n: Int, w: Int) = prefix + "%0${w}d".format(n)
    private fun bad(fa: String) = Reply(422, problem16(422, "validation_failed", fa))
    private fun stepUpMissing() = Reply(403, problem16(403, "step_up_required", "این کار تأیید با اثر انگشت یا چهره میخواهد."))
    private fun unmatched(version: Int?, current: Int): Reply? = when {
        version == null -> Reply(428, problem16(428, "precondition_required", "نسخه همراه درخواست نیامد."))
        version != current -> Reply(409, problem16(409, "version_conflict", "همین حالا عوض شده؛ دوباره نگاه کن."))
        else -> null
    }

    // ---- meetings (§20.1)
    private fun meetingList(): List<JsonObject> = list("/meetings").map { it.jsonObject }
    private fun meetingOf(ref: String): JsonObject? = meetingList().firstOrNull { it.str("ref") == ref }
    private fun saveMeeting(m: JsonObject) {
        val all = meetingList()
        store["/meetings"] = 200 to page(if (all.any { it.str("ref") == m.str("ref") }) all.map { if (it.str("ref") == m.str("ref")) m else it } else all + m)
    }
    private fun turnsOf(ref: String): List<JsonObject> = store["/meetings/$ref/turns"]?.second?.jsonObject?.arr("items").orEmpty()
    private fun saveTurns(ref: String, items: List<JsonObject>) {
        val cur = store["/meetings/$ref/turns"]?.second?.jsonObject ?: buildJsonObject { putJsonArray("whispers") {}; put("next_cursor", JsonNull) }
        store["/meetings/$ref/turns"] = 200 to JsonObject(cur + ("items" to JsonArray(items)))
    }
    private fun items(m: JsonObject) = m.arr("items")
    private fun currentItem(m: JsonObject): JsonObject? = items(m).sortedBy { it.int("n") }.firstOrNull { it.str("state") == "round_1" || it.str("state") == "round_2" }
    private fun withItems(m: JsonObject, xs: List<JsonObject>) = JsonObject(m + ("items" to JsonArray(xs)))
    private fun mapItem(m: JsonObject, id: String?, f: (JsonObject) -> JsonObject) = withItems(m, items(m).map { if (it.str("id") == id) f(it) else it })
    private fun bumped(m: JsonObject) = JsonObject(m + ("version" to JsonPrimitive(m.int("version") + 1)))

    /** A turn said now: numbered, stamped, its tokens on the meeting's budget, a challenge marks the claim, a vote counts on the draft. */
    private fun addTurn(m0: JsonObject, t: JsonObject): JsonObject {
        var m = m0
        val ref = m.str("ref")!!
        val it = t.str("item")?.let { id -> items(m).firstOrNull { x -> x.str("id") == id } } ?: currentItem(m)
        val turns = turnsOf(ref)
        val out = buildJsonObject {
            put("id", "$ref-t${++turnSeq}"); put("meeting", ref); put("item", it?.str("id")?.let { s -> JsonPrimitive(s) } ?: JsonNull); put("n", turns.size + 1)
            put("round", it?.int("round")?.takeIf { r -> r > 0 } ?: 1); put("speaker", t["speaker"]!!); put("kind", t["kind"] ?: JsonPrimitive("statement"))
            put("statement_md", t["statement_md"] ?: JsonPrimitive("")); put("claims", t["claims"] ?: JsonArray(emptyList())); put("draft_md", t["draft_md"] ?: JsonNull)
            put("stance", t["stance"] ?: JsonNull); put("run_id", if (t.str("kind") == "owner") JsonNull else JsonPrimitive("run-$turnSeq")); put("tokens", t.long("tokens")); put("at", stamp)
        }
        var all = turns + out
        t.str("challenge")?.let { cid ->
            all = all.map { x -> JsonObject(x + ("claims" to JsonArray(x.arr("claims").map { c -> if (c.str("id") == cid && c.str("status") == "unsourced") JsonObject(c + ("status" to JsonPrimitive("challenged"))) else c }))) }
        }
        saveTurns(ref, all)
        (t["stance"] as? JsonObject)?.let { st ->
            m = JsonObject(m + ("drafts" to JsonArray(m.arr("drafts").map { d ->
                if (d.str("id") != st.str("draft")) d else {
                    val v = d.obj("votes"); val k = st.str("vote") ?: "abstain"
                    JsonObject(d + ("votes" to JsonObject(v + (k to JsonPrimitive(v.int(k) + 1)))))
                }
            })))
        }
        val b = m.obj("budget")
        m = JsonObject(m + ("budget" to JsonObject(b + ("used" to JsonPrimitive(b.long("used") + out.long("tokens"))))))
        return bumped(m)
    }

    private fun nextItem(m: JsonObject): JsonObject {
        val nx = items(m).sortedBy { it.int("n") }.firstOrNull { it.str("state") == "waiting" } ?: return m
        return mapItem(m, nx.str("id")) { JsonObject(it + mapOf("state" to JsonPrimitive("round_1"), "round" to JsonPrimitive(1))) }
    }

    /** Closing: the minutes from sourced claims only, and each draft a `meeting_resolution` card for the owner's seal. */
    private fun endMeeting(m0: JsonObject): JsonObject {
        val ref = m0.str("ref")!!
        var m = withItems(m0, items(m0).map { x ->
            when (x.str("state")) { "round_1", "round_2" -> JsonObject(x + ("state" to JsonPrimitive("done"))); "waiting" -> JsonObject(x + ("state" to JsonPrimitive("skipped"))); else -> x }
        })
        val turns = turnsOf(ref)
        val sourced = turns.flatMap { t -> t.arr("claims").filter { it.str("status") == "sourced" }.map { c -> "- ${c.str("text_fa")} (${c.obj("source").str("ref")})" } }
        val done = items(m).count { it.str("state") == "done" }
        val deliverable = "O-0000${33 + (meetingList().count { it["minutes"] is JsonObject })}"
        m = JsonObject(m + ("minutes" to buildJsonObject {
            put("deliverable", deliverable)
            put("summary_md", "**$done دستور بررسی شد.** فقط ادعاهای منبع‌دار:\n\n" + (sourced.take(6).joinToString("\n").ifEmpty { "- ادعای منبع‌داری ثبت نشد." }))
        }))
        val drafts = m.arr("drafts").map { d ->
            if (d["decision"] is JsonPrimitive) return@map d
            val dref = nextDecisionRef()
            val title = d.str("text_md").orEmpty().replace(Regex("[؛.].*$", RegexOption.DOT_MATCHES_ALL), "").take(80)
            val itemTitle = items(m).firstOrNull { it.str("id") == d.str("item") }?.str("title_fa").orEmpty()
            addDecision(buildJsonObject {
                put("id", "d-$dref"); put("ref", dref); put("kind", "meeting_resolution"); put("company", m["company"]!!); put("risk", "low"); put("title", title)
                put("proposer", d["proposer"] ?: inspector); put("created_at", stamp); put("expires_at", ahead(60L * 24 * 5))
                put("what", d["text_md"] ?: JsonPrimitive("")); put("why", "پیش‌نویس دستور «$itemTitle» در $ref؛ فقط ادعاهای منبع‌دار همراه کارت است."); put("risk_note", JsonNull)
                putJsonObject("quota_estimate") { put("tokens", 8000); put("usd", "0.15") }
                putJsonObject("payload") {
                    put("meeting", ref); put("item", d["item"] ?: JsonNull); put("text_md", d["text_md"] ?: JsonPrimitive("")); put("votes", d["votes"] ?: JsonObject(emptyMap()))
                    put("claims", JsonArray(turns.filter { it.str("item") == d.str("item") }.flatMap { t -> t.arr("claims").filter { it.str("status") == "sourced" } }))
                }
            })
            JsonObject(d + ("decision" to JsonPrimitive(dref)))
        }
        return JsonObject(m + mapOf("drafts" to JsonArray(drafts), "state" to JsonPrimitive("ended")))
    }

    private fun nextDecisionRef(): String = pad("D-", (list("/decisions?status=all").mapNotNull { it.jsonObject.str("ref")?.substringAfter('-')?.toIntOrNull() }.maxOrNull() ?: 0) + 1, 6)

    /** A new pending card, as the hub would write it (§5.1 defaults), in every list the cartable reads. */
    private fun addDecision(d: JsonObject) {
        val card = JsonObject(buildJsonObject {
            put("action_class", "A1"); put("reversible", true); put("status", "pending"); put("seal", JsonNull); put("decided_at", JsonNull); put("decided_by", JsonNull)
            put("note", JsonNull); put("resolution", JsonNull); put("thread", JsonNull); put("version", 1); put("effect_status", "none"); put("work_id", JsonNull)
            put("expected", JsonNull); putJsonArray("warnings") {}
        } + d)
        store["/decisions/${card.str("ref")}"] = 200 to card
        store["/decisions?status=all"] = 200 to page(listOf<JsonElement>(card) + list("/decisions?status=all"))
        store["/decisions?status=pending"] = 200 to page(list("/decisions?status=all").filter { it.jsonObject.str("status") == "pending" })
        bumpInbox()
    }

    // ---- charter (§20.2)
    private fun charterAll(): List<JsonObject> = store.keys.filter { Regex("^/charter/[^/]+/versions/\\d+$").matches(it) }.map { store[it]!!.second.jsonObject }
    private fun saveCharters(all: List<JsonObject>) {
        for (c in all) store["/charter/${c.str("scope")}/versions/${c.int("version")}"] = 200 to c
        val scopes = all.map { it.str("scope")!! }.distinct().sortedWith(compareBy<String> { if (it == "holding") 0 else 1 }.thenBy { it })
        store["/charter"] = 200 to JsonArray(scopes.map { scope ->
            val vs = all.filter { it.str("scope") == scope }.sortedByDescending { it.int("version") }
            store["/charter/$scope/versions"] = 200 to JsonArray(vs)
            buildJsonObject {
                put("scope", scope); put("sealed", vs.firstOrNull { it.str("status") == "sealed" } ?: JsonNull); put("proposed", vs.firstOrNull { it.str("status") == "proposed" } ?: JsonNull)
                put("versions", JsonArray(vs.map { v -> buildJsonObject { for (k in listOf("version", "status", "created_by", "created_at", "sealed_at")) put(k, v[k] ?: JsonNull) } }))
            }
        })
    }
    /** Canonical JSON: keys sorted at every depth, no spaces (the hub's `body_sha256`). */
    private fun canonical(e: JsonElement): String = when (e) {
        is JsonObject -> e.keys.sorted().joinToString(",", "{", "}") { k -> JsonPrimitive(k).toString() + ":" + canonical(e[k]!!) }
        is JsonArray -> e.joinToString(",", "[", "]") { canonical(it) }
        else -> e.toString()
    }
    private fun charterText(c: JsonObject): String = c.str("body_md").orEmpty() + "\n\n## خطوط قرمز\n" + c.arr("red_lines").joinToString("\n") { r ->
        val n = (r["patterns"] as? JsonArray)?.size ?: 0
        "- [${r.str("check")}] ${r.str("key")}: ${r.str("text_fa")}" + if (n > 0) " ($n الگو)" else ""
    }
    /** A unified diff of two texts, three lines of context, computed like the hub's difflib (line by line). */
    private fun unified(a: String, b: String, la: String, lb: String): String {
        val x = a.split('\n'); val y = b.split('\n'); val n = x.size; val m = y.size
        val dp = Array(n + 1) { IntArray(m + 1) }
        for (i in n - 1 downTo 0) for (j in m - 1 downTo 0) dp[i][j] = if (x[i] == y[j]) dp[i + 1][j + 1] + 1 else maxOf(dp[i + 1][j], dp[i][j + 1])
        data class Op(val s: Char, val t: String, val i: Int, val j: Int)
        val ops = mutableListOf<Op>()
        var i = 0; var j = 0
        while (i < n || j < m) {
            if (i < n && j < m && x[i] == y[j]) { ops += Op(' ', x[i], i, j); i++; j++ }
            else if (j < m && (i >= n || dp[i][j + 1] >= dp[i + 1][j])) { ops += Op('+', y[j], i, j); j++ }
            else { ops += Op('-', x[i], i, j); i++ }
        }
        val out = mutableListOf("--- $la", "+++ $lb")
        val changed = ops.indices.filter { ops[it].s != ' ' }
        var k = 0
        while (k < changed.size) {
            val start = maxOf(0, changed[k] - 3)
            var end = minOf(ops.size - 1, changed[k] + 3)
            while (k + 1 < changed.size && changed[k + 1] - 3 <= end + 1) { k++; end = minOf(ops.size - 1, changed[k] + 3) }
            val seg = ops.subList(start, end + 1)
            out += "@@ -${seg[0].i + 1},${seg.count { it.s != '+' }} +${seg[0].j + 1},${seg.count { it.s != '-' }} @@"
            out += seg.map { "${it.s}${it.t}" }
            k++
        }
        return out.joinToString("\n")
    }

    // ---- calendar (§20.9)
    private val TEHRAN = java.time.ZoneOffset.ofHoursMinutes(3, 30)
    private val WD = mapOf(java.time.DayOfWeek.SUNDAY to "SU", java.time.DayOfWeek.MONDAY to "MO", java.time.DayOfWeek.TUESDAY to "TU", java.time.DayOfWeek.WEDNESDAY to "WE",
        java.time.DayOfWeek.THURSDAY to "TH", java.time.DayOfWeek.FRIDAY to "FR", java.time.DayOfWeek.SATURDAY to "SA")
    private fun events(): List<JsonObject> = store["/calendar"]?.second?.jsonObject?.arr("events").orEmpty()
    private fun saveEvents(xs: List<JsonObject>) { store["/calendar"] = 200 to buildJsonObject { put("events", JsonArray(xs)); put("conflicts", JsonArray(conflicts(xs))) } }
    private fun overlap(a: JsonObject, b: JsonObject) = ms(a.str("starts_at")) < ms(b.str("ends_at")) && ms(b.str("starts_at")) < ms(a.str("ends_at"))
    /** The conflict rules (§20.9), as code: the calendar never decides. */
    private fun conflicts(xs: List<JsonObject>): List<JsonObject> {
        val out = mutableListOf<JsonObject>()
        fun c(a: String, b: String, rule: String, severity: String, note: String) = buildJsonObject { put("a", a); put("b", b); put("rule", rule); put("severity", severity); put("note_fa", note) }
        val live = xs.filter { it.str("status") == "planned" }
        val blackout = list("/authority").map { it.jsonObject }.firstOrNull { it.str("key") == "deploy.blackout_days" }?.obj("limit")?.let { (it["days"] as? JsonArray)?.map { d -> d.jsonPrimitive.content } }.orEmpty().toSet()
        for (d in live.filter { it.str("kind") == "deploy" }) {
            val dr = d.str("ref")!!
            for (o in live) {
                val or = o.str("ref")!!
                if (or == dr) continue
                val k = o.str("kind")
                if (k == "freeze" && (o.str("company") == d.str("company") || o.str("company") == "HQ") && overlap(d, o)) out += c(dr, or, "deploy_in_freeze", "high", "انتشار داخل فریز «${o.str("title_fa")}».")
                if ((k == "campaign" || k == "event") && o.str("company") == d.str("company") && overlap(d, o)) out += c(dr, or, "deploy_in_campaign", "high", "انتشار هم‌زمان با ${if (k == "campaign") "کمپین" else "رویداد"} همان شرکت.")
                if (k == "deploy" && o.str("company") == d.str("company") && dr < or && overlap(d, o)) out += c(dr, or, "two_deploys", "medium", "دو انتشار هم‌زمان یک شرکت.")
                if (k == "maintenance" && overlap(d, o)) out += c(dr, or, "maintenance_during_deploy", "medium", "نگه‌داری هم‌زمان با انتشار.")
                if (k == "holiday" && overlap(d, o)) out += c(dr, or, "deploy_on_holiday", "medium", "انتشار در روز تعطیل.")
            }
            val day = WD[Instant.ofEpochMilli(ms(d.str("starts_at"))).atOffset(TEHRAN).dayOfWeek]
            if (day in blackout) out += c(dr, dr, "deploy_on_blackout_day", "medium", "انتشار در روز ممنوع ماتریس اختیار.")
        }
        return out
    }

    // ---- knowledge (§20.3)
    private val VALID = mapOf("fact" to 90, "faq" to 180, "playbook" to 365, "policy" to 365, "principle" to 730)
    private fun knowledgeList(): List<JsonObject> = list("/knowledge").map { it.jsonObject }
    private fun saveEntry(k: JsonObject, history: JsonObject? = null) {
        val ref = k.str("ref")!!
        val all = knowledgeList()
        store["/knowledge"] = 200 to page(if (all.any { it.str("ref") == ref }) all.map { if (it.str("ref") == ref) k else it } else listOf<JsonElement>(k) + all)
        store["/knowledge/$ref"] = 200 to k
        val older = list("/knowledge/$ref/versions").map { it.jsonObject }.drop(1)
        store["/knowledge/$ref/versions"] = 200 to JsonArray(listOf(k) + listOfNotNull(history) + older)
    }
    private fun knowledgeIn(b: JsonObject): String? {
        val kind = b.str("kind")
        if (b.str("title_fa").isNullOrBlank() || b.str("body_md").isNullOrBlank()) return "عنوان و متن لازم است."
        if (b.str("layer") !in setOf("holding", "company", "department")) return "لایه‌ی کارمند حافظه‌ی خود کارمند است و این‌جا نوشته نمیشود."
        val days = VALID[kind] ?: return "مقاله‌ی پشتیبانی فقط از صفحه‌ی پشتیبانی نوشته میشود."
        if (b.arr("sources").none { !it.str("ref").isNullOrBlank() }) return "دست‌کم یک منبع لازم است."
        val until = b.str("valid_until")?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
        if (until == null || until.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli() > HqClock.millis() + (days + 1) * 86_400_000L) return "اعتبار $kind حداکثر $days روز است."
        if (b.str("layer") == "department" && b.str("department") == null) return "دپارتمان را انتخاب کن."
        return null
    }

    // ---- batch (§20.10)
    private val BATCHABLE = setOf("proposal", "meeting_resolution", "knowledge_entry")
    private fun authorityLimit(key: String, field: String): Double? = list("/authority").map { it.jsonObject }.firstOrNull { it.str("key") == key }?.obj("limit")?.let { (it[field] as? JsonPrimitive)?.content?.toDoubleOrNull() }
    private fun whyNot(d: JsonObject?): String? = when {
        d == null -> "not_found"
        d.str("status") != "pending" -> "not_pending"
        d.str("kind") !in BATCHABLE -> "kind"
        (d.str("action_class") ?: "A1") != "A1" -> "action_class"
        d.str("risk") != "low" -> "risk"
        (d["reversible"] as? JsonPrimitive)?.booleanOrNull == false -> "irreversible"
        d["amendments"] is JsonObject || d["amendments"] is JsonArray -> "amended"
        (d.obj("quota_estimate").str("usd")?.toDoubleOrNull() ?: 0.0) > (authorityLimit("batch.max_usd", "usd") ?: 2.0) -> "over_max_usd"
        else -> null
    }

    /** What sealing a §20 card does in the demo: a proposal with a promise gets its 30/60/90-day reviews. */
    private fun decided17(d: JsonObject) {
        val e = d["expected"] as? JsonObject ?: return
        if (d.str("kind") != "proposal") return
        val all = list("/outcomes").map { it.jsonObject }.toMutableList()
        for (day in listOf(30, 60, 90).filter { it <= e.int("by_days") }) {
            val ref = pad("OR-", all.size + 1, 4)
            all += buildJsonObject {
                put("id", "or-$ref"); put("ref", ref); put("decision", d["ref"]!!); put("company", d["company"]!!); put("day", day); put("due_at", ahead(60L * 24 * day)); put("expected", e)
                put("measured", JsonNull); put("verdict", "pending"); put("proposer", d["proposer"]!!); put("proposer_note_md", JsonNull); put("overseer_note_md", JsonNull); put("status", "due")
            }
        }
        store["/outcomes"] = 200 to page(all)
    }

    private fun v17Read(path: String, q: Map<String, String?>): Pair<Int, JsonElement>? {
        fun has(o: JsonObject, k: String) = q[k] == null || o.str(k) == q[k]
        val notFound = 404 to problem16(404, "not_found", "پیدا نشد.")
        when (path) {
            "/meetings" -> return 200 to page(meetingList().filter { has(it, "type") && has(it, "company") && has(it, "state") }.sortedByDescending { ms(it.str("starts_at")) })
            "/knowledge" -> {
                val text = q["q"]?.trim().orEmpty()
                return 200 to page(knowledgeList().filter { k ->
                    has(k, "layer") && has(k, "company") && has(k, "department") && has(k, "kind") &&
                        (if (q["status"] != null) k.str("status") == q["status"] else q["include_expired"] == "true" || k.str("status") != "expired") &&
                        (text.isEmpty() || "${k.str("ref")} ${k.str("title_fa")} ${k.str("body_md")}".contains(text))
                })
            }
            "/scorecards" -> {
                val text = q["q"]?.trim().orEmpty()
                return 200 to page(list("/scorecards").map { it.jsonObject }.filter { r -> text.isEmpty() || "${r.str("company")} ${nameOf(r.str("company"))}".contains(text) || text.contains(r.str("company").orEmpty()) })
            }
            "/okr" -> return 200 to JsonArray(list("/okr").filter { has(it.jsonObject, "company") && has(it.jsonObject, "quarter") && has(it.jsonObject, "status") })
            "/outcomes" -> return 200 to page(list("/outcomes").map { it.jsonObject }.filter { r ->
                has(r, "company") && has(r, "verdict") && has(r, "decision") && (q["due"] != "true" || (r.str("status") == "due" && ms(r.str("due_at")) <= HqClock.millis()))
            }.sortedBy { ms(it.str("due_at")) })
            "/risks" -> {
                val min = q["min_score"]?.toIntOrNull() ?: 0
                return 200 to page(list("/risks").map { it.jsonObject }.filter { has(it, "company") && has(it, "status") && has(it, "category") && it.int("score") >= min }
                    .sortedWith(compareByDescending<JsonObject> { it.int("score") }.thenBy { it.str("ref") }))
            }
            "/risks/matrix" -> {
                val counts = Array(5) { IntArray(5) }
                for (r in list("/risks").map { it.jsonObject }) if (r.str("status") != "closed" && has(r, "company")) counts[r.int("likelihood") - 1][r.int("impact") - 1]++
                return 200 to buildJsonObject { put("company", q["company"]?.let { s -> JsonPrimitive(s) } ?: JsonNull); put("counts", JsonArray(counts.map { row -> JsonArray(row.map { n -> JsonPrimitive(n) }) })) }
            }
            "/calendar" -> {
                val from = q["from"]?.let { runCatching { LocalDate.parse(it).atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli() }.getOrNull() } ?: Long.MIN_VALUE
                val to = q["to"]?.let { runCatching { LocalDate.parse(it).atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli() }.getOrNull() } ?: Long.MAX_VALUE
                val all = events()
                val xs = all.filter { e ->
                    ms(e.str("ends_at")) >= from && ms(e.str("starts_at")) <= to && has(e, "kind") &&
                        (q["company"] == null || e.str("company") == q["company"] || e.str("company") == null || e.str("company") == "HQ")
                }.sortedBy { ms(it.str("starts_at")) }
                val refs = xs.map { it.str("ref") }.toSet()
                return 200 to buildJsonObject { put("events", JsonArray(xs)); put("conflicts", JsonArray(conflicts(all).filter { it.str("a") in refs || it.str("b") in refs })) }
            }
            "/decisions/batchable" -> {
                val max = authorityLimit("batch.max_items", "items")?.toInt() ?: 20
                return 200 to JsonArray(list("/decisions?status=all").map { it.jsonObject }.filter { whyNot(it) == null }.take(max).map { d ->
                    buildJsonObject { for (k in listOf("ref", "version", "kind", "company", "title", "quota_estimate", "proposer", "risk", "created_at", "expires_at")) put(k, d[k] ?: JsonNull) }
                })
            }
        }
        Regex("^/meetings/(MT-\\d+)(/turns)?$").find(path)?.let { m ->
            val ref = m.groupValues[1]
            var mt = meetingOf(ref) ?: return notFound
            if (m.groupValues[2].isEmpty()) return 200 to mt
            val sc = meetingScripts[ref]
            if (mt.str("state") == "live" && !sc.isNullOrEmpty() && System.currentTimeMillis() - lastReveal > 8_000) {
                mt = addTurn(mt, sc.removeAt(0)); saveMeeting(mt); lastReveal = System.currentTimeMillis()
            }
            val cur = store["/meetings/$ref/turns"]?.second?.jsonObject ?: buildJsonObject { putJsonArray("whispers") {}; put("next_cursor", JsonNull) }
            return 200 to JsonObject(cur + ("items" to JsonArray(turnsOf(ref).filter { q["item"] == null || it.str("item") == q["item"] }.sortedBy { ms(it.str("at")) })))
        }
        Regex("^/charter/([A-Za-z0-9_]+)/versions/(\\d+)/diff$").find(path)?.let { m ->
            val (scope, v) = m.destructured
            store["$path?against=${q["against"]}"]?.let { return it }
            val all = charterAll().filter { it.str("scope") == scope }
            val c = all.firstOrNull { it.int("version") == v.toInt() } ?: return notFound
            val o = all.firstOrNull { it.int("version") == q["against"]?.toIntOrNull() } ?: return 404 to problem16(404, "not_found", "نسخه‌ی مقایسه پیدا نشد.")
            val (a, b) = if (o.int("version") < c.int("version")) o to c else c to o
            return 200 to buildJsonObject {
                put("scope", scope); put("version", c.int("version")); put("against", o.int("version"))
                put("diff", unified(charterText(a), charterText(b), "$scope@${a.int("version")}", "$scope@${b.int("version")}"))
            }
        }
        Regex("^/risks/(RK-\\d+)$").find(path)?.let { m -> return list("/risks").map { it.jsonObject }.firstOrNull { it.str("ref") == m.groupValues[1] }?.let { 200 to it } ?: notFound }
        return null
    }

    private fun v17Write(method: String, path: String, body: JsonObject?, version: Int?, idempotency: String?, stepUp: String?): Reply? {
        val b = body ?: JsonObject(emptyMap())
        val notFound = Reply(404, problem16(404, "not_found", "پیدا نشد."))
        // ---- meetings
        if (path == "/meetings/settings" && method == "PUT") {
            if (stepUp == null) return stepUpMissing()
            val types = list("/meetings/settings").map { it.jsonObject }.toMutableList()
            for (t in b.arr("types")) {
                val i = types.indexOfFirst { it.str("key") == t.str("key") }.takeIf { it >= 0 } ?: continue
                val x = types[i]
                if (t.int("max_rounds") !in 1..3 || t.int("max_speakers") !in 2..8) return bad("دور بین ۱ و ۳ و سخنگو بین ۲ و ۸ است.")
                if ((t["budget_tokens"] == null || t["budget_tokens"] is JsonNull) && t.str("key") != "war_room") return bad("فقط اتاق جنگ بی‌سقف است.")
                if (t.int("version") != x.int("version")) return Reply(409, problem16(409, "version_conflict", "تنظیمات همین حالا عوض شده؛ دوباره نگاه کن."))
                val keys = listOf("max_rounds", "max_speakers", "budget_tokens", "turn_cap_tokens", "owner_presence", "enabled")
                val changed = keys.any { t[it].toString() != x[it].toString() }
                types[i] = JsonObject(x + keys.associateWith { t[it] ?: JsonNull } + ("version" to JsonPrimitive(x.int("version") + if (changed) 1 else 0)))
            }
            store["/meetings/settings"] = 200 to JsonArray(types)
            return Reply(200, JsonArray(types))
        }
        if (path == "/meetings" && method == "POST") {
            replies[idempotency.orEmpty()]?.let { return it }
            val type = b.str("type")
            val t = list("/meetings/settings").map { it.jsonObject }.firstOrNull { it.str("key") == type }
            if (t == null || type == "war_room" || type == "standup") return bad("این نوع جلسه را کد باز میکند، نه دست.")
            val perCompany = type == "company" || type == "postmortem"
            val company = if (perCompany) b.str("company") else "HQ"
            if (company == null) return bad("شرکت را انتخاب کن.")
            val speakers = if (perCompany) listOf(ceo(company), tech(company), inspector) else (operating().map { ceo(it.str("code")!!) } + inspector).takeLast(t.int("max_speakers"))
            val n = (meetingList().mapNotNull { it.str("ref")?.substringAfter('-')?.toIntOrNull() }.maxOrNull() ?: 0) + 1
            val ref = pad("MT-", n, 4)
            val given = b.arr("items").ifEmpty { listOf(buildJsonObject { put("title_fa", "دستور آزاد"); put("time_box_min", 10) }) }
            val its = given.mapIndexed { i, x ->
                buildJsonObject {
                    put("id", "mi-$n-${i + 1}"); put("n", i + 1); put("title_fa", x["title_fa"] ?: JsonPrimitive("")); put("brief_md", x["brief_md"] ?: JsonPrimitive(""))
                    putJsonArray("sources") {}; put("time_box_min", x.int("time_box_min").takeIf { it > 0 } ?: 10); put("speakers", JsonArray(speakers)); put("round", 0); put("state", "waiting")
                }
            }
            val estimate = its.size.toLong() * speakers.size * minOf(t.int("max_rounds"), 2) * 2400 + 6000
            val cap = (t["budget_tokens"] as? JsonPrimitive)?.content?.toLongOrNull()
            val tf = t.str("title_fa").orEmpty()
            val title = if (company == "HQ") tf else "${if (tf == "مدیریت هر شرکت") "مدیریت" else tf} ${nameOf(company)}"
            val starts = b.str("starts_at") ?: HqClock.now().toString()
            val m = buildJsonObject {
                put("id", "mt$n"); put("ref", ref); put("type", type); put("company", company); put("title_fa", title); put("starts_at", starts); put("state", "scheduled"); put("mode", "discussion")
                putJsonObject("budget") { put("cap", cap?.let { n -> JsonPrimitive(n) } ?: JsonNull); put("estimate", if (cap != null) minOf(estimate, cap) else estimate); put("reserved", 0); put("used", 0) }
                put("trimmed_fa", if (cap != null && estimate > cap) JsonPrimitive("برآورد اول ${Math.round(estimate / 1000.0)}K بود و از بودجه بیشتر شد؛ دور دوم دستورهای آخر حذف شد.") else JsonNull)
                put("items", JsonArray(its))
                put("participants", JsonArray(speakers.map { s -> buildJsonObject { put("actor", s); put("role_fa", s["display_fa"]!!); put("speaker", true); put("devil", s.str("code") == "HQ-OVS-MGR") } }))
                put("owner_presence", t["owner_presence"] ?: JsonPrimitive("summary")); put("minutes", JsonNull); put("incident", JsonNull); put("version", 1); put("created_at", stamp); putJsonArray("drafts") {}
            }
            saveMeeting(m)
            saveTurns(ref, emptyList())
            val ce = pad("CE-", events().size + 1, 4)
            saveEvents(events() + buildJsonObject {
                put("id", "ce-$ce"); put("ref", ce); put("company", company); put("kind", "meeting"); put("title_fa", title); put("starts_at", starts)
                put("ends_at", Instant.ofEpochMilli(ms(starts) + 60 * 60_000L).toString()); putJsonObject("source") { put("meeting", ref) }; put("status", "planned"); put("risk", "low"); put("created_by", owner); put("version", 1)
            })
            return Reply(201, m).also { if (!idempotency.isNullOrEmpty()) replies[idempotency] = it }
        }
        Regex("^/meetings/(MT-\\d+)(?:/(speak|control))?$").find(path)?.let { mm ->
            val ref = mm.groupValues[1]
            var m = meetingOf(ref) ?: return Reply(404, problem16(404, "not_found", "این جلسه پیدا نشد."))
            when (mm.groupValues[2]) {
                "" -> {
                    if (method != "PATCH") return null
                    unmatched(version, m.int("version"))?.let { return it }
                    if (m.str("state") == "ended" || m.str("state") == "cancelled") return Reply(409, problem16(409, "validation_failed", "جلسه‌ی تمام‌شده عوض نمیشود."))
                    (b["budget_cap"] as? JsonPrimitive)?.content?.toLongOrNull()?.let { capNew ->
                        val bud = m.obj("budget")
                        val cap = (bud["cap"] as? JsonPrimitive)?.content?.toLongOrNull()
                        if (cap != null && capNew > cap) return bad("این‌جا فقط کم کردن بودجه است؛ افزایش با «افزایش بودجه» در جلسه‌ی زنده.")
                        var nb = JsonObject(bud + ("cap" to JsonPrimitive(capNew)))
                        if (bud.long("estimate") > capNew) {
                            m = JsonObject(m + ("trimmed_fa" to JsonPrimitive("برآورد ${Math.round(bud.long("estimate") / 1000.0)}K از بودجه‌ی تازه‌ی ${Math.round(capNew / 1000.0)}K بیشتر بود؛ طبق قاعده اول دور دوم دستورهای کم‌اهمیت، بعد سخنگوها کم شد.")))
                            nb = JsonObject(nb + ("estimate" to JsonPrimitive(capNew)))
                        }
                        m = JsonObject(m + ("budget" to nb))
                    }
                    for (o in b.arr("items")) m = mapItem(m, o.str("id")) { y ->
                        val skip = (o["skip"] as? JsonPrimitive)?.booleanOrNull
                        val st = when { skip == true && y.str("state") == "waiting" -> "skipped"; skip == false && y.str("state") == "skipped" -> "waiting"; else -> y.str("state") }
                        JsonObject(y + mapOf("n" to JsonPrimitive(o.int("n")), "state" to JsonPrimitive(st)))
                    }
                    m = withItems(m, items(m).sortedBy { it.int("n") })
                    b.str("owner_presence")?.let { m = JsonObject(m + ("owner_presence" to JsonPrimitive(it))) }
                    m = bumped(m)
                    saveMeeting(m)
                    return Reply(200, m)
                }
                "speak" -> {
                    if (idempotency.isNullOrEmpty()) return bad("Idempotency-Key لازم است.")
                    replies[idempotency]?.let { return it }
                    if (m.str("state") != "live") return Reply(409, problem16(409, "meeting_not_live", "جلسه زنده نیست."))
                    val text = b.str("text")?.trim().orEmpty()
                    if (text.isEmpty() && b.str("file_id") == null) return bad("متن یا صدا لازم است.")
                    m = addTurn(m, buildJsonObject { put("speaker", owner); put("kind", "owner"); put("statement_md", text.ifEmpty { "(پیام صوتی)" }); putJsonArray("claims") {}; put("tokens", 0) })
                    saveMeeting(m)
                    val turn = turnsOf(ref).last()
                    val it = currentItem(m)
                    it?.arr("speakers")?.firstOrNull { s -> s.str("code") != "HQ-OVS-MGR" }?.let { next ->
                        meetingScripts.getOrPut(ref) { mutableListOf() }.add(0, buildJsonObject {
                            put("item", it["id"]!!); put("speaker", next); put("kind", "statement"); put("statement_md", "دریافت شد؛ این را در جمع‌بندی همین دستور میاورم و منبعش را میگذارم."); putJsonArray("claims") {}; put("tokens", 1600)
                        })
                    }
                    lastReveal = System.currentTimeMillis() - 5_000
                    return Reply(201, turn).also { replies[idempotency] = it }
                }
                else -> {
                    if (m.str("state") != "live" && m.str("state") != "closing") return Reply(409, problem16(409, "meeting_not_live", "جلسه زنده نیست."))
                    val it = currentItem(m)
                    when (b.str("action")) {
                        "raise_budget" -> {
                            val tokens = b.long("tokens")
                            if (tokens <= 0) return bad("مقدار افزایش را بنویس.")
                            val bud = m.obj("budget")
                            (bud["cap"] as? JsonPrimitive)?.content?.toLongOrNull()?.let { cap ->
                                m = JsonObject(m + ("budget" to JsonObject(bud + mapOf("cap" to JsonPrimitive(cap + tokens), "reserved" to JsonPrimitive(bud.long("reserved") + tokens)))))
                            }
                        }
                        "skip_item" -> { if (it != null) m = mapItem(m, it.str("id")) { x -> JsonObject(x + ("state" to JsonPrimitive("skipped"))) }; m = nextItem(m) }
                        "next_round" -> {
                            val max = list("/meetings/settings").map { x -> x.jsonObject }.firstOrNull { x -> x.str("key") == m.str("type") }?.int("max_rounds") ?: 2
                            val drafts = m.arr("drafts").filter { d -> it != null && d.str("item") == it.str("id") }
                            // The round in progress finishes first: what the demo still had queued for it is said before the next round opens.
                            val sc = meetingScripts.getOrPut(ref) { mutableListOf() }
                            while (sc.isNotEmpty() && sc[0].str("kind") != "vote" && sc[0].str("item") == it?.str("id")) m = addTurn(m, sc.removeAt(0))
                            if (it != null && it.int("round") < max && drafts.isNotEmpty()) {
                                m = mapItem(m, it.str("id")) { x -> JsonObject(x + mapOf("round" to JsonPrimitive(x.int("round") + 1), "state" to JsonPrimitive("round_2"))) }
                                val votes = listOf("support", "support", "support", "abstain")
                                it.arr("speakers").forEachIndexed { k, s ->
                                    val v = votes[k % 4]
                                    sc += buildJsonObject {
                                        put("item", it["id"]!!); put("speaker", s); put("kind", "vote"); put("statement_md", if (v == "support") "موافق." else "ممتنع."); putJsonArray("claims") {}; put("tokens", 700)
                                        putJsonObject("stance") { put("draft", drafts[0]["id"]!!); put("vote", v); put("reason_fa", if (v == "support") "ساعت کم‌بار ریسک بازگشت را کم میکند." else "تا منبع عدد سهم کندی نیاید نظری ندارم.") }
                                    }
                                }
                                lastReveal = System.currentTimeMillis() - 6_000
                            } else {
                                if (it != null) m = mapItem(m, it.str("id")) { x -> JsonObject(x + ("state" to JsonPrimitive("done"))) }
                                m = nextItem(m)
                            }
                        }
                        "end" -> { m = endMeeting(m); meetingScripts[ref] = mutableListOf() }
                        else -> return bad("این کار شناخته نیست.")
                    }
                    m = bumped(m)
                    saveMeeting(m)
                    return Reply(200, m)
                }
            }
        }
        // ---- charter
        Regex("^/charter/([A-Za-z0-9_]+)(?:/versions/(\\d+)/seal)?$").find(path)?.let { mm ->
            val scope = mm.groupValues[1]
            if (scope != "holding" && operating().none { it.str("code") == scope }) return Reply(404, problem16(404, "not_found", "این دامنه پیدا نشد."))
            val all = charterAll()
            if (mm.groupValues[2].isEmpty()) {
                if (method != "PUT") return null
                val text = b.str("body_md").orEmpty()
                val max = if (scope == "holding") 6000 else 3000
                if (text.isBlank()) return bad("متن خالی است.")
                if (text.length > max) return bad("متن از سقف $max نویسه بلندتر است؛ این سند در هر اجرا خوانده میشود.")
                if (b.arr("red_lines").any { it.str("key").isNullOrBlank() || it.str("text_fa").isNullOrBlank() }) return bad("هر خط قرمز کلید و متن دارد.")
                val v = (all.filter { it.str("scope") == scope }.maxOfOrNull { it.int("version") } ?: 0) + 1
                val redLines = b["red_lines"] ?: JsonArray(emptyList())
                val c = buildJsonObject {
                    put("scope", scope); put("version", v); put("status", "proposed"); put("body_md", text); put("red_lines", redLines)
                    put("body_sha256", Api.sha256(canonical(buildJsonObject { put("body_md", text); put("red_lines", redLines) })))
                    put("created_by", owner); put("created_at", stamp); put("sealed_by", JsonNull); put("sealed_at", JsonNull)
                }
                saveCharters(all.map { if (it.str("scope") == scope && it.str("status") == "proposed") JsonObject(it + ("status" to JsonPrimitive("superseded"))) else it } + c)
                return Reply(201, c)
            }
            if (method != "POST") return null
            if (stepUp == null) return stepUpMissing()
            val v = mm.groupValues[2].toInt()
            val c = all.firstOrNull { it.str("scope") == scope && it.int("version") == v }
            if (c == null || c.str("status") != "proposed") return Reply(409, problem16(409, "decision_not_pending", "این نسخه منتظر مُهر نیست."))
            val sealed = JsonObject(c + mapOf("status" to JsonPrimitive("sealed"), "sealed_by" to owner, "sealed_at" to stamp))
            saveCharters(all.map {
                when {
                    it.str("scope") == scope && it.int("version") == v -> sealed
                    it.str("scope") == scope && it.str("status") == "sealed" -> JsonObject(it + ("status" to JsonPrimitive("superseded")))
                    else -> it
                }
            })
            return Reply(200, sealed)
        }
        // ---- knowledge
        if (path == "/knowledge" && method == "POST") {
            knowledgeIn(b)?.let { return bad(it) }
            val n = (knowledgeList().mapNotNull { it.str("ref")?.takeIf { r -> r.startsWith("K-") }?.substringAfter('-')?.toIntOrNull() }.maxOrNull() ?: 0) + 1
            val ref = pad("K-", n, 4)
            val k = JsonObject(buildJsonObject {
                put("id", "k-$ref"); put("ref", ref); put("review", JsonNull); put("version", 1)
            } + b + buildJsonObject {
                put("department", if (b.str("layer") == "department") b["department"] ?: JsonNull else JsonNull)
                put("status", "approved"); put("approved_by", owner); put("created_by", owner); put("created_at", stamp); put("updated_at", stamp)
            })
            saveEntry(k)
            return Reply(201, k)
        }
        Regex("^/knowledge/(K-\\d+)(/retire)?$").find(path)?.let { mm ->
            val k = knowledgeList().firstOrNull { it.str("ref") == mm.groupValues[1] } ?: return Reply(404, problem16(404, "not_found", "این ورودی پیدا نشد."))
            if (k.str("layer") == "employee") return Reply(405, problem16(405, "validation_failed", "لایه‌ی کارمند حافظه‌ی خود اوست؛ فقط خواندنی."))
            if (mm.groupValues[2].isNotEmpty()) {
                val next = JsonObject(k + mapOf("status" to JsonPrimitive("retired"), "updated_at" to stamp))
                saveEntry(next)
                return Reply(200, next)
            }
            if (method != "PUT") return null
            knowledgeIn(JsonObject(b + ("layer" to (b["layer"] ?: k["layer"]!!))))?.let { return bad(it) }
            val old = JsonObject(k + ("status" to JsonPrimitive(if (k.str("status") == "approved") "retired" else k.str("status").orEmpty())))
            val next = JsonObject(k + b + mapOf("version" to JsonPrimitive(k.int("version") + 1), "status" to JsonPrimitive("approved"), "approved_by" to owner, "review" to JsonNull, "updated_at" to stamp))
            saveEntry(next, history = old)
            return Reply(200, next)
        }
        if (Regex("^/knowledge/KB-\\d+").containsMatchIn(path)) return Reply(405, problem16(405, "validation_failed", "مقاله‌ی پشتیبانی فقط از صفحه‌ی پشتیبانی ویرایش میشود."))
        // ---- KPIs
        Regex("^/kpis/([A-Z0-9]+)$").find(path)?.let { mm ->
            if (method != "PUT") return null
            val co = mm.groupValues[1]
            val set = store["/kpis/$co"]?.second?.jsonObject ?: return Reply(404, problem16(404, "not_found", "برای این شرکت KPI تعریف نشده."))
            unmatched(version, set.int("version"))?.let { return it }
            var kpis = set.arr("kpis")
            for (x in b.arr("kpis")) {
                if (kpis.none { it.str("key") == x.str("key") }) return bad("KPI ${x.str("key")} تعریف نشده.")
                if (x.int("freshness_hours") !in 1..720) return bad("تازگی بین ۱ ساعت و ۳۰ روز است.")
                kpis = kpis.map { k -> if (k.str("key") != x.str("key")) k else JsonObject(k + mapOf("target" to (x["target"] ?: JsonNull), "scorecard" to x["scorecard"]!!, "status" to x["status"]!!, "freshness_hours" to x["freshness_hours"]!!, "version" to JsonPrimitive(k.int("version") + 1))) }
            }
            val next = JsonObject(set + mapOf("kpis" to JsonArray(kpis), "version" to JsonPrimitive(set.int("version") + 1)))
            store["/kpis/$co"] = 200 to next
            // The cards and the scorecard read the definitions: targets, scorecard membership and paused KPIs follow.
            val defs = kpis.associateBy { it.str("key") }
            val cardKey = "/cards?company=$co"
            val cards = list(cardKey).map { it.jsonObject }
            val allCardKpis = cards.flatMap { c -> c.arr("kpis").map { k -> c.str("card") to k } }
            store[cardKey] = 200 to JsonArray(cards.map { c ->
                JsonObject(c + ("kpis" to JsonArray(c.arr("kpis").filter { defs[it.str("key")]?.str("status") != "paused" }.map { k -> JsonObject(k + ("target" to (defs[k.str("key")]?.get("target") ?: JsonNull))) })))
            })
            store["/scorecards"] = 200 to page(list("/scorecards").map { it.jsonObject }.map { row ->
                if (row.str("company") != co) row else JsonObject(row + ("kpis" to JsonArray(kpis.filter { (it["scorecard"] as? JsonPrimitive)?.booleanOrNull == true }.mapNotNull { d ->
                    val hit = row.arr("kpis").firstOrNull { it.str("key") == d.str("key") } ?: allCardKpis.firstOrNull { it.second.str("key") == d.str("key") }?.let { (card, k) -> JsonObject(k + mapOf("card" to JsonPrimitive(card), "direction" to (d["direction"] ?: JsonPrimitive("up")))) }
                    hit?.let { JsonObject(it + ("target" to (d["target"] ?: JsonNull))) }
                })))
            })
            return Reply(200, next)
        }
        // ---- authority
        if (path == "/authority" && method == "PUT") {
            if (stepUp == null) return stepUpMissing()
            val rules = list("/authority").map { it.jsonObject }
            val changes = b.arr("rules")
            for (x in changes) {
                val r = rules.firstOrNull { it.str("key") == x.str("key") } ?: return bad("ردیف ${x.str("key")} پیدا نشد.")
                if ((r["locked"] as? JsonPrimitive)?.booleanOrNull == true) return bad("«${r.str("title_fa")}» قفل است و از داده عوض نمیشود.")
                if (r.int("version") != x.int("version")) return Reply(409, problem16(409, "version_conflict", "ماتریس همین حالا عوض شده؛ دوباره نگاه کن."))
                val lim = x["limit"] as? JsonObject
                val num = listOf("tokens_month", "usd", "count_day", "count_hour", "items").firstNotNullOfOrNull { k -> (lim?.get(k) as? JsonPrimitive)?.content?.toDoubleOrNull() }
                val bounds = r["bounds"] as? JsonObject
                if (num != null && bounds != null) {
                    val lo = bounds.str("min")?.toDoubleOrNull() ?: (bounds["min"] as? JsonPrimitive)?.content?.toDoubleOrNull() ?: Double.MIN_VALUE
                    val hi = (bounds["max"] as? JsonPrimitive)?.content?.toDoubleOrNull() ?: Double.MAX_VALUE
                    if (num < lo || num > hi) return bad("«${r.str("title_fa")}» بیرون از محدوده‌ی ${num(lo)} تا ${num(hi)} است.")
                }
            }
            val next = rules.map { r ->
                val x = changes.firstOrNull { it.str("key") == r.str("key") } ?: return@map r
                JsonObject(r + mapOf("limit" to (x["limit"] ?: JsonNull), "version" to JsonPrimitive(r.int("version") + 1)) + (x.str("actor")?.let { mapOf("actor" to JsonPrimitive(it)) } ?: emptyMap()))
            }
            store["/authority"] = 200 to JsonArray(next)
            saveEvents(events())
            return Reply(200, JsonArray(next))
        }
        // ---- risks
        if (path == "/risks" && method == "POST") {
            if (b.str("title_fa").isNullOrBlank() || b.str("company") == null) return bad("عنوان و شرکت لازم است.")
            val l = b.int("likelihood"); val i = b.int("impact")
            if (l !in 1..5 || i !in 1..5) return bad("احتمال و اثر بین ۱ و ۵ است.")
            val score = l * i
            val all = list("/risks").map { it.jsonObject }
            val ref = pad("RK-", all.size + 1, 4)
            val r = JsonObject(buildJsonObject {
                put("id", "rk-$ref"); put("mitigation_md", JsonNull); put("accepted", JsonNull); putJsonObject("links") {}; put("version", 1)
            } + b + buildJsonObject {
                put("ref", ref); put("body_md", b["body_md"] ?: JsonPrimitive("")); put("owner", inspector); put("status", "open"); put("score", score)
                put("review_at", b["review_at"] ?: ahead(60L * 24 * (if (score >= 15) 14 else if (score >= 8) 30 else 90)))
                putJsonArray("history") { add(buildJsonObject { put("at", stamp); put("by", owner); put("change", "ثبت شد"); put("note", "") }) }
            })
            store["/risks"] = 200 to page(all + r)
            return Reply(201, r)
        }
        Regex("^/risks/(RK-\\d+)$").find(path)?.let { mm ->
            if (method != "PATCH") return null
            val all = list("/risks").map { it.jsonObject }
            val r = all.firstOrNull { it.str("ref") == mm.groupValues[1] } ?: return Reply(404, problem16(404, "not_found", "این ریسک پیدا نشد."))
            unmatched(version, r.int("version"))?.let { return it }
            if (b.str("status") == "closed") return bad("بستن ریسک با تأیید بازرس کل (QC) است؛ از او بخواه.")
            val change = b.keys.joinToString("، ") { k -> "$k: ${(r[k] as? JsonPrimitive)?.content?.take(24) ?: "—"} ← ${(b[k] as? JsonPrimitive)?.content?.take(24) ?: "—"}" }
            var next = JsonObject(r + b + ("version" to JsonPrimitive(r.int("version") + 1)))
            next = JsonObject(next + mapOf(
                "score" to JsonPrimitive(next.int("likelihood") * next.int("impact")),
                "history" to JsonArray(listOf(buildJsonObject { put("at", stamp); put("by", owner); put("change", change); put("note", "") }) + r.arr("history")),
            ))
            store["/risks"] = 200 to page(all.map { if (it.str("ref") == r.str("ref")) next else it })
            return Reply(200, next)
        }
        // ---- calendar
        if (path == "/calendar" && method == "POST") {
            if (b.str("title_fa").isNullOrBlank() || b.str("starts_at") == null || b.str("ends_at") == null || ms(b.str("ends_at")) <= ms(b.str("starts_at"))) return bad("عنوان و بازه‌ی درست لازم است.")
            val ref = pad("CE-", events().size + 1, 4)
            val e = JsonObject(buildJsonObject {
                put("id", "ce-$ref"); put("company", JsonNull); putJsonObject("source") {}; put("status", "planned"); put("risk", "low"); put("version", 1)
            } + b + buildJsonObject { put("ref", ref); put("created_by", owner) })
            saveEvents(events() + e)
            return Reply(201, e)
        }
        Regex("^/calendar/(CE-\\d+)$").find(path)?.let { mm ->
            if (method != "PATCH") return null
            val all = events()
            val e = all.firstOrNull { it.str("ref") == mm.groupValues[1] } ?: return Reply(404, problem16(404, "not_found", "این رویداد پیدا نشد."))
            unmatched(version, e.int("version"))?.let { return it }
            val next = JsonObject(e + b + ("version" to JsonPrimitive(e.int("version") + 1)))
            saveEvents(all.map { if (it.str("ref") == e.str("ref")) next else it })
            return Reply(200, next)
        }
        // ---- batch seal
        if (path == "/decisions/batch/approve") {
            if (stepUp == null) return stepUpMissing()
            if (idempotency.isNullOrEmpty()) return bad("Idempotency-Key لازم است.")
            replies[idempotency]?.let { return it }
            val xs = b.arr("items")
            if (xs.isEmpty()) return bad("هیچ کارتی انتخاب نشده.")
            val all = list("/decisions?status=all").map { it.jsonObject }
            val refused = xs.mapNotNull { x ->
                val d = all.firstOrNull { it.str("ref") == x.str("ref") }
                (whyNot(d) ?: if (d!!.int("version") != x.int("version")) "changed" else null)?.let { x.str("ref").orEmpty() to it }
            }.toMutableList()
            val max = authorityLimit("batch.max_items", "items")?.toInt() ?: 20
            if (xs.size > max) refused += xs[max].str("ref").orEmpty() to "over_max_items"
            if (refused.isNotEmpty()) return Reply(422, problem16(422, "batch_not_eligible", "یکی از کارت‌ها دیگر شایسته‌ی مُهر گروهی نیست؛ هیچ کارتی مُهر نشد.", buildJsonObject {
                putJsonObject("fields") { put("items", JsonArray(refused.map { (r, why) -> buildJsonObject { put("ref", r); put("reason", why) } })) }
            }))
            val batch = pad("B-", batchSeq++, 4)
            val out = xs.map { x ->
                val ref = x.str("ref")!!
                val resolution = pad("M-", ++resolutionSeq, 4)
                val d = JsonObject(all.first { it.str("ref") == ref } + mapOf(
                    "status" to JsonPrimitive("approved"), "decided_at" to stamp, "decided_by" to owner, "resolution" to JsonPrimitive(resolution), "effect_status" to JsonPrimitive("applied"),
                    "seal" to buildJsonObject { put("method", "passkey_uv"); put("sealed_at", stamp); put("step_up_id", "demo"); put("batch", batch) },
                ))
                store["/decisions/$ref"] = 200 to d
                replaceIn("/decisions?status=all", ref, d)
                decided17(d)
                buildJsonObject { put("ref", ref); put("resolution", resolution) }
            }
            store["/decisions?status=pending"] = 200 to page(list("/decisions?status=all").filter { it.jsonObject.str("status") == "pending" })
            bumpInbox()
            return Reply(200, buildJsonObject { put("batch", batch); put("items", JsonArray(out)) }).also { replies[idempotency] = it }
        }
        return null
    }

    private fun num(v: Double): String = if (v % 1.0 == 0.0) v.toLong().toString() else v.toString()
}
