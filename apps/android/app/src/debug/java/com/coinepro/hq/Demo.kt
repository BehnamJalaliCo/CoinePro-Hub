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
        if (req.method == "GET") ownerToolsRead(path, query)?.let { return respond(req, it) }
        else ownerToolsWrite(req.method, path, body, req.header("If-Match")?.trim('"')?.toIntOrNull())?.let { return respond(req, it) }
        return respond(req, if (req.method == "GET") read(path, query) else write(path, body))
    }

    private fun respond(req: okhttp3.Request, result: Pair<Int, JsonElement>): Response {
        val (status, out) = result
        return Response.Builder()
            .request(req).protocol(Protocol.HTTP_1_1).code(status).message("demo")
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

}
