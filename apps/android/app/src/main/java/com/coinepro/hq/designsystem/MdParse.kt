package com.coinepro.hq.designsystem

// The Markdown the hub writes (the rule-based morning report, letters, minutes, memos, agents' outputs), parsed line by line into
// blocks: #-headings, paragraphs, "-" and "1." lists with nesting and continuation lines, "> " quotes, ``` code, "---" rules and
// GFM tables. Pure Kotlin, no Compose: the renderer is Md.kt, the tests are MarkdownTest. No raw HTML, ever.

sealed interface MdBlock {
    data class Heading(val level: Int, val text: String) : MdBlock
    data class Para(val text: String) : MdBlock
    data class Quote(val blocks: List<MdBlock>) : MdBlock
    data class ListBlock(val ordered: Boolean, val start: Int, val items: List<MdItem>) : MdBlock
    data class Code(val lang: String?, val text: String) : MdBlock
    data class Table(val header: List<String>, val align: List<MdAlign>, val rows: List<List<String>>) : MdBlock {
        val columns: Int get() = header.size
    }
    data object Rule : MdBlock
}

/** One list item: its text and what is nested under it (a deeper list, a quote, a paragraph). */
data class MdItem(val text: String, val children: List<MdBlock> = emptyList())

/** GFM column alignment as written (`:--` left, `--:` right, `:-:` centre); [NONE] lets the renderer choose. */
enum class MdAlign { NONE, LEFT, CENTER, RIGHT }

object MdParser {
    private val HEADING = Regex("^ {0,3}(#{1,6})\\s+(.*?)(?:\\s+#+)?\\s*$")
    private val FENCE = Regex("^ {0,3}(```|~~~)\\s*([\\w+-]*)\\s*$")
    private val RULE = Regex("^ {0,3}([-*_])(\\s*\\1){2,}\\s*$")
    private val QUOTE = Regex("^ {0,3}>\\s?(.*)$")
    private val ITEM = Regex("^(\\s*)([-*+•]|(\\d{1,9})[.)])\\s+(.*)$")
    private val SEPARATOR_CELL = Regex("^\\s*:?-+:?\\s*$")

    fun parse(text: String): List<MdBlock> = blocks(text.replace("\r\n", "\n").replace('\r', '\n').split('\n'))

    private fun blocks(lines: List<String>): List<MdBlock> {
        val out = mutableListOf<MdBlock>()
        val para = mutableListOf<String>()
        fun flush() {
            if (para.isNotEmpty()) out += MdBlock.Para(para.joinToString(" ") { it.trim() })
            para.clear()
        }
        var i = 0
        while (i < lines.size) {
            val line = lines[i]
            if (line.isBlank()) { flush(); i++; continue }
            val fence = FENCE.find(line)
            if (fence != null) {
                flush()
                val mark = fence.groupValues[1]
                val body = mutableListOf<String>()
                i++
                while (i < lines.size && !lines[i].trimStart().startsWith(mark)) { body += lines[i]; i++ }
                i++ // the closing fence (or the end)
                out += MdBlock.Code(fence.groupValues[2].ifBlank { null }, body.joinToString("\n").trimEnd())
                continue
            }
            val heading = HEADING.find(line)
            if (heading != null) {
                flush()
                out += MdBlock.Heading(heading.groupValues[1].length, heading.groupValues[2].trim())
                i++
                continue
            }
            if (isTableStart(lines, i)) {
                flush()
                val header = cells(lines[i])
                val align = cells(lines[i + 1]).map(::alignOf)
                val rows = mutableListOf<List<String>>()
                i += 2
                while (i < lines.size && lines[i].isNotBlank() && lines[i].contains('|') && !HEADING.matches(lines[i])) { rows += cells(lines[i]); i++ }
                val n = header.size
                out += MdBlock.Table(header, List(n) { align.getOrElse(it) { MdAlign.NONE } }, rows.map { r -> List(n) { r.getOrElse(it) { "" } } })
                continue
            }
            if (RULE.matches(line) && !(para.isNotEmpty() && line.trim().all { it == '-' })) {
                // "---" under a paragraph line is a setext heading in CommonMark; the hub never writes those, so it is a rule.
                flush(); out += MdBlock.Rule; i++; continue
            }
            if (QUOTE.matches(line)) {
                flush()
                val inner = mutableListOf<String>()
                while (i < lines.size && QUOTE.matches(lines[i])) { inner += QUOTE.find(lines[i])!!.groupValues[1]; i++ }
                out += MdBlock.Quote(blocks(inner))
                continue
            }
            if (ITEM.matches(line)) {
                flush()
                val (list, next) = list(lines, i)
                out += list
                i = next
                continue
            }
            para += line
            i++
        }
        flush()
        return out
    }

