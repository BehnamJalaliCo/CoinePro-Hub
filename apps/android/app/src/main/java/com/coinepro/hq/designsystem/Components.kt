package com.coinepro.hq.designsystem

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.GenericShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LocalContentColor
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.designsystem.generated.DivanIcon

// ------------------------------------------------------------------ tone --
/** Background and foreground of a tone (status colours never carry meaning alone: always with words or an icon). */
@Composable
fun toneColors(t: Tone): Pair<Color, Color> {
    val c = Divan.colors
    return when (t) {
        Tone.NEUTRAL -> c.tile to c.textSecondary
        Tone.GOLD -> c.softGold to c.goldInk
        Tone.POS -> c.softPositive to c.positive
        Tone.NEG -> c.softNegative to c.negative
        Tone.WARN -> c.softWarning to c.warning
        Tone.LAPIS -> c.softLapis to c.lapis
        Tone.LEARN -> c.softLearning to c.learning
        Tone.SILVER -> c.silverInk.copy(alpha = 0.14f) to c.silverInk
    }
}

// ----------------------------------------------------------------- text --
/** Persian text with Latin figures inside: wrap figure runs with [fig]. The run is a left-to-right isolate
 *  (U+2066 … U+2069), so "+412 −188" or "$6–7" keep their order inside a right-to-left sentence. */
fun AnnotatedString.Builder.fig(text: String, color: Color? = null, weight: FontWeight? = null) {
    withStyle(SpanStyle(fontFamily = FigureFace, fontFeatureSettings = "tnum", color = color ?: Color.Unspecified, fontWeight = weight)) { append("\u2066$text\u2069") }
}

/** A clock time inside a sentence ("10:50", "08:00–09:30"): drawn with Latin digits like every figure, whatever face the sentence has. */
private val CLOCK = Regex("(?<![\\d:])\\d{1,2}:\\d{2}(?![\\d:])")

/**
 * A Latin run inside Persian text: a model name with its version ("GPT 5.5"), a path ("/opt/tradeyar"), a URL, a command, a version
 * ("v0.10.1"), an English phrase ("Never sleeping apps", "down: otel-collector, tempo"). It starts with a letter, `$ @ # / ~` or digits
 * glued to letters ("8GB", "2FA"), may hold spaces and Latin punctuation, ends on a letter, a digit, `%`, `/` or `$`, and has a letter
 * in it (a bare prose number stays Persian).
 */
private val LATIN_RUN = Regex("(?:[A-Za-z$@#/~]|\\d[\\d.,]*(?=[A-Za-z]))[A-Za-z0-9 ._%$/@:+#=~&?,'*\\\\-]*[A-Za-z0-9%/$]|[A-Za-z]")
/** A date written in figures ("2026-10-17", "1405/07/25"). */
private val DATE = Regex("(?<![\\d/-])\\d{4}[-/]\\d{1,2}[-/]\\d{1,2}(?![\\d/-])")
/** A count of tokens or dollars ("182400 توکن", "12 USD"): money and tokens are figures. */
private val COUNT = Regex("(?<![\\d.,])\\d[\\d,.]*(?=\\s?(?:توکن|USDT?\\b))")
/** ⟨1.0.1⟩ A signed amount ("+640", "-18", "−$3.20") at the start of a word, and a percent ("21%", "99.8%"): figures, sign and all. */
private val AMOUNT = Regex("(?<![^\\s(«])[+\\-−±]\\$?\\d[\\d.,]*%?|(?<![\\w.,:/])\\d[\\d.,]*%")
/** A bare number ("500", "≥ 80%", "2.4M"), for text whose every number is a figure ([bidi] with `numbers`). */
private val NUMBER = Regex("(?:[≥≤<>~±+−-]\\s?)?\\$?\\d[\\d.,/:]*(?:\\s?[%٪]|[KMBs](?![A-Za-z]))?")

private fun arabicLetter(ch: Char) = ch in '؀'..'ۿ' || ch in 'ݐ'..'ݿ' || ch in 'ﭐ'..'﻿'

/**
 * Where [text] must read left to right in Latin figures: its Latin runs, dates, counts of tokens or money, signed amounts, percents
 * and clock times ([numbers]: every number), in order and never overlapping (the longest first where two start together). A Latin
 * run's digits stay Latin («GPT 5.5», never «GPT ۵٫۵»).
 *
 * ⟨1.0.1⟩ C0.4, one token is one run, whatever it is made of: an amount and the unit after it («+640 USDT», «-18 USD», «2 GB»), a
 * letter and the digit glued to it («P0»), a date and its time. A slash that leads on to a Persian word («USDT/ماه») stays outside
 * the run, so it is drawn between the two and not at the run's far end.
 */
