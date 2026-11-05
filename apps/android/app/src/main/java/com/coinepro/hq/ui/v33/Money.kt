package com.coinepro.hq.ui.v33

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import com.coinepro.hq.core.data.COST_PER_FA
import com.coinepro.hq.core.data.PAY_SOURCE_KIND_FA
import com.coinepro.hq.core.data.PAY_SOURCE_STATE_FA
import com.coinepro.hq.core.data.PAY_STATUS_HINT_FA
import com.coinepro.hq.core.data.PAY_STATUS_ORDER
import com.coinepro.hq.core.data.moneyFigure
import com.coinepro.hq.core.data.payCounts
import com.coinepro.hq.core.data.payNetworkFa
import com.coinepro.hq.core.data.payStatusFa
import com.coinepro.hq.core.data.payStatusTone
import com.coinepro.hq.core.data.rateText
import com.coinepro.hq.core.data.reconcileLine
import com.coinepro.hq.core.data.reconcileProblems
import com.coinepro.hq.core.data.reconcileTotal
import com.coinepro.hq.core.data.payAddressOk
import com.coinepro.hq.core.data.shortHash
import com.coinepro.hq.core.data.signedFigure
import com.coinepro.hq.core.data.usdtText
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.PayReconcile
import com.coinepro.hq.core.net.PayRow
import com.coinepro.hq.core.net.PaySource
import com.coinepro.hq.core.net.PaySourceIn
import com.coinepro.hq.core.net.PayReadResult
import com.coinepro.hq.core.net.RevenueBoard
import com.coinepro.hq.core.net.StepUp
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Chevron
import com.coinepro.hq.designsystem.CountingText
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Seg
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StackedBar
import com.coinepro.hq.designsystem.StatRow
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.springIn
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served

// Contract §33.2, §33.3 ⟨1.15⟩ the company's «پول» tab, in three short views: the revenue board (computed by code from the payments), the
// payments with how well the company's own ledger and the public chain agree, and the places they are read from. The hub reads money; it
// never moves it, and a page never has a button that would.

@Composable
fun CompanyMoney(code: String, seg0: String = "revenue") {
    val has = served(HubFeature.MONEY)
    var seg by rememberSaveable { mutableStateOf(seg0) }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (!has) Empty("پول و درآمد با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.TREASURY)
        else {
            Segmented(listOf(SegOption("revenue", "درآمد"), SegOption("payments", "پرداخت‌ها"), SegOption("sources", "منبع‌ها")), seg, { seg = it }, Modifier.fillMaxWidth())
            when (seg) {
                "payments" -> PaymentsView(code)
                "sources" -> SourcesView(code)
                else -> RevenueView(code) { seg = "sources" }
            }
        }
    }
}

// ------------------------------------------------------------- revenue --
@Composable
private fun RevenueView(code: String, onSources: () -> Unit) {
    val q = rememberQuery("revenue-board:$code", "money", "payments", maxAgeMs = 60_000) { gated(HubFeature.MONEY) { revenueBoard(code) } }
    val b = q.data
    when {
        b == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
        b == null -> Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Skeleton(Modifier.fillMaxWidth().height(260.dp), radius = 16.dp)
            Skeleton(Modifier.fillMaxWidth().height(110.dp), radius = 16.dp)
        }
        b.months.isEmpty() -> Empty(
            "هنوز پرداختی خوانده نشده", icon = DivanIcon.TREASURY, body = "وقتی یک منبع پرداخت وصل شود و خوانده شود، درآمد و ریزش از همان ساخته میشود.",
            action = { HqButton("منبع‌ها", onSources, variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.NEXT) },
        )
        else -> RevenueBoardBody(b)
    }
}

