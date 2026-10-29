package com.coinepro.hq.ui.notifications

import com.coinepro.hq.ui.itemMotion
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.level
import com.coinepro.hq.core.net.Notification
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.toneColors
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher

/** Notifications in five levels (urgent, decision, report, info, learning). Learning questions are answered
 *  with one touch. Approvals never happen here: a decision notification only opens the cartable. */
@Composable
fun NotificationsScreen() {
    val env = LocalEnv.current
    val nav = LocalNav.current
    var lvl by rememberSaveable { mutableStateOf<String?>(null) }
    val q = rememberQuery("notifications:${lvl ?: "all"}", "notifications") { notifications(level = lvl) }
    val r = refresher(q)
    val action = rememberAction()
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("اعلان‌ها", eyebrow = "پنج سطح؛ فوری هر جا باشی میرسد") {
                HqButton("همه خوانده شد", { action.run { env.api.readAll(); env.cache.invalidate("notifications", "inbox") } }, size = BtnSize.SM, variant = BtnVariant.SECONDARY, icon = DivanIcon.SEAL, loading = action.busy)
            }
        }
        item {
            com.coinepro.hq.designsystem.ScrollRow {
                FilterChip("همه", lvl == null, { lvl = null })
                for (l in listOf("urgent", "decision", "report", "info", "learning")) FilterChip(level(l).fa, lvl == l, { lvl = if (lvl == l) null else l })
            }
        }
        val list = q.data?.items
        when {
            list == null && q.error == null -> items(4) { Skeleton(Modifier.fillMaxWidth().height(76.dp), radius = 14.dp) }
            list == null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list.isEmpty() -> item { Empty("اعلانی نیست", icon = DivanIcon.BELL) }
            else -> items(list, key = { it.id }) { n -> Box(itemMotion()) {
                NotificationCard(n) {
                    action.run {
                        if (n.readAt == null) env.api.readNotification(n.id)
                        env.cache.invalidate("notifications", "inbox")
                        when (n.link?.kind) {
                            "decision" -> n.link.ref?.let { nav.go("cartable/$it") }
                            "deliverable" -> n.link.ref?.let { nav.go("outputs/$it") }
                            "work" -> n.link.ref?.let { nav.go("work/$it") }
                            "thread" -> n.link.ref?.let { nav.go("messages/$it") }
                        }
                    }
                }
            }}
        }
    }
}

@Composable
private fun NotificationCard(n: Notification, onOpen: () -> Unit) {
    val env = LocalEnv.current
    val c = Divan.colors
    val l = level(n.level)
    val (bg, fg) = toneColors(l.tone)
    val answer = rememberAction()
    HqCard(Modifier.fillMaxWidth(), onClick = onOpen, color = if (n.readAt == null) c.card else c.page, tahrir = n.readAt == null && n.level == "urgent") {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(36.dp).clip(CircleShape).background(bg), contentAlignment = Alignment.Center) { DIcon(l.icon, size = 18.dp, tint = fg) }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(l.fa, style = Divan.type.micro, color = fg)
                    CompanyMark(n.company, height = 11.dp, mono = true, ink = c.textMuted)
                    Text(ago(n.createdAt), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
                    if (n.readAt == null) Box(Modifier.size(8.dp).clip(CircleShape).background(c.goldFill))
                }
                RichText(n.titleFa, style = Divan.type.small.copy(fontWeight = if (n.readAt == null) FontWeight.Bold else FontWeight.SemiBold), color = c.textPrimary)
                if (n.bodyFa.isNotBlank()) RichText(n.bodyFa, style = Divan.type.caption, color = c.textSecondary)
                val choices = n.choices
                if (!choices.isNullOrEmpty()) {
                    FlowRow(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (ch in choices) {
                            val chosen = n.answer == ch.id
                            Text(
                                ch.labelFa, style = Divan.type.small, color = if (chosen) c.goldInk else c.textSecondary,
                                modifier = Modifier.clip(RoundedCornerShape(16.dp)).background(if (chosen) c.softGold else c.tile)
                                    .clickable(enabled = n.answer == null, role = Role.Button) { answer.run { env.api.answer(n.id, ch.id); env.cache.invalidate("notifications") } }
                                    .padding(horizontal = 12.dp, vertical = 6.dp),
                            )
                        }
                    }
                }
            }
        }
    }
}
