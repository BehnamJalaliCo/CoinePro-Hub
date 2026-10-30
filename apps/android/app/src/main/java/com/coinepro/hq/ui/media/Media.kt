package com.coinepro.hq.ui.media

import android.content.Intent
import androidx.annotation.OptIn
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.FileProvider
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.PlayerView
import coil3.compose.AsyncImage
import com.coinepro.hq.core.media.MediaKit
import com.coinepro.hq.core.media.clock
import com.coinepro.hq.core.media.fileSize
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.Request

/** Everything attached to one message, grouped: pictures first, then films, voice notes and documents (§17.1). */
@Composable
fun MessageMedia(items: List<FileRef>, transcriptInBody: Boolean = false, modifier: Modifier = Modifier) {
    if (items.isEmpty()) return
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        val images = items.filter { it.kind == "image" }
        if (images.isNotEmpty()) Images(images)
        items.filter { it.kind == "video" }.forEach { VideoTile(it) }
        items.filter { it.kind == "audio" }.forEach { AudioNote(it, showTranscript = !transcriptInBody) }
        items.filter { it.kind == "document" }.forEach { DocRow(it) }
    }
}

@Composable
private fun Images(images: List<FileRef>) {
    val media = LocalEnv.current.media
    val c = Divan.colors
    var open by remember { mutableStateOf<Int?>(null) }
    if (images.size == 1) {
        val one = images[0]
        // Known size: the frame is exactly the picture, at most 280 wide and 260 tall. Unknown: a 4:3 frame.
        val ratio = if (one.width != null && one.height != null && one.height > 0) one.width.toFloat() / one.height else 4f / 3f
        val w: Dp = minOf(280f, 260f * ratio).dp
        AsyncImage(
            media.imageModel(one.variants.thumb ?: one.id, if (one.variants.thumb != null) null else "thumb"), one.name, media.images,
            Modifier.width(w).aspectRatio(ratio).clip(RoundedCornerShape(12.dp)).background(c.tile).clickable(role = Role.Image, onClickLabel = "نمایش") { open = 0 },
            contentScale = ContentScale.Crop,
        )
    } else {
        Column(Modifier.width(260.dp).clip(RoundedCornerShape(12.dp)), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            images.take(4).chunked(2).forEachIndexed { row, pair ->
                Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                    pair.forEachIndexed { col, m ->
                        val i = row * 2 + col
                        Box(Modifier.weight(1f).aspectRatio(1f).background(c.tile).clickable(role = Role.Image, onClickLabel = "نمایش") { open = i }) {
                            AsyncImage(media.imageModel(m.variants.thumb ?: m.id, if (m.variants.thumb != null) null else "thumb"), m.name, media.images, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                            if (i == 3 && images.size > 4) {
                                Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.55f)), contentAlignment = Alignment.Center) {
                                    Fig("+${images.size - 4}", style = Divan.type.h2, color = Color.White)
                                }
                            }
                        }
                    }
                    if (pair.size == 1) Box(Modifier.weight(1f))
                }
            }
        }
    }
    open?.let { start -> ImageViewer(images, start, media) { open = null } }
}

/** Full-screen pictures: swipe between them, close with back or the button. */
@Composable
private fun ImageViewer(images: List<FileRef>, start: Int, media: MediaKit, onClose: () -> Unit) {
    val pager = rememberPagerState(initialPage = start) { images.size }
    Dialog(onClose, DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Box(Modifier.fillMaxSize().background(Color.Black)) {
            HorizontalPager(pager, Modifier.fillMaxSize()) { i ->
                AsyncImage(media.imageModel(images[i].id), images[i].name, media.images, Modifier.fillMaxSize().pointerInput(Unit) { detectTapGestures(onDoubleTap = { onClose() }) }, contentScale = ContentScale.Fit)
            }
            Row(Modifier.fillMaxWidth().statusBarsPadding().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(44.dp).clip(CircleShape).clickable(role = Role.Button, onClickLabel = "بستن", onClick = onClose).semantics { contentDescription = "بستن" }, contentAlignment = Alignment.Center) {
                    DIcon(DivanIcon.CLOSE, size = 24.dp, tint = Color.White)
                }
                Text(images[pager.currentPage].name, Modifier.weight(1f).padding(horizontal = 8.dp), style = Divan.type.small, color = Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (images.size > 1) Fig("${pager.currentPage + 1}/${images.size}", style = Divan.type.figureSmall, color = Color.White.copy(alpha = 0.7f))
            }
        }
    }
}

