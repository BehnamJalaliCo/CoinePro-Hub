package com.coinepro.hq.ui.outputs

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.JPEG_LINE_FA
import com.coinepro.hq.core.data.bestChoice
import com.coinepro.hq.core.data.bestClockFa
import com.coinepro.hq.core.data.cancellable
import com.coinepro.hq.core.data.cancelling
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.goesAsJpeg
import com.coinepro.hq.core.data.withPublish
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.Deliverable
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.core.net.PublishComment
import com.coinepro.hq.core.net.PublishPanel
import com.coinepro.hq.core.net.SessionPublish
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.served
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v16.ChipRow
import kotlinx.coroutines.delay
import java.util.UUID

/*
 * ⟨0.19.8⟩ §44.5 «تأیید و انتشار».
 *
 * The owner, 2026-11-10: «این برو بیا و هی مهر بکن و اینو مجوز بده … آزار و اذیت میده منو». A reel the workshop made sat in his
 * session with nowhere to go: publishing had no button, and the card that could approve it lived on another page behind a passkey.
 * Now each video or image of a session's output has the one action under it. His tap is the seal for what goes out and can be
 * taken back: no card, no passkey. The hub sends the file to the company's Instagram through IG-Hub and the row says where it
 * stands; a company whose publish path is not connected yet is the technical team's work, said in one calm line.
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
    "publishing" to "در حال انتشار", "scheduled" to "زمان‌بندی شد", "published" to "منتشر شد", "failed" to "انجام نشد", "waiting_seal" to "منتظر مُهر",
    "cancelled" to "لغو شد",
)

/**
 * Under an output's files: nothing for an output of no session (or a hub that does not know the route yet), else one row per video
 * or image with «تأیید و انتشار» or where its publish stands.
 */
@Composable
internal fun PublishSection(d: Deliverable) {
    val files = remember(d) { publishable(d) }
    if (files.isEmpty()) return
    // a hub before §44.5 has no such route: learnt once, then nothing is asked and nothing is shown
    val q = rememberQuery("publish:${d.ref}", "publish", "orders") { gated(HubFeature.SESSION_PUBLISH) { publishPanel(d.ref) } ?: PublishPanel() }
    val panel = q.data ?: return
    // ⟨0.19.9⟩ §45 a working group's daily output is no session's and is tapped here all the same (a hub of §45 says `tap`)
    if (panel.order == null && !panel.tap) return
    val c = Divan.colors
    var asking by remember { mutableStateOf<FileRef?>(null) }
    // what the hub said of a file whose publish path is not connected yet (no job to list): kept while the page is open
    var notes by remember { mutableStateOf(mapOf<String, String>()) }
    // ⟨1.0.1⟩ §51 a cancel on its way to IG-Hub is followed like a publish on its way
    val live = panel.publishes.any { it.state == "publishing" || cancelling(it) }
    LaunchedEffect(live) { while (live) { delay(5_000); q.refresh() } }
    val cancel = rememberPublishCancel { out -> q.set(panel.copy(publishes = withPublish(panel.publishes, out))) }
    val canCancel = served(HubFeature.PUBLISH_CANCEL)
    Column(Modifier.testTag("publish"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("انتشار در اینستاگرام", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.silverInk)
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 4.dp)) {
            files.forEachIndexed { i, f ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                PublishRow(f, publishOf(panel, f.id), notes[f.id], storyOf(panel, f.id), cancel.takeIf { canCancel }) { asking = f }
            }
        }
        Text(
            if (panel.mode == "auto") "کارگروه «${panel.groupFa ?: "این خروجی"}» خروجی هر روز را خودکار منتشر میکند؛ وضعش همین‌جاست."
            else "با تأیید شما همین فایل منتشر میشود؛ کارت و اثر انگشت ندارد.",
            style = Divan.type.micro, color = c.textMuted,
        )
    }
    asking?.let { f ->
        PublishSheet(d, f, panel, onDismiss = { asking = null }) { out ->
            asking = null
            if (out.job == null) notes = notes + (f.id to (out.noteFa ?: "تیم فنی هلدینگ مسیر انتشار را وصل میکند."))
            else { notes = notes - f.id; q.set(panel.copy(publishes = listOf(out) + panel.publishes.filter { it.job != out.job })) }
        }
    }
}

