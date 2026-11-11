package com.coinepro.hq.designsystem

import android.content.Context
import android.database.ContentObserver
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.Easing
import androidx.compose.animation.core.FiniteAnimationSpec
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.InteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.material3.LocalContentColor
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.node.currentValueOf
import androidx.compose.ui.hapticfeedback.HapticFeedback
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToLong
import kotlinx.coroutines.launch

/**
 * Divan motion: three durations and two curves, used everywhere instead of ad-hoc values, so every part of the app moves with
 * one rhythm. Calm rather than lively: things settle, nothing bounces.
 *
 * - [SHORT] 120 ms — press feedback, colour and small state changes.
 * - [MEDIUM] 220 ms — expand and collapse, list items, a value that changes, screens of the same level.
 * - [EMPHASISED] 400 ms — what arrives: a screen pushed on top, a sheet's content, counters, a state that matters (stopped, sealed).
 *
 * [Standard] is the default curve; [Emphasised] decelerates long for things that arrive; [Exit] accelerates away.
 * The system's «remove animations» (animator duration scale 0) makes every state instant: [LocalReducedMotion] turns the specs
 * into snaps, transitions into none, and loops (pulses, orbits, shimmer) into still frames.
 */
object Motion {
    const val SHORT = 120
    const val MEDIUM = 220
    const val EMPHASISED = 400

    /** The Divan standard curve (design/tokens `motion.standard`). */
    val Standard: Easing = CubicBezierEasing(0.2f, 0f, 0f, 1f)
    /** Arrivals: a quick start and a long, gentle settle. */
    val Emphasised: Easing = CubicBezierEasing(0.05f, 0.7f, 0.1f, 1f)
    /** Exits accelerate away and do not linger. */
    val Exit: Easing = CubicBezierEasing(0.3f, 0f, 1f, 1f)

    /** Loops: a slow breath (glows, live pulses) and an orbit (work in progress). */
    const val BREATH = 1800
    const val ORBIT = 2800
    const val SHIMMER = 1400
    /** A particle's flight across the holding orbit (an order going out, a delivery coming back). */
    const val TRAVEL = 1600

    fun <T> short(reduced: Boolean = false): FiniteAnimationSpec<T> = if (reduced) snap() else tween(SHORT, easing = Standard)
    fun <T> medium(reduced: Boolean = false): FiniteAnimationSpec<T> = if (reduced) snap() else tween(MEDIUM, easing = Standard)
    fun <T> emphasised(reduced: Boolean = false): FiniteAnimationSpec<T> = if (reduced) snap() else tween(EMPHASISED, easing = Emphasised)
    fun <T> exit(reduced: Boolean = false): FiniteAnimationSpec<T> = if (reduced) snap() else tween(SHORT, easing = Exit)
}

/** True when the phone asks for no animations (Settings → Accessibility → Remove animations, or a 0× animator scale). */
val LocalReducedMotion = staticCompositionLocalOf { false }

