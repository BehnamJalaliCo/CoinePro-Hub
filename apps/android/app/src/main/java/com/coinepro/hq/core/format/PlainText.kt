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

// ⟨1.0.1⟩ Part C (C1.4), the owner's decisions: a terminal command is never the owner's step, and a publishing account is never «کلید
// ندارد» for him (Instagram of every company goes out through IG-Hub; what must be connected is the technical team's work). A note
// of the hub's that carries a command is shown without that sentence; the sentence goes one tap away, under «جزئیات فنی».
private val COMMAND = Regex("`[^`]+`|\\bmake\\s+[a-z][a-z0-9-]*", RegexOption.IGNORE_CASE)
private val ROUTE_WORDS = Regex("کلید|حساب|اینستاگرام|account|key", RegexOption.IGNORE_CASE)
private val SENTENCE_END = Regex("(?<=[.!؟])\\s+")

/** What the owner reads where the publishing path of a company is not connected yet. */
const val ROUTE_NOT_READY_FA = "مسیر انتشار این شرکت را تیم فنی وصل میکند؛ بعد خودش منتشر میشود."
const val ROUTE_NOT_READY_SHORT_FA = "تیم فنی مسیر انتشار را وصل میکند"

/** [fa]: what the owner reads; [technical]: the sentences with their commands, for «جزئیات فنی» (null when there are none). */
data class OwnerNote(val fa: String, val technical: String?)

/** [text] split into what the owner reads and the technical sentences (with their commands) that go one tap away. */
fun ownerNote(text: String?): OwnerNote {
    val t = text.orEmpty().trim()
    if (t.isEmpty() || !COMMAND.containsMatchIn(t)) return OwnerNote(t, null)
    val sentences = t.split(SENTENCE_END)
    val tech = sentences.filter { COMMAND.containsMatchIn(it) }
    val keep = sentences.filterNot { COMMAND.containsMatchIn(it) }.toMutableList()
    if (tech.any { ROUTE_WORDS.containsMatchIn(it) }) keep += ROUTE_NOT_READY_FA
    return OwnerNote(keep.joinToString(" ").trim(), tech.joinToString(" ").trim().ifEmpty { null })
}

// ⟨1.17⟩ The owner reads plain short Persian: never a ref (W-000153, F-0007, CV-0012, D-000085), a role's code (TY-MEDIA-MGR, role@CODE).
// The hub's own texts are already humanized (§29.7); this is the app's second line of defence where a line of the hub's is shown
// compact (a notification's row). A ref is dropped with its brackets and joiners, so the sentence still reads whole. The web's
// lib/plain.ts `plain`, rule for rule (the word «توکن» is left as the hub wrote it here).
private val OWNER_REF = Regex("\\b[A-Z]{1,3}-\\d{3,}\\b")
private val OWNER_CODE = Regex("\\b[A-Z][A-Z0-9]{1,9}-(?:[A-Z]{2,12}-(?:MGR|\\d{1,3})|CEO|ADV|OVR|AST|SYS|LIB|ARC|SEC|SRE)\\b")
private val OWNER_PERSONA = Regex("\\b[a-z_]+@[A-Z]{2,5}\\b")

/** [text] without refs and role codes; the rest untouched. */
fun withoutCodes(text: String?): String {
    if (text.isNullOrEmpty()) return ""
    return text.replace(OWNER_REF, "").replace(OWNER_PERSONA, "").replace(OWNER_CODE, "")
        .replace(Regex("[(\\[«]\\s*[)\\]»]"), "") // brackets that held only a ref
        .replace(Regex("\\s*[،,]\\s*(?=[،,.؛:])"), "") // a comma left against another mark
        .replace(Regex("(^|\\s)[،,:؛]\\s*")) { it.groupValues[1] } // a mark left at the start
        .replace(Regex("\\s+([،.؛:!؟])"), "$1")
        .replace(Regex("\\s{2,}"), " ")
        .trim()
}
