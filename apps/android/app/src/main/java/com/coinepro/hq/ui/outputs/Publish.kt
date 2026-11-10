package com.coinepro.hq.ui.outputs

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
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
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.Deliverable
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.gated
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

internal val KIND_FA = mapOf("reel" to "ریلز", "post" to "پست", "story" to "استوری")

/** The kinds a file may go out as: a video is a reel or a story, an image a post or a story. */
internal fun kindsOf(f: FileRef): List<String> = if (f.kind == "video") listOf("reel", "story") else listOf("post", "story")

/** The files of an output that can be published at all. */
internal fun publishable(d: Deliverable): List<FileRef> = d.attachments.map(::kindFromMime).filter { it.kind == "video" || it.kind == "image" }

/** The newest publish of one file (the hub lists them newest first). */
internal fun publishOf(panel: PublishPanel, fileId: String): SessionPublish? = panel.publishes.firstOrNull { it.fileId == fileId }

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
    if (panel.order == null) return
    val c = Divan.colors
    var asking by remember { mutableStateOf<FileRef?>(null) }
    // what the hub said of a file whose publish path is not connected yet (no job to list): kept while the page is open
    var notes by remember { mutableStateOf(mapOf<String, String>()) }
    val live = panel.publishes.any { it.state == "publishing" }
    LaunchedEffect(live) { while (live) { delay(5_000); q.refresh() } }
    Column(Modifier.testTag("publish"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("انتشار در اینستاگرام", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 4.dp)) {
            files.forEachIndexed { i, f ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                PublishRow(f, publishOf(panel, f.id), notes[f.id]) { asking = f }
            }
        }
        Text("با تأیید شما همین فایل منتشر میشود؛ کارت و اثر انگشت ندارد.", style = Divan.type.micro, color = c.textMuted)
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
private fun PublishRow(f: FileRef, p: SessionPublish?, note: String?, onAsk: () -> Unit) {
    val c = Divan.colors
    val uri = LocalUriHandler.current
    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        DIcon(if (f.kind == "video") DivanIcon.VIDEO else DivanIcon.IMAGE, size = 20.dp, tint = c.textSecondary)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Fig(f.name.ifBlank { "فایل" }, style = Divan.type.figureSmall, color = c.textPrimary)
            // the handle is Latin inside a Persian line: isolated left-to-right, so «@» stays in front of it
            val where = p?.let { listOfNotNull(KIND_FA[it.kind], it.account?.let { a -> "\u2066@$a\u2069" }, it.coverName?.let { "با کاور" }).joinToString(" · ") }
            when {
                p == null && note != null -> Text(note, style = Divan.type.micro, color = c.textSecondary)
                p == null -> Text(if (f.kind == "video") "ویدیو · آماده‌ی انتشار" else "تصویر · آماده‌ی انتشار", style = Divan.type.micro, color = c.textMuted)
                p.state == "failed" -> Text(listOfNotNull(where, p.noteFa).joinToString(" · "), style = Divan.type.micro, color = c.negative)
                p.state == "waiting_seal" -> Text(p.noteFa ?: "منتظر مُهر شما", style = Divan.type.micro, color = c.textSecondary)
                else -> if (!where.isNullOrEmpty()) Text(where, style = Divan.type.micro, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        when (p?.state) {
            null -> HqButton(if (note == null) "تأیید و انتشار" else "دوباره", onAsk, variant = if (note == null) BtnVariant.PRIMARY else BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.SEND)
            "publishing" -> Pill("در حال انتشار", Tone.GOLD, dot = true, live = true)
            "published" -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Pill("منتشر شد", Tone.POS, dot = true)
                val url = p.url
                if (url != null) HqButton("باز کن", { runCatching { uri.openUri(url) } }, variant = BtnVariant.TEXT, size = BtnSize.SM)
            }
            "waiting_seal" -> Pill("منتظر مُهر", Tone.WARN, dot = true)
            else -> HqButton("دوباره", onAsk, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.REFRESH)
        }
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
    val kinds = remember(f) { kindsOf(f) }
    var kind by rememberSaveable(f.id) { mutableStateOf(kinds.first()) }
    var account by rememberSaveable(f.id) { mutableStateOf(panel.accounts.singleOrNull()) }
    var caption by rememberSaveable(f.id) { mutableStateOf("") }
    // a reel goes out with its cover: the output's images (the one there is, chosen already)
    val covers = remember(d, f) { if (f.kind == "video") publishable(d).filter { it.kind == "image" } else emptyList() }
    var cover by rememberSaveable(f.id) { mutableStateOf(covers.singleOrNull()?.id) }
    val key = rememberSaveable(f.id) { UUID.randomUUID().toString() }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        @Composable fun Label(t: String) = Text(t, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(if (f.kind == "video") DivanIcon.VIDEO else DivanIcon.IMAGE, size = 18.dp, tint = c.goldInk)
            Fig(f.name.ifBlank { "فایل" }, style = Divan.type.figureSmall, color = c.textPrimary)
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
        }
        if (kind != "story") Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Label("کپشن")
            HqTextField(caption, { caption = it }, "کپشن و هشتگ‌ها (اختیاری)", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 2200)
        }
        val pick = panel.accounts.size > 1 && account == null
        HqButton(
            "تأیید و انتشار",
            {
                action.run {
                    val out = env.api.publishOutput(d.ref, f.id, kind, caption.takeIf { kind != "story" }, account, key, cover.takeIf { kind == "reel" })
                    env.cache.invalidate("publish", "orders")
                    when (out.state) {
                        "waiting_setup" -> toasts.info(out.noteFa ?: "تیم فنی هلدینگ مسیر انتشار را وصل میکند.")
                        "published" -> toasts.ok("منتشر شده است.")
                        else -> toasts.ok("${KIND_FA[out.kind] ?: "فایل"} به اینستاگرام رفت؛ نتیجه همین‌جا می‌آید.")
                    }
                    onDone(out)
                }
            },
            Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEND, enabled = !pick, loading = action.busy,
        )
        Text(
            if (pick) "اول حساب را انتخاب کنید." else "برداشتن پست از خود اینستاگرام انجام میشود.",
            style = Divan.type.micro, color = c.textMuted, modifier = Modifier.fillMaxWidth(),
        )
    }
}