private fun animationsOff(ctx: Context): Boolean = runCatching {
    Settings.Global.getFloat(ctx.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
}.getOrDefault(false)

/** The system setting, followed live (the owner can switch it while the app is open). */
@Composable
fun rememberSystemReducedMotion(): Boolean {
    val ctx = LocalContext.current
    var off by remember(ctx) { mutableStateOf(animationsOff(ctx)) }
    DisposableEffect(ctx) {
        val observer = object : ContentObserver(Handler(Looper.getMainLooper())) {
            override fun onChange(selfChange: Boolean) { off = animationsOff(ctx) }
        }
        val uri = Settings.Global.getUriFor(Settings.Global.ANIMATOR_DURATION_SCALE)
        runCatching { ctx.contentResolver.registerContentObserver(uri, false, observer) }
        onDispose { runCatching { ctx.contentResolver.unregisterContentObserver(observer) } }
    }
    return off
}

// --------------------------------------------------------------- specs --
@Composable fun <T> motionShort(): FiniteAnimationSpec<T> = Motion.short(LocalReducedMotion.current)
@Composable fun <T> motionMedium(): FiniteAnimationSpec<T> = Motion.medium(LocalReducedMotion.current)
@Composable fun <T> motionEmphasised(): FiniteAnimationSpec<T> = Motion.emphasised(LocalReducedMotion.current)

/** Content that opens and closes in place (a card's details, a form's extra fields). */
@Composable
fun expandIn(): EnterTransition =
    if (LocalReducedMotion.current) EnterTransition.None
    else expandVertically(tween(Motion.MEDIUM, easing = Motion.Standard), expandFrom = Alignment.Top) + fadeIn(tween(Motion.MEDIUM, delayMillis = 40, easing = Motion.Standard))

@Composable
fun collapseOut(): ExitTransition =
    if (LocalReducedMotion.current) ExitTransition.None
    else shrinkVertically(tween(Motion.MEDIUM, easing = Motion.Standard), shrinkTowards = Alignment.Top) + fadeOut(tween(Motion.SHORT, easing = Motion.Exit))

/** A container whose height follows its content smoothly (expand and collapse, a list that grows). */
fun Modifier.smoothSize(): Modifier = composed {
    if (LocalReducedMotion.current) this else animateContentSize(tween<IntSize>(Motion.MEDIUM, easing = Motion.Standard))
}

// --------------------------------------------------------------- press --
/** ⟨1.0.1⟩ M16 «فرورفتن»: how far a pressable surface sinks under the finger (2 %), in [Motion.SHORT] (120 ms). */
const val PRESS_SCALE = 0.98f

/** Press feedback (M16): the element sinks a little while pressed. The scale lives in the layer, so pressing never recomposes. A plain
 *  `clickable` needs nothing: the theme's indication ([PressIndication]) answers every touch the same way. */
fun Modifier.pressScale(source: InteractionSource, pressed: Float = PRESS_SCALE): Modifier = composed {
    val reduced = LocalReducedMotion.current
    val down by source.collectIsPressedAsState()
    val s = animateFloatAsState(if (down && !reduced) pressed else 1f, Motion.short(reduced), label = "press")
    graphicsLayer { scaleX = s.value; scaleY = s.value }
}

/**
 * ⟨1.0.1⟩ M16 for every pressable surface at once: the theme's indication ([DivanTheme] provides it as `LocalIndication`), so a row, a
 * card, a chip or a tab made with a plain `clickable` / `selectable` / `toggleable` sinks to [PRESS_SCALE] and back in 120 ms, with the
 * usual ripple. No touch is left without an answer, and no screen has to ask for it. Instant when animations are removed.
 */
object PressIndication : androidx.compose.foundation.IndicationNodeFactory {
    override fun create(interactionSource: InteractionSource): androidx.compose.ui.node.DelegatableNode = PressNode(interactionSource)
    override fun equals(other: Any?): Boolean = other === this
    override fun hashCode(): Int = 16
}

private class PressNode(private val source: InteractionSource) :
    androidx.compose.ui.node.DelegatingNode(), androidx.compose.ui.node.DrawModifierNode, androidx.compose.ui.node.CompositionLocalConsumerModifierNode {
    // The platform ripple itself (the same one Material's `ripple()` draws, in the content colour), owned here so that its drawing
    // and the content's sink together in one draw.
    private val ripple = delegate(
        androidx.compose.material.ripple.createRippleModifierNode(
            source, bounded = true, radius = Dp.Unspecified,
            color = { currentValueOf(LocalContentColor) },
            rippleAlpha = { androidx.compose.material3.RippleDefaults.RippleAlpha },
        ),
    )
    private val scale = Animatable(1f)

    override fun onAttach() {
        coroutineScope.launch {
            var down = 0
            source.interactions.collect { i ->
                when (i) {
                    is androidx.compose.foundation.interaction.PressInteraction.Press -> down++
                    is androidx.compose.foundation.interaction.PressInteraction.Release, is androidx.compose.foundation.interaction.PressInteraction.Cancel -> down = (down - 1).coerceAtLeast(0)
                    else -> return@collect
                }
                val reduced = currentValueOf(LocalReducedMotion)
                val to = if (down > 0 && !reduced) PRESS_SCALE else 1f
                launch { if (reduced) scale.snapTo(1f) else scale.animateTo(to, tween(Motion.SHORT, easing = Motion.Standard)) }
            }
        }
    }

    override fun androidx.compose.ui.graphics.drawscope.ContentDrawScope.draw() {
        val s = scale.value
        val content = this
        val inner = ripple as androidx.compose.ui.node.DrawModifierNode
        // The ripple's own draw draws the content once and then the ripple over it.
        if (s == 1f) with(inner) { content.draw() } else scale(s, s) { with(inner) { content.draw() } }
    }
}

// -------------------------------------------------------------- haptics --
/**
 * ⟨1.0.1⟩ M21 «لرزش»: three subtle haptics, each answering an act of the owner, never a passive update. Get it with [rememberHaptics].
 * - [tick]: one light tap (a step done, a selection, «خوانده شد»);
 * - [seal]: one heavier tap (an approval sent);
 * - [error]: two short taps (it did not happen).
 * [confirm], [firm] and [reject] are the older names of the same platform constants.
 */
@Stable
class Haptics(private val h: HapticFeedback) {
    /** One heavier tap: an approval was sent («تأیید», «باز کن», «انتشار»). */
    fun seal() = h.performHapticFeedback(HapticFeedbackType.LongPress)
    /** Two short taps: the act did not go through. */
    fun error() = h.performHapticFeedback(HapticFeedbackType.Reject)
    /** A light tick: marked seen, a toggle, a chip. */
    fun tick() = h.performHapticFeedback(HapticFeedbackType.SegmentTick)
    /** Done: sealed, saved, resumed. */
    fun confirm() = h.performHapticFeedback(HapticFeedbackType.Confirm)
    /** A firm one: something stopped, a hold reached. */
    fun firm() = h.performHapticFeedback(HapticFeedbackType.LongPress)
    /** It did not happen. */
    fun reject() = h.performHapticFeedback(HapticFeedbackType.Reject)
}

@Composable
fun rememberHaptics(): Haptics {
    val h = LocalHapticFeedback.current
    return remember(h) { Haptics(h) }
}

// --------------------------------------------------------------- M17 stagger --
/** ⟨1.0.1⟩ M17 «پله‌پله»: at most this many rows of a list settle one after another; the rest are simply there. */
const val STAGGER_ROWS = 8
/** The gap between one row's start and the next one's. */
const val STAGGER_MS = 30

/**
 * M17: the [index]th row of a list settles (M1: it fades in and rises 6 dp, 200 ms) [STAGGER_MS] after the one before, the first time
 * the list is shown; rows past [STAGGER_ROWS] and every row when animations are removed are simply in place. Put it on each row:
 * `Modifier.stagger(i)`. The motion lives in the layer, so it never re-lays out.
 */
fun Modifier.stagger(index: Int): Modifier = composed {
    if (LocalReducedMotion.current || index >= STAGGER_ROWS) return@composed this
    val p = remember { Animatable(0f) }
    LaunchedEffect(Unit) {
        // By the frame clock, so it follows the display and the test clock alike.
        if (index > 0) {
            val start = androidx.compose.runtime.withFrameNanos { it }
            while (androidx.compose.runtime.withFrameNanos { it } - start < index * STAGGER_MS * 1_000_000L) Unit
        }
        p.animateTo(1f, tween(Grammar.SETTLE_ROW, easing = Motion.Standard))
    }
    graphicsLayer {
        alpha = p.value
        translationY = (1f - p.value) * Grammar.RISE.toPx()
    }
}

// --------------------------------------------------------------- M18 collapse --
/**
 * ⟨1.0.1⟩ M18 «جمع شدن سربرگ»: how far a page's header has folded, 0 (open) to 1 (one line), from how far its list has scrolled:
 * the first [range] of scroll folds it. Read `.value` inside [CollapsingHeader] (or a layer); with animations removed it is 0 or 1.
 */
@Composable
fun rememberCollapse(list: androidx.compose.foundation.lazy.LazyListState, range: Dp = 72.dp): State<Float> {
    val px = with(androidx.compose.ui.platform.LocalDensity.current) { range.toPx() }
    val reduced = LocalReducedMotion.current
    return remember(list, px, reduced) {
        androidx.compose.runtime.derivedStateOf {
            val f = if (list.firstVisibleItemIndex > 0) 1f else (list.firstVisibleItemScrollOffset / px).coerceIn(0f, 1f)
            if (reduced) (if (f >= 0.5f) 1f else 0f) else f
        }
    }
}

/** The same for a page that scrolls as one column. */
@Composable
fun rememberCollapse(scroll: androidx.compose.foundation.ScrollState, range: Dp = 72.dp): State<Float> {
    val px = with(androidx.compose.ui.platform.LocalDensity.current) { range.toPx() }
    val reduced = LocalReducedMotion.current
    return remember(scroll, px, reduced) {
        androidx.compose.runtime.derivedStateOf {
            val f = (scroll.value / px).coerceIn(0f, 1f)
            if (reduced) (if (f >= 0.5f) 1f else 0f) else f
        }
    }
}

/**
 * M18: a header that folds to one line as its page scrolls. Put it ABOVE the list (not inside it): [full] is the open header, [line]
 * the one line it becomes; its height follows [fraction] (from [rememberCollapse]) between the two, [full] fading out as [line]
 * fades in. Nothing here animates on its own: it follows the finger.
 */
@Composable
fun CollapsingHeader(fraction: () -> Float, modifier: Modifier = Modifier, line: @Composable () -> Unit, full: @Composable () -> Unit) {
    androidx.compose.ui.layout.Layout(
        content = {
            Box(Modifier.graphicsLayer { alpha = (1f - fraction() * 1.6f).coerceIn(0f, 1f) }) { full() }
            Box(Modifier.graphicsLayer { alpha = ((fraction() - 0.4f) / 0.6f).coerceIn(0f, 1f) }) { line() }
        },
        modifier = modifier.clip(androidx.compose.ui.graphics.RectangleShape),
    ) { measurables, constraints ->
        val loose = constraints.copy(minHeight = 0, maxHeight = androidx.compose.ui.unit.Constraints.Infinity)
        val open = measurables[0].measure(loose)
        val folded = measurables[1].measure(loose)
        val f = fraction().coerceIn(0f, 1f)
        val h = (open.height + (folded.height - open.height) * f).toInt().coerceAtLeast(0)
        layout(constraints.maxWidth, h) {
            // Whichever cannot be seen is not placed, so it takes no touch.
            if (f < 1f) open.placeRelative(0, 0)
            if (f > 0f) folded.placeRelative(0, 0)
        }
    }
}

// ---------------------------------------------------------------- loops --
/** 0 → 1 → 0 over [periodMs], for a breathing glow or a calm pulse; still at [rest] when off or when animations are removed.
 *  Read it only inside draw or layer lambdas, so the loop redraws without recomposing. */
@Composable
fun rememberBreath(on: Boolean = true, periodMs: Int = Motion.BREATH, rest: Float = 0f): State<Float> {
    if (!on || LocalReducedMotion.current) return remember(rest) { mutableStateOf(rest) }
    return rememberInfiniteTransition(label = "breath").animateFloat(
        0f, 1f, infiniteRepeatable(tween(periodMs / 2, easing = Motion.Standard), RepeatMode.Reverse), label = "breath",
    )
}

/** 0 → 360 over [periodMs], for an orbit; still when off or when animations are removed. Read it in draw or layer lambdas. */
@Composable
fun rememberOrbit(on: Boolean = true, periodMs: Int = Motion.ORBIT): State<Float> {
    if (!on || LocalReducedMotion.current) return remember { mutableStateOf(0f) }
    return rememberInfiniteTransition(label = "orbit").animateFloat(0f, 360f, infiniteRepeatable(tween(periodMs, easing = LinearEasing)), label = "orbit")
}

// ------------------------------------------------------------- counters --
private val NUMBER = Regex("-?\\d[\\d,]*(?:\\.\\d+)?")

/**
 * A figure that counts to its value when it first appears and when it changes ("11", "$2.94", "160K"): the number inside the
 * text animates, the prefix and suffix stay. The final text is laid out underneath (invisible), so the width is reserved from the
 * first frame and nothing beside it moves while it counts.
 */
@Composable
fun CountingText(text: String, style: TextStyle, modifier: Modifier = Modifier, color: Color = LocalContentColor.current, maxLines: Int = 1) {
    val m = remember(text) { NUMBER.find(text) }
    val target = remember(m) { m?.value?.replace(",", "")?.toDoubleOrNull() }
    if (m == null || target == null || LocalReducedMotion.current) {
        Text(text, modifier, style = style, color = color, maxLines = maxLines, overflow = TextOverflow.Ellipsis)
        return
    }
    val decimals = m.value.substringAfter('.', "").length
    val grouped = ',' in m.value
    val anim = remember { Animatable(0f) }
    LaunchedEffect(target) { anim.animateTo(target.toFloat(), tween(Motion.EMPHASISED + 200, easing = Motion.Emphasised)) }
    Box(modifier) {
        Text(text, Modifier.alpha(0f), style = style, maxLines = maxLines)
        CountingValue(anim, text, m.range, decimals, grouped, target, style, color)
    }
}

@Composable
private fun CountingValue(anim: Animatable<Float, *>, text: String, range: IntRange, decimals: Int, grouped: Boolean, target: Double, style: TextStyle, color: Color) {
    val v = anim.value.toDouble()
    val shown = if (abs(v - target) < 1e-9) text else {
        val n = if (decimals == 0) String.format(Locale.US, if (grouped) "%,d" else "%d", v.roundToLong()) else String.format(Locale.US, if (grouped) "%,.${decimals}f" else "%.${decimals}f", v)
        text.replaceRange(range, n)
    }
    Text(shown, style = style, color = color, maxLines = 1)
}

// --------------------------------------------------------------- expand --
/** Content that opens and closes in place: it grows from the top and fades in, and folds away the same way (medium); it simply
 *  appears and disappears when animations are removed. */
@Composable
fun Expand(open: Boolean, modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    androidx.compose.animation.AnimatedVisibility(open, modifier, enter = expandIn(), exit = collapseOut()) { content() }
}

/** The chevron of an expander: it turns to point the way the content went. */
@Composable
fun Chevron(open: Boolean, size: androidx.compose.ui.unit.Dp = 14.dp, tint: Color = LocalContentColor.current) {
    val r = animateFloatAsState(if (open) 180f else 0f, motionMedium(), label = "chevron")
    DIcon(com.coinepro.hq.designsystem.generated.DivanIcon.CHEVRON, Modifier.graphicsLayer { rotationZ = r.value }, size = size, tint = tint)
}

// --------------------------------------------------------------- springs --
/** The one place the app springs: things that arrive by the owner's hand (a sheet's tiles), with a small, settled overshoot. Everything
 *  else keeps the calm curves above. */
object Springs {
    const val DAMPING = 0.68f
    val STIFFNESS = androidx.compose.animation.core.Spring.StiffnessMediumLow
    /** Frames between one item's start and the next one's (about 33 ms at 60 Hz). */
    const val STAGGER_FRAMES = 2
    /** Items after this many arrive together, so a long grid never keeps the owner waiting. */
    const val STAGGER_MAX = 14
}

/**
 * Arrives with a spring: it rises a little, grows from 90% and fades in, the [index]th item a couple of frames after the one before (frames,
 * not milliseconds, so it follows the display and the test clock alike). Still and in place when animations are removed. The motion
 * lives in the layer, so it never re-lays out.
 */
fun Modifier.springIn(index: Int): Modifier = composed {
    if (LocalReducedMotion.current) return@composed this
    val p = remember { Animatable(0f) }
    LaunchedEffect(Unit) {
        repeat(minOf(index, Springs.STAGGER_MAX) * Springs.STAGGER_FRAMES) { androidx.compose.runtime.withFrameNanos { } }
        p.animateTo(1f, androidx.compose.animation.core.spring(Springs.DAMPING, Springs.STIFFNESS))
    }
    graphicsLayer {
        val v = p.value
        alpha = v.coerceIn(0f, 1f)
        val s = 0.9f + 0.1f * v
        scaleX = s
        scaleY = s
        translationY = (1f - v) * 18.dp.toPx()
    }
}

// ======================================================================================================================================
// ⟨0.20.0⟩ The live views' motion grammar (design/LIVE_VIEWS.md §2, K-1): M1–M13, built once here and composed by every live view.
// Every motion maps to exactly one event (or to the real clock); nothing moves at rest; loops live only as long as the process they
// show. With «remove animations» ([LocalReducedMotion]) every primitive is an instant change, a loop a still glyph and a word, and a
// particle a tint on its edge with a «×n» chip (Particles.kt). When the app is hidden nothing is drawn ([rememberAppVisible]).
// ======================================================================================================================================

/** The grammar's durations (ms) and its ceremony curve. */
object Grammar {
    /** M1 settle: a new thing arrives (list rows: [SETTLE_ROW]). */
    const val SETTLE = 320
    const val SETTLE_ROW = 200
    /** M2 crossfade: a state, a label or a figure changes (figures never count up). */
    const val CROSSFADE = 200
    /** M3 ripple: one ring, once, when a node changes state. */
    const val RIPPLE = 600
    /** M4 particle: one event crossing one edge (proposed token `motion.duration.travel`). */
    const val TRAVEL = 900
    /** M5 work band and M6 breath: one loop. */
    const val LOOP = 1600
    /** M7 arc: one turn. */
    const val ARC = 1000
    /** M8 draw: a tick, an edge; a new node or edge is drawn as a small ceremony ([DRAW_NEW]). */
    const val DRAW = 320
    const val DRAW_NEW = 480
    /** M9 break: a link drops (reversed on reconnect). */
    const val BREAK = 320
    /** M10 ceremony: the owner acts (an order arrives, a seal). */
    const val CEREMONY = 480
    /** M11 reorder, M12 fill, M13 glint. */
    const val REORDER = 320
    const val FILL = 600
    const val GLINT = 600
    /** Rule 8: in reduced motion a particle becomes a tint on its edge for this long. */
    const val TINT = 1500
    /** Rule 4: particles per edge and animating elements per screen. */
    const val MAX_PER_EDGE = 3
    const val MAX_ANIMATING = 24
    /** M1's rise. */
    val RISE = 6.dp
    /** The ceremony curve (design/tokens `motion.ceremony`). */
    val Ceremony: Easing = CubicBezierEasing(0.3f, 0f, 0.1f, 1f)
    /** A particle through the hub (two legs) eases in and out. */
    val InOut: Easing = CubicBezierEasing(0.4f, 0f, 0.2f, 1f)
}

/** Whether the app is on screen: hidden, nothing is drawn and no loop runs (rule 7). */
@Composable
fun rememberAppVisible(): Boolean {
    val owner = androidx.lifecycle.compose.LocalLifecycleOwner.current
    val state by owner.lifecycle.currentStateFlow.collectAsState()
    return state.isAtLeast(androidx.lifecycle.Lifecycle.State.STARTED)
}

// --------------------------------------------------------------- M1 settle --
/** M1: arrives once — opacity 0 → 1 and 6 dp up into place (320 ms; 200 ms for a list row). Still when animations are removed. */
fun Modifier.settle(row: Boolean = false): Modifier = composed {
    if (LocalReducedMotion.current) return@composed this
    val p = remember { Animatable(0f) }
    LaunchedEffect(Unit) { p.animateTo(1f, tween(if (row) Grammar.SETTLE_ROW else Grammar.SETTLE, easing = Motion.Standard)) }
    graphicsLayer {
        alpha = p.value
        translationY = (1f - p.value) * Grammar.RISE.toPx()
    }
}

// --------------------------------------------------------------- M2 crossfade --
/** M2: [content] for [target], crossfading (200 ms) when it changes; instant when animations are removed. */
@Composable
fun <T> Crossfading(target: T, modifier: Modifier = Modifier, content: @Composable (T) -> Unit) {
    if (LocalReducedMotion.current) Box(modifier) { content(target) }
    else androidx.compose.animation.Crossfade(target, modifier, tween(Grammar.CROSSFADE, easing = Motion.Standard), label = "m2", content = content)
}

/** M2 for a colour (a node's ring, a badge's ink). */
@Composable
fun liveColor(target: Color): State<Color> =
    androidx.compose.animation.animateColorAsState(target, if (LocalReducedMotion.current) snap() else tween(Grammar.CROSSFADE, easing = Motion.Standard), label = "m2-colour")

// --------------------------------------------------------------- M3 ripple --
/** M3: one ring, 1 → 1.5× its node and .55 → 0, once each time [trigger] changes (not on first showing). Nothing when animations are removed. */
fun Modifier.rippleOnce(trigger: Any?, color: Color): Modifier = composed {
    if (LocalReducedMotion.current) return@composed this
    val p = remember { Animatable(1f) }
    var first by remember { mutableStateOf(true) }
    LaunchedEffect(trigger) {
        if (first) { first = false; return@LaunchedEffect }
        p.snapTo(0f)
        p.animateTo(1f, tween(Grammar.RIPPLE, easing = Motion.Standard))
    }
    drawBehind {
        val v = p.value
        if (v < 1f) drawCircle(color.copy(alpha = 0.55f * (1f - v)), radius = size.minDimension / 2 * (1f + 0.5f * v), style = androidx.compose.ui.graphics.drawscope.Stroke(1.5.dp.toPx()))
    }
}

/** M3 as a value for a canvas: 0 → 1 over the ripple each time [trigger] changes (1 at rest: nothing drawn). */
@Composable
fun rememberRipple(trigger: Any?): State<Float> {
    val p = remember { Animatable(1f) }
    if (LocalReducedMotion.current) return p.asState()
    var first by remember { mutableStateOf(true) }
    LaunchedEffect(trigger) {
        if (first) { first = false; return@LaunchedEffect }
        p.snapTo(0f)
        p.animateTo(1f, tween(Grammar.RIPPLE, easing = Motion.Standard))
    }
    return p.asState()
}

// --------------------------------------------------------------- M5 work band --
/**
 * M5: a 4 dp band moving (1.6 s loop) only while [on] (a run queued or running); nothing at rest. With animations removed: a still band
 * and [word] beside it («در حال انجام»).
 */
@Composable
fun WorkBand(on: Boolean, color: Color, modifier: Modifier = Modifier, height: Dp = 4.dp, word: String? = null) {
    val reduced = LocalReducedMotion.current
    val visible = rememberAppVisible()
    if (!on) { Box(modifier.height(height)); return }
    if (reduced || !visible) {
        Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Box(Modifier.weight(1f).height(height).clip(RoundedCornerShape(height / 2)).background(color.copy(alpha = 0.45f)))
            if (word != null) Text(word, style = Divan.type.micro, color = Divan.colors.textMuted)
        }
        return
    }
    val t = rememberInfiniteTransition(label = "m5").animateFloat(0f, 1f, infiniteRepeatable(tween(Grammar.LOOP, easing = LinearEasing)), label = "m5")
    Canvas(modifier.fillMaxWidth().height(height).clip(RoundedCornerShape(height / 2))) {
        val w = size.width
        val x = -w + 2 * w * t.value
        drawRect(
            Brush.horizontalGradient(listOf(Color.Transparent, color.copy(alpha = 0.9f), Color.Transparent), startX = x, endX = x + w),
        )
    }
}

