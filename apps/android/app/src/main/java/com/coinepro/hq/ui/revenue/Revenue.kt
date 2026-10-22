package com.coinepro.hq.ui.revenue

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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.RescueCase
import com.coinepro.hq.core.net.RevenueAccount
import com.coinepro.hq.core.net.RevenueAccountIn
import com.coinepro.hq.core.net.RevenueAlert
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.ChartLine
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.LinesChart
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.Label
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.ALERT_FA
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.CompanyChips
import com.coinepro.hq.ui.v16.Fact
import com.coinepro.hq.ui.v16.FactRows
import com.coinepro.hq.ui.v16.Labelled
import com.coinepro.hq.ui.v16.Notice
import com.coinepro.hq.ui.v16.RESCUE_STATE
import com.coinepro.hq.ui.v16.RESCUE_STEP
import com.coinepro.hq.ui.v16.TerminalCommand
import com.coinepro.hq.ui.v16.compact
import com.coinepro.hq.ui.v16.companyColor
import com.coinepro.hq.ui.v16.go
import com.coinepro.hq.ui.v16.money
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v16.rate
import java.time.LocalDate
import java.util.Locale
import java.util.UUID
import kotlin.math.abs

private val PERIOD_FA = mapOf("day" to "دیروز", "week" to "۷ روز", "month" to "۳۰ روز")
private val ACCOUNT_STATE = mapOf("ok" to Label("سالم", Tone.POS), "error" to Label("خطا", Tone.NEG), "not_configured" to Label("بی‌کلید", Tone.NEUTRAL))

private fun shift(day: String, n: Long): String = runCatching { LocalDate.parse(day).plusDays(n).toString() }.getOrDefault(day)

/** درآمد (contract §19.1–§19.2): referral commission every day after the exchange settles, against what the tokens cost; the
 *  funnel and referral rescue. USDT is read as dollars (≈), which the page says. The holding earns nothing itself, so the page
 *  is the whole holding; the funnel picks one company. */
