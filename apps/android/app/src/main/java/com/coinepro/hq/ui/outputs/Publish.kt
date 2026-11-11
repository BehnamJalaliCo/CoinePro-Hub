package com.coinepro.hq.ui.outputs

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.JPEG_LINE_FA
import com.coinepro.hq.core.data.ROUTE_WAITS_FA
import com.coinepro.hq.core.data.bestChoice
import com.coinepro.hq.core.data.bestClockFa
import com.coinepro.hq.core.data.cancellable
import com.coinepro.hq.core.data.cancelling
import com.coinepro.hq.core.data.goesAsJpeg
import com.coinepro.hq.core.data.goesOut
import com.coinepro.hq.core.data.isImage
import com.coinepro.hq.core.data.isVideo
import com.coinepro.hq.core.data.routeOpen
import com.coinepro.hq.core.data.sheetBest
import com.coinepro.hq.core.data.stands
import com.coinepro.hq.core.data.tappable
import com.coinepro.hq.core.data.withPublish
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.ROUTE_NOT_READY_FA
import com.coinepro.hq.core.format.ROUTE_NOT_READY_SHORT_FA
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.BestHour
import com.coinepro.hq.core.net.Deliverable
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.PublishComment
import com.coinepro.hq.core.net.PublishPanel
import com.coinepro.hq.core.net.SessionPublish
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DecisionBar
import com.coinepro.hq.designsystem.DecisionState
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.SpringSheet
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.rememberHaptics
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.look.FaceFrame
import com.coinepro.hq.ui.look.FileFace
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v29.served
import kotlinx.coroutines.delay
import java.util.UUID

/*
 * ⟨0.19.8⟩ §44.5 «تأیید و انتشار»; ⟨1.0.1⟩ Part C, in the look (C3.3; contract §44.5, §46, §49, §51, §52).
 *
 * The owner, 2026-11-10: «این برو بیا و هی مهر بکن و اینو مجوز بده … آزار و اذیت میده منو». His tap is the seal for what goes out and
 * can be taken back: no card and no passkey. The publish sheet is the one spring sheet: the file itself, its kind, the account, the
 * caption, the time (now, an hour, or the account's best hour), the comment word, the JPEG line under a picture that is not one, and
 * «انتشار» in its decision bar. Under an output's files, one row per video or picture says where its publication stands and takes it
 * back while it is not out; the page's first file to publish is carried by the page's decision bar (the one full gold), the others
 * are outlined. A company whose publishing path is not connected yet is the technical team's work, said in one calm line, never the
 * owner's step.
 */

internal val KIND_FA = mapOf("reel" to "ریلز", "post" to "پست", "story" to "استوری", "carousel" to "اسلاید")

/**
 * The kinds a file may go out as: a video is a reel or a story, an image a post or a story. ⟨0.20.0⟩ §46 With other videos or
 * images in the same output ([others]), also a carousel of them all, this file first.
 */
internal fun kindsOf(f: FileRef, others: Int = 0): List<String> =
    (if (f.kind == "video") listOf("reel", "story") else listOf("post", "story")) + (if (others > 0) listOf("carousel") else emptyList())

/**
 * ⟨0.20.0⟩ §46 The time he set, as the hub takes it (with the owner's zone): today ([day] 0) or tomorrow (1) at [clock] («18:30»,
 * Persian digits too). Null when [clock] is no hour.
 */
internal fun scheduledIso(day: Int, clock: String): String? {
    val hm = com.coinepro.hq.core.data.clockOf(clock) ?: return null
    val zone = java.time.ZoneId.of(com.coinepro.hq.core.format.OWNER_TZ)
    val at = HqClock.today(zone).plusDays(day.toLong()).atTime(hm.substringBefore(':').toInt(), hm.substringAfter(':').toInt()).atZone(zone)
    return at.toOffsetDateTime().format(java.time.format.DateTimeFormatter.ISO_OFFSET_DATE_TIME)
}

