package com.coinepro.hq.ui.scorecard

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.CardKpi
import com.coinepro.hq.core.net.KpiCard
import com.coinepro.hq.core.net.KpiDef
import com.coinepro.hq.core.net.KpiPatch
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.ChartLine
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.LinesChart
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.Fact
import com.coinepro.hq.ui.v16.FactRows
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.CARD_FA
import com.coinepro.hq.ui.v17.KPI_STATE
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v17.ScopeChips
import com.coinepro.hq.ui.v17.Trend
import com.coinepro.hq.ui.v17.gov
import com.coinepro.hq.ui.v17.kpiFig
import com.coinepro.hq.ui.v17.num
import com.coinepro.hq.ui.v17.onTarget

/** کارت‌ها و امتیاز (contract §20.4): the three cards of the holding and of each company, and the live scorecard. Every figure has
 *  a source and a time; an old value is «قدیمی» and a KPI without a source is a dash, never zero. */
@Composable
fun ScorecardScreen(company0: String? = null) {
    val c = Divan.colors
    var company by rememberSaveable { mutableStateOf(company0) }
    var open by remember { mutableStateOf<String?>(null) }
    var targets by remember { mutableStateOf(false) }
    val q = rememberQuery("cards:${company.orEmpty()}", "cards", maxAgeMs = 60_000) { cards(company) }
    val defs = company?.let { co -> rememberQuery("kpis:$co", "kpis") { kpis(co) } }
    val dirs = defs?.data?.kpis.orEmpty().associate { it.key to it.direction }
    val r = refresher(*listOfNotNull(q, defs).toTypedArray())
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader(
                "کارت‌ها و امتیاز", eyebrow = "پایداری، رشد، ایمنی و هزینه؛ هر عدد با منبع و زمان",
                actions = if (company != null) ({ HqButton("هدف‌ها", { targets = true }, icon = DivanIcon.SETTINGS) }) else null,
            )
        }
        item {
            Text(
                "منبع هر KPI از رجیستری بسته‌ی کوئری‌های بازبینی‌شده است، یا دستی با شاهد. عددی که از تازگی‌اش گذشته «قدیمی» است و KPIای که منبعش ساخته نشده خط تیره است، هرگز صفر. کارت هلدینگ تجمیع شرکت‌هاست.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        item { ScopeChips(company, { company = it }, holding = false, allLabel = "هلدینگ") }
        val cards = q.data
        when {
            cards == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            cards == null -> item { Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 16.dp) }
            else -> for (card in cards) item(key = "card:${card.card}") { CardPanel(card, dirs, if (company != null) ({ k -> open = k }) else null) }
        }
        item(key = "scorecard") { Scorecard() }
    }
    val co = company
    val k = open?.let { key -> q.data?.flatMap { it.kpis }?.firstOrNull { it.key == key } }
    if (co != null && k != null) HqSheet({ open = null }, k.nameFa) { KpiView(co, k.key) }
    if (co != null && targets) TargetsSheet(co) { targets = false }
}

/** One KPI: its value with unit, the target, the trend, and how fresh it is. */
@Composable
private fun KpiRow(k: CardKpi, direction: String?, onOpen: (() -> Unit)?) {
    val c = Divan.colors
    // A card carries no direction for the holding: without the definition the row does not judge the target.
    val hit = onTarget(k.value, k.target, direction)
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).then(if (onOpen != null) Modifier.clickable(role = Role.Button, onClick = onOpen) else Modifier).padding(horizontal = 6.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(prose(k.nameFa), style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                if (k.state != "ok") LabelPill(KPI_STATE[k.state], k.state)
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Fig(kpiFig(k.value, k.unit), style = Divan.type.figureM.copy(fontSize = 18.sp, lineHeight = 26.sp), color = if (k.value == null) c.textMuted else c.textPrimary)
                if (k.target != null) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(buildAnnotatedString { append("هدف "); fig(kpiFig(k.target, k.unit)) }, style = Divan.type.micro, color = c.textMuted)
                    if (hit != null) DIcon(if (hit) DivanIcon.SEAL else DivanIcon.URGENT, size = 12.dp, tint = if (hit) c.positive else c.warning)
                }
            }
            Text(
                if (k.state == "no_source") buildAnnotatedString { append("منبعی در رجیستری نیست؛ عدد ساخته نمیشود") }
                else buildAnnotatedString { k.at?.let { append(ago(it)) }; k.sourceRef?.let { append(" · "); fig(it.ref) } },
                style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
        }
        Trend(k.trend, hit)
    }
}

