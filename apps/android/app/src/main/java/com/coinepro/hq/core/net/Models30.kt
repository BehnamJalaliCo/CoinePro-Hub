package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

// ----------------------------------------------------------------- v1.12 --
// Contract §30 (prompt 22): production lines. A template is the plan of steps, a line is a template set for one company, one platform
// and one channel, a run is one pass of a line, step by step. Same rules as Models.kt: camelCase here, snake_case on the wire; a field the
// hub omits takes its default (so a newer hub never breaks the screens).

/** One step of a template or of a line (§30.1 StepDef). [settings] is free-form (each kind reads its own keys). */
@Serializable
data class StepDef(
    val key: String,
    val kind: String = "",
    val titleFa: String = "",
    val promptFa: String? = null,
    val settings: JsonObject = JsonObject(emptyMap()),
    val inputs: List<String> = emptyList(),
    /** auto · owner · ceo */
    val gate: String = "auto",
    val optional: Boolean = false,
    val enabled: Boolean = true,
    val maxAttempts: Int = 1,
    /** ⟨2026-11-11⟩ audit: the hub's default (a step of 120 s was left out of a save as «the default» and came back as 300). */
    val timeoutS: Int = 300,
)

/** §30.1 LineTemplate: the plan of steps, named for no company. */
@Serializable
data class LineTemplate(
    val key: String,
    val titleFa: String = "",
    val platform: String = "",
    val version: Int = 1,
    val steps: List<StepDef> = emptyList(),
    val defaults: JsonObject = JsonObject(emptyMap()),
    /** ⟨2026-11-11⟩ audit: the hub sends a list (`list[str]`); an older answer's single string is read as one item. */
    @Serializable(with = StringList::class) val outputsFa: List<String> = emptyList(),
)

/** A list of strings that also takes a single string (one item) or null (none). */
object StringList : kotlinx.serialization.KSerializer<List<String>> {
    private val list = kotlinx.serialization.builtins.ListSerializer(kotlinx.serialization.serializer<String>())
    override val descriptor = list.descriptor
    override fun serialize(encoder: kotlinx.serialization.encoding.Encoder, value: List<String>) = list.serialize(encoder, value)
    override fun deserialize(decoder: kotlinx.serialization.encoding.Decoder): List<String> {
        val e = (decoder as? kotlinx.serialization.json.JsonDecoder)?.decodeJsonElement() ?: return list.deserialize(decoder)
        return when (e) {
            is kotlinx.serialization.json.JsonArray -> e.mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content }
            is JsonPrimitive -> if (e.isString && e.content.isNotBlank()) listOf(e.content) else emptyList()
            else -> emptyList()
        }
    }
}

@Serializable
data class LineChannel(val kind: String = "", val subject: String = "")

/** Per-line caps (§30.3): runs a day, tokens a run, Opus calls a day. */
@Serializable
data class LineCaps(val runsPerDay: Int? = null, val tokensPerRun: Long? = null, val opusPerDay: Int? = null)

/** The last run of a line, as the list shows it (the hub may leave it out: then the list shows nothing for it). */
@Serializable
data class LineLast(val ref: String = "", val state: String = "", val at: String? = null)

/** §30.1 Line. [nextAt] and [lastRun] are the list's conveniences (not in the contract's shape: absent means nothing to show). */
@Serializable
data class Line(
    val ref: String,
    val company: String = "",
    val template: String = "",
    val templateVersion: Int = 1,
    val platform: String = "",
    val channel: LineChannel = LineChannel(),
    val titleFa: String = "",
    val schedule: String? = null,
    /** draft · on · paused */
    val state: String = "draft",
    /** draft · auto */
    val mode: String = "draft",
    val goodRuns: Int = 0,
    val autoAfter: Int = 7,
    val caps: LineCaps = LineCaps(),
    val version: Int = 1,
    val steps: List<StepDef> = emptyList(),
    val library: List<String> = emptyList(),
    val createdAt: String? = null,
    val updatedAt: String? = null,
    /** The next time its schedule falls (the engine's `next_at`). */
    val nextAt: String? = null,
    /** The engine says the line has earned «خودکار کن». */
    val offerAuto: Boolean = false,
    val nameFa: String? = null,
    val copiedFrom: String? = null,
    val lastRun: LineLast? = null,
)

/** §30.1 LineVersion: the whole line as it was, who made the change and why. */
@Serializable
data class LineVersion(
    val line: String = "",
    val version: Int = 1,
    /** ⟨2026-11-11⟩ audit: the hub's body of a version (template, steps, caps… but no `ref`): kept as it came. */
    val body: JsonObject? = null,
    /** Who made it (`{kind, code}`). */
    val by: Actor? = null,
    val at: String? = null,
    val noteFa: String = "",
)

