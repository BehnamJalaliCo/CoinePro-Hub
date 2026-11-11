package com.coinepro.hq.designsystem

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

// ⟨1.0.1⟩ Part C: the one ring of the look, and the tiny line of a series.
//
// - [Ring]: a share as an arc with something in its middle: a Claude account's window (the treasury), a deadline that empties (a
//   notification), and, in phase 2, the build ring of a workshop turn (elapsed time out of its cap, the minute in the middle).
//   `Ring(value = 0.62f, tone = RingTone.SILVER, live = calling) { Fig("62%") }`. It moves only for a reason: the arc follows its real
//   value (M12), and a small arc turns on it (M7) only while [live] says work is going on. `value = null`: unknown, only the track.
// - [Spark]: the last points of a figure as a small line, no axis; nothing is drawn for fewer than two points.
// - A tick that draws itself (M8) is [DrawnMark] (Motion.kt).

enum class RingTone { SILVER, GOLD, WARN, NEAR, NEG, MUTED }

/** The ink of a tone. [RingTone.NEAR] is red-amber: beside the gold of a page it must never read as gold. */
@Composable
fun ringColor(tone: RingTone): Color = with(Divan.colors) {
    when (tone) {
        RingTone.SILVER -> silverInk
        RingTone.GOLD -> goldInk
        RingTone.WARN -> warning
        RingTone.NEAR -> lerp(warning, negative, 0.45f)
        RingTone.NEG -> negative
        RingTone.MUTED -> lineStrong
    }
}

/**
 * [value]: the share drawn, 0..1 (null: unknown, only the track). [live]: a small arc turns on the ring while a call is in flight
 * (still when animations are removed). [broken]: the track is dashed (a thing that is off or stuck). The middle is [content].
 */
@Composable
fun Ring(
    value: Float?,
    modifier: Modifier = Modifier,
    size: Dp = 72.dp,
    stroke: Dp = 5.dp,
    tone: RingTone = RingTone.SILVER,
    live: Boolean = false,
    broken: Boolean = false,
    label: String? = null,
    content: @Composable () -> Unit = {},
) {
    val c = Divan.colors
    val ink = ringColor(tone)
    val track = c.raised
    val v = value?.takeIf { it.isFinite() }?.coerceIn(0f, 1f)
    val shown by animateFill(v ?: 0f)
    val reduced = LocalReducedMotion.current
    val turning = live && !reduced && rememberAppVisible()
    val turn = if (turning) rememberInfiniteTransition(label = "ring").animateFloat(0f, 360f, infiniteRepeatable(tween(Grammar.ARC * 2, easing = LinearEasing)), label = "ring")
    else remember { mutableStateOf(0f) }
    val liveInk = c.textPrimary.copy(alpha = 0.7f)
    Box(modifier.size(size).then(if (label != null) Modifier.semantics(mergeDescendants = true) { contentDescription = label } else Modifier), contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(size)) {
            val w = stroke.toPx()
            val r = this.size.minDimension / 2 - w / 2
            val tl = Offset(center.x - r, center.y - r)
            val box = Size(2 * r, 2 * r)
            drawCircle(track, r, style = Stroke(w, pathEffect = if (broken) PathEffect.dashPathEffect(floatArrayOf(3.dp.toPx(), 5.dp.toPx())) else null))
            if (v != null && shown > 0f) drawArc(ink, -90f, 360f * shown, false, tl, box, style = Stroke(w, cap = StrokeCap.Round))
            if (live) rotate(turn.value) {
                drawArc(liveInk, -90f, 58f, false, tl, box, style = Stroke((w - 2.5.dp.toPx()).coerceAtLeast(1.5.dp.toPx()), cap = StrokeCap.Round))
            }
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) { content() }
    }
}

/** A tiny line of a series (the last 24 hours of a figure): no axis, no dots, the last point marked. Drawn left to right, oldest first. */
@Composable
fun Spark(series: List<Double>?, modifier: Modifier = Modifier, width: Dp = 44.dp, height: Dp = 16.dp, gold: Boolean = false, label: String? = null) {
    val s = series.orEmpty().filter { it.isFinite() }
    if (s.size < 2) return
    val c = Divan.colors
    val ink = if (gold) c.goldInk else c.silverInk
    Canvas(modifier.size(width, height).then(if (label != null) Modifier.semantics { contentDescription = label } else Modifier)) {
        val pad = 2.dp.toPx()
        val min = s.min()
        val span = (s.max() - min).takeIf { it > 0 } ?: 1.0
        val pts = s.mapIndexed { i, y -> Offset(pad + i * (size.width - 2 * pad) / (s.size - 1), size.height - pad - ((y - min) / span).toFloat() * (size.height - 2 * pad)) }
        val path = androidx.compose.ui.graphics.Path().apply { moveTo(pts[0].x, pts[0].y); for (p in pts.drop(1)) lineTo(p.x, p.y) }
        drawPath(path, ink.copy(alpha = 0.75f), style = Stroke(1.4.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
        drawCircle(ink, 1.8.dp.toPx(), pts.last())
    }
}
