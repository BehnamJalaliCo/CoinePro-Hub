package com.coinepro.hq.core.data

import com.coinepro.hq.core.link.AlwaysOnline
import com.coinepro.hq.core.link.Backoff
import com.coinepro.hq.core.link.Connectivity
import com.coinepro.hq.core.link.LinkStore
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.StreamEvent
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.merge
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources

enum class StreamState { CONNECTING, LIVE, OFFLINE }

/** What the stream keeps open: nothing, the alert lane only (the app is closed and the background link is on), or every lane. */
enum class StreamMode { OFF, ALERTS, FULL }

/** Where the alert lane stands, for the background link's notification and the settings. */
enum class LinkPhase { OFF, CONNECTING, LIVE, WAITING_NETWORK, RETRYING, REFUSED }

/** The alert lane's state: its phase, why it is not live, whether the last connect resumed from the last event, and since when. */
data class LaneStatus(val phase: LinkPhase, val why: String? = null, val resumed: Boolean = false, val since: Long = 0L, val retryAt: Long? = null)

/**
 * The SSE connection to `/api/v1/stream` (contract §7, §16): one per lane of topics, since the hub takes at most 200 characters of
 * `topics` ([StreamTopics]). Each event refreshes the queries it touches.
 *
 * The first lane is the alert lane ([StreamTopics.ALERTS]): it stays open while the app is closed if the background link is on
 * ([StreamMode.ALERTS], `device/HubLinkService`), so the phone hears urgent notifications, cards, orders and kill switches without a push
 * service; the other lanes open only while the app is on screen ([StreamMode.FULL]). Opening or closing the app never reconnects the alert
 * lane, and no topic is ever asked for twice: one stream, one set of connections, for the app and the background link together.
 *
 * A dropped lane reconnects with Last-Event-ID (the alert lane's is kept across process restarts, [LinkStore]) after a [Backoff] wait that
 * a new network cuts short; with no network at all it waits for one instead of retrying blind. A connection that has said nothing for
 * [STALE_S] seconds (the hub sends a heartbeat every 15 s) is treated as dead.
 */