/** The comment rule from the three fields: null when all are empty; a word and its reply are both needed ([commentHalf]). */
internal fun commentOf(word: String, reply: String, link: String): PublishComment? {
    val words = word.split(',', '،').map { it.trim() }.filter { it.isNotEmpty() }
    if (words.isEmpty() || reply.isBlank()) return null
    return PublishComment(keywords = words.take(10), reply = reply.trim(), link = link.trim().takeIf { it.startsWith("https://") })
}

/** He began a comment rule and left it half: a word without its reply, a reply or a link without the word. */
internal fun commentHalf(word: String, reply: String, link: String): Boolean =
    (word.isNotBlank() || reply.isNotBlank() || link.isNotBlank()) && commentOf(word, reply, link) == null

/** The files of an output that can be published at all. */
internal fun publishable(d: Deliverable): List<FileRef> = d.attachments.map(::kindFromMime).filter { it.kind == "video" || it.kind == "image" }

/** The image chosen as a reel's cover before he touches anything: the one named `cover…`, else the only one. */
internal fun coverOf(images: List<FileRef>): FileRef? = images.firstOrNull { it.name.lowercase().startsWith("cover") } ?: images.singleOrNull()

/**
 * Where one file stands (the hub lists its publishes newest first): its reel or its post when there is one, else its story. ⟨0.19.9⟩
 * The same video can go out as a reel and as a story (the standing word's «استوری هم»): the reel is the row, the story a line under it.
 */
internal fun publishOf(panel: PublishPanel, fileId: String): SessionPublish? =
    panel.publishes.firstOrNull { it.fileId == fileId && it.kind != "story" } ?: panel.publishes.firstOrNull { it.fileId == fileId }

/** The story of a file that also went out as a reel or a post (null when the story is the row itself). */
internal fun storyOf(panel: PublishPanel, fileId: String): SessionPublish? =
    panel.publishes.firstOrNull { it.fileId == fileId && it.kind == "story" }?.takeIf { publishOf(panel, fileId)?.kind != "story" }

internal val STATE_FA = mapOf(
    "publishing" to "در حال انتشار", "scheduled" to "زمان‌بندی شد", "published" to "منتشر شد", "failed" to "انجام نشد", "waiting_seal" to "منتظر تأیید",
    "waiting_setup" to "در حال وصل شدن", "cancelled" to "لغو شد",
)

/** The panel of an output (nothing asked of a hub before §44.5: learnt once, then an empty panel). The same cached read everywhere. */
@Composable
internal fun rememberPublishPanel(ref: String) =
    rememberQuery("publish:$ref", "publish", "orders") { gated(HubFeature.SESSION_PUBLISH) { publishPanel(ref) } ?: PublishPanel() }

// ================================================================================================ the publish sheet ==
/** What a caller already knows of the publication (a desk card): the sheet opens with it in place. */
data class PublishSeed(val caption: String? = null, val account: String? = null, val cover: String? = null, val best: BestHour? = null)

/** The sheet's fields, held together so that the sheet, its decision bar and a screenshot read the same state. */
@Stable
class PublishState(val d: Deliverable, val f: FileRef, val panel: PublishPanel, seed: PublishSeed? = null) {
    /** ⟨0.20.0⟩ §46 the output's other videos and images: with them this file can go out as a carousel (ten files at most). */
    val others: List<FileRef> = publishable(d).filter { it.id != f.id }.take(9)
    val kinds: List<String> = kindsOf(f, others.size)
    /** A reel goes out with its cover: the output's images (the one named `cover…`, else the one there is, chosen already). */
    val covers: List<FileRef> = if (f.kind == "video") publishable(d).filter { it.kind == "image" } else emptyList()
    private val seedBest = seed?.best

    var kind by mutableStateOf(kinds.first())
    var account by mutableStateOf(seed?.account?.takeIf { it in panel.accounts } ?: panel.accounts.singleOrNull())
    /** ⟨0.19.9⟩ §45 the caption its package carries is already in place; he edits it or just taps. */
    var caption by mutableStateOf(seed?.caption ?: panel.caption.orEmpty())
    var cover by mutableStateOf(seed?.cover?.takeIf { id -> covers.any { it.id == id } } ?: coverOf(covers)?.id)
    /** `now` · `later` (today or tomorrow at an hour) · `best` (the account's best hour, §49). */
    var whenAt by mutableStateOf("now")
    var day by mutableStateOf(0)
    var clock by mutableStateOf("")
    var word by mutableStateOf(panel.comment?.keywords.orEmpty().joinToString("، "))
    var reply by mutableStateOf(panel.comment?.reply.orEmpty())
    var link by mutableStateOf(panel.comment?.link.orEmpty())
    /** The hub's own words when the publish was refused. */
    var error by mutableStateOf<String?>(null)

