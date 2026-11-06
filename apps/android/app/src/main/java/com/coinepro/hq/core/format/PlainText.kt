package com.coinepro.hq.core.format

/**
 * Markdown as the plain words the owner copies: headings, emphasis, code marks, quotes and links lose their marks (a link keeps its
 * words), list items keep a dash, the line breaks stay. What is pasted elsewhere reads like what was on the screen.
 */
fun plainOfMd(md: String): String {
    val out = mutableListOf<String>()
    for (raw in md.replace("\r\n", "\n").lines()) {
        if (raw.trimStart().startsWith("```")) continue
        var line = raw
        line = HEADING.replace(line, "")
        line = QUOTE.replace(line, "")
        line = BULLET.replace(line) { m -> m.groupValues[1] + "- " }
        line = IMAGE.replace(line) { it.groupValues[1] }
        line = LINK.replace(line) { it.groupValues[1] }
        line = BOLD.replace(line) { it.groupValues[2] }
        line = ITALIC.replace(line) { it.groupValues[1] }
        line = CODE.replace(line) { it.groupValues[1] }
        line = STRIKE.replace(line) { it.groupValues[1] }
        out += line.trimEnd()
    }
    return out.joinToString("\n").replace(BLANKS, "\n\n").trim()
}

private val HEADING = Regex("^\\s{0,3}#{1,6}\\s+")
private val QUOTE = Regex("^\\s{0,3}>\\s?")
private val BULLET = Regex("^(\\s*)[*+-]\\s+")
private val IMAGE = Regex("!\\[([^\\]]*)]\\([^)]*\\)")
private val LINK = Regex("\\[([^\\]]+)]\\([^)]*\\)")
private val BOLD = Regex("(\\*\\*|__)(.+?)\\1")
private val ITALIC = Regex("(?<![\\p{L}\\p{N}*])\\*(?!\\s)(.+?)(?<!\\s)\\*(?![\\p{L}\\p{N}*])")
private val CODE = Regex("`([^`]+)`")
private val STRIKE = Regex("~~(.+?)~~")
private val BLANKS = Regex("\n{3,}")
