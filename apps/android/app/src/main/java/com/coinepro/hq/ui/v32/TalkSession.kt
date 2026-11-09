package com.coinepro.hq.ui.v32

import android.media.AudioManager
import android.media.ToneGenerator
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import com.coinepro.hq.core.Env
import com.coinepro.hq.core.data.AudioOrder
import com.coinepro.hq.core.data.SOURCE_TYPED
import com.coinepro.hq.core.data.TalkEvent
import com.coinepro.hq.core.data.latestOf
import com.coinepro.hq.core.data.parseTalkEvent
import com.coinepro.hq.core.media.FILES_ONLY_TEXT
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.TalkAudio
import com.coinepro.hq.core.net.TalkCard
import com.coinepro.hq.core.net.TalkConversation
import com.coinepro.hq.core.net.TalkPersona
import com.coinepro.hq.core.net.TalkTurn
import com.coinepro.hq.core.net.VoiceMeter
import com.coinepro.hq.core.net.turnFilesUnknown
import com.coinepro.hq.ui.Toasts
import java.util.UUID
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.Request
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources

/** What the persona is doing now: nothing, thinking (or using tools), writing the answer. Speaking is [TalkSession.speaking]. */
enum class Phase { IDLE, THINKING, WRITING }

/**
 * One open conversation of the talk screen (contract §32): its turns, the answer being streamed, the sentences being played in order,
 * and the owner's barge-in. Screens read its snapshot state; the network, the stream and the player live here, not in the composables.
 *
 * A turn is `POST /talk/conversations/{ref}/turns`; its answer streams on `GET /talk/turns/{id}/events` ([TalkEvent]s): the text as it is
 * written, the audio of each sentence (played in `seq` order), cards, the meter and the end. A stream that cannot open is made up for by
 * reading the conversation a few times (the stored answer still arrives). Demo sessions play the stored answer back as a script with no
 * sound, so screenshots and the demo are the same on any machine.
 */
@Stable
class TalkSession(private val env: Env, private val scope: CoroutineScope, private val toasts: Toasts) {
    var personas by mutableStateOf<List<TalkPersona>>(emptyList())
    var conv by mutableStateOf<TalkConversation?>(null)
    val turns = mutableStateListOf<TalkTurn>()
    var loading by mutableStateOf(true)
        private set
    var error by mutableStateOf<ApiException?>(null)
        private set

    var phase by mutableStateOf(Phase.IDLE)
        private set
    /** The answer as it is written (`show_md`), the cards that came with it, and why it failed. */
    var liveText by mutableStateOf("")
        private set
    val liveCards = mutableStateListOf<TalkCard>()
    var liveFailed by mutableStateOf<String?>(null)
        private set
    /** The sentence audio is playing now: the speaker's face glows. */
    var speaking by mutableStateOf(false)
        private set
    /** Plain lines the app says once in the chat («سقف ماه پر شد؛ با صدای ساده ادامه میدهم»). */
    val notices = mutableStateListOf<String>()
    /** The meter as the stream last said it: the counter moves live. */
    var meterLive by mutableStateOf<VoiceMeter?>(null)
        private set
    /** The engine lights as the stream last said them: engine → (state, reason). */
    var lightsLive by mutableStateOf<Map<String, Pair<String, String?>>>(emptyMap())
        private set

    /** The id of the answer being streamed, for `…/stop`. */
    var answerId: String? = null
        private set
    private var streamJob: Job? = null
    private var watchdog: Job? = null
    private val order = AudioOrder<TalkAudio>()
    private var player: ExoPlayer? = null
    private var tone: ToneGenerator? = null
    private var toneJob: Job? = null
    private var demoPlayJob: Job? = null
    private var queued = 0

    /** Told when the whole answer is over (the text is in and the last sentence has been played): hands-free listens again. */
    var onAnswerEnded: (() -> Unit)? = null
    private var streamDone = true

