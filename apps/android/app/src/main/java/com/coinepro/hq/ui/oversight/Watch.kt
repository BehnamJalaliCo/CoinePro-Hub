package com.coinepro.hq.ui.oversight

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.Refs
import com.coinepro.hq.core.data.Watch
import com.coinepro.hq.core.data.WatchKind
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.net.Finding
import com.coinepro.hq.core.net.WorkCreate
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Space
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.rememberHaptics
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.itemMotion
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.FINDING_STATUS
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v14.SeverityPill

// ⟨1.10⟩ contract §28.3: the watch (دیده‌بان). The overseer's protocols over the apps, the hub and every company — a daily security sweep,
// the apps' own error reports grouped and traced to the code, a weekly code review per repository — with the advisor's weekly growth
// memo and the digital CEO's monthly «پیشنهاد هلدینگ». Each finding comes with the proposed fix; «تأیید اصلاح» opens the card or the
// session waiting for the owner's seal, or gives the fix as a work item when there is none yet. Same `/oversight/findings`, grouped.

private val KIND_ICON = mapOf(
    WatchKind.SECURITY to DivanIcon.LOCK, WatchKind.APP_HEALTH to DivanIcon.URGENT, WatchKind.CODE to DivanIcon.CODE,
    WatchKind.GROWTH to DivanIcon.CHART, WatchKind.HOLDING to DivanIcon.HOLDING,
)

@Composable
private fun rememberWatch() = Pair(
    rememberQuery("oversight:findings", "oversight") { findings().items },
    rememberQuery("oversight:protocols", "oversight", maxAgeMs = 120_000) { protocols() },
)

/** «دیده‌بان»: the watch's open findings by kind, with severity, the proposed fix and «تأیید اصلاح». */
@Composable
fun WatchScreen(kind0: String? = null) {
    val nav = LocalNav.current
    val c = Divan.colors
    val (findings, protocols) = rememberWatch()
    val r = refresher(findings, protocols)
    var kind by rememberSaveable { mutableStateOf(kind0) }
    var closed by rememberSaveable { mutableStateOf(false) }
    var open by remember { mutableStateOf<Finding?>(null) }
    val all = findings.data
    val groups = Watch.groups(all.orEmpty().filter { closed != Watch.open(it) }, protocols.data, includeClosed = true)
    val openCounts = Watch.groups(all.orEmpty(), protocols.data).associate { (k, l) -> k to l.size }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("دیده‌بان", eyebrow = "ناظر کل هر روز امنیت و سلامت اپ‌ها، هر هفته کد و رشد، و هر ماه فرصت‌های هلدینگ را میسنجد") {
                HqButton("ناظر کل", { nav.go("oversight") }, size = BtnSize.SM, icon = DivanIcon.OVERSEER)
            }
        }
        item {
            ScrollRow {
                FilterChip("همه", kind == null, { kind = null }, count = openCounts.values.sum().takeIf { it > 0 })
                for (k in WatchKind.entries) FilterChip(k.fa, kind == k.key, { kind = if (kind == k.key) null else k.key }, count = openCounts[k])
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip("باز", !closed, { closed = false })
                FilterChip("بسته و تأییدشده", closed, { closed = true })
            }
        }
        val shown = groups.filter { kind == null || it.first.key == kind }
        when {
            all == null && findings.error != null -> item { ErrorBlock(findings.error, { findings.refresh() }) }
            all == null -> items(3) { Skeleton(Modifier.fillMaxWidth().height(150.dp), radius = Radius.card) }
            shown.isEmpty() -> item {
                Empty(
                    if (closed) "یافته‌ی بسته‌ای نیست" else "دیده‌بان چیزی باز ندارد", icon = DivanIcon.SCOPE,
                    body = "پایش امنیتی و سلامت اپ هر روز، بازبینی کد و یادداشت رشد هر هفته، پیشنهاد هلدینگ هر ماه اجرا میشود؛ هر یافته با اصلاحش این‌جا میاید.",
                )
            }
            else -> for ((k, list) in shown) {
                item(key = "kind-${k.key}") { SectionTitle(k.fa, note = k.note, icon = KIND_ICON[k]) }
                items(list.size, key = { "w-${list[it].ref}" }) { i -> Box(itemMotion()) { WatchFindingCard(list[i], k) { open = list[i] } } }
            }
        }
    }
    open?.let { FindingSheet(it) { open = null } }
}

