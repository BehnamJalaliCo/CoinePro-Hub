package com.coinepro.hq.designsystem

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withLink
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// The Markdown the hub and its agents write (mirrors apps/web/src/components/ui/md.tsx, and goes further): #-headings, paragraphs,
// "-" and "1." lists (nested), "> " quotes, ``` code, rules, GFM tables, **bold**, `code`, [links](…) and refs (D-…, M-…, O-…, W-…,
// A-…, and ⟨1.3⟩ F-…, S-…, G-…, AP-…; ⟨1.4⟩ FI-…, PR-…, CH-…, SO-…, H-…, Q-…, E-…, SK-…, EV-…, TE-…, L-…, C-…, PV-…, N-…, P-…; ⟨1.5⟩
// MT-…, K-…, KB-…, OB-…, KR-…, OR-…, RK-…, CE-…, B-…; §21 DM-…, AK-…, WR-…, BR-…, HR-…, NT-…, CL-…, DP-…, CR-…; ⟨1.6⟩ SR-…, MI-…, LC-…,
// RD-…, HQ-LGL; ⟨1.7⟩ AR-…, FP-…, PT-…, RR-…, LH-…, RM-…, AU-…, HQ-ARC) as Latin figures in gold, opening their page where the app
// has one; a ref inside a path (hq/S-0004) stays part of the path. Latin tokens with digits (hashes, versions, model names, money,
// ⟨1.5⟩ a ref at its version "TM-0008@1") keep Latin digits; prose counts keep Persian digits; a table's figure cells are Latin.
// The block parser is MdParse.kt.

private val REF = Regex("(?<![/\\w-])([DMOWIFSGNPHQELCKB]-\\d{3,6}|A-\\d{4}|AR-\\d{6}|(?:AP|FI|PR|CH|SO|SK|EV|TE|PV|MT|KB|OB|KR|OR|RK|CE|DM|AK|WR|BR|HR|NT|CL|DP|CR|SR|MI|LC|RD|FP|PT|RR|LH|RM|AU)-\\d{3,4}|[A-Z]{2,5}(?:-[A-Z]{2,8})?-(?:\\d{2,3}|MGR|CEO|ADV|OVR|PA|LGL|ARC|SYS)(?:-\\d{4})?)\\b")
// ⟨1.7.3⟩ also a date (2026-10-17, 1405/07/25) and a count of tokens or dollars ("182400 توکن", "12 USD"): figures, Latin.
private val LATIN = Regex("((?:Opus|Sonnet|Haiku|Fable|Claude|GPT|Gemini) \\d+(?:\\.\\d+)*|(?:\\$|[A-Za-z])[A-Za-z0-9._%$/@-]*\\d[A-Za-z0-9._%/@-]*|\\d+(?:[.,]\\d+)*[A-Za-z][A-Za-z0-9._-]*|\\b\\d{4}[-/]\\d{1,2}[-/]\\d{1,2}\\b|\\d[\\d,.]*(?=\\s?(?:توکن|USDT?\\b)))")
private val INLINE = Regex("(\\*\\*[^*]+\\*\\*|`[^`]+`|\\[[^\\]\\n]+]\\([^)\\s]+\\))")
private val LINK = Regex("^\\[([^\\]]+)]\\(([^)\\s]+)\\)$")

/** How a ref in agent text opens its page: the shell provides the app's routes; without it (or for a ref with no page) it only shows. */
@Immutable
class RefLinks(val hasPage: (String) -> Boolean, val open: (String) -> Unit)

val LocalRefLinks = staticCompositionLocalOf<RefLinks?> { null }

@Immutable
private class MdColors(val ink: Color, val gold: Color, val codeBg: Color, val link: Color, val links: RefLinks?)

private fun AnnotatedString.Builder.ref(ref: String, k: MdColors) {
    val links = k.links
    if (links != null && links.hasPage(ref)) {
        withLink(LinkAnnotation.Clickable(ref, TextLinkStyles(SpanStyle(color = k.gold))) { links.open(ref) }) { fig(ref, k.gold) }
    } else fig(ref, k.gold)
}