/** The board: the month's revenue with its line and forecast, four numbers, who came and left, what the money cost, and who stays. */
@Composable
fun RevenueBoardBody(b: RevenueBoard, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val last = b.months.last()
    val prev = b.months.getOrNull(b.months.size - 2)
    val delta = prev?.takeIf { it.mrrUsdt > 0 }?.let { (last.mrrUsdt - it.mrrUsdt) / it.mrrUsdt * 100 }
    var cohortOpen by rememberSaveable { mutableStateOf(false) }
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        HqCard(Modifier.fillMaxWidth().springIn(0), tahrir = true) {
            Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text("درآمد ماهانه", style = Divan.type.caption, color = c.textMuted)
                    Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        CountingText(moneyFigure(last.mrrUsdt), Divan.type.figureL, color = c.textPrimary)
                        Text("USDT", Modifier.padding(bottom = 4.dp), style = Divan.type.figureSmall, color = c.textMuted)
                    }
                }
                if (delta != null) Pill(signedFigure(delta).let { "$it%" }, if (delta >= 0) Tone.POS else Tone.NEG, figure = true)
            }
            Box(Modifier.padding(top = 10.dp)) { MrrChart(b.months, b.forecast) }
            if (b.forecast.isNotEmpty()) Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Pill("پیش‌بینی", Tone.LAPIS, icon = DivanIcon.TIME)
                    Text("خط چین و سایه: بازه‌ی محتمل", style = Divan.type.micro, color = c.textMuted)
                }
                b.forecastBasisFa?.takeIf { it.isNotBlank() }?.let { Para(it, style = Divan.type.caption, color = c.textSecondary) }
            }
        }
        Column(Modifier.springIn(1), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            StatRow {
                StatTile("مشتری فعال", last.active.toString(), Modifier.weight(1f), sub = "${last.newCustomers} تازه، ${last.churned} رفته", count = true)
                StatTile("ریزش ماهانه", rateText(b.churnRate, 1), Modifier.weight(1f), sub = "مشتریِ رفته در ماه", tone = (b.churnRate ?: 0.0).let { if (it > 0.1) Tone.WARN else null })
            }
            StatRow {
                StatTile("ارزش هر مشتری", b.ltvUsdt?.let { moneyFigure(it) } ?: "—", Modifier.weight(1f), sub = if (b.ltvUsdt == null) "داده‌ی کافی نیست" else "USDT در کل عمرش", count = b.ltvUsdt != null)
                StatTile("هزینه‌ی جذب", b.cacUsdt?.let { moneyFigure(it) } ?: "—", Modifier.weight(1f), sub = b.paybackMonths?.let { "برگشت در ${moneyFigure(it)} ماه" } ?: "هنوز محاسبه نمیشود", count = b.cacUsdt != null)
            }
        }
        if (b.months.size >= 2) HqCard(Modifier.fillMaxWidth().springIn(2)) {
            SectionTitle("مشتری تازه و رفته", note = "سبز: تازه، قرمز: رفته؛ هر ماه")
            Box(Modifier.padding(top = 10.dp)) { FlowBars(b.months) }
        }
        b.roi?.let { roi ->
            HqCard(Modifier.fillMaxWidth().springIn(3)) {
                SectionTitle("خرج و درآمد", note = "هزینه‌ی هوش مصنوعی و تبلیغ در برابر پولی که آمد")
                Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    if (roi.ratio != null) Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        CountingText(String.format(java.util.Locale.US, "%.1f", roi.ratio), Divan.type.figureM, color = if (roi.ratio >= 1) c.positive else c.negative)
                        Text("برابر؛ به‌ازای هر ۱ دلار خرج، ${moneyFigure(roi.ratio)} دلار درآمد".let { plain(it) }, Modifier.padding(bottom = 3.dp), style = Divan.type.caption, color = c.textSecondary)
                    }
                    val cost = roi.costUsd
                    val parts = listOf(
                        Triple("توکن", cost.tokens, c.chart[0]), Triple("صدا", cost.voice, c.chart[1]), Triple("تبلیغ", cost.ads, c.chart[2]), Triple("سرور", cost.servers, c.chart[3]),
                    ).filter { (it.second ?: 0.0) > 0.0 }
                    if (parts.isNotEmpty()) StackedBar(parts.map { (n, v, col) -> Seg(n, n, v ?: 0.0, col, "$" + moneyFigure(v ?: 0.0)) }, "هزینه به تفکیک")
                    if (b.costPerOutput.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        HorizontalDivider(color = c.lineDivider)
                        for (x in b.costPerOutput) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(COST_PER_FA[x.kind] ?: x.kind, style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
                            Text(plain("${x.count} بار"), style = Divan.type.micro, color = c.textMuted)
                            Fig("$" + String.format(java.util.Locale.US, "%.2f", x.usdEach), style = Divan.type.figure, color = c.textPrimary)
                        }
                    }
                }
            }
        }
        if (b.cohorts.isNotEmpty()) HqCard(Modifier.fillMaxWidth().springIn(4), onClick = { cohortOpen = !cohortOpen }) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(Modifier.weight(1f)) { SectionTitle("چه کسانی میمانند", note = "مشتری‌ها به تفکیک ماهی که آمدند") }
                Chevron(cohortOpen, tint = c.textMuted)
            }
            Expand(cohortOpen) { Box(Modifier.padding(top = 12.dp)) { CohortGrid(b.cohorts) } }
        }
    }
}

