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
import okhttp3.Request
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources

enum class StreamState { CONNECTING, LIVE, OFFLINE }

/** The SSE connection to `/api/v1/stream` (contract §7, §16): one per lane of topics, since the hub takes at most 200 characters of
 *  `topics` ([StreamTopics]). Each event refreshes the queries it touches; reconnects back off from 1 s to 30 s and resume with
 *  Last-Event-ID. Runs only in the foreground. */
class HoldingStream(
    private val api: Api,
    private val cache: QueryCache,
    private val scope: CoroutineScope,
    private val demo: Boolean,
    /** «خطاخوان»: drops and reconnects are recorded (a real session only). */
    private val log: com.coinepro.hq.core.diag.ErrorLog? = null,
) {
    private val stateFlow = MutableStateFlow(StreamState.CONNECTING)
    val state: StateFlow<StreamState> = stateFlow.asStateFlow()
    private val eventsFlow = MutableSharedFlow<StreamEvent>(extraBufferCapacity = 64)
    val events: SharedFlow<StreamEvent> = eventsFlow.asSharedFlow()
    /** Who is working right now, per company, and each company's recent events (the companies' live indicators and feeds). */
    val activity = LiveActivity()

    /** One connection per lane of topics ([StreamTopics.lanes]): the hub takes at most 200 characters of `topics` per connection. */
    private inner class Lane(val index: Int, var topics: String) {
        var source: EventSource? = null
        var lastId: String? = null
        @Volatile var state = StreamState.CONNECTING
        /** The hub refused this lane's topics (an older hub): it is not asked again this session. */
        @Volatile var refused = false
    }

    private val lanes = StreamTopics.lanes().mapIndexed { i, t -> Lane(i, t) }
    private var loops: List<Job> = emptyList()
    /** When the connection last dropped (elapsed ms), so the reconnect can say after how long. */
    @Volatile private var droppedAt: Long? = null
    /** The app is going to the background: the connection is closed on purpose, not dropped. */
    @Volatile private var stopping = false

    /** The URLs the stream opens, one per lane (what the hub must accept: [StreamTopics.accepted]). */
    fun urls(): List<okhttp3.HttpUrl> = lanes.map { api.url("/stream", StreamTopics.query(it.topics)) }

    fun start() {
        if (loops.any { it.isActive }) return
        stopping = false
        if (demo) {
            loops = listOf(scope.launch { demoPulse() })
            return
        }
        loops = lanes.map { lane ->
            scope.launch {
                var retry = 0
                while (isActive && !lane.refused) {
                    lane.state = if (retry == 0) StreamState.CONNECTING else StreamState.OFFLINE
                    publish()
                    val closed = kotlinx.coroutines.CompletableDeferred<Unit>()
                    lane.source = open(lane) { closed.complete(Unit) }
                    closed.await()
                    retry = if (lane.state == StreamState.LIVE) 1 else retry + 1
                    lane.state = StreamState.OFFLINE
                    publish()
                    if (lane.refused) break
                    delay(min(30_000L, 1_000L shl min(retry - 1, 5)))
                }
                publish()
            }
        }
    }

    fun stop() {
        stopping = true
        loops.forEach { it.cancel() }
        loops = emptyList()
        for (l in lanes) { l.source?.cancel(); l.source = null }
    }

    /** One state for the top bar: live when every lane the hub serves is, offline when one dropped, connecting otherwise. */
    private fun publish() {
        val asked = lanes.filter { !it.refused }
        stateFlow.value = when {
            asked.isEmpty() -> StreamState.OFFLINE
            asked.all { it.state == StreamState.LIVE } -> StreamState.LIVE
            asked.any { it.state == StreamState.OFFLINE } -> StreamState.OFFLINE
            else -> StreamState.CONNECTING
        }
    }

    private fun open(lane: Lane, onClosed: () -> Unit): EventSource {
        val req = Request.Builder()
            .url(api.url("/stream", StreamTopics.query(lane.topics)))
            .header("Accept", "text/event-stream")
            .apply { lane.lastId?.let { header("Last-Event-ID", it) } }
            .build()
        return EventSources.createFactory(api.streamClient).newEventSource(req, object : EventSourceListener() {
            override fun onOpen(eventSource: EventSource, response: Response) {
                lane.state = StreamState.LIVE
                publish()
                api.hub?.ok()
                if (stateFlow.value == StreamState.LIVE) droppedAt?.let { t ->
                    val s = (android.os.SystemClock.elapsedRealtime() - t + 500) / 1000
                    log?.note("stream", com.coinepro.hq.core.diag.LEVEL_INFO, "reconnected", "the live stream is back after $s s" + (lane.lastId?.let { " (resumed from the last event)" } ?: ""))
                    log?.crumb("stream live")
                    droppedAt = null
                }
            }

            override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                if (id != null) lane.lastId = id
                val parsed = runCatching { Api.json.decodeFromString(StreamEvent.serializer(), data) }.getOrNull()
                val event = (parsed ?: StreamEvent()).copy(id = id ?: parsed?.id.orEmpty(), type = type ?: parsed?.type.orEmpty())
                dispatch(event)
            }

            override fun onClosed(eventSource: EventSource) {
                dropped(null, "closed by the hub", null)
                onClosed()
            }

            override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                if (response?.code == 401) api.unauthorized()
                if (response?.code == 422) {
                    // An older hub refusing a topic it does not know (before ⟨1.4.2⟩): the first lane keeps the core topics, the others stop.
                    if (lane.index == 0 && lane.topics != CORE_TOPICS) lane.topics = CORE_TOPICS else lane.refused = true
                }
                if (response == null || response.code in 502..504) api.hub?.transient()
                dropped(response?.code, if (response == null) "no answer" else "refused", t?.let { it::class.simpleName })
                response?.close()
                onClosed()
            }
        })
    }

    /** A drop goes to the log once per outage (a burst of failed reconnects collapses there, like the calls). */
    private fun dropped(status: Int?, title: String, cause: String?) {
        if (stopping) return
        if (droppedAt == null) {
            droppedAt = android.os.SystemClock.elapsedRealtime()
            log?.crumb("stream dropped")
        }
        log?.record(
            com.coinepro.hq.core.net.ApiFailure(
                "stream", "GET", "/api/v1/stream", status, if (status == null || status in 502..504) "hub_unreachable" else "stream_refused", title, detail = cause,
            ),
        )
    }

    private fun dispatch(e: StreamEvent) {
        val tags = INVALIDATE.firstOrNull { e.type.startsWith(it.first) }?.second
        if (tags != null) cache.invalidate(*tags)
        activity.on(e)
        eventsFlow.tryEmit(e)
    }

    /** The demo holding's stream (debug builds): the demo's own script of runs, outputs and cards, and what the owner's actions
     *  there cause (a stopped company's runs end). Release builds have no demo. */
    private suspend fun demoPulse() {
        stateFlow.value = StreamState.LIVE
        var tick = 0
        while (true) {
            for (e in com.coinepro.hq.Demo.next(tick)) dispatch(e)
            delay(600)
            tick++
        }
    }

    private companion object {
        val CORE_TOPICS = StreamTopics.CORE.joinToString(",")

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
            // ⟨1.5⟩ §19.9: the radar (revenue.day, revenue.alert), the desk (support.message, .queue, .channel), rescue and lifecycle
            // sends, a closed NPS wave (its comments reach the feedback inbox), and feedback items.
            "revenue." to arrayOf("revenue"),
            "support." to arrayOf("support"),
            "rescue." to arrayOf("growth"),
            "lifecycle." to arrayOf("growth"),
            "nps." to arrayOf("growth", "feedback"),
            "feedback." to arrayOf("feedback"),
            // ⟨1.5⟩ §20.11: a meeting's turns, claims and whispers (the room and the planner); a sealed charter; a stale KPI (cards
            // and the scorecard); OKR and outcome updates; risks; calendar conflicts (the deploy cards carry them too); knowledge.
            "meeting." to arrayOf("meetings", "planner"),
            "charter." to arrayOf("charter"),
            "kpi." to arrayOf("cards", "scorecards", "kpis"),
            "okr." to arrayOf("okr"),
            "outcome." to arrayOf("outcomes"),
            "risk." to arrayOf("risks"),
            "calendar." to arrayOf("calendar", "planner", "decisions"),
            "knowledge." to arrayOf("knowledge"),
            // ⟨1.5⟩ §21.12: a memo is ready (the card shows it), a proactive note (thread A), an answer, the weekly review, a briefing,
            // ranks and the HR round (its cards), a note, a claim's verdict (the health board), a scored prediction, a substitute's
            // state, a creative. `decision.reminded` is covered by `decision.`.
            "memo." to arrayOf("memos", "decisions"),
            "advisor." to arrayOf("advisor", "messages", "threads"),
            "ask." to arrayOf("ask"),
            "review." to arrayOf("reviews"),
            "briefing." to arrayOf("briefings"),
            "rankings." to arrayOf("rankings"),
            "hr." to arrayOf("hr", "decisions"),
            "note." to arrayOf("notes"),
            "claim." to arrayOf("claims", "runs-health"),
            "dceo." to arrayOf("dceo", "decisions"),
            "substitute." to arrayOf("substitutes", "treasury"),
            "creative." to arrayOf("creatives"),
            // ⟨1.6⟩ §22.6: an item moved in the pipeline (the board, its series, the cards it raised); a case changed (its thread L and its
            // email cards); a role written on demand changed state (the department's roles, GET /roles for hiring, the story it makes).
            "media." to arrayOf("media", "decisions"),
            "legal." to arrayOf("legal", "threads", "decisions"),
            "role." to arrayOf("roles", "stories", "decisions"),
            // ⟨1.7⟩ §23.11: a record filed, changed or sealed; a reminder due; a hold placed or released (its case too); a fixity failure;
            // a schema change (and the archivist's cards it may void).
            "record." to arrayOf("archive"),
            "reminder." to arrayOf("archive"),
            "hold." to arrayOf("archive", "legal"),
            "fixity." to arrayOf("archive"),
            "schema." to arrayOf("archive", "decisions"),
        )
    }
}