    /** ⟨1.0.1⟩ §49 the account's best hour as one of the times (only when the hub is sure of it). */
    val best: BestHour? get() = sheetBest(bestChoice(panel.best ?: seedBest, account))
    val atBest: Boolean get() = whenAt == "best" && best != null
    val later: Boolean get() = whenAt == "later" || atBest
    val whenIso: String? get() = if (atBest) best?.at else if (whenAt == "later") scheduledIso(day, clock) else null
    val pick: Boolean get() = panel.accounts.size > 1 && account == null
    val noHour: Boolean get() = whenAt == "later" && whenIso == null
    val half: Boolean get() = kind != "story" && commentHalf(word, reply, link)
    val ready: Boolean get() = !pick && !noHour && !half
    val coverFile: FileRef? get() = if (kind == "reel") covers.firstOrNull { it.id == cover } else null

    // One key for one press: a different kind or time is another publication.
    private val keys = mutableMapOf<String, String>()
    fun key(): String = keys.getOrPut("$kind|${if (whenAt == "later") "$day|$clock" else whenAt}") { UUID.randomUUID().toString() }

    /** What is decided, in one line for the decision bar. */
    val contextFa: String
        get() = when {
            pick -> "اول حساب را انتخاب کن."
            noHour -> "ساعت را به شکل ۱۸:۳۰ بنویس."
            half -> "برای کامنت، هم کلمه لازم است و هم پیام."
            kind == "carousel" -> "هر ${others.size + 1} فایل این خروجی با هم، به همین ترتیب، میروند."
            else -> listOfNotNull(
                KIND_FA[kind], account?.let { "@$it" },
                when {
                    atBest -> "بهترین ساعت ${bestClockFa(best).orEmpty()}"
                    whenAt == "later" -> "${if (day == 1) "فردا" else "امروز"} ${whenIso?.let(::jTime).orEmpty()}"
                    else -> "همین حالا"
                },
            ).joinToString(" · ")
        }
}

@Composable
private fun Label(t: String) = Text(t, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.textSecondary)

/** ⟨1.0.1⟩ §52 a picture that is no JPEG goes out as one the hub makes: said once, quietly, under the picture. */
@Composable
private fun JpegLine() = Text(timesFig(JPEG_LINE_FA), style = Divan.type.micro, color = Divan.colors.textMuted, modifier = Modifier.testTag("jpeg-line"))