@Composable
private fun CardPanel(card: KpiCard, dirs: Map<String, String>, onOpen: ((String) -> Unit)?) {
    val c = Divan.colors
    val meta = CARD_FA[card.card]
    val stale = card.kpis.count { it.state == "stale" }
    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(12.dp)) {
        Row(Modifier.padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.width(34.dp).height(34.dp).clip(RoundedCornerShape(10.dp)).background(c.tile), contentAlignment = Alignment.Center) { DIcon(meta?.icon ?: DivanIcon.CHART, size = 18.dp, tint = c.goldInk) }
            Column(Modifier.weight(1f)) {
                Text(meta?.fa ?: card.card, style = Divan.type.bodyStrong)
                Text(meta?.note.orEmpty(), style = Divan.type.micro, color = c.textMuted)
            }
            if (stale > 0) Pill("$stale قدیمی", Tone.WARN)
        }
        Spacer(Modifier.height(4.dp))
        card.kpis.forEachIndexed { i, k ->
            if (i > 0) Box(Modifier.fillMaxWidth().height(1.dp).background(c.lineDivider))
            KpiRow(k, dirs[k.key] ?: k.direction, onOpen?.let { f -> { f(k.key) } })
        }
    }
}

/** One KPI of a company's cards, with its definition: what the sheet shows when the owner opens a KPI. */
@Composable
fun KpiView(company: String, key: String) {
    val q = rememberQuery("cards:$company", "cards", maxAgeMs = 60_000) { cards(company) }
    val defs = rememberQuery("kpis:$company", "kpis") { kpis(company) }
    val k = q.data?.flatMap { it.kpis }?.firstOrNull { it.key == key }
    if (k == null) Skeleton(Modifier.fillMaxWidth().height(260.dp)) else KpiDetail(company, k, defs.data?.kpis?.firstOrNull { it.key == key })
}

/** One KPI over 30 days, from its own values (every value with its source). */
@Composable
private fun KpiDetail(company: String, k: CardKpi, def: KpiDef?) {
    val c = Divan.colors
    val to = HqClock.today()
    val from = to.minusDays(30)
    val q = rememberQuery("kpis:values:$company:${k.key}:$from:$to", "kpis") { kpiValues(company, k.key, from.toString(), to.toString()) }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        def?.let { d -> Text(if (d.source.kind == "query") "از رجیستری: ${d.source.query}" else "دستی، با kpi.record و شاهد", style = Divan.type.caption, color = c.textMuted) }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Fig(kpiFig(k.value, k.unit), style = Divan.type.figureL.copy(fontSize = 26.sp), color = c.textPrimary)
            if (k.target != null) Text(buildAnnotatedString { append("هدف "); fig(kpiFig(k.target, k.unit)) }, style = Divan.type.small, color = c.textSecondary)
            LabelPill(KPI_STATE[k.state], k.state)
        }
        val vs = q.data
        when {
            vs == null -> Skeleton(Modifier.fillMaxWidth().height(220.dp))
            vs.size < 2 -> Empty("مقداری برای نمودار نیست", icon = DivanIcon.CHART, body = if (k.state == "no_source") "تا منبع وصل نشود، این KPI عدد ندارد؛ هرگز صفر نشان داده نمیشود." else null)
            else -> LinesChart(
                vs.map { jDate(it.at) }, listOf(ChartLine(k.key, k.nameFa, c.chart[0], vs.map { it.value })),
                { v -> kpiFig(Math.round(v * 100) / 100.0, k.unit) }, "روند ${k.nameFa}",
            )
        }
        def?.let { d ->
            FactRows(listOf(
                { m -> Fact("جهت", if (d.direction == "up") "بیشتر بهتر" else "کمتر بهتر", m) },
                { m -> Fact("تازگی", "${d.freshnessHours} ساعت", m) },
                { m -> Fact("تجمیع در هلدینگ", d.aggregate, m, figure = true) },
                { m -> Fact("کارت امتیاز", if (d.scorecard) "بله" else "نه", m) },
            ))
        }
        vs?.lastOrNull()?.let { last ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("آخرین منبع:", style = Divan.type.caption, color = c.textMuted)
                RefChip(last.sourceRef.ref, last.sourceRef.note.ifBlank { null }, RefTone.NEUTRAL)
            }
        }
    }
}

