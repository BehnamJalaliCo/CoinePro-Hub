package com.coinepro.hq

import android.content.Context
import com.coinepro.hq.core.net.Api
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
import kotlinx.serialization.json.put
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

private class DemoInterceptor(context: Context) : Interceptor {
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
        val body = req.body?.let { b -> Buffer().also { b.writeTo(it) }.readUtf8() }?.takeIf { it.isNotBlank() }?.let { Api.json.parseToJsonElement(it).jsonObject }
        val (status, out) = if (req.method == "GET") read(path, req.url.queryParameterNames.associateWith { req.url.queryParameter(it) }) else write(path, body)
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
            val msg = buildJsonObject {
                put("id", "m${System.nanoTime()}"); put("ref", "$code-%04d".format(items.size + 1)); put("thread", code); put("kind", "text")
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
        if (path == "/notifications/read-all") return 200 to buildJsonObject { put("updated", 0) }
        if (path == "/auth/logout") return 204 to JsonObject(emptyMap())
        return 200 to JsonObject(emptyMap())
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