@Composable
fun RevenueScreen() {
    val c = Divan.colors
    val companies = rememberCompanies()
    var period by rememberSaveable { mutableStateOf("month") }
    val sum = rememberQuery("revenue:summary:$period", "revenue", maxAgeMs = 60_000) { revenueSummary(period) }
    // The previous period's numbers stay on screen until the new ones arrive (the web's keepPreviousData).
    var shown by remember { mutableStateOf<com.coinepro.hq.core.net.RevenueSummary?>(null) }
    LaunchedEffect(sum.data) { sum.data?.let { shown = it } }
    val s = sum.data ?: shown
    // The 30-day trend ends on the summary's last settled day; it waits for the summary so it is fetched once.
    val to = s?.to
    val from = to?.let { shift(it, -29) }
    val days = if (from != null && to != null) rememberQuery("revenue:days:$from:$to", "revenue") { revenueDays(from, to) } else null
    val r = refresher(*listOfNotNull(sum, days).toTypedArray())
    val d = days?.data
    val keys = remember(from) { if (from == null) emptyList() else (0L until 30L).map { shift(from, it) } }
    val total = s?.totalUsdt?.toDoubleOrNull()
    val prev = s?.prevTotalUsdt?.toDoubleOrNull()
    val change = if (total != null && prev != null && prev != 0.0) (total - prev) / prev * 100 else null
    val cost = s?.byCompany?.sumOf { it.tokenCostUsd.toDoubleOrNull() ?: 0.0 }
    val net = s?.byCompany?.sumOf { it.netUsd.toDoubleOrNull() ?: 0.0 }
    val invitees = if (s != null && d != null) d.filter { it.day >= s.from && it.day <= s.to }.sumOf { it.newInvitees } else null
    val incomplete = d?.count { !it.complete } ?: 0

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("درآمد", eyebrow = "کمیسیون رفرال صرافی‌ها، هر روز بعد از تسویه") }
        item {
            Text(
                prose("درآمد به USDT است و این‌جا هم‌ارز دلار خوانده میشود (USDT ≈ USD). هزینه‌ی توکن از خزانه میاید، نه از گزارش ایجنت. pull کار کد است و کلید صرافی هرگز از egress بیرون نمیرود."),
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        item { Segmented(listOf(SegOption("day", "روز"), SegOption("week", "هفته"), SegOption("month", "ماه")), period, { period = it }, Modifier.fillMaxWidth()) }
        if (s == null && sum.error != null) item { ErrorBlock(sum.error, { sum.refresh() }) }
        item {
            if (s == null) Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                repeat(2) { Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) { repeat(2) { Skeleton(Modifier.weight(1f).height(104.dp), radius = 14.dp) } } }
            } else Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatTile("درآمد ${PERIOD_FA[period]} (USDT)", money(s.totalUsdt), Modifier.weight(1f), subRich = buildAnnotatedString {
                        if (change == null) append("دوره‌ی قبل داده ندارد")
                        else {
                            fig((if (change >= 0) "+" else "−") + String.format(Locale.US, "%.1f%%", abs(change)), if (change >= 0) c.positive else c.negative, FontWeight.SemiBold)
                            append(" نسبت به دوره‌ی قبل")
                        }
                    })
                    StatTile("هزینه‌ی توکن", usd(cost), Modifier.weight(1f), sub = "از خزانه‌ی توکن")
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatTile("خالص", usd(net), Modifier.weight(1f), sub = "درآمد منهای توکن", tone = if (net != null && net < 0) Tone.NEG else null)
                    StatTile("دعوت‌شده‌ی تازه", invitees?.toString() ?: "—", Modifier.weight(1f), sub = "از داده‌ی افیلیت")
                }
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("روند ۳۰ روز", note = "کمیسیون روزانه‌ی هر شرکت به USDT؛ روز بی‌داده خالی میماند" + if (incomplete > 0) "، $incomplete روز هنوز ناقص" else "")
                Box(Modifier.padding(top = 12.dp)) {
                    when {
                        d == null && days?.error != null -> ErrorBlock(days.error, { days.refresh() })
                        d == null -> Skeleton(Modifier.fillMaxWidth().height(260.dp), radius = 12.dp)
                        else -> {
                            val cos = (s?.byCompany.orEmpty().map { it.company } + d.map { it.company }).distinct()
                            val lines = cos.map { co ->
                                val mine = d.filter { it.company == co }
                                ChartLine(
                                    co, companyOf(companies, co).nameFa, companyColor(co),
                                    keys.map { k -> mine.filter { it.day == k }.takeIf { it.isNotEmpty() }?.sumOf { it.commissionUsdt.toDoubleOrNull() ?: 0.0 } },
                                    mark = { CompanyMark(co, height = 11.dp, mono = true, ink = c.textSecondary) },
                                )
                            }
                            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                LinesChart(keys.map { jDate(it) }, lines, fmt = ::money, label = "کمیسیون روزانه‌ی هر شرکت", tick = ::compact)
                                DayTable(keys, lines)
                            }
                        }
                    }
                }
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("شرکت‌ها", note = "${PERIOD_FA[period]}؛ رنگ هر شرکت ثابت است، نه بر اساس رتبه")
                if (s == null) Skeleton(Modifier.fillMaxWidth().padding(top = 12.dp).height(140.dp))
                else Column(Modifier.padding(top = 4.dp)) {
                    s.byCompany.forEach { x ->
                        HorizontalDivider(Modifier.padding(vertical = 10.dp), color = c.lineDivider)
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                CompanyMark(x.company, height = 14.dp, mono = true, ink = c.textSecondary)
                                Text(companyOf(companies, x.company).nameFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                            }
                            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                Figure("درآمد (USDT)", money(x.usdt), Modifier.weight(1f), strong = true)
                                Figure("هزینه‌ی توکن", usd(x.tokenCostUsd), Modifier.weight(1f))
                                val n = x.netUsd.toDoubleOrNull() ?: 0.0
                                Figure("خالص", usd(x.netUsd), Modifier.weight(1f), strong = true, negative = n < 0)
                            }
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                MeterBar((x.share * 100).coerceAtLeast(1.5), Modifier.weight(1f), height = 8.dp, color = companyColor(x.company))
                                Fig(rate(x.share), Modifier.width(40.dp), style = Divan.type.figureSmall, color = c.textSecondary)
                            }
                        }
                    }
                }
            }
        }
        item { FunnelCard() }
        item { AlertsCard(s?.alerts) }
        item { AccountsCard() }
        item { RescueCard() }
    }
}