/** Targets and which KPIs make the scorecard: the owner's to set (If-Match on the company's set). */
@Composable
private fun TargetsSheet(company: String, onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val q = rememberQuery("kpis:$company", "kpis") { kpis(company) }
    val edit = remember { mutableStateMapOf<String, KpiPatch>() }
    val text = remember { mutableStateMapOf<String, String>() }
    HqSheet(onClose, "هدف‌ها و کارت امتیاز", sub = "تحقق KPI در امتیاز شرکت (۳۵٪) از همین هدف‌هاست، وقتی OKR فعالی نیست.") {
        val set = q.data
        if (set == null) Skeleton(Modifier.fillMaxWidth().height(260.dp))
        else {
            for (k in set.kpis) {
                val p = edit[k.key] ?: KpiPatch(k.key, k.target, k.scorecard, k.status, k.freshnessHours)
                fun put(n: KpiPatch) { if (n == KpiPatch(k.key, k.target, k.scorecard, k.status, k.freshnessHours)) edit.remove(k.key) else edit[k.key] = n }
                Column(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(k.nameFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                    Text(buildAnnotatedString { fig(if (k.source.kind == "query") k.source.query.orEmpty() else "manual"); append(" · " + (CARD_FA[k.card]?.fa ?: k.card)) }, style = Divan.type.micro, color = c.textMuted)
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("هدف", style = Divan.type.caption, color = c.textSecondary)
                        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                            HqTextField(text[k.key] ?: p.target?.let(::num).orEmpty(), { v ->
                                val clean = v.filter { it.isDigit() || it == '.' }
                                text[k.key] = clean
                                put(p.copy(target = clean.toDoubleOrNull()))
                            }, "—", Modifier.width(96.dp), maxLength = 12, figure = true)
                        }
                        Fig(k.unit, style = Divan.type.figureSmall, color = c.textMuted)
                        Spacer(Modifier.weight(1f))
                        Text("تازگی", style = Divan.type.caption, color = c.textSecondary)
                        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                            HqTextField(p.freshnessHours.toString(), { v -> put(p.copy(freshnessHours = v.filter(Char::isDigit).toIntOrNull()?.coerceAtLeast(1) ?: 1)) }, "24", Modifier.width(60.dp), maxLength = 4, figure = true)
                        }
                        Fig("h", style = Divan.type.figureSmall, color = c.textMuted)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        HqSwitch(p.scorecard, { put(p.copy(scorecard = it)) }, "کارت امتیاز: ${k.nameFa}")
                        Text("امتیاز", style = Divan.type.caption, color = c.textSecondary)
                        Spacer(Modifier.width(12.dp))
                        HqSwitch(p.status == "active", { put(p.copy(status = if (it) "active" else "paused")) }, "فعال: ${k.nameFa}")
                        Text("فعال", style = Divan.type.caption, color = c.textSecondary)
                    }
                    Box(Modifier.fillMaxWidth().height(1.dp).background(c.lineDivider))
                }
            }
            HqButton("ذخیره", {
                action.gov(toasts) {
                    env.api.putKpis(set, set.kpis.mapNotNull { edit[it.key] })
                    env.cache.invalidate("kpis", "cards", "scorecards")
                    toasts.ok("هدف‌ها ذخیره شد؛ کارت‌ها و امتیاز شرکت از همین حساب میشوند.")
                    onClose()
                }
            }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, enabled = edit.isNotEmpty(), loading = action.busy)
        }
    }
}

/** The live scorecard: one row per company (any number, paged and searchable), each a scorecard KPI with value, target and trend. */
@Composable
private fun Scorecard() {
    val c = Divan.colors
    var text by rememberSaveable { mutableStateOf("") }
    val q = rememberQuery("scorecards:${text.trim()}", "scorecards", "cards") { scorecards(text) }
    val companies = rememberCompanies()
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("کارت امتیاز", note = "یک ردیف برای هر شرکت؛ هر عدد با زمان و منبع")
        Spacer(Modifier.height(8.dp))
        HqTextField(text, { text = it }, "جستجوی شرکت", Modifier.fillMaxWidth(), maxLength = 60)
        Spacer(Modifier.height(10.dp))
        val rows = q.data?.items
        when {
            rows == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            rows == null -> Skeleton(Modifier.fillMaxWidth().height(160.dp))
            rows.isEmpty() -> Empty("شرکتی پیدا نشد", icon = DivanIcon.CHART)
            else -> Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                for (row in rows) Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(10.dp)) {
                    Row(Modifier.padding(horizontal = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        CompanyMark(row.company, height = 14.dp, mono = true, ink = c.textPrimary)
                        Text(companyOf(companies, row.company).nameFa, style = Divan.type.bodyStrong)
                    }
                    row.kpis.forEachIndexed { i, k ->
                        if (i > 0) Box(Modifier.fillMaxWidth().height(1.dp).background(c.lineDivider))
                        KpiRow(k, k.direction, null)
                    }
                }
            }
        }
    }
}
