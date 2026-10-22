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
        // ⟨1.6⟩ the studio's renders, posters and voice clips (assets/demo), as the web serves them from public/demo.
        if (req.method == "GET" && path.startsWith("/files/")) demoFile(req, path.removePrefix("/files/"), req.url.queryParameter("variant"))?.let { return it }
        // ⟨1.5⟩ a body may be a list (§21.13 seats), not only an object.
        val raw = req.body?.let { b -> Buffer().also { b.writeTo(it) }.readUtf8() }?.takeIf { it.isNotBlank() }?.let { Api.json.parseToJsonElement(it) }
        val body = raw as? JsonObject
        val query = req.url.queryParameterNames.associateWith { req.url.queryParameter(it) }
        val version = req.header("If-Match")?.trim('"')?.toIntOrNull()
        tick18()
        // ⟨1.7⟩ §23: the archive, and the step-up and staleness check on approving its two cards.
        archive.handle(req, path, raw, query)?.let { return it }
        if (req.method == "GET") {
            v19Read(path, query)?.let { return respond(req, it.status to it.body, it.headers) }
            v18Read(path, query)?.let { return respond(req, it.status to it.body, it.headers) }
            v17Read(path, query)?.let { return respond(req, it) }
            v16Read(path, query)?.let { return respond(req, it) }
            ownerToolsRead(path, query)?.let { return respond(req, it) }
        } else {
            v19Write(req.method, path, body ?: JsonObject(emptyMap()), version, req.header("Idempotency-Key"), req.header("X-Step-Up"))?.let { return respond(req, it.status to it.body, it.headers) }
            v18Write(req.method, path, raw, version, req.header("Idempotency-Key"), req.header("X-Step-Up"))?.let { return respond(req, it.status to it.body, it.headers) }
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
            // ⟨1.6⟩ §22: the item published or rejected, the email sent or its case reopened, the role active or rejected.
            decided19(updated.jsonObject)
            // ⟨1.7⟩ §23: the schema change applied, or the batch disposed with tombstones (held records skipped).
            archive.decided(updated.jsonObject)
            // ⟨1.5⟩ §21: the prediction revealed, memos, the evaluation's effect and the HR round, for every verdict.
            return 200 to decided18(updated.jsonObject)
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
                // ⟨1.5⟩ §21.1: the advisor's devil mode (thread A; v18Write refuses it anywhere else).
                body?.get("mode")?.let { put("meta", buildJsonObject { put("mode", it) }) }
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
    private val archive by lazy { ArchiveDemo(context, store, files) }
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
                decided18(d)
                buildJsonObject { put("ref", ref); put("resolution", resolution) }
            }
            store["/decisions?status=pending"] = 200 to page(list("/decisions?status=all").filter { it.jsonObject.str("status") == "pending" })
            bumpInbox()
            return Reply(200, buildJsonObject { put("batch", batch); put("items", JsonArray(out)) }).also { replies[idempotency] = it }
        }
        return null
    }

    // ------------------------------------------------------------ ⟨1.5⟩ §21 --
    // Management tools (contract §21), as the web's mock-v18.ts: what the hub computes by rule (seat caps, reminders, the baseline
    // prediction and its accuracy, the HR round's close) is code here too, reduced to what a demo needs; what a model would write is
    // canned text. Timers run on the wall clock, so a memo still finishes writing while HqClock is fixed (the screenshots).
    private val t0 = System.currentTimeMillis()
    private val memoReady = mutableMapOf<String, Pair<Long, JsonObject>>()
    private val askRule = mutableMapOf<String, Int>()
    private val askAt = mutableMapOf<String, Long>()
    private val verifying18 = mutableMapOf<String, Long>()
    private val logins = mutableMapOf<String, JsonObject>()
    private val loginAt = mutableMapOf<String, Long>()
    private val creativeAt = mutableMapOf<String, Long>()
    private val creativeReady = mutableMapOf("CR-0007" to t0 + 25_000)

    private fun j(s: String): JsonElement = Api.json.parseToJsonElement(s)
    private fun jo(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(kv.associate { (k, v) ->
        k to when (v) { null -> JsonNull; is JsonElement -> v; is String -> JsonPrimitive(v); is Number -> JsonPrimitive(v); is Boolean -> JsonPrimitive(v); else -> JsonPrimitive(v.toString()) }
    })
    private fun ja(xs: List<JsonElement>) = JsonArray(xs)
    private fun JsonObject.with(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(this + jo(*kv))
    private fun JsonObject.dbl(k: String): Double = (this[k] as? JsonPrimitive)?.content?.toDoubleOrNull() ?: 0.0
    private fun gone18(fa: String) = Reply(404, problem16(404, "not_found", fa))

    // ---- the digital CEO's sealed predictions (§21.10), the same table as mock-v18
    private class Pred(val verdict: String, val confidence: Double, val method: String, val rationale: String?, val principles: List<String>, val minutesBefore: Int)
    private val PRED = mapOf(
        "D-000011" to Pred("approve", 0.82, "baseline", null, emptyList(), 40),
        "D-000004" to Pred("approve", 0.74, "baseline", null, emptyList(), 55),
        "D-000003" to Pred("approve", 0.74, "baseline", null, emptyList(), 30),
        "D-000005" to Pred("approve", 0.71, "baseline", null, emptyList(), 50),
        "D-000008" to Pred("approve", 0.73, "baseline", null, emptyList(), 35),
        "D-000006" to Pred("approve", 0.88, "baseline", null, emptyList(), 20),
        "D-000007" to Pred("approve", 0.66, "model", "اصلاحیه خط قرمز تازه میافزاید و چیزی را برنمیدارد؛ مالک این را تأیید میکند (DP-005).", listOf("DP-005"), 70),
        "D-000009" to Pred("reject", 0.55, "model", "پذیرش ۶۰ روزه طولانی است و مالک تا امروز ریسک بی‌راه کاهش را نپذیرفته.", listOf("DP-004"), 90),
        "D-000017" to Pred("approve", 0.64, "model", "تست‌ها سبزند و canary کوچک است؛ اما پنجره‌ی انتشار در ساعت پربار است (DP-001).", listOf("DP-001"), 10),
        "D-000031" to Pred("approve", 0.83, "baseline", null, emptyList(), 30),
        "D-000032" to Pred("approve", 0.71, "model", "آزمون سایه با ۹۳٪ قبول شده و فقط جواب عین دانشنامه بی‌مالک میرود.", listOf("DP-003"), 45),
        "D-000033" to Pred("approve", 0.8, "baseline", null, emptyList(), 25),
        "D-000034" to Pred("approve", 0.86, "baseline", null, emptyList(), 15),
        "D-000035" to Pred("return", 0.57, "baseline", null, listOf("DP-002"), 15),
        "D-000040" to Pred("approve", 0.69, "model", "پرچم قاعده‌محور، دو ماه امتیاز بالا و پاکت جا دارد؛ مالک ارتقای با شاهد را تأیید میکند.", listOf("DP-003"), 60),
    )
    private val ACTUAL = mapOf("approved" to "approve", "rejected" to "reject", "returned" to "return")

    private fun brief(d: JsonObject): JsonElement {
        val p = PRED[d.str("ref")] ?: return JsonNull
        val actual = ACTUAL[d.str("status")] ?: return JsonNull
        if (d.obj("decided_by").str("kind") != "owner") return JsonNull
        return jo("verdict" to p.verdict, "confidence" to p.confidence, "method" to p.method, "correct" to (p.verdict == actual))
    }

    private fun sha256(s: String): String = java.security.MessageDigest.getInstance("SHA-256").digest(s.toByteArray()).joinToString("") { "%02x".format(it) }

    /** A new clean prediction after a decision, and the three windows recounted (§21.10). */
    private fun scored(d: JsonObject) {
        val ref = d.str("ref") ?: return
        val p = PRED[ref] ?: return
        val actual = ACTUAL[d.str("status")] ?: return
        val decided = ms(d.str("decided_at"))
        val made = maxOf(decided - p.minutesBefore * 60_000L, ms(d.str("created_at")) + 60_000L)
        val madeAt = Instant.ofEpochMilli(made).toString()
        val row = jo(
            "decision" to ref, "kind" to d.str("kind"), "title" to d.str("title"), "made_at" to madeAt, "method" to p.method, "verdict" to p.verdict,
            "confidence" to p.confidence, "rationale_fa" to p.rationale, "principles" to ja(p.principles.map(::JsonPrimitive)),
            "sealed_hash" to sha256("{\"confidence\":${p.confidence},\"decision\":\"$ref\",\"made_at\":\"$madeAt\",\"method\":\"${p.method}\",\"verdict\":\"${p.verdict}\"}"),
            "seen_before" to (settings18().obj("digital_ceo").str("reveal") == "before"), "actual" to actual, "correct" to (p.verdict == actual),
        )
        val rows = listOf(row) + list("/digital-ceo/predictions").map { it.jsonObject }.filter { it.str("decision") != ref }
        store["/digital-ceo/predictions"] = 200 to page(rows)
        val decidedOf = { r: JsonObject -> ms(r.str("made_at")) + (PRED[r.str("decision")]?.minutesBefore ?: 0) * 60_000L }
        val now0 = HqClock.millis()
        fun stats(window: String): JsonObject {
            val span = when (window) { "30d" -> 30L; "90d" -> 90L; else -> Long.MAX_VALUE / 86_400_000L / 2 }
            val xs = rows.filter { (it["seen_before"] as? JsonPrimitive)?.booleanOrNull != true && now0 - decidedOf(it) <= span * 86_400_000L + 60_000L }
            fun acc(ys: List<JsonObject>): JsonElement = if (ys.isEmpty()) JsonNull else JsonPrimitive(ys.count { it["correct"]?.jsonPrimitive?.booleanOrNull == true }.toDouble() / ys.size)
            val byKind = xs.groupBy { it.str("kind").orEmpty() }.mapValues { (_, ys) -> jo("n" to ys.size, "accuracy" to ((acc(ys) as? JsonPrimitive)?.content?.toDoubleOrNull() ?: 0.0)) }
            val calibration = listOf("0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0").mapNotNull { bucket ->
                val (lo, hi) = bucket.split('-').map { it.toDouble() }
                val ys = xs.filter { val c = it.dbl("confidence"); c >= lo && (c < hi || (hi == 1.0 && c <= 1.0)) }
                if (ys.isEmpty()) null else jo("bucket" to bucket, "n" to ys.size, "hit_rate" to ((acc(ys) as? JsonPrimitive)?.content?.toDoubleOrNull() ?: 0.0))
            }
            val brier = if (xs.isEmpty()) null else xs.sumOf { val c = it.dbl("confidence"); if (it["correct"]?.jsonPrimitive?.booleanOrNull == true) (1 - c) * (1 - c) else c * c } / xs.size
            return jo(
                "window" to window, "n" to xs.size, "accuracy" to acc(xs), "baseline_accuracy" to acc(xs.filter { it.str("method") == "baseline" }),
                "model_accuracy" to acc(xs.filter { it.str("method") == "model" }), "brier" to brier?.let { Math.round(it * 1000) / 1000.0 },
                "by_kind" to JsonObject(byKind), "calibration" to ja(calibration),
            )
        }
        edit("/digital-ceo") { it + mapOf("stats" to ja(listOf("30d", "90d", "all").map(::stats)), "hidden" to JsonPrimitive(rows.count { r -> (r["seen_before"] as? JsonPrimitive)?.booleanOrNull != true })) }
    }

    private fun settings18(): JsonObject = store["/owner/settings"]?.second as? JsonObject ?: JsonObject(emptyMap())

    // ---- decisions
    private fun decisionOf(ref: String): JsonObject? =
        store["/decisions/$ref"]?.second as? JsonObject ?: list("/decisions?status=all").map { it.jsonObject }.firstOrNull { it.str("ref") == ref }

    private fun saveDecision(d: JsonObject) {
        val ref = d.str("ref") ?: return
        store["/decisions/$ref"] = 200 to d
        replaceIn("/decisions?status=all", ref, d)
        store["/decisions?status=pending"] = 200 to page(list("/decisions?status=all").filter { it.jsonObject.str("status") == "pending" })
    }

    /** What deciding a card does for §21: the prediction revealed, no more waiting, a memo still writing goes stale, an approved
     *  evaluation changes the employee, the HR round closes once its cards are decided, and the accuracy is recounted. */
    private fun decided18(d0: JsonObject): JsonObject {
        val ref = d0.str("ref") ?: return d0
        saveMemos(memos().map { m -> if (m.str("decision") == ref && m.str("state") == "writing") m.with("state" to "stale").also { memoReady.remove(m.str("ref")) } else m })
        var d = d0.with("digital_ceo_prediction" to brief(d0), "waiting_h" to null, "memos" to memoBriefs(ref))
        if (d.str("kind") == "evaluation" && d.str("status") == "approved") {
            val p = d.obj("payload")
            val code = p.str("employee")
            val change = p["change"] as? JsonObject
            if (code != null) {
                fun change(e: JsonObject): JsonObject {
                    var x = e
                    if (change != null) x = x.with("title_fa" to (change.str("title_fa") ?: e.str("title_fa")), "model" to JsonObject(e.obj("model") + listOfNotNull(change["model"]?.let { "model" to it }, change["effort"]?.let { "effort" to it })))
                    if (p.str("recommendation") == "confirm") x = x.with("probation_until" to null)
                    return x
                }
                (store["/employees/$code"]?.second as? JsonObject)?.let { store["/employees/$code"] = 200 to change(it) }
                for (k in store.keys.filter { it == "/employees" || it.startsWith("/employees?") }) update(k, code, idKey = "code") { change(it) }
            }
        }
        saveDecision(d)
        val all = list("/decisions?status=all").map { it.jsonObject }
        store["/hr/rounds"] = 200 to ja(list("/hr/rounds").map { r0 ->
            val r = r0.jsonObject
            val refs = r["decisions"]?.jsonArray?.map { it.jsonPrimitive.content }.orEmpty()
            if (ref in refs && refs.all { x -> all.firstOrNull { it.str("ref") == x }?.str("status") != "pending" }) r.with("state" to "done") else r
        })
        scored(d)
        d = decisionOf(ref) ?: d
        return d
    }

    // ---- memos (§21.1)
    private fun memos(): List<JsonObject> = list("/advisor/memos").map { it.jsonObject }
    private fun saveMemos(xs: List<JsonObject>) { store["/advisor/memos"] = 200 to page(xs) }
    private fun memoBriefs(ref: String) = ja(memos().filter { it.str("decision") == ref }.map { m -> jo("ref" to m["ref"], "mode" to m["mode"], "state" to m["state"]) })
    private val REC_FA = mapOf("approve" to "تأیید", "reject" to "رد", "return" to "برگشت", "ask" to "اول بپرس")

    private fun option(t: String, pros: String, cons: String) = jo("title_fa" to t, "pros_md" to pros, "cons_md" to cons)
    private fun risk(t: String, l: String, i: String, m: String) = jo("title_fa" to t, "likelihood" to l, "impact" to i, "mitigation_fa" to m)
    private fun strs(vararg xs: String) = ja(xs.map(::JsonPrimitive))

    private fun cannedMemo(d: JsonObject, mode: String): JsonObject {
        val deploy = d.str("kind") == "deploy"
        val evaln = d.str("kind") == "evaluation"
        val riskNote = d.str("risk_note")
        if (mode == "devil") return jo(
            "summary_fa" to "چرا نه: «${d.str("title")}» را ${if (deploy) "امروز" else "به همین شکل"} مُهر نکن، مگر جواب پرسش‌های زیر را بگیری.",
            "recommendation" to "reject", "confidence" to 0.58,
            "options" to ja(listOf(option("رد با دلیل", "هیچ اثر برگشت‌ناپذیری نمیماند.", "کار پیشنهاددهنده یک دور عقب میافتد."), option("برگشت با یادداشت", "همان کار با شرط روشن دوباره میاید.", "یک روز وقت."))),
            "against_md" to when {
                deploy -> "- **ساعت انتشار:** پنجره‌ی CE-0002 در ساعت پربار پرو-چارت است؛ بازگشت خودکار ۴ دقیقه طول میکشد.\n- **یافته‌ی باز:** FI-0009 (تغییر پیکربندی بی‌مُهر) هنوز بسته نشده و H-0002 روی همین انتشار است.\n- **تست بار:** هیچ تست باری روی ۳۰ روز داده‌ی ۱ دقیقه‌ای اجرا نشده؛ ۲۸۶ تست سبز همه واحدی‌اند."
                evaln -> "- **یک خروجی درخشان:** نیمی از امتیاز این ماه از یک گزارش (O-000031) است.\n- **هزینه:** Sonnet تقریباً دو برابر Haiku است و کار سئوی فنی هنوز با Haiku خوب انجام شده.\n- **جایگزین:** میشود effort را بالا برد بی‌آنکه مدل عوض شود."
                else -> "- شاهد این کارت به یک منبع تکیه دارد.\n- اثرش در ۳۰ روز اندازه‌پذیر نیست.\n- ${riskNote ?: "ریسکش در کارت نوشته نشده."}"
            },
            "risks" to ja(listOf(risk(if (deploy) "قطع ثبت‌نام در بازگشت خودکار" else "هزینه‌ی بیشتر بی‌نتیجه‌ی اندازه‌پذیر", "medium", if (deploy) "high" else "medium", if (deploy) "انتشار در ساعت کم‌بار" else "آزمون ۳۰ روزه پیش از تعهد ماهانه"))),
            "questions" to if (deploy) strs("تست بار کی و روی چه داده‌ای اجرا شد؟", "چرا پنجره‌ی انتشار ساعت پربار است؟") else strs("اگر این تصمیم نتیجه نداد، از کجا میفهمیم و کی برمیگردیم؟"),
        )
        if (deploy) return jo(
            "summary_fa" to "انتشار ترمینال پرو-چارت با ۲۸۶ تست سبز و canary ۱۰٪. بیشتر diff بازنویسی cache نمودار و انتقال decode به worker است؛ ریسک اصلی بازگشت ۴ دقیقه‌ای در ساعت پربار است.",
            "recommendation" to "approve", "confidence" to 0.72,
            "options" to ja(listOf(
                option("مُهر الان، canary ۱۰٪", "کندی ۲٫۴ ثانیه‌ای نمودار از امروز برطرف میشود.", "پنجره‌ی CE-0002 در ساعت پربار است."),
                option("مُهر با پنجره‌ی کم‌بار (۰۲:۰۰ تا ۰۴:۰۰)", "اگر canary شکست بخورد، کمتر از ۲۰ کاربر میبینند.", "یک شب دیرتر."),
                option("برگشت برای تست بار", "ریسک cache روی داده‌ی واقعی سنجیده میشود.", "دست‌کم دو روز عقب میافتد."),
            )),
            "against_md" to "- `src/chart/cache.ts` ۹۶ خط حذف دارد و هیچ تست باری روی داده‌ی ۳۰ روزه ندارد.\n- یافته‌ی FI-0009 روی همین سرور هنوز باز است.\n- بازبینی دوم GPT یک یافته‌ی تأییدشده دارد: کلیدهای قدیمی cache پاک نمیشوند.",
            "risks" to ja(listOf(
                risk("بازگشت خودکار ۴ دقیقه در ساعت پربار", "low", "high", "پنجره‌ی کم‌بار"),
                risk("ماندن cache قدیمی در مرورگر کاربران", "medium", "medium", "پاک‌سازی یک‌باره‌ی کلیدهای v2 در شروع"),
            )),
            "questions" to strs("تست بار روی داده‌ی ۳۰ روزه‌ی ۱ دقیقه‌ای اجرا شده؟", "اگر canary شکست بخورد، کاربران پرو در آن ۴ دقیقه چه میبینند؟"),
        )
        return jo(
            "summary_fa" to "${d.str("title")}: ${if (evaln) "پرچم قاعده‌محور و شاهد کافی دارد؛ هزینه‌ی تازه در پاکت جا میشود." else "شاهد کارت با سوابق میخواند و برگشت‌پذیر است."}",
            "recommendation" to if (d.str("risk") == "low" || evaln) "approve" else "ask", "confidence" to if (evaln) 0.68 else 0.63,
            "options" to ja(listOf(
                option("مُهر همین‌طور", "کار از امروز جلو میرود.", riskNote ?: "هزینه‌ی برآوردشده خرج میشود."),
                option(if (evaln) "ارتقا با effort بالاتر، بی‌تغییر مدل" else "برگشت با شرط روشن", "هزینه کمتر.", "شاید همان نتیجه را ندهد."),
            )),
            "against_md" to if (evaln) "- نیمی از امتیاز این ماه از یک گزارش است.\n- Sonnet تقریباً دو برابر Haiku خرج دارد." else "- اثرش هنوز سنجیده نشده؛ تا بازبینی ۳۰ روزه معلوم نیست.",
            "risks" to ja(listOf(risk(if (evaln) "هزینه‌ی بیشتر بی‌بهبود کیفیت" else "نتیجه‌ی کمتر از انتظار", "medium", "low", "بازبینی در دور ارزیابی ماه بعد"))),
            "questions" to strs(if (evaln) "کدام کار این ماه با Haiku انجام نشد یا ضعیف شد؟" else "سنجه‌ی موفقیت و تاریخش چیست؟"),
        )
    }

    private fun opinion(player: String, model: String, rec: String, confidence: Double, summary: String, differences: List<String>, base: String) =
        jo("player" to player, "model" to model, "recommendation" to rec, "confidence" to confidence, "summary_fa" to summary, "differences" to ja(differences.map(::JsonPrimitive)), "agrees" to (rec == base))

    /** One call on a player's seat under its daily cap (§21.13); over it, or the player not ready, the seat is skipped and counted. */
    private fun takeSeat(player: String, seatKey: String): Boolean {
        var ok = false
        store["/substitutes"] = 200 to ja(list("/substitutes").map { e ->
            val s = e.jsonObject
            if (s.str("player") != player) return@map s
            val seat = s.arr("seats").firstOrNull { it.str("seat") == seatKey }
            val month = s.obj("month")
            ok = seat != null && seat["enabled"]?.jsonPrimitive?.booleanOrNull == true && s.str("status") == "ready" &&
                (seat.str("via") != "web" || s.obj("web").str("state") == "signed_in") && seat.int("used_today") < seat.int("per_day")
            if (!ok) return@map s.with("month" to month.with("skipped" to month.int("skipped") + 1))
            s.with(
                "seats" to ja(s.arr("seats").map { x -> if (x.str("seat") == seatKey) x.with("used_today" to x.int("used_today") + 1) else x }),
                "month" to month.with("calls" to month.int("calls") + 1),
            )
        })
        return ok
    }

    private fun attachOpinions(m: JsonObject, d: JsonObject): JsonObject {
        if (m.str("mode") != "standard") return m
        val rec = m.str("recommendation").orEmpty()
        fun generic(player: String, model: String) = opinion(player, model, rec, maxOf(0.5, m.dbl("confidence") - 0.05), "روی همان بسته‌ی شاهد ماسک‌شده، بی‌دیدن یادداشت مشاور: ${REC_FA[rec]}.", emptyList(), rec)
        val deploy17 = d.str("ref") == "D-000017"
        var out = m
        if (takeSeat("gpt", "advisor_second_opinion")) out = out.with("second_opinion" to if (deploy17) opinion(
            "gpt", "gpt-5.5", "return", 0.61, "تغییر خوب است ولی بدون تست بار روی داده‌ی واقعی نباید منتشر شود؛ canary ۱۰٪ ساعت پربار هم برای ترمینال زیاد است.",
            listOf("GPT تست بار را پیش‌شرط میداند؛ مشاور آن را با پنجره‌ی کم‌بار جبران میکند.", "GPT به canary ۵٪ رأی میدهد، مشاور ۱۰٪."), rec,
        ) else generic("gpt", "gpt-5.5"))
        if (takeSeat("deepseek", "third_opinion")) out = out.with("third_opinion" to if (deploy17) opinion(
            "deepseek", "deepseek-v3.2", "approve", 0.66, "با canary و بازگشت خودکار، ریسک پذیرفتنی است؛ فقط پنجره را به ساعت کم‌بار ببرید.", listOf("DeepSeek هم پنجره‌ی کم‌بار را شرط میکند."), rec,
        ) else generic("deepseek", "deepseek-v3.2"))
        return out
    }

    // ---- ask the hub (§21.2)
    private class Rule(val re: Regex, val answer: String, val citations: String, val notIndexed: List<String> = emptyList())
    private val CORPUS = listOf(
        Rule(Regex("گزارش روزانه|خاموش|مدیرعامل‌ها"), "گزارش روزانه‌ی مدیرعامل‌ها با مصوبه‌ی **M-0006** خاموش ماند: «تا وقتی استخدام باز نشده، گزارش صبحگاهی هلدینگ کافی است.» این از گفت‌وگوی تو با مشاور در A-0003 آمد.",
            """[{"kind":"resolution","ref":"M-0006","snippet":"تا وقتی استخدام باز نشده، گزارش روزانه‌ی مدیرعامل‌ها خاموش میماند."},{"kind":"message","ref":"A-0003","snippet":"استخدام SRE برای هر سه شرکت لازم است؟"}]"""),
        Rule(Regex("حداقل موجودی|VIP|100 ?USDT", RegexOption.IGNORE_CASE), "حداقل موجودی VIP **100 USDT** است. در ربات FX در `src/bot/handlers/vip.py` (خط‌های 41 تا 58) از سیاست `vip.min_balance` خوانده میشود و مقاله‌ی KB-0003 همین عدد را میگوید. عدد ۵۰ قدیمی ربات با O-000029 اصلاح شد.",
            """[{"kind":"code","repo":"behnamjalalico/CoineProFx","path":"src/bot/handlers/vip.py","lines":[41,58],"commit":"a91c3e2","snippet":"MIN_BALANCE = policy.get(\"vip.min_balance\")  # 100 USDT\nif balance < MIN_BALANCE:\n    return await reply(msg, kb(\"KB-0003\"))"},{"kind":"doc","path":"contracts/HQ_CORE_API_v1.md","lines":[1160,1164],"snippet":"policy keys, e.g. \"vip.min_balance\""}]""",
            listOf("behnamjalalico/CoinePro-App")),
        Rule(Regex("ثبت‌?نام|کندی|ایندکس|signup", RegexOption.IGNORE_CASE), "کندی ثبت‌نام FX از جستجوی بی‌ایندکس روی `users.email` بود (۲٫۸ ثانیه). اصلاح در جلسه‌ی کد S-0004 روی شاخه‌ی `hq/S-0004` آماده است: ایندکس یکتا و حذف دو کوئری تکراری؛ در تست بار از ۲٫۹ به ۰٫۳۱ ثانیه رسید (W-000104).",
            """[{"kind":"work","ref":"W-000104","snippet":"رفع کندی ثبت‌نام"},{"kind":"code","repo":"behnamjalalico/CoineProFx","path":"alembic/versions/0042_users_email_index.py","lines":[8,24],"commit":"hq/S-0004","snippet":"op.create_index(\"ix_users_email\", \"users\", [\"email\"], unique=True)"}]"""),
        Rule(Regex("SRE|پایداری"), "برای تریدیار و FX شاهد بود (دو حادثه‌ی کندی: I-0002 و I-0005)؛ هر دو کارت استخدام (D-000014، D-000015) با بسته شدن استخدام پس گرفته شدند. برای پرو-چارت هنوز پیشنهادی نیامده.",
            """[{"kind":"decision","ref":"D-000014","snippet":"استخدام SRE تریدیار"},{"kind":"message","ref":"A-0004","snippet":"برای تریدیار و FX شاهد دارد…"}]"""),
        Rule(Regex("canary|ترمینال|انتشار|deploy", RegexOption.IGNORE_CASE), "انتشار ترمینال پرو-چارت (D-000017) با canary ۱۰٪ و بازگشت خودکار پیشنهاد شده؛ ۲۸۶ تست سبز دارد و جلسه‌ی مدیریت پرو-چارت (MT-0009) آمادگی‌اش را تأیید کرد. ناظر کل آن را با H-0002 نگه داشته تا FI-0009 روشن شود.",
            """[{"kind":"decision","ref":"D-000017","snippet":"انتشار نسخه‌ی تازه‌ی ترمینال پرو-چارت"},{"kind":"deliverable","ref":"O-000027","snippet":"ترمینال تازه با 286 تست سبز آماده‌ی انتشار است"}]"""),
        Rule(Regex("بودجه|پاکت|توکن"), "پاکت ماهانه‌ی تریدیار 6M و FX 5M توکن است؛ پرو-چارت هنوز پاکت ندارد و سقف بودجه‌اش 6M است که ۹۲٪ آن مصرف شده. مصوبه‌ی بودجه‌ها از ویرایش خزانه آمده است.",
            """[{"kind":"doc","path":"docs/OPERATING_MODEL.md","lines":[212,230],"snippet":"پاکت ماهانه‌ی هر شرکت همان سقف استخدام مدیرعامل است"}]"""),
    )

    /** An answer moves on with time: queued, searching, answering, done (or, with nothing found, done without a model). */
    private fun askState(a: JsonObject): JsonObject {
        val ref = a.str("ref") ?: return a
        if (a.str("state") == "done" || a.str("state") == "failed") return a
        val rule = askRule[ref] ?: return a
        val age = System.currentTimeMillis() - (askAt[ref] ?: 0L)
        val next = when {
            rule < 0 -> if (age > 1_200) a.with("state" to "done", "finished_at" to stamp) else a.with("state" to "searching")
            age > 4_000 -> CORPUS[rule].let { r ->
                a.with("state" to "done", "answer_md" to r.answer, "citations" to j(r.citations), "not_indexed" to strs(*r.notIndexed.toTypedArray()),
                    "usage" to jo("tokens" to 19_800, "usd" to "0.150000"), "finished_at" to stamp)
            }
            age > 1_500 -> a.with("state" to "answering")
            age > 500 -> a.with("state" to "searching")
            else -> a
        }
        if (next != a) update("/ask", ref) { next }
        return next
    }

    // ---- the clock of §21: memos finish writing, keys verify, device codes complete, creatives render
    private fun tick18() {
        val now0 = System.currentTimeMillis()
        for ((ref, v) in memoReady.toMap()) if (now0 > v.first) {
            memoReady.remove(ref)
            val m0 = memos().firstOrNull { it.str("ref") == ref } ?: continue
            val dref = m0.str("decision").orEmpty()
            val devil = m0.str("mode") == "devil"
            var m = JsonObject(m0 + v.second).with(
                "state" to "ready", "citations" to ja(listOf(jo("kind" to "decision", "ref" to dref))),
                "usage" to jo("tokens" to if (devil) 27_900 else 39_600, "usd" to if (devil) "0.590000" else "0.840000"),
            )
            decisionOf(dref)?.let { d -> m = attachOpinions(m, d) }
            saveMemos(memos().map { if (it.str("ref") == ref) m else it })
            decisionOf(dref)?.let { saveDecision(it.with("memos" to memoBriefs(dref))) }
        }
        for ((id, at) in verifying18.toMap()) if (now0 > at) {
            verifying18.remove(id)
            update("/connections", id, idKey = "id") { it.with("status" to "ready", "status_reason" to null, "updated_at" to stamp, "version" to it.int("version") + 1) }
        }
        for ((id, l) in logins.toMap()) {
            if (l.str("state") == "waiting" && l.str("method") == "device_code" && now0 - (loginAt[id] ?: now0) > 8_000) finishLogin(id)
            else if (l.str("state") == "waiting" && ms(l.str("expires_at")) < HqClock.millis()) logins[id] = l.with("state" to "expired")
        }
        if (store.containsKey("/creatives")) {
            var changed = false
            val xs = list("/creatives").map { e ->
                val x = e.jsonObject
                val ref = x.str("ref").orEmpty()
                when {
                    x.str("state") == "queued" && now0 - (creativeAt[ref] ?: now0) > 1_500 -> { changed = true; x.with("state" to "generating") }
                    x.str("state") == "generating" && creativeReady[ref]?.let { now0 > it } == true -> {
                        changed = true
                        creativeReady.remove(ref)
                        x.with(
                            "state" to "review", "source" to jo("player" to x["player"], "model" to x["model"], "at" to stamp), "updated_at" to stamp, "version" to x.int("version") + 1,
                            "review_md" to "مدیر مارکتینگ ${nameOf(x.str("company"))}: با brief میخواند؛ تصویر بی‌متن است و متن فارسی در حاشیه‌ی امن ${x.str("placement")} نشسته.",
                        )
                    }
                    else -> x
                }
            }
            if (changed) store["/creatives"] = 200 to page(xs)
        }
    }

    private fun finishLogin(id: String) {
        val l = logins[id] ?: return
        logins[id] = l.with("state" to "done")
        store["/substitutes"] = 200 to ja(list("/substitutes").map { e ->
            val s = e.jsonObject
            if (s.str("connection") != l.str("connection")) return@map s
            var x = s.with("login" to s.obj("login").with("state" to "signed_in", "since" to stamp, "last_ok_at" to stamp), "version" to s.int("version") + 1)
            if (s.str("status") == "off") x = x.with("status" to "ready", "status_reason" to null)
            x
        })
    }

    // ---- creatives (§21.13)
    private fun fileRef(f: File, name: String, size: Pair<Int, Int>) = jo(
        "id" to Uri.fromFile(f).toString(), "name" to name, "mime" to "image/jpeg", "size" to f.length(), "sha256" to "demo", "kind" to "image", "status" to "ready",
        "width" to size.first, "height" to size.second, "variants" to JsonObject(emptyMap()),
    )

    /** The finished picture and the one composed with its overlay, drawn once into the cache. */
    private fun rendered(x: JsonObject): JsonObject {
        if (x.str("state") in setOf("failed", "generating", "queued") || x.arr("files").isNotEmpty()) return x
        val ref = x.str("ref") ?: return x
        val company = x.str("company").orEmpty()
        val placement = x.str("placement").orEmpty()
        val seed = DemoArt.seedOf(ref)
        val dir = File(context.cacheDir, "demo-creatives")
        return runCatching {
            val raw = File(dir, "$ref-${x.str("player")}.jpg")
            val rawSize = DemoArt.render(context, company, placement, seed, null, raw)
            val o = x["overlay"] as? JsonObject
            var out = x.with("files" to ja(listOf(fileRef(raw, raw.name, rawSize))))
            if (o != null) {
                val comp = File(dir, "$ref-composed.jpg")
                val size = DemoArt.render(context, company, placement, seed, DemoArt.Overlay(o.str("title_fa").orEmpty(), o.str("body_fa"), o.str("cta_fa"), o["mark"]?.jsonPrimitive?.booleanOrNull == true), comp)
                out = out.with("composed" to fileRef(comp, comp.name, size))
            }
            update("/creatives", ref) { out }
            out
        }.getOrDefault(x)
    }

    private fun creativesAll(): List<JsonObject> = list("/creatives").map { rendered(it.jsonObject) }

    // ---- reads
    private fun v18Read(path: String, q: Map<String, String?>): Reply? {
        fun has(o: JsonObject, k: String) = q[k] == null || o.str(k) == q[k]
        when (path) {
            "/advisor/memos" -> return Reply(200, page(memos().filter { q["decision"] == null || it.str("decision") == q["decision"] }))
            "/advisor/triggers" -> return Reply(200, ja(list("/advisor/triggers").map { it.jsonObject }.filter { has(it, "kind") && (q["since"] == null || it.str("fired_at").orEmpty() >= q["since"]!!) }))
            "/ask" -> return Reply(200, page(list("/ask").map { askState(it.jsonObject) }))
            "/reviews/weekly" -> return Reply(200, ja(list("/reviews/weekly")))
            "/reviews/weekly/current" -> return list("/reviews/weekly").firstOrNull()?.let { Reply(200, it) } ?: gone18("هنوز مروری نیست.")
            "/briefings" -> return Reply(200, page(list("/briefings").map { it.jsonObject }.filter { has(it, "kind") && has(it, "company") }))
            "/briefings/latest" -> return list("/briefings").map { it.jsonObject }.firstOrNull { it.str("kind") == (q["kind"] ?: "morning") && has(it, "company") }?.let { Reply(200, it) } ?: gone18("هنوز گزارشی نیست.")
            "/rankings/departments" -> {
                val p = if (q["period"] == "week") "week" else "month"
                return Reply(200, ja(list("/rankings/departments?period=$p").map { it.jsonObject }.filter { has(it, "company") }.sortedByDescending { it.dbl("score") }))
            }
            "/hr/rounds" -> return Reply(200, ja(list("/hr/rounds").map { it.jsonObject }.filter { has(it, "company") && has(it, "month") }))
            "/treasury/waste" -> {
                val co = q["company"]
                val all = list(if (co == null) "/treasury/waste" else "/treasury/waste?company=$co").map { it.jsonObject }
                if (q["from"] != null && q["to"] != null) return Reply(200, ja(all.filter { it.str("day").orEmpty() in q["from"]!!..q["to"]!! }.sortedBy { it.str("day") }))
                val day = q["day"] ?: all.maxOfOrNull { it.str("day").orEmpty() }
                return all.firstOrNull { it.str("day") == day }?.let { Reply(200, it) } ?: gone18("هدررفت آن روز هنوز حساب نشده؛ هر روز ۰۷:۴۵ برای دیروز.")
            }
            "/treasury/roi" -> {
                val by = q["by"] ?: "company"
                val p = if (q["period"] == "week") "week" else "month"
                return Reply(200, ja(list("/treasury/roi?by=$by&period=$p").map { it.jsonObject }.filter { r ->
                    has(r, "company") && (q["key"] == null || r.str("key") == q["key"] || r.str("key").orEmpty().endsWith("-${q["key"]}"))
                }))
            }
            "/notes" -> {
                val text = q["q"]?.trim().orEmpty()
                return Reply(200, page(list("/notes").map { it.jsonObject }.filter { n ->
                    has(n, "status") && (text.isEmpty() || "${n.str("text_md")} ${n["tags"]?.jsonArray?.joinToString(" ") { it.jsonPrimitive.content }} ${n.str("ref")}".contains(text))
                }.sortedByDescending { ms(it.str("created_at")) }))
            }
            "/claims" -> return Reply(200, page(list("/claims").map { it.jsonObject }.filter { has(it, "company") && has(it, "employee") && has(it, "verdict") }))
            "/runs/health" -> {
                val p = if (q["period"] == "30d") "30d" else "7d"
                return Reply(200, page(list("/runs/health?period=$p").map { it.jsonObject }.filter { has(it, "company") }.map { it.with("period" to p) }))
            }
            "/digital-ceo" -> return Reply(200, (store["/digital-ceo"]!!.second.jsonObject).with("settings" to (settings18()["digital_ceo"] ?: JsonObject(emptyMap()))))
            "/digital-ceo/predictions" -> return Reply(200, page(list("/digital-ceo/predictions").map { it.jsonObject }.filter { r ->
                (q["correct"] == null || r["correct"]?.jsonPrimitive?.content == q["correct"]) && has(r, "kind")
            }))
            "/creatives" -> return Reply(200, page(creativesAll().filter { has(it, "company") && has(it, "state") && has(it, "kind") }.sortedByDescending { ms(it.str("created_at")) }))
        }
        Regex("^/decisions/(D-\\d+)/memo$").find(path)?.let { m ->
            val mode = q["mode"] ?: "standard"
            return memos().firstOrNull { it.str("decision") == m.groupValues[1] && it.str("mode") == mode }?.let { Reply(200, it) } ?: gone18("برای این کارت هنوز یادداشتی نوشته نشده.")
        }
        Regex("^/decisions/(D-\\d+)/diff$").find(path)?.let { m ->
            val file = q["file"].orEmpty()
            store["$path?file=$file"]?.let { return Reply(it.first, it.second) }
            val f = decisionOf(m.groupValues[1])?.obj("payload")?.obj("diff")?.arr("files")?.firstOrNull { it.str("path") == file } ?: return gone18("این فایل در diff این کارت نیست.")
            return Reply(200, f.with("truncated" to false))
        }
        Regex("^/ask/(AK-\\d+)$").find(path)?.let { m -> return list("/ask").map { it.jsonObject }.firstOrNull { it.str("ref") == m.groupValues[1] }?.let { Reply(200, askState(it)) } ?: gone18("این پرسش پیدا نشد.") }
        Regex("^/briefings/(BR-\\d+)$").find(path)?.let { m -> return list("/briefings").map { it.jsonObject }.firstOrNull { it.str("ref") == m.groupValues[1] }?.let { Reply(200, it) } ?: gone18("این گزارش پیدا نشد.") }
        Regex("^/hr/rounds/(HR-\\d+)$").find(path)?.let { m -> return list("/hr/rounds").map { it.jsonObject }.firstOrNull { it.str("ref") == m.groupValues[1] }?.let { Reply(200, it) } ?: gone18("این دور ارزیابی پیدا نشد.") }
        Regex("^/connections/([\\w-]+)/login/([\\w-]+)$").find(path)?.let { m -> return logins[m.groupValues[2]]?.let { Reply(200, it) } ?: gone18("این ورود پیدا نشد.") }
        Regex("^/creatives/(CR-\\d+)$").find(path)?.let { m -> return list("/creatives").map { it.jsonObject }.firstOrNull { it.str("ref") == m.groupValues[1] }?.let { Reply(200, rendered(it)) } ?: gone18("این درخواست پیدا نشد.") }
        return null
    }

    // ---- writes
    private fun v18Write(method: String, path: String, raw: JsonElement?, version: Int?, idempotency: String?, stepUp: String?): Reply? {
        val b = raw as? JsonObject ?: JsonObject(emptyMap())
        fun keyed(r: Reply): Reply = r.also { if (!idempotency.isNullOrEmpty()) replies[idempotency] = it }
        // ---- the advisor's devil mode lives in thread A only (§21.1)
        Regex("^/threads/([^/]+)/messages$").find(path)?.let { m ->
            val mode = b.str("mode") ?: return null
            if (m.groupValues[1] != "A" || mode != "devil") return Reply(422, problem16(422, "validation_failed", "حالت مخالف‌خوان فقط در رشته‌ی مشاور کل است.", jo("fields" to jo("mode" to "thread A only"))))
            return null
        }
        if (path == "/owner/settings" && method == "PUT") {
            val s = settings18()
            unmatched(version, s.int("version"))?.let { return it }
            val next = JsonObject(s + b.mapValues { (k, v) -> val cur = s[k]; if (v is JsonObject && cur is JsonObject) JsonObject(cur + v) else v } + ("version" to JsonPrimitive(s.int("version") + 1)))
            store["/owner/settings"] = 200 to next
            return Reply(200, next)
        }
        // ---- §21.1 a memo
        Regex("^/decisions/(D-\\d+)/memo$").find(path)?.let { m ->
            if (method != "POST") return null
            val d = decisionOf(m.groupValues[1]) ?: return gone18("این کارت پیدا نشد.")
            if (d.str("status") != "pending") return Reply(409, problem16(409, "decision_not_pending", "این کارت دیگر منتظر تصمیم نیست."))
            val mode = b.str("mode") ?: "standard"
            if (mode != "standard" && mode != "devil") return bad("حالت یادداشت standard یا devil است.")
            val old = memos().firstOrNull { it.str("decision") == d.str("ref") && it.str("mode") == mode && it.int("decision_version") == d.int("version") && it.str("state") != "failed" }
            val x = old ?: run {
                val n = (memos().mapNotNull { it.str("ref")?.substringAfter('-')?.toIntOrNull() }.maxOrNull() ?: 0) + 1
                val ref = pad("DM-", n, 4)
                val made = jo(
                    "id" to "dm$n", "ref" to ref, "decision" to d.str("ref"), "decision_version" to d.int("version"), "mode" to mode, "state" to "writing", "trigger" to "owner",
                    "summary_fa" to "", "recommendation" to "ask", "confidence" to 0.0, "options" to ja(emptyList()), "against_md" to "", "risks" to ja(emptyList()), "questions" to ja(emptyList()),
                    "citations" to ja(emptyList()), "usage" to jo("tokens" to 0, "usd" to "0.000000"), "second_opinion" to null, "third_opinion" to null, "created_at" to stamp,
                )
                memoReady[ref] = System.currentTimeMillis() + 5_000 to cannedMemo(d, mode)
                saveMemos(listOf(made) + memos())
                made
            }
            saveDecision(d.with("memos" to memoBriefs(d.str("ref")!!)))
            return Reply(202, x)
        }
        // ---- §21.2 ask
        if (path == "/ask" && method == "POST") {
            replies[idempotency.orEmpty()]?.let { return it }
            val text = b.str("q")?.trim().orEmpty()
            if (text.isEmpty()) return Reply(422, problem16(422, "validation_failed", "پرسش خالی است.", jo("fields" to jo("q" to "required"))))
            if (text.length > 500) return Reply(422, problem16(422, "validation_failed", "پرسش حداکثر ۵۰۰ نویسه است.", jo("fields" to jo("q" to "max 500"))))
            val rule = CORPUS.indexOfFirst { it.re.containsMatchIn(text) }
            val n = list("/ask").size + 1
            val ref = pad("AK-", n, 4)
            val a = jo(
                "id" to "ak$n", "ref" to ref, "q" to text, "scope" to (b["scope"] ?: JsonNull), "state" to "queued", "found" to if (rule >= 0) 6 + DemoArt.seedOf(text) % 9 else 0,
                "answer_md" to if (rule >= 0) null else "چیزی پیدا نشد. در مصوبه‌ها، تصمیم‌ها، خروجی‌ها، پیام‌ها، سندها و کد چیزی درباره‌ی «${text.take(40)}» نیست؛ مدلی هم اجرا نشد. کلیدواژه‌ی دیگری امتحان کن.",
                "citations" to ja(emptyList()), "not_indexed" to ja(emptyList()), "usage" to jo("tokens" to 0, "usd" to "0.000000"), "created_at" to stamp, "finished_at" to null,
            )
            askRule[ref] = rule
            askAt[ref] = System.currentTimeMillis()
            prepend("/ask", a)
            return keyed(Reply(202, a))
        }
        // ---- §21.3 the weekly review
        Regex("^/reviews/weekly/(WR-\\d+)/(start|finish|items/(\\d+))$").find(path)?.let { m ->
            val all = list("/reviews/weekly").map { it.jsonObject }
            val r = all.firstOrNull { it.str("ref") == m.groupValues[1] } ?: return gone18("این مرور پیدا نشد.")
            fun save(x: JsonObject): Reply { store["/reviews/weekly"] = 200 to ja(all.map { if (it.str("ref") == x.str("ref")) x else it }); return Reply(200, x) }
            when (m.groupValues[2]) {
                "start" -> {
                    if (r.str("state") != "ready") return Reply(409, problem16(409, "validation_failed", "این مرور شروع‌شدنی نیست."))
                    return save(r.with("state" to "in_progress", "started_at" to stamp, "version" to r.int("version") + 1))
                }
                "finish" -> {
                    if (r.str("state") != "in_progress") return Reply(409, problem16(409, "validation_failed", "مرور شروع نشده."))
                    val items = r.arr("agenda")
                    val o = jo(
                        "id" to "o-O-000048", "ref" to "O-000048", "company" to "HQ", "title" to "صورت‌جلسه‌ی مرور هفتگی ${r.str("ref")}",
                        "summary" to "${items.count { it.str("status") == "done" }} مورد انجام شد، ${items.count { it.str("status") == "deferred" }} مورد عقب افتاد.",
                        "body" to items.joinToString("\n") { i -> "- ${i.str("title_fa")}: ${i.str("status")}${i.str("owner_note")?.let { " ($it)" }.orEmpty()}" },
                        "producer" to jo("code" to "HQ-ADV", "company" to "HQ", "kind" to "advisor", "department" to null, "title_fa" to "مشاور کل"),
                        "rating" to null, "created_at" to stamp, "work_ref" to null, "attachments" to ja(emptyList()), "evidence" to ja(emptyList()),
                        "produced_with" to jo("model" to "claude-opus-5-5", "effort" to "xhigh", "label_fa" to "Opus 5.5 · xhigh"), "usage" to jo("tokens" to 0, "usd" to "0.00"), "work_id" to null,
                    )
                    store["/deliverables/O-000048"] = 200 to o
                    prepend("/deliverables", o)
                    val started = ms(r.str("started_at"))
                    return save(r.with("state" to "done", "finished_at" to stamp, "duration_s" to ((HqClock.millis() - started) / 1000).coerceAtLeast(0), "minutes_ref" to "O-000048", "version" to r.int("version") + 1))
                }
                else -> {
                    if (method != "PATCH") return null
                    unmatched(version, r.int("version"))?.let { return it }
                    val n = m.groupValues[3].toInt()
                    if (r.arr("agenda").none { it.int("n") == n }) return gone18("این مورد در دستور نیست.")
                    val st = b.str("status")
                    if (st != null && st !in setOf("open", "done", "deferred")) return bad("وضعیت نامعتبر.")
                    val agenda = r.arr("agenda").map { i ->
                        if (i.int("n") != n) i else {
                            var x = i
                            if (st != null) x = x.with("status" to st)
                            if (b.containsKey("owner_note")) x = x.with("owner_note" to b.str("owner_note")?.ifBlank { null })
                            x
                        }
                    }
                    return save(r.with("agenda" to ja(agenda), "version" to r.int("version") + 1))
                }
            }
        }
        // ---- §21.7 a new connection
        if (path == "/connections" && method == "POST") {
            if (stepUp == null) return stepUpMissing()
            if (idempotency.isNullOrEmpty()) return bad("Idempotency-Key لازم است.")
            replies[idempotency]?.let { return it }
            val all = list("/connections").map { it.jsonObject }
            val key = b.str("key").orEmpty()
            val provider = b.str("provider").orEmpty()
            val base = b.str("base_url")
            if (!Regex("^[a-z0-9][a-z0-9-]{2,39}$").matches(key)) return Reply(422, problem16(422, "validation_failed", "کلید فقط حروف کوچک لاتین، عدد و خط تیره است.", jo("fields" to jo("key" to "pattern"))))
            if (all.any { it.str("key") == key }) return Reply(409, problem16(409, "version_conflict", "اتصالی با همین کلید هست."))
            if (provider !in setOf("anthropic", "openai", "google", "deepseek", "mistral", "openai_compatible")) return Reply(422, problem16(422, "validation_failed", "مسیریاب این ارائه‌دهنده را نمیشناسد.", jo("fields" to jo("provider" to "unsupported"))))
            if (base != null && (provider != "openai_compatible" || !base.startsWith("https://") || Regex("//(localhost|127\\.|10\\.|192\\.168\\.|172\\.(1[6-9]|2\\d|3[01])\\.)").containsMatchIn(base)))
                return Reply(422, problem16(422, "validation_failed", "نشانی پایه فقط برای سازگار با OpenAI، با https و نه نشانی خصوصی.", jo("fields" to jo("base_url" to "egress guard"))))
            val models = b["models"] as? JsonArray
            if (models.isNullOrEmpty()) return Reply(422, problem16(422, "validation_failed", "دست‌کم یک مدل لازم است.", jo("fields" to jo("models" to "required"))))
            val c = jo(
                "id" to "c${all.size + 1}", "key" to key, "display_name" to b["display_name"], "kind" to b["kind"], "provider" to provider, "status" to "pending_secret", "status_reason" to "منتظر کلید",
                "models" to models, "default_model" to (b["default_model"]?.takeIf { it !is JsonNull } ?: models[0]), "fallback_priority" to b["fallback_priority"], "has_secret_ref" to false,
                "limits" to (b["limits"] ?: JsonObject(emptyMap())), "pricing" to (b["pricing"] ?: JsonObject(emptyMap())), "quota_reset_at" to null, "base_url" to base, "updated_at" to stamp, "version" to 1,
            )
            store["/connections"] = 200 to ja(all + c)
            return keyed(Reply(201, c))
        }
        Regex("^/connections/([\\w-]+)/secret$").find(path)?.let { m ->
            val c = list("/connections").map { it.jsonObject }.firstOrNull { it.str("id") == m.groupValues[1] } ?: return null
            if (c.str("status") != "pending_secret") return null
            if (stepUp == null) return stepUpMissing()
            update("/connections", c.str("id")!!, idKey = "id") {
                it.with("status" to "verifying", "status_reason" to "بررسی با فراخوانی بی‌هزینه (فهرست مدل‌ها)", "has_secret_ref" to true, "version" to it.int("version") + 1, "updated_at" to stamp)
            }
            verifying18[c.str("id")!!] = System.currentTimeMillis() + 3_500
            return Reply(200, jo("connection" to c.str("key"), "stored" to true))
        }
        // ---- §21.13 a CLI's sign-in
        Regex("^/connections/([\\w-]+)/(login|logout)$").find(path)?.let { m ->
            if (method != "POST") return null
            val c = list("/connections").map { it.jsonObject }.firstOrNull { it.str("id") == m.groupValues[1] }
            val s = list("/substitutes").map { it.jsonObject }.firstOrNull { it.str("connection") == c?.str("key") }
            if (c == null || s == null) return gone18("این اتصال پیدا نشد.")
            if (stepUp == null) return stepUpMissing()
            fun saveSub(x: JsonObject) { store["/substitutes"] = 200 to ja(list("/substitutes").map { if (it.jsonObject.str("player") == x.str("player")) x else it }) }
            if (m.groupValues[2] == "logout") {
                saveSub(s.with("login" to s.obj("login").with("state" to "signed_out", "since" to null), "status" to "off", "status_reason" to "ورود CLI پاک شد؛ جایگاه‌های CLI رد میشوند.", "version" to s.int("version") + 1))
                return Reply(200, jo("connection" to c.str("key"), "signed_out" to true))
            }
            if (s["runner"] == null || s["runner"] is JsonNull) return Reply(409, problem16(409, "not_ready", "این بازیکن CLI ندارد؛ فقط از مرورگر لاگین‌شده‌ی هاب کار میکند."))
            val gemini = s.str("player") == "gemini"
            val id = "lg${logins.size + 1}"
            val l = jo(
                "id" to id, "connection" to c.str("key"), "method" to if (gemini) "auth_code" else "device_code",
                "verification_url" to if (gemini) "https://accounts.google.com/o/oauth2/v2/auth?client_id=gemini-cli&response_type=code" else "https://auth.openai.com/codex/device",
                "user_code" to if (gemini) null else "${'A' + logins.size % 20}K7M-4TZP", "expires_at" to ahead(10), "state" to "waiting", "status_reason" to null,
            )
            logins[id] = l
            loginAt[id] = System.currentTimeMillis()
            saveSub(s.with("login" to s.obj("login").with("state" to "signing_in")))
            return Reply(201, l)
        }
        Regex("^/connections/([\\w-]+)/login/([\\w-]+)/code$").find(path)?.let { m ->
            val l = logins[m.groupValues[2]]
            if (l == null || l.str("state") != "waiting" || l.str("method") != "auth_code") return Reply(409, problem16(409, "validation_failed", "این ورود منتظر کد نیست."))
            if (b.str("code")?.trim().orEmpty().length < 6) return bad("کد کوتاه است.")
            finishLogin(m.groupValues[2])
            return Reply(200, logins.getValue(m.groupValues[2]))
        }
        // ---- §21.8 notes
        if (path == "/notes" && method == "POST") {
            replies[idempotency.orEmpty()]?.let { return it }
            val text = b.str("text_md")?.trim().orEmpty()
            if (text.isEmpty()) return bad("یادداشت خالی است.")
            val n = (list("/notes").mapNotNull { it.jsonObject.str("ref")?.substringAfter('-')?.toIntOrNull() }.maxOrNull() ?: 0) + 1
            val x = jo(
                "id" to "nt$n", "ref" to pad("NT-", n, 4), "text_md" to text, "source" to if (b.str("source") == "voice") "voice" else "text", "file_id" to b["file_id"],
                "tags" to ja(b["tags"]?.jsonArray.orEmpty().take(8)), "status" to "open", "promoted_to" to null, "created_at" to stamp, "updated_at" to stamp, "version" to 1,
            )
            prepend("/notes", x)
            return keyed(Reply(201, x))
        }
        Regex("^/notes/(NT-\\d+)(/promote)?$").find(path)?.let { m ->
            val x = list("/notes").map { it.jsonObject }.firstOrNull { it.str("ref") == m.groupValues[1] } ?: return gone18("این یادداشت پیدا نشد.")
            val count = list("/notes").size
            if (m.groupValues[2].isNotEmpty()) {
                if (x.str("status") != "open") return Reply(409, problem16(409, "validation_failed", "فقط یادداشت باز تبدیل میشود."))
                val to = b.str("to")
                if (to == "work" && b.str("company") == null) return Reply(422, problem16(422, "validation_failed", "برای کار، شرکت را انتخاب کن.", jo("fields" to jo("company" to "required"))))
                val ref = when (to) { "work" -> "W-0001${40 + count}"; "order" -> "F-00${10 + count}"; "errand" -> "E-00${10 + count}"; else -> return bad("مقصد کار، فرمان یا کار دستیار است.") }
                return Reply(200, update("/notes", x.str("ref")!!) { it.with("status" to "promoted", "promoted_to" to jo("kind" to to, "ref" to ref), "updated_at" to stamp, "version" to it.int("version") + 1) }!!)
            }
            if (method != "PATCH") return null
            unmatched(version, x.int("version"))?.let { return it }
            val st = b.str("status")
            if (st != null && st != "archived") return bad("فقط بایگانی؛ یادداشت حذف نمیشود.")
            if (b.containsKey("text_md") && b.str("text_md")?.trim().isNullOrEmpty()) return bad("یادداشت خالی نمیشود.")
            return Reply(200, update("/notes", x.str("ref")!!) { n ->
                var y = n.with("updated_at" to stamp, "version" to n.int("version") + 1)
                b.str("text_md")?.let { y = y.with("text_md" to it.trim()) }
                (b["tags"] as? JsonArray)?.let { y = y.with("tags" to ja(it.take(8))) }
                if (st != null) y = y.with("status" to st)
                y
            }!!)
        }
        // ---- §21.10 principles
        if (path == "/digital-ceo/principles" && method == "POST") {
            val text = b.str("text_fa")?.trim().orEmpty()
            if (text.isEmpty()) return bad("متن اصل خالی است.")
            val all = list("/digital-ceo/principles")
            val x = jo(
                "id" to "dp${all.size + 1}", "ref" to pad("DP-", all.size + 1, 3), "text_fa" to text, "sources" to ja(listOf(jo("kind" to "owner", "ref" to "owner"))),
                "status" to "active", "edited_by_owner" to true, "version" to 1, "updated_at" to stamp,
            )
            store["/digital-ceo/principles"] = 200 to ja(all + x)
            return Reply(201, x)
        }
        Regex("^/digital-ceo/principles/(DP-\\d+)(/accept)?$").find(path)?.let { m ->
            val x = list("/digital-ceo/principles").map { it.jsonObject }.firstOrNull { it.str("ref") == m.groupValues[1] } ?: return gone18("این اصل پیدا نشد.")
            if (m.groupValues[2].isNotEmpty()) {
                if (x.str("status") != "proposed") return Reply(409, problem16(409, "validation_failed", "فقط اصل پیشنهادی پذیرفته میشود."))
                return Reply(200, update("/digital-ceo/principles", x.str("ref")!!) { it.with("status" to "active", "version" to it.int("version") + 1, "updated_at" to stamp) }!!)
            }
            if (method != "PUT") return null
            unmatched(version, x.int("version"))?.let { return it }
            val text = b.str("text_fa")?.trim().orEmpty()
            if (text.isEmpty()) return bad("متن اصل خالی است.")
            return Reply(200, update("/digital-ceo/principles", x.str("ref")!!) {
                it.with(
                    "text_fa" to text, "status" to if (b.str("status") == "retired") "retired" else "active",
                    "edited_by_owner" to ((it["edited_by_owner"] as? JsonPrimitive)?.booleanOrNull == true || text != it.str("text_fa")), "version" to it.int("version") + 1, "updated_at" to stamp,
                )
            }!!)
        }
        // ---- §21.13 seats and the browser profile
        Regex("^/substitutes/(gpt|gemini|deepseek)/(seats|web/logout)$").find(path)?.let { m ->
            val s = list("/substitutes").map { it.jsonObject }.firstOrNull { it.str("player") == m.groupValues[1] } ?: return gone18("این بازیکن پیدا نشد.")
            if (stepUp == null) return stepUpMissing()
            fun saveSub(x: JsonObject): Reply { store["/substitutes"] = 200 to ja(list("/substitutes").map { if (it.jsonObject.str("player") == x.str("player")) x else it }); return Reply(200, x) }
            if (m.groupValues[2] == "web/logout") return saveSub(s.with("web" to s.obj("web").with("state" to "signed_out", "last_failure" to null), "version" to s.int("version") + 1))
            unmatched(version, s.int("version"))?.let { return it }
            val rows = (raw as? JsonArray)?.map { it.jsonObject } ?: return bad("فهرست جایگاه‌ها لازم است.")
            val ids = s.arr("models").mapNotNull { it.str("id") }.toSet()
            for (x in rows) {
                if (x.int("per_day") !in 0..500) return bad("سقف روزانه‌ی ${x.str("seat")} بین ۰ و ۵۰۰ است.")
                if (x.str("model") !in ids) return bad("مدل ${x.str("model")} در اتصال این بازیکن نیست.")
                if ((s["runner"] == null || s["runner"] is JsonNull) && x.str("via") == "cli") return bad("این بازیکن CLI ندارد؛ فقط وب.")
            }
            val seats = rows.map { x ->
                val old = s.arr("seats").firstOrNull { it.str("seat") == x.str("seat") }
                var y = x.with("used_today" to (old?.int("used_today") ?: 0))
                if (x["per_day_video"] != null && x["per_day_video"] !is JsonNull) y = y.with("used_today_video" to (old?.int("used_today_video") ?: 0))
                y
            }
            return saveSub(s.with("seats" to ja(seats), "version" to s.int("version") + 1))
        }
        // ---- §21.13 creatives
        if (path == "/creatives" && method == "POST") {
            replies[idempotency.orEmpty()]?.let { return it }
            val company = b.str("company")
            val brief = b.str("brief_md")?.trim().orEmpty()
            val placement = b.str("placement").orEmpty()
            val video = b.str("kind") == "video"
            if (company == null || brief.isEmpty()) return bad("شرکت و brief لازم است.")
            val aspect = DemoArt.ASPECT[placement] ?: return bad("جای انتشار نامعتبر است.")
            val duration = b.int("duration_s")
            if (video && (duration <= 0 || duration > 10)) return Reply(422, problem16(422, "validation_failed", "ویدیو حداکثر ۱۰ ثانیه است.", jo("fields" to jo("duration_s" to "≤ 10"))))
            val player = if (video) "gemini" else b.str("player") ?: settings18().obj("substitutes").str("creative_default_image") ?: "gpt"
            val s = list("/substitutes").map { it.jsonObject }.firstOrNull { it.str("player") == player }
            val seat = s?.arr("seats")?.firstOrNull { it.str("seat") == "creative" }
            val n = (list("/creatives").mapNotNull { it.jsonObject.str("ref")?.substringAfter('-')?.toIntOrNull() }.maxOrNull() ?: 0) + 1
            val ref = pad("CR-", n, 4)
            val mark = DemoArt.BRAND[company]?.mark ?: company
            var x = jo(
                "id" to "cr$n", "ref" to ref, "company" to company, "kind" to if (video) "video" else "image", "brief_md" to brief, "placement" to placement, "aspect" to aspect,
                "duration_s" to if (video) duration else null, "overlay" to (b["overlay"] ?: JsonNull), "composed" to null, "player" to player,
                "model" to (s?.arr("models")?.firstOrNull()?.str("id") ?: ""), "path" to "web", "state" to "queued", "requested_by" to owner, "work_ref" to null, "errand_ref" to null,
                "files" to ja(emptyList()), "review_md" to null, "source" to null, "ai_generated" to true,
                "prompt_md" to "Advertising ${if (video) "teaser video, $duration s" else "image"} for $mark, aspect $aspect, in the brand palette. Brief (masked): ${brief.take(160)} No text, no letters, no logos anywhere; keep the lower third calm for an overlay.",
                "created_at" to stamp, "updated_at" to stamp, "version" to 1,
            )
            when {
                s == null || s.obj("web").str("state") != "signed_in" || seat?.get("enabled")?.jsonPrimitive?.booleanOrNull != true -> x = x.with(
                    "state" to "failed",
                    "review_md" to "ساخته نشد: پروفایل وب ${if (player == "gemini") "gemini-web" else "chatgpt-web"} وارد نیست یا جایگاه creative خاموش است؛ هیچ جابه‌جایی پنهانی به بازیکن دیگر نیست.",
                )
                !video && seat.int("used_today") >= seat.int("per_day") -> return Reply(429, problem16(429, "rate_limited", "سقف روزانه‌ی عکس این بازیکن پر شده.", jo("retry_after" to 3600)), mapOf("Retry-After" to "3600"))
                else -> {
                    creativeAt[ref] = System.currentTimeMillis()
                    creativeReady[ref] = System.currentTimeMillis() + 6_000
                    if (!video) store["/substitutes"] = 200 to ja(list("/substitutes").map { e ->
                        val y = e.jsonObject
                        if (y.str("player") != player) y else y.with("seats" to ja(y.arr("seats").map { z -> if (z.str("seat") == "creative") z.with("used_today" to z.int("used_today") + 1) else z }))
                    })
                }
            }
            prepend("/creatives", x)
            return keyed(Reply(201, x))
        }
        Regex("^/creatives/(CR-\\d+)/(accept|reject)$").find(path)?.let { m ->
            val x = list("/creatives").map { it.jsonObject }.firstOrNull { it.str("ref") == m.groupValues[1] } ?: return gone18("این درخواست پیدا نشد.")
            if (x.str("state") != "review") return Reply(409, problem16(409, "validation_failed", "فقط نتیجه‌ی در بازبینی پذیرفته یا رد میشود."))
            val note = b.str("note")?.takeIf { it.isNotBlank() }
            return Reply(200, update("/creatives", x.str("ref")!!) {
                it.with(
                    "state" to if (m.groupValues[2] == "accept") "accepted" else "rejected",
                    "review_md" to if (note != null) "${it.str("review_md").orEmpty()}\n\nمالک: «$note»" else it["review_md"], "updated_at" to stamp, "version" to it.int("version") + 1,
                )
            }!!)
        }
        return null
    }

    private fun num(v: Double): String = if (v % 1.0 == 0.0) v.toLong().toString() else v.toString()

    // ------------------------------------------------------------ ⟨1.6⟩ §22 --
    // The media studio and the legal counsel (contract §22), as the web's mock-v19.ts: the fixtures hold whole lists (series, items with
    // every step, voices with their clips, the platforms' limits, role drafts, every case with its emails); the demo filters them and
    // answers every write the mock answers. What the hub does by code (the next runs of a series, its digest, the platform rules, the
    // seal bindings) is code here too, reduced to what a demo needs. The renders and voice clips are the web's demo files (assets/demo);
    // the stills are drawn once into the cache like the §21.13 creatives. Companies and accounts are data here too.
    private val referenceAt = mutableMapOf<String, Long>()
    private val counsel = buildJsonObject { put("kind", "agent"); put("code", "HQ-LGL"); put("display_fa", "مشاور حقوقی") }

    /** A file of the demo's own store (`/demo/…`, as the web serves them from public/demo): a film's poster sits beside it as `-poster.webp`. */
    private fun demoFile(req: okhttp3.Request, id: String, variant: String?): Response? {
        if (!id.startsWith("/demo/")) return null
        val name = id.removePrefix("/").let { if (variant == "poster") it.replace(Regex("\\.[a-z0-9]+$", RegexOption.IGNORE_CASE), "-poster.webp") else it }
        val bytes = runCatching { context.assets.open(name).use { it.readBytes() } }.getOrNull() ?: return null
        val mime = when (name.substringAfterLast('.').lowercase()) { "mp4" -> "video/mp4"; "m4a" -> "audio/mp4"; "webp" -> "image/webp"; else -> "application/octet-stream" }
        return Response.Builder().request(req).protocol(Protocol.HTTP_1_1).code(200).message("demo")
            .body(okio.ByteString.of(*bytes).toResponseBody(mime.toMediaType())).build()
    }

    private val BYDAY = mapOf("MO" to 1, "TU" to 2, "WE" to 3, "TH" to 4, "FR" to 5, "SA" to 6, "SU" to 7)

    /** The next runs of a simple RRULE (DAILY or WEEKLY with BYDAY, BYHOUR, BYMINUTE) in the owner's zone. */
    private fun nextRuns(rrule: String, n: Int = 3): List<String> {
        val p = rrule.split(';').mapNotNull { kv -> kv.split('=').takeIf { it.size == 2 }?.let { it[0] to it[1] } }.toMap()
        val hours = (p["BYHOUR"] ?: "9").split(',').mapNotNull { it.toIntOrNull() }
        val mins = p["BYMINUTE"]?.toIntOrNull() ?: 0
        val days = if (p["FREQ"] == "WEEKLY") (p["BYDAY"] ?: "SA").split(',').mapNotNull { BYDAY[it] } else null
        val now0 = HqClock.now()
        val today = LocalDate.ofInstant(now0, TEHRAN)
        val out = mutableListOf<String>()
        for (k in 0 until 21) {
            val day = today.plusDays(k.toLong())
            if (days != null && day.dayOfWeek.value !in days) continue
            for (h in hours) { val t = day.atTime(h, mins).toInstant(TEHRAN); if (t.isAfter(now0) && out.size < n) out += t.toString() }
            if (out.size >= n) break
        }
        return out
    }

    private fun accountOk(): Map<String, Boolean> = list("/tools/accounts").map { it.jsonObject }.associate { (it.str("key") ?: "") to (it["has_secret"]?.jsonPrimitive?.booleanOrNull == true) }

    // ---- series
    private fun seriesAll(): List<JsonObject> = list("/media/series").map { it.jsonObject }
    private fun saveSeries(x: JsonObject) { store["/media/series"] = 200 to page(seriesAll().map { if (it.str("ref") == x.str("ref")) x else it }.let { if (it.any { s -> s.str("ref") == x.str("ref") }) it else it + x }) }
    private fun seriesBody(b: JsonObject, company: String?) = jo(
        "company" to (company ?: b.str("company")), "title_fa" to b["title_fa"], "kind" to b["kind"], "targets" to b["targets"], "schedule" to b["schedule"],
        "topics" to b["topics"], "format" to b["format"], "checks" to b["checks"], "auto_publish" to b["auto_publish"], "max_per_day" to b["max_per_day"],
    )
    private fun withDigest(s: JsonObject): JsonObject = s.with("digest" to sha256(canonical(seriesBody(s, null))))
    private fun seriesOut(s: JsonObject): JsonObject {
        val live = s.str("status") == "sealed"
        return s.with("next_at" to ja(if (live) nextRuns(s.str("schedule").orEmpty()).map(::JsonPrimitive) else emptyList()), "today" to if (live) (s["today"]?.takeIf { it !is JsonNull } ?: jo("made" to 0, "published" to 0)) else null)
    }
    private fun placementProblem(kind: String, aspect: String, t: JsonObject): String? {
        val placement = t.str("placement").orEmpty()
        return when {
            t.str("account") !in accountOk().keys -> "حساب ${t.str("account")} در هاب تعریف نشده."
            placement.startsWith("telegram") != (t.str("channel") == "telegram") -> "جای انتشار با کانال نمیخواند."
            placement == "instagram_reel" && (kind != "reel" || aspect != "9:16") -> "ریلز اینستاگرام فقط برای ریلز ۹:۱۶ است."
            placement.endsWith("_story") && (kind != "story" || aspect != "9:16") -> "استوری فقط ۹:۱۶ و از نوع استوری است."
            placement == "instagram_post" && kind !in setOf("post", "carousel") -> "پست اینستاگرام برای پست یا کاروسل است."
            placement == "instagram_post" && aspect !in setOf("4:5", "1:1") -> "پست اینستاگرام ۴:۵ یا ۱:۱ است."
            else -> null
        }
    }
    private fun fieldBad(fa: String, field: String, why: String) = Reply(422, problem16(422, "validation_failed", fa, jo("fields" to jo(field to why))))
    private fun validateSeries(b: JsonObject): Reply? {
        val kind = b.str("kind").orEmpty()
        val format = b.obj("format")
        val topics = b["topics"] as? JsonObject
        return when {
            b.str("title_fa")?.trim().isNullOrEmpty() -> fieldBad("عنوان لازم است.", "title_fa", "required")
            kind !in setOf("reel", "story", "post", "carousel") -> fieldBad("نوع نامعتبر است.", "kind", "enum")
            b.arr("targets").isEmpty() -> fieldBad("دست‌کم یک جای انتشار لازم است.", "targets", "required")
            b.arr("targets").firstNotNullOfOrNull { placementProblem(kind, format.str("aspect").orEmpty(), it) } != null ->
                fieldBad(b.arr("targets").firstNotNullOf { placementProblem(kind, format.str("aspect").orEmpty(), it) }, "placement", "platform")
            !Regex("^FREQ=(DAILY|WEEKLY)(;BYDAY=(SA|SU|MO|TU|WE|TH|FR)(,(SA|SU|MO|TU|WE|TH|FR))*)?;BYHOUR=\\d{1,2};BYMINUTE=\\d{1,2}$").matches(b.str("schedule").orEmpty()) ->
                fieldBad("زمان‌بندی (RRULE) نامعتبر است.", "schedule", "rrule")
            b.int("max_per_day") !in 1..10 -> fieldBad("سقف روزانه بین ۱ و ۱۰ است.", "max_per_day", "1..10")
            (format["duration_s"] as? JsonPrimitive)?.intOrNull?.let { if (kind == "reel") it > 90 else it > 60 } == true -> fieldBad("مدت بیشتر از سقف خود پلتفرم است.", "duration_s", "platform")
            topics == null || (topics.arr("pool").isEmpty() && (topics["pool"] as? JsonArray).isNullOrEmpty() && topics.str("rule_fa")?.trim().isNullOrEmpty()) -> fieldBad("فهرست موضوع یا قاعده‌ی انتخاب موضوع لازم است.", "topics", "required")
            else -> null
        }
    }

    // ---- items
    private class Still(val title: String, val body: String?, val cta: String?, val placement: String)
    /** The stills the web paints in the browser (mock-v19 `_paint`): the hub's Persian text over the brand's art. */
    private val STILLS = mapOf(
        "MI-0018" to Still("اصطلاح روز: پیپ", "کوچک‌ترین واحد تغییر قیمت؛ در EUR/USD یعنی 0.0001", "ادامه در کانال", "instagram_story"),
        "MI-0020" to Still("اصطلاح روز: اسپرد", "فاصله‌ی قیمت خرید و فروش؛ هزینه پیش از هر سود", "ادامه در کانال", "instagram_story"),
        "MI-0012" to Still("کمپین رفرال این هفته", null, null, "other"),
        "MI-0010" to Still("ترمینال تازه‌ی پرو-چارت", "نمودار در کمتر از یک ثانیه", "امتحانش کن", "other"),
    )
    private fun itemsAll(): List<JsonObject> = list("/media/items").map { painted(it.jsonObject) }
    private fun saveItem(x: JsonObject) { store["/media/items"] = 200 to page(list("/media/items").map { e -> if (e.jsonObject.str("ref") == x.str("ref")) x else e }) }
    private fun painted(x: JsonObject): JsonObject {
        val ref = x.str("ref") ?: return x
        val still = STILLS[ref] ?: return x
        if (x["render"] != null && x["render"] !is JsonNull) return x
        return runCatching {
            val f = File(context.cacheDir, "demo-studio/$ref.jpg")
            val size = DemoArt.render(context, x.str("company").orEmpty(), still.placement, DemoArt.seedOf(ref), DemoArt.Overlay(still.title, still.body, still.cta, true), f)
            val out = x.with("render" to fileRef(f, "$ref.jpg", size))
            saveItem(out)
            out
        }.getOrDefault(x)
    }
    private fun publishNow(x: JsonObject): JsonObject {
        val rows = x.arr("publish").map { r ->
            when {
                r.str("placement") == "telegram_story" -> r.with("at" to stamp, "external_id" to "manual", "error" to null)
                r.str("error") == "account_not_configured" -> r
                else -> r.with("at" to stamp, "external_id" to (18_000 + DemoArt.seedOf(x.str("ref") + r.str("placement"))).toString(),
                    "url" to if (r.str("channel") == "telegram") "https://t.me/demo_${x.str("company")?.lowercase()}/${DemoArt.seedOf(x.str("ref").orEmpty())}" else null, "error" to null)
            }
        }
        return x.with("publish" to ja(rows), "state" to "published", "updated_at" to stamp, "version" to x.int("version") + 1,
            "state_note_fa" to if (rows.any { it["error"] != null && it["error"] !is JsonNull }) "آنچه راه رسمی داشت منتشر شد؛ جای بی‌کلید منتشر نشد." else null)
    }

    // ---- cases
    private val caseKey = Regex("^/legal/cases/LC-\\d+$")
    private fun casesAll(): List<JsonObject> = store.keys.filter { caseKey.matches(it) }.map { store[it]!!.second.jsonObject }
    private fun saveCase(c: JsonObject) { store["/legal/cases/${c.str("ref")}"] = 200 to c }
    private fun caseOut(c: JsonObject) = JsonObject(c - "emails")
    private fun lMessage(body: String, links: JsonObject) {
        val l = list("/threads/L/messages")
        val ref = pad("L-", l.size + 1, 4)
        store["/threads/L/messages"] = 200 to page(l + jo("id" to "m19-$ref", "ref" to ref, "thread" to "L", "author" to counsel, "body" to body, "kind" to "text", "attachments" to ja(emptyList()), "links" to links, "created_at" to stamp))
    }

    // ---- reads
    private fun v19Read(path: String, q: Map<String, String?>): Reply? {
        fun has(o: JsonObject, k: String) = q[k] == null || o.str(k) == q[k]
        when (path) {
            "/roles/drafts" -> return Reply(200, page(list("/roles/drafts").map { it.jsonObject }.filter { has(it, "company") && has(it, "department") && has(it, "state") }.sortedByDescending { ms(it.str("created_at")) }))
            "/media/series" -> return Reply(200, page(seriesAll().filter { has(it, "company") && has(it, "status") }.map(::seriesOut)))
            "/media/items" -> return Reply(200, page(itemsAll().filter { has(it, "company") && has(it, "series") && has(it, "state") }.sortedByDescending { ms(it.str("updated_at")) }))
            "/media/voices" -> return Reply(200, ja(list("/media/voices")))
            "/media/voices/reference" -> {
                val r = store["/media/voices/reference"]?.second as? JsonObject ?: return gone18("هنوز نمونه‌ی صدای تو ضبط نشده.")
                if (r.str("state") == "processing" && System.currentTimeMillis() - (referenceAt["r"] ?: 0L) > 4_000) store["/media/voices/reference"] = 200 to r.with("state" to "ready")
                return Reply(200, store["/media/voices/reference"]!!.second)
            }
            "/media/limits" -> return Reply(200, ja(list("/media/limits")))
            "/legal/cases" -> return Reply(200, page(casesAll().filter { has(it, "company") && has(it, "status") }.sortedByDescending { ms(it.str("updated_at")) }.map(::caseOut)))
        }
        Regex("^/roles/drafts/(RD-\\d+)$").find(path)?.let { m -> return list("/roles/drafts").map { it.jsonObject }.firstOrNull { it.str("ref") == m.groupValues[1] }?.let { Reply(200, it) } ?: gone18("این نقش پیدا نشد.") }
        Regex("^/media/items/(MI-\\d+)$").find(path)?.let { m -> return itemsAll().firstOrNull { it.str("ref") == m.groupValues[1] }?.let { Reply(200, it) } ?: gone18("این آیتم پیدا نشد.") }
        Regex("^/legal/cases/(LC-\\d+)$").find(path)?.let { m ->
            val c = store["/legal/cases/${m.groupValues[1]}"]?.second as? JsonObject ?: return gone18("این پرونده پیدا نشد.")
            return Reply(200, c.with("emails" to ja(c.arr("emails").sortedBy { ms(it.str("at")) })))
        }
        return null
    }

    // ---- writes
    private fun v19Write(method: String, path: String, b: JsonObject, version: Int?, idempotency: String?, stepUp: String?): Reply? {
        fun keyed(r: Reply): Reply = r.also { if (!idempotency.isNullOrEmpty()) replies[idempotency] = it }
        // A media_series card is sealed only on its own route, on the series digest (like a server plan, §18.8).
        Regex("^/decisions/(D-\\d+)/approve$").find(path)?.let { m ->
            if (decisionOf(m.groupValues[1])?.str("kind") == "media_series") return Reply(409, problem16(409, "validation_failed", "این کارت روی صفحه‌ی برنامه‌های انتشار، روی digest همان برنامه مُهر میشود."))
            return null
        }
        // ---- §22.1 mandate
        Regex("^/companies/([A-Z0-9]+)/departments/([A-Z]+)/mandate$").find(path)?.let { m ->
            if (method != "PUT") return null
            if (stepUp == null) return stepUpMissing()
            val key = "/companies/${m.groupValues[1]}/departments"
            val d = list(key).map { it.jsonObject }.firstOrNull { it.str("code") == m.groupValues[2] } ?: return gone18("این دپارتمان پیدا نشد.")
            unmatched(version, d.int("version").coerceAtLeast(1))?.let { return it }
            val x = b.obj("mandate")
            if (x.str("from_fa")?.trim().isNullOrEmpty() || x.str("to_fa")?.trim().isNullOrEmpty()) return fieldBad("مبدأ و مقصد لازم است.", "mandate", "from_fa, to_fa")
            val outs = (x["outputs_fa"] as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.content?.trim()?.takeIf(String::isNotEmpty) }
            if (outs.isEmpty()) return fieldBad("دست‌کم یک خروجی لازم است.", "outputs_fa", "required")
            if (x.str("model_ceiling") !in setOf("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")) return fieldBad("سقف مدل نامعتبر است.", "model_ceiling", "enum")
            val next = d.with("mandate" to x.with("outputs_fa" to ja(outs.map(::JsonPrimitive))), "identity_md" to b.str("identity_md")?.trim().orEmpty(), "version" to d.int("version").coerceAtLeast(1) + 1)
            update(key, d.str("code")!!, idKey = "code") { next }
            return Reply(200, next)
        }
        // ---- §22.5 roles
        if (path == "/roles/drafts" && method == "POST") {
            replies[idempotency.orEmpty()]?.let { return it }
            val company = b.str("company")
            val department = b.str("department")
            val brief = b.str("brief_md")?.trim().orEmpty()
            if (company == null || department == null || brief.isEmpty()) return fieldBad("شرکت، دپارتمان و شرح نقش لازم است.", "brief_md", "required")
            val n = list("/roles/drafts").size + 1
            val ref = pad("RD-", n, 4)
            val d = jo(
                "id" to "rd$n", "ref" to ref, "company" to company, "department" to department, "role" to "", "title_fa" to brief.take(40), "title_en" to "", "why_md" to "", "charter_md" to "",
                "tools" to ja(emptyList()), "model" to "", "effort" to "", "limits" to jo("steps_per_run" to 0, "tokens_per_step" to 0, "tokens_per_run" to 0),
                "eval" to jo("suite" to "", "cases" to ja(emptyList())), "state" to "drafting", "review" to null, "eval_run" to null, "approver" to null, "decision_ref" to null, "version" to 1,
                "created_at" to stamp, "activated_at" to null, "brief_md" to brief, "requested_by" to owner,
                "written_by" to if (company == "HQ") owner else agent("$company-$department-MGR", "مدیر $department ${nameOf(company)}"),
                "compared" to ja(emptyList()), "originality" to null, "hires" to 0, "retired_at" to null,
            )
            prepend("/roles/drafts", d)
            return keyed(Reply(201, d))
        }
        Regex("^/roles/drafts/(RD-\\d+)/retire$").find(path)?.let { m ->
            val d = list("/roles/drafts").map { it.jsonObject }.firstOrNull { it.str("ref") == m.groupValues[1] } ?: return gone18("این نقش پیدا نشد.")
            if (d.str("state") != "active") return Reply(409, problem16(409, "validation_failed", "فقط نقش فعال بازنشسته میشود."))
            val out = update("/roles/drafts", d.str("ref")!!) { it.with("state" to "retired", "retired_at" to stamp, "version" to it.int("version") + 1) }!!
            store["/roles"] = 200 to ja(list("/roles").filter { it.jsonObject.str("draft") != d.str("ref") })
            return Reply(200, out)
        }
        // ---- §22.2 series
        if (path == "/media/series" && method == "POST") {
            replies[idempotency.orEmpty()]?.let { return it }
            validateSeries(b)?.let { return it }
            val n = seriesAll().size + 1
            val s = withDigest(JsonObject(seriesBody(b, null) + jo(
                "id" to "sr$n", "ref" to pad("SR-", n, 4), "checks" to ja(MEDIA_CHECKS.map(::JsonPrimitive)), "status" to "draft", "sealed_at" to null, "version" to 1,
                "proposed_by" to owner, "decision_ref" to null, "items_total" to 0, "created_at" to stamp, "updated_at" to stamp, "status_note_fa" to null,
            )))
            saveSeries(s)
            return keyed(Reply(201, seriesOut(s)))
        }
        Regex("^/media/series/(SR-\\d+)(?:/(seal|pause|retire))?$").find(path)?.let { m ->
            val s = seriesAll().firstOrNull { it.str("ref") == m.groupValues[1] } ?: return gone18("این برنامه پیدا نشد.")
            val st = s.str("status")
            when (m.groupValues[2]) {
                "" -> {
                    if (method != "PUT") return null
                    unmatched(version, s.int("version"))?.let { return it }
                    validateSeries(b.with("company" to s.str("company")))?.let { return it }
                    if (st == "retired") return Reply(409, problem16(409, "validation_failed", "برنامه‌ی بازنشسته ویرایش نمیشود."))
                    var x = JsonObject(s + seriesBody(b, s.str("company")) + jo("checks" to ja(MEDIA_CHECKS.map(::JsonPrimitive)), "version" to s.int("version") + 1, "updated_at" to stamp))
                    if (st == "sealed" || st == "paused") x = x.with("status" to "proposed", "sealed_at" to null, "status_note_fa" to "ویرایش شد؛ مُهر قبلی این نسخه را نمیپوشاند و تا مُهر دوباره چیزی خودکار منتشر نمیشود.")
                    x = withDigest(x)
                    saveSeries(x)
                    return Reply(200, seriesOut(x))
                }
                "seal" -> {
                    if (stepUp == null) return stepUpMissing()
                    if (b.str("digest") != null && b.str("digest") != s.str("digest")) return Reply(409, problem16(409, "version_conflict", "برنامه بعد از دیدن تو عوض شده؛ دوباره نگاه کن و مُهر کن."))
                    if (st !in setOf("draft", "proposed", "paused")) return Reply(409, problem16(409, "validation_failed", if (st == "sealed") "همین نسخه مُهر شده است." else "برنامه‌ی بازنشسته مُهر نمیشود."))
                    val ok = accountOk()
                    val unconfigured = s.arr("targets").mapNotNull { it.str("account") }.filter { ok[it] != true }
                    val x = s.with("status" to "sealed", "sealed_at" to stamp, "version" to s.int("version") + 1, "updated_at" to stamp,
                        "status_note_fa" to if (unconfigured.isNotEmpty()) "مُهر شد؛ ${unconfigured.joinToString("، ")} هنوز کلید ندارد و تا ورودش روی آن منتشر نمیشود." else null)
                    saveSeries(x)
                    // Sealing a paused or proposed series decides its pending media_series card (§22.7).
                    for (d in list("/decisions?status=all").map { it.jsonObject }) if (d.str("kind") == "media_series" && d.str("status") == "pending" && d.obj("payload").str("series") == s.str("ref")) {
                        saveDecision(d.with("status" to "approved", "decided_at" to stamp, "decided_by" to owner, "seal" to jo("method" to "passkey_uv", "sealed_at" to stamp, "step_up_id" to "demo"), "resolution" to "M-0040", "effect_status" to "applied"))
                        bumpInbox()
                    }
                    return Reply(200, seriesOut(x))
                }
                "pause" -> {
                    if (st != "sealed") return Reply(409, problem16(409, "validation_failed", "فقط برنامه‌ی مُهرشده متوقف میشود."))
                    val x = s.with("status" to "paused", "version" to s.int("version") + 1, "updated_at" to stamp, "status_note_fa" to "مالک متوقف کرد؛ با مُهر دوباره ادامه میدهد.")
                    saveSeries(x)
                    return Reply(200, seriesOut(x))
                }
                else -> {
                    if (st == "retired") return Reply(409, problem16(409, "validation_failed", "همین حالا بازنشسته است."))
                    val x = s.with("status" to "retired", "version" to s.int("version") + 1, "updated_at" to stamp, "status_note_fa" to null)
                    saveSeries(x)
                    return Reply(200, seriesOut(x))
                }
            }
        }
        // ---- §22.2 items
        if (path == "/media/items" && method == "POST") {
            replies[idempotency.orEmpty()]?.let { return it }
            val company = b.str("company")
            val kind = b.str("kind").orEmpty()
            val brief = b.str("brief_md")?.trim().orEmpty()
            if (company == null || company == "HQ" || kind !in setOf("reel", "story", "post", "carousel", "design") || brief.length < 8) return fieldBad("شرکت، نوع و brief (دست‌کم ۸ نویسه) لازم است.", "brief_md", "required")
            val n = (list("/media/items").mapNotNull { it.jsonObject.str("ref")?.substringAfter('-')?.toIntOrNull() }.maxOrNull() ?: 0) + 1
            val x = jo(
                "id" to "mi$n", "ref" to pad("MI-", n, 4), "company" to company, "series" to b["series"], "kind" to kind, "title_fa" to brief.take(48), "state" to "scripting",
                "script" to null, "direction" to null, "composition" to null, "assets" to ja(emptyList()), "voice" to null, "render" to null, "captions" to null, "checks" to ja(emptyList()), "qc" to null,
                "publish" to ja(emptyList()), "decision_ref" to null, "ai_generated" to true, "cost" to jo("tokens" to 0, "usd" to "0.000000"), "brief_md" to brief, "topic_fa" to null,
                "deliverable_ref" to null, "version" to 1, "created_at" to stamp, "updated_at" to stamp,
                "state_note_fa" to if (kind == "design") "طراح رابط brief و ترکیب‌بندی را مینویسد؛ طراحی منتشر نمیشود و به مدیر فنی میرسد." else "یک‌باره است: آخرش همیشه کارت انتشار برای توست.",
            )
            prepend("/media/items", x)
            return keyed(Reply(201, x))
        }
        Regex("^/media/items/(MI-\\d+)/unpublish$").find(path)?.let { m ->
            val x = itemsAll().firstOrNull { it.str("ref") == m.groupValues[1] } ?: return gone18("این آیتم پیدا نشد.")
            if (x.str("state") == "held") return Reply(423, problem16(423, "held", "ناظر کل این آیتم را نگه داشته."))
            if (stepUp == null) return stepUpMissing()
            if (x.str("state") != "published") return Reply(409, problem16(409, "validation_failed", "فقط آیتم منتشرشده پایین میآید."))
            val rows = x.arr("publish").map { r -> if (r.str("channel") == "telegram" && r.str("placement") != "telegram_story") r.with("url" to null, "error" to "removed") else r.with("error" to "remove_by_hand") }
            val out = x.with("publish" to ja(rows), "state" to "rejected", "updated_at" to stamp, "version" to x.int("version") + 1,
                "state_note_fa" to if (rows.any { it.str("error") == "remove_by_hand" }) "مالک پایین آورد؛ جایی که API اجازه‌ی حذف نداد را از خود اپ پایین بیاور." else "مالک پایین آورد.")
            saveItem(out)
            return Reply(200, out)
        }
        // ---- §22.3 voices
        Regex("^/media/voices/([\\w-]+)/(score|activate)$").find(path)?.let { m ->
            val v = list("/media/voices").map { it.jsonObject }.firstOrNull { it.str("id") == m.groupValues[1] } ?: return gone18("این صدا پیدا نشد.")
            fun save(x: JsonObject): Reply { store["/media/voices"] = 200 to ja(list("/media/voices").map { if (it.jsonObject.str("id") == x.str("id")) x else it }); return Reply(200, x) }
            if (m.groupValues[2] == "score") {
                val score = (b["score"] as? JsonPrimitive)?.intOrNull
                if (score == null || score !in 1..10) return fieldBad("نمره از ۱ تا ۱۰ است.", "score", "1..10")
                if (v.arr("samples").isEmpty()) return Reply(409, problem16(409, "not_ready", "این صدا هنوز نمونه ندارد."))
                return save(v.with("owner_score" to score, "version" to v.int("version") + 1))
            }
            if (stepUp == null) return stepUpMissing()
            if (v.arr("samples").isEmpty()) return Reply(409, problem16(409, "not_ready", "این صدا هنوز اندازه‌گیری نشده؛ فعال نمیشود."))
            if (v["licence_commercial"]?.jsonPrimitive?.booleanOrNull != true && b["accept_non_commercial"]?.jsonPrimitive?.booleanOrNull != true)
                return fieldBad("لایسنس این صدا غیرتجاری است؛ فعال شدنش انتخاب صریح تو را میخواهد.", "accept_non_commercial", "required")
            store["/media/voices"] = 200 to ja(list("/media/voices").map { e -> val x = e.jsonObject; if (x.str("status") == "active") x.with("status" to "candidate") else x })
            return save(v.with("status" to "active", "version" to v.int("version") + 1))
        }
        if (path == "/media/voices/reference" && method == "POST") {
            val id = b.str("file_id") ?: return fieldBad("فایل نمونه لازم است.", "file_id", "required")
            val r = jo("file" to (files[id] ?: jo("id" to id, "name" to "owner-reference.m4a", "mime" to "audio/mp4", "size" to 0, "sha256" to "demo")), "duration_s" to (files[id]?.get("duration_s") ?: JsonPrimitive(0)),
                "created_at" to stamp, "state" to "processing", "reason_fa" to null)
            store["/media/voices/reference"] = 200 to r
            referenceAt["r"] = System.currentTimeMillis()
            return Reply(201, r)
        }
        // ---- §22.4 legal
        if (path == "/legal/cases" && method == "POST") {
            replies[idempotency.orEmpty()]?.let { return it }
            val company = b.str("company")
            val title = b.str("title_fa")?.trim().orEmpty()
            val kind = b.str("kind")
            val brief = b.str("brief_md")?.trim().orEmpty()
            if (company == null || title.isEmpty() || kind == null || brief.isEmpty()) return fieldBad("شرکت، عنوان، نوع و شرح لازم است.", "brief_md", "required")
            val n = casesAll().size + 1
            val ref = pad("LC-", n, 4)
            val c = jo(
                "id" to "lc$n", "ref" to ref, "company" to company, "title_fa" to title, "kind" to kind, "counterpart" to jo("name" to "—", "channel" to "other", "address" to null),
                "status" to "open", "opened_by" to owner, "brief_md" to brief, "created_at" to stamp, "updated_at" to stamp, "version" to 1, "deadlines" to ja(emptyList()),
                "timeline" to ja(listOf(jo("at" to stamp, "kind" to "note", "ref" to null, "summary_fa" to "پرونده باز شد؛ مشاور حقوقی بیدار شد و اول واقعیت‌ها را جمع میکند."))), "emails" to ja(emptyList()),
            )
            saveCase(c)
            lMessage("پرونده‌ی **$ref** باز شد. اول واقعیت‌ها و قاعده‌ی خود طرف مقابل را پیدا میکنم؛ هر ایمیل یا فرم، کارت مُهر توست.", jo("case" to ref))
            return keyed(Reply(201, caseOut(c)))
        }
        Regex("^/legal/cases/(LC-\\d+)/close$").find(path)?.let { m ->
            val c = store["/legal/cases/${m.groupValues[1]}"]?.second as? JsonObject ?: return gone18("این پرونده پیدا نشد.")
            if (c.str("status") == "closed") return Reply(409, problem16(409, "validation_failed", "همین حالا بسته است."))
            if (c.arr("emails").any { it.str("state") == "waiting_seal" }) return Reply(409, problem16(409, "validation_failed", "ایمیلی منتظر مُهر توست؛ اول آن را مُهر یا رد کن."))
            val x = c.with("timeline" to ja(c.arr("timeline") + jo("at" to stamp, "kind" to "decision", "ref" to null, "summary_fa" to "مالک پرونده را بست.")), "status" to "closed", "updated_at" to stamp, "version" to c.int("version") + 1)
            saveCase(x)
            return Reply(200, x)
        }
        return null
    }

    /** What deciding a §22 card does in the demo (the web's decided19): publish or reject the item, send or reopen the email's case,
     *  activate or reject the role. */
    private fun decided19(d: JsonObject) {
        val status = d.str("status")
        val p = d.obj("payload")
        when (d.str("kind")) {
            "media_publish" -> {
                val x = itemsAll().firstOrNull { it.str("ref") == p.str("item") } ?: return
                saveItem(if (status == "approved") publishNow(x) else x.with("state" to "rejected", "updated_at" to stamp, "version" to x.int("version") + 1,
                    "state_note_fa" to if (status == "returned") "مالک برگرداند: «${d.str("note").orEmpty()}»" else "مالک رد کرد."))
            }
            "email_send" -> {
                val c = casesAll().firstOrNull { cs -> cs.arr("emails").any { it.str("decision_ref") == d.str("ref") } } ?: return
                val out = c.arr("emails").count { it.str("direction") == "out" }
                val emails = c.arr("emails").map { e ->
                    if (e.str("decision_ref") != d.str("ref")) e
                    else if (status == "approved") e.with("state" to "sent", "at" to stamp, "message_id" to "<${c.str("ref")?.lowercase()}.$out@coinepro.com>")
                    else e.with("state" to "rejected")
                }
                val entry = if (status == "approved") jo("at" to stamp, "kind" to "email_out", "ref" to d.str("ref"), "summary_fa" to "با مُهر مالک فرستاده شد؛ دقیقاً همان پیام، یک بار.")
                else jo("at" to stamp, "kind" to "decision", "ref" to d.str("ref"), "summary_fa" to if (status == "returned") "مالک برگرداند: «${d.str("note").orEmpty()}»؛ مشاور پیش‌نویس تازه مینویسد." else "مالک ایمیل را رد کرد؛ فرستاده نشد.")
                saveCase(c.with("emails" to ja(emails), "timeline" to ja(c.arr("timeline") + entry), "status" to if (status == "approved") "waiting_reply" else "open", "updated_at" to stamp, "version" to c.int("version") + 1))
            }
            "role_new" -> update("/roles/drafts", p.str("draft") ?: return) {
                if (status == "approved") it.with("state" to "active", "activated_at" to stamp, "approver" to owner) else it.with("state" to "rejected")
            }
        }
    }

    private val MEDIA_CHECKS = listOf("brand", "red_lines", "risk_warning", "facts", "rights", "platform", "qc")
}
