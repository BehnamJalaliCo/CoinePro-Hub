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
import androidx.compose.foundation.interaction.InteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.Text
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
/** Press feedback: the element sinks a little while pressed. The scale lives in the layer, so pressing never recomposes. */
fun Modifier.pressScale(source: InteractionSource, pressed: Float = 0.97f): Modifier = composed {
    val reduced = LocalReducedMotion.current
    val down by source.collectIsPressedAsState()
    val s = animateFloatAsState(if (down && !reduced) pressed else 1f, Motion.short(reduced), label = "press")
    graphicsLayer { scaleX = s.value; scaleY = s.value }
}

// -------------------------------------------------------------- haptics --
/** Light haptics for the actions that matter (seal, stop, mark seen); nothing for ordinary taps. */
@Stable
class Haptics(private val h: HapticFeedback) {
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
