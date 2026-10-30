package com.coinepro.hq.ui.media

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.media.HUB_TRANSCRIBING
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.rememberQuery

// ⟨1.9⟩ Contract §27.3: the hub's speech to text. Voice messages and voice notes carry the hub's own transcript (`transcript_fa`), the
// stream's `file.transcribed` refreshes them, and the owner can read the hub's words in place of the phone's («متن هاب»).

/** `/meta.speech.enabled`, shared with the voice inputs (they read it at each start); false until read. */
@Composable
fun rememberSpeechEnabled(): Boolean {
    val env = LocalEnv.current
    val meta = rememberQuery("meta", "meta", maxAgeMs = 300_000) { meta() }
    val m = meta.data
    LaunchedEffect(m) { if (m != null) env.media.speechEnabled = m.speech?.enabled }
    return m?.speech?.enabled == true
}

/** An audio file's `FileRef` with the hub's transcript (`GET /files/{id}/meta`), refreshed by `file.*` on the stream. Null while off. */
@Composable
fun rememberHubTranscript(fileId: String?, enabled: Boolean): FileRef? {
    if (fileId == null || !enabled) return null
    return rememberQuery("file:meta:$fileId", "files", maxAgeMs = 60_000) { fileMeta(fileId) }.data
}

/** Whether the hub is likely still turning a recent recording into words (within a quarter of an hour of [at]). */
fun hubStillWriting(at: String?): Boolean {
    val t = instant(at) ?: return false
    return com.coinepro.hq.core.format.HqClock.millis() - t.toEpochMilli() < 15 * 60_000L
}

/**
 * The «متن هاب» switch under a voice message or a voice note: on, the hub's transcript is shown in place of the phone's words; off, the
 * words as sent. Without a transcript yet (and [writing]) it says the hub is at it; with none and not writing it shows nothing.
 */
@Composable
fun HubTextToggle(hubText: String?, on: Boolean, onToggle: () -> Unit, writing: Boolean, modifier: Modifier = Modifier) {
    val c = Divan.colors
    when {
        hubText != null -> Row(
            modifier.clip(CircleShape).background(if (on) c.softGold else c.tile).clickable(role = Role.Switch, onClickLabel = if (on) "متن خود پیام" else "متن هاب") { onToggle() }
                .padding(horizontal = 10.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp),
        ) {
            DIcon(DivanIcon.MIC, size = 12.dp, tint = if (on) c.goldInk else c.textSecondary)
            Text(if (on) "متن هاب · برگرد به متن پیام" else "متن هاب", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = if (on) c.goldInk else c.textSecondary)
        }
        writing -> Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            CircularProgressIndicator(Modifier.size(10.dp), color = c.textMuted, strokeWidth = 1.5.dp)
            Text(HUB_TRANSCRIBING, style = Divan.type.micro, color = c.textMuted)
        }
    }
}