/** The sheet's fields: the file itself, its kind, the account, the cover, the caption, the time, the comment word. */
@Composable
internal fun PublishFields(s: PublishState) {
    val c = Divan.colors
    val f = s.f
    Row(Modifier.testTag("publish-preview"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        FaceFrame(Modifier.size(width = 72.dp, height = 96.dp)) { FileFace(f, sign = 28.dp) }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Fig(f.name.ifBlank { "فایل" }, style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Text(if (isVideo(f)) "ویدیو" else "تصویر", style = Divan.type.caption, color = c.textSecondary)
            if (isImage(f) && goesAsJpeg(f)) JpegLine()
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Label("به شکل")
        ChipRow { for (k in s.kinds) FilterChip(KIND_FA[k] ?: k, s.kind == k, { s.kind = k }) }
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Label("حساب")
        when {
            s.panel.accounts.isEmpty() -> Text(ROUTE_NOT_READY_FA, style = Divan.type.small, color = c.textSecondary)
            s.panel.accounts.size == 1 -> Fig("@${s.panel.accounts[0]}", style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            else -> ChipRow { for (a in s.panel.accounts) FilterChip("@$a", s.account == a, { s.account = a }, figure = true) }
        }
    }
    if (s.kind == "reel" && s.covers.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Label("کاور")
        ChipRow {
            for (x in s.covers) FilterChip(x.name.ifBlank { "تصویر" }, s.cover == x.id, { s.cover = x.id }, figure = true)
            FilterChip("بدون کاور", s.cover == null, { s.cover = null })
        }
        if (goesAsJpeg(s.coverFile)) JpegLine()
    }
    if (s.kind != "story") Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Label("کپشن")
        HqTextField(s.caption, { s.caption = it }, "کپشن و هشتگ‌ها (اختیاری)", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 2200)
    }
    Column(Modifier.testTag("publish-time"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Label("زمان")
        ChipRow {
            FilterChip("الان", s.whenAt == "now" || (s.whenAt == "best" && !s.atBest), { s.whenAt = "now" })
            FilterChip("ساعت مشخص", s.whenAt == "later", { s.whenAt = "later" })
            s.best?.let { b -> FilterChip("بهترین ساعت (${bestClockFa(b).orEmpty()})", s.atBest, { s.whenAt = "best" }) }
        }
        // what the hour rests on, as the hub says it wherever it shows the hour
        if (s.atBest) s.best?.noteFa?.trim()?.ifBlank { null }?.let { Text(timesFig(it), style = Divan.type.micro, color = c.textMuted) }
        if (s.whenAt == "later") Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip("امروز", s.day == 0, { s.day = 0 })
            FilterChip("فردا", s.day == 1, { s.day = 1 })
            HqTextField(s.clock, { s.clock = it }, "18:30", Modifier.weight(1f), maxLength = 5, figure = true)
        }
    }
    if (s.kind != "story") Column(Modifier.testTag("publish-comment"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Label("کامنت و لینک (اختیاری)")
        HqTextField(s.word, { s.word = it }, "کلمه یا عددی که مخاطب کامنت میکند", Modifier.fillMaxWidth(), maxLength = 100)
        HqTextField(s.reply, { s.reply = it }, "پیام خصوصی برای او", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 1000)
        HqTextField(s.link, { s.link = it }, "https://…", Modifier.fillMaxWidth(), maxLength = 1900, figure = true)
    }
}

/** The sheet's one act, stuck to its bottom: «انتشار» (or «زمان‌بندی»), what is decided in one line, the hub's refusal in its place. */
@Composable
internal fun PublishDecisionBar(s: PublishState, busy: Boolean, onGo: () -> Unit) {
    DecisionBar(
        if (s.later) "زمان‌بندی" else "انتشار", onGo, context = s.contextFa, error = s.error, enabled = s.ready, icon = DivanIcon.SEND,
        state = if (busy) DecisionState.WORKING else DecisionState.IDLE,
    )
}

const val PUBLISH_SHEET_FA = "تأیید و انتشار"
const val PUBLISH_SHEET_SUB_FA = "اینستاگرام؛ بی کارت و بی اثر انگشت"

/** The publish sheet of one file: the one confirmation. His tap in its decision bar is the seal. */
@Composable
internal fun PublishSheet(d: Deliverable, f: FileRef, panel: PublishPanel, seed: PublishSeed? = null, onDismiss: () -> Unit, onDone: (SessionPublish) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val haptics = rememberHaptics()
    val action = rememberAction()
    val s = remember(d.ref, f.id) { PublishState(d, f, panel, seed) }
    SpringSheet(onDismiss, PUBLISH_SHEET_FA, sub = PUBLISH_SHEET_SUB_FA, bar = {
        PublishDecisionBar(s, action.busy) {
            s.error = null
            action.run(onError = { e: ApiException -> haptics.error(); s.error = e.messageFa.ifBlank { "این کار انجام نشد؛ دوباره امتحان کن." } }) {
                val out = env.api.publishOutput(
                    d.ref, f.id, s.kind, s.caption.takeIf { s.kind != "story" }, s.account, s.key(), s.cover.takeIf { s.kind == "reel" },
                    fileIds = if (s.kind == "carousel") s.others.map { it.id } else emptyList(),
                    scheduledAt = s.whenIso, comment = commentOf(s.word, s.reply, s.link),
                )
                haptics.seal()
                env.cache.invalidate("publish", "orders", "order-report")
                val kind = KIND_FA[out.kind] ?: "فایل"
                when (out.state) {
                    "waiting_setup" -> toasts.info(ROUTE_NOT_READY_FA)
                    "published" -> toasts.ok("منتشر شده است.")
                    "scheduled" -> toasts.ok("$kind زمان‌بندی شد؛ سر ساعت خودش منتشر میشود.")
                    else -> toasts.ok("$kind به اینستاگرام رفت؛ نتیجه همین‌جا می‌آید.")
                }
                onDone(out)
            }
        }
    }) { PublishFields(s) }
}

/**
 * The publish sheet of one file of an output, wherever it is asked from (the output's page, a tile in a session, a card of the desk):
 * the output's own files and publish panel are read (the cached reads the output's page uses), then the sheet opens with them.
 */
@Composable
fun PublishFor(output: String, fileId: String, seed: PublishSeed? = null, onDismiss: () -> Unit, onDone: (SessionPublish) -> Unit = {}) {
    val q = rememberQuery("deliverable:$output", "deliverables") { deliverable(output) }
    val panel = rememberPublishPanel(output)
    val d = q.data
    val p = panel.data
    val f = d?.let(::publishable)?.firstOrNull { it.id == fileId }
    when {
        d != null && p != null && f != null && tappable(p) -> PublishSheet(d, f, p, seed, onDismiss) { out ->
            panel.set(p.copy(publishes = listOf(out) + p.publishes.filter { it.job != out.job || out.job == null }))
            onDone(out)
            onDismiss()
        }
        (d == null && q.error == null) || (p == null && panel.error == null) -> SpringSheet(onDismiss, PUBLISH_SHEET_FA) {
            Skeleton(Modifier.fillMaxWidth().height(96.dp), radius = 12.dp)
            Skeleton(Modifier.fillMaxWidth().height(40.dp), radius = 10.dp)
            Skeleton(Modifier.fillMaxWidth().height(112.dp), radius = 10.dp)
        }
        else -> SpringSheet(onDismiss, PUBLISH_SHEET_FA) {
            Text("این فایل الان آماده‌ی انتشار نیست؛ کمی بعد دوباره امتحان کن.", style = Divan.type.small, color = Divan.colors.textSecondary)
        }
    }
}

// ==================================================================================== where a publication stands ==
/** The state of a publication in words with its mark; nothing here is gold. */
@Composable
internal fun PublishStateWord(p: SessionPublish, modifier: Modifier = Modifier) {
    val word = STATE_FA[p.state] ?: "انجام نشد"
    when (p.state) {
        "publishing" -> Pill(word, Tone.SILVER, modifier, dot = true, live = !cancelling(p))
        "scheduled" -> Pill(word, Tone.SILVER, modifier, icon = DivanIcon.TIME)
        "published" -> Pill(word, Tone.POS, modifier, dot = true)
        "cancelled" -> Pill(word, Tone.NEUTRAL, modifier, dot = true)
        "waiting_seal" -> Pill(word, Tone.WARN, modifier, icon = DivanIcon.TIME)
        "waiting_setup" -> Pill(word, Tone.NEUTRAL, modifier, dot = true)
        else -> Pill(word, Tone.NEG, modifier, icon = DivanIcon.URGENT)
    }
}

/** The facts of a publication in one line: its kind, its hour, its account, its cover, whether the hub sent it by itself, its comment word. */
internal fun publishFacts(p: SessionPublish): AnnotatedString = facts(
    KIND_FA[p.kind] ?: "پست",
    p.scheduledAt?.takeIf { p.state == "scheduled" }?.let { "ساعت ${jTime(it)}" },
    p.account?.let { "@$it" }, "با کاور".takeIf { p.coverName != null }, "خودکار".takeIf { p.auto }, p.comment?.let { "کامنت «$it»" },
)

/** What the hub notes on a publication that is neither failed nor waiting (those say it in their own line): «در حال لغو», «لغو انجام نشد (…)». */
internal fun publishNote(p: SessionPublish?): String? =
    p?.noteFa?.trim()?.ifBlank { null }?.takeIf { p.state == "scheduled" || p.state == "publishing" }

/** «باز کن»: the published post, outside the app. */
@Composable
internal fun OpenLink(url: String) {
    val uri = LocalUriHandler.current
    HqButton("باز کن", { runCatching { uri.openUri(url) } }, variant = BtnVariant.TEXT, size = BtnSize.SM)
}

/** One file: itself small, where its publication stands, and the one quiet action that fits. */
@Composable
private fun PublishRow(f: FileRef, p: SessionPublish?, note: String?, story: SessionPublish?, lead: Boolean, cover: Boolean, open: Boolean, cancel: PublishCancel?, onAsk: () -> Unit) {
    val c = Divan.colors
    val job = p?.job
    val asking = job != null && cancel?.asking == job
    val free = p == null || p.state == "failed" || p.state == "cancelled"
    val video = isVideo(f)
    Column(Modifier.fillMaxWidth().testTag("publish-row")) {
        Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            FaceFrame(Modifier.size(width = 44.dp, height = 56.dp), radius = 8.dp) { FileFace(f, sign = 20.dp) }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Fig(f.name.ifBlank { "فایل" }, style = Divan.type.figureSmall, color = c.textPrimary)
                when {
                    p == null && note != null -> Text(note, style = Divan.type.micro, color = c.textSecondary)
                    p == null -> Text(
                        when {
                            cover -> "کاور ریلز؛ با ریلز میرود"
                            !open -> if (video) "ویدیو" else "تصویر"
                            else -> if (video) "ویدیو، آماده‌ی انتشار" else "تصویر، آماده‌ی انتشار"
                        },
                        style = Divan.type.micro, color = c.textMuted,
                    )
                    else -> {
                        // whole, on a second line when it has to: the hour and the comment word are what he looks for
                        Text(remember(p) { publishFacts(p) }, style = Divan.type.micro, color = if (p.state == "failed") c.negative else c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        if (p.state == "failed" || p.state == "waiting_seal") p.noteFa?.trim()?.ifBlank { null }?.let { Text(timesFig(it), style = Divan.type.micro, color = if (p.state == "failed") c.negative else c.textSecondary) }
                    }
                }
                // what the hub says of it meanwhile («در حال لغو», «لغو انجام نشد (…)»), and what it refused of his cancel
                publishNote(p)?.let { Text(timesFig(it), style = Divan.type.micro, color = c.textMuted) }
                job?.let { j -> cancel?.refused?.get(j) }?.let { Text(timesFig(it), style = Divan.type.micro, color = c.negative) }
                if (story != null) Text("استوری: ${STATE_FA[story.state] ?: story.state}", style = Divan.type.micro, color = if (story.state == "failed") c.negative else c.textMuted)
            }
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                if (p != null) PublishStateWord(p)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val url = p?.url
                    if (p?.state == "published" && url != null) OpenLink(url)
                    if (p != null && job != null && cancel != null && !asking && cancellable(p)) HqButton("لغو", { cancel.ask(job) }, variant = BtnVariant.TEXT, size = BtnSize.SM, label = "لغو این انتشار")
                    // The page's first file to publish is in the decision bar; here it is said, not repeated.
                    if (free && open && !lead) HqButton(if (p != null || note != null) "دوباره" else if (cover) "جدا منتشر کن" else "تأیید و انتشار", onAsk, variant = BtnVariant.SECONDARY, size = BtnSize.SM)
                }
            }
        }
        if (asking && job != null && cancel != null) CancelAsk(job, cancel)
    }
}