/** One watch finding: severity and company, what was found, the proposed fix, and «تأیید اصلاح». */
@Composable
internal fun WatchFindingCard(f: Finding, kind: WatchKind, onDetails: () -> Unit) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val haptics = rememberHaptics()
    val companies = rememberCompanies()
    val action = rememberAction()
    val live = Watch.open(f)
    val shape = RoundedCornerShape(Radius.card)
    HqCard(
        Modifier.fillMaxWidth().then(if (live && f.severity == "critical") Modifier.border(1.dp, c.negative.copy(alpha = 0.45f), shape) else Modifier),
        onClick = onDetails, onClickLabel = "جزئیات یافته",
    ) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            SeverityPill(f.severity)
            CompanyMark(f.company, height = 12.dp, mono = true, ink = c.textSecondary)
            Text(companyOf(companies, f.company).nameFa, style = Divan.type.caption, color = c.textSecondary)
            if (!live || f.status != "open") LabelPill(FINDING_STATUS[f.status], f.status)
            Fig(f.ref, style = Divan.type.figureSmall, color = c.textMuted)
        }
        RichText(f.titleFa, Modifier.padding(top = Space.xs), style = Divan.type.bodyStrong, color = c.textPrimary, maxLines = 3)
        if (f.bodyMd.isNotBlank()) Md(f.bodyMd, Modifier.padding(top = 4.dp), style = Divan.type.caption, color = c.textSecondary)
        val fix = f.fixMd?.takeIf { it.isNotBlank() } ?: f.fix?.summaryFa
        if (fix != null) Column(
            Modifier.padding(top = Space.sm).fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.softGold).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                DIcon(DivanIcon.EDIT, size = 14.dp, tint = c.goldInk)
                Text(if (kind == WatchKind.GROWTH || kind == WatchKind.HOLDING) "پیشنهاد" else "اصلاح پیشنهادی", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk, modifier = Modifier.weight(1f))
                f.fix?.ref?.let { Fig(it, style = Divan.type.figureSmall, color = c.goldInk) }
            }
            Md(fix, style = Divan.type.small, color = c.textPrimary)
        }
        Row(Modifier.padding(top = Space.sm), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(ago(f.openedAt), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            if (live && fix != null) HqButton("تأیید اصلاح", {
                val route = f.fix?.ref?.let(Refs::route)
                if (route != null) {
                    haptics.tick()
                    nav.go(route)
                } else action.run {
                    // No card or session yet: the fix becomes a work item for the company, from the finding, at its severity.
                    val w = env.api.createWork(
                        WorkCreate(
                            company = f.company, title = "اصلاح ${f.ref}: ${f.titleFa}".take(140),
                            brief = "$fix\n\nیافته‌ی دیده‌بان: ${f.ref}", priority = Watch.priorityOf(f.severity),
                        ),
                    )
                    env.orders.track(w)
                    env.cache.invalidate("work", "orders", "oversight")
                    haptics.confirm()
                    toasts.ok("اصلاح به ${w.ref} سپرده شد؛ مرحله‌به‌مرحله در «فرمان‌های من».")
                    nav.go("work/${w.id}")
                }
            }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = action.busy)
            HqButton("جزئیات", onDetails, variant = BtnVariant.TEXT, size = BtnSize.SM)
        }
    }
}

/** The watch's open findings by kind (empty while none, or while they load). */
@Composable
fun rememberWatchGroups(): List<Pair<WatchKind, List<Finding>>> {
    val (findings, protocols) = rememberWatch()
    return Watch.groups(findings.data.orEmpty(), protocols.data)
}

/** The home page's watch card, shown only while something is open: the count by kind and the most serious finding. */
@Composable
fun WatchHomeCard(groups: List<Pair<WatchKind, List<Finding>>>) {
    val nav = LocalNav.current
    val c = Divan.colors
    val top = groups.flatMap { it.second }.minByOrNull { listOf("critical", "high", "medium", "low", "info").indexOf(it.severity).let { i -> if (i < 0) 9 else i } }
    val serious = groups.sumOf { (_, l) -> l.count { it.severity == "critical" || it.severity == "high" } }
    HqCard(Modifier.fillMaxWidth(), tahrir = serious > 0, onClick = { nav.go("watch") }) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(44.dp).clip(CircleShape).background(if (serious > 0) c.softNegative else c.tile), contentAlignment = Alignment.Center) {
                DIcon(DivanIcon.SCOPE, size = 22.dp, tint = if (serious > 0) c.negative else c.goldInk)
            }
            Column(Modifier.weight(1f)) {
                Text("دیده‌بان", style = Divan.type.bodyStrong)
                Text(
                    groups.joinToString("، ") { (k, l) -> "${l.size} ${k.fa}" },
                    style = Divan.type.caption, color = if (serious > 0) c.negative else c.textSecondary, maxLines = 2,
                )
            }
            DIcon(DivanIcon.NEXT, size = 18.dp, tint = c.textMuted)
        }
        top?.let { f ->
            Row(Modifier.padding(top = 10.dp).fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.tile).padding(10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SeverityPill(f.severity)
                RichText(f.titleFa, Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary, maxLines = 2)
            }
        }
    }
}
