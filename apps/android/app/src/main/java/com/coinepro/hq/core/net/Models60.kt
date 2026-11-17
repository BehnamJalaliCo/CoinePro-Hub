package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

// Contract §60 ⟨1.39⟩: the publish centre. Every publication is one permanent row (`media.publications`): its texts, its files and where
// it came from; the centre (today, the desk, the calendar, the archive, an item, the search, «منتظر شما») reads only those rows. Same
// rules as Models.kt: camelCase here, snake_case on the wire; a field the hub omits takes its default.

/** A slide set as one card (`group=set`): how many slides, how many went out, the next one's hour. */
@Serializable
data class CardSet(val n: Int = 0, val done: Int = 0, val nextAt: String? = null)

/** One publication in a list (§60.2). [at] is `published_at ?? scheduled_at ?? created_at`. */
@Serializable
data class PublicationCard(
    val ref: String = "",
    val company: String = "",
    val companyFa: String = "",
    val channel: String = "instagram",
    val account: String = "",
    /** `reel` · `story` · `post` · `carousel` · `short` · `video` · `tg_post` · `article` */
    val kind: String = "reel",
    /** `scheduled` · `publishing` · `published` · `held` · `failed` · `cancelled` */
    val state: String = "scheduled",
    val stateNoteFa: String? = null,
    val at: String = "",
    val titleFa: String = "",
    val thumbFileId: String? = null,
    val filesN: Int = 0,
    val url: String? = null,
    val setKey: String? = null,
    val set: CardSet? = null,
    val automation: String? = null,
    val automationFa: String? = null,
    /** With `q`: where it matched (`title` · `topic` · `caption` · `word`) and ≤ 80 characters around the hit. */
    val match: String? = null,
    val snippetFa: String? = null,
)

/** What an automation will still make today (not a row yet). */
@Serializable
data class PlannedItem(
    val automation: String = "",
    val automationFa: String = "",
    val account: String = "",
    val kind: String = "reel",
    val titleFa: String = "",
    val buildAt: String = "",
    val publishAt: String = "",
    /** `planned` · `building` */
    val state: String = "planned",
)

@Serializable
data class TodayCounts(val published: Int = 0, val scheduled: Int = 0, val held: Int = 0, val failed: Int = 0)

/** `GET /publications/today`: the owner's day in Tehran, sets grouped, in time order. */
@Serializable
data class PublishToday(
    val day: String = "",
    val items: List<PublicationCard> = emptyList(),
    val planned: List<PlannedItem> = emptyList(),
    val next: PublicationCard? = null,
    val counts: TodayCounts = TodayCounts(),
)

@Serializable
data class TreeAccount(
    val channel: String = "instagram",
    val account: String = "",
    val avatarFileId: String? = null,
    val total: Int = 0,
    /** `{reel: n, story: n, …}` */
    val byKind: Map<String, Int> = emptyMap(),
    val automations: Int = 0,
)

@Serializable
data class TreeCompany(val code: String = "", val nameFa: String = "", val markFileId: String? = null, val total: Int = 0, val accounts: List<TreeAccount> = emptyList())

/** `GET /publications/tree`: every company and account with a row in the range. */
@Serializable
data class PublishTree(val companies: List<TreeCompany> = emptyList())

@Serializable
data class PublicationPage(val items: List<PublicationCard> = emptyList(), val next: String? = null)

@Serializable
data class LinkButton(val title: String = "", val url: String = "")

/** The comment rule that went with a reel: its words, the DM and its buttons, the public replies in their order. */
@Serializable
data class PubComment(
    val keywords: List<String> = emptyList(),
    val match: String? = null,
    val reply: String? = null,
    val link: String? = null,
    val buttons: List<LinkButton> = emptyList(),
    val publicReplies: List<String> = emptyList(),
)

@Serializable
data class PubSeo(val slug: String? = null, val metaTitle: String? = null, val metaDescription: String? = null, val canonical: String? = null)

/** A file of the row: `video` · `cover` · `slide` · `image` · `thumb`; [n] a slide's place. Kept for good (§58.4 amended). */
@Serializable
data class PubFile(val role: String = "", val fileId: String = "", val name: String? = null, val mime: String? = null, val size: Long? = null, val n: Int? = null)

@Serializable
data class PubSource(
    val automation: String? = null,
    val automationFa: String? = null,
    val flowKey: String? = null,
    val version: Int? = null,
    val day: String? = null,
    val order: String? = null,
    val work: String? = null,
    val output: String? = null,
    val session: String? = null,
    val jobId: String = "",
)

@Serializable
data class PubInsights(
    val views: Long? = null,
    val likes: Long? = null,
    val comments: Long? = null,
    val dms: Long? = null,
    val bestHour: String? = null,
    val updatedAt: String? = null,
)

/** A slide of the same set (the item route only). */
@Serializable
data class SetItem(val ref: String = "", val n: Int? = null, val at: String = "", val state: String = "scheduled", val fileId: String? = null)

/** `GET /publications/{ref}`: the whole row. */
@Serializable
data class Publication(
    val ref: String = "",
    val company: String = "",
    val companyFa: String = "",
    val channel: String = "instagram",
    val account: String = "",
    val kind: String = "reel",
    val state: String = "scheduled",
    val stateNoteFa: String? = null,
    val scheduledAt: String? = null,
    val publishedAt: String? = null,
    val at: String = "",
    val url: String? = null,
    val externalId: String? = null,
    val titleFa: String = "",
    val topicFa: String? = null,
    val caption: String? = null,
    val comment: PubComment? = null,
    val storyWord: String? = null,
    val seo: PubSeo? = null,
    val files: List<PubFile> = emptyList(),
    val thumbFileId: String? = null,
    val setKey: String? = null,
    val set: List<SetItem>? = null,
    val source: PubSource = PubSource(),
    val insights: PubInsights? = null,
    val createdAt: String? = null,
    val updatedAt: String? = null,
)

@Serializable
data class PubCalendarDay(
    val day: String = "",
    val published: Int = 0,
    val scheduled: Int = 0,
    val held: Int = 0,
    val failed: Int = 0,
    val planned: Int = 0,
    val accounts: List<String> = emptyList(),
)

@Serializable
data class PublishCalendar(val days: List<PubCalendarDay> = emptyList())

@Serializable
data class WaitingAction(val key: String = "", val labelFa: String = "", val primary: Boolean = false)

/** Only what cannot move without the owner (§60.2); none: the centre hides «منتظر شما». */
@Serializable
data class Waiting(
    val id: String = "",
    /** `publish_ask` (and, on a hub before the owner's word of 2026-11-17, `budget_cap`) */
    val kind: String = "publish_ask",
    val titleFa: String = "",
    val account: String? = null,
    val at: String = "",
    val deadlineAt: String? = null,
    val publication: PublicationCard? = null,
    val actions: List<WaitingAction> = emptyList(),
)

@Serializable
data class WaitingList(val items: List<Waiting> = emptyList())

/** The answer of a waiting item's action, read loosely. */
typealias WaitingDone = JsonObject