/**
 * Under an output's files: one row per video or picture with where its publication stands. [lead]: the file whose «تأیید و انتشار»
 * the page's decision bar carries (it is not repeated here). [onAsk] null: the section opens the sheet itself. Nothing for an output
 * that cannot be published by a tap, or on a hub before §44.5.
 */
@Composable
internal fun PublishSection(d: Deliverable, lead: String? = null, onAsk: ((FileRef) -> Unit)? = null) {
    val files = remember(d) { publishable(d) }
    if (files.isEmpty()) return
    val q = rememberPublishPanel(d.ref)
    val panel = q.data ?: return
    // ⟨0.19.9⟩ §45 a working group's daily output is no session's and is tapped here all the same (a hub of §45 says `tap`)
    if (!tappable(panel)) return
    val c = Divan.colors
    var asking by remember { mutableStateOf<FileRef?>(null) }
    // what the hub said of a file whose publish path is not connected yet (no job to list): kept while the page is open
    val notes = remember { mutableStateMapOf<String, String>() }
    // ⟨1.0.1⟩ §51 a cancel on its way is followed like a publish on its way
    val live = panel.publishes.any { it.state == "publishing" || cancelling(it) }
    LaunchedEffect(live) { while (live) { delay(5_000); q.refresh() } }
    val cancel = rememberPublishCancel { out -> q.set(panel.copy(publishes = withPublish(panel.publishes, out))) }
    val canCancel = served(HubFeature.PUBLISH_CANCEL)
    val open = routeOpen(panel)
    // A reel's cover goes out with its reel; on its own it is a second, quieter act.
    val cover = if (files.any(::isVideo)) coverOf(files.filter(::isImage))?.id else null
    Column(Modifier.testTag("publish"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("انتشار در اینستاگرام", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 2.dp)) {
            files.forEachIndexed { i, f ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                PublishRow(f, publishOf(panel, f.id), notes[f.id], storyOf(panel, f.id), lead = lead == f.id, cover = cover == f.id, open = open, cancel = cancel.takeIf { canCancel }) {
                    if (onAsk != null) onAsk(f) else asking = f
                }
            }
        }
        Text(
            when {
                !open -> ROUTE_WAITS_FA
                panel.mode == "auto" -> "کارگروه «${panel.groupFa ?: "این خروجی"}» خروجی هر روز را خودکار منتشر میکند؛ وضعش همین‌جاست."
                else -> "با تأیید تو همین فایل منتشر میشود؛ کارت و اثر انگشت ندارد."
            },
            style = Divan.type.micro, color = if (open) c.textMuted else c.textSecondary,
        )
    }
    asking?.let { f ->
        PublishSheet(d, f, panel, onDismiss = { asking = null }) { out ->
            asking = null
            if (out.job == null) notes[f.id] = out.noteFa?.trim()?.ifBlank { null } ?: ROUTE_NOT_READY_FA
            else { notes.remove(f.id); q.set(panel.copy(publishes = listOf(out) + panel.publishes.filter { it.job != out.job })) }
        }
    }
}

