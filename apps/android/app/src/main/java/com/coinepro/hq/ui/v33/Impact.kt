package com.coinepro.hq.ui.v33

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.data.IMPACT_KIND_FA
import com.coinepro.hq.core.data.hasImpact
import com.coinepro.hq.core.data.impactMonthly
import com.coinepro.hq.core.data.impactText
import com.coinepro.hq.core.data.moneyFigure
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.DecisionImpact
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain

// Contract §33.6 ⟨1.15⟩: the money a decision card moves. A measured figure is a solid chip; an estimate is a dashed outline with the word
// «تخمین» in front, so the two are never mistaken for each other. A tap opens the basis in plain words.

/** «+120 USDT/ماه» on a decision card; nothing at all when the hub has no figure for it. */
@Composable
fun ImpactChip(impact: DecisionImpact?, modifier: Modifier = Modifier) {
    if (impact == null || !hasImpact(impact)) return
    val c = Divan.colors
    val measured = impact.kind == "measured"
    val tint = if (impactMonthly(impact) >= 0) c.positive else c.negative
    var open by remember { mutableStateOf(false) }
    Row(
        modifier.height(24.dp).clip(CircleShape)
            .then(
                if (measured) Modifier.background(tint.copy(alpha = 0.14f))
                else Modifier.drawBehind {
                    drawRoundRect(tint.copy(alpha = 0.75f), cornerRadius = CornerRadius(size.height / 2), style = Stroke(1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(5.dp.toPx(), 3.dp.toPx()))))
                },
            )
            .clickable(role = Role.Button, onClickLabel = "پایه‌ی این عدد") { open = true }
            .padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        if (measured) DIcon(DivanIcon.SEAL, size = 12.dp, tint = tint)
        else Text("تخمین", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold, fontSize = 11.sp), color = tint)
        Text(timesFig(impactText(impact)), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold, fontSize = 12.sp), color = tint, maxLines = 1)
    }
    if (open) com.coinepro.hq.ui.v14.HqSheet({ open = false }, "اثر پولی این کارت", sub = IMPACT_KIND_FA[impact.kind] ?: impact.kind) {
        ImpactBasis(impact)
    }
}

/** The basis of an impact: what the figure is made of and over how many days. */
@Composable
fun ImpactBasis(impact: DecisionImpact) {
    val c = Divan.colors
    val measured = impact.kind == "measured"
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Pill(if (measured) "اندازه‌گیری‌شده" else "تخمین", if (measured) Tone.POS else Tone.LAPIS, icon = if (measured) DivanIcon.SEAL else DivanIcon.INFO)
            Pill(impactText(impact), if (impactMonthly(impact) >= 0) Tone.POS else Tone.NEG)
        }
        impact.revenueUsdt?.let { Text(plain("درآمد: ${moneyFigure(it)} USDT در ${impact.horizonDays} روز"), style = Divan.type.small, color = c.textPrimary) }
        impact.costUsd?.let { Text(plain("هزینه: ${moneyFigure(it)} دلار در ${impact.horizonDays} روز"), style = Divan.type.small, color = c.textPrimary) }
        if (impact.basisFa.isNotBlank()) Para(impact.basisFa, style = Divan.type.small, color = c.textSecondary)
        Para(
            if (measured) "این عدد را کد از روی داده‌ی خود شرکت حساب کرده است." else "این فقط یک تخمین است، نه حساب دقیق؛ مدل آن را از روی پیشنهاد و دانش شرکت نوشته. بعد از مُهر، عدد واقعی اندازه گرفته میشود.",
            style = Divan.type.caption, color = c.textMuted,
        )
    }
}
