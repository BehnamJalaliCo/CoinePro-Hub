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
data class VoiceResult(val text: String, val fileId: String, val seconds: Double)

/** Speak → exact Persian text (contract §17.2). The text lands in the caller's field for the owner to read and fix;
 *  the recording travels with it. When the speech service cannot help, [onFallback] gets the audio file itself. */
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
    var recording by mutableStateOf(false)
        private set
    var transcribing by mutableStateOf(false)
        private set
    var elapsed by mutableDoubleStateOf(0.0)
        private set
    val levels = mutableStateListOf<Float>().apply { repeat(32) { add(0f) } }
    private var ticker: Job? = null
    private var work: Job? = null
    val active: Boolean get() = recording || transcribing

    internal fun begin() {
        if (!rec.start()) { toasts.error("میکروفون در دسترس نیست."); return }
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
        ticker?.cancel()
        recording = false
        val (file, seconds) = rec.stop() ?: return toasts.info("صدایی ضبط نشد؛ دکمه را بزن و بعد حرف بزن.")
        reset()
        if (seconds < 0.6) { file.delete(); return toasts.info("صدایی ضبط نشد؛ دکمه را بزن و بعد حرف بزن.") }
        transcribing = true
        work = scope.launch {
            try {
                val t = withContext(Dispatchers.IO) { env.api.transcribe(file, "audio/mp4", purpose) }
                if (t.text.isBlank()) toasts.info("حرفی شنیده نشد؛ دوباره بگو.")
                else onText()(VoiceResult(t.text.trim(), t.fileId, if (t.durationS > 0) t.durationS else seconds))
            } catch (e: ApiException) {
                val fb = onFallback()
                if (fb != null) { fb(file); toasts.info("${e.messageFa} صدا به‌عنوان پیوست اضافه شد.") } else toasts.error(e.messageFa)
            } finally {
                transcribing = false
            }
        }
    }

    fun cancel() {
        ticker?.cancel(); work?.cancel()
        rec.cancel()
        recording = false; transcribing = false
        reset()
    }

    private fun reset() { elapsed = 0.0; for (i in levels.indices) levels[i] = 0f }
}

/** A voice input wired to the microphone permission: [start] asks once, then records. */
class VoiceHandle(val v: VoiceInput, val start: () -> Unit)

@Composable
fun rememberVoiceInput(purpose: String, onFallback: ((File) -> Unit)? = null, onText: (VoiceResult) -> Unit): VoiceHandle {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val text by rememberUpdatedState(onText)
    val fallback by rememberUpdatedState(onFallback)
    val v = remember(env, purpose) { VoiceInput(env, scope, toasts, purpose, { text }, { fallback }) }
    DisposableEffect(v) { onDispose { v.cancel() } }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        if (ok) v.begin() else toasts.error("اجازه‌ی میکروفون داده نشده؛ از تنظیمات گوشی برای این اپ روشنش کن.")
    }
    return remember(v) {
        VoiceHandle(v) {
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) v.begin()
            else ask.launch(Manifest.permission.RECORD_AUDIO)
        }
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
        voice = r
    }
    val v = vh.v
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
                    Row(Modifier.weight(1f).height(44.dp).padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        LiveDot(c.negative, size = 9.dp)
                        Waveform(v.levels, Modifier.weight(1f).height(30.dp))
                        Fig(clock(v.elapsed), Modifier.width(40.dp), style = Divan.type.figureSmall, color = c.textSecondary)
                    }
                    RoundAction(DivanIcon.STOP, "تمام؛ به متن تبدیل کن", true, v::finish)
                }
                v.transcribing -> {
                    IconBtn(DivanIcon.CLOSE, "لغو", v::cancel)
                    Row(Modifier.weight(1f).height(44.dp).padding(horizontal = 4.dp).semantics { contentDescription = "در حال تبدیل به متن" }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        CircularProgressIndicator(Modifier.size(16.dp), color = c.goldInk, strokeWidth = 2.dp)
                        Text("در حال تبدیل به متن فارسی…", style = Divan.type.small, color = c.textSecondary)
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
