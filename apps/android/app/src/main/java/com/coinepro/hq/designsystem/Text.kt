package com.coinepro.hq.designsystem

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.InlineTextContent
import androidx.compose.foundation.text.TextAutoSize
import androidx.compose.foundation.text.appendInlineContent
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.LocalTextStyle
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.Placeholder
import androidx.compose.ui.text.PlaceholderVerticalAlign
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp

// ⟨1.0.1⟩ Part C, numbers and text (C0.4). The one place every text of the app passes through, so every screen gains:
//
// - [Text]: the app's `Text`. Every screen imports THIS one (`com.coinepro.hq.designsystem.Text`), never Material's. A plain string is
//   shaped before it is drawn ([shape]): each Latin token inside Persian (money, a percent, a ref like O-000152, P0, a file name, a
//   handle) becomes one isolated left-to-right run in Latin tabular digits, and « · » between two facts becomes the hairline
//   ([sep]); a string with nothing to shape is drawn as it is.
// - Building a line yourself: `buildAnnotatedString { append("…"); fig("$4.20"); sep(); bidi(hubText) }`, or [facts] for a row of
//   facts («۲ از ۴ کار | با من | ۶ دقیقه پیش»); [Facts] is the same as a composable. Never write « · » beside a number.
// - [FitText] / [Amount]: a figure that is never cut with «…». It shrinks its font to fit its box (down to 60 %), and below that it
//   wraps. [Fig] (Components.kt) and the stat tiles use it already.
// - [ScrollX]: a block wider than the screen (a table) scrolls sideways inside its card, with fading edges.
// - A string that must stay a string (a toast, a content description): [com.coinepro.hq.core.format.ltr] isolates a token, and
//   [sepsFa] turns « · » into a spaced Persian comma.

// ------------------------------------------------------------------------------------------------- the separator --
private const val SEP_ID = "hq.sep"
/** What a screen reader, a copy of the text, or a text drawn without the hairline gets in its place. */
private const val SEP_ALT = "، "
/** A zero-width right-to-left mark after the hairline. Without it, a fact that ends in a number or a Latin word («کار 3 از 4»)
 *  right before the hairline is measured wider by the platform's line breaker than by the text's own width, and a line laid out
 *  at its own width (one line, «…») loses its last word. Measured, and kept by a test (LookMotionTest). */
const val SEP_GUARD = "\u200F"
private val DOT_SEP = Regex("\\s+[·•]\\s+")

/** The separator between two facts: a thin vertical hairline with air on both sides (never «·», which reads as a zero beside a
 *  Persian digit). Drawn by [Text]; read aloud, and copied, as a Persian comma. */
fun AnnotatedString.Builder.sep() {
    appendInlineContent(SEP_ID, SEP_ALT)
    append(SEP_GUARD)
}

private val SEP_INLINE: Map<String, InlineTextContent> = mapOf(
    SEP_ID to InlineTextContent(Placeholder(0.95.em, 1.em, PlaceholderVerticalAlign.TextCenter)) {
        Box(Modifier.fillMaxWidth().fillMaxHeight(), contentAlignment = Alignment.Center) {
            Box(Modifier.width(1.dp).fillMaxHeight(0.86f).background(Divan.colors.lineStrong))
        }
    },
)

/** Facts in one line with the hairline between them; blank ones are left out. Each fact is shaped like any text ([bidi]). */
fun facts(vararg parts: String?): AnnotatedString = buildAnnotatedString {
    var first = true
    for (p in parts) {
        if (p.isNullOrBlank()) continue
        if (!first) sep()
        bidi(p.trim())
        first = false
    }
}

/** A line that still joins its facts with « · », for a place that takes only a string: a spaced Persian comma. */
fun sepsFa(text: String): String = text.replace(DOT_SEP, "، ")

/** A standalone hairline between two composables of a row (a mark and a text, two figures). */
@Composable
fun Sep(modifier: Modifier = Modifier, height: Dp = 12.dp) {
    Box(modifier.width(1.dp).height(height).background(Divan.colors.lineStrong))
}

/** [facts] as one line of text. */
@Composable
fun Facts(vararg parts: String?, modifier: Modifier = Modifier, style: TextStyle = Divan.type.caption, color: Color = Divan.colors.textMuted, maxLines: Int = 1) {
    Text(remember(*parts) { facts(*parts) }, modifier, style = style, color = color, maxLines = maxLines, overflow = TextOverflow.Ellipsis)
}

// ---------------------------------------------------------------------------------------------------- shaping --
private fun arabic(ch: Char) = ch in '֐'..'ࣿ' || ch in 'ﭐ'..'﻿'
private fun latinLetter(ch: Char) = ch in 'A'..'Z' || ch in 'a'..'z'

/**
 * A plain string as the app draws it, or null when it reads right as it is (most Persian sentences and most bare codes): « · »
 * between facts is the hairline, and each Latin token is one isolated left-to-right run in Latin digits ([bidi]). A string with no
 * Persian in it is shaped only when it mixes Latin letters with digits (a version, a ref), so its digits are not drawn Persian.
 */
