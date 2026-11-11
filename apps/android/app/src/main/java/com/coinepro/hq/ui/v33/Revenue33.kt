package com.coinepro.hq.ui.v33

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.GAP_STATE_FA
import com.coinepro.hq.core.data.gapUsdt
import com.coinepro.hq.core.data.moneyFigure
import com.coinepro.hq.core.data.pctText
import com.coinepro.hq.core.data.usdtText
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jMonth
import com.coinepro.hq.core.net.AffiliateGap
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HBarRow
import com.coinepro.hq.designsystem.HBars
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StatRow
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served

// Contract §33.3, §33.5 ⟨1.15⟩: the revenue board of the holding or of one company (every figure by code), where the money comes from,
// and the months an exchange paid less commission than it owed.

/** «تابلوی درآمد»: the holding's board, or one company's (a chip per company; companies are data). */
@Composable
fun RevenueBoardScreen(company0: String? = null) {
    val companies = rememberCompanies()
    var company by rememberSaveable { mutableStateOf(company0) }
    val q = rememberQuery("revenue-board:${company ?: "holding"}", "money", "payments", maxAgeMs = 60_000) { gated(HubFeature.MONEY) { revenueBoard(company) } }
    val src = rememberQuery("revenue-by-source:month", "money", "revenue", maxAgeMs = 60_000) { gated(HubFeature.MONEY) { revenueBySource("month") } }
    val r = refresher(q, src)
    val has = served(HubFeature.MONEY)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("تابلوی درآمد", eyebrow = "درآمد ماهانه، ریزش، ارزش هر مشتری و پیش‌بینی؛ همه را کد از پرداخت‌ها حساب میکند") }
        if (!has) {
            item { Empty("تابلوی درآمد با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.CHART) }
            return@Page
        }
        item {
            ScrollRow {
                FilterChip("کل هلدینگ", company == null, { company = null })
                for (co in companies.filter { it.kind != "holding" }) FilterChip(co.nameFa ?: co.code, company == co.code, { company = co.code })
            }
        }
        val b = q.data
        when {
            b == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            b == null -> item { Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 16.dp) }
            b.months.isEmpty() -> item { Empty("هنوز پرداختی خوانده نشده", icon = DivanIcon.TREASURY, body = "وقتی منبع پرداخت یک شرکت وصل و خوانده شود، تابلو از همان ساخته میشود.") }
            else -> item(key = "board") { RevenueBoardBody(b) }
        }
        src.data?.let { s -> if (s.bySource.isNotEmpty()) item(key = "by-source") { BySourceCard(s.bySource.filter { company == null || it.company == company }) } }
    }
}

/** «از کجا میاید»: each company's month from the affiliate commission and from its customers' payments, side by side. */
@Composable
fun BySourceCard(rows: List<com.coinepro.hq.core.net.RevBySource>) {
    if (rows.isEmpty()) return
    val c = Divan.colors
    val companies = rememberCompanies()
    val total = rows.sumOf { it.totalUsdt }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("از کجا میاید", note = "30 روز اخیر؛ جمع ${moneyFigure(total)} USDT")
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            val aff = rows.sumOf { it.affiliateUsdt }
            val pay = rows.sumOf { it.paymentsUsdt }
            HBars(listOf(
                HBarRow("affiliate", aff, "${moneyFigure(aff)} USDT", c.chart[0]) { Text("کمیسیون صرافی‌ها", style = Divan.type.small) },
                HBarRow("payments", pay, "${moneyFigure(pay)} USDT", c.chart[1]) { Text("پرداخت مشتری‌ها", style = Divan.type.small) },
            ))
            if (rows.size > 1) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                HorizontalDivider(color = c.lineDivider)
                for (x in rows.sortedByDescending { it.totalUsdt }) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(companyOf(companies, x.company).nameFa, Modifier.weight(1f), style = Divan.type.small, color = c.textSecondary)
                    Fig(usdtText(x.totalUsdt), style = Divan.type.figureSmall, color = c.textPrimary)
                }
            }
            val store = rows.sumOf { it.storePayments }
            if (store > 0) Text(plain("$store پرداخت درون‌برنامه‌ای هم بود که مبلغش را فروشگاه نگه میدارد؛ شمرده شد، جمع نشد."), style = Divan.type.micro, color = c.textMuted)
        }
    }
}