// --------------------------------------------------------------- M6 breath --
/** M6: opacity .55 ↔ 1 (1.6 s) only while [on] (a model call in flight, the advisor listening); still at 1 when off or removed. */
fun Modifier.breath(on: Boolean): Modifier = composed {
    if (!on || LocalReducedMotion.current || !rememberAppVisible()) return@composed this
    val b = rememberInfiniteTransition(label = "m6").animateFloat(1f, 0.55f, infiniteRepeatable(tween(Grammar.LOOP / 2, easing = Motion.Standard), RepeatMode.Reverse), label = "m6")
    graphicsLayer { alpha = b.value }
}

/** One breath (600 ms) each time [trigger] changes, at most one in [minGapMs] (GL-1's dot on a byte from the hub). */
fun Modifier.beat(trigger: Any?, minGapMs: Long = 2_000): Modifier = composed {
    if (LocalReducedMotion.current) return@composed this
    val p = remember { Animatable(1f) }
    var last by remember { mutableStateOf(0L) }
    LaunchedEffect(trigger) {
        val now = android.os.SystemClock.uptimeMillis()
        if (trigger == null || now - last < minGapMs) return@LaunchedEffect
        last = now
        p.snapTo(1f)
        p.animateTo(0.55f, tween(Grammar.RIPPLE / 2, easing = Motion.Standard))
        p.animateTo(1f, tween(Grammar.RIPPLE / 2, easing = Motion.Standard))
    }
    graphicsLayer { alpha = p.value }
}

