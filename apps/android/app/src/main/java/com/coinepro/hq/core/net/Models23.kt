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
/** One table of a catalogue section: its columns and rows (a cell is text or a number; never a secret, never a row's contents). */
@Serializable
data class CatalogueTable(
    val titleFa: String? = null,
    val columns: List<String> = emptyList(),
    val rows: List<List<JsonElement>> = emptyList(),
) {
    /** A cell as text: a string as is, a number or a boolean as written, null as a dash. */
    fun cell(r: Int, c: Int): String = when (val e = rows.getOrNull(r)?.getOrNull(c)) {
        null, JsonNull -> "—"
        is JsonPrimitive -> e.content
        is JsonArray -> e.joinToString("، ") { (it as? JsonPrimitive)?.content ?: it.toString() }
        is JsonObject -> e.toString()
    }
}

/** One part of the catalogue (products, automations, data, interfaces, code, risks…): a summary, tables and any notes. */
@Serializable
data class CatalogueSection(
    /** products · automations · data · interfaces · code · risks (or another key the hub adds). */
    val key: String = "",
    val titleFa: String = "",
    val summaryMd: String? = null,
    val tables: List<CatalogueTable> = emptyList(),
    val notesMd: String? = null,
    /** How many things the section found, when the hub counts them. */
    val count: Int? = null,
)

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