// ------------------------------------------------------------ payments --
/** Payments, newest first, in pages of [com.coinepro.hq.core.net.Api.MAX_PAGE]: a status chip asks the hub for that status only. */
@Composable
private fun PaymentsView(code: String) {
    val env = LocalEnv.current
    val more = rememberAction()
    var filter by rememberSaveable { mutableStateOf<String?>(null) }
    var days by rememberSaveable { mutableStateOf(7) }
    val today = com.coinepro.hq.core.format.HqClock.today()
    val from = today.minusDays(days - 1L).toString()
    val rec = rememberQuery("reconcile:$code:$days:$from", "money", "payments", maxAgeMs = 60_000) { gated(HubFeature.MONEY) { reconcile(code, from, today.toString()) } }
    val first = rememberQuery("payments:$code:${filter ?: "all"}", "money", "payments", maxAgeMs = 30_000) { gated(HubFeature.MONEY) { payments(code, status = filter) } }
    // Pages after the first, kept while this filter stays; a refresh of the first page starts over.
    val extra = androidx.compose.runtime.remember(code, filter, first.data) { androidx.compose.runtime.mutableStateListOf<PayRow>() }
    var cursor by androidx.compose.runtime.remember(code, filter, first.data) { mutableStateOf(first.data?.nextCursor) }
    val rows = first.data?.items.orEmpty() + extra
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        ReconcileCard(rec.data.orEmpty(), days) { days = it }
        ScrollRow {
            FilterChip("همه", filter == null, { filter = null })
            for (s in PAY_STATUS_ORDER) FilterChip(payStatusFa(s), filter == s, { filter = if (filter == s) null else s })
        }
        filter?.let { f -> PAY_STATUS_HINT_FA[f]?.let { Para(it, style = Divan.type.caption, color = Divan.colors.textMuted) } }
        when {
            first.data == null && first.error != null -> ErrorBlock(first.error, { first.refresh() })
            first.data == null -> Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = 16.dp)
            rows.isEmpty() -> Empty(
                if (filter == null) "هنوز پرداختی خوانده نشده" else "پرداختی با این وضعیت نیست", icon = DivanIcon.TREASURY,
                body = if (filter == null) "بعد از وصل شدن منبع‌ها و اولین خواندن، پرداخت‌ها این‌جا میایند." else null,
            )
            else -> {
                HqCard(Modifier.fillMaxWidth(), padding = androidx.compose.foundation.layout.PaddingValues(horizontal = 12.dp, vertical = 6.dp)) {
                    rows.forEachIndexed { i, r ->
                        if (i > 0) HorizontalDivider(color = Divan.colors.lineDivider)
                        androidx.compose.runtime.key(r.id) { PaymentRow(r) }
                    }
                }
                cursor?.let { cur ->
                    HqButton("پرداخت‌های قدیمی‌تر", {
                        more.run {
                            val p = env.api.payments(code, status = filter, cursor = cur)
                            extra += p.items
                            cursor = p.nextCursor
                        }
                    }, Modifier.fillMaxWidth(), variant = BtnVariant.SILVER, icon = DivanIcon.NEXT, loading = more.busy)
                }
            }
        }
    }
}

