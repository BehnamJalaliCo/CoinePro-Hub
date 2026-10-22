package com.coinepro.hq.ui.notes

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.net.OwnerNote
import com.coinepro.hq.core.net.tagsOf
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.media.Composer
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.Chip
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v18.AudioPlayer
import com.coinepro.hq.ui.v18.NOTE_STATUS
import com.coinepro.hq.ui.v18.PROMOTE
import com.coinepro.hq.ui.v18.mgmt
import java.util.UUID
import kotlinx.coroutines.delay

// یادداشت‌های سریع مالک (contract §21.8), mirroring apps/web/src/app/(app)/notes/page.tsx: text or voice, promoted into work, an order
// or an errand; never deleted. No model runs on notes; the advisor reads the open ones only in the weekly review.

private val STATUSES = listOf<String?>("open", "promoted", "archived", null)
private val PROMOTED_ROUTE = mapOf<String, (String) -> String>("work" to { r -> "work/$r" }, "order" to { _ -> "home" }, "errand" to { _ -> "assistant" })

@Composable
fun NotesScreen(highlight: String? = null) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    var status by rememberSaveable { mutableStateOf<String?>("open") }
    var text by rememberSaveable { mutableStateOf("") }
    var query by remember { mutableStateOf("") }
    LaunchedEffect(text) { delay(300); query = text.trim() }
    val q = rememberQuery("notes:${status ?: "all"}:$query", "notes") { notes(status, query).items }
    val r = refresher(q)
    var promote by remember { mutableStateOf<OwnerNote?>(null) }
    suspend fun create(body: String, attachments: List<String>) {
        // The composer sends the voice as its only attachment (files are off here): a voice note keeps its recording.
        val voice = attachments.lastOrNull()
        try {
            val n = env.api.createNote(body, if (voice != null) "voice" else "text", voice, tagsOf(Regex("#[^\\s#]+").findAll(body).joinToString(",") { it.value }), UUID.randomUUID().toString())
            env.cache.invalidate("notes", "reviews")
            toasts.ok("یادداشت ${n.ref} ثبت شد.")
            if (status != null && status != "open") status = "open"
        } catch (e: com.coinepro.hq.core.net.ApiException) {
            toasts.error(com.coinepro.hq.core.net.mgmtError(e)); throw e
        }
    }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("یادداشت‌های سریع", eyebrow = "هر فکری، همان لحظه؛ بعداً به کار، فرمان یا کار دستیار تبدیلش کن") }
        item {
            Text(
                "هیچ مدلی روی یادداشت‌ها اجرا نمیشود؛ مشاور کل یادداشت‌های باز را فقط در مرور هفتگی میخواند. یادداشت پاک نمیشود؛ بایگانی میشود. برچسب را با # در متن بنویس.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        item { Composer("یادداشت تازه… (ویس هم میشود؛ صدای اصلی کنارش میماند)", ::create, purpose = "note", allowFiles = false, draftKey = "note:new") }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                ChipRow { for (s in STATUSES) FilterChip(s?.let { NOTE_STATUS[it]?.fa } ?: "همه", status == s, { status = s }) }
                HqTextField(text, { text = it }, "جستجو در یادداشت‌ها…", Modifier.fillMaxWidth(), maxLength = 200)
            }
        }
        val list = q.data
        when {
            list == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list == null -> items(3) { Skeleton(Modifier.fillMaxWidth().height(120.dp), radius = 16.dp) }
            list.isEmpty() -> item { Empty("یادداشتی نیست", icon = DivanIcon.EDIT, body = "بالای صفحه بنویس یا بگو.") }
            else -> items(list, key = { it.ref }) { n -> NoteCard(n, highlight == n.ref) { promote = n } }
        }
    }
    promote?.let { n -> PromoteDialog(n) { promote = null } }
}