/** What a step produced (§30.1 StepRun.output). */
@Serializable
data class StepOutput(
    val text: String? = null,
    val fileId: String? = null,
    val files: List<String> = emptyList(),
    val data: JsonObject = JsonObject(emptyMap()),
) {
    /** Every file of the output once, the single [fileId] first. */
    val allFiles: List<String> get() = (listOfNotNull(fileId) + files).distinct()
    val isEmpty: Boolean get() = text.isNullOrBlank() && allFiles.isEmpty() && data.isEmpty()
}

@Serializable
data class StepRun(
    val key: String = "",
    val kind: String = "",
    /** pending · running · waiting · done · failed · skipped */
    val state: String = "pending",
    val attempt: Int = 1,
    val startedAt: String? = null,
    val endedAt: String? = null,
    val output: StepOutput = StepOutput(),
    val via: String? = null,
    val tokens: Long = 0,
    val usdEquiv: JsonPrimitive? = null,
    val errorFa: String? = null,
    val titleFa: String? = null,
    val gate: String? = null,
    val sealedAt: String? = null,
    val sealedBy: String? = null,
    /** The step's output was taken from the earlier run (a rerun from a later step). */
    val reused: Boolean = false,
    val missing: kotlinx.serialization.json.JsonElement? = null,
    // ⟨1.37⟩ §59.8 a flow's step: who, with what, at what cost, and what it left (a text file read in place)
    val seatFa: String? = null,
    val helper: String? = null,
    val model: String? = null,
    val effort: String? = null,
    val costUsd: Double? = null,
    val outputs: List<StepFile> = emptyList(),
)

@Serializable
data class RunCost(val tokens: Long = 0, val usdEquiv: JsonPrimitive? = null, val usd: Double? = null)

@Serializable
data class Published(val platform: String = "", val kind: String = "", val externalId: String? = null, val at: String? = null, val url: String? = null, val permalink: String? = null)

@Serializable
data class RunMetrics(val h24: JsonObject? = null, val d7: JsonObject? = null)

/** §30.1 Run. */
@Serializable
data class LineRun(
    val ref: String,
    val line: String = "",
    val lineVersion: Int = 1,
    /** schedule · owner · test · n8n · group */
    val trigger: String = "owner",
    val dry: Boolean = false,
    /** queued · running · waiting · done · failed · skipped · cancelled */
    val state: String = "queued",
    val at: String? = null,
    val endedAt: String? = null,
    val steps: List<StepRun> = emptyList(),
    val cost: RunCost = RunCost(),
    val published: List<Published> = emptyList(),
    val metrics: RunMetrics = RunMetrics(),
    val noteFa: String = "",
    /** The line's company and title, when the hub adds them to a run (the runs list reads them). */
    val company: String? = null,
    val titleFa: String? = null,
    val platform: String? = null,
    /** The card (`D-…`) that asks for the owner's seal while the run waits. */
    val decision: String? = null,
    val rerunOf: String? = null,
    val fromStep: String? = null,
    // ⟨1.37⟩ §59.8 a flow's run: its automation and playbook, the day's topic, what it published and how it did, its minutes
    val automation: String? = null,
    val playbook: String? = null,
    val playbookFa: String? = null,
    val version: Int? = null,
    val companyFa: String? = null,
    val topicFa: String? = null,
    val results: RunResults? = null,
    val minutes: Double? = null,
)

/** §30.1 Asset: a library entry of a company (or of the holding when [company] is null). */
@Serializable
data class Asset(
    val id: String,
    val company: String? = null,
    /** cover_folder · voice · prompt · pattern · music · brand */
    val kind: String = "prompt",
    val titleFa: String = "",
    val config: JsonObject = JsonObject(emptyMap()),
    val files: List<String> = emptyList(),
    val createdAt: String? = null,
)

/** §30.5 `GET /tts/voices`: a speaker the speech tool offers, with a sample file when there is one. */
@Serializable
data class TtsVoice(val name: String, val titleFa: String = "", val gender: String = "", val sampleFile: String? = null)

/** §30.5 the calendar: what is scheduled and what ran, by day. */
@Serializable
data class CalendarItem(
    val line: String = "",
    val company: String = "",
    val platform: String = "",
    val at: String? = null,
    val state: String = "scheduled",
    val run: String? = null,
    /** Optional: the line's title, when the hub adds it. */
    val titleFa: String? = null,
)

@Serializable
data class CalendarDay(val day: String = "", val items: List<CalendarItem> = emptyList())

@Serializable
data class LineCalendar(val days: List<CalendarDay> = emptyList())
