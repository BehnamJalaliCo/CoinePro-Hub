package com.coinepro.hq.core.net

import java.io.IOException
import java.util.UUID
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNamingStrategy
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
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
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response

/** A failed API call, carrying the contract's stable [code] and Persian [messageFa] (contract §1). */
class ApiException(
    val status: Int,
    val code: String,
    val messageFa: String,
    val requestId: String? = null,
) : Exception("HTTP $status $code") {
    val isAuth: Boolean get() = status == 401
    val isOffline: Boolean get() = status == 0

    companion object {
        fun offline() = ApiException(0, "network_error", "اتصال برقرار نشد. اینترنت را بررسی کن.")
        fun unexpected(status: Int) = ApiException(status, "internal_error", "خطای غیرمنتظره؛ دوباره تلاش کن.")
    }
}

/** Where the session token lives; the API only reads it and clears it on 401. */
interface TokenSource {
    fun token(): String?
    fun clear()
}

/** The hub's public API (contract v1.2) as the Android client sees it: Bearer session, JSON, Problem errors. */
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

    /** The session is gone (401 outside a normal call, e.g. on the stream). */
    fun unauthorized() = tokens.clear()

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
    suspend fun deliverable(ref: String): Deliverable = get("/deliverables/${seg(ref)}")
    suspend fun rate(ref: String, score: Int, comment: String?): Deliverable =
        post("/deliverables/${seg(ref)}/rating", buildJsonObject { put("score", score); put("comment", comment) })

    // ------------------------------------------------------- organisation --
    suspend fun companies(): List<Company> = get("/companies")
    suspend fun company(code: String): Company = get("/companies/${seg(code)}")
    suspend fun departments(code: String): List<Department> = get("/companies/${seg(code)}/departments")
    suspend fun orgChart(company: String): OrgChart = get("/org/${seg(company)}/chart")
    suspend fun employees(company: String? = null, department: String? = null, limit: Int = 100): Page<Employee> =
        get("/employees", mapOf("company" to company, "department" to department, "limit" to limit))
    suspend fun employee(code: String): Employee = get("/employees/${seg(code)}")

    // --------------------------------------------------------------- work --
    suspend fun work(company: String? = null, status: String? = null, assignee: String? = null, q: String? = null, limit: Int = 50): Page<Work> =
        get("/work", mapOf("company" to company, "status" to status, "assignee" to assignee, "q" to q, "limit" to limit))

    /** Work by id, or by its ref ("W-000104") as planner items and messages carry it: the API addresses work
     *  by UUID, so a ref is resolved through the list search first. */
    suspend fun workOne(idOrRef: String): Work {
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
    suspend fun send(code: String, body: String): JsonObject = post("/threads/${seg(code)}/messages", buildJsonObject { put("body", body) })
    suspend fun markRead(code: String, upToRef: String): Thread = post("/threads/${seg(code)}/read", buildJsonObject { put("up_to_ref", upToRef) })

    // ------------------------------------------------------ notifications --
    suspend fun notifications(unread: Boolean? = null, level: String? = null, limit: Int = 50): NotificationPage =
        get("/notifications", mapOf("unread" to unread, "level" to level, "limit" to limit))
    suspend fun readAll(): JsonObject = post("/notifications/read-all", JsonObject(emptyMap()))
    suspend fun readNotification(id: String): Notification = post("/notifications/${seg(id)}/read", JsonObject(emptyMap()))
    suspend fun answer(id: String, choiceId: String): Notification = post("/notifications/${seg(id)}/answer", buildJsonObject { put("choice_id", choiceId) })

    // ------------------------------------------------------------ control --
    suspend fun control(): ControlState = get("/control/state")
    suspend fun killSwitch(scope: String, engaged: Boolean, reason: String, stepUp: String?): ControlState =
        post("/control/kill-switch", buildJsonObject { put("scope", scope); put("state", if (engaged) "engaged" else "released"); put("reason", reason) }, stepUp)

    // ----------------------------------------------------------- treasury --
    suspend fun treasury(period: String = "month", company: String? = null): TreasurySummary =
        get("/treasury/summary", mapOf("period" to period, "company" to company))
    suspend fun breakdown(by: String, from: String? = null, to: String? = null, company: String? = null): List<BreakdownRow> =
        get("/treasury/breakdown", mapOf("by" to by, "from" to from, "to" to to, "company" to company))
    suspend fun connections(): List<Connection> = get("/connections")

    // -------------------------------------------------------------- audit --
    suspend fun audit(limit: Int = 50): Page<AuditEntry> = get("/audit", mapOf("limit" to limit))
    suspend fun auditVerify(): AuditVerify = get("/audit/verify")

    // ------------------------------------------------------------ plumbing --
    private fun seg(s: String): String = java.net.URLEncoder.encode(s, "UTF-8").replace("+", "%20")

    private suspend inline fun <reified T> get(path: String, query: Map<String, Any?> = emptyMap()): T =
        call(Request.Builder().url(url(path, query)).get().build(), serializer())

    private suspend inline fun <reified T> post(path: String, body: JsonElement, stepUp: String? = null): T =
        call(write("POST", path, body, stepUp), serializer())

    private suspend inline fun <reified T> put(path: String, body: JsonElement): T = call(write("PUT", path, body, null), serializer())

    private suspend fun postUnit(path: String, body: JsonElement, stepUp: String? = null) {
        execute(write("POST", path, body, stepUp)).use { check(it) }
    }

    private fun write(method: String, path: String, body: JsonElement, stepUp: String?): Request =
        Request.Builder().url(url(path))
            .method(method, json.encodeToString(JsonElement.serializer(), body).toRequestBody(JSON))
            .apply {
                if (method == "POST") header("Idempotency-Key", UUID.randomUUID().toString())
                if (stepUp != null) header("X-Step-Up", stepUp)
            }
            .build()

    private suspend fun <T> call(request: Request, s: KSerializer<T>): T = execute(request).use { r ->
        check(r)
        val text = r.body.string()
        try {
            json.decodeFromString(s, text)
        } catch (e: kotlinx.serialization.SerializationException) {
            throw ApiException(r.code, "contract_mismatch", "پاسخ سرور با قرارداد نمیخواند؛ نسخه‌ی اپ را به‌روز کن.", r.header("X-Request-Id"))
        }
    }

    private fun check(r: Response) {
        if (r.isSuccessful) return
        if (r.code == 401) tokens.clear()
        val p = runCatching { json.decodeFromString(Problem.serializer(), r.body.string()) }.getOrNull()
        if (p?.messageFa == null) throw ApiException.unexpected(r.code)
        throw ApiException(r.code, p.code, p.messageFa, p.requestId ?: r.header("X-Request-Id"))
    }

    private suspend fun execute(request: Request): Response = suspendCancellableCoroutine { cont ->
        val call = client.newCall(request)
        cont.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                if (!cont.isCancelled) cont.resumeWithException(ApiException.offline())
            }

            override fun onResponse(call: Call, response: Response) {
                cont.resume(response) { _, r, _ -> r.close() }
            }
        })
    }

    companion object {
        private val JSON = "application/json".toMediaType()

        @OptIn(ExperimentalSerializationApi::class)
        val json = Json {
            ignoreUnknownKeys = true
            explicitNulls = false
            coerceInputValues = true
            namingStrategy = JsonNamingStrategy.SnakeCase
        }
    }
}

/** Contract §2 for the Android client: Bearer session, `X-HQ-Client: android`, JSON accept. */
private class ContractHeaders(private val tokens: TokenSource) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val b = chain.request().newBuilder()
            .header("X-HQ-Client", "android")
            .header("Accept", "application/json")
        tokens.token()?.let { b.header("Authorization", "Bearer $it") }
        return chain.proceed(b.build())
    }
}