private fun AnnotatedString.Builder.refs(text: String, k: MdColors) {
    var last = 0
    for (m in REF.findAll(text)) {
        latin(text.substring(last, m.range.first))
        ref(m.value, k)
        last = m.range.last + 1
    }
    latin(text.substring(last))
}

private fun AnnotatedString.Builder.latin(text: String) {
    var last = 0
    for (m in LATIN.findAll(text)) {
        append(text.substring(last, m.range.first))
        fig(m.value)
        last = m.range.last + 1
    }
    append(text.substring(last))
}

// A middle dot between Persian words or beside a count is drawn by the text face like the Persian zero ("· ۶" reads "۰ ۶"): there it
// becomes the Persian comma. Between Latin words ("Chrome · Android") it stays.
private val DOT = Regex(" · (?=[\u0600-\u06FF0-9])|(?<=[\u0600-\u06FF0-9]) · ")

/** A decimal inside Persian prose ("disk 90.4%") takes the Persian separator, so «۹۰٫۴٪» does not read as «۹۰.۴». */
private val DECIMAL = Regex("(?<![\\w.:/-])(\\d+)\\.(\\d+)(?=%|٪|\\s|$|[،؛,;)])")

private fun inline(raw: String, k: MdColors): AnnotatedString = timesFig(inlineText(raw, k))

private fun inlineText(raw: String, k: MdColors): AnnotatedString = buildAnnotatedString {
    val text = DECIMAL.replace(DOT.replace(raw, "، "), "$1٫$2")
    var last = 0
    for (m in INLINE.findAll(text)) {
        refs(text.substring(last, m.range.first), k)
        val t = m.value
        when {
            t.startsWith("**") -> withStyle(SpanStyle(fontWeight = FontWeight.SemiBold, color = k.ink)) { refs(t.substring(2, t.length - 2), k) }
            t.startsWith("`") -> withStyle(SpanStyle(fontFamily = FigureFace, background = k.codeBg, color = k.ink)) { append("⁦" + t.substring(1, t.length - 1) + "⁩") }
            else -> link(t, k)
        }
        last = m.range.last + 1
    }
    refs(text.substring(last), k)
}

/** `[label](target)`: a ref opens its page, a web address opens in the browser; anything else shows its label only. */
private fun AnnotatedString.Builder.link(t: String, k: MdColors) {
    val m = LINK.find(t) ?: return refs(t, k)
    val (label, target) = m.destructured
    val ref = REF.matchEntire(target)?.value ?: REF.matchEntire(label.trim())?.value
    when {
        ref != null -> if (label.trim() == ref) ref(ref, k) else {
            val links = k.links
            if (links != null && links.hasPage(ref)) withLink(LinkAnnotation.Clickable(ref, TextLinkStyles(SpanStyle(color = k.gold))) { links.open(ref) }) { refs(label, k) }
            else withStyle(SpanStyle(color = k.gold)) { refs(label, k) }
        }
        target.startsWith("https://") || target.startsWith("http://") ->
            withLink(LinkAnnotation.Url(target, TextLinkStyles(SpanStyle(color = k.link, textDecoration = TextDecoration.Underline)))) { refs(label, k) }
        else -> refs(label, k)
    }
}

@Composable
private fun mdColors(): MdColors {
    val c = Divan.colors
    val links = LocalRefLinks.current
    return remember(c, links) { MdColors(c.textPrimary, c.goldInk, c.tile, c.lapis, links) }
}

/** One line or paragraph of agent or server text with refs and Latin tokens kept Latin (no blocks). */
@Composable
fun RichText(text: String, modifier: Modifier = Modifier, style: TextStyle = Divan.type.small, color: Color = Divan.colors.textSecondary, maxLines: Int = Int.MAX_VALUE) {
    val k = mdColors()
    Text(remember(text, k) { inline(text, k) }, modifier, style = style, color = color, maxLines = maxLines, overflow = TextOverflow.Ellipsis)
}

@Composable
fun Md(text: String?, modifier: Modifier = Modifier, style: TextStyle = Divan.type.small.copy(lineHeight = 24.sp), color: Color = Divan.colors.textSecondary) {
    if (text.isNullOrBlank()) return
    val k = mdColors()
    val blocks = remember(text) { MdParser.parse(text) }
    Blocks(blocks, modifier, style, color, k, 0)
}

