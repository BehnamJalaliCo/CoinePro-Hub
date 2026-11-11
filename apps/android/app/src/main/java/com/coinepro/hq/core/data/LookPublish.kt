package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.BestHour
import com.coinepro.hq.core.net.Deliverable
import com.coinepro.hq.core.net.DeskCard
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.PublishDesk
import com.coinepro.hq.core.net.PublishPanel
import com.coinepro.hq.core.net.SessionPublish
import java.time.ZoneId
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull

// ⟨1.0.1⟩ Part C, «تأیید و انتشار» and «میز انتشار» in the look (C2.3, C3.3; contract §44.5, §55.2), in the owner's words (the web's
// look/publish.tsx, look/desk.tsx and lib/api/v55.ts, rule for rule): which file a page's one «تأیید و انتشار» is about, whether a
// publication stands, the desk's three sections in their order and its one full gold, and the day of a moment as the owner says it.
// Pure functions: the unit tests read them.

// ============================================================================================ what can be published ==
fun isVideo(f: FileRef): Boolean = f.kind == "video" || f.mime.startsWith("video/")
fun isImage(f: FileRef): Boolean = f.kind == "image" || f.mime.startsWith("image/")

/** A video or a picture: what Instagram takes. */
fun goesOut(f: FileRef): Boolean = isVideo(f) || isImage(f)

/** A publication that stands: on its way, set for an hour, out, or waiting on the team. A failed or cancelled one does not. */
fun stands(p: SessionPublish?): Boolean = p != null && p.state != "failed" && p.state != "cancelled"

/** Whether the files of this output can be published by a tap at all (a session's output, or a working group's daily one). */
fun tappable(panel: PublishPanel?): Boolean = panel != null && (panel.order != null || panel.tap)

/** Whether the company's publishing path is set (§44.5 `ready`). A panel with accounts is taken as set whatever it says. */
fun routeOpen(panel: PublishPanel): Boolean = panel.ready || panel.accounts.isNotEmpty()

/** Where one file stands (the hub lists its publications newest first): its reel or post when there is one, else its story. */
fun publicationOf(panel: PublishPanel, fileId: String): SessionPublish? =
    panel.publishes.firstOrNull { it.fileId == fileId && it.kind != "story" } ?: panel.publishes.firstOrNull { it.fileId == fileId }

/**
 * The file the page's own «تأیید و انتشار» is about: the first video with no publication that stands, else (in an output with no
 * video) the first such picture: a picture that is only a reel's cover waits behind its reel. Nothing when the working group
 * publishes by itself, or the company's publishing path is not set yet.
 */
fun leadFile(panel: PublishPanel?, files: List<FileRef>): FileRef? {
    if (panel == null || !tappable(panel) || panel.mode == "auto" || !routeOpen(panel)) return null
    val free = files.filter { goesOut(it) && !stands(publicationOf(panel, it.id)) }
    return free.firstOrNull(::isVideo) ?: if (files.any(::isVideo)) null else free.firstOrNull()
}

/** The file an output shows of itself first: its first video, else its first picture. */
fun faceOf(files: List<FileRef>): FileRef? = files.firstOrNull(::isVideo) ?: files.firstOrNull(::isImage)

/** What is said of an output whose company's publishing path is not set yet (C2.3; never a step of the owner's). */
const val ROUTE_WAITS_FA = "مسیر انتشار این شرکت را تیم فنی وصل میکند"
const val VIDEO_FAILED_FA = "این ویدیو پخش نشد؛ دانلودش کن"
const val INLINE_VIDEO_FA = "بی‌صدا پخش میشود؛ یک لمس دیگر روی ویدیو: تمام‌صفحه با صدا."

/** The best hour as the sheet offers it: only when the hub named an hour and its moment. */
fun sheetBest(best: BestHour?): BestHour? = best?.takeIf { it.enough && !it.hour.isNullOrBlank() && it.at != null }

/** «21:00» of a best hour the hub is sure of; null otherwise. */
fun bestHourOf(b: BestHour?): String? = b?.takeIf { it.enough }?.let(::bestClockFa)

