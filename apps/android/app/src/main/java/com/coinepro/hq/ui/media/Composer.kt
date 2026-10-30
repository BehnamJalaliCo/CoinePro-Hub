package com.coinepro.hq.ui.media

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import coil3.compose.AsyncImage
import com.coinepro.hq.core.Env
import com.coinepro.hq.core.media.Limits
import com.coinepro.hq.core.media.PhoneSpeech
import com.coinepro.hq.core.media.LocalFile
import com.coinepro.hq.core.media.VoiceRecorder
import com.coinepro.hq.core.media.clock
import com.coinepro.hq.core.media.describe
import com.coinepro.hq.core.media.kindOf
import com.coinepro.hq.core.media.videoSeconds
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.LiveDot
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Toasts
import java.io.File
import java.util.UUID
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// ------------------------------------------------------------ uploads --
@Stable
class Pending(val key: String, val file: LocalFile, val kind: String, val seconds: Double?) {
    var progress by mutableFloatStateOf(0f)
    var state by mutableStateOf("uploading")
    var ref by mutableStateOf<FileRef?>(null)
    var error by mutableStateOf<String?>(null)
    internal var job: Job? = null
}

/** Files the owner is attaching: checked against the contract, uploaded at once with progress, cancellable, retryable. */
@Stable
class Attachments(private val env: Env, private val context: Context, private val scope: CoroutineScope, private val toasts: Toasts, private val max: Int = 10) {
    val items = mutableStateListOf<Pending>()
    val ids: List<String> get() = items.mapNotNull { it.ref?.id }
    val uploading: Boolean get() = items.any { it.state == "uploading" }

    fun add(uris: List<Uri>) {
        scope.launch {
            for (uri in uris) {
                if (items.size >= max) { toasts.error("حداکثر $max پیوست در هر پیام."); return@launch }
                val f = withContext(Dispatchers.IO) { context.contentResolver.describe(uri) }
                Limits.reject(f)?.let { toasts.error(it); continue }
                val kind = kindOf(f.mime)
                val seconds = if (kind == "video") withContext(Dispatchers.IO) { videoSeconds(context, uri) } else null
                if (seconds != null && seconds > Limits.VIDEO_SECONDS) { toasts.error("«${f.name}»: فیلم حداکثر ۱۰ دقیقه است."); continue }
                val p = Pending(UUID.randomUUID().toString(), f, kind, seconds)
                items.add(p)
                upload(p)
            }
        }
    }

    /** A local file (a voice note the speech service could not read) attached as it is. */
    fun addFile(file: File) = add(listOf(Uri.fromFile(file)))

