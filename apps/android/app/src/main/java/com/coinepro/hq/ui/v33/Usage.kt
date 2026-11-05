package com.coinepro.hq.ui.v33

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
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
import com.coinepro.hq.core.data.USAGE_ANOMALY_FA
import com.coinepro.hq.core.data.domainFa
import com.coinepro.hq.core.data.pctText
import com.coinepro.hq.core.data.tokensShort
import com.coinepro.hq.core.data.usagePeriodFa
import com.coinepro.hq.core.data.dollars
import com.coinepro.hq.core.data.vsPrevFa
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.UsagePack
import com.coinepro.hq.core.net.UsageReport
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Chevron
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HBarRow
import com.coinepro.hq.designsystem.HBars
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StatRow
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served

// Contract §33.1 ⟨1.15⟩ «گزارش مصرف»: the usage of the holding in the advisor's words. The figures are the pack, computed by code; the
// words are one model call over the pack only. The latest report on top, a button for a fresh one, the figures under «جزئیات», the
// older reports below.

@Composable
fun UsageScreen(period0: String = "week") {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    var period by rememberSaveable { mutableStateOf(period0) }
    var pick by rememberSaveable { mutableStateOf<String?>(null) }
    val q = rememberQuery("usage-reports:$period", "usage", "money", maxAgeMs = 60_000) { gated(HubFeature.MONEY) { usageReports(period) } }
    val make = rememberAction()
    val r = refresher(q)
    val has = served(HubFeature.MONEY)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("گزارش مصرف", eyebrow = "مشاور میگوید هزینه کجا رفت و کجا میشود کم کرد")
        }
        if (!has) {
            item { Empty("گزارش مصرف با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.CHART) }
            return@Page
        }
        item {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Segmented(listOf(SegOption("week", "هفتگی"), SegOption("day", "روزانه")), period, { period = it; pick = null }, Modifier.weight(1f))
                HqButton("تازه بساز", {
                    make.run {
                        env.api.makeUsageReport(period)
                        env.cache.invalidate("usage")
                        pick = null
                        toasts.ok("گزارش تازه نوشته شد.")
                    }
                }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.REFRESH, loading = make.busy)
            }
        }
        val list = q.data?.items
        when {
            list == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list == null -> item { Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 16.dp) }
            list.isEmpty() -> item {
                Empty("هنوز گزارشی نیست", icon = DivanIcon.CHART, body = "گزارش روزانه هر صبح و گزارش هفتگی شنبه‌ها نوشته میشود؛ همین حالا هم میتوانی یکی بسازی.")
            }
            else -> {
                val shown = list.firstOrNull { it.ref == pick } ?: list.first()
                item(key = "report-${shown.ref}") { UsageReportCard(shown, head = true) }
                val rest = list.filter { it.ref != shown.ref }
                if (rest.isNotEmpty()) item(key = "history") {
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("گزارش‌های قبلی")
                        Column(Modifier.padding(top = 6.dp)) {
                            rest.forEachIndexed { i, x ->
                                if (i > 0) HorizontalDivider(color = Divan.colors.lineDivider)
                                HistoryRow(x) { pick = x.ref }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun HistoryRow(r: UsageReport, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable(role = Role.Button, onClick = onClick).padding(vertical = 10.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(plain(r.text?.linesFa?.firstOrNull() ?: "گزارش ${usagePeriodFa(r.period)}"), style = Divan.type.small, color = c.textPrimary, maxLines = 2)
            Text(plain("${jDate(r.from)} تا ${jDate(r.to)}"), style = Divan.type.micro, color = c.textMuted)
        }
        Fig(dollars(r.pack.byDomain.sumOf { it.usdEquiv }), style = Divan.type.figureSmall, color = c.textSecondary)
    }
}

/** One report: the advisor's lines, one saving, and the pack under «جزئیات». */
@Composable
fun UsageReportCard(r: UsageReport, head: Boolean = false, open0: Boolean = false) {
    val c = Divan.colors
    var open by rememberSaveable(r.ref) { mutableStateOf(open0) }
    HqCard(Modifier.fillMaxWidth(), tahrir = head) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("گزارش مصرف ${usagePeriodFa(r.period)}", style = Divan.type.bodyStrong)
                Text(plain("${jDate(r.from)} تا ${jDate(r.to)} · نوشته شده ${jDateTime(r.at)}"), style = Divan.type.micro, color = c.textMuted)
            }
            Pill("مشاور", Tone.GOLD, icon = DivanIcon.ADVISOR)
        }
        val t = r.text
        if (t == null || t.linesFa.isEmpty()) {
            Para("متن این گزارش هنوز نوشته نشده؛ عددها در «جزئیات» هست.", Modifier.padding(top = 10.dp), color = c.textMuted)
        } else {
            Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                t.linesFa.forEachIndexed { i, l ->
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
                        Box(Modifier.padding(top = 3.dp).size(20.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) {
                            Fig("${i + 1}", style = Divan.type.micro, color = c.textSecondary)
                        }
                        Para(l, Modifier.weight(1f), style = Divan.type.body, color = c.textPrimary)
                    }
                }
            }
            if (t.savingFa.isNotBlank()) Column(
                Modifier.padding(top = 12.dp).fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softGold).padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text("یک صرفه‌جویی", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
                Para(t.savingFa, style = Divan.type.small, color = c.textPrimary)
            }
        }
        Row(
            Modifier.padding(top = 10.dp).clip(RoundedCornerShape(10.dp)).clickable(role = Role.Button) { open = !open }.padding(vertical = 6.dp, horizontal = 2.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text("جزئیات", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
            Chevron(open, tint = c.goldInk)
        }
        Expand(open) { Box(Modifier.padding(top = 8.dp)) { UsagePackBody(r.pack) } }
    }
}

/** The figures of a report, as code computed them. */
@Composable
fun UsagePackBody(p: UsagePack) {
    val c = Divan.colors
    val companies = rememberCompanies()
    val total = p.byDomain.sumOf { it.usdEquiv }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        StatRow {
            StatTile("خرج مدل‌ها", dollars(total), Modifier.weight(1f), sub = vsPrevFa(p.vsPrev.usdPct) ?: "دوره‌ی قبل نبود")
            StatTile("توکن", tokensShort(p.byDomain.sumOf { it.tokens }), Modifier.weight(1f), sub = vsPrevFa(p.vsPrev.tokensPct) ?: "دوره‌ی قبل نبود")
        }
        StatRow {
            StatTile("صدا", dollars(p.voiceUsd), Modifier.weight(1f))
            StatTile("تبلیغات", dollars(p.adsSpendUsd), Modifier.weight(1f))
            StatTile("خط تولید", "${p.lines.runs}", Modifier.weight(1f), sub = "اجرا، ${tokensShort(p.lines.tokens)} توکن")
        }
        if (p.byDomain.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("به تفکیک کار", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            HBars(p.byDomain.sortedByDescending { it.usdEquiv }.map { d ->
                HBarRow(d.domain, d.usdEquiv, "${dollars(d.usdEquiv)} · ${pctText(d.share * 100)}") { Text(domainFa(d.domain), style = Divan.type.small) }
            })
        }
        if (p.byCompany.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("به تفکیک شرکت", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            HBars(p.byCompany.sortedByDescending { it.usdEquiv }.map { x ->
                HBarRow(x.company, x.usdEquiv, "${dollars(x.usdEquiv)} · ${pctText(x.share * 100)}") { Text(companyOf(companies, x.company).nameFa, style = Divan.type.small) }
            })
        }
        if (p.topRuns.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("پرمصرف‌ترین کارها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            for (x in p.topRuns) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Fig(x.ref, style = Divan.type.figureSmall, color = c.textMuted)
                Text(plain(x.role ?: ""), Modifier.weight(1f), style = Divan.type.small, color = c.textSecondary, maxLines = 1)
                Fig(tokensShort(x.tokens), style = Divan.type.figureSmall, color = c.textPrimary)
            }
        }
        if (p.anomalies.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("چیزهای غیرعادی", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.warning)
            for (a in p.anomalies) Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.softWarning).padding(10.dp),
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                USAGE_ANOMALY_FA[a.kind]?.let { Text(it, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary) }
                Para(a.note, style = Divan.type.caption, color = c.textSecondary)
            }
        }
    }
}