// --------------------------------------------------------------- M7 arc --
/**
 * M7: a 12 dp arc turning (1 s a turn) only while [on] (a step or a job runs). With animations removed: a still glyph (a ring with a dot)
 * and [word] beside it, when given.
 */
@Composable
fun Arc(on: Boolean, color: Color, modifier: Modifier = Modifier, size: Dp = 12.dp, word: String? = "در حال انجام") {
    if (!on) return
    val reduced = LocalReducedMotion.current || !rememberAppVisible()
    if (reduced) {
        Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Canvas(Modifier.size(size)) {
                val r = this.size.minDimension / 2 - 1.dp.toPx()
                drawCircle(color, r, style = androidx.compose.ui.graphics.drawscope.Stroke(1.5.dp.toPx()))
                drawCircle(color, r * 0.35f)
            }
            if (word != null) Text(word, style = Divan.type.micro, color = Divan.colors.textMuted, maxLines = 1)
        }
        return
    }
    val turn = rememberInfiniteTransition(label = "m7").animateFloat(0f, 360f, infiniteRepeatable(tween(Grammar.ARC, easing = LinearEasing)), label = "m7")
    Canvas(modifier.size(size).semantics { contentDescription = word ?: "در حال انجام" }) {
        val st = 1.6.dp.toPx()
        val r = this.size.minDimension / 2 - st
        drawArc(
            color, turn.value, 110f, false, topLeft = Offset(center.x - r, center.y - r), size = androidx.compose.ui.geometry.Size(2 * r, 2 * r),
            style = androidx.compose.ui.graphics.drawscope.Stroke(st, cap = StrokeCap.Round),
        )
    }
}