/** The days of the chosen window, one line each: how many of the day's payments the company's ledger and the chain agree on. */
@Composable
private fun ReconcileCard(list: List<PayReconcile>, days: Int, onDays: (Int) -> Unit) {
    val c = Divan.colors
    val shown = list.filter { reconcileLine(it) != null }.sortedByDescending { it.day }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("تطبیق روزانه", note = "دفتر خود شرکت در برابر زنجیره‌ی عمومی", icon = DivanIcon.SCOPE)
        ScrollRow(Modifier.padding(top = 10.dp)) {
            for ((d, l) in listOf(7 to "7 روز", 30 to "30 روز", 90 to "90 روز")) FilterChip(l, days == d, { onDays(d) }, figure = true)
        }
        if (shown.isEmpty()) Text("در این روزها پرداختی نبود.", Modifier.padding(top = 10.dp), style = Divan.type.caption, color = c.textMuted)
        else {
            val problems = shown.sumOf { reconcileProblems(it) }
            Text(
                plain("${shown.sumOf { it.matched }} پرداخت تطبیق شد" + if (problems > 0) "؛ $problems مورد نیاز به بررسی دارد" else "؛ همه درست"),
                Modifier.padding(top = 10.dp), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = if (problems > 0) c.warning else c.positive,
            )
            Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                for (r in shown.take(14)) ReconcileDay(r)
            }
        }
    }
}

@Composable
private fun ReconcileDay(r: PayReconcile) {
    val c = Divan.colors
    val problems = reconcileProblems(r)
    val total = reconcileTotal(r).coerceAtLeast(1)
    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(plain(jDate(r.day)), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
            Text(plain(reconcileLine(r).orEmpty()), style = Divan.type.caption, color = if (problems > 0) c.warning else c.textMuted)
        }
        MeterBar(r.matched * 100.0 / total, tone = if (problems > 0) BarTone.WARN else BarTone.POS, height = 5.dp)
        if (problems > 0 || r.pendingChain > 0) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            if (r.ledgerOnly > 0) Pill("${r.ledgerOnly} بی‌پول", Tone.NEG, figure = true)
            if (r.chainOnly > 0) Pill("${r.chainOnly} بی‌مشتری", Tone.WARN, figure = true)
            if (r.amountMismatch > 0) Pill("${r.amountMismatch} مبلغ کم", Tone.WARN, figure = true)
            if (r.pendingChain > 0) Pill("${r.pendingChain} در انتظار زنجیره", Tone.LAPIS, figure = true)
        }
        if (r.noteFa.isNotBlank()) Para(r.noteFa, style = Divan.type.micro, color = c.textMuted)
    }
}

/** A payment: the customer's pseudonym and plan, the amount, the date and how it reconciled; a tap opens the transaction and the period. */
@Composable
fun PaymentRow(r: PayRow) {
    val c = Divan.colors
    var open by rememberSaveable(r.id) { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).clickable(role = Role.Button, onClickLabel = "جزئیات") { open = !open }.padding(vertical = 10.dp, horizontal = 4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                if (r.customer.isNullOrBlank()) Text("بدون مشتری در دفتر", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                else Fig(r.customer, style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    r.plan?.takeIf { it.isNotBlank() }?.let { Text(plain(it), style = Divan.type.micro, color = c.textSecondary, maxLines = 1) }
                    payNetworkFa(r.network)?.let { Text(it, style = Divan.type.micro, color = c.textMuted) }
                    Text(plain(jDate(r.paidAt)), style = Divan.type.micro, color = c.textMuted)
                }
            }
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                val amount = r.amountUsdt ?: r.chainAmount
                if (amount != null) Fig(usdtText(amount), style = Divan.type.figure, color = c.textPrimary)
                else Text("پرداخت درون‌برنامه‌ای", style = Divan.type.micro, color = c.textMuted)
                Pill(payStatusFa(r.status), payStatusTone(r.status), dot = true)
            }
        }
        Expand(open) {
            Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Para(r.noteFa?.takeIf { it.isNotBlank() } ?: PAY_STATUS_HINT_FA[r.status].orEmpty(), style = Divan.type.caption, color = c.textSecondary)
                if (r.chainAmount != null && r.amountUsdt != null && r.chainAmount != r.amountUsdt) Text(plain("روی زنجیره: ${usdtText(r.chainAmount)}"), style = Divan.type.micro, color = c.warning)
                if (!r.txHash.isNullOrBlank()) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("تراکنش", style = Divan.type.micro, color = c.textMuted)
                    Fig(shortHash(r.txHash), style = Divan.type.figureSmall, color = c.textSecondary)
                }
                if (r.periodStart != null && r.periodEnd != null) Text(plain("دوره: ${jDate(r.periodStart)} تا ${jDate(r.periodEnd)}"), style = Divan.type.micro, color = c.textMuted)
                r.checkedAt?.let { Text(plain("آخرین بررسی ${ago(it)}"), style = Divan.type.micro, color = c.textMuted) }
            }
        }
    }
}

