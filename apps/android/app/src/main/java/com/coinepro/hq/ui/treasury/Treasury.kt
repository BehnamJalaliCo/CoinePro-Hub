package com.coinepro.hq.ui.treasury

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.CONNECTION_STATUS
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.agentKindOf
import com.coinepro.hq.core.format.deptOf
import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.ownerDay
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.pct
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.designsystem.Avatar
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.CumulativeChart
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HBarRow
import com.coinepro.hq.designsystem.HBars
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Seg
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StackedBar
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.budgetTone
import com.coinepro.hq.designsystem.fig
import androidx.compose.ui.text.buildAnnotatedString
import com.coinepro.hq.designsystem.generated.TokenTypeSlot
import com.coinepro.hq.ui.Loadable
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.home.BudgetLine
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import java.time.LocalDate
import java.time.ZoneId

/** The token treasury (D2·2): every model call is metered in one ledger, whatever the connection. Real API
 *  spend is separate from the subscription's equivalent cost. Company colours are their fixed palette slots. */
@Composable
fun TreasuryScreen() {
    val c = Divan.colors
    val companies = rememberCompanies()
    var period by rememberSaveable { mutableStateOf("month") }
    val sum = rememberQuery("treasury:$period", "treasury") { treasury(period) }
    val byCo = rememberQuery("treasury:by:company:$period", "treasury") { breakdown("company", from = periodStart(period)) }
    val byModel = rememberQuery("treasury:by:model:$period", "treasury") { breakdown("model", from = periodStart(period)) }
    val month = rememberQuery("treasury:month", "treasury") { treasury("month") }
    val start = month.data?.periodStart?.let(::ownerDay)?.takeIf { it != "—" }
    val byDay = if (start != null) rememberQuery("treasury:by:day:$start", "treasury") { breakdown("day", from = start) } else null
    val conns = rememberQuery("connections", "treasury") { connections() }
    val r = refresher(*listOfNotNull(sum, month, byCo, byModel, byDay, conns).toTypedArray())
    val slot = { i: Int? -> if (i != null && i in 1..8) c.chart[i - 1] else c.silverInk }
    var editBudgets by rememberSaveable { mutableStateOf(false) }
    var editConn by remember { mutableStateOf<com.coinepro.hq.core.net.Connection?>(null) }

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("خزانه‌ی توکن", eyebrow = "مصرف هر فراخوانی، از یک مسیر واحد")
        }
        item { Segmented(listOf(SegOption("day", "امروز"), SegOption("month", "این ماه")), period, { period = it }, Modifier.fillMaxWidth()) }
        item {
            Loadable(sum, skeleton = { Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = 14.dp) }) { s ->
                val t = s.totals
                val holding = s.budgets.firstOrNull { it.scopeType == "holding" }
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        StatTile("توکن ورودی و خروجی", tokens(t.inputTokens + t.outputTokens), Modifier.weight(1f), subRich = buildAnnotatedString { fig(tokens(t.cacheReadTokens)); append(" از کش خوانده شد") })
                        StatTile("هزینه‌ی معادل", usd(t.equivCostUsd), Modifier.weight(1f), subRich = buildAnnotatedString { append("پرداخت واقعی API: "); fig(usd(t.costUsd)) })
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        StatTile("فراخوانی", t.calls.toString(), Modifier.weight(1f), sub = if (period == "day") "از امروز صبح" else "از اول ماه", figure = false)
                        StatTile("بودجه‌ی مصرف‌شده", pct(holding?.pct), Modifier.weight(1f), subRich = holding?.let { buildAnnotatedString { fig("${tokens(it.tokensUsed)} / ${tokens(it.tokenLimit)}") } },
                            tone = when (budgetTone(holding?.pct)) { com.coinepro.hq.designsystem.BarTone.NEG -> Tone.NEG; com.coinepro.hq.designsystem.BarTone.WARN -> Tone.WARN; else -> null }, figure = false)
                    }
                }
            }
        }
        item { com.coinepro.hq.ui.owner.QuotaCard() }
        // The server's breakdown by day (contract v1.2 addition); hidden until it answers with days.
        val days = byDay?.data.orEmpty().filter { it.key != null }
        if (days.size >= 2 && start != null) item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("مصرف تجمعی ماه", note = "خط قرمز سقف بودجه؛ خط‌چین پیش‌بینی تا آخر ماه با همین آهنگ")
                val budget = month.data?.budgets?.firstOrNull { it.scopeType == "holding" }?.tokenLimit?.toDouble()
                val first = LocalDate.parse(start)
                CumulativeChart(
                    days.map { jDate(it.key + "T12:00:00Z") to (it.inputTokens + it.outputTokens).toDouble() },
                    budget = budget,
                    forecastTo = java.time.temporal.ChronoUnit.DAYS.between(first, first.plusMonths(1)).toInt(),
                    fmt = { tokens(it.toLong()) },
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("نوع توکن", note = "فکر در اشتراک جدا گزارش نمیشود و داخل خروجی است")
                val t = sum.data?.totals
                if (t == null) Skeleton(Modifier.fillMaxWidth().height(40.dp).padding(top = 8.dp))
                else StackedBar(
                    listOf(
                        Seg("in", "ورودی", t.inputTokens.toDouble(), c.chart[TokenTypeSlot.INPUT - 1], tokens(t.inputTokens)),
                        Seg("out", "خروجی", t.outputTokens.toDouble(), c.chart[TokenTypeSlot.OUTPUT - 1], tokens(t.outputTokens)),
                        Seg("cache", "کش", (t.cacheReadTokens + t.cacheWriteTokens).toDouble(), c.chart[TokenTypeSlot.CACHE - 1], tokens(t.cacheReadTokens + t.cacheWriteTokens)),
                    ),
                    label = "تقسیم توکن‌ها", modifier = Modifier.padding(top = 12.dp),
                )
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("شرکت‌ها", note = "رنگ هر شرکت ثابت است، نه بر اساس رتبه")
                Loadable(byCo) { rows ->
                    HBars(
                        rows.filter { it.key != null }.sortedByDescending { it.equivCostUsd.toDoubleOrNull() ?: 0.0 }.map { row ->
                            val co = companyOf(companies, row.key)
                            HBarRow(row.key!!, row.equivCostUsd.toDoubleOrNull() ?: 0.0, usd(row.equivCostUsd), slot(co.colorIndex), tokens(row.inputTokens + row.outputTokens)) {
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    CompanyMark(co.code, height = 13.dp, mono = true, ink = c.textSecondary)
                                    Text(if (co.holding) "هلدینگ" else co.nameFa, style = Divan.type.small)
                                }
                            }
                        },
                        Modifier.padding(top = 12.dp),
                    )
                }
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("مدل‌ها")
                Loadable(byModel) { rows ->
                    HBars(
                        rows.filter { it.key != null }.sortedByDescending { it.equivCostUsd.toDoubleOrNull() ?: 0.0 }.map { row ->
                            HBarRow(row.key!!, row.equivCostUsd.toDoubleOrNull() ?: 0.0, usd(row.equivCostUsd), c.silverInk, "${row.calls} فراخوانی") {
                                Fig(modelLabel(row.key), style = Divan.type.figure)
                            }
                        },
                        Modifier.padding(top = 12.dp),
                    )
                }
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("بودجه‌ها", note = "هشدار در ۷۰٪ و ۹۰٪؛ در ۱۰۰٪ کارهای غیرفوری میایستند", action = {
                    com.coinepro.hq.designsystem.HqButton("ویرایش", { editBudgets = true }, size = com.coinepro.hq.designsystem.BtnSize.SM, variant = com.coinepro.hq.designsystem.BtnVariant.TEXT, icon = com.coinepro.hq.designsystem.generated.DivanIcon.EDIT)
                })
                Loadable(sum) { s ->
                    Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        s.budgets.forEach { b -> BudgetLine(b.scopeType == "holding", b.company, companyOf(companies, b.company).nameFa, b.tokensUsed, b.tokenLimit, b.pct) }
                    }
                }
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("پرمصرف‌ها")
                Loadable(sum) { s ->
                    Column(Modifier.padding(top = 8.dp)) {
                        s.topConsumers.forEachIndexed { i, x ->
                            if (i > 0) HorizontalDivider(color = c.lineDivider)
                            Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                Text((i + 1).toString(), style = Divan.type.caption, color = c.textMuted)
                                Avatar(agentKindOf(x.actor), dept = deptOf(x.actor), size = 32.dp)
                                Column(Modifier.weight(1f)) {
                                    Fig(x.actor, style = Divan.type.figure)
                                    Text("${x.calls} فراخوانی", style = Divan.type.micro, color = c.textMuted)
                                }
                                Fig(tokens(x.tokens), style = Divan.type.figureSmall, color = c.textMuted)
                                Fig(usd(x.usd), style = Divan.type.figure)
                            }
                        }
                    }
                }
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("اتصال‌ها", note = "کلیدها هرگز نمایش داده نمیشوند")
                Loadable(conns) { list ->
                    Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        list.forEach { x ->
                            val (label, tone) = CONNECTION_STATUS[x.status] ?: (x.status to Tone.NEUTRAL)
                            HqCard(Modifier.fillMaxWidth().clickable { editConn = x }, color = c.tile, radius = 12.dp, padding = androidx.compose.foundation.layout.PaddingValues(12.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                        Text(x.displayName, style = Divan.type.small.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold))
                                        Fig("${x.key} · ${x.models.size} models", style = Divan.type.figureSmall, color = c.textMuted)
                                        if (x.status == "quota_exhausted" && x.quotaResetAt != null) Text("ریست سهمیه ${until(x.quotaResetAt)}", style = Divan.type.micro, color = c.warning)
                                        x.statusReason?.let { Text(it, style = Divan.type.micro, color = c.textMuted) }
                                    }
                                    Pill(label, tone, dot = true)
                                }
                            }
                        }
                    }
                }
            }
        }
        item { com.coinepro.hq.ui.owner.WhatIfCard() }
        item { com.coinepro.hq.ui.owner.CallsCard() }
    }
    if (editBudgets) com.coinepro.hq.ui.owner.BudgetSheet { editBudgets = false }
    editConn?.let { x -> com.coinepro.hq.ui.owner.ConnectionSheet(x) { editConn = null } }
}

/** First day of the period in the owner's zone (ISO date), for breakdown queries. */
private fun periodStart(period: String): String {
    val today = com.coinepro.hq.core.format.HqClock.today()
    return (if (period == "day") today else today.withDayOfMonth(1)).toString()
}