/** `usage` as the hub writes it (§5.2: input, output and cache tokens, cost and equivalent cost), or the older `{tokens, usd}`. */
fun usageOf(d: Deliverable): Pair<Long?, String?> {
    fun n(k: String) = (d.usage[k] as? JsonPrimitive)?.longOrNull
    fun s(k: String) = (d.usage[k] as? JsonPrimitive)?.contentOrNull
    val parts = listOf("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens").mapNotNull(::n)
    val tokens = n("tokens") ?: parts.takeIf { it.isNotEmpty() }?.sum()
    val cost = s("usd") ?: s("cost_usd")?.takeIf { (it.toDoubleOrNull() ?: 0.0) > 0 } ?: s("equiv_cost_usd")
    return tokens?.takeIf { it > 0 } to cost
}

/** Whether a summary says something its text does not already say (marks and spaces aside): it is not shown twice. */
fun summaryIsNew(summary: String?, body: String?): Boolean {
    fun squash(t: String?) = t.orEmpty().replace(Regex("[#*_`>\\-\\s]+"), " ").trim()
    val s = squash(summary)
    return s.isNotEmpty() && !squash(body).contains(s)
}

// ================================================================================================== the publish desk ==
const val DESK_FA = "میز انتشار"
const val DESK_EMPTY_FA = "چیزی آماده‌ی انتشار نیست؛ هر خروجی تأییدشدنی همین‌جا می‌آید."

/** When a desk card's publication is due: its set hour, else the card's own time. */
fun deskAt(c: DeskCard): String = c.publish?.scheduledAt?.ifBlank { null } ?: c.at

/**
 * The desk in its three sections, each in its order whatever order the hub sent them in: what is ready newest first, the queue
 * soonest first, what is done newest first.
 */
fun deskSorted(d: PublishDesk): PublishDesk = PublishDesk(
    ready = d.ready.sortedByDescending { instant(it.at)?.toEpochMilli() ?: 0L },
    queue = d.queue.sortedBy { instant(deskAt(it))?.toEpochMilli() ?: Long.MAX_VALUE },
    done = d.done.sortedByDescending { instant(it.publish?.publishedAt ?: it.at)?.toEpochMilli() ?: 0L },
)

fun deskEmpty(d: PublishDesk): Boolean = d.ready.isEmpty() && d.queue.isEmpty() && d.done.isEmpty()

/** The one card whose «تأیید و انتشار» is the page's full gold: the first ready one whose company's path is set. */
fun deskLead(ready: List<DeskCard>): String? = ready.firstOrNull { it.routeReady }?.output

/** The frame a kind of post is shown in on its network, width over height: a reel and a story 9:16, a post 4:5, a carousel 1:1. */
fun deskRatio(kind: String): Float = when (kind) { "reel", "story" -> 9f / 16f; "post" -> 4f / 5f; else -> 1f }

/** What a queued card says in place of an hour while it has none to wait for. */
fun deskQueueWordFa(state: String): String? = when (state) {
    "publishing" -> "در حال انتشار"
    "waiting_setup" -> "در حال وصل شدن"
    "waiting_seal" -> "منتظر تأیید"
    else -> null
}

/** «۳ خروجی آماده‌ی انتشار» / «چیزی آماده نیست», and «۲ در صف» when the queue holds any: the home's line to the desk. */
fun deskLineFa(d: PublishDesk): List<String> = listOfNotNull(
    if (d.ready.isNotEmpty()) "${d.ready.size} خروجی آماده‌ی انتشار" else "چیزی آماده نیست",
    if (d.queue.isNotEmpty()) "${d.queue.size} در صف" else null,
)

/**
 * The day of a moment as the owner says it: «امروز», «امشب», «فردا», «فردا شب», «دیروز», «دیشب», else its date. The hour is written
 * beside it by the caller (a Latin figure). Night begins at 18:00 on the owner's clock.
 */
fun deskDayFa(iso: String?, now: Long = HqClock.millis()): String {
    val t = instant(iso) ?: return ""
    val zone = ZoneId.of(OWNER_TZ)
    val at = t.atZone(zone)
    val today = java.time.Instant.ofEpochMilli(now).atZone(zone).toLocalDate()
    val night = at.hour >= 18
    return when (at.toLocalDate()) {
        today -> if (night) "امشب" else "امروز"
        today.plusDays(1) -> if (night) "فردا شب" else "فردا"
        today.minusDays(1) -> if (night) "دیشب" else "دیروز"
        else -> jDate(iso)
    }
}