    private fun upload(p: Pending) {
        p.job = scope.launch {
            try {
                val ref = withContext(Dispatchers.IO) {
                    env.api.upload(p.file.name, p.file.mime, p.file.size, { context.contentResolver.openInputStream(p.file.uri) ?: error("unreadable") }) { x ->
                        if (x - p.progress >= 0.01f || x >= 1f) p.progress = x
                    }
                }
                p.ref = ref
                p.progress = 1f
                p.state = "ready"
            } catch (e: ApiException) {
                p.state = "failed"; p.error = e.messageFa
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (_: Exception) {
                p.state = "failed"; p.error = "بارگذاری نشد."
            }
        }
    }

    fun retry(p: Pending) { p.state = "uploading"; p.progress = 0f; p.error = null; upload(p) }
    fun remove(p: Pending) { p.job?.cancel(); items.remove(p) }
    fun clear() { items.forEach { it.job?.cancel() }; items.clear() }
}

@Composable
fun rememberAttachments(max: Int = 10): Attachments {
    val env = LocalEnv.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val toasts = LocalToasts.current
    return remember(env) { Attachments(env, context, scope, toasts, max) }
}

/** The composer's row of files on their way. */
@Composable
fun AttachmentTray(a: Attachments, modifier: Modifier = Modifier) {
    if (a.items.isEmpty()) return
    val media = LocalEnv.current.media
    val c = Divan.colors
    Row(modifier.horizontalScroll(rememberScrollState()).padding(4.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        for (p in a.items) {
            Box(Modifier.padding(top = 6.dp, start = 6.dp)) {
                Box(
                    Modifier.size(64.dp).clip(RoundedCornerShape(12.dp)).background(c.tile)
                        .then(if (p.state == "failed") Modifier.border(1.dp, c.negative.copy(alpha = 0.6f), RoundedCornerShape(12.dp)) else Modifier),
                    contentAlignment = Alignment.Center,
                ) {
                    when (p.kind) {
                        "image", "video" -> AsyncImage(p.file.uri, p.file.name, media.images, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                        else -> DIcon(if (p.kind == "audio") DivanIcon.MIC else DivanIcon.REPORT, tint = c.textSecondary)
                    }
                    if (p.kind == "video") {
                        Box(Modifier.align(Alignment.BottomStart).padding(4.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.6f)).padding(horizontal = 5.dp)) {
                            Fig(p.seconds?.let(::clock) ?: "▶", style = Divan.type.figureSmall, color = Color.White)
                        }
                    }
                    when (p.state) {
                        "uploading" -> Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.45f)), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator(progress = { p.progress }, modifier = Modifier.size(28.dp), color = Color.White, trackColor = Color.White.copy(alpha = 0.28f), strokeWidth = 3.dp)
                        }
                        "failed" -> Box(
                            Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.55f)).clickable(role = Role.Button, onClickLabel = "دوباره بفرست") { a.retry(p) },
                            contentAlignment = Alignment.Center,
                        ) { DIcon(DivanIcon.REFRESH, size = 20.dp, tint = Color.White) }
                    }
                }
                Box(
                    Modifier.align(Alignment.TopStart).offset((-6).dp, (-6).dp).size(24.dp).clip(CircleShape).background(c.raised)
                        .clickable(role = Role.Button, onClickLabel = "حذف ${p.file.name}") { a.remove(p) },
                    contentAlignment = Alignment.Center,
                ) { DIcon(DivanIcon.CLOSE, size = 14.dp, tint = c.textSecondary) }
            }
        }
    }
}

// -------------------------------------------------------------- voice --
/** What came of the owner's voice: the text to read and fix, the original recording when the hub transcribed it ([fileId]; the phone's
 *  own recogniser keeps no audio), how long the owner spoke, and who heard it (`phone` · `hub`). */
data class VoiceResult(val text: String, val fileId: String?, val seconds: Double, val engine: String = "hub") {
    val phone: Boolean get() = engine == "phone"
}

/**
 * Speak → Persian text. The phone's own speech recognition (fa-IR) hears it first, for live dictation: it shows the words as they come
 * and leaves them in the caller's field to read and fix. ⟨1.9⟩ §27.3: the hub's `/transcribe` (its own faster-whisper; the audio never
 * leaves the hub) hears when the phone cannot: the phone has no recogniser or no Persian, or its recogniser failed ([fellBack] says so
 * and the hub records the owner saying it again). It keeps the original recording, and when it cannot help [onFallback] gets the audio
 * file itself. When neither can hear, [unavailable] says so in plain words and the screen offers to type.
 */