fun latinRanges(text: String, numbers: Boolean = false): List<IntRange> {
    val found = buildList {
        for (m in LATIN_RUN.findAll(text)) if (m.value.any { it in 'A'..'Z' || it in 'a'..'z' } || m.value.startsWith("$")) add(m.range)
        for (re in listOf(DATE, COUNT, CLOCK)) for (m in re.findAll(text)) add(m.range)
        // A mark that only ends the sentence stays outside the run ("+640.", "80%،").
        fun trimmed(r: IntRange): IntRange { var e = r.last; while (e > r.first && text[e] in ".,:/") e--; return r.first..e }
        for (m in AMOUNT.findAll(text)) add(trimmed(m.range))
        if (numbers) for (m in NUMBER.findAll(text)) add(trimmed(m.range))
    }.sortedWith(compareBy<IntRange>({ it.first }, { -it.last }))
    val out = mutableListOf<IntRange>()
    for (r0 in found) {
        var r = r0
        val prev = out.lastOrNull()
        if (prev != null && r.first <= prev.last) {
            // Overlapping: the earlier run takes what it lacks of the later one ("+640" and "640K").
            if (r.last > prev.last) out[out.lastIndex] = prev.first..r.last
            continue
        }
        // A bare number right before a Latin unit is part of it ("640 USDT", "2 GB", "5 GPT").
        if (text[r.first].let { it in 'A'..'Z' || it in 'a'..'z' }) {
            var i = r.first
            if (i > 0 && text[i - 1] == ' ') i--
            var j = i
            while (j > 0 && (text[j - 1] in '0'..'9' || ((text[j - 1] == '.' || text[j - 1] == ',') && j < i))) j--
            if (j < i && text[j] in '0'..'9' && (j == 0 || !(text[j - 1].isLetterOrDigit() || text[j - 1] in ".,:/-")) && (prev == null || j > prev.last)) r = j..r.last
        }
        // Two runs with one space (or nothing) between them are one ("-18 USD", "2026-10-17 14:00").
        val gap = if (prev == null) null else text.substring(prev.last + 1, r.first)
        if (prev != null && (gap == "" || gap == " ")) out[out.lastIndex] = prev.first..r.last else out += r
    }
    return out.map { r -> if (r.last > r.first && text[r.last] == '/' && r.last + 1 < text.length && arabicLetter(text[r.last + 1])) r.first until r.last else r }
}

/**
 * [text] as it reads inside a Persian line: every Latin run (and date, count, amount, clock) set as a figure inside a left-to-right
 * isolate (U+2066 … U+2069), so it keeps its order and its Latin digits; « · » between facts drawn as the hairline ([sep], unless
 * [seps] is off); a run already isolated is left as it is. [numbers]: every bare number is a figure too.
 */
fun AnnotatedString.Builder.bidi(text: String, color: Color? = null, numbers: Boolean = false, seps: Boolean = true) {
    var last = 0
    fun plain(s: String) = if (seps) appendWithSeps(s) else append(s)
    for (r in latinRanges(text, numbers)) {
        if (insideIsolate(text, r.first)) continue
        plain(text.substring(last, r.first))
        val run = text.substring(r.first, r.last + 1)
        // A bare number with its sign («≥ 80%») is drawn as it is; a run with words in it never splits at its spaces.
        fig(if (run.any { it in 'A'..'Z' || it in 'a'..'z' }) keepTogether(run) else run, color)
        last = r.last + 1
    }
    plain(text.substring(last))
}

/** A Latin run never splits at its spaces: each space is followed by a word joiner (U+2060, invisible; the face has no no-break space
 *  glyph), so «GPT 5.5» or a command stays whole on its line (a line break inside an isolate can reorder its neutral marks, «--name»
 *  drawn «name--»); a run longer than the line still breaks at its hyphens. ⟨1.0.1⟩ A long English passage (a sentence of an error, a
 *  log line) wraps at its spaces like any text. */
fun keepTogether(run: String): String = if (run.length > KEEP_MAX) run else run.replace(" ", " ⁠")
private const val KEEP_MAX = 64

/** [text] as it should read inside a Persian line: Latin runs isolated and Latin, clock times Latin, « · » as the hairline (see [bidi]). */
fun timesFig(text: String): AnnotatedString = buildAnnotatedString { bidi(text) }

/** Mixed text whose every number is a figure too (a KPI target «500 در 90 روز», «≥ 80%»); the words stay in their right-to-left order. */
fun figures(text: String): AnnotatedString = buildAnnotatedString { bidi(text, numbers = true) }

/** [text] with its Latin runs and clock times isolated and set as figures; the spans it already has are kept, and runs already isolated
 *  (inside U+2066 … U+2069) are left as they are. */
