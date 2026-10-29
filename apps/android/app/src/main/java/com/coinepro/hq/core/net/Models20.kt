package com.coinepro.hq.core.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// ------------------------------------------------------------------ v1.7 --
// Contract §23 (prompt 14): the archive of record, open-layered. Records, versions and files sealed on their manifest; classes and their
// fields (the open layer) over a closed list of field types; the file plan, parties and link kinds; levels and clearance; retention,
// disposal by the owner's seal and legal holds; reminders; automations over a closed vocabulary; system sources; search; the schema API.
// §23.12 ⟨1.7.1⟩ fixes the shapes both apps read. Same rules as Models.kt: camelCase here, snake_case on the wire, nullable exactly where
// §23 writes `|null`. Everything that describes the archive is data: the schema is kept whole (`raw`) for the open-layer editor, and the
// typed lists below are read from it, so a new part or a new field type needs no new release. Scopes are data: nothing here counts them.

/** The schema parts `PUT /archive/schema/{part}/{key}` takes, in their tab order (§23.10). */
val SCHEMA_PARTS = listOf("classes", "folders", "levels", "clearance", "retention", "reminders", "party_kinds", "link_kinds", "automations")

/** Parts keyed by ref: created with key `new`, the server assigns the ref (§23.12). */
val REF_PARTS = setOf("folders", "retention", "reminders", "automations")

// ------------------------------------------------------------------ the open layer (§23.2–§23.8) --
@Serializable
data class FieldOption(val key: String = "", val titleFa: String = "")

/** One field of a class or a party kind; `sensitive` is masked below `confidential`. */
@Serializable
data class FieldDef(
    val key: String,
    val titleFa: String = "",
    /** A key of the closed list `field_types` (text, money, date, ref, iban, …). */
    val type: String = "text",
    val required: Boolean = false,
    val searchable: Boolean = false,
    val sensitive: Boolean = false,
    val options: List<FieldOption> = emptyList(),
    val refKinds: List<String> = emptyList(),
    val currency: String? = null,
    val helpFa: String? = null,
    /** active · retired: a field is never deleted. */
    val status: String = "active",
)

@Serializable
data class AutoLink(val field: String = "", val linkKind: String = "")

@Serializable
data class RecordClass(
    val key: String,
    val titleFa: String = "",
    val parent: String? = null,
    /** "all" or a list of scopes. */
    val scopes: JsonElement = JsonPrimitive("all"),
    val icon: String = "report",
    val defaultLevel: String = "internal",
    val defaultFolder: String? = null,
    val fields: List<FieldDef> = emptyList(),
    val requiredFiles: Int = 0,
    val allowedMime: List<String> = emptyList(),
    val ocr: Boolean = false,
    val retention: String? = null,
    val reminderFields: List<String> = emptyList(),
    val autoLink: List<AutoLink> = emptyList(),
    val version: Int = 1,
    val status: String = "active",
    /** Records filed under it (any class version). */
    val records: Int = 0,
) {
    fun inScope(scope: String): Boolean = (scopes as? JsonPrimitive)?.contentOrNull == "all" || (scopes as? JsonArray)?.any { (it as? JsonPrimitive)?.contentOrNull == scope } == true
}

@Serializable
data class FolderNode(
    val ref: String,
    val scope: String = "HQ",
    val parent: String? = null,
    val titleFa: String = "",
    val classes: List<String> = emptyList(),
    val defaultLevel: String? = null,
    val order: Int = 0,
    val status: String = "active",
    val version: Int? = null,
    val records: Int = 0,
)

@Serializable
data class PartyKind(
    val key: String,
    val titleFa: String = "",
    val identifierFields: List<FieldDef> = emptyList(),
    val version: Int? = null,
    val status: String = "active",
    val parties: Int = 0,
)

@Serializable
data class Party(
    val ref: String,
    val kind: String = "other",
    val nameFa: String = "",
    val nameEn: String? = null,
    val identifiers: Map<String, JsonElement> = emptyMap(),
    val scopes: List<String> = emptyList(),
    val status: String = "active",
    val version: Int? = null,
    val records: Int = 0,
)

@Serializable
data class LinkKind(
    val key: String,
    val titleFa: String = "",
    val inverseFa: String = "",
    val toKinds: List<String> = emptyList(),
    val version: Int? = null,
    val status: String = "active",
    val records: Int = 0,
)

