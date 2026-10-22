package com.coinepro.hq.core.data

import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.StreamEvent
import kotlin.math.min
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.Request
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources

enum class StreamState { CONNECTING, LIVE, OFFLINE }

/** The one SSE connection to `/api/v1/stream` (contract §7, §16). Each event refreshes the queries it
 *  touches; reconnects back off from 1 s to 30 s and resume with Last-Event-ID. Runs only in the foreground. */
class HoldingStream(
    private val api: Api,
    private val cache: QueryCache,
    private val scope: CoroutineScope,
    private val demo: Boolean,
) {
    private val stateFlow = MutableStateFlow(StreamState.CONNECTING)
    val state: StateFlow<StreamState> = stateFlow.asStateFlow()
    private val eventsFlow = MutableSharedFlow<StreamEvent>(extraBufferCapacity = 64)
    val events: SharedFlow<StreamEvent> = eventsFlow.asSharedFlow()

    private var source: EventSource? = null
    private var loop: Job? = null
    private var lastId: String? = null
    /** A server older than contract v1.4.2 refuses topics it does not know (422); then only the core topics are asked for. */
    private var coreOnly = false

    fun start() {
        if (loop?.isActive == true) return
        loop = scope.launch {
            if (demo) return@launch demoPulse()
            var retry = 0
            while (isActive) {
                stateFlow.value = if (retry == 0) StreamState.CONNECTING else StreamState.OFFLINE
                val closed = kotlinx.coroutines.CompletableDeferred<Unit>()
                source = open { closed.complete(Unit) }
                closed.await()
                retry = if (stateFlow.value == StreamState.LIVE) 1 else retry + 1
                stateFlow.value = StreamState.OFFLINE
                delay(min(30_000L, 1_000L shl min(retry - 1, 5)))
            }
        }
    }

    fun stop() {
        loop?.cancel()
        source?.cancel()
        source = null
    }

    private fun open(onClosed: () -> Unit): EventSource {
        val req = Request.Builder()
            .url(api.url("/stream", mapOf("topics" to if (coreOnly) CORE_TOPICS else TOPICS)))
            .header("Accept", "text/event-stream")
            .apply { lastId?.let { header("Last-Event-ID", it) } }
            .build()
        return EventSources.createFactory(api.streamClient).newEventSource(req, object : EventSourceListener() {
            override fun onOpen(eventSource: EventSource, response: Response) {
                stateFlow.value = StreamState.LIVE
            }

            override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                if (id != null) lastId = id
                val parsed = runCatching { Api.json.decodeFromString(StreamEvent.serializer(), data) }.getOrNull()
                val event = (parsed ?: StreamEvent()).copy(id = id ?: parsed?.id.orEmpty(), type = type ?: parsed?.type.orEmpty())
                dispatch(event)
            }

            override fun onClosed(eventSource: EventSource) = onClosed()

            override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                if (response?.code == 401) api.unauthorized()
                if (response?.code == 422) coreOnly = true
                response?.close()
                onClosed()
            }
        })
    }

    private fun dispatch(e: StreamEvent) {
        val tags = INVALIDATE.firstOrNull { e.type.startsWith(it.first) }?.second
        if (tags != null) cache.invalidate(*tags)
        eventsFlow.tryEmit(e)
    }

    private suspend fun demoPulse() {
        stateFlow.value = StreamState.LIVE
        var n = 0
        val companies = listOf("TY", "FX", "PC")
        while (true) {
            delay(2_400)
            n++
            val data: JsonObject = buildJsonObject { put("pulse", n) }
            eventsFlow.tryEmit(StreamEvent(n.toString(), "activity.changed", "", companies[n % companies.size], null, data))
        }
    }

    private companion object {
        const val CORE_TOPICS = "work,decisions,deliverables,messages,notifications,activity,llm,control"

        // Unknown topics are ignored from contract v1.4.2 on, so the app names every topic it can use, the newer ones too.
        const val TOPICS = "$CORE_TOPICS,runs,files,workshop,orders,oversight,inquiries,errands,stars,skills,academy,founding,backups,stories,companies"

        // Event type prefix -> query tags to refresh (mirrors apps/web/src/lib/stream.ts).
        val INVALIDATE: List<Pair<String, Array<String>>> = listOf(
            "decision." to arrayOf("decisions", "inbox", "away"),
            "deliverable." to arrayOf("deliverables", "inbox"),
            "work." to arrayOf("work", "planner", "companies"),
            "message." to arrayOf("threads", "messages", "inbox"),
            "notification." to arrayOf("notifications", "inbox"),
            "control." to arrayOf("control", "companies"),
            "employee." to arrayOf("employees", "companies"),
            "presence." to arrayOf("presence", "inbox"),
            "budget." to arrayOf("treasury"),
            "llm." to arrayOf("treasury"),
            "run." to arrayOf("runs"),
            "file." to arrayOf("messages"),
            "workshop." to arrayOf("workshop"),
            "order." to arrayOf("orders", "planner", "work"),
            // ⟨1.4⟩ §18.10 and ⟨1.4.2⟩ §18.11
            "hiring." to arrayOf("hiring"),
            "story." to arrayOf("stories"),
            "oversight." to arrayOf("oversight"),
            "inquiry." to arrayOf("inquiries"),
            "errand." to arrayOf("errands"),
            "stars." to arrayOf("stars"),
            "skill." to arrayOf("skills"),
            "academy." to arrayOf("academy"),
            "founding." to arrayOf("founding"),
            "provision." to arrayOf("founding"),
            "backup." to arrayOf("backups"),
            // ⟨1.4.6⟩ §18.14: a traced or sealed brand — the company's versions, every mark and seal, the founding's step.
            "brand." to arrayOf("brand", "brands", "companies", "founding"),
        )
    }
}