fun timesFig(text: AnnotatedString): AnnotatedString {
    val ranges = latinRanges(text.text).filter { r -> !insideIsolate(text.text, r.first) }
    if (ranges.isEmpty()) return text
    return buildAnnotatedString {
        var last = 0
        for (r in ranges) {
            append(text.subSequence(last, r.first))
            withStyle(SpanStyle(fontFamily = FigureFace, fontFeatureSettings = "tnum")) { append("⁦"); append(keepTogether(text.text.substring(r.first, r.last + 1))); append("⁩") }
            last = r.last + 1
        }
        append(text.subSequence(last, text.length))
    }
}

/** Whether [at] lies inside an isolate already (an LRI/FSI/RLI not yet closed before it). */
private fun insideIsolate(t: String, at: Int): Boolean {
    if ('⁦' !in t && '⁧' !in t && '⁨' !in t) return false
    var depth = 0
    for (i in 0 until at) when (t[i]) { '⁦', '⁧', '⁨' -> depth++; '⁩' -> if (depth > 0) depth-- }
    return depth > 0
}

/** A figure (money, tokens, codes, model names): Latin digits, tabular, read left to right. ⟨1.0.1⟩ On one line it is never cut with
 *  «…»: it shrinks to fit its box ([FitText]). */
@Composable
fun Fig(text: String, modifier: Modifier = Modifier, style: TextStyle = Divan.type.figure, color: Color = LocalContentColor.current, maxLines: Int = 1) {
    if (maxLines == 1) FitText(AnnotatedString(text), modifier, style.copy(textDirection = TextDirection.Ltr), color, wrap = false)
    else Text(AnnotatedString(text), modifier, style = style.copy(textDirection = TextDirection.Ltr), color = color, maxLines = maxLines, overflow = TextOverflow.Ellipsis)
}

// ---------------------------------------------------------------- button --
enum class BtnVariant { PRIMARY, SECONDARY, SILVER, TEXT, DANGER, GHOST }
enum class BtnSize(val height: Dp, val pad: Dp, val font: Int, val icon: Dp, val radius: Dp) {
    SM(32.dp, 12.dp, 12, 16.dp, 8.dp), MD(40.dp, 16.dp, 13, 18.dp, 10.dp), LG(48.dp, 18.dp, 14, 20.dp, 10.dp)
}

/** Buttons (D1): gold = the owner's authority, one primary action per view. ⟨1.0.1⟩ C0.1 «یک طلای پُر در هر صفحه»: [BtnVariant.PRIMARY] is
 *  the ONLY filled gold of the app, and a screen (or an open sheet) shows at most one of it; the second and later actions of a list are
 *  [BtnVariant.SECONDARY] (outlined). A small text action («کپی», «همه», «برگردان») is silver. Every button sinks under the finger (M16). */