    val busy: Boolean get() = phase != Phase.IDLE || speaking
    val presentIds: List<String> get() = conv?.let { listOf(it.persona) + it.presentIds }?.distinct().orEmpty()
    /** The persona answering now. */
    val speakerId: String? get() = conv?.persona

    // ------------------------------------------------------------ opening --
    suspend fun loadPersonas() {
        runCatching { env.api.talkPersonas() }.onSuccess { personas = it }
    }

    /** Opens conversation [ref]. */
    suspend fun open(ref: String) {
        loading = true; error = null
        try {
            val d = env.api.talkConversation(ref)
            conv = d.conversation.takeIf { it.ref.isNotBlank() } ?: TalkConversation(ref = ref)
            turns.clear(); turns.addAll(d.turns.sortedBy { it.n })
        } catch (e: ApiException) {
            error = e
        } finally {
            loading = false
        }
    }

    /** Opens the newest conversation with persona [id] (`secretary`, `ceo@TY`), or starts one. */
    suspend fun openPersona(id: String) {
        loading = true; error = null
        stopAll()
        try {
            val latest = latestOf(runCatching { env.api.talkConversations(persona = id) }.getOrDefault(emptyList()), id)
            if (latest != null) open(latest.ref) else startNew(id)
        } catch (e: ApiException) {
            error = e; loading = false
        }
    }

    /** A new conversation with persona [id]; a manager's id is `role@CODE`. */
    suspend fun startNew(id: String, mode: String? = null) {
        stopAll()
        try {
            val role = id.substringBefore('@', "").ifBlank { null }
            val company = id.substringAfter('@', "").ifBlank { null }
            val c = if (company != null) env.api.newTalkConversation("manager", role, company, mode) else env.api.newTalkConversation(id, mode = mode)
            conv = c
            turns.clear()
            error = null
        } catch (e: ApiException) {
            error = e
        } finally {
            loading = false
        }
    }

    /** Re-reads the open conversation (a stream event, the end of an answer, a card done). */
    suspend fun reload() {
        val ref = conv?.ref ?: return
        try {
            val d = env.api.talkConversation(ref)
            conv = d.conversation.takeIf { it.ref.isNotBlank() } ?: conv
            // The page replaces the list only when it brings the turns; a hub that sends none leaves what the app has.
            if (d.turns.isNotEmpty()) { turns.clear(); turns.addAll(d.turns.sortedBy { it.n }) }
        } catch (_: ApiException) {
        }
    }

    suspend fun setMode(mode: String) {
        val c = conv ?: return
        try {
            conv = env.api.patchTalkConversation(c.ref, mode = mode).takeIf { it.ref.isNotBlank() } ?: c.copy(mode = mode)
        } catch (e: ApiException) {
            toasts.error(e.messageFa)
        }
    }

    // ------------------------------------------------------------ sending --
    /** ⟨1.17⟩ §35.4 in an order's session: who answers the owner's next turn (a participant's key, or `all`); null: the holder. */
    var addressee by mutableStateOf<String?>(null)

    /** ⟨1.16⟩ §34.3 an order's session with the owner's turn open (or no talk yet): his words go to the order's reply instead. */
    /** Takes the owner's words first: true sent, false not (the draft stays), null not taken (they go as an ordinary turn). */
    var interceptor: (suspend (text: String, source: String) -> Boolean?)? = null

