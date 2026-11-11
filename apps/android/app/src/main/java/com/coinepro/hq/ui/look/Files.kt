package com.coinepro.hq.ui.look

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.ui.PlayerView
import coil3.compose.AsyncImage
import com.coinepro.hq.core.data.INLINE_VIDEO_FA
import com.coinepro.hq.core.data.VIDEO_FAILED_FA
import com.coinepro.hq.core.data.isImage
import com.coinepro.hq.core.data.isVideo
import com.coinepro.hq.core.media.clock
import com.coinepro.hq.core.media.fileSize
import com.coinepro.hq.core.net.DeskFile
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FigureFace
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.fadingEdges
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.settle
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.media.openFile
import com.coinepro.hq.ui.media.rememberPlayer
import kotlinx.coroutines.launch

// ⟨1.0.1⟩ Part C, the files of an output (C2.2; features 29 and 30). The thing itself is seen, not a label that stands for it: a strip
// of tiles, each a file as it is (a picture shows itself, a video its poster frame with its length, a document its type mark and
// name), captioned with its plain name and size. A tap opens it in place: a picture on the full screen, a video under the strip
// (muted, without controls; one more tap is the full screen with controls and sound), a document in the phone's own reader. Nothing
// plays before the owner's own tap. A video that will not play says so in one sentence with its download. The player is the
// platform's (Media3, already in the project).
//
// How it is used:
// - `FilesStrip(files) { f -> … what sits under f's tile … }` in a session's thread, its details, an output's page, an end leaf.
// - `HeroMedia(f, ratio = 9f / 16f, cover = cover)` for one file large, in its network's frame (a desk card).
// - `HeroPlayer(f)` for a video that plays where it is, with its controls (the top of an output's page).
// - `FileFace(f)` inside any frame of your own (a small poster of a row).

/** A file of a desk card as the files' pieces take it. */
fun DeskFile.asFile(): FileRef = FileRef(
    id = id, name = name, mime = mime, size = size,
    kind = when { mime.startsWith("video/") -> "video"; mime.startsWith("image/") -> "image"; mime.startsWith("audio/") -> "audio"; else -> "document" },
)

private fun ext(name: String): String = if ('.' in name) name.substringAfterLast('.').uppercase().take(4) else "FILE"

private val TILE_W = 116.dp
private val TILE_H = 148.dp

/** The round play sign on a poster: ivory on a dark disc, never gold. */
@Composable
fun BoxScope.PlaySign(size: Dp = 40.dp) {
    Box(Modifier.align(Alignment.Center).size(size).clip(CircleShape).background(Color.Black.copy(alpha = 0.55f)).border(1.dp, Color.White.copy(alpha = 0.35f), CircleShape), contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(size * 0.36f)) {
            // drawn left to right in both reading directions: play points the way time runs
            val p = Path().apply { moveTo(this@Canvas.size.width * 0.12f, 0f); lineTo(this@Canvas.size.width, this@Canvas.size.height / 2); lineTo(this@Canvas.size.width * 0.12f, this@Canvas.size.height); close() }
            drawPath(p, Color.White)
        }
    }
}

@Composable
private fun BoxScope.Length(seconds: Double?) {
    if (seconds == null || seconds <= 0) return
    Box(Modifier.align(Alignment.BottomStart).padding(6.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.65f)).padding(horizontal = 6.dp, vertical = 1.dp)) {
        Fig(clock(seconds), style = Divan.type.figureSmall.copy(fontSize = 10.sp, lineHeight = 14.sp), color = Color.White)
    }
}

/**
 * What a file shows of itself inside a frame of any size (the frame gives the shape): a video's poster with the play sign and its
 * length, a picture itself, a document's type mark. Under a picture that has not arrived yet its mark is there, never an empty box.
 * [large]: the picture itself, not its thumbnail. [mark] false: no mark under the picture (something of the caller's lies over it).
 */