@Composable
fun HqButton(
    text: String?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    variant: BtnVariant = BtnVariant.SECONDARY,
    size: BtnSize = BtnSize.MD,
    icon: DivanIcon? = null,
    loading: Boolean = false,
    enabled: Boolean = true,
    label: String? = null,
) {
    val c = Divan.colors
    val src = remember { MutableInteractionSource() }
    val pressed by src.collectIsPressedAsState()
    val on = enabled && !loading
    val (bg, fg, border) = when (variant) {
        BtnVariant.PRIMARY -> Triple(if (!enabled) c.disabledFill else if (pressed) c.goldDeep else c.goldFill, if (!enabled) c.disabledText else c.onGold, null)
        BtnVariant.SECONDARY -> Triple(if (pressed) c.pressed else Color.Transparent, if (!enabled) c.disabledText else c.textPrimary, if (!enabled) c.lineDivider else c.lineStrong)
        BtnVariant.SILVER -> Triple(if (!enabled) c.disabledFill else c.silverInk.copy(alpha = if (pressed) 0.24f else 0.14f), if (!enabled) c.disabledText else c.silverInk, null)
        BtnVariant.TEXT -> Triple(if (pressed) c.silverInk.copy(alpha = 0.14f) else Color.Transparent, if (!enabled) c.disabledText else c.silverInk, null)
        BtnVariant.DANGER -> Triple(if (pressed) c.softNegative else Color.Transparent, if (!enabled) c.disabledText else c.negative, if (!enabled) c.lineDivider else c.negative.copy(alpha = 0.45f))
        BtnVariant.GHOST -> Triple(if (pressed) c.pressed else Color.Transparent, if (!enabled) c.disabledText else c.textSecondary, null)
    }
    val bgA by animateColorAsState(bg, motionShort(), label = "btn")
    val shape = RoundedCornerShape(size.radius)
    Row(
        modifier
            .heightIn(min = size.height)
            .pressScale(src)
            .clip(shape)
            .background(bgA)
            .then(if (border != null) Modifier.border(1.dp, border, shape) else Modifier)
            .clickable(src, indication = null, enabled = on, role = Role.Button, onClickLabel = label, onClick = onClick)
            .padding(horizontal = size.pad),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
    ) {
        CompositionLocalProvider(LocalContentColor provides fg) {
            when {
                loading -> CircularProgressIndicator(Modifier.size(size.icon), color = fg, strokeWidth = 2.dp)
                icon != null -> DIcon(icon, size = size.icon)
            }
            if (text != null) {
                Text(
                    timesFig(text),
                    style = Divan.type.small.copy(fontSize = size.font.sp, fontWeight = if (variant == BtnVariant.PRIMARY) FontWeight.Bold else FontWeight.SemiBold),
                    color = fg,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

/** A round icon button with a 48dp touch target; [badge] shows a count (Persian digits). */
@Composable
fun IconBtn(icon: DivanIcon, label: String, onClick: () -> Unit, modifier: Modifier = Modifier, active: Boolean = false, badge: Int = 0, tint: Color? = null, flip: Boolean = false) {
    val c = Divan.colors
    val src = remember { MutableInteractionSource() }
    Box(
        modifier
            .size(44.dp)
            .pressScale(src, 0.92f)
            .clip(CircleShape)
            .clickable(src, androidx.compose.material3.ripple(bounded = true), role = Role.Button, onClickLabel = label, onClick = onClick)
            .semantics { contentDescription = label },
        contentAlignment = Alignment.Center,
    ) {
        DIcon(icon, Modifier.graphicsLayer { if (flip) scaleX = -1f }, size = 22.dp, tint = tint ?: if (active) c.textPrimary else c.textSecondary, active = active)
        if (badge > 0) Badge(badge, Modifier.align(Alignment.TopStart).padding(start = 4.dp, top = 4.dp))
    }
}

@Composable
fun Badge(n: Int, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Box(
        modifier.heightIn(min = 16.dp).widthIn(min = 16.dp).clip(CircleShape).background(c.page).border(1.dp, c.goldInk, CircleShape).padding(horizontal = 4.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(if (n > 99) "99+" else n.toString(), style = Divan.type.micro.copy(fontSize = 10.sp, lineHeight = 14.sp, fontWeight = FontWeight.Bold), color = c.goldInk)
    }
}

// ------------------------------------------------------------------ card --
/** A card (D1): one radius, no shadow, no border unless it is the gold «tahrir» line of the one thing that matters most on the page.
 *  A card that opens something sinks a little under the finger; [onLongClick] opens its actions. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun HqCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    tahrir: Boolean = false,
    color: Color = Divan.colors.card,
    padding: PaddingValues = PaddingValues(Space.md),
    radius: Dp = Radius.card,
    onLongClick: (() -> Unit)? = null,
    onClickLabel: String? = null,
    onLongClickLabel: String? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val shape = RoundedCornerShape(radius)
    val src = remember { MutableInteractionSource() }
    val haptics = rememberHaptics()
    Column(
        modifier
            .then(if (onClick != null || onLongClick != null) Modifier.pressScale(src) else Modifier)
            .clip(shape)
            .background(color)
            .then(if (tahrir) Modifier.border(1.dp, Divan.colors.lineTahrir, shape) else Modifier)
            .then(
                when {
                    onLongClick != null -> Modifier.combinedClickable(
                        src, androidx.compose.material3.ripple(), role = Role.Button, onClickLabel = onClickLabel, onLongClickLabel = onLongClickLabel,
                        onLongClick = { haptics.firm(); onLongClick() }, onClick = { onClick?.invoke() },
                    )
                    onClick != null -> Modifier.clickable(src, androidx.compose.material3.ripple(), role = Role.Button, onClickLabel = onClickLabel, onClick = onClick)
                    else -> Modifier
                },
            )
            .padding(padding),
        content = content,
    )
}

/** ⟨1.0.1⟩ The hairline of a selected chip, tab or switch: silver, never gold. */
@Composable
fun silverLine(): Color = Divan.colors.silverInk.copy(alpha = if (Divan.night) 0.42f else 0.46f)

// ------------------------------------------------------------------ pill --
@Composable
fun Pill(text: String, tone: Tone = Tone.NEUTRAL, modifier: Modifier = Modifier, icon: DivanIcon? = null, dot: Boolean = false, live: Boolean = false, figure: Boolean = false) {
    val (bg, fg) = toneColors(tone)
    // ⟨1.0.1⟩ C0.1: a warning carries its own sign, so its amber never reads as the owner's gold (in the day theme the two are close).
    val sign = icon ?: if (tone == Tone.WARN && !dot && !live) DivanIcon.URGENT else null
    Row(
        modifier.height(24.dp).clip(CircleShape).background(bg).padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(if (sign != null && icon == null) 4.dp else 6.dp),
    ) {
        if (sign != null) DIcon(sign, size = if (icon == null) 12.dp else 14.dp, tint = fg)
        if (dot || live) LiveDot(fg, live)
        Text(if (figure) AnnotatedString(text) else timesFig(text), style = (if (figure) Divan.type.figureSmall else Divan.type.caption).copy(fontWeight = FontWeight.SemiBold, fontSize = 12.sp), color = fg, maxLines = 1)
    }
}

/** A status dot; [live] breathes it (in the layer, so the loop never recomposes) — still when animations are removed. */
@Composable
fun LiveDot(color: Color, live: Boolean = true, size: Dp = 6.dp) {
    val b = rememberBreath(live, periodMs = 1600)
    Box(Modifier.size(size).graphicsLayer { alpha = 1f - 0.6f * b.value }.clip(CircleShape).background(color))
}

// ---------------------------------------------------------------- chips --
@Composable
fun FilterChip(text: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier, count: Int? = null, figure: Boolean = false) {
    val c = Divan.colors
    val shape = CircleShape
    // ⟨1.0.1⟩ C0.1: a selection is ivory on a raised surface with a silver hairline, never gold.
    val bg by animateColorAsState(if (selected) c.raised else Color.Transparent, motionShort(), label = "chip")
    val line by animateColorAsState(if (selected) silverLine() else c.lineStrong, motionShort(), label = "chip-line")
    val src = remember { MutableInteractionSource() }
    Row(
        modifier
            .height(32.dp)
            .pressScale(src)
            .clip(shape)
            .background(bg)
            .border(1.dp, line, shape)
            .selectable(selected, interactionSource = src, indication = androidx.compose.material3.ripple(), role = Role.Tab, onClick = onClick)
            .padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        // A figure (an hour, a code) reads in Latin digits left to right; prose in the text face.
        Text(if (figure) AnnotatedString(text) else timesFig(text), style = (if (figure) Divan.type.figureSmall.copy(textDirection = TextDirection.Ltr) else Divan.type.small).copy(fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal), color = if (selected) c.textPrimary else c.textSecondary)
        if (count != null) Text(count.toString(), style = Divan.type.caption, color = (if (selected) c.textPrimary else c.textSecondary).copy(alpha = 0.8f))
    }
}

data class SegOption<T>(val value: T, val label: String, val icon: DivanIcon? = null)

@Composable
fun <T> Segmented(options: List<SegOption<T>>, value: T, onChange: (T) -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Row(modifier.clip(RoundedCornerShape(Radius.control)).background(c.tile).padding(4.dp).selectableGroup()) {
        for (o in options) {
            val on = o.value == value
            val bg by animateColorAsState(if (on) c.raised else c.raised.copy(alpha = 0f), motionMedium(), label = "seg")
            Row(
                Modifier
                    .weight(1f)
                    .height(36.dp)
                    .clip(RoundedCornerShape(Radius.small))
                    .background(bg)
                    .then(if (on) Modifier.border(1.dp, silverLine(), RoundedCornerShape(Radius.small)) else Modifier)
                    .selectable(on, role = Role.RadioButton, onClick = { onChange(o.value) }),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.Center,
            ) {
                if (o.icon != null) {
                    DIcon(o.icon, size = 16.dp, tint = if (on) c.textPrimary else c.textSecondary)
                    Spacer(Modifier.width(6.dp))
                }
                Text(timesFig(o.label), style = Divan.type.small.copy(fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal), color = if (on) c.textPrimary else c.textSecondary)
            }
        }
    }
}

@Composable
fun HqSwitch(checked: Boolean, onChange: (Boolean) -> Unit, label: String, enabled: Boolean = true) {
    val c = Divan.colors
    val x = animateFloatAsState(if (checked) 1f else 0f, motionMedium(), label = "switch")
    // ⟨1.0.1⟩ C0.1: on = a silver knob on a lighter track (a switch is a setting, not the owner's act; never gold).
    val track by animateColorAsState(if (!enabled) c.disabledFill else if (checked) c.silverInk.copy(alpha = 0.32f) else c.tile, motionMedium(), label = "switch-track")
    Box(
        Modifier
            .size(width = 44.dp, height = 26.dp)
            .clip(CircleShape)
            .background(track)
            .then(if (enabled) Modifier.border(if (checked) 1.dp else 1.5.dp, if (checked) silverLine() else c.lineStrong, CircleShape) else Modifier)
            .toggleable(checked, enabled = enabled, role = Role.Switch, onValueChange = onChange)
            .semantics { contentDescription = label }
            .padding(3.dp),
    ) {
        val d = if (checked) 20.dp else 16.dp
        val rtl = androidx.compose.ui.platform.LocalLayoutDirection.current == LayoutDirection.Rtl
        Box(
            Modifier
                .align(Alignment.CenterStart)
                .offset(x = 2.dp)
                .graphicsLayer { translationX = (if (rtl) -1 else 1) * 16.dp.toPx() * x.value }
                .size(d)
                .clip(CircleShape)
                .background(if (!enabled) c.disabledText else if (checked) c.silverFill else c.textSecondary),
        )
    }
}

private val Octagon = GenericShape { s, _ ->
    val k = 0.3f
    moveTo(s.width * k, 0f); lineTo(s.width * (1 - k), 0f); lineTo(s.width, s.height * k); lineTo(s.width, s.height * (1 - k))
    lineTo(s.width * (1 - k), s.height); lineTo(s.width * k, s.height); lineTo(0f, s.height * (1 - k)); lineTo(0f, s.height * k); close()
}

/** Owner rating 1–10 (D1): numbered octagons. A count, so Persian digits. */
@Composable
fun RatingRow(value: Int, onChange: ((Int) -> Unit)?, modifier: Modifier = Modifier, size: Dp = 30.dp) {
    val c = Divan.colors
    Row(modifier.selectableGroup(), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
        for (n in 1..10) {
            val on = n <= value
            Box(
                Modifier
                    .size(size)
                    .clip(Octagon)
                    // ⟨1.0.1⟩ C0.1: filled gold is the primary action alone; a given score is silver.
                    .background(if (on) c.silverInk else c.tile)
                    .selectable(n == value, enabled = onChange != null, role = Role.RadioButton, onClick = { onChange?.invoke(n) })
                    .semantics { contentDescription = "$n از ۱۰" },
                contentAlignment = Alignment.Center,
            ) {
                Text(n.toString(), style = Divan.type.caption.copy(fontWeight = if (on) FontWeight.Bold else FontWeight.Normal, fontSize = if (size > 30.dp) 13.sp else 11.sp), color = if (on) c.page else c.textSecondary)
            }
        }
    }
}

// ----------------------------------------------------------------- meters --
enum class BarTone { SILVER, GOLD, WARN, NEG, POS }

/** Budget meter tone (D2·2): neutral silver below 70%, warn to 90%, negative above. */
fun budgetTone(pct: Double?): BarTone = when {
    pct == null || pct < 70 -> BarTone.SILVER
    pct < 90 -> BarTone.WARN
    else -> BarTone.NEG
}

@Composable
fun barColor(t: BarTone): Color = with(Divan.colors) {
    when (t) { BarTone.SILVER -> silverInk; BarTone.GOLD -> goldFill; BarTone.WARN -> warning; BarTone.NEG -> negative; BarTone.POS -> positive }
}

/** A meter: it fills to its value when it appears and when the value changes; the fill is drawn, so it never re-lays out. */
@Composable
fun MeterBar(pct: Double, modifier: Modifier = Modifier, tone: BarTone = BarTone.SILVER, height: Dp = 6.dp, color: Color? = null) {
    val target = (pct / 100.0).coerceIn(0.0, 1.0).toFloat()
    val reduced = LocalReducedMotion.current
    val v = remember { androidx.compose.animation.core.Animatable(if (reduced) target else 0f) }
    androidx.compose.runtime.LaunchedEffect(target, reduced) { v.animateTo(target, Motion.emphasised(reduced)) }
    val track = Divan.colors.tile
    val fill = color ?: barColor(tone)
    Box(
        modifier.fillMaxWidth().height(height).drawBehind {
            val r = CornerRadius(size.height / 2)
            drawRoundRect(track, cornerRadius = r)
            val w = (size.width * v.value).let { if (it > 0f) it.coerceIn(minOf(size.height, size.width), size.width) else 0f }
            if (w > 0f) drawRoundRect(fill, Offset(if (layoutDirection == LayoutDirection.Rtl) size.width - w else 0f, 0f), Size(w, size.height), r)
        },
    )
}

/** A placeholder the size of what is coming, with a soft shimmer that runs in the reading direction. The shimmer is drawn from one
 *  clock shared by the frame (not composed), and stands still when animations are removed. */
@Composable
fun Skeleton(modifier: Modifier = Modifier, radius: Dp = Radius.small) {
    val c = Divan.colors
    val reduced = LocalReducedMotion.current
    val x = if (reduced) remember { androidx.compose.runtime.mutableStateOf(0.5f) }
    else rememberInfiniteTransition(label = "skeleton").animateFloat(0f, 1f, infiniteRepeatable(tween(Motion.SHIMMER, easing = androidx.compose.animation.core.LinearEasing)), label = "skeleton")
    val base = c.skeleton
    val hi = c.skeletonHi
    Box(
        modifier
            .clip(RoundedCornerShape(radius))
            .drawWithCache {
                val band = 260.dp.toPx()
                val rtl = layoutDirection == LayoutDirection.Rtl
                onDrawBehind {
                    drawRect(base)
                    if (!reduced) {
                        val span = size.width + 2 * band
                        val p = (if (rtl) 1f - x.value else x.value) * span - band
                        drawRect(Brush.horizontalGradient(listOf(base, hi, base), startX = p, endX = p + band))
                    }
                }
            },
    )
}

@Composable
fun Empty(title: String, modifier: Modifier = Modifier, icon: DivanIcon = DivanIcon.DELIVERABLE, body: String? = null, action: (@Composable () -> Unit)? = null) {
    val c = Divan.colors
    Column(modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 40.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(56.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) { DIcon(icon, size = 26.dp, tint = c.textMuted) }
        Text(timesFig(title), style = Divan.type.bodyStrong, textAlign = TextAlign.Center)
        if (body != null) Text(body, style = Divan.type.caption, color = c.textMuted, textAlign = TextAlign.Center)
        action?.invoke()
    }
}

@Composable
fun ErrorBlock(error: ApiException?, onRetry: (() -> Unit)?, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 32.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(56.dp).clip(CircleShape).background(c.softNegative), contentAlignment = Alignment.Center) {
            DIcon(if (error?.isOffline == true) DivanIcon.OFFLINE else DivanIcon.URGENT, size = 26.dp, tint = c.negative)
        }
        Text(error?.messageFa ?: "بارگذاری انجام نشد.", style = Divan.type.bodyStrong, textAlign = TextAlign.Center)
        if (error != null) Fig(error.code, style = Divan.type.figureSmall, color = c.textMuted)
        if (onRetry != null) HqButton("دوباره", onRetry, icon = DivanIcon.REFRESH)
    }
}

@Composable
fun StatTile(label: String, value: String, modifier: Modifier = Modifier, sub: String? = null, tone: Tone? = null, figure: Boolean = true, subRich: AnnotatedString? = null, onClick: (() -> Unit)? = null, subLines: Int = 1, count: Boolean = false) {
    val c = Divan.colors
    // Label, figure and note sit on the same lines in every tile of a row: one label line, one 32sp figure line, and the note
    // starting on the same baseline (the tile fills the row's height when the row is a [StatRow]).
    HqCard(if (LocalStatFill.current) modifier.fillMaxHeight() else modifier, onClick = onClick) {
        Text(timesFig(label), style = Divan.type.caption, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Spacer(Modifier.height(4.dp))
        val col = when (tone) { Tone.NEG -> c.negative; Tone.WARN -> c.warning; Tone.POS -> c.positive; else -> c.textPrimary }
        val big = (if (figure) Divan.type.figureL else Divan.type.h2).copy(fontSize = 24.sp, lineHeight = 32.sp)
        // ⟨1.0.1⟩ C0.4: a figure is never cut and never leaves its tile; it shrinks to fit.
        if (count) CountingText(value, big, color = col) else FitText(value, style = big, color = col)
        if (subRich != null) Text(subRich, style = Divan.type.caption, color = c.textMuted, maxLines = 2, minLines = subLines, overflow = TextOverflow.Ellipsis)
        else if (sub != null) Text(timesFig(sub), style = Divan.type.caption, color = c.textMuted, maxLines = 2, minLines = subLines, overflow = TextOverflow.Ellipsis)
    }
}

/** A row of [StatTile]s of one height: the tallest tile sets it and the others stretch, so their edges and lines align. */
@Composable
fun StatRow(modifier: Modifier = Modifier, gap: Dp = 12.dp, content: @Composable RowScope.() -> Unit) {
    Row(modifier.fillMaxWidth().height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(gap)) {
        CompositionLocalProvider(LocalStatFill provides true) { content() }
    }
}

/** Inside a [StatRow] a tile fills the row's height. */
internal val LocalStatFill = androidx.compose.runtime.staticCompositionLocalOf { false }

/** A section header, the same everywhere: the title (h3), an optional one-line note under it in muted ink, and an action at the
 *  end aligned with the title's line. */
@Composable
fun SectionTitle(title: String, modifier: Modifier = Modifier, note: String? = null, icon: DivanIcon? = null, action: (@Composable RowScope.() -> Unit)? = null) {
    val c = Divan.colors
    Row(modifier.fillMaxWidth().padding(top = Space.xxs), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
        if (icon != null) DIcon(icon, size = 20.dp, tint = c.textSecondary)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(timesFig(title), style = Divan.type.h3, modifier = Modifier.semantics { heading() })
            if (note != null) Text(timesFig(note), style = Divan.type.caption, color = c.textMuted)
        }
        action?.invoke(this)
    }
}

@Composable
fun PageHeader(title: String, modifier: Modifier = Modifier, eyebrow: String? = null, actions: (@Composable RowScope.() -> Unit)? = null) {
    val c = Divan.colors
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Column {
            if (eyebrow != null) Text(timesFig(eyebrow), style = Divan.type.caption, color = c.textMuted)
            Text(timesFig(title), style = Divan.type.h1, modifier = Modifier.semantics { heading() })
        }
        if (actions != null) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp), content = actions)
    }
}

/** One-line text field in the Divan style (tile fill; ⟨1.0.1⟩ a silver focus line: gold is the primary action alone). */
@Composable
fun HqTextField(
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    singleLine: Boolean = true,
    minLines: Int = 1,
    maxLength: Int = 5000,
    figure: Boolean = false,
) {
    val c = Divan.colors
    val src = remember { MutableInteractionSource() }
    val focused by src.collectIsFocusedAsState()
    BasicTextField(
        value = value,
        onValueChange = { if (it.length <= maxLength) onValueChange(it) },
        modifier = modifier,
        singleLine = singleLine,
        minLines = minLines,
        interactionSource = src,
        textStyle = (if (figure) Divan.type.figure else Divan.type.body).copy(color = c.textPrimary),
        cursorBrush = SolidColor(c.textPrimary),
        decorationBox = { inner ->
            Box(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(10.dp))
                    .background(c.tile)
                    .border(1.dp, if (focused) c.silverInk else c.lineStrong, RoundedCornerShape(10.dp))
                    .padding(horizontal = 12.dp, vertical = 12.dp),
            ) {
                // A figure field's example keeps Latin digits too ("W-000123", "2026-10-20 14:00").
                if (value.isEmpty()) Text(placeholder, style = if (figure) Divan.type.body.copy(fontFamily = FigureFace) else Divan.type.body, color = c.textMuted)
                inner()
            }
        },
    )
}