@Composable
private fun Figure(label: String, value: String, modifier: Modifier, strong: Boolean = false, negative: Boolean = false) {
    val c = Divan.colors
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Fig(value, style = Divan.type.figure.copy(fontWeight = if (strong) FontWeight.SemiBold else FontWeight.Normal), color = if (negative) c.negative else if (strong) c.textPrimary else c.textSecondary)
    }
}

/** The chart's numbers as a table, newest day first: what a screen reader and a careful owner read. */
@Composable
private fun DayTable(keys: List<String>, lines: List<ChartLine>) {
    val c = Divan.colors
    var open by rememberSaveable { mutableStateOf(false) }
    Column {
        Row(
            Modifier.clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button) { open = !open }.padding(vertical = 4.dp, horizontal = 2.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            DIcon(DivanIcon.CHEVRON, size = 14.dp, tint = c.textSecondary, modifier = Modifier.graphicsLayer { rotationZ = if (open) 180f else 0f })
            Text(if (open) "بستن جدول روزها" else "جدول روزها", style = Divan.type.caption, color = c.textSecondary)
        }
        if (open) Column(Modifier.padding(top = 6.dp)) {
            Row(Modifier.padding(vertical = 4.dp)) {
                Text("روز", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1.1f))
                for (l in lines) Text(l.label, style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            for (i in keys.indices.reversed()) {
                HorizontalDivider(color = c.lineDivider)
                Row(Modifier.padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(jDate(keys[i]), style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1.1f))
                    for (l in lines) Fig(l.values[i]?.let(::money) ?: "—", Modifier.weight(1f), style = Divan.type.figureSmall, color = c.textPrimary)
                }
            }
        }
    }
}

