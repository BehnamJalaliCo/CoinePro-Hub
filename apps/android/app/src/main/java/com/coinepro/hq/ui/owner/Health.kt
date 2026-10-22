package com.coinepro.hq.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.AgentHealth
import com.coinepro.hq.core.net.CheckedClaim
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v17.ActorAvatar
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v18.HEALTH
import com.coinepro.hq.ui.v18.VERDICT_CLAIM
import com.coinepro.hq.ui.v18.pct01

/** The agent health board (§21.9), one row per employee, by rule: refuted claims, failures, refusals, retry loops and the owner's returns. */
@Composable
fun HealthBoard(company: String? = null) {
    val c = Divan.colors
    val nav = LocalNav.current
    var period by rememberSaveable { mutableStateOf("7d") }
    val q = rememberQuery("runs-health:$period:${company.orEmpty()}", "runs", "claims") { runsHealth(period, company).items }
    val rows = q.data.orEmpty().sortedWith(compareByDescending<AgentHealth> { it.flags.size }.thenByDescending { it.failedShare })
    HqCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SectionTitle("سلامت کارمندها", Modifier.weight(1f), note = "پرچم‌ها قاعده‌اند؛ ادعای رد شده به بسته‌ی ارزیابی ماهانه هم میرود")
            Segmented(listOf(SegOption("7d", "۷ روز"), SegOption("30d", "۳۰ روز")), period, { period = it }, Modifier.width(132.dp))
        }
        Column(Modifier.padding(top = 10.dp)) {
            when {
                q.data == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
                q.data == null -> Skeleton(Modifier.fillMaxWidth().height(180.dp))
                rows.isEmpty() -> Text("هنوز اجرایی نیست.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(vertical = 12.dp))
                else -> rows.forEachIndexed { i, h ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    HealthRow(h) { nav.go("employees/${h.employee}") }
                }
            }
        }
        Text(
            HEALTH.values.joinToString(" · ") { (l, note) -> "${l.fa}: $note" },
            style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 8.dp),
        )
    }
}

@Composable
private fun HealthRow(h: AgentHealth, onOpen: () -> Unit) {
    val c = Divan.colors
    Column(Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = onOpen).padding(vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            CoMark(h.company, height = 11.dp)
            Fig(h.employee, style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.weight(1f))
            for (f in h.flags) LabelPill(HEALTH[f]?.first, f)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Stat("اجرا", "${h.runs}", c.textSecondary)
            Stat("شکست", pct01(h.failedShare), if (h.failedShare >= 0.25) c.negative else c.textSecondary)
            Stat("رد", pct01(h.refusedShare), if (h.refusedShare >= 0.1) c.warning else c.textMuted)
            Stat("حلقه", "${h.retryLoops}", if (h.retryLoops >= 2) c.warning else c.textMuted)
            Stat("برگشت تو", "${h.ownerReturns}", if (h.ownerReturns > 0) c.warning else c.textMuted)
            Stat(
                "ادعا (رد)",
                "${h.claimsChecked} (${h.refuted}${if (h.refutedShare != null && h.claimsChecked > 0) " · ${pct01(h.refutedShare)}" else ""})",
                if (h.refuted > 0) c.negative else c.textSecondary,
            )
            Stat("مصرف", usd(h.costUsd), c.textSecondary)
        }
    }
}

@Composable
private fun Stat(label: String, value: String, color: Color) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = Divan.type.micro, color = Divan.colors.textMuted)
        Fig(value, style = Divan.type.figureSmall, color = color)
    }
}

/** Claims checked by the fact checker, the overseer or QC (§21.9); a refuted one always carries its evidence. */
@Composable
fun ClaimsCard(company: String? = null) {
    val c = Divan.colors
    var verdict by rememberSaveable { mutableStateOf<String?>("refuted") }
    val q = rememberQuery("claims:${verdict.orEmpty()}:${company.orEmpty()}", "claims", "runs") { claims(company = company, verdict = verdict).items }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("ادعاهای بررسی‌شده", note = "هیچ ادعایی فقط با حرف یک بازیکن ذخیره رد یا تأیید نمیشود")
        Column(Modifier.padding(top = 10.dp)) {
            ChipRow {
                FilterChip("همه", verdict == null, { verdict = null })
                for (v in listOf("refuted", "confirmed", "unverifiable")) FilterChip(VERDICT_CLAIM.getValue(v).fa, verdict == v, { verdict = v })
            }
        }
        val items = q.data
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            when {
                items == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
                items == null -> Skeleton(Modifier.fillMaxWidth().height(120.dp))
                items.isEmpty() -> Text("ادعایی با این حکم نیست.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp))
                else -> items.forEach { ClaimRow(it) }
            }
        }
    }
}

@Composable
private fun ClaimRow(x: CheckedClaim) {
    val c = Divan.colors
    val nav = LocalNav.current
    val v = VERDICT_CLAIM[x.verdict] ?: VERDICT_CLAIM.getValue("unverifiable")
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Fig(x.ref, style = Divan.type.figureSmall, color = c.textMuted)
            CoMark(x.company, height = 10.dp)
            if (x.employee.isNotBlank()) Fig(x.employee, style = Divan.type.figureSmall, color = c.textSecondary, modifier = Modifier.clickable { nav.go("employees/${x.employee}") })
            if (x.deliverable.isNotBlank()) RefChip(x.deliverable)
            Text(ago(x.at), style = Divan.type.micro, color = c.textMuted)
        }
        Md("«${x.claimMd}»", style = Divan.type.small, color = c.textPrimary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Pill(v.fa, v.tone, icon = v.icon)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                ActorAvatar(x.checkedBy, size = 18.dp)
                Text(actorFa(x.checkedBy), style = Divan.type.micro, color = c.textSecondary)
            }
            x.protocol?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
        }
        for (e in x.evidence) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            DIcon(DivanIcon.SEAL, size = 12.dp, tint = if (x.verdict == "refuted") c.negative else c.textSecondary)
            Fig(e.ref, style = Divan.type.figureSmall, color = c.textSecondary)
            if (e.note.isNotBlank()) Md("· ${e.note}", Modifier.weight(1f), style = Divan.type.micro, color = c.textMuted)
        }
    }
}