@OptIn(UnstableApi::class)
@Composable
fun rememberPlayer(media: MediaKit): ExoPlayer {
    val context = LocalContext.current
    val player = remember { ExoPlayer.Builder(context).setMediaSourceFactory(DefaultMediaSourceFactory(media.dataSource)).build() }
    DisposableEffect(player) { onDispose { player.release() } }
    return player
}

/** A film in a message: its poster with a play mark; plays full screen with the platform controls. */
@Composable
private fun VideoTile(v: FileRef) {
    val media = LocalEnv.current.media
    val c = Divan.colors
    var playing by remember { mutableStateOf(false) }
    if (v.status == "failed") {
        Text("فیلم «${v.name}» پردازش نشد.", style = Divan.type.caption, color = c.negative)
        return
    }
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Box(
            Modifier.width(280.dp).aspectRatio(16f / 9f).clip(RoundedCornerShape(12.dp)).background(Color.Black).clickable(role = Role.Button, onClickLabel = "پخش فیلم") { playing = true },
            contentAlignment = Alignment.Center,
        ) {
            v.variants.poster?.let { AsyncImage(media.imageModel(it), null, media.images, Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
            Box(Modifier.size(52.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.55f)), contentAlignment = Alignment.Center) {
                DIcon(DivanIcon.RESUME, size = 26.dp, tint = Color.White)
            }
        }
        Row(Modifier.padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            DIcon(DivanIcon.VIDEO, size = 14.dp, tint = c.textMuted)
            v.durationS?.let { Fig(clock(it), style = Divan.type.figureSmall, color = c.textMuted) }
            Fig(fileSize(v.size), style = Divan.type.figureSmall, color = c.textMuted)
            if (v.status == "processing") Text("آماده‌سازی برای ایجنت‌ها", style = Divan.type.micro, color = c.textMuted)
        }
    }
    if (playing) {
        Dialog({ playing = false }, DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
            val player = rememberPlayer(media)
            LaunchedEffect(v.id) {
                player.setMediaItem(MediaItem.fromUri(media.url(v.id)))
                player.prepare()
                player.play()
            }
            Box(Modifier.fillMaxSize().background(Color.Black)) {
                AndroidView({ PlayerView(it).apply { this.player = player; setShowBuffering(PlayerView.SHOW_BUFFERING_ALWAYS) } }, Modifier.fillMaxSize())
                Box(Modifier.statusBarsPadding().padding(8.dp).size(44.dp).clip(CircleShape).clickable(role = Role.Button, onClickLabel = "بستن") { playing = false }, contentAlignment = Alignment.Center) {
                    DIcon(DivanIcon.CLOSE, size = 24.dp, tint = Color.White)
                }
            }
        }
    }
}

/** Deterministic bar heights per file, so a voice note always looks the same. */
private fun bars(seed: String, n: Int): List<Float> {
    var h = seed.fold(2166136261L.toInt()) { acc, ch -> (acc xor ch.code) * 16777619 }
    return List(n) { i ->
        h = (h xor (i + 1)) * 16777619
        val r = ((h.toLong() and 0xffffffffL) % 1000) / 1000f
        0.25f + 0.75f * kotlin.math.abs(kotlin.math.sin(i * 0.55f + r * 2.4f)) * (0.55f + 0.45f * r)
    }
}

