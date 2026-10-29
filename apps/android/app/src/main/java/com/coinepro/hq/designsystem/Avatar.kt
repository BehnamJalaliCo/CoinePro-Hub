package com.coinepro.hq.designsystem

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.DEPT_ICON
import com.coinepro.hq.designsystem.generated.DivanFixed
import com.coinepro.hq.designsystem.generated.DivanIcon
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin

/** The agent medallion (owner decision 2026-10-17): the ring says rank (1 ring employee, 2 manager, 2 + 8
 *  shamseh ticks CEO) and live state (comet = working, dim = asleep, warn, error); the glyph says the
 *  department. The owner is a gold disc with the CP monogram; the advisor is the orb; the Chief Overseer
 *  is the sentinel; the personal assistant wears its own glyph inside a double ring. */
@Composable
fun Avatar(kind: String, modifier: Modifier = Modifier, dept: String? = null, size: Dp = 40.dp, state: String = "idle", label: String? = null) {
    if (kind == "advisor") return Orb(size, modifier, label = label)
    if (kind == "overseer") return Sentinel(size, modifier, state = state, label = label)
    val c = Divan.colors
    if (kind == "owner") {
        Box(
            modifier
                .size(size)
                .clip(CircleShape)
                .background(c.goldFill)
                .drawBehind {
                    drawCircle(Color(0x590B0D14), radius = this.size.minDimension / 2 - max(3f, this.size.minDimension / 12), style = Stroke(1.dp.toPx()))
                }
                .semantics { contentDescription = label ?: "مدیر کل" },
            contentAlignment = Alignment.Center,
        ) { Monogram(size * 0.46f, ink = c.onGold) }
        return
    }
    val ring = when (state) { "error" -> c.negative; "waiting" -> c.warning; else -> c.silverInk }
    val ringA = if (state == "sleeping") 0.45f else 1f
    val glyph = when {
        kind == "ceo" -> DivanIcon.HOLDING
        kind == "inspector" -> DivanIcon.SEARCH
        kind == "assistant" -> DivanIcon.ASSISTANT
        else -> DEPT_ICON[dept] ?: DivanIcon.AGENT
    }
    // The comet turns in the draw phase only: a working agent never recomposes its row.
    val spin = rememberOrbit(state == "working", periodMs = 2400)
    Box(modifier.size(size).semantics { contentDescription = label ?: "ایجنت" }, contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(size)) {
            val s = this.size.minDimension
            val sw = (if (size < 56.dp) 1.5f else 1.8f).dp.toPx()
            val r = s / 2 - sw / 2
            drawCircle(c.tile, r)
            drawCircle(ring.copy(alpha = ringA), r, style = Stroke(sw))
            if (kind == "manager" || kind == "ceo" || kind == "inspector" || kind == "assistant") {
                drawCircle(ring.copy(alpha = 0.5f * ringA), r - max(3.dp.toPx(), s * 0.1f), style = Stroke(1.dp.toPx()))
            }
            if (kind == "ceo" && size >= 30.dp) {
                val r2 = r - max(2.5.dp.toPx(), s * 0.07f)
                for (k in 0 until 8) {
                    val a = (PI / 4 * k + PI / 8).toFloat()
                    drawLine(
                        ring.copy(alpha = ringA),
                        Offset(center.x + (r - 0.5f) * cos(a), center.y + (r - 0.5f) * sin(a)),
                        Offset(center.x + r2 * cos(a), center.y + r2 * sin(a)),
                        strokeWidth = 1.2.dp.toPx(), cap = StrokeCap.Round,
                    )
                }
            }
            if (state == "working") {
                rotate(spin.value) {
                    drawArc(c.textPrimary, -90f, 360f * 0.18f, false, topLeft = Offset(center.x - r, center.y - r), size = androidx.compose.ui.geometry.Size(2 * r, 2 * r), style = Stroke(sw + 0.4.dp.toPx(), cap = StrokeCap.Round))
                }
            }
        }
        DIcon(glyph, size = size * (if (kind == "ceo") 0.4f else 0.42f), tint = if (state == "sleeping") c.textMuted else c.silverInk)
    }
}

/** The Chief Overseer's sentinel (rank two, beside the advisor's orb): a silver sphere with a gold rim and the eye.
 *  It turns its gaze (a slow pulse) while working or waiting, and dims when the holding sleeps. */
@Composable
fun Sentinel(size: Dp, modifier: Modifier = Modifier, state: String = "idle", label: String? = null) {
    val c = Divan.colors
    val watching = state == "working" || state == "waiting"
    val k = rememberBreath(watching, periodMs = 2200)
    Box(
        modifier
            .size(size)
            .graphicsLayer {
                val s = 1f + 0.05f * k.value
                scaleX = s; scaleY = s
                alpha = if (state == "sleeping") 0.7f else 1f
            }
            .drawBehind {
                val r = this.size.minDimension / 2
                if (watching) drawCircle(c.goldFill.copy(alpha = 0.22f), r + 5.dp.toPx())
                drawCircle(
                    Brush.radialGradient(
                        0f to Color(0xFFF1F3F6), 0.46f to Color(0xFFB9C2CE), 1f to Color(0xFF5B6573),
                        center = Offset(this.size.width * 0.35f, this.size.height * 0.3f), radius = this.size.minDimension * 0.75f,
                    ),
                )
                val rim = max(1.5.dp.toPx(), this.size.minDimension / 28)
                drawCircle(c.goldFill, r - rim / 2, style = Stroke(rim))
            }
            .semantics { contentDescription = label ?: "ناظر کل" },
        contentAlignment = Alignment.Center,
    ) { DIcon(DivanIcon.OVERSEER, size = size * 0.52f, tint = Color(0xFF141821)) }
}

/** The advisor's orb: a gold sphere that breathes when listening (a soft gold glow swells and fades around it) and glows when
 *  thinking. The breath lives in the layer and the draw phase, so it never recomposes; it is still when animations are removed. */
@Composable
fun Orb(size: Dp, modifier: Modifier = Modifier, state: String = "rest", label: String? = null) {
    val breathe = state == "thinking" || state == "listening"
    val k = rememberBreath(breathe, periodMs = if (state == "thinking") 1600 else Motion.BREATH + 400)
    val listening = state == "listening"
    Box(
        modifier
            .size(size)
            .drawBehind {
                val r = this.size.minDimension / 2
                if (listening) {
                    // The breathing glow: two soft rings that swell with the breath.
                    val b = k.value
                    drawCircle(
                        Brush.radialGradient(
                            0.55f to DivanFixed.orbMid.copy(alpha = 0.34f * (0.55f + 0.45f * b)), 1f to DivanFixed.orbMid.copy(alpha = 0f),
                            center = center, radius = r * (1.18f + 0.22f * b),
                        ),
                        radius = r * (1.18f + 0.22f * b),
                    )
                }
            }
            .graphicsLayer { val s = 1f + 0.06f * k.value; scaleX = s; scaleY = s }
            .drawBehind {
                if (state == "thinking" || state == "speaking") drawCircle(DivanFixed.orbMid.copy(alpha = 0.18f), this.size.minDimension / 2 + 6.dp.toPx())
                drawCircle(
                    Brush.radialGradient(
                        0f to DivanFixed.orbLight, 0.48f to DivanFixed.orbMid, 1f to DivanFixed.orbDeep,
                        center = Offset(this.size.width * 0.35f, this.size.height * 0.3f), radius = this.size.minDimension * 0.75f,
                    ),
                )
            }
            .semantics { contentDescription = label ?: "مشاور کل" },
    )
}