// ------------------------------------------------------------- sources --
@Composable
private fun SourcesView(code: String) {
    val q = rememberQuery("payment-sources:$code", "money", maxAgeMs = 30_000) { gated(HubFeature.MONEY) { paymentSources(code) } }
    var editing by rememberSaveable { mutableStateOf<String?>(null) }
    val list = q.data
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionTitle("جای خواندن پرداخت", note = "دفتر خود شرکت و زنجیره‌ی عمومی؛ فقط خوانده میشود، پولی جابه‌جا نمیشود") {
            HqButton("منبع تازه", { editing = "new" }, variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        when {
            list == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            list == null -> Skeleton(Modifier.fillMaxWidth().height(150.dp), radius = 16.dp)
            list.isEmpty() -> Empty("هنوز منبعی وصل نیست", icon = DivanIcon.SERVER, body = "دفتر شرکت از راه سرور خودش خوانده میشود و زنجیره از نشانی عمومی کیف پول.")
            else -> list.forEachIndexed { i, s -> Box(Modifier.springIn(i)) { SourceCard(s) { editing = s.id } } }
        }
    }
    editing?.let { id ->
        val src = list?.firstOrNull { it.id == id }
        com.coinepro.hq.ui.v14.HqSheet({ editing = null }, if (src == null) "منبع پرداخت تازه" else "تغییر منبع", sub = "با اثر انگشت یا رمز تو مُهر میشود.") {
            SourceForm(code, src) { editing = null }
        }
    }
}

@Composable
private fun SourceCard(s: PaySource, onEdit: () -> Unit) {
    val c = Divan.colors
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val read = rememberAction()
    // One key per press: a retry after a lost answer is the same read, never a second one.
    var key by androidx.compose.runtime.remember(s.id) { mutableStateOf(java.util.UUID.randomUUID().toString()) }
    val st = PAY_SOURCE_STATE_FA[s.state] ?: (s.state to Tone.SILVER)
    HqCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.size(36.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) {
                DIcon(if (s.kind == "chain") DivanIcon.GLOBE else DivanIcon.SERVER, size = 18.dp, tint = c.goldInk)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(PAY_SOURCE_KIND_FA[s.kind] ?: s.kind, style = Divan.type.bodyStrong)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    payNetworkFa(s.network)?.let { Pill(it, Tone.SILVER) }
                    s.server?.takeIf { it.isNotBlank() }?.let { Text(plain("سرور $it"), style = Divan.type.micro, color = c.textMuted) }
                    if (!s.enabled) Pill("خاموش", Tone.SILVER)
                }
            }
            Pill(st.first, st.second, dot = true)
        }
        s.address?.takeIf { it.isNotBlank() }?.let {
            Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("نشانی عمومی", style = Divan.type.micro, color = c.textMuted)
                Fig(shortHash(it), style = Divan.type.figureSmall, color = c.textSecondary)
            }
        }
        Text(plain(if (s.lastReadAt == null) "هنوز خوانده نشده" else "آخرین خواندن ${ago(s.lastReadAt)}"), Modifier.padding(top = 6.dp), style = Divan.type.caption, color = c.textMuted)
        s.lastErrorFa?.takeIf { it.isNotBlank() }?.let { Para(it, Modifier.padding(top = 4.dp), style = Divan.type.caption, color = c.warning) }
        Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("همین حالا بخوان", {
                read.run {
                    val r = env.api.readPaymentSource(s.id, key)
                    key = java.util.UUID.randomUUID().toString()
                    env.cache.invalidate("money", "payments")
                    toasts.ok(readResultFa(r))
                }
            }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.REFRESH, loading = read.busy, enabled = s.enabled)
            HqButton("تغییر", onEdit, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.EDIT)
        }
    }
}