/** One file: its name, where its publish stands, and the one action that fits. */
@Composable
private fun PublishRow(f: FileRef, p: SessionPublish?, note: String?, story: SessionPublish? = null, cancel: PublishCancel? = null, onAsk: () -> Unit) {
    val c = Divan.colors
    val uri = LocalUriHandler.current
    // ⟨1.0.1⟩ §51 «لغو» on a publication that is not out yet; once cancelled, the file is his to publish again
    val job = p?.job
    val cancelled = p?.state == "cancelled"
    val asking = job != null && cancel?.asking == job
    Column(Modifier.fillMaxWidth()) {
    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        DIcon(if (f.kind == "video") DivanIcon.VIDEO else DivanIcon.IMAGE, size = 20.dp, tint = c.textSecondary)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Fig(f.name.ifBlank { "فایل" }, style = Divan.type.figureSmall, color = c.textPrimary)
            // the handle is Latin inside a Persian line: isolated left-to-right, so «@» stays in front of it
            val where = p?.let {
                listOfNotNull(
                    KIND_FA[it.kind],
                    // ⟨0.20.0⟩ §46 the hour it is set for (first: the line is one row), and the word viewers comment for its link
                    it.scheduledAt?.takeIf { _ -> it.state == "scheduled" }?.let { t -> "ساعت ${jTime(t)}" },
                    it.account?.let { a -> "\u2066@$a\u2069" }, it.coverName?.let { "با کاور" }, "خودکار".takeIf { _ -> it.auto },
                    it.comment?.let { w -> "کامنت «$w»" },
                ).joinToString(" · ")
            }
            when {
                p == null && note != null -> Text(note, style = Divan.type.micro, color = c.textSecondary)
                p == null -> Text(if (f.kind == "video") "ویدیو · آماده‌ی انتشار" else "تصویر · آماده‌ی انتشار", style = Divan.type.micro, color = c.textMuted)
                p.state == "failed" -> Text(listOfNotNull(where, p.noteFa).joinToString(" · "), style = Divan.type.micro, color = c.negative)
                p.state == "waiting_seal" -> Text(p.noteFa ?: "منتظر مُهر شما", style = Divan.type.micro, color = c.textSecondary)
                cancelled -> Text(listOfNotNull(KIND_FA[p.kind], "لغو شد").joinToString(" · "), style = Divan.type.micro, color = c.textMuted)
                // whole, on a second line when it has to (beside «لغو» the row is narrower): the hour and the comment word are what he looks for
                else -> if (!where.isNullOrEmpty()) Text(where, style = Divan.type.micro, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
            // what the hub says of it meanwhile («در حال لغو», «لغو انجام نشد (…)»), and what it refused of his cancel
            if (p != null && !cancelled && (p.state == "scheduled" || p.state == "publishing")) p.noteFa?.trim()?.ifBlank { null }?.let {
                Text(com.coinepro.hq.designsystem.timesFig(it), style = Divan.type.micro, color = if (cancelling(p)) c.goldInk else c.warning)
            }
            job?.let { j -> cancel?.refused?.get(j) }?.let { Text(com.coinepro.hq.designsystem.timesFig(it), style = Divan.type.micro, color = c.warning) }
            if (story != null) Text(
                "استوری: ${STATE_FA[story.state] ?: story.state}",
                style = Divan.type.micro, color = if (story.state == "failed") c.negative else c.textMuted,
            )
        }
        val quiet = p != null && cancel != null && !asking && cancellable(p)
        when (p?.state) {
            null -> HqButton(if (note == null) "تأیید و انتشار" else "دوباره", onAsk, variant = if (note == null) BtnVariant.PRIMARY else BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.SEND)
            "cancelled" -> HqButton("تأیید و انتشار", onAsk, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEND)
            "publishing", "scheduled" -> Row(verticalAlignment = Alignment.CenterVertically) {
                if (p.state == "publishing") Pill("در حال انتشار", Tone.SILVER, dot = true, live = true) else Pill("زمان‌بندی شد", Tone.GOLD, dot = true)
                if (quiet && job != null) HqButton("لغو", { cancel?.ask(job) }, variant = BtnVariant.TEXT, size = BtnSize.SM, label = "لغو این انتشار")
            }
            "published" -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Pill("منتشر شد", Tone.POS, dot = true)
                val url = p.url
                if (url != null) HqButton("باز کن", { runCatching { uri.openUri(url) } }, variant = BtnVariant.TEXT, size = BtnSize.SM)
            }
            "waiting_seal" -> Pill("منتظر مُهر", Tone.WARN, dot = true)
            else -> HqButton("دوباره", onAsk, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.REFRESH)
        }
    }
    if (asking && job != null && cancel != null) CancelAsk(job, cancel)
    }
}