// ------------------------------------------------------------------ alerts --
/** One per incident (§19.1): a drop below 60% of the weekday median, two failed pulls in a row, a day still incomplete after 36 h. */
@Composable
private fun AlertsCard(alerts: List<RevenueAlert>?) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("هشدارها", note = "یکی برای هر رخداد؛ به مدیرعامل همان شرکت هم میرسد")
        Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            when {
                alerts == null -> Skeleton(Modifier.fillMaxWidth().height(80.dp))
                alerts.isEmpty() -> Text("هشداری نیست.", style = Divan.type.small, color = c.textMuted, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp))
                else -> for (a in alerts) {
                    val drop = a.kind == "drop"
                    val (fa, icon) = ALERT_FA[a.kind] ?: (a.kind to DivanIcon.URGENT)
                    Notice(icon, if (drop) c.softWarning else c.softNegative, if (drop) c.warning else c.negative) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            CompanyMark(a.company, height = 12.dp, mono = true, ink = c.textPrimary)
                            Text(prose(fa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                        }
                        Text(prose(a.noteFa), style = Divan.type.small, color = c.textPrimary)
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------- accounts --
/** The affiliate accounts (§19.1): a mapping to a service account; the key and secret are set in the owner's terminal, never here. */
@Composable
private fun AccountsCard() {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val q = rememberQuery("revenue:accounts", "revenue") { revenueAccounts() }
    val action = rememberAction()
    // One Idempotency-Key per press: only a lost answer is retried with the same key; anything the hub answered starts afresh.
    val keys = remember { mutableMapOf<String, String>() }
    var pulling by remember { mutableStateOf<String?>(null) }
    var edit by remember { mutableStateOf<RevenueAccount?>(null) }
    var neu by remember { mutableStateOf(false) }
    fun pull(a: RevenueAccount) {
        val key = keys.getOrPut(a.id) { UUID.randomUUID().toString() }
        pulling = a.id
        action.go(toasts, onError = { e -> if (!e.isOffline) keys.remove(a.id); pulling = null; false }) {
            env.api.pullRevenue(a.id, key)
            keys.remove(a.id)
            pulling = null
            env.cache.invalidate("revenue")
            toasts.ok("pull در صف رفت؛ روز تازه که برسد، رادار به‌روز میشود.")
        }
    }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("حساب‌های افیلیت", note = "هر روز بعد از تسویه‌ی صرافی، خودکار") {
            HqButton("حساب تازه", { neu = true }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            val list = q.data
            when {
                list == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
                list == null -> Skeleton(Modifier.fillMaxWidth().height(120.dp))
                list.isEmpty() -> Text("حسابی ثبت نشده.", style = Divan.type.small, color = c.textMuted)
                else -> for (a in list) Column(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        CompanyMark(a.company, height = 14.dp, mono = true, ink = c.textSecondary)
                        Text(prose(a.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        LabelPill(ACCOUNT_STATE[a.status], a.status)
                    }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Fig("${a.exchange} · ${a.adapter}", style = Divan.type.figureSmall, color = c.textMuted)
                        Text(if (a.lastPullAt != null) "آخرین pull ${ago(a.lastPullAt)}" else "هنوز pull نشده", style = Divan.type.micro, color = c.textMuted)
                    }
                    a.lastError?.let { err ->
                        Text(
                            err, style = Divan.type.figureSmall.copy(textDirection = TextDirection.Ltr, lineHeight = 16.sp), color = c.negative,
                            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(c.softNegative).padding(horizontal = 10.dp, vertical = 6.dp),
                        )
                    }
                    if (a.status == "not_configured") TerminalCommand("make account-secret KEY=${a.serviceAccount}")
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        HqButton("pull الان", { pull(a) }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.REFRESH, loading = pulling == a.id, enabled = a.status != "not_configured")
                        HqButton("تغییر", { edit = a }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.EDIT)
                    }
                }
            }
        }
    }
    if (neu || edit != null) AccountSheet(edit) { neu = false; edit = null }
}

@Composable
private fun AccountSheet(account: RevenueAccount?, onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    val services = rememberQuery("tools:accounts", "tools", maxAgeMs = 120_000) { serviceAccounts() }
    var company by rememberSaveable { mutableStateOf(account?.company) }
    var exchange by rememberSaveable { mutableStateOf(account?.exchange ?: "lbank") }
    var adapter by rememberSaveable { mutableStateOf(account?.adapter ?: "lbank-affiliate-v2") }
    var service by rememberSaveable { mutableStateOf(account?.serviceAccount ?: "") }
    var title by rememberSaveable { mutableStateOf(account?.titleFa ?: "") }
    val valid = company != null && Regex("^[a-z0-9_-]+$").matches(exchange) && Regex("^[a-z0-9_.-]+$").matches(adapter) &&
        Regex("^[a-z0-9_.-]+$").matches(service) && title.trim().length >= 2
    HqSheet(onClose, if (account != null) "تغییر حساب افیلیت" else "حساب افیلیت تازه", sub = "یک حساب برای هر صرافی و هر شرکت؛ ثبت با passkey و روی همین متن.") {
        Labelled("شرکت") { CompanyChips(company, { company = it }, all = false) }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Labelled("صرافی", Modifier.weight(1f)) { HqTextField(exchange, { exchange = it.trim().lowercase() }, "lbank", Modifier.fillMaxWidth(), maxLength = 40, figure = true) }
            Labelled("adapter", Modifier.weight(1.4f)) { HqTextField(adapter, { adapter = it.trim() }, "lbank-affiliate-v2", Modifier.fillMaxWidth(), maxLength = 60, figure = true) }
        }
        Labelled("حساب سرویس (§18.13)") {
            HqTextField(service, { service = it.trim() }, "lbank-affiliate-ty", Modifier.fillMaxWidth(), maxLength = 80, figure = true)
            services.data?.takeIf { it.isNotEmpty() }?.let { list ->
                ChipRow { for (x in list) FilterChip(x.key, service == x.key, { service = x.key }) }
            }
        }
        Labelled("نام") { HqTextField(title, { title = it }, "افیلیت LBank تریدیار", Modifier.fillMaxWidth(), maxLength = 120) }
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DIcon(DivanIcon.LOCK, size = 16.dp, tint = c.goldInk)
                Text("کلید این‌جا پرسیده نمیشود", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
            }
            Text(prose("کلید و secret صرافی هرگز از API و این صفحه رد نمیشود؛ فقط در egress خوانده میشود. بعد از ثبت، در ترمینال خودت روی سرور:"), style = Divan.type.caption, color = c.textSecondary)
            TerminalCommand("make account-secret KEY=${service.ifBlank { "<service-account>" }}")
            Text(prose("و IP عمومی هاب را در whitelist API افیلیت همان صرافی بگذار؛ بدون آن صرافی جواب نمیدهد."), style = Divan.type.caption, color = c.textMuted)
        }
        HqButton("ثبت با passkey", {
            val co = company ?: return@HqButton
            action.go(toasts) {
                env.api.saveRevenueAccount(RevenueAccountIn(co, exchange, adapter, service, title.trim())) { a, t -> env.auth.stepUp(act, a, t) }
                env.cache.invalidate("revenue")
                toasts.ok(if (account != null) "حساب به‌روز شد." else "حساب ثبت شد؛ حالا کلیدش را در ترمینال خودت بگذار.")
                onClose()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = valid, loading = action.busy)
    }
}

// ------------------------------------------------------------------ funnel --
private val WAITING = mapOf("visit" to "منتظر منبع analytics", "signup" to "منتظر رویداد محصول (CR-009/010)", "vip_active" to "منتظر رویداد محصول (CR-009/010)")
private val SOURCE_FA = mapOf("affiliate" to "داده‌ی افیلیت", "product_events" to "رویداد محصول", "support" to "پشتیبانی", "analytics" to "analytics")

/** The funnel of one company (§19.2). A stage without a source says so and shows no number; a rate is never estimated. */
@Composable
private fun FunnelCard() {
    val c = Divan.colors
    val operating = rememberCompanies().filter { it.kind != "holding" }
    var picked by rememberSaveable { mutableStateOf<String?>(null) }
    val company = picked ?: operating.firstOrNull()?.code
    var period by rememberSaveable { mutableStateOf("month") }
    val q = company?.let { co -> rememberQuery("growth:funnel:$co:$period", "growth") { funnel(co, period) } }
    val f = q?.data
    val color = company?.let { companyColor(it) } ?: c.silverInk
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("قیف", note = "بازدید ← ثبت‌نام ← رفرال تأییدشده ← حداقل موجودی ← VIP فعال")
        Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Segmented(listOf(SegOption("week", "هفته"), SegOption("month", "ماه")), period, { period = it }, Modifier.fillMaxWidth())
            CompanyChips(company, { picked = it }, all = false)
            when {
                f == null && q?.error != null -> ErrorBlock(q.error, { q.refresh() })
                f == null -> Skeleton(Modifier.fillMaxWidth().height(220.dp))
                else -> Column {
                    val max = maxOf(1, f.stages.maxOfOrNull { it.count ?: 0 } ?: 1)
                    f.stages.forEachIndexed { i, s ->
                        if (i > 0) {
                            val conv = f.conversions.firstOrNull { it.from == f.stages[i - 1].key && it.to == s.key }
                            Row(Modifier.padding(start = 12.dp, top = 4.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                DIcon(DivanIcon.CHEVRON, size = 12.dp, tint = c.textMuted)
                                Text(buildAnnotatedString {
                                    if (conv?.rate != null) { append("تبدیل "); fig(rate(conv.rate), c.textSecondary) } else append("تبدیل: —")
                                }, style = Divan.type.micro, color = c.textMuted)
                            }
                        }
                        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            val live = s.connected && s.count != null
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(prose(s.labelFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
                                if (live) Fig(String.format(Locale.US, "%,d", s.count), style = Divan.type.figure.copy(fontSize = 15.sp, fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                                else Pill("وصل نیست", Tone.NEUTRAL)
                            }
                            if (live) MeterBar(maxOf(2.0, s.count!!.toDouble() / max * 100), height = 8.dp, color = color)
                            Text(prose(if (s.connected) "از ${SOURCE_FA[s.source] ?: s.source}" else WAITING[s.key] ?: "منبعی ندارد"), style = Divan.type.micro, color = c.textMuted)
                        }
                    }
                    for (l in f.leaks) {
                        Notice(DivanIcon.URGENT, c.softWarning, c.warning, Modifier.padding(top = 12.dp)) {
                            Text(buildAnnotatedString {
                                append("نشتی در «${f.stages.firstOrNull { it.key == l.stage }?.labelFa ?: l.stage}»: "); fig(rate(l.rate))
                                append(" در برابر میانه‌ی "); fig(rate(l.medianRate))
                            }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                            Text(prose(l.noteFa), style = Divan.type.caption, color = c.textSecondary)
                        }
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------------ rescue --
/** Referral rescue (§19.2): a case opens when a UID check says "not our invitee"; follow-ups run only under a sealed rescue rule.
 *  The rescue rate is the client's `rescued / (rescued + lost)` over the cases listed. */
@Composable
private fun RescueCard() {
    val env = LocalEnv.current
    val c = Divan.colors
    var state by rememberSaveable { mutableStateOf<String?>(null) }
    val all = rememberQuery("growth:rescue:all", "growth") { rescueCases() }
    val list = if (state == null) all else state.let { st -> rememberQuery("growth:rescue:$st", "growth") { rescueCases(state = st) } }
    var more by remember(list.data) { mutableStateOf(emptyList<RescueCase>()) }
    var cursor by remember(list.data) { mutableStateOf(list.data?.nextCursor) }
    val loadMore = rememberAction()
    var open by remember { mutableStateOf<RescueCase?>(null) }
    val every = all.data?.items.orEmpty()
    val items = list.data?.items?.let { it + more }
    val rescued = every.count { it.state == "rescued" }
    val lost = every.count { it.state == "lost" }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("نجات رفرال", note = "پیگیری فقط با قالب و قاعده‌ی مُهرشده؛ هیچ ایجنتی متن آزاد نمیفرستد")
        Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (rescued + lost > 0) Text(buildAnnotatedString {
                append("نرخ نجات "); fig(rate(rescued.toDouble() / (rescued + lost)), c.textPrimary, FontWeight.SemiBold)
                append("، از ${rescued + lost} پرونده‌ی بسته")
            }, style = Divan.type.small, color = c.textSecondary)
            ChipRow {
                FilterChip("همه", state == null, { state = null }, count = every.size)
                for ((k, l) in RESCUE_STATE) FilterChip(l.fa, state == k, { state = k }, count = every.count { it.state == k })
            }
            when {
                items == null && list.error != null -> ErrorBlock(list.error, { list.refresh() })
                items == null -> Skeleton(Modifier.fillMaxWidth().height(140.dp))
                items.isEmpty() -> Text("پرونده‌ای نیست.", style = Divan.type.small, color = c.textMuted, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp))
                else -> Column {
                    items.forEachIndexed { i, rc ->
                        if (i > 0) HorizontalDivider(color = c.lineDivider)
                        Row(
                            Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button) { open = rc }.padding(vertical = 10.dp, horizontal = 2.dp),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            CompanyMark(rc.company, height = 13.dp, mono = true, ink = c.textSecondary)
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text(prose(rc.steps.lastOrNull()?.resultFa ?: "—"), style = Divan.type.small, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Fig(rc.ref, style = Divan.type.figureSmall, color = c.textMuted)
                                    Text(if (rc.source == "support") "از پشتیبانی" else "از محصول", style = Divan.type.micro, color = c.textMuted)
                                    Text(ago(rc.openedAt), style = Divan.type.micro, color = c.textMuted)
                                }
                            }
                            LabelPill(RESCUE_STATE[rc.state], rc.state)
                        }
                    }
                }
            }
            cursor?.let { at ->
                HqButton("بیشتر", {
                    loadMore.run {
                        val pg = env.api.rescueCases(state = state, cursor = at)
                        more = more + pg.items
                        cursor = pg.nextCursor
                    }
                }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, loading = loadMore.busy)
            }
            Text("نرخ نجات = نجات‌یافته ÷ (نجات‌یافته + از دست رفته)، روی پرونده‌های همین فهرست.", style = Divan.type.micro, color = c.textMuted)
        }
    }
    open?.let { RescueSheet(it) { open = null } }
}

@Composable
private fun RescueSheet(seed: RescueCase, onClose: () -> Unit) {
    val nav = LocalNav.current
    val c = Divan.colors
    val companies = rememberCompanies()
    val q = rememberQuery("growth:rescue:one:${seed.ref}", "growth") { rescueCase(seed.ref) }
    val r = q.data ?: seed
    HqSheet(onClose, "پرونده‌ی نجات", ref = r.ref) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LabelPill(RESCUE_STATE[r.state], r.state)
            CompanyMark(r.company, height = 12.dp, mono = true, ink = c.textSecondary)
            Text(companyOf(companies, r.company).nameFa, style = Divan.type.caption, color = c.textSecondary)
        }
        FactRows(listOf(
            { m -> Fact("صرافی", r.exchange, m, figure = true) },
            { m -> Fact("منبع", if (r.source == "support") "گفت‌وگوی پشتیبانی" else "رویداد محصول", m) },
            { m -> Fact("مشتری (نام مستعار)", r.subject, m, figure = true) },
            { m -> Fact("باز شد", jDateTime(r.openedAt), m) },
        ))
        r.conversation?.let { conv ->
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).clickable(role = Role.Button) { onClose(); nav.go("support/$conv") }.padding(12.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                DIcon(DivanIcon.MESSAGES, size = 16.dp, tint = c.goldInk)
                Text(buildAnnotatedString { append("گفت‌وگوی "); fig(conv) }, style = Divan.type.small, modifier = Modifier.weight(1f))
                DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
            }
        }
        Text("گام‌ها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            for (st in r.steps) Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Box(Modifier.padding(top = 6.dp).size(8.dp).clip(CircleShape).background(c.goldInk))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(RESCUE_STEP[st.kind] ?: st.kind, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                        Text(jDateTime(st.at), style = Divan.type.micro, color = c.textMuted)
                        st.template?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                    }
                    Text(prose(st.resultFa), style = Divan.type.small, color = c.textPrimary)
                }
            }
        }
        when {
            r.rescuedAt != null -> Text("نجات یافت، ${jDateTime(r.rescuedAt)}", style = Divan.type.caption, color = c.positive)
            r.closedAt != null -> Text("بسته شد، ${jDateTime(r.closedAt)}", style = Divan.type.caption, color = c.textMuted)
        }
        Text("در این‌جا فقط نام مستعار مشتری است؛ UID و نام کاربری خام هرگز از شرکتش بیرون نمیاید.", style = Divan.type.micro, color = c.textMuted)
    }
}
