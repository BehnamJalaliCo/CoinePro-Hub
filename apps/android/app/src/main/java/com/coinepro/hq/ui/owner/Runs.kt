package com.coinepro.hq.ui.owner

import com.coinepro.hq.ui.itemMotion
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.Run
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.Label
import com.coinepro.hq.ui.v14.LabelPill

val RUN_STATE = mapOf(
    "queued" to Label("در صف", Tone.NEUTRAL),
    "running" to Label("در حال اجرا", Tone.GOLD, live = true),
    "done" to Label("تمام شد", Tone.POS),
    "failed" to Label("شکست", Tone.NEG),
    "refused" to Label("رد شد", Tone.WARN),
)

/** One agent run (contract §16.2): who, why, model, tokens; opens to its steps and tool calls. A running run refreshes itself. */
@Composable
fun RunRow(run: Run, showEmployee: Boolean = true, withSteps: Boolean = false) {
    val c = Divan.colors
    val nav = LocalNav.current
    var open by rememberSaveable(run.id) { mutableStateOf(false) }
    val detail = if (open && !withSteps) rememberQuery("run:${run.id}", "runs", maxAgeMs = if (run.state == "running") 4_000 else 60_000) { runDetail(run.id) } else null
    val d = if (withSteps) run else detail?.data
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile)) {
        Column(Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = if (open) "بستن" else "قدم‌ها") { open = !open }.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                LabelPill(RUN_STATE[run.state], run.state)
                if (showEmployee) Fig(run.employee, style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                // The hub's reason can carry a ref ("PR-001"): rich text keeps it Latin.
                com.coinepro.hq.designsystem.RichText(run.reason, Modifier.weight(1f), style = Divan.type.small, color = c.textSecondary, maxLines = 1)
                com.coinepro.hq.designsystem.Chevron(open, tint = c.textMuted)
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(ago(run.startedAt ?: run.queuedAt), style = Divan.type.micro, color = c.textMuted)
                run.model?.let { Fig(modelLabel(it), style = Divan.type.figureSmall, color = c.textMuted) }
                Text("${run.steps} قدم، ${run.toolCalls} ابزار", style = Divan.type.micro, color = c.textMuted)
                Fig("${tokens(run.tokens.input + run.tokens.output)} · ${usd(run.equivCostUsd)}", style = Divan.type.figureSmall, color = c.textMuted)
                run.workRef?.let { w -> Fig(w, style = Divan.type.figureSmall, color = c.goldInk, modifier = Modifier.clickable { nav.go("work/$w") }) }
                run.errorCode?.let { Fig(it, style = Divan.type.figureSmall, color = c.negative) }
            }
        }
        com.coinepro.hq.designsystem.Expand(open) { Column {
            HorizontalDivider(color = c.lineDivider)
            Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                when {
                    d == null && detail?.error != null -> ErrorBlock(detail.error, { detail.refresh() })
                    d == null -> Skeleton(Modifier.fillMaxWidth().height(56.dp))
                    d.stepsDetail.isEmpty() -> Text("هنوز قدمی ثبت نشده.", style = Divan.type.caption, color = c.textMuted)
                    else -> d.stepsDetail.forEach { s ->
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(s.summaryFa, style = Divan.type.small, color = c.textPrimary)
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text(com.coinepro.hq.designsystem.timesFig(jDateTime(s.at)), style = Divan.type.micro, color = c.textMuted)
                                s.actions.forEach { a ->
                                    val tint = when (a.outcome) { "ok" -> c.positive; "refused", "held" -> c.warning; "error" -> c.negative; else -> c.textMuted }
                                    Text(buildAnnotatedString { fig(a.tool); append(" "); fig(a.outcome, color = tint); a.ref?.let { append(" "); fig(it, color = c.textMuted) } },
                                        style = Divan.type.micro, color = c.textSecondary,
                                        modifier = Modifier.clip(RoundedCornerShape(20.dp)).background(c.card).padding(horizontal = 8.dp, vertical = 2.dp))
                                }
                            }
                        }
                    }
                }
            }
        } }
    }
}

@Composable
fun RunList(runs: List<Run>, empty: String, showEmployee: Boolean = true, withSteps: Boolean = false) {
    val c = Divan.colors
    if (runs.isEmpty()) Text(empty, style = Divan.type.caption, color = c.textMuted, modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp))
    else Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { runs.forEach { RunRow(it, showEmployee, withSteps) } }
}

/** Every agent run, live (§16.2); ⟨1.5⟩ the claims checked and the health board of §21.9 (refuted claims, failures, loops). */
@Composable
fun RunsScreen() {
    val c = Divan.colors
    val nav = LocalNav.current
    var tab by rememberSaveable { mutableStateOf<String?>(null) }
    val all = rememberQuery("runs:all", "runs", maxAgeMs = 15_000) { runs(limit = 200) }
    val list = rememberQuery("runs:${tab ?: "all"}", "runs", maxAgeMs = 15_000) { runs(state = tab, limit = 100) }
    val r = refresher(all, list)
    val items = all.data?.items.orEmpty()
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("اجرای ایجنت‌ها", eyebrow = "هر اجرای هر ایجنت، با قدم‌ها و ابزارها و مصرف") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(Modifier.weight(1f)) { StatTile("اجرای اخیر", "${items.size}", figure = false) }
                Box(Modifier.weight(1f)) { StatTile("در جریان", "${items.count { it.state == "running" }}", figure = false) }
                Box(Modifier.weight(1f)) { val bad = items.count { it.state == "failed" || it.state == "refused" }; StatTile("شکست یا رد", "$bad", figure = false, tone = if (bad > 0) Tone.WARN else null) }
            }
        }
        item {
            com.coinepro.hq.designsystem.ScrollRow {
                listOf(null to "همه", "running" to "در جریان", "failed" to "شکست", "refused" to "رد شده", "queued" to "در صف").forEach { (k, l) -> FilterChip(l, tab == k, { tab = k }) }
            }
        }
        val rows = list.data?.items
        when {
            rows == null && list.error != null -> item { ErrorBlock(list.error, { list.refresh() }) }
            rows == null -> item { Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 14.dp) }
            rows.isEmpty() -> item { Text("اجرایی با این وضعیت نیست.", style = Divan.type.caption, color = c.textMuted) }
            else -> items(rows, key = { it.id }) { Box(itemMotion()) { RunRow(it) } }
        }
        // ⟨1.5⟩ §21.9: claims checked and the health board by rule.
        item { ClaimsCard() }
        item { HealthBoard() }
    }
}
