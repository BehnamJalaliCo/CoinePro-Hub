package com.coinepro.hq.designsystem

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.absoluteOffset
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameMillis
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.BurstLimiter
import com.coinepro.hq.core.data.faNum
import kotlin.math.hypot
import kotlinx.coroutines.delay

// design/LIVE_VIEWS.md §2 M4 and rules 4, 7, 8, 10: the particle layer. One per screen: one Canvas, driven by one frame loop that runs
// only while a particle is in flight; at most three in flight per edge and twenty-four on the screen (the rest fold into the edge's
// «×n» chip); with animations removed a particle is a 1.5 s tint on its edge plus the chip; with the app hidden nothing flies.

/** One particle: a 4 dp dot and two trail dots along [path] (px), [delayMs] after it was asked for (the hub's ceremony first). */
@Stable
class Flight internal constructor(val id: Long, val edge: String, val path: List<Offset>, val color: Color, val durationMs: Int, val delayMs: Int) {
    /** The frame time it set off (the first frame after its delay), or -1 before. */
    internal var start = -1L
    internal var asked = -1L
    val legs: Int get() = path.size - 1
}

/** An edge tinted for a while: a particle in reduced motion, or the chord along which a request travels through the hub. */
data class EdgeTint(val id: Long, val color: Color, val ms: Int = Grammar.TINT)

/** An edge's «×n»: where it sits (px), the edge's direction there (the chip sits beside the line, not on it) and its count. */
data class EdgeChip(val id: Long, val at: Offset, val n: Int, val dir: Offset = Offset(1f, 0f))

/**
 * The particle field of one screen. [fly] launches a particle along a path (or, reduced, tints its edge and counts it); the map reads
 * [tints] to colour its edges and [flying] to know an edge is in use. [hubPassing] is true while a two-leg particle crosses the hub
 * (its rim flickers once).
 */
@Stable
class ParticleField(val limiter: BurstLimiter = BurstLimiter(Grammar.MAX_PER_EDGE, Grammar.MAX_ANIMATING)) {
    internal val flights = mutableStateListOf<Flight>()
    val tints = mutableStateMapOf<String, EdgeTint>()
    internal val chips = mutableStateMapOf<String, EdgeChip>()
    /** The frame clock's last time (ms); the canvas draws from it. */
    internal var frame by mutableLongStateOf(0L)
    private var seq = 0L

    val active: Boolean get() = flights.isNotEmpty()

    /**
     * One event crossed [edge] along [path]: it flies, unless the edge already carries three or the screen twenty-four (it folds into the
     * chip at the path's middle), or animations are removed ([reduced]: the edge tints 1.5 s and the chip counts).
     */
    fun fly(edge: String, path: List<Offset>, color: Color, reduced: Boolean, delayMs: Int = 0) {
        if (path.size < 2) return
        val legs = path.size - 1
        if (reduced) {
            // Nothing flies: the edge tints and its chip counts every event on it.
            tints[edge] = EdgeTint(++seq, color)
            chips[edge] = chipOf(path, (chips[edge]?.n ?: 0) + 1)
            return
        }
        if (!limiter.admit(edge)) {
            chips[edge] = chipOf(path, limiter.chip(edge) ?: 1)
            return
        }
        flights += Flight(++seq, edge, path, color, if (legs > 1) Grammar.TRAVEL + 300 * (legs - 1) else Grammar.TRAVEL, delayMs)
    }

    /** Tint [edge] for a while (a chord glows while a request along it travels through the hub). */
    fun tint(edge: String, color: Color, ms: Int = Grammar.TINT) { tints[edge] = EdgeTint(++seq, color, ms) }

    fun flying(edge: String): Boolean = flights.any { it.edge == edge }

    /** Nothing flies or waits any more (the stream froze, the app was hidden: the state is applied at once). */
    fun stop() {
        for (f in flights) limiter.land(f.edge)
        flights.clear()
    }

    internal fun advance(now: Long) {
        frame = now
        val done = flights.filter { f ->
            if (f.asked < 0) f.asked = now
            if (f.start < 0 && now - f.asked >= f.delayMs) f.start = now
            f.start >= 0 && now - f.start >= f.durationMs
        }
        for (f in done) { flights.remove(f); limiter.land(f.edge) }
    }

    /** Whether a two-leg particle is crossing the hub now. */
    val hubPassing: Boolean get() = flights.any { f -> f.legs > 1 && f.start >= 0 && progress(f, frame).let { it in 0.46f..0.54f } }

    internal fun progress(f: Flight, now: Long): Float = if (f.start < 0) 0f else ((now - f.start).toFloat() / f.durationMs).coerceIn(0f, 1f)