/** A voice note: play, scrub, time — and the exact text when the hub has it. */
@Composable
fun AudioNote(a: FileRef, showTranscript: Boolean = true) {
    val media = LocalEnv.current.media
    val c = Divan.colors
    val player = rememberPlayer(media)
    var playing by remember { mutableStateOf(false) }
    var pos by remember { mutableDoubleStateOf(0.0) }
    var dur by remember { mutableDoubleStateOf(a.durationS ?: 0.0) }
    var text by remember { mutableStateOf(false) }
    val shape = remember(a.id) { bars(a.id.takeLast(64), 32) }
    DisposableEffect(player) {
        val l = object : Player.Listener {
            override fun onIsPlayingChanged(isPlaying: Boolean) { playing = isPlaying }
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_READY && player.duration > 0) dur = player.duration / 1000.0
                if (state == Player.STATE_ENDED) { player.pause(); player.seekTo(0); pos = 0.0 }
            }
        }
        player.addListener(l)
        onDispose { player.removeListener(l) }
    }
    LaunchedEffect(playing) { while (playing) { pos = player.currentPosition / 1000.0; delay(100) } }
    val toggle = {
        if (player.mediaItemCount == 0) { player.setMediaItem(MediaItem.fromUri(media.url(a.id))); player.prepare() }
        if (player.isPlaying) player.pause() else player.play()
    }
    Column(Modifier.widthIn(max = 300.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 10.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Box(Modifier.size(36.dp).clip(CircleShape).background(c.goldFill).clickable(role = Role.Button, onClickLabel = if (playing) "مکث" else "پخش") { toggle() }, contentAlignment = Alignment.Center) {
                DIcon(if (playing) DivanIcon.PAUSE else DivanIcon.RESUME, size = 18.dp, tint = c.onGold)
            }
            // Playback runs left to right like every media timeline, also in RTL.
            val p = if (dur > 0) (pos / dur).toFloat() else 0f
            androidx.compose.runtime.CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                Row(
                    Modifier.weight(1f).height(30.dp).pointerInput(dur) {
                        detectTapGestures { o -> if (dur > 0) { if (player.mediaItemCount == 0) { player.setMediaItem(MediaItem.fromUri(media.url(a.id))); player.prepare() }; player.seekTo((o.x / size.width * dur * 1000).toLong()) } }
                    }.semantics { contentDescription = "جای پخش" },
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    shape.forEachIndexed { i, h ->
                        Box(Modifier.weight(1f).fillMaxHeight(h).clip(CircleShape).background(if (i.toFloat() / shape.size < p) c.goldInk else c.lineStrong))
                    }
                }
            }
            Fig(clock(if (playing || pos > 0) pos else dur), Modifier.width(36.dp), style = Divan.type.figureSmall, color = c.textMuted)
        }
        // ⟨1.9⟩ §27.3: the hub's own transcript (`transcript_fa`) once it is on, refreshed by `file.transcribed`.
        val speech = rememberSpeechEnabled()
        val words = a.hubText
        if (showTranscript && words != null) {
            Text(if (text) "بستن متن" else if (speech) "متن هاب" else "متن ویس", Modifier.clickable { text = !text }.padding(horizontal = 4.dp), style = Divan.type.micro, color = c.goldInk)
            if (text) Text(words, Modifier.padding(horizontal = 4.dp), style = Divan.type.small, color = c.textSecondary)
        } else if (a.status == "processing") {
            Text("در حال نوشتن متن…", Modifier.padding(horizontal = 4.dp), style = Divan.type.micro, color = c.textMuted)
        }
    }
}

/** A PDF: downloaded through the API, then handed to the phone's viewer. */
@Composable
private fun DocRow(d: FileRef) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val c = Divan.colors
    var busy by remember { mutableStateOf(false) }
    Row(
        Modifier.widthIn(max = 300.dp).fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile)
            .clickable(enabled = !busy, role = Role.Button, onClickLabel = "باز کردن") {
                busy = true
                scope.launch {
                    try {
                        val f = withContext(Dispatchers.IO) {
                            val out = File(env.media.scratch("shared"), d.name.replace(Regex("[^\\p{L}\\p{N}._-]"), "_"))
                            env.api.client.newCall(Request.Builder().url(env.media.url(d.id)).build()).execute().use { r ->
                                check(r.isSuccessful)
                                out.outputStream().use { r.body.byteStream().copyTo(it) }
                            }
                            out
                        }
                        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", f)
                        context.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, d.mime).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK))
                    } catch (_: Exception) {
                        toasts.error("فایل باز نشد.")
                    } finally {
                        busy = false
                    }
                }
            }
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        DIcon(DivanIcon.REPORT, tint = c.textSecondary)
        Column(Modifier.weight(1f)) {
            Text(d.name, style = Divan.type.small, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Fig(fileSize(d.size), style = Divan.type.figureSmall, color = c.textMuted)
        }
        if (busy) CircularProgressIndicator(Modifier.size(18.dp), color = c.goldInk, strokeWidth = 2.dp) else DIcon(DivanIcon.DOWNLOAD, size = 18.dp, tint = c.textSecondary)
    }
}
