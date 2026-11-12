package com.coinepro.hq.core.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// ----------------------------------------------------------------- v1.13 --
// Contract §31 (prompt 22): growth. The learning loop of a line, a ready company from a kit, the owned channel (newsletter), SEO rank and
// competitors, one campaign calendar, ad budgets that stop by themselves, and an automation from one sentence. Same rules as Models.kt:
// camelCase here, snake_case on the wire; a field the hub omits takes its default. An id the hub may write as a number or a string is read
// as a [JsonPrimitive] ([idText]).

/** An id the hub writes as a number or a string, as text. */
val JsonPrimitive.idText: String get() = contentOrNull.orEmpty()

// ---------------------------------------------------------------- §31.1 --
@Serializable
data class InsightBest(val hour: Int? = null, val lengthBucket: String? = null, val voice: String? = null, val patternSource: String? = null)

@Serializable
data class Insights(
    val line: String = "",
    val metric: String = "views",
    val windowRuns: Int = 0,
    val best: InsightBest = InsightBest(),
    val topHooks: List<String> = emptyList(),
    val lessonsFa: List<String> = emptyList(),
    val updatedAt: String? = null,
)

// ---------------------------------------------------------------- §31.2 --
@Serializable
data class KitLine(val template: String = "", val platform: String = "", val titleFa: String = "", val ref: String? = null, val whyFa: String? = null)

/** ⟨2026-11-11⟩ audit: the hub's kit parts are objects (`KitGroup`, `KitKpi`, `KitConnection`, `KitTeam`), never bare strings. */
@Serializable
data class KitGroup(val key: String = "", val titleFa: String = "")

@Serializable
data class KitKpi(val key: String = "", val nameFa: String = "", val card: String = "", val unit: String = "", val manual: Boolean = false)

@Serializable
data class KitConnection(val kind: String = "", val labelFa: String = "")

@Serializable
data class KitDepartment(val code: String = "", val nameFa: String = "")

@Serializable
data class KitTeam(val departments: List<KitDepartment> = emptyList(), val positions: Int = 0)

/** `GET /kits` (`KitSummary`): what a kit makes. */
@Serializable
data class Kit(
    val key: String,
    val titleFa: String = "",
    val purposeFa: String = "",
    val teamTemplate: String = "",
    val team: KitTeam? = null,
    val groups: List<KitGroup> = emptyList(),
    val lines: List<KitLine> = emptyList(),
    val kpis: List<KitKpi> = emptyList(),
    val connections: List<KitConnection> = emptyList(),
    val todoFa: List<String> = emptyList(),
    val defaults: JsonObject = JsonObject(emptyMap()),
)

/** `POST /companies/from-kit/preview`: the kit as it would be made for this company, and whether its code is free (nothing is created). */
@Serializable
data class KitPreview(
    val kit: Kit? = null,
    val code: String = "",
    val nameFa: String = "",
    val nameEn: String = "",
    val codeFree: Boolean = true,
    val problems: List<String> = emptyList(),
)

@Serializable
data class KitCompany(val code: String = "", val nameFa: String? = null)

/** `POST /companies/from-kit` (`KitCreated`): the company made, its lines as drafts, and what the owner still has to connect ([todoFa]). */
@Serializable
data class KitResult(
    val company: KitCompany = KitCompany(),
    val lines: List<KitLine> = emptyList(),
    val linesPending: List<KitLine> = emptyList(),
    val todoFa: List<String> = emptyList(),
)

// ---------------------------------------------------------------- §31.3 --
@Serializable
data class NlList(val id: JsonPrimitive = JsonPrimitive(""), val listmonkId: Long? = null, val name: String = "", val subscribers: Long = 0, val sizeLimit: Long? = null)

/** ⟨2026-11-11⟩ audit: as `CampaignOut` writes it: `list_id` (the list's number in the mail service) and `send_at`. */
@OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
@Serializable
data class NlCampaign(
    val id: JsonPrimitive = JsonPrimitive(""),
    @kotlinx.serialization.json.JsonNames("list_id") val list: JsonPrimitive? = null,
    val subject: String = "",
    /** draft · scheduled · running · finished · paused · cancelled (an older answer: sending · sent) */
    val state: String = "draft",
    @kotlinx.serialization.json.JsonNames("send_at") val scheduledAt: String? = null,
    val sent: Long? = null,
    val opens: Long? = null,
    val clicks: Long? = null,
    val bodyMd: String? = null,
)

@Serializable
data class Newsletter(val lists: List<NlList> = emptyList(), val campaigns: List<NlCampaign> = emptyList(), val sizeLimit: Long? = null, val noteFa: String? = null)

// ---------------------------------------------------------------- §31.4 --
@Serializable
data class Keyword(
    val id: JsonPrimitive = JsonPrimitive(""),
    val company: String = "",
    val phrase: String = "",
    val site: String = "",
    val targetUrl: String? = null,
    val state: String = "on",
)