@Composable
fun FileFace(f: FileRef, modifier: Modifier = Modifier, sign: Dp = 40.dp, large: Boolean = false, mark: Boolean = true) {
    val media = LocalEnv.current.media
    val c = Divan.colors
    Box(modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        when {
            isVideo(f) -> {
                AsyncImage(
                    f.variants.poster?.let { media.imageModel(it) } ?: media.imageModel(f.id, "poster"), null, media.images,
                    Modifier.fillMaxSize(), contentScale = ContentScale.Crop,
                )
                PlaySign(sign)
                Length(f.durationS)
            }
            isImage(f) -> {
                if (mark) DIcon(DivanIcon.IMAGE, size = 22.dp, tint = c.textMuted)
                AsyncImage(
                    if (large) media.imageModel(f.id) else media.imageModel(f.variants.thumb ?: f.id, if (f.variants.thumb != null) null else "thumb"), null, media.images,
                    Modifier.fillMaxSize(), contentScale = ContentScale.Crop,
                )
            }
            else -> Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                DIcon(DivanIcon.REPORT, size = 26.dp, tint = c.textSecondary)
                Box(Modifier.clip(RoundedCornerShape(5.dp)).border(1.dp, c.lineStrong, RoundedCornerShape(5.dp)).padding(horizontal = 6.dp, vertical = 1.dp)) {
                    Text(ext(f.name), style = Divan.type.micro.copy(fontFamily = FigureFace, fontWeight = FontWeight.Bold, fontSize = 10.sp, lineHeight = 14.sp), color = c.textSecondary, maxLines = 1)
                }
            }
        }
    }
}

/** A frame for a file's face: the tile surface with a hairline. */
@Composable
fun FaceFrame(modifier: Modifier = Modifier, radius: Dp = 12.dp, content: @Composable BoxScope.() -> Unit) {
    val c = Divan.colors
    val shape = RoundedCornerShape(radius)
    Box(modifier.clip(shape).background(c.tile).border(1.dp, c.lineDivider, shape), contentAlignment = Alignment.Center, content = content)
}

/** One file as a tile: itself, then its plain name and size. */
@Composable
fun FileTile(f: FileRef, onOpen: () -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val what = if (isVideo(f)) "پخش" else "باز کردن"
    Column(
        modifier.width(TILE_W).clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button, onClickLabel = what, onClick = onOpen)
            .semantics(mergeDescendants = true) { contentDescription = "$what ${f.name}" }.testTag("file-tile"),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        FaceFrame(Modifier.fillMaxWidth().height(TILE_H)) { FileFace(f) }
        Column(Modifier.padding(horizontal = 2.dp)) {
            // one line: a long name keeps its two ends (its kind is read from its last letters), never a break inside its extension
            Text(f.name.ifBlank { "فایل" }, style = Divan.type.micro.copy(fontSize = 12.sp, lineHeight = 16.sp), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.MiddleEllipsis)
            if (f.size > 0) Fig(fileSize(f.size), style = Divan.type.figureSmall.copy(fontSize = 11.sp), color = c.textMuted)
        }
    }
}

/** «این ویدیو پخش نشد؛ دانلودش کن», with the download. */
@Composable
fun VideoFailed(f: FileRef, modifier: Modifier = Modifier) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val c = Divan.colors
    var busy by remember { mutableStateOf(false) }
    Row(
        modifier.fillMaxWidth().testTag("video-failed").clip(RoundedCornerShape(12.dp)).background(c.tile).padding(start = 12.dp, end = 8.dp, top = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(VIDEO_FAILED_FA, style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
        HqButton("دانلود", {
            if (busy) return@HqButton
            busy = true
            scope.launch {
                try { openFile(env, context, f) } catch (_: Exception) { toasts.error("فایل باز نشد.") } finally { busy = false }
            }
        }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.DOWNLOAD, loading = busy)
    }
}

/** A player on [f]: muted or with sound, from [at] milliseconds. [failed] is told when the film will not play. */
@Composable
private fun rememberFilm(f: FileRef, sound: Boolean, at: Long, failed: () -> Unit): Player {
    val media = LocalEnv.current.media
    val player = rememberPlayer(media)
    DisposableEffect(player, f.id) {
        val l = object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) = failed()
        }
        player.addListener(l)
        player.volume = if (sound) 1f else 0f
        player.setMediaItem(MediaItem.fromUri(media.url(f.id)))
        player.prepare()
        if (at > 0) player.seekTo(at)
        player.play()
        onDispose { player.removeListener(l) }
    }
    return player
}

