package com.coinepro.hq.core.net

import java.io.File
import java.io.IOException
import java.io.InputStream
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.async
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNamingStrategy
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.coroutines.flow.flowOn
import kotlinx.serialization.json.put
import kotlinx.serialization.serializer
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okio.BufferedSink

/** A failed API call, carrying the contract's stable [code] and Persian [messageFa] (contract §1). */
class ApiException(
    val status: Int,
    val code: String,
    val messageFa: String,
    val requestId: String? = null,
    /** ⟨1.4.6⟩ `409 not_ready`: what is still missing (§18.8, e.g. ["brand"]). */
    val missing: List<String> = emptyList(),
    /** ⟨1.5⟩ `422 send_blocked`: the outbound guard's refusal codes (§19.6). */
    val blockedReasons: List<String> = emptyList(),
    /** A `429` (`rate_limited`, `send_limit`, …): seconds from `Retry-After`, when the server sent one. */
    val retryAfter: Int? = null,
    /** ⟨1.5⟩ `422 batch_not_eligible`: each refused card and why (§20.12 `fields.items`); nothing was sealed. */
    val batchReasons: List<Pair<String, String>> = emptyList(),
    /** ⟨1.6⟩ the fields a `422 validation_failed` names (`fields`), so the app can say which (§22.7). */
    val fieldKeys: List<String> = emptyList(),
    /** ⟨1.7⟩ `422 schema_invalid` and `validation_failed`: each named field with the server's sentence (§23.10), shown next to it. */
    val fields: Map<String, String> = emptyMap(),
    /** ⟨1.10⟩ the Problem's `detail` (the framework's "Not Found" says the route itself is missing, [routeMissing]). */
    val detail: String? = null,
) : Exception("HTTP $status $code") {
    /** The error log's entry for this failure, so a caller that expected it (a 404 read as "none yet") can take it back. */
    @Volatile var logged: Long? = null
    val isAuth: Boolean get() = status == 401
    val isOffline: Boolean get() = status == 0
    /** No answer, or a 502/503/504 from the proxy: what a hub that is restarting looks like (retried, then waited out). */
    val transient: Boolean get() = status == 0 || (status in 502..504 && code == "hub_unreachable")

    companion object {
        fun offline() = ApiException(0, "network_error", "اتصال برقرار نشد. اینترنت را بررسی کن.")
        fun unexpected(status: Int) =
            if (status in 502..504) ApiException(status, "hub_unreachable", "هاب الان جواب نمیدهد؛ چند لحظه بعد خودکار دوباره تلاش میشود.")
            else ApiException(status, "internal_error", "خطای غیرمنتظره؛ دوباره تلاش کن.")
    }
}

/** Where the session token lives; the API only reads it and clears it on 401. */
interface TokenSource {
    fun token(): String?
    fun clear()
}

/** One failed call as the error log keeps it: never a body, a token or a cookie; the log masks the path's ids itself. */
data class ApiFailure(
    /** http · decode · network */
    val kind: String,
    val method: String,
    val path: String,
    val status: Int? = null,
    val code: String? = null,
    val title: String? = null,
    val requestId: String? = null,
    /** decode: the JSON path the decoder stopped at (`$.items[0].samples[0].file`). */
    val field: String? = null,
    /** decode: what it expected, without the input. */
    val detail: String? = null,
    /** The server's own sentence (the Problem's detail or Persian message); the log trims, redacts and masks it. */
    val message: String? = null,
    /** From sending the request to the answer (or the failure), all attempts. */
    val durationMs: Long? = null,
    /** The response's headers; the log keeps an allow-list only. */
    val headers: Map<String, String> = emptyMap(),
    /** error · warning · info; null: the log decides from the kind and status. */
    val level: String? = null,
)

/** Where the app records failed calls (the «خطاخوان» log); [forget] takes back one a caller expected. */
interface FailureSink {
    fun record(f: ApiFailure): Long?
    fun forget(id: Long)
}

/** A decoder's complaint as the log keeps it: the JSON path and the sentence, never the JSON input the message quotes. */
@OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
fun decodeFailure(method: String, path: String, status: Int?, e: Throwable, requestId: String? = null): ApiFailure {
    val msg = e.message.orEmpty().substringBefore("JSON input:")
    val field = Regex("at path:? ?(\\$\\S*)").find(msg)?.groupValues?.get(1)?.trimEnd('.', ',')
    val missing = (e as? kotlinx.serialization.MissingFieldException)?.missingFields
    val type = Regex("serial name '([^']+)'").find(msg)?.groupValues?.get(1)?.substringAfterLast('.')
    val sentence = msg.lineSequence().firstOrNull().orEmpty()
        .replace(Regex("\\s*at path:? ?\\$\\S*"), "").replace(Regex("\\s*Use 'coerceInputValues.*$"), "")
        .replace(Regex("Unexpected JSON token at offset \\d+: "), "").trim().take(240)
    val detail = when {
        missing != null -> "missing ${missing.joinToString()}" + (type?.let { " ($it)" } ?: "")
        else -> sentence.ifBlank { e::class.simpleName.orEmpty() }
    }
    return ApiFailure("decode", method, path, status, "contract_mismatch", null, requestId, field, detail)
}

/** Signs one 🔏 action: the API supplies the contract's action name and target, the caller returns a step-up token. */
typealias StepUp = suspend (action: String, target: String) -> String

