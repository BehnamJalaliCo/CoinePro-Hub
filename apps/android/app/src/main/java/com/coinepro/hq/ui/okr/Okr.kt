package com.coinepro.hq.ui.okr

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.KeyResult
import com.coinepro.hq.core.net.Objective
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.ActorAvatar
import com.coinepro.hq.ui.v17.OBJECTIVE_STATUS
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v17.ScopeChips
import com.coinepro.hq.ui.v17.num
import com.coinepro.hq.ui.v17.pct01

private const val CHECKIN_DAYS = 14

/** "1405-Q3" → «فصل سوم 1405» (the year in the text face's digits). */
fun quarterFa(q: String): String {
    val m = Regex("^(\\d{4})-Q(\\d)$").find(q) ?: return q
    val n = listOf("", "اول", "دوم", "سوم", "چهارم").getOrNull(m.groupValues[2].toInt()) ?: m.groupValues[2]
    return "فصل $n ${m.groupValues[1]}"
}

/** OKR (contract §20.5): each company's objectives by Jalali quarter. A CEO drafts, only the owner's seal makes it active. */
@Composable
fun OkrScreen() {
    val c = Divan.colors
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var quarter by rememberSaveable { mutableStateOf<String?>(null) }
    val q = rememberQuery("okr:list:${company.orEmpty()}", "okr") { okr(company) }
    val companies = rememberCompanies()
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("OKR", eyebrow = "هدف‌های فصل هر شرکت؛ فقط مُهر تو فعالشان میکند") }
        item {
            Text(
                "مدیرعامل در ماه آخر هر فصل OKR فصل بعد را پیش‌نویس میکند و کارتش به کارتابل تو میاید؛ بی‌مُهر، فصل بی‌OKR میماند. نتیجه‌ی کلیدی وصل به KPI مقدارش را از همان KPI میگیرد و هر ۱۴ روز یک check-in میخواهد.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        val all = q.data
        val quarters = all.orEmpty().map { it.quarter }.distinct().sortedDescending()
        val current = quarters.firstOrNull { x -> all.orEmpty().any { it.quarter == x && it.status == "active" } } ?: quarters.firstOrNull()
        val qtr = quarter ?: current
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                ScopeChips(company, { company = it }, holding = false, allLabel = "همه‌ی شرکت‌ها")
                if (quarters.isNotEmpty()) ChipRow { for (x in quarters) FilterChip(quarterFa(x), qtr == x, { quarter = x }) }
            }
        }
        val list = all.orEmpty().filter { qtr == null || it.quarter == qtr }.sortedBy { it.company }
        val without = companies.filter { co -> co.kind != "holding" && (company == null || co.code == company) && list.none { it.company == co.code && it.status == "active" } }
        when {
            all == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            all == null -> item { Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 16.dp) }
            list.isEmpty() && without.isEmpty() -> item { Empty("OKRی نیست", icon = DivanIcon.PLANNER) }
            else -> {
                for (o in list) item(key = o.ref) { ObjectiveCard(o) }
                if (qtr == current) for (co in without) item(key = "none:${co.code}") {
                    HqCard(Modifier.fillMaxWidth()) {
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            CompanyMark(co.code, height = 14.dp, mono = true, ink = c.textSecondary, modifier = Modifier.padding(top = 4.dp))
                            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text("${co.nameFa ?: co.code}: بدون OKR فعال در ${qtr?.let(::quarterFa) ?: "این فصل"}", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                                Text("تحقق KPI در امتیاز شرکت از سهم KPIهای کارت امتیاز که به هدف رسیده‌اند حساب میشود.", style = Divan.type.caption, color = c.textSecondary)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ObjectiveCard(o: Objective) {
    val c = Divan.colors
    val co = companyOf(rememberCompanies(), o.company)
    HqCard(Modifier.fillMaxWidth().alpha(if (o.status == "closed") 0.75f else 1f)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            CompanyMark(o.company, height = 13.dp, mono = true, ink = c.textSecondary)
            Text(co.nameFa, style = Divan.type.caption, color = c.textSecondary)
            Text(quarterFa(o.quarter), style = Divan.type.caption, color = c.textMuted)
            Fig(o.ref, style = Divan.type.figureSmall, color = c.textMuted)
            Spacer(Modifier.weight(1f))
            LabelPill(OBJECTIVE_STATUS[o.status], o.status)
        }
        o.decision?.let { Spacer(Modifier.height(6.dp)); RefChip(it, "مُهر", RefTone.NEUTRAL) }
        Spacer(Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(prose(o.titleFa), style = Divan.type.h3, color = c.textPrimary)
                Md(o.whyMd)
                Row(Modifier.padding(top = 2.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    ActorAvatar(o.owner, 20.dp)
                    Text(actorFa(o.owner), style = Divan.type.caption, color = c.textMuted)
                }
            }
            Column(Modifier.width(76.dp).clip(RoundedCornerShape(14.dp)).background(c.tile).padding(vertical = 12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Fig(pct01(o.progress), style = Divan.type.figureM.copy(fontSize = 22.sp, lineHeight = 28.sp), color = c.textPrimary)
                Text("پیشرفت وزنی", style = Divan.type.micro.copy(fontSize = 10.sp), color = c.textMuted)
            }
        }
        for (k in o.keyResults) {
            Spacer(Modifier.height(10.dp))
            Box(Modifier.fillMaxWidth().height(1.dp).background(c.lineDivider))
            Spacer(Modifier.height(10.dp))
            KrRow(k)
        }
    }
}

@Composable
private fun KrRow(k: KeyResult) {
    val c = Divan.colors
    val now = HqClock.millis()
    val last = k.checkins.maxByOrNull { it.at }
    val late = last == null || (instant(last.at)?.toEpochMilli()?.let { now - it > CHECKIN_DAYS * 86_400_000L } ?: true)
    var open by rememberSaveable(k.ref) { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Fig(k.ref, Modifier.padding(top = 3.dp), style = Divan.type.figureSmall, color = c.textMuted)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(prose(k.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                Text(if (k.kpi != null) buildAnnotatedString { append("از KPI "); fig(k.kpi, c.textSecondary) } else prose(k.metricFa.orEmpty()), style = Divan.type.micro, color = c.textMuted)
            }
        }
        Fig("${num(k.start)} → ${k.current?.let(::num) ?: "—"} → ${num(k.target)}", style = Divan.type.figure, color = c.textSecondary)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            MeterBar(k.progress * 100, Modifier.weight(1f), tone = if (k.progress >= 0.7) BarTone.POS else if (k.progress >= 0.3) BarTone.GOLD else BarTone.WARN)
            Fig(pct01(k.progress), Modifier.width(40.dp), style = Divan.type.figureSmall, color = c.textPrimary)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Text(buildAnnotatedString { append("اطمینان "); fig(pct01(k.confidence), c.textSecondary) }, style = Divan.type.micro, color = c.textMuted)
            Text(buildAnnotatedString { append("وزن "); fig(num(k.weight), c.textSecondary) }, style = Divan.type.micro, color = c.textMuted)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                if (late) DIcon(DivanIcon.TIME, size = 12.dp, tint = c.warning)
                Text(
                    if (last != null) "آخرین check-in ${ago(last.at)}" + if (late) "؛ بیش از $CHECKIN_DAYS روز" else "" else "هنوز check-in ندارد",
                    style = Divan.type.micro, color = if (late) c.warning else c.textMuted,
                )
            }
        }
        if (k.checkins.isNotEmpty()) {
            Row(Modifier.clip(RoundedCornerShape(6.dp)).clickable(role = Role.Button) { open = !open }.padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("check-inها (${k.checkins.size})", style = Divan.type.caption, color = c.textSecondary)
                com.coinepro.hq.designsystem.Chevron(open, tint = c.textSecondary)
            }
            com.coinepro.hq.designsystem.Expand(open) { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { for (ck in k.checkins.sortedByDescending { it.at }) Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                ActorAvatar(ck.by, 22.dp)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(buildAnnotatedString { append("${actorFa(ck.by)}، ${jDate(ck.at)} · اطمینان "); fig(pct01(ck.confidence)) }, style = Divan.type.micro, color = c.textMuted)
                    Md(ck.noteMd)
                    if (ck.evidence.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) { for (e in ck.evidence) RefChip(e.ref, tone = RefTone.NEUTRAL) }
                }
            } } }
        }
    }
}