    /** Sends a turn of the owner and follows the answer; false when it could not go (the draft stays with the caller).
     *
     *  ⟨1.18⟩ §36.2 [files]: the owner's uploads go with the turn (`file_ids`); the words may then be empty, and the hub still gets a
     *  short line ([FILES_ONLY_TEXT]). While the owner's turn of the order is open (§34.3, [interceptor]) the files go in a turn of their
     *  own (in a session they belong to the order, §36.3) and his words to the order's reply. [onFilesSent] is told once the files went,
     *  even when the words after them did not. */
    suspend fun send(text: String, source: String = SOURCE_TYPED, files: List<FileRef> = emptyList(), onFilesSent: () -> Unit = {}): Boolean {
        val body = text.trim()
        val sent = files.filter { it.id.isNotBlank() }
        if (body.isEmpty() && sent.isEmpty()) return false
        val reply = interceptor
        if (sent.isEmpty()) reply?.let { r -> r(body, source)?.let { return it } }
        if (sent.isNotEmpty() && reply != null) {
            if (conv == null) { toasts.error("گفتگوی این جلسه هنوز باز نشده؛ فایل را کمی بعد بفرست."); return false }
            if (!turn(FILES_ONLY_TEXT, source, sent)) return false
            onFilesSent()
            return body.isEmpty() || (reply(body, source) ?: turn(body, source, emptyList()))
        }
        val ok = turn(body.ifEmpty { FILES_ONLY_TEXT }, source, sent)
        if (ok && sent.isNotEmpty()) onFilesSent()
        return ok
    }

    private suspend fun turn(body: String, source: String, files: List<FileRef>): Boolean {
        if (busy) bargeIn()
        val c = conv ?: run {
            startNew("secretary")
            conv ?: return false
        }
        val clientId = UUID.randomUUID().toString()
        val mine = TalkTurn(
            id = JsonPrimitive("local-$clientId"), conversation = c.ref, n = (turns.maxOfOrNull { it.n } ?: 0) + 1, by = "owner", source = source, text = body,
            at = com.coinepro.hq.core.format.HqClock.now().toString(), files = files,
        )
        turns.add(mine)
        beginAnswer()
        return try {
            val out = env.api.sendTalkTurn(c.ref, body, source, clientId, addressee, files.map { it.id })
            val i = turns.indexOf(mine)
            // A hub that does not write the files back on the turn: the ones the owner sent stay on his bubble.
            if (out.turn.owner && i >= 0) turns[i] = if (out.turn.files.isEmpty() && files.isNotEmpty()) out.turn.copy(files = files) else out.turn
            val id = out.turn.idText.ifBlank { null }
            if (id == null) { endAnswer(); reload(); true } else {
                answerId = id
                follow(id, out.events)
                true
            }
        } catch (e: ApiException) {
            turns.remove(mine)
            endAnswer()
            if (files.isNotEmpty() && e.turnFilesUnknown) {
                // A hub before ⟨1.18⟩: no file in a conversation yet; the paperclip goes until the next app start.
                e.logged?.let { env.api.failures?.forget(it) }
                env.api.gaps.mark(HubFeature.TALK_FILES)
                toasts.error("هاب هنوز فایل را در گفتگو نمیگیرد؛ با به‌روزرسانی بعدی هاب میاید. حرفت را بدون فایل بفرست.")
            } else toasts.error(e.messageFa)
            false
        }
    }

    private fun beginAnswer() {
        phase = Phase.THINKING
        liveText = ""; liveCards.clear(); liveFailed = null
        streamDone = false
        order.reset(); queued = 0
        startTone()
    }

    private fun endAnswer() {
        phase = Phase.IDLE
        streamDone = true
        stopTone()
    }

    private fun follow(id: String, events: String?) {
        streamJob?.cancel(); watchdog?.cancel()
        val ref = conv?.ref
        streamJob = scope.launch {
            var got = false
            try {
                (if (env.demo) demoEvents(id) else events(id, events)).collect { e ->
                    got = true
                    apply(e)
                }
            } catch (_: kotlinx.coroutines.CancellationException) {
                return@launch
            } catch (_: Exception) {
            }
            // A stream that never opened: the stored answer is read a few times, slower and slower.
            if (!got && !env.demo) for (wait in listOf(2_000L, 4_000L, 8_000L, 12_000L, 20_000L)) {
                delay(wait)
                reload()
                if (turns.lastOrNull()?.owner == false) break
            }
            finishStream(ref)
        }
        // Ninety seconds of no news ends the wait quietly; the stored answer still arrives.
        watchdog = scope.launch {
            delay(NO_NEWS_MS)
            if (phase != Phase.IDLE && !speaking) { streamJob?.cancel(); finishStream(ref) }
        }
    }

