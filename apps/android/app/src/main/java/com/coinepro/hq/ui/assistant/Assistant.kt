package com.coinepro.hq.ui.assistant

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.Errand
import com.coinepro.hq.designsystem.Badge
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.media.MessageMedia
import com.coinepro.hq.ui.messages.ChatScreen
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.ERRAND_STATUS
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill

private val STEP_ICON = mapOf(
    "search" to DivanIcon.SEARCH, "read" to DivanIcon.KNOWLEDGE, "browse" to DivanIcon.GLOBE, "request" to DivanIcon.SEND,
    "draft" to DivanIcon.EDIT, "note" to DivanIcon.INFO, "proposal" to DivanIcon.SEAL,
)

/** دستیار شخصی (contract §18.3): the owner's errands, done on the internet; any commitment in the holding's name
 *  (paying, booking, sending to a person outside) becomes a decision card. Thread P, with the errands one tap away. */
@Composable
fun AssistantScreen() {
    val q = rememberQuery("errands", "errands", maxAgeMs = 15_000) { errands().items }
    var list by remember { mutableStateOf(false) }
    var open by remember { mutableStateOf<String?>(null) }
    val items = q.data.orEmpty()
    val waiting = items.count { it.status == "waiting_owner" }
    ChatScreen("P", agent = "assistant", headerAction = {
        Box {
            HqButton("کارها", { list = true }, size = BtnSize.SM, icon = DivanIcon.TASK)
            if (waiting > 0) Badge(waiting, Modifier.align(Alignment.TopStart).offset(x = (-4).dp, y = (-4).dp))
        }
    })
    if (list) {
        HqSheet({ list = false }, "کارها", sub = "هر درخواست یک کار با مسیر قابل دیدن") {
            when {
                q.data == null -> Skeleton(Modifier.fillMaxWidth().height(140.dp), radius = 14.dp)
                items.isEmpty() -> Empty("هنوز کاری نخواسته‌ای", icon = DivanIcon.ASSISTANT, body = "در گفت‌وگو بگو؛ دستیار کار را میسازد و جلو میبرد.")
                else -> for (e in items) ErrandRow(e) { list = false; open = e.ref }
            }
        }
    }
    items.firstOrNull { it.ref == open }?.let { ErrandSheet(it) { open = null } }
}

@Composable
private fun ErrandRow(e: Errand, onClick: () -> Unit) {
    val c = Divan.colors
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (e.status == "waiting_owner") c.softGold else c.tile).clickable(role = Role.Button, onClick = onClick).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(e.titleFa, style = Divan.type.small.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold), modifier = Modifier.weight(1f), maxLines = 2, overflow = TextOverflow.Ellipsis)
            LabelPill(ERRAND_STATUS[e.status], e.status)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Fig(e.ref, style = Divan.type.figureSmall, color = c.textMuted)
            Text("${e.steps.size} گام", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
            Text(ago(e.updatedAt), style = Divan.type.micro, color = c.textMuted)
        }
    }
}

/** One errand: the brief, each step it took (search, read, browse, draft), the result, and the decision it waits on. */
@Composable
private fun ErrandSheet(e: Errand, onClose: () -> Unit) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    HqSheet(onClose, e.titleFa, ref = e.ref) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LabelPill(ERRAND_STATUS[e.status], e.status)
            if (e.source == "voice") DIcon(DivanIcon.MIC, size = 14.dp, tint = c.textMuted)
            Text(ago(e.createdAt), style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
            Fig(usd(e.usage.usd), style = Divan.type.figureSmall, color = c.textSecondary)
        }
        Md(e.briefMd, style = Divan.type.body, color = c.textPrimary)
        if (e.attachments.isNotEmpty()) MessageMedia(e.attachments)
        Text("مسیر کار", style = Divan.type.caption.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold), color = c.textSecondary)
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            for (s in e.steps) {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Box(Modifier.size(26.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) { DIcon(STEP_ICON[s.kind] ?: DivanIcon.TASK, size = 14.dp, tint = c.textSecondary) }
                    Column(Modifier.weight(1f)) {
                        RichText(s.summaryFa, style = Divan.type.small, color = c.textPrimary)
                        Text(jTime(s.at), style = Divan.type.micro, color = c.textMuted)
                    }
                }
            }
        }
        e.resultMd?.let {
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.card).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("نتیجه", style = Divan.type.caption.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold), color = c.textSecondary)
                Md(it, color = c.textPrimary)
            }
        }
        e.decisionRef?.let { ref ->
            HqButton("مُهر در کارتابل ($ref)", { onClose(); nav.go("cartable/$ref") }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL)
        }
        if (e.open) HqButton("لغو این کار", {
            action.run {
                env.api.cancelErrand(e.ref)
                env.cache.invalidate("errands")
                toasts.info("لغو شد.")
                onClose()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.GHOST, loading = action.busy)
    }
}
