package com.coinepro.hq.ui.archive

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.DueReminder
import com.coinepro.hq.core.net.RetentionDue
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone

// Reminders and the end of retention (contract §23.5, §23.6), mirroring apps/web/src/app/(app)/archive/{reminders,retention}/page.tsx.

/** یادآورها: due reminders, nearest first, with the days left; closing one closes it everywhere (the cartable or the digest too). */
@Composable
fun RemindersScreen() {
    val c = Divan.colors
    val nav = LocalNav.current
    val arch = rememberArchive()
    val q = rememberQuery("archive:reminders", "archive", maxAgeMs = 300_000) { dueReminders() }
    val r = refresher(q, arch.q)
    val xs = q.data.orEmpty().sortedWith(compareBy<DueReminder> { it.state == "done" }.thenBy { it.daysLeft })
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("یادآورها", eyebrow = "بایگانی · قراردادها، مجوزها و دامنه‌ها پیش از سررسید") }
        item {
            Text(
                "هر یادآور از قاعده‌ی نوع سند میآید (مثلاً پایان قرارداد ۶۰، ۳۰ و ۷ روز قبل). وقتی کار اصلی انجام شد (تمدید، بازبینی، فسخ) اینجا ببندش؛ تا بسته نشود در کارتابل یا خلاصه‌ی روزانه میماند.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        item {
            HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(8.dp)) {
                when {
                    q.data == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
                    q.data == null -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { repeat(3) { Skeleton(Modifier.fillMaxWidth().height(80.dp), radius = 14.dp) } }
                    xs.isEmpty() -> Empty("یادآوری سر نرسیده", icon = DivanIcon.TIME, body = "هر سررسیدی که به روزهای قاعده‌اش برسد اینجا می‌آید.")
                    else -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { for (x in xs) ReminderRow(x, arch.m) }
                }
            }
        }
        item {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("قاعده‌ها در", style = Divan.type.caption, color = c.textMuted)
                Text("طرح بایگانی، یادآورها", Modifier.clickable(role = Role.Button) { nav.go("archive-settings/reminders") }, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
            }
        }
    }
}

@Composable
private fun ReminderRow(x: DueReminder, m: ArchiveMaps) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val nav = LocalNav.current
    val c = Divan.colors
    val action = rememberAction()
    val f = m.cls(x.cls)?.fields?.firstOrNull { it.key == x.field }
    val closed = x.state == "done"
    val tone = when { closed -> c.textMuted; x.daysLeft <= 7 -> c.negative; x.daysLeft <= 30 -> c.warning; else -> c.textSecondary }
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(if (closed) c.page else c.tile).padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top,
    ) {
        Column(Modifier.width(72.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
            DIcon(DivanIcon.TIME, size = 18.dp, tint = tone)
            Text(if (closed) "انجام شد" else daysLeftFa(x.daysLeft.toLong()), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = tone, textAlign = TextAlign.Center)
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(prose(x.titleFa), Modifier.clickable(role = Role.Button) { nav.go("archive/${x.record}") }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                Fig(x.record, style = Divan.type.figureSmall, color = c.textSecondary)
                ScopeTag(x.scope)
                ClassTag(x.cls, m)
                Text(buildAnnotatedString { append((f?.titleFa ?: x.field) + ": "); append(jDay(x.at)) }, style = Divan.type.micro, color = c.textMuted)
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                Text("${x.leadDays} روز پیش از موعد", style = Divan.type.micro, color = c.textMuted)
                Text("برای ${reminderToFa(x.to)}، در ${CHANNEL_FA[x.channel] ?: x.channel}", style = Divan.type.micro, color = c.textMuted)
                x.rule?.let { RefChip(it, tone = RefTone.NEUTRAL) }
            }
            if (closed) Pill("بسته", Tone.POS, icon = DivanIcon.SEAL)
            else HqButton("انجام شد", {
                action.archive(toasts) {
                    env.api.reminderDone(x.id)
                    env.cache.invalidate("archive", "decisions")
                    toasts.ok("یادآور بسته شد.")
                }
            }, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = action.busy)
        }
    }
}

