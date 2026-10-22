package com.coinepro.hq.ui.outcomes

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.OutcomeReview
import com.coinepro.hq.core.net.accuracy
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.ActorAvatar
import com.coinepro.hq.ui.v17.OUTCOME_STATUS
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.ScopeChips
import com.coinepro.hq.ui.v17.VERDICT
import com.coinepro.hq.ui.v17.kpiFig
import com.coinepro.hq.ui.v17.pct01

/** A metric in percent is measured in %; the rest are plain counts. */
fun unitOf(metric: String): String = if (Regex("٪|%").containsMatchIn(metric)) "%" else ""

/** بازبینی نتیجه (contract §20.6): what each sealed decision promised, measured at 30, 60 and 90 days; prediction accuracy comes
 *  from the verdicts. */
@Composable
fun OutcomesScreen() {
    val c = Divan.colors
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var verdict by rememberSaveable { mutableStateOf<String?>(null) }
    var due by rememberSaveable { mutableStateOf(false) }
    val q = rememberQuery("outcomes:${company.orEmpty()}:${verdict.orEmpty()}:$due", "outcomes") { outcomes(company, verdict, due).items }
    val all = rememberQuery("outcomes:${company.orEmpty()}::false", "outcomes") { outcomes(company).items }
    val r = refresher(q, all)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("بازبینی نتیجه", eyebrow = "قول هر تصمیم در ۳۰، ۶۰ و ۹۰ روز با عدد سنجیده میشود") }
        item {
            Text(
                "با KPI حکم را کد میدهد: «رسید» در هدف، «نیمه‌راه» از نیمه‌ی فاصله به بعد، وگرنه «نرسید». بی‌KPI، پیشنهاددهنده یادداشت و شاهد میدهد و ناظر حکم میکند. دقت پیش‌بینی مدیرها و مدیرعامل‌ها از همین حکم‌هاست.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        val every = all.data.orEmpty()
        fun by(v: String) = every.count { it.verdict == v }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    StatTile("رسید", "${by("met")}", Modifier.weight(1f), tone = Tone.POS)
                    StatTile("نیمه‌راه", "${by("partly")}", Modifier.weight(1f), tone = Tone.WARN)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    StatTile("نرسید", "${by("missed")}", Modifier.weight(1f), tone = Tone.NEG)
                    StatTile("منتظر سنجش یا حکم", "${by("pending") + by("unmeasurable")}", Modifier.weight(1f))
                }
            }
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                ScopeChips(company, { company = it }, holding = false, allLabel = "همه‌ی شرکت‌ها")
                ChipRow {
                    FilterChip("همه‌ی حکم‌ها", verdict == null, { verdict = null })
                    for ((k, l) in VERDICT) FilterChip(l.fa, verdict == k, { verdict = k })
                    FilterChip("فقط موعدرسیده", due, { due = !due })
                }
            }
        }
        val rows = q.data
        when {
            rows == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            rows == null -> item { Skeleton(Modifier.fillMaxWidth().height(260.dp), radius = 16.dp) }
            rows.isEmpty() -> item { Empty("بازبینی‌ای نیست", icon = DivanIcon.REFRESH) }
            else -> for ((decision, rs) in rows.groupBy { it.decision }) item(key = decision) { DecisionGroup(decision, rs.sortedBy { it.day }) }
        }
        item(key = "accuracy") { Accuracy(every) }
    }
}

@Composable
private fun DecisionGroup(decision: String, rs: List<OutcomeReview>) {
    val c = Divan.colors
    val e = rs.first().expected
    val u = unitOf(e.metricFa)
    HqCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            CompanyMark(rs.first().company, height = 13.dp, mono = true, ink = c.textSecondary)
            RefChip(decision)
            ActorAvatar(rs.first().proposer, 18.dp)
            Text(actorFa(rs.first().proposer), style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Spacer(Modifier.height(8.dp))
        Text(prose(e.metricFa), style = Divan.type.bodyStrong, color = c.textPrimary)
        Spacer(Modifier.height(2.dp))
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Fig("${kpiFig(e.baseline, u)} → ${kpiFig(e.target, u)}", style = Divan.type.figure, color = c.textSecondary)
            Text(buildAnnotatedString { append("تا ${e.byDays} روز"); if (e.kpi != null) { append(" · "); fig("KPI ${e.kpi}") } else append(" · بی‌KPI") }, style = Divan.type.caption, color = c.textMuted)
        }
        Spacer(Modifier.height(10.dp))
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { for (r in rs) Review(r) }
    }
}

@Composable
private fun Review(r: OutcomeReview) {
    val c = Divan.colors
    val u = unitOf(r.expected.metricFa)
    val due = r.status == "due" && r.verdict == "pending" && (instant(r.dueAt)?.toEpochMilli() ?: Long.MAX_VALUE) <= HqClock.millis()
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).then(if (due) Modifier.border(1.dp, c.goldInk, RoundedCornerShape(12.dp)) else Modifier).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("روز ${r.day}", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            Fig(r.ref, style = Divan.type.figureSmall, color = c.textMuted)
            Spacer(Modifier.weight(1f))
            LabelPill(VERDICT[r.verdict], r.verdict)
        }
        Text(
            r.measured?.let { m -> buildAnnotatedString { append("اندازه "); fig(kpiFig(m.value, u), c.textPrimary); append(" · ${jDate(m.at)}") } } ?: buildAnnotatedString { append("موعد ${jDate(r.dueAt)}") },
            style = Divan.type.caption, color = c.textSecondary,
        )
        Text(OUTCOME_STATUS[r.status] ?: r.status, style = Divan.type.micro, color = c.textMuted)
        r.proposerNoteMd?.let { Note("یادداشت پیشنهاددهنده", it) }
        r.overseerNoteMd?.let { Note("حکم ناظر", it) }
        if (r.expected.kpi == null && r.status == "answered" && r.verdict == "pending") Text(buildAnnotatedString { append("منتظر حکم ناظر ("); fig("PR-006"); append(")") }, style = Divan.type.micro, color = c.warning)
    }
}

@Composable
private fun Note(title: String, md: String) {
    val c = Divan.colors
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(c.card).padding(8.dp)) {
        Text(title, style = Divan.type.micro, color = c.textMuted)
        Md(md)
    }
}

/** Prediction accuracy by proposer: met 1, partly ½, missed 0. */
@Composable
private fun Accuracy(every: List<OutcomeReview>) {
    val c = Divan.colors
    val people = every.groupBy { it.proposer.code }.values.map { rs ->
        Triple(rs.first().proposer, accuracy(rs), rs.count { it.verdict in setOf("met", "partly", "missed") })
    }.sortedByDescending { it.second ?: -1.0 }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("دقت پیش‌بینی", note = "رسید ۱، نیمه‌راه نیم، نرسید صفر")
        Spacer(Modifier.height(8.dp))
        if (people.isEmpty()) Text("هنوز حکمی نیست.", style = Divan.type.caption, color = c.textMuted)
        for ((a, acc, n) in people) Row(Modifier.padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            ActorAvatar(a, 28.dp)
            Column(Modifier.weight(1f)) {
                Text(actorFa(a), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("$n حکم سنجیده", style = Divan.type.micro, color = c.textMuted)
            }
            Fig(pct01(acc), style = Divan.type.figure.copy(fontSize = 15.sp), color = when { acc == null -> c.textMuted; acc >= 0.7 -> c.positive; acc >= 0.4 -> c.warning; else -> c.negative })
        }
    }
}
