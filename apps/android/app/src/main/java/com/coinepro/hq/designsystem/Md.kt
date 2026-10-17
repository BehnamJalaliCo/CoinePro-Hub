package com.coinepro.hq.designsystem

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp

// A small, safe Markdown subset for agent-written text (mirrors apps/web/src/components/ui/md.tsx):
// paragraphs, #-headings, - and 1. lists, **bold**, `code`, and refs (D-…, M-…, O-…, W-…, A-…, and ⟨1.3⟩ F-…, S-…,
// G-…, AP-…) as Latin figures in gold; a ref inside a path (hq/S-0004) stays part of the path. Latin tokens with
// digits (hashes, versions, model names, money) keep Latin digits.

private val REF = Regex("(?<![/\\w-])([DMOWIFSG]-\\d{3,6}|A-\\d{4}|AP-\\d{4}|[A-Z]{2,5}(?:-[A-Z]{2,8})?-(?:\\d{2,3}|MGR|CEO|ADV|SYS)(?:-\\d{4})?)\\b")
private val LATIN = Regex("((?:Opus|Sonnet|Haiku|Fable|Claude|GPT|Gemini) \\d+(?:\\.\\d+)*|(?:\\$|[A-Za-z])[A-Za-z0-9._%$/-]*\\d[A-Za-z0-9._%/-]*|\\d+[A-Za-z][A-Za-z0-9._-]*)")
private val INLINE = Regex("(\\*\\*[^*]+\\*\\*|`[^`]+`)")

private class MdColors(val ink: Color, val gold: Color, val codeBg: Color)

private fun AnnotatedString.Builder.refs(text: String, k: MdColors) {
    var last = 0
    for (m in REF.findAll(text)) {
        latin(text.substring(last, m.range.first))
        fig(m.value, k.gold)
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

private fun inline(text: String, k: MdColors): AnnotatedString = buildAnnotatedString {
    var last = 0
    for (m in INLINE.findAll(text)) {
        refs(text.substring(last, m.range.first), k)
        val t = m.value
        if (t.startsWith("**")) withStyle(SpanStyle(fontWeight = FontWeight.SemiBold, color = k.ink)) { refs(t.substring(2, t.length - 2), k) }
        else withStyle(SpanStyle(fontFamily = FigureFace, background = k.codeBg, color = k.ink)) { append("\u2066" + t.substring(1, t.length - 1) + "\u2069") }
        last = m.range.last + 1
    }
    refs(text.substring(last), k)
}

private sealed interface Block {
    data class Heading(val text: String) : Block
    data class Bullets(val items: List<String>, val ordered: Boolean) : Block
    data class Para(val text: String) : Block
}

private fun parse(text: String): List<Block> {
    val out = mutableListOf<Block>()
    for (raw in text.replace("\r\n", "\n").split(Regex("\n{2,}"))) {
        var lines = raw.split('\n').filter { it.isNotBlank() }
        if (lines.isEmpty()) continue
        Regex("^(#{1,4})\\s+(.*)$").find(lines[0])?.let {
            out += Block.Heading(it.groupValues[2])
            lines = lines.drop(1)
        }
        if (lines.isEmpty()) continue
        val bullet = Regex("^\\s*[-*•]\\s+")
        val number = Regex("^\\s*\\d+[.)]\\s+")
        out += when {
            lines.all { bullet.containsMatchIn(it) } -> Block.Bullets(lines.map { it.replace(bullet, "") }, false)
            lines.all { number.containsMatchIn(it) } -> Block.Bullets(lines.map { it.replace(number, "") }, true)
            else -> Block.Para(lines.joinToString(" "))
        }
    }
    return out
}

/** One line or paragraph of agent or server text with refs and Latin tokens kept Latin (no blocks). */
@Composable
fun RichText(text: String, modifier: Modifier = Modifier, style: TextStyle = Divan.type.small, color: Color = Divan.colors.textSecondary, maxLines: Int = Int.MAX_VALUE) {
    val c = Divan.colors
    val k = remember(c) { MdColors(c.textPrimary, c.goldInk, c.tile) }
    Text(remember(text, k) { inline(text, k) }, modifier, style = style, color = color, maxLines = maxLines, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
}

@Composable
fun Md(text: String?, modifier: Modifier = Modifier, style: TextStyle = Divan.type.small.copy(lineHeight = Divan.type.body.lineHeight), color: Color = Divan.colors.textSecondary) {
    if (text.isNullOrBlank()) return
    val c = Divan.colors
    val k = remember(c) { MdColors(c.textPrimary, c.goldInk, c.tile) }
    val blocks = remember(text) { parse(text) }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (b in blocks) when (b) {
            is Block.Heading -> Text(inline(b.text, k), style = Divan.type.bodyStrong.copy(fontSize = style.fontSize), color = c.textPrimary)
            is Block.Para -> Text(inline(b.text, k), style = style, color = color)
            is Block.Bullets -> Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                b.items.forEachIndexed { i, item ->
                    Row {
                        Text(if (b.ordered) "${i + 1}." else "•", style = style, color = c.textMuted, modifier = Modifier.width(18.dp))
                        Text(inline(item, k), style = style, color = color)
                    }
                }
            }
        }
    }
}