@Composable
private fun NoteCard(n: OwnerNote, highlight: Boolean, onPromote: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val nav = LocalNav.current
    val c = Divan.colors
    val action = rememberAction()
    var edit by rememberSaveable(n.ref) { mutableStateOf(false) }
    var text by rememberSaveable(n.ref) { mutableStateOf(n.textMd) }
    var tags by rememberSaveable(n.ref) { mutableStateOf(n.tags.joinToString("، ")) }
    val muted = n.status == "archived"
    HqCard(Modifier.fillMaxWidth().then(if (highlight) Modifier.border(2.dp, c.goldInk, RoundedCornerShape(16.dp)) else Modifier), color = if (muted) c.tile else c.card) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Fig(n.ref, style = Divan.type.figureSmall, color = c.textMuted)
                if (n.source == "voice") Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                    DIcon(DivanIcon.MIC, size = 12.dp, tint = c.textMuted)
                    Text("از ویس", style = Divan.type.micro, color = c.textMuted)
                }
                Text(ago(n.createdAt), Modifier.weight(1f), style = Divan.type.micro, color = c.textMuted)
                LabelPill(NOTE_STATUS[n.status], n.status)
            }
            if (edit) {
                HqTextField(text, { text = it }, "متن یادداشت", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 4000)
                HqTextField(tags, { tags = it }, "برچسب‌ها، با ویرگول", Modifier.fillMaxWidth(), maxLength = 200)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HqButton("ذخیره", {
                        action.mgmt(toasts) { env.api.patchNote(n, text = text.trim(), tags = tagsOf(tags)); env.cache.invalidate("notes"); edit = false; toasts.ok("یادداشت ذخیره شد.") }
                    }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, enabled = text.isNotBlank(), loading = action.busy)
                    HqButton("انصراف", { edit = false; text = n.textMd; tags = n.tags.joinToString("، ") }, variant = BtnVariant.GHOST, size = BtnSize.SM)
                }
            } else Md(n.textMd, style = Divan.type.body, color = c.textPrimary)
            if (n.source == "voice" && n.fileId != null) AudioPlayer(n.fileId, "صدای اصلی ${n.ref}", compact = true)
            if (n.tags.isNotEmpty() && !edit) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                n.tags.forEach { Text("#$it", Modifier.clip(CircleShape).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.micro, color = c.textSecondary) }
            }
            n.promotedTo?.let { p ->
                val pr = PROMOTE[p.kind]
                Row(
                    Modifier.clip(CircleShape).background(c.softPositive).clickable(role = Role.Button) { PROMOTED_ROUTE[p.kind]?.let { nav.go(it(p.ref)) } }.padding(horizontal = 10.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    DIcon(pr?.icon ?: DivanIcon.TASK, size = 13.dp, tint = c.positive)
                    Text(pr?.fa ?: p.kind, style = Divan.type.caption, color = c.positive)
                    Fig(p.ref, style = Divan.type.figureSmall, color = c.positive)
                }
            }
            if (n.status == "open" && !edit) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                HqButton("تبدیل", onPromote, size = BtnSize.SM, icon = DivanIcon.DELEGATE)
                HqButton("ویرایش", { edit = true }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.EDIT)
                HqButton("بایگانی", {
                    action.mgmt(toasts) { env.api.patchNote(n, archive = true); env.cache.invalidate("notes"); toasts.info("بایگانی شد.") }
                }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.DOWNLOAD, loading = action.busy)
            }
        }
    }
}

/** A note becomes work (for that company's CEO, §4), an order (routed by rule, §17.4) or an errand for the assistant (§18.3). */
@Composable
private fun PromoteDialog(n: OwnerNote, onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val companies = rememberCompanies()
    var to by remember { mutableStateOf("work") }
    var company by remember { mutableStateOf<String?>(null) }
    val ok = to != "work" || company != null
    AlertDialog(
        onDismissRequest = onClose,
        containerColor = c.overlay,
        title = { Text("تبدیل یادداشت", style = Divan.type.h3) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(n.textMd, Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp), style = Divan.type.small, color = c.textPrimary, maxLines = 4)
                for ((k, p) in PROMOTE) {
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (to == k) c.softGold else c.tile).clickable(role = Role.RadioButton) { to = k }.padding(10.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        DIcon(p.icon, size = 18.dp, tint = if (to == k) c.goldInk else c.textSecondary)
                        Column {
                            Text(p.fa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                            Text(p.note, style = Divan.type.micro, color = c.textMuted)
                        }
                    }
                }
                if (to == "work") ChipRow {
                    for (co in companies) Chip(company == co.code, { company = co.code }) { ink ->
                        CoMark(co.code, height = 11.dp, ink = ink)
                        Text(co.nameFa ?: co.code, style = Divan.type.small, color = ink, maxLines = 1)
                    }
                }
            }
        },
        confirmButton = {
            HqButton("تبدیل کن", {
                action.mgmt(toasts) {
                    val out = env.api.promoteNote(n.ref, to, if (to == "work") company else null)
                    env.cache.invalidate("notes", "work", "orders", "errands", "planner", "reviews")
                    toasts.ok("تبدیل شد به ${PROMOTE[to]?.fa ?: to} ${out.promotedTo?.ref.orEmpty()}.")
                    onClose()
                }
            }, variant = BtnVariant.PRIMARY, enabled = ok, loading = action.busy)
        },
        dismissButton = { HqButton("انصراف", onClose, variant = BtnVariant.GHOST) },
    )
}