// --------------------------------------------------------------- M8 draw --
/** M8: a tick ([ok]) or a cross drawn in (320 ms) when it first shows; whole at once when animations are removed. */
@Composable
fun DrawnMark(ok: Boolean, color: Color, modifier: Modifier = Modifier, size: Dp = 12.dp) {
    val reduced = LocalReducedMotion.current
    val p = remember { Animatable(if (reduced) 1f else 0f) }
    LaunchedEffect(Unit) { if (!reduced) p.animateTo(1f, tween(Grammar.DRAW, easing = Motion.Standard)) }
    Canvas(modifier.size(size)) {
        val w = this.size.width
        val st = androidx.compose.ui.graphics.drawscope.Stroke(width = w * 0.16f, cap = StrokeCap.Round, join = androidx.compose.ui.graphics.StrokeJoin.Round)
        val path = Path().apply {
            if (ok) { moveTo(w * 0.14f, w * 0.55f); lineTo(w * 0.4f, w * 0.8f); lineTo(w * 0.88f, w * 0.22f) }
            else { moveTo(w * 0.2f, w * 0.2f); lineTo(w * 0.8f, w * 0.8f); moveTo(w * 0.8f, w * 0.2f); lineTo(w * 0.2f, w * 0.8f) }
        }
        if (p.value >= 1f) drawPath(path, color, style = st)
        else {
            val m = androidx.compose.ui.graphics.PathMeasure()
            m.setPath(path, false)
            val out = Path()
            m.getSegment(0f, m.length * p.value, out, true)
            drawPath(out, color, style = st)
        }
    }
}