/** What sits under a file's tile in a session: its quiet «تأیید و انتشار», or where its publication stands. */
@Composable
internal fun PublishUnder(f: FileRef, panel: PublishPanel?, lead: Boolean, onAsk: () -> Unit) {
    if (panel == null || !tappable(panel) || !goesOut(f)) return
    val c = Divan.colors
    val p = publishOf(panel, f.id)
    when {
        stands(p) && p != null -> Column(Modifier.testTag("tile-publish"), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                if (p.state == "scheduled" && p.scheduledAt != null) "زمان‌بندی شد، ${jTime(p.scheduledAt)}" else STATE_FA[p.state] ?: "در راه",
                style = Divan.type.micro, color = c.textSecondary,
            )
            val url = p.url
            if (p.state == "published" && url != null) OpenLink(url)
        }
        !routeOpen(panel) -> Text(ROUTE_NOT_READY_SHORT_FA, style = Divan.type.micro, color = c.textSecondary)
        // What the session waits on is in its decision bar (the full gold); here it is not repeated.
        lead -> Text("آماده‌ی انتشار", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.testTag("tile-publish"))
        // A cover picture waits behind its reel.
        isImage(f) && panel.mode == "auto" -> Unit
        else -> Box(
            Modifier.fillMaxWidth().height(32.dp).testTag("tile-publish").clip(RoundedCornerShape(8.dp)).border(1.dp, c.lineStrong, RoundedCornerShape(8.dp))
                .clickable(role = Role.Button, onClickLabel = "تأیید و انتشار", onClick = onAsk),
            contentAlignment = Alignment.Center,
        ) { Text(if (p != null) "دوباره" else "تأیید و انتشار", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1) }
    }
}
