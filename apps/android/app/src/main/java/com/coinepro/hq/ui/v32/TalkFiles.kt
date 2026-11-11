package com.coinepro.hq.ui.v32

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import com.coinepro.hq.core.media.FileKind
import com.coinepro.hq.core.media.fileSize
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.media.FileGlyph
import com.coinepro.hq.ui.media.Pending

// Contract §36.2 ⟨1.18⟩: the files on their way in a session's composer. Each one a chip above the words: its picture (or the mark of
// its kind), its name, its kind and size, how far it has gone, and ✕ (cancel while it goes, take it out once it is there). A file that
// failed says why in one plain line and goes again on a tap.

/** The chips of [items], in the order they were picked; drawn from their state only, so each state can be shown. */
@Composable
fun PendingFiles(items: List<Pending>, onRemove: (Pending) -> Unit, onRetry: (Pending) -> Unit, modifier: Modifier = Modifier) {
    if (items.isEmpty()) return
    Column(modifier.fillMaxWidth().padding(horizontal = 2.dp, vertical = 2.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        ScrollRow(spacing = 8.dp) { for (p in items) PendingChip(p, { onRemove(p) }, { onRetry(p) }) }
        val busy = items.count { it.state == "uploading" }
        val failed = items.count { it.state == "failed" }
        val line = when {
            failed > 0 -> "${faCount(failed)} فایل نرسید؛ رویش بزن تا دوباره برود، یا برش دار."
            busy > 0 -> "${faCount(busy)} فایل در راه است؛ بعد از رسیدن میفرستی."
            else -> "${faCount(items.size)} فایل همراه حرف بعدی‌ات میرود؛ بدون نوشتن هم میشود فرستاد."
        }
        Text(line, style = Divan.type.micro, color = if (failed > 0) Divan.colors.negative else Divan.colors.textMuted, modifier = Modifier.padding(horizontal = 4.dp))
    }
}

/** Persian digits for a count in a sentence. */
internal fun faCount(n: Int): String = n.toString().map { if (it in '0'..'9') '۰' + (it - '0') else it }.joinToString("")

@Composable
private fun PendingChip(p: Pending, onRemove: () -> Unit, onRetry: () -> Unit) {
    val c = Divan.colors
    val media = LocalEnv.current.media
    val kind = FileKind.ofKey(p.kind)
    val failed = p.state == "failed"
    val going = p.state == "uploading"
    val shape = RoundedCornerShape(12.dp)
    Column(
        Modifier.width(212.dp).clip(shape).background(c.tile)
            .border(1.dp, if (failed) c.negative.copy(alpha = 0.6f) else c.lineDivider, shape)
            .then(if (failed) Modifier.clickable(role = Role.Button, onClickLabel = "دوباره بفرست", onClick = onRetry) else Modifier),
    ) {
        Row(Modifier.padding(start = 8.dp, top = 8.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.size(40.dp).clip(RoundedCornerShape(10.dp)).background(c.raised), contentAlignment = Alignment.Center) {
                FileGlyph(kind, size = 20.dp)
                // A picture or a film shows itself over its mark (the mark stays when the phone cannot draw it).
                if (kind == FileKind.IMAGE || kind == FileKind.VIDEO) AsyncImage(p.file.uri, null, media.images, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                if (going) CircularProgressIndicator(progress = { p.progress }, modifier = Modifier.size(34.dp), color = c.goldInk, trackColor = c.lineStrong, strokeWidth = 2.5.dp)
                if (failed) DIcon(DivanIcon.REFRESH, size = 18.dp, tint = c.negative)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
                // A file's name keeps its Latin letters and digits («reels-2026.mp4»), as a figure inside the Persian line.
                Text(timesFig(p.file.name), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                    when {
                        failed -> Text(p.error ?: "نرسید", style = Divan.type.micro, color = c.negative, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        else -> {
                            Text(kind?.fa ?: "فایل", style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                            if (p.file.size > 0) Fig(fileSize(p.file.size), style = Divan.type.figureSmall, color = c.textMuted)
                            if (going) Fig("${(p.progress * 100).toInt()}%", style = Divan.type.figureSmall, color = c.silverInk)
                        }
                    }
                }
            }
            IconBtn(DivanIcon.CLOSE, if (going) "لغو فرستادن ${p.file.name}" else "برداشتن ${p.file.name}", onRemove, tint = c.textMuted)
        }
        // How far it has gone, along the chip's foot.
        if (going) Box(Modifier.fillMaxWidth().height(2.dp).background(c.lineDivider)) {
            Box(Modifier.fillMaxWidth(p.progress.coerceIn(0.02f, 1f)).height(2.dp).background(c.goldFill))
        }
    }
}