/** What a read did, in one line. */
fun readResultFa(r: PayReadResult): String = when {
    r.source.kind == "ledger" && r.queued -> "خواندن دفتر به سرور شرکت سپرده شد؛ چند دقیقه‌ی دیگر میرسد."
    r.source.kind == "ledger" -> "دفتر خوانده شد: ${r.payments} پرداخت."
    else -> "زنجیره خوانده شد: ${r.transfers} انتقال."
}

/**
 * A source added or changed (🔏 `payment.source`, on the exact body). A ledger names at most the company server whose runner reads it; a
 * chain names a network and a public address. A source already there is changed by sending the same kind (and address) again: here only
 * its server and whether it is on.
 */
@Composable
fun SourceForm(code: String, src: PaySource?, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val save = rememberAction()
    val key = src?.id
    var kind by rememberSaveable(key) { mutableStateOf(src?.kind ?: "chain") }
    var server by rememberSaveable(key) { mutableStateOf(src?.server) }
    var network by rememberSaveable(key) { mutableStateOf(src?.network ?: "bsc_usdt") }
    var address by rememberSaveable(key) { mutableStateOf(src?.address.orEmpty()) }
    var enabled by rememberSaveable(key) { mutableStateOf(src?.enabled ?: true) }
    val servers = rememberQuery("servers:$code", "servers", maxAgeMs = 60_000) { servers(code) }
    val valid = if (kind == "chain") payAddressOk(network, address.trim()) else true
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (src == null) {
            Text("از کجا بخوانم", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                for ((k, l) in PAY_SOURCE_KIND_FA) FilterChip(l, kind == k, { kind = k })
            }
        }
        if (kind == "ledger") {
            Text("سرور شرکت", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                FilterChip("هر سرور وصل‌شده", server == null, { server = null })
                for (sv in servers.data.orEmpty().filter { it.origin == "attached" }) FilterChip(sv.name, server == sv.name, { server = sv.name }, figure = true)
            }
            Para("دفتر را سرور خود شرکت میخواند و فقط نتیجه‌ی خلاصه به هاب میاید؛ مشتری‌ها با نام مستعار. سرور شرکت باید از قبل وصل شده باشد.", style = Divan.type.caption, color = c.textMuted)
        } else if (src == null) {
            Text("شبکه", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                FilterChip("BSC (BEP20)", network == "bsc_usdt", { network = "bsc_usdt" }, figure = true)
                FilterChip("TRON (TRC20)", network == "trc20_usdt", { network = "trc20_usdt" }, figure = true)
            }
            Text("نشانی عمومی کیف پول شرکت", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            HqTextField(address, { address = it.trim() }, if (network == "bsc_usdt") "0x…" else "T…", Modifier.fillMaxWidth(), figure = true, maxLength = 80)
            if (address.isNotBlank() && !valid) Text("این نشانی برای این شبکه درست نیست.", style = Divan.type.caption, color = c.warning)
            Para("فقط نشانی عمومی. کلید خصوصی هرگز این‌جا نمیاید و هاب هیچ پولی جابه‌جا نمیکند.", style = Divan.type.caption, color = c.textMuted)
        } else {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                payNetworkFa(network)?.let { Pill(it, Tone.SILVER) }
                Fig(shortHash(address), style = Divan.type.figureSmall, color = c.textSecondary)
            }
            Para("برای نشانی دیگر، یک منبع تازه بساز.", style = Divan.type.caption, color = c.textMuted)
        }
        HqSwitch(enabled, { enabled = it }, "خوانده شود")
        HqButton(if (src == null) "اضافه کن" else "ذخیره", {
            save.run {
                val body = if (kind == "chain") PaySourceIn(kind = "chain", network = network, address = address.trim(), enabled = enabled)
                else PaySourceIn(kind = "ledger", server = server, enabled = enabled)
                val sign: StepUp = { a, t -> env.auth.stepUp(act, a, t) }
                env.api.savePaymentSource(code, body, sign)
                env.cache.invalidate("money", "payments")
                toasts.ok("منبع ذخیره شد.")
                onDone()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, enabled = valid, loading = save.busy)
    }
}