// --------------------------------------------------------------- M9 break --
/** M9: how open a broken link's gap is, 0 (whole) → 1 (open), over 320 ms; closing again on reconnect. Instant when removed. */
@Composable
fun animateBreak(broken: Boolean): State<Float> =
    animateFloatAsState(if (broken) 1f else 0f, if (LocalReducedMotion.current) snap() else tween(Grammar.BREAK, easing = Motion.Standard), label = "m9")

// --------------------------------------------------------------- M10 ceremony --
/** M10: 0 → 1 over 480 ms (the ceremony curve) each time [trigger] changes, 1 at rest; always 1 when animations are removed (the state
 *  changes, nothing plays). Only the owner's acts. */
@Composable
fun rememberCeremony(trigger: Any?): State<Float> {
    val p = remember { Animatable(1f) }
    if (LocalReducedMotion.current) return p.asState()
    var first by remember { mutableStateOf(true) }
    LaunchedEffect(trigger) {
        if (first) { first = false; return@LaunchedEffect }
        p.snapTo(0f)
        p.animateTo(1f, tween(Grammar.CEREMONY, easing = Grammar.Ceremony))
    }
    return p.asState()
}

// --------------------------------------------------------------- M11 reorder --
/** M11: the placement spec of a lazy list's item when its order changes (320 ms); none when animations are removed. */
@Composable
fun reorderSpec(): FiniteAnimationSpec<androidx.compose.ui.unit.IntOffset>? =
    if (LocalReducedMotion.current) null else tween(Grammar.REORDER, easing = Motion.Standard)