@Stable
class VoiceInput(
    private val env: Env,
    private val scope: CoroutineScope,
    private val toasts: Toasts,
    private val purpose: String,
    private val onText: () -> (VoiceResult) -> Unit,
    private val onFallback: () -> ((File) -> Unit)?,
) {
    private val rec = VoiceRecorder(env.media.context, env.media.scratch("voice"))
    private val speech = PhoneSpeech(env.media.context)
    /** Listening: the microphone is open (the phone's recogniser or the recording for the hub). */
    var recording by mutableStateOf(false)
        private set
    /** Recognising: the owner stopped; the words are being made. */
    var transcribing by mutableStateOf(false)
        private set
    /** The phone's words so far, while the owner speaks. */
    var partial by mutableStateOf("")
        private set
    /** `phone` · `hub` while it runs. */
    var engine by mutableStateOf<String?>(null)
        private set
    /** A plain sentence when no voice-to-text can hear now: the screen offers to type. [settings]: the microphone is refused. */
    var unavailable by mutableStateOf<String?>(null)
        private set
    var settings by mutableStateOf(false)
        private set
    var elapsed by mutableDoubleStateOf(0.0)
        private set
    val levels = mutableStateListOf<Float>().apply { repeat(32) { add(0f) } }
    private var ticker: Job? = null
    private var work: Job? = null
    private var t0 = 0L
    private var level = 0f
    val active: Boolean get() = recording || transcribing

    /** ⟨1.9⟩ The phone's recogniser failed and the hub is listening instead: the sentence that says so (cleared on the next start). */
    var fellBack by mutableStateOf<String?>(null)
        private set

    private val hubOk: Boolean get() = com.coinepro.hq.core.media.hubUsable(env.media.speechEnabled, env.media.hubSpeech)

    internal fun begin() {
        unavailable = null; settings = false; partial = ""; fellBack = null
        val media = env.media
        when (com.coinepro.hq.core.media.firstEngine(PhoneSpeech.available(media.context), media.phoneSpeech, media.speechEnabled, media.hubSpeech)) {
            com.coinepro.hq.core.media.SpeechEngine.PHONE -> if (!beginPhone()) { if (hubOk) beginHub() else unavailable = NOTHING_HEARS }
            com.coinepro.hq.core.media.SpeechEngine.HUB -> beginHub()
            com.coinepro.hq.core.media.SpeechEngine.NONE -> unavailable = NOTHING_HEARS
        }
    }

    internal fun refused() {
        unavailable = "اجازه‌ی میکروفون داده نشده؛ از تنظیمات گوشی برای این اپ روشنش کن، یا بنویس."
        settings = true
    }

    private fun beginPhone(): Boolean {
        val ok = speech.start(object : PhoneSpeech.Listener {
            override fun level(v: Float) { level = v }
            override fun partial(text: String) { this@VoiceInput.partial = text }
            override fun recognising() { recording = false; transcribing = true }
            override fun result(text: String) {
                val seconds = (android.os.SystemClock.elapsedRealtime() - t0) / 1000.0
                stopTicker(); transcribing = false; recording = false; engine = null; this@VoiceInput.partial = ""; reset()
                onText()(VoiceResult(text.trim(), null, seconds, "phone"))
            }
            override fun failed(messageFa: String, unavailable: Boolean, code: Int) {
                stopTicker(); transcribing = false; recording = false; engine = null; reset()
                // The phone cannot do Persian: from now on the hub is asked first (where it answers).
                if (unavailable) env.media.phoneSpeech = false
                val words = this@VoiceInput.partial
                when (com.coinepro.hq.core.media.afterPhoneFailure(code, unavailable, words.isNotBlank(), hubOk)) {
                    // The recogniser gave up after words were heard: they are what the owner said; keep them.
                    com.coinepro.hq.core.media.PhoneFallback.KEEP_WORDS -> {
                        this@VoiceInput.partial = ""
                        onText()(VoiceResult(words.trim(), null, (android.os.SystemClock.elapsedRealtime() - t0) / 1000.0, "phone"))
                    }
                    // ⟨1.9⟩ §27.3: the hub hears instead; the owner says it again into the recording.
                    com.coinepro.hq.core.media.PhoneFallback.HUB -> { fellBack = com.coinepro.hq.core.media.HUB_TAKES_OVER; beginHub() }
                    com.coinepro.hq.core.media.PhoneFallback.TYPE -> this@VoiceInput.unavailable = messageFa
                    com.coinepro.hq.core.media.PhoneFallback.TELL -> toasts.info(messageFa)
                }
            }
        })
        if (!ok) return false
        engine = "phone"
        recording = true
        t0 = android.os.SystemClock.elapsedRealtime()
        level = 0f
        ticker = scope.launch {
            while (isActive && (recording || transcribing)) {
                delay(90)
                if (recording) elapsed = (android.os.SystemClock.elapsedRealtime() - t0) / 1000.0
                levels.removeAt(0); levels.add(if (recording) level else 0f)
                level *= 0.85f
            }
        }
        return true
    }

    private fun beginHub() {
        if (!rec.start()) { unavailable = "میکروفون در دسترس نیست؛ شاید برنامه‌ی دیگری از آن استفاده میکند. میتوانی بنویسی."; return }
        engine = "hub"
        recording = true
        ticker = scope.launch {
            while (isActive && rec.recording) {
                delay(90)
                elapsed = rec.seconds
                levels.removeAt(0); levels.add(rec.level())
                if (elapsed >= Limits.VOICE_SECONDS) { finish(); break }
            }
        }
    }

    fun finish() {
        if (engine == "phone") {
            // The phone finishes the words it heard and answers through the listener.
            recording = false; transcribing = true
            speech.stop()
            return
        }
        stopTicker()
        recording = false
        val (file, seconds) = rec.stop() ?: run { engine = null; return toasts.info("صدایی ضبط نشد؛ دکمه را بزن و بعد حرف بزن.") }
        reset()
        if (seconds < 0.6) { file.delete(); engine = null; return toasts.info("صدایی ضبط نشد؛ دکمه را بزن و بعد حرف بزن.") }
        transcribing = true
        work = scope.launch {
            try {
                val t = withContext(Dispatchers.IO) { env.api.transcribe(file, "audio/mp4", purpose) }
                env.media.hubSpeech = true
                if (t.text.isBlank()) toasts.info("حرفی شنیده نشد؛ دوباره بگو.")
                else onText()(VoiceResult(t.text.trim(), t.fileId, if (t.durationS > 0) t.durationS else seconds, "hub"))
            } catch (e: ApiException) {
                // Speech-to-text off on the hub (503), busy (429) or failing: not asked again this session.
                if (e.status == 503 || e.status >= 500 || e.code == "channel_not_configured") env.media.hubSpeech = false
                val fb = onFallback()
                if (fb != null) { fb(file); toasts.info("تبدیل صدا روی هاب در دسترس نیست؛ صدا به‌عنوان پیوست اضافه شد.") }
                else unavailable = if (e.isOffline) "به هاب نرسیدم؛ صدا به متن نشد. میتوانی بنویسی." else NOTHING_HEARS
            } finally {
                transcribing = false
                engine = null
                fellBack = null
            }
        }
    }

    fun cancel() {
        stopTicker(); work?.cancel()
        speech.cancel()
        rec.cancel()
        recording = false; transcribing = false; engine = null; partial = ""; fellBack = null
        reset()
    }

    /** Typing instead: the sentence is gone. */
    fun dismiss() { unavailable = null; settings = false }

    private fun stopTicker() { ticker?.cancel(); ticker = null }

    private fun reset() { elapsed = 0.0; for (i in levels.indices) levels[i] = 0f }

    private companion object {
        const val NOTHING_HEARS = "این گوشی تشخیص گفتار فارسی ندارد و تبدیل صدا روی هاب هم خاموش است؛ فعلاً بنویس."
    }
}

