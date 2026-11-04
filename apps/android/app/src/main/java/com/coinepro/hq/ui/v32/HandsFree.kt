package com.coinepro.hq.ui.v32

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import com.coinepro.hq.core.Env
import com.coinepro.hq.core.data.HandsFree
import com.coinepro.hq.core.data.HandsFreeEvent
import com.coinepro.hq.core.data.SOURCE_HANDSFREE
import com.coinepro.hq.core.data.TALK_SILENCE_MS
import com.coinepro.hq.core.data.handsFreeNext
import com.coinepro.hq.core.media.PhoneSpeech
import com.coinepro.hq.core.media.VoiceRecorder
import com.coinepro.hq.core.media.hubUsable
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Toasts
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Contract §32.7 hands-free: the owner taps once and talks; a turn ends after [TALK_SILENCE_MS] of silence, goes to [session], and
 * listening resumes after the answer. The microphone stays open while the answer plays, so the owner can speak over it (barge-in):
 * playback stops, the answer ends, and what he says is the next turn.
 *
 * The phone's recogniser (fa-IR) hears first. A phone without Persian listens through a recording instead, whose loudness decides when
 * the owner started and stopped, and the hub (`/transcribe`, purpose `talk`) turns the recording into words.
 */
@Stable
class HandsFreeTalk(private val env: Env, private val scope: CoroutineScope, private val toasts: Toasts, private val session: TalkSession, private val keys: () -> List<String>, private val onKey: (String) -> Unit) {
    var state by mutableStateOf(HandsFree.OFF)
        private set
    /** The words so far of what the owner is saying. */
    var partial by mutableStateOf("")
        private set
    var level by mutableFloatStateOf(0f)
        private set
    val levels = mutableStateListOf<Float>().apply { repeat(32) { add(0f) } }

    private val speech = PhoneSpeech(env.media.context)
    private var rec: VoiceRecorder? = null
    private var ticker: Job? = null
    private var lastVoice = 0L
    private var heard = false
    private var failures = 0
    private var hubMode = false
    private var loud = 0
    private val hubOk: Boolean get() = hubUsable(env.media.speechEnabled, env.media.hubSpeech)

    val on: Boolean get() = state != HandsFree.OFF

    private fun go(e: HandsFreeEvent) { state = handsFreeNext(state, e) }

    fun start() {
        if (on) return
        failures = 0
        go(HandsFreeEvent.TOGGLE_ON)
        session.onAnswerEnded = {
            go(HandsFreeEvent.ANSWER_ENDED)
            partial = ""
        }
        listen()
        tick()
    }

    fun stop() {
        go(HandsFreeEvent.TOGGLE_OFF)
        session.onAnswerEnded = null
        ticker?.cancel(); ticker = null
        speech.cancel()
        rec?.cancel(); rec = null
        partial = ""; level = 0f; heard = false
    }

    // --------------------------------------------------------------- phone --
    private fun listen() {
        heard = false
        val media = env.media
        val phoneOk = PhoneSpeech.available(media.context) && media.phoneSpeech != false
        hubMode = !phoneOk
        if (hubMode) {
            if (!hubOk) { toasts.info("دست‌آزاد روی این گوشی فارسی ندارد و تبدیل صدا روی هاب هم خاموش است؛ دکمه را نگه دار."); stop(); return }
            listenHub()
            return
        }
        val ok = speech.start(object : PhoneSpeech.Listener {
            override fun level(v: Float) { this@HandsFreeTalk.level = v; if (v > VOICE_LEVEL) lastVoice = now() }
            override fun partial(text: String) {
                partial = text
                lastVoice = now()
                if (text.isNotBlank()) voiceStarted()
            }
            override fun recognising() = Unit
            override fun result(text: String) { failures = 0; utterance(text) }
            override fun failed(messageFa: String, unavailable: Boolean, code: Int) {
                if (unavailable) env.media.phoneSpeech = false
                if (code == android.speech.SpeechRecognizer.ERROR_NO_MATCH || code == android.speech.SpeechRecognizer.ERROR_SPEECH_TIMEOUT) { relisten(); return }
                // Words heard before it gave up are what the owner said.
                if (partial.isNotBlank() && state == HandsFree.HEARING) { utterance(partial); return }
                if (++failures >= 3) { toasts.info(messageFa); stop() } else relisten()
            }
        }, silenceMs = TALK_SILENCE_MS)
        if (!ok) { toasts.info("تشخیص گفتار گوشی در دسترس نیست؛ دکمه را نگه دار یا بنویس."); stop() }
    }

    private fun relisten() {
        if (!on) return
        scope.launch { delay(150); if (on && !speech.listening && !hubMode) listen() }
    }

    /** The owner began to speak: in the quiet this starts a turn; over the answer it is a barge-in. */
    private fun voiceStarted() {
        when (state) {
            HandsFree.LISTENING -> { heard = true; go(HandsFreeEvent.SPEECH_STARTED) }
            HandsFree.ANSWERING -> { heard = true; session.bargeIn(); go(HandsFreeEvent.BARGE_IN) }
            else -> Unit
        }
    }

