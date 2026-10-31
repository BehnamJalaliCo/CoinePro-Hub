package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

// ----------------------------------------------------------------- v1.10 --
// Contract §28 (prompt 19): outputs archived or deleted several at once, the deep company catalogue, the watch (دیده‌بان: security,
// app health, code review, growth and the holding's proposals as overseer findings), the apps' own error reports, and the council's
// failures in plain Persian. Same rules as Models.kt: camelCase here, snake_case on the wire; a field the hub omits takes its default.

/** §28.1 `POST /deliverables/file {refs}`: each output filed as `/{ref}/file` does, idempotent per ref. */
@Serializable
data class FiledRecord(val ref: String, val record: String)

@Serializable
data class FiledMany(val records: List<FiledRecord> = emptyList())

/** §28.1 `DELETE /deliverables {refs}` 🔏: how many rows went (only an Audit line stays). */
@Serializable
data class DeletedOut(val deleted: Int = 0)

// --------------------------------------------------------------- catalogue --
/** One table of a catalogue section: its columns and rows (a cell is text or a number; never a secret, never a row's contents). A row
 *  is a list of cells, or an object keyed by the columns (some models write it so); a table without columns takes its rows' keys. */
@Serializable
data class CatalogueTable(
    val titleFa: String? = null,
    val columns: List<String> = emptyList(),
    val rows: List<JsonElement> = emptyList(),
) {
    /** The header: the columns, or the keys of the rows when they are objects, or none. */
    val header: List<String> get() = columns.ifEmpty {
        rows.filterIsInstance<JsonObject>().flatMap { it.keys }.distinct().ifEmpty {
            val n = rows.maxOfOrNull { (it as? JsonArray)?.size ?: 1 } ?: 0
            List(n) { "" }
        }
    }

    /** A cell as text: a string as is, a number or a boolean as written, null as a dash, a list joined, an object as «key: value». */
    fun cell(r: Int, c: Int): String {
        val row = rows.getOrNull(r) ?: return "—"
        val e = when (row) {
            is JsonArray -> row.getOrNull(c)
            is JsonObject -> header.getOrNull(c)?.let { row[it] } ?: row.values.toList().getOrNull(c)
            else -> if (c == 0) row else null
        }
        return text(e)
    }

    companion object {
        /** Any JSON value as words for a cell or a line. */
        fun text(e: JsonElement?): String = when (e) {
            null, JsonNull -> "—"
            is JsonPrimitive -> e.content
            is JsonArray -> e.joinToString("، ") { text(it) }
            is JsonObject -> e.entries.joinToString(" · ") { (k, v) -> "$k: ${text(v)}" }
        }
    }
}

/**
 * One part of the catalogue (products, automations, data, interfaces, code, risks…): `{title_fa, summary_fa, tables: [{title_fa,
 * columns, rows}], notes_fa: [..]}`. The older `summary_md` / `notes_md` still read. Any text may carry JSON a model wrote into it; the
 * app renders that as a table or a list, never raw ([com.coinepro.hq.core.data.JsonBits]).
 */
@Serializable
data class CatalogueSection(
    /** products · automations · data · interfaces · code · risks (or another key the hub adds). */
    val key: String = "",
    val titleFa: String = "",
    val summaryFa: String? = null,
    val summaryMd: String? = null,
    val tables: List<CatalogueTable> = emptyList(),
    /** A list of lines (or one text, from an older hub). */
    val notesFa: JsonElement? = null,
    val notesMd: String? = null,
    /** How many things the section found, when the hub counts them. */
    val count: Int? = null,
) {
    val summary: String? get() = summaryFa?.takeIf { it.isNotBlank() } ?: summaryMd?.takeIf { it.isNotBlank() }

    /** The notes as lines. */
    val notes: List<String> get() = when (val n = notesFa) {
        is JsonArray -> n.mapNotNull { (it as? JsonPrimitive)?.content ?: it.toString() }.filter { it.isNotBlank() }
        is JsonPrimitive -> listOfNotNull(n.content.takeIf { it.isNotBlank() && n.isString })
        else -> listOfNotNull(notesMd?.takeIf { it.isNotBlank() })
    }
}

/** A paired server's part of a catalogue run (§26): which server, and how far its read-only job is. */
@Serializable
data class CatalogueServer(
    val id: String = "",
    val name: String = "",
    /** queued · running · done · failed */
    val state: String = "queued",
    val reasonFa: String? = null,
)

/** §28.2 `GET /companies/{code}/catalogue`: the latest deep extraction of a company, filed in the archive as a `report` record. */
@Serializable
data class Catalogue(
    val company: String = "",
    val at: String? = null,
    /** running · done · failed */
    val state: String = "running",
    /** The archive record it was filed as (`AR-…`), once done. */
    val record: String? = null,
    /** The owner's deliverable of it (`O-…`), once done. */
    val deliverable: String? = null,
    val reasonFa: String? = null,
    val servers: List<CatalogueServer> = emptyList(),
    val sections: List<CatalogueSection> = emptyList(),
) {
    val running: Boolean get() = state == "running"
}

// -------------------------------------------------------------- the watch --
/** §28.3 a watch finding's proposed fix, waiting for the owner: a work item, a Code Workshop session or a card for the seal. */
@Serializable
data class FindingFix(
    /** work · workshop · decision */
    val kind: String = "work",
    val ref: String? = null,
    val summaryFa: String? = null,
)

// ------------------------------------------------------- app error reports --
/** §28.3 `POST /client/errors` answer: how many entries the hub kept (a repeated one is not stored twice). */
@Serializable
data class ClientErrorsOut(val accepted: Int = 0)

// ------------------------------------------------------- review fixes --
/** ⟨1.7.4⟩ `GET /work/{id}/tree-events`: a work event (`work.<kind>`) or an agent run's step (`run.step`) anywhere in the tree. */
@kotlinx.serialization.Serializable
data class TreeEvent(
    val id: String = "",
    val at: String = "",
    val kind: String = "",
    val workId: String = "",
    val workRef: String = "",
    val depth: Int = 0,
    val actorKind: String = "",
    val actorCode: String = "",
    val data: JsonObject = JsonObject(emptyMap()),
)