fun shape(text: String): AnnotatedString? {
    var rtl = false
    var latin = false
    var digit = false
    var mark = false
    var dot = false
    for (ch in text) {
        when {
            latinLetter(ch) -> latin = true
            ch in '0'..'9' -> digit = true
            ch == '$' || ch == '%' || ch == ':' || ch == '+' || ch == '-' || ch == '−' || ch == '/' -> mark = true
            ch == '·' || ch == '•' -> dot = true
            arabic(ch) -> rtl = true
        }
    }
    val seps = dot && (DOT_SEP.containsMatchIn(text) || LEAD_DOT.containsMatchIn(text) || TRAIL_DOT.containsMatchIn(text))
    if (!rtl) {
        // No Persian in it: the line keeps its own direction (no isolate); only its digits must not be drawn Persian.
        if (!seps && !(latin && digit)) return null
        return buildAnnotatedString {
            if (latin && digit) pushStyle(androidx.compose.ui.text.SpanStyle(fontFamily = FigureFace, fontFeatureSettings = "tnum"))
            if (seps) appendWithSeps(text) else append(text)
        }
    }
    if (!seps && !(latin || (digit && mark))) return null
    if (!seps && latinRanges(text).isEmpty()) return null
    return buildAnnotatedString { bidi(text) }
}

/** [text] with « · » as the hairline (the pieces between are appended as they are). A line that begins or ends with the dot (one
 *  piece of a row of pieces, «· بازنشسته») carries the hairline at that end. */
internal fun AnnotatedString.Builder.appendWithSeps(text: String) {
    if ('·' !in text && '•' !in text) { append(text); return }
    var t = text
    val lead = LEAD_DOT.find(t)
    if (lead != null) { sep(); t = t.substring(lead.range.last + 1) }
    val trail = TRAIL_DOT.find(t)
    if (trail != null) t = t.substring(0, trail.range.first)
    var last = 0
    for (m in DOT_SEP.findAll(t)) {
        append(t.substring(last, m.range.first))
        sep()
        last = m.range.last + 1
    }
    append(t.substring(last))
    if (trail != null) sep()
}

private val LEAD_DOT = Regex("^\\s*[·•]\\s+")
private val TRAIL_DOT = Regex("\\s+[·•]\\s*$")

// ------------------------------------------------------------------------------------------------------- Text --
/**
 * The app's text: Material's `Text`, with the string shaped first ([shape]). Same parameters, so a screen only changes its import.
 */
@Composable
fun Text(
    text: String,
    modifier: Modifier = Modifier,
    color: Color = Color.Unspecified,
    autoSize: TextAutoSize? = null,
    fontSize: TextUnit = TextUnit.Unspecified,
    fontStyle: FontStyle? = null,
    fontWeight: FontWeight? = null,
    fontFamily: FontFamily? = null,
    letterSpacing: TextUnit = TextUnit.Unspecified,
    textDecoration: TextDecoration? = null,
    textAlign: TextAlign? = null,
    lineHeight: TextUnit = TextUnit.Unspecified,
    overflow: TextOverflow = TextOverflow.Clip,
    softWrap: Boolean = true,
    maxLines: Int = Int.MAX_VALUE,
    minLines: Int = 1,
    onTextLayout: ((TextLayoutResult) -> Unit)? = null,
    style: TextStyle = LocalTextStyle.current,
) {
    val shaped = remember(text) { shape(text) }
    if (shaped == null) {
        androidx.compose.material3.Text(text, modifier, color, autoSize, fontSize, fontStyle, fontWeight, fontFamily, letterSpacing, textDecoration, textAlign, lineHeight, overflow, softWrap, maxLines, minLines, onTextLayout, style)
    } else {
        androidx.compose.material3.Text(shaped, modifier, color, autoSize, fontSize, fontStyle, fontWeight, fontFamily, letterSpacing, textDecoration, textAlign, lineHeight, overflow, softWrap, maxLines, minLines, SEP_INLINE, onTextLayout ?: {}, style)
    }
}

/** The same for a line built by hand ([fig], [sep], [bidi], [facts]): it is drawn as built, and its separators are the hairline. */
@Composable
fun Text(
    text: AnnotatedString,
    modifier: Modifier = Modifier,
    color: Color = Color.Unspecified,
    autoSize: TextAutoSize? = null,
    fontSize: TextUnit = TextUnit.Unspecified,
    fontStyle: FontStyle? = null,
    fontWeight: FontWeight? = null,
    fontFamily: FontFamily? = null,
    letterSpacing: TextUnit = TextUnit.Unspecified,
    textDecoration: TextDecoration? = null,
    textAlign: TextAlign? = null,
    lineHeight: TextUnit = TextUnit.Unspecified,
    overflow: TextOverflow = TextOverflow.Clip,
    softWrap: Boolean = true,
    maxLines: Int = Int.MAX_VALUE,
    minLines: Int = 1,
    inlineContent: Map<String, InlineTextContent> = emptyMap(),
    onTextLayout: (TextLayoutResult) -> Unit = {},
    style: TextStyle = LocalTextStyle.current,
) {
    // A line built with « · » between its facts gets the hairline too (its spans are kept).
    val shown = if ('·' in text.text || '•' in text.text) remember(text) { withSeps(text) } else text
    androidx.compose.material3.Text(
        shown, modifier, color, autoSize, fontSize, fontStyle, fontWeight, fontFamily, letterSpacing, textDecoration, textAlign, lineHeight, overflow, softWrap, maxLines, minLines,
        if (inlineContent.isEmpty()) SEP_INLINE else inlineContent + SEP_INLINE, onTextLayout, style,
    )
}

