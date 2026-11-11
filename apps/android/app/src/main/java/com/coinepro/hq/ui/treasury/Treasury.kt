package com.coinepro.hq.ui.treasury

import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.width
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.sep
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
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
    val nav = com.coinepro.hq.ui.LocalNav.current
    val companies = rememberCompanies()
    var period by rememberSaveable { mutableStateOf("month") }
    val sum = rememberQuery("treasury:$period", "treasury") { treasury(period) }
    val byCo = rememberQuery("treasury:by:company:$period", "treasury") { breakdown("company", from = periodStart(period)) }
    val byModel = rememberQuery("treasury:by:model:$period", "treasury") { breakdown("model", from = periodStart(period)) }
    val month = rememberQuery("treasury:month", "treasury") { treasury("month") }
    val start = month.data?.periodStart?.let(::ownerDay)?.takeIf { it != "—" }
    val byDay = if (start != null) rememberQuery("treasury:by:day:$start", "treasury") { breakdown("day", from = start) } else null
    val conns = rememberQuery("connections", "treasury") { connections() }
    // ⟨1.33⟩ §55.3 the limits; read again every minute while the page is open.
    val limits = rememberQuery("treasury:limits", "treasury", maxAgeMs = 30_000) { gated(HubFeature.LIMITS) { limits() } }
    val onScreen = com.coinepro.hq.ui.rememberOnScreen()
    androidx.compose.runtime.LaunchedEffect(onScreen, limits.data != null) { while (onScreen && limits.data != null) { kotlinx.coroutines.delay(60_000); limits.refresh() } }
    // Every number says when it was read: the moment this page last got its summary.
    val readAt = remember(sum.data) { com.coinepro.hq.core.format.HqClock.now().toString() }
    val r = refresher(*listOfNotNull(sum, month, byCo, byModel, byDay, conns, limits).toTypedArray())
    val slot = { i: Int? -> if (i != null && i in 1..8) c.chart[i - 1] else c.silverInk }
    var editBudgets by rememberSaveable { mutableStateOf(false) }
    var editConn by remember { mutableStateOf<com.coinepro.hq.core.net.Connection?>(null) }

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("خزانه‌ی توکن")
        }
        // ⟨1.0.1⟩ C3.6, §55.3: the Claude accounts as rings and today's meter. A hub before it: nothing here, and the older quota card stays.
        limits.data?.let { l -> item(key = "limits") { com.coinepro.hq.ui.look.LimitsBlock(l) } }
        item { Segmented(listOf(SegOption("day", "امروز"), SegOption("month", "این ماه")), period, { period = it }, Modifier.fillMaxWidth()) }
        item {
            Loadable(sum, skeleton = { Skeleton(Modifier.fillMaxWidth().height(180.dp), radius = 14.dp) }) { s -> TreasuryHero(s, period, readAt) }
        }
        if (limits.data == null) item { com.coinepro.hq.ui.owner.QuotaCard() }
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
        // ⟨1.5⟩ §21.7: yesterday's waste, by category, with the fourteen days before.
        item { WasteCard() }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("شرکت‌ها", note = "رنگ هر شرکت ثابت است، نه بر اساس رتبه")
                Loadable(byCo) { rows ->
                    HBars(
                        rows.filter { com.coinepro.hq.core.format.isRealModel(it.key) }.sortedByDescending { it.equivCostUsd.toDoubleOrNull() ?: 0.0 }.map { row ->
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
                                com.coinepro.hq.designsystem.ModelName(row.key)
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
                                Fig((i + 1).toString(), style = Divan.type.figureSmall, color = c.textMuted)
                                Avatar(agentKindOf(x.actor), dept = deptOf(x.actor), size = 32.dp)
                                Column(Modifier.weight(1f)) {
                                    // ⟨1.0.1⟩ a role is read by its name («مدیر رشد تریدیار»), never by its code.
                                    Text(actorTitle(x.actor) { code -> companyOf(companies, code).nameFa }, style = Divan.type.small, color = c.textPrimary, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                                    Text(buildAnnotatedString { fig(x.calls.toString()); append(" فراخوانی") }, style = Divan.type.micro, color = c.textMuted)
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
                SectionTitle("اتصال‌ها", note = "کلیدها هرگز نمایش داده نمیشوند") {
                    // ⟨1.5⟩ §21.7: a new connection is made on the tools page, sealed on its body.
                    com.coinepro.hq.designsystem.HqButton("اتصال تازه", { nav.go("tools") }, size = com.coinepro.hq.designsystem.BtnSize.SM, variant = com.coinepro.hq.designsystem.BtnVariant.TEXT, icon = com.coinepro.hq.designsystem.generated.DivanIcon.ADD)
                }
                Loadable(conns) { list ->
                    Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        list.forEach { x ->
                            // ⟨1.5⟩ §21.7 adds pending_secret, verifying, ready and error.
                            val (label, tone) = CONNECTION_STATUS[x.status] ?: com.coinepro.hq.ui.v18.CONN[x.status]?.let { it.fa to it.tone } ?: (x.status to Tone.NEUTRAL)
                            HqCard(Modifier.fillMaxWidth().clickable { editConn = x }, color = c.tile, radius = 12.dp, padding = androidx.compose.foundation.layout.PaddingValues(12.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                    com.coinepro.hq.designsystem.ModelMark(x.defaultModel ?: x.models.firstOrNull(), provider = x.provider, size = 22.dp)
                                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                        Text(x.displayName, style = Divan.type.small.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold))
                                        androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                            Fig(x.key, style = Divan.type.figureSmall, color = c.textMuted)
                                            x.models.forEach { m -> com.coinepro.hq.designsystem.ModelName(m, size = 11.dp, style = Divan.type.figureSmall, color = c.textMuted) }
                                        }
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
        // ⟨1.5⟩ §21.7: ROI by company, department and employee.
        item { RoiCard() }
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


/** A role's code as the owner reads it: «مدیر فنی کوینه‌پرو FX», never «FX-TECH-MGR». */
internal fun actorTitle(code: String, company: (String) -> String): String {
    val parts = code.split('-')
    val co = parts.getOrElse(0) { "" }
    val a = parts.getOrElse(1) { "" }
    val b = parts.getOrElse(2) { "" }
    val name = company(co)
    val dept = com.coinepro.hq.core.format.DEPT_FA[a]
    return when {
        a == "CEO" -> "مدیرعامل $name"
        a == "ADV" -> "مشاور کل"
        a == "OVR" -> "ناظر کل"
        a == "SYS" -> "سیستم"
        a == "AST" || a == "PA" -> "دستیار"
        dept != null && b == "MGR" -> "مدیر $dept $name"
        dept != null && b.all { it.isDigit() } && b.isNotEmpty() -> "کارمند $dept $name"
        name.isNotBlank() && name != co -> "همکار $name"
        else -> "همکار"
    }
}

/**
 * ⟨1.0.1⟩ C3.6 the top of the period: the verdict sentence («تا آخر ماه میرسم یا نه», the month with its cap), one big number, the
 * three small numbers in one row, and when it was read. Figures are Latin tabular digits; none is cut (it shrinks to fit).
 */
@Composable
private fun TreasuryHero(s: com.coinepro.hq.core.net.TreasurySummary, period: String, readAt: String) {
    val c = Divan.colors
    val t = s.totals
    val budget = s.budgets.firstOrNull { it.scopeType == "holding" }?.takeIf { period == "month" }
    val verdict = budget?.let { com.coinepro.hq.core.data.monthVerdict(it.tokensUsed, it.tokenLimit) }
    HqCard(Modifier.fillMaxWidth().testTag("treasury-hero")) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            verdict?.let { (tone, fa) ->
                val ink = when (tone) { "pos" -> c.positive; "warn" -> c.warning; else -> c.negative }
                Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    com.coinepro.hq.designsystem.DIcon(if (tone == "pos") com.coinepro.hq.designsystem.generated.DivanIcon.SEAL else com.coinepro.hq.designsystem.generated.DivanIcon.URGENT, Modifier.padding(top = 3.dp), size = 16.dp, tint = ink)
                    Text(fa, style = Divan.type.small.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold), color = ink, modifier = Modifier.weight(1f))
                }
            }
            Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                com.coinepro.hq.designsystem.Amount(
                    tokens(budget?.tokensUsed ?: (t.inputTokens + t.outputTokens)), Modifier.weight(1f, fill = false),
                    style = Divan.type.figureL.copy(fontSize = 40.sp, lineHeight = 46.sp, fontWeight = androidx.compose.ui.text.font.FontWeight.Bold), color = c.textPrimary,
                )
                Text(
                    buildAnnotatedString {
                        when {
                            budget != null -> {
                                append("از "); fig(tokens(budget.tokenLimit)); append(" سقف ماه")
                                budget.pct?.let { p -> sep(); fig(pct(p), when { p >= 90 -> c.negative; p >= 70 -> c.warning; else -> null }, androidx.compose.ui.text.font.FontWeight.SemiBold) }
                            }
                            period == "month" -> append("توکن این ماه")
                            else -> append("توکن امروز، از نیمه‌شب تهران")
                        }
                    },
                    style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.padding(bottom = 8.dp),
                )
            }
            Row(Modifier.fillMaxWidth().height(androidx.compose.foundation.layout.IntrinsicSize.Min)) {
                SmallFigure("توکن ورودی و خروجی", tokens(t.inputTokens + t.outputTokens), Modifier.weight(1f))
                androidx.compose.foundation.layout.Box(Modifier.padding(horizontal = 10.dp).width(1.dp).fillMaxHeight().background(c.lineDivider))
                SmallFigure("هزینه‌ی معادل", usd(t.equivCostUsd), Modifier.weight(1f))
                androidx.compose.foundation.layout.Box(Modifier.padding(horizontal = 10.dp).width(1.dp).fillMaxHeight().background(c.lineDivider))
                SmallFigure("فراخوانی", String.format(java.util.Locale.US, "%,d", t.calls), Modifier.weight(1f))
            }
            Text(
                buildAnnotatedString {
                    append(if (period == "month") "از اول ماه" else "امروز"); sep()
                    append("خوانده‌شده در "); fig(com.coinepro.hq.core.format.jTime(readAt)); sep()
                    append("پرداخت واقعی: "); fig(usd(t.costUsd))
                },
                style = Divan.type.micro, color = c.textMuted,
            )
        }
    }
}

/** One small figure of the row under the big number: Latin tabular digits, never cut. */
@Composable
private fun SmallFigure(label: String, value: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        com.coinepro.hq.designsystem.Amount(value, style = Divan.type.figureM.copy(fontSize = 17.sp, lineHeight = 26.sp), color = c.textPrimary)
        Text(label, style = Divan.type.micro, color = c.textMuted, maxLines = 2)
    }
}