/** پایان نگهداری: records whose retention ended; disposal happens only through the owner's `archive_disposal` card. */
@Composable
fun RetentionScreen() {
    val c = Divan.colors
    val nav = LocalNav.current
    val arch = rememberArchive()
    val q = rememberQuery("archive:retention", "archive") { retentionDue() }
    val r = refresher(q, arch.q)
    val xs = q.data.orEmpty().sortedBy { it.dueAt }
    val cards = xs.mapNotNull { it.decisionRef }.distinct()
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("پایان نگهداری", eyebrow = "بایگانی · سندهایی که نگهداری‌شان تمام شده") }
        item {
            Text(
                "هیچ سندی از اینجا پاک نمیشود. امحا فقط با مُهر تو روی کارت هفتگی «امحای سندهای بایگانی» است؛ بعد از آن فایل‌ها نابود میشوند و سنگ‌نشان (شناسه، نوع، عنوان، تاریخ‌ها، hash و همان تصمیم) میماند. سند زیر توقیف رد میشود.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        if (cards.isNotEmpty()) item {
            FlowRow(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.softGold).padding(12.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically,
            ) {
                DIcon(DivanIcon.SEAL, size = 18.dp, tint = c.goldInk)
                Text("کارت امحای منتظر مُهر تو:", style = Divan.type.small, color = c.textPrimary)
                for (d in cards) Fig(d, Modifier.clickable(role = Role.Button) { nav.go("cartable/$d") }, style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(8.dp)) {
                when {
                    q.data == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
                    q.data == null -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { repeat(3) { Skeleton(Modifier.fillMaxWidth().height(80.dp), radius = 14.dp) } }
                    xs.isEmpty() -> Empty("نگهداری هیچ سندی تمام نشده", icon = DivanIcon.MEMORY, body = "وقتی قاعده‌ی نگهداری سندی به پایان برسد، اینجا با کارت امحایش میآید.")
                    else -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { for (x in xs) RetentionRow(x, arch.m) }
                }
            }
        }
        item {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("قاعده‌ها در", style = Divan.type.caption, color = c.textMuted)
                Text("طرح بایگانی، نگهداری", Modifier.clickable(role = Role.Button) { nav.go("archive-settings/retention") }, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
                Text("؛ پیش‌فرض‌اند، نه نظر حقوقی.", style = Divan.type.caption, color = c.textMuted)
            }
        }
    }
}

@Composable
private fun RetentionRow(x: RetentionDue, m: ArchiveMaps) {
    val c = Divan.colors
    val nav = LocalNav.current
    val rule = m.schema?.retention?.firstOrNull { it.ref == x.rule }
    val held = x.holds.isNotEmpty()
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(if (held) c.softNegative else c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(prose(x.titleFa), Modifier.weight(1f).clickable(role = Role.Button) { nav.go("archive/${x.ref}") }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
            when {
                held -> Pill("توقیف؛ رد میشود و میماند", Tone.NEG, icon = DivanIcon.LOCK)
                x.then == "dispose_card" && x.decisionRef != null -> Pill("در کارت امحا", Tone.GOLD, icon = DivanIcon.SEAL)
                x.then == "dispose_card" -> Pill("در کارت هفته‌ی بعد", Tone.WARN, icon = DivanIcon.TIME)
                else -> Pill("بازبینی بایگان", Tone.LAPIS, icon = DivanIcon.AGENT)
            }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Fig(x.ref, style = Divan.type.figureSmall, color = c.textSecondary)
            ScopeTag(x.scope)
            ClassTag(x.cls, m)
            Text(buildAnnotatedString { append("آغاز "); append(jDay(x.triggerAt)) }, style = Divan.type.micro, color = c.textMuted)
            Text(buildAnnotatedString { append("پایان "); append(jDay(x.dueAt)) }, style = Divan.type.micro, color = c.textMuted)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            RefChip(x.rule, tone = RefTone.NEUTRAL)
            rule?.let { Text(prose(it.titleFa), style = Divan.type.caption, color = c.textSecondary) }
            Text("· ${THEN_FA[x.then] ?: x.then}", style = Divan.type.caption, color = c.textMuted)
            if (held) for (h in x.holds) Fig(h, Modifier.clickable(role = Role.Button) { nav.go("archive-holds/$h") }, style = Divan.type.figureSmall, color = c.negative)
            x.decisionRef?.let { d ->
                Row(Modifier.clickable(role = Role.Button) { nav.go("cartable/$d") }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    DIcon(DivanIcon.CARTABLE, size = 14.dp, tint = c.goldInk)
                    Text(buildAnnotatedString { append("کارت "); fig(d) }, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
                }
            }
        }
    }
}