// ----------------------------------------------------------- affiliate gaps --
/** «کسری کمیسیون»: due against received, per exchange account and month; a gap over the threshold opens a follow-up for finance. */
@Composable
fun AffiliateGapsScreen(company0: String? = null) {
    val companies = rememberCompanies()
    var company by rememberSaveable { mutableStateOf(company0) }
    var state by rememberSaveable { mutableStateOf<String?>("open") }
    val q = rememberQuery("affiliate-gaps:${company ?: "all"}", "money", "revenue", maxAgeMs = 60_000) { gated(HubFeature.MONEY) { affiliateGaps(company) } }
    val r = refresher(q)
    val has = served(HubFeature.MONEY)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("کسری کمیسیون", eyebrow = "آنچه صرافی باید میپرداخت در برابر آنچه رسید؛ هر ماه بعد از تسویه") }
        if (!has) {
            item { Empty("کسری کمیسیون با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.TREASURY) }
            return@Page
        }
        val all = q.data
        item {
            ScrollRow {
                FilterChip("همه", state == null, { state = null }, count = all?.size)
                for (s in listOf("open", "waiting", "closed", "ok")) FilterChip(GAP_STATE_FA[s]?.first ?: s, state == s, { state = if (state == s) null else s }, count = all?.count { it.state == s })
            }
        }
        if (companies.count { it.kind != "holding" } > 1) item {
            ScrollRow {
                FilterChip("همه‌ی شرکت‌ها", company == null, { company = null })
                for (co in companies.filter { it.kind != "holding" }) FilterChip(co.nameFa ?: co.code, company == co.code, { company = co.code })
            }
        }
        val list = all?.filter { state == null || it.state == state }?.sortedWith(compareByDescending<AffiliateGap> { it.month }.thenByDescending { it.gapUsdt })
        when {
            list == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list == null -> item { Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = 16.dp) }
            list.isEmpty() -> item { Empty(if (state == "open") "کسری بازی نیست" else "موردی نیست", icon = DivanIcon.SEAL, body = "هر ماه بعد از روز تسویه‌ی صرافی، کمیسیون رسیده با کمیسیون حساب‌شده مقایسه میشود.") }
            else -> items(list.size, key = { "${list[it].account}:${list[it].month}" }) { i -> GapCard(list[i]) }
        }
    }
}

@Composable
fun GapCard(g: AffiliateGap) {
    val c = Divan.colors
    val nav = LocalNav.current
    val companies = rememberCompanies()
    val st = GAP_STATE_FA[g.state] ?: (g.state to Tone.SILVER)
    var open by rememberSaveable("${g.account}:${g.month}") { mutableStateOf(false) }
    HqCard(Modifier.fillMaxWidth(), onClick = if (g.draftFa.isNullOrBlank()) null else ({ open = !open })) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(plain("${jMonth(g.month)} · ${companyOf(companies, g.company).nameFa}"), style = Divan.type.bodyStrong)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Fig(g.exchange, style = Divan.type.figureSmall, color = c.textSecondary)
                    Fig(g.account, style = Divan.type.figureSmall, color = c.textMuted)
                }
            }
            Pill(st.first, st.second, dot = true)
        }
        StatRow(Modifier.padding(top = 10.dp)) {
            StatTile("باید میرسید", moneyFigure(g.dueUsdt), Modifier.weight(1f), sub = "USDT")
            StatTile("رسید", moneyFigure(g.receivedUsdt), Modifier.weight(1f), sub = "USDT")
            StatTile("کسری", moneyFigure(gapUsdt(g)), Modifier.weight(1f), sub = pctText(g.gapPct, 1), tone = if (g.state == "open") Tone.WARN else null)
        }
        if (g.state == "waiting" && g.settlesOn.isNotBlank()) Text(plain("صرافی تا ${jDate(g.settlesOn)} تسویه میکند؛ تا آن روز کسری حساب نمیشود."), Modifier.padding(top = 8.dp), style = Divan.type.caption, color = c.textMuted)
        if (!g.draftFa.isNullOrBlank()) {
            if (open) Column(Modifier.padding(top = 10.dp).fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("پیش‌نویس پیام پیگیری", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                Para(g.draftFa, style = Divan.type.small, color = c.textPrimary)
            } else Text("پیش‌نویس پیام پیگیری آماده است؛ بزن تا ببینی.", Modifier.padding(top = 8.dp), style = Divan.type.caption, color = c.silverInk)
        }
        g.workRef?.let { ref ->
            Box(Modifier.padding(top = 8.dp)) {
                HqButton("کار پیگیری مالی", { nav.go("work/$ref") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.TASK)
            }
        }
    }
}