private fun ratioOf(f: FileRef): Float {
    val w = f.width ?: 0
    val h = f.height ?: 0
    return if (w > 0 && h > 0) (w.toFloat() / h).coerceIn(0.5f, 2f) else 9f / 16f
}

/** A video playing inside the page: muted and bare; a tap on it is the full screen with controls and sound, from where it was. */
@Composable
private fun InlineVideo(f: FileRef, onFull: (Long) -> Unit, onClose: () -> Unit) {
    val c = Divan.colors
    var failed by remember(f.id) { mutableStateOf(false) }
    if (failed) { VideoFailed(f); return }
    val player = rememberFilm(f, sound = false, at = 0) { failed = true }
    val ratio = ratioOf(f)
    Column(Modifier.settle().testTag("inline-video"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Box(
            Modifier.height(if (ratio < 1f) 320.dp else 200.dp).aspectRatio(ratio).clip(RoundedCornerShape(14.dp)).background(Color.Black)
                .clickable(role = Role.Button, onClickLabel = "تمام‌صفحه با صدا") { onFull(player.currentPosition) },
        ) {
            AndroidView({ PlayerView(it).apply { useController = false; this.player = player } }, Modifier.fillMaxSize())
            Box(
                Modifier.align(Alignment.TopEnd).padding(8.dp).size(32.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.6f))
                    .clickable(role = Role.Button, onClickLabel = "بستن پخش", onClick = onClose),
                contentAlignment = Alignment.Center,
            ) { DIcon(DivanIcon.CLOSE, size = 16.dp, tint = Color.White) }
        }
        Text(INLINE_VIDEO_FA, style = Divan.type.micro, color = c.textMuted)
    }
}

