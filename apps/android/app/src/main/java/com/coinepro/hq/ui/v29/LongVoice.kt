package com.coinepro.hq.ui.v29

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import com.coinepro.hq.core.Env
import com.coinepro.hq.core.data.LongVoiceRules
import com.coinepro.hq.core.media.HUB_TAKES_OVER
import com.coinepro.hq.core.media.PhoneSpeech
import com.coinepro.hq.core.media.SpeechEngine
import com.coinepro.hq.core.media.VoiceRecorder
import com.coinepro.hq.core.media.firstEngine
import com.coinepro.hq.core.media.hubUsable
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.media.VoiceResult
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Contract §29.5 ⟨1.11⟩: long voice. The owner speaks as long as he wants and stops when he is done.
 *
 * - **On the phone:** the phone's recogniser (fa-IR) listens, and at every pause (its end of speech, or "nothing more heard") it starts
 *   again at once; each piece joins the text, which grows on screen ([partial]) until the owner presses «تمام».
 * - **Over one minute, or when the recogniser fails:** the microphone goes to a recording (AAC in MP4) cut every [LongVoiceRules.CHUNK_S]
 *   seconds (≤ 90 s); each chunk is uploaded in order to `/transcribe/sessions/{id}/chunks/{n}` while the owner keeps speaking, up to
 *   20 minutes; «تمام» sends the last chunk and `finish` returns the whole text, joined to what the phone heard before. [sent] and
 *   [chunks] show the progress.
 * - A hub before ⟨1.11⟩ (no sessions) takes the recording whole on `/transcribe`.
 *
 * The text comes back through [onText] to be read and edited before anything is sent. The same surface as the short voice input, so
 * the voice order's sheet uses either.
 */