/** A level of the archive: seeded 0, 10, 20, 30 (عمومی، داخلی، محرمانه، سری); a used level's rank never changes (§23.4, §23.12). */
@Serializable
data class Level(
    val key: String,
    val titleFa: String = "",
    val rank: Int = 0,
    val colorIndex: Int = 0,
    val watermark: Boolean = false,
    val encrypt: Boolean = false,
    val stepUpToView: Boolean = false,
    val agentsMax: Boolean = false,
    val version: Int? = null,
    val status: String = "active",
    val records: Int = 0,
)

@Serializable
data class RetentionRule(
    val ref: String,
    val titleFa: String = "",
    /** filed · field:<key> · case_closed · superseded */
    val trigger: String = "filed",
    /** {years?, months?} or "permanent". */
    val keep: JsonElement = JsonPrimitive("permanent"),
    /** review · dispose_card */
    val then: String = "review",
    val version: Int = 1,
    val status: String = "active",
    val records: Int = 0,
) {
    val permanent: Boolean get() = (keep as? JsonPrimitive)?.contentOrNull == "permanent"
    val years: Int get() = ((keep as? JsonObject)?.get("years") as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull()?.toInt() ?: 0
    val months: Int get() = ((keep as? JsonObject)?.get("months") as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull()?.toInt() ?: 0
}

@Serializable
data class ReminderRule(
    val ref: String,
    @SerialName("class") val cls: String = "",
    val field: String = "",
    val leadDays: List<Int> = emptyList(),
    /** "owner", {role} or {company_ceo: true}. */
    val to: JsonElement = JsonPrimitive("owner"),
    /** cartable · digest */
    val channel: String = "cartable",
    val version: Int = 1,
    val status: String = "active",
)

@Serializable
data class Automation(
    val ref: String,
    val titleFa: String = "",
    val on: String = "filed",
    @SerialName("when") val cond: JsonObject = JsonObject(emptyMap()),
    @SerialName("do") val steps: List<JsonObject> = emptyList(),
    val version: Int = 1,
    val status: String = "active",
    @SerialName("runs_30d") val runs30d: Int = 0,
    val lastRunAt: String? = null,
)

/** One switch of `GET /archive/sources` (§23.8, §23.12). */
@Serializable
data class SourceSwitch(
    val key: String = "",
    val titleFa: String = "",
    @SerialName("class") val cls: String = "",
    val enabled: Boolean = false,
    val filed: Int = 0,
    val lastAt: String? = null,
    val noteFa: String? = null,
)

@Serializable
data class FieldType(val key: String, val titleFa: String = "")

/** The rest of the closed vocabulary travels with the schema, so no editor hard-codes it (§23.12). */
@Serializable
data class Vocab(
    val events: List<String> = emptyList(),
    val actions: List<String> = emptyList(),
    val ops: List<String> = emptyList(),
    val refKinds: List<String> = emptyList(),
    val currencies: List<String> = emptyList(),
    val mimes: List<String> = emptyList(),
)

/** `GET /archive/schema`, whole: [raw] is what the open-layer editor draws from; the typed lists are read from it. */
class ArchiveSchema(val raw: JsonObject) {
    private fun <T> listOf(key: String, s: kotlinx.serialization.KSerializer<T>): List<T> = (raw[key] as? JsonArray)?.let { Api.json.decodeFromJsonElement(ListSerializer(s), it) }.orEmpty()

    val classes: List<RecordClass> = listOf("classes", RecordClass.serializer())
    val fieldTypes: List<FieldType> = listOf("field_types", FieldType.serializer())
    val folders: List<FolderNode> = listOf("folders", FolderNode.serializer()).sortedBy { it.order }
    val levels: List<Level> = listOf("levels", Level.serializer()).sortedBy { it.rank }
    val retention: List<RetentionRule> = listOf("retention", RetentionRule.serializer())
    val reminders: List<ReminderRule> = listOf("reminders", ReminderRule.serializer())
    val partyKinds: List<PartyKind> = listOf("party_kinds", PartyKind.serializer())
    val parties: List<Party> = listOf("parties", Party.serializer())
    val linkKinds: List<LinkKind> = listOf("link_kinds", LinkKind.serializer())
    val automations: List<Automation> = listOf("automations", Automation.serializer())
    val sources: List<SourceSwitch> = listOf("sources", SourceSwitch.serializer())
    val vocab: Vocab = (raw["vocab"] as? JsonObject)?.let { Api.json.decodeFromJsonElement(Vocab.serializer(), it) } ?: Vocab()

    /** The rows of one part as the editor reads them; clearance comes one row per grant or grouped per subject (§23.12), read either way. */
    fun rows(part: String): List<JsonObject> {
        val xs = (raw[part] as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()
        return if (part == "clearance") clearanceRows(xs) else xs
    }

    /** Every array of the schema that is a part (a part added on the hub is edited with the generic editor). */
    val parts: List<String> get() = SCHEMA_PARTS + raw.keys.filter { it !in SCHEMA_PARTS && it !in NOT_PARTS && raw[it] is JsonArray }

    override fun equals(other: Any?): Boolean = other is ArchiveSchema && other.raw == raw
    override fun hashCode(): Int = raw.hashCode()

    companion object {
        private val NOT_PARTS = setOf("field_types", "parties", "sources", "vocab")

        /** Clearance rows grouped per subject `{subject: {kind, ref}, grants: [{scope, level}], metadata_level, version}`. */
        fun clearanceRows(raw: List<JsonObject>): List<JsonObject> {
            val by = LinkedHashMap<String, MutableMap<String, JsonElement>>()
            for (c in raw) {
                val s = c["subject"]
                val (kind, ref) = when (s) {
                    is JsonPrimitive -> s.content.substringBefore(':') to s.content.substringAfter(':', "")
                    is JsonObject -> ((s["kind"] as? JsonPrimitive)?.contentOrNull ?: "role") to ((s["ref"] as? JsonPrimitive)?.contentOrNull ?: "")
                    else -> "role" to ""
                }
                val k = "$kind:$ref"
                val cur = by.getOrPut(k) {
                    linkedMapOf(
                        "subject" to JsonObject(mapOf("kind" to JsonPrimitive(kind), "ref" to JsonPrimitive(ref))),
                        "grants" to JsonArray(emptyList()), "metadata_level" to (c["metadata_level"] ?: JsonNull), "version" to (c["version"] ?: JsonNull),
                    )
                }
                val grants = (c["grants"] as? JsonArray)?.toList() ?: listOf(JsonObject(mapOf("scope" to (c["scope"] ?: JsonNull), "level" to (c["level"] ?: JsonNull))))
                cur["grants"] = JsonArray((cur["grants"] as JsonArray) + grants)
            }
            return by.values.map { JsonObject(it) }
        }
    }
}

/** The server's impact of a schema change: records that use it, and how many would miss a new required field. */
@Serializable
data class Impact(val records: Int = 0, val missingRequired: Int = 0)

/** The answer of a schema PUT or retire; `?dry_run=1` answers the same without applying (no passkey). */
@Serializable
data class SchemaResult(
    val part: String = "",
    val key: String = "",
    val version: Int = 0,
    val impact: Impact = Impact(),
    val row: JsonObject? = null,
    val dryRun: Boolean = false,
)

// ------------------------------------------------------------------ records (§23.1) --
@Serializable
data class RecordFile(
    val fileId: String,
    val name: String = "",
    val mime: String = "",
    val sizeBytes: Long = 0,
    val sha256: String = "",
    val pages: Int? = null,
    /** none · text_layer · ocr · failed */
    val textState: String = "none",
    val ocrConfidence: Double? = null,
)

@Serializable
data class RecordVersion(
    val n: Int,
    val files: List<RecordFile> = emptyList(),
    /** SHA-256 of the sorted "sha256  name" lines: the seal is bound to it. */
    val manifestSha256: String = "",
    val noteFa: String? = null,
    val createdBy: Actor? = null,
    val createdAt: String = "",
    val sealed: Boolean = false,
    /** current · superseded */
    val state: String? = null,
)

@Serializable
data class LinkTarget(val kind: String, val ref: String)

/** A link, read as §23.1 writes it (`to: {kind, ref}`) or flat as §23.12 lists it (`to_kind`, `to_ref`). A sealed link is never removed;
 *  `inverse` is a link another record holds to this one, shown with the kind's `inverse_fa`. */
@Serializable
data class RecordLink(
    val kind: String,
    val to: LinkTarget? = null,
    val toKind: String? = null,
    val toRef: String? = null,
    val titleFa: String? = null,
    val at: String? = null,
    val by: Actor? = null,
    val sealed: Boolean = false,
    val inverse: Boolean = false,
) {
    val target: LinkTarget get() = to ?: LinkTarget(toKind ?: "record", toRef ?: "")
}

@Serializable
data class PartyRole(val party: String, val roleFa: String = "")

@Serializable
data class RecordRetention(val rule: String? = null, val triggerAt: String? = null, val reviewAt: String? = null, val disposable: Boolean = false)

@Serializable
data class RecordReminder(val field: String, val at: String, val leadDays: Int = 0, val state: String = "pending")

@Serializable
data class RecordSource(val kind: String = "owner", val ref: String? = null)

/** A draft's suggestion, by the rules or the archivist: never filed by itself. */
@Serializable
data class Suggestion(
    @SerialName("class") val cls: String? = null,
    val titleFa: String? = null,
    val metadata: Map<String, JsonElement> = emptyMap(),
    val parties: List<String> = emptyList(),
    /** rules · archivist */
    val by: String = "rules",
    val noteFa: String? = null,
)

@Serializable
data class HashRow(val name: String = "", val sha256: String = "")

/** What stays after the owner's disposal seal: the decision, when, and one hash per destroyed file. */
@Serializable
data class Tombstone(val decision: String = "", val at: String = "", val hashes: List<HashRow> = emptyList())

@Serializable
data class ArchiveRecord(
    val id: String = "",
    val ref: String,
    val scope: String = "HQ",
    /** null on a draft from import. */
    @SerialName("class") val cls: String? = null,
    val classVersion: Int? = null,
    val titleFa: String = "",
    val folder: String? = null,
    val level: String = "internal",
    /** draft · filed · sealed · superseded · disposed */
    val state: String = "filed",
    val metadata: Map<String, JsonElement> = emptyMap(),
    val parties: List<PartyRole> = emptyList(),
    val links: List<RecordLink> = emptyList(),
    val holds: List<String> = emptyList(),
    val retention: RecordRetention = RecordRetention(),
    val reminders: List<RecordReminder> = emptyList(),
    val currentVersion: Int = 1,
    val versions: List<RecordVersion> = emptyList(),
    val source: RecordSource = RecordSource(),
    val createdBy: Actor? = null,
    val createdAt: String = "",
    val filedAt: String? = null,
    val sealedAt: String? = null,
    /** The row version, for If-Match. */
    val version: Int = 1,
    // ⟨1.7.1⟩ the document's own date (what from/to filter on), the fields masked for this reader, a draft's suggestion, a tombstone.
    val docDate: String? = null,
    val masked: List<String> = emptyList(),
    val suggestion: Suggestion? = null,
    val tombstone: Tombstone? = null,
) {
    val current: RecordVersion? get() = versions.firstOrNull { it.n == currentVersion } ?: versions.maxByOrNull { it.n }
}

/** The filters of `GET /archive/records` (§23.1). */
data class RecordFilters(
    val scope: String? = null,
    val cls: String? = null,
    val folder: String? = null,
    val level: String? = null,
    val state: String? = null,
    val party: String? = null,
    val q: String? = null,
    val from: String? = null,
    val to: String? = null,
    val expiringWithinDays: Int? = null,
    val held: Boolean? = null,
) {
    fun query(): Map<String, Any?> = linkedMapOf(
        "scope" to scope, "class" to cls, "folder" to folder, "level" to level, "state" to state, "party" to party, "q" to q?.trim()?.takeIf { it.length >= 2 },
        "from" to from, "to" to to, "expiring_within_days" to expiringWithinDays, "held" to held,
    )
    val key: String get() = query().entries.joinToString(":") { "${it.value ?: ""}" }
}

/** `POST /archive/records`: the owner may file at once (`file: true`); otherwise a draft. */
@Serializable
data class RecordIn(
    val scope: String,
    @SerialName("class") val cls: String,
    val titleFa: String,
    val metadata: Map<String, JsonElement>,
    val level: String? = null,
    val folder: String? = null,
    val fileIds: List<String>,
    val parties: List<PartyRole>,
    val file: Boolean,
)

@Serializable
data class ArchiveHit(val ref: String, val titleFa: String = "", @SerialName("class") val cls: String? = null, val snippetFa: String = "", val score: Double = 0.0)

/** A row of the access log (owner only); a level change is a row with action `level` and the two level keys. */
@Serializable
data class AccessRow(
    val at: String = "",
    val actor: Actor? = null,
    /** view · download · metadata · level */
    val action: String = "view",
    val fileId: String? = null,
    val version: Int? = null,
    val stepUp: Boolean = false,
    val watermarked: Boolean = false,
    val levelFrom: String? = null,
    val levelTo: String? = null,
)

/** `POST /archive/intake`: the secret scan, hashes and text of files just uploaded, and the rule-based suggestion. */
@Serializable
data class Intake(val files: List<RecordFile> = emptyList(), val suggestion: Suggestion? = null)

/** A record's file as the hub served it (watermarked when its level says so). */
class FileBytes(val bytes: ByteArray, val mime: String)

// ------------------------------------------------------------------ holds, reminders, retention, fixity (§23.5, §23.6, §23.10) --
@Serializable
data class HoldScope(
    val records: List<String> = emptyList(),
    val folders: List<String> = emptyList(),
    val classes: List<String> = emptyList(),
    val parties: List<String> = emptyList(),
    val from: String? = null,
    val to: String? = null,
) {
    val empty: Boolean get() = records.isEmpty() && folders.isEmpty() && classes.isEmpty() && parties.isEmpty() && from == null && to == null
}

@Serializable
data class LegalHold(
    val ref: String,
    val titleFa: String = "",
    val case: String? = null,
    val reasonMd: String = "",
    val scope: HoldScope = HoldScope(),
    /** active · released */
    val state: String = "active",
    val placedBy: Actor? = null,
    val placedAt: String = "",
    val releasedAt: String? = null,
    /** What it covers now, within the reader's clearance. */
    val records: Int = 0,
    val recordRefs: List<String> = emptyList(),
)

@Serializable
data class HoldIn(val titleFa: String, val case: String?, val reasonMd: String, val scope: JsonObject)

@Serializable
data class DueReminder(
    val id: String = "",
    val record: String = "",
    val titleFa: String = "",
    val scope: String = "HQ",
    @SerialName("class") val cls: String? = null,
    val field: String = "",
    val at: String = "",
    val leadDays: Int = 0,
    val daysLeft: Int = 0,
    val state: String = "sent",
    val rule: String? = null,
    val to: JsonElement = JsonPrimitive("owner"),
    val channel: String = "cartable",
)

@Serializable
data class RetentionDue(
    val ref: String,
    val titleFa: String = "",
    val scope: String = "HQ",
    @SerialName("class") val cls: String? = null,
    val rule: String = "",
    val triggerAt: String? = null,
    val dueAt: String = "",
    val then: String = "review",
    val holds: List<String> = emptyList(),
    val decisionRef: String? = null,
)

@Serializable
data class Fixity(val at: String = "", val checked: Int = 0, val failed: List<String> = emptyList(), val nextAt: String? = null)

@Serializable
data class PartyIn(val kind: String, val nameFa: String, val nameEn: String?, val identifiers: Map<String, JsonElement>, val scopes: List<String>)

// ------------------------------------------------------------------ the §23 cards (§23.11, §23.12) --
/** The decision kinds of §23, both sealed with the usual `decision.approve` step-up, target the card's ref. */
val ARCHIVE_KINDS = setOf("archive_schema", "archive_disposal")

/** `archive_schema`: the exact PUT, with the row version it was written against and the impact the server measured. */
@Serializable
data class SchemaCardPayload(val part: String = "", val key: String = "", val baseVersion: Int? = null, val body: JsonObject = JsonObject(emptyMap()), val impact: Impact? = null)

@Serializable
data class DisposalRow(val ref: String, @SerialName("class") val cls: String? = null, val titleFa: String = "", val retentionRule: String = "", val triggerAt: String? = null)

@Serializable
data class DisposalCardPayload(val records: List<DisposalRow> = emptyList())

// ------------------------------------------------------------------ codes (§23.11, §14) --
private val CODE_FA_20 = mapOf(
    "clearance" to "این سند بالاتر از مجوز دیدن است.",
    "sealed_record" to "این سند مُهر خورده و دیگر عوض نمیشود؛ اصلاح یعنی نسخه‌ی تازه.",
    "schema_invalid" to "این تغییر با واژگان بسته‌ی بایگانی نمیخواند؛ چیزی ذخیره نشد.",
    "secret_in_document" to "در این فایل الگوی رمز، کلید خصوصی یا عبارت بازیابی پیدا شد؛ فایل ذخیره نشد و هیچ بخشی از آن ثبت نشد.",
    "held" to "این سند توقیف قانونی دارد؛ جز نسخه‌ی تازه هیچ تغییری نمیپذیرد.",
    "version_conflict" to "همین حالا عوض شده؛ دوباره نگاه کن و بعد ذخیره کن.",
    "precondition_required" to "نسخه همراه درخواست نیامد؛ صفحه را تازه کن.",
    "step_up_required" to "این کار تأیید با اثر انگشت یا چهره میخواهد.",
    "decision_not_pending" to "این کارت دیگر منتظر تصمیم نیست.",
    "not_found" to "پیدا نشد.",
    "not_ready" to "این کار روی این نسخه‌ی سرور هنوز آماده نیست.",
)

/** The Persian sentence for a failed §23 call: its stable codes in the app's words; a refused schema change or record names what failed
 *  (the server's own sentence, with the fields); the server's sentence for everything else. */
fun archiveError(e: ApiException): String {
    if ((e.code == "schema_invalid" || e.code == "validation_failed") && e.messageFa.isNotBlank()) return e.messageFa
    return CODE_FA_20[e.code] ?: e.messageFa
}