class HoldingStream(
    private val api: Api,
    private val cache: QueryCache,
    private val scope: CoroutineScope,
    private val demo: Boolean,
    /** «خطاخوان»: drops and reconnects while the app is open are recorded (a real session only); the background link keeps its own lines. */
    private val log: com.coinepro.hq.core.diag.ErrorLog? = null,
    private val net: Connectivity = AlwaysOnline,
    /** Where the alert lane's last event id is kept across process restarts (a real session only). */
    private val store: LinkStore? = null,
) : com.coinepro.hq.core.link.LinkStream {
    private val stateFlow = MutableStateFlow(StreamState.CONNECTING)
    val state: StateFlow<StreamState> = stateFlow.asStateFlow()
    private val eventsFlow = MutableSharedFlow<StreamEvent>(extraBufferCapacity = 256)
    val events: SharedFlow<StreamEvent> = eventsFlow.asSharedFlow()
    /** Who is working right now, per company, and each company's recent events (the companies' live indicators and feeds). */
    val activity = LiveActivity()

    private val modeFlow = MutableStateFlow(StreamMode.OFF)
    override val mode: StateFlow<StreamMode> = modeFlow.asStateFlow()
    private val alertFlow = MutableStateFlow(LaneStatus(LinkPhase.OFF))
    /** The alert lane: what the background link's notification and the settings show. */
    override val alertLane: StateFlow<LaneStatus> = alertFlow.asStateFlow()
    /** Cuts a backoff wait short (the watchdog, the app coming to the front). */
    private val nudges = MutableSharedFlow<Unit>(extraBufferCapacity = 1)

    /** One connection per lane of topics ([StreamTopics.split]): the hub takes at most 200 characters of `topics` per connection. */
    private inner class Lane(val index: Int, val topics: String) {
        var source: EventSource? = null
        var lastId: String? = null
        @Volatile var state = StreamState.CONNECTING
        /** The hub refused this lane (422, or 401: the session is gone): it is not asked again until the stream starts afresh. */
        @Volatile var refused = false
        var job: Job? = null
        /** The app closed this connection on purpose (a new network, the app going to the background): not a drop. */
        @Volatile var cancelling = false
        val alert: Boolean get() = index == 0
    }

    private val lanes = StreamTopics.split().mapIndexed { i, t -> Lane(i, t) }
    private var demoJob: Job? = null
    /** When the connection last dropped (elapsed ms), so the reconnect can say after how long. */
    @Volatile private var droppedAt: Long? = null
    private val client: OkHttpClient by lazy { api.streamClient.newBuilder().readTimeout(STALE_S, TimeUnit.SECONDS).build() }

    /** The URLs the stream opens, one per lane (what the hub must accept: [StreamTopics.accepted]). */
    fun urls(): List<okhttp3.HttpUrl> = lanes.map { api.url("/stream", StreamTopics.query(it.topics)) }

    /** Every lane: the app is on screen. */
    fun start() = setMode(StreamMode.FULL)

    /** The alert lane only: the app went to the background and the background link is on. */
    fun background() = setMode(StreamMode.ALERTS)

    /** Nothing: signed out, or the background link is off and the app is closed. */
    fun stop() = setMode(StreamMode.OFF)

    /** A waiting lane tries again now (the watchdog found the link down; the app came to the front). */
    override fun nudge() { nudges.tryEmit(Unit) }

    @Synchronized
    override fun setMode(m: StreamMode) {
        val before = modeFlow.value
        if (m == before) { if (m != StreamMode.OFF) nudge(); return }
        modeFlow.value = m
        if (demo) {
            if (m == StreamMode.OFF) { demoJob?.cancel(); demoJob = null; alertFlow.value = LaneStatus(LinkPhase.OFF) }
            else {
                if (demoJob?.isActive != true) demoJob = scope.launch { demoPulse() }
                alertFlow.value = LaneStatus(LinkPhase.LIVE, since = now())
                if (m == StreamMode.ALERTS) com.coinepro.hq.Demo.background()
            }
            stateFlow.value = if (m == StreamMode.OFF) StreamState.OFFLINE else StreamState.LIVE
            return
        }
        for (lane in lanes) {
            val wanted = m == StreamMode.FULL || (m == StreamMode.ALERTS && lane.alert)
            val running = lane.job?.isActive == true
            when {
                wanted && !running -> { lane.refused = false; lane.job = scope.launch { runLane(lane) } }
                !wanted && running -> close(lane)
            }
        }
        if (m == StreamMode.OFF) alertFlow.value = LaneStatus(LinkPhase.OFF)
        if (m != StreamMode.OFF) nudge()
        publish()
    }

    private fun close(lane: Lane) {
        lane.cancelling = true
        lane.job?.cancel()
        lane.job = null
        lane.source?.cancel()
        lane.source = null
        lane.state = StreamState.CONNECTING
    }

    private fun laneStatus(lane: Lane, s: LaneStatus) {
        if (lane.alert) alertFlow.value = s
    }

    private suspend fun runLane(lane: Lane) = coroutineScope {
        if (lane.alert && lane.lastId == null) {
            // Resume where the alert lane stopped before the process ended, if that was recent: the replay is what the phone missed.
            val saved = store?.lastEventId
            if (saved != null && System.currentTimeMillis() - (store?.lastEventAt ?: 0L) < LinkStore.RESUME_MS) lane.lastId = saved
        }
        var attempt = 0
        while (isActive && !lane.refused) {
            if (!net.online.value) {
                lane.state = StreamState.OFFLINE
                publish()
                laneStatus(lane, LaneStatus(LinkPhase.WAITING_NETWORK, "no network", since = now()))
                net.online.first { it }
                attempt = 0
            }
            lane.state = if (attempt == 0) StreamState.CONNECTING else StreamState.OFFLINE
            publish()
            laneStatus(lane, LaneStatus(if (attempt == 0) LinkPhase.CONNECTING else LinkPhase.RETRYING, alertFlow.value.why, since = now()))
            val closed = CompletableDeferred<Unit>()
            var why: String? = null
            var switched = false
            val resumed = lane.lastId != null
            lane.cancelling = false
            lane.source = open(lane, resumed, onWhy = { why = it }) { closed.complete(Unit) }
            // A new default network: the socket on the old one is dropped and the lane reconnects on the new one at once.
            val watcher = launch {
                net.changed.first()
                switched = true
                lane.cancelling = true
                lane.source?.cancel()
                closed.complete(Unit)
            }
            closed.await()
            watcher.cancel()
            val wasLive = lane.state == StreamState.LIVE
            lane.source = null
            lane.state = StreamState.OFFLINE
            publish()
            if (lane.refused) {
                laneStatus(lane, LaneStatus(LinkPhase.REFUSED, why, since = now()))
                break
            }
            attempt = when {
                switched -> 0
                wasLive -> 1
                else -> attempt + 1
            }
            val wait = Backoff.delayMs(attempt, if (modeFlow.value == StreamMode.FULL) Backoff.FOREGROUND_CAP_MS else Backoff.BACKGROUND_CAP_MS)
            laneStatus(lane, LaneStatus(LinkPhase.RETRYING, if (switched) "network changed" else why, since = now(), retryAt = now() + wait))
            if (wait > 0) withTimeoutOrNull(wait) { merge(nudges, net.changed).first() }
        }
        publish()
    }

    /** One state for the top bar: live when every lane on is, offline when one dropped, connecting otherwise. */
    private fun publish() {
        val asked = lanes.filter { it.job?.isActive == true && !it.refused }
        stateFlow.value = when {
            asked.isEmpty() -> StreamState.OFFLINE
            asked.all { it.state == StreamState.LIVE } -> StreamState.LIVE
            asked.any { it.state == StreamState.OFFLINE } -> StreamState.OFFLINE
            else -> StreamState.CONNECTING
        }
    }

    private fun open(lane: Lane, resumed: Boolean, onWhy: (String) -> Unit, onClosed: () -> Unit): EventSource {
        val req = Request.Builder()
            .url(api.url("/stream", StreamTopics.query(lane.topics)))
            .header("Accept", "text/event-stream")
            .apply { lane.lastId?.let { header("Last-Event-ID", it) } }
            .build()
        return EventSources.createFactory(client).newEventSource(req, object : EventSourceListener() {
            override fun onOpen(eventSource: EventSource, response: Response) {
                lane.state = StreamState.LIVE
                publish()
                laneStatus(lane, LaneStatus(LinkPhase.LIVE, resumed = resumed, since = now()))
                api.hub?.ok()
                if (modeFlow.value == StreamMode.FULL && stateFlow.value == StreamState.LIVE) droppedAt?.let { t ->
                    val s = (android.os.SystemClock.elapsedRealtime() - t + 500) / 1000
                    log?.note("stream", com.coinepro.hq.core.diag.LEVEL_INFO, "reconnected", "the live stream is back after $s s" + (lane.lastId?.let { " (resumed from the last event)" } ?: ""))
                    log?.crumb("stream live")
                    droppedAt = null
                }
            }

            override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                if (id != null) {
                    lane.lastId = id
                    if (lane.alert) store?.let { it.lastEventId = id; it.lastEventAt = System.currentTimeMillis() }
                }
                val parsed = runCatching { Api.json.decodeFromString(StreamEvent.serializer(), data) }.getOrNull()
                val event = (parsed ?: StreamEvent()).copy(id = id ?: parsed?.id.orEmpty(), type = type ?: parsed?.type.orEmpty())
                dispatch(event)
            }

            override fun onClosed(eventSource: EventSource) {
                if (lane.cancelling) return onClosed()
                onWhy("closed by the hub")
                dropped(null, "closed by the hub", null)
                onClosed()
            }

            override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                if (lane.cancelling) { response?.close(); return onClosed() }
                val code = response?.code
                if (code == 401) { lane.refused = true; api.unauthorized() }
                // The hub ignores topics it does not know (⟨1.4.2⟩); a 422 now is a malformed value, and asking again will not mend it.
                if (code == 422) lane.refused = true
                if (response == null || code in 502..504) api.hub?.transient()
                onWhy(
                    when {
                        code == 401 -> "session expired"
                        code != null -> "HTTP $code"
                        t is java.net.SocketTimeoutException -> "silent for $STALE_S s"
                        else -> t?.let { it::class.simpleName } ?: "no answer"
                    },
                )
                dropped(code, if (response == null) "no answer" else "refused", t?.let { it::class.simpleName })
                response?.close()
                onClosed()
            }
        })
    }

    /** A drop goes to the log once per outage while the app is open (a burst of failed reconnects collapses there, like the calls). */
    private fun dropped(status: Int?, title: String, cause: String?) {
        if (modeFlow.value != StreamMode.FULL) return
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

    private fun now() = System.currentTimeMillis()

    private fun dispatch(e: StreamEvent) {
        val tags = INVALIDATE.firstOrNull { e.type.startsWith(it.first) }?.second
        if (tags != null) cache.invalidate(*tags)
        activity.on(e)
        eventsFlow.tryEmit(e)
    }

    /**
     * The screenshot tests' stream: the demo's first [ticks] beats played at once, and nothing after them — no clock drives it, so a
     * screen that shows the stream (its live feed, the agents' rings) looks the same however fast the machine runs or in what order the
     * tests run. Debug builds only (the release build has no demo).
     */
    fun demoSeed(ticks: Int) {
        if (!demo) return
        modeFlow.value = StreamMode.FULL
        stateFlow.value = StreamState.LIVE
        for (t in 0 until ticks) for (e in com.coinepro.hq.Demo.next(t)) dispatch(e)
    }

    /** The demo holding's stream (debug builds): the demo's own script of runs, outputs and cards, and what the owner's actions
     *  there cause (a stopped company's runs end). Release builds have no demo. */
    private suspend fun demoPulse() {
        stateFlow.value = StreamState.LIVE
        var tick = 0
        while (true) {
            // With the app closed the demo's link, like the real one, hears the alert topics only.
            val alertsOnly = modeFlow.value == StreamMode.ALERTS
            for (e in com.coinepro.hq.Demo.next(tick)) if (!alertsOnly || StreamTopics.ALERT_PREFIXES.any { e.type.startsWith(it) }) dispatch(e)
            delay(600)
            tick++
        }
    }

    companion object {
        /** No byte for this long (three of the hub's 15 s heartbeats and some) and the connection is taken for dead. */
        const val STALE_S = 50L

        // Event type prefix -> query tags to refresh (mirrors apps/web/src/lib/stream.ts).
        private val INVALIDATE: List<Pair<String, Array<String>>> = listOf(
            "decision." to arrayOf("decisions", "inbox", "away"),
            "deliverable." to arrayOf("deliverables", "inbox"),
            // ⟨1.9⟩ §27.2: a council's members and its synthesis (the order's «شورا» section), before the rest of `work.`.
            "work.council" to arrayOf("council", "work"),
            "work." to arrayOf("work", "planner", "companies"),
            "message." to arrayOf("threads", "messages", "inbox"),
            "notification." to arrayOf("notifications", "inbox"),
            "control." to arrayOf("control", "companies"),
            "employee." to arrayOf("employees", "companies"),
            "presence." to arrayOf("presence", "inbox"),
            "budget." to arrayOf("treasury"),
            "llm." to arrayOf("treasury"),
            "run." to arrayOf("runs"),
            // ⟨1.9⟩ §27.3 `file.transcribed`: the hub's transcript of a voice message, a voice note or an audio file.
            "file." to arrayOf("messages", "files", "notes"),
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
            // ⟨1.8⟩ §26.4: a server's state, each call on it (its activity, the control room's live calls) and a destructive call held
            // for the owner's seal (its `server_destructive` card in the cartable).
            "server.awaiting_seal" to arrayOf("servers", "decisions", "inbox"),
            // ⟨1.8⟩ §26.6: a runner's state carries its road to the hub (`via`, `hub_rtt_ms`), so the network map reads again.
            "server.state" to arrayOf("servers", "network"),
            "server." to arrayOf("servers"),
        )
    }
}