    private fun utterance(text: String) {
        val said = text.trim()
        partial = ""
        if (said.isBlank()) { relisten(); return }
        // The recogniser may end a phrase before the loop saw it begin (a short word).
        if (state == HandsFree.LISTENING) go(HandsFreeEvent.SPEECH_STARTED)
        if (state == HandsFree.ANSWERING) { session.bargeIn(); go(HandsFreeEvent.BARGE_IN) }
        // A key spoken or pasted never goes as a turn: the secure sheet opens with it.
        com.coinepro.hq.core.data.extractKey(said, keys())?.let { k -> onKey(k); go(HandsFreeEvent.SILENCE); go(HandsFreeEvent.SEND_FAILED); relisten(); return }
        go(HandsFreeEvent.SILENCE)
        scope.launch {
            val sent = session.send(said, SOURCE_HANDSFREE)
            if (!on) return@launch
            go(if (sent) HandsFreeEvent.SENT_OK else HandsFreeEvent.SEND_FAILED)
            // The answer plays while the microphone listens again, for a barge-in.
            if (!hubMode) relisten()
            else if (rec == null) listenHub()
        }
    }

    // ----------------------------------------------------------------- hub --
    private val dir: File get() = env.media.scratch("handsfree")

    private fun listenHub() {
        rec?.cancel()
        val r = VoiceRecorder(env.media.context, dir)
        if (!r.start()) { toasts.info("میکروفون در دسترس نیست؛ شاید برنامه‌ی دیگری از آن استفاده میکند."); stop(); return }
        rec = r
        lastVoice = now(); heard = false; loud = 0
    }

    /** The hub path: loudness says when the owner began and when the silence is long enough; the recording is then turned into words. */
    private fun hubStep() {
        val r = rec ?: return
        val l = r.level()
        level = l
        val t = now()
        if (l > HUB_LEVEL) { lastVoice = t; loud++ } else loud = 0
        if (!heard && loud >= 3) {
            heard = true
            if (state == HandsFree.ANSWERING) { session.bargeIn(); go(HandsFreeEvent.BARGE_IN) } else if (state == HandsFree.LISTENING) go(HandsFreeEvent.SPEECH_STARTED)
        }
        if (heard && t - lastVoice >= TALK_SILENCE_MS && state == HandsFree.HEARING) {
            rec = null
            val out = r.stop()
            heard = false
            if (out == null) { listenHub(); return }
            val (file, seconds) = out
            if (seconds < 0.6) { file.delete(); go(HandsFreeEvent.SEND_FAILED); listenHub(); return }
            scope.launch {
                val text = try {
                    withContext(Dispatchers.IO) { env.api.transcribe(file, "audio/mp4", "talk") }.text.also { env.media.hubSpeech = true }
                } catch (e: ApiException) {
                    if (e.status == 503 || e.code == "channel_not_configured") env.media.hubSpeech = false
                    toasts.info(if (e.isOffline) "به هاب نرسیدم؛ صدا به متن نشد." else e.messageFa)
                    ""
                } finally { file.delete() }
                if (!on) return@launch
                if (text.isBlank()) { go(HandsFreeEvent.SEND_FAILED); listenHub() } else utterance(text)
            }
        } else if (!heard && t - lastVoice > 30_000) {
            // A long quiet: a fresh, small recording.
            r.cancel(); rec = null; listenHub()
        }
    }

    // --------------------------------------------------------------- ticker --
    private fun tick() {
        ticker = scope.launch {
            while (isActive && on) {
                delay(100)
                if (hubMode) hubStep()
                // The phone ends a turn after the silence it was asked for; the app makes sure it does.
                else if (state == HandsFree.HEARING && partial.isNotBlank() && now() - lastVoice >= TALK_SILENCE_MS + 300) speech.stop()
                levels.removeAt(0); levels.add(level)
                level *= 0.85f
            }
        }
    }

    private fun now(): Long = android.os.SystemClock.elapsedRealtime()

    private companion object {
        const val VOICE_LEVEL = 0.35f
        const val HUB_LEVEL = 0.22f
    }
}

/** The microphone permission, asked on its own for a button held (the permission dialog would swallow the press). */
@Stable
class MicPermission(val granted: () -> Boolean, val ask: () -> Unit)

@Composable
fun rememberMicPermission(onGranted: () -> Unit = {}): MicPermission {
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (ok) onGranted() }
    return remember(context, launcher) {
        MicPermission({ ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED }, { launcher.launch(Manifest.permission.RECORD_AUDIO) })
    }
}

@Composable
fun rememberHandsFree(session: TalkSession, keys: () -> List<String>, onKey: (String) -> Unit): HandsFreeTalk {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val scope = rememberCoroutineScope()
    val h = remember(env, session) { HandsFreeTalk(env, scope, toasts, session, keys, onKey) }
    DisposableEffect(h) { onDispose { h.stop() } }
    return h
}