@Stable
class LongVoice(
    private val env: Env,
    private val scope: CoroutineScope,
    private val toasts: Toasts,
    private val purpose: String,
    private val onText: () -> (VoiceResult) -> Unit,
) {
    private val speech = PhoneSpeech(env.media.context)
    private val dir: File = env.media.scratch("long-voice")
    private var rec: VoiceRecorder? = null

    /** The microphone is open (the phone's recogniser between its restarts, or the recording for the hub). */
    var recording by mutableStateOf(false)
        private set
    /** The owner pressed «تمام»: the last words or the last chunk are on their way. */
    var transcribing by mutableStateOf(false)
        private set
    /** Everything heard so far, growing while the owner speaks. */
    var partial by mutableStateOf("")
        private set
    /** `phone` · `hub` while it runs. */
    var engine by mutableStateOf<String?>(null)
        private set
    var unavailable by mutableStateOf<String?>(null)
        private set
    var settings by mutableStateOf(false)
        private set
    var elapsed by mutableDoubleStateOf(0.0)
        private set
    /** The recording went to the hub (over a minute, or the recogniser failed): the sentence that says why. */
    var fellBack by mutableStateOf<String?>(null)
        private set
    /** Chunks made and chunks the hub has. */
    var chunks by mutableIntStateOf(0)
        private set
    var sent by mutableIntStateOf(0)
        private set
    val levels = mutableStateListOf<Float>().apply { repeat(32) { add(0f) } }
    val active: Boolean get() = recording || transcribing

    private var committed = ""
    private var stopping = false
    private var t0 = 0L
    private var chunkT0 = 0L
    private var level = 0f
    private var ticker: Job? = null
    private var session: String? = null
    private var legacy = false
    private var uploads: Job? = null
    private var failedUpload: ApiException? = null

    private val hubOk: Boolean get() = hubUsable(env.media.speechEnabled, env.media.hubSpeech)

    internal fun begin() {
        cancel()
        unavailable = null; settings = false; fellBack = null; committed = ""; partial = ""; stopping = false
        chunks = 0; sent = 0; session = null; legacy = false; failedUpload = null
        t0 = android.os.SystemClock.elapsedRealtime()
        val media = env.media
        when (firstEngine(PhoneSpeech.available(media.context), media.phoneSpeech, media.speechEnabled, media.hubSpeech)) {
            SpeechEngine.PHONE -> { engine = "phone"; recording = true; tick(); listen() }
            SpeechEngine.HUB -> toHub(null)
            SpeechEngine.NONE -> unavailable = NOTHING_HEARS
        }
    }

    internal fun refused() {
        unavailable = "اجازه‌ی میکروفون داده نشده؛ از تنظیمات گوشی برای این اپ روشنش کن، یا بنویس."
        settings = true
    }

    // ---------------------------------------------------------------- phone --
    private fun listen() {
        val ok = speech.start(object : PhoneSpeech.Listener {
            override fun level(v: Float) { this@LongVoice.level = v }
            override fun partial(text: String) { this@LongVoice.partial = LongVoiceRules.join(committed, text) }
            // A pause: the piece is being finished; listening starts again with its result.
            override fun recognising() = Unit
            override fun result(text: String) {
                committed = LongVoiceRules.join(committed, text)
                this@LongVoice.partial = committed
                next()
            }
            override fun failed(messageFa: String, unavailable: Boolean, code: Int) {
                if (LongVoiceRules.restartAfter(code)) { next(); return }
                if (unavailable) env.media.phoneSpeech = false
                when {
                    stopping -> done()
                    hubOk -> toHub(com.coinepro.hq.core.media.HUB_TAKES_OVER)
                    committed.isNotBlank() -> { toasts.info(messageFa); done() }
                    else -> { stopTicker(); recording = false; engine = null; this@LongVoice.unavailable = messageFa }
                }
            }
        })
        if (!ok) {
            if (hubOk) toHub(HUB_TAKES_OVER) else if (committed.isNotBlank()) done() else { stopTicker(); recording = false; engine = null; unavailable = NOTHING_HEARS }
        }
    }

    /** After a piece: done if the owner stopped; to the hub after a minute; else listen again (a breath later, off the callback). */
    private fun next() {
        when {
            stopping -> done()
            elapsed >= LongVoiceRules.PHONE_LIMIT_S && hubOk && env.api.gaps.has(HubFeature.STT_SESSIONS) ->
                toHub("بیش از یک دقیقه شد؛ از این‌جا صدا ضبط میشود و هاب آن را به متن میکند. ادامه بده.")
            else -> scope.launch { delay(120); if (recording && engine == "phone" && !stopping) listen() }
        }
    }

    /** The phone's text is the result. */
    private fun done() {
        stopTicker()
        speech.cancel()
        recording = false; transcribing = false; engine = null
        val text = committed.trim()
        val seconds = (android.os.SystemClock.elapsedRealtime() - t0) / 1000.0
        reset()
        if (text.isBlank()) toasts.info("حرفی شنیده نشد؛ دوباره بگو.")
        else onText()(VoiceResult(text, null, seconds, "phone"))
    }

    // ------------------------------------------------------------------ hub --
    private fun toHub(why: String?) {
        speech.cancel()
        fellBack = why
        engine = "hub"
        recording = true
        if (ticker == null) tick()
        scope.launch {
            if (session == null && !legacy) {
                session = try {
                    env.api.gated(HubFeature.STT_SESSIONS) { sttStart(purpose) }?.id
                } catch (_: ApiException) {
                    null
                }
                if (session == null) legacy = true
            }
            if (!startChunk()) {
                stopTicker(); recording = false; engine = null
                if (committed.isNotBlank()) done() else unavailable = "میکروفون در دسترس نیست؛ شاید برنامه‌ی دیگری از آن استفاده میکند. میتوانی بنویسی."
            }
        }
    }

    private fun startChunk(): Boolean {
        val r = VoiceRecorder(env.media.context, dir)
        if (!r.start()) return false
        rec = r
        chunkT0 = android.os.SystemClock.elapsedRealtime()
        return true
    }

    /** The chunk so far is closed and queued for the hub (in order); a new one starts at once. */
    private fun cut(last: Boolean) {
        val r = rec ?: return
        rec = null
        val out = r.stop()
        if (!last && !legacy) startChunk()
        if (out == null) return
        val (file, _) = out
        if (legacy) { legacyFile = file; return }
        val id = session ?: return
        val n = chunks++
        val before = uploads
        uploads = scope.launch {
            before?.join()
            var tries = 0
            while (true) {
                try {
                    withContext(Dispatchers.IO) { env.api.sttChunk(id, n, file) }
                    sent++
                    file.delete()
                    break
                } catch (e: ApiException) {
                    // Idempotent per n: a chunk that failed is sent again a little later; three failures stop the session.
                    if (++tries >= 3 || !e.transient) { failedUpload = e; break }
                    delay(1_500L * tries)
                }
            }
        }
    }

    private var legacyFile: File? = null

    fun finish() {
        if (engine == "phone") {
            stopping = true
            // Between two pieces the recogniser is not listening: what was heard is the text.
            if (!speech.listening) done() else { transcribing = true; speech.stop() }
            return
        }
        if (engine != "hub") return
        stopTicker()
        recording = false
        transcribing = true
        cut(last = true)
        val id = session
        scope.launch {
            try {
                val words = if (legacy) {
                    val f = legacyFile ?: run { transcribing = false; engine = null; toasts.info("صدایی ضبط نشد؛ دوباره بگو."); return@launch }
                    legacyFile = null
                    // The hub before ⟨1.11⟩ knows message, order and note: a rule is said like an order.
                    withContext(Dispatchers.IO) { env.api.transcribe(f, "audio/mp4", if (purpose == "rule") "order" else purpose) }.text.also { f.delete() }
                } else {
                    uploads?.join()
                    failedUpload?.let { throw it }
                    withContext(Dispatchers.IO) { env.api.sttFinish(id!!) }.text
                }
                env.media.hubSpeech = true
                val text = LongVoiceRules.join(committed, words)
                val seconds = (android.os.SystemClock.elapsedRealtime() - t0) / 1000.0
                if (text.isBlank()) toasts.info("حرفی شنیده نشد؛ دوباره بگو.")
                else onText()(VoiceResult(text, null, seconds, "hub"))
            } catch (e: ApiException) {
                if (e.status == 503 || e.code == "channel_not_configured") env.media.hubSpeech = false
                if (committed.isNotBlank()) {
                    toasts.info("هاب صدای آخر را به متن نکرد؛ آنچه گوشی شنید آمد. بقیه را بنویس یا دوباره بگو.")
                    onText()(VoiceResult(committed.trim(), null, (android.os.SystemClock.elapsedRealtime() - t0) / 1000.0, "phone"))
                } else unavailable = if (e.isOffline) "به هاب نرسیدم؛ صدا به متن نشد. میتوانی بنویسی." else e.messageFa
            } finally {
                transcribing = false
                engine = null
                session = null
                reset()
            }
        }
    }

    fun cancel() {
        stopTicker()
        speech.cancel()
        rec?.cancel(); rec = null
        uploads?.cancel(); uploads = null
        legacyFile?.delete(); legacyFile = null
        dir.listFiles()?.forEach { it.delete() }
        recording = false; transcribing = false; engine = null; partial = ""; fellBack = null
        reset()
    }

    /** Typing instead: the sentence is gone. */
    fun dismiss() { unavailable = null; settings = false }

    // --------------------------------------------------------------- ticker --
    private fun tick() {
        ticker = scope.launch {
            while (isActive && recording) {
                delay(90)
                val now = android.os.SystemClock.elapsedRealtime()
                elapsed = (now - t0) / 1000.0
                val r = rec
                val l = if (engine == "hub" && r != null) r.level() else level
                levels.removeAt(0); levels.add(l)
                level *= 0.85f
                if (engine == "hub" && r != null) {
                    if (elapsed >= (if (legacy) com.coinepro.hq.core.media.Limits.VOICE_SECONDS.toDouble() else LongVoiceRules.MAX_S)) { finish(); break }
                    if (!legacy && (now - chunkT0) / 1000.0 >= LongVoiceRules.CHUNK_S) cut(last = false)
                }
            }
        }
    }

    private fun stopTicker() { ticker?.cancel(); ticker = null }

    private fun reset() {
        elapsed = 0.0; committed = ""; stopping = false
        for (i in levels.indices) levels[i] = 0f
    }

    private companion object {
        const val NOTHING_HEARS = "این گوشی تشخیص گفتار فارسی ندارد و تبدیل صدا روی هاب هم خاموش است؛ فعلاً بنویس."
    }
}

/** A long voice wired to the microphone permission: [start] asks for it when needed, then listens. */
class LongVoiceHandle(val v: LongVoice, val start: () -> Unit)

@Composable
fun rememberLongVoice(purpose: String, onText: (VoiceResult) -> Unit): LongVoiceHandle {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val text by rememberUpdatedState(onText)
    // §27.3: whether the hub may transcribe, from `/meta.speech.enabled`.
    com.coinepro.hq.ui.media.rememberSpeechEnabled()
    val v = remember(env, purpose) { LongVoice(env, scope, toasts, purpose) { text } }
    DisposableEffect(v) { onDispose { v.cancel() } }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (ok) v.begin() else v.refused() }
    return remember(v) {
        LongVoiceHandle(v) {
            if (v.active) return@LongVoiceHandle
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) v.begin()
            else ask.launch(Manifest.permission.RECORD_AUDIO)
        }
    }
}