/** The one confirmation: which account, as what, with which caption. The gold button is the owner's word. */
@Composable
private fun PublishSheet(d: Deliverable, f: FileRef, panel: PublishPanel, onDismiss: () -> Unit, onDone: (SessionPublish) -> Unit) {
    HqSheet(onDismiss, "تأیید و انتشار", sub = "اینستاگرام، از راه IG-Hub · بی کارت و بی اثر انگشت") { PublishForm(d, f, panel, onDone) }
}

/** The sheet's content (on its own for the screenshots). */
@Composable
internal fun PublishForm(d: Deliverable, f: FileRef, panel: PublishPanel, onDone: (SessionPublish) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    // ⟨0.20.0⟩ §46 the output's other videos and images: with them this file can go out as a carousel
    val others = remember(d, f) { publishable(d).filter { it.id != f.id } }
    val kinds = remember(f, others) { kindsOf(f, others.size.coerceAtMost(9)) }
    var kind by rememberSaveable(f.id) { mutableStateOf(kinds.first()) }
    var account by rememberSaveable(f.id) { mutableStateOf(panel.accounts.singleOrNull()) }
    // ⟨0.19.9⟩ §45 the caption its package carries (`caption.txt`) is already in place; he edits it or just taps
    var caption by rememberSaveable(f.id) { mutableStateOf(panel.caption.orEmpty()) }
    // a reel goes out with its cover: the output's images (the one named `cover…`, else the one there is, chosen already)
    val covers = remember(d, f) { if (f.kind == "video") publishable(d).filter { it.kind == "image" } else emptyList() }
    var cover by rememberSaveable(f.id) { mutableStateOf(coverOf(covers)?.id) }
    // ⟨0.20.0⟩ §46 the time (now, or today/tomorrow at an hour) and the comment rule of this post (its package's, already in place)
    var later by rememberSaveable(f.id) { mutableStateOf(false) }
    var day by rememberSaveable(f.id) { mutableStateOf(0) }
    var clock by rememberSaveable(f.id) { mutableStateOf("") }
    var word by rememberSaveable(f.id) { mutableStateOf(panel.comment?.keywords.orEmpty().joinToString("، ")) }
    var reply by rememberSaveable(f.id) { mutableStateOf(panel.comment?.reply.orEmpty()) }
    var link by rememberSaveable(f.id) { mutableStateOf(panel.comment?.link.orEmpty()) }
    // ⟨1.0.1⟩ §49 the account's best hour as one of the times (the panel carries it only when there is enough data)
    var best by rememberSaveable(f.id) { mutableStateOf(false) }
    val bestHour = bestChoice(panel.best, account)
    val atBest = best && bestHour != null
    val whenIso = if (atBest) bestHour?.at else if (later) scheduledIso(day, clock) else null
    val key = rememberSaveable(f.id, kind, later, day, clock, atBest) { UUID.randomUUID().toString() }
    // ⟨1.0.1⟩ §52 a picture that is no JPEG goes out as one the hub makes: said once, quietly, under the picture
    @Composable fun JpegLine() = Text(com.coinepro.hq.designsystem.timesFig(JPEG_LINE_FA), style = Divan.type.micro, color = c.textMuted)
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        @Composable fun Label(t: String) = Text(t, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DIcon(if (f.kind == "video") DivanIcon.VIDEO else DivanIcon.IMAGE, size = 18.dp, tint = c.goldInk)
                Fig(f.name.ifBlank { "فایل" }, style = Divan.type.figureSmall, color = c.textPrimary)
            }
            if (f.kind == "image" && goesAsJpeg(f)) JpegLine()
        }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Label("حساب")
            when {
                panel.accounts.isEmpty() -> Text("حساب این شرکت هنوز به هاب معرفی نشده؛ با تأیید شما تیم فنی هلدینگ همین حالا وصلش میکند.", style = Divan.type.small, color = c.textSecondary)
                panel.accounts.size == 1 -> Fig("@${panel.accounts[0]}", style = Divan.type.figure, color = c.textPrimary)
                else -> ChipRow { for (a in panel.accounts) FilterChip("@$a", account == a, { account = a }, figure = true) }
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Label("به شکل")
            ChipRow { for (k in kinds) FilterChip(KIND_FA[k] ?: k, kind == k, { kind = k }) }
        }
        if (kind == "reel" && covers.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Label("کاور")
            ChipRow {
                for (x in covers) FilterChip(x.name.ifBlank { "تصویر" }, cover == x.id, { cover = x.id }, figure = true)
                FilterChip("بدون کاور", cover == null, { cover = null })
            }
            if (goesAsJpeg(covers.firstOrNull { it.id == cover })) JpegLine()
        }
        if (kind != "story") Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Label("کپشن")
            HqTextField(caption, { caption = it }, "کپشن و هشتگ‌ها (اختیاری)", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 2200)
        }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Label("زمان")
            ChipRow {
                FilterChip("الان", !later && !atBest, { later = false; best = false })
                FilterChip("ساعت مشخص", later && !atBest, { later = true; best = false })
                if (bestHour != null) FilterChip(listOfNotNull("بهترین ساعت", bestClockFa(bestHour)?.let { "($it)" }).joinToString(" "), atBest, { best = true; later = false })
            }
            // what the hour rests on, as the hub says it wherever it shows the hour
            if (atBest) bestHour?.noteFa?.trim()?.ifBlank { null }?.let { Text(com.coinepro.hq.designsystem.timesFig(it), style = Divan.type.micro, color = c.textMuted) }
            if (later && !atBest) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip("امروز", day == 0, { day = 0 })
                FilterChip("فردا", day == 1, { day = 1 })
                HqTextField(clock, { clock = it }, "۱۸:۳۰", Modifier.weight(1f), maxLength = 5, figure = true)
            }
        }
        if (kind != "story") Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Label("کامنت و لینک (اختیاری)")
            HqTextField(word, { word = it }, "کلمه یا عددی که مخاطب کامنت میکند", Modifier.fillMaxWidth(), maxLength = 100)
            HqTextField(reply, { reply = it }, "پیام خصوصی برای او", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 1000)
            HqTextField(link, { link = it }, "https://…", Modifier.fillMaxWidth(), maxLength = 1900, figure = true)
        }
        val pick = panel.accounts.size > 1 && account == null
        val noHour = later && !atBest && whenIso == null
        val half = kind != "story" && commentHalf(word, reply, link)
        HqButton(
            if (later || atBest) "تأیید و زمان‌بندی" else "تأیید و انتشار",
            {
                action.run {
                    val out = env.api.publishOutput(
                        d.ref, f.id, kind, caption.takeIf { kind != "story" }, account, key, cover.takeIf { kind == "reel" },
                        fileIds = if (kind == "carousel") others.take(9).map { it.id } else emptyList(),
                        scheduledAt = whenIso, comment = commentOf(word, reply, link),
                    )
                    env.cache.invalidate("publish", "orders")
                    when (out.state) {
                        "waiting_setup" -> toasts.info(out.noteFa ?: "تیم فنی هلدینگ مسیر انتشار را وصل میکند.")
                        "published" -> toasts.ok("منتشر شده است.")
                        "scheduled" -> toasts.ok("${KIND_FA[out.kind] ?: "فایل"} زمان‌بندی شد؛ سر ساعت خودش منتشر میشود.")
                        else -> toasts.ok("${KIND_FA[out.kind] ?: "فایل"} به اینستاگرام رفت؛ نتیجه همین‌جا می‌آید.")
                    }
                    onDone(out)
                }
            },
            Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEND, enabled = !pick && !noHour && !half, loading = action.busy,
        )
        Text(
            when {
                pick -> "اول حساب را انتخاب کنید."
                noHour -> "ساعت را به شکل ۱۸:۳۰ بنویسید."
                half -> "برای کامنت، هم کلمه لازم است و هم پیام."
                kind == "carousel" -> "هر ${faNum(others.take(9).size + 1)} فایل این خروجی با هم، به همین ترتیب، میروند."
                else -> "برداشتن پست از خود اینستاگرام انجام میشود."
            },
            style = Divan.type.micro, color = c.textMuted, modifier = Modifier.fillMaxWidth(),
        )
    }
}