/** The full screen: a picture, or a video with its controls and sound from where the inline one was. */
@Composable
fun FileViewer(f: FileRef, at: Long = 0, onClose: () -> Unit) {
    val media = LocalEnv.current.media
    Dialog(onClose, DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Box(Modifier.fillMaxSize().background(Color.Black), contentAlignment = Alignment.Center) {
            if (isVideo(f)) {
                var failed by remember(f.id) { mutableStateOf(false) }
                if (failed) Box(Modifier.padding(24.dp).widthIn(max = 420.dp)) { VideoFailed(f) }
                else {
                    val player = rememberFilm(f, sound = true, at = at) { failed = true }
                    AndroidView({ PlayerView(it).apply { this.player = player; setShowBuffering(PlayerView.SHOW_BUFFERING_ALWAYS) } }, Modifier.fillMaxSize())
                }
            } else AsyncImage(media.imageModel(f.id), f.name, media.images, Modifier.fillMaxSize(), contentScale = ContentScale.Fit)
            Row(Modifier.align(Alignment.TopStart).fillMaxWidth().statusBarsPadding().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(44.dp).clip(CircleShape).clickable(role = Role.Button, onClickLabel = "بستن", onClick = onClose).semantics { contentDescription = "بستن" }, contentAlignment = Alignment.Center) {
                    DIcon(DivanIcon.CLOSE, size = 24.dp, tint = Color.White)
                }
                Text(f.name, Modifier.weight(1f).padding(horizontal = 8.dp), style = Divan.type.small, color = Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

/**
 * The files of one output as a horizontal strip that scrolls. [under]: what sits under a tile (its publish action, or where its
 * publication stands). A video plays under the strip, in place; a picture opens on the full screen; a document goes to the phone's
 * own reader. [playing0]: a video that is already playing (a link that opens on it).
 */
@Composable
fun FilesStrip(files: List<FileRef>, modifier: Modifier = Modifier, playing0: String? = null, under: (@Composable (FileRef) -> Unit)? = null) {
    val shown = files.filter { it.id.isNotBlank() }
    if (shown.isEmpty()) return
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var playing by rememberSaveable(shown.firstOrNull()?.id) { mutableStateOf(playing0) }
    var full by remember { mutableStateOf<Pair<String, Long>?>(null) }
    val scroll = rememberScrollState()
    Column(modifier.fillMaxWidth().testTag("files-strip"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth().fadingEdges(scroll).horizontalScroll(scroll), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
            for (f in shown) Column(Modifier.width(TILE_W), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                FileTile(f, onOpen = {
                    when {
                        isVideo(f) -> playing = f.id
                        isImage(f) -> full = f.id to 0L
                        else -> scope.launch { try { openFile(env, context, f) } catch (_: Exception) { toasts.error("فایل باز نشد.") } }
                    }
                })
                under?.invoke(f)
            }
        }
        shown.firstOrNull { it.id == playing }?.let { f ->
            InlineVideo(f, onFull = { at -> playing = null; full = f.id to at }, onClose = { playing = null })
        }
    }
    full?.let { (id, at) -> shown.firstOrNull { it.id == id }?.let { f -> FileViewer(f, at) { full = null } } }
}

/**
 * One file large, in a frame of its network's shape ([ratio] width over height): the picture itself, or the video's poster ([cover]:
 * a reel's cover stands for the video until he plays it, as the feed shows it); a tap opens the full screen (a video with its
 * controls and sound). The frame is never taller than [maxHeight].
 */
@Composable
fun HeroMedia(f: FileRef, ratio: Float, modifier: Modifier = Modifier, cover: FileRef? = null, maxHeight: Dp = 300.dp) {
    var open by remember { mutableStateOf(false) }
    Box(modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        FaceFrame(
            Modifier.widthIn(max = maxHeight * ratio).fillMaxWidth().aspectRatio(ratio).testTag("hero-media")
                .clickable(role = Role.Button, onClickLabel = if (isVideo(f)) "پخش" else "نمایش") { open = true }
                .semantics { contentDescription = "${if (isVideo(f)) "پخش" else "نمایش"} ${f.name}" },
            radius = 16.dp,
        ) {
            if (cover != null && isVideo(f) && isImage(cover)) {
                FileFace(cover, large = true, mark = false)
                PlaySign(52.dp)
                Length(f.durationS)
            } else FileFace(f, sign = 52.dp, large = true)
        }
    }
    if (open) FileViewer(f) { open = false }
}

/** A video large and playable where it is: its poster until he plays it, then the platform's player with its controls and sound. */
@Composable
fun HeroPlayer(f: FileRef, modifier: Modifier = Modifier, maxHeight: Dp = 420.dp) {
    var playing by rememberSaveable(f.id) { mutableStateOf(false) }
    var failed by remember(f.id) { mutableStateOf(false) }
    if (failed) { VideoFailed(f, modifier); return }
    val ratio = ratioOf(f)
    Box(modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        FaceFrame(Modifier.widthIn(max = maxHeight * ratio).fillMaxWidth().aspectRatio(ratio).testTag("hero-player"), radius = 16.dp) {
            if (playing) {
                val player = rememberFilm(f, sound = true, at = 0) { failed = true }
                AndroidView({ PlayerView(it).apply { this.player = player; setShowBuffering(PlayerView.SHOW_BUFFERING_WHEN_PLAYING) } }, Modifier.fillMaxSize().background(Color.Black))
            } else Box(Modifier.fillMaxSize().clickable(role = Role.Button, onClickLabel = "پخش") { playing = true }.semantics { contentDescription = "پخش ${f.name}" }) {
                FileFace(f, sign = 56.dp)
            }
        }
    }
}