/** A voice input wired to the microphone permission: [start] asks for it when needed, then listens. */
class VoiceHandle(val v: VoiceInput, val start: () -> Unit)

@Composable
fun rememberVoiceInput(purpose: String, onFallback: ((File) -> Unit)? = null, onText: (VoiceResult) -> Unit): VoiceHandle {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val text by rememberUpdatedState(onText)
    val fallback by rememberUpdatedState(onFallback)
    // ⟨1.9⟩ §27.3: whether the hub may transcribe, from `/meta.speech.enabled` (the voice input reads it at each start).
    rememberSpeechEnabled()
    val v = remember(env, purpose) { VoiceInput(env, scope, toasts, purpose, { text }, { fallback }) }
    DisposableEffect(v) { onDispose { v.cancel() } }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (ok) v.begin() else v.refused() }
    return remember(v) {
        VoiceHandle(v) {
            if (v.active) return@VoiceHandle
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) v.begin()
            else ask.launch(Manifest.permission.RECORD_AUDIO)
        }
    }
}

/** Opens this app's page in the phone's settings (the microphone permission). */
fun openAppSettings(context: Context) {
    runCatching {
        context.startActivity(
            android.content.Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
                .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK),
        )
    }
}

/** Live loudness bars while the owner speaks; the newest bar sits at the reading end. */
@Composable
fun Waveform(levels: List<Float>, modifier: Modifier = Modifier, color: Color = Divan.colors.goldInk) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
        for (l in levels) {
            Box(Modifier.width(3.dp).fillMaxHeight(maxOf(0.12f, l)).alpha(0.35f + 0.65f * minOf(1f, l * 1.6f)).clip(CircleShape).background(color))
        }
    }
}