// ------------------------------------------------------------ scrolling --
/** A soft fade on the side of a sideways scroller that has more to show (the start side once it has scrolled, the end side while
 *  there is more), so a chip cut by the screen's edge reads as "more", not as clipped. Drawn, so scrolling never recomposes. */
fun Modifier.fadingEdges(scroll: androidx.compose.foundation.ScrollState, width: Dp = 28.dp): Modifier =
    graphicsLayer(compositingStrategy = androidx.compose.ui.graphics.CompositingStrategy.Offscreen).drawWithContent {
        drawContent()
        val w = width.toPx().coerceAtMost(size.width / 3)
        val rtl = layoutDirection == LayoutDirection.Rtl
        fun fade(atLeft: Boolean) {
            val x0 = if (atLeft) 0f else size.width - w
            val brush = Brush.horizontalGradient(
                if (atLeft) listOf(Color.Black, Color.Transparent) else listOf(Color.Transparent, Color.Black), startX = x0, endX = x0 + w,
            )
            drawRect(brush, Offset(x0, 0f), Size(w, size.height), blendMode = androidx.compose.ui.graphics.BlendMode.DstOut)
        }
        // horizontalScroll's 0 is the start: the right edge in right-to-left.
        if (scroll.value < scroll.maxValue) fade(atLeft = rtl)
        if (scroll.value > 0) fade(atLeft = !rtl)
    }