/** [text] with every « · » between two facts drawn as the hairline; its spans, links and other annotations stay where they were.
 *  A dot inside a Latin run that is already isolated (U+2066 … U+2069) is part of that run and stays. */
fun withSeps(text: AnnotatedString): AnnotatedString {
    val t = text.text
    val hits = (DOT_SEP.findAll(t).map { it.range } + listOfNotNull(LEAD_DOT.find(t)?.range, TRAIL_DOT.find(t)?.range))
        .filter { !isolatedAt(t, it.first) }.sortedBy { it.first }.toList()
    if (hits.isEmpty()) return text
    return buildAnnotatedString {
        var last = 0
        for (r in hits) {
            if (r.first < last) continue
            append(text.subSequence(last, r.first))
            sep()
            last = r.last + 1
        }
        append(text.subSequence(last, t.length))
    }
}

private fun isolatedAt(t: String, at: Int): Boolean {
    if ('\u2066' !in t) return false
    var depth = 0
    for (i in 0 until at) when (t[i]) { '\u2066', '\u2067', '\u2068' -> depth++; '\u2069' -> if (depth > 0) depth-- }
    return depth > 0
}

// -------------------------------------------------------------------------------------------------- the amount --
/** The smallest share of its own size a fitted figure shrinks to; narrower than that, it wraps. */
const val FIT_FLOOR = 0.6f

/**
 * One line that is never cut: when its box is narrower than the text, the font shrinks to fit, down to [floor] of its size; at the
 * floor and still too wide, it wraps instead of ending in «…» ([wrap] false: a long code ends in «…» there, as the last resort).
 * Nothing is measured twice while the text fits (the usual case).
 */
@Composable
fun FitText(
    text: AnnotatedString,
    modifier: Modifier = Modifier,
    style: TextStyle = LocalTextStyle.current,
    color: Color = LocalContentColor.current,
    floor: Float = FIT_FLOOR,
    textAlign: TextAlign? = null,
    wrap: Boolean = true,
) {
    // 0: one line at its own size; 1: shrinking to fit; 2: at the floor (wrapped, or cut as the last resort).
    var mode by remember(text, style.fontSize) { mutableIntStateOf(0) }
    val size = if (style.fontSize.isSp) style.fontSize else 14.sp
    val min = (size.value * floor).sp
    val wrapped = mode == 2 && wrap
    val shown = if (mode == 2) style.copy(fontSize = min, lineHeight = if (wrap && style.lineHeight.isSp) (style.lineHeight.value * (floor + 0.15f)).sp else style.lineHeight) else style
    // A text node made afresh for each mode: one that turns auto-sizing on after its first layout is not laid out again.
    androidx.compose.runtime.key(mode) {
        Text(
            text, modifier, color = color, style = shown, textAlign = textAlign,
            maxLines = if (wrapped) Int.MAX_VALUE else 1, softWrap = wrapped, overflow = if (mode == 2 && !wrap) TextOverflow.Ellipsis else TextOverflow.Clip,
            autoSize = if (mode == 1) TextAutoSize.StepBased(minFontSize = min, maxFontSize = size, stepSize = 0.5.sp) else null,
            onTextLayout = { r -> if (mode < 2 && (r.didOverflowWidth || r.hasVisualOverflow)) mode += 1 },
        )
    }
}

@Composable
fun FitText(text: String, modifier: Modifier = Modifier, style: TextStyle = LocalTextStyle.current, color: Color = LocalContentColor.current, floor: Float = FIT_FLOOR, textAlign: TextAlign? = null, wrap: Boolean = true) {
    FitText(remember(text) { shape(text) ?: AnnotatedString(text) }, modifier, style, color, floor, textAlign, wrap)
}

/** An amount (money, a count of tokens, a rank, a percent): Latin tabular digits, read left to right, never cut ([FitText]). */
@Composable
fun Amount(text: String, modifier: Modifier = Modifier, style: TextStyle = Divan.type.figureL, color: Color = LocalContentColor.current, floor: Float = FIT_FLOOR, textAlign: TextAlign? = null) {
    FitText(AnnotatedString(text), modifier, style.copy(fontFamily = FigureFace, fontFeatureSettings = "tnum", textDirection = TextDirection.Ltr), color, floor, textAlign)
}

// ---------------------------------------------------------------------------------------------- the wide block --
/** A block wider than the screen (a table, a row of figures) scrolls sideways inside its card; the page itself never does. */
@Composable
fun ScrollX(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    val scroll = rememberScrollState()
    Box(modifier.fillMaxWidth().fadingEdges(scroll).horizontalScroll(scroll)) { content() }
}