// --------------------------------------------------------------- M12 fill --
/** M12: a meter's length following its real value (600 ms); it jumps when animations are removed. */
@Composable
fun animateFill(target: Float): State<Float> =
    animateFloatAsState(target, if (LocalReducedMotion.current) snap() else tween(Grammar.FILL, easing = Motion.Standard), label = "m12")

// --------------------------------------------------------------- M13 glint --
/**
 * M13: the tahrir under a headline figure, .3 → 1 → .3 once (600 ms) when [trigger] changes: [gold] when it concerns the owner, silver for
 * the agents' work. At rest a quiet gold hairline; never when animations are removed (the figure's crossfade carries it).
 */
@Composable
fun Glint(trigger: Any?, gold: Boolean, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val p = remember { Animatable(0.3f) }
    var first by remember { mutableStateOf(true) }
    val reduced = LocalReducedMotion.current
    LaunchedEffect(trigger) {
        if (first || reduced) { first = false; return@LaunchedEffect }
        p.snapTo(0.3f)
        p.animateTo(1f, tween(Grammar.GLINT * 2 / 5, easing = Motion.Standard))
        p.animateTo(0.3f, tween(Grammar.GLINT * 3 / 5, easing = Motion.Standard))
    }
    val ink = if (gold) c.goldInk else c.silverInk
    Box(modifier.fillMaxWidth().height(1.dp).background(if (p.value <= 0.31f) c.lineTahrir else ink.copy(alpha = p.value)))
}