/** A row (chips, filters, tabs) that scrolls sideways when it does not fit the phone, with fading edges. */
@Composable
fun ScrollRow(modifier: Modifier = Modifier, spacing: Dp = Space.xs, content: @Composable RowScope.() -> Unit) {
    val scroll = androidx.compose.foundation.rememberScrollState()
    Row(
        modifier.fillMaxWidth().fadingEdges(scroll).horizontalScroll(scroll),
        horizontalArrangement = Arrangement.spacedBy(spacing),
        verticalAlignment = Alignment.CenterVertically,
        content = content,
    )
}

// ------------------------------------------------------------ technical details --
/**
 * ⟨1.0.1⟩ «جزئیات فنی»: where a command, a code, a host name or the machine's own words go, one tap away from the owner's page (they are
 * never on it). Closed at first; [open0] opens it (a screenshot).
 */
@Composable
fun TechDetails(text: String, modifier: Modifier = Modifier, title: String = "جزئیات فنی", open0: Boolean = false) {
    val c = Divan.colors
    var open by androidx.compose.runtime.saveable.rememberSaveable { androidx.compose.runtime.mutableStateOf(open0) }
    Column(modifier.fillMaxWidth()) {
        Row(
            Modifier.clip(RoundedCornerShape(Radius.small)).clickable(role = Role.Button, onClickLabel = if (open) "بستن" else "نمایش") { open = !open }.padding(horizontal = 4.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Chevron(open, tint = c.textMuted)
            Text(title, style = Divan.type.caption, color = c.textMuted)
        }
        Expand(open) {
            RichText(text, Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.control)).background(c.tile).padding(12.dp), style = Divan.type.caption, color = c.textSecondary)
        }
    }
}
