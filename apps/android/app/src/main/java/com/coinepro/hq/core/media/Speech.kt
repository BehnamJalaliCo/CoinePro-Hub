package com.coinepro.hq.core.media

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer

/**
 * The phone's own speech recognition in Persian (`fa-IR`), first for every live dictation in the app (⟨1.9⟩ §27.3: the hub's
 * speech to text hears when this cannot): partial text while the owner speaks, the loudness for the waveform, and the final text. It runs on the main thread (as
 * [SpeechRecognizer] requires) and owns the microphone while it listens, so no recording runs beside it.
 */
class PhoneSpeech(private val context: Context) {
    interface Listener {
        /** Loudness 0..1. */
        fun level(v: Float)
        fun partial(text: String)
        /** The owner stopped speaking; the phone is turning it into text. */
        fun recognising()
        fun result(text: String)
        /** A Persian sentence the owner can act on, whether typing is the way forward (the phone cannot do Persian at all), and the
         *  recogniser's error code (`SpeechRecognizer.ERROR_*`; `ERROR_NO_MATCH` when it answered with no words) for the hub's fallback. */
        fun failed(messageFa: String, unavailable: Boolean, code: Int)
    }

    private var rec: SpeechRecognizer? = null

    val listening: Boolean get() = rec != null

    /** False when the phone has no recogniser at all (no Google app, no speech service). */
    fun start(l: Listener): Boolean {
        cancel()
        val r = create() ?: return false
        rec = r
        r.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) = Unit
            override fun onBeginningOfSpeech() = Unit
            override fun onRmsChanged(rmsdB: Float) = l.level(((rmsdB + 2f) / 12f).coerceIn(0f, 1f))
            override fun onBufferReceived(buffer: ByteArray?) = Unit
            override fun onEndOfSpeech() = l.recognising()
            override fun onPartialResults(partialResults: Bundle?) {
                best(partialResults)?.let(l::partial)
            }
            override fun onEvent(eventType: Int, params: Bundle?) = Unit
            override fun onResults(results: Bundle?) {
                release()
                val text = best(results)
                if (text.isNullOrBlank()) l.failed("حرفی شنیده نشد؛ دوباره بگو.", unavailable = false, code = SpeechRecognizer.ERROR_NO_MATCH) else l.result(text)
            }
            override fun onError(error: Int) {
                release()
                val (fa, unavailable) = messageOf(error)
                // «خطاخوان»: the recogniser's error code; "nothing heard" is ordinary, the rest are worth a look.
                val quiet = error == SpeechRecognizer.ERROR_NO_MATCH || error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT
                com.coinepro.hq.core.diag.Diag.note(
                    "speech", if (quiet) com.coinepro.hq.core.diag.LEVEL_INFO else com.coinepro.hq.core.diag.LEVEL_WARNING,
                    if (quiet) "nothing heard" else "recogniser error", "SpeechRecognizer error $error ($LANGUAGE)", "speech_$error",
                )
                l.failed(fa, unavailable, error)
            }
        })
        return runCatching { r.startListening(intent()); true }.getOrElse { release(); false }
    }

    /** The owner is done: the phone finishes the text it heard. */
    fun stop() { runCatching { rec?.stopListening() } }

    fun cancel() {
        runCatching { rec?.cancel() }
        release()
    }

    private fun release() {
        val r = rec ?: return
        rec = null
        runCatching { r.destroy() }
    }

    private fun create(): SpeechRecognizer? = runCatching {
        when {
            SpeechRecognizer.isRecognitionAvailable(context) -> SpeechRecognizer.createSpeechRecognizer(context)
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && SpeechRecognizer.isOnDeviceRecognitionAvailable(context) ->
                SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
            else -> null
        }
    }.getOrNull()

    private fun intent() = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        putExtra(RecognizerIntent.EXTRA_LANGUAGE, LANGUAGE)
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, LANGUAGE)
        putExtra(RecognizerIntent.EXTRA_ONLY_RETURN_LANGUAGE_PREFERENCE, true)
        putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
        putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        // An order is said in one breath with pauses: let a short pause pass before the phone decides the owner is done.
        putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 2_500L)
        putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 2_000L)
        putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, context.packageName)
    }

    private fun best(b: Bundle?): String? = b?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim()?.takeIf { it.isNotEmpty() }

    companion object {
        const val LANGUAGE = "fa-IR"

        /** Whether the phone has any speech recogniser (the manifest's `<queries>` makes the service visible on Android 11+). */
        fun available(context: Context): Boolean = runCatching {
            SpeechRecognizer.isRecognitionAvailable(context) ||
                (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && SpeechRecognizer.isOnDeviceRecognitionAvailable(context))
        }.getOrDefault(false)

        /** The recogniser's error as a plain Persian sentence; true when the phone cannot do Persian at all (type instead). */
        fun messageOf(error: Int): Pair<String, Boolean> = when (error) {
            SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "حرفی شنیده نشد؛ دوباره بگو." to false
            SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT, SpeechRecognizer.ERROR_SERVER, ERROR_SERVER_DISCONNECTED ->
                "تشخیص گفتار گوشی به اینترنت نرسید؛ دوباره بگو یا بنویس." to false
            SpeechRecognizer.ERROR_AUDIO -> "میکروفون در دسترس نیست؛ شاید برنامه‌ی دیگری از آن استفاده میکند." to false
            SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "اجازه‌ی میکروفون داده نشده؛ از تنظیمات گوشی برای این اپ روشنش کن." to false
            SpeechRecognizer.ERROR_RECOGNIZER_BUSY, ERROR_TOO_MANY_REQUESTS -> "تشخیص گفتار گوشی مشغول است؛ چند لحظه بعد دوباره بزن." to false
            ERROR_LANGUAGE_NOT_SUPPORTED, ERROR_LANGUAGE_UNAVAILABLE ->
                "تشخیص گفتار این گوشی فارسی ندارد. زبان فارسی را در «گفتار» تنظیمات Google اضافه کن، یا بنویس." to true
            else -> "تشخیص گفتار گوشی کار نکرد؛ دوباره بگو یا بنویس." to false
        }

        // Added in API 31 (S); the constants are compiled in, so they are named here for older SDK levels too.
        private const val ERROR_TOO_MANY_REQUESTS = 10
        private const val ERROR_SERVER_DISCONNECTED = 11
        private const val ERROR_LANGUAGE_NOT_SUPPORTED = 12
        private const val ERROR_LANGUAGE_UNAVAILABLE = 13
    }
}