    private suspend fun finishStream(ref: String?) {
        watchdog?.cancel()
        streamDone = true
        if (phase != Phase.IDLE) phase = Phase.IDLE
        stopTone()
        if (ref != null && ref == conv?.ref) reload()
        // The stored answer is in the list now: the live bubble gives way to it.
        liveText = ""; liveCards.clear()
        env.cache.invalidate("talk", "talk-cards")
        maybeEnded()
    }

    private fun apply(e: TalkEvent) {
        when (e) {
            is TalkEvent.Text -> { stopTone(); phase = Phase.WRITING; liveText += e.delta }
            is TalkEvent.Say -> Unit
            is TalkEvent.Audio -> { stopTone(); order.offer(e.audio.seq, e.audio); order.drain().forEach(::play); gap() }
            is TalkEvent.CardOffered -> if (liveCards.none { it.idText == e.card.idText }) liveCards.add(e.card)
            is TalkEvent.Invite -> scope.launch { reload() }
            is TalkEvent.Meter -> mergeMeter(e.raw)
            is TalkEvent.Tool -> if (e.running) startTone() else stopTone()
            TalkEvent.Done -> Unit
            is TalkEvent.Error -> { stopTone(); liveFailed = e.reasonFa; if (phase == Phase.THINKING) phase = Phase.IDLE }
        }
    }

    private var gapJob: Job? = null

    /** A sentence that is missing (the hub spoke the next one only in text) is stepped over after a short wait. */
    private fun gap() {
        gapJob?.cancel()
        if (order.pending == 0) return
        gapJob = scope.launch { delay(GAP_MS); order.skip().forEach(::play) }
    }

