package com.coinepro.hq.core.media

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import android.os.SystemClock
import java.io.File
import kotlin.math.sqrt

/**
 * The owner's voice on the phone: AAC in MP4, mono, 16 kHz, 32 kb/s — small, and what the hub's Whisper reads
 * well (contract §17.2). One recording at a time; the file lives in the cache until it is sent.
 */
class VoiceRecorder(private val context: Context, private val dir: File) {
    private var rec: MediaRecorder? = null
    private var file: File? = null
    private var t0 = 0L
    private var eased = 0f

    val recording: Boolean get() = rec != null
    val seconds: Double get() = if (rec == null) 0.0 else (SystemClock.elapsedRealtime() - t0) / 1000.0

    /** False when the microphone is busy or missing. */
    fun start(): Boolean {
        cancel()
        val out = File(dir, "voice-${System.currentTimeMillis()}.m4a")
        @Suppress("DEPRECATION")
        val r = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) MediaRecorder(context) else MediaRecorder()
        return try {
            r.setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
            r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            r.setAudioChannels(1)
            r.setAudioSamplingRate(16_000)
            r.setAudioEncodingBitRate(32_000)
            r.setOutputFile(out.absolutePath)
            r.prepare()
            r.start()
            rec = r
            file = out
            t0 = SystemClock.elapsedRealtime()
            eased = 0f
            true
        } catch (_: Exception) {
            r.release()
            out.delete()
            false
        }
    }

    /** Loudness 0..1 since the last call, eased so the bars breathe instead of flicker. */
    fun level(): Float {
        val r = rec ?: return 0f
        val raw = runCatching { r.maxAmplitude }.getOrDefault(0) / 32_767f
        eased = maxOf(sqrt(raw.coerceIn(0f, 1f)), eased * 0.8f)
        return eased
    }

    /** The finished recording and its length, or null when nothing usable was recorded. */
    fun stop(): Pair<File, Double>? {
        val r = rec ?: return null
        val f = file
        val s = seconds
        rec = null
        file = null
        val ok = runCatching { r.stop() }.isSuccess
        r.release()
        if (!ok || f == null || !f.exists() || f.length() == 0L) {
            f?.delete()
            return null
        }
        return f to s
    }

    fun cancel() {
        val r = rec ?: return
        rec = null
        runCatching { r.stop() }
        r.release()
        file?.delete()
        file = null
    }
}
