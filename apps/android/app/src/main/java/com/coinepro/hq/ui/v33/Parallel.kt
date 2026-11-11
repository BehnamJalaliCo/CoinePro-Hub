package com.coinepro.hq.ui.v33

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
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
import com.coinepro.hq.core.data.PART_STATE_FA
import com.coinepro.hq.core.data.SPLIT_STATE_FA
import com.coinepro.hq.core.data.WORKSPACE_STATE_FA
import com.coinepro.hq.core.data.partsDoneLine
import com.coinepro.hq.core.data.tokensShort
import com.coinepro.hq.core.data.workspaceStoppable
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.SplitPart
import com.coinepro.hq.core.net.WorkSplit
import com.coinepro.hq.core.net.WorkspaceProgress
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain

// Contract §33.7, §33.10 ⟨1.15⟩ in the order report: a split work's parts side by side (a failed part shown as failed, never hidden), the
// one merge that follows, and the works done in their own folder on their company's server, each with its progress and «توقف».

/** One card per split work: its parts side by side (a horizontal row on the phone), then the merge. */
@Composable
fun SplitCard(s: WorkSplit) {
    val c = Divan.colors
    val nav = LocalNav.current
    val st = SPLIT_STATE_FA[s.state] ?: (s.state to Tone.SILVER)
    HqCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.weight(1f)) {
                SectionTitle("بخش‌های موازی", note = "${partsDoneLine(s.parts)} بخش تحویل شد؛ بعد از همه، یک ادغام نوشته میشود")
            }
            Pill(st.first, st.second, dot = s.state != "running", live = s.state == "running" || s.state == "merging")
        }
        Row(
            Modifier.padding(top = 12.dp).fillMaxWidth().horizontalScroll(rememberScrollState()).height(IntrinsicSize.Max),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            for (p in s.parts.sortedBy { it.n }) PartTile(p) { nav.go("work/${p.ref}") }
        }
        Row(
            Modifier.padding(top = 12.dp).fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softGold).padding(12.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DIcon(DivanIcon.MEETING, size = 18.dp, tint = c.goldInk)
            Text(
                plain(when (s.state) {
                    "merging" -> "همه‌ی بخش‌ها رسیدند؛ ادغام در حال نوشتن است."
                    "done" -> "ادغام نوشته شد؛ خروجی نهایی در همین گزارش است."
                    "failed" -> "ادغام نشد؛ بخش ناموفق بالا پیداست."
                    "cancelled" -> "این تقسیم لغو شد."
                    else -> "ادغام وقتی نوشته میشود که همه‌ی بخش‌ها تمام شوند."
                }),
                Modifier.weight(1f), style = Divan.type.caption, color = c.textPrimary,
            )
        }
    }
}

@Composable
private fun PartTile(p: SplitPart, onOpen: () -> Unit) {
    val c = Divan.colors
    val st = PART_STATE_FA[p.state] ?: (p.state to Tone.SILVER)
    Column(
        Modifier.width(220.dp).fillMaxHeight().clip(RoundedCornerShape(14.dp)).background(c.tile)
            .then(if (p.state == "failed") Modifier.border(1.dp, c.negative.copy(alpha = 0.45f), RoundedCornerShape(14.dp)) else Modifier)
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Fig("${p.n}", style = Divan.type.figureSmall, color = c.textMuted)
            Pill(st.first, st.second, dot = p.state != "working", live = p.state == "working")
        }
        Text(plain(p.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 3)
        p.whoFa?.takeIf { it.isNotBlank() }?.let { Text(plain(it), style = Divan.type.micro, color = c.textMuted, maxLines = 1) }
        if (p.state == "working" && p.progressPct != null) MeterBar(p.progressPct.toDouble(), tone = BarTone.SILVER, height = 5.dp)
        when {
            p.state == "failed" -> Para(p.failedFa?.takeIf { it.isNotBlank() } ?: "این بخش تمام نشد.", style = Divan.type.caption, color = c.negative)
            p.outputTitleFa != null -> Text(plain("خروجی: ${p.outputTitleFa}"), style = Divan.type.caption, color = c.silverInk, maxLines = 2)
        }
        Box(Modifier.weight(1f, fill = false))
        if (p.tokensUsed > 0) Text(plain("${tokensShort(p.tokensUsed)} توکن" + (p.budgetTokens?.let { " از ${tokensShort(it)}" } ?: "")), style = Divan.type.micro, color = c.textMuted)
        HqButton("باز کن", onOpen, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
    }
}

/** A work done in its own folder on its company's server: where, how far, the last step, and «توقف» while it runs. */
@Composable
fun WorkspaceCard(w: WorkspaceProgress) {
    val c = Divan.colors
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val stop = rememberAction()
    var asking by rememberSaveable(w.workRef) { mutableStateOf(false) }
    val st = WORKSPACE_STATE_FA[w.state] ?: (w.state to Tone.SILVER)
    HqCard(Modifier.fillMaxWidth()) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Pill("روی سرور شرکت", Tone.LAPIS, icon = DivanIcon.SERVER)
            Pill(st.first, st.second, dot = w.state != "working", live = w.state == "working")
            Fig(w.workRef, style = Divan.type.figureSmall, color = c.textMuted)
        }
        if (w.whereFa.isNotBlank()) Text(plain(w.whereFa), Modifier.padding(top = 8.dp), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        w.lastStepFa?.takeIf { it.isNotBlank() }?.let { Para("آخرین قدم: $it", Modifier.padding(top = 4.dp), style = Divan.type.caption, color = c.textSecondary) }
        w.noteFa?.takeIf { it.isNotBlank() }?.let { Para(it, Modifier.padding(top = 4.dp), style = Divan.type.caption, color = if (w.state == "failed") c.negative else c.textSecondary) }
        Text(
            plain("${w.turns} نوبت کار" + (w.updatedAt.takeIf { it.isNotBlank() }?.let { "، آخرین تغییر ${ago(it)}" } ?: "")),
            Modifier.padding(top = 6.dp), style = Divan.type.micro, color = c.textMuted,
        )
        w.removeAfter?.let { Text(plain("پوشه‌ی کار ${jDate(it)} پاک میشود."), Modifier.padding(top = 2.dp), style = Divan.type.micro, color = c.textMuted) }
        if (workspaceStoppable(w.state)) Box(Modifier.padding(top = 10.dp)) {
            if (!asking) HqButton("توقف", { asking = true }, variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.STOP)
            else Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Para("کار روی سرور همین حالا متوقف میشود و تا تو دوباره راهش نیندازی چیزی اجرا نمیشود. کار باز میماند.", style = Divan.type.caption, color = c.textSecondary)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HqButton("متوقف کن", {
                        stop.run {
                            env.api.stopWork(w.workRef)
                            env.cache.invalidate("order-report", "orders", "work")
                            toasts.ok("کار روی سرور متوقف شد.")
                            asking = false
                        }
                    }, variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.STOP, loading = stop.busy)
                    HqButton("نه", { asking = false }, variant = BtnVariant.GHOST, size = BtnSize.SM)
                }
            }
        }
    }
}
