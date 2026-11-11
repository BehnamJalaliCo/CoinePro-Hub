package com.coinepro.hq.ui.session

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.idleWatch
import com.coinepro.hq.core.data.idleWatchFa
import com.coinepro.hq.core.data.lastStepFa
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.LocalReducedMotion
import com.coinepro.hq.ui.live.rememberTicker

// Contract §41.3, §42 ⟨1.24⟩, design/LIVE_VIEWS.md SS-1 (the owner's complaint of 2026-11-08: work that silently stopped while the app
// still said «در جریان»). Beside a moving session's badge: «آخرین قدم ۷ دقیقه پیش» and a thin ring filling toward the hub's ten-minute
// idle sweep, advancing once a minute on the real clock (silver the first window, amber once the holder was woken, red past both). With
// animations removed the ring is its words: «۷ از ۱۰ دقیقه».

/** SS-1's stall watch for a session whose badge is [badge] and whose last step was at [lastStepAt]; nothing unless it is moving. */
@Composable
fun StallWatch(badge: String, lastStepAt: String?, modifier: Modifier = Modifier) {
    if (badge != "moving") return
    val c = Divan.colors
    val now = rememberTicker(60_000)
    val w = idleWatch(lastStepAt, now) ?: return
    val last = lastStepFa(lastStepAt, now) ?: return
    val reduced = LocalReducedMotion.current
    val ink = when (w.window) {
        0 -> c.silverInk
        1 -> c.warning
        else -> c.negative
    }
    Row(
        modifier.semantics(mergeDescendants = true) { contentDescription = "$last، ${idleWatchFa(w)}" },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        if (!reduced && w.minutes >= 1) Canvas(Modifier.size(12.dp)) {
            val st = 2.dp.toPx()
            val r = size.minDimension / 2 - st / 2
            drawCircle(c.lineDivider, r, style = Stroke(st))
            if (w.fraction > 0f) drawArc(
                ink, -90f, 360f * w.fraction, false, topLeft = Offset(center.x - r, center.y - r),
                size = androidx.compose.ui.geometry.Size(2 * r, 2 * r), style = Stroke(st, cap = StrokeCap.Round),
            )
        }
        Text(
            // The ring in words while it fills; past both windows the red «آخرین قدم …» says it alone.
            if (reduced && w.minutes >= 1 && w.window < 2) "$last · ${idleWatchFa(w)}" else last,
            style = Divan.type.micro, color = if (w.window >= 1) ink else c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis,
        )
    }
}