    // ------------------------------------------------------------- the stream --
    private fun events(id: String, path: String?): Flow<TalkEvent> = callbackFlow {
        val url = env.api.url(path?.takeIf { it.startsWith("/") }?.removePrefix("/api/v1") ?: "/talk/turns/${java.net.URLEncoder.encode(id, "UTF-8")}/events")
        val req = Request.Builder().url(url).header("Accept", "text/event-stream").build()
        val src = EventSources.createFactory(env.api.streamClient).newEventSource(req, object : EventSourceListener() {
            override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                val e = parseTalkEvent(type, data) ?: return
                trySend(e)
                if (e == TalkEvent.Done || e is TalkEvent.Error) close()
            }

            override fun onClosed(eventSource: EventSource) { close() }

            override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                response?.close()
                close()
            }
        })
        awaitClose { src.cancel() }
    }

    /** The demo's answer: the stored persona turn of the conversation, played back in pieces (no sound, no network stream). */
    private fun demoEvents(id: String): Flow<TalkEvent> = kotlinx.coroutines.flow.flow {
        val ref = conv?.ref ?: return@flow
        delay(500)
        val answer = runCatching { env.api.talkConversation(ref).turns.lastOrNull { !it.owner } }.getOrNull() ?: return@flow
        val text = answer.showMd ?: answer.text
        var i = 0
        while (i < text.length) {
            val j = minOf(text.length, i + 9)
            emit(TalkEvent.Text(text.substring(i, j)))
            i = j
            delay(45)
        }
        answer.audio.forEach { emit(TalkEvent.Audio(it)); delay(80) }
        answer.cards.forEach { emit(TalkEvent.CardOffered(it)) }
        emit(TalkEvent.Meter(null, kotlinx.serialization.json.JsonObject(emptyMap())))
        emit(TalkEvent.Done)
    }

    private fun mergeMeter(raw: kotlinx.serialization.json.JsonObject) {
        val m = runCatching { Api.json.decodeFromJsonElement(VoiceMeter.serializer(), raw) }.getOrNull() ?: return
        if (raw.isEmpty() || m.period == "today") return
        meterLive = m
    }

    /** The stream says an engine's light changed (`voice.engine`). */
    fun engineLight(engine: String, state: String, reason: String?) { lightsLive = lightsLive + (engine to (state to reason)) }
    fun meterFromStream(m: VoiceMeter) { if (m.period != "today") meterLive = m }

    // --------------------------------------------------------------- sound --
    private fun ensurePlayer(): ExoPlayer = player ?: ExoPlayer.Builder(env.media.context).setMediaSourceFactory(DefaultMediaSourceFactory(env.media.dataSource)).build().also { p ->
        p.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(playbackState: Int) {
                if (playbackState == Player.STATE_ENDED) { speaking = false; maybeEnded() }
            }

            override fun onIsPlayingChanged(isPlaying: Boolean) { if (isPlaying) speaking = true }
        })
        player = p
    }

    /** One sentence's audio joins the queue and plays after those before it. */
    fun play(a: TalkAudio) {
        queued++
        if (env.demo) {
            speaking = true
            val before = demoPlayJob
            demoPlayJob = scope.launch {
                before?.join()
                delay((a.seconds * 1000).toLong().coerceIn(200, 1_500))
                if (--queued <= 0) { speaking = false; maybeEnded() }
            }
            return
        }
        val p = ensurePlayer()
        val index = p.mediaItemCount
        p.addMediaItem(MediaItem.fromUri(env.media.url(a.fileId)))
        if (p.playbackState == Player.STATE_IDLE) p.prepare() else if (p.playbackState == Player.STATE_ENDED) p.seekTo(index, 0)
        p.playWhenReady = true
        speaking = true
    }

    /** Plays one file on its own (a voice's sample, an earlier answer), after stopping what plays. */
    fun playFile(fileId: String, seconds: Double = 0.0) {
        stopSound()
        play(TalkAudio(0, fileId, seconds))
    }

    private fun maybeEnded() {
        if (streamDone && !speaking && phase == Phase.IDLE && order.pending == 0) onAnswerEnded?.invoke()
    }

    private fun startTone() {
        if (env.demo || toneJob != null) return
        toneJob = scope.launch {
            delay(TOOL_QUIET_MS)
            val t = runCatching { ToneGenerator(AudioManager.STREAM_MUSIC, 14) }.getOrNull() ?: return@launch
            tone = t
            while (isActive) {
                runCatching { t.startTone(ToneGenerator.TONE_SUP_PIP, 70) }
                delay(1_400)
            }
        }
    }

    private fun stopTone() {
        toneJob?.cancel(); toneJob = null
        tone?.let { runCatching { it.release() } }; tone = null
    }

    private fun stopSound() {
        gapJob?.cancel(); demoPlayJob?.cancel(); demoPlayJob = null
        player?.let { runCatching { it.stop(); it.clearMediaItems() } }
        order.reset(); queued = 0
        speaking = false
    }

    // ------------------------------------------------------------ barge-in --
    /**
     * The owner speaks over the answer: playback stops at once, `POST /talk/turns/{id}/stop` ends generation (the sentences not yet
     * spoken are never made, so never billed), and what was written so far stays as the answer.
     */
    fun bargeIn() {
        val id = answerId
        val wasAnswering = phase != Phase.IDLE || speaking
        streamJob?.cancel(); watchdog?.cancel()
        stopSound(); stopTone()
        phase = Phase.IDLE
        streamDone = true
        if (wasAnswering && id != null && !env.demo) scope.launch { runCatching { env.api.stopTalkTurn(id) } }
        if (wasAnswering) scope.launch { reload(); liveText = ""; liveCards.clear() }
    }

    /** Leaves the screen: the stream, the sound and the player end. */
    fun stopAll() {
        streamJob?.cancel(); watchdog?.cancel()
        stopSound(); stopTone()
        phase = Phase.IDLE
        streamDone = true
        liveText = ""; liveCards.clear()
    }

    fun release() {
        stopAll()
        player?.release(); player = null
    }

    private companion object {
        const val NO_NEWS_MS = 90_000L
        const val GAP_MS = 2_500L
        const val TOOL_QUIET_MS = 1_200L
    }
}