    /** A chip on [path]: halfway along one edge; on a path through the hub, halfway along its second leg (not on the hub's seal). */
    private fun chipOf(path: List<Offset>, n: Int): EdgeChip {
        val t = if (path.size > 2) 0.75f else 0.45f
        val a = pointAt(path, (t - 0.02f).coerceAtLeast(0f))
        val b = pointAt(path, (t + 0.02f).coerceAtMost(1f))
        val d = b - a
        val len = hypot(d.x, d.y).takeIf { it > 0f } ?: 1f
        return EdgeChip(++seq, pointAt(path, t), n, Offset(d.x / len, d.y / len))
    }
}

/** The point [t] (0…1) of the way along [path] by length. */
fun pointAt(path: List<Offset>, t: Float): Offset {
    if (path.size == 1) return path[0]
    val seg = (1 until path.size).map { i -> hypot(path[i].x - path[i - 1].x, path[i].y - path[i - 1].y) }
    val total = seg.sum().takeIf { it > 0f } ?: return path.first()
    var d = t.coerceIn(0f, 1f) * total
    for (i in seg.indices) {
        if (d <= seg[i] || i == seg.lastIndex) {
            val k = if (seg[i] > 0f) (d / seg[i]).coerceIn(0f, 1f) else 1f
            return path[i] + (path[i + 1] - path[i]) * k
        }
        d -= seg[i]
    }
    return path.last()
}

/**
 * The one particle layer of a screen, over the map's edges: it runs a frame loop only while a particle is in flight and draws nothing
 * when the app is hidden or [frozen] (the stream is not live: particles stop, rule 7 and §5's truth rules). The «×n» chips sit at their
 * edge's middle and fade 1.8 s after the last fold; a tint ends after its time.
 */
@Composable
fun BoxScope.ParticleLayer(field: ParticleField, frozen: Boolean, modifier: Modifier = Modifier) {
    val visible = rememberAppVisible()
    val running = field.active && visible && !frozen
    LaunchedEffect(running) {
        if (!running) { if (frozen || !visible) field.stop(); return@LaunchedEffect }
        while (field.active) withFrameMillis { field.advance(it) }
    }
    if (visible && !frozen && field.active) Canvas(modifier.fillMaxSize()) {
        val now = field.frame
        for (f in field.flights) {
            if (f.start < 0) continue
            val p = field.progress(f, now)
            val e = if (f.legs > 1) Grammar.InOut.transform(p) else Motion.Standard.transform(p)
            val r = 2.dp.toPx()
            drawCircle(f.color.copy(alpha = 0.3f), r * 0.42f, pointAt(f.path, (e - 0.07f).coerceAtLeast(0f)))
            drawCircle(f.color.copy(alpha = 0.55f), r * 0.62f, pointAt(f.path, (e - 0.035f).coerceAtLeast(0f)))
            drawCircle(f.color, r, pointAt(f.path, e))
        }
    }
    // The tints end after their time (a state, not a motion: it simply goes).
    for ((edge, t) in field.tints.toList()) key(edge, t.id) {
        LaunchedEffect(t.id) { delay(t.ms.toLong()); if (field.tints[edge]?.id == t.id) field.tints.remove(edge) }
    }
}

/**
 * The «×n» chips of a particle field, above the map's nodes: each beside its edge (14 dp off the line, never on a node's seal), gone
 * 1.8 s after the last event it counted.
 */
@Composable
fun BoxScope.ParticleChips(field: ParticleField) {
    val density = LocalDensity.current
    for ((edge, ch) in field.chips.toList()) key(edge) {
        LaunchedEffect(ch.id) { delay(CHIP_MS); if (field.chips[edge]?.id == ch.id) { field.chips.remove(edge); field.limiter.clearChip(edge) } }
        // Beside the line: along its normal, on the side away from the screen's centre line.
        val side = with(density) { 14.dp.toPx() }
        val at = ch.at + Offset(-ch.dir.y, ch.dir.x) * side
        val x = with(density) { at.x.toDp() }
        val y = with(density) { at.y.toDp() }
        Box(Modifier.absoluteOffset(x = x - 14.dp, y = y - 10.dp).clip(CircleShape).background(Divan.colors.raised).padding(horizontal = 6.dp, vertical = 1.dp)) {
            Text("×" + faNum(ch.n), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold, textDirection = androidx.compose.ui.text.style.TextDirection.Ltr), color = Divan.colors.textPrimary, maxLines = 1)
        }
    }
}

/** A chip stays this long after the last event it counted. */
private const val CHIP_MS = 1_800L