// -------------------------------------------------------- the composer --
/** Pickers for photos and films (gallery or camera) and PDFs; all land in [a]. */
@Composable
fun rememberPickers(a: Attachments): (String) -> Unit {
    val context = LocalContext.current
    val env = LocalEnv.current
    var capture by remember { mutableStateOf<Uri?>(null) }
    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(10)) { a.add(it) }
    val pdf = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { a.add(it) }
    val photo = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok -> capture?.let { if (ok) a.add(listOf(it)) } }
    val film = rememberLauncherForActivityResult(ActivityResultContracts.CaptureVideo()) { ok -> capture?.let { if (ok) a.add(listOf(it)) } }
    fun target(ext: String): Uri = FileProvider.getUriForFile(context, "${context.packageName}.files", File(env.media.scratch("capture"), "${System.currentTimeMillis()}.$ext")).also { capture = it }
    return { what ->
        when (what) {
            "gallery" -> gallery.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageAndVideo))
            "photo" -> photo.launch(target("jpg"))
            "film" -> film.launch(target("mp4"))
            "pdf" -> pdf.launch(arrayOf("application/pdf"))
        }
    }
}

@Composable
fun AttachMenu(open: Boolean, onDismiss: () -> Unit, pick: (String) -> Unit) {
    val c = Divan.colors
    DropdownMenu(open, onDismiss, containerColor = c.overlay) {
        for ((key, label, icon) in listOf(Triple("gallery", "عکس و فیلم از گالری", DivanIcon.IMAGE), Triple("photo", "عکس با دوربین", DivanIcon.IMAGE), Triple("film", "فیلم با دوربین", DivanIcon.VIDEO), Triple("pdf", "PDF", DivanIcon.REPORT))) {
            DropdownMenuItem(
                text = { Text(label, style = Divan.type.body, color = c.textPrimary) },
                leadingIcon = { DIcon(icon, size = 20.dp, tint = c.textSecondary) },
                onClick = { onDismiss(); pick(key) },
            )
        }
    }
}

/**
 * The owner's composer everywhere: words, voice that becomes words, photos, films and PDFs (contract §17).
 * [onSend] returns normally when sent (the composer clears) and throws to keep the draft.
 */