/** The hub's public API (contract v1.7) as the Android client sees it: Bearer session, JSON, Problem errors. */
class Api(
    origin: String,
    private val tokens: TokenSource,
    extra: Interceptor? = null,
) {
    private val base: HttpUrl = origin.toHttpUrl()

    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .callTimeout(45, TimeUnit.SECONDS)
        .addInterceptor(ContractHeaders(tokens))
        .apply { if (extra != null) addInterceptor(extra) }
        .build()

    /** A client for long-lived SSE streams: no read or call timeout. */
    val streamClient: OkHttpClient = client.newBuilder().readTimeout(0, TimeUnit.SECONDS).callTimeout(0, TimeUnit.SECONDS).build()

    /** Uploads and voice: a ten-minute film on a slow line must not hit the 45 s call limit. */
    private val transferClient: OkHttpClient = client.newBuilder().writeTimeout(120, TimeUnit.SECONDS).readTimeout(120, TimeUnit.SECONDS).callTimeout(0, TimeUnit.SECONDS).build()

    /** The session is gone (401 outside a normal call, e.g. on the stream). */
    fun unauthorized() = expire()

    /** Told when a session the app held is refused (401): the background link tells the owner once and stops. */
    @Volatile var onExpired: (() -> Unit)? = null

    private fun expire() {
        val had = tokens.token() != null
        tokens.clear()
        if (had) onExpired?.invoke()
    }

    /** The app's error log for a real session; the demo and the tests leave it null. */
    @Volatile var failures: FailureSink? = null
    /** ⟨1.10⟩ the §28 routes this hub turned out not to serve, learnt once per app start ([gated]). */
    val gaps = HubGaps()

    /** Whether the hub is answering (a restart's burst of 502s); every answer and every failure reports here. */
    @Volatile var hub: HubHealth? = null

    /** Asks the hub whether it is back (`GET /meta`), without logging: any answer but 502/503/504 counts. */
    suspend fun probe(): Boolean = try {
        send(Request.Builder().url(url("/meta")).get().header(REQUEST_ID, UUID.randomUUID().toString()).build(), client).use { !proxied(it) }
    } catch (e: IOException) {
        false
    }

    private fun mismatch(status: Int, method: String, path: String, e: Throwable, requestId: String? = null, durationMs: Long? = null): ApiException {
        val x = ApiException(status, "contract_mismatch", "پاسخ سرور با قرارداد نمیخواند؛ نسخه‌ی اپ را به‌روز کن.", requestId)
        x.logged = failures?.record(decodeFailure(method, if (path.startsWith("/api/")) path else "/api/v1$path", status, e, requestId).copy(durationMs = durationMs))
        return x
    }

    /** Decodes what a GET answered in more than one shape; a failure is a `contract_mismatch` with its field path in the log. */
    private inline fun <T> decoded(path: String, method: String = "GET", block: () -> T): T = try {
        block()
    } catch (e: IllegalArgumentException) {
        throw mismatch(200, method, path, e)
    }

    fun url(path: String, query: Map<String, Any?> = emptyMap()): HttpUrl {
        val b = base.newBuilder().encodedPath("/api/v1$path")
        for ((k, v) in query) if (v != null) b.addQueryParameter(k, v.toString())
        return b.build()
    }

    // --------------------------------------------------------------- auth --
    suspend fun loginOptions(): JsonObject = post("/auth/passkey/login/options", JsonObject(emptyMap()))
    suspend fun loginVerify(credential: JsonElement, deviceName: String): LoginOut =
        post("/auth/passkey/login/verify", buildJsonObject { put("credential", credential); put("device_name", deviceName) })
    suspend fun registerOptions(enrolmentToken: String?, stepUp: String? = null): JsonObject =
        post("/auth/passkey/register/options", buildJsonObject { put("enrolment_token", enrolmentToken) }, stepUp)
    suspend fun registerVerify(credential: JsonElement, deviceName: String): JsonObject =
        post("/auth/passkey/register/verify", buildJsonObject { put("credential", credential); put("device_name", deviceName) })
    suspend fun stepUpOptions(action: String, target: String): JsonObject =
        post("/auth/step-up/options", buildJsonObject { put("action", action); put("target", target) })
    suspend fun stepUpVerify(credential: JsonElement): StepUpOut = post("/auth/step-up/verify", buildJsonObject { put("credential", credential) })
    suspend fun session(): SessionInfo = get("/auth/session")
    suspend fun logout() { postUnit("/auth/logout", JsonObject(emptyMap())) }
    suspend fun devices(): DeviceList = get("/auth/devices")
    suspend fun revokeDevice(id: String, stepUp: String) { postUnit("/auth/devices/$id/revoke", JsonObject(emptyMap()), stepUp) }
    suspend fun meta(): Meta = get("/meta")

    // -------------------------------------------------------------- owner --
    suspend fun inbox(): InboxSummary = get("/inbox/summary")
    suspend fun away(): AwaySummary = get("/owner/away-summary")
    suspend fun presence(): Presence = get("/owner/presence")
    suspend fun setKhalvat(on: Boolean): Presence = put("/owner/presence", buildJsonObject { put("khalvat", on) })
    suspend fun ownerSettings(): OwnerSettings = get("/owner/settings")

    // ---------------------------------------------------------- decisions --
    suspend fun decisions(status: String? = "pending", risk: String? = null, company: String? = null, limit: Int = 50): Page<Decision> =
        get("/decisions", mapOf("status" to status, "risk" to risk, "company" to company, "limit" to limit))
    /**
     * «همه»: the hub lists one status at a time (`status` defaults to `pending`; there is no "all"), so every status is read and the
     * pages merged, newest first. A hub change (`status=all` or several statuses) would make this one call.
     */
    suspend fun decisionsAll(company: String? = null, limit: Int = 50): Page<Decision> = kotlinx.coroutines.coroutineScope {
        val pages = DECISION_STATUSES.map { s -> async { decisions(s, company = company, limit = limit).items } }.map { it.await() }
        Page(pages.flatten().distinctBy { it.ref }.sortedByDescending { it.decidedAt ?: it.createdAt }.take(limit), null)
    }
    suspend fun decision(ref: String): Decision = get("/decisions/${seg(ref)}")
    suspend fun approve(ref: String, note: String?, stepUp: String?): Decision =
        post("/decisions/${seg(ref)}/approve", buildJsonObject { put("note", note); put("amendments", JsonNull) }, stepUp)
    suspend fun reject(ref: String, reason: String?, reasonCode: String?): Decision =
        post("/decisions/${seg(ref)}/reject", buildJsonObject { put("reason", reason); put("reason_code", reasonCode) })
    suspend fun returnDecision(ref: String, note: String): Decision = post("/decisions/${seg(ref)}/return", buildJsonObject { put("note", note) })
    suspend fun ask(ref: String, question: String?): Posted = post("/decisions/${seg(ref)}/ask", buildJsonObject { put("question", question) })
    suspend fun reviewWithAdvisor(ref: String): Posted = post("/decisions/${seg(ref)}/review-with-advisor", JsonObject(emptyMap()))

    // ------------------------------------------------------- deliverables --
    suspend fun deliverables(unrated: Boolean? = null, company: String? = null, limit: Int = 50): Page<Deliverable> =
        get("/deliverables", mapOf("unrated" to unrated, "company" to company, "limit" to limit))
    /** ⟨1.7.3⟩ the outputs list with every filter of §5.2: [seen] (true · false), [category] (report · work), [from]/[to] (days in the
     *  owner's zone), [producer], [q]; newest first, a Page. A hub before ⟨1.7.3⟩ ignores the new parameters (the app filters too). */
    suspend fun deliverables(q: DeliverableQuery, cursor: String? = null, limit: Int = 50): Page<Deliverable> =
        get("/deliverables", mapOf(
            "seen" to q.seen, "category" to q.category, "unrated" to q.unrated.takeIf { it }, "company" to q.company, "producer" to q.producer,
            "q" to q.text?.trim()?.ifEmpty { null }, "from" to q.from, "to" to q.to, "limit" to limit, "cursor" to cursor,
        ))
    suspend fun deliverable(ref: String): Deliverable = get("/deliverables/${seg(ref)}")
    /** ⟨1.7.3⟩ marks one or many seen (or unseen again); idempotent. A hub before ⟨1.7.3⟩ answers `404`: the caller keeps it on the phone. */
    suspend fun markSeen(refs: List<String>, seen: Boolean = true): SeenOut =
        post("/deliverables/seen", buildJsonObject { put("refs", ids(refs)); put("seen", seen) })
    /** ⟨1.7.3⟩ files it in the archive (§23) as a draft with the body as a PDF; a second call answers the same record. */
    suspend fun fileDeliverable(ref: String): FiledOut = post("/deliverables/${seg(ref)}/file", JsonObject(emptyMap()))
    suspend fun rate(ref: String, score: Int, comment: String?): Deliverable =
        post("/deliverables/${seg(ref)}/rating", buildJsonObject { put("score", score); put("comment", comment) })
    /** ⟨1.10⟩ §28.1 files several at once, each as `/{ref}/file` does (idempotent per ref). */
    suspend fun fileDeliverables(refs: List<String>): FiledMany =
        post("/deliverables/file", buildJsonObject { put("refs", ids(refs.distinct())) })
    /**
     * ⟨1.10⟩ §28.1 deletes for good (the owner only): the rows, their files and ratings; an Audit line stays, and archive records they
     * were filed into stay. 🔏 `deliverables.delete` on [deleteTarget] (the SHA-256 of the sorted refs); the body sends the same list.
     */
    suspend fun deleteDeliverables(refs: List<String>, stepUp: StepUp): DeletedOut {
        val sorted = refs.distinct().sorted()
        val token = stepUp("deliverables.delete", deleteTarget(sorted))
        return call(write("DELETE", "/deliverables", buildJsonObject { put("refs", ids(sorted)) }, token), serializer())
    }

    // ------------------------------------------------ ⟨1.10⟩ §28.2 catalogue --
    /** The latest catalogue of a company; `404` while it has none. */
    suspend fun catalogue(code: String): Catalogue = get("/companies/${seg(code)}/catalogue")
    /** Starts a run (the owner): a read-only `claude` job on every paired server of the company. */
    suspend fun startCatalogue(code: String): Catalogue = post("/companies/${seg(code)}/catalogue", JsonObject(emptyMap()))

    // ---------------------------------------------- ⟨1.10⟩ §28.3 app errors --
    /** The app's own error log (already masked on the phone), one batch. */
    suspend fun clientErrors(version: String, entries: JsonArray): ClientErrorsOut =
        post("/client/errors", buildJsonObject { put("app", "android"); put("version", version); put("entries", entries) })

    // ------------------------------------------------------- organisation --
    suspend fun companies(): List<Company> = get("/companies")
    suspend fun company(code: String): Company = get("/companies/${seg(code)}")
    suspend fun departments(code: String): List<Department> = get("/companies/${seg(code)}/departments")
    suspend fun orgChart(company: String): OrgChart = get("/org/${seg(company)}/chart")
    suspend fun employees(company: String? = null, department: String? = null, limit: Int = 100): Page<Employee> =
        get("/employees", mapOf("company" to company, "department" to department, "limit" to limit))
    suspend fun employee(code: String): Employee = get("/employees/${seg(code)}")

    // --------------------------------------------------------------- work --
    suspend fun work(
        company: String? = null, status: String? = null, assignee: String? = null, q: String? = null, limit: Int = 50,
        createdBy: String? = null, cursor: String? = null,
    ): Page<Work> =
        get("/work", mapOf("company" to company, "status" to status, "assignee" to assignee, "q" to q, "limit" to limit, "created_by" to createdBy, "cursor" to cursor))

    /** ⟨1.7.4⟩ every event of a work and of its sub-works (two levels down) in one list, oldest first, with the agents' run steps
     *  (summaries and tool metadata only). */
    /** One page; the hub takes at most [MAX_PAGE] (`pagination.MAX_LIMIT`): a bigger `limit` is a 422. */
    suspend fun treeEvents(id: String, limit: Int = MAX_PAGE, cursor: String? = null): Page<TreeEvent> =
        get("/work/${seg(id)}/tree-events", mapOf("limit" to limit.coerceIn(1, MAX_PAGE), "cursor" to cursor))

    /** The whole tree, oldest first: pages of [MAX_PAGE] followed to the end (at most [pages] pages, so a runaway tree stays bounded). */
    suspend fun treeEventsAll(id: String, pages: Int = 15): Page<TreeEvent> {
        val out = ArrayList<TreeEvent>()
        var cursor: String? = null
        repeat(pages) {
            val p = treeEvents(id, MAX_PAGE, cursor)
            out += p.items
            cursor = p.nextCursor ?: return Page(out, null)
        }
        return Page(out, cursor)
    }

    /** Work by id, or by its ref ("W-000104") as planner items and messages carry it: the API addresses work
     *  by UUID, so a ref is resolved through the list search first. */
    suspend fun workOne(idOrRef: String): Work {
        // Only a work ref or an id is a work: a meeting's MT-… (0.4.0) or any other ref never reaches the hub as one (its 422).
        if (com.coinepro.hq.core.data.Refs.prefix(idOrRef) != null && !REF.matches(idOrRef)) throw ApiException(404, "not_found", "این مورد کار نیست؛ از صفحه‌ی خودش باز کن.")
        if (!REF.matches(idOrRef)) return get("/work/${seg(idOrRef)}")
        val hit = work(q = idOrRef, limit = 5).items.firstOrNull { it.ref == idOrRef }
            ?: throw ApiException(404, "not_found", "این کار پیدا نشد.")
        return get("/work/${seg(hit.id)}")
    }
    suspend fun workEvents(id: String): Page<WorkEvent> = get("/work/${seg(id)}/events")

    private val REF = Regex("^W-\\d{3,8}$")
    suspend fun createWork(body: WorkCreate): Work = post("/work", json.encodeToJsonElement(WorkCreate.serializer(), body))
    suspend fun planner(from: String, to: String, scope: String? = null): Planner = get("/planner", mapOf("from" to from, "to" to to, "scope" to scope))

    // ----------------------------------------------------------- messages --
    suspend fun threads(): List<Thread> = get("/threads")
    suspend fun messages(code: String, limit: Int = 100): Page<Message> = get("/threads/${seg(code)}/messages", mapOf("limit" to limit))
    /** ⟨1.5⟩ [mode] `"devil"`: the advisor argues why not; thread A only (§21.1), elsewhere `422 validation_failed`. */
    suspend fun send(code: String, body: String, attachments: List<String> = emptyList(), mode: String? = null): JsonObject =
        post("/threads/${seg(code)}/messages", buildJsonObject {
            put("body", body); if (attachments.isNotEmpty()) put("attachments", ids(attachments)); if (mode != null) put("mode", mode)
        })
    suspend fun markRead(code: String, upToRef: String): Thread = post("/threads/${seg(code)}/read", buildJsonObject { put("up_to_ref", upToRef) })

    // ------------------------------------------------------ notifications --
    suspend fun notifications(unread: Boolean? = null, level: String? = null, limit: Int = 50, cursor: String? = null): NotificationPage =
        get("/notifications", mapOf("unread" to unread, "level" to level, "limit" to limit, "cursor" to cursor))
    /** ⟨1.10.1⟩ §28.5 deletes for good (the owner only): these [ids], or with [allReadBefore] every read one up to that moment (the
     *  newest the screen shows). */
    suspend fun deleteNotifications(ids: List<String>? = null, allReadBefore: String? = null): DeletedOut =
        call(write("DELETE", "/notifications", buildJsonObject {
            if (allReadBefore != null) { put("all_read", true); put("before", allReadBefore) } else put("ids", ids(ids.orEmpty().distinct()))
        }, null), serializer())
    /** Everything unread up to [before] (the newest the owner saw, so what arrives meanwhile stays unread), of one [level] or all. */
    suspend fun readAll(before: String? = null, level: String? = null): JsonObject =
        post("/notifications/read-all", buildJsonObject { before?.let { put("before", it) }; level?.let { put("level", it) } })
    suspend fun readNotification(id: String): Notification = post("/notifications/${seg(id)}/read", JsonObject(emptyMap()))
    suspend fun answer(id: String, choiceId: String): Notification = post("/notifications/${seg(id)}/answer", buildJsonObject { put("choice_id", choiceId) })

    // ------------------------------------------------------------ control --
    suspend fun control(): ControlState = get("/control/state")
    suspend fun killSwitch(scope: String, engaged: Boolean, reason: String, stepUp: String?): ControlState =
        post("/control/kill-switch", buildJsonObject { put("scope", scope); put("state", if (engaged) "engaged" else "released"); put("reason", reason) }, stepUp)
    /** Engaging needs no step-up (speed matters, §9): `holding` or `company:<CODE>`. */
    suspend fun engage(scope: String, reason: String): ControlState = killSwitch(scope, true, reason, null)
    /** Releasing is 🔏 `kill_switch.release` on the scope itself. */
    suspend fun release(scope: String, reason: String, stepUp: StepUp): ControlState = killSwitch(scope, false, reason, stepUp("kill_switch.release", scope))
    /** A freeze of the company's deploys until [until] (§9); the owner needs no seal to close. */
    suspend fun freezeDeploys(company: String, until: String, reason: String): FreezeOut = deployFreeze(company, until, reason)
    /** Lifting every freeze of the company (a past `until`) is sealed with the passkey, `deploy_freeze.lift` on `company:<CODE>`:
     *  the owner's rule for opening what was closed. The hub of contract v1.7 does not check this header yet (it takes no 🔏 here). */
    suspend fun liftFreezes(company: String, reason: String, stepUp: StepUp, now: java.time.Instant = java.time.Instant.now()): FreezeOut {
        val token = stepUp("deploy_freeze.lift", "company:$company")
        return post("/control/deploy-freeze", buildJsonObject { put("company", company); put("until", now.minusSeconds(60).toString()); put("reason", reason) }, token)
    }
    /** The owner's own control actions with their reasons (§1.8): `kind=control`. */
    suspend fun ownerInteractions(kind: String? = null, limit: Int = 100): Page<Interaction> = get("/owner/interactions", mapOf("kind" to kind, "limit" to limit))

    // ----------------------------------------------------------- treasury --
    suspend fun treasury(period: String = "month", company: String? = null): TreasurySummary =
        get("/treasury/summary", mapOf("period" to period, "company" to company))
    suspend fun breakdown(by: String, from: String? = null, to: String? = null, company: String? = null): List<BreakdownRow> =
        get("/treasury/breakdown", mapOf("by" to by, "from" to from, "to" to to, "company" to company))
    suspend fun connections(): List<Connection> = get("/connections")

    // ------------------------------------------------------ files ⟨1.3⟩ --
    /** Where a file or one of its variants is served. Demo and local ids (data:, file:) are already loadable. */
    fun fileUrl(id: String, variant: String? = null): String =
        if (LOCAL.any { id.startsWith(it) }) id else url("/files/${seg(id)}", mapOf("variant" to variant)).toString()

    /** Raw-body upload (contract §17.1): the file streams from [open] and is never held in memory; [progress] runs on the
     *  network thread with 0..1. [size] < 0 means unknown (chunked). */
    suspend fun upload(name: String, mime: String, size: Long, open: () -> InputStream, progress: (Float) -> Unit = {}): FileRef {
        val body = object : RequestBody() {
            override fun contentType() = mime.toMediaType()
            override fun contentLength() = size
            override fun writeTo(sink: BufferedSink) {
                open().use { input ->
                    val buf = ByteArray(64 * 1024)
                    var sent = 0L
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        sink.write(buf, 0, n)
                        sent += n
                        if (size > 0) progress((sent.toFloat() / size).coerceIn(0f, 1f))
                    }
                }
            }
        }
        val req = Request.Builder().url(url("/files")).post(body)
            .header("X-File-Name", seg(name))
            .header("Idempotency-Key", UUID.randomUUID().toString())
            .build()
        return call(req, serializer(), transferClient)
    }

    /** A file's `FileRef` (§17.1); ⟨1.9⟩ with the hub's `transcript_fa` once `file.transcribed` said so. */
    suspend fun fileMeta(id: String): FileRef = get("/files/${seg(id)}/meta")

    /** Exact Persian text from the owner's voice (contract §17.2). */
    suspend fun transcribe(audio: File, mime: String, purpose: String): Transcript {
        val req = Request.Builder().url(url("/transcribe", mapOf("purpose" to purpose))).post(audio.asRequestBody(mime.toMediaType()))
            .header("Idempotency-Key", UUID.randomUUID().toString())
            .build()
        return call(req, serializer(), transferClient)
    }

    // --------------------------------------------------- workshop ⟨1.3⟩ --
    suspend fun workspaces(): List<Workspace> = get("/workshop/workspaces")
    suspend fun grants(active: Boolean = true): List<Grant> = get("/workshop/grants", mapOf("active" to active))
    suspend fun sessions(): Page<CodeSession> = get("/workshop/sessions")
    suspend fun codeSession(ref: String): CodeSession = get("/workshop/sessions/${seg(ref)}")
    suspend fun sessionEvents(ref: String, after: Long? = null): Page<SessionEvent> = get("/workshop/sessions/${seg(ref)}/events", mapOf("after" to after))
    suspend fun steer(ref: String, body: String, attachments: List<String>): SessionEvent =
        post("/workshop/sessions/${seg(ref)}/messages", buildJsonObject { put("body", body); put("attachments", ids(attachments)) })
    /** An `approval_request` answered. Allowing needs a step-up bound to "S-0004/AP-0007"; a denial needs none (§17.7). */
    suspend fun answerApproval(ref: String, approvalId: String, allow: Boolean, stepUp: String?, note: String? = null): SessionEvent =
        post("/workshop/sessions/${seg(ref)}/approvals/${seg(approvalId)}", buildJsonObject { put("allow", allow); put("note", note) }, stepUp)
    suspend fun stopSession(ref: String): CodeSession = post("/workshop/sessions/${seg(ref)}/stop", JsonObject(emptyMap()))
    suspend fun createSession(grant: String, title: String, brief: String, attachments: List<String>): CodeSession =
        post("/workshop/sessions", buildJsonObject { put("grant", grant); put("title", title); put("brief", brief); put("attachments", ids(attachments)) })
    suspend fun revokeGrant(ref: String): Grant = post("/workshop/grants/${seg(ref)}/revoke", JsonObject(emptyMap()))

    /** The owner's grant (🔏): the step-up is bound to the SHA-256 of the exact body sent, so it is serialised once. */
    suspend fun createGrant(body: GrantIn, stepUp: suspend (target: String) -> String): Grant {
        val text = json.encodeToString(GrantIn.serializer(), body)
        val token = stepUp(sha256(text))
        val req = Request.Builder().url(url("/workshop/grants")).post(text.toRequestBody(JSON))
            .header("Idempotency-Key", UUID.randomUUID().toString()).header("X-Step-Up", token).build()
        return call(req, serializer())
    }

    // ------------------------------------------------ voice orders ⟨1.3⟩ --
    /** ⟨1.11⟩ §29.4 with [route] (the secretary's preview, maybe edited by the owner) the hub follows it exactly; without, it decides. */
    suspend fun order(text: String, source: String, fileId: String?, route: OrderRoute29? = null): Order =
        post("/orders", buildJsonObject {
            put("text", text); put("source", source); put("file_id", fileId)
            if (route != null) put("route", json.encodeToJsonElement(OrderRoute29.serializer(), route))
        })
    suspend fun orders(): Page<Order> = get("/orders")

    // ------------------------------------------------- oversight ⟨1.4⟩ --
    // Every 🔏 write takes [StepUp]: the API names the action and the exact target (§18.10), the caller only signs.
    suspend fun oversight(): OversightSummary = get("/oversight/summary")
    suspend fun protocols(): List<Protocol> = get("/oversight/protocols")
    suspend fun findings(status: String? = null): Page<Finding> = get("/oversight/findings", mapOf("status" to status))
    suspend fun challenges(): Page<Challenge> = get("/oversight/challenges")
    suspend fun standingOrders(): List<StandingOrder> = get("/oversight/orders")
    suspend fun holds(): List<Hold> = get("/oversight/holds", mapOf("state" to "held"))
    suspend fun findingStatus(ref: String, status: String, note: String): Finding =
        post("/oversight/findings/${seg(ref)}/status", buildJsonObject { put("status", status); put("note", note) })
    suspend fun newStandingOrder(text: String, source: String, fileId: String?, appliesTo: String): StandingOrder =
        post("/oversight/orders", buildJsonObject { put("text_md", text); put("source", source); put("file_id", fileId); put("applies_to", appliesTo) })
    suspend fun sealStandingOrder(ref: String, stepUp: StepUp): StandingOrder =
        post("/oversight/orders/${seg(ref)}/seal", JsonObject(emptyMap()), stepUp("oversight.order", ref))
    suspend fun retireStandingOrder(ref: String): StandingOrder = post("/oversight/orders/${seg(ref)}/retire", JsonObject(emptyMap()))
    suspend fun releaseHold(ref: String, stepUp: StepUp): Hold = post("/oversight/holds/${seg(ref)}/release", JsonObject(emptyMap()), stepUp("oversight.release", ref))
    suspend fun cancelHold(ref: String): Hold = post("/oversight/holds/${seg(ref)}/cancel", JsonObject(emptyMap()))
    suspend fun inquiries(from: String? = null): Page<Inquiry> = get("/inquiries", mapOf("from" to from))

    // ------------------------------------------------- assistant ⟨1.4⟩ --
    suspend fun errands(): Page<Errand> = get("/errands")
    suspend fun cancelErrand(ref: String): Errand = post("/errands/${seg(ref)}/cancel", JsonObject(emptyMap()))

    // ---------------------------------------------------- stars ⟨1.4⟩ --
    /** The last closed period's roll-up, or null while none has been made yet (the hub answers `404 not_found` until the first
     *  Saturday morning, or the first of the month, after stars were given). */
    suspend fun rollup(period: String): StarRollup? = orNull { get("/stars/rollup", mapOf("period" to period)) }
    suspend fun rubrics(): List<StarRubric> = listAny("/stars/rubrics", emptyMap(), StarRubric.serializer())
    /** The hub answers a bare list (`list[Lesson]`); a page is read too. */
    suspend fun lessons(): List<Lesson> = listAny("/lessons", emptyMap(), Lesson.serializer())

    // ------------------------------------------- skills, academy ⟨1.4⟩ --
    suspend fun skills(): List<Skill> = get("/skills")
    suspend fun newSkill(name: String, body: String, roles: List<String>, companies: List<String>?, fileIds: List<String>): Skill =
        post("/skills", buildJsonObject {
            // ⟨1.4.7⟩ scope is nested; the summary defaults to the start of the text on the server.
            put("name_fa", name); put("body_md", body)
            put("scope", buildJsonObject { put("roles", ids(roles)); put("companies", companies?.let(::ids) ?: JsonPrimitive("all")) })
            put("file_ids", ids(fileIds))
        })
    /** Activation is bound to the exact version reviewed and tested: target "SK-005@1". */
    suspend fun activateSkill(s: Skill, stepUp: StepUp): Skill =
        post("/skills/${seg(s.ref)}/activate", buildJsonObject { put("version", s.version) }, stepUp("skill.activate", "${s.ref}@${s.version}"))
    suspend fun retireSkill(ref: String): Skill = post("/skills/${seg(ref)}/retire", JsonObject(emptyMap()))
    suspend fun curricula(): List<Curriculum> = get("/academy/curricula")
    suspend fun evals(): List<EvalSuite> = get<List<EvalSuite>>("/academy/evals").map { s -> s.copy(recent = s.recent.filter { it.done }) }
    /** Item 30: the newest run of each (suite, model) for a role. */
    suspend fun modelComparison(role: String): Page<EvalRun> =
        get<Page<EvalRun>>("/academy/runs?role=${seg(role)}&subject_kind=model&latest=true").let { p -> p.copy(items = p.items.filter { it.done }) }
    suspend fun trainingRecord(employee: String): TrainingRecord = get("/academy/records/${seg(employee)}")
    suspend fun teachings(): List<Teaching> = get("/academy/teach")
    suspend fun teach(targetKind: String, targetRef: String, text: String, source: String, fileId: String?): Teaching =
        post("/academy/teach", buildJsonObject {
            put("target", buildJsonObject { put("kind", targetKind); put("ref", targetRef) }); put("text", text); put("source", source); put("file_id", fileId)
        })
    suspend fun approveTeaching(ref: String, stepUp: StepUp): Teaching = post("/academy/teach/${seg(ref)}/approve", JsonObject(emptyMap()), stepUp("academy.approve", ref))
    suspend fun rejectTeaching(ref: String): Teaching = post("/academy/teach/${seg(ref)}/reject", JsonObject(emptyMap()))

    // --------------------------------------------- egress and MCP ⟨1.4⟩ --
    /** The hub answers one row per company and day (`list[EgressDay]`); an object in the screen's shape is read too. */
    suspend fun egressSummary(period: String = "day"): EgressSummary {
        val e = get<JsonElement>("/egress/summary", mapOf("period" to period))
        return decoded("/egress/summary") {
            if (e is JsonArray) EgressSummary.of(json.decodeFromJsonElement(kotlinx.serialization.builtins.ListSerializer(EgressDay.serializer()), e), period)
            else json.decodeFromJsonElement(EgressSummary.serializer(), e)
        }
    }
    suspend fun egress(limit: Int = 40): Page<EgressEntry> = get("/egress", mapOf("limit" to limit))
    suspend fun mcpServers(): List<McpServer> = get("/tools/mcp")
    suspend fun serviceAccounts(): List<ServiceAccount> = get("/tools/accounts")
    suspend fun toolCatalog(): List<ToolInfo> = get("/tools/catalog")
    suspend fun enableMcp(key: String, stepUp: StepUp): McpServer = post("/tools/mcp/${seg(key)}/enable", JsonObject(emptyMap()), stepUp("mcp.enable", key))
    suspend fun disableMcp(key: String): McpServer = post("/tools/mcp/${seg(key)}/disable", JsonObject(emptyMap()))

    // --------------------------------------- founding, provisioning ⟨1.4⟩ --
    suspend fun foundings(cursor: String? = null): Page<Founding> = get("/foundings", mapOf("cursor" to cursor))
    suspend fun founding(ref: String): Founding = get("/foundings/${seg(ref)}")
    suspend fun startFounding(kind: String, repo: String?, brief: String): Founding =
        post("/foundings", buildJsonObject { put("source", buildJsonObject { put("kind", kind); put("repo", repo); put("brief_md", brief) }) })
    /** ⟨1.4.6⟩ Without an active brand the hub answers `409 not_ready` (missing ["brand"]) unless [skipBrand]. */
    suspend fun activateFounding(ref: String, stepUp: StepUp, skipBrand: Boolean = false): Founding =
        post("/foundings/${seg(ref)}/activate", if (skipBrand) buildJsonObject { put("skip_brand", true) } else JsonObject(emptyMap()), stepUp("founding.activate", ref))
    suspend fun cancelFounding(ref: String): Founding = post("/foundings/${seg(ref)}/cancel", JsonObject(emptyMap()))
    suspend fun plan(ref: String): ServerPlan = get("/provisioning/plans/${seg(ref)}")
    suspend fun run(id: String): ProvisionRun = get("/provisioning/runs/${seg(id)}")
    /** The seal is bound to the plan the owner saw: its digest, which the server recomputes before anything is built. */
    suspend fun sealPlan(p: ServerPlan, stepUp: StepUp): ServerPlan = post("/provisioning/plans/${seg(p.ref)}/seal", JsonObject(emptyMap()), stepUp("provision.seal", p.digest))
    /** ⟨1.4.8⟩ a failed run of a still-sealed plan continues from its failed step, on the same seal. */
    suspend fun resumeRun(id: String): ProvisionRun = post("/provisioning/runs/${seg(id)}/resume", JsonObject(emptyMap()))

    // ------------------------------------------------- hiring ⟨1.4.2⟩ --
    suspend fun hiring(): Hiring = get("/owner/hiring")
    suspend fun roles(): List<RoleInfo> = get("/roles")
    suspend fun startHiring(mode: String, stepUp: StepUp): Hiring = post("/owner/hiring/start", buildJsonObject { put("mode", mode) }, stepUp("hiring.start", "holding"))
    suspend fun closeHiring(): Hiring = post("/owner/hiring/close", JsonObject(emptyMap()))
    /** Company month envelopes are budgets (contract §9 PUT /budgets); the seal is bound to the exact body. */
    suspend fun setEnvelopes(items: Map<String, Long>, stepUp: suspend (target: String) -> String) {
        val body = BudgetsPut(items.map { (co, t) -> CompanyBudgetIn(co, "company", co, "month", t) })
        val text = json.encodeToString(BudgetsPut.serializer(), body)
        val token = stepUp(sha256(text))
        val req = Request.Builder().url(url("/budgets")).put(text.toRequestBody(JSON)).header("X-Step-Up", token).build()
        execute(req).use { check(it) }
    }

    // ------------------------------------------------ stories ⟨1.4.3⟩ --
    suspend fun stories(): List<StoryRing> = get("/stories")
    suspend fun storiesSeen(refs: List<String>) = postUnit("/stories/seen", buildJsonObject { put("refs", ids(refs)) })
    suspend fun welcomeStory(ref: String): Story = post("/stories/${seg(ref)}/welcome", JsonObject(emptyMap()))
    /** Undoing a hire is the employee's dismissal (contract §4), sealed on the code. */
    suspend fun dismissEmployee(code: String, reason: String, stepUp: StepUp) =
        postUnit("/employees/${seg(code)}/dismiss", buildJsonObject { put("reason", reason) }, stepUp("employee.dismiss", code))
    /** The owner's own hire; the seal is bound to the exact body (its SHA-256), which the server hashes again. */
    suspend fun hireDirect(body: HireIn, stepUp: suspend (target: String) -> String): HireOut {
        val text = json.encodeToString(HireIn.serializer(), body)
        val token = stepUp(sha256(text))
        val req = Request.Builder().url(url("/org/hires")).post(text.toRequestBody(JSON))
            .header("Idempotency-Key", UUID.randomUUID().toString()).header("X-Step-Up", token).build()
        return call(req, serializer())
    }

    // ------------------------------------------- the owner's tools ⟨1.4.4⟩ --
    // APIs the hub already serves (docs/GAP_ANALYSIS_v2.md §5A). PATCH and PUT carry If-Match; 🔏 bodies are sealed on their SHA-256.
    suspend fun resolutions(q: String? = null, company: String? = null): Page<Resolution> = get("/resolutions", mapOf("q" to q, "company" to company))
    suspend fun recordResolution(title: String, body: String, sourceMessage: String?): Resolution =
        post("/resolutions", buildJsonObject { put("title", title); put("body", body); put("source_message", sourceMessage) })
    suspend fun notificationSettings(): NotificationSettings = get("/notification-settings")
    suspend fun saveNotificationSettings(s: NotificationSettings): NotificationSettings =
        send("PUT", "/notification-settings", json.encodeToString(NotificationSettingsIn.serializer(), NotificationSettingsIn(s.matrix)), ifMatch = s.version)
    suspend fun searchMessages(q: String, company: String? = null): Page<SearchHit> = get("/search/messages", mapOf("q" to q, "company" to company, "limit" to 20))
    /** A past [until] lifts the company's freezes; the owner lifts any of them (§9). */
    suspend fun deployFreeze(company: String, until: String, reason: String): FreezeOut =
        post("/control/deploy-freeze", buildJsonObject { put("company", company); put("until", until); put("reason", reason) })
    suspend fun cancelWork(id: String, reason: String): Work = post("/work/${seg(id)}/cancel", buildJsonObject { put("reason", reason) })
    suspend fun completeWork(id: String, evidence: List<EvidenceIn>): Work =
        post("/work/${seg(id)}/complete", buildJsonObject { put("evidence", json.encodeToJsonElement(kotlinx.serialization.builtins.ListSerializer(EvidenceIn.serializer()), evidence)) })
    suspend fun patchWork(w: Work, patch: WorkPatch): Work = send("PATCH", "/work/${seg(w.id)}", json.encodeToString(WorkPatch.serializer(), patch), ifMatch = w.version)
    suspend fun pauseEmployee(code: String): Employee = post("/employees/${seg(code)}/pause", JsonObject(emptyMap()))
    suspend fun resumeEmployee(code: String): Employee = post("/employees/${seg(code)}/resume", JsonObject(emptyMap()))
    /** Dismissal (§4): open work returns to the manager or to [transferTo]; a knowledge-transfer item is created. Sealed on the code. */
    suspend fun dismiss(code: String, reason: String, transferTo: String?, stepUp: StepUp): DismissOut =
        post("/employees/${seg(code)}/dismiss", buildJsonObject { put("reason", reason); if (transferTo != null) put("transfer_to", transferTo) }, stepUp("employee.dismiss", code))
    suspend fun runs(employee: String? = null, company: String? = null, state: String? = null, limit: Int = 50): Page<Run> =
        get("/runs", mapOf("employee" to employee, "company" to company, "state" to state, "limit" to limit))
    suspend fun runDetail(id: String): Run = get("/runs/${seg(id)}")
    suspend fun workRuns(id: String): List<Run> = get("/work/${seg(id)}/runs")
    /** ⟨1.9⟩ §27.2: the council of an order given with `mode: "council"`. */
    suspend fun council(id: String): Council = get("/work/${seg(id)}/council")
    suspend fun quota(): QuotaView = get("/treasury/quota")
    suspend fun whatIf(model: String, from: String, to: String, company: String? = null): WhatIf =
        get("/treasury/what-if", mapOf("model" to model, "from" to from, "to" to to, "company" to company))
    suspend fun calls(company: String? = null, actor: String? = null, status: String? = null, cursor: String? = null, limit: Int = 25): Page<CallRow> =
        get("/treasury/calls", mapOf("company" to company, "actor" to actor, "status" to status, "cursor" to cursor, "limit" to limit))
    suspend fun budgets(): List<BudgetUse> = get("/budgets")
    suspend fun putBudgets(rows: List<BudgetRowIn>, stepUp: suspend (target: String) -> String): List<BudgetUse> {
        val text = json.encodeToString(BudgetsBody.serializer(), BudgetsBody(rows))
        return send("PUT", "/budgets", text, stepUp = stepUp(sha256(text)))
    }
    suspend fun patchConnection(c: Connection, patch: ConnectionPatch, stepUp: StepUp): Connection =
        send("PATCH", "/connections/${seg(c.id)}", json.encodeToString(ConnectionPatch.serializer(), patch), ifMatch = c.version, stepUp = stepUp("connection.update", c.id))
    /** Write-only: the key goes to the secret store and never comes back (§10). */
    suspend fun connectionSecret(id: String, secret: String, stepUp: StepUp) =
        postUnit("/connections/${seg(id)}/secret", buildJsonObject { put("secret", secret) }, stepUp("connection.secret", id))
    suspend fun sites(company: String? = null): List<Site> = get("/ops/sites", mapOf("company" to company))
    suspend fun incidents(company: String? = null, open: Boolean? = null): List<Incident> = get("/ops/incidents", mapOf("company" to company, "open" to open, "limit" to 100))
    /** One company's list replaced as a whole (§16.6): left-out URLs are switched off, never deleted. Sealed on the body. */
    suspend fun putSites(company: String, sites: List<SiteIn>, stepUp: suspend (target: String) -> String): List<Site> {
        val text = json.encodeToString(SitesBody.serializer(), SitesBody(company, sites))
        return send("PUT", "/ops/sites", text, stepUp = stepUp(sha256(text)))
    }
    /** A new company (§3.1), sealed on its code. */
    suspend fun createCompany(body: CompanyIn, stepUp: StepUp): Company =
        post("/companies", json.encodeToJsonElement(CompanyIn.serializer(), body), stepUp("company.create", body.code))
    /**
     * Removing a company made by mistake. The hub has no such call yet (a server gap): this is the shape the app proposes,
     * `DELETE /companies/{code}` 🔏 `company.delete` on the code, `204` when the company has no work done, no outputs and no revenue,
     * `409 company_has_history` otherwise. A hub without it answers 404 or 405, and the app offers archiving instead.
     */
    suspend fun deleteCompany(code: String, stepUp: StepUp) {
        fun req(token: String?) = Request.Builder().url(url("/companies/${seg(code)}")).delete()
            .header("Idempotency-Key", UUID.randomUUID().toString()).apply { if (token != null) header("X-Step-Up", token) }.build()
        // Asked first without the passkey: a hub that has no delete answers 405 at once, and the owner is not asked for a seal it
        // cannot use; a hub that has it answers `403 step_up_required`, and the call is sealed and sent again.
        try {
            execute(req(null)).use { check(it) }
        } catch (e: ApiException) {
            if (e.status != 403 || e.code != "step_up_required") throw e
            e.logged?.let { failures?.forget(it) }
            execute(req(stepUp("company.delete", code))).use { check(it) }
        }
    }
    /** `PATCH /companies/{code}` with If-Match (§3.1); `status: archived` takes 🔏 `company.archive` on the code. */
    suspend fun patchCompany(co: Company, nameFa: String? = null, colorIndex: Int? = null, archive: Boolean = false, stepUp: StepUp? = null): Company {
        val text = json.encodeToString(JsonElement.serializer(), buildJsonObject {
            nameFa?.let { put("name_fa", it) }; colorIndex?.let { put("color_index", it) }; if (archive) put("status", "archived")
        })
        return send("PATCH", "/companies/${seg(co.code)}", text, ifMatch = co.version, stepUp = if (archive) stepUp?.invoke("company.archive", co.code) else null)
    }

    // ------------------------------------------- brand and seal ⟨1.4.6⟩ --
    /** Every active brand (§18.14); marks and seals draw from it. OkHttp has no cache here, so the app keeps it in its query cache. */
    suspend fun brands(): Brands = get("/brands")
    suspend fun companyBrand(code: String): CompanyBrandView = get("/companies/${seg(code)}/brand")
    /** Every version, newest first; the screen follows the one being traced. A list or a page, as the hub serves it. */
    suspend fun brandVersions(code: String): List<CompanyBrand> = when (val e = get<JsonElement>("/companies/${seg(code)}/brand/versions")) {
        is JsonArray -> json.decodeFromJsonElement(kotlinx.serialization.builtins.ListSerializer(CompanyBrand.serializer()), e)
        else -> json.decodeFromJsonElement(Page.serializer(CompanyBrand.serializer()), e).items
    }
    /** A new version from the owner's logo ([fileId] from POST /files); the other part is carried over from the active one. */
    suspend fun uploadBrand(code: String, fileId: String, part: String, options: BrandOptions): CompanyBrand =
        post("/companies/${seg(code)}/brand", buildJsonObject { put("file_id", fileId); put("part", part); put("options", optionsOf(options)) })
    suspend fun retraceBrand(code: String, version: Int, options: BrandOptions): CompanyBrand =
        post("/companies/${seg(code)}/brand/$version/retrace", buildJsonObject { put("options", optionsOf(options)) })
    /** The seal is bound to the version the owner saw: its digest, which the server recomputes. */
    suspend fun activateBrand(b: CompanyBrand, stepUp: StepUp): CompanyBrand =
        post("/companies/${seg(b.company)}/brand/${b.version}/activate", JsonObject(emptyMap()), stepUp("company.brand", b.digest))

    private fun optionsOf(o: BrandOptions) = buildJsonObject { o.colors?.let { put("colors", it) }; put("detail", o.detail) }

    // ----------------------------------------- revenue and support ⟨1.5⟩ --
    // Contract §19. Every 🔏 write names its action and exact target here (§19.9); bodies sealed on their hash are serialised
    // once. reply, teach and pull carry the caller's Idempotency-Key, so a retry of the same press never sends twice.
    suspend fun revenueSummary(period: String, company: String? = null): RevenueSummary = get("/revenue/summary", mapOf("period" to period, "company" to company))
    /** Unpaged, at most 400 rows. */
    suspend fun revenueDays(from: String, to: String, company: String? = null, account: String? = null): List<RevenueDay> =
        listOrPage("/revenue/days", mapOf("from" to from, "to" to to, "company" to company, "account" to account), RevenueDay.serializer())
    suspend fun revenueAccounts(): List<RevenueAccount> = listOrPage("/revenue/accounts", emptyMap(), RevenueAccount.serializer())
    /** Adds or changes the account of `exchange` + `company`, sealed on the exact body; the secret is set in the owner's terminal. */
    suspend fun saveRevenueAccount(body: RevenueAccountIn, stepUp: StepUp): RevenueAccount =
        sealedPost("/revenue/accounts", json.encodeToString(RevenueAccountIn.serializer(), body)) { stepUp("revenue.account", it) }
    /** Pull now (≤ 31 days), rate-limited like the schedule. [key] is the press's: a retry after a lost answer sends the same one. */
    suspend fun pullRevenue(id: String, key: String, from: String? = null, to: String? = null): JsonObject =
        call(write("POST", "/revenue/accounts/${seg(id)}/pull", JsonObject(emptyMap()), null, key, mapOf("from" to from, "to" to to)), serializer())

    suspend fun funnel(company: String, period: String): Funnel = get("/growth/funnel", mapOf("company" to company, "period" to period))
    suspend fun rescueCases(company: String? = null, state: String? = null, cursor: String? = null, limit: Int = 50): Page<RescueCase> =
        get("/growth/rescue", mapOf("company" to company, "state" to state, "limit" to limit, "cursor" to cursor))
    suspend fun rescueCase(ref: String): RescueCase = get("/growth/rescue/${seg(ref)}")

    suspend fun supportChannels(company: String? = null): List<SupportChannel> = listOrPage("/support/channels", mapOf("company" to company), SupportChannel.serializer())
    /** Stopping is always safe: no step-up. */
    suspend fun pauseChannel(c: SupportChannel): SupportChannel = post("/support/channels/${seg(c.company)}/${seg(c.kind)}/pause", JsonObject(emptyMap()))
    /** `If-Match` the channel's version. Widening ([widens]) is 🔏 `support.channel` on `company/kind@auto_send`; narrowing needs none. */
    suspend fun patchChannel(c: SupportChannel, autoSend: String? = null, live: Boolean = false, stepUp: StepUp): SupportChannel {
        val text = json.encodeToString(JsonElement.serializer(), buildJsonObject { autoSend?.let { put("auto_send", it) }; if (live) put("state", "live") })
        val token = if (widens(c, autoSend, live)) stepUp("support.channel", "${c.company}/${c.kind}@${autoSend ?: c.autoSend}") else null
        return send("PATCH", "/support/channels/${seg(c.company)}/${seg(c.kind)}", text, ifMatch = c.version, stepUp = token)
    }
    suspend fun conversations(company: String? = null, state: String? = null, channel: String? = null, q: String? = null, cursor: String? = null, limit: Int = 30): Page<Conversation> =
        get("/support/conversations", mapOf("company" to company, "state" to state, "channel" to channel, "q" to q?.trim()?.ifEmpty { null }, "limit" to limit, "cursor" to cursor))
    /** With its messages, oldest first. */
    suspend fun conversation(ref: String): Conversation {
        // The hub answers `{conversation, messages}` (SupportConversationDetail); a flat conversation with its messages is read too.
        val e = get<JsonElement>("/support/conversations/${seg(ref)}")
        return decoded("/support/conversations/{ref}") {
            val o = e as? JsonObject
            val inner = o?.get("conversation") as? JsonObject
            if (inner == null) json.decodeFromJsonElement(Conversation.serializer(), e)
            else json.decodeFromJsonElement(Conversation.serializer(), inner)
                .copy(messages = json.decodeFromJsonElement(kotlinx.serialization.builtins.ListSerializer(SupportMessage.serializer()), o["messages"] ?: JsonArray(emptyList())))
        }
    }
    suspend fun supportQueue(): List<QueueItem> = listOrPage("/support/queue", emptyMap(), QueueItem.serializer())
    /** Sent as the owner through the outbound guard: `422 send_blocked` with its reasons. [key]: one per text. */
    suspend fun reply(ref: String, body: String, key: String): SupportMessage =
        call(write("POST", "/support/conversations/${seg(ref)}/reply", buildJsonObject { put("body", body) }, null, key), serializer())
    /** Sends the answer (when the conversation waits) and opens a KB proposal from it. */
    suspend fun teach(ref: String, messageId: String?, answerMd: String, generalise: Boolean, key: String): TeachOut =
        call(write("POST", "/support/conversations/${seg(ref)}/teach", buildJsonObject {
            if (messageId != null) put("message_id", messageId)
            put("answer_md", answerMd); put("generalise", generalise)
        }, null, key), serializer())
    suspend fun closeConversation(ref: String): Conversation = post("/support/conversations/${seg(ref)}/close", JsonObject(emptyMap()))

    suspend fun kb(company: String? = null, kind: String? = null, status: String? = null, q: String? = null): List<KbArticle> =
        listOrPage("/support/kb", mapOf("company" to company, "kind" to kind, "status" to status, "q" to q?.trim()?.ifEmpty { null }), KbArticle.serializer())
    suspend fun proposeKb(body: KbArticleIn): KbArticle = post("/support/kb", json.encodeToJsonElement(KbArticleIn.serializer(), body))
    /** An approved article changes what may leave without the owner: sealed on `ref@version`. */
    suspend fun approveKb(a: KbArticle, stepUp: StepUp): KbArticle = post("/support/kb/${seg(a.ref)}/approve", JsonObject(emptyMap()), stepUp("support.kb", "${a.ref}@${a.version}"))
    suspend fun retireKb(ref: String): KbArticle = post("/support/kb/${seg(ref)}/retire", JsonObject(emptyMap()))
    /** The latest report of each company. */
    suspend fun shadowReports(): List<ShadowReport> = listOrPage("/support/shadow", emptyMap(), ShadowReport.serializer())
    /** A chat export (Telegram Desktop JSON or a CSV of question and answer), already uploaded through /files. */
    suspend fun supportHistory(company: String, fileId: String): HistoryOut = post("/support/history", buildJsonObject { put("company", company); put("file_id", fileId) })
    /** An academy eval run of the support charter on the company's suite (§18.6). */
    suspend fun runShadow(company: String): ShadowRunOut = post("/support/shadow/${seg(company)}/run", JsonObject(emptyMap()))

    suspend fun templates(company: String? = null): List<Template> = listOrPage("/growth/templates", mapOf("company" to company), Template.serializer())
    suspend fun rules(company: String? = null): List<LifecycleRule> = listOrPage("/growth/rules", mapOf("company" to company), LifecycleRule.serializer())
    suspend fun nps(company: String? = null): List<NpsWave> = listOrPage("/growth/nps", mapOf("company" to company), NpsWave.serializer())
    suspend fun proposeTemplate(body: TemplateIn): Template = post("/growth/templates", json.encodeToJsonElement(TemplateIn.serializer(), body))
    /** Bound to the exact body: `ref@version:sha256`. */
    suspend fun sealTemplate(t: Template, stepUp: StepUp): Template =
        post("/growth/templates/${seg(t.ref)}/seal", JsonObject(emptyMap()), stepUp("growth.template", "${t.ref}@${t.version}:${t.sha256}"))
    suspend fun createRule(body: LifecycleRuleIn): LifecycleRule = post("/growth/rules", json.encodeToJsonElement(LifecycleRuleIn.serializer(), body))
    /** The owner's A3 approval in advance; the rule's template version must be sealed (`409 template_not_sealed`). */
    suspend fun sealRule(r: LifecycleRule, stepUp: StepUp): LifecycleRule = post("/growth/rules/${seg(r.ref)}/seal", JsonObject(emptyMap()), stepUp("growth.rule", "${r.ref}@${r.version}"))
    suspend fun pauseRule(ref: String): LifecycleRule = post("/growth/rules/${seg(ref)}/pause", JsonObject(emptyMap()))
    suspend fun resumeRule(r: LifecycleRule, stepUp: StepUp): LifecycleRule = post("/growth/rules/${seg(r.ref)}/resume", JsonObject(emptyMap()), stepUp("growth.rule", "${r.ref}@${r.version}"))

    /** Most frequent first. */
    suspend fun feedback(company: String? = null, kind: String? = null, state: String? = null, cursor: String? = null, limit: Int = 50): Page<FeedbackItem> =
        get("/feedback", mapOf("company" to company, "kind" to kind, "state" to state, "limit" to limit, "cursor" to cursor))
    /** `If-Match` the item's version; [setWork] sends `work_ref` (null detaches it). */
    suspend fun patchFeedback(x: FeedbackItem, state: String? = null, workRef: String? = null, setWork: Boolean = false): FeedbackItem =
        send("PATCH", "/feedback/${seg(x.ref)}", json.encodeToString(JsonElement.serializer(), buildJsonObject {
            if (state != null) put("state", state)
            if (setWork) put("work_ref", workRef)
        }), ifMatch = x.version)

    suspend fun intakeSources(): List<IntakeSource> = listOrPage("/intake/sources", emptyMap(), IntakeSource.serializer())
    /** Sealed on the exact body (allowed IPs and kinds); the source's secret is set in the owner's terminal, never here. */
    suspend fun registerIntake(body: IntakeSourceIn, stepUp: StepUp): IntakeSource =
        sealedPost("/intake/sources", json.encodeToString(IntakeSourceIn.serializer(), body)) { stepUp("intake.source", it) }

    /** A POST whose step-up is bound to the SHA-256 of [text], the exact body sent. */
    private suspend inline fun <reified T> sealedPost(path: String, text: String, sign: (String) -> String): T {
        val token = sign(sha256(text))
        val req = Request.Builder().url(url(path)).post(text.toRequestBody(JSON))
            .header("Idempotency-Key", UUID.randomUUID().toString()).header("X-Step-Up", token).build()
        return call(req, serializer())
    }

    /** §19 names a cursor only on conversations, rescue cases and feedback; the other lists are read bare or paged. */
    private suspend fun <T> listOrPage(path: String, query: Map<String, Any?>, s: KSerializer<T>): List<T> {
        return decodeList(get<JsonElement>(path, query), s, null, path)
    }

    // ---------------------------------------------------- governance ⟨1.5⟩ --
    // Contract §20, in the shapes §20.12 ⟨1.5.1⟩ fixes. Every 🔏 write names its action and exact target here (§20.11): the charter
    // seal on the body_sha256 the server sent, the authority matrix and the meeting settings on the SHA-256 of the exact body, the
    // batch on the SHA-256 of its sorted [{ref, version}]. PATCH carries If-Match; POST /meetings, speak and the batch carry the
    // caller's Idempotency-Key, kept across retries of one press.
    suspend fun meetings(type: String? = null, company: String? = null, state: String? = null, from: String? = null, to: String? = null): List<Meeting> =
        listAny("/meetings", mapOf("type" to type, "company" to company, "state" to state, "from" to from, "to" to to, "limit" to 100), Meeting.serializer())
    /** With its items, budget estimate, `trimmed_fa` and drafts. */
    suspend fun meeting(ref: String): Meeting = get("/meetings/${seg(ref)}")
    /** The owner's page carries the advisor's whispers too. */
    suspend fun turns(ref: String): TurnsPage = get("/meetings/${seg(ref)}/turns", mapOf("limit" to 200))
    /** An ad-hoc meeting: same speaker rule, budget and daily share as a scheduled one. */
    suspend fun createMeeting(type: String, company: String?, startsAt: String, items: List<MeetingItemIn>, key: String): Meeting =
        call(write("POST", "/meetings", buildJsonObject {
            put("type", type); if (company != null) put("company", company); put("starts_at", startsAt)
            put("items", json.encodeToJsonElement(kotlinx.serialization.builtins.ListSerializer(MeetingItemIn.serializer()), items))
        }, null, key), serializer())
    /** Before or during a meeting: the items in their new order (each may be skipped), a lower cap, the owner's presence. */
    suspend fun patchMeeting(m: Meeting, items: List<ItemOrder>? = null, budgetCap: Long? = null, ownerPresence: String? = null): Meeting =
        send("PATCH", "/meetings/${seg(m.ref)}", json.encodeToString(JsonElement.serializer(), buildJsonObject {
            if (items != null) put("items", json.encodeToJsonElement(kotlinx.serialization.builtins.ListSerializer(ItemOrder.serializer()), items))
            if (budgetCap != null) put("budget_cap", budgetCap)
            if (ownerPresence != null) put("owner_presence", ownerPresence)
        }), ifMatch = m.version)
    /** The owner jumps the queue; `409 meeting_not_live` otherwise. A voice file goes through §17.2 first. */
    suspend fun speak(ref: String, text: String?, fileId: String?, key: String): Turn =
        call(write("POST", "/meetings/${seg(ref)}/speak", buildJsonObject {
            if (!text.isNullOrBlank()) put("text", text)
            if (fileId != null) put("file_id", fileId)
        }, null, key), serializer())
    /** next_round · skip_item · end · raise_budget (with [tokens]); only the owner raises a budget. */
    suspend fun meetingControl(ref: String, action: String, tokens: Long? = null): Meeting =
        post("/meetings/${seg(ref)}/control", buildJsonObject { put("action", action); if (tokens != null) put("tokens", tokens) })
    suspend fun meetingSettings(): List<MeetingType> = listAny("/meetings/settings", emptyMap(), MeetingType.serializer(), wrap = "types")
    /** The whole list `{types}`, no If-Match (each row carries its version), sealed on the SHA-256 of the exact body. */
    suspend fun saveMeetingSettings(types: List<MeetingType>, stepUp: StepUp): List<MeetingType> {
        val text = jsonBody.encodeToString(JsonElement.serializer(), buildJsonObject {
            put("types", jsonBody.encodeToJsonElement(kotlinx.serialization.builtins.ListSerializer(MeetingType.serializer()), types))
        })
        val e: JsonElement = send("PUT", "/meetings/settings", text, stepUp = stepUp("meetings.settings", sha256(text)))
        return decodeList(e, MeetingType.serializer(), "types", "PUT /meetings/settings")
    }

    /** The sealed holding charter and every addendum the principal may read. */
    suspend fun charter(): List<CharterScope> = listAny("/charter", emptyMap(), CharterScope.serializer(), wrap = "scopes")
    suspend fun charterVersions(scope: String): List<Charter> = listAny("/charter/${seg(scope)}/versions", emptyMap(), Charter.serializer())
    suspend fun charterVersion(scope: String, version: Int): Charter = get("/charter/${seg(scope)}/versions/$version")
    /** A unified diff computed on the server. */
    suspend fun charterDiff(scope: String, version: Int, against: Int): CharterDiff = get("/charter/${seg(scope)}/versions/$version/diff", mapOf("against" to against))
    /** A new `proposed` version; nothing reaches an agent until it is sealed. */
    suspend fun proposeCharter(scope: String, body: CharterIn): Charter = send("PUT", "/charter/${seg(scope)}", jsonBody.encodeToString(CharterIn.serializer(), body))
    /** Sealed on the version's body_sha256, which the server recomputes: a token for one text cannot seal another or weaker red lines. */
    suspend fun sealCharter(c: Charter, stepUp: StepUp): Charter =
        post("/charter/${seg(c.scope)}/versions/${c.version}/seal", JsonObject(emptyMap()), stepUp("charter.seal", c.bodySha256))

    suspend fun knowledge(layer: String? = null, company: String? = null, department: String? = null, kind: String? = null, status: String? = null, q: String? = null, includeExpired: Boolean = false, cursor: String? = null): Page<KnowledgeEntry> =
        get("/knowledge", mapOf(
            "layer" to layer, "company" to company, "department" to department, "kind" to kind, "status" to status, "q" to q?.trim()?.ifEmpty { null },
            "include_expired" to (if (includeExpired) true else null), "limit" to 50, "cursor" to cursor,
        ))
    suspend fun knowledgeEntry(ref: String): KnowledgeEntry = get("/knowledge/${seg(ref)}")
    suspend fun knowledgeVersions(ref: String): List<KnowledgeEntry> = listAny("/knowledge/${seg(ref)}/versions", emptyMap(), KnowledgeEntry.serializer())
    /** What the owner writes is approved by that act. */
    suspend fun createKnowledge(body: KnowledgeIn): KnowledgeEntry = post("/knowledge", json.encodeToJsonElement(KnowledgeIn.serializer(), body))
    suspend fun updateKnowledge(ref: String, body: KnowledgeIn): KnowledgeEntry = send("PUT", "/knowledge/${seg(ref)}", json.encodeToString(KnowledgeIn.serializer(), body))
    suspend fun retireKnowledge(ref: String): KnowledgeEntry = post("/knowledge/${seg(ref)}/retire", JsonObject(emptyMap()))

    /** The three cards; [company] null = the holding (the server's default). */
    suspend fun cards(company: String? = null): List<KpiCard> = listAny("/cards", mapOf("company" to company), KpiCard.serializer())
    suspend fun scorecards(q: String? = null, cursor: String? = null): Page<ScorecardRow> =
        get("/scorecards", mapOf("q" to q?.trim()?.ifEmpty { null }, "limit" to 50, "cursor" to cursor))
    suspend fun kpis(company: String): KpiSet = get("/kpis/${seg(company)}")
    suspend fun kpiValues(company: String, key: String, from: String, to: String): List<KpiValue> =
        listAny("/kpis/${seg(company)}/${seg(key)}/values", mapOf("from" to from, "to" to to), KpiValue.serializer())
    /** Targets, scorecard membership, status and freshness; If-Match on the company's set. */
    suspend fun putKpis(set: KpiSet, kpis: List<KpiPatch>): KpiSet =
        send("PUT", "/kpis/${seg(set.company)}", jsonBody.encodeToString(JsonElement.serializer(), buildJsonObject {
            put("kpis", jsonBody.encodeToJsonElement(kotlinx.serialization.builtins.ListSerializer(KpiPatch.serializer()), kpis))
        }), ifMatch = set.version)

    suspend fun okr(company: String? = null, quarter: String? = null, status: String? = null): List<Objective> =
        listAny("/okr", mapOf("company" to company, "quarter" to quarter, "status" to status), Objective.serializer())
    suspend fun objective(ref: String): Objective = get("/okr/${seg(ref)}")
    /** [due]: due now or overdue (⟨1.5.1⟩). */
    suspend fun outcomes(company: String? = null, verdict: String? = null, due: Boolean = false, decision: String? = null, cursor: String? = null): Page<OutcomeReview> =
        get("/outcomes", mapOf("company" to company, "verdict" to verdict, "due" to (if (due) true else null), "decision" to decision, "limit" to 100, "cursor" to cursor))

    /** The whole matrix with its locked rows. */
    suspend fun authority(): List<AuthorityRule> = listAny("/authority", emptyMap(), AuthorityRule.serializer(), wrap = "rules")
    /** Unlocked rows only, inside their bounds (`422` otherwise); sealed on the SHA-256 of the exact body `{rules}`. */
    suspend fun putAuthority(changes: List<AuthorityChange>, stepUp: StepUp) {
        val text = json.encodeToString(JsonElement.serializer(), buildJsonObject {
            put("rules", JsonArray(changes.map { c ->
                buildJsonObject { put("key", c.key); if (c.actor != null) put("actor", c.actor); put("limit", c.limit ?: JsonNull); put("version", c.version) }
            }))
        })
        execute(Request.Builder().url(url("/authority")).put(text.toRequestBody(JSON)).header("X-Step-Up", stepUp("authority.update", sha256(text))).build()).use { check(it) }
    }

    suspend fun risks(company: String? = null, status: String? = null, category: String? = null, minScore: Int? = null, cursor: String? = null): Page<Risk> =
        get("/risks", mapOf("company" to company, "status" to status, "category" to category, "min_score" to minScore, "limit" to 100, "cursor" to cursor))
    suspend fun risk(ref: String): Risk = get("/risks/${seg(ref)}")
    suspend fun riskMatrix(company: String? = null): RiskMatrix = get("/risks/matrix", mapOf("company" to company))
    suspend fun createRisk(body: RiskIn): Risk = post("/risks", json.encodeToJsonElement(RiskIn.serializer(), body))
    /** If-Match the risk's version; [patch] holds only what changed (a null clears it). */
    suspend fun patchRisk(r: Risk, patch: JsonObject): Risk = send("PATCH", "/risks/${seg(r.ref)}", json.encodeToString(JsonElement.serializer(), patch), ifMatch = r.version)

    /** Events and their conflicts in the range. */
    suspend fun calendar(company: String? = null, from: String? = null, to: String? = null, kind: String? = null): CalendarView =
        get("/calendar", mapOf("company" to company, "from" to from, "to" to to, "kind" to kind))
    suspend fun createEvent(body: CalendarIn): CalendarEvent = post("/calendar", jsonBody.encodeToJsonElement(CalendarIn.serializer(), body))
    /** If-Match when the server gave the event a version (⟨1.5.1⟩). */
    suspend fun patchEvent(e: CalendarEvent, status: String): CalendarEvent =
        send("PATCH", "/calendar/${seg(e.ref)}", json.encodeToString(JsonElement.serializer(), buildJsonObject { put("status", status) }), ifMatch = e.version)

    /** The pending cards that may be sealed together. */
    suspend fun batchable(): List<Batchable> = listAny("/decisions/batchable", emptyMap(), Batchable.serializer())
    /** All or nothing (`422 batch_not_eligible` with each card's reason). The passkey is bound to the SHA-256 of the sorted
     *  `[{ref, version}]`; [key] is the press's, kept for a retry of the same set. */
    suspend fun batchApprove(items: List<BatchItem>, key: String, stepUp: StepUp): BatchOut {
        val set = batchItems(items)
        val list = json.encodeToJsonElement(kotlinx.serialization.builtins.ListSerializer(BatchItem.serializer()), set)
        val token = stepUp("decision.batch", sha256(json.encodeToString(JsonElement.serializer(), list)))
        return call(write("POST", "/decisions/batch/approve", buildJsonObject { put("items", list) }, token, key), serializer())
    }

    /** A list read bare, paged, or wrapped in [wrap] (`{types}`, `{scopes}`, `{rules}`): §20 names a cursor only where it says Page. */
    private suspend fun <T> listAny(path: String, query: Map<String, Any?>, s: KSerializer<T>, wrap: String? = null): List<T> =
        decodeList(get<JsonElement>(path, query), s, wrap, path)

    private fun <T> decodeList(e: JsonElement, s: KSerializer<T>, wrap: String? = null, path: String = "?"): List<T> = try {
        val items = when {
            e is JsonArray -> e
            e is JsonObject && wrap != null && e[wrap] is JsonArray -> e[wrap]!!
            e is JsonObject -> e["items"] ?: JsonArray(emptyList())
            else -> JsonArray(emptyList())
        }
        json.decodeFromJsonElement(kotlinx.serialization.builtins.ListSerializer(s), items)
    } catch (x: IllegalArgumentException) {
        val (m, pth) = if (path.contains(' ')) path.substringBefore(' ') to path.substringAfter(' ') else "GET" to path
        // A tree decoder's complaint has no JSON path; the same answer read as text names it (for the error log).
        val withPath = runCatching { json.decodeFromString(kotlinx.serialization.builtins.ListSerializer(s), (if (e is JsonObject && wrap != null && e[wrap] is JsonArray) e[wrap]!! else if (e is JsonObject) e["items"] ?: e else e).toString()) }.exceptionOrNull()
        throw mismatch(200, m, pth, withPath ?: x)
    }

    // ----------------------------------------------- management tools ⟨1.5⟩ --
    // Contract §21, in the shapes §21.14 ⟨1.5.1⟩ fixes. Every 🔏 write names its action and exact target here (§21.12): a new connection
    // and the seats on the SHA-256 of the exact body, a CLI sign-in and sign-out on the connection id, a browser profile on the player.
    // PATCH and PUT carry If-Match; an ask, a note, a creative and a new connection carry the caller's Idempotency-Key, kept across
    // retries of one press. A thing that does not exist yet (a memo, the current review, a briefing) answers 404: null here.
    /** The latest memo of a card in one mode, or null while none was asked for. */
    suspend fun memo(ref: String, mode: String): DecisionMemo? = orNull { get("/decisions/${seg(ref)}/memo", mapOf("mode" to mode)) }
    /** Idempotent per card, mode and card version; a decided card is `409 decision_not_pending`. */
    suspend fun requestMemo(ref: String, mode: String): DecisionMemo = post("/decisions/${seg(ref)}/memo", buildJsonObject { put("mode", mode) })
    suspend fun memos(decision: String? = null, cursor: String? = null): Page<DecisionMemo> = get("/advisor/memos", mapOf("decision" to decision, "limit" to 30, "cursor" to cursor))
    suspend fun advisorTriggers(since: String? = null, kind: String? = null): List<AdvisorTrigger> = listAny("/advisor/triggers", mapOf("since" to since, "kind" to kind), AdvisorTrigger.serializer())

    /** Owner only, ≤ 500 characters; [key] is the press's. */
    suspend fun askHub(q: String, companies: List<String>, key: String): Ask =
        call(write("POST", "/ask", buildJsonObject { put("q", q); if (companies.isNotEmpty()) put("scope", buildJsonObject { put("companies", ids(companies)) }) }, null, key), serializer())
    suspend fun asked(ref: String): Ask = get("/ask/${seg(ref)}")
    suspend fun asks(cursor: String? = null): Page<Ask> = get("/ask", mapOf("limit" to 20, "cursor" to cursor))

    suspend fun weeklyReviews(): List<WeeklyReview> = listAny("/reviews/weekly", emptyMap(), WeeklyReview.serializer())
    suspend fun currentReview(): WeeklyReview? = orNull { get("/reviews/weekly/current") }
    suspend fun startReview(ref: String): WeeklyReview = post("/reviews/weekly/${seg(ref)}/start", JsonObject(emptyMap()))
    /** Writes the minutes as a deliverable O-… by HQ-ADV. */
    suspend fun finishReview(ref: String): WeeklyReview = post("/reviews/weekly/${seg(ref)}/finish", JsonObject(emptyMap()))
    suspend fun reviewItem(r: WeeklyReview, n: Int, status: String, ownerNote: String? = null): WeeklyReview =
        send("PATCH", "/reviews/weekly/${seg(r.ref)}/items/$n", json.encodeToString(JsonElement.serializer(), buildJsonObject {
            put("status", status); if (ownerNote != null) put("owner_note", ownerNote)
        }), ifMatch = r.version)

    suspend fun briefings(kind: String? = null, company: String? = null, cursor: String? = null): Page<Briefing> =
        get("/briefings", mapOf("kind" to kind, "company" to company, "limit" to 30, "cursor" to cursor))
    suspend fun latestBriefing(kind: String, company: String? = null): Briefing? = orNull { get("/briefings/latest", mapOf("kind" to kind, "company" to company)) }
    suspend fun briefing(ref: String): Briefing = get("/briefings/${seg(ref)}")

    suspend fun departmentRanks(period: String, company: String? = null, key: String? = null): List<DepartmentRank> =
        listAny("/rankings/departments", mapOf("period" to period, "key" to key, "company" to company), DepartmentRank.serializer())
    suspend fun hrRounds(company: String? = null, month: String? = null): List<HrRound> = listAny("/hr/rounds", mapOf("company" to company, "month" to month), HrRound.serializer())
    suspend fun hrRound(ref: String): HrRound = get("/hr/rounds/${seg(ref)}")

    /** ⟨1.5.1⟩ one file of a deploy card's diff with its whole patch (≤ 2000 lines, masked the same way), `truncated: false`. */
    suspend fun diffFile(ref: String, path: String): DiffFile = get("/decisions/${seg(ref)}/diff", mapOf("file" to path))

    suspend fun wasteDay(day: String? = null, company: String? = null): WasteDay = get("/treasury/waste", mapOf("day" to day, "company" to company))
    suspend fun wasteRange(from: String, to: String, company: String? = null): List<WasteDay> =
        listAny("/treasury/waste", mapOf("from" to from, "to" to to, "company" to company), WasteDay.serializer())
    suspend fun roi(by: String, period: String, company: String? = null, key: String? = null): List<RoiRow> =
        listAny("/treasury/roi", mapOf("by" to by, "period" to period, "key" to key, "company" to company), RoiRow.serializer())
    /** 🔏 `connection.create`, sealed on the SHA-256 of the exact body; the Idempotency-Key is required ([key], one per wizard). The
     *  result is `pending_secret`: its key goes through [connectionSecret] or the owner's own terminal. */
    suspend fun createConnection(body: ConnectionIn, key: String, stepUp: StepUp): Connection {
        val text = json.encodeToString(ConnectionIn.serializer(), body)
        val req = Request.Builder().url(url("/connections")).post(text.toRequestBody(JSON))
            .header("Idempotency-Key", key).header("X-Step-Up", stepUp("connection.create", sha256(text))).build()
        return call(req, serializer())
    }

    suspend fun notes(status: String? = null, q: String? = null, cursor: String? = null): Page<OwnerNote> =
        get("/notes", mapOf("status" to status, "q" to q?.trim()?.ifEmpty { null }, "limit" to 50, "cursor" to cursor))
    suspend fun createNote(text: String, source: String, fileId: String?, tags: List<String>, key: String): OwnerNote =
        call(write("POST", "/notes", buildJsonObject {
            put("text_md", text); put("source", source); if (fileId != null) put("file_id", fileId); if (tags.isNotEmpty()) put("tags", ids(tags))
        }, null, key), serializer())
    /** No delete: archiving ([archive]) is the end of a note. If-Match the note's version. */
    suspend fun patchNote(n: OwnerNote, text: String? = null, tags: List<String>? = null, archive: Boolean = false): OwnerNote =
        send("PATCH", "/notes/${seg(n.ref)}", json.encodeToString(JsonElement.serializer(), buildJsonObject {
            if (text != null) put("text_md", text); if (tags != null) put("tags", ids(tags)); if (archive) put("status", "archived")
        }), ifMatch = n.version)
    /** ⟨1.5.1⟩ `{to, company?, title?}`; `company` is required for work. */
    suspend fun promoteNote(ref: String, to: String, company: String? = null, title: String? = null): OwnerNote =
        post("/notes/${seg(ref)}/promote", buildJsonObject { put("to", to); if (company != null) put("company", company); if (title != null) put("title", title) })

    suspend fun claims(company: String? = null, employee: String? = null, verdict: String? = null, cursor: String? = null): Page<CheckedClaim> =
        get("/claims", mapOf("company" to company, "employee" to employee, "verdict" to verdict, "limit" to 30, "cursor" to cursor))
    suspend fun runsHealth(period: String, company: String? = null, cursor: String? = null): Page<AgentHealth> =
        get("/runs/health", mapOf("company" to company, "period" to period, "limit" to 100, "cursor" to cursor))

    suspend fun digitalCeo(): DceoView = get("/digital-ceo")
    suspend fun predictions(correct: Boolean? = null, kind: String? = null, cursor: String? = null): Page<Prediction> =
        get("/digital-ceo/predictions", mapOf("correct" to correct, "kind" to kind, "limit" to 50, "cursor" to cursor))
    suspend fun principles(): List<Principle> = listAny("/digital-ceo/principles", emptyMap(), Principle.serializer())
    /** The owner's own principle is active at once. */
    suspend fun addPrinciple(text: String): Principle = post("/digital-ceo/principles", buildJsonObject { put("text_fa", text) })
    /** ⟨1.5.1⟩ an edit or a retirement is a new version: `{text_fa, status}` with If-Match. */
    suspend fun editPrinciple(p: Principle, text: String, status: String): Principle =
        send("PUT", "/digital-ceo/principles/${seg(p.ref)}", json.encodeToString(JsonElement.serializer(), buildJsonObject { put("text_fa", text); put("status", status) }), ifMatch = p.version)
    suspend fun acceptPrinciple(ref: String): Principle = post("/digital-ceo/principles/${seg(ref)}/accept", JsonObject(emptyMap()))

    /** ⟨1.5.1⟩ each changed §21.12 block whole ([blocks], from [ManagementSettings.changedFrom]), If-Match the settings' version. */
    suspend fun saveOwnerSettings(version: Int, blocks: Map<String, JsonElement>): OwnerSettings =
        send("PUT", "/owner/settings", json.encodeToString(JsonElement.serializer(), JsonObject(blocks)), ifMatch = version)

    suspend fun substitutes(): List<Substitute> = listAny("/substitutes", emptyMap(), Substitute.serializer())
    /** 🔏 `substitute.seats`, sealed on the SHA-256 of the exact list, with the player's version. */
    suspend fun putSeats(s: Substitute, seats: List<SeatIn>, stepUp: StepUp): Substitute {
        val text = json.encodeToString(kotlinx.serialization.builtins.ListSerializer(SeatIn.serializer()), seats)
        return send("PUT", "/substitutes/${seg(s.player)}/seats", text, ifMatch = s.version, stepUp = stepUp("substitute.seats", sha256(text)))
    }
    /** 🔏 `substitute.web_logout` on the player: wipes the signed-in browser profile; signing in again is the owner's terminal. */
    suspend fun webLogout(player: String, stepUp: StepUp): Substitute = post("/substitutes/${seg(player)}/web/logout", JsonObject(emptyMap()), stepUp("substitute.web_logout", player))
    /** 🔏 `connection.login` on the id: the CLI's own headless sign-in; `409 not_ready` when it has none (the app shows the command). */
    suspend fun connectionLogin(id: String, stepUp: StepUp): SubstituteLogin = post("/connections/${seg(id)}/login", JsonObject(emptyMap()), stepUp("connection.login", id))
    suspend fun connectionLoginState(id: String, loginId: String): SubstituteLogin = get("/connections/${seg(id)}/login/${seg(loginId)}")
    /** Write-only, `auth_code` logins only, while waiting; covered by the start's step-up (≤ 10 minutes). */
    suspend fun connectionLoginCode(id: String, loginId: String, code: String): SubstituteLogin =
        post("/connections/${seg(id)}/login/${seg(loginId)}/code", buildJsonObject { put("code", code) })
    /** ⟨1.5.1⟩ 🔏 `connection.logout` on the id: removes the stored sign-in. */
    suspend fun connectionLogout(id: String, stepUp: StepUp) = postUnit("/connections/${seg(id)}/logout", JsonObject(emptyMap()), stepUp("connection.logout", id))

    suspend fun creatives(company: String? = null, state: String? = null, kind: String? = null, cursor: String? = null): Page<Creative> =
        get("/creatives", mapOf("company" to company, "state" to state, "kind" to kind, "limit" to 30, "cursor" to cursor))
    suspend fun creative(ref: String): Creative = get("/creatives/${seg(ref)}")
    /** The owner's brief; the Claude agent in charge writes the prompt. A video is Gemini's and ≤ 10 s. [key] is the press's. */
    suspend fun createCreative(company: String, kind: String, brief: String, placement: String, overlay: Overlay?, durationS: Int?, player: String?, key: String): Creative =
        call(write("POST", "/creatives", buildJsonObject {
            put("company", company); put("kind", kind); put("brief_md", brief); put("placement", placement)
            if (overlay != null) put("overlay", jsonBody.encodeToJsonElement(Overlay.serializer(), overlay))
            if (durationS != null) put("duration_s", durationS)
            if (player != null) put("player", player)
        }, null, key), serializer())
    /** ⟨1.9⟩ §27.2: the owner's pick among a media council's Creatives. */
    suspend fun pickCreative(ref: String): Creative = post("/creatives/${seg(ref)}/pick", JsonObject(emptyMap()))
    /** ⟨1.9⟩ §27.2: a video made from the picked image (a new Creative). */
    suspend fun animateCreative(ref: String): Creative = post("/creatives/${seg(ref)}/animate", JsonObject(emptyMap()))
    suspend fun acceptCreative(ref: String, note: String? = null): Creative = post("/creatives/${seg(ref)}/accept", buildJsonObject { if (!note.isNullOrBlank()) put("note", note) })
    suspend fun rejectCreative(ref: String, note: String? = null): Creative = post("/creatives/${seg(ref)}/reject", buildJsonObject { if (!note.isNullOrBlank()) put("note", note) })

    // ------------------------------------- the media studio and the legal counsel ⟨1.6⟩ --
    // Contract §22, in the shapes §22.7 ⟨1.6.1⟩ fixes. Every 🔏 write names its action and exact target here (§22.6): a department's
    // mandate on the SHA-256 of the exact body, a series on its digest, an unpublish on the item's ref, a voice on its id; an
    // `email_send` card is approved on the message digest ([sealTarget]). PUT carries If-Match; a new series, item, case and role
    // carry the caller's Idempotency-Key, kept across retries of one press. Publishing outside a sealed series has one path: the
    // item's `media_publish` card. The owner's voice reference answers 404 while there is none: null here.
    /** 🔏 `department.mandate`, sealed on the SHA-256 of exactly `{mandate, identity_md}`, If-Match the department's version. */
    suspend fun putMandate(company: String, d: Department, body: MandateIn, stepUp: StepUp): Department {
        val text = jsonBody.encodeToString(MandateIn.serializer(), body)
        return send("PUT", "/companies/${seg(company)}/departments/${seg(d.code)}/mandate", text, ifMatch = d.version, stepUp = stepUp("department.mandate", sha256(text)))
    }
    suspend fun roleDrafts(company: String? = null, department: String? = null, state: String? = null): List<RoleDraft> =
        listAny("/roles/drafts", mapOf("company" to company, "department" to department, "state" to state), RoleDraft.serializer())
    suspend fun roleDraft(ref: String): RoleDraft = get("/roles/drafts/${seg(ref)}")
    /** The owner asks («یه تدوینگر پادکست میخوام»); the department's manager is woken to write it. [key] is the press's. */
    suspend fun askRole(company: String, department: String, briefMd: String, key: String): RoleDraft =
        call(write("POST", "/roles/drafts", buildJsonObject { put("company", company); put("department", department); put("brief_md", briefMd) }, null, key), serializer())
    /** Stops new hires on it; employees on it keep running until moved or dismissed. No step-up. */
    suspend fun retireRoleDraft(ref: String): RoleDraft = post("/roles/drafts/${seg(ref)}/retire", JsonObject(emptyMap()))

    suspend fun series(company: String? = null, status: String? = null): List<Series> =
        listAny("/media/series", mapOf("company" to company, "status" to status), Series.serializer())
    /** A `draft`: nothing runs until it is sealed. Written whole; [key] is the press's. */
    suspend fun createSeries(body: SeriesIn, key: String): Series =
        call(write("POST", "/media/series", jsonBody.encodeToJsonElement(SeriesIn.serializer(), body), null, key), serializer())
    /** If-Match the series' version; a sealed series edited goes back to `proposed` (its seal no longer covers it). */
    suspend fun updateSeries(s: Series, body: SeriesIn): Series =
        send("PUT", "/media/series/${seg(s.ref)}", jsonBody.encodeToString(SeriesIn.serializer(), body), ifMatch = s.version)
    /** 🔏 `media.series` on the series digest, which the body names too: a changed series answers `409 version_conflict`. */
    suspend fun sealSeries(s: Series, stepUp: StepUp): Series =
        post("/media/series/${seg(s.ref)}/seal", buildJsonObject { put("digest", s.digest) }, stepUp("media.series", s.digest))
    suspend fun pauseSeries(ref: String): Series = post("/media/series/${seg(ref)}/pause", JsonObject(emptyMap()))
    suspend fun retireSeries(ref: String): Series = post("/media/series/${seg(ref)}/retire", JsonObject(emptyMap()))

    suspend fun mediaItems(company: String? = null, series: String? = null, state: String? = null, cursor: String? = null): Page<MediaItem> =
        get("/media/items", mapOf("company" to company, "series" to series, "state" to state, "limit" to 100, "cursor" to cursor))
    suspend fun mediaItem(ref: String): MediaItem = get("/media/items/${seg(ref)}")
    /** A one-off (it always ends as a card) or a `design` (a UI mockup for the CTO, never published). [key] is the press's. */
    suspend fun createMediaItem(company: String, kind: String, briefMd: String, series: String? = null, key: String): MediaItem =
        call(write("POST", "/media/items", buildJsonObject {
            put("company", company); put("kind", kind); put("brief_md", briefMd); if (series != null) put("series", series)
        }, null, key), serializer())
    /** 🔏 `media.unpublish` on the ref: deleted through the same official API where the platform allows it. */
    suspend fun unpublish(ref: String, stepUp: StepUp): MediaItem = post("/media/items/${seg(ref)}/unpublish", JsonObject(emptyMap()), stepUp("media.unpublish", ref))
    suspend fun mediaLimits(): List<PlatformLimit> = listAny("/media/limits", emptyMap(), PlatformLimit.serializer())

    suspend fun voices(): List<Voice> = listAny("/media/voices", emptyMap(), Voice.serializer())
    /** The owner's own reference recording, or null while none was recorded. */
    suspend fun voiceReference(): VoiceReference? = orNull { get("/media/voices/reference") }
    /** Owner only, 1–3 minutes of clean speech, already uploaded through /files; never sent anywhere. */
    suspend fun setVoiceReference(fileId: String): VoiceReference = post("/media/voices/reference", buildJsonObject { put("file_id", fileId) })
    /** The owner's blind listening score, 1..10. */
    suspend fun scoreVoice(id: String, score: Int): Voice = post("/media/voices/${seg(id)}/score", buildJsonObject { put("score", score) })
    /** 🔏 `voice.activate` on the id; a non-commercial voice is acknowledged in the body (`422` without it), an unmeasured one `409 not_ready`. */
    suspend fun activateVoice(v: Voice, stepUp: StepUp): Voice =
        post("/media/voices/${seg(v.id)}/activate", if (v.licenceCommercial) JsonObject(emptyMap()) else buildJsonObject { put("accept_non_commercial", true) }, stepUp("voice.activate", v.id))

    suspend fun cases(company: String? = null, status: String? = null, cursor: String? = null): Page<LegalCase> =
        get("/legal/cases", mapOf("company" to company, "status" to status, "limit" to 50, "cursor" to cursor))
    /** With the whole timeline and the email thread. */
    suspend fun legalCase(ref: String): LegalCase = get("/legal/cases/${seg(ref)}")
    /** The owner opens a case for any company or the holding; the counsel is woken. [key] is the press's. */
    suspend fun openCase(company: String, titleFa: String, kind: String, briefMd: String, fileIds: List<String>, key: String): LegalCase =
        call(write("POST", "/legal/cases", buildJsonObject {
            put("company", company); put("title_fa", titleFa); put("kind", kind); put("brief_md", briefMd); if (fileIds.isNotEmpty()) put("file_ids", ids(fileIds))
        }, null, key), serializer())
    /** Owner; `409` while an email waits for its seal. */
    suspend fun closeCase(ref: String): LegalCase = post("/legal/cases/${seg(ref)}/close", JsonObject(emptyMap()))

    // ------------------------------------------------------------------- the archive ⟨1.7⟩ --
    // Contract §23, in the shapes §23.12 ⟨1.7.1⟩ fixes. Every 🔏 write names its action and exact target here (§23.11): a schema change on the
    // SHA-256 of the exact body (`archive.schema`, or `archive.clearance` for the clearance part), its retirement on the hash of
    // `{part, key, version}`, a seal on the current version's manifest, a declassification on `ref@version:level`, a file of a level that
    // needs it on the ref (`archive.view`), a hold's release on its ref. PATCH, a draft's filing and a schema save carry If-Match (a new key
    // `If-None-Match: *`); a new record, party and hold carry the caller's Idempotency-Key, kept across retries of one press.
    suspend fun archiveSchema(): ArchiveSchema = get<JsonObject>("/archive/schema").let { o -> decoded("/archive/schema") { ArchiveSchema(o) } }

    /** The impact (and the server's validation, `422 schema_invalid` with `fields`) before the passkey: nothing is applied. */
    suspend fun schemaPreview(part: String, key: String, body: JsonObject, version: Int?): SchemaResult =
        schemaPut(part, key, json.encodeToString(JsonElement.serializer(), body), version, dryRun = true, stepUp = null)

    /** 🔏 `archive.schema` (or `archive.clearance`) on the SHA-256 of the exact body; If-Match the row, `If-None-Match: *` for a new key. */
    suspend fun schemaSave(part: String, key: String, body: JsonObject, version: Int?, stepUp: StepUp): SchemaResult {
        val text = json.encodeToString(JsonElement.serializer(), body)
        return schemaPut(part, key, text, version, dryRun = false, stepUp = stepUp(schemaAction(part), sha256(text)))
    }

    private suspend fun schemaPut(part: String, key: String, text: String, version: Int?, dryRun: Boolean, stepUp: String?): SchemaResult {
        val req = Request.Builder().url(url("/archive/schema/${seg(part)}/${seg(key)}", mapOf("dry_run" to if (dryRun) 1 else null))).put(text.toRequestBody(JSON))
            .apply {
                if (version != null && version > 0) header("If-Match", "\"$version\"") else header("If-None-Match", "*")
                if (stepUp != null) header("X-Step-Up", stepUp)
            }.build()
        return call(req, serializer())
    }

    suspend fun schemaRetirePreview(part: String, key: String, version: Int): SchemaResult =
        call(write("POST", "/archive/schema/${seg(part)}/${seg(key)}/retire", retireBody(part, key, version), null, query = mapOf("dry_run" to 1)), serializer())

    /** Nothing that uses it is deleted; the same action as a save, on the hash of `{part, key, version}`. */
    suspend fun schemaRetire(part: String, key: String, version: Int, stepUp: StepUp): SchemaResult {
        val text = json.encodeToString(JsonElement.serializer(), retireBody(part, key, version))
        val req = Request.Builder().url(url("/archive/schema/${seg(part)}/${seg(key)}/retire")).post(text.toRequestBody(JSON))
            .header("Idempotency-Key", UUID.randomUUID().toString()).header("X-Step-Up", stepUp(schemaAction(part), sha256(text))).build()
        return call(req, serializer())
    }

    private fun retireBody(part: String, key: String, version: Int) = buildJsonObject { put("part", part); put("key", key); put("version", version) }
    private fun schemaAction(part: String) = if (part == "clearance") "archive.clearance" else "archive.schema"

    suspend fun archiveSources(): List<SourceSwitch> = listAny("/archive/sources", emptyMap(), SourceSwitch.serializer())
    /** Owner: `{key: on}` for the switches that change. */
    suspend fun setSources(changes: Map<String, Boolean>): List<SourceSwitch> =
        decodeList(send<JsonElement>("PUT", "/archive/sources", json.encodeToString(JsonElement.serializer(), JsonObject(changes.mapValues { JsonPrimitive(it.value) }))), SourceSwitch.serializer(), path = "PUT /archive/sources")

    /** Only what the reader's clearance allows. */
    suspend fun records(f: RecordFilters, cursor: String? = null): Page<ArchiveRecord> = get("/archive/records", f.query() + mapOf("limit" to 50, "cursor" to cursor))
    /** Persian-normalised full text over the title, searchable fields and file text; clearance-filtered before ranking. */
    suspend fun archiveSearch(q: String, scope: String? = null, cls: String? = null, level: String? = null, from: String? = null, to: String? = null): List<ArchiveHit> =
        listAny("/archive/search", mapOf("q" to q.trim(), "scope" to scope, "class" to cls, "level" to level, "from" to from, "to" to to), ArchiveHit.serializer())
    /** With its versions, links, holds and reminders; `403 clearance` where the reader knows the ref but may not see it. */
    suspend fun record(ref: String): ArchiveRecord = get("/archive/records/${seg(ref)}")
    /** Owner only: who viewed or downloaded what, and every level change. */
    suspend fun accessLog(ref: String): List<AccessRow> = listAny("/archive/records/${seg(ref)}/access", emptyMap(), AccessRow.serializer())

    /** The owner may file at once (`file: true`); otherwise a draft. The Idempotency-Key is required: [key] is the press's. */
    suspend fun createRecord(body: RecordIn, key: String): ArchiveRecord =
        call(write("POST", "/archive/records", json.encodeToJsonElement(RecordIn.serializer(), body), null, key), serializer())
    /** If-Match the row; a sealed record answers `409 sealed_record` unless [body] is only `level`, a held one `423 held`. The level only goes up here. */
    suspend fun patchRecord(r: ArchiveRecord, body: JsonObject): ArchiveRecord =
        send("PATCH", "/archive/records/${seg(r.ref)}", json.encodeToString(JsonElement.serializer(), body), ifMatch = r.version)
    /** Lowering the level is the owner's alone: 🔏 `archive.declassify` on `ref@version:level`, the same PATCH with `level` its only field.
     *  A sealed record takes it too: the level lies outside the sealed manifest (§23.1 ⟨1.7.1⟩). */
    suspend fun declassify(r: ArchiveRecord, level: String, stepUp: StepUp): ArchiveRecord =
        send("PATCH", "/archive/records/${seg(r.ref)}", json.encodeToString(JsonElement.serializer(), buildJsonObject { put("level", level) }), ifMatch = r.version,
            stepUp = stepUp("archive.declassify", "${r.ref}@${r.version}:$level"))
    /** A completed draft becomes `filed`; If-Match the row. */
    suspend fun fileDraft(r: ArchiveRecord): ArchiveRecord =
        call(Request.Builder().url(url("/archive/records/${seg(r.ref)}/file")).post("{}".toRequestBody(JSON))
            .header("Idempotency-Key", UUID.randomUUID().toString()).header("If-Match", "\"${r.version}\"").build(), serializer())
    /** A correction is a new version; on a sealed record the old one is superseded and the record goes back to `filed`. */
    suspend fun addVersion(ref: String, fileIds: List<String>, noteFa: String): ArchiveRecord =
        post("/archive/records/${seg(ref)}/versions", buildJsonObject { put("file_ids", ids(fileIds)); put("note_fa", noteFa) })
    /** 🔏 `archive.seal` on the current version's manifest, which the body names too: the server recomputes it and refuses a mismatch. */
    suspend fun sealRecord(r: ArchiveRecord, stepUp: StepUp): ArchiveRecord {
        val manifest = r.current?.manifestSha256.orEmpty()
        return post("/archive/records/${seg(r.ref)}/seal", buildJsonObject { put("manifest_sha256", manifest) }, stepUp("archive.seal", manifest))
    }
    suspend fun link(ref: String, kind: String, to: LinkTarget): ArchiveRecord =
        post("/archive/records/${seg(ref)}/links", buildJsonObject { put("kind", kind); put("to", buildJsonObject { put("kind", to.kind); put("ref", to.ref) }) })
    /** Removes an unsealed link, named in the query. */
    suspend fun unlink(ref: String, kind: String, to: LinkTarget): ArchiveRecord =
        call(Request.Builder().url(url("/archive/records/${seg(ref)}/links", mapOf("kind" to kind, "to_kind" to to.kind, "to_ref" to to.ref))).delete().build(), serializer())
    /** Owner: one draft per file for the archivist to classify. */
    suspend fun importFiles(scope: String, fileIds: List<String>, cls: String? = null): List<ArchiveRecord> =
        decodeList(post<JsonElement>("/archive/import", buildJsonObject { put("scope", scope); put("file_ids", ids(fileIds)); if (cls != null) put("class", cls) }), ArchiveRecord.serializer(), path = "POST /archive/import")
    /** The secret scan first (`422 secret_in_document`, naming the file in `fields`; nothing is stored), then hashes, text and the suggestion. */
    suspend fun intake(fileIds: List<String>): Intake = post("/archive/intake", buildJsonObject { put("file_ids", ids(fileIds)) })

    /** One file of a record. A level with `step_up_to_view` needs 🔏 `archive.view` on the ref ([stepUp] non-null); every call is a row of
     *  the access log, and a watermarked level is served watermarked. */
    suspend fun recordFile(ref: String, fileId: String, stepUp: StepUp?): FileBytes {
        val token = stepUp?.invoke("archive.view", ref)
        val req = Request.Builder().url(url("/archive/records/${seg(ref)}/files/${seg(fileId)}")).get().header("Accept", "*/*")
            .apply { if (token != null) header("X-Step-Up", token) }.build()
        return execute(req).use { r ->
            check(r)
            FileBytes(r.body.bytes(), r.body.contentType()?.let { "${it.type}/${it.subtype}" } ?: "application/octet-stream")
        }
    }

    suspend fun parties(kind: String? = null, scope: String? = null, q: String? = null): List<Party> =
        listAny("/archive/parties", mapOf("kind" to kind, "scope" to scope, "q" to q?.trim()?.ifEmpty { null }), Party.serializer())
    suspend fun createParty(body: PartyIn, key: String): Party = call(write("POST", "/archive/parties", jsonBody.encodeToJsonElement(PartyIn.serializer(), body), null, key), serializer())
    /** If-Match the party's version; retired, never deleted. */
    suspend fun patchParty(p: Party, body: JsonObject): Party =
        send("PATCH", "/archive/parties/${seg(p.ref)}", json.encodeToString(JsonElement.serializer(), body), ifMatch = p.version ?: 1)

    /** The hub filters by `state` only (it ignores `case`), so a case's holds are kept to that case here; a hub change (`?case=`) would
     *  make the filter the hub's. */
    suspend fun legalHolds(state: String? = null, case: String? = null): List<LegalHold> =
        listAny("/archive/holds", mapOf("state" to state, "case" to case), LegalHold.serializer()).filter { case == null || it.case == case }
    /** The owner places one (the legal counsel too, with its case); [key] is the press's. */
    suspend fun placeHold(body: HoldIn, key: String): LegalHold = call(write("POST", "/archive/holds", jsonBody.encodeToJsonElement(HoldIn.serializer(), body), null, key), serializer())
    /** The owner's alone: 🔏 `archive.hold.release` on the ref. */
    suspend fun releaseLegalHold(ref: String, stepUp: StepUp): LegalHold = post("/archive/holds/${seg(ref)}/release", JsonObject(emptyMap()), stepUp("archive.hold.release", ref))

    suspend fun dueReminders(): List<DueReminder> = listAny("/archive/reminders", emptyMap(), DueReminder.serializer())
    /** The underlying action is done (renewed, reviewed): the reminder closes everywhere. */
    suspend fun reminderDone(id: String) { postUnit("/archive/reminders/${seg(id)}/done", JsonObject(emptyMap())) }
    suspend fun retentionDue(): List<RetentionDue> = listAny("/archive/retention/due", emptyMap(), RetentionDue.serializer())
    suspend fun fixity(): Fixity = get("/archive/fixity")

    /** A GET that answers 404 when the thing does not exist yet: null, not an error. */
    /** A 404 read as "none yet": its entry in the error log is taken back (it was expected). */
    private inline fun <T> orNull(block: () -> T): T? = try { block() } catch (e: ApiException) {
        if (e.status == 404) { e.logged?.let { failures?.forget(it) }; null } else throw e
    }

    // --------------------------------------------------- backups ⟨1.4⟩ --
    suspend fun backups(): BackupStatus = get("/backups/status")

    // -------------------------------------------------------------- audit --
    suspend fun audit(limit: Int = 50): Page<AuditEntry> = get("/audit", mapOf("limit" to limit))
    /** One company's rows of one action (`kill_switch.engage`, `deploy_freeze.set`, …), newest first. */
    suspend fun audit(company: String?, action: String?, limit: Int = 20): Page<AuditEntry> =
        get("/audit", mapOf("company" to company, "action" to action, "limit" to limit))
    suspend fun auditVerify(): AuditVerify = get("/audit/verify")

    // ------------------------------------------- company servers ⟨1.8⟩ (§26) --
    /** Every server of the holding, provisioned or paired through its runner; [company] narrows on the phone (§26.4 names no filter). A bare list or a Page. */
    suspend fun servers(company: String? = null): List<HubServer> =
        listAny("/infra/servers", emptyMap(), HubServer.serializer()).filter { company == null || it.company == company }

    /** The latest `server.map`; null before the first one (`404`). */
    suspend fun serverMap(id: String): ServerMap? = orNull {
        ServerMaps.parse(get<JsonElement>("/infra/servers/${seg(id)}/map"))
    }

    /** Queues a `map` job (§26.4). A hub that answers `202` (the runner maps in the background) gives no map yet: null, and `server.state` follows. */
    suspend fun refreshMap(id: String): ServerMap? {
        val req = write("POST", "/infra/servers/${seg(id)}/map", JsonObject(emptyMap()), null)
        return execute(req).use { r ->
            check(r)
            val text = r.body.string()
            if (r.code == 202 || text.isBlank()) null else ServerMaps.parse(runCatching { json.parseToJsonElement(text) }.getOrNull())
        }
    }

    /** Who did what on the server, newest first (`?actor&from&to`, a Page). */
    suspend fun serverActivity(id: String, actor: String? = null, from: String? = null, to: String? = null, cursor: String? = null, limit: Int = 50): Page<ServerCall> =
        get("/infra/servers/${seg(id)}/activity", mapOf("actor" to actor, "from" to from, "to" to to, "cursor" to cursor, "limit" to limit))

    /**
     * Pairing a company server (§26.1, device-authorisation flow): the runner printed [userCode] on the server; the owner approves it,
     * 🔏 `server.attach` on `company:<CODE>`. The answer is `{server}` (read bare too); the runner then takes its own token on its next
     * poll and the server turns `online`. Nothing secret passes through the app.
     */
    suspend fun approveRunner(company: String, userCode: String, stepUp: StepUp): HubServer {
        val token = stepUp("server.attach", "company:$company")
        val out: JsonObject = post("/runners/approve", json.encodeToJsonElement(ApproveIn.serializer(), ApproveIn(userCode)), token)
        val inner = out["server"] as? JsonObject ?: out
        return runCatching { json.decodeFromJsonElement(HubServer.serializer(), inner) }.getOrElse { throw mismatch(200, "POST", "/runners/approve", it) }
    }

    /** 🔏 `server.detach` on `<CODE>:<server>`: revokes the runner's token at once; the runner stops on its next poll (§26.1). */
    suspend fun detachServer(s: HubServer, stepUp: StepUp) {
        val token = stepUp("server.detach", s.target)
        val req = Request.Builder().url(url("/infra/servers/${seg(s.id)}")).delete().header("X-Step-Up", token).header("Idempotency-Key", UUID.randomUUID().toString()).build()
        execute(req).use { check(it) }
    }

    /**
     * The owner's own command, 🔏 `server.exec` bound to the SHA-256 of the exact body (§26.4 names no target; a passkey per command, for
     * exactly that command), streamed as SSE: stdout and stderr as they come, then the exit. A `202 awaiting_seal` (a destructive command
     * the policy holds) is one [TermEvent.AwaitingSeal]; a refusal (`423 company_locked`) throws.
     */
    fun exec(server: HubServer, body: ExecIn, stepUp: StepUp): kotlinx.coroutines.flow.Flow<TermEvent> = kotlinx.coroutines.flow.flow {
        val text = jsonBody.encodeToString(ExecIn.serializer(), body)
        val token = stepUp("server.exec", sha256(text))
        val req = Request.Builder().url(url("/infra/servers/${seg(server.id)}/exec")).post(text.toRequestBody(JSON))
            .header("Accept", "text/event-stream").header("Idempotency-Key", UUID.randomUUID().toString()).header("X-Step-Up", token).build()
        execute(req, streamClient).use { r ->
            if (r.code == 202) {
                val o = runCatching { json.parseToJsonElement(r.body.string()) as? JsonObject }.getOrNull()
                val ref = (o?.get("decision_ref") ?: o?.get("decision") ?: o?.get("ref")) as? JsonPrimitive
                emit(TermEvent.AwaitingSeal(ref?.contentOrNull, (o?.get("message_fa") as? JsonPrimitive)?.contentOrNull ?: "این فرمان ویرانگر است و منتظر مُهر تو ماند."))
                return@use
            }
            check(r)
            if (r.header("Content-Type").orEmpty().contains("json")) {
                val o = runCatching { json.parseToJsonElement(r.body.string()) as? JsonObject }.getOrNull() ?: return@use
                termEventsOfJson(o).forEach { emit(it) }
                return@use
            }
            val src = r.body.source()
            val p = SseParser()
            while (true) {
                val line = src.readUtf8Line() ?: break
                p.line(line)?.let { m -> termEventOf(m)?.let { emit(it) } }
            }
            p.end()?.let { m -> termEventOf(m)?.let { emit(it) } }
        }
    }.flowOn(kotlinx.coroutines.Dispatchers.IO)

    /** The holding's network map (§26.6): the hub, each server with its road to the hub, and every link the latest checks tried. */
    suspend fun network(): NetworkMap = get("/infra/network")

    /** The owner asks every online runner to check its roads now (§26.6 `netcheck`); results follow on `GET /infra/network`. */
    suspend fun checkNetwork() {
        val req = write("POST", "/infra/network/check", JsonObject(emptyMap()), null)
        execute(req).use { check(it) }
    }

    suspend fun serverPolicy(): ServerPolicy = get("/control/server-policy")

    /** 🔏 PUT on the SHA-256 of the exact body (§26.4 names no action; the app signs `server.policy`, like every body-bound seal). */
    suspend fun putServerPolicy(p: ServerPolicy, stepUp: StepUp): ServerPolicy {
        val text = jsonBody.encodeToString(ServerPolicy.serializer(), p)
        return send("PUT", "/control/server-policy", text, stepUp = stepUp("server.policy", sha256(text)))
    }

    /**
     * Claude Code on the company's server (§26.2 `server.claude`, §26.5 `runtime: "company_server"`): the owner gives it a brief, a driver
     * (an agent of the company, or the owner when [driver] is null) and the repository folder it runs in ([cwd], one of the map's `repos`;
     * left out when null, and the hub picks). The session is then the Workshop's own (events, steering, stop).
     */
    suspend fun startServerSession(server: HubServer, driver: String?, title: String, brief: String, attachments: List<String>, cwd: String? = null): CodeSession =
        post("/workshop/sessions", buildJsonObject {
            put("runtime", "company_server"); put("server", server.id); put("company", server.company)
            put("driver", driver?.let(::JsonPrimitive) ?: JsonNull); put("title", title); put("brief", brief); put("attachments", ids(attachments))
            if (!cwd.isNullOrBlank()) put("cwd", cwd)
        })

    /** A transcript the hub stores (§26.3: owner-readable): an API path (relative or on the hub's origin) read with the session. */
    suspend fun transcript(url: String): String {
        val target = when {
            url.startsWith("http://") || url.startsWith("https://") -> url.toHttpUrl()
            url.startsWith("/api/") -> base.newBuilder().encodedPath(url.substringBefore('?')).encodedQuery(url.substringAfter('?', "").ifBlank { null }).build()
            else -> url(url)
        }
        if (target.host != base.host) throw ApiException(422, "validation_failed", "این نشانی بیرون از هاب است؛ اپ آن را باز نمیکند.")
        return execute(Request.Builder().url(target).get().header("Accept", "text/plain, application/json").build()).use { r -> check(r); r.body.string() }
    }

    // ------------------------------------------------- ⟨1.11⟩ §29 the business --
    /** §29.13 the owner's home: three cards, the morning, each group's KPIs per company, the orders, only critical items. */
    suspend fun home(): Home = get("/home")

    /** §29.13 `run` (makes an order) · `later` · `no` with the owner's reason (the secretary remembers it). */
    suspend fun suggestion(id: String, action: String, reasonFa: String? = null): JsonObject? =
        writeLoose("POST", "/home/suggestions/${seg(id)}", buildJsonObject { put("action", action); if (reasonFa != null) put("reason_fa", reasonFa) })

    /** §29.2 an order's report: state, receipt and plan, steps, blockers, outputs, the end summary. */
    suspend fun orderReport(ref: String): OrderReport = get("/orders/${seg(ref)}/report")

    /** §29.2 a blocker's one-tap fix; `budget.add` carries [tokens]. A sealed fix (`hiring.open`) is signed on its action and target. */
    suspend fun orderFix(ref: String, fix: Fix, tokens: Long? = null, stepUp: StepUp? = null): JsonObject? {
        val token = if (stepUp != null) stepUp(fix.action, fix.target ?: ref) else null
        return writeLoose("POST", "/orders/${seg(ref)}/fix", buildJsonObject {
            put("action", fix.action); put("target", fix.target); if (tokens != null) put("tokens", tokens)
        }, token)
    }

    /** §29.4 the secretary's route and its one line, before the order goes. */
    suspend fun orderPreview(text: String, source: String): OrderRoute29 =
        post("/orders/preview", buildJsonObject { put("text", text); put("source", source) })

    /** §29.3 the owner's rules (standing orders, newest first, with their counts). */
    suspend fun rules(): List<OwnerRule> = items("/rules", OwnerRule.serializer())

    /** §29.3 a rule in the owner's words (text or voice): `proposed`, made precise by the hub; the seal is one tap ([sealRule]). */
    suspend fun newRule(text: String, source: String, fileId: String? = null): OwnerRule =
        post("/rules", buildJsonObject { put("text", text); put("source", source); if (fileId != null) put("file_id", fileId) })

    /** 🔏 the standing order's own seal (`oversight.order` on the ref), read as a rule (its `applies_to` may be an object now). */
    suspend fun sealRule(ref: String, stepUp: StepUp): OwnerRule =
        post("/oversight/orders/${seg(ref)}/seal", JsonObject(emptyMap()), stepUp("oversight.order", ref))

    /** §29.3 🔏 a new version of a rule (`rule.seal` on the ref). */
    suspend fun putRule(ref: String, text: String, stepUp: StepUp): OwnerRule {
        val body = json.encodeToString(JsonElement.serializer(), buildJsonObject { put("text", text); put("text_md", text) })
        return send("PUT", "/rules/${seg(ref)}", body, stepUp = stepUp("rule.seal", ref))
    }

    suspend fun retireRule(ref: String): OwnerRule = post("/rules/${seg(ref)}/retire", JsonObject(emptyMap()))

    /** §29.9 a company's readiness for a working group: each check, and the fix of a failed one. */
    suspend fun readiness(code: String, group: String): Readiness = get("/companies/${seg(code)}/readiness", mapOf("group" to group))

    // §29.11 working groups.
    suspend fun groups(): List<WorkGroup> = items("/groups", WorkGroup.serializer())
    suspend fun group(key: String): WorkGroup = get("/groups/${seg(key)}")
    suspend fun groupMembers(key: String): List<Membership> = items("/groups/${seg(key)}/members", Membership.serializer())
    suspend fun setGroupMember(key: String, code: String, state: String): JsonObject? =
        writeLoose("PUT", "/groups/${seg(key)}/members/${seg(code)}", buildJsonObject { put("state", state) })
    suspend fun groupRuns(key: String, company: String? = null, limit: Int = 30): List<RoutineRun> =
        items("/groups/${seg(key)}/runs", RoutineRun.serializer(), mapOf("company" to company, "limit" to limit))
    suspend fun setRoutine(key: String, routine: String, state: String): JsonObject? =
        writeLoose("PUT", "/groups/${seg(key)}/routines/${seg(routine)}", buildJsonObject { put("state", state) })
    suspend fun groupKpis(key: String, company: String? = null, days: Int = 30): List<KpiSeries> {
        val e: JsonElement = get("/groups/${seg(key)}/kpis", mapOf("company" to company, "days" to days))
        return decoded("/groups/$key/kpis") { kpiSeriesOf(e, company) }
    }
    suspend fun groupExperiments(key: String, company: String? = null): List<Experiment> =
        items("/groups/${seg(key)}/experiments", Experiment.serializer(), mapOf("company" to company))

    // §29.12 connections: each kind with its state, last read and daily figures; the secret is write-only.
    suspend fun companyConnections(code: String): List<CompanyConnection> = items("/companies/${seg(code)}/connections", CompanyConnection.serializer())
    suspend fun connectionGuide(kind: String): ConnectionGuide = get("/connections/guides/${seg(kind)}")

    /** 🔏 `connection.config` on `CODE/kind` (the hub asks for it when the change widens what is read; the app always signs). */
    suspend fun putConnectionConfig(code: String, kind: String, config: JsonObject, stepUp: StepUp): JsonObject? {
        val token = stepUp("connection.config", "$code/$kind")
        return writeLoose("PUT", "/companies/${seg(code)}/connections/${seg(kind)}", buildJsonObject { put("config", config) }, token)
    }

    /** 🔏 `connection.secret` on `CODE/kind`: write-only, never read back (only `set` or `missing`). */
    suspend fun putConnectionSecret(code: String, kind: String, secret: String, stepUp: StepUp) {
        val token = stepUp("connection.secret", "$code/$kind")
        writeLoose("PUT", "/companies/${seg(code)}/connections/${seg(kind)}/secret", buildJsonObject { put("secret", secret) }, token)
    }

    suspend fun testConnection(code: String, kind: String): ConnectionTest =
        post("/companies/${seg(code)}/connections/${seg(kind)}/test", JsonObject(emptyMap()))

    /** §29.1 the company's technical findings («شرکت ← فنی»): every domain of tech, infra and security, not only what reaches the owner. */
    suspend fun techFindings(company: String): List<Finding> = kotlinx.coroutines.coroutineScope {
        TECH_DOMAINS.map { d ->
            async { get<Page<Finding>>("/oversight/findings", mapOf("scope" to "all", "domain" to d, "company" to company)).items }
        }.flatMap { it.await() }.distinctBy { it.ref }.sortedByDescending { it.openedAt }
    }

    // ----------------------------------------- ⟨1.12⟩ §30 production lines --
    suspend fun lineTemplates(): List<LineTemplate> = items("/line-templates", LineTemplate.serializer())
    suspend fun lineTemplate(key: String): LineTemplate = get("/line-templates/${seg(key)}")

    suspend fun companyLines(code: String): List<Line> = items("/companies/${seg(code)}/lines", Line.serializer())

    /** A new line from a template, a `draft`: its first runs wait for the owner's seal. */
    suspend fun newLine(code: String, template: String, platform: String, channel: LineChannel, titleFa: String): Line =
        post("/companies/${seg(code)}/lines", buildJsonObject {
            put("template", template); put("platform", platform); put("title_fa", titleFa)
            put("channel", buildJsonObject { put("kind", channel.kind); put("subject", channel.subject) })
        })

    suspend fun line(ref: String): Line = get("/lines/${seg(ref)}")

    /** `PUT /lines/{ref}`: a new version. A cap that rises is 🔏 `line.caps` on the ref (the caller passes [stepUp] then). */
    suspend fun putLine(ref: String, body: JsonObject, stepUp: StepUp? = null): Line {
        val token = if (stepUp != null) stepUp("line.caps", ref) else null
        return send("PUT", "/lines/${seg(ref)}", jsonBody.encodeToString(JsonObject.serializer(), body), stepUp = token)
    }

    suspend fun setLineState(ref: String, state: String): Line = post("/lines/${seg(ref)}/state", buildJsonObject { put("state", state) })

    /** `auto` is 🔏 `line.auto` on the ref; back to `draft` is not sealed. */
    suspend fun setLineMode(ref: String, mode: String, stepUp: StepUp? = null): Line {
        val token = if (stepUp != null) stepUp("line.auto", ref) else null
        return post("/lines/${seg(ref)}/mode", buildJsonObject { put("mode", mode) }, token)
    }

    suspend fun lineVersions(ref: String): List<LineVersion> = items("/lines/${seg(ref)}/versions", LineVersion.serializer())
    suspend fun revertLine(ref: String, version: Int): Line = post("/lines/${seg(ref)}/revert", buildJsonObject { put("version", version) })
    suspend fun copyLine(ref: String, company: String): Line = post("/lines/${seg(ref)}/copy", buildJsonObject { put("company", company) })

    suspend fun runLine(ref: String, dry: Boolean = false, fromStep: String? = null): LineRun =
        post("/lines/${seg(ref)}/runs", buildJsonObject { put("dry", dry); if (fromStep != null) put("from_step", fromStep) })

    /** That step alone; nothing is kept beyond the answer. The answer is a step run, or the bare output (both are read). */
    suspend fun testLineStep(ref: String, key: String, inputs: JsonObject? = null): StepRun {
        val e: JsonObject = post("/lines/${seg(ref)}/steps/${seg(key)}/test", buildJsonObject { if (inputs != null) put("inputs", inputs) })
        return decoded("/lines/$ref/steps/$key/test", "POST") {
            if (e["output"] is JsonObject || e["state"] != null) json.decodeFromJsonElement(StepRun.serializer(), e)
            else StepRun(key = key, state = "done", output = json.decodeFromJsonElement(StepOutput.serializer(), e))
        }
    }

    suspend fun lineRuns(ref: String, limit: Int = 30): List<LineRun> = items("/lines/${seg(ref)}/runs", LineRun.serializer(), mapOf("limit" to limit))
    suspend fun lineRun(ref: String): LineRun = get("/line-runs/${seg(ref)}")
    suspend fun rerunLineRun(ref: String, fromStep: String): LineRun = post("/line-runs/${seg(ref)}/rerun", buildJsonObject { put("from_step", fromStep) })

    /** The owner's seal of a waiting run: publish it (approve) or refuse it. */
    suspend fun sealLineRun(ref: String, approve: Boolean, noteFa: String? = null, stepUp: StepUp? = null, decision: String? = null): LineRun {
        // Approving is a card approval (A3): 🔏 `decision.approve` on the run's card; refusing needs no seal.
        val token = if (approve && stepUp != null && decision != null) stepUp("decision.approve", decision) else null
        return post("/line-runs/${seg(ref)}/seal", buildJsonObject { put("approve", approve); if (!noteFa.isNullOrBlank()) put("note_fa", noteFa) }, token)
    }

    suspend fun cancelLineRun(ref: String): LineRun = post("/line-runs/${seg(ref)}/cancel", JsonObject(emptyMap()))

    suspend fun lineCalendar(from: String, to: String, company: String? = null): LineCalendar =
        get("/calendar/lines", mapOf("from" to from, "to" to to, "company" to company))

    suspend fun library(company: String? = null, kind: String? = null): List<Asset> = items("/library", Asset.serializer(), mapOf("company" to company, "kind" to kind))

    /** A file for the library, streamed from [open] (a content URI, never held in memory). */
    class LibraryUpload(val name: String, val mime: String, val size: Long, val open: () -> InputStream)

    /** A new library entry: each file goes up with the app's own upload (`POST /files`), then `POST /library` names their ids. */
    suspend fun addAsset(company: String?, kind: String, titleFa: String, config: JsonObject, files: List<LibraryUpload>): Asset {
        val fileIds = files.map { f -> upload(f.name, f.mime, f.size, f.open).id }
        return post("/library", buildJsonObject {
            if (company != null) put("company", company)
            put("kind", kind); put("title_fa", titleFa); put("config", config); put("files", ids(fileIds))
        })
    }

    suspend fun putAsset(id: String, body: JsonObject): Asset = put("/library/${seg(id)}", body)
    suspend fun deleteAsset(id: String) {
        execute(Request.Builder().url(url("/library/${seg(id)}")).delete().build()).use { check(it) }
    }

    suspend fun ttsVoices(): List<TtsVoice> = items("/tts/voices", TtsVoice.serializer())

    // ------------------------------------------------- ⟨1.13⟩ §31 growth --
    suspend fun lineInsights(ref: String): Insights = get("/lines/${seg(ref)}/insights")

    suspend fun kits(): List<Kit> = items("/kits", Kit.serializer())
    private fun kitBody(kit: String, code: String, nameFa: String, nameEn: String, colorIndex: Int?) = buildJsonObject {
        put("kit", kit); put("code", code); put("name_fa", nameFa); put("name_en", nameEn); if (colorIndex != null) put("color_index", colorIndex)
    }
    /** What the call would make, in words; nothing is created. */
    suspend fun previewKit(kit: String, code: String, nameFa: String, nameEn: String, colorIndex: Int? = null): KitPreview =
        post("/companies/from-kit/preview", kitBody(kit, code, nameFa, nameEn, colorIndex))
    /** 🔏 `company.create` on the new company's code. */
    suspend fun createFromKit(kit: String, code: String, nameFa: String, nameEn: String, colorIndex: Int?, stepUp: StepUp): KitResult =
        post("/companies/from-kit", kitBody(kit, code, nameFa, nameEn, colorIndex), stepUp("company.create", code))

    suspend fun newsletter(code: String): Newsletter = get("/companies/${seg(code)}/newsletter")
    suspend fun newNewsletter(code: String, list: String, subject: String, subjectB: String?, bodyMd: String): NlCampaign =
        post("/companies/${seg(code)}/newsletter/campaigns", buildJsonObject {
            put("list", list); put("subject", subject); if (!subjectB.isNullOrBlank()) put("subject_b", subjectB); put("body_md", bodyMd)
        })
    /** A list over its size limit is 🔏 `newsletter.send` on the campaign (the caller passes [stepUp] when the list is over). */
    suspend fun scheduleNewsletter(id: String, at: String, stepUp: StepUp? = null): NlCampaign =
        post("/newsletter/campaigns/${seg(id)}/schedule", buildJsonObject { put("at", at) }, if (stepUp != null) stepUp("newsletter.send", id) else null)

    suspend fun keywords(code: String): List<Keyword> = items("/companies/${seg(code)}/keywords", Keyword.serializer())
    suspend fun addKeyword(code: String, phrase: String, site: String, targetUrl: String?): Keyword =
        post("/companies/${seg(code)}/keywords", buildJsonObject { put("phrase", phrase); put("site", site); put("target_url", targetUrl) })
    suspend fun setKeywordState(code: String, id: String, state: String): Keyword = put("/companies/${seg(code)}/keywords/${seg(id)}", buildJsonObject { put("state", state) })
    suspend fun deleteKeyword(code: String, id: String) { execute(Request.Builder().url(url("/companies/${seg(code)}/keywords/${seg(id)}")).delete().build()).use { check(it) } }
    suspend fun ranks(code: String, days: Int = 30): List<RankDaily> = items("/companies/${seg(code)}/ranks", RankDaily.serializer(), mapOf("days" to days))
    suspend fun competitors(code: String): List<Competitor> = items("/companies/${seg(code)}/competitors", Competitor.serializer())
    suspend fun addCompetitor(code: String, nameFa: String, site: String?, instagram: String?, youtube: String?, telegram: String?): Competitor =
        post("/companies/${seg(code)}/competitors", buildJsonObject {
            put("name_fa", nameFa); put("site", site); put("instagram", instagram); put("youtube", youtube); put("telegram", telegram)
        })
    suspend fun deleteCompetitor(code: String, id: String) { execute(Request.Builder().url(url("/companies/${seg(code)}/competitors/${seg(id)}")).delete().build()).use { check(it) } }
    suspend fun competitorDaily(code: String, days: Int = 30): List<CompetitorDaily> = items("/companies/${seg(code)}/competitors/daily", CompetitorDaily.serializer(), mapOf("days" to days))

    /** §31.5 `GET /campaign-calendar` (not `/calendar`, the change calendar of §20); the answer is a list, `{items}` or `{days: [{day, items}]}`. */
    suspend fun campaignCalendar(from: String, to: String, company: String? = null): List<CampaignItem> {
        val e: JsonElement = get("/campaign-calendar", mapOf("from" to from, "to" to to, "company" to company))
        return decoded("/campaign-calendar") {
            val days = ((e as? JsonObject)?.get("days") as? JsonArray)
            if (days != null) days.flatMap { d ->
                val day = ((d as? JsonObject)?.get("day") as? JsonPrimitive)?.contentOrNull.orEmpty()
                (((d as? JsonObject)?.get("items") as? JsonArray).orEmpty()).map { json.decodeFromJsonElement(CampaignItem.serializer(), it).let { x -> if (x.day.isBlank()) x.copy(day = day) else x } }
            } else e.itemsOrSelf().map { json.decodeFromJsonElement(CampaignItem.serializer(), it) }
        }
    }
    suspend fun campaigns(company: String? = null): List<Campaign> = items("/campaigns", Campaign.serializer(), mapOf("company" to company))
    suspend fun saveCampaign(id: String?, body: JsonObject): Campaign = if (id == null) post("/campaigns", body) else put("/campaigns/${seg(id)}", body)
    suspend fun deleteCampaign(id: String) { execute(Request.Builder().url(url("/campaigns/${seg(id)}")).delete().build()).use { check(it) } }

    suspend fun ads(code: String): Ads = get("/companies/${seg(code)}/ads")
    suspend fun adRules(code: String): List<AdRule> = items("/companies/${seg(code)}/ad-rules", AdRule.serializer())
    suspend fun saveAdRule(code: String, id: String?, body: JsonObject, stepUp: StepUp? = null): AdRule {
        val token = if (id != null && stepUp != null) stepUp("ads.cap", id) else null
        return if (id == null) post("/companies/${seg(code)}/ad-rules", body)
        else send("PUT", "/companies/${seg(code)}/ad-rules/${seg(id)}", jsonBody.encodeToString(JsonObject.serializer(), body), stepUp = token)
    }
    suspend fun deleteAdRule(code: String, id: String) { execute(Request.Builder().url(url("/companies/${seg(code)}/ad-rules/${seg(id)}")).delete().build()).use { check(it) } }
    /** 🔏 `ads.resume` on `platform/id`. */
    suspend fun resumeAd(platform: String, id: String, stepUp: StepUp): AdCampaign =
        post("/ads/campaigns/${seg(platform)}/${seg(id)}/resume", JsonObject(emptyMap()), stepUp("ads.resume", "$platform/$id"))

    suspend fun automations(): List<GrowthAutomation> = items("/automations", GrowthAutomation.serializer())
    suspend fun automation(ref: String): GrowthAutomation = get("/automations/${seg(ref)}")
    suspend fun compileAutomation(sentence: String, company: String?): Compiled =
        post("/automations/compile", buildJsonObject { put("sentence_fa", sentence); if (company != null) put("company", company) })
    suspend fun newAutomation(rule: JsonObject, sentence: String, company: String?): GrowthAutomation =
        post("/automations", buildJsonObject { put("rule", rule); put("sentence_fa", sentence); if (company != null) put("company", company) })
    /** 🔏 `automation.seal`: nothing runs before it. */
    suspend fun sealAutomation(ref: String, stepUp: StepUp): GrowthAutomation = post("/automations/${seg(ref)}/seal", JsonObject(emptyMap()), stepUp("automation.seal", ref))
    suspend fun setAutomationState(ref: String, state: String): GrowthAutomation = post("/automations/${seg(ref)}/state", buildJsonObject { put("state", state) })

    // §29.5 long voice: a session, its chunks (≤ 90 s each, in order, idempotent per n), then the whole text.
    suspend fun sttStart(purpose: String): SttSession = post("/transcribe/sessions", buildJsonObject { put("purpose", purpose) })

    suspend fun sttChunk(id: String, n: Int, audio: File, mime: String = "audio/mp4") {
        val req = Request.Builder().url(url("/transcribe/sessions/${seg(id)}/chunks/$n")).put(audio.asRequestBody(mime.toMediaType())).build()
        execute(req, transferClient).use { check(it) }
    }

    suspend fun sttFinish(id: String): SttDone =
        call(write("POST", "/transcribe/sessions/${seg(id)}/finish", JsonObject(emptyMap()), null), serializer<SttDone>(), transferClient)

    /** A write whose answer the app does not need whole (a 204, or a shape a newer hub may change): the object when there is one. */
    private suspend fun writeLoose(method: String, path: String, body: JsonElement, stepUp: String? = null): JsonObject? =
        execute(write(method, path, body, stepUp)).use { r ->
            check(r)
            val t = r.body.string()
            if (t.isBlank()) null else runCatching { json.parseToJsonElement(t) as? JsonObject }.getOrNull()
        }

    /** A list the hub may answer bare or as a page. */
    private suspend fun <T> items(path: String, s: KSerializer<T>, query: Map<String, Any?> = emptyMap()): List<T> {
        val e: JsonElement = get(path, query)
        return decoded(path) { e.itemsOrSelf().map { json.decodeFromJsonElement(s, it) } }
    }

    // ---------------------------------------------------- ⟨1.14⟩ §32 talk --
    suspend fun talkPersonas(): List<TalkPersona> = items("/talk/personas", TalkPersona.serializer())
    /** The owner's change of a persona's voice, engine or effort (the charter is not editable here). */
    suspend fun setTalkPersona(key: String, engine: String?, voice: String?, effort: String?): TalkPersona =
        put("/talk/personas/${seg(key)}", buildJsonObject { if (engine != null) put("engine", engine); if (voice != null) put("voice", voice); if (effort != null) put("effort", effort) })

    suspend fun talkConversations(persona: String? = null, q: String? = null, cursor: String? = null): List<TalkConversation> =
        items("/talk/conversations", TalkConversation.serializer(), mapOf("persona" to persona, "q" to q?.takeIf { it.isNotBlank() }, "cursor" to cursor))
    suspend fun newTalkConversation(persona: String, role: String? = null, company: String? = null, mode: String? = null): TalkConversation =
        post("/talk/conversations", buildJsonObject { put("persona", persona); if (role != null) put("role", role); if (company != null) put("company", company); if (mode != null) put("mode", mode) })
    suspend fun talkConversation(ref: String): TalkDetail = TalkDetail.parse(get<JsonElement>("/talk/conversations/${seg(ref)}"))
    suspend fun patchTalkConversation(ref: String, mode: String? = null, titleFa: String? = null): TalkConversation =
        send("PATCH", "/talk/conversations/${seg(ref)}", json.encodeToString(JsonElement.serializer(), buildJsonObject { if (mode != null) put("mode", mode); if (titleFa != null) put("title_fa", titleFa) }))
    /** A turn of the owner (`Idempotency-Key` = [clientId], kept across a retry of one press); the answer streams on [TalkTurnOut.events]. */
    suspend fun sendTalkTurn(ref: String, text: String, source: String, clientId: String): TalkTurnOut =
        call(write("POST", "/talk/conversations/${seg(ref)}/turns", buildJsonObject { put("text", text); put("source", source); put("client_id", clientId) }, null, key = clientId), serializer())
    suspend fun inviteToTalk(ref: String, role: String, company: String, department: String? = null): JsonObject? =
        writeLoose("POST", "/talk/conversations/${seg(ref)}/invite", buildJsonObject { put("role", role); put("company", company); if (department != null) put("department", department) })
    /** «صورت‌جلسه کن»: one `minutes` card from the conversation so far. */
    suspend fun talkMinutes(ref: String): JsonObject? = writeLoose("POST", "/talk/conversations/${seg(ref)}/minutes", JsonObject(emptyMap()))
    /** Barge-in: the owner spoke over the answer; generation ends and the sentences not yet spoken are not made. */
    suspend fun stopTalkTurn(id: String): JsonObject? = writeLoose("POST", "/talk/turns/${seg(id)}/stop", JsonObject(emptyMap()))
    /** «اجرا کن»: the card runs the route it stands for, with the owner's edits ([payload]). */
    suspend fun runTalkCard(id: String, payload: JsonObject?, stepUp: StepUp? = null): TalkCardRun {
        val body = if (payload == null) JsonObject(emptyMap()) else buildJsonObject { put("payload", payload) }
        // A card keeps the seal of the route it runs (§32.9): asked first without the passkey; a route that needs it answers
        // `403 step_up_required`, and the card is sealed on its id and sent again.
        return try {
            post("/talk/cards/${seg(id)}/run", body)
        } catch (e: ApiException) {
            if (stepUp == null || e.status != 403 || e.code != "step_up_required") throw e
            e.logged?.let { failures?.forget(it) }
            post("/talk/cards/${seg(id)}/run", body, stepUp("talk.card", id))
        }
    }
    suspend fun dismissTalkCard(id: String): JsonObject? = writeLoose("POST", "/talk/cards/${seg(id)}/dismiss", JsonObject(emptyMap()))

    suspend fun voiceEngines(): List<VoiceEngine> = items("/voice/engines", VoiceEngine.serializer())
    suspend fun voiceVoices(engine: String): List<VoiceVoice> = items("/voice/engines/${seg(engine)}/voices", VoiceVoice.serializer())
    suspend fun voiceMeter(period: String): VoiceMeter = get("/voice/meter", mapOf("period" to period))
    /** 🔏 `voice.secret` on the provider: write-only; the hub checks the key and the light follows on the stream. */
    suspend fun putVoiceSecret(provider: String, secret: String, stepUp: StepUp): VoiceSecretOut =
        send("PUT", "/voice/providers/${seg(provider)}/secret", json.encodeToString(JsonElement.serializer(), buildJsonObject { put("secret", secret) }), stepUp = stepUp("voice.secret", provider))
    suspend fun deleteVoiceSecret(provider: String, stepUp: StepUp) {
        val token = stepUp("voice.secret", provider)
        execute(Request.Builder().url(url("/voice/providers/${seg(provider)}/secret")).delete().header("X-Step-Up", token).build()).use { check(it) }
    }
    suspend fun checkVoiceEngine(key: String): JsonObject? = writeLoose("POST", "/voice/engines/${seg(key)}/check", JsonObject(emptyMap()))
    /** «بشنوید»: a short sample in a voice; its cost lands on the meter. */
    suspend fun talkVoiceSample(engine: String, voice: String, text: String? = null): TalkVoiceSample =
        post("/voice/sample", buildJsonObject { put("engine", engine); put("voice", voice); if (text != null) put("text", text) })
    suspend fun putVoicePrice(key: String, price: VoicePrice): VoiceEngine =
        put("/voice/engines/${seg(key)}/price", buildJsonObject {
            put("text_in_per_m", price.textInPerM); put("audio_out_per_m", price.audioOutPerM); put("audio_tokens_per_s", price.audioTokensPerS)
            price.validUntil?.let { put("valid_until", it) }
        })

    // ------------------------------------------------------------ plumbing --
    private fun seg(s: String): String = java.net.URLEncoder.encode(s, "UTF-8").replace("+", "%20")
    private fun ids(xs: List<String>) = JsonArray(xs.map(::JsonPrimitive))

    private suspend inline fun <reified T> get(path: String, query: Map<String, Any?> = emptyMap()): T =
        call(Request.Builder().url(url(path, query)).get().build(), serializer())

    private suspend inline fun <reified T> post(path: String, body: JsonElement, stepUp: String? = null): T =
        call(write("POST", path, body, stepUp), serializer())

    private suspend inline fun <reified T> put(path: String, body: JsonElement): T = call(write("PUT", path, body, null), serializer())

    /** A PUT or PATCH with an exact text body: If-Match carries the version (§1), X-Step-Up the seal. */
    private suspend inline fun <reified T> send(method: String, path: String, text: String, ifMatch: Int? = null, stepUp: String? = null): T {
        val req = Request.Builder().url(url(path)).method(method, text.toRequestBody(JSON))
            .apply { if (ifMatch != null) header("If-Match", "\"$ifMatch\""); if (stepUp != null) header("X-Step-Up", stepUp) }
            .build()
        return call(req, serializer())
    }

    private suspend fun postUnit(path: String, body: JsonElement, stepUp: String? = null) {
        execute(write("POST", path, body, stepUp)).use { check(it) }
    }

    /** [key]: the caller's Idempotency-Key, kept across retries of one press; otherwise every POST gets a fresh one. */
    private fun write(method: String, path: String, body: JsonElement, stepUp: String?, key: String? = null, query: Map<String, Any?> = emptyMap()): Request =
        Request.Builder().url(url(path, query))
            .method(method, json.encodeToString(JsonElement.serializer(), body).toRequestBody(JSON))
            .apply {
                if (method == "POST") header("Idempotency-Key", key ?: UUID.randomUUID().toString())
                if (stepUp != null) header("X-Step-Up", stepUp)
            }
            .build()

    private suspend fun <T> call(request: Request, s: KSerializer<T>, via: OkHttpClient = client): T = execute(request, via).use { r ->
        check(r)
        val text = r.body.string()
        try {
            json.decodeFromString(s, text)
        } catch (e: IllegalArgumentException) {
            // SerializationException is an IllegalArgumentException, and so is a number that does not fit its type.
            throw mismatch(r.code, r.request.method, r.request.url.encodedPath, e, r.header("X-Request-Id") ?: r.request.header(REQUEST_ID), elapsed(r))
        }
    }

    private fun check(r: Response) {
        if (r.isSuccessful) return
        if (r.code == 401) expire()
        val p = runCatching { json.decodeFromString(Problem.serializer(), r.body.string()) }.getOrNull()
        val rid = p?.requestId ?: r.header("X-Request-Id") ?: r.request.header(REQUEST_ID)
        val logged = failures?.record(
            ApiFailure(
                "http", r.request.method, r.request.url.encodedPath, r.code, p?.code ?: if (r.code in 502..504) "hub_unreachable" else "unexpected",
                p?.title ?: r.message.ifBlank { null }, rid, message = p?.detail ?: p?.messageFa, durationMs = elapsed(r),
                headers = r.headers.toMultimap().mapValues { it.value.joinToString(", ") },
            ),
        )
        if (p?.messageFa == null) throw ApiException.unexpected(r.code).also { it.logged = logged }
        val wait = r.header("Retry-After")?.trim()?.toIntOrNull()?.takeIf { it > 0 }
        throw ApiException(
            r.code, p.code, p.messageFa, p.requestId ?: r.header("X-Request-Id"), p.missing, p.blockedReasons, wait, batchReasons(p), p.fields?.keys?.filter { it != "items" }.orEmpty(),
            p.fields?.mapNotNull { (k, v) -> (v as? JsonPrimitive)?.takeIf { it.isString }?.content?.let { k to it } }?.toMap().orEmpty(),
            p.detail,
        ).also { it.logged = logged }
    }

    /**
     * One call: a client request id the hub echoes (so its logs match the phone's), and for a read a quiet retry with a short pause when
     * the answer is 502/503/504 or there is none ([RETRY_MS]); every answer and failure tells [hub]. Only the final outcome is logged.
     */
    private suspend fun execute(request: Request, via: OkHttpClient = client): Response {
        val req = if (request.header(REQUEST_ID) == null) request.newBuilder().header(REQUEST_ID, UUID.randomUUID().toString()).build() else request
        val started = System.nanoTime()
        val retries = if (req.method == "GET") RETRY_MS.size else 0
        var attempt = 0
        while (true) {
            val res = try {
                send(req, via)
            } catch (e: IOException) {
                hub?.transient()
                if (attempt < retries) { kotlinx.coroutines.delay(RETRY_MS[attempt++]); continue }
                val x = ApiException.offline()
                x.logged = failures?.record(
                    ApiFailure("network", req.method, req.url.encodedPath, null, "network_error", e::class.simpleName, req.header(REQUEST_ID), durationMs = msSince(started)),
                )
                throw x
            }
            if (proxied(res)) {
                hub?.transient()
                if (attempt < retries) { res.close(); kotlinx.coroutines.delay(RETRY_MS[attempt++]); continue }
            } else hub?.ok()
            return res.newBuilder().header(ELAPSED, msSince(started).toString()).build()
        }
    }

    /** The raw exchange; an IOException is the caller's to read. */
    private suspend fun send(request: Request, via: OkHttpClient): Response = suspendCancellableCoroutine { cont ->
        val call = via.newCall(request)
        cont.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                if (cont.isCancelled) return
                cont.resumeWithException(e)
            }

            override fun onResponse(call: Call, response: Response) {
                cont.resume(response) { _, r, _ -> r.close() }
            }
        })
    }

    /** A 502/503/504 the proxy answered for a hub that is not there; a Problem from the hub itself (a 503 `channel_not_configured`)
     *  is the hub answering, not a restart. */
    private fun proxied(r: Response): Boolean {
        if (r.code !in 502..504) return false
        val type = r.header("Content-Type").orEmpty()
        if (!type.contains("json")) return true
        return !runCatching { r.peekBody(8_192).string().contains("\"code\"") }.getOrDefault(false)
    }

    private fun msSince(t0: Long): Long = (System.nanoTime() - t0) / 1_000_000
    private fun elapsed(r: Response): Long? = r.header(ELAPSED)?.toLongOrNull()

    companion object {
        /** The id each call carries; the hub accepts it (`^[A-Za-z0-9-]{8,64}$`), logs it and sends it back as `X-Request-ID`. */
        const val REQUEST_ID = "X-Request-Id"
        /** The hub's page ceiling (`pagination.MAX_LIMIT`); a `limit` above it is refused with 422. */
        const val MAX_PAGE = 200
        /** How long a call took, on the response the app hands on (never sent anywhere). */
        private const val ELAPSED = "X-HQ-Elapsed-Ms"
        /** A read that met a 502/503/504 or no answer is tried again after these pauses. */
        val RETRY_MS = longArrayOf(400, 1_200)
        private val JSON = "application/json".toMediaType()
        private val LOCAL = listOf("data:", "file:", "content:")

        /** `fields.items: [{ref, reason}]` of a refused batch. */
        private fun batchReasons(p: Problem): List<Pair<String, String>> =
            (p.fields?.get("items") as? JsonArray)?.mapNotNull { x ->
                val o = x as? JsonObject ?: return@mapNotNull null
                val ref = (o["ref"] as? JsonPrimitive)?.takeIf { it.isString }?.content ?: return@mapNotNull null
                ref to ((o["reason"] as? JsonPrimitive)?.content ?: "")
            }.orEmpty()

        /** ⟨1.11⟩ §29.1 the technical domains, which reach the owner only under «شرکت ← فنی» (or when critical). */
        val TECH_DOMAINS = listOf("tech", "infra", "security")

        /** Every status `GET /decisions` takes. */
        val DECISION_STATUSES = listOf("pending", "approved", "rejected", "returned", "expired", "withdrawn")

        fun sha256(text: String): String = MessageDigest.getInstance("SHA-256").digest(text.toByteArray()).joinToString("") { "%02x".format(it) }

        /** ⟨1.10⟩ §28.1 the seal's target of a delete: SHA-256 of the canonical JSON of the refs, distinct and sorted
         *  (`["O-000026","O-000028"]`, no spaces), as `decision.batch` seals its sorted items. */
        fun deleteTarget(refs: Collection<String>): String =
            sha256(json.encodeToString(JsonElement.serializer(), JsonArray(refs.distinct().sorted().map(::JsonPrimitive))))

        @OptIn(ExperimentalSerializationApi::class)
        val json = Json {
            ignoreUnknownKeys = true
            explicitNulls = false
            coerceInputValues = true
            namingStrategy = JsonNamingStrategy.SnakeCase
        }

        /** ⟨1.5⟩ Bodies sent whole, where a null or a usual value is meaningful (a war room's `budget_tokens`, a cleared KPI target,
         *  a sampled red line's `patterns: null`, an enabled meeting type): the same wire format, every field written. */
        @OptIn(ExperimentalSerializationApi::class)
        val jsonBody = Json(json) { explicitNulls = true; encodeDefaults = true }
    }
}

/** Contract §2 for the Android client: Bearer session, `X-HQ-Client: android`, JSON accept. */
private class ContractHeaders(private val tokens: TokenSource) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val b = chain.request().newBuilder()
            .header("X-HQ-Client", "android")
        // JSON unless the call asked for something else (an SSE stream, a file, a transcript).
        if (chain.request().header("Accept") == null) b.header("Accept", "application/json")
        tokens.token()?.let { b.header("Authorization", "Bearer $it") }
        return chain.proceed(b.build())
    }
}