@Serializable
data class RankDaily(val keyword: JsonPrimitive = JsonPrimitive(""), val day: String = "", val source: String = "search_console", val position: Double? = null, val url: String? = null)

@Serializable
data class Competitor(
    val id: JsonPrimitive = JsonPrimitive(""),
    val company: String = "",
    val nameFa: String = "",
    val site: String? = null,
    val instagram: String? = null,
    val youtube: String? = null,
    val telegram: String? = null,
    val state: String = "on",
)

@Serializable
data class CompetitorDaily(val competitor: JsonPrimitive = JsonPrimitive(""), val day: String = "", val key: String = "", val value: Double = 0.0, val source: String = "")

// ---------------------------------------------------------------- §31.5 --
@Serializable
data class CampaignItem(
    val day: String = "",
    val at: String? = null,
    val company: String = "",
    /** line · newsletter · ad · campaign · manual */
    val kind: String = "manual",
    val ref: String = "",
    val titleFa: String = "",
    val platform: String? = null,
    val state: String = "",
    val conflictFa: String? = null,
)

@Serializable
data class Campaign(
    val id: JsonPrimitive = JsonPrimitive(""),
    val company: String = "",
    val titleFa: String = "",
    val goalFa: String = "",
    val starts: String = "",
    val ends: String = "",
    val channels: List<String> = emptyList(),
    val budget: Double? = null,
    val state: String = "planned",
)

// ---------------------------------------------------------------- §31.6 --
/** ⟨2026-11-11⟩ audit: as `domain/ads.py` writes an account: its name, whether it is connected, whether its key is set. */
@Serializable
data class AdAccount(
    val platform: String = "", val labelFa: String = "", val state: String = "", val secret: String = "", val missingFa: List<String> = emptyList(),
    val lastReadAt: String? = null, val lastErrorFa: String? = null,
)

/** A campaign's day; conversions may be fractional (the platforms count a share of a purchase). */
@Serializable
data class AdDaily(
    val platform: String = "", val campaignId: String = "", val day: String = "", val spend: Double = 0.0, val clicks: Long = 0,
    val conversions: Double = 0.0, val revenue: Double = 0.0, val roas: Double? = null,
)

/** ⟨2026-11-11⟩ audit: as the hub writes a campaign: `campaign_id`, `name`, `status` (active · paused · removed). */
@Serializable
data class AdCampaign(
    val platform: String = "",
    @SerialName("campaign_id") val id: String = "",
    @SerialName("name") val titleFa: String? = null,
    /** active · paused · removed */
    @SerialName("status") val state: String = "active",
    /** rule · owner · platform */
    val pausedBy: String? = null,
    val pausedReasonFa: String? = null,
    val days: List<AdDaily> = emptyList(),
)

@Serializable
data class Ads(val accounts: List<AdAccount> = emptyList(), val campaigns: List<AdCampaign> = emptyList())

@Serializable
data class AdRule(
    val id: JsonPrimitive = JsonPrimitive(""),
    val company: String = "",
    /** meta · google (the rule's platform; set when it is made, never changed) */
    val platform: String = "",
    val scope: String = "account",
    val dailyCap: Double = 0.0,
    val windowDays: Int = 7,
    val minRoas: Double = 0.0,
    val minSpendBeforeJudging: Double = 0.0,
    /** pause · notify */
    val action: String = "notify",
    val state: String = "on",
)

// ---------------------------------------------------------------- §31.7 --
/** A run of an automation, when the hub lists them with it (`GET /automations/{ref}`). */
@Serializable
data class AutoRun(val at: String? = null, val state: String = "done", val noteFa: String = "")

@Serializable
data class GrowthAutomation(
    val ref: String,
    val company: String? = null,
    val sentenceFa: String = "",
    val rule: JsonObject = JsonObject(emptyMap()),
    /** proposed · on · off */
    val state: String = "proposed",
    /** The run count (a number) on the list; the list of runs on the one automation. */
    val runs: kotlinx.serialization.json.JsonElement? = null,
    val lastRunAt: String? = null,
    val n8nWorkflow: String? = null,
    val previewFa: String? = null,
) {
    val runList: List<AutoRun> get() = (runs as? JsonArray)?.mapNotNull { runCatching { Api.json.decodeFromJsonElement(AutoRun.serializer(), it) }.getOrNull() }.orEmpty()
    val runCount: Int get() = when (runs) { is JsonArray -> runs.size; is JsonPrimitive -> runs.contentOrNull?.toIntOrNull() ?: 0; else -> 0 }
}

@Serializable
data class Compiled(val rule: JsonObject = JsonObject(emptyMap()), val previewFa: String = "", val refusedFa: List<String> = emptyList())