@Composable
private fun Blocks(blocks: List<MdBlock>, modifier: Modifier, style: TextStyle, color: Color, k: MdColors, depth: Int) {
    val c = Divan.colors
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        blocks.forEachIndexed { i, b ->
            when (b) {
                is MdBlock.Heading -> {
                    val hs = when (b.level) {
                        1 -> Divan.type.h3
                        2 -> Divan.type.bodyStrong
                        else -> Divan.type.bodyStrong.copy(fontSize = style.fontSize)
                    }
                    Text(
                        remember(b.text, k) { inline(b.text, k) },
                        Modifier.padding(top = if (i > 0 && b.level <= 2) 6.dp else 0.dp).semantics { heading() },
                        style = hs, color = c.textPrimary,
                    )
                }
                is MdBlock.Para -> Text(remember(b.text, k) { inline(b.text, k) }, style = style, color = color)
                is MdBlock.ListBlock -> MdList(b, style, color, k, depth)
                is MdBlock.Quote -> {
                    val bar = c.lineTahrir
                    Blocks(
                        b.blocks,
                        Modifier.fillMaxWidth()
                            .drawBehind {
                                val w = 3.dp.toPx()
                                val x = if (layoutDirection == LayoutDirection.Rtl) size.width - w else 0f
                                drawRoundRect(bar, Offset(x, 0f), Size(w, size.height), androidx.compose.ui.geometry.CornerRadius(w / 2))
                            }
                            .padding(start = 13.dp),
                        style, c.textSecondary, k, depth,
                    )
                }
                // Code reads left to right and scrolls from its left edge.
                is MdBlock.Code -> androidx.compose.runtime.CompositionLocalProvider(androidx.compose.ui.platform.LocalLayoutDirection provides LayoutDirection.Ltr) {
                    Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(12.dp)) {
                        Text(
                            b.text, Modifier.horizontalScroll(rememberScrollState()),
                            style = style.copy(fontFamily = FigureFace, fontSize = 12.sp, lineHeight = 18.sp, textDirection = TextDirection.Ltr),
                            color = c.textPrimary, softWrap = false,
                        )
                    }
                }
                is MdBlock.Table -> MdTable(b, k)
                MdBlock.Rule -> HorizontalDivider(color = c.lineDivider)
            }
        }
    }
}

@Composable
private fun MdList(b: MdBlock.ListBlock, style: TextStyle, color: Color, k: MdColors, depth: Int) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        b.items.forEachIndexed { i, item ->
            Row {
                val marker = if (b.ordered) "${b.start + i}." else when (depth) { 0 -> "•"; 1 -> "◦"; else -> "▪" }
                Text(marker, style = style, color = c.textMuted, modifier = Modifier.width(if (b.ordered) 22.dp else 18.dp))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    if (item.text.isNotBlank()) Text(remember(item.text, k) { inline(item.text, k) }, style = style, color = color)
                    if (item.children.isNotEmpty()) Blocks(item.children, Modifier, style, color, k, depth + 1)
                }
            }
        }
    }
}

// ------------------------------------------------------------------ tables --
/**
 * A GFM table as a real table: the header on a tile, every row on its own line with a divider, cells padded, columns in reading order
 * (right to left), figures in Latin. Each column is as wide as its widest cell (a long cell wraps within a cap) and the table fills its
 * card; when it is wider than the screen it scrolls sideways inside its card, with a fade on the side that has more.
 */