@Composable
fun Composer(
    placeholder: String,
    onSend: suspend (body: String, attachments: List<String>) -> Unit,
    modifier: Modifier = Modifier,
    purpose: String = "message",
    allowFiles: Boolean = true,
    draftKey: String = placeholder,
) {
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    var text by rememberSaveable(draftKey) { mutableStateOf("") }
    var voice by remember { mutableStateOf<VoiceResult?>(null) }
    var sending by remember { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    val files = rememberAttachments()
    val pick = rememberPickers(files)
    val vh = rememberVoiceInput(purpose, onFallback = if (allowFiles) files::addFile else null) { r ->
        text = if (text.isBlank()) r.text else "${text.trimEnd()} ${r.text}"
        // Only the hub keeps the original recording; the phone's own recogniser leaves the words alone.
        if (r.fileId != null) voice = r
    }
    val v = vh.v
    val ctx = LocalContext.current
    val ready = (text.isNotBlank() || files.ids.isNotEmpty()) && !files.uploading && !sending && !v.active

    fun submit() {
        if (!ready) return
        sending = true
        scope.launch {
            try {
                onSend(text.trim(), files.ids + listOfNotNull(voice?.fileId))
                text = ""; voice = null; files.clear()
            } catch (_: Exception) {
                // the caller reported it; keep the draft
            } finally {
                sending = false
            }
        }
    }

    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.card).border(1.dp, c.lineStrong, RoundedCornerShape(16.dp)).padding(6.dp)) {
        AttachmentTray(files)
        v.unavailable?.let { why -> VoiceProblem(why, v.settings, { openAppSettings(ctx) }, v::dismiss) }
        voice?.let { r ->
            Row(Modifier.padding(horizontal = 8.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                DIcon(DivanIcon.MIC, size = 14.dp, tint = c.textSecondary)
                Text("صدای اصلی", style = Divan.type.micro, color = c.textSecondary)
                Fig(clock(r.seconds), style = Divan.type.figureSmall, color = c.textSecondary)
                Text("همراه پیام میرود", style = Divan.type.micro, color = c.textSecondary, modifier = Modifier.weight(1f))
                Text("نفرست", Modifier.clickable { voice = null }.padding(4.dp), style = Divan.type.micro, color = c.textMuted)
            }
        }
        Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
            when {
                v.recording -> {
                    IconBtn(DivanIcon.CLOSE, "لغو ضبط", v::cancel)
                    Column(Modifier.weight(1f).heightIn(min = 44.dp).padding(horizontal = 4.dp), verticalArrangement = Arrangement.Center) {
                        Row(Modifier.height(44.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            LiveDot(c.negative, size = 9.dp)
                            Waveform(v.levels, Modifier.weight(1f).height(30.dp))
                            Fig(clock(v.elapsed), Modifier.width(40.dp), style = Divan.type.figureSmall, color = c.textSecondary)
                        }
                        // The phone's words as they come (its own recogniser, fa-IR).
                        if (v.partial.isNotBlank()) Text(v.partial, style = Divan.type.small, color = c.textSecondary, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                        // ⟨1.9⟩ §27.3: the phone's recogniser failed; this recording goes to the hub.
                        v.fellBack?.let { Text(it, style = Divan.type.micro, color = c.warning, maxLines = 2) }
                    }
                    RoundAction(DivanIcon.STOP, "تمام؛ به متن تبدیل کن", true, v::finish)
                }
                v.transcribing -> {
                    IconBtn(DivanIcon.CLOSE, "لغو", v::cancel)
                    Row(Modifier.weight(1f).height(44.dp).padding(horizontal = 4.dp).semantics { contentDescription = "در حال تبدیل به متن" }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        CircularProgressIndicator(Modifier.size(16.dp), color = c.goldInk, strokeWidth = 2.dp)
                        Text(v.partial.ifBlank { if (v.engine == "hub") com.coinepro.hq.core.media.HUB_TRANSCRIBING else "در حال تشخیص گفتار…" }, style = Divan.type.small, color = c.textSecondary, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                    }
                }
                else -> {
                    if (allowFiles) Box {
                        IconBtn(DivanIcon.ATTACH, "پیوست عکس، فیلم یا PDF", { menu = true })
                        AttachMenu(menu, { menu = false }, pick)
                    }
                    BasicTextField(
                        text, { if (it.length <= 10_000) text = it },
                        Modifier.weight(1f).heightIn(min = 44.dp).padding(horizontal = 6.dp, vertical = 10.dp).semantics { contentDescription = placeholder },
                        textStyle = Divan.type.body.copy(color = c.textPrimary),
                        cursorBrush = SolidColor(c.goldInk),
                        maxLines = 6,
                        decorationBox = { inner -> Box { if (text.isEmpty()) Text(placeholder, style = Divan.type.body, color = c.textMuted); inner() } },
                    )
                    IconBtn(DivanIcon.MIC, "بگو؛ به متن فارسی تبدیل میشود", vh.start)
                    RoundAction(DivanIcon.SEND, "بفرست", ready, ::submit, busy = sending)
                }
            }
        }
    }
}

/** Why the voice could not be heard, in plain words, with the way forward: typing (always) and the phone's settings (a refused microphone). */
@Composable
fun VoiceProblem(why: String, settings: Boolean, onSettings: () -> Unit, onDismiss: () -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Row(
        modifier.fillMaxWidth().padding(4.dp).clip(RoundedCornerShape(12.dp)).background(c.softWarning).padding(horizontal = 10.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        DIcon(DivanIcon.MIC, size = 16.dp, tint = c.warning)
        Text(why, style = Divan.type.caption, color = c.textPrimary, modifier = Modifier.weight(1f))
        if (settings) Text("تنظیمات", Modifier.clip(RoundedCornerShape(6.dp)).clickable(role = Role.Button, onClick = onSettings).padding(4.dp), style = Divan.type.caption.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold), color = c.goldInk)
        IconBtn(DivanIcon.CLOSE, "بستن؛ مینویسم", onDismiss)
    }
}

@Composable
fun RoundAction(icon: DivanIcon, label: String, enabled: Boolean, onClick: () -> Unit, busy: Boolean = false) {
    val c = Divan.colors
    Box(
        Modifier.size(44.dp).clip(CircleShape).background(if (enabled) c.goldFill else c.disabledFill)
            .clickable(enabled = enabled, role = Role.Button, onClickLabel = label, onClick = onClick).semantics { contentDescription = label },
        contentAlignment = Alignment.Center,
    ) {
        if (busy) CircularProgressIndicator(Modifier.size(18.dp), color = c.onGold, strokeWidth = 2.dp)
        else DIcon(icon, size = 20.dp, tint = if (enabled) c.onGold else c.disabledText)
    }
}