    /** A list from [from]: items at the first item's indent; deeper lines (items or text) belong to the item above them. */
    private fun list(lines: List<String>, from: Int): Pair<MdBlock.ListBlock, Int> {
        val first = ITEM.find(lines[from])!!
        val indent = first.groupValues[1].length
        val ordered = first.groupValues[3].isNotEmpty()
        val start = first.groupValues[3].toIntOrNull() ?: 1
        val items = mutableListOf<MdItem>()
        var i = from
        while (i < lines.size) {
            val m = ITEM.find(lines[i])
            if (m == null || m.groupValues[1].length != indent || (m.groupValues[3].isNotEmpty()) != ordered) break
            val text = StringBuilder(m.groupValues[4].trim())
            val nested = mutableListOf<String>()
            i++
            while (i < lines.size) {
                val l = lines[i]
                if (l.isBlank()) {
                    // A blank line ends the list unless the next line is indented under this item.
                    val n = lines.getOrNull(i + 1)
                    if (n != null && n.isNotBlank() && lead(n) > indent) { nested += ""; i++; continue }
                    break
                }
                val lm = ITEM.find(l)
                if (lm != null && lm.groupValues[1].length <= indent) break
                // An unindented line ends the list (the hub writes a closing sentence right under its items).
                if (lm == null && lead(l) <= indent) break
                val block = lm != null || HEADING.matches(l) || QUOTE.matches(l) || FENCE.matches(l) || isTableStart(lines, i)
                if (!block && nested.isEmpty()) { text.append(' ').append(l.trim()); i++; continue }  // the item's text, wrapped
                nested += l.drop(minOf(lead(l), indent + 2))
                i++
            }
            items += MdItem(text.toString(), if (nested.isEmpty()) emptyList() else blocks(dedent(nested)))
        }
        return MdBlock.ListBlock(ordered, start, items) to i
    }

    private fun lead(s: String): Int = s.length - s.trimStart().length

    private fun dedent(xs: List<String>): List<String> {
        val d = xs.filter { it.isNotBlank() }.minOfOrNull(::lead) ?: 0
        return xs.map { if (it.isBlank()) "" else it.drop(d) }
    }

    private fun isTableStart(lines: List<String>, i: Int): Boolean {
        val head = lines.getOrNull(i) ?: return false
        val sep = lines.getOrNull(i + 1) ?: return false
        if (!head.contains('|') || !sep.contains('-')) return false
        val parts = cells(sep)
        return parts.isNotEmpty() && (sep.contains('|')) && parts.all { SEPARATOR_CELL.matches(it) } && cells(head).isNotEmpty()
    }

    /** The cells of a table row: split on unescaped pipes, the outer pipes optional, `\|` a literal pipe. */
    fun cells(row: String): List<String> {
        var s = row.trim()
        if (s.startsWith("|")) s = s.drop(1)
        if (s.endsWith("|") && !s.endsWith("\\|")) s = s.dropLast(1)
        val out = mutableListOf<String>()
        val cur = StringBuilder()
        var code = false
        var k = 0
        while (k < s.length) {
            val ch = s[k]
            when {
                ch == '\\' && k + 1 < s.length && s[k + 1] == '|' -> { cur.append('|'); k++ }
                ch == '`' -> { code = !code; cur.append(ch) }
                ch == '|' && !code -> { out += cur.toString().trim(); cur.clear() }
                else -> cur.append(ch)
            }
            k++
        }
        out += cur.toString().trim()
        return out
    }

    private fun alignOf(cell: String): MdAlign {
        val c = cell.trim()
        val l = c.startsWith(":")
        val r = c.endsWith(":")
        return when { l && r -> MdAlign.CENTER; r -> MdAlign.RIGHT; l -> MdAlign.LEFT; else -> MdAlign.NONE }
    }

    // ------------------------------------------------------------------ tables --
    private val FIGURE = Regex("^[\\s(]*[-+−~≈$€£]?\\s*[\\d۰-۹٠-٩][\\d۰-۹٠-٩.,٫٬:/\\s]*(%|٪|[KMB]|USD|USDT|tok|ms|s|MB|GB)?[)\\s]*$")

    /** A cell that is a figure (a count, money, a share, a time): it is set in Latin figures and its column centred. */
    fun isFigure(cell: String): Boolean = cell.isNotBlank() && FIGURE.matches(cell.replace("**", "").replace("`", ""))

    /** A column is a figure column when most of its non-empty body cells are figures ("—" counts as empty). */
    fun figureColumns(t: MdBlock.Table): List<Boolean> = List(t.columns) { c ->
        val cells = t.rows.map { it[c] }.filter { it.isNotBlank() && it.trim() != "—" && it.trim() != "-" }
        cells.isNotEmpty() && cells.count(::isFigure) * 2 >= cells.size
    }

    /**
     * Column widths for a table: each column as wide as its widest cell ([natural], the cells' one-line widths), between [min] and
     * [max] (a longer cell wraps inside [max]); when the columns together are narrower than [available] they share the rest in
     * proportion, so the table fills its card. Wider than [available]: the caller scrolls it sideways, never squeezes it.
     */
    fun columnWidths(natural: List<Int>, available: Int, min: Int, max: Int, padding: Int): List<Int> {
        if (natural.isEmpty()) return emptyList()
        val w = natural.map { (it + padding).coerceIn(min, max + padding) }
        val total = w.sum()
        if (total >= available || total == 0) return w
        val extra = available - total
        val out = w.map { it + (extra.toLong() * it / total).toInt() }.toMutableList()
        out[out.lastIndex] += available - out.sum()
        return out
    }
}