@Composable
private fun MdTable(t: MdBlock.Table, k: MdColors) {
    val c = Divan.colors
    val figures = remember(t) { MdParser.figureColumns(t) }
    val shape = RoundedCornerShape(12.dp)
    val scroll = rememberScrollState()
    val textStyle = Divan.type.small.copy(lineHeight = 20.sp)
    val figStyle = textStyle.copy(fontFamily = FigureFace, fontFeatureSettings = "tnum")
    val headStyle = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold)
    BoxWithConstraints(Modifier.fillMaxWidth().clip(shape).border(1.dp, c.lineDivider, shape).background(c.card)) {
        val available = constraints.maxWidth
        Box(Modifier.horizontalScroll(scroll)) {
            val divider = c.lineDivider
            val strong = c.lineStrong
            TableLayout(t.columns, t.rows.size + 1, available) {
                for (col in 0 until t.columns) {
                    val a = alignment(t.align[col], figures[col])
                    Box(Modifier.background(c.tile).drawBehind { drawLine(strong, Offset(0f, size.height - 0.5f), Offset(size.width, size.height - 0.5f), 1.dp.toPx()) }.padding(horizontal = 10.dp, vertical = 8.dp), contentAlignment = a) {
                        Text(remember(t.header[col], k) { inline(t.header[col], k) }, style = headStyle, color = c.textSecondary, textAlign = textAlign(a))
                    }
                }
                t.rows.forEachIndexed { r, row ->
                    for (col in 0 until t.columns) {
                        val cell = row[col]
                        val fig = MdParser.isFigure(cell)
                        val a = alignment(t.align[col], figures[col])
                        Box(
                            Modifier.drawBehind { if (r > 0) drawLine(divider, Offset(0f, 0f), Offset(size.width, 0f), 1.dp.toPx()) }.padding(horizontal = 10.dp, vertical = 8.dp),
                            contentAlignment = a,
                        ) {
                            if (fig) Text(cell.replace("**", "").replace("`", "").trim(), style = figStyle.copy(textDirection = TextDirection.Ltr), color = c.textPrimary, textAlign = textAlign(a))
                            else Text(remember(cell, k) { inline(cell, k) }, style = textStyle, color = c.textPrimary, textAlign = textAlign(a))
                        }
                    }
                }
            }
        }
        if (scroll.maxValue > 0) {
            // A soft fade on the side that has more columns: the table starts at its first column (the right, in Persian) and
            // the rest lies towards the end.
            val rtl = androidx.compose.ui.platform.LocalLayoutDirection.current == LayoutDirection.Rtl
            val clear = c.card.copy(alpha = 0f)
            fun edge(atLeft: Boolean) = Brush.horizontalGradient(if (atLeft) listOf(c.card, clear) else listOf(clear, c.card))
            Box(Modifier.matchParentSize()) {
                if (scroll.value < scroll.maxValue) Box(Modifier.align(Alignment.CenterEnd).width(28.dp).fillMaxHeight().background(edge(atLeft = rtl)))
                if (scroll.value > 0) Box(Modifier.align(Alignment.CenterStart).width(28.dp).fillMaxHeight().background(edge(atLeft = !rtl)))
            }
        }
    }
}

private fun alignment(a: MdAlign, figure: Boolean): Alignment = when (a) {
    // The table is drawn right to left: a column written ":--" (left) still means "the start" to a Persian author; figures centre.
    MdAlign.CENTER -> Alignment.Center
    MdAlign.RIGHT -> Alignment.CenterEnd
    MdAlign.LEFT -> Alignment.CenterStart
    MdAlign.NONE -> if (figure) Alignment.Center else Alignment.CenterStart
}

private fun textAlign(a: Alignment): TextAlign = when (a) {
    Alignment.Center -> TextAlign.Center
    Alignment.CenterEnd -> TextAlign.End
    else -> TextAlign.Start
}

/** Lays out [columns] × [rows] cells (header first, row by row): widths from [MdParser.columnWidths], each row as tall as its tallest cell. */
@Composable
private fun TableLayout(columns: Int, rows: Int, available: Int, content: @Composable () -> Unit) {
    Layout(content) { measurables, _ ->
        val min = 56.dp.roundToPx()
        val max = 240.dp.roundToPx()
        val natural = List(columns) { col -> (0 until rows).maxOf { r -> measurables[r * columns + col].maxIntrinsicWidth(Constraints.Infinity) } }
        val widths = MdParser.columnWidths(natural, available, min, max, 0)
        val heights = List(rows) { r -> (0 until columns).maxOf { col -> measurables[r * columns + col].maxIntrinsicHeight(widths[col]) } }
        val placeables = measurables.mapIndexed { i, m -> m.measure(Constraints.fixed(widths[i % columns], heights[i / columns])) }
        layout(widths.sum(), heights.sum()) {
            var y = 0
            for (r in 0 until rows) {
                var x = 0
                for (col in 0 until columns) {
                    placeables[r * columns + col].placeRelative(x, y)
                    x += widths[col]
                }
                y += heights[r]
            }
        }
    }
}
