package com.coinepro.hq.core.data

import com.coinepro.hq.core.net.CatalogueTable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Text a model wrote may carry JSON (`… "rows": [["n8n", 14]] …`, a whole `{columns, rows}` or a list): the app never shows it raw.
 * [split] cuts a text into its prose and its data; [shape] says how a piece of data is drawn (a table or a list of lines).
 */
object JsonBits {
    sealed interface Part {
        data class Prose(val text: String) : Part
        data class Data(val value: JsonElement) : Part
    }

    /** How a piece of data is drawn. */
    sealed interface Shape {
        data class Table(val table: CatalogueTable) : Shape
        data class Lines(val lines: List<String>) : Shape
    }

    /** [text] as prose and data, in order; a text with no JSON in it is one prose part. Punctuation left between two pieces of data
     *  (", ") is dropped. */
    fun split(text: String): List<Part> {
        val out = mutableListOf<Part>()
        var i = 0
        var prose = StringBuilder()
        fun flushProse() {
            val p = prose.toString().trim().trim(',', '،', ';', '؛', ':').trim()
            if (p.isNotEmpty()) out += Part.Prose(p)
            prose = StringBuilder()
        }
        while (i < text.length) {
            val ch = text[i]
            if (ch == '{' || ch == '[') {
                val end = closing(text, i)
                if (end > i) {
                    // A `"key": [...]` written without its braces: the key goes with its value.
                    val key = Regex("\"([^\"\\n]{1,60})\"\\s*:\\s*$").find(prose)
                    val candidate = text.substring(i, end + 1)
                    val parsed = parse(candidate)
                    if (parsed != null && (parsed is JsonObject || parsed is JsonArray)) {
                        val value = if (key != null) {
                            val name = key.groupValues[1]
                            prose.setLength(key.range.first)
                            JsonObject(mapOf(name to parsed))
                        } else parsed
                        flushProse()
                        out += Part.Data(value)
                        i = end + 1
                        continue
                    }
                }
            }
            prose.append(ch)
            i++
        }
        flushProse()
        return merge(out)
    }

    /** Whether [text] carries any JSON. */
    fun hasData(text: String?): Boolean = text != null && split(text).any { it is Part.Data }

    /** How [e] is drawn: `{columns, rows}` or `{rows}` a table; a list of lists or of objects a table; a list of plain values lines;
     *  one key holding any of those, that; any other object a two-column table of its keys and values. */
    fun shape(e: JsonElement): Shape = when (e) {
        is JsonObject -> when {
            e["rows"] is JsonArray -> Shape.Table(CatalogueTable(
                (e["title_fa"] as? JsonPrimitive)?.content,
                (e["columns"] as? JsonArray)?.map { CatalogueTable.text(it) }.orEmpty(),
                (e["rows"] as JsonArray).toList(),
            ))
            e.size == 1 && e.values.first() is JsonArray -> shape(e.values.first()).let { s ->
                if (s is Shape.Table) Shape.Table(s.table.copy(titleFa = s.table.titleFa ?: e.keys.first())) else s
            }
            else -> Shape.Table(CatalogueTable(null, listOf("", ""), e.entries.map { (k, v) -> JsonArray(listOf(JsonPrimitive(k), JsonPrimitive(CatalogueTable.text(v)))) }))
        }
        is JsonArray -> when {
            e.isNotEmpty() && e.all { it is JsonArray || it is JsonObject } -> Shape.Table(CatalogueTable(null, emptyList(), e.toList()))
            else -> Shape.Lines(e.map { CatalogueTable.text(it) })
        }
        else -> Shape.Lines(listOf(CatalogueTable.text(e)))
    }

    /** Strict JSON only (the app's own decoder is lenient: «[ریسک]» would read as a list). */
    private fun parse(s: String): JsonElement? = runCatching { kotlinx.serialization.json.Json.parseToJsonElement(s) }.getOrNull()?.takeIf(::strict)

    /** The parser takes a bare word as a value; JSON does not: every unquoted value must be a number, true, false or null. */
    private fun strict(e: JsonElement): Boolean = when (e) {
        is JsonObject -> e.values.all(::strict)
        is JsonArray -> e.all(::strict)
        is JsonPrimitive -> e.isString || e.content == "null" || e.content == "true" || e.content == "false" || e.content.toDoubleOrNull() != null
    }

    /** The index of the bracket closing the one at [start] (strings and escapes respected), or -1. */
    private fun closing(t: String, start: Int): Int {
        var depth = 0
        var inString = false
        var i = start
        while (i < t.length) {
            val ch = t[i]
            if (inString) {
                if (ch == '\\') i++ else if (ch == '"') inString = false
            } else when (ch) {
                '"' -> inString = true
                '{', '[' -> depth++
                '}', ']' -> { depth--; if (depth == 0) return i }
            }
            i++
        }
        return -1
    }

    /** Two pieces of data side by side (`"columns": [..], "rows": [..]`) are one object. */
    private fun merge(parts: List<Part>): List<Part> {
        val out = mutableListOf<Part>()
        for (p in parts) {
            val last = out.lastOrNull()
            if (p is Part.Data && last is Part.Data && p.value is JsonObject && last.value is JsonObject) {
                out[out.lastIndex] = Part.Data(JsonObject(last.value + p.value))
            } else out += p
        }
        return out
    }
}
